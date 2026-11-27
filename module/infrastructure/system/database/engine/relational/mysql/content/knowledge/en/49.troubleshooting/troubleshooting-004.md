# Unknown Database/Table/Column and Distinguishing Name Errors from Missing Privileges

Errors such as `Unknown database`, `Table doesn't exist`, and `Unknown column` typically appear when an application queries the wrong name or the schema has not been deployed properly. However, errors like `Access denied`, `SELECT command denied`, or `UPDATE command denied` have a different cause: the MySQL account lacks privileges to perform the operation. Accurately distinguishing these two categories helps avoid unnecessary schema edits or over-granting privileges to mask configuration errors.

The diagnostic flow should start by verifying the server, account, default database, and actual SQL statement. Next, check for the existence of the database/table/column using metadata that the current account is permitted to view, and only then inspect grants. An error can stem from the wrong environment, case sensitivity differences, missing migrations, incorrect aliases, or privileges restricted at the database, table, or column level.

This lesson belongs to the **Troubleshooting** chapter of the `DATABASE_MYSQL` module. The module covers table design, data types, keys, SQL queries, indexes, transactions, concurrency control, query optimization, authorization, backup, and relational database operations. Examples focus on MySQL 8.0, InnoDB, and least-privilege application accounts.

After this lesson, you will be able to:

- Distinguish missing database/table/column errors from insufficient privilege errors.
- Read MySQL error codes, `SQLState`, and error context.
- Confirm the current database, server, and actual account matched by MySQL.
- Check object names, metadata, case sensitivity, and SQL syntax.
- Detect unapplied migrations or applications connecting to the wrong environment.
- Read grants and identify missing privileges at the database, table, or column level.
- Fix issues following the principle of least privilege and re-verify using the application account.
- Avoid workarounds that leak data or grant excessive privileges.

## 1. Identifying the Two Error Categories

When MySQL reports an error, do not read only the message text. Record at minimum:

- MySQL error code (vendor error code).
- `SQLState`.
- Executed SQL statement, after scrubbing sensitive data.
- Default database and host/server used by the connection.
- Authenticated MySQL account and the account MySQL uses for privilege checks.
- Timestamp, application version, and deployed schema version.

Common identifier/object errors:

| Error Code | Common SQLState | Message | Primary Meaning |
|---|---|---|---|
| 1046 | 3D000 | No database selected | The connection has no default database selected and the SQL statement does not qualify the schema. |
| 1049 | 42000 | Unknown database | The requested database name does not exist or is not recognized on that server. |
| 1054 | 42S22 | Unknown column | The referenced column does not exist in the SQL statement's context. |
| 1146 | 42S02 | Table doesn't exist | The referenced table or view does not exist in the resolved schema. |

Common privilege errors:

| Error Code | Common SQLState | Message | Primary Meaning |
|---|---|---|---|
| 1044 | 42000 | Access denied for user to database | The account lacks privilege to access the requested database. |
| 1045 | 28000 | Access denied for user | Authentication failed or account/host/password/plugin mismatch. |
| 1142 | 42000 | Command denied to user for table | Missing privilege to execute the command on the table. |
| 1143 | 42000 | Command denied to user for column | Missing privilege to execute the command on a specific column. |
| 1227 | 42000 | Access denied; need privilege | The operation requires an administrative or specific privilege. |

The error codes and `SQLState` values above are common MySQL cases. Errors may be wrapped inside JDBC, ORM, or framework exceptions; always inspect the exception cause chain and underlying vendor error instead of reading only the outermost message.

**Initial rule of thumb:** `Unknown ...` usually points to object names, schemas, query context, or schema versions; `Access denied`/`command denied` points to authentication or privileges. Even so, never conclude from a single message string alone. Confirm the server, account, and metadata.

## 2. Start by Confirming the Server and Session

One easily overlooked cause is that the application is connecting to the wrong MySQL instance or wrong database. For instance, migrations ran on staging while the application still points to a different development server, or a new pod's environment variables were not updated.

Run a diagnostic query on the failing connection itself:

~~~sql
SELECT
  VERSION() AS mysql_version,
  @@hostname AS server_hostname,
  @@port AS server_port,
  @@server_uuid AS server_uuid,
  DATABASE() AS current_database,
  USER() AS login_identity,
  CURRENT_USER() AS privilege_identity;
~~~

Meaning:

- `VERSION()` shows the MySQL Server version.
- `@@hostname`, `@@port`, and `@@server_uuid` identify the exact server.
- `DATABASE()` returns the current default database; `NULL` means the session has not selected a database.
- `USER()` shows the user and host the client connected with.
- `CURRENT_USER()` shows the MySQL account selected for privilege checking.

`USER()` and `CURRENT_USER()` can differ. MySQL selects an account using user/host matching rules; when checking grants, `CURRENT_USER()` is the authoritative identity. Two accounts with the same username but different hosts can have different privileges.

In JDBC, you can also check:

~~~java
try (Connection connection = dataSource.getConnection()) {
    System.out.println("Catalog: " + connection.getCatalog());
    System.out.println("Schema: " + connection.getSchema());
    System.out.println("Auto commit: " + connection.getAutoCommit());
}
~~~

Do not print passwords or the full JDBC URL if the URL contains secrets. When comparing environments, log hostname, port, database, and a non-sensitive configuration identifier.

## 3. Error: No database selected (1046)

Error 1046 occurs when an SQL statement uses an unqualified table name while the connection has no default database selected.

Example:

~~~sql
SELECT * FROM orders;
~~~

If the session has not executed `USE sales`, the server does not know which database contains `orders`.

Check:

~~~sql
SELECT DATABASE();
~~~

If the result is `NULL`, you can select a database:

~~~sql
USE sales;
SELECT * FROM orders;
~~~

Or explicitly qualify the schema in the SQL statement:

~~~sql
SELECT * FROM sales.orders;
~~~

Qualifying the schema explicitly is helpful for multi-database applications, background jobs, or connection pools. It reduces reliance on the session's default database. However, the schema name must match the environment and the account must have access privileges.

With JDBC, the database is usually specified in the JDBC URL:

~~~text
jdbc:mysql://mysql.example.internal:3306/sales
~~~

If the URL omits the database or the pool alters the catalog after creating the connection, unqualified SQL statements can trigger 1046. Check `Connection.getCatalog()` and the `DataSource` configuration.

## 4. Error: Unknown database (1049)

Example:

~~~sql
USE sales_prod;
~~~

If the server returns `Unknown database 'sales_prod'`, verify:

1. Is the database name spelled accurately?
2. Is the connection pointing to the right server?
3. Has the database been created in this environment?
4. Did deployment/migrations succeed?
5. Does the database name differ in uppercase/lowercase on the target operating system?
6. Does the account and metadata check have sufficient privileges to see the database?

Check the list of databases visible to the current account:

~~~sql
SHOW DATABASES;
~~~

You can query metadata:

~~~sql
SELECT SCHEMA_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = 'sales_prod';
~~~

Not seeing a database in `SHOW DATABASES` does not always prove the database does not exist. MySQL filters metadata visibility based on account privileges. If missing privileges are suspected, ask a DBA to verify schema existence using an administrative account and compare against the application's `CURRENT_USER()`.

Distinguish:

- `1049`: the server does not recognize the specified database.
- `1044`: the requested database exists/is referenced, but the account is not allowed to access it.
- `1045`: authentication failed for the account/host or credentials.

Do not immediately create a new database upon seeing 1049. If the application is pointing to the wrong server or using a typo, creating a matching schema in the wrong place will complicate the incident.

## 5. Error: Table doesn't exist (1146)

Example:

~~~sql
SELECT order_id, status
FROM sales.orders;
~~~

If `sales.orders` does not exist, MySQL can return error 1146. Common causes:

- Wrong database or table name.
- Table has not been created by migrations yet.
- Application connected to the wrong environment or wrong replica.
- Migration partially failed or has not been deployed.
- Table was renamed or dropped in a release.
- Table is a temporary table accessed outside the session that created it.
- Case sensitivity differences between source and target operating systems.

Check table names:

~~~sql
SHOW FULL TABLES FROM sales;
~~~

Or query metadata:

~~~sql
SELECT
  TABLE_SCHEMA,
  TABLE_NAME,
  TABLE_TYPE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'orders';
~~~

`TABLE_TYPE` distinguishes `BASE TABLE` from `VIEW`. A view may be missing or invalid due to dependencies, and object errors should be investigated via DDL and view dependencies.

If the table does not appear, confirm the account has privileges to view its metadata. `information_schema` only exposes metadata the account is allowed to see; an empty result does not always distinguish a nonexistent object from restricted metadata visibility.

### 5.1. Temporary Tables and Session Scope

A temporary table exists only within the session that created it:

~~~sql
CREATE TEMPORARY TABLE tmp_order_ids (
  order_id BIGINT PRIMARY KEY
);
~~~

If you create a temporary table on one connection and query it on another connection from the pool, the second connection will not see that table and may report 1146.

This commonly happens when code acquires two separate connections for two steps, or returns a connection to the pool between creating and using the temporary table.

Hold the same `Connection` across the entire lifecycle of the temporary table:

~~~java
try (Connection connection = dataSource.getConnection()) {
    // Create temporary table.
    // Populate data.
    // Query temporary table.
    // Close connection after completion.
}
~~~

Do not store a temporary table name in a global variable assuming every connection can see it.

## 6. Case Sensitivity of Databases and Tables

Database and table names may be case-sensitive depending on the operating system and the `lower_case_table_names` setting.

Check:

~~~sql
SHOW VARIABLES LIKE 'lower_case_table_names';
~~~

Common values:

| Value | General Behavior |
|---|---|
| 0 | Stores names as declared and compares case-sensitively; common on Unix/Linux with case-sensitive filesystems. |
| 1 | Stores names in lowercase and compares case-insensitively; common on Windows. |
| 2 | Stores names as declared but compares in lowercase; can appear on case-insensitive filesystems where supported by the platform. |

Exact behavior depends on platform and version. In MySQL 8.0, `lower_case_table_names` must be decided when initializing the data directory; never arbitrarily alter it on an existing server with data to fix naming errors. Changing this configuration may be unsupported or cause object name mismatches.

Recommendations:

- Use one consistent naming convention for databases and tables, typically lowercase.
- Keep object casing identical across DDL, migrations, and application code.
- Check source and target configurations before migrating environments.
- Test migrations on the same OS/filesystem type as production.
- Never create two tables differing only by letter case expecting identical behavior across all platforms.

Column and index names do not follow the exact same filesystem rules as database and table names; nevertheless, always use exact declared names to avoid typos or mismatches in generated SQL.

## 7. Error: Unknown column (1054)

Example:

~~~sql
SELECT order_id, customer_nmae
FROM sales.orders;
~~~

If the table has `customer_name` rather than `customer_nmae`, MySQL returns `Unknown column ... in field list`.

Inspect table structure:

~~~sql
SHOW COLUMNS FROM sales.orders;
~~~

Or:

~~~sql
SHOW CREATE TABLE sales.orders;
~~~

You can query column metadata:

~~~sql
SELECT
  COLUMN_NAME,
  DATA_TYPE,
  IS_NULLABLE,
  COLUMN_DEFAULT,
  ORDINAL_POSITION
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
~~~

Cross-check column names against the actual DDL. Do not rely solely on DTO field names, entities, or outdated documentation.

### 7.1. Aliases Cannot Be Used Everywhere

A frequent 1054 error is referencing a select-list alias inside a `WHERE` clause:

~~~sql
SELECT
  total_amount * 1.1 AS amount_with_tax
FROM sales.orders
WHERE amount_with_tax > 100;
~~~

In MySQL, a select-list alias cannot be referenced in the same-level `WHERE` clause in this way because `WHERE` is evaluated before the select expression defines the alias.

Rewrite the expression:

~~~sql
SELECT
  total_amount * 1.1 AS amount_with_tax
FROM sales.orders
WHERE total_amount * 1.1 > 100;
~~~

Or use a derived table:

~~~sql
SELECT amount_with_tax
FROM (
  SELECT total_amount * 1.1 AS amount_with_tax
  FROM sales.orders
) AS calculated
WHERE amount_with_tax > 100;
~~~

