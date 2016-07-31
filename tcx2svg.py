#!/usr/bin/env python

## * Copyright (C) 2009-2011 Percy Zahl
## *
## * Author: Percy Zahl <zahl@users.sf.net>
## * WWW Home: http://tcx2svg.sf.net
## *
## * This program is free software; you can redistribute it and/or modify
## * it under the terms of the GNU General Public License as published by
## * the Free Software Foundation; either version 2 of the License, or
## * (at your option) any later version.
## *
## * This program is distributed in the hope that it will be useful,
## * but WITHOUT ANY WARRANTY; without even the implied warranty of
## * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## * GNU General Public License for more details.
## *
## * You should have received a copy of the GNU General Public License
## * along with this program; if not, write to the Free Software
## * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307, USA.

version = "2.1.0"

import pygtk
pygtk.require('2.0')

import gobject, gtk
import sys
import os
import subprocess
import time
import math
import fcntl

from xml.dom.minidom import parse, parseString
from gtkforms import *

import pango
import gtk.gdk as gdk

#import GtkExtra
import struct
#import array
from numpy import *


### ROUTE & KML SETUP ###
# reading coordinates from kml, GPS route, ... start tag:
# <coordinates>lat,lon,ele lat,lon, ele ...</coordinate>
route = 'cedarcreekC4'
track = 'cedarcreekC4.xml'

data_file = 'data_raw.asc'

svg_info_file = 'data_'

global grade
global rider_draft
global mg_rider
global mrider

global distance
global distance_wheel
global elevation
global climb
global map_elevation
global grade_map

global speed
global speed_dt_hist
global speed_av
global power_av
global power
global speed_rel_av
global speed_real

global speed_max
global power_max

global time_last_reading
global moving_time
global readings

global rounds
global cad
global hr

global rider_last
global rider_update_distance

global rider_view_range
global rider_view_tilt
global rider_view_height

global n_smooth
global hskl
global osd_text
global refresh
refresh=0

global ant_idle_counts

global p_slow_peak
global v_slow_peak

p_slow_peak=0
v_slow_peak=0

#Zone Description Low
#Z1 Active Recovery 0
#Z2 Endurance 132
#Z3 Tempo 180
#Z4 Threshold 216
#Z5 VO2Max 253
#Z6 Anaerobic 289
#Z7 Neuromuscular 361

speed_zones_low = (0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100)

power_zones_Z   = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
power_zones_low = (0, 132, 180, 216, 253, 289, 361, 500, 750, 1000)

CritPwr = 241
VO2Max  = 253

# Zone 1..7 regular
# +Zone .. 9 == 1000

def find_zone_i(x, zones_low):
    z=0
    for low in zones_low:
        z=z+1
        if x < low:
            return z
    return 10

def find_zone(x, zones_low):
    z=0
    p=0
    for low in zones_low:
        z=z+1
        if x < low:
            return z + (1-(low-x)/(low-p))
        p=low
    return 10

dialog = gtk.FileChooserDialog("Select GPS track data file to read...",
                                None,
                                gtk.FILE_CHOOSER_ACTION_OPEN,
                                (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                 gtk.STOCK_OPEN, gtk.RESPONSE_OK))
dialog.set_default_response(gtk.RESPONSE_OK)

filter = gtk.FileFilter()
filter.set_name("TCX")
filter.add_mime_type("track/tcx")
filter.add_pattern("*.tcx")
filter.add_pattern("*.TCX")
dialog.add_filter(filter)

filter = gtk.FileFilter()
filter.set_name("GPX")
filter.add_mime_type("track/gpx")
filter.add_pattern("*.gpx")
filter.add_pattern("*.GPX")
dialog.add_filter(filter)

filter = gtk.FileFilter()
filter.set_name("KML")
filter.add_mime_type("track/kml")
filter.add_pattern("*.kml")
filter.add_pattern("*.KML")
dialog.add_filter(filter)

filter = gtk.FileFilter()
filter.set_name("All files")
filter.add_pattern("*")
dialog.add_filter(filter)

response = dialog.run()

if response == gtk.RESPONSE_OK:
    print dialog.get_filename(), 'selected'
    track = dialog.get_filename()
    route = track[:-4]
elif response == gtk.RESPONSE_CANCEL:
    print 'Closed, no files selected'
dialog.destroy()



### ROUTE/COORDINATES & KML HANDLING ### --------------------------------------------------------

def heading (dlongitude, dlatitude):
    q23 = 0.
    dy=dlongitude
    dx=dlatitude
    if dx < 0.:
        q23 = 180.
    if abs(dx) > 0.:
        h = q23 + 180.*math.atan(dy/dx)/math.pi
    else:
        if dy > 0.:
            h = 90.
        else:
            h = -90.
    h = 90.-h
    if h < 0:
        h = h+360
    return h

def distance_on_unit_sphere(long1, lat1, long2, lat2):

    earth_radius = 6373000  # in m
