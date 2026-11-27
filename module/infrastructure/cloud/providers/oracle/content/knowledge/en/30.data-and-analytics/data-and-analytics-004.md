# GoldenGate and CDC-Based Data Replication

## 1. Objectives and Usage Context

In the **Data and Analytics** chapter of the **CLOUD_PROVIDERS_ORACLE** module, GoldenGate provides a way to stream changes from transactional systems to target systems without repeatedly copying entire tables. On Oracle Cloud Infrastructure, this mechanism supports data warehouses, operational reporting, data integration, and database migrations.

After completing this lesson, you will be able to:

- Explain transaction-log-based CDC and distinguish it from timestamp-based incremental polling.
- Describe the roles of Extract, trails, Distribution/Receiver, and Replicat.
- Prepare source, target, connectivity, and permissions for an Oracle-to-Oracle stream.
- Distinguish initial baseline data from subsequent incremental changes applied afterward.
- Practice verifying inserts, updates, deletes, rollbacks, and recovery after stopping a process.
- Evaluate latency, backlog, retention, correctness, and operational costs.

This lesson uses a **single write source → single replication target** model as its baseline. Bidirectional, multi-source, or streaming-platform-event architectures require dedicated designs for identity, ordering, conflicts, and replayability.

## 2. What Is CDC and Why Is a Transaction Log Needed?

### 2.1. Distinguishing Current State from Change History

Suppose the `ORDERS` table has one million rows, yet only a few thousand changes occur per minute. Repeatedly copying the whole table wastes I/O, CPU, bandwidth, and synchronization time. CDC, short for **Change Data Capture**, focuses strictly on the data that changed.

A log-based CDC mechanism reads transaction records from the source, identifies changes within the configured scope, and delivers them to the target. For Oracle Database, GoldenGate uses redo logs and capture mechanisms suited to the source's configuration and version.

Oracle GoldenGate is a transactional data integration and replication tool; OCI GoldenGate delivers this capability as a managed cloud service. Managed infrastructure does not replace customer responsibility for mapping, permissions, initial instantiation, and reconciliation. [Introducing OCI GoldenGate](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/about-oracle-cloud-infrastructure-goldengate.html).

### 2.2. Comparing Against Timestamp-Based Polling

| Approach | Characteristics to Consider |
| --- | --- |
| Full table copy | Simple to reason about, but requires consistency handling while source writes continue |
| Querying `WHERE updated_at > ...` | Relies on applications updating timestamps reliably; misses hard deletes |
| Triggers writing to a change table | Can add business semantics, but increases logic overhead at the source |
| Transaction-log-based CDC | Tracks transactional changes; requires log configuration and retaining readable history |

For instance, an order might transition from `NEW` to `PAID` and then `CANCELLED` between two polling intervals. Reading current state sees only `CANCELLED` and cannot reconstruct the two prior state transitions. If a row is hard-deleted, a timestamp query on the base table returns nothing at all.

CDC does not automatically turn every table mutation into a business domain event. An `UPDATE` record might represent a profile edit, a payment confirmation, or a maintenance job. When consumers require semantic events like "payment accepted," the application may need an explicit event contract or outbox pattern rather than inferring intent solely from table and column names.

### 2.3. "Near Real-Time" Still Has Latency

Changes must pass through capture, trail storage, transport, and apply. Latency depends on source transactions, system load, networking, and target capacity.

A reporting target database can lag behind the source by several seconds—or much longer during a backlog. Applications should never assume a freshly committed source transaction is immediately readable at the target. If business logic requires read-your-writes consistency, design corresponding read routing and consistency guarantees.

## 3. Components of a GoldenGate Pipeline

### 3.1. Basic Data Flow

~~~mermaid
flowchart LR
    S["Source Oracle Database"] --> L["Redo / archived redo"]
    L --> E["Extract"]
    E --> T1["Source trail"]
    T1 --> D["Distribution Path"]
    D --> R["Receiver"]
    R --> T2["Trail on target deployment"]
    T2 --> A["Replicat"]
    A --> T["Target database"]
~~~

This diagram shows a two-deployment topology. When a single deployment handles both capture and apply, Replicat can read the local trail directly without a Distribution/Receiver path between deployments.

### 3.2. Role of Each Component