Aliases can be used in certain other clauses such as `ORDER BY`, `GROUP BY`, and `HAVING` according to MySQL rules. In complex queries, check the exact scope of aliases and column names.

### 7.2. Duplicate Column Names or Missing Qualifiers

When joining multiple tables, qualify columns to avoid ambiguity:

~~~sql
SELECT
  o.order_id,
  c.customer_name
FROM sales.orders AS o
JOIN sales.customers AS c
  ON c.customer_id = o.customer_id;
~~~

If you reference `customer_name` when the column lives in a different table or the table alias is wrong, MySQL may report unknown column. Check the aliases declared in `FROM` and `JOIN`, not just the column name.

Incorrect example:

~~~sql
SELECT o.order_id
FROM sales.orders AS o
WHERE orders.status = 'PAID';
~~~

Once alias `o` is declared, use that alias:

~~~sql
SELECT o.order_id
FROM sales.orders AS o
WHERE o.status = 'PAID';
~~~

### 7.3. Identifiers vs. String Literals

MySQL uses single quotes for string literals and backticks to quote identifiers:

~~~sql
SELECT `order_id`, `status`
FROM `sales`.`orders`
WHERE `status` = 'PAID';
~~~

Do not write:

~~~sql
SELECT 'order_id'
FROM sales.orders;
~~~

`'order_id'` is a string literal, not a column name. Depending on the query, it returns a constant string instead of column data.

Double quotes are normally used for strings; if `ANSI_QUOTES` is enabled, double quotes are interpreted as identifiers. To keep SQL unambiguous and less dependent on SQL mode, use backticks for quoted identifiers and single quotes for string literals.

## 8. Name Errors Due to Missing or Out-of-Sync Migrations

An application may be deployed with code querying a new column before the database has been migrated.

For example, new code runs:

~~~sql
SELECT order_id, fulfillment_status
FROM sales.orders;
~~~

While the target schema still only has the `status` column. The result is 1054. This is a code/schema version mismatch, not missing privileges.

Verification procedure:

1. Confirm server and database using `@@server_uuid`, `@@hostname`, and `DATABASE()`.
2. Check `SHOW CREATE TABLE sales.orders`.
3. Determine whether the migration adding `fulfillment_status` ran on the target database.
4. Check migration logs/status from your project's deployment tool.
5. Check whether application and migration releases were sequenced properly.
6. Check replicas if read queries are routed to a replica that has not yet applied the DDL.

Do not fix this by manually adding the column in production if the official migration status is still unclear. Manual edits can cause subsequent migrations to fail because the object already exists or introduce schema drift across environments.

### 8.1. Safe Schema Evolution

For schema changes that must support multiple concurrent application versions:

- Add the new column in a backward-compatible state first.
- Deploy code capable of working with both old and new structures.
- Run backfill if needed.
- Switch reads/writes to the new column.
- Drop the old column only after no running application version depends on it.

This sequence minimizes unknown column errors during rolling deployments. Never deploy code depending on a new column before the corresponding DDL is ready across all database endpoints the code can reach.

## 9. Distinguishing Name Errors from Missing Privilege Errors

This is the most critical distinction during diagnosis. Compare message, error code, operation, and account:

| Operation | Common Name/Object Error | Common Privilege Error |
|---|---|---|
| `USE sales` | 1049 Unknown database | 1044 Access denied to database |
| `SELECT ... FROM sales.orders` | 1146 Table doesn't exist | 1142 SELECT command denied for table |
| `SELECT secret_col FROM sales.orders` | 1054 Unknown column | 1143 SELECT command denied for column |
| `UPDATE sales.orders ...` | 1146 if table does not exist | 1142 UPDATE command denied for table or 1143 at column level |
| `CREATE TABLE sales.t ...` | Name/schema or syntax error depending on context | 1044/1142/1227 depending on required privilege |

Privilege errors typically name the denied command and object. For example:

~~~text
ERROR 1142 (42000): SELECT command denied to user 'app'@'10.%' for table 'orders'
~~~

This indicates MySQL recognized the target object, but the current account lacks the `SELECT` privilege for the required scope.

