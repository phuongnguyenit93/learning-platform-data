# Scope, Privilege, and Licensing Boundaries of Integration Options

Oracle Database offers many ways to connect and exchange data with other systems: database links and distributed SQL, materialized views, external tables, Data Pump, Database Gateway, Oracle GoldenGate, Advanced Queuing, and REST APIs. Each option has a distinct data scope, privilege model, operational profile, and licensing requirement.

Choosing the right integration option requires answering three questions:

1. **Scope:** Which systems are connected, which schemas/tables/rows are read or written, and is data moved once or synchronized continuously?
2. **Privileges:** Which identity establishes the connection, where are privileges granted, and can access be delegated or exceed the intended scope?
3. **Licensing:** Which database editions, options, products, deployments, and metrics are permitted under contract?

Never pick a technology merely because it is already installed or a technical command executes successfully. Technical capability and commercial usage rights are two separate matters. Especially with GoldenGate, Gateways, XStream, Active Data Guard, and security features, confirm the exact version, edition, product, contract, and deployment model before promoting to production.

## 1. Map of Integration Options

| Option | Model | Typical Scope | Key Controls |
|---|---|---|---|
| Database link | Query/write from one database to another | Specific objects in a remote database | Remote account, link owner, public/private, distributed transactions |
| Materialized view | Stores a query result copy and refreshes it | Tables or datasets needing local reads | Refresh mode, freshness, source/target privileges, storage |
| External table | Reads file data as a table | Files or formats supported by access drivers | `DIRECTORY`, filesystem permissions, format, and file source |
| Data Pump | Logical export/import | Full, schema, table, or tablespace | Data Pump privileges, dump files, consistency, encryption |
| Database Gateway / Heterogeneous Services | Accesses non-Oracle systems | Objects in SQL Server, ODBC, or supported systems | Gateway/agent, type mapping, pushdown, distributed transactions, licensing |
| Oracle GoldenGate | Captures and replicates changes | Tables/schemas/databases or filtered streams | Product license, capture/apply, conflicts, lag, supplemental logging |
| AQ / Transactional Event Queues | Asynchronous message exchange | Queues, consumers, events | Enqueue/dequeue privileges, retention, delivery semantics |
| REST via ORDS or API layer | Integration over HTTP | Endpoints, resources, operations | Authentication, OAuth/roles, networking, rate limits, and database licensing |

No single option fits every case. For example, a database link is convenient for remote queries yet introduces runtime dependency on the network and source database. GoldenGate suits continuous replication yet requires capture/apply architecture and license governance. Data Pump suits batch movement, not real-time change sync.

## 2. Defining Scope Before Choosing a Technology

Before designing, describe the integration scope across these dimensions:

### System Scope

- Source and target databases.
- Involved CDBs/PDBs and service names.
- Non-Oracle systems such as SQL Server, PostgreSQL, file servers, or APIs.
- Development, test, staging, production, and DR environments.
- Permitted network zones.

### Data Scope

- Which schemas are shared?
- Which tables/views need access?
- Is column-level or tenant-level restriction required?
- Can data be filtered by row, timestamp, or business status?
- Is there sensitive data that must be masked or excluded?
- Is historical data required or only current data?

### Operation Scope

- Read-only or also write?
- Unidirectional or bidirectional?
- On-demand querying or continuous synchronization?
- Are cross-database transactions required?
- Is near-real-time required or is batch acceptable?
- On connection loss, is data retried, queued, or dropped?

### Time and Recovery Scope

- Execution frequency and maintenance windows.
- RPO and maximum tolerable data lag.
- RTO when one system loses connectivity.
- How missing or duplicate data is detected.
- How reconciliation runs after recovery.

A well-defined scope helps grant narrow privileges, estimate load, and pinpoint which licenses require verification.

## 3. Database Links: Direct Connection Between Two Databases

A database link (DB link) allows a session in a local database to access objects in a remote database using syntax such as:

~~~sql
SELECT order_id,
       status
  FROM orders@orders_link;
~~~

DB links generally fit when:

- The application needs to query remote data on demand.
- Object count and traffic volume are manageable.
- Dependency on network and remote database availability is acceptable.
- Distributed SQL or multi-database transactions are required.

A DB link does not copy data locally. Queries still depend on the remote database and network at execution time.

### Creating a Private Database Link

Example:

~~~sql
CREATE DATABASE LINK orders_link
  CONNECT TO integration_reader
  IDENTIFIED BY "Managed-Secret"
  USING 'ORDERS_SERVICE';
~~~

The service name `ORDERS_SERVICE` must be configured in Oracle Net naming or a connect descriptor resolvable by the local database. The password in the example is a placeholder; never store real secrets in source code or committed SQL files.

A user creating a private DB link needs the `CREATE DATABASE LINK` privilege. A private DB link is scoped to the user that owns it.

### Creating a Public Database Link

~~~sql
CREATE PUBLIC DATABASE LINK shared_orders_link
  CONNECT TO integration_reader
  IDENTIFIED BY "Managed-Secret"
  USING 'ORDERS_SERVICE';
