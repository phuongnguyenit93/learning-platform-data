# High Availability, Read Replicas, and Geo-Replication

An e-commerce system stores orders in a relational database on Azure. When a server fails, users must still be able to place orders. During peak hours, dozens of data-heavy reports must not slow down checkout transactions. If an Azure region suffers a prolonged outage, the company must be able to recover the system in another region.

Those three requirements sound similar, yet actually demand three distinct mechanisms:

- **High availability (HA)**: maintaining availability and failing over automatically or in a controlled manner to a standby component when a fault occurs within the design scope.
- **Read replicas**: creating copies to serve read queries and offload query load, typically with some replication delay.
- **Geo-replication**: replicating data across geographic regions to support remote reads or disaster recovery (DR) plans, with mechanisms and limits varying by service.

Do not lump all three concepts into a single "data backup" feature. A read replica **is not an immutable backup**, an HA standby **does not automatically serve read queries**, and geo-replication **does not guarantee zero RPO** when replication is asynchronous.

This lesson belongs to the **Relational Databases** chapter of the `CLOUD_PROVIDERS_AZURE` module. Within the Microsoft Azure ecosystem—from subscriptions, resource groups, and Microsoft Entra ID to VNets, compute, storage, databases, monitoring, and cost—the lesson focuses on availability design for **Azure SQL Database**, **Azure Database for PostgreSQL Flexible Server**, and **Azure Database for MySQL Flexible Server**. Exact capabilities depend on service, tier, version, region, and current policies.

> Resource names, server names, commands, and timestamps in this lesson are illustrative examples. Never perform failover, replica promotion, DNS changes, or topology modifications in Production without approval and a runbook. For SLA, limits, pricing, or regional availability decisions, verify current live details for your service and subscription at deployment time.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **HA, read replicas, geo-replication, backups/PITR, and disaster recovery**.
2. Explain **synchronous** vs. **asynchronous replication** along with latency, consistency, and data-loss trade-offs.
3. Define **RTO, RPO, availability targets**, fault scopes, and downtime cost.
4. Compare HA and read replicas across Azure SQL Database, PostgreSQL Flexible Server, and MySQL Flexible Server.
5. Design read/write strategies across primary, read endpoints, and replicas, handling **replication lag**.
6. Describe Azure SQL Database active geo-replication/failover groups and key nuances of cross-region read replicas on PostgreSQL/MySQL.
7. Distinguish **failover** from **replica promotion**, and assess data-loss risks during regional shifts.
8. Design private networking, TLS, identity, DNS, connection pooling, and appropriate read/write permissions.
9. Monitor replica lag, failover events, CPU, storage, connection counts, and error rates.
10. Plan failover/DR drill testing, failback, and data reconciliation.
11. Use the Portal and Azure CLI to inspect topology before risky operations.
12. Evaluate trade-offs among availability, consistency, performance, regional distance, and cost.

## 2. Opening Story: Three Incident Types, Three Mechanisms

An Orders API uses a SQL database with three requirements:

| Scenario | Question to Answer | Primary Mechanism |
|---|---|---|
| A compute/database host fails in the active region | How does the app keep connecting and writing? | Intra-region HA/failover per service/tier. |
| End-of-day reports scan millions of rows, spiking primary CPU | How to isolate read load from write transactions? | Read scale-out/read replicas, query optimization, and resource sizing. |
| The entire primary region misses recovery targets | How do data and apps shift to the standby region? | Geo-replication/geo-readable secondary, backups/restore, and DR runbook. |
| A developer accidentally runs `DELETE FROM Orders` with no `WHERE` clause | How to revert data to before the delete? | Backups, point-in-time restore, auditing, and recovery workflows. |

**Important note:** if a user accidentally deletes data, the delete may replicate immediately to standby and read replicas. Having HA or geo-replication **never replaces** backups/PITR and safeguards against destructive actions.

## 3. Fault Boundaries: Instance, Zone, and Region

Before picking features, know which failure scope the system is defending against.

```text
Azure geography
  ├── Region A (primary region)
  │    ├── Availability Zone 1
  │    │      └── Primary database/compute
  │    ├── Availability Zone 2
  │    │      └── HA standby (if supported by service/tier)
  │    └── Availability Zone 3
  │
  └── Region B (DR region)
       └── Geo-secondary / remote replica
```

- **Instance/host failure**: a compute node or service process crashes.
- **Availability Zone failure**: power/network/infrastructure disruption in one zone within a region, bounded to that zone.
- **Region outage**: regional-scale disruption potentially affecting many services simultaneously.
- **Data corruption/logical error**: erroneous write/delete or bad schema migration; replication can propagate the mistake.
- **Identity/network/configuration outage**: data is intact, yet apps cannot connect due to DNS, NSG, token, firewall, or config issues.

A database with a same-region secondary can survive certain node/zone faults, yet **does not protect against full region loss**. A geo-secondary in another region reduces regional risk, yet **does not protect the application** if APIs, secrets, Storage, or DNS lack matching DR plans.

## 4. Architectural Model: Primary, HA Standby, and Read Replicas

```text
                        Application
                       /           \
                Write traffic   Read-only traffic
                     |                |
                     v                v
             Primary database     Read endpoint
                     |                |
          +----------+-------+        |
          |                  |        v
          v                  v     Read replica R1
   HA standby         Local read replica
   (failover)          (asynchronous*)
          |
          | standby does not serve reads by default
          |
          +------------------+
                             |
                      Geo-secondary
                      Region B (DR)

* Exact sync mechanics depend on service/tier.
```

In practice, topologies differ:

- Some **Azure SQL Database** tiers use multiple replicas inside a managed HA architecture and may offer read scale-out; users do not always provision a separate "standby" resource manually.
- **PostgreSQL/MySQL Flexible Server HA standby** is strictly a failover component, not a read-only replica freely accepting queries.
- PostgreSQL/MySQL **read replicas** are provisioned with their own endpoints and use asynchronous replication per supported architecture.
- Azure SQL Database **geo-secondaries** are readable, yet their read role and failover mechanics differ from PostgreSQL/MySQL read replicas.

**Never use "secondary" as a standalone precise term** in runbooks. State explicitly whether it is an *HA standby*, *read replica*, *geo-secondary*, *backup copy*, or *promoted standalone server*.

## 5. Synchronous vs. Asynchronous Replication

### Synchronous Replication

In synchronous replication, commits may involve acknowledging data persistence on the standby component per service model. This lowers data-loss risk within the designed fault scope, at the cost of extra latency overhead and network-link dependency between components.

```text
Application
    |
    v
Primary ── sync replicate/ack mechanism ──> Standby
    |
    +── commit acknowledged per policy
```

Do not infer that all HA deployments guarantee **zero data loss in every failure**, or that clients never see errors during failover. Read commit contracts, durability, acknowledgment rules, and RPO per exact service and configuration.

### Asynchronous Replication

The primary can acknowledge a transaction before the replica receives and applies it.

```text
T0: Primary commits Order 1042
T1: API receives success result
T2: Replication stream ships changes
T3: Replica receives/applies Order 1042
```

Between T1 and T3, **replication lag** exists. If the primary fails at T2, transactions already acknowledged to the app may not have reached the replica. Promoting/failing over to a lagging replica risks losing those transactions.

### Comparison

| Property | Synchronous | Asynchronous |
|---|---|---|
| Commit latency | Potentially higher due to replica acknowledgment constraint. | Less tied to replica apply speed at commit time. |
| Reading from replica | Depends on replica type; synchronous standbys are not readable by default. | Read replicas are usually readable, possibly stale. |
| Un-replicated data risk on primary failure | Lower within guaranteed scope. | Risk of losing un-replicated committed data. |
| Suitability over long distances | Typically harder due to high latency. | Typically suited for geo-replication. |
| Impact when replica slows | Can affect commits/availability per design. | Lag rises, reads grow stale; primary keeps writing. |

## 6. RPO, RTO, and Availability Targets

Two core metrics:

- **Recovery Point Objective (RPO)**: maximum acceptable data loss upon recovery, measured by time interval or transactions absent at the recovery point.
- **Recovery Time Objective (RTO)**: maximum acceptable duration to restore service after an outage.

