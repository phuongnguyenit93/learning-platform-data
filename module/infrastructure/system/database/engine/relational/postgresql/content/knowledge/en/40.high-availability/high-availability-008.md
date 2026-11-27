# Integrating Orchestration Tools Like Patroni and a Consensus Store

**Streaming replication** keeps one or more PostgreSQL standbys close to the primary's state by transferring WAL. However, replication by itself does not fully solve detecting failed nodes, deciding who gets to be primary, preventing two primaries from accepting writes simultaneously, updating application routing, and rejoining the old node. Those steps require an orchestration layer.

**Patroni** is a popular HA tool for PostgreSQL. Patroni runs on the database nodes, monitors PostgreSQL, and coordinates with a **Distributed Configuration Store (DCS)** such as etcd, Consul, ZooKeeper, or the Kubernetes API. The DCS provides a place to store cluster state and a distributed coordination mechanism. Patroni uses that information to elect/select a leader, manage the leader lock/lease, track members, and control PostgreSQL operations such as start, stop, promote, demote, and reinitialize.

HA orchestration is a distributed protocol across agents, the DCS, PostgreSQL processes, networking, and client routing. Every component must have an explicit failure model and security boundary.

```text
                 Applications / connection pools
                             |
                       VIP / Proxy / DNS
                             |
                   Current writable primary
                             |
              +--------------+--------------+
              |                             |
          PostgreSQL                    Patroni agent
              |                             |
         WAL streaming               HA loop / REST API
              |                             |
        +-----+------+                      |
        |            |                       |
     Standby A    Standby B                  |
        |            |                       |
    Patroni A    Patroni B                   |
        |            |                       |
        +------------+-----------------------+
                             |
                     DCS cluster/quorum
                  (etcd / Consul / ZooKeeper /
                       Kubernetes API)
```

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why PostgreSQL replication needs an orchestration layer to become an HA solution.
2. Distinguish between database replication, leader election, distributed locks/leases, service discovery, and client routing.
3. Describe the role of Patroni on each PostgreSQL node.
4. Explain a DCS and its requirements for consistency, quorum, availability, and failure detection.
5. Compare etcd, Consul, ZooKeeper, and the Kubernetes API as coordination backends.
6. Understand leader key/lease, TTL, sessions, renewal, and fencing limitations.
7. Explain the Patroni HA loop, state transitions, and REST API.
8. Understand bootstrap, dynamic configuration, local configuration, and cluster initialization.
9. Distinguish between automatic failover, planned switchover, and replica reinitialization.
10. Understand synchronous mode, synchronous replication policies, and failover safety.
11. Integrate proxies/load balancers/service discovery with Patroni.
12. Secure the DCS, Patroni REST API, replication traffic, and PostgreSQL credentials.
13. Design monitoring, backups, restores, disaster recovery, and operational runbooks.
14. Recognize split-brain, DCS outages, network partitions, stale leaders, and quorum scenarios.
15. Practice deploying and testing a Patroni cluster in a lab environment.

## 2. Problems Orchestration Tools Solve

### 2.1. Streaming Replication Only Copies WAL

PostgreSQL physical streaming replication transfers WAL from primary to standbys. It keeps standby data files close to the primary and provides promotion capability. Yet PostgreSQL does not decide everything on its own:

- Is the primary truly dead or just unreachable from one monitor?
- Which standby is eligible to promote?
- Is another node currently holding primary authority?
- Who is authorized to execute promotion?
- How should the endpoint be updated so applications connect to the new primary?
- How should the old primary be brought back as a standby?

These questions belong to the orchestration and HA policy layer.

### 2.2. Two Primaries Can Cause Split-Brain

Suppose primary A becomes network-partitioned from standby B. If B promotes itself while A still accepts writes from some clients, the system has two independent primaries. Both generate divergent WAL histories that cannot automatically merge.

The HA manager needs a distributed ownership mechanism so only one node holds the leader role at a time, along with a fencing mechanism to prevent the old primary from continuing to serve writes once ownership transfers.

### 2.3. Failure Detection Is Not Absolute Truth

A node failing a health check may mean:

- The PostgreSQL process crashed.
- The host powered off or lost electricity.
- The network path between the monitor and node failed.
- CPU/disk overload slowed responses down.
- Firewall/DNS/TLS settings changed.
- The DCS or control plane is unreachable.

A timeout is only a signal. It does not prove a node is dead. A safe HA design must combine leases/quorum, node state, fencing, and promotion rules.

### 2.4. Separating Planes

| Plane | Responsibility |
| --- | --- |
| Data plane | PostgreSQL primary/standbys, WAL streaming, reads/writes. |
| Control plane | Patroni agents, DCS, leader election, cluster membership. |
| Client routing plane | HAProxy/PgBouncer/VIP/DNS/service discovery, read/write routing. |
| Backup/recovery plane | Base backups, WAL archiving, PITR, restore testing. |
| Observability plane | Metrics, logs, alerts, auditing, and incident response. |

A healthy control plane does not guarantee a healthy data plane. A database may be running without a valid leader lock; a leader lock may exist while the PostgreSQL process is not serving queries. Monitor each plane separately.

## 3. What Is Patroni?

### 3.1. Patroni Agent on Each Database Node

Patroni is a Python daemon running alongside PostgreSQL on every node in the cluster. It manages the PostgreSQL lifecycle and participates in HA coordination:

- Reads local configuration and dynamic configuration from the DCS.
- Monitors PostgreSQL state using process checks and SQL connections.
- Tracks cluster state, the leader lock, and member records in the DCS.
- Runs a periodic HA loop to decide what actions to take.
- Holds/renews the leader lock if the node is the leader.
- Transitions the node into a standby or promotes it when policy permits.
- Creates/reinitializes replicas via PostgreSQL tools such as `pg_basebackup`.
- Exposes a REST API for health checks and administration.

The Patroni agent is not a PostgreSQL extension. It is an external process controlling the PostgreSQL server.

### 3.2. Each Node Has One Patroni Instance

A three-node cluster normally has three Patroni agents:

```text
Node A: PostgreSQL + Patroni A ----+
Node B: PostgreSQL + Patroni B ----+---- DCS
Node C: PostgreSQL + Patroni C ----+
```

The agents exchange state via the DCS and PostgreSQL replication. The DCS does not contain database rows or WAL; it contains coordination metadata.

### 3.3. Patroni Does Not Replace PostgreSQL Replication

Patroni uses PostgreSQL physical replication to keep standbys synchronized. It can invoke `pg_basebackup`, manage `primary_conninfo`, replication slots, and promotion, while WAL is still shipped and replayed by PostgreSQL.

### 3.4. Patroni Is Not a Load Balancer by Itself

Patroni's REST API exposes node role/health information. HAProxy, PgBouncer, Envoy, cloud load balancers, or service discovery can use that information to route clients. Routing must be configured explicitly; simply installing Patroni does not redirect client connections on its own.

### 3.5. Patroni Does Not Replace Backups

Patroni focuses on HA and orchestration. It is not a full backup retention/PITR system. Base backups, WAL archiving, immutable backup copies, and restore drills remain essential.

## 4. Distributed Configuration Store (DCS)

### 4.1. What Does the DCS Store?

The DCS is a distributed state store used by Patroni agents to coordinate. Typical data includes:

- Shared cluster configuration.
- Leader key/lease and information on which node holds leadership.
- Member records/heartbeats of Patroni nodes.
- Failover/switchover state or related metadata.
- History/timeline metadata and cluster state per version/configuration.
- Synchronous replication state when synchronous mode is enabled.

Specific key names/paths and schemas depend on Patroni version/backend; never edit DCS keys manually while the cluster is running.

### 4.2. The DCS Does Not Store Database Contents

The DCS does not replicate PostgreSQL tables, indexes, WAL, or user data. If the DCS loses data, PostgreSQL data files may still exist, but Patroni may lose leader ownership/configuration information and cannot coordinate safely until state is restored.

### 4.3. Why Is Consistency Needed?

Suppose two agents both write a leader key without atomic compare-and-set/quorum semantics. Both could think they are leader. The DCS must provide atomic operations and sufficient ordering consistency to guarantee that an ownership record is updated in a single linear sequence.

### 4.4. Quorum

Many DCS engines use a consensus protocol so nodes agree on one ordering of writes. A cluster has quorum when enough members can participate in decisions. For instance, etcd/Raft is typically deployed with an odd number of voting members to tolerate member failures:

| Voting members | Quorum | Members that can fail while keeping quorum |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 3 | 2 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

This is majority quorum arithmetic. Do not increase DCS member count arbitrarily: more members complicate quorum and can increase latency.

### 4.5. How Does a DCS Outage Impact the Cluster?

When Patroni cannot reach the DCS, agents cannot renew/read ownership normally. The node holding the leader lock may have to demote/stop PostgreSQL to avoid continuing writes when it cannot prove leadership. Standbys may be unable to promote because there is no quorum/ownership decision.

Exact behavior depends on Patroni version, DCS backend, and safety settings. A DCS outage must never be interpreted as "the database will immediately fail over on its own."

### 4.6. The DCS Must Have Independent Failure Domains

Placing all DCS voting members on the same host/rack/availability zone defeats quorum when that failure domain goes down. Distribute members across an appropriate topology and understand inter-zone latency.

### 4.7. Do Not Use the DCS as an Application Database

The DCS is meant for small coordination metadata, not application data or arbitrary query workloads. Do not create arbitrary keys inside Patroni's namespace.

## 5. Common DCS Backends

### 5.1. etcd

etcd is a distributed key-value store using Raft consensus. Patroni uses etcd to store cluster state, leader ownership, and dynamic configuration.

Characteristics:

- Strong consistency for quorum-committed operations.
- Lease/TTL and watch APIs supporting leader ownership/notifications.
- Raft majority quorum; 3- or 5-voting-member clusters are commonly used.
- Requires securing client/peer endpoints, certificates, and the data directory.
- Should not share an inadequately sized/isolated etcd cluster across every critical workload.

etcd is a widely used backend across many Patroni deployments.

### 5.2. Consul

Consul provides service discovery, health checks, and a distributed KV store with consistency controls. Patroni can use Consul KV/session mechanisms as a DCS.

Characteristics:

- KV and sessions/locks supporting coordination.
- Agent/server architecture; requires understanding server quorum and datacenter behavior.
- Can integrate with service discovery, though explicit client routing configuration is still required.
- Must protect ACL tokens, gossip encryption, TLS, and server quorum.

Consul session/lock behavior and Patroni DCS semantics must be verified per version.

### 5.3. ZooKeeper

ZooKeeper is a coordination service using atomic operations and the Zab protocol, offering ephemeral znodes, watches, and ensemble quorum.

Characteristics:

- Ephemeral nodes tied to client sessions.
- Watches notifying state changes.
- Ensembles typically use an odd number of voting members.
- Requires managing session timeouts, connection loss, ACLs, and snapshot/transaction logs.
- Watches have one-shot semantics; clients must re-register as needed.

Patroni can use a ZooKeeper backend depending on supported versions/integrations.

### 5.4. Kubernetes API

In Kubernetes, Patroni can use the Kubernetes API/Endpoints or related resources as a DCS, depending on configuration and Patroni version. Kubernetes' API server and backing etcd provide control-plane consistency.

Characteristics:

- No strict need to operate a separate etcd cluster solely for Patroni.
- Can use Kubernetes objects/leases per supported backend.
- Requires least-privilege RBAC service accounts, API availability, and network connectivity.
- A Kubernetes control-plane outage can impact coordination; PostgreSQL pods/volumes may keep running, but failover decisions become restricted.
- Do not confuse Kubernetes liveness/readiness probes with Patroni leader election.

### 5.5. Quick Comparison

| Criterion | etcd | Consul | ZooKeeper | Kubernetes API |
| --- | --- | --- | --- | --- |
| Coordination primitive | KV, lease, watch, transaction | KV, session, lock | Znode, ephemeral node, watch | API objects/leases per backend |
| Consensus/quorum | Raft | Raft for server quorum | Zab ensemble quorum | API server backed by etcd |
| Built-in service discovery | External tool needed | Yes | Not primary focus | Kubernetes Services/Endpoints |
| Operations | Dedicated cluster or managed | Agents + servers | Dedicated ensemble | Kubernetes control plane |
| Primary security | TLS, auth/RBAC | ACL, TLS, gossip encryption | ACL, TLS/auth | RBAC, service account, TLS |
| Main risks | Quorum loss, disk/latency | Server quorum/session/ACL | Session timeout/ensemble | API availability/RBAC/control plane |

There is no single best backend for every organization. Choose the backend your operations team understands well and can monitor, back up, upgrade, and recover.

## 6. Leader Lock, Lease, and Ownership

### 6.1. What Is a Leader Lock?

Patroni uses a record in the DCS to represent which node holds leader authority. Agents read/write this record using the backend's atomic/lease mechanism. A node should only serve writes as primary when it holds valid ownership and the appropriate PostgreSQL role/state.

### 6.2. TTL and Renewal