~~~

Creating a public link requires `CREATE PUBLIC DATABASE LINK`. A public link can be used by any database user according to link settings and corresponding remote privileges. Thus, a public link can expand access scope far beyond a single application's needs.

Prefer private DB links for specific services or schemas. Use a public link only when there is clear architectural justification, an accountable owner, narrow remote privileges, and proper auditing.

### DB Link Authentication Types

Common connection types:

- **Fixed user:** the DB link stores fixed remote user credentials; every access via the link uses that remote identity.
- **Connected user:** the local identity is used to authenticate equivalently on remote per configuration and supported auth models.
- **Current user:** uses global/current user in supported scenarios, typically tied to enterprise user/security models.

Never use a fixed user holding DBA privileges or full-schema read access. Provision a remote account with only what the integration needs, such as `SELECT` on specific views or `EXECUTE` on an API package.

### Privileges Exist on Both Sides

For a query over a DB link to succeed:

1. The local user must have permission to use the DB link according to how it was created and owned.
2. The link must resolve the right service and reach the remote database.
3. Remote credentials must authenticate successfully.
4. The remote user must hold privileges on the accessed objects.
5. Networks and firewalls must allow the connection.

Local grants do not substitute for remote grants. For example, granting `SELECT` to a local user on a view does not automatically grant read access on a remote table. The remote account must hold matching privileges on remote objects or published packages.

### Private Link vs. Public Link

| Criterion | Private DB Link | Public DB Link |
|---|---|---|
| Visibility scope | User owning the link | Database users can reference it |
| Creation privilege | `CREATE DATABASE LINK` | `CREATE PUBLIC DATABASE LINK` |
| Credentials | Can bind to a fixed remote user | Can bind to shared fixed credentials |
| Risk | Depends on remote account privileges and link owner | Easily expands access scope across many users |
| Recommendation | Preferred for specific apps/schemas | Use only with clear justification and controls |

### Inspecting Database Links

~~~sql
SELECT owner,
       db_link,
       username,
       host
  FROM dba_db_links
 ORDER BY owner, db_link;
~~~

Regular users can inspect `USER_DB_LINKS` or `ALL_DB_LINKS` within permitted scope. Never query or export sensitive credential details into reports.

Test remote connectivity:

~~~sql
SELECT 1
  FROM dual@orders_link;
~~~

Then confirm the exact database/service:

~~~sql
SELECT name,
       db_unique_name
  FROM v$database@orders_link;
~~~

The query above requires read access to dynamic performance views on remote; if unavailable, use a minimal verification view published for integration.

## 4. Distributed SQL and Distributed Transactions

DB links support distributed queries, such as joining local and remote tables:

~~~sql
SELECT o.order_id,
       c.customer_name
  FROM local_orders o
  JOIN customers@crm_link c
    ON c.customer_id = o.customer_id;
~~~

Oracle can push part of the processing to the remote database or ship data to local for remaining work. Execution plans depend on statistics, predicates, data types, remote capabilities, and the optimizer.

Do not assume joins always run where the smallest dataset resides. Inspect execution plans and row counts transferred over the network when queries run slowly.

### Cross-Database Transactions

A single transaction can update local and remote objects via a DB link:

~~~sql
UPDATE local_orders
   SET status = 'CONFIRMED'
 WHERE order_id = 1001;

UPDATE orders@orders_link
   SET status = 'CONFIRMED'
 WHERE order_id = 1001;

COMMIT;
~~~

When consistency across multiple databases is required, Oracle uses distributed transaction coordination, typically involving two-phase commit (2PC). A transaction can enter an in-doubt state if a participant or the network fails during commit.

DBAs must know how to monitor and resolve distributed transactions, including views such as `DBA_2PC_PENDING` and corresponding recovery procedures. Never delete or force-commit/rollback an in-doubt transaction before determining the global commit decision.

### Operational Limits of Distributed Transactions

- Network latency prolongs lock hold times.
- Remote database unavailability can prevent transactions from completing.
- 2PC failures can leave in-doubt transactions needing intervention.
- Some operations or object types are incompatible with distributed transactions.
- Large transactions spanning multiple systems increase coupling.

If synchronous cross-database transactions are unnecessary, consider the outbox pattern, queues, or asynchronous replication to reduce coupling.

## 5. Materialized Views: Refreshable Data Copies

A materialized view stores query results in the database instead of running a remote query on every user read. It fits reporting, lookups, or reference data needing fast local reads with tolerable refresh lag.

Example creating a materialized view backed by a remote table:

~~~sql
CREATE MATERIALIZED VIEW local_customer_snapshot
  BUILD IMMEDIATE
  REFRESH COMPLETE ON DEMAND
AS
SELECT customer_id,
       customer_name,
       customer_status
  FROM customers@crm_link;
~~~

This example creates a logical copy of a subset of remote columns. The user creating the MV needs privileges to create materialized views and read the source; the remote user behind the DB link needs read access on the remote table or view.

