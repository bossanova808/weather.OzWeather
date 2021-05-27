# -*- coding: utf-8 -*-
import ftplib
import glob
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib3
from math import sin, cos, sqrt, atan2, radians
import xbmc

# Small hack to allow for unit testing - see common.py for explanation
if not xbmc.getUserAgent():
    sys.path.insert(0, '../../..')

from resources.lib.store import Store
from resources.lib.common import *


def get_distance(point1, point2):
    """
    Given two (lat,long) tuples return the distance between them
    https://stackoverflow.com/questions/57294120/calculating-distance-between-latitude-and-longitude-in-python
    """
    R = 6370
    lat1 = radians(point1[0])
    lon1 = radians(point1[1])
    lat2 = radians(point2[0])
    lon2 = radians(point2[1])

    d_lon = lon2 - lon1
    d_lat = lat2 - lat1

    a = sin(d_lat / 2)**2 + cos(lat1) * cos(lat2) * sin(d_lon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    distance = R * c
    return distance


def closest_radar_to_lat_lon(point):
    """
    Given a lat/long tuple, return the closest radar (lat/lon) from our list of radars
    """
    closest_radar = (0,0)
    closest_distance = 10000
    for radar in Store.BOM_RADAR_LOCATIONS:
        distance = get_distance(point, radar)
        log(f'Point {point}, radar {radar}, distance {distance}')
        if distance < closest_distance:
            log(f'Setting closest radar to {radar}')
            closest_radar = radar
            closest_distance = distance

    return closest_radar


def download_background(radar_code, file_name, backgrounds_path):
    """
    Downloads a radar background given a BOM radar code like IDR023 & filename
    """

    # Needed due to bug in python 2.7 urllib, doesn't hurt anything else, so leave it in...
    # https://stackoverflow.com/questions/44733710/downloading-second-file-from-ftp-fails
    urllib.request.urlcleanup()

    out_file_name = file_name

    # The legend file doesn't have the radar code in the filename
    if file_name == "IDR.legend.0.png":
        out_file_name = "legend.png"
    else:
        # Append the radar code
        file_name = radar_code + "." + file_name

    # Delete backgrounds older than a week old
    if os.path.isfile(backgrounds_path + out_file_name):
        file_creation = os.path.getmtime(backgrounds_path + out_file_name)
        now = time.time()
        week_ago = now - 7 * 60 * 60 * 24  # Number of seconds in a week
        # log ("file creation: " + str(file_creation) + " week_ago " + str(week_ago))
        if file_creation < week_ago:
            log("Backgrounds stale (> one week) - refreshing - " + out_file_name)
            os.remove(backgrounds_path + out_file_name)
        else:
            log("Using cached background - " + out_file_name)

    # Download the backgrounds only if we don't have them yet
    if not os.path.isfile(backgrounds_path + out_file_name):

        log("Downloading missing background image....[%s] as [%s]" % (file_name, out_file_name))

        if "background.png" in file_name and '00004' in file_name:
            url_to_get = Store.BOM_RADAR_BACKGROUND_FTPSTUB + 'IDE00035.background.png'
        else:
            url_to_get = Store.BOM_RADAR_BACKGROUND_FTPSTUB + file_name

        try:
            radar_image = urllib.request.urlopen(url_to_get)
            with open(backgrounds_path + "/" + out_file_name, "wb") as fh:
                fh.write(radar_image.read())

        except Exception as e:
            log(f"Failed to retrieve radar background image: {url_to_get}, exception: {str(e)}")


def prepare_backgrounds(radar_code, backgrounds_path):
    """
    Download backgrounds for given radar
    """

    log("Calling prepareBackgrounds on [%s]" % radar_code)

    download_background(radar_code, "IDR.legend.0.png", backgrounds_path)
    download_background(radar_code, "background.png", backgrounds_path)
    # these images don't exist for the national radar, so don't try and get them
    if radar_code != "IDR00004":
        download_background(radar_code, "locations.png", backgrounds_path)
        download_background(radar_code, "range.png", backgrounds_path)
        download_background(radar_code, "topography.png", backgrounds_path)
        download_background(radar_code, "waterways.png", backgrounds_path)


def build_images(radar_code, update_radar_backgrounds, backgrounds_path, overlay_loop_path):
    """
    Builds the radar images given a BOM radar code like IDR023
    The radar images are cached for four hours, backgrounds for a week (or always if updateRadarBackgrounds is false)
    """

    # grab the current time as as 12 digit 0 padded string
    time_now = format(int(time.time()), '012d')

    log("build_images(%s)" % radar_code)
    log("Overlay loop path: " + overlay_loop_path)
    log("Backgrounds path: " + backgrounds_path)

    log("Deleting any radar overlays older than 2 hours (as BOM keeps last two hours, we do too)")
    current_files = glob.glob(overlay_loop_path + "/*.png")
    for count, file in enumerate(current_files):
        filetime = os.path.getmtime(file)
        two_hours_ago = time.time() - (2 * 60 * 60)
        if filetime < two_hours_ago:
            os.remove(file)
            log("Deleted aged radar image " + str(os.path.basename(file)))

    # rename the currently kept radar backgrounds to prevent Kodi caching issues
    current_files = glob.glob(overlay_loop_path + "/*.png")
    for file in current_files:
        os.rename(file, os.path.dirname(file) + "/" + time_now + "." + os.path.basename(file)[13:])

    # create the folder for the backgrounds path if it does not yet exist
    if not os.path.exists(backgrounds_path):
        try:
            os.makedirs(backgrounds_path)
            log("Created path for backgrounds at" + backgrounds_path)
        except Exception:
            log("ERROR: Failed to create directory for radar background images!")
            return

    if not os.path.exists(overlay_loop_path):
        attempts = 0
        success = False
        while not success and (attempts < 20):
            try:
                os.makedirs(overlay_loop_path)
                success = True
                log("Successfully created " + overlay_loop_path)
            except Exception:
                attempts += 1
                time.sleep(0.1)
        if not success:
            log("ERROR: Failed to create directory for loop images!")
            return

    # If we don't have any backgrounds, try and get them no matter what...
    if not os.listdir(backgrounds_path):
        update_radar_backgrounds = True

    # If we need to get background images, go get them....
    if update_radar_backgrounds:
        prepare_backgrounds(radar_code, backgrounds_path)

    # Ok so we have the backgrounds...now it is time get the current radar loop
    # first we retrieve a list of the available files via ftp

    log("Download the radar loop")
    files = []

    log("Log in to BOM FTP")
    ftp = ftplib.FTP("ftp.bom.gov.au")
    ftp.login("anonymous", "anonymous@anonymous.org")
    ftp.cwd("/anon/gen/radar/")

    log("Get files list")
    # connected, so let's get the list
    try:
        files = ftp.nlst()
    except ftplib.error_perm as resp:
        if str(resp) == "550 No files found":
            log("No files in BOM ftp directory!")
        else:
            log("Something wrong in the ftp bit of radar images")

    log("Download the files...")
    # ok now we need just the matching radar files...
    loop_pic_names = []
    for f in files:
        if radar_code in f:
            loop_pic_names.append(f)

    # download the actual images, might as well get the longest loop they have
    for f in loop_pic_names:
        # don't re-download ones we already have
        if not os.path.isfile(overlay_loop_path + time_now + "." + f):
            # ignore the composite gif...
            if f[-3:] == "png":
                image_to_retrieve = Store.BOM_RADAR_FTPSTUB + f
                output_file = time_now + "." + f
                log("Retrieving new radar image: " + image_to_retrieve)
                log("Output to file: " + output_file)
                try:
                    radar_image = urllib.request.urlopen(image_to_retrieve)
                    with open(overlay_loop_path + "/" + output_file, "wb") as fh:
                        fh.write(radar_image.read())

                except Exception as e:
                    log(f"Failed to retrieve radar image: {image_to_retrieve}, exception: {str(e)}")
        else:
            log("Using cached radar image: " + time_now + "." + f)


###########################################################
# MAIN - for testing outside of Kodi

if __name__ == "__main__":

    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        try:
            log("\n\nCleaning test-outputs folder")
            shutil.rmtree(os.getcwd() + "/test-outputs/")
        except Exception as inst:
            pass

    log("\nCurrent files in test-outputs:\n")

    for dir_path, dir_names, filenames in os.walk(os.getcwd() + "/test-outputs/"):
        for name in dir_names:
            log(os.path.join(dir_path, name))
        for name in filenames:
            log(os.path.join(dir_path, name))

    test_radars = ["IDR023", "IDR00004"]

    for test_radar in test_radars:
        log(f'\nTesting getting radar images from the BOM for {test_radar}\n')
        backgrounds_path = os.getcwd() + "/test-outputs/backgrounds/" + test_radar + "/"
        overlay_loop_path = os.getcwd() + "/test-outputs/loop/" + test_radar + "/"
        build_images(test_radar, True, backgrounds_path, overlay_loop_path)
        log(os.listdir(backgrounds_path))
        log(os.listdir(overlay_loop_path))
