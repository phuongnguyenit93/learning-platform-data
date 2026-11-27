# Observing Replication Lag and Server Role Changes in Spring Data Redis

## 1. Why Monitor Replication and Role Changes?

Redis supports replication between a primary and replicas, and can automatically switch roles when using Sentinel or Redis Cluster. Yet a Spring Boot application receiving `OK` from a Redis primary **does not mean every replica has applied the write**, and having a new primary **does not mean the data on the new primary matches the old primary at the moment of failure**.

Example:

```text
                          Spring Boot
                         RedisTemplate
                              |
                              v
                        Redis primary A
                     offset = 1,000,000
                        /          \
                       v            v
                 Replica B      Replica C
                 998,000        999,900
```

At a given moment, the primary records Replica B trailing by 2,000 offset units and Replica C by 100. Then Primary A fails; Replica C is promoted to become the new primary.

Operational questions:

- Which replica is lagging, and in what unit?
- Which replicas are connected yet undergoing full synchronization?
- Does the current primary match the primary announced by Sentinel/Cluster?
- Are writes acknowledged on A still present on C?
- Does the application still hit `READONLY`, `MOVED`, timeouts, or stale connections?
- How long does it take from Primary A failing until Spring writes succeed again?
- After failover, have the remaining replicas caught up to the new primary?

This lesson walks through reading Redis metrics, detecting role changes, designing dashboards and alerts, Spring Data Redis examples, and fault-testing exercises.

> **Key takeaway:** Monitoring replication lag and role changes helps assess recoverability and the risk of stale reads or write loss. It does not magically turn asynchronous replication into durable transactions or guarantee zero downtime.

## 2. Foundational Concepts

| Concept | Meaning |
| --- | --- |
| Primary/master | Redis node serving writes for the data it manages |
| Replica | Copy of a primary, synchronized over the replication stream |
| Replication offset | Progress in the replication stream, measured in bytes |
| Replication lag | A delay whose measurement method must be explicitly defined |
| ACK age | Time elapsed since the latest replication acknowledgment per a specific metric |
| Full synchronization | Replica receives the full dataset again from the primary |
| Partial resynchronization | Replica catches up from an offset using the backlog when eligible |
| Role change | Node switching between primary and replica roles |
| Promotion | A replica being elevated to primary |
| Failover | Replacing a failed primary with another node to restore service |
| Sentinel | Monitors and coordinates failover for a primary–replica group |
| Redis Cluster | Sharding by hash slots, with per-shard replication and failover |
| RPO | Target amount of data loss tolerable during recovery |
| RTO | Target time to restore service |

In Redis output, field names like `role:slave` and `connected_slaves` still appear commonly even though documentation uses **replica**. Dashboards can label them `primary/replica`, but protocol parsers must recognize the actual field names.

## 3. "Replication Lag" Has at Least Three Different Meanings

### 3.1. Offset Gap in Bytes

Assuming the same replication history at roughly the same timestamp:

```text
primary master_repl_offset   = 1,500,000
replica acknowledged offset  = 1,494,000

offset gap = 6,000 bytes
```

That is a **replication stream progress gap**, not "6,000 milliseconds".

### 3.2. Age of the Replica ACK

On the primary, a line such as:

```text
slave0:ip=10.20.0.12,port=6379,state=online,offset=1494000,lag=0
```

reflects what the primary knows about the replica. Here `lag` relates to the seconds elapsed since the latest acknowledgment received by the primary from that replica—**it does not directly measure the age of each business record**.

A replica can have a recent ACK yet still trail behind in applied data under heavy write workloads.

### 3.3. Staleness of Data Read from a Replica

This is what users actually experience:

```text
Primary: product:42:price = 120000
Replica: product:42:price = 100000

How long until reading the replica sees 120000?
```

To observe this, you can write a heartbeat/sequence key on the primary and read it explicitly from the replica. The result is **application-visible staleness**, distinct from raw offset gap and ACK age.

A dashboard should separate:

```text
replication_offset_gap_bytes
replication_ack_age_seconds
replica_observed_staleness_seconds
```

These names are suggested internal conventions; not every exporter emits these exact names.

## 4. Asynchronous Replication Creates a Write-Loss Window

Typical flow:

```text
Spring app              Primary A                 Replica B
    |                       |                         |
    | SET key v2            |                         |
    |---------------------->|                         |
    |                       | apply v2                |
    |<----------------------| OK                      |
    |                       |                         |
    |                       | replication stream      |
    |                       |------------------------>|
    |                       |                         | apply v2
```

Standard Redis replication is asynchronous, so the primary can reply before the replica receives the write.

Failure scenario:

```text
T0: A and B both hold key=v1
T1: Spring -> A: SET key v2
T2: A replies OK
T3: A dies before B receives v2
T4: B is promoted to primary
T5: Spring reads B -> v1
```

A large offset gap metric warns of risk. Yet an offset gap of 0 at the previous scrape **does not guarantee writes arriving after that scrape will survive**.

Likewise, `OK` from Redis does not mean the write has been fsynced to disk on every node. Distinguish replication, persistence, and failover.

## 5. Observe Across Multiple Layers, Not Just PING

A monitoring system should inspect:

```text
                      Spring Boot service
                       |            |
                  latency/errors   Redis client reconnects
                       |            |
                       v            v
                    Redis primary/replicas
                          |      |
                    INFO replication
                    ROLE / persistence
                          |
               Sentinel or Cluster
                 master, slots, roles
                          |
                          v
                  Prometheus / Grafana
                     Alerts / Logs
```

Layers:

1. **Redis data nodes:** role, offsets, upstream link, full sync.
2. **Replication group or shard:** current primary, healthy replicas, offset gap.
3. **Control plane:** how Sentinel or Redis Cluster sees the topology.
4. **Spring Data Redis client:** command latency, connection failures, timeouts, redirects.
5. **Persistence/recovery:** AOF/RDB errors and backup timestamps.
6. **Business:** stale reads, retry rates, overdue work.

