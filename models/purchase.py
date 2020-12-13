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

	def _product_id_change(self):
		if not self.product_id:
			return

		self.product_uom = self.product_id.uom_po_id or self.product_id.uom_id
		self.uom1 = self.product_id.uom1
		self.uom2 = self.product_id.uom2
		product_lang = self.product_id.with_context(
			lang=get_lang(self.env, self.partner_id.lang).code,
			partner_id=self.partner_id.id,
			company_id=self.company_id.id,
		)
		self.name = self._get_product_purchase_description(product_lang)

		self._compute_tax_id()