| Component | Role |
| --- | --- |
| Extract | Captures changes within the source scope |
| Trail | Persists the change stream for downstream reading |
| Distribution Path | Transfers trails between deployments |
| Receiver | Receives trails at the target deployment |
| Replicat | Reads trails and applies changes to the target |
| Checkpoint | Tracks progress for resumption and recovery |

Distribution Paths are used in distributed topologies; the receiving side accepts data via the Receiver Service. You do not need to add one solely because source and target are two separate databases. [Distribution Paths in OCI GoldenGate](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/replicate/add-a-distribution-path.html).

Trails provide a buffer between stages. If the target pauses temporarily, the source can continue being captured within remaining capacity and storage limits. This buffer is finite: during prolonged outages, account for trail disk capacity and source log retention.

### 3.3. Deployments and Connections in OCI

In OCI GoldenGate, a deployment is the runtime environment executing selected components. A connection stores connectivity details for a source or target. Connections must be assigned to a deployment before use.

The deployment type, technology, and version determine which connections are supported, along with their source/target roles. Do not assume every technology can both capture and apply within the same deployment. [OCI GoldenGate Connections](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/explore-connections.html), [Supported Technologies](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/whats-supported.html).

Distinguish the two consoles:

- **Oracle Cloud Console:** manages deployment cloud resources, connections, networking, service configuration, and cloud monitoring.
- **Deployment Console:** manages capture/apply processes, mappings, trails, and GoldenGate operational runtime info.

Login flows and UI locations may vary across versions, deployment types, and authentication modes. When practicing, follow the documentation for the exact deployment you are using.

## 4. Transactions, Checkpoints, and Guarantee Boundaries

### 4.1. Commits and Rollbacks

In a properly configured transactional Oracle-to-Oracle stream, the target receives the effects of committed source transactions. Rolled-back changes must not become committed business data at the target.

Example:

~~~sql
UPDATE app_src.orders
SET status = 'PAID'
WHERE order_id = 1001;

ROLLBACK;
~~~

After the source rolls back and the stream catches up, the target must not change order `1001` to `PAID` from this transaction.

Capture may read and buffer processing state for open transactions. That does not mean target users see uncommitted source transactions.

### 4.2. Ordering and Scoped Consistency

A single transaction may modify multiple rows across multiple tables. If only a subset of tables is captured, the target reflects only that subset, not the entire business system.

Likewise, splitting data across multiple independent Extracts, trails, or Replicats removes any automatic assumption of a single global order observed across all streams at the target. Identify dependent tables and choose appropriate apply modes.

Cases requiring special care include:

- Parent and child tables placed in different replication streams.
- Very large transactions containing huge volumes of changes.
- Multiple sources writing to the same primary key at the target.
- Targets that are message brokers or object stores rather than transactional databases.
- Consumers invoking external APIs or creating side effects outside the apply transaction.

### 4.3. Checkpoints and Recovery

