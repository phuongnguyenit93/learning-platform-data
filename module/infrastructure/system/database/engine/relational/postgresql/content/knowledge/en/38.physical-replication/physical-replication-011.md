# Cascading Replication and Load Distribution

PostgreSQL physical streaming replication is typically described with a primary sending WAL directly to one or more standbys. As standby count, geographic distance, or read traffic distribution grows, a single primary may end up serving too many replication connections and sending WAL across the same network path. **Cascading replication** allows a standby to forward WAL it has already received to other standbys, forming a tree topology. This distributes WAL connections and bandwidth while letting you place read replicas close to application groups or regions that read data.

Cascading replication and read load distribution are related, yet they are two distinct tasks. Cascading replication distributes the **WAL stream** across servers. Distributing **`SELECT` queries** requires application routing, a connection proxy, or suitable middleware; PostgreSQL does not automatically split read queries across standbys simply because they exist. A standby can act purely as a WAL relay, serve read-only queries, or do both depending on configuration and capacity.

A multi-tier topology introduces additional trade-offs: each hop can increase replay lag, upstream standbys become dependencies for downstream nodes, slots can retain WAL and fill disks, long queries on hot standbys can conflict with WAL replay, and failover requires deliberate reparenting and fencing. A sound design addresses WAL flow, query flow, failure domains, consistency requirements, and per-node operations.

This lesson belongs to the **Physical Replication** chapter of the *Database Engine Relational PostgreSQL* module. It focuses on cascading physical streaming replication, distributing read workloads across hot standbys, observing lag/conflicts, managing WAL retention, and troubleshooting topology issues.

## 1. Learning objectives

After this lesson, you will be able to:

- Explain cascading replication and the role of a relay standby.
- Diagram a primary → standby → downstream standbys topology.
- Distinguish WAL fan-out from read query load balancing.
- Identify which node sends WAL and which receives WAL at each hop.
- Configure the parameters and privileges required for physical streaming replication.
- Understand the roles of `primary_conninfo`, `application_name`, replication slots, and WAL retention.
- Estimate required sender connections and capacity on each node.
- Monitor write/flush/replay lag and understand the limits of statistics views.
- Distribute read traffic based on lag, latency, capacity, and consistency requirements.
- Handle hot standby conflicts, `hot_standby_feedback`, and long queries.
- Design failover, reparenting, fencing, and downstream node rebuilds.
- Evaluate synchronous/asynchronous replication per hop.
- Practice configuring and observing a cascading topology in a lab.

## 2. How does physical streaming replication work?

PostgreSQL writes recoverable changes to the Write-Ahead Log (WAL). A physical standby receives WAL records, stores them in WAL files, and replays them to reconstruct the same data state as its upstream.

~~~text
Application writes
       |
       v
Primary PostgreSQL
       |
       | WAL sender / replication protocol
       v
Standby PostgreSQL
       |
       +--> WAL receiver writes WAL
       |
       +--> Startup process replays WAL
~~~

### 2.1. WAL sender

On the sending node, a WAL sender backend serves the replication connection and sends WAL to the client. A primary can have multiple WAL senders, depending on `max_wal_senders` and connection demand.

### 2.2. WAL receiver

On the standby, the WAL receiver connects to its upstream via `primary_conninfo`, receives WAL, and writes it to local WAL storage. It reports receive/replay progress via the replication protocol.

### 2.3. Replay process

The startup process replays WAL to update data pages and catalogs. Received (written/flushed) WAL may not yet be replayed; therefore receive position and replay position are two distinct signals.

### 2.4. Read-only standby

When hot standby is enabled and recovery state permits, clients can connect to run read-only queries while WAL continues replaying. Standard DML cannot execute on a hot standby.

### 2.5. Physical replication is a block-level stream

Physical streaming replication transmits WAL to maintain physical cluster state, not a stream of logical SQL statements. It has different version/architecture compatibility requirements from logical replication.

## 3. What is cascading replication?

In cascading replication, a standby receives WAL from its upstream and acts as a WAL sender for one or more downstream standbys.

~~~text
                  +------------------+
                  | Primary P        |
                  +--------+---------+
                           |
                         WAL
                           |
                  +--------v---------+
                  | Standby A        |
                  | receiver + sender|
                  +---+-----------+--+
                      |           |
                    WAL         WAL
                      |           |
              +-------v--+    +---v----------+
              | Standby B|    | Standby C    |
              +----------+    +--------------+
~~~

### 3.1. A standby both receives and sends WAL

Standby A runs a WAL receiver to receive from P and WAL senders to serve B/C. It relays WAL that it has already received and stored locally.

### 3.2. Downstream connects to the nearest upstream

Standby B configures `primary_conninfo` pointing to A instead of P. Similarly, C connects to A.

### 3.3. The primary does not send directly to every standby

If P sends only to A, A distributes WAL to B and C. This reduces direct connections and network fan-out on P, while A takes on additional sender/network/disk workload.

### 3.4. Cascading does not automatically create query routing

B and C only receive WAL along the topology. For applications to read from B/C, you must configure routers/proxies or application logic.

### 3.5. Cascading is not multi-primary

Physical standbys remain read-only replicas in recovery. Writes execute on the designated primary; there is no mechanism to merge independent writes from multiple nodes.

## 4. Tree topology and hops

A physical standby normally has one upstream for WAL streaming at a time. A cascading topology is therefore modeled as a tree with a single authoritative root.

~~~text
                         P
                    /    |    \
                   A     D     E
                 /   \
                B     C
               /
              F
~~~

### 4.1. Direct standbys

A, D, and E connect directly to P. They are direct downstreams of P.

### 4.2. Cascaded standbys

B/C connect to A; F connects to B. They do not maintain direct replication connections to P in this topology.

### 4.3. Each hop has its own receive and replay progress

B may receive WAL from A quickly yet replay slowly. A may receive WAL from P quickly yet send to B slowly. Monitor each hop to locate where lag arises.

### 4.4. Avoid cycles

A valid topology must never loop WAL back to an upstream node. Never create cycles such as P→A→B→P.

### 4.5. A node can serve multiple downstreams

The number of downstreams depends on `max_wal_senders`, connection budgets, network bandwidth, CPU, and WAL read performance on the sender. No single number fits every system.

## 5. Why use cascading replication?

Cascading is useful when distributing WAL delivery, placing replicas near read workloads, or organizing topologies by region/rack.

### 5.1. Reduce connection fan-out on the primary

The primary can send WAL to a few relay standbys instead of directly serving dozens or hundreds of replicas.

### 5.2. Geographic WAL distribution

A standby in a regional hub can receive WAL from the primary and relay it to replicas in the same region or private network.

### 5.3. Reduce egress/network pressure

The primary may need to send only one stream to a relay. The relay handles fan-out; total bytes still cross the network, while load shifts to another tier.

### 5.4. Grouping read replicas

A relay near an analytics cluster can feed WAL to multiple read replicas for that group, while another relay serves applications in a different region.

### 5.5. Topology scalability

As replica counts grow, a replication tree clarifies connections and failure domains. In return, relays become dependencies for their descendants.

## 6. Limitations of cascading

Cascading does not eliminate replication cost; it shifts where the cost lands.

### 6.1. Adding a hop can increase lag

WAL must be received from P, written on A, then sent to B and replayed. Each stage adds queue, network, and disk latency.

### 6.2. Relays can become bottlenecks

A replays WAL while sending to multiple downstreams, and may also serve `SELECT` queries. CPU, disk I/O, and network can contend.

### 6.3. Upstream relays are dependencies