Leader ownership typically has a lifetime/TTL. The leader must renew the lock periodically. If it fails to renew within the allotted window, the DCS may treat the lease as expired and allow another node to claim ownership under the HA protocol.

Related parameters include:

- `ttl`: how long the lease/leader lock persists if unrenewed.
- `loop_wait`: interval between HA loop iterations.
- `retry_timeout`: retry limit when DCS/PostgreSQL operations encounter errors.
- `primary_start_timeout`: wait time for primary startup in certain transitions.

Names and constraints vary across Patroni versions. Values must be configured consistently with DCS timeouts and actual latency.

### 6.3. Why Is an Overly Short TTL Dangerous?

If the TTL is shorter than normal DCS/network pauses, the leader can lose its lock due to GC pauses, CPU starvation, network jitter, or DCS latency. This causes unnecessary demotions/failovers.

Conversely, an overly long TTL slows leader failure detection and lengthens RTO. Choose TTL based on measured worst-case latency and failure detection targets.

### 6.4. Compare-and-Set / Transactions

The DCS must ensure operations claiming/renewing the leader lock succeed only when ownership/version preconditions remain valid. Backends use transactions, revisions, sessions, or lease semantics to prevent two agents from blindly overwriting ownership in a last-writer-wins race.

### 6.5. Lease Expiry Does Not Automatically Stop the Old Process

A lease in the DCS does not kill the CPU or close PostgreSQL sockets on the old node. If a node is partitioned from the DCS while still holding client connections, Patroni demotion/stop and/or external fencing/watchdog are needed. This is why distributed locks must pair with fail-closed behavior and a fencing strategy.

### 6.6. Watchdog

Patroni can integrate with the Linux watchdog so a node resets/fences itself if it cannot maintain safe conditions within the allowed time. Hardware/software watchdog must be properly installed and configured, tested in practice, and its host/VM semantics understood. A `watchdog` config entry without a functioning device provides no real fencing.

### 6.7. Infrastructure-Layer Fencing

On cloud/virtualized systems, you may need power fencing, storage detachment, write-access revocation, or control-plane actions. Fencing must be executed by a trusted authority with explicit timeouts. Switching DNS/VIP does not replace fencing because the old primary can still receive traffic via other paths.

### 6.8. Single-Writer Invariant

The core objective is that at any point in time only one node is authorized to accept writes for the cluster. Every failover, manual promotion, restore, and maintenance operation must preserve this invariant.

## 7. Patroni HA Loop and Node States

### 7.1. HA Loop

Each Patroni agent runs a periodic coordination loop:

1. Read local PostgreSQL state.
2. Read dynamic configuration/member/leader state from the DCS.
3. Determine whether this node is leader, replica, candidate, or in a fault state.
4. If leader, verify and renew the leader lock.
5. If replica, check the leader and replication health.
6. Apply policies for failover, synchronous mode, and replica selection.
7. Execute the appropriate action: start, stop, promote, follow, reinitialize, or update state.
8. Publish member status/heartbeat for other agents to observe.

This is a logical description; exact ordering/details depend on the Patroni release and DCS backend.

### 7.2. Leader

The leader node holds the leader lock in the DCS, and PostgreSQL runs as a read-write primary. Patroni continuously checks its ability to retain ownership. If it cannot renew the lock per policy, Patroni may demote/stop PostgreSQL to protect the single-writer invariant.

### 7.3. Replica

A replica is a node in standby/recovery mode following WAL from upstream. Patroni monitors the WAL receiver, replay progress, timeline, and connectivity. If the leader changes, the replica can follow the new leader or be evaluated as a failover candidate.

### 7.4. Candidate

When the leader is no longer valid, eligible replicas can participate in selecting the new primary. Candidates must satisfy eligibility policies and have a suitable WAL position to minimize data loss.

### 7.5. Initializing / Creating Replica

A new node may be bootstrapping or reinitializing from the leader. During this phase it is not yet a healthy replica; do not route application reads to it.

### 7.6. Stopped / Failed

Patroni can detect when PostgreSQL is not running, has crashed, or is unreachable. A node must not be considered a healthy leader merely because an old leader key still sits in the DCS.

### 7.7. Role and Health Are Two Different Questions

- Role: is the node leader/replica according to DCS and PostgreSQL state?
- Health: is the node actually serving queries, streaming/replaying WAL, and meeting latency/SLAs?

The load balancer needs a health endpoint matching its purpose. An "alive" endpoint may return HTTP 200 when a node is not primary; a "primary" endpoint may reject requests when leader ownership is invalid.

## 8. Patroni Configuration

### 8.1. Main Configuration Sections

A Patroni YAML file typically includes these sections:

| Section | Contents |
| --- | --- |
| `scope`, `namespace`, `name` | Cluster identifier, DCS namespace, and node name. |
| `restapi` | Listen/connect address, TLS, and authentication for the REST API. |
| DCS backend | etcd/Consul/ZooKeeper/Kubernetes endpoints and credentials. |
| `bootstrap` | Initial cluster creation, initial dynamic config, initdb, and users. |
| `postgresql` | Listen address, data directory, binaries, authentication, and parameters. |
| `tags` | Eligibility/routing hints such as `nofailover`, `noloadbalance`, `nosync`, `clonefrom`. |

Specific keys depend on Patroni version and backend. Validate the config using the installed tool/version before deploying.

### 8.2. Example Local Configuration for One Node

Illustrative example using etcd v3. Replace hostnames, IPs, paths, users, passwords, and certificate paths:

```yaml
scope: app-ha
namespace: /service/
name: pg-node-a

restapi:
  listen: 10.20.0.11:8008
  connect_address: 10.20.0.11:8008
  authentication:
    username: patroni_api
    password: REPLACE_WITH_SECRET

etcd3:
  hosts:
    - 10.20.0.21:2379
    - 10.20.0.22:2379
    - 10.20.0.23:2379

bootstrap:
  dcs:
    ttl: 30
    loop_wait: 10
    retry_timeout: 10
    maximum_lag_on_failover: 1048576
    postgresql:
      use_pg_rewind: true
      use_slots: true
      parameters:
        wal_level: replica
        hot_standby: "on"
        max_wal_senders: 10
        max_replication_slots: 10
        wal_keep_size: 512MB
  initdb:
    - encoding: UTF8
    - data-checksums
  pg_hba:
    - host replication replicator 10.20.0.0/24 scram-sha-256
    - host all app_user 10.20.0.0/24 scram-sha-256

postgresql:
  listen: 10.20.0.11:5432
  connect_address: 10.20.0.11:5432
  data_dir: /var/lib/postgresql/17/data
  bin_dir: /usr/lib/postgresql/17/bin
  authentication:
    superuser:
      username: postgres
      password: REPLACE_WITH_SECRET
    replication:
      username: replicator
      password: REPLACE_WITH_SECRET
  parameters:
    unix_socket_directories: /var/run/postgresql

tags:
  nofailover: false
  noloadbalance: false
  clonefrom: false
  nosync: false
```

This is a learning configuration, not a complete production file. REST API and PostgreSQL listen addresses must fit your network design. Secrets must be injected from a secret manager or files with restricted permissions.

### 8.3. Configuration Across Nodes

Nodes use the same `scope` and `namespace` to join the same cluster, while `name`, REST API addresses, PostgreSQL addresses, and local data directories must differ. Never copy node A's config verbatim to B/C and forget to change identities.

### 8.4. scope and namespace

`scope` is the logical cluster name. `namespace` defines the prefix/path in the DCS. If two Patroni clusters share a DCS and accidentally use the same scope/namespace, they can collide on metadata and corrupt coordination.

Establish a unique naming convention per environment, such as `prod-orders-eu1` or `staging-orders`, with separate namespaces.

### 8.5. name

`name` is the unique identifier of a member within the cluster. It appears in member records, logs, and `patronictl list`. Never share duplicate names or rename a node arbitrarily while a cluster is running.

### 8.6. restapi listen and connect_address

- `listen`: address/interface the Patroni REST API binds to.
- `connect_address`: address other nodes/health checks use to connect.

The REST API usually uses a dedicated port such as 8008, not the PostgreSQL port. Never expose this endpoint to a public network.

### 8.7. postgresql listen and connect_address

- `listen`: PostgreSQL bind address/interface.
- `connect_address`: endpoint other nodes use for PostgreSQL replication connections.

Keep REST API and PostgreSQL replication addresses distinct. DNS/IPs must be stable and resolve accurately from every node.

### 8.8. data_dir and bin_dir

`data_dir` must point to that node's `PGDATA`. `bin_dir` helps Patroni locate the right PostgreSQL binaries, especially when a host has multiple major versions installed side by side.

Never let two Patroni nodes manage the same data directory. Active-active shared filesystems are not standard physical streaming HA designs.

### 8.9. authentication

Patroni needs credentials for PostgreSQL superuser/admin operations and replication. Separate credentials from application roles. Configure REST API authentication separately; never reuse the same password across the API, PostgreSQL, and DCS.

### 8.10. tags

Certain tags control eligibility or routing policies:

- `nofailover`: node must not be chosen as a failover candidate.
- `noloadbalance`: node should not receive read traffic from the load balancer.
- `nosync`: node must not be chosen as a synchronous standby.
- `clonefrom`: marks a node as eligible to serve as a clone source for replicas in supported configurations.

Tags are policy hints for Patroni/health routing, not firewalls or hard security boundaries. Verify semantics per release.

## 9. Bootstrap and Cluster Initialization

### 9.1. Bootstrap Only Happens When the Cluster Has No State Yet

`bootstrap` describes how Patroni initializes the cluster for the first time. The bootstrapping node creates the data directory, runs `initdb` or the configured bootstrap method, sets up users/`pg_hba`, and writes initial dynamic configuration into the DCS.

Once the cluster is initialized, remaining nodes join by cloning/reinitializing from an eligible member.

### 9.2. bootstrap.dcs

`bootstrap.dcs` holds the initial dynamic configuration. Typical settings include:

- `ttl`, `loop_wait`, `retry_timeout`.
- `maximum_lag_on_failover`.
- `check_timeline`.
- `synchronous_mode`, `synchronous_mode_strict`, `synchronous_node_count`.
- Shared PostgreSQL parameters.
- `use_pg_rewind`, `use_slots`, and other version-dependent policies.

This is an initial seed. Once the cluster exists, editing `bootstrap.dcs` in a local file does not automatically change the dynamic configuration stored in the DCS. Use `patronictl edit-config` or a supported API to change dynamic config.

### 9.3. initdb

Patroni can pass options to `initdb`, such as encoding, locale, and data checksums. Enable checksums at initialization if you want to satisfy that prerequisite for `pg_rewind`; you cannot arbitrarily toggle checksums on an existing cluster without a rebuild/upgrade procedure.

### 9.4. pg_hba in Bootstrap

Patroni can generate/maintain HBA rules per configuration. Ensure replication rules cover node IPs and application rules are appropriate. Verify rule order, TLS requirements, and authentication methods.

### 9.5. Bootstrap Leader

When a cluster has no leader yet, one node wins the bootstrap/leader ownership race via the DCS. That node creates the initial PostgreSQL primary. Other nodes then clone from the leader and start in standby mode.

### 9.6. Never Bootstrap Two Clusters With the Same Scope

If two nodes initialize separate clusters under the same scope/namespace because the DCS was wiped or misconfigured, two incompatible data histories can be created. Before re-bootstrapping, verify DCS state and determine which database data directory is the source of truth.

### 9.7. Clone Methods

Patroni supports replica creation methods such as `pg_basebackup`, pgBackRest, Barman, or custom replica creation methods depending on configuration. Your choice must ensure the standby receives both the base backup and required WAL.

### 9.8. Bootstrapping From a Backup Tool

If using pgBackRest/Barman, Patroni can invoke a custom `create_replica_method` to restore a base backup. Verify:

- The backup set and repository match the right cluster.
- Sufficient WAL exists for recovery.
- Tablespaces map properly.
- Credentials/repository access exist on every node that needs to clone.
- The method returns proper exit codes and logs so Patroni knows the outcome.

### 9.9. Do Not Clone From a Stale Node When a Better Source Exists

A heavily lagging replica or one suffering storage errors may be a poor clone source. Use tags/replica creation policies to select an appropriate source and monitor upstream load.

### 9.10. Post-Bootstrap Verification

Verify:

- `patronictl list` shows one leader and the expected replicas.
- The DCS holds member/leader state.
- PostgreSQL primary/standby roles are correct.
- `pg_stat_replication` and `pg_stat_wal_receiver` are active.
- The REST API returns corresponding roles/health.
- The application endpoint routes writes solely to the leader.

## 10. Dynamic Configuration and patronictl

### 10.1. Local Configuration vs. Dynamic Configuration

Patroni uses two key configuration sources:

- **Local configuration:** node-specific settings such as name, listen/connect addresses, data directory, DCS endpoints, REST API, and credentials.
- **Dynamic configuration:** cluster-wide shared settings stored in the DCS, such as TTL/loop policies, failover policies, synchronous mode, and centrally managed PostgreSQL parameters.

