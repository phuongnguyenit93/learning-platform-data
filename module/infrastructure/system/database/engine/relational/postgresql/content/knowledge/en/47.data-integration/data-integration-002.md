# postgres_fdw, Foreign Server, User Mapping, and Foreign Table

PostgreSQL can access data residing in another PostgreSQL server through the Foreign Data Wrapper (FDW) mechanism. With the **postgres_fdw** extension, the local database defines a foreign server describing how to connect to the remote database, a user mapping that maps local user identities to remote accounts, and foreign tables representing tables on the remote side. Applications can query a foreign table with SQL very similar to querying a local table; PostgreSQL offloads the appropriate portion of the work to the remote server and returns results to the local query.

This mechanism enables data integration without copying entire tables into the local database. It is useful for reading data from other business systems, consolidating data at query time, migrating applications incrementally, or building a cross-server data access layer. However, a foreign table is not a local copy and does not turn two databases into a full distributed transaction engine. Every query can incur network round trips, remote CPU/I/O, authentication, and consistency considerations. Proper design must account for access privileges, latency, planner estimates, pushdown, transaction semantics, failure handling, and monitoring on both sides.

This lesson belongs to the **Data Integration** chapter of the **Database Engine Relational PostgreSQL** module. It covers FDW architecture, installing `postgres_fdw`, creating foreign servers and user mappings, importing or defining foreign tables, querying/DML, optimization, security, transaction behavior, and production operations.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain Foreign Data Wrappers, foreign servers, user mappings, and foreign tables.
- Distinguish between the extension package and extension installation inside a database.
- Install and enable `postgres_fdw` in a local database.
- Create a foreign server with host, port, dbname, and connection options.
- Create a user mapping from a local role to a remote role.
- Grant properly scoped privileges on foreign servers, schemas, and foreign tables.
- Use `IMPORT FOREIGN SCHEMA` or `CREATE FOREIGN TABLE`.
- Understand the mapping between local foreign table metadata and remote relations.
- Query and update data through `postgres_fdw` within supported limits.
- Understand predicate/join/aggregate pushdown and planner costing.
- Tune fetch size, batch size, and remote estimates according to workload.
- Analyze transaction, snapshot, connection cache, and failure semantics.
- Protect credentials, `search_path`, and network connections.
- Monitor activity on both local and remote PostgreSQL servers.
- Build troubleshooting, performance testing, and lifecycle runbooks.

## 2. What Is a Foreign Data Wrapper?

A Foreign Data Wrapper is an extensibility interface that allows PostgreSQL to access external data through a unified API.

### 2.1. FDW Handler

An FDW provides handler functions so the PostgreSQL planner/executor can request metadata and execute scans/updates against a foreign data source.

### 2.2. Foreign Server

A foreign server is a local object describing an external data source along with FDW connection and planning options. With `postgres_fdw`, a server typically represents a remote PostgreSQL database.

### 2.3. User Mapping

A user mapping maps a local database role (or PUBLIC) to a remote identity and authentication options. Multiple local users can map to the same or different remote users.

### 2.4. Foreign Table

A foreign table is an object in the local catalog describing the columns and options of a remote relation. It does not store the remote table's rows in local storage.

### 2.5. Unified SQL Interface

Applications query a foreign table using SELECT/INSERT/UPDATE/DELETE within the capabilities supported by the FDW. PostgreSQL decides which parts can be pushed down to run on the remote server.

## 3. postgres_fdw Architecture

`postgres_fdw` is an FDW included in the PostgreSQL contrib ecosystem that uses libpq to connect to remote PostgreSQL servers.

~~~text
Application / local SQL
          |
          v
Local PostgreSQL planner/executor
          |
          v
Foreign table metadata
          |
          v
postgres_fdw
    |         |
    |         +--> User mapping (remote credentials)
    |
    +------------> Foreign server (host/port/dbname/options)
                         |
                         v
                   libpq connection
                         |
                         v
                 Remote PostgreSQL
                         |
                         v
                 Remote tables/indexes
~~~

### 3.1. Local Database

Foreign servers, user mappings, and foreign tables are created inside a local database. This configuration is not automatically shared with other databases in the same cluster.

### 3.2. Remote Database

The actual data and indexes reside on the remote server. The remote server executes pushed-down SQL and enforces the remote role's permissions.

### 3.3. Connection Layer

`postgres_fdw` opens connections via libpq. Hostname, port, TLS, authentication, and network reachability must work from the host/container running local PostgreSQL.

### 3.4. Planner/Executor Integration

The local planner builds plans containing Foreign Scan nodes. The executor fetches rows from the remote server or sends DML remotely depending on the statement and FDW capabilities.

### 3.5. Not Replication

A foreign table reads remote data on demand per query; it does not maintain a synchronized local copy like physical or logical replication.

## 4. When to Use postgres_fdw?

An FDW is appropriate when you need on-demand access to remote data and can accept the network dependency.

### 4.1. Query-Time Data Consolidation

A local query can join local tables with foreign tables to return combined results without running ETL for the entire source.

### 4.2. Phased Application Integration

Applications can gradually shift queries to a local schema while data remains in the remote database.

### 4.3. Reporting and Read Access

Foreign tables can support reporting against a source database. Query concurrency must be controlled to avoid overloading the remote system.

### 4.4. Small and Medium Data Federation

An FDW can combine multiple PostgreSQL sources under one SQL interface. For data lakes, high-volume analytics, or many heterogeneous sources, consider dedicated federation/ETL tools instead.

### 4.5. When Not to Use It

If you need consistently low latency regardless of network outages, atomic transactions across multiple servers, continuous full-table scans, or heavy analytics workloads, consider replication, materialized copies, ETL/ELT, or a specialized data platform.

## 5. Installing postgres_fdw

`postgres_fdw` is typically distributed in the PostgreSQL contrib package matching your version. The package must be installed on the server before creating the extension in a database.

### 5.1. Package Availability

On Linux, the package name follows the distribution/repository and major version—for example, the PostgreSQL contrib package. On managed services, check the provider's extension allowlist.

### 5.2. Installing the Extension in the Local Database

~~~sql
CREATE EXTENSION postgres_fdw;
~~~

This command creates the FDW handler/validator objects in the current database. Run it in the database that will hold the foreign servers and tables.

### 5.3. Checking the Extension

~~~sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'postgres_fdw';
~~~

### 5.4. Checking FDW Registration

~~~sql
SELECT
    fdwname,
    fdwowner::regrole AS owner,
    fdwhandler::regproc AS handler,
    fdwvalidator::regproc AS validator
FROM pg_foreign_data_wrapper;
~~~

### 5.5. Each Database Needs Its Own Installation

If multiple local databases need `postgres_fdw`, run `CREATE EXTENSION` in each database. Installing the OS package once on the server does not create extension objects in every database.

## 6. Creating the Foreign Data Wrapper Object

`CREATE EXTENSION postgres_fdw` normally creates a foreign data wrapper named `postgres_fdw`. In special cases you can define a wrapper object directly, but normally you use the extension package.

### 6.1. Foreign Data Wrapper

~~~sql
SELECT
    fdwname,
    fdwoptions
FROM pg_foreign_data_wrapper;
~~~

### 6.2. Handler and Validator

The handler provides the callback implementation; the validator verifies whether options on servers, user mappings, and tables are valid for the FDW.

### 6.3. Wrapper Ownership

The wrapper owner manages the object and dependent servers. Use an appropriate administrative role.

### 6.4. Wrapper Options

Some FDWs support wrapper-level options. `postgres_fdw` generally places connection and planning options on the server, user mapping, or foreign table according to option scope.

### 6.5. Do Not Create a Duplicate Wrapper

If the extension has already created the `postgres_fdw` wrapper, do not run `CREATE FOREIGN DATA WRAPPER` with the same name. Check the catalog before installing manually.

## 7. Creating a Foreign Server

A foreign server describes a remote endpoint and belongs to the local database.

~~~sql
CREATE SERVER sales_server
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'sales-db.example.internal',
    port '5432',
    dbname 'sales'
);
~~~

This is an illustrative endpoint; replace it with the real host and database from your deployment configuration.

### 7.1. host

Hostname or address of the remote PostgreSQL server. Prefer a stable DNS/service name and TLS hostname verification.

### 7.2. port

Remote PostgreSQL port, typically 5432 unless customized. Must be permitted by network policy/firewalls from the local server.

### 7.3. dbname

Database name on the remote server. The foreign server object connects to this database.

### 7.4. OPTIONS

Options are key/value strings defined by `postgres_fdw`/libpq. The validator checks supported options.

### 7.5. Local Server Name

`sales_server` is only an object name inside the local database. It does not have to match the remote hostname or remote database name.

## 8. Connection Options and TLS

`postgres_fdw` uses libpq connection parameters, so standard connection options can be configured.

### 8.1. sslmode

For production, prefer an appropriate TLS configuration. `sslmode='verify-full'` requires a valid certificate and matching hostname; the target server needs proper CA trust configured.

### 8.2. connect_timeout

Limits how long connection establishment may take so endpoint/network failures do not stall a query indefinitely during the connect phase.

### 8.3. application_name

Setting `application_name` helps identify FDW connections in `pg_stat_activity` on the remote side.

### 8.4. keepalives

