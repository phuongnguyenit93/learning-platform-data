# Database Links and Querying Objects from Another Database in Oracle

## 1. What Is a Database Link Used For?

A system may split data across multiple Oracle Databases for organizational, security, scaling, regional partitioning, or historical deployment reasons. Applications sometimes need to read data in another database without copying the entire dataset into the current database.

A **Database link (DB link)** is an object in Oracle that allows a session in the local database to connect to a remote database and reference remote objects in SQL. After creating the link, a query can read a remote table using the syntax `schema.table@database_link`.

Example:

```sql
SELECT customer_id, customer_name
FROM sales.customers@sales_link
WHERE status = 'ACTIVE';
```

The statement is issued from the local database, but the `SALES.CUSTOMERS` table resides in the remote database identified by `SALES_LINK`.

Database links are commonly used to:
- Query reference data located in another database.
- Combine local and remote data in a single SQL statement.
- Transfer data between two databases using `INSERT ... SELECT`.
- Call certain packages/procedures in a remote database.
- Support reporting or integration across Oracle systems.

DB links allow remote data access via SQL, but they introduce dependencies on the network, listener, service, credentials, and remote database availability. A local SQL statement can fail if the remote database is unreachable. Therefore, privileges, performance, transactions, and operations must be designed carefully.

This lesson belongs to the **Database Engine Relational Oracle** module, **Distributed Integration** chapter, focusing on **Database links and querying objects from another database**.

## 2. Local and Remote Connection Model

When a local session uses a DB link, the local database acts as the initiator of the connection to the remote database. The connection is not established directly from the machine running SQL Developer or the client application to the remote database in the usual way; the local database server itself initiates the outbound connection.

```text
Application / SQL Developer
          |
          | SQL with @sales_link
          v
Local Oracle Database
          |
          | Oracle Net connection
          | credentials per DB link
          v
Remote Oracle Database
          |
          v
REMOTE_SCHEMA.REMOTE_TABLE
```

Components:
- **Local database:** where the session is connected and executes the initial SQL statement.
- **Database link:** object containing routing information and authentication type for the remote database.
- **Oracle Net service name/connect descriptor:** specifies the host, listener, port, and service on the remote side.
- **Remote database:** the target database.
- **Remote user:** the identity used to access remote objects.
- **Remote object:** table, view, or other object referenced via the link.

### 2.1. When Is the Link Opened?

Typically, when a local session uses a DB link for the first time, Oracle opens a connection/session to the remote database. The remote connection can remain open for the lifetime of the local session to be reused.

A single local session can use multiple DB links. Each link can establish a connection to a different remote database. If many local sessions access a link concurrently, the remote database may receive a corresponding number of sessions.

### 2.2. A DB Link Is Not a Data Copy

A DB link does not automatically synchronize or replicate data. When querying through a link, Oracle accesses the remote database at execution time. If the remote database stops operating or the network is disrupted, queries depending on the link may fail.

If local data is needed for fast querying and reduced runtime dependency on the remote database, evaluate materialized views, ETL, replication, or CDC mechanisms instead of using a DB link for every request.

## 3. Types of Database Links

Oracle supports several scopes and authentication types for database links. Two common ways to classify them are ownership scope and the remote identity used.

### 3.1. Private Database Link

A private database link belongs to the schema that created the link. Only the owner of the link can use it under normal privileges.

For example, user `APP_OWNER` creates `SALES_LINK`; other schemas cannot automatically use this private link.

Advantages:
- Narrow scope of usage.
- Each application/schema can have its own credentials and privileges.
- Easy to identify the responsible owner.

This is usually the more appropriate choice for integration belonging to a single application or schema.

### 3.2. Public Database Link

A public database link is created at the database-wide scope and can be used by users with appropriate access privileges.

Example:

```sql
CREATE PUBLIC DATABASE LINK reporting_link
CONNECT TO report_reader IDENTIFIED BY "password_placeholder"
USING 'REPORTING_SERVICE';
```

A public link is convenient when multiple schemas share one endpoint, but it broadens the usage scope and may cause multiple applications to share a single remote identity. Only create one when there is a clear requirement, an operational owner, and an appropriate privilege policy.

### 3.3. Fixed-User Database Link

A fixed-user link always connects to the remote database using a username declared in the link.

Example:

```sql
CREATE DATABASE LINK sales_link
CONNECT TO sales_reader IDENTIFIED BY "password_placeholder"
USING 'SALES_SERVICE';
```

Regardless of which local user logs into a session permitted to use the link, the remote connection always uses the `SALES_READER` identity.

This is a common pattern for applications that need to access a stable set of remote objects. The remote account should only have necessary privileges, such as `SELECT` on specific views rather than broad schema privileges.

### 3.4. Connected-User or Current-User Database Link

A connected-user link uses the current user's identity to authenticate against the remote database according to mechanisms supported by Oracle. A current-user link can be explicitly declared:

```sql
CREATE DATABASE LINK hr_link
CONNECT TO CURRENT_USER
USING 'HR_SERVICE';
```

This approach suits architectures with centrally managed user identities, such as enterprise/global users and external authentication configured in Oracle. It does not mean any local username automatically exists and can log in to the remote database.

You must verify authentication configuration, directory/enterprise users, privileges, and Oracle versions before choosing this model.

### 3.5. Choosing a Link Type

