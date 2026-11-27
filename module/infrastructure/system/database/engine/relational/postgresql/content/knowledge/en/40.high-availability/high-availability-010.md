# Drilling Network Failures, Server Loss, and Region Outages in PostgreSQL HA

## 1. Why Must Failures Be Drilled?

A PostgreSQL system with standbys, load balancers, and backups is not guaranteed to recover service when production suffers an incident. Components only create high availability when they coordinate properly at the exact moment a failure hits: detecting the fault, determining whether the primary is still valid, preventing two nodes from writing simultaneously, promoting an eligible standby, shifting traffic, restoring application connections, and verifying data.

Failure drilling (failover drills or game days) is the practice of proactively inducing a controlled failure to measure how the system actually responds. The goal is to prove that runbooks, automation, monitoring, and people can return the service to an operational state within committed limits.

Three core scenario groups:

- **Network failures:** primary and standby cannot communicate; clients cannot reach the primary; cross-region links degrade; packet loss or latency destabilizes health checks.
- **Server loss:** PostgreSQL process crashes, host power loss, VM/node termination, storage unavailability, or server isolation.
- **Region outages:** an Availability Zone or entire region can no longer serve, encompassing databases, networking, control planes, or dependencies required to run the application.

A good drill does not only measure how fast PostgreSQL promotes. It measures the time from fault onset until users can execute valid transactions on the new endpoint, determines what data may have been lost, and proves no split-brain occurred.

```text
                 FAILURE INJECTION
                        |
          +-------------+-------------+
          |             |             |
          v             v             v
       Network       Server         Region
       partition     unavailable    unavailable
          |             |             |
          +-------------+-------------+
                        |
                        v
                Detect and classify
                        |
                        v
                 Fence old primary
                        |
                        v
                Select safe standby
                        |
                        v
                    Promote
                        |
                        v
             Route clients and reconnect
                        |
                        v
               Validate data/service
                        |
                        v
             Measure RPO, RTO, evidence
```

## 2. Learning Objectives

After this lesson, you will be able to:

1. Distinguish high availability (HA), disaster recovery (DR), failover, and switchover.
2. Identify failure domains and dependency paths of a PostgreSQL service.
3. Establish RPO and RTO targets for each failure scenario.
4. Explain the difference between synchronous and asynchronous replication during failover.
5. Understand `synchronous_commit` levels and their impact on latency/durability.
6. Distinguish a network partition from a server crash.
7. Recognize split-brain and the role of fencing.
8. Understand quorum, leader leases, and distributed configuration stores in HA automation.
9. Drill loss of client connectivity, replication links, and the control plane.
10. Drill PostgreSQL process crashes and host failures.
11. Design drills for Availability Zone or region loss.
12. Monitor replication state, WAL positions, and replay lag.
13. Measure detection time, fencing time, promotion time, and application recovery time.
14. Verify DNS, load balancers, connection pools, and retry behavior.
15. Verify data after promotion using transaction markers.
16. Distinguish planned switchover from unplanned failover.
17. Execute failback and safely bring the old primary back as a standby.
18. Protect backups, WAL archives, secrets, and dependencies in a standby region.
19. Design a failure matrix, rollback criteria, and evidence collection.
20. Build a game-day schedule and improve runbooks based on results.

## 3. HA, DR, Failover, and Switchover

### 3.1. High Availability

HA minimizes disruption when a component fails. With PostgreSQL, the architecture typically has one primary accepting writes, one or more standbys receiving WAL, a failure detection mechanism, a leader selection mechanism, and a traffic routing path.

HA primarily addresses common failures within the same operating system footprint: process crashes, node failures, storage/network interruptions, or planned maintenance.

### 3.2. Disaster Recovery

DR prepares to restore service after a major disaster beyond typical HA scope, such as losing an entire region, a compromised cloud account, widespread configuration errors, or corrupted data replicated to standbys.

DR typically requires:

- A data copy in a different failure domain.
- Independent base backups and WAL archives.
- Infrastructure capable of standing up in the backup region.
- DNS/network/security rules and credentials.
- A runbook governing DR activation decisions.
- Procedures for data verification and traffic cutover.

A standby in the same region is not DR for a region outage scenario.

### 3.3. Failover

Failover shifts service from a failed or no-longer-trusted primary to a selected standby that becomes the new primary. Failover is typically unplanned and may accept some data loss depending on replication mode.

### 3.4. Switchover

Switchover is a planned role transfer. Operators can stop writes, wait for the standby to catch up, verify LSNs, and switch the primary in a controlled sequence. Switchover exercises the role-transfer path with lower data-loss risk.

### 3.5. Do Not Use Switchover as Proof That Failover Is Ready

Switchover can succeed while automatic failover still fails due to lost DCS quorum, broken fencing, stale DNS caches, or a standby missing WAL. Drill both planned switchovers and real fault scenarios in a test environment.

## 4. Identifying Failure Domains

### 4.1. What Is a Failure Domain?

A failure domain is the scope of components that can be simultaneously affected by a single fault. Examples:

- Process: a PostgreSQL service or worker.
- Host: a VM, bare-metal node, or Kubernetes worker.
- Rack/zone: power, network, storage, or availability zone.
- Region: network, control plane, database nodes, and dependent services.
- Account/project: IAM, quotas, billing, credentials, or administrative actions.
- Organization: configuration, deployment, or credential errors spanning multiple regions.

### 4.2. Do Not Only Place the Database on Multiple Machines

If primary and standby sit on two different VMs yet share the same storage system, subnet, power domain, or region, a single shared failure can still take both out of service.

### 4.3. Diagram Both the Data Path and the Control Path

An HA diagram should depict:

- Primary and standby PostgreSQL instances.
- Replication network.
- DCS/quorum/witness if using an HA manager.
- Load balancers or proxies.
- DNS and service discovery.
- Application instances and connection pools.
- Backup/WAL archive storage.
- Monitoring/alerting.
- Secrets, KMS, and control planes.
- External dependencies required by the application.

### 4.4. Failure Domains Must Reflect Real Architecture

If the application runs in region A while the DR database sits in region B, losing A may leave the database alive while applications, DNS, credentials, or networking cannot run in B. Drills must include all dependencies.

## 5. RPO and RTO in a Failure Drill

### 5.1. RPO (Recovery Point Objective)

RPO is the maximum amount of data an organization tolerates losing, typically measured as the time window between the last acknowledged transaction before an incident and the recovered data state after failover.

Examples:

- Target RPO 0: zero tolerance for losing acknowledged transactions.
- 30-second RPO: tolerates losing at most roughly 30 seconds of writes in a defined scenario.
- 5-minute RPO: tolerates unreplicated data within that window.

RPO must be measured using actual transactions and commit acknowledgements, not merely an average lag metric.

