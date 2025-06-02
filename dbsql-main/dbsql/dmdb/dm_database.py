from __future__ import annotations

import re
from copy import copy
from typing import Optional, Iterable, List, Union, Literal, Dict, Any, Sequence

import dmPython
from langchain_community.utilities import SQLDatabase
from langchain_core._api import deprecated


class DMDatabase(SQLDatabase):
    def __init__(
            self,
            user: str = 'SYSDBA',
            password: str = 'qwertyuio',
            host: str = '127.0.0.1',
            port: int = 5236,
            database: str = 'DMHR',
            sample_rows_in_table_info: int = 3,
            indexes_in_table_info: bool = False,
    ):
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.database = database

        if not isinstance(sample_rows_in_table_info, int):
            raise TypeError("sample_rows_in_table_info must be an integer")

        self._sample_rows_in_table_info = sample_rows_in_table_info
        self._indexes_in_table_info = indexes_in_table_info

        # self._tables = self._get_tables()
        self._tables = ['EGOV_DISPATCH', 'EGOV_COMMON_OPINION', 'RMS_UPDATE_DETAIL_LOG']

    def _get_tables(self):
        tables = self._execute(
            command=f"SELECT TABLE_NAME FROM dba_tables WHERE OWNER='{self.database}';",
            fetch="all"
        )
        return [table[0] for table in tables]

    @classmethod
    def from_uri(
            cls,
            database_uri: str,
    ) -> DMDatabase:
        info = database_uri.split("://")[1]
        user, passwd_host, port_dbname = info.split(":")
        password, host = passwd_host.split('@')
        port, dbname = port_dbname.split('/')
        return cls(
            user=user,
            password=password,
            host=host,
            port=port,
            database=dbname
        )

    @property
    def dialect(self) -> str:
        return "dameng"

    def get_usable_table_names(self) -> Iterable[str]:
        return self._tables

    @deprecated("0.0.1", alternative="get_usable_table_names", removal="1.0")
    def get_table_names(self) -> Iterable[str]:
        return self.get_usable_table_names()

    @property
    def table_info(self) -> str:
        return self.get_table_info()

    def get_table_info(self, table_names: Optional[List[str]] = None) -> str:
        all_table_names = self._tables
        if table_names is not None:
            missing_tables = set(table_names).difference(all_table_names)
            if missing_tables:
                save_tables = copy(missing_tables)
                for table in save_tables:
                    for r_table in all_table_names:
                        if table in r_table:
                            missing_tables.remove(table)
                            table_names.remove(table)

                            table_names.append(table)
                            break
                if missing_tables:
                    table_names = [table for table in table_names if table not in missing_tables]
                # raise ValueError(f"table_names {missing_tables} not found in database")
            if len(table_names) > 0:
                all_table_names = table_names

        metadata_table_names = self._tables
        to_reflect = set(all_table_names) - set(metadata_table_names)
        if to_reflect:
            raise NotImplementedError(f"table names {to_reflect} not found in database")

        meta_tables = [
            table
            for table in self._tables
            if table in set(all_table_names)
        ]

        tables = []
        for table in meta_tables:
            # if table == "WORKFLOWS":
            #     table = "WORKFLOWS"
            table_info = f"\n{self._get_table_structure(table).rstrip()}"
            has_extra_info = (
                    self._indexes_in_table_info or self._sample_rows_in_table_info
            )
            if has_extra_info:
                table_info += "\n\n/*"
            if self._indexes_in_table_info:
                table_info += f"\n{self._get_table_indexes(table)}\n"
            if self._sample_rows_in_table_info:
                table_info += f"\n{self._get_sample_rows(table)}\n"
            if has_extra_info:
                table_info += "*/"
            tables.append(table_info)
        tables.sort()
        final_str = "\n\n".join(tables)
        return final_str

    def _get_table_structure(self, table_name: str) -> str:
        return self._execute(
            command=f"SELECT DBMS_METADATA.GET_DDL('TABLE','{table_name}','{self.database}') FROM dual;",
            fetch="all"
        )[0][0]

    def _get_table_indexes(self, table: str) -> str:
        raise NotImplementedError

    def _get_sample_rows(self, table: str) -> str:
        columns_name = self._execute(
            f"select COLUMN_NAME from all_tab_columns where owner='{self.database}' and Table_Name='{table}'")
        columns_str = "\t".join([column_name[0] for column_name in columns_name])

        sample_rows_result = self._execute(
            command=f'SELECT * FROM {self.database}."{table}" LIMIT {self._sample_rows_in_table_info};'
        )
        sample_rows_str = "\n".join(["\t".join([str(item) for item in row]) for row in sample_rows_result])

        return (
            f"{self._sample_rows_in_table_info} rows from {table} table:\n"
            f"{columns_str}\n"
            f"{sample_rows_str}"
        )

    def _execute(
            self,
            command: str,
            fetch: Literal["all", "one", "cursor"] = "all",
            *,
            parameters: Optional[Dict[str, Any]] = None,
            execution_options: Optional[Dict[str, Any]] = None,
    ):
        # try:
        connection = dmPython.connect(
            user=self.user,
            password=self.password,
            server=self.host,
            port=self.port
        )
        cursor = connection.cursor()

        cursor.execute(command)

        if fetch == "all":
            result = cursor.fetchall()
        elif fetch == "one":
            result = cursor.fetchone()
        elif fetch == "cursor":
            result = cursor
        else:
            raise ValueError(
                "Fetch parameter must be either 'one', 'all', or 'cursor'"
            )

        cursor.close()
        connection.close()

        return result

        # except dmPython.Error as error:
        #     return str(error)

    def run(
            self,
            command: str,
            fetch: Literal["all", "one", "cursor"] = "all",
            include_columns: bool = False,
            *,
            parameters: Optional[Dict[str, Any]] = None,
            execution_options: Optional[Dict[str, Any]] = None,
    ):
        result = self._execute(
            command.strip("\n"), fetch, parameters=parameters, execution_options=execution_options
        )

        if fetch == 'cursor':
            return result

        return str(result)

    def get_table_info_no_throw(self, table_names: Optional[List[str]] = None) -> str:
        try:
            return self.get_table_info(table_names)
        except ValueError as e:
            """Format the error message"""
            return f"Error: {e}"

    def run_no_throw(
            self,
            command: str,
            fetch: Literal["all", "one"] = "all",
            include_columns: bool = False,
            *,
            parameters: Optional[Dict[str, Any]] = None,
            execution_options: Optional[Dict[str, Any]] = None,
    ) -> Union[str, Sequence[Dict[str, Any]]]:
        try:
            return self.run(
                command,
                fetch,
                parameters=parameters,
                execution_options=execution_options,
                include_columns=include_columns,
            )
        except Exception as e:
            return f"Error: {e}"

    def get_context(self) -> Dict[str, Any]:
        """Return db context that you may want in agent prompt."""
        table_names = list(self.get_usable_table_names())
        table_info = self.get_table_info_no_throw()
        return {"table_info": table_info, "table_names": ", ".join(table_names)}


if __name__ == '__main__':
    db = DMDatabase(user='XYCS', password='123456789', port=5236, database='XYCS', sample_rows_in_table_info=5)
    print(db.get_table_names())
    print(db.get_table_info(["EGOV_DISPATCH"]))