Example: 5-minute RPO, 30-minute RTO means the business tolerates losing up to ~5 minutes of data under the chosen measurement and must restore service within 30 minutes. These are **business targets**, not guarantees that any arbitrary replica achieves them.

### Requirements Table

| Workload | Target RPO | Target RTO | Design Direction |
|---|---:|---:|---|
| Paid orders | Very low | Short | HA, lag-monitored DR, outbox/reconciliation, backups, and tested failover. |
| Near-real-time sales dashboard | A few minutes | Tens of minutes | Read replicas, lag budget, cache/refresh. |
| Daily analytics reports | Hours | Hours | Replicas or ETL to analytics store; backups and rerun capability. |
| Test/lab data | Higher | Higher | Cost-saving SKUs, policy backups, and rebuild scripts. |

### Availability Does Not Equal Durability

A database can be unreachable for 10 minutes with zero lost data—**RTO suffers while RPO approaches 0**. Conversely, switching to a DR region in 2 minutes while losing 3 minutes of un-replicated transactions yields **better RTO but worse RPO**.

### Illustrative Downtime Calculation

For a 99.9% availability target over 30 days:

```text
30 days × 24 hours × 60 minutes = 43,200 minutes
0.1% × 43,200 = 43.2 minutes of unavailability
```

This is purely a 30-day illustrative calculation, **not an SLA for any Azure Database tier**. Vendor SLAs carry specific terms, scopes, and exclusions. Define end-to-end application SLOs, not just database uptime.

## 7. High Availability Within a Region

HA typically relies on failover to keep the logical database service running when a component fails. Options include:

- Replicas/standbys in the same Availability Zone or separate zones.
- Redundant data/compute architectures per service tier.
- Platform health detection and failover orchestration.
- Stable endpoints or service-managed rerouting.
- Client retries/reconnects when old connections close.

### What HA Does Not Do Automatically

1. Does not guarantee **zero downtime**: connections can reset and in-flight transactions can fail.
2. Does not automatically provide **read scaling** if the standby does not serve reads.
3. Does not replace **geo-DR** during full-region outages.
4. Does not fix bad SQL, broken schema migrations, or apps hitting the wrong database.
5. Does not auto-heal broken APIs, queues, Storage, or identities.
6. Does not replace backup plans and restore drills.

### Same-Zone vs. Zone-Redundant HA

**Same-zone HA** protects against certain instance/host faults within a single zone, yet both primary and standby can go down together if that zone fails.

**Zone-redundant HA** places the standby component in a separate zone where supported by service and region, mitigating single-zone risk. Also evaluate:

- Does the region have Availability Zones and does your SKU support them?
- Do storage/replication mechanisms meet durability and failover needs?
- Does the application tier also span multiple replicas/zones?
- Are network routes, private endpoints, firewalls, and dependencies zone-resilient?
- What are the added cost and latency?

**Enabling zone-redundant DB does not make the whole app zone-redundant.** An API running on one VM in Zone 1 still suffers an outage even if the database has a standby in Zone 2.

## 8. Azure SQL Database: Managed HA and Tier Effects

**Azure SQL Database** is a managed SQL service. HA is built into the service architecture; replica/compute layouts and zone redundancy depend on service tier, hardware, and region.

Common option groups:

- **General Purpose**: balanced price/performance for common workloads; managed compute/storage failover per tier design.
- **Business Critical/Premium**: suited for lower latency and higher I/O throughput; replica architecture may support **read scale-out**.
- **Hyperscale**: decoupled compute/storage for large data scales; supports configurable compute/read replicas.
- **Serverless** in supported configs: adds auto-scaling/auto-pause and cold start considerations; do not equate directly with provisioned-tier HA.
- **Zone redundancy**: available only on supported tiers/regions/hardware/options; verify the live database property.

Never assume every Azure SQL Database shares the same HA replica count, RTO, or regional zone-redundancy support.

### Does HA Automatically Switch Endpoints?

Applications typically connect to a **logical server/database endpoint** rather than a specific VM IP. Azure SQL Database orchestrates failover at the managed service layer. However:

- Existing SQL/TCP connections may drop.
- Uncommitted transactions roll back per SQL semantics.
- Connection pools may hold dead/stale connections.
- Apps must retry **transient faults**.
- Write operations must enforce idempotency when retrying uncertain outcomes.

**Never hard-code IPs of the SQL service or primary replica.** Use the service's FQDN and connection config.

## 9. PostgreSQL Flexible Server: HA Standby

**Azure Database for PostgreSQL Flexible Server** supports HA configurations under product-permitted conditions/tiers/regions, with same-zone or zone-redundant options. The platform orchestrates role switching between primary and standby if the primary fails.

```text
Application
     |
     v
PostgreSQL Flexible Server endpoint
     |
     +-- Primary (read/write) ── HA replication ──> Standby
                                                  (failover target)
```

Key points:

- **HA standby serves failover**, not an independent read-replica endpoint for offloading read queries.
- HA replication/commit mechanics follow product design; never transfer Azure SQL Database specifics to PostgreSQL.
- Failovers can happen due to maintenance, node faults, or defined platform conditions.
- Client connections can drop and require reconnects/retries.
- In-flight transactions must be handled by application logic.
- Zone-redundant HA requires compatible region, zones, SKU, and capacity.

### When Zone-Redundant Is Unavailable

If a region/tier/node size combination lacks zone-redundant HA or capacity, never pretend the environment is zone-resilient. Document clearly that actual protection is single-zone/same-zone/standalone, and evaluate alternatives or DR.

### HA Is Not Cross-Region DR

HA primary and standby operate within one region per supported model. To recover from a full region outage, evaluate **cross-region replicas** or **geo-redundant backups/restores** per capabilities and RPO/RTO targets.

## 10. MySQL Flexible Server: HA Standby

**Azure Database for MySQL Flexible Server** likewise offers managed HA in supported configs with a standby and automated failover to cut downtime.

```text
Orders API → MySQL Flexible Server endpoint
                         |
                  Primary read/write
                         |
                  HA standby (same-zone /
                  zone-redundant if supported)
```

Design principles:

1. Pick an HA mode matching host vs. zone fault tolerance needs.
2. Verify tier, storage, region, version, and supported limits.
3. Never treat the standby as an independent `SELECT` endpoint.
4. Test retries and transaction rollbacks during failover.
5. Monitor failover events, query latency, CPU, I/O, and connections.
6. To offload reporting queries, provision a **read replica** per supported features.
7. To survive regional outages, prepare a separate **DR strategy**.

Never carry PostgreSQL configuration parameters over to MySQL just because both are named Flexible Server: replication mechanics, logs, SQL commands, and limits differ.

## 11. What Are Read Replicas and When Are They Used?

A **read replica** is a copy receiving data changes from the primary to serve read queries per product capabilities. Most database service read replicas aim to **offload read traffic** using asynchronous replication.

```text
                         +---------------------+
                         | Primary             |
                         | writes + critical   |
                         | fresh reads         |
                         +----------+----------+
                                    |
                      async replication (lag)
                           /                    \
                          v                      v
               Read replica A             Read replica B
               BI dashboards              Search/report API
```

### When Suitable

- Heavy aggregate reports with relaxed freshness needs.
- Near-real-time dashboards tolerating a few seconds/minutes of delay.
- Read-heavy search/filter APIs fitting read-only constraints.
- Batches/exports needing resource isolation from the primary.
- Growing read load where write throughput is not yet a bottleneck.

### When Unsuitable

- Flows needing immediate post-write reads (read-your-writes) without a consistency mechanism.
- Reads depending on instantaneous state such as balance checks right after a debit.
- Workloads needing distributed writes: read replicas are not multi-master.
- Reporting causing heavy locks/CPU that truly belongs in a **data warehouse/OLAP** system instead of scaling SQL replicas endlessly.
- Treating a replica as the sole backup when logic errors replicate.

## 12. Replication Lag and Stale Reads

Why can a read replica return old data?

```text
T0  Primary: UPDATE Orders SET status='Paid' WHERE id=1042
T1  Transaction COMMITs on primary
T2  Client GET /orders/1042 → reads from replica
T3  Replica finally applies Paid change
```

