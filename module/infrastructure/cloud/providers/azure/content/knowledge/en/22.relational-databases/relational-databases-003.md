# DTU, vCore, Serverless, and Elastic Pool

An e-commerce system has an Azure SQL Database running steadily during the day with very few queries at night. Another SaaS company manages 40 separate databases for 40 customers, each with different peak usage hours. Choosing a compute tier by guesswork can leave a business paying for idle resources or suffering high latency when transactions spike.

**Azure SQL Database** provides multiple ways to allocate and bill resources. Four key terms are:

- **DTU (Database Transaction Unit):** a bundled resource model combining CPU, memory, and I/O into performance tiers.
- **vCore (virtual core):** a model expressing resources by virtual core count, memory, storage, and supported hardware/service options.
- **Serverless:** a compute tier within vCore capable of auto-scaling compute with load and, in supported configurations, auto-pausing during inactivity.
- **Elastic pool:** a group of independent databases sharing a pool compute budget instead of provisioning dedicated compute for each database.

Common misconception: **DTU and vCore are resource purchasing models; serverless is a compute provisioning tier; elastic pool is a model for grouping multiple databases to share compute**. They are not four different database engines.

This lesson belongs to the **Relational Databases** chapter of the **CLOUD_PROVIDERS_AZURE** module. The learning path explores Azure from subscriptions, resource groups, and Microsoft Entra ID to VNet, compute, storage, and data; finally learning to deploy, monitor, protect, and control costs for an application architecture on Azure.

> **Scope:** Focuses on **Azure SQL Database** single databases and elastic pools. Do not directly apply the DTU, serverless, or elastic pool options from this lesson to **Azure SQL Managed Instance**, **SQL Server on Azure VM**, or **Azure Database for PostgreSQL**, as their service models and limits differ. SKUs, tiers, limits, and availability vary by region and over time; verify currently supported Azure configurations before purchasing resources.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish DTU/eDTU, vCore, provisioned compute, serverless, and elastic pools.
2. Describe the relationship between DTU's **Basic/Standard/Premium** and vCore's **General Purpose/Business Critical/Hyperscale**.
3. Explain serverless autoscaling, minimum/maximum vCores, auto-pause, auto-resume, and latency impacts.
4. Choose a single database or elastic pool for one or multiple tenants with varying load cycles.
5. Read and interpret CPU, data I/O, log write, workers, sessions, storage, and resource exhaustion signals.
6. Compare options across workload, SLA, security, availability, cost, and operations.
7. Understand the safe process for changing a service objective, validating performance, and preparing rollbacks.
8. Use the Azure portal, Azure CLI, and T-SQL to inspect details before making decisions.

## 1. What Is Azure SQL Database?

Azure SQL Database is a **PaaS relational database** compatible with the SQL Server ecosystem within its supported feature scope. Azure manages many infrastructure tasks such as hardware, the operating system, underlying backup mechanisms, and service availability. Users remain responsible for schema design, queries, data security, application connectivity, performance, authorization, and cost governance.

~~~text
Application / API / worker
        |
        | TDS/SQL connection protected by TLS
        v
Azure SQL logical server
        |
        +-- Database: sales-db
        |
        +-- Database: billing-db
        |
        +-- Database: tenant-001
        |
        +-- Database: tenant-002
        |
        +-- Elastic pool (if configured):
              tenant-003, tenant-004, ...
~~~

**Logical server** is an administrative resource managing endpoints, authentication, and related settings; it does not equate to a VM where you assign CPU directly. Compute and performance of each database or pool are governed by their respective service options.

### First Questions When Choosing Resources

- Is there **one large database** or **multiple separate databases**?
- Is load steady all day or are there long idle periods?
- Do databases peak **simultaneously** or at staggered times?
- Can response times tolerate wake-up latency during serverless auto-resume?
- Is the primary bottleneck concern CPU, I/O, log throughput, memory, concurrency, or storage size?
- What levels of HA, geo-replication, backup/PITR, regional compliance, and access control does the data need?

## 2. Overview of Options

| Model | Primary Resource/Unit | Best Suited For | Trade-Offs |
|---|---|---|---|
| **DTU single database** | DTU level combining CPU/memory/I/O | Simple single database wanting an easy bundled resource tier | Harder to inspect separate CPU/RAM vs. demand |
| **vCore provisioned single database** | Number of vCores and tier/hardware properties | Steady workloads needing clearer compute control | Compute stays provisioned even at low load |
| **vCore serverless single database** | Min/max vCores and active compute usage; auto-pause when supported | Variable workloads with idle windows | Cold start, compatibility limits, and billing while active |
| **DTU elastic pool** | Total pool **eDTUs** and per-DB limits | Many small DBs with staggered loads | DBs compete for a shared budget |
| **vCore elastic pool** | Total vCores/storage per pool model and per-DB limits | Multi-tenant SaaS, many DBs sharing compute | Requires concurrent sizing, avoiding noisy neighbors |

A database can transition between supported configurations, though not every transition is online, instantaneous, or unconditional. Check service tier limits, transition duration, and connection impacts before executing in production.

### Classification Rules

~~~text
                         Azure SQL Database
                                 |
                    Choose resource allocation model
                      /                    \
                     v                      v
                 DTU model               vCore model
                 /       \                /        \
                v         v              v          v
            Single DB  Elastic pool   Single DB  Elastic pool
                                     /      \
                                    v        v
                               Provisioned  Serverless
                               per tier     in supported configs
~~~

The diagram illustrates common models; **serverless is not an elastic pool type you can select by default**. Combinations involving Hyperscale, elastic pools, and compute tiers must be verified against the current support matrix.

## 3. What Is a DTU?

A **Database Transaction Unit (DTU)** is a blended performance measure based on characteristics such as:

- CPU processing power.
- Memory.
- Data I/O.
- Log I/O.

Azure provides service objectives at different DTU levels. Each level includes resource limits and service levels. You pick a level instead of specifying exact vCore counts and individual hardware components.

~~~text
A single database using DTU:

      CPU
        \
      Memory ----> DTU level/SKU ----> Database capacity
        /
     Data I/O
        \
       Log I/O
~~~

For example, **Standard S2** and **Standard S3** are DTU-model service objectives (different resource tiers). Do not look only at the S2/S3 name and infer a direct conversion to vCore counts: they are **bundled resource packages**.

### When Is DTU Useful?

- Small or medium applications without needing separate compute/hardware selection.
- Teams wanting to start with a simple service objective.
- Systems already running steadily on DTU with no clear technical/cost reason to switch models.
- Workloads fitting the provided CPU/memory/I/O bundle.

### Limitations of DTU Thinking

A database with high DTU usage is not necessarily short on CPU alone. The cause could be data I/O or log write throughput hitting its limit. Increasing DTU can help, but does not replace optimizing queries, indexes, batch sizes, and transactions.

**DTU is not the maximum number of SQL transactions per second.** There is no reliable conversion like "100 DTUs = 100 transactions/second." Actual throughput depends on schema, locks, data size, queries, and read/write patterns.

## 4. Service Tiers in the DTU Model

