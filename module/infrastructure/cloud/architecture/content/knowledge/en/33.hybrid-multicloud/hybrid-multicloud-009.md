# Provider Exit Strategy and Portability Verification

> **Chapter:** Hybrid and Multi-Cloud  
> **Scope:** Designing cloud application architectures from business requirements through networking, compute, data, and deployment models. This lesson focuses on reducing provider dependence, proving the ability to migrate workloads and data, and managing cost, security, reliability, and operations during an exit with a Well-Architected mindset.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish portability, interoperability, reversibility, and exit strategies.
2. Inventory provider dependencies across compute, data, identity, networking, observability, control planes, commercial terms, and operations.
3. Define triggers, scope, goals, and portability tiers for each workload.
4. Compare alternative platforms by capabilities, semantics, performance, security, cost, and operability.
5. Design controlled data export, migration, cutover, rollback, and retirement.
6. Organize portability tests, migration rehearsals, and exit drills with quantitative evidence.
7. Estimate exit costs, timelines, risks, and staffing to invest appropriately in portability.

## 1. Why Is a Provider Exit Strategy Needed?

An organization may choose a cloud provider for scalability, regions, managed services, pricing, security, or ecosystem. Over the years, applications can become deeply tied to the provider’s APIs, databases, event services, IAM, networking, proprietary runtimes, backups, observability, and operational procedures.

When it is time to move, the difficulty rarely lies in provisioning VMs or copying container images. Harder questions arise:

- Can data be exported completely, in the right format, and remain readable?
- Does the new database preserve identical transaction, isolation, query semantics, and consistency?
- Can identities, permissions, keys, and audits be recreated equivalently?
- Can network connectivity, DNS, certificates, private endpoints, and routing be migrated?
- Do events, queues, schedulers, and workflows preserve semantics?
- Does the target provider satisfy performance, capacity, DR, and security requirements?
- Do contracts, licenses, egress fees, and data deletion obligations permit leaving?
- Does the operations team have the skills, runbooks, and tooling to run the new platform?

An **exit strategy** is an executable plan to reduce, replace, or terminate usage of a provider/service within a defined scope, with clear goals, timelines, accountability, costs, evidence, and recovery plans.

Not every workload needs immediate portability to every cloud. A native service can deliver greater value than its lock-in cost. What matters is that the organization understands the dependency, the consequences of leaving, and the actual switching cost.

### 1.1. Distinguish Key Concepts

| Concept | Meaning | Example |
| --- | --- | --- |
| Portability | Ability to move workloads/data/config to another environment with bounded changes | Container image running on compatible runtimes |
| Interoperability | Two distinct systems can exchange data and coordinate | Cloud app calling an on-premises API |
| Reversibility | Ability to reverse or withdraw from a technology/provider choice | Exporting data, swapping APIs, and decommissioning services |
| Exit strategy | Governance plan to execute a departure | Migrating databases, cutting over traffic, terminating contracts |
| Vendor lock-in | Technical, financial, or contractual barriers making provider exit hard or costly | Proprietary data models and APIs |
| Multi-cloud | Running workloads across multiple cloud providers | Multiple providers serving different workloads |
| Hybrid cloud | Combining cloud with private/on-premises environments | Sensitive data hosted in a private environment |

Multi-cloud does not automatically prove portability. A system can run on two clouds while still relying on proprietary databases, distinct identity models, and separate operational processes.

## 2. Define Exit Triggers, Scope, and Goals

Do not start by picking a target cloud. First identify what you need to exit from and why.

### 2.1. Exit Triggers

Triggers can include:
- Provider price increases or pricing model changes.
- Regions/services failing availability, latency, or capacity targets.
- Service deprecation or end-of-support.
- Changing data residency, compliance, or sovereign control requirements.
- Vendor changes to contracts, data terms, or support.
- Provider concentration risk exceeding risk appetite.
- Quotas or provisioning capacity no longer meeting business needs.
- Mergers, divestitures, or product strategy shifts.
- A service becoming uncompetitive on cost/performance.

Triggers should have explicit thresholds. “Too expensive” must translate into a measurable condition such as unit cost exceeding budget for consecutive periods after checking utilization and optimization opportunities.

### 2.2. Types of Exit Goals

| Goal | Scope | Example |
| --- | --- | --- |
| Service exit | Replace one managed service | Moving a queue to another broker |
| Data exit | Export and transfer data | Migrating object storage |
| Workload exit | Move one application | Migrating an API and workers |
| Region exit | Leave one region | Moving workloads out of an unsuitable region |
| Provider exit | Terminate provider usage | Migrating workloads, data, and control planes |
| Partial exit | Reduce footprint while retaining selected services | Replacing workflows while keeping CDN for a term |
| Contractual exit | End contract and handle data obligations | Exports, deletion evidence, closing accounts |

Each goal carries different scope, cost, and risk. You do not have to move an entire cloud at once.

### 2.3. Success Criteria

