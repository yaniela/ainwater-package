import pandas as pd
import numpy as np
import scipy.stats as st
import matplotlib.pyplot as plt
import seaborn as sns
##import datetime
import psycopg2
from sqlalchemy import create_engine
from datetime import datetime, time
import pickle
import gzip
import warnings
warnings.simplefilter("ignore")


def dataframe_resumen(df, groupby = False , var_sum = False, var_mean = False, var_date = False, var_delta= False, var_count = False, std=False, size = False):
    df_tmp = pd.DataFrame()

    if groupby != False:
        group = df.groupby(groupby)

    # 1. Suma de valores 
    if var_sum != False:
        for var in var_sum:
            df_tmp[var] = group[var].sum()
    
    # 2. Media de valores
    if var_mean != False:
        for var in var_mean:
            df_tmp[var] = group[var].mean()
            if std == True:
                df_tmp[f'{var}_std'] = group[var].std()

    # 3. delta
    if var_delta != False:
        for var in var_delta:
            df_tmp[f'{var}_min'] = group[var].min()
            df_tmp[f'{var}_max'] = group[var].max()
            df_tmp[f'delta_{var}'] = (df_tmp[f'{var}_max'] - df_tmp[f'{var}_min']).astype('timedelta64[m]')

    # 4. count
    if var_count != False:
        for var in var_count:
            df_tmp[f'count_{var}']= group[var].count()

    if size == True:
        df['size'] = group.size()

    #5. Max o Min
    if var_date != False:
        for var in var_date:
            df_tmp[var] = group[var].min()

    df_tmp = df_tmp.reset_index()

    return df_tmp


def df_etl1_duplicados(df):
    ### Se eliminan los registros que se encuentren duplicados por date_time
    df = df.drop_duplicates(['date_time'], keep = 'first')

    ### Se ordenan los registros por medicion y periodo ascendente 
    df = df.sort_values('date_time')

    return df

def df_etl2_errores_lectura(df, columns_var):  #columns_var = ['do_level', 'do_temp', 'h2o_level', 'mlss_level','n_level', 'blower_hz']
    ### Eliminar registros negativos 
    for colname in columns_var:
        df[colname] = df[colname].map(lambda x: np.nan if x<0 else x)
    return df

def df_etl3_tiempo(df):
    ### Agregar columnas relacionadas a tiempo
    df.set_index('date_time', inplace = True)
    df['date_time'] = df.index
    df['year'] = df['date_time'].dt.year
    df['month'] = df['date_time'].dt.month
    df['year-month'] = (df['year'].astype(str)+ '-' +df['month'].astype(str))
    df['week'] = df['date_time'].dt.week
    df['date'] = df['date_time'].dt.date
    df['time'] = df['date_time'].dt.time
    df['hour'] = df['date_time'].dt.hour
    df['day_name'] =  df['date_time'].dt.day_name().astype(str)
    df['dt_lec'] = (df.date_time - df.date_time.shift(1)).astype("timedelta64[s]").fillna(0)
    return df


