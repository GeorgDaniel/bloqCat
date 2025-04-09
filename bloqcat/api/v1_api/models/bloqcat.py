"""Module containing all API schemas for the bloqcat aggregation API."""

import marshmallow as ma
from ...util import MaBaseSchema

__all__ = ["TopologySchema"]


class TopologySchema(MaBaseSchema):
    topology_xml = ma.fields.String(required=True, allow_none=False, dump_only=True)