An exit is considered complete only when:
- Users complete business journeys within SLO.
- Data is complete, accurate, and reconciled.
- Identity, authorization, keys, and audits satisfy policy.
- Backup/restore, DR, and incident processes are validated.
- Performance/capacity meet load and failure headroom targets.
- Operating costs stay within budget.
- External integrations work properly.
- Data retention/export/deletion with the old provider is finished.
- Contracts, licenses, support, and accounts are closed properly.

## 3. Inventory Dependencies and Assess Lock-In

Inventories must capture actual dependencies, not merely list services on an invoice.

### 3.1. Dependency Layers

| Layer | Examples | Portability questions |
| --- | --- | --- |
| Compute/runtime | VMs, proprietary functions, containers, orchestration, GPUs | Can code and runtimes run elsewhere? |
| Storage | Block, object, file, archive, snapshots | Do exports preserve metadata, versions, and retention? |
| Database | Relational, NoSQL, warehouses, search | Are schemas, transactions, queries, and consistency equivalent? |
| Messaging | Queues, event buses, streams, schedulers | Ordering, delivery, retries, retention, and replay? |
| Identity | IAM, SSO, workload identity, KMS | How do principals, roles, federation, and policies map? |
| Network | VPCs/VNets, firewalls, private endpoints, DNS | Can routing, segmentation, and connectivity be recreated? |
| Security | KMS, HSM, WAF, secrets, threat detection | How do key custody, audits, and controls transfer? |
| Observability | Metrics, logs, traces, alerts | Can history be exported and metric meanings preserved? |
| Delivery/control plane | IaC, registries, GitOps, deployment APIs | Can resources and state be migrated? |
| Operations | Runbooks, support, quotas, incident tooling | Can the team operate and recover? |
| Commercial/legal | Contracts, egress, licenses, committed spend | Export rights, fees, notice periods, and deletion terms? |

### 3.2. Direct and Indirect Dependencies

- **Direct dependency:** the application calls provider-specific APIs or SDKs.
- **Transitive dependency:** frameworks/libraries depend on other services.
- **Operational dependency:** deploys, backups, monitoring, or incidents only run through proprietary consoles/APIs.
- **Data dependency:** schemas, formats, metadata, or semantics tied to a service.
- **Commercial dependency:** licenses, committed spend, egress fees, or termination clauses.
- **Knowledge dependency:** only a small group understands the automation and operations.

An application that never imports a cloud SDK directly can still be locked in through database extensions, queue semantics, IAM policies, proprietary SQL, workflow engines, or deployment controllers.

### 3.3. Dependency Graph

~~~mermaid
flowchart TB
    APP["Business application"] --> API["Managed API / runtime"]
    API --> DB[("Managed database")]
    API --> Q["Provider event / queue"]
    API --> IAM["Provider IAM"]
    API --> SEC["KMS / secret manager"]
    API --> OBS["Logs / metrics / tracing"]
    Q --> WF["Managed workflow"]
    WF --> DB
    DB --> BK["Provider backup / snapshot"]
    IAM --> K["Provider key control plane"]
    OBS --> SIEM["Security analytics"]
~~~

Graphs expose high-fan-out dependencies. When many workloads share one identity, key, or event platform, the exit cost of that shared component can exceed that of an individual application.

### 3.4. Score Lock-In Severity

Evaluate each dependency across:
- Technical specificity: how proprietary are the APIs, data models, and semantics?
- Data gravity: how large, rapidly changing, or hard to export is the data?
- Substitutability: are equivalent alternatives available?
- Migration complexity: number of steps, downtime, and code/config changes.
- Operational readiness: skills, runbooks, tooling, and support.
- Commercial friction: egress, contracts, licenses, and notice periods.
- Blast radius: number of workloads/journeys affected.
- Recovery constraints: can you roll back or run in parallel?

Qualitative reference scale:
- Low: open standards, easy export, multiple alternatives, automated tests.
- Medium: requires adapters, schema changes, or partial operational adjustments.
- High: proprietary APIs/formats, large datasets, differing semantics, long dual-run.
- Very high: incomplete exports, legal/commercial barriers, or business behavior cannot be recreated within the required timeframe.

Never use a composite score to hide severe blockers in data portability or legal exit terms.

## 4. Choose an Appropriate Portability Strategy

Portability carries cost. Making everything portable at every layer can cause over-abstraction, forfeit managed service benefits, and increase toil.

### 4.1. Strategies

| Strategy | Description | Best fit | Trade-off |
| --- | --- | --- | --- |
| Native-first with documented exit | Use native services with exit analysis and exports | High provider value, acceptable lock-in | Exit may require a major project |
| Open standards | Favor standard protocols/formats | Interoperability needed | Standards do not guarantee identical semantics |
| Portable runtime | Containers/Kubernetes/standard runtimes | Workloads needing mobility | Complex platform operations |
| Adapter/abstraction | Encapsulate provider APIs behind interfaces | Multiple implementations or planned swaps | Abstraction drift |
| Data-first portability | Prioritize exports, schemas, CDC, and open formats | Data gravity is the primary risk | May sacrifice some native optimizations |
| Active multi-cloud | Operate multiple providers simultaneously | Strict resilience/regulatory mandates | High cost, consistency, and complexity |

