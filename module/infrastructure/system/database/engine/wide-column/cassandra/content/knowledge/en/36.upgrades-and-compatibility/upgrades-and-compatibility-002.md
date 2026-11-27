# Reading Release Notes, Deprecated Features, and Changed Parameters

> **Chapter:** Upgrades and Compatibility  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Scope:** Apache Cassandra — a distributed wide-column database; focusing on partition keys, query-driven table design, consistency levels, CQL, replication, compaction, repair, error handling, and Java connectivity.

## 1. Why Must You Read Release Notes Before Upgrading?

A Cassandra cluster can operate smoothly before an upgrade yet fail after switching versions even when **schema and data remain unchanged**. Typical causes include:

- Parameters in **cassandra.yaml** or JVM options were renamed, deprecated/removed, or had their default values changed.
- The new Cassandra version requires a different **JDK** range, changing garbage collectors, JVM flags, or memory allocation behavior.
- CQL, authentication, TLS, the native protocol, or returned metadata behave differently in ways the Java application/driver is not yet compatible with.
- **nodetool**, backup/restore, repair, streaming, or compaction behave or accept options differently than before.
- The new version writes SSTables or metadata incompatible with "rolling back" by simply reinstalling the old binary.
- A changed default allows the application to keep running, but with unexpected timeouts, latency, replica participation, or security policies.

Therefore, **release notes** are not merely a list of new features. For Cassandra, they are the input used to build **a compatibility matrix, an actionable change list, a test plan, and a recovery plan** before moving any production node to the new version.

### What Should You Be Able to Do After This Lesson?

1. Locate the right documentation types for **the source version, target version, and mandatory intermediate releases**.
2. Distinguish **deprecated**, **removed**, **renamed**, **default changed**, **behavior changed**, and **known issue**.
3. Cross-check actual configuration, including parameters **relying on defaults**, against the target version's guidance.
4. Identify impacts on the Cassandra cluster, Java driver, CQL/schema, replication, compaction/repair, and backups.
5. Turn every notable change into a verification test with an owner, risk level, and stop condition.
6. Explain why **rolling back with the old binary** can be unsafe after certain data upgrade steps.

> **Note:** This lesson teaches how to read and apply change documentation. Exact parameter names, supported versions, operation order, and compatibility limits **must be checked in the documentation of the exact Cassandra version and distribution in use**. Illustrative example tables are clearly marked so they are not mistaken for official release announcements.

## 2. Read the Right Documents and the Right Upgrade Path

### 2.1. Different Documents Serve Different Purposes

| Document type | What question does it answer? | Output to record in the plan |
|---|---|---|
| **Release notes / changelog** | What bugs were fixed, added, or changed in behavior in this version? | List of changes relevant to the workload |
| **Upgrade guide** | Is direct upgrade from the source version supported? What are the node order, compatibility steps, and post-upgrade commands? | Verified upgrade path and runbook |
| **Breaking changes / migration notes** | Which APIs, storage formats, CQL, parameters, or features must be migrated? | Mandatory remediation items |
| **Configuration reference** | What are the key names, data types, ranges, defaults, and constraints of the target version? | Old/new configuration mapping table |
| **Compatibility matrix** | Are Cassandra, JDK, Java driver, native protocol, backup tools, and OS compatible? | Supported version matrix |
| **Known issues / limitations** | Which cases are unsafe, have workarounds, or require delaying the upgrade? | Risk/stop gate and suitable target version |
| **Security advisories** | Are there security issues requiring patches or configuration changes? | Priority, mitigation, and verification |

**Do not substitute a changelog for an upgrade guide.** A bug fix may require no action, whereas a mandatory multi-hop upgrade step might only be stated explicitly in migration notes or the upgrade guide.

When using a vendor-packaged Cassandra distribution or a managed service, you must also read **the vendor's official documentation**: ability to edit **cassandra.yaml**, supported JDK/driver ranges, snapshots, backups, and rolling upgrade schedules may differ from self-managed Apache Cassandra.

### 2.2. Avoid Confusing Four Types of "Versions"

- **Cassandra server:** version running on the nodes; minor/major/patch releases all matter for bugs and compatibility.
- **JDK/JVM:** server runtime; constrained by the Cassandra version and packaging.
- **Java driver:** client library connecting over the native protocol; has its **own** lifecycle and release notes separate from the server.
- **SSTable/tooling:** file formats and loading, backup, and repair tools can change across versions; must be verified against real data.

For example, a newer Cassandra cluster may still serve an older driver within **the supported protocol range**, but that does not prove all driver features, codecs, retry policies, or metadata handling are safe. You must verify **server ↔ native protocol ↔ driver ↔ application JDK**.

## 3. Lock In Exact Source and Target Versions

Before jumping to "What's New," create a context record:

