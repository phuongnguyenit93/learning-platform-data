# Registry Capacity Planning, High Availability, and Upgrades

## Objectives

After this lesson, you will be able to:

- Estimate registry load from instance counts, heartbeats, lookups, metadata, and topology churn rates.
- Choose an appropriate high-availability architecture for Eureka, Consul, ZooKeeper, or Kubernetes.
- Distinguish Eureka's peer replication model from the quorum/consensus models of Consul, ZooKeeper, and etcd.
- Define SLOs, RTO, and RPO and test recovery when a registry or failure domain is lost.
- Plan backups, restores, rolling upgrades, and compatibility across servers, clients, Spring Boot, and Spring Cloud.
- Validate capacity and upgrade procedures through load testing, canaries, and failure drills.

## 1. The Registry Is Critical Infrastructure, Yet Each Type Operates Differently

A service registry stores or supplies information so consumers can locate service instances. Depending on the technology, a registry may store registrations in memory, replicate across peers, write to a consensus log, or rely on the Kubernetes API.

You cannot apply the same deployment blueprint to every registry:

| Registry | Primary Storage/Sync Model | Components Directly Affecting Availability |
| --- | --- | --- |
| Eureka | Registry is primarily in memory; servers peer-replicate registrations; clients maintain local caches. | Peers, heartbeats, peer replication, client caches, and self-preservation. |
| Consul | Servers use Raft to maintain catalog and state; client agents can run on application nodes. | Quorum of voting server members, leader, disk I/O, and inter-server network. |
| ZooKeeper | Ensemble uses a leader and quorum; registrations are typically represented by ephemeral znodes. | Ensemble majority, transaction logs, sessions, and network between members. |
| Kubernetes | Services and endpoints are stored via the Kubernetes API; control plane uses etcd to persist cluster state. | kube-apiserver, etcd quorum, controllers, and cluster DNS/dataplane paths. |

The first step in planning is identifying which mechanism the application uses: calling Kubernetes Service DNS, querying the Kubernetes API via Spring Cloud Kubernetes, or using a dedicated registry like Eureka, Consul, or ZooKeeper. An application calling only Service DNS does not generate the same discovery load as an application continuously calling the API to fetch endpoint lists.

## 2. Define the Workload Before Selecting Server Specs

Do not start by picking CPU or RAM from a generic rule of thumb. Build a workload model from measurable quantities:

- Number of registered services per environment and per cluster.
- Average and peak replica counts, plus extra instances added during rolling deployments.
- Heartbeat/renewal frequency and number of clients sending heartbeats.
- Consumer count, lookup count, refresh intervals, and how clients use watches, polling, or caches.
- Rate of instance creations, deletions, and updates over a time window.
- Number of metadata key/value pairs and registration payload size.
- Number of namespaces, services, Pods, and EndpointSlices if using Kubernetes.
- Number of agents, concurrent connections, peers, and geographic zones/regions.
- Concurrent reconnect counts when a node, AZ, or network path recovers.

Measure both steady load and burst load. Deploying hundreds of replicas, autoscaling surges, or thousands of clients reconnecting after a network partition can create bursts far larger than average load.

### Initial Estimation Formulas

Let:

- N be the number of registered instances.
- T be the average heartbeat/renewal interval in seconds.
- C be the number of consumer clients.
- Q be the average lookups per consumer per second.
- S be the average serialized data size of one instance.
- F be the headroom factor for bursts and growth.

You can make a rough initial estimate:

~~~~text
Average heartbeat rate ≈ N / T

Average lookup rate ≈ C × Q

Raw registration data size ≈ N × S

Initial planned load ≈ measured load × F
~~~~

These formulas are only input models for benchmarking. They do not predict exact real-world load because each registry batches, caches, replicates, watches, and processes requests differently. Use logs/metrics from existing systems to replace assumptions with measurements.

### Load Calculation Example

