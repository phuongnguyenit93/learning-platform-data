# Rolling Update, Blue–Green, and Canary

Releasing a new version is an operational change that can directly affect availability, latency, data correctness, and user experience. Stopping the entire system to swap versions can result in unacceptable downtime. Routing a new version to all users simultaneously allows a small defect to turn into a widespread incident before teams can detect it.

Rolling update, blue–green, and canary are three deployment strategies that transition versions in different ways. Rolling updates gradually replace instances within the same pool; blue–green maintains two separate environments and switches traffic between them; canary routes a new version to a small slice of traffic or a subset of users before expanding.

In the **CLOUD_ARCHITECTURE** module, this lesson places these strategies in the context of cloud deployment architecture: capacity, load balancing, health checks, sessions, database migrations, observability, rollback, and automation. The goal is to select a release approach aligned with SLOs, data state, compatibility, cost, and the level of risk the organization can accept.

## 1. Why Do We Need a Deployment Strategy?

A deployment does not merely swap a binary or container image. It can simultaneously change:

- Application code and API behavior.
- Runtimes, base images, libraries, or frameworks.
- Database schemas, indexes, and migrations.
- Configuration, feature flags, and secrets.
- Message schemas, event consumers, and background workers.
- Network routes, load balancer targets, and service discovery.
- Cache formats, session state, and static assets.

A new version can start up cleanly yet still be incompatible with older data, messages sitting in queues, or un-updated peer instances. Therefore, a deployment strategy must account for the entire system and the transition window, not just process startup.

### Safe Deployment Goals

1. Minimize or eliminate visible downtime.
2. Limit blast radius when a new version has defects.
3. Detect issues through health and business metrics before full rollout.
4. Maintain a prepared rollback or forward-fix path.
5. Preserve compatibility between old and new versions during transition.
6. Prevent data loss or duplication while requests and jobs are in flight.
7. Capture evidence showing which version served traffic at any point in time.

## 2. Overview of the Three Strategies

| Strategy | How It Deploys | Strengths | Key Trade-Offs |
| --- | --- | --- | --- |
| **Rolling update** | Replaces instances incrementally within one pool | Reuses existing capacity without two full environments | Old and new run concurrently; requires compatibility and surge capacity |
| **Blue–green** | Maintains two environments and switches traffic from blue to green | Fast cutover, relatively clear traffic rollback | Double cost/capacity; database and state must stay compatible |
| **Canary** | Sends a small traffic share to the new version and scales up gradually | Limits blast radius, validates against live traffic | Requires granular routing/metrics and cohort analysis |

No strategy automatically guarantees zero downtime or instant rollback. Outcomes depend on readiness, graceful shutdown, load balancers, sessions/state, data migrations, and dependencies.

~~~mermaid
flowchart TB
    subgraph R["Rolling update"]
      R1["Old instances"] --> R2["Replace a batch"]
      R2 --> R3["Mixed old + new"]
      R3 --> R4["All new"]
    end
    subgraph BG["Blue-green"]
      B1["Blue serves traffic"]
      B2["Green deployed and verified"]
      B1 --> B3["Switch traffic"]
      B2 --> B3
      B3 --> B4["Green serves traffic"]
    end
    subgraph C["Canary"]
      C1["Old version 100%"]
      C2["New version small slice"]
      C3["Increase exposure"]
      C4["New version full traffic"]
      C1 --> C2 --> C3 --> C4
    end
~~~

## 3. Deployment Lifecycle and Instance States

A new instance must pass through several steps before receiving traffic:

1. The artifact is pulled from the registry and provenance/signatures are verified if enabled.
2. The runtime/container starts with the proper config and secrets.
3. Initialization completes and required dependencies become reachable.
4. Readiness checks pass.
5. The load balancer or service discovery adds the instance to the pool.
6. The instance serves traffic while being observed.
7. During replacement, old instances stop receiving new requests.
8. In-flight requests drain within bounded timeouts.
9. Old instances exit cleanly and release resources.

### Liveness, Readiness, and Startup Probes

- **Startup probe:** determines whether an application has finished a slow initialization phase.
- **Readiness probe:** determines whether an instance can accept traffic.
- **Liveness probe:** determines whether a process must be restarted because it is no longer functioning normally.

Readiness and liveness should not blindly use the exact same check. A temporarily slow database might cause readiness to fail so traffic stops flowing, whereas if liveness also fails fleet-wide, the platform could restart every instance and worsen the outage.

### Graceful Shutdown

When an instance is removed from the pool:

- Stop accepting new requests.
- Wait for or finish in-flight requests within a deadline.
- Stop consumers/pollers so no new jobs are picked up.
- Commit/acknowledge messages only upon successful processing according to delivery semantics.
- Close connections, flush metrics/logs, and clean up.
- Exit before the platform's shutdown grace period expires.

Never set the drain timeout shorter than the longest legitimate request unless handoff mechanisms exist. Conversely, unbounded draining stalls deployments.

## 4. How Rolling Updates Work

A rolling update replaces a subset of old instances with new instances across multiple batches. During deployment, both versions can serve traffic concurrently.

~~~mermaid
flowchart LR
    LB["Load balancer"]
    OLD1["Old A"]
    OLD2["Old B"]
    NEW1["New A"]
    NEW2["New B"]
    LB --> OLD1
    LB --> OLD2
    LB --> NEW1
    LB --> NEW2
~~~

The diagram shows the mixed-version phase; the actual ratio of instances shifts batch by batch.

### Parameters to Design

| Parameter | Meaning |
| --- | --- |
| Batch size / max surge | Number of extra new instances created in a batch |
| Max unavailable | Number of instances permitted to be unavailable during rollout |
| Min ready / healthy | Count or percentage of instances that must be healthy before advancing |
| Readiness delay | Time allowed for startup and warm-up |
| Progress deadline | Maximum time allowed for a rollout to make progress |
| Drain / grace period | Time given to old instances to complete in-flight requests |
| Pause / resume | Ability to halt rollout when health gates fail |

Parameter names vary by orchestrator. Understand the exact semantics: some platforms count against desired replicas, while others compute max surge by percentage or absolute count.

