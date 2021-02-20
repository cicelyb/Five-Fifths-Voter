#!/usr/bin/env python3.6
# encoding: utf-8
'''
EarlyGeocoding -- Web Scrape California SOS site to find all current early voting sites and generate a data file that Five Fifths Voter can use for mapping.


@deffield updated: 2021-02-18
'''

import sys
import os
import json
import requests
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from argparse import ArgumentParser
from argparse import RawDescriptionHelpFormatter
from random import randint
from time import sleep

__all__ = []
__version__ = 0.1
__date__ = '2021-02-18'
__updated__ = '2021-02-18'

DEBUG = 0
TESTRUN = 1
TESTURL = 0
PROFILE = 0

JSON_PARAMS = {}
DIR = os.path.dirname(os.path.realpath(__file__))

class CLIError(Exception):
    '''Generic exception to raise and log different fatal errors.'''
    def __init__(self, msg):
        super(CLIError).__init__(type(self))
        self.msg = "E: %s" % msg
    def __str__(self):
        return self.msg
    def __unicode__(self):
        return self.msg

def getScrapeParams(county):
    global JSON_PARAMS
    if not JSON_PARAMS:        
        with open(os.path.join(DIR, 'scrapeParams.json')) as f:
            JSON_PARAMS = json.load(f)
    return JSON_PARAMS[county]

def getCounties():
    global JSON_PARAMS
    if not JSON_PARAMS:
        with open(os.path.join(DIR, 'scrapeParams.json')) as f:
            JSON_PARAMS = json.load(f)
    return JSON_PARAMS.keys()

def scrape(county, skip_existing, apikey):
    outdir = os.path.join(DIR, 'knownLocations')
    if not os.path.exists(outdir):
        os.makedirs(outdir)
    output_json = os.path.join(outdir, county + '.json')
    if os.path.exists(output_json):
        if skip_existing:
            print ("Skipping %s County because data already exists" % county)
            return 0
        with open(output_json) as f:
            print("json load")
            geodata = json.load(f)
    else:
        print("empty geodata")
        geodata = {}         

    payload = getScrapeParams(county.upper())
    print ("scraping early voting sites from %s County" % county)
    if TESTURL:
        scrapeURL='http://localhost:7777/index.html'
    else:
        scrapeURL = 'https://caearlyvoting.sos.ca.gov/'

    driver = webdriver.Chrome(ChromeDriverManager().install())
    driver.get(scrapeURL)
    countyID = Select(driver.find_element(By.NAME, "CountyID"))
    countyID.select_by_value(payload["CountyID"])
    isEarlyVoting = driver.find_element(By.NAME, "IsEarlyVoting")
    isEarlyVoting.click()
    searchButton = driver.find_element(By.ID, "search")
    searchButton.click()
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, 'VoteCenterTable')))

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    table = soup.select('#VoteCenterTable > tbody')
    addresses = []
    addressStart = False
    finishAddress = False
    address = ''
    locationName = ''
    rows = table[0].contents

    for r in range(len(rows)):
        ele = table[0].contents[r]
        if ele.name =='tr':
            cells = ele.find_all('td')
            if(len(cells) > 1):
                locationName = cells[1].contents[0].strip()
                addressCells = cells[1].find_all('div')
                address = addressCells[0].get_text().strip() + "," + addressCells[2].get_text().strip()
            else:
                return len(addresses)
            
        # clean up addresses
        cleanAddress = re.sub(r"[,.]+", ' ', address)
        cleanAddress = re.sub(r"[ ]{2,}", ' ', cleanAddress)
        cleanAddress = cleanAddress.upper()
        address = re.sub(r"[ ]{2,}", ' ', address)
        address = re.sub(r"[,]+", ', ', address)
        
        addresses.append({
            'address': {
                'location_name': locationName,
                'line1': address,
                'clean': cleanAddress
                }})
        address = ''
        locationName = ''
    
    for loc in addresses:
        addr = loc['address']['line1']
        clean = loc['address']['clean']
        
        if clean in geodata and 'lat' in geodata[clean] and 'lng' in geodata[clean]:
            print ("already geocoded", addr)
        else:
            print ("geocoding", addr)
            geodata[clean] = {}
            geodata[clean]['location_name'] = loc['address']['location_name']
            geodata[clean]['original_address'] = addr
            
            payload = {
                'address': addr,
                'key': apikey
                }
            data = requests.get('https://maps.googleapis.com/maps/api/geocode/json', params=payload).json()
            if data['status'] != 'OK':
                geodata[clean]['status'] = data['status']
                geodata[clean]['location_type'] = data['status']
                print("geocoding error %s County: '%s'" % (county, addr), file=sys.stderr)
                print(json.dumps(data, indent=4), file=sys.stderr)
            elif len(data['results']) > 1:
                geodata[clean]['location_type'] = 'AMBIGUOUS'
            else:
                result = data['results'][0]
                geodata[clean]['location_type'] = result['geometry']['location_type']                
                geodata[clean]['formatted_address'] = result['formatted_address']
                geodata[clean]['lat'] = result['geometry']['location']['lat']
                geodata[clean]['lng'] = result['geometry']['location']['lng']
                if geodata[clean]['location_type'] != 'ROOFTOP':
                    print("warning %s County: '%s' coding is %s" % (county, 
                                                             geodata[clean]['location_name'],
                                                             geodata[clean]['location_type']), file=sys.stderr)
            
    with open(output_json, 'w') as outfile:
        json.dump(geodata, outfile, indent=4)

    return len(addresses)

