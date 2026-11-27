# Compatibility Across MongoDB Server, Drivers, and Database Tools

## Learning Objectives

During **MongoDB operations and upgrades**, an apparently simple change—such as upgrading `mongod` from 7.0 to 8.0, updating the Java Sync Driver from 4.x to 5.x, or installing a newer `mongodb-database-tools` package—can ripple across multiple layers. An application being able to connect does not mean every new feature works; a `mongodump` release supporting a server connection does not mean every dump safely restores onto an arbitrary server; and swapping server binaries does not mean Feature Compatibility Version (FCV) has been raised.

This lesson belongs to **Database Engine Document MongoDB → Operations and Upgrades → Compatibility Across Server, Driver, and Database Tools**.

After studying it, you will be able to:

- Distinguish versions of **MongoDB Server**, **MongoDB Drivers**, **MongoDB Database Tools**, **mongosh**, and **FCV**.
- Read official compatibility tables rather than assuming "version numbers must match".
- Inspect active server versions and state from `mongosh`, Java applications, and the command line.
- Understand the difference between **can connect**, **tested**, **fully compatible**, and **capable of running a specific feature**.
- Select a Java Sync Driver compatible with both the server and Java runtime while avoiding dependency conflicts.
- Distinguish `mongodump`/`mongorestore` from `mongoexport`/`mongoimport` along with BSON/Extended JSON limits.
- Verify dump restore compatibility across **server major version/FCV**, metadata, archives, and oplogs.
- Design replica set and sharded cluster upgrade sequences plus FCV confirmation phases.
- Understand why Database Tools `100.x` does not mean MongoDB Server `100.x`.
- Build compatibility matrices and rollout/canary/rollback plans.
- Diagnose wire protocol handshakes, authentication, TLS, DNS, server selection, tool flags, and restore errors.
- Write smoke tests and runbooks for dev, staging, and production environments.

> **Operational principle:** Verify compatibility for the **exact product pairing, version, deployment, and feature**. Never treat one command working on a local machine as proof that a full cluster upgrade is safe.

**Document reference date:** version examples reflect MongoDB documentation published as of **2026-11-14**. Support matrices evolve as new driver, Database Tools, and server releases ship. Before deploying, always consult the official compatibility table for the **exact versions you intend to run**, especially minor/patch or untested releases.

---

## 1. What Components Make Up a Real MongoDB Application?

~~~text
                 Java application / Spring Boot
                        |
                MongoDB Java Sync Driver
                        |
       TLS + authentication + MongoDB wire protocol
                        |
              mongos / mongod / Atlas router
                        |
              MongoDB Server deployment
              binary version + cluster FCV
                        |
              collections, indexes, data

Administrators / CI:
  mongosh                     (shell, independent version)
  mongodump / mongorestore    (Database Tools 100.x)
  mongoexport / mongoimport   (Database Tools 100.x)
  mongostat / mongotop        (Database Tools 100.x)
  mongofiles / bsondump       (Database Tools 100.x)
~~~

Real-world systems also involve:

- Atlas UI/CLI and the Atlas control plane.
- MongoDB Search / Vector Search services.
- Ops Manager / Cloud Manager for self-managed clusters.
- TLS/PKI, DNS/SRV records, IAM, and KMS.
- Container images, Kubernetes Operators, OS distributions, and CPU architectures.
- Backup services and restore histories.

Each component has its own release cadence and compatibility scope.

### 1.1. Five Versions Commonly Tracked

| Component | Illustrative Example | What It Governs |
|---|---|---|
| MongoDB Server binary | `8.0.x` | Engine, commands, wire protocol, storage, query semantics |
| Feature Compatibility Version | `8.0` or `7.0` depending on upgrade state | Enables persistent features incompatible with older releases |
| Java Sync Driver | `5.12.x` | JVM connectivity, codecs, retries, command APIs |
| Database Tools | `100.20.1` | Dump/restore, import/export, diagnostics |
| mongosh | `2.x` or equivalent release | Interactive shell and helper methods |

These version numbers **do not need to—and cannot—match arithmetically**.

### 1.2. Deployment Version Can Differ from Local Tool Version

Running `mongodump --version` locally displays the binary version **on that machine**, not the `mongod` version running in the Atlas cluster it connects to.

Similarly, `mongosh --version` does not tell you which MongoDB Server version the cluster runs.

### 1.3. Questions to Ask Before Upgrading

1. What are the source and target Server versions?
2. What is the cluster FCV?
3. Is it standalone, replica set, sharded cluster, or Atlas-managed?
4. Which driver version and Java runtime does the application use?
5. Which Database Tools version created the backup, and which will restore it?
6. Does the data use new features/metadata unrecognized by an older server?
7. Are encryption, Search, time-series, change streams, or sharding in use?
8. What are the upgrade objectives and rollback window?

---

## 2. MongoDB Server Binary Version

### 2.1. `mongod` and `mongos`

- `mongod`: database server process running as standalone, replica set member, shard, or config server depending on topology.
- `mongos`: query router for a sharded cluster.
- Atlas manages infrastructure provisioning/upgrades and restricts direct host binary access.

Upgrading a sharded cluster is never just swapping one `mongod` binary; you must follow the **official procedure** covering components and upgrade ordering.

### 2.2. Major, Minor, and Patch Releases

Examples like `7.0`, `8.0`, `8.2`, `8.3`, and `9.0` represent MongoDB release lines documented in 2026. Each release train carries its own support policy, deployment availability, and feature set.

A patch release can introduce bug fixes, security patches, or compatibility-relevant changes. Never write a rule like "any upgrade within 8.x is always fully compatible" without reading the release notes.

### 2.3. Do Not Guess Versions from Package Installers

An OS package named `mongodb-org` installs `mongod`/`mongos` alongside companion packages. A Docker tag like `mongo:8` shifts to newer patches over time. Pin exact versions in production rather than using broad tags when reproducibility matters.

### 2.4. Current Local Binary Version

~~~bash
mongod --version
mongos --version
~~~

This checks the binaries installed on the local host without connecting to a database. A developer laptop might have 9.0 installed locally while the app connects to Atlas 8.0.

---

## 3. Checking the Actual Running Server Version

### 3.1. mongosh

~~~javascript
db.version();
~~~

Illustrative result:

~~~text
8.0.12
~~~

### 3.2. `buildInfo`

~~~javascript
db.adminCommand({
  buildInfo: 1
});
~~~

Returns fields such as `version`, build metadata, modules, and environment details. Check actual command output instead of inferring from the URI.

### 3.3. `hello`

~~~javascript
db.adminCommand({
  hello: 1
});
~~~

Returns topology and wire protocol fields such as `maxWireVersion`/`minWireVersion`. Drivers inspect these during handshakes, though **they do not substitute for product compatibility tables**.

### 3.4. FCV

~~~javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
~~~

Example of a deployment mid-upgrade:

~~~javascript
{
  featureCompatibilityVersion: {
    version: "7.0"
  },
  ok: 1
}
~~~

Server binaries may already run 8.0 while FCV remains 7.0 during a transition phase. This is an intentional upgrade stage.

### 3.5. Self-Managed vs. Atlas Commands

In Atlas, certain admin commands or topology fields may be restricted by role or service boundaries. Use the Atlas UI or management API to confirm deployment versions and upgrade state when needed.

### 3.6. What `db.version()` Alone Does Not Prove

- Which Java driver the application runs.
- Which Database Tools sit on the backup host.
- Current FCV (must be queried separately).
- Whether Search/Vector Search infrastructure is ready.
- Privileges to create indexes or backups.
- Network/DNS/TLS reachability from the app environment.
- Whether a backup archive can restore cleanly to the target.

---

## 4. Feature Compatibility Version (FCV)

FCV is MongoDB's mechanism for gating **features/persisted state that could make data incompatible with older binaries**. It is not the same as the binary version.

### 4.1. Example: Upgrading from 7.0 to 8.0

~~~text
Before upgrade:
  mongod binary = 7.0.x
  FCV = 7.0

After rolling binary upgrade:
  mongod binary = 8.0.x
  FCV still = 7.0

After burn-in and deciding to adopt new features:
  mongod binary = 8.0.x
  FCV = 8.0
~~~

