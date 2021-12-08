# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from dateutil.relativedelta import relativedelta
from libmozdata.hgmozilla import Mercurial, Revision
from libmozdata import utils as lmdutils
import re
import requests
from . import buildhub, hgauthors, models, utils


BACKOUT_PAT = re.compile(
    r"^(?:(?:back(?:ed|ing|s)?(?:[ _]*out[_]?))|(?:revert(?:ing|s)?)) (?:(?:cset|changeset|revision|rev|of)s?)?",
    re.I | re.DOTALL,
)
BUG_PAT = re.compile(r"^bug[ \t]*([0-9]+)", re.I)


def is_backed_out(desc):
    """Check the patch description to know if we've a backout or not"""
    return BACKOUT_PAT.match(desc) is not None


def get_bug(desc):
    """Get a bug number from the patch description"""
    m = BUG_PAT.search(desc)
    if m:
        return int(m.group(1))
    return -1


def collect(data, file_filter):
    """Collect the data we need in the pushlog got from hg.mozilla.org"""
    res = []
    for push in data["pushes"].values():
        pushdate = lmdutils.get_date_from_timestamp(push["date"])
        for chgset in push["changesets"]:
            files = [f for f in chgset["files"] if file_filter(f)]
            desc = chgset["desc"]
            author = chgset["author"]
            res.append(
                {
                    "date": pushdate,
                    "node": utils.short_rev(chgset["node"]),
                    "backedout": is_backed_out(desc),
                    "files": files,
                    "merge": len(chgset["parents"]) > 1,
                    "bug": get_bug(desc),
                    "author": hgauthors.analyze_author(author),
                }
            )
    return res


def pushlog(
    startdate, enddate, channel="nightly", file_filter=utils.is_interesting_file
):
    """Get the pushlog from hg.mozilla.org"""
    # Get the pushes where startdate <= pushdate <= enddate
    # pushlog uses strict inequality, it's why we add +/- 1 second
    fmt = "%Y-%m-%d %H:%M:%S"
    startdate -= relativedelta(seconds=1)
    startdate = startdate.strftime(fmt)
    enddate += relativedelta(seconds=1)
    enddate = enddate.strftime(fmt)
    url = "{}/json-pushes".format(Mercurial.get_repo_url(channel))
    r = requests.get(
        url,
        params={"startdate": startdate, "enddate": enddate, "version": 2, "full": 1},
    )
    return collect(r.json(), file_filter)


def pushlog_for_revs(
    startrev, endrev, channel="nightly", file_filter=utils.is_interesting_file
):
    """Get the pushlog from startrev to endrev"""
    # startrev is not include in the pushlog
    url = "{}/json-pushes".format(Mercurial.get_repo_url(channel))
    r = requests.get(
        url,
        params={"fromchange": startrev, "tochange": endrev, "version": 2, "full": 1},
    )
    return collect(r.json(), file_filter)


def pushlog_for_revs_url(startrev, endrev, channel):
    """Get the pushlog url from startrev to endrev"""
    return "{}/pushloghtml?fromchange={}&tochange={}".format(
        Mercurial.get_repo_url(channel), startrev, endrev
    )


def pushlog_for_buildid(
    buildid, channel, product, file_filter=utils.is_interesting_file
):
    """Get the pushlog for a buildid/channel/product"""
    data = buildhub.get_two_last(buildid, channel, product)
    if data:
        startrev = data[0]["revision"]
        endrev = data[1]["revision"]
        return pushlog_for_revs(
            startrev, endrev, channel=channel, file_filter=file_filter
        )
    return None


def pushlog_for_buildid_url(buildid, channel, product):
    """Get the pushlog url for a buildid/channel/product"""
    data = models.Build.get_two_last(utils.get_build_date(buildid), channel, product)
    if len(data) != 2:
        data = buildhub.get_two_last(buildid, channel, product)
    if data:
        startrev = data[0]["revision"]
        endrev = data[1]["revision"]
        return pushlog_for_revs_url(startrev, endrev, channel)
    return None


def pushlog_for_pushdate_url(pushdate, channel, product):
    """Get the pushlog url for the build containing pushdate"""
    data = buildhub.get_enclosing_builds(pushdate, channel, product)
    if data:
        startrev = data[0]["revision"]
        if data[1] is None:
            endrev = "tip"
        else:
            endrev = data[1]["revision"]
        return pushlog_for_revs_url(startrev, endrev, channel)
    return None


def pushlog_for_rev_url(revision, channel, product):
    """Get the pushlog url for the build containing revision"""
    data = Revision.get_revision(channel=channel, node=revision)
    pushdate = lmdutils.get_date_from_timestamp(data["pushdate"][0])
    return pushlog_for_pushdate_url(pushdate, channel, product)