def df_etl4_ciclos(df):
    ### Arreglo para identificar ciclos
    df['blower_on'] = [0 if i ==0 else 1 for i in df['blower_hz']] # 0 blower off
    
    # CREATING STATES VARIABLES
    df['flag_states'] = (df['blower_on']-df['blower_on'].shift(1,fill_value=0 )).replace({-1:1}) # 1 end or start  
    df['state_id'] = df['flag_states'].cumsum() # id para cambio de estado 
    grouped = df.groupby(['state_id'])
    df['state_min_time'] = grouped['date_time'].transform('min') # Fecha y hora de inicio de state_id
    df['state_max_time'] = grouped['date_time'].transform('max') # Fecha y hora de fin de state_id  
    df['dt_state_sec'] = (df['state_max_time'] - df['state_min_time']).astype("timedelta64[s]") # duracion state_id en segundos
    df['dt_state_minu'] = df['dt_state_sec']/60  #duracion state_id minutos
    df['state_off_and_sd'] = df['blower_on'].apply(lambda x: 1 if x==0 else 0) # 1 blower off 
    
    #  Finding settle and decant states
    flag_sd = ((df['state_off_and_sd']==1) & (df['dt_state_minu']>=55))   # conditions : blower is off AND state duration is >=55 min
    df['state_settle_decant'] = flag_sd.astype('int')   # results as 1 (is settle/decant) or 0 (is not settle/decant)
    
    # CREATING CYCLES VARIABLES 
    df['flag_cycle'] = (df['state_settle_decant'] - df['state_settle_decant'].shift(1, fill_value=0)).replace({1:0, -1:1}) # when cycle ends
    df['cycle_id'] = df['flag_cycle'].cumsum()
    grouped2 = df.groupby(['cycle_id'])
    df['cycle_qt_points'] = grouped2['cycle_id'].transform('count')
    df['cycle_min_time'] = grouped2['date_time'].transform('min')
    df['cycle_max_time'] = grouped2['date_time'].transform('max')
    df['dt_cycle_sec'] = (df['cycle_max_time'] - df['cycle_min_time']).astype("timedelta64[s]")
    df['dt_cycle_minu'] = df['dt_cycle_sec']/60
    df['cycle_point_id'] = grouped2['cycle_id'].rank(method='first')
    df['dt_cycle_from_start'] = (df['date_time'] - df['cycle_min_time']).astype("timedelta64[s]")
    
 #  Etiquetado settle decant
    settle_decant_min = df.groupby(['cycle_id', 'state_settle_decant'])['date_time'].min().reset_index().set_index('cycle_id')
    settle_decant_min = settle_decant_min[settle_decant_min.state_settle_decant == 1].drop(columns = 'state_settle_decant').rename(columns= {'date_time': 'inicio_settle_decant'})
    settle_decant_max = df.groupby(['cycle_id', 'state_settle_decant'])['date_time'].max().reset_index().set_index('cycle_id')
    settle_decant_max = settle_decant_max[settle_decant_max.state_settle_decant == 1].drop(columns = 'state_settle_decant').rename(columns= {'date_time': 'fin_settle_decant'})
    
    df = df.merge(settle_decant_min, on = 'cycle_id', how='left')
    df = df.merge(settle_decant_max, on = 'cycle_id', how='left')
    
    df.set_index('date_time', inplace = True)
    df['date_time'] = df.index
    
    return df

def df_etl5_aireacion(df, high = 4, low = 1.5):
    '''
    Etiquetado de nivel de oxigeno de acuerdo a la etapa del proceso y nivel de oxigeno:
    - settle/decant: cuando la medicion corresponde a estado de settle/decant
    - high_do_airon: cuando el soplador esta en operación y el nivel de oxigeno es superior a high
    - normal_do_airon: cuando el soplador esta en operacion y el nivel de oxigeno esta en el rango de operación en fase aerobica: [low-high]
    - low_do_airon: cuando el soplador esta en operacion y el nivel de oxigeno es bajo low
    - nan_do_airon: soplador en uso pero no se tiene información del nivel de oxigeno
    - air_off: soplador en off sin considerar estado settle decant
    '''
    df['flag_do_level'] = np.where(df.state_settle_decant == 1, 'settle/decant',
                                 np.where((df.blower_on == 1) & (df.do_level > high), 'high_do_airon',
                                          np.where((df.blower_on == 1) & (df.do_level < low), 'low_do_airon',
                                                   np.where((df.blower_on == 1) & (df.do_level <= high) & (df.do_level >= low), 'normal_do_airon', 
                                                            np.where((df.blower_on == 1) & (df.do_level.isna() == True), 'nan_do_airon', 'air_off')
                                                            )
                                                   )
                                          )
                                 )
    return df