Suppose a platform has 2,400 instances and each instance sends a heartbeat on average every 30 seconds:

~~~~text
Heartbeat rate ≈ 2,400 / 30 = 80 heartbeats/second
~~~~

If there are 600 consumers and each consumer performs one lookup every 30 seconds:

~~~~text
Lookup rate ≈ 600 / 30 = 20 lookups/second
~~~~

If a rolling deployment spawns 600 new instances registering within 2 minutes, the average registration burst from that rollout alone is:

~~~~text
600 / 120 = 5 registrations/second
~~~~

These numbers exclude retries, synchronized heartbeats, peer replication, client refreshes, cache misses, health checks, and reconnect storms. During benchmarks, generate both steady load and bursts rather than running only a flat requests/second rate.

## 3. Estimating Resources Across Each Dimension

Registries consume more than CPU. A system with many small registrations can be bottlenecked by networking, connection counts, or heap; a system persisting durable state can be bottlenecked by disk latency.

| Resource | Load Drivers | Signs of Insufficient Capacity |
| --- | --- | --- |
| CPU | Serialization/deserialization, request handling, TLS, service filtering, watches, and replication. | Sustained high CPU, rising request latency, leader elections, or elevated GC. |
| Memory | Registry catalog, metadata, indexes, client caches, watch state, and request buffers. | Steadily growing heap/working set, GC pauses, OOM, or cache evictions. |
| Network | Heartbeats, lookup responses, full/incremental registry fetches, peer replication, watch events. | High RTT, retransmits, connection resets, network saturation. |
| Disk capacity | Snapshots, transaction/Raft logs, audit logs, and operational logs. | Disk nearly full, insufficient log retention, failed snapshots. |
| Disk I/O | Writing Raft/transaction logs, fsync, snapshots, and restores. | High write latency, sluggish leader, unstable quorum. |
| Connections/file descriptors | Clients, peers, agents, HTTP pools, and watch connections. | Connection refused, file descriptors exhausted, thread pools depleted. |
| Control-plane/API quota | LIST/WATCH, EndpointSlice updates, API requests, and controller work queues. | API throttling, watch reconnects, slow endpoint updates. |

Measure the footprint of a real registration, including metadata and implementation overhead. Do not take pre-send JSON size as the in-memory footprint. Indexes, object headers, maps, caches, and replication can make the real footprint much larger.

### Metadata and Instance Count

Metadata should stay small and stable. A registry holding tens of thousands of instances, each carrying large metadata, will consume substantial memory and network bandwidth when clients sync the catalog.

Best practices:

- Include only metadata keys that consumers actually use.
- Enforce limits on key count, value length, and total bytes.
- Never use metadata to store large configs, secrets, user lists, or continuously changing state.
- Use labels/filters/namespaces to restrict discovery scope when supported by the implementation.
- Measure actual serialized response sizes and heap usage under high load.

## 4. Benchmarking and Headroom Factors

There is no single CPU/RAM spec applicable to every registry. Hardware sizing for Consul servers, ZooKeeper servers, or the Kubernetes control plane depends on scale, workload profile, network latency, and storage characteristics.

A practical benchmarking workflow:

1. Populate a catalog with service, instance, and metadata counts close to production.
2. Simulate heartbeats/renewals at realistic intervals.
3. Generate lookups at both average and burst rates, covering cache hits, cache misses, and large responses.
4. Execute rolling deployments and scale-out/scale-in to induce churn.
5. Sever a node or network path to measure failover and reconnect behavior.
6. Measure CPU, memory, GC, network, disk latency, open connections, queue depth, and request latency.
7. Ramp load until latency/SLOs or resource limits begin degrading.
8. Pick an operating point below the saturation zone and reserve headroom for growth, maintenance, and node failures.

Headroom factor F should reflect workload volatility, provisioning lead time, and scaling capability. Using 1.5x or 2x forecasted load can serve as a starting benchmark assumption, not a rigid rule. If a cluster must survive a large reconnect burst or losing an entire failure domain, benchmark that scenario directly.