### 4.2. Do Not Abstract Everything

A generic interface for object storage can obscure differences in:
- Versioning and object lock.
- Multipart upload/copy.
- Event notifications.
- Lifecycle/retention.
- Encryption contexts and key policies.
- Consistency and listing semantics.
- Request pricing and egress.
- Metadata, tagging, and access controls.

Adapters should preserve necessary capabilities. Forcing an overly narrow common denominator can strip critical performance or security features.

### 4.3. Workload Portability Tiers

- **Tier 0 — Native commitment:** uses specialized services; has exit analysis and accepts high migration time/cost.
- **Tier 1 — Exportable:** has data exports, API contracts, and runbooks; replacement requires a migration project.
- **Tier 2 — Replaceable:** has adapters/standards, automated tests, and tested target options.
- **Tier 3 — Rehearsed portable:** can deploy/migrate via rehearsed, measured procedures.

Tiers are a governance tool, not a quality ranking. Critical workloads may warrant Tier 2/3; lower-criticality workloads can accept Tier 0 when the business case is clear.

## 5. Select Targets Using Capability Mapping

Do not pick a target provider from product lists or compute prices alone. Compare capabilities and semantics.

| Capability | Current platform | Target platform | Verification questions |
| --- | --- | --- | --- |
| Compute | Managed containers/functions | Runtime/Kubernetes | Startup, autoscaling, networking, limits |
| Database | Managed relational | Managed or self-managed DB | SQL dialect, isolation, replication, backups |
| Events | Proprietary event bus | Alternate broker | Ordering, retention, replay, delivery |
| Identity | Provider IAM | Federation/OIDC/workload identity | Role mappings, tokens, auditing |
| Secrets/KMS | Native vault | Alternate KMS/HSM/secret manager | Key custody, rotation, envelope encryption |
| Object storage | Proprietary object API | Compatible storage | Versioning, lifecycle, retention, metadata |
| Observability | Native monitoring | OpenTelemetry + backend | Metric semantics, trace context, alerts |
| Network | VPC/private endpoints | Target network | Routing, DNS, firewalls, latency |
| Delivery | Provider IaC | Alternate IaC/GitOps | State migration, drift, policies |

“S3-compatible,” “Kubernetes-compatible,” or “PostgreSQL-compatible” is insufficient to assume compatibility. Test real operations, limits, failure behavior, and performance.

### 5.1. Capabilities Over Product Names

Express requirements as capabilities:
- What delivery semantics does the durable queue require?
- What isolation level does the transactional database need?
- What versioning, retention, and legal holds does the object store need?
- What workload identity federation and conditional policies does IAM need?
- What durable execution, compensation, and auditing does the workflow need?
- What cardinality, retention, and trace propagation does observability need?

Then map capabilities to current services and target candidates. This avoids picking targets solely by similar product names.

## 6. Application, Runtime, and Control-Plane Portability

### 6.1. Reduce Proprietary API Coupling in Business Logic

Do not let business logic call cloud SDKs in hundreds of places without reason. Place adapters around object storage, queues, email, secrets, or identity. Interfaces must capture required business semantics and have contract tests for each implementation.

~~~mermaid
flowchart LR
    DOMAIN["Business logic"] --> PORT["Application port / interface"]
    PORT --> A["Provider A adapter"]
    PORT --> B["Provider B adapter"]
    A --> AAPI["Provider A API"]
    B --> BAPI["Provider B API"]
~~~

A queue interface should not model only `publish` if the application needs ordering, deduplication, delays, retries, dead-lettering, and replay. Contracts must specify actual guarantees.

### 6.2. Containers Do Not Guarantee Full Workload Portability

Remaining dependencies include:
- Persistent volume/CSI drivers can be provider-specific.
- Load balancer/ingress annotations differ.
- IAM integrations and secret injection differ.
- Storage classes, network plugins, and service meshes have distinct semantics.
- Autoscaling signals and quotas differ.
- GPUs/accelerators and kernel capabilities differ.
- Runtime security and admission policies are not identical.

Inventory manifests, operators/CRDs, image architectures, persistent state, node requirements, and runtime controls.

### 6.3. IaC and Control Planes

Terraform/Pulumi or similar tools do not make every resource portable. Provider-specific resources, data sources, and state may still require rewrites.

To reduce lock-in:
- Separate common-logic modules from resource-specific modules.
- Use clear input/output contracts.
- Version-pin providers and modules.
- Review plans, state migrations, and drift.
- Never assume similarly named resources behave identically.
- Run automated policy/security tests against the target.
- Store exported inventories, configs, and dependency graphs.

Never edit state files manually without understanding the format and locking/backup procedures. State can contain secrets and must be protected as sensitive data.

## 7. Data Portability: Often the Hardest Part

### 7.1. Data Inventory

