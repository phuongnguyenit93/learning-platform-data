# Evaluating Architectures Across Security, Reliability, Performance, and Cost

An Oracle Cloud Infrastructure (OCI) architecture is considered fit for purpose only when it meets system requirements backed by verifiable evidence. A diagram packed with services, oversized resources, or a low cost estimate is never enough to conclude that a system is secure, operationally stable, and responsibly budgeted.

In the **Capstone Projects and Assessment** chapter, this guide walks through evaluating an OCI capstone submission from four perspectives: **security, reliability, performance, and cost**. Scope covers tenancy, compartments, IAM, VCN, Compute, storage, Oracle Database, monitoring, and automation. An evaluation must identify which requirements the architecture satisfies, what evidence is missing, who owns remaining risks, and what conditions must be fulfilled before going into operation.

Figures for load, duration, budget, and test results in this guide are **assumptions for learning purposes**, not live measurements or OCI pricing. Deployment feasibility must be cross-checked against actual region, service, configuration, and project permissions.

## 1. Evaluation Objectives and Deliverables

After this lesson, learners should be able to:

- Translate business requirements into evaluation criteria with clear pass thresholds.
- Inspect an architecture across deployment config, access flows, and operational telemetry.
- Distinguish intended design from tested capability.
- Surface trade-offs between security, recoverability, processing speed, and budget.
- Score with evidence while enforcing mandatory gates that cannot be compensated by points.
- Build a remediation list with owners, deadlines, and verification methods.

A minimum output set includes:

| Deliverable | Questions to Answer |
|---|---|
| Scope and assumptions | Which environment, version, and failure modes are under review? |
| Diagram and resource inventory | Where do real resources live, in which compartments, and how do they communicate? |
| Requirements-to-evidence matrix | Which configuration or test proves each requirement? |
| Scorecard and mandatory gates | What is the maturity level, and do any blockers prevent acceptance? |
| Findings register | What impact does each gap or constraint cause, and in what order should it be fixed? |
| Decision and re-verification plan | Under what scope can it operate, and who owns remaining actions? |

Architecture review does not stop at finding flaws. It guides selecting a solution that both satisfies requirements and can be deployed, monitored, recovered, and funded sustainably.

## 2. Locking Scope Before Inspecting Configurations

### 2.1. Defining the Unit Under Review

Avoid evaluating "all of OCI" vaguely when a project deploys a single application. Specify:

- Relevant tenancy and compartments; development, staging, or production environment.
- Primary region, replica region if any, and committed failure boundaries.
- Services in scope: networking, IAM, application, database, storage, and monitoring.
- Out-of-control dependencies affecting outcomes: DNS, identity providers, enterprise links, or payment APIs.
- Application version, infrastructure config version, and evidence-capture timestamp.
- Un-deployed or untested changes.

A report holds true only for the evaluated state. After major changes to IAM, network topology, database, load scale, or retention policies, determine which prior conclusions are invalidated.

### 2.2. End-to-End Scenario: Order Intake Portal

Suppose a team builds an order-intake portal on OCI:

- Users call the API over HTTPS.
- OCI Load Balancer routes requests to Compute instances running the app in a private subnet.
- The application writes transactions to a clearly selected Oracle database service.
- Object Storage stores attachments; the database design provides its own backup mechanism.
- IAM separates admin, deployment, operations, and evaluator groups.
- Monitoring, Logging, Audit, and notification channels provide operational signals.

Initial requirements:

| Requirement Group | Assumed Criterion |
|---|---|
| Security | Database and app admin ports must not be directly reachable from the Internet; privileged accounts require MFA |
| Availability | Business request success rate at least 99.9% over a 30-day window |
| Performance | Under agreed test load, API p95 response time under 400 ms, error rate under 0.5% |
| Test load | 100 requests/second for 15 minutes after warm-up; 90% reads, 10% synthetic order creates |
| Component failure | Upon losing one Compute instance, the system still meets load and performance thresholds after the agreed detection and backend-removal window |
| Data recovery | For in-scope data incidents: RTO ≤ 30 minutes, RPO ≤ 5 minutes |
| Regional outage | If committing to disaster recovery from cross-region copies: RTO ≤ 24 hours, RPO ≤ 24 hours |
| Budget | Estimated pre-tax spend ≤ 1,200 USD/month, including an approved contingency buffer rule |
| Business unit | Roughly 100,000 successfully created orders per month used as the cost-allocation baseline |

Explicitly define which scenarios fall under "in-scope data incidents", such as operator errors requiring point-in-time recovery. Never use component-failure targets to implicitly promise surviving full region loss.

The dossier must also specify how latency is measured: e.g. from load-generator send to full response receipt from a defined network vantage point. Measuring from outside OCI includes external transit latency. Such figures cannot be compared directly against internal application processing time.

### 2.3. Defining SLI, SLO, RTO, and RPO

**SLI** is the measured indicator. **SLO** is the target set on that indicator. **RTO** is the maximum acceptable recovery duration for a scenario; **RPO** is acceptable data loss expressed as a time interval.

Example SLI for the order-creation API:

~~~text
Success rate =
    Valid requests completing business logic properly
    / Total valid requests evaluated
~~~

Classification rules must be agreed upon before measuring:

- Count server errors, timeouts, and connection failures as failures.
- An HTTP 200 response that fails to persist the intended order is still a business failure.
- Rejections of invalid client inputs may be excluded from the denominator if that rule is published.
- Valid requests rejected due to overload, including certain 429 responses, must not be arbitrarily excluded to inflate ratios.
- Scanner traffic, health checks, and load-generator probes need clear separation rules.

If an SLO is time-based over a 30-day window:

~~~text
Total time = 30 × 24 × 60 = 43,200 minutes
Error budget at 99.9% = 43,200 × 0.001 = 43.2 minutes
~~~

This applies to time-based SLOs. For request-based SLOs, calculate error budgets by request counts; the two diverge when traffic fluctuates. Also never substitute an infrastructure service SLA for the whole application's SLO.

## 3. Reading Architecture by Flows and Trust Boundaries

### 3.1. What Must the Diagram Show?

A minimal architecture diagram should identify:

- Public entry points and TLS termination locations.
- Public subnets, private subnets, route tables, Internet Gateways, NAT Gateways, or Service Gateways used.
- Network Security Groups (NSGs) and permitted flow groups.
- Placement of Compute, databases, Object Storage, and dependencies.
- Compartment boundaries, administrative permissions, and workload identities.
- Availability Domains (ADs) and Fault Domains (FDs) where relevant.
- Paths for backups, logs, metrics, and alarms.

~~~mermaid
flowchart TD
    U[Users] -->|HTTPS| LB[Public Load Balancer]
    LB -->|Restricted backend flow| APP[Application Compute in private subnet]
    APP -->|Protected DB connection| DB[Oracle Database]
    APP -->|Access via workload identity| OBJ[Object Storage]
    APP -->|Emit logs and metrics| OBS[Logging and Monitoring]
    DB -->|Operational signals| OBS
    OBS --> ALERT[Alert channels and on-call operator]
    OP[Authorized operators] --> ACCESS[Controlled admin channel]
    ACCESS --> APP
    DB --> BACKUP[Backups and recovery procedures]
~~~

This diagram depicts logical relationships. It does not prove instance counts, AD/FD placement, gateway configurations, or database availability. Those details belong in deployment configurations and the evidence inventory.

### 3.2. Tracing Three Independent Flows

**Business flow:** users → Load Balancer → application → database or Object Storage. This shows where data travels, where bottlenecks form, and which tier absorbs load.

**Administrative flow:** deployers or pipelines → IAM → control-plane APIs and admin channels. A system without public SSH can still be completely altered if pipelines hold overly broad credentials.

**Recovery and observability flow:** resources → logs, metrics, alarms, backups → on-call operators or restore procedures. This path determines whether the team can detect incidents and recover while the business flow is broken.

Never assume observability or recovery paths remain functional when the primary system fails. For instance, a runbook stored solely on an application VM becomes hard to reach when that VM is lost.

## 4. Security Review: Checking Real Access Paths and Permissions

### 4.1. Tenancy, Compartments, and IAM

Compartments organize resources and scope permissions; they do not create network isolation. A parent-level or tenancy-level policy can extend privileges over child compartments according to how the policy is written.

Questions to inspect:

1. Who can modify IAM policies, network settings, secrets, encryption keys, and production resources?
2. Which policy grants each permission, and at which scope is it attached?
3. Does any user or workload hold resource-management privileges beyond actual need?
4. Can non-production environments modify production resources or read production data?
5. Does a pipeline hold application-deployment rights alongside permissions to expand its own IAM?
6. Is there a procedure for emergency elevation, revocation, and post-use audit?

Illustrative role-separation table:

| Actor | Valid Need | Red Flag to Investigate |
|---|---|---|
| App deployment team | Update app resources within assigned scope | Can edit any policy in the tenancy |
| Operations team | Read telemetry and follow runbooks | Everyone shares one admin account |
| Application | Read needed secrets and access business buckets | Uses personal API keys with admin rights |
| Evaluator | Read permitted configs and evidence | Needs production passwords to review architecture |
| Infrastructure pipeline | Mutate resources within deployment scope | Can grant itself unbounded permissions |

MFA for privileged human users is essential, but does not replace managing API keys, tokens, pipeline credentials, or workload authentication.

Prefer workload identities such as instance principals or resource principals where supported by the service and workload type. Also inspect dynamic group matching rules and attached policies: an overly broad dynamic group can still grant unintended privileges.

### 4.2. VCN, Subnets, and NSGs

Network evaluation must distinguish three layers:

- **Routability:** whether packets have a forwarding path to the destination.
- **Permissive rules:** whether NSGs, security lists, and filters allow that flow.
- **Service endpoint:** whether the target service listens, authenticates, and protects data properly.

A private subnet alone does not prove the database accepts connections solely from the application. Inspect internal paths, on-premises links, peering, and effective ingress rules.

Example flow matrix:

| Source | Destination | Purpose | Evaluation Criteria |
|---|---|---|---|
| Internet | Load Balancer | User HTTPS access | Only needed listeners open, proper TLS config |
| Load Balancer | App backends | Request forwarding | Only required backend sources and active ports allowed |
| Application | Database | Business transactions | Source, destination, and port restricted to chosen DB service |
| Application | Object Storage | File reads/writes | Network path and IAM scoped to needed resources |
| Operator | Admin channel | Controlled maintenance | Individual identity, bounded rights, and access trail |
| Application | Internet | External APIs or updates | Opened only when justified, dependencies and egress monitored |

