# Post-Migration Validation and Optimizing the New Architecture

> **Scope:** Migration and modernization in CLOUD_ARCHITECTURE. This lesson guides how to verify that a cloud-migrated system satisfies business requirements, data integrity, and operations; then uses measured evidence to optimize the architecture across trade-offs among reliability, security, performance, scalability, and cost based on Well-Architected principles.

## 1. Why Does a Successful Migration Still Require Validation?

An application booting on new cloud infrastructure only proves that part of the deployment pipeline worked. It does not yet prove that customers complete transactions accurately, data is intact, the system sustains peak load, operations can handle incidents, or monthly bills stay within budget. Moving from on-premises servers to VMs, containers, or managed services alters system behavior because network latency, routing rules, access policies, connection limits, storage mechanics, and operational responsibilities change as well.

Two sequential activities must be distinguished:

1. **Post-migration validation:** collecting evidence that the new system meets agreed acceptance criteria. This starts in rehearsals, continues through traffic cutover, and spans the stabilization period.
2. **Post-migration optimization:** using live telemetry to tune resources, processing flows, data structures, and operations. The goal is sustainable value, not making the application run as fast as possible at any cost.

A migration should only be considered operationally complete when **critical business journeys are verified**, the system is observable and recoverable, remaining risks have owners, and the receiving operations team knows how to deploy, detect, and resolve incidents.

### 1.1. Learning Outcomes

After this lesson, learners will be able to:

- Translate business requirements into measurable acceptance criteria with accountable owners.
- Design layered validation: functional, data correctness, integrations, performance, security, reliability, and operations.
- Define criteria for proceeding, pausing, or rolling back during traffic shifts.
- Interpret real-world signals to select appropriate optimizations while identifying Well-Architected trade-offs.
- Produce an evidence report and architecture decision records for operational handover.

## 2. Setting Acceptance Criteria Before Measuring

### 2.1. Defining Boundaries and Baselines

First list all components and flows affecting users: UI, APIs, background workers, data stores, queues, payment providers, identity systems, DNS, network links, and monitoring services. For each component, identify where data is read/written, which dependencies are synchronous or asynchronous, and who can modify configurations.

A **baseline** should be measured on the legacy system over a window representative of normal days, peak hours, scheduled jobs, and predictable traffic surges. In practice, one to two weeks may work if it fits the business cycle; no single duration fits all systems. Record concurrently the application version, data volume, configuration, deployment region, request distribution, and observation timestamps. If the old system was slow or insecure, do not turn every legacy metric into a mandatory target for the new system.

Use terminology consistently:

| Concept | Meaning | Usage Note |
|---|---|---|
| **SLI (Service Level Indicator)** | Quantitative measure of service quality, such as transaction success rate, latency, or data freshness | Must specify measurement method, denominator, scope, and time window |
| **SLO (Service Level Objective)** | Quantitative target for one or more SLIs | Acceptance target for service quality tied to business needs |
| **p95/p99 latency** | Latency threshold within which 95%/99% of observed requests complete | Measure on identical journeys and load; averages can hide slow requests |
| **RTO (Recovery Time Objective)** | Maximum acceptable recovery duration after an outage | Must clarify start point and what counts as restored |
| **RPO (Recovery Point Objective)** | Maximum acceptable data loss measured by recovery timestamp | Replicas and backups are meaningful only when recoverable data is measured |
| **Error budget** | Permitted deviation allowed by an SLO over an evaluation period | Calculation depends on the SLI: request-based, time-based, or event-based |
| **Canary** | Releasing to a small slice of traffic/users before expanding | Useful only with telemetry, risk caps, and stop triggers |

For instance, a **99.9%** request-success SLO over valid requests in 30 days allows at most **0.1% failed requests** as defined by the SLI. Do not automatically convert this into downtime minutes if the SLI is request-based. Conversely, an availability-time SLO requires its own time-counting method.

### 2.2. Auditable Acceptance Matrix

Each criterion needs a **target threshold, measurement method, evaluation window, evidence, and approver**. The table below illustrates an e-commerce service; real numbers must be adjusted to business commitments, budgets, and actual data characteristics.