Classify data requiring handling:
- Primary databases and replicas.
- Objects/files/blobs, metadata, and versions.
- Queues/topics/event logs and consumer offsets.
- Search indexes and materialized views.
- Caches/session state.
- Backups, snapshots, and archives.
- Audit/log/trace/security events.
- Encryption keys, certificates, and secrets.
- Schema registries, data catalogs, lineage, and retention metadata.

Not all data must be migrated. Caches can be rebuilt; audit logs may need long-term retention; queues may need draining or replay; keys may have to remain in the current HSM by policy prior to re-encryption.

### 7.2. Export Formats and Semantics

Verify:
- Is the format open and well documented?
- Does the export include schemas, indexes, constraints, and metadata?
- Are timestamps/time zones, encodings, and collations preserved?
- How are transaction boundaries and ordering represented?
- Can object versions, retention/legal holds, and tags be exported?
- Are delete markers, tombstones, and soft deletes preserved?
- Are checksums and manifests included?
- Do export APIs impose limits, throttling, or fees?

CSV is rarely a complete database export. It can drop constraints, sequences, binary fields, indexes, transaction state, and relationships.

### 7.3. Data Migration Patterns

| Pattern | Approach | When suitable | Risks |
| --- | --- | --- | --- |
| Offline bulk copy | Stop writes, export/import, verify, then cut over | Small datasets or tolerable downtime | Long downtime |
| Online bulk + CDC | Copy baseline then sync change logs | Large datasets, low downtime | Lag, ordering, schema compatibility |
| Dual-write | Write to both systems during transition | Clear semantics and idempotency | Partial success and divergence |
| Event replay | Rebuild target from event history | Complete logs, stable contracts | Retention, versioning, poison events |
| Logical replication | Replicate database changes | Supported engines, compatible target | Types, DDL, sequences, extensions |
| Snapshot/restore | Snapshot and restore on target | Compatible formats | Version/region constraints |

Do not use dual-write merely to minimize downtime. It creates distributed transactions where one side succeeds and the other fails. If needed, enforce outbox/inbox, idempotency, reconciliation, and an explicit source of truth.

### 7.4. Data Validation

Check:
- Record counts by table/partition/tenant.
- Checksums/hashes per batch or object.
- Aggregate business totals.
- Referential integrity and constraints.
- Null, duplicate, and outlier profiles.
- Final sequences/offsets/timestamps.
- Query result comparisons.
- Source/target reconciliation.
- Controlled spot checks of sensitive records.

Matching row counts alone does not prove data equivalence. Recent transactions may be missing, time zones shifted, tombstones lost, or numeric precision altered.

## 8. Identity, Security, and Key Portability

### 8.1. Identity Mapping

Roles and permissions cannot be translated one-to-one by name. Map:
- Human identities, groups, and federation.
- Workload/service identities.
- Roles, resource scopes, and conditions.
- Cross-account/project access.
- MFA, privileged access, and break-glass paths.
- Token issuers/audiences and trust policies.
- Audit principals and attribution.

Test both allow and deny cases. Broader permissions on the target can be a severe bug even when the application works.

### 8.2. Secrets and Encryption Keys

Secrets/passwords can be regenerated on the target; encryption keys are not always exportable or permitted to be exported. Clarify key custody, ownership, HSM/KMS capabilities, envelope encryption, rotation, and re-encryption strategies.

Options may include:
- Keeping keys at the source during dual-run while the target calls over a protected network.
- Re-encrypting data at the source using an approved intermediate format.
- Decrypting/re-encrypting in a controlled environment with auditing and separation of duties.
- Using customer-managed keys that can be imported/replicated if provider and policy permit.

Never export plaintext keys into tickets, file shares, or build pipelines just to speed up migration.

### 8.3. Security Control Parity

The target needs equivalent controls or approved residual risks:
- TLS/mTLS, encryption at rest.
- Network segmentation, egress controls.
- IAM least privilege, workload identity, JIT admin.
- Secret management and rotation.
- Vulnerability scanning, provenance, and runtime hardening.
- Logging, retention, alerting, and incident response.
- Backup immutability and restore testing.
- Data residency, deletion, and auditing.

Control parity does not require identical products; it requires proving equivalent security outcomes against the threat model.

## 9. Networking, Connectivity, and Traffic Cutover

Moving workloads can require updating IP ranges, subnets, routes, firewalls, VPN/private interconnects, DNS, certificates, load balancers, WAFs, service discovery, NAT, egress allowlists, and partner integrations.

### 9.1. DNS Cutover

Lower DNS TTLs help some clients pick up endpoints sooner, but do not guarantee every resolver/client updates immediately. Steps:
1. Verify domain/zone management permissions and records.
2. Lower TTL ahead of cutover with sufficient lead time.
3. Prepare target endpoints and certificates.
4. Verify health, routing, firewalls, and capacity.
5. Shift traffic by percentage/weighted routing if supported.
6. Monitor connections, errors, latency, and business SLIs.
7. Keep the old source active during the rollback window.
8. Raise TTL back to target only after stabilization.