A successful `PING` is only a basic connectivity check; it does not confirm replicas are caught up or that the application has discovered the new master.

## 6. INFO replication on the Primary

Redis command:

```bash
redis-cli -h redis-primary.internal -p 6379 INFO replication
```

Example output (illustrative):

```text
# Replication
role:master
connected_slaves:2
slave0:ip=10.20.0.12,port=6379,state=online,offset=1950200,lag=0
slave1:ip=10.20.0.13,port=6379,state=online,offset=1948600,lag=1
master_replid:2a1...
master_repl_offset:1951000
repl_backlog_active:1
repl_backlog_size:1048576
```

| Field | Meaning |
| --- | --- |
| `role` | Current node role |
| `connected_slaves` | Number of connected replicas reported by the primary |
| `slaveN.ip`/`port` | Replica endpoint |
| `slaveN.state` | Online/sync state of the replica as seen by the primary |
| `slaveN.offset` | Replica progress tracked by the primary |
| `slaveN.lag` | ACK age according to the primary, not absolute data staleness |
| `master_replid` | Replication history identifier |
| `master_repl_offset` | Current primary offset |
| `repl_backlog_active` | Replication backlog active flag |
| `repl_backlog_size` | Backlog buffer capacity; not current lag |

The field set can vary by Redis version. Do not write a rigid parser assuming every version returns the same fields or ordering of `slave0`, `slave1`.

## 7. INFO replication on a Replica

Command:

```bash
redis-cli -h redis-replica.internal -p 6379 INFO replication
```

Example:

```text
# Replication
role:slave
master_host:10.20.0.11
master_port:6379
master_link_status:up
master_last_io_seconds_ago:1
master_sync_in_progress:0
slave_read_repl_offset:1950200
slave_repl_offset:1950200
slave_priority:100
slave_read_only:1
```

Fields to watch:

- `master_host`, `master_port`: current upstream. After a failover, this address may change.
- `master_link_status`: current replication link status.
- `master_last_io_seconds_ago`: seconds since last I/O with the master—**does not mean data is stale by that exact number of seconds**.
- `master_sync_in_progress`: whether a full synchronization is underway.
- `slave_repl_offset`: replica progress field provided by your Redis version.
- `slave_read_repl_offset`: available on supported versions to observe stream read progress.
- `slave_priority`: parameter influencing replica selection during certain failover mechanisms.

If a replica is undergoing a full resync, offset gap cannot simply be interpreted as normal catch-up lag; inspect snapshot/sync progress and link health as well.

## 8. Computing Offset Gap Meaningfully

From the primary:

```text
master_repl_offset = 1,951,000
slave0.offset      = 1,950,200
slave1.offset      = 1,948,600
```

We get:

```text
slave0 gap = 800 bytes
slave1 gap = 2,400 bytes
```

Formula for a valid observation:

```text
offset_gap_bytes =
    max(0, master_repl_offset - replica_ack_offset)
```

Conditions:

1. Same primary/replication history.
2. Measurements captured at nearly the same timestamp.
3. Replica is not in a state where comparison is meaningless, such as initial full sync.
4. Never subtract a pre-failover primary offset from a new primary's offset under a different history.
5. Never mix offsets across two different Redis Cluster shards.

Tag metrics with `node_id`, `replication_group`, `master_replid` or generation metadata, and scrape timestamp.

**A negative gap or abnormal jump** can stem from unsynchronized scrape times, a history change, mis-mapped nodes, or exporter resets. Never simply clamp negatives to 0 and declare the system healthy.

## 9. Why Offset Gap Is Not Seconds

Examples:

| Primary Workload | What a 100 KB Gap Might Mean |
| --- | --- |
| Writing 20 MB per second | A very brief interval under ideal conditions |
| Writing 1 KB per minute | Could represent a long accumulated delay |
| Replication link down | Stops advancing even if workload is tiny |
| Full sync | Other sync states apply beyond stream byte gap |
| No new writes | Gap is 0 yet the link may already be down |

Offset gap is measured in bytes, not time. To estimate business data age, use a controlled probe carrying a sequence or timestamp.

Do not convert bytes to seconds by dividing by average throughput if enforcing a strict SLA; throughput varies dramatically over time.

## 10. Link Up Does Not Prove the Replica Has Caught Up

A replica may show:

```text
master_link_status:up
master_sync_in_progress:0
```

while its offset gap remains large during sustained primary writes.

Conversely, a replica with:

```text
master_link_status:down
```

and a last-known gap of 0 because no new writes occurred still needs an alert for broken replication.

Combine signals:

```text
link status
sync status
offset gap
ACK age
last I/O age
replica eligibility
server health
```

A simple health classification:

```text
link down                -> unhealthy
full sync running        -> syncing
sustained rising gap     -> lagging
all signals stable       -> currently healthy
```

This is an operational classification, not Redis's formal failover election rule.

## 11. ROLE: Checking a Node's Actual Role

Command:

```bash
redis-cli -h redis-node.internal -p 6379 ROLE
```

Primary output typically begins with:

```text
1) "master"
2) (integer) <replication-offset>
3) ...
```

Replica output typically begins with:

```text
1) "slave"
2) "<upstream-host>"
3) (integer) <upstream-port>
4) "connected"
5) (integer) <replication-offset>
```

Remaining array shape varies by Redis role and version; do not parse every role using identical array indices.

`ROLE` verifies whether the node you are **actually connected to** is currently a primary or replica. `INFO replication` offers a broader set of fields for time-series monitoring.

Normalize labels on dashboards:

```text
Redis role "master" -> primary
Redis role "slave"  -> replica
```

Keep raw fields in debug logs if needed for cross-checking with Redis CLI.

## 12. Sentinel: Master Identity Is Part of Observability

Redis Sentinel coordinates failover for a primary–replica group. Applications connect by logical group name, such as `mymaster`:

```text
Sentinel A -------\
Sentinel B --------+---- mymaster
Sentinel C -------/
                         |
                         v
                       Primary A
                         |
                         v
                       Replica B
```

Commands:

```bash
redis-cli -h sentinel-a.internal -p 26379 SENTINEL get-master-addr-by-name mymaster
redis-cli -h sentinel-a.internal -p 26379 SENTINEL master mymaster
redis-cli -h sentinel-a.internal -p 26379 SENTINEL replicas mymaster
redis-cli -h sentinel-a.internal -p 26379 SENTINEL sentinels mymaster
```

What to track:

- Current master endpoint for `mymaster`.
- When that address changes.
- Whether all Sentinels agree on the master.
- Down/failover states.
- Which replica was promoted.
- Whether remaining replicas have re-pointed to the new master.

`mymaster` is a **master group name**, not a hostname. It is declared in Sentinel:

```conf
sentinel monitor mymaster 10.20.0.11 6379 2
```

If an application records only the master name without tracking the resolved endpoint, dashboards can miss node switches after failover.

## 13. Sentinel Events and Pub/Sub Limitations

Sentinel emits events such as:

```text
+sdown
-sdown
+odown
+new-epoch
+try-failover
+failover-end
+switch-master
+slave-reconf-sent
+slave-reconf-inprog
+slave-reconf-done
```

Exact events and ordering depend on failure type and Redis/Sentinel version.

You can observe them in a test environment:

```bash
redis-cli -h sentinel-a.internal -p 26379 PSUBSCRIBE '*'
```

`+switch-master` is especially useful: it indicates Sentinel switched the monitored master.

**However, Sentinel events over Pub/Sub are not a durable log for offline subscribers.** If a monitor disconnects, it may miss emitted events.

A more reliable design:

```text
Sentinel Pub/Sub event -> fast update / log
             +
Poll Sentinel master address periodically
             +
Compare topology against previous snapshot
```

Even if `+switch-master` is missed, the next poll cycle still detects that the master endpoint changed.

## 14. Sentinel Failover Timeline

Hypothetical milestone timestamps:

```text
10:00:00  A is primary; B/C are replicas
10:00:04  A stops responding
10:00:07  Sentinel detects SDOWN/ODOWN once quorum conditions hold
10:00:10  B is promoted to primary
10:00:12  Sentinel announces mymaster -> B
10:00:13  Lettuce reconnects / rediscovers topology
10:00:15  Spring writes to B succeed
10:00:25  C follows B and catches up
```

Metrics along the timeline:

| Phase | Redis/Sentinel Signal | Application Signal |
| --- | --- | --- |
| Fault | Node unreachable, link down | Timeouts / connection errors |
| Detection | SDOWN/ODOWN | Retries / fallbacks |
| Promotion | Switch-master, node role | May still hold stale connections |
| Reconnect | New master address | Reconnects, possible `READONLY` |
| Recovery | Replication stabilized | Successful writes / normal latency |
| Post-recovery | Replica offsets caught up | Critical data reconciliation |

Do not measure only the time from SDOWN detection to `+switch-master` and treat that as **user-perceived RTO**. Measure until real application requests succeed again.

## 15. Redis Cluster: Per-Shard Replication and Roles

Redis Cluster partitions data across **16,384 hash slots**. Each primary owns a set of slots and can have replicas:

```text
                   Redis Cluster
            +-----------+-----------+
            |           |           |
         Primary A   Primary B   Primary C
          slots A     slots B     slots C
            |           |           |
         Replica A1  Replica B1  Replica C1
```

If Primary B fails, Replica B1 can be promoted and take over **slots B**.

In Cluster, monitor:

- Node ID and role.
- Each replica's primary.
- Slot ownership.
- `cluster_state` and slot coverage.
- Replication offsets **within each shard**.
- Role changes and corresponding epoch/topology.
- Cluster bus/network health.

You cannot subtract Replica C1's offset from Primary A's offset to compute replication lag because they belong to **two separate replication streams**.

## 16. Redis Cluster Commands for Monitoring

Commands:

```bash
redis-cli -c -h redis-node-1.internal -p 6379 CLUSTER INFO
redis-cli -c -h redis-node-1.internal -p 6379 CLUSTER NODES
redis-cli -c -h redis-node-1.internal -p 6379 CLUSTER SHARDS
redis-cli -c -h redis-node-1.internal -p 6379 CLUSTER SLOTS
```

Check:

- Whether `cluster_state` is `ok` or `fail`.
- How many hash slots are assigned and served.
- Which nodes are masters vs. replicas.
- Nodes flagged `fail`, `pfail`, or abnormal states.
- Which slot ranges belong to which primary.
- Which replica follows which primary.
- After promotion, which node ID took over the old slots.

`CLUSTER SHARDS` is available in supported Redis versions. On older environments, use `CLUSTER NODES`/`CLUSTER SLOTS` as supported.

**Redis Cluster does not use Sentinel to fail over shards.** Do not rely on Sentinel `+switch-master` events to track Redis Cluster role changes.

## 17. Failover vs. Resharding

Both change topology, yet serve different purposes.

**Failover:**

```text
Primary B fails
Replica B1 is promoted
B1 holds slots B
```

**Resharding:**

```text
Primary D is added
Some slots migrate from A/B/C to D
Key migration and redirects
```

During resharding, clients may receive `ASK` and `MOVED`. During failover, clients may encounter `READONLY`, `MOVED`, timeouts, or cluster state errors depending on timing.

Do not assume "failover" just because a node's slot count changed. Role-change logs should include:

```text
timestamp
replication_group/shard
old_node_id / new_node_id
old_role / new_role
old_primary / new_primary
owned_slots_before / after
observation_source
```

Dashboards should distinguish planned resharding, rolling restarts, and unexpected failovers so alerts fire accurately.

## 18. Master Endpoint Differs from Master Role

An application monitoring trap:

```text
T0: Spring -> Redis A, INFO role=master
T1: Failover A -> B
T2: Spring -> Redis B, INFO role=master
```

If you only compare the string `master`, the monitor reports "no change", yet the actual primary switched from A to B.

Track:

- Sentinel master name and **resolved master endpoint**.
- Redis Cluster **node ID** and slot ownership.
- Replication ID/generation when tracking offsets.
- Observation timestamps and control-plane data.