If using a Service Gateway, confirm the target is an OCI service supported by the gateway within that configuration scope. A Service Gateway is not a general Internet egress route. A NAT Gateway handles outbound connectivity from private networks; it does not replace authorization, encryption, or service resilience.

Strong evidence pairs route tables, NSG/security list rules, and connectivity tests from both allowed and denied sources. Screenshotting one NSG is insufficient if a security list or alternate link still widens exposure.

### 4.3. Secrets, Data, and Encryption Keys

Examine the secret lifecycle from creation through revocation:

- Do secrets appear in source code, public config files, logs, bootstrap scripts, or pipeline outputs?
- Who can read secrets, and who can rotate or modify them?
- How does the application fetch secrets and how long does it retain them in memory?
- During secret rotation, how do old and new connections transition?
- Can exposed credentials be revoked without manually editing fleets of hosts?

OCI Vault is a tool for secrets and keys, yet "using Vault" alone does not prove policies, rotation, and operational procedures are sound.

For encryption, separate:

1. Encryption in transit: user to Load Balancer, Load Balancer to backends, application to database.
2. Encryption at rest: database, volumes, Object Storage, and backups.
3. Key-usage permissions and recovery when a key becomes unavailable.

If choosing customer-managed keys, also evaluate key-admin rights, disable/deletion controls, cross-region dependencies, and restoring backups encrypted with that key. Never pick complex key management just to add features to a diagram.

Sensitive data also requires retention policies, log redaction, and test-data controls. Encryption does not fix a valid account granted overly broad read permissions.

### 4.4. Audit, Logs, and Drift/Anomaly Detection

Distinguish the purpose of each source:

| Source | Helps Answer |
|---|---|
| Audit | Who called logged control-plane APIs within scope, and when? |
| Application logs | Which request failed, at which business step, and under which correlation ID? |
| Access or network logs | Where did traffic originate, where did it go, and are anomalies present? |
| Metrics and alarms | Which thresholds are breached and require action? |
| Cloud Guard (if deployed) | Are any risky configurations or behaviors flagged within enabled scope? |

Audit does not replace full business logs or all data-access trails. Nor does an undetected misconfiguration become safe merely because tooling stayed quiet.

Run a controlled alert test: generate a signal, check the alarm, verify the notification channel, and confirm responders know how to act. Never include real secrets or real customer data in the evidence package.

## 5. Reliability Review: Measuring Fault Tolerance and Recovery

### 5.1. Finding Single Points of Failure by Layer

For every component, ask: "If this component stops working, what functionality stops, and what replaces it?"

| Layer | Common Single Points of Failure | Required Evidence |
|---|---|---|
| Application | Single instance; session state in local memory | Backend count, state storage model, single-instance failure test |
| Data | DB setup without recovery meeting targets | Specific HA/backup design, switchover or restore results |
| Networking | Single critical link without redundancy | Topology and per-link failover tests |
| Operations | One person holding all rights and runbooks | Backup personnel roster, access setup, and drills |
| Automation | Unrecoverable artifacts, state, or pipelines | Rebuild procedures and deployment-state management |
| Observability | Alarms routed to unmonitored channels | Alert test and acknowledgment latency |

Multiple instances in one location do not cover all failure modes. Spreading across FDs mitigates certain intra-AD infrastructure faults; it does not prove full-AD loss tolerance. Spreading across ADs or regions helps only when applications, data, and cutover procedures all support it.

AD counts and placement options depend on the region and service. Reports must reflect real placement rather than extrapolating from a sample diagram.

### 5.2. Separating HA, Backup, and DR

**High Availability (HA)** aims to keep serving when a component fails.

**Backup** provides data copies or restore points to recover from data loss or corruption.

**Disaster Recovery (DR)** is a recovery plan for major incidents within a defined scope, typically involving alternate sites, data copies, and cutover procedures.

These three are related yet non-interchangeable:

- Replicas can propagate accidental deletions or corrupted data.
- Intact backups may not restore fast enough to meet RTO.
- Same-region redundancy does not prove recovery from region loss.
- A restored database does not mean applications, DNS, secrets, and user links are working again.

Across Oracle database services, HA, standby, backup, and switchover mechanisms differ. Reviews must specify the exact deployed service, edition/options, and configuration. Never assume every database service shares identical features or enables cross-region redundancy automatically.

### 5.3. Verifying RTO and RPO with Canary Transactions

A useful restore drill includes:

1. Test dataset containing uniquely tagged transactions with verifiable commit timestamps.
2. Defined incident start time or target recovery point.
3. Timestamps for detection, confirmation, restore start, and each major milestone.
4. Verification of the final recovered data.
5. End-to-end business verification from the user entry point.
6. Completion timestamp once agreed service criteria are met.

~~~text
Observed RTO =
    Timestamp when service recovery is verified
    - Incident start milestone per evaluation convention

Observed RPO =
    Interval of unrecovered data prior to incident start,
    determined via transactions and commit timestamps
~~~

