import streamlit as st
import time
import json
from datetime import datetime
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import urllib.request
import base64
import os

# Configuración de página
st.set_page_config(page_title="Sistema de Compras - Abastecedora Keops 2000", layout="wide")

# ==========================================
# CONFIGURACIÓN DE GOOGLE CLOUD
# ==========================================
ID_CARPETA_DRIVE = "1M2jMjYGls4MX5skiNb1_5v5kEy8hdXm7" 
URL_SCRIPT = "https://script.google.com/macros/s/AKfycbzf9j-eAdP_QOR57AWgETaxf6ove5p8kXKicH_QxbIaZypoROK57Cl4fcSlkt3oheb1YQ/exec"
NOMBRE_HOJA_SHEETS = "Base_Pedidos_Keops"

@st.cache_resource
def conectar_google():
    # Leer las credenciales de la caja fuerte de Streamlit
    cred_dict = json.loads(st.session_state.get('secrets', st.secrets)["GOOGLE_CREDENTIALS"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(cred_dict, scopes=scopes)
    
    # Conectar a Sheets y Drive
    gc = gspread.authorize(creds)
    sheet = gc.open(NOMBRE_HOJA_SHEETS).sheet1
    drive_service = build('drive', 'v3', credentials=creds)
    
    return sheet, drive_service

sheet, drive_service = conectar_google()

def subir_a_drive(archivo):
    """Sube el archivo a Drive usando Google Apps Script"""
    file_bytes = archivo.getvalue()
    base64_encoded = base64.b64encode(file_bytes).decode('utf-8')
    
    payload = {
        "folder_id": ID_CARPETA_DRIVE,
        "filename": archivo.name,
        "mimeType": archivo.type,
        "file_base64": base64_encoded
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(URL_SCRIPT, data=data, headers={'Content-Type': 'application/json'})
    
    try:
        with urllib.request.urlopen(req) as response:
            resultado = json.loads(response.read().decode())
            if resultado.get("status") == "success":
                return resultado.get("url")
            else:
                st.error(f"Error de Google: {resultado.get('message')}")
                return None
    except Exception as e:
        st.error(f"Error de conexión: {str(e)}")
        return None

def cargar_pedidos():
    registros = sheet.get_all_records()
    for r in registros:
        if isinstance(r.get('Historial_JSON'), str) and r['Historial_JSON']:
            r['historial'] = json.loads(r['Historial_JSON'])
        else:
            r['historial'] = []
    return registros

def actualizar_pedido_en_sheet(pedido_actualizado):
    """Busca el ID en la hoja y actualiza la fila completa"""
    todos_los_ids = sheet.col_values(1) # Obtener todos los IDs (Columna A)
    try:
        # +1 porque las listas de python empiezan en 0, y +1 por el encabezado = +2
        fila_indice = todos_los_ids.index(str(pedido_actualizado['ID'])) + 1
        
        historial_str = json.dumps(pedido_actualizado.get('historial', []))
        
        sheet.update(f'G{fila_indice}:H{fila_indice}', [[
            pedido_actualizado['Estado'],
            historial_str
        ]])
    except ValueError:
        st.error("Error: No se encontró el pedido en la base de datos.")

# ==========================================
# SISTEMA DE USUARIOS LOCAL (Temporal para el prototipo)
# ==========================================
ARCHIVO_USUARIOS = "usuarios.json"

def cargar_usuarios():
    if os.path.exists(ARCHIVO_USUARIOS):
        with open(ARCHIVO_USUARIOS, "r") as f:
            return json.load(f)
    usuarios_base = [{"usuario": "admin", "password": "123", "rol": "Admin"}]
    with open(ARCHIVO_USUARIOS, "w") as f:
        json.dump(usuarios_base, f, indent=4)
    return usuarios_base

# ==========================================
# SISTEMA DE LOGIN Y SESIÓN
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.usuario = ''
    st.session_state.rol = ''

if not st.session_state.logged_in:
    st.title("🔒 Acceso al Sistema de Compras")
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login_form"):  # <--- Corregido: Este es el form de login normal
            st.subheader("Iniciar Sesión")
            usuario_input = st.text_input("Usuario")
            password_input = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("Ingresar", type="primary", use_container_width=True)
            
            if submit:
                usuarios = cargar_usuarios()
                usuario_valido = next((u for u in usuarios if u['usuario'] == usuario_input and u['password'] == password_input), None)
                
                if usuario_valido:
                    st.session_state.logged_in = True
                    st.session_state.usuario = usuario_valido['usuario']
                    st.session_state.rol = usuario_valido['rol']
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
    st.stop()

# ==========================================
# MENÚ LATERAL
# ==========================================
st.sidebar.title(f"👤 Bienvenido, {st.session_state.usuario}")
st.sidebar.markdown(f"**Rol actual:** {st.session_state.rol}")

opciones_menu = []
if st.session_state.rol == "Compras":
    opciones_menu = ["Área de Compras", "Reportes de Movimientos"]
elif st.session_state.rol == "Gerencia":
    opciones_menu = ["Pedidos por Autorizar", "Reportes de Movimientos"]
elif st.session_state.rol == "Admin":
    opciones_menu = ["Área de Compras", "Pedidos por Autorizar", "Reportes de Movimientos"]

seleccion = st.sidebar.radio("Menú de Navegación", opciones_menu)

if st.sidebar.button("🚪 Cerrar Sesión"):
    st.session_state.logged_in = False
    st.rerun()

pedidos = cargar_pedidos()

# ==========================================
# VISTA: ÁREA DE COMPRAS
# ==========================================
if seleccion == "Área de Compras":
    st.title("🛒 Área de Compras")
    tab1, tab2 = st.tabs(["📝 Crear Nuevo Pedido", "⚠️ Pedidos Rechazados"])
    
    with tab1:
        # <--- Corregido: Aquí es donde va el clear_on_submit=True
        with st.form("form_pedido", clear_on_submit=True): 
            proveedor = st.text_input("Nombre del Proveedor")
            monto = st.number_input("Monto Total ($)", min_value=0.0, format="%.2f")
            proc_sel = st.selectbox("Procedencia del Pedido", ["Mercado Libre", "Amazon", "Centro", "Otra"])
            procedencia_final = st.text_input("Especificar procedencia") if proc_sel == "Otra" else proc_sel
            archivo = st.file_uploader("Sube la cotización (PDF/Excel)", type=["pdf", "xlsx", "xls"])
            enviado = st.form_submit_button("Enviar a Gerencia y Subir a la Nube")
            
            if enviado and proveedor and monto > 0 and archivo:
                with st.spinner('Subiendo archivo a Google Drive y registrando en Sheets...'):
                    enlace_drive = subir_a_drive(archivo)
                    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    nuevo_id = len(pedidos) + 1
                    
                    historial_inicial = [{"fecha": fecha_actual, "usuario": st.session_state.usuario, "accion": "Creación", "detalle": "Enviado a gerencia"}]
                    
                    # Escribir fila en Google Sheets
                    sheet.append_row([
                        nuevo_id, fecha_actual, proveedor, monto, procedencia_final, 
                        enlace_drive, "Pendiente", json.dumps(historial_inicial)
                    ])
                st.success("¡Pedido enviado y respaldado en la nube exitosamente!")
                time.sleep(2)  # <--- Corregido: Da tiempo para leer el mensaje
                st.rerun()     # <--- Corregido: Recarga para aplicar la limpieza y bajar los datos nuevos

    with tab2:
        rechazados = [p for p in pedidos if p.get("Estado") == "Rechazado"]
        if not rechazados:
            st.info("No hay pedidos rechazados.")
        else:
            for p in rechazados:
                with st.expander(f"❌ Pedido #{p.get('ID', '?')} - {p.get('Proveedor', '?')} (Rechazado)"):
                    for h in p.get("historial", []):
                        if h["accion"] in ["Rechazo", "Comentario"]:
                            st.info(f"**{h['fecha']} - {h['usuario']}:** {h['detalle']}")
                    if st.button("Reenviar a revisión", key=f"reenviar_{p.get('ID', '?')}"):
                        p["Estado"] = "Pendiente"
                        p["historial"].append({"fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "usuario": st.session_state.usuario, "accion": "Reenvío", "detalle": "Pedido ajustado"})
                        actualizar_pedido_en_sheet(p)
                        st.success("Pedido reenviado.")
                        time.sleep(1)
                        st.rerun()

# ==========================================
# VISTA: GERENCIA
# ==========================================
elif seleccion == "Pedidos por Autorizar":
    st.title("✅ Autorización de Pedidos")
    pendientes = [p for p in pedidos if p.get("Estado") == "Pendiente"]
    
    if not pendientes:
        st.success("No hay pedidos pendientes de revisión.")
    else:
        for pedido in pendientes:
            st.markdown(f"### Pedido #{pedido.get('ID', '?')} - {pedido.get('Proveedor', '?')}")
            st.write(f"**Monto:** ${float(pedido.get('Monto', 0)):,.2f} | **Procedencia:** {pedido.get('Procedencia', '?')} | **Fecha:** {pedido.get('Fecha', '?')}")
            st.markdown(f"[📄 **Hacer clic aquí para abrir el documento adjunto**]({pedido.get('Enlace_Archivo', '#')})")
            
            comentario = st.text_area("Comentarios:", key=f"com_{pedido.get('ID', '?')}")
            
            col_aut, col_rech = st.columns(2)
            with col_aut:
                if st.button("✔️ Autorizar", type="primary", key=f"aut_{pedido.get('ID', '?')}"):
                    pedido["Estado"] = "Autorizado"
                    pedido["historial"].append({"fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "usuario": st.session_state.usuario, "accion": "Autorización", "detalle": comentario or "Sin comentarios"})
                    actualizar_pedido_en_sheet(pedido)
                    st.rerun()
            with col_rech:
                if st.button("❌ Rechazar", key=f"rech_{pedido.get('ID', '?')}"):
                    pedido["Estado"] = "Rechazado"
                    pedido["historial"].append({"fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "usuario": st.session_state.usuario, "accion": "Rechazo", "detalle": comentario or "Rechazado sin comentarios"})
                    actualizar_pedido_en_sheet(pedido)
                    st.rerun()
            st.divider()

# ==========================================
# VISTA: REPORTES
# ==========================================
elif seleccion == "Reportes de Movimientos":
    st.title("📊 Reportes y Auditoría")
    
    st.markdown("Si deseas extraer los datos para contabilidad, abre la base de datos directa en Google Sheets:")
    st.info("💡 **Abre tu Google Drive y busca el archivo 'Base_Pedidos_Keops' para ver la tabla completa y descargarla en Excel.**")
    
    if not pedidos:
        st.info("No hay datos.")
    else:
        for p in reversed(pedidos):
            # <--- Corregido: Previene colapsos si faltan datos en Excel
            estado = str(p.get('Estado', 'Pendiente')).strip() 
            color = "🟢" if estado == 'Autorizado' else "🔴" if estado == 'Rechazado' else "🟡"
            
            with st.expander(f"{color} #{p.get('ID', '?')} | {p.get('Proveedor', '?')} | ${float(p.get('Monto', 0)):,.2f} | {p.get('Procedencia', '?')}"):
                for mov in p.get("historial", []):
                    st.write(f"- *{mov['fecha']}* | **{mov['usuario']}** ({mov['accion']}): {mov['detalle']}")