### 5.2. RTO (Recovery Time Objective)

RTO is the maximum acceptable time from service disruption until the service resumes operating according to business criteria.

Do not count only PostgreSQL promotion time. RTO should include:

1. Detection.
2. Failover decision.
3. Fencing the old primary.
4. Promotion.
5. Updating routing.
6. Application reconnect.
7. Smoke tests and data validation.
8. Opening full traffic.

### 5.3. Example RTO Breakdown

| Phase | Illustrative target time |
| --- | ---: |
| Detection and classification | 20 seconds |
| Fence old primary | 15 seconds |
| Promote standby | 20 seconds |
| Switch endpoint/routing | 30 seconds |
| Application reconnect | 20 seconds |
| Smoke test and open traffic | 25 seconds |
| Total | 130 seconds |

This is only a planning example. Measure actual figures during drills and account for timeouts, DNS caches, connection pools, and human approvals.

### 5.4. RPO and RTO Are Distinct

A system can recover very fast yet lose unreplicated transactions. Conversely, a system can preserve all data yet take a long time to stand up a new endpoint. Measure both separately.

### 5.5. Set Targets per Scenario

A process failure within the same zone may have a different RTO/RPO than a region outage. Never apply one single number across all failure domains.

## 6. How Synchronous and Asynchronous Replication Affect RPO

### 6.1. Asynchronous Replication

With asynchronous replication, the primary can acknowledge commits before the standby receives or flushes the corresponding WAL. When the primary is lost abruptly, the standby may lack some transactions already acknowledged by the primary.

Pros:

- Lower commit latency.
- Does not depend on standby responses for every commit.
- Suitable for distant or cross-region replicas where latency is high.

Trade-offs:

- Can lose acknowledged data if promoting a standby that has not received all WAL.
- RPO depends on replication lag at failure time and which standby is chosen.

### 6.2. Synchronous Replication

With synchronous replication, commits on the primary wait for acknowledgement from selected standbys per configuration. This reduces the risk of losing acknowledged transactions, at the cost of higher commit latency and potential write stalls when standbys/networks are unavailable.

### 6.3. synchronous_commit

Common levels:

| Value | High-level behavior |
| --- | --- |
| `off` | Does not wait for local WAL flush before reporting commit success; can lose recent transactions on crash |
| `local` | Waits for local WAL flush, does not wait for synchronous standbys |
| `remote_write` | Waits for synchronous standby to write WAL to OS, not necessarily durable on storage |
| `on` | Waits for synchronous standby to flush WAL durably per PostgreSQL semantics |
| `remote_apply` | Waits for synchronous standby to replay the transaction so it is visible there |

Exact semantics depend on synchronous standby configuration and version. `remote_apply` typically adds more latency by waiting for replay, whereas `on` focuses on remote WAL flush.

### 6.4. synchronous_standby_names