### Rolling Update Example

A service runs 10 replicas, rolling out in batches of 2 instances:

1. Maintain sufficient current capacity.
2. Create 2 new instances.
3. Wait for readiness checks to pass and observe health.
4. Drain 2 old instances.
5. Repeat until all 10 instances run the new version.

If each batch requires 30 seconds of warm-up and 20 seconds of bake time, the rollout takes several minutes. That is usually safer than replacing everything at once without observing failures.

### Max Surge and Capacity

If 10 old replicas remain running while 2 new replicas are created, the cluster temporarily needs capacity for 12 replicas—along with corresponding CPU, memory, networking, and quotas. Without headroom, the scheduler may fail to place new pods or the autoscaler may lag in provisioning nodes.

If using `max unavailable`, verify that the remaining instances can handle peak traffic and failure scenarios. Deployments must not remove more instances concurrently than your capacity plan permits.

## 5. Pros and Cons of Rolling Updates

### Pros

- No need to maintain two full stacks for the entire release duration.
- Leverages existing load balancers and orchestrators.
- Rollouts can be automated batch by batch.
- Well-suited to stateless, backward-compatible services.
- Additional resource cost is typically just short-lived surge capacity.

### Cons

- Old and new versions run concurrently, requiring API, schema, cache, and event compatibility.
- Binary rollback cannot undo database migrations that broke compatibility.
- If a defect is detected late, many batches may already have been replaced.
- Requests may hit both versions and exhibit inconsistent behavior.
- Insufficient capacity can stall rollouts or strip production of headroom.

### When It Fits

- Stateless services or externalized state.
- Small, backward-compatible changes.
- Reliable health/readiness probes and metrics.
- High deployment frequency requiring resource efficiency.
- Mixed-version coexistence is acceptable during rollout.

Do not assume rolling updates fit every database migration, incompatible protocol change, or quorum-sensitive stateful system.

## 6. How Blue–Green Deployment Works

Blue–green maintains two environments capable of running the same application:

- **Blue:** the version currently serving production.
- **Green:** the new environment deployed, verified, and staged to receive traffic.

Once green is ready, a load balancer, router, or DNS/service discovery switches traffic from blue to green. Blue is retained for a period so traffic can be switched back if necessary.

~~~mermaid
flowchart TB
    USER["Users"]
    ROUTER["Traffic router"]
    subgraph BLUE["Blue environment"]
      B["Version N"]
    end
    subgraph GREEN["Green environment"]
      G["Version N+1"]
    end
    USER --> ROUTER
    ROUTER -->|Before cutover| B
    ROUTER -.->|After cutover| G
~~~

### Deployment Steps

1. Confirm blue is healthy and capture baseline metrics.
2. Provision green with the new artifact and configuration.
3. Initialize dependencies, secrets, networking, schema-compatible access, and capacity.
4. Run startup/readiness checks, smoke tests, and synthetic transactions.
5. If appropriate, send controlled test traffic to green.
6. Shift production traffic using the defined cutover method.
7. Monitor health, business metrics, error rates, and data correctness.
8. Retain blue for the bake and rollback window.
9. Decommission blue only after rollback conditions expire and approval is granted.

### Cutover

Cutover can use load balancer target switches, service selectors, ingress routes, service meshes, or DNS. Each mechanism has distinct convergence times and failure modes. DNS switching can suffer from TTLs and resolver caching; load balancer switching is faster, though existing connections still need draining.

### Rollback

If green malfunctions, switch traffic back to blue. This is fast when:

- Blue is still running and able to accept traffic.
- Database and API contracts remain compatible with both versions.
- Green has not written data in schemas or semantics that blue cannot parse.
- Sessions, caches, and events are not in a green-only state.
- The router can switch back and connections are handled safely.

Blue–green does not provide safe rollback if green has executed destructive migrations or written data the old version cannot process.

## 7. Pros and Cons of Blue–Green

### Pros

- Allows testing the new environment before shifting real users.
- Clean traffic cutover with a direct path back to the prior environment.
- Minimizes mixed-version execution within the same instance pool.
- Can reduce deployment risk for large services when both environments are isolated.
- Supports smoke and synthetic testing on green before production cutover.

### Cons

- May require nearly double the compute and network capacity while both environments coexist.
- The data layer is typically shared, so environments are not completely independent.
- Secrets, certificates, DNS, sessions, caches, and queues must be coordinated across both environments.
- Cutover does not terminate open connections or undo already-emitted side effects.
- Configuration or dependencies between the two environments can drift.

### When It Fits

- Services needing rapid cutover and able to run two environments.
- Higher-risk releases requiring validation before live traffic exposure.
- Infrastructure that can be provisioned in parallel.
- Data-compatible contracts and established rollback procedures.
- Workloads suited to traffic switching at the routing layer.

Blue–green works especially well for stateless web/API tiers; workers, schedulers, and database migrations require additional planning.

## 8. How Canary Deployment Works

Canary exposes a new version to a small slice of users or traffic, observes outcomes, and increases exposure incrementally. Canary traffic can be routed by request percentage, tenant, region, user cohort, or headers/feature flags.

~~~mermaid
flowchart LR
    CLIENT["Production traffic"]
    ROUTER["Traffic splitter"]
    OLD["Stable version"]
    NEW["Canary version"]
    METRIC["Compare SLI/business metrics"]
    CLIENT --> ROUTER
    ROUTER -->|95%| OLD
    ROUTER -->|5%| NEW
    OLD --> METRIC
    NEW --> METRIC
~~~

The 95/5 split is purely illustrative. With selective tenants or cohorts, request share may not correspond to customer count, transaction value, or risk exposure.

### Canary Steps

1. Establish a baseline for the stable version.
2. Deploy the canary with minimal capacity.
3. Select a representative, controllable cohort or traffic slice.
4. Shift a small fraction of traffic.
5. Observe health, SLIs, business outcomes, and version-tagged telemetry.
6. Maintain enough bake time to cover cyclical workload behavior.
7. Increase exposure if guardrails pass; pause or roll back if violated.
8. Repeat until the canary serves 100% of traffic.
9. Finalize the rollout and retire stable per the rollback policy.

