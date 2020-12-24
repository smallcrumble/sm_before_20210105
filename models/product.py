# -*- coding: utf-8 -*-

from odoo import models, fields


class ProductTemplate(models.Model):
	_inherit = "product.template"
	
	uom_id1 = fields.Many2one('uom.uom', 'UoM 1', help="Extra unit of measure.")
	uom_id2 = fields.Many2one('uom.uom', 'UoM 2', help="Extra unit of measure.")
	qty_available1 = fields.Float(
		'Quantity On Hand', compute='_compute_quantities', search='_search_qty_available',
		compute_sudo=False, digits='Product Unit of Measure')
	qty_available2 = fields.Float(
		'Quantity On Hand', compute='_compute_quantities', search='_search_qty_available',
		compute_sudo=False, digits='Product Unit of Measure')
	#qty1 = fields.Float('Qty 1')
	#qty2 = fields.Float('Qty 2')
	_defaults = {
		'type' : 'product'
	}

	@api.depends_context('company')
	def _compute_quantities(self):
		res = self._compute_quantities_dict()
		for template in self:
			template.qty_available = res[template.id]['qty_available']
			template.qty_available1 = res[template.id]['qty_available1']
			template.qty_available2 = res[template.id]['qty_available2']
			template.virtual_available = res[template.id]['virtual_available']
			template.incoming_qty = res[template.id]['incoming_qty']
			template.outgoing_qty = res[template.id]['outgoing_qty']

	def _compute_quantities_dict(self):
		# TDE FIXME: why not using directly the function fields ?
		variants_available = self.with_context(active_test=False).mapped('product_variant_ids')._product_available()
		prod_available = {}
		for template in self:
			qty_available = 0
			qty_available1 = 0
			qty_available2 = 0
			virtual_available = 0
			incoming_qty = 0
			outgoing_qty = 0
			for p in template.with_context(active_test=False).product_variant_ids:
				qty_available += variants_available[p.id]["qty_available"]
				qty_available1 += variants_available[p.id]["qty_available1"]
				qty_available2 += variants_available[p.id]["qty_available2"]
				virtual_available += variants_available[p.id]["virtual_available"]
				incoming_qty += variants_available[p.id]["incoming_qty"]
				outgoing_qty += variants_available[p.id]["outgoing_qty"]
			prod_available[template.id] = {
				"qty_available": qty_available,
				"qty_available1": qty_available1,
				"qty_available2": qty_available2,
				"virtual_available": virtual_available,
				"incoming_qty": incoming_qty,
				"outgoing_qty": outgoing_qty,
			}
		return prod_available