| Tier | General Characteristics | Example Workloads |
|---|---|---|
| **Basic** | Small resource level for simple workloads | Labs, small apps, and suitable dev/test |
| **Standard** | Intermediate performance levels | Steady web apps/line-of-business apps |
| **Premium** | Higher performance levels with suited I/O/latency characteristics | Heavy transactional workloads needing high performance |

Each tier has limits on size, concurrency, backup retention, and features per SKU. Never conclude that switching from Standard to Premium will automatically fix every slow query.

### How to Read a DTU Metric

Suppose Azure Monitor shows the database frequently approaching 100% DTU during peak hours. Next steps:

1. Inspect **CPU percentage**, **data IO percentage**, **log IO percentage**, and related metrics.
2. Identify which requests cause load, and check for blocking or large index scans.
3. Check read/write ratio, connection counts, workers, and sessions.
4. Measure latency before and after optimization.
5. If saturation persists under real load, then consider increasing the DTU tier or migrating to vCore.

**Brief high usage** might simply be a normal batch job. What matters is sustained high utilization accompanied by timeouts, throttling, or missed SLAs.

## 5. What Is an eDTU?

An **Elastic Database Transaction Unit (eDTU)** is the bundled resource unit inside a **DTU elastic pool**. Instead of assigning dedicated DTUs to each database, you purchase a shared eDTU budget used by multiple databases based on actual load.

~~~text
DTU single:
  tenant-A --> S2 database
  tenant-B --> S2 database
  tenant-C --> S2 database

DTU elastic pool:
  tenant-A --\
  tenant-B ---+--> Shared eDTU budget
  tenant-C --/
~~~

**Do not add the pool's eDTUs and individual database DTUs as two separate compute bills.** Within a pool, databases draw from the shared pool budget subject to per-database configured limits.

### Why Is It Called Elastic?

One tenant may peak at 9 AM; another peaks after business hours; a third has almost no transactions. A pool exploits **non-simultaneous load**, avoiding provisioning full peak compute separately for every database.

If multiple tenants peak simultaneously, the pool remains bounded by the total purchased resources. Elastic **does not mean infinite capacity or free automatic pool budget expansion**.

## 6. What Is vCore?

**vCore** is an Azure SQL Database configuration model specifying compute in **virtual cores**, alongside service tier, hardware, memory profile, and supported storage choices. It helps administrators relate more directly to SQL workloads already measured by CPU, memory, and I/O.

Common benefits:

- Clearer visibility into compute budgets via **vCore counts**.
- Choice among **service tiers** with distinct performance/architectural profiles.
- Ability to leverage **Azure Hybrid Benefit** when eligible and supported.
- Options for **reserved capacity** or supported cost commitments depending on service/tier.
- Easier capacity translation from observed CPU/IO than bundled DTUs, though benchmarking is still required.

### A vCore Is Not a Dedicated Physical CPU

A vCore is a cloud service compute unit tied to a hardware generation/configuration. One vCore is not a promise of a dedicated physical core on every SKU.

**The same vCore count on different service tiers/hardware can yield different performance and costs.** Memory, storage latency, I/O limits, and tier topology affect real-world performance.

## 7. vCore Service Tiers

Azure SQL Database primarily offers these tiers:

| Tier | General Architecture/Characteristics | When to Use |
|---|---|---|
| **General Purpose** | Balanced price and performance, compute and storage per tier architecture | Common business apps, workloads not needing ultra-low I/O latency |
| **Business Critical** | Oriented toward low I/O latency, high availability/replicas, and high performance per tier topology | Heavy OLTP, workloads with strict performance and SLA demands |
| **Hyperscale** | Decoupled compute/storage architecture with scalable capacity per Hyperscale design | Large databases, rapid growth, specialized scale/storage needs |

**Hyperscale is not just "Business Critical with more GB."** Each tier has its own architecture, HA, backup/restore, and limits. Do not assume features like auto-pause, elastic pools, zone redundancy, or secondary replicas behave identically across all tiers.

### Choosing General Purpose vs. Business Critical

Measure **latency and bottlenecks**. If a General Purpose database has data I/O latency slowing transactions and query optimization isn't enough, Business Critical may be worth evaluating. If the issue is transaction locking or missing indexes, upgrading tiers may not bring proportional gains.

### When to Consider Hyperscale

- Database size is growing beyond the comfortable capacity of the current tier.
- Restore/scale/read workloads require Hyperscale's specific capabilities.
- You want storage and replica architectures scalable per Hyperscale design.

Before migrating, check **feature limitations, forward/backward transitions, latency, backup retention, billing, and restore capabilities** under current configurations. Never treat moving between tiers as an instantaneously reversible operation.

## 8. Provisioned Compute in the vCore Model

**Provisioned compute** allocates compute at the chosen vCore level. The database receives a fixed CPU/memory budget per SKU, even during low-activity hours.

~~~text
Application load over 24 hours:

Low low low | HIGH HIGH | low low low

Provisioned vCore:
Selected compute remains present per service objective,
never dropping to 0 simply because there are no queries.
~~~

Advantages:

1. Resources are provisioned at predictable levels, suited for continuous or steady loads.
2. Avoids auto-resume delays from serverless auto-pause.
3. Easy to budget compute based on provisioned size for the period.
4. Can pair with reserved capacity/Azure Hybrid Benefit when eligible.

Trade-offs:

- Pays for compute even when the database is lightly used under the billing model.
- Changing vCore counts typically requires changing the service objective, which can briefly impact connections/latency during scaling.
- Does not guarantee good application performance if queries, locking, or networking are the bottleneck.

Provisioned is appropriate when **consistent latency is required** and the database carries a regular baseline load.

## 9. What Is Serverless in Azure SQL Database?

**Serverless** is a **vCore compute tier** for **single databases in supported service tiers/configurations**. It can:

- Automatically scale compute between **minimum vCores** and **maximum vCores** based on demand.
- Bill compute based on actual usage, the billing model, and tier rules.
- In supported configurations, **auto-pause** after an inactivity period.
- **Auto-resume** when triggered by a qualifying connection/activity.

~~~text
             Load over time

vCores
   ^
  4|                  /----\
   |                 /      \
  2|        /-------/        \--
   |       /
0.5|------/
   +---------------------------------> hours
      Idle   Load rises     Peak

Serverless: compute scales up/down within selected min/max.
Auto-pause (if supported) is separate behavior when idle conditions are met.
~~~

**Serverless does not mean no servers and no costs.** Data still resides on managed storage, uses backup mechanisms, and still incurs storage or related service fees.

### Serverless Is Not an Elastic Pool

Serverless **scales compute for one database**. An elastic pool **shares a compute budget across multiple databases**. In this lesson, do not treat a serverless database like a multi-tenant pool, and do not assume every database inside an elastic pool can be set to serverless like a single database.

### Configurations Supporting Serverless

Serverless is available in **General Purpose** and supported **Hyperscale** configurations of Azure SQL Database, yet **auto-pause/auto-resume behavior is not identical across tiers**. Specifically, do not assume Hyperscale serverless auto-pauses identically to General Purpose serverless. When selecting an SKU, inspect the support matrix, region, hardware, and enabled features.