libpq keepalive options can help detect broken TCP connections depending on OS and network behavior. Tune according to your environment.

### 8.5. Do Not Store Secrets in Server Options

Host, port, and dbname are generally not secrets. Remote username/password belong in the user mapping and must be protected separately.

## 9. Inspecting Foreign Servers

The `pg_foreign_server` catalog stores server object metadata.

~~~sql
SELECT
    srvname,
    srvowner::regrole AS owner,
    fdwname,
    srvoptions
FROM pg_foreign_server AS s
JOIN pg_foreign_data_wrapper AS w
  ON w.oid = s.srvfdw
ORDER BY srvname;
~~~

### 9.1. srvname

Name of the foreign server in the local database.

### 9.2. srvowner

Role that owns the server object. The owner can ALTER/DROP the object and manage privileges.

### 9.3. fdwname

Foreign data wrapper used by the server, such as `postgres_fdw`.

### 9.4. srvoptions

Connection and planning options stored on the server object. Do not place passwords here.

### 9.5. Catalog Visibility

Metadata read access may depend on privileges. Avoid granting broad catalog access if options contain sensitive details.

## 10. Creating the Remote Role and Remote Privileges

A local user mapping authenticates as a role on the remote server. That remote role needs privileges on the database, schemas, and tables being accessed.

### 10.1. Creating a Read-Only Role on the Remote Server

On the remote database, a DBA can create a dedicated role:

~~~sql
CREATE ROLE fdw_sales_reader
LOGIN
NOSUPERUSER
NOCREATEDB
NOCREATEROLE;
~~~

Set the password via an appropriate secret-management/deployment process; never record secrets in source code or tickets.

### 10.2. Granting Connect Privilege

~~~sql
GRANT CONNECT ON DATABASE sales TO fdw_sales_reader;
~~~

### 10.3. Granting Schema Usage

~~~sql
GRANT USAGE ON SCHEMA public TO fdw_sales_reader;
~~~

### 10.4. Granting Read Privileges

~~~sql
GRANT SELECT ON TABLE public.customers, public.orders
TO fdw_sales_reader;
~~~

### 10.5. Least Privilege

Never use a remote superuser for an application FDW. Grant privileges strictly on the required tables and operations; for writes, grant INSERT/UPDATE/DELETE individually as needed.

## 11. What Is a User Mapping?

A user mapping connects a local role with a remote user and authentication options for a specific foreign server.

~~~sql
CREATE USER MAPPING FOR app_reader
SERVER sales_server
OPTIONS (
    user 'fdw_sales_reader',
    password 'REPLACE_WITH_SECRET'
);
~~~

This example only shows the SQL structure. Password values must be supplied through your environment's secure secret process.

### 11.1. Local Role

`app_reader` is the role in the local database executing the query.

### 11.2. Remote User

`fdw_sales_reader` is the remote account that `postgres_fdw` uses to connect.

### 11.3. Mapping Per Server

A local role can have different mappings for different foreign servers.

### 11.4. Per-User Mappings

Mappings can be created for multiple local roles, each using a different remote identity and privilege set.

### 11.5. Mapping for PUBLIC

A mapping `FOR PUBLIC` applies to local users without an explicit mapping, but requires caution because it can share a remote identity too broadly.

## 12. User Mapping and Authentication

Authentication takes place when the local backend connects to the remote PostgreSQL server.

### 12.1. Password Option

`postgres_fdw` can use `user`/`password` options in the mapping. The password is a remote credential and requires rotation and protection like any other secret.

### 12.2. .pgpass

libpq can use a password file according to the client process rules when passwords are not passed via the mapping. For service accounts, strictly control file ownership and permissions.

### 12.3. Certificate Authentication

Client certificate options supported by libpq can be used alongside remote `pg_hba.conf` configuration. Protect private keys and manage the certificate lifecycle.

### 12.4. GSS/SSPI and Other Auth Methods

Available authentication methods depend on the libpq build, OS, and remote `pg_hba.conf`. Verify compatibility in your target environment.

### 12.5. Remote pg_hba.conf

The remote server must allow connections from the local PostgreSQL host/container for the target database and remote user using an appropriate authentication method.

## 13. User Mapping Catalog and Access Controls

`pg_user_mapping` stores mapping metadata; the `pg_user_mappings` view provides a more readable format.

~~~sql
SELECT
    s.srvname,
    u.umuser::regrole AS local_user,
    u.umoptions
FROM pg_user_mapping AS u
JOIN pg_foreign_server AS s
  ON s.oid = u.umserver
ORDER BY s.srvname, local_user;
~~~

### 13.1. Mapping for PUBLIC

`umuser` equal to zero represents a mapping for PUBLIC. You can inspect it via catalog queries, taking care to interpret zero correctly.

### 13.2. pg_user_mappings

This view displays user mappings and masks the password option depending on the viewer's privileges.

### 13.3. Password Visibility

Superusers and the mapping owner may have permission to view sensitive options; do not grant mapping metadata access to users who do not need it.

### 13.4. Ownership

The role owning the mapping/server and USAGE privileges determine who may use the foreign server. Review grants before granting application access.

### 13.5. Credential Rotation

`ALTER USER MAPPING` can update options such as password without dropping and recreating the mapping. After rotation, test a new connection and confirm the old credential is revoked.

## 14. Granting Permission to Use a Foreign Server

Creating a server and user mapping does not automatically allow every role to use them.

~~~sql
GRANT USAGE ON FOREIGN SERVER sales_server TO app_reader;
~~~

### 14.1. USAGE Privilege

A role needs USAGE on the foreign server to access it through foreign tables.

### 14.2. Local Schema Privilege

The role also needs USAGE on the local schema containing the foreign tables.

### 14.3. Local Table Privileges

Grant SELECT/INSERT/UPDATE/DELETE on foreign tables as needed. Remote permissions are still enforced on the remote server.

### 14.4. Avoid Broad Server Usage Grants

Granting USAGE to PUBLIC or too many application roles can widen access to remote connection mappings. Grant only to the specific required role.

### 14.5. Two Layers of Authorization

Local privileges control who can query the foreign table; remote privileges control what data the remote user can read or write. Verify both layers.

## 15. Creating a Local Schema for Foreign Tables

Foreign tables must reside in a local schema, independent of the remote schema.

~~~sql
CREATE SCHEMA remote_sales AUTHORIZATION db_owner;
GRANT USAGE ON SCHEMA remote_sales TO app_reader;
~~~

### 15.1. Local Namespace

`remote_sales` is a schema in the local database and can differ from the remote `public` schema.

### 15.2. Namespace Separation

A dedicated schema distinguishes remote objects from local tables and avoids name collisions.

### 15.3. Owner

Choose a deployment/DBA role as owner. Application runtime roles only need the minimum required grants.

### 15.4. Search Path

Do not rely on an ambiguous `search_path` when foreign table names collide with local relations. Use schema-qualified names in critical SQL.

### 15.5. Schema Lifecycle

The local schema does not synchronize automatically with the remote schema. Remote DDL changes require manual migration/refresh or separate automation.


## 16. Importing a Foreign Schema

`IMPORT FOREIGN SCHEMA` creates multiple local foreign tables from relations in a remote schema.

~~~sql
IMPORT FOREIGN SCHEMA public
LIMIT TO (customers, orders)
FROM SERVER sales_server
INTO remote_sales;
~~~

### 16.1. Remote Schema

`public` is the schema on the remote database. It does not have to match the local schema where foreign tables are created.

### 16.2. LIMIT TO

Imports only the listed tables/views. Useful when only a small subset of objects is needed.

### 16.3. EXCEPT

You can use `EXCEPT` to import all objects in a remote schema except an exclusion list.

~~~sql
IMPORT FOREIGN SCHEMA public
EXCEPT (audit_log, internal_events)
FROM SERVER sales_server
INTO remote_sales;
~~~

### 16.4. Does Not Copy Data

`IMPORT FOREIGN SCHEMA` creates metadata/foreign table definitions in the local catalog. Rows remain on the remote server.

### 16.5. Re-Running Imports

`IMPORT FOREIGN SCHEMA` is not an automatic schema sync mechanism. If foreign tables already exist, conflicts must be handled and DDL updated via a migration plan.

## 17. Options for IMPORT FOREIGN SCHEMA

`IMPORT FOREIGN SCHEMA` supports options provided by the FDW validator.

### 17.1. import_collate

Some versions support `import_collate` to control how collation metadata is imported. Check the documentation for your major version before using it.

### 17.2. import_default

Some versions support `import_default` to decide whether default expressions are imported. A remote default expression cannot necessarily execute equivalently on the local server.

### 17.3. Version Awareness

Import options can vary across PostgreSQL major versions. Check `pg_available_extension_versions` and the corresponding documentation rather than copying unsupported options.

### 17.4. Type Mapping

The FDW maps remote column types to local types. Verify numeric precision, timestamps/time zones, arrays, enums, domains, and extension types.

### 17.5. Review Generated Definitions

After importing, inspect the generated foreign table definitions/catalog options and test representative queries. Do not treat a successful import as proof of complete schema contract compatibility.

## 18. Creating a Foreign Table Manually

You can define a specific foreign table using `CREATE FOREIGN TABLE`.