### 9.2. Traffic Cutover Patterns

| Pattern | Approach | Advantages | Controls needed |
| --- | --- | --- | --- |
| Big-bang | Shift all traffic at once | Simple schedule | Large blast radius and rollback |
| Weighted/canary | Shift incrementally | Reduces risk | Session affinity and data writes |
| Blue-green | New environment runs in parallel | Clear switch point | Dual-run cost and data sync |
| Cell/tenant waves | Migrate tenant cohorts | Isolates blast radius | Tenant routing |
| Regional waves | Migrate region by region | Fits data locality | Cross-region dependencies |

If both environments accept writes without clear replication/ownership, weighted traffic can cause data divergence.

## 10. Migration and Cutover Runbook

### 10.1. Preparation Phase

- Define source/target, owners, scope, and success criteria.
- Freeze or tightly control schema/API changes during the migration window.
- Verify quotas, networking, identity, keys, registries, and dependencies.
- Capture data/performance/cost baselines.
- Rehearse bulk copy and measure duration.
- Verify backup/restore on the target.
- Prepare traffic routing and DNS.
- Prepare communications, escalation, and incident command.
- Verify rollback preconditions and decision owners.

### 10.2. Cutover Phase

~~~mermaid
flowchart TD
    A["Preflight: capacity, security, backup"] --> B["Initial data copy"]
    B --> C["CDC / replication catch-up"]
    C --> D["Validate data and application"]
    D --> E{"Cutover gates pass?"}
    E -->|"No"| X["Stop, repair or abort rehearsal"]
    E -->|"Yes"| F["Freeze writes / drain transactions"]
    F --> G["Final sync and reconciliation"]
    G --> H["Switch routing and identity paths"]
    H --> I["Smoke / synthetic / business checks"]
    I --> J{"SLO and correctness pass?"}
    J -->|"No"| K["Rollback or forward recovery decision"]
    J -->|"Yes"| L["Observe stabilization window"]
    L --> M["Accept target as primary"]
    M --> N["Retire source after exit criteria"]
~~~

### 10.3. Cutover Gates

Never promote the target as primary merely because a migration job reports completion. Gates should include:
- Replication lag at zero or within approved thresholds.
- Final sequence/offset reconciled.
- Data checksums and business aggregates verified.
- Target schema/version supported by applications.
- Identity/authorization tests passing.
- Encryption/backup/restore verified.
- Latency/throughput/capacity meeting load targets.
- Error rates and business SLIs within thresholds.
- On-call, escalation, and runbooks ready.
- Risk owner/change approver confirms cutover.

## 11. Rollback and Return Decisions

Data rollback is harder than application rollback. Once the target accepts new writes, returning to the source can lose transactions unless reverse-synchronized.

### 11.1. Rollback Window

Before cutover, define:
- How long the source is kept and whether data can reverse-sync.
- Whether the source stays writable or is fenced/read-only.
- Whether reverse replication exists.
- Which external side effects have occurred.
- What reconciliation or compensation is needed.
- When rollback is no longer safe and roll-forward is mandatory.

~~~mermaid
flowchart TD
    A["Target has issue after cutover"] --> B{"Any new writes?"}
    B -->|"No"| C["Route to source if still valid"]
    B -->|"Yes"| D{"Reverse sync/reconcile reliable?"}
    D -->|"Yes"| E["Freeze, reverse sync, validate, rollback"]
    D -->|"No"| F["Keep target and forward-fix/manual recovery"]
    E --> G["Verify correctness and SLO"]
    C --> G
    F --> G
~~~

Do not roll back if the source has been decommissioned, keys revoked, schemas made incompatible, or external side effects cannot be reversed. Runbooks need a decision owner and decision deadline.

## 12. Exit Cost and Financial Modeling

Exit cost is usually far larger than data egress fees alone. Include engineering, operations, commercial, and risk across the entire process.

### 12.1. Exit Cost Components

- Egress, export APIs, snapshots, retrieval, and temporary storage.
- Target compute/storage/databases during dual-run.
- Data conversion, schema adaptation, re-encryption, and validation.
- Rewriting application adapters, IaC, CI/CD, observability, and policies.
- Network interconnects, DNS, certificates, and security tooling.
- Testing, rehearsals, performance tuning, and DR.
- Vendor professional services or termination fees.
- License portability and new support contracts.
- Skills, training, hiring, and on-call load.
- Downtime, business disruption, and opportunity cost.
- Decommissioning, deletion certification, and auditing.
- Contingency for delays, mismatches, and rollbacks.

### 12.2. Sample Exit Budget

Suppose a service holds 80 TB of data. Illustrative model:

| Item | Estimate |
| --- | ---: |
| Data transfer/export and temporary storage | \$18,000 USD |
| Target platform running in parallel for 2 months | \$42,000 USD |
| Engineering and application adaptation | \$70,000 USD |
| Database migration, testing, and reconciliation | \$28,000 USD |
| Security, network, and observability integration | \$16,000 USD |
| Training, support, and operational readiness | \$12,000 USD |
| 20% contingency | \$37,200 USD |
| **Illustrative total** | **\$223,200 USD** |