~~~text
Cluster:             <cluster-id>
Distribution:        Apache Cassandra / vendor / managed service
Source Cassandra:    <major.minor.patch + build>
Target Cassandra:    <major.minor.patch + build>
Source server JDK:   <distribution + version>
Target server JDK:   <supported distribution + version>
Java Driver:         <artifact + version>
Application JDK:     <version>
DC / rack / RF:      <actual topology>
OS / container:      <environment>
SSTable:             <current format, if known>
Backup/repair tools: <name + version>
Collection date:     <UTC timestamp>
~~~

These values must come from **the running cluster and the build to be deployed**. Do not treat versions written in internal docs months ago as truth if nodes have since been patched. A cluster might also be in a **mixed-version** state from an earlier maintenance window; inventory **every node**.

### 3.1. Safe Observation Commands

On an authorized cluster and host:

~~~bash
# Node status in the cluster, datacenter, and general token/rack overview.
nodetool status

# Node information, including Cassandra version when supported.
nodetool info

# Cluster/schema structure as supported by the cqlsh version in use.
cqlsh
~~~

In **cqlsh**:

~~~sql
-- Local query: returns the server version that this connection hits.
SELECT release_version, schema_version
FROM system.local;

-- Inspect metadata of the keyspace in use.
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'shop';
~~~

**system.local** reflects the connected node, not automatically every node. Collect the version and state of **each node** using appropriate tooling/metrics. System table queries may vary across deployments; verify the system schema on the running version.

If configuration is generated by Helm, Ansible, container images, or a managed service, record both **the deployment manifest and the effective configuration after startup**, because files in Git do not always match runtime values.

### 3.2. Read Every Hop, Not Just Endpoints

Suppose the official documentation allows the following path:

~~~text
Version A  ->  Version B  ->  Version C
     \______________________________/
             final target
~~~

You must read the changes for **A → B**, **B → C**, and all relevant patch releases. A feature **deprecated** in B and **removed** in C may not appear prominently in C's "new features" section.

Confirm:

1. **Is a direct upgrade supported?** If not, what are the mandatory intermediate hops?
2. How long is a **mixed-version window** allowed, and under what CQL/schema and feature constraints?
3. Are **node operation order** and post-upgrade tasks constrained?
4. Is there a requirement to **upgrade the driver or JDK before/after the server**?
5. Do SSTable formats and internode protocols allow **downgrade/rollback**?

Never invent an upgrade path by assuming "newer is always compatible."

## 4. Classify Changes to Know Required Actions

### 4.1. Six Critical Categories

| Category | Practical meaning | Required action |
|---|---|---|
| **Deprecated** | Feature/parameter may still work for some releases but is scheduled for removal | Locate usages, schedule replacement, track removal milestone |
| **Removed** | Target version no longer supports the legacy mechanism | Migrate **before** deploying; fail gate if dependencies remain |
| **Renamed / moved** | Parameter name, config location, or interface changed | Migrate key/location, remove old key, verify at runtime |
| **Default changed** | Behavior changes even without editing config | Record source/target defaults; decide whether to set explicitly or accept |
| **Behavior / semantic changed** | CQL, API, timeout, repair, compaction, or security behavior changed | Test behavior and failure cases, not just startup |
| **Known issue / limitation** | Target version has a known bug or restricted upgrade path | Assess impact, choose patch/workaround, or postpone |

A release entry can also be a **performance improvement**, **bug fix**, or **new feature**. Those still need review if the application previously relied on old buggy behavior, used internal APIs, or has strict latency SLAs.

### 4.2. Deprecated Does Not Mean Removed

**Deprecated** is a planned transition signal, **not a guarantee** that the feature works in every subsequent release. **Removed** is a blocker that must be fixed before upgrading to the version that removes it.

Hypothetical example, solely to practice reading:

> "Option **old_mode** deprecated in A; removed in B. Use **new_mode** instead."

Correct action:

1. Find every reference to **old_mode**: config files, IaC, env vars, scripts, CLI flags, node provisioning docs.
2. Verify whether **new_mode** has the same data type and semantics.
3. Update deployments **before** nodes run version B; inspect startup, logs, and effective values.
4. Confirm no code or script still depends on the legacy option.

**old_mode/new_mode are fictional placeholders, not real Cassandra parameters.** In real work, use only exact names from the target version's official documentation.

### 4.3. Default Changed Is Often Hardest to Spot

Suppose **parameter P** was omitted from the config file because the cluster relied on the old version's default. Upon upgrading, P's new default differs:

| Before upgrade | After upgrade | What matters |
|---|---|---|
| P omitted from config, default is X | P omitted from config, default is Y | Behavior changes silently even with zero Git diff |
| P explicitly set to X | P keeps value X if still valid | Can preserve old behavior, but support must be verified |
| P was renamed or removed | Old key remains in file | May fail startup, warn, or be ignored depending on version |

