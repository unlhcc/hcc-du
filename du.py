#!/usr/bin/python
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

# WP/Warning Percentages for blocks and files/inodes
# users
WP_UB = .65
WP_UI = .25
# groups
WP_GB = .75
WP_GI = .75
# all the things (tm)
WP_AB = .85
WP_AI = .85

WARNING_MESSAGE    = \
"**ATTENTION** Please clean what you can from /work **ATTENTION**"

LUSTRE_MOUNT_POINT = "/lustre"
GROUP_QUOTA_BINARY = "/util/opt/bin/hcc/lgq"

import collections
import sys
import math
import operator
import subprocess
from colors import color
from os import getuid, stat, statvfs
from rquota import USRQUOTA, GRPQUOTA, rquota_t, rquota_get, \
                   rquota_find_home_mount
from lquota import if_quotactl, lquota_get
from pwd import getpwuid
from grp import getgrgid
from optparse import OptionParser

def get_bar(
        opts,
        txt = None,
        used = 0,
        total = 100,
        length = 30,
        unit = 'GB',
    ):
    """Return a bar graphic indicating disk usage"""

    # Consider no quota as positive infinity
    if total is None:
        total = float("inf")

    try:
        percent = 100.0 * used / total
    except ZeroDivisionError:
        percent = 0.0

    # If percent usage is <= val, use color/style for bar background
    colors = [
        { 'val':           65, 'color': 'green',
          'style': 'negative+underline' },
        { 'val':           85, 'color': 'yellow',
          'style': 'bold+negative+underline' },
        { 'val': float("inf"), 'color': 'red',
          'style': 'blink+bold+negative+underline' },
    ]

    bar_color = ''
    bar_style = 'underline'
    for k in colors:
        if percent <= k['val']:
            if opts.color == "a":
                bar_color = k['color']
            if opts.reverse:
                bar_style = k['style']
            break

    # The remainder is filled with the following style
    fill_style = ''
    if opts.color == "a" or opts.reverse:
        fill_style = 'underline'
        
    # Reduce the length to account for the two brackets on the ends
    length = length - 2

    # Num chars in bar which are marked used
    try:
        used_len = int(math.ceil(1.0 * length * used / total))
    except ZeroDivisionError:
        used_len = 0

    # Space usage description
    # Example: 10% (10 / 100GB)
    if txt is None:
        txt = "{percent:.1f}% ({used:.0f}/{total:.0f}{unit})".format(
            percent = percent,
            used = round(used),
            total = round(total),
            unit = unit,
        )

    # Pad description to bar length
    txt = txt.ljust(length)[:length]

    ret = ''
    ret += color('[')
    if opts.fill:
        ret += color(txt[:used_len].replace(' ', '='),
                     bg = bar_color, style = bar_style)
        ret += color(txt[used_len:].replace(' ', '-'), style = fill_style)
    else:
        ret += color(txt[:used_len], bg = bar_color, style = bar_style)
        ret += color(txt[used_len:],                 style = fill_style)
    ret += color(']')

    return ret

def get_window_size():
    """Return window size as rows, columns"""
    import sys, fcntl, termios, struct
    try:
        data = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, 'xxxx')
    except:
        return (24, 80)
    return struct.unpack('hh', data)

def equal_split(length, count):
    """Split length into "count" of integer pieces where pieces are
       approximately equal and sum(pieces) = length"""
    pieces = []

    while True:
        if count < 1: break
        i = int(math.floor(1.0 * length / count))
        pieces.append(i)
        length -= i
        count -= 1

        if count < 1: break
        i = int(math.ceil(1.0 * length / count))
        pieces.append(i)
        length -= i
        count -= 1

    return pieces

def group_lquota():
    """Calls out to suid-root binary to collect all group member UIDs' quota
       that the calling process is a member of"""
    proc = subprocess.Popen([ GROUP_QUOTA_BINARY ],
                            stdout = subprocess.PIPE)
    output = proc.stdout
    lgq = output.read()
    output.close()

    if proc.wait() != 0:
        print "Group quota not available, please try again later."
        sys.exit(proc.returncode)

    # TODO, import the data without eval
    return eval(lgq)
    
