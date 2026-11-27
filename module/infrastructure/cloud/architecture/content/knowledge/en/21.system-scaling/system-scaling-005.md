# Partitioning by Business Domain, Customer, or Geography

As a system grows in users, transactions, and data volume, a single database or centralized server group becomes a bottleneck. Scaling up only goes so far; beyond that ceiling, the system must distribute data and load across multiple nodes, service groups, or deployment regions. A critical architectural decision is **which boundary to partition along**: by business domain, by customer/tenant, or by geography.

Partitioning by business domain gives each domain ownership over its own data and processing capacity. Partitioning by customer isolates data and load between tenants, fitting SaaS or multi-organization platforms. Partitioning by geography moves data and compute closer to users, supporting latency, regional resilience, and data residency requirements. These approaches can be combined, though each partitioning layer adds routing, operational overhead, consistency controls, and cost.

No single shard key or topology fits every workload. The decision must come from access patterns, tenant scale, data boundaries, transaction requirements, data laws, user locations, and operational capability. A sound design answers: where does each piece of data live, how are requests routed, how is an overloaded partition handled, and how can data be moved without breaking correctness?

This lesson belongs to the **System Scaling** section of the cloud architecture module. It focuses on partitioning by business domain, customer, or geography to balance scalability, reliability, security, performance, cost, and operations using Well-Architected principles.

After this lesson, you will be able to:

- Explain partitioning, sharding, and the difference between logical and physical partitions.
- Choose domain, tenant, or geographic partitioning based on workloads and business requirements.
- Design shard keys, partition maps, routing, and directory services.
- Identify hotspots, skew, large tenants, and limits of hash/range partitioning.
- Design transactions, consistency, uniqueness, and cross-partition queries.
- Plan rebalancing, migration, backup/restore, and multi-region failover.
- Evaluate data isolation, residency, observability, cost, and operability.

## 1. What Are Partitioning and Sharding?

Partitioning divides a dataset or workload into smaller parts according to a rule. Each part is a partition. Partitions can live inside a single database engine, across multiple nodes, or across different clusters/regions.

Sharding typically refers to distributing data across multiple independent database nodes or shards. Each shard stores a subset of data and serves a subset of requests. In practice, partitioning and sharding are sometimes used interchangeably; when designing systems, clarify whether you mean logical partitions inside one engine or physical shards with independent failure domains and lifecycles.

### Benefits

- **Scale out:** expand capacity by adding nodes or partitions.
- **Scoped load:** queries touch only the needed partition when keys and queries align.
- **Isolation:** tenants or domains can be isolated by data, quotas, and faults.
- **Locality:** place data near users or dependent services.
- **Lifecycle:** archive or delete data by region, tenant, or time.
- **Failure containment:** an outage in one shard can have bounded blast radius if routing and dependencies are well designed.

### Costs and Risks

- Cross-shard queries and joins become more complex.
- Multi-partition transactions make atomicity harder to guarantee.
- Routing, metadata, and shard placement become critical infrastructure.
- Rebalancing, backup, restore, and migration grow more complex.
- Skewed data distributions can overload one shard even with spare cluster capacity.
- A corrupted partition map or directory outage can cause widespread impact.

Sharding is not the default first step when load grows. Before splitting data, inspect indexes, query plans, connection pooling, caching, read replicas, vertical scaling, and workload separation. Add shards only with evidence that splitting data/load resolves a concrete bottleneck.

## 2. Choosing Partitioning Boundaries

The three primary boundaries solve different problems:

| Boundary | Unit of Division | Primary Goal | Main Challenges |
| --- | --- | --- | --- |
| **Business domain** | Bounded context, service, or data product | Ownership, autonomy, and independent scaling per capability | Cross-domain queries, transactions, and data coordination |
| **Customer/tenant** | Single tenant, tenant group, or tenant partition | Isolation, noisy-neighbor control, per-customer scaling | Tenant skew, tenant moves, and shared-vs-dedicated trade-offs |
| **Geography** | Region, country, market, or locality | Latency, residency, regional resilience | Routing, replication, data sovereignty, and cross-region consistency |

### 2.1. Partitioning by Business Domain

