# Designing Multi-Region Failover

An application running on Azure can operate smoothly for months and then face a connectivity loss, a data dependency failure, or a region-wide outage. If the entire web frontend, API, and database live in a single region, multiple VMs or multiple instances in that same region still cannot keep the service alive if the whole region becomes unresponsive. **Multi-region failover** is the ability to shift operations to a standby region or a set of remaining healthy regions so the application continues serving within designed recovery targets.

This lesson belongs to the **Load Balancing and Application Delivery** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module explores Microsoft Azure from subscriptions, resource groups, and Entra ID to virtual networks, compute, storage, data services, deployment, monitoring, protection, and cost control. Multi-region failover ties all of these topics together: traffic distribution is only one piece; **data, identity, configuration, operational readiness, and cost** determine whether the system truly recovers.

After this lesson, you will be able to:

- Distinguish intra-region high availability from cross-region disaster recovery.
- Define **RTO** and **RPO** targets and assess their impact on architecture.
- Choose active-passive, active-active, or hot/warm/cold standby based on requirements.
- Compare **Azure Front Door**, **Azure Traffic Manager**, and **cross-region Azure Load Balancer**.
- Design health probes, origin priorities, routing, and prevent flapping.
- Define failover ordering for applications, databases, caches, queues, and dependencies.
- Build a drill runbook, verify failover/failback, and plan costs.

## 1. Understanding Failures and Recovery Scope

Before provisioning a second region, identify the failure scenarios the system must withstand:

| Scenario | Example | Appropriate response |
|---|---|---|
| Single instance failure | A VM or container becomes unhealthy | Intra-region load balancer shifts to another instance |
| Availability Zone failure | One zone suffers a power or network outage | Multi-zone deployment within the region where supported by services |
| Regional app service failure | App Service or backend stops returning valid responses | Recover in-region or shift traffic when eligible |
| Broad regional outage | Multiple network/compute components become unavailable | Activate the prepared standby region |
| Data corruption or accidental deletion | Bad writes replicate to the secondary | Restore from backup/point-in-time, not merely switch regions |
| System-wide bad deployment/config | A release breaks both regions | Roll back software/config; failover alone will not fix it |
| Global dependency outage | DNS, shared secret/config, or external provider failure | Dependency analysis and separate recovery plan |

**High availability (HA)** reduces disruption from routine component failures. **Disaster recovery (DR)** focuses on recovering when disruptions exceed normal HA boundaries. Deploying across multiple Availability Zones in one region protects against zone failures; it does not replace recovery when that entire region becomes unavailable.

Not every HTTP 500 is a reason to fail over regions. If both regions run the same buggy release, failing over can spread or worsen confusion. A sound procedure defines **failure categories**, trigger conditions, and how to return to a steady state.

## 2. Setting RTO and RPO Targets

Two standard targets in DR design:

- **RTO — Recovery Time Objective:** the maximum downtime an organization targets before the service is restored.
- **RPO — Recovery Point Objective:** the maximum amount of data loss, measured in time, an organization tolerates during an incident.

Example: an online store sets an RTO of **30 minutes** and an RPO of **5 minutes**. The design must get shoppers back to placing orders within the target time and bound data loss within the chosen threshold. These are business targets, **not automatic guarantees** from an Azure service merely because geo-replication is turned on.

~~~text
09:58   Last update reaches the standby replica
10:00   Primary region stops serving
10:03   Monitoring detects and confirms the outage
10:08   Database write promotion completes
10:11   Ingress shifts traffic to the standby region
10:15   Application verified as fully recovered

Observed RTO in example: 10:15 - 10:00 = 15 minutes
Observed RPO in example: 10:00 - 09:58 = 2 minutes
~~~

This is an **illustrative timeline**. On a real system, RTO includes detection, decision-making, data promotion, path updates, workload startup, and functional verification. RPO depends on actual commits and replication lag, which can differ across data stores or operations.

### Do Not Measure Only DNS Switch Speed

A system might switch DNS within minutes, yet the database in the standby region has not been promoted to primary, secrets are missing, or processing queues only exist in the primary region. Users then see the webpage load but cannot place orders: **the service has not met its functional RTO**.

Define **full recovery** via business checks, such as signing in, reading carts, placing orders, looking up orders, processing events, and sending notifications.

## 3. Multi-Region Deployment Models

### Active-Passive

One region handles most or all production traffic; the other stands ready to take over during an incident.

~~~text
                     Users
                       |
             Global entry / routing
                       |
               Region A (active)
                 Web + API + DB
                       |
                Replication
                       |
               Region B (standby)
                 Web + API + DB
             (not serving primary traffic)
~~~

Pros: simpler data write paths and operations, minimizing write conflicts. Cons: standby resources may sit idle and must have enough capacity when traffic shifts.

### Active-Active

Two or more regions serve traffic simultaneously:

~~~text
                      Users
                        |
                   Global routing
                   /           \
            Region A         Region B
            Web + API        Web + API
                   \           /
                 Data and state
                designed multi-region
~~~

Pros: lower regional latency, utilization of multi-region capacity, and potentially fast recovery if architected properly. Cons: must solve **data synchronization, write ordering, customer partitioning, consistency, conflict resolution**, and capacity to absorb load if one region goes down.

**Application active-active does not automatically mean data active-active.** You can run active frontends in two regions against a single primary database writer, forcing one region to reach across regions for data writes.

### Cold, Warm, and Hot Standby

| Standby tier | Secondary region state | Typical trade-offs |
|---|---|---|
| **Cold standby** | Mostly keeps configs, images, backups, and IaC; workloads not running at scale | Lower baseline cost, but many startup steps and longer RTO |
| **Warm standby** | Subset of services running at reduced capacity with data prepared | Balances cost and speed; must scale up on failover |
| **Hot standby** | Infrastructure ready for full load, continuously monitored, data replicated | Shorter RTO possible, but higher cost and requires frequent drills |

Labels are not SLAs. A warm standby can miss RTO if quota is insufficient to scale instances, and a hot standby still fails if database promotion or dependency connections were never tested.

## 4. Choosing a Global Traffic-Steering Service

Azure offers several options; **do not treat a regional load balancer as an automatic region-switching tool**.

| Service | Processing model | Strengths | Key limitations |
|---|---|---|---|
| **Azure Front Door Standard/Premium** | Global HTTP/HTTPS edge reverse proxy based on origin groups/routes | Health probes, origin priority, acceleration, web/API routing; optional WAF by tier | HTTP(S) only; does not replace data layers or backend recovery |
| **Azure Traffic Manager** | **DNS-based** routing with Priority, Performance, Weighted, etc. | Fits public endpoints needing DNS steering; app protocols not HTTP-proxied by Traffic Manager | Subject to TTL, resolver/client caches; not an inline proxy |
| **Cross-region Azure Load Balancer** | Global Layer 4 load balancer with supported regional backend models | Fits TCP/UDP scenarios under supported LB architectures | Not a WAF; does not support arbitrary backends; requires supported SKUs/topologies/regions |
| **Application Gateway** | Regional HTTP(S) reverse proxy | Fits Layer 7 load balancing, TLS, and WAF within a region | A single Application Gateway does not provide a global multi-region entry point |
| **Regional Azure Load Balancer** | Single-region Layer 4 | Distributes TCP/UDP to backends in supported topologies | Does not handle cross-region failover on its own |

### Azure Front Door: Selecting Healthy Origins

With Front Door, you configure a profile, endpoint, route, origin group, and origins in regions A/B. Health probes and routing conditions help Front Door choose eligible origins. You can use **priority** to prefer origin A in active-passive designs, and **weight** plus **latency** for load distribution when origins share the same priority.

Design note: origin selection is not governed solely by a priority column; health probes, origin settings, routes, latency sensitivity, and origin-group options all affect outcomes. Test against your actual configuration instead of assuming from diagrams.

~~~text
https://shop.example
        |
  Azure Front Door
        |
    Origin group
        +-- origin-a: app-region-a.example (priority 1)
        +-- origin-b: app-region-b.example (priority 2)
        |
        +-- health probe: /health/ready
~~~

**Security note:** if origin B is an App Service or API with its own public Internet address, restrict direct access so callers cannot bypass Front Door/WAF. Evaluate Private Link where supported by tier and origin type, access restrictions, and Front Door identity verification per service guidance. Enforce TLS from client to Front Door and onward to origins as required.

### Azure Traffic Manager: DNS Priority Failover

Traffic Manager answers DNS queries based on routing method and endpoint health. In **Priority** mode, the healthy endpoint with the highest priority is returned preferentially; when monitoring marks it unavailable, an eligible standby endpoint can be returned for new queries.

~~~text
             DNS lookup: app.example
                        |
                 Traffic Manager
                        |
            +-----------+-----------+
            |                       |
    Region A endpoint        Region B endpoint
     higher priority          lower priority
~~~

Traffic Manager **does not receive and proxy every client HTTP request**. After resolving DNS, clients connect directly to the target endpoint. Transition timing depends on TTL, DNS resolvers, app caches, and existing connections; never promise that every client switches regions the instant endpoint A turns unhealthy.

If an application requires TCP/UDP or a protocol unsuitable for an L7 reverse proxy, evaluate Traffic Manager or cross-region Load Balancer per product capabilities. Separately review how endpoint health is probed and how clients reconnect.

## 5. Architecture Example: Active-Passive Web/API Across Two Regions

Suppose a company operates an order management system. Requirements: customers use a single hostname, the service must stay available if the primary region fails, order loss must be minimized, and duplicate orders must be prevented.

