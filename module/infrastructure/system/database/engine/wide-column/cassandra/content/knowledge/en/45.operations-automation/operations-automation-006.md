# Periodic Restore Testing and Recording Recovery Evidence

> **Chapter:** Operations Automation  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — understanding distributed architecture and the Apache Cassandra wide-column model, specifically partition keys, query-driven table design, and read/write consistency; practicing CQL, replication, compaction, repair, error handling, and connecting from Java applications.

A system has a nightly snapshot job, displays a "backup succeeded" notice on its dashboard, and has stored many terabytes of SSTables in object storage. When a critical keyspace is accidentally dropped, the on-call team discovers that `schema.cql` was never preserved, several nodes lack concurrent snapshots, credentials/KMS for the recovery region were never provisioned, and Java reads fail due to a missing role. **A green backup job does not prove recoverability.**

A trustworthy backup program requires **repeatable restore drills in an isolated environment**, measuring **RPO (Recovery Point Objective)** and **RTO (Recovery Time Objective)** from real runs, verifying data, schema, access permissions, and consistency, and archiving auditable evidence. That is the objective of this lesson.

**Scope:** Cassandra 4.1/5.0, native CQL, SSTable snapshots/incremental backups, additional requirements when commitlog archiving is present, Java Driver 4.x, and a product-agnostic automation orchestrator. Command names and options vary across versions; always check `nodetool help` and docs for your running release. Do not treat commands in this lesson as a ready-to-use production runbook.

> **Critical safety:** Restore exercises must run ONLY on **an isolated lab cluster, synthetic data, dedicated credentials, and allowlisted namespaces/paths**. Never `DROP/TRUNCATE` a production keyspace, write SSTables into a live production data directory, alter system keyspaces/host IDs on a user-serving cluster, or run a real restore simply because CI reports missing test coverage.

## 1. Learning objectives and success criteria

After this lesson, you can:

1. Distinguish snapshots, incremental SSTable backups, commitlog archiving, anti-entropy repair, and replication; know which data or consistency guarantees each mechanism **does not** provide.
2. Define RPO, RTO, restore scope, and workload invariants before deploying automation.
3. Design a **sufficiently complete backup manifest** to rebuild schema, topology, table IDs/SSTables, Cassandra version, data, and security configuration.
4. Pick the right restore path: `sstableloader` streaming into a lab cluster with compatible schema, `nodetool refresh` for local SSTables matching exact node/layout, or an appropriate full node recovery procedure.
5. Explain why per-node snapshots do not produce **an atomic cluster-wide snapshot transaction**.
6. Schedule restore drills by risk level with concurrency limits, deadlines, isolation, and stop conditions.
7. Validate checksums/manifests, object access, encryption/decryption, retention, schema, roles, data, TTLs/tombstones, and the Java application path.
8. Measure **observed RPO** and **observed RTO** using UTC timestamps and separate restore, query-readiness, and application-readiness phases.
9. Produce an evidence ledger, run ID, logs/tracing metrics, sample key catalog, and a substantiated PASS/FAIL report.
10. Design negative tests such as missing SSTable components, version mismatch, unavailable KMS, missing roles, partial restores, full disks/quotas, and post-failure recovery.
11. Explain why **replication/repair do not replace off-cluster backups**, and why hard-linked backups are not independent of the failure domain.
12. Assess drill risks, protect production data, audit access, and assign approvers.

**Overall success criterion:** a restore test counts as `PASS` only when **the chosen backup can genuinely be decrypted and read, all dependencies are present, data and application behavior match targets, RPO/RTO stay within thresholds, and evidence is durably archived**. Checking only file presence or Cassandra startup without reading accurate data yields at most `BACKUP_PRESENT` or `CLUSTER_BOOTED`, never `RESTORE_VERIFIED`.

## 2. Why test restores periodically?

### 2.1. Failures missed by "backup succeeded"

| Failure mode | Backup job may stay green | Restore drill catches it |
|---|---|---|
| Snapshots exist on only two of three nodes | Yes, if job aggregation is flawed | Missing token ranges/replica coverage in manifest |
| Hard-linked snapshot never copied off-node | Yes | Losing node/disk destroys both source and "backup" |
| Object-store file corrupted or missing a component | Yes | Checksum/SSTable TOC or loader fails |
| Schema/UDTs/indexes/roles not saved | Yes | Target cluster cannot rebuild model or app lacks grants |
| KMS/truststore/key rotation issues | Yes | Cannot decrypt, start, or connect |
| Snapshot taken from too stale a point | Yes | Observed data loss breaches RPO |
| TTLs/deletes expired | Yes | Wrong live-row expectations or resurrection risk |
| Gap in incremental chain | Yes | Real RPO differs from dashboard watermark |
| Version incompatibility / SSTable format | Yes | Loader/refresh fails or schema mismatch detected |
| Insufficient recovery disk/RAM/network | Yes | Restore misses RTO or runs out of disk |
| Java Driver cannot connect | Yes | Missing roles, TLS, local DC, or routing config |

**Recoverability is a whole-system property**, spanning backups, offsite storage, metadata, keys, compute/network resources, Cassandra topology, CQL schema, accounts, runbooks, and result verification.

### 2.2. Distinguishing replication, repair, backup, and restore

~~~mermaid
flowchart LR
    A["Cassandra mutation"] --> B["Replicas per RF/CL"]
    B --> C["Anti-entropy repair"]
    B --> D["SSTable snapshots"]
    D --> E["Independent off-cluster storage"]
    B --> F["Incremental SSTable copies"]
    F --> E
    G["Optional commitlog archive"] --> E
    E --> H["Restore into isolated cluster"]
    H --> I["Data + app validation"]
    I --> J["Measured RPO/RTO + evidence"]
~~~

- **Replication** maintains copies across chosen failure domains, yet it also propagates accidental deletes, app bugs, or logical corruption.
- **Repair** synchronizes existing replicas; once a valid delete propagates to all replicas, repair cannot recover the pre-delete state.
- **Snapshots/incremental backups** are recovery artifacts captured at SSTable flush points and must be moved to independent storage with retention and integrity checks.
- **Commitlog archives** can extend recovery to mutations after the snapshot, yet require segment coverage, timestamp semantics, and real testing.
- **Restore drills** prove a specific set of artifacts can reconstruct required data and applications at test time; they do not fix a backup that has gaps.

### 2.3. Failure domains and what "independent" means

A hard-linked snapshot on the same filesystem **does not protect against** disk loss or volume deletion. Off-cluster copies in a separate account/region of object storage, with immutability/retention and least privilege, are stronger yet can still share a control plane, credentials, or KMS failure. An off-region copy encrypted with **the exact key that was just deleted** is unrecoverable.

When scheduling drills, define explicitly:

~~~text
Production cluster -> isolated restore environment
Production backup account -> read-only restore identity with scoped permissions
Backups / encryption keys -> controlled, audited, tested access
No network path from restore client to production native 9042 by default
Cleanup restricted to ephemeral lab resources
Evidence exported to independent, access-controlled storage
~~~

## 3. RPO, RTO, RLO metrics and how to measure them

### 3.1. RPO is not "the age of the backup job"

**RPO** is the maximum tolerable data-loss window (e.g., 15 minutes). During a drill, one practical measurement is:

\[
\text{observed RPO} =
\text{disaster cut time} -
\text{latest verified recoverable write time}.
\]

**Condition:** "latest verified recoverable write" must rely on a ledger, fixture, or meaningful verification—not merely the newest filename timestamp. Writes **after** the recovery point that are intentionally excluded are **expected loss**, not corruption.

Illustrative example: simulated failure at 12:00Z; the latest confirmed restored mutation ACK was at 11:52Z, with no proof for 11:53Z. Report `observed RPO ≤ 8 minutes on tested writes`, rather than claiming "exact 8-minute RPO across all keyspaces" when coverage only spans 100 keys.

### 3.2. RTO needs consistent start and end boundaries

**RTO** is how long the service may remain down before serving capability returns. Drill phases:

~~~text
T0         DR declared / start simulated loss
T1         Backup set selected and manifest verified
T2         Isolated infra, keys, schema/roles ready
T3         SSTable stream/restore ends
T4         Cassandra nodes healthy; reads/writes meet required CL
T5         Java application completes representative transactions
T6         Correctness tests and operational checks pass
~~~

Define "service restored" upfront: some organizations use `T5` once minimum integrity checks pass, others `T6`. **Never measure RTO solely from when `sstableloader` starts to when it exits**, as provisioning, decryption, schema/role creation, and validation often dominate total time.

### 3.3. Recovery Level Objective and coverage scope

Beyond RPO/RTO, describe **the recovered service scope**: one table, a keyspace, multiple DCs, whole cluster, or single tenant; read/write or read-only; 1% sample or all partitions. RLO here is an internal name for **the target functional/data level**, not a built-in Cassandra metric.

| Target | Test scope | Must not infer |
|---|---|---|
| Single table | CQL schema, SSTables, keys, TTL, Java repository | Whole keyspace restored |
| Keyspace | Required tables/UDTs/indexes/functions, read/write | All `system_auth`/credentials ready |
| Single DC | Local RF/CL, nodes, and token ranges | Multi-DC disaster recovery achieved |
| Full service | CQL access + Java workflows/TLS/auth/metrics | Organization-wide backups all usable |
| PITR | Point-in-time target and replay semantics | Global single-commit consistency across tables |

### 3.4. Sample drill SLOs, not Cassandra standards

| Test class | Suggested cadence | Suggested target | Approver |
|---|---|---|---|
| Object/file integrity | Daily | 100% manifest files present + checksum match | Backup owner |
| Synthetic single-table restore | Weekly | Schema + representative rows + Java query PASS | DB/platform owner |
| Keyspace/service restore | Monthly | RPO/RTO per published tier | Service owner + SRE |
| PITR/window boundary | Quarterly | Time-target includes/excludes exact fixtures | DB recovery owner |
| Cross-region/credential-loss drill | Every 6–12 months | Independent access, region isolation, and recovery | Security + DR owner |

