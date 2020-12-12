# -*- coding: utf-8 -*-

from odoo import models, fields


class ProductTemplate(models.Model):
	_inherit = "product.template"
	
	uom1 = fields.Many2one('uom.uom', 'UoM 1', help="Extra unit of measure.")
	uom2 = fields.Many2one('uom.uom', 'UoM 2', help="Extra unit of measure.")
	qty1 = fields.Float('Qty 1')
	qty2 = fields.Float('Qty 2')