### Complete Refresh vs. Fast Refresh

| Mechanism | Behavior | Characteristics |
|---|---|---|
| `COMPLETE` | Re-runs the query to rebuild full contents | Simple to understand, can consume heavy I/O and time |
| `FAST` | Applies incremental changes when eligible | Requires logs/metadata and qualifying query structure |
| `FORCE` | Attempts `FAST`, falls back to `COMPLETE` per rules | Result and cost depend on fast-refresh eligibility |

Fast refresh imposes strict conditions on queries, materialized view logs, keys, and source/target support. Not every arbitrary query can fast refresh. With remote masters, check Oracle documentation for your exact release and test refreshes in an equivalent environment.

### Privileges and Scope

- Local owner needs privileges to create and refresh the MV.
- Remote account needs only read access on source objects.
- Never grant remote `SELECT ANY TABLE` just to refresh one MV.
- If users only need to read the MV, grant `SELECT` on the MV rather than exposing the DB link or source tables.
- Schedule refreshes according to freshness SLAs and source load.

Materialized views reduce direct queries on the remote database, yet create a data copy. Define who may read that copy, whether data is sensitive, and when data is purged or refreshed.

## 6. External Tables: Reading Files via SQL

External tables let Oracle query data stored in external files outside the database as if they were tables. Data does not have to live inside Oracle table segments; an access driver reads files per configuration.

Simple example with `ORACLE_LOADER`:

~~~sql
CREATE TABLE ext_orders (
  order_id      NUMBER,
  customer_id   NUMBER,
  order_date    DATE,
  order_status  VARCHAR2(30)
)
ORGANIZATION EXTERNAL (
  TYPE ORACLE_LOADER
  DEFAULT DIRECTORY dp_dir
  ACCESS PARAMETERS (
    RECORDS DELIMITED BY NEWLINE
    FIELDS TERMINATED BY ','
    OPTIONALLY ENCLOSED BY '"'
    MISSING FIELD VALUES ARE NULL
  )
  LOCATION ('orders.csv')
)
REJECT LIMIT UNLIMITED;
~~~

External tables fit:

- Loading CSV or text files.
- Reading batch exchange files.
- Using SQL to filter/transform file data.
- Staging data before inserting into internal tables.

### External Table Privileges

The user creating an external table needs table-creation privileges and `READ` on the `DIRECTORY` object. The Oracle software owner needs OS read permissions on the file. If an external table writes files via a supported access driver, `WRITE` privilege and corresponding OS permissions are required.

Never grant `DIRECTORY` privileges to `PUBLIC`. A `DIRECTORY` object can point to a location holding multiple files; overly broad permissions can expose files outside business scope.

### External Tables Are Not DB Links

External tables read files; they do not query another database directly. When files are produced by another system, establish procedures for delivering files to the folder and verifying checksums, formats, encodings, permissions, and completion timing.

Never let applications read a file while the producer is still writing it. Use atomic staging/renaming or manifest files so only completed files are imported.

## 7. Data Pump: Scoped Logical Movement

Data Pump uses `expdp`/`impdp` to export/import metadata and data:

| Mode | Scope |
|---|---|
| `FULL=YES` | Full database scope per privileges and support |
| `SCHEMAS` | One or more schemas |
| `TABLES` | One or more tables |
| `TABLESPACES` | Objects/data by tablespace |
| `TRANSPORT_TABLESPACES` | Metadata for transportable datafile workflows |

Data Pump fits migrations, refreshing test environments, schema moves, or batch data exchanges. It is not a continuous synchronization mechanism.

### Data Pump Privileges

Users need privileges matching the mode, objects, and `DIRECTORY`:

- `CREATE SESSION`.
- `READ`/`WRITE` on the `DIRECTORY` object.
- Read privileges on source objects.
- Object-creation privileges in the target database.
- Full export/import Data Pump roles when operating outside the user's own schema.

Do not grant `DBA` by default. Distinguish `DATAPUMP_EXP_FULL_DATABASE` and `DATAPUMP_IMP_FULL_DATABASE` roles from general `DBA` privileges.

### Network Link Imports

Data Pump can use `NETWORK_LINK` to read directly from a source database over a database link:

~~~text
impdp app_user@TARGET NETWORK_LINK=SOURCE_LINK SCHEMAS=APP_OWNER LOGFILE=network_import.log
~~~

The target needs a database link pointing to the source and required read privileges. Check version compatibility, network throughput, remote load, and transaction/consistency requirements. `NETWORK_LINK` does not turn Data Pump into continuous replication.

## 8. Database Gateway and Heterogeneous Services

Standard database links connect to Oracle Databases. When accessing a non-Oracle RDBMS, Oracle Database Gateway or an appropriate heterogeneous connectivity solution may be required.

Heterogeneous Services provides the integration layer enabling Oracle to access heterogeneous systems. The gateway translates requests, metadata, and data between Oracle SQL and the target system's protocol/SQL.

Conceptual architecture example:

~~~text
Oracle application
       |
       v
Oracle Database
       |
       | database link
       v
