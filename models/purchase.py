# -*- coding: utf-8 -*-

from odoo import models, fields

class PurchaseOrderLine(models.Model):
	_inherit = "purchase.order.line"

	qty1 = fields.Float(string='Qty 1', digits='Product Unit of Measure')
	uom1 = fields.Many2one('uom.uom', string='UoM 1')
	qty2 = fields.Float(string='Qty 2', digits='Product Unit of Measure')
	uom2 = fields.Many2one('uom.uom', string='UoM 2')