## http://en.wikipedia.org/wiki/Earth_radius
## http://www.johndcook.com/python_longitude_latitude.html

    # Convert latitude and longitude to 
    # spherical coordinates in radians.
    degrees_to_radians = math.pi/180.0
        
    # phi = 90 - latitude
    phi1 = (90.0 - lat1)*degrees_to_radians
    phi2 = (90.0 - lat2)*degrees_to_radians
        
    # theta = longitude
    theta1 = long1*degrees_to_radians
    theta2 = long2*degrees_to_radians
        
    # Compute spherical distance from spherical coordinates.
        
    # For two locations in spherical coordinates 
    # (1, theta, phi) and (1, theta, phi)
    # cosine( arc length ) = 
    #    sin phi sin phi' cos(theta-theta') + cos phi cos phi'
    # distance = rho * arc length
    
    cos = (math.sin(phi1)*math.sin(phi2)*math.cos(theta1 - theta2) + 
           math.cos(phi1)*math.cos(phi2))
    arc = 0.
    if cos < 1.:
        arc = math.acos( cos )
    else:
        print 'math!!0'
        
    # Remember to multiply arc by the radius of the earth 
    # in your favorite set of units to get length.
    return arc*earth_radius

def make_meter (value, vrange, vhold, zoneprefix, zones, pos, lev, body=True):
    r=100.
    x=pos
    xl=x-r
    xr=x+r
    w=15.
    y0=0.
    yb=-10.
    if body:
        meter_body = '	<path class="Moutline" d="M %d,%d'%(xl,yb) + ' L %d,%d'%(xl,y0) + ' A%d,%d'%(r,r) + ' 0 0,0 %d,%d'%(xr,y0) + ' L %d,%d'%(xr,yb) + ' L %d,%d'%(xl,yb) + '"/>\n'
    else:
        meter_body = ''
        
    meter_bar_hold = ''
    meter_bar = ''
    za=0.
    zone=0
    for z in zones:
        zone = zone + 1
        if z > 0 and z <= ceil(value):
            valueA=za/vrange
            if floor(value) > z:
                valueB=z/vrange
            else:
                valueB=value/vrange
            za = z

            if valueA > valueB:
                tmp = valueB
                valueB = valueA
                valueA = tmp

            vxa  = xl + r*(1.-math.cos(valueA*math.pi))
            vya  = y0 + r*math.sin(valueA*math.pi)
            vxa2 = xl + w + (r-w)*(1.-math.cos(valueA*math.pi))
            vya2 = y0 + (r-w)*math.sin(valueA*math.pi)
            
            vxb  = xl + r*(1.-math.cos(valueB*math.pi))
            vyb  = y0 + r*math.sin(valueB*math.pi)
            vxb2 = xl + w + (r-w)*(1.-math.cos(valueB*math.pi))
            vyb2 = y0 + (r-w)*math.sin(valueB*math.pi)
            
            meter_bar = meter_bar + ' 	<path class="%s%d'%(zoneprefix,zone) + '" d="M %.2f,%.2f'%(vxa,vya) + ' A%.2f,%.2f'%(r,r) + ' 0 0,0 %.2f,%.2f'%(vxb,vyb) + ' L %.2f,%.2f'%(vxb2,vyb2) + ' A%.2f,%.2f'%(r-w,r-w) + ' 0 0,1 %.2f,%.2f'%(vxa2,vya2) + ' L  %.2f,%.2f'%(vxa,vya) + '"/>\n'

            
        if z > value and z <= ceil(vhold):
            valueA=za/vrange
            za = z
            if floor(vhold) > z:
                valueB=z/vrange
            else:
                valueB=vhold/vrange

            if valueA > valueB:
                tmp = valueB
                valueB = valueA
                valueA = tmp

            vxa  = xl + r*(1.-math.cos(valueA*math.pi))
            vya  = y0 + r*math.sin(valueA*math.pi)
            vxa2 = xl + w + (r-w)*(1.-math.cos(valueA*math.pi))
            vya2 = y0 + (r-w)*math.sin(valueA*math.pi)
            
            vxb  = xl + r*(1.-math.cos(valueB*math.pi))
            vyb  = y0 + r*math.sin(valueB*math.pi)
            vxb2 = xl + w + (r-w)*(1.-math.cos(valueB*math.pi))
            vyb2 = y0 + (r-w)*math.sin(valueB*math.pi)
            meter_bar_hold = meter_bar_hold + ' 	<path class="%sHold%d'%(zoneprefix,zone) + '" d="M %.2f,%.2f'%(vxa,vya) + ' A%.2f,%.2f'%(r,r) + ' 0 0,0 %.2f,%.2f'%(vxb,vyb) + ' L %.2f,%.2f'%(vxb2,vyb2) + ' A%.2f,%.2f'%(r-w,r-w) + ' 0 0,1 %.2f,%.2f'%(vxa2,vya2) + ' L  %.2f,%.2f'%(vxa,vya) + '"/>\n' 

    return meter_body + meter_bar_hold + meter_bar