### Progressive Delivery Example

| Stage | Traffic to Canary | Criteria to Proceed |
| --- | ---: | --- |
| Initial | 1% | Readiness and synthetic checks pass; no critical errors |
| Small cohort | 5% | Error/latency no worse than baseline beyond threshold |
| Expansion | 20% | Business conversion and data correctness remain stable |
| Broad | 50% | No SLO violations; sufficient capacity |
| Full | 100% | Bake time complete; owner confirms |

Numeric thresholds must reflect SLOs, traffic volume, and risk. At 1% traffic, request volume may be too low for statistical significance; enforce a minimum sample size and observation window.

## 9. Pros and Cons of Canary

### Pros

- Bounds blast radius when defects occur.
- Measures impact on real production traffic and live dependencies.
- Combines business metrics with technical SLIs.
- Supports pausing before all customers are affected.
- Detects differences across regions, tenant tiers, or client versions.

### Cons

- Requires version/cohort-aware traffic routing and telemetry.
- Analysis can be skewed if the cohort is unrepresentative.
- Rare bugs or load-induced failures may not surface in a small canary.
- Old and new versions coexist, still requiring backward compatibility.
- Increases complexity in feature flags, routing, and data attribution.

### When It Fits

- Workloads with enough traffic volume for meaningful observation.
- Risky changes requiring progressive validation.
- Ability to route by percentage or cohort.
- Availability of SLIs and business metrics comparing stable vs. canary.
- Ability to pause or auto-roll back safely.

## 10. Traffic, Tenant, and Cohort Canaries

Not every canary splits random request percentages.

| Method | Characteristics | Risks to Watch |
| --- | --- | --- |
| Random traffic percentage | Randomly selects a percentage of requests | A single user may hit both versions |
| Sticky user/session | Pins a user or session to one version | Session affinity and load skew |
| Tenant cohort | Selects specific tenants | Selected tenants may not be representative |
| Region/AZ cohort | Enables one region or failure domain | Network and data locality differences |
| Header/client cohort | Routes by header, app version, or integration | Headers must be authenticated; skewed client distribution |
| Feature flag | Enables new behavior for selected groups | Old and new code paths coexist longer |

### Selecting a Cohort

A strong cohort must:

- Represent critical workload patterns and data shapes.
- Be selected via clear, reproducible criteria.
- Not accidentally consist solely of internal or trivial test traffic.
- Have a bounded maximum impact.
- Be identifiable in logs and metrics without leaking PII.

### Tenant Canaries

Tenant-based canaries work well in SaaS when pilot or internal tenants understand the risk. However, pilot tenants may have smaller datasets, fewer integrations, or atypical usage patterns. Supplement with synthetic and representative load tests; never extrapolate fleet-wide safety from a single atypical tenant.

### Per-Request or Per-User?

If one user makes multiple requests, random per-request routing can cause the same session to bounce between versions, producing UI/API inconsistencies and debugging difficulty. Sticky per-user or per-tenant assignment maintains consistency, though it can skew load distribution. Choose based on workload semantics.

## 11. Backward Compatibility During Mixed-Version Windows

Rolling updates and canaries create windows where old and new versions coexist. Blue–green also frequently involves both versions accessing shared databases or services. During transition, every component must handle data and protocols produced by the other version.

### Compatibility Layers

- **API compatibility:** fields, status codes, validation, pagination, and error semantics.
- **Database compatibility:** old versions can still read and write the new schema during rollout.
- **Event compatibility:** producers and consumers accept both old and new message versions.
- **Cache compatibility:** serialization formats and key namespaces do not break old instances.
- **Session compatibility:** sessions or tokens issued by the new version remain readable by the old version.
- **Configuration compatibility:** new configs do not crash old binaries upon rollback.
- **Static asset compatibility:** HTML, JS, and APIs may skew across browser/CDN caches.

### Rules for Safe Changes

Prefer additive changes:

- Add optional fields instead of altering the meaning of existing ones.
- Consumers should ignore unknown fields when contracts permit.
- Producers should emit new fields only after consumers are ready.
- Retain old endpoints and formats during the migration window.
- Remove deprecated fields in a later release once no consumers remain.
- Maintain schema versioning and compatibility tests.

Never silently change the semantics of enums, statuses, or units while reusing the same field name if old consumers cannot distinguish them.

## 12. Database Migrations: Expand–Migrate–Contract

The database is often what makes application rollback difficult. Running a destructive migration alongside a deployment can render the old version inoperable.

The expand–migrate–contract strategy splits schema changes into phases:

~~~mermaid
flowchart LR
    E["Expand\nAdd compatible schema"]
    M["Migrate\nDual-read/write or backfill"]
    V["Verify\nCompare data and consumers"]
    C["Contract\nRemove obsolete schema later"]
    E --> M --> V --> C
~~~

### Example: Renaming Column `customer_name` to `display_name`

**Release A — Expand**

- Add a nullable `display_name` column.
- Keep `customer_name`.
- New code reads `display_name` if present, falling back to `customer_name`.
- Write paths may dual-write both columns during transition.

**Backfill**

- Copy data from `customer_name` to `display_name` in batches.
- Monitor progress, errors, and concurrent writes.
- Reconcile row counts, checksums, or business rules.

**Release B — Migrate**

- New consumers read `display_name`.
- Producers write `display_name`; dual-writing may continue for compatibility during the rollback window.
- Verify no readers depend solely on the old schema.

**Release C — Contract**

- After the rollback window closes and no old consumers remain, drop `customer_name`.
- Execute destructive cleanup as a separate, reviewed change.

### Controlling Backfills

- Batch sizes, rate limits, and execution schedules.
- Lock duration and impact on production queries.
- Retries, idempotency, and checkpoints.
- Handling records created or updated concurrently.
- Post-backfill reconciliation.
- Pause, resume, and abort capabilities.

Never run a full-table update migration on a large table during peak hours without measuring locks, I/O, replication lag, and workload impact.

### Migration Rollback

Not all migrations are reversible. Destructive changes typically require forward-compatible code, backup/recovery plans, and delayed contraction. A "deployment rollback" only swaps binaries; it does not automatically restore altered schemas or data.