If A goes down, B/C lose their WAL source until reparented or A recovers. Primary P may stay healthy while descendants fall behind.

### 6.4. WAL retention becomes more complex

Every upstream must retain WAL long enough for downstreams to reconnect. Unmanaged slots can retain excessive WAL and fill disks.

### 6.5. Does not protect against logical corruption

If P executes a mistaken business transaction, cascading tiers receive and replay that change too. Backups/PITR remain essential.

## 7. Cascading replication and read load balancing

These two goals are often deployed together yet must be designed separately.

| Aspect | Cascading replication | Read load balancing |
|---|---|---|
| What is distributed? | WAL stream | SQL read queries |
| Core components | WAL sender/receiver, standbys | App router, proxy, pooler |
| Goal | Scale WAL fan-out | Split read load |
| Measurement | Receive/replay LSN, sender state | Query latency, QPS, CPU, cache hit |
| Failure mode | Upstream relay disconnects | Router picks unhealthy/lagging replica |
| Consistency | WAL replay order | Queries may read stale state |

### 7.1. A standby can act purely as a relay

Node A may accept no application queries, solely relaying WAL to B/C. Capacity should then prioritize WAL receiving, replaying, and sending.

### 7.2. A standby can both relay and serve reads

Node A may sit in a read pool, though query load can compete with WAL senders/receivers and replay.

### 7.3. Downstreams can serve isolated read groups

B/C can sit close to application regions with their own connection policies and capacity. They typically exhibit higher lag than direct upstreams.

### 7.4. Never route writes to a hot standby

Writes must go to the primary. If a proxy sends DML to a standby, PostgreSQL rejects it due to recovery/read-only state.

### 7.5. Never blindly route every SELECT to a replica

Queries needing read-after-write, transaction consistency, or the latest data may need to read from the primary or wait for a replica to replay up to a target LSN.

## 8. Role of each node

Before configuring, document each node's role and owner.

| Node | Role | Upstream | Downstream | App reads |
|---|---|---|---|---|
| P | Primary | — | A, D | Main reads/writes |
| A | Relay + optional read | P | B, C | Capacity-dependent |
| B | Read replica | A | F | Read group B |
| C | Read replica | A | — | Read group C |
| D | Direct standby | P | — | DR/read group D |

### 8.1. Primary

Handles writes, generates WAL, and serves direct replication clients.

### 8.2. Relay standby

Receives/replays WAL, serves downstream sender connections, and optionally serves read-only workloads if capacity permits.

### 8.3. Leaf standby

Receives WAL from a relay and typically serves query traffic for a specific application group/region.

### 8.4. DR standby

May sit in a separate topology to support failover or DR. Never let routed read workloads starve capacity needed for recovery.

### 8.5. Roles must be recorded in inventory

Hostnames alone do not describe topology. Document upstream, downstream, region, purpose, slots, connection budgets, and failover owners.

## 9. Baseline parameters on the primary

Exact configuration depends on PostgreSQL version and load. Commonly reviewed settings include:

~~~conf
wal_level = replica
max_wal_senders = 16
max_replication_slots = 16
wal_keep_size = '2GB'
~~~

These are illustrative values, not tuning recommendations.

### 9.1. wal_level

`replica` provides WAL needed for physical replication and archive recovery. `logical` adds information for logical decoding at its own overhead; it is unnecessary solely for cascading physical replication.

### 9.2. max_wal_senders

Size for direct standbys, cascading relays, backup tools, and other replication connections, plus headroom for reconnects/failover.

### 9.3. max_replication_slots

Size slots for consumers requiring WAL retention. Slots can pin WAL when downstreams disconnect; capacity planning must account for retention risks.

### 9.4. wal_keep_size

Keeps a minimum amount of WAL so standbys can reconnect after brief interruptions. It is not an absolute retention cap and does not replace slots/archives in all topologies.

### 9.5. Restart or reload?

Parameters such as `wal_level`, `max_wal_senders`, and `max_replication_slots` require a restart depending on context/version. Check `pg_settings.context` and `pending_restart` before changes.

## 10. Configuring a relay standby to send WAL

A relay standby must receive WAL from upstream and serve replication connections to downstream nodes.

~~~conf
# On the relay standby
hot_standby = on
max_wal_senders = 8
max_replication_slots = 8
wal_keep_size = '2GB'
~~~

### 10.1. max_wal_senders on the standby

The relay node also runs WAL sender processes for downstreams. Do not configure `max_wal_senders` only on the primary.

### 10.2. hot_standby

Enable `hot_standby` if the node needs to serve read-only queries during recovery. Verify query access, WAL relay behavior, and downstream replication support for your exact version/configuration.

### 10.3. max_replication_slots on the relay

If downstreams use physical replication slots on the relay, provision enough slot capacity on the relay and manage retention on that node.

### 10.4. Local disk

The relay needs enough WAL storage to replay and retain segments for downstreams. WAL retention on the relay can differ from retention on the primary.

### 10.5. Resource isolation

If the relay also serves reads, configure connection limits, workload priorities, and monitoring so read spikes do not delay WAL distribution.

## 11. Configuring a downstream standby

Downstreams point to the relay via `primary_conninfo`, not necessarily to the root primary.

~~~conf
primary_conninfo = 'host=standby-a.example.internal port=5432 user=replicator application_name=standby-b sslmode=verify-full'
primary_slot_name = 'standby_b_slot'
~~~

Hostnames, roles, certificates, and slot names are illustrative only.

### 11.1. primary_conninfo

Specifies the upstream replication server, user, and connection parameters. Store passwords in appropriate secret/permission mechanisms instead of hardcoding plaintext in shared files.

### 11.2. application_name

This name appears in the upstream's replication statistics, helping identify downstreams and cross-reference topology inventory.

### 11.3. primary_slot_name

If using a replication slot, the standby asks the upstream to retain WAL for that slot. The slot must exist on that exact upstream node and be monitored.

### 11.4. standby.signal

On PostgreSQL 12+, `standby.signal` marks the data directory to run in standby mode. Physical backup/restore tooling can generate this file or equivalent config.

### 11.5. restore_command

You can configure `restore_command` to fetch WAL from an archive when streaming lacks a needed segment or during archive-based recovery. Ensure the archive chain and timeline match.

## 12. Replication roles and pg_hba.conf

Each sender must permit downstream replication connections. With cascading, configuring permissions on relays is just as critical as on the primary.

### 12.1. Creating the replication role

~~~sql
CREATE ROLE replicator
WITH LOGIN REPLICATION PASSWORD 'use-a-secret-manager';
~~~

Example is for lab use only; production should use secret management, TLS, and a rotation policy.

### 12.2. pg_hba.conf on the primary

~~~conf
hostssl replication replicator 10.20.0.0/16 scram-sha-256
~~~

### 12.3. pg_hba.conf on the relay

The relay also needs a rule for the downstream subnet/hosts:

~~~conf
hostssl replication replicator 10.30.0.0/16 scram-sha-256
~~~

### 12.4. Restrict source addresses

Allow only expected downstream nodes. Avoid overly broad rules like the entire Internet or all IPv4 addresses.

### 12.5. Reload and verify

After editing HBA, reload configuration and test connections. Use `pg_hba_file_rules` to catch parse errors when available.

## 13. Physical replication slots and WAL retention

A replication slot tells an upstream from which position a consumer still needs WAL. In a cascading topology, track which node owns each slot and protect that node's filesystem.

### 13.1. Slots belong to the direct upstream

If B connects to A, B's slot (if used) is managed on A. It does not automatically exist as a slot on P.