def write_data_file (opts, frame, seconds, toff, kmph, watts, grd, tp):
    global p_slow_peak
    global v_slow_peak
    #                       0    1    2    3  4  5   6        7     8    9     10     11   12
    # track_points.append ((s, lon, lat, ele, g, h, ts, userlap, dist, cad, speed, power, hrm))

    t = seconds - toff
    hh = (int)(t/3600.)
    mm = (int)((t-hh*3600)/60.)
    ss = (t-hh*3600)-mm*60.

    dist = tp[0]/1000.
    ele  = tp[3]
    lap  = tp[7]
    cad  = tp[9]
    bpm  = tp[12]

    if opts.splitlaps:
        f=open(svg_info_file+'L%03d-'%lap+'%05d'%frame+'.svg', 'w')
    else:
        f=open(svg_info_file+'%05d'%frame+'.svg', 'w')

    print 'Display Time of %d, %f s => %02d:%02d:%02d %.0fW ->  Z%d'%(i, seconds, hh,mm,ss, watts, find_zone_i (watts, power_zones_low))


    if (kmph > v_slow_peak):
        v_slow_peak = kmph
    else:
        v_slow_peak = v_slow_peak*0.95 + kmph*0.05

    speedo_meter = make_meter (100., 100., 0., 'MbarZBG', speed_zones_low, 0, 0)\
                   + make_meter (kmph, 100., v_slow_peak, 'MbarZ', speed_zones_low, 0, 0)
    
    if (watts > p_slow_peak):
        p_slow_peak = watts
    else:
        p_slow_peak = p_slow_peak*0.95 + watts*0.05

    if opts.pwr:
        power_meter  = make_meter (10., 10., 0., 'MbarZBG', power_zones_Z, 500, 0)\
                       + make_meter (find_zone (watts, power_zones_low), 10., find_zone (p_slow_peak, power_zones_low), 'MbarZ', power_zones_Z, 500, 0)
    else:
        power_meter = ''


    if opts.hrm and bpm > 0.:
        bpm_display = '	<text class="computerdisplayR" id="AChrm"   y="-50" x="465" transform="scale(1,-1)">%3.0f'%bpm + '</text>\n'\
                      '	<text class="unitdisplay"      id="AChrmU"  y="-50" x="535" transform="scale(1,-1)">bpm</text>\n'
    else:
        bpm_display = ''

    if opts.cad:
        cad_display = '	<text class="computerdisplayR" id="ACcad"       y="-50" x="-30" transform="scale(1,-1)">%3.0f'%cad + '</text>\n'\
                      '	<text class="unitdisplay"      id="ACcadU"      y="-50" x="40" transform="scale(1,-1)">rpm</text>\n'
    else:
        cad_display = ''

    if opts.laps:
        lap_display = '	<text class="computerdisplayR" id="AClap"       y="0" x="140" transform="scale(1,-1)">#%2d'%lap + '</text>\n'
    else:
        lap_display = ''

    if opts.elev:
        ele_display = '	<text class="computerdisplayR" id="ACelevation" y="0" x="270" transform="scale(1,-1)">%4.0f'%ele +' m</text>\n'
    else:
        ele_display = ''

    if opts.grade:
        grade_display = '	<text class="computerdisplayR" id="ACelevation" y="-35" x="270" transform="scale(1,-1)">%4.0f'%grd +' %</text>\n'
    else:
        grade_display = ''




    f.write('<?xml version="1.0"?>\n'
            '<!-- Created by PyZahl for dynamic data blending into race and action video -->\n'
            '\n'
            '<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n'
            '\n'
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1280" height="720" >\n'
            '\n'
            '<defs>\n'
            '<style type="text/css"><![CDATA[\n'
            '   .axes { fill:none;stroke:#333333;stroke-width:1.6 }\n'
            '   .pointlabels { font-size:16px; font-family: Arial; font-style: italic;\n'
            '  	stroke:none; fill:#000000; text-anchor: middle }\n'
            '   .computerdisplayR { font-size:40px; font-style:normal; font-variant:normal; font-weight:normal; font-stretch:normal;\n'
            '	fill:#ff0000; fill-opacity:1; stroke:none; font-family:Arial; text-anchor: right }\n'
            '   .computerdisplayL { font-size:40px; font-style:normal; font-variant:normal; font-weight:normal; font-stretch:normal;\n'
            '	fill:#ff0000; fill-opacity:1; stroke:none; font-family:Arial; text-anchor: left }\n'
            '   .computerdisplayC { font-size:40px; font-style:normal; font-variant:normal; font-weight:normal; font-stretch:normal;\n'
            '	fill:#ff0000; fill-opacity:1; stroke:none; font-family:Arial; text-anchor: center }\n'
            '   .unitdisplay { font-size:22px; font-style:normal; font-variant:normal; font-weight:normal; font-stretch:normal;\n'
            '	fill:#000000; fill-opacity:1; stroke:none; font-family:Arial; text-anchor: left }\n'
            '   .computerbox { fill:#ac9dff; fill-opacity:0.35; fill-rule:evenodd; stroke:none }\n'
            '   .point{ fill:#000000; stroke:white; stroke-width:1 }\n'
            '   .outline{ fill:#ffffdd; stroke:#0077bb; stroke-width:3 }\n'
            '   .Moutline{ fill:#ffffdd;  fill-opacity:0.35; stroke:#0077bb; stroke-width:3 }\n'
            '   .MbarZ1{ fill:#ff00ff; fill-opacity:0.85; stroke:non; }\n'
            '   .MbarZ2{ fill:#6600ff; fill-opacity:0.85; stroke:non; }\n'
            '   .MbarZ3{ fill:#00ccff; fill-opacity:0.85; stroke:non; }\n'
            '   .MbarZ4{ fill:#00ffcc; fill-opacity:0.85; stroke:non; }\n'
            '   .MbarZ5{ fill:#66ff00; fill-opacity:0.85; stroke:non; }\n'
            '   .MbarZ6{ fill:#ffdd55; fill-opacity:0.85; stroke:non; }\n'
            '   .MbarZ7{ fill:#ff0000; fill-opacity:0.85; stroke:non; }\n'
            '   .MbarZ8{ fill:#800080; fill-opacity:0.85; stroke:non; }\n'
            '   .MbarZ9{ fill:#cc00ff; fill-opacity:0.85; stroke:non; }\n'
            '   .MbarZ10{ fill:#dd00ff; fill-opacity:0.85; stroke:non; }\n'
            '   .MbarZ11{ fill:#ee00ff; fill-opacity:0.85; stroke:non; }\n'
            '   .MbarZ12{ fill:#ff00ff; fill-opacity:0.85; stroke:non; }\n'
            '   .MbarZHold1{ fill:#ff00ff; fill-opacity:0.3; stroke:non; }\n'
            '   .MbarZHold2{ fill:#6600ff; fill-opacity:0.3; stroke:non; }\n'
            '   .MbarZHold3{ fill:#00ccff; fill-opacity:0.3; stroke:non; }\n'
            '   .MbarZHold4{ fill:#00ffcc; fill-opacity:0.3; stroke:non; }\n'
            '   .MbarZHold5{ fill:#66ff00; fill-opacity:0.3; stroke:non; }\n'
            '   .MbarZHold6{ fill:#ffdd55; fill-opacity:0.3; stroke:non; }\n'
            '   .MbarZHold7{ fill:#ff0000; fill-opacity:0.3; stroke:non; }\n'
            '   .MbarZHold8{ fill:#800080; fill-opacity:0.3; stroke:non; }\n'
            '   .MbarZHold9{ fill:#cc00ff; fill-opacity:0.3; stroke:non; }\n'
            '   .MbarZHold10{ fill:#dd00ff; fill-opacity:0.3; stroke:non; }\n'
            '   .MbarZHold11{ fill:#ee00ff; fill-opacity:0.3; stroke:non; }\n'
            '   .MbarZHold12{ fill:#ff00ff; fill-opacity:0.3; stroke:non; }\n'
            '   .MbarZBG1{ fill:#ffffff; fill-opacity:0.15; stroke:#cccccc; stroke-width:1.0 }\n'
            '   .MbarZBG2{ fill:#777777; fill-opacity:0.15; stroke:#cccccc; stroke-width:1.0 }\n'
            '   .MbarZBG3{ fill:#ffffff; fill-opacity:0.15; stroke:#cccccc; stroke-width:1.0 }\n'
            '   .MbarZBG4{ fill:#777777; fill-opacity:0.15; stroke:#cccccc; stroke-width:1.0 }\n'
            '   .MbarZBG5{ fill:#ffffff; fill-opacity:0.15; stroke:#cccccc; stroke-width:1.0 }\n'
            '   .MbarZBG6{ fill:#777777; fill-opacity:0.15; stroke:#cccccc; stroke-width:1.0 }\n'
            '   .MbarZBG7{ fill:#ffffff; fill-opacity:0.15; stroke:#cccccc; stroke-width:1.0 }\n'
            '   .MbarZBG8{ fill:#777777; fill-opacity:0.15; stroke:#cccccc; stroke-width:1.0 }\n'
            '   .MbarZBG9{ fill:#ffffff; fill-opacity:0.15; stroke:#cccccc; stroke-width:1.0 }\n'
            '   .MbarZBG10{ fill:#777777; fill-opacity:0.15; stroke:#cccccc; stroke-width:1.0 }\n'
            '   .MbarZBG11{ fill:#ffffff; fill-opacity:0.15; stroke:#cccccc; stroke-width:1.0 }\n'
            '   .MbarZBG12{ fill:#777777; fill-opacity:0.15; stroke:#cccccc; stroke-width:1.0 }\n'
            '   .thinline{ stroke:#770000; stroke-dasharray: 12,4; stroke-width:1.6 }\n'
            '   .thickline{ fill:none; stroke:#ff2222; stroke-width:3.5 }\n'
            '   ]]>\n'
            '</style>\n'
            '</defs>\n'
            '\n'
            '<g transform="matrix(1, 0, 0, -1, 640, 700)">\n'
            '\n'
            '	<rect class="computerbox" id="displaybox" width="1220.0" height="60.0" x="-610.0" y="-10" ry="12.0" rx="12.0" />\n'
            '	<text class="computerdisplayR" id="ACtime"      y="0" x="-550" transform="scale(1,-1)">%2d:%02d:%02d'%(hh,mm,ss) + '</text>\n'
            '	<text class="computerdisplayR" id="ACdist"      y="0" x="-320" transform="scale(1,-1)">%6.2f'%dist + ' km</text>\n'
            + speedo_meter +
            '	<text class="computerdisplayR" id="ACspeed"     y="0"   x="-80" transform="scale(1,-1)">%4.1f'%kmph + ' km/h</text>\n'
            + cad_display
            + lap_display
            + ele_display +
            '\n'
            + grade_display
            + power_meter +
            '	<text class="computerdisplayR" id="ACpower" y="0"   x="450" transform="scale(1,-1)">%3.0f'%watts + ' W</text>\n'
            + bpm_display +
            '         \n'
            '</g>\n'
            '\n'
            '</svg>\n')
    f.close

