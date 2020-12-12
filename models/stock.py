# -*- coding: utf-8 -*-

from odoo import models, fields


class Picking(models.Model):
	_inherit = "stock.picking"
	
	#qty1 = fields.Float('Demand 1')
	done1 = fields.Float('Done 1')
	uom1 = fields.Many2one('uom.uom', 'UoM 1', help="Extra unit of measure.")
	#qty2 = fields.Float('Demand 2')
	done2 = fields.Float('Done 2')
	uom2 = fields.Many2one('uom.uom', 'UoM 2', help="Extra unit of measure.")
	