| Requirement | Option Typically Considered |
|---|---|
| Only one application schema needs remote access | Private link |
| Multiple schemas genuinely need to share a link | Public link, after risk assessment |
| A read-only remote service account | Private fixed-user link |
| Need to preserve user identity across databases | Appropriate current-user/enterprise authentication |
| Need privilege isolation between applications | Separate private links and remote accounts |

Do not choose a public link merely for ease of configuration. The broader the access scope, the harder auditing, control, and rotation become.

## 4. Prerequisites and Privileges to Create a Database Link

A user creating a private DB link needs the `CREATE DATABASE LINK` system privilege. Creating a public link requires `CREATE PUBLIC DATABASE LINK`.

A DBA can grant the privilege per policy:

```sql
GRANT CREATE DATABASE LINK TO app_owner;
```

To create a public link:

```sql
GRANT CREATE PUBLIC DATABASE LINK TO integration_admin;
```

Do not grant the privilege to create public links to every developer or service account. This privilege can create connection paths to other databases and must be managed as a system integration privilege.

In addition to local database privileges, prepare:
- The remote database is running and reachable from the local database server.
- The listener is listening on the correct endpoint.
- The service name is accurate.
- A valid Oracle Net naming/connect descriptor.
- The remote account exists and is not locked/expired.
- The remote account has privileges on the target objects to query.
- Firewall/network policy allows connections from the local host to the remote listener.
- TLS/network encryption configured per security requirements.

## 5. Configuring Oracle Net for a Database Link

A DB link uses a connect string or service name in the `USING` clause.

For example, `USING 'SALES_SERVICE'` references an Oracle Net service name resolvable on the local database server.

An illustrative entry in `tnsnames.ora`:

```text
SALES_SERVICE =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = sales-db.example.internal)
      (PORT = 1521)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = salespdb.example.internal)
    )
  )
```

The values above are examples only. Use the actual hostname, port, and service name of your environment.

### 5.1. Where Is the TNS Alias Resolved?

Because the DB link connection is initiated from the local database server, the `SALES_SERVICE` alias must be resolvable within the Oracle Net environment used by the local database server. An alias existing on a developer's workstation that does not exist or is incorrect on the database server is not sufficient for the DB link to work.

Check:
- `TNS_ADMIN` or the Oracle Net configuration location of the database service.
- `tnsnames.ora` on the local database host.
- DNS/firewall from the local database host to the remote host.
- Listener and service registration on the remote side.
- Wallet/TLS configuration if used.

### 5.2. Service Name and PDB

In a multitenant environment, the service name can identify the target PDB. A DB link pointing to the wrong service may connect successfully yet access the wrong container or schema.

Confirm the target service with an identification query:

```sql
SELECT name, db_unique_name, open_mode
FROM v$database;
```

This query runs on the remote database over the link if the user has privilege to read the view. There is no space between `@` and the link name:

```sql
SELECT name, db_unique_name, open_mode
FROM v$database@sales_link;
```

The remote user might not have privilege to read `V$DATABASE`; in that case, use `GLOBAL_NAME` or a granted verification view.

### 5.3. Testing Connectivity Before Creating the Link

The DBA can use appropriate Oracle Net tools on the local host to verify the alias and listener. After creating the link, querying `DUAL` from remote is the simplest test.

Do not test only from a client workstation and conclude that the local database server can also connect. The two machines may have different DNS, firewall, or Oracle Net configurations.

## 6. Creating a Private Database Link

Example of creating a fixed-user private link in the `APP_OWNER` schema:

```sql
CREATE DATABASE LINK sales_link
CONNECT TO sales_reader
IDENTIFIED BY "password_placeholder"
USING 'SALES_SERVICE';
```

In this example:
- `sales_link`: local DB link name.
- `sales_reader`: remote username.
- `password_placeholder`: illustrative placeholder, not a real credential.
- `SALES_SERVICE`: Oracle Net service name of the remote database.

Passwords in DDL can appear in scripts, SQL history, deployment output, or audit/log tools depending on how execution is performed. In real deployments, pass credentials through a protected administrative channel, restrict history/output, and never commit DDL containing passwords to a repository.

Oracle stores fixed-user database link credentials using the database's protection mechanisms; do not design processes around querying plaintext passwords back from the data dictionary.

### 6.1. Creating a Link with Current User

```sql
CREATE DATABASE LINK hr_link
CONNECT TO CURRENT_USER
USING 'HR_SERVICE';
```

This model only works when remote authentication and current-user identity are properly configured. Do not use it as a way to bypass provisioning accounts/privileges on the remote side.

### 6.2. Creating a Public Link

```sql
CREATE PUBLIC DATABASE LINK shared_reporting_link
CONNECT TO report_reader
IDENTIFIED BY "password_placeholder"
USING 'REPORTING_SERVICE';
```

A public link has broader visibility. You must control which users can reference the link and what privileges the remote account holds.

### 6.3. Verifying the Newly Created Link

```sql
SELECT db_link,
       username,
       host,
       created
FROM user_db_links
ORDER BY db_link;
```

The `USER_DB_LINKS` view lists links owned by the current user. You can use `ALL_DB_LINKS` or `DBA_DB_LINKS` if privileged to see the corresponding scope.

Metadata views do not display plaintext passwords. Still, protect usernames, hosts, and endpoint details if they are classified as sensitive data in your organization.

