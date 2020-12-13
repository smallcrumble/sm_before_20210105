# -*- coding: utf-8 -*-

from odoo import models, fields


class StockMove(models.Model):
	_inherit = "stock.move"
	
	qty1 = fields.Float('Demand 1')
	done1 = fields.Float('Done 1')
	uom1 = fields.Many2one('uom.uom', 'UoM 1', help="Extra unit of measure.")
	qty2 = fields.Float('Demand 2')
	done2 = fields.Float('Done 2')
	uom2 = fields.Many2one('uom.uom', 'UoM 2', help="Extra unit of measure.")

	def _prepare_move_line_vals(self, quantity=None, reserved_quant=None):
		res = super(StockMove, self)._prepare_move_line_vals(quantity, reserved_quant)
		res['qty_done1']=self.done1
		res['uom1']=self.uom1.id
		res['qty_done2']=self.done2
		res['uom2']=self.uom2.id
		return res
	
class StockMoveLine(models.Model):
	_inherit = "stock.move.line"

	qty_done1 = fields.Float('Done 1') #done1
	uom1 = fields.Many2one('uom.uom', 'UoM 1', help="Extra unit of measure.")
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

class Picking(models.Model):
	_inherit = "stock.picking"

	def _check_immediate(self):
		immediate_pickings = self.browse()
		precision_digits = self.env['decimal.precision'].precision_get('Product Unit of Measure')
		for picking in self:
			if all(float_is_zero(move_line.qty_done, precision_digits=precision_digits) and 
			float_is_zero(move_line.qty_done1, precision_digits=precision_digits) and
			float_is_zero(move_line.qty_done2, precision_digits=precision_digits) 
			for move_line in picking.move_line_ids.filtered(lambda m: m.state not in ('done', 'cancel'))):
				immediate_pickings |= picking
		return immediate_pickings