def main(argv=None): # IGNORE:C0111
    '''Command line options.'''

    if argv is None:
        argv = sys.argv
    else:
        sys.argv.extend(argv)

    program_name = os.path.basename(sys.argv[0])
    program_version = "v%s" % __version__
    program_build_date = str(__updated__)
    program_version_message = '%%(prog)s %s (%s)' % (program_version, program_build_date)
    program_shortdesc = __import__('__main__').__doc__.split("\n")[1]
    program_license = '''%s

  Updated on %s.
    
USAGE
''' % (program_shortdesc, str(__date__))

    try:
        # Setup argument parser
        parser = ArgumentParser(description=program_license, formatter_class=RawDescriptionHelpFormatter)
        parser.add_argument("-v", "--verbose", dest="verbose", action="count", default=0, help="set verbosity level [default: %(default)s]")
        parser.add_argument("-c", "--county", dest="counties", action="append", default=[], help="Which counties to include. [default: all counties]", metavar="COUNTY")
        parser.add_argument("-s", "--skip-existing", dest="skip_existing", action="store_true", default=False, help="skip counties that already have a data file. [default: %(default)s]")        
        parser.add_argument("-k", "--key", dest="apikey", required=True, action="store", help="Google Geocoding api key. [default: %(default)s]", metavar="KEY")
        
        parser.add_argument('-V', '--version', action='version', version=program_version_message)

        # Process arguments
        args = parser.parse_args()

        verbose = args.verbose
        skip_existing = args.skip_existing
        apikey = args.apikey
        counties = args.counties
        if len(counties) == 0:
            counties = getCounties()

        if verbose > 0:
            print("Verbose mode on")
        
        print(len(counties))
        num_counties = len(counties)
        i = 0
        for county in counties:            
            found = scrape(county.upper(), skip_existing, apikey)
            print(found)
            if found > 0 and i < (num_counties - 1):
                pause = randint(30,45)
                print("sleeping %d ... " % pause)
                sleep(pause)
            i = i + 1
            
        return 0
    except KeyboardInterrupt:
        ### handle keyboard interrupt ###
        return 0
    except Exception as e:
        if DEBUG or TESTRUN:
            raise(e)
        indent = len(program_name) * " "
        sys.stderr.write(program_name + ": " + repr(e) + "\n")
        sys.stderr.write(indent + "  for help use --help")
        return 2

if __name__ == "__main__":
    if DEBUG:
        sys.argv.append("-h")
        sys.argv.append("-v")
        sys.argv.append("-r")
    if TESTRUN:
        import doctest
        doctest.testmod()
    if PROFILE:
        import cProfile
        import pstats
        profile_filename = 'EarlyGeocoding_profile.txt'
        cProfile.run('main()', profile_filename)
        statsfile = open("profile_stats.txt", "wb")
        p = pstats.Stats(profile_filename, stream=statsfile)
        stats = p.strip_dirs().sort_stats('cumulative')
        stats.print_stats()
        statsfile.close()
        sys.exit(0)
    sys.exit(main())