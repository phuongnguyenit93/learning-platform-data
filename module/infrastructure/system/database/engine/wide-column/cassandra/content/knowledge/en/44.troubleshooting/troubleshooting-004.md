# Non-Existent Keyspace/Table and Schema Disagreement in Apache Cassandra

> **Chapter:** Troubleshooting  
> **Focus:** Distinguishing **a keyspace/table that was genuinely never created**, mismatched names/namespaces, insufficient permissions, stale Java Driver metadata, and **schema disagreement** across Cassandra nodes. Hands-on guidance with CQL, `cqlsh`, `nodetool`, Java Driver 4.x, and Java 17. All schema creation/deletion examples must run only on **lab clusters or authorized namespaces**. In production, prioritize reading state, halting rollouts, and remediating through migration workflows.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Explain the meaning of `Keyspace ... does not exist`, `unconfigured table`, and `Undefined column name`, and distinguish them from `Unauthorized`, `Unavailable`, and timeouts.
2. Identify the exact keyspace/table using **fully qualified CQL names**, case-folding rules, and quoted identifiers.
3. Inspect schemas via `system_schema.keyspaces`, `system_schema.tables`, `system_schema.columns`, and `cqlsh` `DESCRIBE` commands.
4. Distinguish **DDL accepted by a coordinator** from **schema agreement**, refreshed client metadata, and **data actually servable at the target CL**.
5. Read `system.local.schema_version`, peer metadata, and `nodetool describecluster` output to detect schema version divergence; state the limits of each view.
6. Isolate **single-coordinator** errors from cluster-wide errors, DC/rack/token errors, and deployment/application config errors.
7. Properly use `CqlSession.checkSchemaAgreement()`, `ExecutionInfo.isSchemaInAgreement()`, and `session.getMetadata()` in Java Driver 4.x without misusing cached metadata.
8. Design migrations with a **single writer, explicit DDL ordering, checkpoints, and bounded retries**, avoiding multiple service pods racing to alter schemas at startup.
9. Write integration tests that create a keyspace/table, wait for agreement with a deadline, prepare CQL, write/read at target CL, and assert exact data correctness.
10. Build a GO/HOLD/STOP runbook covering data protection, RBAC permissions, multi-DC, DOWN nodes, and prolonged schema disagreement.
11. Recognize cases where **`DROP`/`TRUNCATE`/mass node restarts must never be used** as a "quick fix".
12. Collect sufficiently detailed evidence for DBA/SRE verification and handoff without leaking credentials or PII.

**`DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` service context:** Cassandra is a distributed wide-column database; partition keys map to tokens/natural replicas, keyspaces define replication strategies and RF, and CL governs read/write acknowledgements. Schema determines **how CQL is interpreted**, yet schema agreement itself **does not replace repair, compaction, data recovery, or CL verification**. Java examples focus on Java Driver 4.x and do not modify production data.

## 2. Two Incident Categories to Separate Immediately

**Category A — Unrecognized object:** The coordinator rejects CQL because the referenced keyspace, table, column, type, index, or function does not exist in **the schema currently visible to that node**, or the client sent the wrong name.

**Category B — Schema disagreement:** Cassandra nodes do not agree on the same schema version at a given point in time, typically during migration/DDL propagation, un-converged nodes, or network/topology/schema processing failures. One node may know the new table while another does not.

~~~text
                    Java application / cqlsh
                               |
                         Query to node X
                               |
                   X resolves keyspace/table?
                       /                 \
                     NO                  YES
                       |                   |
            unconfigured / does not      Check schema definition
                       |                    |
          +------------+----------+         v
          |                       |   Coordinator runs CQL
    Object absent           Some nodes know,       |
    cluster-wide            others do not          v
          |                       |         CL/replicas/data path
          v                       |         (may fail separately)
    Missing migration,          Schema
    namespace, name          disagreement
~~~

**Crucial point:** `InvalidQueryException: unconfigured table` does not by itself prove the table is absent across the entire cluster. It proves **the responding coordinator could not resolve the object for its request/namespace**. Always inspect keyspace, identifier spelling, and schema views across **the relevant nodes**.

### 2.1. Same Error, Multiple Causes

| Symptom | Possible Cause | How to Distinguish |
|---|---|---|
| `Keyspace 'orders' does not exist` | Migration not run, wrong cluster, case mismatch | List `system_schema.keyspaces` and verify cluster/DC |
| `unconfigured table orders_by_id` | Table not created, wrong current keyspace, one node has stale schema | Use fully qualified name; query `system_schema.tables` on multiple nodes |
| `Undefined column name status` | ALTER migration hasn't propagated, Java code ahead of schema, typo | `system_schema.columns`, app version, DDL history |
| Query works in `cqlsh` but fails in Java | Different cluster/keyspace/role/DC, stale driver metadata, prepared schema mismatch | Compare contact points, `withKeyspace`, auth, query string, coordinator |
| Errors appear only after new deploy | Startup race between migration and app traffic | Check DDL completion, schema agreement, and readiness gates |
| Some requests PASS, others FAIL | Coordinators have different schema views, routing/caches, mixed DC | Group errors by coordinator/DC and `schema_version` |
| `SELECT` succeeds yet returns 0 rows | Table exists, but data/CL/partition differs | Data oracle, PK/RF/CL; not schema disagreement |
| `Unauthorized` | Role lacks `SELECT`/`CREATE`/`ALTER` | RBAC issue; do not call it "table missing" |

### 2.2. Three Guiding Questions Before Making Changes

1. **Right target?** Are cluster, environment, contact points, local DC, keyspace, table, role, and app version all right?
2. **Do all nodes see the same schema?** Compare schema versions/metadata across appropriate vantage points; are any nodes DOWN or partitioned?
3. **Is the data ready?** Once schema aligns, do reads/writes at the required CL succeed with expected keys/values?

Answering these three clearly prevents most dangerous "fixes", such as running `DROP TABLE` and recreating it merely because an app reported `unconfigured table`.

## 3. Keyspace, Table, Schema, and Data Are Distinct Layers

### 3.1. Keyspace Defines Namespace and Replication

~~~sql
CREATE KEYSPACE IF NOT EXISTS catalog_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};
~~~

This example is for a **single-node lab only**. A keyspace holds:

- The namespace name referenced as `catalog_lab.orders_by_id`.
- Replication strategy and RF; multi-DC production typically uses `NetworkTopologyStrategy`.
- Metadata for types, tables, materialized views, and related definitions.

Creating a keyspace does not create tables. Raising RF does not automatically populate historical data onto new replicas. Schema agreement is not repair.

### 3.2. Table Defines Columns and Primary Key

~~~sql
CREATE TABLE IF NOT EXISTS catalog_lab.orders_by_id (
  tenant_id text,
  order_id uuid,
  status text,
  revision int,
  PRIMARY KEY ((tenant_id), order_id)
);
~~~

`PRIMARY KEY ((tenant_id), order_id)` means `tenant_id` is the partition key and `order_id` is the clustering key. A `SELECT` filtering only on `order_id` does not become valid just because the table exists; Cassandra's query model and primary-key rules still apply.

### 3.3. Three States That Can Diverge

~~~text
DDL committed/acknowledged?
         |
         v
Schema agreed among currently UP nodes?
         |
         v
Data migrated/restored/repaired and query at CL succeeds?
~~~

For instance, right after creating an empty table, all nodes may be **schema-agreed** immediately, yet an API expecting 10 million historical rows will receive nothing. That is a **data migration/recovery problem**, not `schema disagreement`. Conversely, SSTable data may still sit on disk while schema no longer shows the table; never manually swap SSTables around to patch broken metadata without an approved backup/restore runbook.

## 4. CQL Naming: Default Keyspace, Fully Qualified, and Quoted Identifiers

### 4.1. `USE` in `cqlsh` Is Session Context, Not a Migration

~~~sql
USE catalog_lab;
SELECT status FROM orders_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Without `USE catalog_lab`, or if the session points to another keyspace, `orders_by_id` resolves in the wrong namespace. Safer diagnostic form:

~~~sql
SELECT status FROM catalog_lab.orders_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

**When writing Java Driver 4.x code**, prefer **fully qualified CQL** for migrations/probes or configure the keyspace explicitly on the session builder. Avoid issuing ad-hoc `USE` statements from application pods sharing connection pools; `cqlsh` session context and driver pool management behave differently.

### 4.2. Unquoted Identifiers Are Lowercased

~~~sql
CREATE TABLE catalog_lab.OrderEvents (
  tenant_id text PRIMARY KEY,
  status text
);
~~~

Unquoted `OrderEvents` folds to lowercase `orderevents`. Therefore:

~~~sql
SELECT status FROM catalog_lab.orderevents
WHERE tenant_id = 'tenant-a';
~~~

references the table correctly. However:

~~~sql
SELECT status FROM catalog_lab."OrderEvents"
WHERE tenant_id = 'tenant-a';
~~~

references a **case-sensitive** table literally named `OrderEvents`, not `orderevents`, and will report an unconfigured table.

### 4.3. Quoted Names Preserve Case and Special Characters

~~~sql
CREATE TABLE catalog_lab."OrderEvents" (
  "TenantId" text PRIMARY KEY,
  status text
);

SELECT status FROM catalog_lab."OrderEvents"
WHERE "TenantId" = 'tenant-a';
~~~

With quoted identifiers, spelling and casing must match identically in **every** CQL and driver call. Use `CqlIdentifier.fromCql`/`fromInternal` appropriately when looking up Java metadata; never call `.toLowerCase()` blindly on a quoted name expecting it to match.

**Recommendation:** Use unquoted `lower_snake_case` names for new schemas to avoid errors and query-builder friction unless backward compatibility dictates otherwise.

### 4.4. Current Keyspace, Wrong Keyspace, Wrong Cluster

~~~text
staging cluster:
  catalog_lab.orders_by_id exists

production cluster:
  catalog_lab.orders_by_id absent

Application config:
  contact_points = production
  expected_keyspace = catalog_lab

Result:
  unconfigured table
~~~

This is **not schema disagreement** between staging and prod; they are two independent clusters with separate schemas. Verify `cluster_name`, contact points, DCs, credentials, and deployment targets before touching schemas.

## 5. How Does Schema Propagate in Cassandra?

### 5.1. There Is No Single "Master SQL Schema" to Edit Directly

Cassandra is peer-to-peer distributed; every node maintains **local schema metadata** and exchanges schema versions/definitions with peers. CQL DDL can be submitted to any authorized coordinator, after which the schema propagates so remaining nodes converge toward agreement.

~~~text
                 Deployment / migration runner
                              |
                       CREATE TABLE
                              |
                              v
                      Coordinator A
                              |
                   Apply local schema change
                              |
                   Gossip/schema propagation
                         /            \
                        v              v
                     Node B          Node C
                     update          delayed
                        |              |
                  schema_version   old_version
                        \              /
                         \            /
                  SCHEMA DISAGREEMENT
                              |
                      C receives updates
                              |
                    SCHEMA AGREEMENT
~~~

Normally this is a **transient state** right after DDL; not every second of differing schema versions is an outage. However, if divergence persists past a defined **wait budget**, or queries keep throwing `unconfigured table`, it becomes an incident to investigate.

### 5.2. What Does `schema_version` Represent?

Each node has a `schema_version` representing its local schema view. When **live nodes** advertise the same schema version, it is a strong signal that schema metadata has converged. However:

- It is not the Java Driver version, Cassandra binary version, or migration file version.
- It is not a Git commit ID or DDL sequence number.
- It is not a checksum proving SSTables or data rows are identical.
- It does not guarantee **DOWN** nodes received the new schema.
- It does not prove the app is connected to the **right cluster**.

**Never** directly edit `system.local.schema_version` or system schema tables to "make UUIDs match". Cassandra manages those internally; manual edits can corrupt metadata and complicate recovery.

### 5.3. Coordinator Handling Requests During the Convergence Window

Suppose nodes A/B/C are in the same cluster and `catalog_lab.orders_by_id` was just created:

~~~text
T0    DDL sent to A
T1    A knows new table; B,C may not
T2    SELECT via A --> can resolve table
T3    SELECT via C --> unconfigured table
T4    B,C receive schema updates
T5    agreement reached
T6    SELECT via A/B/C --> schema resolution consistent
~~~

These milestones are conceptual, not an SLA that "all nodes sync in X ms". In many setups, the driver **waits for agreement within a budget** after schema-changing requests; that reduces races but does not eliminate every failure mode.

### 5.4. DOWN Nodes and Agreement Scope

~~~text
Node A UP  schema V2
Node B UP  schema V2
Node C DOWN (last known V1)

UP-node schema agreement: may PASS
All-nodes-ready-to-serve-new-schema: NOT YET PASS
~~~

When C comes back up, verify it receives the new schema and serves properly before declaring the whole cluster ready. Even if A+B still serve read/write CL via quorum, **the next step of a rolling restart** must enforce a gate to avoid losing another replica.

## 6. What Does Schema Agreement Differ From?

