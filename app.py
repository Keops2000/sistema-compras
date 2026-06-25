import streamlit as st
import json
import os
import base64
from datetime import datetime
import pandas as pd

# Configuración de página
st.set_page_config(page_title="Sistema de Compras - Abastecedora Keops 2000", layout="wide")

ARCHIVO_DATOS = "pedidos.json"
ARCHIVO_USUARIOS = "usuarios.json"
CARPETA_UPLOADS = "uploads"

# Crear carpeta de subidas si no existe
if not os.path.exists(CARPETA_UPLOADS):
    os.makedirs(CARPETA_UPLOADS)

# ==========================================
# FUNCIONES DE CARGA Y GUARDADO
# ==========================================
def cargar_pedidos():
    if os.path.exists(ARCHIVO_DATOS):
        with open(ARCHIVO_DATOS, "r") as f:
            return json.load(f)
    return []

def guardar_pedidos(pedidos):
    with open(ARCHIVO_DATOS, "w") as f:
        json.dump(pedidos, f, indent=4)

def cargar_usuarios():
    if os.path.exists(ARCHIVO_USUARIOS):
        with open(ARCHIVO_USUARIOS, "r") as f:
            return json.load(f)
    # Usuario administrador por defecto si no existe el archivo
    usuarios_base = [{"usuario": "admin", "password": "123", "rol": "Admin"}]
    guardar_usuarios(usuarios_base)
    return usuarios_base

def guardar_usuarios(usuarios):
    with open(ARCHIVO_USUARIOS, "w") as f:
        json.dump(usuarios, f, indent=4)