def group_quota_display(opts, gq):
    if opts.group == "b":
        sort_idx = 4
    elif opts.group == "i":
        sort_idx = 7
    else:
        sort_idx = 4
        
    gq = sorted(gq, key = operator.itemgetter(sort_idx), reverse = True)

    print "{0}{1}{2}{3}" \
          .format("Group ID".rjust(20, " "),
          "User ID".rjust(20, " "),
          "Disk Usage".rjust(16, " "),
          "File Count".rjust(16, " "))
    for u in gq:
        pwe = getpwuid(u.qc_id)
        gre = getgrgid(pwe.pw_gid)
        print "{0}{1}{2} GB{3}" \
              .format(gre.gr_name.rjust(20, " "),
              pwe.pw_name.rjust(20, " "),
              str(u.dqb_curspace / 2 ** 30).rjust(16 - len(" GB"), " "),
              str(u.dqb_curinodes).rjust(16, " "))

def main_group(opts):
    """display sorted group member disk usage"""
    gq = group_lquota()
    group_quota_display(opts, gq)
    try:
        sys.stdout.close()
    except:
        pass

def min_not_0(a, b):
    """return the minimum value that is not zero"""
    if a and b:
        return a if a < b else b
    if a:
        return a
    else:
        return b

ds_t = collections.namedtuple("ds_t",
                              [
                                  "bc",
                                  "bh",
                                  "ic",
                                  "ih"
                              ])

def disk_stats(type, ts, pwe, gre, quota, svfs, stat):
    """return the appropriate text message along with the used and size of
       space allocated along with file counts for the calling user on the
       filesystem in question"""

    # text message to override default
    txt = None
    # blocks current in bytes
    bc = 0
    # blocks hard limit in KB
    bh = 0
    # inodes/files current
    ic = 0 
    # inodes/files hard limit
    ih = 0

    # blocks
    used = svfs.f_bsize * (svfs.f_blocks - svfs.f_bavail)
    size = svfs.f_bsize *  svfs.f_blocks / (2 ** 10)
    # inodes
    file = svfs.f_files - svfs.f_favail
    max  = svfs.f_files

    # quota info for primary UID/GID of calling user
    if type == USRQUOTA or type == GRPQUOTA:
        # Do we have quota data?
        if len(quota):
            # Calling user's used space is based on type.
            bc = quota[type].dqb_curspace
            ic = quota[type].dqb_curinodes
            # The size will be the smaller of USRQUOTA, GRPQUOTA or
            # filesystem size, whichever the user is likely to run into first.
            if type == USRQUOTA:
                bh = min_not_0(min_not_0(quota[USRQUOTA].dqb_bhardlimit,
                                         quota[GRPQUOTA].dqb_bhardlimit),
                               size)
                ih = min_not_0(min_not_0(quota[USRQUOTA].dqb_ihardlimit,
                                         quota[GRPQUOTA].dqb_ihardlimit),
                               max)
            else:
                bh = min_not_0(quota[GRPQUOTA].dqb_bhardlimit, size)
                ih = min_not_0(quota[GRPQUOTA].dqb_ihardlimit, max)
        # No quota data, go with the filesystem stats
        else:
            # Does the user own the mount point?
            if stat.st_uid == pwe.pw_uid:
                # If so, the filesystem stats should suffice for the user.
                if type == USRQUOTA:
                    bc = used
                    bh = size
                    ic = file
                    ih = max
                # GRPQUOTA
                else:
                    txt = "user unique, see above"
            # Does the calling user's group own the mount point?
            elif stat.st_gid == pwe.pw_gid:
                # We don't have stats on disk space used by the user.
                if type == USRQUOTA:
                    txt = ts + " disk usage not tracked"
                # If so, the filesystem stats should suffice for the group.
                else:
                    bc = used
                    bh = size
                    ic = file
                    ih = max
            # mount not user or group owned.
            else:
                txt = ts + " disk usage not tracked"
    # quota info for supplementary group
    elif type > GRPQUOTA:
        # Do we have quota data?
        if len(quota):
            # Calling supplementary group's used space
            bc = quota[type].dqb_curspace
            ic = quota[type].dqb_curinodes
            # use the bhardlimit if set, otherwise the filesystem size
            bh = min_not_0(quota[type].dqb_bhardlimit, size)
            ih = min_not_0(quota[type].dqb_ihardlimit, max)
        else:
            txt = ts + " disk usage not tracked"
    # other/-1 filesystem stats
    else:
        if stat.st_uid == pwe.pw_uid:
            txt = "user unique, see above"
        elif stat.st_gid == pwe.pw_gid:
            txt = "group unique, see above"
        else:
            bc = used
            bh = size
            ic = file
            ih = max

    return (txt, ds_t(bc, bh, ic, ih))