**Comparing two `cassandra.yaml` files is not enough**; compare **source default, target default, and actual loaded values**. Do not copy an old config file verbatim onto a new binary, as it may carry obsolete keys or miss newly required settings.

## 5. Turn Changes Into a Testable Matrix

During release note review, each finding should become **an assignable row**:

| Field | Question to answer |
|---|---|
| **Source document** | Which version's release notes/upgrade guide, section/URL, date reviewed? |
| **Change type** | Deprecated, removed, renamed, default, semantic, known issue? |
| **Component** | CQL/schema, driver, JVM, cassandra.yaml, nodetool, storage, backup, security? |
| **In use?** | Is there evidence from config/schema/logs/code/metrics? |
| **Impact** | Startup failure, wrong data, latency, availability, security, compatibility? |
| **Action** | What to fix, where, before or after upgrade? |
| **Owner** | DBA/SRE, Java team, security, platform, or vendor? |
| **Validation** | Exact command/fixture and expected outcome? |
| **Rollback/stop gate** | When to abort; if data format changed, how to recover? |

**Illustrative** example of a review entry, not asserting this is a real change in any Cassandra version:

~~~yaml
change_id: "COMPAT-EXAMPLE-001"
source_document: "<official-upgrade-guide-url-and-section>"
from_version: "<source>"
to_version: "<target>"
classification: "default_changed"
component: "server-config"
config_key: "<documented-key>"
old_effective_value: "<measured>"
new_default_value: "<from-target-doc>"
used_by_cluster: true
risk: "request-latency"
action: "decide explicit value; update deployment template"
owner: "database-platform"
validation:
  - "record effective value after startup"
  - "measure p95/p99 at representative load"
stop_gate: "latency regression exceeds agreed threshold"
status: "open"
~~~

Do not set **used_by_cluster: false** merely because the key does not appear in Git; the feature may be active via defaults, environment variables, or startup-generated configuration.

### 5.1. Prioritize by Impact

- **P0 — block upgrade:** a removed feature required by the workload; unsupported upgrade path; lack of trustworthy backup/rollback; data safety bug or severe security vulnerability with no mitigation.
- **P1 — must fix and test before rollout:** changed defaults affecting throughput/latency/CL, config breaking startup/behavior, driver/TLS unable to connect, repair/backup failing to run.
- **P2 — operational verification:** new warnings, changed admin CLI syntax, renamed metrics/dashboards, scripts needing updates.
- **P3 — informational tracking:** unused new features, deprecations with a transition window not yet removed in the target version.

Priority is decided by the running system, not solely by the document's "Critical" or "Minor" label.

## 6. Reviewing Cassandra-Specific Compatibility Areas

### 6.1. CQL, Schema, and Query-Driven Table Design

Cassandra is a wide-column database: **partition keys** determine data distribution and replicas; **clustering columns** determine sort order within a partition. Changes in the CQL parser, collections, indexes, UDTs, or query execution can impact correctness and latency.

When reading release notes, search for:

- **CQL syntax**, prepared statements, bind markers, collections/UDTs, timestamps, TTL, and tombstones;
- Secondary indexes, materialized views, or search/index features **actually in use**;
- Schema agreement, migration metadata, new limits/guardrails;
- Changes in query handling, paging, read repair, timeouts, or exception behavior.

Use a partition-key query as a fixture:

~~~sql
CREATE TABLE IF NOT EXISTS shop.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    happened_at timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id ASC);

SELECT happened_at, event_id, event_type
FROM shop.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
LIMIT ?;
~~~

**shop** must exist with appropriate replication before creating the table; the snippet above is a schema/query example, not a full cluster setup script. In real testing, verify the query returns **the exact rows, ordering, data types, paging, and latency** before and after. Prepared statements do not guarantee optimal routing if a query omits the partition key.

If the new version adds guardrails or tightens query restrictions, a CQL statement that previously only logged a warning may be rejected; check **logs and execution errors** on representative staging.

### 6.2. Replication, Topology, and Consistency Levels

Upgrading a node does not change a keyspace's **replication factor** simply because the binary changed, yet related mechanisms can affect operational behavior:

- Are topology/rack/snitch and node metadata still read consistently?
- Does the software impose specific mixed-version and internode protocol limits?
- Are there transition notes for hints, streaming, node replace/bootstrap, read repair, and repair?
- Are consistency levels **ONE, LOCAL_QUORUM, EACH_QUORUM, ALL** used properly for the datacenter topology?
- When one node stops for an upgrade, do enough replicas remain to satisfy application CLs?

For example, with RF = 3 in one datacenter, **LOCAL_QUORUM** requires a majority of **2** replicas to acknowledge according to request semantics. If one of the remaining replicas is already unhealthy before stopping a node, the rollout can cause insufficient replicas or elevated timeouts. Therefore, upgrades must be gated on **actual cluster health**, not assumptions like "RF 3 can always survive stopping any node."

### 6.3. SSTables, Commitlog, Compaction, and Repair

