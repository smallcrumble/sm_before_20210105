# -*- coding: utf-8 -*-

from odoo.tools.float_utils import float_compare, float_is_zero, float_round
from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import UserError
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)

class StockMove(models.Model):
	_inherit = "stock.move"
	
	product_uom_qty1 = fields.Float(
		'Demand 1',
		digits='Product Unit of Measure',
		default=0.0, states={'done': [('readonly', True)]})
	#always product_qty1 = product_uom_qty1
	#always product_qty2 = product_uom_qty2
	product_uom_qty2 = fields.Float(
		'Demand 2',
		digits='Product Unit of Measure',
		default=0.0, states={'done': [('readonly', True)]})
	product_uom1 = fields.Many2one('uom.uom', 'UoM 1', domain="[('category_id', '=', product_uom_category_id)]")
	product_uom2 = fields.Many2one('uom.uom', 'UoM 2', domain="[('category_id', '=', product_uom_category_id)]")
	reserved_availability = fields.Float(
		'Quantity Reserved', compute='_compute_reserved_availability',
		digits='Product Unit of Measure',
		readonly=True, help='Quantity that has already been reserved for this move')
	reserved_availability1 = fields.Float(
		'Qty Reserved 1', compute='_compute_reserved_availability',
		digits='Product Unit of Measure',
		readonly=True, help='Quantity 1 that has already been reserved for this move')
	reserved_availability2 = fields.Float(
		'Qty Reserved 2', compute='_compute_reserved_availability',
		digits='Product Unit of Measure',
		readonly=True, help='Quantity 2 that has already been reserved for this move')
	quantity_done1 = fields.Float('Done 1', compute='_quantity_done_compute', digits='Product Unit of Measure', inverse='_quantity_done_set')
	quantity_done2 = fields.Float('Done 2', compute='_quantity_done_compute', digits='Product Unit of Measure', inverse='_quantity_done_set')
	forecast_availability1 = fields.Float('Forecast Availability 1', compute='_compute_forecast_information', digits='Product Unit of Measure')
	forecast_availability2 = fields.Float('Forecast Availability 2', compute='_compute_forecast_information', digits='Product Unit of Measure')

	@api.depends('move_line_ids.qty_done', 'move_line_ids.qty_done1', 'move_line_ids.qty_done2', 'move_line_ids.product_uom_id', 'move_line_ids.product_uom_id1', 'move_line_ids.product_uom_id2', 'move_line_nosuggest_ids.qty_done', 'picking_type_id')
	def _quantity_done_compute(self):
		if not any(self._ids):
			# onchange
			for move in self:
				quantity_done = 0
				quantity_done1 = 0
				quantity_done2 = 0
				for move_line in move._get_move_lines():
					quantity_done += move_line.product_uom_id._compute_quantity(
						move_line.qty_done, move.product_uom, round=False)
					quantity_done1 += move_line.qty_done1
					quantity_done2 += move_line.qty_done2
					''' bypass _compute_quantity :
					quantity_done1 += move_line.product_uom_id1._compute_quantity(
						move_line.qty_done1, move.product_uom1, round=False)
					quantity_done2 += move_line.product_uom_id2._compute_quantity(
						move_line.qty_done2, move.product_uom2, round=False)
					'''
				move.quantity_done = quantity_done
				move.quantity_done1 = quantity_done1
				move.quantity_done2 = quantity_done2
		else:
			# compute
			move_lines = self.env['stock.move.line']
			for move in self:
				move_lines |= move._get_move_lines()

			data = self.env['stock.move.line'].read_group(
				[('id', 'in', move_lines.ids)],
				['move_id', 'product_uom_id', 'qty_done'], ['move_id', 'product_uom_id'],
				lazy=False
			)

			data1 = self.env['stock.move.line'].read_group(
				[('id', 'in', move_lines.ids)],
				['move_id', 'product_uom_id1', 'qty_done1'], ['move_id', 'product_uom_id1'],
				lazy=False
			)

			data2 = self.env['stock.move.line'].read_group(
				[('id', 'in', move_lines.ids)],
				['move_id', 'product_uom_id2', 'qty_done2'], ['move_id', 'product_uom_id2'],
				lazy=False
			)

			'''_logger.info('data   : %s', str(data))
			_logger.info('data 1 : %s', str(data1))
			_logger.info('data 2 : %s', str(data2))
			'''

			rec = defaultdict(list)
			rec1 = defaultdict(list)
			rec2 = defaultdict(list)
			for d in data:
				rec[d['move_id'][0]] += [(d['product_uom_id'][0], d['qty_done'])]
			for d in data1:
				if d['product_uom_id1'] and d['qty_done1'] :
					#_logger.info('d 1 : %s', str(d))
					rec1[d['move_id'][0]] += [(d['product_uom_id1'][0], d['qty_done1'])]
			for d in data2:
				if d['product_uom_id2'] and d['qty_done2'] :
					#_logger.info('d 2 : %s', str(d))
					rec2[d['move_id'][0]] += [(d['product_uom_id2'][0], d['qty_done2'])]
			
			for move in self:
				uom = move.product_uom
				uom1 = move.product_uom1
				uom2 = move.product_uom2
				move.quantity_done = sum(
					self.env['uom.uom'].browse(line_uom_id)._compute_quantity(qty, uom, round=False)
					 for line_uom_id, qty in rec.get(move.ids[0] if move.ids else move.id, [])
				)
				move.quantity_done1 = sum(
					self.env['uom.uom'].browse(line_uom_id)._compute_quantity(qty1, uom1, round=False)
					 for line_uom_id, qty1 in rec1.get(move.ids[0] if move.ids else move.id, [])
				)
				move.quantity_done2 = sum(
					self.env['uom.uom'].browse(line_uom_id)._compute_quantity(qty2, uom2, round=False)
					 for line_uom_id, qty2 in rec2.get(move.ids[0] if move.ids else move.id, [])
				)
				''' bypass _compute_quantity :
				move.quantity_done1 = sum(
					self.env['uom.uom'].browse(line_uom_id)._compute_quantity(qty1, uom1, round=False)
					 for line_uom_id, qty1 in rec1.get(move.ids[0] if move.ids else move.id, [])
				)
				move.quantity_done2 = sum(
					self.env['uom.uom'].browse(line_uom_id)._compute_quantity(qty2, uom2, round=False)
					 for line_uom_id, qty2 in rec2.get(move.ids[0] if move.ids else move.id, [])
				)
				'''

	def _quantity_done_set(self):
		quantity_done = self[0].quantity_done  # any call to create will invalidate `move.quantity_done`
		quantity_done1 = self[0].quantity_done1
		quantity_done2 = self[0].quantity_done2
		for move in self:
			move_lines = move._get_move_lines()
			if not move_lines:
				if quantity_done:
					# do not impact reservation here
					move_line = self.env['stock.move.line'].create(dict(move._prepare_move_line_vals(), qty_done=quantity_done, qty_done1=quantity_done1, qty_done2=quantity_done2))
					move.write({'move_line_ids': [(4, move_line.id)]})
			elif len(move_lines) == 1:
				move_lines[0].qty_done = quantity_done
				move_lines[0].qty_done1 = quantity_done1
				move_lines[0].qty_done2 = quantity_done2
				#_logger.info('_quantity_done_set : %s', str(quantity_done))
			else:
				# Bypass the error if we're trying to write the same value.
				ml_quantity_done = 0
				ml_quantity_done1 = 0
				ml_quantity_done2 = 0
				for move_line in move_lines:
					ml_quantity_done += move_line.product_uom_id._compute_quantity(move_line.qty_done, move.product_uom, round=False)
					ml_quantity_done1 += move_line.qty_done # bypass _compute_quantity, tp ga yakin codingnya
					ml_quantity_done2 += move_line.qty_done
				if float_compare(quantity_done, ml_quantity_done, precision_rounding=move.product_uom.rounding) != 0:
					raise UserError(_("Cannot set the done quantity from this stock move, work directly with the move lines."))

	@api.depends('move_line_ids.product_qty', 'move_line_ids.product_uom_qty1', 'move_line_ids.product_uom_qty2')
	def _compute_reserved_availability(self):
		""" Fill the `availability` field on a stock move, which is the actual reserved quantity
		and is represented by the aggregated `product_qty` on the linked move lines. If the move
		is force assigned, the value will be 0.
		"""
		if not any(self._ids):
			# onchange
			for move in self:
				reserved_availability = sum(move.move_line_ids.mapped('product_qty'))
				move.reserved_availability = move.product_id.uom_id._compute_quantity(
					reserved_availability, move.product_uom, rounding_method='HALF-UP')
				move.reserved_availability1 = sum(move.move_line_ids.mapped('product_uom_qty1'))
				move.reserved_availability2 = sum(move.move_line_ids.mapped('product_uom_qty2'))
		else:
			# compute
			result = {data['move_id'][0]: data['product_qty'] for data in
					  self.env['stock.move.line'].read_group([('move_id', 'in', self.ids)], ['move_id', 'product_qty'], ['move_id'])}
			for move in self:
				move.reserved_availability = move.product_id.uom_id._compute_quantity(
					result.get(move.id, 0.0), move.product_uom, rounding_method='HALF-UP')
				move.reserved_availability1 = 0.0
				move.reserved_availability2 = 0.0

	@api.depends('state', 'product_id', 'product_qty', 'location_id')
	def _compute_product_availability(self):
		""" Fill the `availability` field on a stock move, which is the quantity to potentially
		reserve. When the move is done, `availability` is set to the quantity the move did actually
		move.
		"""
		for move in self:
			if move.state == 'done':
				move.availability = move.product_qty
				move.availability1 = move.product_uom_qty1
				move.availability2 = move.product_uom_qty2
			else:
				total_availability = self.env['stock.quant']._get_available_quantity(move.product_id, move.location_id) if move.product_id else 0.0
				move.availability = min(move.product_qty, total_availability)
				total_availability1 = self.env['stock.quant']._get_available_quantity1(move.product_id, move.location_id) if move.product_id else 0.0
				move.availability1 = min(move.product_uom_qty1, total_availability1)
				total_availability2 = self.env['stock.quant']._get_available_quantity2(move.product_id, move.location_id) if move.product_id else 0.0
				move.availability2 = min(move.product_uom_qty2, total_availability2)

	@api.depends('product_id', 'picking_type_id', 'picking_id', 'reserved_availability', 'priority', 'state', 'product_uom_qty', 'location_id')
	def _compute_forecast_information(self):
		""" Compute forecasted information of the related product by warehouse."""
		self.forecast_availability = False
		self.forecast_availability1 = False
		self.forecast_availability2 = False
		self.forecast_expected_date = False

		not_product_moves = self.filtered(lambda move: move.product_id.type != 'product')
		for move in not_product_moves:
			move.forecast_availability = move.product_qty
			move.forecast_availability1 = move.product_uom_qty1
			move.forecast_availability2 = move.product_uom_qty2

		product_moves = (self - not_product_moves)
		warehouse_by_location = {loc: loc.get_warehouse() for loc in product_moves.location_id}

		outgoing_unreserved_moves_per_warehouse = defaultdict(lambda: self.env['stock.move'])
		for move in product_moves:
			picking_type = move.picking_type_id or move.picking_id.picking_type_id
			is_unreserved = move.state in ('waiting', 'confirmed', 'partially_available')
			if picking_type.code in self._consuming_picking_types() and is_unreserved:
				outgoing_unreserved_moves_per_warehouse[warehouse_by_location[move.location_id]] |= move
			elif picking_type.code in self._consuming_picking_types():
				move.forecast_availability = move.reserved_availability
				move.forecast_availability1 = move.reserved_availability1
				move.forecast_availability2 = move.reserved_availability2

		for warehouse, moves in outgoing_unreserved_moves_per_warehouse.items():
			if not warehouse:  # No prediction possible if no warehouse.
				continue
			product_variant_ids = moves.product_id.ids
			wh_location_ids = [loc['id'] for loc in self.env['stock.location'].search_read(
				[('id', 'child_of', warehouse.view_location_id.id)],
				['id'],
			)]
			forecast_lines = self.env['report.stock.report_product_product_replenishment']\
				._get_report_lines(None, product_variant_ids, wh_location_ids)
			for move in moves:
				lines = [l for l in forecast_lines if l["move_out"] == move._origin and l["replenishment_filled"] is True]
				if lines:
					move.forecast_availability = sum(m['quantity'] for m in lines)
					move.forecast_availability1 = sum(m['quantity1'] for m in lines)
					move.forecast_availability2 = sum(m['quantity2'] for m in lines)
					move_ins_lines = list(filter(lambda report_line: report_line['move_in'], lines))
					if move_ins_lines:
						expected_date = max(m['move_in'].date for m in move_ins_lines)
						move.forecast_expected_date = expected_date

	def _set_lot_ids(self):
		for move in self:
			move_lines_commands = []
			if move.picking_type_id.show_reserved is False:
				mls = move.move_line_nosuggest_ids
			else:
				mls = move.move_line_ids
			mls = mls.filtered(lambda ml: ml.lot_id)
			for ml in mls:
				if ml.lot_id not in move.lot_ids:
					move_lines_commands.append((2, ml.id))
			ls = move.move_line_ids.lot_id
			for lot in move.lot_ids:
				if lot not in ls:
					move_line_vals = self._prepare_move_line_vals(quantity=0)
					move_line_vals['lot_id'] = lot.id
					move_line_vals['lot_name'] = lot.name
					move_line_vals['product_uom_id'] = move.product_id.uom_id.id
					move_line_vals['product_uom_id1'] = move.product_id.uom_id1.id
					move_line_vals['product_uom_id2'] = move.product_id.uom_id2.id
					move_line_vals['qty_done'] = 1
					move_line_vals['qty_done1'] = 1
					move_line_vals['qty_done2'] = 1
					move_lines_commands.append((0, 0, move_line_vals))
			move.write({'move_line_ids': move_lines_commands})

	@api.model
	def default_get(self, fields_list):
		# We override the default_get to make stock moves created after the picking was confirmed
		# directly as available in immediate transfer mode. This allows to create extra move lines
		# in the fp view. In planned transfer, the stock move are marked as `additional` and will be
		# auto-confirmed.
		defaults = super(StockMove, self).default_get(fields_list)
		if self.env.context.get('default_picking_id'):
			picking_id = self.env['stock.picking'].browse(self.env.context['default_picking_id'])
			if picking_id.state == 'done':
				defaults['state'] = 'done'
				defaults['product_uom_qty'] = 0.0
				defaults['product_uom_qty1'] = 0.0
				defaults['product_uom_qty2'] = 0.0
				defaults['additional'] = True
			elif picking_id.state not in ['cancel', 'draft', 'done']:
				if picking_id.immediate_transfer:
					defaults['state'] = 'assigned'
				defaults['product_uom_qty'] = 0.0
				defaults['product_uom_qty1'] = 0.0
				defaults['product_uom_qty2'] = 0.0
				defaults['additional'] = True  # to trigger `_autoconfirm_picking`
		return defaults

	def _merge_moves_fields(self):
		""" This method will return a dict of stock move’s values that represent the values of all moves in `self` merged. """
		state = self._get_relevant_state_among_moves()
		origin = '/'.join(set(self.filtered(lambda m: m.origin).mapped('origin')))
		return {
			'product_uom_qty': sum(self.mapped('product_uom_qty')),
			'product_uom_qty1': sum(self.mapped('product_uom_qty1')),
			'product_uom_qty2': sum(self.mapped('product_uom_qty2')),
			'date': min(self.mapped('date')) if self.mapped('picking_id').move_type == 'direct' else max(self.mapped('date')),
			'move_dest_ids': [(4, m.id) for m in self.mapped('move_dest_ids')],
			'move_orig_ids': [(4, m.id) for m in self.mapped('move_orig_ids')],
			'state': state,
			'origin': origin,
		}

	def _action_confirm(self, merge=True, merge_into=False):
		""" Confirms stock move or put it in waiting if it's linked to another move.
		:param: merge: According to this boolean, a newly confirmed move will be merged
		in another move of the same picking sharing its characteristics.
		"""
		move_create_proc = self.env['stock.move']
		move_to_confirm = self.env['stock.move']
		move_waiting = self.env['stock.move']

		to_assign = {}
		for move in self:
			if move.state != 'draft':
				continue
			# if the move is preceeded, then it's waiting (if preceeding move is done, then action_assign has been called already and its state is already available)
			if move.move_orig_ids:
				move_waiting |= move
			else:
				if move.procure_method == 'make_to_order':
					move_create_proc |= move
				else:
					move_to_confirm |= move
			if move._should_be_assigned():
				key = (move.group_id.id, move.location_id.id, move.location_dest_id.id)
				if key not in to_assign:
					to_assign[key] = self.env['stock.move']
				to_assign[key] |= move

		# create procurements for make to order moves
		procurement_requests = []
		for move in move_create_proc:
			values = move._prepare_procurement_values()
			origin = (move.group_id and move.group_id.name or (move.origin or move.picking_id.name or "/"))
			procurement_requests.append(self.env['procurement.group'].Procurement(
				move.product_id, move.product_uom_qty, move.product_uom,
				move.product_uom_qty1, move.product_uom1, move.product_uom_qty2, move.product_uom2,
				move.location_id, move.rule_id and move.rule_id.name or "/",
				origin, move.company_id, values))
		self.env['procurement.group'].run(procurement_requests, raise_user_error=not self.env.context.get('from_orderpoint'))

		move_to_confirm.write({'state': 'confirmed'})
		(move_waiting | move_create_proc).write({'state': 'waiting'})

		# assign picking in batch for all confirmed move that share the same details
		for moves in to_assign.values():
			moves._assign_picking()
		self._push_apply()
		self._check_company()
		moves = self
		if merge:
			moves = self._merge_moves(merge_into=merge_into)
		# call `_action_assign` on every confirmed move which location_id bypasses the reservation
		moves.filtered(lambda move: not move.picking_id.immediate_transfer and move._should_bypass_reservation() and move.state == 'confirmed')._action_assign()
		return moves

	def _prepare_move_line_vals(self, quantity=None, reserved_quant=None, quantity1=None, quantity2=None):
		self.ensure_one()
		# apply putaway
		location_dest_id = self.location_dest_id._get_putaway_strategy(self.product_id).id or self.location_dest_id.id
		vals = {
			'move_id': self.id,
			'product_id': self.product_id.id,
			'product_uom_id': self.product_uom.id,
			'location_id': self.location_id.id,
			'location_dest_id': location_dest_id,
			'picking_id': self.picking_id.id,
			'company_id': self.company_id.id,
			'product_uom_id1': self.product_uom1.id,
			'product_uom_id2': self.product_uom2.id,
		}
		if quantity:
			rounding = self.env['decimal.precision'].precision_get('Product Unit of Measure')
			uom_quantity = self.product_id.uom_id._compute_quantity(quantity, self.product_uom, rounding_method='HALF-UP')
			uom_quantity = float_round(uom_quantity, precision_digits=rounding)
			uom_quantity_back_to_product_uom = self.product_uom._compute_quantity(uom_quantity, self.product_id.uom_id, rounding_method='HALF-UP')
			
			if float_compare(quantity, uom_quantity_back_to_product_uom, precision_digits=rounding) == 0:
				vals = dict(vals, product_uom_qty=uom_quantity)
			else:
				vals = dict(vals, product_uom_qty=quantity, product_uom_id=self.product_id.uom_id.id)
			vals = dict(vals,product_uom_qty1=quantity1)
			vals = dict(vals,product_uom_qty2=quantity2)
			#vals = dict(vals,product_uom_qty1=self.product_uom_qty1)
			#vals = dict(vals,product_uom_qty2=self.product_uom_qty2)
			#_logger.info('vals  : %s', str(vals))
			
		if reserved_quant:
			vals = dict(
				vals,
				location_id=reserved_quant.location_id.id,
				lot_id=reserved_quant.lot_id.id or False,
				package_id=reserved_quant.package_id.id or False,
				owner_id =reserved_quant.owner_id.id or False,
			)
		#_logger.info('vals sblm return : %s', str(vals))
		return vals

	def _update_reserved_quantity(self, need, need1, need2, available_quantity, available_quantity1, available_quantity2, location_id, lot_id=None, package_id=None, owner_id=None, strict=True):
		""" Create or update move lines.
		"""
		self.ensure_one()

		if not lot_id:
			lot_id = self.env['stock.production.lot']
		if not package_id:
			package_id = self.env['stock.quant.package']
		if not owner_id:
			owner_id = self.env['res.partner']

		taken_quantity = min(available_quantity, need)
		taken_quantity1 = min(available_quantity1, need1)
		taken_quantity2 = min(available_quantity2, need2)

		# `taken_quantity` is in the quants unit of measure. There's a possibility that the move's
		# unit of measure won't be respected if we blindly reserve this quantity, a common usecase
		# is if the move's unit of measure's rounding does not allow fractional reservation. We chose
		# to convert `taken_quantity` to the move's unit of measure with a down rounding method and
		# then get it back in the quants unit of measure with an half-up rounding_method. This
		# way, we'll never reserve more than allowed. We do not apply this logic if
		# `available_quantity` is brought by a chained move line. In this case, `_prepare_move_line_vals`
		# will take care of changing the UOM to the UOM of the product.
		if not strict:
			taken_quantity_move_uom = self.product_id.uom_id._compute_quantity(taken_quantity, self.product_uom, rounding_method='DOWN')
			taken_quantity = self.product_uom._compute_quantity(taken_quantity_move_uom, self.product_id.uom_id, rounding_method='HALF-UP')

		quants = []
		rounding = self.env['decimal.precision'].precision_get('Product Unit of Measure')

		if self.product_id.tracking == 'serial':
			if float_compare(taken_quantity, int(taken_quantity), precision_digits=rounding) != 0:
				taken_quantity = 0
			if float_compare(taken_quantity1, int(taken_quantity1), precision_digits=rounding) != 0:
				taken_quantity1 = 0
			if float_compare(taken_quantity2, int(taken_quantity2), precision_digits=rounding) != 0:
				taken_quantity2 = 0

		try:
			with self.env.cr.savepoint():
				if not float_is_zero(taken_quantity1, precision_rounding=self.product_id.uom_id.rounding):
					quants = self.env['stock.quant']._update_reserved_quantity(
						self.product_id, location_id, taken_quantity, taken_quantity1, taken_quantity2, lot_id=lot_id,
						package_id=package_id, owner_id=owner_id, strict=strict
					)
		except UserError:
			taken_quantity = 0
			taken_quantity1 = 0
			taken_quantity2 = 0

		_logger.info('quants joged= %s',str(quants))
		# Find a candidate move line to update or create a new one.
		for reserved_quant, quantity in quants:
			to_update = self.move_line_ids.filtered(lambda ml: ml._reservation_is_updatable(quantity, reserved_quant))
			if to_update:
				uom_quantity = self.product_id.uom_id._compute_quantity(quantity, to_update[0].product_uom_id, rounding_method='HALF-UP')
				uom_quantity = float_round(uom_quantity, precision_digits=rounding)
				uom_quantity1 = quantity1
				uom_quantity2 = quantity2
				uom_quantity_back_to_product_uom = to_update[0].product_uom_id._compute_quantity(uom_quantity, self.product_id.uom_id, rounding_method='HALF-UP')
			if to_update and float_compare(quantity, uom_quantity_back_to_product_uom, precision_digits=rounding) == 0:
				to_update[0].with_context(bypass_reservation_update=True).product_uom_qty += uom_quantity
				to_update[0].with_context(bypass_reservation_update=True).product_uom_qty1 += uom_quantity1
				to_update[0].with_context(bypass_reservation_update=True).product_uom_qty2 += uom_quantity2
			else:
				if self.product_id.tracking == 'serial':
					for i in range(0, int(quantity)):
						self.env['stock.move.line'].create(self._prepare_move_line_vals(quantity=1, quantity1=1, quantity2=1, reserved_quant=reserved_quant))
				else:
					self.env['stock.move.line'].create(self._prepare_move_line_vals(quantity=quantity, quantity1=quantity1, quantity2=quantity2, reserved_quant=reserved_quant))
		return taken_quantity, taken_quantity1, taken_quantity2

	

	def _get_available_quantity1(self, location_id, lot_id=None, package_id=None, owner_id=None, strict=False, allow_negative=False):
		self.ensure_one()
		return self.env['stock.quant']._get_available_quantity(self.product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict, allow_negative=allow_negative)

	def _get_available_quantity2(self, location_id, lot_id=None, package_id=None, owner_id=None, strict=False, allow_negative=False):
		self.ensure_one()
		return self.env['stock.quant']._get_available_quantity(self.product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict, allow_negative=allow_negative)


	def _action_assign(self):
		""" Reserve stock moves by creating their stock move lines. A stock move is
		considered reserved once the sum of `product_qty` for all its move lines is
		equal to its `product_qty`. If it is less, the stock move is considered
		partially available.
		"""
		assigned_moves = self.env['stock.move']
		partially_available_moves = self.env['stock.move']
		# Read the `reserved_availability` field of the moves out of the loop to prevent unwanted
		# cache invalidation when actually reserving the move.
		reserved_availability = {move: move.reserved_availability for move in self}
		reserved_availability1 = {move: move.reserved_availability1 for move in self}
		reserved_availability2 = {move: move.reserved_availability2 for move in self}
		roundings = {move: move.product_id.uom_id.rounding for move in self}
		move_line_vals_list = []
		for move in self.filtered(lambda m: m.state in ['confirmed', 'waiting', 'partially_available']):
			rounding = roundings[move]
			missing_reserved_uom_quantity = move.product_uom_qty - reserved_availability[move]
			missing_reserved_uom_quantity1 = move.product_uom_qty1 - reserved_availability1[move]
			missing_reserved_uom_quantity2 = move.product_uom_qty2 - reserved_availability2[move]
			missing_reserved_quantity = move.product_uom._compute_quantity(missing_reserved_uom_quantity, move.product_id.uom_id, rounding_method='HALF-UP')
			if move._should_bypass_reservation():
				# create the move line(s) but do not impact quants
				if move.product_id.tracking == 'serial' and (move.picking_type_id.use_create_lots or move.picking_type_id.use_existing_lots):
					for i in range(0, int(missing_reserved_quantity)):
						move_line_vals_list.append(move._prepare_move_line_vals(quantity=1, quantity1=1, quantity2=1))
				else:
					to_update = move.move_line_ids.filtered(lambda ml: ml.product_uom_id == move.product_uom and
															ml.location_id == move.location_id and
															ml.location_dest_id == move.location_dest_id and
															ml.picking_id == move.picking_id and
															not ml.lot_id and
															not ml.package_id and
															not ml.owner_id)
					if to_update:
						to_update[0].product_uom_qty += missing_reserved_uom_quantity
						to_update[0].product_uom_qty1 += missing_reserved_uom_quantity1
						to_update[0].product_uom_qty2 += missing_reserved_uom_quantity2
					else:
						move_line_vals_list.append(move._prepare_move_line_vals(quantity=missing_reserved_quantity, quantity1=missing_reserved_uom_quantity1, quantity2=missing_reserved_uom_quantity2))
				assigned_moves |= move
			else:
				if float_is_zero(move.product_uom_qty, precision_rounding=move.product_uom.rounding):
					assigned_moves |= move
				elif not move.move_orig_ids:
					if move.procure_method == 'make_to_order':
						continue
					# If we don't need any quantity, consider the move assigned.
					need = missing_reserved_quantity
					need1 = missing_reserved_uom_quantity1
					need2 = missing_reserved_uom_quantity2
					if float_is_zero(need, precision_rounding=rounding):
						assigned_moves |= move
						continue
					# Reserve new quants and create move lines accordingly.
					forced_package_id = move.package_level_id.package_id or None
					available_quantity = move._get_available_quantity(move.location_id, package_id=forced_package_id)
					available_quantity1 = move._get_available_quantity1(move.location_id, package_id=forced_package_id)
					available_quantity2 = move._get_available_quantity2(move.location_id, package_id=forced_package_id)
					if available_quantity <= 0:
						continue
					taken_quantity = move._update_reserved_quantity(need, available_quantity, move.location_id, package_id=forced_package_id, strict=False)
					if float_is_zero(taken_quantity, precision_rounding=rounding):
						continue
					if float_compare(need, taken_quantity, precision_rounding=rounding) == 0:
						assigned_moves |= move
					else:
						partially_available_moves |= move
				else:
					# Check what our parents brought and what our siblings took in order to
					# determine what we can distribute.
					# `qty_done` is in `ml.product_uom_id` and, as we will later increase
					# the reserved quantity on the quants, convert it here in
					# `product_id.uom_id` (the UOM of the quants is the UOM of the product).
					move_lines_in = move.move_orig_ids.filtered(lambda m: m.state == 'done').mapped('move_line_ids')
					keys_in_groupby = ['location_dest_id', 'lot_id', 'result_package_id', 'owner_id']

					def _keys_in_sorted(ml):
						return (ml.location_dest_id.id, ml.lot_id.id, ml.result_package_id.id, ml.owner_id.id)

					grouped_move_lines_in = {}
					for k, g in groupby(sorted(move_lines_in, key=_keys_in_sorted), key=itemgetter(*keys_in_groupby)):
						qty_done = 0
						for ml in g:
							qty_done += ml.product_uom_id._compute_quantity(ml.qty_done, ml.product_id.uom_id)
						grouped_move_lines_in[k] = qty_done
					move_lines_out_done = (move.move_orig_ids.mapped('move_dest_ids') - move)\
						.filtered(lambda m: m.state in ['done'])\
						.mapped('move_line_ids')
					# As we defer the write on the stock.move's state at the end of the loop, there
					# could be moves to consider in what our siblings already took.
					moves_out_siblings = move.move_orig_ids.mapped('move_dest_ids') - move
					moves_out_siblings_to_consider = moves_out_siblings & (assigned_moves + partially_available_moves)
					reserved_moves_out_siblings = moves_out_siblings.filtered(lambda m: m.state in ['partially_available', 'assigned'])
					move_lines_out_reserved = (reserved_moves_out_siblings | moves_out_siblings_to_consider).mapped('move_line_ids')
					keys_out_groupby = ['location_id', 'lot_id', 'package_id', 'owner_id']

					def _keys_out_sorted(ml):
						return (ml.location_id.id, ml.lot_id.id, ml.package_id.id, ml.owner_id.id)

					grouped_move_lines_out = {}
					for k, g in groupby(sorted(move_lines_out_done, key=_keys_out_sorted), key=itemgetter(*keys_out_groupby)):
						qty_done = 0
						for ml in g:
							qty_done += ml.product_uom_id._compute_quantity(ml.qty_done, ml.product_id.uom_id)
						grouped_move_lines_out[k] = qty_done
					for k, g in groupby(sorted(move_lines_out_reserved, key=_keys_out_sorted), key=itemgetter(*keys_out_groupby)):
						grouped_move_lines_out[k] = sum(self.env['stock.move.line'].concat(*list(g)).mapped('product_qty'))
					available_move_lines = {key: grouped_move_lines_in[key] - grouped_move_lines_out.get(key, 0) for key in grouped_move_lines_in.keys()}
					# pop key if the quantity available amount to 0
					available_move_lines = dict((k, v) for k, v in available_move_lines.items() if v)

					if not available_move_lines:
						continue
					for move_line in move.move_line_ids.filtered(lambda m: m.product_qty):
						if available_move_lines.get((move_line.location_id, move_line.lot_id, move_line.result_package_id, move_line.owner_id)):
							available_move_lines[(move_line.location_id, move_line.lot_id, move_line.result_package_id, move_line.owner_id)] -= move_line.product_qty
					for (location_id, lot_id, package_id, owner_id), quantity in available_move_lines.items():
						need = move.product_qty - sum(move.move_line_ids.mapped('product_qty'))
						# `quantity` is what is brought by chained done move lines. We double check
						# here this quantity is available on the quants themselves. If not, this
						# could be the result of an inventory adjustment that removed totally of
						# partially `quantity`. When this happens, we chose to reserve the maximum
						# still available. This situation could not happen on MTS move, because in
						# this case `quantity` is directly the quantity on the quants themselves.
						available_quantity = move._get_available_quantity(location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=True)
						if float_is_zero(available_quantity, precision_rounding=rounding):
							continue
						taken_quantity = move._update_reserved_quantity(need, min(quantity, available_quantity), location_id, lot_id, package_id, owner_id)
						if float_is_zero(taken_quantity, precision_rounding=rounding):
							continue
						if float_is_zero(need - taken_quantity, precision_rounding=rounding):
							assigned_moves |= move
							break
						partially_available_moves |= move
			if move.product_id.tracking == 'serial':
				move.next_serial_count = move.product_uom_qty

		self.env['stock.move.line'].create(move_line_vals_list)
		partially_available_moves.write({'state': 'partially_available'})
		assigned_moves.write({'state': 'assigned'})
		self.mapped('picking_id')._check_entire_pack()


	
	
	

	
	def _merge_moves_fields(self):
		""" This method will return a dict of stock move’s values that represent the values of all moves in `self` merged. """
		state = self._get_relevant_state_among_moves()
		origin = '/'.join(set(self.filtered(lambda m: m.origin).mapped('origin')))
		return {
			'product_uom_qty': sum(self.mapped('product_uom_qty')),
			'product_uom_qty1': sum(self.mapped('product_uom_qty1')),
			'product_uom_qty2': sum(self.mapped('product_uom_qty2')),
			'date': min(self.mapped('date')) if self.mapped('picking_id').move_type == 'direct' else max(self.mapped('date')),
			'move_dest_ids': [(4, m.id) for m in self.mapped('move_dest_ids')],
			'move_orig_ids': [(4, m.id) for m in self.mapped('move_orig_ids')],
			'state': state,
			'origin': origin,
		}

	def _action_done(self, cancel_backorder=False):
		self.filtered(lambda move: move.state == 'draft')._action_confirm()  # MRP allows scrapping draft moves
		moves = self.exists().filtered(lambda x: x.state not in ('done', 'cancel'))
		moves_todo = self.env['stock.move']

		# Cancel moves where necessary ; we should do it before creating the extra moves because
		# this operation could trigger a merge of moves.
		for move in moves:
			if move.quantity_done <= 0:
				if float_compare(move.product_uom_qty, 0.0, precision_rounding=move.product_uom.rounding) == 0 or cancel_backorder:
					move._action_cancel()

		# Create extra moves where necessary
		for move in moves:
			if move.state == 'cancel' or move.quantity_done <= 0:
				continue

			moves_todo |= move._create_extra_move()

		moves_todo._check_company()
		# Split moves where necessary and move quants
		backorder_moves_vals = []
		for move in moves_todo:
			# To know whether we need to create a backorder or not, round to the general product's
			# decimal precision and not the product's UOM.
			rounding = self.env['decimal.precision'].precision_get('Product Unit of Measure')
			if float_compare(move.quantity_done, move.product_uom_qty, precision_digits=rounding) < 0:
				# Need to do some kind of conversion here
				qty_split = move.product_uom._compute_quantity(move.product_uom_qty - move.quantity_done, move.product_id.uom_id, rounding_method='HALF-UP')
				qty_split1 = move.product_uom_qty1 - move.quantity_done1
				qty_split2 = move.product_uom_qty2 - move.quantity_done2
				new_move_vals = move._split(qty_split, qty_split1, qty_split2)
				backorder_moves_vals += new_move_vals
		backorder_moves = self.env['stock.move'].create(backorder_moves_vals)
		backorder_moves._action_confirm(merge=False)
		if cancel_backorder:
			backorder_moves.with_context(moves_todo=moves_todo)._action_cancel()
		moves_todo.mapped('move_line_ids').sorted()._action_done()
		# Check the consistency of the result packages; there should be an unique location across
		# the contained quants.
		for result_package in moves_todo\
				.mapped('move_line_ids.result_package_id')\
				.filtered(lambda p: p.quant_ids and len(p.quant_ids) > 1):
			if len(result_package.quant_ids.filtered(lambda q: not float_is_zero(abs(q.quantity) + abs(q.reserved_quantity), precision_rounding=q.product_uom_id.rounding)).mapped('location_id')) > 1:
				raise UserError(_('You cannot move the same package content more than once in the same transfer or split the same package into two location.'))
		picking = moves_todo.mapped('picking_id')
		moves_todo.write({'state': 'done', 'date': fields.Datetime.now()})

		move_dests_per_company = defaultdict(lambda: self.env['stock.move'])
		for move_dest in moves_todo.move_dest_ids:
			move_dests_per_company[move_dest.company_id.id] |= move_dest
		for company_id, move_dests in move_dests_per_company.items():
			move_dests.sudo().with_company(company_id)._action_assign()

		# We don't want to create back order for scrap moves
		# Replace by a kwarg in master
		if self.env.context.get('is_scrap'):
			return moves_todo

		if picking and not cancel_backorder:
			picking._create_backorder()
		return moves_todo

	def _prepare_move_split_vals(self, qty, qty1, qty2):
		vals = {
			'product_uom_qty': qty,
			'product_uom_qty1': qty1,
			'product_uom_qty2': qty2,
			'procure_method': 'make_to_stock',
			'move_dest_ids': [(4, x.id) for x in self.move_dest_ids if x.state not in ('done', 'cancel')],
			'move_orig_ids': [(4, x.id) for x in self.move_orig_ids],
			'origin_returned_move_id': self.origin_returned_move_id.id,
			'price_unit': self.price_unit,
		}
		if self.env.context.get('force_split_uom_id'):
			vals['product_uom'] = self.env.context['force_split_uom_id']
		return vals

	def _split(self, qty, qty1, qty2, restrict_partner_id=False):
		""" Splits `self` quantity and return values for a new moves to be created afterwards

		:param qty: float. quantity to split (given in product UoM)
		:param restrict_partner_id: optional partner that can be given in order to force the new move to restrict its choice of quants to the ones belonging to this partner.
		:returns: list of dict. stock move values """
		self.ensure_one()
		if self.state in ('done', 'cancel'):
			raise UserError(_('You cannot split a stock move that has been set to \'Done\'.'))
		elif self.state == 'draft':
			# we restrict the split of a draft move because if not confirmed yet, it may be replaced by several other moves in
			# case of phantom bom (with mrp module). And we don't want to deal with this complexity by copying the product that will explode.
			raise UserError(_('You cannot split a draft move. It needs to be confirmed first.'))
		if float_is_zero(qty, precision_rounding=self.product_id.uom_id.rounding) or self.product_qty <= qty:
			return []

		decimal_precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')

		# `qty` passed as argument is the quantity to backorder and is always expressed in the
		# quants UOM. If we're able to convert back and forth this quantity in the move's and the
		# quants UOM, the backordered move can keep the UOM of the move. Else, we'll create is in
		# the UOM of the quants.
		uom_qty = self.product_id.uom_id._compute_quantity(qty, self.product_uom, rounding_method='HALF-UP')
		uom_qty1 = qty1
		uom_qty2 = qty2
		if float_compare(qty, self.product_uom._compute_quantity(uom_qty, self.product_id.uom_id, rounding_method='HALF-UP'), precision_digits=decimal_precision) == 0:
			defaults = self._prepare_move_split_vals(uom_qty, uom_qty1, uom_qty2)
		else:
			defaults = self.with_context(force_split_uom_id=self.product_id.uom_id.id)._prepare_move_split_vals(qty, qty1, qty2)

		if restrict_partner_id:
			defaults['restrict_partner_id'] = restrict_partner_id

		# TDE CLEANME: remove context key + add as parameter
		if self.env.context.get('source_location_id'):
			defaults['location_id'] = self.env.context['source_location_id']
		new_move_vals = self.with_context(rounding_method='HALF-UP').copy_data(defaults)

		# Update the original `product_qty` of the move. Use the general product's decimal
		# precision and not the move's UOM to handle case where the `quantity_done` is not
		# compatible with the move's UOM.
		new_product_qty = self.product_id.uom_id._compute_quantity(self.product_qty - qty, self.product_uom, round=False)
		new_product_qty = float_round(new_product_qty, precision_digits=self.env['decimal.precision'].precision_get('Product Unit of Measure'))
		new_product_qty1 = self.product_uom_qty1 - qty1
		new_product_qty2 = self.product_uom_qty2 - qty2
		self.with_context(do_not_unreserve=True, rounding_method='HALF-UP').write({'product_uom_qty': new_product_qty, 'product_uom_qty1': new_product_qty1, 'product_uom_qty2': new_product_qty2})
		return new_move_vals

