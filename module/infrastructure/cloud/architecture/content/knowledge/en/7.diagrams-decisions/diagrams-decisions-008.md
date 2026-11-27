# Keeping Documentation and Diagrams Synchronized with Deployed Systems

An architecture diagram is useful only when readers can rely on it to understand **what the system is actually running** and make sound decisions. A polished diagram missing a newly created database, misdrawing an Internet link as a private connection, or still depicting a decommissioned region can cause operations teams to mishandle incidents, overlook security risks, and build unworkable recovery plans.

In cloud systems, architecture can evolve with every release: a team adds a service, changes network configuration, enables replication, switches payment providers, or adds a standby region. Updating documentation from one person's memory cannot keep up with that pace. Therefore, **keeping documentation and diagrams synchronized with the deployed system must be built into the development and operations workflow**.

This lesson belongs to the **Diagrams and Decisions** chapter of the **CLOUD_ARCHITECTURE** module. The focus is connecting business requirements, decisions around networking/compute/data/deployment models, and Well-Architected verification to observable resources, configurations, data flows, and operational mechanisms. The goal is not an immutable document, but a process ensuring every significant change has an owner, gets verified, and leaves evidence.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **intended architecture**, **deployed architecture**, and **observed runtime state**, and understand why no single source serves as absolute proof for all three.
2. Choose the right document types: context, container, component, deployment, data-flow, and network diagrams, runbooks, and Architecture Decision Records (ADRs).
3. Tie architectural changes into pull requests, Infrastructure as Code (IaC), deployment pipelines, tests, and release workflows.
4. Build a reconciliation process comparing documentation against cloud resources, production configs, and observability data.
5. Design detection, classification, and remediation for **architecture drift** and out-of-band emergency changes.
6. Measure documentation freshness, evidence quality, and drift remediation time rather than merely checking whether "a doc exists".
7. Evaluate trade-offs across reliability, security, performance, cost, and operational effort under Well-Architected.

## 2. What Does "Synchronized" Mean?

### 2.1. Three Views of One System

| View | Question | Common evidence sources | What may be missing |
|---|---|---|---|
| **Intended / planned architecture** | What **should** the system consist of, and why was that decided? | Requirements, ADRs, design diagrams, policies, proposed IaC | Not necessarily deployed or enabled yet |
| **Deployed / configured architecture** | Which resources and configs **actually exist** in the target environment? | Cloud inventory/APIs, IaC state, Kubernetes configs, deployment manifests, service catalogs | May not fully reflect runtime behavior, feature flags, or live traffic |
| **Observed / runtime architecture** | Which components and call paths are **actively running**, failing, or producing data? | Traces, metrics, logs, flow logs, service mesh telemetry, test results | Sees only what is instrumented; may miss rare flows or standby resources |

For example: IaC declares a read-replica database; inventory confirms the instance exists; yet telemetry reveals the application still reads straight from the primary database. If the diagram marks the replica as serving production reads, the documentation is ahead of reality.

Another example: a load balancer has two targets across two zones, yet one target continuously fails health checks. The deployment diagram remains accurate in resource count; claiming "survives single-zone failure" still requires verification through actual serving capability.

**Principle:** explicitly state whether each diagram depicts *desired*, *deployed*, or *observed* state, which environment, and which point in time or release. Being "synchronized" means verifiable consistency between what the document claims and the system scope that claim describes.

### 2.2. There Is No Single Source of Truth for Every Layer

The *single source of truth* concept works well when applied **per type of information**, but misleads if one repository or dashboard is treated as holding the entire truth.

| Type of information | Authoritative source to designate | How to reconcile |
|---|---|---|
| **Architectural rationale** | Approved ADRs | Compare decisions against current configuration and business goals |
| **Desired infrastructure config** | Approved IaC, GitOps manifests, and policies | Plan/diff against live resource state |
| **Existing cloud resources** | Provider inventory/configuration APIs per account/region | Compare against IaC and owner catalogs |
| **Running software versions** | Deployment system and runtime rollout status | Compare against commits, artifacts, and release records |
| **Runtime dependencies and traffic** | Distributed tracing, network telemetry, and active testing | Compare against interaction diagrams and trust boundaries |
| **Operations / recovery procedures** | Owned runbooks, periodically tested | Fault drills and actual restore/failover results |
| **Security and data policies** | Approved policies, data classifications, legal/contractual rules | Config scans, IAM reviews, data-flow reviews, and audit evidence |

