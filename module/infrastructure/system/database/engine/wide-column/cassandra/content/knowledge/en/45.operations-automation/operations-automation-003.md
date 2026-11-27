# Pre- and Post-Maintenance Health Checks via Status and Queries in Apache Cassandra

## 1. Objectives and operational principles

In Apache Cassandra, maintenance can include rolling restarts, version upgrades, JVM/TLS config changes, node replacements, topology expansions, repairs, disk replacements, Java Driver updates, or schema adjustments. A maintenance operation can **succeed at the host level** while still degrading CQL responsiveness; conversely, a single successful `SELECT` can mask an unhealthy replica, compaction backlog, or the inability to tolerate losing another node.

This lesson belongs to the **Operations Automation** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. The goal is not merely to read `UN` lines in `nodetool status`, but to build an **evidence-backed health gate**:

- Verify the cluster is in a suitable state **before** maintenance.
- Establish a baseline for topology, replication/consistency, query success, latency, and resources.
- Observe risks during maintenance and **halt** if continuation criteria are not met.
- Verify **after** maintenance using node states, schema, native CQL, and safe read/write queries.
- Confirm real recovery: queues, hints, streaming, repair/compaction, disk, CPU/GC, and p95/p99.
- Return an automatable outcome: **PASS**, **FAIL**, or **UNKNOWN**, with explanations and evidence.
- Have a rollback/recovery plan; never use retries or lower consistency levels to mask an incident.

This lesson focuses on distributed Cassandra, the partition-key wide-column model, per-DC consistency levels, and building probes from a Java Driver 4.x application. All threshold numbers in examples illustrate methodology only and are **not default Cassandra thresholds**.

> **Safety rule:** Do not execute maintenance commands, write production data, run `repair`, `cleanup`, `decommission`, alter schemas, or restart nodes simply because of an example snippet. Write tests must use a dedicated keyspace/table, a least-privilege role, and an approved maintenance window. No commands are executed while authoring this material.

## 2. Health checking is condition verification, not a single command

### 2.1. Evidence layering

~~~mermaid
flowchart TD
    A["Maintenance controller"] --> B["Preflight"]
    B --> C["Topology & node state"]
    B --> D["Cassandra service & CQL"]
    B --> E["Replica availability + RF/CL"]
    B --> F["Resource/latency baseline"]
    C --> G{"Ready for maintenance?"}
    D --> G
    E --> G
    F --> G
    G -->|No / Unknown| H["STOP + human review"]
    G -->|Yes| I["Execute approved maintenance"]
    I --> J["Postflight: compare state + query + metrics"]
    J --> K{"Acceptance gates pass?"}
    K -->|Yes| L["PASS + release traffic/change"]
    K -->|No / Unknown| M["Hold / rollback / recovery runbook"]
~~~

**Liveness** only states that a service/process is alive or a node is seen as Up. **Readiness** states that the node/application can handle expected workloads. **Correctness** states that data read/written matches the primary key and consistency policy. **Performance** states that load, tail latency, and resources stay within limits.

These four dimensions must be checked independently. Never collapse them into a single Boolean flag `healthy=true`, because missing evidence can be mistaken for PASS.

### 2.2. Scope and source-of-truth table

| Scope | Example questions | Observation sources |
|---|---|---|
| Node/process | Are the Cassandra process and native listener serving? | Service logs, `nodetool info`, native connection |
| Gossip/ring | Is the node viewed as `UN`/`DN`? | `nodetool status` from multiple vantage points |
| Topology | Are DC/rack, node count, and token distribution accurate? | Status/ring, inventory, cluster metadata |
| Schema | Do schema agreement and tables/columns match? | `nodetool describecluster`, release-specific schema metadata |
| Replication | Do RF and CL have enough live replicas? | Keyspace replication, node states, request errors |
| Client→node | Can a Java session open and run queries? | CqlSession, driver errors, SSL/auth |
| Read correctness | Does a partition-key query return the expected row? | Prepared SELECT canary |
| Write correctness | Is a mutation acknowledged and readable back? | Prepared INSERT/SELECT on probe table |
| Performance | Have p95/p99, retries, throughput, and timeouts recovered? | Client & Cassandra metrics |
| Background work | Are streaming, hints, compaction, and repair stable? | `netstats`, `compactionstats`, metrics/logs |
| OS/JVM | Is CPU/GC/RAM/disk headroom safe? | JMX, cgroup, device metrics |

**`nodetool` typically operates over JMX**, not native CQL. Therefore, a successful JMX connection does not prove the Java Driver has valid TLS/auth/permissions or reachable contact points.

## 3. Defining "before," "during," and "after" maintenance

### 3.1. Preflight: do not start maintenance with an untrusted baseline

Before the maintenance window, define:

1. **Change ID and scope:** single node, rack, DC, all clients, topology change, or certificate rotation?
2. **Expected target:** how many nodes/DCs, racks, token ownership, and software versions after the change?
3. **Business RF/CL:** e.g., `NetworkTopologyStrategy`, `LOCAL_QUORUM`, or permitted application CLs.
4. **Dependencies:** active repair/backup/streaming, batch jobs, schema migrations, or Java rollouts?
5. **Traffic policy:** load shedding, canarying, migration freeze window, and who holds stop authority.
6. **Rollback path:** if schema/data-format/upgrade changes are not backward-compatible, rollback **may be infeasible**; establish this upfront.
7. **Expected data:** canary rows, test keyspace, test role, and representative query templates.
8. **Resources:** disk headroom, CPU/GC, heap/off-heap, compaction, hints, pending queues, network.
9. **Baseline window:** a representative observation window, avoiding comparisons between peak and off-peak hours.
10. **Exit gates:** PASS/FAIL/UNKNOWN states and actions for each outcome.

Do not pick a one-minute baseline right after a restart or during bootstrap/repair if it does not reflect normal steady state.

### 3.2. During maintenance: gate after every node/step

For rolling maintenance, order must respect topology/DC/rack/RF/CL. After each node:

- Verify the node returned to its expected state.
- Verify the CQL canary **from the application network** to the local DC.
- Observe p99/errors, retries, and replica availability.
- Check that hints/streaming/compaction/GC/disk are returning to acceptable levels.
- Ensure no other node went DOWN unexpectedly.
- Proceed to the next node only after gates pass; never "manually enter PASS" when telemetry is missing.

**When maintenance itself changes topology**, post-change node count/tokens/ownership should not match pre-change; compare against the **expected change manifest**.

### 3.3. Postflight: a single check is not enough

Even after the node is `UN` and a probe `SELECT` succeeds, you still need:

- **New native connections** (especially after TLS, auth, Java driver, or port changes).
- Read/write paths verified at **production CL** in every involved DC.
- No spike in timeouts, unavailable errors, request failures, or retry storms.
- Pending queues not accumulating persistently.
- Hints/streaming/compaction/repair recovering on schedule.
- Schema agreement, prepared statement metadata, and app compatibility.
- End-to-end API p95/p99 and data correctness.
- An **observation window** long enough to catch errors after reconnects and cache warm-up.

## 4. Inspecting cluster status with `nodetool`

### 4.1. Common read-only commands

~~~bash
# Observe topology; exact syntax/output varies by Cassandra release.
nodetool status

# Node stats and local state.
nodetool info

# Schema/topology summary by release.
nodetool describecluster

# Gossip peer view/metadata when investigating.
nodetool gossipinfo

# JMX checks for native transport/gossip if supported by release.
nodetool statusbinary
nodetool statusgossip

# Executor stage active/pending/completed/dropped.
nodetool tpstats

# Compactions, streaming, and table-level indicators.
nodetool compactionstats
nodetool netstats
nodetool tablestats ops_health.probes_by_run
~~~

**Command syntax, metric names, and availability of `statusbinary`, `statusgossip`, and `describecluster` can vary across Cassandra 3.x/4.x/5.x and distributions.** Before automating, check `nodetool help` on the exact running version.

Never run `nodetool repair`, `drain`, `cleanup`, `compact`, or `decommission` merely as a "health check": these are state- and resource-mutating tasks, not harmless observations.

### 4.2. Reading status output

An illustrative output looks like:

~~~text
Datacenter: dc1
Status=Up/Down
|/ State=Normal/Leaving/Joining/Moving
-- Address       Load       Tokens Owns Host ID                              Rack
UN 10.1.1.11     120 GiB    16     ?    ...                                  rack1
UN 10.1.2.12     118 GiB    16     ?    ...                                  rack2
UN 10.1.3.13     125 GiB    16     ?    ...                                  rack3
~~~

Addresses, sizes, and host IDs are **hypothetical**; `?` under ownership can appear when multiple keyspaces/RFs prevent representing ownership as a single simple percentage.

- `U`: node is seen as Up from the observer's vantage point.
- `D`: Down according to membership/gossip view.
- `N`: Normal, as opposed to `J` Joining, `L` Leaving, `M` Moving.
- `UN` is a useful precondition before rolling maintenance, **not proof that API read/write meets SLO**.
- A new node may legitimately be `UJ` during a planned bootstrap; gates must understand expected phases.
- Read from **multiple seed/observer nodes** to reduce the risk of a skewed single gossip view.

Do not make topology decisions using a context-free `grep UN`, because output and semantics vary by DC and phase.

### 4.3. Do not trust `UN` count while forgetting inventory

Suppose 6 nodes are expected (3 per DC), yet `nodetool status` prints only 5 lines and all are `UN`. A naive script checking "no DN found" will falsely PASS because **one node is completely missing**.

Health gates must compare against expected inventory:

- Host ID and address/logical identifier of **each node**.
- DC/rack placement.
- Node count per DC.
- Token/vnode allocation and expected joining/leaving states.
- Software version and upgrade status during version maintenance.
- Advertised native transport endpoint reachable by applications.

Cross-check metadata and trusted sources; never treat a fixed IP as a permanent identifier across node replacements.

## 5. Replication and consistency when verifying availability

### 5.1. What RF/CL means for "sufficient replicas"

With `NetworkTopologyStrategy` and `RF(dc1)=3`, a normal operation at `LOCAL_QUORUM` typically requires **2 replica ACKs** in the local DC. With one node DOWN, the logical condition may still be met, yet:

- Headroom drops to only two replicas.
- One slow remaining replica can trigger request timeouts.
- Retries/streaming/hints raise post-recovery load.
- Maintenance on the next node would break quorum.

Thus preflight does not merely ask **"can current requests succeed?"**—it asks **"is it safe to take down another node in the next step?"**

### 5.2. Simplified matrix example

| Hypothetical state in dc1, RF=3 | LOCAL_ONE | LOCAL_QUORUM | Proceed with rolling? |
|---|---|---|---|
| 3 healthy replicas, enough resource headroom | Possible | Possible | Consider PASS if other gates pass |
| 2 healthy replicas, 1 DOWN | Possible | Possible | Usually HOLD: lack of redundancy |
| 1 healthy replica, 2 DOWN | Possible per routing/policy | Insufficient quorum | FAIL for LOCAL_QUORUM apps |
| 3 `UN` nodes, one with terrible p99 | Possible | May time out | HOLD/FAIL if SLO breached |
| Node bootstrap/streaming incomplete | Topology-dependent | Topology-dependent | Follow topology-specific gate |

This table is a **conceptual model**, not a substitute for actual replica-set calculation per partition, DC, rack, transient replication, availability, LWT, or special versions. Never assume 3 nodes across a DC are replicas for every partition in all configurations.

### 5.3. Choosing consistency for canaries

If production workloads use `LOCAL_QUORUM`, a probe running only at `ONE` can PASS even while the real application times out on quorum. Canaries should use the **CL matching the target workload**, rather than lowering CL for convenience.

In multi-DC:

- Launch probes **from each important local DC/client region**.
- Use the matching session `localDatacenter`.
- Test reads/writes at each path's business CL.
- Evaluate cross-DC replication, streaming/repair, and failover policies if applicable.
- `LOCAL_QUORUM` in dc1 does not automatically prove dc2 has received or can read the data.

A `LOCAL_QUORUM` write+read probe in dc1 proves a bounded scope; it does not verify global synchronization across all replicas in all DCs.

## 6. Schema, native transport, and driver compatibility

### 6.1. Schema agreement is a separate gate

Before and after migrations or rolling upgrades, verify:

- Keyspaces, tables, types, and indexes needed by the application.
- Cassandra schema versions/gossip agreement per release.
- Driver schema metadata and prepared CQL compatibility.
- DDL migration ordering across old and new application versions.
- No unexpected table/column drops or type incompatibilities.

`nodetool describecluster` may display node schema versions depending on the release; **never treat a single "schema versions" line as proof that all apps have reprepared or that all queries are valid**.

`system.local` and `system.peers_v2` (if present in the release) provide local metadata and peer views, not a single cluster-wide source of truth or tables for manual editing. Never directly modify `system_schema` to "force agreement."

### 6.2. Native CQL must be tested from where the app runs

`nodetool` can connect over JMX even when:

- The native transport port is not listening.
- TLS certificates are expired or have wrong SANs.
- The Java truststore is missing the CA.
- The CQL user lost permissions.
- Firewalls/NetworkPolicies block the pod.
- The driver discovers unreachable peer addresses.

Therefore you need a **new CqlSession/new connection canary**, followed by **prepared CQL**. Running `cqlsh` locally on a node with admin credentials is no substitute for a canary using the Java driver, app role, and application network path.

### 6.3. A driver exception does not automatically mean the server is DOWN

An `AllNodesFailedException` wraps errors per coordinator candidate and can stem from TLS, DNS, protocol, auth, or connection issues. When handling it:

- Collect `getAllErrors()` per node/cause via an authorized channel.
- Do not treat it as a replica ACK map.
- Distinguish `InvalidQueryException`, `UnauthorizedException`, timeouts, unavailable, and codec errors.
- Do not retry configuration errors endlessly (bad certs, wrong password, invalid prepared statements).

## 7. Deciding between read-only and read/write checks

### 7.1. Read-only probes

A read probe can query a pre-seeded static row with full primary key and a stable expected value:

~~~cql
SELECT check_id, expected_value
FROM ops_health.probes_by_run
WHERE run_id = ?
  AND check_id = ?;
~~~

Advantage: creates no new mutations, uses a `SELECT`-only role, suitable for preflight when writes are forbidden. However, it only proves the **read path** and that the probe row still exists—it does not verify writes, commitlog, or write quorum.

### 7.2. Dedicated read/write canary

A write+read probe should use:

- A **dedicated keyspace/table**, created via approved schema migration **prior to** maintenance.
- Partition/key scoped by **run_id UUID** to avoid colliding with production/user data.
- Stable `check_id`/`expected_value` for idempotent retries.
- Short/valid TTL to limit data accumulation; note it still generates tombstones, requiring retention/compaction planning.
- `SELECT` and `MODIFY` permissions scoped strictly to the probe table.
- Realistic CL, bounded timeout/retry budgets, and latency tracking.
- Never `TRUNCATE`/`DROP TABLE` after every check.

A successful read-after-write does not prove every replica in every DC has the data or lacks divergent stale data. At the chosen consistency, it is **scoped evidence**, not proof of global convergence.

### 7.3. Avoid unsafe probe writes

Never write into business tables just to test, because:

- It can trigger event consumers, CDC, or notifications.
- TTL/timestamps can alter business semantics.
- Retries can cause side effects.
- Repeated runs can expose canary data to end users.
- LWT/counter writes have different non-idempotent/conditional behavior.
- Cleanup via bulk deletes creates unnecessary tombstones and I/O.

Do not ad-hoc modify production schemas or roles during a health-check window just to create a probe table; prepare beforehand.

## 8. Designing a practical probe keyspace/table

### 8.1. DDL for lab or approved environments

~~~cql
-- Example for a single-DC 3-node cluster; do not copy RF to
-- another cluster without checking topology and availability.
CREATE KEYSPACE IF NOT EXISTS ops_health
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;
~~~

~~~cql
CREATE TABLE IF NOT EXISTS ops_health.probes_by_run (
    run_id uuid,
    check_id text,
    observed_at timestamp,
    expected_value text,
    PRIMARY KEY ((run_id), check_id)
);
~~~

For multi-DC, define RF per DC per policy. If testing cross-DC replication, design dedicated checks and understand the relevant CLs and failover rules.

### 8.2. Why is `run_id` the partition key?

- Each maintenance run gets a single identifying `run_id`; probes for that run stay within a bounded partition.
- `check_id` distinguishes read-only references/canaries or multiple test types within a run.
- Reusing `run_id + check_id` with the same value enables **value-level idempotent** retries for regular mutations.
- Limit `check_id` count per run so partitions do not grow wide.
- Limit run frequency; TTL expiration still produces tombstones prior to compaction.

Do not use `now()` as part of the primary key on every retry if you want to avoid generating multiple rows; never use counter increments for a health probe.

### 8.3. CQL smoke write/read

~~~cql
-- Each run receives a unique UUID generated by the controller;
-- the same UUID is reused across retries within that run.
INSERT INTO ops_health.probes_by_run
    (run_id, check_id, observed_at, expected_value)
VALUES (?, ?, ?, ?)
USING TTL 3600;
~~~

~~~cql
SELECT expected_value, observed_at
FROM ops_health.probes_by_run
WHERE run_id = ?
  AND check_id = ?;
~~~

Use a fixed `expected_value` per run and compare exact strings. **A 3600-second TTL is illustrative**, not a default SLA/retention; rewrites refresh expiration. If preflight needs comparison across longer spans, use a reference probe with appropriate retention and a separate `check_id`/`run_id`.

### 8.4. Read probe with a stable data fixture

If a reference record uses a 1-hour TTL, the next day's preflight will return empty because it expired. Maintain **separate reference data** with appropriate lifetime, pre-seeded and monitored for expiry. Never turn "row expired" into a conclusion of "Cassandra READ BROKEN."

A sound plan includes:

- A reference read probe with a stable expected value and managed retention.
- An ephemeral write-read probe to verify the mutation path.
- Representative application queries (read-only, full partition key, bounded).
- Dedicated cross-DC probes if replica convergence is required by policy.

## 9. Baseline and decision thresholds

### 9.1. Separating hard gates and soft signals

**Hard gates** typically include:

- Any node missing from expected inventory or unexpectedly `DN`.
- A node in Joining/Leaving/Moving contrary to the planned phase.
- Insufficient replicas/CL for the application.
- Schema incompatibility or CQL role/query failures.
- Probe read/write returning incorrect values or unable to execute.
- Disk/memory/headroom below the organization's safety threshold.
- Repair/streaming/backup incompatible with the upcoming change.
- Required observability data unavailable → **UNKNOWN**, never auto-PASS.

**Soft signals** may include:

- Slightly elevated GC pauses still under SLO.
- Non-zero pending compactions that are stable with a drain plan.
- Brief CPU/disk await spikes during cache warm-up.
- Request p99 slightly above baseline yet within budget.

Soft signals must not be ignored; they require a tolerance/observation-window policy and an authorized approver.

### 9.2. Example pre/post condition manifest

~~~yaml
# Documentation example only, not an actual Cassandra config file.
change_id: MAINT-2026-041
cluster: cassandra-prod-example
local_datacenters: [dc1, dc2]
expected_nodes:
  dc1: 3
  dc2: 3
expected_states_before: ["UN"]
expected_states_after: ["UN"]
allowed_transient_state_during_rolling: ["DN", "UJ"]
replication_policy: "NTS, RF=3 per DC"
read_consistency: LOCAL_QUORUM
write_consistency: LOCAL_QUORUM
hard_gates:
  schema_compatible: true
  app_read_probe: required
  app_write_read_probe: required
  no_unexpected_down_nodes: true
  no_unexpected_topology_changes: true
limits:
  p99_read_ms: 200
  error_rate_pct: 0.5
  minimum_disk_free_pct: 20
observation_window_minutes: 15
~~~

**Numbers are illustrative only.** Do not treat `p99<=200 ms` or disk free >=20% as universal Cassandra standards; derive them from your specific SLO and capacity runbook.