If `GET` runs at T2 before the replica applies the change, the client still sees `Pending`. This is a **stale read**, not necessarily a connectivity or SQL bug.

### Causes of Rising Lag

- Primary generates WAL/binlog/transaction logs very rapidly.
- Network/regional latency or congestion between primary and replica.
- Replica lacks sufficient CPU, I/O, or memory to replay changes.
- Long-running queries/DDL, locks, or engine-specific constraints.
- Overloaded storage/replication subsystems.
- Replay paused during maintenance or faults.
- Bulk updates or index operations generating massive change volume.

Never enforce one lag threshold for every app. Define a business-driven **lag budget**.

| Query Type | Required Data Freshness | Routing Guidance |
|---|---|---|
| Newly confirmed payment | Immediate post-commit per consistency contract. | Primary. |
| Checking order status right after placing it | Read-your-writes critical. | Primary or consistency-token/wait mechanism per design. |
| Hourly revenue report | Short delay acceptable. | Read replica. |
| Daily trend dashboard | Few minutes delay acceptable when appropriate. | Read replica/analytics store. |
| End-of-period financial reconciliation | Requires consistent snapshot/cutoff, not just "latest." | Primary/snapshot/designed analytics pipeline. |

## 13. SQL Database Read Scale-Out and Application Intent

Certain Azure SQL Database tiers like **Premium/Business Critical** and **Hyperscale** configurations support read scale-out per tier architecture/features.

Applications can route read-only workloads using **connection strings / `ApplicationIntent=ReadOnly`** to the supported endpoint. Key points:

- **`ApplicationIntent=ReadOnly`** is a routing hint in compatible configs, not a security rule replacing database permissions.
- Do not assume this works on every tier or creates a brand-new reader replica.
- Replicas can exhibit replication lag; verify consistency requirements before shifting all `SELECT`s.
- Reporting queries can consume significant resources even on a read replica.
- For geo-secondaries, read endpoints and failover group listeners follow dedicated mechanics; check the read-only listener when using failover groups.
- Read scale-out does not mean data is replicated to another region.

### Conceptual Connection String Example

```text
Server=tcp:<logical-server>.database.windows.net,1433;
Database=ordersdb;
Encrypt=True;
TrustServerCertificate=False;
ApplicationIntent=ReadOnly;
...
```

This is a **snippet explaining the option**, not complete credentials. Never insert real passwords. Connections must still target a tier/endpoint supporting read routing with approved authentication.

### Separating Application Read/Write Clients

Maintain two logical database clients:

```text
OrderCommandRepository ─── primary/write endpoint
OrderQueryRepository   ─── reader endpoint (tolerates lag)
```

Never funnel every `SELECT` into one shared pool expecting it to guess which transactions tolerate stale reads.

## 14. PostgreSQL Flexible Server: Read Replicas

PostgreSQL Flexible Server supports **read replicas** under service terms. Read replicas can reside in the same region or another region in supported configurations/regions; check feature scope, private networking, and promotion ahead of deployment.

Example:

```text
PostgreSQL Primary: pg-orders-prod
      |
      | asynchronous replication
      +------------------------+
      |                        |
      v                        v
pg-orders-read-a       pg-orders-read-b
reporting workload     analytics workload
```

### Differences from HA Standby

| Criterion | HA Standby | Read Replica |
|---|---|---|
| Purpose | Role takeover when primary fails. | Scale reads; optionally support DR per topology. |
| Dedicated read endpoint | Not by default. | Has its own replica endpoint. |
| Accepts app writes | No while acting as standby. | No; read-only while acting as replica. |
| Replication mechanism | Per HA implementation. | Typically asynchronous. |
| Promotion | HA failover via platform/operations. | Explicit **promote replica** flow to standalone primary/server per features. |
| Consequence | HA/primary endpoint managed by service. | Post-promotion requires updating endpoints/topology; never assume automatic role reversal. |

### Items to Verify

- Replica is **read-only** and rejects `INSERT`/`UPDATE`/DDL writes.
- Replica compute/storage sizing and replication lag.
- Compatible roles, extensions, and Postgres server parameters.
- Networking/FQDN/DNS/private access for each replica.
- How apps detect a failed replica and fall back or switch to another.
- Replica limits, tier/region support, and quotas.
- Promotion/cross-region support by version/region.
- Cost of **each replica server** and replication traffic.

**Never treat a read replica as a secondary that auto-promotes alongside HA standby.** If automated DR or tight RTO is needed, evaluate service failover/orchestration and application workflows.

## 15. MySQL Flexible Server: Read Replicas

MySQL Flexible Server offers read replicas within supported features. Replicas receive changes from the primary via MySQL/Azure replication and serve read workloads, typically with **replication lag**.

```text
MySQL Primary: mysql-orders-prod
      |
      +-- Read replica: mysql-orders-read
      |
      +-- (optional remote replica when supported)
```

Notes:

1. Replicas have their own **server endpoint**, separate from the primary write endpoint.
2. Cross-region read replicas/region pairings carry conditions; never assume every region pair is valid.
3. A lagging read replica can return stale values.
4. Heavy queries on a replica can slow down its replication apply speed.
5. Send writes strictly to the primary; enforce read-only connection policies and matching DB permissions.
6. Promotion to a standalone server (where supported) is an **impactful topology change**.
7. A single MySQL replica does not automatically provide full failback or auto-redirect all clients post-promotion.

If an app relies on specific **MySQL transaction consistency**, verify behavior when reading from replicas under your MySQL version's isolation, commit, and replication semantics.

## 16. Read Routing, Read-Your-Writes, and Transaction Boundaries

A simple CQRS-style setup:

```text
Orders API
   |
   +-- POST /orders --------> Primary
   |
   +-- POST /orders/pay ----> Primary
   |
   +-- GET /orders/{id} ----> Read replica?
                                   |
                              Potentially stale
```

Right after a `POST`, clients often expect `GET` to reflect the new state. If `GET` hits a read replica lagging by a few seconds, user experience breaks.

### Control Patterns

- **Primary-only reads** for flows needing immediate post-write consistency.
- **Read-after-write stickiness**: for a short window or after a write token, route queries back to the primary.
- **Consistency tokens/LSN/GTID** per engine/support to verify the replica caught up to a write point, if implemented safely.
- **Accept eventual consistency** for dashboards/reporting while displaying data freshness timestamps.
- **Deliberate cache invalidation**, preventing caches from serving even staler data than replicas.
- **Clear transaction boundaries**: never split operations within one business transaction arbitrarily across primary and replica.

### Anti-Pattern Example

1. Write `Order.status = Paid` on primary.
2. Immediately read replica to verify `Paid`.
3. Replica hasn't applied yet, returns `Pending`.
4. App concludes payment failed and charges again.

This is not an HA failure—it is a **consistency design flaw**. Verify transactions against a strongly consistent source and enforce idempotency to prevent double charges.

## 17. Connection Pooling Across Multiple Endpoints

When an app uses a primary and read replicas, manage separate connection pools or route through a supported proxy/router.

| Pool | Endpoint | Role | Notes |
|---|---|---|---|
| Write pool | Primary/write listener | Writes and strongly consistent reads. | Retry transient faults, timeouts; never cache DNS/IP forever. |
| Read pool A | Local read replica A | Reports and lag-tolerant reads. | Throttle load and monitor replica lag. |
| Read pool B | Local read replica B | Distribute reads when supported. | Health checks and proper routing. |
| DR pool | Geo-secondary/promoted remote endpoint | Only upon approved region switch. | Verify permissions/network and write readiness. |

### Common Mistakes

- Connection pools retaining stale connections after failover.
- Excessively long DNS caching or hard-coded IPs.
- Infinite retries on all transactions when the DB is genuinely down.
- Reporting workloads opening too many connections and exhausting limits.
- App sending `INSERT` to a read-only replica due to swapped connection strings.
- Switching endpoints with incompatible secrets, firewalls, or TLS certificate verification.
- In multi-tenant apps, one tenant's heavy report starving the read replica for others.

**Verify how clients/drivers handle reconnects and DNS re-resolution.** A DNS alias alone will not heal an app if its connection pool never evicts dead connections.

## 18. Geo-Replication: Defending Against Regional Disasters