This is an arithmetic example, not a price quote. Real estimates require price books, contracts, data size/egress, export rates, dual-run duration, labor rates, and workload risk.

### 12.3. Exit Readiness as an Investment

\[
ExpectedExitCost = P(trigger) \times Cost(exit\ when\ triggered)
\]

\[
PortabilityValue =
ExpectedExitCost_{before} -
ExpectedExitCost_{after} -
Cost(portability\ controls)
\]

This is a trade-off model, not a deterministic forecast. Beyond financial value, factor in strategic option value, negotiating leverage, regulatory readiness, and resilience.

## 13. Contracts, Data, and Shared Responsibility During Exit

Exit plans must be reviewed with Procurement, Legal, Privacy, Security, and Finance.

Items to verify:
- Rights to export data and metadata; formats, APIs, and delivery timelines.
- Egress/export fees and archive/snapshot retrieval fees.
- Notice periods, termination dates, and auto-renewal terms.
- Data processors/subprocessors and processing locations.
- Post-termination retention.
- Deletion, backup expiration, and certificates of destruction.
- Access to audits/evidence after account closure.
- License portability, BYOL, and third-party software.
- Support during the migration window.
- Transition assistance clauses.
- Ownership of keys, domains, certificates, and IPs.
- Handling when the provider fails to export or suffers an outage.

Do not assume deleting a resource deletes all data. Confirm replicas, snapshots, backups, logs, caches, and subprocessors under applicable terms.

## 14. Exit Testing and Migration Rehearsals

An unrehearsed exit plan is merely a hypothesis.

### 14.1. Testing Levels

| Level | Content | Evidence |
| --- | --- | --- |
| Inventory test | Export dependency/resource inventory | Coverage and owners |
| Export test | Export representative dataset | Duration, completeness, checksums |
| Restore test | Import into target | Restore success, schema/data validation |
| Compatibility test | Run application contract/test suites | Functional/integration results |
| Performance test | Benchmark target | p95/p99, throughput, saturation, cost |
| Security test | IAM, keys, networking, auditing | Policy/negative tests, scans, and audits |
| Operational test | Deploy, monitor, back up, incidents, and DR | Runbooks and on-call sign-off |
| Cutover rehearsal | Rehearse full sequence | Downtime, lag, and decision timing |
| Exit drill | Simulated partial/full exit | Duration, cost, and blockers |

### 14.2. Representative Workloads

Do not test only on tiny datasets:
- Keep data proportions, indexes, object sizes, and partition skew close to production.
- Simulate peak traffic, background jobs, and event rates.
- Account for data growth during initial copy.
- Test schema changes mid-CDC.
- Simulate network interruptions and API throttling.
- Test target restarts, failovers, and restores.
- Measure reconciliation time and final downtime.

### 14.3. Portability Proof

A minimum proof should demonstrate:
1. Deploying workloads on the target from source/version-controlled artifacts.
2. Provisioning identity, networking, secrets, and configs through reviewed workflows.
3. Importing data and passing integrity checks.
4. Applications completing critical journeys.
5. Performance/capacity within thresholds.
6. Backup/restore and monitoring operating properly.
7. Cutover and rollback/forward recovery tested.
8. Different operators able to follow the runbooks.

## 15. Conditions to Retire the Old Provider

Never close the provider account or delete source resources immediately after traffic shifts.

Before retirement:
- Target passes the stabilization window.
- Data reconciliation completes with owner sign-off.
- Backups/retention/legal holds are handled.
- DNS, certificates, webhooks, partner allowlists, and integrations are updated.
- No remaining traffic, jobs, scheduled tasks, cross-account roles, or callbacks hit the source.
- Old keys/secrets are rotated/revoked per plan.
- Required logs/audits are exported and accessible.
- Data deletion/retention evidence is captured.
- Licenses, contracts, committed spend, and support are properly closed.
- Rollback window closes with decision owner approval.
- CMDB/inventory/architecture/DR runbooks are updated.

~~~mermaid
flowchart TD
    A["Target stable and accepted"] --> B["Confirm data reconciliation"]
    B --> C["Drain jobs, queues and integrations"]
    C --> D["Export required audit/evidence"]
    D --> E["Revoke old access, keys and credentials"]
    E --> F["Delete/expire source data per policy"]
    F --> G["Verify deletion and residual backups"]
    G --> H["Close license, contract and billing"]
    H --> I["Update inventory and architecture records"]
~~~

Each step requires evidence and an owner. A provider account can remain in a restricted state for a period per retention/audit policy before full closure.

## 16. Real-World Scenario: Migrating a Booking Platform Between Two Clouds

A booking SaaS runs on Provider A with containerized APIs/workers, a managed relational database, an event bus/workflow engine, object storage, IAM, secret manager, KMS, and monitoring. The organization evaluates exiting due to rising costs, new data residency rules, and a desire to reduce dependence on the event/workflow platform. Not every service needs to move at once.