Read the release notes to determine:

| Component | Questions to ask |
|---|---|
| **SSTable format** | Can the new binary read old files? Once new-format files are written, can the old binary still read them? |
| **Commitlog / recovery** | Did the format, replay mechanism, or related limits change? |
| **Compaction strategy** | Were parameters, behaviors, warnings, disk headroom requirements, or post-upgrade steps changed? |
| **Repair** | Are anti-entropy tools/syntax/behaviors and mixed-node versions compatible? |
| **Streaming / bootstrap** | Can nodes on different versions exchange data during the supported window? |
| **Backup / restore** | Do snapshots, incremental backups, `sstableloader`, or third-party tools support the new format? |

For example, a release note may require post-upgrade work such as **rewriting old SSTables into the new format**. In versions providing **`nodetool upgradesstables`**, this command can generate heavy I/O and require significant free disk space. **Do not run it blindly**: confirm the exact command, options, order, preconditions, maintenance window, and rollback capability **for your exact Cassandra version**.

Once data or metadata has been written in a format unsupported by the old binary, "rolling back" by reinstalling the old package may prevent the node from starting or reading files. Recovery plans must be established **before** potentially irreversible operations.

### 6.4. Java/JVM, Memory, and Performance

Changing Cassandra versions may bring a different JDK/GC range. Review:

- Supported JDKs, distribution runtime requirements, and OS requirements;
- Removed/obsolete JVM flags; recommended garbage collectors;
- Heap/off-heap, direct buffers, memtables/caches, and page cache;
- Thread pools, schedulers, concurrency, connections/timeouts, and guardrails;
- Default metrics, log formats, GC logs, and observability.

**`-Xmx` does not cap total process RAM.** A default change that increases native memory, connection counts, or compaction can push a container to OOM even when the heap is not full. Verification must examine **heap, GC, RSS/cgroup, MemAvailable, disk I/O, and p95/p99** together.

Use an **officially supported server JDK**; do not copy JVM flags verbatim from an older major JDK onto a new JDK and ignore warnings.

### 6.5. Security, Access Control, and TLS

Release notes may contain changes affecting:

- Authenticators/authorizers, roles/permissions, CQL access behavior;
- Client-to-node and internode TLS, ciphers/protocols/certificates;
- JMX/management endpoints and administrative tools;
- Audit logging, security defaults, and underlying security libraries;
- Backup read permissions, encryption, and vendor KMS integrations.

After upgrading, Java applications must verify **authentication, TLS certificate validation, and least-privilege permissions**. Do not resolve connection failures by temporarily disabling authentication or TLS in production just to "get the upgrade done."

### 6.6. Operational Tooling and Observability

Update or re-verify scripts calling **nodetool**, `cqlsh` commands, export/restore pipelines, backup schedulers, metric scrapers, alerts, and dashboards. A node may report **UN** in `nodetool status` while backup/repair/driver tools remain incompatible. Treat operational tooling as part of the system to upgrade and test, not as secondary utilities.

## 7. Reviewing Configuration: Declared, Default, and Effective Values

### 7.1. Do Not Copy `cassandra.yaml` Verbatim from the Old Version

Configuration can originate from multiple sources: **cassandra.yaml, cassandra-env.sh, JVM options, environment variables, templating/Helm, service flags, or managed APIs**. Before changing anything:

1. **Inventory** all configuration sources on current nodes; store a secret-redacted copy.
2. **Obtain the target version's config reference** and migration guide.
3. **Flag removed/renamed/type-changed keys**. Do not keep keys just because the parser ignores or only warns on them.
4. **Compare defaults** for both explicitly set keys and omitted keys.
5. **Generate a fresh template from the target version**, carrying over intentional overrides; carefully review security/replication/timeout/repair settings.
6. **Start a staging node** to inspect startup logs, warnings, effective configuration, and runtime behavior.
7. **Re-verify on canary rollout**; retain config snapshots/manifests for investigation.

Never store passwords, private keys, access tokens, or signed URIs inside diff tables or reports.

### 7.2. Configuration Grouping Checklist

The following areas are typically worth checking when comparing **source and target documentation**; these are example groupings, **not a claim that every key name exists in every release**:

| Group | Example items to check | Potential observable impact |
|---|---|---|
| Identity / network | Cluster name, listen/broadcast addresses, seed discovery, native transport | Node fails to join or driver fails to connect |
| Topology / replication | DC/rack/snitch, RF, and cluster metadata | Replicas not placed as intended |
| Security | Authenticator, authorizer, client/internode encryption | Login failures, wrong permissions, TLS mismatch |
| Disk / commitlog | Data directories, commitlog location/segments/flush, disk thresholds | Disk pressure, data path/commitlog errors |
| Memtable / cache | Heap, off-heap, cache budgets | GC pauses, OOM, insufficient page cache |
| Request / guardrail | Timeouts, batch/mutation/partition limits, CQL guardrails | Statements start getting rejected or slow down |
| Compaction / streaming | Throughput, concurrency, maintenance tools | Backlog, I/O spikes during rollout |
| Logging / metrics | Loggers, metrics/JMX, tracing | Loss of visibility or sensitive data exposure |