**Geo-replication** replicates data to a database in another region for DR or geographically closer reads. Many managed database services use **asynchronous cross-region replication** to avoid high cross-continent commit latency.

```text
                      Region A (primary)
                 +------------------------+
                 | API A                  |
                 | Primary DB (write)     |
                 +-----------+------------+
                             |
                 async geo-replication
                             |
                             v
                      Region B (secondary)
                 +------------------------+
                 | API B (standby/DR)     |
                 | Geo-secondary (read)   |
                 +------------------------+
```

Notes:

- The geo-secondary may sit **behind the primary** by seconds or longer during disruptions.
- Actual RPO depends on lag right before failover, not merely published targets.
- Region B must also have compute, secrets, networking, DNS, storage, dependencies, and permissions ready for the app.
- Distinguish **planned switchover/failover** (allows pre-sync/checks) from **forced/unplanned failover** (data-loss risk when primary is gone).
- Failback after Region A recovers may require **re-establishing replication and reconciliation**.
- Data residency/compliance may forbid replicating into arbitrary regions.

Geo-replication puts data in another region, **yet does not automatically shift client HTTP traffic** to API B. Routing outside the database must be coordinated too.

## 19. Azure SQL Database Active Geo-Replication

**Active geo-replication** in Azure SQL Database creates one or more **readable geo-secondary databases** per product limits and conditions, typically via asynchronous replication.

```text
Azure SQL Database (Region A)
  logical server: sql-orders-a
  database: ordersdb (read/write)
             |
             | asynchronous geo-replication
             v
Azure SQL Database (Region B)
  logical server: sql-orders-b
  database: ordersdb (readable secondary)
```

### When to Use

- Need a secondary database in another region for disaster recovery.
- Read workloads need to run closer to users in Region B.
- Want manual/runbook-driven failover across regions when the primary is down.
- Want separate logical servers/networking/security in the DR region under the SQL Database model.

### Key Points to Remember

1. **Geo-secondaries are read-only** while acting as secondaries.
2. Async replication cannot guarantee the latest commits reached Region B before an outage.
3. Geo-secondaries incur compute/storage costs plus potential data transfer fees.
4. Server-level settings, auth, firewalls/Entra networking, logins/roles, and external objects must be evaluated separately—**do not assume all Azure resource configs clone automatically**.
5. Upon failover, app connections and routing must be verified or updated per design.
6. Never treat a geo-secondary as an immutable backup against erroneous deletes.

### Active Geo-Replication vs. Local Read Scale-Out

- **Read scale-out** uses managed replicas within the same region/tier.
- **Active geo-replication** targets a **cross-region secondary** and regional recovery.
- Geo-secondaries can serve read workloads, subject to cross-region latency, lag, and takeover impact.

## 20. Azure SQL Failover Groups and Listeners

For Azure SQL Database and supported **Azure SQL Managed Instance** setups, **failover groups** manage database/instance groups for geo-failover plans alongside **listener endpoints**.

Conceptual model:

```text
                 Application
                 /         \
        Write connection   Read connection
               |               |
               v               v
        RW listener       RO listener
               |               |
               v               v
       Primary region     Geo-secondary region
       SQL database(s)    SQL database(s)
                \             /
                  Failover group
```

Depending on service and configuration, a failover group may expose:

- **Read-write listener**: endpoint directing clients to whichever region currently holds primary.
- **Read-only listener**: endpoint for read-only routing where supported.
- Automatic or manual failover policies per product capabilities.
- Sets of databases managed together as a failover group per supported semantics.

### Benefits and Limitations

- Apps avoid hard-coding logical server A vs. B in supported scenarios.
- A stable listener FQDN minimizes connection-string edits during region switches.
- DNS caching/connection pools can still keep clients hitting the old endpoint; **reconnect/retry logic remains mandatory**.
- Failover groups **do not make cross-region replication synchronous**; async RPO risk still applies.
- Review failover policies, grace periods, and secondary health; automatic failover never guarantees zero data loss or instant recovery.
- Do not assume the listener auto-routes **every `SELECT`** to a read replica; configure read-only intent and exact endpoints properly.

### Database vs. Managed Instance

Azure SQL Database active geo-replication and SQL Managed Instance failover groups **do not share the same resource model**. For Managed Instance, inspect product-specific failover group/link/network/instance-level requirements; never run SQL Database commands blindly on MI.

## 21. PostgreSQL/MySQL Cross-Region Read Replicas: Conditional DR

With **PostgreSQL Flexible Server** and **MySQL Flexible Server**, read replicas can maintain a cross-region copy **if supported by your engine version, tier, region, and features**.

```text
Region A                         Region B
+--------------------+           +--------------------------+
| PostgreSQL/MySQL   |  async    | Remote read replica      |
| primary (read/write)|--------->| (read-only before promote)|
+--------------------+           +--------------------------+
                                              |
                                              | promotion when DR authorized
                                              v
                                   Standalone primary / new endpoint
```

### Promotion Is Not Automatic HA Failover

A **promoted** read replica leaves its old replica topology and becomes a standalone read/write server. When promoting:

1. Confirm the old primary can no longer accept writes to prevent **split-brain**.
2. Check how far the replica caught up, replication lag, and potential data loss.
3. Approve promotion based on incident severity.
4. Update routes/endpoints/connection strings or virtual endpoints where supported.
5. Verify networking/roles/TLS/secrets in Region B.
6. Run smoke tests and reconcile transaction counts.
7. Plan **re-sync/failback**; never assume replication automatically reverses direction.

### MySQL and PostgreSQL Differ

Limits, cross-region mechanics, DDL replication behavior, engine versions, virtual endpoints, and promotion steps differ. Follow docs/CLI for the **exact engine and deployment mode**. Avoid running `pg_ctl promote` or raw MySQL replication statements directly against a managed Flexible Server when the service mandates its own management API.

## 22. Backups, Geo-Redundant Backups, and PITR Are Not Replicas

Backups restore data to a preserved historical state, whereas replication maintains a live-tracking copy for HA, read scaling, or DR.

| Mechanism | Primary Protection | Advantages | Limitations |
|---|---|---|---|
| HA standby | Node/zone faults within design scope. | Relatively fast failover per product. | Not an independent backup; normally does not serve reads. |
| Local read replica | Read scaling, report isolation. | Offloads reads, scales consumers. | Has lag; cannot roll back old data errors. |
| Geo-secondary/read replica | Regional outage, read locality if supported. | Data already present in DR region. | Async lag, promotion/failover risks. |
| Automated backups + PITR | Accidental delete or logic bug within retention. | Restores to pre-error timestamp per service. | Takes time and may create a new server/database. |
| Geo-redundant backups | Restore from backups in another region per supported options. | Valuable during prolonged primary region loss. | Not a hot secondary; RTO differs from replica failover. |
| Exports/archives/immutable backups | Retain or recover discrete data milestones. | Supports compliance/forensics. | Requires lifecycle, security, and restore testing. |

**PITR (point-in-time restore)** requires sufficient backup/log retention and database support—it does not magically produce an in-place "rolled-back" primary without impacting workloads. Many services restore to a **new database/server**, requiring controlled application cutover.

### Accidental Deletion Example

09:00: database holds 10,000 orders.  
09:05: an operator executes an erroneous `DELETE`.  
09:05–09:06: the error replicates to HA standby and geo-secondary.  
09:10: the application detects missing orders.

**Never** blindly promote the geo-secondary: it likely already received the `DELETE`. The right path is identifying the recovery point, using PITR/backups for controlled restoration, reconciling valid writes between 09:00 and the error, and repairing data.

## 23. Architecture Selection Table by Objective

| Requirement | Azure SQL Database | PostgreSQL Flexible Server | MySQL Flexible Server |
|---|---|---|---|
| Intra-region instance faults | Built-in HA per service tier. | HA primary/standby where config supports. | HA primary/standby where config supports. |
| Availability Zone faults | Zone-redundant option per tier/region. | Zone-redundant HA where supported. | Zone-redundant HA where supported. |
| Offload read queries | Read scale-out/replicas per tier, `ApplicationIntent`. | Create read replicas. | Create read replicas. |
| Readable copy in another region | Active geo-replication/secondary. | Cross-region read replica where supported. | Cross-region read replica where supported. |
| Cross-region failover | Active geo-replication/failover group per features. | Promotion/DR orchestration per features. | Promotion/DR orchestration per features. |
| Read-write listener across regions | Failover group listener where supported. | Endpoints/virtual endpoints or routing per features. | Endpoints/virtual endpoints or routing per features. |
| Recover accidental deletes | Automated backups/PITR. | Backups/PITR. | Backups/PITR. |