These systems can contradict each other; discovering a discrepancy is itself a signal to investigate. Never pick whichever source is most convenient and declare the system "in sync".

## 3. Choosing Diagrams for the Right Purpose and Abstraction Level

A good documentation set guides readers from **who uses the system** down to **which services run where, how they communicate, and how they recover**. You do not need to cram everything into one dense diagram.

### 3.1. Diagram Levels to Maintain

| Document / diagram | Target audience | Minimum content to keep updated | When to update |
|---|---|---|---|
| **System Context** | Product, architects, security, integrators | Users, external systems, responsibility boundaries, key business flows | Adding partners, external systems, data flows, or user groups |
| **Container — apps/services and data stores** | Developers, architects, SRE | Services, APIs, queues, databases, owners, and communication links | Adding/splitting/merging services, changing datastores, changing protocols |
| **Component / sequence** | Developers, reviewers | Critical components and processing order; transactions, retries, timeouts, consistency | Changing business workflows or inter-service contracts |
| **Deployment topology** | SRE, cloud/platform, security | Accounts/subscriptions, regions, zones, clusters, compute, databases, load balancers, connections | Adding zones/regions, changing HA/DR models, changing compute |
| **Network / trust boundaries** | Security, network, SRE | Public/private ingress, egress, ports/protocols, subnets, security groups, IAM boundaries | Exposing endpoints, changing DNS, routing, firewalls, private links |
| **Data-flow / data classification** | Security, data, compliance | Sensitive data, processing/storage/backup locations, cross-border transfers, access permissions | Adding data fields, replicas, analytics, CDNs, or partners |
| **ADR — decision record** | Future maintainers, reviewers | Context, options, rationale, trade-offs, consequences, and superseding decisions | Making or changing a significant decision |
| **Runbook / DR plan** | On-call, incident commanders | Failure symptoms, access rights, commands/procedures, rollback, recovery, verification | Changing operational procedures, connectivity, or tooling |

An ADR answers **why**; diagrams answer **which components connect how**; IaC answers **what desired configuration can be applied**; telemetry answers **how the system actually behaved**. Each complements the others.

### 3.2. Consistent Diagram Metadata

Every diagram needs metadata so readers know its scope. Header template:

~~~text
Name: Booking Platform - Deployment topology
Environment: production
Cloud account / project: <non-sensitive internal code>
Region: region-primary; region-dr (DR when activated)
View: deployed topology / approved design
Owner: Platform team + Booking team
Revision: release-2026.11 / related commit
Last verified: date of most recent verification
Evidence: links to inventory, IaC, releases, and dashboards
Assumptions: DR is currently in warm standby mode
~~~

Never embed private keys, tokens, passwords, or sensitive identifiers inside diagrams. When operations require exact IP addresses, account names, or resource IDs, store them in access-controlled documentation rather than publishing them openly.

### 3.3. Example: Two Views of One Product

**Logical view** describing service and data relationships:

~~~mermaid
flowchart LR
    C[Users] --> EDGE[Web / API Gateway]
    EDGE --> BOOK[Booking Service]
    EDGE --> LIST[Listing Service]
    BOOK --> DBB[(Booking DB)]
    LIST --> DBL[(Listing DB)]
    BOOK --> BUS[(Event Broker)]
    BUS --> NOTIFY[Notification Service]
    BOOK --> PAY[Payment Provider]
~~~

**Deployment view** describing failure domains and components running in one region:

~~~mermaid
flowchart TB
    CLIENT[Internet Users] --> WAF[WAF + Public Load Balancer]
    subgraph REGION[Primary Region]
        subgraph AZ1[Availability Zone A]
            APP1[App instance A]
        end
        subgraph AZ2[Availability Zone B]
            APP2[App instance B]
        end
        WAF --> APP1
        WAF --> APP2
        APP1 --> DB[(Managed DB - HA)]
        APP2 --> DB
    end
    APP1 --> EXT[Payment Partner]
    APP2 --> EXT