Cadences are **risk-governance examples**. Service tiers requiring RPO 0 or near-real-time recovery need matching backup chains and drills; never cite a "monthly restore" as evidence of a 15-minute RPO.

## 4. What does Cassandra actually back up?

### 4.1. Snapshot = hard links to existing SSTables

Apache Cassandra stores on-disk data in immutable SSTable components. `nodetool snapshot` normally flushes memtables before snapshotting so pre-flush writes reside in SSTables. Snapshots consist of **hard links** to SSTable components and usually include `schema.cql` and a manifest. Depending on the release, passing `--skip-flush` **omits data still in memtables** not yet flushed to SSTables.

~~~text
<data_dir>/<keyspace>/<table>-<table_id>/
  <sstable components...>
  snapshots/
    <tag>/
      <version>-<generation>-Data.db
      <version>-<generation>-Index.db
      <version>-<generation>-Statistics.db
      <version>-<generation>-TOC.txt
      ... (corresponding components)
      manifest.json
      schema.cql
  backups/
    <sstable components...>
~~~

This layout is **illustrative**; actual SSTable names and paths differ by version and installation. Never copy only `Data.db` while omitting `Index.db`, compression info, statistics, or TOC. Derive the file list from the manifest or actual snapshot directory.

Example snapshot command on a **lab node**:

~~~bash
nodetool help snapshot
nodetool snapshot --tag drill-20261121 --table events_by_device_day restore_lab
nodetool listsnapshots
~~~

**A single `nodetool snapshot` on node N1 snapshots only N1's local data**; it does not automatically capture N2/N3. The coordinator/orchestrator must snapshot **each required node**, recording tags, timestamps, and token coverage. Node snapshots happen at slightly different instants while writes continue.

### 4.2. Incremental backups = hard links from flushes/streams

When `incremental_backups: true` or `nodetool enablebackup` is active, Cassandra hard-links flushed/streamed SSTables into each table's `backups/` directory. They are not automatically uploaded to object storage or pruned, requiring separate upload and retention pipelines.

~~~bash
# Read-only status check on an authorized node:
nodetool statusbackup

# These commands CHANGE runtime configuration and do not belong in check steps:
# nodetool enablebackup
# nodetool disablebackup
~~~

An incremental backup **is not** "a list of all CQL mutations since the snapshot." It holds flushed/streamed SSTables and excludes unarchived commitlogs or unflushed memtables. When designing restore chains, account for SSTable generations, compaction, deletions/tombstones, and overlaps; **never concatenate filenames or estimate row counts by summing SSTables**.

### 4.3. Commitlog archiving and PITR are a separate flow

`commitlog_archiving.properties` includes fields such as `archive_command`, `restore_command`, `restore_directories`, `restore_point_in_time`, and `precision`. Archived segments can supply post-snapshot mutations, provided:

- **All relevant segments for the node/table** are archived, not just the latest file.
- Archiving succeeds and copies artifacts to durable, independent storage; node-local hard links can still be lost with the disk.
- PITR cutoffs follow mutation/write timestamps and replay semantics, **not a distributed transaction timestamp**.
- Out-of-order/client-supplied timestamps, TTLs/deletes, and concurrent writes make "restoring the exact state at 12:00Z" trickier than an arrival-time cut.
- Commitlog restores risk overwriting state if misapplied across nodes, segments, or schemas; test only in labs with release-matched runbooks.

Example **descriptive configuration file**, never plug straight into production untested:

~~~properties
# Paths and scripts are purely illustrative; scripts must enforce safety checks.
archive_command=/opt/drill/bin/archive-segment %path %name
restore_command=/opt/drill/bin/restore-segment %from %to
restore_directories=/srv/restore-drill/commitlogs
restore_point_in_time=2026:11:21 12:00:00
precision=MICROSECONDS
~~~

Some documentation explains that when client timestamps exceed the PITR cutoff, recovery handles segments under specific rules; timestamp ordering mismatches can still prevent certain pre-cutoff mutations from replaying. **Never promise microsecond-exact PITR** without testing diverse CQL mutations against real version semantics. <https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_cl_archive_file.html>.

### 4.4. No cluster-wide consistent snapshot by default

Per-node snapshots occur at slightly different times, each holding SSTables for its own token ranges and replicas. Under active writes:

~~~text
N1 snapshot at 11:59:58Z
N2 snapshot at 12:00:04Z
N3 snapshot at 12:00:09Z
~~~

Never assume these snapshots represent **an atomic cut at 12:00:00Z** across partitions and tables. Business-workflow consistency may require **quiescing writers, application barriers/checkpoints, event-sequence ledgers, or specialized restore strategies**. Never equate per-node `nodetool snapshot` success with transaction-level consistency.

### 4.5. What SSTable backups do not carry automatically

| Dependency | Where to store/verify |
|---|---|
| Keyspace DDL, table DDL, UDTs, indexes/SAI, materialized views | Versioned schema exports and migration order |
| Roles, grants, and authentication state | Dedicated `system_auth` procedure; never copy system tables blindly |
| Cassandra version / JDK / native protocol | Build/cluster manifest |
| `cassandra.yaml`, rack/DC topology, encryption, snitch | Configuration backup with secrets redacted |
| TLS certs/truststores, KMS keys, object credentials | Least-privilege secret/KMS recovery plan |
| SSTable version, table IDs, token ownership, RF | Source manifest and target restore mapping |
| Commitlog archives if PITR is required | Chain, segment checksums, target timestamps |
| Java Driver/Spring Data/DTO/codec compatibility | App releases, integration tests, CQL contracts |
| Business event logs/operation IDs, TTL policies | Fixture ledger and reconciliation plan |

Never copy raw `system.local`, `system.peers`, token/host-id configs, or full `system_*` directories from source to a different-topology target cluster. They hold cluster-specific metadata that can corrupt the restore environment. `system_auth` backups also have specific restore requirements; test roles/grants in an **isolated cluster** under security runbooks rather than feeding production credentials into tests.

## 5. Designing a reproducible backup manifest

### 5.1. Logical backup unit

Each backup set is identified by a **unique `backup_set_id`** and **node/table components**:

~~~text
backup_set_id
  ├── cluster metadata, schema, versions, RF/DC/token/host IDs
  ├── snapshot tag + per-node UTC capture window
  ├── source node A: tables + SSTable file list/checksums
  ├── source node B: tables + SSTable file list/checksums
  ├── source node C: tables + SSTable file list/checksums
  ├── incremental sets and commitlog archive references (if enabled)
  ├── encryption/key references, not plaintext secrets
  └── application verification fixture catalog
~~~

**Never use only a timestamp or snapshot folder name as the restore identifier.** Two nodes may share a tag yet have different SSTable sets, differing tables, or incomplete uploads. Use an immutable manifest and content checksums.

### 5.2. Illustrative YAML manifest

~~~yaml
manifest_version: "1"
backup_set_id: "cass-restore-lab-20261121T120000Z"
source_cluster: "synthetic-source-lab"
source_cassandra_release: "5.0.x-record-exact-build"
source_schema_revision: "sha256:example"
partitioner: "org.apache.cassandra.dht.Murmur3Partitioner"
dc_replication:
  dc1: 3
snapshot_tag: "drill-20261121"
capture_started_utc: "2026-11-21T11:59:50Z"
capture_finished_utc: "2026-11-21T12:00:12Z"
tables:
  - name: "restore_lab.events_by_device_day"
    schema_object: "schema/restore_lab.cql"
    schema_sha256: "<replace with actual digest>"
nodes:
  - source_node_id: "lab-n1"
    host_id: "synthetic-host-id-1"
    dc: "dc1"
    token_ranges_manifest: "tokens/lab-n1.json"
    files_manifest: "files/lab-n1.json"
  - source_node_id: "lab-n2"
    host_id: "synthetic-host-id-2"
    dc: "dc1"
    token_ranges_manifest: "tokens/lab-n2.json"
    files_manifest: "files/lab-n2.json"
  - source_node_id: "lab-n3"
    host_id: "synthetic-host-id-3"
    dc: "dc1"
    token_ranges_manifest: "tokens/lab-n3.json"
    files_manifest: "files/lab-n3.json"
encryption:
  method: "AES-256-GCM-example"
  key_reference: "alias/restore-test-key"
incremental_chain: []
commitlog_chain: []
fixture_ledger: "fixtures/expected-writes.jsonl"
uploader_version: "record-commit"
status: "SEALED_AFTER_VERIFICATION"
~~~

These fields represent a **custom backup metadata design**, not a file read natively by Cassandra. Placeholder values are invalid for real restores. For dual-region setups, store location, object version ID, storage account, retention/immutability, and encryption context per object.

### 5.3. Per-file manifest and SHA-256

Example:

~~~json
{
  "object": "backup/cass-.../lab-n1/restore_lab/events_by_device_day/ma-1-big-Data.db",
  "size_bytes": 17422389,
  "sha256": "<64 hex chars computed from actual bytes>",
  "sstable_descriptor": "ma-1-big",
  "source_host_id": "synthetic-host-id-1",
  "table_id": "<actual table UUID from source>",
  "uploaded_utc": "2026-11-21T12:03:10Z",
  "storage_version_id": "<actual immutable version id>"
}
~~~

**Checksums must be re-verified after download/decryption**, and manifest integrity protected via signatures/MACs, object immutability, or trusted hash anchors. Computing SHA-256 only on upload without re-hashing during restore misses corruption in download, merging, or storage gateways.

### 5.4. Watermarks and completeness

Separate four timestamps:

~~~text
snapshot_capture_completed_utc
all_nodes_uploaded_and_verified_utc
latest_incremental_sstable_uploaded_utc
latest_commitlog_segment_archived_and_verified_utc
~~~

None of these equals the **latest recoverable business write**. An archived segment might hold no mutations for the target table; a newly uploaded SSTable might cover only a different partition. Maintain marker writes / a fixture ledger to prove workload RPO and coverage.

### 5.5. Sealing and retention rules

Seal a backup set only when:

1. Source nodes/tables within scope are finalized.
2. Every object in the manifest is present with matching checksums.
3. Schema/UDT/index/role references and key references are accessible per policy.
4. Cassandra/SSTable version metadata and token/rack/DC placement are recorded.
5. Retention/immutability is applied so cleanup cannot delete it before the drill.
6. Any gaps are explicitly **recorded as FAIL/PARTIAL**, never silently narrowing scope.

If a snapshot ran while a node was Down, the manifest must record `MISSING_SOURCE_NODE`. Never assume RF3 guarantees full restore despite a missing node: replicas might have been out of sync or some writes only lived elsewhere; test actual recovery guarantees.

## 6. Choosing the right restore mechanism: streaming or local SSTables?

### 6.1. Cassandra-supported paths

| Path | When suitable | Why caution is needed |
|---|---|---|
| **`sstableloader`** | Load SSTables into a Cassandra cluster **with existing schema** and possibly different topology/tokens | Streams by token to target replicas; needs format/schema match, disk/network headroom, creds |
| **`nodetool refresh`** | **Compatible local SSTables** placed in the exact node table directory to load without restart | Must match table ID/layout/node; does not redistribute data across token ranges |
| **Offline node recovery / restore data directory** | Restoring a same-topology node from prepared files per runbook | System tables, host IDs, tokens, and commitlogs are hazardous across clusters |
| **Application-level replay/import** | Complete event log/source of truth exists to rebuild state via business logic | Does not preserve CQL timestamps/TTLs/deletes automatically; throughput/RPO pipeline-bound |

Choose the **restore use case** upfront: dropped table into a new cluster, lost node disk in an existing cluster, or full-DC loss. Identical snapshot files require vastly different operations and validation.

### 6.2. Why `sstableloader` often fits a fresh lab

Per Apache Cassandra docs, `sstableloader` reads SSTables from a directory whose parent folders specify keyspace/table and **streams data to natural replicas per target topology**, writing new SSTables; it does not clean up source files automatically.

~~~text
/srv/restore-input/
  restore_lab/
    events_by_device_day/
      ma-1-big-Data.db
      ma-1-big-Index.db
      ma-1-big-Statistics.db
      ma-1-big-TOC.txt
      ... complete components for each SSTable
~~~

On Cassandra 5.0, an example command shape:

~~~bash
# Run ONLY in the restore lab, from a controlled helper/host.
sstableloader --nodes 10.30.0.11 \
  /srv/restore-input/restore_lab/events_by_device_day
~~~

Beforehand: create compatible keyspace, tables, UDTs, and indexes; verify the target seed belongs strictly to the isolated lab; prepare credentials, TLS, ports, and internode streaming as needed. Check `sstableloader --help` for your version; some SSTable tools have constraints when Cassandra runs on **the tool's host** and must not share the live data directory. Safest practice runs the loader against a **read-only copy on a helper host** rather than live serving SSTables.

**Never run `sstableloader` across every replica's snapshot for the same keys without a plan:** snapshots from multiple replicas contain overlapping SSTables with potentially differing deletes/timestamps. The pipeline must plan source SSTable selection, repair/reconciliation, and data verification on the new topology; streaming success alone does not prove business state is right.

### 6.3. `nodetool refresh` is not a substitute for redistribution

`nodetool refresh <keyspace> <table>` expects SSTables placed inside **the target node's exact table directory** and makes Cassandra load them without restarting. It does not:

- Create missing schemas, UDTs, or roles.
- Automatically backfill token ranges belonging to other nodes.
- Turn node N1's backup into full replicas across N2/N3 on a new topology.
- Verify application-level correctness.

On a fresh cluster with different table IDs and token ranges, **copying directories directly and refreshing** can fail or yield missing/misplaced data. When drilling recovery of a dropped table into a new cluster, prefer a verified streaming/restore path over manipulating live data dirs.

### 6.4. Why not copy the `system` directory wholesale?

System tables carry node-local identity, peer membership, tokens, and schema state. Copying raw `system.local` from cluster A to B risks duplicate host IDs or broken membership. `system_auth` contains roles/grants governed by separate policies and requires compatible replication strategies and password handling on the new cluster. Keep these separate:

~~~text
Cluster identity/configuration: build fresh for restore environment
Application schema: recreate via versions/migrations and validated DDL
Application data SSTables: restore along approved path
Authentication/authorization: test separately, do not clone live env blindly
Commitlog/PITR: separate, node/schema/precision-aware
~~~

### 6.5. Dependency order for restoring schema/objects

In real CQL:

1. Keyspaces with replication strategies matching the restore lab and real DC names.
2. UDTs before tables using them; UDFs/UDAs only if genuinely required and allowed by security policy.
3. Base tables, columns, PKs, clustering, options, TTL/`gc_grace`, compression/compaction.
4. Data SSTables loaded per plan, never injecting raw data into system tables.
5. Indexes/SAI/materialized views: check release-specific support and rebuild behavior; never assume index snapshots work automatically on a new cluster.
6. Lab roles/grants/TLS; driver/service config.
7. Post-load repair/consistency and business verification as needed.

A `schema.cql` dumped for **one table** may omit UDTs, keyspace definitions, roles, or other dependencies. Never mark a restore PASS if the loader imported data yet indexes or app queries fail.

## 7. Mandatory preflight before automation runs

### 7.1. Independent target environment

Automation must enforce a **positive allowlist**, never relying on hostnames containing `test`:

| Gate | Example condition | On failure |
|---|---|---|
| Namespace / cluster ID | Exact platform-assigned restore-lab ID | **ABORT** |
| Cloud account / project | Dedicated non-prod account only | **ABORT** |
| Network egress | No route to production Cassandra cluster | **ABORT** |
| Credentials | Restore identity: read-only backup source, write lab DB | **ABORT** |
| Source data | Synthetic or approved privacy-sanitized snapshot | **ABORT** |
| Restore target | Empty/new table/volume with zero user data | **ABORT** |
| Version / schema | SSTable/driver/schema compatibility per matrix | Hold / rebuild test image |
| Capacity | Projected disk, memory, CPU, network, and quotas sufficient | Hold / scale |
| Evidence destination | Writable audit storage with retention | Hold; never run "blind" |
| Cleanup scope | Specific resource labels/`run_id`, finalizer | Disallow broad cleanup |

**Never put secrets in logs/manifests**, and never grant a CI job `DROP` on production just to reset test tables conveniently. Least privilege prevents an automation bug from becoming a data incident.

### 7.2. Target health check before loading

On the isolated Cassandra lab:

~~~bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
nodetool status
nodetool describecluster
nodetool info
nodetool tpstats
nodetool compactionstats
~~~

`nodetool status` shows the queried node's gossip view; query multiple nodes if membership/network is suspect. Verify DC/rack names against snitch, keyspace RF, schema agreement, disk headroom, native/internode ports, and TLS policy. An `UN` cluster does not prove schema, roles, or query success.

### 7.3. Checking source manifest and objects before restore

A file set passes initial checks when:

- `backup_set_id` exists, is sealed, and belongs to the expected source cluster.
- All node/table/file references are downloadable by the drill identity.
- Component sizes and checksums match after download/decryption.
- Effective DDL at backup time includes all dependencies.
- SSTable format is readable by the chosen target version; never assume downgrading 5.0 to 4.1 works.
- Plans exist for TTL, tombstones, per-node incrementals, and PITR chains if used.
- Expected fixture rows/versions/writes have clear timestamps and provenance.
- KMS decryption keys are active/authorized and lab truststores/certs are ready.

**If any component is missing:** classify as `PRECHECK_FAILED`—never load an incomplete set and blame Cassandra corruption. Log the object/version/checksum mismatch in the evidence report; never "auto-heal" by dropping the file from the manifest.

### 7.4. Resource budgets, rate limits, and windows

Restores can download GiBs/TiBs, write SSTables, build indexes, stream across nodes, trigger compaction, and consume disk. Define:

~~~text
Maximum concurrent drills per failure domain: 1 (example)
Per-job timeouts: provisioning, download, stream, validate, cleanup
Disk low watermark: per capacity plan (no magic 10% across all clusters)
Network egress budget: GB/run, MiB/s, approval for cross-region
KMS/API rate quotas: per provider
SSTableloader throughput/concurrency: bounded and monitored
Stop conditions: disk alert, checksum mismatch, schema failure,
                 target unhealthy, wrong target ID, lost audit sink
~~~

Never run cleanup to "free space" via `rm -rf` on an empty path variable or wildcard. Cleanup must target explicit resource IDs owned by the **exact `run_id`**, with dry-run and permission boundaries.

### 7.5. Selecting backups without trusting upload time alone

Suppose a nightly snapshot finishes uploading at 00:15Z, yet contains SSTables captured between 00:00–00:05Z. If the disaster cut is 01:00Z:

- `upload_finished_utc=00:15Z` proves only when artifacts arrived in remote storage.
- Restored data likely lacks writes after the snapshot cut.
- RPO is not 45 minutes just from `01:00 - 00:15`; evaluate actual recoverable mutations.
- With incrementals/commitlogs, watermarks are valid only when **the chain is complete** and late-write/TTL semantics are checked.

Define a clear selection policy: latest **sealed + verified** set meeting location, schema, KMS, version, and coverage constraints; never pick the "newest file" merely by object timestamp.

## 8. End-to-end stateful restore drill pipeline

### 8.1. Architecture of a single drill

~~~mermaid
flowchart TD
    A["Scheduled trigger / approved request"] --> B["Allocate unique run_id + lease"]
    B --> C{"Isolated target and credentials verified?"}
    C -->|No| X["FAIL + evidence, no destructive action"]
    C -->|Yes| D["Select sealed backup set"]
    D --> E["Download/decrypt/verify all SSTable files"]
    E --> F["Provision restore lab + apply schema"]
    F --> G["Restore via approved loader or local path"]
    G --> H["Cassandra health + schema validation"]
    H --> I["CQL data/TTL/delete/integrity validation"]
    I --> J["Java app + role/TLS/consistency tests"]
    J --> K{"RPO/RTO and coverage pass?"}
    K -->|Yes| L["PASS report + immutable evidence"]
    K -->|No| X
    L --> M["Bounded cleanup with run_id"]
    X --> M