Role only says "the node I am inspecting is currently a primary"—not "it is the same node as last time".

## 19. Replication ID and Generation After Failover

Redis replication uses metadata such as replication ID and offset to identify a stream/history. When topology changes, the new primary can start a new identity/history; some mechanisms retain a secondary replication ID across transitions.

Common mistake:

```text
A's offset before failover = 10,000,000
B's offset after failover  =  9,990,000

=> exactly 10,000 bytes of business data lost
```

You cannot conclude this from two raw numbers alone, because:

- Replication histories may differ.
- Metric scrapes may come from different timestamps.
- Byte offsets do not map 1:1 to business record counts.
- B was promoted and stream identity changed.
- Replica ACK state may not reflect actual data durability.

When master identity/history changes, **rebaseline the metric** and record the generation. Never graph negative offset rates across a failover or alert on data loss using naive subtraction.

## 20. Observing Through Spring Data Redis

Spring Data Redis provides `RedisConnectionFactory`, `RedisTemplate`/`StringRedisTemplate`, and server command APIs.

An illustrative component reading `INFO replication` from a factory-provided connection:

```java
package com.example.monitoring;

import java.util.Properties;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class RedisReplicationInspector {

    private final StringRedisTemplate template;

    public RedisReplicationInspector(
            StringRedisTemplate template) {
        this.template = template;
    }

    public Properties readInfo() {
        return template.execute(
            (RedisCallback<Properties>) connection ->
                connection.serverCommands().info("replication")
        );
    }
}
```

This example uses `RedisServerCommands` at the connection level as supported by your Spring Data Redis version.

**Crucial limitation:** this snippet reads from whichever single connection the factory picks. It **does not automatically query every replica or every Redis Cluster shard**. With Sentinel or Cluster, the factory may switch nodes after failover, so the application still needs control-plane topology monitoring.

Do not treat this snippet as a fleet-wide Redis exporter.

## 21. Reading Role Defensively

A service normalizing role names:

```java
package com.example.monitoring;

import java.util.Properties;
import org.springframework.stereotype.Service;

@Service
public class RedisRoleInspector {

    private final RedisReplicationInspector inspector;

    public RedisRoleInspector(
            RedisReplicationInspector inspector) {
        this.inspector = inspector;
    }

    public String currentRole() {
        Properties info = inspector.readInfo();

        if (info == null) {
            return "unknown";
        }

        String role = info.getProperty("role", "unknown");

        return switch (role) {
            case "master" -> "primary";
            case "slave", "replica" -> "replica";
            default -> "unknown";
        };
    }
}
```

The `switch` expression requires a compatible Java version; on older Java versions, replace it with `if/else`.

Never turn a connection error into `primary`, never guess role from a hostname, and never use role-observation code to orchestrate failover yourself.

## 22. Polling Role Changes in Spring

A simple example using Spring Scheduling:

```java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicReference;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class RedisRoleObserver {

    private static final Logger log =
        LoggerFactory.getLogger(RedisRoleObserver.class);

    private final RedisRoleInspector roles;
    private final AtomicReference<String> previous =
        new AtomicReference<>("unknown");

    public RedisRoleObserver(RedisRoleInspector roles) {
        this.roles = roles;
    }

    @Scheduled(
        fixedDelay = 10_000,
        initialDelay = 10_000
    )
    public void pollRole() {
        try {
            String role = roles.currentRole();
            String old = previous.getAndSet(role);

            if (!old.equals(role)) {
                log.info(
                    "Observed Redis role: {} -> {}",
                    old, role
                );
            }
        } catch (RuntimeException ex) {
            log.warn("Cannot query Redis role", ex);
        }
    }
}
```

Enable scheduling with `@EnableScheduling`:

```java
@Configuration
@EnableScheduling
public class RedisMonitoringConfig { }
```

Import the corresponding Spring annotations.

### Limitations of This Example

- Polling can miss transitions occurring between two polls.
- On app restart, `unknown -> primary` does not prove a failover happened.
- With Sentinel, before and after failover the factory may still report `master` even though the underlying node changed.
- No node ID or endpoint is included in that check.
- A single connection does not gather full Redis Cluster topology.
- If the monitor is offline during failover, the JVM itself lacks complete role-change history.

To detect primary changes reliably, combine **master identity/endpoint polling** with control-plane events.

## 23. Spring Boot Sentinel Configuration and Observation Scope

Modern Spring Boot:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      sentinel:
        master: mymaster
        nodes:
          - sentinel-a.internal:26379
          - sentinel-b.internal:26379
          - sentinel-c.internal:26379
      connect-timeout: 3s
      timeout: 3s
```

A Sentinel-aware client discovers the primary. However, that configuration does not automatically make every command safely retryable or eliminate downtime windows during failover.

Monitor simultaneously:

1. Master endpoint from Sentinel.
2. Role and replication `INFO` across all data nodes.
3. Lettuce command errors, reconnects, and latency.
4. Business requests that failed to complete.
5. Timestamp when writes succeed again.

On older Spring Boot versions, the property prefix may be `spring.redis.*` instead of `spring.data.redis.*`. Use the property namespace matching your version.

## 24. Spring Boot Redis Cluster Configuration

Example:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      cluster:
        nodes:
          - redis-a.internal:6379
          - redis-b.internal:6379
          - redis-c.internal:6379
        max-redirects: 5
      connect-timeout: 3s
      timeout: 3s
```

`cluster.nodes` lists seed nodes for topology discovery; it is not automatically the full list of replicas to monitor.

To monitor the entire cluster, use an exporter or topology-aware collector that queries **every Redis data node**.

Spring client errors like `MOVED`/`ASK` can surface when topology or slot ownership changes. Distinguish cluster redirects from replication lag.

`max-redirects` is not a safe business-level retry count after timeouts.

## 25. When Using Lettuce to Read from Replicas

Lettuce offers `ReadFrom` policies in supported configurations:

```java
import io.lettuce.core.ReadFrom;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;

LettuceClientConfiguration client =
    LettuceClientConfiguration.builder()
        .readFrom(ReadFrom.REPLICA_PREFERRED)
        .build();
```

This snippet creates only the client configuration; attach it to your connection factory according to your Spring Data Redis version.

With `REPLICA_PREFERRED`, the client can fall back to the primary when no suitable replica is available. Thus, a `GET` returning fresh data **does not prove** the replica you intended to test has caught up; the request may have been routed to the primary.

For a staleness probe:

- Read directly from a **specific replica** using a dedicated monitoring connection.
- Verify node ID/role before and after the measurement.
- Never rely on a read path with automatic fallback.
- Never use a probe on a single Redis Cluster slot to represent all shards.

## 26. Staleness Probe Using Heartbeat/Sequence

Suppose the application writes a dedicated heartbeat:

```text
monitor:replication:shard-b
value = sequence:1024, time:...
```

Flow:

```text
T0  Write sequence 1024 on primary B
T1  Read replica B1 -> sequence 1022
T2  Read replica B1 -> sequence 1023
T3  Read replica B1 -> sequence 1024
```

From this, you can observe how many heartbeat versions behind the replica is and the delay from when the primary accepted a version until the replica exposes it.

Conditions:

- Sequence must increase monotonically within a generation.
- Do not write to the same key from multiple uncoordinated producers.
- The read path must target the intended replica directly.
- If using timestamps, watch for clock skew; measure elapsed time using the monitoring system's own clock alongside send time.
- Redis Cluster needs a probe per shard if you want visibility into each replication stream.
- Use a dedicated key, reasonable TTL, and low frequency to avoid adding load.
- On failover, detect the new generation and rebaseline the probe appropriately.

A staleness probe checks **one specific data path**, not proof that every key is equally fresh.

## 27. Redis Exporter and Metrics

A monitoring architecture may look like:

```text
Redis primary ----> exporter ------\
Redis replica ----> exporter -------+--> Prometheus --> Grafana
Redis Sentinel ---> control-plane -/
Redis Cluster ----> topology collector
Spring Boot ------> Micrometer/Actuator
```

Semantically important metrics:

| Group | Example Signals |
| --- | --- |
| Node role | Node ID, role, primary identity |
| Replication link | Up/down, last I/O age |
| Replication progress | Primary/replica offsets, gap |
| ACK | ACK age, replica online state |
| Sync | Full sync in progress, sync failures |
| Topology | Sentinel master, Cluster slot ownership |
| Availability | Redis up, cluster state |
| Persistence | AOF/RDB write status |
| Application | Redis command latency/errors/reconnects |
| Business | Stale reads, overdue work, fallback rate |

Actual Prometheus series names depend on your exporter, Redis version, and labeling. Never assume every exporter emits `redis_replication_lag_seconds` with identical semantics.

Useful labels:

```text
environment
cluster
replication_group
shard
node_id
role
availability_zone
```

Avoid user IDs, tokens, or individual keys as metric labels to prevent cardinality explosion.

## 28. A Dashboard Should Have Four Sections

### Topology Overview

```text
Group: mymaster
Primary now: redis-b.internal:6379
Replicas: redis-a, redis-c
Last observed master switch: 10:00:12
Quorum/topology health: available
```

### Replication

| Node | Role | Link | Offset Gap | ACK Age | Sync |
| --- | --- | --- | ---: | ---: | --- |
| Redis B | Primary | — | — | — | — |
| Redis A | Replica | Up | 800 B | 0 s | No |
| Redis C | Replica | Up | 2,400 B | 1 s | No |

Illustrative numbers. In production, use time series and master identity/generation metadata.

### Application

```text
Redis command p95 / p99 latency
Timeout rate
READONLY / CLUSTERDOWN errors
Reconnect attempts
Redis fallback rate
Request failure rate
```

### Recovery

```text
Role changes in last 24h
Replica full sync duration
AOF/RDB errors
Last successful backup
Last tested restore
Time from failure to successful application write
```

A dashboard showing only `redis_up=1` without replication lag, role changes, and application errors remains severely incomplete.

## 29. Alert Design: Avoid One Fixed Threshold for Every Workload

| Alert | Reference Condition | Purpose |
| --- | --- | --- |
| Replica link down | Link down past tolerance window | Detect broken replication |
| High replica lag | Sustained high offset gap within same history | Detect insufficient catch-up |
| Rising ACK age | ACK stops updating within threshold | Detect unstable link |
| Prolonged full sync | Sync incomplete for too long | Investigate disk/network/load |
| Primary changed | Master endpoint or node ID changed | Record role change |
| Insufficient standby replicas | Healthy replicas below target | Detect degraded HA |
| Cluster fail | Cluster state unavailable | Service impact |
| Rising Redis errors | Timeouts/`READONLY`/`CLUSTERDOWN` | Application impact |
| Staleness exceeds SLA | Replica read probe version too old | Data inconsistency risk |
| Persistence error | AOF/RDB failures | Durability/recovery risk |

Never apply thresholds like `10 KB` or `2 seconds` as universal rules. Choose them based on write throughput, baselines, replica counts, and RPO/RTO for the use case.

To avoid an **alert storm** during failover, group alerts by replication group/shard and use inhibition or correlation to separate root cause from downstream symptoms.

## 30. Connected Replicas Do Not Equal Valid Failover Candidates

Output:

```text
connected_slaves:2
```

does not prove both replicas can be promoted immediately.

Also check:

- Whether the replica is online and finished syncing.
- Whether lag is high.
- Whether network connectivity to other nodes is intact.
- Whether election/quorum conditions are satisfied.
- Configured replica priority/eligibility.
- Independent failure-domain placement.
- Whether disk, CPU, and memory can handle primary load.

A replica currently running a full resync is in a very different state from an online, caught-up replica.

Monitoring should define an explicit **healthy/eligible replica count** rather than relying solely on `connected_slaves`.

## 31. min-replicas-to-write and Monitoring

Redis provides two settings:

```conf
min-replicas-to-write 1
min-replicas-max-lag 10
```