## 10. Min vCores, Max vCores, and Autoscaling

A serverless database can be configured with:

~~~text
Min compute: 0.5 vCore (for example, when supported by SKU)
Max compute: 4 vCores
Idle window: auto-pause delay per supported configuration
~~~

During low load, the database can use less compute than the maximum; when CPU/memory demand rises, compute can scale within the allowed bounds. I/O, log, worker, latency, and memory limits still apply per tier/hardware.

### No Guarantee of Instantaneous Autoscaling

When a hundred heavy queries arrive suddenly, compute does not necessarily jump to max vCores in the same millisecond. Reaction time, memory pressure, workload mix, and service limits all influence the outcome.

### Setting Minimum Too Low Can Cause Issues

- Baseline load may face memory starvation or frequent compute scaling.
- Initial burst queries may run slower than on provisioned.
- Latency-sensitive connections/workflows can be impacted.

### Setting Maximum Too Low Is Also Risky

If sustained CPU demand equals eight vCores but max is capped at two, the database remains throttled. Serverless scales **within the configured bounds**, never raising the ceiling beyond your cost limit.

### Data to Inform Decisions

Measure:

- CPU and memory usage over time.
- Data I/O and log I/O percentages.
- Transaction p95/p99 latency.
- Connection counts, workers, sessions.
- Peak frequency, peak duration, and actual idle windows.

## 11. Auto-Pause and Auto-Resume

With a **serverless configuration supporting auto-pause**, the database can pause after an idle period. When triggered, the database auto-resumes to serve connections.

~~~text
22:00  No remaining application queries
       |
       | No activity preventing pause
       v
       Auto-pause delay elapses
       |
       v
    Database PAUSED
       |
08:00  Client opens connection
       |
       v
    RESUMING
       |
       v
    ONLINE / connections handled
~~~

Timestamps only illustrate sequence, **not a guaranteed auto-resume duration**. Resuming introduces latency that clients must handle with controlled timeouts and retries.

### Conditions for Auto-Pause to Work

You must verify:

1. Does the SKU/tier support auto-pause?
2. Is auto-pause delay configured and not disabled?
3. Are there any sessions/activities or features preventing auto-pause per rules?
4. Are jobs, monitoring queries, health checks, or connection pools continuously waking the database?
5. Are any HA/replication features or service states enabled that are incompatible with auto-pause?

**Do not assume setting an auto-pause delay guarantees the database pauses every night.** A periodic health probe sending `SELECT 1` can keep it awake, depending on the app and pause rules.

### How Cold Starts Affect APIs

An API with a 200 ms response SLA may not suit a paused database if the first request must wait for resume. Meanwhile, an internal reporting system running a few times a day can tolerate wake-up latency.

Clients should implement:

- Appropriate connection timeouts and command timeouts.
- Retries with backoff/jitter for suitable transient errors.
- User-facing states like "initializing data" if needed.
- Limits on concurrent retrying clients to avoid a retry storm.

**Never infinitely retry non-idempotent writes.** A timeout can occur after the server already committed the transaction.

## 12. Serverless Costs

In serverless, costs must be viewed through **compute consumed while the database is active**, min/max configuration, memory/CPU billing, and **storage costs**. When a database actually auto-pauses in a supported configuration, inactive compute stops accruing active compute charges, while storage and related services continue billing.

### Intuitive Model

~~~text
Total serverless cost in period
  ≈ Billed compute while active
    + Storage/data size per tier
    + Excess backup/retention charges if any
    + Networking/monitoring/related features
~~~

This is not an official rate card. Azure SQL has specific billing rules, minimum compute, memory billing, and SKU limits. **Never multiply max vCores by 24 hours and call that the serverless bill**, nor assume 0 vCore billing for every hour the app sends no queries.

### Qualitative Examples

| Workload | Can Serverless Save Cost? | What to Verify |
|---|---|---|
| Dev/test running only during office hours | Potentially, if auto-paused and resume is acceptable | Health checks, connection pools, auto-pause eligibility |
| Public API receiving requests every few seconds all day | Likely little advantage | Active compute billing, latency, and peaks |
| Batch reports spiking twice daily | Potentially suitable | Batch duration, max compute, and cold start |
| Payments requiring ultra-fast response at all times | Usually consider provisioned | p99 SLO, connectivity, and availability |
| Continuous multi-hour data analytics | Must benchmark, not guaranteed cheaper | Long active compute and tier limits |

For production data, compare **projected monthly costs** in the Azure Pricing Calculator and inspect actual billing after testing; never pick serverless solely for the name "serverless."

## 13. What Is an Elastic Pool?

An **Azure SQL Database elastic pool** is a model allowing multiple **separate databases** to share one pool compute budget. Each database maintains independent schemas, permissions, data, and connections per SQL Database design; compute is shared based on aggregate load and pool/per-database limits.

~~~text
           Multi-tenant SaaS application
                        |
            +-----------+-----------+
            |           |           |
            v           v           v
         tenant-A     tenant-B     tenant-C
            \           |           /
             \          |          /
              +-------------------+
              | Azure SQL         |
              | Elastic Pool      |
              | Shared resources  |
              +-------------------+
~~~

### Why Elastic Pools Fit SaaS

A company has 50 customers, each with its own database. If buying enough resources per database to handle **concurrent peaks** despite only spiking a few minutes daily, total idle compute is huge. If peaks are staggered, a pool shares resources more efficiently.

### Important Caveats

- Pools have **aggregate compute**, storage, and other quotas.
- Each database has **minimum/maximum resource settings** per tier/pool.
- Simultaneous peaks across many databases can saturate pool resources.
- A pool does not merge multiple databases into one shared database.
- A pool does not fix slow queries or poor tenant partitioning.
- Service tier conditions, database count limits, storage, and billing must be checked per SKU.

## 14. Elastic Pool: Shared Resource Model

Suppose a vCore pool has a configured compute budget of **8 vCores** containing three databases:

~~~text
Pool capacity: 8 vCores (illustrative)

09:00:
  tenant-A uses heavy CPU
  tenant-B has low activity
  tenant-C has low activity
  -> pool can serve A's peak well

13:00:
  tenant-A uses heavy CPU
  tenant-B also peaks
  tenant-C also peaks
  -> total demand can exceed 8 vCores
~~~

This illustrates an aggregate budget, **not simple arithmetic to predict the real scheduler**. Pools also enforce I/O/log/memory limits, per-DB limits, and tier-specific resource mechanics.

### Per-Database Limits

If one tenant can consume nearly the entire pool, other tenants suffer. You must manage **per-database minimum and maximum resources** matching the pool's service objective:

- **Minimum** guarantees baseline resources per supported configuration.
- **Maximum** caps how much compute one database can consume.
- Sum of minimum guarantees and pool capacity must satisfy configuration constraints.

Do not assume "max per DB = 8, pool = 8" means all 20 DBs get 8 vCores simultaneously; each DB only has a **potential ceiling**, not dedicated compute guaranteed at all times.

