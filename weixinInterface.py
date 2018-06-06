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

关于代码的一些说明：

	1、由于新浪SAE的MySQL是付费服务，所以利用Memcached 来暂时代替数据库功能，Memcached 只消耗云豆
	
	2、在SAE上面模拟登录会遇到一些奇怪的问题，每一次向学生管理系统提交表单时，表单里面包含有一个随机码，通常在本地开发环境
	下，随机码不会每次都变化，但在SAE服务器上，提交的随机码会每次都不一样，猜测这是导致有些时候模拟登录失败的原因，模拟
	登录失败网页会返回"警告！你不是本站登录的用户"，目前我的解决方法就是利用for循环重复模拟登录获取cookie，直到登录成功
	才跳出循环。
	
	3、学生系统里面有些页面是利用studentid构成的网址不需要cookeie也能访问(例如个人信息页面)，而有些页面则需要cookie才能
	访问的页面(例如课表页面)所以当绑定学号时，先获取studentid和cookie，再把学号、密码、studentid、cookeie存储在数据库中，
	方便用户查询，这样做的目的是减少每一次查询都要进行一次模拟登录加快提取信息速度，当cookeie过期后会自动重新获取cookie，
	自动更新到数据库
	
	4、关于Python编码问题，Python的内部为unicode编码，获取到的学生系统网页是gbk编码，需要把利用decode("gbk") 转为unicode
	编码，进行字符串查找中文时也需要在查找关键词前面加u，例如str.find(u"中文")，编码问题要很注意，在SAE上面很难排错，只有
	语法问题之类的严重错误才可以在浏览器上面打开你的应用地址查看报错信息，编码问题则会导致微信公众号直接不响应，浏览器上
	也找不到报错信息

