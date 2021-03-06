# -*- coding: utf-8 -*-
import math
import zlib
import base64
import thread
import urllib
import urllib2
import socket
import sqlite3

from funcs import *

from PIL import Image

import twisted
from twisted.web import static, server, resource
from twisted.internet import reactor

class P2PChanWeb(resource.Resource):
  isLeaf = True
  conn = sqlite3.connect(localFile('posts.db'))

  def __init__(self, p2pchan, stylesheet):
    self.p2pchan = p2pchan
    self.stylesheet = stylesheet

  def render_GET(self, request):
    if getRequestPath(request).startswith('/manage'):
      return self.renderManage(request)
    elif getRequestPath(request).startswith('/image'):
      return self.renderImage(request)
    else:
      return self.renderNormal(request)

  def render_POST(self, request):
    if getRequestPath(request).startswith('/manage'):
      return self.renderManage(request)
    else:
      return self.renderNormal(request)

  def renderImage(self, request):
    lnk = getRequestPath(request).replace('/image/', '')
    c = self.conn.cursor()
    if lnk.startswith('thumb/'):
      lnk = lnk.replace('thumb/', '')
      c.execute('select thumb from posts where guid = \'' + lnk + '\'')
    else:
      c.execute('select file from posts where guid = \'' + lnk + '\'')
    outputraw = ''
    output = ''
    for row in c:
      outputraw += row[0]
    try:
      output = base64.decodestring(outputraw)
      imageinfo = getImageInfo(output)
      if 'image/jpeg' in imageinfo[0]:
        request.setHeader("content-type", "image/jpeg")
      elif 'image/png' in imageinfo[0]:
        request.setHeader("content-type", "image/png")
      elif 'image/gif' in imageinfo[0]:
        request.setHeader("content-type", "image/gif")
    except:
      print 'Not an image'
      output = outputraw
    return output

  def renderNormal(self, request):
    replyto = False
    page = numpages = 0
    c = self.conn.cursor()
    c2 = self.conn.cursor()
    c3 = self.conn.cursor()
    request_path = getRequestPath(request)
    text = ""
    if 'message' in request.args:
      hostresponse = ['','']

      if 'file' in request.args:
        if request.args['file'][0] != '':
          imageinfo = getImageInfo(request.args['file'][0])
          if len(request.args['file'][0]) > 524288: #if image is greater than limit
            return formatError('You must upload an image, which size is lower than 512 KBytes')
          if 'image/jpeg' in imageinfo[0] or 'image/png' in imageinfo[0] or 'image/gif' in imageinfo[0]:
            io = StringIO(request.args['file'][0])
            img = Image.open(io)
            if img.size[0] > 200 or img.size[1] > 200: # downscale
              if img.size[1] > img.size[0]:
                newX = img.size[0] / (img.size[1] / 200.0)
                newY = 200
              else:
                newY = img.size[1] / (img.size[0] / 200.0)
                newX = 200
            else:
              newX = img.size[0]
              newY = img.size[1]
            img = img.resize((int(newX), int(newY)), Image.ANTIALIAS)
            io = StringIO()
            if 'image/jpeg' in imageinfo[0]:
              img.save(io, "JPEG")
            elif 'image/png' in imageinfo[0]:
              img.save(io, "PNG")
            elif 'image/gif' in imageinfo[0]:
              img.save(io, "GIF")

            hostresponse[0] = base64.encodestring(request.args['file'][0])
            hostresponse[1] = base64.encodestring(io.getvalue())
          else:
            return formatError('Invalid file format')

      if request.args['parent'][0] == "" and hostresponse == ['','']:
        return formatError('You must upload an image to start a new thread')
      if request.args['parent'][0] != "" and hostresponse == ['',''] and request.args['message'][0] == '':
        return formatError('You must upload an image or enter a message to reply to a thread')

      request.args['message'][0] = request.args['message'][0][0:4096] #truncates message

      post = [newGUID(),
              request.args['parent'][0],
              str(timestamp()),
              str(timestamp()),
              request.args['name'][0],
              request.args['email'][0],
              request.args['subject'][0],
              '',
              '',
              request.args['message'][0]]
      post = decodePostData(toEntity(encodePostData(post))) # Encode utf-8 to HTML entitys

      c.execute("insert into posts values ('" + "', '".join(post) + "')")

      c.execute("update posts set file = ? where guid = '" + post[0] + "'", [hostresponse[0]])
      c.execute("update posts set thumb = ? where guid = '" + post[0] + "'", [hostresponse[1]])

      post[7] = hostresponse[1]
      post[8] = hostresponse[0]

      if post[1] != "" and post[5].lower() != 'sage':
        c.execute("update posts set bumped = '" + post[2] + "' where guid = '" + post[1] + "'")
      self.conn.commit()
      self.p2pchan.kaishi.sendData('POST', encodePostData(post))

      if request.args['parent'][0] == '':
        return '<meta http-equiv="refresh" content="1;URL=/">--&gt; --&gt; --&gt;'
      else:
        return '<meta http-equiv="refresh" content="1;URL=/?res=' + request.args['parent'][0] + '">--&gt; --&gt; --&gt;'
    else:
      if 'res' in request.args:
        replyto = request.args['res'][0]
        c.execute('select * from posts where guid = \'' + request.args['res'][0] + '\' limit 1')
        for post in c:
          text += buildPost(post, self.conn, -1)
        c.execute('select * from posts where parent = \'' + request.args['res'][0] + '\' order by timestamp asc')
        for post in c:
          text += buildPost(post, self.conn, -1)
      else:
        c.execute('select count(*) from posts where parent = \'\'')
        for row in c:
          numpages = int(math.ceil(float(int(row[0])) / float(int(self.p2pchan.postsperpage))))

        if 'ind' in request.args:
          page = request.args['ind'][0]

        c.execute('select * from posts where parent = \'\' order by bumped desc limit ' + str(self.p2pchan.postsperpage) + ' offset ' + str(int(self.p2pchan.postsperpage) * int(page)))
        for post in c:
          c2.execute('select count(*) from hiddenposts where guid = \'' + post[0] + '\'')
          for row in c2:
            if row[0] == 0:
              c3.execute('select count(*) from posts where parent = \'' + post[0] + '\'')
              for row in c3:
                numreplies = row[0]

              text += buildPost(post, self.conn, numreplies)

              replies = ''
              if numreplies > 0:
                c3.execute('select * from posts where parent = \'' + post[0] + '\' order by timestamp desc limit 5')
                for reply in c3:
                  replies = buildPost(reply, self.conn, 0) + replies

              text += replies + '<br clear="left"><hr>'

    return renderPage(text, self.p2pchan, self.stylesheet, replyto, page, numpages)

  def renderManage(self, request):
    replyto = False
    c = self.conn.cursor()
    request_path = getRequestPath(request)
    text = ''
    if 'getthread' in request.args:
      self.p2pchan.kaishi.sendData('THREAD', request.args['getthread'][0])
      text += 'Sent thread request. <a href="/?res=' + request.args['getthread'][0] + '">Go to thread</a>'
    elif 'fetchthreads' in request.args:
      self.p2pchan.kaishi.sendData('THREADS', "")
      text += 'Sent thread fetch request.'
    elif 'hide' in request.args and 'post' in request.args:
      if not os.path.isfile(localFile('servermode')):
        c = self.conn.cursor()
        c.execute('select count(*) from hiddenposts where guid = \'' + request.args['post'][0] + '\'')
        for row in c:
          if row[0] == 0:
            c.execute('insert into hiddenposts values (\'' + request.args['post'][0] + '\')')
            self.conn.commit()
            text += 'Post hidden.'
          else:
            text += 'That post has already been hidden.'
    elif 'refresh' in request.args and 'post' in request.args:
      self.p2pchan.kaishi.sendData('THREAD', request.args['post'][0])
      text += 'Sent thread request. You will be redirected to the thread in a few seconds.<meta http-equiv="refresh" content="5;URL=/?res=' + request.args['post'][0] + '">'
    elif 'unhide' in request.args:
      c = self.conn.cursor()
      c.execute('delete from hiddenposts where guid = \'' + request.args['unhide'][0] + '\'')
      self.conn.commit()
    elif 'peers' in request.args:
      self.p2pchan.kaishi.fetchPeersFromProvider()
      text += 'Refreshed peer provider.'

    if text == '':
      text += """<table width="100%" border="0"><tr width="100%"><td width="50%">
      <form action="/manage" method="get">
      <fieldset>
      <legend>
      Fetch Full Thread
      </legend>
      <label for="getthread">Thread Identifier:</label> <input type="text" name="getthread"><br>
      <input type="submit" value="Fetch Thread" class="managebutton">
      </fieldset>
      </form>
      <fieldset>
      <legend>
      Hidden Posts
      </legend>"""
      c.execute('select count(*) from hiddenposts')
      for row in c:
        if row[0] > 0:
          c.execute('select * from hiddenposts order by guid asc')
          text += 'Click a post\'s guid to unhide it:'
          for row in c:
            text += '<br><a href="/manage?unhide=' + row[0] + '">' + row[0] + '</a>'
        else:
          text += 'You are not hiding any posts.'
      text += """
      </fieldset>
      <fieldset>
      <legend>
      Fetch Missing Threads
      </legend>"""
      missingthreads = []
      c = self.conn.cursor()
      c2 = self.conn.cursor()
      c.execute('select * from posts where parent != \'\'')
      for post in c:
        c2.execute('select count(*) from posts where guid = \'' + post[1] + '\'')
        for row in c2:
          if row[0] == 0 and post[1] not in missingthreads:
            missingthreads.append(post[1])
      if len(missingthreads) > 0:
        text += "You have " + str(len(missingthreads)) + " missing threads:"
        for missingthread in missingthreads:
          text += '<br>' + missingthread + ' - <a href="/manage?getthread=' + missingthread + '">Request thread</a>'
      else:
        text += "If you receive a reply to a thread which you do not yet have, it will appear in this list."
      text += """<br><br>
      Alternatively, you can send out a request for some of the latest threads which you have not yet received any replies for:<br>
      <form action="/manage" method="get"><input type="submit" name="fetchthreads" value="Fetch Threads" class="managebutton"></form>
      </fieldset>
      <fieldset>
      <legend>
      Refresh Peer Provider
      </legend>
      <form action="/manage" method="get"><input type="submit" name="peers" value="Refresh Peers" class="managebutton"></form>
      </fieldset></td><td width="50%" valign="top">
      <fieldset>
      <legend>
      Help
      </legend>
      <p>To fetch some of the latest posts so you don't have a blank board, click "Fetch Threads" to the left.</p>
      <p>If you can not properly connect to any peers, or are connected but don't receive any posts from them, your computer or router may be blocking P2PChan's traffic. Try opening UDP port 44545, TCP port 44546 on your router, or disabling your local firewall for P2PChan's process.</p>
      <p>Use &gt; to quote some text: <span class="unkfunc">&gt;you, sir, are an idiot :)</span></p>
      <p>Use &gt;&gt; to reference another post in the same thread: <a href="#1a179">&gt;&gt;1a179</a></p>
      <p>Use &gt;&gt;&gt; to reference another thread: <a href="/?res=b02de651-c923-11de-b7eb-001d72ed9aa8">&gt;&gt;&gt;&shy;b02de651-c923-11de-b7eb-001d72ed9aa8</a>
      <p>Formatting options:</p>
      <p>[b]text[/b], __text__, **text** == <b>text</b></p>
      <p>[i]text[/i], *text* == <i>text</i></p>
      <p>[s]text[/s] == <s>text</s></p>
      <p>[spoiler]text[/spoiler], %% text %% == spoiler</p>
      </fieldset>
      </td></tr></table>"""
    return renderManagePage(text, self.stylesheet)