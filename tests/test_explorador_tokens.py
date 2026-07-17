
// Referencias a los elementos del DOM (HTML)
const checkboxes = document.querySelectorAll('.opc-chk');
const btnSubir = document.getElementById('btn-subir');
const listaArchivos = document.getElementById('lista-archivos');
const motivoError = document.getElementById('motivo-error');
const mensajeEstado = document.getElementById('estado-mensaje');

// Explorador de directorios del servidor (reemplaza al <input type="file">
// nativo: el navegador no expone la ruta absoluta de un archivo local, y esta
// app necesita esa ruta para referenciar el archivo sin copiarlo).
const modalExplorador = document.getElementById('modal-explorador');
const rutaActualExplorador = document.getElementById('ruta-actual-explorador');
const listaExplorador = document.getElementById('lista-explorador');
const btnSubirNivel = document.getElementById('btn-subir-nivel');
const btnCerrarExplorador = document.getElementById('btn-cerrar-explorador');

// Estado del modo "Cambiar Opciones": mientras hay un archivo en edición,
// actualizarVistaAplicacion() no debe reconstruir la 1ra Sección (perdería el
// botón "Aceptar" y el bloqueo de los demás controles) ni ante el polling de
// 2s ni ante los cambios de checkbox que el propio usuario hace para elegir
// la nueva combinación.
let modoEdicionOpciones = { activo: false, archivoId: null };

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

// Abrir el explorador de directorios del servidor en vez del picker nativo
btnSubir.addEventListener('click', () => {
    modalExplorador.style.display = 'flex';
    cargarDirectorioExplorador('');
});

btnCerrarExplorador.addEventListener('click', () => {
    modalExplorador.style.display = 'none';
});

// Guardado para poder navegar hacia arriba con el botón "Subir un nivel"
let tokenPadreActualExplorador = null;

btnSubirNivel.addEventListener('click', () => {
    if (tokenPadreActualExplorador) cargarDirectorioExplorador(tokenPadreActualExplorador);
});

// Pide al backend el listado de una carpeta (GET /api/explorar) y lo renderiza.
// `token` (vacío = raíz permitida) es un token opaco minteado por una
// respuesta anterior de este mismo endpoint, nunca una ruta cruda: el
// navegador nunca vuelve a mandar una ruta de filesystem hacia el backend
// (ver CLAUDE.md "Security: path containment").
function cargarDirectorioExplorador(token) {
    fetch(`/api/explorar?token=${encodeURIComponent(token)}`)
        .then(res => res.json())
        .then(data => {
            rutaActualExplorador.innerText = data.ruta_actual_texto;
            tokenPadreActualExplorador = data.token_padre;
            btnSubirNivel.disabled = !data.token_padre;

            listaExplorador.innerHTML = '';
            data.entradas.forEach(entrada => {
                const li = document.createElement('li');
                li.className = entrada.es_carpeta ? 'entrada-carpeta' : 'entrada-archivo';
                li.innerText = (entrada.es_carpeta ? '📁 ' : '📄 ') + entrada.nombre;
                li.addEventListener('click', () => {
                    if (entrada.es_carpeta) {
                        cargarDirectorioExplorador(entrada.token);
                    } else {
                        referenciarArchivoSeleccionado(entrada.token);
                    }
                });
                listaExplorador.appendChild(li);
            });
        })
        .catch(err => console.error("Error al explorar directorio:", err));
}

