#!/usr/bin/env python
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

PURGE_PATH = "/lustre/purge/current"

from optparse import OptionParser, OptionGroup
from os import getuid, stat
from pwd import getpwuid
from sys import exit
from time import ctime
import subprocess

def print_stat(uid):
    stat_file = "{0}/{1}.stat".format(PURGE_PATH, uid)
    try:
        usf_s = stat(stat_file)
    except:
        return 1
    usf = open(stat_file, "r")
    print "Eligible /work purge status for {0} (as of {1}):\n" \
          "{2}".format(uid, ctime(usf_s.st_mtime), usf.read()),
    return 0

def print_list(uid):
    list_file = "{0}/{1}.list".format(PURGE_PATH, uid)
    try:
        ulf_s = stat(list_file)
    except:
        return 1
    subprocess.call("less -n {0}".format(list_file).split(" "))
    return 0

def main():
    usage = "usage: %prog [OPTION]"
    parser = OptionParser(usage = usage)
    parser.add_option("-l", "--list", action = "store_true", default = False,
                      help = "print listing of eligible files to purge")
    (opts, args) = parser.parse_args()

    pwe = getpwuid(getuid())

    if opts.list:
        rc = print_list(pwe.pw_name)
    else:
        rc = print_stat(pwe.pw_name)

    exit(rc)
