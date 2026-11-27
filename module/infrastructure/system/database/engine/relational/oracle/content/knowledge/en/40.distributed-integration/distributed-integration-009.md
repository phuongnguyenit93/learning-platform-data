# Change Data Capture, GoldenGate, and Distinguishing from Data Guard

A business system often needs to know which data has changed in order to update a data warehouse, synchronize to another application, build near-real-time reports, or emit events to downstream services. Re-reading entire tables on a schedule may seem simple initially, but becomes expensive when data grows large, change rates increase, or low latency is required. **Change Data Capture (CDC)** solves this problem by capturing changes occurring at the source and delivering them to consumers.

In the Oracle ecosystem, Oracle GoldenGate is a widely used platform for capturing, transporting, and applying data changes across different databases or systems. GoldenGate can read Oracle Database redo, convert changes into logical records inside trail files, transmit trails over the network, and apply them at the target. As a result, the target system receives inserts, updates, deletes, and supported structural changes per configuration.

Oracle Data Guard also ships change information from primary to standby, yet its goal and operation differ from GoldenGate. Data Guard primarily protects a database via a standby database for high availability and disaster recovery. GoldenGate primarily serves logical replication and distributing changes to consuming systems. The two technologies can complement each other within the same architecture.

## 1. What Is Change Data Capture?

Change Data Capture is the technique of identifying and forwarding changes occurring in source data. Changes typically include:

- `INSERT`: a new row is added.
- `UPDATE`: values of one or more columns change.
- `DELETE`: a row is removed.
- DDL: certain structural changes such as creating, altering, or dropping objects if supported by the tool and configuration.

CDC differs from copying entire tables on a schedule. With a full refresh, the system re-reads the entire dataset to build a new state. With CDC, the system reads changes since a known position, reducing the volume of data transferred when the change rate is small relative to total dataset size.

For example, table `ORDERS` has 200 million rows, yet only a few thousand transactions insert or update each minute. A scheduled full refresh every minute would read and transmit a massive amount of data. CDC can transmit only the changes corresponding to newly committed transactions.

### 1.1. Where Is CDC Commonly Used?

| Need | How CDC Helps |
|---|---|
| Database synchronization | Transfers changes from source database to target database |
| Data warehouse | Feeds inserted/updated/deleted records into the warehouse for downstream processing |
| Data lake | Streams changes to another storage or analytics platform |
| Search index | Updates search documents when business data changes |
| Event-driven architecture | Emits change events for downstream services to process |
| Near-real-time reporting | Updates reporting tables or read models from source changes |
| Auditing and analytics | Retains change history per custom policies and formats |

CDC does not itself decide the business meaning of a change. For example, an `UPDATE` changing `ORDER_STATUS` from `NEW` to `CANCELLED` is a data change; whether downstream systems must issue a refund, send a notification, or release inventory is business logic belonging to consuming applications.

### 1.2. CDC Is Not Event Sourcing

CDC captures changes to data already stored in a database. Event sourcing stores business events as the primary source of truth and derives current state by applying those events. Both patterns can coexist in a system, yet not every redo record or row change can be treated as a complete business event.

For instance, a single transaction might update multiple tables to complete an order placement. CDC captures per-table changes. If downstream needs a single `OrderPlaced` business event, either an aggregation layer must group changes by transaction boundary or the application should emit a dedicated business event.

## 2. Ways to Implement CDC

CDC can be implemented in several ways. The chosen method affects latency, completeness, source overhead, and operational complexity.

### 2.1. Snapshot or Timestamp-Column Polling

An application periodically queries rows whose `UPDATED_AT` exceeds the previous watermark:

```sql
SELECT order_id,
       customer_id,
       order_status,
       updated_at
FROM orders
WHERE updated_at > :last_watermark
ORDER BY updated_at, order_id;
```

The advantage is simplicity of understanding and implementation. However, this approach has limitations:

- Cannot detect deleted rows without tombstones or soft-delete mechanisms.
- Can miss changes if timestamps are not updated reliably.
- Two rows sharing the same timestamp at the watermark boundary may be read twice or skipped if logic is imprecise.
- Clocks, precision, and transaction commit order can cause application timestamps not to reflect exact commit order.
- Polling typically scans indexes/ranges repeatedly and can add load to the source table.

If using polling, include a secondary ordering key for a deterministic watermark, such as `(UPDATED_AT, ORDER_ID)`, use an overlap window, and process idempotently. Even so, polling is not full log-based CDC.

### 2.2. Trigger-Based CDC

Triggers on tables record changes into an audit or change table:

```sql
CREATE OR REPLACE TRIGGER orders_audit_trg
AFTER INSERT OR UPDATE OR DELETE ON orders
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        INSERT INTO orders_change_log (
            order_id, operation_type, changed_at
        ) VALUES (
            :NEW.order_id, 'I', SYSTIMESTAMP
        );
    ELSIF UPDATING THEN
        INSERT INTO orders_change_log (
            order_id, operation_type, changed_at
        ) VALUES (
            :NEW.order_id, 'U', SYSTIMESTAMP
        );
    ELSIF DELETING THEN
        INSERT INTO orders_change_log (
            order_id, operation_type, changed_at
        ) VALUES (
            :OLD.order_id, 'D', SYSTIMESTAMP
        );
    END IF;
END;
/
```

The example above illustrates the concept only. A production solution must handle keys, old/new values, transaction identity, bulk DML, error handling, retention, and additional write load.

Trigger-based CDC can record changes in the same transaction, yet adds work onto the application's DML path. Row-level triggers can impose heavy overhead on bulk loads, create tight coupling to table structures, and require careful design to avoid recursion or side effects.

### 2.3. Log-Based CDC

