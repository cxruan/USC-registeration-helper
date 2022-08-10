# -*- coding: UTF-8 -*-
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import smtplib
from email.header import Header
from email.mime.text import MIMEText
import requests
import os
import time
import re
import json

config = json.loads(os.environ.get("CONFIG"))

# Configuration
MODE = config["settings"]['general']['mode']
UPDATE_INTERVAL = config["settings"]['general']['update_interval']
MONITOR_ALL = config["settings"]['general']['monitor_all']
USC_TERM = config["settings"]['usc']['term']
USC_USERNAME = config["settings"]['usc']['usc_username']
USC_PASSWORD = config["settings"]['usc']['usc_password']
IFTTT_EVENT_NAME = config["settings"]['ifttt']['event_name']
IFTTT_KEY = config["settings"]['ifttt']['key']
SMTP_SERVER = config["settings"]['smtp']['server']
SMTP_PORT = config["settings"]['smtp']['port']
SMTP_USERNAME = config["settings"]['smtp']['user']
SMTP_PASSWORD = config["settings"]['smtp']['password']
SMTP_FROM = config["settings"]['smtp']['from']
SMTP_TO = [config["settings"]['smtp']['to']]
SECTIONS_TO_MONITOR = set(config['sections_to_monitor'])
SECTIONS_TO_ENROLL = []

print("---------- Recipes -----------")
for recipe in config['recipes_to_enroll']:
    SECTIONS_TO_ENROLL += recipe['conditions'].get('open', [])
    SECTIONS_TO_ENROLL += recipe['conditions'].get('closed', [])
    SECTIONS_TO_ENROLL += recipe['conditions'].get('registered', [])
    SECTIONS_TO_ENROLL += recipe['conditions'].get('not_registered', [])
    print(recipe)
print("------------------------------")

SECTIONS_TO_ENROLL = set(SECTIONS_TO_ENROLL)
PEOPLE_SECTIONS_DIC = config.get('people_sections_dic', {})


class Course:
    courseId = ""
    section = ""
    courseType = ""
    time = ""
    days = ""
    instructor = ""
    regSeats = ""
    opened = False
    openChanged = False
    registered = False
    scheduled = False

    def __init__(self, section):
        self.section = section

    def status_update(self, soup):
        target = soup.find(
            id="section_" +
            self.section).find(
            attrs={
                "style": "padding:0;border-top: solid 1px #F2F1F1;"})
        self.courseId = target.parent.parent.find_previous_sibling(
            attrs={"data-parent": "#accordion"}).find(class_="crsID").get_text().rstrip(": ")
        self.courseType = target.find(class_="type_alt1").get_text() if target.find(
            class_="type_alt1") else target.find(class_="type_alt0").get_text()
        self.time = target.find(class_="hours_alt1").get_text() if target.find(
            class_="hours_alt1") else target.find(class_="hours_alt0").get_text()
        self.days = target.find(class_="days_alt1").get_text() if target.find(
            class_="days_alt1") else target.find(class_="days_alt0").get_text()
        self.instructor = target.find(class_="instr_alt1").get_text() if target.find(
            class_="instr_alt1") else target.find(class_="instr_alt0").get_text()
        self.regSeats = target.find(class_="regSeats_alt1").get_text() if target.find(
            class_="regSeats_alt1") else target.find(class_="regSeats_alt0").get_text()
        oldOpened = self.opened
        self.opened = False if target.find(style="color:#ff0000 ;") else True
        self.openChanged = False if oldOpened == self.opened else True
        active_button = target.find(class_="schUnschRmv", style="display: block;")
        self.registered = False if active_button.get("id")[7:11] == "regN" else True
        self.scheduled = False if active_button.get("id")[0:6] == "schedN" else True


def land_in_coursebin():
    chrome_options = webdriver.ChromeOptions()
    chrome_bin = os.environ.get("GOOGLE_CHROME_BIN")
    if chrome_bin:
        chrome_options.binary_location = chrome_bin
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--remote-debugging-port=9222")
    browser = webdriver.Chrome(options=chrome_options)
    browser.get('https://my.usc.edu/')
    WebDriverWait(browser, 10).until(ec.visibility_of_element_located((By.CLASS_NAME, 'page-wrapper')))
    username = browser.find_element_by_id('username')
    username.send_keys(USC_USERNAME)
    password = browser.find_element_by_id('password')
    password.send_keys(USC_PASSWORD)
    button = browser.find_element_by_name('_eventId_proceed')
    button.click()
    
    WebDriverWait(browser, 10).until(ec.visibility_of_element_located((By.CLASS_NAME, 'main')))
    pushButton = browser.find_element(By.CLASS_NAME, 'auth-button positive')
    pushButton.click()
                                                                       
    WebDriverWait(browser, 10).until(ec.visibility_of_element_located((By.CLASS_NAME, 'service-header')))
    browser.get('https://my.usc.edu/portal/oasis/webregbridge.php')
    browser.get('https://webreg.usc.edu/Terms/termSelect?term=' + USC_TERM)
    browser.get('https://webreg.usc.edu/myCourseBin')
    return browser


