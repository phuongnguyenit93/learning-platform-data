# Granting Database Account Permissions with Least Privilege

## 1. Why Shouldn't an Application Use a Full-Privilege Database Account?

A Spring Data JDBC application needs to connect to a database to read and write aggregates. The simplest approach during local development is often using an account with very broad permissions, such as a database administrator account or schema owner account.

This is convenient for experimentation but dangerous in production. If the application is compromised, a SQL injection bug, credential leak, or accidental write bug could allow an attacker to:

- Read data outside the application's business scope.
- Modify or delete unrelated tables.
- Drop schemas or databases.
- Create users and grant privileges to other accounts.
- Alter table structures or create malicious objects.
- Access data belonging to another application sharing the same database server.

The **least privilege** principle requires each account to hold only the permissions needed to perform its specific duties. The application runtime account typically needs to read and write specific tables; it does not need permissions to create databases, alter schemas, or manage users.

In a Spring Data JDBC system, you must account for operations on aggregate roots, child tables, sequences, views, functions, and custom SQL statements. If you grant permissions only on the root table and forget child tables or sequences, repositories may read partially yet fail when saving aggregates.

This lesson covers separating runtime, migration, and administrative accounts; granting schema and table privileges; configuring Spring Boot, Flyway, and Liquibase; verifying effective permissions; and resolving common permission errors.

## 2. Distinguishing Accounts, Roles, and Privileges

Different database management systems use slightly different terminology, but three concepts can be distinguished:

| Concept | Meaning |
| --- | --- |
| User/account | Identity used to authenticate when opening a connection |
| Role | Group of privileges that can be assigned to one or more users |
| Privilege | Specific permission on a database, schema, table, sequence, view, or routine |

Instead of granting individual privileges directly to many users, it is usually better to create functional roles and assign users to those roles.

Example:

~~~text
orders_runtime
  SELECT, INSERT, UPDATE, DELETE on required business tables

orders_readonly
  SELECT on permitted reporting views

orders_migrator
  CREATE, ALTER, DROP, and DDL privileges required for migrations

database_admin
  Database administration privileges for operational tasks
~~~

The runtime user is assigned the orders_runtime role. The migration account receives separate privileges to create or modify schemas. Administrative accounts are reserved strictly for authorized personnel or operational procedures.

## 3. Permissions Typically Needed by Spring Data JDBC

Spring Data JDBC persists data along aggregate boundaries. A single repository save can read or write multiple tables:

~~~text
PurchaseOrderRepository
       |
       v
purchase_order
       |
       +--> purchase_order_line
       |
       +--> shipment
~~~

If an aggregate contains a child collection, saving it may insert, update, or delete child rows according to aggregate semantics. Therefore, the runtime account needs privileges on every object that use cases actually access.

### 3.1. Read Privileges

Repository queries typically require SELECT on:

- Aggregate root tables.
- Child tables belonging to aggregates.
- Tables joined in custom queries.
- Views or materialized views read by the application.

If a repository only needs to read a subset of non-sensitive columns, consider column-level privileges where supported by the database and compatible with mappings/queries.

### 3.2. Write Privileges

CRUD operations may require:

| Spring Data JDBC operation | Database privileges usually required |
| --- | --- |
| findById, findAll, derived query | SELECT |
| Insert aggregate root | INSERT |
| Insert child entity | INSERT on child table |
| Update aggregate root | UPDATE and potentially SELECT to read data |
| Synchronize child collection | DELETE and INSERT/UPDATE on child table depending on strategy |
| deleteById | DELETE on root and related child tables |
| Custom @Modifying UPDATE | UPDATE |
| Custom @Modifying DELETE | DELETE |

Do not grant INSERT/UPDATE/DELETE only on the root table and assume aggregate saves will succeed. Inspect the actual SQL and child tables used by mappings.

### 3.3. Sequence and Generated ID Privileges

Some databases use sequences to generate IDs. In PostgreSQL, an account may need USAGE on a sequence to call nextval. Without this privilege, INSERT can fail even if the user has INSERT on the table.

