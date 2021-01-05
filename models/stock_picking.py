# -*- coding: utf-8 -*-

from odoo.tools.float_utils import float_compare, float_is_zero, float_round
from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)

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
