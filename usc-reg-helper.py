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
sessions = ast.literal_eval(cf['session']['sessions'])
usc_username = cf['usc']['usc_username']
usc_password = cf['usc']['usc_password']
logging_enabled  = cf.getboolean('logging','logging')

if logging_enabled:
	# Configure logging
	logger = logging.getLogger()
	logger.setLevel(logging.INFO)
	rq = time.strftime('%Y%m%d%H%M', time.localtime(time.time()))
	log_path = './logs/'
	log_name = log_path + rq + '.log'
	fh = logging.FileHandler(log_name, mode='w')
	fh.setLevel(logging.DEBUG)
	formatter = logging.Formatter("%(asctime)s - %(filename)s - %(levelname)s: %(message)s", '%Y-%m-%d %H:%M:%S')
	fh.setFormatter(formatter)
	logger.addHandler(fh)

if cf['mode']['mode'] == "smtp":
	mode = 0
	smtp_server = cf['smtp']['smtp_server']
	smtp_user = cf['smtp']['smtp_user']
	smtp_password = cf['smtp']['smtp_password']
	from_addr = cf['email']['from_addr']
	to_addr = [cf['email']['to_addr']]
elif cf['mode']['mode'] == "ifttt":
	mode = 1
	event_name = cf['ifttt']['event_name']
	key = cf['ifttt']['key']
elif cf['mode']['mode'] == "both":
	mode = 2
	smtp_server = cf['smtp']['smtp_server']
	smtp_user = cf['smtp']['smtp_user']
	smtp_password = cf['smtp']['smtp_password']
	from_addr = cf['email']['from_addr']
	to_addr = [cf['email']['to_addr']]
	event_name = cf['ifttt']['event_name']
	key = cf['ifttt']['key']	
else:
	print("Invalid mode")
	sys.exit(0)

update_interval = int(cf['update_interval']['interval'])

class Course:
	session_ = ""
	type_ = ""
	time_ = ""
	days_ = ""
	instr_ = ""
	regSeats_ = ""
	prev_status = False
	status = False

	def __init__(self, session, soup_data, prev_status):
		target = soup_data.find(id="section_"+session).find(attrs={"style":"padding:0;border-top: solid 1px #F2F1F1;"})
		self.session_ = session
		self.type_ = target.find(class_="type_alt1").get_text() if target.find(class_="type_alt1") else target.find(class_="type_alt0").get_text()
		self.time_ = target.find(class_="hours_alt1").get_text() if target.find(class_="hours_alt1") else target.find(class_="hours_alt0").get_text()
		self.days_ = target.find(class_="days_alt1").get_text() if target.find(class_="days_alt1") else target.find(class_="days_alt0").get_text()
		self.instr_ = target.find(class_="instr_alt1").get_text() if target.find(class_="instr_alt1") else target.find(class_="instr_alt0").get_text()
		self.regSeats_ = target.find(class_="regSeats_alt1").get_text() if target.find(class_="regSeats_alt1") else target.find(class_="regSeats_alt0").get_text()
		self.prev_status = prev_status
		if not target.find(style="color:#ff0000 ;"):
			self.status = True;

	def str(self,k):
		# Verbose
		if(k==1):
			return "Session: "+self.session_+"\n"+self.type_+"\n"+self.time_+"\n"+self.days_+"\n"+self.instr_+"\n"+self.regSeats_+"\n\n"
		# Logging
		elif(k==2):
			return "Session: "+self.session_+" "+self.regSeats_

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
	browser.get('https://webreg.usc.edu/Terms/termSelect?term=20191')
	browser.get('https://webreg.usc.edu/myCourseBin')
	return browser

def sendEmail(content, to):
    message = MIMEText(content, 'plain', 'utf-8')
    message['From'] = "USC Webreg Helper <{}>".format(from_addr)
    message['To'] = ",".join(to)
    message['Subject'] = "Section(s) Status Change " + time.strftime('%H:%M:%S', time.localtime(time.time()))
    try:
        smtpObj = smtplib.SMTP_SSL(smtp_server, 465)
        smtpObj.login(smtp_user, smtp_password)
        smtpObj.sendmail(from_addr, to, message.as_string())
        print("Email has been send successfully to " + to[0])
        if logging_enabled:
        	logger.info("Email has been send successfully to " + to[0])
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
			soup = BeautifulSoup(browser.page_source,"html.parser")
			# Reopen coursebin if not loaded successfully
			if not soup.find(class_="content-wrapper-coursebin"):
				browser.close()
				print("Cannot open Coursebin.\nReopenning...\n")
				if logging_enabled:
					logger.warning("Cannot open Coursebin. Reopenning...")
				break
			for session in sessions:
				courses.append(Course(session,soup,prev_statuses[session]))
			for course in courses:
				prev_statuses[course.session_] = True if course.status else False
				if course.status != course.prev_status:
					content += course.str(1)
				if logging_enabled:
					logger.info(course.str(2))
			if content:
				if mode == 0:
					sendEmail(content, to_addr)
				elif mode == 1:
					api_url = "https://maker.ifttt.com/trigger/{}/with/key/{}".format(event_name, key)
					r = requests.post(api_url, data={'value1': content})
					print(r.text)
					if logging_enabled:
						logger.info(r.text)
				else:
					sendEmail(content, to_addr)
					api_url = "https://maker.ifttt.com/trigger/{}/with/key/{}".format(event_name, key)
					r = requests.post(api_url, data={'value1': content})
					print(r.text)
					if logging_enabled:
						logger.info(r.text)
			time.sleep(update_interval)
			browser.refresh()

if __name__ == '__main__':
	main()