A column-level error looks like:

~~~text
ERROR 1143 (42000): SELECT command denied to user 'app'@'10.%' for column 'salary' in table 'employees'
~~~

In this case, the account may be allowed to read certain columns while restricted from sensitive columns.

Do not deliberately infer object existence solely from error messages across every security configuration. Verify with a DBA or properly privileged account while preserving the rule not to grant extra privileges to the application account just for troubleshooting.

## 10. Identifying the Actual Applied MySQL Account

A MySQL account has the form `'user'@'host'`. Two accounts with the same username but different hosts are distinct accounts and can hold different grants.

Check:

~~~sql
SELECT
  USER() AS client_identity,
  CURRENT_USER() AS matched_account;
~~~

For instance, a client connects from `10.20.1.15` with username `app`, while MySQL might match `'app'@'10.%'`, `'app'@'%'`, or a more specific host account. Privileges must be checked on the matched account.

View current grants:

~~~sql
SHOW GRANTS;
~~~

Or:

~~~sql
SHOW GRANTS FOR CURRENT_USER();
~~~

If roles are used, check active roles:

~~~sql
SELECT CURRENT_ROLE();
~~~

A role granted to an account is not necessarily active in the session if default roles or `SET ROLE` statements differ from expectations. Therefore, compare both grants and active roles.

Never ask operators to send passwords, password hashes, or secret files for diagnostics. You only need account identity, host, sanitized grants, and error codes.

## 11. Understanding MySQL Privilege Scopes

MySQL supports privileges at multiple scopes:

| Scope | Example | Meaning |
|---|---|---|
| Global | `ON *.*` | Applies server-wide across objects covered by that privilege. |
| Database | `ON sales.*` | Applies to objects inside the `sales` database. |
| Table | `ON sales.orders` | Applies to a specific table. |
| Column | `ON sales.employees (salary)` | Applies to a specific column for privileges supporting column scope. |
| Routine | `ON PROCEDURE sales.recalculate` | Privileges such as `EXECUTE`/`ALTER ROUTINE` on supported routines. |
| Dynamic privilege | Specific administrative privileges | Scope and names depend on the MySQL version. |

Example account allowed only to read the `sales` database:

~~~sql
GRANT SELECT
ON sales.*
TO 'sales_reader'@'10.%';
~~~

Example allowing reads on a single table:

~~~sql
GRANT SELECT
ON sales.orders
TO 'order_reader'@'10.%';
~~~

Example granting read access to specific columns:

~~~sql
GRANT SELECT (employee_id, display_name)
ON hr.employees
TO 'directory_reader'@'10.%';
~~~

Syntax and privileges may require adjustment based on object type, version, and actual account. `GRANT` statements must be executed by a DBA or an account with appropriate administrative privileges.

Do not grant `ALL PRIVILEGES ON *.*` to fix errors 1142/1143. Identify the exact operation, database/table/column, and grant only the minimum required privileges.

## 12. Reading SHOW GRANTS and Finding Missing Privileges

Example output:

~~~sql
SHOW GRANTS FOR 'sales_app'@'10.%';
~~~

Might show:

~~~sql
GRANT USAGE ON *.* TO `sales_app`@`10.%`;
GRANT SELECT, INSERT, UPDATE ON `sales`.* TO `sales_app`@`10.%`;
~~~

The account above can read, insert, and update objects in the `sales` database, but cannot `DELETE` unless granted. If the application runs `DELETE FROM sales.orders`, a privilege error is expected.

Map privileges by operation:

- `SELECT`: read data.
- `INSERT`: insert rows.
- `UPDATE`: modify data; column-level privileges can restrict which columns may be updated.
- `DELETE`: delete rows.
- `CREATE`/`ALTER`/`DROP`: alter database/table structure.
- `INDEX`: create or drop indexes.
- `REFERENCES`: create foreign key references where this privilege is required.
- `EXECUTE`: invoke stored procedures/functions.
- `TRIGGER`: create or drop triggers.

A single statement can require multiple privileges. For example, `INSERT ... ON DUPLICATE KEY UPDATE` requires appropriate `INSERT` and `UPDATE` privileges. `CREATE TABLE ... SELECT` can require table creation privileges and read access to the source data.

