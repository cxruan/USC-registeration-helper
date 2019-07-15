# -*- coding: UTF-8 -*-
import ast
from bs4 import BeautifulSoup
import configparser
from email.header import Header
from email.mime.text import MIMEText
import logging
import requests
from selenium import webdriver
import smtplib
import sys
import time

# Configuration
cf = configparser.ConfigParser()
cf.read("./config.ini")
mode = cf['general']['mode']
sessions = ast.literal_eval(cf['general']['sessions'])
logging_enabled = cf.getboolean('general', 'logging')
update_interval = int(cf['general']['update_interval'])
term = cf['usc']['term']
usc_username = cf['usc']['usc_username']
usc_password = cf['usc']['usc_password']
event_name = cf['ifttt']['event_name']
key = cf['ifttt']['key']
smtp_server = cf['smtp']['smtp_server']
smtp_user = cf['smtp']['smtp_user']
smtp_password = cf['smtp']['smtp_password']
from_addr = cf['smtp']['from_addr']
to_addr = [cf['smtp']['to_addr']]

if logging_enabled:
    # Configure logging
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    rq = time.strftime('%Y%m%d%H%M', time.localtime(time.time()))
    log_path = './logs/'
    log_name = log_path + rq + '.log'
    fh = logging.FileHandler(log_name, mode='w')
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s - %(filename)s - %(levelname)s: %(message)s", '%Y-%m-%d %H:%M:%S')
    fh.setFormatter(formatter)
    logger.addHandler(fh)

if not (mode == "ifttt" or mode == "smtp" or mode == "both"):
    print("Invalid mode")
    sys.exit(0)


class Course:
    courseId_ = ""
    session_ = ""
    type_ = ""
    time_ = ""
    days_ = ""
    instr_ = ""
    regSeats_ = ""
    prev_status = False
    curr_status = False

    def __init__(self, session, soup_data, prev_status):
        target = soup_data.find(
            id="section_"+session).find(attrs={"style": "padding:0;border-top: solid 1px #F2F1F1;"})
        self.courseId_ = target.parent.parent.find_previous_sibling(
            attrs={"data-parent": "#accordion"}).find(class_="crsID").get_text().rstrip(": ")
        self.session_ = session
        self.type_ = target.find(class_="type_alt1").get_text() if target.find(
            class_="type_alt1") else target.find(class_="type_alt0").get_text()
        self.time_ = target.find(class_="hours_alt1").get_text() if target.find(
            class_="hours_alt1") else target.find(class_="hours_alt0").get_text()
        self.days_ = target.find(class_="days_alt1").get_text() if target.find(
            class_="days_alt1") else target.find(class_="days_alt0").get_text()
        self.instr_ = target.find(class_="instr_alt1").get_text() if target.find(
            class_="instr_alt1") else target.find(class_="instr_alt0").get_text()
        self.regSeats_ = target.find(class_="regSeats_alt1").get_text() if target.find(
            class_="regSeats_alt1") else target.find(class_="regSeats_alt0").get_text()
        self.prev_status = prev_status
        if not target.find(style="color:#ff0000 ;"):
            self.curr_status = True

    def __str__(self):
        return "Course: {}\nSession: {}\n{}\n{}\n{}\n{}\n{}\n\n".format(self.courseId_, self.session_, self.type_, self.time_, self.days_, self.instr_, self.regSeats_)

    def __repr__(self):
        return "{} {} {} {}".format(self.session_, self.courseId_.replace(" ", ""), self.type_.lstrip("Type: "), self.regSeats_.lstrip("Registered: "))


def land_in_coursebin():
    opts = webdriver.ChromeOptions()
    opts.add_argument('headless')
    browser = webdriver.Chrome(options=opts)
    browser.get('https://my.usc.edu/')
    username = browser.find_element_by_id('username')
    username.send_keys(usc_username)
    password = browser.find_element_by_id('password')
    password.send_keys(usc_password)
    button = browser.find_element_by_name('_eventId_proceed')
    button.click()
    browser.get('https://my.usc.edu/portal/oasis/webregbridge.php')
    browser.get('https://webreg.usc.edu/Terms/termSelect?term='+term)
    browser.get('https://webreg.usc.edu/myCourseBin')
    return browser


def sendEmail(econtent, efrom, eto, esubject):
    message = MIMEText(econtent, 'plain', 'utf-8')
    message['From'] = "USC Webreg Helper <{}>".format(efrom)
    message['To'] = ",".join(eto)
    message['Subject'] = esubject
    try:
        smtpObj = smtplib.SMTP_SSL(smtp_server, 465)
        smtpObj.login(smtp_user, smtp_password)
        smtpObj.sendmail(efrom, eto, message.as_string())
        print("Email has been send successfully to " + eto[0])
        if logging_enabled:
            logger.info("Email has been send successfully to " + eto[0])
    except smtplib.SMTPException as e:
        print(e)
        if logging_enabled:
            logger.warning(e)


def main():
    while True:
        browser = land_in_coursebin()
        prev_statuses = {}
        for session in sessions:
            prev_statuses[session] = False
        while True:
            courses = []
            content = ""
            soup = BeautifulSoup(browser.page_source, "html.parser")
            # Reopen coursebin if not loaded successfully
            if not soup.find(class_="content-wrapper-coursebin"):
                browser.close()
                print("Cannot open Coursebin.\nReopenning...\n")
                if logging_enabled:
                    logger.warning("Cannot open Coursebin. Reopenning...")
                break
            for session in sessions:
                courses.append(Course(session, soup, prev_statuses[session]))
            for course in courses:
                prev_statuses[course.session_] = course.curr_status
                if logging_enabled:
                    if course.curr_status == True:
                        logger.warning(repr(course))
                    else:
                        logger.info(repr(course))
                if course.curr_status != course.prev_status:
                    content += str(course)
            if content:
                if mode == "smtp" or mode == "both":
                    sendEmail(content, from_addr, to_addr,
                              "Status Change - USC Webreg Helper")
                if mode == "ifttt" or mode == "both":
                    api_url = "https://maker.ifttt.com/trigger/{}/with/key/{}".format(
                        event_name, key)
                    r = requests.post(api_url, data={'value1': content})
                    print(r.text)
                    if logging_enabled:
                        logger.info(r.text)
            time.sleep(update_interval)
            browser.refresh()


if __name__ == '__main__':
    main()