### Noisy Neighbor

A database running large table-scan queries can consume CPU, I/O, or log throughput, slowing other tenants via the shared mechanism. Monitor all of:

1. **Pool resource utilization**.
2. **Per-database utilization**.
3. **Query/resource waits**.
4. **Business SLOs** for each tenant.

If a tenant is consistently heavy, consider moving that database to a single database or a separate pool with tailored limits.

## 15. When Is an Elastic Pool Cost-Effective?

Suppose there are 30 databases:

- Most have very low traffic.
- Some experience brief spikes at opening hours.
- Peaks rarely overlap.
- Each database must isolate data and permissions per customer.

A pool can cut idle compute by avoiding dedicated peak ceilings for every database.

Conversely, if **all tenants peak simultaneously** from 10:00–12:00 daily, total required compute remains large. An undersized pool causes slowdowns and retries, while an oversized pool wastes money on idle capacity.

### How to Compare

~~~text
Option A cost:
  Sum of compute/storage for N single databases

Option B cost:
  Compute/storage and add-ons of an elastic pool

Additional evaluation:
  p95/p99 latency
  Peak concurrency
  Data I/O and log I/O
  Query completion rate
  Administrative overhead and noisy-neighbor risk
~~~

Do not just sum list prices; reserved capacity, license benefits, or differing storage/backup tiers alter the financial result.

## 16. DTU Elastic Pool vs. vCore Elastic Pool

| Criterion | DTU Elastic Pool | vCore Elastic Pool |
|---|---|---|
| Compute unit | **eDTU** | **vCores** |
| Resource view | Bundled CPU/memory/I/O package | vCores, hardware/tier, and resource limits |
| Per-DB limits | By min/max eDTU config | By pool compute/resource config |
| Tiers | DTU pool tiers per availability | Supported vCore tiers like General Purpose, Business Critical, and other options over time |
| Cost optimization | Share eDTUs across DBs | Share vCores and select suitable tier/hardware/benefits |
| When to use | Organizations already using DTU or wanting bundled tiers | Need more transparent compute control |

**eDTUs cannot be converted directly to vCores using a fixed ratio across all queries.** Conversion requires measuring real workloads, using appropriate Azure estimation guidance/tools, and testing.

### Pool vs. Serverless Billing Models

Elastic pools typically purchase a **pool compute budget**, whereas serverless scales a single database's compute and can auto-pause conditionally. A pool with 20 idle databases does not automatically auto-pause and stop billing like a serverless single database.

### Storage Considerations

Check **per-DB max data size** limits, **total pool storage** limits, and tier storage costs. A pool with ample CPU containing a few rapidly growing databases can still hit storage caps.

## 17. Choosing Single Database or Pool?

| Question | Favors Single Database | Favors Elastic Pool |
|---|---|---|
| How many databases? | One or a few distinct DBs with notable load | Many small, similar DBs |
| Is load steady? | Individual load is steady/predictable | Per-DB loads fluctuate and are staggered |
| Strong performance isolation needed? | Yes | Must evaluate noisy-neighbor and per-DB max |
| Wide variance among tenants? | Large tenants should be separated | Homogeneous small tenants group well |
| Is auto-pause required? | Serverless single DB may fit | Pools do not replace auto-pause |
| Idle compute cost? | Can be high if each DB is provisioned | Saves money if aggregate utilization is low |
| Tenant lifecycle management? | Not necessarily complex | Requires tracking pool membership and per-DB limits |

### A Hybrid Strategy

Production SaaS rarely needs to put **all** databases into one pool:

- Small customers: share one elastic pool.
- Medium customers: group by workload or SLO into multiple pools.
- Large customers/strict performance needs: dedicated vCore provisioned single databases.
- Dev/test or intermittent jobs: serverless single database if conditions fit.

Every tenant still requires independent data security and permissions regardless of how compute is shared.

## 18. DTU and vCore: No Fixed Conversion Factor

Many ask: "How many vCores equal 100 DTUs?" A trustworthy answer depends on **workload characteristics**.

For example:

~~~text
Database X (DTU)
  CPU percent: 90%
  Data IO percent: 20%
  Log IO percent: 15%

Database Y (DTU)
  CPU percent: 25%
  Data IO percent: 95%
  Log IO percent: 85%

Both DBs can be near 100% DTU,
but X is CPU-bound while Y is I/O-bound.
~~~

Using a simple DTU-to-vCore formula without checking I/O limits can leave Database Y throttled after migration even if vCores look sufficient.

### Migration Assessment Process

1. Collect **at least one representative load cycle**, including peak hours, batches, weekends/month-end as needed.
2. Record CPU, data I/O, log I/O, workers, sessions, and latency metrics.
3. Identify heavy queries, wait types, missing/unused indexes, long transactions, and blocking.
4. Define SLA/RPO/RTO and mandatory features to retain.
5. Select candidate vCore SKU/tier/hardware per Azure guidance.
6. Load test in a production-like environment or controlled canary.
7. Compare performance and cost; prepare to revert to an appropriate service objective if needed.

**Never switch tiers just to fix an unindexed query** without tuning analysis first.

## 19. Which Metrics Measure a Workload?

| Metric | What It Shows | If High, What to Investigate? |
|---|---|---|
| **DTU percentage** | Usage vs. DTU budget | Which of CPU/data I/O/log I/O is hitting the limit |
| **CPU percentage** | CPU usage vs. limit | Query CPU, plans, concurrency, missing indexes |
| **Data IO percentage** | Data read/write pressure vs. limit | Table scans, index design, read patterns |
| **Log IO percentage** | Transaction log write pressure | Batch writes, transaction patterns, log bottleneck |
| **Memory usage** | Memory pressure per supported limit/metric | Sorts/hashes, plan cache, workload memory |
| **Workers percentage** | Concurrent request processing capacity | Excess concurrency, long-running queries |
| **Sessions percentage** | Connections/sessions near limit | Connection pooling/leaks, retry storms |
| **Storage used / max size** | Risk of running out of space | Growth, retention, indexing/archival |
| **Deadlocks / blocking / waits** | Contention issues | Isolation, lock duration, indexing, transactions |
| **Query duration p95/p99** | User-visible latency | Query Store, execution plans, backend/network |

**One high metric is not automatically the root cause.** For example, high CPU may stem from continuously retrying a deadlocked query; simply adding compute won't fix deadlocks.

### Separate Three Observation Levels

1. **Database:** which resource limits is the database hitting?
2. **Pool:** total vCore/eDTU, workers/IO, and which databases peak together?
3. **Application:** request rate, latency, timeouts, connection pools, 429/5xx, and business SLOs?

Looking only at pool totals can hide a single tenant hitting its per-database max even when the pool still has unused compute.

## 20. T-SQL: Inspecting Resource Usage from the Database

The commands below are **read-only** and require appropriate permissions. Run them on the target **Azure SQL Database** over an authorized connection, mindful of monitoring and logging policies in production.

### Recent Resource Statistics