| State | Signal | Does Not Guarantee |
|---|---|---|
| Process ready | Node JVM/container running | CQL open; schema/data ready |
| Native transport ready | Port `9042`/auth/handshake works | Application tables exist |
| DDL request accepted | Coordinator finished DDL command | UP nodes have converged |
| **Schema agreement** | UP nodes share identical schema version | DOWN nodes updated, historical data synced |
| Driver schema metadata updated | Client sees new keyspace/table | All coordinators updated |
| Keyspace/table queryable | Coordinator resolves CQL | Replicas satisfy CL, expected rows exist |
| Data available at CL | CQL reads/writes meet CL | Full data migration/restore complete |
| Business readiness | CQL meets CL, expected values/versions, and SLO | Full cluster partition coverage if probing only one key |

### 6.1. Why `CREATE TABLE IF NOT EXISTS` Does Not Prove Correct Schema

~~~sql
CREATE TABLE IF NOT EXISTS catalog_lab.orders_by_id (
  tenant_id text,
  order_id uuid,
  status text,
  revision int,
  PRIMARY KEY ((tenant_id), order_id)
);
~~~

If the table already exists with a **different definition** (e.g., missing `revision` or a different primary key), `IF NOT EXISTS` lets the DDL succeed silently **without checking** whether the existing schema matches expectations. Post-migration, inspect `system_schema.columns`/driver metadata and run contract CQL probes.

### 6.2. Agreement Does Not Replace Repair

Increasing a keyspace's RF from 2 to 3 reaches schema agreement quickly, yet historical data is not automatically replicated onto the new replica. You still need **repair/streaming and data verification** per your version's operational runbook. Similarly, restoring a snapshot can yield perfect schema agreement while missing some SSTables.

### 6.3. Agreement Does Not Make Invalid CQL Valid

~~~sql
SELECT amount
FROM catalog_lab.orders_by_id
WHERE tenant_id = 'tenant-a';
~~~

If the table has no `amount` column, the query will continue throwing `Undefined column` even when all nodes are schema-agreed. **Never retry infinitely** on permanent errors like wrong column names, wrong table names, missing permissions, or queries lacking partition keys.

## 7. Common Causes: Migrations, Configuration, Network, and Nodes

### 7.1. Application Deployed Before Migration

~~~text
Release v2 Java expects column revision
                  |
                  v
Traffic shifted to v2
                  |
Migration ALTER TABLE ADD revision hasn't run
                  |
            Undefined column
~~~

**Prevention:** Treat migrations as an owned deployment step; gate on DDL/agreement before shifting traffic, and keep schema changes backward-compatible across old and new binaries.

### 7.2. Multiple App Pods Running DDL Concurrently at Startup

~~~text
Pod A --- CREATE TABLE ----------> Coordinator X
Pod B --- ALTER TABLE ADD col ---> Coordinator Y
Pod C --- CREATE INDEX ----------> Coordinator Z
            |                       |
       Conflicting/overlapping schema modifications
            |
     Disagreement / validation errors / races
~~~

Cassandra schema changes are cluster-wide operations, **not** isolated per-pod transactional migrations. Running multiple migration runners concurrently triggers races, schema churn, and retry storms. Use a **single migration owner**, reliable locking/leader election (usually in the deployment control plane), versioned migrations, and schema+data gates.

### 7.3. Node DOWN or Gossip/Communication Partitioned

If a node is unreachable from peers during DDL, it may retain an old schema version. After recovery, Cassandra generally converges schemas, though persistent network faults leave prolonged divergence. Check ring/gossip/network/internode TLS and logs; **never mass-restart the entire cluster**.

### 7.4. Mixed Cassandra Versions or Incompatible Schema Features

During a rolling upgrade between versions, DDL using features supported only on newer nodes may fail or fail to apply uniformly on older nodes. For types, indexes, and compaction options, verify release notes and upgrade compatibility for **your exact version pair**; never assume a command working on a new node is safe cluster-wide mid-upgrade.

### 7.5. Wrong Cluster, Namespace, or Permissions

One pod points to staging while another points to production; one pod sets `withKeyspace("catalog_lab")` while another omits it; or a session runs under an account lacking read permissions on schema/user tables. These symptoms **look like schema errors** without being node-to-node disagreement in the same cluster.

### 7.6. Driver Metadata Lags Behind Schema Changes

Java Driver 4.x keeps a local metadata snapshot, listens for schema-change events, and refreshes metadata per driver configuration. Right after DDL, a **previously captured** snapshot remains stale. Never assign `Metadata oldMetadata = session.getMetadata()` once and poll **that same object** forever. Re-fetch `session.getMetadata()` after agreement/refresh settles, and distinguish stale client metadata from server rejections.

### 7.7. Cassandra Fails While Applying Schema

Other causes include disk/GC/CPU pressure, thread-pool backlogs, invalid schema mutations, internode messaging failures, DNS/broadcast address issues, or version-specific bugs. When schema disagreement persists, **collect timestamped evidence by coordinator and peer**, and never "fix" it by editing `system_schema` tables manually.

## 8. Diagnostic Flowchart from a Failing Request

~~~text
       Application reports keyspace/table not found
                        |
           Confirm query, CL, cluster, DC, role
                        |
            Using fully qualified CQL?
                 /               \
                NO                YES
                |                  |
       Fix namespace/case          |
                |                  v
          Check from cqlsh   Works with admin yet
          same cluster/role? service role fails?
                               /        \
                              YES        NO
                               |          |
                         RBAC issue       v
                                   Inspect system_schema
                                            |
                               Object exists on coordinator?
                                 /                \
                                NO                YES
                                |                  |
                           Migration?        Wrong columns?
                           Wrong cluster?      /       \
                             |                YES       NO
                             v                 |         |
                      Compare schema       Schema     Driver
                      versions across     migration  metadata/
                      UP peer nodes       ordering   prepared/CL
                             |
                   Versions differ/stale?
                      /           \
                     YES          NO
                      |            |
               Hold schema        Investigate
               migration,        wrong query/
               gossip/logs        schema version
                      |
               Agreement & CQL probes PASS?
                      /             \
                    YES              NO
                     |                |
              Enable canary      HOLD/ESCALATE
              after data CL      do not DROP/
              correctness       TRUNCATE/repair blindly
~~~

**Every branch starts by confirming the exact cluster and role.** Having superuser `cqlsh` succeed does not prove the Java service role can prepare statements or read data.

## 9. Read-Only Diagnostic CQL Suite

**Convention:** In production, prefer logging in with a read-only diagnostic account holding minimum required permissions, and never expose secrets in command-line history. When a coordinator is suspected of being stale, connect `cqlsh` **directly to that node's endpoint** (where networking/auth permit) and run the same queries. **Never** take one read from one node as representative of every node.

### 9.1. Identify the Cluster/DC/Node Serving CQL

~~~sql
SELECT cluster_name, data_center, host_id,
       listen_address, native_protocol_version, release_version,
       schema_version
FROM system.local;
~~~

`system.local` columns vary by release; if a column is missing, run:

~~~sql
DESCRIBE TABLE system.local;
SELECT cluster_name, data_center, host_id, schema_version
FROM system.local;
~~~

**Do not** rely solely on `cluster_name`: multiple environments may accidentally share the same name. Cross-check addresses, DCs, host IDs, TLS/cert identity, and deployment registries.

### 9.2. List Visible Keyspaces

~~~sql
SELECT keyspace_name, durable_writes, replication
FROM system_schema.keyspaces;

SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'catalog_lab';
~~~

If the keyspace is absent on this node:

- Verify `catalog_lab` casing and quoting.
- Confirm this is the target cluster, not a node from another environment.
- Inspect migration logs and peer schema versions.
- If other UP nodes see the keyspace, suspect unconverged schema.
- Do not run `CREATE KEYSPACE` yourself in production if a migration owner manages schemas; escalating/holding is safer.

### 9.3. List Tables and Columns

~~~sql
SELECT keyspace_name, table_name
FROM system_schema.tables
WHERE keyspace_name = 'catalog_lab';

SELECT keyspace_name, table_name, column_name,
       kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'catalog_lab'
  AND table_name = 'orders_by_id';
~~~

Compare the live table against the schema contract: primary-key columns, clustering order, UUID/text/int types, and table/index/view options—not just whether the table name exists. If CQL throws `Unknown identifier revision` while `system_schema.columns` on your chosen node shows `revision`, check **which coordinator Java actually hit** and the DDL applied timeline.

### 9.4. Check UDTs, Indexes, and Views When Relevant

~~~sql
SELECT keyspace_name, type_name
FROM system_schema.types
WHERE keyspace_name = 'catalog_lab';

SELECT keyspace_name, table_name, index_name, kind
FROM system_schema.indexes
WHERE keyspace_name = 'catalog_lab';

SELECT keyspace_name, view_name, base_table_name
FROM system_schema.views
WHERE keyspace_name = 'catalog_lab';
~~~

Metadata layout varies by Cassandra version and feature support; if suspecting Storage-Attached Index/SAI issues, check plugin/version compatibility and index schema rather than claiming "table missing" because an index query is unsupported. For materialized views, base-table schema agreement and view build/catch-up are **separate steps**.

### 9.5. `DESCRIBE` in `cqlsh`

~~~text
cqlsh> DESCRIBE KEYSPACES;
cqlsh> DESCRIBE KEYSPACE catalog_lab;
cqlsh> DESCRIBE TABLE catalog_lab.orders_by_id;
cqlsh> DESCRIBE TABLES;
~~~

`DESCRIBE` is a **`cqlsh` client command**, not a standard CQL statement accepted by every Java Driver `session.execute("DESCRIBE ...")`. From Java, inspect driver metadata or query `system_schema`. In production, avoid pasting full schemas into public tickets if names/annotations contain sensitive info.

### 9.6. Compare Peer Schema Versions

~~~sql
SELECT schema_version FROM system.local;

-- On versions that provide system.peers:
SELECT peer, data_center, host_id, schema_version
FROM system.peers;
~~~

Cassandra 4.x/5.x introduces `system.peers_v2` with address/port columns that vary by version. Before querying it, run `DESCRIBE TABLE system.peers_v2;` to see available fields. **Do not** assume a single `system.peers` query in every version lists all nodes or reflects instantaneous gossip state: `system.peers`/`peers_v2` store **the node's persisted peer metadata**, whereas live agreement should be cross-checked with `nodetool describecluster`, the driver, and direct node queries.

If node A's local `schema_version` differs from node B's local `schema_version`, that is direct evidence of disagreement. If peer metadata on A looks stale while local versions on A and B already match, do not declare ongoing cluster disagreement solely from one peer table.

### 9.7. Read-Only Business Probe After Schema Is Confirmed

~~~sql
CONSISTENCY ONE;

SELECT status, revision
FROM catalog_lab.orders_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

`ONE` is appropriate only in an RF1 lab. In production, use the **application's actual CL** (e.g., `LOCAL_QUORUM` on NTS RF3) and verify expected values/revisions. A zero-row query without errors does not prove data migration finished.

## 10. `nodetool` and Topology/Schema Observation

### 10.1. Initial Command Set

~~~bash
nodetool status
nodetool describecluster
nodetool gossipinfo
nodetool tpstats
nodetool netstats
~~~

These commands answer **different** questions:

| Command | What It Shows | Limitation |
|---|---|---|
| `status` | Up/Down + Normal/Joining/Leaving/Moving, DC/rack, tokens | `UN` does not guarantee schema agreement |
| `describecluster` | Cluster name, snitch, peer schema versions from `nodetool`'s view | Does not prove data on disk is right |
| `gossipinfo` | Gossip endpoint states, including version-dependent schema/state info | Verbose; does not prove a coordinator can execute queries |
| `tpstats` | Active/pending/dropped messages per executor | Backlogs can stall schema propagation or requests |
| `netstats` | Streaming/network activity | Completed streaming does not verify data correctness |

`nodetool` requires JMX access and operator permissions; being unable to reach JMX from an app host is an environment access boundary, **not** proof that Cassandra is DOWN.

### 10.2. Reading `describecluster`

**Simulated** example:

~~~text
Cluster Information:
        Name: OrdersCluster
        Snitch: org.apache.cassandra.locator.GossipingPropertyFileSnitch
        ...
Schema versions:
        11111111-1111-1111-1111-111111111111:
          /10.1.0.11
          /10.1.0.12
        22222222-2222-2222-2222-222222222222:
          /10.1.0.13
~~~

This is **evidence of version disagreement** from the queried node's perspective. When one node holds an older version, check whether it is the coordinator throwing `unconfigured table`, inspect logs/connectivity, and allow a **bounded wait** if DDL just ran. Never "fix" it by manually copying schema version UUIDs.

### 10.3. `UN` Does Not Equal Converged Schema

~~~text
Status:
  A UN
  B UN
  C UN

Schema versions:
  A V2
  B V2
  C V1

=> Node states OK yet schema agreement FAILS
~~~

**Conversely**, all UP nodes sharing a schema version does not ensure a DOWN node knows the new table upon rejoin, nor that replicas at `LOCAL_QUORUM` hold expected data. Keep node health and schema/data readiness separate.

### 10.4. Encountering `UJ` or `DN` Nodes

`UJ` means Up/Joining; `DN` means Down/Normal in gossip. Rollouts and migrations must account for:

- A `UJ` node may not have finished bootstrapping/streaming and is not ready to serve its new token ranges.
- A `DN` node may miss schema updates; agreement among UP nodes can still PASS.
- With RF3 and `LOCAL_QUORUM`, one DOWN replica can still allow queries to succeed via the remaining two, yet you **must not** start the next rolling restart while resilience margin is reduced.
- Never run `decommission`, `removenode`, or `repair` merely because schema versions differ without confirming topology and following runbooks.

### 10.5. Logging and Time Correlation

Collect Cassandra logs around the DDL window:

~~~text
T0 UTC - migration runner starts
T1 UTC - CREATE/ALTER dispatched to coordinator
T2 UTC - DDL completion + schema agreement observation
T3 UTC - Java PREPARE/EXECUTE fails/succeeds
T4 UTC - nodetool describecluster snapshot
T5 UTC - CQL system.local.schema_version per node
~~~

Look first for events involving **schema migration, schema pull/push, dropped gossip/internode messages, write/read failures, and node joining**, noting that exact log strings and levels vary by Cassandra release. Do not only `grep "ERROR"`; normal schema changes often log at INFO, and failures caused by routing or app namespaces leave no Cassandra error logs at all.

## 11. Classifying Java Exceptions to Prevent Wrong Fixes

### 11.1. Error Matrix

| Error Type | Common Causes | Retry Immediately? |
|---|---|---|
| `InvalidQueryException` | Missing keyspace/table/column or invalid query | **No** by default; only bounded wait if a migration is known to be converging |
| `SyntaxError` | Invalid CQL syntax | **No**; fix CQL |
| `UnauthorizedException` | Role lacks permission | **No**; fix RBAC/role |
| `AlreadyExistsException` | `CREATE` target already exists | Do not auto-fix; diff expected schema |
| `UnavailableException` | Insufficient live replicas for CL | Handle RF/CL/topology; not schema |
| `ReadTimeoutException`/`WriteTimeoutException` | Replica responses/ACKs missed deadline | Respect idempotency, unknown write outcomes |
| `DriverTimeoutException` | Client deadline expired during prep, send, or wait | Do not assume server didn't apply |
| `AllNodesFailedException` | Per-coordinator failures aggregated | Inspect `getAllErrors()`, never swallow causes |
| `NoNodeAvailableException` | No usable coordinator | Check local DC, connections, contact points |
| Codec/serialization error | Bad Java bind type/mapping | Fix driver/codec; never run blind migrations |

`InvalidQueryException` covers many conditions beyond missing tables. Record the **CQL query family, keyspace/table, and sanitized message**; avoid classifying errors solely by matching the word "table" in a version-specific string.

### 11.2. Different Error Categories Require Different Actions

~~~text
unconfigured table          -> Validate schema/namespace/DDL timeline
Unauthorized                -> Permissions and service role
Unavailable                 -> RF/replica liveness/CL
ReadTimeout                 -> Replica read path/time budgets
WriteTimeout                -> Unknown write outcome; reconcile
DriverTimeout               -> Driver queue/network/timeout, server unknown
NoNodeAvailable             -> Driver routing/connectivity/DC
Protocol/schema mismatch    -> Driver/server version/compatibility
~~~

**Never** catch `Exception` and automatically execute `CREATE TABLE IF NOT EXISTS`; doing so can mask auth/routing bugs, create tables in the wrong environment, or hide real schema drift.

### 11.3. Server Errors and Driver Errors Can Be Nested

Java Driver can wrap failures from multiple coordinators inside `AllNodesFailedException`. Even a `PREPARE` call can attempt multiple nodes; log sanitized per-node root causes:

~~~java
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.metadata.Node;
import java.util.List;
import java.util.Map;

static void logCoordinatorFailures(AllNodesFailedException failure) {
    for (Map.Entry<Node, List<Throwable>> e :
            failure.getAllErrors().entrySet()) {
        String coordinator = String.valueOf(e.getKey().getHostId());
        for (Throwable cause : e.getValue()) {
            System.err.printf(
                "coordinatorHostId=%s errorType=%s%n",
                coordinator, cause.getClass().getSimpleName());
        }
    }
}
~~~

Never log prepared statement **bind values**, usernames/passwords/tokens, or customer records. Use correlation IDs and sanitized query families for cross-service tracing.

## 12. Java Driver 4.x: Proper Use of Schema Agreement and Metadata

### 12.1. `CqlSession` Is Long-Lived, Never Created Per Probe

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

try (CqlSession session = CqlSession.builder()
        .addContactPoint(
            new InetSocketAddress("127.0.0.1", 9042))
        .withLocalDatacenter("datacenter1")
        .build()) {
    // Run only against a single-node Cassandra LAB.
    // Use fully qualified CQL; do not rely on USE from cqlsh.
}
~~~

In production apps, `CqlSession` is **reused for the application's lifetime**. Repeatedly opening/closing sessions thrashes metadata refreshes, connections, auth/TLS, and prepared caches, and adds noise to schema diagnostics.

### 12.2. Set an Explicit Keyspace If Not Using Fully Qualified CQL

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;

CqlSession withKeyspace = CqlSession.builder()
    .addContactPoint(
        new InetSocketAddress("127.0.0.1", 9042))
    .withLocalDatacenter("datacenter1")
    .withKeyspace(CqlIdentifier.fromCql("catalog_lab"))
    .build();
~~~

`withKeyspace` assumes the keyspace already exists at session creation time. When bootstrapping an app *for the first time* before migrations have created the keyspace, open a migration session **without specifying a keyspace** (in a lab or dedicated runner), then start the application session with the keyspace or use fully qualified CQL. Avoid starting the app session before migrations and looping connection retries without surfacing the root cause.

### 12.3. Driver Metadata Is a Snapshot

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.metadata.Metadata;

Metadata snapshotBefore = session.getMetadata();

// DDL may have been run by a separate migration runner.
// snapshotBefore is not a live view to hold and poll forever.

Metadata snapshotAfter = session.getMetadata();
boolean keyspaceKnown = snapshotAfter
    .getKeyspace(CqlIdentifier.fromCql("catalog_lab"))
    .isPresent();

System.out.println("Keyspace visible to driver=" + keyspaceKnown);
~~~

Seeing the keyspace in a snapshot **does not** guarantee table data is ready or all nodes agree. Not seeing the keyspace in a snapshot **also does not prove** Cassandra lacks the keyspace: metadata refresh may be disabled/debounced, or the driver has not processed the schema-change event yet. Cross-check `system_schema` directly on a coordinator and review DDL status.

### 12.4. Checking a Table in Metadata

~~~java
import java.util.Optional;

Optional<KeyspaceMetadata> ks = session.getMetadata()
    .getKeyspace(CqlIdentifier.fromCql("catalog_lab"));

boolean tableKnown = ks
    .flatMap(meta ->
        meta.getTable(CqlIdentifier.fromCql("orders_by_id")))
    .isPresent();

System.out.println("Table visible in driver metadata=" + tableKnown);
~~~

If `tableKnown=false`:

1. Confirm driver schema metadata is enabled in configuration.
2. Confirm keyspace/table are referenced with the **exact case/quoted `CqlIdentifier`**.
3. Check `system_schema.tables` on a coordinator.
4. If the server sees the table yet the driver does not, inspect metadata refresh/events/connectivity.
5. If some servers also do not see it, investigate schema disagreement/DDL propagation.

### 12.5. `session.checkSchemaAgreement()` Is a Point-in-Time Check

~~~java
boolean agreed = session.checkSchemaAgreement();
if (!agreed) {
    System.err.println("Schema agreement not reached among UP nodes");
}
~~~

This check returns the state at invocation time; it does not recreate tables or repair schemas. Around DDL, **poll with a deadline** instead of waiting forever. Per Java Driver 4.x documentation, driver schema agreement checks **UP nodes**; DOWN nodes catch up once recovered.

### 12.6. `ExecutionInfo.isSchemaInAgreement()` Only Applies to DDL

~~~java
import com.datastax.oss.driver.api.core.cql.ResultSet;

ResultSet ddl = session.execute(
    "CREATE TABLE IF NOT EXISTS catalog_lab.audit_by_id (" +
    "id uuid PRIMARY KEY, event_name text)");

boolean ddlAgreement =
    ddl.getExecutionInfo().isSchemaInAgreement();

System.out.println("DDL agreement observed=" + ddlAgreement);
~~~

For schema-changing requests, the driver can wait for agreement per config and populate this flag with the wait outcome. **Never use** this flag from a regular `SELECT` to claim agreement:

~~~java
ResultSet read = session.execute(
    "SELECT cluster_name FROM system.local");

// WRONG to infer "schema ready" from this line:
boolean misleading = read.getExecutionInfo().isSchemaInAgreement();
~~~

The Javadoc notes that for non-DDL statements, `isSchemaInAgreement()` may return `true` by default because agreement waiting does not apply. Use `session.checkSchemaAgreement()` and metadata checks when an independent gate is needed.

### 12.7. Prepared Statements After Schema Changes

A prepared statement is **prepared** against the CQL and schema at preparation time. When a table changes:

- Driver/server may need to re-prepare if a prepared ID is missing on a node.
- DDL altering or dropping a column referenced or bound by CQL can break the statement.
- The driver handles some `UNPREPARED` responses automatically, **but cannot fix invalid business CQL**.
- Holding a cached `PreparedStatement` does not substitute for verifying schema agreement and migration versions.

For contract-impacting changes, prepare statements **after migration agreement and gates pass**, verify result-set columns, and verify rollback compatibility. **Do not wipe all prepared caches or restart nodes** the moment a table fails to resolve; locate the failing coordinator first.

## 13. Waiting for Schema Agreement with a Deadline and Detecting Startup Races

### 13.1. Bounded Polling

~~~java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

static void awaitSchemaAgreement(
        CqlSession session,
        Duration budget,
        Duration interval) throws InterruptedException {

    long deadline = System.nanoTime() + budget.toNanos();
    int attempts = 0;

    while (System.nanoTime() < deadline) {
        attempts++;
        if (session.checkSchemaAgreement()) {
            return;
        }

        long remaining = deadline - System.nanoTime();
        if (remaining <= 0) {
            break;
        }

        TimeUnit.NANOSECONDS.sleep(
            Math.min(interval.toNanos(), remaining));
    }

    throw new IllegalStateException(
        "Schema not agreed after " + attempts +
        " attempts within " + budget);
}
~~~

**Intended for integration tests or dedicated management threads**—never run blocking sleeps inside Netty I/O callbacks. Example `45s`/`500ms` values must be tuned to your startup and deployment profile; there is no "universal default for every cluster".

### 13.2. What If `checkSchemaAgreement()` Throws an Exception?

The helper above intentionally **does not** catch every exception:

- Bad credentials/permissions, missing coordinators, and cluster misrouting should surface clearly.
- During controlled startup, specific transient connection/availability errors can be **retried with classification** inside an overall budget.
- Never swallow `InvalidQueryException` or `UnauthorizedException` and sit looping for 5 minutes.

If transient connectivity retries are needed, write a **tested wrapper** scoped to specific error classes, preserving the last cause and metrics. Never coerce every failure to `false` to "wait for schema" when you haven't even verified you're hitting the right cluster.

### 13.3. Waiting for Agreement Does Not Finish the Workflow

~~~text
DDL submit
     |
DDL succeeds
     |
awaitSchemaAgreement() PASS
     |
Re-read driver metadata / system_schema
     |
Validate expected table columns/PK
     |
Prepare application statements
     |
Read/write CQL probe at declared CL
     |
Verify expected data/value and latency
     |
Enable traffic
~~~

In multi-node production, **each step has a narrow scope**: agreement covers UP nodes, metadata covers the current driver view, and a CQL probe covers only the sampled partition/token. Never treat a `ONE` probe as proof a `LOCAL_QUORUM` workload is ready.

### 13.4. DDL Succeeds Yet `isSchemaInAgreement=false`

This **does not automatically mean the DDL rolled back**. The coordinator may have applied the schema while the agreement wait timed out waiting for peers to sync. Proper steps:

1. Record the DDL/query family, timestamp, and coordinator.
2. Read `system_schema` across nodes A/B/C and compare schema versions.
3. Wait within a bounded window if convergence is actively progressing.
4. If the budget expires, HOLD the rollout and investigate gossip, networking, and DDL conflicts.
5. **Do not fire hundreds of duplicate DDLs** from every pod, even with `IF NOT EXISTS`.

### 13.5. Separating CQL Preparation from CQL Execution

`session.prepare("SELECT ...")` also requires the coordinator to resolve the table schema; if the table does not exist yet, `PREPARE` fails before any `INSERT`/`SELECT` runs. Thus, `unconfigured table` during **startup prepare** often points to **unfinished migrations**, not corrupted read data.

## 14. Safe Migration Strategy for Multi-Node Clusters

### 14.1. Single Migration Runner

~~~text
CI/CD:
  1. Build artifact
  2. Validate backward-compatible CQL migrations
  3. Run dedicated single migration job
  4. Await DDL outcome + schema agreement (UP nodes)
  5. Validate metadata and expected CQL
  6. Deploy new app code gradually
  7. Observe CL/data oracle/error metrics

