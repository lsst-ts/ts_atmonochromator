# This file is part of ts_atmonochromator.
#
# Developed for Vera C. Rubin Observatory Telescope and Site Systems.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License

__all__ = ["CONFIG_SCHEMA"]

import yaml

CONFIG_SCHEMA = yaml.safe_load(
    """
$schema: http://json-schema.org/draft-07/schema#
$id: https://github.com/lsst-ts/ts_atmonochromator/blob/master/schema/ATMonochromator.yaml
# title must end with one or more spaces followed by the schema version, which must begin with "v"
title: ATMonochromator v2
description: Schema for ATMonochromator configuration files
type: object
properties:
  host:
    type: string
    description: IP for the controller.
  port:
    type: integer
    description: Port for the controller.
  connection_timeout:
    type: number
    description: Connection timeout (seconds).
  read_timeout:
    type: number
    description: Timeout for receiving data from the controller (seconds).
  write_timeout:
    type: number
    description: Timeout for writing data to the controller (seconds).
  wavelength_gr1:
    type: number
    description: Minimum wavelength to use with Grating 1 (nm).
  wavelength_gr1_gr2:
    type: number
    description: Wavelength to use to change to Grating 2 (nm).
  wavelength_gr2:
    type: number
    description: Maximum wavelength to use with Grating 2 (nm).
  min_slit_width:
    type: number
    description: Minimum acceptable Slit width (mm).
  max_slit_width:
    type: number
    description: Maximum acceptable Slit Width (mm).
  min_wavelength:
    type: number
    description: Minimum acceptable wavelength (nm).
  max_wavelength:
    type: number
    description: Maximum acceptable Wavelength (nm).
  period:
    type: number
    description: Controller internal heartbeat cycle period (seconds).
  timeout:
    type: number
    description: Time out for the heartbeat to test communication to the controller (seconds).
additionalProperties: false
"""
)
