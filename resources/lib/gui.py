# *  This Program is free software; you can redistribute it and/or modify
# *  it under the terms of the GNU General Public License as published by
# *  the Free Software Foundation; either version 2, or (at your option)
# *  any later version.
# *
# *  This Program is distributed in the hope that it will be useful,
# *  but WITHOUT ANY WARRANTY; without even the implied warranty of
# *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *  GNU General Public License for more details.
# *
# *  You should have received a copy of the GNU General Public License
# *  along with Kodi; see the file COPYING.  If not, write to
# *  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *  http://www.gnu.org/copyleft/gpl.html

import random, copy, threading
import xbmcgui, xbmcaddon
import EXIFvfs
from iptcinfovfs import IPTCInfo
from XMPvfs import XMP_Tags
from xml.dom.minidom import parse
from utils import *
import json

ADDON    = sys.modules[ '__main__' ].ADDON
ADDONID  = sys.modules[ '__main__' ].ADDONID
CWD      = sys.modules[ '__main__' ].CWD
SKINDIR  = xbmc.getSkinDir().decode('utf-8')

# images types that can contain exif/iptc data
EXIF_TYPES  = ('.jpg', '.jpeg', '.tif', '.tiff')

# random effect list to choose from
EFFECTLIST = ["('conditional', 'effect=zoom start=100 end=400 center=auto time=%i condition=true'),",
              "('conditional', 'effect=slide start=1280,0 end=-1280,0 time=%i condition=true'), ('conditional', 'effect=zoom start=%i end=%i center=auto time=%i condition=true')",
              "('conditional', 'effect=slide start=-1280,0 end=1280,0 time=%i condition=true'), ('conditional', 'effect=zoom start=%i end=%i center=auto time=%i condition=true')",
              "('conditional', 'effect=slide start=0,720 end=0,-720 time=%i condition=true'), ('conditional', 'effect=zoom start=%i end=%i center=auto time=%i condition=true')",
              "('conditional', 'effect=slide start=0,-720 end=0,720 time=%i condition=true'), ('conditional', 'effect=zoom start=%i end=%i center=auto time=%i condition=true')",
              "('conditional', 'effect=slide start=1280,720 end=-1280,-720 time=%i condition=true'), ('conditional', 'effect=zoom start=%i end=%i center=auto time=%i condition=true')",
              "('conditional', 'effect=slide start=-1280,720 end=1280,-720 time=%i condition=true'), ('conditional', 'effect=zoom start=%i end=%i center=auto time=%i condition=true')",
              "('conditional', 'effect=slide start=1280,-720 end=-1280,720 time=%i condition=true'), ('conditional', 'effect=zoom start=%i end=%i center=auto time=%i condition=true')",
              "('conditional', 'effect=slide start=-1280,-720 end=1280,720 time=%i condition=true'), ('conditional', 'effect=zoom start=%i end=%i center=auto time=%i condition=true')"]

# get local dateformat to localize the exif date tag
DATEFORMAT = xbmc.getRegion('dateshort')

