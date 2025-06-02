"""SQL 相关 Prompt 汇集"""

TABLE_QUERY = """ 请根据以下内容为表 {table_name} 生成辅助信息。请严格按照示例结构进行回复。不要额外生成任何其他内容。
#### 信息 ####
{table_info}

#### 示例结构 ####
## 表用途
EGOV_DISPATCH 表用于保存系统发文信息，记录了发文的详细信息，包括发文标题、拟稿人、签发人、文件密级、文号、分发单位、归档状态等。",
## 表结构
- ID: 发文的唯一标识，主键，不可为空。
- TIME: 投诉涉及的日期。
- SUBJECT: 投诉方。
- OBJECT: 被投诉方。
- DESCRIPTION: 投诉的具体内容描述。
- PLATFORM: 投诉发生的平台。
- COMPLAINT_TYPE: 投诉的实际分类值。


请严格按照示例结构回答问题！！
"""

TABLE_PROMPT = """You are a database expert assisting in mapping user questions to database tables. 

Given the following:
1. **User Question**: "{question}"
2. **Table Descriptions**: 
{table_info}

你需要根据所有的表结构以及表示例数据找出与问题相关联的表名。如果有多个表与问题相关联，则需要将这些表都列出来，表之间用“,”进行分隔。
注意: 你需要着重关注表结构中列名与问题的关系并以此确定最相关的表。请严格按照示例回答格式，不要额外回答其他任何内容。
你的回答格式如下：
Answer:table_name
请不要加任何其它内容，如果是多表:
Answer:table_one,table_two
严格按照回答格式回答问题
"""

QUESTION_PROMPT = """### Task
Given an input question, first create a syntactically correct MySQL query to run, then look at the results of the query and return the answer to the input question.

### Instructions
- If you cannot answer the question with the available database schema, return 'I do not know'
- Unless the user specifies in the question a specific number of examples to obtain, query for at most {top_k} results using the LIMIT clause as per MySQL. You can order the results to return the most informative data in the database.
- Pay attention to use only the column names you can see in the tables below. Be careful to not query for columns that do not exist. Also, pay attention to which column is in which table.
- Pay attention to use CURDATE() function to get the current date, if the question involves "today".
- Generate at least one SQL query.
- An example of your reply: 
  - ```sql\nSELECT * FROM DB_TEST.FLOW_WORK_ATDO WHERE BUSINESS_CATE = '中央' LIMIT 5;\n```

### User Question
The query will be generated based on the following question:
{input}

### Database Schema
The query will run on a database with the following schema:
{table_info}

### Answer
Given the database schema, here is the MySQL query that answers [QUESTION]{input}[/QUESTION]
[SQL]
"""

ANSWER_PROMPT = """Given the following user question, corresponding SQL query, 
and SQL result, answer the user question. 

Use the following format:
`Answer`: If the `SQL Result` has more than one tuple and can transform to table, must use markdown table format. If the `SQL Result` has one tuple, must use Chinese to answer the `Question`.

Question: {user_question}
SQL Query: {sql_query}
SQL Result: {sql_result}
Answer: """