Some settings can only be set locally; others can be managed dynamically. Never assume every YAML key can be edited via `edit-config`.

### 10.2. patronictl list

```bash
patronictl -c /etc/patroni/patroni.yml list
```

Displays member names, roles, states, timelines, lag, and cluster info depending on version. This is the first operational command for inspecting topology; always cross-check PostgreSQL and the DCS during incidents.

### 10.3. patronictl show-config

```bash
patronictl -c /etc/patroni/patroni.yml show-config
```

Displays dynamic configuration currently stored in the DCS. Compare against local files during investigations because changes to local YAML may not apply to dynamic fields.

### 10.4. patronictl edit-config

```bash
patronictl -c /etc/patroni/patroni.yml edit-config
```

Opens an editor to modify dynamic config. Changes must be reviewed, validated, and applied in a controlled manner. Some PostgreSQL parameters require a restart; Patroni can schedule/restart according to policy.

### 10.5. Setting Config From the Command Line

Some versions support:

```bash
patronictl -c /etc/patroni/patroni.yml \
  edit-config --set maximum_lag_on_failover=1048576
```

Check `--help` for your exact release because CLI flags/semantics can change. Do not treat this example as universal across every version.

### 10.6. patronictl reload

```bash
patronictl -c /etc/patroni/patroni.yml reload app-ha
```

Reload instructs Patroni to reload supported configuration without restarting the entire node. Some PostgreSQL parameters require a restart or take effect only on PostgreSQL reload; read the output and check `pending_restart`.

### 10.7. patronictl restart

```bash
patronictl -c /etc/patroni/patroni.yml restart app-ha pg-node-b
```

Restarting a node requires understanding its role and failover policy. Never restart the leader in production without an appropriate HA/switchover plan.

### 10.8. patronictl switchover

Planned switchover transfers leadership to a chosen replica. Confirm the candidate, lag, timeline, and application readiness beforehand. Check the help output and syntax for your version.

### 10.9. patronictl failover

The failover command supports intentional promotion when the leader is unavailable or an operator chooses a node. This is a sensitive operation: execute only after assessing the old primary, fencing, and RPO.

### 10.10. patronictl reinit

Reinitializes a replica by recreating its data directory from upstream/the clone method. It destroys existing local replica data. Confirm the exact member, backup/recovery method, and maintenance window before running.

### 10.11. Never Edit DCS Keys Directly

DCS keys are Patroni's state machine. Manual edits can fabricate leader ownership, delete configs, or mislead nodes about topology. Use `patronictl`/supported APIs; intervene directly in the DCS only under an official recovery runbook.

## 11. Integrating DCS Backends

### 11.1. Dedicated etcd Cluster

For etcd, deploy a cluster of voting members independent from the PostgreSQL nodes. Example with three members:

```text
etcd-a 10.20.0.21:2379
etcd-b 10.20.0.22:2379
etcd-c 10.20.0.23:2379

Patroni nodes -> client endpoints :2379
etcd members -> peer endpoints :2380
```

Default ports can be changed. Client and peer ports carry different traffic flows; firewall rules must permit the appropriate traffic.

### 11.2. etcd Client vs. Peer TLS

etcd can use TLS for client-to-server and peer-to-peer traffic. Patroni needs to trust the CA and hold client credentials matching the etcd endpoint. Peer certificates need SANs matching advertised peer URLs.

Do not enable client TLS while overlooking peer links; etcd members may fail to form quorum.

### 11.3. etcd Quorum Health

Monitor:

- Member count and leader.
- Raft applied/committed index.
- Proposal failures/latency.
- Disk fsync latency.
- DB size/quota alarms.
- Peer network latency and packet loss.
- Snapshot/compaction health.

An etcd endpoint answering a request does not necessarily mean the cluster holds quorum and can commit writes.

### 11.4. etcd Backups

Back up etcd snapshots per official etcd guidelines, store them securely, and test restores. A DCS snapshot does not replace PostgreSQL backups. When restoring the DCS, reconcile cluster metadata against database data histories to avoid restoring a stale leader lock.

### 11.5. Consul Servers and Agents

Consul deploys server agents with quorum and client agents on nodes or network segments. Patroni can connect to Consul servers per backend config. Ensure:

- Server count/quorum is sufficient.
- The ACL token for Patroni has only required permissions on its namespace/prefix.
- Gossip encryption and TLS are configured properly.
- Session TTL/lock delay are appropriate.
- Snapshot/restore and upgrades have runbooks.

### 11.6. Consul Session Semantics

Consul sessions tie lock ownership to session lifecycle/health checks. When a session invalidates or expires, the lock can be released. Agents must handle network partitions and session renewals properly; do not draw conclusions merely from a key's presence.

### 11.7. ZooKeeper Ensemble

ZooKeeper deploys an ensemble with quorum. Patroni connects to ensemble servers; configure session timeout, ACLs/authentication, and TLS per version. Monitor:

- Quorum/leader/follower state.
- Outstanding requests and latency.
- Session expirations/reconnects.
- Transaction log/snapshot storage.
- Disk capacity and compaction/cleanup policies.

### 11.8. Kubernetes API Backend

When using the Kubernetes backend, Patroni agents interact with the Kubernetes API using a service account. Create RBAC roles/bindings scoped to the exact namespace and resources Patroni must manage. Never grant `cluster-admin` without explicit justification.

Some deployments use Endpoints/ConfigMaps or Lease resources depending on Patroni release/backend options. Use the exact schema/permissions from the documentation for your installed version; do not mix YAML across releases.

### 11.9. Kubernetes API Outage

When the API server is unavailable, Patroni cannot update leader state or renew ownership. PostgreSQL pods may keep running and serving existing connections, but orchestration cannot guarantee safe failover. Designing Kubernetes control-plane availability is part of database HA.

### 11.10. Choosing a Backend

Prefer a backend that:

- Has existing operational expertise.
- Has clear quorum/failure domains.
- Has TLS/authn/authz and auditing.
- Has metrics/alerts and backup/restore runbooks.
- Is officially supported by your Patroni version.
- Exhibits stable latency across designed failure domains.

Do not pick a DCS solely because it happens to be installed somewhere without establishing operational ownership.

## 12. Patroni REST API and Health Checks

### 12.1. What Is the REST API Used For?

Each Patroni agent exposes a REST API on the port configured under `restapi`. The API allows:

- Health checks/load balancers to inspect node role.
- Operators to query node/cluster status.
- HA tooling to issue supported administrative operations.
- Monitoring to collect runtime metrics/state.

This API is a sensitive control surface. Expose it only on management networks and enable appropriate authentication/TLS.

### 12.2. Common Health Endpoints

Common endpoints across many Patroni releases:

| Endpoint | Common purpose |
| --- | --- |
| `/health` | Checks basic process/health of the Patroni node. |
| `/primary` | Returns success when the node is primary/leader per Patroni state. |
| `/replica` | Returns success when the node is an eligible replica per endpoint semantics. |
| `/replica?lag=...` | Checks replica and applies a lag threshold if supported by the release. |
| `/read-only` | Node can serve the read-only role. |
| `/read-write` | Node can serve the read-write role. |
| `/leader` | Checks leader status per API semantics. |
| `/liveness` and `/readiness` | Health probes on supported releases. |

Exact endpoint lists, status codes, and semantics must be verified against the REST API documentation of the running Patroni version. Do not treat all endpoints as interchangeable.

### 12.3. Health Endpoints and Routing

A write load balancer should probe the appropriate primary/leader endpoint; a read pool can probe a replica endpoint with a lag threshold. The `/health` endpoint alone is insufficient for write routing because a healthy node may be a standby.

### 12.4. curl Examples

```bash
curl --fail http://10.20.0.11:8008/primary
curl --fail http://10.20.0.12:8008/replica
```

If the REST API requires auth/TLS, supply credentials/certificates per policy. Never use `curl -k` as a production solution because it bypasses certificate verification.

### 12.5. REST API Authentication

Configure username/password or an authentication mechanism supported by your Patroni release. Protect credentials, restrict source access, and enable TLS when traversing untrusted networks. Even read-only status endpoints reveal topology and addresses.

### 12.6. Never Expose the API Publicly

The REST API includes cluster control operations in certain configurations. If an attacker reaches the API with sufficient permissions, they can cause disruption or alter roles. Place the API behind private networks/firewalls, authentication, and auditing.

## 13. Integrating HAProxy and Client Routing

### 13.1. Why Is a Routing Layer Needed?

Applications typically need a stable endpoint even when the primary changes. HAProxy or a similar proxy probes the Patroni REST API and routes write connections to the leader node. Read connections can go to the standby pool.

### 13.2. Example HAProxy Backend for the Primary

```conf
frontend postgres_write
    bind *:5000
    default_backend postgres_primary

backend postgres_primary
    mode tcp
    option httpchk GET /primary
    http-check expect status 200
    default-server inter 3s fall 3 rise 2 on-marked-down shutdown-sessions
    server pg_a 10.20.0.11:5432 check port 8008
    server pg_b 10.20.0.12:5432 check port 8008
    server pg_c 10.20.0.13:5432 check port 8008
```

This is an illustrative template; verify syntax for your HAProxy version. HTTP health checks hit the REST API on port 8008 while PostgreSQL traffic flows over port 5432.

### 13.3. Example Backend for Read Replicas

```conf
frontend postgres_read
    bind *:5001
    default_backend postgres_replicas

backend postgres_replicas
    mode tcp
    balance roundrobin
    option httpchk GET /replica
    http-check expect status 200
    server pg_b 10.20.0.12:5432 check port 8008
    server pg_c 10.20.0.13:5432 check port 8008
```

Do not put the primary into the read pool unless policy permits. If read queries require freshness/consistency, route by lag/`remote_apply` policy rather than blind round-robin.

### 13.4. Controlling Lag

A replica can be in recovery yet lag severely. The `/replica?lag=...` endpoint can exclude replicas exceeding a threshold if supported by your Patroni release. Set thresholds based on workload/RPO; health-check lag does not replace full metrics.

### 13.5. PgBouncer

PgBouncer manages connection pooling, whereas Patroni manages PostgreSQL HA. You can place PgBouncer behind HAProxy or integrate auth/query routing per architecture. PgBouncer does not automatically know the primary changed if the backend behind it stays static; a connection reset/reconnect strategy is required.

### 13.6. VIP and keepalived

Some deployments move a VIP between nodes. Keepalived/VRRP can migrate a network address, but must rely on Patroni role checks and fencing. Standalone VRRP election does not replace DCS leader election; never let a VIP point to two primaries or a node without a leader lock.

### 13.7. DNS and Service Discovery

DNS records have TTL/caching behavior; failover cannot merely update DNS and expect every client to switch instantly. Connection pools can hold old IPs. Use proxies/VIPs or health-aware service discovery endpoints; understand cache TTLs and retry behavior.

### 13.8. Connection Pools After Failover

After promotion, old connections to the former primary may reset or stay open depending on networking/fencing. Applications must:

- Reconnect to the new endpoint.
- Retry transactions idempotently when outcomes are unknown.
- Never blindly retry non-idempotent operations.
- Detect read-only/standby errors and redirect write traffic to the right endpoint.

### 13.9. Separating Read and Write Pools

Dedicated endpoints for writes and reads give clean routing control. The read pool can pick replicas by lag, locality, or workload. The write pool routes only to the node confirmed as leader by Patroni.

### 13.10. Routing Is Not Fencing

HAProxy marking the old primary down only stops traffic flowing through that proxy. Clients can connect directly to the old IP, or another proxy may still route to it. Fencing must block old primary writes at the database/host/network authority layer.

## 14. Synchronous Mode in Patroni

### 14.1. PostgreSQL Synchronous Replication and Patroni Policy

PostgreSQL provides `synchronous_standby_names` and `synchronous_commit`. Patroni can manage these parameters and track synchronous standby membership to align with failover eligibility.

### 14.2. synchronous_mode

The dynamic setting `synchronous_mode` enables Patroni's synchronous replication management. Patroni selects eligible standbys and configures PostgreSQL's synchronous standby policy according to cluster state.

### 14.3. synchronous_mode_strict

Strict mode can preserve the synchronous acknowledgement requirement when no eligible synchronous standby exists, causing writes to block rather than automatically downgrading to asynchronous behavior per policy. This strengthens durability guarantees at the expense of write availability when standbys are unavailable.

Verify semantics and defaults for your Patroni release before enabling.

### 14.4. synchronous_node_count

This setting specifies how many synchronous standbys Patroni requires per policy/release. Higher counts improve redundancy but increase commit latency and dependency on multiple nodes being available.

### 14.5. maximum_lag_on_failover

Sets the maximum lag allowed for a replica to qualify as a failover candidate. The value is typically measured in WAL bytes. It is a guardrail against promoting an overly stale replica, not an exact RPO guarantee under every race/failure.

### 14.6. check_timeline

The timeline checking policy helps Patroni verify that a replica has an appropriate history before promotion. Timeline checks are especially critical after failover/rejoin, when nodes can diverge.

