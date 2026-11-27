# Relationship Between Database, Schema, Table, and User Account

This lesson belongs to the **Schema and Metadata** chapter of the `DATABASE_MYSQL` module. The module aims to help you master MySQL—from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, privilege management, backups, and troubleshooting relational database operations. Properly understanding the relationship between database, schema, table, and account helps organize data logically, read metadata accurately, and grant access permissions with the right scope.

After this lesson, you will be able to describe the logical structure of a MySQL Server, explain why `database` and `schema` are equivalent terms in MySQL, distinguish a schema from tables and accounts, determine the default database of a session, inspect structure through `INFORMATION_SCHEMA`, and design account privileges following the principle of least privilege.

## 1. Overview of MySQL's Logical Structure

A MySQL Server (instance) manages multiple databases. In MySQL, **schema is synonymous with database**. A database/schema contains objects such as tables, views, stored procedures, functions, triggers, and events. Tables contain columns and rows of data; indexes and constraints describe access paths, uniqueness, and relationships between data.

A MySQL user account is an identity used to authenticate connections to the Server. An account is identified by a user-and-host pair, and is then granted privileges across the entire Server or on specific databases and objects.

You can visualize the relationship as follows:

~~~mermaid
flowchart TD
    S["MySQL Server / Instance"]
    S --> D1["Database / Schema: shop"]
    S --> D2["Database / Schema: analytics"]
    S --> D3["System schemas"]
    D1 --> T1["Table: customers"]
    D1 --> T2["Table: orders"]
    D1 --> V1["View: active_customers"]
    D1 --> R1["Stored routines, triggers, events"]
    T1 --> C1["Columns, indexes, constraints"]
    T2 --> C2["Columns, indexes, constraints"]
    U1["Account: 'shop_app'@'10.20.0.15'"] -. "GRANT on shop.*" .-> D1
    U2["Account: 'reporter'@'10.20.0.0/24'"] -. "GRANT SELECT on table" .-> T2
~~~

The diagram illustrates two different kinds of relationships:

- A database contains data objects within a logical namespace.
- An account exists at the Server level and is granted privileges over scopes. An account is not an object residing inside the database it is permitted to access.

For example, the account `'shop_app'@'10.20.0.15'` can be granted privileges on the `shop` database. The `shop` database does not become the private property of this account, nor does the account automatically gain privileges on other databases.

## 2. Database and Schema in MySQL

In some database management systems, database and schema have different meanings. For example, a schema may represent a group of objects owned by a user inside a database. **MySQL does not use that distinction: schema and database are synonymous.**

You can use both pairs of statements below:

~~~sql
CREATE DATABASE shop;
CREATE SCHEMA analytics;

SHOW DATABASES;
SHOW SCHEMAS;

DROP DATABASE analytics;
-- Equivalent syntax if you want to drop analytics:
-- DROP SCHEMA analytics;
~~~

In MySQL, `CREATE SCHEMA` and `CREATE DATABASE` are equivalent forms. Similarly, `SHOW SCHEMAS` and `SHOW DATABASES` return the list of databases/schemas that the account has privilege to see.

When reading cross-DBMS documentation, pay attention to context:

| DBMS | Common interpretation |
|---|---|
| MySQL | Schema is synonymous with database |
| PostgreSQL | A database can contain multiple schemas; a schema is a namespace inside a database |
| SQL Server | A database can contain multiple schemas; a schema is a namespace/object group |
| Oracle Database | A schema is the set of objects belonging to a database user |

Do not mechanically apply the schema concept from PostgreSQL, SQL Server, or Oracle to MySQL. With MySQL, when documentation mentions `schema name`, it usually refers directly to the database name.

### Creating a database with charset and collation

A database can specify a default character set and collation so that new tables and columns inherit them when not declared explicitly:

~~~sql
CREATE DATABASE shop
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
~~~