~~~

Both diagrams illustrate different aspects of the same system. Never infer that the database truly spans multiple zones merely from a "Managed DB - HA" label; in real deployments, verify that HA is enabled, check replication/failover status, and inspect the specific service's failure domains. Cross-region links must also appear on trust-boundary/data-flow diagrams whenever sensitive data is involved.

## 4. Architecture Drift: Where Does Divergence Come From?

**Architecture drift** is a meaningful discrepancy between the documented/approved architecture and the live system. It differs from **configuration drift** by encompassing service boundaries, data paths, runtime dependencies, availability posture, and operational decisions—not merely resource property diffs.

Common sources:

1. **Manual console edits:** operators open firewall ports, add instances, or alter IAM permissions directly in the console without updating IaC or docs.
2. **Changes across multiple pipelines:** one team updates services while another updates networking; diagrams are only partially updated.
3. **Runtime configuration:** feature flags, routing rules, service discovery, autoscaling, or canaries shift traffic away from the original design.
4. **Managed service changes:** cloud providers upgrade underlying infrastructure or adjust behavior within service agreements; not all internal changes show up in inventory.
5. **External tools and appliances:** CDNs, DNS, SaaS, on-premises systems, payment partners, and monitoring tools sit outside one cloud account's IaC scope.
6. **Write-once documentation:** docs written only at project kickoff without owners, triggers, or scheduled reviews.
7. **Multiple environments:** staging gets upgraded while production diagrams show staging's architecture, or vice versa.
8. **Emergency changes:** incident responders bypass normal workflows and later forget to document the rationale and final state.

### 4.1. Not Every Difference Is a Defect

| Difference | Acceptable? | Remediation decision |
|---|---|---|
| Scaling from 3 to 8 pods under autoscaling policy | Yes, if diagrams model workload groups and capacity bounds rather than individual pods | Keep diagrams at a stable abstraction; verify autoscaler follows policy |
| Canary shifts 10% traffic to a new version briefly | Yes, if part of an approved release | Tie rollout details to release records/runtime dashboards |
| A new public endpoint appears outside diagrams and policies | Usually a critical anomaly | Inspect exposure, owner, and change source; handle per risk severity |
| Production uses a single-zone DB while diagrams show multi-zone HA | Unacceptable if diagrams claim zone-fault resilience | Remediate infrastructure or revise design/risk assessment and record an ADR |
| Runbook points recovery steps to a deleted cluster | Unacceptable when it breaks recovery | Update and drill the runbook |
| A temporary sandbox environment is absent from production diagrams | Acceptable if scope, owner, and expiry are clearly separated | Track in a separate inventory under sandbox policy |

Never automatically add every short-lived instance to core diagrams: that ruins readability and causes needless churn. Govern **durable architectural components, security boundaries, policies, and operational characteristics**, while tracking dynamic resource counts via labels and dashboards.

## 5. "Documentation as Code" Keeps Docs Moving with Software

### 5.1. Co-Locating Documentation with Related Changes

Storing text-based docs (Markdown, Mermaid, PlantUML, or other declarative formats) in version control makes reviews, diffs, commit traceability, and rollbacks far easier than opaque binary image files without source.

Reference repository layout:

~~~text
repository/
  docs/
    architecture/
      README.md
      context.md
      containers.md
      deployment-prod.md
      data-flows.md
      decisions/
        0001-database-ha.md
        0002-event-broker.md
    operations/
      incident-response.md
      disaster-recovery.md
  infrastructure/
    network/
    compute/
    data/
  services/
    booking/
    listing/
  .ci/
    architecture-checks.yml
~~~

This is an **example layout**, not a requirement for every project to use these exact folder names. Whether documentation lives in a monorepo or a separate repository, what matters is bidirectional linking between deployment changes and related docs.

### 5.2. Artifacts That Should Be Managed as Code