### 14.7. Synchronous Node Tags

The `nosync` tag can exclude a node from synchronous standby selection. Use tags to express policy—for instance, a distant DR node should not sit on the commit path due to high latency.

### 14.8. Synchronous Mode Does Not Eliminate All Data Loss

Durability also depends on:

- The PostgreSQL `synchronous_commit` level.
- Which node actually acknowledged the commit.
- Which candidate is promoted.
- Fencing/leader ownership.
- Whether application transactions use `local`/`off`.
- External side effects outside PostgreSQL.

Do not advertise "zero data loss" without fully verifying all conditions.

### 14.9. Strict Mode and Standby Loss

If strict mode requires a synchronous standby and all standbys disconnect, transactions needing remote acknowledgement can block. This is a deliberate trade-off prioritizing durability. Runbooks must specify who is authorized to temporarily relax the policy during an incident and how to restore it afterward.

### 14.10. Synchronous State in patronictl

`patronictl list`/dynamic config and PostgreSQL's `pg_stat_replication.sync_state` help verify synchronous membership. Compare both because DCS policy and PostgreSQL runtime state can momentarily lag behind each other during state transitions.

## 15. Automatic Failover and Switchover

### 15.1. Automatic Failover

Automatic failover occurs when Patroni determines the leader is no longer healthy/cannot retain ownership per policy. Replica agents exchange state via the DCS, evaluate candidate eligibility, and one node acquires the leader lock and promotes.

A conceptual flow:

```text
Leader A fails to renew leader lock
             |
             v
      Ownership expires
             |
             v
  Replica agents observe DCS state
             |
             v
  Candidate eligibility / WAL position
             |
             v
  One node claims leader ownership
             |
             v
      Promote PostgreSQL
             |
             v
  Publish new leader/member state
             |
             v
  Proxy switches write traffic
```

This is a logical model. Exact election and candidate selection details are implemented by your Patroni release/backend.

### 15.2. Candidate Conditions

A candidate can be disqualified if:

- The node is tagged `nofailover`.
- PostgreSQL is not running or not in an eligible replica state.
- WAL lag exceeds `maximum_lag_on_failover`.
- The timeline does not match the `check_timeline` policy.
- The node cannot reach the DCS or cannot claim ownership.
- Synchronous policy requires another/more eligible node.

Do not treat the geographically closest replica as the best candidate if its WAL history is older.

### 15.3. maximum_lag_on_failover

This setting caps the WAL lag Patroni accepts when considering a replica for promotion. The goal is to avoid promoting an overly stale replica. Its value should reflect:

- Peak WAL generation rate.
- Acceptable RPO.
- Network/storage capacity.
- DCS/election and detection duration.
- Synchronous mode policy.

A fixed byte threshold does not directly translate to time of data loss when WAL generation rates swing sharply.

### 15.4. No Eligible Candidate

If no replica satisfies policy, Patroni may refuse to auto-promote. This is safe behavior when no candidate can be proven close enough to the primary. Operators must decide according to RPO and runbook rather than forcing a blind promotion.

### 15.5. Manual Failover

Manual failover is used when an operator needs to choose a specific candidate or automatic failover cannot complete. Before acting:

1. Determine whether the old primary is alive or dead.
2. Fence the old primary if there is any chance it still accepts writes.
3. Verify DCS quorum/leader state.
4. Compare replica lag and timelines.
5. Select the right candidate.
6. Execute failover via `patronictl`/API per version.
7. Verify the new leader and routing.

### 15.6. Planned Switchover

Switchover transfers leadership while the old primary is still healthy. Patroni can check replicas, wait for WAL synchronization, and coordinate the role transfer on a controlled schedule.

Use switchover for:

- Host/OS maintenance.
- Kernel or storage upgrades.
- Moving the primary to another availability zone.
- Periodic DR/HA drills.

### 15.7. Switchover vs. Failover

| Aspect | Switchover | Failover |
| --- | --- | --- |
| Old primary | Usually healthy and able to cooperate. | May be dead or unreachable. |
| WAL position | Can wait for replica to catch up. | Last primary WAL position may be unknown. |
| RPO | Can approach zero if sync finishes and procedure is followed. | Depends on promoted replica and replication mode. |
| Workflow | Planned/controlled. | Incident response. |
| Goal | Maintenance/role transfer. | Service recovery after an outage. |

### 15.8. Reinitializing a Replica

If a replica has diverged, lacks WAL, or cannot follow the new primary, Patroni can reinitialize it using the clone method. Reinitializing overwrites the replica's local data directory. Execute only on the right member after confirming source/backups.

### 15.9. Failover Does Not Mean Traffic Has Switched

After PostgreSQL promotes, applications may still connect to the old endpoint. Proxies/VIPs/DNS/service discovery and connection pools must handle the role change. Measure RTO until application-ready, not merely until promotion finishes.

### 15.10. Patroni Does Not Resolve Unknown Transaction Outcomes

If a client loses connection right at `COMMIT`, the client may not know whether the transaction committed on the old primary. Applications need idempotency keys or business-state queries before retrying to avoid duplicate payments/orders/events.

## 16. DCS Outage, Network Partition, and Failsafe

### 16.1. Losing One DCS Member

In a quorum-based DCS, losing one member still allows writes to continue if a majority remains operational. For instance, a 3-member etcd cluster can continue when one member fails. Repair the failed member promptly before losing another.

### 16.2. Losing Quorum

When the DCS loses quorum, it cannot commit coordination writes. Patroni cannot renew leader ownership through the normal mechanism. Automatic failover may stall because there is no shared authority to grant new leadership.

### 16.3. Primary Still Running During a DCS Outage

The PostgreSQL process on the primary may keep running and existing clients may stay connected. However, safe write serving depends on Patroni's leader lock/failsafe behavior and policy. Never infer "the database answers queries, so the primary is still valid."

### 16.4. failsafe_mode

Some Patroni versions provide `failsafe_mode` to handle certain DCS-unavailable situations. When enabled, the leader may continue operating if it meets inter-member communication/consensus conditions under Patroni's failsafe mechanism, typically via REST API member checks.

This is a special policy, not a way to bypass the DCS. Read the documentation for your exact release, verify network reachability requirements, and test partition scenarios before enabling.

### 16.5. Never Handle a DCS Outage by Deleting the Leader Key

Manually deleting the leader key while the primary is still running can let another node claim leadership while the old primary is unfenced. Use official recovery procedures only after verifying the state of all nodes.

### 16.6. Network Partition Between Database Nodes

One node may reach the DCS while losing access to the primary; another may reach the primary while losing the DCS. Analyze the full connectivity matrix, not just ping from a single host.

### 16.7. Network Partition Between Patroni and PostgreSQL

Patroni can lose its SQL connection to PostgreSQL while the process keeps running. Check process health, sockets, disk stalls, and the leader lock. Patroni may stop/restart the process per policy; avoid killing PostgreSQL manually before understanding recovery state.

### 16.8. Network Partition Between DCS Members

The DCS consensus protocol dictates which partition can commit. A minority partition must never grant new leader ownership. Monitor quorum and never run two independent DCS clusters under the same Patroni scope.

### 16.9. Failsafe and Watchdog Are Two Different Layers

Failsafe mode defines Patroni's behavior during a DCS outage under its conditions. Watchdog/fencing forces a node to stop acting as leader when it cannot prove ownership. The two layers complement each other; neither replaces quorum or infrastructure fencing.

### 16.10. Runbook When the DCS Loses Quorum

1. Do not delete DCS keys or re-bootstrap the cluster.
2. Check member status, logs, network, disks, and quorum.
3. Determine whether the primary still holds valid ownership.
4. Preserve the single-writer invariant; do not promote standbys arbitrarily.
5. Restore DCS quorum per the backend-specific runbook.
6. Once the DCS stabilizes, check Patroni leader/member state and PostgreSQL roles.
7. Verify replication and routing before opening broad traffic.

## 17. Fencing and Watchdog

### 17.1. Why Does a Leader Lock Need Fencing?

A DCS lease only governs ownership in the control plane. If the old primary is paused or partitioned yet can still write to local storage and accept client traffic, DCS lease expiration does not automatically stop it. Fencing guarantees the old primary cannot continue acting as writer after authority transfers to another node.

### 17.2. Patroni Watchdog

Patroni can integrate with a watchdog to reset the node if it fails to renew the leader lock within a safe boundary. A watchdog bounds how long a node can keep running after losing ownership.

### 17.3. Hardware Watchdog

A hardware watchdog is provided by host/firmware. Patroni can open the watchdog device and trigger a system reset if keep-alives stop arriving on time. Verify driver, permissions, device path, and actual reset behavior.

### 17.4. Software Watchdog

A software watchdog may use kernel/system service mechanisms depending on the platform. It may not protect against every kernel/host failure the way a hardware watchdog does. Verify the failure model and test in a disposable environment.

### 17.5. watchdog.mode

Patroni releases offer watchdog modes such as `off`, `automatic`, and `required` depending on version. `required` mode can prevent a node from starting/holding leadership if the watchdog is not working properly; `automatic` has different fallback behavior. Check release semantics before configuring.

### 17.6. Watchdog Safety Margin

Watchdog timeout and Patroni `ttl`/`loop_wait`/`retry_timeout` must be coordinated. If the watchdog timeout is longer than the leader lease safety window, the node can keep running too long after losing ownership. If too short, normal scheduler pauses/network jitter can trigger unwanted resets.

### 17.7. Fencing Outside Patroni

At the infrastructure layer, fencing can include:

- Stopping the old VM/instance.
- Powering off the node via out-of-band management.
- Revoking storage write access.
- Network isolation from application clients.
- Detaching the volume from the old primary.

Use only methods with verifiable outcomes. Sending a stop command across a partitioned network without confirmation is not reliable fencing.

### 17.8. Testing Fencing

Drill at least:

- Patroni process dies while PostgreSQL keeps running.
- Node paused longer than TTL.
- DCS partition.
- Host loses management network connectivity.
- Watchdog device missing.
- Proxy switches traffic while old primary remains directly reachable.

The goal is to prove two concurrent writers cannot exist.

## 18. Kubernetes and PostgreSQL Orchestration

### 18.1. Two Orchestration Layers Can Coexist

In Kubernetes, you may have:

- The Kubernetes control plane managing Pods, StatefulSets, Services, PersistentVolumes, and scheduling.
- Patroni managing PostgreSQL roles, leader lock, replication, and database failover.
- A PostgreSQL operator managing the Patroni cluster lifecycle via Custom Resources.

Each layer has distinct responsibilities. A Pod restart does not automatically mean the PostgreSQL role is safe; Patroni leader election does not automatically provision PersistentVolumes or Service routing.

### 18.2. Patroni Running Inside Pods

Some architectures run a Patroni sidecar/agent alongside the PostgreSQL container inside each Pod. Patroni manages the PostgreSQL process in the container and uses the configured DCS backend (which may be the Kubernetes API). Pod identity and storage identity must be stable by design.

### 18.3. Kubernetes Service for the Primary

A Service can select Pod labels updated according to role. However, label updates must rely on trustworthy Patroni state and allow propagation time. Never let two Pods carry the primary label during a failover.

### 18.4. Readiness and Liveness Probes

- Liveness checks whether the container/process needs restarting.
- Readiness decides whether the Pod receives traffic via the Service.
- Patroni REST role endpoints verify whether the node is an eligible primary/replica.

Never use a plain TCP probe to the PostgreSQL port as a primary health check; standbys also listen on the PostgreSQL port.

### 18.5. StatefulSet Is Not Leader Election

A StatefulSet provides stable ordinal/network identity and volume binding. It does not choose the PostgreSQL primary on its own. Replica roles and leader ownership are handled by Patroni/DCS or the operator.

### 18.6. PersistentVolumes

Each PostgreSQL node needs dedicated storage with an independent lifecycle. When a Pod reschedules, its volume reattaches per policy. Never mount the same `PGDATA` read-write into multiple PostgreSQL instances as an HA shortcut.

### 18.7. Operators and Patroni

PostgreSQL operators may use Patroni internally for HA, or use a different architecture. An operator typically manages:

- Custom Resources/desired state.
- Pod/StatefulSet/Service lifecycle.
- Backup/restore integration.
- Certificates/secrets.
- Upgrades and configuration rollouts.
- Monitoring/maintenance windows.

Before deploying standalone Patroni inside an operator-managed cluster, establish clearly who controls the PostgreSQL lifecycle. Never let two controllers simultaneously start/stop/promote the same instance.

### 18.8. RBAC for Kubernetes DCS

Patroni's service account should receive only the permissions required on the namespace/resources used by its backend. Never grant `cluster-admin` by default. Separate operator/controller permissions from Patroni agent permissions whenever possible.

### 18.9. Kubernetes API Outage

If the API server or control plane is unavailable, Pods and PostgreSQL processes may keep running, yet Patroni cannot update DCS ownership. That impacts failover. Monitor control-plane health as a dependency of database HA.