def get_stats(rows, columns,
              type, pwe, gre,
              hquota, hsvfs, hstat,
              wquota, wsvfs, wstat):
    """return USRQUOTA, GRPQUOTA or "other/-1" stats for home and work"""

    # print tuple, set below
    pt = None
    # text message if not "percent% (usage/sizeGB)"
    htxt = None
    wtxt = None

    if type == USRQUOTA or type == GRPQUOTA:
        pt = ("user", pwe.pw_name) if type == USRQUOTA else \
             ("primary group", gre.gr_name)
    elif type > GRPQUOTA:
        pt = ("supplementary group", gre.gr_name)
    else:
        pt = ("all HCC", "groups")

    htxt, hds = disk_stats(type, pt[0], pwe, gre,
                           hquota, hsvfs, hstat)
    wtxt, wds = disk_stats(type, pt[0], pwe, gre,
                           wquota, wsvfs, wstat)

    return (pt[0], pt[1], htxt, hds, wtxt, wds)

WARN_H = 0x01 # involves home file system
WARN_W = 0x02 # involves work file system

WARN_B = 0x04 # warn block usage
WARN_I = 0x08 # warn inode usage

WARN_U = 0x10 # warn for user  usage
WARN_G = 0x20 # warn for group usage
WARN_A = 0x40 # warn for all   usage

def qcheck(type, hds, wds):
    """Check the state of the calling users quota and return a number"""
    ret = 0
    # check the WP_ or "warning percentages"
    if type == USRQUOTA:
        if hds.bh and 1.0 * hds.bc / (hds.bh * (2 ** 10)) > WP_UB:
            ret |= WARN_U | WARN_H | WARN_B
        if hds.ih and 1.0 * hds.ic / hds.ih > WP_UI:
            ret |= WARN_U | WARN_H | WARN_I
        if wds.bh and 1.0 * wds.bc / (wds.bh * (2 ** 10)) > WP_UB:
            ret |= WARN_U | WARN_W | WARN_B
        if wds.ih and 1.0 * wds.ic / wds.ih > WP_UI:
            ret |= WARN_U | WARN_W | WARN_I
    elif type >= GRPQUOTA:
        if hds.bh and 1.0 * hds.bc / (hds.bh * (2 ** 10)) > WP_GB:
            ret |= WARN_G | WARN_H | WARN_B
        if hds.ih and 1.0 * hds.ic / hds.ih > WP_GI:
            ret |= WARN_G | WARN_H | WARN_I
        if wds.bh and 1.0 * wds.bc / (wds.bh * (2 ** 10)) > WP_GB:
            ret |= WARN_G | WARN_W | WARN_B
        if wds.ih and 1.0 * wds.ic / wds.ih > WP_GI:
            ret |= WARN_G | WARN_W | WARN_I
    else:
        if hds.bh and 1.0 * hds.bc / (hds.bh * (2 ** 10)) > WP_AB:
            ret |= WARN_A | WARN_H | WARN_B
        if hds.ih and 1.0 * hds.ic / hds.ih > WP_AI:
            ret |= WARN_A | WARN_H | WARN_I
        if wds.bh and 1.0 * wds.bc / (wds.bh * (2 ** 10)) > WP_AB:
            ret |= WARN_A | WARN_W | WARN_B
        if wds.ih and 1.0 * wds.ic / wds.ih > WP_AI:
            ret |= WARN_A | WARN_W | WARN_I
    return ret

def display_usage(rows, columns,
                  type, pwe, gre,
                  hquota, hsvfs, hstat,
                  wquota, wsvfs, wstat):
    """default display output"""

    # ts: type string
    # tn: type name
    # [h|w]: home or work
    # [h|w]ds: disk stats (txt, ds_t(bc, bh, ic, ih))
    # txt: text message to override default
    # bc: blocks current in bytes
    # bh: blocks hard limit in KB
    # ic: inodes/files current
    # ih: inodes/files hard limit
    ts, tn, htxt, hds, wtxt, wds = \
        get_stats(rows, columns,
                  type, pwe, gre,
                  hquota, hsvfs, hstat,
                  wquota, wsvfs, wstat)

    # convert to floats so get_bar can round()
    ht = (htxt, 1.0 * hds.bc / 2 ** 30, 1.0 * hds.bh / 2 ** 20)
    wt = (wtxt, 1.0 * wds.bc / 2 ** 30, 1.0 * wds.bh / 2 ** 20)

    # Column widths for home and work (add 2 col margin on the right side)
    p2cw = equal_split(columns - 2, 2)

    # print usage line
    pu = ""
    pu += '  Home ' + get_bar(opts, *ht,
                              length = p2cw.pop() - (len('Home') + 3))
    pu += '  Work ' + get_bar(opts, *wt,
                              length = p2cw.pop() - (len('Work') + 3))
    print "Disk usage for {0} {1}:\n{2}".format(ts, tn, pu)

    return qcheck(type, hds, wds), (hds, wds)