| Artifact | Recommended representation | Feasible automation |
|---|---|---|
| Cloud infrastructure | Terraform/OpenTofu, CloudFormation, Pulumi, or suitable IaC tool | Plan, validate, policy checks, and inventory diffs |
| Kubernetes | Manifests, Helm/Kustomize, GitOps state | Config validation and reconcile/rollout status checks |
| APIs | OpenAPI, protobuf, AsyncAPI, or contract schemas | Compatibility checks and detecting new endpoints/events |
| Service dependencies | Service catalog, metadata, traces, and dependency graphs | Compare declared catalog against observed dependencies |
| Architecture diagrams | Reviewed text-based Mermaid/C4/PlantUML | Syntax, link, and declared-ID validation |
| Architectural decisions | ADRs with status, date, and owner | Mandatory template and PR link checks |
| Runbooks / DR | Markdown + controlled scripts/procedures | Link checks; live drills to verify accuracy |

**Limitation:** diagram generators reading IaC can see subnets, VMs, and databases, yet cannot understand business transactions, implicit dependencies, personal-data boundaries, or design rationale. Treat auto-generated diagrams as **supporting input evidence**, enriched with semantics, owners, and human review.

### 5.3. Linking Changes to Documentation

A pull request introducing architectural change should answer:

- What changes will happen in production or the target environment?
- Which documents/diagrams are affected?
- Does it add or modify public endpoints, IAM permissions, data, dependencies, regions, zones, or DR mechanisms?
- Does this decision already have an ADR, or is it an implementation detail within a prior decision?
- How will post-deploy verification confirm the live system matches claims?
- Who is responsible for reviewing architecture, security, data, and operations?

Short template for PR descriptions:

~~~markdown
## Architectural impact
- [ ] No changes to topology / trust boundaries / data flows
- [ ] Updated affected diagrams or documentation
- [ ] Updated or linked relevant ADR
- [ ] Updated runbooks and observability/DR requirements
- [ ] Checked IAM, networking, data residency, and cost

Evidence / links:
- Diagram:
- ADR:
- IaC plan:
- Release / deployment:
- Verification after deploy:
~~~

Do not force every typo fix or internal refactor to spawn a new ADR. Use real-impact triggers: protocols, data, security, failure domains, cost, deployment topology, contracts, and system behavior.

## 6. Standard Workflow from Decision to Running System

### Step 1 — Describe Requirements and Constraints

Define business capabilities, projected load, SLOs, RTO/RPO, permitted data regions, security risks, budget, and operational capacity. Example: "Booking API must continue serving if one instance fails" is a requirement; "run three instances" is merely one implementation choice.

### Step 2 — Record an ADR for Significant Choices

The ADR should capture context, options, rationale for the choice, rejected options, trade-offs, and consequences. Statuses like **Proposed / Accepted / Superseded** clarify which decisions remain active. When replacing an old decision, create or link to the superseding ADR; preserve history to investigate why the system was built that way.

### Step 3 — Update Design Diagrams and Contracts

Redraw impacted views: context/container, deployment topology, network/trust boundaries, data flows, and business sequences as needed. Explicitly mark environment, region, and **proposed** status before deployment. API/event contract changes require consumer compatibility checks.

### Step 4 — Modify IaC / Application in the Same Review Stream

Architectural changes are expressed in appropriate deployment artifacts. CI checks syntax, policies, network rules, security scans, and required doc links. Reviewers verify consistency across requirements, diagrams, ADRs, and IaC diffs rather than trusting cloud icons in pictures.

### Step 5 — Traceable Deployment

Link every deployment to its commit, artifact, environment, approver/approval method, and rollback plan. If staging and production deploy on different schedules, documentation must clarify which view applies to which environment. Alert if production config diverges from expectations or a rollout stalls.

### Step 6 — Post-Deploy Verification Against the Live System

Reconcile inventory, controller status, service discovery, health checks, metrics/traces, and IAM/network/backup configs against expectations. Promote documentation status from **proposed** to **verified deployed** once evidence is collected. If results diverge from design, open a drift item and assign remediation.

### Step 7 — Continuous Observation and Periodic Review

Schedule reconciliation for infrastructure, dependencies, ownership, diagrams, runbooks, and security configurations. Do not wait for an outage to discover an outdated diagram. Cadence depends on risk and change velocity; public endpoints, sensitive permissions, and data boundaries may require near-real-time monitoring.