`allowed_transient_state_during_rolling` only describes states *permitted by the plan*; **it does not allow automatically continuing** if a planned node remains DOWN unrecovered or CL is unsafe.

### 9.3. Comparing baseline to postflight properly

Never compare a percentile measured during 30 idle seconds against a peak-hour percentile and blame every difference on maintenance.

Record:

- Workload mix, offered/successful QPS, rows/page, and payload size.
- Timestamp, duration, sample size, and percentile calculation method.
- CL/RF, client region/DC, and driver/JDK versions.
- Node count/rack/token topology.
- Active repair/streaming/compaction/background jobs.
- CPU/GC/disk/network/memory headroom.
- **Worst-node** metrics, not just cluster averages.

A good result means post-maintenance meets the **absolute SLO** and does not regress beyond agreed baseline tolerance. Both conditions should be evaluated separately.

## 10. Tri-state gate model: `PASS/FAIL/UNKNOWN`

### 10.1. Why three states are needed

~~~text
PASS:
  Sufficient data sources, full observation window, and all conditions met.

FAIL:
  Concrete evidence violating a hard gate or SLO.

UNKNOWN:
  Data could not be collected, window too short, stale metrics,
  missing probe permissions/secrets, or unconfirmed inventory.
~~~

If an API lacks write permissions due to a `SELECT`-only role while the manifest requires write/read, the result must not be PASS. It may be `UNKNOWN` because it could not execute; if the missing preparation/role violates defined policy, the controller may mark `FAIL` per rules.

### 10.2. Gate aggregation pseudocode

~~~text
function evaluate(gates):
    for gate in gates:
        if gate.status == FAIL:
            return FAIL
    for gate in gates:
        if gate.status == UNKNOWN:
            return UNKNOWN
    if all expected gates present and all == PASS:
        return PASS
    return UNKNOWN
~~~

This logic prioritizes FAIL when a clear violation exists, while **never treating missing gates as PASS**. If business policy requires stopping immediately on UNKNOWN, enforce `stop_on_unknown=true`.

### 10.3. Do not check only the exit code of `nodetool status`

A `nodetool status` exit code of 0 only states that the command executed and read status per its interface; it does not mean every node matches expected inventory or is `UN`.

If automation parses text output, it must:

- Pin the Cassandra/nodetool version and locale.
- Parse the DC/node table with schema validation, never a naive `UN` string grep.
- Verify the expected node set/racks, states, and views from multiple vantage points.
- Return **UNKNOWN** whenever the parser encounters an unrecognized format.
- Include tests for missing node, DN, UJ, renamed DC, and truncated output.
- Prefer structured metrics/APIs supported by official tooling when available.

## 11. Java Driver 4.x: verified read/write smoke test

### 11.1. Probe contract

The Java probe accepts a **pre-configured `CqlSession`**, rather than storing passwords/CAs in code. The session needs:

- Environment-appropriate contact points and local datacenter.
- TLS trust/hostname validation and CQL credentials per policy.
- Keyspace `ops_health` with table `probes_by_run` created **prior to** maintenance.
- A canary role with `SELECT` and `MODIFY` scoped strictly to the probe table.
- Environment-appropriate RF/DC and consistency level.
- A `UUID runId` generated by the controller **once per run**, kept stable across retries.
- Fixed expected value, never varying the string across retry attempts.

### 11.2. Java code using prepared statements

~~~java
package example.cassandra.ops;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public final class CassandraReadWriteProbe {
    private final CqlSession session;
    private final PreparedStatement write;
    private final PreparedStatement read;

    public CassandraReadWriteProbe(CqlSession session) {
        this.session = Objects.requireNonNull(session);

        this.write = session.prepare(
            "INSERT INTO ops_health.probes_by_run " +
            "(run_id, check_id, observed_at, expected_value) " +
            "VALUES (?, ?, ?, ?) USING TTL ?"
        );

        this.read = session.prepare(
            "SELECT expected_value, observed_at " +
            "FROM ops_health.probes_by_run " +
            "WHERE run_id = ? AND check_id = ?"
        );
    }

    public ProbeResult check(
            UUID runId, String checkId, String expected,
            Instant observedAt) {
        Objects.requireNonNull(runId);
        Objects.requireNonNull(checkId);
        Objects.requireNonNull(expected);
        Objects.requireNonNull(observedAt);

        if (checkId.isBlank() || expected.isBlank()) {
            throw new IllegalArgumentException(
                "probe identifiers must be nonempty");
        }

        BoundStatement writeStatement = write
            .bind(runId, checkId, observedAt, expected, 3600)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true)
            .setTimeout(Duration.ofSeconds(5));

        long writeStarted = System.nanoTime();
        session.execute(writeStatement);
        long writeNanos = System.nanoTime() - writeStarted;

        BoundStatement readStatement = read
            .bind(runId, checkId)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true)
            .setTimeout(Duration.ofSeconds(5));

        long readStarted = System.nanoTime();
        Row row = session.execute(readStatement).one();
        long readNanos = System.nanoTime() - readStarted;

        if (row == null) {
            return ProbeResult.fail(
                "READ_RETURNED_NO_ROW", writeNanos, readNanos);
        }

        if (!expected.equals(row.getString("expected_value"))) {
            return ProbeResult.fail(
                "READBACK_MISMATCH", writeNanos, readNanos);
        }

        return ProbeResult.pass(writeNanos, readNanos);
    }

    public record ProbeResult(
            boolean pass,
            String code,
            long writeNanos,
            long readNanos) {

        static ProbeResult pass(long w, long r) {
            return new ProbeResult(true, "PASS", w, r);
        }

        static ProbeResult fail(String code, long w, long r) {
            return new ProbeResult(false, code, w, r);
        }
    }
}
~~~

This example uses a Java `record`, requiring Java 16+; if Cassandra/driver runs on an older JDK, replace it with a POJO class. `setTimeout`, `setIdempotent`, and bound values must be verified against your exact Java Driver 4.x release, JDK, and custom codecs.

**Adjust CL for lab clusters:** if a lab has only one node/RF=1, `LOCAL_QUORUM` corresponds to one replica in that DC by quorum arithmetic, yet policy/compatibility still must be tested; this example targets a single-DC RF=3 workload, not a one-size-fits-all script for every environment.

### 11.3. Is overwriting the same key a safe retry?

Keeping the same `runId`, `checkId`, and `expected` **targets a single key** without creating extra rows. However:

- Each retried `INSERT` carries a new timestamp/TTL and can extend expiration.
- The controller passes the same `observedAt` across attempts within a run rather than calling `Instant.now()` on each retry, keeping `observed_at` and `expected_value` stable.
- Even with an identical payload, re-writing refreshes TTL or Cassandra mutation timestamps. Only set `setIdempotent(true)` when such refreshes **cause no business side effects**; if strict idempotency is required, pin the write timestamp/retention policy or omit timestamp/TTL from the mutation and manage cleanup separately.
- Never infer idempotency for counters or LWTs from this example.

In production automation, **never retry endlessly**. A write timeout is an uncertain outcome; perform a bounded read-back at the appropriate CL on the same key and reconcile, returning `UNKNOWN` or FAIL per policy if evidence is insufficient.

### 11.4. Turning exceptions into gate decisions

The snippet above throws exceptions on driver/CQL errors. The outer controller must:

1. Classify auth, TLS, codec, `InvalidQuery`, unavailable, and timeout errors.
2. Log query template, error family, local DC, UTC time, `runId`, and check ID.
3. Never log passwords, unpermitted raw contact point lists, or sensitive bind values.
4. Decide `FAIL` when a violation is confirmed, or `UNKNOWN` when observability/roles prevent verification.
5. Cap attempts, latency, and cancellation; never create a retry storm on a degraded cluster.

### 11.5. Do not use `wasApplied()` for regular writes

`wasApplied()` is meaningful for conditional statements such as `INSERT ... IF NOT EXISTS`. For a regular `INSERT`, **never use it to infer the server applied the write on all replicas**. Application evidence requires:

- No exception at the selected CL.
- A read-back probe returning the expected value at the appropriate read CL.
- Separate node/replica state and availability gates.
- Post-write metrics confirming cluster stability.

## 12. Controlled read-only probes using business queries

### 12.1. Why is more than the `ops_health` table needed?

A probe table is typically tiny with simple partitions and SSTables. Production queries, by contrast, may:

- Read `(device_id, event_day)` across many clustering rows.
- Encounter TTLs, tombstones, and SSTable merges.
- Use custom Java codecs or UDTs.
- Be affected by secondary indexes/SAI or page sizes.
- Span multiple DCs/tenants and different tables.

A passing `SELECT` on `ops_health` does not prove every business query works.

### 12.2. Representative query example

~~~cql
-- Assumes an existing business table.
SELECT event_time, reading_value, status
FROM telemetry.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
ORDER BY event_time DESC
LIMIT 20;
~~~

**Use a seeded key or an authorized, non-sensitive fixture.** If a query expects 20 rows but data expired via TTL or the writer rolled to a new day bucket, a lower row count is not necessarily a maintenance fault. Validate expected result/shape against the data contract.

Avoid table scans, `ALLOW FILTERING`, `SELECT *` without a partition key, or `COUNT(*)` over huge partitions as "health tests"; such probes themselves cause latency/GC spikes and false alarms.

### 12.3. Query correctness gates

| Gate | What it proves | What to observe |
|---|---|---|
| Prepare | Schema/CQL remains compatible | Prepared statement accepted by server |
| Execute read | Read CL and networking work | Request success, exceptions, latency |
| Result shape | Java mapping is intact | Column types, row mapper, non-null fields |
| Semantic result | Fixture data is intact | Expected row/key/value/timestamp |
| Pagination | Multi-page reads succeed | Bounded next-page fetch |
| Authorization | App role retains privileges | No unauthorized/auth failures |
| Workload | p99/budget remains met | Time series & node resources |
| Multi-DC | Regions/DCs are served | Per-DC dedicated probes |

For queries relying on new metadata/schema after an upgrade, test **both old and new Java app versions** during the compatibility window.

## 13. Checking partition coverage and local DC