This setting defines which standbys count as synchronous and can use `FIRST` or `ANY` with the desired standby count. Illustrative example:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
```

With `FIRST`, PostgreSQL selects standbys by priority order. With `ANY`, acknowledgements can be required from any count in the list. Verify syntax and semantics for your deployed PostgreSQL major version.

### 6.5. Synchronous Replication Does Not Create an HA Manager

Synchronous replication governs commit acknowledgements. It does not detect dead nodes, fence old primaries, choose new nodes, update DNS, or guarantee control-plane quorum on its own.

### 6.6. Conditional RPO 0

Zero data loss for acknowledged commits is achieved only when:

- Transactions actually use an appropriate synchronous commit level.
- The standby was confirmed synchronous per config at commit time.
- Promotion selects the exact standby that received/flushed the required WAL.
- No writes were acknowledged under an async override.
- Fencing prevents the old primary from continuing to accept writes.
- Storage and system failure assumptions hold true.

Merely having `synchronous_commit = on` in a config file is not enough to claim RPO 0 across every transaction and every failure scenario.

### 6.7. Cross-Region Synchronous Replication

Placing a synchronous standby in a distant region raises commit latency by the network round-trip time and hurts availability if the inter-region link drops. Many architectures choose synchronous replication within a nearby region/zone and asynchronous DR in another region. Choices must reflect RPO, latency budgets, and failure models.

## 7. Network Failures: Distinguish Which Path Broke

"Network down" has many meanings. Outcomes differ depending on which link failed.

### 7.1. Client Cannot Reach Primary

Primary and standby remain healthy and replication keeps running, yet applications cannot connect to the primary. If health checks rely only on client-side errors, the system might trigger an unnecessary failover.

Inspect:

- Load balancer health checks.
- Routing/security groups/firewalls.
- DNS resolution.
- Client subnets and application egress.
- TLS/proxy paths.
- Direct connectivity from an independent probe.

### 7.2. Primary Cannot Reach Standby

The primary can continue accepting writes while the standby stops receiving WAL. Under async replication, lag grows and RPO worsens. Under synchronous replication, commits needing synchronous acknowledgement may block or wait per timeout/config.

Never automatically promote a standby merely because the replication link dropped: the primary may still be alive and accepting writes. Promoting while the old primary is unfenced can cause split-brain.

### 7.3. Standby Cannot Reach Primary

The standby stops receiving WAL and replay lag rises. An HA manager must evaluate whether the standby is truly eligible for promotion based on topology, leader leases, quorum, and data freshness.

### 7.4. Node Cannot Reach DCS/Quorum

If the HA manager uses etcd, Consul, or a distributed configuration store, losing contact with the DCS leaves the node unable to tell whether it still holds leadership.

DCS quorum and PostgreSQL replication are two separate layers. A node can still have a running PostgreSQL process while losing leader coordination authority. Fail-closed policies and proper fencing are required.

### 7.5. Asymmetric Network Partitions

The primary may communicate with some nodes while failing to reach others. Health checks from a single vantage point can draw wrong conclusions. Drill from multiple vantage points and verify bidirectional paths.

### 7.6. Latency and Packet Loss

A network does not need a complete outage to cause failures. High latency, jitter, and packet loss can cause replication timeouts, health-check flapping, connection pool retries, and sluggish synchronous commits. Drills should include both soft faults and hard faults.

## 8. Split-Brain and Fencing

### 8.1. What Is Split-Brain?

Split-brain happens when two nodes both believe they are primary and simultaneously accept writes. This can create two independent WAL/data histories, causing divergence and making data reconciliation very difficult or impossible to automate.

### 8.2. Why Are Network Partitions Dangerous?

The old primary may simply be isolated from the HA manager or standby while remaining reachable by applications from another network. If the standby is promoted concurrently, two primaries can serve writes at once.

### 8.3. What Is Fencing?

Fencing is the action of guaranteeing the old node cannot continue writing or serving as primary before the new node is promoted.

Fencing methods depend on the environment:

- Power fencing/STONITH: shut down the old node via out-of-band management or a cloud API.
- Network fencing: block client and replication traffic to the old node.
- Storage fencing: revoke access to shared storage in shared-storage architectures.
- Orchestrator fencing: pair lease/leader state with mechanisms stopping a node that lost authority from serving.

Fencing must be proven effective. Changing DNS alone is not fencing because clients may keep old connections or hit direct IPs.

### 8.4. Promote Only After Verifying the Old Primary

The runbook must specify explicit conditions: the old node is powered off, isolated from all write paths, or the HA manager has a reliable fencing mechanism. If it cannot be proven, do not auto-promote in a topology vulnerable to split-brain.

### 8.5. Never Use Ping as Proof a Node Is Dead

Ping failures can result from blocked ICMP, broken routes, or partitions while the PostgreSQL process remains active. Multiple health signals and fencing are required.

### 8.6. Verify After Fencing

Test from network/application paths whether the old primary still accepts connections. Check cloud instance state, service state, routing, and DCS leases. Record evidence before promotion.

## 9. Quorum and HA Orchestration

### 9.1. Quorum

Quorum is the minimum number of members needed for a distributed system to make a consistent decision. With a three-node DCS, many deployments need a majority of nodes to keep committing state. Upon losing quorum, the system may refuse leader changes to prevent two sides from taking control.

### 9.2. Witness

A witness can help arbitrate in certain architectures, but must be a member with genuine quorum semantics. A tiny VM merely running health checks is not automatically a safe witness.

### 9.3. PostgreSQL Does Not Provide Complete Failover Orchestration on Its Own

PostgreSQL provides streaming replication, synchronous replication, and promotion functions. Automatic primary failure detection, leader election, fencing, routing, and lifecycle are typically handled by external tooling such as Patroni with a DCS, repmgr, or a managed database platform.

Do not mix APIs/commands across tools. Execute drills using the exact tool and version deployed.

### 9.4. Leader Lease

Some HA managers use time-bounded leases/locks to identify the leader. A node losing DCS connectivity can lose leader authority when its lease expires. Verify timing, clock assumptions, renewal, and fencing behavior.

### 9.5. Quorum Does Not Guarantee the Newest Standby

Quorum answers who holds coordination authority; it does not automatically ensure the selected node has the latest WAL. You need a candidate selection policy and data-loss checks.

## 10. PostgreSQL Process Loss and Server Loss

### 10.1. Process Crash

The PostgreSQL process can crash due to bugs, OOM kills, invalid extensions, resource exhaustion, or OS errors. The host remains up and reachable via SSH/management plane.

Drills must check:

- Does the process supervisor restart the process?
- How does the HA manager distinguish a restart from a node failure?
- Does WAL crash recovery complete?
- Do health checks report healthy only after the database accepts required connections/queries?
- Is failover triggered prematurely during a brief process restart?

### 10.2. Complete Host/VM Loss

A node can lose power, suffer a hypervisor crash, have its VM terminated, or become unreachable. Standbys must be evaluated for promotion. The old primary must be fenced before another node accepts writes.

### 10.3. Storage Failure

The host may stay alive while the volume holding `PGDATA` or WAL detaches, turns read-only, suffers extreme latency, or throws I/O errors. A TCP port health check can miss storage failures.

Do not keep retrying restarts on a failing volume. Follow storage runbooks to assess recoverability, fencing, and backup/replica sources.

### 10.4. Disk Full

Full WAL, log, or data volumes can cause writes to fail or stop normal server operation. Drill early alerting and capacity response. Never manually delete files in `PGDATA` or `pg_wal`.

### 10.5. Restart Is Not Failover

If a process restarts quickly and crash recovery finishes, promoting a standby may be unnecessary. However, if a restart loop persists or the host is unsafe, HA policy may require failover. Decision thresholds must be explicit and tested.

## 11. Availability Zone or Region Loss

### 11.1. Zone Loss

A zone failure can take out the primary, some standbys, network paths, or DCS members. The design should keep database candidates and remaining quorum across independent zones per the failure model.

### 11.2. Region Loss

A region outage can simultaneously impact:

- Primary and same-region standbys.
- Load balancers and private DNS.
- DCS/control plane.
- Application services.
- Backup credentials or KMS access.
- Monitoring/alerting endpoints.
- NAT, routing, and service dependencies.

### 11.3. Cross-Region Standby

A standby in another region can serve as a DR candidate. If asynchronous, unreceived WAL can be lost. Measure RPO against replay position and transactions committed on the primary.

### 11.4. Cross-Region WAL Archive

An off-region WAL archive lets you rebuild the cluster if standbys are unavailable. PITR requires base backups and continuous WAL; having only an old snapshot yields an older recovery point.

### 11.5. The New Region Needs Complete Infrastructure

Before declaring DR ready, verify:

- Compute capacity and PostgreSQL version.
- Storage throughput/capacity.
- Networks, subnets, firewalls, and private endpoints.
- Secrets, certificates, and KMS keys.
- DNS/traffic routing.
- Application images/configuration.
- Observability and alert delivery.
- External integrations and data dependencies.
- Operator access permissions when the primary region is down.

### 11.6. DR Activation Is a Business Decision

Runbooks must specify who has authority to declare the primary region unrecoverable, when to activate DR, how to handle unreplicated data, and conditions for returning to the old region.

### 11.7. Never Let Two Regions Accept Writes Simultaneously

After the DR region promotes and serves writes, when the old region returns it must be fenced and treated as holding an old history. Never open traffic to both primaries simultaneously unless using a purpose-built multi-writer architecture.

## 12. Designing a Failure Matrix

Before game day, build a matrix of scenarios, detection signals, expected behaviors, and success criteria.

| Scenario | Injected failure | Expected behavior | Risks to verify |
| --- | --- | --- | --- |
| Client path down | App cannot reach primary | Distinguish routing issue from DB failure | Unnecessary failover |
| Replication link down | Primary stops sending WAL to standby | Alert lag, keep primary or handle per policy | Data loss if promoting stale standby |
| Primary isolated from DCS | Node loses quorum/lease | Fencing and safe leader decision | Split-brain |
| Standby lost | Replica process/host stops | Primary continues per policy, alert redundancy loss | No remaining candidate |
| Primary process crash | PostgreSQL stops | Restart or failover per threshold | Flapping |
| Primary host lost | Node unreachable | Fence and promote candidate | RPO |
| Storage failure | Data/WAL volume errors | Isolate, restore/replica recovery | Corruption or repeated restarts |
| Zone outage | Multiple nodes/paths lost together | Pick candidate in surviving zone | Quorum placement |
| Region outage | Entire region unavailable | Activate DR region | WAL lag, DNS, dependencies |
| DNS stale | Client uses old endpoint | Route updates and proper reconnect | Stale caches/pools |
| DCS quorum loss | Cannot make leader decisions | Fail closed per policy | Unsafe promotion |
| Slow network | Latency/loss increases | Alerts and timeout behavior | False failure detection |

## 13. Preparing a Safe Game Day

### 13.1. Define Concrete Objectives

Example: prove a primary host failure shifts writes to a standby within 120 seconds without losing acknowledged transactions beyond the committed RPO.

Never start with a vague goal like "see if HA works."

### 13.2. Choose the Environment

Prefer staging matching production topology: same PostgreSQL major version, HA manager, DCS, routing, connection pools, and replication settings. If testing in production, require an approved change window, owner, rollback conditions, and bounded blast radius per organizational process.

### 13.3. Record a Baseline

Before the drill, save:

- Primary identity and standby list.
- Timelines and LSN positions.
- Replication state/lag.
- Synchronous standby state.
- DCS quorum/leader.
- Disk/WAL/storage health.
- Current application endpoint.
- Active connection count.
- Error rate and transaction throughput.
- Committed transaction marker IDs.

### 13.4. Define Stop Conditions

Halt the drill if:

- Signs appear of two primaries accepting writes.
- Fencing cannot be proven.
- Quorum is unclear or DCS state is abnormal.
- RPO breaches acceptable thresholds.
- Storage/backups are impacted out of scope.
- Which node is primary cannot be determined.
- Application error rate or business impact exceeds limits.
- Rollback procedures become unavailable.

### 13.5. Assign Independent Roles

One person performs injection, one observes the database/HA manager, one monitors the application, and one holds authority to halt the drill. Small teams may combine roles, but the stop decision-maker must be designated beforehand.

### 13.6. Record Consistent Timestamps

Synchronize clocks via NTP/chrony or a managed time source. Record UTC timestamps for injection, detection, fencing, promotion, routing, first successful write, and validation.

## 14. Drilling Network Failures in a Lab Environment

### 14.1. Separate Network Paths

List actual ports and paths:

- Client/app to PostgreSQL endpoint.
- Primary to standby replication.
- Nodes to DCS.
- Nodes to DNS/load balancers.
- Backups/WAL archives to object storage.
- Operators to management plane.

Port 5432 is a common example for PostgreSQL, though deployments may use another port. DCS ports also depend on the tool.

### 14.2. Network Latency and Packet Loss

In a Linux lab, `tc netem` can simulate delay/loss on a chosen interface:

```bash
# Lab only: add delay and packet loss to the selected test interface.
sudo tc qdisc add dev eth0 root netem delay 200ms 50ms loss 2%