~~~sql
CREATE FOREIGN TABLE remote_sales.orders (
    order_id bigint,
    customer_id bigint,
    status text,
    created_at timestamptz,
    total_amount numeric(12,2)
)
SERVER sales_server
OPTIONS (
    schema_name 'public',
    table_name 'orders'
);
~~~

### 18.1. Column Definitions

Local columns must match remote types/semantics closely enough for safe reads and writes. The FDW does not store data to arbitrarily convert every mismatch.

### 18.2. SERVER Clause

Associates the foreign table with an existing foreign server object.

### 18.3. schema_name

Specifies the remote schema containing the relation. If omitted, `postgres_fdw` uses the default schema according to FDW behavior.

### 18.4. table_name

Name of the remote relation. It can differ from the local foreign table name.

### 18.5. Foreign Table Name

`remote_sales.orders` is the local name. The remote relation is identified by the server together with the `schema_name`/`table_name` options.

## 19. Mapping Column Names

A local foreign table can use column names different from the remote relation via column options.

~~~sql
CREATE FOREIGN TABLE remote_sales.customer_summary (
    customer_key bigint OPTIONS (column_name 'customer_id'),
    customer_name text OPTIONS (column_name 'name'),
    lifetime_value numeric OPTIONS (column_name 'total_value')
)
SERVER sales_server
OPTIONS (
    schema_name 'reporting',
    table_name 'customer_summary'
);
~~~

### 19.1. column_name

This option maps a local column to a remote column name. Useful when local naming conventions differ from the source.

### 19.2. Column Order

Do not rely on column position for mapping. Column names/options and types should be declared explicitly.

### 19.3. Type Compatibility

The local type must be compatible with the remote type representation. Type mismatches can cause fetch/conversion errors or alter semantics.

### 19.4. Quoted Identifiers

Remote identifiers with mixed case or special characters must be specified accurately according to PostgreSQL identifier rules and option values.

### 19.5. Schema Drift

If the remote side renames or drops a column, the local foreign table definition does not update automatically. Queries may fail until local metadata is updated.

## 20. Foreign Table Metadata and Catalog

`pg_foreign_table` stores the server reference and options for each foreign table.

~~~sql
SELECT
    n.nspname AS local_schema,
    c.relname AS foreign_table,
    s.srvname AS foreign_server,
    ft.ftoptions
FROM pg_foreign_table AS ft
JOIN pg_class AS c ON c.oid = ft.ftrelid
JOIN pg_namespace AS n ON n.oid = c.relnamespace
JOIN pg_foreign_server AS s ON s.oid = ft.ftserver
ORDER BY 1, 2;
~~~

### 20.1. pg_foreign_table

This catalog contains foreign-table-specific metadata, including the server OID and table options.

### 20.2. pg_class

Foreign tables are relations in the catalog with the corresponding `relkind` for foreign tables. They can be inspected via `pg_class`.

### 20.3. pg_attribute

Column definitions reside in catalog attributes. Use `information_schema.columns` or `pg_attribute` to inspect the local schema.

### 20.4. information_schema.foreign_tables

The `information_schema.foreign_tables` view provides a SQL-standard inventory.

### 20.5. DDL Source of Truth

Keep foreign table definitions in migrations/source control. Do not rely solely on catalog queries when reconstructing an environment.

## 21. Modifying Foreign Table Definitions

`ALTER FOREIGN TABLE` modifies the local metadata of a foreign table.

### 21.1. Changing the Remote Table Mapping

~~~sql
ALTER FOREIGN TABLE remote_sales.orders
OPTIONS (SET table_name 'orders_archive');
~~~

This changes a local option; it does not rename the relation on the remote server.

### 21.2. Changing the Remote Schema

~~~sql
ALTER FOREIGN TABLE remote_sales.orders
OPTIONS (SET schema_name 'sales');
~~~

After changing it, verify that the relation exists and the remote role has privileges.

### 21.3. Adding/Dropping Columns

`ALTER FOREIGN TABLE` can update local column definitions. Coordinate with remote DDL and application code.

### 21.4. Does Not Sync Remote DDL

`ALTER FOREIGN TABLE` does not execute `ALTER TABLE` on the remote server. It only alters local metadata.

### 21.5. Safe Migrations

Change the remote schema before/after local changes according to a compatibility plan. If the remote side drops a column before local queries stop referencing it, requests will fail.

## 22. Inspecting Foreign Table Definitions

Use psql meta-commands or catalog queries to inspect foreign table definitions.

~~~sql
\d+ remote_sales.orders
~~~

### 22.1. psql Describe

`\d+` displays columns, the foreign server, and options depending on psql version.

### 22.2. pg_get_userbyid

You can combine `pg_class.relowner` and `pg_get_userbyid` to check ownership.

### 22.3. Column Inventory

Reconcile local foreign columns against remote `information_schema.columns` via controlled queries or metadata workflows.

### 22.4. Server Association

Each foreign table is bound to one foreign server. Switching servers typically requires creating a new foreign table or a controlled migration.

### 22.5. Reviewing Options

Verify `schema_name`/`table_name`, `column_name` mappings, and planner/fetch options before running workloads.

## 23. Querying Foreign Tables

Once the server, mapping, privileges, and foreign table exist, query it like a local relation.

~~~sql
SELECT order_id, customer_id, status, total_amount
FROM remote_sales.orders
WHERE status = 'open'
ORDER BY created_at DESC
LIMIT 50;
~~~

### 23.1. Remote Execution

`postgres_fdw` can offload eligible scans, filters, ordering, and limits to the remote server rather than pulling all rows locally.

### 23.2. Network Dependency

Queries depend on the network, DNS, TLS, remote availability, and remote load. The local server cannot return fresh data if the remote server is unavailable.

### 23.3. Result Transfer

Rows not filtered via pushdown must be transferred over the network to the local executor. Large result sets increase bandwidth, memory, and latency.

### 23.4. Local Joins

Foreign tables can be joined with local tables. The planner chooses the join location; not every join is pushed down.

### 23.5. Read Semantics

A foreign table query returns data according to remote transaction/snapshot behavior. Do not assume it shares the same freshness guarantees as a local cache or replica.

## 24. DML via postgres_fdw

`postgres_fdw` supports write operations on foreign tables when the remote relation and mapping permit them.

### 24.1. INSERT

~~~sql
INSERT INTO remote_sales.orders
    (order_id, customer_id, status, created_at, total_amount)
VALUES
    (9001, 101, 'new', now(), 125.50);
~~~

### 24.2. UPDATE

~~~sql
UPDATE remote_sales.orders
SET status = 'shipped'
WHERE order_id = 9001;
~~~

### 24.3. DELETE

~~~sql
DELETE FROM remote_sales.orders
WHERE order_id = 9001;
~~~

### 24.4. Remote Privileges

The remote role needs the corresponding INSERT/UPDATE/DELETE privileges. Both local table grants and remote table grants must be in place.

### 24.5. Updatability

Some foreign tables or queries are not updatable or are restricted based on relation/FDW options. Check the `postgres_fdw` documentation and EXPLAIN for the specific statement.

## 25. UPDATE and DELETE Row Identity

To update or delete a remote row, `postgres_fdw` must identify the row accurately.

### 25.1. Primary Key

A remote primary key provides stable row identification and is strongly recommended for foreign table definitions.

### 25.2. Row Identity

PostgreSQL provides a row identity mechanism for foreign tables; `postgres_fdw` uses appropriate columns to identify the remote tuple to update or delete.

### 25.3. Without a Primary Key

Some foreign tables can update/delete using columns chosen as row identity depending on behavior and version. Do not build write workloads around non-unique row identities.

### 25.4. Concurrent Changes

Remote rows may be modified concurrently by other sessions. Remote constraints and transaction isolation determine outcomes; handle serialization/conflict errors in the application.

### 25.5. Testing DML

Test inserts, updates, and deletes in staging, including concurrent updates, constraints, triggers, defaults, and remote generated values.

## 26. TRUNCATE and Foreign Tables

`postgres_fdw` supports TRUNCATE on foreign tables when FDW/table configuration allows it and the remote role holds the privilege.

### 26.1. Remote Truncation

TRUNCATE on a foreign table sends the corresponding operation to the remote relation. It can affect many rows immediately.

### 26.2. Privileges

The remote role needs TRUNCATE privilege on the remote table. The local user also needs the corresponding privilege on the foreign table.

### 26.3. Cascading Behavior

Do not assume local `TRUNCATE CASCADE` behaves identically to every local table relationship; foreign relations and remote dependencies have specific limitations.

### 26.4. Explicit Approval

TRUNCATE is destructive. Restrict grants and apply appropriate transaction and change controls.

### 26.5. Validation

Verify remote row counts, constraints, and downstream effects before incorporating TRUNCATE into an application workflow.

## 27. Local Constraints vs. Remote Constraints

A foreign table definition can declare columns and certain constraints, so you must understand which constraints are actually enforced.

### 27.1. Remote Constraints

Primary keys, unique constraints, foreign keys, CHECK constraints, and NOT NULL on the remote relation are enforced by remote PostgreSQL.

### 27.2. Local Metadata

A local foreign table does not automatically import full indexes or constraints as a mirror of the remote table. `IMPORT FOREIGN SCHEMA` primarily creates table/column definitions.

### 27.3. Planner Assumptions