Do not use low average CPU as proof that the registry has spare capacity. With Consul/ZooKeeper, disk sync or networking among quorum members can limit availability before CPU reaches 100%. With Eureka, server peer replication and client caches can mask partial failures in the short run, yet peer data can diverge during network partitions.

## 5. Planning Availability with SLO, RTO, and RPO

Before picking node counts, define how the system needs to recover:

- **Availability SLO:** percentage of time critical lookup/registration operations complete within agreed latency and error rate thresholds.
- **RTO:** maximum time allowed to restore registry service after an outage.
- **RPO:** amount of registry changes acceptable to lose in a data recovery scenario.
- **Failure domain:** blast radius of simultaneous failure, such as process, VM, node, rack, AZ, region, or entire cluster.
- **Degraded mode:** how providers/consumers behave when the registry is unreachable.

For registries storing data reconstructible from heartbeats and re-registrations, RPO can be treated differently than a registry storing durable configuration or coordination data. Never assume every registration must be backed up like a transactional business database.

### Choosing Failure Domains

If all voting servers sit in the same rack or the same AZ, an outage of that failure domain can break quorum even if the node count looks sufficient on paper. Distribute members across real physical topology and verify network latency between zones.

Balance among:

- Node/AZ fault tolerance.
- Latency between quorum members.
- Network and compute costs.
- Number of members required to coordinate each write.
- Node replacement and quorum recovery procedures.

## 6. High Availability with Eureka

Eureka uses a peer-aware server model. Each server holds the registry in memory, accepts client heartbeats, and replicates registrations to configured peers. Clients also keep a registry cache so they do not query servers on every request.

In production:

- Run multiple peer-aware Eureka Servers across independent failure domains.
- Configure clients to reach multiple peers or an appropriately designed load balancer.
- Ensure peer URLs, hostnames, TLS, and network paths are mutually reachable as configured.
- Monitor peer replication, renewal rates, evictions, and self-preservation.
- Verify clients continue using cached data when a peer is temporarily unreachable.

Eureka does not use Raft quorum like Consul or ZooKeeper. One peer can keep serving from its own registry view when cut off from other peers. This boosts availability, though peers may temporarily hold differing views of registrations.

Self-preservation protects the registry from mass-evicting instances when heartbeats drop abnormally. During a network partition, the registry may retain instances that are no longer serving. Consumers must have timeouts, retries/failover, and the ability to handle stale endpoints.

Illustrative peer configuration example:

~~~~yaml
eureka:
  client:
    service-url:
      defaultZone: https://eureka-a.internal/eureka/,https://eureka-b.internal/eureka/,https://eureka-c.internal/eureka/
~~~~

This is an example URL list, not a complete configuration for every topology. Verify that each peer actually replicates and that clients can fail over. Adding peers without testing connectivity and replication does not yield real HA.

Because the Eureka registry is usually rebuilt from client registrations and heartbeats, backup procedures should prioritize server configs, peer topology, TLS/credentials, and clients' ability to re-register. If special data recovery guarantees are required, verify behavior for your exact version and deployment; do not assume a durable database snapshot equivalent to Consul Raft exists.

## 7. High Availability with Consul

Consul servers use Raft to maintain consistent state. Only voting server members participate in the Raft peer set; Consul client agents do not increase server quorum.

With N voting servers, quorum is:

~~~~text
quorum = floor(N / 2) + 1
failure tolerance = N - quorum
~~~~

Examples:

| Voting Servers | Quorum | Servers That Can Be Lost While Preserving Quorum |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 6 | 4 | 2 |

Consul typically recommends 3 or 5 voting servers for production. Adding more servers does not scale throughput linearly; larger quorums increase coordination and operational overhead. Spread servers across failure domains while keeping inter-server latency within acceptable bounds.