## 7. Testing a Database Link

### 7.1. Querying Remote DUAL

```sql
SELECT 1
FROM dual@sales_link;
```

If it returns one row, the local session can open the link and execute a basic remote query.

### 7.2. Checking the Global Database Name

```sql
SELECT *
FROM global_name@sales_link;
```

The result helps identify the global database name on the remote side. This is useful when checking `GLOBAL_NAMES` or link name mismatch errors.

### 7.3. Checking the Remote User

You can verify the remote identity with:

```sql
SELECT USER
FROM dual@sales_link;
```

For a fixed-user link, the result is typically the remote username declared in the link. This confirms the link is using the expected identity.

### 7.4. Checking Remote Objects

```sql
SELECT owner,
       table_name
FROM all_tables@sales_link
WHERE owner = 'SALES'
ORDER BY table_name;
```

The `ALL_TABLES` view only shows objects the remote user can see according to its privileges. If an object does not appear, check the owner, privileges, and schema name on the remote side.

### 7.5. Checking Service/Container

If the remote database is a CDB/PDB, confirm the DB link connects to the right service and container. A link that connects successfully does not guarantee it points to the right business PDB.

## 8. Querying Remote Objects

General syntax:

```sql
object_name@database_link
```

With a schema-qualified object:

```sql
schema_name.object_name@database_link
```

Example:

```sql
SELECT order_id,
       customer_id,
       order_date,
       amount
FROM sales.orders@sales_link
WHERE order_date >= DATE '2026-01-01';
```

`SALES.ORDERS` resides in the remote database. The predicate is sent in the distributed query, and Oracle decides how to execute it based on the optimizer, statistics, and remote processing capabilities.

### 8.1. Querying a Remote View

```sql
SELECT customer_id,
       customer_name,
       customer_status
FROM sales.active_customers@sales_link;
```

If the remote user has been granted privileges on the view, it can be queried like a table. Using views to encapsulate logic and restrict columns can simplify access permissions.

### 8.2. Querying Remote Metadata

```sql
SELECT owner,
       table_name,
       num_rows,
       last_analyzed
FROM all_tables@sales_link
WHERE owner = 'SALES';
```

Data dictionary metadata might not reflect all objects if the remote user lacks privileges. When administrative visibility is needed, the remote DBA should provide restricted views or dedicated reports.

### 8.3. Using Aliases for Remote Objects

```sql
SELECT o.order_id,
       o.amount
FROM sales.orders@sales_link o
WHERE o.status = 'OPEN';
```

Aliases make SQL easier to read and are helpful when writing joins or optimizer hints. In multi-database queries, use clear aliases to distinguish local and remote objects.

### 8.4. Remote Synonyms

You can create a local synonym pointing to a remote object:

```sql
CREATE SYNONYM remote_orders
FOR sales.orders@sales_link;
```

Then query it:

```sql
SELECT order_id, amount
FROM remote_orders
WHERE status = 'OPEN';
```

A synonym is just an alias name. It does not copy data, does not grant remote privileges, and does not remove dependency on the DB link. If the link or remote object changes, the synonym may become invalid or inaccessible.

## 9. Combining Local and Remote Data

A single SQL statement can join local objects with remote objects:

```sql
SELECT c.customer_id,
       c.customer_name,
       o.order_id,
       o.amount
FROM app.customers c
JOIN sales.orders@sales_link o
  ON o.customer_id = c.customer_id
WHERE c.region_id = 10
  AND o.status = 'OPEN';
```

Oracle must decide where to execute parts of the query and how much data needs to be transferred over the network.

### 9.1. Reducing Network Data Transfer

Principles that commonly help:
- Select only the columns actually needed.
- Filter data early using predicates that can be pushed down to remote.
- Aggregate remotely if the aggregated result is significantly smaller.
- Avoid fetching an entire remote table and joining row by row locally.
- Use remote views with stable, optimized logic.
- Avoid issuing remote queries repeatedly inside a PL/SQL loop.

For example, if you only need total sales per customer, let the remote database aggregate first:

```sql
SELECT r.customer_id,
       r.total_amount,
       c.customer_name
FROM app.customers c
JOIN (
    SELECT customer_id,
           SUM(amount) AS total_amount
    FROM sales.orders@sales_link
    WHERE order_date >= DATE '2026-01-01'
    GROUP BY customer_id
) r
  ON r.customer_id = c.customer_id;
```

This structure expresses the intent to transfer only aggregated results from remote. However, whether the optimizer actually pushes the operation down to remote must be confirmed via the execution plan.

### 9.2. Collocated Inline Views

In a distributed query, a group of operations can be executed together at a single remote site to reduce data transfer. Oracle can transform the SQL statement to execute part of the query at the remote database when appropriate.

When control is needed, DBAs can examine the `DRIVING_SITE` hint and collocated inline view techniques. A hint can change the driving site of the query; it is not a default solution. Always measure on real workloads and inspect the SQL sent to the remote site.

### 9.3. Avoiding Row-by-Row Remote Calls

Inefficient pattern:

```text
FOR each local customer:
    SELECT corresponding data FROM remote_table@link
```

Each loop iteration can incur an extra network round trip. With thousands of customers, network latency can dominate total execution time.

Prefer a single distributed query, bulk operations, or batch staging to reduce round trips.

### 9.4. Pay Attention to Selectivity and Statistics