class StockImmediateTransfer(models.TransientModel):
	_inherit = 'stock.immediate.transfer'

	def process(self):
		pickings_to_do = self.env['stock.picking']
		pickings_not_to_do = self.env['stock.picking']
		for line in self.immediate_transfer_line_ids:
			if line.to_immediate is True:
				pickings_to_do |= line.picking_id
			else:
				pickings_not_to_do |= line.picking_id

		for picking in pickings_to_do:
			# If still in draft => confirm and assign
			if picking.state == 'draft':
				picking.action_confirm()
				if picking.state != 'assigned':
					picking.action_assign()
					if picking.state != 'assigned':
						raise UserError(_("Could not reserve all requested products. Please use the \'Mark as Todo\' button to handle the reservation manually."))
			for move in picking.move_lines.filtered(lambda m: m.state not in ['done', 'cancel']):
				for move_line in move.move_line_ids:
					move_line.qty_done = move_line.product_uom_qty
					move_line.qty_done1 = move_line.product_uom_qty1
					move_line.qty_done2 = move_line.product_uom_qty2

		pickings_to_validate = self.env.context.get('button_validate_picking_ids')
		if pickings_to_validate:
			pickings_to_validate = self.env['stock.picking'].browse(pickings_to_validate)
			pickings_to_validate = pickings_to_validate - pickings_not_to_do
			return pickings_to_validate.with_context(skip_immediate=True).button_validate()
		return True



