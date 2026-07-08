
// Referencias a los elementos del DOM (HTML)
const checkboxes = document.querySelectorAll('.opc-chk');
const btnSubir = document.getElementById('btn-subir');
const inputArchivo = document.getElementById('input-archivo-nativo');
const listaArchivos = document.getElementById('lista-archivos');
const motivoError = document.getElementById('motivo-error');
const mensajeEstado = document.getElementById('estado-mensaje');

// Diccionario con los textos amigables que el usuario final debe leer en los controles.
// PENDIENTE: tras el nuevo seed de orden_opciones (Grupo_c, Grupo_e, Grupo_g, Grupo_i,
// Grupo_l, Grupo_n) los códigos antiguos (Opcion_Free, Region_LATAM, etc.) ya no existen.
// Los nuevos códigos (a, b, aa, hh...) aún no tienen significado de negocio definido, así
// que se deja vacío a propósito: el fallback de abajo (diccionarioTextos[id] || id) muestra
// el código crudo hasta que se agreguen sus etiquetas reales aquí.
const diccionarioTextos = {};

// --- EVENTOS DE ESCUCHA ---

// Detectar cambios en las casillas de verificación
checkboxes.forEach(checkbox => {
    checkbox.addEventListener('change', actualizarVistaAplicacion);
});

// Forzar la apertura del buscador nativo de Windows desde el botón estilizado
btnSubir.addEventListener('click', () => {
    inputArchivo.click();
});

// Capturar el archivo seleccionado y enviarlo al Backend de Python
inputArchivo.addEventListener('change', function() {
    if (this.files.length === 0) return;
    
    const archivoSeleccionado = this.files[0];
    const formData = new FormData();
    
    // Adjuntar el archivo binario real
    formData.append('archivo', archivoSeleccionado);
    
    // Adjuntar el listado de opciones de negocio seleccionadas actualmente
    obtenerOpcionesSeleccionadas().forEach(opcion => {
        formData.append('opciones', opcion);
    });

    // Envío Multipart a la API de Flask
    fetch('/api/subir', {
        method: 'POST',
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        if(data.success) {
            alert(`¡Éxito!\nArchivo movido a 'media/'.\nRegistrado en BD con PK: [${data.pk}]\nHash generado a partir de la PK: ${data.hash_generado}`);
            actualizarVistaAplicacion(); 
        } else {
            alert(`Error de validación del backend: ${data.error}`);
        }
    })
    .catch(err => console.error("Error de red:", err));
    
    // Limpiar el input para permitir cargas sucesivas del mismo archivo
    this.value = '';
});

// --- FUNCIONES AUXILIARES DE PROCESAMIENTO ---

// Extrae un array de texto con los checkboxes que están marcados
function obtenerOpcionesSeleccionadas() {
    const seleccionadas = [];
    document.querySelectorAll('.opc-chk:checked').forEach(chk => {
        seleccionadas.push(chk.value);
    });
    return seleccionadas;
}

// Sincroniza el estado de las 4 secciones consultando al Backend
function actualizarVistaAplicacion() {
    const opciones = obtenerOpcionesSeleccionadas();

    fetch('/api/procesar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ opciones: opciones })
    })
    .then(res => res.json())
    .then(data => {
        // Resetear contenedor de la 1ra sección
        listaArchivos.innerHTML = "";
        
        // REGLA DE RENDERIZADO - 1ra Sección (Resultados del filtro)
        if (!data.valido) {
            listaArchivos.innerHTML = `<li class="txt-muted" style="color: #ef4444;">Combinación bloqueada por reglas de negocio. Modifique sus filtros.</li>`;
        } else if (data.archivos.length === 0) {
            listaArchivos.innerHTML = `<li class="txt-muted">📂 No hay archivos registrados para esta combinación exacta de opciones.</li>`;
        } else {
            data.archivos.forEach(file => {
                // Creamos la URL que apunta al endpoint de Flask que acabamos de crear
                const urlArchivo = `/media/${file.nombre}`;

                listaArchivos.innerHTML += `
                    <li>
                        <span>
                            📄 
                            <a href="${urlArchivo}" target="_blank" class="file-link">
                                <b>${file.nombre}</b>
                            </a>
                        </span>
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <span class="badge-info">PK: ${file.id}</span>
                            <span class="badge-info" style="background:#bfdbfe;">Hash: ${file.hash}</span>
                            <button class="btn-eliminar" onclick="confirmarYEliminar(${file.id}, '${file.nombre}')">Eliminar</button>
                        </div>
                    </li>`;

            });
        }

        // REGLA DE RENDERIZADO - 2da Sección (Cuadro de incompatibilidad)
        if (!data.valido) {
            motivoError.innerText = data.mensaje;
            motivoError.style.display = "block";
        } else {
            motivoError.style.display = "none";
        }

        // REGLA DE RENDERIZADO - 3ra y 4ta Sección (Mensajes de Control y Botón)
        if (data.valido) {
            mensajeEstado.innerText = "Agregar un nuevo archivo con el botón AGREGAR";
            mensajeEstado.className = "success-box";
            btnSubir.disabled = false;
        } else {
            mensajeEstado.innerText = "No se puede definir esa combinación de opciones.";
            mensajeEstado.className = "error-box";
            mensajeEstado.style.display = "block";
            btnSubir.disabled = true;
        }
    })
    .catch(err => console.error("Error al procesar opciones:", err));
}

