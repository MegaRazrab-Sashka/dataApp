"""Слой доступа к PostgreSQL для телефонного справочника."""
from __future__ import annotations

from dataclasses import dataclass
import psycopg
from psycopg import sql

class QueryError(Exception):
    """Ошибка валидации запроса."""
    pass


class Database:
    def __init__(self) -> None:
        self.conn: psycopg.Connection | None = None
        self._main_cols = {}  # Сюда сохраним точные имена колонок

    def connect(self, host: str, port: int, dbname: str, user: str, password: str) -> None:
        self.close()
        self.conn = psycopg.connect(
            host=host, port=port, dbname=dbname, user=user, password=password,
            connect_timeout=5, autocommit=True, options="-c statement_timeout=10000"
        )
        self._main_cols = self._get_main_columns()

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def _require_conn(self) -> psycopg.Connection:
        if self.conn is None:
            raise QueryError("Нет подключения к базе данных")
        return self.conn

    def _get_main_columns(self) -> dict:
        """Автоматически определяет точные имена колонок в таблице main."""
        conn = self._require_conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'main'
            """)
            cols = [r[0] for r in cur.fetchall()]

        # Ищем нужные колонки без учета регистра
        mapping = {}
        for c in cols:
            cl = c.lower()
            if 'name' in cl:
                mapping['name'] = c
            elif cl == 'fam':
                mapping['fam'] = c
            elif cl == 'otc':
                mapping['otc'] = c
            elif cl == 'street':
                mapping['street'] = c
            elif cl == 'kor':
                mapping['kor'] = c
            elif cl == 'dom':
                mapping['dom'] = c
            elif cl == 'tel':
                mapping['tel'] = c

        # Если вдруг name_integer не нашли по слову name, даем дефолт
        if 'name' not in mapping: mapping['name'] = 'name_integer'
        return mapping

    def get_dict(self, table_name: str, id_col: str, val_col: str) -> list[tuple[int, str]]:
        conn = self._require_conn()
        query = sql.SQL("SELECT {id}, {val} FROM {tbl} ORDER BY {val}").format(
            id=sql.Identifier(id_col), val=sql.Identifier(val_col), tbl=sql.Identifier(table_name)
        )
        with conn.cursor() as cur:
            cur.execute(query)
            return [(r[0], r[1]) for r in cur.fetchall()]

    def get_records(self, filters: dict = None, limit: int = 1000) -> tuple[list[str], list[tuple]]:
        """Получает записи с учетом фильтров."""
        if filters is None:
            filters = {}

        conn = self._require_conn()

        name_col = sql.Identifier(self._main_cols['name'])
        fam_col = sql.Identifier(self._main_cols['fam'])
        otc_col = sql.Identifier(self._main_cols['otc'])
        street_col = sql.Identifier(self._main_cols['street'])
        kor_col = sql.Identifier(self._main_cols['kor'])
        dom_col = sql.Identifier(self._main_cols['dom'])
        tel_col = sql.Identifier(self._main_cols['tel'])

        query = sql.SQL("""
            SELECT 
                m.uid, 
                f.f_value AS fam, 
                n.name_value AS name, 
                o.o_value AS otc, 
                s.s_value AS street, 
                m.{kor} AS kor, 
                m.{dom} AS dom, 
                m.{tel} AS tel
            FROM main m
            LEFT JOIN fam f ON m.{fam} = f.fid
            LEFT JOIN ns n ON m.{name} = n.nid
            LEFT JOIN otcs o ON m.{otc} = o.oid
            LEFT JOIN streets s ON m.{street} = s.sid
        """).format(
            name=name_col, fam=fam_col, otc=otc_col, street=street_col,
            kor=kor_col, dom=dom_col, tel=tel_col
        )

        conditions = []
        params = []

        # Динамически добавляем условия WHERE
        if filters.get("fam_id"):
            conditions.append(sql.SQL("m.{fam} = %s").format(fam=fam_col))
            params.append(filters["fam_id"])

        if filters.get("name_id"):
            conditions.append(sql.SQL("m.{name} = %s").format(name=name_col))
            params.append(filters["name_id"])

        if filters.get("otc_id"):
            conditions.append(sql.SQL("m.{otc} = %s").format(otc=otc_col))
            params.append(filters["otc_id"])

        if filters.get("street_id"):
            conditions.append(sql.SQL("m.{street} = %s").format(street=street_col))
            params.append(filters["street_id"])

        if filters.get("tel"):
            conditions.append(sql.SQL("m.{tel} LIKE %s").format(tel=tel_col))
            params.append(f"%{filters['tel']}%")

        if filters.get("dom"):
            conditions.append(sql.SQL("m.{dom} = %s").format(dom=dom_col))
            params.append(filters["dom"])

        if conditions:
            query += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(conditions)

        query += sql.SQL(" ORDER BY f.f_value, n.name_value LIMIT %s")
        params.append(limit)

        with conn.cursor() as cur:
            cur.execute(query, params)
            headers = [d.name for d in cur.description] if cur.description else []
            rows = cur.fetchall() if cur.description else []
        return headers, rows

    def add_record(self, name_id: int, fam_id: int, kor: int, dom: int, otc_id: int, street_id: int, tel: str) -> None:
        conn = self._require_conn()
        # Используем sql.Identifier, чтобы подставить точные имена колонок
        query = sql.SQL("""
            INSERT INTO main ({name}, {fam}, {kor}, {dom}, {otc}, {street}, {tel}) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """).format(
            name=sql.Identifier(self._main_cols['name']),
            fam=sql.Identifier(self._main_cols['fam']),
            kor=sql.Identifier(self._main_cols['kor']),
            dom=sql.Identifier(self._main_cols['dom']),
            otc=sql.Identifier(self._main_cols['otc']),
            street=sql.Identifier(self._main_cols['street']),
            tel=sql.Identifier(self._main_cols['tel'])
        )
        with conn.cursor() as cur:
            cur.execute(query, (name_id, fam_id, kor, dom, otc_id, street_id, tel))

    def update_record(self, uid: int, name_id: int, fam_id: int, kor: int, dom: int, otc_id: int, street_id: int,
                      tel: str) -> None:
        conn = self._require_conn()
        query = sql.SQL("""
            UPDATE main 
            SET {name}=%s, {fam}=%s, {kor}=%s, {dom}=%s, {otc}=%s, {street}=%s, {tel}=%s 
            WHERE uid=%s
        """).format(
            name=sql.Identifier(self._main_cols['name']),
            fam=sql.Identifier(self._main_cols['fam']),
            kor=sql.Identifier(self._main_cols['kor']),
            dom=sql.Identifier(self._main_cols['dom']),
            otc=sql.Identifier(self._main_cols['otc']),
            street=sql.Identifier(self._main_cols['street']),
            tel=sql.Identifier(self._main_cols['tel'])
        )
        with conn.cursor() as cur:
            cur.execute(query, (name_id, fam_id, kor, dom, otc_id, street_id, tel, uid))

    def delete_record(self, uid: int) -> None:
        conn = self._require_conn()
        query = "DELETE FROM main WHERE uid = %s"
        with conn.cursor() as cur:
            cur.execute(query, (uid,))