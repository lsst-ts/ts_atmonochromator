#!/usr/bin/env python

import asyncio

from lsst.ts.atmonochromator import MonochromatorCsc

asyncio.run(MonochromatorCsc.amain(index=None))