~~~text
                     https://orders.example
                              |
                      Azure Front Door
                        (global HTTP)
                              |
                +-------------+-------------+
                |                           |
        Region A (primary)          Region B (standby)
        +------------------+        +-------------------+
        | Web / API        |        | Web / API         |
        | Health endpoint  |        | Health endpoint   |
        +--------+---------+        +---------+---------+
                 |                            |
        +--------v---------+          +-------v----------+
        | Database primary | ~~~~~~~> | Geo secondary    |
        | Read/write       | repl.    | Promoted if DR   |
        +------------------+          +------------------+

        Other dependencies: identity, secrets, cache,
        queue/event, object storage, external APIs, DNS.
~~~

The diagram shows the **logical architecture**. For Azure SQL Database, you can evaluate **failover groups/active geo-replication** with listener endpoints; for other database engines, replication and promotion mechanics differ. Never force a single database pattern onto every workload.

### Components to Deploy in Both Regions

| Component | Region A | Region B | Condition for failover |
|---|---|---|---|
| Frontend/API | Serving normally | Ready and tested | Enough instances/capacity to carry load |
| App configuration | Approved release | Compatible with A | Same contracts, endpoints, and feature flags |
| Database | Primary writer | Secondary/replica | Defined write promotion and lag handling |
| DNS/certificates | Hostname via global entry | Same public hostname at steering layer | TLS and routing verified |
| Secrets/keys | Securely managed | Accessible when A fails | No single-region endpoint/copy lock-in |
| Queues/workers | Active task workers | Standby workers | Prevent both worker pools from misprocessing |
| Logs/monitoring | Metrics/logs/alerts | Equivalent setup | Still observable if A loses connectivity |
| External systems | Payment, mail, webhooks | Approved routes/allowlists | Partners accept egress and callbacks from B |

Configuring two origins in Front Door alone is **not enough**. If region B lacks a writable database, queues, or secrets, ingress may fail over to a site unable to process transactions.

## 6. Designing Reliable Health Probes

**Health probes** decide whether traffic routes to an origin. A probe that is too simplistic can report healthy when the app is unusable; a probe that is too deep can trigger unnecessary region failovers over minor dependency glitches.

### Liveness vs. Readiness

- **Liveness:** is the process running and responsive? Typically used to restart hung instances.
- **Readiness:** can this instance/region serve traffic for its current role? Used by ingress to decide whether an origin should receive requests.

Example endpoint separation:

~~~text
GET /health/live
  200 if the process is alive

GET /health/ready
  200 when the app can serve requests in its assigned role
  503 when the app is not ready for traffic
~~~

**Standby region readiness must be designed carefully.** If backend B only has a read replica and cannot accept writes yet, returning 200 for all requests on standby can cause ingress to shift traffic before database promotion, triggering write failures. Two coordination approaches:

1. Have readiness report not-ready for write workloads until promotion and role transition finish.
2. Use a dedicated orchestration/cutover step so ingress treats B as primary only after business prerequisites are ready.

Never let a public probe accidentally write data, create orders, or leak secrets. Probes should be lightweight, stable, check only **mandatory** dependencies, and use sensible timeouts.

### Avoiding Flapping

**Flapping** occurs when the system repeatedly bounces between A and B due to unstable metrics. Mitigations:

- Mark unhealthy only after a sensible number of consecutive failed probes per service capabilities.
- Use health checks representative of real transactions rather than a static homepage.
- Define thresholds, observation windows, and authorized roles/procedures for database write promotion.
- When region A recovers, avoid snapping all traffic back immediately before verifying stability.
- Monitor WAF, TLS, DNS, and backend health together to avoid misdiagnosing root causes.

Do not copy probe intervals, failure counts, and thresholds blindly from another product's docs: health algorithms and knobs differ across Front Door, Traffic Manager, and cross-region LB.

## 7. Data Determines RPO and Failover Viability

### Azure SQL Database and Failover Groups

For Azure SQL Database, consider **failover groups** to manage a database group with a geo-secondary and provide listener endpoints that reduce connection string changes when the primary switches. Cross-region replication is **asynchronous**, so a forced failover during a severe outage can lose transactions not yet replicated.

Points to design:

- Distinguish **planned failover** (both sides alive, minimizing data loss) from **forced/unplanned failover**.
- Verify permissions, credentials, firewall/private endpoints, and connection policies in region B.
- Monitor replication lag, replica state, and primary switching per service guidance.
- Use read-write/read-only listener endpoints instead of hardcoding a single region's primary server name.
- Configure automatic failover policy/grace period if supported and aligned with goals; do not assume application traffic switching automatically synchronizes with database switching.
- Multi-database or distributed data systems need consistency plans, schema/migration discipline, and post-failover validation.

If using **Azure SQL Managed Instance**, failover group capabilities and constraints may differ from Azure SQL Database. Follow documentation for your exact service type.

### Azure Cosmos DB