The optimizer must estimate local/remote row counts. Stale statistics, skewed data distributions, or non-sargable predicates can lead to plans that transfer excessive data.

Read the execution plan and compare against actual row counts if runtime statistics are available. Do not conclude a join is slow solely because a DB link is involved; the issue may lie in a remote index, cardinality estimate, or network latency.

## 10. Execution Plans of Distributed Queries

Use `EXPLAIN PLAN` to view the estimated structure:

```sql
EXPLAIN PLAN FOR
SELECT c.customer_id,
       o.order_id,
       o.amount
FROM app.customers c
JOIN sales.orders@sales_link o
  ON o.customer_id = c.customer_id
WHERE c.region_id = 10
  AND o.status = 'OPEN';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

The plan may contain a `REMOTE` operation and a section showing the SQL sent to the remote site. Operation names and display formatting depend on the version.

If the SQL has executed and runtime statistics were collected, view the cursor:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

Appropriate privileges are required to read cursor plans and runtime statistics.

### 10.1. Questions to Ask When Reading the Plan

- Where does the `REMOTE` operation appear?
- Which predicates are pushed down to remote?
- How many rows/bytes are transferred to local?
- Is the join executed locally or remotely?
- Is there an unexpected remote full scan?
- Is there a large sort or aggregation after data is transferred back?
- Are there repeated remote accesses?
- Does the remote SQL use an appropriate index?

### 10.2. Checking Both Databases

A distributed query has two sides:
- The local plan shows how the local database coordinates execution.
- The remote SQL/plan shows the work performed on the remote database.

When needed, the remote DBA can locate the corresponding SQL in the shared pool or AWR/Statspack according to privileges and licensing. Combine timestamps, SQL text, module/action, and session information to correlate both sides.

## 11. DML Over a Database Link

DB links are not limited to SELECT. Oracle supports several forms of DML on remote objects.

### 11.1. INSERT into a Remote Table

```sql
INSERT INTO sales.archive_orders@sales_link (
    order_id,
    customer_id,
    amount
)
SELECT order_id,
       customer_id,
       amount
FROM app.local_orders
WHERE archive_flag = 'Y';
```

This statement reads local data and writes to remote. It requires controlling transactions, remote privileges, and data volume.

### 11.2. INSERT from Remote into Local

```sql
INSERT INTO app.customer_stage (
    customer_id,
    customer_name
)
SELECT customer_id,
       customer_name
FROM sales.customers@sales_link
WHERE status = 'ACTIVE';
```

This approach is useful for staging or ETL. For large volumes, benchmark fetch/transfer, redo, undo, index maintenance, and batch size.

### 11.3. UPDATE on a Remote Object

```sql
UPDATE sales.orders@sales_link
SET status = 'ARCHIVED'
WHERE order_date < DATE '2025-01-01';
```

The remote account needs appropriate UPDATE privileges. Before running, verify the predicate selects the exact target scope and consider the impact on remote workload.

### 11.4. DELETE on a Remote Object

```sql
DELETE FROM sales.staging_orders@sales_link
WHERE load_batch_id = :batch_id;
```

DML from a local session can initiate a distributed transaction. Identify which databases the transaction modifies and whether two-phase commit may be required.

### 11.5. MERGE and DML Limitations

Some forms of `MERGE`, `RETURNING`, LOBs, object types, triggers, or constraints may have limitations when objects reside in a remote database. Support depends on syntax, version, and statement structure.

Do not assume every DML statement that runs on a local table will run over a DB link. Test on staging, consult the SQL Language Reference for your exact release, and check actual errors before deployment.

## 12. Distributed Transactions and Two-Phase Commit

When a transaction modifies data across multiple databases, Oracle must ensure participants reach a consistent commit outcome. Oracle uses the **two-phase commit (2PC)** mechanism for distributed transactions according to supported configuration and semantics.

Example local transaction:
1. Update local table `APP.ORDERS`.
2. Update remote table `SALES.INVENTORY@SALES_LINK`.
3. Commit.

```sql
UPDATE app.orders
SET status = 'ALLOCATED'
WHERE order_id = :order_id;

UPDATE sales.inventory@sales_link
SET reserved_qty = reserved_qty + :qty
WHERE product_id = :product_id;

COMMIT;
```

Both operations belong to the same distributed transaction. If one participant cannot complete, Oracle must coordinate to ensure the commit/rollback decision is handled according to the protocol.

### 12.1. The Two Phases

**Prepare phase:**
- The global coordinator asks participants to prepare to commit.
- Each participant ensures it can complete the commit and records the necessary state.
- Participants reply prepared/commit-ready or report an error.

**Commit phase:**
- Once participants are ready, the coordinator notifies them to commit.
- If the transaction cannot commit per the transaction decision, the coordinator orchestrates rollback per the protocol.
- Participants complete the action and release resources upon receiving the decision.

Conceptual diagram:

```text
Local transaction coordinator
          |
          | PREPARE
          +--------------------+
          |                    |
          v                    v
   Local database        Remote database
          |                    |
          +------ READY -------+
          |
          | COMMIT decision
          +--------------------+
          |                    |
          v                    v
   Commit local          Commit remote