If local constraints are declared on a foreign table, the planner may rely on them as metadata. Declare them only when you can guarantee they always hold remotely; the local FDW does not continuously verify remote changes.

### 27.4. Remote DDL Drift

If remote constraints or data semantics change, local assumptions can become invalid and lead to incorrect query results if the planner relies on them.

### 27.5. Data Integrity

Enforce authoritative constraints in the remote owner database. The local layer should reflect verified assumptions rather than inventing synthetic guarantees.


## 28. Predicate Pushdown

Predicate pushdown shifts filter conditions to the remote server so only the needed rows are returned.

### 28.1. Local vs. Remote Filtering

If a WHERE condition is pushed down, remote PostgreSQL filters before sending rows locally. Otherwise, the local executor may have to fetch many rows and filter afterward.

### 28.2. Shippable Expressions

`postgres_fdw` only pushes down expressions it determines are safe and semantically compatible remotely. Eligible built-in operators and functions can typically be pushed down.

### 28.3. Functions and Operators

Function volatility, collations, type semantics, and extension availability affect pushdown eligibility. Do not assume every function in a WHERE clause runs remotely.

### 28.4. Inspecting Remote SQL

Use `EXPLAIN VERBOSE` to inspect Remote SQL inside the Foreign Scan node. This is the practical way to see which filters are sent remotely.

### 28.5. Reducing Data Transfer

Predicate pushdown usually reduces network bytes, remote result size, and local executor work. Write clear predicates and avoid wrapping columns in unnecessary expressions.

## 29. Join Pushdown

`postgres_fdw` can execute joins remotely when foreign tables share the same server and the planner determines the join can be shipped safely.

### 29.1. Same Foreign Server

Foreign tables bound to the same foreign server are candidates for join pushdown. Tables from two different servers generally cannot be joined in a single remote query.

### 29.2. Safe Join Conditions

Join expressions and collations must have compatible semantics. Conditions containing local-only expressions can force the join to run locally.

### 29.3. Remote Join

When join pushdown succeeds, remote PostgreSQL executes the join and returns only the resulting rows needed locally.

### 29.4. Local/Remote Join

If the join is not pushed down, the local executor may fetch rows from each foreign relation and join them locally. Network transfer can spike sharply.

### 29.5. EXPLAIN Evidence

Inspect Foreign Scan/Remote SQL and row estimates. Check whether the remote query contains a JOIN or whether the local plan uses multiple independent foreign scans.

## 30. Aggregate, Sort, and LIMIT Pushdown

Several operations can run remotely to cut down transferred data volume.

### 30.1. Aggregate Pushdown

Eligible aggregate and grouping expressions can be shipped when semantics and safety rules are satisfied.

### 30.2. ORDER BY

Sorts can be pushed down when remote ordering semantics are compatible. Collation differences can block pushdown.

### 30.3. LIMIT/OFFSET

LIMIT/OFFSET can be pushed down under qualifying conditions. If the local executor still has to process rows before determining the final output, LIMIT may stay local.

### 30.4. HAVING

HAVING can be shipped with aggregates when all involved expressions are shippable.

### 30.5. Verify, Do Not Assume

Use `EXPLAIN VERBOSE` to inspect the actual Remote SQL. Concise query syntax does not prove every operation executes remotely.

## 31. EXPLAIN for Foreign Queries

EXPLAIN helps separate network transfer, remote execution, and local processing.

~~~sql
EXPLAIN (VERBOSE, COSTS, SETTINGS)
SELECT
    customer_id,
    count(*)
FROM remote_sales.orders
WHERE status = 'open'
GROUP BY customer_id;
~~~

### 31.1. Foreign Scan

The Foreign Scan node represents the local executor reading rows from a foreign data source.

### 31.2. Remote SQL

VERBOSE typically displays the SQL sent to the remote server. Check whether filters, joins, grouping, ordering, and limits were pushed down.

### 31.3. Estimated Rows

Compare Foreign Scan estimated rows with actual rows from `EXPLAIN ANALYZE` in a test environment. Inaccurate estimates can cause poor local join orders.

### 31.4. EXPLAIN ANALYZE

`EXPLAIN ANALYZE` actually executes the query and can generate load on the remote server. Run it only after considering workload, side effects, and remote capacity.

### 31.5. Remote-Side Plan

Local EXPLAIN does not always expose full details of the internal remote query plan. Run EXPLAIN and monitoring on the remote server with the captured Remote SQL when needed.


## 32. use_remote_estimate

`postgres_fdw` provides the `use_remote_estimate` option to ask the remote server for cost estimates rather than relying solely on local estimates.

~~~sql
ALTER SERVER sales_server
OPTIONS (ADD use_remote_estimate 'true');
~~~

### 32.1. Local Estimates

By default, the local planner estimates foreign table scans from available local metadata/statistics and FDW cost settings.

### 32.2. Remote Estimates

When `use_remote_estimate` is enabled, `postgres_fdw` sends EXPLAIN requests remotely to obtain estimates. This can improve planning for complex remote data distributions.

### 32.3. Planning Overhead

Remote EXPLAIN adds network round trips and remote planning CPU. For queries with many foreign scans or high QPS, planning latency can increase.

### 32.4. Statistics Locality

Running local `ANALYZE` on a foreign table samples from the remote server to build local statistics. Balance remote estimates and local statistics according to workload.

### 32.5. Choose by Benchmarking

Compare planning time, plan quality, execution time, and remote load before and after. Do not enable globally across all servers without measuring.

## 33. FDW Cost Options

`postgres_fdw` provides cost parameters so the local planner can estimate foreign scan expense.

### 33.1. fdw_startup_cost

Represents the startup cost of a foreign scan, including connection/remote query setup in the planner cost model.

### 33.2. fdw_tuple_cost

Represents the per-tuple cost of processing/transferring each row from the remote server to the local instance.

### 33.3. Cost Model Is Not a Runtime Guarantee

Costs are planner units, not milliseconds. Tune them based on observed network and remote behavior.

### 33.4. Per-Server Behavior

Options can be set on each foreign server to reflect differing latency and throughput across remote endpoints.

### 33.5. Avoid Forcing Plans

Misconfigured cost tuning can cause the planner to pick bad join orders or scan strategies. Validate with EXPLAIN and workload benchmarks.

## 34. fetch_size and Network Round Trips

`fetch_size` controls how many rows `postgres_fdw` retrieves per batch during a scan.

~~~sql
ALTER SERVER sales_server
OPTIONS (ADD fetch_size '500');
~~~

### 34.1. Batch Fetching

Fetching more rows per round trip reduces protocol and network overhead for large result sets.

### 34.2. Memory Trade-Off

Larger `fetch_size` increases memory used to buffer rows in the local backend. Under many concurrent foreign scans, memory pressure can rise.

### 34.3. Small Result Sets

For queries returning few rows, increasing `fetch_size` may yield little or no benefit.

### 34.4. Table-Level Override

You can set `fetch_size` on a specific foreign table if one relation has a different access pattern from others on the same server, per version option support.

### 34.5. Benchmark

Measure latency, network round trips, backend memory, and concurrency. No single `fetch_size` is optimal for every workload.

## 35. batch_size for Bulk Inserts

`batch_size` allows `postgres_fdw` to group multiple inserted rows into a single remote INSERT statement when conditions allow.

~~~sql
ALTER SERVER sales_server
OPTIONS (ADD batch_size '100');
~~~

### 35.1. Reducing Round Trips

Batched inserts reduce network exchanges and improve throughput for bulk DML.

### 35.2. Batch Limits

Excessively large batch sizes can increase memory usage, statement size, lock duration, and rollback cost.

### 35.3. Row Compatibility

Rows must meet batch execution criteria; triggers, defaults, RETURNING semantics, or query shapes can affect batching.

### 35.4. Table-Specific Setting

If only one foreign table receives bulk inserts, consider configuring `batch_size` on that table per supported options.

### 35.5. Test Remote Capacity

The remote server still performs writes, WAL generation, index maintenance, and triggers. Batching reduces communication overhead, not the actual remote write work.

## 36. Async-Capable Foreign Scans

Some PostgreSQL versions support asynchronous execution for foreign scans when the FDW and plan can overlap work asynchronously.

### 36.1. async_capable Option

`postgres_fdw` provides the `async_capable` option in supported versions. Verify defaults and behavior for your major version.

### 36.2. Parallel Foreign Scans

Asynchronous execution allows the local executor to overlap remote operations instead of waiting for each foreign scan sequentially.

### 36.3. Plan Conditions

Not every foreign scan can run asynchronously. Plan shape, foreign server association, and executor support affect eligibility.

### 36.4. Remote Concurrency

Async execution can run multiple remote queries simultaneously, increasing load on the remote server and network. Bound concurrency within capacity.

### 36.5. Validate Execution

Check EXPLAIN output and remote `pg_stat_activity` to confirm actual query concurrency. Do not enable it merely because the option exists.

## 37. ANALYZE on Foreign Tables

`ANALYZE` can sample foreign tables to populate local planner statistics.

~~~sql
ANALYZE remote_sales.orders;
~~~

### 37.1. Remote Sampling

`postgres_fdw` reads sample rows from the remote server via FDW sampling. This generates network and remote I/O and can impact the source workload.

### 37.2. Local pg_stats