Not every new feature waits for FCV elevation; some gates depend on server version or service tier. Still, **backward-incompatible persisted features** are why FCV must be managed carefully.

### 4.2. Check FCV Before Upgrading

The MongoDB 8.0 upgrade guide requires a 7.0 source deployment to have FCV `7.0` before upgrading to 8.0. The MongoDB 8.2 upgrade guide requires an 8.0 source to have FCV `8.0` before upgrading to 8.2.

Never jump across multiple major/minor versions by replacing binaries in one shot. Follow the official upgrade path for your exact source and target.

### 4.3. Changing FCV Is a Consequential Admin Action

Illustrative example for 8.0 after completing the binary upgrade:

~~~javascript
db.adminCommand({
  setFeatureCompatibilityVersion: "8.0",
  confirm: true
});
~~~

**Never run this command just to experiment.** It alters compatibility state cluster-wide and can restrict or block downgrades under release policy.

### 4.4. Burn-In Period

MongoDB recommends running the new binaries under the old FCV for a suitable burn-in window before enabling backward-incompatible features. Use this window to:

- Monitor application errors.
- Check query plans and latency.
- Verify backups and restores.
- Run canary business workflows.
- Evaluate whether a supported binary rollback is needed.

### 4.5. Downgrading Is Not Just "Reinstalling the Old Binary"

A new schema, index, or feature can persist formats unreadable by an older server. MongoDB 8.2/8.3/9.0 introduced policy changes by version and edition, including **single-version downgrade** support or MongoDB Support engagement rules.

Read the exact downgrade guide for your **target**, FCV, server edition, and active features. Never reuse one generic downgrade script across branches.

### 4.6. Version 9.0

MongoDB 9.0 upgrade documentation describes upgrading binaries to 9.0, running without backward-incompatible features enabled, and only then considering FCV `9.0` after burn-in. This is an **example of separating binary upgrades from FCV activation**, not advice to jump every deployment straight to 9.0.

---

## 5. What Is a MongoDB Driver?

A driver is the application library that connects to MongoDB and translates language-level operations into MongoDB commands over the wire protocol.

Java example:

~~~java
MongoClient client =
    MongoClients.create(connectionString);

MongoDatabase db =
    client.getDatabase("shop");

MongoCollection<Document> orders =
    db.getCollection("orders");

long count =
    orders.countDocuments();

System.out.println(count);
~~~

Drivers handle critical infrastructure tasks applications should never reimplement:

- Connection pooling.
- Server discovery / SDAM.
- Handshake / wire protocol negotiation.
- Supported authentication mechanisms.
- TLS.
- BSON codecs / serialization.
- Read/write concerns.
- Eligible retryable reads/writes.
- Sessions and transactions.
- Replica set / sharded topology routing.
- Compression and command monitoring.

### 5.1. Driver Version Differs from MongoDB Server Version

Java Sync Driver `5.12.x` connects to MongoDB Server `8.0` cleanly. There is no "driver 8.0 required for server 8.0" rule.

### 5.2. Two Layers of Compatibility

1. **Protocol compatibility:** Can the driver handshake, authenticate, and send commands to the server?
2. **Feature/API compatibility:** Does the driver expose APIs for a specific server feature, and does the server support that command?

A driver that connects successfully may still **not fully support a brand-new MongoDB feature**.

### 5.3. Different Language Libraries

Node.js, Python/PyMongo, Go, C#, and Java each follow independent release trains and support matrices. This lesson uses the Java Sync Driver as its primary example, while the general rule is to consult the **compatibility table for your exact driver and language**.

---

## 6. Java Sync Driver and MongoDB Server Compatibility Table

MongoDB publishes **Client Library Compatibility Tables** using these symbols:

- **✓ Fully supported:** driver version is fully compatible with that server branch as defined by the matrix.
- **⊛ Partially supported:** can connect and operate, though not all newest server features are supported.
- **✗ Incompatible:** unsafe/unsupported connection per the matrix.
- **Blank cell:** untested/no support listed in the table; **never** assume it works.

### 6.1. Example Based on Tables Published in 2026

| Java Driver version | MongoDB Server 9.0 | MongoDB Server 8.3 | MongoDB Server 8.1–8.2 | MongoDB Server 8.0 | MongoDB Server 7.0 |
|---|---|---|---|---|---|
| **5.12–5.13** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **5.9–5.11** | ⊛ | ✓ | ✓ | ✓ | ✓ |
| **5.8** | Not listed as supported in table | ✓ | ✓ | ✓ | ✓ |
| **5.2–5.7** | Not listed as supported in table | ⊛ | ✓ | ✓ | ✓ |

This is an **instructional excerpt** to practice reading the matrix—not a substitute for the live table. The official matrix also covers servers `6.0`, `5.0`, `4.4`, `4.2`, and other driver releases. Before deploying, check:

[MongoDB Client Library Compatibility Tables](https://www.mongodb.com/docs/drivers/compatibility/?driver-language=java&java-driver-framework=java-sync)

### 6.2. Decision Examples

- App targeting Server **9.0**: MongoDB docs list Java Driver **5.12+** for full support of 9.0 in the published matrix.
- App targeting Server **8.0**: the published table shows Java Driver **5.2+** as fully compatible across those rows.
- Drivers older than an example cutoff are not automatically incompatible; look up their exact row in the official table.

### 6.3. A `✓` Mark Alone Is Still Not Enough

You must also check:

- Does the feature you want exist in your exact server patch/minor version?
- Does your deployment configuration support it?
- Is the Java runtime version supported?
- Does Spring Data / your ODM support this driver major version?
- Do auth/TLS/session settings align with your infrastructure?
- Has the driver been tested against your framework and application schema?

### 6.4. Do Not Infer from Larger/Smaller Numbers

"Driver 5.9 connects to Server 9.0" **differs from** "5.9 supports every 9.0 feature". Conversely, a Server 8.0 feature may be blocked by FCV, deployment tier, or permissions rather than the driver.

---

## 7. Java Runtime Compatibility

The Java Driver also has its own **Java version compatibility matrix**.

Per published tables:

- Java Driver **4.11–5.13** is marked compatible with Java **8, 11, 17, 21**.
- Older 4.x groups have differing compatibility marks.
- Driver 4.5–4.10 on Java 21 carries specific notes regarding virtual threads.
- Older Java runtimes have limited support and should not be assumed compatible with newer drivers.

### 7.1. Checking the JVM

~~~bash
java -version
~~~

### 7.2. Checking Driver Dependencies

Maven:

~~~xml
<dependency>
  <groupId>org.mongodb</groupId>
  <artifactId>mongodb-driver-sync</artifactId>
  <version>5.12.0</version>
</dependency>
~~~

The version is **illustrative only**. Use a verified patch version via your project's dependency management. If Spring Boot manages the driver BOM, verify whether it overrides your declared version.

Gradle dependency declaration, solely to illustrate build configuration:

~~~groovy
dependencies {
    implementation "org.mongodb:mongodb-driver-sync:5.12.0"
}
~~~

You do not need to run a build merely to understand compatibility; in real projects, builds and integration tests belong to your CI workflow.

### 7.3. Avoiding JAR Conflicts

If the classpath mixes incompatible versions of:

- `mongodb-driver-sync`.
- `mongodb-driver-core`.
- `bson`.
- Spring Data MongoDB dependencies.

the application can throw `NoSuchMethodError`, `NoClassDefFoundError`, or codec/runtime errors even when the server is compatible.

Prefer unified BOM/dependency management, lock versions, and never copy JARs manually.

### 7.4. Virtual Threads and Frameworks

JVM compatibility does not guarantee a framework or app uses virtual threads, reactive pipelines, or coroutine patterns optimally. Validate driver and framework combinations independently.

---

## 8. Upgrading the Driver Before Upgrading the Server

Suppose you want to upgrade Server 8.0 to 9.0:

~~~text
1. Record running driver/JVM/Spring versions.
2. Read the compatibility table for Server 9.0.
3. Upgrade the driver to a supported version
   while keeping Server on 8.0 if the matrix permits.
4. Canary the app against the current server.
5. Upgrade staging Server to 9.0 and FCV per procedure.
6. Test app flows, failover, auth,
   query behavior, and backup/restore.
7. Execute topology-aware production rolling upgrade.
8. Burn in before raising FCV.
~~~

### 8.1. Why Upgrading the Driver First Often Helps

A newer driver often supports **both the old and new server**, reducing the number of simultaneous changes. Still, do not apply this blindly: if a driver major bump changes API or codec behavior, test the app first.

### 8.2. When Upgrading the Driver Alone Is Not Enough

If a feature requires a newer Server/FCV, upgrading the driver will not make an older server accept the command. Sending a newer aggregation stage to an older binary throws `Unrecognized pipeline stage`.

### 8.3. When the Server Upgrades While Old Apps Keep Running

The compatibility matrix may show an older driver supports the new Server. Even so, test reconnection, failover, retries, live commands, and deprecations. Never treat "`MongoClient.connect` succeeded" as end-to-end compatibility.

---

## 9. MongoDB Wire Protocol and Capability Negotiation

### 9.1. Handshake

When connecting, the driver discovers topology and exchanges server capability metadata, e.g., via `hello`. The response includes fields like:

~~~javascript
{
  isWritablePrimary: true,
  minWireVersion: 0,
  maxWireVersion: 25,
  // other fields depending on server/topology
}
~~~

**Numeric values in this example are not a version-mapping promise.** Never hardcode `maxWireVersion` from an old blog table and infer full feature support.

### 9.2. Errors You May Encounter

- Driver does not support the server's wire protocol range.
- Server selection timeout because no primary/router is reachable.
- DNS/SRV fails to resolve the Atlas endpoint.
- Wrong replica set name.
- TLS handshake or certificate error.
- Invalid authentication mechanism or credentials.
- Misconfigured proxy or load balancer routing.

### 9.3. Do Not Confuse Connectivity Errors with Compatibility

If you see `MongoTimeoutException` or `MongoSocketException`, never jump immediately to "driver/server version mismatch". Check logs for the real root cause: DNS, TLS, auth, firewalls, or topology.

### 9.4. URI Options Have Version Constraints Too

~~~text
mongodb+srv://...
mongodb://host1:27017,host2:27017/?replicaSet=rs0
~~~

`mongodb+srv` requires DNS SRV/TXT resolution and driver support. Newer connection string options exist only in specific driver releases and are not automatically understood by older servers or drivers.

### 9.5. Mixed-Version Clusters During Rolling Upgrades

While nodes run two supported versions mid-upgrade, client topology discovery and command routing must stay compatible. Never invoke new features requiring the new FCV mid-rolling upgrade before the cluster completes the upgrade and enables the feature.

---

## 10. What Are Database Tools?

MongoDB Database Tools are a standalone suite of command-line utilities for logical backup/restore, data import/export, live statistics, and GridFS.

### 10.1. Core Utilities

| Tool | Purpose | Use Case |
|---|---|---|
| `mongodump` | Creates a BSON dump | Logical backup or dataset export |
| `mongorestore` | Restores from a BSON dump | Conditional recovery or migration |
| `bsondump` | Converts BSON dumps to readable JSON | Diagnostic sample inspection |
| `mongoexport` | Exports JSON/CSV | Data interchange |
| `mongoimport` | Imports JSON/CSV/TSV | ETL/ingestion |
| `mongostat` | Summarizes `mongod`/`mongos` activity | Quick live diagnostics |
| `mongotop` | Reports read/write time per collection | I/O hotspot diagnostics |
| `mongofiles` | Manages GridFS files | CLI upload/download/list/put/delete |

### 10.2. Database Tools Differ from `mongosh`

- `mongosh` is the interactive shell for queries and admin commands.
- `mongodump` is not a JavaScript method called inside the shell.
- `mongorestore` runs from a terminal, cmd, or PowerShell.
- `bsondump` needs no live server connection when inspecting local BSON files.
- Database Tools follow a release/version scheme separate from `mongosh` and Server.

### 10.3. Database Tools `100.x`

Since MongoDB 4.4, Database Tools have been released **independently of MongoDB Server**, starting at version **100.0.0**.

Thus:

~~~text
Server 8.0.x
Java Sync Driver 5.12.x
Database Tools 100.20.1
mongosh 2.x
~~~

is a **potentially valid** combination if every matrix condition holds. Never look for a "Database Tools `8.0.x`" release just because the server is 8.0.

### 10.4. Currently Documented Database Tools Version

At this writing, the official page documents **Database Tools 100.20.1**, which lists support for servers:

- 9.0.
- 8.3.
- 8.2.
- 8.1.
- 8.0.
- 7.0.
- 6.0.
- 5.0.
- 4.4.
- 4.2.

It **does not support** servers older than 4.2 per that table. This applies specifically to **Tools 100.20.1** and cannot be assumed for older or future `100.x` releases.

Source: [MongoDB Database Tools Compatibility](https://www.mongodb.com/docs/database-tools/).

### 10.5. Checking Local Tools

~~~bash
mongodump --version
mongorestore --version
mongoexport --version
mongoimport --version
mongostat --version
mongotop --version
mongofiles --version
mongosh --version
~~~

On Windows PowerShell:

~~~powershell
Get-Command mongodump
Get-Command mongorestore
Get-Command mongosh
~~~

`Get-Command` shows which binary `PATH` resolves first. Two versions may be installed side by side, with a newer one sitting in another folder omitted from `PATH`.

---

## 11. Four Types of "Compatibility" to Distinguish

Calling a tool/server pair "compatible" usually refers to only one dimension.

| Type | Question | Example |
|---|---|---|
| **Connection** | Can it connect, authenticate, and handshake? | Driver reads `hello` |
| **Command/API** | Does the specific command exist and work? | `$vectorSearch`, index APIs |
| **Data format** | Are persisted data, metadata, and features understood? | BSON dumps, FCV |
| **Operational** | Does it satisfy RPO/RTO, performance, security, and correctness? | Production restore, index rebuilds |

### 11.1. Database Tools Connection Support Does Not Guarantee Every Restore

`mongorestore 100.20.1` can connect to both 7.0 and 8.0, yet restoring **data dumped from Server 8.0 onto Server 7.0** may be unsupported. Always evaluate source/target versions, FCV, and archive/metadata formats.

### 11.2. Driver Compatibility Does Not Enable New Server Features on Old Servers

Java Driver 5.x can connect to Server 8.0, yet a feature introduced in Server 9.0 will not run on Server 8.0.

### 11.3. FCV Cannot Turn an Old Server into a New Server

A Server 7.0 instance does not become 8.0 by sending `setFeatureCompatibilityVersion: "8.0"`. FCV only transitions among values supported by your current server release per procedure.

### 11.4. A New Tool Does Not Replace a Backup Policy

A newer `mongodump` does not magically provide PITR without snapshots and oplog retention infrastructure.

---

## 12. Rules for Restoring MongoDB BSON Dumps: Source, Target, and FCV

MongoDB Database Tools documentation specifies requirements for restoring dumps created with `mongodump`:

- Source and target deployments should run the **same major version** or the **same Feature Compatibility Version** per docs.
- Docs also note **BSON files** can be restored to the same or a newer server version, yet **restoring into a newer server should not be used as the recommended Server upgrade procedure**.
- Ensure `mongorestore` uses the **same Database Tools version** as the `mongodump` that created the dump whenever possible.

### 12.1. Why Do Those Rules Seem Different?

Docs distinguish **BSON collection data** from **metadata, archive, and oplog replay files**. The rule that "BSON files can go into a newer server" **does not guarantee**:

- Index metadata or collection options transfer identically.
- Oplog replay is safe across versions.
- Archive formats are universally interchangeable.
- Newly persisted features will be understood by older servers.

Production plans must account for full source/target details and exact backup contents.

### 12.2. Recommended Alignment

~~~text
Source: MongoDB 8.0 / FCV 8.0
Target: MongoDB 8.0 / FCV 8.0
Tools dump: 100.20.1
Tools restore: 100.20.1
~~~

This minimizes version variables, though you must still check topology, users/roles, encrypted data, and data consistency.

### 12.3. Case Requiring Careful Scrutiny

~~~text
Source: MongoDB 9.0
Target: MongoDB 8.0
~~~

Never assume that because `mongorestore` supports both 8.0 and 9.0, a 9.0 dump restores cleanly to 8.0. Newly persisted formats may be incompatible; this is **not a standard downgrade path**.

### 12.4. Preventing "Silent Metadata Corruption"

MongoDB docs warn that restoring metadata, archive, or oplog files across differing source/target versions can trigger failures, silent errors, or corrupted metadata. Never accept a restore merely because exit code was 0; run a test restore and verify indexes, validators, data types, and business invariants.

---

## 13. `mongodump` and `mongorestore`: Controlled Examples

### 13.1. Dump a Single Database

~~~bash
mongodump \
  --uri="$SOURCE_MONGODB_URI" \
  --db=shop \
  --out=./backups/shop
~~~

This is a Linux/macOS terminal command, not `mongosh`. For sensitive data, protect backup files, process arguments/URIs, and storage permissions.

### 13.2. Dump a Compressed Archive

~~~bash
mongodump \
  --uri="$SOURCE_MONGODB_URI" \
  --archive=./backups/shop-all.archive.gz \
  --gzip
~~~

### 13.3. Restore to a Test Cluster

~~~bash
mongorestore \
  --uri="$TARGET_MONGODB_URI" \
  --archive=./backups/shop-all.archive.gz \
  --gzip
~~~

**Caution:** A full-deployment dump can include multiple databases; never aim it at a target holding important data without checking namespaces and restore options. In small labs, target an empty test database.

### 13.4. Restore a Specific Namespace

~~~bash
mongorestore \
  --uri="$TARGET_MONGODB_URI" \
  --nsInclude="shop.orders" \
  --nsFrom="shop.orders" \
  --nsTo="recovery.orders" \
  ./backups/shop
~~~

This copies the collection into a temporary namespace without overwriting production. Always verify directory structure and namespace mapping syntax.

### 13.5. What Is the Risk of `--drop`?

`mongorestore --drop` drops the target collection before restoring to prevent duplicates. In production, this can wipe newer writes. Use it only under a scoped plan with a pre-restore target backup and explicit approval.

### 13.6. Access Privileges

`mongodump` requires read privileges on target collections; `mongorestore` requires privileges to create collections, indexes, and metadata. Connecting with Database Tools does not guarantee the account holds every required role.

---

## 14. `--oplog` and `--oplogReplay`

### 14.1. Why Capture the Oplog During a Dump?

A full logical dump of a replica set takes time while writes keep arriving. `mongodump --oplog` captures oplog entries generated during the dump window so `mongorestore --oplogReplay` can bring the restore to a consistent point per supported mechanics.

### 14.2. Replica Set Lab Example

~~~bash
mongodump \
  --uri="$REPLICA_SET_SOURCE_URI" \
  --oplog \
  --archive=./backup-rs.archive.gz \
  --gzip
~~~

Restore to an **isolated** target:

~~~bash
mongorestore \
  --uri="$REPLICA_SET_TARGET_URI" \
  --archive=./backup-rs.archive.gz \
  --gzip \
  --oplogReplay
~~~

### 14.3. Important Technical Limitations

- `--oplog` applies to a **full dump** of a replica set per documentation rules and cannot be freely combined with `--db`, `--collection`, or `--query`.
- `mongorestore --oplogReplay` disallows namespace-filtering options such as `--db`, `--collection`, `--nsInclude`, `--nsExclude`, `--nsFrom`, and `--nsTo` in full-dump replay mode.
- **Sharded clusters do not support** `mongorestore --oplogReplay` in this way.
- FCV changes can trigger time-series collection format conversions across versions (e.g., transitioning 8.x ↔ 9.0), imposing special constraints on oplog replay.
- `--oplogReplay` replays only the oplog entries captured during the dump window—it does not provide arbitrary continuous PITR.

### 14.4. Do Not Confuse with Change Streams

Oplogs and Change Streams both relate to change history, yet a Change Stream consumer checkpoint is not a full database backup. Restoring the source database while consumer checkpoints point into the future must be reconciled separately.

### 14.5. Atlas Tier Restrictions

Some Database Tools flags face limits on Atlas tiers such as Free/Flex. Select backup/restore paths based on **deployment type and tier**, not solely server and tool versions.

---

## 15. `mongoexport`/`mongoimport` Do Not Replace `mongodump`/`mongorestore`

### 15.1. Intended for Data Interchange

~~~bash
mongoexport \
  --uri="$MONGODB_URI" \
  --db=shop \
  --collection=products \
  --type=json \
  --out=products.json
~~~

~~~bash
mongoimport \
  --uri="$MONGODB_URI" \
  --db=shop \
  --collection=products_imported \
  --file=products.json
~~~

### 15.2. BSON Type Fidelity

BSON includes `ObjectId`, `Decimal128`, `Date`, `Binary`, `Timestamp`, and `Int64`. Plain JSON cannot represent all of these natively.

MongoDB Extended JSON v2 (canonical/relaxed) preserves many BSON types, yet requires choosing the right mode and understanding parsing semantics. CSV discards even more type richness, arrays, and nested documents.

### 15.3. Never Treat Import/Export as a Full Backup

`mongoexport` is not a safe substitute for `mongodump` when you need:

- Collection options.
- Index definitions.
- Validators and collations.
- Exact raw BSON type fidelity.
- Atomic point-in-time consistency.
- Oplog-based restores.
- Users, roles, and privileges per policy.
- GridFS binary data across its two collections.

### 15.4. Dotted and Dollar-Prefixed Field Names

MongoDB 5.0+ supports field names containing dots or starting with `$` in certain contexts. Docs warn that `mongoimport`/`mongoexport` can handle such field names ambiguously or improperly, especially in CSV and Extended JSON wrappers.

Never assume a JSON round-trip preserves 100% of BSON documents with special keys. Test explicitly before relying on it for migrations.

### 15.5. CSV and Numbers

If `Decimal128("12.30")` is exported to CSV and re-imported with wrong type inference, it can turn into a string or double and lose precision. For monetary values, validate numeric schemas post-import.

---

## 16. `bsondump`, `mongostat`, `mongotop`, and `mongofiles`

### 16.1. `bsondump`

~~~bash
bsondump ./backups/shop/orders.bson
~~~

Converts BSON dump files to JSON for diagnostic inspection. Never treat `bsondump` output as a backup assuming JSON retains all metadata.

### 16.2. `mongostat`

~~~bash
mongostat --uri="$MONGODB_URI"
~~~

Useful for quick live overview of server activity. Output and metrics depend on Server/Tools versions, privileges, and deployment. It does not replace long-term Prometheus or Atlas monitoring.

### 16.3. `mongotop`

~~~bash
mongotop --uri="$MONGODB_URI"
~~~

Shows per-collection read/write time on supported deployments. Never assume the tool has permissions or capability across every Atlas tier.

### 16.4. `mongofiles`

CLI utility for managing GridFS files (list, upload, download, put, delete per documented flags). GridFS operations must account for non-unique filenames and multiple revisions; never use `mongofiles` to bypass application versioning or tenant isolation APIs.

### 16.5. Database Tools Compatibility Still Differs from Feature Compatibility

A `mongostat` version may connect to a server yet miss a renamed metric or require higher roles. A `mongofiles` version may read buckets without enforcing business retention or versioning. Test the exact operation.

---

## 17. Checking Installations on Linux, Windows, and Containers

### 17.1. Linux

MongoDB ships separate packages such as:

~~~text
mongodb-org-server        -> mongod
mongodb-org-mongos        -> mongos
mongodb-mongosh           -> mongosh
mongodb-database-tools    -> Database Tools
~~~

A meta-package pulls multiple components, yet individual component versions remain independent. Never read `dpkg -l mongodb-org` alone and assume every binary matches that exact number.

### 17.2. Windows

PowerShell:

~~~powershell
Get-Command mongod
Get-Command mongosh
Get-Command mongodump

mongod --version
mongosh --version
mongodump --version
~~~

If `mongodump` reports command not found, Database Tools may not be installed or added to `PATH`; do not conclude MongoDB Server lacks dump support.

### 17.3. Docker

~~~bash
docker run --rm mongo:8 mongod --version
~~~

The container holds the server binary; **never assume** the image ships the exact Database Tools or `mongosh` version you want. Depending on the image, tag, or release, use a separate tools image or install matching tools.

### 17.4. CPU Architecture

Database Tools packages target specific OS/architecture pairs such as `x86_64`/`ARM64` and specific Linux distros. Never assume an archive built for Ubuntu `x86_64` runs on macOS `ARM64` or Alpine `musl`.

### 17.5. Pin Versions

In CI and production, record exact versions for:

- Server image/package tags and digests where available.
- Database Tools `100.x` version.
- `mongosh` version.
- Java driver and BSON artifacts.
- JVM version.
- OS and CPU architecture.
- MongoDB Operator or Atlas API version if applicable.

---

## 18. Upgrade Plan for a Java Application + MongoDB Server

### 18.1. Before Changing Anything

Record the baseline:

~~~yaml
service: order-api
environment: staging
server:
  binaryVersion: "8.0.x"
  fcv: "8.0"
  topology: replica-set
driver:
  language: java-sync
  version: "5.12.x"
  javaRuntime: "21"
databaseTools:
  dumpVersion: "100.20.1"
  restoreVersion: "100.20.1"
target:
  serverVersion: "9.0.x"
  fcvAfterBurnIn: "9.0"
  backupRestoreTested: true
~~~

This is an **illustrative manifest**, not a configuration parsed directly by Atlas or MongoDB Server.

### 18.2. Step 1 — Read Compatibility Matrices and Release Notes

- Select exact source and target versions.
- Check the Java driver compatibility table.
- Check JVM and framework support.
- Read Server upgrade and downgrade procedures.
- Check Database Tools compatibility for backup/restore tooling.
- Review feature compatibility changes and deprecations.

### 18.3. Step 2 — Test Driver Upgrade Separately

Upgrade the driver in staging/canary while keeping the old server. Verify:

- Connectivity and authentication.
- CRUD.
- Aggregations.
- Index creation/listing under app privileges.
- Transactions and retries.
- Change Streams.
- Serialization (`ObjectId`, `Date`, `Decimal128`, `UUID`).
- Timeouts and connection pools.
- TLS and SRV.
- Failure recovery.

### 18.4. Step 3 — Test Backup and Restore

Take a real backup, restore to an isolated target, and validate data, metadata, and the application. Never treat backup job success as restore proof.

### 18.5. Step 4 — Upgrade the Server per Topology

- Standalone: follow the standalone upgrade guide.
- Replica set: follow the official rolling upgrade guide, checking member eligibility and elections.
- Sharded: follow the sharded cluster upgrade guide; strictly honor version-specific config server / shard / `mongos` ordering.
- Atlas: use Atlas upgrade workflows and maintenance windows—never SSH to swap binaries manually.

### 18.6. Step 5 — Burn-In Under the Old FCV

Monitor metrics, traces, and smoke tests. Do not use backward-incompatible persisted features before deciding on final FCV elevation.

### 18.7. Step 6 — Transition FCV per Procedure

This administrative action can affect downgrade eligibility. Never execute it before securing approvals and a verified backup/rollback plan.

### 18.8. Step 7 — Post-Upgrade Validation

Verify:

- Server versions across all members and routers.
- Consistent, expected FCV.
- Replica set / shard health.
- Java application operations.
- Change Stream consumers.
- Search / Vector Search index readiness if applicable.
- Backup jobs and restore tests.
- p95/p99 latency, connection pools, and errors.
- Security and audit compliance.

---

## 19. Replica Set Upgrades and the Mixed-Version Window

### 19.1. Never Update All Nodes at Once

A documented rolling upgrade updates secondaries in order, switches leadership when needed, and updates the primary last. However, **exact steps vary by version and topology**—never copy an ad-hoc homegrown script universally.

### 19.2. Mixed-Version Mode Is Temporary

During a rolling upgrade, the cluster briefly runs members on two permitted versions simultaneously. This is a transition state, never a permanent architecture.

### 19.3. Drivers Must Handle Elections and SDAM

Applications must anticipate transient errors during primary transitions; drivers rely on topology discovery and eligible retryable operations. Critical business writes still need idempotency keys to avoid duplicate side effects on retries.

### 19.4. Never Enable the New FCV Mid-Upgrade

FCV upgrades occur **only after** binaries and topology finish per procedure and pass burn-in. Enabling it early risks incompatible writes/metadata that block rollback.

### 19.5. Pre-Upgrade Backup

Maintain a restorable backup with a documented restore drill and key access. The newest snapshot alone is useless unless you know you can stand up a target matching the old version and FCV.

---

## 20. Upgrading a Sharded Cluster

### 20.1. Components

~~~text
Application
    |
   mongos
    |
    +-- Config Server Replica Set
    |
    +-- Shard 1 Replica Set
    +-- Shard 2 Replica Set
    +-- Shard 3 Replica Set
~~~

### 20.2. Why Is It Harder Than Standalone?

- Server binaries run across config servers, shard members, and `mongos`.
- Sharding metadata and routing caches interact across tiers.
- Chunk migrations, the balancer, and resharding are involved.
- Cross-shard transactions and change streams span shards.
- Backup/restore tools must respect sharded topology.

### 20.3. Never Guess the Order

You cannot upgrade `mongos` first and `mongod` afterward in arbitrary order. Follow the **official upgrade instructions** for your source/target, including balancer state, FCV, and preconditions.

### 20.4. `mongodump --oplog` Is Not a Full Sharded Backup

Never stitch together individual shard dumps and assume they form a cluster-consistent recovery point. Use backup solutions and consistency procedures built for sharded clusters.

### 20.5. Drivers May Connect Mid-Upgrade Yet Hit Edge Cases

Sensitive operations—transactions, change streams, new feature calls, or chunk migrations—face extra constraints. Integration tests must cover real sharded workloads.

---

## 21. Atlas vs. Self-Managed Upgrades

### 21.1. Atlas

- Atlas manages server provisioning, nodes, and upgrade workflows.
- Maintenance windows and auto-upgrades depend on tier and contract.
- Some admin operations are restricted.
- Backup/restore capabilities depend on cluster tier and plan.
- Search / Vector Search have dedicated deployment mechanics.
- Never alter binaries directly on managed hosts.

### 21.2. Self-Managed

- Operations team manages OS packages, MongoDB binaries, and procedures.
- Controls FCV, topology, snapshots, backup tools, and downtime.
- Must prepare an upgrade rollback path aligned with support policy.
- Self-manages TLS, users, storage, and monitoring.

### 21.3. A Developer Laptop Is Not Production

Connecting to a local standalone instance and restoring 1 GiB proves nothing about RTO on a 5 TiB sharded production cluster. Test in staging matching production topology, indexes, scale, and roles.

---

## 22. Diagnosing Server/Driver Errors

### 22.1. Wire Version Mismatch

Symptom: driver reports it does not support the server's wire protocol range or incompatible server wire version.

Action:

1. Check the exact driver version in resolved runtime dependencies.
2. Check server `db.version()` and `hello`.
3. Consult the Client Library Compatibility Tables.
4. Upgrade the driver per matrix; never try hardcoding `maxWireVersion`.
5. Retest with the exact JVM and framework.

### 22.2. `MongoTimeoutException`

Do not assume a version mismatch immediately. Check:

- DNS/SRV resolution.
- Firewall / IP allowlist.
- TLS.
- Wrong replica set name or URI.
- No primary.
- Connection pool exhaustion.
- Network routing or latency.
- Server saturation.

### 22.3. Authentication Failure

Driver and server may lack a shared authentication mechanism, or credentials/`authSource` may be wrong. Inspect error codes and auth mechanism docs; never disable authentication in production just to test.

### 22.4. TLS Handshake Failure

Check CA, certificate hostname/SAN, TLS protocol versions, JDK truststore, and server cert rotation. Never disable TLS certificate validation in production.

### 22.5. Unsupported Command or Stage

If Java sends a newer command and an older Server rejects it as unrecognized, the server needs the corresponding capability, tier, or FCV. Updating the driver alone will not add it to an older server.

### 22.6. Serialization Errors

`CodecConfigurationException`, `ClassCastException`, or `NoSuchMethodError` often point to codec/POJO mapping or JAR dependency conflicts rather than server version directly. Inspect the dependency tree and BSON type handling.

---

## 23. Diagnosing Database Tools Errors

### 23.1. `mongodump: command not found`

The tool is missing or not on `PATH`. It does not mean MongoDB Server cannot be backed up.

### 23.2. Tool Reports Version 100.x

This is the independent tools version—not an error just because Server is 8.x or 9.x.

### 23.3. Cannot Connect to Server

Verify URI, TLS, auth, DNS, and supported server versions for that exact Tools release. Separate connection errors from incompatible dump data.

### 23.4. `mongorestore --oplogReplay` Fails

Verify the dump was created with full `mongodump --oplog`, a replica set topology, an archive containing the oplog, no conflicting namespace filters, and no version/FCV conversion issues.

### 23.5. Duplicate Keys During Restore

If the target already holds documents or indexes, restoring into it triggers duplicate `_id` or unique index conflicts. Restore into an empty target or plan an explicit overwrite—never enable `--drop` accidentally.

### 23.6. Restoring an Old Dump to a Newer Target

BSON files follow different compatibility rules from metadata, archives, and oplogs. Match the `mongorestore` version to `mongodump` where possible, verify source/target server and FCV, and validate in an isolated environment.

### 23.7. `mongoimport` Alters BSON Types

Check `--type`, `--jsonFormat`/Extended JSON inputs, field types, CSV parsing flags, and numeric precision. Never rely on CSV round-trips for financial data without schema validation.

### 23.8. Failed Restores Aren't Only Non-Zero Exit Codes

Metadata or definitions can still be broken even when documents load. Verify validators, indexes, TTLs, collations, collection options, and business invariants.

---

## 24. Compatibility of Advanced Features

### 24.1. Transactions

Requires supporting server topology/version plus matching driver session/transaction APIs. Never assume an old standalone `mongod` supports multi-document transactions just because the Java Driver exposes `ClientSession`.

### 24.2. Change Streams

Requires a supporting topology with oplog/change history. After an upgrade or restore, resume tokens become invalid if history was lost or the source rolled back. Prepare consumer bootstrap/reconciliation logic.

### 24.3. Time-Series Collections

Time-series internals evolved across major versions, including persisted formats and FCV behavior. Database Tools docs explicitly warn about `mongorestore --oplogReplay` when the oplog spans a time-series format conversion between 8.x and 9.0.

### 24.4. Search / Vector Search

A Java Driver can construct a `$vectorSearch` pipeline, yet execution depends on server version, deployment tier, Search service, indexes, and patch support. Self-managed vs. Atlas availability differs; never infer feature availability from driver compatibility alone.

### 24.5. Queryable Encryption / CSFLE

`mongorestore` carries documented limitations for collections using Queryable Encryption or Client-Side Field Level Encryption. Follow dedicated encrypted backup/restore procedures including KMS/key management rather than running generic dump/restore blindly.

### 24.6. Indexes and Schema Validation

An index or validator created with a newer feature can block downgrades or restores into older servers. Review release notes and feature compatibility matrices before rolling back.

### 24.7. UUID / BSON Representation

Different languages and driver versions handle UUID binary subtypes differently. When migrating Java Drivers or importing/exporting data, verify UUID representation so ID lookups never silently miss. Add round-trip tests for UUID, `ObjectId`, `Decimal128`, `ZonedDateTime`/`Instant`, arrays, and null/missing fields.

---

## 25. Java Runtime: Checking the Active Driver Version

### 25.1. Declared Dependencies Do Not Always Equal Runtime Dependencies

Maven or Gradle resolution can pick a different version than expected. Frameworks and transitive dependencies can override versions, or containers can package stale artifacts.

### 25.2. Example: Reading Package Metadata

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public class DriverDiagnostics {

    public static void main(String[] args) {
        Package p = MongoClient.class.getPackage();

        System.out.println(
            "Implementation version: "
            + p.getImplementationVersion()
        );

        String uri =
            System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                "Missing MONGODB_URI"
            );
        }

        try (MongoClient client =
                 MongoClients.create(uri)) {

            System.out.println(
                client.getDatabase("admin")
                    .runCommand(
                        new org.bson.Document("ping", 1)
                    )
                    .toJson()
            );
        }
    }
}
~~~