def df_etl6_timeofday(df):
    '''
    Etiquetado de momento del dia:
    - Morning: Ciclo inicio entre 5-9
    - Noon: Ciclo inicio entre 9-15
    - Afternoon: Ciclo inicio entre 15-20 
    - Night: Ciclo inicio entre 20-24
    - Early Morning: Ciclo inicio ente 24-5
    '''
    df['date_cycle'] = df.cycle_min_time.dt.date
    df['hora_inicio_ciclo'] = df.cycle_min_time.dt.hour
    df['hora_fin_ciclo'] = df.cycle_max_time.dt.hour
    df['time_of_day'] = np.where((df.hora_inicio_ciclo >=9) & (df.hora_inicio_ciclo < 15), '3-Noon',
                               np.where((df.hora_inicio_ciclo >=5) & (df.hora_inicio_ciclo < 9), '2-Morning',
                                        np.where( (df.hora_inicio_ciclo >=15) & (df.hora_inicio_ciclo < 20), '4-Afternoon',
                                                 np.where((df.hora_inicio_ciclo >=20) & (df.hora_inicio_ciclo < 24), '5-Night', '1-Early Morning'

                                                          )
                                                 )
                                        )
                               )  
    return df


def df_etl7_hz_min(df, col_hz = 'blower_hz', range_hz = [15,40]):
    """"""
    df['blower_hz_int'] = df[col_hz].map(lambda x: 0 if np.isnan(x) else int(x))
    df_tmp = df[(df['blower_hz_int'] >= range_hz[0]) & (df['blower_hz_int'] <= range_hz[1])][['cycle_id', 'blower_hz_int']]

    cycle = []
    mode = []
    fq = []

    for ciclo in df_tmp.cycle_id.unique():
        df_tmp2 = df_tmp[df_tmp.cycle_id == ciclo]
        moda = st.mode(df_tmp2.blower_hz_int)[0][0]
        freq = st.mode(df_tmp2.blower_hz_int)[1][0]

        if freq < 2: #si la frecuencia de la moda es menor a dos, significa que no es un ciclo con hz minimos, ya que opero a un mismo nivel
            None       # Se reviso previamente esos ciclos y corresponden a los que tienen errores de lectura
        else:
            mode.append(moda)
            cycle.append(ciclo)
            fq.append(freq)

    hz_min = pd.DataFrame(zip(cycle, mode, fq ), columns= ['cycle_id', 'hz_min', 'freq'])
    hz_min['hz_min'] = hz_min['hz_min'].astype(int)

    df = df.merge(hz_min, how='left', on='cycle_id')
    df.set_index('date_time', inplace = True)
    df['date_time'] = df.index
    return df

def df_etl8_do_air(df):
    do_level_air = df[df.blower_on ==1].groupby(['cycle_id']).do_level.mean().reset_index().rename(columns = {'do_level': 'do_level_air'})
    df = df.merge(do_level_air, how='left', on='cycle_id')
    return df

def df_etl9_n_final(df):
    dic_cycle = {}
    for cycle_id in df.cycle_id.unique():
        cycle_obs =  df[(df.state_settle_decant == 1) & (df.cycle_id == cycle_id)]
        diff_cm = ((cycle_obs.h2o_level - cycle_obs.h2o_level.shift(1))*100).reset_index().set_index('index')
        diff_cm['cum_sum'] = diff_cm.h2o_level.cumsum()
        diff_cm['cum_perc'] = 100*diff_cm['cum_sum']/diff_cm['h2o_level'].sum()

        list_index = []
        n_index = None
        for index, value in diff_cm.cum_perc.items():
            if value >= 8 and np.isnan(value)==False: #si la caida de agua es sobre un 8% de la caida total se considera como momento de caida
                list_index.append(index)

        if len(list_index) > 0:
            n_index = np.min(list_index)  #el indice que me interesa es el anterior a la caida de agua, ya que sigo con el nivel de agua alto
            n_mean = cycle_obs.n_level.loc[n_index-2: n_index+2].mean() #determino el promedio de no3 con dos obserrvaciones antes al momento de caida y dos obs dsps
            dic_cycle[cycle_id] = [n_mean, cycle_obs.date_time.loc[n_index]]
    
    n_level_final = pd.DataFrame(dic_cycle).T.reset_index().rename(columns = {'index':'cycle_id', 0:'n_level_final', 1:'date_time_no3'})
    n_level_final['n_level_final']  = n_level_final['n_level_final'].astype(float)
    df = df.merge(n_level_final, how='left', on='cycle_id')
    df['dt_descarga_minu'] = (df.cycle_max_time - df.date_time_no3).astype("timedelta64[s]")/60 

    return df

