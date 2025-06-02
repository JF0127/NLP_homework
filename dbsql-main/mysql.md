# mysql

| user | password | port | database |
|:----:|:----:|:----:|:----:|
| `root` | `password` | `3006` | - |
| `DBSQL` | `12345678` | `3006` | `DB_TEST` |

## start

```bash
cd ~/mysql
bin/mysqld_safe --defaults-file=etc/my.cnf --user=tmp_user &
```

## stop

```bash
cd ~/mysql
bin/mysqladmin -u root -p shutdown -S tmp/mysql.sock
```


