# -*- coding: utf-8 -*-

from odoo import models, fields


class ProductTemplate(models.Model):
	_inherit = "product.template"
	
	uom_id2 = fields.Many2one('uom.uom', 'Unit of Measure 2', help="Extra unit of measure.")
	uom_id3 = fields.Many2one('uom.uom', 'Unit of Measure 3', help="Extra unit of measure.")
	qty2 = fields.Float()
	qty3 = fields.Float()