Log-based CDC reads change information from the database transaction log rather than requiring applications to write duplicate change records via triggers. In Oracle, redo logs contain the information needed for database recovery and can be consumed by tools like GoldenGate to reconstruct logical changes.

Advantages of log-based capture:

- Can capture changes from multiple applications without requiring each to maintain change tables.
- Can capture transactions in commit order and preserve transaction boundaries.
- Does not require running polling queries over entire tables to find new rows.
- Can reduce direct overhead on the DML path compared to trigger-based approaches.

However, log-based CDC requires configuring redo/supplemental logging, log access permissions, retention, and proper recovery/checkpoint mechanisms. It also depends on capture support for the specific version, object types, and operations.

### 2.4. Comparing Approaches

| Criterion | Polling | Trigger-Based | Log-Based |
|---|---|---|---|
| Change source | Query on table | Trigger writing change table | Transaction log/redo |
| Delete detection | Requires extra design | Can log explicitly in trigger | Can capture from logs |
| Overhead on DML | Usually low per DML, but adds polling queries | Adds work inside source transaction | Reads logs and captures outside main DML path |
| Latency | Driven by polling interval | Near real-time after commit/trigger processing | Can be near real-time depending on capture and transport |
| Transaction ordering | Must design custom watermark | Can record within same transaction | Can preserve transactions/order from logs |
| Complexity | Low to medium | Medium | Medium to high |
| Best fit | Small tables, simple changes, low latency not critical | Local audit/change log with clear scope | Large-scale sync, many tables, low latency/transaction semantics |

## 3. Redo, Archive Logs, and Supplemental Logging in Oracle CDC

Oracle Database generates redo to support instance recovery and media recovery. Redo records the information needed to reconstruct changes on database blocks. Redo resides in online redo logs and is subsequently archived into archived redo logs.

GoldenGate uses redo to identify logical changes. To fully identify the affected row and columns—especially for updates and deletes—sufficient identifying data must exist in redo. Supplemental logging adds necessary key values or column values into redo.

### 3.1. Online Redo and Archived Redo

When a transaction performs DML, Oracle generates redo in the redo log buffer and writes it to online redo logs via `LGWR`. When a log switch occurs and archiving conditions are met, `ARCn` or equivalent mechanisms produce archived redo logs.

A log-based capture process can read online redo to minimize latency and fall back to archived redo when needed. If required logs are deleted before capture reads them, the process can stall or require restoration from backup/other logs depending on configuration capabilities.

Therefore, archive log retention and backup policies must be designed alongside GoldenGate. Never delete archive logs merely because a database backup finished if GoldenGate Extract still needs to read those logs.

### 3.2. What Is Supplemental Logging?

Standard redo is optimized for recovery. Certain changes do not record enough old values for a CDC tool to uniquely pinpoint which row to update at the target. Supplemental logging instructs Oracle to log additional identifying data into redo.

You can enable database-level minimal supplemental logging:

```sql
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA;
```

Depending on capture mode and tables, additional logging is needed for primary keys, unique keys, or all columns. Database-level example:

```sql
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA (PRIMARY KEY) COLUMNS;
```

Or at the table level:

```sql
ALTER TABLE app.orders
ADD SUPPLEMENTAL LOG DATA (PRIMARY KEY) COLUMNS;
```

These commands must be verified against your Oracle version, GoldenGate configuration, and actual key definitions. Do not enable all-column logging on every table without weighing redo volume and overhead. Enabling supplemental logging increases redo generation in exchange for giving capture enough data to identify changes.

### 3.3. Key Logging and Row Identification

GoldenGate needs to know which target row corresponds to a source row. A primary key is usually the best option. If a table lacks a primary key, a unique key or another configured identifier can be used. For tables without unique keys, identifying rows becomes harder and may require logging more columns.

For example, `ORDERS` has primary key `ORDER_ID`. When `ORDER_STATUS` is updated, target can locate the row by `ORDER_ID` and apply the new value. If a table lacks a unique key, two rows sharing identical values across several columns can prevent apply from identifying a unique row or cause conflicts.

Good primary key/unique key design simplifies CDC, reduces supplemental data volume, and improves apply reliability.

### 3.4. Checking Supplemental Logging

Useful views:

```sql
SELECT supplemental_log_data_min,
       supplemental_log_data_pk,
       supplemental_log_data_ui,
       supplemental_log_data_fk,
       supplemental_log_data_all
FROM v$database;
```

Check table-level log groups:

```sql
SELECT owner,
       table_name,
       log_group_name,
       log_group_type,
       always
FROM dba_log_groups
WHERE owner = 'APP'
  AND table_name = 'ORDERS';
```

Views and columns may vary by version. Confirm actual logging policies before starting capture.

## 4. What Is Oracle GoldenGate?

Oracle GoldenGate is a platform for capturing, transporting, and delivering data changes between source and target systems. GoldenGate supports multiple topologies and diverse database/platform types depending on release, licensing, and deployment configuration.

GoldenGate can be used to:

- Replicate data from Oracle to Oracle.
- Replicate from Oracle to another supported database or data platform.
- Maintain a read-only/reporting copy.
- Feed change data to a data warehouse or data lake.
- Distribute data to multiple consumers.
- Support low-downtime migrations by combining initial load with CDC.

GoldenGate is a logical replication technology. It understands table/record-level data operations and can map, filter, and transform per configuration. This differs from shipping raw blocks/redo to maintain a physical standby identical to the primary.

## 5. Classic GoldenGate Architecture: Extract, Trail, Pump, and Replicat

In Classic architecture, core components typically include:

- **Manager:** manages GoldenGate processes in a Classic deployment, supporting start/stop and administrative tasks.
- **Extract:** reads changes from source redo/logs or supported sources and generates trail records.
- **Local trail:** sequential file holding logical change records on the source host.
- **Data Pump:** secondary Extract on source that reads the local trail and ships data over the network to the target; this is the GoldenGate Data Pump process, not the Oracle Data Pump utility `expdp`/`impdp`.
- **Remote trail:** trail written on the target side or intermediate deployment.
- **Replicat:** reads the trail and applies changes to the target database.
- **Checkpoint:** records the processed position so processes can resume after restart.

```text
       Source Oracle Database
       +----------------------+
       | Tables / Transactions|
       | Online & Archive Redo|
       +----------+-----------+
                  |
                  v
              EXTRACT
                  |
                  v
            Local Trail
                  |
                  v
           Data Pump (optional)
                  |
              Network
                  |
                  v
            Remote Trail
                  |
                  v
              REPLICAT
                  |
                  v
       Target Database / Consumer
```

A Data Pump process is commonly used to decouple redo reading from network transmission. If the network or target is temporarily unavailable, the primary Extract can keep writing to the local trail, provided trail storage has sufficient space and processes are configured appropriately.

### 5.1. Extract

Extract captures changes from the source. For Oracle, common modes are Integrated Extract and Classic Extract, depending on version, topology, and supportability.

Integrated Extract works with the database log mining server to read redo and reconstruct logical changes. Integrated capture is recommended by Oracle for many modern Oracle deployments, though you must still verify the compatibility matrix, database version, and supported object/operation types.

Classic Extract handles redo capture itself in classic mode. It still appears in legacy environments or certain supported topologies. Never choose a mode out of habit; base the decision on versions, required features, and corresponding GoldenGate deployment guidelines.

Extract can filter tables/schemas and choose columns or operations to capture via parameter files. Conceptual example:

```text
EXTRACT ext_orders
USERIDALIAS gg_src
EXTTRAIL ./dirdat/ea
TABLE app.orders;
```

This is an illustrative configuration sample for Classic architecture; authentication syntax, credential store, trail paths, and parameters must be adapted to your version/deployment. Never copy directly into production without verifying security settings and source requirements.

### 5.2. Trail Files

A trail is GoldenGate's internal file format containing logical change records. Trails decouple capture from transport and apply while supporting checkpoint-based restart/recovery.

A trail can contain:

- Metadata about source tables and record formats.
- Operation types such as insert, update, delete.
- Column values required per logging/configuration.
- Transaction boundaries and ordering info.
- Timestamps/SCNs or related positioning details.

Trails are not CSVs or SQL scripts. Never edit trail files with a text editor. Use GoldenGate tools like `logdump` to inspect trails per supported procedures.

Trail files require retention management. Deleting trails still needed by Extract/Data Pump/Replicat can break continuity. Trail purging must rely on GoldenGate checkpoints and purge policies.

### 5.3. Data Pump Process

In Classic architecture, a Data Pump is an Extract process that reads a local trail and transmits records to a remote trail. It prevents capture Extract from depending directly on network/target health.

Conceptual parameter example:

```text
EXTRACT pump_orders
PASSTHRU
RMTHOST target-host, MGRPORT 7809
RMTTRAIL ./dirdat/rt
TABLE app.orders;
```

`PASSTHRU` can be used in some configurations to pass records without mapping/transforming at the pump. Actual parameters depend on trail format, credentials, and version.

### 5.4. Replicat

Replicat reads the trail at the target and applies changes. Common modes include Classic Replicat, Coordinated Replicat, and Integrated Replicat. Integrated Replicat uses Oracle Database apply servers to apply transactions and can leverage parallelism/commit dependencies where supported.

Conceptual parameter example:

```text
REPLICAT rep_orders
USERIDALIAS gg_tgt
MAP app.orders, TARGET dw.orders;
```

In production environments, configure mappings, column conversions, error handling, checkpoint tables, and appropriate apply options. Integrated Replicat is often considered for modern Oracle targets; specific choices depend on version and transaction/DDL requirements.

## 6. GoldenGate Microservices Architecture

GoldenGate now offers Microservices Architecture alongside Classic architecture. Service names and interfaces may vary by release, but the main roles include:

| Component | General Role |
|---|---|
| Service Manager | Manages deployments and services in the Microservices environment |
| Administration Server | Creates, configures, and manages Extract/Replicat and related processes |
| Distribution Server | Distributes trails/data from one deployment to another |
| Receiver Server | Receives trails/data from Distribution Server |
| Performance Metrics Server | Provides metrics and monitoring data per deployment |

In Microservices, administration is usually done via REST APIs and browser UI, while capture/apply processes still perform their corresponding logical roles. Distinguish deployment architecture from data flow: Extract captures, trails store, Distribution/Receiver forward, and Replicat applies.

Do not arbitrarily mix Classic architecture commands and parameters with Microservices operations. Follow documentation for your exact release and deployment mode.

## 7. Data Flow from Source to Target

A basic GoldenGate pipeline consists of these steps:

1. A transaction executes DML on the source.
2. Oracle writes necessary redo to online redo logs.
3. Extract reads redo and identifies changes for configured tables.
4. Extract constructs logical change records and writes them to the local trail.
5. Data Pump/Distribution Server ships trails over the network if an intermediate hop is configured.
6. Receiver/remote trail receives records at the target.
7. Replicat reads the trail, maps source objects to target objects, and applies changes.
8. Checkpoints update the processed position for safe restarts.

Transaction boundaries and commit ordering must be preserved per replication configuration. Replicat does not blindly run an independent SQL statement per row without regard for transactions. GoldenGate includes transaction handling, checkpointing, and apply dependency mechanisms to maintain consistency within supported topologies.

