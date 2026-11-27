# Multi-Region Design and Choosing Active-Active or Active-Passive

## Lesson Objectives

In the **Microsoft Azure** ecosystem, an application can span multiple **regions** to keep serving during a regional outage, bring endpoints closer to users, and satisfy data residency requirements. However, provisioning resources in two regions does not automatically create a disaster recovery architecture: request paths, write authority, replication, access permissions, standby capacity, and region-switching procedures must all be designed together.

After this lesson, you will be able to:

- Distinguish **Availability Zones**, **regions**, **region pairs**, data redundancy, and **disaster recovery (DR)**.
- Establish **RTO**, **RPO**, and SLI/SLO targets and use them to drive architectural choices.
- Compare **active-active**, **active-passive** (hot/warm/cold standby), and the hybrid **multi-region read, single-region write** pattern.
- Design routing with **Azure Front Door** or **Azure Traffic Manager**, while coordinating application and data failover in the right order.
- Build verifiable runbooks, monitoring, drills, and failback plans.

This lesson belongs to the **Reliability and Disaster Recovery** chapter of the **CLOUD_PROVIDERS_AZURE** module, spanning subscriptions, resource groups, Entra ID, networking, and compute through storage, data, monitoring, security, and cost. Examples use Azure services; all time, capacity, and cost figures below are **design assumptions**, not Azure SLA guarantees.

## 1. Why Design Across Multiple Regions?

A region is a geographic area containing one or more Azure datacenters. In regions supporting **Availability Zones (AZs)**, zones create isolated fault domains within the same region, reducing the impact of a datacenter or local infrastructure failure. **Multi-region** spreads applications and/or data across at least two regions, addressing broader outage classes such as full-region disruptions or multi-geography serving needs.

| Concept | Primary protection scope | What you must not infer |
| --- | --- | --- |
| Multiple instances in one zone | Process, host, or instance failures | Does not protect against full zone/region outages. |
| Zone-redundant within one region | Single-zone failure, if supported by service and config | Does not equal cross-region redundancy. |
| Multi-region | Wide regional outage; can reduce cross-region latency | Only effective when traffic, app, data, and dependencies are all ready. |
| Geo-replication | Creates data copies elsewhere per service mechanism | Does not automatically allow dual-region writes or guarantee zero RPO. |
| Backup/restore | Restores deleted, encrypted, miswritten, or logically corrupted data | Does not automatically keep a live service up or switch traffic fast. |

**Region pairs** are region pairings defined by Azure for certain operational and recovery purposes. Not every service or feature requires using a region pair; choosing a pair of regions should be based on **service availability, data residency boundaries, latency, capacity, pricing, and replication model**. Region pairing also does not guarantee both regions can never experience simultaneous issues.

For instance, an API with two Azure App Service instances in two regions that both query a single database lacking cross-region recovery **does not have end-to-end DR**. Likewise, having a database replica without a failover mechanism and connection cutover still misses RTO targets.

### 1.1. RTO, RPO, and Operational Metrics

- **RTO (Recovery Time Objective):** the maximum acceptable time to restore service after a sufficiently severe outage. For example, a 30-minute RTO means failover procedures must be engineered and drilled to meet that threshold.
- **RPO (Recovery Point Objective):** the maximum age of successfully written data that may be lost upon recovery. A 5-minute RPO requires matching replication, lag monitoring, and failover procedures.
- **SLI:** a metric measuring real user experience, such as request success rate, p95/p99 latency, and transaction correctness.
- **SLO:** a target level for an SLI over a window, such as 99.95% successful requests over 30 days. This corresponds to a **21.6-minute error budget** if every minute carries equal weight; request-based measurement can yield different numbers.

RTO measures **recovery duration**; RPO measures **data loss**. Shifting traffic to a surviving region in one minute does not equal a one-minute RTO if the app still cannot write or serve consistent data. Asynchronous replication can lose transactions confirmed in the primary region that have not yet reached the secondary during a forced failover.

Before picking a model, split requirements by business flow: payment transactions may demand very low RPO and avoid dual-site writes; a product catalog page may tolerate several minutes of sync lag while needing global availability. A single system often uses **different models for different data classes**.

## 2. Three Operational Patterns

### 2.1. Active-Passive: One Primary Serving Region