#            '         y="1029.9216">%.2f'%(tp[0]/1000.)+' km</tspan></text>\n'
#            '         sodipodi:role="line">%.0f'%kmph+' km/h</tspan></text>\n'
#            '         y="1029.9216">%.0f'%tp[3]+' m</tspan></text>\n'
#            '         y="1029.9216">#%.0f'%tp[7]+' %.0f'%tp[3]+' m</tspan></text>\n'
#            '         sodipodi:role="line">%.0f'%watts+' W</tspan></text>\n'
#            '         sodipodi:role="line">%02d:%02d:%02d'%(hh,mm,ss)+'</tspan></text>'

def smooth (section):
	avg = array (section[0])
	n = 1
	for x in section[1:]:
		avg = avg + array (x)
		n = n+1
	avg = avg / n
	return avg.tolist()


def getText(nodelist):
    rc = ""
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            rc = rc + node.data
    return rc

def read_and_calculate_track_gpx (route):
    
    track_points = []

    dom_gpx = parse(route+'.gpx') # parse an XML file by name
#    handleGPX(dom_gpx)

#    print "gpx"
    trk = dom_gpx.getElementsByTagName("trk")[0]
    name = trk.getElementsByTagName("name")[0]
#    print " Name: %s" % getText(name.childNodes)
    trkseg = trk.getElementsByTagName("trkseg")[0]
    points = trkseg.getElementsByTagName("trkpt")

    lap = 1 # auto lap counter
    lapmark = 1
    dp0x = 0.;
    i = 0  # index
    s = 0. # segment length
    dh= 0. # segment climb
    g = 0. # grade
    h = 0. # heading
    t0 = 0.
    
    for point in points:
#        print " trkpt"
#        print "  Lon= %s" % point.getAttribute("lon")
#        print "  Lat= %s" % point.getAttribute("lat")
        p_ele = point.getElementsByTagName("ele")[0]
#        print "  Ele= %s" % getText(p_ele.childNodes)
        p_time = point.getElementsByTagName("time")[0]
#        print "  Time:%s" % getText(p_time.childNodes)

        lon = float(point.getAttribute("lon"))
        lat = float(point.getAttribute("lat"))
        ele = float(getText(p_ele.childNodes))
        time = getText(p_time.childNodes)
        # 2010-04-10T16:50:21.000Z

        t = time.split('T')[1].split(':')
        t[2]=t[2].rstrip('Z')
#        print t
        ts = float(t[0])*3600. + float(t[1])*60. + float(t[2])

#        print ts
        if t0 == 0:
            t0 = ts

        ts = ts-t0

        if ts < -1000:
            ts += 24.*3600.

        ds = 0.
        dh = 0.
        g = 0.
        
        if i > 0 and track_points[i-1][1]-lon <> 0. and track_points[i-1][2]-lat <> 0.:
            dp0 = distance_on_unit_sphere(track_points[0][1], track_points[0][2], lon, lat)
            ds = distance_on_unit_sphere(track_points[i-1][1], track_points[i-1][2], lon, lat)
            if dp0 < 130:
                if dp0 > dp0x:
                    if lapmark == 0:
                        lap = lap + 1
                    lapmark = 1
                else:
                    lapmark = 0
            dp0x = dp0
                
            s = s + ds
            dh = ele - track_points[i-1][3]
            if ds > 1.:
                g = 100.*dh/ds
                h = heading (lat-track_points[i-1][2], lon-track_points[i-1][1])

# not in gpx
        dist=0.
        cad=-1.
        speed=0.
        power=-1.
        hrm=-1.

        track_points.append ((s, lon, lat, ele, g, h, ts, lap, dist, cad, speed, power, hrm))
