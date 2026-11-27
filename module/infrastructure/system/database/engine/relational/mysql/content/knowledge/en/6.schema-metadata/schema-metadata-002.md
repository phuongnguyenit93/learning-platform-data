# CREATE DATABASE, USE, and Default Database Scope

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, privilege management, backups, and operations. Before creating tables and manipulating data, you need to know how to organize databases, set default character sets, and select a database as the context for SQL statements.

In MySQL, the terms **database** and **schema** are used interchangeably. A database is a namespace containing objects such as tables, views, triggers, procedures, and events. `CREATE DATABASE` creates this namespace; `USE` sets the default database for the current session so that unqualified table names are resolved in the right scope.

## 1. Database and Schema in MySQL

A MySQL instance can manage multiple databases. Each database contains objects with their own names within its scope. For example, two databases `sales` and `support` can both contain a table named `customers`:

~~~text
MySQL Server
├── sales
│   ├── customers
│   ├── orders
│   └── order_items
└── support
    ├── customers
    └── tickets
~~~

When querying, you can specify the database explicitly to avoid confusion:

~~~sql
SELECT * FROM sales.customers;
SELECT * FROM support.customers;
~~~

In MySQL, the `CREATE SCHEMA` syntax is a synonym for `CREATE DATABASE`; both create a database. This differs from some other DBMSs, where a schema can be a namespace inside a database.

A database is not synonymous with a single file. InnoDB manages tables and metadata through tablespaces, the data dictionary, and its own storage structures. Do not directly manipulate directories or files on disk to modify a database; use SQL and MySQL administrative tools.

## 2. Database Naming Rules

A database name is an identifier, not a character string used as a value. A few helpful guidelines:

- Use lowercase letters, digits, and underscores so names stay readable and consistent across operating systems.
- Choose short names that clearly express the business scope, such as `sales`, `inventory`, or `customer_portal`.
- Avoid names that collide with SQL keywords or could be confused with system databases like `mysql`, `sys`, `performance_schema`, and `information_schema`.
- MySQL limits database name length to 64 characters.
- Do not rely on uppercase/lowercase differences to distinguish databases. Name sensitivity can depend on the operating system and the `lower_case_table_names` configuration.

If an identifier contains special characters or collides with a keyword, it can be enclosed in backticks. Backticks are used to quote identifiers. Single quotes are used for string literals, for example `'PAID'`; do not write `CREATE DATABASE 'sales'` because a database name is not a string literal.

For applications to run consistently across Windows, Linux, and macOS, standardize database names using lowercase letters and underscores, and do not depend on how the filesystem handles letter case.

## 3. Creating a Database with CREATE DATABASE

### 3.1. Basic syntax

~~~sql
CREATE DATABASE database_name;
~~~

Example:

~~~sql
CREATE DATABASE sales;
CREATE SCHEMA support;
~~~

The two statements above create the `sales` and `support` databases respectively. If the name already exists, MySQL returns an error unless `IF NOT EXISTS` is used.

`CREATE DATABASE` is a DDL statement and causes an implicit commit according to MySQL rules. You cannot place database creation inside a business transaction and expect `ROLLBACK` to remove the newly created database.

The executor needs the appropriate `CREATE` privilege at the server level. In organizational environments, usually only a DBA or a schema deployment account is granted privileges to create databases. Do not grant broad administrative privileges to an application account just so the application can auto-create databases at startup.

### 3.2. Avoiding errors when the database already exists

You can use `IF NOT EXISTS` to avoid an error when the database has already been created:

~~~sql
CREATE DATABASE IF NOT EXISTS sales;
~~~

If `sales` does not exist yet, MySQL creates the database. If it already exists, the statement does not create another database and typically returns a warning/note.

**Key point:** `IF NOT EXISTS` does not synchronize the configuration of an existing database. If the existing database uses a different charset or collation, the statement above does not automatically change them. After using `IF NOT EXISTS`, check metadata if you need to guarantee configuration.