In **active-passive**, region A handles primary traffic; region B maintains standby app and data resources at the chosen readiness tier. When needed, roles switch to B. Typically, the application has only **one valid writer** for transactional data at any moment.

| Standby tier | Standby region state | Advantages | Costs and trade-offs |
| --- | --- | --- | --- |
| **Hot** | Apps, networking, permissions, and capacity already running; data replicates continuously | Fast switchover once dependencies are verified | Pays for parallel running resources; still must promote the database. |
| **Warm** | Config and data ready; compute runs scaled down and scales out on demand | Balances cost and RTO | Needs time to scale, warm caches, and verify quotas. |
| **Cold** | Mainly templates, backups, configs, and rebuild procedures | Generally lower ongoing cost | Long RTO dependent on provisioning and restore times; requires thorough drills. |

**Best fit:** transactional systems constrained to a single write source, operations teams needing controlled procedures, or RTOs allowing time to promote and scale standby capacity. With warm/cold standby, never confuse **Front Door rerouting time** with the time until the system can actually serve.

### 2.2. Active-Active: Two or More Regions Serving Simultaneously

In **active-active**, multiple regions actively handle user traffic. Benefits can include lower geographic latency, utilizing capacity across both regions, and faster traffic shift when one region fails. When region A stops serving, region B must have **enough spare headroom** to absorb the shifted load.

The hardest part typically lies in **data and state**:

- **Active-active reads, single-writer writes:** both regions serve read requests, while writes route to a single writer. Easier to protect consistency, though the write path depends on the writer region.
- **Active-active multi-writer:** both regions write to the same logical data; requires platform support, conflict-resolution strategies, unique keys, idempotency, and explicit consistency policies.

For example, Azure Cosmos DB supports multi-region write configurations, yet the application must still account for consistency levels and conflict resolution. Never assume every Azure SQL database, Storage account, or queue can safely open two independent writers and reconcile automatically.

### 2.3. Architectural Decision Comparison

| Criterion | Active-passive | Active-active |
| --- | --- | --- |
| Normal traffic | Primarily in one region | Distributed across regions |
| Remote user latency | Can be higher | Can be lower via nearby processing |
| Recovery on single-region app failure | Shift to standby; warm/cold need startup | Shift to surviving region if capacity exists |
| Data writes | Usually single-writer, simpler to control | Multi-region single-writer or complex multi-writer |
| Operations | Requires promote, traffic switch, and failback runbooks | Requires load distribution, sync, conflict, and N-1 capacity control |
| Typical cost | Lower for warm/cold; hot standby still costly | Multiple full runtime environments, cross-region transfer, complex observability |
| Core risks | Slow data promotion, under-sized standby | Split-brain, data conflicts, shared-dependency failures |

A **hybrid model** is often the pragmatic choice: two regions active for frontends or content reads, while only one region writes transactional data. That is **active-active at the application tier**, and should not be described as multi-writer at the data tier.

## 3. Process for Choosing Active-Active or Active-Passive

Do not start with a product selection. Answer these in sequence:

1. **Which failures must be survived?** Single instance, AZ, full region, cross-region network partition, logical data corruption, or external provider outage?
2. **What are RTO/RPO per business flow?** Separate search, page views, ordering, payment, inventory updates, and event processing.
3. **Can transactions be lost or duplicated?** If not, design idempotency, confirmation semantics, old-writer fencing, and post-failover reconciliation.
4. **Which replication modes does the data service support?** Read replicas, geo-failover, multi-write, consistency, replication lag, and SKU/region limits.
5. **Are data locations restricted?** Identify data residency, data classes, encryption keys, private links, and internal compliance rules.
6. **Can the surviving region carry 100% of load?** Test against peak traffic, quotas, database connections, backend pools, caches, and scale-out speed.
7. **Who and what decide failover/failback?** Where is automation appropriate, where is approval required, and what checks validate re-enabling writes?

Quick starting guide:

| Business scenario | Starting option to evaluate | What must be proven |
| --- | --- | --- |
| Transactional business API with a single relational data source | Active-passive hot or warm with single writer | Promotion and reroute RTO; RPO under async replication |
| Read-heavy website with globally distributed users | Active-active frontend/reads, single-writer backend | Real latency, cache invalidation, and write path |
| Distributed data resolvable by key/account conflicts | Active-active multi-writer, if supported by platform | Merge rules, idempotency, consistency, conflict detection |
| Internal system tolerating multi-hour recovery | Active-passive warm/cold | Provisioning speed, backup restores, test procedures |

