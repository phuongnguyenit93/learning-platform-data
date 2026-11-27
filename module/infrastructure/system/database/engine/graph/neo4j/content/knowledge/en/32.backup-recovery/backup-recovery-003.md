# Offline Dump and Load Using the Tooling of Your Installed Version

## 1. Why Must You Know the Exact Version Before Dumping/Loading?

When operating Neo4j, administrators may need to copy a database to a testing environment, save a snapshot before a major change, or restore a database from an archive file. Two commonly used commands are **dump** (packaging a database into an archive) and **load** (loading an archive back into a database). However, **command names, arguments, database-stop requirements, and database registration methods change across versions and editions**.

A guide written for Neo4j 4.4 using `neo4j-admin dump` cannot be copied verbatim to Neo4j 5 or Neo4j 2025–2026, where the tools are grouped under `neo4j-admin database dump`. Similarly, 4.4's `--from` differs from `--from-path` in newer releases; overwrite flags and cluster handling also differ. Using the wrong syntax or procedure can cause unintended downtime, overwrite the wrong database, or create an inconsistent state.

This lesson belongs to the **Backup and Recovery** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. It covers procedures suitable for property graphs containing nodes, relationships, indexes, constraints, and data created by Cypher, the Neo4j Java Driver, or Spring Data Neo4j applications.

**Learning objectives:**

1. Distinguish **offline dump/load**, online backup/restore, and logical data exports.
2. Check your installed version and identify the `neo4j-admin` syntax matching your runtime environment.
3. Perform a controlled dump/load workflow on an **isolated test database**.
4. Understand archive limitations regarding `system`, users/roles, configuration, extensions, and clusters.
5. Reconcile data integrity using deterministic Cypher verification checks after recovery.
6. Write an operational runbook with success criteria, rollback plan, RPO, and RTO.

> **Operational warning:** Shell blocks in this lesson are **templates to study and adapt in a lab**; never run them directly in production. `neo4j stop` interrupts service, and `--overwrite-destination=true` can replace target data. Never run destructive or overwriting commands without approval, a verified recoverable copy, and confirmation of the exact target database/instance.

## 2. Four Operations That Sound Similar But Are Not Equivalent

| Operation | Tool or mechanism | Database state | Output/meaning |
|---|---|---|---|
| **Dump** | `neo4j-admin database dump` in Neo4j 5+ | Source database **must not be mounted/running** | Dump archive of the full contents of one database |
| **Load** | `neo4j-admin database load` in Neo4j 5+ | Target database **must not be mounted/running** when replacing | Converts the archive into the target database store |
| **Online backup** | `neo4j-admin database backup`, Enterprise feature in supported versions | Source database is online | Backup artifact; can support full/differential and dedicated metadata policies |
| **Logical export** | Cypher, APOC export, or Java application | Can run online depending on approach | CSV/JSON/Cypher; **not automatically equivalent** to a store dump |

**Dump is not a Cypher statement.** It is a `neo4j-admin` CLI command run in an environment with access to the required database files. Java Driver and Spring Data Neo4j do not turn an arbitrary `CALL` into a physical dump.

**Dump is not a standard online backup.** When the application must keep writing, use an online backup approach supported by your edition or schedule a maintenance window long enough for the database to be truly offline. Copying the database directory via file copy while Neo4j is running is **not** a supported backup method.

**Load is not CSV import.** `neo4j-admin database import` creates a database from CSV/Parquet records via an import pipeline; `database load` restores an archive format produced by a valid dump/backup. Never confuse the two commands.

## 3. Lifecycle Diagram of a Dump/Load Run

~~~mermaid
flowchart TD
    A["Verify version, edition, and source database"] --> B["Record baseline: nodes, relationships, constraints, business data"]
    B --> C["Stop source database / transition to appropriate offline state"]
    C --> D["neo4j-admin database dump → archive"]
    D --> E["Verify exit code, size, permissions, checksum, and metadata"]
    E --> F["Transfer archive to isolated recovery instance"]
    F --> G["Ensure target database is offline with no unintended overwrite"]
    G --> H["neo4j-admin database load"]
    H --> I["Start / register database per edition and scenario"]
    I --> J["Compare baseline, schema, Java Driver/SDN functionality"]
    J --> K{"All checks PASS?"}
    K -->|Yes| L["Close runbook, record timings, and secure archive"]
    K -->|No| M["Halt cutover, analyze logs, and roll back per plan"]
~~~

**Precondition before every arrow:** database name, paths, file permissions, and target node/instance must be verified. In a cluster, never blindly replicate a standalone load workflow across multiple members.

## 4. Version Matrix: Pick the Right Command and Arguments

| Version line | Dump | Load | Key differences to remember |
|---|---|---|---|
| **Neo4j 4.4 (legacy)** | `neo4j-admin dump --database=neo4j --to=/path/neo4j.dump` | `neo4j-admin load --database=neo4j --from=/path/neo4j.dump` | `--to` and `--from` typically take a **file path**; replacing existing data uses `--force` |
| **Neo4j 5.x** | `neo4j-admin database dump neo4j --to-path=/backup-dir` | `neo4j-admin database load neo4j --from-path=/backup-dir` | Uses the `database` subcommand group; path points to a **directory** containing the archive |
| **Current Neo4j 2025–2026** | `neo4j-admin database dump` | `neo4j-admin database load` | Check `--help` on the exact installation; newer cloud/split-archive options may be added per release |

**Never guess from generic Internet snippets.** On the exact server/container image you will operate, run these **read-only** commands to inspect what the tool actually supports:

~~~bash
# From a shell environment with neo4j-admin in PATH.
neo4j-admin --version
neo4j-admin database dump --help
neo4j-admin database load --help
~~~

If `neo4j-admin database dump --help` does not exist on Neo4j 4.4, check:

~~~bash
# Applies only to the corresponding Neo4j 4.4 tools.
neo4j-admin dump --help
neo4j-admin load --help
~~~

Read the **Syntax**, **Default**, **Overwrite**, **From/To**, and edition requirements in the output. In enterprise environments, track both the **tool binary version** and the **source store and target server versions**. Never run a tool from an arbitrary image against an older store without verifying compatibility.

### 4.1. Do Not Confuse the Neo4j Version with the Java Driver Version

Your `spring.neo4j.uri` configuration, Maven `neo4j-java-driver` artifact, and Neo4j DBMS version are separate components. `Driver 5.x` does not imply the server runs Neo4j 5.26. When running dump/load, command syntax must match the **`neo4j-admin` bundled with the Neo4j server installation**, not the application's Java library version.

### 4.2. Upgrade Path Considerations

Neo4j 4.4 has reached the end of its long-term support lifecycle per current documentation schedules. Migrating stores from **4.4 to 5** involves dedicated migration guides and compatibility steps; you cannot simply load a 4.4 archive into any 2026 release and expect automatic seamless upgrading. Likewise, **downgrading a store to an older version is not supported as a routine operation**.

When changing versions during recovery, separate two questions:

1. Can the target tool **read/load** the archive format?
2. After loading, does the database require **store/schema migration**, recreating users/roles, or updating configuration per version upgrade guides?

A "load succeeded" message alone does not prove the application works on the new version.

## 5. Edition and Online/Offline State

Current Neo4j documentation distinguishes:

- **Community Edition:** `database dump` and `database load` are executed while the **DBMS is offline**. In labs, you typically stop the Neo4j process before running them.
- **Enterprise Edition:** local tools may run while the **DBMS remains online**, provided the **database being dumped or replaced is not mounted/running on that server**. For an individual user database, you can use `STOP DATABASE` with appropriate privileges and administrative procedures.
- **Enterprise Cluster:** the database belongs to a distributed topology. Seeding, restoring, or replacing a store must follow cluster procedures—not simply running `load --overwrite-destination` on each member.

An example pre-maintenance check:

~~~cypher
// Run in an appropriate administrative session.
SHOW DATABASES
YIELD name, currentStatus
RETURN name, currentStatus
ORDER BY name;
~~~

In Enterprise deployments with approval to take a user database offline, the administrative command can be:

~~~cypher
// ONLY inside an approved maintenance window; do not run in shared labs.
STOP DATABASE mydb WAIT;
~~~

Do not confuse **stopping a database** with **stopping the entire DBMS**. `STOP DATABASE` syntax, admin privileges, cluster behavior, and rules for `system` must be verified for your version. In Community Edition or simpler setups, stop the DBMS in a **dedicated test instance**.

## 6. Pre-Dump Checks: Do Not Look Only at the Destination File

A minimal runbook should record:

| Must verify | Why it matters |
|---|---|
| Source database and instance | Avoid dumping data from the wrong tenant/cluster |
| Edition, server version, admin tool version | Determines command, syntax, and version migration path |
| Database is offline per procedure | Avoids reading an actively changing store |
| OS user running the tool | Avoids creating `root`-owned files that Neo4j cannot read/write |
| Archive directory exists, has enough space, and is not public | Prevents mid-run failures and graph data leaks |
| Allowed RPO/RTO and downtime | Offline dump disrupts availability of the source database |
| Prior independent, restore-tested backup | Provides fallback if the new archive is defective |
| Data/schema baseline | Enables post-load comparison so you catch "starts up with wrong data" |
| Plugin, config, JDK, and store compatibility | A user DB archive does not include the full runtime environment |
| Approval logs and checklist | Establishes accountability for rollback/cutover |

**File security:** Dumps can contain sensitive data such as emails, orders, business relationships, hashed passwords, or personal attributes. Store them only in restricted locations, encrypt at rest and in transit, and never commit dumps to Git or public artifact registries. Never open backup folder permissions to "everyone" just to bypass permission errors.

## 7. Deterministic Cypher Fixture Before Dumping

To verify correctness after restore, use a **dedicated test database** with labels `QA003ArchiveItem`, `QA003ArchiveOwner`, and relationship `QA003_OWNED_BY`. Never run cleanup on a database containing real data or shared labels.

### 7.1. Create Clearly Identified Test Data