def df_etl10_h2o_mean(df):
    """"""
    dic_cycle = {}
    for cycle_id in df.cycle_id.unique():
        cycle_obs =  df[(df.state_settle_decant == 0) & (df.cycle_id == cycle_id)]
        diff_cm = ((cycle_obs.h2o_level - cycle_obs.h2o_level.shift(1))*100).reset_index().set_index('index')
        diff_cm['cum_sum'] = diff_cm.h2o_level.cumsum()
        diff_cm['cum_perc'] = 100*diff_cm['cum_sum']/diff_cm['h2o_level'].sum()

        list_index = []
        w_index = None
        for index, value in diff_cm.cum_perc.items():
            if value >= 95 and np.isnan(value)==False: 
                list_index.append(index)

        if len(list_index) > 0:
            w_index = np.min(list_index)  
            w_mean = cycle_obs.h2o_level.loc[w_index:].mean() 
            dic_cycle[cycle_id] = [w_mean, cycle_obs.date_time.loc[w_index]]
      
    h2o_mean = pd.DataFrame(dic_cycle).T.reset_index().rename(columns = {'index':'cycle_id', 0:'h2o_max', 1:'date_time_h2o'})
    h2o_mean['h2o_max']  = h2o_mean['h2o_max'].astype(float)
    df = df.merge(h2o_mean, how='left', on='cycle_id')
    df['dt_carga_minu'] = (df.date_time_h2o - df.cycle_min_time).astype("timedelta64[s]")/60
  
    return df

def etl11_do_setpoint(df):
    df.set_index('date_time', inplace = True)
    df['date_time'] = df.index

    list_cycle = []
    list_date_first_sp = []
    list_first_sp = []
    list_date_max_do = []
    list_max_do = []
    data = {'cycle_id':list_cycle, 'date_first_sp':list_date_first_sp, 'do_first_sp':list_first_sp, 'date_max_do':list_date_max_do, 'max_do_level':list_max_do}
  
    ### recorrer ciclos  
    for cycle_id in df.cycle_id.unique():
        cycle_obs = df[df.cycle_id == cycle_id]
        dict_do = {}

        for index, value in cycle_obs.do_level.items():
        #if value >=4:
            dict_do[index] = value

        if len(dict_do)>0:
        # Maximo nivel de oxigeno
            date_max_do = max(dict_do, key=dict_do.get)
            max_do_level = dict_do[date_max_do]
        else:
            date_max_do = np.nan
            max_do_level = np.nan

        # Septpoint
        tmp_dict = dict(filter(lambda x: x[1] >=4, dict_do.items()))
        if len(tmp_dict)> 0:
            date_first_sp  = list(tmp_dict.keys())[0]
            do_first_sp = tmp_dict[date_first_sp]
        else:
            date_first_sp = np.nan
            do_first_sp = np.nan
      
        list_cycle.append(cycle_id)
        list_date_max_do.append(date_max_do)
        list_max_do.append(max_do_level)
        list_date_first_sp.append(date_first_sp)
        list_first_sp.append(do_first_sp)

    df_do = pd.DataFrame(data)
    df = df.merge(df_do, on='cycle_id', how='left')
    df['dt_first_sp'] = (df.date_first_sp - df.cycle_min_time).astype("timedelta64[s]")/60
    df['dt_do_max'] = (df.date_max_do - df.cycle_min_time).astype("timedelta64[s]")/60

    df.set_index('date_time', inplace = True)
    df['date_time'] = df.index

    return df