Statistics are stored in the local database and help the local planner estimate foreign relations when remote estimates are off.

### 37.3. Freshness

If remote data changes rapidly, local stats can quickly go stale. Schedule `ANALYZE` appropriately or use remote estimates if benchmarks show a benefit.

### 37.4. Auto-Analyze

Autovacuum/analyze behavior for foreign tables depends on PostgreSQL version and FDW support; do not assume remote data changes automatically trigger local auto-analyze.

### 37.5. Sampling Cost

Analyzing foreign tables can transfer significant data over the network. Scope tables/columns carefully and monitor impact on the remote side.


## 38. Remote-Side Indexes and Query Optimization

Indexes live on the remote server. A local foreign table does not build physical indexes over remote data.

### 38.1. Remote Indexes

Create indexes on the remote relation matching pushed-down query patterns. Use remote EXPLAIN to verify the remote plan uses those indexes.

### 38.2. Local Index Metadata

Foreign tables do not store remote index definitions like local indexes. The local planner relies on estimates and FDW options instead.

### 38.3. Pushdown Before Indexing

An index helps only if the remote query receives predicates, joins, or sorts that can use it. If filtering stays local, the remote server may still scan many rows.

### 38.4. Remote Statistics

Run `ANALYZE` on remote tables so the remote planner has accurate statistics. Running local `ANALYZE` on a foreign table does not replace analyzing the source table.

### 38.5. Workload Isolation

Foreign queries can consume CPU and I/O on the source. Use dedicated remote roles, `statement_timeout`, resource controls, and workload scheduling.

## 39. Joining Foreign and Local Tables

Joins between a local table and a foreign table typically run locally, unless pushdown opportunities exist within a single remote server.

### 39.1. Local-to-Foreign Join

For example, joining local customers with foreign orders. The local executor may have to fetch one or both sides depending on the plan.

~~~sql
SELECT c.customer_name, o.order_id
FROM app.customers AS c
JOIN remote_sales.orders AS o
  ON o.customer_id = c.customer_id
WHERE c.region = 'north';
~~~

### 39.2. Data Transfer

If the remote filter does not receive local join keys, many rows may need to be transferred locally. Query shape and join order matter greatly.

### 39.3. Parameterized Paths

Under certain conditions, the planner can use parameterized foreign paths to push lookup keys/predicates to the remote server. Inspect the plan and Remote SQL.

### 39.4. Materialize Local Keys

For some workloads, staging a key set into a remote staging table or using ETL can outperform many round trips. Design consistency and lifecycle carefully.

### 39.5. Federation Boundary

If queries frequently join large volumes across multiple remote servers, consider materialized copies, replication, or a data integration pipeline.

## 40. Remote Query Timeouts and Connection Behavior

A foreign query can stall due to connection setup, remote execution, or data transfer.

### 40.1. connect_timeout

Limits how long establishing a connection via libpq can take. It does not limit remote query execution time once connected.

### 40.2. statement_timeout

Set appropriate timeouts on local sessions/roles and the remote role. Verify that cancellations actually take effect on both sides.

### 40.3. lock_timeout

Remote DML/DDL can wait on remote locks. `lock_timeout` must be applied where the statement executes.

### 40.4. Network Interruption

A dropped TCP connection can cause the local query to fail. Never automatically assume the remote transaction rolled back if the client missed the final response.

### 40.5. Retry Safety

Retrying SELECT is generally simpler than DML. For writes, the remote server may have committed while the local client lost the response; use idempotency keys, unique constraints, and reconciliation.

## 41. Transaction Behavior via postgres_fdw

`postgres_fdw` opens remote transactions to perform operations within a local transaction.

### 41.1. Remote Transaction

When a foreign table is accessed, the FDW opens a corresponding remote connection and transaction. Remote statements execute inside that transaction.

### 41.2. Local Commit/Rollback

Local COMMIT/ROLLBACK drives completion of the remote transaction via FDW transaction callbacks. Remote DML commits or rolls back with the local transaction under normal operating conditions.

### 41.3. Snapshot Behavior

Queries inside a local transaction observe remote data according to the transaction/snapshot behavior supported by `postgres_fdw` and the isolation level. Test semantics with specific isolation levels if the application relies on repeatable reads.

### 41.4. Savepoints/Subtransactions

The FDW supports subtransaction handling per PostgreSQL's mechanism; errors inside a subtransaction can roll back the corresponding work. Test edge cases and version behavior.

### 41.5. Not Distributed 2PC

`postgres_fdw` does not provide full distributed two-phase commit across multiple remote servers. A transaction writing across multiple remotes may not be atomic if one remote commits and another fails.

## 42. Multiple Foreign Servers in the Same Transaction

A local query can access multiple remote servers, but distributed transaction guarantees are limited.

### 42.1. Independent Remote Connections

Each foreign server and user mapping can use a separate connection. One local transaction can open multiple remote transactions.

### 42.2. Commit Ordering

Remote transactions are committed via FDW transaction handling. There is no 2PC coordinator guaranteeing atomic commit across all remote servers.

### 42.3. Partial Commit Risk

If one remote commits successfully and another fails, state can become inconsistent. Applications need a reconciliation or compensation strategy.

### 42.4. Local Rollback Limits

A local rollback cannot undo a remote transaction that has already committed.

### 42.5. Transaction Boundary Design

Avoid business-critical atomic writes across multiple remote servers. Prefer a single authoritative writer, outbox/saga patterns, or a replication pipeline.

## 43. Isolation Levels and Consistency

Consistency must be designed around how applications read and write via FDW.

### 43.1. Local Transaction Isolation

The local isolation level affects snapshots and concurrency semantics. `postgres_fdw` maps remote transaction behavior according to its implementation and version; check documentation and test when specific guarantees are needed.

### 43.2. Remote Concurrent Writers

Other remote applications can modify rows concurrently. A local foreign query does not block remote writers unless locking or transaction semantics apply.

### 43.3. Read-After-Write

After writing via a foreign table in the same transaction, subsequent remote reads can see the changes per transaction semantics. Verify with your actual isolation level and connection setup.

### 43.4. Cross-Database Snapshots

There is no synchronized global snapshot across multiple remote PostgreSQL servers. Queries joining multiple sources may observe different points in time.

### 43.5. Business Consistency

If business logic requires global consistency, rely on clear data ownership, event ordering, distributed coordination, or synchronized materialized data rather than FDW alone.

## 44. Remote Locks and Contention

DML through `postgres_fdw` acquires locks on the remote server and can wait on other remote transactions.

### 44.1. Lock Location

Foreign table DML does not merely lock local metadata; the actual write and locking occur on the remote relation.

### 44.2. Blocking Sessions

Inspect `pg_stat_activity` and `pg_locks` on the remote server to find blockers. A local session may appear to wait on network/remote responses.

### 44.3. Deadlocks

Deadlocks can occur between remote transactions or in combination with local locks. Design consistent lock ordering and short transaction scopes.

### 44.4. Lock Timeout

Set an appropriate `lock_timeout` on the remote role/session to prevent FDW writes from waiting indefinitely. Test timeout propagation.

### 44.5. Long Transactions

Long local transactions keep remote transactions and connections open. Commit early and avoid waiting on users or external services inside transactions.


## 45. Connection Caching

`postgres_fdw` can retain and reuse remote connections for the lifetime of a local backend process.

### 45.1. Reducing Connect Overhead

Reusing connections avoids TCP/TLS/authentication handshakes on every statement.

### 45.2. Connection per Mapping

Remote connections are keyed by foreign server and local user mapping/remote identity. A single local backend may open multiple connections across different servers and mappings.

### 45.3. Pool Multiplication

If an application has many local PostgreSQL backends, each backend can maintain its own remote connections. Total remote connections can grow higher than expected.

### 45.4. Credential Changes

After `ALTER USER MAPPING`, check how cached connections behave and establish new connections to confirm credential rotation takes effect.

### 45.5. Disconnect Management

`postgres_fdw` provides helper functions to inspect and close cached connections in supported versions, such as `postgres_fdw_get_connections` and `postgres_fdw_disconnect`. Check function signatures for your version before using them.

## 46. Managing Servers and User Mappings

DDL commands allow changing endpoints, credentials, and privileges without recreating every foreign table.

### 46.1. ALTER SERVER

~~~sql
ALTER SERVER sales_server
OPTIONS (SET host 'sales-db-new.example.internal');
~~~

Changing an endpoint requires verifying TLS, DNS, remote `pg_hba.conf`, and availability before opening workload traffic.

### 46.2. ALTER USER MAPPING

~~~sql
ALTER USER MAPPING FOR app_reader
SERVER sales_server
OPTIONS (SET password 'REPLACE_WITH_ROTATED_SECRET');
~~~

Execute through a secret-safe deployment path; never commit secret literals to migration repositories.

### 46.3. DROP USER MAPPING

~~~sql
DROP USER MAPPING FOR app_reader
SERVER sales_server;
~~~

This removes the local mapping; it does not drop the remote role.

### 46.4. DROP SERVER

~~~sql
DROP SERVER sales_server RESTRICT;
~~~

`RESTRICT` is the default and prevents dropping if foreign tables or user mappings still depend on it. `CASCADE` deletes dependent objects and requires an impact review.