## 13. Event Schemas, Queues, and Consumer Compatibility

In event-driven systems, producers and consumers may deploy at different times. Old consumers may encounter messages sitting in queues; new events may be replayed from retention.

Core principles:

- Versioned schema evolution with compatibility rules.
- Add optional fields with clear default semantics.
- Consumers tolerate unknown fields when appropriate.
- Never silently redefine existing fields.
- Consumers must parse historical events across the entire retention and replay window.
- Dead-letter and replay paths must also support both old and new schemas.

### Producer-First or Consumer-First?

Ordering depends on the change type:

- When adding a new field, deploy consumers that understand it first, then have producers emit it.
- When removing an old field, stop emitting it once consumers no longer need it, then remove reader logic.
- For new event types, deploy consumers first (ignoring or no-oping) before enabling producers.

### Event Schema Registries

A schema registry can enforce compatibility when producers register schemas. However, registries only protect declared syntax/contracts; consumers must still test business semantics, optional/null/default handling, and replay behavior. A syntactically valid schema can still alter business outcomes.

## 14. Caches, Sessions, and Static Assets During Rollout

### Cache Formats

If a new version serializes objects in an incompatible format, old instances may fail to read new cache entries. Options include:

- Version key namespaces, e.g., `cache:v2:...`.
- Tolerate cache misses and rebuild when data is regenerable.
- Dual-read/dual-write briefly during transition.
- Use serialization formats that support schema evolution.
- Maintain TTLs for old keys through the rollback window.

Avoid flushing the entire cache during a rollout if cold-cache rebuilds would overload the database.

### Sessions

Sessions may live in shared stores or instance memory. In-memory sessions force sticky routing and hinder failover. Shared sessions require schema compatibility, encryption, and TTLs. Logout and revocation must apply across both versions.

### Static Assets and CDNs

Old HTML can reference new JS bundles or vice versa. Use content-hashed asset filenames, retain prior assets across cache windows, and deploy in compatible order. Never delete old bundles immediately at cutover while browsers hold cached HTML.

### Feature Flags

Feature flags decouple code deployment from feature activation. Ensure:

- Clear owners and purposes.
- Default off for unready capabilities.
- Targeting based on authenticated tenant/cohort identities.
- Tested kill switches with access controls.
- Metrics segmented by flag and version.
- Expiration and cleanup dates to avoid permanent dead flags.

Feature flags do not replace rollout strategies; they control behavior within running versions.

## 15. Stateful Workloads and Deployment Strategies

Stateful workloads are harder to deploy than stateless ones because instances may own local storage, partitions, leadership roles, or quorum membership.

### Databases and Clustered Stateful Services

- Check quorum before replacing nodes.
- Replace followers/replicas before leaders when the protocol permits.
- Wait for replication catch-up and verify health.
- Never replace more nodes concurrently than the disruption budget allows.
- Enforce fencing to prevent split-brain dual-leader writes.
- Verify backups and recovery before destructive upgrades.
- Follow vendor-supported version upgrade paths.

### Queue Consumers

Rolling updates must handle old and new consumers reading the same queue concurrently. Stop old consumers from pulling new messages, wait for in-flight messages to finish or requeue per semantics, and enforce idempotency to prevent duplicates during mid-flight shutdowns.

### Scheduled Jobs and Singleton Tasks

If two versions run schedulers concurrently, duplicate jobs may fire. Use distributed locks/leases, leader election, or external schedulers; jobs require idempotency and version-aware state. During blue–green switches, only one environment should run the authoritative scheduler at a time unless jobs are designed for concurrent execution.

### Graceful Draining

Draining must account for long-lived connections, WebSockets, streaming requests, consumer leases, and in-flight transactions. A single fixed drain timeout rarely suits every workload; tune it per service class and deadline.

## 16. Health Gates and Metrics for Advancing Rollouts

Do not advance a rollout merely because new instances report `Ready`. Combine platform health, service SLIs, and business outcomes.

### Technical Signals

- Startup/readiness success and restart counts.
- HTTP/gRPC error rates, timeouts, and retry rates.
- p50/p95/p99 latencies.
- CPU, memory, GC pauses, and thread/connection pool usage.
- Queue depth, oldest message age, and consumer lag.
- Database connections, lock waits, and replication lag.
- Dependency latency and error rates.
- Crash loops, OOMs, throttling, and network errors.

### Business Signals

- Booking and payment success rates.
- Checkout abandonment or transaction conflict rates.
- Duplicate invoice/job counts.
- Inventory correctness and data reconciliation.
- Login and authorization failure rates.
- Customer support contacts or synthetic journey failures.

A new version can return HTTP 200 cleanly while creating corrupted bookings or duplicate payments. Business metrics belong in deployment gates at an appropriate level.

### Comparing Canary Against Baseline

| Dimension | Stable | Canary | Interpretation |
| --- | --- | --- | --- |
| Error rate | 0.3% | 1.8% | Canary likely regressed |
| p99 latency | 420 ms | 900 ms | Tail latency degraded |
| CPU | 55% | 62% | Slight increase, inconclusive alone |
| Booking success | 99.7% | 98.1% | Business outcome declined |
| Payment duplicates | 0 | 3 | Critical guardrail breach; halt and investigate |

Numbers are illustrative. Always compare within matching cohorts, regions, time windows, traffic mixes, and request types; otherwise, load differences can skew conclusions.

### Guardrails and Automated Analysis

Each rollout step can evaluate into:

- **Continue:** all critical guardrails pass and minimum sample size is met.
- **Pause:** insufficient data or unstable metrics.
- **Abort/rollback:** pre-defined critical threshold breached.
- **Manual review:** conflicting signals or business risks requiring owner judgment.

Avoid relying solely on opaque composite scores. Log the exact reasoning behind automated proceed or halt decisions.

## 17. Bake Time and Sample Size

Bake time is the observation window at a given exposure level before expanding further. It must be long enough to cover representative workloads and allow probabilistic defects to surface.

### Determining Factors