Check privileges against the actual SQL executed rather than inferring from UI feature names.

## 13. Fixing Privilege Errors with Least Privilege

Privilege granting workflow:

1. Identify the account via `CURRENT_USER()`.
2. Identify the denied operation and exact object.
3. Determine the narrowest possible privilege scope.
4. Confirm the host pattern matches the application.
5. Have a DBA grant privileges on the exact database/table/column.
6. Open a new connection or refresh roles/sessions if needed.
7. Re-test using the application account itself.
8. Document the rationale and scope of granted privileges.

For example, if a service needs `SELECT` and `UPDATE` on `sales.orders`:

~~~sql
GRANT SELECT, UPDATE
ON sales.orders
TO 'sales_app'@'10.%';
~~~

If the service also needs `INSERT` for new orders:

~~~sql
GRANT INSERT
ON sales.orders
TO 'sales_app'@'10.%';
~~~

Do not grant `CREATE`, `ALTER`, or `DROP` to the runtime account merely because the application has a migration flow. Use a dedicated migration account granted DDL privileges only within deployment windows and managed as a privileged secret.

### 13.1. Column-Level Privileges

Suppose an account is allowed to read `employee_id` and `display_name`, but not `salary`. Query:

~~~sql
SELECT employee_id, salary
FROM hr.employees;
~~~

can return 1143 due to missing `SELECT` on column `salary`. Do not grant `SELECT` on the whole table if the business feature only needs certain columns. Adjust the query to select only allowed columns, or request the DBA to grant the exact privilege if justified by business requirements and security approval.

Similarly, `UPDATE` on sensitive columns should be restricted. Table-level privileges are broader than column-level privileges; understand existing grants before proposing changes.

## 14. Distinguishing Authentication Error 1045

Error 1045 typically occurs before the application executes any SQL. Example:

~~~text
ERROR 1045 (28000): Access denied for user 'sales_app'@'10.20.1.15' (using password: YES)
~~~

Possible causes:

- Wrong password, or secret was rotated without the application picking up the new value.
- Account does not exist with a matching host pattern.
- Incompatible or unconfigured authentication plugin.
- Account is locked or authentication policy prevents login.
- Connected to the wrong server with different accounts.
- TLS or additional authentication requirements unmet.

Check account and plugin using a DBA account:

~~~sql
SELECT
  user,
  host,
  plugin,
  account_locked,
  password_expired
FROM mysql.user
WHERE user = 'sales_app';
~~~

`mysql.user` contains sensitive administrative data; only authorized accounts should access it. Never require the runtime application to query this table. Ask a DBA to verify account status and share sanitized findings.

1045 differs from 1044: 1045 is an account connection/authentication failure; 1044 means the account authenticated successfully but lacks privilege to access the database requested in the operation.

## 15. Step-by-Step Diagnostic Procedure

When receiving an `Unknown database/table/column` or `Access denied` ticket, follow this sequence:

### Step 1: Collect the Raw Error

Record error code, `SQLState`, exception class, operation, and referenced object. In Java applications, inspect the `SQLException.getNextException()` chain and ORM exception causes.

### Step 2: Confirm the Endpoint

Run the query:

~~~sql
SELECT
  @@hostname,
  @@port,
  @@server_uuid,
  VERSION(),
  DATABASE(),
  USER(),
  CURRENT_USER();
~~~

Compare the endpoint with the environment configuration the application is supposed to use.

### Step 3: Verify Object Names

- For databases: `SHOW DATABASES` or `information_schema.SCHEMATA`.
- For tables: `SHOW FULL TABLES FROM db_name`.
- For columns: `SHOW COLUMNS FROM db_name.table_name` or `information_schema.COLUMNS`.
- For full DDL: `SHOW CREATE TABLE db_name.table_name`.

Remember metadata visibility can be restricted by account grants.

### Step 4: Verify SQL Statement and Scope

Check schema qualifiers, table aliases, column aliases, identifier quoting, typos, and migration ordering. If SQL is ORM-generated, enable safe SQL logging in an appropriate environment and inspect bind parameters without exposing sensitive data.