**Note:** `Package.getImplementationVersion()` can return `null` depending on how JARs are packaged; never rely on it alone. In production, inspect the resolved dependency tree and build manifest as well.

### 25.3. Never Log Secrets

During diagnostics, never print connection URIs containing passwords or tokens to logs. Use redaction and proper credential management.

### 25.4. Connection Pool and Timeout Changes

After a major driver upgrade, review connection pool sizing, default timeouts, retry behavior, compression, and telemetry. Server compatibility does not guarantee identical performance defaults.

---

## 26. Smoke Tests After Upgrading Server or Driver

A smoke test should verify more than `ping`.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class MongoSmokeTest {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                "MONGODB_URI required"
            );
        }

        try (MongoClient client =
                 MongoClients.create(uri)) {

            MongoDatabase db =
                client.getDatabase(
                    "mongo_compat_lab"
                );

            db.runCommand(
                new Document("ping", 1)
            );

            MongoCollection<Document> coll =
                db.getCollection("smoke");

            String testId =
                "smoke-test-2026-11-14";

            coll.updateOne(
                new Document("_id", testId),
                new Document(
                    "$set",
                    new Document(
                        "kind", "COMPAT"
                    )
                ),
                new com.mongodb.client.model
                    .UpdateOptions()
                    .upsert(true)
            );

            Document found =
                coll.find(
                    new Document(
                        "_id", testId
                    )
                ).first();

            if (found == null) {
                throw new IllegalStateException(
                    "Read after write failed"
                );
            }

            System.out.println(
                "CRUD smoke test passed"
            );
        }
    }
}
~~~