MySQL AUTO_INCREMENT and SQL Server IDENTITY work differently; do not apply PostgreSQL-style sequence grants across every database.

### 3.4. Additional Privileges That May Be Needed

Grant only when the application actually uses them:

- EXECUTE on stored procedures or functions.
- SELECT on views.
- USAGE on schemas or sequences.
- Access to outbox/audit tables.
- Metadata read privileges if the application has custom introspection features.

Typically, a runtime account does not need:

- CREATE DATABASE or CREATE SCHEMA.
- CREATE, ALTER, or DROP TABLE.
- DROP DATABASE.
- TRUNCATE unless the application uses that operation.
- GRANT OPTION.
- Permission to create users or roles.
- SUPERUSER, DBA, db_owner, or equivalent administrative roles.

## 4. Separating Runtime and Migration Accounts

An application generally has at least two distinct types of database work:

1. Running the application: reading and writing business data.
2. Upgrading the schema: creating tables, adding columns, indexes, constraints, or altering structure.

These two tasks have very different privilege requirements.

### 4.1. Runtime Account

The runtime account is used by the DataSource that Spring Data JDBC repositories use while serving requests.

Example privileges:

- SELECT, INSERT, UPDATE, DELETE on the business schema.
- USAGE on the schema.
- USAGE/SELECT on required sequences.
- EXECUTE on routines if use cases call routines.

Do not grant DDL privileges just so the application can alter schemas itself at startup.

### 4.2. Migration Account

Flyway or Liquibase may require:

- CREATE TABLE.
- ALTER TABLE.
- CREATE INDEX.
- CREATE SEQUENCE.
- CREATE/DROP constraints.
- Performing controlled data migrations.

This account should be used in the deployment pipeline or a controlled migration phase. Never use it as the default username for the request-serving connection pool.

### 4.3. Administrative Account

The DBA/admin account is kept separate for:

- Creating databases and schemas.
- Creating users/roles.
- Granting and revoking privileges.
- Performing privileged operational tasks.
- Resolving incidents that require administrative access.

Do not store administrative credentials in application.yml or in the runtime application's container environment.

### 4.4. Separation Diagram

~~~text
Deployment pipeline
       |
       v
Migration account
  CREATE / ALTER / INDEX / CONSTRAINT
       |
       v
Database schema
       ^
       |
Application runtime
       |
       v
Runtime account
  SELECT / INSERT / UPDATE / DELETE

DBA / operator
       |
       v
Admin account
  USER / ROLE / DATABASE / SCHEMA administration
~~~

## 5. Granting Permissions in PostgreSQL

PostgreSQL distinguishes privileges across databases, schemas, tables, sequences, functions, and other objects. To access a table in a schema, a user typically needs CONNECT on the database, USAGE on the schema, and the appropriate privilege on the table.

### 5.1. Creating the Runtime Role

Example:

~~~sql
CREATE ROLE orders_runtime LOGIN PASSWORD 'replace-with-secret';
~~~

In production, the password must come from a secret manager or approved security workflow. Never commit real passwords into migrations or source control.

### 5.2. Granting Connect and Schema Privileges

~~~sql
GRANT CONNECT ON DATABASE orders TO orders_runtime;
GRANT USAGE ON SCHEMA app TO orders_runtime;
~~~

CONNECT allows opening a session to the database. USAGE allows resolving objects inside the schema, without automatically granting table read/write privileges.

### 5.3. Granting Privileges on Existing Tables

~~~sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA app
TO orders_runtime;
~~~

This command applies to tables existing in schema app at the time it runs. If the application never deletes data, omit DELETE. If some tables are read-only, grant SELECT individually rather than granting write privileges across the entire schema.

### 5.4. Granting Privileges on Sequences

~~~sql
GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA app
TO orders_runtime;
~~~

USAGE allows using the sequence for database-defined operations. SELECT allows reading sequence state such as currval. Only grant UPDATE if the application genuinely needs privileged operations such as setval.