If detection takes 8 minutes, restore prep 7 minutes, restore 12 minutes, and business verification 6 minutes, total recovery is 33 minutes. Claiming "restore took 12 minutes so 30-minute RTO passed" ignores most of the timeline.

For RPO, do not judge solely by backup file creation timestamps. Determine the actual recoverable point in time, including required backup chains or logs for the chosen solution.

Backups must be tested alongside access permissions, decryption keys, target capacity, network dependencies, and accessibility when the source system is down.

### 5.4. Testing Failover/Switchover and Data Correctness

When standbys or failover exist, measure more than how fast a new address responds. Check:

- How the application reconnects and refreshes connection pools.
- Whether in-flight transactions duplicate, vanish, or end in unknown states.
- What mechanism guarantees only the authorized writer accepts writes.
- Replication lag and unsynchronized data volume at cutover time.
- How to return to steady state and resynchronize data.

Retries need bounded counts, timeouts, and backoff. Order creation requires deduplication such as business-linked idempotency keys. Unbounded retries amplify load right when the database is weakest.

### 5.5. Does Automation Actually Improve Recoverability?

Terraform or OCI Resource Manager helps rebuild infrastructure, yet "having IaC code" is not enough. Check:

- How state is protected, access-controlled, and change-managed.
- Whether application artifacts and configs for the recovery version remain reachable.
- Whether secrets, data, and manual steps are covered in the rebuild plan.
- Whether re-running creates duplicate resources, unintended replacements, or data loss.
- Whether resource limits, quotas, and provisioning capacity could block rebuilding.

Having permission to create resources does not guarantee capacity will be available on demand. Recovery plans must consider limits and workable fallback options.

## 6. Performance Review: Linking Measurements to Load and Config

### 6.1. Load Models Must Describe Behavior

A claim like "handles 100 users" omits critical facts. The same 100 users generate vastly different request rates depending on think time and operation types.

Test models should record:

| Element | Details to Specify |
|---|---|
| Arrival rate | Requests per second and how pacing is maintained |
| Business mix | Ratios of reads, writes, file uploads, searches, or reports |
| Dataset | Table sizes, key distributions, file sizes, and historical volume |
| Test lifecycle | Warm-up, ramp-up, steady state, ramp-down, and observation window |
| Connections | New connection rate, keep-alive reuse, and authentication overhead |
| Load origin | Inside OCI, from corporate network, or over the public Internet |
| Configuration | Instance count, shapes, pool limits, DB tier, and storage tiers |
| Pass criteria | Throughput, p95, p99, error rates, and business correctness |

The load generator itself must have enough capacity. If it only emits 70 requests/second against a target of 100, you cannot claim the app passed a 100 req/s test.

For 100 requests/second over 15 minutes, expected steady-state requests are:

~~~text
100 × 15 × 60 = 90,000 requests

With an error threshold under 0.5%:
Failed requests must stay below 450,
while send rate and validity criteria are also verified.
~~~

This is a single test threshold, not complete proof for a 30-day SLO.

### 6.2. Looking Beyond Average CPU

Examine metrics together:

- Achieved throughput, queued requests, and timeouts.
- p50, p95, and p99 latencies by endpoint and time window.
- CPU, memory, and garbage-collection pressure for JVM applications.
- Connection counts, pool wait times, and database connection limits.
- Query execution times, locks, I/O, and database-tier metrics.
- Network latency, bandwidth, and payload sizes.
- Backend health, active serving instances, and autoscaling timing.

Low CPU often accompanies high latency when threads block on database queries, pool waits, or external APIs.

Never average per-instance p95 values and call it system-wide p95. Aggregate distributions properly or compute across the full request population. Also inspect write endpoints separately so fast reads do not mask slow writes.

### 6.3. Estimating Concurrency with Little's Law

In steady state, you can apply:

~~~text
L ≈ λ × W

L: average number of requests in the system
λ: average throughput
W: average time a request spends in the system
~~~

For example, at 100 requests/second and 0.2 seconds average duration:

~~~text
L ≈ 100 × 0.2 = 20 requests
~~~

The figure 20 is a sanity check for average concurrency under those conditions. It is not a required thread count or database connection count. A single request might make zero DB calls, multiple DB calls, or wait on another dependency. Never plug p95 latency into `W` in this formula.

### 6.4. Checking Capacity Upon Single-Instance Loss

Suppose one instance is measured handling up to roughly 70 requests/second while meeting latency and error targets.

With two instances:

~~~text
Normal: 100 / 2 = 50 requests/second/instance
Lose one instance: 100 / 1 = 100 requests/second/instance
~~~

The architecture meets normal load yet fails the single-instance loss requirement.

Two options to evaluate:

- Run three instances of the same shape: losing one leaves two instances handling roughly 50 req/s each.
- Run two larger instances, each verified capable of handling the full surviving load plus headroom.

Simple division is only a screening step—it does not prove linear scaling. Databases, Load Balancers, connection pools, or shared dependencies may become the new bottleneck.

Autoscaling does not materialize capacity instantaneously. Tests must measure detection delay, provisioning time, app startup, warm-up, and backend registration. If requirements disallow degradation during that gap, pre-provision capacity or obtain formal approval to relax the requirement.

### 6.5. A Well-Scoped Test Suite