Purpose: the primary can reject writes if fewer than the required replicas satisfy the lag/ACK criteria checked by Redis.

This reduces the risk of a primary accepting writes without a healthy replication path, trading off write availability when replicas fall short.

However, it **does not prove a just-acknowledged write has arrived or been fsynced on a replica**.

Monitor:

- Number of connected replicas meeting the criteria.
- ACK age.
- Rate of rejected writes.
- Abnormal load and replication link health.
- Application impact when Redis rejects writes.

If the Redis process is alive yet application writes fail, check `min-replicas-*` and replica health before assuming the Redis server is down.

## 32. WAIT and WAITAOF Help Gauge Acknowledgment Progress

Redis provides `WAIT`:

```redis
SET demo:repl "v2"
WAIT 1 2000
```

`WAIT` blocks until the specified number of replicas acknowledge the replication offset of prior writes on **the same client connection**, up to the timeout. It returns the count of replicas that acknowledged, which may be less than requested.

**Remember:** `WAIT` does not mean replicas have fsynced to disk, nor does it guarantee absolute zero data loss across every failover scenario.

On supported Redis versions, `WAITAOF` can wait for AOF fsync acknowledgments:

```redis
SET demo:aof "v2"
WAITAOF 1 1 2000
```

Verify Redis version (introduced in Redis 7.2), AOF configuration, and the meaning of local/replica acknowledgment counts returned by Redis.

Monitoring around these mechanisms can track:

- Commands meeting the requested acknowledgment count.
- Timeout / insufficient-ACK counts.
- Wait latency.
- Local and replica acknowledgment counts.
- Differences across replication groups/shards.

If `SET` runs on one connection and `WAIT` on another without controlling context, you cannot assume you waited for that exact write.

Neither `WAIT` nor `WAITAOF` replaces backups, an authoritative source of truth, or idempotency.

## 33. Persistence Is a Complementary Signal

A replica may have applied a write in RAM while its AOF has not yet fsynced. Therefore monitor:

```bash
redis-cli -h redis-node.internal -p 6379 INFO persistence
```

Typically important fields:

| Field | What to Understand |
| --- | --- |
| `aof_enabled` | Whether AOF is enabled on the node |
| `aof_last_write_status` | Recent AOF write status |
| `aof_last_bgrewrite_status` | Whether recent AOF rewrite succeeded |
| `rdb_last_bgsave_status` | Whether recent RDB background snapshot succeeded |
| `rdb_bgsave_in_progress` | Whether a snapshot is currently running |
| `aof_rewrite_in_progress` | Whether an AOF rewrite is currently running |

Never infer from `replica offset gap=0` that data is durable on disk. Replication ACK and persistence/fsync are separate signals.

If Redis is strictly a cache, persistence can be tuned around warm-up needs. If Redis holds critical state, monitor RDB/AOF, backups, and restore readiness together.

## 34. RPO and RTO: Monitor the Right Things

**RPO** asks "how much data loss is tolerable in an incident?". It does not equal a single offset gap reading.

**RTO** asks "how long after a fault until the service works again?". Measure from the application rather than stopping at Sentinel's promotion event.

Timeline:

```text
t0  primary fails
t1  Sentinel/Cluster detects failure
t2  replica is promoted
t3  client refreshes topology / reconnects
t4  Spring API writes succeed again
```

One operational RTO measure is `t4 - t0`, though exact definitions depend on your organization's service contract.

Post-incident observed RPO can be estimated by recording **sequence IDs** for client-acknowledged writes and checking which ones exist on the new primary.

Offset gap flags risk, but cannot by itself tell you how many business transactions were lost.

## 35. Diagnosing Increasing Replica Lag

Workflow:

1. **Identify the group/shard:** avoid comparing two unrelated data streams.
2. **Inspect `INFO replication`:** primary offset, replica offset, ACK age, link, sync state.
3. **Verify master identity:** did a failover or restart just occur?
4. **Inspect resources:** CPU, memory, network bandwidth/loss, disk I/O, AOF rewrite.
5. **Inspect replication sync:** partial/full resync, backlog, snapshot transfer.
6. **Inspect application workload:** write bursts, large commands, Lua scripts, or hot keys.
7. **Inspect Sentinel/Cluster events:** SDOWN, ODOWN, role changes, node health.
8. **Assess impact:** stale replica reads, write rejections, API latency/fallbacks.
9. **Verify recovery with evidence:** link stable, sync complete, gap back to baseline.
10. **Record the timeline:** for RPO/RTO analysis and configuration review.

Common causes:

| Cause | Possible Symptoms |
| --- | --- |
| Slow/lossy network | Link flapping, rising ACK age |
| Overloaded replica CPU | Slow stream application, growing gap |
| Heavy disk I/O | Snapshot/AOF rewrite, rising latency |
| Large primary write burst | Offset jumps rapidly, replica catches up |
| Full resync | Sync in progress, elevated network/disk |
| Recent failover | Master identity changed, role/offset reset |
| Client reading wrong node | Probe reads unexpectedly stale data |
| Skewed monitoring scrape times | Abnormal or negative offset gap |

Never conclude root cause from a single dashboard tile.

## 36. Diagnosing Repeated Role Flapping

Role flapping:

```text
10:00 primary A -> B
10:03 primary B -> A
10:05 primary A -> B
```

Possible contributors:

- Network partitions, packet loss, or latency spikes.
- Cluster/Sentinel quorum instability.
- Redis process restarts.
- Host overload, GC pauses, or disk stalls.
- Overly aggressive failover thresholds.
- Shared failure domains.
- Client/control-plane views failing to converge.

Correlate logs across multiple Sentinel/Cluster nodes with application error timestamps. Never try to override master roles from an application health check; the control plane must coordinate roles.

Alerts on frequent role changes within a short window should be separated from planned maintenance.

## 37. Scenario: ACK Age Is Low Yet the Replica Is Still Stale

Suppose:

```text
Primary A: slave0.lag=0
Primary A: slave0.offset trails master by 20,000 bytes
Spring GET via replica B: stale value
```