Points to monitor:

- Current leader and leader election duration.
- Raft commit/apply latency, log size, and replication lag.
- Disk sync latency and data directory free space.
- Voting/healthy server counts and quorum status.
- Request latency, blocking queries, catalog size, and client agent health.

When quorum is lost, Consul cannot commit new log entries. Never try to fix an unhealthy cluster by starting extra servers with empty data directories; membership and recovery actions must follow official Consul procedures.

## 8. High Availability with ZooKeeper

ZooKeeper uses an ensemble and requires a majority to stay operational. With N servers, quorum is:

~~~~text
quorum = floor(N / 2) + 1
failure tolerance = floor((N - 1) / 2)
~~~~

| Ensemble | Quorum | Servers That Can Be Lost |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 3 | 2 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

In production, 3 or 5 servers are usually a sensible starting point. Adding members increases replication and management overhead; do not add nodes just to have extra replicas without accounting for quorum math.

Key considerations:

- Place servers on independent hosts/VMs and failure domains.
- Use a stable, low-latency network between members.
- Dedicate suitable devices or volumes for transaction logs; ZooKeeper must persist transaction logs durably before acknowledging updates.
- Avoid swapping; heap must not consume all physical RAM because the OS and page cache also need memory.
- Monitor outstanding requests, latency, fsync, leader state, and watcher/session counts.
- Configure snapshot/transaction log purging per retention policy; by default, servers do not automatically delete all old files.

Ephemeral znode registrations are deleted when sessions expire. Therefore, when a client reconnects after session loss, the application must recreate its session and registration. Registry availability and service availability are not identical: the ensemble may have quorum while a provider has not yet re-registered.

## 9. High Availability with Kubernetes Discovery

When discovery relies on Kubernetes, the registry view depends on the Kubernetes API and control plane health. The API server serves requests; etcd stores cluster state. EndpointSlices and Services are updated by controllers based on Pod readiness and selectors.

If applications only call ClusterIP Services via DNS, data-plane requests can keep working in some control-plane outage scenarios. However, updates to Services, Pods, or EndpointSlices may be delayed when API server/etcd encounters issues. Applications calling the Kubernetes API directly to refresh discovery are affected more visibly.

For self-managed clusters via kubeadm, HA topology typically follows two patterns:

- **Stacked etcd:** etcd members run on the same control-plane nodes. Simpler to deploy, yet losing a node loses both a control-plane instance and an etcd member.
- **External etcd:** etcd runs on dedicated hosts. Provides cleaner failure-domain isolation, yet requires extra machines and separate etcd operations.

An HA cluster requires multiple control-plane nodes and etcd members in a supported topology; API server load balancer configuration must be tested independently. Never treat worker node count as proof that the control plane is HA.

When using Spring Cloud Kubernetes `DiscoveryClient`, restrict namespaces and label filters to cut `LIST`/`WATCH` overhead. Monitor API throttling, watch reconnects, EndpointSlice update latency, and cache freshness. If you only need Service hostnames, Kubernetes DNS usually reduces reliance on every application calling the API server.

## 10. Designing Behavior When the Registry Is Unavailable

Availability is not just node count. You must decide what consumers and providers do when the registry goes down:

| Scenario | Behavior to Consider |
| --- | --- |
| Provider fails to register at startup | Retry with backoff and jitter; report degraded status; avoid tight retry loops. |
| Registry drops after app is already running | Retain last-known-good cache if supported by the library; fail requests fast with timeouts and monitor cache age. |
| Lookup returns an empty list | Distinguish a nonexistent service from a lookup error; do not blindly keep stale caches indefinitely on empty results. |
| Cached instance is stale | Attempt endpoint with bounded timeout, retry another instance, and refresh cache once the registry recovers. |
| Mass registry reconnects | Use backoff/jitter and concurrency caps to avoid reconnect storms. |
| Provider shutdown | Deregister if possible; apply readiness/draining before process exit. |