| Test Type | Purpose |
|---|---|
| Baseline | Understand low-load behavior; validate tools and test data |
| Target load | Confirm thresholds at 100 requests/second |
| Single-backend loss | Verify application fault tolerance under the same load |
| Soak test | Detect memory leaks, queue growth, connection leaks, or storage growth |
| Overload recovery | Observe whether the system self-stabilizes once load drops |
| Controlled stress ramp | Identify saturation point and overload rejection behavior |

Fault tests must execute in authorized environments with appropriate data, bounded blast radius, and clear abort criteria. Before recovery tests, verify a path back to steady state.

## 7. Cost Review: Accounting for Full Scope and Business Units

### 7.1. Starting from Resource Bills, Ending at Business Outcomes

Costs extend well beyond Compute. For this architecture, review:

- Compute instances, OS images, and applicable software licensing.
- Database service, compute/OCPU sizing, storage, and licensing options.
- Boot volumes, block volumes, storage performance tiers, and backups.
- Object Storage capacity, operation counts, storage tiers, and retrieval fees.
- Load Balancer and networking services used.
- Data transfer by source, destination, and network path.
- Logs, metrics, and billable observability features in the live config.
- Non-production environments, orphaned resources, and over-retained data.
- Standby capacity, replicas, or cross-region copies supporting recovery targets.

Never assume all outbound traffic is billed identically, or that any network path is free by default. Estimates must specify traffic types and applicable pricing rules checked against current rate cards at estimation time.

Free Tier or promotional credits can lower bills temporarily. Separate promotional credits from steady-state run rates so architectural sustainability is not misjudged.

### 7.2. Illustrative Estimate Table

Assume each line item is normalized to the same monthly period on a pre-tax basis:

| Line Item | Est. USD/Month | Primary Cost Driver |
|---|---:|---|
| Application Compute | 180 | Two instances and runtime hours |
| Oracle Database | 520 | Sizing, resource tier, and licensing choice |
| Load Balancer | 60 | Bandwidth shape and assumed usage |
| Boot/block volumes | 80 | Capacity and performance tier |
| Object Storage for app data | 30 | Capacity, storage tier, and requests |
| Observability | 85 | Log volume, retention, and enabled features |
| Networking | 110 | Transfer direction and assumed egress |
| Backups | 55 | In-scope DB/volume backup copies |
| **Total** | **1,120** | Excluding contingency buffer |

Audit line items to avoid double counting. Here, Object Storage covers only app data; separate backup copies appear under Backups. When building a real estimate, align categories with actual service billing line items.

Assuming 100,000 successful orders/month:

~~~text
Allocated infrastructure cost per order =
    1,120 / 100,000
    = 0.0112 USD/order
~~~

This is allocated infrastructure cost per business unit, not the total cost of fulfilling an order. Scope may exclude staffing, taxes, support, or external services.

As traffic grows, per-order cost may drop initially by utilizing spare capacity, then climb when database upgrades or standby environments are required. Never extrapolate linearly from a single data point.

### 7.3. Sensitivity Checks and Contingency Buffers

At minimum, compare these scenarios:

| Scenario | Factors to Recompute |
|---|---|
| Traffic doubles | Instance counts, DB sizing, logs, bandwidth, and limits |
| Data grows after one year | Database storage, backups, Object Storage, and restore duration |
| Cross-region DR enabled | Standby resources, replicas, and cross-region transfer |
| Longer log retention | Storage volume, query volume, and retention settings |
| Extended incident | Temporary resources, parallel runs, and recovery actions |
| Credits expire | Run rate after credits or promotional programs end |

If the estimation rule requires adding a 10% contingency buffer to base cost, 1,120 USD becomes 1,232 USD. The architecture breaches the 1,200 USD cap under that rule even though base spend looked under budget.

Lock contingency rules before judging pass/fail. Never tweak math afterward to squeeze an estimate under budget.

### 7.4. Operational Cost Controls

Controls to evaluate include:

- Defined tags or equivalent chargeback mechanisms for owner, environment, application, and cost center.
- Budgets and alerts routed to people authorized to act.
- Cost Analysis reviews tracking trends by service and business unit.
- Off-hours shutdown schedules for non-24/7 environments.
- Measurement-based rightsizing accounting for fault tolerance and peak loads.
- Object Storage and log lifecycle rules matched to access and retention needs.
- Cleanup of orphaned resources left behind after drills or deployment changes.
- Quotas, limits, and resource-creation permissions aligned with governance.

**A budget alert is not an automatic spend cap.** It fires per configuration and billing reporting cadence; never cite it as proof that bills will stop at a fixed dollar amount. Quotas and service limits also do not replace complete budget governance.

Do not move data across storage tiers based solely on per-GB storage rates. Factor in retrieval times, retrieval fees, retention constraints, restore capability, and access frequency.

## 8. Handling Trade-Offs Across the Four Pillars

Improving one pillar often degrades another. Reviewers must document concrete impacts rather than assuming "more redundancy is always better" or "lowest cost is optimal."