~~~sql
SELECT TOP (100)
    end_time,
    avg_cpu_percent,
    avg_data_io_percent,
    avg_log_write_percent,
    avg_memory_usage_percent
FROM sys.dm_db_resource_stats
ORDER BY end_time DESC;
~~~

**`sys.dm_db_resource_stats`** provides time-sampled stats for the current database; retention window and available columns depend on Azure SQL Database. For multi-day/week trends, use Azure Monitor, Query Store, or a telemetry sink with appropriate retention.

### Checking Current Resource Levels and Config

~~~sql
SELECT
    name,
    state_desc,
    compatibility_level
FROM sys.databases
ORDER BY name;
~~~

This query is **not** sufficient to determine DTU/vCore counts or serverless settings. Combine with **Azure resource properties**/service objectives and metrics.

### Inspecting Expensive Queries

Azure SQL Database's **Query Store** (when enabled and configured) supports execution history and regression analysis. For slow workloads, inspect Query Store in the Azure portal/SSMS/Azure Data Studio or query appropriate DMVs/Query Store views.

Do not mass-create indexes based on a single snapshot of missing index suggestions. New indexes increase storage usage and write overhead.

## 21. Measuring Peak, Median, and Load Cycles

One hour at 90% CPU does not represent an entire month. When selecting serverless or a pool, measure load across multiple resolutions:

~~~text
By minute:
  detects bursts and timeouts

By hour:
  shows daily peak hours

By day/week:
  reveals business cycles

By month/quarter:
  reveals period-end batches, campaigns, major events
~~~

### Sample Baseline Table

| Metric | Daytime | Nighttime | Month-End Peak |
|---|---:|---:|---:|
| Relative CPU | 35% | 2% | 85% |
| Relative Data I/O | 20% | 1% | 70% |
| Relative Log I/O | 25% | 1% | 90% |
| Requests/s | 80 | 0–2 | 500 |
| Latency p95 | 70 ms | 50 ms | 900 ms |

**Numbers are hypothetical examples for learning analysis**, not official benchmarks or predictions for any Azure SKU.

From this table:

- Serverless may be worth testing if the database stays **idle long enough** to reduce compute and nothing blocks pausing.
- Provisioned is worth considering if p95 latency must remain stable at all times.
- If 30 tenants have staggered peaks, an elastic pool may pay off; if all peak together at month-end, increase total pool capacity or split groups.

## 22. Billing Models to Distinguish

| Option | Compute Billed By | Storage | Notes |
|---|---|---|---|
| DTU single | Selected service objective/DTUs | Per tier limits/rate card | Bundled resource package |
| vCore provisioned single | Provisioned vCores per SKU/tier | Per vCore tier profile/rate card | Eligible for reserved capacity/benefits if supported |
| vCore serverless single | Active compute usage and minimums per billing model | Storage/backup fees still apply | Auto-pause if supported and actually triggered |
| DTU pool | Pool eDTUs | Per pool and data sizes | Must account for all databases in pool |
| vCore pool | Pool vCores | Per pool config/data size | Avoid summing full individual peaks when peaks are staggered |

### Do Not Confuse Compute and Storage Pricing

vCore provisioned usually separates compute and storage more transparently, yet pricing still depends on **region, tier, hardware, redundancy, backup retention, and discount programs**. DTU has its own pricing/limit structure. A financial comparison model should show:

~~~text
Approximate monthly TCO:
  Database compute
  + Data storage
  + Extra backup/PITR/LTR costs if applicable
  + Networking/Private Endpoint and related services
  + Monitoring/Log Analytics
  + Operations and migration effort
~~~

Do not hard-code fixed USD unit prices into curriculum materials since pricing changes. Use the Azure Pricing Calculator and Azure Cost Management for your active region and offer.

## 23. Azure Hybrid Benefit and Reserved Capacity

One reason organizations choose vCore provisioned is the ability to optimize licensing and costs under eligible Azure programs.

### Azure Hybrid Benefit

For customers holding **eligible SQL Server licenses**, Azure Hybrid Benefit can reduce the licensing portion of costs on supported SKUs/services. Eligibility depends on license type, Software Assurance/subscription, and Microsoft terms.

Do not apply the benefit merely because the company "bought SQL Server before"; verify **legal/license compliance eligibility and supported SKUs** with the responsible team.

### Reserved Capacity

Supported capacity reservations can benefit steady, long-running workloads. However, if a database is frequently idle and auto-pauses, a fixed commitment may not be the most economical choice.

### Holistic Evaluation

Compare:

- Pay-as-you-go pricing.
- Pricing with license benefits if eligible.
- Reserved capacity pricing if conditions are met.
- Likelihood of needing to change workloads/tiers mid-term.
- Risk of over-committing relative to demand.

Never base an entire architectural decision solely on an assumed discount percentage.

## 24. Serverless and Connection Pooling

A practical issue with serverless is **databases failing to pause** because applications keep opening connections or running health checks.

~~~text
Application pool
    |
    +--> connection 1 stays active
    +--> connection 2 stays active
    +--> periodic SELECT 1 health check
    |
    v
Azure SQL serverless database
    |
    +--> May fail to meet idle condition for auto-pause
~~~

### Factors to Review

1. True database idle level, not just HTTP request rates.
2. Connection pools in App Service, Functions, AKS, or VMs.
3. Background jobs, maintenance, scheduled queries, and monitoring.
4. Database features that can prevent pausing.
5. Retry/backoff logic upon resume.

Do not recklessly "disable all health checks" solely to save compute. Health checks serve operational purposes; design an approach balancing SLOs and auto-pause conditions.

### Pooling and Client Timeouts

If 100 application instances wake a database simultaneously, initial requests may time out and retry together, creating fresh pressure. Ensure:

- Bounded max pool sizes and retry counts.
- Backoff/jitter.
- Idempotency for write operations.
- Monitoring of connection failures and connection-open times.
- Considering provisioned if the workload requires continuous availability.

## 25. Serverless and Conditional Features

Certain features and configurations can affect choosing serverless or auto-pause behavior:

- Active geo-replication/failover groups per support matrix.
- Long-term retention, data sync, or related management features per config.
- Private endpoints/firewalls and network/monitoring paths; **not every network feature blocks auto-pause**, but they must be verified.
- Hyperscale serverless with its distinct auto-pause behavior.
- HA/zone redundancy or backup restore options depending on service tier.
- Required background activities keeping the database non-idle.

**Do not conclude every listed feature is universally forbidden on serverless.** This is a compatibility checklist; cross-check feature docs, SKUs, and database state before switching.

## 26. Elastic Pool and Multi-Tenant SaaS Concerns

In the **database-per-tenant** model, pools lower compute costs, yet the application still must manage:

1. **Tenant routing:** connecting to the right database for the authenticated tenant.
2. **Schema migrations:** applying migrations across many databases with monitoring.
3. **Backup/recovery:** restoring one database independently without harming other tenants.
4. **Per-tenant SLOs:** measuring latency and usage per tenant.
5. **Noisy neighbors:** isolating or moving large tenants when needed.
6. **Security:** SQL users/Entra ID, firewalls, private endpoints, and secret rotation.
7. **Lifecycle:** creating, upgrading, moving pools, or deleting databases via approved workflows.

