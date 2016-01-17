#!/usr/bin/env python

import os, sys, cgi, re

def should_pull(line):
    return re.match(".*using floor.*", line) != None

def process_log(data):
    lines = data.split("\n")
    print "process_log found %d bytes in %d lines" % (len(data), len(lines))
    lines = filter(should_pull, lines)
    lines.sort()
    locs_seen = 1
    last_loc = ""
    print "filtered to %d lines:" % len(lines)
    print "<table>"
    print "<tr><td>Loc</td><td>SKU</td><td># other</td><td>low</td><td>lowest</td><td>rnk</td><td>Loc</td><td>Title</td></tr>"
    for line in lines:
        #101A using floor 5.01, low is $2.73 with 1 offers <= (2.73) sku/loc/title: 000713 101A: Five senses;
        m = re.match("^(\w+) using floor (.+), low is \$(.+) with (\d+) offers <= \((.*)\) rank (.+) sku/loc/title: (\w+) (\w+): (.*)$", line)
        (loc, floorprice, lowprice, lowoffercount, lowprices, salesrank, sku, _, title) = m.groups()
        
        # ignore borderline cases
        if int(lowoffercount) == 1 and float(lowprice) >= 4.50:
            continue

        if loc != last_loc:
            locs_seen += 1
        last_loc = loc
        if locs_seen % 2 > 0:
            bgcolor = "#ffffff"
        else:
            bgcolor = "#dddddd"
        #print "<br>", cgi.escape(line, quote=True)
        print "<tr bgcolor='%s'>" % bgcolor
        #            loc        sku        #other      low                  lowest       rnk        loc        title
        print "  <td>%s</td><td>%s</td><td>%d</td><td>$%0.2f</td><td nowrap>(%s)</td><td>%s</td><td>%s</td><td>%s</td>" % (loc, sku, int(lowoffercount), float(lowprice), lowprices, salesrank, loc, title)
        print "</tr>"

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