**RF and consistency level are not the same parameter:** RF belongs to the **keyspace** replication strategy; CL is typically chosen per request/client. Check **CQL keyspace metadata and Java applications** alongside server config files.

### 7.3. Example Mapping Table

Suppose there are three **fictional** parameters:

| Fictional key | Source version | Target version | Handling |
|---|---|---|---|
| **alpha_timeout** | Accepts unit `ms` | Accepts unit `s` | Convert units after verifying docs, test runtime timeouts |
| **legacy_cache_mode** | Deprecated | Removed | Remove key, migrate to supported mechanism |
| **beta_limit** | Default 100 | Default 50 | Decide whether to set explicitly or accept new default, test workload |

These names **are not real Cassandra config keys**. The example highlights the mindset: copying text verbatim could turn a 5,000 ms timeout into 5,000 s if a unit change goes unnoticed.

## 8. Reading Release Notes with a Five-Pass Method

This approach reduces the chance of missing changes scattered across different sections of the documentation.

### Pass 1 — Compatibility Boundaries

Read **Supported upgrade paths**, prerequisites, JDK, driver, OS, compatibility, mixed-version limitations, and known issues. Before going further, you must know along which path the target version **can safely be reached from the source**.

### Pass 2 — Breaking Changes

Search for **breaking, removed, incompatible, no longer supported, deprecated, requires migration, cannot downgrade**. Cross-reference against configs, scripts, schemas, and Java code. These items can block the plan.

### Pass 3 — Defaults and Silent Behavior Changes

Search for **default, timeout, guardrail, warning, compaction, concurrency, memory, TLS, authentication, protocol, consistency, paging**. Anything the application relies on via **defaults** must be tested.

### Pass 4 — Fixed Bugs and Remaining Known Issues

Look for bug fixes impacting data/repair/streaming/timeouts/GC and the target release's **known issues**. A bug fix can alter outcomes compared to prior behavior, or a subsequent patch release may fix a regression. Choose the **final target patch** based on real stability and support policy.

### Pass 5 — Convert Into a Test Plan

Do not stop at "release notes read." Every relevant item must have **evidence of whether the system uses it, an owner, a test, and pass/fail criteria**. If unverified, mark **UNKNOWN** rather than silently turning it into **NOT APPLICABLE**.

~~~mermaid
flowchart TD
    A["Lock source/target + distribution"] --> B["Gather release notes, upgrade guide, config reference"]
    B --> C["Read compatibility boundaries"]
    C --> D{"Valid upgrade path?"}
    D -->|No| X["Block plan, pick supported path"]
    D -->|Yes| E["Scan breaking, removed, defaults, behavior"]
    E --> F["Find usages + assess risk"]
    F --> G["Action and test matrix"]
    G --> H["Staging and canary"]
    H --> I{"All stop gates PASS?"}
    I -->|No| X
    I -->|Yes| J["Rolling upgrade per version runbook"]
    J --> K["Verify cluster, data, apps, and maintenance"]
~~~

## 9. Practical Exercise: Analyzing Hypothetical Release Notes

Suppose the documentation for a **hypothetical X.Y.Z** release contains these three lines:

~~~text
[HYPOTHETICAL — not real Cassandra release notes]

1. "The legacy FOO transport setting was removed; configure BAR instead."
2. "The default READ_TIMEOUT policy changed."
3. "The new on-disk format is not readable by the previous major version."
~~~

How to document the review outcome:

| Hypothetical note | Questions | Action and verification test |
|---|---|---|
| FOO removed | Is FOO used anywhere? Is BAR equivalent? | Search deployments/configs, migrate setting; confirm node starts and app connects |
| READ_TIMEOUT default changed | Which defaults does the workload rely on? | Compare before/after, check Java driver and server timeouts, test query p95/p99/timeouts |
| On-disk SSTable format not backward compatible | Is there an SSTable rewrite/upgrade step? | Approve backup/restore plan, do not promise old-binary rollback, test loading/streaming |

If a note is a **security fix** requiring a new setting, add a security owner and authentication/TLS/authorization tests. If it requires **data migration**, calculate disk capacity, duration, and the point of no return.

The correctness of this exercise lies in **the reasoning and verification workflow**, not the fictional change items. In real projects, replace X.Y.Z with verified official release notes.

## 10. Verifying the Java Driver and CQL Before and After Upgrade

### 10.1. Application-Side Checklist