### Step 5: Verify Grants

Use `CURRENT_USER()`, `SHOW GRANTS`, and `CURRENT_ROLE()`. Compare privileges required by the statement against actual privileges.

### Step 6: Fix the Exact Cause

- Wrong server/database: fix endpoint or catalog configuration.
- Wrong object name: fix SQL or migration per design.
- Missing migration: deploy migration via the proper process.
- Missing privileges: ask DBA to grant least-privilege permissions.
- Wrong host account/authentication: fix account mapping or secret per administrative procedures.

### Step 7: Test with the Application Account

Re-run the exact failing operation in the target environment and account. Verify both required read and write paths rather than using a DBA account just to prove the query runs.

## 16. Java/JDBC: Extracting Useful Error Details

Example `SQLException` handling:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(
             "SELECT order_id FROM sales.orders WHERE order_id = ?")) {

    statement.setLong(1, orderId);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("order_id");
        }
    }

} catch (SQLException e) {
    logger.error(
        "Database operation failed: sqlState={}, vendorCode={}, type={}",
        e.getSQLState(),
        e.getErrorCode(),
        e.getClass().getSimpleName()
    );

    for (SQLException next = e.getNextException();
         next != null;
         next = next.getNextException()) {
        logger.error(
            "Additional database error: sqlState={}, vendorCode={}",
            next.getSQLState(),
            next.getErrorCode()
        );
    }

    throw e;
}
~~~

In production logs, never record passwords, tokens, personal data, or full bind values. If a query must be reproduced, log the SQL template and request/correlation ID, then retrieve sanitized test data.

With Spring JDBC/JPA, exceptions may be translated into `DataAccessException`. Inspect the root cause and `SQLState`/vendor code to distinguish `BadSqlGrammarException`, `DataIntegrityViolationException`, privilege errors, or connection errors. Do not collapse every error into a generic message like "database unavailable".

## 17. ORMs and Column Name Errors

Hibernate/JPA can generate SQL based on entity mappings. If the mapping does not match DDL, MySQL can report 1054 even though the Java code compiles cleanly.

Example:

~~~java
@Entity
@Table(name = "orders", schema = "sales")
public class Order {
    @Id
    private Long id;

    @Column(name = "fulfillment_status")
    private String fulfillmentStatus;
}
~~~

If the actual table only has column `status`, this mapping generates a query referencing `fulfillment_status` and hits unknown column.

Check:

- `@Table(schema = ..., name = ...)`.
- `@Column(name = ...)`.
- Naming strategy converting `camelCase` to `snake_case`.
- Default schema and JDBC URL.
- Actual DDL from `SHOW CREATE TABLE`.
- Whether migrations have been applied to the right database.
- Whether native queries use exact physical column names.

Do not alter DDL just to make an entity mapping work if the database's canonical column name is already correct per contract. Pick one source of truth for schema and mapping; prevent migrations, ORM naming strategies, and native SQL from drifting apart.

## 18. Metadata Privileges and Object Visibility

`SHOW DATABASES`, `SHOW TABLES`, and `information_schema` queries may show only objects the account is permitted to view. Therefore:

- An empty result does not always prove an object does not exist.
- `SHOW CREATE TABLE` may require appropriate privileges.
- An account with column-level `SELECT` may see only partial data.
- Runtime accounts should not be granted administrative privileges just to assist diagnostics.

When an object's existence must be confirmed, use a DBA account or approved inspection process, keeping the action read-only. Then compare results with the application account to determine whether the issue is naming or privileges.

Do not attempt to access sensitive data via another account to bypass configured restrictions. The goal is to identify the missing privilege, then decide whether to grant legitimate access or adjust the query so it does not touch out-of-scope objects/columns.

## 19. Common Anti-Patterns

