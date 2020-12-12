# -*- coding: utf-8 -*-

from odoo import models, fields

class PurchaseOrderLine(models.Model):
	_inherits = "purchase.order.line"

	qty1 = fields.Float(string='Qty 1', digits='Product Unit of Measure')
	uom1 = fields.Many2one('uom.uom', string='UoM 1')
	qty2 = fields.Float(string='Qty 2', digits='Product Unit of Measure')
	uom2 = fields.Many2one('uom.uom', string='UoM 2')

	def _prepare_stock_move_vals(self, picking, price_unit, product_uom_qty, product_uom):
		self.ensure_one()
		product = self.product_id.with_context(lang=self.order_id.dest_address_id.lang or self.env.user.lang)
		description_picking = product._get_description(self.order_id.picking_type_id)
		if self.product_description_variants:
			description_picking += self.product_description_variants
		date_planned = self.date_planned or self.order_id.date_planned
		return {
			# truncate to 2000 to avoid triggering index limit error
			# TODO: remove index in master?
			'name': (self.name or '')[:2000],
			'product_id': self.product_id.id,
			'date': date_planned,
			'date_deadline': date_planned + relativedelta(days=self.order_id.company_id.po_lead),
			'location_id': self.order_id.partner_id.property_stock_supplier.id,
			'location_dest_id': (self.orderpoint_id and not (self.move_ids | self.move_dest_ids)) and self.orderpoint_id.location_id.id or self.order_id._get_destination_location(),
			'picking_id': picking.id,
			'partner_id': self.order_id.dest_address_id.id,
			'move_dest_ids': [(4, x) for x in self.move_dest_ids.ids],
			'state': 'draft',
			'purchase_line_id': self.id,
			'company_id': self.order_id.company_id.id,
			'price_unit': price_unit,
			'picking_type_id': self.order_id.picking_type_id.id,
			'group_id': self.order_id.group_id.id,
			'origin': self.order_id.name,
			'description_picking': description_picking,
			'propagate_cancel': self.propagate_cancel,
			'route_ids': self.order_id.picking_type_id.warehouse_id and [(6, 0, [x.id for x in self.order_id.picking_type_id.warehouse_id.route_ids])] or [],
			'warehouse_id': self.order_id.picking_type_id.warehouse_id.id,
			'product_uom_qty': product_uom_qty,
			'product_uom': product_uom.id,
			'qty1' : self.qty1,
			'uom1' : self.uom1.id,
		}