No single stale-cache policy fits every service. One consumer may tolerate using known addresses for several minutes on non-sensitive reads; another requires fresh membership data for writes or security reasons. Define cache age limits, timeouts, and retries per business contract.

## 11. Backup, Restore, and Disaster Recovery

Backups must match the type of data the registry stores.

| Registry | Data to Protect | Recovery Notes |
| --- | --- | --- |
| Eureka | Configuration, peer topology, TLS/credentials, deployment manifests, and client re-registration flow. | Runtime registry is primarily in memory; verify rebuild capability from heartbeats/clients rather than assuming a DB snapshot. |
| Consul | Raft snapshots, server/agent configs, ACLs, TLS, encryption keys, and deployment info. | Store snapshots securely and test restoring into an appropriate recovery cluster. |
| ZooKeeper | Snapshots, transaction logs, `dataDir`, `logDir`, `myid`, and ensemble configs. | Retain snapshots alongside required transaction logs; test recovery and server sync per docs. |
| Kubernetes | etcd snapshots, PKI/certificates, encryption configs, manifests, and control-plane info. | etcd snapshots contain sensitive cluster state; encrypt and restrict access. |

### Backing Up Consul

Consul provides snapshots of server cluster state. Example commands:

~~~~bash
consul snapshot save registry-backup.snap
consul snapshot inspect registry-backup.snap
~~~~

Store snapshots separately from the cluster and verify readability. Restore is a low-level Raft operation intended primarily for disaster recovery and can heavily alter cluster state. Consul documentation requires the recovery cluster to run the same Consul version that created the snapshot. Restore into a fresh/isolated cluster following the version's runbook; never treat restore as a hot rollback on a live cluster. Rehearse in an isolated environment before needing it in production.

### Backing Up ZooKeeper

ZooKeeper stores snapshots of the data tree and transaction logs. Understand the relationship between the latest snapshot and subsequent transaction logs. Never manually delete files needed for recovery. Configure autopurge/retention to prevent disk exhaustion while keeping enough files per backup policy.

### Backing Up Kubernetes etcd

An etcd snapshot holds Kubernetes cluster state, including Secrets and other sensitive data. Encrypt backup files, restrict read permissions, manage certificates/keys, and test restores on an isolated control plane. An untested backup is not proof that DR works.

### Testing Restores

A minimal drill should verify:

1. The snapshot is taken from a healthy cluster with a clear timestamp/index.
2. The snapshot is transferred to isolated storage with checksum verification.
3. Operators hold all credentials/certificates/configs needed to stand up a recovery cluster.
4. Restore succeeds in an isolated environment.
5. Service catalog, ACLs, metadata, namespaces, and registrations are verified.
6. Consumers can look up and call instances after providers re-register.
7. Actual recovery duration is measured against RTO/RPO.

## 12. Planning Registry Upgrades

Upgrading a registry can impact protocols, persistent data, APIs, client libraries, and Spring Cloud integrations. Break upgrades into observable, safely stoppable steps.

### Before Upgrading

- Identify current and target versions of servers, agents, and client libraries.
- Read release notes, deprecations, breaking changes, and supported upgrade paths.
- Verify the compatibility matrix across Spring Boot, Spring Cloud release train, Spring Cloud Netflix/Consul/Zookeeper/Kubernetes, and the registry server.
- Check protocol compatibility, API versions, serialization, metadata schemas, and authentication.
- Measure baseline: registration failures, lookup errors/empties, latency, connection states, catalog size, and quorum health.
- Take backups or confirm registry reconstruction procedures appropriate to the technology.
- Rehearse restore and rollback in staging under near-production load.
- Confirm clients continue operating while one server node is upgraded.

Never upgrade multiple voting servers simultaneously. In quorum-based registries, doing so can cost the cluster its majority. Do not begin an upgrade while the cluster has downed nodes, an unstable leader, or high replication lag.