# Remove the injected rule after the drill.
sudo tc qdisc del dev eth0 root
```

Replace `eth0` with the verified test interface. This rule affects traffic on that interface; never run it on production or management interfaces without understanding blast radius.

### 14.3. Blocking the Replication Path

You can use lab-specific security groups/firewalls to block primary-standby connectivity for a bounded interval. Record the exact rule added so you remove the right one.

Never block all traffic on a host when the goal is only to test the replication link. Keep management access intact for observation and recovery.

### 14.4. Blocking the Client Path

Block only the application subnet to the database endpoint or test route. Confirm the primary remains healthy and standbys still receive WAL. The goal is to prove the system distinguishes a client-path failure from a database failure.

### 14.5. Blocking the DCS Path

In an HA manager lab, block the test node from reaching the DCS or take down selected DCS members to observe quorum/lease behavior. Never inject arbitrary partitions into a production control plane.

### 14.6. Restoring the Network

After removing the fault, check:

- Did TCP connections re-establish?
- Did the WAL receiver reconnect?
- Is replay lag shrinking?
- Do DCS members hold quorum?
- Is the old node still fenced?
- Are no two primaries accepting writes?

### 14.7. Never Treat a Network Partition as a Node Failure

This is the single most important rule of network drills. A node unreachable by an observer can still be alive and accepting writes via another path.

## 15. Drilling Process Crashes and Host Loss

### 15.1. PostgreSQL Process Restart

In the lab, stop the service in a planned way to observe the supervisor/HA manager:

```bash
sudo systemctl stop postgresql
sudo systemctl status postgresql
```

This is a controlled stop, not a power loss. It verifies health detection and service management.

### 15.2. Abrupt Process Crash

Use a test VM/container to simulate abrupt process termination. Document how it is performed and ensure no impact to shared storage or other hosts.

Never use `kill -9` in production as a substitute for a controlled drill.

### 15.3. Host Failure

Power off the test VM using hypervisor/cloud test controls or simulate host network isolation. Verify standby promotion and fencing of the old node.

### 15.4. Storage Detach/Error

If testing storage failure, use a test volume. Verify monitoring detects I/O errors, mount loss, or extreme latency. Never detach a volume holding production `PGDATA` as a test.

### 15.5. After the Old Host Returns

Never start the old node as primary. First determine the current role, fence/disable its write path, and prepare to rebuild it as a standby from the new primary.

## 16. Drilling Zone or Region Loss

### 16.1. Losing One Availability Zone

Scenario:

1. Map primary, standbys, and DCS members by zone.
2. Record baseline LSNs and transaction markers.
3. Network-isolate or stop test nodes in the selected zone.
4. Observe quorum and leader election.
5. Verify the old primary is fenced.
6. Promote a standby in a surviving zone.
7. Switch endpoints and reconnect applications.
8. Run transaction validation.
9. Restore the test zone and return the old node as a standby.

### 16.2. Region Loss

A DR scenario should exercise all dependencies:

1. Record baseline in the primary region.
2. Simulate the primary region being unreachable from the DR control plane.
3. Verify the DR activation decision per runbook.
4. Identify the latest recoverable WAL/base backup in the DR region.
5. Promote the DR standby or restore from backup/WAL archive.
6. Stand up/verify app dependencies in DR.
7. Switch DNS/traffic.
8. Run smoke tests and data reconciliation.
9. Record RPO/RTO.
10. Plan failback separately.

### 16.3. Do Not Destroy a Region to Test

You can use network policies, test accounts, test VPCs, test clusters, or bounded game days. The goal is simulating primary-region unavailability from DR's perspective without deleting real resources.

### 16.4. Verify Independent Control Planes

Some cloud operations depend on a regional/account control plane. If that control plane itself is impacted, operators may be unable to launch VMs, modify firewalls, or update DNS. Test permissions and automation from another failure domain.

### 16.5. Backups and WAL Archives Must Be Off-Region

If base backups/WAL archives live solely in the primary region, a region outage can leave DR unable to rebuild the cluster. Also verify object metadata, KMS keys, credentials, and download capability.

## 17. Observing Replication Before and During Drills

### 17.1. Primary Replication State

On the primary:

```sql
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
FROM pg_catalog.pg_stat_replication
ORDER BY application_name;
```

`sync_state` helps identify whether a standby is currently synchronous or async per config. Read alongside `synchronous_standby_names` and transaction settings.

### 17.2. Standby Receiver State

On the standby:

```sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    received_tli,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time
FROM pg_catalog.pg_stat_wal_receiver;
```

If the view returns no rows, the standby may lack an active WAL receiver connection. Cross-check logs and `pg_is_in_recovery()`.

### 17.3. Receive and Replay Positions

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit_time;
```