### 3.3. Choosing character set and collation at creation time

A database has default character set and collation values. These values are used as defaults when creating tables or columns without specifying them explicitly.

Example for MySQL 8.0:

~~~sql
CREATE DATABASE customer_portal
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

- `CHARACTER SET utf8mb4` allows storing full Unicode, including Vietnamese and emoji.
- `COLLATE utf8mb4_0900_ai_ci` specifies the string comparison and sorting rules under the `utf8mb4` character set.
- The `_ai_ci` suffix indicates accent-insensitive and case-insensitive rules in this collation.

`utf8mb4_0900_ai_ci` belongs to MySQL 8.0. For MySQL 5.7 or environments requiring compatibility with older versions, choose a collation available on that version, such as `utf8mb4_unicode_ci`. Do not copy a collation from another machine without checking whether the target machine supports it.

If you omit `CHARACTER SET` and `COLLATE`, MySQL uses the server's default values. Therefore, two environments with different server configurations can create databases with different defaults even when running the exact same `CREATE DATABASE` statement without explicit charset/collation.

### 3.4. Choosing charset and collation based on requirements

A character set determines which characters can be represented; a collation determines how strings are compared, sorted, and evaluated for equivalence. Two databases with the same charset can still use different collations.

| Component | Question to answer | Example |
|---|---|---|
| Character set | Which characters can be stored? | utf8mb4 |
| Collation | By what rules are strings compared and sorted? | utf8mb4_0900_ai_ci |

For Vietnamese applications and multilingual data, `utf8mb4` is usually the right choice. Collation should be chosen based on search and comparison requirements. An accent-insensitive collation may treat certain accented and unaccented strings as equivalent during comparison; this helps some searches but may be unsuitable for identifiers or business logic requiring accent sensitivity.

You can inspect available charsets and collations:

~~~sql
SHOW CHARACTER SET LIKE 'utf8mb4';
SHOW COLLATION LIKE 'utf8mb4%';
~~~

A collation must belong to the corresponding character set. Do not choose a `latin1` collation for a database using `utf8mb4`.

## 4. Inspecting the Newly Created Database

### 4.1. Listing databases

~~~sql
SHOW DATABASES;
SHOW DATABASES LIKE 'sales';
~~~

The list of databases an account sees may be restricted by the account's privileges. If a database does not appear, check the current account and privileges before concluding the database does not exist.

### 4.2. Viewing database configuration

~~~sql
SHOW CREATE DATABASE sales;
~~~

This command returns the database creation statement along with attributes such as default character set and collation. This is a quick way to check the configuration MySQL has stored.

You can also query `information_schema.SCHEMATA`:

~~~sql
SELECT SCHEMA_NAME,
       DEFAULT_CHARACTER_SET_NAME,
       DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = 'sales';
~~~

`information_schema` is the metadata interface for inspecting database and object information. Results only reflect metadata that the current account is permitted to view.

### 4.3. Distinguishing server defaults from database defaults

Check defaults at the server level:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'character_set_server';
SHOW GLOBAL VARIABLES LIKE 'collation_server';
~~~

Check defaults on the database:

~~~sql
SELECT SCHEMA_NAME,
       DEFAULT_CHARACTER_SET_NAME,
       DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = DATABASE();
~~~

These two levels can differ. A database created with `CHARACTER SET utf8mb4` keeps its own database default even if the server default changes afterward.

## 5. Changing Defaults with ALTER DATABASE

When you need to change the defaults for newly created objects, you can use:

~~~sql
ALTER DATABASE sales
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

This statement changes the database's default character set and collation. It **does not automatically convert** the character set or collation of existing tables and columns. Existing tables continue to keep their own attributes.

If existing data needs to be converted, plan separately for each table/column, checking data lengths, indexes, unique constraints, and application impact. `ALTER TABLE ... CONVERT TO CHARACTER SET ...` can convert data and may require rebuilding the table; do not run it in bulk on production without evaluating duration, disk space, locks, and backups.