### End-to-End Flow

~~~mermaid
flowchart TD
    REQ[Business requirements / SLO / constraints] --> ADR[Proposed ADR and diagrams]
    ADR --> PR[PR changing app / API / IaC / docs]
    PR --> CI{Automated checks + review}
    CI -->|Failed| PR
    CI -->|Passed| DEP[Deploy with release record]
    DEP --> VERIFY[Inventory + runtime + policy verification]
    VERIFY --> OK{Matches expectations?}
    OK -->|Yes| DOC[Mark verified and store evidence]
    OK -->|No| DRIFT[Classify drift + owner + due date]
    DRIFT --> FIX[Fix infra or update approved design]
    FIX --> PR
    DOC --> OBS[Monitor and review periodically]
    OBS --> VERIFY
~~~

In practice, organizations may span multiple pipelines and tools; this diagram defines **required control gates**, not a mandate to put everything inside a single pipeline.

## 7. Automating Checks Without Equating "Has a Diagram" with "Correct"

### 7.1. CI Checks to Implement First

1. **Source validity:** Markdown/diagram sources parse cleanly, internal links resolve, and required metadata is present.
2. **Change impact:** when IaC paths, API schemas, manifests, or IAM/network configs change, require declaring architectural impact and linking affected docs.
3. **Schema diffing:** breaking changes to endpoints/events or data structures must be flagged, requiring compatibility and rollout plans.
4. **Policy as code:** block dangerous configurations such as unauthorized public storage, overly broad security groups, or deploying into prohibited regions.
5. **Ownership checks:** new services must declare an owner, environment, criticality tier, alert channel, and minimum runbook path.
6. **Post-deploy verification:** capture deployed state, versions, and inventory; flag divergences from intended topology.

Policies can require **review evidence** for sensitive changes rather than blindly blocking every diff. For instance, introducing a new business relationship is hard to detect accurately merely by counting changed IaC lines.

### 7.2. Example Check Using a Mapping Catalog

Suppose the team maintains a declarative service catalog:

~~~yaml
services:
  - id: booking-api
    owner: booking-team
    environments: [staging, production]
    source: services/booking
    deploy_manifest: infrastructure/compute/booking
    diagram_node: BOOK
    runtime_name: booking-api
    data_classification: internal
    runbook: docs/operations/booking.md

  - id: notification-worker
    owner: communications-team
    environments: [production]
    source: services/notification
    deploy_manifest: infrastructure/compute/notification
    diagram_node: NOTIFY
    runtime_name: notification-worker
    data_classification: internal
    runbook: docs/operations/notification.md
~~~

From this same catalog, a pipeline **can** check that each declared ID maps to a node on the diagram and a matching environment resource/runtime. Example check logic:

~~~text
for each service in catalog:
    assert service.owner is assigned
    assert service.deploy_manifest exists
    assert service.diagram_node exists in logical diagram
    assert service.runbook exists
    if service is deployed to production:
        assert observed_runtime_contains(service.runtime_name)

for each observed production service:
    if not exists_in_catalog(service) and not has_approved_exception:
        report_architecture_drift(service)
~~~

This is **illustrative pseudocode**, not a runnable script. Runtime names must map explicitly per environment and platform; one logical component may deploy across multiple workloads. CI should report discrepancies and evidence, while whether to hard-block or alert depends on severity.

### 7.3. Checking via Cloud APIs and Runtime State

A reconciliation job can pull inventory per account/project and region and normalize durable properties:

- Resource type, ID, owner, environment, and governance tags.
- Region/zone, subnet/VPC/VNet, public endpoints, routes, and security policies.
- Compute services with deployed versions/images and deployment targets.
- Databases, replication/failover, backup policies, and encryption settings.
- Messaging topics/subscriptions and declared third-party endpoints.

Reconcile these fields against IaC state/plans, the service catalog, and architecture diagrams. Separate **discovered undeclared resources**, **expected missing resources**, **unexpected configurations**, and **unexpected dependency paths** into distinct drift categories. Inventory alone does not prove business flows work correctly; telemetry and real tests remain essential.

### 7.4. Watch Out for Observability Blind Spots

