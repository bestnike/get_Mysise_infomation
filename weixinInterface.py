# -*- coding: gb2312 -*-
import hashlib
import web
import time
import os
import urllib2,urllib
from lxml import etree
import random
import pylibmc as memcache
import cookielib
import re


'''

���ڴ����һЩ˵����

	1����������SAE��MySQL�Ǹ��ѷ�����������Memcached ����ʱ�������ݿ⹦�ܣ�Memcached ֻ�����ƶ�
	
	2����SAE����ģ���¼������һЩ��ֵ����⣬ÿһ����ѧ������ϵͳ�ύ��ʱ�������������һ������룬ͨ���ڱ��ؿ�������
	�£�����벻��ÿ�ζ��仯������SAE�������ϣ��ύ��������ÿ�ζ���һ�����²����ǵ�����Щʱ��ģ���¼ʧ�ܵ�ԭ��ģ��
	��¼ʧ����ҳ�᷵��"���棡�㲻�Ǳ�վ��¼���û�"��Ŀǰ�ҵĽ��������������forѭ���ظ�ģ���¼��ȡcookie��ֱ����¼�ɹ�
	������ѭ����
	
	3��ѧ��ϵͳ������Щҳ��������studentid���ɵ���ַ����ҪcookeieҲ�ܷ���(���������Ϣҳ��)������Щҳ������Ҫcookie����
	���ʵ�ҳ��(����α�ҳ��)���Ե���ѧ��ʱ���Ȼ�ȡstudentid��cookie���ٰ�ѧ�š����롢studentid��cookeie�洢�����ݿ��У�
	�����û���ѯ����������Ŀ���Ǽ���ÿһ�β�ѯ��Ҫ����һ��ģ���¼�ӿ���ȡ��Ϣ�ٶȣ���cookeie���ں���Զ����»�ȡcookie��
	�Զ����µ����ݿ�
	
	4������Python�������⣬Python���ڲ�Ϊunicode���룬��ȡ����ѧ��ϵͳ��ҳ��gbk���룬��Ҫ������decode("gbk") תΪunicode
	���룬�����ַ�����������ʱҲ��Ҫ�ڲ��ҹؼ���ǰ���u������str.find(u"����")����������Ҫ��ע�⣬��SAE��������Ŵ�ֻ��
	�﷨����֮������ش���ſ������������������Ӧ�õ�ַ�鿴������Ϣ������������ᵼ��΢�Ź��ں�ֱ�Ӳ���Ӧ���������
	Ҳ�Ҳ���������Ϣ

'''

url_class = u'http://class.sise.com.cn:7001/sise/module/student_schedular/student_schedular.jsp'
url_main = u'http://class.sise.com.cn:7001/sise/module/student_states/student_select_class/main.jsp'
mc = memcache.Client()

#ģ���¼��ȡcookie
def get_cookie(username,password):

	#�����cookie��opener
	c = cookielib.LWPCookieJar()
	cookie = urllib2.HTTPCookieProcessor(c)
	opener = urllib2.build_opener(cookie,urllib2.HTTPHandler)
	urllib2.install_opener(opener)
 
	path="http://class.sise.com.cn:7001/sise/login_check_login.jsp"

	data={}

	headers={	
				'Host': 'class.sise.com.cn:7001',
				'Content-Type': 'application/x-www-form-urlencoded',
				'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/61.0.3163.100 Safari/537.36',
				'Referer': 'http://class.sise.com.cn:7001/sise/'
			}
	
	#��ȡ�����
	hidden_html = opener.open('http://class.sise.com.cn:7001/sise/').read()
	hidden_list = re.findall(r'"([\w]{32})"',hidden_html)
	
	#�����
	data[hidden_list[0]]=hidden_list[1]
	data['username'] = username
	data['password'] = password
	
	#ģ���¼
	data = urllib.urlencode(data)
	req = urllib2.Request(path,headers=headers)
	html = urllib2.urlopen(req, data=data).read().decode('gbk')
	
	#ģ���¼ʧ���򷵻�"failure"���ɹ��򷵻�cookie
	if re.findall(r'parent.window.opener',html):
		return "failure"
	return c

def for_get_cookie(username,password):
	for i in range(5):
		cookie = get_cookie(username,password)
		if cookie != "failure":
			break
	return cookie
	
	