### 7.1. Transaction-Aware Capture

A single source transaction may modify many rows across multiple tables. CDC must preserve the relationship among changes belonging to the same transaction and apply them in a manner that upholds the designed consistency model.

Example order-creation transaction:

```sql
INSERT INTO orders(order_id, customer_id, order_status)
VALUES (1001, 501, 'NEW');

INSERT INTO order_items(order_id, product_id, quantity)
VALUES (1001, 9001, 2);

COMMIT;
```

If downstream requires consistency between `ORDERS` and `ORDER_ITEMS`, capture/apply must preserve transaction boundaries and correct mappings. If downstream receives individual row events over a broker, consumers must either group by transaction or accept eventual consistency under the data contract.

### 7.2. Checkpoints and Restart

Checkpoints record how far a process has progressed in logs/trails or target apply. Upon process restart, GoldenGate uses checkpoints to resume from the appropriate point rather than starting from scratch.

Checkpoints do not replace trail or archive log backups. If a needed file is deleted, the checkpoint may point to a position the process wants to read whose data is gone. Therefore, retention must cover expected lag, downtime, recovery, and incident response windows.

### 7.3. Transaction Ordering and Parallel Apply

Replicat can apply in parallel to boost throughput. Parallel apply must respect inter-transaction dependencies so consistency is not broken. Independent transactions can apply concurrently; conflicting or dependent transactions must be ordered appropriately.

Increasing parallelism does not always increase throughput. The target may be bottlenecked by index contention, foreign keys, triggers, redo generation, CPU, I/O, or long transactions forming dependency chains.

## 8. Configuring Source and Target for GoldenGate

A GoldenGate deployment requires preparing databases, privileges, logging, and connectivity on both source and target.

### 8.1. Preparing the Source

Typical steps include:

- Verify database version and GoldenGate release compatibility.
- Enable `ARCHIVELOG` if capture mode/topology requires archived redo.
- Configure appropriate supplemental logging.
- Ensure redo/archive logs are retained long enough.
- Grant capture privileges to the GoldenGate user using Oracle-supplied scripts/grants for your release.
- Identify schemas/tables to capture and operations to support.
- Account for Data Guard, RAC, CDB/PDB, or TDE if present in the architecture.

Do not invent a fixed privilege list across all versions. Oracle GoldenGate provides release- and mode-specific grant scripts/procedures. Run them with an approved admin account and grant only required privileges.

### 8.2. Preparing the Target

The target needs:

- Compatible target schemas and tables, or well-defined mappings.
- GoldenGate user with apply privileges on target objects.
- Checkpoint table if required by mode/deployment.
- Rules for handling duplicates, constraints, and triggers.
- Disk space for trails, reports, and discard files.
- Transaction and error-handling policies.

If the target already holds data before CDC begins, synchronize initial load and CDC using a consistent SCN or instantiation mechanism.

### 8.3. Process Management Example in Classic Architecture

In Classic deployments, `GGSCI` is commonly used to manage processes:

```text
GGSCI> INFO ALL
GGSCI> INFO EXTRACT ext_orders, DETAIL
GGSCI> INFO REPLICAT rep_orders, DETAIL
GGSCI> LAG EXTRACT ext_orders
GGSCI> LAG REPLICAT rep_orders
```

Command names and capabilities may vary by release/deployment. In Microservices, administration typically goes through the Administration Server/REST API. Never run Classic commands on an unsupported deployment.

## 9. Initial Load and Continuous Change Sync

When the target is empty, CDC cannot simply apply new changes while skipping existing state. An initial load is needed to establish the baseline, followed by applying changes that occurred during the load.

### 9.1. Consistency Between Initial Load and CDC

Suppose copying a table starts at 10:00 and finishes at 10:30. During that window, the source continues receiving transactions. If you merely copy the table and start capturing at 10:30, changes between 10:00 and 10:30 are lost. If you capture from before 10:00 without coordination, some changes may apply redundantly on top of snapshot data.

The solution is establishing a synchronization point, typically an SCN or supported instantiation mechanism:

1. Establish consistency point `S` on the source.
2. Initial load reads a data snapshot as of `S`.
3. Extract captures changes starting from `S` or the corresponding position.
4. Load the baseline into the target.
5. Replicat applies changes after `S` in order.

In real deployments, follow the exact instantiation procedure for your GoldenGate version, database version, and topology. Never pick an arbitrary SCN by querying `CURRENT_SCN` casually unless snapshot and capture start points are guaranteed aligned.

### 9.2. Initial Load Methods

Several methods apply depending on scale and downtime requirements:

- SQL-based load via `INSERT ... SELECT` or database links.
- Data Pump export/import to transfer the baseline.
- GoldenGate initial load processes.
- Backup/restore or storage-level copies in certain migration architectures.

Initial loads must be reconciled by row counts, keys, aggregates/checksums, and related tables. Only after the baseline completes should Replicat resume applying trails from the defined starting point.

### 9.3. Re-Synchronizing After Data Loss or Target Drift

If the target drifts or misses data, determine the scope and point of divergence. You can reload a single table/partition or re-instantiate. Never delete trails or reset checkpoints arbitrarily, as that can lose unapplied changes or cause duplicate applies.

## 10. Mapping, Filtering, and Transformation

GoldenGate can map source tables to target tables and apply transformations. Example:

```text
MAP app.orders, TARGET dw.fact_orders;
MAP app.customers, TARGET dw.dim_customers;
```

Mapping lets source and target have different schema/table names. Column mapping can be configured when column names or types differ:

```text
MAP app.orders, TARGET dw.fact_orders,
    COLMAP (
        order_key = order_id,
        customer_key = customer_id,
        status_code = order_status
    );
```