### 13.1. One key does not represent the entire token ring

Cassandra distributes data by the token of the **partition key**. A probe using a single `run_id` always routes to the same replica set; another failed node or rack might not be part of that partition's replicas.

To increase coverage when needed:

- Probe multiple safely generated `run_id`/partition keys.
- Log token-to-target-replica mappings using approved tooling if genuinely required.
- Check **all nodes** via an independent topology gate.
- Run probes in every DC/app client region.
- Verify CQL requests route across multiple coordinators in controlled tests.
- Cap probe QPS/bytes so checks do not amplify load.

**Never** claim "all replicas verified" just because 10 writes ran; without inspecting token distribution, all 10 keys could hit the same subset of replicas.

### 13.2. Quorum CL does not replace application checks

With RF=3/`LOCAL_QUORUM`, a read/write can succeed even while one node is unhealthy. Before deciding to maintain the next node:

- Check topology inventory and node states.
- Check headroom on the **remaining replicas**.
- Check degraded workload p99/error budget.
- Check business data correctness, not just one probe key.
- Avoid starting concurrent repairs/streaming that consume headroom.

### 13.3. Cross-DC smoke tests

If the app can fail over across regions or serves both dc1 and dc2, a dedicated test must clearly separate:

~~~text
From region A, session localDc=dc1:
  CL=LOCAL_QUORUM, read + write probes, latency/error.

From region B, session localDc=dc2:
  CL=LOCAL_QUORUM, read + write probes, latency/error.

Cross-DC visibility:
  tested separately per replication/convergence policy;
  do not infer from a single LOCAL_QUORUM read in dc1.
~~~

Do not reuse the wrong `localDc` `CqlSession` across regions or guess host/rack from IPs. Distinguish **local DC availability** from **inter-DC replication lag/repair**.

## 14. `system.local`, peers, and metadata limitations

### 14.1. Small queries to identify node/schema

Some releases support:

~~~cql
SELECT host_id, release_version, data_center, rack,
       schema_version
FROM system.local;
~~~

`system.local` returns metadata from the **coordinator node queried by the session**; it is not cluster-wide consensus. Columns may change across Cassandra releases.

On releases with `system.peers_v2`:

~~~cql
SELECT peer, host_id, data_center, rack, schema_version
FROM system.peers_v2;
~~~

Table/column names and peer semantics differ between Cassandra 3.x/4.x/5.x. **Do not infer data loss from a missing peer row**: peer views reflect propagated state and must be cross-checked with `nodetool status` and inventory.

### 14.2. Never use system tables to mutate state

While querying metadata is helpful, health automation must **never write directly to `system.local`, `system.peers_v2`, or `system_schema`**. Topology and schema changes must follow supported Cassandra mechanisms and runbooks.

### 14.3. Choosing observers

Querying `system.local` behind a load balancer can hit different coordinators across calls, making snapshots hard to distinguish. Better observation practice:

- Collect node-identified snapshots from authorized seed observers.
- Record host ID, DC/rack, and timestamp for every sample.
- Do not confuse driver contact points with a partition's replica set.
- Account for node restarts and metadata changes during topology operations.
- Cross-check multiple sources rather than relying on one query.

## 15. Resource health gates: avoiding PASS when a node is near overload

### 15.1. JVM/OS headroom

Evaluate against the **hottest node** and real resource limits:

| Resource | Signals to check | Relation to maintenance |
|---|---|---|
| CPU per-core/quota | Busy/throttling/steal | Restart shifts load onto peers |
| JVM GC | Pause p95/max, post-GC occupancy | Stop-the-world pauses inflate p99 |
| Heap/off-heap/RSS | Memory pressure, OOM events | Caches/warm-up/compaction raise footprint |
| Disk free | GiB/% on exact data/commitlog volumes | Streaming/compaction need temporary headroom |
| Disk await/IOPS | Device latency and queue depth | Flush/repair compete with reads |
| Network | RTT, retransmits, NIC bytes/s | Gossip/streaming/replica traffic |
| File descriptors/threads | Limits, errors | Node can be `UN` while CQL connections fail |
| Cgroup | `memory.events`/`cpu.stat` | Pod OOMKilled or throttled |
| Native transport | Connection failures/in-flight | TLS/auth/pool reconnects |

Never use "heap is only 40%" to ignore cgroup OOMs or nearly full disks. Never use cluster-wide average CPU to hide a hot replica.

### 15.2. Compaction does not always have to be zero

Healthy Cassandra nodes routinely run background compaction and flushes. A reasonable gate asks:

- Are active/pending compactions normal for the workload?
- Is the pending backlog growing unbounded?
- Is there enough disk headroom for rewrites?
- Are p99 and timeouts within budget?
- Is post-maintenance background work completing on schedule?

A strict "`pending=0` at all times" gate can block PASS even on a healthy cluster. Conversely, continuously rising pending counts alongside tight disk is a hard safety signal.

### 15.3. Hints, repair, and streaming

- `nodetool netstats` primarily observes **SSTable streaming**; an empty `netstats` **does not** prove all CQL/replication network traffic is idle.
- Hints may accumulate and replay after node outages, requiring release-appropriate metrics/time trends.
- Repair may not run immediately after a node returns; consistency/correctness policies require an explicit repair plan.
- Bootstrap/replace/decommission can shift token/rack placement and streaming within a window; gates must be **phase-aware**.
- A `UN` node is not guaranteed to have finished recovery or synchronized all SSTables/replicas.

## 16. Observing p95/p99, errors, and retries consistently

### 16.1. Separating outcome categories

For CQL/Java probes and business queries:

- Offered logical requests/s.
- Completed/successful requests/s.
- Error rate broken down by auth, invalid query, timeout, unavailable, and transport.
- Driver retry/speculative attempts/s (if metrics exist).
- p50/p95/p99 **of successes** alongside timeout rate; never inspect success p99 in isolation.
- Client app response p95/p99, not only server read/write latency.
- Worst-node latency/GC/disk and request sample counts.

### 16.2. Do not average p99

Suppose node A has p99=30 ms, B has p99=60 ms, and C has p99=600 ms; the arithmetic mean is **not** the cluster p99. If histograms are exported, aggregate buckets properly with matching labels and sample counts.

A 2-second p99 computed from only 4 probe requests is statistically unstable. **Single probe latency** is a canary signal, not a reliable percentile. You need a workload time series with sufficient samples across the observation window.

### 16.3. Example acceptance rules (hypothetical)

~~~text
Preflight:
  unexpected_down_nodes = 0
  schema_compatible = true
  CQL read + write probe pass in each required DC
  p99_app_read <= agreed SLO
  error_rate <= agreed budget
  resource headroom >= organization threshold
  no incompatible repair/streaming/topology work

Postflight:
  expected topology/node state reached
  new connections TLS/auth/CQL pass
  CQL read + write probe pass, expected values match
  business query templates pass
  p99_app_read and error_rate within budget
  queues/compaction/hints/streaming stable or on approved track
  no new unexpected OOM/FD/disk pressure
  observation window sufficient
~~~

Thresholds must come from your SLO and on-call policies, not from this example. If preflight failed, mark the baseline untrusted and **never "PASS post-maintenance simply because it compares against an even worse baseline."**

## 17. Designing a staged verification pipeline

### 17.1. Implementable pipeline flow

~~~mermaid
flowchart LR
    A["Collect inventory + change manifest"] --> B["Read-only preflight"]
    B --> C{"Gate"}
    C -->|PASS| D["Approved operation 1"]
    C -->|FAIL / UNKNOWN| E["STOP + on-call"]
    D --> F["Node/service gate"]
    F --> G{"PASS?"}
    G -->|Yes| H["Next planned operation"]
    G -->|No| E
    H --> I["Postflight cluster + CQL + metrics"]
    I --> J{"SLO & correctness achieved?"}
    J -->|Yes| K["Close change, archive evidence"]
    J -->|No| L["Hold, recovery/rollback"]
~~~

The pipeline **never triggers maintenance commands** without approvals and checkpoints. This example focuses on health gating and does not replace a formal rolling upgrade/repair SOP.

### 17.2. Artifacts to retain

| Artifact | Fields | Purpose |
|---|---|---|
| Change manifest | ID, owner, scope, expected deltas | Verify objective |
| Preflight report | Node inventory, DC/rack, schema, probes | Baseline/start preconditions |
| Maintenance timeline | Node steps, timestamps, guardrails | Incident correlation |
| Postflight report | Actual vs expected, query results, metrics | PASS/FAIL/UNKNOWN |
| Probe receipts | Run UUID, check ID, CL, latency, outcome | Reproducible evidence |
| Resource snapshots | Worst-node CPU/GC/disk/queues | Capacity/safety |
| Rollback log | Decisions, approvals, verification | Recovery/audit |
| RCA | Failure root cause, change controls | Prevent recurrence |

Do not copy raw auth secrets, sensitive CQL bind values, or full production data into artifacts. Retain evidence per retention and access-control policies.

### 17.3. Timeouts and cancellation

A deadline-bound health check needs:

- Per-query timeout.
- Per-gate timeout.
- Overall preflight/postflight timeout.
- Max attempts/backoff and total request budget.
- Cancellation semantics if the tool/controller stops.
- Policy when a step fails to finish: **UNKNOWN** or FAIL, never PASS.

Deadlines must fit the workload; never simply raise timeouts to hide poor p99.

## 18. Schedulers, idempotency, and preventing probe storms

### 18.1. Multiple controllers running concurrently

In automation, you may encounter:

- Two Jenkins/GitHub Actions workflows with the same change ID.
- A runner that timed out while requests remain in flight.
- Health probes autoscaled per application pod.
- Retries increasing simultaneously in both the controller and the Java Driver.
- An on-call engineer re-triggering a run because results weren't visible yet.

Enforce a **lock/lease or single-owner per change ID** in the orchestrator; track `running/finalized` state and cap probes/s.

### 18.2. Stable run ID and retry budget

~~~text
change_id = MAINT-2026-041
run_id    = UUID generated once
check_id  = rw-local-dc1
expected  = fixed non-sensitive nonce for this run

