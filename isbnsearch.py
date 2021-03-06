#!/usr/bin/env python
#
# Algorithm:
#
#  * For any item with an ISBN, we want to say:
#    - if the sales rank is 
#
import os, sys, re, lxml, cgi, unicodedata, locale, time, traceback
import cgitb
import StringIO
from ConfigParser import *
from amazonproduct import *
import urllib2 # for exception handling on timeouts from amazonproduct calls
from datetime import date

cgitb.enable()
import shelve

dat = shelve.open("isbnsearch.dat", writeback=True)
datkey = str(date.fromtimestamp(time.time()).toordinal())
if not dat.has_key(datkey):
    dat[datkey] = {'selected': 0, 'unknown': 0, 'rejected': 0}

lowcutoffprice = 500.0 # in pennies US$
highcutoffprice = 1500.0 # in pennies US$
cutoffprice_epsilon = 5.0
salesrankcutoff = 10000000

def dosearch(api, isbn, page):
    node = None
    try:
        idType = "ISBN"
        if len(isbn) == 12: idType = "UPC"
        node = api.item_lookup(isbn, IdType=idType, SearchIndex="All", MerchantId="All", Condition="All", ResponseGroup="Medium,Offers", OfferPage=page)
        #open("/tmp/%s-search.xml" % isbn, "w").write(str(node))
    except InvalidParameterValue, e:
        if e.args[0] == "ItemId":
            pass
        else:
            raise e
    return node

def safe_note(s):
    res = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore')
    res = cgi.escape(res, True)
    return res.replace('\'', "&rsquot;")

def firstof(lxmlnode, possibleattributes, default="(none)"):
    for attr in possibleattributes:
        try:
            res = lxmlnode.__getattr__(attr)
            return res
        except AttributeError, e:
            pass
    return default


#
# rejected, selected or unknown
#
def classifyvalues(values):
    if (values[0] > usedcutoffprice):
        return "selected"
    if (len(values) > 5 and values[4] < usedcutoffprice):
        return "rejected"
    return "unknown"

def classifyoffersummaries(item):
    salesrank = firstof(item, ["SalesRank"], 0)
    results = {"lowused": None,
               "lowusedfmt": "--",
               "lownew":  None,
               "lownewfmt": "--",
               "lowcollectible": None,
               "lowcollectiblefmt": "--",
               "totalnew": 0,
               "totalused": 0,
               "totalcollectible": 0,
               "class": "unknown",
               "msg": ""}

    for offs in (item.OfferSummary):
        results["totalnew"] += offs.TotalNew
        results["totalused"] += offs.TotalUsed
        results["totalcollectible"] += offs.TotalCollectible
        try:
            lu = int(offs.LowestUsedPrice.Amount)
            if (results["lowused"] is None or lu < results["lowused"]):
                results["lowused"] = lu
                results["lowusedfmt"] = offs.LowestUsedPrice.FormattedPrice
        except:
            pass
        try:
            ln = int(offs.LowestNewPrice.Amount)
            if (results["lownew"] is None or ln < results["lownew"]):
                results["lownew"] = ln
                results["lownewfmt"] = offs.LowestNewPrice.FormattedPrice
        except:
            pass
        try:
            lc = int(offs.LowestCollectiblePrice.Amount)
            if (results["lowcollectible"] is None or lc < results["lowcollectible"]):
                results["lowcollectible"] = lc
                results["lowcollectiblefmt"] = offs.LowestCollectiblePrice.FormattedPrice
        except:
            pass

    # if we have new items offered for less than 'lowcutoffprice' then we don't want to list
    if (results["lownew"] is not None and results["lownew"] < (lowcutoffprice+cutoffprice_epsilon)):
        results["class"] = "rejected"
        results["msg"] = "rejected because there are new copies for sale at less than $%.2f" % ((lowcutoffprice+cutoffprice_epsilon)/100.0)

    # if we have very poor selling items offered for less than 'highcutoffprice' then we don't want to list
    if ( (results["lownew"] is not None and results["lownew"] < highcutoffprice) and ((salesrank is None) or (salesrank > salesrankcutoff))):
        results["class"] =  "rejected"
        results["msg"] = "rejected because salesrank is poor and there are new copies for sale at less than $%.2f" % ((highcutoffprice)/100.0)

    # if we have more than 20 items used, and lowprice is < a dollar, don't list
    if ((results["totalused"] > 20) and results["lowused"] is not None and (results["lowused"] < 100)):
        results["class"] = "rejected"
        results["msg"] = "rejected because there are more than 20 used copies available and the lowprice is < $1.00"

    # if there are no items listed below 'lowcutoffprice' and the salesrank exists and is < 'salesrankcutoff', then DO list
    if ((results["lowused"] > (lowcutoffprice+cutoffprice_epsilon) and (results["lownew"] is None or results["lownew"] > (lowcutoffprice+cutoffprice_epsilon))) and (salesrank is not None) and (salesrank < salesrankcutoff)):
        results["class"] = "selected"
        results["msg"] = "ACCEPTED because low price is > $%.2f and sales rank is < %d" % (((lowcutoffprice+cutoffprice_epsilon)/100.0), salesrankcutoff)

    ### NEW TODAY ###
    # if there are no items listed below 'highcutoffprice' and the salesrank exists and is > 'salesrankcutoff', then DO list
    if ((results["lowused"] > (highcutoffprice+cutoffprice_epsilon) and (results["lownew"] is None or results["lownew"] > (highcutoffprice+cutoffprice_epsilon))) and (salesrank is not None) and (salesrank > salesrankcutoff)):
        results["class"] = "selected"
        results["msg"] = "ACCEPTED because low price is > $%.2f and sales rank is > %d" % (((highcutoffprice+cutoffprice_epsilon)/100.0), salesrankcutoff)

    ### NEW TODAY ###
    # if there is NO sales rank and the prices is > $25, list
    if (salesrank is None) and ((results["lowused"] > 2500+cutoffprice_epsilon) and (results["lownew"] is None or results["lownew"] > 2500+cutoffprice_epsilon)):
        results["class"] = "selected"
        results["msg"] = "ACCEPTED because low price is > $%.2f and there is no sales rank" % 25.00

    return results

    
