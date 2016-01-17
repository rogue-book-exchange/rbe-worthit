#!/usr/bin/env python

import os, sys, cgi, re

def should_pull(line):
    return re.match(".*using floor.*", line) != None

def process_log(data):
    lines = data.split("\n")
    print "process_log found %d bytes in %d lines" % (len(data), len(lines))
    lines = filter(should_pull, lines)
    lines.sort()
    print "filtered to %d lines:" % len(lines)
    for line in lines:
        print "<br>", cgi.escape(line, quote=True)

form = cgi.FieldStorage()

if __name__ == "__main__":
    print "Content-Type: text/html\n\n"
    print "<html><head>"
    print "<style type='text/css'>"
    print "</style>"
    print "</head>\n<body>"

    if form.has_key("log"):
        process_log(form.getfirst("log", ""))

    print "<h3>Enter Debugging Log from Repricing Script</h3>"
    print "<form method='POST'>"
    print "<textarea width='80%' name=log rows=20></textarea>"
    print "<input type='submit' value='Show to-be-pulled'/>"
    print "</form>"

    print "</body></html>"