- Traffic volume and actual request counts.
- Diurnal or batch traffic cycles.
- Hourly, daily, or weekly scheduled tasks.
- Long user sessions or multi-step journeys.
- Event/queue processing latency and eventual consistency delays.
- Frequency of rare but critical transactions.

A 5% canary lasting two minutes will miss bugs triggered only during nightly batch runs. Conversely, hours of bake time under near-zero traffic still yields an inadequate sample.

### Minimum Sample Size

Define a minimum request or transaction count before evaluating error rates. If a canary receives too little traffic, do not conclude "zero errors" merely because none were observed yet. Supplement with synthetic and targeted tests, though they do not fully replace live production data.

### Sequential Rollouts

Each stage should log:

- Exposure percentage.
- Start and end timestamps.
- Sample count.
- Guardrail results.
- Human or automated decision-maker.
- Dependency and capacity status.

This allows reconstructing why a rollout advanced or halted.

## 18. Rollback, Roll-Forward, and Feature Disable

Rollback restores a prior state or version. Roll-forward releases a new fix forward. Feature disable turns off a capability without necessarily swapping binaries.

| Mechanism | When to Use | Conditions |
| --- | --- | --- |
| Traffic rollback | New version fails while old version remains compatible | Router can switch back; data/schema compatibility intact |
| Binary rollback | Prior artifact still runs against current schema and config | Old binary is backward-compatible |
| Roll-forward | Fix needed urgently or migration is irreversible | Tested patch and safe rollout path exist |
| Feature kill switch | One specific feature causes errors | Flag has safe semantics and fast propagation |
| Restore | Data is corrupted or lost | Valid recovery point, RPO, and integrity checks |

### Rollback Readiness

Before deploying, confirm:

- Where is the prior artifact/version, and can it be redeployed?
- Are current configs and secrets compatible with the old version?
- Are database migrations backward-compatible?
- Can event, cache, and session formats still be read?
- Have any irreversible side effects occurred?
- How will traffic routing and connection draining behave?
- Who authorizes rollback, and is approval required?

### Rollback Is Not an Undo Button for Everything

A processed payment cannot be reversed by rolling back an application binary. A sent email cannot be "unsent" via deployment. Distinguish software state from business side effects; handle business state with separate reconciliation or compensating actions.

### When Roll-Forward Is Safer

After expanding a schema and writing new data, rolling back binaries can be harder than shipping a compatible patch. Decide based on data state, not the assumption that "rollback is always best."

## 19. Traffic Shifting and Connection Behavior

Traffic routing may use load balancers, ingress controllers, service meshes, API gateways, DNS, or application-level routers.

### Traffic Shifting Patterns

- Percentage-based weighted routing.
- Header or cookie routing.
- User or tenant cohorts.
- Region or AZ routing.
- Blue–green target switches.
- In-application feature routing.

### Long-Lived Connections

WebSockets, gRPC streams, HTTP/2, and persistent TCP connections may outlive routing rule changes. Routers often apply new rules only to new connections while existing connections stay pinned to old backends. Define:

- Drain timeouts.
- Maximum connection age.
- Graceful GOAWAY/close semantics where supported by the protocol.
- Sticky session behavior.
- Client reconnect and retry policies.
- Mitigations against reconnect storms during cutover.

### DNS and Caching

DNS TTLs do not guarantee all clients switch endpoints on schedule. Resolvers and caches may honor records longer, or persistent connections may linger. For blue–green, never assume DNS cutover is instantaneous; measure propagation and maintain health checks and rollback plans.

### Weighted Routing Does Not Guarantee Equal User Proportions

If certain customers generate disproportionate traffic, 5% of requests does not equal 5% of users or tenants. When choosing exposure levels, align the metric to your goal: request volume, tenant count, revenue/transactions, data sensitivity, or risk cohort.

## 20. Security and Supply Chain in Deployment

Deployment is the moment new artifacts, configurations, and identities enter production. A safe rollout must verify both what is deployed and what permissions it receives.

### Artifact Integrity

- Build from controlled pipelines and repositories.
- Scan dependencies and container images per policy.
- Pin versions/digests instead of mutable tags for production.
- Sign artifacts and verify signatures/provenance where supported.
- Maintain SBOMs or dependency inventories as required.
- Restrict registry push/pull rights and audit publishes.

### Secrets and Identity

- Use workload identity and secret managers instead of hard-coded secrets.
- Grant least-privilege permissions to the new version.
- Verify secret/certificate rotation compatibility across old and new versions.
- Avoid logging secrets in startup or config dumps.
- Maintain revocation procedures if an artifact or credential is compromised.

### IaC and Configuration

Blue and green infrastructure can drift. Manage infrastructure and configs from a single source of truth, enforce policy reviews, and detect drift. Deployments should bind artifact versions to config/manifest versions so you know the exact combination serving traffic.

### Progressive Delivery and Security Gates

Canaries can limit blast radius if a new release has a vulnerability or misconfigured permission, but they do not replace security reviews. Never rely on a canary to catch secret leaks or privilege escalations; enforce static/dynamic scanning, policy gates, and approvals before production.

## 21. Automating Deployments with Pipelines and Progressive Delivery

CI/CD pipelines turn releases into repeatable, verifiable steps. Progressive delivery adds metric- and health-driven exposure control instead of immediately shifting 100% of traffic upon deploy completion.

~~~mermaid
flowchart TD
    SRC["Source commit"]
    BUILD["Build + unit/integration tests"]
    SEC["Scan + sign artifact"]
    STAGE["Deploy staging"]
    TEST["Smoke + contract + load checks"]
    PROD["Deploy production candidate"]
    CANARY["Canary / blue-green / rolling"]
    GATE{"Health and business gates pass?"}
    EXPAND["Expand traffic / finish rollout"]
    PAUSE["Pause / abort / rollback"]
    SRC --> BUILD --> SEC --> STAGE --> TEST --> PROD --> CANARY --> GATE
    GATE -->|Yes| EXPAND
    GATE -->|No| PAUSE
~~~

### Pipeline Stages