Application pods:
  DO NOT all run concurrent ALTER TABLE at startup.
~~~

A `migration_history` table is useful for tracking applied versions, but by itself is not a safe distributed lock if multiple runners `INSERT` concurrently without CAS or leader coordination. Prefer **deployment-level serialization** or a single migration coordinator with reliable idempotency/locking semantics.

### 14.2. Expand → Migrate → Contract

Example: migrating an API from `status` to `payment_status` while older binaries remain live during rolling deployment:

~~~text
Phase 1 EXPAND:
  ALTER TABLE ... ADD payment_status text
  Await schema agreement

Phase 2 DUAL-COMPATIBILITY:
  New writer optionally dual-writes/reads fallback
  Backfill safely with checkpoint/version
  Validate queries on old and new fields

Phase 3 CONTRACT:
  Confirm no old clients depend on status
  After retention/rollback windows, remove old dependency
  Only then consider DROP COLUMN per reviewed migration
~~~

**Never run `ALTER TABLE DROP status` the instant the first node learns `payment_status`**; older pods may still be running and executing prepared queries against `status`. Changing a primary key generally requires a **new table** plus backfill and cutover, not an in-place `ALTER`.

### 14.3. `IF NOT EXISTS` Does Not Substitute for a Schema Diff

When DDL includes `IF NOT EXISTS` on an existing table with wrong columns or PK:

~~~text
Desired:
  PRIMARY KEY ((tenant_id), order_id)
  revision int

Actual:
  PRIMARY KEY ((order_id))
  revision text

CREATE TABLE IF NOT EXISTS ... returns without creating
-> schema is still incompatible.
~~~

Always diff actual vs. expected schema and **fail the migration** on incompatible drift instead of reporting green just because DDL threw no exception. Manage DDL in reviewed, versioned migration files—never auto-generate it unconditionally from runtime errors.

### 14.4. Keeping Older Applications Compatible During Rollouts

| Change | Risk to Older Apps | Mitigation |
|---|---|---|
| ADD nullable column | Usually low, depends on `SELECT *` / mapping | Explicit column lists, tolerant DTOs |
| ADD index | Build/visibility lag, new query load | Measure index build/readiness separately |
| DROP column | Old prepared statements/DAOs fail | Drop only after all old readers are gone |
| Rename column | Legacy CQL referencing old name fails | Prefer expand + new column + migrate |
| Change table primary key | Semantics cannot be altered via normal ADD | New table + backfill + dual-read/write |
| Change keyspace RF | Separate data placement/repair requirements | Schema agreement + repair + data probes |
| View/index creation | Requires build phase and version limits | Verify feature-specific readiness |

### 14.5. When DDL Rollback Is Needed

Rolling back an **application deploy** is far easier than rolling back **schema/data mutations**. When DDL causes trouble:

- Stop/hold the rollout and check how far the DDL applied.
- Never `DROP TABLE` to "go back before the migration": it can destroy live data.
- Never `TRUNCATE` to "clear bad data"; it is a destructive operation.
- If rolling back via a compatible schema change, create a new reviewed migration and test in staging first.
- If data was backfilled or written, execute a separate reconciliation/restore plan; schema agreement does not undo data writes.

## 15. Lab A — CQL: Existing Keyspace/Table, Wrong Names, and Expected Errors

### 15.1. Prerequisites and Safety Conditions

- **Single-node lab** Cassandra 4.1/5.0 with `cqlsh` access.
- Account authorized to create a **dedicated lab keyspace**; never touch real keyspaces.
- `SimpleStrategy` RF1 and `CONSISTENCY ONE` are for single-node labs only.
- The lab includes **intentionally failing queries**; record expected errors rather than altering the cluster.
- If `troubleshoot_lab` already exists with data you do not own, **do not overwrite it**; use a newly approved lab namespace.

### 15.2. Initialize Keyspace and Baseline Table

~~~sql
CREATE KEYSPACE IF NOT EXISTS troubleshoot_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS troubleshoot_lab.orders_by_tenant (
  tenant_id text,
  order_id uuid,
  status text,
  revision int,
  PRIMARY KEY ((tenant_id), order_id)
);

CONSISTENCY ONE;

INSERT INTO troubleshoot_lab.orders_by_tenant
  (tenant_id, order_id, status, revision)
VALUES (
  'tenant-lab',
  11111111-1111-1111-1111-111111111111,
  'CREATED',
  1
);
~~~

**Use synthetic data only.** Re-running the lab `INSERT` with the same PK updates the same row; if another test modified the data, verify provenance before overwriting.

### 15.3. Verify Schema and Expected Row

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'troubleshoot_lab';

SELECT table_name
FROM system_schema.tables
WHERE keyspace_name = 'troubleshoot_lab';

SELECT column_name, kind, type
FROM system_schema.columns
WHERE keyspace_name = 'troubleshoot_lab'
  AND table_name = 'orders_by_tenant';

SELECT status, revision
FROM troubleshoot_lab.orders_by_tenant
WHERE tenant_id = 'tenant-lab'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Expect one row with `status='CREATED'`, `revision=1`, and four table columns. This is the **positive control**: table and data work on the lab coordinator at `ONE`. It does not prove multi-node RF3 schema agreement.

### 15.4. Negative Test 1 — Genuinely Non-Existent Keyspace

~~~sql
SELECT status
FROM no_such_keyspace_999.orders_by_tenant
WHERE tenant_id = 'tenant-lab'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Expect a **query validation error** indicating the keyspace does not exist. Exact wording varies by Cassandra version; confirm `system_schema.keyspaces` lacks `no_such_keyspace_999`. This is **not schema disagreement** because the lab deliberately references an uncreated namespace.

### 15.5. Negative Test 2 — Non-Existent Table in a Real Keyspace

~~~sql
SELECT status
FROM troubleshoot_lab.orders_by_tenant_v999
WHERE tenant_id = 'tenant-lab'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Expect an error such as `unconfigured table`. Re-run `SELECT table_name FROM system_schema.tables ...` to distinguish a wrong table name from unconverged schema.

### 15.6. Negative Test 3 — No Keyspace Selected

~~~sql
-- From a cqlsh session without USE:
SELECT status
FROM orders_by_tenant
WHERE tenant_id = 'tenant-lab'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Expect **no keyspace has been specified** rather than missing table. Next:

~~~sql
USE troubleshoot_lab;
SELECT status, revision
FROM orders_by_tenant
WHERE tenant_id = 'tenant-lab'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

These two SELECTs illustrate **namespace resolution**, not cluster schema disagreement. In Java apps, prefer fully qualified CQL to avoid relying on session context.

### 15.7. Negative Test 4 — Non-Existent Column

~~~sql
SELECT payment_status
FROM troubleshoot_lab.orders_by_tenant
WHERE tenant_id = 'tenant-lab'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Expect `Undefined column name payment_status` (or equivalent). **Never** catch this and run `ALTER TABLE ADD payment_status` automatically in production; v2 code may have deployed ahead of migrations, or the DTO/CQL has a typo.

### 15.8. Negative Test 5 — Case-Sensitive Quoted Table

~~~sql
CREATE TABLE IF NOT EXISTS troubleshoot_lab."OrderEvents" (
  "TenantId" text PRIMARY KEY,
  status text
);

-- Valid:
SELECT status
FROM troubleshoot_lab."OrderEvents"
WHERE "TenantId" = 'tenant-lab';

-- Invalid (unquoted folds to orderevents):
SELECT status
FROM troubleshoot_lab.OrderEvents
WHERE "TenantId" = 'tenant-lab';
~~~

The first SELECT returning 0 rows is **valid** because no row was inserted yet, proving the table exists; the second SELECT must fail with object not found. This cleanly demonstrates that "returns 0 rows" and "`unconfigured table`" are **two completely different outcomes**.

### 15.9. Limits of Checking `schema_version` on a Single Node

~~~sql
SELECT schema_version FROM system.local;
~~~

A single-node lab reports agreement without exercising network propagation to peers. Never simulate disagreement by editing `system.local.schema_version` or mutating system tables. Multi-node diagnostics belong on authorized staging clusters following section 19.

## 16. Lab B — Java 17: DDL, Agreement, Metadata, PREPARE, Write/Read

### 16.1. Dependency and Setup

Gradle Kotlin DSL example using Apache Java Driver 4.18.1:

~~~kotlin
dependencies {
    implementation("org.apache.cassandra:java-driver-core:4.18.1")
}
~~~

For DataStax-maintained 4.17.x drivers, Maven coordinates differ (`com.datastax.oss:java-driver-core:4.17.x`). Pick one driver version compatible with your Cassandra release and JDK; never mix versions. This code targets a **single-node lab on localhost:9042**; replace placeholder DC `datacenter1` with the actual value from `system.local`/`nodetool status`.

### 16.2. Standalone Program

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.metadata.schema.KeyspaceMetadata;
import com.datastax.oss.driver.api.core.servererrors.InvalidQueryException;
import java.net.InetSocketAddress;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class SchemaTroubleshootingLab {
    private SchemaTroubleshootingLab() {}

    private static final CqlIdentifier KS =
        CqlIdentifier.fromCql("troubleshoot_java_lab");
    private static final CqlIdentifier TABLE =
        CqlIdentifier.fromCql("orders_by_id");

    public static void main(String[] args) throws Exception {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            // Step 1: DDL in lab namespace; do not run inside
            // every production application pod.
            ResultSet keyspaceDdl = session.execute(
                "CREATE KEYSPACE IF NOT EXISTS troubleshoot_java_lab " +
                "WITH replication = {'class':'SimpleStrategy', " +
                "'replication_factor':1}");
            System.out.println("keyspace DDL agreement=" +
                keyspaceDdl.getExecutionInfo().isSchemaInAgreement());

            ResultSet tableDdl = session.execute(
                "CREATE TABLE IF NOT EXISTS " +
                "troubleshoot_java_lab.orders_by_id (" +
                "tenant_id text, order_id uuid, " +
                "status text, revision int, " +
                "PRIMARY KEY ((tenant_id), order_id))");
            System.out.println("table DDL agreement=" +
                tableDdl.getExecutionInfo().isSchemaInAgreement());

            // Step 2: Await agreement and metadata with deadline;
            // avoid hardcoded Thread.sleep(10000).
            awaitExpectedSchema(session, Duration.ofSeconds(45));

            // Step 3: Verify PREPARE + read/write path
            PreparedStatement insert = session.prepare(
                "INSERT INTO troubleshoot_java_lab.orders_by_id " +
                "(tenant_id, order_id, status, revision) " +
                "VALUES (?, ?, ?, ?)");

            PreparedStatement select = session.prepare(
                "SELECT status, revision " +
                "FROM troubleshoot_java_lab.orders_by_id " +
                "WHERE tenant_id = ? AND order_id = ?");

            UUID orderId = UUID.fromString(
                "22222222-2222-2222-2222-222222222222");

            BoundStatement write = insert.bind(
                    "tenant-java", orderId, "READY", 5)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setTimeout(Duration.ofSeconds(3));
            session.execute(write);

            BoundStatement read = select.bind("tenant-java", orderId)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setIdempotent(true)
                .setTimeout(Duration.ofSeconds(3));
            Row row = session.execute(read).one();
            if (row == null
                    || !"READY".equals(row.getString("status"))
                    || row.getInt("revision") != 5) {
                throw new AssertionError("Data oracle failed");
            }

            System.out.println("DDL + schema + CQL/data PASS");

            // Step 4: negative control — intentionally invalid table name.
            try {
                session.execute(
                    "SELECT status FROM troubleshoot_java_lab." +
                    "missing_table_999 WHERE tenant_id='tenant-java'");
                throw new AssertionError(
                    "Expected validation error for missing table");
            } catch (InvalidQueryException expected) {
                System.out.println(
                    "Negative control PASS: " +
                    expected.getClass().getSimpleName());
            }
        }
    }

    private static void awaitExpectedSchema(
            CqlSession session, Duration budget)
            throws InterruptedException {

        long deadline = System.nanoTime() + budget.toNanos();
        while (System.nanoTime() < deadline) {
            boolean agreement = session.checkSchemaAgreement();

            boolean metadataHasTable = session.getMetadata()
                .getKeyspace(KS)
                .flatMap(ks -> ks.getTable(TABLE))
                .isPresent();

            if (agreement && metadataHasTable) {
                return;
            }
            TimeUnit.MILLISECONDS.sleep(250);
        }
        throw new AssertionError(
            "Schema agreement/driver metadata did not converge");
    }
}
~~~

### 16.3. Why Check Table Metadata Alongside Agreement?

The full snippet in section 16.2 uses:

~~~java
boolean metadataHasTable = session.getMetadata()
    .getKeyspace(KS)
    .flatMap(ks -> ks.getTable(TABLE))
    .isPresent();
~~~

The goal is verifying **the exact table** in a fresh metadata snapshot, not merely that the keyspace exists. UP-node agreement can PASS before driver metadata refreshes; the app should only prepare/query the table once all defined conditions hold. This lab code is an educational and testable example; in-depth STEP 6/QA will compile and verify with the proper toolchain, while this STEP 4 **does not run Gradle**.