| Incorrect Approach | Risk | Proper Approach |
|---|---|---|
| Seeing 1049 and immediately creating a new database | Creating the wrong schema on the wrong server or masking an endpoint error | Verify server UUID, database, and migrations first. |
| Seeing 1146 and manually running `CREATE TABLE` | Schema drift, subsequent migration failures | Check DDL, release state, and migration status. |
| Seeing 1054 and adding a column to match code | May create incorrect structure or semantics | Cross-check entity, query, and approved DDL. |
| Seeing 1142 and granting `ALL PRIVILEGES` | Over-privileging the runtime account | Grant only required `SELECT`/`INSERT`/`UPDATE`/`DELETE` on the specific object. |
| Using `USER()` to check grants | Checking the wrong host account | Use `CURRENT_USER()` and `SHOW GRANTS`. |
| Using a DBA account to test the app | Broad DBA privileges mask runtime permission issues | Test with the actual application account. |
| Concluding a table does not exist from an empty `SHOW TABLES` | Metadata may be hidden by privileges | Verify with an authorized account and check grants. |
| Changing `lower_case_table_names` on a live server | May be unsupported or corrupt data directory alignment | Standardize naming and migrations; never toggle config arbitrarily. |
| Concatenating table names from user input | SQL injection or querying the wrong object | Whitelist identifiers; bind parameters for values. |
| Logging full SQL and credentials | Secret or sensitive data leakage | Log error code, SQL template, endpoint, and correlation ID. |

## 20. Practice Exercises

### Exercise 1: Distinguish 1046 and 1049

Open a connection without selecting a database, run `SELECT * FROM orders`, and observe the error. Then run `USE nonexistent_database` to observe the different error. Explain the difference between no database selected and a nonexistent database.

### Exercise 2: Distinguish 1146 and 1142

Create a test table `sales.orders`. Use an account with `SELECT` privilege and then revoke `SELECT` in a lab environment. Compare the error when the table does not exist with the error when the account lacks table read privilege. Restore grants after the exercise.

### Exercise 3: Reproduce 1054

Run a query with a misspelled column name, then inspect `SHOW COLUMNS` and `SHOW CREATE TABLE`. Try adding an alias in `SELECT` and referencing it in `WHERE`; explain why the alias is not yet in scope inside `WHERE`.

### Exercise 4: Inspect Account Mapping

Connect using accounts with the same username but different host patterns. Run `USER()`, `CURRENT_USER()`, and `SHOW GRANTS`. Identify which account MySQL actually used for privilege checking.

### Exercise 5: Simulate Out-of-Sync Schema Migration

Create a table at an older schema version, run a query referencing a new column, and observe 1054. Apply the migration to the target database and re-run with the application account. Document how to verify the migration ran on the right endpoint.

### Exercise 6: Grant Least Privilege

Create an account allowed to read only one table or a subset of columns. Test `SELECT`, `UPDATE`, and accessing restricted columns. Grant the exact required privilege, re-run tests, and confirm no server-wide privileges were granted.

## 21. Troubleshooting Checklist

- [ ] Recorded MySQL error code, `SQLState`, and root exception.
- [ ] Confirmed `@@hostname`, `@@server_uuid`, port, and version.
- [ ] Checked `DATABASE()` and the JDBC connection's default database.
- [ ] Checked `USER()` and `CURRENT_USER()`.
- [ ] Verified database/table/column via appropriate metadata.
- [ ] Checked schema qualifiers, aliases, typos, and identifier quoting.
- [ ] Checked `lower_case_table_names` when errors happen on only one platform.
- [ ] Verified migrations and schema version on the right server.
- [ ] Read grants and active roles of the matched account.
- [ ] Distinguished database access, table privilege, and column privilege errors.
- [ ] Proposed least-privilege grants at the narrowest scope if privileges are genuinely missing.
- [ ] Re-tested using the application account, not just a DBA account.
- [ ] Avoided logging secrets or sensitive data.
- [ ] Documented root cause and recurrence prevention.

`Unknown database`, `Table doesn't exist`, and `Unknown column` generally require checking names, session context, schemas, and migrations. `Access denied` and `command denied` errors require checking the account matched by MySQL and grants at the exact scope. By confirming the endpoint first, inspecting metadata second, and comparing privileges with `CURRENT_USER()` and `SHOW GRANTS`, you can pinpoint the real cause and fix it with minimal changes. Always test with the real application account to verify the error is resolved without expanding privileges unnecessarily.