1. **Build:** create an immutable artifact from the source commit.
2. **Verify:** run unit, integration, contract, and security tests.
3. **Package:** attach digest, version, and metadata to the image/artifact.
4. **Deploy candidate:** deploy to staging or a low-exposure production pool.
5. **Validate:** run startup/readiness, smoke, synthetic, and dependency checks.
6. **Progressive exposure:** execute rolling batches, blue–green cutover, or canary percentages.
7. **Analyze:** evaluate SLIs, business guardrails, and sample sizes.
8. **Promote or abort:** advance, pause, roll back, or roll forward per policy.
9. **Finalize:** log the deployment record and schedule cleanup after the rollback window.

### Deployment Metadata

Link every release to its source commit/build ID, artifact digest/signature, config/IaC version, database migration version, feature flag state, deployment strategy, batch/exposure history, start/end times, approvals, and health gate decisions. Metadata connects incidents to exact versions and configs rather than vague "we just deployed" guesses.

### Automation Must Not Hide Decisions

When auto-promotion occurs, record the metrics and rules satisfied. When auto-rollback triggers, log the cause, threshold, timestamp, and target version. Provide audited pause and manual override controls so automation cannot advance blindly past an unmodeled anomaly.

## 22. Canary Analysis and Statistical Comparison

Canary analysis compares the new version against the stable baseline under equivalent conditions. Do not inspect raw values alone; evaluate baselines, variance, and sample sizes.

### Apples-to-Apples Comparisons

- Same region or normalized for regional differences.
- Same endpoints and request classes.
- Same tenant tiers or client versions when traffic varies by segment.
- Same time windows and peak/off-peak profiles.
- Exclude non-representative internal test traffic.
- Monitor dependencies and downstream side effects too.

### Absolute vs. Relative Thresholds

An absolute threshold might require error rates below 1%; a relative threshold might forbid the canary from degrading more than 0.2 percentage points over stable. Both can be necessary: if stable is already degraded, "no worse than stable" is insufficient to justify advancing.

### Guardrails Matter More Than Averages

A rare, high-impact bug—such as double charging or cross-tenant data leakage—may barely shift overall error rates. Enforce explicit invariant and security guardrails and halt immediately upon any violation.

### Correlation Does Not Prove Causation

A higher canary error rate might stem from a different traffic mix rather than the code version. Check cohorts, request types, regions, and dependencies before drawing conclusions. Still, when severe risk appears, pause exposure first and investigate; do not wait for root cause before limiting blast radius.

## 23. Multi-Region and Multi-Tenant Deployments

In multi-region or multi-tenant architectures, rollouts can be segmented by failure domain or cohort to contain impact.

### Region-First Rollouts

1. Select a pilot region with representative traffic and spare capacity.
2. Deploy the new version to the pilot region.
3. Run synthetic/business transactions and inspect replication and dependencies.
4. Increase traffic/canary exposure within the region.
5. Roll out remaining regions in waves.
6. Monitor the global control plane and data consistency.

Choose the first region based on risk and recovery capability—not blindly the lowest-traffic region if it is unrepresentative.

### Tenant Cohort Rollouts

Segment tenants by tier, region, integrations, or usage profiles. Pilot tenants need owners, clear communication, and opt-out or rollback plans. Feature flag evaluation and routing must rely on authenticated canonical tenant identities.

### Shared Control Planes

If a deployment controller or flag service is globally shared, a control-plane bug can impact all regions. Staged rollouts may be needed for the control plane itself, alongside fail-safe modes so the data plane does not lock up if control-plane connectivity drops temporarily.

### Data Residency and Deployment

Canaries and blue–green tests must never inadvertently copy production data across regions for testing. Use synthetic or approved datasets, and ensure backups, logs, and telemetry obey data residency policies.

## 24. Rollouts Across Frontends, APIs, and Mobile Clients

Client tiers update asynchronously. Backends may deploy new versions while older browsers and mobile apps stay active for weeks.

### API Evolution

- Make additive changes and keep old endpoints active during a compatibility window.
- Version APIs explicitly when semantics change significantly.
- Monitor client versions and endpoint usage before retiring old paths.
- Never require all clients to upgrade simultaneously.

### Frontend / CDN

- Use content-hashed filenames and immutable caching for versioned assets.
- Update HTML/app shells alongside release metadata.
- Retain old assets long enough for cached browsers and active sessions.
- Test service worker updates and rollbacks; stale service workers can keep serving outdated bundles.

### Mobile

- App store approvals and user adoption slow down client upgrades.
- Backends must support `N` and `N-1` (or a defined compatibility window).
- Minimum supported versions may be enforced with clear communication and fallbacks.
- Remote feature flags can disable faulty capabilities without waiting for a new client release.

### Contract Testing

Test providers against multiple consumer versions using historical API and event fixtures. Contract tests catch breaking changes before release, though they do not replace integration or E2E testing for business workflows.

## 25. Choosing a Strategy by Scenario

| Scenario | Typically Appropriate Strategy | Additional Conditions |
| --- | --- | --- |
| Stateless API, additive code/schema | Rolling update | Readiness, draining, compatibility |
| Needs fast cutover and traffic rollback | Blue–green | Two environments, shared-data safety |
| High-risk business logic, high traffic | Canary | Granular metrics, cohorts, bake time |
| Database engine / stateful cluster | Vendor-protocol rolling upgrade | Quorum, replication, upgrade path |
| Frontend asset + API changes | Rolling/blue–green with versioned assets | Client compatibility window |
| Multi-tenant SaaS with pilot group | Tenant canary | Identity-based routing, tenant owner |
| Infrequent release, low traffic | Blue–green or staged rollout | Synthetic tests and manual review |
| Destructive schema changes | Expand–migrate–contract, split releases | Backfill, validation, delayed contraction |

### Decision Flow

1. Can old and new versions safely run concurrently? If not, migrate protocols or data first.
2. Is capacity available for two environments? If yes and clean cutover is desired, consider blue–green.
3. Are traffic and metrics rich enough to evaluate cohorts? If yes, consider canary.
4. Is the service stateless with small changes needing resource efficiency? Rolling update usually fits.
5. Is it a stateful, quorum, or database workload? Follow dedicated upgrade procedures and verify consistency.
6. Are there destructive data changes? Design expand–migrate–contract before choosing a traffic strategy.