> Record the choice in an **Architecture Decision Record (ADR)**: load assumptions, RTO/RPO targets, write model, failover procedure, data constraints, and success criteria. Whenever an assumption changes, re-evaluate the architecture.

## 4. Reference Architectures on Azure

### 4.1. Active-Passive with Azure Front Door and Azure SQL

Consider an e-commerce API running on **Azure App Service** in two regions. **Azure Front Door Standard/Premium** terminates global HTTPS, probes origin health, and prioritizes region A. An **Azure SQL Database failover group** provides asynchronous geo-replication and a logical endpoint for read/write connections. Monitoring, secrets, configs, and permissions are prepared in both regions.

~~~mermaid
flowchart TD
    U[HTTPS users] --> F[Azure Front Door + WAF]
    F -->|Priority 1, normal| A[App Service region A]
    F -.->|Priority 2, when appropriate| B[App Service region B]
    A --> L[SQL failover group: read-write listener]
    B --> L
    L --> P[(SQL primary region A)]
    P -.->|Async replication| S[(SQL geo-secondary region B)]
    M[Azure Monitor and alerts] -.-> F
    M -.-> P
    M -.-> S
~~~

The dashed arrow from Front Door to B indicates **route priority**, not that B automatically becomes the database writer. If A loses both app and database, ensure the **failover group has switched the writer to B**, app B connects to the valid endpoint, and data plus core dependencies pass checks before receiving business traffic.

An example of origin group **configuration intent** (the YAML below is a logical model for discussion, **not a directly deployable manifest**):

~~~yaml
frontDoor:
  mode: priority-routing
  probe:
    protocol: HTTPS
    method: GET
    path: /health/traffic-ready
  origins:
    - name: api-region-a
      priority: 1
      enabled: true
    - name: api-region-b
      priority: 2
      enabled: true
database:
  writeEndpoint: <sql-failover-group-read-write-listener>
  writesAllowed: single-primary-only
~~~

In Azure Front Door, **priority** controls failover between priority groups of origins; **weight** distributes traffic across origins at the same priority (per supported configuration). App probes must reflect real serving capability, especially data read/write paths. Never advertise standby as healthy merely because the process is alive while all business operations fail.

### 4.2. Active-Active at the Application Tier

~~~mermaid
flowchart TD
    C[Global users] --> FD[Azure Front Door + WAF]
    FD -->|By latency, health, config| RA[API region A]
    FD -->|By latency, health, config| RB[API region B]
    RA --> DA[(Region A data and cache)]
    RB --> DB[(Region B data and cache)]
    DA <-->|Data service replication mechanism| DB
    RA --> Q[Write / consistency coordination path]
    RB --> Q
~~~

The diagram deliberately separates the **write / consistency coordination path** from the two data copies. That path may be a single writer or a platform-supported multi-writer model. Before choosing it, answer clearly: where can transactions write, what is read-after-write visibility delay, how are conflicts resolved, and what happens if the two regions lose connectivity to each other?

### 4.3. Choosing a Traffic Steering Service

| Service | How it works | When appropriate | Notes |
| --- | --- | --- | --- |
| **Azure Front Door Standard/Premium** | Global Layer 7 HTTP/HTTPS reverse proxy; origin groups, health probes, routes, WAF, TLS | Multi-region web/API needing edge proximity and automatic origin switching | Must verify health, rules, and backend readiness; does not promote databases. |
| **Azure Traffic Manager** | DNS-based routing via configured method and endpoint monitoring | Apps needing multi-region DNS policies or endpoints not behind a global HTTP proxy | Resolvers/clients cache DNS; switchover time exceeds detection time alone. |
| **Azure Application Gateway** | Regional Layer 7 load balancer with SKU-dependent WAF | Balancing and protecting traffic entering a region | Not a standalone global multi-region solution. |
| **Azure Load Balancer** | Layer 4 balancing per scope and SKU | TCP/UDP, internal, or regional services | Does not replace data strategy or global HTTP failover. |