def register(browser, test=False):
    browser.get('https://webreg.usc.edu/Register')
    if not test:
        browser.find_element_by_name('btnSubmit').click()
        WebDriverWait(browser, 10).until(ec.visibility_of_element_located(
            (By.CLASS_NAME, 'content-wrapper-regconfirm')))
        status = "Success" if BeautifulSoup(browser.page_source, "html.parser").find(
            string=re.compile("Your transaction was successful:")) else "Failed"
    else:
        status = "Test"
    return (browser, status)


def satisfy_recipe(recipe, courses):
    for section in recipe['conditions'].get('open', []):
        if section not in courses or not courses[section].opened:
            return False
    for section in recipe['conditions'].get('closed', []):
        if section not in courses or courses[section].opened:
            return False
    for section in recipe['conditions'].get('registered', []):
        if section not in courses or not courses[section].registered:
            return False
    for section in recipe['conditions'].get('not_registered', []):
        if section not in courses or courses[section].registered:
            return False
    return True


def all_activated_recipes(recipes, courses, failed_recipes):
    results = []
    for recipe in recipes:
        satisfied = satisfy_recipe(recipe, courses)
        if satisfied and recipe['name'] not in failed_recipes:
            results.append(recipe)
    return results


def check_schedule(course, checkout, browser):
    to_drop = False
    if course.registered:
        if course.section in checkout.get('drop', []):
            to_drop = True
            if course.scheduled:
                browser.find_element_by_css_selector(
                    """a[data-ajax-complete="procschedNregY('""" + course.section + """')"]""").click()
                WebDriverWait(
                    browser, 10).until(
                    ec.visibility_of_element_located(
                        (By.CSS_SELECTOR, """a[data-ajax-complete="procschedYregY('""" + course.section + """')"]""")))
        else:
            if not course.scheduled:
                browser.find_element_by_css_selector(
                    """a[data-ajax-complete="procschedYregY('""" + course.section + """')"]""").click()
                WebDriverWait(
                    browser, 10).until(
                    ec.visibility_of_element_located(
                        (By.CSS_SELECTOR, """a[data-ajax-complete="procschedNregY('""" + course.section + """')"]""")))
    else:
        if course.section in checkout.get('register', []):
            if not course.scheduled:
                browser.find_element_by_css_selector(
                    """a[data-ajax-complete="procschedYregN('""" + course.section + """')"] """).click()
                WebDriverWait(
                    browser, 10).until(
                    ec.visibility_of_element_located(
                        (By.CSS_SELECTOR, """a[data-ajax-complete="procschedNregN('""" + course.section + """')"]""")))
        else:
            if course.scheduled:
                browser.find_element_by_css_selector(
                    """a[data-ajax-complete="procschedNregN('""" + course.section + """')"]""").click()
                WebDriverWait(
                    browser, 10).until(
                    ec.visibility_of_element_located(
                        (By.CSS_SELECTOR, """a[data-ajax-complete="procschedYregN('""" + course.section + """')"]""")))
    return to_drop


def get_activated_courses(soup):
    monitored_courses = []
    recipe_courses = {}
    for course_soup in soup.find_all(style="padding:0;border-top: solid 1px #F2F1F1;"):
        section = course_soup.parent["id"].split('_')[1]
        if section in SECTIONS_TO_MONITOR:
            monitored_courses.append(Course(section))
        if section in SECTIONS_TO_ENROLL:
            recipe_courses[section] = Course(section)
    return (monitored_courses, recipe_courses)


def monitor_message(course, verbose=False):
    if verbose:
        msg = '========Monitor Information=======\n'
        msg += "Course: {}\nSection: {}\n{}\n{}\n{}\n{}\n{}".format(
            course.courseId,
            course.section,
            course.courseType,
            course.time,
            course.days,
            course.instructor,
            course.regSeats)
    else:
        msg = "{} {} {} {}".format(
            course.regSeats.lstrip("Registered: "),
            course.section,
            course.courseId.replace(" ", ""),
            course.courseType.lstrip("Type: "))
    return msg