### 18.10. Never Stack Multiple Leader Elections

If a Kubernetes operator, Patroni, keepalived, and a custom script all attempt to decide the primary, controllers can issue conflicting decisions. Pick one authority for database leader election and design other layers solely to consume that state.

## 19. Configuration Changes and Lifecycle Operations

### 19.1. Changing Dynamic Config

Edit dynamic config with `patronictl edit-config` or a supported API. Before applying:

1. Export/save the current config.
2. Identify which parameters are dynamic and which require a restart.
3. Check constraints among TTL, `loop_wait`, and `retry_timeout`.
4. Assess impact on synchronous replication/failover.
5. Apply during a maintenance/change window if needed.
6. Verify runtime state on every node.

### 19.2. Changing Local Config

Node-specific fields such as listen/connect addresses, `data_dir`, DCS endpoints, and REST API settings typically live in local config. Changes may require reloading/restarting Patroni. Ensure nodes do not lose DCS connectivity or accidentally change identity.

### 19.3. PostgreSQL Parameter Changes

Some PostgreSQL parameters need only a reload; others require a restart. Patroni tracks dynamic PostgreSQL parameters and may flag a restart requirement. Check `pending_restart`, `pg_settings.context`, and Patroni output before acting.

### 19.4. Rolling Restart

For replicas:

1. Restart replicas one at a time.
2. Wait for the replica to resume streaming and catch up.
3. Advance to the next node only when the topology has enough redundancy.
4. Avoid restarting all standbys at once.

For the leader, consider a planned switchover before restarting to reduce downtime.

### 19.5. PostgreSQL Minor Upgrades

Minor upgrades within the same major version normally swap binaries/packages and restart nodes via a rolling plan. Check compatibility and release notes. Keep at least one healthy replica throughout the rolling upgrade.

### 19.6. PostgreSQL Major Upgrades

Major upgrades require a dedicated procedure because the physical data format changes. Patroni does not turn a major upgrade into a routine package update. Plan with `pg_upgrade`, logical migration, or a vendor/operator-supported method; test rollback and replication topology.

### 19.7. Patroni Upgrades

Upgrading Patroni versions can change DCS backend APIs, config validation, REST API, and failover behavior. Read release notes, check compatibility with PostgreSQL/DCS, test in staging, and perform a rolling upgrade per documentation.

### 19.8. DCS Upgrades

A DCS upgrade is an independent operation that can affect quorum. Execute a rolling upgrade per backend guidelines, monitor member health, and avoid upgrading multiple voting members simultaneously.

### 19.9. Node Maintenance

Before shutting down a node:

- Check its role.
- If it is the leader, perform a planned switchover.
- Confirm remaining replicas and DCS quorum are sufficient.
- Ensure backups/WAL archiving are working.
- Perform maintenance.
- Start the node, verify role/replication, and check routing.

### 19.10. Changing DCS Endpoints

Changing DCS endpoints can cause all Patroni agents to lose coordination if rolled out improperly. Ensure the new backend holds accurate cluster state or follow an official migration procedure. Never point production nodes at an empty DCS.

## 20. Backup, Restore, and Disaster Recovery for a Patroni Cluster

### 20.1. Two Types of Data Must Be Protected

1. **PostgreSQL data:** base backups, WAL archives, tablespaces, configs, extensions, and external dependencies.
2. **DCS/control-plane state:** dynamic configuration, cluster metadata, and backend-specific state.

They have different lifecycles and consistency requirements.

### 20.2. Patroni Does Not Back Up the Database Automatically

Use pgBackRest, Barman, `pg_basebackup`, or an appropriate backup tool. Configure continuous WAL archiving with sufficient retention for PITR. Test backups from primary/standbys as supported by your tool.

### 20.3. DCS Snapshots Are Not Database Backups

etcd/Consul/ZooKeeper snapshots only protect coordination state. They contain no PostgreSQL table data. Conversely, a PostgreSQL base backup does not automatically preserve DCS leader metadata.

### 20.4. Restoring a PostgreSQL Cluster

Restore database data following your backup tool and PostgreSQL recovery procedures. Then configure Patroni to manage the restored data directory/cluster identity properly. Avoid letting Patroni bootstrap a brand-new cluster over a data directory containing data to recover.

### 20.5. Restoring the DCS

Restore the DCS per backend documentation. Before allowing Patroni agents to run:

- Verify cluster scope/namespace.
- Verify the leader key/lease is not stale or pointing to an old node.
- Reconcile member records with PostgreSQL roles/timelines.
- Ensure no other primary is accepting writes.
- Follow the official Patroni/DCS recovery runbook.

### 20.6. Never Arbitrarily Restore DCS and PostgreSQL Independently Without Reconciliation

A DCS snapshot from time T1 and a PostgreSQL restore from time T2 may not match the same topology/leader/timeline. Maintain a manifest recording timestamps, scope, system identifier, timeline, and backup IDs for reconciliation.

### 20.7. DR in Another Region

You can place an asynchronous standby in a DR region and design DCS quorum/control plane accordingly. If the DCS resides solely in the primary region and that region is completely lost, DR Patroni may lack quorum to promote. Design control-plane/witness/DR procedures for decisive action in a region-loss scenario.

### 20.8. Do Not Stretch DCS Quorum Across a WAN Without Measuring

Quorum members across distant regions raise the RTT of every DCS write and inflate failover/renewal latency. Trade off locality, quorum survival, and WAN failures. Design per backend recommendations and measure network behavior.

### 20.9. Backup Restore Drills

Verify:

- Restoring a base backup onto a new host.
- Replaying WAL to a recovery target.
- Initializing Patroni management under the right scope/namespace.
- Rebuilding replicas.
- Restoring routing.
- Testing app roles/permissions and business invariants.
- Measuring actual RTO/RPO.

### 20.10. Immutable Backups

Replication and the DCS do not protect against ransomware or compromised credentials. Store backup copies in an independent account/storage failure domain with immutability/object lock where appropriate, encryption, and access auditing.

## 21. Security and Hardening

### 21.1. Network Segmentation

Isolate or restrict traffic flows:

- PostgreSQL client traffic.
- PostgreSQL replication traffic.
- Patroni REST API.
- DCS client traffic.
- DCS peer traffic.
- Backup repository access.
- Monitoring/admin access.

Open only required sources/destinations/ports.

### 21.2. DCS Credentials

Use etcd client certificates/authentication, Consul ACL tokens, ZooKeeper ACLs/authentication, or Kubernetes service accounts/RBAC. Never allow anonymous write access to the Patroni namespace.

### 21.3. DCS Namespace Isolation

Each Patroni cluster should have its own scope/namespace. DCS permissions must be scoped to that cluster's prefix/resources. One cluster should never have permission to modify another cluster's metadata.

### 21.4. Patroni REST API

Enable authentication and TLS as needed. Restrict access to HAProxy/monitoring/admin networks only. Never publicly expose an endpoint capable of controlling the cluster.

### 21.5. PostgreSQL Replication Role

Use a dedicated role with `REPLICATION` and restrict HBA source addresses. Manage and rotate passwords per policy. Because the replication role can pull base backups, treat it as sensitive data access.

### 21.6. Secrets Distribution

Inject secrets via a secret manager/Kubernetes Secrets with encryption at rest, strict filesystem permissions, and a rotation plan. Avoid writing passwords into Git, container images, logs, or command lines.

### 21.7. TLS Certificate Rotation

Certificate expiration or CA rotation can break DCS/replication/API connections all at once. Roll out CA trust first, then rotate leaf certificates, verify every node, and keep a rollback window.

### 21.8. OS Privileges

Run PostgreSQL under a dedicated OS account. Patroni needs permission to control the PostgreSQL service and access the watchdog device per deployment; avoid running as full-time root when scoped systemd permissions/sudo rules work.

### 21.9. Auditing

Maintain an audit trail for:

- Dynamic configuration changes.
- Manual failovers/switchovers.
- DCS snapshots/restores.
- Node reinitializations/rewinds.
- REST API administrative calls.
- Credential/certificate rotations.
- HAProxy/Service routing changes.

### 21.10. Supply Chain

Pin Patroni/DCS/PostgreSQL versions, verify packages/images, monitor security advisories, and upgrade through staging. Never use untrusted container images for the database control plane.

## 22. Monitoring and Observability

### 22.1. Monitor All Layers

An HA dashboard must aggregate:

1. PostgreSQL data plane.
2. Patroni orchestration state.
3. DCS quorum/health.
4. Client routing.
5. Backup/recovery.

Monitoring only the PostgreSQL port does not tell you whether the DCS has quorum or Patroni holds a valid leader lock.

### 22.2. PostgreSQL Metrics

Track:

- Primary/standby role via `pg_is_in_recovery()`.
- `pg_stat_replication` and `pg_stat_wal_receiver`.
- Sent/write/flush/replay LSN and lag.
- WAL generation rate and `pg_wal` disk usage.
- Replication slot retained WAL.
- Checkpoints, I/O, CPU, memory, and connection saturation.
- Recovery conflicts on standbys.
- Synchronous wait/commit latency.

### 22.3. Patroni Metrics and API

Collect data from the Patroni REST API/metrics endpoint per version and exporter:

- Member role/state.
- Leader lock/leader name.
- HA loop duration and failures.
- DCS access errors/latency.
- PostgreSQL process state.
- Replica lag/candidate eligibility.
- Synchronous mode state.
- Pending restart/config changes.
- REST API request failures.

Exact metric names depend on the Patroni release/exporter. Do not hardcode metric names from another version without verifying.

### 22.4. DCS Metrics

For etcd:

- Quorum/member health.
- Raft leader changes.
- Proposal latency/failures.
- Disk fsync/backend commit latency.
- Database size/quota.
- Peer RTT/traffic.

For Consul:

- Server quorum/leader.
- Raft apply/commit latency.
- Session expiration/lock behavior.
- ACL/TLS errors.
- Agent/server health.

For ZooKeeper:

- Ensemble quorum and leader/follower.
- Request latency/queues.
- Session expiration.
- Transaction log/snapshot storage.

For Kubernetes:

- API server availability/latency.
- Request throttling/errors.
- Service account authorization failures.
- Control-plane etcd health.

### 22.5. Routing Metrics

Monitor HAProxy backend state, active sessions, health check failures, queue depth, and connection errors. Verify the write endpoint has only one healthy backend at a time.

### 22.6. Backup Metrics

Track:

- Last successful base backup.
- WAL archive success/lag.
- Backup verification/restore test age.
- Repository capacity.
- Retention/immutability status.
- PITR target coverage.

### 22.7. Alert Severity

| Severity | Examples |
| --- | --- |
| Critical | No writable leader, split-brain suspicion, DCS quorum lost, `pg_wal` nearly full. |
| High | Synchronous standby unavailable, replica lag exceeding RPO, prolonged backup/WAL archive failures. |
| Medium | One DCS member down while quorum holds, replica reconnects, slow HA loop. |
| Low | Certificate nearing expiration, pending planned restart, backup/restore drill due soon. |

Specific thresholds must be grounded in RPO/RTO, workload, and backend baselines.

### 22.8. Log Correlation

Synchronize clocks across database nodes, DCS members, proxies, and orchestration hosts. Use cluster scope, node name, timeline, LSN, leader changes, and incident IDs to correlate logs.

### 22.9. Alert Fatigue

Do not alert on every brief replica reconnect if that is normal behavior. Alerts must reflect impact: lost quorum, lost leader, lag breaching SLA, growing WAL retention, or an app write endpoint with no backend.

### 22.10. Minimum Dashboard

An operational dashboard should display:

- Current topology diagram and leader.
- DCS quorum status.
- PostgreSQL roles and replication state.
- Lag in bytes/time per replica.
- WAL slot/archive retention.
- HAProxy primary/read backends.
- Backup/WAL archive freshness.
- Actual RPO/RTO from restore/failover drills.

## 23. Failure Scenarios and Handling

### 23.1. PostgreSQL Primary Crash

Patroni detects PostgreSQL is unhealthy, and DCS/HA policy governs leader ownership. If an eligible candidate exists, a replica is promoted. Verify fencing, WAL lag, new timeline, and routing.

### 23.2. Primary Host Power Loss

The node stops renewing its lock. Once the lease expires, a replica can be promoted per policy. When the host returns, never start the old PostgreSQL read-write; rejoin via rewind/rebuild.

### 23.3. Primary Partitioned From DCS While Still Serving Clients

This is a dangerous scenario. Patroni must fail closed/demote or use a well-engineered failsafe policy. If another node promotes while the old primary still accepts writes, split-brain can occur. Watchdog/fencing and partition testing are required.

### 23.4. DCS Loses One Member

While quorum holds, the cluster can continue. Repair the failed member and check Raft/ensemble health; do not wait until quorum is lost.

### 23.5. DCS Loses Quorum

There is no authority to grant new leader ownership. Preserve the single-writer invariant, restore backend quorum, and check leader state and PostgreSQL roles before allowing failover.

### 23.6. DCS Leader Changes