#����cookie��ȡHTMLҳ��	
def get_htmlc(c,url):
	cookie = urllib2.HTTPCookieProcessor(c)
	opener = urllib2.build_opener(cookie,urllib2.HTTPHandler)
	urllib2.install_opener(opener)
	str_html = opener.open(url).read().decode('gbk')
	
	#���cookeieʧЧ���򷵻�ʧ��
	if re.findall(r"/sise/login.jsp",str_html):
		return "failure"
	return str_html

#����cookeie��ȡѧ��id�ţ����ڻ�ȡϵͳѧ����Ϣ
def get_studentid(cookie,url):
	main_html = get_htmlc(cookie,url)
	studentid = re.findall(r'&studentid=(.*?)=\'\"',main_html)[0]
	studentid_exam = re.findall(r'&studentid=(.*?)\'\"',main_html)[1]
	
	return studentid,studentid_exam

#��ȡϵͳѧ����Ϣ����ҳ������studentid��ȡ
def get_info(studentid):
	url_info = u'http://class.sise.com.cn:7001/SISEWeb/pub/course/courseViewAction.do?method=doMain&studentid={}='.format(studentid)
	req = urllib2.Request(url_info)
	html = urllib2.urlopen(req).read().decode('gbk')
	
	key_list = re.findall(r'<div align="left">.(.+?).</div>',html,re.S)
	#ȥ�����з����Ʊ����ʹ��ʽ����
	for i in range(len(key_list)):
		key_list[i] = key_list[i].replace('\n','').replace(u'\t','')
	return key_list
	

#��ȡ�γ̱���Ϣ
def get_class(fromUser,cookie,url,wk):
	global mc
	html = get_htmlc(cookie,url)
	
	#���cookieʧЧ�������»�ȡ������ȡ5�Σ�����cookie���������ݿ�
	if html == "failure":
		mc_data = mc.get(fromUser)
		cookie = for_get_cookie(mc_data[0],mc_data[1])
		mc_data[4] = cookie
		mc.set(fromUser,mc_data)
		html = get_htmlc(cookie,url)
	classlist = re.findall(r"valign='top' class='font12'>(.+?)</td>",html)
	classdict = {
					"1":[""]*8,
					"2":[""]*8,
					"3":[""]*8,
					"4":[""]*8,
					"5":[""]*8
				}
	#�Ѹ����ڵĿα����洢���ֵ�
	for i in range(64):
		num = i%8
		if num == 1:
			classdict["1"][i/8] = classlist[i]#����һ�α�
		elif num == 2:
			classdict["2"][i/8] = classlist[i]#���ڶ��α�
		elif num == 3:
			classdict["3"][i/8] = classlist[i]#�������α�
		elif num == 4:
			classdict["4"][i/8] = classlist[i]#�����Ŀα�
		elif num == 5:
			classdict["5"][i/8] = classlist[i]#������α�
	j = 0
	str_class_time = [u"-   -   -   -   -   -   -   -   -   -   -   -   -   -   -   -   -\n��1 - 2 ��09:00 - 10:20��\n",u"��3 - 4 ��10:40 - 12:00��\n",u"-   -   -   -   -   -   -   -   -   -   -   -   -   -   -   -   -\n��5 - 6 ��12:30 - 13:50��\n",u"��7 - 8 ��14:00 - 15:20��\n",u"��9 - 10 ��15:30 - 16:50��\n",u"��11 - 12 ��17:00 - 18:20��\n",u"-   -   -   -   -   -   -   -   -   -   -   -   -   -   -   -   -\n��13 - 14 ��19:00 - 20:20��\n",u"��15 - 16 ��20:30 - 21:50��\n"]
	str_class = ""
	for i in classdict[wk]:
		if i != u"&nbsp;":
			str_class = str_class + str_class_time[j] + i + '\n'
		j = j+1
	return str_class

#��ȡ����ʱ�����ҳ������studenid_exam��ȡ������ʱ������ȡ
def get_exam(studentid_exam):
	url_exam = u"http://class.sise.com.cn:7001/SISEWeb/pub/exam/studentexamAction.do?method=doMain&studentid={}".format(studentid_exam)
	req = urllib2.Request(url_exam)
	html = urllib2.urlopen(req).read().decode('gbk')
	
	return html

#��ȡ������Ϣ����ҳ������studenid��ȡ��������Ϣ����ȡ
def get_AttendenceRecord(studentid):
	url_attendence = u"http://class.sise.com.cn:7001/SISEWeb/pub/studentstatus/attendance/studentAttendanceViewAction.do?method=doMain&studentID={}=&gzcode=%2BKffjkRBcyfEhrrLLkc9Tw==".format(studentid)
	req = urllib2.Request(url_attendence)
	html = urllib2.urlopen(req).read().decode('gbk')
	
	return html
	

