# labels not being generated

# BUG: Do not allow more than one point to be selected (when overlaid)
# BUG: error bars remain when there is no point
# TODO make display table responsive
# TODO throttle slider callback time (callback_policy)


import numpy as np

from bokeh.plotting import figure
from bokeh.layouts import widgetbox, gridplot, layout
from bokeh.models import Slider, RangeSlider, Div, Select
from bokeh.models import Circle, ColorBar, HoverTool
from bokeh.models import ColumnDataSource
from bokeh.transform import linear_cmap
from bokeh.palettes import Spectral10 as palette

TOOLS = "pan,wheel_zoom,tap,reset"

GASES = ['carbon dioxide', 'nitrogen', 'methane',
         'ethane', 'ethene', 'acetylene', 'propane', 'propene',
         'butane', 'isobutane']


def gen_cmap(z):
    """Create a linear cmap with a particular name."""
    return linear_cmap(
        field_name='n_{0}'.format(z), palette=palette,
        low_color='grey', high_color='red',
        low=3, high=90)


def graph_link(rends):
    """Add a linked selection and hover effect."""
    sel = Circle(fill_alpha=1, fill_color="black", line_color='black')
    for rend in rends:
        rend.selection_glyph = sel
        rend.hover_glyph = sel


class Dashboard():

    def __init__(self, doc, data, **templates):

        # Save templates
        self.t_tooltip = templates["t_tooltip"]
        self.t_matdet = templates["t_matdet"]
        self.t_isodet = templates["t_isodet"]

        # Save references for thread access
        self._data = data
        self._doc = doc

        # Gas definitions
        self.g1 = GASES[0]
        self.g2 = GASES[1]

        # Pressure definitions
        self.lp = 0
        self.p1 = 0
        self.p2 = 9

        # Bokeh specific data generation
        self.data = ColumnDataSource(data=self.gen_data())
        self.errors = ColumnDataSource(data=self.gen_error())

        # Data callback
        self.data.selected.on_change('indices', self.selection_callback)

        # Gas selections
        g1_sel = Select(title="Gas 1", options=GASES, value=self.g1)
        g2_sel = Select(title="Gas 2", options=GASES, value=self.g2)

        def g1_sel_callback(attr, old, new):
            self.g1 = new
            self.new_gas_callback()

        def g2_sel_callback(attr, old, new):
            self.g2 = new
            self.new_gas_callback()

        g1_sel.on_change("value", g1_sel_callback)
        g2_sel.on_change("value", g2_sel_callback)

        # Top graphs
        self.p_henry, rend1 = self.top_graph(
            "K", "Initial Henry's constant",
            x_range=(1e-3, 1e7), y_range=(1e-3, 1e7),
            y_axis_type="log", x_axis_type="log")
        self.p_loading, rend2 = self.top_graph(
            "L", "Uptake at selected pressure")
        self.p_wc, rend3 = self.top_graph(
            "W", "Working capacity in selected range")
        graph_link([rend1, rend2, rend3])
        self.top_graph_labels()

        # Pressure slider
        p_slider = Slider(title="Pressure", value=0.5,
                          start=0.5, end=20, step=0.5)
        p_slider.on_change('value', self.pressure_callback)

        # Working capacity slider
        wc_slider = RangeSlider(title="Working capacity", value=(0.5, 5),
                                start=0.5, end=20, step=0.5)
        wc_slider.on_change('value', self.wc_callback)

        # Material details
        self.details = Div(text=self.gen_details())

        # Isotherm details
        self.details_iso = Div(text="Bottom text", height=400)

        self.dash_layout = layout([
            [g1_sel, g2_sel],
            [gridplot([
                [self.details, self.p_henry],
                [self.p_loading, self.p_wc]],
                sizing_mode='scale_width')],
            [widgetbox(children=[p_slider, wc_slider])],
            # [gridplot([[self.p_g0iso, self.p_g1iso]])],
            [self.details_iso],
        ], sizing_mode='scale_width')

    def top_graph(self, ind, title, **kwargs):

        # Generate figure dict
        plot_side_size = 400
        fig_dict = dict(tools=TOOLS,
                        active_scroll="wheel_zoom",
                        plot_width=plot_side_size,
                        plot_height=plot_side_size,
                        title=title)
        fig_dict.update(kwargs)

        # Create a colour mapper
        mapper = gen_cmap(ind)

        # create a new plot and add a renderer
        graph = figure(**fig_dict)

        graph.add_tools(HoverTool(
            names=["data_{0}".format(ind)],
            tooltips=self.t_tooltip.render(p=ind))
        )

        # Data
        rend = graph.circle(
            "x_{0}".format(ind), "y_{0}".format(ind),
            source=self.data, size=10,
            line_color=mapper, color=mapper,
            name="data_{0}".format(ind)
        )

        # Errors
        graph.segment('{0}_x0'.format(ind), '{0}_y0'.format(ind),
                      '{0}_x1'.format(ind), '{0}_y1'.format(ind),
                      source=self.errors, color="black", line_width=2)

        # Colorbar
        graph.add_layout(ColorBar(
            color_mapper=mapper['transform'],
            width=8, location=(0, 0)),
            'right'
        )

        return graph, rend

    def top_graph_labels(self):
        self.p_loading.xaxis.axis_label = '{0} (mmol/g)'.format(self.g1)
        self.p_loading.yaxis.axis_label = '{0} (mmol/g)'.format(self.g2)
        self.p_henry.xaxis.axis_label = '{0} (dimensionless)'.format(
            self.g1)
        self.p_henry.yaxis.axis_label = '{0} (dimensionless)'.format(
            self.g2)
        self.p_wc.xaxis.axis_label = '{0} (mmol/g)'.format(self.g1)
        self.p_wc.yaxis.axis_label = '{0} (mmol/g)'.format(self.g2)

    # #########################################################################
    # Selection update

    def new_gas_callback(self):

        # # Reset any selected materials
        if self.data.selected.indices:
            self.data.selected.update(indices=[])

        # # Gen data
        self.data.data = self.gen_data()

        # # Update labels
        self.top_graph_labels()

        # # Update bottom
        # self.purge_isos()

    # #########################################################################
    # Set up pressure slider and callback

    def pressure_callback(self, attr, old, new):
        self.lp = int(new * 2) - 1
        self.data.patch(self.patch_data_l())
        sel = self.data.selected.indices
        if sel:
            self.errors.patch(self.patch_error_l(sel[0]))
            self.details.text = self.gen_details(sel[0])

    # #########################################################################
    # Set up working capacity slider and callback

    def wc_callback(self, attr, old, new):
        self.p1, self.p2 = int(new[0] * 2) - 1, int(new[1] * 2) - 1
        self.data.patch(self.patch_data_w())
        sel = self.data.selected.indices
        if sel:
            self.errors.data = self.gen_error(sel[0])
            self.details.text = self.gen_details(sel[0])

    # #########################################################################
    # Data generator

    def gen_data(self):

        def get_loading(x):
            if not x:
                return np.nan
            elif len(x) <= self.lp:
                return np.nan
            return x[self.lp]

        def get_wc(x):
            if not x:
                return np.nan
            elif len(x) <= self.p1 or len(x) <= self.p2:
                return np.nan
            return x[self.p2] - x[self.p1]

        def get_nwc(x):
            if not x:
                return np.nan
            elif len(x) <= self.p1 or len(x) <= self.p2:
                return np.nan
            return x[self.p1] + x[self.p2]

        return {
            'labels': self._data.index,

            # henry data
            'x_K': self._data[self.g1, 'mKh'].values,
            'y_K': self._data[self.g2, 'mKh'].values,
            'n_xK': self._data[self.g1, 'lKh'].values,
            'n_yK': self._data[self.g2, 'lKh'].values,
            'n_K': self._data[self.g1, 'lKh'].values + self._data[self.g2, 'lKh'].values,

            # loading data
            'x_L': self._data[self.g1, 'mL'].apply(get_loading).values,
            'y_L': self._data[self.g2, 'mL'].apply(get_loading).values,
            'n_xL': self._data[self.g1, 'lL'].apply(get_loading).values,
            'n_yL': self._data[self.g2, 'lL'].apply(get_loading).values,
            'n_L': self._data[self.g1, 'lL'].apply(get_loading).values +
            self._data[self.g2, 'lL'].apply(get_loading).values,

            # Working capacity data
            'x_W': self._data[self.g1, 'mL'].apply(get_wc).values,
            'y_W': self._data[self.g2, 'mL'].apply(get_wc).values,
            'n_xW': self._data[self.g1, 'lL'].apply(get_nwc).values,
            'n_yW': self._data[self.g2, 'lL'].apply(get_nwc).values,
            'n_W': self._data[self.g1, 'lL'].apply(get_nwc).values +\
            self._data[self.g2, 'lL'].apply(get_nwc).values,
        }

    def patch_data_l(self):

        def get_loading(x):
            if not x:
                return np.nan
            elif len(x) <= self.lp:
                return np.nan
            return x[self.lp]

        return {
            'x_L': [(slice(None), self._data[self.g1, 'mL'].apply(get_loading).values)],
            'y_L': [(slice(None), self._data[self.g2, 'mL'].apply(get_loading).values)],
            'n_xL': [(slice(None), self._data[self.g1, 'lL'].apply(get_loading).values)],
            'n_yL': [(slice(None), self._data[self.g2, 'lL'].apply(get_loading).values)],
            'n_L': [(slice(None), self._data[self.g1, 'lL'].apply(get_loading).values +
                     self._data[self.g2, 'lL'].apply(get_loading).values)]
        }

    def patch_data_w(self):

        def get_wc(x):
            if not x:
                return np.nan
            elif len(x) <= self.p1 or len(x) <= self.p2:
                return np.nan
            return x[self.p2] - x[self.p1]

        def get_nwc(x):
            if not x:
                return np.nan
            elif len(x) <= self.p1 or len(x) <= self.p2:
                return np.nan
            return x[self.p1] + x[self.p2]

        return {
            'x_W': [(slice(None), self._data[self.g1, 'mL'].apply(get_wc).values)],
            'y_W': [(slice(None), self._data[self.g2, 'mL'].apply(get_wc).values)],
            'n_xW': [(slice(None), self._data[self.g1, 'lL'].apply(get_nwc).values)],
            'n_yW': [(slice(None), self._data[self.g2, 'lL'].apply(get_nwc).values)],
            'n_W': [(slice(None), self._data[self.g1, 'lL'].apply(get_nwc).values +
                     self._data[self.g2, 'lL'].apply(get_nwc).values)]
        }

    # #########################################################################
    # Error generator

    def gen_error(self, index=None):

        if index is None:
            return {
                'K_x0': [], 'K_y0': [], 'K_x1': [], 'K_y1': [],
                'L_x0': [], 'L_y0': [], 'L_x1': [], 'L_y1': [],
                'W_x0': [], 'W_y0': [], 'W_x1': [], 'W_y1': [],
            }

        else:
            def get_err(x, y):
                if not x:
                    return np.nan
                elif len(x) <= y:
                    return np.nan
                return x[y]

            mat = self.data.data['labels'][index]
            K_x = self.data.data['x_K'][index]
            K_y = self.data.data['y_K'][index]
            L_x = self.data.data['x_L'][index]
            L_y = self.data.data['y_L'][index]
            W_x = self.data.data['x_W'][index]
            W_y = self.data.data['y_W'][index]
            K_ex = self._data.loc[mat, (self.g1, 'eKh')]
            K_ey = self._data.loc[mat, (self.g2, 'eKh')]
            if np.isnan(L_x) or np.isnan(L_y):
                L_x, L_y = 0, 0
                L_ex, L_ey = 0, 0
            else:
                L_ex = get_err(self._data.loc[mat, (self.g1, 'eL')], self.lp)
                L_ey = get_err(self._data.loc[mat, (self.g2, 'eL')], self.lp)
            if np.isnan(W_x) or np.isnan(W_y):
                W_x, W_y = 0, 0
                W_ex, W_ey = 0, 0
            else:
                W_ex = get_err(self._data.loc[mat, (self.g1, 'eL')], self.p1) + \
                    get_err(self._data.loc[mat, (self.g1, 'eL')], self.p2)
                W_ey = get_err(self._data.loc[mat, (self.g2, 'eL')], self.p1) + \
                    get_err(self._data.loc[mat, (self.g2, 'eL')], self.p2)

            return {
                'labels': [mat, mat],

                # henry data
                'K_x0': [K_x - K_ex, K_x],
                'K_y0': [K_y, K_y - K_ey],
                'K_x1': [K_x + K_ex, K_x],
                'K_y1': [K_y, K_y + K_ey],
                # loading data
                'L_x0': [L_x - L_ex, L_x],
                'L_y0': [L_y, L_y - L_ey],
                'L_x1': [L_x + L_ex, L_x],
                'L_y1': [L_y, L_y + L_ey],
                # working capacity data
                'W_x0': [W_x - W_ex, W_x],
                'W_y0': [W_y, W_y - W_ey],
                'W_x1': [W_x + W_ex, W_x],
                'W_y1': [W_y, W_y + W_ey],
            }

    def patch_error_l(self, index=None):
        if index is None:
            return {
                # loading data
                'L_x0': [(slice(None), [])],
                'L_y0': [(slice(None), [])],
                'L_x1': [(slice(None), [])],
                'L_y1': [(slice(None), [])],
            }
        else:
            def get_err(x, y):
                if not x:
                    return np.nan
                elif len(x) <= y:
                    return np.nan
                return x[y]
            mat = self.data.data['labels'][index]
            K_ex = self._data.loc[mat, (self.g1, 'eKh')]
            K_ey = self._data.loc[mat, (self.g2, 'eKh')]
            if np.isnan(L_x) or np.isnan(L_y):
                L_x, L_y = 0, 0
                L_ex, L_ey = 0, 0
            else:
                L_ex = get_err(self._data.loc[mat, (self.g1, 'eL')], self.lp)
                L_ey = get_err(self._data.loc[mat, (self.g2, 'eL')], self.lp)
            return {
                # loading data
                'L_x0': [(slice(None), [L_x - L_ex, L_x])],
                'L_y0': [(slice(None), [L_y, L_y - L_ey])],
                'L_x1': [(slice(None), [L_x + L_ex, L_x])],
                'L_y1': [(slice(None), [L_y, L_y + L_ey])],
            }

    def patch_error_wc(self, index=None):
        if index is None:
            return {
                # loading data
                'W_x0': [(slice(None), [])],
                'W_y0': [(slice(None), [])],
                'W_x1': [(slice(None), [])],
                'W_y1': [(slice(None), [])],
            }
        else:
            def get_err(x, y):
                if not x:
                    return np.nan
                elif len(x) <= y:
                    return np.nan
                return x[y]
            mat = self.data.data['labels'][index]
            W_x = self.data.data['x_W'][index]
            W_y = self.data.data['y_W'][index]
            if np.isnan(W_x) or np.isnan(W_y):
                W_x, W_y = 0, 0
                W_ex, W_ey = 0, 0
            else:
                W_ex = get_err(self._data.loc[mat, (self.g1, 'eL')], self.p1) + \
                    get_err(self._data.loc[mat, (self.g1, 'eL')], self.p2)
                W_ey = get_err(self._data.loc[mat, (self.g2, 'eL')], self.p1) + \
                    get_err(self._data.loc[mat, (self.g2, 'eL')], self.p2)
            return {
                # loading data
                'W_x0': [(slice(None), [W_x - W_ex, W_x])],
                'W_y0': [(slice(None), [W_y, W_y - W_ey])],
                'W_x1': [(slice(None), [W_x + W_ex, W_x])],
                'W_y1': [(slice(None), [W_y, W_y + W_ey])],
            }

    # #########################################################################
    # Text generator

    def gen_details(self, index=None):
        if index is None:
            return self.t_matdet.render()
        else:
            mat = self.data.data['labels'][index]
            data = {
                'material': mat,
                'gas1': self.g1,
                'gas2': self.g2,
                'gas1_niso': len(self._data.loc[mat, (self.g1, 'iso')]),
                'gas2_niso': len(self._data.loc[mat, (self.g2, 'iso')]),
                'gas1_load': self.data.data['x_L'][index],
                'gas2_load': self.data.data['y_L'][index],
                'gas1_eload': self.errors.data['L_x1'][0] - self.errors.data['L_x1'][1],
                'gas2_eload': self.errors.data['L_y1'][1] - self.errors.data['L_y1'][0],
                'gas1_hk': self.data.data['x_K'][index],
                'gas2_hk': self.data.data['y_K'][index],
                'gas1_ehk': self.errors.data['K_x1'][0] - self.errors.data['K_x1'][1],
                'gas2_ehk': self.errors.data['L_y1'][1] - self.errors.data['L_y1'][0],
            }
            return self.t_matdet.render(**data)

    # #########################################################################
    # Callback for selection

    def selection_callback(self, attr, old, new):

        # Check if the user has selected a point
        if len(new) == 1:

            # Display error points:
            self.errors.data = self.gen_error(new[0])

            # Generate material details
            self.details.text = self.gen_details(new[0])

        else:
            # Remove error points:
            self.errors.data = self.gen_error()

            # Remove material details
            self.details.text = self.gen_details()
