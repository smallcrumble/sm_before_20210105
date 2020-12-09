# -*- coding: utf-8 -*-

from odoo import models, fields


class ProductTemplate(models.Model):
	_inherit = "product.template"
	
	uom_id2 = fields.Many2one('uom.uom', 'UoM 2', help="Extra unit of measure.")
	uom_id3 = fields.Many2one('uom.uom', 'UoM 3', help="Extra unit of measure.")
	qty2 = fields.Float()
	qty3 = fields.Float()