## 26. Case Study: Deploying the Booking API via Rolling Update

A Booking API runs 12 replicas across three AZs. The new release adds an optional response field, optimizes a query, and changes log formatting. Backward compatibility is preserved; there are no destructive database migrations.

### Rollout Design

- `maxSurge`: 2 replicas.
- `maxUnavailable`: 1 replica.
- Maximum 2 instances per batch.
- Readiness passes only after configuration and connection pools initialize.
- Drain in-flight requests before terminating old instances.
- 5-minute bake time between batches (assuming sufficient traffic).

### Health Gates

- Error rate does not rise past threshold relative to baseline.
- p99 latency stays within SLO.
- DB connections, CPU, and replication lag remain within bounds.
- Booking creation success rates and duplicate counts stay normal.
- No increase in restarts or OOMs.

### Rollback

If the optimized query spikes latency, pause the rollout and roll back the binary to the previous version. Because schema changes were additive and non-destructive, the old version continues working. Any newly added index is retained until confirmed unused—never drop indexes hastily mid-incident.

### What to Record

Deployment records log each batch, instance IDs, versions, readiness timestamps, metric gate evaluations, and decisions. On-call engineers immediately know which slice of the fleet is updated.

## 27. Case Study: Blue–Green for a Payment API

A Payment API is upgrading its runtime and internal architecture and wants a fast cutover. The team provisions an isolated green environment, runs contract and synthetic tests against a sandbox provider, and shifts traffic incrementally.

### Data Contract

Blue and green share the payment ledger/database. Migrations are strictly additive; green avoids writing fields that blue cannot understand during the rollback window. Provider idempotency keys remain consistent across payment operations.

### Cutover

1. Provision green with dedicated capacity and secrets.
2. Verify readiness, egress networking, certificates, KMS access, and provider connectivity.
3. Run synthetic authorize/capture/void flows in sandbox; production probes use only approved, reconciled test transactions.
4. Shift a partial slice of traffic at the router if business and consistency rules allow.
5. Observe payment successes, declines, timeouts, duplicates, and reconciliation.
6. Shift remaining traffic once guardrails pass.
7. Retain blue until the rollback window closes.

### Rollback Safety

If green errors occur, switch traffic back to blue. Payment operations already committed at the provider must never be retried under a new idempotency key; query provider state using the provider reference. Both versions must handle pending/unknown states and the ledger format.

Blue–green reduces code cutover risk, but it does not isolate transactions from external payment providers; idempotency and reconciliation remain mandatory.

## 28. Case Study: Tenant-Based Canary for Multi-Tenant SaaS

A SaaS platform introduces a new invoice export workflow. Tenants vary widely in scale and integrations; bugs may surface only for tenants with millions of invoices or custom policies.

### Cohort Selection

- Internal cohort using synthetic datasets.
- One medium-volume pilot tenant with explicit owner consent.
- One high-volume tenant after batching and limits are validated.
- Expand by tier and region rather than raw tenant count alone.

### Routing and Guardrails

Feature flags evaluate against authenticated canonical tenant identities, never arbitrary request headers. Metrics break down by version and tenant tier while avoiding unbounded label cardinality. Guardrails track export success, completion time, file correctness, storage cost, and cross-tenant isolation tests.

### Pause and Rollback

If an export file is corrupt or contains another tenant's records, immediately disable the flag, halt new workers, quarantine generated outputs, preserve evidence, and trigger security/privacy review per protocol. Never just route back to old code and ignore already-generated files; lock down output access per storage semantics.

## 29. Common Mistakes

1. **Treating `Ready` as sufficient to promote:** instances can pass platform probes while failing business transactions.
2. **Rolling too many instances simultaneously:** remaining capacity drops too low or quorum breaks.
3. **Ignoring `maxSurge` headroom:** clusters run out of CPU, memory, or quotas when spinning up new instances.
4. **Improper draining:** long-running requests, WebSockets, or in-flight messages get severed.
5. **Non-backward-compatible old/new versions:** deployment succeeds while requests across mixed versions produce inconsistent results.
6. **Coupling destructive DB migrations with releases:** binary rollback cannot restore changed schemas or data.
7. **Blue–green switching only the router:** schedulers/workers in both environments execute duplicate jobs and side effects.
8. **Deleting blue too early:** losing traffic rollback capability when defects surface after initial bake time.
9. **Assuming DNS cutover is instantaneous:** resolvers and persistent connections continue hitting the old endpoint.
10. **Unrepresentative canary cohorts:** testing only light internal traffic misses high-volume tenants or peak loads.
11. **Tiny canary samples:** insufficient data to evaluate error rates reliably.
12. **Measuring only averages:** hiding p99 spikes, duplicate transactions, or data corruption.
13. **Not tagging telemetry by version:** inability to tell whether errors come from stable or canary.
14. **Zero minimum bake time:** cyclical bugs appear only after 100% promotion.
15. **Never cleaning up feature flags:** old and new code paths accumulate, inflating complexity.
16. **Ignoring side effects during rollback:** committed payments, emails, or events do not automatically undo.
17. **Deleting old static assets immediately:** cached HTML/service workers break against missing JS bundles.
18. **Not testing `N-1` clients:** legacy mobile apps and integrations continue running post-release.
19. **Advancing rollouts while dependencies are degraded:** downstream errors get masked by retries or misattributed.
20. **Missing deployment metadata:** incidents cannot be traced back to the exact artifact and config.

## 30. Deployment Strategy Review Checklist

