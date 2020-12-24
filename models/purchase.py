# -*- coding: utf-8 -*-

from odoo import models, fields
from odoo.tools.misc import formatLang, get_lang

class PurchaseOrderLine(models.Model):
	_inherit = "purchase.order.line"

	#qty1 = fields.Float(string='Qty 1', digits='Product Unit of Measure')
	product_qty1 = fields.Float(string='Quantity 1', digits='Product Unit of Measure')	
	#qty2 = fields.Float(string='Qty 2', digits='Product Unit of Measure')
	product_qty2 = fields.Float(string='Quantity 2', digits='Product Unit of Measure')
	#uom1 = fields.Many2one('uom.uom', string='UoM 1')
	product_uom1 = fields.Many2one('uom.uom', string='UoM 1', domain="[('category_id', '=', product_uom_category_id)]")
	#uom2 = fields.Many2one('uom.uom', string='UoM 2')
	product_uom2 = fields.Many2one('uom.uom', string='UoM 2', domain="[('category_id', '=', product_uom_category_id)]")

	def _prepare_stock_move_vals(self, picking, price_unit, product_uom_qty, product_uom):
		res = super(PurchaseOrderLine, self)._prepare_stock_move_vals(picking, price_unit, product_uom_qty, product_uom)
		res['product_uom_qty1']=self.product_qty1
		res['product_uom1']=self.product_uom1.id
		res['product_uom_qty2']=self.product_qty2
		res['product_uom2']=self.product_uom2.id
		return res

	def _product_id_change(self):
		if not self.product_id:
			return

		self.product_uom = self.product_id.uom_po_id or self.product_id.uom_id
		self.product_uom1 = self.product_id.uom_id1
		self.product_uom2 = self.product_id.uom_id2
		product_lang = self.product_id.with_context(
			lang=get_lang(self.env, self.partner_id.lang).code,
			partner_id=self.partner_id.id,
			company_id=self.company_id.id,
		)
		self.name = self._get_product_purchase_description(product_lang)

		self._compute_tax_id()