- Is the driver version in the **compatibility matrix** for the target Cassandra and native protocol?
- Is the application's JDK still supported by the driver?
- Do contact points, local datacenter, TLS, authentication, and connection pools work under the new setup?
- Do prepared statements, bound types (**uuid, date, timestamp, collections, UDTs**), and paging remain accurate?
- Could retries/speculative execution amplify errors when nodes are mixed-version or replicas are temporarily down?
- Are read/write consistency levels compatible with RF/DC and stopping nodes one at a time?
- Do denormalized query-pattern tables return correct data, including partition/time-bucket boundaries?
- Do driver metrics and logs still distinguish **timeout, unavailable, auth/schema/protocol errors**?

### 10.2. Java Driver 4.x Smoke Test Example

The following demonstrates a **partition-key read**, prepared/bound execution, and coordinator inspection; it does not replace a full production test suite. Before running, ensure the keyspace/table and sample test data from Section 6 exist, an appropriate Java driver is configured, and the test cluster has **dc1** with enough replicas for `LOCAL_QUORUM`.

~~~java
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public class CassandraUpgradeSmokeTest {
    public static void main(String[] args) {
        UUID tenantId = UUID.fromString(
                "11111111-1111-4111-8111-111111111111");
        LocalDate day = LocalDate.of(2026, 11, 21);

        // Point only to a verified test cluster.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                "SELECT happened_at, event_id, event_type " +
                "FROM shop.events_by_tenant_day " +
                "WHERE tenant_id = ? AND event_day = ? LIMIT ?");

            BoundStatement request = prepared.bind(tenantId, day, 20)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM);

            ResultSet result = session.execute(request);
            System.out.println(
                "Coordinator: " +
                result.getExecutionInfo().getCoordinator());

            int rows = 0;
            for (Row row : result) {
                // Count only; verify event_id/values via a separate fixture.
                if (row.getUuid("event_id") == null) {
                    throw new IllegalStateException(
                        "Unexpected data: missing event_id");
                }
                rows++;
            }
            System.out.println("Rows read: " + rows);
        }
    }
}
~~~

**Testing limitations:**

- A query returning **0 rows** without error does not prove data was preserved. Assert against **a fixture with known order/event IDs** and explicit expectations.
- When upgrading from an older server to a newer one, run **the same test suite** on the source version, mixed-version state (if supported), and target version after completion.
- The driver must validate server TLS certificates and credentials as in production; the minimal snippet focuses only on querying.
- Measure p95/p99, error rates, and retries under representative load; a single passing smoke test does not prove performance.
- Real applications should reuse **`CqlSession`** and `PreparedStatement`; closing the session after one run in `main` is solely for illustration.

## 11. Gated Upgrade Workflow

### 11.1. Before Rollout

1. **Lock documentation:** release notes, upgrade guide, migration/compatibility, known issues, and config reference for **the exact build**.
2. **Build change matrix:** all relevant **removed/renamed/default changed/behavior changed** items, owners, and test plans.
3. **Check cluster state:** node health, gossip/schema agreement per supported tools, DC/rack/RF, hints, streaming, repair backlog, compaction backlog, free disk, heap/GC.
4. **Verify backups:** full backup, schema, snapshot/incremental/commitlog matching target RPO, plus an independent restore test; never treat replicas as backups.
5. **Run staging tests:** mirror schema, partition-key workloads, reads/writes, TTL/tombstones, batches, compaction/repair, failure scenarios, and the Java driver.
6. **Finalize runbook:** node order, checkpoints, accountable owners, stop gates, post-upgrade tasks, and **points of no return**.

### 11.2. During Rolling Upgrade

**Rolling upgrade** replaces nodes in the order and constraints permitted by **that version's upgrade guide**. Never assume any two versions can run mixed-version safely.

For each node or allowed batch:

- Verify remaining replicas can satisfy CL and no background incident is active.
- Put the node in maintenance, replace binary/config/JDK per the official runbook.
- Start it, inspect startup warnings/errors, verify version and node status.
- Monitor schema agreement, client errors, read/write latency, GC, disk I/O, compaction/streaming/hints.
- Proceed to the next node only when **the previous batch's acceptance criteria pass**.
- Do not rush into SSTable conversion steps documented as **post-upgrade** while the cluster is still in a mixed-version state.

If a node fails to join, CQL binds fail, timeouts exceed thresholds, or replicas are insufficient, **halt rollout** and investigate per the contingency plan. Never disable security or consistency checks just to push forward.

### 11.3. After Rollout

- Confirm **all nodes** run the target version and topology is intact; verify no unexpected old binaries remain.
- Verify schema, reads/writes at target CL, consistency across sample partitions, and Java driver health.
- Compare p50/p95/p99 latency, throughput, errors/retries, GC/heap/native/RSS, disk, compaction/repair, and pending tasks against baseline.
- Execute **post-upgrade actions** only when required by documentation, following approved order and limits.
- Test snapshots, backup upload/restore, repair, `nodetool`, metric scrapers, and alerts.
- Update runbooks, configurations, SBOM/inventory, dashboards, and internal docs with verified changes.