Cosmos DB provides multi-region distribution with **single-write region** or **multi-write region** options depending on supported APIs/configs. Design must choose an appropriate consistency model, failover mechanism, conflict resolution, and SDK retry/endpoint discovery settings.

**Multi-write does not mean conflict-free data.** Two regions can accept updates to the same item; the application must handle conflicts and the selected consistency model. In single-write mode, switching the write region has specific preconditions and ordering.

### Azure Storage

Options like **GRS/GZRS** replicate data to a secondary region under storage account rules. **RA-GRS/RA-GZRS** can allow reads from the secondary endpoint under certain conditions. However, the secondary is **not automatically a writable primary**, and account failover has its own process and impact.

Geo-redundancy is not versioned backup and does not fix accidental deletions that already replicated. Add versioning, soft delete, and backup/retention if required by the workload. Storage account failover, endpoint changes, and potential data loss must be treated as controlled DR decisions.

### Queues, Events, and Background Tasks

Systems commonly include message queues, schedulers, or event consumers. Avoid assuming every messaging service replicates **message data** across regions:

- Some messaging geo-disaster recovery/alias features focus on **metadata/configuration**, meaning messages currently sitting in queues are not automatically mirrored.
- During failover, workers may reprocess retried requests. Design **idempotency keys**, deduplication, replay, and dead-letter queues wherever possible.
- Establish clear ownership for sequential jobs and prevent both regions from issuing the same transaction.
- For external integrations outside Azure, verify egress IPs, endpoint allowlists, and credentials in the standby region.

### Key Insight: Every Data Store Has Its Own RPO

An app might have SQL with an RPO of minutes, blob storage with a different recovery point, unreplicated queues, and rebuildable caches. The business RPO of a **complete transaction** is bounded by its most critical component and how those components coordinate.

If a user sees "order placed" yet the order never reached the secondary, the system needs a post-failover reconciliation process against payment gateways and transaction logs.

## 8. Stateless Web Tiers, Sessions, and Caches

Keep frontend/API tiers as **stateless** as possible so new requests can run in whichever region is healthy:

- Do not keep shopping carts or checkout steps solely in a single instance's RAM.
- Use multi-region-capable session/token mechanisms; if sessions live in a central store, that store also needs DR.
- Verify cookie validation, JWT signing, and key rotation across both regions; never copy secrets casually via files.
- For caches, distinguish rebuildable data from critical state that cannot be lost.
- If using sticky sessions/affinity, plan how sessions recover when an origin drops, or force a clean re-login safely.
- Scheduled jobs must guard against both regions sending duplicate emails or charging twice if triggered concurrently.

The goal is not keeping every TCP socket alive through a region outage. What matters is that **clients can safely retry/reconnect** and the app communicates clear status when an operation is unconfirmed.

### Idempotency for Write Transactions

Suppose a customer clicks "Pay," the request processes in A, and the response is lost as region A goes down. The client retries to B. Without an idempotency key, the two regions could create duplicate transactions or charge twice.

~~~text
POST /orders
Idempotency-Key: order-request-42

API:
  - Look up the request key in a business data store with appropriate consistency
  - If already processed: return the stored result tied to that key
  - If not yet processed: execute within a uniqueness constraint / safe transaction
~~~

This is a logical pattern. Key storage, retention period, consistency guarantees, and handling unreplicated data must all be designed explicitly. Adding a header without backend guarantees does not solve cross-region retries.

## 9. Failover Sequencing: Coordinating Application and Data Cutover

A good runbook prevents **split-brain**: both A and B believing they are the primary writer without safe multi-write coordination.

### Reference Runbook for Active-Passive

1. **Detect:** monitoring and health probes alert that A is unavailable; correlate multiple signals rather than a single failed request.
2. **Assess:** confirm outage scope—check whether it is a global issue, a faulty recent deployment, or data corruption.
3. **Decide:** weigh RTO/RPO, replication lag, and data-loss risk. Trigger the appropriate approval workflow.
4. **Fence write access:** isolate or disable writer A if A might still be alive yet unreachable, preventing two independent writers.
5. **Switch data:** promote secondary/switch primary per database mechanics and approved policy; record data state.
6. **Activate app B:** verify config, secrets, networking, connection strings/listeners, workers, and write permissions.
7. **Verify B readiness:** run safe non-destructive read/write checks and verify mandatory connectivity paths.
8. **Steer traffic:** use Front Door, Traffic Manager, or the chosen global entry point to direct users to B.
9. **Verify business workflows:** sign in, search, submit a safe test transaction, consume events, and reconcile data.
10. **Monitor and communicate:** log timestamps, actual RTO/RPO, error rates, and latency; update stakeholders.

The exact sequence varies by service. Some data services support automatic failover; in other cases, shifting traffic before switching write ownership causes errors. Design docs must clearly state the **data ownership handoff point** and readiness gates at each stage.

### Pseudo-Runbook