Split by domain when business capabilities differ in access patterns, lifecycles, SLOs, or team ownership. For example, Booking, Payment, Catalog, and Analytics can use separate datastores and scaling policies.

Benefits:

- Each domain optimizes schemas, indexes, and capacity for its own workload.
- Failures or load spikes in one domain have limited impact on others if dependencies are bounded.
- Teams can deploy and upgrade independently within contract boundaries.
- Data that does not need continuous joins can live close to its owning service.

Trade-offs:

- Cross-domain use cases require APIs, events, or a data platform to aggregate.
- Cross-domain transactions typically require Sagas or workflows.
- Must standardize identity, correlation, schemas, and security policies.
- Avoid splitting one domain into too many tiny services/partitions without matching ownership and operational maturity.

Domain partitioning is an ownership boundary first; it does not require giving every domain a separate cluster on day one. You can start with separate schemas/databases on shared infrastructure and physically separate when isolation or scale demands it.

### 2.2. Partitioning by Customer or Tenant

In SaaS platforms, many customers share one product while differing widely in data and traffic requirements. Three common models exist:

| Model | Storage Layout | Advantages | Trade-offs |
| --- | --- | --- | --- |
| Shared database, shared schema | All tenants share tables with a tenant key | Cost-efficient, centralized operations | Needs row-level isolation, indexes, and noisy-neighbor controls |
| Shared database, schema per tenant | Separate schemas inside the same engine/database | Clearer logical boundaries | Bulk migrations, many schema/objects, and engine limits |
| Database/shard per tenant or tenant group | Tenants placed on dedicated databases/clusters | Strong isolation, flexible backup/restore and placement | High cost, connection count, fleet operations, and migration effort |

No single model fits every tenant. A system can start with shared schemas for most customers, use shard groups as scale grows, and reserve dedicated databases for giant customers or strict isolation needs.

### 2.3. Partitioning by Geography

Data can be placed by country, market, or region serving users. This supports:

- Lower network latency for co-located users and services.
- Keeping data within geographic boundaries per legal/contractual requirements.
- Limiting blast radius when one region suffers an incident.
- Distributing load across markets and local peak hours.

However, multi-region does not automatically deliver consistency or DR. You must define which region is the writer, what read replicas serve, who owns write failover, what rules govern cross-region data transfer, and how conflicts are resolved.

## 3. Combining Multiple Partitioning Dimensions

Large systems often stack dimensions in an explicit hierarchy. For example, select a region by tenant residency, then shard by tenant ID inside the region, while Booking and Payment domains maintain separate datastores.

~~~mermaid
flowchart TD
    REQ["Request"] --> AUTH["Resolve identity and tenant"]
    AUTH --> GEO["Select permitted region"]
    GEO --> DOMAIN["Route to business domain"]
    DOMAIN --> TENANT["Resolve tenant partition"]
    TENANT --> SHARD["Selected shard / database"]
~~~

Example topology:

~~~text
Platform
  Region A
    Booking domain
      Tenant shard group 1
      Tenant shard group 2
    Payment domain
      Payment shard group 1
  Region B
    Booking domain
      Tenant shard group 3
    Payment domain
      Payment shard group 2
~~~

This diagram illustrates placement hierarchy only. Avoid adding too many partitioning dimensions because combinations multiply rapidly, complicating routing, metadata, deployments, monitoring, and restores. Every dimension needs an independent justification and clear owner.

## 4. Designing Shard Keys

The shard key determines which partition holds a record. Picking the wrong key creates hotspots, skewed distributions, or forces most queries to hit multiple shards.

A strong shard key generally:

- Has high enough cardinality and distributes fairly evenly under real load.
- Appears in most critical queries to enable direct routing.
- Remains immutable over the record's lifecycle.
- Does not expose sensitive data through the identifier.
- Aligns with transaction boundaries and business locality.
- Supports rebalancing or directory remapping as needs evolve.

### Key Types