Priority 1/2 or latency-based routing is a **policy**; actual outcomes depend on health probes, caching, timeouts, open sessions, and persistent connections. For dynamic APIs, inspect Front Door caching rules carefully so responses containing personal data are never cached by mistake.

## 5. Data Defines the Model's Boundaries

**Applications can be stateless, but business processes rarely are.** Inventory databases, blobs, queues, caches, keys, secrets, temp files, sessions, cron jobs, and third-party callbacks. Any layer with a copy only in region A becomes a single point of failure when A goes down.

| Azure component | Options to evaluate | Design questions |
| --- | --- | --- |
| **Azure SQL Database** | Failover groups/geo-replication per service tier and capability; single logical writer | Replica lag? Read-write listener? Which transactions may be lost on forced failover? |
| **Azure Cosmos DB** | Multi-region distribution; read/write region settings and consistency levels | Allow multi-write? How do conflict resolution, session consistency, and failover behave? |
| **Azure Storage** | ZRS for zones, GRS/GZRS or read-access variants for geo-redundancy | Are secondary reads appropriate? During account failover, what happens to unreplicated data? |
| **Azure Service Bus/Event Hubs** | Check exact geo-recovery/geo-replication capabilities for tier and service | Does the feature replicate **message/event payloads** or only configuration metadata? How is backlog handled? |
| **Azure Cache for Redis/caching** | Independent regional caches, warm-up, and invalidation | Can the cache be rebuilt? Never treat a cache as the primary data source. |
| **Azure Key Vault** | Permissions and secrets must be reachable on the backup region's runtime path | Do regional dependencies, private endpoints, managed identities, and secret lifecycles impede failover? |

### 5.1. Single-Writer and Preventing Split-Brain

**Split-brain** happens when both sides believe they hold write authority. For instance, region A loses monitoring connectivity yet stays reachable to a subset of clients; operators promote region B while A keeps accepting orders. When connectivity returns, two transaction histories conflict.

To reduce this risk:

1. Establish **one authority for the writer role** (the data platform or a controlled orchestration procedure).
2. On promotion, **fence** the old writer: block write paths/routing or revoke write permissions appropriate to the technology—never rely solely on DNS edits.
3. Have apps write via a **logical writer endpoint** rather than hardcoding one region's primary address.
4. Use an **idempotency key** on retryable commands (ordering, payment creation, event emission) and unique constraints in the authoritative store.
5. On failback, verify the new replication direction, backlogs, and integrity before returning writer authority to the original region.

If a system requires **RPO = 0 for transactional data**, asynchronous geo-replication alone usually cannot prove that target across all scenarios. Design matching consistency and business policies—even **pausing writes** when safety conditions are unmet rather than allowing dual-region writes.

### 5.2. Sessions, Transactions, Queues, and Background Jobs

- Move session/identity state to mechanisms verifiable in both regions (tokens or a DR-planned session store). Never rely on single-instance memory for critical sessions.
- When retrying across regions, an HTTP request may have succeeded in A even though the client saw a timeout. APIs must be **idempotent** or support transaction status lookup.
- For scheduled jobs and consumers, ensure only one actor executes non-duplicable work; consider distributed leases/leader election with suitable consistency guarantees.
- For queues/events, define handling for in-flight messages, ordering, duplicates, dead-lettering, and backlogs based on **actual per-service/SKU replication capabilities**.
- Separate backups and logical recovery from replication. Accidental deletes or malware can **replicate to the standby region** very quickly.

### 5.3. Readiness for Traffic Shifting

A **liveness** endpoint only reports that the process is alive; **traffic readiness** must report whether the instance can currently serve expected request flows. For write-required apps, readiness should at minimum verify connectivity to the database **write endpoint** and read-write updateability. Below is a minimal ASP.NET Core example with SQL Database (requires the **Microsoft.Data.SqlClient** package):

~~~csharp
using Microsoft.AspNetCore.Diagnostics.HealthChecks;
using Microsoft.Data.SqlClient;
using Microsoft.Extensions.Diagnostics.HealthChecks;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddHealthChecks()
    .AddCheck<WritableSqlCheck>("sql-writer");

var app = builder.Build();
app.MapGet("/health/live", () => Results.Ok("alive"));
app.MapHealthChecks("/health/traffic-ready", new HealthCheckOptions
{
    Predicate = _ => true
});
app.Run();