**Never treat "Yes" as a blanket guarantee across every SKU and region.** In your final design, specify exact deployment mode, pricing tier, zone choice, engine version, region pair, and active features.

## 24. DNS, Endpoints, and Post-Failover Routing

Successful DR depends on clients **leaving the old endpoint** and connecting to the new primary.

```text
Before failover
  app write → db-write.example.internal → Region A primary
  app read  → db-read.example.internal  → read replica

After region DR failover
  app write → db-write.example.internal → Region B promoted primary
  app read  → db-read.example.internal  → suitable reader
```

The diagram uses **logical DNS aliases** conceptually; not every Azure database service permits arbitrary CNAMEs in place of default FQDNs while preserving TLS hostname validation. Check:

- Do database drivers/connection strings support aliases/redirects/listeners per product?
- Does TLS certificate hostname validation still pass?
- What are DNS TTLs and caches across client/JVM/.NET/OS/connection pools?
- Are Private DNS zone links and private endpoints ready in the DR region?
- Are firewalls/NSGs/UDRs/Azure Firewall routes ready?
- Are Microsoft Entra auth, database users, and secrets/credentials ready?
- How are TCP timeouts, retry budgets, and pool refreshes configured?
- Can clients resolve and write to the new primary immediately after role change?

**Never hard-code static IPs** for managed database endpoints. Nor assume a low DNS TTL guarantees instant switching: clients holding open connections may not re-query DNS until reconnecting.

## 25. Consistency and In-Flight Transactions During Failover

Failover hits while transactions are actively running:

```text
Client                 Primary              Secondary
  | BEGIN TRANSACTION    |                      |
  | UPDATE Orders        |                      |
  | COMMIT ? ------------|------ replication --->|
  |      connection lost |                      |
  | retry to new primary |                      |
```

When the client loses connection without receiving a `COMMIT` ack, either the transaction **committed** or **rolled back**. Unconditional retries can double-charge or duplicate orders if statements aren't idempotent.

### Safe Strategy

1. Assign every business operation a stable `requestId`/idempotency key.
2. Enforce a **unique constraint** in the database for operation IDs.
3. On network/failover errors, query business state before re-creating.
4. Retry transient errors with bounded backoff and timeouts.
5. Keep transactions short to minimize lock holds.
6. Use outbox/inbox patterns when message brokers participate.
7. Reconcile transactions inside the **RPO risk window** after failover.
8. Flag unverified records/orders rather than guessing success or failure.

**HA does not replace transactional correctness.** Even a clean infrastructure failover causes business errors if application retries are flawed.

## 26. Planned Failover, Forced Failover, and Failback

### Planned Failover

Executed while the primary remains controllable and the team intentionally switches roles—e.g., maintenance or DR drills. Depending on the product, data can be pre-synced/checked to minimize data-loss risk.

Workflow:

1. Define scope, approval, and impact window.
2. Verify secondary health/lag, networking, and capacity.
3. Temporarily throttle/pause app writes if required by runbook.
4. Wait for replication to catch up within supported workflow bounds.
5. Trigger the **service-specific** failover/switchover operation.
6. Verify or update listeners/endpoints.
7. Smoke-test reads/writes and final data state.
8. Reopen traffic; monitor error rates and latency.

### Forced/Unplanned Failover

When the primary region disappears, you cannot tell whether the secondary received every committed write. You must accept **potential data loss** and split-brain risk if the old primary revives.

- Assign an accountable decision owner.
- Record observed lag and the uncertainty window.
- Prevent both primaries from accepting writes simultaneously.
- Promote/fail over strictly using service-supported mechanisms.
- Reroute the entire stack and verify dependencies.
- Reconcile transactions and recover missing records from outboxes, logs, or upstream sources if still intact.
- Never auto-failback the moment Region A comes back online.

### Failback

Failback is a **brand-new topology change**, not simply flipping DNS back:

1. Verify the new primary is operating stably.
2. Determine replication direction, data watermark, and how to rebuild a secondary in the old region.
3. Confirm zero lingering writes hit the old primary.
4. Rebuild/sync per product runbook, avoiding merging two diverged data branches.
5. Run a planned switchover if returning to the original region is required.
6. Reconcile data, keep a rollback plan, and update architecture docs.

## 27. Azure Portal: Inspecting HA and Replicas

### Azure SQL Database

1. Open Portal and confirm tenant/subscription/resource group.
2. Select **SQL database**; note database name and logical server.
3. Inspect **Compute + storage / Service tier** and **zone redundancy** if present.
4. Open **Replicas/Geo-replication** (or equivalent blade).
5. If using a failover group, inspect primary/secondary servers, roles, and listeners.
6. Check **Metrics**, Resource health, and alert rules.
7. Record read-write and read-only connection endpoints.

### PostgreSQL Flexible Server

1. Open the primary server; check **High availability** mode and status.
2. Open **Read replicas** to verify replica count, source, region, and state.
3. Record each server's endpoint, engine version, compute SKU, and networking.
4. Inspect service metrics for replication lag, CPU, storage, and connections.
5. Confirm backup retention and geo-redundancy settings if present.
6. Click **Promote/Failover** only within an approved workflow.

### MySQL Flexible Server

1. Open the server; check **High availability** and region/zone.
2. Check **Read replicas** and endpoints.
3. Inspect replication lag, CPU, I/O, memory, and connection metrics.
4. Review replica networking/private access.
5. Check backup retention, restore options, and alerts.
6. Never delete a lagging replica or promote ad-hoc just to silence alerts.

**The Portal is a management UI**, not sole proof of consistency. Failover rehearsals require real end-to-end app tests and data reconciliation.

## 28. Azure CLI: Safe Topology Inspection

The commands below are primarily **read-only**—they do not create secondaries, promote, or fail over. Replace placeholders with approved lab/Production resources. Check CLI/extension versions if flags or fields differ.

### Verify Subscription/Tenant

```bash
az account show \
  --query "{Subscription:id,Tenant:tenantId,Name:name}" \
  --output table
```

### Azure SQL Database

```bash
az sql db show \
  --resource-group "<RESOURCE_GROUP>" \
  --server "<LOGICAL_SQL_SERVER>" \
  --name "<DATABASE_NAME>" \
  --query "{Name:name,Status:status,Edition:edition,ZoneRedundant:zoneRedundant,Location:location}" \
  --output json

az sql db replica list \
  --resource-group "<RESOURCE_GROUP>" \
  --server "<LOGICAL_SQL_SERVER>" \
  --name "<DATABASE_NAME>" \
  --output table
```

### Azure SQL Failover Groups

```bash
az sql failover-group list \
  --resource-group "<RESOURCE_GROUP>" \
  --server "<LOGICAL_SQL_SERVER>" \
  --output table
```

When reading output, verify primary/partner servers and replication roles/states. Never execute failover just to verify a group name.

### PostgreSQL Flexible Server

```bash
az postgres flexible-server show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<POSTGRES_SERVER>" \
  --output json

az postgres flexible-server replica list \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<POSTGRES_PRIMARY_SERVER>" \
  --output table
```

### MySQL Flexible Server

```bash
az mysql flexible-server show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<MYSQL_SERVER>" \
  --output json

az mysql flexible-server replica list \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<MYSQL_PRIMARY_SERVER>" \
  --output table
```

Supported properties vary across API versions. `show` displays topology/HA config, yet **does not replace measuring runtime lag**. If the CLI reports an unsupported option, check `az ... --help` and installed extensions instead of guessing parameters.

### Why Omit One-Line Failover Commands?

Promoting, failing over, deleting replicas, or toggling HA modes carry **data-loss or outage risks**. Exact syntax, prerequisites, and rollbacks vary by engine and SKU. This lesson therefore focuses on read-only commands; write actions belong in verified runbooks matching product docs.