| Category | Illustrative Criterion | Verification Method | Approver |
|---|---|---|---|
| Business | Ordering and payment work; retries never create duplicate charges | End-to-end tests, transaction ID and idempotency-key reconciliation | Product owner + QA |
| Data | Zero missing confirmed orders at reconciliation mark; monetary totals match after rule normalization | Consistent snapshot, batch reconciliation, exception inspection | Data owner |
| Performance | Ordering API p95 ≤ 400 ms at 300 requests/sec | Load test with representative data measured from a fixed vantage point | Tech lead + SRE |
| Reliability | RTO ≤ 60 minutes, RPO ≤ 5 minutes for defined disaster scenario | Recovery drill, post-recovery data and business verification | SRE + business owner |
| Security | Zero unaccepted critical/high findings; permission flows match design | IAM review, vulnerability scan, unauthorized-access testing | Security owner |
| Operations | Useful logs, metrics, traces, alerts, and rehearsed runbooks | Incident simulation, verifying on-call responders receive alerts | Operations owner |
| Cost | Cost allocation and budget thresholds configured across environments | Tag-based reports, cost dashboards, alert verification | FinOps/Finance |

For **go/no-go** decisions, never average criteria together to hide a critical failure: one lost-order bug, secret leak, or unrecoverable database should halt cutover even if speed and cost look great.

### 2.3. Decision Gates

~~~mermaid
flowchart LR
    A["Baseline and acceptance criteria"] --> B["Migration rehearsal"]
    B --> C{"Pre-cutover criteria met?"}
    C -- "Not yet" --> D["Remediate and re-rehearse"]
    D --> B
    C -- "Met" --> E["Controlled traffic shift"]
    E --> F{"Guardrail breached?"}
    F -- "Yes" --> G["Halt ramp, remediate, or roll back"]
    G --> B
    F -- "No" --> H["Stabilize and hand over"]
    H --> I["Measure, optimize, re-evaluate"]
~~~

The three validation checkpoints are **pre-cutover** (proving readiness), **during cutover** (detecting degradation as live traffic arrives), and **post-cutover** (verifying data, stability, recoverability, and cost across operating cycles). Good signals at one checkpoint do not replace measurements at the next.

## 3. Multi-Layer Validation

### 3.1. Infrastructure, Configuration, and Connectivity

Verify deployed configurations against the approved architecture and Infrastructure as Code (IaC):

- Geographic regions/availability zones, private networks, subnets, route tables, NAT, VPNs or dedicated links, firewall rules, and security groups.
- Load balancers, health checks, TLS/certificates, domain names, DNS record TTLs, and client behavior when DNS changes.
- Access permissions to databases, object storage, secret managers, identity services, and external vendors.
- Environment configuration, runtime versions, container images, env variables, replica counts, CPU/memory limits, disk capacity, and service quotas.
- Key storage locations, encryption mechanisms, log retention regions, backup policies, and record retention windows.

A successful ping or HTTP 200 on the homepage does not validate the whole flow. Test the full path **from users through DNS/TLS/load balancer/API to data and integrations**, including background worker paths and outbound connections.

### 3.2. Functionality and Business Invariants

Test **high-value journeys**: login, search, order creation, payment, refunds, report export, and partner synchronization. Every journey should define inputs, expected outputs, related persisted data, and observability traces.

Specifically, verify **business invariants** rather than counting HTTP success codes alone:

- One payment request ID produces at most one financial effect even if a client or queue retries multiple times. Use idempotency keys, unique constraints, and transaction state checks; never assume networks or message brokers guarantee single execution.
- Inventory cannot be oversold beyond stock rules when concurrent requests arrive.
- Every order marked paid must reference a valid payment transaction.
- Role privileges must never escalate due to IAM configuration or identity-mapping changes.

Cover failure paths too: timeouts, retries, duplicate requests, expired tokens, unresponsive third-party services, slow processing, and payloads with Unicode characters or differing time zones.

### 3.3. Data Integrity and Freshness

Data migration commonly pairs an **initial snapshot** with **change capture (CDC)**. If the legacy system keeps accepting writes during migration, comparing two databases at different moments creates false discrepancies or hides missed records.

A reliable reconciliation process includes:

1. Lock a **consistency watermark**: transaction log position, CDC offset, well-defined timestamp, or equivalent transactional snapshot. Store this mark alongside the report.
2. Ensure the target system has applied all changes through the chosen watermark. Monitor **replication lag**, queued events, and CDC processing errors.
3. Compare **counts across meaningful partitions**, primary keys, business totals, foreign-key relationships, nulls, and edge cases. Do not compare total row counts alone.
4. For large datasets, reconcile in chunks using checksums of records **serialized consistently**; intentionally sample sensitive, high-value, and recently updated records.
5. Resolve root causes of differences: format conversions, time zones, decimal precision, collation, encoding, rounding rules, soft deletes, and in-flight transactions.
6. Log discrepancies, rerun checks, and close items only once data matches or an authorized owner formally accepts residual risk.

Example daily order reconciliation query run on **both source and target** at the same consistency watermark and filter rules:

~~~sql
SELECT
    CAST(created_at AS DATE) AS order_day,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_value,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid_count
FROM orders
WHERE created_at < :cutoff
GROUP BY CAST(created_at AS DATE)
ORDER BY order_day;
~~~

This query is illustrative and **does not create a consistent snapshot by itself**. Under continuous writes, filtering by an application timestamp column is insufficient if updates/deletes happen after the mark; use snapshots, log positions, or DBMS-native versioning. When comparing monetary values, prefer exact decimal types rather than floating-point numbers. For personal data, reports should include only aggregates and redacted reference IDs.

**Rollback caution:** if the new system has already accepted writes after switching, reverting to the legacy database is safe only with a strategy to bring new writes back to source or pause writes during sync. Never allow both systems to act as primary writers simultaneously without designed and tested conflict resolution; doing so risks **split-brain**, producing conflicting orders and transactions.

### 3.4. Integrations and Asynchronous Processing

For queues, event buses, webhooks, schedulers, and background jobs, also measure message backlogs, oldest-message age, end-to-end completion time, retry rates, and dead-letter queues (DLQs). An API returning `202 Accepted` does not prove downstream background work succeeded.

Test when messages arrive **duplicated, late, or out of order**; when consumers restart; and when partners send duplicate webhooks. Retries need backoff and caps; unprocessable jobs must be detected, captured as evidence, and handled via a DLQ workflow. System clocks, time zones, and batch schedules must also be reconciled because cron timing can shift after migration.

### 3.5. Performance and Scalability

Run tests with **realistic data, read/write ratios, payload sizes, and traffic distributions**. Record where the load generator runs; if load generators are underpowered or farther away than real users, results can mislead.

| Test Type | Question to Answer | Metrics to Track |
|---|---|---|
| Baseline/comparison | Does the new flow match or beat acceptance criteria? | p50/p95/p99, throughput, error rate |
| Load | Is the system stable at expected load? | Latency under load, CPU/memory, DB connections |
| Stress | Where are the limits and how does failure manifest? | Saturation point, timeouts, error rate, backpressure |
| Spike | Does autoscaling react fast enough to sudden surges? | Scale-out time, cold starts, queue depth |
| Soak | Are there resource leaks or long-term degradation? | Memory trend, pool usage, lock waits, disk |
| Failure/recovery | When a component fails, how does the system degrade and recover? | Success rate, failover time, data drift |

Do not draw conclusions from CPU alone. Low CPU with high p95 can stem from slow queries, exhausted connection pools, cross-region API calls, lock contention, or queue backlogs. Break down latency via distributed traces, database query plans, and per-dependency metrics. In before/after comparisons, hold workload, versions, dataset size, cache warm-up, and measurement duration consistent.

### 3.6. Recoverability and Reliability

Separate failure modes to test the right mechanisms:

- **Instance/pod failure:** health checks, restarts, traffic redistribution.
- **Availability zone failure:** whether multi-AZ infrastructure truly eliminates single points of failure and whether data/workers keep processing.
- **Database failure:** failover, application reconnection behavior, in-flight transactions, connection pools, and retry logic.
- **Region/disaster failure:** executing DR plans under realistic steps, verifying restored data, DNS/routing, and cross-region dependencies.
- **Human error or malware:** restoring isolated backups, write/delete protections on backups, integrity checks.

**Scheduled backups succeeding do not prove recovery works.** You must actually restore data, start the application, verify transactions, and record elapsed time from incident start until core capabilities resume (measured RTO). Measure RPO as the gap between the latest recoverable valid data timestamp and the defined incident time. Ensure measurements match specific scenarios—for example, losing one AZ differs from losing an entire region.

Fault-injection tests should bound blast radius, define clear abort criteria, and follow agreed schedules; you need not break production if a representative test environment proves the requirement. Still, document simulation limitations, especially for DR and provider-managed behaviors.