~~~text
Authenticated API request
        |
        v
Tenant registry / authorization
        |
        v
Database mapping
        |
        +--> Tenant A -> Pool 1, database A
        +--> Tenant B -> Pool 1, database B
        +--> Tenant C -> Pool 2, database C
        +--> Tenant D -> Single database (dedicated)
~~~

**An elastic pool does not enforce authorization between tenants.** Separate databases establish data boundaries, yet the API must authenticate tenants and never allow users to pick another database via unvalidated headers or query parameters.

## 27. Security and Networking Across All Four Models

Whether a database uses DTU, vCore, serverless, or a pool, security principles remain consistent:

### Identity and Permissions

- Prefer **Microsoft Entra authentication** or managed identities in supported apps/services.
- Grant least-privilege database permissions per role.
- Avoid using SQL admin for all application connections.
- Never embed passwords/connection strings in source code, images, or docs.
- Use Key Vault/secret management with rotation workflows.

### Network Connectivity

- Configure firewalls, private endpoints, and private DNS when required.
- Verify network paths from App Service, AKS, Functions/VMs to the SQL endpoint.
- Use TLS and configure client drivers properly.
- Never open public network access to the entire Internet just to fix a connection error.
- Reconcile NSGs/UDRs/Azure Firewall and egress policies inside the VNet.

### Data Controls

- Configure backups/PITR and retention per requirements.
- Enforce encryption at rest/in transit per service capabilities and policy.
- Enable auditing and appropriate query logging without leaking PII/secrets.
- Apply data masking/row-level security where needed without replacing app authorization.

**Choosing an elastic pool does not change your responsibility for isolating data security across tenants.**

## 28. Availability, Backups, and DR

When choosing a service tier and compute model, evaluate:

- Current SKU SLA and availability guarantees.
- Redundancy/failover during infrastructure failures.
- Zone redundancy and multi-region DR if permitted by the service/tier.
- Automated backups, PITR, and long-term retention per supported configuration.
- Restore times and backup storage/geo-restore limitations.
- Impact when scaling/switching tiers or auto-resuming.

### Do Not Confuse Auto-Pause with Failover

Serverless **auto-pause** intentionally suspends compute during idle periods to save resources in supported configs. **Failover/HA** reacts to infrastructure faults. Both can briefly interrupt connections, yet their causes and handling differ.

### Do Not Confuse Elastic Pools with Replication

Multiple databases in an elastic pool share a compute budget. That **does not replicate data to another region** and does not automatically provide DR. Backups/replication must be designed per database and tier.

### Verified Restore Testing

A backup reporting success does not prove RPO/RTO compliance. Run a restore drill in an isolated environment, verify schemas, record counts, transaction integrity, and end-to-end duration before declaring the data strategy safe.

## 29. Azure Portal: Option Evaluation Workflow

The steps below focus on **observation and planning**. Actually modifying database configurations can incur charges or disrupt connections; obtain approval and test on lab resources first.

### Step 1: Identify the Database

1. Select the correct subscription and resource group.
2. Open **SQL databases** and select the database to evaluate.
3. Inspect logical server, region, status, service tier, and compute model.
4. Check whether the database belongs to an elastic pool or is a single database.
5. Identify the owner, consuming applications, and SLA.

### Step 2: Inspect Compute + Storage

In the compute/storage configuration blade per current UI:

- If using DTU: inspect tier and service objective.
- If using vCore: inspect tier, hardware, and vCore count.
- If using serverless: inspect min/max compute and auto-pause where supported.
- If using an elastic pool: inspect pool budget, storage, and per-DB limits.

### Step 3: Open Metrics and Query Performance

Pull charts spanning enough time to capture peaks:

- CPU, data I/O, log I/O, and DTU usage if using DTU.
- Storage, workers/sessions, and connection failures.
- Query Store/tuning findings and app p95 latency.
- For pools: view pool totals alongside individual databases.

### Step 4: Model Alternatives

Compare:

1. Current single DTU.
2. Single vCore provisioned.
3. Single serverless if compatible and clearly idle.
4. Elastic pool for groups of databases with staggered peaks.

Benchmark before/after in a test environment; never change production solely because a calculator shows a lower price.

## 30. Azure CLI: Read-Only Configuration Inspection

The commands below only **read Azure resources**—they do not create, scale, or delete databases. Fill in your authorized subscription and environment details.

### Identify Subscription

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az account show \
  --query "{subscription:id,name:name,tenantId:tenantId}" \
  --output json
~~~

### Inspect Logical Server

~~~bash
az sql server show \
  --resource-group "rg-sql-lab" \
  --name "sql-demo-server" \
  --query "{name:name,location:location,version:version}" \
  --output json
~~~

### Inspect Single Database

~~~bash
az sql db show \
  --resource-group "rg-sql-lab" \
  --server "sql-demo-server" \
  --name "orders-db" \
  --query "{name:name,status:status,sku:sku,computeModel:computeModel,minCapacity:minCapacity,autoPauseDelay:autoPauseDelay,elasticPoolName:elasticPoolName,maxSizeBytes:maxSizeBytes}" \
  --output json
~~~

Some fields may be null/absent depending on compute model and Azure API. For instance, `autoPauseDelay` does not apply uniformly to every DTU/vCore SKU. Inspect full JSON when confirming actual structure rather than altering configurations to "make a field appear."

### List Databases

~~~bash
az sql db list \
  --resource-group "rg-sql-lab" \
  --server "sql-demo-server" \
  --query "[].{name:name,sku:sku,status:status,elasticPoolName:elasticPoolName}" \
  --output table
~~~

### Inspect Elastic Pools

~~~bash
az sql elastic-pool list \
  --resource-group "rg-sql-lab" \
  --server "sql-demo-server" \
  --output json

az sql elastic-pool show \
  --resource-group "rg-sql-lab" \
  --server "sql-demo-server" \
  --name "tenant-pool" \
  --output json
~~~

Compare SKU, capacity, `perDatabaseSettings`, and storage limits in the actual output. **Reading configs alone does not prove a pool has enough capacity**; you need Azure Monitor and per-tenant latency metrics.

## 31. T-SQL: Observing Slowness and Resource Contention

A database with high p95 latency can result from:

- Queries scanning excessive data.
- Poorly suited indexes.
- Blocking/deadlocks.
- Long-running transactions.
- CPU throttling.
- Log write throttling.
- Connection/session exhaustion.

Diagnostic flow:

~~~text
Client p95 latency rises
         |
         v
Are database CPU/IO/log hitting limits?
      /          \
    Yes           No
     |             |
     v             v
Check resource   Check blocking, waits,
limitations      networking, query plans,
& heavy queries  app connection pool
     |
     v
Test tuning / sizing in lab
~~~

### Do Not Rely on DMVs as Sole Evidence

DMVs have limited retention and sampled data. For multi-day workloads, use **Azure Monitor**/Query Store and retained logs. If workloads have brief spikes, hourly averages can mask the issue.