```

Simplified diagram for illustration. Distributed transactions can involve multiple participants and a coordinator/commit point depending on the actual topology.

### 12.2. Why Is 2PC Important?

2PC prevents situations where one database commits while another rolls back within the same distributed transaction. However, it comes with costs:
- Additional network round trips.
- Potentially longer lock durations.
- Dependency on participant availability.
- Possible in-doubt states if coordinator/participants lose communication.
- Increased operational complexity.

Do not introduce DB links into business transactions unless simultaneously updating multiple databases is genuinely necessary.

### 12.3. Read-Only Queries and Distributed Commit

A simple remote SELECT does not mean a transaction is updating multiple databases. Two-phase commit primarily applies to distributed transactions modifying data across multiple participants. Nonetheless, distributed queries still depend on network/remote availability and consume resources on both sides.

## 13. In-Doubt Transactions and Recovery

If a failure occurs during 2PC, a participant may not have received the final decision. The transaction may appear in an in-doubt state.

Oracle includes a background recovery process such as RECO to assist in automatically resolving distributed transactions once connectivity and coordinator information return.

### 13.1. Checking Pending Transactions

DBAs can inspect:

```sql
SELECT local_tran_id,
       global_tran_id,
       state,
       mixed,
       fail_time,
       retry_time
FROM dba_2pc_pending
ORDER BY fail_time;
```

Participant details:

```sql
SELECT local_tran_id,
       in_out,
       database,
       dbuser_owner,
       interface
FROM dba_2pc_neighbors
ORDER BY local_tran_id;
```

These views require DBA privileges, and columns may vary by version. Never delete or force-resolve a transaction simply because you see a pending row.

### 13.2. RECO

RECO is the recovery process for distributed transactions. When a network or database outage recovers, RECO can communicate with participants to complete the transaction according to the recorded decision.

DBAs should check:
- Whether the remote database is up.
- Whether the listener/service and network are stable.
- What state the transaction is in.
- Whether the coordinator and participants have the same decision.
- What information appears in the alert log and traces.

### 13.3. Do Not Force Commit/Rollback Arbitrarily

Force resolution commands such as `COMMIT FORCE` or `ROLLBACK FORCE` are only for DBAs handling special situations after determining the global decision and consulting Oracle procedures.

Forcing a participant based on guesswork can create a mixed outcome, meaning databases no longer share the same business result. Preserve evidence, identify the global transaction ID, and coordinate with the DBAs of all participants before manual intervention.

## 14. Transaction Boundaries and Errors When the Remote Database Loses Connection

When DML over a DB link encounters an error, do not continue the transaction as though all previous operations succeeded.

Principles:
- Catch exceptions and roll back the transaction according to Oracle's required state/semantics.
- Do not perform a partial commit just to ignore a remote error.
- Check pending transactions if a 2PC error occurs.
- Do not blindly retry DML without knowing the outcome.
- Use a business key or idempotency key if the operation may be re-submitted.
- Log the global transaction context and appropriate error code, without logging credentials.

A connection failure after sending COMMIT can leave the client unaware of the final outcome. This is similar to transaction outcome ambiguity in distributed applications; a status-determination procedure is required, rather than assuming no response means rollback.

## 15. Database Link Lifecycle Management

### 15.1. Viewing Links in the Current Schema

```sql
SELECT db_link,
       username,
       host,
       created
FROM user_db_links
ORDER BY db_link;
```

### 15.2. Viewing Links Accessible to the User

```sql
SELECT owner,
       db_link,
       username,
       host
FROM all_db_links
ORDER BY owner, db_link;
```

### 15.3. DBA Viewing All Links

```sql
SELECT owner,
       db_link,
       username,
       host,
       created