### 46.5. Foreign Data Wrapper Lifecycle

`DROP FOREIGN DATA WRAPPER` is blocked while dependent servers exist unless `CASCADE` is used. Normally, remove the `postgres_fdw` extension only after handling all foreign servers and tables.

## 47. Monitoring on Local PostgreSQL

The local server shows which applications use FDWs and which queries are waiting or running.

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
~~~

### 47.1. Application Identity

Set `application_name` in both the local application and remote connection options to trace requests across both servers.

### 47.2. Query Duration

Local query duration includes planning/execution and may include remote connect, remote work, network transfer, and local processing.

### 47.3. Wait Events

Check `wait_event_type`/`wait_event` for your PostgreSQL version to identify backends waiting on resources or FDW-related activity where instrumented.

### 47.4. Connection Count

Count local sessions by app/user and compare against remote `pg_stat_activity`. Differences can stem from connection caching, pooling, and backend lifecycles.

### 47.5. Query Logging

Use `log_min_duration_statement` or tracing locally; avoid logging secrets or sensitive result values.

## 48. Monitoring on Remote PostgreSQL

The remote server is where pushed-down SQL executes and where data, locks, and indexes live.

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE application_name LIKE 'fdw-%'
   OR application_name = 'fdw-local-reporting'
ORDER BY query_start NULLS LAST;
~~~

### 48.1. Remote application_name

Configure `application_name` in foreign server options to make FDW sessions easier to identify.

### 48.2. Client Address

Verify whether connections originate from local PostgreSQL hosts, NAT/proxies, or application nodes.

### 48.3. Remote Query Plan

Extract Remote SQL from local `EXPLAIN VERBOSE` and run `EXPLAIN` on the remote server to inspect index usage, row estimates, and remote execution cost.

### 48.4. Remote Locks

Check `pg_locks`, `pg_blocking_pids`, and long transactions on the remote server. A local backend may be waiting on a blocker visible only remotely.

### 48.5. Source Workload Impact

Monitor remote CPU, disk I/O, buffer cache, connections, WAL, and p95/p99 latency of native remote applications. FDW traffic must not degrade the source service beyond budget.

## 49. Connection Count and Capacity Planning

An FDW places load on both databases and the network path between them.

### 49.1. Local Backends

Each local client backend can open remote connections per foreign server and user mapping as needed.

### 49.2. Remote Sessions

Estimate remote sessions from local backend process counts, active mappings, and connection reuse—not merely the number of application instances.

### 49.3. Remote max_connections

Preserve headroom for native applications, administration, replication, and FDW traffic. Prevent FDW traffic from exhausting all remote connection slots.

### 49.4. Pooling

A connection pooler in front of local PostgreSQL can reduce local backends; however, transaction/session pooling modes and FDW connection cache behavior must be tested.

### 49.5. Concurrency Caps

Cap parallel queries, application concurrency, and scheduled FDW jobs to protect remote capacity.

## 50. Schema Drift and Metadata Synchronization

Foreign table metadata does not update automatically when the remote schema changes.

### 50.1. Remote Add Column

Adding a column remotely does not add it to the local foreign table. Run `ALTER FOREIGN TABLE` or update/re-import definitions via a migration plan.

### 50.2. Remote Rename/Drop Column

The local foreign table still references the old remote column and queries may fail. Changes must be coordinated across both sides.

### 50.3. Type Changes

Remote type widening or narrowing may be incompatible with the local definition. Check precision, nullability, casts, and application expectations.

### 50.4. Migration Order

Use expand-and-contract: add the compatible remote structure, update the local foreign table, deploy consumers, and only then remove the legacy structure.

### 50.5. Schema Contract

Store remote/local DDL in source control and run automated drift detection. `IMPORT FOREIGN SCHEMA` is a one-time metadata creation step, not continuous schema sync.


## 51. Troubleshooting: Connection Refused or Timeout

### 51.1. DNS and Hostname

Verify the hostname resolves from the local PostgreSQL host/container. Resolution on a developer laptop does not prove the database server can resolve it.

### 51.2. Network/Firewall

Verify routing, security groups, firewalls, ports, and egress/ingress policies between both servers.

### 51.3. Remote Listen Addresses

Remote PostgreSQL must listen on an appropriate network interface, not only `localhost`.

### 51.4. pg_hba.conf

A rule must match the remote database, remote user, source address, and authentication method. Reload HBA after changes and inspect server logs.

### 51.5. TLS

Check the CA chain, certificate expiration, hostname verification, and client certificate requirements if using `verify-full` or cert auth.

## 52. Troubleshooting: Password Authentication Failed or Permission Denied

### 52.1. Local Mapping

Confirm the exact mapping exists for the local role running the query and the target foreign server.

### 52.2. Remote Identity

Check the remote username, password rotation state, role LOGIN attribute, and account validity.

### 52.3. Database/Schema/Table Grants

The remote role needs CONNECT, USAGE, and table privileges. DML requires the appropriate privileges for each operation.

### 52.4. Local Grants

The local role needs USAGE on the foreign server/schema and SELECT/INSERT/UPDATE/DELETE on the foreign table.

### 52.5. PUBLIC Mapping

If multiple users share a PUBLIC mapping, one remote identity may grant overly broad access. Create per-role mappings and audit access.

## 53. Troubleshooting: Relation/Column Does Not Exist

### 53.1. Remote Schema/Table Options

Verify the foreign table's `schema_name`/`table_name` options match the remote relation.

### 53.2. Column Mapping

Check `column_name` options, identifier casing, and local column definitions.

### 53.3. Remote search_path

`postgres_fdw` sends schema-qualified relation names based on foreign table metadata; do not rely on a remote session `search_path` to work around an incorrect mapping.

### 53.4. DDL Drift

The remote table may have renamed or dropped a column. Compare remote `information_schema.columns` against the local foreign table definition.

### 53.5. Permissions

Some access errors can manifest as an inability to access a relation. Check remote logs to distinguish a missing object from a privilege failure.

## 54. Troubleshooting: Slow Queries or Missing Pushdown

### 54.1. EXPLAIN VERBOSE

Inspect Remote SQL to see which filters, joins, sorts, or aggregates are actually shipped.

### 54.2. Expression Shippability

Check functions/operators, volatility, collations, and extension compatibility. A single local-only expression can force execution locally.

### 54.3. Remote EXPLAIN

Run the captured Remote SQL on the remote server with representative parameters. Inspect remote indexes, statistics, joins, and row estimates.

### 54.4. Network Transfer

Estimate rows and bytes returned. Raising `fetch_size` reduces round trips but does not fix a query returning too many rows.

### 54.5. Local Join Order

The local planner may pick a poor join order if foreign estimates are inaccurate. Test `use_remote_estimate` or `ANALYZE` on the foreign table in staging and benchmark.

## 55. Troubleshooting: Type Mismatch and Semantic Errors

### 55.1. Numeric Precision

Local numeric precision and scale must accommodate remote values. A narrower local type can cause overflow or rounding errors.

### 55.2. Timestamp Semantics

Distinguish `timestamp without time zone` from `timestamptz`. Do not implicitly shift timezones if business logic requires preserving wall-clock time.

### 55.3. Enum/Domain/Custom Types

Extension-defined types require compatible type support on both local and remote servers and mapping support from the FDW.

### 55.4. Collation

Text comparison and sorting can differ across collation providers and versions. Pushdown is safe only when semantics match.

### 55.5. Null/Default Behavior

Remote defaults, generated columns, and triggers execute remotely. Local foreign table defaults do not automatically reflect remote default changes.

## 56. Troubleshooting: Ambiguous Remote Transaction or Commit Outcome

### 56.1. Client Disconnect

If the network drops after the remote server receives COMMIT but before the local server receives the response, the outcome is ambiguous to the caller.

### 56.2. Inspecting Remote State

Use transaction/business identifiers, audit records, and remote query logs to determine whether the change committed.

### 56.3. Idempotent Writes

Use unique keys/request IDs and proper conflict handling for safe retries. Never blindly retry a payment or order write.

### 56.4. Multiple Remote Servers

If a local transaction writes to multiple remotes, some may commit before an error occurs on another server. Reconciliation or compensating actions are required.

### 56.5. Application Contract

Expose uncertain/in-progress operation states and use a recovery worker rather than simply reporting failure and issuing a duplicate write.


## 57. Foreign Server and Foreign Table Options

`postgres_fdw` supports options at multiple levels; each option has its own scope and precedence by PostgreSQL version.

### 57.1. use_remote_estimate

Can be set on a server or foreign table to control how the planner gathers estimates. Table-level settings are useful when one relation behaves differently from others.

### 57.2. fetch_size

Can be set on a server or table to control rows fetched per batch. Check option inheritance and overrides in your version's documentation.

### 57.3. updatable

Controls whether a foreign table is considered updatable by `postgres_fdw`. Even when enabled, remote grants and relation capabilities determine whether writes succeed.

### 57.4. truncatable

The `truncatable` option controls whether TRUNCATE is permitted on a foreign table. Enable only when the remote operation is authorized and under change control.

### 57.5. async_capable and batch_size

These options control asynchronous execution and batched inserts on supported versions. Check compatibility, defaults, and impact before applying them.

## 58. Extensions Option for Function Pushdown