Attempt 1 -> timeout while writing
Attempt 2 -> optionally read back same row first
Attempt 3 -> bounded retry only if policy allows
No endless retries, no new run_id per attempt.
~~~

Do not turn the nonce into a secret or randomize it differently per retry and cause false mismatches. In the example, `observed_at` changes on retry if regenerated, so observe the read-back semantics discussed in Section 11.3.

### 18.3. Backpressure and load limits

A health system injecting an extra 10,000 CQL requests/s while a cluster is degraded can worsen the outage. Configure:

- Max concurrent probes per DC.
- Max QPS, bytes/s, and time window.
- Max pages/rows per query.
- Priority/throttling so business traffic comes first.
- Stop guardrails if p99 or failed requests cross thresholds.
- Never create a new client session/TLS handshake per request.

**Health probes must be lighter than the workload they monitor.**

## 19. Security, permissions, and maintenance scope

### 19.1. Least privilege

| Actor | Required permissions | Should not hold by default |
|---|---|---|
| Read-only observer | JMX/metrics or permitted metadata `SELECT` | Schema ALTER / role admin |
| CQL read probe | `SELECT` on probe + fixture | `MODIFY` on app tables |
| CQL write probe | `SELECT`/`MODIFY` on `ops_health.probes_by_run` | Cluster-wide ALL PERMISSIONS |
| Maintenance operator | Dedicated SOP/tool permissions | Application account used as admin |
| Report reader | Redacted metrics/logs | Raw secrets / heap dumps |

`nodetool` over JMX has its own auth/TLS/permissions. An app role with `SELECT` does not automatically have JMX `status` access; never make every account a superuser just to avoid separating privileges.

### 19.2. Verifying TLS and certificates after rotation

If maintenance rotates certificates or CAs:

- Test **new connections** from the actual app namespace/region, not just existing pooled connections.
- Verify the chain, SANs, NotBefore/NotAfter, and Java truststore/SSLContext.
- Never disable hostname validation or use trust-all managers.
- Distinguish client-to-node, internode, and JMX TLS.
- Verify CA overlap/rolling and recovery if one node has not switched to the new cert yet.
- Test authentication + authorization for the CQL probe role.

An OK `nodetool status` does not prove native TLS has recovered.

### 19.3. Keeping data and probe receipts safe

Reports should record:

- Outcome code, local DC, CL, query template, and run UUID.
- Duration and UTC time, release versions, and node group.
- Classified error class and safe explanation.
- Certificate fingerprint/serial **if permitted**, never private keys.
- Links to access-controlled metrics.

Never record passwords, client cert private keys, raw application tenant IDs, JWTs/tokens, heap dumps, or sensitive bind values.

## 20. Rolling restart scenario: expected state changes by phase

### 20.1. Sample timeline

~~~text
T-20m    Inventory + initial baseline + CQL probes.
T-10m    Confirm no unplanned DN/repair/backfill.
T0       Start approved restart of node A.
T+...    Node A may briefly be DOWN during planned window.
T+...    Wait A returns expected state + native CQL reachable.
T+...    Observe queues/retries/resources in recovery.
T+...    Gate A PASS => only then consider node B.
T-end    Postflight all nodes, DCs, read/write/probes/SLO.
T+obs    Sustained monitoring + evidence/close or rollback.
~~~

`T+...` denotes **condition-dependent milestones**, not a promise of fixed minutes. Never let a script sleep a fixed interval and declare PASS if state is still wrong.

### 20.2. Per-node gates differ from cluster-wide gates

A node returning to `UN` is insufficient to proceed if:

- DC/rack/host ID differs from expected.
- Quorum in another DC is impacted.
- Native transport is not yet ready.
- CQL requests to that node/region fail.
- Hints/streaming/compaction are overloaded.
- Disk/GC/network lack headroom.
- Business query correctness fails.

### 20.3. Rolling upgrades with compatibility checks

Beyond liveness/latency, when changing Cassandra/JDK/Driver versions:

- Verify mixed-version compatibility within the supported window.
- Verify prepared CQL, native protocol, codecs, and TLS/auth.
- Compare schema metadata and system tables after upgrade.
- Do not spontaneously run schema/data-format changes or `upgradesstables` unless required by the runbook.
- Maintain a backout plan and know which operations make rollback impossible.
- Monitor background compaction, hinted handoff, and repair.

## 21. Runbook A — Preflight sees a `DN` node or a node missing from inventory

**Situation:** Before maintenance begins, an observer sees 5/6 nodes `UN` and one node `DN` or absent from the list.

1. **Halt the upcoming change:** current state fails expected inventory; mark `FAIL` or `UNKNOWN` if observations are incomplete.
2. Identify the affected node by host ID, DC/rack, and expected state per the change manifest.
3. Collect `nodetool status` from at least two authorized observers, cross-checking monitoring and node inventory.
4. Distinguish `DN`, planned bootstrap `UJ`, and a node completely missing from the ring view.
5. Inspect service logs, process state, disk, network/gossip, native transport, and internode TLS.
6. Verify **per-DC RF/CL**; a `LOCAL_QUORUM` application might still work yet lack redundancy for another restart.
7. If a node is undergoing planned replace/decommission, compare against **post-change expected topology**, not necessarily the baseline.
8. Never reflexively run `nodetool removenode`, `decommission`, `replace`, or mass restarts.
9. Reopen the gate only when inventory/topology/CL, resources, and query probes satisfy policy or receive explicit incident approval.
10. Save evidence: node IDs, DC/rack, sample times, observer views, and root cause.

**Common pitfall:** scripts checking only "no DN present" while **not checking expected node count**, allowing a completely vanished node to PASS.

## 22. Runbook B — `nodetool status` shows `UN`, yet apps cannot connect via CQL

**Situation:** After TLS rotation or rolling restart, `nodetool status` looks clean, while the Java canary receives `AllNodesFailedException`.

1. Identify the app pod, region, local DC, driver/JDK version, and exact contact points.
2. Inspect `getAllErrors()` by coordinator candidate/cause; do not assume all replicas are DOWN.
3. Classify network/TCP, DNS, TLS trust/SAN/expiry, CQL credentials, or protocol mismatch.
4. Check native transport/`statusbinary` per release, without equating JMX success to native CQL success.
5. Compare the client truststore/SSLContext against the server certificate actually served on the endpoint.
6. Check role `LOGIN`, password/secret version, and probe `SELECT`/`MODIFY` permissions.
7. If the driver discovers peer addresses beyond contact points, verify SAN/DNS/routing for all required peers.
8. Fix trust/CA/secrets/endpoints per change procedure; **never use a trust-all manager or disable hostname verification**.
9. Test a **new connection** and prepared read/write from the app network in every required DC.
10. Mark PASS only when authentication, authorization, CQL queries, and resource/SLO gates all pass.

**Never** increase connection pools or retry indefinitely to work around a bad CA or wrong password.

## 23. Runbook C — Read probe PASS, write/read probe FAIL

**Situation:** `SELECT` on the reference row succeeds, while `INSERT` into `ops_health.probes_by_run` fails or read-back mismatches.

1. Verify it targets the **right table/role/environment**; does the role hold `MODIFY` on the probe table or only `SELECT`?
2. Read the error class and cause: `Unauthorized`, `InvalidQuery`, `WriteTimeout`, `Unavailable`, driver codec, or TLS.
3. Check write/read CL and RF/DC: are enough replicas available for `LOCAL_QUORUM`?
4. Check commitlog/free disk, memtable flushes, write p99, and `MutationStage Pending` if metrics exist.
5. Verify written values: `run_id/check_id/expected` must remain constant within the attempt group.
6. If `INSERT` times out, **do not assume the mutation rolled back**; perform a bounded read-back with the same key/CL and classify the uncertain outcome.
7. If SELECT returns null, check whether row TTL expired, UUID/bucket mismatched, or read-path/query routing failed.
8. On mismatch, check for concurrent runs using the same key or an expected value modified across retries.
9. Never "fix" it by writing to business tables, deleting data, lowering CL, or granting superuser.
10. HOLD maintenance, log the outcome, and fix the root cause; reopen the gate only once write path, read-back, and SLO stabilize.

**A successful read does not prove commitlog, write coordinator, replicas, or write permissions are healthy.**

## 24. Runbook D — Schema disagreement or `InvalidQuery` after upgrade

**Situation:** Some Java pods prepare CQL successfully while others report unknown column/table or `InvalidQuery` right after DDL or a rolling upgrade.

1. Identify the app versions and failing prepared CQL templates.
2. Verify exact keyspace/cluster/DC and table schema on observers.
3. Check `nodetool describecluster`/schema agreement per release.
4. Check migration order: did additive DDL run before the new app version rolled out?
5. Check column/UDT types, quoted identifiers, and CQL syntax compatibility per Cassandra/driver release.
6. Check `UnpreparedException` and driver reprepare behavior; do not confuse driver cache state with Cassandra data loss.
7. **Halt the rollout**; never re-run `DROP/CREATE TABLE` over live data.
8. If schema rollback is incompatible, trigger the approved forward-fix plan; never assume version downgrade is safe.
9. After remediation, canary prepare+execute critical query templates across all supported client versions.
10. Mark PASS only when schema/driver compatibility, correctness, errors, and latency pass.

Never directly edit `system_schema` tables or restart the entire cluster solely to force metadata sync on a hunch.

## 25. Runbook E — Poor p99 despite healthy node state and passing CQL smoke

**Situation:** After a rolling restart, 6/6 nodes are `UN` and the read-write canary passes, yet API read p99 jumped from 80 to 700 ms within a comparable workload window.

1. Confirm **absolute SLO** and regression tolerance before evaluating.
2. Compare offered/successful QPS, query mix, payloads, rows/page, and sample counts.
3. Compare worst-node GC pauses, CPU throttling, disk await, and network latency.
4. Check post-restart cold caches: OS page cache, key/chunk caches, and read paths.
5. Check pending compaction/flushes, hints replay, repair/streaming, and SSTables per read.
6. Check driver retry/speculative attempts and connection pool reestablishment.
7. Throttle non-essential background jobs, preserving user traffic priority per SOP.
8. Never increase driver timeouts to mask p99, and never treat `nodetool status` as a performance gate.
9. Keep the observation window long enough to confirm a trend back toward baseline; never PASS on a single low sample.
10. If the SLO remains breached, HOLD/rollback as feasible and preserve evidence.