### 3.7. Security and Compliance

Re-verify the **shared responsibility model** for the chosen cloud service types. Moving a database to a managed service reduces OS patching, yet the application team remains responsible for data access permissions, secure configuration, backups, classification, and data governance.

Key inspection areas include:

- **Identity and access:** least privilege for humans and service accounts, workload identities, MFA on privileged accounts, environment separation, no unnecessary wildcard permissions.
- **Network and attack surface:** which components have public IPs, inbound/outbound rules, network segmentation, private links, WAF, abuse protection, and rate limiting.
- **Data and secrets:** TLS in transit, encryption at rest, key management, secret lifecycle, zero passwords/tokens baked into images, logs, or repositories.
- **Detection and response:** audit logs with accurate timestamps and identities, tamper-evident storage where required, alerts on permission changes and anomalous access.
- **Compliance:** data residency, retention/deletion windows, access segregation for sensitive data, and applicable regulatory/customer requirements.

Document scan scope and open findings. “No vulnerabilities found” does not mean “guaranteed free of vulnerabilities.”

### 3.8. Observability and Operational Readiness

At a minimum, telemetry must answer: **what is broken, who is affected, since when, at which layer, and who is handling it**. Observability should include:

- **Metrics:** traffic, errors, latency, saturation; plus domain metrics like confirmed orders, duplicate transactions, CDC lag, and message age.
- **Logs:** consistent structure with timestamps, request/correlation IDs, environment, and version; mask PII, secrets, and payment data.
- **Traces:** end-to-end journey visibility across APIs, databases, caches, queues, and external services.
- **Alerts:** tied to SLOs/user impact, severity, evaluation window, recipients, and runbooks; minimize noisy alerts on single-host metrics.
- **Runbooks:** symptom identification, access paths, safe diagnostic commands, recovery steps, communication templates, and escalation paths.

Before handover, simulate at least one scenario such as elevated payment errors or queue congestion and confirm on-call engineers **actually receive alerts and can execute** the runbook. Also verify audit trails for deployments and configuration changes.

## 4. Controlled Cutover, Canary, and Rollback

**Cutover** is the transition of users or primary write authority to the new environment; it need not be a single action. The right mechanism depends on risk, data compatibility, and reversibility.

### 4.1. Pre-Cutover

Complete and sign off on:

1. Versions, configurations, and owners for each system frozen per change control; snapshots/backups taken and restore verified.
2. Data synced to the agreed watermark with lag within thresholds; for continuous-write systems, a brief write-lock or **single-writer** handoff rehearsed.
3. Critical functional, performance, security, and operational tests passed; exceptions have named owners and risk acceptance.
4. Dashboards and alerts monitoring legacy source, new target, data, resources, and business errors ready.
5. Communication plan, decision contacts, checkpoint schedule, and actionable halt/recovery procedures ready.

### 4.2. During Cutover

You can use blue-green, user-cohort canary, or stepped traffic percentages. Below is an **illustrative pseudocode** configuration for a guardrail-monitored rollout; it is not direct syntax for a specific deployment tool:

~~~yaml
rollout:
  strategy: canary
  traffic_steps_percent: [1, 5, 25, 50, 100]
  minimum_observation_minutes_per_step: 20
  guardrails:
    checkout_success_rate_min: 0.9995
    checkout_p95_ms_max: 400
    replication_lag_seconds_max: 10
  critical_stop_conditions:
    - confirmed_order_missing
    - duplicate_payment_effect_detected
    - secret_exposure_detected
  on_breach: pause_and_invoke_runbook
~~~

Thresholds, step percentages, and observation windows are **examples**, not default recommendations. With low traffic, 20 minutes may lack statistical sample size; assess statistical confidence and ensure enough critical transactions occur. Every threshold needs an independent measurement source and a procedure if metrics drop out. Under a shared-data model, shifting read traffic is usually easier than shifting write authority; verify schema version compatibility and application rollback safety.

As each ramp step completes, inspect simultaneously: user errors, latency distributions, DB/queue health, reconciliation of new transactions, and integration status. **Halt traffic ramp immediately** when a critical guardrail breaches; investigate and decide whether to fix forward or roll back per runbook. Never keep ramping merely because “most dashboards are still green.”

### 4.3. Choosing a Safe Rollback

Rollback must be designed **before cutover**, covering specific cases:

| Scenario | Suitable Approach | Conditions to Verify |
|---|---|---|
| New app version fails while schema remains compatible | Shift traffic back to old version | Old version can read/write new data without duplicate processing |
| Wrong network/routing configuration | Restore verified routing/config | Connectivity, DNS caching, timeouts, and user sessions |
| New system accepted writes but must return to legacy DB | Freeze writes, reverse-sync, or execute controlled recovery | Transaction completeness/ordering, single write authority, reconciliation |
| Incompatible schema change or data loss | Trigger data recovery plan and incident process | Restore point, data-loss bounds, business impact |

Not every change can roll back automatically. For example, dropping a column or lossy format conversions require a **roll-forward** plan, backup/restore, or compensating migration. Prioritize data preservation and halt writes whenever no certain reversal exists.

### 4.4. Post-Cutover: Stabilization Phase

During heightened monitoring (hypercare), compare new system metrics against baselines and acceptance criteria across all critical usage cycles. Verify daily/weekly operations such as report aggregation, financial close, notifications, token expirations, and data archiving. Close incidents by severity, archive evidence, and mark the milestone when the project team hands ongoing accountability to operations.

Release the legacy source and temporary sync mechanisms only after verifying retention constraints, data preservation policies, rollback horizon, and the end of hypercare; deleting too early destroys reconciliation and recovery capability.

## 5. Evidence-Driven Architecture Optimization

Post-migration, the application runs under real infrastructure conditions, revealing issues rehearsal environments missed. Even so, optimize purposefully: **preserve or improve user experience, reliability, and security within acceptable budget and operational complexity**.

A controlled optimization loop:

1. **Observe:** gather SLIs, traces, profiles, query plans, costs, and business feedback; pinpoint impacted times and user cohorts.
2. **Hypothesize:** name the bottleneck component and expected evidence—e.g., “p95 rises due to connection pool limits during autoscaling.”
3. **Pick a small change:** adjust one or two reversible variables with clear success and abort criteria.
4. **Experiment:** compare under equivalent load, data, and time windows; watch guardrails such as error rate, RPO/RTO, and cost.
5. **Decide and document:** keep, tune, or revert; update IaC, dashboards, runbooks, and Architecture Decision Records (ADRs).

### 5.1. Diagnose Before Adding Resources

| Symptom | Hypothesis to Test | Possible Experiment / Optimization | Trade-Offs to Watch |
|---|---|---|---|
| p95 rises while app CPU stays low | Slow DB queries, lock waits, remote service calls, or exhausted pools | Traces, EXPLAIN, measure wait times, tune indexes/pools | Indexes add write/storage cost; oversized pools overload DB |
| High CPU, many new pods spawning | Pods undersized, reactive autoscaling late, CPU-heavy code | Right-size, profile, tune HPA on better signals | More replicas increase DB connections and cost |
| Queue keeps growing | Slow consumers, resource contention, retry storms | Measure oldest-message-age, cap concurrency, backpressure, DLQ | Scaling workers can push overload onto DB/partners |
| DB healthy yet clients time out | DNS/TLS, load balancer, NAT, network path, or external API | End-to-end traces, review timeouts, connection reuse, region placement | Overly aggressive timeouts can trigger retries/false failures |
| Network cost jumps post-migration | Cross-region/AZ transfer, NAT, external egress | Flow/cost analysis, co-locate chatty services, private endpoints where suitable | Grouping components can reduce fault isolation |
| Low cache hit rate, DB hit repeatedly | Bad TTL/keys or missing cache warming | Tune cache while measuring hit rate, add invalidation | Stale data, extra memory, and consistency complexity |
| Actual RTO exceeds target | Manual recovery steps, lack of automation, unready dependencies | Rehearse, automate repeatable steps, pre-stage DR | Always-on DR infrastructure increases cost |

### 5.2. Compute and Scalability

- **Right-sizing:** base on CPU, RAM, and I/O percentiles, peak windows, and failover headroom—not averages alone.
- **Autoscaling:** pick signals close to real demand such as queued requests, load-correlated CPU, or messages/worker; configure min/max bounds, warm-up times, cooldowns, and downstream dependency capacity.
- **Statelessness:** avoid storing critical sessions on a single instance; use appropriate external state stores for smoother rolling deploys and self-healing.
- **Load shedding:** rate limits, queues, backpressure, and circuit breakers prevent cascading failures; timeouts and retries need bounds and jitter where appropriate.
- **Service decomposition:** extract services only with clear domain boundaries and strong independent deployment/scaling value. Each microservice adds network hops, distributed data, and observability overhead.

