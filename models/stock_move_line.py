# -*- coding: utf-8 -*-

from odoo.tools.float_utils import float_compare, float_is_zero, float_round
from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import UserError
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)

class StockMoveLine(models.Model):
	_inherit = "stock.move.line"

	product_uom_id1 = fields.Many2one('uom.uom', 'UoM 1', help="Extra unit of measure.")
	product_uom_id2 = fields.Many2one('uom.uom', 'UoM 2', help="Extra unit of measure.")
	#always product_qty1 = product_uom_qty1
	#always product_qty2 = product_uom_qty2
	product_uom_qty1 = fields.Float('Reserved 1', default=0.0, digits='Product Unit of Measure', required=True)
	product_uom_qty2 = fields.Float('Reserved 2', default=0.0, digits='Product Unit of Measure', required=True)
	qty_done1 = fields.Float('Done 1', default=0.0, digits='Product Unit of Measure', copy=False)
	qty_done2 = fields.Float('Done 2', default=0.0, digits='Product Unit of Measure', copy=False)
	
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
			#_logger.info('*ml.move_id.product_uom_qty : %s*', str(ml.move_id.product_uom_qty))
			#_logger.info('*ml.move_id.qty1 : %s*', str(ml.move_id.qty1))
			#_logger.info('*ml.move_id.qty2 : %s*', str(ml.move_id.qty2))
			if ml.move_id and \
					ml.move_id.picking_id and \
					ml.move_id.picking_id.immediate_transfer and \
					ml.move_id.state != 'done' and \
					'qty_done' in vals:
				ml.move_id.product_uom_qty = ml.move_id.quantity_done
				ml.move_id.product_uom_qty1 = ml.move_id.quantity_done1
				ml.move_id.product_uom_qty2 = ml.move_id.quantity_done2
			#_logger.info('*ml.move_id.quantity_done : %s*', str(ml.move_id.quantity_done))
			#_logger.info('*ml.move_id.done1 : %s*', str(ml.move_id.done1))
			#_logger.info('*ml.move_id.done2 : %s*', str(ml.move_id.done2))
			if ml.state == 'done':
				if 'qty_done' in vals:
					ml.move_id.product_uom_qty = ml.move_id.quantity_done
					ml.move_id.product_uom_qty1 = ml.move_id.quantity_done1
					ml.move_id.product_uom_qty2 = ml.move_id.quantity_done2
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
					extra_qty1 = ml.qty_done1 - ml.product_qty1
					extra_qty2 = ml.qty_done2 - ml.product_qty2
					ml._free_reservation(ml.product_id, ml.location_id, extra_qty, extra_qty1, extra_qty2, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id, ml_to_ignore=done_ml)
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
		
	def _free_reservation(self, product_id, location_id, quantity, quantity1, quantity2, lot_id=None, package_id=None, owner_id=None, ml_to_ignore=None):
		""" When editing a done move line or validating one with some forced quantities, it is
		possible to impact quants that were not reserved. It is therefore necessary to edit or
		unlink the move lines that reserved a quantity now unavailable.

		:param ml_to_ignore: recordset of `stock.move.line` that should NOT be unreserved
		"""
		self.ensure_one()

		if ml_to_ignore is None:
			ml_to_ignore = self.env['stock.move.line']
		ml_to_ignore |= self

		# Check the available quantity, with the `strict` kw set to `True`. If the available
		# quantity is greather than the quantity now unavailable, there is nothing to do.
		available_quantity = self.env['stock.quant']._get_available_quantity(
			product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=True
		)
		if quantity > available_quantity:
			# We now have to find the move lines that reserved our now unavailable quantity. We
			# take care to exclude ourselves and the move lines were work had already been done.
			outdated_move_lines_domain = [
				('state', 'not in', ['done', 'cancel']),
				('product_id', '=', product_id.id),
				('lot_id', '=', lot_id.id if lot_id else False),
				('location_id', '=', location_id.id),
				('owner_id', '=', owner_id.id if owner_id else False),
				('package_id', '=', package_id.id if package_id else False),
				('product_qty', '>', 0.0),
				('id', 'not in', ml_to_ignore.ids),
			]
			# We take the current picking first, then the pickings with the latest scheduled date
			current_picking_first = lambda cand: (
				cand.picking_id != self.move_id.picking_id,
				-(cand.picking_id.scheduled_date or cand.move_id.date).timestamp()
				if cand.picking_id or cand.move_id
				else -cand.id,
			)
			outdated_candidates = self.env['stock.move.line'].search(outdated_move_lines_domain).sorted(current_picking_first)

			# As the move's state is not computed over the move lines, we'll have to manually
			# recompute the moves which we adapted their lines.
			move_to_recompute_state = self.env['stock.move']

			rounding = self.product_uom_id.rounding
			for candidate in outdated_candidates:
				if float_compare(candidate.product_qty, quantity, precision_rounding=rounding) <= 0:
					quantity -= candidate.product_qty
					quantity1 -= candidate.product_qty1
					quantity2 -= candidate.product_qty2
					move_to_recompute_state |= candidate.move_id
					if candidate.qty_done:
						candidate.product_uom_qty = 0.0
						candidate.product_uom_qty1 = 0.0
						candidate.product_uom_qty2 = 0.0
					else:
						candidate.unlink()
					if float_is_zero(quantity, precision_rounding=rounding):
						break
				else:
					# split this move line and assign the new part to our extra move
					quantity_split = float_round(
						candidate.product_qty - quantity,
						precision_rounding=self.product_uom_id.rounding,
						rounding_method='UP')
					quantity_split1 = float_round(
						candidate.product_qty1 - quantity1,
						precision_rounding=self.product_uom_id1.rounding,
						rounding_method='UP')
					quantity_split2 = float_round(
						candidate.product_qty2 - quantity2,
						precision_rounding=self.product_uom_id2.rounding,
						rounding_method='UP')
					candidate.product_uom_qty = self.product_id.uom_id._compute_quantity(quantity_split, candidate.product_uom_id, rounding_method='HALF-UP')
					candidate.product_uom_qty1 = self.quantity_split1
					candidate.product_uom_qty2 = self.quantity_split2
					move_to_recompute_state |= candidate.move_id
					break
			move_to_recompute_state._recompute_state()