- Does the strategy fit the stateful/stateless nature and risk profile of the change?
- Are old/new version coexistence and compatibility windows explicitly defined?
- Are readiness, liveness, startup probes, and graceful drain properly separated?
- Are `maxSurge` / `maxUnavailable` sized against capacity, quotas, and failure domains?
- Do load balancers and traffic routers include health gates and rollback paths?
- Have DNS TTLs, long-lived connections, sticky sessions, and reconnect storms been addressed?
- Do database migrations follow expand–migrate–contract when needed?
- Are event producers, consumers, and queue replays schema-compatible?
- Do caches, sessions, and static assets have versioning and migration plans?
- How are workers and schedulers prevented from duplicating work across two environments?
- Are canary cohorts and minimum sample sizes representative?
- Is bake time long enough to span traffic, cron, and queue cycles?
- Do technical and business guardrails compare stable vs. canary under matching conditions?
- Are auto-pause/abort, manual overrides, and decision evidence in place?
- Do rollback, roll-forward, and feature disable paths have clear owners and stop conditions?
- Do business side effects enforce idempotency and reconciliation?
- Have artifact provenance, signatures, scans, secrets, and least privilege been verified?
- Do multi-region and multi-tenant rollouts bound blast radius and preserve data residency?
- Do deployment records bind commits, artifacts, configs, migrations, flags, and approvals?
- Are incident/rollback runbooks and post-deploy monitoring ready?

## 31. Post-Deployment Metrics to Monitor

| Group | Metrics |
| --- | --- |
| Deployment progress | Instances updated, rollout duration, batch status, pause/failure counts |
| Availability | Success rate, readiness failures, restarts/crash loops |
| Latency | p50/p95/p99 by version and cohort |
| Correctness | Business success, duplicates, invariant violations, reconciliation |
| Capacity | CPU, memory, network, connection/pool usage, autoscaler activity |
| Dependencies | DB latency/replication lag, cache hit rate, queue lag, external APIs |
| Traffic | Request volume, cohort exposure, region/tenant distribution |
| Recovery | Rollback count/time, time to mitigate, late completions |
| Cost | Surge capacity, dual-environment hours, data transfer, idle resources |
| Security | Artifact signature/provenance status, policy violations, access anomalies |

### Deployment Frequency and Change Failure Rate

Deployment frequency measures delivery cadence; change failure rate tracks the percentage of deployments causing incidents, rollbacks, or hotfixes as defined by the organization; lead time for changes and time to restore round out delivery flow and reliability. Never optimize one metric in isolation: increasing deployment frequency at the cost of severe failures degrades overall outcomes.

### Before/After Comparisons

Capture a pre-deployment baseline segmented by version and time. Note any shifts in traffic mix, region, or dependency health to avoid false conclusions. After each rollout, archive results in the deployment record and recalibrate thresholds if alerts prove overly noisy or miss real regressions.

## 32. Hands-On Exercise and Guided Answers

A booking service runs 8 replicas across two AZs. The new release changes an API response, adds a database column, and alters message processing logic. The team proposes a 10% canary for 2 minutes followed by full rollout. The system has older mobile clients, a queue with 24-hour message retention, and scheduled worker jobs.

### Question 1 — Is a 10% canary for 2 minutes sufficient?

**Guided Answer:** Not enough information to conclude yes, and likely insufficient. You must evaluate traffic volume, minimum sample size, peak profiles, batch/queue cycles, and rare edge cases. Two minutes will miss scheduled jobs and replayed events; bake time must reflect actual workload cycles.

### Question 2 — Can we change the API response and deploy immediately?

**Guided Answer:** Check `N-1` mobile clients and external integrations first. Prefer additive fields and preserve existing semantics; if breaking changes are unavoidable, version the API or maintain a compatibility window. Run contract tests against older consumer fixtures.

### Question 3 — Can the migration adding a column run beforehand?

**Guided Answer:** If additive and backward-compatible, yes—expand the schema before the application release. Backfill in batches and verify; contract/drop old columns only after the rollback window closes and no consumers remain.

### Question 4 — How does the 24-hour queue retention affect rollout?

**Guided Answer:** New consumers must handle older event formats across the full retention and replay window. Maintain schema compatibility or build upcasters/adapters; test DLQ replays and out-of-order events.

### Question 5 — Can the scheduler run on both old and new versions?

**Guided Answer:** Only if jobs are idempotent and protected by distributed locks/leases to avoid duplicate execution. Otherwise, only one environment or elected leader should run scheduled jobs during cutover.

### Question 6 — What capacity must the rolling update account for?

**Guided Answer:** With 8 replicas, `maxSurge` and `maxUnavailable` determine concurrent instance counts. Account for CPU/memory, DB connections, and node quotas while old and new coexist—and retain enough headroom to survive losing an AZ.

### Question 7 — Which signals require aborting the canary immediately?

**Guided Answer:** Security or tenant-isolation breaches, double bookings, duplicate payments, data corruption, or critical business invariant failures. Error rate or p99 breaches past policy guardrails can also trigger immediate abort; never wait for a large sample once a critical defect is confirmed.

### Question 8 — When rolling back, must we roll back the database?

**Guided Answer:** Not by default. If schema changes were additive, keeping the schema and rolling back to a compatible binary is usually safer. Only roll back data/schemas using verified migration rollbacks; destructive migrations typically require forward fixes or restore/repair plans.

## 33. Well-Architected Review

| Pillar | Question | Evidence |
| --- | --- | --- |
| **Reliability** | Does the release limit blast radius and support rollback and recovery? | Health gates, canaries, draining, rollback/DR tests |
| **Security** | Are artifacts, configs, secrets, and new traffic verified with least privilege? | Signatures/provenance, scanning, IAM, secret manager |
| **Performance Efficiency** | Does the rollout preserve capacity, tail latency, and dependency health? | Surge sizing, p95/p99 tracking, pool/queue metrics |
| **Cost Optimization** | Are surge, dual-environment, and bake-time costs right-sized? | Cost per release, environment hours, right-sizing |
| **Operational Excellence** | Are deployments automated with records, runbooks, and decision gates? | CI/CD, deployment metadata, pause/abort, incident runbooks |
| **Sustainability** | Are temporary resources and old environments cleaned up promptly? | Cleanup policies, retention limits, capacity utilization |

Rolling update, blue–green, and canary are mechanisms for distributing the risk of change. **Rolling updates replace instances incrementally; blue–green switches traffic between two environments; canary validates a new version on a limited workload slice before expanding.** Choose a strategy based on coexistence feasibility, data state, capacity, telemetry quality, and recovery paths. A safe deployment concludes only when the new version is verified across real business journeys, side effects are reconciled, and rollback/cleanup procedures are handled as planned.
