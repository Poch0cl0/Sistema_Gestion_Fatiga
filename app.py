"""
SISTEMA DE GESTIÓN DE FATIGA - DASHBOARD STREAMLIT
Aplicación multi-panel para monitoreo de fatiga en operadores de maquinaria pesada
VERSIÓN ADAPTADA - Compatible con Schema SQL y Workflow n8n
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta, timezone, time
import json
from supabase import create_client, Client
import os
from typing import List, Dict, Optional
import base64
from io import BytesIO
from reportlab.lib.pagesizes import letter, A4
import requests # Importar la librería requests
import random # Importar random para la función de prueba
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT


# ============================================
# CONFIGURACIÓN INICIAL
# ============================================

st.set_page_config(
    page_title="Sistema de Gestión de Fatiga",
    page_icon="⚠️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Configuración de Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://obxaiijugjzqrkpihttt.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9ieGFpaWp1Z2p6cXJrcGlodHR0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjMzOTY3MzEsImV4cCI6MjA3ODk3MjczMX0.Ifr2_Q99wL1eNmtK0JsMl-AaoNuuF2Oxl5cBSLJarII")

# Configuración del Webhook de n8n
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook-test/fatigue-data-ingestion") # ¡IMPORTANTE! Reemplaza con la URL real de tu webhook de n8n

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"Error conectando a Supabase: {e}")
    st.stop()

# Estilos CSS personalizados
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 20px;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #1f77b4;
    }
    .alert-critical {
        background-color: #ff4444;
        color: white;
        padding: 15px;
        border-radius: 5px;
        font-weight: bold;
    }
    .alert-high {
        background-color: #ff9800;
        color: white;
        padding: 15px;
        border-radius: 5px;
        font-weight: bold;
    }
    .alert-medium {
        background-color: #ffc107;
        color: black;
        padding: 15px;
        border-radius: 5px;
        font-weight: bold;
    }
    .status-ok {
        color: #4CAF50;
        font-weight: bold;
    }
    .status-warning {
        color: #ff9800;
        font-weight: bold;
    }
    .status-danger {
        color: #f44336;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# FUNCIONES DE UTILIDAD - ADAPTADAS
# ============================================

@st.cache_data(ttl=60)
def get_operator_uuid_by_external_id(external_id):
    url = f"{SUPABASE_URL}/rest/v1/operadores?select=id&codigo_operador=eq.{external_id}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return None

    data = response.json()
    if not data:
        return None

    return data[0]["id"]  # UUID del operador

def generar_datos_simulados(tipo_dispositivo: str) -> dict:
    """Genera datos simulados aleatorios según el tipo de dispositivo"""
    if tipo_dispositivo == 'SMARTWATCH':
        return {
            "sleep": {
                "duration_hours": round(random.uniform(4.0, 9.0), 1),
                "quality_score": random.randint(40, 95),
                "deep_minutes": random.randint(30, 120),
                "rem_minutes": random.randint(60, 120),
                "efficiency": round(random.uniform(0.6, 0.95), 2)
            },
            "vitals": {
                "heart_rate": random.randint(55, 100),
                "hrv_rmssd": round(random.uniform(15.0, 80.0), 1),
                "hrv_sdnn": round(random.uniform(20.0, 100.0), 1),
                "spo2": round(random.uniform(90.0, 100.0), 1),
                "skin_temp": round(random.uniform(35.5, 37.5), 1),
                "stress_level": random.randint(10, 90)
            }
        }
    elif tipo_dispositivo == 'BANDA_ANTIFATIGA':
        return {
            "posture": {
                "trunk_angle": round(random.uniform(0.0, 45.0), 1),
                "head_nods": random.randint(0, 10),
                "micro_sleeps": random.randint(0, 5)
            },
            "emg": {
                "neck_activity": random.randint(20, 100)
            },
            "movement": {
                "inactivity_minutes": random.randint(0, 60)
            }
        }
    elif tipo_dispositivo == 'TELEMATICA':
        return {
            "machinery": {
                "type": random.choice(["Excavadora", "Camión Minero", "Pala Cargadora", "Bulldozer", "Grúa"])
            },
            "shift": {
                "type": random.choice(["DIA", "NOCHE", "ROTATIVO"]),
                "hours_elapsed": round(random.uniform(0.5, 10.0), 1)
            },
            "environment": {
                "temperature": round(random.uniform(15.0, 40.0), 1),
                "humidity": random.randint(20, 90)
            }
        }
    return {}

def cargar_operadores_activos():
    """Carga operadores activos con su última métrica - ADAPTADO"""
    try:
        # Usar la vista v_estado_actual_operadores
        response = supabase.table('v_estado_actual_operadores')\
            .select('*')\
            .execute()
        
        if response.data:
            df = pd.DataFrame(response.data)
            # Renombrar columnas para compatibilidad
            if 'indice_fatiga_actual' not in df.columns and 'indice_fatiga' in df.columns:
                df['indice_fatiga_actual'] = df['indice_fatiga']
            return df
        return pd.DataFrame()
    except Exception as e:
        # Si la vista no existe, usar consulta directa
        try:
            # Obtener operadores activos
            response_ops = supabase.table('operadores')\
                .select('*')\
                .eq('estado', 'ACTIVO')\
                .execute()
            
            if not response_ops.data:
                return pd.DataFrame()
            
            df_ops = pd.DataFrame(response_ops.data)
            df_ops['nombre_completo'] = df_ops['nombre'] + ' ' + df_ops['apellido']
            
            # Obtener última métrica para cada operador
            metricas_list = []
            for op_id in df_ops['id']:
                response_metric = supabase.table('metricas_procesadas')\
                    .select('indice_fatiga, clasificacion_riesgo, timestamp')\
                    .eq('id_operador', op_id)\
                    .order('timestamp', desc=True)\
                    .limit(1)\
                    .execute()
                
                if response_metric.data:
                    metric = response_metric.data[0]
                    metric['id_operador'] = op_id
                    metricas_list.append(metric)
            
            if metricas_list:
                df_metrics = pd.DataFrame(metricas_list)
                df_result = df_ops.merge(df_metrics, left_on='id', right_on='id_operador', how='left')
                df_result['indice_fatiga_actual'] = df_result['indice_fatiga']
                df_result['ultima_medicion'] = df_result['timestamp']
                
                # Contar alertas activas
                response_alerts = supabase.table('alertas')\
                    .select('id_operador')\
                    .eq('estado', 'ACTIVA')\
                    .execute()
                
                if response_alerts.data:
                    df_alerts = pd.DataFrame(response_alerts.data)
                    alert_counts = df_alerts['id_operador'].value_counts()
                    df_result['alertas_activas'] = df_result['id'].map(alert_counts).fillna(0)
                else:
                    df_result['alertas_activas'] = 0
                
                return df_result
            
            return df_ops
        except Exception as e2:
            st.error(f"Error al cargar operadores: {e2}")
            return pd.DataFrame()

@st.cache_data(ttl=30)
def cargar_alertas_activas():
    """Carga alertas activas del sistema - ADAPTADO"""
    try:
        response = supabase.table('alertas')\
            .select('*, operadores(nombre, apellido, codigo_operador)')\
            .eq('estado', 'ACTIVA')\
            .order('timestamp', desc=True)\
            .limit(100)\
            .execute()
        
        if response.data:
            df = pd.DataFrame(response.data)
            # Extraer nombre del operador del objeto anidado
            if 'operadores' in df.columns:
                df['operador_nombre'] = df['operadores'].apply(
                    lambda x: f"{x['nombre']} {x['apellido']}" if x else 'N/A'
                )
                df['operador_codigo'] = df['operadores'].apply(
                    lambda x: x['codigo_operador'] if x else 'N/A'
                )
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error al cargar alertas: {e}")
        return pd.DataFrame()

def cargar_metricas_operador(operator_id: str, horas: int = 24):
    """Carga métricas históricas de un operador - ADAPTADO"""
    try:
        fecha_inicio = (datetime.now() - timedelta(hours=horas)).isoformat()
        response = supabase.table('metricas_procesadas')\
            .select('*')\
            .eq('id_operador', operator_id)\
            .gte('timestamp', fecha_inicio)\
            .order('timestamp', desc=False)\
            .execute()
        
        if response.data:
            df = pd.DataFrame(response.data)
            # Convertir timestamp a datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error al cargar métricas: {e}")
        return pd.DataFrame()

def cargar_turnos_activos():
    """Carga turnos actualmente en curso - ADAPTADO"""
    try:
        response = supabase.table('turnos')\
            .select('*, operadores(nombre, apellido, codigo_operador)')\
            .eq('estado', 'EN_CURSO')\
            .execute()
        
        if response.data:
            df = pd.DataFrame(response.data)
            # Procesar datos anidados del operador
            if 'operadores' in df.columns:
                df['operador_nombre'] = df['operadores'].apply(
                    lambda x: f"{x['nombre']} {x['apellido']}" if x else 'N/A'
                )
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error al cargar turnos: {e}")
        return pd.DataFrame()

def color_riesgo(clasificacion: str) -> str:
    """Retorna color según clasificación de riesgo"""
    colores = {
        'BAJO': '#4CAF50',
        'MEDIO': '#ffc107',
        'ALTO': '#ff9800',
        'CRITICO': '#f44336'
    }
    return colores.get(clasificacion, '#808080')

def gestionar_alerta(alert_id: str, accion: str, notas: str = ""):
    """Gestiona el estado de una alerta - ADAPTADO"""
    try:
        nuevo_estado = {
            'ignorar': 'IGNORADA',
            'reconocer': 'RECONOCIDA',
            'gestionar': 'EN_GESTION',
            'resolver': 'RESUELTA'
        }.get(accion, 'ACTIVA')
        
        update_data = {
            'estado': nuevo_estado,
            'updated_at': datetime.now().isoformat()
        }
        
        if accion == 'reconocer':
            update_data['timestamp_reconocimiento'] = datetime.now().isoformat()
        elif accion == 'resolver':
            update_data['timestamp_resolucion'] = datetime.now().isoformat()
            if notas:
                update_data['resultado'] = 'Resuelto'
        
        if notas:
            update_data['notas'] = notas
            
        supabase.table('alertas').update(update_data).eq('id', alert_id).execute()
        st.success(f"✅ Alerta {accion}da exitosamente")
        st.rerun()
    except Exception as e:
        st.error(f"Error al gestionar alerta: {e}")

# ============================================
# FUNCIONES DE VISUALIZACIÓN
# ============================================

def crear_gauge_fatiga(valor: float, titulo: str = "Índice de Fatiga"):
    """Crea un gauge chart para mostrar índice de fatiga"""
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=valor if valor is not None else 0,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': titulo, 'font': {'size': 20}},
        delta={'reference': 50, 'increasing': {'color': "red"}},
        gauge={
            'axis': {'range': [None, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
            'bar': {'color': "darkblue"},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 40], 'color': '#4CAF50'},
                {'range': [40, 70], 'color': '#ffc107'},
                {'range': [70, 85], 'color': '#ff9800'},
                {'range': [85, 100], 'color': '#f44336'}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 85
            }
        }
    ))
    
    fig.update_layout(
        height=300,
        margin=dict(l=20, r=20, t=50, b=20),
        paper_bgcolor="white",
        font={'color': "darkblue", 'family': "Arial"}
    )
    
    return fig

def crear_mapa_flota(df_operadores: pd.DataFrame):
    """Crea visualización de mapa de flota"""
    if df_operadores.empty:
        return go.Figure()
    
    fig = go.Figure()
    
    for riesgo in ['BAJO', 'MEDIO', 'ALTO', 'CRITICO']:
        df_filtrado = df_operadores[df_operadores['clasificacion_riesgo'] == riesgo]
        if not df_filtrado.empty:
            fig.add_trace(go.Scatter(
                x=df_filtrado.index,
                y=[riesgo] * len(df_filtrado),
                mode='markers+text',
                name=riesgo,
                text=df_filtrado['nombre_completo'],
                textposition="top center",
                marker=dict(
                    size=30,
                    color=color_riesgo(riesgo),
                    line=dict(width=2, color='white')
                ),
                hovertemplate='<b>%{text}</b><br>' +
                              'Índice: %{customdata[0]:.1f}<br>' +
                              'Turno: %{customdata[1]}<br>' +
                              '<extra></extra>',
                customdata=df_filtrado[['indice_fatiga_actual', 'turno_asignado']].values
            ))
    
    fig.update_layout(
        title="Mapa de Estado de la Flota",
        xaxis_title="Operador",
        yaxis_title="Nivel de Riesgo",
        height=400,
        showlegend=True,
        hovermode='closest',
        plot_bgcolor='rgba(240,240,240,0.5)'
    )
    
    return fig

def crear_serie_temporal_fatiga(df_metricas: pd.DataFrame):
    """Crea gráfico de serie temporal de fatiga"""
    if df_metricas.empty:
        return go.Figure()
    
    fig = go.Figure()
    
    # Línea de índice de fatiga
    fig.add_trace(go.Scatter(
        x=df_metricas['timestamp'],
        y=df_metricas['indice_fatiga'],
        mode='lines+markers',
        name='Índice de Fatiga',
        line=dict(color='#1f77b4', width=3),
        marker=dict(size=6),
        fill='tozeroy',
        fillcolor='rgba(31, 119, 180, 0.2)'
    ))
    
    # Líneas de umbral
    fig.add_hline(y=70, line_dash="dash", line_color="orange", 
                  annotation_text="Umbral Alto", annotation_position="right")
    fig.add_hline(y=85, line_dash="dash", line_color="red", 
                  annotation_text="Umbral Crítico", annotation_position="right")
    
    # Marcar anomalías
    if 'anomalia_detectada' in df_metricas.columns:
        df_anomalias = df_metricas[df_metricas['anomalia_detectada'] == True]
        if not df_anomalias.empty:
            fig.add_trace(go.Scatter(
                x=df_anomalias['timestamp'],
                y=df_anomalias['indice_fatiga'],
                mode='markers',
                name='Anomalía Detectada',
                marker=dict(size=15, color='red', symbol='x', line=dict(width=2))
            ))
    
    fig.update_layout(
        title="Evolución del Índice de Fatiga",
        xaxis_title="Tiempo",
        yaxis_title="Índice de Fatiga (0-100)",
        height=400,
        hovermode='x unified',
        yaxis=dict(range=[0, 100])
    )
    
    return fig

def crear_dashboard_metricas(df_metricas: pd.DataFrame):
    """Crea dashboard multi-métrica"""
    if df_metricas.empty or len(df_metricas) < 2:
        return go.Figure()
    
    # Crear subplots
    fig = make_subplots(
        rows=3, cols=2,
        subplot_titles=('HRV (RMSSD)', 'SpO2', 'Frecuencia Cardíaca', 
                       'Nivel de Estrés', 'Calidad de Sueño', 'Horas en Turno'),
        vertical_spacing=0.1,
        horizontal_spacing=0.1
    )
    
    # HRV
    if 'hrv_rmssd' in df_metricas.columns:
        fig.add_trace(go.Scatter(
            x=df_metricas['timestamp'], 
            y=df_metricas['hrv_rmssd'].fillna(0),
            name='HRV', line=dict(color='green')
        ), row=1, col=1)
    
    # SpO2
    if 'spo2' in df_metricas.columns:
        fig.add_trace(go.Scatter(
            x=df_metricas['timestamp'], 
            y=df_metricas['spo2'].fillna(0),
            name='SpO2', line=dict(color='blue')
        ), row=1, col=2)
    
    # Frecuencia Cardíaca
    if 'frecuencia_cardiaca' in df_metricas.columns:
        fig.add_trace(go.Scatter(
            x=df_metricas['timestamp'], 
            y=df_metricas['frecuencia_cardiaca'].fillna(0),
            name='FC', line=dict(color='red')
        ), row=2, col=1)
    
    # Nivel de Estrés
    if 'nivel_estres' in df_metricas.columns:
        fig.add_trace(go.Scatter(
            x=df_metricas['timestamp'], 
            y=df_metricas['nivel_estres'].fillna(0),
            name='Estrés', line=dict(color='orange')
        ), row=2, col=2)
    
    # Calidad de Sueño
    if 'calidad_sueño' in df_metricas.columns:
        fig.add_trace(go.Scatter(
            x=df_metricas['timestamp'], 
            y=df_metricas['calidad_sueño'].fillna(0),
            name='Sueño', line=dict(color='purple')
        ), row=3, col=1)
    
    # Horas en turno
    if 'horas_turno_actual' in df_metricas.columns:
        fig.add_trace(go.Scatter(
            x=df_metricas['timestamp'], 
            y=df_metricas['horas_turno_actual'].fillna(0),
            name='Horas Turno', line=dict(color='brown')
        ), row=3, col=2)
    
    fig.update_layout(height=800, showlegend=False, hovermode='x unified')
    
    return fig

# ============================================
# FUNCIONES DE REPORTES - ADAPTADAS
# ============================================

def generar_reporte_pdf(periodo_inicio: datetime, periodo_fin: datetime, 
                        tipo_reporte: str = "SEMANAL") -> BytesIO:
    """Genera reporte PDF con estadísticas del periodo"""
    
    # Convertir date → datetime con hora mínima
    periodo_inicio_dt = datetime.combine(periodo_inicio, time.min).replace(tzinfo=timezone.utc)

    # Convertir date → datetime con hora máxima
    periodo_fin_dt = datetime.combine(periodo_fin, time.max).replace(tzinfo=timezone.utc)
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    story = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1f77b4'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    story.append(Paragraph(f"Reporte {tipo_reporte} de Gestión de Fatiga", title_style))
    story.append(Paragraph(
        f"Periodo: {periodo_inicio.strftime('%d/%m/%Y')} - {periodo_fin.strftime('%d/%m/%Y')}", 
        styles['Normal']
    ))
    story.append(Spacer(1, 0.3*inch))
    
    # Inicializar resumen_data y riesgo_data fuera del bloque if
    resumen_data = []
    riesgo_data = []

    try:
        # Métricas del periodo
        response_metricas = (
            supabase.table('metricas_procesadas')
            .select('*')
            .gte('timestamp', periodo_inicio_dt.isoformat())
            .lte('timestamp', periodo_fin_dt.isoformat())
            .execute()
        )
        
        df_metricas = pd.DataFrame(response_metricas.data) if response_metricas.data else pd.DataFrame()
        
        # Alertas del periodo
        response_alertas = (
            supabase.table('alertas')
            .select('*')
            .gte('timestamp', periodo_inicio_dt.isoformat())
            .lte('timestamp', periodo_fin_dt.isoformat())
            .execute()
        )
        
        df_alertas = pd.DataFrame(response_alertas.data) if response_alertas.data else pd.DataFrame()
        
        # Resumen Ejecutivo
        story.append(Paragraph("RESUMEN EJECUTIVO", styles['Heading2']))
        story.append(Spacer(1, 0.2*inch))
        
        if not df_metricas.empty:
            total_mediciones = len(df_metricas)
            indice_promedio = df_metricas['indice_fatiga'].mean()
            indice_maximo = df_metricas['indice_fatiga'].max()
            operadores_monitoreados = df_metricas['id_operador'].nunique()
            
            resumen_data = [
                ['Métrica', 'Valor'],
                ['Total de Mediciones', f'{total_mediciones:,}'],
                ['Operadores Monitoreados', str(operadores_monitoreados)],
                ['Índice de Fatiga Promedio', f'{indice_promedio:.1f}/100'],
                ['Índice de Fatiga Máximo', f'{indice_maximo:.1f}/100'],
                ['Total de Alertas', str(len(df_alertas))],
                ['Alertas Críticas', str(len(df_alertas[df_alertas['nivel_alerta'] == 'CRITICO']))],
            ]
            
            resumen_table = Table(resumen_data, colWidths=[3*inch, 2*inch])
            resumen_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            
            story.append(resumen_table)
            story.append(Spacer(1, 0.3*inch))
            
            # Distribución de Riesgo
            story.append(Paragraph("DISTRIBUCIÓN DE NIVELES DE RIESGO", styles['Heading2']))
            story.append(Spacer(1, 0.2*inch))
            
            dist_riesgo = df_metricas['clasificacion_riesgo'].value_counts()
            riesgo_data = [['Nivel de Riesgo', 'Cantidad', 'Porcentaje']]
            for nivel in ['BAJO', 'MEDIO', 'ALTO', 'CRITICO']:
                if nivel in dist_riesgo.index:
                    cantidad = dist_riesgo[nivel]
                    porcentaje = (cantidad / total_mediciones) * 100
                    riesgo_data.append([nivel, str(cantidad), f'{porcentaje:.1f}%'])
            
            riesgo_table = Table(riesgo_data, colWidths=[2*inch, 1.5*inch, 1.5*inch])
            riesgo_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey)
            ]))
            
            story.append(riesgo_table)
        
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph(
            "Este reporte fue generado automáticamente por el Sistema de Gestión de Fatiga", 
            styles['Italic']
        ))
        story.append(Paragraph(
            f"Fecha de generación: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", 
            styles['Italic']
        ))
        
    except Exception as e:
        story.append(Paragraph(f"Error al generar reporte: {str(e)}", styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)

    # Calcular tamaño del archivo
    buffer.seek(0, os.SEEK_END)
    tamaño_kb = buffer.tell() / 1024
    buffer.seek(0)

    # Preparar estadísticas para JSONB
    estadisticas_reporte = {
        "resumen_ejecutivo": resumen_data,
        "distribucion_riesgo": riesgo_data
    }

    # Construir nombre de archivo
    nombre_archivo = f"reporte_fatiga_{tipo_reporte}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    # Datos para insertar en la tabla informes
    reporte_data = {
        "fecha_generacion": datetime.now().isoformat(),
        "tipo_informe": tipo_reporte,
        "periodo_inicio": periodo_inicio.isoformat(),
        "periodo_fin": periodo_fin.isoformat(),
        "titulo": f"Reporte {tipo_reporte} de Gestión de Fatiga",
        "descripcion": f"Reporte de fatiga generado para el periodo {periodo_inicio.strftime('%d/%m/%Y')} - {periodo_fin.strftime('%d/%m/%Y')}.",
        "filtros_aplicados": {}, # Dejar vacío por ahora, no se implementan filtros específicos en la generación
        "operadores_incluidos": [], # Dejar vacío por ahora
        "areas_incluidas": [], # Dejar vacío por ahora
        "estadisticas": estadisticas_reporte,
        "url_archivo": None, # Requiere Supabase Storage, no implementado en este paso
        "nombre_archivo": nombre_archivo,
        "formato": "PDF",
        "tamaño_kb": int(tamaño_kb),
        "generado_por": None, # Requiere autenticación de usuario, no implementado
        "nivel_confidencialidad": "INTERNO",
        "estado": "GENERADO"
    }

    try:
        supabase.table('informes').insert(reporte_data).execute()
        st.toast("Reporte registrado en Supabase exitosamente.", icon="✅")
    except Exception as e:
        st.error(f"Error al registrar reporte en Supabase: {e}")

    return buffer, nombre_archivo

# ============================================
# PANEL PRINCIPAL - GERENTE DE SEGURIDAD
# ============================================

def panel_gerente():
    st.markdown('<p class="main-header">🛡️ Panel de Control - Gerente de Seguridad</p>', 
                unsafe_allow_html=True)
    
    # KPIs principales
    col1, col2, col3, col4 = st.columns(4)
    
    df_operadores = cargar_operadores_activos()
    df_alertas = cargar_alertas_activas()
    
    with col1:
        total_operadores = len(df_operadores)
        st.metric("Operadores Activos", total_operadores)
    
    with col2:
        alertas_activas = len(df_alertas)
        alertas_criticas = len(df_alertas[df_alertas['nivel_alerta'] == 'CRITICO']) if not df_alertas.empty else 0
        st.metric("Alertas Activas", alertas_activas, 
                 delta=f"{alertas_criticas} críticas", delta_color="inverse")
    
    with col3:
        if not df_operadores.empty and 'indice_fatiga_actual' in df_operadores.columns:
            indice_promedio = df_operadores['indice_fatiga_actual'].mean()
            st.metric("Índice Fatiga Promedio", f"{indice_promedio:.1f}" if pd.notna(indice_promedio) else "N/A")
        else:
            st.metric("Índice Fatiga Promedio", "N/A")
    
    with col4:
        if not df_operadores.empty and 'clasificacion_riesgo' in df_operadores.columns:
            operadores_riesgo = len(df_operadores[
                df_operadores['clasificacion_riesgo'].isin(['ALTO', 'CRITICO'])
            ])
            st.metric("Operadores en Riesgo", operadores_riesgo, delta_color="inverse")
        else:
            st.metric("Operadores en Riesgo", "0")
    
    st.markdown("---")
    
    # ===== FILA 1: Distribución de Riesgo + Comparativa por Turno =====
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("🎯 Distribución de Niveles de Riesgo")
        if not df_operadores.empty and 'clasificacion_riesgo' in df_operadores.columns:
            # Filtrar valores nulos
            df_riesgo = df_operadores[df_operadores['clasificacion_riesgo'].notna()]
            
            if not df_riesgo.empty:
                # Contar por clasificación de riesgo
                riesgo_counts = df_riesgo['clasificacion_riesgo'].value_counts().reset_index()
                riesgo_counts.columns = ['Nivel', 'Cantidad']
                
                # Ordenar por severidad
                orden_riesgo = ['BAJO', 'MEDIO', 'ALTO', 'CRITICO']
                riesgo_counts['orden'] = riesgo_counts['Nivel'].apply(lambda x: orden_riesgo.index(x) if x in orden_riesgo else 99)
                riesgo_counts = riesgo_counts.sort_values('orden')
                
                colores_riesgo = {'BAJO': '#4CAF50', 'MEDIO': '#FFC107', 'ALTO': '#FF9800', 'CRITICO': '#F44336'}
                
                fig_dona = px.pie(
                    riesgo_counts, 
                    values='Cantidad', 
                    names='Nivel',
                    hole=0.5,
                    color='Nivel',
                    color_discrete_map=colores_riesgo
                )
                fig_dona.update_layout(
                    height=350,
                    margin=dict(t=30, b=30, l=30, r=30),
                    legend=dict(orientation="h", yanchor="bottom", y=-0.2)
                )
                fig_dona.update_traces(textposition='inside', textinfo='percent+value')
                st.plotly_chart(fig_dona, use_container_width=True)
            else:
                st.info("📊 Sin datos de clasificación de riesgo. Envíe datos desde Ingesta.")
        else:
            st.info("📊 Sin datos de riesgo disponibles")
    
    with col_chart2:
        st.subheader("📊 Fatiga Promedio por Turno")
        if not df_operadores.empty and 'turno_asignado' in df_operadores.columns and 'indice_fatiga_actual' in df_operadores.columns:
            # Filtrar datos válidos
            df_turno = df_operadores[df_operadores['indice_fatiga_actual'].notna()]
            
            if not df_turno.empty:
                # Calcular promedio por turno
                fatiga_turno = df_turno.groupby('turno_asignado')['indice_fatiga_actual'].mean().reset_index()
                fatiga_turno.columns = ['Turno', 'Índice Promedio']
                fatiga_turno = fatiga_turno.dropna()
                
                if not fatiga_turno.empty:
                    fig_turno = px.bar(
                        fatiga_turno,
                        x='Turno',
                        y='Índice Promedio',
                        color='Turno',
                        text='Índice Promedio',
                        color_discrete_sequence=['#1f77b4', '#ff7f0e', '#2ca02c', '#9467bd']
                    )
                    fig_turno.update_traces(texttemplate='%{text:.1f}', textposition='outside')
                    fig_turno.update_layout(
                        height=350,
                        margin=dict(t=30, b=30),
                        showlegend=False,
                        yaxis=dict(range=[0, 100], title="Índice de Fatiga")
                    )
                    # Agregar líneas de umbral
                    fig_turno.add_hline(y=70, line_dash="dash", line_color="orange", annotation_text="Alto")
                    fig_turno.add_hline(y=85, line_dash="dash", line_color="red", annotation_text="Crítico")
                    st.plotly_chart(fig_turno, use_container_width=True)
                else:
                    st.info("📊 Sin datos de fatiga por turno")
            else:
                st.info("📊 Sin métricas de fatiga. Envíe datos desde Ingesta.")
        else:
            st.info("📊 Sin datos de turno disponibles")
    
    st.markdown("---")
    
    # ===== FILA 2: Top Operadores + Alertas por Tipo =====
    col_chart3, col_chart4 = st.columns(2)
    
    with col_chart3:
        st.subheader("🏆 Top 5 Operadores con Mayor Fatiga")
        if not df_operadores.empty and 'indice_fatiga_actual' in df_operadores.columns:
            # Filtrar y obtener top 5
            df_con_fatiga = df_operadores[df_operadores['indice_fatiga_actual'].notna()]
            
            if not df_con_fatiga.empty:
                df_top = df_con_fatiga.nlargest(5, 'indice_fatiga_actual')[['nombre_completo', 'indice_fatiga_actual', 'clasificacion_riesgo']].copy()
                
                if not df_top.empty:
                    # Asignar colores según riesgo
                    colores_riesgo = {'BAJO': '#4CAF50', 'MEDIO': '#FFC107', 'ALTO': '#FF9800', 'CRITICO': '#F44336'}
                    df_top['Color'] = df_top['clasificacion_riesgo'].map(colores_riesgo).fillna('#808080')
                    
                    fig_top = go.Figure()
                    fig_top.add_trace(go.Bar(
                        y=df_top['nombre_completo'],
                        x=df_top['indice_fatiga_actual'],
                        orientation='h',
                        marker_color=df_top['Color'],
                        text=df_top['indice_fatiga_actual'].apply(lambda x: f"{x:.1f}"),
                        textposition='outside'
                    ))
                    fig_top.update_layout(
                        height=350,
                        margin=dict(t=30, b=30, l=150),
                        xaxis=dict(range=[0, 110], title="Índice de Fatiga"),
                        yaxis=dict(autorange="reversed")
                    )
                    fig_top.add_vline(x=70, line_dash="dash", line_color="orange")
                    fig_top.add_vline(x=85, line_dash="dash", line_color="red")
                    st.plotly_chart(fig_top, use_container_width=True)
                else:
                    st.info("📊 Sin datos de fatiga disponibles")
            else:
                st.info("📊 Sin métricas de fatiga. Envíe datos desde Ingesta.")
        else:
            st.info("📊 Sin datos de operadores disponibles")
    
    with col_chart4:
        st.subheader("📈 Alertas por Tipo")
        if not df_alertas.empty and 'tipo_alerta' in df_alertas.columns:
            # Contar alertas por tipo
            alertas_tipo = df_alertas['tipo_alerta'].value_counts().reset_index()
            alertas_tipo.columns = ['Tipo', 'Cantidad']
            
            # Nombres más amigables
            nombres_alertas = {
                'FATIGA_ALTA': '⚠️ Fatiga Alta',
                'FATIGA_CRITICA': '🔴 Fatiga Crítica',
                'ANOMALIA_DETECTADA': '🔍 Anomalía',
                'CABECEO_MULTIPLE': '😴 Cabeceos',
                'HRV_BAJO': '❤️ HRV Bajo',
                'SPO2_BAJO': '🫁 SpO2 Bajo',
                'TURNO_EXTENDIDO': '⏰ Turno Extendido'
            }
            alertas_tipo['Tipo_Display'] = alertas_tipo['Tipo'].map(nombres_alertas).fillna(alertas_tipo['Tipo'])
            
            fig_alertas = px.bar(
                alertas_tipo,
                y='Tipo_Display',
                x='Cantidad',
                orientation='h',
                color='Cantidad',
                color_continuous_scale='Reds',
                text='Cantidad'
            )
            fig_alertas.update_traces(textposition='outside')
            fig_alertas.update_layout(
                height=350,
                margin=dict(t=30, b=30, l=150),
                showlegend=False,
                coloraxis_showscale=False,
                yaxis=dict(title=""),
                xaxis=dict(title="Cantidad de Alertas")
            )
            st.plotly_chart(fig_alertas, use_container_width=True)
        else:
            st.success("✅ No hay alertas activas")
    
    st.markdown("---")
    
    # ===== FILA 3: Tendencia de Fatiga en las últimas 24 horas =====
    st.subheader("📉 Tendencia de Fatiga Promedio (Últimas 24 horas)")
    
    try:
        fecha_inicio_tendencia = (datetime.now() - timedelta(hours=24)).isoformat()
        response_metricas = supabase.table('metricas_procesadas')\
            .select('timestamp, indice_fatiga')\
            .gte('timestamp', fecha_inicio_tendencia)\
            .order('timestamp')\
            .execute()
        
        if response_metricas.data:
            df_tendencia = pd.DataFrame(response_metricas.data)
            df_tendencia['timestamp'] = pd.to_datetime(df_tendencia['timestamp'])
            
            # Agrupar por hora
            df_tendencia['hora'] = df_tendencia['timestamp'].dt.floor('H')
            tendencia_hora = df_tendencia.groupby('hora')['indice_fatiga'].mean().reset_index()
            
            fig_tendencia = go.Figure()
            
            # Área de fondo para zonas de riesgo
            fig_tendencia.add_hrect(y0=0, y1=40, fillcolor="rgba(76, 175, 80, 0.1)", line_width=0)
            fig_tendencia.add_hrect(y0=40, y1=70, fillcolor="rgba(255, 193, 7, 0.1)", line_width=0)
            fig_tendencia.add_hrect(y0=70, y1=85, fillcolor="rgba(255, 152, 0, 0.1)", line_width=0)
            fig_tendencia.add_hrect(y0=85, y1=100, fillcolor="rgba(244, 67, 54, 0.1)", line_width=0)
            
            # Línea de tendencia
            fig_tendencia.add_trace(go.Scatter(
                x=tendencia_hora['hora'],
                y=tendencia_hora['indice_fatiga'],
                mode='lines+markers',
                name='Índice Promedio',
                line=dict(color='#1f77b4', width=3),
                marker=dict(size=8),
                fill='tozeroy',
                fillcolor='rgba(31, 119, 180, 0.2)'
            ))
            
            fig_tendencia.update_layout(
                height=350,
                margin=dict(t=30, b=30),
                xaxis=dict(title="Hora", tickformat="%H:%M"),
                yaxis=dict(range=[0, 100], title="Índice de Fatiga Promedio"),
                hovermode='x unified'
            )
            
            # Líneas de umbral
            fig_tendencia.add_hline(y=70, line_dash="dash", line_color="orange", annotation_text="Umbral Alto")
            fig_tendencia.add_hline(y=85, line_dash="dash", line_color="red", annotation_text="Umbral Crítico")
            
            st.plotly_chart(fig_tendencia, use_container_width=True)
        else:
            st.info("📊 No hay datos de métricas en las últimas 24 horas. Envíe datos desde la sección de Ingesta.")
    except Exception as e:
        st.warning(f"No se pudo cargar la tendencia de fatiga: {e}")
    
    st.markdown("---")
    
    # ===== FILA 4: Mapa de la flota =====
    st.subheader("📍 Mapa de Estado de la Flota")
    if not df_operadores.empty:
        fig_mapa = crear_mapa_flota(df_operadores)
        st.plotly_chart(fig_mapa, use_container_width=True)
        
        # Tabla de operadores
        st.subheader("👷 Estado Detallado de Operadores")
        
        # Preparar columnas para mostrar
        display_cols = ['codigo_operador', 'nombre_completo']
        if 'turno_asignado' in df_operadores.columns:
            display_cols.append('turno_asignado')
        if 'indice_fatiga_actual' in df_operadores.columns:
            display_cols.append('indice_fatiga_actual')
        if 'clasificacion_riesgo' in df_operadores.columns:
            display_cols.append('clasificacion_riesgo')
        if 'alertas_activas' in df_operadores.columns:
            display_cols.append('alertas_activas')
        
        available_cols = [col for col in display_cols if col in df_operadores.columns]
        df_display = df_operadores[available_cols].copy()
        
        # Renombrar columnas según las disponibles
        column_names = {
            'codigo_operador': 'Código',
            'nombre_completo': 'Nombre',
            'turno_asignado': 'Turno',
            'indice_fatiga_actual': 'Índice Fatiga',
            'clasificacion_riesgo': 'Riesgo',
            'alertas_activas': 'Alertas'
        }
        df_display.columns = [column_names.get(col, col) for col in df_display.columns]
        
        st.dataframe(df_display, use_container_width=True, height=400)
    else:
        st.info("No hay operadores activos en este momento")
    
    st.markdown("---")
    
    # Sección de generación de reportes
    st.subheader("📊 Generador de Reportes")
    
    col_rep1, col_rep2, col_rep3 = st.columns([2, 2, 1])
    
    with col_rep1:
        tipo_reporte = st.selectbox(
            "Tipo de Reporte",
            ["DIARIO", "SEMANAL", "MENSUAL", "PERSONALIZADO"]
        )
    
    with col_rep2:
        if tipo_reporte == "PERSONALIZADO":
            fecha_inicio = st.date_input("Fecha Inicio", datetime.now() - timedelta(days=7))
            fecha_fin = st.date_input("Fecha Fin", datetime.now())
        elif tipo_reporte == "DIARIO":
            fecha_inicio = datetime.now().replace(hour=0, minute=0, second=0)
            fecha_fin = datetime.now()
        elif tipo_reporte == "SEMANAL":
            fecha_inicio = datetime.now() - timedelta(days=7)
            fecha_fin = datetime.now()
        else:  # MENSUAL
            fecha_inicio = datetime.now() - timedelta(days=30)
            fecha_fin = datetime.now()
    
    with col_rep3:
        if st.button("🔄 Generar Reporte", type="primary"):
            with st.spinner("Generando reporte PDF..."):
                try:
                    pdf_buffer, nombre_archivo_generado = generar_reporte_pdf(fecha_inicio, fecha_fin, tipo_reporte)
                    st.success("✅ Reporte generado exitosamente")
                    st.download_button(
                        label="📥 Descargar Reporte PDF",
                        data=pdf_buffer,
                        file_name=nombre_archivo_generado,
                        mime="application/pdf"
                    )
                except Exception as e:
                    st.error(f"Error al generar reporte: {e}")

# ============================================
# PANEL SUPERVISOR DE TURNO - MEJORADO
# ============================================

def panel_supervisor():
    st.markdown('<p class="main-header">👨‍💼 Vista de Supervisor de Turno</p>', 
                unsafe_allow_html=True)
    
    # ===== SECCIÓN 1: RESUMEN GENERAL =====
    st.subheader("📊 Resumen del Turno Actual")
    
    # Cargar datos
    df_operadores = cargar_operadores_activos()
    df_alertas = cargar_alertas_activas()
    
    # KPIs del turno
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_operadores = len(df_operadores) if not df_operadores.empty else 0
        st.metric("👷 Operadores Activos", total_operadores)
    
    with col2:
        alertas_activas = len(df_alertas) if not df_alertas.empty else 0
        st.metric("🚨 Alertas Activas", alertas_activas, delta_color="inverse")
    
    with col3:
        alertas_criticas = len(df_alertas[df_alertas['nivel_alerta'] == 'CRITICO']) if not df_alertas.empty else 0
        st.metric("⚠️ Alertas Críticas", alertas_criticas, delta_color="inverse")
    
    with col4:
        # Cargar turnos en curso
        try:
            resp_turnos = supabase.table('turnos').select('id').eq('estado', 'EN_CURSO').execute()
            turnos_activos = len(resp_turnos.data) if resp_turnos.data else 0
        except:
            turnos_activos = 0
        st.metric("🕐 Turnos en Curso", turnos_activos)
    
    st.markdown("---")
    
    # ===== SECCIÓN 2: ALERTAS ACTIVAS =====
    st.subheader("🚨 Alertas Activas")
    
    if not df_alertas.empty:
        # Ordenar por nivel de alerta (crítico primero)
        orden_alertas = {'CRITICO': 0, 'URGENTE': 1, 'ATENCION': 2, 'INFO': 3}
        df_alertas['orden'] = df_alertas['nivel_alerta'].map(orden_alertas)
        df_alertas = df_alertas.sort_values('orden')
        
        for idx, alerta in df_alertas.iterrows():
            nivel_color = {
                'CRITICO': 'alert-critical',
                'URGENTE': 'alert-high',
                'ATENCION': 'alert-medium',
                'INFO': 'alert-medium'
            }.get(alerta['nivel_alerta'], 'alert-medium')
            
            icono_alerta = {
                'CRITICO': '🔴',
                'URGENTE': '🟠',
                'ATENCION': '🟡',
                'INFO': '🔵'
            }.get(alerta['nivel_alerta'], '⚪')
            
            with st.expander(
                f"{icono_alerta} [{alerta['nivel_alerta']}] {alerta['titulo']}", 
                expanded=(alerta['nivel_alerta'] == 'CRITICO')
            ):
                st.markdown(f"<div class='{nivel_color}'>{alerta.get('descripcion', 'Sin descripción')}</div>", 
                           unsafe_allow_html=True)
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    operador_display = alerta.get('operador_nombre', alerta.get('operador_codigo', 'N/A'))
                    st.write(f"**Operador:** {operador_display}")
                with col2:
                    indice = alerta.get('indice_fatiga_actual')
                    st.write(f"**Índice Fatiga:** {indice if indice else 'N/A'}")
                with col3:
                    st.write(f"**Hora:** {pd.to_datetime(alerta['timestamp']).strftime('%d/%m %H:%M')}")
                
                st.markdown("---")
                col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)
                
                with col_btn1:
                    if st.button("✅ Reconocer", key=f"reconocer_{alerta['id']}"):
                        gestionar_alerta(alerta['id'], 'reconocer')
                
                with col_btn2:
                    if st.button("🔧 Gestionar", key=f"gestionar_{alerta['id']}"):
                        gestionar_alerta(alerta['id'], 'gestionar')
                
                with col_btn3:
                    if st.button("✔️ Resolver", key=f"resolver_{alerta['id']}"):
                        gestionar_alerta(alerta['id'], 'resolver', "Resuelto por supervisor")
                
                with col_btn4:
                    if st.button("🚫 Ignorar", key=f"ignorar_{alerta['id']}"):
                        gestionar_alerta(alerta['id'], 'ignorar')
    else:
        st.success("✅ No hay alertas activas en este momento")
    
    st.markdown("---")
    
    # ===== SECCIÓN 3: OPERADORES Y TURNOS =====
    st.subheader("👷 Operadores y Turnos")
    
    # Crear tabs para diferentes acciones
    tab_operadores, tab_crear_turno = st.tabs(["📋 Estado de Operadores", "➕ Iniciar Turno"])
    
    with tab_operadores:
        if not df_operadores.empty:
            # Cargar turnos activos para cada operador
            try:
                resp_turnos = supabase.table('turnos')\
                    .select('id, id_operador, tipo_turno, fecha_inicio, maquinaria_asignada, ubicacion')\
                    .eq('estado', 'EN_CURSO')\
                    .execute()
                
                turnos_map = {}
                if resp_turnos.data:
                    for t in resp_turnos.data:
                        turnos_map[t['id_operador']] = t
            except:
                turnos_map = {}
            
            for idx, operador in df_operadores.iterrows():
                turno_actual = turnos_map.get(operador['id'])
                
                with st.container():
                    col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 2, 1])
                    
                    with col1:
                        st.write(f"**{operador.get('nombre_completo', operador.get('nombre', 'N/A'))}**")
                        st.caption(f"Código: {operador.get('codigo_operador', 'N/A')}")
                    
                    with col2:
                        indice = operador.get('indice_fatiga_actual')
                        if indice and indice > 0:
                            st.metric("Fatiga", f"{indice:.1f}")
                        else:
                            st.metric("Fatiga", "Sin datos")
                    
                    with col3:
                        riesgo = operador.get('clasificacion_riesgo', 'SIN DATOS')
                        color_class = {
                            'BAJO': 'status-ok',
                            'MEDIO': 'status-warning',
                            'ALTO': 'status-danger',
                            'CRITICO': 'status-danger'
                        }.get(riesgo, '')
                        st.markdown(f"<p class='{color_class}'><b>{riesgo}</b></p>", unsafe_allow_html=True)
                    
                    with col4:
                        if turno_actual:
                            horas = (datetime.now(timezone.utc) - pd.to_datetime(turno_actual['fecha_inicio'])).total_seconds() / 3600
                            st.write(f"🕐 **En turno**")
                            st.caption(f"{turno_actual['tipo_turno']} - {horas:.1f}h")
                        else:
                            st.write("⚪ **Sin turno**")
                    
                    with col5:
                        if st.button("📊", key=f"detalle_{operador['id']}", help="Ver detalle"):
                            st.session_state['operador_seleccionado'] = operador['id']
                            st.session_state['ver_detalle'] = True
                            st.rerun()
                    
                    st.markdown("---")
            
            # Vista detallada de operador seleccionado
            if st.session_state.get('ver_detalle', False):
                st.markdown("---")
                st.subheader("📈 Vista Detallada de Operador")
                
                operador_id = st.session_state['operador_seleccionado']
                operador_info = df_operadores[df_operadores['id'] == operador_id]
                
                if not operador_info.empty:
                    operador_info = operador_info.iloc[0]
                    
                    col_close, col_title = st.columns([1, 10])
                    with col_close:
                        if st.button("❌ Cerrar"):
                            st.session_state['ver_detalle'] = False
                            st.rerun()
                    with col_title:
                        st.write(f"### {operador_info.get('nombre_completo', 'Operador')}")
                    
                    # Gauge de fatiga actual
                    col_g1, col_g2 = st.columns(2)
                    
                    with col_g1:
                        fig_gauge = crear_gauge_fatiga(
                            operador_info.get('indice_fatiga_actual', 0) or 0,
                            "Índice de Fatiga Actual"
                        )
                        st.plotly_chart(fig_gauge, use_container_width=True)
                    
                    with col_g2:
                        st.write("**Información del Operador:**")
                        st.write(f"- **Código:** {operador_info.get('codigo_operador', 'N/A')}")
                        st.write(f"- **Turno Asignado:** {operador_info.get('turno_asignado', 'N/A')}")
                        
                        ultima_med = operador_info.get('ultima_medicion')
                        if ultima_med:
                            st.write(f"- **Última medición:** {pd.to_datetime(ultima_med).strftime('%d/%m/%Y %H:%M:%S')}")
                        else:
                            st.write("- **Última medición:** Sin datos")
                        
                        alertas_op = operador_info.get('alertas_activas', 0)
                        st.write(f"- **Alertas activas:** {int(alertas_op) if alertas_op else 0}")
        else:
            st.info("No hay operadores activos en el sistema. Agregue operadores desde el panel de **📋 Mantenedores**.")
    
    with tab_crear_turno:
        st.subheader("➕ Iniciar Nuevo Turno")
        st.write("Cree un turno para un operador que aún no tiene turno activo.")
        
        try:
            # Cargar operadores sin turno activo
            resp_ops = supabase.table('operadores')\
                .select('id, codigo_operador, nombre, apellido')\
                .eq('estado', 'ACTIVO')\
                .execute()
            
            resp_turnos = supabase.table('turnos')\
                .select('id_operador')\
                .eq('estado', 'EN_CURSO')\
                .execute()
            
            operadores_con_turno = [t['id_operador'] for t in resp_turnos.data] if resp_turnos.data else []
            
            operadores_sin_turno = [
                op for op in resp_ops.data 
                if op['id'] not in operadores_con_turno
            ] if resp_ops.data else []
            
            if operadores_sin_turno:
                with st.form("form_crear_turno"):
                    ops_map = {
                        f"{op['nombre']} {op['apellido']} ({op['codigo_operador']})": op['id']
                        for op in operadores_sin_turno
                    }
                    
                    operador_turno = st.selectbox("👷 Seleccionar Operador", options=list(ops_map.keys()))
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        tipo_turno = st.selectbox("Tipo de Turno", ["DIA", "NOCHE", "EXTRA"])
                        maquinaria = st.text_input("Maquinaria Asignada (opcional)")
                    with col2:
                        ubicacion = st.text_input("Ubicación (opcional)")
                    
                    submitted = st.form_submit_button("🚀 Iniciar Turno", type="primary", use_container_width=True)
                    
                    if submitted:
                        try:
                            nuevo_turno = {
                                'id_operador': ops_map[operador_turno],
                                'fecha_inicio': datetime.now().isoformat(),
                                'tipo_turno': tipo_turno,
                                'maquinaria_asignada': maquinaria if maquinaria else None,
                                'ubicacion': ubicacion if ubicacion else None,
                                'estado': 'EN_CURSO'
                            }
                            
                            supabase.table('turnos').insert(nuevo_turno).execute()
                            st.success(f"✅ Turno iniciado para {operador_turno}")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error al crear turno: {e}")
            else:
                if resp_ops.data:
                    st.success("✅ Todos los operadores ya tienen un turno activo")
                else:
                    st.warning("⚠️ No hay operadores activos. Cree operadores desde el panel de **📋 Mantenedores**.")
                    
        except Exception as e:
            st.error(f"Error al cargar datos: {e}")

# ============================================
# PANEL MANTENEDORES - CRUD OPERADORES Y DISPOSITIVOS
# ============================================

def panel_mantenedores():
    st.markdown('<p class="main-header">📋 Mantenedores del Sistema</p>', 
                unsafe_allow_html=True)
    
    tab_ops, tab_disp = st.tabs(["👷 Operadores", "📱 Dispositivos"])
    
    # =============================================
    # TAB OPERADORES - CRUD COMPLETO
    # =============================================
    with tab_ops:
        st.subheader("👷 Gestión de Operadores")
        
        # Filtros
        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        with col_f1:
            filtro_estado = st.selectbox("Estado", ["TODOS", "ACTIVO", "INACTIVO", "LICENCIA", "SUSPENDIDO"], key="filtro_estado_op")
        with col_f2:
            filtro_turno = st.selectbox("Turno", ["TODOS", "DIA", "NOCHE", "ROTATIVO", "FLEXIBLE"], key="filtro_turno_op")
        with col_f3:
            filtro_experiencia = st.selectbox("Experiencia", ["TODOS", "NOVATO", "INTERMEDIO", "EXPERTO"], key="filtro_exp_op")
        with col_f4:
            buscar_nombre = st.text_input("🔍 Buscar por nombre/código", key="buscar_op")
        
        try:
            # Cargar operadores con filtros
            query = supabase.table('operadores').select('*')
            
            if filtro_estado != "TODOS":
                query = query.eq('estado', filtro_estado)
            if filtro_turno != "TODOS":
                query = query.eq('turno_asignado', filtro_turno)
            if filtro_experiencia != "TODOS":
                query = query.eq('nivel_experiencia', filtro_experiencia)
            
            response = query.order('created_at', desc=True).execute()
            df_operadores = pd.DataFrame(response.data) if response.data else pd.DataFrame()
            
            # Filtrar por búsqueda de texto
            if buscar_nombre and not df_operadores.empty:
                mask = (
                    df_operadores['nombre'].str.contains(buscar_nombre, case=False, na=False) |
                    df_operadores['apellido'].str.contains(buscar_nombre, case=False, na=False) |
                    df_operadores['codigo_operador'].str.contains(buscar_nombre, case=False, na=False)
                )
                df_operadores = df_operadores[mask]
            
            # Mostrar estadísticas
            if not df_operadores.empty:
                col_st1, col_st2, col_st3, col_st4 = st.columns(4)
                with col_st1:
                    st.metric("Total Operadores", len(df_operadores))
                with col_st2:
                    activos = len(df_operadores[df_operadores['estado'] == 'ACTIVO'])
                    st.metric("Activos", activos)
                with col_st3:
                    turno_dia = len(df_operadores[df_operadores['turno_asignado'] == 'DIA'])
                    st.metric("Turno Día", turno_dia)
                with col_st4:
                    turno_noche = len(df_operadores[df_operadores['turno_asignado'] == 'NOCHE'])
                    st.metric("Turno Noche", turno_noche)
            
            st.markdown("---")
            
            # Modo de operación: Ver/Editar/Crear
            modo_op = st.radio(
                "Acción:",
                ["📋 Ver Listado", "➕ Agregar Operador", "✏️ Editar Operador", "🗑️ Gestionar Estado"],
                horizontal=True,
                key="modo_operadores"
            )
            
            st.markdown("---")
            
            # ===== VER LISTADO =====
            if modo_op == "📋 Ver Listado":
                if not df_operadores.empty:
                    # Crear nombre completo
                    df_operadores['nombre_completo'] = df_operadores['nombre'] + ' ' + df_operadores['apellido']
                    
                    cols_mostrar = ['codigo_operador', 'nombre_completo', 'documento_identidad', 
                                   'turno_asignado', 'nivel_experiencia', 'estado', 'email', 'telefono']
                    cols_disponibles = [c for c in cols_mostrar if c in df_operadores.columns]
                    
                    st.dataframe(
                        df_operadores[cols_disponibles],
                        use_container_width=True,
                        height=400,
                        column_config={
                            "codigo_operador": "Código",
                            "nombre_completo": "Nombre Completo",
                            "documento_identidad": "Documento",
                            "turno_asignado": "Turno",
                            "nivel_experiencia": "Experiencia",
                            "estado": st.column_config.SelectboxColumn(
                                "Estado",
                                options=["ACTIVO", "INACTIVO", "LICENCIA", "SUSPENDIDO"],
                                disabled=True
                            ),
                            "email": "Email",
                            "telefono": "Teléfono"
                        }
                    )
                else:
                    st.info("No se encontraron operadores con los filtros seleccionados")
            
            # ===== AGREGAR OPERADOR =====
            elif modo_op == "➕ Agregar Operador":
                st.subheader("Nuevo Operador")
                
                with st.form("form_crear_operador", clear_on_submit=True):
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.markdown("**Datos Personales**")
                        codigo = st.text_input("Código de Operador*", max_chars=20)
                        nombre = st.text_input("Nombre*", max_chars=100)
                        apellido = st.text_input("Apellido*", max_chars=100)
                        documento = st.text_input("Documento de Identidad*", max_chars=20)
                        fecha_nac = st.date_input("Fecha de Nacimiento", value=None)
                    
                    with col2:
                        st.markdown("**Datos Laborales**")
                        turno = st.selectbox("Turno Asignado*", ["DIA", "NOCHE", "ROTATIVO", "FLEXIBLE"])
                        experiencia = st.selectbox("Nivel de Experiencia*", ["NOVATO", "INTERMEDIO", "EXPERTO"])
                        licencia = st.text_input("Tipo de Licencia")
                        area = st.text_input("Área de Trabajo")
                        fecha_contrato = st.date_input("Fecha de Contratación", value=None)
                    
                    with col3:
                        st.markdown("**Contacto**")
                        email = st.text_input("Email")
                        telefono = st.text_input("Teléfono")
                        perfil_riesgo = st.selectbox("Perfil de Riesgo Inicial", ["BAJO", "MEDIO", "ALTO"])
                        
                        st.markdown("**Contacto de Emergencia**")
                        nombre_emergencia = st.text_input("Nombre Contacto")
                        telefono_emergencia = st.text_input("Teléfono Emergencia")
                    
                    submitted = st.form_submit_button("💾 Guardar Operador", type="primary", use_container_width=True)
                    
                    if submitted:
                        if codigo and nombre and apellido and documento:
                            try:
                                contacto_emergencia = None
                                if nombre_emergencia or telefono_emergencia:
                                    contacto_emergencia = {
                                        "nombre": nombre_emergencia,
                                        "telefono": telefono_emergencia
                                    }
                                
                                nuevo_operador = {
                                    'codigo_operador': codigo,
                                    'nombre': nombre,
                                    'apellido': apellido,
                                    'documento_identidad': documento,
                                    'fecha_nacimiento': fecha_nac.isoformat() if fecha_nac else None,
                                    'turno_asignado': turno,
                                    'tipo_licencia': licencia if licencia else None,
                                    'fecha_contratacion': fecha_contrato.isoformat() if fecha_contrato else None,
                                    'area_trabajo': area if area else None,
                                    'nivel_experiencia': experiencia,
                                    'email': email if email else None,
                                    'telefono': telefono if telefono else None,
                                    'perfil_riesgo': perfil_riesgo,
                                    'contacto_emergencia': contacto_emergencia,
                                    'estado': 'ACTIVO'
                                }
                                
                                supabase.table('operadores').insert(nuevo_operador).execute()
                                st.success("✅ Operador creado exitosamente")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error al crear operador: {e}")
                        else:
                            st.error("⚠️ Complete todos los campos obligatorios (*)")
            
            # ===== EDITAR OPERADOR =====
            elif modo_op == "✏️ Editar Operador":
                if not df_operadores.empty:
                    # Selector de operador
                    opciones_operadores = {
                        f"{row['codigo_operador']} - {row['nombre']} {row['apellido']}": row['id']
                        for _, row in df_operadores.iterrows()
                    }
                    
                    operador_seleccionado = st.selectbox(
                        "Seleccionar Operador a Editar",
                        options=list(opciones_operadores.keys()),
                        key="select_editar_op"
                    )
                    
                    if operador_seleccionado:
                        op_id = opciones_operadores[operador_seleccionado]
                        op_data = df_operadores[df_operadores['id'] == op_id].iloc[0]
                        
                        with st.form("form_editar_operador"):
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                st.markdown("**Datos Personales**")
                                nombre_edit = st.text_input("Nombre*", value=op_data['nombre'])
                                apellido_edit = st.text_input("Apellido*", value=op_data['apellido'])
                                fecha_nac_edit = st.date_input(
                                    "Fecha de Nacimiento",
                                    value=pd.to_datetime(op_data['fecha_nacimiento']).date() if op_data.get('fecha_nacimiento') else None
                                )
                            
                            with col2:
                                st.markdown("**Datos Laborales**")
                                turno_idx = ["DIA", "NOCHE", "ROTATIVO", "FLEXIBLE"].index(op_data.get('turno_asignado', 'DIA'))
                                turno_edit = st.selectbox("Turno Asignado", ["DIA", "NOCHE", "ROTATIVO", "FLEXIBLE"], index=turno_idx)
                                
                                exp_idx = ["NOVATO", "INTERMEDIO", "EXPERTO"].index(op_data.get('nivel_experiencia', 'NOVATO'))
                                experiencia_edit = st.selectbox("Nivel de Experiencia", ["NOVATO", "INTERMEDIO", "EXPERTO"], index=exp_idx)
                                
                                licencia_edit = st.text_input("Tipo de Licencia", value=op_data.get('tipo_licencia') or '')
                                area_edit = st.text_input("Área de Trabajo", value=op_data.get('area_trabajo') or '')
                            
                            with col3:
                                st.markdown("**Contacto**")
                                email_edit = st.text_input("Email", value=op_data.get('email') or '')
                                telefono_edit = st.text_input("Teléfono", value=op_data.get('telefono') or '')
                                
                                riesgo_idx = ["BAJO", "MEDIO", "ALTO"].index(op_data.get('perfil_riesgo', 'MEDIO'))
                                perfil_riesgo_edit = st.selectbox("Perfil de Riesgo", ["BAJO", "MEDIO", "ALTO"], index=riesgo_idx)
                            
                            submitted_edit = st.form_submit_button("💾 Actualizar Operador", type="primary", use_container_width=True)
                            
                            if submitted_edit:
                                try:
                                    update_data = {
                                        'nombre': nombre_edit,
                                        'apellido': apellido_edit,
                                        'fecha_nacimiento': fecha_nac_edit.isoformat() if fecha_nac_edit else None,
                                        'turno_asignado': turno_edit,
                                        'nivel_experiencia': experiencia_edit,
                                        'tipo_licencia': licencia_edit if licencia_edit else None,
                                        'area_trabajo': area_edit if area_edit else None,
                                        'email': email_edit if email_edit else None,
                                        'telefono': telefono_edit if telefono_edit else None,
                                        'perfil_riesgo': perfil_riesgo_edit
                                    }
                                    
                                    supabase.table('operadores').update(update_data).eq('id', op_id).execute()
                                    st.success("✅ Operador actualizado exitosamente")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error al actualizar: {e}")
                else:
                    st.warning("No hay operadores disponibles para editar")
            
            # ===== GESTIONAR ESTADO =====
            elif modo_op == "🗑️ Gestionar Estado":
                if not df_operadores.empty:
                    st.warning("⚠️ Cambiar el estado de un operador afecta su disponibilidad en el sistema")
                    
                    opciones = {
                        f"{row['codigo_operador']} - {row['nombre']} {row['apellido']} ({row['estado']})": row['id']
                        for _, row in df_operadores.iterrows()
                    }
                    
                    op_seleccionado = st.selectbox("Seleccionar Operador", options=list(opciones.keys()))
                    
                    if op_seleccionado:
                        op_id = opciones[op_seleccionado]
                        op_actual = df_operadores[df_operadores['id'] == op_id].iloc[0]
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.info(f"**Estado Actual:** {op_actual['estado']}")
                            nuevo_estado = st.selectbox(
                                "Cambiar Estado a:",
                                ["ACTIVO", "INACTIVO", "LICENCIA", "SUSPENDIDO"],
                                index=["ACTIVO", "INACTIVO", "LICENCIA", "SUSPENDIDO"].index(op_actual['estado'])
                            )
                        
                        with col2:
                            if nuevo_estado != op_actual['estado']:
                                if st.button("🔄 Cambiar Estado", type="primary"):
                                    try:
                                        supabase.table('operadores').update({'estado': nuevo_estado}).eq('id', op_id).execute()
                                        st.success(f"✅ Estado cambiado a {nuevo_estado}")
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"❌ Error: {e}")
                else:
                    st.warning("No hay operadores disponibles")
                    
        except Exception as e:
            st.error(f"Error al cargar operadores: {e}")
    
    # =============================================
    # TAB DISPOSITIVOS - CRUD COMPLETO
    # =============================================
    with tab_disp:
        st.subheader("📱 Gestión de Dispositivos IoT")
        
        # Filtros
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            filtro_tipo_disp = st.selectbox("Tipo", ["TODOS", "SMARTWATCH", "BANDA_ANTIFATIGA", "TELEMATICA"], key="filtro_tipo_disp")
        with col_f2:
            filtro_estado_disp = st.selectbox("Estado", ["TODOS", "ACTIVO", "INACTIVO", "MANTENIMIENTO", "DESHABILITADO"], key="filtro_estado_disp")
        with col_f3:
            buscar_disp = st.text_input("🔍 Buscar por ID/Marca/Modelo", key="buscar_disp")
        
        try:
            query = supabase.table('dispositivos').select('*, operadores(nombre, apellido, codigo_operador)')
            
            if filtro_tipo_disp != "TODOS":
                query = query.eq('tipo_dispositivo', filtro_tipo_disp)
            if filtro_estado_disp != "TODOS":
                query = query.eq('estado', filtro_estado_disp)
            
            response = query.order('created_at', desc=True).execute()
            df_dispositivos = pd.DataFrame(response.data) if response.data else pd.DataFrame()
            
            # Filtrar por búsqueda
            if buscar_disp and not df_dispositivos.empty:
                mask = (
                    df_dispositivos['id_dispositivo_externo'].str.contains(buscar_disp, case=False, na=False) |
                    df_dispositivos['marca'].str.contains(buscar_disp, case=False, na=False) |
                    df_dispositivos['modelo'].str.contains(buscar_disp, case=False, na=False)
                )
                df_dispositivos = df_dispositivos[mask]
            
            # Estadísticas
            if not df_dispositivos.empty:
                col_st1, col_st2, col_st3, col_st4 = st.columns(4)
                with col_st1:
                    st.metric("Total Dispositivos", len(df_dispositivos))
                with col_st2:
                    activos_disp = len(df_dispositivos[df_dispositivos['estado'] == 'ACTIVO'])
                    st.metric("Activos", activos_disp)
                with col_st3:
                    asignados = len(df_dispositivos[df_dispositivos['id_operador_asignado'].notna()])
                    st.metric("Asignados", asignados)
                with col_st4:
                    en_mant = len(df_dispositivos[df_dispositivos['estado'] == 'MANTENIMIENTO'])
                    st.metric("En Mantenimiento", en_mant)
            
            st.markdown("---")
            
            modo_disp = st.radio(
                "Acción:",
                ["📋 Ver Listado", "➕ Agregar Dispositivo", "✏️ Editar Dispositivo", "🔗 Asignar a Operador"],
                horizontal=True,
                key="modo_dispositivos"
            )
            
            st.markdown("---")
            
            # ===== VER LISTADO DISPOSITIVOS =====
            if modo_disp == "📋 Ver Listado":
                if not df_dispositivos.empty:
                    df_display = df_dispositivos.copy()
                    if 'operadores' in df_display.columns:
                        df_display['operador_asignado'] = df_display['operadores'].apply(
                            lambda x: f"{x['codigo_operador']} - {x['nombre']} {x['apellido']}" if x else 'Sin asignar'
                        )
                    
                    cols_mostrar = ['id_dispositivo_externo', 'tipo_dispositivo', 'marca', 'modelo',
                                   'estado', 'operador_asignado', 'nivel_bateria', 'ultima_sincronizacion']
                    cols_disponibles = [c for c in cols_mostrar if c in df_display.columns]
                    
                    st.dataframe(
                        df_display[cols_disponibles],
                        use_container_width=True,
                        height=400,
                        column_config={
                            "id_dispositivo_externo": "ID Dispositivo",
                            "tipo_dispositivo": "Tipo",
                            "marca": "Marca",
                            "modelo": "Modelo",
                            "estado": st.column_config.SelectboxColumn(
                                "Estado",
                                options=["ACTIVO", "INACTIVO", "MANTENIMIENTO", "DESHABILITADO"],
                                disabled=True
                            ),
                            "operador_asignado": "Operador Asignado",
                            "nivel_bateria": st.column_config.ProgressColumn(
                                "Batería",
                                min_value=0,
                                max_value=100,
                                format="%d%%"
                            ),
                            "ultima_sincronizacion": "Última Sincronización"
                        }
                    )
                else:
                    st.info("No se encontraron dispositivos con los filtros seleccionados")
            
            # ===== AGREGAR DISPOSITIVO =====
            elif modo_disp == "➕ Agregar Dispositivo":
                st.subheader("Nuevo Dispositivo")
                
                with st.form("form_crear_dispositivo", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("**Información del Dispositivo**")
                        id_externo = st.text_input("ID del Dispositivo*", max_chars=100)
                        tipo_disp = st.selectbox("Tipo de Dispositivo*", ["SMARTWATCH", "BANDA_ANTIFATIGA", "TELEMATICA"])
                        marca = st.text_input("Marca")
                        modelo = st.text_input("Modelo")
                        version_fw = st.text_input("Versión de Firmware")
                    
                    with col2:
                        st.markdown("**Configuración**")
                        freq_muestreo = st.number_input("Frecuencia de Muestreo (seg)", min_value=1, value=60)
                        nivel_bateria = st.slider("Nivel de Batería (%)", min_value=0, max_value=100, value=100)
                        
                        # Operador a asignar
                        resp_ops = supabase.table('operadores').select('id, nombre, apellido, codigo_operador').eq('estado', 'ACTIVO').execute()
                        if resp_ops.data:
                            ops_disponibles = {
                                f"{op['codigo_operador']} - {op['nombre']} {op['apellido']}": op['id']
                                for op in resp_ops.data
                            }
                            operador_asignar = st.selectbox("Asignar a Operador", ["Sin asignar"] + list(ops_disponibles.keys()))
                        else:
                            operador_asignar = "Sin asignar"
                            ops_disponibles = {}
                            st.warning("No hay operadores activos")
                    
                    submitted_disp = st.form_submit_button("💾 Guardar Dispositivo", type="primary", use_container_width=True)
                    
                    if submitted_disp:
                        if id_externo and tipo_disp:
                            try:
                                nuevo_disp = {
                                    'id_dispositivo_externo': id_externo,
                                    'tipo_dispositivo': tipo_disp,
                                    'marca': marca if marca else None,
                                    'modelo': modelo if modelo else None,
                                    'version_firmware': version_fw if version_fw else None,
                                    'frecuencia_muestreo': freq_muestreo,
                                    'nivel_bateria': nivel_bateria,
                                    'estado': 'ACTIVO'
                                }
                                
                                if operador_asignar != "Sin asignar":
                                    nuevo_disp['id_operador_asignado'] = ops_disponibles[operador_asignar]
                                    nuevo_disp['fecha_asignacion'] = datetime.now().isoformat()
                                
                                supabase.table('dispositivos').insert(nuevo_disp).execute()
                                st.success("✅ Dispositivo registrado exitosamente")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error al registrar dispositivo: {e}")
                        else:
                            st.error("⚠️ Complete los campos obligatorios (*)")
            
            # ===== EDITAR DISPOSITIVO =====
            elif modo_disp == "✏️ Editar Dispositivo":
                if not df_dispositivos.empty:
                    opciones_disp = {
                        f"{row['id_dispositivo_externo']} ({row['tipo_dispositivo']})": row['id']
                        for _, row in df_dispositivos.iterrows()
                    }
                    
                    disp_seleccionado = st.selectbox("Seleccionar Dispositivo", options=list(opciones_disp.keys()))
                    
                    if disp_seleccionado:
                        disp_id = opciones_disp[disp_seleccionado]
                        disp_data = df_dispositivos[df_dispositivos['id'] == disp_id].iloc[0]
                        
                        with st.form("form_editar_dispositivo"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                marca_edit = st.text_input("Marca", value=disp_data.get('marca') or '')
                                modelo_edit = st.text_input("Modelo", value=disp_data.get('modelo') or '')
                                version_fw_edit = st.text_input("Versión Firmware", value=disp_data.get('version_firmware') or '')
                            
                            with col2:
                                freq_edit = st.number_input("Frecuencia Muestreo (seg)", value=disp_data.get('frecuencia_muestreo') or 60)
                                estado_idx = ["ACTIVO", "INACTIVO", "MANTENIMIENTO", "DESHABILITADO"].index(disp_data.get('estado', 'ACTIVO'))
                                estado_edit = st.selectbox("Estado", ["ACTIVO", "INACTIVO", "MANTENIMIENTO", "DESHABILITADO"], index=estado_idx)
                                bateria_edit = st.slider("Nivel Batería (%)", 0, 100, value=int(disp_data.get('nivel_bateria') or 100))
                            
                            submitted_edit_disp = st.form_submit_button("💾 Actualizar Dispositivo", type="primary", use_container_width=True)
                            
                            if submitted_edit_disp:
                                try:
                                    update_data = {
                                        'marca': marca_edit if marca_edit else None,
                                        'modelo': modelo_edit if modelo_edit else None,
                                        'version_firmware': version_fw_edit if version_fw_edit else None,
                                        'frecuencia_muestreo': freq_edit,
                                        'estado': estado_edit,
                                        'nivel_bateria': bateria_edit
                                    }
                                    
                                    supabase.table('dispositivos').update(update_data).eq('id', disp_id).execute()
                                    st.success("✅ Dispositivo actualizado")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error: {e}")
                else:
                    st.warning("No hay dispositivos disponibles")
            
            # ===== ASIGNAR A OPERADOR =====
            elif modo_disp == "🔗 Asignar a Operador":
                if not df_dispositivos.empty:
                    st.info("Gestione la asignación de dispositivos a operadores")
                    
                    opciones_disp = {
                        f"{row['id_dispositivo_externo']} ({row['tipo_dispositivo']})": row['id']
                        for _, row in df_dispositivos.iterrows()
                    }
                    
                    disp_sel = st.selectbox("Seleccionar Dispositivo", options=list(opciones_disp.keys()), key="asig_disp")
                    
                    if disp_sel:
                        disp_id = opciones_disp[disp_sel]
                        disp_data = df_dispositivos[df_dispositivos['id'] == disp_id].iloc[0]
                        
                        # Mostrar asignación actual
                        operador_actual = disp_data.get('operadores')
                        if operador_actual:
                            st.warning(f"📌 Actualmente asignado a: **{operador_actual['codigo_operador']} - {operador_actual['nombre']} {operador_actual['apellido']}**")
                        else:
                            st.info("📌 Dispositivo no asignado")
                        
                        # Cargar operadores disponibles
                        resp_ops = supabase.table('operadores').select('id, nombre, apellido, codigo_operador').eq('estado', 'ACTIVO').execute()
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            if resp_ops.data:
                                ops_map = {
                                    f"{op['codigo_operador']} - {op['nombre']} {op['apellido']}": op['id']
                                    for op in resp_ops.data
                                }
                                nuevo_operador = st.selectbox("Asignar a:", ["Sin asignar"] + list(ops_map.keys()))
                                
                                if st.button("🔗 Asignar", type="primary"):
                                    try:
                                        if nuevo_operador == "Sin asignar":
                                            supabase.table('dispositivos').update({
                                                'id_operador_asignado': None,
                                                'fecha_asignacion': None
                                            }).eq('id', disp_id).execute()
                                            st.success("✅ Dispositivo desasignado")
                                        else:
                                            supabase.table('dispositivos').update({
                                                'id_operador_asignado': ops_map[nuevo_operador],
                                                'fecha_asignacion': datetime.now().isoformat()
                                            }).eq('id', disp_id).execute()
                                            st.success(f"✅ Dispositivo asignado a {nuevo_operador}")
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"❌ Error: {e}")
                        
                        with col2:
                            if operador_actual:
                                if st.button("❌ Quitar Asignación", type="secondary"):
                                    try:
                                        supabase.table('dispositivos').update({
                                            'id_operador_asignado': None,
                                            'fecha_asignacion': None
                                        }).eq('id', disp_id).execute()
                                        st.success("✅ Asignación removida")
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"❌ Error: {e}")
                else:
                    st.warning("No hay dispositivos disponibles")
                    
        except Exception as e:
            st.error(f"Error al cargar dispositivos: {e}")


# ============================================
# PANEL CONFIGURACIÓN - CONFIGURACIÓN E INGESTA
# ============================================

def panel_configuracion():
    st.markdown('<p class="main-header">⚙️ Configuración del Sistema</p>', 
                unsafe_allow_html=True)
    
    # Tabs para Configuración e Ingesta
    tab_config, tab_ingesta = st.tabs(["⚙️ Parámetros del Sistema", "📤 Ingesta de Datos"])
    
    # TAB 1: Configuración del Sistema
    with tab_config:
        st.subheader("Configuración del Sistema")
        
        try:
            response = supabase.table('configuracion_sistema').select('*').execute()
            df_config = pd.DataFrame(response.data) if response.data else pd.DataFrame()
            
            if not df_config.empty:
                st.write("**Parámetros Configurables:**")
                
                for idx, config in df_config.iterrows():
                    if config['modificable']:
                        col1, col2, col3 = st.columns([3, 2, 1])
                        
                        with col1:
                            st.write(f"**{config['clave']}**")
                            st.caption(config['descripcion'])
                        
                        with col2:
                            valor_actual = config['valor']
                            
                            # Manejar diferentes tipos de valores
                            if config['tipo_dato'] == 'INTEGER':
                                try:
                                    nuevo_valor = st.number_input(
                                        f"Valor",
                                        value=int(valor_actual),
                                        key=f"config_{config['id']}"
                                    )
                                except:
                                    nuevo_valor = st.number_input(
                                        f"Valor",
                                        value=0,
                                        key=f"config_{config['id']}"
                                    )
                            elif config['tipo_dato'] == 'BOOLEAN':
                                nuevo_valor = st.checkbox(
                                    "Activado",
                                    value=(str(valor_actual).lower() == 'true'),
                                    key=f"config_{config['id']}"
                                )
                            else:
                                nuevo_valor = st.text_input(
                                    "Valor",
                                    value=str(valor_actual),
                                    key=f"config_{config['id']}"
                                )
                        
                        with col3:
                            if st.button("💾 Guardar", key=f"save_{config['id']}"):
                                try:
                                    supabase.table('configuracion_sistema').update({
                                        'valor': str(nuevo_valor)
                                    }).eq('id', config['id']).execute()
                                    st.success("✅ Guardado")
                                    st.cache_data.clear()
                                except Exception as e:
                                    st.error(f"❌ Error: {e}")
                        
                        st.markdown("---")
            else:
                st.info("No hay configuraciones disponibles")
                
        except Exception as e:
            st.error(f"Error al cargar configuración: {e}")
            
    # TAB 2: Ingesta Manual de Datos
    with tab_ingesta:
        st.subheader("📤 Ingesta de Datos de Fatiga")
        st.write("Envíe datos de dispositivos al sistema de procesamiento n8n.")
        
        st.markdown("---")
        
        # ===== PASO 1: Seleccionar Operador =====
        st.markdown("### 1️⃣ Seleccionar Operador")
        
        try:
            # Cargar operadores activos con dispositivos
            resp_operadores = supabase.table('operadores')\
                .select('id, codigo_operador, nombre, apellido')\
                .eq('estado', 'ACTIVO')\
                .order('nombre')\
                .execute()
            
            if resp_operadores.data:
                operadores_map = {
                    f"{op['nombre']} {op['apellido']} ({op['codigo_operador']})": {
                        'id': op['id'],
                        'codigo': op['codigo_operador']
                    }
                    for op in resp_operadores.data
                }
                
                operador_seleccionado = st.selectbox(
                    "👷 Operador",
                    options=list(operadores_map.keys()),
                    key="ingesta_operador_select",
                    help="Seleccione el operador que envía los datos"
                )
                
                if operador_seleccionado:
                    op_info = operadores_map[operador_seleccionado]
                    operador_id = op_info['id']
                    operador_codigo = op_info['codigo']
                    
                    st.success(f"✅ Operador seleccionado: **{operador_seleccionado}**")
                    
                    # ===== PASO 2: Seleccionar Dispositivo del Operador =====
                    st.markdown("### 2️⃣ Seleccionar Dispositivo")
                    
                    # Cargar dispositivos del operador
                    resp_dispositivos = supabase.table('dispositivos')\
                        .select('id, id_dispositivo_externo, tipo_dispositivo, marca, modelo')\
                        .eq('id_operador_asignado', operador_id)\
                        .eq('estado', 'ACTIVO')\
                        .execute()
                    
                    if resp_dispositivos.data:
                        # Mapeo de iconos para cada tipo
                        iconos_dispositivo = {
                            'SMARTWATCH': '⌚',
                            'BANDA_ANTIFATIGA': '💪',
                            'TELEMATICA': '📡'
                        }
                        
                        nombres_dispositivo = {
                            'SMARTWATCH': 'Smartwatch',
                            'BANDA_ANTIFATIGA': 'Banda Antifatiga',
                            'TELEMATICA': 'Telemática'
                        }
                        
                        dispositivos_map = {
                            f"{iconos_dispositivo.get(d['tipo_dispositivo'], '📱')} {nombres_dispositivo.get(d['tipo_dispositivo'], d['tipo_dispositivo'])} - {d.get('marca', '')} {d.get('modelo', '')} ({d['id_dispositivo_externo']})": {
                                'id': d['id'],
                                'id_externo': d['id_dispositivo_externo'],
                                'tipo': d['tipo_dispositivo']
                            }
                            for d in resp_dispositivos.data
                        }
                        
                        dispositivo_seleccionado = st.selectbox(
                            "📱 Dispositivo",
                            options=list(dispositivos_map.keys()),
                            key="ingesta_dispositivo_select",
                            help="Seleccione el dispositivo que envía los datos"
                        )
                        
                        if dispositivo_seleccionado:
                            disp_info = dispositivos_map[dispositivo_seleccionado]
                            dispositivo_id_externo = disp_info['id_externo']
                            tipo_dispositivo = disp_info['tipo']
                            
                            st.success(f"✅ Dispositivo: **{dispositivo_seleccionado}**")
                            
                            st.markdown("---")
                            
                            # ===== PASO 3: Datos del Dispositivo =====
                            st.markdown("### 3️⃣ Datos del Dispositivo")
                            
                            # Fecha y hora
                            col_dt1, col_dt2 = st.columns(2)
                            with col_dt1:
                                ingesta_date = st.date_input("📅 Fecha", value="today", key="ingesta_date")
                            with col_dt2:
                                ingesta_time = st.time_input("🕐 Hora", value="now", key="ingesta_time")
                            
                            timestamp = datetime.combine(ingesta_date, ingesta_time)
                            
                            st.markdown("---")
                            
                            # Inicializar datos simulados en session_state si no existen
                            if 'datos_simulados' not in st.session_state:
                                st.session_state.datos_simulados = None
                            if 'tipo_dispositivo_anterior' not in st.session_state:
                                st.session_state.tipo_dispositivo_anterior = None
                            
                            # Limpiar datos si cambia el tipo de dispositivo
                            if st.session_state.tipo_dispositivo_anterior != tipo_dispositivo:
                                st.session_state.datos_simulados = None
                                st.session_state.tipo_dispositivo_anterior = tipo_dispositivo
                            
                            # Botón para generar datos simulados
                            col_sim1, col_sim2 = st.columns([1, 3])
                            with col_sim1:
                                if st.button("🎲 Generar Datos Simulados", type="secondary", use_container_width=True):
                                    st.session_state.datos_simulados = generar_datos_simulados(tipo_dispositivo)
                                    st.rerun()
                            
                            with col_sim2:
                                if st.session_state.datos_simulados:
                                    st.info("✨ Datos simulados generados. Puede modificarlos antes de enviar.")
                            
                            # Obtener valores (simulados o por defecto)
                            datos = st.session_state.datos_simulados or {}
                            
                            # Formulario de datos según tipo de dispositivo
                            with st.form("form_ingesta_datos"):
                                data_payload = {}
                                
                                if tipo_dispositivo == 'SMARTWATCH':
                                    st.subheader("⌚ Datos de Smartwatch")
                                    
                                    col_sw1, col_sw2 = st.columns(2)
                                    with col_sw1:
                                        st.markdown("**💤 Datos de Sueño**")
                                        sleep_duration = st.number_input(
                                            "Duración del Sueño (horas)", 
                                            min_value=0.0, max_value=24.0,
                                            value=float(datos.get('sleep', {}).get('duration_hours', 7.0)),
                                            step=0.5
                                        )
                                        sleep_quality = st.slider(
                                            "Calidad del Sueño", 
                                            0, 100, 
                                            value=int(datos.get('sleep', {}).get('quality_score', 75))
                                        )
                                        sleep_deep = st.number_input(
                                            "Sueño Profundo (min)", 
                                            min_value=0, max_value=480,
                                            value=int(datos.get('sleep', {}).get('deep_minutes', 90))
                                        )
                                        sleep_rem = st.number_input(
                                            "Sueño REM (min)", 
                                            min_value=0, max_value=480,
                                            value=int(datos.get('sleep', {}).get('rem_minutes', 90))
                                        )
                                        sleep_efficiency = st.slider(
                                            "Eficiencia del Sueño", 
                                            0.0, 1.0, 
                                            value=float(datos.get('sleep', {}).get('efficiency', 0.85)),
                                            step=0.05
                                        )
                                    
                                    with col_sw2:
                                        st.markdown("**❤️ Signos Vitales**")
                                        heart_rate = st.number_input(
                                            "Frecuencia Cardíaca (bpm)", 
                                            min_value=30, max_value=200,
                                            value=int(datos.get('vitals', {}).get('heart_rate', 70))
                                        )
                                        hrv_rmssd = st.number_input(
                                            "HRV RMSSD", 
                                            min_value=0.0, max_value=200.0,
                                            value=float(datos.get('vitals', {}).get('hrv_rmssd', 40.0))
                                        )
                                        hrv_sdnn = st.number_input(
                                            "HRV SDNN", 
                                            min_value=0.0, max_value=200.0,
                                            value=float(datos.get('vitals', {}).get('hrv_sdnn', 50.0))
                                        )
                                        spo2 = st.slider(
                                            "SpO2 (%)", 
                                            85.0, 100.0, 
                                            value=float(datos.get('vitals', {}).get('spo2', 98.0)),
                                            step=0.5
                                        )
                                        skin_temp = st.number_input(
                                            "Temperatura Piel (°C)", 
                                            min_value=30.0, max_value=42.0,
                                            value=float(datos.get('vitals', {}).get('skin_temp', 36.5))
                                        )
                                        stress_level = st.slider(
                                            "Nivel de Estrés", 
                                            0, 100, 
                                            value=int(datos.get('vitals', {}).get('stress_level', 30))
                                        )
                                    
                                    data_payload = {
                                        "sleep": {
                                            "duration_hours": sleep_duration,
                                            "quality_score": sleep_quality,
                                            "deep_minutes": sleep_deep,
                                            "rem_minutes": sleep_rem,
                                            "efficiency": sleep_efficiency
                                        },
                                        "vitals": {
                                            "heart_rate": heart_rate,
                                            "hrv_rmssd": hrv_rmssd,
                                            "hrv_sdnn": hrv_sdnn,
                                            "spo2": spo2,
                                            "skin_temp": skin_temp,
                                            "stress_level": stress_level
                                        }
                                    }
                                
                                elif tipo_dispositivo == 'BANDA_ANTIFATIGA':
                                    st.subheader("💪 Datos de Banda Antifatiga")
                                    
                                    col_ba1, col_ba2 = st.columns(2)
                                    with col_ba1:
                                        st.markdown("**🧘 Postura**")
                                        trunk_angle = st.number_input(
                                            "Ángulo del Tronco (°)", 
                                            min_value=0.0, max_value=90.0,
                                            value=float(datos.get('posture', {}).get('trunk_angle', 10.0))
                                        )
                                        head_nods = st.number_input(
                                            "Cabeceos Detectados", 
                                            min_value=0, max_value=100,
                                            value=int(datos.get('posture', {}).get('head_nods', 0))
                                        )
                                        micro_sleeps = st.number_input(
                                            "Micro-sueños Detectados", 
                                            min_value=0, max_value=50,
                                            value=int(datos.get('posture', {}).get('micro_sleeps', 0))
                                        )
                                    
                                    with col_ba2:
                                        st.markdown("**💪 Actividad Muscular**")
                                        neck_activity = st.slider(
                                            "Actividad Muscular Cuello (EMG)", 
                                            0, 100, 
                                            value=int(datos.get('emg', {}).get('neck_activity', 50))
                                        )
                                        inactivity_min = st.number_input(
                                            "Minutos de Inactividad", 
                                            min_value=0, max_value=480,
                                            value=int(datos.get('movement', {}).get('inactivity_minutes', 15))
                                        )
                                    
                                    data_payload = {
                                        "posture": {
                                            "trunk_angle": trunk_angle,
                                            "head_nods": head_nods,
                                            "micro_sleeps": micro_sleeps
                                        },
                                        "emg": {
                                            "neck_activity": neck_activity
                                        },
                                        "movement": {
                                            "inactivity_minutes": inactivity_min
                                        }
                                    }
                                
                                elif tipo_dispositivo == 'TELEMATICA':
                                    st.subheader("📡 Datos Telemáticos")
                                    
                                    col_tel1, col_tel2 = st.columns(2)
                                    with col_tel1:
                                        st.markdown("**🚜 Maquinaria**")
                                        machinery_type = st.selectbox(
                                            "Tipo de Maquinaria",
                                            ["Excavadora", "Camión Minero", "Pala Cargadora", "Bulldozer", "Grúa", "Otro"],
                                            index=0
                                        )
                                        shift_type = st.selectbox(
                                            "Tipo de Turno", 
                                            ["DIA", "NOCHE", "ROTATIVO"]
                                        )
                                        hours_in_shift = st.number_input(
                                            "Horas en Turno", 
                                            min_value=0.0, max_value=24.0,
                                            value=float(datos.get('shift', {}).get('hours_elapsed', 4.0)),
                                            step=0.5
                                        )
                                    
                                    with col_tel2:
                                        st.markdown("**🌡️ Ambiente**")
                                        ambient_temp = st.number_input(
                                            "Temperatura Ambiente (°C)", 
                                            min_value=-20.0, max_value=60.0,
                                            value=float(datos.get('environment', {}).get('temperature', 25.0))
                                        )
                                        ambient_humidity = st.slider(
                                            "Humedad Ambiente (%)", 
                                            0, 100, 
                                            value=int(datos.get('environment', {}).get('humidity', 60))
                                        )
                                    
                                    data_payload = {
                                        "machinery": {"type": machinery_type},
                                        "shift": {"type": shift_type, "hours_elapsed": hours_in_shift},
                                        "environment": {"temperature": ambient_temp, "humidity": ambient_humidity}
                                    }
                                
                                st.markdown("---")
                                
                                # Botón de envío
                                submitted = st.form_submit_button(
                                    "🚀 Enviar Datos a n8n", 
                                    type="primary", 
                                    use_container_width=True
                                )
                                
                                if submitted:
                                    full_payload = {
                                        "device_type": tipo_dispositivo,
                                        "device_external_id": dispositivo_id_externo,
                                        "operator_external_id": operador_codigo,
                                        "operator_id": operador_id,
                                        "timestamp": timestamp.isoformat(),
                                        **data_payload
                                    }
                                    
                                    # Mostrar payload
                                    with st.expander("📋 Ver Payload JSON", expanded=False):
                                        st.json(full_payload)
                                    
                                    try:
                                        response = requests.post(N8N_WEBHOOK_URL, json=full_payload)
                                        
                                        if response.status_code == 200:
                                            st.success(f"✅ Datos enviados exitosamente a n8n")
                                            st.balloons()
                                            # Limpiar datos simulados después de enviar
                                            st.session_state.datos_simulados = None
                                        else:
                                            st.error(f"❌ Error al enviar. Código: {response.status_code}")
                                            st.code(response.text)
                                    except requests.exceptions.RequestException as e:
                                        st.error(f"❌ Error de conexión: {e}")
                    else:
                        st.warning("⚠️ Este operador no tiene dispositivos asignados. Asígnele un dispositivo en el panel de **📋 Mantenedores**.")
            else:
                st.warning("⚠️ No hay operadores activos en el sistema. Cree operadores en el panel de **📋 Mantenedores**.")
                
        except Exception as e:
            st.error(f"Error al cargar datos: {e}")

# ============================================
# NAVEGACIÓN PRINCIPAL
# ============================================

def main():
    # Sidebar para navegación
    with st.sidebar:
        st.markdown("### ⚠️ Sistema de Gestión de Fatiga")
        st.markdown("---")
        
        # Selector de vista
        vista = st.radio(
            "Seleccionar Vista:",
            ["🛡️ Gerente de Seguridad", "👨‍💼 Supervisor de Turno", "📋 Mantenedores", "⚙️ Configuración"],
            index=0
        )
        
        st.markdown("---")
        
        # Información del sistema
        st.subheader("ℹ️ Info del Sistema")
        st.write(f"**Fecha:** {datetime.now().strftime('%d/%m/%Y')}")
        st.write(f"**Hora:** {datetime.now().strftime('%H:%M:%S')}")
        
        # Botón de actualización
        if st.button("🔄 Actualizar Datos"):
            st.cache_data.clear()
            st.rerun()
        
        st.markdown("---")
        st.caption("Sistema de Gestión de Fatiga v2.2")
        st.caption("© 2025 - Todos los derechos reservados")
    
    # Renderizar vista seleccionada
    if vista == "🛡️ Gerente de Seguridad":
        panel_gerente()
    elif vista == "👨‍💼 Supervisor de Turno":
        panel_supervisor()
    elif vista == "📋 Mantenedores":
        panel_mantenedores()
    else:
        panel_configuracion()

# ============================================
# PUNTO DE ENTRADA
# ============================================

if __name__ == "__main__":
    # Inicializar session state
    if 'ver_detalle' not in st.session_state:
        st.session_state['ver_detalle'] = False
    if 'operador_seleccionado' not in st.session_state:
        st.session_state['operador_seleccionado'] = None
    
    main()