A DCS consensus leader election can happen without a PostgreSQL primary change. Monitor the two leader concepts separately: the DCS consensus leader and the Patroni/PostgreSQL leader. They are distinct concepts.

### 23.7. Patroni Agent Dies While PostgreSQL Keeps Running

The PostgreSQL process may continue running briefly, yet the node is no longer managed by the HA loop. Watchdog/fencing policies must address this case. Do not arbitrarily kill/restart before knowing whether the node holds a valid leader lock.

### 23.8. Severe Replica Lag

Inspect network, WAL sender, disk replay throughput, slot retention, and recovery conflicts. If lag exceeds `maximum_lag_on_failover`, the node may lose candidate eligibility. Resolve the lag or reinitialize per policy.

### 23.9. Replica Missing a WAL Segment

If the segment is gone from the primary and missing from the archive, the replica cannot resume from its current position. Reinitialize from a fresh base backup.

### 23.10. REST API Unavailable

HAProxy health checks or monitoring may mark a node down even though PostgreSQL is still running. Check the Patroni process, listen/connect addresses, firewall, TLS, authentication, and DCS. Never infer the database is dead solely from an HTTP failure.

### 23.11. HAProxy Still Routes to the Old Primary

Check health-check endpoints, REST API port, expected status codes, server check intervals, and session shutdown settings. Verify the old primary is fenced; do not rely solely on proxy state.

### 23.12. Synchronous Commits Blocked

Check `synchronous_standby_names`, `sync_state`, standby network/storage latency, and synchronous strict mode policy. Decide whether to wait, restore a standby, or temporarily adjust durability policy under incident authorization.

### 23.13. DCS Disk Full

The DCS may reject writes or fail to commit proposals. Check quota/backend size, compaction/defragmentation procedures, free disk space, and logs. Never arbitrarily delete Patroni keys to free space.

### 23.14. Expired Certificates

DCS, Patroni REST API, or replication connections can fail simultaneously. Check expiry, trust chains, SAN/hostnames, and clocks. Roll out trust/certificates in order and verify every connection.

### 23.15. DCS Restored From an Old Snapshot

An old snapshot may contain leader metadata/leases that no longer match current PostgreSQL timelines. Keep the cluster isolated, reconcile DCS state with database nodes, and follow an official recovery procedure before allowing Patroni agents to orchestrate.

### 23.16. Database Restored While DCS Points to Another Node

This is a control-plane/data-plane mismatch. Establish the source of truth, fence writers, fix topology per runbook, and never let two nodes both believe they are primary.

### 23.17. Manual pg_ctl promote Outside Patroni

Promoting PostgreSQL directly while Patroni manages the node desynchronizes DCS role state. Perform promotions through Patroni/`patronictl`/HA manager per procedure. If a node was promoted outside management, isolate and reconcile immediately.

### 23.18. Pod Rescheduled

Kubernetes may restart a Pod or attach its volume on another node. Verify volume identity, Patroni config, DCS member state, and PostgreSQL role. Never allow both an old Pod and a new Pod to mount/write the same `PGDATA`.

### 23.19. Primary Restarts During a DCS Outage

The node may fail to start or fail to acquire leader ownership. Never bypass Patroni by manually starting PostgreSQL to accept writes. Restore DCS/ownership or follow an emergency runbook with fencing.

### 23.20. Entire Region Lost

Evaluate where DCS quorum remains, how far DR standby WAL has reached, whether backups/WAL archives are intact, and who has authority to promote. Fence the old region in case it returns. Route clients to DR after promotion and business validation.

## 24. Lab 1: Building a Patroni Cluster With etcd in a Disposable Environment

This lab describes a three-PostgreSQL-node and three-etcd-member topology. Use dedicated lab VMs/containers; never deploy onto production.

### 24.1. Diagram

```text
PostgreSQL/Patroni:
  pg-a 10.20.0.11:5432 / REST 8008
  pg-b 10.20.0.12:5432 / REST 8008
  pg-c 10.20.0.13:5432 / REST 8008

etcd:
  etcd-a 10.20.0.21:2379
  etcd-b 10.20.0.22:2379
  etcd-c 10.20.0.23:2379

Application:
  HAProxy :5000 (writes)
  HAProxy :5001 (reads)
```

### 24.2. Prepare the DCS

Initialize a three-member etcd cluster per etcd documentation. Configure peer/client URLs, unique member names, separate data directories, TLS/authentication, and firewalls. Confirm quorum and health before starting Patroni.

### 24.3. Install PostgreSQL and Patroni

On each PostgreSQL node:

- Install the same PostgreSQL major version.
- Install the chosen Patroni version.
- Create the OS user and data directory.
- Configure PostgreSQL binary/data paths.
- Configure networking/firewalls for replication and the REST API.
- Prepare secret files.

### 24.4. Write Node-Specific Configs

Create a dedicated local config for each node. Share `scope`/`namespace`/DCS cluster; vary `name`, listen/connect addresses, and `data_dir`. Use the configuration section example as a template, adding DCS TLS credentials and PostgreSQL HBA rules.

### 24.5. Bootstrap One Node

Start Patroni on the node chosen as bootstrap candidate. Watch logs, DCS state, and PostgreSQL `initdb`. Confirm the node holds the leader lock and PostgreSQL runs read-write.

### 24.6. Join Two Replicas

Start Patroni on the remaining two nodes. They should detect the existing cluster, clone from the leader using the configured method, and start as standbys. Verify WAL receiver and replication state.

### 24.7. Inspect the Cluster

```bash
patronictl -c /etc/patroni/patroni.yml list
patronictl -c /etc/patroni/patroni.yml show-config
```

Expect one leader and two replicas. Verify directly on PostgreSQL:

```sql
SELECT pg_is_in_recovery();
```

The leader returns `false`; replicas return `true`.

### 24.8. Create a Test Table

On the leader:

```sql
CREATE TABLE public.patroni_lab (
    id bigint PRIMARY KEY,
    note text NOT NULL
);

INSERT INTO public.patroni_lab
VALUES (1, 'created-on-leader');
```

Read on replicas after replay. Do not write to replicas.

### 24.9. Save a Baseline

Record:

- DCS quorum/member health.
- Leader name and lock state.
- Replica lag.
- WAL generation rate.
- HA loop timing.
- REST API endpoints.
- Application write/read endpoints.

### 24.10. Clean Up the Lab

Stop lab Patroni/PostgreSQL/etcd in the planned order. Delete only data directories, DCS data, and test tables belonging to the disposable lab. Never run cleanup against production.

## 25. Lab 2: Health Checks and HAProxy Routing

### 25.1. Check the REST API Directly

```bash
curl --fail http://10.20.0.11:8008/primary
curl --fail http://10.20.0.12:8008/replica
curl --fail http://10.20.0.13:8008/replica
```

Substitute your lab node addresses. Add credentials/certificates if the API uses auth/TLS.

### 25.2. Configure HAProxy

Use the primary/read backend examples from Section 13. Configure separate frontend ports and REST API health-check ports. Validate the HAProxy config with the appropriate tool before reloading.

### 25.3. Test the Write Endpoint

Connect to the HAProxy write port:

```bash
psql -h haproxy-lab -p 5000 -U app_user -d appdb
```

Verify which server is selected using `inet_server_addr()` and `pg_is_in_recovery()`.

### 25.4. Test the Read Endpoint

Connect to the read port, run a `SELECT`, and confirm the node is a standby in recovery. The read pool must exclude nodes that fail policy checks.

### 25.5. Observe Failover Routing

Perform a planned switchover in the lab. Watch HAProxy backend state transition from the old leader to the new leader. Verify client reconnect and session reset behavior.

### 25.6. Limitations

A passing health check does not prove the old primary was fenced. Attempt a direct connection to the old primary after switchover/failover to verify fencing/role transition.

## 26. Lab 3: Planned Switchover

### 26.1. Pre-Checks

Before switchover:

- One leader and at least one healthy replica.
- Sufficient DCS quorum.
- Replica candidate has caught up or lag is within policy.
- Backups/WAL archiving healthy.
- HAProxy/API health checks working.
- Rollback/recovery plan ready.

### 26.2. Execute Switchover

Use `patronictl switchover` with syntax matching your release. Explicitly select the old leader and new candidate if prompted by the CLI. Confirm the prompts and maintenance window.

### 26.3. Verify Post-Switchover

```bash
patronictl -c /etc/patroni/patroni.yml list
```

Confirm the new node is leader, the old node is replica, and replication state is stable. Verify the write endpoint routes to the new leader.

### 26.4. Verify Data

Compare test rows/transaction markers on the new primary and replicas. Run application smoke tests and verify unknown `COMMIT` handling.

### 26.5. Record RTO

Measure time from starting the switchover until application writes/reads work normally through the stable endpoint. Record downtime and connection errors.

## 27. Lab 4: Failover and Rejoining the Old Primary

This lab requires a disposable cluster with at least two PostgreSQL nodes. Never run kill/power-off experiments on production.

### 27.1. Record Pre-Failover State

Save:

- Leader name.
- Replica receive/flush/replay LSN.
- DCS member/leader state.
- Synchronous state.
- Current timeline.
- HAProxy backend health.

### 27.2. Simulate Failure

In the lab environment, stop the primary via Patroni-managed means or controlled fault injection. Observe Patroni logs and the DCS lock transition.

### 27.3. Confirm Promotion

An eligible replica is promoted per policy. Check `patronictl list`, `pg_is_in_recovery()`, and PostgreSQL logs. Only one leader exists.

### 27.4. Verify Routing

Connect through the write endpoint and confirm it routes to the new primary. Verify the old primary does not accept writes.

### 27.5. Rejoin the Old Primary

If the old node diverged, use Patroni reinitialize/`pg_rewind` per policy and preconditions. If rewind is impossible, clone a new base backup. Never start the old primary read-write.

### 27.6. Verify Cluster Stability

Expect one leader and streaming replica(s). Inspect timelines, slots, WAL retention, lag, and routing.

### 27.7. Record Results

Record detection time, DCS election time, promotion time, client routing time, data loss/uncertainty, and rejoin duration. This establishes your RTO/RPO baseline.

## 28. Lab 5: DCS Outage and Quorum

### 28.1. Use a Disposable DCS

Test only on a lab etcd/Consul/ZooKeeper cluster. Identify clearly which members can be stopped and whether quorum remains.

### 28.2. Lose One Member

Stop one DCS member. Confirm the remaining majority retains quorum and Patroni agents continue reading/renewing state as designed. Restart the member and observe catch-up.

### 28.3. Lose Quorum

In the lab, isolate enough DCS members to lose majority. Observe logs and Patroni behavior. Never manually delete the leader key or promote a replica by hand.

### 28.4. Restore Quorum

Restore networking/member state per backend procedure. Confirm DCS quorum before inspecting Patroni leader/member records.

### 28.5. Compare Database and DCS Health

During a DCS outage, the PostgreSQL process may keep running. Check database health and control-plane health separately; never treat query success as proof that safe failover is possible.

### 28.6. Failsafe Mode

If the lab enables `failsafe_mode`, repeat the scenario and observe REST API member reachability conditions. Document the exact behavior of your Patroni version; never enable it in production just because the lab looked fine.

## 29. Lab 6: Dynamic Configuration and Restart Policy

### 29.1. Inspect Dynamic Config

```bash
patronictl -c /etc/patroni/patroni.yml show-config
```

Note TTL, `loop_wait`, `retry_timeout`, failover lag, and PostgreSQL parameters.

### 29.2. Change a Safe Value in the Lab

Use `patronictl edit-config` to change an identified lab setting. Avoid changing TTL/`loop_wait` arbitrarily without understanding constraints.

### 29.3. Verify Saved Config

Run `show-config` and inspect each node. Compare dynamic config against local YAML.

### 29.4. Check Pending Restart

Check Patroni output or PostgreSQL `pg_settings.pending_restart` to see whether the parameter requires a restart. Never perform an unplanned leader restart.

### 29.5. Rollback

Restore the previously recorded config via `edit-config`. Confirm agents picked up the value and PostgreSQL runtime state matches.

## 30. Lab 7: Observing DCS and Patroni API

### 30.1. REST API

Call `/health`, `/primary`, and `/replica` on each node and record status codes. Confirm the primary endpoint succeeds only on the leader and the replica endpoint succeeds only on eligible nodes per version.

### 30.2. DCS State

Use official backend tools to read health/member state. Avoid writing/editing keys. Record revision/term/session/lease metadata as needed.

### 30.3. Correlate State

Compare:

- Patroni node name/role.
- DCS leader/member state.
- PostgreSQL `pg_is_in_recovery()`.
- `pg_stat_replication`.
- HAProxy backend state.

Every layer must reflect the same single-writer topology.

### 30.4. Auditing

Execute a dynamic config change and a planned switchover in the lab. Verify logs/audit trails show who acted, when, and the outcome.

## 31. Common Mistakes

### 31.1. Thinking Streaming Replication Automatically Creates HA

Replication only transfers/replays WAL to standbys. It does not solve failure detection, leader ownership/election, fencing, client routing, backups, and rejoining. Orchestration and operational runbooks are required.

