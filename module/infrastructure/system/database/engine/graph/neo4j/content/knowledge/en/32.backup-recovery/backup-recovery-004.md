# Online Backup When Supported by Your Neo4j Edition or Service

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **online backup**, **offline dump**, managed service snapshots, cluster replication, and disaster recovery.
- Identify which **editions and deployment models** support `neo4j-admin database backup` versus which environments must use provider-managed snapshots.
- Configure the backup service, network address, port, TLS, read/write permissions, and resources for **self-managed Neo4j Enterprise**.
- Execute and explain **FULL**, **DIFF**, **AUTO**, backup chains, metadata, and version-conditional options.
- Design backup schedules aligned with **RPO** and **RTO** while avoiding broken chains, missing transaction logs, and insufficient temporary disk space.
- Inspect backup metadata, drill **restoring into an isolated environment**, run consistency checks, and reconcile business data.
- Secure backups containing sensitive information, and design monitoring, alerting, and recovery workflows when the graph system experiences an incident.

This lesson belongs to the **Backup and Recovery** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. Neo4j stores nodes, relationships, properties, indexes, and constraints to power Cypher queries over connections and paths. Java Driver or Spring Data Neo4j applications depend on valid graph state to perform read/write transactions. Backups are therefore not merely "saving a file": they must allow re-establishing a **consistent database state** that meets the system's maximum data-loss and recovery-time targets.

> **Version scope:** Commands in this lesson are based on the Neo4j Operations Manual for Neo4j 5.x and corresponding 2025.x–2026.x releases. **CLI options, defaults, cloud storage capabilities, and differential chain rules change across versions.** Before running in production, check `neo4j-admin ... --help` and documentation for your **exact installed version**. Commands that modify data or restore are explicitly meant for **isolated/lab environments**, not direct production overwrites.

## 1. What Is Online Backup and What Does It Solve?

**Online backup** collects recovery data **while the source database remains running** and accepting transactions. In **self-managed Neo4j Enterprise**, `neo4j-admin database backup` connects to a backup service on the source server, backing up the store and required transaction data to create recoverable artifacts.

~~~mermaid
flowchart LR
    A["Java / Spring application"] -->|Cypher READ/WRITE| N[("Neo4j Enterprise<br/>online")]
    N -->|Backup protocol| C["Backup client<br/>neo4j-admin"]
    C -->|FULL / DIFF| B[("Backup repository<br/>.backup artifacts")]
    B --> V["Inspect + consistency + restore drill"]
    V --> R[("Neo4j recovery environment")]
~~~

Key points to remember:

- The **source keeps running** during backup, yet backups still consume CPU, I/O, and network, and can increase query latency.
- A **backup artifact** is stored recovery data for one database plus accompanying metadata; it is not a `MATCH` query exported to CSV or JSON.
- You can take an initial **FULL** and subsequent **DIFF** backups to reduce transferred data.
- To restore to a valid state, the system requires a **complete backup chain** and the ability to apply the corresponding transactions.
- Having a successful backup **does not automatically guarantee** you have a restore runbook, access permissions to the backup, or an achievable RTO.

### Online Backup Does Not Equal HA/Replication

| Mechanism | Purpose | Does it replace backup? |
| --- | --- | --- |
| **Cluster replication** | Maintain availability when a member fails | **No**: accidental deletions or bad writes can replicate across members |
| **Online backup** | Retain recoverable data points in independent storage | Serves as a recovery data source, does not provide automatic failover |
| **Offline dump** | Create an archive file when the database is offline | Usable for migration/labs and scenarios permitting downtime |
| **Aura snapshot** | Service-managed backup per plan entitlements | Does not mean running `neo4j-admin` directly on Aura hosts |
| **CDC / event stream** | Synchronize committed data changes | Does not automatically replace consistent snapshots and restore procedures |

If a business transaction accidentally deletes all `PLACED` relationships, the cluster can replicate that exact erroneous change. An independent backup from before the incident provides a different layer of defense.

## 2. Support Conditions by Edition and Deployment Model

Do not infer from having the Neo4j Java Driver, admin login access, or a newer Neo4j version that the environment definitely supports the online backup command.

| Environment | Online backup `neo4j-admin database backup` | Recommended approach |
| --- | --- | --- |
| **Self-managed Neo4j Enterprise Edition** | **Yes**, when the backup service and network/resource permissions are configured properly | Use a backup client, FULL/DIFF/AUTO, scheduling, and restore drills |
| **Self-managed Neo4j Community Edition** | **No**, does not support this Enterprise online backup feature | Use `neo4j-admin database dump` for an **offline** database, or adopt a supported edition if live backups are required |
| **Neo4j Enterprise in Docker/Kubernetes** | **Yes**, if image/license, backup service, ports, volumes, and permissions are properly configured | Run backup tooling from a trusted client/job, never just copy an actively written volume |
| **AuraDB Free** | No scheduled user snapshot backups like paid tiers per current service table | Do not assume snapshot recovery is available; check plan policy and allowed export methods |
| **AuraDB Professional, Business Critical, Virtual Dedicated Cloud** | **Cannot run self-managed Enterprise commands directly** | Use **snapshot/backup/restore** provided by Aura per plan; frequency and retention vary |
| **AuraDS or other managed services** | Depends on product/plan and provided interfaces | Check snapshot policies and service-specific administrative operations |

According to current Aura documentation, for example, **AuraDB Professional** includes daily full snapshots; **Business Critical** includes daily full and hourly differential snapshots; and **Virtual Dedicated Cloud** policies depend on instance generation and plan. **Retention duration, on-demand/export rights, and restore scope** vary, and official service tables can change. Never write a "30-day retention" schedule assuming it applies universally across all Aura tiers.

