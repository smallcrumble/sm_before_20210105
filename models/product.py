# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.tools.float_utils import float_round
import logging

_logger = logging.getLogger(__name__)

class Product(models.Model):
	_inherit = "product.product"

	qty_available1 = fields.Float(
        'Quantity On Hand', compute='_compute_quantities', search='_search_qty_available',
        digits='Product Unit of Measure', compute_sudo=False)
	qty_available2 = fields.Float(
        'Quantity On Hand', compute='_compute_quantities', search='_search_qty_available',
        digits='Product Unit of Measure', compute_sudo=False)

	@api.depends('stock_move_ids.product_qty', 'stock_move_ids.state')
	@api.depends_context(
		'lot_id', 'owner_id', 'package_id', 'from_date', 'to_date',
		'location', 'warehouse')
	def _compute_quantities(self):
		products = self.filtered(lambda p: p.type != 'service')
		res = products._compute_quantities_dict(self._context.get('lot_id'), self._context.get('owner_id'), self._context.get('package_id'), self._context.get('from_date'), self._context.get('to_date'))
		for product in products:
			product.qty_available = res[product.id]['qty_available']
			product.qty_available1 = res[product.id]['qty_available1']
			product.qty_available2 = res[product.id]['qty_available2']
			product.incoming_qty = res[product.id]['incoming_qty']
			product.outgoing_qty = res[product.id]['outgoing_qty']
			product.virtual_available = res[product.id]['virtual_available']
			product.free_qty = res[product.id]['free_qty']
		# Services need to be set with 0.0 for all quantities
		services = self - products
		services.qty_available = 0.0
		services.qty_available1 = 0.0
		services.qty_available2 = 0.0
		services.incoming_qty = 0.0
		services.outgoing_qty = 0.0
		services.virtual_available = 0.0
		services.free_qty = 0.0

	def _compute_quantities_dict(self, lot_id, owner_id, package_id, from_date=False, to_date=False):
		domain_quant_loc, domain_move_in_loc, domain_move_out_loc = self._get_domain_locations()
		domain_quant = [('product_id', 'in', self.ids)] + domain_quant_loc
		dates_in_the_past = False
		# only to_date as to_date will correspond to qty_available
		to_date = fields.Datetime.to_datetime(to_date)
		if to_date and to_date < fields.Datetime.now():
			dates_in_the_past = True

		domain_move_in = [('product_id', 'in', self.ids)] + domain_move_in_loc
		domain_move_out = [('product_id', 'in', self.ids)] + domain_move_out_loc
		if lot_id is not None:
			domain_quant += [('lot_id', '=', lot_id)]
		if owner_id is not None:
			domain_quant += [('owner_id', '=', owner_id)]
			domain_move_in += [('restrict_partner_id', '=', owner_id)]
			domain_move_out += [('restrict_partner_id', '=', owner_id)]
		if package_id is not None:
			domain_quant += [('package_id', '=', package_id)]
		if dates_in_the_past:
			domain_move_in_done = list(domain_move_in)
			domain_move_out_done = list(domain_move_out)
		if from_date:
			date_date_expected_domain_from = [('date', '<=', from_date)]
			domain_move_in += date_date_expected_domain_from
			domain_move_out += date_date_expected_domain_from
		if to_date:
			date_date_expected_domain_to = [('date', '<=', to_date)]
			domain_move_in += date_date_expected_domain_to
			domain_move_out += date_date_expected_domain_to

		Move = self.env['stock.move'].with_context(active_test=False)
		Quant = self.env['stock.quant'].with_context(active_test=False)
		domain_move_in_todo = [('state', 'in', ('waiting', 'confirmed', 'assigned', 'partially_available'))] + domain_move_in
		domain_move_out_todo = [('state', 'in', ('waiting', 'confirmed', 'assigned', 'partially_available'))] + domain_move_out
		moves_in_res = dict((item['product_id'][0], item['product_qty'], item['product_qty1'], item['product_qty2']) for item in Move.read_group(domain_move_in_todo, ['product_id', 'product_qty', 'product_qty1', 'product_qty2'], ['product_id'], orderby='id'))
		moves_out_res = dict((item['product_id'][0], item['product_qty'], item['product_qty1'], item['product_qty2']) for item in Move.read_group(domain_move_out_todo, ['product_id', 'product_qty', 'product_qty1', 'product_qty2'], ['product_id'], orderby='id'))
		quants_res = dict((item['product_id'][0], (item['quantity'], item['reserved_quantity'], item['quantity1'], item['reserved_quantity1'], item['quantity2'], item['reserved_quantity2'])) for item in Quant.read_group(domain_quant, ['product_id', 'quantity', 'reserved_quantity', 'quantity1', 'reserved_quantity1', 'quantity2', 'reserved_quantity2'], ['product_id'], orderby='id'))
		_logger.info('Quants_res : %s',str(quants_res))
		if dates_in_the_past:
			# Calculate the moves that were done before now to calculate back in time (as most questions will be recent ones)
			domain_move_in_done = [('state', '=', 'done'), ('date', '>', to_date)] + domain_move_in_done
			domain_move_out_done = [('state', '=', 'done'), ('date', '>', to_date)] + domain_move_out_done
			moves_in_res_past = dict((item['product_id'][0], item['product_qty']) for item in Move.read_group(domain_move_in_done, ['product_id', 'product_qty'], ['product_id'], orderby='id'))
			moves_out_res_past = dict((item['product_id'][0], item['product_qty']) for item in Move.read_group(domain_move_out_done, ['product_id', 'product_qty'], ['product_id'], orderby='id'))
			_logger.info('moves_in_res_past : %s',str(moves_in_res_past))
		res = dict()
		for product in self.with_context(prefetch_fields=False):
			product_id = product.id
			if not product_id:
				res[product_id] = dict.fromkeys(
					['qty_available', 'free_qty', 'incoming_qty', 'outgoing_qty', 'virtual_available', 'qty_available1', 'qty_available2'],
					0.0,
				)
				continue
			rounding = product.uom_id.rounding
			res[product_id] = {}
			if dates_in_the_past:
				qty_available = quants_res.get(product_id, [0.0])[0] - moves_in_res_past.get(product_id, 0.0) + moves_out_res_past.get(product_id, 0.0)
				qty_available1 = quants_res.get(product_id, [0.0])[0] - moves_in_res_past.get(product_id, 0.0) + moves_out_res_past.get(product_id, 0.0)
				qty_available2 = quants_res.get(product_id, [0.0])[0] - moves_in_res_past.get(product_id, 0.0) + moves_out_res_past.get(product_id, 0.0)
			else:
				qty_available = quants_res.get(product_id, [0.0])[0]
				qty_available1 = quants_res.get(product_id, [0.0])[0]
				qty_available2 = quants_res.get(product_id, [0.0])[0]

			reserved_quantity = quants_res.get(product_id, [False, 0.0])[1]
			res[product_id]['qty_available'] = float_round(qty_available, precision_rounding=rounding)
			res[product_id]['qty_available1'] = float_round(qty_available1, precision_rounding=rounding)
			res[product_id]['qty_available2'] = float_round(qty_available2, precision_rounding=rounding)
			res[product_id]['free_qty'] = float_round(qty_available - reserved_quantity, precision_rounding=rounding)
			res[product_id]['incoming_qty'] = float_round(moves_in_res.get(product_id, 0.0), precision_rounding=rounding)
			res[product_id]['outgoing_qty'] = float_round(moves_out_res.get(product_id, 0.0), precision_rounding=rounding)
			res[product_id]['virtual_available'] = float_round(
				qty_available + res[product_id]['incoming_qty'] - res[product_id]['outgoing_qty'],
				precision_rounding=rounding)

		return res
        

class ProductTemplate(models.Model):
	_inherit = "product.template"
	
	uom_id1 = fields.Many2one('uom.uom', 'UoM 1', help="Extra unit of measure.")
	uom_id2 = fields.Many2one('uom.uom', 'UoM 2', help="Extra unit of measure.")
	qty_available1 = fields.Float(
		'Quantity On Hand 1', compute='_compute_quantities', search='_search_qty_available',
		compute_sudo=False, digits='Product Unit of Measure')
	qty_available2 = fields.Float(
		'Quantity On Hand 2', compute='_compute_quantities', search='_search_qty_available',
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