~~~

**The workflow must fail closed:** missing credentials, incomplete files, bad schema, or mismatched target cluster ID halts execution. Always record a terminal state (`PASS`/`FAIL`/`BLOCKED`/`ABORTED`) with root-cause evidence; never report "green" when tests were skipped.

### 8.2. Phases and exit gates

| Phase | Input | Output/evidence | Gate to advance |
|---|---|---|---|
| SELECT | Policy, backup index | `backup_set_id` + source manifest | SEALED + within retention |
| PRECHECK | Target ID, identity, schema/version | Allowlist and access attestations | PASS |
| DOWNLOAD | Object versions + KMS | Download logs, bytes, hashes | 100% manifest files verified |
| PROVISION | Version, DC/RF/topology | Cluster IDs, node status, resources | Schema/quorum prerequisites |
| LOAD | Complete SSTable input | Loader logs, bytes, duration, errors | Streaming success, zero missing files |
| DATA_CHECK | Fixture ledger, CQL | Per-table/key assertions | Accurate rows/cells/TTL/deletes |
| APP_CHECK | Java release, auth/TLS | API/Driver attempts and results | Required contract PASS |
| REPORT | UTC timestamps, metrics | Signed result with links | Valid RPO/RTO + coverage |
| CLEANUP | Resource IDs of run | Destruction audit of lab only | No stale credentials/resources |

**Measure every phase with UTC wall clock and monotonic duration.** Long Java/retry durations cannot be computed by subtracting unsynchronized UTC clocks across two hosts without checking skew. Outage timing starts at `T0` per the drill contract, not when the loader starts.

### 8.3. State machine preventing false PASS

~~~text
NEW
 -> PRECHECKED
 -> ARTIFACTS_VERIFIED
 -> TARGET_READY
 -> DATA_LOADED
 -> DATA_VERIFIED
 -> APP_VERIFIED
 -> REPORT_SEALED
 -> CLEANED

Any state -> FAILED / ABORTED / BLOCKED
  with reason, evidence, owner, remediation
~~~

Disallow transitions like `TARGET_READY → REPORT_SEALED`, and never mark `PASS` merely because `sstableloader` exited 0. Cleanup can fail even when restore passes; emit `RESTORE_PASS_CLEANUP_FAIL` so resource or credential leaks are not hidden.

### 8.4. At-least-once execution and idempotency

Orchestrators may retry jobs after network glitches or pod restarts. Restore workflows need:

- Unique `run_id` and per-environment / per-backup-set **lease/lock**.
- Phase checkpoints, hashed inputs, and durable state independent of pod memory.
- Idempotent artifact fetching/checksumming; never overwrite sealed object versions.
- Target schema/tables created **only if the environment ID matches** and no user data exists.
- Never blindly run `sstableloader` twice over the same data without understanding duplicate/timestamp effects; retrying LOAD may require provisioning a **fresh isolated target** instead of "streaming again."
- Network retries with exponential backoff, capped attempts, and deadlines; schema errors, checksum mismatches, or revoked KMS keys must fail fast.
- `finally` cleanup touches only resources tagged/owned by `run_id` and never deletes evidence.

### 8.5. Standardizing logs and correlation

Example JSONL event:

~~~json
{
  "run_id": "drill-20261121-a",
  "phase": "DATA_LOADED",
  "event_time_utc": "2026-11-21T12:12:17Z",
  "duration_ms": 143000,
  "backup_set_id": "cass-restore-lab-20261121T120000Z",
  "target_cluster_id": "isolated-drill-a",
  "result": "PASS",
  "files_verified": 128,
  "bytes_loaded": 2304104448,
  "evidence_uri": "audit://restore-drills/drill-20261121-a/loader.json"
}
~~~

In real implementations, `audit://...` is an **illustrative internal URI**. Never log raw passwords, tokens, KMS plaintext, sensitive hostnames, or row payloads in events. Every metric needs units, source, UTC window, and scope (node/table/DC).

## 9. Single-table lab: restorable with accurate read-back

### 9.1. Preparing synthetic data

On an isolated source lab Cassandra cluster (actual datacenter name `dc1`) only, create:

~~~sql
CREATE KEYSPACE IF NOT EXISTS restore_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS restore_lab.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    revision int,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

If the lab has only **one node**, create a dedicated keyspace with RF1 and explicitly note **RF3 recoverability was not tested**. Never create RF3 on a one-node lab, run `LOCAL_QUORUM`, and blame timeouts on backups.

Fixture:

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO restore_lab.events_by_device_day
  (device_id,event_day,event_time,event_id,event_type,payload,revision)
VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21','2026-11-21T10:00:00Z',
  22222222-2222-4222-8222-222222222222,
  'created','fixture-a',1
);

INSERT INTO restore_lab.events_by_device_day
  (device_id,event_day,event_time,event_id,event_type,payload,revision)
VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21','2026-11-21T10:01:00Z',
  33333333-3333-4333-8333-333333333333,
  'confirmed','fixture-b',2
);
~~~

Maintain an operation ledger recording UTC ACKs for every write, PK, revision, payload hash, and CQL timestamp/TTL policy—not just "inserted two rows." For RPO testing, add boundary writes **before and after the snapshot cut** with explicit expected inclusion/exclusion.

### 9.2. Snapshot every node in scope

The orchestrator invokes on **each lab node** (e.g., N1, N2, N3) with one tag:

~~~bash
# Run once on EACH source node in the isolated lab.
nodetool snapshot --tag drill-20261121 \
  --table events_by_device_day restore_lab
nodetool listsnapshots
~~~

Outputs must record per-node timestamps, table ID paths, file lists from `manifest.json`/directory, checksums/hashes, source host ID/DC, sizes, and upload confirmations. Never copy a snapshot from one node and quietly label it "cluster-wide"; if intentionally demonstrating a single-replica restore, tag it `SINGLE_NODE_SCOPE`.

### 9.3. Export and seal backup artifacts

In an authorized backup agent environment:

1. Pull the file list for the exact **node/table** snapshot tag, never wildcarding across tags.
2. Copy components to a path **outside the data directory and on independent storage**; source hard links do not automatically become offsite backups.
3. Compute SHA-256 per file and aggregate per-node/per-table manifests.
4. Upload to object storage with object versioning, retention policies, and encryption.
5. Download samples/verify checksums; seal the set only once all required nodes/tables finish.
6. Preserve schema/migrations, config references, fixture ledger, backup script versions, and source restore metadata.

Example command **reading exported backup files**:

~~~bash
sha256sum /srv/export/drill-20261121/lab-n1/restore_lab/events_by_device_day/* 
~~~

This Linux command is illustrative, not the only method; it prints hashes per file in the directory. If subfolders or secrets exist, restrict strictly to the manifest's file list. Never log payload contents.

### 9.4. Provision the target cluster and schema

Spin up a fresh **isolated** cluster on the right Cassandra release, with lab-only networking and fresh credentials. Use **new** cluster name, host IDs, and tokens; never copy `system.local`/`system.peers` from source. Apply schema:

~~~sql
CREATE KEYSPACE IF NOT EXISTS restore_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS restore_lab.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    revision int,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

**Never** rely on `CREATE TABLE IF NOT EXISTS` as proof the schema matches: if the table exists with different columns or PK, the statement leaves it untouched. Diff exported DDL/UDTs/options against live table metadata before streaming.

### 9.5. Run the loader on a read-only copy

Once SSTable components match checksums and are staged in the right directory layout:

~~~bash
# Stage the source copy on a helper/lab host, NOT inside a live Cassandra data dir.
sstableloader --nodes 10.30.0.11 \
  /srv/restore-input/restore_lab/events_by_device_day
~~~

The command streams SSTables to target replicas per topology. When multiple source replicas hold overlapping keys, plan how to gather/merge timestamps and tombstones before invoking loaders; **never load duplicate copies arbitrarily** assuming zero duplicate effects.

Monitor `bytes transferred`, duration, streaming errors, target free disk, CPU/compaction, and node status. Exit code 0 proves the tool finished its requested streaming, **not that fixture data is right**.

### 9.6. Verify CQL by exact partition key

~~~sql
CONSISTENCY LOCAL_QUORUM;
SELECT event_time,event_id,event_type,payload,revision
FROM restore_lab.events_by_device_day
WHERE device_id=11111111-1111-4111-8111-111111111111
  AND event_day='2026-11-21'
LIMIT 20;
~~~

**Compare:** expected row count for the PK, event IDs, revisions, payload hashes, and TTL/deletes if applicable. Never run a full-table `SELECT COUNT(*) FROM restore_lab.events_by_device_day` as a mandatory check on large datasets, since Cassandra is not optimized for RDBMS-style full scans; rely on a fixture key catalog, partition-stratified sampling, and precomputed business aggregates.

After restoring, run a separate synthetic write/read **on the lab table** or a dedicated canary table to verify permissions and CL without corrupting the original fixtures. Cleanup removes only lab resources tagged with `run_id`, leaving source snapshots untouched.

## 10. Verifying data, TTLs, and Java connectivity post-restore

### 10.1. Multiple independent verification layers

| Layer | Check | Must not conclude |
|---|---|---|
| File | SHA-256, size, TOC, and SSTable components match | Rows are readable through Cassandra |
| Schema | Keyspace, table, PK, clustering, UDTs, indexes, role grants | SSTables finished loading |
| Cassandra | Node status, query success at CL, zero loader errors | Java service is ready |
| Data | Fixture PKs, revisions, deletes, TTLs, and checksums | All partitions/tenants are covered |
| Driver | `CqlSession`, TLS/auth/local DC, prepared statements, paging | End-to-end HTTP/API is healthy |
| Application | Read/write canary, serialization, business invariants | Full disaster scope is recovered |
| Operations | RPO/RTO, disk headroom, compaction/GC/network, alerts | Long-term stability under production load |

Never run an RDBMS-style `SELECT 1` to "test Cassandra readiness": CQL does not support that as a universal probe. Use a query targeting a known keyspace/table/sample key or an explicit health API with well-defined semantics.

### 10.2. Java Driver 4.x: test-runner verifier

Example in Java 17 with Driver 4.19. It accepts a `CqlSession` **preconfigured** with auth/TLS/local DC pointing to the restore lab and checks one partition; never hardcode production credentials or endpoints.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Duration;
import java.time.LocalDate;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public final class RestoreFixtureVerifier {
    private RestoreFixtureVerifier() {}

    record Expected(String type, String payload, int revision) {}

    public static void verify(CqlSession session) {
        UUID deviceId =
            UUID.fromString("11111111-1111-4111-8111-111111111111");
        LocalDate day = LocalDate.of(2026, 11, 21);
        Map<UUID, Expected> expected = Map.of(
            UUID.fromString("22222222-2222-4222-8222-222222222222"),
            new Expected("created", "fixture-a", 1),
            UUID.fromString("33333333-3333-4333-8333-333333333333"),
            new Expected("confirmed", "fixture-b", 2)
        );

        PreparedStatement ps = session.prepare(
            "SELECT event_id, event_type, payload, revision " +
            "FROM restore_lab.events_by_device_day " +
            "WHERE device_id=? AND event_day=? LIMIT 100");
        BoundStatement stmt = ps.bind(deviceId, day)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setTimeout(Duration.ofSeconds(5))
            .setIdempotent(true);

        List<Row> rows = session.execute(stmt).all();
        Map<UUID, Expected> observed = new HashMap<>();
        for (Row row : rows) {
            UUID id = row.getUuid("event_id");
            Expected value = new Expected(
                row.getString("event_type"),
                row.getString("payload"),
                row.getInt("revision"));
            if (observed.put(id, value) != null) {
                throw new IllegalStateException("Duplicate event_id");
            }
        }
        if (!expected.equals(observed)) {
            throw new IllegalStateException(
                "RESTORE_MISMATCH expected=" + expected.size() +
                " observed=" + observed.size());
        }
    }
}
~~~

**Code limitations:** uses `LIMIT 100` and two fixture IDs; does not replace sampling across millions of partitions. With real data, log **hashes/fingerprints and counts**, never raw payloads. Let exceptions propagate so CI fails; never swallow errors and return PASS. `LOCAL_QUORUM` works only when lab RF/DC and node availability permit.

### 10.3. Verifying TTL and tombstones in real time

When restoring a seven-day-old snapshot, a cell with a 1-day TTL **is already expired today**. Do not expect it to remain live merely because the snapshot held its bytes. TTL follows write timestamp/expiry metadata; restoring does not "reset TTL to 0" like a fresh INSERT.

Example fixture with TTL:

~~~sql
INSERT INTO restore_lab.events_by_device_day
 (device_id,event_day,event_time,event_id,event_type,payload,revision)
VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21','2026-11-21T10:05:00Z',
  44444444-4444-4444-8444-444444444444,
  'ephemeral','expires-in-lab',3
) USING TTL 3600;
~~~

In the live lab table:

~~~sql
SELECT event_id, TTL(payload), WRITETIME(payload)
FROM restore_lab.events_by_device_day
WHERE device_id=11111111-1111-4111-8111-111111111111
  AND event_day='2026-11-21'
LIMIT 20;
~~~

`TTL(payload)` shows **remaining seconds** per cell; `WRITETIME(payload)` reflects the CQL write timestamp (in microseconds per CQL semantics), not backup/upload time. Once a cell expires, queries may omit the row or column; **never turn `NULL` into "missing backup"** before checking expiration deadlines.

Tombstones must be preserved so deleted data does not resurrect from another replica. Mixing an old snapshot with other live replicas can create zombie data if tombstones purged past grace; **restore only into an isolated cluster with a recovery plan documenting timestamps and deletion history**. Never shorten `gc_grace_seconds` to speed up tests.

### 10.4. Checking data across a representative distribution, not just two rows

A production-like drill needs:

- **Positive samples:** rows/partitions expected to exist, checked by payload hash, revision, and operation ID.
- **Negative samples:** deleted rows and TTL-expired cells; queries must not return stale live data.
- **Boundary samples:** data before and after snapshot/PITR cuts, late writes, concurrent updates.
- **Wide/hot partitions:** p95/p99/max rows per partition and realistic paging.
- **Types:** collections, frozen UDTs, blobs, timestamps, and counters/LWTs if used; each has distinct semantics.
- **Indexes/materialized views:** real application queries and post-rebuild readiness.
- **Multi-DC:** local DC routing, RF/CL, and cross-DC visibility requirements.
- **Auth:** least-privilege role used by the Java application holds `SELECT`/`INSERT`/`UPDATE` only on intended targets.

Set sample sizes and acceptance gates upfront; report coverage (%) by partition/category. Never claim "all data is valid" from 100 samples in a multi-billion-row backup.

### 10.5. Do not test read consistency by picking a contact point

The Java Driver routes to coordinators via its load-balancing policy. Connecting to a seed host **does not force** queries to read directly from that host's local SSTables; the coordinator may contact other replicas. `ExecutionInfo.getCoordinator()` reveals only the coordinator, not which data replicas served each cell.

When proving replica convergence, use repair/integrity strategies or authorized sampled tracing—never spam `LOCAL_ONE` requests to one contact point and call it node-specific verification.

## 11. Automating restore drill schedules and blocking dangerous actions

### 11.1. Tiered schedules: checking files ≠ restoring

You do not need to spin up a cluster and stream terabytes every day to detect object corruption. Separate:

1. **Daily metadata/file checks:** backup job status, immutable objects, sampled or full checksums within budget, KMS reachability, manifest completeness, retention TTLs.
2. **Weekly table restore:** take a sealed backup set, apply schema, stream a synthetic/representative table, run CQL + Java verifiers.
3. **Monthly service restore:** multiple keyspaces, roles, app release, representative workload, real RPO/RTO.
4. **Quarterly PITR/negative drills:** commitlog chains, timestamp boundaries, missing files, wrong versions, unavailable KMS, and recovery failures.
5. **Annual regional DR exercise:** recovery in another failure domain, identity/key/infra independence, cross-team coordination.

Adjust cadence by tier/RPO: a service tolerating at most 5 minutes of data loss needs more frequent chain/replication verification. **Drill cadence** differs from **backup creation frequency**; never conflate the two settings.

### 11.2. Illustrative Kubernetes CronJob with safe `suspend`

**Reference** manifest only—do not enable without namespaces, images, service accounts, network policies, admission policies, and storage controls. `suspend: true` prevents the template from spawning jobs immediately:

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cassandra-restore-drill
  namespace: restore-drills
spec:
  schedule: "0 2 * * 0"
  timeZone: "Etc/UTC"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 3600
  suspend: true
  successfulJobsHistoryLimit: 2
  failedJobsHistoryLimit: 4
  jobTemplate:
    spec:
      backoffLimit: 0
      activeDeadlineSeconds: 14400
      ttlSecondsAfterFinished: 604800
      template:
        metadata:
          labels:
            app: cassandra-restore-drill
        spec:
          restartPolicy: Never
          serviceAccountName: restore-drill-runner
          containers:
            - name: restore-check
              image: registry.example.invalid/restore-drill@sha256:REPLACE
              command: ["/opt/drill/bin/run-isolated-restore"]
              args:
                - "--scope=synthetic-table"
                - "--target=isolated-restore-lab"
              resources:
                requests:
                  cpu: "500m"
                  memory: "1Gi"
                limits:
                  cpu: "2"
                  memory: "4Gi"
~~~

`registry.example.invalid` and `sha256:REPLACE` are **placeholders**, not real images. `timeZone` requires supported Kubernetes versions (e.g., 1.27+); verify against your cluster. `concurrencyPolicy: Forbid` prevents **two Jobs from the same CronJob** overlapping, **not** conflicts with other restore workflows or manual runs; enforce a separate distributed lock/lease per target/account. `ttlSecondsAfterFinished` cleans up Job objects afterward and **does not replace** cleaning up volumes, credentials, cloud resources, or archiving evidence off-cluster.

Never inject production KMS credentials via environment variables or plain YAML. Use approved workload identity/secret managers, namespace network isolation, egress allowlists, and read-only backup access. If creating/deleting target clusters is required, split permissions between orchestrator and worker; workers must never have rights to delete arbitrary namespaces.

### 11.3. Fail-closed orchestrator pseudocode

~~~text
function scheduled_restore_drill(policy):
    run_id = allocate_unique_run_id()
    lock = acquire_lease(policy.target_environment)
    if lock is missing:
        record BLOCKED: ANOTHER_DRILL_RUNNING; return

    try:
        assert policy.target_environment in approved_lab_ids
        assert network_and_account_isolation()
        assert not target_has_non_test_data()
        selected = select_latest_sealed_backup(policy.scope)
        verify_manifest_signature_and_access(selected)
        verify_schema_version_compatibility(selected, target_version)
        local_copy = download_with_integrity_verification(selected)
        target = provision_fresh_isolated_cluster(run_id)
        assert target.cluster_id == approved_target_id(run_id)
        apply_validated_schema_and_lab_roles(target)
        stream_approved_sstables(target, local_copy, bounded_concurrency)
        verify_cluster_ready_and_schema(target)
        verify_fixture_ledger_and_negative_cases(target)
        verify_java_workflows_with_lab_credentials(target)
        assert observed_rpo <= policy.rpo
        assert observed_rto <= policy.rto
        seal_report(PASS, evidence)
    catch error:
        seal_report(FAIL_OR_BLOCKED, reason, evidence_so_far)
        notify_owner()
    finally:
        cleanup_only_resources_labeled_with(run_id)
        audit_cleanup_result()
        release_lease(lock)
~~~

This is **design pseudocode**; crashes before `seal_report` require durable checkpoints, outbox/report finalizers, and separate cleanup failure handling. Avoid `catch: return PASS` patterns; runners must return failing exit codes to CI/schedulers on failure.

### 11.4. Distinguishing deadlines, retries, backoff, and remediable errors

| Error | Retry? | Rationale |
|---|---|---|
| Transient object-store 503 | Bounded + exponential backoff | May recover automatically |
| Throttling / KMS rate limit | Bounded, respecting quotas | Provider-dependent |
| SHA-256 mismatch | **Do not retry blindly and ignore**; investigate integrity | Possible corruption or tampering |
| Schema/SSTable version mismatch | Fail fast | Retrying does not fix compatibility |
| Insufficient disk | Hold/scale per policy | Retrying repeats outage |
| Wrong cluster/environment ID | ABORT immediately | Risk of writing to wrong target |
| Partial `sstableloader` run | Do not blindly re-stream | Provision fresh target or reviewed idempotent recovery |
| Missing restore key | BLOCKED, page security owner | Never disable encryption |
| Java test fails | FAIL data/app gate | Never skip tests to turn reports green |

### 11.5. Alerts and escalations

Create alerts for:

- **Missed drill:** no completed run within policy cadence.
- **Consecutive failures:** *n* consecutive FAILs or recurring error classes.
- **RPO/RTO breach:** actuals exceed targets even if restore succeeded.
- **Data correctness breach:** missing/wrong fixtures or TTL/delete mismatches.
- **Backup coverage gap:** missing node/table/object or unsealed recent backups.
- **Evidence incomplete:** audit sink or manifest signature unavailable.
- **Cleanup leak:** leftover restore volumes, namespaces, cloud instances, or tokens.

Never alert only when backup jobs fail: a job can succeed for months while restores remain broken. Dashboards should surface **last successful full restore verification** and **age of the most recent trustworthy drill**.

## 12. Recording auditable recovery evidence

### 12.1. Milestone-by-milestone evidence, not a single screenshot

| Evidence ID | Source | Required data | Question answered |
|---|---|---|---|
| EV-001 | Scheduler/lock | Run ID, trigger, owner, UTC, lease | Did the drill truly run or get skipped? |
| EV-002 | Backup index | `backup_set_id`, scope, sealed state | Were the right artifacts selected? |
| EV-003 | Manifest verification | File list, SHA-256, object versions, key reference | Are artifacts intact and readable? |
| EV-004 | Target inventory | Cluster ID, IP allowlist, version, RF/DC, config hash | Restored into the right isolated cluster? |
| EV-005 | Schema apply | DDL hash, UDT/indexes/table options, grants | Are schema and privileges accurate? |
| EV-006 | Streaming tool | Redacted commands, exit status, bytes, duration, errors | How much did the tool load? |
| EV-007 | Cassandra state | `status`, JMX/GC/compaction, schema agreement | Is target healthy enough to verify? |
| EV-008 | CQL verifier | Hashed fixture IDs, row versions, TTL/deletes, CL | Is the data accurate? |
| EV-009 | Java integration | Driver version, local DC, TLS/auth, prepared CQL, outcomes | Can applications access it? |
| EV-010 | RPO/RTO report | T0/T5/T6, latest recoverable write, coverage | Are DR targets met? |
| EV-011 | Cleanup audit | Resource IDs/labels, revoked credentials | Did the drill leave residual risk? |

**Tie all evidence to the same `run_id` and `backup_set_id`.** A failed log parser or missing metrics must become `EVIDENCE_GAP`, never "N/A so PASS." Record clock sources and timestamp resolution (15s scrapes, millisecond logs, etc.).

### 12.2. Illustrative JSON report

~~~json
{
  "run_id": "drill-20261121-a",
  "status": "PASS",
  "backup_set_id": "cass-restore-lab-20261121T120000Z",
  "restore_scope": ["restore_lab.events_by_device_day"],
  "target_cluster_id": "isolated-drill-a",
  "source_cassandra_version": "5.0.x-example",
  "target_cassandra_version": "5.0.x-example",
  "start_utc": "2026-11-21T12:00:00Z",
  "service_recovered_utc": "2026-11-21T12:19:00Z",
  "rto_seconds": 1140,
  "rto_target_seconds": 1800,
  "rpo_upper_bound_seconds": 420,
  "rpo_target_seconds": 900,
  "fixtures_checked": 500,
  "fixtures_failed": 0,
  "negative_cases_checked": 40,
  "data_gate": "PASS",
  "app_gate": "PASS",
  "evidence": ["EV-001", "EV-002", "EV-003", "EV-004",
               "EV-005", "EV-006", "EV-007", "EV-008",
               "EV-009", "EV-010", "EV-011"],
  "cleanup_status": "PASS"
}
~~~

**These are hypothetical numbers** illustrating schema structure, not measurements from a real cluster. If a test has not run, status must be `NOT_EXECUTED`. If RPO comes from a sample ledger, report `rpo_upper_bound_seconds` with coverage/assumptions; never mix synthetic placeholders and real-run metrics in one report.

### 12.3. Report signing and validation rules

Protect reports/manifests with:

- SHA-256 hashes for artifacts, digital signatures, or tamper-evident storage.
- Immutable object version IDs and retention per audit policy.
- Trustworthy time source (UTC), plus service/version/build metadata.
- Test owner, approver, and the exact policy/thresholds used to judge PASS.
- Redaction policy: zero passwords, TLS private keys, PII, or raw user data.
- Separation of duties: separate roles create backups, read backups, execute restores, and review evidence.

Do not upload just a PDF screenshot reading "SUCCESS": it omits exact commands, source versions, fixture counts, schema hashes, and RPO/RTO; reports must drill down to raw evidence.

### 12.4. Separating phase outcomes

Example "halfway" result:

~~~yaml
run_id: drill-20261121-b
artifacts_verified: PASS
cluster_provisioned: PASS
sstable_streamed: PASS
schema_verified: PASS
fixture_verification: FAIL
java_app_verification: NOT_RUN
rpo_evaluation: NOT_EVALUABLE
rto_evaluation: NOT_EVALUABLE
overall_status: FAIL
reason: "event_id X restored with wrong revision"
~~~

In this case, never report "80% restore success"—investigate the wrong data. Earlier passing phases isolate the fault, **without softening a data-correctness FAIL**.

### 12.5. Watermarks of a healthy restore program

After each run, publish dashboard/trend metrics:

~~~text
last_verified_backup_set
last_verified_restore_utc
days_since_last_success
backup_coverage_percent_by_keyspace
manifest_file_verification_percent
restore_duration_p50/p95 (comparable scope only)
observed_rpo_by_service_tier
observed_rto_by_service_tier
data_invariant_failure_count
cleanup_failure_count
evidence_retention_expiry
~~~

Never lump RTO of restoring **one 1 GiB table** together with **an entire 20 TiB cluster** into one generic Cassandra p95. Report by service tier, scope, topology, and dataset size, recording *n* so sample counts remain meaningful.

### 12.6. When is "no errors seen" valid evidence?

Zero `ERROR` lines in loader logs does not prove 100% file integrity. Zero `ReadTimeoutException`s across 10 CQL reads does not prove quorum under production load. Zero `UNAVAILABLE` errors with one node up does not prove multi-DC DR. Use **absence of errors** only when coverage/sampling, log collection, and error counters are verified active—and pair it with **positive assertions** on data and app behavior.

## 13. Negative tests: proving the workflow stops and reports FAIL

### 13.1. Minimum test suite

| Fault injected **only into lab copy** | Expected outcome | Evidence |
|---|---|---|
| Delete one SSTable component from **copy** | Integrity gate FAILS before LOAD | Missing path + manifest diff |
| Flip one byte in `Data.db` in copy | SHA-256 mismatch, ABORT | Redacted expected/actual digests |
| KMS key access denied | BLOCKED; never disable encryption | KMS access error, no plaintext fallback |
| Schema PK/clustering differs from backup | `SCHEMA_MISMATCH`, no streaming | DDL hash + table metadata diff |
| Target version cannot read SSTable format | `COMPATIBILITY_FAILED` | Release/build + loader error |
| Upload snapshot of only one node under RF3 | `COVERAGE_FAILED` or partial-scope tag | Per-node/token manifest |
| Brief object-store 503 | Bounded retry, logged attempts; eventual PASS/FAIL | Backoff/elapsed/attempts |
| Target disk fills during LOAD | FAIL + stop stream, preserve evidence | Disk free, I/O errors, cleanup audit |
| Job killed mid-stream | Never PASS; retry handles partial target | Checkpoint + fresh target test |
| Java user lacks `SELECT` | `APP_AUTH_FAILED` | Role/grant and exception class |
| Wrong local DC in Driver | `APP_CONNECTIVITY_FAILED` | Driver config, node list, errors |
| Deleted data reappears | `DATA_INTEGRITY_FAILED` | Fixture/TTL/delete ledger |
| PITR target before/after mutation boundary | Includes and excludes per semantics | Write ledger + verified query |
| Evidence object store unwritable | `REPORT_FAILED`, overall not SUCCESS | Audit sink error |
| Cleanup quota/dangling resources | `RESTORE_PASS_CLEANUP_FAIL` | Resource IDs, owner, remediation |

Never modify original snapshots or encrypted objects in a production account to craft negative cases. Always **create an isolated synthetic copy**, and destroy resources by `run_id` afterward.

### 13.2. Prioritized failure checks

1. **Preflight failures** must block before provisioning/streaming: wrong target, missing KMS, checksums, schema/version.
2. **Load failures** must never report success: disk full, network partition, loader timeout, budget exceeded.
3. **Data failures** are hard blockers: wrong revision, missing partition, resurrected delete, broken TTL semantics.
4. **App failures** block service readiness: TLS, auth/grants, prepared CQL, codecs, consistency.
5. **Reporting/cleanup failures** must surface clearly, never masked by earlier passing phases.

When a command exits non-zero, save redacted stderr with exit code and UTC timestamp; when killed without an exit code, report `UNKNOWN_PROCESS_OUTCOME` and reconcile target/stream state. Never "retry until PASS" on the same data dir after a partial restore lacking idempotency guarantees.

### 13.3. Difference between negative testing and destroying data

For example, "deleting an SSTable component" happens **only inside the drill's staging copy**, after confirming the immutable source backup remains intact. Corruption tests can use a **tool-generated fake fixture file** instead of editing a real SSTable, as long as the real parser/checksum gate is exercised.

Running `nodetool clearsnapshot` or deleting source backups is not a safe way to test backup deletion resilience without planning and approval. To test retention/legal-hold behavior, use a separate lab bucket with object lock/versioning—never the account storing production backups.

### 13.4. Key PITR boundary tests

In the lab, write a ledgered sequence:

~~~text
11:59:50Z  INSERT k1=v1, ACK at agreed CL
12:00:00Z  RESTORE_POINT_TARGET
12:00:10Z  UPDATE k1=v2, ACK
12:00:20Z  DELETE k2, ACK
12:00:25Z  UPDATE k3 USING TIMESTAMP older than k3 previous write
~~~

**Expected:** the 12:00 target retains mutations per cutoff semantics; post-cutoff values must **not** appear from improper replay, while pre-cutoff writes in the base snapshot may remain. Out-of-order client timestamps can diverge from arrival-order expectations; design fixtures tracking **event time, write timestamp, arrival time, and snapshot capture time** separately.

A genuine PITR test requires:

- Base snapshots and commitlog segments mapped by source node/format in a continuous chain.
- Restore scripts/config and precision matching the Cassandra version.
- Never using arbitrary client-supplied timestamps to claim exact PITR precision.
- Independent read-back before/after target plus negative samples.
- Never promising atomic consistency across partitions/tables when the app lacks transaction barriers.

If a drill includes only snapshots without a commitlog archive chain, record `PITR_NOT_CONFIGURED` rather than PITR PASS. More frequent snapshots tighten RPO, yet do not turn snapshots into a point-in-time transaction log.

### 13.5. Production-derived test data requires explicit authorization

If testing production-derived backups is permitted, assess:

- PII, regulated data, and tenant isolation; masking can alter SSTable contents/PK distribution.
- Encryption at rest/in transit, scoped KMS, storage access audits.
- Output logs/traces containing only hashes, zero sensitive query bind values.
- Independent data retention/cleanup per approved lifetime.
- Organizational compliance/legal rules; never move data to unauthorized regions.

Default to **synthetic backups**, or production backups de-identified through an approved, verified process. Never treat a raw hash of a guessable user ID as sufficient privacy protection.

## 14. Security, access control, and backup lifecycle

### 14.1. Two privilege axes: backup and restore

| Actor | Required permissions | Must not hold |
|---|---|---|
| Backup agent | Read local snapshots, upload to exact backup prefix | `DROP` keyspace, read unrelated secrets |
| Restore scheduler | Read metadata, create runs/locks | Native CQL production mutations |
| Restore worker | Read-only sealed backup objects, KMS decrypt, write lab cluster | Delete source backups, cloud account root |
| Schema migrator | `CREATE`/`ALTER` inside lab restore namespace | `ALTER` production schemas |
| Verifier | `SELECT`/limited canary writes in lab | Unrestricted admin data export |
| Evidence writer | Append/write audit run prefix | Overwrite old reports, delete retention objects |
| Cleanup agent | Delete resources tagged `run_id` in lab | List/delete arbitrary projects/clusters |

**Backup object encryption and database authentication are two separate layers.** Decrypting SSTables does not prove a Java user holds permissions. Conversely, a CQL superuser in the restore cluster does not automatically have permission to decrypt backup objects.

### 14.2. Testing key rotation and disaster independence

Safe KMS key rotation retains old key versions and lifecycle coverage; yet if a key is destroyed, intact backups become unreadable. Drill:

1. Record key alias/ID/version references for the backup set, never plaintext DEKs.
2. Verify the restore workload identity can decrypt under the exact context.
3. Test cross-account/region keys per DR policy without assuming source-region KMS stays up.
4. Audit decrypt events and revoke access post-job.
5. Test access denial **in a sandbox** and verify fail-closed behavior.

Never export private keys or DB passwords into backup manifests or test artifacts; redact all outputs before archiving reports.

### 14.3. Retention must protect restorability

Policies typically require:

- Immutable snapshot baselines and incremental/commitlog chains **never split apart**.
- Retention covering RPO, RTO, legal holds, and accidental-deletion detection windows.
- Local hard-link cleanup only after upload, verification, and retention rules pass.
- Deleting remote objects only once no backup sets depend on them, with full audit trails.
- Preserving manifest/schema/key references for the entire retention window.
- Testing restores of the **oldest supported backup**, not just the "latest."

If retention purges a baseline while keeping incrementals, the recovery path breaks. Conversely, restoring a months-old backup to the present can surface expired TTLs, tombstones, or sensitive records; verify business/legal semantics before serving restored data.

### 14.4. Testing region/zone mobility

A cross-AZ/region DR test must document:

~~~text
source and target failure domains
independent object-store location / immutable version
independent KMS recovery path
new cluster network endpoints, DNS, certificates, truststores
RF/DC strategy and Java Driver local DC
inter-DC streaming/network quotas
schema/roles/secrets availability
manual approvals and audit trail
~~~

If source and target share a failure domain or network identity, record scope `SAME_REGION_RESTORE` instead of `REGIONAL_DR_VALIDATED`.

## 15. Operational scenarios and evaluating outcomes

### 15.1. Case A — Complete backup files, yet restore fails

**Context:** a single-table snapshot runs at 00:00Z, uploads by 00:10Z, and passes manifest checks. When provisioning the target cluster, the loader rejects the SSTable version: target runs Cassandra 4.1 while source ran 5.0.

**Analysis:**

1. Compare exact versions, SSTable formats, and JDK/driver compatibility; never label an unsupported downgrade as backup corruption.
2. Provision a compatible Cassandra release or follow a verified migration strategy.
3. Record `COMPATIBILITY_FAILED`, source/target versions, and loader logs in evidence.
4. Retest on a **fresh target**; never patch production directly.

**Key takeaway:** backup integrity and restore compatibility are separate gates. A 100% hash match does not guarantee a different target version can read the SSTables.

### 15.2. Case B — Streaming completes, yet the Java service still errors

**Context:** `sstableloader` exits 0 and admin `cqlsh` `SELECT` finds fixtures, yet the Java Driver throws `UnauthorizedException` or fails TLS handshakes.

**Analysis:**

- Schema/data likely succeeded at admin level while **application readiness FAILED**.
- Check roles/grants, `system_auth` recovery plan, secret manager, client truststores/server certs, and local DC.
- Distinguish `UnauthorizedException` (CQL authz) from `SSLHandshakeException` (TLS); never retry blindly or disable TLS verification.
- Report `DATA_PASS_APP_FAIL`; service RTO is not met until the app path works.

**Key takeaway:** the application contract spans schema, credentials, driver profiles, consistency, codecs, and query shapes—not just SSTables.

### 15.3. Case C — Latest backup passes, yet RPO fails targets

**Hypothetical context:** business requires a 10-minute RPO. Snapshot completes at 12:00Z, upload finishes at 12:05Z. Disaster hits at 12:45Z; no incrementals or commitlog archives exist. Snapshot restore recovers writes only up to 12:00Z.

**Analysis:**

- The backup pipeline may match its design, yet **RPO policy FAILS**.
- Never use `upload_time=12:05Z` as the latest recoverable write.
- Increase trustworthy snapshot cadence or implement incremental/commitlog capture—and test the real chain.
- Distinguish replication availability from historical snapshot recovery after accidental deletion.

**Key takeaway:** RPO is an architectural and tested guarantee, not something fixed on a dashboard by picking a flattering timestamp.

### 15.4. Case D — Single table restored, yet multiple APIs return wrong results

**Context:** table `events_by_device_day` is restored; other endpoints query secondary indexes/SAI, materialized views, UDTs, or separate denormalized tables.

**Analysis:**

1. Inspect the schema dependency graph and query fingerprints across all endpoints.
2. Recognize that restoring **one table** does not equal restoring **one service**.
3. Test index rebuild/query readiness and separately written projection/denormalized tables.
4. Record `RLO: TABLE_ONLY`; never label the whole service recovered.

**Key takeaway:** Cassandra models data by query; a single business flow can span multiple tables serving distinct query shapes.

### 15.5. Case E — Restoring an old backup causes TTL/deletion skew

**Context:** a 10-day-old snapshot holds records with a 7-day TTL and records deleted after the snapshot. Restored today, the app expects current state.

**Analysis:**

- Per-cell TTLs may cause expired records to **disappear** today; that is not a loader bug.
- For records deleted post-snapshot, restoring the pre-delete state may be **right for point-in-time recovery** yet wrong for "current state."
- Mixing old snapshots with live replicas risks timestamp/tombstone skew and zombie data.
- Define the restore target time and business recovery invariants, considering event replay or deletion ledgers.

**Key takeaway:** verify data against **expected state at the recovery point**, not always latest production.

### 15.6. Case F — RTO spikes sharply at realistic data scale

**Context:** last week restoring a 1 GiB table took 3 minutes; today restoring a 5 TiB keyspace cross-region hits a 1 Gbit/s egress cap and saturates target compaction.

**Analysis:**

1. Benchmark scope, bytes, network, CPU, and disk per drill; never compare RTOs across mismatched scales.
2. Estimate the **lower bound** of transfer time from bytes and bandwidth alone: `5 TiB / 1 Gbit/s` takes many hours or days before overhead.
3. Report effective throughput, per-phase timings, and bottlenecks.
4. Tune parallelism, compression, snapshot sharding, index rebuilds, and capacity without raising concurrency unboundedly.

**Key takeaway:** RTO must be tested at **representative scale**; restoring a tiny fixture does not prove large datasets meet SLO.

### 15.7. Rules for publishing results

| Situation | Accurate report | Never report |
|---|---|---|
| Blocked by preflight failure | `BLOCKED` with reason | `PASS` |
| Download and checksums PASS, not yet loaded | `BACKUP_VERIFIED_ONLY` | `RESTORE_VERIFIED` |
| Loader PASS, data FAIL | `DATA_INTEGRITY_FAIL` | Unexplained `PARTIAL_PASS` |
| Data PASS, Java FAIL | `DATA_PASS_APP_FAIL` | `SERVICE_RESTORED` |
| Data/app PASS, RPO breached | `RESTORE_WORKED_RPO_FAIL` | `DR_SLO_PASS` |
| RPO/RTO PASS, cleanup fails | `RESTORE_PASS_CLEANUP_FAIL` | `ALL_PASS` |
| All gates PASS, evidence sealed | `RESTORE_VERIFIED` | "All failure modes guaranteed" |

## 16. Exercises and self-assessment questions

### Exercise 1 — Does a green backup prove restorability?

A dashboard shows 100% snapshot/upload job success for 90 days, with zero loader or Java tests run.

**Answer:** No. It proves only part of the backup pipeline. Restore into an isolated cluster and verify data, app paths, RPO, and RTO.

### Exercise 2 — Snapshot still sitting on node disk

An operator sees `snapshots/<tag>` on the Cassandra volume with no offsite copy. A disk dies.

**Answer:** Hard links on the same filesystem perish with the disk; export and verify an independent copy across failure domains with retention and key access.

### Exercise 3 — Does one node's snapshot cover RF3?

In an RF3 cluster across multiple token ranges, N1 has a snapshot while N2/N3 do not. Can we report a full cluster backup?

**Answer:** Not automatically. Coverage by node/table/token is required; replicas may diverge or N1 may not own every token range. Record partial scope.

### Exercise 4 — Snapshots with `--skip-flush`

An acknowledged write sits in a memtable; the job runs `nodetool snapshot --skip-flush`.

**Answer:** The snapshot can miss writes not yet flushed to SSTables; verify flush semantics and RPO bounds. Without commitlog archiving, memtable contents are excluded.

### Exercise 5 — Measuring RTO incorrectly

A team reports a 2-minute RTO from `sstableloader` start to exit, while provisioning and Java tests add 20 minutes.

**Answer:** Measure per the recovery contract from `T0` to service readiness/validation gates; report per-phase durations without calling 2 minutes the service RTO.

### Exercise 6 — Do incremental backups include commitlogs?

A team enables `incremental_backups: true` expecting to replay every mutation prior to memtable flush.

**Answer:** No. Incremental backups hard-link SSTables after flush/stream; PITR mutations require commitlog archiving and real chain testing.

### Exercise 7 — Choosing the restore path

A new cluster has different token ranges and table IDs from source. Should raw SSTables be copied into live data dirs and refreshed via `nodetool refresh`?

**Answer:** Not by default. `sstableloader` is usually more appropriate to stream to natural replicas of the new topology. `refresh` expects local SSTables placed in matching node/table layouts with matching schema.

### Exercise 8 — Checksums match, schema differs

All manifest SHA-256 hashes match, yet the target table has a different clustering order/PK.

**Answer:** `SCHEMA_MISMATCH`; fail before LOAD. File integrity does not guarantee CQL compatibility.

### Exercise 9 — Nodes are `UN`, so is the app ready?

All nodes in the restore cluster are `UN`, yet the Java user gets permission errors on `SELECT`.

**Answer:** No. App readiness FAILS; verify auth, TLS, local DC, prepared CQL, and business transactions.

### Exercise 10 — Does restoring "reset" TTLs?

A row with a 24-hour TTL sits in a 7-day-old snapshot restored today.

**Answer:** TTL metadata does not reset to restore time; the cell may already be expired. Validate against expected state at recovery time.

### Exercise 11 — Counter timeouts after PITR

A client increments a counter, times out, and retries; backup/commitlog replay yields an unexpected total.

**Answer:** Timeouts have unknown outcomes, and counters are not idempotent like regular cell sets. Check operation ledgers and write/replay semantics; never arbitrarily replay counter increments.

### Exercise 12 — KMS key revoked

Backup objects are readable, yet decryption fails; the team proposes turning off encryption.

**Answer:** No. Mark `BLOCKED/FAIL`; follow key recovery/rotation and audit procedures. Never weaken security to force a green test.

### Exercise 13 — Overconfident PITR timestamp

An app writes with out-of-order client timestamps, yet the team claims cutting at 12:00Z restores an atomic cross-table transaction state.

**Answer:** No. PITR replay follows timestamp/segment semantics, and Cassandra has no global wall-clock transaction cut across tables. Use application barriers and validate boundary fixtures.

### Exercise 14 — Flipping one byte in staging backup

Checksum mismatch fires after fault injection on a **backup copy** of an SSTable. The runner streams anyway because 99% of files are intact.

**Answer:** FAIL/`PRECHECK_FAILED`; never silently skip components to report recovery success. Halting is the whole point of the negative test.

### Exercise 15 — Service PASS, cleanup failed

CQL and Java tests PASS, yet the lab namespace, KMS grant, or volume remains behind.

**Answer:** Report `RESTORE_PASS_CLEANUP_FAIL` separately and resolve leftover resources/credentials with the owner rather than calling it all-green.

### Exercise 16 — Using one fixture for cluster-wide RPO

Out of 10 million rows, the team checks two rows, sees the latest ACK at 11:59Z (disaster 12:00Z), and claims a guaranteed 1-minute RPO.

**Answer:** Insufficient. Report sample coverage and uncertainty; use token/partition-stratified evidence and verified backup-chain completeness to support any claimed scope.

### Checklist before accepting a drill

- [ ] Source cluster, target lab cluster ID, and Cassandra/JDK/Driver versions recorded.
- [ ] Owner, `run_id`, `backup_set_id`, UTC window, and anti-overlap lease in place.
- [ ] Target belongs to a non-prod allowlist with zero network path to write native production Cassandra.
- [ ] Synthetic/authorized data source, protected credentials/keys, and audit logging enabled.
- [ ] Schema, UDTs, indexes, auth/roles, and app release versioned in manifest.
- [ ] Snapshots cover all source nodes/tables/token ranges in the declared scope.
- [ ] SSTable components, sizes, SHA-256 hashes, and manifest signatures verified post-download.
- [ ] Incremental/commitlog chains (if used) have complete segments and verified watermarks.
- [ ] All required keys/key versions can decrypt inside the recovery domain.
- [ ] Loader/refresh matches topology/format; never copy `system.local`/peers across clusters.
- [ ] CQL tests target exact partition keys, avoiding full-table `COUNT(*)` on large datasets.
- [ ] Positive/negative records, TTL/tombstones, latest/older writes, and LWT/counters (if used) verified.
- [ ] Java Driver verifies CL, local DC, TLS/auth, prepared queries, and serialization.
- [ ] RPO measured from the latest **verified recoverable business write** with stated coverage.
- [ ] RTO measured from DR start per contract to app/data readiness, including per-phase durations.
- [ ] Target disk, GC, compaction, network, and errors monitored under representative load.
- [ ] At least one negative test proves fail-closed behavior without silently dropping files.
- [ ] PASS/FAIL/BLOCKED reports rely strictly on real gates, never assumptions.
- [ ] Evidence sealed with checksums, retention, links, and owner, containing zero secrets or PII.
- [ ] Cleanup deletes only `run_id`-scoped resources, alerting an owner if cleanup fails.
- [ ] Drill cadence, age since last PASS, and remediations actively tracked.

## 17. References

1. Apache Cassandra — [Backups](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/backups.html): snapshots, incremental backups, hard links, `schema.cql`, and restore paths.
2. Apache Cassandra — [nodetool snapshot](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/snapshot.html): tags, table/keyspace scope, `--skip-flush`, and limitations.
3. Apache Cassandra — [nodetool listsnapshots](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/listsnapshots.html): inspecting snapshot lists and distinguishing on-disk vs. true size.
4. Apache Cassandra — [nodetool refresh](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/refresh.html): loading local SSTables placed on a node in compatible layouts.
5. Apache Cassandra — [sstableloader](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/sstable/sstableloader.html): streaming SSTables to a target cluster per topology, input directory naming, `--nodes`, and streaming/TLS options.
6. Apache Cassandra — [commitlog-archiving.properties](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_cl_archive_file.html): archive/restore commands, restore directories, point-in-time targets, and timestamp precision.
7. Apache Cassandra — [cassandra.yaml configuration](https://cassandra.apache.org/doc/latest/cassandra/managing/configuration/cass_yaml_file.html): `incremental_backups`, `auto_snapshot`, `snapshot_before_compaction`, commitlog, and storage options.
8. Apache Cassandra — [SSTable tools](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/sstable/index.html): offline tools and safety preconditions.
9. Apache Cassandra — [Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): anti-entropy, differences from backup, overhead, and scope.
10. Apache Cassandra — [Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html): TTLs, deletion markers, grace, and zombie data risks.
11. Apache Cassandra — [Monitoring](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html): table, client request, compaction, and disk metrics during restores.
12. Apache Cassandra — [CQL DDL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html) and [CQL DML](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `NetworkTopologyStrategy`, primary keys, TTLs, timestamps, and read/write semantics.
13. Apache Cassandra Java Driver 4.19 — [Configuration](https://apache.github.io/cassandra-java-driver/4.19.0/core/configuration/): driver profiles, local datacenter, request timeouts, and TLS/auth patterns.
14. Apache Cassandra Java Driver 4.19 — [Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/): prepared/bound statements, consistency, timeouts, and idempotency.
15. Apache Cassandra Java Driver 4.19 — [Paging](https://apache.github.io/cassandra-java-driver/4.19.0/core/paging/): consuming `ResultSet`s and actual page counts.
16. Kubernetes — [CronJobs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/): schedules/timezones, `concurrencyPolicy`, `suspend`, `startingDeadlineSeconds` for Kubernetes orchestration.

**Conclusion:** "Having backups" is only the starting point. Periodic restore testing must prove a backup can reconstruct **accurate schemas, data, and application access paths** in an isolated environment **within committed RPO/RTO**, backed by immutable evidence and safe halt procedures whenever any gate fails. Every `PASS` notice must stay bound to its **scope, version, `backup_set_id`, `run_id`, and verification conditions**—never extrapolate restoring one synthetic table into a guarantee of full-cluster recovery.