Heterogeneous Services
       |
       v
Database Gateway / agent
       |
       v
Non-Oracle database
~~~

The specific gateway depends on the target system and version. Gateways may be vendor-specific or generic ODBC-based connectivity.

### Scope and Limitations

- Not every Oracle data type maps one-to-one to the target system.
- SQL functions, joins, analytic functions, and data types may not push down.
- Certain DDL or transaction semantics behave differently than Oracle-to-Oracle.
- Performance depends on networks, drivers, gateway hosts, and remote optimizer capabilities.
- Distributed transactions with non-Oracle participants carry specific limitations.
- Verify character sets, timezones, numeric precision, and `NULL` semantics.

Never assume a query working on Oracle behaves identically over a gateway. Test actual SQL statements, execution behavior, transactions, and errors on both sides.

### Gateway Privileges

The remote account needs least privileges on the target system. Local database users need privileges on the database link and published objects/views. Gateway processes/agents need configured credentials, OS accounts, and network access.

Separate gateway service accounts from database admin accounts. Never store remote credentials in world-readable configuration files. Restrict permissions on gateway hosts, logs, and config folders.

### Gateway Licensing

Never infer a gateway is licensed for use merely because binaries, drivers, or configurations exist in Oracle Home. License terms can depend on gateway product name, target system, version, edition, deployment model, and contract. Check current licensing documentation and order documents for the exact gateway before production.

Generic connectivity, vendor-specific gateways, and third-party integration products can carry different commercial terms. Never apply a blanket license assumption across all gateways.

## 9. Oracle GoldenGate: Change Capture and Replication

Oracle GoldenGate is a platform for capturing, routing, and applying data changes across supported databases or systems. It fits:

- Near-real-time replication.
- Syncing data to reporting systems.
- Low-downtime database migrations.
- Multi-system data integration.
- Active/passive architectures or specially designed multi-directional topologies.

Simplified flow:

~~~text
Source database
      |
      | redo / transaction log
      v
GoldenGate Extract
      |
      v
Trail files
      |
      | network transfer
      v
GoldenGate Replicat
      |
      v
Target database
~~~

GoldenGate may use Extract/Replicat and additional components depending on architecture, deployment model, and version. Do not treat this simplified diagram as a complete deployment architecture.

### Replication Scope

GoldenGate can filter by:

- Database/schema/table.
- Column mapping.
- Row predicates.
- Operation type.
- Routing rules.

Filtering scope must be tested. If you filter parent tables while omitting child tables, target data loses referential integrity. If filtering by tenant, ensure every transaction and dependent table applies the same policy.

### Privileges and Security

Capture accounts need privileges to read metadata/logs and access required views/packages per version, capture mode, and configuration. Apply accounts need write privileges on target objects. Never grant `DBA` to both Extract and Replicat unless documentation explicitly requires it.

Areas to manage:

- Credential stores and secret rotation.
- TLS/encryption for data in transit.
- Read permissions on trail files.
- Network access between source, target, and GoldenGate deployments.
- Auditing of configuration changes.
- Separating GoldenGate operational accounts from DBA accounts.

### Consistency and Conflicts

Asynchronous GoldenGate replication introduces lag. Bidirectional replication requires conflict detection/resolution design, keys, sequences, and transaction ordering. Never enable bidirectional replication merely by configuring two opposing streams.

Define:

- Source of truth for each table/column.
- Conflict rules.
- Duplicate transaction handling.
- DDL replication policy.
- Unsupported data types/objects.
- Initial load and instantiation SCN.
- Lag alerts and recovery/repositioning procedures.

### GoldenGate Licensing

Oracle GoldenGate is a separately licensed product; never treat it as automatically included with Oracle Database rights just because the database has redo logs or a GoldenGate agent can connect. Metrics, deployments, topologies, cloud/on-premises rules, sources/targets, and usage rights vary by contract and product version.

Before enabling GoldenGate in production, consult the Oracle GoldenGate Licensing Information/User Manual, Oracle price lists, and signed contracts. Verify whether DR, test, development, passive targets, and auxiliary deployments are covered.

## 10. XStream and Capture/Apply Interfaces

Oracle XStream provides APIs for external applications to receive changes from Oracle or send changes into Oracle via capture/outbound and apply/inbound models.

XStream can be useful when middleware or applications must integrate directly with the transaction change stream. However, it demands deep understanding of LCRs, transaction boundaries, ordering, checkpoints, restarts, and backpressure.

Do not treat XStream as a free replacement for GoldenGate. XStream carries licensing terms tied to Oracle GoldenGate per Oracle documentation; confirm current entitlements before use.

Privileges to review:

- Dedicated capture/apply users.
- Execute privileges on XStream packages/APIs per documentation.
- Required log and dictionary access.
- Credential stores and networking.
- Operational privileges for checkpoints/restarts.

Never grant `SYSDBA` or `DBA` to an application merely to initialize a stream. Use official grant scripts for your exact release with least-privilege roles.

## 11. Advanced Queuing and Transactional Event Queues

