import streamlit as st
import json
import os
import base64
from datetime import datetime
import pandas as pd

# Configuración de página más ancha para ver mejor los archivos
st.set_page_config(page_title="Gestión de Pedidos", layout="wide")

ARCHIVO_DATOS = "pedidos.json"
CARPETA_UPLOADS = "uploads"

# Crear carpeta de subidas si no existe
if not os.path.exists(CARPETA_UPLOADS):
    os.makedirs(CARPETA_UPLOADS)

def cargar_pedidos():
    if os.path.exists(ARCHIVO_DATOS):
        with open(ARCHIVO_DATOS, "r") as f:
            return json.load(f)
    return []

def guardar_pedidos(pedidos):
    with open(ARCHIVO_DATOS, "w") as f:
        json.dump(pedidos, f, indent=4)

def previsualizar_archivo(ruta_archivo):
    """Función para mostrar PDF o Excel directamente en la pantalla"""
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
        st.info("Vista previa no disponible. Por favor descarga el archivo para verlo.")

st.title("Sistema de Autorización de Compras")

# Menú lateral
rol = st.sidebar.radio("Simulador de Rol:", ["Área de Compras", "Gerencia", "Reportes de Movimientos"])
pedidos = cargar_pedidos()

# ==========================================
# VISTA: ÁREA DE COMPRAS
# ==========================================
if rol == "Área de Compras":
    tab1, tab2 = st.tabs(["📝 Crear Nuevo Pedido", "⚠️ Pedidos Rechazados (Revisión)"])
    
    with tab1:
        st.subheader("Registrar nuevo pedido")
        with st.form("form_pedido"):
            proveedor = st.text_input("Nombre del Proveedor")
            monto = st.number_input("Monto Total ($)", min_value=0.0, format="%.2f")
            
            # Lógica de Procedencia
            proc_sel = st.selectbox("Procedencia del Pedido", ["Mercado Libre", "Amazon", "Centro", "Otra"])
            procedencia_final = st.text_input("Especificar procedencia") if proc_sel == "Otra" else proc_sel
            
            archivo = st.file_uploader("Sube la cotización (PDF/Excel)", type=["pdf", "xlsx", "xls"])
            enviado = st.form_submit_button("Enviar a Gerencia")
            
            if enviado and proveedor and monto > 0 and archivo:
                # Guardar archivo físicamente
                ruta_guardado = os.path.join(CARPETA_UPLOADS, archivo.name)
                with open(ruta_guardado, "wb") as f:
                    f.write(archivo.getbuffer())
                
                fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                nuevo_pedido = {
                    "id": len(pedidos) + 1,
                    "fecha_creacion": fecha_actual,
                    "proveedor": proveedor,
                    "monto": monto,
                    "procedencia": procedencia_final,
                    "archivo_nombre": archivo.name,
                    "ruta_archivo": ruta_guardado,
                    "estado": "Pendiente",
                    "historial": [
                        {"fecha": fecha_actual, "usuario": "Compras", "accion": "Creación", "detalle": "Pedido enviado a gerencia"}
                    ]
                }
                pedidos.append(nuevo_pedido)
                guardar_pedidos(pedidos)
                st.success("¡Pedido enviado exitosamente para su autorización!")

    with tab2:
        st.subheader("Pedidos que requieren corrección")
        rechazados = [p for p in pedidos if p["estado"] == "Rechazado"]
        
        if not rechazados:
            st.info("No hay pedidos rechazados en este momento.")
        else:
            for p in rechazados:
                with st.expander(f"❌ Pedido #{p['id']} - {p['proveedor']} (Rechazado)"):
                    st.write("### Últimos comentarios de Gerencia:")
                    # Mostrar historial de comentarios
                    for h in p["historial"]:
                        if h["accion"] in ["Rechazo", "Comentario"]:
                            st.info(f"**{h['fecha']} - {h['accion']}:** {h['detalle']}")
                    
                    if st.button("Reenviar a Gerencia para revisión", key=f"reenviar_{p['id']}"):
                        p["estado"] = "Pendiente"
                        p["historial"].append({
                            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "usuario": "Compras", "accion": "Reenvío", "detalle": "Pedido ajustado y reenviado"
                        })
                        guardar_pedidos(pedidos)
                        st.rerun()

# ==========================================
# VISTA: GERENCIA
# ==========================================
elif rol == "Gerencia":
    st.header("✅ Pedidos Pendientes de Autorizar")
    pendientes = [p for p in pedidos if p["estado"] == "Pendiente"]
    
    if not pendientes:
        st.success("No hay pedidos pendientes de revisión. ¡Todo al día!")
    else:
        for pedido in pendientes:
            with st.container():
                st.markdown(f"### Pedido #{pedido['id']} - {pedido['proveedor']}")
                
                col_datos, col_preview = st.columns([1, 2])
                
                with col_datos:
                    st.write(f"**Monto:** ${pedido['monto']:,.2f}")
                    st.write(f"**Procedencia:** {pedido['procedencia']}")
                    st.write(f"**Fecha:** {pedido['fecha_creacion']}")
                    
                    st.write("---")
                    comentario = st.text_area("Agregar Comentarios:", key=f"com_{pedido['id']}")
                    
                    # Botones de acción
                    if st.button("💬 Enviar solo comentario", key=f"solo_com_{pedido['id']}"):
                        if comentario:
                            pedido["historial"].append({
                                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "usuario": "Gerencia", "accion": "Comentario", "detalle": comentario
                            })
                            guardar_pedidos(pedidos)
                            st.success("Comentario guardado sin alterar el estado del pedido.")
                            st.rerun()
                        else:
                            st.warning("Escribe un comentario primero.")

                    col_aut, col_rech = st.columns(2)
                    with col_aut:
                        if st.button("✔️ Autorizar", type="primary", key=f"aut_{pedido['id']}"):
                            pedido["estado"] = "Autorizado"
                            pedido["historial"].append({
                                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "usuario": "Gerencia", "accion": "Autorización", "detalle": comentario or "Sin comentarios"
                            })
                            guardar_pedidos(pedidos)
                            st.rerun()
                    with col_rech:
                        if st.button("❌ Rechazar", key=f"rech_{pedido['id']}"):
                            pedido["estado"] = "Rechazado"
                            pedido["historial"].append({
                                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "usuario": "Gerencia", "accion": "Rechazo", "detalle": comentario or "Rechazado sin comentarios específicos"
                            })
                            guardar_pedidos(pedidos)
                            st.rerun()
                            
                with col_preview:
                    st.write("**Previsualización del Documento:**")
                    previsualizar_archivo(pedido["ruta_archivo"])
                st.divider()

# ==========================================
# VISTA: REPORTES Y MOVIMIENTOS
# ==========================================
elif rol == "Reportes de Movimientos":
    st.header("📊 Historial General y Reportes")
    
    if not pedidos:
        st.info("No hay datos registrados aún.")
    else:
        for p in reversed(pedidos): # Mostrar los más recientes primero
            color_estado = "🟢" if p['estado'] == 'Autorizado' else "🔴" if p['estado'] == 'Rechazado' else "🟡"
            
            with st.expander(f"{color_estado} Pedido #{p['id']} | {p['proveedor']} | ${p['monto']:,.2f} | {p['procedencia']}"):
                st.write("**Historial de acciones:**")
                for mov in p["historial"]:
                    st.write(f"- *{mov['fecha']}* | **{mov['usuario']}** ({mov['accion']}): {mov['detalle']}")