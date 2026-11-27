# Applying Least Privilege to Database Accounts

In Spring Data Relational R2DBC, the application connects to the database using one or more accounts configured in `ConnectionFactory`. Those accounts determine whether the application can read, insert, update, delete data, call stored procedures, create objects, or alter schemas.

The principle of **least privilege** requires each account to hold only the permissions needed to perform its exact job. The account running the application should not have database administration rights or schema-modification rights if runtime operations do not require them. Migration accounts, reporting read accounts, and background processing accounts should each have their own scoped privileges.

This limits damage when credentials leak, SQL injection occurs, a query is miswritten, or a service is compromised. If the runtime account only has `SELECT`/`INSERT`/`UPDATE` on a specific schema, an attacker cannot use that same credential to create new users, drop other databases, or read tables outside the service's scope.

Spring Data R2DBC does not grant database permissions on its own. Repositories, `DatabaseClient`, `R2dbcEntityTemplate`, and transaction managers all execute under the database principal attached to the connection. Privileges must be designed and granted in the database, then verified using the exact account the application uses.

## 1. What Is Least Privilege?

Least privilege is the principle of granting only the required permissions, within the exact scope and timeframe needed.

For example, a service that only reads a product catalog might only need:

- Connection access to the products database.
- `SELECT` privilege on specific tables or views it needs to read.
- No `INSERT`, `UPDATE`, or `DELETE` privileges.
- No privileges to create tables, indexes, schemas, or users.
- No access to customer or billing databases.

An order-creation service might additionally need `INSERT`/`UPDATE` on order tables and `SELECT` on product tables to validate details. It still does not need `DROP TABLE`, `ALTER ROLE`, `CREATE DATABASE`, or system-wide administrative rights.

Least privilege is more than "not using an admin account." It also includes:

1. Restricting to the exact database and schema.
2. Restricting to the exact tables, views, sequences, and procedures.
3. Restricting to exact operations: `SELECT`, `INSERT`, `UPDATE`, `DELETE`, or `EXECUTE`.
4. Restricting columns where the database supports it and business rules warrant it.
5. Separating runtime privileges from migration and operational privileges.
6. Revoking privileges or credentials when no longer needed.

## 2. Why Shouldn't the Runtime Account Be an Administrative Account?

Suppose the application uses an account with database-wide administrative rights. A bug in an endpoint or a SQL injection flaw could escalate into:

- Reading all sensitive tables.
- Modifying or deleting data outside the service's domain.
- Creating users or granting privileges to other accounts.
- Altering schemas, triggers, or stored procedures.
- Dropping tables, indexes, or databases.
- Disabling data protection mechanisms depending on granted rights.

If the account only has permissions on the service's schema, the blast radius is significantly smaller.

| Scenario | Over-privileged account | Least-privilege account |
|---|---|---|
| SQL injection in order-read API | Can read many databases/tables | Can only read granted objects |
| Buggy endpoint executes DELETE | Can wipe large amounts of data | DELETE is denied if not granted |
| Runtime credential leaks | Attacker gains admin rights | Attacker is constrained to runtime rights |
| Application needs deployment | Runtime can self-modify schema | Uses migration pipeline with separate credentials |
| Service only needs SELECT | Can still write/delete under admin account | Database rejects write operations |

Least privilege does not replace authentication, application authorization, encryption, or SQL injection prevention. It is an additional defense layer at the database itself.

## 3. Distinguishing Database Accounts from Application Users

A database account typically represents the process or service opening connections, such as `orders_runtime`. It does not necessarily represent the logged-in end user.

For example:

~~~text
Alice ─┐
Bob   ─┼──> Orders API ──> ConnectionFactory ──> orders_runtime
Carol ─┘
~~~

The database may see every SQL query arriving from `orders_runtime`, whether the request came from Alice, Bob, or Carol.

Therefore:

- The database account defines what operations the service is allowed to perform.
- Application authorization defines which business actions an end user is allowed to perform.
- Row-level security (if used) can add database-level constraints by tenant or actor context.
- Do not put individual end-user usernames/passwords into connection pools as a substitute for application authorization.

If actor auditing is required, propagate actor details through reactive context and record them via auditing or audit logs. Do not confuse the actor in an `updated_by` column with the database login executing the SQL statement.

## 4. Separating Accounts by Workload

A system may use multiple accounts:

| Account/role | Workload | Typical permissions needed |
|---|---|---|
| orders_runtime | Handling order requests | SELECT/INSERT/UPDATE on required objects |
| orders_readonly | Reporting or read-only queries | SELECT on permitted views/tables |
| orders_migration | Running schema migrations | CREATE/ALTER/DROP within owned schema |
| orders_worker | Background queue processing | SELECT/UPDATE state and INSERT results |
| orders_backup | Scheduled backups | Database-appropriate backup privileges |
| DBA/operator | System administration | Separately controlled administrative rights |

Not every application needs all of these accounts. Create only identities that actually represent distinct workloads.

### Separating roles and logins

Many database engines support roles/groups to bundle privileges, which are then assigned to logins/users. This lets you:

- Define permissions once.
- Create separate credentials per environment or instance.
- Revoke a single login without rewriting every `GRANT`.
- Avoid scattering ad-hoc direct grants across individual accounts.

Conceptual example:

~~~text
orders_runtime_login ──┐
                      ├──> role_orders_runtime
orders_worker_login ──┘

orders_report_login ─────> role_orders_readonly

orders_migration_login ──> role_orders_migration
~~~

Combine two logins into the same role only when they truly need the exact same set of permissions. A worker may need `UPDATE` on a queue status while a read API does not.

## 5. Building a Permission Matrix Before Granting

Before writing SQL `GRANT` statements, list the operations each workload performs:

| Object | Runtime API | Read-only | Worker | Migration |
|---|---:|---:|---:|---:|
| orders | SELECT, INSERT, UPDATE | SELECT | SELECT, UPDATE | ALTER |
| order_line | SELECT, INSERT | SELECT | SELECT, INSERT | ALTER |
| customer_view | SELECT | SELECT | Not needed | Create/alter view |
| outbox_event | INSERT, SELECT | Not needed | SELECT, UPDATE | ALTER |
| ID sequence | USAGE/NEXT VALUE | Not needed | USAGE/NEXT VALUE | Administration |
| Schema | USAGE | USAGE | USAGE | CREATE/ALTER as needed |

This is an illustrative matrix. Never grant permissions just because they "might be needed later." If the application does not currently `DELETE`, start by not granting `DELETE`.

### Identifying permissions per operation

- `SELECT`: read data.
- `INSERT`: add rows.
- `UPDATE`: modify rows or permitted columns.
- `DELETE`: remove rows.
- `EXECUTE`: invoke procedures/functions.
- `USAGE`/`REFERENCES`: specific permissions such as using sequences or referencing objects, depending on the database.
- `CREATE`/`ALTER`/`DROP`: modify schemas or objects.
- `CONNECT`/`CREATE SESSION`: log in/connect to the database.

Permission names and `GRANT` scopes are not identical across all database engines.

## 6. Never Use Schema Owner Privileges for Runtime

A schema owner or object owner usually has the ability to alter objects it owns. That is needed for migrations and administration, but is too broad for request-handling processes.

A safer model:

- `orders_owner`: non-login role owning schemas and objects.
- `orders_migration`: login allowed to run migrations within the schema scope.
- `orders_runtime`: login granted only needed DML privileges.
- `orders_readonly`: login granted only `SELECT`.

Runtime should not own tables if the database allows separating ownership from table usage rights. When runtime owns a table, merely revoking `SELECT`/`UPDATE` is often insufficient to stop it from altering the object.

Migrations can create objects under the owner role or use a controlled deployment process to ensure new objects have the proper owner and default privileges.

## 7. PostgreSQL Example: Creating a Runtime Role

PostgreSQL distinguishes between login roles and group roles. You can create a non-login group role and grant it to the runtime login:

~~~sql
CREATE ROLE orders_runtime_role NOLOGIN;

GRANT CONNECT ON DATABASE orders_db
TO orders_runtime_role;

GRANT USAGE ON SCHEMA orders
TO orders_runtime_role;

GRANT SELECT, INSERT, UPDATE
ON ALL TABLES IN SCHEMA orders
TO orders_runtime_role;

GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA orders
TO orders_runtime_role;
~~~

Create a separate login:

~~~sql
CREATE ROLE orders_runtime
LOGIN
PASSWORD '<set-through-secure-secret-management>';

GRANT orders_runtime_role TO orders_runtime;
~~~

The password in the example is a placeholder. Never write real passwords into committed migrations, logs, documentation, or shell history. Provision credentials through a secret manager or secure provisioning pipeline.

### Why are both `CONNECT` and `USAGE` needed?

- `CONNECT` allows the role to connect to the database.
- `USAGE` on the schema allows referencing objects inside the schema.
- `SELECT`/`INSERT`/`UPDATE` on tables grant data manipulation privileges.
- `USAGE`/`SELECT` on sequences is often needed to obtain IDs from sequences.