### Rolling Upgrade

A general sequence:

~~~~mermaid
flowchart TD
    A[Check versions and release notes] --> B[Measure baseline and confirm cluster health]
    B --> C[Backup or confirm rebuild capability]
    C --> D[Rehearse upgrade and restore in staging]
    D --> E[Upgrade one canary server/peer]
    E --> F{Node healthy and synced?}
    F -- No --> G[Halt rollout and investigate/rollback per runbook]
    F -- Yes --> H[Upgrade remaining servers one by one]
    H --> I[Upgrade client agents and apps in waves]
    I --> J[Test register, lookup, heartbeat, and failover]
    J --> K[Monitor SLOs and close upgrade window]
~~~~

This is a skeleton sequence. Detailed ordering must follow the target product and version's upgrade guide.

### Consul

The standard Consul process upgrades one server agent at a time, waiting for the server to become healthy and rejoin the cluster before moving to the next server. Once the server cluster finishes, roll out client agents and dependent components like Envoy according to the compatibility matrix.

Before upgrading, take a snapshot and consult version-specific guides for each major release. Some releases introduce protocol compatibility steps or two-phase procedures for backward-incompatible changes. Never assume every version can jump directly to the latest release.

### ZooKeeper

ZooKeeper defines backward-compatibility rules and rolling upgrade paths per release. Check source version, target version, client compatibility, and any new features clients start using. Release docs may recommend stepping through an intermediate branch before moving to a newer branch.

When rolling-upgrading an ensemble, preserve active quorum, upgrade one member at a time, and wait for it to rejoin stably. Do not enable new features requiring the newer server version cluster-wide until all members and relevant clients are compatible.

### Eureka

Peer-aware Eureka servers can be upgraded one peer at a time while remaining peers continue serving. Before moving to the next peer, verify peer replication, heartbeats, registry fetches, and client error rates. Since registry views can briefly diverge between peers, verify clients can reach healthy peers and tolerate stale data during the rollout.

Upgrade Spring Cloud Netflix clients alongside the compatible Spring Boot release train. Do not upgrade only the server while overlooking changes in client transport, heartbeats, health checks, or metadata handling.

### Kubernetes

Kubernetes control-plane upgrades must follow the version skew policy and Kubernetes version upgrade guides. With kubeadm, upgrade the control plane and nodes using the supported workflow; back up etcd before making changes. Never upgrade kube-apiserver, kubelet, kubeadm, and etcd in an arbitrary order. Check deprecated/removed APIs and versions of controllers/operators managing EndpointSlices.

## 13. Post-Upgrade Verification

After each node or each wave of client upgrades, verify:

- All server members report the expected version/build.
- Quorum or peer replication is healthy.
- The leader is not continuously re-electing.
- Clients connect, register new instances, and heartbeat/renew successfully.
- Lookups return the right instances, metadata, and endpoints.
- Registrations/deregistrations show no error spikes.
- Request latency and connection latency stay within SLO.
- No spikes occur in retries, reconnects, timeouts, or stale caches.
- Backup/restore procedures remain compatible with the new version.
- Dashboards, alerts, and runbooks remain operational.

Do not close a change just because new processes started. Verify end-to-end behavior from provider to consumer.

## 14. Change and Rollback Plan

A change plan should clearly document:

| Item | Details to Document |
| --- | --- |
| Scope | Registry servers, client agents, Spring Cloud dependencies, control plane, or all. |
| Objective | Target versions, bugs to resolve, features to adopt. |
| Compatibility | Supported upgrade path, protocols, APIs, client/server version skew. |
| Backup | Snapshot/config backup, storage location, restore permissions, and creation time. |
| Sequence | Canary node, remaining servers, client agents, applications. |
| Gates | Quorum/peer health, registration errors, lookup latency, catalog visibility. |
| Halt rollout | Conditions breaching SLO, lost quorum, peer replication errors, or client incompatibility. |
| Rollback | How to revert to the previous version; when snapshot restore is needed instead of merely downgrading binaries. |
| Verification | Register, heartbeat, lookup, failover, restore tests, and dashboards. |