This example fits modern MySQL versions that support the `utf8mb4_0900_ai_ci` collation, such as MySQL 8.0 and newer releases. If you maintain MySQL 5.7, choose a collation available in that version, such as `utf8mb4_unicode_ci`.

Check the database configuration:

~~~sql
SHOW CREATE DATABASE shop;

SELECT
    SCHEMA_NAME,
    DEFAULT_CHARACTER_SET_NAME,
    DEFAULT_COLLATION_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
WHERE SCHEMA_NAME = 'shop';
~~~

The charset and collation at the database level are default values. A table or column can declare its own charset/collation, so when verifying actual data settings, inspect both table and column metadata.

### A database is not synonymous with a physical directory

A database/schema is a logical organization seen by SQL. You should not assume that every database always corresponds to a directory that can be copied independently, or that every table always has exactly one file on disk. Storage layout depends on the storage engine, tablespaces, server configuration, and MySQL version. With InnoDB, data and metadata are managed according to InnoDB's storage mechanisms; MySQL 8.0 uses a transactional data dictionary.

When backing up or migrating data, use appropriate backup/restore tools and procedures such as MySQL Shell dump utilities, `mysqldump`, or supported physical backup solutions. Do not arbitrarily copy database directories while the Server is running.

## 3. A Table Is an Object Inside a Database/Schema

A table is a structure that stores data in rows and columns. In MySQL, a table is identified by the database/schema name and the table name:

~~~text
database_name.table_name
~~~

For example, `shop.customers` is the `customers` table belonging to the `shop` database. If you have two databases, `shop` and `archive`, both can contain a table named `orders`:

~~~sql
shop.orders
archive.orders
~~~

These are two distinct tables. A table name only needs to be unique within its corresponding schema, not necessarily unique across the entire Server.

Create an example table:

~~~sql
CREATE TABLE shop.customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;
~~~

In the example:

- `shop` is the database/schema containing the table.
- `customers` is the table name.
- The fields `customer_id`, `email`, `full_name`, and `created_at` are columns.
- Each customer record is a row.
- The primary key uniquely identifies a row.
- The unique key ensures emails are not duplicated.
- InnoDB is the storage engine of the table.

To view the actual definition:

~~~sql
SHOW CREATE TABLE shop.customers;
~~~

If you have already selected a default database with `USE shop`, you can write the shorter form:

~~~sql
SHOW CREATE TABLE customers;
~~~

However, when writing deployment or migration scripts that work across multiple databases, the fully qualified name `shop.customers` helps avoid confusion.

### Other objects in a schema

A database does not only contain tables. Common objects include:

| Object | Role |
|---|---|
| Base table | Stores data in rows and columns |
| View | Provides a named query as a logical table |
| Stored procedure | Groups SQL operations into a callable procedure |
| Stored function | Returns a value and can be used in SQL expressions |
| Trigger | Executes automatically when certain operations occur on a table |
| Event | Schedules statement execution based on time |
| Index | Structure supporting search and sorting; attached to a table |
| Constraint | Rules such as PRIMARY KEY, UNIQUE, FOREIGN KEY, CHECK |

Indexes and constraints are components of a table, not standalone database objects. Triggers are attached to a table; stored routines and events belong to a schema.

## 4. User Accounts Exist at the MySQL Server Level

A MySQL account is written in the form:

~~~sql
'user_name'@'host_name'
~~~

Examples:

- `'shop_app'@'localhost'`: an application connecting from the local machine.
- `'shop_app'@'10.20.0.15'`: an application connecting from a specific IP address.
- `'reporter'@'10.20.0.0/24'`: an account for a specified IPv4 network.

An account is created on the Server with `CREATE USER`. It does not need to be created inside a specific database:

~~~sql
CREATE USER 'shop_app'@'10.20.0.15'
    IDENTIFIED BY 'replace_with_a_strong_password';
~~~