This is a conceptual parameter file example. Verify exact syntax against your GoldenGate release, target type, and mapping rules.

### 10.1. Filtering

You can capture only selected tables or replicate only rows matching a condition—for example, shipping orders for a specific region or status. Filtering reduces network transfer and storage, but requires considering how row conditions evolve over time.

If a filter excludes a row upon insert and a later update makes it satisfy the filter, the pipeline needs logic to realize the row must now be inserted into the target. Conversely, if an existing target row is updated so it no longer satisfies the filter, handle delete/ignore per chosen semantics.

### 10.2. Transformation

GoldenGate supports mapping/conversion features depending on release, but avoid embedding heavy business logic inside capture/apply processes. Heavy transformations increase lag and complicate testing. For complex rules, land raw changes into a staging/stream processor and transform downstream.

### 10.3. DDL Replication

GoldenGate can support capturing/replicating certain DDL depending on database, version, object type, and configuration. DDL replication requires strict control because source and target schemas may intentionally diverge. Do not blindly enable all DDL for all schemas if the target is a transformed reporting model.

## 11. Ensuring Consistency and Handling Conflicts

GoldenGate is typically used for asynchronous logical replication. Source transactions commit before changes apply at the target. Therefore, the target can lag behind the source for a period of time.

### 11.1. Eventual Consistency

In an asynchronous model, when the pipeline operates normally with no errors/backlog, the target converges toward the state reflected by captured and applied changes. At any given instant, however, the target may not yet show a transaction just committed at the source.

Applications reading the target must understand this latency. If a user creates an order on the source and immediately queries a reporting replica, the order may not appear yet. Options include:

- Read back from the source for workflows requiring read-your-writes.
- Wait until the target reaches the required checkpoint/lag.
- Pass a transaction token/commit position so consumers know when data has arrived.
- Accept eventual consistency if business logic permits.

### 11.2. Transactional Consistency

GoldenGate can preserve transaction grouping and commit order within the pipeline per configuration. Yet if downstream splits each row into an independent event processed in parallel, consumers can observe partial states unless grouped by transaction.

Explicitly define the consistency contract:

- Must all changes of a source transaction apply together?
- Must global commit order be preserved, or only per key/table order?
- Is parallel apply of independent transactions allowed?
- Do consumers need transaction IDs/commit timestamps/SCNs?

### 11.3. Conflicts in Multi-Source Writes

A unidirectional source-to-target topology is far simpler than active-active replication. When multiple sources can write to the same logical row, conflicts arise:

- Two sites update the same row concurrently.
- One site deletes while another updates.
- Duplicate unique keys are generated.
- Transactions arrive at the target in a different order than business logic expects.

GoldenGate provides conflict detection/resolution mechanisms for supported topologies and configurations, yet cannot deduce correct business rules on its own. Design key ownership, timestamps/versions, site priorities, or explicit merge rules. Avoid multi-master unless the application has clear conflict-resolution rules.

## 12. Monitoring Lag and Operating GoldenGate

CDC is only useful if you know whether the pipeline is keeping up or falling behind. Monitor capture, transport, and apply together.

### 12.1. Types of Lag

| Component | Question |
|---|---|
| Extract lag | How far behind source change time is the capture process? |
| Pump/Distribution lag | How long are trails waiting to be transmitted? |
| Replicat lag | How far behind source commit is target apply? |
| End-to-end latency | How long from source commit until data is readable at target? |

Lag is not just a single number. Inspect throughput, backlog/trail size, large transactions, process status, and last successful apply timestamp.

### 12.2. Monitoring Commands and Interfaces

In Classic architecture, `GGSCI` provides commands such as:

```text
GGSCI> INFO ALL
GGSCI> INFO EXTRACT ext_orders, DETAIL
GGSCI> INFO REPLICAT rep_orders, DETAIL
GGSCI> LAG EXTRACT ext_orders
GGSCI> LAG REPLICAT rep_orders
GGSCI> STATS EXTRACT ext_orders, TOTAL
GGSCI> STATS REPLICAT rep_orders, TOTAL
```

In Microservices, check process status, lag, throughput, and reports via Administration Server/Performance Metrics Server or REST APIs depending on release. Never rely on a single command; alert when processes abend, trail storage grows rapidly, or lag breaches SLA thresholds.

### 12.3. Checkpoints and Heartbeats

Checkpoints show how far a process has captured or applied. Some Replicat configurations use a checkpoint table in the target database. Heartbeat tables record timestamps or positions of change batches to measure end-to-end latency and detect stalled pipelines.

Heartbeats must be properly configured and maintained. If clocks between source and target drift out of sync, timestamp-based measurements can mislead. Use SCN/commit positions or GoldenGate-provided metrics where appropriate.

### 12.4. Trail and Archive Log Capacity

When the target stops or the network drops, trail backlogs grow. Without sufficient disk space, Extract or pumps can halt. Source archive logs must also be retained long enough for Extract to resume after downtime.

Capacity planning must account for:

- Peak redo generation rate.
- Proportion of redo belonging to captured tables.
- Maximum duration the target may be down.
- Time needed to catch up after recovery.
- Number of trail copies/routes and retention.
- Archive log capacity and backup/purge policies.

Never manually delete trails or archive logs just to free disk space. Use purge/checkpoint mechanisms and verify which processes still need those files.

## 13. Error Handling and Pipeline Recovery

Replicat can fail when a target constraint rejects a row, mapping mismatches types, a target object is missing, or data was already applied earlier. Extract can fail due to missing logs, insufficient privileges, or unsupported operations. Each error type requires a different response.

### 13.1. Discard Files and Error Handling

Discard files record unapplied records per configuration. Report files and process logs supply error details. Never configure processes to ignore all errors just to stay running; doing so silently leaves the target missing data without anyone noticing.