~~~text
if outage_confirmed
   and failover_authorized
   and region_b_capacity_sufficient
   and data_loss_risk_accepted:

    fence_primary_writes_in_region_a()
    promote_secondary_data_if_required()
    validate_region_b_read_write_paths()
    mark_region_b_ready_for_ingress()
    shift_global_traffic_to_region_b()
    run_business_smoke_tests()
    watch_errors_latency_replication_and_cost()
else:
    keep_diagnosing_and_record_decision()
~~~

This is orchestration pseudocode, not a runnable Azure script. In particular, **fencing must rely on capabilities supported by the data service**; merely shutting down a VM may not suffice if connections or transactions elsewhere remain active.

## 10. Failback: Returning to the Original Region Is More Than Flipping a Route

When A comes back online, A may hold stale data and is no longer primary. Immediately sending requests back to A risks reading stale data or overwriting new writes created in B.

A safe **failback** plan includes:

1. Confirm A is stable; fix the root cause and apply needed versions/configs.
2. Re-establish replication topology from current primary B back to A per service capabilities.
3. Wait for A to catch up and verify consistency, migrations, versions, and business data.
4. Run a planned failover to move primary back to A if needed, minimizing data loss.
5. Verify A readiness and confirm a single primary writer.
6. Shift traffic back carefully, monitoring errors, throughput, and cost.
7. Document timeline, actual RTO/RPO, and lessons learned.

**Immediate failback is not mandatory.** If B is serving steadily, waiting for an approved maintenance window is usually safer than snapping back to A the moment a health probe recovers.

## 11. Covering All Cross-Region Dependencies

A region outage affects services easily overlooked on a web/API diagram. Audit every category:

| Dependency group | Design questions |
|---|---|
| **Identity** | Can users still sign in? Does app B have the right app registration, permissions, and callback URLs? |
| **Secrets/keys** | Can B access required secrets/certificates/keys? What happens if a vault or endpoint in A fails? |
| **Networking** | Are B's VNets/subnets, NSGs, UDRs, NAT, Private Endpoints, private DNS zones, and firewalls ready? |
| **Public ingress** | Do Front Door/Traffic Manager/certificates/custom domains operate independently of A? |
| **Data** | How are replicas, backups, recovery, encryption, key dependencies, and write permissions handled? |
| **Files/media** | Are uploaded files present in B? Are static URLs, CDN, and cache invalidation aligned? |
| **Message processing** | How are workers, queues, checkpoints, dead-letter queues, and schedulers recovered? |
| **Third-party APIs** | Do payment gateways, webhooks, email providers, and IP allowlists accept region B? |
| **Observability** | When A is down, are dashboards, alerts, and runbooks still accessible? |
| **Deployment** | Are Terraform/Bicep/pipelines, image registries, artifacts, and quota for B available? |

Multiple regions do not automatically guarantee independence if both rely on a single endpoint, an expired credential, or a faulty deployment job. Assess the **blast radius** of shared config edits, secret rotations, releases, and access changes.

### Infrastructure as Code and Compatible Configurations

Use Terraform, Bicep, or an appropriate IaC tool to define A/B infrastructure consistently: naming, tags, network rules, app settings, monitoring, and policies. For data, never run a breaking schema migration in one region before the other region can read/write safely.

Design releases with **backward/forward compatibility** where needed, feature flags, and rollback procedures. DR fails easily if app B runs a version incompatible with the database schema after failover.

### Region Pairs and Data Residency

Azure defines region pairs in certain geographies with specific service behaviors, yet **do not assume every service replicates to its paired region or meets a fixed RPO/RTO automatically**. Select the secondary region based on residency/compliance, latency, SKU/quota, service availability, fault isolation distance, and cost. Verify DR features per service rather than assuming from pairing alone.

## 12. Routing Deployment Guide via Azure Portal

This section illustrates routing with **Azure Front Door Standard/Premium** for HTTP/HTTPS applications, not the entire database DR workflow. Before starting, ensure you have two valid, authorized backend app/API deployments.

### Step 1: Prepare Both Origins

- Deploy the same tested version of the app to regions A and B.
- Verify each backend has a hostname, TLS, health endpoint, and networking configured.
- Verify B can handle requests per its assigned role. Until data is promoted, do not send production writes to B.
- Prepare access permissions, secrets, and controls restricting direct access to origins.

### Step 2: Create Front Door Profile and Origin Group