### 13.2. Slots prevent premature WAL recycling

When B disconnects, the slot retains WAL on A until B returns or the slot is handled. This avoids rebuilding the standby after brief outages.

### 13.3. Slots can fill disks

If a consumer stays disconnected long, retained WAL grows continuously. Monitor `pg_replication_slots`, `pg_wal` disk usage, and version-appropriate retention limits.

### 13.4. max_slot_wal_keep_size

This parameter caps WAL retained by replication slots on supported versions. Once exceeded, the slot may lose streaming continuity and the standby must recover WAL from an archive or be reseeded.

### 13.5. Slots do not replace archives

Slots serve a specific consumer on its upstream; an independent WAL archive provides a recovery path and supports rebuilds. Maintain both when durability/DR demands it.

## 14. WAL retention across multiple tiers

Each hop has its own retention boundary.

~~~text
P --slot A--> A --slot B--> B
                     |
                     +--slot C--> C
~~~

### 14.1. P retains WAL for A

If A disconnects, slot A on P retains WAL that A has not yet received.

### 14.2. A retains WAL for B/C

A must retain segments needed by B/C. Slots B and C live on A and can cause A's WAL usage to grow.

### 14.3. Retention does not simply add across tiers

Each node maintains its own WAL generation/retention state. Disk planning must measure WAL volume and outage windows on every sender.

### 14.4. Archives can bridge certain gaps

If a downstream has `restore_command` and a complete archive, it can fetch segments from the archive when its streaming upstream no longer retains them, subject to timeline/recovery config.

### 14.5. Monitor inactive slots

Long-inactive slots need owners and expiry/recovery plans. Never drop a slot just to free disk without confirming the consumer and rebuild path.

## 15. max_wal_senders and connection budgeting

Each sender caps concurrent replication connections. Cascading distributes connections across nodes without eliminating total connection load.

### 15.1. Budget per sender

With topology P→A,D,E and A→B,C, P needs sender slots for A/D/E; A needs slots for B/C, plus backup/maintenance connections.

### 15.2. Reserve headroom for reconnect/failover

Keep headroom for standby reconnects, `pg_basebackup`, and rebuilds. If `max_wal_senders` matches steady-state clients exactly, failover may run out of slots.

### 15.3. max_connections does not replace max_wal_senders

Replication connections are bounded by their own settings. Increasing `max_connections` does not solve exhausted WAL sender slots.

### 15.4. Each node needs its own budget

Relays carry app read sessions, background jobs, and replication senders. Budget `max_connections`, pool sizes, WAL senders, workers, and OS limits together.

### 15.5. Never raise limits unboundedly

Every process/connection consumes memory, file descriptors, and CPU. Measure peak concurrency before raising limits.

## 16. Monitoring on the primary and relays

`pg_stat_replication` shows WAL sender connections directly attached to the queried node. On P, it shows A/D/E; on A, it shows B/C.

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
~~~

### 16.1. One node's view does not show the whole tree

Querying P will not list B/C if they connect to A. To observe B/C, query `pg_stat_replication` on A or aggregate metrics from every node.

### 16.2. sent_lsn

WAL position sent to the client per view/state. Pair with write/flush/replay positions to isolate which stage lags.

### 16.3. write_lsn and flush_lsn

Distinguish WAL received/written from WAL durably flushed on the standby per reported status.

### 16.4. replay_lsn

Reports WAL replay progress. Read queries on the standby see state up to the replay position, not merely the receive position.

### 16.5. Lag intervals can be NULL

Lag time columns are estimates and may be NULL when idle or lacking recent samples. Supplement with LSN deltas, timestamps, and application metrics.

## 17. Monitoring on the standby receiver

On a standby, `pg_stat_wal_receiver` describes the active receiver connection.

~~~sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    received_tli,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time,
    slot_name,
    sender_host,
    sender_port
FROM pg_stat_wal_receiver;
~~~

### 17.1. sender_host

Confirms the standby receives WAL from the intended upstream. Useful evidence after reparenting.

### 17.2. written and flushed positions

Distinguishes WAL written to local buffers/files from flushed WAL. Cross-check with sender-side stats when diagnosing network/disk lag.

### 17.3. last message times

If message receipt time grows stale, inspect upstream availability, network, authentication, timeouts, and receiver logs.

### 17.4. slot_name

Confirms which slot is used if any. If NULL, the standby is not using a slot and relies on `wal_keep_size`/archive retention.

### 17.5. One snapshot is not enough

Collect time-series samples to separate transient pauses from growing backlogs.

## 18. Measuring lag by LSN

Byte lag can be approximated as the difference between upstream current WAL LSN and downstream replay LSN.

~~~sql
-- On upstream
SELECT pg_current_wal_lsn() AS current_lsn;

-- On standby
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn;
~~~

### 18.1. Receive lag

Compare upstream send/current position with receive position to assess the network/receiver path.

### 18.2. Replay lag

Compare receive position with replay position to assess the apply backlog. If receive is fast while replay lags, investigate CPU, disk, conflicts, or replay load.

### 18.3. LSN difference

`pg_wal_lsn_diff(lsn1, lsn2)` returns the byte distance between two LSNs. Comparisons are valid only within the same replication timeline/stream.

### 18.4. Byte lag does not equal time lag

At high write rates, 1 GB of WAL may represent seconds; at low write rates, the same 1 GB may represent hours. Pair with WAL generation rates and timestamps.

### 18.5. Cumulative lag across cascades

If P→A lags 2 seconds and A→B lags 3 seconds, B may trail P by roughly 5 seconds or vary depending on timing/queues; never treat summed discrete snapshots as an exact measurement.

## 19. Monitoring topology across multiple nodes

Because views are local, collect state from each node and assemble a topology inventory.

### 19.1. Static inventory

Record node ID, role, upstream host, downstream list, region, availability zone, replication slot, `application_name`, and owner.

### 19.2. Dynamic inventory

Poll sender/receiver state from each node and confirm live connections match the expected topology.

### 19.3. Detect reparenting

After failover, `sender_host` on receivers may change. Alert if an upstream falls outside the approved topology.

### 19.4. Correlate LSNs

Capture current/replay LSNs and timestamps for each hop at aligned sample times. Use UTC for cross-region comparisons.

### 19.5. TCP connectivity alone does not mean a healthy node

Replication protocol, WAL availability, timeline compatibility, and replay progress prove the stream actually works.

## 20. Capacity planning for relay nodes

A relay is an intermediary that can handle WAL receive, replay, WAL send, and read workloads simultaneously.

### 20.1. Network ingress

A receives WAL from P. Ingress must keep pace with P's peak WAL generation, plus bursts and reconnect catch-up.

### 20.2. Network egress

A sends WAL to B/C. Total egress scales with downstream count and how streams are transmitted.

### 20.3. Disk I/O

A writes received WAL, replays data pages, and reads WAL to send downstream. High disk latency impacts both replay and sender throughput.

### 20.4. CPU

WAL processing, checksums, encryption, transport/tooling compression, and read queries all consume CPU.

### 20.5. Headroom and isolation

Never allocate 100% of capacity to read traffic. Reserve headroom for WAL replay, post-outage catch-up, and backup operations.

## 21. Distributing read traffic across hot standbys

Hot standbys can serve `SELECT` queries to offload the primary, yet read routing must respect lag and query semantics.

### 21.1. Application-level routing

Applications can maintain two connection pools: a write pool targeting the primary and a read pool targeting selected replicas. This allows per-endpoint consistency decisions.