def recipe_message(recipe, status, courses, verbose=False):
    if verbose:
        msg = '========Recipe Information========\n'
        msg += "Recipe: " + recipe['name'] + '\n'
        if recipe['action']['register']:
            msg += "Register:\n"
            for section in recipe['action'].get('register', []):
                msg += "#{secion_id} {course_id:10s} {type}".format(
                    secion_id=courses[section].section,
                    type=courses[section].courseType,
                    course_id=courses[section].courseId) + '\n'
        if recipe['action']['drop']:
            msg += "Drop:\n"
            for section in recipe['action'].get('drop', []):
                msg += "#{secion_id} {course_id:10s} {type}".format(
                    secion_id=courses[section].section,
                    type=courses[section].courseType,
                    course_id=courses[section].courseId) + '\n'
        msg += "Status: " + str(status) + '\n'
    else:
        msg = recipe['name'] + ' : ' + str(status)
    return msg


def send_email(econtent, efrom, eto, esubject):
    message = MIMEText(econtent, 'plain', 'utf-8')
    message['From'] = "USC Webreg Helper <{}>".format(efrom)
    message['To'] = ",".join(eto)
    message['Subject'] = esubject
    try:
        smtpObj = smtplib.SMTP_SSL(SMTP_SERVER, int(SMTP_PORT))
        smtpObj.login(SMTP_USERNAME, SMTP_PASSWORD)
        smtpObj.sendmail(efrom, eto, message.as_string())
        print("Email has been sent successfully to " + eto[0])
    except smtplib.SMTPException as e:
        print(e)


def main():
    browser = land_in_coursebin()
    soup = BeautifulSoup(browser.page_source, "html.parser")
    monitored_courses, recipe_courses = get_activated_courses(soup)
    failed_recipes = set()
    while True:
        content = ""
        soup = BeautifulSoup(browser.page_source, "html.parser")

        # Reopen coursebin if not loaded successfully
        if not soup.find(class_="content-wrapper-coursebin"):
            browser.close()
            print("Cannot open Coursebin.\nReopenning...\n")
            break

        # Failed Recipes
        if len(failed_recipes) != 0:
            print("failed recipes:", end=" ")
            print(list(failed_recipes))

        # Status Update
        for course in recipe_courses.values():
            course.status_update(soup)
        for course in monitored_courses:
            course.status_update(soup)

        # Courses Monitoring
        for course in monitored_courses:
            print(monitor_message(course, False), end=" ->")
            if course.openChanged:
                content += monitor_message(course, True) + '\n\n'
                for people, sections in PEOPLE_SECTIONS_DIC.items():
                    if course.section in sections:
                        print(f" {people}")
                        send_email(monitor_message(course, True) + '\n\n', SMTP_FROM,
                                   [people], "Status Change - USC Webreg Helper")
                print()
            else:
                for people, sections in PEOPLE_SECTIONS_DIC.items():
                    if course.section in sections:
                        print(f" {people}", end="")
                print()

        # Courses Enrolling
        activated_recipes = all_activated_recipes(
            config['recipes_to_enroll'], recipe_courses, failed_recipes)
        for recipe in activated_recipes:
            dropped_set = set()
            for section, course in recipe_courses.items():
                to_drop = check_schedule(course, recipe['action'], browser)
                if to_drop:
                    dropped_set.add(section)
            browser, status = register(browser, False)
            print(recipe_message(recipe, status, recipe_courses, False))
            content += recipe_message(recipe, status,
                                      recipe_courses, True) + '\n\n'
            if status == "Failed":
                failed_recipes.add(recipe['name'])
            elif status == "Success":
                for dropped in dropped_set:
                    if dropped in recipe_courses.keys():
                        recipe_courses.pop(dropped)
                    for i in range(len(monitored_courses)):
                        if monitored_courses[i].section == dropped:
                            monitored_courses.pop(i)

        if content and MONITOR_ALL:
            if MODE == "smtp" or MODE == "both":
                send_email(content, SMTP_FROM, SMTP_TO, "Status Change - USC Webreg Helper")
            if MODE == "ifttt" or MODE == "both":
                api_url = "https://maker.ifttt.com/trigger/{}/with/key/{}".format(IFTTT_EVENT_NAME, IFTTT_KEY)
                r = requests.post(api_url, data={'value1': content})
                print(r.text)
        print("------------------------------")
        time.sleep(UPDATE_INTERVAL)
        browser.get('https://webreg.usc.edu/myCourseBin')


if __name__ == '__main__':
    main()
