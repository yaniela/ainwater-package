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
df['date_time']=df['date_time'].astype('datetime64[m]')

print(df['date_time'] )

df= df.set_index('date_time')
#df = df.asfreq('3min')
df = df[~df.index.duplicated()] # elimino indices duplicados. 
df = df.sort_index()


fn.zoom_plot(('2020-10-17 06:33:37','2020-10-18 06:33:37'),df, 'h2o_level')

fn.two_histplot(df,'h2o_level',15,3)