### 21.2. Proxies or middleware

A proxy can health-check replicas and distribute connections/queries by policy. Check whether the proxy understands transaction boundaries and read/write classification or routes only at connection level.

### 21.3. PgBouncer

PgBouncer focuses on connection pooling. PgBouncer itself does not automatically parse arbitrary SQL to split `SELECT` to replicas and writes to the primary; database/user routing or app logic is usually needed.

### 21.4. Pgpool-II and query routing

Middleware like Pgpool-II supports configurable read load balancing. Understand behavior with transactions, prepared statements, temp tables, functions, and session state.

### 21.5. Do not treat every SELECT as safe to route

A `SELECT` may call functions with side effects/volatile behavior, rely on transaction state, or require read-your-writes. Route according to actual application semantics.

## 22. Read-after-write consistency

When an app writes to the primary and immediately reads from a standby, the standby may not have replayed that commit yet.

### 22.1. Eventual consistency

Read replicas normally reflect data after a delay. Applications must tolerate stale reads for appropriate use cases.

### 22.2. Read-your-writes

After a write, requests needing fresh data can stick to the primary for a window or wait until the standby replays the transaction's LSN.

### 22.3. LSN tokens

Applications can capture a post-commit LSN on the primary and pass a consistency requirement to the router. The router waits until a replica replays up to/past that LSN or falls back to the primary.

### 22.4. Transaction consistency

Never split statements of one transaction across multiple servers. A transaction requires one consistent database session and transaction context.

### 22.5. Monotonic reads

If a user routes across replicas with differing lag, they may see newer data followed by older data. Sticky routing or LSN-aware selection prevents this.

## 23. Selecting a replica per query

Replica selection can factor in health, lag, latency, capacity, and region.

### 23.1. Health

The replica must accept connections, be in recovery, not overloaded, and have an active WAL receiver per policy.

### 23.2. Lag thresholds

Exclude replicas whose replay lag exceeds the use case's limit. Avoid one global threshold for every endpoint.

### 23.3. Query latency

A nearby replica has low network latency yet may lack CPU/cache. Measure end-to-end query latency rather than ping alone.

### 23.4. Weighted routing

Assign weights by CPU/memory/storage capacity and max connections. Recompute weights when a node degrades.

### 23.5. Fallback

If all read replicas fail freshness or health checks, the router needs a policy: fall back to the primary, return an error/retry, or serve stale data. Business semantics decide.


## 24. Hot standby conflicts with WAL replay

Read queries on a standby can hold snapshots or locks while recovery needs to apply WAL. When they clash, PostgreSQL chooses between keeping queries running and advancing replay.

### 24.1. Cleanup conflicts

Upstream `VACUUM` can clean up tuple versions that a long standby query still needs to read. When the WAL record replays, the standby may have to cancel the query to apply the change.

### 24.2. Lock conflicts

Upstream DDL or lock records can conflict with existing queries/locks on the standby. Recovery can wait within configured limits before canceling queries.

### 24.3. Buffer pin conflicts

A query holding a buffer pin long can stall recovery needing to modify that page.

### 24.4. Monitoring conflict counters

~~~sql
SELECT
    datname,
    confl_tablespace,
    confl_lock,
    confl_snapshot,
    confl_bufferpin,
    confl_deadlock
FROM pg_stat_database_conflicts
ORDER BY datname;
~~~

Counters report queries canceled due to recovery conflicts per database, not all query errors.

### 24.5. Trade-off between freshness and query continuity

Delaying recovery too long increases standby lag. Canceling queries frequently destabilizes read workloads. Choose policies per use case and measure both.

## 25. max_standby_streaming_delay and max_standby_archive_delay

These parameters control how long recovery waits when WAL replay conflicts with standby queries.

### 25.1. max_standby_streaming_delay

Limits total replay delay for conflicts with WAL received via streaming in the processing window. It is not an individual per-query runtime limit.

### 25.2. max_standby_archive_delay

Controls wait time when replaying archived WAL hits conflicts. Archive recovery can behave differently from streaming.

### 25.3. Low values

Recovery prioritizes advancing quickly; long queries may be canceled sooner. Fits when freshness/replication lag matters more than read query continuity.

### 25.4. High values

Gives queries more time to finish while increasing replay lag. If downstreams keep receiving WAL, backlogs can grow.

### 25.5. Do not set indefinite delays casually

An analytics query can run for hours. Letting recovery wait indefinitely can leave the standby too stale for failover or read consistency.

## 26. hot_standby_feedback and upstream bloat

`hot_standby_feedback` lets a standby send snapshot horizon info upstream to reduce cleanup conflicts.

### 26.1. Goal

The upstream can retain tuple versions standby queries still need, reducing query cancellations from cleanup conflicts.

### 26.2. Trade-off

Retaining dead tuples longer can increase bloat on the upstream. A long query on a standby can affect vacuum cleanup on the sending node.

### 26.3. In cascading topologies

Feedback and cleanup horizons must be understood per replication hop and PostgreSQL version. Never assume enabling it on a leaf automatically propagates identical semantics all the way to the primary in every topology.

### 26.4. Monitoring the xmin horizon

Inspect `backend_xmin`, replication slot `xmin`, and vacuum progress on upstream nodes. Locate sessions/standbys holding old snapshots.

### 26.5. Choose by workload

Read replicas serving short queries may not need feedback. Replicas serving long analytics may need a different policy, or workload isolation onto a dedicated replica to bound impact.

## 27. Delayed standbys and cascading

A standby can intentionally delay replay to create a window for detecting certain logical mistakes.

### 27.1. recovery_min_apply_delay

`recovery_min_apply_delay` instructs the standby to wait a period before replaying commit records per PostgreSQL semantics. It is not a full historical backup.

### 27.2. Used as a detection window

If an accidental `DROP` hits the primary, a delayed standby may not apply it immediately. Operators gain time to detect and halt/investigate per runbook.

### 27.3. Does not protect against all corruption

Mistakes discovered after the delay window have already replayed. Delayed standbys do not replace base backups, WAL archives, and PITR.

### 27.4. Impact on downstreams

If a delayed standby serves as upstream for downstream nodes, downstreams also receive state from a replay-delayed relay. Lag compounds across tiers.

### 27.5. Never use a delayed replica for strict read freshness

An intentionally delayed node does not fit endpoints requiring fresh data. Isolate it or reserve it for recovery/forensic purposes.

## 28. Synchronous and asynchronous replication across hops

Streaming replication defaults to asynchronous. Synchronous replication can be configured so a sender waits for acknowledgements from synchronous standbys per connection semantics.

### 28.1. Async replication

The primary does not wait for standbys to flush/apply WAL before returning commit under async policy. This lowers commit latency while risking loss of untransmitted transactions upon primary failure.

### 28.2. Sync replication

The primary can wait for remote acknowledgement per `synchronous_commit` and `synchronous_standby_names`. The chosen wait level (`remote_write`, flush, or apply) affects durability and latency.

### 28.3. Each hop has its own acknowledgement semantics

In P→A→B, P waiting for A does not automatically prove B replayed the transaction. If multi-tier durability is needed, design and verify synchronous relationships/acknowledgements at each hop.

### 28.4. Cascading does not automatically create end-to-end synchronous guarantees

Never infer zero RPO across the entire tree from a synchronous setting on the primary alone. Verify which node is selected as synchronous standby, acknowledgement level, and protected failure domains.

### 28.5. Network partitions and availability

If the primary requires a synchronous standby and standbys/networks stop responding, writes wait per configuration. Define quorum/failover policies and business decisions for this availability trade-off.