Schema `USAGE` does not automatically grant table read rights. Conversely, table `SELECT` does not replace schema access rights.

### Sequences and generated IDs

For a table using a sequence:

~~~sql
INSERT INTO orders (customer_id, status)
VALUES (100, 'NEW');
~~~

If the ID default calls `nextval()` on a sequence, the writing role may need `USAGE` on that sequence. Grant privileges on the exact sequences rather than all sequences if a schema holds multiple sensitive data groups.

`SERIAL` and `IDENTITY` differ in how the database manages sequences and privileges. Verify privileges against the actual column type and `INSERT` statement.

## 8. PostgreSQL: Privileges for Future Objects

`GRANT` on `ALL TABLES IN SCHEMA` applies only to objects existing at execution time. New tables created by later migrations will not automatically inherit those privileges without default privileges.

Example:

~~~sql
ALTER DEFAULT PRIVILEGES
FOR ROLE orders_owner
IN SCHEMA orders
GRANT SELECT, INSERT, UPDATE ON TABLES
TO orders_runtime_role;

ALTER DEFAULT PRIVILEGES
FOR ROLE orders_owner
IN SCHEMA orders
GRANT USAGE, SELECT ON SEQUENCES
TO orders_runtime_role;
~~~

Default privileges apply to new objects created by the specified role within the target schema. If migrations run under a different role, configure default privileges for the exact role creating the objects.

Do not confuse default privileges with retroactively modifying permissions on existing tables. You still need grants for existing objects and should verify permissions after every migration.

## 9. PostgreSQL: Column-Level Privileges

If runtime may only update certain columns, PostgreSQL supports column-level privileges:

~~~sql
GRANT SELECT ON orders.customer
TO orders_runtime_role;

GRANT UPDATE (display_name, phone_number)
ON orders.customer
TO orders_runtime_role;
~~~

This example allows reading the table while restricting `UPDATE` to the two listed columns. Do not grant table-level `UPDATE` to the same role when restricting columns, because the broader privilege overrides the restriction.

Column-level privileges are useful when a table has sensitive columns such as `credit_limit`, `risk_score`, or `is_admin`. However, they do not replace business validation: the service must still verify whether the user is authorized to change a specific value.

## 10. PostgreSQL: Avoiding Unnecessary Admin and PUBLIC Privileges

Runtime should not have role attributes such as:

- `SUPERUSER`.
- `CREATEDB`.
- `CREATEROLE`.
- `REPLICATION`.
- `BYPASSRLS`.

Never grant membership in administrative roles just to fix a permission-denied error.

PostgreSQL has a `PUBLIC` role of which every role is a member. Certain default privileges may be granted to `PUBLIC` depending on the database/schema/object and version. Audit default privileges in your environment.

For example, you can revoke `CREATE` on schema `public` if the application does not need it:

~~~sql
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
~~~

This is a schema-level change that may affect other applications sharing the database. Apply it only after checking ownership, migrations, and active workloads. Do not run broad `REVOKE` commands in production without impact assessment.

Also verify `search_path`. Do not let runtime resolve functions/tables through a schema where untrusted users can create objects with the same name. Set a safe `search_path` and schema-qualify object names when needed.

## 11. MySQL Example: Roles and Runtime Accounts

MySQL supports roles to group privileges:

~~~sql
CREATE ROLE 'orders_runtime_role';

GRANT SELECT, INSERT, UPDATE
ON orders_db.orders
TO 'orders_runtime_role';

GRANT SELECT, INSERT
ON orders_db.order_line
TO 'orders_runtime_role';

CREATE USER 'orders_runtime'@'10.%'
IDENTIFIED BY '<managed-secret>';

GRANT 'orders_runtime_role'
TO 'orders_runtime'@'10.%';

SET DEFAULT ROLE 'orders_runtime_role'
TO 'orders_runtime'@'10.%';
~~~

Key points to note:

- A MySQL account is identified by both user and host.
- `GRANT ... ON database.table` scopes privileges to specific objects.
- `SET DEFAULT ROLE` activates the role automatically on login.
- Never use `GRANT ALL ON *.*` for a runtime account.
- Never grant `FILE`, `PROCESS`, `SUPER`, `CREATE USER`, `GRANT OPTION`, or other global privileges unless the workload requires them.

Role syntax and behavior can vary across MySQL/MariaDB versions. Verify against the exact product and version you are running.

### MySQL: separating migration privileges

The migration account may need `CREATE`/`ALTER`/`INDEX`/`DROP` in the target schema, whereas runtime does not:

~~~sql
CREATE ROLE 'orders_migration_role';