References:

- [Neo4j — Back up an online database](https://neo4j.com/docs/operations-manual/current/backup-restore/online-backup/)
- [Neo4j — Backup modes](https://neo4j.com/docs/operations-manual/current/backup-restore/modes/)
- [Aura — Backup, export, restore and upload](https://neo4j.com/docs/aura/managing-instances/backup-restore-export/)

**Verify in place** if you have permission:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

Compare `versions` and `edition` against your installation and license. On Aura, visibility into these procedures may differ; verify the plan name in the service console and actual snapshot capabilities.

## 3. Defining RPO, RTO, and What Must Be Backed Up

Before deciding cron schedules and storage capacity, define:

- **RPO (Recovery Point Objective):** maximum acceptable data loss, typically measured as the time between the latest recoverable point and the incident.
- **RTO (Recovery Time Objective):** maximum allowed time until the service operates again at committed levels.
- **Backup scope:** a single database or the entire DBMS, including the `system` database, user-defined databases, and configurations/secrets/connectors needed to rebuild.
- **Failure scope:** node failure, volume failure, full-region outage, accidental deletion, ransomware, or business data corruption.
- **Restore target:** restoring a new database for reconciliation, replacing the existing database, or standing up an isolated recovery cluster.

Example illustrative contract:

| Capability | Example target | Architectural implication |
| --- | --- | --- |
| RPO | 15 minutes | Schedule DIFF/backup cadence frequently enough, with failure alerts |
| RTO | 2 hours | Need a recent FULL, manageable DIFF chain length, and ready restore target |
| Scope | `orders_graph` and `system` | Back up every required database/metadata, not just the default DB |
| Location | Survives total host loss | Artifacts must live **off the source host**, outside its failure domain |
| Correctness | All nodes, relationships, constraints, key queries | Validate after restore, not just by checking file existence |

The numbers above are training examples only. **Backing up every 15 minutes does not automatically guarantee an exact 15-minute RPO**: a failed job, missing logs, or slow upload can leave the latest recovery point older than expected.

### 3.1. One Application May Use Multiple Databases

For example, an application may use `customer_graph` and `order_graph` or multiple databases in one DBMS. Neo4j backups store **per-database artifacts**. If the backend updates two databases in separate transactions, backing them up at two different times **does not yield an atomic cross-database snapshot**.

Agree upfront on:

1. Which database is the authoritative source of truth?
2. Must **`system`** be backed up to preserve administrative and operational metadata?
3. Is there documentation to recreate users/roles/privileges, aliases, configurations, and secrets?
4. If two databases collaborate in one workflow, how will they be **reconciled** post-restore by business ID/version?

**Never assume a single database artifact holds all server configurations or state of systems outside Neo4j.**

## 4. FULL, DIFF, and Backup Chain Architecture

Neo4j Enterprise online backup produces these artifact types:

- **FULL:** contains the required store files of a database plus metadata.
- **DIFF:** contains transaction logs/deltas continuing from a suitable parent backup.
- **AUTO:** the tool chooses automatically; if no valid chain exists yet, it can create a FULL; when eligible, it runs a DIFF.

~~~mermaid
flowchart LR
    F["FULL #1<br/>base store"] --> D1["DIFF #2<br/>subsequent transactions"]
    D1 --> D2["DIFF #3"]
    D2 --> D3["DIFF #4"]
    D3 --> R["Restore to point #4"]
~~~

A **backup chain** depends on parent-child linkage across artifacts. If you delete an intermediate DIFF needed by later DIFFs, the chain can no longer restore to the desired point. Beyond the chain itself, artifacts also track **database ID**, transaction IDs, Neo4j version compatibility, and recovery state.

### 4.1. When a DIFF Cannot Run

A DIFF requires a valid parent and the required transaction logs. If necessary logs were pruned or the chain is incompatible, `AUTO` mode may need to take a new FULL. Never configure "DIFF forever" without monitoring failure reasons, chain continuity, and storage costs.

**Never copy a single `.backup` file out of a set and assume it is standalone.** A FULL can be self-contained once properly recovered; a DIFF is meaningful only alongside its related chain.

### 4.2. Version-Specific Behavior Milestones

| Version / option | Important note |
| --- | --- |
| **Neo4j 2025.04**: `--prefer-diff-as-parent` | Can prefer the latest DIFF as parent to maintain a chain per target; review retention rules carefully |
| **Neo4j 2025.09**: `--remote-address-resolution` | Helps select an eligible backup source server in a topology when available |
| **Neo4j 2025.11**: `--skip-recovery` and `--parallel-download` | Can shift backup/restore timing or enable parallel downloads; evaluate resource and support impacts |
| **Neo4j 2026.02** | First DIFF after a FULL is allowed to **overlap** with the prior FULL; makes FULL and DIFF schedules more independent |
| **Neo4j 2026.08**: `--skip-empty-diffs` | Can skip creating empty DIFF files under specified metadata selection conditions |
| **Neo4j 2026.09**: `--split-archive-part-size` | Can split large artifacts into multiple parts above a documented minimum; all parts must be kept to restore |

These options **do not exist in every release**. In addition, `--skip-recovery` can defer recovery work to restore time: shortening backup duration does **not automatically improve RTO**. See [Online backup](https://neo4j.com/docs/operations-manual/current/backup-restore/online-backup/) and [Aggregate backup chain](https://neo4j.com/docs/operations-manual/current/backup-restore/aggregate/).

## 5. Preparing Self-Managed Neo4j Enterprise

### 5.1. Pre-Run Requirements

- The Neo4j DBMS is running licensed **Enterprise** Edition and the target database is online.
- The backup client host has a **`neo4j-admin` compatible** with the source server.
- The exact physical database name is confirmed; do not mistakenly pass an **alias** instead of a physical database.
- The backup service is enabled, and the backup port is reachable **from the authorized backup client host**.
- Sufficient space exists at both **destination and temporary staging paths**, alongside adequate CPU, heap, page cache, I/O, and network.
- Operators have CLI execution and appropriate filesystem permissions; restrict who can read/copy artifacts.
- Secure backup storage, retention, encryption, and restore drills are defined.

Check the database list in an authorized environment:

~~~cypher
SHOW DATABASES
YIELD name, requestedStatus, currentStatus
RETURN name, requestedStatus, currentStatus
ORDER BY name;
~~~

Use **`orders_graph`** in subsequent examples only if it actually exists; substitute your system's database name.

### 5.2. Configuring the Backup Service

In self-managed Neo4j Enterprise, common settings include:

~~~properties
# neo4j.conf - illustrative example. Configure on the source server.
server.backup.enabled=true
server.backup.listen_address=127.0.0.1:6362
~~~

Per current operational docs, the backup service is **enabled by default** yet listens only on **loopback** `127.0.0.1:6362`. That works for local backups; backing up from a separate host requires binding to a **specific private network address** and opening the appropriate path, for example:

~~~properties
# Use only when the backup client sits on a controlled private network.
server.backup.enabled=true
server.backup.listen_address=10.0.10.12:6362
~~~

The address is illustrative and must match an actual interface. Config changes may require restarting/redeploying per version and server procedures. Never bind to `0.0.0.0` and expose port 6362 to the Internet: **it is a sensitive interface allowing database data extraction**. Enforce firewalls, private networking, service account controls, and TLS.

### 5.3. The Backup Port Is Not the Bolt Port

| Function | Common port | Used for |
| --- | ---: | --- |
| **Bolt** | 7687 | Java Driver, Spring Data Neo4j, Cypher queries |
| **HTTP** | 7474 | HTTP interface/Browser if enabled |
| **Backup protocol** | 6362 | `neo4j-admin database backup` on Enterprise |
| **Cluster traffic** | Topology/config dependent | Inter-cluster communication, requires private network policy |

`neo4j-admin database backup --from=...` uses the **backup endpoint**, not a `neo4j://...:7687` URI or Browser login credentials. **Seeing port 7687 reachable does not prove backup port 6362 is serving.**

### 5.4. Enabling TLS for Backups

Neo4j supports a dedicated SSL policy for backups, configured on both the server and the backup client. Conceptual flag skeleton:

~~~properties
# Skeleton for backup policy setup; NOT a complete TLS configuration.
dbms.ssl.policy.backup.enabled=true
dbms.ssl.policy.backup.client_auth=REQUIRE
~~~

For real use, configure **certificates, private keys, trust stores, CA chains, TLS protocol versions, and ciphers** consistently across server and client per Neo4j docs. Do not merely set those two flags and assume the connection is secure. Prefer trusted CA certificates and restrict the backup network. See [Online backup — SSL/TLS configuration](https://neo4j.com/docs/operations-manual/current/backup-restore/online-backup/).

## 6. Performing an Online FULL Backup

**Run only in a configured Enterprise test environment.** Assumptions:

- The machine running `neo4j-admin` is an authorized backup client able to reach `10.0.10.12:6362`.
- The source database is `orders_graph` and is online.
- Directory `/srv/neo4j-backups/orders` exists, has sufficient space, and is outside Neo4j's data directory.

~~~bash
# On the backup client; DO NOT run inside Cypher Browser.
neo4j-admin database backup \
  --from=10.0.10.12:6362 \
  --to-path=/srv/neo4j-backups/orders \
  --type=FULL \
  orders_graph
~~~

This creates a FULL artifact in the destination directory. Exact filenames usually contain the database name and a timestamp; **never hardcode guessed filenames when restoring**—read the generated artifact metadata instead.

You can set resource limits for the backup client as needed:

~~~bash
# Illustrative values, not universal recommendations.
export HEAP_SIZE=2G

neo4j-admin database backup \
  --from=10.0.10.12:6362 \
  --to-path=/srv/neo4j-backups/orders \
  --pagecache=4G \
  --type=FULL \
  orders_graph
~~~

`HEAP_SIZE` and `--pagecache` here configure resources **for the backup client process**, not Neo4j Server's heap/page cache. Size them based on available RAM, store size, and backup host load.

### 6.1. Why Use a Dedicated Backup Host?

A backup run consumes CPU for compression/recovery, disk I/O, and RAM. Running the backup client on a heavily loaded transactional node forces backups to compete with application `MATCH`, traversals, and `MERGE` writes. A dedicated backup host on a **trusted network** offloads much of that overhead, though the source server must still read and stream store data.

To minimize application impact, monitor **Java API p95/p99 latency**, CPU, page cache, disk, and network during backups. Schedule heavy runs during low-traffic windows when SLOs require it.

## 7. DIFF/AUTO Backups and Chain Management

After taking an initial FULL, you can use `AUTO`:

~~~bash
neo4j-admin database backup \
  --from=10.0.10.12:6362 \
  --to-path=/srv/neo4j-backups/orders \
  --type=AUTO \
  orders_graph
~~~

Or explicitly request DIFF when prerequisites are satisfied:

~~~bash
neo4j-admin database backup \
  --from=10.0.10.12:6362 \
  --to-path=/srv/neo4j-backups/orders \
  --type=DIFF \
  orders_graph
~~~

**Do not intentionally run an initial DIFF without a FULL**: a base backup chain is required. With `AUTO`, the tool can automatically create a FULL if no chain exists, yet actual mode transitions should be tracked via metadata, logs, and exit codes.

### 7.1. Example Backup Schedule

~~~text
Sunday 02:00:    FULL    orders_graph
Daily 02:00:     DIFF/AUTO depending on version capabilities and policy
Every 15 min:    DIFF/AUTO if RPO requires it
Daily:           inspect chain + alert on missing backups
Weekly:          restore drill in an isolated environment
~~~

This schedule illustrates **a learning scenario only**. Prior to **Neo4j 2026.02**, interleaving FULLs among DIFFs had different chain continuity constraints; **from 2026.02 onward**, the first DIFF is allowed to overlap a parent FULL. Designing independent FULL/DIFF schedules requires checking your version and `--prefer-diff-as-parent` behavior if available.

### 7.2. Risks of Long Chains

A chain of 1 FULL + 500 DIFFs saves bandwidth per backup run, yet restoring can take a long time to apply many deltas. To reduce RTO:

- Increase FULL frequency as capacity permits.
- **Aggregate** the backup chain into a recovered FULL artifact where supported by version/features.
- Measure actual restore duration on large datasets rather than extrapolating from artifact creation speed.
- Only delete older artifacts once certain they are **no longer referenced by any chain you intend to keep**.

## 8. Backing Up in a Cluster: Source Selection and Protecting Write Availability

In a Neo4j Enterprise cluster, multiple servers may host the same database with different roles or freshness at any moment. Backups can be taken from any eligible member and should be targeted considering topology, transaction IDs, and load impact.

### 8.1. Pattern for Specifying Multiple Backup Endpoints

~~~bash
neo4j-admin database backup \
  --from=10.0.10.21:6362,10.0.10.22:6362,10.0.10.23:6362 \
  --to-path=/srv/neo4j-backups/orders \
  --type=AUTO \
  orders_graph
~~~

This is an **example address list**. Never use those IPs outside a real matching network; in a production cluster, verify membership, backup listen addresses, firewalls, and database status on every member.

### 8.2. Evaluating Secondaries vs. Primaries

If your topology includes **secondary** members holding sufficiently fresh data, preferring backups from a secondary reduces contention on write-serving primaries. However:

- A secondary can **lag behind the writer**, making the recovery point older than required.
- A secondary with slow network/disk can cause backups to miss deadlines.
- If no secondary is available, an appropriate primary can be used per operational runbooks.
- When a cluster loses quorum or is degraded, do not add heavy backup load or auto-restart nodes simply because a backup job failed.

Monitor transaction IDs or replication/lag metrics supported by your Neo4j version to evaluate freshness. On versions supporting `--remote-address-resolution`, the DBMS can help select an appropriate backup source; **this option does not exist in older releases**.

### 8.3. A Database Alias Is Not a Physical Database

If a Java application connects via an alias to abstract the physical database name, online backup still requires the **real physical database**. Do not attempt to back up an alias as if it held its own store files; identify the underlying target database and also record alias definitions for recovery.

## 9. Storage Destinations, Cloud, and Temporary Space

Choosing where to store backups must account for **accessibility when the source fails**:

| Destination | Advantages | Risks to address |
| --- | --- | --- |
| Separate directory on backup client | Easy to run, inspect, and restore | If on the same host/volume/fault zone as source, backups can be lost together |
| Network storage | Decoupled from source host | Mount permissions, I/O speed, network failures, and ransomware |
| Object storage (S3/GCS/Azure) | Durable storage and lifecycle policies | IAM, encryption, versioning/retention, cost, and staging space |
| Multi-region/location | Survives large regional outages | Must verify replication and test restoring from the remote region |

In Neo4j versions supporting cloud storage URIs, `--to-path` can point to **S3, Google Cloud Storage, or Azure** using appropriate syntax and cloud permissions. However, **cloud backups still use local staging** to hold store/log data before packaging or uploading. Ensure `--temp-path` has sufficient space:

~~~bash
# Illustrative syntax on a release supporting S3 URIs.
neo4j-admin database backup \
  --from=10.0.10.12:6362 \
  --to-path=s3://approved-neo4j-backups/orders/ \
  --temp-path=/mnt/backup-staging \
  --type=FULL \
  orders_graph
~~~

`/mnt/backup-staging` must be an **appropriate empty/dedicated directory** writable by the backup client with ample free space; avoid defaulting to a small OS partition. Example bucket names do not represent real resources. Grant cloud accounts least-privilege role permissions—never embed access keys in command lines, shell history, or backup files.

### Multi-Part Artifacts

Starting with **Neo4j 2026.09** and `--split-archive-part-size`, large artifacts can be split into multiple files. These parts form a **single atomic unit**; losing `.backup.1` or moving one part to a different directory will cause restore to fail. Do not use this flag on unsupported versions, and always verify **every part** is copied intact.

## 10. Backing Up on Aura: Service-Managed Snapshots

**Neo4j Aura does not give customers server shell access to run `neo4j-admin database backup` like self-managed deployments.** Your service tier determines snapshot types, frequency, retention, and restore/export options. Restores are triggered via **Aura's UI/API/workflows**, not backup port 6362.

General workflow:

1. Identify your **Aura plan, instance version, and admin account permissions**.
2. Open the instance/database management page and go to the **Backups/Snapshots** section supported by your tier.
3. Review **scheduled snapshots** and **on-demand snapshot** availability.
4. Confirm retention, which snapshot types can be restored/exported, and tier limits.
5. Choose **restoring into a controlled environment** when testing; never overwrite a production database out of habit.
6. After restore, verify URIs, credentials, network access, application data, sync plans, and related integrations.

### Do Not Confuse Snapshot Restore with Exportability

A snapshot may be **restorable** inside the service yet **not exportable** over the same retention window. Aura documentation distinguishes:

- **Scheduled full/differential snapshots** by tier and service generation.
- **On-demand snapshots**, subject to tier limits/capabilities.
- **Restorable days** vs. **exportable days**, which can differ.
- Restore operations scoped to **individual databases** vs. the **entire instance**.

Therefore, before promising "we can download a backup file to move to a self-managed server," verify **actual export support** for that snapshot/tier. Never extrapolate retention numbers from other tiers onto AuraDB Free or Professional.

Source: [Neo4j Aura — Backup, export, restore and upload](https://neo4j.com/docs/aura/managing-instances/backup-restore-export/).

## 11. Verifying Artifacts and Backup Chains After Execution

A job is technically complete only when:

1. The tool exits with a **success code** and logs show no errors.
2. Artifacts exist, no files are missing, and they reside in the proper repository.
3. Metadata shows the expected **database name/ID**, timestamp, FULL/DIFF type, and transaction ID range.
4. The chain can restore to the desired point in time.
5. Recoverability is periodically tested on an isolated database.

### 11.1. Inspecting Metadata

~~~bash
neo4j-admin database backup \
  --inspect-path=/srv/neo4j-backups/orders
~~~

`--inspect-path` reads artifact information (without creating a new backup). Metadata can include:

| Field | What to verify |
| --- | --- |
| `FILE` | Artifact path, still present and readable |
| `DATABASE` / `DATABASE ID` | Ensures you do not mix up backups from different databases |
| `TIME` | Backup timestamp, determining freshness upon restore |
| `FULL` | `true` for FULL, `false` for DIFF |
| `LOWEST TX` / `HIGHEST TX` | Transaction ID range covered by the artifact |
| `COMPRESSED` / `RECOVERED` | Compression and recovery status, depending on version/tool |

**Inspection does not verify full physical consistency.** An artifact with valid-looking metadata can still fail to restore due to missing chain links, storage corruption, incompatibility, or insufficient disk space.

### 11.2. Aggregating Chains When Appropriate

In versions with `neo4j-admin backup aggregate` (modern command name from 2025.01):

~~~bash
# Practice on an authorized backup repository.
# Keep old artifacts during testing so you do not lose an active chain.
neo4j-admin backup aggregate \
  --from-path=/srv/neo4j-backups/orders \
  --keep-old-backup=true \
  orders_graph
~~~

This command combines FULL + DIFF, runs recovery, and produces a recovered FULL artifact. It is **not free in CPU, I/O, or temporary disk space**. In older releases, the aggregate command name may differ; check `--help`.

### 11.3. Consistency Check

Neo4j provides `neo4j-admin database check` for consistency checking within version-supported boundaries. Before running it on an artifact:

- Verify whether your version supports `--from-path` for backups/dumps (this flag evolved across 2025.x).
- If the tool requires a recovered backup, aggregate first.
- Run on a host and at a time with sufficient RAM/disk; inspect both exit code and report.
- Distinguish **physical consistency** from **business correctness**: a graph with broken business invariants can still pass structural checks.

See [Neo4j — Consistency checker](https://neo4j.com/docs/operations-manual/current/backup-restore/consistency-checker/).

## 12. Restore Drill: Proving a Backup Through Actual Recovery

**Warning:** Restore is a sensitive operation. **Never run the examples below against a customer-facing production database.** Provision an isolated test server/DBMS with dedicated permissions, config, and storage, using an approved copy of the backup.

### 12.1. Safe Restore Workflow

1. Select the **recovery point and FULL/DIFF artifacts** from metadata; verify the complete chain.
2. Stand up an **isolated Neo4j Enterprise lab** or documentation-approved environment with compatible config and version.
3. Ensure the target database **does not yet exist or is properly stopped**; avoid overwriting other data.
4. Run `neo4j-admin database restore` with `--from-path` pointing to the appropriate artifact/chain.
5. Create/start the restored database per version guidance (if needed), then verify online status.
6. Run consistency checks and **business reconciliation queries**, timing until the API is usable again.
7. Document gaps against RPO/RTO and update the runbook.

### 12.2. Command Example for an Isolated Lab Only

~~~bash
# Path must point to an actual artifact within a complete chain.
# Target database orders_graph_restored DOES NOT EXIST yet on the lab DBMS.
neo4j-admin database restore \
  --from-path=/srv/neo4j-backups/orders/orders_graph-TIMESTAMP.backup \
  orders_graph_restored
~~~

`orders_graph-TIMESTAMP.backup` is a **placeholder**; obtain the real name via inspect. When targeting the final DIFF artifact of a chain, the tool looks up related artifacts to replay all transactions. Per documentation, restoring into a new database typically requires running **`CREATE DATABASE orders_graph_restored`** in the `system` database (Enterprise) to register it, then verifying it comes online.

**Never add `--overwrite-destination=true` out of habit.** Overwriting an existing database can destroy data, and Neo4j docs warn that overwriting in a cluster is **unsafe** due to cluster state; in clusters, restore into a **new database** following cluster-specific procedures.

### 12.3. Post-Restore Cypher Verification

~~~cypher
SHOW DATABASES
YIELD name, currentStatus
RETURN name, currentStatus
ORDER BY name;
~~~

~~~cypher
// Run on the restored database, not the source database.
MATCH (c:Customer)
RETURN count(c) AS customerCount;
~~~

~~~cypher
// Verify a critical business relationship.
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN count(*) AS placedEdges;
~~~

~~~cypher
SHOW CONSTRAINTS
YIELD name, type
RETURN name, type
ORDER BY name;
~~~

Node and relationship counts are only a **sanity check**. Reconcile by business IDs and business state—such as `Order.orderId`, `PLACED` ownership, `Customer.customerId` keys, path-query results, required indexes/constraints, and the latest recovered commit timestamp.

### 12.4. Application Recoverability

Even after the restore tool succeeds, the application may still fail because:

- Database names/aliases, user accounts, and roles were not properly restored.
- URIs, TLS certificates, cluster routing, or network policies do not yet point to the new host.
- APOC/GDS plugins, custom procedures, or `neo4j.conf` were not redeployed.
- Kafka/CDC sync jobs, search indexes, caches, bookmarks, or checkpoints have not been reconciled.
- Data committed after the backup timestamp needs replaying/reconciling against other authoritative systems.

**Measure RTO until users can execute critical workflows**, not merely until the restore command reports success.

## 13. Notes on Metadata, Users/Roles, and Cross-System Dependencies

### 13.1. The `system` Database and RBAC

In multi-database Neo4j Enterprise, `system` holds administrative state. Backup docs advise **planning backups for all databases, including `system`**. Depending on `--include-metadata`, a database artifact can also carry associated user/role metadata.

However, **never assume a single database backup carries all users, roles, privileges, and DBMS configurations**. During restore, user/role metadata may require running generated reconstruction scripts, resolving conflicts, and checking admin permissions. Always back up and manage **configuration, secrets, TLS certificates, and plugin definitions** through dedicated procedures separate from data artifacts.

### 13.2. External Systems Are Not Inside Neo4j Backups

Suppose an Order Service uses PostgreSQL as its transactional source of truth, Neo4j as a read model, and Kafka as a broker. A Neo4j backup captures only the **graph state at that instant**; it does not simultaneously back up PostgreSQL tables, Kafka offsets, object storage, or search indexes.

During restore:

1. Determine how many events the graph is missing compared to the source of truth.
2. Identify a reconcilable **source version/watermark**.
3. Replay or rebuild projections using business IDs and idempotent upserts/deletes.
4. Account for deletion events, ownership transfers, out-of-order states, and orphaned records.
5. Mark freshness-dependent APIs ready only after meeting the freshness contract.

### 13.3. Neo4j CDC After Restore

If downstream consumers read Neo4j CDC, a restore can alter database/transaction-log lifecycles, rendering **old change identifiers/cursors invalid**. `txLogEnrichment` mode may need reconfiguration when creating a new database. Never blindly restart a consumer with an old cursor and assume every event was preserved.

CDC recovery design must include:

- Identifying a consistent cut point and which event sources remain intact.
- Confirming CDC is enabled on the database in a supported edition/version.
- Re-bootstrapping/reconciling downstream systems that may have missed events.
- Recording evidence of the recovered synchronization checkpoint.

### 13.4. Graph Data Science and In-Memory State

Named graphs in the **GDS graph catalog** are in-memory analytical projections, not base nodes/relationships in the store. After restore/restart, in-memory graph projections may need to be **re-projected**, and analytical models/features may not reside in database backups depending on GDS policy and edition. Never judge a restore complete solely because Cypher `MATCH` works if the application also relies on GDS jobs and caches.

## 14. Securing Backups and Recovery

A backup can contain **all sensitive data** that regular Neo4j users are normally restricted from reading. Once someone obtains a backup file, source database RBAC no longer protects offline contents. Thus, the backup repository is a **high-sensitivity asset**.

Principles:

- **Network:** block public access to backup port `6362`; allow only designated backup clients to reach the endpoint, using TLS per policy.
- **OS permissions:** restrict backup directories and artifact files strictly to required operational accounts; never stage backups in `/tmp` or broadly shared directories.
- **Encryption:** protect data in transit and at rest, managing keys outside the repository; define key-recovery procedures for incidents.
- **IAM permissions:** grant least-privilege read/write/list/delete permissions to jobs and operators; separate backup creation rights from backup deletion rights where possible.
- **Immutability/retention:** use versioning or object lock to restrict unauthorized deletion/modification while respecting legal retention/erasure mandates.
- **Isolation:** store a copy in a separate failure domain; follow the 3-2-1 model and test restores from the off-site copy.
- **Audit:** log who creates/downloads/deletes artifacts, backup policy edits, and restore drill results; never leak secrets into command logs.

In particular, exposing the backup port to the Internet can create a **database exfiltration vulnerability**. Never fix a backup connection error by opening `0.0.0.0:6362` without firewalls and TLS.

## 15. Backup Monitoring: Measure Success, Not Just Cron Execution

A backup job must emit alertable **telemetry**:

| Metric | Meaning | Alert when |
| --- | --- | --- |
| `last_successful_backup_at` | Timestamp of the most recent valid backup | Too old relative to schedule/RPO |
| `backup_duration_seconds` | Time to create/copy/compress/recover | Sharp spike or exceeds window |
| `backup_exit_code` | Tool exit status | Non-zero or missing job logs |
| `backup_type` | Whether FULL/DIFF/AUTO actually ran | DIFF failed or unexpected FULL |
| `backup_bytes` / transfer rate | Size and network I/O | Abnormal growth/drop, destination full |
| `backup_chain_health` | Validity of chain and transaction IDs | Missing artifact or chain gap |
| `restore_drill_result` | Proven recoverability | Drill failed or exceeded RTO |
| `backup_repository_free_bytes` | Remaining storage space | Nearly full or abnormal growth rate |
| `production_latency_during_backup` | Impact on workload | Transaction p95/p99 breaches SLO |

Avoid placing unbounded `databaseName` or sensitive business IDs into metric labels. Track **environment, database, backup job, source server, and artifact timestamp** using controlled label sets.

### 15.1. The "Cron Ran So Backup Is Fine" Trap

A scheduler may mark a shell command complete even if it only launched a wrapper without checking `neo4j-admin`'s actual exit code. Verify:

1. When did the job start and finish?
2. What **exit code** did the tool return?
3. Were artifacts created completely at the right destination?
4. Does inspect show a newer transaction checkpoint?
5. How **successful was the most recent restore drill**?

If today's backup failed and the last successful one was three days ago, actual RPO is not 15 minutes even if cron says "every 15 minutes."

### 15.2. Appropriate Alerting

- **Critical:** no backup satisfies the recovery threshold, artifacts/chains are missing, repository files were unexpectedly deleted, or backup source is persistently unreachable.
- **Warning:** storage nearing capacity, rising backup duration, restore drill exceeding RTO, or heavy impact on OLTP traffic.
- **Informational:** scheduled FULL completed, backup client version updated, approved retention policy change.

Design alerts around **impact on recoverability**, not a single isolated CPU spike.

## 16. Runbook: Backup Incidents and Remediation

### Case A — Cannot Connect to Backup Endpoint

Symptoms: `Connection refused`, timeout, or TLS handshake failure when calling `neo4j-admin database backup`.

1. Confirm **Enterprise Edition**, target database online, and backup service enabled.
2. Check `server.backup.listen_address` for exact interface/port, distinguishing localhost vs. remote client.
3. Check network paths, firewalls, Docker ports/NetworkPolicies, and proxies.
4. If using TLS, inspect trust stores, CAs, hostnames, keys/certs, and TLS versions.
5. Retry within authorized bounds; never open the backup port publicly as a quick fix.

### Case B — DIFF Fails or Chain Is Broken

1. Run `--inspect-path` to view all FULLs and DIFFs with database IDs and transaction IDs.
2. Verify parent artifacts were not deleted/moved and the backup destination is not mixing incompatible sources.
3. Check logs for missing required transaction logs or retention pruning errors.
4. If policy allows, take a **new FULL** with official tooling; adjust retention/aggregation schedules.
5. Re-evaluate RPO from the latest FULL/DIFF **actually proven recoverable**.

### Case C — Insufficient Staging Disk Space

1. Remember `--to-path` and `--temp-path` are **two distinct storage areas**, especially when writing to cloud.
2. Check absolute free space, inodes/quotas, write speed, and file permissions.
3. Expand staging on an appropriate volume; do not delete artifacts still needed in active chains.
4. Re-run and record peak space usage for capacity planning.

### Case D — Backups Slow Down Application Queries

1. Inspect CPU/disk/network on both Neo4j source and backup client, API p95/p99, and active transactions.
2. Reduce concurrent backup jobs or target a sufficiently fresh secondary cluster member.
3. Offload compression/aggregation to a dedicated backup client and tune page cache/heap methodically.
4. Reschedule FULLs or spread load; evaluate impact on RPO/RTO.
5. **Never** prioritize a "fast-at-all-costs" backup if it causes payment/write transactions to fail.

### Case E — Restore Succeeded, But the Application Fails

1. Confirm the database is registered/started and `currentStatus` is right.
2. Check users/roles, aliases, database name, TLS/URI, networking, and Java Driver routing.
3. Verify indexes/constraints, sample Cypher lookups, and critical paths.
4. Redeploy plugins/configs and rebuild graph projections/caches if required by the app.
5. Reconcile external systems, CDC/checkpoints/outbox, and transactions committed after the backup checkpoint.
6. Switch traffic only once **read/write availability** and business data checks pass acceptance.

## 17. Lab Exercise: A FULL → DIFF → Inspect → Restore Drill Cycle

**Goal:** on an **isolated Neo4j Enterprise lab**, demonstrate that an online backup taken while the database is live can be restored, and estimate preliminary RPO/RTO. Never practice restores or alter backup listeners in production.

### Step 1 — Set Up Sample Data

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

~~~cypher
MERGE (c:Customer {customerId: 'C-BACKUP-01'})
MERGE (o:Order {orderId: 'O-BACKUP-01'})
SET o.status = 'CREATED', o.totalCents = 100000
MERGE (c)-[:PLACED]->(o);
~~~

### Step 2 — Configure and Run FULL

Confirm Enterprise Edition, backup service, directory permissions, backup client, and backup port over a private network. Run:

~~~bash
neo4j-admin database backup \
  --from=10.0.10.12:6362 \
  --to-path=/srv/neo4j-backups/lab \
  --type=FULL \
  neo4j
~~~

Here `neo4j` is just an **example lab database**. Never assume every deployment uses this database name or back up all databases when only one is needed.

### Step 3 — Mutate Data and Run DIFF

~~~cypher
MATCH (o:Order {orderId: 'O-BACKUP-01'})
SET o.status = 'PAID';
~~~

~~~bash
neo4j-admin database backup \
  --from=10.0.10.12:6362 \
  --to-path=/srv/neo4j-backups/lab \
  --type=DIFF \
  neo4j
~~~

**Check:** the second command produces a valid DIFF for the right database and chain; do not rely solely on filenames to determine backup type.

### Step 4 — Inspect and Record Checkpoints

~~~bash
neo4j-admin database backup \
  --inspect-path=/srv/neo4j-backups/lab
~~~

Record which artifacts are FULL/DIFF, timestamps, database ID, and transaction ID ranges. Evaluate: if the DIFF were lost, how far back would recovery revert based on the remaining FULL?

### Step 5 — Restore into an Isolated Environment

1. Stand up a Neo4j lab target **separate** from the source.
2. Select the final DIFF artifact of the chain along with all linked files.
3. Run `neo4j-admin database restore` per version docs, creating the new database if required.
4. Check whether `O-BACKUP-01` has `status='PAID'`:

~~~cypher
MATCH (o:Order {orderId: 'O-BACKUP-01'})
RETURN o.orderId AS id, o.status AS status, o.totalCents AS totalCents;
~~~

5. Verify relationships and constraints, measuring elapsed time from recovery start until lab read/write queries succeed.

Restoring **only the FULL taken before the update** should show `CREATED`; restoring the chain including the DIFF covering the update should show `PAID`. That demonstrates **RPO checkpoints and chain continuity**.

### Step 6 — Controlled Failure Simulation

No need to destroy live data. Use a **copy of the lab backup directory** to test:

- Removing a DIFF artifact from the **copy** (never modify the primary repository).
- Setting bad read permissions on the copy or an invalid `--temp-path` and observing the error messages.
- Passing a different database name and verifying it does not restore into the wrong target.
- Measuring restore duration with many DIFFs; evaluate aggregation if RTO is missed.

### Self-Check Questions

**1. Can Neo4j Community perform online backups simply by setting `server.backup.enabled=true`?**

No. `neo4j-admin database backup` is an Enterprise feature; configuration flags do not turn Community into Enterprise.

**2. Why isn't cluster replication treated as a backup?**

Because erroneous updates or accidental deletions replicate to other members; replication provides availability, whereas backups recover historical data points.

**3. A DIFF job runs every 15 minutes, but the last successful run was 2 hours ago. Is actual RPO ~15 minutes?**

No. Measure from the **latest valid recoverable point** to the incident, accounting for actual backup outcomes and chain integrity.

**4. Why does backing up to S3 still require a large `--temp-path`?**

Because backup uses local staging before packaging and uploading artifacts to cloud storage; object storage does not eliminate temporary local disk needs.

**5. Can backup port 6362 be exposed to the Internet as long as Bolt uses passwords?**

No. The backup protocol differs from Bolt; the backup endpoint must be protected by firewalls/private networking and TLS per policy.

**6. Can you use `--overwrite-destination=true` to restore directly over a database in a live cluster?**

Do not do this: overwriting in a cluster is unsafe due to cluster state; documentation recommends **restoring as a new database** following supported cluster workflows.

**7. After restore, `MATCH` works, yet the CDC consumer fails. Why?**

Enrichment configuration, cursors/transaction logs, checkpoints, or database lifecycle identifiers may have changed; re-bootstrap/reconcile rather than blindly reusing old cursors.

## 18. Implementation and Operations Checklist

- [ ] Confirm **Neo4j edition, version, license, and deployment model**; do not expect Enterprise online backup on Community or Aura.
- [ ] Define **RPO/RTO** and recovery points per database/service.
- [ ] List all physical databases to back up, including `system` where appropriate, plus external assets needed to rebuild.
- [ ] Configure the backup service and listen address **only on authorized networks**; protect port 6362 with firewalls and TLS.
- [ ] Use a compatible backup client/version with least-privilege OS and IAM permissions.
- [ ] Choose FULL/DIFF/AUTO per version, seed an initial FULL, and verify chains.
- [ ] Track source/backup transaction IDs, especially in clusters.
- [ ] Separate destinations from sources; protect artifacts with encryption, retention, and versioning/immutability.
- [ ] Provision adequate **destination disk, staging disk, heap, page cache, CPU, and network** for backups.
- [ ] Verify exit codes, artifact metadata via `--inspect-path`, and chain continuity.
- [ ] Run consistency checks/aggregation under version-supported conditions.
- [ ] Conduct regular restore drills on **isolated** servers/databases without overwriting production.
- [ ] Reconcile Cypher data: nodes, relationships, business IDs, indexes/constraints, and checkpoint transactions.
- [ ] Measure RTO until the application **actually serves traffic**, not just until the CLI exits.
- [ ] Maintain runbooks for roles, aliases, secrets, plugins, configs, CDC, caches, and cross-system sync.
- [ ] Alert when **last successful backup** ages out, chains break, storage fills up, or restore drills fail.
- [ ] Regularly review **Aura snapshot/retention policies** if using the managed service.
- [ ] Drill disk exhaustion, missing artifacts, version mismatches, lost storage permissions, and cross-region recovery scenarios.

## Official References

- [Neo4j Operations Manual — Back up an online database](https://neo4j.com/docs/operations-manual/current/backup-restore/online-backup/)
- [Neo4j Operations Manual — Backup modes](https://neo4j.com/docs/operations-manual/current/backup-restore/modes/)
- [Neo4j Operations Manual — Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/)
- [Neo4j Operations Manual — Aggregate a database backup chain](https://neo4j.com/docs/operations-manual/current/backup-restore/aggregate/)
- [Neo4j Operations Manual — Restore a database backup](https://neo4j.com/docs/operations-manual/current/backup-restore/restore-backup/)
- [Neo4j Operations Manual — Check database consistency](https://neo4j.com/docs/operations-manual/current/backup-restore/consistency-checker/)
- [Neo4j Operations Manual — Offline database dump](https://neo4j.com/docs/operations-manual/current/backup-restore/offline-backup/)
- [Neo4j Operations Manual — Backup ports and configuration](https://neo4j.com/docs/operations-manual/current/configuration/ports/)
- [Neo4j Operations Manual — Docker online backup](https://neo4j.com/docs/operations-manual/current/docker/backup-restore/)
- [Neo4j Aura — Backup, export, restore and upload](https://neo4j.com/docs/aura/managing-instances/backup-restore-export/)

**Conclusion:** Neo4j online backup is a capability **conditional on edition and service**. In **self-managed Enterprise**, `neo4j-admin database backup` enables FULL/DIFF backups while the database stays online, provided you manage backup endpoints, TLS, resources, transaction chains, and storage security. In **Aura**, snapshots are governed by service plan; in **Community**, do not mistake Enterprise online backup commands for offline dumps. **A backup is trustworthy only once it has been restored, reconciled, and proven to bring the application back within committed RPO/RTO.**
