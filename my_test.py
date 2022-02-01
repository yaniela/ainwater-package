import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pandas.core.indexes.datetimes import date_range
import graphics_functions as fn
import psycopg2
import seaborn as sns

#sns.set_theme(style="white", context="talk")

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
df['week']=df['date_time'].dt.week
df['year']=df['date_time'].dt.year
df['month']=df['date_time'].dt.month
#print(df['date_time'] )

df= df.set_index('date_time')
#df = df.asfreq('3min')
df = df[~df.index.duplicated()] # elimino indices duplicados. 
df = df.sort_index()

print(df.columns)
print(df[['year','do_level']])

#################### Distribution graphics ###############################
fn.plot_sns_distribution_hue(df, 'cycle_moment','cycle_moment' , 'do_level', 'Oxigeno disuelto por momento del ciclo')
fn.simple_sns_kdeplot(df, 'do_level')
fn.two_sns_histplot(df,'h2o_level',15,3)
fn.simple_histplot(df,'do_level', 5, 3)


#################### lineplots  ###############################

fn.plot_two_series(df[['blower_hz_1', 'blower_hz_2']], 5, 3)
fn.multiple_lineplot_secundary_y_axis(df, 'h2o_level',['do_temp', 'do_level'],10,10)
fn.zoom_lineplot(('2020-10-05 06:33:37','2020-10-06 06:33:37'),df, 'h2o_level')
fn.simple_sns_lineplot_marker(df,'year','do_level',1.5,'Oxigeno disuelto por año')
fn.multiple_sns_lineplot_secundary_y_axis(df,'date_time', 'h2o_level',['blower_hz_1', 'blower_hz_2','do_temp', 'mlss_level'],20,20)
fn.multiple_sns_lineplot(df,'date_time', ['blower_hz_1', 'blower_hz_2','do_temp', 'mlss_level'],20,20)
fn.simple_sns_lineplot_two_y_axis(df,'date_time','do_temp','mlss_level',20,20)

######################### scatterplots ###################################
fn.sns_joinplot_hex(df,'h2o_level','do_level')
fn.multiple_sns_scatterplot_one_vs_all(df,['blower_hz_1', 'blower_hz_2','do_temp', 'h2o_level', 'mlss_level'],'do_level',20,20)
fn.sns_pairplot(df[['do_level','h2o_level',"cycle_moment"]],"cycle_moment")