Receive LSN and replay LSN can differ. A standby may have received WAL without finishing replay yet.

### 17.4. Calculating WAL Distance

On the standby, when both LSNs exist:

```sql
SELECT pg_wal_lsn_diff(
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn()
) AS received_not_replayed_bytes;
```

This is un-replayed WAL address space, not exact lag duration. Combine with timestamps and workload context.

### 17.5. Verify Primary Identity

Record system identifier and timeline/cluster identity using tools matching your version. Do not rely solely on hostnames or database names when multiple clusters share similar names.

## 18. Measuring RPO With Transaction Markers

### 18.1. Create a Marker Workload

In the lab, create a simple marker table on the primary:

```sql
CREATE TABLE IF NOT EXISTS ha_drill_markers (
    marker_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    drill_id text NOT NULL,
    committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    note text
);
```

A test client writes markers periodically, recording each marker ID and when the client received commit success.

### 18.2. Record Acknowledged Transactions

Log each marker to an observer outside the database or a test file with synchronized timestamps. The goal is knowing exactly which transactions were acknowledged to the client before fault injection began.

### 18.3. After Promotion

On the new primary, read the marker IDs. Compare the set acknowledged before failure against the set present after recovery.

### 18.4. Calculate the Data-Loss Window

Find the last marker acknowledged before the incident that is absent on the new primary. The timestamp difference between that marker and the failure/last surviving commit estimates actual RPO.

If zero acknowledged markers were lost, record that result under those exact test conditions; do not generalize it into a zero-data-loss guarantee for every transaction and failure mode.

### 18.5. Idempotency

A client may not know whether a commit succeeded or the response was lost when the connection severed. Use idempotency keys or transaction IDs in the lab to distinguish duplicate retries from genuinely lost transactions.

## 19. Applications, DNS, and Connection Pools

### 19.1. Database Promotion Alone Does Not Recover the Application

Applications may still hold connections to the old primary. Old TCP connections do not migrate automatically to the new primary. Pools must detect failed connections, evict stale ones, and open new connections to the current endpoint.

### 19.2. DNS TTL Is Not a Guaranteed Switchover Time

Resolvers, JVMs, OSes, container runtimes, and connection pools can cache DNS longer than expected TTLs. Load balancers/proxies have their own health checks and routing behavior. Measure directly from application processes.

### 19.3. Stable Endpoints

Use a stable endpoint via load balancer/proxy or DNS failover per architecture. The endpoint must route to the right new primary and reject writes against read-only standbys.

### 19.4. Retry Policy

Retries on connection/primary shutdown errors should include:

- Backoff with jitter.
- Bounded retry duration.
- Distinguishing transient errors from constraint/business errors.
- Idempotency for operations that may have committed when responses were lost.
- Overall timeout to prevent infinite retries.
- Circuit breakers when downstream is not yet ready.

### 19.5. SQLSTATE and Reconnect

Applications may receive connection exceptions or server shutdown errors during failover. Classify SQLSTATEs per driver/version rather than relying on fixed error message strings. When a connection drops, in-flight transactions may have unknown outcomes to the client; idempotency/reconciliation checks are needed.

### 19.6. Read/Write Routing

If read replicas exist, applications need to know which endpoints are read-only and which is primary. After promotion, routing metadata must update so writes do not keep targeting the old node and reads do not read stale data outside SLA.

### 19.7. Connection Storms

When thousands of clients reconnect simultaneously, the new primary can overload. Use pool limits, staggered reconnects, backoff, and appropriate connection proxies. Drills must measure connection establishment rate and CPU/memory.

## 20. Checking Consistency After Failover

### 20.1. Server State

Confirm:

- Only one primary is permitted to accept writes.
- Remaining standbys follow the right timeline.
- WAL receiver/sender states are healthy.
- No stale leader lease remains.
- The old node is fenced.
- Replication slots/standby connections match the topology.

### 20.2. Data Checks

Run verification queries for:

- Last committed marker.
- Row counts on critical tables.
- Business aggregates.
- Unique keys and foreign keys.
- Transaction records near the time of failure.
- Sequence values if cutover occurred.
- Replicated data per publication if using logical replication.

### 20.3. Sequence State

With physical replication, sequence state is included in the physical data stream. With native logical replication, sequence state is not replicated like ordinary row changes. If using logical migration/cutover, synchronize sequence values per runbook to avoid duplicate IDs.

### 20.4. Do Not Only Check SELECT 1

`SELECT 1` proves the server accepts connections and executes a trivial query. It does not prove applications can write, commit, read back data, or invoke dependencies.

### 20.5. Smoke Tests Along Business Paths

Execute a controlled test transaction: create a record, commit, read back, verify test-environment side effects, and confirm no duplicates occurred. Use synthetic accounts/orders to avoid creating real transactions.

## 21. Failback: Bringing the Old Node Back

### 21.1. The Old Primary Does Not Automatically Return as Primary

After failover, the old node may hold a diverged WAL history. Never restart it as an independent primary or route applications to it.

### 21.2. Rebuild as a Standby

The safe path is typically bringing the old primary back as a standby of the current primary. Depending on divergence, use `pg_rewind` if prerequisites are met or take a fresh base backup.

### 21.3. pg_rewind

`pg_rewind` can synchronize a diverged data directory back to a source cluster sharing lineage when conditions hold. Typically this requires data checksums or `wal_log_hints` enabled beforehand, sufficient retained WAL, and matching major versions. Check documentation for your exact version and follow the runbook.

If prerequisites are unmet, use a fresh base backup. Never assume `pg_rewind` can always repair any old primary.

### 21.4. Fencing Remains Necessary

Keep the old primary blocked from accepting writes throughout the rebuild. Only admit it to the replication topology after verifying the data directory and role.

### 21.5. Do Not Fail Back Merely to Return to the Old Hostname

Failback is an operational change carrying risk. Execute it only for valid capacity, latency, topology, or maintenance reasons; planned switchover requires verifying standby catch-up and having a rollback plan.

### 21.6. Verify After Failback

Verify replication state, timelines, LSN positions, synchronous standby configuration, routing, backup jobs, and monitoring. Ensure full HA topology is restored after the incident.