#done qty = 0 odoo otomatis pangisiin done qty = demand
class Picking(models.Model):
	_inherit = "stock.picking"

	@api.model
	def create(self, vals):
		#_logger.info('--MASUK create PICKING--')
		defaults = self.default_get(['name', 'picking_type_id'])
		picking_type = self.env['stock.picking.type'].browse(vals.get('picking_type_id', defaults.get('picking_type_id')))
		if vals.get('name', '/') == '/' and defaults.get('name', '/') == '/' and vals.get('picking_type_id', defaults.get('picking_type_id')):
			if picking_type.sequence_id:
				vals['name'] = picking_type.sequence_id.next_by_id()

		# As the on_change in one2many list is WIP, we will overwrite the locations on the stock moves here
		# As it is a create the format will be a list of (0, 0, dict)
		moves = vals.get('move_lines', []) + vals.get('move_ids_without_package', [])
		if moves and vals.get('location_id') and vals.get('location_dest_id'):
			for move in moves:
				if len(move) == 3 and move[0] == 0:
					move[2]['location_id'] = vals['location_id']
					move[2]['location_dest_id'] = vals['location_dest_id']
					# When creating a new picking, a move can have no `company_id` (create before
					# picking type was defined) or a different `company_id` (the picking type was
					# changed for an another company picking type after the move was created).
					# So, we define the `company_id` in one of these cases.
					picking_type = self.env['stock.picking.type'].browse(vals['picking_type_id'])
					if 'picking_type_id' not in move[2] or move[2]['picking_type_id'] != picking_type.id:
						move[2]['picking_type_id'] = picking_type.id
						move[2]['company_id'] = picking_type.company_id.id
		# make sure to write `schedule_date` *after* the `stock.move` creation in
		# order to get a determinist execution of `_set_scheduled_date`
		scheduled_date = vals.pop('scheduled_date', False)
		res = super(Picking, self).create(vals)
		if scheduled_date:
			res.with_context(mail_notrack=True).write({'scheduled_date': scheduled_date})
		res._autoconfirm_picking()

		# set partner as follower
		if vals.get('partner_id'):
			for picking in res.filtered(lambda p: p.location_id.usage == 'supplier' or p.location_dest_id.usage == 'customer'):
				picking.message_subscribe([vals.get('partner_id')])
		if vals.get('picking_type_id'):
			for move in res.move_lines:
				if not move.description_picking:
					move.description_picking = move.product_id.with_context(lang=move._get_lang())._get_description(move.picking_id.picking_type_id)

		return res

	def write(self, vals):
		#_logger.info('--MASUK WRITE PICKING--')
		if vals.get('picking_type_id') and self.state != 'draft':
			raise UserError(_("Changing the operation type of this record is forbidden at this point."))
		# set partner as a follower and unfollow old partner
		if vals.get('partner_id'):
			for picking in self:
				if picking.location_id.usage == 'supplier' or picking.location_dest_id.usage == 'customer':
					if picking.partner_id:
						picking.message_unsubscribe(picking.partner_id.ids)
					picking.message_subscribe([vals.get('partner_id')])
		res = super(Picking, self).write(vals)
		if vals.get('signature'):
			for picking in self:
				picking._attach_sign()
		# Change locations of moves if those of the picking change
		after_vals = {}
		if vals.get('location_id'):
			after_vals['location_id'] = vals['location_id']
		if vals.get('location_dest_id'):
			after_vals['location_dest_id'] = vals['location_dest_id']
		if after_vals:
			self.mapped('move_lines').filtered(lambda move: not move.scrapped).write(after_vals)
		if vals.get('move_lines'):
			self._autoconfirm_picking()

		return res
		
	def button_validate(self):
		# Clean-up the context key at validation to avoid forcing the creation of immediate
		# transfers.
		ctx = dict(self.env.context)
		ctx.pop('default_immediate_transfer', None)
		self = self.with_context(ctx)
		#_logger.info('--MASUK button validate PICKING--')
		# Sanity checks.
		pickings_without_moves = self.browse()
		pickings_without_quantities = self.browse()
		pickings_without_lots = self.browse()
		products_without_lots = self.env['product.product']
		#_logger.info('=pickings_without_moves : %s=', str(pickings_without_moves))
		#_logger.info('=pickings_without_quantities : %s=', str(pickings_without_quantities))
		#_logger.info('=pickings_without_lots : %s=', str(pickings_without_lots))
		#_logger.info('=products_without_lots : %s=', str(products_without_lots))
		for picking in self:
			if not picking.move_lines and not picking.move_line_ids:
				pickings_without_moves |= picking

			picking.message_subscribe([self.env.user.partner_id.id])
			picking_type = picking.picking_type_id
			precision_digits = self.env['decimal.precision'].precision_get('Product Unit of Measure')
			no_quantities_done = all(float_is_zero(move_line.qty_done, precision_digits=precision_digits) for move_line in picking.move_line_ids.filtered(lambda m: m.state not in ('done', 'cancel')))
			no_reserved_quantities = all(float_is_zero(move_line.product_qty, precision_rounding=move_line.product_uom_id.rounding) for move_line in picking.move_line_ids)

			if no_reserved_quantities and no_quantities_done:
				pickings_without_quantities |= picking

			if picking_type.use_create_lots or picking_type.use_existing_lots:
				lines_to_check = picking.move_line_ids
				if not no_quantities_done:
					lines_to_check = lines_to_check.filtered(lambda line: float_compare(line.qty_done, 0, precision_rounding=line.product_uom_id.rounding))
				for line in lines_to_check:
					product = line.product_id
					if product and product.tracking != 'none':
						if not line.lot_name and not line.lot_id:
							pickings_without_lots |= picking
							products_without_lots |= product

		if not self._should_show_transfers():
			if pickings_without_moves:
				raise UserError(_('Please add some items to move.'))
			if pickings_without_quantities:
				raise UserError(self._get_without_quantities_error_message())
			if pickings_without_lots:
				raise UserError(_('You need to supply a Lot/Serial number for products %s.') % ', '.join(products_without_lots.mapped('display_name')))
		else:
			message = ""
			if pickings_without_moves:
				message += _('Transfers %s: Please add some items to move.') % ', '.join(pickings_without_moves.mapped('name'))
			if pickings_without_quantities:
				message += _('\n\nTransfers %s: You cannot validate these transfers if no quantities are reserved nor done. To force these transfers, switch in edit more and encode the done quantities.') % ', '.join(pickings_without_quantities.mapped('name'))
			if pickings_without_lots:
				message += _('\n\nTransfers %s: You need to supply a Lot/Serial number for products %s.') % (', '.join(pickings_without_lots.mapped('name')), ', '.join(products_without_lots.mapped('display_name')))
			if message:
				raise UserError(message.lstrip())

		# Run the pre-validation wizards. Processing a pre-validation wizard should work on the
		# moves and/or the context and never call `_action_done`.
		if not self.env.context.get('button_validate_picking_ids'):
			self = self.with_context(button_validate_picking_ids=self.ids)
		res = self._pre_action_done_hook()
		if res is not True:
			return res

		# Call `_action_done`.
		if self.env.context.get('picking_ids_not_to_backorder'):
			pickings_not_to_backorder = self.browse(self.env.context['picking_ids_not_to_backorder'])
			pickings_to_backorder = self - pickings_not_to_backorder
		else:
			pickings_not_to_backorder = self.env['stock.picking']
			pickings_to_backorder = self
		_logger.info('=pickings_not_to_backorder : %s=', str(pickings_not_to_backorder))
		_logger.info('=pickings_to_backorder : %s=', str(pickings_to_backorder))	
		pickings_not_to_backorder.with_context(cancel_backorder=True)._action_done()
		pickings_to_backorder.with_context(cancel_backorder=False)._action_done()
		return True

	def _autoconfirm_picking(self):
		""" Automatically run `action_confirm` on `self` if the picking is an immediate transfer or
		if the picking is a planned transfer and one of its move was added after the initial
		call to `action_confirm`. Note that `action_confirm` will only work on draft moves.
		"""
		# Clean-up the context key to avoid forcing the creation of immediate transfers.
		ctx = dict(self.env.context)
		ctx.pop('default_immediate_transfer', None)
		self = self.with_context(ctx)
		_logger.info('--MASUK autoconfirm PICKING--')
		for picking in self:
			if picking.state in ('done', 'cancel'):
				continue
			if not picking.move_lines and not picking.package_level_ids:
				continue
			if picking.immediate_transfer or any(move.additional for move in picking.move_lines):
				picking.action_confirm()
				# Make sure the reservation is bypassed in immediate transfer mode.
				if picking.immediate_transfer:
					picking.move_lines.write({'state': 'assigned'})