| Type | Example | Advantages | Risks |
| --- | --- | --- | --- |
| Tenant ID | `tenant_id` | Isolates queries per customer | One giant tenant can become a hot shard |
| User/customer ID | `customer_id` | Distributes by user | Regional/time-range queries fan out |
| Geographic key | `country`/`region` | Keeps data near locality | Uneven population/load; users move |
| Hash key | `hash(account_id)` | Even distribution with well-distributed input | Hard range queries; changing shard count remaps many keys |
| Range key | `date` or ID range | Easy range scans and lifecycle management | New keys pile onto the latest partition, creating a hotspot |
| Composite key | `tenant_id` + bucket | Splits large tenants across buckets | Queries may fan out or need extra mapping |

### Hash Partitioning

A hash key maps an ID through a hash function to determine the partition. Conceptual example:

~~~text
partition = hash(tenant_id) mod N
~~~

With a fixed N partitions, changing N can force many tenants to switch shards. Hash partitioning works well when queries target exact keys and need even spread. Consistent hashing or virtual nodes cut the number of keys moved when adding/removing nodes, though you still need data migration and routing state updates.

### Range Partitioning

Range partitioning splits by key ranges or time, such as order IDs, creation dates, or ID blocks. It excels for range queries and archival, but new writes concentrate on the current range. Partition splitting, time bucketing, or distributed write strategies are needed to avoid hotspots.

### Composite Keys and Bucketing

If a tenant grows too large, partitioning purely by tenant ID dumps all its load onto one shard. You can split a tenant across multiple buckets:

~~~text
bucket = hash(resource_id) mod B
partition = placement(tenant_id, bucket)
~~~

This spreads a single tenant's load, though listing all data for that tenant may need to read across B buckets. Choose B based on access patterns and fan-out limits, not just current shard counts.

### Avoiding Low-Cardinality or Skew-Prone Keys

Keys like `status` (ACTIVE/INACTIVE), `country` with few distinct values, or current date create unbalanced partitions. Pair them with a hash suffix/bucket or pick another key with better spread. Measure both storage volume and request rate; balanced row counts do not guarantee balanced load.

## 5. Routing and Partition Directories

Once a key is resolved, the system must locate the target partition. Three common approaches exist:

1. **Deterministic routing:** clients/services compute the partition from the key using an agreed algorithm.
2. **Directory-based routing:** look up the tenant/key in a metadata service to find its current shard.
3. **Proxy/router layer:** requests pass through a dedicated routing proxy that also manages shard connections.

### Directory-Based Architecture

~~~mermaid
flowchart LR
    CLIENT["Application"] --> ROUTER["Shard router"]
    ROUTER --> DIR[("Partition directory")]
    DIR --> ROUTER
    ROUTER --> S1[("Shard A")]
    ROUTER --> S2[("Shard B")]
    ROUTER --> S3[("Shard C")]
    ADMIN["Placement controller"] --> DIR
    ADMIN --> MOVE["Migration workflow"]
    MOVE --> S1
    MOVE --> S2
~~~

The directory can store tenant → shard, region → cluster, virtual bucket → node, and placement versions. It becomes a critical dependency requiring caching, HA, versioning, auditing, and safe update procedures.

### Directory Caching

Routers can cache mappings to cut latency. However, stale mappings during a tenant migration can send writes to the old shard. Safeguards include:

- Placement versions or epochs.
- Mechanisms to detect stale routes and refresh.
- Dual-read or bounded forwarding windows during cutover.
- Fencing so only the currently owning shard accepts writes.
- Idempotent retries so rerouted requests do not create duplicates.

Never allow clients to supply arbitrary shard IDs in requests. Routing must rely on system-controlled identities and directories.

## 6. Querying Across Partitions

Queries carrying the shard key can usually route to one partition (single-shard query). Queries missing the shard key may hit multiple partitions (scatter-gather/fan-out) and merge results.

### Single-Shard Queries

If a request includes `tenant_id` or `account_id` and related records live on the same shard, the router sends it straight to that shard. This is the simplest path with the most predictable latency.

### Scatter-Gather Queries

For instance, a platform-wide order summary report reads multiple shards, merges results, and handles sorting/pagination. Fan-out scales with shard count and gets bottlenecked by the slowest shard.

Mitigations:

- Cap query fan-out and concurrency.
- Enforce timeouts, partial-result policies, and cancellation.
- Use aggregates, read models, or a data platform for recurring reports.
- Paginate with stable cursors rather than expensive global offsets.
- Avoid running BI queries directly across all OLTP shards.