#        print 'tp[%d'%1 + ', %d]:'%lap +' dist=%f m, %f,%f, ele=%f m, %f, %f%%, %f'%track_points[i] + ', dh: %f'%dh + ', dp0: %f'%dp0x
        print '#%d '%i + '%f s '%ts + '%f '%track_points[i][0] + '%f'%dp0x + ' %d'%lap
        i=i+1

    return track_points


def read_and_calculate_track_tcx (route):
    
    track_points = []

    print "#---- Reading TCX Activities ----"

    dom_tcx = parse(route+'.tcx') # parse an XML file by name
#    handleGPX(dom_tcx)

    Activities = dom_tcx.getElementsByTagName("Activities")[0]
    Activity = Activities.getElementsByTagName("Activity")[0]

#    print " Activities: %s" % getText(Activities.childNodes)
#    print " Activity: %s" % getText(Activity.childNodes)

    lap = 1 # auto lap counter
    lapmark = 1
    dp0x = 0.;
    i = 0  # index
    s = 0. # segment length
    dh= 0. # segment climb
    g = 0. # grade
    h = 0. # heading

    userlap = 0

    t_lap_last=0.;

# data in table form
    fd=open(data_file, 'w')
    fd.write ('# 10--t[s]   10-t[min] lap --s[m] dp0x[m] GPS[m] ele[m]   m/s RPM P[W] BPM  ----i\n')

    i=0
    for Lap in Activities.getElementsByTagName("Lap"):
        t0 = -1.
        userlap = userlap + 1
        lapstart = "N/A"
        t_lap_end_time = t_lap_last;
        lapdist = 0
        lapstart = Lap.getAttribute("StartTime")
        for x in Lap.getElementsByTagName ("DistanceMeters"):
            lapdistance  = float (getText(x.childNodes))
        for x in Lap.getElementsByTagName ("TotalTimeSeconds"):
            laptime = float (getText(x.childNodes))
        print 'Lap %d'%userlap + ' start: ' + lapstart + ' total: %f'%lapdistance
        for Track in Lap.getElementsByTagName("Track"):
            for point in Track.getElementsByTagName("Trackpoint"):
                # 2010-04-10T16:50:21.000Z
                time = getText (point.getElementsByTagName ("Time")[0].childNodes)
                ele  = float (getText(point.getElementsByTagName ("AltitudeMeters")[0].childNodes))
                dist = float (getText(point.getElementsByTagName ("DistanceMeters")[0].childNodes))

                cad=0
                for x in point.getElementsByTagName ("Cadence"):
                    cad  = float (getText(x.childNodes))

                hrm=0 
                for x in point.getElementsByTagName ("HeartRateBpm"):
                    hrm = float (getText (x.getElementsByTagName ("Value")[0].childNodes))

                lat=long=0 
                for x in point.getElementsByTagName ("Position"):
                    lat = float (getText (x.getElementsByTagName ("LatitudeDegrees")[0].childNodes))
                    lon = float (getText (x.getElementsByTagName ("LongitudeDegrees")[0].childNodes))

                speed=0     
                power=0
                for x in point.getElementsByTagName ("Extensions"):
                    for ns3 in x.getElementsByTagName ("ns3:TPX"):
                        for ns3speed in ns3.getElementsByTagName ("ns3:Speed"):
                            speed = float (getText (ns3speed.childNodes))
                        for ns3watts in ns3.getElementsByTagName ("ns3:Watts"):
                            power = float (getText (ns3watts.childNodes))
                    for ns3 in x.getElementsByTagName ("TPX"):
                        for ns3watts in ns3.getElementsByTagName ("Watts"):
                            power = float (getText (ns3watts.childNodes))

                t = time.split('T')[1].split(':')
                t[2]=t[2].rstrip('Z')
                ts = float(t[0])*3600. + float(t[1])*60. + float(t[2])

#                print 'time= ' + t[0] + ':' + t[1] + ':' + t[2]
                
                if t0 < 0.:
                    t0 = ts

                ts = ts-t0 + t_lap_end_time

                if ts < -1000:
                    ts += 24.*3600.

                t_lap_last = ts

                ds = 0.
                dh = 0.
                g = 0.
        
                if i > 0 and track_points[i-1][1]-lon <> 0. and track_points[i-1][2]-lat <> 0.:
                    dp0 = distance_on_unit_sphere(track_points[0][1], track_points[0][2], lon, lat)
                    ds = distance_on_unit_sphere(track_points[i-1][1], track_points[i-1][2], lon, lat)
                    dt = ts - track_points[i-1][0]
                    if dp0 < 130:
                        if dp0 > dp0x:
                            if lapmark == 0:
                                lap = lap + 1
                            lapmark = 1 
                        else:
                            lapmark = 0
                    dp0x = dp0
                    v = ds/dt
                    if speed == 0:
                        speed = v
                            
                    s = s + ds
                    dh = ele - track_points[i-1][3]
                    if ds > 1.:
                        g = 100.*dh/ds
                        h = heading (lat-track_points[i-1][2], lon-track_points[i-1][1])
                                
                track_points.append ((s, lon, lat, ele, g, h, ts, userlap, dist, cad, speed, power, hrm))