Verify again after making the change:

~~~sql
SHOW CREATE DATABASE sales;
SELECT DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = 'sales';
~~~

## 6. Selecting the Default Database with USE

### 6.1. Syntax and scope

~~~sql
USE sales;
SELECT DATABASE();
~~~

`USE sales` sets `sales` as the default database for the **current connection/session**. From then on, statements using table names without a database prefix will look for tables in `sales`:

~~~sql
SELECT * FROM customers;
SELECT * FROM orders;
~~~

You can change the default database within the same session:

~~~sql
USE support;
SELECT DATABASE();
SELECT * FROM tickets;
~~~

The default database remains in effect until the session ends or another `USE` statement is executed on that same session. It is not a server-wide setting and does not automatically apply to other connections.

### 6.2. Checking the current database

The `DATABASE()` function returns the name of the session's default database; if no default database has been selected, it returns `NULL`.

~~~sql
SELECT DATABASE() AS current_database;
SELECT SCHEMA() AS current_schema;
~~~

In MySQL, `SCHEMA()` is a synonym for `DATABASE()`. Both functions help verify context before running a multi-statement script.

### 6.3. USE does not grant privileges

`USE` only changes the object-naming context for the session. It does not grant privileges to read, write, create, or drop objects. When executing a statement on a table, MySQL still checks the account's privileges for the corresponding database and object.

For example, selecting `sales` as the default database does not mean the account automatically has `SELECT` privilege on `sales.orders`. Check privileges:

~~~sql
SHOW GRANTS FOR CURRENT_USER();
~~~

When encountering an Access denied error, identify the account in use, the host match, and the required privileges. Do not confuse selecting a database with being granted privileges on that database.

## 7. Unqualified Table Names and Fully Qualified Names

Once a default database is selected, you can reference a table by its short name:

~~~sql
USE sales;
SELECT order_id, total_amount
FROM orders;
~~~

If no database has been selected or you want to specify the data source explicitly, use the fully qualified name:

~~~sql
SELECT order_id, total_amount
FROM sales.orders;
~~~

In MySQL, object names can be qualified in the forms:

~~~text
database_name.table_name
database_name.table_name.column_name
~~~

Fully qualified names are especially useful when:

- A query joins tables across multiple databases.
- A deployment script must run unambiguously even if the client has not selected a default database.
- An application uses multiple schemas and wants to avoid depending on session state.
- A DBA inspects objects with the same name across different databases at the same time.

Example joining two databases:

~~~sql
SELECT c.customer_id, c.full_name, t.ticket_id
FROM sales.customers AS c
JOIN support.tickets AS t
  ON t.customer_id = c.customer_id;
~~~

If an identifier needs quoting, quote each component with backticks. Do not quote the entire `sales.orders` string as a single identifier; the dot is the separator between database and table.

## 8. Default Database in MySQL CLI and Applications

### 8.1. MySQL CLI

You can select a database right when opening a connection:

~~~bash
mysql --host=127.0.0.1 --port=3306 --user=app_user --password sales
~~~

Here `sales` is the default database selected when the client logs in. Once inside the CLI, you can check:

~~~sql
SELECT DATABASE();
STATUS;
~~~

Or select a database after connecting with `USE sales`.

### 8.2. JDBC and MySQL Connector/J

Java applications typically specify the default database in the JDBC URL:

~~~java
String url = "jdbc:mysql://db.example.internal:3306/sales";
Connection connection = DriverManager.getConnection(url, user, password);
~~~

The `/sales` portion of the URL specifies the default database for the connection. The application can still reference other databases using fully qualified names if the account has the appropriate privileges.

When using a connection pool, each physical connection has its own session state. If one thread calls `USE support` and returns the connection to the pool, the next thread borrowing that same connection may receive a modified default database state if the pool or application does not reset the state. Therefore:

- Keep a consistent default database per pool whenever possible.
- If the application switches databases per request, explicitly reset the catalog/schema when borrowing a connection and understand how the driver/pool manages state.
- Use fully qualified table names when SQL statements need to access multiple databases or must be independent of the default database.
- Do not assume connections in the same pool share a common `USE`; each session has its own state.

Never concatenate user-supplied database names directly into SQL. Identifiers cannot be passed as regular bind parameters; if you must select a database dynamically, validate the name against an allowlist and quote the identifier properly.

## 9. How Are Charset and Collation Inherited?

When creating objects without specifying a dedicated charset/collation, MySQL uses a hierarchical default inheritance mechanism:

~~~text
Server defaults
    ↓
Database defaults
    ↓
Table defaults
    ↓
Column defaults (if overridden)
~~~

For example, the `sales` database is created with `utf8mb4` and `utf8mb4_0900_ai_ci`; when creating a table without specifying charset/collation, the table typically inherits the database defaults. Character columns without explicit settings can inherit from the table.

~~~sql
CREATE DATABASE sales
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE sales;

CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
);
~~~

Check the charset/collation of the table and columns:

~~~sql
SHOW TABLE STATUS LIKE 'customers';

SELECT TABLE_NAME, COLUMN_NAME, CHARACTER_SET_NAME, COLLATION_NAME
FROM information_schema.columns
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'customers';
~~~

Not every column has a character set. Numeric, date/time, or binary columns do not use collations in the way string columns do.

## 10. Database-Related Metadata

MySQL provides multiple ways to inspect databases and objects:

| Command or view | Information |
|---|---|
| `SHOW DATABASES` | List of databases the current account is permitted to see |
| `SHOW CREATE DATABASE db_name` | Statement and attributes used to create the database |
| `SELECT DATABASE()` | Default database of the session |
| `information_schema.SCHEMATA` | Database name, default charset, and default collation |
| `information_schema.TABLES` | Table metadata, including database and storage engine |
| `information_schema.COLUMNS` | Column metadata, data types, charset/collation if applicable |

Example retrieving the list of databases with default charset/collation:

~~~sql
SELECT SCHEMA_NAME,
       DEFAULT_CHARACTER_SET_NAME,
       DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
ORDER BY SCHEMA_NAME;
~~~

Example finding tables in the current database:

~~~sql
SELECT TABLE_NAME, TABLE_TYPE, ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME;
~~~

Metadata results help verify deployment environments and spot differences between development, staging, and production. When comparing, use an account with privileges to see all relevant objects; a privilege-restricted listing can cause incomplete reports.

## 11. Common Errors

| Symptom | Possible cause | How to handle |
|---|---|---|
| Can't create database or Access denied | Account lacks CREATE privilege, invalid name, or filesystem/server error | Check `SHOW GRANTS`, error log, and database name; ask a DBA to create the database if needed |
| Database exists | The database already exists | Check `SHOW CREATE DATABASE`; use `IF NOT EXISTS` if the goal is only to create when absent |
| Ran `IF NOT EXISTS` yet charset still differs from expected | Old database already existed; statement did not update defaults | Use `SHOW CREATE DATABASE`, then `ALTER DATABASE` if defaults need changing |
| No database selected | Session has no default database and statement uses an unqualified table name | Run `USE db_name` or use `db_name.table_name` |
| Table doesn't exist even though table exists in another database | Default database is pointing to the wrong place | Run `SELECT DATABASE()` and reference with fully qualified name |
| Table access returns Access denied after `USE` | Selecting a database does not grant privileges on tables | Check user-host match and `SHOW GRANTS` |
| Vietnamese characters display incorrectly or compare unexpectedly | Charset/collation across server, database, table, column, or connection is inconsistent | Check metadata and connection charset variables; fix at the necessary level |
| Same database name behaves differently across OSs | Case sensitivity or `lower_case_table_names` differences | Use consistent lowercase names and verify configuration before deployment |