GRANT SELECT, INSERT, UPDATE, DELETE,
      CREATE, ALTER, INDEX, DROP
ON orders_db.*
TO 'orders_migration_role';
~~~

The exact privilege list depends on the migration tool and schema change types. Grant only what current migrations require. This account should not be configured in the request-serving application's connection pool.

## 12. SQL Server Example: Database Users and Database Roles

SQL Server distinguishes between server logins and database users. After creating a login, create a corresponding user in the database and add it to a database role:

~~~sql
USE master;
CREATE LOGIN orders_runtime
WITH PASSWORD = '<managed-secret>';
GO

USE orders_db;
CREATE USER orders_runtime
FOR LOGIN orders_runtime;
GO

CREATE ROLE orders_runtime_role;

GRANT SELECT, INSERT, UPDATE
ON SCHEMA::orders
TO orders_runtime_role;

ALTER ROLE orders_runtime_role
ADD MEMBER orders_runtime;
GO
~~~

This example grants `SELECT`/`INSERT`/`UPDATE` on the `orders` schema. If finer object or column limits are needed, grant on specific tables or columns.

Never add runtime to broad roles like `db_owner`, `db_ddladmin`, or the server role `sysadmin` to resolve an operation error. Identify the exact missing permission and grant it narrowly.

### SQL Server: permissions for stored procedures

If the application is only permitted to execute business logic through stored procedures, you can grant only `EXECUTE` on the procedure or its schema:

~~~sql
GRANT EXECUTE
ON OBJECT::orders.CreateOrder
TO orders_runtime_role;
~~~

When using stored procedures to restrict rights, evaluate ownership chaining, execution context, and the underlying privileges used inside the procedure. Do not grant additional direct table privileges if the security design does not require them.

## 13. Oracle Example: Roles and Object Privileges

Oracle typically uses roles to bundle privileges:

~~~sql
CREATE ROLE orders_runtime_role;

GRANT CREATE SESSION
TO orders_runtime_role;

GRANT SELECT, INSERT, UPDATE
ON orders_owner.orders
TO orders_runtime_role;

GRANT SELECT, INSERT
ON orders_owner.order_line
TO orders_runtime_role;

GRANT SELECT
ON orders_owner.customer_view
TO orders_runtime_role;

GRANT orders_runtime_role
TO orders_runtime;
~~~

`CREATE SESSION` allows the user to log in. Object privileges restrict operations on objects belonging to the schema owner.

Never grant broad system privileges such as `DBA`, `CREATE ANY TABLE`, `ALTER ANY TABLE`, or `SELECT ANY TABLE` to a runtime account without approved justification.

For sequences, Oracle uses sequence privileges, for example:

~~~sql
GRANT SELECT ON orders_owner.orders_seq
TO orders_runtime_role;
~~~

Required privileges depend on how `INSERT` invokes `NEXTVAL`, procedures, and referenced objects. Test with the actual runtime user.

## 14. SQLite and User/Role Model Limitations

SQLite is an embedded database without a user/role and `GRANT`/`REVOKE` model like PostgreSQL, MySQL, SQL Server, or Oracle.

In applications using SQLite, access control typically relies on:

- Operating system read/write permissions on the database file.
- The OS identity of the process running the application.
- Directory permissions for the database and journal/WAL files.
- Access permissions on backups and temporary files.
- Separating database files by workload or tenant when architecture requires it.
- Configuring read-only connections via driver/URI options when needed.

Read-only mode and URI syntax depend on the driver. Do not assume every R2DBC SQLite driver supports the same options.

Because SQLite lacks server-side database users, examples like `CREATE ROLE` or `GRANT SELECT` above do not apply directly. Protect files and processes at the OS layer while still controlling SQL inside the application.

## 15. Granting by Database, Schema, Table, and Column

Start from the narrowest scope that satisfies requirements:

1. Database: allow `CONNECT` or `CREATE SESSION`.
2. Schema: allow `USAGE` or equivalent schema access.
3. Table/view: `SELECT`, `INSERT`, `UPDATE`, `DELETE`.
4. Column: read/modify only required columns if the database supports it.
5. Sequence: privilege to obtain ID values.
6. Procedure/function: `EXECUTE`.

Do not grant database-wide privileges if a service uses only one schema. Do not grant schema-wide privileges if a service only needs a few tables or views.

### Using views to limit readable data

If reporting only needs a subset of columns, you can create a view:

~~~sql
CREATE VIEW reporting.order_summary AS
SELECT id, tenant_id, status, created_at
FROM orders.orders;
~~~

