# -*- coding: utf-8 -*-

from odoo import models, fields

class PurchaseOrderLine(models.Model):
	_inherit = "purchase.order.line"

	product_qty2 = fields.Float(string='Quantity 2', digits='Product Unit of Measure')
	product_uom2 = fields.Many2one('uom.uom', string='Unit of Measure 2')
	product_qty3 = fields.Float(string='Quantity 3', digits='Product Unit of Measure')
	product_uom3 = fields.Many2one('uom.uom', string='Unit of Measure 3')