This example runs on a **lab/staging database**; never write test records into production collections without explicit controls. In real suites, add cleanup and avoid hardcoded IDs that could collide across concurrent runners.

### 26.1. Broader Test Coverage

- CRUD with read/write concerns.
- Indexed aggregations.
- Multi-document transactions if used by the business domain.
- Change stream resume/restarts.
- Retryable writes and failover.
- `Decimal128`, `UUID`, and `Date` serialization.
- TTL and unique indexes.
- Atlas Search / Vector Search where applicable.
- Auth, TLS, SRV, and pool saturation.
- Post-upgrade backup/restore.

---

## 27. Difference Between Connectivity Testing and Data Testing

### 27.1. Can Connect

~~~text
Driver -> TLS/auth/hello -> server OK
~~~

This proves only basic connectivity.

### 27.2. CRUD Correctness

All BSON types, unique constraints, codecs, and read/write concerns must behave properly.

### 27.3. Business Consistency

Orders, payments, and inventory invariants must hold; triggers, events, and retries must not duplicate actions. A newer server might alter a query plan (changing latency while keeping results accurate), whereas a driver migration might alter UUID encoding so lookups miss documents.

### 27.4. Backup/Restore Correctness

Dumps taken after an upgrade may require updated targets, FCVs, or Tools versions. Confirm a genuinely compatible backup and restore target—not merely "the backup job wrote a file".