## 29. SQL Examples: Reading the Right Source After Writes

### Write Transaction to Primary

```sql
-- Run in a test environment; illustrates business idempotency.
BEGIN TRANSACTION;

UPDATE Orders
SET Status = 'Paid'
WHERE OrderId = 1042
  AND Status = 'Pending';

-- Must check affected row count and real business rules.
COMMIT TRANSACTION;
```

This illustrates SQL Server T-SQL syntax, not directly portable to every PostgreSQL/MySQL dialect. In production, preventing double charges requires **idempotency keys**, unique constraints, and payment-service coordination; `WHERE Status='Pending'` alone is insufficient.

### Reading from Primary or Replica

```sql
SELECT OrderId, Status, UpdatedAt
FROM Orders
WHERE OrderId = 1042;
```

The exact same `SELECT` may return `Paid` on the primary while returning `Pending` on a lagging async replica. **A SQL query does not know whether it hit a primary or a replica.** Verify connection properties and routing inside the app.

### Measuring Data Freshness

Applications can store `UpdatedAtUtc` or a version/commit marker to spot overly stale reporting data:

```text
Report generated at 10:05 UTC
Max source UpdatedAtUtc observed = 10:01 UTC
Estimated data freshness lag >= 4 minutes (heuristic)
```

This is only a **heuristic**: if no new records arrived, a timestamp gap does not equal replication lag. Accurate lag measurement requires engine/service metrics or replication status views.

## 30. Metrics You Must Monitor

Even a database with HA and replicas can miss SLOs without monitoring.

| Signal | Purpose | Action |
|---|---|---|
| **Availability/connection errors** | Detect failovers or drops. | Correlate app errors, DB health, and networking. |
| **Replication lag** | Know how far read replicas/geo-secondaries lag. | Evaluate read freshness and RPO risk. |
| **CPU** | Detect compute bottlenecks. | Compare primary vs. replicas, queries, and tiers. |
| **Memory/I/O/storage latency** | Spot disk, buffer, or replay bottlenecks. | Inspect query plans, workloads, and resources. |
| **Storage usage/growth** | Avoid hitting quotas/full disks. | Capacity planning and alerts. |
| **Connections** | Catch pool storms or connection exhaustion. | Tune pools/retries and scale capacity. |
| **Deadlocks/lock waits** | Spot transaction contention. | Optimize SQL and shorten transactions. |
| **Query latency/p95** | User-visible impact. | Check workloads, indexes, and read routing. |
| **Failover events** | Pinpoint timing/type of role switch. | Correlate with application retries. |
| **Backup status/retention** | Ensure PITR remains valid. | Check backup policies and restore drills. |
| **Geo DR readiness** | Are secondaries healthy with capacity/permissions? | Test DNS, dependencies, and replication. |

### Lag Only Makes Sense When You Know Its Measurement Source

- Azure SQL geo-replication exposes service-specific lag and replication states/metrics.
- PostgreSQL exposes WAL replay/receiver concepts and server metrics.
- MySQL exposes engine/service replication metrics/states calculated differently from PostgreSQL.
- **Never use the same SQL query or metric name** across all three engines.
- Some metrics update with reporting delay; verify collection timestamps and clock sources.

With a 60-second RPO target, a lag chart sampled every 5 minutes cannot prove RPO compliance at the moment of an incident from a dashboard screenshot alone.

## 31. Alerts and SLOs from the Application's Perspective

Minimum alerts:

1. Database unavailable/connection failures above threshold.
2. Replica lag exceeds **read freshness budget**.
3. Geo-replica lag exceeds **DR RPO risk threshold**.
4. Sustained high primary CPU/I/O or storage usage.
5. High replica CPU/I/O causing replay to fall behind.
6. Failover/switchover occurring outside a maintenance window.
7. Elevated post-failover errors or unrecovered connection pools.
8. Backup/restore check failure or unexpected retention changes.
9. Writes hitting a read-only replica or read endpoint losing its role.
10. Unexpected budget/cost spikes from new replicas.

### Combining Metrics with Synthetic Checks

An important synthetic check:

- From the **actual app/VNet**, open a read-write connection to the database.
- Run a harmless read query without logging secrets.
- Verify the endpoint's role using an engine-supported method.
- Measure latency and response.
- Verify the reader endpoint returns results within defined stale tolerance.
- During failover drills, validate both **write paths** and **read paths**.

Never run synthetic test writes directly in Production without dedicated lab tables/accounts and approval; rely on read-only health checks plus business tracing.

## 32. Security, Networking, and Identity for Primary and Replicas

Adding replicas adds endpoints and resources that must be secured.

### Checklist

- **Private access:** VNet integration, private endpoints/delegated subnets per service.
- **DNS:** accurate resolution for every server/replica, private DNS zones, and links.
- **Firewall/NSG/UDR:** permit only required workloads and ports.
- **TLS:** enforce encryption, hostname validation, and trusted certificates.
- **Identity:** Microsoft Entra auth/managed identities where supported by DB and drivers, or Key Vault credential management.
- **DB permissions:** reporting apps hold only required `SELECT`—never DDL/admin rights just because they hit a replica.
- **Secret rotation:** check whether primary, replica, and failover endpoints share or separate credentials.
- **Auditing:** control-plane changes, login failures, DDL, and required activity.
- **Data residency:** is the remote region legally permitted to store customer/PII data?
- **Replication encryption:** leverage service-supported encryption in transit and at rest.
- **Key management:** if using CMK/TDE/Key Vault, verify keys and permissions in the DR region.

### Commonly Overlooked Risk

A geo-secondary can provision cleanly yet remain unreachable from Region B apps because a **private DNS zone isn't linked**, a firewall rule is missing, or the identity lacks rights. **Data-plane DR readiness must be tested from where the apps actually run**, not just from the Azure Portal.

Never open the firewall to the Internet to "test if the replica works" in Production. Fix the scoped network issue and revoke any temporary exceptions.

## 33. Calculating the Cost of HA, Replicas, and Geo-DR

Costs arise from:

| Component | Cost Impact |
|---|---|
| HA/zone redundancy | Standby compute or tier-specific HA charges per product. |
| Read replicas | Compute, storage, and I/O for each replica. |
| Geo-secondary | Database resource in Region B plus replication/network transfer where applicable. |
| Backups/PITR/long-term retention | Backup volume, retention, redundancy, exports. |
| DNS/private networking | Private Endpoints, VNet peering, firewalls, NAT, egress. |
| Monitoring | Azure Monitor/Log Analytics/alerting. |
| DR-ready application | App instances, load balancers, secrets, caches, queues, Storage in Region B. |
| Exercises | Failover drill duration, test data, staffing, and recovery work. |

### Comparing Three Reporting Options

1. **No read replica**: saves replica compute, yet reporting load slows the primary; requires SQL/index tuning.
2. **One local read replica**: increases database cost, yet isolates reporting and improves write transaction performance.
3. **One geo-secondary doubling as reporter**: supports DR and remote reads, yet latency/lag/networking/roles may not fit every report. **Never turn a DR secondary into a bottleneck** that jeopardizes timely failover.

### Simple Cost Mental Model

```text
Total system cost =
  Database primary
+ HA surcharge/standby if applicable
+ Σ(read replicas)
+ Geo-DR resources
+ Backups/PITR
+ Networking/private DNS
+ Monitoring
+ Application DR capacity
+ Operations and drills
```

Actual prices vary by region, SKU, vCore/compute size, storage, uptime, and reservations/discounts. Use the Azure Pricing Calculator and real load metrics rather than hypothetical assumptions.

## 34. Runbook: Regional Failover During Primary Region Outage

**Context:** SQL primary in Region A suffers a prolonged outage. Region B hosts a geo-secondary and standby API. Goal: restore ordering without creating two simultaneous primaries.

### Phase 1 — Verify the Incident

1. Record incident ID, UTC start time, and impacted customer scope.
2. Check Azure Service Health, database health, app error rates, and networking/DNS.
3. Distinguish a database outage from an isolated connection/identity error.
4. Inspect secondary health, lag, and replicated data state.
5. Quantify RPO risk against approved targets.

### Phase 2 — DR Decision