GoldenGate uses checkpoint files, checkpoint tables, and trail metadata to track progress and recover. Checkpoint configuration and target transactional capabilities form the basis for avoiding re-applying already-processed data on restart. Never manually edit checkpoints or trail contents just to make a process "keep running." [Replication Components and Checkpoints](https://docs.oracle.com/en/database/goldengate/core/26/coredoc/overview-components-data-replication-oracle-goldengate.html).

Do not extrapolate the guarantees of a supported replication path into a promise that every external side effect occurs exactly once. When delivering events to independent consumers, the consumer side still requires progress tracking, idempotency, and retry handling per the target protocol.

Manual actions such as repositioning read offsets, skipping errors, changing mappings, or reloading tables can also leave data diverging from what standard recovery expects.

## 5. Preparing Source, Target, and Connectivity

### 5.1. Confirm Technology Pairing Before Deploying

Before creating processes, lock down an inventory table:

| Item | Details to Confirm |
| --- | --- |
| Source | Database type, version, deployment model, container/PDB |
| Target | Database type or target technology, version |
| GoldenGate | Deployment type, technology, and build version |
| Data | Table list, keys, data types, LOBs, and relevant DDL |
| Topology | Unidirectional, source/target counts, deployments, and regions |
| Goals | Target latency, change volume, tolerable outage window |
| Instantiation | Baseline load method and consistency point |
| Operations | Retention, checkpoints, alerts, and reconciliation plan |

A system that "can connect" does not necessarily support every data type or operation an application uses. Verify capture, apply, DDL, and specialized table features.

### 5.2. Logging and Privileges on a Source Oracle Database

For standard Oracle Databases, evaluate `ARCHIVELOG`, supplemental logging, GoldenGate configuration, and capture account privileges. Supplemental logging records additional column data needed to identify rows and values accurately for replication. Beyond database-level minimal supplemental logging, configure appropriate schema- or table-level logging.

`FORCE LOGGING` is an important safeguard to prevent `NOLOGGING` operations from leaving gaps in captured data. Logging levels must match features and versions; increased logging can also increase redo volume. [Preparing Oracle Database for GoldenGate](https://docs.oracle.com/en/middleware/goldengate/core/21.3/oracle-db/preparing-database-oracle-goldengate.html).

A reference inspection query run by a DBA with appropriate privileges on a standard Oracle Database:

~~~sql
SELECT log_mode,
       supplemental_log_data_min,
       force_logging
FROM v$database;
~~~

This query does not verify per-table logging, capture privileges, or full compatibility. Do not grant full DBA privileges to a GoldenGate account merely to make queries run.

Additional items to verify:

- Capture/apply accounts per documentation for the exact database type.
- CDB/PDB scope and object naming conventions.
- Actual supplemental logging enabled on selected tables.
- Accessibility of active redo and archived redo logs still needed.
- Long-running open transactions and memory/space needed for log mining.
- DDL operations or application features that could impact capture.

For Autonomous Database and other managed services, preparation steps can differ from self-managed Oracle Databases. Do not blindly copy `ALTER DATABASE` statements or privilege scripts across models. [Prerequisites for Capturing from Autonomous Database](https://docs.oracle.com/en/database/goldengate/core/26/coredoc/adb-prerequisites-capturing-autonomous-database.html).

### 5.3. Identifying Keys and Target Schema

A primary key or stable unique identifier lets apply locate the exact row for updates and deletes. Without a suitable key, row identification can be expensive or fail to behave as intended. Using `KEYCOLS` when needed must be paired with uniqueness design and appropriate logging; `KEYCOLS` does not enforce uniqueness by itself.

At the target, prepare compatible structures and data types. Review indexes, constraints, triggers, sequences, identity columns, and default values under the replication model. Do not assume a target trigger serves the same role as when an application writes directly.

In a unidirectional model, enforce controls preventing applications from modifying Replicat-managed data at the target. If the target is edited independently, duplicate-key or row-not-found errors often signal data drift.

### 5.4. Networking and Authentication Layers

Separate verification into three layers:

1. OCI IAM permissions to manage or view deployments and connections.
2. Access permissions for the Deployment Console and process management.
3. Database accounts and privileges inside source and target databases.

Holding permissions on OCI cloud resources does not grant redo read or table write privileges inside a database.

On networking, distinguish the path into the Deployment Console from the path from a connection to a database. OCI GoldenGate offers connection routing options such as shared endpoints and dedicated endpoints; source addresses, DNS, routes, and NSG/security rules must match the selected routing model. [OCI GoldenGate Networking Connectivity](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/oci-goldengate-connectivity.html).

Verify in order: DNS → routes → listener port → TLS/wallet → database service → credentials → privileges. A successful TCP connection does not prove an account holds sufficient capture or apply privileges.

Store passwords and wallets in appropriate credential/secret stores. Never embed them in example parameter files, shared logs, or source repositories. When rotating or changing a connection, verify both synchronization to deployments and any resulting network changes.

## 6. Initial Baseline Data and Consistency Points

### 6.1. CDC Does Not Automatically Backfill Existing Rows

If the source already holds data before capture begins and the target is empty, starting CDC from the current point leaves behind every row that is not subsequently modified.

For example, suppose the source has order `1001` before Extract starts. If that order is never updated again, CDC starting from now will never create it at the target. If it is later updated while missing at the target, apply can fail with a row-not-found error.

**Initial load / instantiation** establishes the baseline state at the target. CDC then streams subsequent changes starting from that consistency point. Both halves must be coordinated into one verified procedure. [Instantiation Concepts](https://docs.oracle.com/en/database/goldengate/core/26/coredoc/instantiate-instantiating.html).

### 6.2. Snapshot Model at Consistency Point S

Suppose a source snapshot reflects all transactions committed up to consistency point `S`. Once this snapshot is loaded, the target reflects those transactions. CDC must resume from the exact boundary to avoid gaps or duplicate applications.

~~~text
T0: Prepare logging and capture using the chosen method
T1: Record consistency point S for the baseline dataset
T2: Load the baseline dataset into the target
T3: Start applying CDC changes not yet included in the baseline
T4: Reconcile, drain backlog, and open target data for consumers
~~~

This is a logical model. Obtaining the SCN, registering Extract, applying instantiation filters, and setting start positions depend on the chosen load method and version. Never replace the entire process with simply selecting "Now."

A transaction may begin before `S` and commit after `S`. Capture must retain enough log history to handle that transaction, even though its effects are absent from the snapshot. That is why registration SCN, open transactions, and log retention matter rather than merely comparing export timestamps.

Oracle's precise instantiation guides coordinate CDC Extract, the instantiation point, and initial-load processes; follow one complete matching procedure rather than stitching together steps from incompatible guides. [Precise Instantiation with Initial Load Extract](https://docs.oracle.com/en/database/goldengate/core/26/coredoc/instantiate-add-initial-load-extract-using-admin-client.html).

### 6.3. Choosing Instantiation Based on Operational Conditions

| Condition | Design Approach |
| --- | --- |
| Both tables are empty, no active transactions | Start the stream before any DML; suited for basic labs |
| Writes can pause during a controlled window | Create baseline and CDC boundary while source is quiescent |
| Source must keep accepting transactions | Use snapshot/export/initial load coordinated with CDC and a consistency point |
| Need to reload a subset of data | Design table/range resync coordinated with running processes |

Do not rely on collision-handling flags to mask every instantiation mistake. If a chosen method requires overlap handling, know its exact scope, conditions, and when to turn it off. Always reconcile data after loading.

## 7. Configuring an Oracle-to-Oracle Stream on OCI

### 7.1. Deployment Sequence

A reference sequence is:

1. Confirm technology support, source/target compatibility, and instantiation method.
2. Prepare IAM, networking, database accounts, and logging.
3. Create a deployment matching the technology.
4. Create source and target connections in the Oracle Cloud Console.
5. Assign those connections to the deployment using them.
6. Test connectivity and prepare checkpoint structures.
7. Create Extract with an explicit capture scope.
8. Create a Distribution Path if the topology uses separate deployments.
9. Complete the baseline load and configure Replicat at the exact boundary.
10. Start processes, monitor, and reconcile before handoff.

OCI GoldenGate workflows separate cloud resource setup, connection assignment, and replication process management. [Basic OCI GoldenGate Task Flows](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/basic-taskflows.html).

### 7.2. Selecting Tables for Extract

In the Deployment Console, choose the Extract type matching the source, credentials, start position, and trail. For Oracle, Integrated Extract is a provided capture option; follow the guide for your exact deployment version. [Adding an Extract for Oracle Database](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/replicate/add-an-extract-for-oracle-ai-database.html).

A minimal **capture scope snippet**:

~~~text
TABLE APP_SRC.ORDERS;
~~~

This snippet is not a complete parameter file. Credentials, trail settings, registration, encryption, and UI-generated properties still need configuration.

If Extract operates in a multitenant environment requiring container qualification, source names may need `PDB.SCHEMA.TABLE`. Use the exact connection scope and object qualification required by your capture mode—never guess table naming prefixes.

### 7.3. Replicat Mapping

Mapping snippet from one source table to one target table:

~~~text
MAP APP_SRC.ORDERS, TARGET APP_DST.ORDERS;
~~~

`TABLE` selects objects for capture; `MAP ... TARGET ...` specifies the source–target relationship for apply. Filtering or column transformations must be explicitly designed if schemas differ. [TABLE and MAP Reference](https://docs.oracle.com/en/database/goldengate/core/26/reference/table-map.html).

Starting with a single table that has a primary key and simple data types makes CDC behavior easy to observe. Expand to wildcards only after confirming which tables will be captured, whether logging is ready, and whether administrative tables might accidentally be included.

### 7.4. Checkpoints and Process States

Create or select an appropriate checkpoint table for Replicat per the guide. Choose the exact trail and starting position, especially if an initial load or prior trail exists. [Adding a Replicat for Oracle Database](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/replicate/add-a-replicat-for-oracle-ai-database.html).

Process names must adhere to process-type and version naming limits. In examples, short names like `EORD` and `RORD` help distinguish processes easily.

After starting, inspect reports, checkpoints, and capture/apply statistics. Status `RUNNING` shows the process is active; it does not prove there are no missing rows, incorrect mappings, or silently skipped changes.

## 8. Hands-On CDC with an Orders Table

### 8.1. Prerequisites and Objectives

Use two Oracle Databases or two suitable source/target schemas provisioned for the lab. Assume source schema `APP_SRC` and target schema `APP_DST`. The DBA has already prepared logging, GoldenGate accounts, and privileges appropriate for the database type.

This lab uses synthetic data. No bidirectional configuration or production tables are required.

The goal is to prove:

- Committed DML at the source is reflected at the target.
- Rolled-back transactions do not alter target state.
- Stopping Replicat delays the target and can resume cleanly from checkpoint.
- Final state reconciles by primary key and content.

### 8.2. Create Two Empty Tables

Run the following DDL once in the source schema and once in the target schema:

~~~sql
CREATE TABLE orders (
    order_id    NUMBER(12)       PRIMARY KEY,
    customer_id NUMBER(12)       NOT NULL,
    status      VARCHAR2(20 CHAR) NOT NULL,
    amount      NUMBER(12, 2)    NOT NULL,
    changed_at  TIMESTAMP(6)     DEFAULT SYSTIMESTAMP NOT NULL
);
~~~

In the source schema, the table is `APP_SRC.ORDERS`; in the target schema, `APP_DST.ORDERS`. This lab creates matching structures on both sides independently rather than relying on DDL replication.

Confirm both tables are empty, no application sessions are writing to them, and all prerequisite steps are complete. Disable auto-commit in your SQL client for the transaction-testing steps.

Start Extract and Replicat with the exact table scope, trail, and start position while the source is still empty. Generate DML only after processes are ready.

This eliminates needing an initial load inside the lab. For tables that already hold data, apply the initial load methods from the earlier section rather than using an empty-table shortcut.

### 8.3. Insert and Commit

Run all DML below on the **source**:

~~~sql
INSERT INTO app_src.orders
    (order_id, customer_id, status, amount)
VALUES
    (1001, 501, 'NEW', 125.00);

INSERT INTO app_src.orders
    (order_id, customer_id, status, amount)
VALUES
    (1002, 502, 'NEW', 80.00);

COMMIT;
~~~

Once the stream catches up, query the target:

~~~sql
SELECT order_id, customer_id, status, amount
FROM app_dst.orders
ORDER BY order_id;
~~~

The expected result is rows `1001` and `1002` with matching values. Inspect process statistics and any errors rather than looking only at a single lag metric.

Insert one more row:

~~~sql
INSERT INTO app_src.orders
    (order_id, customer_id, status, amount)
VALUES
    (1003, 503, 'NEW', 30.00);

COMMIT;
~~~

Order `1003` should appear at the target after apply within the lab environment's expected latency.

### 8.4. Committed Update

~~~sql
UPDATE app_src.orders
SET status = 'PAID',
    changed_at = SYSTIMESTAMP
WHERE order_id = 1001;

COMMIT;
~~~

At the target, order `1001` must transition from `NEW` to `PAID`, while `amount` remains `125.00`.

This DML demonstrates CDC propagating an update onto existing state. The target must have the correct baseline data; if order `1001` did not already exist, a standalone update would not reliably produce the desired state.

### 8.5. Change Followed by Rollback

~~~sql
UPDATE app_src.orders
SET amount = 999.00,
    changed_at = SYSTIMESTAMP
WHERE order_id = 1002;

ROLLBACK;
~~~

After confirming the source rolled back, check order `1002` at the target. Its amount must still be `80.00`.

If your SQL client has auto-commit enabled, this test no longer exercises rollback. Always record client transaction mode and avoid mixing DDL into the middle of this test.

### 8.6. Committed Delete

~~~sql
DELETE FROM app_src.orders
WHERE order_id = 1002;

COMMIT;
~~~

Once the stream catches up, order `1002` must no longer exist at the target under the standard replication mapping in use.

This highlights an easily observed contrast with base-table timestamp polling: after a hard delete, the row no longer exists in the source table for an incremental query to return.

### 8.7. Multi-Operation Transaction

~~~sql
INSERT INTO app_src.orders
    (order_id, customer_id, status, amount)
VALUES
    (1004, 504, 'NEW', 50.00);

UPDATE app_src.orders
SET status = 'PAID',
    amount = 31.00,
    changed_at = SYSTIMESTAMP
WHERE order_id = 1003;

COMMIT;
~~~

Reconcile after apply completes: order `1004` exists, and order `1003` has `status='PAID'` and `amount=31.00`.

This lab tests one transaction across one stream and one table. Do not generalize this result into an atomic visibility guarantee across multiple independent targets or multiple Replicats.

### 8.8. Pause Apply and Resume

In the Deployment Console, stop Replicat via supported operational controls; leave Extract running if the environment has sufficient resources and trail capacity.

At the source, execute:

~~~sql
UPDATE app_src.orders
SET status = 'PAID',
    changed_at = SYSTIMESTAMP
WHERE order_id = 1004;

COMMIT;
~~~

While Replicat remains stopped, the target does not receive this update. Inspect Extract, the trail, and apply positions to see where changes are queued.

Restart Replicat from its current checkpoint using standard procedure. Do not select start from "Now" or reset position merely to make displayed lag drop.

Once the backlog clears, order `1004` at the target must show `status='PAID'`. Earlier data must remain accurate with no duplicate-key rows.

### 8.9. Final State Reconciliation

Pause generating DML in the lab scope, wait for the stream to drain all pending changes, and run the detailed query on both source and target:

~~~sql
SELECT order_id, customer_id, status, amount
FROM orders
ORDER BY order_id;
~~~

Expected results:

| order_id | customer_id | status | amount |
| --- | --- | --- | --- |
| 1001 | 501 | PAID | 125.00 |
| 1003 | 503 | PAID | 31.00 |
| 1004 | 504 | PAID | 50.00 |

Order `1002` was deleted; the rolled-back `999.00` change does not appear in the final state.

You can also run an aggregate check:

~~~sql
SELECT COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM orders;
~~~

The result is `3` rows totaling `206.00`. Counts and sums are only quick sanity checks: two different datasets can still share identical row counts and sums. For formal acceptance, reconcile keys and required columns at a consistent point.

`changed_at` is an application-written timestamp, not a precise commit/apply clock. Never rely on it alone to prove latency SLAs.

### 8.10. Handoff and Lab Cleanup

Record the deployment version, table scope, process names, observed checkpoints/lag, execution timestamps, and test results.

If freeing the environment, save needed evidence and stop/delete only lab resources within your assigned responsibility. Never delete shared connections, checkpoints, logging, or databases without confirming no other streams depend on them.

## 9. Monitoring Latency, Backlog, and Correctness

### 9.1. Observe Every Stage

| Question | Signals to Watch |
| --- | --- |
| Is capture keeping up with the source? | Extract progress, capture lag, long-running open transactions |
| Are trails transferring reliably? | Path/receiver status, read/write positions, network errors |
| Is apply keeping up? | Replicat lag, checkpoint progress, throughput, target errors |
| Is the buffer at risk of filling up? | Trail growth rate, disk capacity, and retention |
| Does the target hold accurate data? | Content reconciliation, ignored errors, mapping scope |
| Do consumers see sufficiently fresh data? | End-to-end timing measured via an appropriate mechanism |

OCI GoldenGate emits metrics in the `oci_goldengate` namespace. Metrics and dimensions vary across deployments, processes, pipelines, and versions; select the exact resource rather than copying metric names from another deployment type. [OCI GoldenGate Metrics](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/oracle-cloud-infrastructure-goldengate-metrics.html).

To measure end-to-end latency, evaluate heartbeat mechanisms supported for your replication path. Local capture or apply metrics alone do not represent total elapsed time from source commit to target consumer readiness.

Also monitor metric freshness and missing data points. A dashboard showing no recent data points does not mean lag is zero.

### 9.2. Set Thresholds Around Realistic Goals

For example, suppose a hypothetical data team wants order data to lag under 30 seconds normally. Define alert thresholds, evaluation windows, and peak-load handling rather than placing a single number on a dashboard.

Alerts should cover:

- Stopped or abended processes.
- Continuously climbing lag while the source is active.
- Stalled checkpoints.
- Rapidly growing trails or approaching storage limits.
- Connectivity, permission, schema, or apply errors.
- Reconciliation detecting missing/divergent data despite low lag.

The 30-second threshold here is an illustrative goal, not an SLA or default service guarantee.

### 9.3. Backlog Shrinks Only When Processing Rate Exceeds Arrival Rate

Suppose a backlog currently holds `B` changes, the source keeps generating `λ` changes per second, and apply processes `μ` changes per second. With steady rates and consistent units, you can estimate:

~~~text
If μ > λ:
    Time to catch up ≈ B / (μ - λ)

If μ <= λ:
    Will not catch up while incoming load stays at that rate
~~~

For example, `B=2,000,000`, `λ=1,000/sec`, and `μ=1,600/sec` yields roughly `3,333` seconds, or about `55.6` minutes.

This is a simplified model. Large transactions, locking, per-row complexity, indexes, and inter-transaction dependencies can shift throughput dramatically. Never treat this formula as an operational commitment without measuring the actual workload.

### 9.4. Reconciling at a Meaningful Consistency Point

If the source is still accepting writes, two count queries run at slightly different moments can diverge even when replication is healthy. Choose an appropriate comparison strategy:

- Pause writes briefly in a controlled window during testing.
- Use snapshots or matching transaction boundaries where supported by the technology.
- Slice by stable key ranges or settled time windows.
- Compare checksums/contents using identical normalization rules.
- Explicitly note in-flight rows and ranges that cannot yet be concluded.

When mappings filter or transform data, the target is expected to match the mapping output, not necessarily match the source byte-for-byte. Reconciliation must reflect that data contract.

## 10. Retention, Performance, and Cost

### 10.1. Retain Enough History for Every Stage

At least two categories of history require management:

- Redo / archived redo that capture still needs to read or that recovery requires.
- Trails that downstream processes still need to read or resume from.

If Extract has been stopped for a long time and required source logs are deleted, adding OCPUs to the deployment cannot recreate lost history. If Replicat needs a trail that was already purged, treat it as a data-recovery incident.

A reference trail-sizing model:

~~~text
Minimum planned capacity
≈ Measured trail generation rate × Expected outage duration × Safety factor
~~~

With `5 MiB/sec`, `2 hours`, and a safety factor of `1.5`:

~~~text
5 × 7,200 × 1.5 = 54,000 MiB ≈ 52.7 GiB
~~~

This models a single illustrative buffer and excludes trails on other deployments, overhead, multiple consumers, or catch-up time after recovery. Trail rate must be measured from the workload; do not equate it with table size or total redo size.

Retention should cover detection, response, remediation, and backlog drain time. Sizing solely for process downtime leaves you exposed to running out of history during catch-up.

### 10.2. Identify Bottlenecks Before Scaling Resources

If capture is slow, inspect the source, mining, long transactions, and logging settings. If trail transfer is slow, inspect paths, bandwidth, latency, and fan-out volume. If apply is slow, inspect target CPU/I/O, locks, indexes, and Replicat mode.

Parallelism can boost throughput, but it must align with apply mode and data dependencies. Splitting every table into separate streams purely to multiply processes can complicate consistency and recovery.

OCI GoldenGate sizing guidance accounts for workload, source/target counts, process types, and measured capacity. There is no fixed OCPU count fitting every CDC stream. [Sizing and Capacity Planning](https://docs.oracle.com/en/cloud/paas/goldengate-service/ocigg/oci-goldengate-sizing-and-capacity-planning-guide.html).

Autoscaling or scaling up a deployment also cannot fix a target blocked by long locks, missing indexes, or connection limits.

### 10.3. Cost Components to Budget

When budgeting, include GoldenGate deployment resources, trail storage, source/target databases, backups, network connectivity, logs, and operations. Multi-deployment or multi-target topologies multiply data paths and monitoring surface area.

Supplemental logging and capture still consume resources at the source. Small row counts in large tables are not necessarily lightweight if rows are very wide, contain LOBs, or transactions bundle massive numbers of changes.

For labs, keep scope small and release resources responsibly after saving results. For production, configure storage and resource utilization alerts so you have time to respond before buffers fill up.

## 11. Troubleshooting Along the Data Path

### 11.1. Isolate the Stage Before Repositioning Checkpoints

When the target is missing data, record:

1. Specific table, key, and transaction.
2. Whether the source committed, along with timestamp and transaction marker if available.
3. Whether the table is covered by `TABLE`/`MAP`.
4. Whether Extract has read past the relevant position.
5. Whether the trail has reached where Replicat reads.
6. Whether Replicat hit an error, filtered the row, or is waiting.
7. Whether a user or application modified the row directly at the target.

Only then decide on remediation. Altering checkpoints or picking a new start position before understanding where data was lost can destroy reconciliation traceability.

### 11.2. Common Symptoms

| Symptom | Where to Check |
| --- | --- |
| Unable to create connection | DNS, routes, endpoint, listener, TLS/wallet, credentials |
| Connection works but Extract fails to start | Capture mode, privileges, logging, registration, container scope |
| No new changes at target | Source commit, table scope, Extract, path, Replicat, and filters |
| Duplicate key on apply | Initial load overlap, independent target writes, replay, or mapping |
| Update/delete row not found | Missing baseline data, row edited/deleted at target, key mismatch |
| Increasing capture lag | Source load, mining, long transactions, capture capacity |
| Increasing apply lag | Locks, I/O, indexes, target resources, and apply mode |
| Process running yet content is wrong | Mapping, transformations, ignored errors, schema changes |
| Restart requests missing trail/log | Retention, purge policies, outage history, and resync plan |
| Errors after DDL | DDL support matrix, metadata, target schema, and upgrade plan |

Reports and logs may contain SQL statements, schema names, or sensitive data. When sharing for investigation, use controlled storage and preserve necessary originals.

### 11.3. Never Handle Data Errors by Bulk-Skipping

A duplicate-key or row-not-found error often signals source–target divergence. Skipping errors lets the process move forward while leaving inaccurate data behind.

When a resync is needed:

- Identify affected tables/ranges.
- Preserve evidence and current processing markers.
- Fix the root cause before reloading.
- Choose the baseline load method and new CDC boundary.
- Execute the verified procedure for that topology.
- Reconcile after recovery and document any unverified slices.

Never truncate an active target table and restart from an old checkpoint assuming CDC will magically rebuild every historical row.

## 12. DDL, Bidirectional Flows, and Target Consumption

### 12.1. Schema Changes Require Coordination

Adding columns, changing data types, altering keys, or renaming tables can impact capture and apply. Verify DDL replication capabilities for your exact source/target pair, versions, and object types.

If DDL replication is not used, coordinate source and target schema changes so Replicat never encounters incompatible schemas. Even when DDL replication is supported, application scripts, grants, jobs, and out-of-scope objects still require management.

Do not assume adding `TABLE schema.*` automatically solves every aspect of schema evolution.

### 12.2. Bidirectional Streams Require Conflict Design

In a bidirectional setup, the same key can be modified on both sides. You must address key generation, loop prevention, ownership, conflict detection/resolution, and clock skew if using timestamp-based rules.

A working unidirectional lab does not prove active-active will work safely. Establish clear business ownership rules for where each data type may be modified rather than simply adding a reverse stream.

### 12.3. Distinguishing Replication from Backups and Physical Standby

| Need | What to Evaluate |
| --- | --- |
| Selective table replication and heterogeneous integration | GoldenGate with supported mapping/capture/apply |
| Point-in-time recovery before bugs or accidental deletes | Backups and appropriate recovery mechanisms |
| Standby database and role switchover | HA/DR architectures such as Data Guard per requirements |
| Retaining every state transition for historical analytics | History/event storage design, not just current-state tables |

A valid accidental delete at the source can replicate straight to the target. Therefore, a target table kept identical to the source does not replace a backup capable of restoring state prior to that operation.

Likewise, a target table updated to reflect current state does not automatically preserve every historical version. Analyzing individual changes requires designing an append/history storage model accordingly.

### 12.4. Using CDC in Database Migrations

GoldenGate can help minimize write downtime by loading baseline data beforehand and catching up on changes. During cutover, control source writes, wait for relevant transactions to complete, confirm apply reached the required point, and reconcile before switching applications.

Also prepare objects and settings outside replication scope, such as sequences, privileges, jobs, triggers, connections, and integrations. Once the target begins accepting live application writes, failing back to the old source is no longer a simple endpoint swap—you must have a data-level rollback plan.

A well-operated CDC pipeline requires **accurate instantiation boundaries, recoverable checkpoints, sufficient history retention, and reconciliation evidence**. Together, these allow using OCI GoldenGate to feed analytics or migrate systems while maintaining measurable confidence in target freshness and accuracy.