### Cross-Shard Joins

Joining two tables sharing the same shard key executes locally on the shard. Joins across different keys or domains require choices:

- Denormalize just enough data for the query.
- Perform bounded application-level joins with caching.
- Build event-driven read models or materialized views.
- Offload data to an analytical platform.
- Redesign the shard key if that query is a core workload.

Never try to support arbitrary distributed joins across all shards on low-latency endpoints.

## 7. Transactions and Cross-Partition Consistency

When all records in a transaction sit on one shard, local transactions preserve familiar database semantics. When a transaction spans multiple shards, cost and complexity jump sharply.

### Keep Transaction Boundaries on One Shard

For example, a booking and its booking line items are typically queried and updated together. If they share `booking_id` or `tenant_id` as the shard key, transactions run locally. This is a primary criterion when picking keys.

### Cross-Shard Transactions

Distributed transactions/2PC may work if the engine and architecture support them, though coordinator and failure handling get complex. Often you can redesign the workflow as a Saga:

- Each shard/service executes a local transaction.
- Emit events or commands carrying an operation ID.
- Retry idempotently.
- Run compensating actions when completion fails.
- Reconcile indeterminate outcomes.

Never claim global atomicity if the system merely uses events and retries. APIs should expose `PENDING`/`PROCESSING` states while workflows are still in flight.

### Global Uniqueness

Standard unique constraints only enforce uniqueness within a single database/shard. If email addresses or external references must be globally unique:

- Use globally generated IDs with controlled collision risk.
- Maintain a registry/identity service with a clear uniqueness boundary.
- Route by the unique key if access patterns allow.
- Use a reservation/claim service before writing to other shards.

Do not rely on cross-shard read-then-write checks, since concurrent requests can both see the value as absent.

## 8. Tenant Partitioning and Noisy-Neighbor Isolation

Tenants vary drastically in load. One enterprise tenant can generate more requests or data than thousands of small tenants combined. If everyone shares a single shard with shared quotas, large tenants degrade service for others.

### Tiered Placement Strategy

A hybrid strategy:

- Small tenants: shared shard groups distributed via hashing.
- Medium tenants: controlled placement based on capacity and workload.
- Large tenants: dedicated shards or dedicated databases when isolation value justifies cost.
- Regulated tenants: placed in specific regions/accounts with dedicated security policies if required.

### Quotas and Fairness

Set per-tenant limits: request rates, concurrent jobs, storage, connections, queue depth, and export sizes. Use rate limits/token buckets, workload queues, and priority policies so large tenants cannot monopolize capacity.

Quotas must tie to contracts and SLOs. On breach, return appropriate retryable errors or throttle; never queue silently forever and blow up latency and cost.

### Tenant Migration

Moving a tenant from a shared shard to a dedicated shard requires:

1. Selecting the tenant and sizing its data/load.
2. Provisioning the target and verifying version/schema/indexes.
3. Taking a snapshot or initial copy.
4. Streaming delta/CDC updates up to a checkpoint.
5. Switching reads to the target or running dual-reads for validation.
6. Cutting over the writer with fencing/epoch checks while handling in-flight requests.
7. Reconciling row counts, checksums, and business invariants.
8. Holding a rollback window and deleting old source data per policy.

Never flip a directory mapping and assume data moved safely.

## 9. Geographic Partitioning and Multi-Region

Geo-partitioning places tenants or data by locality such as country or market. A tenant may have a fixed home region, or data may partition per object/location. Clarify which rule is mandatory.

### Home-Region Model

Each tenant has one home region for authoritative writes. Users can enter through edge/API gateways and get routed to their home region. Read replicas elsewhere can serve reads if the business tolerates lag.

Pros: clear writer ownership and minimal write conflicts. Trade-offs: distant users see higher latency; home-region outages require controlled DR/failover.

### Regional Data Residency

When laws or contracts mandate storing data within a specific country or region, check:

- Where primary data, backups, logs, snapshots, and exports reside.
- Whether telemetry contains PII or sensitive payloads.
- Whether support access or control planes transfer data out of region.
- Whether cross-region replication is permitted.
- How data deletion and retention execute across every copy.

