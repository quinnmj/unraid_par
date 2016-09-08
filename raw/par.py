#!/usr/bin/python

import itertools as it
import os, glob, subprocess, sys, re
import getopt
import threading, signal, time
import shutil, math, xattr,datetime

#
# Basic definitions
#
kMaxDisks = 32
kDiskBasePath = "/mnt"
kVideoBasePath = "/mnt/user"
kParBasePath="/mnt/disk7/Backups/Mike Backups/_VideoPars"
kParGlobExt=".vol0*+*.par2"

kParXattrType = "user.par2"

kPar2Bin = "/boot/custom/par2"
kParBadDate = 99990000
kParNoDate = 0

Par_re_pattern="^(.+)\.vol[0-9]+\+[0-9]+\.par2$"
Par2_ext = ".par2"
Video_ext_pattern=".*"

listVideoFolders={ "TV_DVR", "Movies", "Vacations", "TV" }
listVideoExts={".mp4", ".mkv", ".avi", ".iso"}

Yes={ "yes", "ye", "y"}
No={"no", "n"}

#
# Threading globals
#
gThreadCount = 0
gKillMe = False

gIoLock = threading.Lock()
gWaitSem = threading.Semaphore()

Today=datetime.date.today().year * 10000 + datetime.date.today().month * 100 + datetime.date.today().day

#
# Ask y/n question
#
def ask(question):
    while True:
        sys.stdout.write(question + "? ")
        choice=raw_input().lower()
        if choice in Yes:
            return True
        if choice in No:
            return False
        sys.stdout.write("Please respond with 'yes' or 'no'\n")

def Get_absolute_par_name(base_file):
    return os.path.join(kParBasePath, base_file)

def Get_absolute_video_name(base_file):
    return os.path.join(kVideoBasePath, base_file)

def Get_file_info_string(base_file, date):
    (mode, ino, dev, nlink, uid, gid, size, atime, mtime, ctime) = os.stat(Get_absolute_video_name(base_file))
    return str(date) + "," + str(size) + "," + str(mtime)

def Parse_file_info(value):
    if value == "bad":
        return [kParBadDate, 0, 0];
    if not ',' in value:
        return [int(value), 0, 0];
    m=re.match("^([0-9]+),([0-9]+),([0-9]+)$", value)
    if not m:
        print("ERROR: Couldn't parse " + value)
        return [0, 0, 0];
    return [int(m.group(1)), int(m.group(2)), int(m.group(3))]

def File_matches_info(base_file, info):
    (mode, ino, dev, nlink, uid, gid, size, atime, mtime, ctime) = os.stat(Get_absolute_video_name(base_file))
    if info[1] != size or info[2] != mtime:
        return False
    return True
   
def Is_video_file(file):
    filename, file_ext = os.path.splitext(file)
    return file_ext in listVideoExts
#
# Get the size of a video
#
def Get_video_size(base_file):
    return os.path.getsize(Get_absolute_video_name(base_file))
#
# Get the block size we should use for the file
#
def Get_block_size(base_file, pct):
    size = Get_video_size(base_file)
    blocks = size/10000
    a=2**(blocks - 1).bit_length()
    if (size / a) > 700 * pct:
        a = a * 2
    return a

def Get_folder(file):
    return os.path.dirname(file)

def Get_basename_from_par(par_file):
    m=os.path.basename(par_file)
    d=re.match(Par_re_pattern, m)
    return d.group(1)

def Get_basename_from_video(file):
    return os.path.basename(file)
#
################################################################################
# Routines to get lists of files
################################################################################
#
# Get list of par files
#
def Get_par_list():
    file_list=[]
    pstrip_len=len(kParBasePath)
    for bdir in listVideoFolders:
        for sroot, sdir, sfiles in os.walk(os.path.join(kParBasePath, bdir)):
            for sname in sfiles:
                tmp=os.path.join(sroot[pstrip_len + 1:], sname)
                file_list.append(tmp)
    return file_list