### 16.4. Expected Output

~~~text
keyspace DDL agreement=true/false
table DDL agreement=true/false
DDL + schema + CQL/data PASS
Negative control PASS: InvalidQueryException
~~~

The two DDL agreement flags may read false briefly during convergence; the helper keeps polling within the budget. In a single-node lab it usually finishes quickly. The negative test confirms the misnamed table **genuinely does not exist** on the lab node without simulating schema disagreement.

### 16.5. Choosing CL Appropriate to Topology

In an RF1 lab:

~~~java
request.setConsistencyLevel(DefaultConsistencyLevel.ONE);
~~~

In single-DC RF3 production, use `LOCAL_QUORUM` once **three eligible full replicas** exist and the data contract requires it. Never treat RF1/`ONE` results as proof for RF3/`LOCAL_QUORUM` production, and never lower CL just to pass a schema migration gate.

## 17. Lab C — JUnit 5 Against False Greens

The Java program in section 16 runs as a standalone app. For CI, add **concrete test oracles** rather than just logging `Schema agreed`. The JUnit 5 example below assumes the **single-node lab created and seeded** in section 16; it does not spin up a multi-node cluster or validate multi-node schema agreement.

### 17.1. Complete Test Class for Lab Environments

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.servererrors.InvalidQueryException;
import java.net.InetSocketAddress;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

final class SchemaReadinessIT {
    private static CqlSession session;

    @BeforeAll
    static void connect() {
        session = CqlSession.builder()
            .addContactPoint(
                new InetSocketAddress("127.0.0.1", 9042))
            .withLocalDatacenter("datacenter1")
            .build();
    }

    @AfterAll
    static void close() {
        if (session != null) {
            session.close();
        }
    }

    @Test
    void tableExistsAndCqlContractWorks() {
        assertTrue(session.checkSchemaAgreement(),
            "Schema not agreed among currently UP nodes");

        assertTrue(session.getMetadata()
            .getKeyspace(
                CqlIdentifier.fromCql("troubleshoot_java_lab"))
            .flatMap(ks -> ks.getTable(
                CqlIdentifier.fromCql("orders_by_id")))
            .isPresent(), "Missing table in driver metadata");

        Row row = session.execute(
            session.prepare(
                "SELECT status, revision FROM " +
                "troubleshoot_java_lab.orders_by_id " +
                "WHERE tenant_id = ? AND order_id = ?")
                .bind("tenant-java",
                    UUID.fromString(
                        "22222222-2222-2222-2222-222222222222"))
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setIdempotent(true)).one();

        assertNotNull(row, "Expected lab row missing");
        assertEquals("READY", row.getString("status"));
        assertEquals(5, row.getInt("revision"));
    }

    @Test
    void missingTableShouldProduceValidationError() {
        assertThrows(InvalidQueryException.class,
            () -> session.execute(
                "SELECT status FROM " +
                "troubleshoot_java_lab.table_not_created_999"));
    }
}
~~~

**Prerequisites:** Run the data-setup step from section 16 first. With Testcontainers, start Cassandra and seed data before `@BeforeAll` or manage the session inside the test class. In parallel CI workers, isolate keyspaces/row IDs so tests do not read stale state. **Never** write a test where `assertTrue(checkSchemaAgreement())` passes and assume all CQL, data, and CL contracts are ready.

### 17.2. Negative Controls Must Assert the Specific Exception Type

`assertThrows(InvalidQueryException.class)` proves CQL reached the coordinator and the table name was rejected. `assertThrows(RuntimeException.class)` is too broad: connection loss, bad credentials, or syntax errors could make the test pass for the wrong reason.

### 17.3. Cases Where Tests Must Fail Explicitly

~~~text
Wrong local DC/credentials                 -> FIX CONFIG
DDL agreement timeout                     -> HOLD MIGRATION
Expected table missing in driver metadata -> INVESTIGATE REFRESH/SCHEMA
CL ONE works but production wants LQ      -> COVERAGE GAP
Expected row/revision differs             -> DATA/SCHEMA CONTRACT FAIL
~~~

In shared or production-like environments, concurrent writes occur, so sentinel tests must own dedicated partitions/IDs and test at the real consistency contract.

## 18. Multiple Coordinators: Finding Which Node Sees Stale Schema

### 18.1. A Safe Diagnostic Workflow

For a 3-node cluster A/B/C:

~~~text
Target: keyspace catalog_lab, table orders_by_id
Expected: tenant_id text, order_id uuid, status text, revision int

1. Direct cqlsh to A -> system.local.schema_version
2. Read system_schema.tables/columns on A
3. Repeat for B/C using read-only diagnostic credentials
4. Run nodetool describecluster from an authorized vantage point
5. Correlate Java error timestamps/coordinators with host_id
6. Inspect migration DDL logs and internode communication
7. Bounded wait; if disagreement persists -> HOLD/ESCALATE
~~~

Never force the driver to hit a suspect node by breaking topology or altering production routing. **Direct `cqlsh` connections** to each node are safe read checks when kept at low rate with proper TLS/credentials.

### 18.2. Three-Node Comparison Table

| Node | State | `schema_version` | Table Visible? | `revision` Column? | Preliminary Conclusion |
|---|---|---|---|---|---|
| A | UN | V2 | Yes | Yes | Current schema |
| B | UN | V2 | Yes | Yes | Current schema |
| C | UN | V1 | Yes | No | Stale schema |

All nodes being `UN` does not rule out schema disagreement. Conversely, if all three show V2 yet a Java instance still fails, check **wrong keyspace/identifier/role, stale driver metadata, or older binary CQL** instead of insisting C is still on V1.

### 18.3. Attributing Errors to a Coordinator

Java Driver 4.x exposes `ExecutionInfo.getCoordinator()` on successful responses; on failures, multiple causes may sit inside `AllNodesFailedException.getAllErrors()`. A report should record:

~~~text
request_id=trace-abc
query_family=orders.getById
keyspace=catalog_lab
table=orders_by_id
local_dc=dc1
coordinator_host_id=... (when evidenced)
exception_type=InvalidQueryException
phase=PREPARE
app_release=...
schema_version_local_A=...
schema_version_local_B=...
schema_version_local_C=...
~~~

**Note:** On a standalone `InvalidQueryException`, the coordinator ID might not appear directly on the exception the way it does on `ExecutionInfo`; check driver tracing or server logs. Never guess a `host_id` without evidence.

### 18.4. One Stale Coordinator Does Not Mean Lost Data

If node C still holds schema V1, tables added in V2 cannot be resolved when queries hit C. Data previously written on other replicas is **not deleted** by this event. Restoring schema requires investigating propagation, **never** running `DROP/CREATE` (which risks losing SSTables or creating a table with the wrong primary key).

### 18.5. Wait or Escalate?

| Situation | Choice |
|---|---|
| DDL just ran, peers actively updating, budget remains | **HOLD + bounded wait** |
| One node DOWN, UP-node agreement PASSES | **HOLD node promotion** until post-recovery schema check |
| Schema versions diverge persistently | **ESCALATE**, collect logs/versions |
| Versions match, yet expected DDL definition is wrong | **STOP migration**, fix definition |
| One pod uses wrong keyspace | **FIX CONFIG**, do not touch schema |
| Role lacks privileges | **FIX RBAC**, do not retry DDL |
| Cluster lacks CL due to replica failures | **Availability incident**, not schema disagreement |

No fixed second count fits every topology. Tune wait budgets to cluster size, networking, and deployment SLOs; measure convergence progress instead of guessing.

## 19. Multi-DC, Node Restarts, and Mixed-Version Clusters

### 19.1. Local DC Is a Java Driver Requirement

~~~text
Cluster:
  dc1: A, B, C
  dc2: D, E, F

Java service in dc1:
  local-datacenter=dc1
  session connects/routes via local nodes per policy

Java service in dc2:
  local-datacenter=dc2
  session connects/routes via local nodes per policy
~~~

Verifying schema only in `dc1` does not certify `dc2` is ready, especially during inter-DC network/gossip trouble. Verify from each DC's application vantage point. When DC RFs differ, `LOCAL_QUORUM` requires different numbers of full replicas per DC; **schema readiness** and **data availability at CL** are separate gates.

### 19.2. NTS Is Replication Metadata, Not Automatic Node Provisioning

~~~sql
-- Example ONLY on a REAL lab cluster with both DCs:
CREATE KEYSPACE IF NOT EXISTS catalog_multidc_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 3
};
~~~

**Do not run this on a single-node lab** expecting Cassandra to spawn six replicas. DDL may be accepted even without enough physical replicas, yet `LOCAL_QUORUM`/`EACH_QUORUM` reads/writes will fail for lack of natural replicas. Never lower CL just to pass a migration test.

### 19.3. Node DOWN During Migration

~~~text
Before DDL: A/B/C schema V1; C DOWN
Migration:  A/B apply V2; UP-node agreement PASS
App deploy: Uses V2
C rejoins later, may need schema catch-up
~~~

When C rejoins, verify:

- It received and applied schema V2 with valid table/column metadata.
- CQL transport and driver node state recovered cleanly.
- Required writes/snapshots/streaming converged per CL/repair policy.
- Do not start rolling-restarting the next node until resilience margin is restored.

Agreement between A and B while C was DOWN **does not certify** C is ready for V2 traffic the second it flips to `UN`.

### 19.4. Rolling Upgrades and Feature Support

In a mixed-version cluster:

- Never issue DDL using syntax, indexes, types, or compaction options unsupported by older nodes still in the cluster.
- Check official upgrade paths/release notes for **your exact Cassandra version pair**.
- Run incompatible schema migrations only after the supported upgrade phase completes.
- Record app + driver + server versions in incident reports; exception/log wording may vary.

### 19.5. Repair Does Not Fix Schema Disagreement

`nodetool repair` synchronizes **data replicas/SSTables**; **it is not a schema-disagreement repair command**. While `system_schema`/`schema_version` remain diverged, repair will not align them and can add heavy load to a stressed cluster. Likewise, `nodetool cleanup`, `compact`, and `flush` act on storage lifecycles, not DDL migrations or peer schema propagation.

## 20. Permissions and False "Table Not Found" Errors

### 20.1. Why Roles Matter

In Cassandra:

- `CREATE KEYSPACE` and `CREATE TABLE` require schema-level permissions.
- `ALTER` and `DROP` require administrative permissions on the target object.
- `SELECT` and `MODIFY` require role permissions on the keyspace/table.
- Accessing `system_schema`/metadata/`DESCRIBE` may be governed by RBAC or authorizer settings.

If a superuser check PASSES while the Java service throws `UnauthorizedException`, **do not** create a new keyspace/table; compare accounts, roles, grants, and auth configuration.

### 20.2. Authorized Permission Verification Commands

~~~sql
LIST ROLES;
LIST ALL PERMISSIONS OF app_service_role;
~~~

Exact syntax and output depend on Cassandra version and authorizer. Never paste full grants containing sensitive internal names into public tickets. Test with the **actual service role** or an equivalent test role rather than a superuser.

### 20.3. Two Credential Sets, One Query

~~~text
Admin cqlsh:
  SELECT catalog_lab.orders_by_id -> PASS

Java service role:
  SELECT catalog_lab.orders_by_id -> Unauthorized

Conclusion:
  RBAC/config incident; schema itself may already be fully agreed.
~~~

**Never fix this by granting superuser to the Java app** just to clear a readiness gate. Enforce least privilege by query family, clear role ownership, and a dedicated migration role.

### 20.4. Error Messages Masked by ORMs/Frameworks

Spring Data Cassandra, custom repositories, or exception translators can wrap `InvalidQueryException` inside generic errors:

~~~text
HTTP 500: "repository initialization failed"
      |
Bean/DAO startup
      |
CqlSession.prepare(query)
      |
InvalidQueryException: unconfigured table catalog_lab.orders_by_id
~~~

Trace the **root-cause chain and CQL query family** before blaming dependency injection or object mapping. Never print raw CQL with bind values/PII into public logs.

## 21. Observability: Which Signals Reveal Real Disagreement?

### 21.1. Evidence Sources to Correlate

| Layer | Signal | Proper Interpretation |
|---|---|---|
| CI/CD/migration runner | DDL statement ID, sequence, start/end, agreement check | How far DDL progressed |
| Cassandra `system.local` | Per-node local `schema_version` | Schema version seen by that node |
| `nodetool describecluster` | Schema version → peers mapping | Unconverged peer groups from that vantage point |
| Cassandra logs | Schema change/propagation/apply failures | Why propagation stalled or failed |
| Driver schema metadata | Keyspace/table/column snapshot | Which definition the client sees |
| Driver exceptions | `InvalidQuery`/`Unauthorized`/`AllNodesFailed` | Whether queries fail on schema or another layer |
| App query family | Error rate per route/DAO/release | Blast radius |
| Ring/topology | `UN`/`UJ`/`DN`, DC/rack, gossip | Which nodes should hold schema |
| Business CL/data probes | Real CQL and value/version at required CL | Post-agreement readiness |

A spike in `InvalidQuery` **may** accompany schema disagreement, or simply reflect a Java release requesting a wrong column; confirm with **schema version evidence** before labeling it.