def display_default(rows, columns,
                    pwe, gre,
                    hquota, hsvfs, hstat,
                    wquota, wsvfs, wstat):
    """display primary user, primary group and global filesystem stats"""

    uret, ut = display_usage(rows, columns,
                         USRQUOTA, pwe, gre,
                         hquota, hsvfs, hstat,
                         wquota, wsvfs, wstat)
    gret, gt = display_usage(rows, columns,
                         GRPQUOTA, pwe, gre,
                         hquota, hsvfs, hstat,
                         wquota, wsvfs, wstat)
    aret, at = display_usage(rows, columns,
                         -1      , pwe, gre,
                         hquota, hsvfs, hstat,
                         wquota, wsvfs, wstat)

    return (uret | gret | aret, [ut, gt, at])

def display_sgroups(rows, columns,
                    pwe, gre,
                    hquota, hsvfs, hstat,
                    wquota, wsvfs, wstat):
    """display supplementary group filesystem usage"""
    if len(hquota) > 2 or len(wquota) > 2:
        print "\n"
        i = 2
        for g in wquota[2:]:
            gre = getgrgid(g.qc_id)
            display_usage(rows, columns,
                          i, pwe, gre,
                          hquota, hsvfs, hstat,
                          wquota, wsvfs, wstat)
            i += 1

def scold(reason):
    if reason[0] & WARN_U:
        if reason[0] & WARN_W:
            if reason[0] & WARN_B:
                print repr(reason[1])
                print "you are using {0:.1f}% of your groups space on " \
                      "/work".format( 100.0 * reason[1][0][1].bc /
                                              reason[1][1][1].bc)
    if reason[0] & WARN_G:
        print "your group is doing something wrong, help them"
    if reason[0] & WARN_A:
        if reason[0] & (WARN_W | WARN_B) == (WARN_W | WARN_B):
            print color(WARNING_MESSAGE.center(columns), style = "blink+bold")

def main_default(opts):
    """HCC Disk Usage default output"""

    rows, columns = get_window_size()

    # get pwd/grp entries for calling user
    pwe = getpwuid(getuid())
    gre = getgrgid(pwe.pw_gid)

    # find the filesystem that contains calling user's pw_dir
    home_mount = rquota_find_home_mount()

    # get statvfs and stat info on mount points
    hsvfs = statvfs(home_mount)
    wsvfs = statvfs(LUSTRE_MOUNT_POINT)

    hstat = stat(home_mount)
    wstat = stat(LUSTRE_MOUNT_POINT)

    # get RPC/remote and lustre quota info
    hquota = rquota_get(home_mount)
    wquota = lquota_get(LUSTRE_MOUNT_POINT)


    ret = display_default(rows, columns,
                          pwe, gre,
                          hquota, hsvfs, hstat,
                          wquota, wsvfs, wstat)
    if opts.login and ret[0]:
        scold(ret)

    if opts.sup:
        display_sgroups(rows, columns,
                        pwe, gre,
                        hquota, hsvfs, hstat,
                        wquota, wsvfs, wstat)



if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option("-c", "--color", action = "store", 
                      metavar = "[a|n]", choices = ["a", "n"], default = "a",
                      help = "utilized bar graph has colored background "
                      "'a'/always or 'n'/never, default 'a'")
    parser.add_option("-f", "--fill", action = "store_true", default = False,
                      help = "bar graph is filled with the following " \
                             "characters: '='/utilized '-'/available")
    parser.add_option("-g", "--group", action = "store", type = "choice",
                      metavar = "[b|i]", choices = ["b", "i"],
                      help = "display all member user quotas from your "
                      "group(s) sorted by 'b'/blocks used or 'i'/files used")
    parser.add_option("-l", "--login", action = "store_true", default = False,
                      help = "use with system login profile")
    parser.add_option("-r", "--reverse", action = "store_true", default = False,
                      help = "utilized bar graph is reverse video")
    parser.add_option("-s", "--sup", action = "store_true", default = False,
                      help = "display supplementary group usage")
    (opts, args) = parser.parse_args()

    if opts.group:
        main_group(opts)
    else:
        main_default(opts)