def previsualizar_archivo(ruta_archivo):
    if not os.path.exists(ruta_archivo):
        st.warning("El archivo no se encontró.")
        return
    ext = ruta_archivo.split('.')[-1].lower()
    if ext == 'pdf':
        with open(ruta_archivo, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode('utf-8')
        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
        st.markdown(pdf_display, unsafe_allow_html=True)
    elif ext in ['xls', 'xlsx']:
        try:
            df = pd.read_excel(ruta_archivo)
            st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.error("Error al leer el archivo Excel.")
    else:
        st.info("Vista previa no disponible.")

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
        with st.form("login_form"):
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
    st.stop() # Detiene la ejecución del resto de la app si no hay sesión

# ==========================================
# MENÚ LATERAL SEGÚN ROL
# ==========================================
st.sidebar.title(f"👤 Bienvenido, {st.session_state.usuario}")
st.sidebar.markdown(f"**Rol actual:** {st.session_state.rol}")

# Definir a qué pestañas tiene acceso cada rol
opciones_menu = []
if st.session_state.rol == "Compras":
    opciones_menu = ["Área de Compras", "Reportes de Movimientos"]
elif st.session_state.rol == "Gerencia":
    opciones_menu = ["Pedidos por Autorizar", "Reportes de Movimientos"]
elif st.session_state.rol == "Admin":
    opciones_menu = ["Área de Compras", "Pedidos por Autorizar", "Reportes de Movimientos", "Gestión de Usuarios"]

seleccion = st.sidebar.radio("Menú de Navegación", opciones_menu)

if st.sidebar.button("🚪 Cerrar Sesión"):
    st.session_state.logged_in = False
    st.session_state.usuario = ''
    st.session_state.rol = ''
    st.rerun()

pedidos = cargar_pedidos()

# ==========================================
# VISTA: ÁREA DE COMPRAS
# ==========================================
if seleccion == "Área de Compras":
    st.title("🛒 Área de Compras")
    tab1, tab2 = st.tabs(["📝 Crear Nuevo Pedido", "⚠️ Pedidos Rechazados (Revisión)"])
    
    with tab1:
        with st.form("form_pedido"):
            proveedor = st.text_input("Nombre del Proveedor")
            monto = st.number_input("Monto Total ($)", min_value=0.0, format="%.2f")
            proc_sel = st.selectbox("Procedencia del Pedido", ["Mercado Libre", "Amazon", "Centro", "Otra"])
            procedencia_final = st.text_input("Especificar procedencia") if proc_sel == "Otra" else proc_sel
            archivo = st.file_uploader("Sube la cotización (PDF/Excel)", type=["pdf", "xlsx", "xls"])
            enviado = st.form_submit_button("Enviar a Gerencia")
            
            if enviado and proveedor and monto > 0 and archivo:
                ruta_guardado = os.path.join(CARPETA_UPLOADS, archivo.name)
                with open(ruta_guardado, "wb") as f:
                    f.write(archivo.getbuffer())
                
                fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                nuevo_pedido = {
                    "id": len(pedidos) + 1, "fecha_creacion": fecha_actual, "proveedor": proveedor,
                    "monto": monto, "procedencia": procedencia_final, "archivo_nombre": archivo.name,
                    "ruta_archivo": ruta_guardado, "estado": "Pendiente",
                    "historial": [{"fecha": fecha_actual, "usuario": st.session_state.usuario, "accion": "Creación", "detalle": "Enviado a gerencia"}]
                }
                pedidos.append(nuevo_pedido)
                guardar_pedidos(pedidos)
                st.success("¡Pedido enviado exitosamente!")

    with tab2:
        rechazados = [p for p in pedidos if p["estado"] == "Rechazado"]
        if not rechazados:
            st.info("No hay pedidos rechazados.")
        else:
            for p in rechazados:
                with st.expander(f"❌ Pedido #{p['id']} - {p['proveedor']} (Rechazado)"):
                    for h in p.get("historial", []):
                        if h["accion"] in ["Rechazo", "Comentario"]:
                            st.info(f"**{h['fecha']} - {h['usuario']}:** {h['detalle']}")
                    if st.button("Reenviar a revisión", key=f"reenviar_{p['id']}"):
                        p["estado"] = "Pendiente"
                        p["historial"].append({"fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "usuario": st.session_state.usuario, "accion": "Reenvío", "detalle": "Pedido ajustado"})
                        guardar_pedidos(pedidos)
                        st.rerun()

# ==========================================
# VISTA: GERENCIA
# ==========================================
elif seleccion == "Pedidos por Autorizar":
    st.title("✅ Autorización de Pedidos")
    pendientes = [p for p in pedidos if p["estado"] == "Pendiente"]
    
    if not pendientes:
        st.success("No hay pedidos pendientes de revisión.")
    else:
        for pedido in pendientes:
            st.markdown(f"### Pedido #{pedido['id']} - {pedido['proveedor']}")
            col_datos, col_preview = st.columns([1, 2])
            with col_datos:
                st.write(f"**Monto:** ${pedido['monto']:,.2f} | **Procedencia:** {pedido['procedencia']}")
                comentario = st.text_area("Comentarios:", key=f"com_{pedido['id']}")
                
                if st.button("💬 Enviar solo comentario", key=f"solo_com_{pedido['id']}"):
                    if comentario:
                        pedido["historial"].append({"fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "usuario": st.session_state.usuario, "accion": "Comentario", "detalle": comentario})
                        guardar_pedidos(pedidos)
                        st.success("Comentario guardado.")
                        st.rerun()
                
                col_aut, col_rech = st.columns(2)
                with col_aut:
                    if st.button("✔️ Autorizar", type="primary", key=f"aut_{pedido['id']}"):
                        pedido["estado"] = "Autorizado"
                        pedido["historial"].append({"fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "usuario": st.session_state.usuario, "accion": "Autorización", "detalle": comentario or "Sin comentarios"})
                        guardar_pedidos(pedidos)
                        st.rerun()
                with col_rech:
                    if st.button("❌ Rechazar", key=f"rech_{pedido['id']}"):
                        pedido["estado"] = "Rechazado"
                        pedido["historial"].append({"fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "usuario": st.session_state.usuario, "accion": "Rechazo", "detalle": comentario or "Rechazado sin comentarios"})
                        guardar_pedidos(pedidos)
                        st.rerun()
            with col_preview:
                previsualizar_archivo(pedido["ruta_archivo"])
            st.divider()

# ==========================================
# VISTA: REPORTES
# ==========================================
elif seleccion == "Reportes de Movimientos":
    st.title("📊 Reportes y Auditoría")
    if not pedidos:
        st.info("No hay datos.")
    else:
        for p in reversed(pedidos):
            color = "🟢" if p['estado'] == 'Autorizado' else "🔴" if p['estado'] == 'Rechazado' else "🟡"
            with st.expander(f"{color} #{p['id']} | {p['proveedor']} | ${p['monto']:,.2f} | {p['procedencia']}"):
                for mov in p.get("historial", []):
                    st.write(f"- *{mov['fecha']}* | **{mov['usuario']}** ({mov['accion']}): {mov['detalle']}")

# ==========================================
# VISTA: ADMINISTRADOR (Gestión de Usuarios)
# ==========================================
elif seleccion == "Gestión de Usuarios":
    st.title("⚙️ Gestión de Usuarios del Sistema")
    usuarios = cargar_usuarios()
    
    st.subheader("Crear Nuevo Usuario")
    with st.form("nuevo_usuario_form"):
        nuevo_user = st.text_input("Nombre de Usuario")
        nueva_pass = st.text_input("Contraseña")
        nuevo_rol = st.selectbox("Asignar Rol", ["Compras", "Gerencia", "Admin"])
        if st.form_submit_button("Crear Usuario"):
            if nuevo_user and nueva_pass:
                # Verificar que no exista ya
                if any(u['usuario'] == nuevo_user for u in usuarios):
                    st.error("El usuario ya existe.")
                else:
                    usuarios.append({"usuario": nuevo_user, "password": nueva_pass, "rol": nuevo_rol})
                    guardar_usuarios(usuarios)
                    st.success(f"Usuario {nuevo_user} creado con éxito.")
                    st.rerun()
            else:
                st.warning("Llena todos los campos.")
    
    st.markdown("---")
    st.subheader("Usuarios Actuales")
    for i, u in enumerate(usuarios):
        col1, col2, col3 = st.columns([2, 2, 1])
        col1.write(f"**Usuario:** {u['usuario']}")
        col2.write(f"**Rol:** {u['rol']}")
        
        # Evitar que el admin se borre a sí mismo accidentalmente
        if u['usuario'] != st.session_state.usuario:
            if col3.button("🗑️ Eliminar", key=f"del_{i}"):
                usuarios.pop(i)
                guardar_usuarios(usuarios)
                st.rerun()