If a transaction must be skipped, document transaction identity, reason, affected data scope, and reconciliation plan. Skipping is an operational decision that affects consistency.

### 13.2. Process Restarts

When a process stops, check reports, error codes, checkpoints, trail files, and database health before restarting. If it was a transient error, restarting from checkpoint can resume cleanly. If trails are missing or the target was manually edited, assess potential duplicates or gaps before restarting.

### 13.3. Idempotency and Duplicate Handling

CDC pipelines may need to retry after network or process failures. Design consumers to be idempotent whenever possible: reprocessing the same change event should not create unintended side effects.

For database targets, primary keys/unique constraints and checkpointing govern apply. For event consumers, store processed event IDs/transaction keys or upsert by business key. Never rely on assuming "every event arrives exactly once" if transport or consumers can retry.

## 14. What Is Oracle Data Guard?

Oracle Data Guard maintains one or more standby databases to protect a primary database. The primary ships redo to the standby; the standby receives and applies redo to stay closely synchronized with the primary.

Data Guard's primary goals are high availability, data protection, and disaster recovery. If the primary suffers an outage, a standby can take over via failover. For planned maintenance, switchover swaps primary/standby roles cleanly following procedure.

### 14.1. Primary and Standby

```text
           Primary Database
                  |
              Redo Transport
                  |
                  v
           Standby Database
                  |
              Redo Apply
                  |
                  v
        Database close to Primary
```

A standby can be a physical standby or a logical standby, depending on configuration and goals. Active Data Guard is an additional option/capability enabling certain read-only workloads on a physical standby, subject to corresponding licensing terms.

### 14.2. Physical Standby

A physical standby maintains a block-for-block physical copy of the primary. Redo is applied via Redo Apply so the standby mirrors primary changes. Physical standby is commonly preferred for DR because database structures remain identical to the primary.

### 14.3. Logical Standby

A logical standby uses SQL Apply to transform redo into logical SQL changes. It can be opened for certain supported read/write operations and has specific object/data type limitations. A logical standby is not equivalent to GoldenGate; it is a standby database type within Data Guard.

### 14.4. Redo Transport and Apply

The primary ships redo to standbys using transport services. Standbys receive redo into standby redo logs or archive logs and apply it according to configured mode. You can choose synchronous/asynchronous transport and protection modes aligned with RPO targets, latency, and distance.

## 15. How Do GoldenGate and Data Guard Differ?

Both technologies can leverage redo and ship changes, yet they solve different problems.

| Criterion | Oracle GoldenGate | Oracle Data Guard |
|---|---|---|
| Primary goal | Logical replication, CDC, and data distribution | High availability, data protection, and disaster recovery |
| Sync unit | Logical changes such as object-level insert/update/delete | Redo and standby database state |
| Target | Can be a different database, schema, or supported platform | Standby database of the primary |
| Schema mapping | Can map schema/table/column names and transform | Physical standby keeps exact physical structure; logical standby has SQL Apply rules |
| Filtering | Can select tables, operations, and rows per configuration | Not a general CDC subset distribution tool |
| Heterogeneous replication | Can support diverse platforms per release | Primarily protects Oracle Databases in Data Guard configurations |
| Latency | Usually asynchronous, depends on capture/transport/apply | Supports synchronous/asynchronous redo transport and apply lag |
| Database role failover | Does not replace Data Guard role transitions | Supports switchover/failover between primary and standby |
| Conflict handling | Requires design for multi-source/active-active topologies | Not a multi-master conflict resolution model |
| Use cases | DWH, integration, migration, reporting copy, CDC feeds | DR sites, HA databases, data protection |

### 15.1. Technology Selection Examples

**Scenario A: Need a standby database to fail over to if the primary site goes down.** Data Guard is usually the right choice because the goal is maintaining a standby database ready to assume the primary role.

**Scenario B: Need to move selected tables from Oracle to another data platform for analytics.** GoldenGate fits better because it captures object-level changes and streams logical records to supported targets.

**Scenario C: Need a database migration with minimal downtime.** GoldenGate can continuously sync changes after an initial load, keeping target caught up with source until cutover. Plan data verification and write freeze at cutover.

**Scenario D: Need both HA/DR for an OLTP database and a near-real-time data warehouse.** Use Data Guard for standby/DR and GoldenGate to feed changes to the warehouse. Both pipelines must be designed with appropriate resources, logging, networking, and source endpoints.

## 16. Can GoldenGate Be Combined with Data Guard?

Yes. A common architecture features an Oracle RAC primary database at the main site, a Data Guard standby at a DR site, and GoldenGate capturing/replicating changes to a reporting or warehouse platform.

```text
                    OLTP Application
                          |
                          v
                 Primary Oracle RAC
                          |
               +----------+----------+
               |                     |
               v                     v
         Data Guard redo       GoldenGate Extract
               |                     |
               v                     v
        Standby Database          Trail / Pump
                                     |
                                     v
                              GoldenGate Replicat
                                     |
                                     v
                             Data Warehouse
```

Data Guard protects the database via standby. GoldenGate delivers logical changes to the warehouse. If the source uses RAC or undergoes a Data Guard role transition, design where GoldenGate capture runs, how role transitions are handled, and how to prevent duplicate capture or gaps when primary switches to another standby.

Never assume GoldenGate automatically fails over capture to a Data Guard standby in every configuration. Follow Oracle-supported architectures and failover/switchover procedures for your deployed version.

## 17. GoldenGate in RAC and Data Guard Environments

GoldenGate can be deployed with Oracle RAC and Data Guard, but requires understanding redo threads, archive logs, and instance topology.

### 17.1. RAC Sources