Immediately after creation, the account can authenticate a connection if the authentication configuration and host match, but it does not yet automatically have privileges to read or write application databases. Privileges must be granted separately:

~~~sql
GRANT SELECT, INSERT, UPDATE
    ON shop.*
    TO 'shop_app'@'10.20.0.15';
~~~

The statement above grants privileges on all applicable tables and objects in the `shop` database according to the scope of the granted privileges. It does not grant privileges on the `analytics` database.

One account can be granted privileges on multiple databases; multiple accounts can access the same database with different privilege levels. The account-database relationship is therefore a privilege-assignment relationship, not a containment or ownership relationship.

### Distinguishing account, user, and session

In everyday conversation, the terms user, account, and connection are often used interchangeably, but they should be distinguished:

- **Account:** MySQL's authentication and privilege record, identified by a user-host pair.
- **Client identity:** the username and host information the client uses when connecting.
- **Session/connection:** the working session created after a connection is accepted. Each session has its own state, such as default database, transaction state, and session variables.
- **Default database:** the schema that the session uses when a SQL statement does not specify a database name.

One account can open multiple concurrent sessions. Each session can choose a different default database without modifying the account or its granted privileges.

## 5. Default Database and How Tables Are Qualified

After logging in, a session can select a default database:

~~~sql
USE shop;

SELECT DATABASE();
~~~

`DATABASE()` returns the name of the current session's default database. If the session has not selected a database, the result is `NULL`.

Once `shop` is selected, a query can reference a table by its unqualified name:

~~~sql
SELECT customer_id, email
FROM customers;
~~~

Or reference it with its fully qualified name, regardless of the current default database:

~~~sql
SELECT customer_id, email
FROM shop.customers;
~~~

The difference lies in naming resolution, not access privileges:

- `USE shop` only selects the default database for the session.
- `USE shop` does not grant additional privileges to the account.
- If the account lacks the required privileges on `shop`, selecting the default database will not allow the query to succeed.
- Using the fully qualified name `shop.customers` avoids depending on the default database.

One account can access multiple databases on which it has been granted privileges:

~~~sql
SELECT * FROM shop.customers;
SELECT * FROM analytics.monthly_sales;
~~~

Whether access succeeds depends on the account's privileges on each object. The default database is not the only database an account is permitted to access.

### SHOW DATABASES and schema visibility

The statement:

~~~sql
SHOW DATABASES;
~~~

does not necessarily display every database on the Server. A regular account only sees databases on which it has some privilege, unless it holds the global `SHOW DATABASES` privilege or falls under a special privilege configuration case.

Therefore, not seeing a database in `SHOW DATABASES` is not enough to conclude that the database does not exist. An administrator needs to check visibility privileges and access permissions.

## 6. At What Scopes Are Privileges Granted?

MySQL has multiple privilege levels. They can be viewed from broadest to narrowest:

| Scope | GRANT syntax | Effective scope |
|---|---|---|
| Entire Server | `ON *.*` | All databases and corresponding objects on the Server |
| A database/schema | `ON shop.*` | Objects within the `shop` database |
| A table/view | `ON shop.customers` | A specific table or view |
| Specific columns | `ON shop.customers (email, full_name)` | The specified columns |
| A stored routine | `ON PROCEDURE shop.rebuild_summary` | A specific procedure; functions use the `FUNCTION` keyword |

Example of granting read access to an entire database:

~~~sql
GRANT SELECT
    ON shop.*
    TO 'shop_reader'@'10.20.0.0/24';
~~~

Example of allowing reads on only one table:

~~~sql
GRANT SELECT
    ON shop.orders
    TO 'support_agent'@'10.20.0.21';
~~~

Example of restricting to specific columns:

~~~sql
GRANT SELECT (customer_id, email, full_name)
    ON shop.customers
    TO 'support_agent'@'10.20.0.21';
~~~

Example of allowing execution of only one procedure:

~~~sql
GRANT EXECUTE
    ON PROCEDURE shop.rebuild_daily_summary
    TO 'report_job'@'10.20.0.30';
~~~

Do not grant global privileges just to fix an access error on a single database. Global privileges have a much broader impact than database or table privileges.

### Privileges are additive

Privileges from multiple scopes are combined when MySQL checks an operation. For example, an account with global `SELECT` already has privilege to read every table globally; omitting `SELECT` at a specific database level does not automatically revoke that global privilege.

MySQL 8.0 and later support partial revokes when configured, though this is a specialized administrative mechanism. For standard configurations, avoid granting overly broad privileges from the start.

Examples of role-based privilege design:

| Account type | Appropriate privileges |
|---|---|
| Business runtime application | SELECT, INSERT, UPDATE on required databases; DELETE only if truly needed |
| Support staff | SELECT on required lookup tables or views |
| Reporting | SELECT on reporting databases or restricted views |
| Migration/deployment | CREATE, ALTER, INDEX, and necessary DDL privileges during deployment windows |
| DBA | Global administrative privileges aligned with operational responsibilities |

Do not use a DBA account for routine application connections. Separating the application account from the migration account reduces blast radius if the application's credentials are compromised.

## 7. Complete Example: Creating a Schema, Tables, and an Application Account

Suppose you are building a store application. The Server has a `shop` database containing customers and orders. The application connects from `10.20.0.15` and only needs to read, insert, and update business data.

### Step 1: create the database

~~~sql
CREATE DATABASE shop
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
~~~

### Step 2: create the tables

~~~sql
CREATE TABLE shop.customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE = InnoDB;

CREATE TABLE shop.orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_total DECIMAL(12, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    KEY ix_orders_customer_created (customer_id, created_at),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES shop.customers (customer_id)
) ENGINE = InnoDB;
~~~

Both tables reside in the same `shop` schema. The foreign key links `orders.customer_id` to the primary key `customers.customer_id`.

### Step 3: create the application account

~~~sql
CREATE USER 'shop_app'@'10.20.0.15'
    IDENTIFIED BY 'replace_with_a_strong_password';
~~~

### Step 4: grant required privileges

~~~sql
GRANT SELECT, INSERT, UPDATE
    ON shop.*
    TO 'shop_app'@'10.20.0.15';
~~~

If the application needs to delete orders, evaluate the business requirement and grant `DELETE` separately. If the application does not create tables or alter the schema at runtime, do not grant `CREATE`, `ALTER`, or `DROP` to the runtime account.

### Step 5: verify privileges

~~~sql
SHOW GRANTS FOR 'shop_app'@'10.20.0.15';
~~~

After connecting with the application account, check the identity and default database:

~~~sql
SELECT
    USER() AS client_identity,
    CURRENT_USER() AS authenticated_account,
    DATABASE() AS default_database;
~~~

If no database has been selected yet, `DATABASE()` may be `NULL`. Select the database and verify:

~~~sql
USE shop;

SELECT customer_id, email
FROM customers;
~~~

The account can still query the table using the fully qualified name `shop.customers` even without selecting `shop` as the default database, provided it holds the appropriate privileges.

## 8. Inspecting Schemas and Tables via INFORMATION_SCHEMA

MySQL provides the `INFORMATION_SCHEMA` system database for reading metadata: which databases exist, which tables belong to a database, what data types columns have, which indexes are defined, and which privileges are granted.

`INFORMATION_SCHEMA` is a read-only metadata interface. Its tables are implemented as views; do not use `INSERT`, `UPDATE`, or `DELETE` to modify metadata. Metadata visibility is also restricted according to the current account's privileges.

### Listing databases/schemas

~~~sql
SELECT
    SCHEMA_NAME,
    DEFAULT_CHARACTER_SET_NAME,
    DEFAULT_COLLATION_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
ORDER BY SCHEMA_NAME;
~~~

Equivalent within the scope of databases visible to the account:

~~~sql
SHOW DATABASES;
~~~

### Listing tables and views in a schema

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_TYPE,
    ENGINE,
    TABLE_ROWS
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'shop'
ORDER BY TABLE_NAME;
~~~

`TABLE_TYPE` distinguishes base tables from views. For InnoDB, `TABLE_ROWS` is usually an estimated value, not always an exact row count. If you need an exact count, run `SELECT COUNT(*)` on the table and weigh the query cost.

### Inspecting column structure

~~~sql
SELECT
    COLUMN_NAME,
    ORDINAL_POSITION,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    COLUMN_KEY,
    EXTRA
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'customers'
ORDER BY ORDINAL_POSITION;
~~~

This query shows column order, data type, nullability, default value, and attributes such as `AUTO_INCREMENT`.

### Inspecting indexes

~~~sql
SELECT
    INDEX_NAME,
    COLUMN_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    INDEX_TYPE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

A multi-column index has multiple rows in metadata. `SEQ_IN_INDEX` indicates the position of the column within the index.

### Inspecting constraints

~~~sql
SELECT
    CONSTRAINT_NAME,
    CONSTRAINT_TYPE,
    TABLE_SCHEMA,
    TABLE_NAME
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
WHERE TABLE_SCHEMA = 'shop'
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
~~~

To view columns participating in foreign keys:

~~~sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    CONSTRAINT_NAME,
    REFERENCED_TABLE_SCHEMA,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'shop'
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION;
~~~

### Inspecting privileges at schema and table levels

~~~sql
SELECT
    GRANTEE,
    TABLE_SCHEMA,
    PRIVILEGE_TYPE,
    IS_GRANTABLE
FROM INFORMATION_SCHEMA.SCHEMA_PRIVILEGES
WHERE TABLE_SCHEMA = 'shop'
ORDER BY GRANTEE, PRIVILEGE_TYPE;
~~~

~~~sql
SELECT
    GRANTEE,
    TABLE_SCHEMA,
    TABLE_NAME,
    PRIVILEGE_TYPE,
    IS_GRANTABLE
FROM INFORMATION_SCHEMA.TABLE_PRIVILEGES
WHERE TABLE_SCHEMA = 'shop'
ORDER BY GRANTEE, TABLE_NAME, PRIVILEGE_TYPE;
~~~

Privilege metadata may only display grants that the current account is permitted to see. To fully inspect a specific account, an administrator should use:

~~~sql
SHOW GRANTS FOR 'shop_app'@'10.20.0.15';
~~~

### Distinguishing system schemas

A MySQL Server typically has the following system schemas:

| Schema | Purpose |
|---|---|
| `mysql` | Accounts, grants, and system administrative data |
| `information_schema` | Metadata about databases, tables, columns, indexes, constraints, and privileges |
| `performance_schema` | Runtime metrics on operations, instruments, and performance |
| `sys` | Views and helpers for analysis and diagnostics |

Do not directly edit system tables to grant privileges or change structure. Use statements such as `CREATE USER`, `ALTER USER`, `GRANT`, and `REVOKE`. Also do not confuse `INFORMATION_SCHEMA.TABLES` with an application business table: this is metadata provided by MySQL.

## 9. Common Design Mistakes and Misconceptions