Then grant `SELECT` only on the view to the reporting role. Do not grant `SELECT` on the base table if the view meets the requirement.

View security depends on the database, view configuration, owner/invoker semantics, and underlying object permissions. Verify how the database enforces view permissions, especially when the view references tables in another schema.

## 16. `DELETE` and `UPDATE` Privileges Need Special Consideration

`DELETE` can cause wide data loss. If the application only marks records as `inactive` or `cancelled`, it may only need `UPDATE` on the status column rather than `DELETE`.

When deletion is required:

- Restrict to exact tables.
- Restrict to the exact tenant/row via application authorization or row-level security.
- Consider soft delete when suited to business requirements.
- Use transactions and verify conditions before deleting.
- Audit significant delete operations.

Table-level `UPDATE` allows modifying any column the role can access. To protect sensitive columns, use column-level privileges or an appropriate stored procedure.

Never grant `TRUNCATE` to runtime just because it deletes data quickly. `TRUNCATE` has different semantics and impact than `DELETE`, depending on the database.

## 17. Separating Privileges for Migration and Runtime

Schema migrations need broader rights than request handling. Both credentials should be separated:

~~~text
Deploy pipeline
      |
      v
orders_migration
      |
      +--> CREATE / ALTER / INDEX / DROP
      |
      v
orders schema

Application runtime
      |
      v
orders_runtime
      |
      +--> SELECT / INSERT / UPDATE
      |
      v
orders schema
~~~

Recommended workflow:

1. The migration job uses the migration credential fetched from the secret store.
2. Migrations evolve the schema by version.
3. Verify object ownership and default permissions on new objects.
4. The application starts with the runtime credential.
5. Runtime performs only granted DML operations.

Do not run migrations automatically using the runtime account when runtime does not need DDL. If a framework or startup hook attempts to run migrations, configure migrations to run in a separate pipeline or with separate credentials.

### Default privileges and new objects

After a migration creates a new table, the runtime role may encounter permission-denied errors if privileges were granted only on older tables. You should:

- Configure default privileges matching the owner role (if the database supports it).
- Or have the migration explicitly grant privileges on new objects.
- Verify new sequences, views, procedures, and functions.
- Include a test that starts the application with the runtime credential after migration.

## 18. Integrating Privileges with Spring Data R2DBC

Spring Data R2DBC uses whatever credentials `ConnectionFactory` provides. Simple configuration example:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db-host:5432/orders_db
    username: ORDERS_DB_USERNAME
    password: ORDERS_DB_PASSWORD
~~~

`ORDERS_DB_USERNAME` and `ORDERS_DB_PASSWORD` represent values supplied from the environment or secret manager at runtime. Never commit real values into `application.yml`, Docker images, or repositories.

When `ReactiveCrudRepository` calls `findById()`, `save()`, or `deleteById()`, the database executes operations under the account attached to the connection. If the role lacks `UPDATE` privilege, `save()` will raise a database error when the framework chooses the `UPDATE` branch.

Likewise, `DatabaseClient` does not bypass database privileges. Writing SQL directly does not give a statement extra permissions.

### Distinguishing mapping errors from permission errors

Common errors include:

- Permission denied / insufficient privilege: the account lacks privileges on the database/schema/object.
- Authentication failed: incorrect username/password or authentication method.
- Object not found: wrong schema/search path or object name; sometimes databases intentionally avoid disclosing objects.
- SQL syntax/type error: invalid statement or bind type.

Never resolve permission errors by automatically granting admin privileges. Identify the exact denied object and operation, then grant the minimal privilege if the business case is valid.

## 19. Separating Read-Only and Read-Write `ConnectionFactory` Beans

An application with distinct read and write workloads can use two accounts:

~~~text
Read service
    |
    v
readOnlyConnectionFactory
    |
    v
orders_readonly (SELECT)

Write service
    |
    v
readWriteConnectionFactory
    |
    v
orders_runtime (SELECT/INSERT/UPDATE)
~~~

The read-only account may connect to a replica or primary database while having only `SELECT`. When connecting to a replica, account for replication lag and read-consistency semantics required by the domain.

Bean example:

~~~java
@Bean("ordersReadOnlyConnectionFactory")
ConnectionFactory ordersReadOnlyConnectionFactory(
        ReadOnlyDatabaseProperties properties) {
    return properties.connectionFactory();
}

@Bean("ordersReadWriteConnectionFactory")
ConnectionFactory ordersReadWriteConnectionFactory(
        ReadWriteDatabaseProperties properties) {
    return properties.connectionFactory();
}
~~~

