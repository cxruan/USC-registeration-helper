from selenium import webdriver
from bs4 import BeautifulSoup
import time
import logging
import smtplib
from email.header import Header
from email.mime.text import MIMEText
import configparser
import ast

# Configuration
cf = configparser.ConfigParser()
cf.read("./config.ini")
sessions = ast.literal_eval(cf['session']['sessions'])
usc_username = cf['usc']['usc_username']
usc_password = cf['usc']['usc_password']
smtp_server = cf['smtp']['smtp_server']
smtp_user = cf['smtp']['smtp_user']
smtp_password = cf['smtp']['smtp_password']
from_addr = cf['email']['from_addr']
to_addr = [cf['email']['to_addr']]


class Course:
	session_ = ""
	type_ = ""
	time_ = ""
	days_ = ""
	instr_ = ""
	regSeats_ = ""
	is_open = False

	def __init__(self, session, soup_data):
		target = soup_data.find(id="section_"+session).find(attrs={"style":"padding:0;border-top: solid 1px #F2F1F1;"})
		self.session_ = session
		self.type_ = target.find(class_="type_alt1").get_text() if target.find(class_="type_alt1") else target.find(class_="type_alt0").get_text()
		self.time_ = target.find(class_="hours_alt1").get_text() if target.find(class_="hours_alt1") else target.find(class_="hours_alt0").get_text()
		self.days_ = target.find(class_="days_alt1").get_text() if target.find(class_="days_alt1") else target.find(class_="days_alt0").get_text()
		self.instr_ = target.find(class_="instr_alt1").get_text() if target.find(class_="instr_alt1") else target.find(class_="instr_alt0").get_text()
		self.regSeats_ = target.find(class_="regSeats_alt1").get_text() if target.find(class_="regSeats_alt1") else target.find(class_="regSeats_alt0").get_text()
		if not target.find(style="color:#ff0000 ;"):
			self.is_open = True;

	def str(self,k):
		if(k==1):
			return "Session: "+self.session_+"\n"+self.type_+"\n"+self.time_+"\n"+self.days_+"\n"+self.instr_+"\n"+self.regSeats_+"\n"
		elif(k==2):
			return "Session: "+self.session_+" "+self.regSeats_
		else:
			return "So such option"

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
	time.sleep(2)
	browser.get('https://my.usc.edu/portal/oasis/webregbridge.php')
	time.sleep(2)
	browser.get('https://webreg.usc.edu/Terms/termSelect?term=20191')
	time.sleep(2)
	browser.get('https://webreg.usc.edu/myCourseBin')
	return browser

def sendEmail(content):
    message = MIMEText(content, 'plain', 'utf-8')
    message['From'] = "USC Webreg Helper <{}>".format(from_addr)
    message['To'] = ",".join(to_addr)
    message['Subject'] = "A course is open now!"
    try:
        smtpObj = smtplib.SMTP_SSL(smtp_server, 465)
        smtpObj.login(smtp_user, smtp_password)
        smtpObj.sendmail(from_addr, to_addr, message.as_string())
        print("Email has been send successfully.")
    except smtplib.SMTPException as e:
        print(e)	

def main():
	# Configure logging
	logger = logging.getLogger()
	logger.setLevel(logging.INFO)
	rq = time.strftime('%Y%m%d%H%M', time.localtime(time.time()))
	log_path = './'
	log_name = rq + '.log'
	fh = logging.FileHandler(log_name, mode='w')
	fh.setLevel(logging.DEBUG)
	formatter = logging.Formatter("%(asctime)s - %(filename)s - %(levelname)s: %(message)s")
	fh.setFormatter(formatter)
	logger.addHandler(fh)

	while True:
		browser = land_in_coursebin()
		while True:
			courses = []		
			soup = BeautifulSoup(browser.page_source,"html.parser")
			# Reopen coursebin if not loaded successfully
			if not soup.find(class_="content-wrapper-coursebin"):
				browser.close()
				print("Cannot open Coursebin.\nReopenning...\n")
				break
			for session in sessions:
				courses.append(Course(session,soup))
			for course in courses:
				if course.is_open:
					sendEmail(course.str(1))
				logger.info(course.str(2))
			print(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())))
			time.sleep(10)
			browser.refresh()
main()