### 5.5. Setting Default Privileges for Future Objects

When migrations continue creating new tables, privileges granted on existing tables do not automatically apply to new objects. You can configure default privileges:

~~~sql
ALTER DEFAULT PRIVILEGES
FOR ROLE orders_migrator
IN SCHEMA app
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES
TO orders_runtime;

ALTER DEFAULT PRIVILEGES
FOR ROLE orders_migrator
IN SCHEMA app
GRANT USAGE, SELECT ON SEQUENCES
TO orders_runtime;
~~~

Key point: default privileges apply to future objects created by the specified role. If migrations actually create objects under a different owner role, configure default privileges for that creator role.

ALTER DEFAULT PRIVILEGES does not change privileges on already-existing objects. You must run both GRANT for existing objects and default privileges for future objects.

### 5.6. Checking Privileges

PostgreSQL provides privilege inspection functions:

~~~sql
SELECT has_schema_privilege(
    'orders_runtime',
    'app',
    'USAGE'
);

SELECT has_table_privilege(
    'orders_runtime',
    'app.purchase_order',
    'SELECT'
);

SELECT has_sequence_privilege(
    'orders_runtime',
    'app.purchase_order_id_seq',
    'USAGE'
);
~~~

In psql, you can use metadata commands such as \du, \dn+, and \dp to inspect roles, schemas, and table privileges.

### 5.7. Watch Out for PUBLIC Privileges

PostgreSQL grants certain default privileges to PUBLIC on some object types, such as CONNECT/TEMPORARY on databases and EXECUTE on functions under default settings. If your application requires strict access control, review and revoke unnecessary PUBLIC privileges.

Do not run broad REVOKE statements without understanding their impact on other applications. Changing shared privileges can break existing workloads.

## 6. Granting Permissions in MySQL

MySQL supports privileges at global, database, table, column, and routine levels. For runtime applications, scope grants to the required database or tables.

### 6.1. Creating a Host-Restricted User

~~~sql
CREATE USER 'orders_runtime'@'10.%'
IDENTIFIED BY 'replace-with-secret';
~~~

The host portion restricts where the user can connect according to MySQL account rules. Choose a scope matching the deployment network; do not use a wider wildcard than necessary.

### 6.2. Granting DML Privileges on a Database

~~~sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON orders.*
TO 'orders_runtime'@'10.%';
~~~

If the application only needs a subset of tables, grant privileges per table:

~~~sql
GRANT SELECT, INSERT, UPDATE
ON orders.purchase_order
TO 'orders_runtime'@'10.%';

GRANT SELECT, INSERT, UPDATE, DELETE
ON orders.purchase_order_line
TO 'orders_runtime'@'10.%';
~~~

Do not grant ALL PRIVILEGES or GRANT OPTION if the application has no privilege-management duties.

### 6.3. Verifying Privileges

~~~sql
SHOW GRANTS FOR 'orders_runtime'@'10.%';
~~~

MySQL does not use sequence objects in the same way PostgreSQL does for AUTO_INCREMENT. If the application uses stored procedures or functions, grant EXECUTE on specific routines rather than globally.

## 7. Granting Permissions in SQL Server

SQL Server supports database roles and schema-level permissions. You can create a dedicated role for the application:

~~~sql
CREATE ROLE orders_runtime;

GRANT SELECT, INSERT, UPDATE, DELETE
ON SCHEMA::orders
TO orders_runtime;

ALTER ROLE orders_runtime
ADD MEMBER orders_app;
~~~

In this example:

- orders_runtime is the database role.
- orders_app is a database user created and mapped to an appropriate login.
- DML privileges are granted on schema orders.
- The user is added to the role to inherit those permissions.

Schema-level grants apply to objects inside the schema according to the granted permissions. If the schema also holds sensitive tables the application should not access, separate schemas or grant permissions per object.

Do not add the runtime account to db_owner or db_ddladmin. Those roles grant broader scope than normal DML needs.