Each repository group or `DatabaseClient` must be wired to the right `ConnectionFactory` via entity operations/qualifier configuration. Do not expect a method name starting with `find...` to automatically switch to a read-only account; the credential comes from the connection factory.

`@Transactional(readOnly = true)` can pass hints to transaction infrastructure or the database, but does not replace `SELECT`-only database privileges. To make the database reject writes, use an account/role without write privileges or a database-enforced read-only transaction.

## 20. Tenant-Scoped Authorization and Row-Level Security

Table-level `SELECT` allows an account to read any row covered by that privilege. When a table stores multiple tenants' data, application-level filters alone may fall short if a query has a bug or an endpoint omits the tenant predicate.

Some databases support row-level security (RLS), policies, or conditional views. With PostgreSQL, for example:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_policy
ON orders
USING (
    tenant_id =
    current_setting('app.tenant_id', true)::bigint
)
WITH CHECK (
    tenant_id =
    current_setting('app.tenant_id', true)::bigint
);
~~~

The application sets tenant context inside the transaction:

~~~sql
SELECT set_config('app.tenant_id', :tenantId, true);
~~~

The third argument `true` scopes the setting to the current transaction (equivalent to a local setting). Ensure the context-setting command and all tenant queries execute on the same transaction/connection.

### RLS does not replace tenant authentication

The tenant value must come from a verified principal or trusted source. Never accept an arbitrary tenant ID from a request and treat it as valid access permission.

With connection pools:

- Prefer transaction-local settings over session-level settings.
- Never allow a previous request's tenant context to leak into a subsequent request.
- If a transaction cancels or fails, ensure context rolls back/resets per database semantics.
- Test reusing the same pooled connection across two tenants.

PostgreSQL superusers and roles with `BYPASSRLS` bypass RLS; table owners are usually exempt unless `FORCE ROW LEVEL SECURITY` is enabled. Runtime should therefore never be a superuser or owner when relying on RLS to constrain rows.

RLS, policies, and session context differ across PostgreSQL, SQL Server, Oracle, and other databases. Do not treat the PostgreSQL syntax above as a portable solution.

## 21. `EXECUTE` Privileges for Stored Procedures and Functions

If the application only needs to invoke specific workflows encapsulated in stored procedures, you can grant `EXECUTE` instead of direct DML privileges across all tables.

Conceptual example:

~~~sql
GRANT EXECUTE ON PROCEDURE orders.create_order
TO orders_runtime_role;
~~~

Exact syntax varies among PostgreSQL, MySQL, SQL Server, and Oracle. Also verify whether procedures run under owner or invoker rights, ownership chaining, and how the database checks underlying object permissions.

Stored procedures are not automatically safe simply because the caller lacks `SELECT`/`UPDATE` on tables. A procedure can contain dynamic SQL or run with elevated rights. Review procedures as security boundaries:

- Accept only necessary parameters.
- Enforce tenant/actor checks if the procedure is responsible for authorization.
- Never concatenate input into uncontrolled dynamic SQL.
- Never grant `EXECUTE` on all procedures when only specific ones are needed.
- Audit sensitive operations.

## 22. SQL Injection and Least Privilege

Bind parameters remain the foundational defense:

~~~java
return databaseClient.sql(
        "SELECT id, status FROM orders WHERE customer_id = :customerId"
    )
    .bind("customerId", customerId)
    .map((row, metadata) -> new OrderSummary(
        row.get("id", Long.class),
        row.get("status", String.class)
    ))
    .all();
~~~

Never concatenate input values into SQL:

~~~java
// Unsafe
String sql = "SELECT * FROM orders WHERE customer_id = " + customerId;
~~~

Bind parameters are for values, not for binding table names, column names, or keywords. When dynamic identifiers are needed:

- Use a fixed allowlist.
- Select identifiers from controlled enums/configs.
- Quote identifiers per database/dialect.
- Never let clients send arbitrary SQL fragments.

Least privilege reduces the blast radius if injection occurs, but does not make SQL injection acceptable. You must still use bind parameters and control dynamic SQL.

## 23. Credential and Secret Management

A least-privilege account still poses risk if its password leaks. Credential management requires:

- Storing secrets in a secret manager or the environment's secret management system.
- Never committing them to Git, sample files with real values, logs, or exceptions.
- Never printing full R2DBC URLs if URLs contain credentials.
- Restricting secret read access to the exact workload.
- Using different credentials across development, test, staging, and production.
- Auditing secret access and modifications.
- Revoking credentials when a service or instance is decommissioned.

Never share one password across runtime, migration, backup, and DBA accounts. A single credential leak should not grant access across all workloads.