class Screensaver(xbmcgui.WindowXMLDialog):
    def __init__( self, *args, **kwargs ):
        pass

    def onInit(self):
        # load constants
        self._get_vars()
        # get addon settings
        self._get_settings()
        # settings for umsa
        if self.slideshow_umsa == 'true':
            self._set_umsa()
        # get the effectslowdown value from the current skin
        effectslowdown = self._get_animspeed()
        # use default if we couldn't find the effectslowdown value
        if not effectslowdown:
            effectslowdown = 1
        # calculate the animation time
        speedup = 1 / float(effectslowdown)
        self.adj_time = int(101000 * speedup)
        # get the images
        self._get_items()
        if self.slideshow_type == '2' and self.slideshow_random == 'false' and self.slideshow_resume == 'true':
            self._get_offset()
        if self.items:
            # hide startup splash
            self._set_prop('Splash', 'hide')
            # start slideshow
            self._start_show(copy.deepcopy(self.items))

    def _get_vars(self):
        # get the screensaver window id
        self.winid    = xbmcgui.Window(xbmcgui.getCurrentWindowDialogId())
        # init the monitor class to catch onscreensaverdeactivated calls
        self.Monitor  = MyMonitor(action = self._exit)
        self.stop     = False
        self.startup  = True
        self.offset   = 0

    def _get_settings(self):
        # read addon settings
        self.slideshow_type   = ADDON.getSetting('type')
        self.slideshow_path   = ADDON.getSetting('path')
        self.slideshow_effect = ADDON.getSetting('effect')
        self.slideshow_time   = int(ADDON.getSetting('time'))
        self.slideshow_umsa   = ADDON.getSetting('umsa')
        # convert float to hex value usable by the skin
        self.slideshow_dim    = hex(int('%.0f' % (float(100 - int(ADDON.getSetting('level'))) * 2.55)))[2:] + 'ffffff'
        self.slideshow_random = ADDON.getSetting('random')
        self.slideshow_resume = ADDON.getSetting('resume')
        self.slideshow_scale  = ADDON.getSetting('scale')
        self.slideshow_name   = ADDON.getSetting('label')
        self.slideshow_date   = ADDON.getSetting('date')
        self.slideshow_iptc   = ADDON.getSetting('iptc')
        self.slideshow_music  = ADDON.getSetting('music')
        self.slideshow_bg     = ADDON.getSetting('background')
        # select which image controls from the xml we are going to use
        if self.slideshow_scale == 'false':
            self.image1 = self.getControl(1)
            self.image2 = self.getControl(2)
            self.getControl(3).setVisible(False)
            self.getControl(4).setVisible(False)
            if self.slideshow_bg == 'true':
                self.image3 = self.getControl(5)
                self.image4 = self.getControl(6)
        else:
            self.image1 = self.getControl(3)
            self.image2 = self.getControl(4)
            self.getControl(1).setVisible(False)
            self.getControl(2).setVisible(False)
            self.getControl(5).setVisible(False)
            self.getControl(6).setVisible(False)
        if self.slideshow_name == '0':
            self.getControl(99).setVisible(False)
        else:
            self.namelabel = self.getControl(99)
        self.datelabel = self.getControl(100)
        self.textbox = self.getControl(101)
        # set the dim property
        self._set_prop('Dim', self.slideshow_dim)
        # show music info during slideshow if enabled
        if self.slideshow_music == 'true':
            self._set_prop('Music', 'show')
        # show background if enabled
        if self.slideshow_bg == 'true':
            self._set_prop('Background', 'show')

    def _set_umsa(self):
        
        # for usage in combination with script.umame.mame.surfer
        #
        # TODO:
        #
        # - cool would be to fade out and in so the background can be seen
        # - also cool: in wall mode make one position a video
        # - even more cool: make screensaver in umame
        #  
        # - get all folders from progetto path
        #   - artwork: artworkpreview, cabinets, covers, cpanel, flyers, marquees
        #   - snap: snap, titles
        #   - others: cabdevs, devices, icons, manuals, pcb, videosnaps
        #
        # - count evspace and ehspace together / 2 and then calc again with new space
        #   see 4 rows
        
        # settings
        self.umsa_musicinfo = ADDON.getSetting('umsa_musicinfo')
        self.umsa_random    = ADDON.getSetting('umsa_random')
        self.umsa_time      = int(ADDON.getSetting('umsa_time'))
        self.umsa_type      = int(ADDON.getSetting('umsa_type'))
        rows                = int(ADDON.getSetting('umsa_rows'))
        rows_b              = int(ADDON.getSetting('umsa_rows_b'))
        titles              = ADDON.getSetting('umsa_titles')
        umsa_free           = int(ADDON.getSetting('umsa_free'))
        # will be extended later according to type
        self.slideshow_path = 'multipath://'
        
        self.umsa_info = False
        if ADDON.getSetting('umsa_info') == 'true':
            self.umsa_info = True
            
        pil = False
        if ADDON.getSetting('umsa_pil') == "true":
            pil = True
            
        # import modules from script.umsa.mame.surfer
        sys.path.append(
            xbmc.translatePath(
                'special://home/addons/script.umsa.mame.surfer/resources/lib'
                )
            )
        # image check init
        from utilmod2 import Check
        self.umsa_util = Check( pil )
        # db init        
        from dbmod import DBMod
        self.umsa_db = DBMod(
            xbmc.translatePath(
                'special://profile/addon_data/script.umsa.mame.surfer/'
            )
        )
        
        # get skin controls for info label
        # TODO create info controls here when umsa_info
        # so can be deleted from skin
        self.umsa_label = self.getControl(102)
        
        # get settings from umsa addon for paths
        umsa_addon = xbmcaddon.Addon('script.umsa.mame.surfer')
        self.umsa_progetto_path = umsa_addon.getSetting('progetto')
        aratio = umsa_addon.getSetting('aspectratio')
        ar_norm = 1.7777 # 16:9
        ar_x = 1.7777
        
        # set correct aspect ratio for snapshots (bottom left picture)
        # for everything which is not 16:9
        if aratio == "16:10":
            ar_x = 1.6
        elif aratio == "5:4":
            ar_x = 1.25
        elif aratio == "4:3":
            ar_x = 1.3333
        
        # correct aspect ratio for snap in bottom left position
        _4to3 = self.getControl(104).getWidth()
        _3to4 = self.getControl(106).getWidth()
        self.getControl(104).setWidth(int(_4to3 /ar_x*ar_norm)) # 4:3
        self.getControl(106).setWidth(int(_3to4 *ar_norm/ar_x)) # 3:4
        
        # type random = set standard or wall
        if self.umsa_type == 2:
            self.umsa_type = random.randint(0,1)
        
        # type wall
        if self.umsa_type == 1:
            # create multipath
            spath = ["snap"]
            if titles == "Both":
                spath.append("titles")
            elif titles == "Titles":
                spath = ["titles"]
            for i in spath:
                self.slideshow_path = self.slideshow_path + os.path.join(
                        self.umsa_progetto_path, i
                    ).replace( '/' , '%2f' ) + '%2f/'
            
            # set view time from umsa wall time option
            self.slideshow_time = self.umsa_time
            
            # generate image and position list
            # TODO: make vars from spacing and other numbers
            x_space = 20
            y_space = 10
            x_max   = 1280
            y_max   = 660
            
            # how many rows
            if rows < rows_b:
                rows = random.randint( rows , rows_b )
            else:
                rows = random.randint( rows_b , rows )
            # width
            self.umsa_width = ( x_max - ( rows + 1 ) * x_space ) / rows
            ehspace = ( x_max - self.umsa_width * rows ) / ( rows + 1 )
            # height
            self.umsa_height = int( self.umsa_width / 1.3333 / ar_norm * ar_x )
            # TODO: check spacing on big screen
            # idea is that info at the bottom is always visible
            cols = ( y_max - 20) / self.umsa_height
            evspace = ( y_max - self.umsa_height * cols ) / ( cols + 1 )
            # calculate width and x for vertical images
            self.umsa_vert_width = int(
                self.umsa_height / 1.3333 * ar_norm / ar_x
            )
            self.umsa_vert_x = int(
                ( self.umsa_width - self.umsa_vert_width ) / 2 )
            # create lists
            self.umsa_wallpics = rows * cols
            self.umsa_wallpos = range( self.umsa_wallpics )
            # generate image list
            x = x_space
            y = y_space
            self.umsa_wall = []
            for i in range(cols):
                for j in range(rows):
                    self.umsa_wall.append(
                        xbmcgui.ControlImage(
                            x,
                            y,
                            self.umsa_width,
                            self.umsa_height,
                            ''
                        )
                    )
                    x += self.umsa_width + x_space
                y += self.umsa_height + evspace
                x = x_space
                
            # add images to window
            for i in self.umsa_wall:
                self.addControl(i)
            # shuffle position list
            random.shuffle(self.umsa_wallpos)
            # how many free
            if umsa_free == 0:
                self.umsa_freelist = 0
            else:
                self.umsa_free = (
                    self.umsa_wallpics
                    - ( self.umsa_wallpics * umsa_free / 100 )
                )
                #print "HOW MANY FREE: %s" % (self.umsa_free)
                self.umsa_freelist = []
        # type standard
        else:
            # multipath for progetto artwork
            for i in [
                "artpreview",
                "cabinets",
                "covers",
                "cpanel",
                "flyers",
                "marquees"
            ]:
                self.slideshow_path = self.slideshow_path + os.path.join(
                    self.umsa_progetto_path, i
                ).replace( '/' , '%2f' ) + '%2f/'
            # TODO remove before release
            self.slideshow_path = self.slideshow_path + '%2fmedia%2fgames%2fmame%2fextras%2fprojectmess%2f/'
            
        # read last games shown by screensaver
        self.lastgames = []
        try:
            fobj = None
            fobj = open(xbmc.translatePath(
                'special://profile/addon_data/script.umsa.mame.surfer/lastsaver.txt'
                ), 'r'
            )
            if fobj:
                for line in fobj:
                   self.lastgames.append(line.strip())
        except:
            pass
        if len(self.lastgames) != 50:
            while len(self.lastgames) < 50:
                self.lastgames.insert( 0 , '' )
                
        return
    
    def _start_show(self, items):
        # we need to start the update thread after the deep copy of self.items finishes
        thread = img_update(data=self._get_items)
        thread.start()
        # start with image 1
        cur_img = self.image1
        order = [1,2]
        # loop until onScreensaverDeactivated is called
        while (not self.Monitor.abortRequested()) and (not self.stop):
            # keep track of image position, needed to save the offset
            self.position = self.offset
            # iterate through all the images
            for img in items[self.offset:]:
                # cache file may be outdated
                if self.slideshow_type == '2' and not xbmcvfs.exists(img[0]):
                    continue
                # add image to gui
                # only when not in umsa mode or when umsa type is standard
                if self.umsa_type == 0 or self.slideshow_umsa == 'false':
                    cur_img.setImage(img[0],False)
                # otherwise wall mode: goto next image when not valid
                elif not self.umsa_util.check_snapshot(img[0]):
                    continue
                # add background image to gui
                if self.slideshow_scale == 'false' and self.slideshow_bg == 'true':
                    if order[0] == 1:
                        self.image3.setImage(img[0],False)
                    else:
                        self.image4.setImage(img[0],False)
                # give xbmc some time to load the image
                if not self.startup:
                    xbmc.sleep(1000)
                else:
                    self.startup = False
                # get exif and iptc tags if enabled in settings and we have an image that can contain this data
                datetime = ''
                title = ''
                description = ''
                keywords = ''
                exif = False
                iptc_ti = False
                iptc_de = False
                iptc_ke = False
                if self.slideshow_type == '2' and ((self.slideshow_date == 'true') or (self.slideshow_iptc == 'true')) and (os.path.splitext(img[0])[1].lower() in EXIF_TYPES):
                    imgfile = xbmcvfs.File(img[0])
                    # get exif date
                    if self.slideshow_date == 'true':
                        try:
                            exiftags = EXIFvfs.process_file(imgfile, details=False, stop_tag='DateTimeOriginal')
                            if exiftags.has_key('EXIF DateTimeOriginal'):
                                datetime = str(exiftags['EXIF DateTimeOriginal']).decode('utf-8')
                                # sometimes exif date returns useless data, probably no date set on camera
                                if datetime == '0000:00:00 00:00:00':
                                    datetime = ''
                                else:
                                    try:
                                        # localize the date format
                                        date = datetime[:10].split(':')
                                        time = datetime[10:]
                                        if DATEFORMAT[1] == 'm':
                                            datetime = date[1] + '-' + date[2] + '-' + date[0] + '  ' + time
                                        elif DATEFORMAT[1] == 'd':
                                            datetime = date[2] + '-' + date[1] + '-' + date[0] + '  ' + time
                                        else:
                                            datetime = date[0] + '-' + date[1] + '-' + date[2] + '  ' + time
                                    except:
                                        pass
                                    exif = True
                        except:
                            pass
                    # get iptc title, description and keywords
                    if self.slideshow_iptc == 'true':
                        try:
                            iptc = IPTCInfo(imgfile)
                            iptctags = iptc.data
                            if iptctags.has_key(105):
                                title = iptctags[105].decode('utf-8')
                                iptc_ti = True
                            if iptctags.has_key(120):
                                description = iptctags[120].decode('utf-8')
                                iptc_de = True
                            if iptctags.has_key(25):
                                keywords = ', '.join(iptctags[25]).decode('utf-8')
                                iptc_ke = True
                        except:
                            pass
                        if (not iptc_ti or not iptc_de or not iptc_ke):
                            try:
                                tags = XMP_Tags().get_xmp(img[0]) # passing the imgfile object does not work for some reason
                                if (not iptc_ti) and tags.has_key('dc:title'):
                                    title = tags['dc:title']
                                    iptc_ti = True
                                if (not iptc_de) and tags.has_key('dc:description'):
                                    description = tags['dc:description']
                                    iptc_de = True
                                if (not iptc_ke) and tags.has_key('dc:subject'):
                                    keywords = tags['dc:subject'].replace('||',', ')
                                    iptc_ke = True
                            except:
                                pass
                    imgfile.close()
                # display exif date if we have one
                if exif:
                    self.datelabel.setLabel('[I]' + datetime + '[/I]')
                    self.datelabel.setVisible(True)
                else:
                    self.datelabel.setVisible(False)
                # display iptc data if we have any
                if iptc_ti or iptc_de or iptc_ke:
                    self.textbox.setText(
                        '[CR]'.join([title, keywords] if title == description
                                    else [title, description, keywords]))
                    self.textbox.setVisible(True)
                else:
                    self.textbox.setVisible(False)
                # get the file or foldername if enabled in settings
                if self.slideshow_name != '0':
                    if self.slideshow_name == '1':
                        if self.slideshow_type == '2':
                            NAME, EXT = os.path.splitext(os.path.basename(img[0]))
                        else:
                            NAME = img[1]
                    elif self.slideshow_name == '2':
                        ROOT, NAME = os.path.split(os.path.dirname(img[0]))
                    elif self.slideshow_name == '3':
                        if self.slideshow_type == '2':
                            ROOT, FOLDER = os.path.split(os.path.dirname(img[0]))
                            FILE, EXT = os.path.splitext(os.path.basename(img[0]))
                            NAME = FOLDER + ' / ' + FILE
                        else:
                            ROOT, FOLDER = os.path.split(os.path.dirname(img[0]))
                            NAME = FOLDER + ' / ' + img[1]
                    self.namelabel.setLabel(NAME)
                    
                # umsa slideshow actions
                if self.slideshow_umsa == 'true':
                    
                    # split image path and filename
                    FILENAME, EXT = os.path.splitext(os.path.basename(img[0]))
                    ROOT, DIRNAME = os.path.split(os.path.dirname(img[0]))
                    
                    # get infos from db                    
                    name, swl, info, systempic, snapshot, snaporientation = self.umsa_db.get_info_by_filename(
                        FILENAME,
                        DIRNAME,
                        self.umsa_progetto_path,
                        xbmc.translatePath(
                            'special://home/addons/script.umsa.mame.surfer/resources/skins/Default/media/'
                        )
                    )
                    
                    # remember last one, so we can save the last games for umsa
                    if swl:
                        self.lastgames.append( "%s,%s" % (FILENAME, swl))
                        del self.lastgames[0]
                        
                    if self.umsa_info:
                        # set info into label
                        # TODO: split shown info into 2 labels for alignment
                        self.umsa_label.setLabel(
                            '[B]' + name + '[/B][CR]' + info
                        )
                        # show system picture
                        if systempic:
                            self.getControl(105).setImage( systempic , False )
                        else:
                            self.getControl(105).setImage( '' )
                        # if snapshot and not wall mode and image is ok
                        if ( snapshot
                             and self.umsa_type == 0
                             and self.umsa_util.check_snapshot(snapshot)
                            ):
                            if snaporientation == 'horizontal':
                                snapctrl = 104
                                self.getControl(106).setImage('')
                                self.getControl(107).setImage('')
                            elif snaporientation == 'vertical':
                                snapctrl = 106
                                self.getControl(104).setImage('')
                                self.getControl(107).setImage('')
                            elif snaporientation == 'keep':
                                snapctrl = 107
                                self.getControl(106).setImage('')
                                self.getControl(104).setImage('')
                            self.getControl(snapctrl).setImage( snapshot, False )
                        # no snapshot = clear all 3 snap views
                        else:
                            self.getControl(104).setImage('')
                            self.getControl(106).setImage('')
                            self.getControl(107).setImage('')
                        
                    # type = wall
                    if self.umsa_type == 1:
                        # refill position list when empty
                        if len(self.umsa_wallpos) == 0:
                            self.umsa_wallpos = range(self.umsa_wallpics)
                            random.shuffle(self.umsa_wallpos)
                            # dont let the last entry in list
                            # be the last position choosen
                            while self.umsa_wallpos[-1] == self.lastpos:
                                random.shuffle(self.umsa_wallpos)
                        # pop new position from list
                        self.lastpos = self.umsa_wallpos.pop()
                        # delete one of the last pics
                        if self.umsa_freelist != 0:
                            self.umsa_freelist.append(self.lastpos)
                            # print "IMAGELIST:"
                            # print self.umsa_wallpos
                            # print "FREELIST:"
                            # print self.umsa_freelist
                            if len(self.umsa_freelist) == self.umsa_free:
                                tofree = self.umsa_freelist.pop(
                                    random.randint(
                                        0 , len( self.umsa_freelist ) / 2
                                    )
                                )
                                # print "TO MAKE FREE: %s" % (tofree)
                                # insert actual to be cleaned image pos
                                # to umsa_wallpos
                                self.umsa_wallpos.insert( 0 , tofree )
                                # make image empty
                                self.removeControl( self.umsa_wall[tofree] )
                                self.umsa_wall[tofree].setImage('')
                                self.addControl( self.umsa_wall[tofree] )
                        # check if image is horizontal, vertical
                        # or aspect ratio must be keeped
                        # get image position
                        x , y = self.umsa_wall[self.lastpos].getPosition()
                        # width not standard =
                        # image was vertical > correct x position
                        if self.umsa_wall[self.lastpos].getWidth() != self.umsa_width:
                            x = x - self.umsa_vert_x
                        # remove image control
                        self.removeControl(self.umsa_wall[self.lastpos])
                        # create new image control for horz, vert or ar=keep
                        if snaporientation == 'horizontal':
                            self.umsa_wall[self.lastpos] = xbmcgui.ControlImage(
                                x,
                                y,
                                self.umsa_width,
                                self.umsa_height,
                                ''
                            )
                        elif snaporientation == 'vertical':
                            self.umsa_wall[self.lastpos] = xbmcgui.ControlImage(
                                x + self.umsa_vert_x,
                                y,
                                self.umsa_vert_width,
                                self.umsa_height,
                                ''
                            )
                        elif snaporientation == 'keep':
                            self.umsa_wall[self.lastpos] = xbmcgui.ControlImage(
                                x,
                                y,
                                self.umsa_width,
                                self.umsa_height,
                                '',
                                2
                            )
                        # set image
                        self.umsa_wall[self.lastpos].setImage( img[0] , False )
                        # add new image control
                        self.addControl( self.umsa_wall[self.lastpos] )
                        
                # set animations
                if self.slideshow_effect == '0':
                    # add slide anim
                    self._set_prop('Slide%d' % order[0], '0')
                    self._set_prop('Slide%d' % order[1], '1')
                else:
                    # add random slide/zoom anim
                    if self.slideshow_effect == '2':
                        # add random slide/zoom anim
                        self._anim(cur_img)
                    # add fade anim, used for both fade and slide/zoom anim
                    self._set_prop('Fade%d' % order[0], '0')
                    self._set_prop('Fade%d' % order[1], '1')
                # add fade anim to background images
                if self.slideshow_bg == 'true':
                    self._set_prop('Fade1%d' % order[0], '0')
                    self._set_prop('Fade1%d' % order[1], '1')
                # define next image
                if cur_img == self.image1:
                    cur_img = self.image2
                    order = [2,1]
                else:
                    cur_img = self.image1
                    order = [1,2]
                # slideshow time in secs (we already slept for 1 second)
                count = self.slideshow_time - 1
                # display the image for the specified amount of time
                while (not self.Monitor.abortRequested()) and (not self.stop) and count > 0:
                    count -= 1
                    xbmc.sleep(1000)
                # break out of the for loop if onScreensaverDeactivated is called
                if  self.stop or self.Monitor.abortRequested():
                    break
                self.position += 1
            self.offset = 0
            items = copy.deepcopy(self.items)

    def _get_items(self, update=False):
        self.slideshow_type   = ADDON.getSetting('type')
        log('slideshow type: %s' % self.slideshow_type)
	    # check if we have an image folder, else fallback to video fanart
        if self.slideshow_type == '2':
            hexfile = checksum(self.slideshow_path) # check if path has changed, so we can create a new cache at startup
            log('image path: %s' % self.slideshow_path)
            log('update: %s' % update)
            if (not xbmcvfs.exists(CACHEFILE % hexfile)) or update: # create a new cache if no cache exits or during the background scan
                log('create cache')
                create_cache(self.slideshow_path, hexfile)
            self.items = self._read_cache(hexfile)
            log('items: %s' % len(self.items))
            if not self.items:
                self.slideshow_type = '0'
                # delete empty cache file
                if xbmcvfs.exists(CACHEFILE % hexfile):
                    xbmcvfs.delete(CACHEFILE % hexfile)
	    # video fanart
        if self.slideshow_type == '0':
            methods = [('VideoLibrary.GetMovies', 'movies'), ('VideoLibrary.GetTVShows', 'tvshows')]
	    # music fanart
        elif self.slideshow_type == '1':
            methods = [('AudioLibrary.GetArtists', 'artists')]
        # query the db
        if not self.slideshow_type == '2':
            self.items = []
            for method in methods:
                json_query = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "' + method[0] + '", "params": {"properties": ["fanart"]}, "id": 1}')
                json_query = unicode(json_query, 'utf-8', errors='ignore')
                json_response = json.loads(json_query)
                if json_response.has_key('result') and json_response['result'] != None and json_response['result'].has_key(method[1]):
                    for item in json_response['result'][method[1]]:
                        if item['fanart']:
                            self.items.append([item['fanart'], item['label']])
        # randomize
        if self.slideshow_random == 'true':
            random.seed()
            random.shuffle(self.items, random.random)

    def _get_offset(self):
        try:
            offset = xbmcvfs.File(RESUMEFILE)
            self.offset = int(offset.read())
            offset.close()
        except:
            self.offset = 0

    def _save_offset(self):
        if not xbmcvfs.exists(CACHEFOLDER):
            xbmcvfs.mkdir(CACHEFOLDER)
        try:
            offset = xbmcvfs.File(RESUMEFILE, 'w')
            offset.write(str(self.position))
            offset.close()
        except:
            log('failed to save resume point')

    def _read_cache(self, hexfile):
        images = ''
        try:
            cache = xbmcvfs.File(CACHEFILE % hexfile)
            images = eval(cache.read())
            cache.close()
        except:
            pass
        return images

    def _anim(self, cur_img):
        # reset position the current image
        cur_img.setPosition(0, 0)
        # pick a random anim
        number = random.randint(0,8)
        posx = 0
        posy = 0
        # add 1 sec fadeout time to showtime
        anim_time = self.slideshow_time + 1
        # set zoom level depending on the anim time
        zoom = 110 + anim_time
        if number == 1 or number == 5 or number == 7:
            posx = int(-1280 + (12.8 * anim_time) + 0.5)
        elif number == 2 or number == 6 or number == 8:
            posx = int(1280 - (12.8 * anim_time) + 0.5)
        if number == 3 or number == 5 or number == 6:
            posy = int(-720 + (7.2 * anim_time) + 0.5)
        elif number == 4 or number == 7 or number == 8:
            posy = int(720 - (7.2 * anim_time) + 0.5)
        # position the current image
        cur_img.setPosition(posx, posy)
        # add the animation to the current image
        if number == 0:
            cur_img.setAnimations(eval(EFFECTLIST[number] % (self.adj_time)))
        else:
            cur_img.setAnimations(eval(EFFECTLIST[number] % (self.adj_time, zoom, zoom, self.adj_time)))

    def _get_animspeed(self):
        # find the skindir
        json_query = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "Addons.GetAddonDetails", "params": {"addonid": "%s", "properties": ["path", "extrainfo"]}, "id": 1}' % SKINDIR)
        json_query = unicode(json_query, 'utf-8', errors='ignore')
        json_response = json.loads(json_query)
        if json_response.has_key('result') and (json_response['result'] != None) and json_response['result'].has_key('addon') and json_response['result']['addon'].has_key('path'):
            skinpath = json_response['result']['addon']['path']
        skinxml = xbmc.translatePath( os.path.join( skinpath, 'addon.xml' ).encode('utf-8') ).decode('utf-8')
        try:
            # parse the skin addon.xml
            self.xml = parse(skinxml)
            # find all extension tags
            tags = self.xml.documentElement.getElementsByTagName( 'extension' )
            for tag in tags:
                # find the effectslowdown attribute
                for (name, value) in tag.attributes.items():
                    if name == 'effectslowdown':
                        anim = value
                        return anim
        except:
            return

    def _set_prop(self, name, value):
        self.winid.setProperty('SlideView.%s' % name, value)

    def _clear_prop(self, name):
        self.winid.clearProperty('SlideView.%s' % name)

    def _exit(self):
        # exit when onScreensaverDeactivated gets called
        self.stop = True

        # exit for umsa
        if self.slideshow_umsa == 'true':
            
            # close db, doesn't work as sometimes after this a select is done
            #self.umsa_db.close()
            
            # write last 50 games to file
            try:
                fobj = None
                fobj = open(
                    xbmc.translatePath(
                        'special://profile/addon_data/script.umsa.mame.surfer/lastsaver.txt'
                    ),
                    'w'
                )
                if fobj:
                    fobj.write( '\n'.join(self.lastgames) )
                    fobj.close()
            except:
                pass
         
        # clear our properties on exit
        self._clear_prop('Slide1')
        self._clear_prop('Slide2')
        self._clear_prop('Fade1')
        self._clear_prop('Fade2')
        self._clear_prop('Fade11')
        self._clear_prop('Fade12')
        self._clear_prop('Dim')
        self._clear_prop('Music')
        self._clear_prop('Splash')
        self._clear_prop('Background')
        # save the current position  to file
        if self.slideshow_type == '2' and self.slideshow_random == 'false' and self.slideshow_resume == 'true':
            self._save_offset()
        self.close()


class img_update(threading.Thread):
    def __init__( self, *args, **kwargs ):
        self._get_items =  kwargs['data']
        threading.Thread.__init__(self)
        self.stop = False
        self.Monitor = MyMonitor(action = self._exit)

    def run(self):
        while (not self.Monitor.abortRequested()) and (not self.stop):
            # create a fresh index as quickly as possible after slidshow started
            self._get_items(True)
            count = 0
            while count != 3600: # check for new images every hour
                xbmc.sleep(1000)
                count += 1
                if self.Monitor.abortRequested() or self.stop:
                    return

    def _exit(self):
        # exit when onScreensaverDeactivated gets called
        self.stop = True

class MyMonitor(xbmc.Monitor):
    def __init__( self, *args, **kwargs ):
        self.action = kwargs['action']

    def onScreensaverDeactivated(self):
        self.action()