When investigating, determine whether the error occurs at database creation, default database selection, name resolution, access privileges, or character conversion. Each stage has different causes and inspection methods.

## 12. Hands-On Lab: Creating a Database and Working with Default Scope

Perform this in a MySQL lab instance or development environment where you are permitted to create databases. The account needs the `CREATE` privilege at the appropriate level.

**Step 1 — Check the environment.** Run:

~~~sql
SELECT VERSION(), DATABASE();
SHOW GLOBAL VARIABLES LIKE 'character_set_server';
SHOW GLOBAL VARIABLES LIKE 'collation_server';
~~~

Record the MySQL version, initial default database, and server default charset/collation.

**Step 2 — Create a database.** Create a lab database with `utf8mb4` charset and a collation supported by your current version:

~~~sql
CREATE DATABASE mysql_schema_lab
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

If the server does not support the collation above, check `SHOW COLLATION LIKE 'utf8mb4%';` and pick an `utf8mb4` collation compatible with your version.

**Step 3 — Verify metadata.** Run `SHOW CREATE DATABASE mysql_schema_lab;` and query `information_schema.SCHEMATA`. Compare the returned charset/collation with the values specified.

**Step 4 — Select the default database.** Run:

~~~sql
USE mysql_schema_lab;
SELECT DATABASE();
~~~

Create a small table without specifying table-level charset/collation:

~~~sql
CREATE TABLE notes (
    note_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    note_text VARCHAR(200) NOT NULL,
    PRIMARY KEY (note_id)
);
~~~

Check the charset/collation of the table and column in `information_schema`.

**Step 5 — Compare short and fully qualified names.** While using `mysql_schema_lab`, run `SELECT * FROM notes;`. Then switch to another database with `USE` (if the account has privileges) and run `SELECT * FROM mysql_schema_lab.notes;`. Observe that the fully qualified name does not depend on the default database.

**Step 6 — Verify session scope.** Open two independent connections. Run `USE mysql_schema_lab` in the first connection and `SELECT DATABASE()` in both. Observe that only the first session changes its default database.

**Step 7 — Verify `IF NOT EXISTS` behavior.** Run `CREATE DATABASE IF NOT EXISTS mysql_schema_lab;` again, then use `SHOW CREATE DATABASE` to verify that this statement does not automatically alter the charset/collation of the existing database.

**Step 8 — Clean up the lab according to your privileges.** If the database was created only for this lab and contains no data to keep, confirm the exact database name and drop it according to your lab procedure. Do not run drop commands on shared databases or databases you did not create.

**Expected outcomes:** create and verify a database, understand default charset/collation, select a database per session, distinguish short table names from fully qualified names, and prove that `USE` does not affect other sessions.

## 13. Project Usage Guidelines

- Create databases through migrations or controlled deployment workflows; restrict `CREATE DATABASE` privileges on runtime application accounts.
- Choose `utf8mb4` and collations based on language, search, and comparison requirements of the business domain.
- Use `SHOW CREATE DATABASE` and `information_schema.SCHEMATA` to verify configuration rather than relying solely on migration files.
- Set a consistent default database for each connection pool; do not assume `USE` has server-wide scope.
- Use fully qualified names when querying across multiple databases or when reducing dependency on session state.
- Do not treat `CREATE DATABASE IF NOT EXISTS` as a mechanism for updating an existing database's configuration.
- When changing charset/collation, distinguish changing database defaults from converting table and column data.
- Verify privileges separately for creating databases and for operating on individual objects inside a database.

Mastering `CREATE DATABASE`, `USE`, and default database scope helps organize schemas cleanly, deploy environments consistently, and prevent query errors caused by sessions pointing to the wrong database. This is the foundation for continuing to manage metadata, create tables, constraints, and other objects in MySQL.