FROM dba_db_links
ORDER BY owner, db_link;
```

Metadata views may not display all information depending on privileges. Do not attempt to extract plaintext passwords from the data dictionary.

### 15.4. Closing a DB Link Connection in a Session

You can close the remote connection for the current session:

```sql
ALTER SESSION CLOSE DATABASE LINK sales_link;
```

Only execute this when no active transaction depends on the link and in accordance with Oracle conditions. When the link is used again, Oracle can open a new connection.

### 15.5. Dropping a Private Link

```sql
DROP DATABASE LINK sales_link;
```

This command drops a private link belonging to the current schema.

### 15.6. Dropping a Public Link

```sql
DROP PUBLIC DATABASE LINK shared_reporting_link;
```

This change affects every consumer using that public link. Before dropping, inventory all dependent schemas, jobs, and applications.

### 15.7. Credential Rotation

A fixed-user DB link is tied to remote credentials. When the remote password changes, the link must be updated through a supported procedure, typically recreating the link with the new credential after assessing dependencies.

A rotation plan requires:
1. Identifying all consumers of the link.
2. Creating/preparing the new remote credential or an appropriate transition window.
3. Updating the DB link via a secure deployment process.
4. Testing remote queries with a new session.
5. Refreshing old sessions if they still hold remote connections.
6. Revoking old credentials once no consumers remain.

Do not record real passwords in scripts, tickets, or logs. Do not change remote credentials before knowing which links and jobs are using them.

## 16. Database Link Security

A DB link creates an access path from the local database to the remote database. If credentials have overly broad privileges or the link is misused, the impact can propagate across multiple systems.

### 16.1. Least Privilege on the Remote Side

The remote account should only be granted:
- `SELECT` on required views/tables if read-only querying is needed.
- DML on specific objects if writing is genuinely required.
- No DBA or `ANY` privileges for standard integrations.
- Never use a schema owner or administrative account as the remote identity.

Prefer creating remote views containing only necessary columns, then granting privileges on the views to the remote account.

### 16.2. Per-Application Private Links

Each application should have its own private link and appropriate remote identity. Avoid using a single public link with a remote account that can read an entire schema for all workloads.

### 16.3. Protecting Credentials

Credentials in DDL can be exposed through:
- Source control.
- SQL history.
- Deployment scripts.
- Terminal transcripts.
- CI/CD output.
- Audit or logs depending on configuration.

Use secret management workflows, restrict link-creation privileges, and control where scripts are stored. Oracle protects link credentials in metadata via its own mechanisms, but that does not protect copies of DDL containing passwords stored elsewhere by deployment teams.

### 16.4. Network Protection

Local-to-remote connections should be restricted:
- Firewalls allowing only required hosts/services.
- Oracle Net encryption/integrity or TLS per policy.
- Certificate and wallet verification when using TLS.
- Limiting listener exposure.
- Monitoring connections and authentication failures.
- Not allowing the database server to connect arbitrarily to any endpoint.

### 16.5. Auditing and Traceability

Record:
- Schema owning the link.
- Remote username.
- Endpoint/service.
- Business consumer.
- Owner and purpose.
- Granted remote privileges.
- Creation/last rotation date.
- DDL changes and who performed them.

Do not record passwords. Combine database auditing, network monitoring, and application module/action to investigate anomalous access.

## 17. Database Link Names and GLOBAL_NAMES

The `GLOBAL_NAMES` parameter controls whether a DB link name must match the global database name of the remote database.

Check:

```sql
SHOW PARAMETER global_names;
```

Or:

```sql
SELECT name, value
FROM v$parameter
WHERE name = 'global_names';
```

If `GLOBAL_NAMES=TRUE`, the link name must follow the global name rule of the remote database. If the name does not match, error `ORA-02085` may occur.

Check the remote global name:

```sql
SELECT *
FROM global_name@sales_link;
```

Do not change global names or `GLOBAL_NAMES` just to make one link work without assessing the impact on other links. Follow clear naming conventions and verify database identity before creating a link.

## 18. Limitations and Data Types in Remote Access

Distributed SQL has certain limitations compared to SQL running within a single database. Restrictions depend on the version, object type, and statement.

In particular, check:
- `LONG` and certain LOB operations.
- User-defined object types and collections.
- Remote temporary tables.
- Certain special joins, subqueries, or DML constructs.
- Triggers, constraints, and cross-database referential integrity.
- Certain `RETURNING` clauses or operations unsupported over links.
- Remote procedure calls and datatype mapping.
- Behavior of materialized views or objects with remote dependencies.

Do not assume a local foreign key can directly enforce integrity with a remote table the way two tables in the same database do. If cross-database business constraints are needed, design them at the integration layer or use an appropriate transaction/distributed architecture.

For large datasets or special data types, test on the exact Oracle release, driver, and object structure before deployment.

## 19. Performance and Availability

### 19.1. Network Latency

Every data exchange between local and remote incurs network latency. Queries with many round trips can be slow even when both databases have plenty of CPU and I/O capacity.

Reduce round trips by:
- Consolidating queries.
- Using bulk fetch/bulk DML.
- Avoiding remote calls inside loops.
- Pushing filters/aggregates to where the data resides.
- Limiting concurrent requests.

### 19.2. Remote Database as a Runtime Dependency

If application SQL depends on a DB link, a remote outage can cause local requests to fail. Configure timeouts, concurrency limits, and remote error classification.

For business workflows that do not require strictly up-to-the-second data on every request, consider caches, materialized views, or staging to reduce synchronous dependency.

### 19.3. Connection/Session Fan-Out

A large number of local sessions simultaneously using a DB link can spawn many remote sessions. This affects:
- Remote process/session limits.
- Remote PGA/CPU.
- Network connection count.
- Connection setup overhead.
- Recovery behavior after an outage.

Set pool and concurrency limits at the local application/database level, and monitor remote session counts.

### 19.4. Query Only Needed Columns

Avoid:

```sql
SELECT *
FROM sales.orders@sales_link;
```

if only a few columns are needed. Transferring unnecessary data increases network, memory, and processing time.

### 19.5. Choosing Where to Execute Joins

If most data resides on the remote side, pushing joins/filters/aggregates down to remote so only a small result is returned can help. If the remote dataset is very small, transferring it to local to join with a local dataset may make more sense.

No single site is always best. Inspect the plan, cardinality, network throughput, and remote/local costs before using steering hints.

## 20. Troubleshooting Common DB Link Errors

| Error Code | Common Cause | Investigation Direction |
|---|---|---|
| `ORA-12154` | Could not resolve connect identifier | Check Oracle Net alias and config on local database server |
| `ORA-12541` | No listener at endpoint | Check host/port, listener, and firewall |
| `ORA-12514` | Listener does not recognize requested service | Check `SERVICE_NAME`, service registration, and PDB |
| `ORA-01017` | Invalid username/password | Check remote account, credentials, and rotation status |
| `ORA-28000` | Remote account is locked | Handle remote account/profile per policy |
| `ORA-02019` | Connection description not found | Check `USING`, TNS alias, and Oracle Net config |
| `ORA-02085` | Link name does not match global database name when required | Check `GLOBAL_NAMES` and remote `GLOBAL_NAME` |
| `ORA-02049` | Timeout waiting for distributed transaction lock | Check blocking transaction, wait time, and concurrency |
| `ORA-02068` | Subsequent severe error from remote database | Read following errors and alert/trace logs on both sides |
| `ORA-02055` | Distributed update failed, transaction must roll back | Roll back as required, check transaction state and participants |
| `ORA-03113` | Communication channel closed unexpectedly | Check network, alert log, and remote session |

A single error code can be a symptom of multiple causes. Always read the entire error stack, including trailing remote errors, and correlate timestamps on both local and remote sides.

### 20.1. Investigation Workflow

1. Test `SELECT 1 FROM dual@link`.
2. Verify link metadata and remote username.
3. Verify service name and global database name.
4. Check network connectivity from the local database host.
5. Check the listener and service on the remote side.
6. Check remote account status and object privileges.
7. Review local/remote alert logs and listener logs.
8. Check pending transactions if the error occurred during distributed DML/COMMIT.
9. Check the SQL plan and data transfer volume if the issue is performance.
10. Document findings and configuration changes to prevent recurrence.

## 21. Choosing a DB Link or Another Integration Option?

A DB link fits when direct SQL access to remote data is needed at controllable volume and frequency. It is not the optimal choice for every integration pattern.

| Requirement | Option to Consider |
|---|---|
| Direct reference queries between two Oracle DBs | Database link |
| Repeated reporting, tolerable data lag | Materialized view |
| Scheduled, large-volume data transfer | ETL/staging/Data Pump |
| Continuous change synchronization | CDC/replication such as Oracle GoldenGate per architecture |
| Business communication via API | Service/API layer |
| Asynchronous integration and decoupling runtime dependency | Message broker/event/outbox |
| HA/DR for a database | Data Guard or suitable HA architecture |

### 21.1. Materialized View

A materialized view can store remote query results locally and refresh on a schedule or supported mechanism. This reduces remote access per request, at the cost of data lag and refresh management.

### 21.2. ETL and Staging

When moving millions of records in batches, ETL/staging can offer easier control over retries, restarts, auditing, and data quality than a long-running runtime query over a link.

### 21.3. API or Messaging

If the remote database belongs to a different bounded context, API or event integration preserves clearer data ownership and avoids coupling applications directly to the other side's schema.

A DB link can still be an appropriate tool for certain internal integrations, provided schema coupling and access permissions are properly managed.

## 22. Comprehensive Hands-On Lab

This lab assumes two Oracle Databases:
- Local database containing schema `APP`.
- Remote database containing schema `SALES`.
- Remote service configured in Oracle Net on the local database server as `SALES_SERVICE`.
- Remote account `SALES_READER` with read-only privileges on selected objects.

Do not use real passwords in documentation or source control. Perform this in a lab environment with appropriate permissions.

### Step 1. Prepare the Remote Account and Privileges

On the remote database, the DBA creates the account per policy and grants least privileges. Example:

```sql
GRANT CREATE SESSION TO sales_reader;
GRANT SELECT ON sales.customers TO sales_reader;
GRANT SELECT ON sales.orders TO sales_reader;
```

If the remote account needs to read a view, grant privileges on that view rather than broad schema privileges.

### Step 2. Verify Oracle Net from the Local Server

Confirm `SALES_SERVICE` resolves properly from the local database host and the remote listener exposes the corresponding service.

### Step 3. Create a Private Link Locally

In the application schema:

```sql
CREATE DATABASE LINK sales_link
CONNECT TO sales_reader
IDENTIFIED BY "password_placeholder"
USING 'SALES_SERVICE';
```

Replace the placeholder with credentials provided through an appropriate secure process in the lab environment.

### Step 4. Test the Link

```sql
SELECT 1
FROM dual@sales_link;