**Passing correctness and `UN` readiness do not automatically pass performance SLOs.**

## 26. Runbook F — Hints, compaction, or streaming have not recovered

**Situation:** The node returned to `UN` after disk replacement/restart, yet `compactionstats` pending grows, streaming is unfinished, and hinted handoff has a backlog.

1. Identify which work was **planned** in the change (bootstrap/repair/rebuild).
2. Read `nodetool compactionstats/netstats` per release and compare time-series metrics.
3. Check free disk, device await, CPU/GC, network, and native CQL error rates.
4. Check write/read CL, replica liveness, and requests triggering retries.
5. Compare backlog trend: draining steadily or growing rapidly?
6. Do not require `compaction pending == 0` unconditionally on a cluster serving normal writes.
7. However, never PASS if the backlog grows uncontrollably or disk nears full.
8. Never trigger extra major compaction/repair/cleanup when resources lack headroom.
9. Establish checkpoints and owners to resume repair/streaming per runbook.
10. Close the change only when recovery finishes or enters an observable **accepted recovery envelope**; never force `PASS` by disabling metrics.

## 27. Runbook G — Controller missing metrics or running concurrently

**Situation:** The health dashboard fails to return GC/driver metrics while automation keeps proceeding. Two runners with the same change ID generate probes with different keys, driving up request rates.

1. Halt further actions; evaluate `UNKNOWN` due to missing evidence.
2. Check the collector, scrape timestamps, query window, app versions, and labels.
3. Never convert a metrics-endpoint timeout into a `0` value.
4. Check controller run leases, duplicate workflows, and stable `run_id` usage.
5. Check max concurrent probes/QPS, driver retry budgets, and deadlines.
6. Check whether a new `CqlSession` is accidentally created per probe request.
7. Restore observability or use a **policy-approved** fallback channel, explicitly recording the source.
8. If evidence remains insufficient, require human approval/hold; never silently bypass gates.
9. After fixing, add CI tests for missing/stale metrics and duplicate runs.
10. Save an audit trail: why the gate returned UNKNOWN and who approved proceeding or rolling back.

**No telemetry means unknown, not 100% healthy.**

## 28. Runbook H — Cross-DC failover after maintenance

**Situation:** The app works fine in dc1, yet after routing fails over to dc2, clients time out or read unexpected data.

1. Check source and destination DCs and each region's client `localDatacenter`.
2. Compare per-DC RF, replica health, and read/write CLs.
3. Check native TLS/auth/network from the **new client region** to dc2.
4. Run `LOCAL_QUORUM` read/write probes in dc2 using keys/values newly written in dc2.
5. If cross-DC visibility is required, run a **dedicated replication/convergence probe** with explicit timing and policy.
6. Check multi-DC network traffic, hints, streaming/repair, latency, and packet loss.
7. Never equate `LOCAL_QUORUM` in dc1 with quorum in dc2.
8. If stale data is a concern, check timestamps/TTL and consistency requirements; never assume a CQL read is correct just because "a row came back."
9. Keep traffic in a safe region per the failover SOP or roll back routing when permitted.
10. PASS only when **connectivity, correctness, latency, and replica recovery** all pass in the target region.

**Cross-DC failover is a serving-path change**, not merely swapping a contact point.

## 29. Health-gate automation test matrix

Apply the following tests in CI or multi-node labs as appropriate; **never auto-inject faults into production**.

| ID | Scenario | Expected outcome |
|---|---|---|
| T01 | All expected nodes `UN`, probes and SLO pass | PASS |
| T02 | An expected node `DN` before maintenance | FAIL/HOLD |
| T03 | A node missing from status output | FAIL/UNKNOWN; not PASS |
| T04 | `UJ` during a planned bootstrap phase | Phase-gated, not final PASS yet |
| T05 | `UJ` outside a planned phase | FAIL/HOLD |
| T06 | DC/rack differs from expected inventory | FAIL or investigate change |
| T07 | Node count matches but host ID changed after replace | Check replace manifest, not unconditional PASS |
| T08 | `nodetool status` exits 0 while a node is DN | FAIL |
| T09 | JMX OK, native TLS fails | CQL gate FAIL |
| T10 | Java auth wrong despite ring UN | CQL auth gate FAIL |
| T11 | Canary role lacks MODIFY | Write gate FAIL/UNKNOWN per policy |
| T12 | Reference read matches expected value | Read gate PASS |
| T13 | Reference row TTL expired | Fixture invalid/UNKNOWN, do not label data loss |
| T14 | Write succeeds, read-back mismatches | FAIL |
| T15 | Write times out, read-back finds value | Analyze outcome, do not auto-PASS everything |
| T16 | Single-key probe passes while another node is DN | Cluster gate FAIL |
| T17 | Client from dc1 passes, dc2 cannot connect | Multi-DC gate FAIL |
| T18 | New TLS connection after rotation fails | FAIL even if old pool still works |
| T19 | Schema disagreement after migration | FAIL/HOLD |
| T20 | Prepared CQL invalid on new app | FAIL/rollback or forward-fix |
| T21 | p99 exceeds absolute SLO even with passing probes | FAIL |
| T22 | Success p99 drops while timeout rate spikes | FAIL if error budget exceeded |
| T23 | Missing metrics during observation window | UNKNOWN |
| T24 | Counter reset caused by node restart | Do not compute delta across reset |
| T25 | Mild, stable compaction pending | Do not auto-FAIL if policy permits |
| T26 | Compaction backlog steadily rising / disk tight | FAIL/HOLD |
| T27 | Hints replay still running after node returns UN | Recovery gate per policy |
| T28 | Planned streaming not yet finished | Phase-aware HOLD |
| T29 | Driver retry attempts surge | HOLD/FAIL per budget |
| T30 | Two workflows share the same change ID | Prevent dual execution; lock/lease |
| T31 | A probe query times out | Bounded retry, tri-state decision |
| T32 | New CqlSession created per request | Test catches connection storm |
| T33 | Unrecognized `nodetool` output format | UNKNOWN |
| T34 | No expected node inventory provided | UNKNOWN/stop |
| T35 | Rolling node B before A has recovered | Gate blocks continuation |
| T36 | App RF/CL unsatisfied after node down | FAIL |
| T37 | Schema and state pass, API mapper fails | Business probe FAIL |
| T38 | Full-table-scan test query proposed | Guardrail blocks, requires bounded query |
| T39 | Credentials/secrets appear in logs | Security gate FAIL |
| T40 | Change completed with insufficient observation window | UNKNOWN/HOLD, not auto-PASS |

### 29.1. Test layering

- **Unit:** tri-state gate evaluation, inventory matching, parser failures, threshold windows, stale metrics, counter resets.
- **Single-node integration:** prepared CQL, auth/TLS, probe table TTL, read-back, Java driver code.
- **Multi-node cluster:** RF/CL, single-node downtime, gossip/schema state, post-restart recovery.
- **Multi-DC lab:** localDC routing, failover, inter-DC visibility, per-region auth/trust.
- **Load/fault lab:** p95/p99 behavior, retry storms, compaction backlogs, cache warm-up, capacity headroom.

A single-node RF=1 Testcontainers test does not verify RF=3/`LOCAL_QUORUM` behavior or rolling maintenance in a real DC.

### 29.2. Fixture cleanup must not cause outages

- Use TTLs to keep the probe table from growing unbounded, while monitoring tombstones/compaction.
- Never `TRUNCATE` after each test run, as it can disrupt concurrent probes.
- Never create a new table/keyspace per health check.
- Keep run IDs fixed for retries and randomized per **new run**.
- Never seed production fixtures with customer data or secrets.
- Ensure test processes close sessions cleanly without reconnect storms.

## 30. Sample pre/post-maintenance health report

### 30.1. Data sufficient for side-by-side comparison

A report can place metrics side by side:

| Check group | Preflight | Expected postflight | Observed postflight | Gate |
|---|---|---|---|---|
| Node inventory dc1 | 3 expected, 3 UN | 3 UN | 3 UN | PASS |
| Node inventory dc2 | 3 expected, 3 UN | 3 UN | 3 UN | PASS |
| Schema agreement | Yes | Yes | Yes | PASS |
| Java new connection/TLS | Yes | Yes | Yes | PASS |
| CQL read probe dc1 | Matches expected | Match | Match | PASS |
| CQL write/read dc1 | Matches expected | Match | Match | PASS |
| CQL read/write dc2 | Matches expected | Match | Timeout | FAIL |
| Representative business query | p99=90 ms | ≤ SLO | p99=140 ms | Per SLO |
| Compaction backlog | 4 pending | No drift | 11 and rising | HOLD |
| Disk headroom | 35% free | ≥ policy | 31% free | Per policy |
| Required observation | Full 15 min | Full 15 min | 5 min | UNKNOWN |

**All numbers and states in the table are hypothetical.** If `dc2` write/read FAILS or the window is incomplete, **overall cannot be PASS** even if most other rows pass.

### 30.2. YAML report schema

~~~yaml
# Sample controller output schema, not a file to create in STEP 4.
change_id: MAINT-2026-041
run_id: "7c0a0a4f-2f5a-4f6c-8c0f-b70c0a071111"
stage: postflight
timestamp_utc: "2026-11-21T10:00:00Z"
cluster_id: "approved-logical-cluster-name"
expected_topology:
  dc1: 3
  dc2: 3
checks:
  - id: topology_dc1
    status: PASS
    evidence: "Expected host IDs/racks in UN"
  - id: topology_dc2
    status: PASS
    evidence: "Expected host IDs/racks in UN"
  - id: schema
    status: PASS
    evidence: "Metadata and schema gates passed"
  - id: canary_write_read_dc2
    status: FAIL
    error_family: "READ_TIMEOUT"
    consistency: "LOCAL_QUORUM"
  - id: performance_observation_window
    status: UNKNOWN
    reason: "Only 5 of required 15 minutes"