### 16.1. Workload Classification

| Workload | Primary lock-in | Strategy |
| --- | --- | --- |
| Booking API | IAM, database drivers, secret integration | Containers, adapters, and DB compatibility tests |
| Notification worker | Event semantics | Event contracts and idempotency |
| Workflow | Proprietary state machine | Migrate by use case; test timeouts/compensation |
| Invoice storage | Object metadata, retention, KMS | Export manifests, re-encrypt, verify versions/tags |
| Analytics | Warehouse SQL and data formats | Open formats/exports, query validation |
| Observability | Query/alert language | OpenTelemetry pipeline, migrate dashboards |
| CI/CD | Provider deploy API/IaC | Versioned pipelines and target deploy identities |

### 16.2. Wave Roadmap

1. **Discovery:** inventory, dependency graph, contract reviews, cost/SLO baselines.
2. **Foundation:** target landing zone, networking, IAM, logging, KMS, registries, policies, and CI/CD.
3. **Stateless workloads:** deploy read-only/canary APIs, verify tokens, routing, and performance.
4. **Data:** baseline copies, CDC, object exports, checksums, and reconciliation.
5. **Events/workflows:** migrate producers/consumers, idempotency, replay, and durable state.
6. **Transaction cutover:** freeze/dual-run per design, final sync, and traffic shift.
7. **Stabilization:** SLOs, cost, security, backup/restore, and on-call exercises.
8. **Exit:** drain source, revoke credentials, export audits, capture deletion evidence, and close contracts.

### 16.3. Success Gates

- Checkout/search SLOs met on the target.
- Booking/payment state reconciled within thresholds.
- Zero lost events and duplicates handled idempotently.
- Access controls and tenant isolation pass negative tests.
- Keys/secrets and encryption policies verified.
- Backup restores and DR meet RTO/RPO.
- Cost per successful booking within business thresholds.
- Zero production dependencies requiring fallback to Provider A after retirement.

## 17. Second Scenario: Proprietary Managed Service Without a Direct Equivalent

An analytics team uses a proprietary workflow/streaming service tightly integrated with a warehouse. The target lacks an equivalent API.

Do not pick a product merely because its name sounds similar. Instead:
- List active capabilities: ordering, windowing, state stores, watermarks, replay, exactly-once boundaries, schema registries, schedulers, and lineage.
- Separate mandatory capabilities from those replaceable via redesign.
- Encode semantics into contract tests and data correctness tests.
- Compare self-managing a broker/stream processor against managed alternatives.
- Measure throughput, latency, late events, recovery, replay, and cost.
- Accept a rewrite if the business case and exit objective justify it.
- Record residual risks and dual-system maintenance costs during migration.

Keeping a proprietary service in a narrow scope is fine when benefits are large and exit risk is accepted. An exit strategy does not force replacing every technology with a generic commodity.

## 18. Measuring Exit Readiness and Portability

| Metric | Meaning | Usage |
| --- | --- | --- |
| Dependency inventory coverage | % of workloads with documented dependencies/owners | Find blind spots |
| Critical dependency portability | % of critical dependencies with tested exit paths | Assess readiness |
| Data export completeness | % of data/metadata exportable and validatable | Identify data lock-in |
| Migration rehearsal success | % of rehearsals passing gates | Execution evidence |
| Measured exit time | Rehearsed duration to reach target | Compare against RTO/contract windows |
| Exit cost variance | Delta between estimates and rehearsals/actuals | Improve budgeting |
| Provider-specific surface | Footprint of code/config tied to proprietary APIs | Track trends |
| Unresolved exit blockers | Technical, legal, or commercial blockers | Escalation |
| Operational readiness | Runbooks/owners/on-call verified | Operability |
| Residual source dependencies | Flows still relying on old provider | Retirement gates |

Do not use lines of provider-specific code as the sole KPI. A small amount of code can call a proprietary service holding most business state; a system full of adapters can still be hard to operate.

## 19. Well-Architected Trade-Offs

| Pillar | Questions |
| --- | --- |
| Operational Excellence | Does the team have skills, runbooks, IaC, monitoring, and owners for the target? |
| Security | Are identity, key custody, data protection, and auditing equivalent? |
| Reliability | Does migration cover backups, replication, rollback, DR, and fencing? |
| Performance Efficiency | Does the target hit latency/throughput on realistic workloads? |
| Cost Optimization | Are egress, dual-run, licenses, operations, and unit economics accounted for? |
| Sustainability | Are duplicate footprints, redundant transfers, and over-provisioning avoided? |

Multi-cloud can reduce concentration risk, yet multiplies control planes, network paths, IAM models, on-call skills, and observability backends. Invest only when resilience, negotiation, residency, or continuity gains outweigh complexity and cost.