### 31.2. Running Patroni Without a Healthy DCS

Patroni depends on the DCS to coordinate leader/member/config state. A DCS without quorum can block safe failover. Monitor the DCS as a critical dependency.

### 31.3. Treating the DCS as Database Storage

The DCS only stores coordination metadata/configuration. It contains no table rows/WAL and does not replace PostgreSQL backups.

### 31.4. Placing All DCS Members on the Same Host

A single host failure can wipe out quorum. Distribute members across appropriate failure domains while weighing latency and network partitions.

### 31.5. Pointing Two Independent DCS Clusters at the Same Patroni Scope

Two control planes can hold conflicting leader states. Ensure all Patroni agents of a cluster use exactly one DCS authority and namespace.

### 31.6. Confusing the DCS Leader With the PostgreSQL Leader

etcd/Consul/ZooKeeper have a consensus protocol leader; a Patroni cluster has a PostgreSQL primary. Those are two different leaders.

### 31.7. Overly Short TTL

Network jitter, CPU pauses, or DCS latency can prevent timely leader renewal, causing unnecessary demotions/failovers. Measure worst-case latency before tuning.

### 31.8. Overly Long TTL

Failure detection and promotion become sluggish, lengthening RTO. Choose TTL alongside `loop_wait`/`retry_timeout` per your failure budget.

### 31.9. Believing Lease Expiry Automatically Fences the Old Primary

A DCS lease does not stop the PostgreSQL process. Patroni fail-closed behavior, watchdog, and/or external fencing are required.

### 31.10. Not Testing the Watchdog for Real

Declaring watchdog config does not prove the device works. Test permissions, timeouts, reset behavior, and failure scenarios.

### 31.11. Bootstrapping Twice

Re-bootstrapping a scope that already has data/history can generate incompatible cluster metadata. Establish the source of truth before bootstrapping/reinitializing.

### 31.12. Thinking Editing bootstrap.dcs Changes Running Config

`bootstrap.dcs` only seeds initial dynamic configuration. Once the cluster exists, use `patronictl edit-config`/API to modify dynamic settings.

### 31.13. Copying the Same name/data_dir Across All Nodes

Member names and data directories must be unique. Duplicate identities cause Patroni member state and process management conflicts.

### 31.14. Exposing the REST API Publicly

The REST API is a control surface and reveals topology. Restrict network access, enable auth/TLS, and audit administrative actions.

### 31.15. Using /health as a Write Routing Check

A healthy node can be a standby. The write pool must probe an endpoint confirming primary/leader status per Patroni version semantics.

### 31.16. Thinking an HAProxy Health Check Is Fencing

A proxy only stops routing traffic through itself. The old primary can still receive direct connections or traffic from another proxy. Fencing must act at the database/host/network authority layer.

### 31.17. Stacking Multiple Leader Election Controllers

Having Patroni, an operator, keepalived, and custom scripts all decide the primary can push the cluster into an inconsistent state. Only one authority should decide the database leader.

### 31.18. Misunderstanding DCS Quorum

Losing one member in a three-node cluster differs from losing two members. Design and drill both majority and minority partitions.

### 31.19. Manually Deleting the Leader Key During a DCS Error

This can grant new leadership while the old primary still accepts writes. Never edit DCS keys manually without a recovery procedure and fencing.

### 31.20. Ignoring Candidate Lag

Promoting a stale replica can lose many committed transactions. Monitor LSN/lag and `maximum_lag_on_failover`; do not force an ineligible candidate without accepting the RPO impact.

### 31.21. Lacking an Explicit Synchronous Policy

Synchronous mode can block commits when standbys are unavailable, or fail to provide expected remote durability if applications use `local`/`off`. Document the durability/availability policy clearly.

### 31.22. Enabling synchronous_mode_strict Without a Runbook

Writes can block when no synchronous standby remains. Define who can alter policy during an incident and how to re-enable it afterward.

### 31.23. Using Tags as Security Boundaries

`nofailover`, `nosync`, and `noloadbalance` are policy hints. They do not replace HBA, firewalls, RBAC, or fencing.

### 31.24. Pointing the DCS Endpoint at an Empty DCS

Patroni agents may think cluster state vanished and attempt to bootstrap/orchestrate wrongly. Migrations must transfer state properly per backend procedures.

### 31.25. Restoring an Old DCS Snapshot Without Reconciliation

Leader/member metadata may mismatch current PostgreSQL timelines. Isolate nodes, identify the database source of truth, and restore the control plane per runbook.

### 31.26. Assuming Kubernetes StatefulSet Creates PostgreSQL HA

A StatefulSet only manages Pod identity/storage lifecycle. Patroni/an operator is required for database leader election and replication.

### 31.27. Using Liveness Probes Instead of Patroni Role Checks

Liveness determines whether a process needs restarting; it does not say whether the node is primary. Use readiness/Patroni endpoints suited to the goal.

### 31.28. Reinitializing the Wrong Node

Reinit destroys a replica's data directory. Verify member name, upstream, backups, and maintenance approval beforehand.

### 31.29. Upgrading All Nodes Simultaneously

Rolling upgrades preserve redundancy. Restarting all replicas/primary together destroys HA and causes an outage.

### 31.30. Testing Failover Without Testing Rejoin

A successful failover does not prove the old primary can rewind/rebuild and restore topology health. Drill failover, fencing, routing, and rejoin together.

### 31.31. Skipping Backups Because Three Replicas Exist

Accidental `DELETE`/`DROP` replicates to every node. Base backups, WAL archiving, PITR, and immutable copies are still mandatory.

### 31.32. Ignoring Unknown COMMIT Outcomes

Clients losing connection during `COMMIT` may not know whether the transaction committed. Blind retries can duplicate operations; use idempotency keys and reconciliation.

### 31.33. Monitoring PostgreSQL Without Monitoring the DCS

The database can still answer queries while the DCS has lost quorum. HA failover is no longer guaranteed. Alert on the DCS separately.

### 31.34. Ignoring WAL Slot Retention

A disconnected replica with an active replication slot retaining WAL can fill the primary's disk. Monitor inactive slots, retained bytes, and disk headroom.

### 31.35. Checking Only /primary Without Checking the Client Path

The endpoint may be right while HAProxy/DNS/pools still route wrongly. Test through application endpoints and verify `inet_server_addr()`/role.

## 32. Practice Exercises

The following questions use the lab topology. Exercises involving partitions, promotion, DCS restore, and watchdogs must be performed only in disposable environments.

### Exercise 1. Orchestration

Why is PostgreSQL streaming replication insufficient to form a complete HA cluster?

### Exercise 2. Data Plane and Control Plane

Distinguish between the data plane, control plane, and client routing plane in a Patroni architecture.

### Exercise 3. Patroni Agent

List at least five responsibilities of the Patroni agent on each database node.

### Exercise 4. DCS

What kinds of metadata does a DCS store? Does a DCS store PostgreSQL table data?

### Exercise 5. Quorum

A DCS has three voting members. How many members are needed for a majority quorum? How many members can fail while retaining quorum?

### Exercise 6. Backend Comparison

Compare etcd, Consul, ZooKeeper, and the Kubernetes API by coordination primitive and failure modes.

### Exercise 7. Leader Lock

What do leader lease/TTL do? Why does TTL expiration not automatically stop the old primary process?

### Exercise 8. Timing

Explain the relationship among `ttl`, `loop_wait`, and `retry_timeout`. What happens if TTL is too short or too long?

### Exercise 9. Patroni HA Loop

List the main steps of the HA loop.

### Exercise 10. Patroni Config

Distinguish `scope`, `namespace`, `name`, `restapi.listen`, `postgresql.listen`, and `connect_address`.

### Exercise 11. Bootstrap

When is `bootstrap.dcs` used? Why does editing it after cluster creation not automatically update dynamic config?

### Exercise 12. Dynamic Config

Which tools view and edit dynamic config? Why should you avoid editing DCS keys directly?

### Exercise 13. REST API

Distinguish `/health`, `/primary`, and `/replica` in routing.

### Exercise 14. HAProxy

Why does HAProxy probe Patroni's REST API on port 8008 while forwarding PostgreSQL traffic to port 5432?

### Exercise 15. Read Routing

A standby can return stale data. State two ways to handle a read-after-write requirement.

### Exercise 16. Synchronous Mode

Distinguish `synchronous_mode` and `synchronous_mode_strict` at a general policy level.

### Exercise 17. Candidate Eligibility

What role does `maximum_lag_on_failover` play? Why is it not an absolute RPO guarantee?

### Exercise 18. Failover vs. Switchover

Compare the two operations by primary availability, WAL synchronization, and RPO.

### Exercise 19. DCS Outage

Why can DCS quorum loss block automatic failover even when PostgreSQL replicas are still running?

### Exercise 20. failsafe_mode

What is the goal of `failsafe_mode`? Why must it be tested per Patroni version and network topology?

### Exercise 21. Fencing

Name three fencing methods and explain why a DNS switch is insufficient.

### Exercise 22. Watchdog

How does a watchdog support leader safety? Name one condition to verify beyond YAML config.

### Exercise 23. Kubernetes

Distinguish the roles of StatefulSet, Kubernetes Service, Patroni, and a PostgreSQL operator.

### Exercise 24. Backups

Why does an etcd snapshot not replace a PostgreSQL base backup? Conversely, does a base backup store DCS leader state?

### Exercise 25. DCS Restore

Why can you not restore an old DCS snapshot and immediately start all Patroni agents?

### Exercise 26. Security

List the endpoints/traffic flows that must be secured in a Patroni + DCS topology.

### Exercise 27. Monitoring

List at least eight signals needed on an HA dashboard.

### Exercise 28. Split-Brain

Describe how a network partition can produce two primaries and how to prevent it.

### Exercise 29. Rejoin

After failover, why does the old primary need `pg_rewind` or a new base backup before returning as a standby?

### Exercise 30. Comprehensive Design

Design a three-node PostgreSQL HA cluster using Patroni, a quorum DCS, HAProxy, backups, and monitoring. Explain how to handle primary crash, DCS outage, network partition, and region failure.

## 33. Suggested Exercise Solutions

### Answer 1. Orchestration

Replication only ships WAL and keeps standbys close to the primary. HA also requires failure detection, leader ownership/election, fencing, candidate selection, promotion, routing, rejoining, and backup/recovery.

### Answer 2. Data Plane and Control Plane

- Data plane: PostgreSQL processes, data files, WAL streaming, and client SQL.
- Control plane: Patroni agents, DCS, leader leases, member records, and failover policies.
- Client routing plane: HAProxy/proxy/VIP/DNS/service discovery sending writes to the leader and reads to suitable replicas.

### Answer 3. Patroni Agent

Examples: reading config, monitoring PostgreSQL, acquiring/renewing the leader lock, publishing member state, controlling start/stop/promote/follow, creating replicas, exposing the REST API, and coordinating synchronous mode.

### Answer 4. DCS

The DCS stores dynamic config, leader key/lease, member records/heartbeats, failover metadata, and synchronous state per backend/version. It does not store PostgreSQL table data, indexes, or WAL.

### Answer 5. Quorum

Three voting members require a majority of 2. One member can fail while preserving quorum; losing two loses quorum.

### Answer 6. Backend Comparison

- etcd: Raft KV, leases, watches; loses write commits when majority is lost.
- Consul: Raft server quorum, KV/sessions/locks; pay attention to sessions/ACLs/TLS.
- ZooKeeper: Zab ensemble, ephemeral znodes/watches; pay attention to session expiration and ensemble quorum.
- Kubernetes API: API resources/leases backed by control-plane etcd; pay attention to API availability/RBAC/throttling.

### Answer 7. Leader Lock

The lease/TTL indicates which node holds ownership and requires periodic renewal. Lease expiry only changes control-plane state; it does not automatically stop the old primary's process/sockets. Patroni demotion/watchdog/external fencing is needed.

### Answer 8. Timing

`loop_wait` is the HA loop period; `retry_timeout` limits retries when operations fail; `ttl` is the ownership/lease duration. Too short a TTL causes false failovers from jitter; too long a TTL slows detection/RTO. Tune based on latency/failure budgets and release constraints.

### Answer 9. Patroni HA Loop

Read local PostgreSQL state, read DCS/member/leader state, determine role, renew leader lock if leader, inspect replicas, apply failover/sync policies, execute start/stop/promote/follow/reinit, and publish heartbeat/member state.

### Answer 10. Patroni Config

`scope` identifies the cluster; `namespace` is the DCS prefix; `name` is member identity; `restapi.listen` is the REST API bind address; `postgresql.listen` is the PostgreSQL bind address; `connect_address` is the endpoint other nodes use to connect.

### Answer 11. Bootstrap

`bootstrap.dcs` seeds dynamic config when the cluster first initializes. Once cluster state exists, dynamic config lives in the DCS; editing the local bootstrap block does not update active state. Use `edit-config`/API.

### Answer 12. Dynamic Config

