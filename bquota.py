#!/usr/bin/python
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import collections
import operator
import os
import subprocess
import sys
import pwd

# used in bquota_t.type
USRQUOTA = 0
GRPQUOTA = 1

# bquota_t namedtuple
# Based off of 'struct dqblk' v2 in linux source /usr/include/sys/quota.h.
# Members defined in order of quota program output, other than type and id:
# Filesystem blocks quota limit grace files quota limit grace
bquota_t = collections.namedtuple("bquota_t",
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

def call_beegfs_ctl(qtype, path, id):
    """Calls out to the beegfs-ctl binary to collect user/group
       info on path for id.  Returns a bquota_t object."""
    # see "beegfs-ctl --getquota --help"
    if qtype == USRQUOTA:
        QUOTA = "/usr/bin/beegfs-ctl --getquota --csv --mount={0} --{1} {2}" \
                .format(path, "uid", id).split()
    else:
        QUOTA = "/usr/bin/beegfs-ctl --getquota --csv --mount={0} --{1} {2}" \
                .format(path, "gid", id).split()

    # quota standard output read into string
    try:
        qstdout = subprocess.Popen(QUOTA,
                                   stdout = subprocess.PIPE,
                                   stderr = subprocess.STDOUT).communicate()[0]
    except:
        return

    # split string blob into a list of lines
    qlines = qstdout.split("\n")

    # first line is header keys, read into list
    hk = qlines[0].split(",")

    # (facepalm) hard is listed twice
    hk[3] = "size_hard"
    hk[5] = "files_hard"

    # and the values
    qv = qlines[1].split(",")

    # quota dictionary
    qd = dict(zip(hk, qv))

    return bquota_t(qtype,
                    int(qd["id"]),
                    int(qd["size"].split()[0]),
                    0 if qd["size_hard"] == "unlimited"
                      else int(qd["size_hard"].split()[0]) / (1 << 10),
                    0 if qd["size_hard"] == "unlimited"
                      else int(qd["size_hard"].split()[0]) / (1 << 10),
                    0,
                    int(qd["files"]),
                    0 if qd["files_hard"] == "unlimited"
                      else int(qd["files_hard"]),
                    0 if qd["files_hard"] == "unlimited"
                      else int(qd["files_hard"]),
                    0)

def bquota_get(path, query_supplementary = False):
    """Returns a list of bquota_t objects in order UID, GID, followed
       by supplemental GID(s) of the calling user."""
    # user quota list
    uql = []

    if type(path) is not str:
        return uql

    uid = os.getuid()
    # place primary GID at the start of the list
    gid = os.getgid()
    if query_supplementary:
        grps = os.getgroups()
        grps.sort()
        grps.remove(gid)
    else:
        grps = list()
    grps.insert(0, gid)

    # index 0 reserved for primary user quota
    uql.append(call_beegfs_ctl(USRQUOTA, path, uid))

    # index 1 reserved for primary group quota, followed by supplementary groups
    for g in grps:
        uql.append(call_beegfs_ctl(GRPQUOTA, path, g))

    return [] if ((uql[0] is None) or (uql[1] is None)) else uql

if __name__ == "__main__":
    path = "/common"
    ql = bquota_get(path, True)
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
            path,
            q.dqb_curspace / (1 << 10), q.dqb_bhardlimit,
            q.dqb_curinodes, q.dqb_ihardlimit)