Never assume the physically closest region satisfies residency. Verify services, regional availability, backup behavior, and legal contracts.

### Active-Passive vs. Active-Active

| Model | Data Writes | Advantages | Risks |
| --- | --- | --- | --- |
| Active-passive | One region writes, standby region waits | Clear writer ownership, simpler failover reasoning | Failover downtime, replication lag, and failback |
| Active-active | Multiple regions accept writes | Low latency and regional serving | Conflict resolution, duplicates, ordering, and consistency are highly complex |

Active-active only works when data and business logic have clean conflict rules, such as owner-partitioned data or mergeable operations. If the same balance or inventory slot can be written simultaneously in two regions, coordination or single-writer rules are required.

### Regional Failover

Runbooks must specify:

- Criteria for declaring a region down and who authorizes failover.
- Checking whether replicas meet RPO freshness.
- Fencing the old writer to prevent split-brain.
- Updating routing/directories/DNS.
- Handling in-flight requests and idempotent retries.
- Reconciling data post-failover.
- Failback procedures, never automatically shifting writes back without validation.

## 10. Rebalancing and Topology Changes

When adding nodes, filling shards, or moving tenant tiers, data must be redistributed. This is one of the riskiest operations in a sharded system.

### When Is Rebalancing Needed?

- A shard exceeds target storage or QPS capacity.
- A large tenant creates a hotspot.
- Nodes are added or removed due to growth or failure.
- Virtual bucket counts or placement policies change.
- Tenants migrate to new regions or dedicated shards.

### Techniques

- **Consistent hashing/virtual nodes:** minimizes key remapping when node membership changes.
- **Directory remapping:** controlled mapping updates after copying data.
- **Split/merge partitions:** split hot ranges or merge tiny partitions.
- **Online migration:** background copy, CDC deltas, fenced cutover.
- **Tenant evacuation:** migrate a single tenant via a dedicated pipeline.

### Suggested Online Migration Workflow

~~~mermaid
flowchart TD
    A["Plan target capacity"] --> B["Create target partition"]
    B --> C["Initial snapshot copy"]
    C --> D["Stream ongoing changes"]
    D --> E["Validate counts, checksums, invariants"]
    E --> F{"Lag within threshold and validation pass?"}
    F -- "No" --> D
    F -- "Yes" --> G["Fence writes / short cutover"]
    G --> H["Switch placement version"]
    H --> I["Monitor target and reconcile"]
    I --> J["Retire old partition after rollback window"]
~~~

### What Must Be Protected

- Never allow old and new writers to accept uncoordinated writes concurrently.
- Copy data without missing updates/deletes occurring mid-copy.
- Persist checkpoints durably so migrations can resume.
- Ensure consumers and routers handle stale mappings.
- Use idempotency to protect retries during shard transitions.
- Maintain a rollback plan and understand rollback limits once the target accepts new writes.

## 11. Hotspots, Skew, and Capacity Planning

A cluster can have plenty of aggregate headroom and still crawl if one shard takes most traffic. Balanced row counts do not guarantee balanced request rates.

### Symptoms

- One partition shows noticeably higher CPU, IO, or connections.
- p99 latency spikes for a specific tenant/key group.
- Queue backlogs and retries pile up on one shard.
- Skewed storage growth or one range expanding rapidly.
- Routers frequently fan out queries to every shard.

### Mitigations

- Pick a better shard key or add buckets for large tenants.
- Move hot tenants onto dedicated shards.
- Cache hot reads without making the cache the transactional decision point.
- Throttle hot tenants or noisy workloads.
- Split partitions/ranges and rebalance.
- Offload analytical/reporting workloads from OLTP shards.

### Capacity Sizing

Do not size solely on storage:

~~~text
Shard demand =
  storage footprint
  + read/write QPS
  + active connections
  + CPU per query
  + IO/throughput
  + replication/backup overhead
  + growth and failover headroom
~~~

Capacity planning must be validated at steady state, peak, growth horizons, and failure modes when a shard/node/region is lost. If N shards run near 100% capacity, losing one shard and shifting load onto the survivors can collapse the whole system. Reserve headroom based on SLOs and failure scenarios.

