import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pandas.core.indexes.datetimes import date_range
import graphics_functions as fn
import psycopg2
import seaborn as sns

#query= '''select * 
#from curacavi.basin_b1
# '''

# Creating connections
#conn_string = "host=34.73.91.152 port=5432 dbname=ainwater user=postgres password=ainwater_kYaUM7xjPEEdza6X"
#conn=psycopg2.connect(conn_string)

#df = pd.read_sql(query, con=conn)
#df.to_csv('data.csv', header=True, index=False)

df_temp = pd.read_csv('data.csv')
df=df_temp[:5000]
df['date_time'] = df['date'].astype(str) +' ' +df['time'].astype(str)

fn.simple_kdeplot(df, 'do_level')


fn.plot_box_and_dot(df, 'cycle_moment', 'do_level', hue_var = None)