function confirmarYEliminar(id, nombre) {
    // Notificación nativa del navegador para confirmar la acción
    const seguro = confirm(`¿Estás seguro de que deseas eliminar el archivo "${nombre}"?\nEsta acción lo borrará del disco y de la base de datos.`);
    
    if (!seguro) return; // Si el usuario cancela, no hace nada

    // Petición HTTP DELETE al backend usando la PK
    fetch(`/api/eliminar/${id}`, {
        method: 'DELETE'
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            alert("Archivo eliminado con éxito.");
            actualizarVistaAplicacion(); // Refrescar la lista de la 1ra Sección
        } else {
            alert(`Error del servidor: ${data.error}`);
        }
    })
    .catch(err => console.error("Error de red:", err));
}

// --- FUNCIÓN PARA CARGAR Y CONSTRUIR LAS OPCIONES EN SU ORDEN PERSISTENTE ---
function cargarOpcionesOrdenadas() {
    fetch('/api/orden')
        .then(res => res.json())
        .then(mapaOrden => {
            // Iterar sobre cada categoría devuelta por la BD (Suscripcion, Region, TipoDatos)
            Object.keys(mapaOrden).forEach(cat => {
                const contenedor = document.getElementById(`col-${cat}`);
                if (!contenedor) return;
                
                // Conservar solo el encabezado H3
                const h3 = contenedor.querySelector('h3');
                contenedor.innerHTML = '';
                contenedor.appendChild(h3);

                // Recorrer las opciones en el estricto orden posicional Y devuelto
                mapaOrden[cat].forEach(opcionId => {
                    const textoLegible = diccionarioTextos[opcionId] || opcionId;
                    
                    // Crear fila contenedora arrastrable (Y)
                    const item = document.createElement('div');
                    item.className = 'opcion-item';
                    item.draggable = true; // Activa la propiedad física de arrastre
                    item.setAttribute('data-id', opcionId);

                    item.innerHTML = `
                        <input type="checkbox" class="opc-chk" value="${opcionId}" id="chk-${opcionId}">
                        <label for="chk-${opcionId}">${textoLegible}</label>
                        <span class="handle-drag">☰</span>
                    `;

                    contenedor.appendChild(item);
                });
            });

            // Re-vincular los eventos de escucha a los nuevos checkboxes creados dinámicamente
            document.querySelectorAll('.opc-chk').forEach(checkbox => {
                checkbox.addEventListener('change', actualizarVistaAplicacion);
            });

            // Activar las funciones mecánicas de Arrastrar y Soltar en las columnas
            configurarDragAndDrop();
        });
}

// --- MECANISMO DRAG AND DROP NATIVO DEL NAVEGADOR ---
function configurarDragAndDrop() {
    const columnas = document.querySelectorAll('.categoria-col');

    columnas.forEach(col => {
        col.addEventListener('dragstart', e => {
            if (e.target.classList.contains('opcion-item')) {
                e.target.classList.add('dragging');
            }
        });

        col.addEventListener('dragend', e => {
            if (e.target.classList.contains('opcion-item')) {
                e.target.classList.remove('dragging');
                
                // Al terminar el movimiento, guardar la nueva posición en la DB
                guardarNuevoOrdenFisico(col);
            }
        });

        col.addEventListener('dragover', e => {
            e.preventDefault(); // Necesario para permitir el Drop
            const elementoArrastrado = document.querySelector('.dragging');
            const itemCercano = obtenerElementoAbajo(col, e.clientY);
            
            if (itemCercano == null) {
                col.appendChild(elementoArrastrado);
            } else {
                col.insertBefore(elementoArrastrado, itemCercano);
            }
        });
    });
}

// Determina matemáticamente cuál es la fila Y más cercana a la posición del cursor
function obtenerElementoAbajo(columna, yCursor) {
    const elementosArrastrables = [...columna.querySelectorAll('.opcion-item:not(.dragging)')];

    return elementosArrastrables.reduce((masCercano, hijo) => {
        const caja = hijo.getBoundingClientRect();
        const offset = yCursor - caja.top - caja.height / 2;
        if (offset < 0 && offset > masCercano.offset) {
            return { offset: offset, element: hijo };
        } else {
            return masCercano;
        }
    }, { offset: Number.NEGATIVE_INFINITY }).element;
}

// Envía el nuevo orden vectorial del bloque al backend
function guardarNuevoOrdenFisico(columna) {
    const categoria = columna.getAttribute('data-categoria');
    const items = [...columna.querySelectorAll('.opcion-item')];
    const listaIdsOrdenados = items.map(item => item.getAttribute('data-id'));

    fetch('/api/orden/guardar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            categoria: categoria,
            opciones: listaIdsOrdenados
        })
    });
}

// Reemplazar la invocación directa al final de tu app.js para cargar con prioridad el orden de BD
cargarOpcionesOrdenadas();


// Inicializar la interfaz vacía al cargar la ventana
actualizarVistaAplicacion();