def alerta_h2o_level(df, metodo = 1, segmento_day = False):
    '''
    data requerida: ['cycle_id', 'cycle_min_time', 'h2o_max']
    '''
    df_tmp = df.copy()

    df_tmp = df_etl6_timeofday(df)

    df_tmp = dataframe_resumen(df_tmp, groupby = ['cycle_id', 'cycle_min_time', 'time_of_day'], var_mean = ['h2o_max'])
    
    df_tmp = df_tmp.set_index('cycle_id')


    ic_sigma= {'1-Early Morning': [4.159110, 4.638898], '2-Morning': [4.190239, 4.614350], '3-Noon':  [4.691703,	5.681053] , 
              '4-Afternoon':[4.778890, 5.416666], '5-Night': [4.510861, 5.140025]}


    ic_quantile = {'1-Early Morning': [4.109883, 4.693305], '2-Morning': [4.147417, 4.604059], '3-Noon':  [4.463348,	5.681545] , 
              '4-Afternoon':[4.686255, 5.490179], '5-Night': [4.401845, 5.236923]}

    if metodo == 1:
        ic = ic_sigma

    if metodo == 2:
        ic = ic_quantile

    cycle_id = []
    time = []
    outliers = []

  
    for index, row in df_tmp.iterrows():
        time_cycle = row['time_of_day']
        lim_inf = ic[time_cycle][0]
        lim_sup = ic[time_cycle][1]
        obs = row['h2o_max']

        cycle_id.append(index)
        time.append(time_cycle)

        if np.isnan(obs) == True:
            outliers.append(1)
        elif obs < lim_inf:
            outliers.append(1)
        elif obs > lim_sup:
            outliers.append(1)
        else:
            outliers.append(0)

    if segmento_day == True:
        df_out_h2o = pd.DataFrame({'cycle_id': cycle_id, 'time_of_day': time,'outlier_h2o_max': outliers})
 
    if segmento_day == False:
        df_out_h2o = pd.DataFrame({'cycle_id': cycle_id,'outlier_h2o_max': outliers})

    df = df.merge(df_out_h2o, on= 'cycle_id', how= 'left')
    return df

def alerta_do_level_air(df, metodo = 1, segmento_day = False):
    '''
    data requerida: ['cycle_id', 'cycle_min_time', 'do_level_air']
    '''
    df_tmp = df.copy()

    df_tmp = df_etl6_timeofday(df)

    df_tmp = dataframe_resumen(df_tmp, groupby = ['cycle_id', 'cycle_min_time', 'time_of_day'], var_mean = ['do_level_air'])
  
    df_tmp = df_tmp.set_index('cycle_id')

    ic_sigma= {'1-Early Morning': [2.124242, 3.410706], '2-Morning': [2.397565, 3.559911], '3-Noon':  [1.183621,	2.465646] , 
                '4-Afternoon':[1.125073, 2.292883], '5-Night': [1.508356, 2.452817]}

    ic_quantile = {'1-Early Morning': [1.898231, 3.354442], '2-Morning': [2.489497, 3.481098], '3-Noon':  [0.962602,	2.671460] , 
                '4-Afternoon':[0.914143, 2.388957], '5-Night': [1.283736, 2.444022]}

    if metodo == 1:
        ic = ic_sigma

    if metodo == 2:
        ic = ic_quantile

    cycle_id = []
    time = []
    outliers = []

    for index, row in df_tmp.iterrows():
        time_cycle = row['time_of_day']
        lim_inf = ic[time_cycle][0]
        lim_sup = ic[time_cycle][1]
        obs = row['do_level_air']

        cycle_id.append(index)
        time.append(time_cycle)

        if np.isnan(obs) == True:
            outliers.append(1)
        elif obs < lim_inf:
            outliers.append(1)
        elif obs > lim_sup:
            outliers.append(1)
        else:
            outliers.append(0)

    if segmento_day == True: 
        df_out_air = pd.DataFrame({'cycle_id': cycle_id, 'time_of_day': time,'outlier_do_level_air': outliers})

    if segmento_day == False:
        df_out_air = pd.DataFrame({'cycle_id': cycle_id,'outlier_do_level_air': outliers})
  
    df = df.merge(df_out_air, on= 'cycle_id', how= 'left')
    return df