#                print 'tp[%d'%1 + ', %d]:'%lap +' dist=%f m, %f,%f, ele=%f m, %f, %f%%, %f'%track_points[i] + ', dh: %f'%dh + ', dp0: %f'%dp0x
                print '#%d '%i + time + ' %f s '%ts + ' %.1f min '%(ts/60.) + '%f m '%track_points[i][0] + ' dpx0 %f'%dp0x + ' Lap %d'%userlap + ' (dist) %f m'%dist + ' %f km/h'%speed + ' %f RPM'%cad + ' %f W'%power + ' %f BPM'%hrm
                fd.write ('%10.0f'%ts + ' %10.2f '%(ts/60.) + ' %2d'%userlap + ' %7.1f '%track_points[i][0] + ' %6.1f'%dp0x + ' %6.1f'%dist + ' %6.1f'%ele + ' %5.1f'%speed + ' %3.0f'%cad + ' %4.0f'%power + ' %3.0f'%hrm + ' %6.0d'%i + '\n')
                i=i+1

    return track_points

def read_and_calculate_track_kml (route):
    
    track_points = []

    f=open (route+'.kml', "r")
    line = f.readline()
    while line.find('<coordinates>') < 0:
        line = f.readline()

#    print line

    line = f.readline()
    coord_sets = line.split(' ')
    f.close ()

    i = 0  # index
    s = 0. # segment length
    dh= 0. # segment climb
    g = 0. # grade
    h = 0. # heading

    for coord in coord_sets:
        if coord.find('</coordinates>') < 0:
            p = coord.split(',')
            if len (p) <> 3:
                print 'stop reading coords, invalid pair/end.'
                break
            lon = float(p[0])
            lat = float(p[1])
            ele = float(p[2])
            ds = 0.
            dh = 0.
            g = 0.
            if i > 0 and track_points[i-1][1]-lon <> 0. and track_points[i-1][2]-lat <> 0.:
                ds = distance_on_unit_sphere(track_points[i-1][1], track_points[i-1][2], lon, lat)
                s = s + ds
                dh = ele - track_points[i-1][3]
                if ds > 1.:
                    g = 100.*dh/ds
                    h = heading (lat-track_points[i-1][2], lon-track_points[i-1][1])

# not supported here:
            ts = lap = dist = cad = speed = hrm = -1.
            power = -1.

            track_points.append ((s, lon, lat, ele, g, h, ts, lap, dist, cad, speed, power, hrm))
            print 'tp[%d]:'%i +' dist=%f m, %f,%f, ele=%f m, %f, %f, TCX: %f m, %f rpm, %f km/h, %f W, %f BPM'%track_points[i] + '%' + ', dh: %f'%dh
            i=i+1

    return track_points


def interpolate_position(distance, route, track_points):
    k=1
    i=k+1
    i1=i2=k
    tpv=track_points[0]
#    print 'looking for %f m'%distance
    for tp in track_points[k+1:]:
        if tp[0] >= distance:
#            print 'tp[%d]:'%i + ' dist=%f m, %f,%f, ele=%f m, g=%f, h=%f'%tp
            i2=i
            i1=i-1
            p1 = array(tpv)
            p2 = array(tp)
	    p1s = smooth(track_points[i1-k:i1+k])
	    p2s = smooth(track_points[i2-k:i2+k])
	    p1[3]=p1s[3]
	    p1[4]=p1s[4]
	    p1[5]=p1s[5]
	    p2[3]=p2s[3]
	    p2[4]=p2s[4]
	    p2[5]=p2s[5]
	    if abs(tp[0]-tpv[0]) > 0:
		    p =  p1+(p2-p1)*(1.-(tp[0]-distance)/(tp[0]-tpv[0]))
		    return p.tolist()
	    return tp
        tpv = tp
        i=i+1

def interpolate_to_time(time, route, track_points):
    k=1
    i=k+1
    i1=i2=k
    tpv=track_points[0]
#    print 'looking for %f m'%distance
    for tp in track_points[k+1:]:
        if tp[6] >= time:
#            print 'tp[%d]:'%i + ' dist=%f m, %f,%f, ele=%f m, g=%f%%, h=%f, t=%f s, lap=%d'%tp
            i2=i
            i1=i-1
            p1 = array(tpv)
            p2 = array(tp)
	    p1s = smooth(track_points[i1-k:i1+k])
	    p2s = smooth(track_points[i2-k:i2+k])
	    p1[3]=p1s[3]
	    p1[4]=p1s[4]
	    p1[5]=p1s[5]
	    p2[3]=p2s[3]
	    p2[4]=p2s[4]
	    p2[5]=p2s[5]
	    if abs(tp[0]-tpv[0]) > 0:
		    p =  p1+(p2-p1)*(1.-(tp[6]-time)/(tp[6]-tpv[6]))
		    return p.tolist()
	    return tp
        tpv = tp
        i=i+1