There is no contradiction: `lag=0` reflects ACK age, while offset gap shows the stream had not yet caught up at observation time. Also, the application might be reading from a different node than expected.

Investigate:

1. Check `slave0.offset` and `master_repl_offset`.
2. Confirm `slave0` corresponds to replica B.
3. Read `INFO replication` directly on B.
4. Check Spring read routing.
5. Run a direct staleness probe.
6. Check for an application-level cache outside Redis.

Never use `slave0.lag=0` as proof of read-your-writes consistency.

## 38. Scenario: Offset Gap Is 0 Yet the Link Is Down

A node with no writes for a few minutes:

```text
master offset = 900000
replica offset = 900000
```

If the replication link just dropped, the gap can still be 0 simply because no new writes arrived.

Therefore:

```text
offset_gap=0  +  master_link_status=down
```

must be classified as **replication unhealthy**, not healthy just because the byte difference is 0.

Metrics must track both progress and the ability to continue replicating.

## 39. Scenario: Role Changed Yet Metrics Look Unchanged

Before failover:

```text
Spring -> Redis A
INFO role = master
```

After failover:

```text
Spring -> Redis B
INFO role = master
```

If `currentRole()` only returns `primary`, no node change is observed.

Solution:

- Sentinel: poll `SENTINEL get-master-addr-by-name`.
- Cluster: poll `CLUSTER SHARDS`/`CLUSTER NODES`.
- Record node identity and endpoint.
- Use Sentinel Pub/Sub only as a fast supplementary signal.
- Compare topology snapshots and emit role-change metrics.
- Track replication history/generation to reset offset gap cleanly.

This is why **role label** and **primary identity** must be tracked as two separate fields.

## 40. Scenario: Primary Promoted Yet Application Still Errors

Steps:

1. Sentinel/Cluster announces the new primary.
2. Confirm the new primary's `ROLE` returns master.
3. Verify Spring containers can connect to the new endpoint.
4. Check Redis ACLs, TLS, and hostname verification.
5. Check driver reconnect and topology refresh behavior.
6. Check Redis command timeouts and `READONLY` errors.
7. Run a controlled test write in a test environment or authorized monitoring namespace.
8. Measure elapsed time from the failover event until writes succeed.
9. Verify replicas are following the new primary.
10. If this is a fault test, check RPO against sequence-ID writes.

Sentinel announcing `switch-master` does not mean the entire client fleet has reconnected and resumed writing successfully.

## 41. Redis Cluster: Observe Per Shard, Never Sum Offsets Across the Cluster

Wrong:

```text
max(master_repl_offset across all primaries)
-
min(slave_repl_offset across all replicas)
```

That calculation is meaningless because offsets belong to different streams.

Better:

```text
for each shard:
    identify current primary
    identify its replicas
    verify common replication history
    calculate gap for each replica
    emit per-shard metrics
```

Useful cluster-level rollups:

- Count of shards lacking healthy replicas.
- Count of replicas exceeding lag thresholds.
- Role changes within a time window.
- Slot coverage and cluster state.
- Shards currently in full sync.
- Application error rates by shard when routing is known.

With a hot key on one shard, lag there can diverge sharply from other shards. Cluster-wide averages can hide a failing shard.

## 42. Securing Monitoring

Commands such as:

```text
INFO replication
INFO persistence
ROLE
CLUSTER SHARDS / NODES
SENTINEL master / replicas
```

may require specific Redis ACLs or managed service permissions.

Principles:

- Separate monitoring credentials from application write credentials if infrastructure supports it.
- Grant read-only permissions; never grant failover privileges just to scrape metrics.
- Enforce TLS, CA, and hostname verification as required.
- Never write passwords into logs or metric labels.
- Never expose Actuator or Prometheus endpoints publicly if they reveal sensitive system details.
- Never let a health check issue `REPLICAOF NO ONE` or `CLUSTER FAILOVER`.
- On managed Redis, use provider-supported APIs/metrics when `CONFIG`/`INFO` are restricted.

Monitoring must never become a privileged path that can accidentally mutate topology.

## 43. Lab A: Reading INFO replication

Given:

```text
master_repl_offset:7000000
slave0:state=online,offset=6998000,lag=0
slave1:state=online,offset=6980000,lag=2
```

Tasks:

1. Compute the byte gaps.
2. Explain why `lag=0` does not mean 0 ms data staleness.
3. Identify which fields to inspect on the replicas themselves.
4. Explain why byte gap cannot be converted to seconds using a fixed constant.
5. State the conditions required for offset comparisons to be valid.

## 44. Lab B: Sentinel Failover

Before:

```text
mymaster -> Redis A
Replicas B/C follow A
```

After:

```text
mymaster -> Redis B
Redis C follows B
```

Design monitoring:

1. Poll master address from multiple Sentinels.
2. Subscribe to `+switch-master` as an extra fast signal.
3. Cross-check `ROLE`/`INFO replication` on nodes.
4. Record timeline of application errors and reconnects.
5. Measure time until writes succeed on the new primary.
6. Verify sequence writes acknowledged prior to failover.
7. Explain why the role string stays `master` even though the node changed.

## 45. Lab C: Redis Cluster

You have three primaries A/B/C, each with one replica. Primary B fails, and B1 is promoted.

Tasks:

1. Use `CLUSTER SHARDS` to identify updated slot ownership.
2. Track role and node ID before and after.
3. Compute replication gap **within shard B**.
4. Explain why you cannot compare A's offset against B1's.
5. Observe application `MOVED`, `READONLY`, and timeout errors.
6. Measure RTO along the business write path.

## 46. Lab D: Heartbeat Staleness Probe

Design a probe:

1. Every 5 seconds, write an incrementing sequence to a shard's dedicated monitoring key.
2. Read directly from the target replica.
3. Record observed sequence and delay.
4. Avoid `REPLICA_PREFERRED` if the client could fall back to the master.
5. When the master node or replication generation changes, rebaseline.
6. Set appropriate TTL, key namespace, and rate limits.
7. Analyze why probing a single key does not represent every key.

