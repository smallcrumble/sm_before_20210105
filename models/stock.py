# -*- coding: utf-8 -*-

from odoo import models, fields
from odoo.tools.float_utils import float_is_zero
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
		res = super(StockMove, self)._prepare_move_line_vals(quantity, reserved_quant)
		res['qty1']=self.qty1
		res['qty_done1']=self.done1
		res['uom1']=self.uom1.id
		res['qty2']=self.qty2
		res['qty_done2']=self.done2
		res['uom2']=self.uom2.id
		return res

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

class StockMoveLine(models.Model):
	_inherit = "stock.move.line"

	qty1 = fields.Float('Demand 1')
	qty_done1 = fields.Float('Done 1') #done1
	uom1 = fields.Many2one('uom.uom', 'UoM 1', help="Extra unit of measure.")
	qty2 = fields.Float('Demand 2')
	qty_done2 = fields.Float('Done 2') #done2
	uom2 = fields.Many2one('uom.uom', 'UoM 2', help="Extra unit of measure.")

	'''def create_move(move_line):
		res = super(StockMoveLine, self).create_move(move_line)
		res['qty1']=self.qty_done1
		#res['uom1']=self.uom1.id
		res['qty2']=self.qty_done2
		#res['uom2']=self.uom2.id
		return res
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

'''done qty = 0 odoo otomatis pangisiin done qty = demand
class Picking(models.Model):
	_inherit = "stock.picking"

	def _check_immediate(self):
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