Oracle Advanced Queuing (AQ) and Transactional Event Queues (TxEventQ, depending on release) support asynchronous messaging inside the database.

A producer enqueues a message into a queue; a consumer dequeues and processes it later. This reduces synchronous coupling between two applications.

~~~text
Producer
   |
   | enqueue
   v
Oracle Queue
   |
   | dequeue
   v
Consumer
~~~

The queue model fits when:

- Producers do not need to wait for consumers to finish.
- Retries are needed when consumers pause temporarily.
- Buffering is needed during traffic spikes.
- Two services' lifecycles should be decoupled.

### Scope and Privileges

Grant privileges per queue and API used. Producer users need enqueue rights; consumers need dequeue rights; queue admins need appropriate rights to create, alter, and monitor queues.

Do not grant queue admin privileges to every service. Separate queues by domain or service to restrict who can send/receive messages.

### Delivery Semantics

Designs must specify:

- At-most-once, at-least-once, or idempotent processing.
- Retries and backoff.
- Dead-letter/exception queues.
- Message expiration and retention.
- Ordering and grouping.
- Poison messages.
- Transaction boundaries between enqueue/dequeue and business table updates.

Never assume a message processes exactly once if a consumer can crash after executing business work yet before completing acknowledgment/dequeue. Design idempotency keys and duplicate handling.

### Licensing

AQ/TxEventQ are database features whose usage terms depend on release, edition, and configuration. Check the licensing guide and feature documentation for your exact version, especially when combined with GoldenGate, sharding, RAC, or other options. Never infer licensing from package names or the fact that creating a queue succeeds.

## 12. REST APIs and ORDS

REST APIs establish an HTTP-layer integration boundary instead of letting external systems connect directly to the database. Oracle REST Data Services (ORDS) maps REST endpoints to SQL, PL/SQL, or defined modules.

General flow:

~~~text
External application
       |
       | HTTPS / OAuth
       v
ORDS / API layer
       |
       | database session
       v
Oracle schema / PL/SQL API
~~~

REST fits when integrating via explicit API contracts, controlling requests/responses, authentication, rate limiting, and versioning.

### Endpoint Privileges

Never expose an entire schema directly. Instead:

- Create modules/resources aligned with business workflows.
- Use dedicated schemas/API owners where appropriate.
- Grant `EXECUTE` on packages or `SELECT` on restricted views.
- Map roles/OAuth scopes to operations.
- Enforce tenant and authorization checks on every request.
- Cap payload size, request rate, and timeouts.
- Protect endpoints with HTTPS and token policies.

A `GET` endpoint is not automatically read-only if underlying PL/SQL causes side effects. Review handler and package behavior carefully.

### Licensing and Product Boundaries

ORDS is a service/API tier; the underlying database still requires licensing by edition, metric, and deployment. Rights to use ORDS, Oracle Database, and any options invoked by code must be checked separately under current terms. Calling a separately licensed database feature via REST does not waive that license requirement.

## 13. Least-Privilege Matrix by Option

| Option | Local Identity | Remote/Target Identity | Privileges to Restrict |
|---|---|---|---|
| Private DB link | Schema/service owner with `CREATE DATABASE LINK` | Dedicated account on remote | `SELECT` views or `EXECUTE` specific APIs |
| Public DB link | DBA with `CREATE PUBLIC DATABASE LINK` | Fixed remote account | Avoid unless needed; never use broad accounts |
| Materialized view | Owner with MV create/refresh privileges | DB link account reading source | Read only source objects needed for refresh |
| External table | User with table creation and `READ DIRECTORY` | Oracle server OS account | Read only staging folders/files |
| Data Pump | User running job and `DIRECTORY` privileges | Source/target databases per job | Mode-specific Data Pump roles, not `DBA` by default |
| Gateway | Local integration schema | Remote gateway account | Only required objects and operations |
| GoldenGate | Capture/apply accounts | Source/target credentials | Roles matching capture/apply mode and version |
| AQ/TxEventQ | Producer/consumer identities | Queue owner/admin | Enqueue/dequeue on specific queues |
| REST/ORDS | API schema/handler | OAuth client/end-user | Scoped endpoints, packages/views, and tenants |

Actual privileges depend on release and configuration. Use official Oracle grant scripts for GoldenGate, XStream, Gateways, or corresponding components; never substitute `DBA`.

## 14. Database Links and Privileges Through PL/SQL

When a stored procedure uses a DB link, understand the PL/SQL unit's execution privileges:

- Definer-rights units execute with the owner's privileges per Oracle rules.
- Invoker-rights units execute in the invoker's context per `AUTHID CURRENT_USER` rules.
- Roles can be disabled inside named definer-rights units.
- The remote account behind the DB link must still hold privileges on remote objects.

API package example:

~~~sql
CREATE OR REPLACE PACKAGE app_api AS
  PROCEDURE read_customer(p_customer_id IN NUMBER);
END app_api;
/