| Decision | Potential Benefit | Impact to Verify |
|---|---|---|
| Add an app backend | Increases surviving capacity if one instance fails | Higher cost; DB may become the next bottleneck |
| Add caching | Lowers latency and DB load | Stale reads, invalidation bugs, access checks, cache failures |
| Log more verbosely | Faster incident triage | Higher cost, sensitive-data exposure, logging latency |
| Add cross-region standby | Expands recovery scope | Higher cost, replication lag, failover complexity, consistency |
| Tighten egress | Shrinks outbound attack surface | Can break package updates or external dependencies |
| Shorten backup retention | Lowers storage spend | Inability to roll back before delayed defect detection |
| Off-hours shutdown | Cuts Compute spend | Startup warm-up lag and test scheduling impact |
| Switch to customer-managed keys | Stronger key control per policy | Key operations risk and restore dependencies |

Every decision needs rationale, alternatives considered, applicability conditions, and verification criteria. For example:

> Choose three backends of the current shape to survive losing one instance at target load. Accept only after fault-injection load tests confirm the database does not saturate and the buffered estimate remains within approved budget.

This is a measurable, conditional decision. Saying "add instances to ensure stability" states neither bounds nor proof.

## 9. Building a Requirements-to-Evidence Matrix

### 9.1. Every Review Row Must Be Traceable

Each row should contain:

- Requirement ID and business rationale.
- Scope and test conditions.
- Pass threshold.
- Evidence, timestamp, and matching configuration.
- Observed outcome.
- Reviewer and remediation owner.
- Status: pass, fail, insufficient evidence, or justified not-applicable.

Example:

| ID | Requirement | Evidence to Collect | Pass Threshold |
|---|---|---|---|
| SEC-01 | DB unreachable directly from Internet | Routes, endpoint, NSGs/security lists, and connection tests | Zero unauthorized paths within test scope |
| SEC-02 | Workload reads only needed data | Dynamic groups, policies, and negative access tests | Authorized reads succeed; out-of-scope access denied |
| REL-01 | Survive single-backend loss | Test logs, backend health, metrics, and load results | Meets load, latency, and error thresholds after agreed failover window |
| REL-02 | Data recovery | Timeline, canary transactions, and business checks | RTO ≤ 30 minutes; RPO ≤ 5 minutes |
| PERF-01 | Serve target load | Load script, generator stats, and latency distribution | 100 req/s, p95 < 400 ms, errors < 0.5% |
| COST-01 | Stay within budget | Resource inventory, pricing assumptions, and sensitivity | Total with contingency buffer ≤ 1,200 USD/month |
| OPS-01 | Detect and receive alerts | Alarms, channels, and alert-test trail | Reaches right on-call owner within agreed response window |

Latency thresholds require an explicit evaluation window. Meeting targets inside each 5-minute slice of steady state differs from meeting them averaged across all 15 minutes. Choose upfront and apply consistently across healthy and fault tests.

### 9.2. Assessing Evidence Quality

Four maturity levels can be distinguished:

| Level | Example | What Can Be Concluded |
|---|---|---|
| Assertion | "Backups exist" | Intent is known; configuration and recovery remain unproven |
| Design | Diagrams and backup flow description | Intended plan is known |
| Implementation | Backup config and schedule | A mechanism is configured |
| Verification | Successful restore, measured RTO/RPO, and data checks | Observable capability under tested conditions |

Not every criterion requires destructive fault injection. Policies may rely on config inspection plus controlled access tests, while RTO targets demand real restore evidence. Match proof to requirement type.

Tie every piece of evidence to deployment version, timestamp, environment, and collection method. Load tests run before downsizing the database do not prove the smaller config still passes.

"Not applicable" requires an approved justification. "Not yet tested" must never be relabeled "not applicable".

## 10. Using Scoring While Enforcing Mandatory Gates

### 10.1. 0–4 Maturity Scale

| Score | Meaning |
|---:|---|
| 0 | No meeting mechanism exists, or known gap lacks a remediation plan |
| 1 | Idea or design exists, insufficiently implemented |
| 2 | Partially implemented or passes only under narrow conditions |
| 3 | Implemented with solid verification evidence for core requirements |
| 4 | Verified, repeatably operated, drift-monitored, and metric-driven improvement |

A score of 4 does not mean the system is invulnerable or immune to outages. It reflects mechanism and evidence maturity within the agreed scope.

Where evidence is missing, record confidence explicitly. Never award top scores merely for confident presentations or polished diagrams.

### 10.2. Illustrative Weights

| Criterion | Weight |
|---|---:|
| Security | 30% |
| Reliability | 30% |
| Performance | 20% |
| Cost | 20% |
| **Total** | **100%** |

~~~text
Total score out of 100 =
    Sum of [decimal weight × criterion score / 4] × 100
~~~

Example with scores 3, 2, 2, and 3:

~~~text
(0.30 × 3/4 + 0.30 × 2/4 + 0.20 × 2/4 + 0.20 × 3/4) × 100
= 62.5 points
~~~

Lock weights before the review session. Systems handling highly sensitive data or strict uptime demands may adjust weights. Never alter weights mid-review simply because one pillar scored low.

### 10.3. Non-Compensable Mandatory Gates

Certain requirements should serve as hard acceptance gates:

| Gate | Example Condition |
|---|---|
| G1 — Access and data | No critical unauthorized access paths remain; no active secrets exposed publicly |
| G2 — Recovery | Restore evidence meets RTO/RPO across mandatory failure scenarios |
| G3 — Load and fault tolerance | Target load and backend-loss tests pass per requirements |
| G4 — Financial | Complete estimate under approved assumptions and buffer fits budget, or new funding approved |
| G5 — Operations | Clear ownership, active alarms, and reachable runbooks exist |

A project scoring 85 points yet failing G1 or G2 may still be unfit for production. Total score is only one input to the release decision.

For conditional approvals, state whether conditions must clear before launch or during a bounded pilot, who accepts residual risk, and the permitted operating scope. Never use "conditional approval" to waive a gate designated mandatory before production.

## 11. Complete Example Evaluation for the Fictional Architecture

### 11.1. Assumed Observed State

The team supplies these illustrative findings:

- Deployment and operational permissions separated; admins use MFA; out-of-scope workload access denied.
- Database has no direct Internet access path within tested scope.
- Two app backends span distinct FDs within the active AD; full-AD loss tolerance not claimed.
- Normal load test achieves 100 req/s, p95 310 ms, 0.2% errors.
- After the agreed backend-removal window, single-instance loss test yields p95 820 ms and 3.1% errors; the surviving instance saturates.
- Data recovery drill measures RTO 36 minutes, RPO 18 minutes.
- Base cost estimate is 1,120 USD/month; approved contingency rule adds 10%.
- Alarms reach on-call staff; recurring drill schedules and named owners are still missing.

All numbers are fictional. In real projects, bind every figure to evidence from that exact test run.

### 11.2. Four-Pillar Results

| Criterion | Score | Assessment |
|---|---:|---|
| Security | 3/4 | Core permissions and access paths verified; repeatable checks need completion |
| Reliability | 2/4 | Deployment and restore mechanisms exist, yet RTO/RPO miss targets; backend-loss capacity insufficient |
| Performance | 2/4 | Passes steady state; fails under mandatory single-instance fault scenario |
| Cost | 3/4 | Cost model and sensitivity exist; buffered total exceeds budget |
| **Weighted Total** | **62.5/100** | **Not yet eligible for production acceptance** |

A cost score of 3 reflects sound measurement and evidence-backed estimation; it does not erase the budget overrun. Mandatory gates are evaluated independently.

| Gate | Outcome | Rationale |
|---|---|---|
| G1 | Passed within test scope | Checked access paths and secrets show no release blockers |
| G2 | Failed | 36 minutes > 30 minutes; 18 minutes > 5 minutes |
| G3 | Failed | Latency and error rate breach thresholds upon losing one backend |
| G4 | Failed | 1,120 × 1.10 = 1,232 USD > 1,200 USD |
| G5 | Insufficient evidence | Missing owners and recurring operational drill schedule |

The proper conclusion is continuing remediation and re-testing failed gates—never concluding "pass because steady state works" or "just add one VM and ship."

### 11.3. Actionable Findings Register

| ID | Finding | Impact | Remediation Direction | Closure Criteria |
|---|---|---|---|---|
| F-01 | Insufficient surviving capacity when losing one backend | Business errors and latency spikes on host failure | Compare adding a backend vs. upsizing shapes; inspect shared DB | Re-run fault load test meeting all thresholds and windows |
| F-02 | Data recovery sequence exceeds RTO/RPO | Fails committed recovery time and data-loss bounds | Profile each recovery step; tune restore mechanics per live DB service | Repeat restore drill with canary transactions meeting targets |
| F-03 | Buffered estimate exceeds budget | Operational funding shortfall or forced emergency cuts | Optimize with measurements or secure formal budget increase | Estimate under identical approved rules with active cost owner |
| F-04 | Drills lack schedule and named owners | Runbooks go stale; nobody validates ongoing recoverability | Assign owners, set cadence, and archive drill outcomes | Schedule, backup owners, and verified drill log in place |

In real reports, add an owner and due date to each row. Remediation options should compare alternatives rather than assuming one single service is the only answer.

### 11.4. Recalculating Cost After Reliability Fixes

Suppose the team adds one backend costing 90 USD/month. They also propose:

- Saving 20 USD via appropriate data lifecycle rules.
- Saving 25 USD by trimming unnecessary verbose logs while keeping security and forensic logs.
- Saving 35 USD by tuning network paths or transfer after verifying impact.

~~~text
New base cost = 1,120 + 90 - 20 - 25 - 35
              = 1,130 USD/month

With 10% buffer = 1,130 × 1.10
                = 1,243 USD/month
~~~

The capacity-improved option still exceeds the 1,200 USD budget. To stay within budget under the 10% buffer rule, base cost cannot exceed roughly 1,090.91 USD/month; rounding conservatively to the cent gives a maximum of 1,090.90 USD.

The team must optimize further or obtain budget approval. Never drop the contingency buffer, shrink backups below requirements, or disable mandatory logging merely to flip status to pass.

After adding a backend, re-testing remains mandatory. Load-division math and cost tables only guide selection; they are not verification results for the new configuration.

## 12. Organizing the Review Session and Re-Verification

### 12.1. Before the Review

Prepare a specific deployment version and a sanitized evidence package:

1. Summary of business goals, SLOs, RTO, RPO, budget, and dependencies.
2. As-built diagrams and per-compartment resource inventory.
3. Requirements matrix, pass thresholds, and acceptance gates.
4. Necessary configs or extracts for IAM, networking, storage, database, and observability.
5. Test plans and results, including limitations of each test.
6. Estimates, pricing assumptions, cost allocation, and sensitivity analysis.
7. Runbooks, architectural decisions, and known risks.

Never include private keys, passwords, tokens, or real customer records in submission packages. Evidence must suffice to verify configurations and behavior without introducing exposure.

### 12.2. During the Review

An effective sequence:

- Confirm scope, version, and acceptance conditions.
- Walk through business, administrative, and recovery flows.
- Verify critical requirements with concrete evidence rather than verbal descriptions.
- Compare steady-state metrics against committed fault scenarios.
- Inspect cost estimates after accounting for changes needed for reliability.
- Log findings, severity/impact, owners, and re-verification steps.
- Record gate statuses and permitted next-stage scope.

Evaluators should document scope limits of every conclusion. For instance, passing a single-instance loss test proves that scenario under the tested config; it does not automatically prove resilience to database, AD, or region loss.

### 12.3. After Remediation

Not every test needs re-running when a change affects a narrow scope, provided dependencies are mapped:

| Change | Evidence Typically Requiring Update |
|---|---|
| IAM policy edit | Authorized access, denied access, pipeline/workload behavior |
| Adding a backend | Steady-state load, backend loss, DB load, sessions, and cost |
| Changing backup method | Restore drill, RTO/RPO, permissions, keys, and retention cost |
| Changing storage tier | Retrieval behavior, recoverability, retention, and cost estimate |
| Reducing logs | Investigation coverage, alarms, sensitive-data exposure, and cost |
| Adding standby region | Networking, data, IAM/keys, cutover, failback, and cost estimate |

A finding closes only when evidence satisfies its closure criteria. "Configuration updated" is an implementation status, not proof of passing.

## 13. Architecture Review Conclusion Template

The template below outlines report content structure, not deployment commands or configs:

~~~text
SYSTEM / ENVIRONMENT:
DEPLOYMENT VERSION:
REVIEW DATE AND REVIEWER:

SCOPE:
- Regions, compartments, services, and dependencies covered.
- Failure scenarios committed for handling.
- Approved exceptions and evidence limitations.

REQUIREMENTS:
- SLOs and SLI calculation formulas.
- Load, latency, and error-rate targets.
- Per-scenario RTO/RPO targets.
- Budget, pricing basis, and contingency buffer rules.

RESULTS:
- Four-pillar scores and confidence levels.
- Status of each acceptance gate.
- Evidence tied to the evaluated version.

FINDINGS:
- ID, description, and impact.
- Priority, owner, and target date.
- Remediation action, residual risk, and verification method.

DECISION:
- Approved / not approved, and within what scope.
- Mandatory prerequisites before production operation.
- Designated authority accepting residual risk.
- Triggers or changes requiring re-evaluation.
~~~

A strong conclusion reads like:

> The current configuration passes core access-control checks and steady-state load tests. It is not yet fit for production because data recovery, single-backend loss load, and buffered cost estimates miss thresholds. The implementation team must close F-01 through F-04, update the cost estimate, and submit matching verification evidence before requesting re-acceptance.

This states results, bounds, and next actions without turning a list of OCI features into a blanket quality guarantee.

## 14. Pitfalls That Invalidate Evaluation Results

| Pitfall | Why the Conclusion Is Untrustworthy | How to Fix |
|---|---|---|
| Assuming private subnets alone mean security | Ignores IAM, routes, internal paths, and credentials | Evaluate permissions, routes, and live access tests |
| Using a service SLA as the app SLO | Ignores dependencies and business logic failures | Measure SLIs from defined user behavior |
| Assuming two instances equal full HA | May share a fault domain or lack surviving capacity | Check placement, health, and remaining capacity |
| Assuming backups alone meet RTO/RPO | Leaves restore speed, data integrity, and dependencies unproven | Drill and time the complete recovery chain |
| Load-testing tiny datasets and extrapolating to production | Misses real queries, I/O, and payload sizes | Use representative data and distributions |
| Downsizing immediately on low CPU | Threads may be DB-bound or capacity needed for failover | Inspect bottlenecks, peaks, and fault tests |
| Concluding pass from low average latency | Masks slow tails and critical write endpoints | Inspect percentiles, endpoints, and time windows |
| Treating budget alerts as hard spend caps | Alerts do not automatically block spending | Pair owners, estimates, and resource controls |
| Using promotional credits to claim low cost | Hides post-credit steady-state run rate | Separate credits from baseline operating costs |
| Averaging scores to waive severe flaws | High scores elsewhere cannot recover lost data | Keep acceptance gates independent |
| Reusing old test results for new configs | Evidence no longer matches the live system | Version-stamp evidence and re-verify changed scope |
| Accepting risk with no named owner | No traceable governance decision exists | Record approver, expiration, and conditions |

The quality of an OCI capstone shows in the traceability chain: **requirements → architectural decisions → deployment configuration → evidence → conclusions**. When this chain is complete, a team can explain not just which OCI services were assembled, but why the system meets its goals, where its boundaries lie, and what must change as demand grows.