def alerta_blower_hz(df, metodo = 1, segmento_day = False):
    '''
    data requerida: ['cycle_id', 'cycle_min_time', 'blower_hz']
    '''

    df_tmp = df.copy()

    df_tmp = df_etl6_timeofday(df)

    df_tmp = dataframe_resumen(df_tmp, groupby = ['cycle_id', 'cycle_min_time', 'time_of_day'], var_sum = ['blower_hz'])
    
    df_tmp = df_tmp.set_index('cycle_id')


    ic_sigma= {'1-Early Morning': [618.933251, 1187.315789], '2-Morning': [588.154735, 1116.272274], '3-Noon':  [870.335238,	1512.570014] , 
              '4-Afternoon':[1053.224687, 1510.664739], '5-Night': [976.458680, 1391.274993]}


    ic_quantile = {'1-Early Morning': [600.120008, 1137.766258], '2-Morning': [611.560009, 1060.241263], '3-Noon':  [891.885002,	1600.430008] , 
              '4-Afternoon':[1018.650007, 1512.210005], '5-Night': [940.690001, 1488.535024]}

    if metodo == 1:
        ic = ic_sigma

    if metodo == 2:
        ic = ic_quantile

    cycle_id = []
    time = []
    outliers = []

  
    for index, row in df_tmp.iterrows():
        time_cycle = row['time_of_day']
        lim_inf = ic[time_cycle][0]
        lim_sup = ic[time_cycle][1]
        obs = row['blower_hz']

        cycle_id.append(index)
        time.append(time_cycle)

        if np.isnan(obs) == True:
            outliers.append(1)
        elif obs < lim_inf:
            outliers.append(1)
        elif obs > lim_sup:
            outliers.append(1)
        else:
            outliers.append(0)

    if segmento_day == True:
        df_out_blw = pd.DataFrame({'cycle_id': cycle_id, 'time_of_day': time,'outlier_blower': outliers})
    
    if segmento_day == False:
        df_out_blw = pd.DataFrame({'cycle_id': cycle_id,'outlier_blower': outliers})

    df = df.merge(df_out_blw, on= 'cycle_id', how= 'left')
    return df

def etl_cycle_resumen(df): 
    """"""
    colnames = ['cycle_id', 'date_cycle', 'time_of_day', 'cycle_min_time', 'cycle_max_time','dt_cycle_minu', 'hora_inicio_ciclo', 'hora_fin_ciclo', #atributos del ciclo
                'inicio_settle_decant', 'fin_settle_decant', #info de settle/decant
                'date_time_h2o', 'dt_carga_minu',  'h2o_max', #info de nivel de agua y tiempo en llegar al maximo
                'date_time_no3', 'dt_descarga_minu', 'n_level_final', #info del nivel de nitrato y tiempo en descargar agua del ciclo 
                'date_first_sp', 'dt_first_sp', 'do_first_sp', #info sobre el primer setpoint maximo 
                'date_max_do', 'dt_do_max',  'max_do_level', #info sobre el nivel maximo de oxigeno alcanzado
                'do_level_air', 'do_level', 'do_temp', 'mlss_level', 'h2o_level', 'n_level','blower_hz', 'hz_min',
                'outlier_h2o_max', 'outlier_do_level_air', 'outlier_blower'] 

    groupby =  ['cycle_id', 'date_cycle', 'time_of_day', 'cycle_min_time', 'cycle_max_time','dt_cycle_minu', 'hora_inicio_ciclo', 'hora_fin_ciclo', #atributos del ciclo
                'inicio_settle_decant', 'fin_settle_decant', 'outlier_h2o_max', 'outlier_do_level_air', 'outlier_blower']
    var_sum = ['blower_hz']
    var_mean = ['do_level', 'do_temp', 'mlss_level', 'h2o_level', 'n_level','dt_carga_minu', 'do_level_air',  
                'h2o_max', 'dt_descarga_minu', 'n_level_final', 'dt_first_sp', 'do_first_sp',  'dt_do_max',  'max_do_level', 'hz_min']
    var_date = ['date_time_h2o', #info de nivel de agua y tiempo en llegar al maximo
                'date_time_no3', #info del nivel de nitrato y tiempo en descargar agua del ciclo 
                'date_first_sp', #info sobre el primer setpoint maximo 
                'date_max_do']

    df_cycle = dataframe_resumen(df, groupby, var_sum, var_mean, var_date = var_date)
    df_cycle = df_cycle[colnames]
    return df_cycle