## 12. Security, Isolation, and Data Governance

Partitioning can strengthen isolation, but only when every access path enforces placement and authorization policies.

- Extract tenant identity from verified tokens/sessions; never trust self-declared tenant IDs in request bodies.
- Routers must resolve tenant → region/shard mappings from a secured directory.
- Query layers must enforce tenant scoping or appropriate row-level security.
- Scope database credentials per service/shard with least privilege.
- Cross-tenant data must never leak via cache keys, logs, traces, or reports.
- Enforce encryption at rest/in transit and region-appropriate key policies.
- Backups, replicas, snapshots, logs, and exports must obey the same data classification/residency rules.
- Audit placement changes, permission updates, and data movements.

Schema-per-tenant or database-per-tenant does not guarantee security if admin credentials access every tenant or routers lack strict checks. Audit both control plane and data plane.

## 13. Observability and Operating Sharded Systems

A request may traverse gateways, routers, directories, services, and shards. Observability must track logical tenants, partitions, and physical nodes together.

### End-to-End Identifiers

Every request, log, and trace should carry controlled metadata:

- Request/correlation ID.
- Domain/service name.
- Masked/hashed tenant identifier per policy.
- Region, shard ID, and placement version.
- Query class or operation name.
- Retry count, routing decision, and error category.

Never place PII or credentials in high-cardinality metric labels. Design shard/tenant labels carefully so they do not overwhelm monitoring backends.

### Key Metrics

| Metric | Purpose |
| --- | --- |
| Read/write QPS per shard | Detect skewed load |
| CPU, memory, IOPS, storage, and connections | Track capacity |
| p50/p95/p99 per tenant/shard/region | Surface tail latency |
| Router cache hit rate and directory latency | Monitor routing dependency health |
| Fan-out count and scatter-gather duration | Catch queries missing shard keys |
| Replication lag per region/shard | Track freshness and RPO |
| Rebalancing lag/bytes/errors | Monitor live migrations |
| Failed/stale routes and retries | Spot mapping bugs |
| Hot tenants/keys and quota throttling | Control noisy neighbors |
| Backup/restore status | Ensure recoverability |

### Essential Runbooks

- Shard unavailable or node loss.
- Stale or unreachable directory/router.
- Tenant exceeding quotas or causing a hotspot.
- Stuck rebalancing or validation mismatch.
- Cross-region replication lag or failover.
- Tenant migration rollback.
- Restoring one tenant/shard without impacting others.

## 14. Partitioned Backup, Restore, and Disaster Recovery

Backups in sharded systems require coordination. Snapshots taken on individual shards at different timestamps may not yield a business-consistent recovery point.

### Backup Policies

- Define backups per shard, tenant, region, and whole system.
- Record timestamps, LSNs/offsets, or required checkpoints.
- Back up directory/placement metadata alongside versions.
- Encrypt and store backups per residency policy.
- Test restoring an individual tenant/shard as well as full-cluster restores.
- Maintain runbooks to rebuild routers, credentials/secrets, and networking.

### Restoring a Single Tenant

On shared shards, restoring an entire shard directly overwrites updates from other tenants. Options:

- Restore the snapshot into a staging environment and extract the tenant's rows via point-in-time logic.
- Maintain per-tenant logical backups/exports.
- Restore into a new shard and repoint the tenant via the directory after validation.
- Replay audit/event logs post-snapshot if supported.

Not all database engines support tenant-level PITR; verify capabilities thoroughly before committing to SLAs.

## 15. Common Mistakes

**Picking a shard key purely by data volume.** Request load and access patterns create hotspots; balanced row counts are not enough.

**Using tenant ID as the shard key with no large-tenant strategy.** One enterprise tenant can melt a single shard; plan bucketing or dedicated placement.

**Partitioning by region without defining writer ownership.** Two regions can accept conflicting writes or split-brain.

**Assuming hash partitioning solves all queries.** Range queries and cross-shard reports still fan out; build read models/warehouses.

**Changing shard counts without a migration plan.** Deterministic modulo remapping can force moving almost all data.

