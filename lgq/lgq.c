
/*
 *  lgq: lustre group quota
 *
 *  2013-03-03 Josh Samuelson
 *
 *  Outputs a python parsable data structure containing all the UIDs that
 *  are members of the calling process group(s).
 *
 *  How to build:
 *
 *  Have a configured Lustre source tree somewhere:
 *      cd /path/to/lustre.git
 *      git archive --prefix=lustre.tag/ lustre.tag | tar -C /tmp -vpxf -
 *      cd /tmp/lustre.tag/
 *      sh autogen.sh
 *      # With the interest of saving time and just getting a source
 *      # tree we can build against
 *      ./configure --disable-doc --disable-manpages --disable-utils \
 *                  --disable-client --disable-server --disable-modules
 *  cd /path/to/lgq
 *  ln -s /tmp/lustre.tag lustre
 *  make
 *
 *  Must be SUID-root to function: chown root.root lgq ; chmod 4511 lgq
 */

#define _GNU_SOURCE
#include <dirent.h>
#include <fcntl.h>
#include <pwd.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <asm/ioctl.h>

#include <lustre/lustre_user.h>

#include "source_code.h"

#ifndef USRQUOTA
#define USRQUOTA 0
#endif  
#ifndef GRPQUOTA
#define GRPQUOTA 1
#endif  

#define MAX_GROUP_MEMBERS 100
struct grp_mbrs
{
    struct if_quotactl qctl[MAX_GROUP_MEMBERS];
    unsigned int count;
};

#define MAX_SUPPLEMENTARY_GROUPS 20

struct res_uid
{
    uid_t ruid,
          euid,
          suid;
};

#define LUSTRE_MOUNT_POINT "/lustre"

#ifdef DEBUG
void
uid_state(const char *func)
{
    struct res_uid u;

    if (getresuid(&u.ruid, &u.euid, &u.suid) < 0)
    {
        return;
    }
    printf("%s: r:%u e:%u s:%u\n", func, u.ruid, u.euid, u.suid);
}
#else
void
uid_state(const char *func)
{
    ;
}
#endif

int
lquota(char *lmnt,
       struct grp_mbrs *gm,
       struct res_uid *u)
{
    int fd,
        rc = -1;
    unsigned int idx;
    DIR *dp;

    dp = opendir(lmnt);
    if (!dp)
    {
        return -1;
    }

    fd = dirfd(dp);

    uid_state(__FUNCTION__);
    if (setresuid(-1, u->suid, -1) < 0)
    {
        rc = -1;
        goto out;
    }
    uid_state(__FUNCTION__);

    for (idx = 0; idx < gm->count; idx++)
    {
        rc = ioctl(fd, LL_IOC_QUOTACTL, &gm->qctl[idx]);
        if (rc < 0)
            continue;
    }

    uid_state(__FUNCTION__);
    if (setresuid(-1, u->ruid, u->ruid) < 0)
    {
        rc = -1;
    }
    uid_state(__FUNCTION__);

out:

    closedir(dp);

    return rc;
}

void
p_if_quotactl(struct if_quotactl *qctl)
{
    printf("if_quotactl(qc_type=%u,qc_id=%u,dqb_bhardlimit=%llu,"
           "dqb_bsoftlimit=%llu,dqb_curspace=%llu,dqb_ihardlimit=%llu,"
           "dqb_isoftlimit=%llu,dqb_curinodes=%llu)",
           qctl->qc_type,
           qctl->qc_id,
           qctl->qc_dqblk.dqb_bhardlimit,
           qctl->qc_dqblk.dqb_bsoftlimit,
           qctl->qc_dqblk.dqb_curspace,
           qctl->qc_dqblk.dqb_ihardlimit,
           qctl->qc_dqblk.dqb_isoftlimit,
           qctl->qc_dqblk.dqb_curinodes);
}

void
print(struct grp_mbrs *gm)
{
    int comma = 0;
    unsigned int idx;

    printf("[");
    for (idx = 0; idx < gm->count ; idx++)
    {
        if (comma)
        {
            printf(",");
        }
        else
        {
            comma = 1;
        }
        p_if_quotactl(&gm->qctl[idx]);
    }
    printf("]");
}

int
get_group_members(struct grp_mbrs *gm)
{
    int rc,
        idx;
    struct passwd *p;
    gid_t gid[MAX_SUPPLEMENTARY_GROUPS];

    memset(gm, 0, sizeof(*gm));

    if ((rc = getgroups(MAX_SUPPLEMENTARY_GROUPS, gid)) <= 0)
    {
        return -1;
    }

    setpwent();
    while ((p = getpwent()) != NULL)
    {
        for (idx = 0; idx < rc; idx++)
        {
            if (p->pw_gid == gid[idx])
            {
                if (gm->count < MAX_GROUP_MEMBERS)
                {
                    gm->qctl[gm->count].qc_cmd = LUSTRE_Q_GETQUOTA;
                    gm->qctl[gm->count].qc_type = USRQUOTA;
                    gm->qctl[gm->count].qc_id = p->pw_uid;
                    gm->count++;
                }
                else
                {
                    break;
                }
            }
        }
    }
    endpwent();

    if (!gm->count)
    {
        return -1;
    }

    return 0;
}

int
main(int argc,
     char **argv)
{
    struct res_uid u;
    struct grp_mbrs gm;

    uid_state(__FUNCTION__);
    if (getresuid(&u.ruid, &u.euid, &u.suid) < 0)
    {
        return -1;
    }
    if (setresuid(-1, u.ruid, u.euid) < 0)
    {
        return -1;
    }
    uid_state(__FUNCTION__);

    if (get_group_members(&gm) < 0)
    {
        return -1;
    }

    if (lquota(LUSTRE_MOUNT_POINT, &gm, &u) < 0)
    {
        return -1;
    }

    print(&gm);

    return 0;
}
