# -*- coding: utf-8 -*-

from odoo import models, fields
from odoo.tools.float_utils import float_compare, float_is_zero, float_round
from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import UserError
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)

class StockMove(models.Model):
	_inherit = "stock.move"
	
	qty1 = fields.Float('Demand 1')
	done1 = fields.Float('Done 1', compute='_quantity_done_compute', digits='Product Unit of Measure', inverse='_quantity_done_set')
	uom1 = fields.Many2one('uom.uom', 'UoM 1', help="Extra unit of measure.")
	qty2 = fields.Float('Demand 2')
	done2 = fields.Float('Done 2', compute='_quantity_done_compute', digits='Product Unit of Measure', inverse='_quantity_done_set')
	uom2 = fields.Many2one('uom.uom', 'UoM 2', help="Extra unit of measure.")

	def _prepare_move_line_vals(self, quantity=None, reserved_quant=None):
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
			#'qty1': self.qty1,
			'uom1': self.uom1.id,
			#'qty2': self.qty2,
			'uom2': self.uom2.id,
		}
		if quantity:
			rounding = self.env['decimal.precision'].precision_get('Product Unit of Measure')
			uom_quantity = self.product_id.uom_id._compute_quantity(quantity, self.product_uom, rounding_method='HALF-UP')
			uom_quantity = float_round(uom_quantity, precision_digits=rounding)
			uom_quantity_back_to_product_uom = self.product_uom._compute_quantity(uom_quantity, self.product_id.uom_id, rounding_method='HALF-UP')
			_logger.info('qty1   : %s', str(self.qty1))
			_logger.info('qty2   : %s', str(self.qty2))
			if float_compare(quantity, uom_quantity_back_to_product_uom, precision_digits=rounding) == 0:
				vals = dict(vals, product_uom_qty=uom_quantity)
			else:
				vals = dict(vals, product_uom_qty=quantity, product_uom_id=self.product_id.uom_id.id)
			vals = dict(vals,qty1=self.qty1)
			vals = dict(vals,qty2=self.qty2)
			_logger.info('vals  : %s', str(vals))
			
		if reserved_quant:
			vals = dict(
				vals,
				location_id=reserved_quant.location_id.id,
				lot_id=reserved_quant.lot_id.id or False,
				package_id=reserved_quant.package_id.id or False,
				owner_id =reserved_quant.owner_id.id or False,
			)
		_logger.info('vals sblm return : %s', str(vals))
		return vals

	@api.depends('move_line_ids.qty_done', 'move_line_ids.qty_done1', 'move_line_ids.qty_done2', 'move_line_ids.product_uom_id', 'move_line_ids.uom1', 'move_line_ids.uom2', 'move_line_nosuggest_ids.qty_done', 'picking_type_id')
	def _quantity_done_compute(self):
		if not any(self._ids):
			# onchange
			for move in self:
				quantity_done = 0
				done1 = 0
				done2 = 0
				for move_line in move._get_move_lines():
					quantity_done += move_line.product_uom_id._compute_quantity(
						move_line.qty_done, move.product_uom, round=False)
					done1 += move_line.uom1._compute_quantity(
						move_line.qty_done1, move.uom1, round=False)
					done2 += move_line.uom2._compute_quantity(
						move_line.qty_done2, move.uom2, round=False)
				move.quantity_done = quantity_done
				move.done1 = done1
				move.done2 = done2
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
				['move_id', 'uom1', 'qty_done1'], ['move_id', 'uom1'],
				lazy=False
			)

			data2 = self.env['stock.move.line'].read_group(
				[('id', 'in', move_lines.ids)],
				['move_id', 'uom2', 'qty_done2'], ['move_id', 'uom2'],
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
				if d['uom1'] and d['qty_done1'] :
					#_logger.info('d 1 : %s', str(d))
					rec1[d['move_id'][0]] += [(d['uom1'][0], d['qty_done1'])]
			for d in data2:
				if d['uom2'] and d['qty_done2'] :
					#_logger.info('d 2 : %s', str(d))
					rec2[d['move_id'][0]] += [(d['uom2'][0], d['qty_done2'])]
			
			for move in self:
				uom = move.product_uom
				uom1 = move.uom1
				uom2 = move.uom2
				move.quantity_done = sum(
					self.env['uom.uom'].browse(line_uom_id)._compute_quantity(qty, uom, round=False)
					 for line_uom_id, qty in rec.get(move.ids[0] if move.ids else move.id, [])
				)
				move.done1 = sum(
					self.env['uom.uom'].browse(line_uom_id)._compute_quantity(qty, uom1, round=False)
					 for line_uom_id, qty in rec1.get(move.ids[0] if move.ids else move.id, [])
				)
				move.done2 = sum(
					self.env['uom.uom'].browse(line_uom_id)._compute_quantity(qty, uom2, round=False)
					 for line_uom_id, qty in rec2.get(move.ids[0] if move.ids else move.id, [])
				)

	def _quantity_done_set(self):
		quantity_done = self[0].quantity_done  # any call to create will invalidate `move.quantity_done`
		quantity_done1 = self[0].done1
		quantity_done2 = self[0].done2
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
				_logger.info('_quantity_done_set : %s', str(quantity_done))
			else:
				# Bypass the error if we're trying to write the same value.
				ml_quantity_done = 0
				for move_line in move_lines:
					ml_quantity_done += move_line.product_uom_id._compute_quantity(move_line.qty_done, move.product_uom, round=False)
				if float_compare(quantity_done, ml_quantity_done, precision_rounding=move.product_uom.rounding) != 0:
					raise UserError(_("Cannot set the done quantity from this stock move, work directly with the move lines."))

class StockMoveLine(models.Model):
	_inherit = "stock.move.line"

	qty1 = fields.Float('Demand 1', default=0.0)
	qty_done1 = fields.Float('Done 1', default=0.0) #done1
	uom1 = fields.Many2one('uom.uom', 'UoM 1', help="Extra unit of measure.")
	qty2 = fields.Float('Demand 2', default=0.0)
	qty_done2 = fields.Float('Done 2', default=0.0) #done2
	uom2 = fields.Many2one('uom.uom', 'UoM 2', help="Extra unit of measure.")

	'''def create_move(move_line):
		res = super(StockMoveLine, self).create_move(move_line)
		res['qty1']=self.qty_done1
		#res['uom1']=self.uom1.id
		res['qty2']=self.qty_done2
		#res['uom2']=self.uom2.id
		return res
	'''
	@api.model_create_multi
	def create(self, vals_list):
		_logger.info('**MASUK create MOVE_LINE**')
		for vals in vals_list:
			if vals.get('move_id'):
				vals['company_id'] = self.env['stock.move'].browse(vals['move_id']).company_id.id
			elif vals.get('picking_id'):
				vals['company_id'] = self.env['stock.picking'].browse(vals['picking_id']).company_id.id

		mls = super().create(vals_list)

		def create_move(move_line):
			_logger.info('**MASUK create_move MOVE_LINE**')
			new_move = self.env['stock.move'].create({
				'name': _('New Move:') + move_line.product_id.display_name,
				'product_id': move_line.product_id.id,
				'product_uom_qty': move_line.qty_done,
				'product_uom': move_line.product_uom_id.id,
				'description_picking': move_line.description_picking,
				'location_id': move_line.picking_id.location_id.id,
				'location_dest_id': move_line.picking_id.location_dest_id.id,
				'picking_id': move_line.picking_id.id,
				'state': move_line.picking_id.state,
				'picking_type_id': move_line.picking_id.picking_type_id.id,
				'restrict_partner_id': move_line.picking_id.owner_id.id,
				'company_id': move_line.picking_id.company_id.id,
			})
			move_line.move_id = new_move.id

		# If the move line is directly create on the picking view.
		# If this picking is already done we should generate an
		# associated done move.
		for move_line in mls:
			if move_line.move_id or not move_line.picking_id:
				continue
			if move_line.picking_id.state != 'done':
				moves = move_line.picking_id.move_lines.filtered(lambda x: x.product_id == move_line.product_id)
				moves = sorted(moves, key=lambda m: m.quantity_done < m.product_qty, reverse=True)
				if moves:
					move_line.move_id = moves[0].id
				else:
					create_move(move_line)
			else:
				create_move(move_line)

		for ml, vals in zip(mls, vals_list):
			_logger.info('*ml.move_id.product_uom_qty : %s*', str(ml.move_id.product_uom_qty))
			_logger.info('*ml.move_id.qty1 : %s*', str(ml.move_id.qty1))
			_logger.info('*ml.move_id.qty2 : %s*', str(ml.move_id.qty2))
			if ml.move_id and \
					ml.move_id.picking_id and \
					ml.move_id.picking_id.immediate_transfer and \
					ml.move_id.state != 'done' and \
					'qty_done' in vals:
				ml.move_id.product_uom_qty = ml.move_id.quantity_done
				ml.move_id.qty1 = ml.move_id.done1
				ml.move_id.qty2 = ml.move_id.done2
			_logger.info('*ml.move_id.quantity_done : %s*', str(ml.move_id.quantity_done))
			_logger.info('*ml.move_id.done1 : %s*', str(ml.move_id.done1))
			_logger.info('*ml.move_id.done2 : %s*', str(ml.move_id.done2))
			if ml.state == 'done':
				if 'qty_done' in vals:
					ml.move_id.product_uom_qty = ml.move_id.quantity_done
				if ml.product_id.type == 'product':
					Quant = self.env['stock.quant']
					quantity = ml.product_uom_id._compute_quantity(ml.qty_done, ml.move_id.product_id.uom_id,rounding_method='HALF-UP')
					in_date = None
					available_qty, in_date = Quant._update_available_quantity(ml.product_id, ml.location_id, -quantity, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id)
					if available_qty < 0 and ml.lot_id:
						# see if we can compensate the negative quants with some untracked quants
						untracked_qty = Quant._get_available_quantity(ml.product_id, ml.location_id, lot_id=False, package_id=ml.package_id, owner_id=ml.owner_id, strict=True)
						if untracked_qty:
							taken_from_untracked_qty = min(untracked_qty, abs(quantity))
							Quant._update_available_quantity(ml.product_id, ml.location_id, -taken_from_untracked_qty, lot_id=False, package_id=ml.package_id, owner_id=ml.owner_id)
							Quant._update_available_quantity(ml.product_id, ml.location_id, taken_from_untracked_qty, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id)
					Quant._update_available_quantity(ml.product_id, ml.location_dest_id, quantity, lot_id=ml.lot_id, package_id=ml.result_package_id, owner_id=ml.owner_id, in_date=in_date)
				next_moves = ml.move_id.move_dest_ids.filtered(lambda move: move.state not in ('done', 'cancel'))
				next_moves._do_unreserve()
				next_moves._action_assign()
		return mls
'''
	def write(self, vals):
		_logger.info('**MASUK WRITE**')
		if self.env.context.get('bypass_reservation_update'):
			return super(StockMoveLine, self).write(vals)

		if 'product_id' in vals and any(vals.get('state', ml.state) != 'draft' and vals['product_id'] != ml.product_id.id for ml in self):
			raise UserError(_("Changing the product is only allowed in 'Draft' state."))

		moves_to_recompute_state = self.env['stock.move']
		Quant = self.env['stock.quant']
		precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
		triggers = [
			('location_id', 'stock.location'),
			('location_dest_id', 'stock.location'),
			('lot_id', 'stock.production.lot'),
			('package_id', 'stock.quant.package'),
			('result_package_id', 'stock.quant.package'),
			('owner_id', 'res.partner')
		]
		updates = {}
		for key, model in triggers:
			if key in vals:
				updates[key] = self.env[model].browse(vals[key])

		# When we try to write on a reserved move line any fields from `triggers` or directly
		# `product_uom_qty` (the actual reserved quantity), we need to make sure the associated
		# quants are correctly updated in order to not make them out of sync (i.e. the sum of the
		# move lines `product_uom_qty` should always be equal to the sum of `reserved_quantity` on
		# the quants). If the new charateristics are not available on the quants, we chose to
		# reserve the maximum possible.
		if updates or 'product_uom_qty' in vals:
			for ml in self.filtered(lambda ml: ml.state in ['partially_available', 'assigned'] and ml.product_id.type == 'product'):

				if 'product_uom_qty' in vals:
					new_product_uom_qty = ml.product_uom_id._compute_quantity(
						vals['product_uom_qty'], ml.product_id.uom_id, rounding_method='HALF-UP')
					# Make sure `product_uom_qty` is not negative.
					if float_compare(new_product_uom_qty, 0, precision_rounding=ml.product_id.uom_id.rounding) < 0:
						raise UserError(_('Reserving a negative quantity is not allowed.'))
				else:
					new_product_uom_qty = ml.product_qty

				# Unreserve the old charateristics of the move line.
				if not ml._should_bypass_reservation(ml.location_id):
					try:
						Quant._update_reserved_quantity(ml.product_id, ml.location_id, -ml.product_qty, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id, strict=True)
					except UserError:
						# If we were not able to unreserve on tracked quants, we can use untracked ones.
						if ml.lot_id:
							Quant._update_reserved_quantity(ml.product_id, ml.location_id, -ml.product_qty, lot_id=False, package_id=ml.package_id, owner_id=ml.owner_id, strict=True)
						else:
							raise

				# Reserve the maximum available of the new charateristics of the move line.
				if not ml._should_bypass_reservation(updates.get('location_id', ml.location_id)):
					reserved_qty = 0
					try:
						q = Quant._update_reserved_quantity(ml.product_id, updates.get('location_id', ml.location_id), new_product_uom_qty, lot_id=updates.get('lot_id', ml.lot_id),
															 package_id=updates.get('package_id', ml.package_id), owner_id=updates.get('owner_id', ml.owner_id), strict=True)
						reserved_qty = sum([x[1] for x in q])
					except UserError:
						if updates.get('lot_id'):
							# If we were not able to reserve on tracked quants, we can use untracked ones.
							try:
								q = Quant._update_reserved_quantity(ml.product_id, updates.get('location_id', ml.location_id), new_product_uom_qty, lot_id=False,
																	 package_id=updates.get('package_id', ml.package_id), owner_id=updates.get('owner_id', ml.owner_id), strict=True)
								reserved_qty = sum([x[1] for x in q])
							except UserError:
								pass
					if reserved_qty != new_product_uom_qty:
						new_product_uom_qty = ml.product_id.uom_id._compute_quantity(reserved_qty, ml.product_uom_id, rounding_method='HALF-UP')
						moves_to_recompute_state |= ml.move_id
						ml.with_context(bypass_reservation_update=True).product_uom_qty = new_product_uom_qty

		# When editing a done move line, the reserved availability of a potential chained move is impacted. Take care of running again `_action_assign` on the concerned moves.
		if updates or 'qty_done' in vals:
			next_moves = self.env['stock.move']
			mls = self.filtered(lambda ml: ml.move_id.state == 'done' and ml.product_id.type == 'product')
			if not updates:  # we can skip those where qty_done is already good up to UoM rounding
				mls = mls.filtered(lambda ml: not float_is_zero(ml.qty_done - vals['qty_done'], precision_rounding=ml.product_uom_id.rounding))
			for ml in mls:
				_logger.info('MASUK WRITE UNDO THE ORI MOVE LINE')
				# undo the original move line
				qty_done_orig = ml.move_id.product_uom._compute_quantity(ml.qty_done, ml.move_id.product_id.uom_id, rounding_method='HALF-UP')
				in_date = Quant._update_available_quantity(ml.product_id, ml.location_dest_id, -qty_done_orig, lot_id=ml.lot_id,
													  package_id=ml.result_package_id, owner_id=ml.owner_id)[1]
				Quant._update_available_quantity(ml.product_id, ml.location_id, qty_done_orig, lot_id=ml.lot_id,
													  package_id=ml.package_id, owner_id=ml.owner_id, in_date=in_date)

				# move what's been actually done
				product_id = ml.product_id
				location_id = updates.get('location_id', ml.location_id)
				location_dest_id = updates.get('location_dest_id', ml.location_dest_id)
				qty_done = vals.get('qty_done', ml.qty_done)
				qty_done1 = vals.get('qty_done1', ml.qty_done1)
				qty_done2 = vals.get('qty_done2', ml.qty_done2)
				lot_id = updates.get('lot_id', ml.lot_id)
				package_id = updates.get('package_id', ml.package_id)
				result_package_id = updates.get('result_package_id', ml.result_package_id)
				owner_id = updates.get('owner_id', ml.owner_id)
				quantity = ml.move_id.product_uom._compute_quantity(qty_done, ml.move_id.product_id.uom_id, rounding_method='HALF-UP')
				if not ml._should_bypass_reservation(location_id):
					ml._free_reservation(product_id, location_id, quantity, lot_id=lot_id, package_id=package_id, owner_id=owner_id)
				if not float_is_zero(quantity, precision_digits=precision):
					available_qty, in_date = Quant._update_available_quantity(product_id, location_id, -quantity, lot_id=lot_id, package_id=package_id, owner_id=owner_id)
					if available_qty < 0 and lot_id:
						# see if we can compensate the negative quants with some untracked quants
						untracked_qty = Quant._get_available_quantity(product_id, location_id, lot_id=False, package_id=package_id, owner_id=owner_id, strict=True)
						if untracked_qty:
							taken_from_untracked_qty = min(untracked_qty, abs(available_qty))
							Quant._update_available_quantity(product_id, location_id, -taken_from_untracked_qty, lot_id=False, package_id=package_id, owner_id=owner_id)
							Quant._update_available_quantity(product_id, location_id, taken_from_untracked_qty, lot_id=lot_id, package_id=package_id, owner_id=owner_id)
							if not ml._should_bypass_reservation(location_id):
								ml._free_reservation(ml.product_id, location_id, untracked_qty, lot_id=False, package_id=package_id, owner_id=owner_id)
					Quant._update_available_quantity(product_id, location_dest_id, quantity, lot_id=lot_id, package_id=result_package_id, owner_id=owner_id, in_date=in_date)

				# Unreserve and reserve following move in order to have the real reserved quantity on move_line.
				next_moves |= ml.move_id.move_dest_ids.filtered(lambda move: move.state not in ('done', 'cancel'))

				# Log a note
				if ml.picking_id:
					ml._log_message(ml.picking_id, ml, 'stock.track_move_template', vals)

		res = super(StockMoveLine, self).write(vals)
		# Update scrap object linked to move_lines to the new quantity.
		if 'qty_done' in vals:
			for move in self.mapped('move_id'):
				if move.scrapped:
					move.scrap_ids.write({'scrap_qty': move.quantity_done})

		# As stock_account values according to a move's `product_uom_qty`, we consider that any
		# done stock move should have its `quantity_done` equals to its `product_uom_qty`, and
		# this is what move's `action_done` will do. So, we replicate the behavior here.
		if updates or 'qty_done' in vals:
			moves = self.filtered(lambda ml: ml.move_id.state == 'done').mapped('move_id')
			moves |= self.filtered(lambda ml: ml.move_id.state not in ('done', 'cancel') and ml.move_id.picking_id.immediate_transfer and not ml.product_uom_qty).mapped('move_id')
			for move in moves:
				move.product_uom_qty = move.quantity_done
				move.qty1 = move.done1
				move.qty2 = move.done2
			next_moves._do_unreserve()
			next_moves._action_assign()

		if moves_to_recompute_state:
			moves_to_recompute_state._recompute_state()

		return res

	def _action_done(self):
		""" This method is called during a move's `action_done`. It'll actually move a quant from
		the source location to the destination location, and unreserve if needed in the source
		location.

		This method is intended to be called on all the move lines of a move. This method is not
		intended to be called when editing a `done` move (that's what the override of `write` here
		is done.
		"""
		Quant = self.env['stock.quant']

		# First, we loop over all the move lines to do a preliminary check: `qty_done` should not
		# be negative and, according to the presence of a picking type or a linked inventory
		# adjustment, enforce some rules on the `lot_id` field. If `qty_done` is null, we unlink
		# the line. It is mandatory in order to free the reservation and correctly apply
		# `action_done` on the next move lines.
		ml_to_delete = self.env['stock.move.line']
		ml_to_create_lot = self.env['stock.move.line']
		tracked_ml_without_lot = self.env['stock.move.line']
		for ml in self:
			# Check here if `ml.qty_done` respects the rounding of `ml.product_uom_id`.
			uom_qty = float_round(ml.qty_done, precision_rounding=ml.product_uom_id.rounding, rounding_method='HALF-UP')
			precision_digits = self.env['decimal.precision'].precision_get('Product Unit of Measure')
			qty_done = float_round(ml.qty_done, precision_digits=precision_digits, rounding_method='HALF-UP')
			if float_compare(uom_qty, qty_done, precision_digits=precision_digits) != 0:
				raise UserError(_('The quantity done for the product "%s" doesn\'t respect the rounding precision \
								  defined on the unit of measure "%s". Please change the quantity done or the \
								  rounding precision of your unit of measure.') % (ml.product_id.display_name, ml.product_uom_id.name))

			qty_done_float_compared = float_compare(ml.qty_done, 0, precision_rounding=ml.product_uom_id.rounding)
			if qty_done_float_compared > 0:
				if ml.product_id.tracking != 'none':
					picking_type_id = ml.move_id.picking_type_id
					if picking_type_id:
						if picking_type_id.use_create_lots:
							# If a picking type is linked, we may have to create a production lot on
							# the fly before assigning it to the move line if the user checked both
							# `use_create_lots` and `use_existing_lots`.
							if ml.lot_name and not ml.lot_id:
								lot = self.env['stock.production.lot'].search([
									('company_id', '=', ml.company_id.id),
									('product_id', '=', ml.product_id.id),
									('name', '=', ml.lot_name),
								])
								if lot:
									ml.lot_id = lot.id
								else:
									ml_to_create_lot |= ml
						elif not picking_type_id.use_create_lots and not picking_type_id.use_existing_lots:
							# If the user disabled both `use_create_lots` and `use_existing_lots`
							# checkboxes on the picking type, he's allowed to enter tracked
							# products without a `lot_id`.
							continue
					elif ml.move_id.inventory_id:
						# If an inventory adjustment is linked, the user is allowed to enter
						# tracked products without a `lot_id`.
						continue

					if not ml.lot_id and ml not in ml_to_create_lot:
						tracked_ml_without_lot |= ml
			elif qty_done_float_compared < 0:
				raise UserError(_('No negative quantities allowed'))
			else:
				ml_to_delete |= ml

		if tracked_ml_without_lot:
			raise UserError(_('You need to supply a Lot/Serial Number for product: \n - ') +
							  '\n - '.join(tracked_ml_without_lot.mapped('product_id.display_name')))
		ml_to_create_lot._create_and_assign_production_lot()

		ml_to_delete.unlink()

		(self - ml_to_delete)._check_company()

		# Now, we can actually move the quant.
		done_ml = self.env['stock.move.line']
		for ml in self - ml_to_delete:
			if ml.product_id.type == 'product':
				rounding = ml.product_uom_id.rounding

				# if this move line is force assigned, unreserve elsewhere if needed
				if not ml._should_bypass_reservation(ml.location_id) and float_compare(ml.qty_done, ml.product_uom_qty, precision_rounding=rounding) > 0:
					qty_done_product_uom = ml.product_uom_id._compute_quantity(ml.qty_done, ml.product_id.uom_id, rounding_method='HALF-UP')
					extra_qty = qty_done_product_uom - ml.product_qty
					ml._free_reservation(ml.product_id, ml.location_id, extra_qty, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id, ml_to_ignore=done_ml)
				# unreserve what's been reserved
				if not ml._should_bypass_reservation(ml.location_id) and ml.product_id.type == 'product' and ml.product_qty:
					try:
						Quant._update_reserved_quantity(ml.product_id, ml.location_id, -ml.product_qty, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id, strict=True)
					except UserError:
						Quant._update_reserved_quantity(ml.product_id, ml.location_id, -ml.product_qty, lot_id=False, package_id=ml.package_id, owner_id=ml.owner_id, strict=True)

				# move what's been actually done
				quantity = ml.product_uom_id._compute_quantity(ml.qty_done, ml.move_id.product_id.uom_id, rounding_method='HALF-UP')
				available_qty, in_date = Quant._update_available_quantity(ml.product_id, ml.location_id, -quantity, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id)
				if available_qty < 0 and ml.lot_id:
					# see if we can compensate the negative quants with some untracked quants
					untracked_qty = Quant._get_available_quantity(ml.product_id, ml.location_id, lot_id=False, package_id=ml.package_id, owner_id=ml.owner_id, strict=True)
					if untracked_qty:
						taken_from_untracked_qty = min(untracked_qty, abs(quantity))
						Quant._update_available_quantity(ml.product_id, ml.location_id, -taken_from_untracked_qty, lot_id=False, package_id=ml.package_id, owner_id=ml.owner_id)
						Quant._update_available_quantity(ml.product_id, ml.location_id, taken_from_untracked_qty, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id)
				Quant._update_available_quantity(ml.product_id, ml.location_dest_id, quantity, lot_id=ml.lot_id, package_id=ml.result_package_id, owner_id=ml.owner_id, in_date=in_date)
			done_ml |= ml
		# Reset the reserved quantity as we just moved it to the destination location.
		_logger.info('QTY JADI 0')
		(self - ml_to_delete).with_context(bypass_reservation_update=True).write({
			'product_uom_qty': 0.00,
			'qty1': 0.00,
			'qty2': 0.00,
			'date': fields.Datetime.now(),
		})
'''		

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
					move_line.qty_done1 = move_line.qty1
					move_line.qty_done2 = move_line.qty2

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
		_logger.info('--MASUK create PICKING--')
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
		_logger.info('--MASUK WRITE PICKING--')
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
		_logger.info('--MASUK button validate PICKING--')
		# Sanity checks.
		pickings_without_moves = self.browse()
		pickings_without_quantities = self.browse()
		pickings_without_lots = self.browse()
		products_without_lots = self.env['product.product']
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
				_logger.info('moves_to_log : %s', str(moves_to_log[move]))
			pick_id._log_less_quantities_than_expected(moves_to_log)

		pickings_to_validate = self.env.context.get('button_validate_picking_ids')
		_logger.info('pickings_to_validate : %s', str(pickings_to_validate))
		if pickings_to_validate:
			pickings_to_validate = self.env['stock.picking'].browse(pickings_to_validate).with_context(skip_backorder=True)
			if pickings_not_to_do:
				pickings_to_validate = pickings_to_validate.with_context(picking_ids_not_to_backorder=pickings_not_to_do.ids)
			return pickings_to_validate.button_validate()
		return True