---

## 28. Restore Drill Across Two Database Tools Versions

### 28.1. Do Not Mix Versions Accidentally

For example, Team A creates an archive with `mongodump 100.20.1`, while Team B restores with `mongorestore 100.5.x` on an older CI runner.

Even when it happens to work, docs recommend **matching dump and restore tool versions** to avoid archive/metadata format mismatches.

### 28.2. Safe Procedure

1. Record the dump tool version: `mongodump --version`.
2. Record source Server binary and FCV.
3. Record deployment topology.
4. Store checksums of the archive/BSON files.
5. Record dump flags (`--oplog`, `--archive`, `--gzip`, filters).
6. Install the matching tool version for restore.
7. Provision a target with compatible Server/FCV.
8. Run a test restore in an isolated environment.
9. Compare counts, sampled records, indexes, validators, and GridFS contents if applicable.
10. Record elapsed time, errors, and business sign-off.

### 28.3. RPO/RTO

A successful `100.x` dump alone does not prove RPO/RTO. Logical BSON restores on large clusters can take hours and exclude index/search rebuilds, validation, and traffic cutover.

---

## 29. Sample Decision Matrix

| Scenario | Assessment | Watch Out For |
|---|---|---|
| Server 8.0 + Java Driver 5.12 | Supported per driver matrix | Feature-specific gates |
| Server 9.0 + Java Driver 5.9 | Partially compatible per matrix | Missing some 9.0 features |
| Server 9.0 + Java Driver 5.12 | Fully compatible per matrix | Still needs JVM/framework/feature tests |
| Server 8.0 + Tools 100.20.1 | Tools support Server 8.0 | Match dump source/target FCV |
| Server 4.0 + Tools 100.20.1 | Outside server support list | Do not use for production |
| Dump 8.0 → Restore 8.0 same FCV | Much easier to control | Still verify encrypted data and indexes |
| Dump 9.0 → Restore 8.0 | Never assume compatibility | New persisted formats / downgrade rules |
| JSON export → import | Data interchange | BSON type and metadata loss |
| `--oplogReplay` on sharded cluster | Unsupported per docs | Does not produce consistent cluster restore |
| Server upgraded but old FCV | Valid intermediate state per procedure | New features may remain off |
| New FCV enabled before burn-in | Downgrade risk | Backward-incompatible persisted state |
| Atlas Search index restore | Depends on restore mode | Index data may need rebuild/sync |