def exponentialFilter(curVal, prevVal, alpha):
    return prevVal + alpha * (curVal - prevVal);


## MAIN ##

print "--READING TRACK-- >>" + route + "<<"

xml_type = track[-3:]
print 'Track type: ' + xml_type
if xml_type == 'tcx':
    track_points = read_and_calculate_track_tcx (route)
else:
    if xml_type == 'gpx':
        track_points = read_and_calculate_track_gpx (route)
    else:
        if xml_type == 'kml':
            track_points = read_and_calculate_track_kml (route)
        else:
            print 'Sorry -- not yet supported GPS/XML track file type -- please use gpx, tcx or kml.'
            exit

i = len (track_points)
print 'Track has %d'%i + ' points. Last entry is:'
i = i-1
print 'tp[%d]:'%i +' dist=%f m, %f,%f, ele=%f m, h=%f deg, %f%%, time=%f s, lap=%d, TCX: %f m, %f rpm, %f km/h, %f W, %f BPM'%track_points[i]

print "--START GENERATING SVG SEQUENCE--"

time0 = 0 #Time offset for display
ti = 0. #2417.   #33.*60.+58.
dt = 0.5
s  = interpolate_to_time(ti-dt, route, track_points)[0]
h  = interpolate_to_time(ti-dt, route, track_points)[3]

km2mph = 0.62137119
mps2mph = km2mph*3.6
c0=13.244   # offset in Watts
c1=2.0982*mps2mph   # linear term x mph  (converted to m/s coef.)
c2=0.53274*mps2mph*mps2mph  # quadratic x mph^2  (converted to m/s coef.)

# Mass of moving object (bike + rider)
m=66+6+8

# number of time steps
n=2.5*60*60/dt

opts = options()\
       .add('svgname', label="SVG file prefix", value="data_")\
       .add('splitlaps', label="Split by Laps", value= False)\
       .add('start', label="Start (s)", value=ti, style="integer(lower=0)")\
       .add('time0', label="T0 (s)", value=time0, style="integer(lower=0)")\
       .add('length', label="Length (s)", value=n*dt, style="integer(lower=1)")\
       .add('fps', label="Frames/s", value=2, style="integer(lower=1)")\
       .add('mass', label="Mass (kg)", value=m)\
       .add('power', label="Power", value= True)\
       .add('calcpower', label="Calc.Power", value= True)\
       .add('autopower', label="Auto Calc.Power", value= True)\
       .add('laps', label="Laps", value= False)\
       .add('hrm', label="HRM", value= False)\
       .add('cad', label="CAD", value= False)\
       .add('pwr', label="Power", value= True)\
       .add('elev', label="Elevation", value= True)\
       .add('grade', label="Gradient", value= True)

create_gtk_dialog(opts).run()
print ("svgname=\t\t" + str(opts.svgname))    
print ("start=\t\t" + str(opts.start))    
print ("length=\t"+ str(opts.length))
print ("fps=\t"+ str(opts.fps))
print ("mass=\t"+ str(opts.mass))
print ("power=\t"+ str(opts.power))
print ("laps=\t"+ str(opts.laps))
print ("elev=\t"+ str(opts.elev))
print ("grade=\t"+ str(opts.grade))

svg_info_file = opts.svgname
ti = opts.start
time0 = opts.time0
dt = 1./opts.fps
n = int(opts.length/dt)
m = opts.mass
frame = 0
ll = 0

vprev = 0
elev = h
elevprev = h

grd = 0


for i in range(n):
    tp = interpolate_to_time(ti+dt*i, route, track_points)
    ds = tp[0]-s
    v = exponentialFilter(ds/dt, vprev, 0.25)
    vprev = v
    elev = exponentialFilter(tp[3], elevprev, 0.01)
    elevprev = elev
    if ds != 0:
        grd = ((elev-h)/ds)*100
    pwr =  c0 + (c1  + c2*v)*v + (elev-h)*9.81*m/dt;
    if pwr < 0:
        pwr = 0

    if opts.calcpower:
        # computed power
        write_data_file (opts, frame, dt*i, time0, v*3.6, pwr, grd, tp)
    else:
        # real power
        # print dt*i, v*3.6, 'km/h', pwr, 'W', tp[11], 'W-real, ', tp[8], tp[9], tp[10]
        if opts.autopower:
            if tp[11] < 0:
                write_data_file (opts, frame, dt*i, time0, v*3.6, pwr, grd, tp)
        else:
            write_data_file (opts, frame, dt*i, time0, v*3.6, tp[11], grd, tp)

    frame = frame+1
    lap  = tp[7]
    if opts.splitlaps and ll < lap:
        frame = 0
        ll = lap

    s = tp[0]
    h = elev

print ("Done.")