RAC has multiple redo threads, with each instance writing redo to its own thread. Extract must read sufficient redo from all relevant threads to capture database changes. Access to online/archive logs and shared storage must match the RAC architecture.

If an instance fails, ensure Extract can continue from remaining logs and required archive logs. Monitoring should track capture lag and process health across the entire cluster.

### 17.2. Data Guard Sources

If GoldenGate captures from a primary database that has a Data Guard standby, define the capture mode and redo read location. Some configurations allow capturing from a standby to offload the primary, but support depends on GoldenGate/database releases, database role, standby type, and Oracle-published requirements.

Never move Extract to a standby arbitrarily just because the standby has redo. Verify supplemental logging requirements, redo access, database role, licensing, and release-specific restrictions.

### 17.3. Role Transitions

During a Data Guard switchover/failover, database roles change. GoldenGate must be configured to recognize the new source, recover capture position, and avoid unintended lost or duplicated changes. Runbooks must include:

- Identifying which database is primary after the transition.
- Checking where Extract is capturing and its checkpoint state.
- Verifying archive/redo availability.
- Starting or relocating processes per the supported architecture.
- Checking trail continuity and Replicat lag.
- Reconciling data once the pipeline resumes.

## 18. CDC and Near-Zero-Downtime Migrations

GoldenGate is often used to minimize downtime during database migrations or platform upgrades.

A general migration flow:

1. Prepare target schemas, privileges, and GoldenGate.
2. Enable supplemental logging and start source capture at a consistent point.
3. Perform the initial load from source to target.
4. Replicat applies changes generated during the initial load.
5. Monitor lag until the target catches up.
6. Verify row counts, checksums, constraints, and business data.
7. Choose the cutover window, pause writes on source or follow final sync procedure.
8. Wait for Replicat to drain remaining backlog and confirm target consistency.
9. Switch applications to the target.
10. Monitor post-cutover and retain a rollback plan for the agreed window.

Low downtime does not mean zero downtime. A brief period is still needed to halt writes or transfer write ownership so two sources do not accept uncoordinated writes simultaneously.

### 18.1. Data Verification Before Cutover

Never look solely at zero lag and conclude the target is completely accurate. Verify:

- Row counts per table and partition.
- Aggregates by business key.
- Checksums/hashes by chunk or key range.
- Missing/duplicate primary keys.
- Foreign keys and data relationships.
- Latest transactions on the source.
- Sequences, identities, database links, jobs, triggers, and related dependencies.

### 18.2. Cutover and Rollback

Cutover must clearly specify when source stops accepting writes, when target starts accepting writes, and how stale connections are handled. Once the target accepts new writes, rolling back to source is no longer simple unless target changes are replicated back. Define a rollback window and reverse-replication strategy if required.

## 19. GoldenGate Security and Governance

GoldenGate holds privileges to read redo, access source objects, write trails, and apply target data. Consequently, GoldenGate user credentials and privileges must be protected like critical database service accounts.

Principles:

- Use a dedicated GoldenGate user; never use `SYS` or application schemas for routine operations.
- Grant privileges using scripts/procedures for your exact GoldenGate release and capture/apply mode.
- Store credentials in supported credential stores/secret mechanisms; avoid plaintext passwords in parameter files.
- Protect trail files, reports, logs, and discard files, as they can contain sensitive data.
- Encrypt network connections/transport where required by network security policies.
- Restrict OS permissions on GoldenGate directories and trail files.
- Separate roles for operators, administrators, and metrics viewers.
- Audit parameter changes, process start/stop actions, skipped transactions, and purge operations.

## 20. Risks and Limitations to Understand

CDC and GoldenGate do not automatically solve every synchronization challenge:

- **Unsupported objects/operations:** certain data types, objects, DDL, or special operations have release-specific limits.
- **Large transactions:** huge transactions can spike memory usage, trail backlogs, and apply latency.
- **LOBs:** verify configuration and capture/apply limitations for specific LOB types and operations.
- **DDL drift:** mismatched source/target schemas can break apply.
- **Keyless tables:** lacking unique keys makes row identification harder and increases supplemental logging.
- **Target contention:** parallel apply transactions can contend on indexes/constraints.
- **Long-running transactions:** uncommitted changes may not emit to target even though redo is already generated.
- **Trail/archive retention:** missing logs can prevent capture from resuming from checkpoint.
- **Network outages:** backlogs grow and target can lag long after network recovery.
- **Duplicates/replays:** retries or re-instantiation require idempotent procedures and accurate checkpoints.

Before deploying, build a compatibility matrix covering database versions, GoldenGate version, platforms, character sets, encryption, topology, and data types. Run a proof-of-concept with realistic workloads instead of relying on toy examples.

## 21. Workflow for Designing a CDC Pipeline

An implementation workflow can follow these steps:

1. **Define the goal:** is the target for DR, reporting, integration, migration, or an event feed?
2. **Choose semantics:** is logical replication, physical standby, or simple snapshot/polling required?
3. **Assess source and target:** database versions, schemas, data types, keys, volumes, and network.
4. **Select capture mode:** log-based, trigger/polling, or GoldenGate integrated/classic per support.
5. **Prepare logging:** `ARCHIVELOG`, supplemental logging, archive retention, and capture privileges.
6. **Design initial load:** choose SCN/instantiation point and baseline method.
7. **Design mapping:** table/column mappings, filters, transforms, and DDL policies.
8. **Design apply:** integrated/classic/coordinated Replicat, checkpoints, and transaction semantics.
9. **Design error and retry handling:** discards, error handling, skip policy, idempotency, and reconciliation.
10. **Design monitoring:** lag, throughput, process status, trail/archive capacity, and alerts.
11. **Test failures:** source restarts, network outages, target outages, process abends, and role transitions.
12. **Test cutover/recovery:** verify data and fallback procedures.