def etl_complete(df):
    df = df_etl1_duplicados(df)
    df = df_etl2_errores_lectura(df, columns_var = ['do_level', 'do_temp', 'h2o_level', 'mlss_level','n_level', 'blower_hz'])
    df = df_etl3_tiempo(df)
    df = df_etl4_ciclos(df)
    df = df_etl5_aireacion(df, high=4, low=1.5)
    df = df_etl6_timeofday(df)
    df = df_etl7_hz_min(df)
    df = df_etl8_do_air(df)
    df = df_etl9_n_final(df)
    df = df_etl10_h2o_mean(df)
    df = etl11_do_setpoint(df)
    df = alerta_h2o_level(df, segmento_day= False)
    df = alerta_do_level_air(df, segmento_day= False)
    df = alerta_blower_hz(df, segmento_day= False)
    df_cycle = etl_cycle_resumen(df)
    return df, df_cycle


#########
#########
#########
def historico_variables_index(df, columns, range_date = False, cycle_id = False ,figsize = (20, 10)):

    fig = plt.figure(figsize = figsize)

    if range_date != False:
        df_tmp = df.loc[range_date[0] : range_date[1]]
        print(f'Historico de periodo {range_date[0]} - {range_date[1]}')

    if cycle_id != False:
        df_tmp = df[df.cycle_id == cycle_id]
        print(f'Historico de ciclo {cycle_id}')

    i=0
    for colname in columns:
        plt.subplot(len(columns),1, i+1)
        df_tmp[colname].plot(title = colname)
        i+=1

    fig.tight_layout()



def plot_var(df, xvar, yvar, y2var = False, range_date = False, cycle_id = False, show_cycle = True, figsize=(20,5), kind = 'line'):

    if range_date != False:
        df_tmp = df.loc[range_date[0] : range_date[1]]
        print(f'Historico de periodo {range_date[0]} - {range_date[1]}')

    if cycle_id != False:
        df_tmp = df[df.cycle_id == cycle_id]
        print(f'Historico de ciclo {cycle_id}')

    ax = df_tmp.plot( x= xvar, y= yvar, figsize=figsize, kind = kind)
    ax.set_ylabel(yvar)
    
    if y2var != False:
        ax2 = df_tmp.plot( x= xvar, y= y2var, secondary_y = True, figsize=figsize, kind = kind, ax=ax)
        ax2.set_ylabel(y2var)
        
    if show_cycle == True:
        cycle_date = df_tmp.groupby('cycle_id')['date_cycle'].min()
        for ciclo in range(len(cycle_date)):
            plt.axvline(cycle_date[ciclo], color= 'r', ls='dotted')
            
    plt.tight_layout()
    plt.show()

def distribucion_clase(dataframe, variable, categoria, clase, titulo):
    '''
    distribución_ciclo: entrega histograma con la distribución de la variable en estudio, esta función tiene la 
    particularidad de filtrar el dataframe de acuerdo a una categoria y clase especifica
    Parámetros
    dataframe: dataframe que contiene la muestra de observaciones
    variable: variable en estudio tipo string
    categoria: categoria por la cual se quiere filtrar el dataframe tipo string
    clase: clase distintiva de la categoria tipo string
    titulo:  titulo del histograma
    '''
    df_tmp = dataframe[dataframe[categoria]==clase]
    mean = round(np.mean(df_tmp[variable]),2)
    sns.distplot(df_tmp[variable]).set_title(titulo)
    plt.axvline(mean, color= 'r', ls='dotted', label = f'media: {mean}')
    plt.legend()