'''	def _check_immediate(self):
		immediate_pickings = self.browse()
		precision_digits = self.env['decimal.precision'].precision_get('Product Unit of Measure')
		for picking in self:
			if all((float_is_zero(move_line.qty_done, precision_digits=precision_digits) and 
			float_is_zero(move_line.qty_done1, precision_digits=precision_digits) and
			float_is_zero(move_line.qty_done2, precision_digits=precision_digits)) 
			for move_line in picking.move_line_ids.filtered(lambda m: m.state not in ('done', 'cancel'))):
			 	immediate_pickings |= picking
		return immediate_pickings
'''	



class StockBackorderConfirmation(models.TransientModel):
	_inherit = 'stock.backorder.confirmation'

	def process(self):
		pickings_to_do = self.env['stock.picking']
		pickings_not_to_do = self.env['stock.picking']
		_logger.info('~ PROCESS bACKoRDERcONFIRMATION ~')
		for line in self.backorder_confirmation_line_ids:
			if line.to_backorder is True:
				pickings_to_do |= line.picking_id
			else:
				pickings_not_to_do |= line.picking_id

		for pick_id in pickings_not_to_do:
			moves_to_log = {}
			for move in pick_id.move_lines:
				if float_compare(move.product_uom_qty,
								 move.quantity_done,
								 precision_rounding=move.product_uom.rounding) > 0:
					moves_to_log[move] = (move.quantity_done, move.product_uom_qty)
				#_logger.info('moves_to_log : %s', str(moves_to_log[move]))
				_logger.info('moves_to_log[%i] : %s',move,str(moves_to_log[move]))
			pick_id._log_less_quantities_than_expected(moves_to_log)

		pickings_to_validate = self.env.context.get('button_validate_picking_ids')
		_logger.info('pickings_to_validate : %s', str(pickings_to_validate))
		if pickings_to_validate:
			pickings_to_validate = self.env['stock.picking'].browse(pickings_to_validate).with_context(skip_backorder=True)
			if pickings_not_to_do:
				pickings_to_validate = pickings_to_validate.with_context(picking_ids_not_to_backorder=pickings_not_to_do.ids)
			return pickings_to_validate.button_validate()
		return True