## 12. Rollback and Recovery: Do Not Equate Them

### 12.1. Binary Rollback May Be Restricted

**Rollback** usually means reverting nodes/clusters to the previous binary/config version. However, some changes to **data formats, metadata, schemas, or synchronization mechanisms** are not backward compatible. In those cases, direct downgrades are unsafe.

Distinguish the scenarios:

| Scenario | Viable handling |
|---|---|
| No data/metadata changes yet, docs allow reverting | Perform rollback using the exact supported procedure, re-verify nodes/apps |
| SSTable format or incompatible schema already written | Do not blindly reinstall old binaries; evaluate restoring from backup into a compatible environment |
| Java app errors while server runs cleanly | Roll back only the app/driver if still compatible with the target server |
| Bad new config or removed key | Fix config for the target version or follow a supported revert path; check startup and CL |
| New writes arrived during the upgrade | Identify recovery point, preserve valid writes, and reconcile data on restore |

**Never promise RPO = 0 simply because a snapshot exists.** A snapshot is a point-in-time image; you must account for acknowledged writes after the snapshot and any incremental/commitlog archives. When restoring an older backup into a cluster, verify TTLs/tombstones and business-deleted records to avoid resurrecting unwanted data.

### 12.2. Mandatory Stop Gates

Signals that should halt a rollout:

- The upgrade path or current mixed-version state **is unsupported**.
- No clean, complete backup and verified restore capability meeting RPO/RTO requirements.
- Remaining nodes cannot satisfy the service's required consistency level.
- Startup warns on removed/unsupported parameters with unknown impact.
- Schema agreement, CQL reads/writes, authentication/TLS, or Java driver tests fail.
- Timeouts, unavailable errors, corrupted data, GC/OOM, full disks, or latency breaching agreed thresholds.
- Post-upgrade step would write an incompatible format while recovery plans are unready.

## 13. Reading Release Notes Through an Operational Lens

Some seemingly minor changes can have indirect effects:

### 13.1. New Timeouts and Distributed Queries

Cassandra computes tokens from partition keys, and drivers can perform **token-aware routing** when statements bind the full partition key. If default timeouts or retries change, multi-partition queries or large partitions expose issues much faster. Measure **latency per query shape** and inspect table design before blindly raising limits.

### 13.2. Compaction / Repair and Disk Space

Compaction-related changes can generate heavy I/O when many SSTables already exist. Calculate **disk headroom**, repair schedules, partition/tombstone sizes, and maintenance windows. Increasing concurrency may shorten one task's runtime while spiking query latency if I/O saturates.

### 13.3. Security Defaults and Java Connection Failures

A change to TLS/cipher/auth defaults can prevent older clients from completing handshakes. Verify with compatible driver/config settings and proper certificate provisioning. **Do not work around it by disabling hostname verification or trusting all certificates.**

### 13.4. Backup Tool Support for New Formats

Even when a new node serves `SELECT` queries fine, an older backup tool might fail to understand new metadata/SSTables or fail during restore. Complete **at least one restore rehearsal into an isolated cluster** compatible with the target version; consider backups usable only once checksums, schema, data, and application queries all verify cleanly.

## 14. Release Note Assessment Report Template

Minimum sections for an upgrade approval report:

~~~markdown
# Cassandra upgrade readiness — <cluster> / <source> -> <target>

**Reviewed documentation:** <release notes, upgrade guide, migration guide,
config reference, driver/JDK matrix, known issues, review date>

**Scope:** <DC, node count, RF, application/driver, backup/tooling>

**Supported upgrade path:** <hops and preconditions>
**Mixed-version plan:** <allowed conditions, time limit, stop gates>

| ID | Change type | In use? | Risk | Owner | Evidence | Status |
|----|-------------|---------|------|-------|----------|--------|
| 01 | removed     | yes/no/?| ...  | ...   | ...      | OPEN/PASS |
| 02 | default     | yes/no/?| ...  | ...   | ...      | OPEN/PASS |
| 03 | behavior    | yes/no/?| ...  | ...   | ...      | OPEN/PASS |

**Baseline:** <p95/p99, throughput, errors/retries, GC, I/O, repair>
**Backup/restore:** <backup ID, recovery point, restore drill result>
**CQL/Java tests:** <fixture, CL, schema, paging, driver/TLS>
**Post-upgrade actions:** <commands/impact/execution criteria>

**Rollback feasibility:** <supported up to which milestone>
**Recovery alternative:** <backup and accepted RPO/RTO>
**Go/No-Go:** <decision + approver + timestamp>
~~~

The template only defines structure; real values must come from the actual cluster and verified documentation. If an item lacks a source or evidence, mark it **UNKNOWN** and assign verification; avoid marking PASS based on intuition.

## 15. Practice Exercises

### Exercise 1 — How Does Deprecated Differ from Removed?

