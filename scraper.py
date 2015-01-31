#!/usr/bin/env python                                                                                                                                                                
import re
import os
import sys
import django
import mechanize

sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), 'scraper/')))
sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), 'scraper/scraper/')))

os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'
django.setup()

from bs4 import BeautifulSoup, Comment, Tag
from django.core.exceptions import ObjectDoesNotExist
from custom_scraper.models import *
from time import sleep

def soupify(page):
    s = BeautifulSoup(page)

    # Remove unwanted tags
    tags = s.findAll(lambda tag: tag.name == 'script' or \
                                 tag.name == 'style')
    for t in tags:
        t.extract()
        
    # Remove comments
    comments = s.findAll(text=lambda text:isinstance(text, Comment))
    for c in comments:
        c.extract()

    # Remove entity references?
    return s

class ArchitectFinderScraper(object):
    def __init__(self):
        self.url = "http://architectfinder.aia.org/frmSearch.aspx"
        self.br = mechanize.Browser()
        self.br.addheaders = [('User-agent', 
                               'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_6_8) AppleWebKit/535.7 (KHTML, like Gecko) Chrome/16.0.912.63 Safari/535.7')]

    def extract_addr(self, soup, firm):
        p = soup.find('span', id='ctl00_ContentPlaceHolder1_lblFirmLocation')

        addr = ' '.join(['%s' % x for x in p.findAll(text=True)])
        addr = ' '.join(addr.split())

        firm.addr = addr

    def extract_contact_name(self, soup, firm):
        p = soup.find('span', id='ctl00_ContentPlaceHolder1_lblPrimaryContact')
        r = re.compile(r'\d{4}')
        t = p.findAll(text=True)

        if len(t) > 0:
            if re.search(r, t[0]) is None:
                firm.contact_name = t[0]

    def extract_phone(self, soup, firm):
        p = soup.find('span', id='ctl00_ContentPlaceHolder1_lblPrimaryContact')
        r = re.compile(r'\d{4}')
        t = p.findAll(text=True)

        if len(t) > 0:
            if re.search(r, t[-1]):
                firm.phone = t[-1]

    def extract_email(self, soup, firm):
        p = soup.find('span', id='ctl00_ContentPlaceHolder1_lblMoreInfo')
        r = re.compile(r'mailto:\b([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,4})\b', re.I)
        a = p.find('a', href=r)

        if a:
            m = re.search(r, a.get('href'))
            if len(m.groups()):
                firm.email = m.group(1)

    def extract_url(self, soup, firm):
        p = soup.find('span', id='ctl00_ContentPlaceHolder1_lblMoreInfo')
        a = p.find('a', text=re.compile(r'^Website.?$', re.I))

        if a:
            firm.link = a['href']

    def scrape_firm_page(self, firm):
        u = 'http://architectfinder.aia.org/frmFirmDetails.aspx?FirmID=%s' % firm.frmid

        print 'Opening %s' % u
        self.br.open(u)

        s = BeautifulSoup(self.br.response().read())

        self.extract_addr(s, firm)
        self.extract_contact_name(s, firm)
        self.extract_phone(s, firm)
        self.extract_email(s, firm)
        self.extract_url(s, firm)

        firm.checked_email = True
        firm.save()

    def get_state_items(self):
        self.br.open(self.url)
        self.br.select_form('aspnetForm')
        items = self.br.form.find_control('ctl00$ContentPlaceHolder1$drpState').get_items()
        return items

    def scrape_state_firms(self, state_item):
        self.br.open(self.url)
        
        s = soupify(self.br.response().read())
        saved_form = s.find('form', id='aspnetForm').prettify()

        self.br.select_form('aspnetForm')

        self.br.form.new_control('hidden', '__EVENTTARGET',   {'value': ''})
        self.br.form.new_control('hidden', '__EVENTARGUMENT', {'value': ''})
        self.br.form.new_control('hidden', '__ASYNCPOST',     {'value': 'true'})
        self.br.form.new_control('hidden', 'ctl00$ScriptManager1', {'value': 'ctl00$ScriptManager1|ctl00$ContentPlaceHolder1$btnSearch'})
        self.br.form.fixup()
        self.br.form['ctl00$ContentPlaceHolder1$drpState'] = [ state_item.name ]

        ctl = self.br.form.find_control('ctl00$ContentPlaceHolder1$btnfrmSearch')
        self.br.form.controls.remove(ctl)

        ctl = self.br.form.find_control('ctl00$ContentPlaceHolder1$btnAccept')
        self.br.form.controls.remove(ctl)

        ctl = self.br.form.find_control('ctl00$ContentPlaceHolder1$btnSearch')
        ctl.disabled = False

        self.br.submit()

        pageno = 2

        while True:
            r = self.br.response()
            s = BeautifulSoup(r.read())
            r = re.compile(r'^frmFirmDetails\.aspx\?FirmID=([A-Z0-9-]+)$')

            for a in s.findAll('a', href=r):
                m = re.search(r, a['href'])
                g = m.group(1)

                if ArchitectureFirm.objects.filter(frmid=g).exists():
                    continue

                firm = ArchitectureFirm()
                firm.name = a.text
                firm.frmid = m.group(1)
                firm.save()

                print a


            a = s.find('a', text='%d' % pageno)
            if not a:
                break

            pageno += 1

            r = re.compile(r'VIEWSTATE\|([^|]+)')
            m = re.search(r, str(s))
            view_state = m.group(1)

            r = re.compile(r"__doPostBack\('([^']+)")
            m = re.search(r, a['href'])

            html = saved_form.encode('utf8')
            resp = mechanize.make_response(html, [("Content-Type", "text/html")],
                                           self.br.geturl(), 200, "OK")
            self.br.set_response(resp)
            self.br.select_form('aspnetForm')

            self.br.form.set_all_readonly(False)
            self.br.form['__EVENTTARGET'] = m.group(1)
            self.br.form['__VIEWSTATE'] = view_state
            self.br.form['ctl00$ContentPlaceHolder1$drpState'] = [ state_item.name ]
            self.br.form.new_control('hidden', '__ASYNCPOST',     {'value': 'true'})
            self.br.form.new_control('hidden', 'ctl00$ScriptManager1', {'value': 'ctl00$ContentPlaceHolder1$pnlgrdSearchResult|'+m.group(1)})
            self.br.form.fixup()

            ctl = self.br.form.find_control('ctl00$ContentPlaceHolder1$btnfrmSearch')
            self.br.form.controls.remove(ctl)

            ctl = self.br.form.find_control('ctl00$ContentPlaceHolder1$btnAccept')
            self.br.form.controls.remove(ctl)

            ctl = self.br.form.find_control('ctl00$ContentPlaceHolder1$btnSearch')
            self.br.form.controls.remove(ctl)

            self.br.submit()

    def scrape(self):
        state_items = self.get_state_items()
        for state_item in state_items:
            if len(state_item.name) < 1:
                continue

            print 'Scraping firms for %s' % state_item.name
#            self.scrape_state_firms(state_item)

        r = r'[A-Z90-9]{8}-'
        for firm in ArchitectureFirm.objects.filter(frmid__regex=r):
            if not firm.email: 
                if firm.checked_email is False:
                    print 'Scraping firm page %s' % firm.frmid
                    self.scrape_firm_page(firm)
                    sleep(0.75)                
            else:
                firm.checked_email = True
                firm.save()

            print firm

if __name__ == '__main__':
    scraper = ArchitectFinderScraper()
    scraper.scrape()