**Updating the directory after only a partial copy.** Requests can read/write the wrong shard; enforce checkpoints, fencing, and clean cutover.

**Omitting placement versions.** Stale router caches keep sending writes to old partitions.

**Allowing arbitrary cross-shard transactions.** Latency and failure surfaces explode; prefer Sagas and tighter aggregate boundaries.

**Scanning every OLTP shard for reports.** Fan-out queries overload transactional systems; move reporting to a data platform.

**Equating database-per-tenant with complete security.** Credentials, backups, logs, and control planes can still allow cross-tenant access.

**Never testing single-tenant restores.** Full-cluster backups do not prove you can recover one customer cleanly.

**Forgetting fleet operational costs.** More shards multiply backups, monitoring, patching, version drift, migrations, and support burden.

## 16. Design Example: Multi-Country Booking SaaS Platform

**Hypothetical Context:** A platform serves clinics across multiple countries. Small tenants share infrastructure; several large clinic chains generate heavy traffic; certain customers legally require in-country data residency. Booking and Payment have distinct workloads, ownership, and SLOs. A platform-wide dashboard aggregates daily metrics.

### Partitioning Design

1. Select region based on tenant residency/home region.
2. Inside each region, separate Booking and Payment domains for independent ownership, scaling, and access policies.
3. Place small tenants into shared shard groups using hashes/virtual buckets.
4. Give large tenants dedicated placement or reserved-capacity shard groups.
5. Routers query a directory resolving tenant → region/domain/partition and placement version.
6. An analytics data platform ingests authorized events/CDC for cross-domain reporting; never fan out OLTP queries for dashboards.

~~~mermaid
flowchart TD
    USER["User request"] --> GATE["API Gateway + authentication"]
    GATE --> DIR["Tenant placement directory"]
    DIR --> RA["Region A"]
    DIR --> RB["Region B"]
    subgraph A["Region A"]
        BA["Booking shard group"]
        PA["Payment shard group"]
    end
    subgraph B["Region B"]
        BB["Booking shard group"]
        PB["Payment shard group"]
    end
    RA --> A
    RB --> B
    BA --> EV["Governed events / CDC"]
    PA --> EV
    BB --> EV
    PB --> EV
    EV --> DP["Analytics data platform"]
~~~

### Decisions That Must Be Validated

- Do shared shards meet quotas and isolation for small tenants?
- Can large tenants migrate to dedicated shards without prolonged downtime?
- What happens during a directory outage; do routers cache mappings and enforce fencing?
- Does regional failover respect residency and RPO?
- Do Payment and Booking require local transactions or Sagas when coordinating?
- Can dashboards report cross-region using governed, authorized data feeds?
- Can a single tenant be restored without rolling back other tenants?

## 17. Hands-On Exercise: Designing a Partitioning Strategy

**Scenario:** A SaaS platform serves 10,000 businesses across three regions: 9,700 small tenants, 250 medium tenants, and 50 large tenants. A handful of large tenants generate 35% of total requests. Customers in certain markets mandate keeping data in designated regions. Workloads include reading bookings by tenant and date, writing bookings by ID, querying tenant-wide reports, and looking up payments. (Simulated figures for practice.)

### Tasks

1. **Select topology:** order domain, tenant, and geographic partitions; distinguish logical ownership from physical shards.
2. **Choose shard keys:** propose keys for bookings and payments; explain single-shard queries, hot tenants, range scans, and cross-shard reporting.
3. **Design the placement directory:** define mappings, versioning, caching, HA, routing, and update permissions.
4. **Build tenant tiering:** assign small/medium/large tenants to shared, shard-group, or dedicated models; define graduation triggers.
5. **Design consistency:** transaction boundaries, global uniqueness, Sagas, read models, and event flows.
6. **Design geography:** home regions, writer ownership, read replicas, residency, DR/failover, and failback.
7. **Create a migration plan:** move a hot tenant onto a dedicated shard via snapshots/CDC, validation, fencing, and cutover.
8. **Design operations:** skew metrics, QPS, latency, fan-out, directory health, lag, backups, and runbooks.

### Test Matrix