### 21.2. Simple Alert Conditions

~~~text
Alert A:
  schema_versions_distinct_among_UP_nodes > 1
  continuously across configured windows
  AND migration_in_progress is known/unknown
  -> HOLD rollout, investigate propagation

Alert B:
  application_invalid_query_errors increase
  after app_release or migration
  -> inspect namespace/table/column and coordinator

Alert C:
  schema agreement PASS
  BUT business data oracle at required CL FAIL
  -> investigate data/replica/readiness separately
~~~

These metric names are **conceptual instrumentation targets**, not guaranteed out-of-the-box Prometheus series. If an exporter lacks `schema_versions_distinct`, use **rate-limited** periodic read-only probes or operator conditions.

### 21.3. Avoid Creating a Schema Storm While Investigating

A readiness endpoint calling `checkSchemaAgreement()` and querying `system_schema` thousands of times per second across hundreds of pods adds unnecessary metadata/network pressure. Instead:

- Have one migration/controller owner perform centralized agreement checks.
- Poll with budgets, backoff, and jitter.
- Keep `CqlSession` long-lived rather than opening sessions per request.
- Scrape/log just enough to catch schema drift/incidents.
- Never trigger DDL from a liveness probe.

### 21.4. Correlating Without Leaking Data

~~~text
incident_id=inc-2026-...
app_release=orders-v2
query_family=orders.getById
phase=PREPARE
keyspace=catalog_lab
table=orders_by_id
local_dc=dc1
coordinator=host-id-or-unknown
error_type=InvalidQueryException
migration_version=V24
schema_agreement=false
last_observation_utc=...
~~~

Never put raw tenant IDs/order IDs, passwords, TLS keys, or full user-bound CQL into metric labels. Even schema/table names may be sensitive in some environments; restrict dashboard access appropriately.

### 21.5. When Metrics Say READY Yet Queries Still Fail

A schema-agreement boolean can return true even while:

- The app points to another keyspace or uses wrong casing.
- The table drifted and every node agrees on **the wrong schema**.
- Java Driver hasn't refreshed its snapshot yet.
- The role lacks permissions.
- Historical data wasn't restored/repaired or CL cannot be satisfied.

Therefore, the final gate must validate **CQL execution + an expected data oracle** with explicit scope, not merely an agreement boolean.

## 22. Twenty-Two Common Troubleshooting Scenarios

### Case 1 — Just Deployed Java v2, `PREPARE` Throws `unconfigured table`

**Symptom:** New app pods boot before the migration job finishes; startup `session.prepare()` fails.

**Diagnosis:** Check deployment order, keyspace/table in `system_schema`, schema versions, and migration history. If no node has the table yet, it is a race / unrun migration.

**Resolution:** HOLD v2 traffic, run migration via single owner, await agreement, verify metadata, then start/enable apps. **Never** have every pod retry DDL indefinitely.

### Case 2 — Table Exists in `cqlsh`, Yet Java Cannot See It

**Symptom:** Admin `DESCRIBE TABLE catalog_lab.orders_by_id` PASSES, Java throws `InvalidQueryException`.

**Diagnosis:** Compare contact points/DC/cluster, credentials, fully qualified CQL, and casing. Then inspect driver metadata snapshot/refresh and the failing coordinator.

**Resolution:** Fix configuration or handle version-appropriate metadata refresh; **never** `DROP/CREATE` the table because one pod lacks context.

### Case 3 — One Pod Uses the Wrong Default Keyspace

**Symptom:** `SELECT ... FROM orders_by_id` on pod A PASSES while pod B reports unconfigured.

**Diagnosis:** Pod A sets `withKeyspace(catalog_lab)` while pod B omits it or points elsewhere. Driver execution profiles may also differ.

**Resolution:** Use fully qualified `catalog_lab.orders_by_id` or align builder configs; add a startup assertion for expected keyspace.

### Case 4 — Quoted `"OrderEvents"` vs. `OrderEvents`

**Symptom:** Table was created quoted with uppercase letters; the app queries unquoted.

**Diagnosis:** Inspect `system_schema.tables` for actual stored casing; recall CQL identifier folding rules.

**Resolution:** Fix CQL/`CqlIdentifier` to match the exact quoted spelling; prefer `lower_snake_case` in new schemas. Never create a second `orderevents` table as a stealth workaround.

### Case 5 — `IF NOT EXISTS` Succeeds, Yet Column Is Missing

**Symptom:** Migration job reports success; v2 app throws `Undefined column revision`.

**Diagnosis:** The table pre-existed with a different schema; `IF NOT EXISTS` does not compare definitions.

**Resolution:** Diff expected vs. actual columns/PK/types; issue an intentional compatible migration instead of looping `CREATE TABLE`.

### Case 6 — Schema Versions A/B=V2, C=V1, All Three `UN`

**Symptom:** A fraction of requests hitting C fail with unconfigured table while A/B PASS.

**Diagnosis:** Check local schema versions, `nodetool describecluster`, internode/gossip logs, and migration timestamps.

**Resolution:** HOLD rollout, allow bounded propagation if DDL just ran; if persistent, investigate connectivity/schema application and follow DBA runbooks. **Never** run `UPDATE system.local`.

### Case 7 — C Is DOWN During Migration, UP Nodes Report Agreement PASS

**Symptom:** A/B converge to V2 while C is DOWN; release gate relies solely on `checkSchemaAgreement` and opens full traffic.

**Risk:** C has not been verified on the new schema upon recovery.

**Resolution:** Separate the UP-node agreement gate from the **node-rejoin gate**; verify C's local schema/CL/data after rejoin before any further rolling restarts.

### Case 8 — `ExecutionInfo.isSchemaInAgreement()` on `SELECT` Always Looks Green

**Symptom:** Team checks this flag on `SELECT system.local` and declares "schema agreement success".

**Cause:** The flag reflects waiting after schema-changing DDL, not agreement for arbitrary SELECTs.

**Resolution:** Use `session.checkSchemaAgreement()` + metadata/`nodetool describecluster` properly, plus separate user-table CQL and data oracle tests.

### Case 9 — Driver Metadata Captured Before Migration Never Updates

**Symptom:** Java caches `Metadata m = session.getMetadata()` before DDL and keeps polling `m.getKeyspace()`, seeing it forever absent.

**Diagnosis:** Immutable metadata snapshot vs. live server schema.

**Resolution:** Call `session.getMetadata()` afresh after agreement, and verify schema metadata refresh settings. Do not force constant driver reconnects to "refresh" when proper APIs exist.

### Case 10 — Old Java `PREPARE` Fails After `DROP COLUMN`

**Symptom:** Rolling deploy still has v1 pods reading `status` while v2 migration already dropped `status`.

**Cause:** Backward-incompatible DDL executed while old and new binaries coexisted.

**Resolution:** STOP/drain traffic per plan, preserve data, follow expand–migrate–contract; restore schema via reviewed migrations rather than dropping tables.

### Case 11 — Multi-DC: `dc1` PASSES, `dc2` Partially Fails

**Symptom:** `dc1` schema versions match, while `dc2` has a stale node or an app routes to the wrong local DC.

**Diagnosis:** Per-DC `system.local.schema_version`, inter-DC connectivity, driver local DC, and coordinator identity.

**Resolution:** HOLD `dc2` rollout and verify `dc2` agreement/CL/data independently. Never extrapolate `dc1` results to the whole cluster.

### Case 12 — `Unauthorized` Misreported as "Table Missing"

**Symptom:** Repository wrapper logs "schema not initialized" when the underlying cause is `UnauthorizedException`.

**Diagnosis:** Inspect stack/cause chain, service role vs. admin role, and grants.

**Resolution:** Fix least-privilege RBAC; never create duplicate tables or grant superuser to the app.

### Case 13 — `CREATE KEYSPACE` DDL Times Out, Runner Retries Repeatedly

**Symptom:** Coordinator already applied the keyspace; subsequent retries fail with `AlreadyExistsException` and increment error counters.

**Diagnosis:** DDL outcomes can be ambiguous on client timeouts; inspect `system_schema.keyspaces` across peers and migration state.

**Resolution:** Stop retry storms and reconcile schema versions/definitions before idempotent replay; `IF NOT EXISTS` still requires a schema diff.

### Case 14 — Schema Versions Match, Yet `SELECT` Returns Empty After Restore

**Symptom:** DDL/metadata match and agreement PASSES, yet historical order IDs are missing.

**Possible Causes:** Incomplete snapshot/restore, wrong partition/TTL, RF/CL mismatch, unloaded SSTables, or wrong source manifest.

**Resolution:** Switch to a **data recovery incident**, verify seeded records/backup manifests, and follow repair/restore runbooks. Do not touch schema when the table already exists.

### Case 15 — Raised RF Shows "Schema Agreement", Yet New Replicas Lack Data

**Symptom:** `ALTER KEYSPACE` succeeded to raise RF, yet strong-CL reads time out or miss older data.

**Diagnosis:** Altering replication metadata does not automatically stream historical data.

**Resolution:** Run version-appropriate full repair/streaming, check natural replica counts/tokens/DCs, and verify data oracles; **never** lower CL as a "schema fix".

### Case 16 — New Index Appears in Schema, Yet Queries Fail or Stall

**Symptom:** `CREATE INDEX`/SAI reaches schema agreement, yet the index build is incomplete or queries violate index restrictions.

**Diagnosis:** Separate **index definition visibility** from **index build/readiness**, version support, and query patterns.

**Resolution:** Check feature-specific metrics/logs, run query tests, and wait for build completion per runbook; do not blame missing base tables.

### Case 17 — Mixed Cassandra Versions Reject New DDL on Older Nodes

**Symptom:** DDL succeeds on upgraded nodes, while older peers fail to apply it or schema versions diverge.

**Diagnosis:** Server release versions, upgrade compatibility, unsupported types/options.

**Resolution:** HOLD DDL, complete the supported upgrade path before applying incompatible migrations, escalate to DBAs, and never force schema versions.

### Case 18 — K8s Liveness Probe Runs Migrations on Every Call

**Symptom:** Dozens of pods fire `CREATE TABLE IF NOT EXISTS` every few seconds, driving schema chatter and errors.

**Cause:** DDL placed inside a health endpoint or bean constructor.

**Resolution:** Remove DDL from liveness probes; use a single-owner migration job and rate-limited readiness checks. Liveness checks process health; readiness checks scoped dependencies/CL/data.

### Case 19 — Operator Runs `nodetool repair` Expecting It to Fix Schema Disagreement

**Symptom:** Cluster schema versions diverge; operator starts full repair causing heavy I/O while schema mismatch persists.

**Cause:** Repair reconciles data replicas, not diverged DDL schema versions.

**Resolution:** Avoid expensive maintenance before diagnosing. Collect versions/logs/DDL timelines and resolve schema propagation via version-specific runbooks.

### Case 20 — One Node Still `UJ`, Migration Gate Lets Traffic Through

**Symptom:** Joining node shows matching schema version yet hasn't finished streaming/bootstrapping; queries at required CL time out.

**Diagnosis:** `nodetool status`, `netstats`, RF/natural replica sets, and CQL/data probes.

**Resolution:** Separate node-up from service-ready; avoid shifting traffic onto nodes mid-bootstrap/streaming. Agreement does not mean data readiness.

### Case 21 — Table Exists, Yet Java Query Builder Misspells a Column

**Symptom:** ORM-generated CQL references `order_status` while the schema defines `status`.

**Diagnosis:** Record query family and sanitized CQL identifier; compare `system_schema.columns` and DTO mappings.

**Resolution:** Fix the DAO/mapping and add contract integration tests; never add extra dummy columns just to make broken queries run.

### Case 22 — CQL `USE` Works in `cqlsh`, Yet Java Still Hits Wrong Namespace

**Symptom:** An operator runs `USE catalog_lab` and `SELECT` PASSES, while Java continues failing unconfigured.

**Explanation:** `USE` only sets context **for that `cqlsh` session**.

**Resolution:** Configure `withKeyspace` or fully qualified CQL in Java, and verify target cluster/role. Never expect an operator's `USE` to change cluster-wide namespaces.

## 23. GO / HOLD / STOP Runbook for Schema Errors

### 23.1. Operational Goal

Restore query service **without corrupting data or schema**, identify the failing layer, and bring the release to a proven state. Completion is not merely "no more `unconfigured table` errors"; verify:

1. **Right cluster, DC, role, and keyspace/table**.
2. **Exact schema definition**, not merely matching names.
3. **Schema agreement** across UP nodes, with topology risks documented.
4. **Java Driver metadata** and prepared CQL match the release.
5. **CL + data oracle** pass, with p99/errors inside SLO.

### 23.2. Phase A — Isolate and Halt Further Spread

~~~text
Incident start
    |
    v
Freeze competing DDL/migration runners
    |
Confirm cluster/DC/keyspace/table/role
    |
Identify affected app versions/query families
    |
Check if data writes are failing or unknown
    |
Decide initial blast radius and action
    |
HOLD risky rollout / preserve availability
~~~

**Note:** "Freeze competing DDL" does not mean killing Cassandra nodes, aborting active streaming, or hastily rolling back schemas. If a migration is in progress, stop **new DDLs** and coordinate with the owner to see how far the statement committed.