## 22. Backups and DR Differ From Standbys

### 22.1. Standbys Replicate Logical Mistakes

If a user accidentally runs `DELETE` or an application writes bad data, physical standbys replay that change too. A standby is not an immutable historical copy.

### 22.2. Backups Preserve Older Recovery Points

Base backups and WAL archives allow PITR back before the mistake if retention suffices. Backups must reside in an independent failure domain.

### 22.3. Snapshots and Archives

Storage snapshots can spin up volumes quickly, yet require consistency procedures and needed WAL. WAL archives must form a continuous chain and be verified.

### 22.4. DR Tests Must Exercise Restoring From Backups

A DR region should not rely solely on a standby. Practice standing up a cluster from base backups and WAL archives in an isolated environment to prove an independent recovery path.

### 22.5. Backup Restore and Failover Are Two Different Drills

Failover tests continuity from a standby. Restore drills test recovery when replicas/primary suffer logical corruption or storage loss. Both are required.

## 23. Runbooks for Each Scenario

### 23.1. Network Partition

1. Identify which path broke: client, replication, DCS, or management.
2. Collect health signals from multiple vantage points.
3. Check whether the primary still accepts writes from any client.
4. Check DCS quorum/leader lease.
5. Verify fencing before promotion.
6. Assess standby freshness and RPO.
7. Promote per HA manager/runbook if eligible.
8. Switch endpoints and reconnect clients.
9. Verify the old primary accepts no writes.
10. Restore networking and rejoin the old node as a standby.

### 23.2. Primary Process/Host Loss

1. Confirm process/host state and failure scope.
2. Inspect DCS/HA manager.
3. Identify standby candidate and replay position.
4. Fence old primary or verify host power-off.
5. Promote candidate using deployed tooling.
6. Switch endpoints and reconnect applications.
7. Verify transaction markers and business data.
8. Restore redundancy with a new standby.
9. Plan rebuilding the old node.
10. Measure RPO/RTO and preserve logs.

### 23.3. Region Loss

1. Confirm the primary region is genuinely unable to serve.
2. Verify DR authority and activation criteria.
3. Select the appropriate standby or base backup/WAL archive.
4. Estimate data loss from the latest recoverable LSN.
5. Fence the old region if possible and prevent split-brain if it returns.
6. Promote/restore the database in the DR region.
7. Stand up apps, secrets, networking, and dependencies.
8. Shift DNS/traffic.
9. Run data/application validation.
10. Record RPO/RTO and plan failback separately.

## 24. Measuring Drill Outcomes

### 24.1. Timestamps to Record

| Timestamp | Meaning |
| --- | --- |
| T0 | Fault injection starts |
| T1 | Monitoring detects fault |
| T2 | Incident/failover decision |
| T3 | Fencing completes |
| T4 | Promotion completes |
| T5 | Endpoint/routing updated |
| T6 | Application reconnect succeeds |
| T7 | First successful write |
| T8 | Data validation completes |
| T9 | Full service restored |

### 24.2. Derived Metrics

- Detection time = T1 - T0.
- Decision time = T2 - T1.
- Fencing time = T3 - T2.
- Promotion time = T4 - T3.
- Routing time = T5 - T4.
- Application recovery time = T7 - T5.
- End-to-end RTO = T9 - T0 per defined service-restored criteria.
- RPO = span of acknowledged data absent from recovered state.

### 24.3. Record Secondary Errors

Track error rates, failed transactions, retry counts, duplicate requests, connection storms, CPU/memory, WAL lag, and disk usage.

### 24.4. Outcomes Are More Than Pass/Fail

A drill may meet RTO yet reveal RPO worse than committed; or data may stay intact while client reconnect takes too long. Record each dimension separately.

### 24.5. Evidence

Save timelines, HA manager logs, PostgreSQL logs, DCS state, LSN snapshots, transaction markers, DNS/LB changes, application traces, and decision approvals.

## 25. Drill Frequency and Levels

### 25.1. Tabletop Exercise

The team walks through runbooks and explains who does what when a failure hits, without injection. Used to uncover missing owners, ambiguous decisions, and outdated contact details.

### 25.2. Component Drill

Test a single process/connection or network path in the lab. Goal is understanding each component's behavior.

### 25.3. Staging Failover Drill

Execute end-to-end failover with applications, routing, and monitoring matching production.

### 25.4. Zone/Region DR Drill

Drill periodically in an environment with bounded blast radius. Test both database and application dependencies.

### 25.5. After Architectural Changes

Re-drill whenever changing PostgreSQL major version, HA manager, DCS topology, networking, DNS, storage, synchronous replication, or connection pools.

### 25.6. Cadence by Criticality

Critical services may require quarterly tabletops, more frequent staging failovers, and periodic DR tests per compliance/business needs. Base schedules on risk and operational readiness rather than arbitrary calendars.

## 26. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| Having a standby means having HA | Requires detection, fencing, promotion, routing, and validation |
| Failover never loses data | Async replication can lose acknowledged commits |
| `synchronous_commit = on` guarantees RPO 0 in every scenario | Requires an active synchronous standby, right candidate, and fencing |
| Cannot ping means primary is dead | May simply be a network partition |
| Blocking client path means standby must promote | Database may be healthy and replication normal |
| Standby receiving no WAL means primary is dead | Replication path may be broken while primary still writes |
| DCS quorum and PostgreSQL replication are the same | They are two separate layers |
| Quorum guarantees picking the newest replica | Quorum decides coordination authority, not data freshness |
| Changing DNS is fencing | Old node can still accept writes via old connections/direct IPs |
| Promote first, fence later | Risks split-brain |
| Successful switchover proves failover works | Failure paths may involve different quorum/fencing/network conditions |
| Promotion means service is restored | App reconnect and data validation are still required |
| DNS TTL equals reconnect time | Caches/pools can hold old state longer |
| Retrying every transaction is safe | Commit outcome may be unknown; idempotency is required |
| Zero replay lag proves all business data is processed | Transaction/app/downstream state must be verified |
| Region loss only needs database promotion | Apps, secrets, networking, DNS, and dependencies are also needed |
| Same-region backups suffice for region DR | Region outage can wipe out those backups too |
| Standbys replace backups | Logical corruption replicates too |
| Old primary can restart normally | Must be fenced and rebuilt/rejoined as standby |
| `pg_rewind` always fixes any old primary | Has prerequisites and WAL/common-history requirements |
| Failback must happen immediately | Perform only with clear justification and a safe runbook |
| One successful drill is enough | Configs and dependencies evolve; drill regularly |
| RTO is just promotion time | End-to-end RTO includes detection, routing, reconnect, and validation |
| RPO can be inferred from average lag | Measure with actual acknowledged transactions |
| Region DR needs no testing because standby is streaming | Control planes and app dependencies must also be tested |

