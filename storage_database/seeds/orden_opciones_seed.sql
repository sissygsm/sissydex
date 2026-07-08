BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS orden_opciones (
    categoria TEXT NOT NULL,
    opcion_id TEXT NOT NULL,
    posicion_y INTEGER NOT NULL,
    PRIMARY KEY (categoria, opcion_id)
);

DELETE FROM orden_opciones;

INSERT INTO orden_opciones (categoria, opcion_id, posicion_y) VALUES 
('Grupo_c', 'o', 1),
('Grupo_c', 'u', 2),
('Grupo_c', 'aa', 3),
('Grupo_c', 'hh', 4),
('Grupo_c', 'll', 5),
('Grupo_c', 'pp', 6),
('Grupo_c', 'tt', 7),
('Grupo_c', 'ww', 8),
('Grupo_e', 'p', 1),
('Grupo_e', 'v', 2),
('Grupo_e', 'bb', 3),
('Grupo_e', 'ii', 4),
('Grupo_e', 'mm', 5),
('Grupo_e', 'qq', 6),
('Grupo_g', 'q', 1),
('Grupo_g', 'w', 2),
('Grupo_g', 'cc', 3),
('Grupo_g', 'jj', 4),
('Grupo_g', 'nn', 5),
('Grupo_g', 'rr', 6),
('Grupo_g', 'uu', 7),
('Grupo_g', 'xx', 8),
('Grupo_g', 'zz', 9),
('Grupo_g', 'bbb', 10),
('Grupo_i', 'r', 1),
('Grupo_i', 'x', 2),
('Grupo_i', 'dd', 3),
('Grupo_i', 'kk', 4),
('Grupo_i', 'oo', 5),
('Grupo_i', 'ss', 6),
('Grupo_i', 'vv', 7),
('Grupo_i', 'yy', 8),
('Grupo_i', 'aaa', 9),
('Grupo_i', 'ccc', 10),
('Grupo_i', 'ddd', 11),
('Grupo_i', 'eee', 12),
('Grupo_l', 's', 1),
('Grupo_l', 'y', 2),
('Grupo_l', 'ii', 3),
('Grupo_n', 't', 1),
('Grupo_n', 'z', 2),
('Grupo_n', 'jj', 3);

COMMIT;