Build a UTC timeline: deployment, migration DDL start/end, first `InvalidQuery`, `schema_version` snapshots, failures by coordinator, and affected tenants/query families. Never let a global HTTP 500 rate stand in for root cause.

### 23.3. Phase B — Read-Only Evidence Collection

~~~bash
# Commands within authorized scope, performing no data mutations:
nodetool status
nodetool describecluster
nodetool gossipinfo
nodetool tpstats
nodetool netstats
~~~

~~~sql
-- Connect cqlsh directly to each suspect coordinator:
SELECT cluster_name, data_center, host_id, schema_version
FROM system.local;

SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name='catalog_lab';

SELECT table_name FROM system_schema.tables
WHERE keyspace_name='catalog_lab';

SELECT column_name, kind, type
FROM system_schema.columns
WHERE keyspace_name='catalog_lab'
  AND table_name='orders_by_id';
~~~

When running `cqlsh` from an admin host, explicitly record **the coordinator's IP/host ID** so you do not accidentally query the same node three times thinking you checked three nodes. In multi-DC, record each node's DC/rack and Cassandra version.

### 23.4. Phase C — Root-Cause Classification

| Finding | Classification | Action |
|---|---|---|
| Object absent on all UP nodes, migration never ran | MISSING MIGRATION | **HOLD** app release; run owned versioned migration |
| Object absent on some nodes, versions differ | SCHEMA DISAGREEMENT | **HOLD** new DDL/traffic; bounded wait / gossip diagnosis |
| Object present everywhere, wrong columns/PK | SCHEMA DRIFT | **STOP** incompatible rollout; reviewed migration |
| Object present, app uses wrong case/keyspace | APP CONFIG/CQL | Fix client query/config; leave schema untouched |
| Object present, driver metadata stale | CLIENT METADATA | Check refresh/events/version; revalidate query |
| Admin PASSES, service role unauthorized | RBAC | Fix least-privilege role/grants |
| Table exists, read at CL unavailable | REPLICA AVAILABILITY | Investigate RF/CL/natural replicas; do not run DDL |
| Table exists, expected row missing post-restore | DATA RECOVERY | Manifest/SSTables/repair; never touch schema blindly |
| DDL timed out, schema state unclear | UNKNOWN DDL OUTCOME | Reconcile state before retrying |

### 23.5. Phase D — Safe Remediation Actions

**If migration is missing:** Verify deployment target, review compatible DDL, run from **a single runner**, await agreement with deadline, diff schema, and verify prepare/read/write. Keep a rollback/forward-fix plan.

**If transient disagreement:** Monitor versions/logs/network, HOLD new deployments, and wait within budget. If drift persists past deadline, DBA/SRE investigate schema apply/gossip/protocol per version-specific runbook. **Never** edit schema version UUIDs or system metadata tables.

**If wrong identifier/role:** Fix Java config, CQL mapping, or RBAC; do not touch Cassandra user data.

**If data unready:** Switch to restore/repair/replica availability runbooks; schema agreement **never resolves** data mismatches.

### 23.6. Phase E — Verification Gates

~~~text
G0: Correct target cluster, local DC and credentials
           |
G1: Expected keyspace/table/columns/PK verified
           |
G2: Schema agreement among currently UP nodes
           |
G3: Previously DOWN nodes handled by rejoin gate
           |
G4: Java Driver current metadata + PREPARE succeeds
           |
G5: CQL write/read at required CL and data oracle
           |
G6: Error rate, p95/p99 and retries stable
           |
         GO canary
           |
       Expand traffic with monitoring
~~~

If G2 PASSES yet G5 FAILS, **do not mark resolved**. The fault may lie in data, replicas, or CL rather than schema. A `SELECT system.local` or a `ONE` read does not prove a `LOCAL_QUORUM` service recovered.

### 23.7. GO/HOLD/STOP Decision Table

| Observation | Decision | Explanation |
|---|---|---|
| DDL just ran, versions converging, no major errors | **HOLD** | Wait for bounded agreement |
| Persistent stale node, app requests hitting it fail | **HOLD + ESCALATE** | Requires DBA/network investigation |
| Concurrent DDLs firing from multiple pods | **STOP new DDL** | Prevent schema storm |
| Wrong app namespace/casing fixed, metadata/CQL PASS | **GO canary** | No Cassandra data edits needed |
| Broken RBAC, role still lacks permissions | **STOP** | Do not admit traffic |
| Schema agreed, yet table definition is wrong | **STOP** | Unanimous wrong schema is still broken |
| Reads/writes at required CL + oracle PASS, p99 stable | **GO canary** | Meets probe criteria |
| DOWN node needs schema catch-up before next rolling restart | **HOLD topology change** | Protect resilience margin |
| `DROP/TRUNCATE` proposed because table "not found" | **STOP** | Destructive and unfounded |
| DDL client timeout, server state unclear | **HOLD** | Reconcile before retrying |
| Data corruption / recovery mismatch | **STOP + DATA INCIDENT** | Halt rollout, preserve evidence |

### 23.8. Bounded Rollback After Migration

A migration adding a new column/table can often remain in place while rolling back Java binaries if it is backward-compatible. **Rolling back binaries first** is often safer than dropping newly created schema, after verifying:

- Can older app binaries run cleanly against the current schema?
- Were any writes already issued using the new column/table?
- Are dual-writes, backfills, or timestamp conflicts active?
- Do older clients still query a dropped column?
- Are snapshot/restore and data reconciliation plans ready?

When evidence is missing, **HOLD** and coordinate with owners rather than destroying schema.

### 23.9. Incident Report Template

~~~text
INCIDENT_ID:
UTC_FIRST_ERROR:
CLUSTER / ENVIRONMENT / LOCAL_DC:
CASSANDRA VERSION PER NODE:
JAVA DRIVER / APP RELEASE:
KEYSPACE / TABLE / EXPECTED SCHEMA VERSION:
QUERY FAMILY / ERROR AT PREPARE OR EXECUTE:
SERVICE ROLE / EFFECTIVE KEYSPACE:
COORDINATOR HOST IDS / SAMPLE COUNTS:
SCHEMA_VERSION BY NODE:
NODE STATUS / GOSSIP / NETWORK:
LATEST MIGRATION AND DDL OUTCOME:
SYSTEM_SCHEMA_DIFF:
CL / RF / DATA ORACLE RESULT:
ACTION: GO / HOLD / STOP / ESCALATE:
ROLLBACK/FORWARD-FIX OWNER:
UNKNOWN OUTCOMES (DDL/WRITE):
NEXT REVALIDATION UTC:
~~~

**Never** put raw credentials, restricted private IPs, or PII-bearing bind values into public incident tickets. Host IDs, timestamps, and sanitized query families usually suffice for internal correlation.

## 24. Checklists Before and After Schema Remediation

### 24.1. Confirming the Right Environment

- [ ] Verified **exact cluster/environment**, not just `cluster_name`.
- [ ] Java contact points, native transport, TLS/auth, and local DC are right.
- [ ] Application release/version and migration version recorded.
- [ ] Using **fully qualified** `keyspace.table` where needed.
- [ ] Checked unquoted/lowercase vs. quoted/case-sensitive identifiers.
- [ ] Service role and schema/user-table permissions match.
- [ ] Identified whether failure occurs at PREPARE or EXECUTE.
- [ ] Did not mistake `Unauthorized`/`Unavailable`/timeout for missing table.
- [ ] Did not infer cluster-wide schema agreement from one `UN` node.

### 24.2. Verifying Actual Schema

- [ ] `system_schema.keyspaces` has expected keyspace/replication config.
- [ ] `system_schema.tables` has expected table name.
- [ ] `system_schema.columns` matches types/PK/clustering layout.
- [ ] Index/view/type metadata verified if queries rely on them.
- [ ] Schema versions compared across relevant UP nodes.
- [ ] DOWN/JOINING nodes identified with rejoin gate required.
- [ ] `nodetool describecluster`/`gossipinfo` read with vantage-point awareness.
- [ ] Driver `session.getMetadata()` fetched fresh rather than holding a stale object.
- [ ] `checkSchemaAgreement()` used properly with timeout/budget.
- [ ] `isSchemaInAgreement()` not taken from a SELECT as proof of agreement.

### 24.3. Migrations and Java Driver

- [ ] Only one migration runner actively dispatches DDL at a time.
- [ ] `IF NOT EXISTS` is not treated as schema-definition validation.
- [ ] DDL is source-controlled, reviewed, versioned, and compatibility-planned.
- [ ] Old and new code coexist safely during rolling releases.
- [ ] `DROP COLUMN`/`DROP TABLE` executed only after zero remaining dependencies and backups exist.
- [ ] Prepared CQL verified after DDL agreement and metadata refresh.
- [ ] Bounded polling used—no blind `Thread.sleep(30000)` or infinite retries.
- [ ] Exceptions retain root causes/coordinators; never catch-all to auto-create tables.
- [ ] Older Cassandra nodes are never fed unsupported DDL mid-upgrade.
- [ ] CQL/metadata tested under the app role, not just superuser.

### 24.4. Post-Fix Verification

- [ ] All UP nodes within scope are schema-agreed with no lingering drift.
- [ ] Previously DOWN nodes pass the rejoin schema gate.
- [ ] Keyspace/table/columns match the full definition, not just name existence.
- [ ] `session.prepare` and production query families succeed.
- [ ] WCL/RCL match RF/local DC and business contracts.
- [ ] Data oracle (expected key/value/version) PASSES; separate migration/restore if needed.
- [ ] Error rates, timeouts, retries, and p95/p99 remain stable across windows.
- [ ] No schema storms triggered by healthchecks or apps.
- [ ] Incident evidence/rollback plan archived and handoff owner assigned.
- [ ] No `DROP`/`TRUNCATE`/system-table edits used as workarounds.

## 25. "Quick Fixes" to Avoid

### 25.1. `DROP TABLE` Followed by `CREATE TABLE`

**Wrong:** A service pod reports `unconfigured table`, so the DBA drops and recreates it to "refresh schema".

**Harm:** Can wipe existing table data, break prepared queries/caches everywhere, and destroy restore/replica state. Creating a new table with the same name **does not bring data back**.

**Right:** Compare `system_schema` across nodes, agreement/versions, cluster/role, then use a reviewed migration or client fix; never touch data before gathering evidence.

### 25.2. Manually Editing `system.local` or `system_schema`

**Wrong:** Seeing differing `schema_version` UUIDs and manually updating system tables.

**Harm:** Cassandra owns schema internals; manual edits risk unrecoverable divergence, metadata corruption, and unsupported states.

**Right:** Investigate gossip/schema propagation/DDL conflicts/versions, escalate to DBAs, and follow **supported procedures** for your Cassandra version.

### 25.3. Restarting All Nodes Simultaneously

**Wrong:** Seeing disagreement and immediately restarting the whole cluster to "reset caches".

**Harm:** Loses quorum/availability, causes startup/streaming/commitlog replay contention, and destroys volatile diagnostic evidence.

**Right:** Preserve logs/snapshots and inspect nodes individually; if a rolling restart is truly warranted, require an owner, RF/CL safety gates, and rollback.

### 25.4. Downgrading CL from `LOCAL_QUORUM` to `ONE`

**Wrong:** After a schema migration, reads/writes fail due to missing replicas, so the team lowers CL to turn tests green.

**Harm:** Fails to resolve schema mismatches, masks replica outages, and weakens consistency/freshness guarantees.

**Right:** CL is a business contract. Separate schema validation, replica availability, and data correctness; never weaken contracts just to hide errors.

### 25.5. Retrying Every `InvalidQueryException` Infinitely

**Wrong:** Sleeping 100ms and retrying forever on any CQL error.

**Harm:** Typos, wrong tables, missing columns, and Unauthorized never self-heal; retries generate load and stall rollouts.

**Right:** Retry **conditionally** within a deadline only when a migration is verified to be converging; permanent query/schema drift must fail fast.

### 25.6. Running `CREATE TABLE IF NOT EXISTS` on Every HTTP Request

**Wrong:** Repository checks table existence per request and issues CREATE when an error occurs.

**Harm:** Schema chatter/DDL storms, auth side effects, migration races, hard rollbacks, and masked misconfigurations.

**Right:** Schema belongs to a dedicated migration runner. Apps perform only low-frequency readiness/query checks.

### 25.7. Treating `Schema agreement PASS` as Proof All Data Restored

**Wrong:** All nodes report the same schema version, so backup restoration is declared complete.

**Harm:** Data may remain unloaded, SSTables missing, repair incomplete, CL unmet, or expected PKs empty.

**Right:** Verify historical seeded keys, data manifests/checksums, restore/repair runbooks, and CQL at required CL.

### 25.8. Mistaking `NoNodeAvailable` for a Missing Keyspace

**Wrong:** Driver has no usable coordinator, so the team runs DDL to recreate the keyspace.

**Harm:** Root cause is local DC/routing/auth/transport, not schema.

**Right:** Inspect driver node metadata, contact points, local DC, TLS/auth, and connectivity first; classify as schema only when query validation proves it.

### 25.9. Checking Tables in Only One DC

