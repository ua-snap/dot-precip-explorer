import os, json, io, requests
import dash 
from dash.dependencies import Input, Output, State
import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objs as go
import pandas as pd
import numpy as np

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
# #  NSIDC-0051 Derived FUBU Data Explorer Tool                         # #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def get_data_return_df( sid ):
    ''' helper function for working with ACIS JSON'''
    sdate = '1979-01-02'
    edate = '2015-10-29'
    elems = 'pcpn'
    output_type = 'json'

    url = 'http://data.rcc-acis.org/StnData?sid={}&sdate={}&edate={}&elems={}&output={}'\
            .format(sid, sdate, edate, elems, output_type )

    # get the station data json
    response = requests.get(url)
    json_data = json.loads(response.text)
    df = pd.DataFrame(json_data['data'], columns=['time','pcpn'])
    df.index = pd.DatetimeIndex(df['time'].values)
    return df['pcpn']

def load_data():
    print('loading remote data files...')
    # load the data
    # wrf
    url = 'https://www.snap.uaf.edu/webshared/Michael/data/pcpt_hourly_communities_v2_ERA-Interim_historical.csv'
    s = requests.get(url).content
    wrf = pd.read_csv(io.StringIO(s.decode('utf-8')), index_col=0, parse_dates=True)
    start, end = wrf.index.min().strftime('%Y-%d-%m'), wrf.index.max().strftime('%Y-%d-%m')
    # harvest acis
    sids = {'Barrow':'USW00027502', 'Nome':'USW00026617', 'Bethel':'USW00026615', \
    'Anchorage':'USW00026451', 'Juneau':'USW00025309', 'Fairbanks':'USW00026411',} #'Homer':'USC00503672
    df = pd.DataFrame({ name:get_data_return_df( sid ) for name,sid in sids.items() })
    df = df.replace('M', np.nan).replace('T', '.001').astype(np.float32)
    acis = df*25.4 # make mm
    print('data loaded.')
    return wrf, acis

# load data
wrf, acis = load_data()
wrf = wrf.resample('1D').sum() # make daily sums from hourlies

# get the range of years
years = acis.index.map(lambda x: x.year).unique()

app = dash.Dash(__name__)
server = app.server
server.secret_key = os.environ['SECRET-SNAP-KEY']
# server.secret_key = 'secret_key'
app.config.supress_callback_exceptions = True
app.css.append_css({'external_url': 'https://codepen.io/chriddyp/pen/bWLwgP.css'})
app.title = 'WRF-ACIS-Precip-Compare'

# PAGE LAYOUT
app.layout = html.Div([
                html.Div([
                    html.H3('Compare Precip From WRF ERA-Interim and ACIS at select locations', style={'font-weight':'bold'}),
                    ]),

                html.Div([ 
                    html.Div([
                        html.Div([ # group1
                            html.Div([
                                html.Label('Choose Community', style={'font-weight':'bold'})
                                ], className='three columns'),
                            html.Div([
                                dcc.Dropdown(
                                        id='community-dd',
                                        options=[{'label':i,'value':i} for i in wrf.columns],
                                        value='Fairbanks')
                                    ], className='four columns'),
                            ], className='row'),
                        html.Div([ # group2
                            html.Div([
                                html.Label('Choose Duration Length', style={'font-weight':'bold'})
                                ], className='three columns'),
                            html.Div([
                                dcc.Dropdown(
                                    id='duration-dd',
                                    options=[{'label':'{} days'.format(i),'value':i} for i in range(31)] + \
                                    [{'label':'Annual', 'value':366}],
                                    value=366 ),
                                ], className='four columns'),
                            ], className='row'),

                        ], className='nine columns'),

                    html.Div([
                        dcc.Markdown(id='corr-label')
                        ], className='three columns'),
                    ], className='row' ),


                html.Div([
                    html.Div([dcc.Graph( id='acis-wrf-graph' )]),
                    html.Div([
                        dcc.RangeSlider(
                            id='time-slider',
                            marks={i:str(i) for i in years},
                            min=min(years),
                            max=max(years),
                            value=[1979, 2015],
                            pushable=True)
                        ])
                    ], className='eleven columns'),
                ])


@app.callback(Output('thresh-value', 'children'),
            [Input('my-slider', 'value')])
def update_thresh_value( thresh ):
    return 'threshold: {}'.format(thresh)

@app.callback([Output('acis-wrf-graph', 'figure'),
            Output('corr-label','children')],
            [Input('time-slider', 'value'),
            Input('community-dd', 'value'),
            Input('duration-dd', 'value'),])
def update_graph( time_range, community, duration ):
    begin,end = time_range
    begin = str(begin)
    end = str(end)

    # pull data for the year we want to examine
    wrf_sub = wrf[community].copy(deep=True)
    acis_sub = acis[community].copy(deep=True)
    
    # duration and plot title-fu
    title = 'ERA-Interim / ACIS Daily Precip Total' # base title if None
    if duration is not None:
        title = 'ERA-Interim / ACIS Daily Precip Total: {}'.format(community)
        if duration > 0:
            if duration == 366:
                wrf_sub = wrf_sub.resample('Y'.format(duration)).max()
                acis_sub = acis_sub.resample('Y'.format(duration)).max()
                title = 'ERA-Interim / ACIS Daily Precip Total: {} - {} Max'.format(community, 'Annual') # fill in when complete with testing
            else:
                wrf_sub = wrf_sub.resample('{}D'.format(duration)).mean()
                acis_sub = acis_sub.resample('{}D'.format(duration)).mean()
                title = 'ERA-Interim / ACIS Daily Precip Total: {} - {} Day Mean'.format(community, duration) # fill in when complete with testing

    # get some correlation coefficients
    pearson = wrf_sub.corr( acis_sub, method='pearson' ).round(2)
    spearman = wrf_sub.corr( acis_sub, method='spearman' ).round(2)
    kendall = wrf_sub.corr( acis_sub, method='kendall' ).round(2)

    # slice to the year-range selected
    wrf_sub = wrf_sub.loc[begin:end]
    acis_sub = acis_sub.loc[begin:end]

    # build Graph object
    graph = {'data':[ 
                go.Bar(
                    x=wrf_sub.index,
                    y=wrf_sub,
                    name='wrf',
                    ),
                go.Bar(
                    x=acis_sub.index,
                    y=acis_sub,
                    name='acis',
                    ),
                ],
            'layout': { 
                    'title': title,
                    'xaxis': dict(title='time'),
                    'yaxis': dict(title='mm'),
                    }
            }
    # output correlation values
    corr_value = '''
        WRF/ACIS Series Correlation:
          pearson : {}
          spearman: {}
          kendall : {}
    '''.format(pearson,spearman,kendall)
    return graph, corr_value

if __name__ == '__main__':
    app.run_server( debug=False )