def formatitem(item, offsresult):
    res = StringIO.StringIO()
    try:
        atr = item.ItemAttributes
        author = firstof(atr, ["Author", "Artist", "Creator"])
        pub = firstof(atr, ["Publisher", "Label"])
        sr = firstof(item, ["SalesRank"], 0)

        if author is None or type(author) == type(""):
            author = "(no author)"
        else:
            author = author.text.encode('utf8')

        if pub is None or type(pub) == type(""):
            pub = "(no publisher)"
        else:
            pub = pub.text.encode('utf8')

        bycond = dict()
        rowclass = offsresult["class"]
        if dat[datkey].has_key(rowclass):
            dat[datkey][rowclass] += 1
        else:
            dat[datkey][rowclass] = 1

        print >>res, "<tr class='%s' title='%s'>" % (rowclass, offsresult["msg"])

        print >>res, "<td>"
        #print >>res, "<b>", cgi.escape(str(atr.Title), True), "</b><br>ASIN: ", item.ASIN, "<br>by", cgi.escape(str(author)), ",", cgi.escape(str(pub))
        print >>res, "<b><a href='%s' target='_blank'>" % item.DetailPageURL, cgi.escape(atr.Title.text.encode('utf8'), True), "</a></b><br>ASIN: ", item.ASIN, "<br>EAN: ", firstof(atr, "EAN"), "<br>ISBN: ", firstof(atr, "ISBN"), "<br>by", cgi.escape(author, True), ",", cgi.escape(pub, True)
        print >> res, "</td>"

        offs = item.OfferSummary
        print >>res, "<td><table>"
        print >>res, "<tr><td colspan=2>SalesRank <b>", locale.format("%d", int(sr), True), "</b></td></tr>"
        try:
            print >>res, "<tr><td align=right>%d N</td><td> &gt;= %s</td></tr>" % (offsresult["totalnew"], offsresult["lownewfmt"])
        except:
            print >>res, "<tr><td align=right>0 N</td><td></td></tr>"
        try:
            print >>res, "<tr><td align=right>%d U</td><td> &gt;= %s</td></tr>" % (offsresult["totalused"], offsresult["lowusedfmt"])
        except:
            print >>res, "<tr><td align=right>0 U</td><td></td></tr>"
        try:
            print >>res, "<tr><td align=right>%d C</td><td> &gt;= %s</td></tr>" % (offsresult["totalcollectible"], offsresult["lowestcollectiblefmt"])
        except:
            print >>res, "<tr><td align=right>0 C</td><td></td></tr>"
        print >>res, "</table></td>"

        print >>res, "<td><table>"
        for key in bycond.keys():
            print >>res, "<tr><td align=right>%s</td><td>%s</td></tr>" % (key, ' '.join(bycond[key]))
            #print >>res, "<br>"
        print >>res, "</table></td>"
        
        print >>res, "</tr>"

        # debugging, dump the item into the table too
        #print >>res, "<tr><td colspan=3>", str(item).replace("\n", "<br>"), "</td></tr>"
    except:
        res.truncate(0)
        print >>res, "<tr><td colspan=3>Unknown exception: ", 
        traceback.print_exc(None, res) #str(sys.exc_type), str(sys.exc_value), str(sys.exc_traceback), 
        print >>res, "</td></tr>"
    return res.getvalue()