**Wrong:** `system_schema` looks good in `dc1`, so the team assumes `dc2` already has the new schema.

**Harm:** Inter-DC propagation/network issues or DOWN nodes can leave `dc2` behind.

**Right:** Run schema probes and data CL probes per deployment region; explicitly report coverage and DOWN-node caveats.

### 25.10. Waiting for Matching Schema UUIDs and Ignoring SLOs/Error Rates

**Wrong:** Versions match and rollout goes GO despite high app p99/timeouts.

**Harm:** Apps may be caught in reprepare storms, cold caches, network faults, or CL replica failures; schema agreement does not measure latency.

**Right:** Post-agreement, verify reads/writes at required CL, data oracles, and stable p95/p99/retries/errors over an adequate sample window.

## 26. Self-Assessment Questions and Suggested Answers

**Q1.** Does `unconfigured table` prove the table is missing on every node?  
**Hint:** No; it reflects the responding coordinator's schema or the namespace used by the query.

**Q2.** How does `Keyspace ... does not exist` differ from `Unauthorized`?  
**Hint:** One is schema/namespace resolution, the other is permissions; inspect exception type/cause before acting.

**Q3.** Why use fully qualified `keyspace.table` names during diagnostics?  
**Hint:** Avoids depending on a session/`cqlsh` current keyspace.

**Q4.** Does `USE catalog_lab` in `cqlsh` change the Java service's keyspace?  
**Hint:** No; only that `cqlsh` session.

**Q5.** How does Cassandra interpret unquoted `OrderEvents`?  
**Hint:** Lowercases it to `orderevents`.

**Q6.** Are `"OrderEvents"` and `orderevents` the same table?  
**Hint:** No; quoted identifiers are case-sensitive.

**Q7.** Why doesn't a succeeding `CREATE TABLE IF NOT EXISTS` prove the schema is right?  
**Hint:** An existing table might have a different primary key, types, or columns.

**Q8.** Does an existing keyspace imply any particular table exists?  
**Hint:** No; a keyspace is namespace and replication metadata.

**Q9.** Which nodes does schema agreement cover?  
**Hint:** Nodes considered UP/known from the check's perspective; DOWN nodes are not guaranteed.

**Q10.** Does schema agreement guarantee data is restored/repaired?  
**Hint:** No; metadata and data lifecycles are separate.

**Q11.** Is the `schema_version` UUID a Git migration version?  
**Hint:** No; it identifies the node's schema state.

**Q12.** Should you edit `system.local.schema_version` manually so UUIDs match?  
**Hint:** No; Cassandra manages internals—fix propagation/root cause instead.

**Q13.** Does `nodetool status UN` prove schema agreement?  
**Hint:** No; U=Up, N=Normal, not schema version.

**Q14.** Which command groups schema versions by peers?  
**Hint:** `nodetool describecluster` (alongside checking local `schema_version` per node).

**Q15.** If nodes A/B show V2, C shows V1, and all are UN, what does that indicate?  
**Hint:** Schema disagreement or transient propagation from the measured vantage point.

**Q16.** If schema versions match yet a column query fails, what should you inspect?  
**Hint:** Definitions/DTOs/CQL/`system_schema.columns`; agreement can mean "unanimous wrong schema".

**Q17.** Which CQL lists keyspaces?  
**Hint:** `SELECT ... FROM system_schema.keyspaces`.

**Q18.** Which CQL lists table names for a keyspace?  
**Hint:** `system_schema.tables WHERE keyspace_name=?`.

**Q19.** Which CQL checks columns, types, and PK kinds?  
**Hint:** `system_schema.columns` filtered by keyspace and table.

**Q20.** Can `DESCRIBE TABLE` be sent via every Java Driver `execute` call as standard CQL?  
**Hint:** No; it is a `cqlsh` command—use metadata or `system_schema` in Java.

**Q21.** Does `system.peers_v2` have identical columns in every Cassandra version?  
**Hint:** Never assume; run `DESCRIBE TABLE` to check the actual schema.

**Q22.** Why check local `schema_version` directly on multiple nodes?  
**Hint:** Peer metadata/gossip view on one coordinator may be stale.

**Q23.** Right after DDL runs, are differing schema versions for a few seconds always a bug?  
**Hint:** No; it may be transient propagation—wait within a bounded deadline.

**Q24.** If the deadline expires and versions still differ, what should you do?  
**Hint:** HOLD rollout, gather logs/network/schema-apply evidence, and escalate.

**Q25.** What does `session.checkSchemaAgreement()` do?  
**Hint:** Checks agreement at call time; it does not run DDL or fix schemas.

**Q26.** Should `isSchemaInAgreement()` from a SELECT prove agreement?  
**Hint:** No; it applies after DDL, and non-DDL may default to true.

**Q27.** Why can `session.getMetadata()` captured before DDL look wrong afterward?  
**Hint:** It is an older metadata snapshot; fetch a fresh snapshot after schema refresh.

**Q28.** Does `Metadata.getKeyspace` finding the keyspace prove replicas satisfy CL?  
**Hint:** No; metadata visibility differs from read/write availability.

**Q29.** When `PREPARE` fails due to a missing table, did the `INSERT` execute?  
**Hint:** No, if the failure happened during `PREPARE` for that statement.

**Q30.** Does `UNPREPARED` mean the table was dropped?  
**Hint:** No; the node may have lost its prepared cache and the driver re-prepares; verify cause/schema.

**Q31.** Why shouldn't 20 Java pods all run `ALTER TABLE` on boot?  
**Hint:** DDL races/churn, schema disagreement, and chaotic rollouts.

**Q32.** Does a migration history table automatically provide a distributed lock?  
**Hint:** No, not with plain INSERTs lacking CAS/owner coordination.

**Q33.** What does expand–migrate–contract buy you?  
**Hint:** Keeps old and new apps compatible during rolling deployments and backfills.

**Q34.** Can you change a partition key with `ALTER TABLE ADD`?  
**Hint:** Not primary-key semantics; typically requires a new table plus backfill and cutover.

**Q35.** If keyspace RF increases and schema agrees, is data already on the new replica?  
**Hint:** No; requires separate repair/streaming and data verification.

**Q36.** Why isn't `nodetool repair` a fix for schema disagreement?  
**Hint:** Repair syncs data replicas/SSTables, not DDL/schema state.

**Q37.** Admin `cqlsh` PASSES while the service role gets `Unauthorized`; where is the root cause?  
**Hint:** Permissions/role—do not assume missing table.

**Q38.** Is `NoNodeAvailableException` a missing-keyspace error?  
**Hint:** No; the driver found no usable coordinator—inspect config/local DC.

**Q39.** Is `UnavailableException` schema disagreement?  
**Hint:** No; it reflects replica liveness/CL availability.

**Q40.** Does a DDL request timeout prove the DDL did not apply?  
**Hint:** No; outcome may be ambiguous—reconcile schema versions/definitions.

**Q41.** Why never run `DROP TABLE` just because a Java pod reports "not found"?  
**Hint:** Risks destroying data when the real issue is namespace, metadata, or propagation.

**Q42.** With C DOWN and A/B agreement PASSING, can traffic hit C immediately upon UP?  
**Hint:** Requires a rejoin schema/data/readiness gate; never assumed automatically.

**Q43.** Why don't `dc1` results represent `dc2`?  
**Hint:** Separate schema propagation, local DC, RF/CL, and network availability.

**Q44.** If SELECT throws no error yet returns empty after restore, which layer do you inspect?  
**Hint:** Data restore/TTL/partition/CL, not schema by default.

**Q45.** What does a `LOCAL_QUORUM` query need besides schema agreement?  
**Hint:** Enough live natural replicas for CL, plus accurate data/oracle/SLO.

**Q46.** What is the flaw in a negative test using `assertThrows(Exception.class)`?  
**Hint:** Can pass due to network, auth, or syntax errors; assert the specific exception.

**Q47.** What should go into an incident ticket to diagnose schema disagreement?  
**Hint:** App/driver/server versions, keyspace/table/role, coordinator, per-node schema versions, DDL timeline, sanitized errors, CL probes.

**Q48.** When can traffic open after a schema fix?  
**Hint:** After passing gates for target/permissions, definition, UP-node agreement/rejoin, Java metadata/PREPARE, data oracle at CL, and stable SLOs.

## 27. Summary: From "Table Not Found" to Exact Root Cause

~~~text
             INVALID QUERY / MISSING KEYSPACE-TABLE
                              |
                  1. Verify target identity
                 cluster + DC + role + app release
                              |
                  2. Check CQL identifiers
               fully qualified name + case + quote
                              |
                  3. Inspect system_schema
              keyspace + table + columns + PK/types
                              |
                 4. Compare per-node schema
            schema_version + describecluster + logs
                              |
                +-------------+--------------+
                |                            |
           AGREED BUT WRONG             DIFFERENT VERSIONS
                |                            |
           App config/migration          Gossip/DDL/rejoin
           RBAC/definition drift         investigate and HOLD
                |                            |
                +-------------+--------------+
                              |
                  5. Java metadata refresh
                session.getMetadata() + PREPARE
                              |
                  6. Verify business query
            required RF/CL + expected value/revision
                              |
                   7. SLO and rollout gate
                     GO / HOLD / STOP
~~~

### 27.1. Seven Principles to Remember

1. **Object errors are clues, not complete proof.** `unconfigured table` can stem from namespace, casing, role, migration timing, or a stale coordinator.
2. **Schema metadata is distributed.** DDL accepted by one coordinator does not mean every node knows it yet. Compare schema versions, especially on failing nodes.
3. **Agreement is scoped.** It covers UP nodes, without guaranteeing DOWN nodes or completed data restores/repairs.
4. **Driver metadata has its own lifecycle.** Stale snapshots, prepared statements, and keyspace config can make Java see something different from `cqlsh`.
5. **Migrations need a coordinator.** Single runner, versioned DDL, expand–migrate–contract, bounded waits, and schema diffs; `IF NOT EXISTS` is not contract validation.
6. **Never use destructive operations as workarounds.** `DROP`, `TRUNCATE`, editing system tables, mass cluster restarts, or lowering CL can worsen incidents.
7. **Recovery is proven by real queries.** Verify exact tables, `session.prepare`, reads/writes at business CL, and data oracles, then monitor errors/p99 over an adequate window.

**Core takeaway:** When hitting `Keyspace/table does not exist` in Apache Cassandra, ask **"Does the object exist in the right cluster, the right namespace, and the schema views of which coordinators?"** If schema versions haven't converged, troubleshoot **schema propagation / DDL lifecycle**; if versions already match yet CQL still fails, investigate **identifiers, schema drift, permissions, or Java Driver metadata**. Declare the service ready only after CQL at required CL and business data pass verification.

### 27.2. Practice Scope and Deeper Testing

Single-node labs here demonstrate **wrong names/namespaces, schema creation, and waiting for agreement**—not true multi-node schema disagreement. Testing inter-node propagation requires a **real multi-node cluster** with proper RF/DC/seed/rack/gossip configuration and controlled staging fault injection. In this documentation workflow, STEP 4 finalizes technical Markdown; STEP 6 Content QA deeply verifies accuracy and executes snippets with the appropriate toolchain. Never treat unexecuted examples as production test results.

## References

- [Apache Cassandra — Documentation](https://cassandra.apache.org/doc/stable/) — official versioned docs on CQL, schemas, architecture, and operations.
- [Apache Cassandra — CQL and data modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — keyspace/table design, query-first modeling, and primary-key restrictions.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — tokens, coordinators, natural replicas, RF, and consistency levels.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html) — `USE`, `DESCRIBE`, `CONSISTENCY`, and CQL diagnostics.
- [Apache Cassandra — nodetool describecluster](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/describecluster.html) — schema versions and cluster status per `nodetool`.
- [Apache Cassandra — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — server request/error metrics and Cassandra resources.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — scope of data repair vs. schema propagation.
- [Apache Java Driver 4.18 — Schema metadata](https://apache.github.io/cassandra-java-driver/4.18.0/core/metadata/schema/) — agreement, schema-change events, and metadata refresh.
- [Apache Java Driver 4.18 — Metadata overview](https://apache.github.io/cassandra-java-driver/4.18.0/core/metadata/) — snapshot semantics and node/schema metadata.
- [Apache Java Driver 4.18 — Node metadata](https://apache.github.io/cassandra-java-driver/4.18.0/core/metadata/node/) — node states, local DC, and driver view.
- [Apache Java Driver 4.18 — Prepared statements](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/) — `PREPARE`, caching, and re-prepare.
- [Apache Java Driver 4.18 — ExecutionInfo Javadoc](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/cql/ExecutionInfo.html) — `isSchemaInAgreement` semantics and coordinator info.
- [Apache Java Driver 4.18 — Configuration](https://apache.github.io/cassandra-java-driver/4.18.1/core/configuration/) — driver local DC, keyspace, metadata/timeout policies.
- [Apache Java Driver 4.18 — Retry policies](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/) — error/attempt classification and avoiding non-idempotent retries.
- [JUnit 5 User Guide](https://docs.junit.org/current/user-guide/) — assertions, test lifecycle, and integration setup.
