#!/usr/bin/env python
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

"""
python collections type "if_quotactl" based off of "struct if_quotactl"
please see the following lustre source files for details:
   lustre/utils/lfs.c
   lustre/include/lustre/lustre_user.h
"""
    
import os
import collections
import fcntl
import struct

LL_IOC_QUOTACTL = 0xc0b066a2
LUSTRE_Q_GETQUOTA = 0x800007

USRQUOTA = 0
GRPQUOTA = 1
UGQUOTA = 2

fmt_obd_dqinfo = "2L2I"
fmt_obd_dqblk = "8L2I"
fmt_obd_type = "16c"
fmt_obd_uuid = "40c"
fmt_if_quotactl = "6I" + fmt_obd_dqinfo + fmt_obd_dqblk + \
                         fmt_obd_type + fmt_obd_uuid

if_quotactl = collections.namedtuple("if_quotactl",
                                     [
                                       "qc_type",
                                       "qc_id",
                                       "dqb_bhardlimit",
                                       "dqb_bsoftlimit",
                                       "dqb_curspace",
                                       "dqb_ihardlimit",
                                       "dqb_isoftlimit",
                                       "dqb_curinodes"
                                     ])

def lquota_if_quotactl(q):
    """defines and returns a "if_quotactl" named tuple from passed in tuple"""
    return if_quotactl(q[1], q[2], q[10], q[11], q[12], q[13], q[14], q[15])

def lquota_ioctl(fd, lq_type, lq_id):
    """calls lustre ioctl LL_IOC_QUOTACTL"""
    if_quotactl = struct.pack(fmt_if_quotactl, LUSTRE_Q_GETQUOTA,
                              lq_type, lq_id, 0, 0, 0,
                              *(([0] * 4) + ([0] * 10) +
                               (['\0'] * 16) + (['\0'] * 40)))
    return fcntl.ioctl(fd, LL_IOC_QUOTACTL, if_quotactl)

def lquota_get(lq_path):
    """returns Lustre quota information for the calling process UID/GID(s)"""
    ret_lq = []
    fd = os.open(lq_path, os.O_RDONLY | os.O_NONBLOCK | os.O_DIRECTORY)

    q = lquota_ioctl(fd, USRQUOTA, os.geteuid())
    ret_lq.append(lquota_if_quotactl(struct.unpack(fmt_if_quotactl, q)))

    # place primary GID at the start of the list
    gid = os.getgid()
    grps = os.getgroups()
    grps.sort()
    grps.remove(gid)
    grps.insert(0, gid)

    for g in grps:
        q = lquota_ioctl(fd, GRPQUOTA, g)
        ret_lq.append(lquota_if_quotactl(struct.unpack(fmt_if_quotactl, q)))

    os.close(fd)

    return ret_lq

if __name__ == "__main__":
    path = "/lustre"
    ql = lquota_get(path)
    m = [
            "user quota",
            "group quota",
        ]
    # are quotas enabled?
    for q in ql:
        print "{0} {1} for {2} is {3}/{4} KiB {5}/{6} files".format(
            q.qc_id,
            m[q.qc_type],
            path,
            q.dqb_curspace / (1 << 10), q.dqb_bhardlimit,
            q.dqb_curinodes, q.dqb_ihardlimit)