`postgres_fdw` provides the `extensions` server option to declare extensions whose functions/operators may be shipped remotely when compatible.

~~~sql
ALTER SERVER sales_server
OPTIONS (ADD extensions 'some_extension');
~~~

### 58.1. Matching Extensions on Both Sides

Listed extensions must be compatibly installed on both local and remote servers. Semantics and versions must align so execution yields identical results.

### 58.2. Function Safety

Only expressions satisfying shippability and safety rules are shipped. The `extensions` option does not force every extension function to run remotely.

### 58.3. Security Implications

Remote function execution can have different privileges and side effects from local execution. Review code, ownership, and remote role permissions.

### 58.4. Upgrade Compatibility

When upgrading extension versions, ensure local and remote versions stay aligned and plan behavior does not change unexpectedly.

### 58.5. Verify Remote SQL

Use `EXPLAIN VERBOSE` and remote logs to verify that the function is actually pushed down.


## 59. End-to-End Example: Configuring a Read-Only Integration

This scenario creates local foreign tables to read data from a remote `sales` database.

### 59.1. On the Remote Server

The DBA creates the `fdw_sales_reader` role and grants CONNECT, schema USAGE, and SELECT on the tables to expose.

### 59.2. On the Local Server

Install the extension and create the server:

~~~sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;

CREATE SERVER sales_server
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'sales-db.example.internal',
    port '5432',
    dbname 'sales',
    sslmode 'verify-full',
    application_name 'fdw-local-reporting'
);
~~~

### 59.3. Creating the User Mapping

~~~sql
CREATE USER MAPPING FOR reporting_app
SERVER sales_server
OPTIONS (
    user 'fdw_sales_reader',
    password 'REPLACE_WITH_SECRET'
);
~~~

Secrets must be injected from a credential management system, never hard-coded into repositories.

### 59.4. Creating the Schema and Importing

~~~sql
CREATE SCHEMA remote_sales AUTHORIZATION db_owner;

IMPORT FOREIGN SCHEMA public
LIMIT TO (customers, orders)
FROM SERVER sales_server
INTO remote_sales;
~~~

### 59.5. Granting Local Privileges

~~~sql
GRANT USAGE ON FOREIGN SERVER sales_server TO reporting_app;
GRANT USAGE ON SCHEMA remote_sales TO reporting_app;
GRANT SELECT ON ALL TABLES IN SCHEMA remote_sales TO reporting_app;
~~~

Then test using the actual `reporting_app` role and verify in remote `pg_stat_activity` that the expected remote identity and `application_name` appear.

## 60. End-to-End Example: Manual Foreign Table and DML

This scenario demonstrates a foreign table writing to a remote relation.

### 60.1. Remote Permissions

The remote role needs CONNECT, schema USAGE, and INSERT/UPDATE/DELETE on the target table. Identify unique keys and constraints on the remote table.

### 60.2. Local Mapping

Create a dedicated mapping for the local writer role using a remote account with only the required privileges.

### 60.3. Foreign Table Definition

~~~sql
CREATE FOREIGN TABLE remote_sales.order_updates (
    order_id bigint,
    status text,
    updated_at timestamptz
)
SERVER sales_server
OPTIONS (
    schema_name 'public',
    table_name 'order_updates',
    updatable 'true'
);
~~~

### 60.4. DML Test

~~~sql
INSERT INTO remote_sales.order_updates
    (order_id, status, updated_at)
VALUES
    (9001, 'processed', now());

UPDATE remote_sales.order_updates
SET status = 'shipped'
WHERE order_id = 9001;
~~~

### 60.5. Validate Remote Outcome

Query the remote table directly using a remote DBA/read role and verify row values. Check transaction commits, triggers, constraints, and audit records.

## 61. Example: Checking Pushdown and Remote Plan

### 61.1. Local Query

~~~sql
EXPLAIN (VERBOSE, COSTS)
SELECT order_id, total_amount
FROM remote_sales.orders
WHERE customer_id = 101
  AND status = 'open'
ORDER BY created_at DESC
LIMIT 20;
~~~

### 61.2. Inspect Remote SQL

Check the Foreign Scan node to see whether Remote SQL includes the appropriate WHERE/ORDER BY/LIMIT clauses.

### 61.3. Remote EXPLAIN

Run the Remote SQL on the remote server with an appropriate role to inspect index scans, row estimates, and sort behavior.

### 61.4. Test Fetch Size

Run the workload with several `fetch_size` values in staging while keeping dataset, parameters, and concurrency comparable.

### 61.5. Compare the Full Path

Record local planning time, execution time, rows/bytes transferred, remote CPU/I/O, and native remote workload latency.

## 62. Lab: Connecting Two PostgreSQL Databases

Use two instances or databases in a lab environment. One acts as the remote source and the other as the local consumer.

### 62.1. Prepare the Remote Schema

Create `customers`/`orders` tables, insert representative rows, create indexes, and create a read-only role.

### 62.2. Prepare Network/Authentication

Verify DNS/host, port, TLS, and `pg_hba.conf` for the local PostgreSQL host.

### 62.3. Install postgres_fdw

Install the required server package and run `CREATE EXTENSION` in the local database.

### 62.4. Create Server/Mapping/Table

Create the foreign server, user mapping, local schema, and run `IMPORT FOREIGN SCHEMA ... LIMIT TO`.

### 62.5. Query

Run SELECT and join foreign tables; confirm via remote activity/logs that data is served from the remote instance.

## 63. Lab: Pushdown and Query Tuning

### 63.1. Query with a Selective Filter

Create a remote index on the filter column and run `EXPLAIN VERBOSE`.

### 63.2. Predicate Pushdown

Verify that WHERE appears in Remote SQL and that the remote plan uses the expected index.

### 63.3. Join Pushdown

Join two foreign tables on the same server and check whether Remote SQL contains a JOIN.

### 63.4. Local/Remote Join

Join a local table with a foreign table; observe row transfer and the local plan.

### 63.5. Tune fetch_size/Estimates

Test `fetch_size` and `use_remote_estimate` in staging, comparing planning/execution time, network traffic, and remote load.

## 64. Lab: Security and Failure Handling

### 64.1. Least-Privilege Role

Create a remote read role permitted to SELECT only on a subset of schemas/tables.

### 64.2. Local Authorization

Create a dedicated local role mapping and GRANT USAGE/SELECT only on the necessary server, schema, and tables.

### 64.3. Negative Tests

Attempt to query an ungranted table and confirm the remote server rejects it. Test a user lacking local USAGE to confirm local admission control.

### 64.4. Network Failure

In the lab, temporarily stop the remote endpoint or block the port, then run a query to observe timeout/error behavior. Restore networking afterward.

### 64.5. DML Retry

Simulate a lost response after a write if your environment permits; build idempotency/reconciliation logic and avoid blind retries.


## 65. Common Mistakes When Using postgres_fdw

1. Thinking a foreign table stores a local copy of remote data.
2. Forgetting to run `CREATE EXTENSION` in the target local database.
3. Installing the package for the wrong PostgreSQL major version.
4. Creating a foreign server whose remote host is unreachable from the local database host.
5. Confusing local roles with remote users.
6. Forgetting `CREATE USER MAPPING` for the actual application role.
7. Using a PUBLIC mapping backed by a remote superuser.
8. Forgetting `GRANT USAGE ON FOREIGN SERVER`.
9. Granting local SELECT while forgetting remote CONNECT/schema/table privileges.
10. Putting passwords into server options or source control.
11. Assuming `IMPORT FOREIGN SCHEMA` syncs DDL automatically.
12. Failing to verify type and column mappings.
13. Assuming every WHERE, JOIN, and ORDER BY pushes down.
14. Not checking Remote SQL in `EXPLAIN VERBOSE`.
15. Increasing `fetch_size` without measuring memory and concurrency.
16. Enabling `use_remote_estimate` without accounting for planning overhead.
17. Allowing FDW reporting to overload a remote OLTP source.
18. Overlooking remote session counts caused by local backend/pool multiplication.
19. Assuming multiple remote servers have distributed atomic commits.
20. Retrying DML after a network error without checking the remote commit outcome.
21. Monitoring only the local database while ignoring remote locks, CPU, and I/O.
22. Forgetting to install shared libraries on standby/DR nodes.
23. Having no schema drift process between local foreign tables and remote tables.
24. Using FDW for bulk federation without benchmarking against replication/ETL.

## 66. Practice Exercises

### Exercise 1 — Concept

What role does a Foreign Data Wrapper serve?

**Answer:** It provides an interface enabling PostgreSQL to access external data sources.

### Exercise 2 — Foreign Server

What does a foreign server describe?

**Answer:** The endpoint and connection/planning options for a foreign data source.

### Exercise 3 — User Mapping

Which identities does a user mapping connect?

**Answer:** A local PostgreSQL role with a remote user and authentication options.

### Exercise 4 — Foreign Table

Does a foreign table store remote rows in the local database?

**Answer:** No; it is metadata representing the remote relation.

### Exercise 5 — Extension

Where must `CREATE EXTENSION postgres_fdw` be run?

**Answer:** In the local database that will contain the foreign servers and tables.

### Exercise 6 — Server Options

What do `host`/`port`/`dbname` specify?

**Answer:** The remote PostgreSQL endpoint and target database.

### Exercise 7 — Remote Role