## 29. Relay standby failover

If relay A fails, downstreams B/C lose their WAL source even while primary P stays healthy.

### 29.1. Detecting failure

Monitor receiver/sender health, heartbeats, replay lag, disks, host health, and networks. Distinguish A being down from a single downstream disconnecting.

### 29.2. Keep A fenced if data corruption is suspected

If A suffered corruption or compromise, never let downstreams keep trusting A. Choose a verified clean upstream.

### 29.3. Reparenting downstreams

B/C can be reconfigured to receive WAL from P or another relay if timelines/WAL positions match. Ensure the new upstream retains enough WAL for downstreams to catch up.

### 29.4. WAL gaps

If the new upstream no longer holds needed segments, downstreams can fetch from the archive if supported and complete; otherwise reseed from a base backup.

### 29.5. Recovery order

Prioritize restoring WAL paths for critical nodes and production read downstreams. Document ordering and bandwidth limits so all nodes do not pull base backups concurrently and saturate the network.

## 30. Primary failover and timeline changes

When primary P is lost, a standby is promoted to new primary. Cascading descendants must follow the new timeline.

### 30.1. Choosing a promotion candidate

Pick a healthy standby with the newest data per policy and sufficient capacity. Compare received/flushed/replayed LSNs and synchronous acknowledgement state.

### 30.2. Fence the old primary

Ensure the old primary cannot keep accepting writes. DNS changes alone do not stop stale clients or open connections.

### 30.3. Timeline history

Promotion creates a new timeline. Standbys need matching timeline history/WAL to follow the new branch; do not assume every node switches upstreams cleanly on its own.

### 30.4. Reparenting direct and cascaded standbys

Update `primary_conninfo` on relay/direct standbys to match the new topology. Then verify downstreams still receive WAL through the new relays.

### 30.5. Rewind or reseed

If the old node diverged, `pg_rewind` may work when prerequisites/WAL suffice; otherwise rebuild the standby from a new base backup. Never manually copy data directories between diverged branches.

## 31. Reparenting: switching a downstream to another upstream

Reparenting changes a standby's WAL source. It is a topology change, not merely editing a hostname.

### 31.1. Check compatibility

Confirm the target upstream shares lineage/timeline and can supply the WAL the downstream needs. If the target is on another timeline or lacks WAL, follow a recovery/reseed strategy.

### 31.2. Update primary_conninfo

Update upstream host/port/user/TLS parameters via configuration management. Keep credentials in secret management.

### 31.3. Update slots

Create/verify slots on the new upstream if the downstream uses slots. Do not leave `primary_slot_name` pointing to a slot that exists only on the old node.

### 31.4. Verify the receiver

Check `pg_stat_wal_receiver.sender_host`/`slot_name` and logs to confirm the node connects to the right upstream.

### 31.5. Verify the sender

On the new upstream, check `pg_stat_replication` to see the downstream, state, and replay progress. Update topology inventory.

## 32. Failback after an old relay or primary returns

An old node returning online does not automatically become a valid upstream again.

### 32.1. Do not automatically reclaim the primary role

Avoid failing back merely because the old node recovered. Verify the authoritative primary, timeline, and data divergence.

### 32.2. The old node can become a standby

Use `pg_rewind` if preconditions are met, or reseed from a base backup of the new primary. Keep the old node fenced until complete.

### 32.3. Downstream topology

You may keep the new relay as upstream or move descendants back after the old relay catches up. Decide based on capacity, region, and failure domains.

### 32.4. Switch in batches

Reparent one group of downstreams, watch lag/health, then proceed. Avoid sweeping simultaneous changes without a rollback path.

### 32.5. Record final topology

Update inventory, alerts, backup schedules, slot owners, routing policies, and runbooks after failback.

## 33. Network and latency planning

Cascading is often used to distribute WAL across networks, making network design part of database architecture.

### 33.1. Bandwidth sized for WAL generation

Measure WAL bytes/sec during peak hours and bursts. Each hop needs enough throughput to transmit the stream and catch up after outages.

### 33.2. Network RTT

RTT affects replication feedback/acknowledgements and sync commit latency. Async replication is still bounded by network throughput/latency during catch-up.

### 33.3. Cross-region egress

A relay in a target region reduces cross-region streams from the primary, yet the relay needs sufficient egress to downstreams in that region.

### 33.4. Packet loss and reconnects

Packet loss, firewall idle timeouts, and NAT behavior can drop replication connections. Check TCP keepalives, `wal_sender_timeout`, and network devices.

### 33.5. TLS overhead

TLS protects WAL streams over untrusted networks while consuming CPU. Use proper certificate validation and monitor handshake/reconnect failures.

## 34. Storage and WAL disk planning

Every sender needs enough storage to hold WAL per retention policies and outage tolerances.

### 34.1. WAL generation rate

Estimate WAL bytes per second during peaks. Use `pg_stat_wal` or backup/monitoring tool metrics depending on version.

### 34.2. Outage windows

If a downstream can disconnect for 2 hours, calculate WAL generated in that window plus buffers and bursts.

### 34.3. Replication slot retention

Slots can retain WAL longer than expected. Alert on `retained_wal`/slot age and filesystem free space.

### 34.4. wal_keep_size is not a hard disk limit

This parameter sets a minimum WAL floor for standbys; replication slots/archives can retain far more WAL. Monitor actual disk usage.

### 34.5. Disk full is a critical incident

If `pg_wal` fills up, PostgreSQL can stop running or fail to accept writes. Keep runbooks to handle slots, archives, storage, and downstreams before hitting critical thresholds.

## 35. Backups and cascading topologies

Replication aids availability, while backups remain the independent recovery path.

### 35.1. Backups from the primary

Backing up from the primary adds I/O/network load and should avoid peak hours. Works well when the primary has headroom.

### 35.2. Backups from a standby

Some tools support taking base backups from a standby. This offloads the primary while increasing I/O on the relay/standby and carrying tool/version constraints.

### 35.3. Independent WAL archives

Store WAL archives on storage separate from database nodes. If a relay fails, the archive helps downstreams recover/reseed along the right chain.

### 35.4. Backup catalog

Record source node, timeline, LSN, backup ID, WAL coverage, and version. In cascading topologies, knowing which node produced a backup is critical.

### 35.5. Restore drills

Test restoring independently from the current topology. Never conclude DR works just because replicas are streaming.

## 36. Offloading workloads beyond SELECT

Standbys can offload read-mostly jobs as long as workloads are compatible with recovery mode.

### 36.1. Analytics/reporting

Long aggregation queries can run on dedicated replicas to shield the primary. However, they can create hot standby conflicts and lag.

### 36.2. Backups/exports

Logical exports from a standby can offload the primary in some scenarios. Check snapshot semantics, version, connection load, and replica lag.

### 36.3. Search indexing/ETL

Incremental data-reading jobs can run on replicas if consistency/lag tolerances allow. Consumers need checkpointing/idempotency and replica switchover handling.

### 36.4. Read-only BI

Isolating BI replicas from user-facing read replicas controls query duration and resource contention.

### 36.5. Never run write-side maintenance on a standby

Standard DDL/DML cannot run on a hot standby. Schema changes must go through the primary and replay downstream.

## 37. Security for cascading replication

Every hop is a connection privileged to read the cluster's WAL.

### 37.1. Least-privilege replication role

Roles need `LOGIN` and `REPLICATION`, without `SUPERUSER` just to stream WAL.

### 37.2. Network segmentation

Open database ports only between required upstream/downstream nodes and monitoring/bastion hosts.