- Traces show only instrumented and sampled requests; rare flows may be absent during a capture window.
- IaC does not reflect all SaaS settings, temporary overrides, or out-of-band manual changes.
- Cloud inventory may miss outbound partner links or services managed in other accounts.
- Feature flags can make live traffic diverge from default flows even when binaries and manifests match.
- Diagram generators may crowd pictures with low-level infrastructure resources while missing business semantics.

Verification reports should state **coverage scope, timestamp, and confidence level**, avoiding labels like "100% synchronized" when the entire system cannot be observed.

## 8. Managing Emergency Architectural Changes

During production incidents, on-call engineers may need to open temporary routes, disable features, raise quotas, or shift traffic to restore service. Documentation processes must support emergencies while preserving auditability and reversibility.

Minimum workflow:

1. **Log the action:** timestamp, operator, incident ID, intent, and modified target; capture audit logs if tooling supports it.
2. **Immediate risk check:** public exposure, sensitive data, region changes, cost, single points of failure, and blast radius.
3. **Restore service:** apply changes within delegated authority; monitor business, error, and security signals.
4. **Post-incident reconciliation:** document gaps between live runtime state and IaC/docs; decide whether to codify the change or roll it back.
5. **Update via PR/ADR:** bring accepted state into managed config, update diagrams and runbooks, and close exceptions with evidence.
6. **Postmortem improvements:** examine why docs were insufficient or runbooks fell short; add needed alerts and automation.

**Never blindly "reconcile" by reverting manual emergency changes that are actively keeping the service alive** before understanding incident state. Conversely, an emergency change opening public access must never become a permanent exception just because "the system looks stable now". Enforce a due date, owner, and formal risk acceptance.

## 9. Example: Adding a Database Replica and Shifting Read Paths in a Booking System

Suppose a booking product has a Booking API and primary database. As booking-history query traffic grows, the team proposes adding a **read replica** to offload reads. The business requirement is keeping response times stable without serving inaccurate transaction confirmation data.

### 9.1. Before the Change

~~~mermaid
flowchart LR
    WEB[Web / Mobile] --> API[Booking API]
    API --> DB[(Primary DB)]
~~~

At this stage, logical and deployment diagrams may show a single primary DB. The team must know which queries require read-after-write consistency, which reports tolerate stale data, and the primary's real HA/backup posture.

### 9.2. Controlled Decision and Change

The team writes an ADR: "Use a read replica for latency-tolerant history queries; checks on newly created bookings continue reading from primary." Affected areas include:

- **Logical architecture:** Booking API classifies queries needing strong/read-your-writes consistency versus history lists tolerant of replication lag.
- **Infrastructure:** add a replica in a compliant region/zone; configure connections, secrets, monitoring, quotas, and replication-lag alerts.
- **Application:** route eligible queries to the replica endpoint with explicit fallback and load limits.
- **Documentation:** update container/deployment diagrams, ADR, data-flow docs, runbooks, and dashboards.
- **Testing:** verify post-write queries remain consistent; test replica lag or unavailability; verify behavior during primary failover.

**Intended post-change diagram:**

~~~mermaid
flowchart LR
    WEB[Web / Mobile] --> API[Booking API]
    API -->|Writes + reads needing freshest data| PRI[(Primary DB)]
    PRI -->|Replication| REP[(Read replica)]
    API -->|Lag-tolerant history reads| REP
    REP --> LAG[Metric: replication lag]
~~~

### 9.3. Recording Evidence at Each Milestone

| Milestone | Docs / evidence | Responsible party |
|---|---|---|
| Pre-deploy | Accepted ADR, Proposed diagram, IaC plan, app compatibility tests | Architect, Booking lead, Platform |
| Post-staging | Replica exists, health/lag measured, queries routed properly, failure cases tested | Booking + SRE |
| Post-production | Deployment version, replica inventory, read-path logs/traces, and replication-lag dashboard | SRE/Platform |
| Upon verification | Diagram marked Verified for production with timestamp and evidence links | Document owner |
| After operating period | Review cost, performance, lag metrics, residual risks; keep or supersede ADR | System owner |

