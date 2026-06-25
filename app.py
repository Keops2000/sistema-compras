import streamlit as st
import time
import json
from datetime import datetime
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import io
import urllib.request
import base64
import os
import re  # <--- NUEVO: Herramienta para forzar la lectura del ID de Google Drive
import extra_streamlit_components as stx

# Configuración de página
st.set_page_config(page_title="Sistema de Compras - Abastecedora Keops 2000", layout="wide")

# Inicializar el gestor de cookies
cookie_manager = stx.CookieManager(key="keops_cookie_manager")
time.sleep(0.2)

# ==========================================
# CONFIGURACIÓN DE GOOGLE CLOUD
# ==========================================
ID_CARPETA_DRIVE = "1M2jMjYGls4MX5skiNb1_5v5kEy8hdXm7" 
URL_SCRIPT = "https://script.google.com/macros/s/AKfycbzf9j-eAdP_QOR57AWgETaxf6ove5p8kXKicH_QxbIaZypoROK57Cl4fcSlkt3oheb1YQ/exec"
NOMBRE_HOJA_SHEETS = "Base_Pedidos_Keops"

@st.cache_resource
def conectar_google():
    cred_dict = json.loads(st.session_state.get('secrets', st.secrets)["GOOGLE_CREDENTIALS"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(cred_dict, scopes=scopes)
    
    gc = gspread.authorize(creds)
    workbook = gc.open(NOMBRE_HOJA_SHEETS)
    
    sheet_pedidos = workbook.sheet1
    
    try:
        sheet_usuarios = workbook.worksheet("Usuarios")
    except gspread.exceptions.WorksheetNotFound:
        sheet_usuarios = workbook.add_worksheet(title="Usuarios", rows="100", cols="3")
        sheet_usuarios.append_row(["usuario", "password", "rol"])
        sheet_usuarios.append_row(["admin", "123", "Admin"])
    
    drive_service = build('drive', 'v3', credentials=creds)
    
    return sheet_pedidos, sheet_usuarios, drive_service

sheet, sheet_usuarios, drive_service = conectar_google()

# ==========================================
# FUNCIONES DE CONTROL
# ==========================================
def subir_a_drive(archivo):
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
    pedidos_limpios = []
    for r in registros:
        p = {str(k).strip(): v for k, v in r.items()}
        if isinstance(p.get('Historial_JSON'), str) and p['Historial_JSON']:
            p['historial'] = json.loads(p['Historial_JSON'])
        else:
            p['historial'] = []
        pedidos_limpios.append(p)
    return pedidos_limpios

def actualizar_pedido_en_sheet(pedido_actualizado):
    todos_los_ids = sheet.col_values(1)
    try:
        fila_indice = todos_los_ids.index(str(pedido_actualizado['ID'])) + 1
        historial_str = json.dumps(pedido_actualizado.get('historial', []))
        sheet.update(f'F{fila_indice}:H{fila_indice}', [[
            pedido_actualizado.get('Enlace_Archivo', ''),
            pedido_actualizado['Estado'],
            historial_str
        ]])
    except ValueError:
        st.error("Error: No se encontró el pedido en la base de datos.")

def cargar_usuarios_cloud():
    return sheet_usuarios.get_all_records()

def registrar_usuario_cloud(nuevo_user, nuevo_pass, nuevo_rol):
    usuarios = cargar_usuarios_cloud()
    if any(str(u['usuario']).strip().lower() == nuevo_user.lower() for u in usuarios):
        return False
    sheet_usuarios.append_row([nuevo_user, nuevo_pass, nuevo_rol])
    return True

# --- NUEVO: FUNCIÓN INFALIBLE PARA MOSTRAR EL VISOR DE PDF/EXCEL ---
def mostrar_visor_incrustado(enlace):
    enlace_str = str(enlace)
    # Busca el ID del archivo sin importar si es de docs.google o drive.google
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', enlace_str)
    if not match:
        match = re.search(r'id=([a-zA-Z0-9_-]+)', enlace_str)
        
    if match:
        file_id = match.group(1)
        enlace_preview = f"https://drive.google.com/file/d/{file_id}/preview"
        st.components.v1.iframe(enlace_preview, height=600, scrolling=True)
    else:
        st.markdown(f"[📄 **Abrir documento adjunto**]({enlace_str})")

# ==========================================
# SESIÓN Y COOKIES
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.usuario = ''
    st.session_state.rol = ''

if not st.session_state.logged_in:
    try:
        c_user = cookie_manager.get("keops_user")
        c_rol = cookie_manager.get("keops_rol")
        if c_user and c_rol:
            st.session_state.logged_in = True
            st.session_state.usuario = c_user
            st.session_state.rol = c_rol
            st.rerun()
    except Exception:
        pass

# ==========================================
# LOGIN
# ==========================================
if not st.session_state.logged_in:
    st.title("🔒 Acceso al Sistema de Compras")
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login_form"): 
            st.subheader("Iniciar Sesión")
            usuario_input = st.text_input("Usuario").strip()
            password_input = st.text_input("Contraseña", type="password").strip()
            recordar_sesion = st.checkbox("Mantener sesión iniciada en este equipo")
            submit = st.form_submit_button("Ingresar", type="primary", use_container_width=True)
            
            if submit:
                usuarios_registrados = cargar_usuarios_cloud()
                usuario_valido = next((u for u in usuarios_registrados if str(u['usuario']).strip() == usuario_input and str(u['password']).strip() == password_input), None)
                
                if usuario_valido:
                    st.session_state.logged_in = True
                    st.session_state.usuario = usuario_valido['usuario']
                    st.session_state.rol = usuario_valido['rol']
                    
                    if recordar_sesion:
                        cookie_manager.set("keops_user", usuario_valido['usuario'], max_age=2592000, key="cookie_user")
                        cookie_manager.set("keops_rol", usuario_valido['rol'], max_age=2592000, key="cookie_rol")
                    
                    st.success("¡Acceso concedido!")
                    time.sleep(1)
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
    opciones_menu = ["Área de Compras", "Pedidos por Autorizar", "Reportes de Movimientos", "⚙️ Gestión de Usuarios"]

seleccion = st.sidebar.radio("Menú de Navegación", opciones_menu)

if st.sidebar.button("🚪 Cerrar Sesión"):
    st.session_state.logged_in = False
    st.session_state.usuario = ''
    st.session_state.rol = ''
    cookie_manager.delete("keops_user", key="borrar_user")
    cookie_manager.delete("keops_rol", key="borrar_rol")
    st.rerun()

pedidos = cargar_pedidos()

# ==========================================
# VISTA: ÁREA DE COMPRAS
# ==========================================
if seleccion == "Área de Compras":
    st.title("🛒 Área de Compras")
    tab1, tab_notif, tab2 = st.tabs(["📝 Crear Nuevo Pedido", "🔔 Pedidos Aprobados", "⚠️ Pedidos Rechazados"])
    
    with tab1:
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
                    
                    sheet.append_row([
                        nuevo_id, fecha_actual, proveedor, monto, procedencia_final, 
                        enlace_drive, "Pendiente", json.dumps(historial_inicial)
                    ])
                st.success("¡Pedido enviado y respaldado en la nube exitosamente!")
                time.sleep(2)
                st.rerun()

    with tab_notif:
        st.subheader("📦 Notificaciones de Aprobación Recientes")
        aprobados = [p for p in pedidos if p.get("Estado") == "Autorizado"]
        if not aprobados:
            st.info("No hay pedidos autorizados recientemente.")
        else:
            for p in reversed(aprobados):
                with st.expander(f"🟢 Pedido #{p.get('ID', '?')} - {p.get('Proveedor', '?')} | ¡APROBADO!"):
                    st.success(f"El pedido por un monto de **${float(p.get('Monto', 0)):,.2f}** procedente de **{p.get('Procedencia', '?')}** ha sido autorizado con éxito.")
                    st.markdown("**Notas de Autorización Gerencial:**")
                    for h in p.get("historial", []):
                        if h["accion"] == "Autorización":
                            st.write(f"- *{h['fecha']}* | Autorizado por **{h['usuario']}**: {h['detalle']}")

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
                    
                    st.write("---")
                    st.markdown("**🔄 Corregir y Reenviar Pedido**")
                    
                    with st.form(key=f"form_reenvio_{p.get('ID', '?')}"):
                        nuevo_comentario = st.text_area("¿Qué cambios realizaste?:")
                        nuevo_archivo = st.file_uploader("Sube el nuevo archivo corregido", type=["pdf", "xlsx", "xls"])
                        btn_reenviar = st.form_submit_button("Subir archivo y Reenviar a Gerencia")
                        
                        if btn_reenviar:
                            if nuevo_comentario and nuevo_archivo:
                                with st.spinner('Subiendo nuevo documento...'):
                                    nuevo_enlace = subir_a_drive(nuevo_archivo)
                                    if nuevo_enlace:
                                        p["Enlace_Archivo"] = nuevo_enlace
                                        p["Estado"] = "Pendiente (Reenviado)"
                                        p["historial"].append({
                                            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                                            "usuario": st.session_state.usuario, 
                                            "accion": "Reenvío", 
                                            "detalle": f"NUEVO ARCHIVO ADJUNTO: {nuevo_comentario}"
                                        })
                                        actualizar_pedido_en_sheet(p)
                                        st.success("¡Pedido actualizado y reenviado!")
                                        time.sleep(2)
                                        st.rerun()
                            else:
                                st.warning("⚠️ Debes adjuntar el archivo y comentar los cambios.")

# ==========================================
# VISTA: GERENCIA (AUTORIZACIONES)
# ==========================================
elif seleccion == "Pedidos por Autorizar":
    st.title("✅ Autorización de Pedidos")
    pendientes = [p for p in pedidos if p.get("Estado") in ["Pendiente", "Pendiente (Reenviado)"]]
    
    if not pendientes:
        st.success("No hay pedidos pendientes de revisión.")
    else:
        for pedido in pendientes:
            alerta_reenvio = " ⚠️ *(REENVIADO CORREGIDO)*" if pedido.get("Estado") == "Pendiente (Reenviado)" else ""
            st.markdown(f"### Pedido #{pedido.get('ID', '?')} - {pedido.get('Proveedor', '?')}{alerta_reenvio}")
            st.write(f"**Monto:** ${float(pedido.get('Monto', 0)):,.2f} | **Procedencia:** {pedido.get('Procedencia', '?')} | **Fecha:** {pedido.get('Fecha', '?')}")
            
            if pedido.get("Estado") == "Pendiente (Reenviado)":
                with st.expander("Ver notas de la corrección anterior"):
                    for mov in pedido.get("historial", []):
                        if mov["accion"] in ["Rechazo", "Reenvío"]:
                            st.write(f"- **{mov['accion']} ({mov['usuario']}):** {mov['detalle']}")

            # Llama a la nueva función infalible
            mostrar_visor_incrustado(pedido.get('Enlace_Archivo', '#'))
            
            comentario = st.text_area("Comentarios:", key=f"com_{pedido.get('ID', '?')}")
            col_aut, col_rech = st.columns(2)
            
            with col_aut:
                if st.button("✔️ Autorizar", type="primary", key=f"aut_{pedido.get('ID', '?')}"):
                    pedido["Estado"] = "Autorizado"
                    pedido["historial"].append({
                        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                        "usuario": st.session_state.usuario, 
                        "accion": "Autorización", 
                        "detalle": comentario or "Sin comentarios"
                    })
                    actualizar_pedido_en_sheet(pedido)
                    st.rerun()
            with col_rech:
                if st.button("❌ Rechazar", key=f"rech_{pedido.get('ID', '?')}"):
                    pedido["Estado"] = "Rechazado"
                    pedido["historial"].append({
                        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                        "usuario": st.session_state.usuario, 
                        "accion": "Rechazo", 
                        "detalle": comentario or "Rechazado sin comentarios"
                    })
                    actualizar_pedido_en_sheet(pedido)
                    st.rerun()
            st.divider()

# ==========================================
# VISTA: REPORTES CONTABLES Y DASHBOARDS
# ==========================================
elif seleccion == "Reportes de Movimientos":
    st.title("📊 Reportes, Filtros Avanzados y Gráficas")
    st.markdown("Para contabilidad general externa, abre la base de datos de Google Sheets directamente:")
    st.info("💡 **Abre tu Google Drive y busca el archivo 'Base_Pedidos_Keops' para ver las tablas completas en crudo.**")
    
    if not pedidos:
        st.info("No hay datos en la base de datos.")
    else:
        df_pedidos = pd.DataFrame(pedidos)
        df_pedidos['Monto'] = pd.to_numeric(df_pedidos['Monto'], errors='coerce').fillna(0.0)
        df_pedidos['Fecha_DT'] = pd.to_datetime(df_pedidos['Fecha'], errors='coerce')
        df_pedidos['Estado'] = df_pedidos['Estado'].astype(str).str.strip()
        df_pedidos['Proveedor'] = df_pedidos['Proveedor'].astype(str).str.strip()
        df_pedidos['Procedencia'] = df_pedidos['Procedencia'].astype(str).str.strip()
        df_pedidos['Fecha_Corta'] = df_pedidos['Fecha_DT'].dt.strftime('%Y-%m-%d')

        tab_lista, tab_dashboard = st.tabs(["📋 Historial con Filtros Dinómicos", "📈 Dashboard Financiero de Gastos"])
        
        with tab_lista:
            st.subheader("🔍 Panel de Filtros")
            col_f1, col_f2, col_f3 = st.columns(3)
            
            with col_f1:
                fechas_validas = df_pedidos['Fecha_DT'].dropna()
                if not fechas_validas.empty:
                    min_date = fechas_validas.min().date()
                    max_date = fechas_validas.max().date()
                    rango_fecha = st.date_input("Rango de Fechas del Pedido:", [min_date, max_date], key="filt_date_range")
                else:
                    rango_fecha = []
            
            with col_f2:
                min_monto = float(df_pedidos['Monto'].min())
                max_monto = float(df_pedidos['Monto'].max())
                if min_monto < max_monto:
                    rango_monto = st.slider("Importe del Pedido ($):", min_monto, max_monto, (min_monto, max_monto), key="filt_monto_slider")
                else:
                    rango_monto = (min_monto, min_monto + 100.0)
            
            with col_f3:
                estados_disponibles = ["Todos"] + list(df_pedidos['Estado'].unique())
                estado_sel = st.selectbox("Estado actual:", estados_disponibles, key="filt_estado_select")
            
            df_filtrado = df_pedidos.copy()
            if isinstance(rango_fecha, (list, tuple)) and len(rango_fecha) == 2:
                df_filtrado = df_filtrado[(df_filtrado['Fecha_DT'].dt.date >= rango_fecha[0]) & (df_filtrado['Fecha_DT'].dt.date <= rango_fecha[1])]
            
            df_filtrado = df_filtrado[(df_filtrado['Monto'] >= rango_monto[0]) & (df_filtrado['Monto'] <= rango_monto[1])]
            
            if estado_sel != "Todos":
                df_filtrado = df_filtrado[df_filtrado['Estado'] == estado_sel]
                
            st.markdown(f"**Registros que coinciden con la búsqueda:** {len(df_filtrado)}")
            st.write("---")
            
            pedidos_filtrados_dict = df_filtrado.to_dict('records')
            if not pedidos_filtrados_dict:
                st.warning("No hay pedidos guardados que cumplan las condiciones del filtro.")
            else:
                for p in reversed(pedidos_filtrados_dict):
                    est = str(p.get('Estado', 'Pendiente')).strip() 
                    color_est = "🟢" if est == 'Autorizado' else "🔴" if est == 'Rechazado' else "🟡"
                    
                    with st.expander(f"{color_est} #{p.get('ID', '?')} | {p.get('Proveedor', '?')} | ${float(p.get('Monto', 0)):,.2f} | {p.get('Procedencia', '?')}"):
                        historial_lista = p.get("historial", [])
                        if not historial_lista and isinstance(p.get('Historial_JSON'), str) and p['Historial_JSON']:
                            try:
                                historial_lista = json.loads(p['Historial_JSON'])
                            except:
                                historial_lista = []
                                
                        for mov in historial_lista:
                            st.write(f"- *{mov.get('fecha', '')}* | **{mov.get('usuario', '')}** ({mov.get('accion', '')}): {mov.get('detalle', '')}")

        with tab_dashboard:
            df_gastos = df_pedidos[df_pedidos['Estado'] == 'Autorizado'].copy()
            
            if df_gastos.empty:
                st.info("💡 El Dashboard de Egresos se alimenta de pedidos en estado **'Autorizado'**. Actualmente no hay gastos registrados en la base de datos.")
            else:
                st.subheader("💰 Reporte Periódico de Montos Gastados")
                df_gastos['Mes'] = df_gastos['Fecha_DT'].dt.to_period('M').astype(str)
                
                df_resumen = df_gastos.groupby(['Mes', 'Proveedor', 'Procedencia'])['Monto'].sum().reset_index()
                df_resumen.columns = ['Período (Mes)', 'Proveedor', 'Procedencia (Destino)', 'Total Gastado ($)']
                st.markdown("**Tabla Analítica de Salidas Corporativas:**")
                st.dataframe(df_resumen.style.format({'Total Gastado ($)': '${:,.2f}'}), use_container_width=True)
                
                st.write("---")
                st.subheader("📊 Gráficas de Control y Variación Temporal")
                
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    st.markdown("**Variación de Montos por Fecha y Proveedor**")
                    df_prov = df_gastos.groupby(['Fecha_Corta', 'Proveedor'])['Monto'].sum().reset_index()
                    st.bar_chart(df_prov, x='Fecha_Corta', y='Monto', color='Proveedor', use_container_width=True)
                    
                with col_g2:
                    st.markdown("**Variación de Montos por Fecha y Procedencia (Destino)**")
                    df_proc = df_gastos.groupby(['Fecha_Corta', 'Procedencia'])['Monto'].sum().reset_index()
                    st.bar_chart(df_proc, x='Fecha_Corta', y='Monto', color='Procedencia', use_container_width=True)

# ==========================================
# VISTA NUEVA: GESTIÓN DE USUARIOS (SÓLO ADMIN)
# ==========================================
elif seleccion == "⚙️ Gestión de Usuarios" and st.session_state.rol == "Admin":
    st.title("⚙️ Panel de Control: Gestión de Usuarios")
    st.markdown("Registra nuevas cuentas corporativas resguardadas directamente en la base de datos de Google Sheets.")
    
    col_reg, col_list = st.columns([1, 1])
    
    with col_reg:
        st.subheader("📝 Registrar Nuevo Empleado")
        with st.form("form_registro_usuario", clear_on_submit=True):
            reg_user = st.text_input("Nombre de Usuario (Ej. 'juan.perez')").strip()
            reg_pass = st.text_input("Contraseña de Acceso", type="password").strip()
            reg_rol = st.selectbox("Rol Asignado en la Empresa", ["Compras", "Gerencia", "Admin"])
            btn_registrar = st.form_submit_button("Dar de Alta en la Nube", type="primary")
            
            if btn_registrar:
                if reg_user and reg_pass:
                    exito = registrar_usuario_cloud(reg_user, reg_pass, reg_rol)
                    if exito:
                        st.success(f"¡Usuario '{reg_user}' registrado con éxito en la base de datos!")
                        time.sleep(1.5)
                        st.rerun()
                    else:
                        st.error("⚠️ Ese nombre de usuario ya existe en la base de datos.")
                else:
                    st.warning("Por favor rellena todos los campos.")
                    
    with col_list:
        st.subheader("📋 Usuarios Activos")
        lista_usuarios = cargar_usuarios_cloud()
        df_usuarios = pd.DataFrame(lista_usuarios)
        if not df_usuarios.empty and 'password' in df_usuarios.columns:
            df_usuarios['password'] = "••••••••"
        st.dataframe(df_usuarios, use_container_width=True)