1. Incident commander/DB owner confirms activation criteria.
2. Record **potential loss of un-replicated committed writes** if forcing failover.
3. Ensure Region A can no longer accept writes once Region B becomes primary.
4. Pause/throttle producer workloads to prevent split data branches.
5. Verify API B, Service Bus, secrets, Storage, caches, and external dependencies.
6. Select the exact failover/promote operation for the database service.

### Phase 3 — Activation

1. Execute failover/failover group switch or replica promotion per product runbook.
2. Confirm the database role in Region B.
3. Verify listener/FQDN/DNS routing and connection pool reconnects.
4. Open write traffic in a controlled rollout.
5. Run transactional and read-after-write smoke tests from the live app runtime.
6. Monitor latency, error rates, locks, and connection counts.

### Phase 4 — Reconciliation

1. Identify the last confirmed replicated data watermark.
2. Reconcile request/transaction IDs inside the RPO risk window.
3. Recover eligible transactions from outboxes, message logs, or upstream sources.
4. Never auto-retry all payments without checking idempotency.
5. Flag unconfirmed cases for manual resolution.

### Phase 5 — Stabilization and Failback

1. Monitor Region B for at least the defined operational stabilization window.
2. Re-establish replication/secondary topology.
3. Execute an approved failback plan; never blindly point traffic back to Region A.
4. Update DNS, certificates, automation, and documentation.
5. Hold a postmortem and close identified gaps.

## 35. Runbook: High Read Replica Lag

**Symptom:** reporting dashboards run slowly and occasionally show order data 3–5 minutes behind primary commits.

### Diagnosis

1. Measure lag using the **appropriate metric/engine signal** and log timestamps.
2. Check primary write volume, bulk updates, DDL, and transaction log/WAL/binlog growth.
3. Check replica CPU, memory, I/O latency, storage usage, and long-running queries.
4. Check network/region health and replication status.
5. Identify which reporting queries consume resources or hold locks.
6. Determine which SLO is affected: dashboards or checkout?
7. Check whether lag started after a tier change, migration, index rebuild, or deployment.

### Remediation

- For flows needing fresh data immediately, temporarily **route to primary** within capacity limits.
- Optimize reporting queries and add needed indexes on primary/replicas per engine capabilities (mindful of replicated schemas).
- Scale up replica compute/I/O if workload justifies and approval is granted.
- Throttle reporting concurrency or reschedule heavy reports off-peak.
- Inspect replication links and platform health incidents.
- If severe replica lag persists, consider rebuilding per runbook; never delete a replica before ensuring serving and DR coverage remain.
- Re-measure lag, query latency, and primary load after changes.

**Mistake to avoid:** loosening lag alert thresholds or raising cache TTLs to hide stale data when business SLOs are still violated.

## 36. Runbook: Failover Breaks Application Connectivity

**Symptom:** the database switched roles cleanly, yet the app continues throwing connection timeouts or login failures.

### Layered Checks

| Layer | What to Verify |
|---|---|
| Endpoint | Does the connection string point to the new primary, listener, or supported alias? |
| DNS | Does the FQDN resolve to the right IP/route from the app's VNet? |
| TCP/network | NSGs, UDRs, firewalls, private endpoints, ports? |
| TLS | Certificate hostname, CA, encryption settings? |
| Identity | Entra principals, DB user mappings, secrets/connection passwords? |
| Driver | Stale connection pool, DNS cache, retry/transient fault handling? |
| Database | Is the server read-write, or is a replica still in recovery? |
| Transactions | Which transactions rolled back, and which requests need reconciliation? |
| Capacity | Does the new primary have enough CPU/I/O/connection headroom for real load? |

### Response

1. Never enable infinite retries.
2. Verify FQDN and host identity from the real client runtime.
3. Evict/refresh connection pools via application mechanisms.
4. Fix permissions and TLS properly—never disable certificate validation.
5. Verify the new connection reads and writes safely on authorized lab data.
6. Monitor error rates, latency, and business workflows.
7. If rolling back, assess data divergence first; never flip DNS blindly.

## 37. Scenario A: Reporting Slows Down Payment Transactions

**Context:** a PostgreSQL Flexible Server runs the Orders API alongside 20 end-of-day BI reports. Primary CPU regularly hits 95%, causing payment requests to time out.

**Viable solution:**

