#!/usr/bin/python
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import collections
import operator
import os
import subprocess
import sys
import pwd

# used in rquota_t.type
USRQUOTA = 0
GRPQUOTA = 1

# rquota_t namedtuple
# Based off of 'struct dqblk' v2 in linux source /usr/include/sys/quota.h.
# Members defined in order of quota program output, other than type and id:
# Filesystem blocks quota limit grace files quota limit grace
rquota_t = collections.namedtuple("rquota_t",
                                  [
                                     "type",
                                     "id",
                                     "dqb_curspace",   # v2 in bytes
                                     "dqb_bsoftlimit",
                                     "dqb_bhardlimit",
                                     "dqb_btime",
                                     "dqb_curinodes",
                                     "dqb_isoftlimit",
                                     "dqb_ihardlimit",
                                     "dqb_itime"
                                  ])

def rquota_get(path, query_supplementary = False):
    """Calls out to the quota binary to collect user/group rpc.rquotad
       info on path.  Returns a list of rquota_t objects in order UID,
       GID, followed by supplemental GID(s) of the calling user."""
    # user quota list
    uql = []
    if type(path) is not str:
        return uql
    # see "man quota"
    QUOTA = "/usr/bin/quota " \
            "-F rpc -v -p -w -u -g -Q -f {0}".format(path).rsplit(" ")
    # quota standard output read into string
    try:
        qstdout = subprocess.Popen(QUOTA,
                                   stdout = subprocess.PIPE,
                                   stderr = subprocess.STDOUT).communicate()[0]
    except:
        return uql
    uid = os.getuid()
    gid = os.getgid()
    # index 0 reserved for primary user quota
    uql.append(None)
    # index 1 reserved for primary group quota
    uql.append(None)
    # split string blob into a list of lines
    qlines = qstdout.split("\n")
    for l in qlines:
        if l.startswith("Disk quotas for"):
            # info we're after is two lines later
            qi = qlines.index(l) + 2
            ql = qlines[qi].split()
            lt = l.split()
            qt = rquota_t(USRQUOTA if lt[3] == "user" else GRPQUOTA,
                          int(lt[6].split(")")[0]),
                          int(ql[1].split("*")[0]) * (1 << 10), # in bytes
                          int(ql[2].split("*")[0]),
                          int(ql[3].split("*")[0]),
                          int(ql[4].split("*")[0]),
                          int(ql[5].split("*")[0]),
                          int(ql[6].split("*")[0]),
                          int(ql[7].split("*")[0]),
                          int(ql[8].split("*")[0]))
            if lt[3] == "user":
                if uid == qt.id:
                    uql[0] = qt
            elif lt[3] == "group":
                if gid == qt.id:
                    uql[1] = qt
                elif query_supplementary:
                    uql.append(qt)
    return [] if ((uql[0] is None) or (uql[1] is None)) else uql

def rquota_find_home_mount():
    """find the file system mount point that holds the home path for the
       calling user"""
    pwe = pwd.getpwuid(os.getuid())
    path = pwe.pw_dir
    # stat home directory path
    shd = os.stat(path)
    # path components
    pc = path.split("/")
    # if home dir is /home/group/uid, check in order for st_dev change:
    # /home/group
    # /home
    # /
    for c in range(len(pc) - 1, 0, -1):
        path = "/".join(pc[:c])
        if not len(path):
            path = "/"
        if os.stat(path).st_dev != shd.st_dev:
            path = "/".join(pc[:c + 1]);
            break
    return path

if __name__ == "__main__":
    ql = rquota_get(rquota_find_home_mount(), True)
    m = [
            "user quota",
            "group quota"
        ]
    pwe = pwd.getpwuid(os.getuid())
    # are quotas enabled?
    for q in ql:
        print "{0} {1} for {2} is {3}/{4} KiB {5}/{6} files".format(
            q.id,
            m[q.type],
            pwe.pw_dir,
            q.dqb_curspace / (1 << 10), q.dqb_bhardlimit,
            q.dqb_curinodes, q.dqb_ihardlimit)