sealed class WritableSqlCheck : IHealthCheck
{
    private readonly IConfiguration _config;
    public WritableSqlCheck(IConfiguration config) => _config = config;

    public async Task<HealthCheckResult> CheckHealthAsync(
        HealthCheckContext context,
        CancellationToken cancellationToken = default)
    {
        try
        {
            var cs = _config.GetConnectionString("ApplicationDb");
            if (string.IsNullOrWhiteSpace(cs))
                return HealthCheckResult.Unhealthy("Missing DB connection");

            await using var connection = new SqlConnection(cs);
            await connection.OpenAsync(cancellationToken);
            await using var cmd = connection.CreateCommand();
            cmd.CommandText =
                "SELECT CAST(DATABASEPROPERTYEX(DB_NAME(), 'Updateability') AS varchar(20))";
            var mode = await cmd.ExecuteScalarAsync(cancellationToken) as string;
            return mode == "READ_WRITE"
                ? HealthCheckResult.Healthy()
                : HealthCheckResult.Unhealthy("SQL is not writable");
        }
        catch (Exception ex)
        {
            return HealthCheckResult.Unhealthy("SQL writer unavailable", ex);
        }
    }
}
~~~

In operational setups, `ApplicationDb` should use a secure connection to the writer endpoint authenticated with **Microsoft Entra / managed identity** where supported, avoiding passwords in source code. Health checks need short timeouts, connection pooling, stability thresholds, and rate bounds. This snippet illustrates only the SQL path check; **`READ_WRITE` does not prove the entire business flow is ready**. Add checks for critical dependencies while avoiding cascading failovers triggered by non-essential services.

## 6. Design Example: Two-Region Ordering API

Assume an ordering system serving users in Asia with these requirements:

| Constraint | Exercise assumption |
| --- | --- |
| Failure to survive | Total loss of the primary app and database region |
| RTO | Maximum **30 minutes** |
| RPO | Maximum **5 minutes** for confirmed orders |
| Data | Azure SQL, order transactions, single writer only |
| Peak traffic | 2,000 requests/second system-wide |
| Backup region | Separate region with matching services/SKUs, quotas, data residency compliance |

**Decision:** start with **active-passive hot standby** for the API and a single-writer SQL failover group. Front Door prioritizes origin A and is ready to switch to origin B when B is healthy; B's supporting services and secrets are fully provisioned. If budget is tighter, evaluate warm standby, factoring scale-out duration into RTO.

**Normal flow:**

1. Front Door receives HTTPS, applies WAF policy, and forwards requests to App Service A.
2. The app uses the SQL failover group **read-write listener**, not a hardcoded region A database host.
3. SQL primary replicates asynchronously to the geo-secondary. Monitor **replication lag**, app errors, and user latency.
4. App Service B stays ready with configuration, managed identity, network access, DNS, secrets, and writer connectivity. Probes verify more than just process status.
5. Order creation requests carry an idempotency key; database transactions and event emission use retry-safe patterns such as a transactional outbox where appropriate.

**When region A fails completely:**

1. Alerts from external synthetic probes, Front Door, and Azure Monitor are cross-checked to avoid reacting to a single flaky check.
2. Invoke the runbook, determine incident scope, replication lag, and expected data loss. If forced failover is required, record the RPO risk decision.
3. Switch **SQL primary** authority to B via the service-supported mechanism; ensure A cannot resume writes if it regains connectivity.
4. App Service B confirms the writer endpoint works, permissions are valid, jobs/consumers are safe, and **traffic readiness** succeeds.
5. Front Door shifts traffic to B by health/priority; monitor error rates, p95, throughput, order counts, and backlogs. Scale B if traffic rises.
6. Reconcile in-flight orders, retried requests, and unsent events, then communicate recovery status.

**RTO breakdown for verification:** detection 2 min + triage/decision 3 min + data failover 4 min + scale/warm-up 6 min + traffic stabilization 2 min + business validation 5 min = **22 minutes** assuming sequential steps that actually hit those timings. This is only a **trial budget**; if promotion or scaling takes 20 minutes in reality, the 30-minute target can be breached. Some steps can run in parallel, yet only drill results confirm RTO.