CREATE OR REPLACE PACKAGE BODY app_api AS
  PROCEDURE read_customer(p_customer_id IN NUMBER) IS
    l_name VARCHAR2(200);
  BEGIN
    SELECT customer_name
      INTO l_name
      FROM customers@crm_link
     WHERE customer_id = p_customer_id;
  END;
END app_api;
/
~~~

This is an illustrative example. Verify the DB link exists in the right schema, the owner has privileges to use the link, remote credentials work, and the remote user holds `SELECT` on the object. Never grant `SELECT ANY TABLE` on remote to fix missing privileges on a single table.

## 15. Separating Privileges by Environment and Identity

Never share one credential across all environments:

| Environment | Example Identity | Principle |
|---|---|---|
| Development | `APP_DEV_INTEGRATION` | Access dev data only |
| Test | `APP_TEST_INTEGRATION` | Test data and test endpoints |
| Staging | `APP_STAGE_INTEGRATION` | Production-like, yet separate secrets |
| Production | `APP_PROD_INTEGRATION` | Narrow privileges, central secrets, audited |
| DR | `APP_DR_INTEGRATION` | Used strictly per DR topology and plan |

A production DB link must never accidentally point to a test database, or vice versa. Verify service names, `DB_UNIQUE_NAME`, PDBs, and remote accounts during deployment.

Credentials must:

- Be stored in an appropriate secret manager or wallet.
- Have an owner and lifecycle.
- Be rotated in a controlled manner.
- Have a revocation plan if exposed.
- Never appear in Git, logs, or command history.

## 16. Row-Level, Column-Level, and Tenant Scope

Schema/table privileges normally restrict only objects, not rows per tenant. If a remote account holds `SELECT` on `CUSTOMER`, it can read every row permitted by that grant.

To narrow scope:

- Publish views filtering columns/rows.
- Use package APIs checking business context.
- Use Virtual Private Database (VPD) or Row-Level Security when appropriate.
- Use Application Contexts populated from trusted sources.
- Separate schemas or databases per tenant if architecture requires.
- Pass tenant identifiers via bind variables and enforce checks in the database.

Never trust an unauthenticated `tenant_id` sent directly by a client. If all requests share one DB account, the database needs a secure context mechanism to distinguish requests/tenants.

### Views as a Data Publication Layer

Example view exposing only required columns:

~~~sql
CREATE OR REPLACE VIEW app_owner.customer_public_v AS
SELECT customer_id,
       customer_name,
       customer_status
  FROM app_owner.customers
 WHERE customer_status = 'ACTIVE';

GRANT SELECT ON app_owner.customer_public_v TO integration_reader;
~~~

Views restrict columns and rows via fixed predicates. For tenant-specific access, bind predicates to verified contexts and carefully audit bypass privileges.

### Package APIs

Instead of granting `INSERT`/`UPDATE` on tables, grant `EXECUTE` on a package exposing only valid operations:

~~~sql
GRANT EXECUTE ON app_owner.customer_api TO integration_writer;
~~~

Packages must validate inputs, tenants, business states, and transaction boundaries. `EXECUTE` on a package can still allow overly broad operations if internal code is not designed safely.

## 17. Network Scope and Connection Endpoints

Integration is not just database privileges. Restrict networking:

- Open only required hosts/ports between two systems.
- Use service names targeting the right PDB.
- Never expose database listeners directly to the Internet.
- Use TLS/TCPS where appropriate.
- Use VPNs, private networks, or service meshes per architecture.
- Restrict outbound connections from databases/gateways.
- Govern DNS, certificates, and endpoint rotations.
- Monitor connection sources and anomalies.

For REST, restrict endpoints and API gateways. For GoldenGate, open only ports needed between deployment components. For Gateways, restrict connections from the gateway host to the remote database.

## 18. Licensing: Distinguishing Databases, Options, and Products

Oracle licensing can span multiple layers:

1. **Database edition:** e.g., Standard Edition 2 or Enterprise Edition per contract and release.
2. **Database options:** add-on features that may require separate licenses.
3. **Management packs:** certain monitoring/diagnostic tools carrying separate license terms.
4. **Separate integration products:** e.g., Oracle GoldenGate or a specific gateway.
5. **Metrics and deployments:** Processor, Named User Plus, or other metrics; on-premises, cloud, virtualized, DR, and non-prod environments.

A feature being pre-installed or visible in an interface does not prove the organization holds an entitlement. Conversely, calling a feature in code is not always sufficient to determine licensing; verify actual usage, edition, release, and contracts.

### Principles for Checking Licenses

- Identify the exact product/option and version.
- Read the Licensing Information/User Manual for your release.
- Cross-check Oracle price lists and order documents/contracts.
- Confirm applicable metrics and license quantities.
- Check production, test, development, standby, and DR environments.
- Confirm virtualization, cloud, and disaster recovery rules.
- Preserve approval evidence before production go-live.
- Consult a license specialist/Oracle when terms are unclear.

Never rely on a blog post, forum answer, or technical installation outcome as final legal authority.

## 19. Licensing Guidance Table by Option