### 37.3. TLS and certificate validation

Enforce TLS per policy, verify server identity, and manage certificate rotations. Avoid permissive `sslmode` over untrusted networks.

### 37.4. Secret rotation

Update credentials on every downstream on schedule. Test reconnects after rotation to avoid breaking replication.

### 37.5. Auditing and access control

Audit replication connections, role usage, config changes, and slot operations. Never grant replication privileges to application read roles.

## 38. Goal-oriented monitoring and alerting

Do not alert only when a standby disconnects. Alert based on impact to RPO, RTO, and read freshness.

| Metric | Alert when | Impact |
|---|---|---|
| Receiver disconnected | Exceeds allowed reconnect window | WAL stream stopped |
| Replay lag | Exceeds freshness SLO | Stale reads / failover risk |
| Sender slots | Nearing `max_wal_senders` | Cannot accept more downstreams |
| Slot retained WAL | Rising fast / low disk | Disk exhaustion |
| WAL archive lag | Exceeds RPO buffer | Recovery point falls behind |
| Hot standby conflicts | Sudden spike | Read query cancellations |
| Relay CPU/disk/network | Sustained saturation | Fan-out bottleneck |
| Query latency | Exceeds read SLO | User impact |
| Timeline mismatch | Node on unexpected branch | Replication cannot continue |
| Fencing state | Old primary still reachable/writable | Split-brain risk |

### 38.1. Alert per hop

Each sender/receiver pair needs its own metrics. A dashboard showing only P→A can miss B/C lagging severely.

### 38.2. Alert on trends

Steadily rising lag is more dangerous than a brief spike. Track rate-of-change, duration, and WAL generation.

### 38.3. Alert by business freshness

If reporting dashboards tolerate 5 minutes of lag while user profiles tolerate 1 second, set separate thresholds.

### 38.4. Alert on disk before exhaustion

Combine filesystem free space, WAL retained bytes, slot inactivity, and growth rate so you have time to act.

### 38.5. Test alert paths

Alerts must reach the right on-call with a runbook; unmonitored metrics cannot drive action.

## 39. Troubleshooting: downstream fails to connect to relay

### 39.1. Check receiver state

Inspect `pg_stat_wal_receiver` and PostgreSQL logs on the downstream for connection/auth/streaming errors.

### 39.2. Check sender on the relay

Inspect `pg_stat_replication` on the relay. If no row appears, check HBA, network, `max_wal_senders`, and the replication role.

### 39.3. Check primary_conninfo

Verify host, port, user, `application_name`, TLS mode, and secrets. Avoid pointing at the old primary.

### 39.4. Check slots

If `primary_slot_name` is set, confirm the slot exists on that exact relay and has not been invalidated/lost WAL.

### 39.5. Check timeline/WAL availability

The downstream needs continuous WAL on the right timeline or matching archive recovery. If segments are missing, restore from archive or reseed.

## 40. Troubleshooting: replica lag steadily growing

### 40.1. Distinguish receive lag and replay lag

If receive lag grows, check network/upstream sender/receiver throughput. If replay lag grows, check disk/CPU/conflicts and query workloads.

### 40.2. Relay egress saturation

A relay feeding many downstreams may struggle to send WAL fast enough. Measure network egress and active sender sessions.

### 40.3. Disk latency

Replay and WAL reads need sufficient disk throughput/latency. Inspect IOPS, queue depth, and storage saturation.

### 40.4. Hot standby queries

Long queries force recovery to wait/cancel per conflict policy. Check `pg_stat_database_conflicts` and active queries.

### 40.5. WAL bursts

Bulk loads, index builds, or batch updates generate WAL bursts. Evaluate catch-up capacity and peaks, not average write rates alone.

## 41. Troubleshooting: read pool returns stale data

### 41.1. Identify the selected replica

Log the host/`application_name`, upstream chain, and replay LSN when the query ran.

### 41.2. Check consistency requirements

Did the request require read-after-write? If so, route to the primary or wait for an LSN token.

### 41.3. Check routing policies

The proxy may pick a replica that passes TCP checks yet lags heavily. Add health/lag checks and fallback behavior.

### 41.4. Sticky sessions

If users need monotonic reads, pin them to one replica or ensure the chosen replica's replay position never regresses behind the prior token.

### 41.5. Do not mask errors with infinite retries

If replicas cannot catch up, return degraded responses/fallbacks per policy and alert. Unlimited retries amplify load.

## 42. Lab: designing a primary → relay → leaves topology

Labs should run on isolated PostgreSQL VMs/containers with the same major version and private networking. Never use production credentials/data.

~~~text
Primary P
   |
   v
Relay A
  / \
 v   v
B   C
~~~

### 42.1. Prepare nodes

Create four separate data directories/instances with dedicated ports and storage. Record host/port, role, upstream, and downstream.

### 42.2. Configure primary

Set an appropriate `wal_level`, and size `max_wal_senders` and `max_replication_slots` for A plus lab connections. Create the replication role and source-restricted HBA rule.

### 42.3. Create standby A

Run `pg_basebackup` from P, configure `primary_conninfo` to P, and start A in standby mode. Confirm `pg_stat_wal_receiver` on A.

### 42.4. Configure A as sender

Set `max_wal_senders` on A, add HBA rules for B/C, and verify network routing. If using slots, create slots on A.

### 42.5. Create B/C

Take base backups from a compatible source per lab procedure, point `primary_conninfo` to A, and start B/C. Verify sender state on A and receiver state on B/C.

## 43. Lab: observing WAL across each hop

### 43.1. Create a write workload on P