def process_isbns(isbns):
    print "<table border='1'>"
    print "<tr><th>Item Details</th><th>Offer Summary</th><th>20 Lowest Priced Offers</th></tr>"

    for isbn in isbns:
        try:
            node = dosearch(api, isbn, 1)
        except urllib2.URLError, e:
            print "<tr><td colspan=3 bgcolor=purple><b>TIMEOUT SEARCHING FOR ISBN: ", isbn, "<br>%s</b></td></tr>" % str(e)
            continue
        except Exception as e:
            print "<tr><td colspan=3 bgcolor=purple><b>EXCEPTION HANDLING ISBN: ", isbn, "<br>%s</b></td></tr>" % str(e)
            continue
        
        if node is None:
            print "<tr><td colspan=3 bgcolor=yellow><b>INVALID ISBN: ", isbn, "</b></td></tr>"
            continue

        try:
            item = None
            # For books with kindle editions, we get one item for the kindle version which *does not* have an Offers attribute
            # and another (for the one we actually asked for) which does have it.
            # The kindle ISBN is not the same as the book ISBN, so we can distinguish by that, or by the ItemAttributes.Binding, or .Edition
            itemsandoffers = []
            for i in node.Items.Item:
                if i.__dict__.keys().__contains__("Offers"):
                    item = i
                    offers = classifyoffersummaries(item)
                    itemsandoffers.append((item, offers))

            # FIXME: ok, in the case where we have multiple itemsandoffers,
            # should create a formatted listing using different code, better
            # explain what's going on.
            (item, offers) = realitemandoffers(itemsandoffers)
            if (item is not None):
                print formatitem(item, offers)
            elif (allselected(itemsandoffers)):
                print formatitem(itemsandoffers[0][0], itemsandoffers[0][1])
            else:
                print "<tr><td colspan=3 bgcolor=red><b>%d ASIN LISTINGS FOR ISBN: " % len(itemsandoffers), isbn, "</b>, not all accept</td></tr>"

        except Exception as e:
            print "<tr><td colspan=3 bgcolor=yellow><b>EXCEPTION PROCESSING ISBN: ", isbn, ", email emile.snyder@gmail.com<br>%s</b></td></tr>" % str(e)
        sys.stdout.flush()
    print "</table>"

def realitemandoffers(itemsandoffers):
    for (item, offers) in itemsandoffers:
        if item.ASIN[0] != 'B':
            return (item, offers)
    return (None, None)

def allselected(itemsandoffers):
    for (item, offers) in itemsandoffers:
        if offers['class'] == 'rejected': return False
    return True

# api = API(os.getenv("AMAZON_ACCESS_KEY"), os.getenv("AMAZON_SECRET_KEY"), "us")
def make_apiobj():
    cfg = ConfigParser()
    cfg.read("/etc/apache2/amazon.keys")
    if not cfg.has_option("keys", "AMAZON_ACCESS_KEY"):
        cfg.read("./amazon.keys")
    return API(cfg.get("keys", "AMAZON_ACCESS_KEY"), cfg.get("keys", "AMAZON_SECRET_KEY"), "us", cfg.get("keys", "AMAZON_ASSOCIATE_TAG"))


def display_searches(shelf, key):
    print "<h3>ISBN searches: last 7 days</h3>"
    print "<table border=1>"
    datkeyordinal = int(key)
    print "<tr><th>date</th><th>(sell, ?, shelve)</th><th>total # isbn searches</th></tr>"
    for o in range(datkeyordinal-6, datkeyordinal+1):
        d = str(date.fromordinal(o))
        v = shelf.get(str(o), dict())
        (acc, unkn, rej) = (v.get('selected', 0), v.get('unknown', 0), v.get('rejected', 0))
        print "<tr><td><b>%s</b>: </td><td>(<span class='selected'>%d</span>, %d, <span class='rejected'>%d</span>)</td><td><b> %d</b></td></tr>" % (d, acc, unkn, rej, acc+unkn+rej)
    print "</table>"

isbnstring = ""
form = cgi.FieldStorage()

api = make_apiobj()
lxml.objectify.enable_recursive_str(True)

locale.setlocale(locale.LC_ALL, 'en_US.utf8')

if __name__ != "main":
    print "Content-Type: text/html\n\n"
    print "<html><head>"
    print "<style type='text/css'>"
    print " .rejected { background-color: #FF0000; }"
    print " .selected { background-color: #00FF00; }"
    print "</style>"
    print "</head>\n<body>"

    isbns = list()
    invalidisbns = dict()
    if form.has_key("isbns"):
        isbns = form["isbns"].value.split()
        process_isbns(isbns)
    else:
        pass

    display_searches(dat, datkey)
    #print "ISBN lookups today: ", dat[datkey], "\n"

    dat.close()

    print "<h3>Enter ISBNs (or UPC from CD/DVD/etc.) 1 per line</h3>"
    #print "Listing calculations using:<br>"
    #print "low price cutoff:   $%.2f<br>" % (lowcutoffprice / 100.0)
    #print "high price cutoff:  $%.2f<br>" % (highcutoffprice / 100.0)
    #print "salesrank cutoff:   %d<br>" % salesrankcutoff
    #print "<br>"

    print "<form method='GET'>"
    print "<textarea width='80%' name=isbns rows=20></textarea>"
    print "<input type='submit' value='Search'/>"
    print "</form>"

    print "</body></html>"