The table below provides technical orientation on what must be verified. It does not replace contracts, price lists, or official licensing advice.

| Option | Licensing Items to Verify |
|---|---|
| Oracle-to-Oracle DB link | DB links are a database capability; each database deployment must still be licensed under its edition/metric |
| Distributed SQL / 2PC | Confirm database edition/version and any architecture-related options; do not infer from successful execution |
| Materialized views | Confirm feature rights in your edition/release and dependent options such as Partitioning if used in the design |
| Basic external tables | Confirm access drivers and specific features; specialized drivers or external integrations may have separate terms |
| Data Pump | Logical export/import utility; source/target databases and used options must still carry proper entitlements |
| Database Gateway | Confirm exact gateway product, target platform, version, and contract; never generalize across all gateways |
| GoldenGate | Separately licensed product; verify metrics, sources/targets, deployments, topologies, and non-prod environments |
| XStream | Check GoldenGate-tied licensing terms per current Oracle documentation |
| AQ / TxEventQ | Confirm release, edition, and queue features used; evaluate other options if the architecture relies on them |
| REST / ORDS | Confirm rights to use ORDS and underlying database/options; APIs do not waive database licensing |
| Active Data Guard | If using Active Data Guard option features, confirm separate entitlement; do not equate with all basic Data Guard functions |

### Special Areas Requiring Attention

**GoldenGate:** usually a separately licensed product. Identify deployment counts, sources/targets, topologies, and metrics per contract.

**XStream:** should not be treated as a license-free alternative to GoldenGate. Check Oracle's licensing guide for XStream and your running release.

**Gateway:** gateway products for specific target systems can have separate terms. Verify the exact SKU/product instead of searching only for "Heterogeneous Services."

**Active Data Guard:** capabilities such as real-time query on a physical standby belong to the Active Data Guard option. Distinguish base Data Guard from additionally licensed capabilities.

**Advanced Security:** features such as Transparent Data Encryption or network encryption have license conditions varying by release and licensing program. When integrations require encryption, verify specific features and entitlements.

**Partitioning:** when using partitioned tables in materialized views, staging, or replication targets, verify the Partitioning option is licensed and deployed under the proper metric.

## 20. Controlling Licensing Across the Integration Lifecycle

License reviews should occur before designs are finalized and before enabling features in production:

1. List all planned technologies.
2. Specify features, options, products, and versions.
3. Document sources/targets, database counts, nodes, deployments, and environments.
4. Identify applicable metrics per contract.
5. Check which edition/option governs each used feature.
6. Verify test, DR, standby, cloud, and virtualization coverage.
7. Archive entitlement evidence and approvers.
8. Re-verify whenever topologies or versions change.

Do not wait for an audit to discover which GoldenGate deployments or options are running. New integrations can change license footprints even when core data and applications stay unchanged.

### Feature Usage Views Are Not Contracts

Oracle provides views for tracking feature usage, such as `DBA_FEATURE_USAGE_STATISTICS` in supported releases. They can help identify features the database recorded as used:

~~~sql
SELECT name,
       detected_usages,
       currently_used,
       first_usage_date,
       last_usage_date
  FROM dba_feature_usage_statistics
 ORDER BY name;
~~~

This view is a technical investigation aid, not a sole legal determination of entitlements or payment obligations. It has limitations in detection, update timing, and mapping features to licenses. Always verify against contracts, licensing guides, and license owners.

## 21. Choosing an Option by Real Need

| Need | Commonly Considered Option | Questions to Answer |
|---|---|---|
| On-demand remote query | DB link | Are network dependencies and remote availability acceptable? |
| Fast-read reporting with tolerable lag | Materialized view | How often to refresh, complete or fast? |
| Batch file loading | External table | Who creates files, format, encoding, and atomic handoff? |
| Batch schema or table movement | Data Pump | What downtime, snapshot consistency, and remapping apply? |
| Accessing non-Oracle databases | Gateway | Which driver, data types, pushdown, transactions, and licenses? |
| Continuous replication, low downtime | GoldenGate | Licensing, capture/apply design, lag, and conflict strategy? |
| Decoupling producer/consumer | AQ/TxEventQ | How are retries, duplicates, ordering, and retention handled? |
| API for multiple external systems | REST/ORDS | How are authentication, authorization, rate limits, and contracts handled? |

Do not pick GoldenGate just because you need one remote query; likewise, do not pick a DB link for a replication stream that must keep working during temporary source outages. Each technology addresses a different form of coupling.

## 22. Example of a Secure Integration Design

Suppose an order application must:

- Read customer catalogs from CRM.
- Send order events to the payment system.
- Sync reporting data to a data warehouse.
- Ingest nightly catalog files.

Responsibilities can be split as follows:

| Need | Design | Privilege Scope |
|---|---|---|
| Read CRM | Private DB link or API | Remote account has `SELECT` only on customer view |
| Emit events | AQ/TxEventQ or message broker API | Producer only enqueues to order queue |
| Reporting | Materialized view or GoldenGate by freshness/volume | Reader queries view only; GoldenGate capture/apply accounts via official scripts |
| Catalog files | External table | `READ` on staging `DIRECTORY` and minimal filesystem permissions |

