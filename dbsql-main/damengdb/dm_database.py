from __future__ import annotations

from typing import Optional, Iterable, List, Union, Literal, Dict, Any, Sequence

import dmPython


class DMDatabase:
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

        self._tables = self._get_tables()
        self._history = list()

    @classmethod
    def from_uri(
            cls,
            database_uri: str,
    ) -> DMDatabase:
        """create an instance of the database connector from url.

        Args:
            database_uri: an url contain information to connect to
                          dameng database

        Examples:
            >>> dmdb = DMDatabase.from_uri("dm://username:password@host:port/database_name")
        """
        db_type, info = database_uri.split("://")
        assert db_type == 'dm', f'Invalid database {db_type}'
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
        """get the dialect type of the database

        Returns:
            the dialect type of the database

        Examples:
            >>> dmdb = DMDatabase(database='DMHR')
            >>> print(dmdb.dialect)
            dameng
        """
        return "dameng"

    @property
    def table_info(self) -> str:
        return self.get_table_info()

    def get_usable_table_names(self) -> Iterable[str]:
        """get the names of the tables in the database

        Returns:
            the names of the tables in the database

        Examples:
            >>> dmdb = DMDatabase()
            >>> print(dmdb.get_usable_table_names())
            ['REGION', 'CITY', 'LOCATION', 'DEPARTMENT', 'JOB', 'EMPLOYEE', 'JOB_HISTORY']
        """
        return self._tables

    def get_table_names(self) -> Iterable[str]:
        """get the names of the tables in the database

        Returns:
            the names of the tables in the database

        Examples:
            >>> dmdb = DMDatabase()
            >>> print(dmdb.get_usable_table_names())
            ['REGION', 'CITY', 'LOCATION', 'DEPARTMENT', 'JOB', 'EMPLOYEE', 'JOB_HISTORY']
        """
        return self.get_usable_table_names()

    def _get_tables(self):
        """get the names of the tables in the database

        Returns:
            the names of the tables in the database

        Examples:
            >>> dmdb = DMDatabase()
            >>> print(dmdb.get_usable_table_names())
            ['REGION', 'CITY', 'LOCATION', 'DEPARTMENT', 'JOB', 'EMPLOYEE', 'JOB_HISTORY']
        """
        tables = self._execute(
            command=f"SELECT TABLE_NAME FROM dba_tables WHERE OWNER='{self.database}';",
            fetch="all"
        )
        return [table[0] for table in tables]

    def get_table_info(self, table_names: Optional[List[str]] = None) -> str:
        """get the table information from the database, including table structure
        and several lines of data of table.

        Args:
            table_names: a list of table names which you want to query the
                         detailed information.

        Returns:
            the table information.

        Examples:
            >>> dmdb = DMDatabase(database='DMHR')
            >>> dmdb.get_table_info(['CITY'])

            CREATE TABLE "DMHR"."CITY"
            (
            "CITY_ID" CHAR(3) NOT NULL,
            "CITY_NAME" VARCHAR(40),
            "REGION_ID" INT,
            CONSTRAINT "CITY_C_ID_PK" NOT CLUSTER PRIMARY KEY("CITY_ID"),
            CONSTRAINT "CITY_REG_FK" FOREIGN KEY("REGION_ID") REFERENCES "DMHR"."REGION"("REGION_ID")) STORAGE(ON "MAIN", CLUSTERBTR) ;

            /*
            3 rows from CITY table:
            CITY_ID	CITY_NAME	REGION_ID
            BJ 	北京	1
            SJZ	石家庄	1
            SH 	上海	2
            */
        """
        all_table_names = self._tables
        if table_names is not None:
            missing_tables = set(table_names).difference(all_table_names)
            if missing_tables:
                raise ValueError(f"table_names {missing_tables} not found in database")
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
        """ get the table structure based on SQL.

        Args:
             table_name: the name of the table

        Returns:
            the table structure in SQL format.

        Examples:
            >>> self._get_table_structure("CITY")
            CREATE TABLE "DMHR"."CITY"
            (
            "CITY_ID" CHAR(3) NOT NULL,
            "CITY_NAME" VARCHAR(40),
            "REGION_ID" INT,
            CONSTRAINT "CITY_C_ID_PK" NOT CLUSTER PRIMARY KEY("CITY_ID"),
            CONSTRAINT "CITY_REG_FK" FOREIGN KEY("REGION_ID") REFERENCES "DMHR"."REGION"("REGION_ID")) STORAGE(ON "MAIN", CLUSTERBTR) ;
        """
        return self._execute(
            command=f"SELECT DBMS_METADATA.GET_DDL('TABLE','{table_name}','{self.database}') FROM dual;",
            fetch="all"
        )[0][0]

    def _get_table_indexes(self, table: str) -> str:
        raise NotImplementedError

    def _get_table_columns(self, table: str) -> List[str]:
        """ get column names of table

        Args:
            table (str): table name

        Returns:
            List[str]: column names

        Examples:
            >>> self._get_table_columns('CITY')
            ['CITY_ID', 'CITY_NAME', 'REGION_ID']
        """
        columns = self._execute(
            f"select COLUMN_NAME from all_tab_columns where owner='{self.database}' and Table_Name='{table}'"
        )
        column_names = [column[0] for column in columns]
        return column_names

    def _get_sample_rows(self, table: str, num_rows: int = None) -> str:
        """ get several lines of data from specified table.

        Args:
            table (str): name of table to get data.
            num_rows (int): number of rows of data. Defaults to None.
                            If not specified will use self._sample_rows_in_table_info.

        Returns:
            str: lines of data from specified table.

        Examples:
            >>> self._get_sample_rows("CITY")
            3 rows from CITY table:
            CITY_ID	CITY_NAME	REGION_ID
            BJ 	北京	1
            SJZ	石家庄	1
            SH 	上海	2
        """
        columns_name = self._get_table_columns(table)
        columns_str = '\t'.join(columns_name)

        num_rows = self._sample_rows_in_table_info if num_rows is None else num_rows
        sample_rows_result = self._execute(
            command=f'SELECT * FROM {self.database}."{table}" LIMIT {num_rows};'
        )
        sample_rows_str = "\n".join(["\t".join([str(item) for item in row]) for row in sample_rows_result])

        return (
            f"{num_rows} rows from {table} table:\n"
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
        try:
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

        except dmPython.Error as error:
            raise ValueError("==" * 20 + "\n{}\nwhile executing query:\n```sql\n{}\n````\n".format(str(error), command) + "==" * 26)

    def run(
            self,
            command: str,
            fetch: Literal["all", "one", "cursor"] = "all",
            include_columns: bool = False,
            *,
            parameters: Optional[Dict[str, Any]] = None,
            execution_options: Optional[Dict[str, Any]] = None,
    ):
        """ run sql query and return result

        Args:
            command (str): sql command
            fetch (str, optional): 'all' for all results of sql query;
                                   'one' for one result of sql query;
                                   'cursor' for the cursor used to execute the sql query.

        Examples:
            >>> dmdb = DMDatabase(database='DMHR')
            >>> dmdb.run("SELECT CITY_NAME FROM DMHR.CITY")
            [('北京',), ('石家庄',), ('上海',), ('南京',), ('广州',), ('海口',), ('武汉',), ('长沙',), ('沈阳',), ('西安',), ('成都',)]

        """
        result = self._execute(
            command.strip("\n"), fetch, parameters=parameters, execution_options=execution_options
        )

        if fetch == 'cursor':
            return result

        return str(result)

    def get_table_info_no_throw(self, table_names: Optional[List[str]] = None) -> str:
        """get the table information from the database, including table structure
        and several lines of data of table.

        Args:
            table_names: a list of table names which you want to query the
                         detailed information.

        Returns:
            the table information.

        Examples:
            >>> dmdb = DMDatabase(database='DMHR')
            >>> dmdb.get_table_info(['CITY'])

            CREATE TABLE "DMHR"."CITY"
            (
            "CITY_ID" CHAR(3) NOT NULL,
            "CITY_NAME" VARCHAR(40),
            "REGION_ID" INT,
            CONSTRAINT "CITY_C_ID_PK" NOT CLUSTER PRIMARY KEY("CITY_ID"),
            CONSTRAINT "CITY_REG_FK" FOREIGN KEY("REGION_ID") REFERENCES "DMHR"."REGION"("REGION_ID")) STORAGE(ON "MAIN", CLUSTERBTR) ;

            /*
            3 rows from CITY table:
            CITY_ID	CITY_NAME	REGION_ID
            BJ 	北京	1
            SJZ	石家庄	1
            SH 	上海	2
            */
        """
        try:
            return self.get_table_info(table_names)
        except dmPython.DatabaseError as error:
            return str(error)

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
            result = self._execute(
                command.strip("\n"), fetch, parameters=parameters, execution_options=execution_options
            )

            if fetch == 'cursor':
                return dict(state=1, message=result)

            return dict(state=0, message=str(result))
        except dmPython.Error as error:
            return dict(state=2, message=str(error))

    def get_context(self) -> Dict[str, Any]:
        """returns db context that you may want in agent prompt.

        Returns:
            Dict[str, str]: db context that you may want in agent prompt.

        Examples:
            >>> dmdb = DMDatabase()
            >>> print(dmdb.get_context())
            {'table_info': str, 'table_names': str}
        """
        table_names = list(self.get_usable_table_names())
        table_info = self.get_table_info_no_throw()
        return {"table_info": table_info, "table_names": ", ".join(table_names)}


if __name__ == '__main__':
    db = DMDatabase(user='XYCS', password='123456789', port=5236, database='XYCS')
    print(db.get_table_info())