This table is a **reasoning framework**, not a substitute for testing in a real environment.

---

## 30. Common Misconceptions

**Misconception 1:** "Server 8.0 needs Java Driver 8.0."  
Drivers follow independent release trains; check the support matrix.

**Misconception 2:** "Tools 100.x means Server 100.x."  
Database Tools adopted independent `100.x` versioning starting in MongoDB 4.4.

**Misconception 3:** "`mongosh --version` shows the Atlas version."  
It shows only the local shell version.

**Misconception 4:** "`db.version()` shows driver and tools versions."  
It reports only the server endpoint version.

**Misconception 5:** "Upgrading the server binary automatically raises FCV."  
FCV transitions separately per procedure.

**Misconception 6:** "Raising FCV doesn't affect downgrades."  
FCV can enable backward-incompatible persisted features.

**Misconception 7:** "If the driver connects, every feature is supported."  
Matrix entries distinguish full vs. partial support alongside feature gates.

**Misconception 8:** "A blank cell in the driver matrix means it works."  
It means untested or unsupported; never assume.

**Misconception 9:** "The newest driver always supports every old server."  
Check EOL entries, compatibility tables, and API/binary changes.

**Misconception 10:** "Any Java runtime works with the same driver."  
Verify the JVM compatibility matrix.

**Misconception 11:** "Maven declared version X, so runtime definitely uses X."  
BOMs, transitive overrides, or stale artifacts can change runtime versions.

**Misconception 12:** "`NoSuchMethodError` is a MongoDB Server bug."  
Usually a JAR version conflict on the classpath.

**Misconception 13:** "Wire protocol handshake success proves business data works."  
You still need CRUD, codec, schema, and transaction tests.

**Misconception 14:** "`mongodump 100.x` supports Server 9.0, so a 9.0 dump restores onto Server 7.0."  
Connection support differs from data/FCV compatibility.

**Misconception 15:** "`mongoexport` JSON replaces BSON backups."  
Risks losing type fidelity, metadata, and index definitions.

**Misconception 16:** "`--oplogReplay` turns a full dump into unlimited PITR."  
It replays only oplog entries captured during that dump, with strict limits.

**Misconception 17:** "Sharded clusters use `--oplogReplay` just like replica sets."  
Unsupported in that form.

**Misconception 18:** "Having an archive guarantees restore succeeds."  
Depends on tool version, source/target version/FCV, integrity, and key access.

**Misconception 19:** "Database Tools are preinstalled in every MongoDB Docker image."  
Inspect the exact image binaries.

**Misconception 20:** "All MongoDB 8.x releases support the exact same features."  
Depends on release train, patch, edition, and deployment type.

**Misconception 21:** "Production upgrades replace all nodes at once."  
Follow topology-specific rolling upgrade procedures.

**Misconception 22:** "Changing version after an upgrade is a simple rollback."  
Depends on FCV and persisted incompatibilities.

**Misconception 23:** "Atlas upgrades work like SSHing into self-managed nodes to swap binaries."  
Atlas is a managed platform.

**Misconception 24:** "Restoring documents alone is enough without checking indexes/validators."  
Metadata and query readiness may be missing or broken.

**Misconception 25:** "One `ping` test in staging is enough."  
Run backup/restore drills and realistic business integration tests under load.

---

## 31. Pre-Upgrade Checklist

### 31.1. Environment Survey

- [ ] Source Server version, patch, topology, and edition.
- [ ] Target Server version and supported upgrade path.
- [ ] Current FCV and target FCV.
- [ ] Actual runtime Java Driver version.
- [ ] JVM version and Spring Data / framework compatibility.
- [ ] Database Tools versions used for dump and restore.
- [ ] `mongosh` / Atlas CLI versions.
- [ ] OS/CPU architecture and container image.
- [ ] Authentication, TLS, URI, and DNS/SRV.
- [ ] Search/Vector Search, encryption, time-series, transactions, and sharding.
- [ ] RPO/RTO and business recovery scope.

### 31.2. Compatibility Verification

- [ ] Driver/server matrix shows appropriate support mark.
- [ ] Feature-specific minimum Server versions verified.
- [ ] FCV preconditions verified for the upgrade path.
- [ ] Server downgrade policy reviewed.
- [ ] Database Tools version compatible with server.
- [ ] Source/target dump major version and FCV aligned.
- [ ] Matching Database Tools version used for dump and restore where possible.
- [ ] Oplog and sharded constraints checked.
- [ ] BSON and Extended JSON type semantics verified.
- [ ] Permissions and encryption key access confirmed.

### 31.3. Staging / Canary

- [ ] CRUD + aggregations + unique indexes.
- [ ] Transactions and change streams if used.
- [ ] Codec round trips (`ObjectId`, `UUID`, `Decimal128`, dates).
- [ ] TLS, auth, and network failure tests.
- [ ] Retryable writes and failover tests.
- [ ] Search / Vector Search readiness.
- [ ] Query latency p95/p99 under load.
- [ ] Backup created and restore verified.
- [ ] Unified driver dependency graph.
- [ ] Explicit rollback decision window defined.

### 31.4. Production Rollout

- [ ] Maintenance and notification plan.
- [ ] Backup/snapshot preflight complete.
- [ ] Official rolling/sharded procedure followed.
- [ ] Burn-in completed before raising FCV.
- [ ] Canary traffic and alerts active.
- [ ] All nodes and routers confirmed upgraded.
- [ ] Recovery runbook and on-call staffed.
- [ ] Post-upgrade backup/restore test complete.
- [ ] Business sign-off obtained.

---

## 32. Hands-On Exercises

### Exercise 1 — Distinguishing Versions

A system runs Server 8.0, FCV 7.0, Java Driver 5.12, Tools 100.20.1, and `mongosh` 2.x. Explain why differing numbers do not indicate a "version mismatch".

### Exercise 2 — Inspecting the Environment

Capture `db.version()`, `buildInfo`, and `getParameter featureCompatibilityVersion` from a lab cluster; compare against local `mongodump --version` and `mongosh --version`.

### Exercise 3 — Reading the Java Driver Matrix

Using the published matrix, evaluate Java Driver 5.9 with Server 9.0 and explain what partially compatible means.

### Exercise 4 — Selecting a Driver

An app is preparing to upgrade Server 8.0 → 9.0. Recommend a supported driver and Java runtime from the official compatibility matrix, listing pre-upgrade tests needed.

### Exercise 5 — Dependency Conflict

Suppose an app declares `mongodb-driver-sync:5.x` while a framework pulls an older transitive `bson` version. Describe runtime symptoms and how to enforce unified dependency management.

### Exercise 6 — FCV

Diagram the timeline: 7.0 binaries/FCV → 8.0 binaries/old FCV → 8.0 new FCV. Why shouldn't FCV be raised immediately during the rolling upgrade?

### Exercise 7 — Docker

Run a MongoDB Server container in a lab, check `mongod --version`, and verify whether `mongodump` is actually installed inside that image.

### Exercise 8 — Dump/Restore

Create an archive with a recorded Database Tools version, restore to a lab target sharing the same Server major version/FCV, and reconcile counts and indexes.

