from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional, Union

from langchain.chains.sql_database.query import create_sql_query_chain, SQLInput, SQLInputWithTables
from langchain_core.language_models import BaseLanguageModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import BasePromptTemplate
from langchain_core.runnables import Runnable, RunnablePassthrough

if TYPE_CHECKING:
    from langchain_community.utilities.sql_database import SQLDatabase

from dbsql.utils import table_extract
from dbsql.utils import table_info_generate


def _strip(text: str) -> str:
    return text.strip()


def create_sql_query_chain_with_limit(
        llm: BaseLanguageModel,
        db: SQLDatabase,
        table_prompt: Optional[BasePromptTemplate] = None,
        query_prompt: Optional[BasePromptTemplate] = None,
        extra_data: Dict = None,
        k: int = 5,
) -> Runnable[Union[SQLInput, SQLInputWithTables, Dict[str, Any]], str]:
    if table_prompt is None:
        return create_sql_query_chain(llm, db, query_prompt, k)

    # TODO: replace get_table_info with get_table_description
    inputs = {
        "input": lambda x: x["question"] + "\nSQLQuery: ",
        "table_info": lambda x: table_info_generate(
            db=db,
            table_names=x.get("table_names_to_use", ""),
            extra_data=extra_data,
        ),
    }

    return (
            RunnablePassthrough.assign(**inputs)  # type: ignore
            | (
                lambda x: {
                    **x,
                    "relevant_table_names": table_extract(
                        llm.invoke(
                            table_prompt.invoke({
                                "question": x["input"].replace("\nSQLQuery: ", ""),
                                "table_info": x["table_info"],
                            })
                        )
                    )
                }
            )
            | (
                lambda x: {
                    **x,
                    "table_info": table_info_generate(
                        db=db,
                        table_names=x["relevant_table_names"],
                        extra_data=extra_data,
                    ),
                }
            )
            | (
                lambda x: {
                    k: v
                    for k, v in x.items()
                    if k not in ("question", "table_names_to_use", "relevant_table_names")
                }
            )
            | query_prompt.partial(top_k=str(k))
            | llm.bind(stop=["\nSQLResult:"])
            | StrOutputParser()
            | _strip
    )