~~~sql
CREATE TABLE public.replication_lab (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO public.replication_lab(payload)
SELECT repeat('x', 200)
FROM generate_series(1, 10000);
~~~

### 43.2. Check P→A

On P, inspect `pg_stat_replication` and identify A's `application_name`. Record sent/write/flush/replay LSNs.

### 43.3. Check A→B/C

On A, query `pg_stat_replication` and record positions for B/C. Do not look for B/C in P's view when they connect directly to A.

### 43.4. Check receivers

On B/C, query `pg_stat_wal_receiver` to confirm `sender_host` is A.

### 43.5. Compare replay

Run `SELECT` on each standby to confirm rows replayed. Capture aligned timestamps and LSN samples.

## 44. Lab: distributing read queries

### 44.1. Create read-only endpoints

Configure a primary/write endpoint and read endpoints for B/C. Avoid sharing one connection string that hides which node serves requests.

### 44.2. Verify actual serving node

~~~sql
SELECT
    inet_server_addr(),
    inet_server_port(),
    pg_is_in_recovery();
~~~

Applications/test clients can log the endpoint to verify queries route to the right standby.

### 44.3. Verify read-only behavior

Run `SELECT` on the standby. DML must be rejected in recovery state; never use DML to test read pools in production.

### 44.4. Test read-after-write

Write a row on P and immediately read on B. Observe the row may be missing before B replays the commit. Repeat once replay LSN catches up.

### 44.5. Fallback

Simulate B breaching the lag threshold and verify the router chooses C or primary per policy. Record latency and consistency behavior.

## 45. Lab: hot standby conflicts

Use only a lab with test data and bounded query durations.

### 45.1. Generate workload on primary

Create a table, load rows, and run `UPDATE`/`DELETE` on P to generate cleanup-related WAL records.

### 45.2. Run a long query on standby

On B, open a snapshot read transaction and intentionally hold a short query open. Observe conflict behavior when upstream cleanup replays.

### 45.3. Monitor conflicts

Query `pg_stat_database_conflicts` before/after. Record counter changes and related logs.

### 45.4. Test changing delay

In the lab, alter `max_standby_streaming_delay` and repeat the workload. Observe the query cancellation vs replay lag trade-off.

### 45.5. Test hot_standby_feedback

Toggle it in the lab, tracking conflicts and upstream vacuum behavior. Never extrapolate production bloat from a tiny lab.

## 46. Lab: failover and reparenting

This lab requires an isolated topology and disposable data.

### 46.1. Capture baseline

Save timeline/LSN, sender/receiver states, upstream names, and slot inventories of P/A/B/C.

### 46.2. Simulate relay outage

Stop A in the lab. Observe B/C receivers disconnecting and replay positions stalling.

### 46.3. Reparent leaves

Reconfigure B/C to connect to P or an alternate relay if WAL/timeline compatibility permits. Verify slots on the new upstream.

### 46.4. Confirm catch-up

On the new upstream, check `pg_stat_replication`; on B/C, check `pg_stat_wal_receiver`. Wait for replay LSNs to catch up with the workload.

### 46.5. Simulate primary failover

Promote a standby per lab runbook, fence old P, reparent relay/leaf nodes, and verify timelines. Never run practice promotions on a production cluster.

## 47. Common misconceptions

1. **"Cascading replication automatically load-balances SELECT."** False; it relays WAL, while query routing requires a separate layer.
2. **"A primary still has to send directly to every leaf."** False; leaves can receive from relays.
3. **"Only the primary needs relay configuration."** False; relays need sender capacity/HBA/slots for downstreams.
4. **"pg_stat_replication on the primary shows the whole tree."** False; it shows direct sender connections on the queried node.
5. **"WAL receive LSN equals replay LSN."** False; a standby can receive WAL without having replayed it yet.
6. **"Extra hops do not add lag."** False; network, disk, and replay queues at each hop can add lag.
7. **"Replication slots have no cost."** False; slots can pin WAL and fill disks.
8. **"wal_keep_size is an absolute cap on WAL."** False; slots/archives can retain additional WAL.
9. **"hot_standby_feedback does not affect the primary."** False; it can defer cleanup and increase bloat.
10. **"Increasing max_standby_streaming_delay is always better."** False; fewer queries cancel while replay lag can rise.
11. **"Every SELECT can be routed to a standby."** False; consider read-after-write, volatile functions, and transaction semantics.
12. **"Synchronous on the primary guarantees every leaf has replayed."** False; acknowledgement semantics apply per relationship.
13. **"If TCP is healthy, replication is healthy."** False; verify receiver/sender state, WAL continuity, and replay progress.
14. **"Primary failover does not affect cascading leaves."** False; descendants may need reparenting/timeline handling.
15. **"Changing DNS is fencing."** False; stale connections can keep writing to the old primary.
16. **"Standbys replace backups/PITR."** False; logical corruption replays across every tier.
17. **"The more downstreams on one relay, the better."** False; senders, disk, CPU, and egress all have limits.
18. **"Read replicas need no catch-up capacity."** False; after outages they need bandwidth to replay backlogs.
19. **"Byte lag converts directly to time lag."** False; you need the WAL generation rate.
20. **"You can reparent to any standby."** False; timeline/WAL compatibility is required.
21. **"pg_rewind can always rescue an old node."** False; prerequisites and sufficient WAL are required.
22. **"Enabling hot_standby_feedback on a leaf always propagates horizons up the entire tree."** Never assume; verify semantics/version at each hop.
23. **"A readable replica has finished replaying everything."** False; queries can read older state.
24. **"Backups from a standby add zero load."** False; backups still consume CPU, disk, and network.
25. **"Cascading is multi-primary."** False; physical standbys remain recovery/read-only nodes.

## 48. Practice exercises

### Exercise 1 — Definition

What is cascading replication?

**Answer:** A standby receives WAL from an upstream and forwards WAL to downstream standbys.

### Exercise 2 — Topology

In P→A→B, which node is B's direct upstream?

**Answer:** A.

### Exercise 3 — WAL fan-out

Which component does cascading distribute?

**Answer:** The WAL stream.

### Exercise 4 — Query routing

Does PostgreSQL automatically route all `SELECT` queries to hot standbys?

**Answer:** No; application/proxy/middleware routing is required.

### Exercise 5 — Sender

Which view on a sending node displays direct replication clients?

**Answer:** `pg_stat_replication`.

### Exercise 6 — Receiver

Which view on a standby displays WAL receiver state?

**Answer:** `pg_stat_wal_receiver`.

### Exercise 7 — Relay config

Which parameter limits WAL sender processes on a relay?

**Answer:** `max_wal_senders`.

### Exercise 8 — WAL level

Which `wal_level` is usually sufficient for physical replication?

**Answer:** `replica`.

### Exercise 9 — Downstream upstream

Which parameter specifies the upstream connection?

**Answer:** `primary_conninfo`.

### Exercise 10 — Application name

How does `application_name` help?

**Hint:** Identifies the standby in sender statistics.

### Exercise 11 — Slot location

If B streams from A, where is B's replication slot managed?

**Answer:** On A.

### Exercise 12 — Slot risk

Why are long-inactive slots dangerous?

**Answer:** They can retain WAL and fill the disk.

### Exercise 13 — wal_keep_size

Is `wal_keep_size` an absolute cap on WAL retention?

**Answer:** No.

### Exercise 14 — Lag

How do receive LSN and replay LSN differ?

**Answer:** Receive is WAL received/written; replay is WAL applied to the standby's state.

### Exercise 15 — Local stats

Why doesn't querying `pg_stat_replication` on P show B if B connects to A?

**Answer:** The view lists only direct sender connections on the queried node.

### Exercise 16 — Read-only

Can you run `INSERT` on a hot standby?

**Answer:** No.

### Exercise 17 — Read-after-write

Why might an `INSERT` on P not immediately appear in a `SELECT` on B?

**Hint:** B has not replayed the commit WAL yet.

### Exercise 18 — LSN token

What does an application use an LSN token for?

**Hint:** Waiting for a replica to replay up to the commit point needed for a read.

### Exercise 19 — PgBouncer

Does PgBouncer automatically parse SQL to route `SELECT` to replicas?

**Answer:** No; it primarily handles connection pooling.

### Exercise 20 — Hot standby conflict

What can a cleanup conflict cause?

**Answer:** Standby queries may be canceled so WAL replay can continue.

### Exercise 21 — max_standby_streaming_delay

Is this a per-query runtime limit?

**Answer:** No; it limits how long recovery can delay due to conflicts within the processing window.

### Exercise 22 — hot_standby_feedback

What are its main benefit and cost?

**Answer:** Reduces query cancellations while potentially increasing upstream bloat.

### Exercise 23 — Delayed standby

What does `recovery_min_apply_delay` provide?

**Hint:** Creates a replay delay window to catch certain logical mistakes.

### Exercise 24 — Synchronous replication

Can zero RPO across the whole cascading tree be inferred from sync primary→relay alone?

**Answer:** No; acknowledgements must be determined at each hop.

### Exercise 25 — Relay outage

If A stops working in P→A→B, how is B affected?

**Answer:** B loses its WAL source until A returns or B is reparented.

### Exercise 26 — Reparent

Before switching B from A to P, what must be checked?

**Hint:** Timeline, WAL availability, slots, credentials, and upstream capacity.

### Exercise 27 — Timeline

What important artifact does promotion create for downstreams?

**Answer:** A new timeline; downstreams must follow a compatible WAL branch.

### Exercise 28 — Fencing

Why fence the old primary before opening writes on the new primary?

**Answer:** Prevents split brain and divergent writes.

### Exercise 29 — Disk planning

If WAL generation is 20 MB/s and an outage window of 30 minutes must be tolerated, what is the ideal baseline WAL before buffers?

**Answer:** 20 × 60 × 30 = 36,000 MB, roughly 36 GB decimal.

### Exercise 30 — Capacity

A relay sends WAL to 20 downstreams and serves analytics. What should be measured?

**Hint:** Sender count, network egress, disk latency, CPU, replay lag, read query latency, and headroom.

### Exercise 31 — Read routing

Where should a query needing the latest data immediately after a write be routed?

**Answer:** Primary or a replica confirmed replayed up to the required LSN.

### Exercise 32 — Monotonic reads

Why can alternating a user across replicas with varying lag show data moving backward?

**Hint:** The second replica may have replayed less WAL than the first.

### Exercise 33 — Backup

Does cascading replication replace WAL archiving/PITR?

**Answer:** No.

### Exercise 34 — Backup from standby

What are the benefit and trade-off?

**Hint:** Offloads primary while adding load to the standby and depending on tool/version constraints.

### Exercise 35 — Monitoring

Which metric helps detect query cancellations caused by recovery conflicts?

**Answer:** `pg_stat_database_conflicts`.

### Exercise 36 — Receiver identity

After reparenting, which field helps confirm the new upstream?

**Answer:** `sender_host` in `pg_stat_wal_receiver`.

### Exercise 37 — Leaf lag

Why can a leaf's lag exceed a relay's lag?

**Hint:** Extra network hop, sender queues, and receiver/replay backlogs.

### Exercise 38 — Slot loss

If a slot exceeds `max_slot_wal_keep_size` and loses required WAL, what must be done?

**Hint:** Use the archive if WAL is complete; otherwise reseed the standby.

### Exercise 39 — Failback

Can an old primary returning after promotion automatically reclaim the primary role?

**Answer:** No; requires fencing, timeline reconciliation, `pg_rewind` or reseed, and a failback plan.

### Exercise 40 — End-to-end design

Design a topology for a primary in region A, a relay in region B, and four read replicas in regions B/C. Requirements: 5-second read freshness, 2-minute primary failure RTO, plus long analytics queries.

**Hint:** Pick direct relay(s) by failure domain/capacity, group downstreams, isolate analytics onto a dedicated replica, monitor each hop/LSN, configure a read router with lag-aware selection and fallbacks, set separate conflict/`hot_standby_feedback` policies, clarify sync semantics if durability requires it, maintain independent backups/PITR, automate fencing/reparenting, and run restore/failover drills.

## 49. Design and operations checklist

### 49.1. Topology

- [ ] Primary, relays, leaves, and direct connections documented?
- [ ] No replication cycles?
- [ ] Every node has a clear owner and purpose?
- [ ] Failure domains/regions defined?
- [ ] Alternate upstreams and reparenting plans prepared?

### 49.2. WAL and connections

- [ ] Appropriate `wal_level`?
- [ ] Sufficient `max_wal_senders` on primary and relays?
- [ ] Sufficient `max_replication_slots`?
- [ ] WAL retention sized with headroom for outage windows?
- [ ] Slot owners and inactive-slot alerts configured?
- [ ] Independent WAL archiving and PITR tested?

### 49.3. Read routing

- [ ] Write pool always routes to primary?
- [ ] Read pool selects only healthy replicas?
- [ ] Lag thresholds defined per use case?
- [ ] Read-after-write/monotonic reads handled?
- [ ] Long analytics queries isolated to a dedicated replica?
- [ ] Fallback behavior defined?

### 49.4. Conflicts and capacity

- [ ] `hot_standby` and conflict metrics monitored?
- [ ] `max_standby` delays properly tuned?
- [ ] `hot_standby_feedback` bloat trade-off evaluated?
- [ ] Relay has sufficient network ingress/egress?
- [ ] Disk/CPU sufficient for WAL replay and reads?
- [ ] Headroom reserved for catch-up and `pg_basebackup`?

### 49.5. Failover and security

- [ ] Sender/receiver metrics collected at every hop?
- [ ] Timeline/reparenting procedures tested?
- [ ] Old primary fencing verified with evidence?
- [ ] Least-privilege replication roles and TLS enforced?
- [ ] Secret rotation tested?
- [ ] Backup/restore/failover drills scheduled?

## 50. Quick reference table

| Component | Role |
|---|---|
| Cascading replication | Standby relays WAL to downstreams |
| Primary | Authoritative node accepting writes |
| Relay standby | Receives and sends WAL |
| Leaf standby | Downstream read replica |
| WAL sender | Sends WAL over replication protocol |
| WAL receiver | Receives WAL from upstream |
| Replay LSN | WAL applied on the standby |
| `pg_stat_replication` | Direct sender connections |
| `pg_stat_wal_receiver` | Receiver connection on standby |
| `pg_stat_database_conflicts` | Query cancellations from recovery conflicts |
| `primary_conninfo` | Upstream connection configuration |
| `primary_slot_name` | Slot requested by downstream on upstream |
| `max_wal_senders` | Limits WAL sender processes |
| `max_replication_slots` | Number of replication slots |
| `wal_keep_size` | Minimum WAL amount to retain |
| `max_slot_wal_keep_size` | Cap on WAL retained by slots per version |
| `hot_standby` | Read-only queries during recovery |
| `hot_standby_feedback` | Sends snapshot horizon to reduce cleanup conflicts |
| `max_standby_streaming_delay` | Limits replay delay from streaming conflicts |
| `recovery_min_apply_delay` | Intentionally delays replay |
| Read load balancing | Distributes SQL reads via app/proxy |
| Read-after-write | Ensures requests read their own commits |
| LSN token | Replay milestone to reach before reading |
| Reparenting | Switching a downstream to another upstream |
| Fencing | Preventing old primary from continuing writes |
| Timeline | Branch of WAL history after recovery/promotion |
| `pg_rewind` | Re-syncs diverged node when preconditions hold |
| WAL archive | Independent recovery path for WAL |
| Reseed | Rebuilding a standby from a base backup |

## 51. Conclusion

**Cascading replication distributes WAL across a multi-tier topology; read load balancing distributes `SELECT` queries per application or middleware policy.** A standby can act as a relay, serve reads, or do both, yet each role consumes network, CPU, disk, and connection capacity. Tree topologies reduce direct fan-out on the primary and place replicas near workloads, at the trade-off of making relays dependencies for downstreams and adding potential lag per hop.

For stable operations, configure senders/receivers, HBA, replication roles, slots, and WAL retention on every node. Monitor `pg_stat_replication` on every sender, `pg_stat_wal_receiver` on every standby, replay LSNs, conflict counters, slot retention, and disk headroom. For read routing, separate eventual consistency from read-after-write, select replicas by lag/capacity, and define explicit fallbacks. Long queries on hot standbys need clear conflict policies; `hot_standby_feedback` reduces cancellations while causing upstreams to hold dead tuples longer.

When a relay or primary fails, descendants must reparent according to timeline/WAL compatibility; promotion must pair with fencing to avoid split brain. Cascading never replaces backups/PITR and does not protect against replayed logical corruption. Validate designs through labs, failover drills, restore tests, and per-hop monitoring.

Operational principle: **design WAL topology, read routing, consistency, capacity, and failover as related parts with distinct criteria; measure lag at every hop, protect WAL/backups independently, and drill reparenting before an incident demands it.**