overall: FAIL
decision: "STOP_NEXT_STEP_AND_ESCALATE"
owner: "operations-oncall"
~~~

- `PASS` applies only when the gate was actually observed and satisfied.
- `FAIL` is never overridden by another passing check.
- `UNKNOWN` requires more evidence or human review; never auto-promote to PASS.
- `run_id` identifies one check run, whereas `change_id` may span multiple pre/during/post runs.
- Metrics and source links must include timestamps, units, and sampling windows.
- Reports must never contain secrets, private keys, or sensitive customer bind values.

### 30.3. Why do reports need two types of time?

- **UTC wall-clock** to correlate logs/events across nodes and regions, alongside clock-drift checks.
- **Monotonic duration** such as Java `System.nanoTime()` to measure elapsed latency within one process.

Do not subtract wall timestamps from two hosts and call the difference exact request latency when clocks are unsynchronized. Never construct p99 by averaging separate p99s across nodes or windows.

### 30.4. Do not turn an old `PASS` into an unlimited permit

A health report that passed at 09:00 does not guarantee the cluster is healthy at 11:00 if workload or topology changed. Controllers should:

- Attach a `valid_until`/TTL to snapshots and reports.
- Re-measure before **any risky maintenance step**.
- Invalidate gates upon node changes or new alerts.
- Bind cluster, version, and change IDs to evidence.
- Block reusing reports from another DC or cluster.

## 31. Unit testing the gate model: fail closed on missing data

### 31.1. Simple gate aggregator in Java

~~~java
package example.cassandra.ops;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class GatePolicy {

    public enum Status { PASS, FAIL, UNKNOWN }

    public record Check(String id, Status status) {}

    public static Status aggregate(
            Set<String> requiredIds, List<Check> observations) {

        Map<String, Status> received = new HashMap<>();

        for (Check check : observations) {
            if (check == null
                    || check.id() == null
                    || check.status() == null
                    || !requiredIds.contains(check.id())) {
                return Status.UNKNOWN;
            }

            if (received.putIfAbsent(check.id(), check.status())
                    != null) {
                // Duplicate source/check ID: never silently take the last sample.
                return Status.UNKNOWN;
            }
        }

        if (received.values().contains(Status.FAIL)) {
            return Status.FAIL;
        }
        if (!received.keySet().containsAll(requiredIds)) {
            return Status.UNKNOWN;
        }
        if (received.values().contains(Status.UNKNOWN)) {
            return Status.UNKNOWN;
        }
        return Status.PASS;
    }
}
~~~

This example uses Java records, suitable for Java 16+; substitute POJOs on older JDKs. A production controller must also validate **freshness, sample windows, source signatures, exceptions, hysteresis, and scopes/DCs**. This is only aggregation logic, not a complete health system.

### 31.2. Testing key cases

~~~java
package example.cassandra.ops;

import org.junit.jupiter.api.Test;
import java.util.List;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static example.cassandra.ops.GatePolicy.*;

class GatePolicyTest {

    private final Set<String> required =
        Set.of("topology", "schema", "cql");

    @Test
    void allRequiredPass() {
        assertEquals(Status.PASS, aggregate(required, List.of(
            new Check("topology", Status.PASS),
            new Check("schema", Status.PASS),
            new Check("cql", Status.PASS)
        )));
    }

    @Test
    void explicitFailDominatesPass() {
        assertEquals(Status.FAIL, aggregate(required, List.of(
            new Check("topology", Status.PASS),
            new Check("schema", Status.PASS),
            new Check("cql", Status.FAIL)
        )));
    }

    @Test
    void missingEvidenceIsNotPass() {
        assertEquals(Status.UNKNOWN, aggregate(required, List.of(
            new Check("topology", Status.PASS),
            new Check("schema", Status.PASS)
        )));
    }

    @Test
    void duplicateCheckIsNotSilentlyAccepted() {
        assertEquals(Status.UNKNOWN, aggregate(required, List.of(
            new Check("topology", Status.PASS),
            new Check("topology", Status.PASS),
            new Check("schema", Status.PASS),
            new Check("cql", Status.PASS)
        )));
    }
}
~~~

In production, if there is both a FAIL and a duplicate/unrecognized observation, the logic above may return UNKNOWN before evaluating FAIL. Policy may prioritize FAIL in all circumstances; the crucial requirement is that both **UNKNOWN and FAIL block maintenance** under fail-closed rules. Organizations should explicitly define and test this precedence.

### 31.3. `nodetool` parsers must have version-contract tests

If the controller parses text output, build fixtures for:

- 3 `UN` nodes matching expected inventory.
- `DN`, `UJ`, `UL` nodes, and a completely missing node.
- Multiple DCs/racks, including DC names with special characters if supported.
- Header/spacing changes after upgrades.
- Empty/partial output or JMX timeouts.
- Schema version mismatches.
- Node replacement keeping the same IP with a new host ID.
- Output with warnings or different locales.

Never rely solely on `line.startsWith("UN")` as a safety check. On unrecognized parser output → UNKNOWN.

## 32. Practice questions with answers

### Question 1 — UN status

All six nodes show `UN`. Can we conclude Java client reads/writes and p99 are healthy?

**Answer:** No. `UN` reflects the ring/gossip view; native TLS/auth, CQL reads/writes, replica CL, queues/compaction, and SLOs still need verification.

### Question 2 — Node missing from inventory

Six nodes are expected, yet `nodetool status` displays only five `UN` rows and zero `DN` rows. Is that a PASS?

**Answer:** No. An expected node is missing; cross-check inventory, host IDs, and observer views and HOLD.

### Question 3 — JMX vs native CQL

`nodetool info` succeeds while Java reports a TLS handshake failure. Is this contradictory?

**Answer:** No. JMX and native CQL are two independent network/TLS/auth paths.

### Question 4 — RF/CL

A DC has RF=3 and the app uses `LOCAL_QUORUM`. One replica is down, two remain up. Is the logical condition met for a request to succeed?

**Answer:** Usually yes, if those two belong to the replica set and respond in time; however, **there is no remaining safety headroom** to restart another replica.

### Question 5 — Missing metrics

CQL probes PASS, yet the GC metrics exporter is unreachable. What should the controller return?

**Answer:** UNKNOWN (or FAIL if policy treats loss of observability as a violation) and block the next maintenance step; never treat missing metrics as 0 errors.

### Question 6 — Read-only

Reading the reference fixture succeeds. Can we assert the write/commitlog path is also healthy?

**Answer:** No. You need a write/read canary on an authorized table or equivalent write evidence.

### Question 7 — Write timeout

The probe `INSERT` timed out, yet read-back shows the expected value. Can we conclude the initial attempt "rolled back"?

**Answer:** No. A timeout is an uncertain outcome; reconcile by key/CL, enforce gates per policy, and do not assume success across all replicas.

### Question 8 — Non-idempotent probe

A retry generates a new `run_id` and a different expected value. What is the risk?

**Answer:** Extra rows accumulate, attempts become hard to correlate, and outcomes/mismatches are obscured. Keep run ID and expected value stable within a run.

### Question 9 — TTL

A reference row seeded yesterday used a 1-hour TTL; today `SELECT` returns 0 rows. Is Cassandra definitely broken?

**Answer:** No. The fixture expired. Use reference data with appropriate retention and distinguish expiry from read failures.

### Question 10 — Compaction backlog

`compactionstats` shows 4 pending tasks in a normal cluster. Does that automatically FAIL?

**Answer:** Not necessarily. Look at trends, workload, disk headroom, and SLO; background compaction is normal.

### Question 11 — Netstats

`nodetool netstats` is empty. Can we conclude native CQL traffic is zero?

**Answer:** No. `netstats` primarily reflects SSTable streaming.

### Question 12 — Schema agreement

`nodetool describecluster` shows matching schema versions. Can we skip prepared Java query tests?

**Answer:** No. Schema agreement does not prove driver codecs, role grants, or application queries are compatible.

### Question 13 — Lowering CL to pass

Production uses `LOCAL_QUORUM`; the probe uses `ONE` and PASSes. Does this sufficiently verify the production path?

**Answer:** No. Probes must use a CL matching the workload/consistency requirement; `ONE` masks quorum failures.

### Question 14 — P99

Three nodes report p99 of 50, 70, and 500 ms. Can we average them and call it the cluster p99?

**Answer:** No. You need histograms/raw samples with valid aggregation, plus worst-node inspection.

### Question 15 — Success-only bias

After maintenance, p99 of successful requests dropped while timeout rate rose by 5%. Is that an improvement?

**Answer:** Not by default. SLOs must evaluate both latency and errors; slow requests may simply be dropping out via timeouts.

### Question 16 — One health check per node

Does a single passing `run_id` probe key prove every replica in the ring is healthy?

**Answer:** No. One partition maps only to a specific replica set; combine inventory checks with planned multi-key/per-DC probes.

### Question 17 — Rolling

Node A is `UN`, yet p99 still breaches SLO and pending compactions are climbing. Should we restart node B now?

**Answer:** No. HOLD; wait for/restore resource and CQL/SLO gates before continuing.

### Question 18 — Cross DC

A `LOCAL_QUORUM` probe in dc1 PASSes. Are clients in dc2 guaranteed to read the same data?

**Answer:** No. Verify dc2 local routing/RF/CL and visibility/convergence separately.

### Question 19 — Read vs write role

The read canary succeeds, while writes get `Unauthorized`. Is this a replica error?

**Answer:** Likely the role lacks `MODIFY`. Classify authz before investigating replication; the probe role needs exact least-privilege grants on the probe table.

### Question 20 — Test data

Should we `INSERT` a health marker into a production `events` table to test the write path?

**Answer:** Not without explicit design and approval. Dedicated probe tables avoid triggers, CDC, and user impact.

### Question 21 — Baseline

Preflight p99 was measured off-peak and postflight at peak hour. Can we blame the entire difference on maintenance?

**Answer:** No. Account for workload mix/QPS/sample windows, using both absolute SLOs and methodical tolerances.

### Question 22 — Report reuse