Before production:

- Confirm every database deployment is licensed.
- Check gateways/GoldenGate/options if used.
- Separate dev/test/prod credentials.
- Restrict networking.
- Verify row/tenant scoping.
- Verify retries, consistency, and auditing.
- Prepare runbooks for when remote systems are unavailable.

## 23. Post-Deployment Verification

Once the integration is live, verify:

### Scope

- Only intended schemas/objects are accessible.
- No unexpected public DB links or `PUBLIC` grants exist.
- Row/column/tenant filters enforce properly.
- Services and PDBs point to the right environments.

### Privileges

- Remote users hold only required privileges.
- Local users lack unnecessary `DBA` or `ANY` privileges.
- `DIRECTORY` objects are granted only to appropriate users/jobs.
- GoldenGate capture/apply run under dedicated accounts.
- Queue producers/consumers interact only with their own queues.
- REST scopes map strictly to intended endpoints.

### Operations

- Alerts exist when DB links/gateways lose connectivity.
- Refresh status and lag monitoring exist for MVs/GoldenGate.
- Dead-letter/retry handling exists for queues.
- File staging and external tables are controlled.
- Logs and audits meet requirements.
- Recovery and reconciliation runbooks exist.

### Licensing

- Products/options/versions are documented.
- Metrics and deployments are confirmed.
- DR/test/cloud/virtualization coverage is reviewed.
- Approval evidence and owners are recorded.

## 24. Common Design Mistakes

**Using a public database link for all applications:** every user can reference the link and a fixed remote account becomes a broad access gateway. Prefer private links and remote views/APIs.

**Granting `SELECT ANY TABLE` on remote:** an integration needing only a few tables ends up able to read multiple schemas. Provision a dedicated remote account and views.

**Using a DB link for continuous replication:** synchronous queries depend on remote availability and create tight coupling. Evaluate queues or replication platforms.

**Assuming materialized views always fast refresh:** fast refresh has strict prerequisites. Check queries, logs, and releases before committing to SLAs.

**Assuming external tables read files from client machines:** the Oracle server reads files via `DIRECTORY` objects. Ensure files live on the right host with OS permissions.

**Confusing `TABLESPACES` with transportable tablespaces:** logical export differs from moving datafiles.

**Using a Gateway while ignoring type mapping:** data types, SQL functions, and transaction behavior can differ across systems.

**Using GoldenGate without defining conflict ownership:** bidirectional replication creates conflicts and inconsistent data.

**Using XStream to bypass GoldenGate licensing:** verify XStream licensing terms in Oracle documentation.

**Granting `DBA` to capture/apply accounts:** overly broad privileges magnify blast radius if credentials leak.

**Believing a feature working means it is licensed:** technical capability and commercial entitlement are separate.

**Using feature usage views as final licensing proof:** views are only one piece of technical evidence.

## 25. Integration Design Checklist

- [ ] Identify source, target, CDB/PDB, and services.
- [ ] Define schema, table, column, row, and tenant scopes.
- [ ] Choose synchronous, asynchronous, batch, or replication model.
- [ ] Define consistency, ordering, retry, and duplicate handling.
- [ ] Select technologies and document rationale.
- [ ] Define local identities, remote identities, and owners.
- [ ] Grant minimal object privileges/roles.
- [ ] Control private/public DB links and database link credentials.
- [ ] Restrict `DIRECTORY` and filesystem access.
- [ ] Verify gateway type mappings and pushdown behavior.
- [ ] Verify GoldenGate/XStream capture/apply permissions.
- [ ] Verify REST authentication and API authorization.
- [ ] Confirm edition, option, product, metric, and deployment licenses.
- [ ] Check test, DR, cloud, and virtualization coverage.
- [ ] Establish monitoring, auditing, incident, and recovery runbooks.
- [ ] Archive technical evidence and license approvals.

## 26. Conclusion

Oracle integration options differ in scope, privileges, and operational behavior. DB links serve remote access; materialized views store refreshable copies; external tables read files; Data Pump performs logical movement; Gateways access heterogeneous systems; GoldenGate continuously captures/applies changes; AQ/TxEventQ decouples producers and consumers; REST establishes API boundaries.

Secure design starts with clearly defining schemas, objects, rows, tenants, operations, and latency needs. Separate local/remote identities, prefer private links, remote views, or package APIs, restrict `DIRECTORY`, queue, and endpoint privileges, and protect credentials and networking. Distributed transactions, bidirectional replication, gateways, and refreshes each carry their own consistency and recovery limits.

On licensing, never infer entitlements from pre-installed features or commands succeeding. Identify exact database editions, options, products, versions, metrics, sources/targets, prod/test/DR footprints, and deployment models. GoldenGate, XStream, Gateways, Active Data Guard, and certain security features require explicit verification against current licensing documentation and contracts. Feature usage views only aid investigation; entitlement decisions must rest on official documentation and formal approval.