### Credential rotation

A rotation process can include:

1. Creating a new credential with the same required role/privileges.
2. Updating the secret store.
3. Restarting or reloading the application via a supported mechanism.
4. Confirming new connection pools use the new credential.
5. Verifying requests and jobs operate normally.
6. Revoking the old credential once no connections depend on it.

Connection pools hold authenticated connections. Simply changing a secret in the environment does not immediately switch existing connections to the new credential. Understand how your application implements pool refresh/restart.

## 24. Connection Pools and Database Identity

Every connection in a pool is opened using `ConnectionFactory` credentials. Requests reuse those connections under the same database principal.

This has several consequences:

- Do not switch database users per request on the same pool.
- Do not store session-level tenant context and forget to reset it.
- Do not keep admin-privileged connections inside a runtime pool.
- When separating read-only and write workloads, create separate `ConnectionFactory`/pools with their respective accounts.
- Set pool sizes and timeouts within database limits.

When an account is locked or a password rotated, existing connections may remain alive until closed. Operational procedures must handle the connection pool, not just update passwords in the secret store.

## 25. Auditing and Monitoring Database Privileges

You should be able to answer:

- Which account connects from which service/instance?
- Which account performed sensitive operations?
- Are there unusual login failures or permission-denied errors?
- Which roles are assigned to runtime?
- When were permissions or credentials changed?
- Do old unused accounts still exist?

Databases provide different audit logs and monitoring mechanisms. Choose logging levels carefully to avoid recording sensitive data or causing excessive overhead.

The application should also log correlation IDs, service identity, and business actor (where permitted) to tie requests to database activity. Never log passwords, tokens, or full sensitive bind values.

Periodically review:

- Role memberships.
- Grants on schemas, tables, sequences, and procedures.
- Inactive accounts.
- Expired credentials or ones due for rotation.
- Temporary permissions granted for incident response.

## 26. Handling Permission Denied in the Application

When the database rejects an operation, R2DBC normally emits a data access error through the reactive pipeline. Do not:

- Retry a permission-denied error indefinitely.
- Automatically escalate permissions from application code.
- Swallow the error and return success.
- Expose raw schema details, SQL, or internal permissions to end clients.

Instead:

1. Let the error surface at the service layer so the request/job fails clearly.
2. Log internally with a correlation ID and sanitized operation details.
3. Distinguish permission configuration errors from business errors.
4. Grant additional privileges only after confirming the operation is valid and the privilege is genuinely needed.
5. Avoid blindly repeating a write operation if it is unclear whether the first attempt executed partially.

A permission error is usually not a transient error suitable for retries. Retries belong only to well-defined transient errors such as connection resets or deadlocks according to policy.

## 27. Testing with the Actual Runtime Account

Tests running under developer or admin accounts can mask missing runtime privileges. Security integration tests must connect using credentials matching production runtime.

Example test matrix:

| Operation | Runtime role | Read-only role | Migration role |
|---|---|---|---|
| SELECT orders | Succeeds | Succeeds | As needed |
| INSERT orders | Succeeds if needed | Denied | As needed |
| UPDATE orders | Succeeds if needed | Denied | As needed |
| DELETE orders | Denied if not needed | Denied | As needed |
| CREATE TABLE | Denied | Denied | Succeeds if needed |
| ALTER TABLE | Denied | Denied | Succeeds if needed |
| Read billing schema | Denied if outside service | Denied | Within migration scope |

Test both allowed and denied behaviors. Testing only that `SELECT` succeeds does not prove the runtime account cannot `DROP TABLE`.

### Post-migration testing

A CI/CD pipeline should:

1. Create a test database/schema.
2. Run migrations using the migration credential.
3. Switch to the runtime credential.
4. Start the application or integration tests.
5. Run all CRUD/queries/procedures required by the service.
6. Attempt several out-of-scope operations to verify they are denied.
7. Verify privileges on newly created objects.

Never run destructive tests against shared or production databases. Use isolated test databases and synthetic data.

## 28. Example Privilege Architecture for an R2DBC Application

An orders service can be structured as:

~~~text
                    Database: orders_db
                            |
          +-----------------+-----------------+
          |                 |                 |
          v                 v                 v
   orders_runtime    orders_readonly   orders_migration
          |                 |                 |
          v                 v                 v
   Required SELECT/    SELECT on         DDL within
   INSERT/UPDATE       needed views/     schema scope
                       tables
          |                 |                 |
          v                 v                 v
   Write Connection   Read Connection    Migration job
       Factory            Factory
          |                 |
          v                 v
   R2dbcEntityTemplate  R2dbcEntityTemplate
          |                 |
          v                 v
   Write repositories  Read repositories
