from dbsql.llm.chains.dbsql_answer import DBSQLAnswer

def test_dbsql():
    # 初始化数据库连接
    db_handler = DBSQLAnswer(
        model="local",
        db_type="MySQL",
        db_host="localhost",
        db_port=3306,  # 注意确认实际端口
        db_user="root",
        db_password="jhl12735800",
        db_name="NLP_DB_BY_TYPE",
    )

    # 测试用例
    test_cases = [
        "请问虚假信息类中涉及的最大金额是多少？"
    ]

    for question in test_cases:
        print(f"\n{' 测试问题 ':=^40}")
        print(f"输入：{question}")
        
        try:
            process, response = db_handler.step_run(question)
            
            print(f"\n{' 处理过程 ':-^40}")
            print(process)
            
            print(f"\n{' 最终回答 ':-^40}")
            print(response)
            
        except Exception as e:
            print(f"\n[错误] {str(e)}")

if __name__ == "__main__":
    test_dbsql()