### Evaluate Query Tuning Before Upscaling

For example, a query filtering by `customerId` without a matching index may scan millions of rows. Adding the right index drastically cuts data I/O and CPU, potentially costing far less than adding vCores. However, new indexes also raise write overhead and storage; measure before/after on realistic data.

## 32. Migration: Switching from DTU to vCore

**Changing a service objective** can be a supported operation in Azure SQL Database, but you must account for limits, scaling duration, connection impact, and reversibility.

### Before Switching

1. Snapshot the current SKU/service objective, max size, and features.
2. Save metric charts across a representative cycle.
3. Check client software/drivers, connection retries, and transaction semantics.
4. Cross-check unsupported/incompatible features on the target tier.
5. Calculate storage/backup/replication/quota and regional pricing.
6. Assign approvers, change window, and rollback plan.

### During the Switch

1. Execute in a lab or staging environment first.
2. Monitor operation status/provisioning.
3. Watch for brief connection drops and verify client retries handle them.
4. Avoid running full-load benchmarks concurrently with major tier changes unless planned.

### After the Switch

1. Confirm the new service objective is active.
2. Test login, reads/writes, and business transactions.
3. Compare CPU/IO/log/waits and p95/p99 latency under equivalent load.
4. Verify backups/PITR/DR, alerts, and logs.
5. Monitor billing/costs over a sufficient window.

**Rollback is not always just picking the previous plan.** Certain tier/hardware/size transitions carry constraints, delays, or revert restrictions. Know the rules before executing the change.

## 33. Migration: Moving Databases Into or Out of an Elastic Pool

### Key Considerations

- Pool and databases must meet regional/logical server/tier requirements and service constraints.
- Data is not automatically lost when moving pools, though performance/cost and service objectives may shift.
- A large database can consume excessive resources and degrade the pool.
- A pool near storage or compute capacity may reject additional databases.
- Feature compatibility specific to single databases vs. elastic pools must be verified.

### Process

1. List databases and concurrent peaks.
2. Determine pool SKU, total compute, and per-DB min/max.
3. Check storage sizes and unusually large databases.
4. Move **a small group** into a lab/canary pool.
5. Monitor pool metrics, per-DB latency, and connection failures.
6. Add more DBs gradually if real headroom remains.
7. Set alerts for noisy neighbors and capacity.
8. Keep a workflow ready to extract heavy tenants to a single database or separate pool.

Never pack 100 tenants into one pool simply because average per-DB usage is idle; measure **simultaneous** load and potential pool-wide peak events.

## 34. Using Serverless for Development and Testing Environments

A sensible use case is a dev/test environment used only during work hours:

~~~text
Developers run tests: 09:00–18:00
Nighttime: minimal activity
Database: serverless single DB, auto-pause configured if supported
~~~

Advantages:

- Opportunity to lower compute bills during unused hours.
- Avoids paying 24/7 for large provisioned vCores on a test DB.

Things to check:

- Do midnight CI pipelines wake the database?
- Do tools/health checks keep connections continuously open?
- Do integration tests time out during resume?
- Does the database hold backups/retention or test data that must be preserved?
- Are required features compatible with serverless and auto-pause?

Never enable serverless in production merely because it succeeded in dev/test; traffic, latency requirements, and features differ.

## 35. Common Errors and Diagnostic Approach

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| DTU near 100% and API slow | CPU/data I/O/log I/O hitting limits | Measure all three metric groups and query plans |
| Increased DTUs without speedup | Blocking, deadlocks, networking, or unoptimized queries | Query Store, waits, application traces |
| Switched to vCore with same "number" but slower | No 1:1 DTU→vCore ratio, different hardware/I/O | Compare resource limits and benchmark |
| Serverless fails to auto-pause | Unsupported feature, active sessions/background tasks, or delay config | Check SKU, `autoPauseDelay`, connections, and activity |
| First request after idle is slow | Cold start/auto-resume | Inspect database state and connection time; adjust SLO |
| High serverless bill despite low traffic | Database not pausing or active compute/background workers | Review usage hours, metrics, config, and billing |
| Serverless hits max vCores | Demand exceeds ceiling or heavy queries | Measure CPU/waits, tune, and consider raising max |
| Pool has free vCores but one DB is slow | Per-DB max/IO cap, query locks, or memory | Inspect per-database metrics and pool settings |
| Multiple tenants slow at same hour | Noisy neighbor or concurrent peaks exceeding pool | Monitor pool totals and individual databases |
| Unexpected pool storage growth | A few tenants growing data/indexes | Check max size/used storage and retention |
| Connection timeouts after tier change | Scale/reconfiguration, networking, or weak client retry | Correlate timestamps, Azure Activity Log, client driver |
| Azure SQL returns 401/18456 | Authentication/RBAC/SQL login | Check Entra ID, SQL permissions, tokens |
| App cannot reach Private Endpoint | DNS/NSG/UDR/firewall, not DTU/vCore | Test DNS and TCP/TLS path |
| Low estimate but high bill | Storage/backups/networking/monitoring or compute billing differed from assumptions | Cost Analysis by resource/SKU/tier |
| Incorrect pool membership displayed | Viewing wrong logical server/resource group or pending change | Verify Azure resource ID, subscription, and CLI show |

### Six-Step Diagnostic Process

1. **Scope:** correct subscription, logical server, database, and pool?
2. **Model:** which DTU/vCore, provisioned/serverless, tier, and SKU?
3. **Resources:** are CPU/data I/O/log I/O, memory, workers, or storage hitting ceilings?
4. **Query/application:** issues in Query Store, waits, blocking, or connection pools?
5. **Infrastructure:** auth, DNS, firewall/private endpoint, or scaling/reconfiguration?
6. **Costs/SLO:** what is the solution costing, and are latency/throughput targets met?

Never delete a database or recreate a pool simply because timeouts occur. First triage the error and protect data and recoverability.

## 36. Case Study: 24 SaaS Databases with Uneven Load

A SaaS provider manages 24 customers, each with an Azure SQL Database. Observed profile:

- **18 small tenants:** average ~0.2 vCore equivalent each, peaking up to 1 vCore, usually at different hours.
- **4 medium tenants:** average ~0.7 vCore, peaking at 2 vCores.
- **2 large tenants:** steadily use 2–4 vCores with sustained high peaks.
- One internal admin DB runs reporting only at end of day.
- Production API requires p95 query latency under 150 ms under normal load.
- Financial data requires backups/PITR and tested recoverability.

### Tasks

1. Explain why "one provisioned database sized to peak per tenant" is wasteful.
2. Decide which tenant groups fit an elastic pool vs. single databases.
3. Explain why averaging `18 × 0.2 vCore` is **insufficient** to size pool capacity.
4. Propose a method to measure concurrency/peaks across tenants.
5. Design suitable per-DB maximums to limit noisy neighbors.
6. Evaluate whether the end-of-day reporting DB suits serverless.
7. Compare a DTU pool vs. vCore pool across metrics and cost.
8. State differences among General Purpose, Business Critical, and Hyperscale.
9. Propose a canary migration, rollback, and observability plan.
10. Identify metrics to alert on at pool and database levels.
11. Outline tenant access permissions, private networking, and backup strategy.
12. Build a TCO estimate table covering compute, storage, backups, monitoring, and operations.