**A 5-minute RPO is not automatically guaranteed** by an SQL failover group. Measure replication lag under peak load and understand the risk of unreplicated transactions during an unexpected outage. If potential data loss exceeds business limits, evaluate alternative confirmation, compensation, and data architectures.

## 7. Full Operational Design for Each Region

### 7.1. Resources, Networking, Identity, and Secrets

Build repeatable infrastructure with **Bicep or Terraform**, parameterized per region with consistent resource naming and tags. Use checked, least-privilege pipelines to deploy both regions. For each region, review:

- **Compute:** App Service/AKS/Container Apps SKUs and features available in that region, minimum instances, autoscaling, and quotas.
- **Networking:** VNet/subnets, private endpoints, private DNS, NSGs, firewalls, egress, hybrid links, and routes when the primary region is down.
- **Identity and secrets:** managed identities, Entra ID, role assignments/RBAC, Key Vault, TLS certificates, encryption keys, and secret provisioning/rotation.
- **Data:** primary/secondary setup, backups, retention, restores, replication, and read/write access permissions.
- **Ops:** Azure Monitor, Application Insights/Log Analytics, alerts, action groups, dashboards, and incident communication channels.
- **External dependencies:** payment providers, email, webhooks, on-premises systems; verify they allow traffic originating from region B.

For network security, Azure Front Door can support origin-protection mechanisms appropriate to service type and tier, yet you must verify the exact setup; never assume enabling WAF prevents direct calls to the origin. Also review management and authorization paths when the primary region or a private link component is down.

### 7.2. N-1 Capacity and Cost

With **50/50 active-active**, each region normally handles roughly 1,000 requests/second in the 2,000 requests/second example. If one region fails, the surviving region must handle nearly **2,000 requests/second** plus an appropriate safety margin. You cannot merely double API instances: database connections, storage throughput, queue consumers, networking, caches, rate limits, and third-party quotas must also absorb the surge.

Costs must span the full lifecycle: continuously running compute in both sites, data copies, backups, replication, **cross-region data transfer**, global ingress traffic, logs/metrics, drills, and standby headroom. Hot standby approaches the cost of two production environments; warm standby costs less but introduces scale-time and allocation-quota risks.

### 7.3. Monitoring Must Observe User Experience and Data State

Recommended signal set:

| Signal | Why it is needed |
| --- | --- |
| Multi-location synthetic tests | Detects user inaccessibility even when VMs/App Service report running. |
| Front Door origin health, HTTP 5xx, latency | Shows whether traffic is shifting and which origin is failing. |
| API success rate, p95/p99, dependency failures | Verifies SLOs at the business and user-experience level. |
| SQL replication lag, writer role, connection errors | Tracks RPO exposure and prevents routing where writes cannot succeed. |
| Cache hit/miss, queue backlog, consumer lag | Surfaces bottlenecks after concentrating load onto region B. |
| Capacity, autoscaling, quotas, and cost | Ensures N-1 capacity and controls DR budget. |

Example KQL query in a **Log Analytics workspace** using `AppRequests` (verify column names and data sources against your Application Insights setup):

~~~kusto
AppRequests
| where TimeGenerated > ago(24h)
| summarize Requests = count(),
            Succeeded = countif(Success == true)
    by bin(TimeGenerated, 5m), AppRoleName
| extend SuccessPct = 100.0 * todouble(Succeeded) / Requests
| order by TimeGenerated asc
~~~

This metric **cannot count requests blocked at Front Door or failing before reaching the app**; measuring end-to-end experience requires combining edge signals and synthetic probes. Alerts need proper thresholds and evaluation windows to avoid flapping routes on brief noise.

## 8. Failover, Failback, and Drills

**Failover** shifts workload traffic and data roles to the standby region. **Failback** is the decision to return to the original region after remediation, resynchronization, and risk assessment; failback does not have to occur the instant the old region comes back online.

A minimum runbook should specify owners, trigger criteria, observed metrics, approved commands/actions per service, split-brain prevention, safe abort points, and rollback paths. Reference orchestration flow:

~~~mermaid
flowchart TD
    D[Detect degradation in region A] --> V{Incident meets failover criteria?}
    V -->|No| O[Investigate and continue monitoring]
    V -->|Yes| G[Assess RPO and lock invalid write paths]
    G --> P[Promote writer to region B per runbook]
    P --> R{Can B write and serve business flow?}
    R -->|No| S[Hold traffic switch, fix dependencies]
    R -->|Yes| T[Shift/open traffic to B]
    T --> H[Verify transactions, SLIs, backlog, and load]
    H --> F[Recover region A, resync, and plan failback]
~~~

Conduct periodic **game days** with explicit measurement criteria:

| Drill test | What to record |
| --- | --- |
| Fail one instance or zone | Fault stays isolated; unrelated flows stay within SLO. |
| Take origin A out of service | Front Door/Traffic Manager switches properly, clients retry safely; measure duration and 5xx. |
| Simulate primary database unable to write | Readiness fails accurately, writer promotion/fencing works, actual RPO checked. |
| Shift 100% load to B during simulated peak | Throughput, latency, queues, database, and quotas stay within limits. |
| Break cross-region network while both apps run | No dual unauthorized writers; read/write behavior matches consistency policy. |
| Corrupt/delete data or push broken release | Restore/rollback from backups or safe artifacts; replication does not replace logical recovery. |
| Failback after A recovers | Zero lost/duplicate orders; replication direction and writer authority re-verified. |

For every test, record **incident start, detection, decision, last intact data point, successful service restoration, and user error count**. Derive achieved RTO/RPO, update runbooks, and increase automation only after observing safe behavior. Drill in non-production environments first; any production testing must follow organizational schedules and change controls.

## 9. Common Mistakes and How to Check for Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Running app in two regions and calling it DR | Database, keys, queues, or DNS become shared SPOFs | Draw an end-to-end dependency graph and test actual regional loss. |
| Pointing Front Door probe at a static HTTP 200 path | Origin looks healthy while the database cannot write | Use layered readiness checks and route by business capability. |
| Treating geo-replication as backup or RPO = 0 | Logical corruption replicates to secondary; unreplicated writes are lost | Separate backups/restores, measure lag, and test forced failover. |
| Active-active using in-memory sessions | Users lose sessions or see stale/skewed data across regions | Externalize sessions and define consistency and idempotency. |
| Splitting 50/50 when each region only holds half capacity | Surviving region overloads immediately on failover | Test N-1 capacity, quotas, and scale-out speed. |
| Promoting B while A can still write | Split-brain and irreconcilable transaction histories | Enforce explicit fencing and writer authority before opening writes. |
| Switching back to A the moment services turn green | Unsettled backlogs, cold caches, and unstable replication | Run failback on a dedicated schedule, reconciliation, and control process. |

## 10. Design Practice Exercise

Outline an order-management service with a global frontend, APIs on Azure, and an Azure SQL database. Assumed requirements: 30-minute RTO, 5-minute RPO, 2,000 requests/second peak, and zero duplicate orders. Deliverables:

1. **One-page ADR** choosing active-passive hot, warm, or active-active reads / single-writer; justify using RTO/RPO, consistency, and cost.
2. **Architecture diagram** showing edge routing, at least two regions, writer endpoint, replication path, identity/secret dependencies, and monitoring.
3. **Failover runbook table** detailing detection signals, promotion approver, old-writer fencing, readiness conditions, traffic cutover, and verification metrics.
4. **N-1 test scenario** at 2,000 requests/second plus retry verification with idempotency keys.
5. **Failback plan** with abort criteria and checks for missing/duplicate orders.

A strong answer will not claim a 5-minute RPO merely because geo-replication is enabled: it explains how to **measure replication lag**, handle or mitigate forced-failover risk, and reconcile transactions not guaranteed to have replicated.

## Key Takeaways

- **Multi-region is an end-to-end challenge**, covering traffic, apps, data, identity, networking, operations, and recovery.
- **Active-passive** is generally simpler when business rules require a single writer; hot/warm/cold standby dictates cost and RTO.
- **Active-active** serves multiple geographies and can shift traffic fast, yet demands proven consistency, conflict handling, and **N-1 capacity**.
- **Azure Front Door / Traffic Manager solve traffic routing**; database promotion, data protection, and failback require dedicated strategies.
- **SLOs, RTO, and RPO matter only when measured through drills**; replication does not replace backups and having two regions does not automatically protect against all outages.