1. Optimize reporting queries/indexes and identify which queries genuinely need the Primary.
2. Provision a same-region read replica (if SKU/region support) sized adequately for BI.
3. Configure a separate read pool targeting the replica endpoint, routing only reports that **tolerate eventual consistency**.
4. Set a lag SLO (e.g., reports tolerate up to a few minutes' delay) and monitor the metric.
5. Keep payment states and immediate reconciliation on the primary.
6. Test that heavy reports do not push replica lag beyond thresholds.
7. Weigh replica cost against moving heavy BI workloads into a dedicated analytics store.

**Conclusion:** a read replica **distributes read load**; it does not fix all inefficient queries or provide a transactionally consistent global snapshot.

## 38. Scenario B: Primary Region Lost, Remote Replica Lags by 90 Seconds

**Context:** MySQL Flexible Server has a cross-region read replica in a supported setup. The primary region loses connectivity; the last recorded replication lag metric was ~90 seconds.

**Tough trade-off:**

- Promoting the replica immediately restores the app faster, yet risks missing writes from the 90-second lag window.
- Waiting for Region A may preserve more data, yet stretches RTO.
- With a 30-second RPO target, promoting at 90 seconds of lag **risks breaching RPO**.
- For payment data, reconcile transaction IDs from upstream systems instead of assuming every Region A commit exists in Region B.

**Runbook:** confirm incident and lag, obtain decision approval, prevent split-brain, promote per product workflow, update app routing, verify write readiness, and run reconciliation. When Region A recovers, never allow both servers to accept writes together.

## 39. Scenario C: Table Deleted Erroneously While Geo-Replication Stays Healthy

**Context:** Azure SQL Database has a healthy geo-secondary. A bad migration executes `DELETE FROM OrderItems`, wiping records. Replication monitoring reports the secondary is caught up to the primary.

**Analysis:**

- "Healthy" replication means **the erroneous `DELETE` was replicated too**.
- Failing over to the secondary will not recover pre-error data.
- If backups/PITR retain a clean recovery point, restore a copy to just before the delete.
- Reconcile valid writes occurring after that recovery point to avoid losing transactions.
- Proper flow: stop/revoke offending write access, restore into a new database in a controlled environment, verify, and execute targeted data repair or cutover.

**Lesson:** HA/geo-replication provide **system availability**, whereas PITR/backups protect against **logical data errors**.

## 40. Hands-On Exercise: Designing HA, Read Scale, and DR for Orders

**Context:** an Orders system handles 20,000 transactions/day, runs heavy BI dashboards, and must recover from zone/region outages. The organization can choose Azure SQL Database or PostgreSQL Flexible Server.

### Requirements

| Requirement | Illustrative Value |
|---|---|
| Write workload | Transactional OLTP; payments require idempotency. |
| Read workload | Dashboards/reporting tolerate up to a few minutes of delay. |
| Zone failure | App must have an availability plan. |
| Region failure | DR region with business-approved RPO/RTO. |
| Logical deletion | Backups/PITR required. |
| Networking | Private access, TLS, identity-based auth where supported. |
| Monitoring | Lag, availability, failovers, CPU/I/O, connections, backups. |
| Rehearsals | Never alter Production outside approved windows. |

### Tasks

1. Diagram primary, HA standby, local read replica, and geo-secondary/remote replica.
2. Distinguish which components are failover targets vs. read-only query targets.
3. Choose same-zone vs. zone-redundant HA and explain the protected fault scope.
4. Specify which workloads read the primary vs. replicas.
5. Define RPO, RTO, and read freshness SLOs (distinct metrics).
6. Explain synchronous vs. asynchronous replication and when data-loss risk occurs.
7. For SQL Database, compare read scale-out with active geo-replication/failover groups.
8. For PostgreSQL/MySQL, explain how HA standby differs from a read replica and what promotion means.
9. Design primary/read connection strings/endpoints and post-failover reconnect logic.
10. Define 3 alerts: replica lag, primary unavailable, failed failover/connection errors.
11. Add a read replica to the diagram and estimate added resources/cost.
12. Design a way to prevent stale reads of `Order.status` immediately after payment.
13. Simulate Primary unavailable with a lagging remote replica; decide based on RPO/RTO.
14. Simulate an accidental `DELETE`; explain why PITR is mandatory.
15. Design failback and split-brain prevention.
16. Write a checklist verifying DNS, permissions, TLS, API services, and secrets in the DR region.
17. Design a DR drill that does not impact real data.
18. Draft a brief status report for the incident commander covering observed lag, data-loss risk, RTO, and recommended actions.

### Reference Solution Diagram

```text
                       Global routing / API clients
                                 |
                   +-------------+-------------+
                   |                           |
              Region A                    Region B
              API active                  API DR ready
                   |                           |
              Write pool                 DR write pool
                   |                           |
                   v                           v
               Primary DB ─── async ───> Geo-secondary
                   |
             +-----+------+
             |            |
           HA standby   Local read replica
           (failover)   (BI reports)
             |
        Backups / PITR
         in managed storage
```

**Solution notes:**

- **Primary:** OLTP and reads needing immediate post-write consistency.
- **HA standby:** never used as a BI reader; mitigates node/zone failures per HA mode.
- **Local read replica:** serves reports/dashboards with a lag budget and read-only credentials.
- **Geo-secondary:** serves DR/cross-region reads per product; requires reconciliation on forced promotion/failover.
- **Backups/PITR:** protects against accidental `DELETE`/corruption within retention.
- **Measurements:** lag, query latency, HTTP 5xx, connection errors, failover events, restore readiness.
- **Security:** private DNS/networking, TLS, identity, and Key Vault/credentials prepared in Region B.
- **Process:** scheduled planned drills; never delete the primary or force Production failovers purely for testing.
- **Cost:** database replicas, DR API resources, backups, networking, and monitoring.

### Acceptance Criteria

A design meets requirements when:

- Every resource has a clear role and documented fault boundary.
- RPO/RTO have measurement plans and fallbacks if missed.
- Read routing never breaks read-your-writes business flows.
- Read replicas are never treated as the sole final backup.
- Region switching and failback prevent split-brain.
- Logs/metrics verify DR readiness and recovery.
- Costs align with SLAs/SLOs and data requirements.

## 41. Self-Check Knowledge Quiz

**Q1.** How does HA differ primarily from a read replica?

**Answer:** HA protects availability when the primary fails; read replicas offload read traffic and may support DR depending on topology. An HA standby is not a default read endpoint.

**Q2.** Does geo-replication replace backups/PITR?

**Answer:** No. Accidental deletes/bad writes propagate via replication; backups/PITR are needed to restore data prior to the error.

**Q3.** How do RPO and RTO differ?

**Answer:** RPO is the maximum acceptable data loss upon recovery; RTO is the maximum acceptable time to restore service.

**Q4.** Can an async replica lag behind the primary even when primary commits succeed?

**Answer:** Yes. The primary acknowledges before the replica receives/applies transactions, creating replication lag.

**Q5.** Can an application run `UPDATE` directly against a PostgreSQL read replica?

**Answer:** No while it serves as a read-only replica; writes must hit the primary. After supported promotion, it becomes writable, though topology has changed.

**Q6.** Are PostgreSQL/MySQL HA standbys used as default BI read replicas?

**Answer:** No. An HA standby is strictly for failover; offloading BI reads requires a separate read replica.

**Q7.** Does zone-redundant HA protect against losing an entire region?

**Answer:** No. Cross-region DR and matching app/dependency readiness are required.

**Q8.** Do Azure SQL read scale-out and active geo-replication serve the same purpose?

**Answer:** No. Read scale-out offloads reads within the tier; active geo-replication replicates to a cross-region secondary for DR and remote reads.

**Q9.** Does a SQL failover group read-write listener guarantee 100% of clients never drop connections on failover?

**Answer:** No. Existing connections reset, and DNS caches/pools require reconnects and retries; the listener stabilizes the logical endpoint name.

**Q10.** Why should a `GET` for order status right after `POST` favor the primary?

**Answer:** Read replicas have replication lag and may return stale values; read-your-writes flows need a consistent source/strategy.

**Q11.** Does promoting a remote read replica automatically reverse replication when the old region recovers?

**Answer:** Never assume so. Promotion turns a replica into a standalone primary; failback requires rebuilding/syncing topology per service.

**Q12.** Can you fail over to a geo-secondary lagging by 90 seconds and guarantee zero lost commits?

**Answer:** No. Under asynchronous replication, un-replicated committed writes risk loss.

**Q13.** Why must split-brain be prevented in geo-DR?

**Answer:** If both old and new primaries accept writes, data diverges into two branches that are extremely difficult to reconcile cleanly.

**Q14.** Does adding a read replica shield the primary from all performance problems?

**Answer:** No. It offloads read queries, yet write bottlenecks, bad queries, locks, and replication overhead still require optimization.

**Q15.** What risk exists if a database has HA and a geo-secondary without adequate PITR?

**Answer:** Zero safe recovery point if a bad schema migration or erroneous `DELETE` gets replicated.

**Q16.** Why doesn't a low DNS TTL guarantee apps instantly switch endpoints after failover?

**Answer:** Drivers/OSes/apps may cache DNS or retain old connections; reconnect, retry, and pool refresh logic are required.

**Q17.** Does enabling managed identity on an Azure VM/AKS automatically grant database permissions?

**Answer:** No. You must still configure authentication, database users/roles, service-specific Azure RBAC, and networking.

**Q18.** If a read replica lags 4 minutes while the dashboard SLO permits 1 minute, should the dashboard keep hitting the replica blindly?

**Answer:** Not without mitigation or clear staleness indicators. Reduce lag, reroute per policy, or flag that data misses the freshness SLO.

**Q19.** Does synchronous replication always mean zero downtime?

**Answer:** No. While data durability improves within design bounds, failover and reconnects still cause brief interruptions.

**Q20.** Is a geo-redundant backup identical to a hot geo-secondary ready for writes?

**Answer:** No. Backups require restore workflows, carry a different RTO, and do not behave like a promotable live replica.

**Q21.** When an app hits a connection timeout during `COMMIT`, what is the risk of retrying immediately?

**Answer:** The transaction may have committed while the ack was lost; non-idempotent retries can create duplicate side effects.

**Q22.** Which target matters more in failover design: RPO or RTO?

**Answer:** There is no universal answer. The business must define acceptable data loss vs. outage duration; sometimes they trade off directly against each other.

**Q23.** A read replica in Region B is ready, yet App B's private DNS zone is misconfigured. Is DR ready?

**Answer:** No. Data exists, yet the app cannot connect; end-to-end testing including DNS/network/TLS/identity is mandatory.

**Q24.** What can happen when a read-only geo-secondary shows sustained high CPU?

**Answer:** Heavy read queries can slow the replica and increase lag, hurting read performance and potentially degrading DR readiness.

**Q25.** Why does failback need its own dedicated runbook?

**Answer:** Once Region B accepts writes, data and replication topology have changed; you cannot simply flip a CNAME back to A without verifying sync/divergence.

**Q26.** Can you use the exact same PostgreSQL promotion command for Azure SQL Database?

**Answer:** No. They are different services/engines with different APIs and failover semantics.

**Q27.** When adding read replicas, where do costs accrue?

**Answer:** Compute/storage per replica, replication traffic, networking/private endpoints, monitoring, and DR operations.

**Q28.** What must a successful restore drill prove beyond the new resource showing Online?

**Answer:** Data matches the expected timestamp, schemas/permissions work, apps connect, reads/writes behave as expected, and recovery time/data loss meet targets.

**Summary:** **High availability** reduces disruption from infrastructure faults within supported host/zone bounds; **read replicas** offload reads at the cost of replication lag; **geo-replication** keeps data in another region while usually carrying async RPO risk. A reliable Azure database design combines **tier/region-appropriate HA, consistency-aware read routing, backups/PITR, geo-DR runbooks, idempotent reconnecting apps, network/identity security, monitoring, and real recovery drills**. The ultimate goal is not merely a database marked Online, but **accurate business operations recoverable within committed RTO and RPO**.