1. In the [Azure Portal](https://portal.azure.com), open Azure Front Door and create a Standard/Premium profile as required.
2. Create an endpoint and origin group representing the ordering application.
3. Add origin A and origin B with appropriate hostnames/backends.
4. Set active-passive priorities: give A higher priority than B, ensuring B becomes eligible to serve only when B's data and app are ready.
5. Configure the health probe (protocol/path/method/interval matching current service capabilities).
6. Create a route mapping public hostname/paths to the origin group.
7. Configure custom domain/TLS and WAF/security policies if used; block bypass paths to origins.
8. Verify requests, responses, access logs, origin health, and cutover behavior in a test environment.

Portal labels may change over time. Specific options depend on tier/SKU and private-origin support for each backend type.

### Step 3: If Using Traffic Manager

Instead of a reverse proxy, you can:

1. Create a Traffic Manager profile with routing method **Priority**.
2. Configure DNS name, TTL, and endpoint monitoring.
3. Add monitored, reachable endpoints A/B and assign priority order.
4. Configure public DNS so the application hostname points to Traffic Manager per supported pattern.
5. Simulate disconnecting a lab endpoint and inspect DNS responses from multiple resolvers over time.
6. Confirm the app handles reconnects/retries and data is ready in B.

Never experiment with production DNS records without a plan and change window. With Traffic Manager, **DNS propagation/caching** is a major variable in RTO.

## 13. Read-Only Configuration Inspection with Azure CLI

The commands below only **list/view** resources without creating or modifying global routing. They are useful for inspecting existing profiles, origin groups, and configurations.

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --output table
~~~

List Front Door profiles in a resource group:

~~~bash
az afd profile list \
  --resource-group <RESOURCE_GROUP> \
  --output table
~~~

View origin groups in a profile:

~~~bash
az afd origin-group list \
  --resource-group <RESOURCE_GROUP> \
  --profile-name <AFD_PROFILE_NAME> \
  --output table
~~~

View origins in a selected group:

~~~bash
az afd origin list \
  --resource-group <RESOURCE_GROUP> \
  --profile-name <AFD_PROFILE_NAME> \
  --origin-group-name <ORIGIN_GROUP_NAME> \
  --output json
~~~

For Traffic Manager:

~~~bash
az network traffic-manager profile list \
  --resource-group <RESOURCE_GROUP> \
  --output table

az network traffic-manager endpoint list \
  --resource-group <RESOURCE_GROUP> \
  --profile-name <TM_PROFILE_NAME> \
  --output table
~~~

In these examples, values inside **< >** are placeholders to replace before running. Azure CLI syntax can vary across versions and extensions; run **az afd --help** or the command's help output to confirm. Listing output shows **configuration** only; it is not proof of end-to-end failover or RTO/RPO compliance.

## 14. Failover Monitoring and Alerting

Monitoring must show **whether a region is healthy, where traffic is flowing, and whether business workflows have recovered**:

| Signal | What to observe |
|---|---|
| Synthetic availability | Multi-location checks covering sign-in or safe read-only workflows |
| Front Door/Traffic Manager health | Origin/endpoint status, origin switch events, probe config |
| HTTP error rate | 5xx and app errors broken down by region, origin, and hostname |
| Latency | p95/p99 globally and per region |
| Database health | Primary/secondary roles, replication lag, failover state |
| Data correctness | Successful orders, payment reconciliation, delayed/missing/duplicate events |
| Capacity | CPU/instances/connections/throughput and quota in B when A is down |
| Security/network | WAF, TLS, DNS, firewalls, private networks, and access restrictions |
| Cost | Standby baseline, cross-region transfer, monitoring, geo-replication |

Do not trigger automatic database failover from a single ingress probe alone. Require independent signals and logic ruling out DNS issues, WAF blocks, or a bad deployment affecting both A and B.

**Alerting** must still reach on-call responders even if A is unavailable. Store runbooks where they are accessible from both regions, and verify emergency contacts and decision authority in advance.

## 15. Failover Drills and Chaos Testing

DR testing should have at least three layers:

1. **Tabletop:** walk through an outage on paper, confirming owners, required data, and action order.
2. **Staging/sandbox failover:** run on an isolated environment, testing origin routing, data promotion, and smoke tests.
3. **Controlled game day:** when approved, rehearse partial or full failover on a production-representative architecture with rollback and monitoring.

### Testing Matrix

| Scenario | Expected behavior | Evidence |
|---|---|---|
| One instance in A fails | Intra-region LB/HA handles traffic if healthy instances remain | Health status and synthetic tests |
| Entire frontend A fails, B eligible | Global entry shifts valid requests to B | Origin logs, status, responses from B |
| Database A fails while app A stays up | Does not report healthy for write paths; triggers data procedure | Readiness and DB primary status |
| B receives traffic without write rights | Blocks/alerts cleanly; never fakes success | API logs, trace of test transaction |
| A recovers after B became primary | No automatic split-brain or premature failback | Primary state, replication status |
| Payment request retried cross-region | No duplicate transaction if idempotency is supported | Transaction ID, reconciliation |
| DNS TTL not yet expired on some clients | Client retries/stale connections handled per design | Output from multiple resolvers/clients |
| Region B lacks quota/compute | Alerts and scaling plan trigger before load shift | Capacity/quota and autoscale logs |
| Simultaneous bad deploy on A and B | Identified as deployment fault rather than single-region outage | Release/feature-flag history |
| External dependency rejects B's IP | Mitigation path and partner contact ready | Egress logs and test results |

### Measuring Outcomes After Drills

Record: fault injection time, detection time, decision time, data promotion time, traffic shift time, smoke-test completion, last replicated data timestamp, latency, retry counts, and user errors.

~~~text
Actual RTO = timestamp when service meets recovery criteria
             - timestamp when outage began

Actual RPO = verified lost data/transaction window
             relative to pre-outage state, expressed in time
~~~

If lost data or the last replicated transaction cannot be verified, record **RPO unmeasured** rather than assuming 0. Call a drill successful only after business transactions pass verification and metrics meet targets.

## 16. Zero-Cost Design Exercise

You can complete this exercise with diagrams and decision tables **without provisioning Azure resources**.

### Prompt

Application **shop.example** has:

- Web and API running in one region, storing carts and orders.
- Azure SQL Database as the transactional data source.
- 10,000 requests/minute at peak, including write operations.
- Hypothetical business targets: **maximum RTO 30 minutes, maximum RPO 5 minutes**.
- Data must stay within regions approved by the organization.
- Customers use a single URL, preferring region A under normal conditions.

### Step 1: Sketch the Proposed Architecture

Show blocks for frontend/API A, frontend/API B, Front Door, primary/secondary databases, health endpoints, DNS/TLS, secrets, logging, workers/queues, and external payments. Use distinct arrows for **web traffic**, **data write paths**, and **replication**.

### Step 2: Select and Justify the Model

A reasonable starting pattern to evaluate is **active-passive warm/hot standby**:

| Decision | Initial choice | Open questions to test |
|---|---|---|
| Global entry | Azure Front Door | Does B receive traffic cleanly when A is unhealthy? |
| Primary region | A, chosen for residency/latency | Are Availability Zones used? |
| Secondary region | B, frontend/API deployed | Are instances/quotas sufficient to absorb A's load? |
| Database | Azure SQL failover group per service capabilities | Do replication lag and forced failover meet RPO? |
| User sessions | Stateless or DR-capable sessions | Are client retries safe after region switch? |
| Health | Readiness reflecting business serving capability | Is B reporting ready before DB promotion dangerous? |
| Region outage | Coordinated runbook with approvers | When is potential data loss accepted? |

This is a **baseline proposal for evaluation**, not a guarantee that an Azure SQL failover group automatically hits a 5-minute RPO or Front Door automatically meets a 30-minute RTO.

### Step 3: Tabletop Walkthrough

Simulate: **at 10:00 region A becomes unreachable**, and database B has unconfirmed replication lag. Document:

1. Which signals distinguish a region outage from a bad deployment?
2. Who is authorized to approve a forced failover with potential data loss?
3. How do you stop A from writing if A partially recovers while B is promoted to primary?
4. In what order do database promotion, B readiness, and Front Door cutover occur?
5. Which business operations verify full recovery?
6. Once A comes back, should you immediately switch traffic back to A?

### Step 4: Deliverable Table

| Item | Deliverable |
|---|---|
| Architecture | Diagram of ingress, compute, A/B data tiers, and dependencies |
| Targets | Chosen RTO/RPO, assumptions, measurement method |
| Procedures | Activation, failover, and failback runbooks |
| Testing | At least 5 test cases from the matrix in section 15 |
| Risks | At least 3 risks: data loss, split-brain, capacity shortfall, DNS caching, etc. |
| Optimization | Ways to reduce standby cost without violating business targets |

### Step 5: Optional Extension If an Authorized Sandbox Is Available

If you have two sample apps without real data, configure Front Door or Traffic Manager with two lab endpoints, observe health probes, and watch routing shift when one backend stops. **Never practice forced database failover on important data** and never induce faults in production without approval.

Services such as Front Door, Traffic Manager, App Service, log storage, and geo-replication **can incur charges**. Check pricing and budgets before provisioning, and delete all lab resources afterward.

## 17. Cost Optimization and Standby Region Capacity

DR creates ongoing costs even when no outage occurs. Typical cost drivers:

- Compute/instances, autoscale, and reserved capacity in B.
- Database replicas, geo-redundant storage, replication, and backups.
- Cross-region data transfer, egress, and networking.
- Azure Front Door/Traffic Manager/cross-region LB usage/SKU fees.
- WAF, log ingestion, retention, monitoring, and synthetic tests.
- Bandwidth, message processing, and third-party APIs during failover.

Do not optimize purely by scaling B down to zero instances if RTO requires immediate readiness. With warm standby, measure **scale-up time and available quota**, VM/SKU provisioning capacity, warm-up duration, and database connection establishment time.

A critical metric is **post-failure capacity after losing one region**. If A and B each run at 70% capacity in active-active, the surviving region may be unable to absorb 100% of traffic during an outage. Designs need headroom, scale plans, rate limiting, and approved degraded modes.

### Graceful Degradation

When B lacks capacity for every feature, prioritize critical transaction paths (login, order lookup, checkout) and temporarily defer non-essential features (heavy reports, product recommendations, batch jobs). This works only when predefined, observable, and safe for data integrity.

## 18. Common Incidents and Isolation

| Symptom | Possible cause | Resolution |
|---|---|---|
| Front Door switched to B, yet users see 500s | B passed simple probes, but DB/secrets/queues are not ready | Inspect real readiness, backend logs, and DB write rights |
| Traffic Manager returns B, yet some users hit A | Resolver/client caching, TTL, or existing connections | Check DNS across networks; plan client retries/reconnects |
| Failover lost recent orders near outage time | Asynchronous geo-replication lagged behind | Reconcile transactions, measure RPO, improve data workflow |
| Users forced to re-login after failover | Unshared session/state or mismatched signing keys | Check session strategy, token/cookie keys, and security policy |
| Both regions reject writes | Unclear primary, wrong endpoint/listener, or writer unpromoted | Check database role, listener, and runbook |
| Conflicting writes after A recovers | Split-brain or multi-write lacking conflict resolution | Fence old writer, assess consistency, and re-sync |
| Failover succeeded, yet webhooks fail | B's egress IP/callback URL/credentials not allowlisted by partner | Check third-party settings and networking |
| B fails to scale as planned | Missing quota/SKU, cold instances, or config limits | Check quotas, capacity reservations, and load tests |
| Web failed over, yet queues stayed in A | Missing messaging DR strategy | Review message replication, replay, and idempotency |
| A recovers, traffic snaps back and drops again | Probe flapping or premature automatic failback | Add stability windows and controlled failback procedures |
| DR drill ran, yet data loss is unknown | Missing audit/reconciliation and replication checkpoints | Add business audit logs, checkpoints, and RPO measurement |

During an incident, log timestamps, region names, chosen origin/endpoint, HTTP status codes, trace IDs, database primary, replication lag, recent changes, and smoke-test results. Do not flip traffic back and forth repeatedly by trial and error without recording state, as doing so can trigger loops or data loss.

## 19. Self-Check Questions

1. How does multi-Availability-Zone HA differ from multi-region DR?
2. How do RTO and RPO measure different things? Why does fast DNS switching not guarantee meeting RTO?
3. When should you choose active-passive over active-active?
4. How does Azure Front Door differ from Azure Traffic Manager in the path of an HTTP request?
5. Why can DNS TTL affect how long it takes users to shift to the standby region?
6. If frontend B returns HTTP 200 while database B is read-only, how should the health endpoint be designed?
7. What causes primary database switching during a region outage to risk data loss?
8. Why can't you assume queues replicate alongside the database?
9. What is split-brain? How do you prevent both regions from writing simultaneously when multi-write is not designed?
10. Why can an active-active system still fail when one region is lost?
11. Which components beyond web/API need failover runbooks?
12. After A recovers, why should traffic not immediately be switched from B back to A?

## 20. References

- [Azure reliability documentation](https://learn.microsoft.com/azure/reliability/) — availability, resiliency, and disaster recovery concepts on Azure.
- [Azure Well-Architected Framework: Reliability](https://learn.microsoft.com/azure/well-architected/reliability/) — designing for recovery targets, failure modes, and testing.
- [Azure Front Door overview](https://learn.microsoft.com/azure/frontdoor/front-door-overview) — global HTTP/HTTPS orchestration.
- [Azure Front Door health probes](https://learn.microsoft.com/azure/frontdoor/health-probes) — origin health checks and backend selection mechanics.
- [Azure Traffic Manager overview](https://learn.microsoft.com/azure/traffic-manager/traffic-manager-overview) — DNS routing and steering methods.
- [Azure SQL Database failover groups](https://learn.microsoft.com/azure/azure-sql/database/failover-group-sql-db) — geo-replication and failover groups for SQL Database.
- [Azure Cosmos DB global distribution](https://learn.microsoft.com/azure/cosmos-db/distribute-data-globally) — multi-region data and write options.
- [Azure Storage redundancy](https://learn.microsoft.com/azure/storage/common/storage-redundancy) — LRS/ZRS/GRS/GZRS and data replication behavior.
- [Azure CLI: Azure Front Door Standard/Premium](https://learn.microsoft.com/cli/azure/afd) — command group for reading and managing Front Door.
- [Azure CLI: Traffic Manager](https://learn.microsoft.com/cli/azure/network/traffic-manager) — managing profiles and endpoints.

**Conclusion:** Multi-region failover is never just adding a second backend and enabling a health probe. A complete DR plan defines **RTO/RPO targets, data state, write ownership, user traffic paths, standby region capacity, and operational runbooks**. Drill every layer, measure real results, and automate only steps with well-understood safety conditions.