The 5-second interval is an exercise example; production workloads should choose a frequency suited to their needs.

## 47. Lab E: Fault Test with Sequence Writes

An isolated test scenario:

1. Spin up an eligible primary and replica.
2. Write sequence IDs and record client-side `OK` results.
3. Capture offsets and link state.
4. Trigger a controlled primary failure.
5. Observe promotion and client reconnection.
6. Check which sequence IDs exist on the new primary.
7. Record any write loss and actual downtime.
8. Correlate metrics scraped across the incident window.
9. Repeat with `WAIT` or different policies and compare carefully.
10. Never conclude zero-data-loss guarantees from a single passing test.

Never run fault tests or role-change commands on production Redis without approved operational procedures.

## 48. Common Misconceptions

**"`slaveN.lag=0` means the replica has zero millisecond delay."** No. It reflects ACK age, not the staleness of every application record.

**"Offset gap is measured in seconds."** No. It is a byte difference in the replication stream under matching observation conditions.

**"Link up means caught up."** No. A replica can still lag or be running a full sync.

**"A gap of 0 proves writes cannot be lost."** No. It is only a point-in-time snapshot.

**"Having 2 connected replicas means 2 healthy failover candidates."** Not automatically. Check lag, sync state, election rules, and failure domains.

**"`WAIT 1` means data is 100% durable."** No. It only waits for replication acknowledgment within that command's scope.

**"Spring `INFO role=master` before and after means no failover occurred."** No. The master endpoint may have moved.

**"Sentinel events are always received by monitors."** No. Pub/Sub events can be missed while a subscriber is offline.

**"Cluster has one shared primary so compute one cluster-wide gap."** No. A cluster contains multiple shards and independent replication streams.

**"Every exporter uses the exact same lag metric name."** No. Verify exporter metric names and semantics.

**"A successful `PING` means the system has recovered."** No. Verify application writes and stabilized topology/replication.

**"Monitoring by itself prevents data loss."** No. Monitoring only observes; durability requires persistence, backups, choosing the right source of truth, and proper client policies.

**"The application should promote a replica itself when `ROLE` looks wrong."** No. Sentinel/Cluster coordinate failover; monitors only observe.

## 49. Frequently Asked Questions

**How should Redis replication lag be measured?**

At minimum track offset gap (bytes), ACK age (seconds), replication link/sync state, and—when business data freshness matters—a heartbeat/version probe.

**Should I use `INFO replication` or `ROLE`?**

Both help. `ROLE` confirms the role of the currently connected node; `INFO replication` provides richer link, offset, and sync metrics.

**Do I need to query every Redis data node?**

For complete topology monitoring, yes. A standard `StringRedisTemplate` does not return metrics across all replicas and shards.

**How do I detect when Sentinel switches masters?**

Compare addresses returned by `SENTINEL get-master-addr-by-name` across polls, paired with `+switch-master` Pub/Sub events as a fast signal.

**Does Redis Cluster emit Sentinel events?**

No. Redis Cluster uses its own role coordination protocol; monitor via Cluster topology and role commands.

**Is it abnormal for a replica read to return stale data when offset gap is small?**

Not necessarily. Asynchronous replication, measurement timing, and read routing can produce stale reads; verify the read path and probe directly.

**Should ACK age serve as a stale-read SLA?**

Not directly. ACK age does not measure record-level staleness. Use a freshness probe or an appropriate consistency contract.

**Can RPO be computed directly from byte gaps?**

Not accurately in terms of business transactions. Combine replication history, fault testing, and tracking client-acknowledged sequence writes.

**Should RTO be measured from Sentinel `switch-master` or from the application?**

To reflect user experience, measure from fault onset until application requests and writes succeed again; the Sentinel event is only one milestone.

**Does `WAITAOF` replace replication metrics?**

No. It confirms fsync progress within a command's scope on supported versions; you still need to monitor nodes, links, offsets, topology, and errors.

**Do we still need to monitor AOF/RDB if replicas exist?**

Yes, if durability or recovery objectives require it. Replication ACK does not equal fsync, and replication is not a backup.

## 50. Summary

To observe replication lag and server role changes in Spring Data Redis effectively:

1. **Distinguish three kinds of lag:** offset gap, ACK age, and application-visible staleness.
2. **Collect from every data node:** `INFO replication`, `ROLE`, link status, sync state, and offsets.
3. **Track master identity:** Sentinel master endpoint or Redis Cluster node ID and slot owner, not just the role string.
4. **Reset/rebaseline after failover:** never compare offsets across different replication histories as one continuous timeline.
5. **Observe at the Spring layer:** timeouts, `READONLY`, redirects, reconnects, latency, and when writes recover.
6. **Build context-aware alerts:** separate high lag, broken links, missing replicas, role flapping, and API impact.
7. **Never confuse monitoring with durability:** asynchronous replication and failover can still cause stale reads or write loss even if the previous scrape showed low lag.
8. **Test failures deliberately:** use sequence writes, real topologies, and measure application-visible RPO/RTO in isolated environments.

By tracking replication progress, control-plane role transitions, and real Spring client behavior together, teams catch issues earlier, diagnose incidents accurately, and design sound recovery policies.

## References

- [Redis – Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis – INFO](https://redis.io/docs/latest/commands/info/)
- [Redis – ROLE](https://redis.io/docs/latest/commands/role/)
- [Redis – Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/)
- [Redis – SENTINEL commands](https://redis.io/docs/latest/commands/sentinel/)
- [Redis – Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Redis – CLUSTER NODES](https://redis.io/docs/latest/commands/cluster-nodes/)
- [Redis – CLUSTER SHARDS](https://redis.io/docs/latest/commands/cluster-shards/)
- [Redis – WAIT](https://redis.io/docs/latest/commands/wait/)
- [Redis – WAITAOF](https://redis.io/docs/latest/commands/waitaof/)
- [Redis – Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Spring Data Redis – Connection Modes](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html)
- [Spring Data Redis – Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Boot – Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