## 27. Practice Exercises With Answers

Exercises assume you have a dedicated PostgreSQL HA lab. Never create network partitions, stop hosts, or promote nodes in production just to practice.

### Exercise 1. How does HA differ from DR?

**Answer:** HA minimizes outages from routine failures; DR restores service after major disasters such as region or primary failure-domain loss.

### Exercise 2. What is failover?

**Answer:** Shifting service from a failed primary to a standby promoted to become the new primary.

### Exercise 3. What is switchover?

**Answer:** A planned and controlled transfer of primary/standby roles.

### Exercise 4. What is RPO?

**Answer:** The maximum amount of data an organization tolerates losing for a given failure scenario.

### Exercise 5. What is RTO?

**Answer:** The maximum acceptable duration to restore service according to defined criteria.

### Exercise 6. Why is RTO not just promotion time?

**Answer:** It also includes detection, fencing, routing, reconnect, smoke tests, and data validation.

### Exercise 7. When can asynchronous replication lose data?

**Answer:** When the primary is lost before the latest WAL is received/flushed by the standby and that standby is promoted.

### Exercise 8. How does synchronous replication help?

**Answer:** Commits wait for acknowledgement from synchronous standbys per configuration, reducing the risk of losing acknowledged transactions.

### Exercise 9. What does synchronous_commit = remote_write wait for?

**Answer:** The synchronous standby writing WAL to the operating system, not necessarily durable remote flush.

### Exercise 10. What does synchronous_commit = on wait for?

**Answer:** Local WAL flush and remote synchronous standby flush per configuration.

### Exercise 11. How does remote_apply differ from on?

**Answer:** `remote_apply` waits for the standby to replay the transaction so it becomes visible there.

### Exercise 12. What is the role of synchronous_standby_names?

**Answer:** Selects synchronous standbys and the required acknowledgement count under `FIRST`/`ANY`.

### Exercise 13. Does synchronous replication fence the old primary automatically?

**Answer:** No. Separate fencing/HA orchestration is required.

### Exercise 14. What is split-brain?

**Answer:** Two nodes simultaneously accepting writes while each believes it is primary.

### Exercise 15. What is fencing?

**Answer:** Preventing the old node from continuing to accept writes before promoting a new node.

### Exercise 16. Is changing DNS considered fencing?

**Answer:** No. Existing clients or direct IP paths can still reach the old node.

### Exercise 17. How does a network partition differ from a server crash?

**Answer:** A partition breaks a communication path; the server may remain alive and accept writes from another path.

### Exercise 18. Does blocking the client path necessarily require failover?

**Answer:** No. The primary may be healthy and standbys still synchronized.

### Exercise 19. Does blocking the replication path mean the primary is dead?

**Answer:** No. The primary may continue accepting writes while standbys lag.

### Exercise 20. What is DCS quorum used for?

**Answer:** Supporting consistent leader/coordination decisions in a distributed HA manager.

### Exercise 21. Does native PostgreSQL replication provide full leader election on its own?

**Answer:** No. An external HA manager/orchestrator is typically needed.

### Exercise 22. What is the significance of a witness?

**Answer:** A member assisting quorum/arbitration under the system's semantics, not merely a health-check VM.

### Exercise 23. Why not use ping as proof a node is dead?

**Answer:** ICMP can be blocked or routes broken while PostgreSQL continues operating.

### Exercise 24. How does a process crash differ from host loss?

**Answer:** A process crash only stops PostgreSQL/the service; host loss makes the entire node unreachable.

### Exercise 25. What can disk full affect?

**Answer:** WAL/data writes can fail and the server may stop operating normally.

### Exercise 26. Why never manually delete files in pg_wal?

**Answer:** PostgreSQL manages WAL lifecycle; manual deletion can break recovery and replication.

### Exercise 27. What does a region outage affect besides the database?

**Answer:** Apps, networking, DNS, control planes, secrets, KMS, monitoring, and external dependencies.

### Exercise 28. Why are off-region base backups and WAL archives needed?

**Answer:** To rebuild the cluster when the primary region and storage within it become inaccessible.

### Exercise 29. What is the trade-off of a cross-region async replica?

**Answer:** Lower commit latency, but a potential data-loss window if the primary region is lost.

### Exercise 30. Why measure LSNs before a drill?

**Answer:** As a baseline to compare WAL received/replayed and estimate data freshness.

### Exercise 31. Which view on the primary shows replication state?

**Answer:** `pg_stat_replication`.

### Exercise 32. Which view on a standby shows the WAL receiver?

**Answer:** `pg_stat_wal_receiver`.

### Exercise 33. Which function checks whether a standby is in recovery?

**Answer:** `pg_is_in_recovery()`.

### Exercise 34. How do receive LSN and replay LSN differ?

**Answer:** Receive is WAL received; replay is WAL applied to database state.

### Exercise 35. What is pg_wal_lsn_diff used for?

**Answer:** Computing the byte distance between two WAL positions, not directly measuring lag time.

### Exercise 36. What do transaction markers help measure?

**Answer:** Whether transactions acknowledged before failure still exist after promotion.

### Exercise 37. Why is idempotency needed in failover drills?

**Answer:** Clients can lose the response after commit succeeded, and retries could create duplicates.

### Exercise 38. Does DNS TTL guarantee applications reconnect on time?

**Answer:** No. Resolvers, OSes, and connection pools can cache or retain connections longer.

### Exercise 39. What must connection pools do after failover?

**Answer:** Evict stale connections and open new connections to the current primary endpoint.

### Exercise 40. Why must transaction retries be cautious?

**Answer:** Clients may not know whether the previous transaction committed; idempotency/reconciliation is required.

### Exercise 41. Does SELECT 1 prove the service is fully restored?

**Answer:** No. Write/commit/read paths and business dependencies must be tested.

### Exercise 42. Why verify that only one primary accepts writes?

**Answer:** To detect and prevent split-brain.

### Exercise 43. After failover, what should happen to the old primary?

**Answer:** Be fenced and rebuilt/rejoined as a standby of the new primary.

### Exercise 44. When is pg_rewind used?

**Answer:** Synchronizing a diverged data directory back to a source cluster sharing history when prerequisites are met.

### Exercise 45. When is a fresh base backup needed instead of pg_rewind?

**Answer:** When prerequisites are unmet, required WAL/common history is gone, or rewind is unsuitable.

### Exercise 46. Why does failback need a dedicated plan?

**Answer:** The old primary may hold a diverged history; transferring roles requires catch-up, fencing, routing, and validation.

### Exercise 47. What is a game day?

**Answer:** A controlled failure-injection drill to measure detection, recovery, and improve runbooks.

### Exercise 48. How does a tabletop exercise differ from fault injection?