### Solution Hints

- **18 small tenants:** good candidates to test in one or more elastic pools due to staggered peaks.
- **4 medium tenants:** evaluate a separate pool or joining small groups if concurrency metrics allow.
- **2 large tenants:** place on provisioned single databases for dedicated compute budgets and clear SLOs.
- **Internal reporting DB:** test serverless single DB if idle periods are long, features are compatible, and resume latency is acceptable.

Note that **0.2/0.7 vCore** in the scenario are hypothetical measured/modeled values, not fractional vCores reported for every Azure SKU. Final decisions must rely on **actual SKU capacities**, metrics, and load tests.

## 37. Preliminary Pool Capacity Sizing Exercise

Suppose there are 12 databases:

~~~text
Each DB:
  projected peak demand = 2 vCores

However, concurrent peaks:
  typically 2 DBs peak together
  occasionally 4 DBs peak together

Conceptual peak compute demand:
  2 x 2 = 4 vCores (typical)
  4 x 2 = 8 vCores (rare event)
~~~

An 8-vCore pool **can be a test candidate**, but is insufficient proof for production because:

- CPU is not the only resource.
- I/O and log throughput can saturate first.
- Other databases still consume baseline load.
- Per-DB max and tier limits have an impact.
- Peaks can overlap more than expected during campaigns or batches.
- Headroom is needed for spikes and incidents.

Use this arithmetic solely to shortlist **configurations for benchmarking**, never as an SLO guarantee or standard pricing estimate.

## 38. Pre-Production Model Selection Checklist

| Area | Acceptance Question |
|---|---|
| Service type | Definitely Azure SQL Database rather than Managed Instance/VM/PostgreSQL? |
| Workload | Multi-day baseline, concurrent peaks, and business SLO documented? |
| DTU | Inspected CPU/data I/O/log I/O rather than only DTU percentage? |
| vCore | Tier, hardware, vCores, resource limits, and storage appropriate? |
| Provisioned | Baseline load justifies fixed compute? |
| Serverless | SKU compatible, min/max sensible, and auto-pause actually occurs? |
| Resume | Client retries/backoff, timeouts, and SLO tolerate cold starts? |
| Elastic pool | Multiple DBs with staggered load and concurrency metrics measured? |
| Per-DB limits | Prevented one tenant from monopolizing pool compute/IO? |
| Storage | Per-DB/pool max size, data growth, and backup retention appropriate? |
| Query tuning | Used Query Store/waits/index analysis before scaling up? |
| HA/DR | Backups/PITR, zone/geo redundancy, and restore drills adequate? |
| Security | Entra ID/managed identity, RBAC, TLS, private endpoint as needed? |
| Cost | Compute + storage + backups + monitoring + networking estimated? |
| Migration | Canary, change window, rollback, and validation prepared? |
| Observability | Alerts on CPU/IO/log/workers/connections/storage and p95 latency? |
| Documentation | Database owner, service objective, and selection rationale recorded? |

## 39. Self-Check Questions

1. What resource types does DTU represent?
2. Why does 100 DTU not equal 100 transactions/second?
3. How does eDTU differ from single-database DTU?
4. How does the vCore model expose resources differently?
5. Is a vCore always a dedicated physical CPU core?
6. Which model do Basic/Standard/Premium belong to?
7. How do General Purpose, Business Critical, and Hyperscale differ in focus?
8. Does provisioned compute automatically scale to 0 when a database is idle?
9. Does serverless mean zero storage cost?
10. Does serverless automatically scale beyond configured max vCores?
11. Is auto-pause always available for every Hyperscale serverless database?
12. Why can health checks or connection pools prevent auto-pause?
13. How does auto-resume latency affect APIs?
14. Why must retries after timeouts be designed as idempotent?
15. Do elastic pools benefit most when DB peaks are simultaneous or staggered?
16. Why can a pool suffer from noisy neighbors?
17. What problem do per-database maximums in a pool solve?
18. Why can't you multiply each DB's max vCores and claim the pool always provides that total compute?
19. Can eDTUs be converted to vCores using a fixed ratio?
20. When DTU reaches 100%, which metrics should be checked first?
21. Will a database throttled on log I/O automatically improve by adding only CPU?
22. Why is Query Store important when sizing?
23. How do serverless single DBs and elastic pools differ in scaling models?
24. What eligibility conditions must be checked for reserved capacity and Azure Hybrid Benefit?
25. Why doesn't an elastic pool automatically geo-replicate data?
26. When switching a DB between tiers, which validation steps are mandatory?
27. Why is a small canary useful when consolidating databases into a pool?
28. How do you determine whether serverless is cheaper than provisioned for a specific workload?
29. Which cost items are easy to overlook when looking only at compute price?
30. With 20 tenants and uneven loads, how would you group their databases?

## References

- Microsoft Learn — *Azure SQL Database overview*: https://learn.microsoft.com/azure/azure-sql/database/sql-database-paas-overview
- Microsoft Learn — *DTU-based purchasing model*: https://learn.microsoft.com/azure/azure-sql/database/service-tiers-dtu
- Microsoft Learn — *vCore-based purchasing model*: https://learn.microsoft.com/azure/azure-sql/database/service-tiers-sql-database-vcore
- Microsoft Learn — *General Purpose service tier*: https://learn.microsoft.com/azure/azure-sql/database/service-tier-general-purpose
- Microsoft Learn — *Business Critical service tier*: https://learn.microsoft.com/azure/azure-sql/database/service-tier-business-critical
- Microsoft Learn — *Hyperscale service tier*: https://learn.microsoft.com/azure/azure-sql/database/service-tier-hyperscale
- Microsoft Learn — *Serverless compute tier for Azure SQL Database*: https://learn.microsoft.com/azure/azure-sql/database/serverless-tier-overview
- Microsoft Learn — *Elastic pools in Azure SQL Database*: https://learn.microsoft.com/azure/azure-sql/database/elastic-pool-overview
- Microsoft Learn — *Resource limits for single databases*: https://learn.microsoft.com/azure/azure-sql/database/resource-limits-vcore-single-databases
- Microsoft Learn — *Resource limits for elastic pools*: https://learn.microsoft.com/azure/azure-sql/database/resource-limits-vcore-elastic-pools
- Microsoft Learn — *Monitoring and performance tuning in Azure SQL Database*: https://learn.microsoft.com/azure/azure-sql/database/monitor-tune-overview
- Microsoft Learn — *sys.dm_db_resource_stats*: https://learn.microsoft.com/sql/relational-databases/system-dynamic-management-views/sys-dm-db-resource-stats-azure-sql-database
- Microsoft Learn — *Azure SQL Database pricing*: https://azure.microsoft.com/pricing/details/azure-sql-database/
- Microsoft Learn — *Azure Hybrid Benefit for Azure SQL*: https://learn.microsoft.com/azure/azure-sql/azure-hybrid-benefit