// El archivo elegido en el explorador NO se sube: se envía el token que lo
// identifica (minteado por GET /api/explorar) para que el backend lo
// resuelva a su ruta real, la referencie y le anteponga el hash al nombre.
function referenciarArchivoSeleccionado(tokenArchivo) {
    modalExplorador.style.display = 'none';

    fetch('/api/subir', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            token: tokenArchivo,
            opciones: obtenerOpcionesSeleccionadas()
        })
    })
    .then(res => res.json())
    .then(data => {
        if(data.success) {
            mostrarNotificacionSubida(data.pk, data.hash_generado);
            actualizarVistaAplicacion();
        } else {
            alert(`Error de validación del backend: ${data.error}`);
        }
    })
    .catch(err => console.error("Error de red:", err));
}

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
    // Mientras el usuario está eligiendo la nueva combinación para un archivo
    // (botón "Cambiar Opciones" -> "Aceptar"), no se refresca nada: ni el
    // polling de 2s ni los propios cambios de checkbox del usuario deben
    // reconstruir la 1ra Sección hasta que confirme con "Aceptar".
    if (modoEdicionOpciones.activo) return;

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
                // El archivo se sirve desde su ubicación original por PK, no por nombre
                const urlArchivo = `/media/${file.id}`;

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
                            <button class="btn-cambiar-opciones" onclick="iniciarCambioOpciones(${file.id}, this)">Cambiar Opciones</button>
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

        // REGLA DE RENDERIZADO - 4ta Sección (Botón): siempre se actualiza,
        // independientemente de si hay una notificación de subida en pantalla.
        btnSubir.disabled = !data.valido;

        // REGLA DE RENDERIZADO - 3ra Sección (Mensaje de Control): este polling
        // corre cada 2s (ver INTERVALO_REFRESCO_MS), así que si hay una notificación
        // de subida reciente en pantalla (ver mostrarNotificacionSubida) no la
        // pisamos - se limpia sola con su propio setTimeout.
        if (!notificacionSubidaActiva) {
            if (data.valido) {
                mensajeEstado.innerText = "Agregar un nuevo archivo con el botón AGREGAR";
                mensajeEstado.className = "success-box";
            } else {
                mensajeEstado.innerText = "No se puede definir esa combinación de opciones.";
                mensajeEstado.className = "error-box";
                mensajeEstado.style.display = "block";
            }
        }
    })
    .catch(err => console.error("Error al procesar opciones:", err));
}

// Cuánto tiempo se muestra la notificación de subida en la 3ra Sección antes
// de que el polling normal (actualizarVistaAplicacion) retome el mensaje de
// control habitual.
const DURACION_NOTIFICACION_SUBIDA_MS = 4000;
let notificacionSubidaActiva = false;

// Muestra el resultado de una subida exitosa en la 3ra Sección ("Estado de
// Combinación") en vez de un alert() bloqueante. Ver el guard
// `notificacionSubidaActiva` en actualizarVistaAplicacion: sin él, el polling
// de 2s tapa este mensaje casi de inmediato.
function mostrarNotificacionSubida(pk, hashGenerado) {
    notificacionSubidaActiva = true;
    mensajeEstado.innerText = `¡Éxito! Archivo referenciado sin copiar. Registrado en BD con PK: [${pk}] Hash generado a partir de la PK: ${hashGenerado}`;
    mensajeEstado.className = "success-box";
    mensajeEstado.style.display = "block";

    setTimeout(() => {
        notificacionSubidaActiva = false;
        actualizarVistaAplicacion();
    }, DURACION_NOTIFICACION_SUBIDA_MS);
}

function confirmarYEliminar(id, nombre) {
    // Notificación nativa del navegador para confirmar la acción
    const seguro = confirm(`¿Estás seguro de que deseas eliminar el archivo "${nombre}" de la base de datos?\nEl archivo físico permanecerá en su ubicación original, solo se le quitará el prefijo de hash del nombre.`);
    
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

// Entra en modo edición para el archivo indicado: el botón que disparó el
// clic pasa a decir "Aceptar" y se bloquean el resto de los controles
// (AGREGAR ARCHIVO, "Eliminar" y "Cambiar Opciones" de los demás archivos)
// hasta que el usuario confirme la nueva combinación.
function iniciarCambioOpciones(id, boton) {
    modoEdicionOpciones = { activo: true, archivoId: id };

    btnSubir.disabled = true;
    document.querySelectorAll('.btn-eliminar, .btn-cambiar-opciones').forEach(otroBoton => {
        if (otroBoton !== boton) otroBoton.disabled = true;
    });

    boton.innerText = 'Aceptar';
    boton.onclick = () => confirmarCambioOpciones(id, boton);
}

// Envía la combinación de checkboxes actualmente marcada como la nueva
// combinación del archivo, y sale del modo edición (con éxito o sin él, para
// no dejar la interfaz bloqueada ante un error de red).
function confirmarCambioOpciones(id, boton) {
    const nuevasOpciones = obtenerOpcionesSeleccionadas();

    fetch(`/api/archivos/${id}/opciones`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ opciones: nuevasOpciones })
    })
    .then(res => res.json())
    .then(data => {
        if (!data.success) {
            alert(`Error al cambiar las opciones: ${data.error}`);
        }
    })
    .catch(err => console.error("Error de red:", err))
    .finally(() => {
        modoEdicionOpciones = { activo: false, archivoId: null };
        actualizarVistaAplicacion();
    });
}

