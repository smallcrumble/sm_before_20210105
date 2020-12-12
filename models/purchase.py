# -*- coding: utf-8 -*-

from odoo import models, fields

class PurchaseOrderLine(models.Model):
	_inherit = "purchase.order.line"

	qty1 = fields.Float(string='Qty 1', digits='Product Unit of Measure')
	uom1 = fields.Many2one('uom.uom', string='UoM 1')
	qty2 = fields.Float(string='Qty 2', digits='Product Unit of Measure')
	uom2 = fields.Many2one('uom.uom', string='UoM 2')

	def _prepare_stock_move_vals(self, picking, price_unit, product_uom_qty, product_uom):
		res = super(PurchaseOrderLine, self)._prepare_stock_move_vals(picking, price_unit, product_uom_qty, product_uom)
		res['qty1']=self.qty1
		res['uom1']=self.uom1.id
		res['qty2']=self.qty2
		res['uom2']=self.uom2.id
		return res