If the replica has been provisioned yet the application has not switched traffic, the "deployed resources" diagram can show the replica while the "observed read path" view must still show reads hitting primary. This distinction prevents diagrams from intentionally or accidentally claiming unlaunched behavior.

### 9.4. Drift Scenarios to Catch

**Scenario A:** an engineer routes queries requiring immediate consistency to the replica, causing users not to see just-confirmed bookings. Functional CI tests and traces catch this even though IaC did not change.

**Scenario B:** replication lag spikes after an incident. Infrastructure config still matches the diagram, yet the read model's freshness guarantee fails; dashboards/alerts must guide operators to runbooks and degraded-mode handling.

**Scenario C:** a new replica is created in a different region without evaluating data residency, backups, and access paths. Inventory diffs and policy checks must catch this; if restricted data is moved, run a compliance review before recognizing the new architecture.

## 10. Well-Architected Evaluation

| Pillar | Verification questions | Example evidence / impact |
|---|---|---|
| **Operational Excellence** | Do owners and runbooks match production? Do changes link PRs, ADRs, and deployments? | Incident drills, change history, last verified dates, service catalog coverage |
| **Security** | Do trust-boundary and data diagrams reflect live public endpoints, IAM, and processing locations? | Security group scans, policy reports, access logs, data-flow reviews |
| **Reliability** | Do diagrams depict failure domains accurately? Are HA/DR and backup/failover tested? | Zone-loss tests, restore results, measured RTO/RPO, and dependency maps |
| **Performance Efficiency** | Do diagrams surface long call chains, bottlenecks, or cross-region hops? | Trace latency, throughput, replication lag, load tests |
| **Cost Optimization** | Do resources have owners; did topology changes account for compute, storage, network, and logs? | Tagged inventory, cost allocation, PR cost estimates, idle-resource reports |
| **Sustainability** | Are unused resources or redundant replicas decommissioned? | Idle resources, utilization, sensible retention, right-sized replication |

A synchronized diagram helps **evaluate** these pillars, yet does not by itself create reliability or compliance. Outcomes must be proven via testing, audits, production metrics, and clear decision authority.

### 10.1. Level of Detail and Maintenance Cost

Drawing every pod, rotating IP address, or ephemeral queue causes diagrams to rot immediately. Conversely, writing only "Frontend → Backend → Database" lacks the detail needed to assess HA, IAM, or data residency. Pick detail based on real questions:

- **Logical diagrams** capture durable responsibility boundaries, contracts, and dependencies.
- **Deployment diagrams** capture environments, regions/zones, fault boundaries, and operationally significant resources.
- **Dashboards/inventories** track live instance counts, pods, IPs, and point-in-time health.
- **Data-flow and trust-boundary views** show where sensitive data travels, access controls, and processing points.

The goal is minimizing **the cost of keeping docs accurate** while maintaining enough precision for architectural decisions and incident response.

## 11. Measuring Synchronization Quality

"Number of diagrams written" does not measure reliability. Track verifiable metrics instead:

| Metric | Meaning | Pitfall to avoid |
|---|---|---|
| **Coverage** | Share of critical services/resources with assigned owners and linked docs in audit scope | Do not count auto-scaled instances as separate new services |
| **Freshness** | Time elapsed from an impactful production change to doc update/re-verification | "Recently edited file" does not guarantee accurate content |
| **Drift count and severity** | Open discrepancies broken down by security/reliability/contract/visibility | Avoid comparing raw totals when scan scope changes |
| **Time to reconcile** | Time from detection to remediation or formal risk acceptance with clear owner | Never silence alerts by deleting findings |
| **Post-deploy verification rate** | Share of deployments with post-deploy config/runtime verification | Do not mistake passing CI for verified production behavior |
| **Runbook exercise success** | Outcomes of recovery/incident drills within defined scope | Checking "link opens" does not prove a runbook works |

**Example calculation:** when a project has 20 critical services and 17 have verified owners, runbooks, and diagrams meeting criteria:

~~~text
Documentation coverage = 17 / 20 = 85%
~~~

This is solely an illustrative formula. Explicitly state the denominator, "complete" criteria, and audit date. Never impose one blanket threshold across all projects without considering criticality and observability.

## 12. Practical Checklists

