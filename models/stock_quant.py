# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class StockQuant(models.Model):
	_inherit = 'stock.quant'

	product_uom_id1 = fields.Many2one(
		'uom.uom', 'UoM 1',
		readonly=True, related='product_id.uom_id1')
	product_uom_id2 = fields.Many2one(
		'uom.uom', 'UoM 2',
		readonly=True, related='product_id.uom_id2')
	quantity1 = fields.Float(
		'Quantity 1',
		help='Quantity of products in this quant, in the default unit of measure of the product',
		readonly=True)
	quantity2 = fields.Float(
		'Quantity 2',
		help='Quantity of products in this quant, in the default unit of measure of the product',
		readonly=True)
	inventory_quantity1 = fields.Float(
		'Inventoried Quantity 1', compute='_compute_inventory_quantity1',
		inverse='_set_inventory_quantity', groups='stock.group_stock_manager')
	inventory_quantity2 = fields.Float(
		'Inventoried Quantity 2', compute='_compute_inventory_quantity2',
		inverse='_set_inventory_quantity', groups='stock.group_stock_manager')
	reserved_quantity1 = fields.Float(
		'Reserved Quantity 1',
		default=0.0,
		help='Quantity of reserved products in this quant, in the default unit of measure of the product',
		readonly=True)
	reserved_quantity2 = fields.Float(
		'Reserved Quantity 2',
		default=0.0,
		help='Quantity of reserved products in this quant, in the default unit of measure of the product',
		readonly=True)
	available_quantity1 = fields.Float(
		'Available Quantity 1',
		help="On hand quantity which hasn't been reserved on a transfer, in the default unit of measure of the product",
		compute='_compute_available_quantity1')
	available_quantity2 = fields.Float(
		'Available Quantity 2',
		help="On hand quantity which hasn't been reserved on a transfer, in the default unit of measure of the product",
		compute='_compute_available_quantity2')

	@api.depends('quantity1', 'reserved_quantity1')
	def _compute_available_quantity1(self):
		for quant in self:
			quant.available_quantity1 = quant.quantity1 - quant.reserved_quantity1

	@api.depends('quantity2', 'reserved_quantity2')
	def _compute_available_quantity2(self):
		for quant in self:
			quant.available_quantity2 = quant.quantity2 - quant.reserved_quantity2

	@api.depends('quantity1')
	def _compute_inventory_quantity1(self):
		if not self._is_inventory_mode():
			self.inventory_quantity1 = 0
			return
		for quant in self:
			quant.inventory_quantity1 = quant.quantity1

	@api.depends('quantity2')
	def _compute_inventory_quantity2(self):
		if not self._is_inventory_mode():
			self.inventory_quantity2 = 0
			return
		for quant in self:
			quant.inventory_quantity2 = quant.quantity2

	def _set_inventory_quantity(self):
		""" Inverse method to create stock move when `inventory_quantity` is set
		(`inventory_quantity` is only accessible in inventory mode).
		"""
		if not self._is_inventory_mode():
			return
		for quant in self:
			# Get the quantity to create a move for.
			rounding = quant.product_id.uom_id.rounding
			diff = float_round(quant.inventory_quantity - quant.quantity, precision_rounding=rounding)
			diff_float_compared = float_compare(diff, 0, precision_rounding=rounding)
			diff1 = float_round(quant.inventory_quantity1 - quant.quantity1, precision_rounding=rounding)
			diff2 = float_round(quant.inventory_quantity2 - quant.quantity2, precision_rounding=rounding)
			# Create and vaidate a move so that the quant matches its `inventory_quantity`.
			if diff_float_compared == 0:
				continue
			elif diff_float_compared > 0:
				move_vals = quant._get_inventory_move_values(diff, diff1, diff2, quant.product_id.with_company(quant.company_id).property_stock_inventory, quant.location_id)
			else:
				move_vals = quant._get_inventory_move_values(-diff, -diff1, -diff2, quant.location_id, quant.product_id.with_company(quant.company_id).property_stock_inventory, out=True)
			move = quant.env['stock.move'].with_context(inventory_mode=False).create(move_vals)
			move._action_done()

	@api.model
	def create(self, vals):
		""" Override to handle the "inventory mode" and create a quant as
		superuser the conditions are met.
		"""
		if self._is_inventory_mode() and 'inventory_quantity' in vals:
			allowed_fields = self._get_inventory_fields_create()
			if any(field for field in vals.keys() if field not in allowed_fields):
				raise UserError(_("Quant's creation is restricted, you can't do this operation."))
			inventory_quantity = vals.pop('inventory_quantity')
			inventory_quantity1 = vals.pop('inventory_quantity1')
			inventory_quantity2 = vals.pop('inventory_quantity2')

			# Create an empty quant or write on a similar one.
			product = self.env['product.product'].browse(vals['product_id'])
			location = self.env['stock.location'].browse(vals['location_id'])
			lot_id = self.env['stock.production.lot'].browse(vals.get('lot_id'))
			package_id = self.env['stock.quant.package'].browse(vals.get('package_id'))
			owner_id = self.env['res.partner'].browse(vals.get('owner_id'))
			quant = self._gather(product, location, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=True)
			if quant:
				quant = quant[0]
			else:
				quant = self.sudo().create(vals)
			# Set the `inventory_quantity` field to create the necessary move.
			quant.inventory_quantity = inventory_quantity
			quant.inventory_quantity1 = inventory_quantity1
			quant.inventory_quantity2 = inventory_quantity2
			return quant
		res = super(StockQuant, self).create(vals)
		if self._is_inventory_mode():
			res._check_company()
		return res

	
	@api.model
	def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
		""" Override to set the `inventory_quantity` field if we're in "inventory mode" as well
		as to compute the sum of the `available_quantity` field.
		"""
		if 'available_quantity' in fields:
			if 'quantity' not in fields:
				fields.append('quantity')
			if 'quantity1' not in fields:
				fields.append('quantity1')
			if 'quantity2' not in fields:
				fields.append('quantity2')
			if 'reserved_quantity' not in fields:
				fields.append('reserved_quantity')
			if 'reserved_quantity1' not in fields:
				fields.append('reserved_quantity1')
			if 'reserved_quantity2' not in fields:
				fields.append('reserved_quantity2')
		result = super(StockQuant, self).read_group(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
		for group in result:
			if self._is_inventory_mode():
				group['inventory_quantity'] = group.get('quantity', 0)
				group['inventory_quantity1'] = group.get('quantity1', 0)
				group['inventory_quantity2'] = group.get('quantity2', 0)
			if 'available_quantity' in fields:
				group['available_quantity'] = group['quantity'] - group['reserved_quantity']
				group['available_quantity1'] = group['quantity1'] - group['reserved_quantity1']
				group['available_quantity2'] = group['quantity2'] - group['reserved_quantity2']
		return result

	@api.model
	def _get_available_quantity1(self, product_id, location_id, lot_id=None, package_id=None, owner_id=None, strict=False, allow_negative=False):
		""" Return the available quantity, i.e. the sum of `quantity` minus the sum of
		`reserved_quantity`, for the set of quants sharing the combination of `product_id,
		location_id` if `strict` is set to False or sharing the *exact same characteristics*
		otherwise.
		This method is called in the following usecases:
			- when a stock move checks its availability
			- when a stock move actually assign
			- when editing a move line, to check if the new value is forced or not
			- when validating a move line with some forced values and have to potentially unlink an
			  equivalent move line in another picking
		In the two first usecases, `strict` should be set to `False`, as we don't know what exact
		quants we'll reserve, and the characteristics are meaningless in this context.
		In the last ones, `strict` should be set to `True`, as we work on a specific set of
		characteristics.

		:return: available quantity as a float
		"""
		self = self.sudo()
		quants = self._gather(product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict)
		rounding = product_id.uom_id.rounding
		if product_id.tracking == 'none':
			available_quantity1 = sum(quants.mapped('quantity1')) - sum(quants.mapped('reserved_quantity1'))
			if allow_negative:
				return available_quantity1
			else:
				return available_quantity1 if float_compare(available_quantity1, 0.0, precision_rounding=rounding) >= 0.0 else 0.0
		else:
			availaible_quantities = {lot_id: 0.0 for lot_id in list(set(quants.mapped('lot_id'))) + ['untracked']}
			for quant in quants:
				if not quant.lot_id:
					availaible_quantities['untracked'] += quant.quantity1 - quant.reserved_quantity1
				else:
					availaible_quantities[quant.lot_id] += quant.quantity1 - quant.reserved_quantity1
			if allow_negative:
				return sum(availaible_quantities.values())
			else:
				return sum([available_quantity1 for available_quantity1 in availaible_quantities.values() if float_compare(available_quantity1, 0, precision_rounding=rounding) > 0])

	@api.model
	def _get_available_quantity2(self, product_id, location_id, lot_id=None, package_id=None, owner_id=None, strict=False, allow_negative=False):
		""" Return the available quantity, i.e. the sum of `quantity` minus the sum of
		`reserved_quantity`, for the set of quants sharing the combination of `product_id,
		location_id` if `strict` is set to False or sharing the *exact same characteristics*
		otherwise.
		This method is called in the following usecases:
			- when a stock move checks its availability
			- when a stock move actually assign
			- when editing a move line, to check if the new value is forced or not
			- when validating a move line with some forced values and have to potentially unlink an
			  equivalent move line in another picking
		In the two first usecases, `strict` should be set to `False`, as we don't know what exact
		quants we'll reserve, and the characteristics are meaningless in this context.
		In the last ones, `strict` should be set to `True`, as we work on a specific set of
		characteristics.

		:return: available quantity as a float
		"""
		self = self.sudo()
		quants = self._gather(product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict)
		rounding = product_id.uom_id.rounding
		if product_id.tracking == 'none':
			available_quantity2 = sum(quants.mapped('quantity2')) - sum(quants.mapped('reserved_quantity2'))
			if allow_negative:
				return available_quantity2
			else:
				return available_quantity2 if float_compare(available_quantity2, 0.0, precision_rounding=rounding) >= 0.0 else 0.0
		else:
			availaible_quantities = {lot_id: 0.0 for lot_id in list(set(quants.mapped('lot_id'))) + ['untracked']}
			for quant in quants:
				if not quant.lot_id:
					availaible_quantities['untracked'] += quant.quantity2 - quant.reserved_quantity2
				else:
					availaible_quantities[quant.lot_id] += quant.quantity2 - quant.reserved_quantity2
			if allow_negative:
				return sum(availaible_quantities.values())
			else:
				return sum([available_quantity2 for available_quantity2 in availaible_quantities.values() if float_compare(available_quantity2, 0, precision_rounding=rounding) > 0])


	@api.onchange('location_id', 'product_id', 'lot_id', 'package_id', 'owner_id')
	def _onchange_location_or_product_id(self):
		vals = {}

		# Once the new line is complete, fetch the new theoretical values.
		if self.product_id and self.location_id:
			# Sanity check if a lot has been set.
			if self.lot_id:
				if self.tracking == 'none' or self.product_id != self.lot_id.product_id:
					vals['lot_id'] = None

			quants = self._gather(self.product_id, self.location_id, lot_id=self.lot_id, package_id=self.package_id, owner_id=self.owner_id, strict=True)
			reserved_quantity = sum(quants.mapped('reserved_quantity'))
			reserved_quantity1 = sum(quants.mapped('reserved_quantity1'))
			reserved_quantity2 = sum(quants.mapped('reserved_quantity2'))
			quantity = sum(quants.mapped('quantity'))
			quantity1 = sum(quants.mapped('quantity1'))
			quantity2 = sum(quants.mapped('quantity2'))

			vals['reserved_quantity'] = reserved_quantity
			vals['reserved_quantity1'] = reserved_quantity1
			vals['reserved_quantity2'] = reserved_quantity2
			# Update `quantity` only if the user manually updated `inventory_quantity`.
			if float_compare(self.quantity, self.inventory_quantity, precision_rounding=self.product_uom_id.rounding) == 0:
				vals['quantity'] = quantity
				vals['quantity1'] = quantity1
				vals['quantity2'] = quantity2
			# Special case: directly set the quantity to one for serial numbers,
			# it'll trigger `inventory_quantity` compute.
			if self.lot_id and self.tracking == 'serial':
				vals['quantity'] = 1
				vals['quantity1'] = 1
				vals['quantity2'] = 1

		if vals:
			self.update(vals)

	@api.model
	def _update_available_quantity(self, product_id, location_id, quantity, quantity1, quantity2, lot_id=None, package_id=None, owner_id=None, in_date=None):
		""" Increase or decrease `reserved_quantity` of a set of quants for a given set of
		product_id/location_id/lot_id/package_id/owner_id.

		:param product_id:
		:param location_id:
		:param quantity:
		:param lot_id:
		:param package_id:
		:param owner_id:
		:param datetime in_date: Should only be passed when calls to this method are done in
								 order to move a quant. When creating a tracked quant, the
								 current datetime will be used.
		:return: tuple (available_quantity, in_date as a datetime)
		"""
		self = self.sudo()
		quants = self._gather(product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=True)

		incoming_dates = [d for d in quants.mapped('in_date') if d]
		incoming_dates = [fields.Datetime.from_string(incoming_date) for incoming_date in incoming_dates]
		if in_date:
			incoming_dates += [in_date]
		# If multiple incoming dates are available for a given lot_id/package_id/owner_id, we
		# consider only the oldest one as being relevant.
		if incoming_dates:
			in_date = fields.Datetime.to_string(min(incoming_dates))
		else:
			in_date = fields.Datetime.now()

		for quant in quants:
			try:
				with self._cr.savepoint(flush=False):  # Avoid flush compute store of package
					self._cr.execute("SELECT 1 FROM stock_quant WHERE id = %s FOR UPDATE NOWAIT", [quant.id], log_exceptions=False)
					quant.write({
						'quantity': quant.quantity + quantity,
						'quantity1': quant.quantity1 + quantity1,
						'quantity2': quant.quantity2 + quantity2,
						'in_date': in_date,
					})
					break
			except OperationalError as e:
				if e.pgcode == '55P03':  # could not obtain the lock
					continue
				else:
					raise
		else:
			self.create({
				'product_id': product_id.id,
				'location_id': location_id.id,
				'quantity': quantity,
				'quantity1': quantity1,
				'quantity2': quantity2,
				'lot_id': lot_id and lot_id.id,
				'package_id': package_id and package_id.id,
				'owner_id': owner_id and owner_id.id,
				'in_date': in_date,
			})
		return self._get_available_quantity(product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=False, allow_negative=True), fields.Datetime.from_string(in_date)

	@api.model
	def _update_reserved_quantity(self, product_id, location_id, quantity, quantity1, quantity2, lot_id=None, package_id=None, owner_id=None, strict=False):
		""" Increase the reserved quantity, i.e. increase `reserved_quantity` for the set of quants
		sharing the combination of `product_id, location_id` if `strict` is set to False or sharing
		the *exact same characteristics* otherwise. Typically, this method is called when reserving
		a move or updating a reserved move line. When reserving a chained move, the strict flag
		should be enabled (to reserve exactly what was brought). When the move is MTS,it could take
		anything from the stock, so we disable the flag. When editing a move line, we naturally
		enable the flag, to reflect the reservation according to the edition.

		:return: a list of tuples (quant, quantity_reserved) showing on which quant the reservation
			was done and how much the system was able to reserve on it
		"""
		self = self.sudo()
		rounding = product_id.uom_id.rounding
		quants = self._gather(product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict)
		reserved_quants = []

		if float_compare(quantity, 0, precision_rounding=rounding) > 0:
			# if we want to reserve
			available_quantity = self._get_available_quantity(product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict)
			available_quantity1 = self._get_available_quantity1(product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict)
			available_quantity2 = self._get_available_quantity2(product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict)
			
			if float_compare(quantity, available_quantity, precision_rounding=rounding) > 0:
				raise UserError(_('It is not possible to reserve more products of %s than you have in stock.', product_id.display_name))
		elif float_compare(quantity, 0, precision_rounding=rounding) < 0:
			# if we want to unreserve
			available_quantity = sum(quants.mapped('reserved_quantity'))
			available_quantity1 = sum(quants.mapped('reserved_quantity1'))
			available_quantity2 = sum(quants.mapped('reserved_quantity2'))
			if float_compare(abs(quantity), available_quantity, precision_rounding=rounding) > 0:
				raise UserError(_('It is not possible to unreserve more products of %s than you have in stock.', product_id.display_name))
		else:
			return reserved_quants

		for quant in quants:
			if float_compare(quantity, 0, precision_rounding=rounding) > 0:
				max_quantity_on_quant = quant.quantity - quant.reserved_quantity
				max_quantity_on_quant1 = quant.quantity1 - quant.reserved_quantity1
				max_quantity_on_quant2 = quant.quantity2 - quant.reserved_quantity2
				if float_compare(max_quantity_on_quant, 0, precision_rounding=rounding) <= 0:
					continue
				max_quantity_on_quant = min(max_quantity_on_quant, quantity)
				max_quantity_on_quant1 = min(max_quantity_on_quant1, quantity1)
				max_quantity_on_quant2 = min(max_quantity_on_quant2, quantity2)
				quant.reserved_quantity += max_quantity_on_quant
				quant.reserved_quantity1 += max_quantity_on_quant1
				quant.reserved_quantity2 += max_quantity_on_quant2
				reserved_quants.append((quant, max_quantity_on_quant))
				reserved_quants.append((quant, max_quantity_on_quant1))
				reserved_quants.append((quant, max_quantity_on_quant2))
				quantity -= max_quantity_on_quant
				quantity1 -= max_quantity_on_quant1
				quantity2 -= max_quantity_on_quant2
				available_quantity -= max_quantity_on_quant
				available_quantity1 -= max_quantity_on_quant1
				available_quantity2 -= max_quantity_on_quant2
			else:
				max_quantity_on_quant = min(quant.reserved_quantity, abs(quantity))
				max_quantity_on_quant1 = min(quant.reserved_quantity1, abs(quantity1))
				max_quantity_on_quant2 = min(quant.reserved_quantity2, abs(quantity2))
				quant.reserved_quantity -= max_quantity_on_quant
				quant.reserved_quantity1 -= max_quantity_on_quant1
				quant.reserved_quantity2 -= max_quantity_on_quant2
				reserved_quants.append((quant, -max_quantity_on_quant))
				reserved_quants.append((quant, -max_quantity_on_quant1))
				reserved_quants.append((quant, -max_quantity_on_quant2))
				quantity += max_quantity_on_quant
				quantity1 += max_quantity_on_quant1
				quantity2 += max_quantity_on_quant2
				available_quantity += max_quantity_on_quant
				available_quantity1 += max_quantity_on_quant1
				available_quantity2 += max_quantity_on_quant2

			if float_is_zero(quantity, precision_rounding=rounding) or float_is_zero(available_quantity, precision_rounding=rounding):
				break
		return reserved_quants

	@api.model
	def _merge_quants(self):
		""" In a situation where one transaction is updating a quant via
		`_update_available_quantity` and another concurrent one calls this function with the same
		argument, we’ll create a new quant in order for these transactions to not rollback. This
		method will find and deduplicate these quants.
		"""
		query = """WITH
						dupes AS (
							SELECT min(id) as to_update_quant_id,
								(array_agg(id ORDER BY id))[2:array_length(array_agg(id), 1)] as to_delete_quant_ids,
								SUM(reserved_quantity) as reserved_quantity,
								SUM(reserved_quantity1) as reserved_quantity1,
								SUM(reserved_quantity2) as reserved_quantity2,
								SUM(quantity) as quantity,
								SUM(quantity1) as quantity1,
								SUM(quantity2) as quantity2
							FROM stock_quant
							GROUP BY product_id, company_id, location_id, lot_id, package_id, owner_id, in_date
							HAVING count(id) > 1
						),
						_up AS (
							UPDATE stock_quant q
								SET quantity = d.quantity,
									quantity1 = d.quantity1,
									quantity2 = d.quantity2,
									reserved_quantity = d.reserved_quantity,
									reserved_quantity1 = d.reserved_quantity1,
									reserved_quantity2 = d.reserved_quantity2
							FROM dupes d
							WHERE d.to_update_quant_id = q.id
						)
				   DELETE FROM stock_quant WHERE id in (SELECT unnest(to_delete_quant_ids) from dupes)
		"""
		try:
			with self.env.cr.savepoint():
				self.env.cr.execute(query)
		except Error as e:
			_logger.info('an error occured while merging quants: %s', e.pgerror)

	@api.model
	def _get_inventory_fields_create(self):
		""" Returns a list of fields user can edit when he want to create a quant in `inventory_mode`.
		"""
		return ['product_id', 'location_id', 'lot_id', 'package_id', 'owner_id', 'inventory_quantity', 'inventory_quantity1', 'inventory_quantity2']

	@api.model
	def _get_inventory_fields_write(self):
		""" Returns a list of fields user can edit when he want to edit a quant in `inventory_mode`.
		"""
		return ['inventory_quantity', 'inventory_quantity1', 'inventory_quantity2']

	def _get_inventory_move_values(self, qty, qty1, qty2, location_id, location_dest_id, out=False):
		""" Called when user manually set a new quantity (via `inventory_quantity`)
		just before creating the corresponding stock move.

		:param location_id: `stock.location`
		:param location_dest_id: `stock.location`
		:param out: boolean to set on True when the move go to inventory adjustment location.
		:return: dict with all values needed to create a new `stock.move` with its move line.
		"""
		self.ensure_one()
		return {
			'name': _('Product Quantity Updated'),
			'product_id': self.product_id.id,
			'product_uom': self.product_uom_id.id,
			'product_uom_qty': qty,
			'product_uom1': self.product_uom_id1.id,
			'product_uom_qty1': qty1,
			'product_uom2': self.product_uom_id2.id,
			'product_uom_qty2': qty2,
			'company_id': self.company_id.id or self.env.company.id,
			'state': 'confirmed',
			'location_id': location_id.id,
			'location_dest_id': location_dest_id.id,
			'move_line_ids': [(0, 0, {
				'product_id': self.product_id.id,
				'product_uom_id': self.product_uom_id.id,
				'qty_done': qty,
				'product_uom_id1': self.product_uom_id1.id,
				'qty_done1': qty1,
				'product_uom_id2': self.product_uom_id2.id,
				'qty_done2': qty2,
				'location_id': location_id.id,
				'location_dest_id': location_dest_id.id,
				'company_id': self.company_id.id or self.env.company.id,
				'lot_id': self.lot_id.id,
				'package_id': out and self.package_id.id or False,
				'result_package_id': (not out) and self.package_id.id or False,
				'owner_id': self.owner_id.id,
			})]
		}