Can yesterday's PASS report authorize restarting node B today?

**Answer:** Not by default. Reports have a validity window and must be invalidated when topology or conditions change.

### Question 23 — Parser

After a Cassandra upgrade, `nodetool status` column layout changes and breaks the parser. What is the safe result?

**Answer:** UNKNOWN, halting automation; update the parser and versioned test fixtures.

### Question 24 — Insufficient observation window

Postflight requires 15 minutes of SLO data, yet only 3 minutes of samples exist. Is that a PASS?

**Answer:** No. Return UNKNOWN/HOLD until enough evidence arrives; never mark PASS from a handful of requests.

### Question 25 — Maintenance rollback

A schema/data-format upgrade is not backward-compatible. Should a script auto-downgrade upon gate failure?

**Answer:** No. Rollback may be unsafe; follow an approved recovery/forward-fix SOP with human escalation and evidence.

### Question 26 — Native TLS rotation

Existing Java pools stay connected after CA rotation. Is that enough proof new clients can connect?

**Answer:** No. Test new connections with the right truststore, hostname verification, local DC, and role.

### Question 27 — Backlog

After node restart, streaming finishes while the hints backlog keeps growing. Can we close the change just because the API probe PASSes?

**Answer:** Not yet. Check the recovery envelope, trends, and workload; HOLD/require owner sign-off per policy.

### Question 28 — Representative query

The tiny probe table PASSes. A business `SELECT` on a tombstone-heavy partition times out. Can the cluster be considered healthy?

**Answer:** Not for that workload. Add bounded representative business queries and investigate the data model/tombstones/compaction.

### Question 29 — Snapshot freshness

A report from 6 hours ago showed 30% free disk, and the node is currently running repair. Is that enough to approve a restart?

**Answer:** No. Require fresh metrics for the exact node/device and safety headroom at decision time.

### Question 30 — Final PASS

What are the minimum conditions to close maintenance?

**Answer:** Expected topology/replicas, native CQL auth/read/write and business correctness, error/p95/p99/resource headroom, recovery/backlogs within policy, full observation window, and retained evidence must all pass; missing any hard gate precludes PASS.

## 33. Pre/post verification and handover checklist

### 33.1. Pre-window preparation

~~~text
[ ] Change ID, owner, scope, and approval documented.
[ ] Expected inventory by node host ID, DC/rack, token/phase defined.
[ ] Cassandra/JDK/driver versions and schema/migration plan pinned.
[ ] RF/CL defined for every workload and DC.
[ ] In-flight repair/backup/streaming/backfill identified.
[ ] Rollback/recovery SOP and automation boundaries established.
[ ] Baseline workload/latency/error and resource headroom recorded.
[ ] SLO thresholds, hard/soft gates, and observation window defined.
[ ] Probe keyspace/table created ahead of time, least-privilege role, TTL policy.
[ ] Stable reference row or authorized non-expiring fixture ready.
[ ] No secrets/passwords/raw customer data in scripts or logs.
[ ] Controller enforces lock/lease, rate limits, budgets, and deadlines.
~~~

### 33.2. Preflight gate

~~~text
[ ] nodetool/JMX readable from authorized observers.
[ ] Expected node count, host IDs, DC/rack, and states match.
[ ] No unexpected DN/Joining/Leaving/Moving nodes.
[ ] Schema agreement and driver metadata/query compatibility pass.
[ ] RF/CL sufficient, with no concurrent maintenance removing redundancy.
[ ] New native TLS/auth connections succeed from app network/regions.
[ ] Read-only fixture query and expected result match.
[ ] Write/read probe on ops_health passes if required by manifest.
[ ] Representative business queries pass with bounded inputs.
[ ] p95/p99, timeouts/errors, and attempts/s meet policy.
[ ] Worst-node CPU/GC/heap/disk/network/headroom pass.
[ ] Hints, streaming, compaction, and repair do not violate gates.
[ ] Every check has a timestamp/source and is fresh.
[ ] Overall PASS; FAIL/UNKNOWN means stop and investigate.
~~~

### 33.3. During rolling maintenance

~~~text
[ ] Each node has an expected phase and RF/CL safety boundary.
[ ] Never start the next step until the previous node's gate PASSes.
[ ] Observe topology from multiple seeds, not a single text output.
[ ] Verify CQL new connections, app queries, and auth/permissions.
[ ] Check latency/errors, retries, queues, and disk/GC.
[ ] Stop on unexpected DN, unavailable, OOM, or disk pressure.
[ ] Probe rate/concurrency will not storm a degraded cluster.
[ ] Designated owner ready if rollback/forward-fix is required.
[ ] Never ad-hoc edit system tables, CL, grants, or schema outside plan.
~~~

### 33.4. Postflight and change closure

~~~text
[ ] Actual topology/DC/rack/tokens match expected manifest.
[ ] Nodes reached target state with no unexpected phases remaining.
[ ] Cassandra/schema/driver/JDK versions match the plan.
[ ] App new connections, TLS/auth/permissions pass.
[ ] Read & write/read-back probes pass in all required DCs.
[ ] Representative business queries, mappers, and pagination pass.
[ ] RF/CL, data correctness, and multi-DC policies satisfied.
[ ] p95/p99, timeouts/errors, and retries within absolute SLO/budget.
[ ] Node resources/compaction/hints/streaming show stable trends.
[ ] Observation window is long enough with reliable sample counts.
[ ] PASS/FAIL/UNKNOWN, reasons, and evidence archived.
[ ] Owner sign-off recorded before closing the change.
[ ] Do not apply Step 6 Content QA during this writing step.
~~~

## 34. Anti-patterns to catch in code review

| Anti-pattern | Why it causes bad decisions | How to fix |
|---|---|---|
| `nodetool status` exit 0 = healthy | Only proves the command ran | Parse inventory/state |
| Grep finds no DN = PASS | A node may be missing from output | Match expected host IDs/nodes |
| Running only one probe key | Does not cover tokens/DC/rack | Topology gate + coverage |
| Read-only PASS = writes healthy | Never exercises commitlog/write quorum | Add write/read-back |
| CL ONE instead of LOCAL_QUORUM | Masks quorum failures | Match production workload CL |
| Smoke test with admin role | Masks app RBAC failures | Least-privilege representative role |
| Local node cqlsh instead of Java pod | Different network/TLS/driver | Probe from app path |
| Reusing existing pool after cert rotation | Skips reconnect/new trust validation | New connection canary |
| Returning `healthy=true` on exporter timeout | Missing evidence | UNKNOWN, fail closed |
| Treating missing metric as 0 | False healthy | Freshness/source gate |
| PASS only when 0 compactions | Background compaction is normal | Trend, disk, SLO |
| Fixed 30-second sleep then PASS | Recovery depends on load | Condition-based polling |
| Running `repair` as health check | Mutating/storage-heavy operation | Read-only observability |
| Testing with full-table scan | Causes resource spikes itself | Bounded/full partition key query |
| Writing to user tables | Triggers/CDC/side effects | Dedicated probe table |
| `TRUNCATE` probe table every run | Disrupts other probes | TTL/retention strategy |
| New run UUID per retry | Creates extra rows / hard to reconcile | Stable ID per run |
| New session per probe request | TLS/connection storm | Reuse CqlSession |
| No QPS cap on checker | Overwhelms degraded cluster | Bounded concurrency/rate |
| Checking only success p99 | Hides timeout failures | Error budget + p99 |
| Averaging node p99s | Percentiles are non-linear | Histograms/raw samples |
| Comparing before/after across traffic mixes | False regression/fix | Absolute SLO and workload context |
| Ignoring expected topology deltas | Topology changes misclassified | Change manifest |
| Auto-downgrading after incompatible schema | Risks data loss | Approved recovery SOP |
| Reusing stale PASS as permit | Health is point-in-time | Validity TTL/recheck |
| Logging credentials/PKI private keys | Secret leakage | Redaction/least privilege |

## 35. Summary

A high-quality **pre- and post-maintenance health check workflow using status and queries** upholds the following principles:

1. **Never equate Up/Normal with healthy.** `nodetool status` is one topology/gossip source; native CQL, replica CL, and p99 must be checked separately.
2. **Verify against expected inventory**, not merely counting present `UN` nodes. Host IDs, DC/rack, topology phases, and planned changes all matter.
3. **Evaluate availability through RF/CL**: having quorum for one request does not mean it is safe to restart another node or fail over.
4. **Preflight and postflight are scoped, time-bounded gates**; yesterday's healthy state does not substitute for checks at maintenance time.
5. **Read and write/read-back probes complement each other.** Probes must be small, typed, least-privilege, and isolated to a dedicated table; results are always scoped.
6. **Prepared Java Driver tests must traverse the real network/TLS/auth/local DC path** and query by partition key; local admin `cqlsh` is not an adequate sole proxy.
7. **Verify schema/migrations and app codecs**, especially during rolling upgrades; schema agreement does not guarantee every prepared query works.
8. **Resources and tail latency are independent gates**, covering CPU/GC/memory/disk/compaction/hints/streaming/retries as well as application API SLOs.
9. **Tri-state PASS/FAIL/UNKNOWN protects automation**; missing metrics, broken parsers, or short windows must never become PASS.
10. **Rolling execution must be condition-based**, gated after each node; never proceed on fixed sleep timers or while a node remains unrecovered.
11. **Retain auditable evidence** keyed by change ID, run UUID, CL, DC, query template, UTC time, duration, metric sources, and action decisions.
12. **Never turn health checks into maintenance operations**: do not run repair/compact/cleanup, alter CL/schema, disable TLS, or grant privileges without an SOP.

The core question before authorizing the next maintenance step is not **"Do all nodes report UN?"**, but rather: **"Is the cluster in the exact expected topology, can the Java application read and write accurately by partition key and required consistency level, do tail latency and resources have enough headroom, are recovery tasks stable, and are all conclusions backed by fresh, trustworthy evidence?"**

Only when every mandatory condition truly passes does the controller have grounds to emit **PASS**. On any violation, emit **FAIL**; on missing evidence, emit **UNKNOWN** and keep the cluster safe.