#��΢�ŷ����࣬���ڴ���΢�Ź��ںŵ�get��post����
class WeixinInterface:
	
	global url_class
	global url_main
	global mc
	
	def __init__(self):
		self.app_root = os.path.dirname(__file__)
		self.templates_root = os.path.join(self.app_root, 'templates')
		self.render = web.template.render(self.templates_root)

	#GET����������֤token
	def GET(self):

		data = web.input()
		signature=data.signature
		timestamp=data.timestamp
		nonce=data.nonce
		echostr=data.echostr
		#token ��Ҫ��΢�Ź��ںŵ�һ��
		token="javatoken"

		list=[token,timestamp,nonce]
		list.sort()
		sha1=hashlib.sha1()
		map(sha1.update,list)
		hashcode=sha1.hexdigest()

		if hashcode == signature:
			return echostr
	
	#POST�������ڴ���΢���û�������
	def POST(self):      
		data_time=str(time.strftime('%Y-%m-%d',time.localtime(time.time())))
		week = str(time.strftime('%w',time.localtime(time.time())))
		week_u = str(int(time.strftime('%W',time.localtime(time.time())))-35)
		str_xml = web.data() #���post��������
		xml = etree.fromstring(str_xml)#����XML����
		
		#��ȡ�û�������Ϣ
		msgType=xml.find("MsgType").text	
		fromUser=xml.find("FromUserName").text
		toUser=xml.find("ToUserName").text
		

		
		#�¼������
		if msgType == "event":
			mscontent = xml.find("Event").text
			
			#��ע�¼�
			if mscontent == "subscribe":
				replayText = u'''��ӭ��ע��΢�ţ��ظ�help�鿴���ʹ�ð���'''
				return self.render.reply_text(fromUser,toUser,int(time.time()),replayText)
			
		#��Ϣ�����
		elif msgType == "text":
			content=xml.find("Content").text#��ȡ��Ϣ�ľ�������
			
			#��ȡ������ʱ��
			if content == "time":
				return self.render.reply_text(fromUser,toUser,int(time.time()),data_time)
			
			#����
			elif content == "music":
				musicList =  [
								 [r'http://bcs.duapp.com/yangyanxingblog3/music/destiny.mp3','Destiny',u'for my love'],
								 [r'http://bcs.duapp.com/yangyanxingblog3/music/5days.mp3','5 Days',u'for my love'],
								 [r'http://bcs.duapp.com/yangyanxingblog3/music/Far%20Away%20%28Album%20Version%29.mp3','Far Away (Album Version)',u'for my love']
							 ]
				music=random.choice(musicList)
				musicurl = music[0]
				musictitle = music[1]
				musicdes =music[2]
				return self.render.reply_music(fromUser,toUser,int(time.time()),musictitle,musicdes,musicurl)
			
			#������Ϣ
			elif content == "help":
				help = u"�α�\n��Ϣ�鿴\n������ֵ"
				return self.render.reply_new(fromUser,toUser,int(time.time()),u"�ظ�һ�¹ؼ��ֻ�ȡ��Ӧ����",help)
			
			elif content == "week":
				return self.render.reply_text(fromUser,toUser,int(time.time()),week_u)
			#���ѳ�ֵ
			elif content == u"���ѳ�ֵ":
				return self.render.reply_url(fromUser,toUser,int(time.time()),u"�ֻ������ѳ�ֵ",u"��ʾ��ѧ���ż�ѧ��",u"http://ecard.scse.com.cn:8070/AutoPay/NetFee/Index")
			
			#�ֻ��淹����ֵ
			elif content == u"������ֵ":
				return self.render.reply_url(fromUser,toUser,int(time.time()),u"�ֻ��淹����ֵ",u"��ʾ��ѧ���ż�ѧ��",u"http://ecard.scse.com.cn:8070/")
			
			mc_data = mc.get(fromUser)
			
			#��ȡ�û���Ӧ���ݿ����Ϣ
			if mc_data:
				username = mc_data[0]
				password = mc_data[1]
				studentid = mc_data[2]
				studentid_exam = mc_data[3]
				cookie = mc_data[4]
			
			#������
			if content == "test":
				printtest = for_get_cookie(username,password)
				
				return self.render.reply_new(fromUser,toUser,int(time.time()),u"��������",printtest)
			
			
			if content[:2] == u"�α�":
				#�ж��Ƿ��Ѱ�ѧ��
				if not mc_data:
					return self.render.reply_text(fromUser,toUser,int(time.time()),u"���Ȱ�ѧ�ţ��󶨸�ʽ���ÿո���������� ѧ�� Mysise����\n������ 123456789 123")
				else:
					week2chana = [u"",u"һ",u"��",u"��",u"��",u"��"]
					if content[2:3] == "6" or content[2:3] == "7":
						return self.render.reply_text(fromUser,toUser,int(time.time()),u"��ĩû�пΣ������Լ�ϲ��������ɣ�")
					
					elif content[2:3]:
						str_print = get_class(fromUser,cookie,url_class,content[2:3])
						return self.render.reply_new(fromUser,toUser,int(time.time()),u"�����ǵ�"+week_u+u"��  \n"+u"���ѯ������"+week2chana[int(content[2:3])]+u"�α�����",u'��ѯ��ʽΪ��\n�ظ�"�α�"�ɻ�ȡ���տα��磺�α�\n�ظ�"�α�"+����1~5�ɻ�ȡ��Ӧ���������Ŀα��磺�α�5\n\n'+str_print)
					
					elif week == "6" or week == "0":
						return self.render.reply_text(fromUser,toUser,int(time.time()),u"������ĩ�������Լ�ϲ��������ɣ�")
				
					else:
						str_print = get_class(fromUser,cookie,url_class,week)
						return self.render.reply_new(fromUser,toUser,int(time.time()),u"�����ǵ�"+week_u+u"��  \n"+u"����������"+week2chana[int(week)]+u"  ���տα�Ϊ��",u'��ѯ��ʽΪ��\n�ظ�"�α�"�ɻ�ȡ���տα��磺�α�\n�ظ�"�α�"+����1~5�ɻ�ȡ��Ӧ���������Ŀα��磺�α�5\n\n'+str_print)
			#�鿴ѧ��ϵͳ������Ϣ
			elif content == u"��Ϣ�鿴":
				if not mc_data:
					return self.render.reply_text(fromUser,toUser,int(time.time()),u"���Ȱ�ѧ�ţ��󶨸�ʽ���� ѧ�� Mysise����")
				else:
					info = get_info(studentid)
					return self.render.reply_new(fromUser,toUser,int(time.time()),u"��Ϣ���ҳɹ�",u"������"+info[2]+u"\nѧ�ţ�"+username+u"\n�꼶��"+info[3]+u"\nרҵ��"+info[4]+u"\n�������䣺"+info[6]+u"\n��ʦ��"+info[7]+u"\n����Ա��"+info[8])
			
			#��ѧ��
			elif content[:2]== u"��":
				#�ָ��ѧ�ź�����
				content=content.split()
				
				#ѭ��ģ���¼��ȡcookeie,cookie��Ч������
				cookie = for_get_cookie(content[1],content[2])

				#��ȡstudentid
				studentid,studentid_exam = get_studentid(cookie,url_main)
				
				#�ѻ�ȡ����ѧ�š����롢studentid��cookie���ֵ�Ƕ���б�ķ�ʽ�洢�����ݿ⣬�ֵ�ؼ���ΪfromUser��fromUser�Ǳ�ʶ�û��ı�־
				if studentid:
					#�ж��Ƿ��״ΰ�
					if mc_data:
						mc.set(fromUser,[content[1],content[2],studentid,studentid_exam,cookie])
						info = get_info(studentid)
						return self.render.reply_new(fromUser,toUser,int(time.time()),u"���°���Ϣ�ɹ�",u"���û���"+info[2]+u"\n��������ظ�: ���\n")
					else:
						mc.set(fromUser,[content[1],content[2],studentid,studentid_exam,cookie])
						info = get_info(studentid)
						return self.render.reply_new(fromUser,toUser,int(time.time()),u"�󶨳ɹ�",u"���û���"+info[2]+u"\n��������ظ�: ���")
				
				else:
					return self.render.reply_text(fromUser,toUser,int(time.time()),u"��ʧ��")
		
			#ɾ����Ӧ�û������ݿ���Ϣ
			elif content == u"���":
				if mc_data:
					mc.delete(fromUser)
					return self.render.reply_text(fromUser,toUser,int(time.time()),u"���ɹ�")
				else:
					return self.render.reply_text(fromUser,toUser,int(time.time()),u"û�а�")
			
			#������Ϣ
			else:	
				return self.render.reply_new(fromUser,toUser,int(time.time()),u"��û���壬��ղ�˵ʲô??�ظ�help��һ��",u"�����ʺ�.jpg")
				

	