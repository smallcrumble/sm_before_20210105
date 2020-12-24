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