**Answer:** A tabletop walks through runbooks without inducing real faults; fault injection creates controlled failures in a chosen environment.

### Exercise 49. Why are stop conditions needed?

**Answer:** To halt the drill if split-brain risk arises, RPO is breached, or blast radius expands out of bounds.

### Exercise 50. Who should hold authority to stop a drill?

**Answer:** A pre-designated person, independent from the person executing fault injection when possible.

### Exercise 51. Which timestamps should be recorded?

**Answer:** Injection, detection, decision, fencing, promotion, routing, first successful write, and validation complete.

### Exercise 52. How is detection time calculated?

**Answer:** T1 - T0, where T0 is fault injection start and T1 is when monitoring detects it.

### Exercise 53. How is end-to-end RTO calculated?

**Answer:** From fault start until the service satisfies defined restored criteria, including validation if part of the criteria.

### Exercise 54. How should RPO be measured?

**Answer:** Using acknowledged transaction markers and recovered data, not just an average lag metric.

### Exercise 55. Why test the control plane in the DR region?

**Answer:** If you cannot provision compute, networking, update DNS, or fetch secrets, the DR region may fail to start the service.

### Exercise 56. How can a region outage affect KMS/secrets?

**Answer:** Key/secret access may depend on the primary region or control plane; test decryption permissions and credentials in DR.

### Exercise 57. What is the cost of a distant synchronous standby?

**Answer:** Commit latency increases by network RTT and availability can drop when the inter-region link fails.

### Exercise 58. Why is one successful drill not enough?

**Answer:** Topology, software, networks, and dependencies change; drill regularly and after major changes.

### Exercise 59. When can a drill be declared passed?

**Answer:** When RPO/RTO, fencing, single-primary state, application validation, and evidence all meet defined criteria.

### Exercise 60. Create a region-loss drill checklist

**Suggested answer:**

1. Define RPO/RTO and who holds DR activation authority.
2. Record baseline primary/standby LSNs, timelines, and acknowledged markers.
3. Verify off-region base backups/WAL archives and KMS access.
4. Simulate primary-region unavailability from DR's perspective.
5. Check quorum, leader decision, and fencing.
6. Choose a standby/backup with suitable WAL freshness.
7. Promote or restore the database in the DR region.
8. Stand up applications, networking, secrets, DNS, and dependencies.
9. Run write/read smoke tests and verify markers/business data.
10. Record RPO/RTO, retain evidence, and plan failback separately.

## 28. Production Checklist

| Check | Requirement to guarantee |
| --- | --- |
| Failure domains | Primary, standbys, quorum, and apps do not unnecessarily share one failure domain |
| RPO/RTO | Separate targets defined per scenario |
| Replication mode | Sync/async trade-offs clearly documented |
| `synchronous_commit` | Matches durability requirements |
| `synchronous_standby_names` | Candidate/acknowledgement policy explicit |
| HA manager | Version, leader election, and failover policy tested |
| DCS quorum | Sufficient members and proper placement |
| Fencing | Able to prove old primary accepts no writes |
| Split-brain | Single-primary verification after promotion |
| Network paths | Client, replication, DCS, and management tested separately in drills |
| Health checks | Multiple vantage points, avoiding false failovers |
| Replication lag | Baseline and alerts configured |
| LSN markers | Able to measure acknowledged transactions |
| Host failure | Both process and VM/host loss drilled |
| Zone failure | Candidate and quorum available in surviving zones |
| Region DR | Includes both database and application dependencies |
| Backups | Off-region base backups/WAL archives |
| KMS/secrets | Accessible in DR |
| DNS/LB | Routing updates and health checks verified |
| Connection pools | Reconnect, stale connection cleanup, and retries |
| Idempotency | Handles unknown commit outcomes |
| Data validation | Business smoke tests and reconciliation |
| Failback | Old primary fenced/rebuilt as standby |
| Observability | PostgreSQL, HA manager, DCS, network, app logs |
| Stop conditions | Agreed upon before the drill |
| Drill owner | Assigned roles for inject, observe, and stop |
| Evidence | Timelines, logs, LSNs, markers, and routing changes |
| RPO/RTO report | Actual measured numbers |
| Restore drill | Backups tested independently of standbys |
| Review actions | Owner and due date for every gap |

## 29. Summary

Drilling network failures, server loss, and region outages proves that PostgreSQL HA/DR works under real failure conditions. A complete recovery workflow must handle detection, leader decision, fencing, promotion, routing, application reconnect, and data validation. Success is not merely a standby becoming primary; the system must prevent split-brain, stay within RPO, and restore application service within RTO.

Key principles:

1. **Distinguish HA and DR.** Same-region standbys do not protect against every region failure.
2. **Set RPO/RTO per scenario.** Measure acknowledged transactions and service restoration time.
3. **Understand sync/async trade-offs.** Synchronous replication can reduce data loss, but increases latency and standby dependency.
4. **A network partition is not a server crash.** An isolated node can still be alive and accepting writes.
5. **Fence before promotion.** Never allow two primaries to serve writes concurrently.
6. **Quorum and replication are two separate layers.** DCS governs leader coordination; WAL state governs data freshness.
7. **Never use ping as proof a node is dead.** Use multiple health signals and fencing.
8. **Test client, replication, and DCS paths separately.** Each failure type needs a distinct response.
9. **Region loss affects all dependencies.** Database, apps, networking, DNS, secrets, KMS, and control planes must all be tested.
10. **Measure RPO with transaction markers.** Lag metrics do not prove every acknowledged commit survived.
11. **Applications need reconnect and idempotency.** Failover can leave commit outcomes unknown to clients.
12. **The old primary must be rebuilt safely.** Never allow the old node to restart as primary after promotion.
13. **Backups do not replace standbys, and standbys do not replace backups.** Drill both failover and restore.
14. **Game days need stop conditions and evidence.** Control blast radius and measure every phase.
15. **Repeat after major changes.** Passing once does not guarantee future topology safety.

Evaluation model:

```text
Failure detected?
        |
        v
Failure domain identified accurately?
        |
        v
Old primary fenced?
        |
        v
Candidate has WAL meeting RPO?
        |
        v
Exactly one primary promoted?
        |
        v
Endpoints and clients reconnected?
        |
        v
Write/read business tests succeeded?
        |
        v
RPO/RTO targets met?
        |
        v
Evidence, review, and action owners
```

**Final review question:** "If the primary only loses connectivity to the DCS while still accepting writes from applications, does the system fence it before promoting a standby? If the primary region vanishes, does the DR region have sufficient WAL, compute, secrets, DNS, and application dependencies to serve? And have we measured with transaction markers that actual RPO/RTO meet targets?" An HA/DR design is only trustworthy when those questions have been answered with real drills and evidence.
