"""
  File: main.py
  Author: Matthew Morgan
  Date: 23 January 2019

  Description:
  This program reads in a significant amount of data from the Gutenberg corpora, processing the
  title, author, dates, and content of each document to generate a postings index for each unique
  term in the corpora.
"""

from rediscluster import StrictRedisCluster
from stem import PorterStemmer
from ir import Token, tokenize
from util import confirm, fileList
import sys

# rhost, rport, and rpass are the database login credentials and access location
rhost, rport, rpass = '150.216.79.30', 6379, '1997mnmRedisStudies2019'
rnode = [ {"host": rhost, "port": rport} ]

# LANG_ALLOWED is the list of allowed languages (english, latin)
LANG_ALLOWED = ['english']

def __main__():
  global rhost, rport, rpass

  # ------------------------------------------------------------------------------------------------
  # Connect to the Redis database, or terminate if the connection fails
  print("Connecting to ", rhost, ":", rport, sep="")

  try:
    r = StrictRedisCluster(startup_nodes=rnode, decode_responses=True, password=rpass)
  except Exception:
    print("Error connecting to database...")
    sys.exit(1)
  
  print("Connection successful")

  # Prompt to clear the database
  nodes = r.dbsize()
  for node in nodes:
    if nodes[node] > 0:
      if confirm("Clear the database? (y/n)"):
        r.flushall()
      break

  # ------------------------------------------------------------------------------------------------
  if confirm("Load corpus data? (y/n)"):
    tDic, tokens, fidList = {}, {}, []
    stem = PorterStemmer()

    cnt = 0

    for f in fileList('./data/cor/0-1/english/'):
      # The fid is the numerical portion of the file's name, before a hyphen. For example:
      # ./data/100.txt --> 100, ./data/245-1.txt --> 245
      fid = f.split('/')[-1]
      fid = fid[:len(fid)-4]
      if '-' in fid: fid = fid.split("-")[0]

      cnt += 1
      if cnt > 3: continue

      # Ignore duplicate/alternate document IDs
      if fid in fidList: continue
      else: fidList.append(fid)

      with open(f, 'r', encoding='utf-8') as fRead:
        lines, pos = fRead.readlines(), 0

        meta = {
          "name": lines[0][lines[0].index(':')+1:].strip(),
          "auth": lines[1][lines[1].index(':')+1:].strip(),
          "date": lines[2][lines[2].index(':')+1:].strip(),
          "lang": lines[3][lines[3].index(':')+1:].strip().lower()
        }

        if '[' in meta['date']: meta['date'] = meta['date'][:meta['date'].rindex('[')]

        # Skip the file if it isn't in the list of allowed languages
        if not meta['lang'] in LANG_ALLOWED: continue
        tDic[fid] = meta

        # Tokenize lines and remove those that are empty after tokenization
        lines = [tokenize(line) for line in lines[5:]]
        lines = [line for line in lines if line]

        for line in lines:
          for word in line:
            pos += 1
            word = stem.stem(word, 0, len(word)-1)
            if not word in tokens: tokens[word] = Token(tok=word)

            tok = tokens[word]
            tok.add_doc(fid)      # Boolean retrieval
            tok.add_pos(fid, pos) # Positional index
      
      print('%7s' % (fid),':',tDic[fid]['name'])
    print()

    # ----------------------------------------------------------------------------------------------
    if confirm("Load data into database? (y/n)"):
      # Add the data to the database
      print("Copying document data to the database... (", len(tDic), " documents)", sep='')
      for doc in tDic:
        r.hset('doc:'+doc, 'name', tDic[doc]['name'])
        r.hset('doc:'+doc, 'auth', tDic[doc]['auth'])
        r.hset('doc:'+doc, 'date', tDic[doc]['date'])
    
      print("Copying word data to the database... (", len(tokens), " tokens)", sep='')
      for tok in tokens:
        r.sadd('term:'+tok, *set(tokens[tok].docs))
        for doc in tokens[tok].docs: r.lpush('post:'+tok+'-'+doc, tokens[tok].pos[doc]) # TODO Connection error

  # ------------------------------------------------------------------------------------------------
  # Allow the user to type phrase and term queries
  done = False

  print("\nType '!stop' to exit querying")

  while not done:
    q, search = input("Query > "), []

    if q == '!stop': done = True
    elif q == '!sys':
      keys, info, rep = r.dbsize(), r.info(section='memory'), r.info(section='replication')

      print('Database Master Nodes')
      for node in [k for k in keys if rep[k]['role'] == 'master']:
        print('  ', node, ' -> ', keys[node], ' keys', sep='')
        print('    Memory: (Cur\\Ttl -> %s \\ %s), (RSS\\LUA -> %s \\ %s)' %
          (info[node]['used_memory_human'], info[node]['total_system_memory_human'],
           info[node]['used_memory_rss_human'], info[node]['used_memory_lua_human']))
        print('    Workers:', rep[node]['connected_slaves'])
    else:
      for term in tokenize(q): search.append('term:'+PorterStemmer().stem(term, 0, len(term)-1))
      res = r.sinter(search)

      print("There were", len(res), "hits")
      for doc in res:
        print('%7s' % (doc), ':', r.hget('doc:'+doc, 'name'))
    
    print()

__main__()