'''

url_class = u'http://class.sise.com.cn:7001/sise/module/student_schedular/student_schedular.jsp'
url_main = u'http://class.sise.com.cn:7001/sise/module/student_states/student_select_class/main.jsp'
mc = memcache.Client()

#模拟登录获取cookie
def get_cookie(username,password):

	#构造带cookie的opener
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
	
	#获取随机码
	hidden_html = opener.open('http://class.sise.com.cn:7001/sise/').read()
	hidden_list = re.findall(r'"([\w]{32})"',hidden_html)
	
	#构造表单
	data[hidden_list[0]]=hidden_list[1]
	data['username'] = username
	data['password'] = password
	
	#模拟登录
	data = urllib.urlencode(data)
	req = urllib2.Request(path,headers=headers)
	html = urllib2.urlopen(req, data=data).read().decode('gbk')
	
	#模拟登录失败则返回"failure"，成功则返回cookie
	if re.findall(r'parent.window.opener',html):
		return "failure"
	return c

def for_get_cookie(username,password):
	for i in range(5):
		cookie = get_cookie(username,password)
		if cookie != "failure":
			break
	return cookie
	
	
#利用cookie获取HTML页面	
def get_htmlc(c,url):
	cookie = urllib2.HTTPCookieProcessor(c)
	opener = urllib2.build_opener(cookie,urllib2.HTTPHandler)
	urllib2.install_opener(opener)
	str_html = opener.open(url).read().decode('gbk')
	
	#如果cookeie失效，则返回失败
	if re.findall(r"/sise/login.jsp",str_html):
		return "failure"
	return str_html

#利用cookeie获取学生id号，用于获取系统学生信息
def get_studentid(cookie,url):
	main_html = get_htmlc(cookie,url)
	studentid = re.findall(r'&studentid=(.*?)=\'\"',main_html)[0]
	studentid_exam = re.findall(r'&studentid=(.*?)\'\"',main_html)[1]
	
	return studentid,studentid_exam

#获取系统学生信息，该页面利用studentid获取
def get_info(studentid):
	url_info = u'http://class.sise.com.cn:7001/SISEWeb/pub/course/courseViewAction.do?method=doMain&studentid={}='.format(studentid)
	req = urllib2.Request(url_info)
	html = urllib2.urlopen(req).read().decode('gbk')
	
	key_list = re.findall(r'<div align="left">.(.+?).</div>',html,re.S)
	#去掉换行符和制表符，使格式整齐
	for i in range(len(key_list)):
		key_list[i] = key_list[i].replace('\n','').replace(u'\t','')
	return key_list
	

#获取课程表信息
def get_class(fromUser,cookie,url,wk):
	global mc
	html = get_htmlc(cookie,url)
	
	#如果cookie失效，则重新获取，最多获取5次，最后把cookie更新在数据库
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
	#把各星期的课表归类存储到字典
	for i in range(64):
		num = i%8
		if num == 1:
			classdict["1"][i/8] = classlist[i]#星期一课表
		elif num == 2:
			classdict["2"][i/8] = classlist[i]#星期二课表
		elif num == 3:
			classdict["3"][i/8] = classlist[i]#星期三课表
		elif num == 4:
			classdict["4"][i/8] = classlist[i]#星期四课表
		elif num == 5:
			classdict["5"][i/8] = classlist[i]#星期五课表
	j = 0
	str_class_time = [u"-   -   -   -   -   -   -   -   -   -   -   -   -   -   -   -   -\n【1 - 2 】09:00 - 10:20：\n",u"【3 - 4 】10:40 - 12:00：\n",u"-   -   -   -   -   -   -   -   -   -   -   -   -   -   -   -   -\n【5 - 6 】12:30 - 13:50：\n",u"【7 - 8 】14:00 - 15:20：\n",u"【9 - 10 】15:30 - 16:50：\n",u"【11 - 12 】17:00 - 18:20：\n",u"-   -   -   -   -   -   -   -   -   -   -   -   -   -   -   -   -\n【13 - 14 】19:00 - 20:20：\n",u"【15 - 16 】20:30 - 21:50：\n"]
	str_class = ""
	for i in classdict[wk]:
		if i != u"&nbsp;":
			str_class = str_class + str_class_time[j] + i + '\n'
		j = j+1
	return str_class

#获取考试时间表，该页面利用studenid_exam获取，考试时间表待提取
def get_exam(studentid_exam):
	url_exam = u"http://class.sise.com.cn:7001/SISEWeb/pub/exam/studentexamAction.do?method=doMain&studentid={}".format(studentid_exam)
	req = urllib2.Request(url_exam)
	html = urllib2.urlopen(req).read().decode('gbk')
	
	return html

#获取考勤信息，该页面利用studenid获取，考勤信息待提取
def get_AttendenceRecord(studentid):
	url_attendence = u"http://class.sise.com.cn:7001/SISEWeb/pub/studentstatus/attendance/studentAttendanceViewAction.do?method=doMain&studentID={}=&gzcode=%2BKffjkRBcyfEhrrLLkc9Tw==".format(studentid)
	req = urllib2.Request(url_attendence)
	html = urllib2.urlopen(req).read().decode('gbk')
	
	return html
	

#主微信服务类，用于处理微信公众号的get和post请求
class WeixinInterface:
	
	global url_class
	global url_main
	global mc
	
	def __init__(self):
		self.app_root = os.path.dirname(__file__)
		self.templates_root = os.path.join(self.app_root, 'templates')
		self.render = web.template.render(self.templates_root)

	#GET请求，用于验证token
	def GET(self):

		data = web.input()
		signature=data.signature
		timestamp=data.timestamp
		nonce=data.nonce
		echostr=data.echostr
		#token 需要与微信公众号的一致
		token="javatoken"

		list=[token,timestamp,nonce]
		list.sort()
		sha1=hashlib.sha1()
		map(sha1.update,list)
		hashcode=sha1.hexdigest()

		if hashcode == signature:
			return echostr
	
	#POST请求，用于处理微信用户的请求
	def POST(self):      
		data_time=str(time.strftime('%Y-%m-%d',time.localtime(time.time())))
		week = str(time.strftime('%w',time.localtime(time.time())))
		week_u = str(int(time.strftime('%W',time.localtime(time.time())))-35)
		str_xml = web.data() #获得post来的数据
		xml = etree.fromstring(str_xml)#进行XML解析
		
		#提取用户操作信息
		msgType=xml.find("MsgType").text	
		fromUser=xml.find("FromUserName").text
		toUser=xml.find("ToUserName").text
		

		
		#事件类操作
		if msgType == "event":
			mscontent = xml.find("Event").text
			
			#关注事件
			if mscontent == "subscribe":
				replayText = u'''欢迎关注本微信，回复help查看相关使用帮助'''
				return self.render.reply_text(fromUser,toUser,int(time.time()),replayText)
			
		#消息类操作
		elif msgType == "text":
			content=xml.find("Content").text#提取消息的具体内容
			
			#获取服务器时间
			if content == "time":
				return self.render.reply_text(fromUser,toUser,int(time.time()),data_time)
			
			#音乐
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
			
			#帮助信息
			elif content == "help":
				help = u"课表\n信息查看\n饭卡充值"
				return self.render.reply_new(fromUser,toUser,int(time.time()),u"回复一下关键字获取对应内容",help)
			
			elif content == "week":
				return self.render.reply_text(fromUser,toUser,int(time.time()),week_u)
			#网费充值
			elif content == u"网费充值":
				return self.render.reply_url(fromUser,toUser,int(time.time()),u"手机版网费充值",u"提示：学工号即学号",u"http://ecard.scse.com.cn:8070/AutoPay/NetFee/Index")
			
			#手机版饭卡充值
			elif content == u"饭卡充值":
				return self.render.reply_url(fromUser,toUser,int(time.time()),u"手机版饭卡充值",u"提示：学工号即学号",u"http://ecard.scse.com.cn:8070/")
			
			mc_data = mc.get(fromUser)
			
			#提取用户对应数据库的信息
			if mc_data:
				username = mc_data[0]
				password = mc_data[1]
				studentid = mc_data[2]
				studentid_exam = mc_data[3]
				cookie = mc_data[4]
			
			#测试用
			if content == "test":
				printtest = for_get_cookie(username,password)
				
				return self.render.reply_new(fromUser,toUser,int(time.time()),u"测试内容",printtest)
			
			
			if content[:2] == u"课表":
				#判断是否已绑定学号
				if not mc_data:
					return self.render.reply_text(fromUser,toUser,int(time.time()),u"请先绑定学号，绑定格式（用空格隔开）：绑定 学号 Mysise密码\n例：绑定 123456789 123")
				else:
					week2chana = [u"",u"一",u"二",u"三",u"四",u"五"]
					if content[2:3] == "6" or content[2:3] == "7":
						return self.render.reply_text(fromUser,toUser,int(time.time()),u"周末没有课，做点自己喜欢的事情吧！")
					
					elif content[2:3]:
						str_print = get_class(fromUser,cookie,url_class,content[2:3])
						return self.render.reply_new(fromUser,toUser,int(time.time()),u"这周是第"+week_u+u"周  \n"+u"你查询的星期"+week2chana[int(content[2:3])]+u"课表如下",u'查询格式为：\n回复"课表"可获取今日课表，如：课表\n回复"课表"+数字1~5可获取对应的星期数的课表，如：课表5\n\n'+str_print)
					
					elif week == "6" or week == "0":
						return self.render.reply_text(fromUser,toUser,int(time.time()),u"今天周末，做点自己喜欢的事情吧！")
				
					else:
						str_print = get_class(fromUser,cookie,url_class,week)
						return self.render.reply_new(fromUser,toUser,int(time.time()),u"这周是第"+week_u+u"周  \n"+u"今天是星期"+week2chana[int(week)]+u"  当日课表为：",u'查询格式为：\n回复"课表"可获取今日课表，如：课表\n回复"课表"+数字1~5可获取对应的星期数的课表，如：课表5\n\n'+str_print)
			#查看学生系统个人信息
			elif content == u"信息查看":
				if not mc_data:
					return self.render.reply_text(fromUser,toUser,int(time.time()),u"请先绑定学号，绑定格式：绑定 学号 Mysise密码")
				else:
					info = get_info(studentid)
					return self.render.reply_new(fromUser,toUser,int(time.time()),u"信息查找成功",u"姓名："+info[2]+u"\n学号："+username+u"\n年级："+info[3]+u"\n专业："+info[4]+u"\n华软邮箱："+info[6]+u"\n导师："+info[7]+u"\n辅导员："+info[8])
			
			#绑定学号
			elif content[:2]== u"绑定":
				#分割出学号和密码
				content=content.split()
				
				#循环模拟登录获取cookeie,cookie有效则跳出
				cookie = for_get_cookie(content[1],content[2])

				#获取studentid
				studentid,studentid_exam = get_studentid(cookie,url_main)
				
				#把获取到的学号、密码、studentid、cookie以字典嵌套列表的方式存储在数据库，字典关键字为fromUser，fromUser是标识用户的标志
				if studentid:
					#判断是否首次绑定
					if mc_data:
						mc.set(fromUser,[content[1],content[2],studentid,studentid_exam,cookie])
						info = get_info(studentid)
						return self.render.reply_new(fromUser,toUser,int(time.time()),u"更新绑定信息成功",u"绑定用户："+info[2]+u"\n如需解绑则回复: 解绑\n")
					else:
						mc.set(fromUser,[content[1],content[2],studentid,studentid_exam,cookie])
						info = get_info(studentid)
						return self.render.reply_new(fromUser,toUser,int(time.time()),u"绑定成功",u"绑定用户："+info[2]+u"\n如需解绑则回复: 解绑")
				
				else:
					return self.render.reply_text(fromUser,toUser,int(time.time()),u"绑定失败")
		
			#删除对应用户的数据库信息
			elif content == u"解绑":
				if mc_data:
					mc.delete(fromUser)
					return self.render.reply_text(fromUser,toUser,int(time.time()),u"解绑成功")
				else:
					return self.render.reply_text(fromUser,toUser,int(time.time()),u"没有绑定")
			
			#其他消息
			else:	
				return self.render.reply_new(fromUser,toUser,int(time.time()),u"我没听清，你刚才说什么??回复help试一下",u"黑人问号.jpg")
				

	