Rollback is not always just swapping the old binary back in. If the new version altered persistent state or protocols, follow specific downgrade/restore instructions. Never restore an old snapshot onto a live cluster without assessing the impact of that operation.

## 15. Capacity and Availability Checklist

- [ ] Counted instances, consumers, heartbeats, lookups, churn, and metadata per environment.
- [ ] Measured actual catalog size and response payload sizes.
- [ ] Benchmarked steady load, deployment bursts, reconnects, and node failures.
- [ ] Identified CPU, memory, network, disk I/O, connections, and file descriptors as distinct limits.
- [ ] Chosen headroom based on benchmark data and growth rate.
- [ ] Defined SLOs, RTO, RPO, and failure domains.
- [ ] Distinguished Eureka peer replication from Consul/ZooKeeper/etcd quorum.
- [ ] Distributed voting/peer servers across appropriate failure domains.
- [ ] Defined client behavior during registry unavailability and cache age limits.
- [ ] Put backups or re-registration workflows suited to the registry in place.
- [ ] Rehearsed restores and measured actual RTO.
- [ ] Verified version compatibility and supported upgrade paths.
- [ ] Upgraded a canary first and preserved quorum throughout rolling upgrades.
- [ ] Verified registration, heartbeats, lookups, failover, and client compatibility post-upgrade.
- [ ] Updated dashboards, alerts, and runbooks.

## Key Takeaways

- Capacity planning starts from instance count, heartbeats, lookups, churn, and metadata size—never from a default server spec.
- Benchmarks must include steady load, deployment bursts, and reconnect storms.
- Eureka peer replication lacks Raft quorum; Consul, ZooKeeper, and etcd require a majority/quorum.
- Adding voting servers does not always increase throughput; larger quorums also increase coordination cost.
- HA must consider failure domains, networking, disk I/O, backups, and client behavior when the registry is unavailable.
- Backups must fit the data: Consul snapshots, ZooKeeper snapshots/logs, Kubernetes etcd snapshots; Eureka generally requires protecting configs and clients' ability to re-register.
- Rolling upgrades proceed step by step only once each node is healthy and synced; always follow the version's supported upgrade path.
- Verify register, lookup, latency, failover, and restores after upgrading before closing the change.

## Official References

- [Spring Cloud Netflix – Eureka Server and High Availability](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Netflix Eureka – Peer-to-Peer Communication and Self-Preservation](https://github.com/Netflix/eureka/wiki/Understanding-Eureka-Peer-to-Peer-Communication)
- [Consul – Capacity Planning](https://developer.hashicorp.com/consul/docs/reference/architecture/capacity)
- [Consul – Reliability and Quorum](https://developer.hashicorp.com/consul/docs/concept/reliability)
- [Consul – Upgrading Consul](https://developer.hashicorp.com/consul/docs/upgrade)
- [Consul – General Upgrade Process](https://developer.hashicorp.com/consul/docs/upgrade/instructions/general)
- [Consul – Backup and Restore](https://developer.hashicorp.com/consul/docs/manage/disaster-recovery/backup-restore)
- [Apache ZooKeeper – Administrator's Guide](https://zookeeper.apache.org/doc/current/zookeeperAdmin.html)
- [Apache ZooKeeper – Releases and Upgrade Guidance](https://zookeeper.apache.org/releases/)
- [Kubernetes – Highly Available Topology](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/ha-topology/)
- [Kubernetes – Highly Available Cluster](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/high-availability/)
- [Kubernetes – Operating etcd Clusters](https://kubernetes.io/docs/tasks/administer-cluster/configure-upgrade-etcd/)