Hypothetical release notes state: "Parameter **P** deprecated in version A, removed in version C; version B still supports it with a warning." The cluster currently runs A and plans to upgrade straight to C.

**Question:** What must the operations team do before deploying C? Can they simply delete line P without checking defaults?

**Hint:** Find all usages of P, migrate to the new mechanism, verify whether path A → C is supported, and compare defaults/behaviors. Deleting P without understanding its effect can silently alter operations.

### Exercise 2 — Parameter Absent from Config File

A feature relies on a default timeout. On the source version timeout = 1,000 ms; suppose on the target version timeout = 500 ms. The config file omits this parameter.

**Question:** Why does `Git diff = 0` not prove nothing changed? What testing is needed?

**Hint:** Defaults live in the binary/config reference, not in Git. Compare effective values and measure p95/p99 and timeouts/retries on representative queries.

### Exercise 3 — Java Test Passes but Returns Wrong Data

After upgrading, a smoke test simply executes `SELECT...LIMIT 10` without throwing an exception, yet never checks the expected event IDs.

**Question:** What is missing from this test?

**Hint:** It could return 0 rows or the wrong set of rows and still pass. You need deterministic fixtures, value/order/paging assertions, multiple partition token ranges, CL checks, and failure cases.

### Exercise 4 — Upgrading a Node When RF = 3

A datacenter with RF = 3 has two unstable nodes, and the application uses `LOCAL_QUORUM`. An operator wants to stop one more node to upgrade it.

**Question:** Should they proceed right away? Why or why not?

**Hint:** No; check available replicas per partition and CL requirements. RF is only the configured replica count, not a guarantee that enough healthy replicas are online during maintenance.

### Exercise 5 — "Rollback Just Means Reinstalling the Old Binary"

The target version's upgrade guide requires converting SSTables into a format the old version cannot read. The operations team still writes the rollback plan as "reinstall the old version."

**Question:** What is wrong? What preparation steps must be added?

**Hint:** There is a backward-incompatibility boundary; confirm whether any rollback procedure is supported, preserve clean backups, rehearse restore and measure RPO/RTO, and avoid irreversible conversions before a recovery plan is ready.

### Exercise 6 — Choosing the Right Documentation Sources

A system runs a vendor-customized Cassandra distribution, apps use a specific Java driver, and backups use a third-party tool. An engineer reads only the Apache Cassandra server release notes.

**Question:** Which sources are missing, and what are the risks?

**Hint:** Vendor/managed docs, driver/JDK compatibility, backup tool compatibility, known issues/security advisories, upgrade/migration guides, and config references. Risks include unsupported paths, driver failures, failed backups/restores, and missing remediation steps.

## 16. Pre-Approval Checklist for Upgrade Plans

- [ ] Recorded **actual version of every node**, build/distribution, server JDK, OS, Java driver, and operational tools.
- [ ] Verified **supported upgrade path**, intermediate hops, and mixed-version limitations.
- [ ] Read relevant **release notes, upgrade guide, migration/breaking changes, known issues, and security advisories**.
- [ ] Every **deprecated/removed/renamed/default changed/behavior changed** item has an owner and status.
- [ ] Compared declared config, generated config, **defaults**, and **effective values**; did not copy old config verbatim.
- [ ] Tested schema, CQL, partition keys, collections, TTL, tombstones, and active indexes/features.
- [ ] Verified replication strategy, DC/rack/RF, consistency levels, and single-node stop tolerance.
- [ ] Verified Cassandra/JDK, Java driver/native protocol, and TLS/auth compatibility with the target environment.
- [ ] Checked backup/restore, error handling, and compatibility of SSTables, compaction/repair/streaming.
- [ ] Ran representative workload in staging, comparing p95/p99 latency, timeouts, throughput, GC, disk I/O, and memory headroom.
- [ ] Have a verified **clean backup + restore drill** and a recovery plan when binary rollback is unsafe.
- [ ] Runbook specifies node order, tests, stop gates, decision-makers, and post-upgrade tasks.
- [ ] Planned updates for metrics, dashboards, logs, permissions, `nodetool`/`cqlsh` scripts, and internal docs.
- [ ] Go/No-Go decision is based on **evidence**, not merely on nodes starting up cleanly.

## 17. Summary

Reading Cassandra release notes effectively means turning **version information into verifiable actions**. Start with supported upgrade paths and dependencies, then classify changes into **deprecated, removed, renamed, default changed, behavior changed, and known issues**. For each item, gather evidence of whether the system uses it, assess risk, and write a concrete test.

Because Cassandra is a wide-column distributed system, upgrade decisions affect **partition keys, query-driven tables, replication/consistency, SSTables, compaction, repair, backups, and Java applications**. A valid config or a node reporting `UP` is not enough: only when **data, queries, fault tolerance, and recovery** are verified on the target version can you declare an upgrade compatible and safe.