## 22. Hands-On Lab: Replicating ORDERS Table to a Reporting Database

Suppose `APP.ORDERS` on source must be replicated to `REPORTING.ORDERS` on target for reporting. Both source and target are Oracle Databases; the deployment uses GoldenGate Classic to illustrate process flow.

### Step 1: Confirm the Table Has a Primary Key

```sql
SELECT constraint_name,
       constraint_type,
       status
FROM user_constraints
WHERE table_name = 'ORDERS';
```

Verify `ORDER_ID` has an appropriate primary key or unique key. Without a key, design key/supplemental logging before capturing.

### Step 2: Enable Required Supplemental Logging

```sql
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA;
ALTER TABLE app.orders
ADD SUPPLEMENTAL LOG DATA (PRIMARY KEY) COLUMNS;
```

Run commands with an authorized account and confirm alignment with capture settings.

### Step 3: Create the Target Table

The target needs a compatible structure or defined mappings. Create the baseline using Data Pump/SQL or your chosen initial load method.

### Step 4: Configure Extract

Illustrative parameters:

```text
EXTRACT ext_orders
USERIDALIAS gg_src
EXTTRAIL ./dirdat/ea
TABLE app.orders;
```

### Step 5: Configure Data Pump

```text
EXTRACT pump_orders
PASSTHRU
RMTHOST target-host, MGRPORT 7809
RMTTRAIL ./dirdat/rt
TABLE app.orders;
```

### Step 6: Configure Replicat

```text
REPLICAT rep_orders
USERIDALIAS gg_tgt
MAP app.orders, TARGET reporting.orders;
```

These parameter snippets are skeletons to illustrate mapping. Add credentials, checkpointing, error handling, trail format, process groups, and security settings per your real deployment.

### Step 7: Initial Load and Start CDC

Pick a consistent SCN/instantiation point. Load the baseline into `REPORTING.ORDERS`, then start Replicat from the matching trail position. Never start apply from an arbitrary position.

### Step 8: Verify Results

Compare row counts and aggregates:

```sql
SELECT COUNT(*) AS row_count,
       SUM(total_amount) AS total_amount
FROM app.orders;
```

```sql
SELECT COUNT(*) AS row_count,
       SUM(total_amount) AS total_amount
FROM reporting.orders;
```

These two queries are only a basic reconciliation check. If the source continues receiving transactions during comparison, numbers may differ due to replication lag. Use a consistent snapshot point or pause writes for an exact comparison.

### Step 9: Monitor Lag and Processes

```text
GGSCI> INFO ALL
GGSCI> LAG EXTRACT ext_orders
GGSCI> LAG REPLICAT rep_orders
GGSCI> STATS REPLICAT rep_orders, TOTAL
```

Configure alerts for process abends, lag breaching SLA, trail disk filling up, and insufficient archive log retention.

## 23. Checklist for Choosing Between GoldenGate, Data Guard, and Simple CDC

| Question | Typical Choice |
|---|---|
| Need a standby database to fail over to if primary site fails? | Data Guard |
| Need to replicate a subset of tables to another system? | GoldenGate or suitable CDC platform |
| Need to move Oracle data to a non-Oracle platform? | GoldenGate if target is supported |
| Need migration with a short write-freeze window? | GoldenGate combining initial load and cutover |
| Only need to sync one small table hourly? | Polling may be simple enough |
| Need local change auditing in the same transaction? | Triggers/change table may fit |
| Need site-loss protection plus warehouse data feed? | Data Guard combined with GoldenGate |
| Need multi-master with multiple sites writing concurrently? | Only choose with explicit conflict/ownership design and supported topology |

## 24. Misconceptions to Avoid

| Misconception | Accurate Understanding |
|---|---|
| CDC is just polling by `UPDATED_AT` | CDC can be log-based, trigger-based, or polling; log-based capture also captures deletes and transaction metadata |
| GoldenGate is Data Guard | GoldenGate is logical replication/CDC; Data Guard maintains standby databases for HA/DR |
| Data Guard is a tool for replicating a few selected tables | Data Guard protects databases at the standby level, not general table-level subset distribution |
| GoldenGate only copies whole tables | GoldenGate continuously captures changes and filters/maps per configuration |
| Trail files are CSVs or SQL scripts | Trails are GoldenGate's internal format requiring appropriate inspection tools |
| GoldenGate Data Pump is `expdp` | GoldenGate's Data Pump process ships trails; Oracle Data Pump is a separate export/import utility |
| Target is always in sync immediately after source commit | Asynchronous pipelines have replication lag; define consistency SLAs |
| Enabling supplemental logging has zero cost | Redo increases; choose the appropriate logging level |
| Replicat errors can be bypassed by skipping all transactions | Skipping can drift the target; log and reconcile |
| Zero lag means the target is fully verified | Lag is a time/position metric, not a substitute for data reconciliation |
| Multi-master resolves conflicts automatically | Requires explicit ownership and conflict-resolution rules |
| GoldenGate replaces backups | GoldenGate does not replace backup/restore and DR strategies |

Change Data Capture lets systems ship only necessary changes rather than continuously re-reading entire datasets. Oracle GoldenGate provides a logical replication pipeline with capture, trails, transport, and apply; redo and supplemental logging form the foundation for capturing from Oracle Database. Oracle Data Guard serves a different goal: maintaining standby databases to protect data and fail over roles during outages. Choosing the right technology requires clearly defining goals, consistency, latency, topology, compatibility, and operational procedures; many architectures combine GoldenGate with Data Guard rather than treating them as mutually exclusive alternatives.