### 12.1. Before Approving an Architectural Change

- [ ] Business goals, SLOs, RTO/RPO, data regions, and major risks are defined.
- [ ] Owners exist for services, docs, diagrams, ADRs, and related operational workflows.
- [ ] Diagrams state environment, scope, date/version, and proposed vs. deployed status.
- [ ] Added/removed components and links across IAM, networking, regions, data, and dependencies are checked.
- [ ] Significant changes have an ADR documenting choices, trade-offs, and consequences.
- [ ] IaC/API schemas/deployment manifests are reviewed and linked to affected docs.
- [ ] Runbooks, DR, monitoring, costs, and security checks are reviewed for the change's scope.

### 12.2. Post-Deploy and During Operations

- [ ] Release record, commit/version, and environment match the running configuration.
- [ ] Inventory and live config have been reconciled against IaC/manifests and diagrams.
- [ ] Critical links and dependencies are confirmed via telemetry or tests.
- [ ] Claims about HA, backups, access controls, and data flows carry matching evidence.
- [ ] Drift is logged by severity with an owner, detection date, and remediation plan.
- [ ] Runbooks are drilled at a risk-based cadence and corrected whenever steps diverge.
- [ ] Emergency changes are reconciled and brought under version control post-incident.
- [ ] Old docs/ADRs are clearly marked superseded or archived so readers do not mistake them for current architecture.

## 13. Applied Exercises

### Exercise A — Live System Differs from Diagram

The production diagram shows two availability zones and an HA database. In inventory, the team discovers all compute sits in a single zone and the database is a single instance without failover enabled.

**Question:** Can you just edit the diagram labels and mark the issue closed?

**Hint:** Not enough. Check the approved zone-resilience requirement, find out why deployment diverged, assess current risk, and decide whether to fix infrastructure or approve a design change via ADR. Update diagrams to reflect current reality, attach evidence, and drill fault tolerance before claiming HA.

### Exercise B — Adding a Partner Webhook

The Payment team adds an inbound Internet webhook callback to a new endpoint. The PR updates application code without modifying IaC because the endpoint path already exists on the gateway.

**Question:** Which docs must be updated and what needs checking?

**Hint:** Update context/container or sequence diagrams for the payment flow, trust-boundary/data-flow diagrams, and the webhook contract. Verify signature validation, replay protection, idempotency, permissions, sensitive-payload handling, logging, timeouts, retries, rate limits, and owner/alerts. Never rely solely on "did IaC change?" as the trigger for doc updates.

### Exercise C — Production Emergency Rescue

During an incident, on-call shifts routing so 100% of traffic goes to a standby cluster. The system stabilizes, yet the repository still declares the old route.

**Question:** How do you stop GitOps/IaC from accidentally reverting the state keeping the system alive?

**Hint:** Log the incident and emergency change, inspect reconcile policies before re-enabling automation, open a PR codifying the desired steady state or plan a controlled rollback, and verify runbooks and diagrams match production. Track the exception with an owner, deadline, and closure condition.

### Exercise D — Auto-Generated Diagram

A cloud scanner generates a diagram with 300 resources. It shows every VM, yet contains no service owners, no sensitive-data markers, and no API-to-API call paths.

**Question:** Should this count as complete architecture documentation?

**Hint:** No. You can use the generated diagram/inventory as deployed-topology evidence, yet you still need logical views, trust/data flows, owners, ADRs, runtime dependencies, SLOs, and runbooks. Pick the right abstraction level for reviews instead of dumping every resource into one picture.

## 14. Practical Conclusion

Keeping docs and diagrams synchronized with the cloud is not a "redraw after every sprint" chore. It is a continuous control loop:

**Requirements → Decisions → Diagrams → Managed Config → Deployment → Live-State Verification → Drift Logging → Updates.**

Diagrams must state clearly **what they depict, in which environment, as of when, and who verified them**. IaC governs desired infrastructure; inventory reflects existing resources; telemetry and drills reveal how the system truly behaves; ADRs preserve rationale and trade-offs. Only when these sources connect and discrepancies follow a clear remediation workflow can teams rely on documentation to evaluate architectural correctness, handle incidents, and improve systems under Well-Architected.