// --- FUNCIÓN PARA CARGAR Y CONSTRUIR LAS OPCIONES EN SU ORDEN PERSISTENTE ---
// Las columnas de categoría (.categoria-col) ya no están hardcodeadas en el
// HTML: se crean aquí, una por cada categoría que devuelva GET /api/orden, y
// se agregan a #pool-categorias. Así el HTML deja de ser una fuente de verdad
// paralela - la cadena real es CSV -> seed SQL -> BD -> este fetch, y agregar
// o renombrar una categoría en el CSV/BD no requiere tocar el HTML.
function cargarOpcionesOrdenadas() {
    const poolCategorias = document.getElementById('pool-categorias');

    fetch('/api/orden')
        .then(res => res.json())
        .then(mapaOrden => {
            // Iterar sobre cada categoría devuelta por la BD (Suscripcion, Region, TipoDatos)
            Object.keys(mapaOrden).forEach(cat => {
                let contenedor = document.getElementById(`col-${cat}`);

                if (!contenedor) {
                    // Primera vez que se ve esta categoría: crear su columna
                    contenedor = document.createElement('div');
                    contenedor.className = 'categoria-col';
                    contenedor.id = `col-${cat}`;
                    contenedor.setAttribute('data-categoria', cat);

                    const h3 = document.createElement('h3');
                    h3.innerText = cat;
                    contenedor.appendChild(h3);

                    poolCategorias.appendChild(contenedor);
                }

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

                colorearOpcionesPorPosicion(contenedor);
                agregarControlNuevaOpcion(contenedor, cat);
            });

            // Quitar columnas de categorías que ya no existen en la BD (p. ej.
            // tras reseedear con un CSV que renombró o eliminó una categoría)
            document.querySelectorAll('.categoria-col').forEach(col => {
                const cat = col.getAttribute('data-categoria');
                if (!(cat in mapaOrden)) col.remove();
            });

            // Re-vincular los eventos de escucha a los nuevos checkboxes creados dinámicamente
            document.querySelectorAll('.opc-chk').forEach(checkbox => {
                checkbox.addEventListener('change', actualizarVistaAplicacion);
            });

            // Activar las funciones mecánicas de Arrastrar y Soltar en las columnas
            configurarDragAndDrop();
        });
}

// Colorea cada opción de una columna según su posición: verde arriba (primero),
// rojo abajo (último), con una interpolación de tono (hue) entre ambos. Se
// aplica vía la variable CSS --color-posicion para que la regla .dragging siga
// pudiendo sobreescribir el color mientras se arrastra un elemento.
function colorearOpcionesPorPosicion(columna) {
    const items = [...columna.querySelectorAll('.opcion-item')];
    const total = items.length;

    items.forEach((item, indice) => {
        const proporcion = total > 1 ? indice / (total - 1) : 0;
        const tono = 120 * (1 - proporcion); // 120° = verde, 0° = rojo
        item.style.setProperty('--color-posicion', `hsl(${tono}, 70%, 88%)`);
    });
}