Scaling an API from 4 to 20 instances opening up to 100 connections each can demand 2,000 database connections, far exceeding what the DB tolerates. Calculate a **system-wide connection budget**, apply pooling, cap instance counts, or optimize queries before blindly adding compute.

### 5.3. Data, Storage, and Latency

Inspect query plans, actually used indexes, transaction sizes, connection pools, cache miss rates, peak IOPS, and inter-component latency. Options include partitioning large tables, routing replication-lag-tolerant reads to replicas, caching hot reads, optimizing batches, or choosing fitting storage tiers. Every option must state **consistency semantics**: replicas may miss just-committed writes; caches need expiration and invalidation; batching lowers overhead while raising per-event latency.

Placing data near compute lowers latency, balanced against data residency, multi-AZ availability, and transfer costs. Moving data across regions or public egress increases both latency and billing. Before altering schemas, plan phased backward-compatible rollouts and recovery paths if a migration fails.

### 5.4. Cost Optimization with FinOps

The cloud bills across many dimensions: compute time, storage capacity, IOPS, requests, logs, data transfer, managed services, snapshots, and standby capacity. Simply **reducing server count** does not guarantee a lower bill.

Start with consistent tagging/cost allocation (application, owning team, environment, cost center), budget dashboards, and cost per unit of business value. For example:

**Cost per 1,000 successful orders** = 1,000 × (cloud spend allocated to ordering service in period) / (successful orders in same period).

This metric separates bill growth caused by higher business volume from rising unit costs caused by inefficient architecture. When comparing periods, keep shared costs, inputs, promotional periods, and success definitions consistent. Effective levers often include:

- Deleting or shutting down unneeded test resources, aligning object and log lifecycles to retention rules.
- Right-sizing overprovisioned resources, applying autoscaling, and purchasing reserved/commitment discounts **after** demand stabilizes and commitment risk is assessed.
- Eliminating unnecessary data transfer; auditing NAT, cross-zone/cross-region, egress, and query charges.
- Clarifying **which redundancy is mandatory** for SLO/RTO/RPO; never cut HA or backups merely because standby resources look “idle.”

Cost is a guardrail alongside service quality. An optimization that cuts bills by 20% while increasing payment failures is a failed optimization for a transaction-driven product.

### 5.5. Operations and Security After Optimization

Every architectural change must flow through CI/CD, security testing, policy checks, and corresponding telemetry. Temporary broad permissions granted during migration must be revoked; temporary secrets rotated; temporary firewall rules and snapshots audited. Add IaC drift detection and policy-as-code guardrails where appropriate.

Tune alerts around user impact: a short CPU spike may be benign, whereas rising payment failures at low CPU can be a severe outage. Update dashboards and runbooks after every change so on-call responders never troubleshoot against outdated diagrams.

## 6. Evaluating Through a Well-Architected Lens

Well-Architected provides systematic questioning around design decisions and risks. Pillar counts, names, and specifics vary by cloud provider; the table below uses six common perspectives to assess a cloud architecture.

| Perspective | Architectural Questions | Typical Evidence and Actions |
|---|---|---|
| **Operational Excellence** | Can we deploy, observe, recover, and learn from incidents consistently? | IaC, runbooks, SLI dashboards, drills, postmortems |
| **Security** | Who can access resources and data; are controls verifiable? | Least privilege, network segmentation, key/secret management, audits |
| **Reliability** | What happens if an instance, AZ, service, or region goes down? | Failover tests, backup/restore, measured RTO/RPO, load caps |
| **Performance Efficiency** | Do resources and processing models meet latency, throughput, and growth? | Load tests, traces, right-sizing, indexing, scale testing |
| **Cost Optimization** | Is spend proportional to value, allocated, and continuously tracked? | Cost allocation, unit economics, budgets, egress analysis |
| **Sustainability** | Are wasted resources and redundant data processing/storage avoided? | Cut idle capacity, improve resource efficiency, data lifecycle |

Pillars **interact with one another**. Keeping standby capacity across zones raises cost while lowering outage risk; compressing data saves storage and bandwidth while costing CPU; verbose logs aid investigation while raising spend and exposure risk if unredacted. Every decision must record business priorities, assumptions, and accepted trade-offs.