#
# Get list of video files
#
def Get_video_list():
    file_list=[]
    vstrip_len=len(kVideoBasePath)
    for bdir in listVideoFolders:
        for sroot, sdir, sfiles in os.walk(os.path.join(kVideoBasePath, bdir)):
            for sname in sfiles:
                if Is_video_file(sname):
                    tmp=os.path.join(sroot[vstrip_len + 1:], sname)
                    file_list.append(tmp)
    return file_list
#
# Create a list of lists of files (one list for each disk)
# This is used for multi-threaded commands
#
def CreateVideoLists():
  disk_list = []
  for i in range(1,kMaxDisks):
    dname = os.path.join(kDiskBasePath, "disk" + str(i))
    if os.path.isdir(dname):
      vstrip = len(dname) + 1
      list = []
      for bdir in listVideoFolders:
        for sroot, sdir, sfiles in os.walk(os.path.join(dname, bdir)):
          for sname in sfiles:
            if Is_video_file(sname):
              tmp=os.path.join(sroot[vstrip:], sname)
              list.append(tmp)
      disk_list.append(list)
  return disk_list

def Get_par_normalized_names(par_files):
    list = []
    for name in par_files:
        use = os.path.join(Get_folder(name), Get_basename_from_par(name))
        list.append(use)
    return list

def Get_par_xattr_data(par_file):
    file = Get_absolute_par_name(par_file)
    try:
        b=xattr.getxattr(file, kParXattrType)
        return Parse_file_info(b)
    except:
        return [0, 0, 0]


def Get_file_pct(vid_file):
    pct = 5
    if "_TempMovies/" in vid_file or "TV_DVR/" in vid_file:
        pct = 2
    return pct

def Get_relative_video_file_name(full_vid_file):
    m = re.match(kVideoBasePath + "/(.+)", full_vid_file)
    if not m:
        return ""
    return m.group(1)

def Get_par_file_name(full_vid_file):
    m = re.match(kVideoBasePath + "(.+)", full_vid_file)
    if not m:
        return ""
    pfile = kParBasePath + m.group(1) + kParGlobExt
    if not glob.glob(pfile):
        return ""
    return glob.glob(pfile)[0]

def Do_create_par(vid_file):
    pct = Get_file_pct(vid_file)
    blocks = Get_block_size(vid_file, pct)
    video = os.path.join(kVideoBasePath, vid_file)
    list = [ "nice", kPar2Bin, "create" , "-d" + kVideoBasePath, "-n1", "-r" + str(pct),  "-s" + str(blocks), video]
    subprocess.call(list)
    #
    # Now, we have to remove the std par2 file, and move the file to it's final resting place
    # a[0] is the par file with data that we want to keep
    # 
    a=glob.glob(os.path.join(kVideoBasePath, vid_file + kParGlobExt))
    #
    # Remove any existing par file in the par folder for this vide
    #
    b=glob.glob(os.path.join(kParBasePath, vid_file + kParGlobExt))
    if b:
        for f in b:
            print("Remove old target par " + f)
            os.remove(f)
    b = glob.glob(os.path.join(kVideoBasePath, vid_file + Par2_ext))
    if b:
        for f in b:
            print("Remove basic par file " + f)
            os.remove(f)
    dest_dir = os.path.join(kParBasePath, os.path.dirname(vid_file))
    par_file = os.path.join(dest_dir, os.path.basename(a[0]))
    print("Move " + a[0] + " to " + par_file)
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
    shutil.move(a[0], dest_dir)
    info = Get_file_info_string(vid_file, Today)
    print("Setting file info to " + info)
    xattr.setxattr(par_file, kParXattrType, info)

def Do_create_1(file):
    full_file = os.path.abspath(file)
    print(full_file)
    if not os.path.isfile(full_file):
        print("ERROR: File " + file + " does not exist")
        exit(1)
    rel_file = Get_relative_video_file_name(full_file);
    print(rel_file)
    if rel_file == "":
        print("ERROR: File " + file + " is not on the video path")
        exit(1)
    Do_create_par(rel_file)