// Agrega al final de la columna el control para crear opciones nuevas: un
// botón "Agregar" que, al hacer clic, se reemplaza a sí mismo por un campo de
// texto. Al escribir el nombre y presionar Enter se crea la opción y toda la
// columna se recarga (cargarOpcionesOrdenadas), lo que naturalmente deja la
// opción nueva en la lista seguida otra vez del botón "Agregar" al final.
function agregarControlNuevaOpcion(contenedor, categoria) {
    const boton = document.createElement('button');
    boton.type = 'button';
    boton.className = 'btn-agregar-opcion';
    boton.innerText = 'Agregar';

    boton.addEventListener('click', () => {
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'input-nueva-opcion';
        input.placeholder = 'Nombre de la opción...';

        input.addEventListener('keydown', e => {
            if (e.key !== 'Enter') return;
            const opcionId = input.value.trim();
            if (!opcionId) return;
            crearNuevaOpcion(categoria, opcionId);
        });

        boton.replaceWith(input);
        input.focus();
    });

    contenedor.appendChild(boton);
}

// Envía la nueva opción al backend; si se creó, recarga la interfaz de
// opciones completa para reflejarla en su columna.
function crearNuevaOpcion(categoria, opcionId) {
    fetch('/api/orden/agregar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ categoria: categoria, opcion_id: opcionId })
    })
    .then(res => res.json())
    .then(data => {
        if (!data.success) {
            alert(`No se pudo agregar la opción: ${data.error}`);
            return;
        }
        cargarOpcionesOrdenadas();
    })
    .catch(err => console.error("Error de red:", err));
}

// --- MECANISMO DRAG AND DROP NATIVO DEL NAVEGADOR ---
// Las opciones solo se pueden reordenar DENTRO de su propia categoría; no está
// permitido moverlas a otra columna. `columnaOrigenActual` recuerda de qué
// columna partió el arrastre, para que `dragover` ignore cualquier columna
// distinta: el elemento nunca se reparenta fuera de su categoría de origen, así
// que al soltar simplemente permanece donde estaba (sin mensaje de error).
let columnaOrigenActual = null;

function configurarDragAndDrop() {
    const columnas = document.querySelectorAll('.categoria-col');

    columnas.forEach(col => {
        col.addEventListener('dragstart', e => {
            if (e.target.classList.contains('opcion-item')) {
                e.target.classList.add('dragging');
                columnaOrigenActual = col;
            }
        });

        col.addEventListener('dragend', e => {
            if (e.target.classList.contains('opcion-item')) {
                e.target.classList.remove('dragging');

                // Al terminar el movimiento, guardar la nueva posición en la DB
                guardarNuevoOrdenFisico(col);
                columnaOrigenActual = null;
            }
        });

        col.addEventListener('dragover', e => {
            // Ignorar columnas que no son la de origen: no se permite mover
            // opciones entre categorías, solo reordenarlas dentro de la misma.
            if (col !== columnaOrigenActual) return;

            e.preventDefault(); // Necesario para permitir el Drop
            const elementoArrastrado = document.querySelector('.dragging');
            const itemCercano = obtenerElementoAbajo(col, e.clientY);

            if (itemCercano == null) {
                col.appendChild(elementoArrastrado);
            } else {
                col.insertBefore(elementoArrastrado, itemCercano);
            }

            // Recalcular los colores en vivo: la posición de varias opciones
            // pudo cambiar al reacomodarse alrededor del elemento arrastrado.
            colorearOpcionesPorPosicion(col);
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

// Refrescar periódicamente la 1ra Sección (listado de archivos). Un archivo
// puede eliminarse fuera de la app -ej. borrado manual detectado por
// storage_database/watcher.py-, lo cual actualiza la base de datos pero no
// dispara ningún evento en el navegador; sin este refresco, la lista seguiría
// mostrando el archivo ya eliminado hasta la próxima interacción del usuario.
const INTERVALO_REFRESCO_MS = 2000;
setInterval(actualizarVistaAplicacion, INTERVALO_REFRESCO_MS);