~~~

Each `ConnectionFactory` is configured with its own credentials. Each repository group is bound to the proper `R2dbcEntityOperations`, and transaction managers use the matching `ConnectionFactory`.

The migration job is a separate process, not a runtime endpoint. Once deployed, request-serving code needs only its defined DML rights.

## 29. Least-Privilege Design Checklist

Before deployment:

1. List service, worker, reporting, and migration workloads.
2. Identify the databases/schemas/tables/views/sequences/procedures each workload needs.
3. List exact `SELECT`, `INSERT`, `UPDATE`, `DELETE`, and `EXECUTE` operations.
4. Determine whether column-level or view-level restrictions can be applied.
5. Separate object owner/migration accounts from runtime accounts.
6. Create non-login group roles if supported by the database.
7. Create separate logins per workload and environment.
8. Avoid granting administrative rights, `GRANT OPTION`, or unnecessary global rights.
9. Configure `ConnectionFactory` with proper credentials from the secret store.
10. Verify connection pools and transaction managers use the right account/database.
11. For multi-tenant systems, evaluate RLS or appropriate policies and protect tenant context.
12. Control dynamic SQL via bind parameters and identifier allowlists.
13. Configure default privileges or migration grants for new objects.
14. Test both allowed and denied operations using the runtime account.
15. Monitor logins, permission errors, grants, and credential rotation.
16. Review and revoke privileges no longer required.

## 30. Common Mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Using a DBA account for R2DBC runtime | Application bugs can affect the whole database | Create a dedicated runtime role |
| Sharing runtime and migration credentials | Request services can alter schemas | Separate the migration identity |
| `GRANT ALL` across all databases | Overly broad access scope | Grant by schema/object/operation |
| Runtime owning tables | Can alter objects beyond DML needs | Use a separate owner role |
| Granting only on older tables | New tables created by migrations hit permission denied | Default privileges or migration grants |
| Forgetting sequence privileges | ID-generating `INSERT` fails | Grant exact sequence privileges per database |
| Granting unnecessary `DELETE`/`TRUNCATE` | Raises data loss risk | Grant only required business operations |
| Treating `@Transactional(readOnly=true)` as a security barrier | Database may still permit writes | Use a read-only database role |
| Confusing database accounts with end users | Cannot control per-actor permissions | Enforce authorization in the app and RLS if suited |
| Trusting tenant ID from requests | Can access other tenants | Resolve tenant from trusted principal |
| Using session-level tenant settings with pools | Context can leak across requests | Transaction-local settings and pool reuse tests |
| Building dynamic SQL from input | SQL injection or unintended object access | Bind values and allowlist identifiers |
| Granting admin roles to fix permission errors | Excessive privilege escalation | Identify the exact denied object/operation |
| Testing only with developer accounts | Misses missing runtime privileges | Test with runtime credentials |
| Rotating secrets without refreshing the pool | Old connections keep using old credentials | Plan pool refresh/restart |
| Not auditing role memberships | Old permissions linger long-term | Review and revoke periodically |

## 31. Takeaways

- Least privilege means each database account holds only the permissions needed for its exact workload.
- A database account represents the service/connection; it does not replace end-user authorization.
- Separate runtime, read-only, worker, migration, and DBA accounts whenever privilege needs differ.
- Use roles to bundle permissions and separate logins to manage credentials per environment/workload.
- Never let runtime own schemas/tables or hold `SUPERUSER`, `DBA`, `db_owner`, `CREATEROLE`, or equivalent privileges unnecessarily.
- Grant `CONNECT`/session, schema usage, table DML, sequences, and procedure `EXECUTE` to the actual required scope.
- Grants on existing tables do not automatically cover future objects; configure default privileges or grant within migrations.
- PostgreSQL, MySQL, SQL Server, and Oracle differ in `GRANT` syntax and semantics; SQLite has no server-side users/roles.
- `@Transactional(readOnly = true)` does not replace a read-only database role.
- Spring Data R2DBC and `DatabaseClient` always run under the principal attached to `ConnectionFactory`.
- For multi-tenant systems, combine application authorization with RLS/policies when appropriate; tenant context must be set safely inside transactions.
- Use bind parameters for values, allowlists for identifiers, and never assemble SQL from input.
- Manage passwords via secret stores, separate credentials across environments, and maintain rotation/revocation procedures.
- Test both permitted and denied operations using the real runtime account after migrations.
- Monitor database grants, logins, and permission errors, and audit privileges regularly.
