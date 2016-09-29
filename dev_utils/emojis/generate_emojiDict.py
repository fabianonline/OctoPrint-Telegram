import json, codecs, os, sys

if len(sys.argv) < 2:
    sys.exit('Usage: %s <path to JSON file>' % sys.argv[0])

if not os.path.exists(sys.argv[1]):
    sys.exit('ERROR: JSOn file %s was not found!' % sys.argv[1])

with open(sys.argv[1]) as data_file:    
    data = json.load(data_file)

myDict = {}
cntE = 0
cntPass = 0
for d in data:
	cntE += 1
	if 'description' in d and 'emoji' in d:
		if d['description'] not in myDict:
			myDict[d['description']] = d['emoji']
			cntPass += 1
		else:
			print "Double entry for: {}".format(str(d))
	else:
		print "No description or emoji found for: {}".format(str(d))

fileName = 'emojiDict.py'
print "\n\nAdded " + str(cntPass) + " of " + str(cntE) + " emojis in "+str(sys.argv[1])+".\nSving now to " + fileName

f = codecs.open(fileName,encoding='utf-8',mode='w+')
f.write('# Generated with Data from:\n# https://github.com/github/gemoji\n\n# Overview can be found here (description in table on the page used as key in this dict):\n# http://apps.timwhitlock.info/emoji/tables/unicode\n\n\ntelegramEmojiDict = {\n') # python will convert \n to os.linesep
for d in myDict:
	f.write("'{}'".format(d)+": u'"+ myDict[d].encode("unicode_escape") + "',\n")
f.write("}")
f.close() # you can omit in most cases as the destructor will call it

print "DONE"