## 20. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating containers as full portability | Data, IAM, networking, and managed services stay locked in | Inventory all dependencies |
| Choosing targets by product name | Differing semantics break business logic | Capability mapping and contract tests |
| Testing only app startup | Fails to prove data, security, or performance | End-to-end portability proof |
| Treating CSV export as data exit | Loses schemas, transactions, metadata, and history | Data inventory and semantic validation |
| Dual-write without idempotency | Divergence and duplicate transactions | Outbox/inbox and reconciliation |
| Shifting traffic before data catch-up | Data loss or stale reads | Replication lag gates and final sync |
| Missing rollback window | Cannot return after new writes | Define reverse sync or forward recovery |
| Underestimating egress/dual-run | Budget and timeline overruns | Comprehensive exit cost model |
| Ignoring contracts/deletion | Lingering obligations or data on old provider | Legal review and deletion evidence |
| Making everything multi-cloud | Complexity and cost exceed value | Tier portability by criticality |
| Over-abstraction | Loses features, performance, or semantics | Capability-aligned adapters |
| Ignoring key portability | Unable to decrypt/recover data | Key custody/re-encryption tests |
| Not migrating observability | Target lacks alerts and incident context | Dashboard, trace, log, and runbook parity |
| Shutting down old provider too early | Loses rollback/evidence/data access | Stabilization and retirement gates |
| No assigned owner | Exit plan goes stale, never rehearsed | Assign owners and review cadences |

## 21. Practice Exercise

A booking SaaS runs on Provider A with managed PostgreSQL, object storage, an event bus, serverless workflows, IAM, KMS, and monitoring. Leadership wants to evaluate moving critical workloads to Provider B within 9 months due to cost and concentration risk. The system holds 12 TB in databases, 90 TB in objects, millions of daily events, and multiple tenants with data residency requirements.

Complete the following:

1. Draw a dependency graph for the API, database, event bus, workflows, storage, identity, keys, and observability.
2. Build an inventory of direct/transitive/operational/data/commercial dependencies; score lock-in.
3. Classify which workloads require Tier 0/1/2/3 portability and explain why.
4. Build a Provider A/B capability matrix; verify semantics rather than relying on product names.
5. Design data export/migration for databases, objects, event history, and workflow state.
6. Select bulk copy, CDC, replay, or a hybrid approach; define consistency/cutover gates.
7. Design identity mapping, workload identity, KMS/re-encryption, networking, and auditing.
8. Plan migration waves, staffing, downtime budgets, rollback windows, and forward recovery.
9. Calculate exit costs including egress, dual-run, engineering, testing, licenses, training, decommissioning, and contingency.
10. Build a portability test matrix, rehearsals, and an exit drill.
11. Define contract/legal/residency/deletion checks prior to provider termination.
12. Write an ADR on the right portability investment; state residual lock-in, owners, and review triggers.

**Self-assessment criteria:** your solution must specify which workloads/data can move, how, in what timeframe, and at what cost and risk; include test evidence and rollback/retirement plans; and never treat multi-cloud or containers as proof of portability by themselves.

## 22. Pre-Commitment Exit Readiness Checklist

- [ ] Exit triggers, scope, and goals are defined.
- [ ] Workloads, data, services, identity, networking, control planes, and contracts are inventoried.
- [ ] Dependency graph identifies direct, transitive, operational, data, and commercial lock-in.
- [ ] Criticality, residency, recovery, and blast radius are classified.
- [ ] Portability tiers have rationale and owners.
- [ ] Target capability matrix validates real semantics and limits.
- [ ] Application/provider-specific code and adapters have contract tests.
- [ ] IaC, CI/CD, registries, observability, and runbooks have migration plans.
- [ ] Data exports include schemas, metadata, versions, retention, and required audits.
- [ ] Migration includes checksums, reconciliation, CDC/replay, and cutover gates.
- [ ] Identity, permissions, secrets, key custody, and encryption are verified.
- [ ] Networking, DNS, certificates, private connectivity, and routing are tested.
- [ ] Performance, capacity, cost, and failure headroom meet targets.
- [ ] Backup/restore, rollback, reverse sync, or forward recovery are rehearsed.
- [ ] Legal, Procurement, Privacy, and Security confirm data/contract obligations.
- [ ] Exit costs include egress, dual-run, engineering, training, and decommissioning.
- [ ] Owners, staffing, timelines, escalation, and communications are clear.
- [ ] Portability proof and end-to-end rehearsals have captured evidence.
- [ ] Stabilization windows and old-provider retirement criteria are clear.
- [ ] Data deletion, key revocation, and license/contract closures have audit evidence.
- [ ] Exit plans are reviewed whenever providers/services change.

## Key Takeaways

A provider exit strategy starts with understanding real dependencies, data gravity, semantics, and commercial constraints. Portability is not just running containers on another cloud; it must encompass data, identity, keys, networking, delivery, observability, security, operations, and recovery.

A credible exit plan follows the sequence **inventory → lock-in assessment → target capability mapping → data/application preparation → migration rehearsal → gated cutover → stabilization → deletion and contract closure**. Claim readiness to leave a provider only after gathering evidence on duration, cost, correctness, SLOs, security, and the team’s ability to execute the process.