SELECT USER
FROM dual@sales_link;

SELECT *
FROM global_name@sales_link;
```

Confirm the remote identity and target database.

### Step 5. Query a Remote Table

```sql
SELECT customer_id,
       customer_name
FROM sales.customers@sales_link
WHERE status = 'ACTIVE';
```

### Step 6. Query a Remote View or Synonym

```sql
CREATE SYNONYM active_customers_remote
FOR sales.active_customers@sales_link;
```

```sql
SELECT customer_id, customer_name
FROM active_customers_remote;
```

### Step 7. Join Local and Remote Data

```sql
SELECT c.customer_id,
       c.customer_name,
       o.order_id
FROM app.customer_map c
JOIN sales.orders@sales_link o
  ON o.customer_id = c.remote_customer_id
WHERE c.region_id = 10;
```

### Step 8. View the Execution Plan

```sql
EXPLAIN PLAN FOR
SELECT c.customer_id,
       o.order_id
FROM app.customer_map c
JOIN sales.orders@sales_link o
  ON o.customer_id = c.remote_customer_id
WHERE c.region_id = 10;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Look for the `REMOTE` operation, pushed-down predicates, and estimated rows transferred over the network.

### Step 9. Test DML Only in the Lab

If the remote account has write privileges and the lab allows it, test inserting/updating a test row. Check whether the transaction modifies both local and remote, then commit or roll back according to the scenario.

Do not test distributed DML on production data just to verify connectivity.

### Step 10. Check Metadata and Clean Up the Lab

