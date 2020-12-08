# -*- coding: utf-8 -*-
# from odoo import http


# class Sm(http.Controller):
#     @http.route('/sm/sm/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/sm/sm/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('sm.listing', {
#             'root': '/sm/sm',
#             'objects': http.request.env['sm.sm'].search([]),
#         })

#     @http.route('/sm/sm/objects/<model("sm.sm"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('sm.object', {
#             'object': obj
#         })