def str_todate(date = ''):
    date = datetime.datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
    return date


def cycle_points(input_hora = '00:00:00', ciclo = 0, dict_level_h2o = 'dict_level_h2o', dict_index = 'dict_index', list_var_level = ['h2o_inicio', 'h2o_max','h2o_fin'], list_var_time = ['dt_carga_minu', 'dt_max_level','dt_descarga_minu'] ):
    with open(dict_level_h2o, 'rb') as xf_level:
        dict_level_h2o = pickle.load(xf_level)

    with open(dict_index, 'rb') as xf_index:
        dict_index = pickle.load(xf_index)
    
    hora = int(input_hora[:2])
    minutos = int(input_hora[3:5])
    
    time_input = time(hora,minutos)
    time_input_str = time.strftime(time_input, '%H:%M:%S')

    if minutos in range(1,16): #si minutos esta entre 1 y 15 minutos 
        arr_minuto = 15
    elif minutos in range(16,31): # Si minutos esta entre 16 y 30 minutos
        arr_minuto = 30
    elif minutos in range(31,46):
        arr_minuto = 45
    else:
        arr_minuto = 0

    time_search = time(hora,arr_minuto)
    time_search_key = time.strftime(time_search, '%H:%M:%S')


    key_index = dict_index[time_search_key]

    dic_var_level = {}
    for var_level in list_var_level:
        value_var_level = round(dict_level_h2o[var_level][key_index],2)
        dic_var_level[var_level] = value_var_level

    dic_var_time = {}
    acum_time = 0
    for var_time in list_var_time:
        value_var_time = int(dict_level_h2o[var_time][key_index]) #valor de variable (minutos)
        acum_time += value_var_time #total de minutos desde el inicio del proceso
        horas_acum = acum_time/60 #conversion de minutos a horas
        total_horas = int(horas_acum) #horas acumuladas
        total_minutos = int((horas_acum - total_horas)*60) #minutos acumulados

        time_refac = (minutos + total_minutos)/60 
        hora_refac =  hora + total_horas + int(time_refac)
        if hora_refac > 23:
            hora_refac = hora_refac - 24

        minutos_refac = int((time_refac - int(time_refac))*60)

        time_point = time(hora_refac, minutos_refac)
        time_point_str = time.strftime(time_point, '%H:%M:%S') 

        dic_var_time[var_time] = [value_var_time, acum_time, time_point_str]



    puntos = {'time': {1: time_input_str, 2: dic_var_time['dt_carga_minu'][2], 3: dic_var_time['dt_max_level'][2], 4: dic_var_time['dt_descarga_minu'][2]},
            'h2o_level': {1: dic_var_level['h2o_inicio'], 2: dic_var_level['h2o_max'], 3: dic_var_level['h2o_max'],4: dic_var_level['h2o_fin']},
            'duration': {1: 0, 2: dic_var_time['dt_carga_minu'][0], 3: dic_var_time['dt_max_level'][0],4: dic_var_time['dt_descarga_minu'][0]},
            'duration_acum': {1: 0, 2: dic_var_time['dt_carga_minu'][1], 3: dic_var_time['dt_max_level'][1], 4: dic_var_time['dt_descarga_minu'][1]},
            'ciclo': {1: ciclo, 2: ciclo, 3: ciclo, 4: ciclo}}
    return puntos


def simulacion_ciclos(input_hora = '00:00:00', cant_ciclos=5,dict_level_h2o = 'dict_level_h2o', dict_index = 'dict_index'):
    df_ciclos = {}

    hora_ciclo = input_hora
    for ciclo in range(cant_ciclos):
        puntos = cycle_points(input_hora = hora_ciclo, ciclo= ciclo,dict_level_h2o=dict_level_h2o,dict_index=dict_index)
        df_puntos = pd.DataFrame(puntos)
        if len(df_ciclos) == 0:
            df_ciclos = df_puntos
        else:
            df_ciclos = pd.concat([df_ciclos, df_puntos])
        hora_ciclo = puntos['time'][4]

    return df_ciclos