### Exercise 9 — Cross-Version Restore

Compare source 8.0 → target 9.0 against source 9.0 → target 8.0. Distinguish BSON data files, metadata/archives, and official upgrade paths.

### Exercise 10 — Oplog Replay

Write commands for a full replica set dump with `--oplog` and restore with `--oplogReplay`. Explain why it is not used that way for sharded clusters.

### Exercise 11 — BSON vs. JSON

Export a document containing `ObjectId`, `Decimal128`, `Date`, and `Binary` via `mongoexport`; re-import with `mongoimport` and inspect resulting types.

### Exercise 12 — Compatibility Smoke Test

Write a Java smoke test covering `ping`, insert/update/find, aggregation, and `Decimal128` codec round-trip, cleaning up in a lab database.

### Exercise 13 — Auth/TLS Failure

Describe how to distinguish a server version mismatch from a certificate validation error or a DNS SRV resolution failure.

### Exercise 14 — Atlas

Design a Server upgrade plan on Atlas Dedicated with a Java backend. Separate Atlas-managed steps from application tests your team must run.

### Exercise 15 — Replica Set

Design a rolling upgrade plan based on the official upgrade guide, covering election/failover monitoring and business transactions.

### Exercise 16 — Sharding

Identify all components requiring upgrades in a sharded cluster and explain why a simple standalone script cannot be applied.

### Exercise 17 — Change Streams

After an upgrade or restore, a consumer hits an invalid resume token. Design bootstrap/rebuild logic that avoids dropping events.

### Exercise 18 — Search / Vector Search

A Java Driver can send `$vectorSearch`, yet the server deployment rejects it. Analyze why client compatibility does not guarantee feature availability.

### Exercise 19 — Restore Runbook

Document backup ID, Tools versions, source/target binary/FCV, archive checksum, encryption key handling, validation steps, and measured RTO.

### Exercise 20 — Rollback

After upgrading to Server 9.0, the system used a persisted feature incompatible with 8.0. Why is "reinstalling the 8.0 binary" not a guaranteed rollback plan?

---

## 33. Review Questions

1. What is the server binary version?
2. How does FCV differ from the server version?
3. When should FCV be raised after an upgrade?
4. Why can downgrades become restricted after FCV activation?
5. How does `mongod` differ from `mongos`?
6. What does `mongosh --version` tell you?
7. What does `db.version()` tell you?
8. Which command retrieves FCV?
9. What does wire protocol compatibility mean?
10. Why does a successful handshake not prove full feature support?
11. Does Driver 5.x require Server 5.x?
12. How do fully and partially compatible entries differ?
13. What does a blank cell in a compatibility table mean?
14. Why does the Java runtime have its own compatibility matrix?
15. What errors can a Spring Data / BSON version conflict cause?
16. Since when have MongoDB Database Tools used independent versioning?
17. What does Tools `100.x` mean?
18. Which Server versions does Tools 100.20.1 support per current docs?
19. Which binaries are included in Database Tools?
20. How does `mongodump` differ from `mongoexport`?
21. How does `mongorestore` differ from `mongoimport`?
22. Why are JSON/CSV not substitutes for BSON backups?
23. Which BSON types easily lose precision across import/export?
24. What is the source/target major version or FCV rule for restores?
25. Why do BSON data and metadata/archive/oplog files have different compatibility rules?
26. Why should dump and restore use the same Tools version?
27. Which deployment type supports `--oplog`?
28. Does `--oplogReplay` provide arbitrary PITR?
29. Can sharded clusters use `--oplogReplay` like replica sets?
30. Why does Tools supporting a server version not prove cross-version dump restores work?
31. How do TLS/auth/network failures differ from wire version mismatches?
32. Why should you check the exact binary resolved by `PATH`?
33. Does running the `mongo:8` container guarantee Database Tools are installed?
34. Can a newer driver enable new features on an older server?
35. Does a newer server always allow a feature if FCV hasn't been raised?
36. When do you choose a rolling upgrade?
37. Why is a mixed-version cluster only a transitional phase?
38. Which extra components must be checked during sharded upgrades?
39. How do Atlas and self-managed upgrades differ?
40. What smoke tests beyond `ping` should be run?
41. Why can query plans and performance shift after an upgrade?
42. How can UUID representation break lookups?
43. Why does Queryable Encryption require dedicated restore procedures?
44. Can Search indexes need rebuilding after a restore?
45. How do you confirm a rollback path is supported?
46. Does a successful backup job prove RTO is met?
47. Why is changing driver, server, and tools simultaneously hard to troubleshoot?
48. When should you test restores onto an isolated target?
49. Which fields belong in a version inventory?
50. Why must compatibility be evaluated per feature rather than by major version alone?

---

## 34. Summary

**MongoDB Server, Drivers, and Database Tools are three independently versioned product lines**, while FCV governs backward-incompatible persisted features inside a deployment.

- **Server** governs the query engine, commands, storage, feature availability, and topology.
- **FCV** gates newer persisted features; upgrading binaries does not automatically change FCV.
- **Drivers** govern connectivity, codecs, retries, and client APIs; verify both Server and Java runtime matrices.
- **Database Tools** carry `100.x` versions; server connection support does not mean any source dump restores safely onto any target server.
- **`mongosh`** follows its own release train and does not represent Server version.
- **BSON dump/restore** and **JSON/CSV import/export** serve different purposes with very different metadata and type fidelity.
- **Upgrades** require topology/edition-specific procedures, staging tests, backup drills, burn-in, and controlled FCV elevation.
- **Rollbacks** are more than swapping old binaries; evaluate FCV, persisted data, feature usage, and downgrade policies.

The reliable decision flow is **capture an exact inventory → consult compatibility matrices → verify feature-specific gates → test thoroughly in staging → upgrade per official procedure → validate data, apps, and recoverability**.

## Official MongoDB Documentation

- [MongoDB Client Library Compatibility Tables — Java Sync](https://www.mongodb.com/docs/drivers/compatibility/?driver-language=java&java-driver-framework=java-sync)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [MongoDB Java Sync Driver Release Notes](https://www.mongodb.com/docs/drivers/java/sync/current/reference/release-notes/)
- [MongoDB Database Tools — Overview, Versioning, Compatibility](https://www.mongodb.com/docs/database-tools/)
- [MongoDB Database Tools — Install](https://www.mongodb.com/docs/database-tools/installation/)
- [mongodump Documentation](https://www.mongodb.com/docs/database-tools/mongodump/)
- [mongodump Compatibility and Installation](https://www.mongodb.com/docs/database-tools/mongodump/mongodump-compatibility-and-installation/)
- [mongorestore Documentation](https://www.mongodb.com/docs/database-tools/mongorestore/)
- [mongorestore Compatibility and Installation](https://www.mongodb.com/docs/database-tools/mongorestore/mongorestore-compatibility-and-installation/)
- [mongorestore Behavior, Access and Usage](https://www.mongodb.com/docs/database-tools/mongorestore/mongorestore-behavior-access-usage/)
- [mongoexport Documentation](https://www.mongodb.com/docs/database-tools/mongoexport/)
- [mongoimport Documentation](https://www.mongodb.com/docs/database-tools/mongoimport/)
- [bsondump Documentation](https://www.mongodb.com/docs/database-tools/bsondump/)
- [MongoDB Manual — Feature Compatibility Version](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/)
- [MongoDB Manual — MongoDB Versions and Upgrade Paths](https://www.mongodb.com/docs/manual/administration/upgrade/)
- [MongoDB Manual — Upgrade from 7.0 to 8.0](https://www.mongodb.com/docs/manual/release-notes/8.0/)
- [MongoDB Manual — MongoDB 8.2 Release Notes](https://www.mongodb.com/docs/manual/release-notes/8.2/)
- [MongoDB Manual — Upgrade from 8.0 to 9.0 Replica Set](https://www.mongodb.com/docs/manual/release-notes/9.0-upgrade-from-8.0-replica-set/)
- [MongoDB Manual — Upgrade from 8.0 to 9.0 Sharded Cluster](https://www.mongodb.com/docs/manual/release-notes/9.0-upgrade-from-8.0-sharded-cluster/)
- [MongoDB Manual — Backup Methods](https://www.mongodb.com/docs/manual/core/backups/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