#
# These are the main routines here
#
def do_file_fix(file):
    file_to_fix=os.path.abspath(file)
    if not os.path.isfile(file_to_fix):
        print("ERROR: File " + file_to_fix + " does not exist")
        exit(1)
    par_file = Get_par_file_name(file_to_fix)
    if par_file == "":
        print("ERROR: No par2 file for " + file)
        exit(1)
    list = [ "nice", kPar2Bin, "repair", "-d" + kVideoBasePath, par_file, file_to_fix ]
    subprocess.call(list)
#
# Return the name of the current par file for the video file 
#
def Get_par_file_for(base_vid):
  pfile = os.path.join(kParBasePath, base_vid + kParGlobExt)
  p = glob.glob(pfile)
  if not p:
    return ""
  return p[0]


def Par_check_thread(date_from, disk_list, recheck_bad):
  global gThreadCount
  #
  # Sub-function to start off the par check
  #
  def Start_check(file, vid_file):
    par_file = os.path.join(kParBasePath, file)
    list = [ "nice", kPar2Bin, "verify" , "-q", "-q", "-d" + kVideoBasePath, par_file]
    return subprocess.Popen(list, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


  for name in disk_list:
    if gKillMe:
      break
    par_file = Get_par_file_for(name)
    if par_file == "":
      with gIoLock:
        print("ERROR: Missing par file for " + name)
    else:
      if gKillMe:
        break
      info = Get_par_xattr_data(par_file)
      doit = False
      show_good = False
      if info[0] == kParBadDate:
        if not File_matches_info(name, info) and info[1] != 0 and info[2] != 0:
          a = "bad (but file has changed) - "
          err = "ERROR: "
        else:
          doit = True
          show_good = True
          a = "bad - "
          err = "INFO: "
        with gIoLock:
          print(err + "File already marked as " + a + name + " " + str(info))
      elif not File_matches_info(name, info) and info[1] != 0 and info[2] != 0:
        with gIoLock:
          print("WARNING - Skipping changed file " + name + " " + str(info))
      elif info[0] == 0 or info[0] < date_from or (info[1] == 0 and info[2] == 0):
        doit = True
      if doit:
        with gIoLock:
          print("INFO: Start check for " + name + " " + str(info))
        proc = Start_check(par_file, name)
        code = proc.wait();
        if gKillMe:
          break
        if code != 0:
          sout, serr = proc.communicate()
          if gKillMe:
            break
          xattr.setxattr(par_file, kParXattrType, Get_file_info_string(name, kParBadDate))
          with gIoLock:
            print("ERROR: Par check failed for " + name)
            print("       " + serr)
        else:
          if gKillMe:
            break
          if show_good:
            print("!!!!: Retested as good - " + name)
          xattr.setxattr(par_file, kParXattrType, Get_file_info_string(name, Today))

  with gIoLock:
    gThreadCount -= 1
  if gThreadCount == 0:
    gWaitSem.release()

#
###############################################################################################
# Top-level function to handle control-C for those functions that use threading 
###############################################################################################
#
def Handle_kill(sig, frame):
  global gKillMe
  gKillMe = True

#
###############################################################################################
# Top-level function to start off par check functions - one on each disk 
###############################################################################################
#
def Do_checks(date_from, recheck_bad):
  global gThreadCount
  disk_list = CreateVideoLists()
  gWaitSem.acquire()
  signal.signal(signal.SIGINT, Handle_kill)
  signal.signal(signal.SIGTERM, Handle_kill)
  for disk_files in disk_list:
    with gIoLock:
      gThreadCount += 1
      t = threading.Thread(target=Par_check_thread, args=(date_from, disk_files, recheck_bad))
      t.start()
  while not gWaitSem.acquire(False):
    time.sleep(1)




def do_updates(do_del, do_create):
    vids = Get_video_list()
    pars = Get_par_list()
    par_base = Get_par_normalized_names(pars)
    if do_del:
        for name in par_base:
            if not name in vids:
                pname=pars[par_base.index(name)]
                print("Par with no video: " + pname )
                os.remove(Get_absolute_par_name(pname))
    if do_create:
        for name in vids:
            if not name in par_base:
                print("Missing par file: " + name)
                Do_create_par(name)
            else:
                pname=pars[par_base.index(name)]
                info = Get_par_xattr_data(pname)
                if not File_matches_info(name, info):
                   print("File changed: " + name)
                   Do_create_par(name)

           

def do_show_info():
    vids = Get_video_list()
    pars = Get_par_list()
    par_base = Get_par_normalized_names(pars)
    no_par = 0
    for name in vids:
        if not name in par_base:
            no_par += 1
            print("Missing par file: " + name)
    
    date_list = []
    no_info = 0
    changed = 0
    bad = 0
    wierd = 0
    ok = 0
    for name in vids:
        if name in par_base:
            info = Get_par_xattr_data(pars[par_base.index(name)])
            if info[0] == 0 and info[1] == 0 and info[2] == 0:
                print("No check information stored: " + name)
                no_info += 1
            elif not File_matches_info(name, info):
                print("File has changed: " + name)
                changed += 1
            elif info[0] == kParBadDate:
                print("Par is bad: " + name)
                bad += 1
            elif info[0] == 0:
                print("Wierd xattr information: " + name)
                wierd += 1
            else:
                ok += 1
                if not info[0] in date_list:
                    date_list.append(info[0])
    no_vid = 0
    for name in par_base:
        if not name in vids:
            print("Par with no video: " + name)
            no_vid += 1
    print("")
    print("Number of Video files = " + str(len(vids)))
    print(" Number that are ok       = " + str(ok))
    print(" Number without par file  = " + str(no_par))
    print(" Number with no info      = " + str(no_info))
    print(" Number that have changed = " + str(changed))
    print(" Number that are BAD      = " + str(bad))
    print(" Number with wierd info   = " + str(wierd))
    print("Number of Par files   = " + str(len(pars)))
    print(" Number with no video file = " + str(no_vid))
    print("Unique dates:")
    print("_____________")
    for date in date_list:
        print(date)



def main(argv):
    try:
        opts, args = getopt.getopt(argv, "dpc:f:r:1:")
    except getopt.GetoptError:
        print("-d = delete unused par2 files")
        print("-p = create new par2 files")
        print("-1 <filename> = create 1 par file")
        print("-c yyyymmdd = check par2 files not check since specified date")
        print("-f b = with -c forces rechecking of bad files")
        print("-r <filename> = repair specified file")
        print("no arguments = print(status information")
        exit(0)

    do_check = False
    date_from = 0
    do_delete = False
    do_create = False
    do_fix    = False
    recheck_bad = False
    fix_file = ""

    for opt, arg in opts:
        if opt == "-f":
            if arg == "b":
                recheck_bad = True
            else:
                print("ERROR: Illegal argument for -f")
                exit(1)
        if opt == "-d":
            do_delete = True
        elif opt == "-p":
            do_create = True
        elif opt == "-1":
            do_create = True
            fix_file = arg;
        elif opt == "-c":
            do_check = True
            date_from = int(arg)
            if ((date_from != 0 and date_from < 20160101) or date_from > Today):
                print("ERROR: Date must be > 20160101 and <= Today (" + str(Today) + ")")
                exit(1)
        elif opt == "-r":
            do_fix = True
            fix_file = arg

    if do_fix:
        if do_check or do_delete or do_create or recheck_bad:
            print("ERROR: -r must be the only option on the command line")
            exit(1)
        do_file_fix(fix_file)
    elif do_check:
        Do_checks(date_from, recheck_bad)
    elif do_create and fix_file != "":
        if do_delete or recheck_bad:
            print("ERROR: -1 must be the only command on the line")
        Do_create_1(fix_file)
    elif (do_delete or do_create):
        if recheck_bad:
            print("ERROR: -f x is not valid with this command")
            exit(1)
        do_updates(do_delete, do_create)
    else:
        if recheck_bad:
            print("ERROR: -f x is not valid by itself")
            exit(1)
        do_show_info()


if __name__ == "__main__":
    main(sys.argv[1:])