```sql
SELECT db_link, username, host, created
FROM user_db_links;
```

Once no sessions or transactions depend on it:

```sql
DROP DATABASE LINK sales_link;
```

Clean up lab synonyms or objects you created according to dependencies. Do not drop shared links or business objects.

## 23. Checklist Before Promoting a DB Link to Production

### Connectivity and Configuration
- TNS/service name verified from the local database host.
- Remote listener/service is accurate.
- Link points to the right database/PDB.
- `GLOBAL_NAMES` behavior is clearly understood.
- Appropriate timeouts/network policies are in place.
- Tested after failover/restart.

### Security
- Private links preferred when sufficient.
- Public links have a clear owner and justification.
- Remote account has least privilege.
- DBA/schema owner accounts are not used for applications.
- Credentials are absent from source code/logs.
- Network encryption and firewalls are configured.
- Auditing and rotation plan are in place.

### SQL and Performance
- Only needed columns are queried.
- Predicates can be pushed down to remote.
- No unexpected row-by-row remote calls.
- Execution plans reviewed on local and remote when needed.
- Remote session count is controlled.
- Timeouts and concurrency limits are set.
- Benchmarked with representative data/latency.

### Transactions and Operations
- Identified whether transactions update multiple databases.
- 2PC and in-doubt handling are understood.
- Rollback procedure exists for remote errors.
- Transactions are never force-resolved without a global decision.
- Troubleshooting runbook is available.
- Fallback plan exists for remote database outages.

## 24. Self-Check Questions

**Question 1.** What is a database link?

**Answer:** An object that allows a local session to connect to a remote database and reference remote objects in SQL using the syntax `object@link`.

**Question 2.** How does a private link differ from a public link?

**Answer:** A private link belongs to a single schema; a public link has broader usage scope across the database.

**Question 3.** How does a fixed-user link work?

**Answer:** It always connects remotely using the username declared in the link, regardless of which local session uses the link.

**Question 4.** Does a current-user link work automatically for every user?

**Answer:** No. Appropriate authentication/identity configuration is required on both databases, typically involving enterprise/global users or external authentication.

**Question 5.** Where is the DB link's TNS alias resolved?

**Answer:** In the Oracle Net environment used by the local database server, because the local database server itself initiates the remote connection.

**Question 6.** How do you perform a basic link test?

**Answer:** Run `SELECT 1 FROM dual@link` and check the remote identity/global name if privileged.

**Question 7.** Does a remote synonym copy data?

**Answer:** No. A synonym is only an alias for the remote object and still depends on the DB link.

**Question 8.** Why can a distributed query be slow?

**Answer:** Due to network latency, data transfer volume, number of round trips, the remote execution plan, or remote resources.

**Question 9.** What is the `DRIVING_SITE` hint used for?

**Answer:** To instruct the optimizer which site drives a distributed query; it must be measured and checked in the plan before applying.

**Question 10.** When is two-phase commit needed?

**Answer:** When a distributed transaction updates multiple participant databases and Oracle must coordinate the commit/rollback decision.

**Question 11.** What does RECO do?

**Answer:** Assists in resolving pending distributed transactions once participants/coordinators become reachable again.

**Question 12.** Why shouldn't you arbitrarily force commit an in-doubt transaction?

**Answer:** It can leave participants with inconsistent outcomes; you must determine the global decision and coordinate with DBAs first.

**Question 13.** How does `GLOBAL_NAMES` affect DB links?

**Answer:** When enabled, the link name must conform to rules matching the remote database's global database name.

**Question 14.** Why does the remote account need least privilege?

**Answer:** If the link or credentials are misused, least privilege limits the scope of data and operations affected.

**Question 15.** Does a DB link replace replication?

**Answer:** No. A DB link accesses remote data at query time; it does not maintain a synchronized copy.

**Question 16.** When should you consider a materialized view instead of a runtime DB link?

**Answer:** When queries are repeated frequently, refresh lag is acceptable, and you want to reduce dependency on the remote database per request.

**Question 17.** Why avoid remote queries inside a loop?

**Answer:** Each call can incur a network round trip, causing latency to scale with the number of loop iterations.

**Question 18.** What must be checked when the remote password changes?

**Answer:** The link, remote account, consumers, open sessions, test queries, and when to revoke old credentials.

## 25. Conclusion

Database links allow a local Oracle Database to access tables, views, and certain objects in a remote database using the `object@link` syntax. Private/public links determine usage scope; fixed-user/current-user links determine the remote identity. Connections are initiated from the local database server via Oracle Net, so service names, listeners, networking, remote accounts, and object privileges must be configured properly on both sides.

DB links make distributed queries and DML convenient to write, but performance depends on network round trips, transferred data volume, join execution site, and remote resources. Filter and aggregate early, select only needed columns, avoid row-by-row remote calls, and inspect execution plans on both local and remote sides. For transactions modifying multiple databases, understand two-phase commit, in-doubt transactions, and the role of RECO; never force commit/rollback before determining the global decision.

On the security side, prefer private links, least-privilege remote accounts, strict control over public link creation privileges, protection of credentials in DDL, and network connection restrictions. A DB link is not replication, backup, or a message queue. When runtime dependency needs to be reduced, consider materialized views, ETL/CDC, APIs, or messaging. Only promote a link to production after verifying the target service, privileges, rotation, performance, transaction recovery, and runbooks for remote database outages.