On a test database named `neo4j` (or substitute your lab deployment's database name), only after confirming the fixture does not already exist:

~~~cypher
CREATE CONSTRAINT qa003_archive_item_id IF NOT EXISTS
FOR (i:QA003ArchiveItem)
REQUIRE i.itemId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT qa003_archive_owner_id IF NOT EXISTS
FOR (o:QA003ArchiveOwner)
REQUIRE o.ownerId IS UNIQUE;
~~~

~~~cypher
UNWIND range(1, 5) AS id
MERGE (i:QA003ArchiveItem {itemId:id})
SET i.title = 'Item ' + toString(id),
    i.score = id * 10,
    i.recordedOn = date('2026-11-01');
~~~

~~~cypher
UNWIND [
  {id:'U01', name:'An'},
  {id:'U02', name:'Binh'}
] AS row
MERGE (o:QA003ArchiveOwner {ownerId:row.id})
SET o.name = row.name;
~~~

~~~cypher
UNWIND [
  {item:1, owner:'U01'},
  {item:2, owner:'U01'},
  {item:3, owner:'U02'},
  {item:4, owner:'U02'}
] AS row
MATCH (i:QA003ArchiveItem {itemId:row.item})
MATCH (o:QA003ArchiveOwner {ownerId:row.owner})
MERGE (i)-[:QA003_OWNED_BY]->(o);
~~~

**Note:** There are five items, and **item 5 has no owner**. This serves as a control case for `OPTIONAL MATCH`, verifying whether relationships are preserved accurately after restore.

### 7.2. Record the Pre-Dump Baseline

~~~cypher
MATCH (i:QA003ArchiveItem)
WITH count(i) AS items, sum(i.score) AS scores
MATCH (o:QA003ArchiveOwner)
WITH items, scores, count(o) AS owners
MATCH ()-[r:QA003_OWNED_BY]->()
RETURN items, scores, owners, count(r) AS relationships;
~~~

| items | scores | owners | relationships |
|---:|---:|---:|---:|
| **5** | **150** | **2** | **4** |

Because scores for items 1–5 are 10, 20, 30, 40, and 50, `sum(score)=150`.

Check each item individually, including the unowned item:

~~~cypher
MATCH (i:QA003ArchiveItem)
OPTIONAL MATCH (i)-[:QA003_OWNED_BY]->(o:QA003ArchiveOwner)
RETURN i.itemId AS itemId,
       i.title AS title,
       i.score AS score,
       i.recordedOn AS recordedOn,
       collect(o.ownerId) AS owners
ORDER BY itemId;
~~~

| itemId | title | score | recordedOn | owners |
|---:|---|---:|---|---|
| 1 | Item 1 | 10 | 2026-11-01 | [U01] |
| 2 | Item 2 | 20 | 2026-11-01 | [U01] |
| 3 | Item 3 | 30 | 2026-11-01 | [U02] |
| 4 | Item 4 | 40 | 2026-11-01 | [U02] |
| 5 | Item 5 | 50 | 2026-11-01 | [] |

Compare `owners` lists as sets or sort them when multiple owners exist; never assume `collect` ordering is invariant if the query does not sort prior to aggregation.

### 7.3. Record Schema/Constraints

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
WHERE name IN [
  'qa003_archive_item_id',
  'qa003_archive_owner_id'
]
RETURN name, type, labelsOrTypes, properties
ORDER BY name;
~~~

Expected result: two `IS UNIQUE` constraints for `QA003ArchiveItem(itemId)` and `QA003ArchiveOwner(ownerId)`; constraint-backing indexes must reach `ONLINE` before benchmarking. After loading, compare both **data** and **schema**, not just two counts.

## 8. Dump Procedure for Neo4j 5.x and Neo4j 2025–2026

**Assumption:** this is a **dedicated standalone lab**, the test database `neo4j` has been brought offline properly, Neo4j tools are installed on the host, and `/secure/neo4j-dumps` already exists with read/write access restricted to required accounts.

### 8.1. Pre-Run Checks

~~~bash
neo4j-admin --version
neo4j-admin database dump --help

# Read-only filesystem metadata checks; run in the lab environment.
ls -ld /secure/neo4j-dumps
df -h /secure/neo4j-dumps
~~~

For a Community lab, **only after stopping traffic and receiving approval to stop the DBMS**, an operator may run:

~~~bash
# ONLY on a test instance. This command stops Neo4j.
neo4j stop
~~~

For Enterprise, you can stop an individual user database via administrative Cypher while the DBMS remains online, but you must confirm the database is genuinely offline. **Never** run dump on a mounted database.

### 8.2. Create the Archive

~~~bash
# Neo4j 5+/2025–2026; database name is neo4j.
# --to-path points to an EXISTING writable directory.
neo4j-admin database dump neo4j --to-path=/secure/neo4j-dumps
~~~

Equivalent argument placement in documentation:

~~~bash
neo4j-admin database dump --to-path=/secure/neo4j-dumps neo4j
~~~

`--to-path` is the **target directory**. In many versions, this creates an archive named `neo4j.dump`; newer releases may alter naming, add timestamps, or support split archives. **Read the command output and list the actual files** rather than scripting under the assumption that every version emits the exact same filename.

**Do not add `--overwrite-destination=true` to dump unless you genuinely intend to replace an existing archive.** Last week's dump may be your lifesaver if the new archive is corrupt; organize runs into separate directories/lifecycles with explicit retention.

### 8.3. Verify the Archive

~~~bash
# Inspect newly created files in the directory.
ls -lh /secure/neo4j-dumps

# Check help to see if --info and artifact selection options are supported.
neo4j-admin database load --help
~~~

If the directory contains a matching dump and your version supports `--info`:

~~~bash
# Prints archive metadata; DOES NOT load the database.
neo4j-admin database load neo4j \
  --from-path=/secure/neo4j-dumps --info
~~~

`--info` reveals metadata such as format, file count, and size, **without replacing** checksum verification or a load + query drill. If multiple archives for the same database exist in one directory, verify how the tool **selects which artifact to load**; consider placing each dump in its own directory.

Example checksum verification once you know the **exact file** is named `neo4j.dump`:

~~~bash
sha256sum /secure/neo4j-dumps/neo4j.dump
~~~

Do not compute a checksum against a guessed filename if the tool created a different name. Record the checksum alongside timestamp, version, source database, and operator in a managed manifest; never edit an archive to "patch" dump contents.

## 9. Offline Load into an Isolated Test Instance — The Safest Choice

**Never test recovery directly on production.** Provision a **new, isolated Neo4j instance** on the same or documentation-compatible version, with a target volume completely separate from the source volume.

Assumptions:

- Source: test database `neo4j` from which the dump was taken.
- Target: **dedicated recovery test instance**, using database name `neo4j`.
- Archive directory `/secure/neo4j-dumps` transferred to the target, checksum verified.
- Target database **has no existing store**, or is prepared per version guidance **without needing overwrite**.

On the **offline target instance**:

~~~bash
neo4j-admin --version
neo4j-admin database load --help

# Example loading where no corresponding database store exists yet.
neo4j-admin database load neo4j \
  --from-path=/secure/neo4j-dumps
~~~

With `--from-path`, Neo4j 5+ expects the **directory containing the archive**, not the direct path to the `.dump` file. Some releases support loading via `--from-stdin`; use that only when you need to select a specific artifact and have tested stdin behavior in your shell.

**When a store already exists:** the command refuses to load by default, which is a **critical safeguard**. Do not reflexively add `--overwrite-destination`; confirm you are targeting the test instance, hold a copy of existing target data, and have replacement authorization.

### 9.1. Starting or Registering the Database After Load

On a Community standalone instance **with the DBMS stopped**, finish loading and then start the DBMS per procedure:

~~~bash
# Use only on the recovery test instance.
neo4j start
~~~

On **Enterprise**, when loading a database that **has never existed in the catalog**, current Neo4j documentation requires **registering it with `CREATE DATABASE` on the `system` database after load**:

~~~cypher
// Example for an Enterprise test instance only,
// when data is loaded but the catalog does not yet include this database.
CREATE DATABASE restoredtest WAIT;
~~~

The name `restoredtest` is valid only if the archive/store was loaded under **that exact name** following your version's procedure. Never run `CREATE DATABASE` blindly to "fix" a load error; understand both filesystem state and catalog state to avoid accidentally creating an empty database.

If restoring to **replace an existing database**, the startup/registration sequence differs; follow the dedicated guidance in Section 10.

### 9.2. Verify the Database Is Actually Online

~~~cypher
SHOW DATABASES
YIELD name, currentStatus
RETURN name, currentStatus
ORDER BY name;
~~~

Only after the expected database is `ONLINE` and your account has permissions, run the verification Cypher queries from Section 7. If a query returns 0 nodes, do not jump to concluding the dump is empty: check the database name configured in your Java Driver session, Neo4j Browser, or Spring Data Neo4j.

## 10. Replacing an Existing Database: A High-Risk Operation

Neo4j 5+ supports `--overwrite-destination=true` when **restoring on a standalone server** and the target database **is completely stopped**. This is an example to **recognize syntax in runbooks**, not an instruction to execute immediately:

~~~bash
# ONLY ON AN ISOLATED RECOVERY INSTANCE, AFTER APPROVAL.
# Target database is stopped, existing data is backed up, and paths are verified.
neo4j-admin database load neo4j \
  --from-path=/secure/neo4j-dumps \
  --overwrite-destination=true
~~~

Defaulting to `--overwrite-destination=false` is safer. In 4.4, the corresponding flag was `--force`; **do not** swap flag names while skipping database-stop and archive-compatibility checks.

### Approval Checklist for Overwrite

1. Change ticket exists, with database owner sign-off and communicated downtime window.
2. Hostname, instance, data directory, and target database name verified **twice**.
3. Admin command uses the **exact matching binary version** for the recovery procedure.
4. Target database has stopped accepting writes and is offline; in Community, DBMS is offline.
5. A **pre-overwrite backup of target data** exists outside the fault domain.
6. Source archive metadata/checksum verified and previously restore-tested.
7. Clear rollback owner, acceptance criteria, and RTO checkpoint defined.
8. Applications connect/start only after post-load validation PASSES.

**Never copy an internet `--overwrite-destination=true` snippet to immediately overwrite a production database.**

## 11. Fundamental Differences in Neo4j 4.4

Neo4j 4.4 uses legacy CLI commands, for example:

~~~bash
# Neo4j 4.4, offline lab environment.
neo4j-admin dump \
  --database=neo4j \
  --to=/secure/neo4j-dumps/neo4j-legacy.dump
~~~

Loading the archive into a **compatible target**:

~~~bash
# Neo4j 4.4, when the target database has no existing store.
neo4j-admin load \
  --database=neo4j \
  --from=/secure/neo4j-dumps/neo4j-legacy.dump
~~~

If the target already has data and requires replacement after stopping/backing up, Neo4j 4.4 provides `--force`. In Neo4j 5+, that flag is replaced by `--overwrite-destination` under the `database load` subcommand.

| Mistake | Consequence |
|---|---|
| Running `neo4j-admin dump` on 5+ | Command not found error |
| Passing `--to-path=/file.dump` as in 4.4 | Newer tool expects a **directory**, not a file path |
| Passing `--from=/file.dump` on 5+ | Invalid syntax for standard newer commands |
| Carrying `--force` from 4.4 to newer commands | Not the new `--overwrite-destination` syntax |
| Assuming any 4.4 archive loads into any 2026 release | Ignores migration path and store-format compatibility |
| Assuming Driver version dictates admin commands | False: the Neo4j DBMS binary dictates CLI syntax |

Neo4j 4.4 has exited long-term support; for systems still running 4.4, plan an upgrade following official migration guides rather than treating dump/load as a complete migration strategy.

## 12. Docker: Which Volume Holds the Archive and Database?

In Docker, the database process may run inside a container with a `/data` volume. To dump while the database is offline, Neo4j documentation illustrates launching a **temporary admin container** mounted to both the data volume and a dump volume.

Example **lab pattern**, on Linux, after the main Neo4j container has completely stopped:

~~~bash
# TEMPLATE: substitute host volumes and image for your actual deployment.
docker run --rm \
  --volume=/srv/lab-neo4j/data:/data \
  --volume=/srv/lab-neo4j/dumps:/backups \
  neo4j/neo4j-admin:2026.10.2 \
  neo4j-admin database dump neo4j --to-path=/backups
~~~

Once the archive is created, use **a fresh data volume** for the restore target:

~~~bash
# NEW TEST TARGET: do not mount the source data volume.
docker run --rm \
  --volume=/srv/lab-neo4j/restored-data:/data \
  --volume=/srv/lab-neo4j/dumps:/backups \
  neo4j/neo4j-admin:2026.10.2 \
  neo4j-admin database load neo4j --from-path=/backups
~~~

**Important:**

- The `data` and `restored-data` volumes must be genuinely distinct.
- No Neo4j container using the source volume may continue writing while the admin container dumps the store.
- The admin image version must match the database version; version numbers above are documentation examples, **not upgrade recommendations**.
- Volume ownership/permissions must allow the Neo4j user to read/write; avoid creating root-owned files that prevent the Neo4j process from starting.
- Dump archives must be copied/stored externally, not left inside ephemeral container layers.
- For clusters/Kubernetes, consult Helm/operator and topology-aware backup guides; never run an admin container simultaneously on a volume mounted by another server.

## 13. Kubernetes and Clusters: Do Not Follow Standalone Steps

### 13.1. Kubernetes

Neo4j on Kubernetes typically uses PVCs, StatefulSets, and containers managed by an operator or Helm chart. To dump/load:

1. Identify the data PVC and archive destination.
2. Put the database into **offline maintenance mode** per deployment docs.
3. Run tooling from a matching-version image with verified volume mounts.
4. Load only into a **test target** or managed recovery environment.
5. Verify pods, database status, volume permissions, and application queries after recovery.

Never delete PVCs, randomly scale replicas, or swap production pods just to "make load work." Volume-level mistakes can cause far wider impact than ordinary Cypher errors.

### 13.2. Enterprise Clusters

A cluster also maintains metadata about database membership, identity, and state. When seeding a cluster from a dump where a database of the same name already exists in cluster state, **overwriting local files without handling catalog/topology properly can cause logical corruption**.

Current documentation recommends using **database creation/recovery from URI** or a designated seeder workflow. Never run `neo4j-admin database load --overwrite-destination=true` one by one across cluster nodes as if they were standalone servers; and never propose `DROP DATABASE` on a cluster without a dedicated runbook, backup, and approval.

**Composite databases** are not direct targets for some dump/load commands; operate on constituent databases supported by the tooling using topology-appropriate procedures.

## 14. The `system` Database, Users/Roles, and What Is Not Automatically Included

A dump archive of a user database like `neo4j` primarily contains **database data**, including that database's graph and schema in store format. It **does not mean the entire DBMS is backed up**, because:

- User and role metadata typically lives in the **`system` database**, not inside individual user database dumps.
- `neo4j.conf`, environment variables, secret managers, TLS certificates, plugin JARs (APOC, GDS, or custom plugins), container manifests, and network policies have independent lifecycles.
- Full-text/vector indexes, analyzers, or procedures tied to target plugins/versions require post-restore compatibility verification.
- Cluster routing/topology state cannot be restored by arbitrarily copying stores.

For DBMS-wide DR strategies, Neo4j documentation requires **planning backups for each database, including `system`**, as appropriate for your version and deployment. However:

**Never load/overwrite `system` on an existing DBMS merely to "restore roles."** The `system` database holds sensitive administrative state; improper restoration can break the database catalog, users/roles, and login access. Follow a dedicated runbook verified for your exact version and edition.

After restoring a user database, verify:

| Component | Post-load check |
|---|---|
| Nodes, relationships, properties | Counts, logical checksums, or sample business records |
| Constraints/indexes | `SHOW CONSTRAINTS`, `SHOW INDEXES`, `ONLINE` status |
| Users/roles | Login and READ/WRITE/EXECUTE rights; whether metadata needs separate restoration |
| Java Driver | URI, database name, TLS, reads/writes, parameterized queries |
| Spring Data Neo4j | Entity mapping, repositories, relationship hydration, transactions |
| Plugins and extensions | Compatible versions installed and permissions configured |
| Backup configuration | Backup schedule, retention, encryption, and monitoring active again |

## 15. Verifying an Archive: Three-Tier Checks

### Tier 1 — Physical File

- File exists, had no write errors, and is non-zero in size.
- Checksum matches after transfer between hosts/object storage.
- File permissions, user/group ownership, and encryption comply with policy.
- Directory name, tool version, source database, and dump timestamp recorded in a manifest.
- Target disk space is sufficient for extraction/loading plus any index building/recovery overhead.

### Tier 2 — Format and Compatibility

~~~bash
# Inspect metadata only; does not load.
neo4j-admin database load neo4j \
  --from-path=/secure/neo4j-dumps --info
~~~

Record the format and metadata reported by the command. Run `neo4j-admin database load --help` if your version differs. **An archive whose metadata can be read can still fail to load** due to store incompatibility, insufficient disk space, or file corruption.

### Tier 3 — Actual Restore and Business Verification

On an isolated test instance, after loading and starting:

~~~cypher
MATCH (i:QA003ArchiveItem)
WITH count(i) AS items, sum(i.score) AS scores
MATCH (o:QA003ArchiveOwner)
WITH items, scores, count(o) AS owners
MATCH ()-[r:QA003_OWNED_BY]->()
RETURN items, scores, owners, count(r) AS relationships;
~~~

Expected output from the fixture: **5 / 150 / 2 / 4**. Also query item 5 and confirm it has no owner:

~~~cypher
MATCH (i:QA003ArchiveItem {itemId:5})
OPTIONAL MATCH (i)-[:QA003_OWNED_BY]->(o)
RETURN i.itemId AS itemId, count(o) AS owners;
~~~

**Answer:** `itemId=5` and `owners=0`. Also verify the `recordedOn` date:

~~~cypher
MATCH (i:QA003ArchiveItem {itemId:1})
RETURN i.recordedOn AS recordedOn, i.score AS score;
~~~

**Answer:** `recordedOn = date('2026-11-01')` and `score=10`.

Do not check only `RETURN 1` or "database online." A database can start up yet not be the one you intended to recover, or be missing schema, plugins, or roles.

## 16. Verifying from Java Driver and Spring Data Neo4j

### 16.1. Java Driver Must Target the Exact Restored Database

A Java application can connect successfully yet default to a **home database** different from the restored test database. Specify it explicitly:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public static long restoredCount(
        Driver driver, String database) {
    try (Session session = driver.session(
            SessionConfig.forDatabase(database))) {
        return session.executeRead(tx ->
            tx.run("""
                MATCH (i:QA003ArchiveItem)
                RETURN count(i) AS total
                """).single().get("total").asLong()
        );
    }
}
~~~

**Answer:** `restoredCount(driver, "neo4j") == 5` if that is indeed the test database holding the fixture, the user has sufficient permissions, and the data loaded cleanly. This snippet does not replace relationship/schema reconciliation, but it catches wrong-database configuration bugs in Java apps.

### 16.2. Spring Data Neo4j

In Spring Data Neo4j, database configuration, repository/entity mapping, and transaction management must be verified separately:

- Can repositories look up `QA003ArchiveItem` nodes by business key?
- Do entities hydrate `LocalDate recordedOn`, `score`, and owner relationships accurately?
- Are custom `@Query` methods still compatible with the target version's Cypher runtime and indexes?
- Does the user/role have sufficient rights for `MERGE`, `MATCH` queries, and any application-driven schema migrations?
- Do post-restore transactions commit and roll back as expected?

When moving a dump to a newer Neo4j release, Java/SDN smoke tests can uncover compatibility issues that node counts alone miss.

## 17. Distinguishing Dump from RPO/RTO and Long-Term Retention Plans

**RPO (Recovery Point Objective)** is the maximum data-loss time window the business permits. **RTO (Recovery Time Objective)** is the target time to restore service.

**Illustrative** example:

- An offline dump is taken only once every 24 hours.
- A failure happens 23 hours after the last dump.
- If only that dump exists with no other recovery mechanism, available data may be nearly **23 hours** stale.
- Downloading, loading, starting, and validating the application takes **70 minutes** in a drill.

Under these assumptions, this strategy **fails to meet** a 5-minute RPO or a 30-minute RTO. If the business requires minimal downtime, consider Enterprise online backups, backup chains, and suitable topology rather than repeatedly stopping the database to dump.

### 17.1. Does Dump Replace a Strategic Backup?

Dump is a **full-archive mechanism** under supported conditions and can be part of a recovery strategy. However, if you keep only one file on the same machine:

- Losing the machine/volume can wipe both database and archive.
- Accidental deletion or ransomware can hit the archive too.
- If the file corrupts, there is no fallback.
- Without load tests, nobody knows the actual RTO or whether recovery even works.

You need off-failure-domain copies, archive versioning/retention, access controls, checksums, and regular restore tests.

### 17.2. Capacity and Speed

Actual offline duration can include:

\[
T_{\text{downtime}} \approx
T_{\text{stop}} + T_{\text{dump/load}} +
T_{\text{start}} + T_{\text{verify}} + T_{\text{cutover}}
\]

This formula is only a planning model; some steps can run in parallel on another instance. Dump duration depends on store size, indexes, filesystem, compression/archive level, I/O, and CPU; load additionally incurs decompression, write amplification, recovery, and startup overhead. **Never extrapolate duration solely from node count** or advertised peak SSD throughput.

## 18. Common Errors During Dump and Load

| Symptom | Likely cause | Safe remediation |
|---|---|---|
| `Unrecognized command: database dump` | Running neo4j-admin 4.4 or wrong binary | Check `--version`/`--help`; use release-appropriate syntax |
| `Unknown option --to-path` | Using newer syntax on an older binary | 4.4 typically uses `--to=/file.dump` |
| `--from-path` cannot find archive | Passed a file instead of a directory, wrong DB/file name, or permissions | Check directory, dump output, `--info`, and OS permissions |
| `Database is in use` / cannot dump | Database is mounted or a process holds file locks | Stop database/DBMS per edition; never raw-copy live files |
| Permission denied on dump folder | OS user running tool lacks write access | Fix minimal ownership/ACL; do not set world-readable |
| Load refuses because database already exists | Default prevents overwrite | Verify target; avoid adding overwrite flags without approval |
| Load succeeds but database is not ONLINE | Not started/registered, config error, store migration, or permissions | Check catalog/logs, Enterprise/Community workflow, and version |
| Query returns 0 nodes after restore | Connected to wrong database, wrong archive, or different source data | Set explicit `SessionConfig.forDatabase`, check manifest and fixture |
| Java/SDN connects but gets permission denied | User/role metadata does not ship with user DB dumps | Check target DBMS privileges; restore RBAC per procedure |
| Indexes not ONLINE yet | Index population still running or different environment | Run `SHOW INDEXES`, wait for online before performance testing |
| Cluster reports store/state errors after load | Copied stores outside topology/cluster procedure | Halt; use URI/seed/recovery per cluster docs |
| 4.4 archive incompatible with newer target | Skipped migration/store-format upgrade path | Follow supported version migration path; keep original dump |
| Checksum mismatch after transfer | Incomplete/corrupt transfer or wrong artifact | Do not load; re-transfer correct file, verify source |
| Dump succeeds but backup fails RPO | Dump cadence too sparse, requires downtime | Design online backup/retention and drill against RPO/RTO |

**Error-handling rule:** never add `--overwrite-destination=true`, delete store directories, or reload `system` by reflex. Log the error and diagnose the root cause on an environment without irreplaceable data.

## 19. Archive Management Techniques: Naming, Checksums, and Security

An artifact bundle might look like:

~~~text
offline-dumps/
  run-2026-11-25T020000Z/
    neo4j.dump                 # Illustrative filename only.
    manifest.txt               # Operational metadata managed separately.
    sha256.txt                 # Artifact checksum.
~~~

Depending on version, actual dump names may include timestamps or multiple parts. **Do not rename arbitrarily** when `load` relies on artifact naming/structure; check first and keep original contents intact.

A manifest should record:

| Field | Example value |
|---|---|
| Run ID, UTC timestamp | `run-2026-11-25T020000Z` |
| Database/source DBMS | `neo4j / lab-db-01` |
| Neo4j edition/version/tool | `5.x, Community, matching admin version` |
| Offline state and verification step | `DBMS stopped / verified` |
| Archive path, size, SHA-256 | Actual path, byte count, digest |
| Baseline query results | 5 items, 2 owners, 4 relationships, sum score 150 |
| Constraint/index inventory | Name, type, status |
| Retention schedule and secondary location | Owner, policy |
| Restore test outcome | Duration, PASS/FAIL validation |
| RPO/RTO and recovery scope | Data checkpoint, limitations |

Never store passwords, private keys, or tokens inside manifests. Dump files holding business data must be encrypted and accessed under the principle of least privilege. If storing in cloud storage, verify object-storage read/write support in your **exact version**; do not assume every Neo4j 5 build supports every newer cloud URI scheme.

## 20. Stop-the-World Operational Runbook Template

**Pre-maintenance phase**

1. Owner approves source/target databases and recovery targets.
2. Verify edition/version/tool and compatibility.
3. Run data/schema baseline queries and save results.
4. Verify disk capacity, archive destination, permissions, and prior backup.
5. Provision an isolated restore instance with access to the archive.

**Dump phase**

6. Stop writes and take the database offline per edition procedure.
7. Run `database dump` or legacy `dump` per actual tooling.
8. Verify exit code, archive, metadata, and checksum.
9. If the source must resume serving, reopen only after dump verification; record downtime duration.

**Restore test phase**

10. Transfer archive/checksum to the isolated target and verify match.
11. Confirm target database is offline and either has no data to preserve or has a pre-overwrite backup.
12. Run `database load`, and register/start the database properly.
13. Reconcile nodes/relationships/properties/schema and smoke-test Java/SDN.
14. If failed, halt cutover, save logs, analyze, and revert target to initial state.
15. If passed, record versions and actual restore duration, update RPO/RTO, and save audit trail.

### Completion Criteria

A dump/load run is marked **PASS** only when all of the following hold:

- Archive can be read/loaded by supported tooling.
- Target database is online with the expected name.
- Required data counts, relationships, temporal properties, and schema match the baseline.
- Applications via Java Driver/SDN can read/write with proper permissions (if in test scope).
- Rollback procedure, artifact security, and repeatable restore capability are proven.

Seeing only "command exited 0" is **insufficient**.

## 21. Exercises with Answers

### Exercise 1 — Choosing the Right Syntax

A machine runs Neo4j 5.26. An engineer tries `neo4j-admin dump --database=neo4j --to=/x/neo4j.dump` and gets a command-not-found error. What syntax is appropriate?

**Answer:** check `neo4j-admin database dump --help` and use `neo4j-admin database dump neo4j --to-path=/x`, where `/x` is a **directory**, after the database is offline.

### Exercise 2 — Edition and Downtime

A Neo4j Community instance is actively serving requests. Can you run dump while keeping the DBMS online like an online backup?

**Answer:** No. Per current Neo4j documentation, Community runs `database dump` only when the DBMS is offline. You must schedule a maintenance window or choose an appropriate backup architecture.

### Exercise 3 — Is `--info` a Restore Test?

`neo4j-admin database load neo4j --from-path=/x --info` prints valid metadata. Can you declare the backup guaranteed to restore?

**Answer:** Not yet. `--info` does not load; you must test loading on an isolated instance, start the database, and reconcile nodes, relationships, schema, and the application.

### Exercise 4 — Fixture Verification

Before dumping, the database contains five items with scores 10, 20, 30, 40, and 50; two owners; and four relationships. After loading, what should the verification query return?

**Answer:** `items=5`, `scores=150`, `owners=2`, and `relationships=4`. Item ID 5 has `owners=0`.

### Exercise 5 — User Permissions After Load

After loading a user database into a new DBMS, the application gets permission denied even though data and constraints are intact. Why?

**Answer:** A user database dump does not automatically include user/role metadata or full DBMS configuration; you must configure/restore RBAC and security state via the `system` database/edition procedure.

### Exercise 6 — Overwriting the Target

`database load` refuses because the database already exists. Should you immediately add `--overwrite-destination=true`?

**Answer:** No. First verify the target instance/database, take an independent backup of the target, bring the database offline, assess impact, and obtain approval. The overwrite flag can destroy data you intended to keep.

### Exercise 7 — Storing Files in Docker

A dump container writes `neo4j.dump` into its ephemeral filesystem layer, and after the container exits and is removed, the file is gone. What went wrong?

**Answer:** The archive path was not mounted to a persistent volume/storage. Mount a dedicated dump volume and copy it to another failure domain; ephemeral containers should run the task, not store the sole copy.

### Exercise 8 — Cluster Restore

An engineer plans to load the same archive directly over the data directory of each cluster member hosting a database of the same name. Is this sound?

**Answer:** Do not do this. Use cluster restore via URI/seeding with proper state/topology management. Blindly overwriting local store files can leave cluster state inconsistent.

### Exercise 9 — Calculating RPO/RTO

The only dump runs at 00:00, a failure occurs at 20:00, and a test restore takes 50 minutes. If the business requires a 10-minute RPO and 20-minute RTO, does this approach pass?

**Answer:** No. The dump can be **20 hours** stale and actual restore time is **50 minutes**, both breaching targets. Redesign the backup/recovery strategy and re-measure.

### Exercise 10 — Restoring to Upgrade

You have a dump from Neo4j 4.4 and a Neo4j 2026 server. Should you load it directly and assume no migration is needed?

**Answer:** No. Follow the supported migration path, verify store/archive/tool compatibility, and address roles/plugins/config procedures. A successful load does not automatically mean an upgrade is complete.

### Exercise 11 — Dump or Online Backup?

A business cannot interrupt transactions during business hours and wants frequent recovery points. Should it rely continuously on offline dumps?

**Answer:** Offline dumps cause downtime for the source database; for online requirements, evaluate Enterprise `neo4j-admin database backup` or another supported architecture, paired with retention and restore drills.

## 22. Fixture Cleanup (Test Database Only)

Once recovery testing is complete and the test evidence is no longer needed, you can clean up **only the fixture** on the lab instance. **Do not run** if those demo labels were ever used for real data.

~~~cypher
MATCH (n)
WHERE n:QA003ArchiveItem OR n:QA003ArchiveOwner
DETACH DELETE n;
~~~

~~~cypher
DROP CONSTRAINT qa003_archive_item_id IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa003_archive_owner_id IF EXISTS;
~~~

Verify:

~~~cypher
MATCH (n)
WHERE n:QA003ArchiveItem OR n:QA003ArchiveOwner
RETURN count(n) AS remaining;
~~~

**Answer:** `remaining = 0`. Post-restore cleanup **does not modify existing dump files**; if you want a fresh dump of the cleaned state, that is a new backup run and must receive a new run ID.

## 23. Official Documentation and Takeaways

- [Neo4j Operations — Back up an offline database](https://neo4j.com/docs/operations-manual/current/backup-restore/offline-backup/): `neo4j-admin database dump` syntax, edition/offline requirements, archive destinations, and file safety.
- [Neo4j Operations — Restore a database dump](https://neo4j.com/docs/operations-manual/current/backup-restore/restore-dump/): `database load`, `--info`, `--from-path`, overwrite behavior, database registration, and cluster risks.
- [Neo4j Operations — Backup and restore planning](https://neo4j.com/docs/operations-manual/current/backup-restore/planning/): comparison table of backup/restore vs. dump/load/copy, downtime requirements, and capabilities.
- [Neo4j Operations — Backup modes](https://neo4j.com/docs/operations-manual/current/backup-restore/modes/): full/differential backups, RBAC metadata, and dump limits.
- [Neo4j Operations — Docker: dump and load](https://neo4j.com/docs/operations-manual/current/docker/dump-load/): temporary admin container and volume mounting.
- [Neo4j Operations — Kubernetes: dump/load](https://neo4j.com/docs/operations-manual/current/kubernetes/operations/dump-load/): offline maintenance in Kubernetes.
- [Neo4j Operations — Neo4j admin tool](https://neo4j.com/docs/operations-manual/current/neo4j-admin-neo4j-tools/): command groups, `--version`, `--help`, and OS permissions.
- [Neo4j Upgrade and Migration Guide — Migrate 4.4 to 5](https://neo4j.com/docs/upgrade-migration-guide/current/version-5/migration/): compatibility paths and preparing databases/roles.
- [Neo4j Upgrade and Migration Guide — Legacy 4.4 syntax](https://neo4j.com/docs/upgrade-migration-guide/current/version-4/migrate-community-enterprise/): 4.4 `neo4j-admin dump`/`load` examples.

**Takeaway:** **Choose tooling matching the actual DBMS version**, not snippets from another release or the Java Driver version. `dump` is valid only when the source database is in a supported offline state; `load` must target an offline destination database on the right instance. **Never overwrite by default**, never arbitrarily load local files onto a cluster, and never treat a user-database archive as a complete backup of users/roles/config. Only after **a successful trial restore reconciling data, schema, permissions, and the application** do you have grounds to trust that a dump supports real recovery.