Use `patronictl show-config` to view and `patronictl edit-config` to edit. Never modify DCS keys directly because doing so can corrupt leader ownership, member state, or config schemas.

### Answer 13. REST API

`/health` is basic health; `/primary` confirms the primary/leader node per version semantics; `/replica` confirms an eligible replica. Write routing must use the primary endpoint, and read routing the replica endpoint/lag policy.

### Answer 14. HAProxy

PostgreSQL TCP traffic runs on the database port (e.g., 5432). HAProxy uses HTTP health checks calling Patroni's REST API on a separate port (e.g., 8008) to verify role before picking a backend.

### Answer 15. Read Routing

You can read back from the primary; or use synchronous replication with `synchronous_commit=remote_apply` for transactions requiring read-after-write; or wait for the standby to replay up to the commit LSN.

### Answer 16. Synchronous Mode

`synchronous_mode` enables Patroni's management of synchronous standby selection. `synchronous_mode_strict` retains the synchronous acknowledgement requirement when no eligible standby exists, which can block writes and lower availability.

### Answer 17. Candidate Eligibility

`maximum_lag_on_failover` excludes overly stale replicas from the candidate set by WAL lag. It is not an absolute RPO guarantee because WAL generation rates, timing, races, timelines, sync policies, and candidate selection at failure time still matter.

### Answer 18. Failover vs. Switchover

Switchover is planned, the old primary cooperates, and you can wait for standbys to catch up. Failover happens when the primary is unavailable; the final WAL position may be unknown, so RPO depends on replication mode and the chosen replica.

### Answer 19. DCS Outage

Without quorum, the DCS cannot commit leader ownership changes. Replicas lack unified authority to claim leadership; promoting on their own could cause split-brain.

### Answer 20. failsafe_mode

Failsafe mode can allow a leader to continue during certain DCS outages if inter-member communication/checks defined by the Patroni release succeed. Different network partitions yield different outcomes; read docs and test.

### Answer 21. Fencing

Examples: power off the old host, revoke storage write access, network-isolate from application clients, or watchdog reset. A DNS switch only updates normal routing; clients may still hold direct connections to the old primary.

### Answer 22. Watchdog

A watchdog forces a node to reset if keep-alives stop within the safety window, reducing the risk of an old leader continuing to run after losing ownership. Verify the actual device/driver, permissions, timeouts, and reset behavior.

### Answer 23. Kubernetes

StatefulSet manages Pod identity/storage; Service routes traffic; Patroni manages PostgreSQL roles/leader/replication; an operator manages desired state and database cluster lifecycle. Avoid having two controllers manage the primary at once.

### Answer 24. Backups

An etcd snapshot only stores control-plane metadata, not PostgreSQL table data/WAL. A PostgreSQL base backup stores data files, not DCS leader lock/config state.

### Answer 25. DCS Restore

An old snapshot may hold leader/member state inconsistent with current PostgreSQL timelines/roles. You must fence writers, reconcile the source of truth, and verify metadata before starting agents to prevent dual leaders.

### Answer 26. Security

Secure PostgreSQL client/replication ports, the Patroni REST API, DCS client/peer ports, backup repositories, monitoring/admin endpoints, credentials, certificates, and Kubernetes API/RBAC.

### Answer 27. Monitoring

Examples: Patroni leader/member state, DCS quorum, DCS proposal latency, PostgreSQL roles, replication LSN lag, slot retained WAL, WAL archive status, HAProxy backend state, free disk space, synchronous waits, recovery conflicts, and backup freshness.

### Answer 28. Split-Brain

Primary A is partitioned from the DCS while still accepting writes; replica B loses contact with A while retaining DCS quorum and is promoted. If A is unfenced, both A and B accept writes. Prevent with quorum/lease semantics, Patroni fail-closed behavior, watchdog/external fencing, and single-writer routing.

### Answer 29. Rejoin

The old primary may hold a diverged WAL history after promotion. `pg_rewind` or a fresh base backup aligns it onto the current primary's history before starting as a standby; two histories cannot be merged by restarting the old process.

### Answer 30. Comprehensive Design

A viable design:

1. Three PostgreSQL nodes of the same major version, each with a Patroni agent.
2. A three-voting-member etcd DCS across proper failure domains; TLS/auth enabled and quorum monitored.
3. One leader and two physical streaming replicas; enable synchronous mode for a standby near the primary if low RPO demands it.
4. A DR replica in another region can remain asynchronous to avoid WAN latency on every commit; pair with an acceptable RPO and continuous WAL archiving.
5. HAProxy write backend probing `/primary`; read backend probing `/replica` with a lag threshold.
6. Independent base backups/WAL archiving, immutable copies, and restore drills.
7. Monitoring for PostgreSQL, Patroni, DCS, HAProxy, slots, archives, disks, and backup freshness.
8. Primary crash: confirm incident, DCS quorum, candidate lag, fencing, promotion, and traffic routing.
9. DCS outage: preserve single-writer, restore quorum; use failsafe only if the policy was tested.
10. Network partition: rely on watchdog/external fencing and do not promote without authority.
11. Region failure: inspect DR control-plane quorum, WAL/backups, fence the old region, promote the right standby, update routing, and validate business data.

## 34. Patroni Design and Operations Checklist

### 34.1. Cluster Topology

1. Does each PostgreSQL node have a Patroni agent and unique identity?
2. Are all PostgreSQL nodes on the same major version?
3. Are data directories/tablespaces/storage failure domains independent?
4. Are `scope`/`namespace` unique per cluster?
5. Is there exactly one authority deciding the PostgreSQL leader?

### 34.2. DCS

6. Is the DCS backend supported by your Patroni version?
7. Are quorum members distributed across proper failure domains?
8. Are client/peer TLS and authentication enabled?
9. Do DCS ACLs/RBAC grant only necessary permissions?
10. Are DCS metrics, snapshot/restore, and upgrade runbooks in place?
11. Are there alerts for member loss/quorum loss/proposal latency/disk quota?

### 34.3. Patroni

12. Are local config and dynamic config clearly distinguished?
13. Is bootstrap executed only on a fresh cluster with no existing state?
14. Are TTL/`loop_wait`/`retry_timeout` tuned to measured latency?
15. Do `maximum_lag_on_failover`/`check_timeline` have clear policies?
16. Are `failsafe_mode`/watchdog understood and tested?
17. Are REST API authentication/TLS/firewalls appropriate?
18. Do tags reflect failover/sync/read routing policies?

### 34.4. PostgreSQL

19. Are base backups/replication slots/WAL retention configured?
20. Do synchronous mode and `synchronous_commit` have a clear durability policy?
21. Are replication lag and recovery conflicts monitored?
22. Are `pg_rewind` preconditions in place if used?
23. Are independent backups/WAL archiving functioning?

### 34.5. Routing and Applications

24. Does the write endpoint route only to Patroni's primary endpoint?
25. Does the read endpoint route only to eligible replicas?
26. Are lag thresholds and stale-read semantics defined?
27. Do connection pools reconnect after failover?
28. Does the application have idempotency for unknown `COMMIT` outcomes?
29. Is routing tested end-to-end, not just health checks?

### 34.6. Operations

30. Are runbooks available for bootstrap, failover, switchover, DCS outages, and rejoin?
31. Are rolling upgrades defined for PostgreSQL/Patroni/DCS?
32. Is there auditing for manual failovers and dynamic config changes?
33. Are fencing tests and split-brain exercises conducted?
34. Are restore/PITR/DR drills held regularly?
35. Have actual RTO/RPO been measured and compared against SLAs?

## 35. General Runbook When the HA Cluster Is Abnormal

### Step 1. Determine Incident Scope

Inspect PostgreSQL, Patroni, DCS, networking, proxies, and backups. Distinguish a database process failure from a control-plane failure or a routing failure.

### Step 2. Identify the Current Leader

Compare:

- `patronictl list`.
- DCS leader/member state.
- `pg_is_in_recovery()` on each node.
- `pg_stat_replication`.
- REST API `/primary`.

If layers disagree, isolate writes and investigate before promoting.

### Step 3. Confirm Quorum

Check DCS voting members, leader, and ability to commit. Never delete keys or re-bootstrap before quorum is understood.

### Step 4. Assess Fencing

Determine whether the old primary can still accept writes. Perform reliable fencing before transferring leader ownership.

### Step 5. Select a Candidate

Compare LSN/lag/timeline/synchronous state and policy. Never force promotion of an ineligible node without accepting data loss.

### Step 6. Execute Promotion Through Patroni

Use `patronictl` or the API per runbook/version. Promote only one node. Never run `pg_ctl promote` outside Patroni while the cluster remains managed.

### Step 7. Shift Traffic

Confirm HAProxy/Service/DNS updates, connection pools reconnect, and writes land on the new primary. Test from the application.

### Step 8. Reconcile Data

Inspect unknown transaction outcomes, idempotency keys, external events, and business invariants. Assess actual RPO.

### Step 9. Rejoin Nodes

Repoint replicas onto the new timeline. Rewind/rebuild the old primary. Confirm all nodes return to proper roles.

### Step 10. Restore Redundancy

Verify DCS quorum, replica health, backups/WAL archiving, and monitoring. Never close the incident with only a single active primary before redundancy is restored.

### Step 11. Write an Incident Report

Record the timeline, node roles, DCS events, LSNs, RTO/RPO, data loss/uncertainty, fencing evidence, and corrective actions.

## 36. Summary

**Patroni orchestrates PostgreSQL HA; the DCS provides coordination state/quorum; PostgreSQL streaming replication transfers WAL; proxies/service discovery direct clients to the right role; fencing prevents the old primary from continuing to write.** These components must be designed and operated as one cohesive system.

Core principles:

- PostgreSQL replication does not elect a leader or update client routing on its own.
- A Patroni agent runs on each database node and manages the PostgreSQL lifecycle/HA loop.
- The DCS stores leader/member/config metadata, not database contents.
- Quorum lets agents agree on ownership; losing quorum can prevent safe failover.
- Leader TTL/leases require renewal; lease expiration does not automatically stop the old primary.
- Watchdogs/external fencing protect the single-writer invariant.
- `bootstrap.dcs` seeds initial config; subsequent dynamic config is managed via DCS/`patronictl`/API.
- The REST API provides role/health endpoints; load balancers must probe the right endpoint for write/read routing.
- Synchronous mode is a durability/availability trade-off; strict policies can block writes.
- Automatic failover requires candidate eligibility, WAL lag/timeline policies, and DCS authority.
- DCS outages, network partitions, and Kubernetes API outages require dedicated runbooks.
- Database backups and DCS backups are two separate tasks; both need restore/reconciliation plans.
- Kubernetes StatefulSets/Services do not replace Patroni leader election; operators and Patroni must not fight for control.
- Monitor PostgreSQL, Patroni, DCS, routing, backups, and fencing; drill failover/rejoin end-to-end.

Practical principle:

> **An HA cluster is only safe when ownership is coordinated through quorum, the old primary is fenced, clients route to the valid leader, and every node can rejoin using tested runbooks.**

## 37. References

Official documentation; select the exact Patroni/PostgreSQL/DCS versions you run:

- [Patroni Documentation](https://patroni.readthedocs.io/en/latest/): architecture, configuration, DCS, HA loop, REST API, and operations.
- [Patroni Configuration](https://patroni.readthedocs.io/en/latest/yaml_configuration.html): local/dynamic config, bootstrap, PostgreSQL, and tags.
- [Patroni Dynamic Configuration](https://patroni.readthedocs.io/en/latest/dynamic_configuration.html): DCS-backed cluster settings and configuration changes.
- [Patroni REST API](https://patroni.readthedocs.io/en/latest/rest_api.html): health/role endpoints and administrative API.
- [Patroni Replication Modes](https://patroni.readthedocs.io/en/latest/replication_modes.html): asynchronous/synchronous behavior and failover policy.
- [Patroni DCS](https://patroni.readthedocs.io/en/latest/dcs_failsafe_mode.html): DCS behavior and failsafe mode.
- [etcd Documentation](https://etcd.io/docs/): Raft, quorum, leases, TLS, snapshots, and operations.
- [Consul Documentation](https://developer.hashicorp.com/consul/docs): KV, sessions, ACLs, TLS, and server quorum.
- [Apache ZooKeeper Documentation](https://zookeeper.apache.org/doc/current/): ensemble, sessions, znodes, watches, and security.
- [Kubernetes Documentation](https://kubernetes.io/docs/): API server, StatefulSets, Services, probes, RBAC, and storage.
- [PostgreSQL Warm Standby](https://www.postgresql.org/docs/current/warm-standby.html): physical streaming replication and standby operation.
- [PostgreSQL Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION): commit acknowledgement semantics.
- [PostgreSQL pg_rewind](https://www.postgresql.org/docs/current/app-pgrewind.html): rejoining a cluster after timeline divergence.
- [PostgreSQL Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html): base backups, WAL archiving, and recovery.
- [HAProxy Configuration Manual](https://www.haproxy.org/documentation.html): TCP backends and HTTP health checks.