You can check effective permissions with:

~~~sql
SELECT *
FROM fn_my_permissions('orders.purchase_order', 'OBJECT');
~~~

## 8. Configuring Spring Boot with the Runtime Account

The application's primary DataSource should use the runtime account:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-host:5432/orders
    username: ${DB_RUNTIME_USER}
    password: ${DB_RUNTIME_PASSWORD}
~~~

The corresponding environment variables or secrets are supplied by the deployment environment. Never put real passwords into committed configuration files.

Spring Data JDBC repositories, JdbcTemplate, and the transaction manager should use this runtime DataSource for business operations.

### 8.1. Configuring Flyway with a Separate Migration Account

Spring Boot allows Flyway to use separate credentials:

~~~yaml
spring:
  flyway:
    url: jdbc:postgresql://db-host:5432/orders
    user: ${DB_MIGRATION_USER}
    password: ${DB_MIGRATION_PASSWORD}
~~~

When a separate Flyway datasource is configured, migrations can run under an account with DDL privileges while the application continues using the restricted runtime account.

Without separate connection details, Flyway may reuse the application's primary DataSource. In that case, migrations run with runtime account permissions and can fail when ALTER or CREATE is needed.

### 8.2. Configuring Liquibase with a Separate Account

Similarly, Liquibase has its own properties:

~~~yaml
spring:
  liquibase:
    url: jdbc:postgresql://db-host:5432/orders
    user: ${DB_MIGRATION_USER}
    password: ${DB_MIGRATION_PASSWORD}
~~~

Configure only one migration tool as the owner of the schema workflow. Never let Flyway and Liquibase both modify the same schema without an explicit coordination design.

### 8.3. When Using Multiple DataSources

If the application defines a separate DataSource for Flyway or Liquibase alongside the runtime DataSource:

- Ensure the migration bean does not accidentally become the primary DataSource for repositories.
- Use Flyway/Liquibase configuration aligned with your Spring Boot version.
- If creating beans manually, verify qualifiers, Primary, and transaction managers.
- Confirm Spring Data JDBC repositories still use the runtime account.

## 9. Read-Only Accounts for Reporting

Some applications have reporting flows that never write data. You can create a separate role with SELECT only on reporting views or tables:

~~~sql
GRANT CONNECT ON DATABASE orders TO orders_report;
GRANT USAGE ON SCHEMA reporting TO orders_report;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO orders_report;
~~~

This account should not be used by repositories or services performing writes. Separating a read-only role limits damage if reporting credentials are exposed.

If only specific columns or rows should be visible, create views exposing only the needed data and grant SELECT on those views.

## 10. Granting Privileges for Audit, Outbox, and Custom SQL Tables

Spring Data JDBC applications often use additional technical tables:

- audit_log.
- outbox_message.
- import_checkpoint.
- job_execution.
- idempotency_record.

If callbacks, application services, or batch jobs write to these tables, the runtime account needs appropriate permissions on them.

Do not grant database-wide permissions just because a use case adds one table. Grant permissions on the exact objects:

~~~sql
GRANT SELECT, INSERT
ON TABLE app.outbox_message
TO orders_runtime;

GRANT SELECT, INSERT, UPDATE
ON TABLE app.import_checkpoint
TO orders_runtime;
~~~

If custom queries invoke stored procedures, grant EXECUTE on the specific routines. If queries use views, grant SELECT on the views and verify underlying table access according to your database's security model.

## 11. Database Permissions Do Not Replace Domain Authorization

Least privilege at the database layer limits what a connection can do. It does not decide whether an end user is allowed to view or edit a specific order.

For example, if the runtime account has SELECT on purchase_order, at the database level it can read every row in the table. The application must still check:

- Is the current user authorized to access this order?
- Does the order belong to the request's tenant?
- Is the user's role allowed to perform this status transition?
- Which sensitive data fields may be returned?

In multi-tenant systems, you can combine:

- Tenant_id predicates in queries.
- Views restricting data.
- Row-level security if supported by the database.
- Schema/database isolation per tenant when required by architecture.

Never rely on a client-supplied tenant ID for access decisions. Tenant context must be authenticated on the server and applied consistently to queries or policies.

## 12. Schema Privileges and Search Path

In PostgreSQL, an account can hold SELECT on a table and still fail to access it without USAGE on the containing schema.

Additionally, search_path determines which schemas are searched when SQL references unqualified table names. You should:

- Use explicit schemas in configuration or mappings where needed.
- Keep search_path restricted to a list of trusted schemas.
- Avoid placing schemas where the runtime user can create objects into search_path unnecessarily.
- Audit schema ownership and CREATE privileges.

CREATE privilege on a schema allows creating objects inside it. Runtime accounts normally do not need this privilege.

## 13. Testing with the Actual Runtime Account

An application succeeding under an admin account does not prove the runtime account has enough permissions or is properly restricted.

Include integration smoke tests running with the runtime account:

1. Connect to the database using runtime credentials.
2. Read an aggregate root.
3. Read an aggregate with a child collection.
4. Insert a new aggregate.
5. Update the aggregate and children.
6. Delete an aggregate if allowed by use cases.
7. Write audit/outbox/checkpoint records if the application uses those tables.
8. Confirm DDL operations are rejected.
9. Confirm access to out-of-scope schemas/tables is rejected.

### 13.1. Testing Required Permissions

PostgreSQL check example:

~~~sql
SELECT has_table_privilege(
    current_user,
    'app.purchase_order',
    'SELECT'
);
~~~

### 13.2. Testing Disallowed Permissions

The runtime account should be denied when attempting operations such as:

~~~sql
CREATE TABLE app.unexpected_table (
    id BIGINT PRIMARY KEY
);

DROP TABLE app.purchase_order;
~~~

Run these negative tests in a test environment or test database—never run destructive commands in production.

## 14. Managing and Rotating Credentials

Least privilege loses its value if credentials are widely shared or stored in many places.

Principles:

- Give each application or workload its own credentials.
- Never share passwords across runtime, migration, and admin accounts.
- Store secrets in a secret manager or platform secrets store.
- Never commit passwords to Git.
- Never place passwords in logs, exception messages, or metric labels.
- Restrict allowed source hosts/networks.
- Monitor logins and anomalous activity.
- Rotate credentials according to policy.

When changing the runtime account's password, update both the secret store and the connection pool. The pool may hold existing connections authenticated with the old credential; follow an appropriate refresh/restart procedure before revoking the old credential.

Do not rotate the migration account password on the exact same schedule as the runtime account if the two accounts have distinct lifecycles and owners.

## 15. Common Mistakes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Permission denied for schema | Missing USAGE on PostgreSQL schema | Grant USAGE on the right schema |
| Permission denied for table | Missing SELECT/INSERT/UPDATE/DELETE on table | Grant exact DML privileges on required objects |
| Permission denied for sequence | Runtime user lacks USAGE on sequence | Grant appropriate sequence privileges |
| Root save succeeds but child insert fails | Missing privileges on child table | Audit all tables belonging to the aggregate |
| Repository reads fine but save fails | Has SELECT but lacks write privileges | Grant INSERT/UPDATE/DELETE per use case |
| Flyway fails unable to ALTER TABLE | Migrations using runtime credentials | Configure a separate migration account |
| Newly created table inaccessible to app | Default privileges not configured for object creator | Update ALTER DEFAULT PRIVILEGES for the owner role |
| Application can access too many tables | Database-wide grant or overly broad role | Narrow down to required schema, tables, or views |
| Runtime account can DROP/ALTER | Using owner, db_owner, or DDL privileges | Transfer ownership to admin role and revoke DDL privileges |
| App works locally but fails in production | Local uses admin account, production uses runtime role | Run integration tests using the runtime account |

## 16. Least-Privilege Provisioning Workflow

When preparing a database for a Spring Data JDBC application:

1. **List use cases:** identify repositories, custom queries, batch jobs, and technical tables in use.
2. **List objects:** root tables, child tables, sequences, views, functions, audit, and outbox.
3. **Classify accounts:** runtime, read-only, migration, and admin.
4. **Create roles:** group permissions serving the same purpose into dedicated roles.
5. **Grant on existing objects:** grant only necessary SELECT/DML/EXECUTE privileges.
6. **Set default privileges:** ensure new objects created by the migration owner receive appropriate grants for the runtime role.
7. **Configure credentials:** runtime DataSource uses the runtime account; Flyway/Liquibase use the migration account.
8. **Verify with the runtime user:** run smoke tests on a real database.
9. **Test forbidden privileges:** verify the runtime user cannot ALTER, DROP, CREATE, or GRANT.
10. **Monitor and audit:** review grants after every migration or use-case change.

## 17. Self-Practice Exercises

**Exercise 1 — Create a runtime role.** Create an account with only SELECT, INSERT, UPDATE, and DELETE on the business schema. Verify the account cannot create or drop tables.

**Exercise 2 — PostgreSQL sequence.** Create a table using a sequence, grant table privileges, and intentionally omit sequence privileges. Attempt an insert to observe the error, then grant USAGE and re-run.

**Exercise 3 — Child table.** Create an aggregate with a child collection. Grant privileges only on the root table, call save, and identify which privileges are missing.

**Exercise 4 — Default privileges.** Configure ALTER DEFAULT PRIVILEGES for the migration owner, create a new table, and confirm the runtime role can access it.

**Exercise 5 — Separate Flyway.** Configure Flyway with a migration account and the primary DataSource with a runtime account. Confirm migrations run while the application lacks DDL privileges.

**Exercise 6 — MySQL.** Create a host-restricted user, grant DML on one database, and inspect grants with SHOW GRANTS.

**Exercise 7 — SQL Server.** Create a database role, grant schema permissions, and add the runtime user to the role. Verify effective permissions on a table.

**Exercise 8 — Read-only reporting.** Create a reporting view and a role with SELECT only on that view. Confirm the role cannot read ungranted business tables.

**Exercise 9 — Test negative permissions.** Run tests as the runtime account and verify CREATE, ALTER, DROP, and GRANT are all denied.

**Exercise 10 — Rotate credentials.** Change the runtime account password in the secret store, refresh the connection pool, and confirm the application reconnects with the new credentials.

## 18. Takeaways

A Spring Data JDBC runtime account should hold only the privileges needed to execute business use cases. For aggregate operations, account for root tables, child tables, sequences, views, functions, audit, and outbox tables. Privileges on the root table do not automatically grant access to other objects.

Separate the runtime account from migration and admin accounts. Runtime typically needs SELECT/INSERT/UPDATE/DELETE on permitted objects; Flyway or Liquibase uses separate credentials with DDL privileges; admin accounts must never be embedded in application configuration.

PostgreSQL requires attention to CONNECT, schema USAGE, table privileges, sequence privileges, and ALTER DEFAULT PRIVILEGES for future objects. MySQL supports database/table and host-scoped grants. SQL Server supports database roles and schema-level permissions. Always verify permissions using the runtime account itself, testing both allowed operations and operations that must be denied.

### References

- [PostgreSQL – Privileges](https://www.postgresql.org/docs/current/ddl-priv.html)
- [PostgreSQL – ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html)
- [MySQL 8.4 – GRANT Statement](https://dev.mysql.com/doc/refman/8.4/en/grant.html)
- [SQL Server – Getting Started with Database Engine Permissions](https://learn.microsoft.com/en-us/sql/relational-databases/security/authentication-access/getting-started-with-database-engine-permissions)
- [SQL Server – GRANT Schema Permissions](https://learn.microsoft.com/en-us/sql/t-sql/statements/grant-schema-permissions-transact-sql)
- [Spring Boot – Database Initialization and Flyway/Liquibase DataSources](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