| Misconception or mistake | Consequence | How to handle |
|---|---|---|
| Treating schema as a namespace inside a database like PostgreSQL | Object naming and migrations mismatch MySQL's model | Remember that in MySQL, schema is synonymous with database |
| Thinking an account is created inside a database | Privileges configured at the wrong level | Create the account on the Server, then grant privileges on databases/objects |
| Thinking `USE database` grants privileges | Still encountering access denied when querying | Check GRANTs and the actual account via `CURRENT_USER()` |
| Thinking `SHOW DATABASES` always lists every database | Wrongly concluding a database does not exist | Check visibility privileges and use an appropriate admin account |
| Using unqualified table names in multi-database scripts | Querying the wrong table due to different default databases | Use fully qualified `database.table` names |
| Granting `ALL ON *.*` to an application account | Application has overly broad privileges across the entire Server | Grant least privilege at the schema, table, or column level |
| Directly editing `mysql.user` or grant tables | Can corrupt metadata or leave inconsistent state | Use `CREATE USER`, `ALTER USER`, `GRANT`, and `REVOKE` |
| Treating `TABLE_ROWS` in `INFORMATION_SCHEMA` as an exact count | Inaccurate row count reports | Use `COUNT(*)` when an exact count is truly needed |
| Treating a database as a physical directory safe to hot-copy | Inconsistent backup/restore | Use supported backup tools and procedures appropriate for the storage engine |

## 10. Design and Verification Checklist

Before handing off a database to an application or operations team, confirm:

- [ ] Distinguished database/schema according to MySQL's usage.
- [ ] Identified business databases and the tables/views/routines belonging to each schema.
- [ ] Chosen an appropriate default charset and collation.
- [ ] Used fully qualified `database.table` names in scripts that must run independently of the default database.
- [ ] Separated the runtime account from DBA or migration accounts.
- [ ] Each account has a host matching its actual connection origin.
- [ ] Privileges are granted at the right scope: global, schema, table, column, or routine.
- [ ] Verified with `SHOW GRANTS` and tested connecting with the actual application account.
- [ ] Verified metadata using `INFORMATION_SCHEMA`.
- [ ] Identified which databases are system schemas and avoided editing system metadata directly.
- [ ] Established an appropriate backup/restore procedure without relying on copying database directories while the Server is running.

## Official References

The concepts and statements in this lesson were verified against the MySQL 9.7 Reference Manual as of **19-11-2026**:

1. [MySQL Glossary — database and schema](https://dev.mysql.com/doc/refman/9.7/en/glossary.html): schema is a synonym for database in MySQL.
2. [CREATE DATABASE Statement](https://dev.mysql.com/doc/refman/9.7/en/create-database.html): creating a database/schema, default charset, and collation.
3. [USE Statement](https://dev.mysql.com/doc/refman/9.7/en/use.html): selecting the default database for a session.
4. [CREATE TABLE Statement](https://dev.mysql.com/doc/refman/9.7/en/create-table.html): defining tables, columns, indexes, constraints, and storage engine.
5. [MySQL Account Names](https://dev.mysql.com/doc/refman/9.7/en/account-names.html): identifying accounts by user and host.
6. [Privileges Provided by MySQL](https://dev.mysql.com/doc/refman/9.7/en/privileges-provided.html): privilege types and applicable scopes.
7. [Access Control, Stage 2: Request Verification](https://dev.mysql.com/doc/refman/9.7/en/request-access.html): how the Server checks privileges when an account makes a request.
8. [GRANT Statement](https://dev.mysql.com/doc/refman/9.7/en/grant.html): granting privileges at global, database, table, column, and routine levels.
9. [INFORMATION_SCHEMA Introduction](https://dev.mysql.com/doc/refman/9.7/en/information-schema-introduction.html): purpose and how to query metadata.
10. [The INFORMATION_SCHEMA SCHEMATA Table](https://dev.mysql.com/doc/refman/9.7/en/information-schema-schemata-table.html): list of schemas/databases and default charset/collation.
11. [The INFORMATION_SCHEMA TABLES Table](https://dev.mysql.com/doc/refman/9.7/en/information-schema-tables-table.html): table, view, and storage engine metadata.
12. [The INFORMATION_SCHEMA COLUMNS Table](https://dev.mysql.com/doc/refman/9.7/en/information-schema-columns-table.html): column metadata.
13. [The MySQL System Schema](https://dev.mysql.com/doc/refman/9.7/en/system-schema.html): roles of system schemas and the data dictionary.