| Test | Scenario | Required Evidence |
| --- | --- | --- |
| Tenant isolation | Forged tenant ID or spoofed routing input | Zero cross-tenant reads or writes |
| Hot tenant | Large tenant multiplies load severalfold | Quotas/fairness engage; other tenants hold SLOs |
| Shard unavailable | One database shard loses connectivity | Bounded retries/fallbacks; blast radius contained |
| Directory stale | Router holds stale mapping mid-migration | Placement version/fencing blocks misrouted writes |
| Rebalance | Move virtual bucket/shard | Counts, checksums, and business invariants match |
| Cross-shard query | Tenant-wide report | Fan-out bounded or served via read model |
| Region outage | Home region goes offline | RTO/RPO and writer fencing meet plan |
| Replica lag | Read replica falls behind | Read-after-write queries fall back to writer |
| Restore tenant | Single tenant needs recovery | Zero data loss for other tenants |
| Residency audit | Audit data/backup/log locations | Zero policy-violating replicas |
| Duplicate retry | Request retried across routing change | Idempotency prevents duplicate records |
| Capacity failover | One shard dies, load shifts to survivors | Sufficient headroom or admission control protects system |

### Deliverables

- Logical/physical partition topology diagram.
- Shard key decision record and query routing matrix.
- Tenant tiering and placement policy.
- Directory API/data model and versioning strategy.
- Multi-region/residency/DR plan.
- Online migration/rebalancing runbook.
- Security/isolation matrix.
- Load, failure, restore, latency, and cost validation report.

## 18. Well-Architected Evaluation

| Pillar | Partitioning Questions |
| --- | --- |
| **Operational Excellence** | Do you have a placement inventory, routing versions, migration runbooks, capacity dashboards, and shard owners? |
| **Security** | Are tenant isolation, regional residency, IAM, backup/log access, and placement audits enforced? |
| **Reliability** | Have shard/region failures, directory outages, stale routes, backup/restore, and rebalancing recovery been tested? |
| **Performance Efficiency** | Do shard keys balance both QPS and storage? Are query fan-out, hot keys, connections, and tail latency measured? |
| **Cost Optimization** | Are shared/dedicated trade-offs, replication, backups, cross-region transfers, and fleet overhead justified? |
| **Sustainability** | Are over-sharding, redundant data duplication, idle nodes, and unnecessary rebalancing avoided? |

## 19. Production Readiness Checklist for Partitioning

- [ ] Bottlenecks measured and proven unsolvable by indexing, caching, or scaling up alone.
- [ ] Domain, tenant, and geographic boundaries backed by clear business justification.
- [ ] Shard keys align with queries, transaction boundaries, cardinality, and QPS distribution.
- [ ] Hot tenants/keys and data skew have explicit mitigation strategies.
- [ ] Single-shard and fan-out queries enforce policies, timeouts, and concurrency caps.
- [ ] Directory/routers provide HA, caching, versioning, auditing, and stale-mapping handling.
- [ ] Tenant isolation, authentication, authorization, and quotas tested.
- [ ] Cross-shard transactions cleanly designed; Sagas used where appropriate.
- [ ] Global uniqueness backed by an appropriate registry/claim strategy.
- [ ] Home regions, writer ownership, residency, replication, and failover defined.
- [ ] Rebalancing/migrations cover snapshots, CDC, checkpoints, fencing, validation, and rollback windows.
- [ ] Backups/restores cover both shard data and placement metadata; single-tenant restores tested.
- [ ] Per-tenant/shard/region observability maintains bounded cardinality and actionable alerts.
- [ ] Capacity headroom verified even under shard/region loss.
- [ ] Cost models include replicas, backups, networking, routers, directories, migrations, and fleet operations.
- [ ] ADR, runbooks, owners, and revisit triggers documented for load/tenant/region shifts.

Partitioning by business domain, customer, or geography lets systems scale and isolate load along meaningful boundaries. Yet every boundary adds routing, consistency, migration, and operational overhead. Start from access patterns and ownership, pick shard keys reflecting both queries and load distribution, and design directories, isolation, failover, and rebalancing as first-class capabilities. A sharded system truly scales only when it can distribute data **and** change placement safely, observably, and recoverably when failures hit.