What privileges does a remote role need to read a table?

**Answer:** CONNECT on the database, USAGE on the schema, and SELECT on the table.

### Exercise 8 — Local Privilege

What is `GRANT USAGE ON FOREIGN SERVER` used for?

**Answer:** To permit a local role to use the foreign server.

### Exercise 9 — Import

Does `IMPORT FOREIGN SCHEMA` copy data?

**Answer:** No; it creates local foreign table definitions.

### Exercise 10 — Column Mapping

What does the `column_name` option do?

**Answer:** Maps a local column name to a remote column name.

### Exercise 11 — Schema

Must the local schema match the remote schema?

**Answer:** No; `INTO` specifies the local schema, while `schema_name` specifies the remote schema.

### Exercise 12 — Pushdown

How does predicate pushdown help?

**Answer:** It filters rows remotely before transferring them to the local server.

### Exercise 13 — Join Pushdown

What opportunity exists when two foreign tables share the same server?

**Answer:** The planner can push the join down to the remote server if expressions are safe.

### Exercise 14 — EXPLAIN

Which option displays Remote SQL?

**Answer:** `EXPLAIN VERBOSE`.

### Exercise 15 — Remote Estimate

What trade-off does `use_remote_estimate` introduce?

**Answer:** Estimates match the remote server better, but planning incurs extra remote round trips and CPU.

### Exercise 16 — fetch_size

What can increasing `fetch_size` improve?

**Answer:** It reduces network round trips when fetching many rows, at the trade-off of higher memory usage.

### Exercise 17 — batch_size

Which workload benefits from `batch_size`?

**Answer:** Multi-row INSERT operations that can be grouped into batches.

### Exercise 18 — ANALYZE

Where does `ANALYZE` on a foreign table store statistics?

**Answer:** In the local database for use by the local planner.

### Exercise 19 — Remote Indexes

Where are indexes created for a foreign table?

**Answer:** On the remote relation.

### Exercise 20 — DML

What happens if the remote role lacks the UPDATE privilege?

**Answer:** An UPDATE via the foreign table will be rejected by the remote server.

### Exercise 21 — Transaction

Does `postgres_fdw` provide distributed 2PC atomic commits across multiple remote servers?

**Answer:** No; multi-remote commits can partially commit upon failure.

### Exercise 22 — Retry

Why should DML not be blindly retried after a network error?

**Answer:** The remote server may have committed even though the local client never received the response.

### Exercise 23 — Connection Count

Why can remote sessions outnumber local application instances?

**Answer:** Each local backend/mapping can hold its own remote connection.

### Exercise 24 — Schema Drift

Does renaming a remote column automatically update the local foreign table?

**Answer:** No; local metadata must be migrated in coordination.

### Exercise 25 — Monitoring

Which sides must be monitored?

**Answer:** Local PostgreSQL, remote PostgreSQL, and the network/application path.

### Exercise 26 — TLS

What does `sslmode` `verify-full` verify?

**Answer:** The TLS certificate chain and hostname identity.

### Exercise 27 — PUBLIC Mapping

What is the risk of a PUBLIC mapping?

**Answer:** Multiple local users may share the same remote identity and privileges.

### Exercise 28 — Server Lifecycle

What does `DROP SERVER ... RESTRICT` do?

**Answer:** Refuses to drop the server while dependent foreign tables or user mappings exist.

### Exercise 29 — Async

Does `async_capable` mean every foreign query runs in parallel?

**Answer:** No; only plans and operations meeting executor and FDW eligibility criteria leverage async execution.

### Exercise 30 — Choosing Technology

When should you consider replication/ETL instead of FDW?

**Suggestion:** When you need a low-latency local copy, high-volume scans, resilience during remote outages, or consistency/transaction semantics that FDW cannot provide.


## 67. postgres_fdw Deployment Checklist

- [ ] Is the extension package matching the PostgreSQL major version installed?
- [ ] Was `CREATE EXTENSION` executed in the correct local database?
- [ ] Were remote host/port/dbname and TLS verified from the local server?
- [ ] Does the remote role have least-privilege grants?
- [ ] Are foreign server options free of secrets?
- [ ] Does the user mapping match the intended local role and remote user?
- [ ] Are passwords/certificates managed via a secret process?
- [ ] Are local server/schema/table USAGE and object grants configured?
- [ ] Do foreign table columns, types, and schema/table mappings match the remote side?
- [ ] Is the `IMPORT FOREIGN SCHEMA` scope appropriately restricted?
- [ ] Does `EXPLAIN VERBOSE` confirm the expected pushdown?
- [ ] Have remote query and index plans been verified?
- [ ] Have fetch/batch/estimate options been benchmarked?
- [ ] Do connection counts and remote capacity have sufficient headroom?
- [ ] Are monitoring and logging ready on both local and remote servers?
- [ ] Do schema drift, credential rotation, and package upgrades have runbooks?

## 68. Operations and Troubleshooting Checklist

- [ ] Are local query errors correlated with remote logs?
- [ ] Are DNS/network/firewall/TLS checked when connections fail?
- [ ] Are `pg_hba.conf` and remote grants verified?
- [ ] Are local user mappings and remote identities correct?
- [ ] Are remote locks and long transactions checked?
- [ ] Are Remote SQL and plans inspected when queries are slow?
- [ ] Are data transfer/result sizes and `fetch_size` measured?
- [ ] Is transaction commit outcome verified after network errors?
- [ ] Do DML retries have idempotency and reconciliation?
- [ ] Are remote session counts compared against local backends?
- [ ] Is foreign table metadata updated alongside remote DDL?
- [ ] Do HA/standby/DR nodes have the required packages and credentials?
- [ ] Do backup/restore and failover rehearsals cover foreign objects?
- [ ] Is the lifecycle of extensions, servers, and mappings inventoried and audited?

## 69. Quick Reference Table

| Component | Role |
|---|---|
| FDW | Interface for accessing foreign data |
| postgres_fdw | FDW for remote PostgreSQL |
| CREATE EXTENSION | Installs `postgres_fdw` in the local database |
| CREATE SERVER | Defines the remote endpoint |
| CREATE USER MAPPING | Maps a local role to a remote identity |
| CREATE FOREIGN TABLE | Defines a remote relation in the local catalog |
| IMPORT FOREIGN SCHEMA | Generates foreign tables from a remote schema |
| pg_foreign_data_wrapper | Catalog of FDW objects |
| pg_foreign_server | Catalog of foreign servers |
| pg_user_mapping | Catalog of user mappings |
| pg_foreign_table | Catalog of foreign table options |
| pg_extension | Extension installations in the database |
| GRANT USAGE ON FOREIGN SERVER | Permits a local role to use the server |
| schema_name/table_name | Selects the remote relation |
| column_name | Maps local and remote columns |
| use_remote_estimate | Obtains planner estimates from the remote server |
| fdw_startup_cost | Startup cost model parameter |
| fdw_tuple_cost | Per-tuple cost model parameter |
| fetch_size | Rows per fetch batch |
| batch_size | Rows per INSERT batch when supported |
| async_capable | Enables async foreign execution when supported |
| updatable | Controls DML capability per FDW |
| truncatable | Controls TRUNCATE support |
| EXPLAIN VERBOSE | Shows Remote SQL |
| ANALYZE foreign table | Creates local planner statistics |
| postgres_fdw_get_connections | Inspects cached remote connections in supported versions |
| postgres_fdw_disconnect | Closes cached connections in supported versions |
| application_name | Identifies FDW sessions on the remote server |
| Pushdown | Executes filters/joins/aggregates remotely |
| User mapping | Remote authentication mapping |
| Foreign table | Local metadata representing a remote relation |
| Distributed 2PC | Not fully provided by `postgres_fdw` for multi-remote atomic commits |

## 70. Conclusion

**`postgres_fdw` enables querying remote PostgreSQL data via foreign tables, but success depends on both local and remote configuration.** The foreign server defines the endpoint, the user mapping sets the remote identity, and the foreign table describes the relation and columns in the local catalog. `CREATE EXTENSION` only enables the FDW inside the local database; the package must be present on the server and the remote role must hold proper privileges. `IMPORT FOREIGN SCHEMA` creates metadata—it neither copies data nor automatically syncs remote DDL.

Performance depends on predicate/join/aggregate pushdown, remote indexes and statistics, planner estimates, network latency, result size, `fetch_size`, and concurrency. `EXPLAIN VERBOSE` reveals Remote SQL; remote EXPLAIN and `pg_stat_activity` show how the source server executes it. Running local `ANALYZE` on a foreign table equips the local planner with statistics but does not replace `ANALYZE` on the remote server. Monitor both sides and account for the remote sessions opened by local backends.

`postgres_fdw` supports many read/write operations and transaction coordination in normal scenarios, yet it does not provide full distributed two-phase commit for atomic commits across multiple remote servers. Network failures can leave write outcomes ambiguous; applications require idempotency and reconciliation. If a workload demands data locality, high-volume scans, global consistency, or resilience independent of remote availability, evaluate replication, materialization, or ETL instead.

Operational principle: **design remote identities with least privilege, verify schema/column mappings, confirm pushdown with EXPLAIN, benchmark networking and concurrency, monitor the remote source, and prepare commit-outcome handling before using FDWs for critical writes.**