A concise **Architecture Decision Record (ADR)** might look like:

~~~text
ADR: Cap DB connection pool of ordering service
Context: During autoscaling, connection counts push the DB to its limit.
Option: Lower max pool per instance; cap max replicas;
        add connection-wait metrics and a circuit breaker.
Trade-off: May increase connection wait at peak load while protecting the DB.
Criteria: p95 <= 400 ms; no increase in error rate;
          connections < measured safe threshold.
Decision: Apply/reject after load test.
Owner, review date, metrics link: ...
~~~

## 7. End-to-End Scenario: Moving an Ordering System to the Cloud

### 7.1. Context and Target Architecture

Suppose an enterprise runs an on-premises ordering app consisting of web/API, a relational database, and async payment/confirmation workers. The business needs promotional peak scaling, higher resilience, and less server toil. The target architecture uses a load balancer, containers across multiple availability zones, a managed database, an event queue, and centralized observability.

~~~mermaid
flowchart TB
    U["User"] --> Edge["DNS / CDN / WAF"]
    Edge --> LB["Load balancer"]
    subgraph Cloud["Cloud Application Network"]
        LB --> API["API containers - Multi-AZ"]
        API --> DB[("Managed Database")]
        API --> MQ["Event Queue"]
        MQ --> W["Workers - Multi-AZ"]
        API --> OBS["Metrics / logs / traces"]
        W --> OBS
        DB --> BK["Backups and DR plan"]
    end
    W --> PAY["Payment Partner"]
~~~

This diagram shows only functional blocks and does not replace detailed designs for subnets, IAM, traffic direction, data partitioning, or how far services support multi-AZ. In particular, verify safeguards ensuring a payment transaction is never duplicated when the queue redelivers messages.

### 7.2. Pre-Cutover Criteria

All numbers in this scenario are **assumed solely to illustrate the method**:

- Target load: 300 order requests/sec under a defined profile combining product reads and writes.
- Latency: ordering API p95 ≤ 400 ms at target load.
- Quality: order success rate ≥ 99.95% in the evaluation window; distinguish valid user input errors from system failures.
- Data: zero missing or duplicated confirmed orders or payment effects after locking the reconciliation mark.
- DR: RTO ≤ 60 minutes; RPO ≤ 5 minutes in the agreed zone-loss scenario, verified via a recovery rehearsal.
- Cost: stays within agreed unit-cost bounds unless explicitly approved; logs, backups, and networking all included.

### 7.3. Validating Assumptions and Fixing Gaps

| Item | Initial Observation | Assessment / Action | Post-Fix Result |
|---|---|---|---|
| Ordering journey | Core cases pass; retries exposed one duplicate webhook case | Added idempotency keys and unique constraints | Zero duplicate financial effects in test suite |
| Data reconciliation | Order counts match; one day's total differed due to time zone | Standardized time zone and queried identical snapshot/CDC position | Verified zero discrepancy at reconciliation mark |
| API p95 latency | 480 ms at target load, **failed** | Traces showed DB pool waiting during API autoscale; tuned pool cap and indexes | 335 ms under identical load profile, **passed** |
| DR recovery | Restore succeeded, yet one manual DNS step drove RTO high | Rehearsed runbook, automated eligible step, verified permissions | RTO 42 minutes, RPO 2 minutes in test scenario |
| Unit cost | 24% above baseline | Identified unnecessary egress and idle resources | 5% above baseline, within hypothetical threshold |

In real projects, the “post-fix result” column must link to test reports, sample scope, version, and timestamps. One successful DR drill does not prove the system survives **every** disaster; it provides evidence only for the tested scenario, data, and method.

After the failing p95 result, the team **should not simply add containers**, as doing so could exhaust DB connections faster. Traces and metrics isolated the bottleneck; fixing pooling and queries, then re-running the exact load profile proved the improvement. This illustrates optimization via **symptom → hypothesis → measurement → change → re-measurement**.

### 7.4. Acceptance Report Template

A go/no-go report should contain enough detail for someone outside the implementation team to verify:

| Field | Example Content |
|---|---|
| Scope | Ordering service, API/worker/DB, target region, release version |
| Data watermark | Reconciled snapshot ID, CDC position, or log sequence |
| Measurement window | Start/end timestamps with time zone, transaction volume, load profile |
| Targets | SLIs/SLOs, RTO/RPO, business invariants, acceptance thresholds |
| Evidence | Links to test reports, dashboards, reconciliation queries, logs, drill minutes |
| Variances | Impact description, severity, assignee, due date |
| Decision | GO / PAUSE / ROLLBACK / ACCEPTED RISK and authorized sign-offs |
| Handover | Runbooks, current diagrams, alerts, on-call schedule, optimization review schedule |

If severe errors affecting data accuracy or recoverability remain, the report must record **NO-GO/PAUSE**, even if all other tests passed.

## 8. Misconceptions That Distort Decisions

| Misconception | Why It Is Wrong | Sound Practice |
|---|---|---|
| “The app boots, so migration is done.” | Ignores business logic, data, security, and operations | Use a multi-layer acceptance matrix |
| “Matching DB row counts means data is right.” | Values may differ, rows may duplicate or lag | Reconcile at a consistent watermark by keys and business totals |
| “Having backups guarantees RTO/RPO.” | Backups may fail to restore or take too long | Rehearse restores and measure real RTO/RPO |
| “Adding instances always boosts throughput.” | Database, queue, network, or partner may be the bottleneck | Measure end-to-end saturation and apply backpressure |
| “Cut costs as aggressively as possible.” | Can degrade HA, security, or user experience | Track cost per business unit alongside SLO guardrails |
| “5% canary is green, so shift 100%.” | 5% may not hit load limits, data edge cases, or special cohorts | Ramp in steps with adequate samples and high-load tests |
| “App rollback restores old data state.” | Schema and newly written data may be incompatible | Design sync and write authority before cutover |
| “Solve every problem with microservices.” | Splitting adds network hops, distributed data, and ops load | Split only with clear business benefits and evidence |

## 9. Practice Exercise: Designing an Architecture Acceptance Pass

**Prompt:** An order management app just moved from on-premises VMs to cloud containers and a managed database. During peak hours, the API returns 200 yet customers report missing confirmation emails; network costs spiked and the operations team has never tested data recovery.

Draft a concise validation dossier containing:

1. **Three business journeys** to monitor and invariants to preserve; at least one journey must traverse queue/worker.
2. **Five SLIs/guardrails** with measurement definitions and evaluation windows covering business errors, latency, background processing, data, and recovery.
3. **One reconciliation check** between old and new systems at a consistency watermark; specify conditions proving zero lost orders.
4. **One failure scenario** to rehearse proving RTO/RPO and alerting workflows.
5. **Two optimization hypotheses** for network costs and email backlog, plus metrics to test them.
6. **GO/PAUSE/ROLLBACK criteria** and how new writes are protected if rolling back.

Thinking hints: “API returns 200” only confirms the synchronous tier. Confirming emails were sent requires tracking emitted events, queue dwell time, worker results, retry/DLQ errors, and email provider status. Rising network costs should be decomposed into cross-AZ transfer, NAT/egress, and internal traffic before moving services. Untested restores represent a recovery evidence gap that must feed into the go/no-go decision proportional to data criticality.

## 10. Pre-Migration-Closure Self-Check

Use this checklist for handover, attaching concrete evidence rather than merely ticking “checked”:

- [ ] Every critical business journey has an owner, test results, and acceptance criteria.
- [ ] Data is reconciled at a consistency watermark; discrepancies are resolved or approved.
- [ ] Performance measured under representative load; bottlenecks and scaling behavior verified.
- [ ] Access controls, secrets, networking, logs, and security requirements reviewed in the live environment.
- [ ] Backups restore cleanly; RTO/RPO measured for agreed scenarios.
- [ ] SLIs, alerts, runbooks, on-call coverage, and incident workflows verified.
- [ ] Cutover, guardrails, rollback/roll-forward, and data write authority documented clearly.
- [ ] Costs allocated with monitoring thresholds and data-backed optimization plans.
- [ ] Architectural decisions and Well-Architected trade-offs documented with a review schedule.
- [ ] Receiving operations team holds required permissions, documentation, dashboards, and clear ownership.

**Core takeaway:** Migration quality is proven by business outcomes, data integrity, recoverability, and operational evidence. Architecture optimization is a purposeful measurement loop: change one hypothesis, verify system-wide impact, and accept trade-offs transparently.
