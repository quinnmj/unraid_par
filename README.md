# unraid_par
Par script to create and check par files on unraid server

This might eventually become an unraid package, but currently I'm not sure how to do that.

This is intended to handle your video files - I don't suggest using it on the auxiliary nfo and xml files
that the various video downloading utilities create. 

I will be looking at extending it for music files, where it does 1 par file per album (you can obviously do 1 par file per flac/aac/mp3, but that could create a lot of files - up to you).

NOTE: If you're familiar with par2, this is a modified version of par2 that has added the -d switch to set the root directory for the par file (this is useful for files deeper than 1 level deep). 

Installation:

1) Put the 4 *.txz files into the /boot/extra folder
2) Create a /boot/custom folder and put par2 and par.py in it.
3) Make sure python 2.7 is installed (doesn't work with python3 yet) - Nerd pack has it.
4) Modify kParBasePath for where you want Par files kept
5) Modify kPar2Bin if you didn't put the par2 file /boot/custom
6) Modify listVideoFolders for the folders that you want to search for files
7) Modify listVideoExts for the video extension you want handled.
8) Modify kVideoBasePath if you really want to (I don't think you do).
9) Put the libtbb*.so.x files into the same folder as par2 (This can be fixed once this thing is packaged up properly,
   but for now, this is the easiest way to do it until a package gets created)
   
   
   
   
Anybody who wants to create an unraid package for this, that would be great - I haven't found any docs on how to actually do it (I do know how to create a txz package, but not really the .plg file....
   
   
