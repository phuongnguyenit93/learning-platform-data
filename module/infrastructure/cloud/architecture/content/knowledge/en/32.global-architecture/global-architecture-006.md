# Geographic Partitioning and Data Residency Requirements

A cloud platform serving users across multiple countries typically wants to place applications close to users to reduce latency, improve resilience, and expand into new markets. However, data does not merely follow requests into the application. It can be written to databases, caches, object storage, backups, logs, traces, analytics, support systems, and third-party services. If a dataset must be stored or processed within a specific geographic boundary, the architecture must govern all of these flows—not just the location of the primary database.

**Data residency** refers to where data is geographically stored or processed. **Data sovereignty** refers to the jurisdictions and legal authorities that apply to the data, organization, or provider. **Data localization** typically refers to requirements that data within a given scope must be stored, processed, or kept inside a designated country or region. These concepts are related but not synonymous; actual obligations must be determined by data type, processing purpose, organizational role, and applicable law.

This lesson belongs to the **Global Architecture** chapter of the **CLOUD_ARCHITECTURE** module. The module focuses on designing cloud architectures from business requirements through networking, compute, data, and deployment models while evaluating trade-offs across reliability, security, scalability, cost, and operations under Well-Architected principles. This lesson teaches how to partition by geography, define data boundaries, choose home regions, control replication/cross-border transfers, and ensure backups, telemetry, support, and dependencies obey residency requirements.

## 1. Why Partition Data by Geography?

A system may have users across multiple regions while different data types carry different obligations. For example, in a booking platform:
- Customer profiles may be subject to residency rules or cross-border transfer restrictions.
- Booking and payment records may carry distinct retention, access, and audit requirements.
- Room/property photos may be less sensitive public content.
- Security logs may contain IPs, user identifiers, or access metadata.
- Aggregated metrics may be used globally if stripped of or minimized against identifiability per policy.
- Backups may need to stay in the same region as the source data.
- Support data might be accessed by staff in another country.

Choosing a single region for the entire system can result in high latency or fail legal requirements. Replicating all data to every region can violate boundaries, expand the attack surface, and incur high transfer/replication costs.

Geographic partitioning aims to answer:
1. Which data may be stored in which regions?
2. Which data may be processed or accessed from where?
3. May data be transferred to support, analytics, observability, or external providers?
4. Do backups, replicas, caches, search indexes, and logs share the same control scope?
5. Which region is each user/tenant bound to, and who is authorized to change it?
6. During failover, may data move to another region or must it remain in the same jurisdiction?
7. Can data be deleted, exported, or disclosed on request while preserving global consistency?

~~~mermaid
flowchart TB
    USER["Users / tenants"] --> ROUTER["Global entry and policy router"]
    ROUTER --> RA["Region A cell"]
    ROUTER --> RB["Region B cell"]
    RA --> DA[("Regional data A")]
    RB --> DB[("Regional data B")]
    RA --> GA["Local backup / logs / keys"]
    RB --> GB["Local backup / logs / keys"]
    RA -. "Approved aggregate only" .-> GLOBAL["Global analytics / control"]
    RB -. "Approved aggregate only" .-> GLOBAL
~~~

## 2. Distinguishing Residency, Sovereignty, and Localization

| Concept | Core Question | Example Requirement |
|---|---|---|
| **Data residency** | In which geographic location is data stored? | Databases and backups must reside inside a specified region |
| **Data sovereignty** | Which laws/jurisdictions apply to the data or provider? | Evaluate access obligations under national law and contracts |
| **Data localization** | Is keeping or processing data inside a specific territory mandatory? | A dataset may not leave the country |
| **Data transfer restriction** | When and under what mechanism may data cross borders? | Transfer only specific data classes after assessment and safeguards |
| **Data access boundary** | Who may access data and from which locations? | Support staff abroad require approval and auditing |

Do not assume that storing data in a region guarantees only that region's laws apply. The provider, data controller, subprocessors, staff access locations, and transfer mechanisms all affect legal analysis. This requires confirmation from legal/privacy owners and cannot be decided from a cloud diagram alone.

### 2.1. Data Residency Is Not Just Database Location

A record can appear in:
- Primary databases and read replicas.
- Caches and session stores.
- Object storage and CDN caches.
- Search indexes and materialized views.
- Queues, event streams, and dead-letter queues.
- Backups, snapshots, and point-in-time recovery logs.
- Application logs, audit logs, traces, and crash dumps.
- Analytics warehouses, data lakes, and notebooks.
- Support exports, ticket attachments, and local downloads.
- Third-party SaaS tools or APIs.

Each copy can have its own lifecycle and access path. Data maps must cover primary, secondary, ephemeral copies, backups, and derived data.

## 3. Start with Data Classification and Processing Purposes

You cannot select regions before understanding your data. Classify data by sensitivity, business criticality, legal category, retention, and processing purpose.

For example:

| Data Category | Examples | What to Assess |
|---|---|---|
| Public content | Property descriptions, public photos | CDN, caching, licensing, and integrity |
| Account/profile | Name, contact details, address | PII, access, residency, deletion |
| Transactions | Bookings, invoices, payment references | Financial records, retention, auditing |
| Authentication | Credential metadata, sessions, auth events | Security, secrets, log access |
| Sensitive support | Tickets, attachments, identity documents | Support location, subprocessors, exports |
| Telemetry | IP, device ID, trace attributes | Re-identification, minimization, region |
| Derived analytics | Aggregated demand, conversions | Anonymization/pseudonymization, joins |
| ML data | Features, training samples, model artifacts | Source lineage, memorization, model access |

### 3.1. Classification by Identifiability

Names, emails, or phone numbers are direct identifiers. IPs, device IDs, geolocation, event timestamps, or combinations of fields can indirectly identify individuals when linked with other datasets. Hashing an identifier does not automatically render data anonymous.

Document:
- Direct identifiers.
- Quasi-identifiers.
- Sensitive attributes.
- Free text and attachments.
- Derived/inferred attributes.
- Data subject/tenant linkage keys.
- Re-identification risk after aggregation.

### 3.2. Data Purpose and Lifecycle

The same data field can serve multiple purposes: fulfilling a booking, fraud prevention, customer support, analytics, or marketing. Each purpose can have distinct legal bases, access permissions, retention periods, and transfer boundaries.

Separating purposes where needed helps:
- Reduce the volume of data copied into analytics systems.
- Set separate retention windows for support exports.
- Restrict who can read identifying fields.
- Delete or de-link data once a purpose ends.
- Distinguish transactional records that must be retained from transient data that can be purged.

## 4. Building Data Flow Maps and Residency Matrices

A data flow map should show where data originates, which services process it, where it is stored, who accesses it, and how it exits.

### 4.1. Example Data Flow for a Booking Platform

~~~mermaid
flowchart LR
    U["Customer in Country A"] --> EDGE["Regional edge / gateway"]
    EDGE --> API["Booking API - Region A"]
    API --> DB[("Customer and booking DB - A")]
    API --> OBJ[("Documents - A")]
    API --> Q[("Regional event stream - A")]
    Q --> ANALYTICS["Approved transformation"]
    ANALYTICS --> AGG["Minimized aggregate"]
    AGG --> GLOBAL["Global reporting"]
    API --> PAY["Payment provider"]
    API --> SUPPORT["Support platform"]
~~~

Arrows leading to payment, analytics, or support are checkpoints for transfer and access review. Never assume data transfer is permitted simply because the destination is a SaaS tool or internal service.

### 4.2. Residency Matrix

| Data Class | Primary Location | Replica/Backup | Processing/Access | Cross-Border Rule |
|---|---|---|---|---|
| Public catalog | Content-serving regions | Global CDN permitted | Public read | Per licensing and cache policy |
| Customer profile | Tenant's home region | Backups inside approved boundary | Services and authorized support | Only via approved mechanisms |
| Booking ledger | Transaction-owning region | DR location per policy | Booking/payment services | Verify legal and recovery constraints |
| Security audit | Regional audit store | Archived inside approved boundary | Security team per case | Redact/minimize and review transfers |
| Aggregate analytics | Global analytics zone if permitted | Per retention policy | Analysts/BI | Policy-processed data only |
| Temporary cache | Same region as source | May omit replication | Application runtime | TTL and avoid storing excess fields |

The matrix must be a living document with an owner, version, approvals, and review date. It is not write-once; changes to services, providers, or subprocessors can introduce new data flows.

## 5. Choosing a Partitioning Model: Region, Tenant, Cell, or Data Domain

### 5.1. Region-per-Tenant / Home Region

Each tenant or group of tenants is assigned a home region. Requests route to that region for authoritative reads and writes.

Advantages:
- Clear data ownership.
- Easy to enforce per-tenant residency policies.
- Reduces cross-region writes and conflicts.
- Regions can be chosen by contract or geography.

Trade-offs:
- Requires managing tenant-to-region mappings.
- Moving a tenant between regions is a complex migration.
- Traffic in a home region can become skewed.
- Global features require aggregating data across boundaries.
- Support and admin tooling must be tenant-context aware.

### 5.2. Regional Cell Architecture

Each cell is a relatively independent infrastructure unit: gateway, application, database, queue, cache, observability, and policies. Tenants are placed into a cell/region. Faults or changes can be contained within a cell rather than affecting the entire platform.

~~~mermaid
flowchart TB
    G["Global routing / tenant directory"] --> C1["Cell A"]
    G --> C2["Cell B"]
    G --> C3["Cell C"]
    C1 --> D1[("Data A")]
    C2 --> D2[("Data B")]
    C3 --> D3[("Data C")]
    C1 -.-> AGG["Approved aggregate plane"]
    C2 -.-> AGG
    C3 -.-> AGG
~~~

Cell architectures support blast-radius isolation and residency, though duplicating control/operations can raise costs. Global shared services such as identity, DNS, deployment, and support access still require careful evaluation.

### 5.3. Data Domain Partitioning

You can partition by data category or bounded context:
- Transactional databases in each tenant's home region.
- Public media in global object storage/CDN.
- Analytics on de-identified aggregates.
- Security audits retained by region and policy.
- Feature stores scoped by processing location and purpose.

This approach is flexible, though a single workflow may span multiple data domains/regions. Define data contracts, sources of truth, and transfer semantics.

### 5.4. Comparing Options

| Model | Best Fit When | Primary Trade-Off |
|---|---|---|
| Single central region | Simple legal scope, concentrated traffic | Latency and single-region dependency |
| Multi-region shared data plane | User proximity needed and data distribution permitted | Cross-region consistency and transfers |
| Home region per tenant | Per-tenant residency and ownership | Tenant placement and migration |
| Regional cells | Isolation and blast-radius control are priorities | Platform duplication and ops overhead |
| Hybrid by data domain | Data types carry distinct rules | Complex data flows and governance |

## 6. Global Control Plane and Regional Data Planes

A common pattern separates:
- **Global control plane:** manages the tenant directory, deployment intent, policy catalogs, routing metadata, and fleet governance.
- **Regional data plane:** handles requests, transactions, and data belonging to the region.

However, the global control plane should not become a default backdoor to all tenant data. The global directory only needs minimal routing metadata—such as tenant ID, home region, service tier, and routing state—and should not copy customer profiles unnecessarily.

~~~mermaid
flowchart TB
    ADMIN["Platform operators"] --> CP["Global control plane"]
    CP --> DIR[("Tenant-to-region directory")]
    CP --> DEP["Regional deployment controllers"]
    USER["Customer request"] --> EDGE["Global entry"]
    EDGE --> DIR
    DIR --> ROUTE["Route to home region"]
    ROUTE --> DP1["Regional data plane A"]
    ROUTE --> DP2["Regional data plane B"]
    DP1 --> DATA1[("A data boundary")]
    DP2 --> DATA2[("B data boundary")]
~~~

### 6.1. Risks of a Global Plane

- Misconfigured tenant mappings can route data to an unapproved region.
- A global admin role may hold overly broad privileges.
- Global telemetry can ingest PII from every region.
- Control-plane outages can block provisioning or failover.
- Deployment pipelines can push a faulty policy to all regions simultaneously.

Mitigations:
- Metadata minimization.
- Signed/versioned routing policies.
- Least privilege scoped by region/cell.
- Approvals for tenant migrations and residency overrides.
- Locally cached routing metadata with TTLs and integrity checks.
- Bounded regional operation when the global control plane is unavailable.
- Separate auditing for cross-region administrative actions.

## 7. Routing and Tenant Placement

Routing must rely on verified policy. Do not infer regions solely from a user's IP on every request; users may roam, use VPNs, or represent a tenant with a fixed home region.

### 7.1. Tenant Directory

The directory can store:
- Tenant ID.
- Home region/cell.
- Data classification/policy profile.
- Placement status: `active`, `migrating`, `restricted`.
- Mapping version/epoch.
- Allowed failover region set.
- References to contracts/approvals rather than storing legal documents.
- Timestamp and actor of each change.

Never let client applications supply a region header to pick where data is written. The backend must authenticate the tenant and look up routing policy server-side.

### 7.2. Region Migration

When a tenant needs to move home regions:
1. Confirm legal/business approvals and data inventory.
2. Select a destination inside the permitted boundary.
3. Verify dependencies, quotas, keys, and service availability.
4. Design full snapshot copying and incremental change capture.
5. Keep the source authoritative during copying.
6. Verify checksums, record counts, and business invariants.
7. Schedule a cutover window; pause or buffer writes.
8. Synchronize the final delta and transfer ownership.
9. Update the directory with a new version/epoch.
10. Shift traffic and monitor closely.
11. Retain the source read-only during the migration retention window.
12. Delete source data per policy once legal, operational, and reconciliation checks finish.

Never update the directory to the new region before data and dependencies are ready. Allowing both source and destination to accept writes risks creating two authoritative sources.

## 8. Replication and Cross-Border Data Transfers

Replication is a data transfer operation. It must be evaluated for residency, purpose, security, access, and retention just like read requests.

### 8.1. Replication Types

- **Synchronous replication:** lowers the chance of losing committed data per engine semantics, but increases latency and availability coupling across failure domains.
- **Asynchronous replication:** keeps write latency low, but replicas can lag and failover RPO is greater than zero.
- **Logical replication/CDC:** selects specific tables/events to sync; can filter or transform while preserving semantics and lineage.
- **Object replication:** copies files/versions/metadata; check encryption keys, ACLs, and delete markers.
- **Aggregate export:** transfers only de-identified data for analytics where policy allows.

Do not treat replication as the default for all data. One dataset may only need local backups, another can be aggregated globally, and another must never leave its home region.

### 8.2. Transfer Review

Before enabling replication or exports, answer:
- Which data class is being sent?
- Which jurisdictions contain source and destination?
- Who acts as controller/processor or equivalent role?
- Have processing purpose and legal/contractual bases been confirmed?
- Do any subprocessors receive the data?
- How are encryption and key custody handled?
- Are transfer mechanisms or contractual safeguards required?
- How are retention and deletion enforced on both ends?
- Can fields be minimized or aggregated prior to transfer?
- Which audit events prove who enabled and used the transfer path?

Specific legal assessments are performed by legal/privacy owners. Architects must supply accurate data flows, destinations, access paths, and technical controls so decisions are grounded in facts.

## 9. Backups, Snapshots, and Disaster Recovery Within Geographic Boundaries

Residency rules can restrict where backups or DR copies are placed. A standard multi-region DR design is not automatically allowed to replicate data to any region.

Options:
- Backups within the same region across separate accounts/projects.
- Backups within the same country/jurisdiction across separate failure domains.
- Cross-region copies to a pre-approved region.
- Encrypted backups with keys managed inside the boundary.
- Logical backups/portable exports stored in permitted locations.
- Rebuilding from local source data where feasible.

### 9.1. RTO/RPO and Residency Can Conflict

If the nearest DR region sits outside the permitted boundary, sensitive data cannot simply fail over there to lower RTO. Business owners must select a permitted strategy:
- Multi-AZ within the same boundary.
- Another DR region inside the boundary.
- Degraded mode or read-only service.
- In-jurisdiction backup/restore with a longer RTO.
- Rebuilding service from local data while accepting partial feature disruption.

Document achievable RTO/RPO within residency constraints rather than committing to targets that violate legal or technical boundaries.

### 9.2. Backups and Keys

Backups are useful only if they can be decrypted during recovery. Destination key access must follow policy—never copy private keys or grant broad global decrypt permissions carelessly. Check:
- Key regions and replication support.
- IAM/workload identities at the DR site.
- Key rotation and backup key versions.
- Recovery access and break-glass procedures.
- Residency of key metadata and audit logs.
- Key revocation procedures upon compromise.

## 10. CDNs, Caches, and Edge Data

CDNs/caches bring data closer to users, yet not all data types belong in global caches.

Potentially suitable:
- Public images and static media.
- Non-identity-bound content.
- Versioned static assets with integrity checks.
- Approved aggregate data.

Exercise caution with:
- Private profiles, bookings, invoices, and documents.
- Auth tokens, sessions, and personal preferences.
- Responses containing PII or tenant-specific data.
- Data subject to strict deletion/retention mandates.

Cache keys must include authorization/tenant dimensions when applicable. Never cache sensitive responses on a shared CDN just to boost hit ratios. Apply `Cache-Control`, `private`/`no-store`, signed access, TTLs, and invalidation aligned with data classification. Inspect edge logs and origin logs as well, because CDN telemetry can record IPs, headers, or URLs containing identifiers.

## 11. Logs, Metrics, Traces, and Security Telemetry

Observability is frequently overlooked in residency designs. An API might return only an opaque ID, while logs or traces capture emails, IPs, query parameters, document URLs, or request bodies.

### 11.1. Regional Telemetry Design

- Collect logs and traces in-region first.
- Redact and minimize at collectors close to the source.
- Retain security/audit events per jurisdiction and policy.
- Export only aggregated/low-cardinality metrics if permitted.
- Separate operational metadata from data payloads.
- Restrict support analyst access by region and case.
- Apply retention and residency rules to archived/backed-up telemetry.
- Audit access logs of CDNs, WAFs, DNS, API gateways, and SaaS tools.

Do not assume a metric is non-personal merely because it is numeric. Labels containing tenant IDs, user IDs, URLs, or emails turn metrics into identifiable data.

### 11.2. Global Observability

You can centralize global dashboards without centralizing raw logs. For example, each region emits:
- Aggregated availability/error rates.
- Aggregated latency histograms.
- Resource utilization.
- Queue age.
- Deployment versions and incident references.
- Security finding counts by severity.

When deep investigation is required, analysts query regional log stores under role and case controls. This curbs cross-border raw data movement while preserving global operational visibility.

## 12. Analytics, Data Lakes, and Machine Learning

Analytics and ML often need insights across markets, yet do not always require raw personal data.

Patterns:
- **In-region processing:** raw data stays in-region; only approved outputs leave.
- **Aggregation:** export counts, histograms, or summaries across sufficiently large cohorts.
- **Pseudonymization:** replace direct identifiers with controlled keys/tokens; still treated as personal data if re-linkable.
- **Federated queries:** execute queries where data resides and return only policy-compliant results.
- **Federated learning:** distributed model training exchanging aggregated updates; does not automatically eliminate privacy risk.
- **Regional model serving:** run inference near the data, avoiding raw feature exports.
- **Global model artifacts:** ship vetted models after checking for memorization or data leakage.

### 12.1. Derived Data Still Requires Governance

Features, embeddings, scores, model artifacts, and analytics tables can retain or leak information from source records. Before treating them as "safe to transfer," evaluate:
- Can records or users be reverse-looked-up?
- Do they contain rare combinations or sensitive attributes?
- Can training data be extracted from the model?
- How are derived-data retention and deletion handled?
- Is there lineage back to source datasets to fulfill corrections or deletions?

Never assume a trained model is automatically exempt from source-data obligations. Govern according to use case and applicable law.

## 13. Support, Human Access, and Subprocessors

Even when a database sits inside a region, staff or support vendors in another country might view records via consoles or APIs. This is an access path that requires separate evaluation.

Controls:
- Role-based access control and purpose limitation.
- Just-in-time elevation, approvals, and session expiration.
- Masking or field-level redaction.
- Regional support teams or follow-the-sun operations with clear access policies.
- Customer consent or contractual restrictions where applicable.
- Auditing of all sensitive queries, views, exports, and downloads.
- Time-bound break-glass access with post-incident review.
- Prevent automatic copying of tickets/attachments into global SaaS tools.
- Subprocessor inventories and location transparency.

A global ticketing tool may hold minimal support metadata while profile contents are viewed exclusively through a regional service. Never use ad-hoc file exports as a workaround, as files end up on laptops, emails, chats, or ticket attachments outside the boundary.

## 14. Encryption, Key Management, and Regional Access Controls

Encryption is an essential control, yet it does not by itself prove compliance or residency. Examine who holds keys, who can decrypt, where keys reside, and which access paths exist.

### 14.1. Regional Key Strategy

- Scope keys by region and data classification.
- Separate principals by workload and purpose.
- Never grant a single global role permission to decrypt all tenants.
- Audit key usage, policy updates, grants/revocations, and rotations.
- Test backup restores using valid identities in the DR region.
- Manage envelope encryption and key versions.
- Maintain emergency access procedures if the primary identity/control plane fails.
- Use cryptographic erasure only when semantics, backups, and retention align.

### 14.2. Tenant-Level Keys

For some workloads, customer-managed keys or per-tenant key scoping strengthens isolation and contractual assurance. Trade-offs include:
- Managing far more keys and grants.
- More complex rotation and recovery.
- Disabling a key can lock a tenant out of its own data.
- Cross-region DR depends on key replicas and policies.
- Audits and support must distinguish key owners.

Do not introduce per-tenant keys without an operational model capable of managing their lifecycle, quotas, and incidents.

## 15. Deletion, Retention, and Data Rights

Deletion requests grow harder when data is replicated across regions or transformed into derived datasets.

Inventory all copies:
- Primary records.
- Read replicas and regional copies.
- Object versions and CDN caches.
- Backups/snapshots per retention schedules.
- Search indexes and materialized views.
- Queues and event logs.
- Analytics/ML features and training datasets.
- Exports and support tickets.
- Third-party processors.

A deletion workflow can:
1. Validate the request and scope.
2. Check legal/contractual retention exceptions.
3. Create an idempotent, audited deletion job.
4. Delete or de-link at the source of truth.
5. Propagate to derived stores within SLAs.
6. Invalidate caches/CDNs and search indexes.
7. Apply backup expiry or cryptographic erasure policies where appropriate.
8. Notify or invoke third-party processors per contract/API.
9. Verify completion and emit policy-compliant reports.

Never promise instant deletion from immutable backups. Retention mandates or legal holds may require keeping backups until expiration; restrict access and ensure restored data does not resurrect deleted records by applying a deletion ledger or tombstones.

## 16. Governance and Geographic Change Management

An architecture compliant today can drift out of compliance tomorrow when a new region, provider, subprocessor, or analytics integration is added.

Manage:
- Data inventories and classification owners.
- Residency matrices and approved region lists.
- Data transfer assessments.
- Provider/subprocessor registers.
- Region enablement and change approvals.
- Tenant placement and migration workflows.
- Key and access policies.
- Retention and deletion policies.
- Jurisdiction-specific incident/breach response plans.
- Periodic reviews when laws, contracts, or products change.

### 16.1. Policy as Code

Automate checks to ensure:
- Sensitive resources can be created only in approved regions.
- Backup destinations belong to an allowlist.
- Log sinks and storage buckets are not misconfigured to wrong regions.
- Replication targets are approved.
- Public access is blocked per policy.
- Data class, owner, and region tags are present.
- Cross-region routes open only to approved services.
- KMS key policies and workload roles align.

Policy as code cuts misconfiguration risk, yet does not replace legal interpretation. Map business policies to technical rules, test for false positives, and enforce an approved exception process.

## 17. Well-Architected Trade-Offs

| Dimension | Benefits of Regional Partitioning | Risks / Costs | Evidence |
|---|---|---|---|
| **Reliability** | Cell isolation, local operations, regional recovery | Regional capacity shortfalls, global router/control-plane faults, constrained DR | Regional failover drills, SLO/RTO/RPO |
| **Security** | Data boundaries, least privilege, key scoping | Cross-border access, copy/log leaks, key policy drift | Data-flow reviews, IAM/KMS audits |
| **Performance Efficiency** | Data near users, fewer round trips | Cross-region calls, home-region latency, cache misses | Regional p95/p99, transfer paths |
| **Cost Optimization** | Replicate only necessary data, localize workloads | Multiple cells/regions, duplicated capacity and ops | Cost per region/tenant, egress/replica costs |
| **Operational Excellence** | Clear ownership, policy automation, inventories | Configuration variants, complex migrations | Region runbooks, policy coverage, audits |
| **Sustainability** | Avoid redundant copies and unnecessary transfers | Distributed standby increases compute/storage | Resource utilization, data lifecycles, transfer volume |

Common trade-offs:
- Explicit home regions reduce conflicts at the cost of higher latency for distant users.
- Global replication boosts read availability while expanding data boundaries and transfer expenses.
- Regional observability limits raw data movement but requires multiple stores/collectors.
- Warm standby inside permitted jurisdictions raises DR readiness at a baseline cost.
- Pseudonymization reduces exposure without guaranteeing irreversibility.
- A global control plane keeps management consistent, yet can become a shared dependency and metadata concentration point.

## 18. Geographic Partitioning Architecture Review Process

1. **Gather business and legal requirements:** identify markets, data subjects, purposes, contracts, and jurisdictions.
2. **Classify data:** PII, transactions, sensitive records, public content, telemetry, derived data, and retention.
3. **Map data flows:** primary, replicas, caches, backups, logs, support, analytics, and third parties.
4. **Build the residency matrix:** allowed locations, processing/access, replication, and transfer rules.
5. **Select the partitioning model:** home region, cells, region-per-tenant, or hybrid by data domain.
6. **Design routing:** tenant mappings, authentication, and server-side policy enforcement.
7. **Design the data plane:** sources of truth, consistency, replication, migrations, and deletion.
8. **Evaluate the control plane:** metadata minimization, admin access, deployments, and outage behavior.
9. **Protect keys and identity:** regional keys, least privilege, audits, and break-glass access.
10. **Evaluate backup/DR:** achievable RTO/RPO inside permitted boundaries and restore tests.
11. **Design telemetry:** local collection, redaction, global aggregates, and incident access.
12. **Govern support and processors:** access locations, subprocessors, tickets, and exports.
13. **Implement policy as code:** enforce approved regions, transfers, and resource metadata.
14. **Measure:** SLOs, transfer bytes, replication lag, policy violations, costs, and access audits.
15. **Rehearse:** region outages, tenant migrations, key failures, deletions, and data-transfer incidents.
16. **Record ADRs:** choices, assumptions, exceptions, owners, and review triggers.

### Production Checklist

| Item | PASS Criteria |
|---|---|
| Data classification | Has owner, purpose, sensitivity, and retention |
| Residency matrix | Covers primary, replicas, backups, logs, caches, and derived data |
| Legal review | Restrictions and transfer mechanisms confirmed by authorized owners |
| Tenant placement | Home region resolved server-side with approvals and audits |
| Regional isolation | Cells/data planes enforce boundaries and least privilege |
| Replication | Destinations, semantics, lag, and transfer policies are explicit |
| Backup/DR | Restore tests meet targets within permitted boundaries |
| Observability | Raw logs cannot accidentally leave boundaries |
| Support access | Human access and subprocessors are controlled |
| Encryption | Keys, decrypt identities, and recovery paths align |
| Deletion | Propagates to replicas/derived stores and respects backup policies |
| Policy automation | Region/transfer misconfigurations are detected or blocked |
| Cost | Replica, transfer, storage, and per-region costs are tracked |
| Governance | Owners, exceptions, audits, and review dates are defined |

## 19. Illustrative ADR — Home Regions for Booking Customer Data

> **Context:** The Booking Platform serves customers across many countries. Certain contracts and regulations impose geographic limits on customer profiles and transaction records. Public catalogs need global distribution to keep latency low.
>
> **Option A:** One global database with multi-region replicas for all data. Simple for analytics and failover, yet expands copy footprints and cross-border transfers for sensitive data.
>
> **Option B:** Home region per tenant for profiles/bookings; public catalogs on global object storage/CDN; regional audit/log stores; global analytics receiving only approved aggregates.
>
> **Illustrative Decision:** Choose Option B. The tenant directory retains minimal mappings to home regions; the backend routes all profile and booking reads/writes using verified mappings.
>
> **Replication/DR:** Each tenant fails over only within its approved region set. If no permitted DR region exists, the system enters degraded/read-only mode per business policy rather than shipping data across borders.
>
> **Support:** Global staff view only necessary metadata; profile details are accessed via a regional service with JIT approval and auditing.
>
> **Analytics:** Regions process raw data locally; only reviewed aggregate/minimized datasets move to the global warehouse.
>
> **Verification:** Test tenant isolation, wrong-region routing, backup/restore, global log leakage, deletion propagation, KMS access, and failover.
>
> **Re-evaluation Triggers:** Market/contract changes, provider launching a suitable region, updated data classification, or revised RTO/RPO targets.

## 20. Practice Exercise: Designing Residency for a Global Booking Platform

A booking platform plans to serve three market tiers:
- Tier A requires customer profiles and transaction records to stay inside a single country boundary.
- Tier B permits storage within an approved region list, but restricts support access from certain locations.
- Tier C has no specific localization mandate, yet must still meet privacy, security, and contractual controls.

The current system uses:
- One global relational database.
- Globally distributed CDNs and caches.
- Centralized logging in Region A.
- An analytics warehouse in Region B.
- Cross-region database replicas for DR.
- A support SaaS staffed across multiple countries.
- Backup copies in a third region.

**Tasks:**
1. Build a data inventory covering profiles, bookings, payments, public catalogs, audits, logs, and derived analytics.
2. Create a residency matrix for each market tier.
3. Propose home regions/cells for tenants and how requests will route.
4. Identify where the global database, caches, and CDN could push data across boundaries.
5. Design backup/DR inside permitted regions.
6. Redesign central logging and analytics without moving raw personal data in violation of policy.
7. Design support access and subprocessor controls.
8. Propose key management, deletion, and region-migration workflows.
9. Define policy-as-code rules and audit evidence.
10. Compare latency, cost, resilience, and operations across two topologies.

### Solution Guidance

- Classify data fields before picking providers; trace primary, replica, cache, backup, log, ticket, and analytics copies.
- Tier A uses home regions within the country boundary; replicas/backups go only to approved locations. If no suitable DR location exists, trade off RTO via read-only/degraded mode.
- Tier B uses an approved region set plus location/role-based access policies; support access is explicitly audited rather than inferred from storage placement.
- Tier C can adopt flexible regional cells or multi-region topologies while enforcing purpose, retention, privacy, and security controls.
- Public catalogs can leverage global CDNs if free of tenant-specific/private data; cache keys and response rules must isolate sensitive content.
- Route raw logs through regional collectors for redaction/minimization, keeping global dashboards on approved aggregates; check metric labels and trace attributes.
- Run analytics close to sources and export only summaries/approved datasets; check aggregates for re-identification risk.
- Keep backups and DR inside approved boundaries, ensure encryption keys have recovery paths, and test restores against realistic RPO/RTO.
- Support SaaS requires subprocessor reviews, location/access controls, field masking, approvals, and auditing; keep raw attachments out of global tickets.
- Policy as code should block resources, replicas, or log sinks in unapproved regions and audit tenant mappings, exceptions, and cross-border transfers.
- Compare costs across regional cells, replication, egress, support, and duplicated operations, balancing against latency, isolation, and recovery goals.

### Self-Check Questions

1. How do data residency, data sovereignty, and data localization differ?
2. Why is database location alone insufficient to prove residency?
3. Which telemetry signals can contain identifiable data?
4. What problems does home-region-per-tenant solve, and what trade-offs does it introduce?
5. How does a regional cell architecture reduce blast radius?
6. What metadata should a global control plane hold?
7. Is replication always permitted when two regions belong to the same cloud provider?
8. Why must the DR region stay within the approved boundary?
9. How can CDNs/caches leak data outside a region?
10. Do derived data, embeddings, and model artifacts require residency assessment?
11. How should support access and subprocessors across multiple countries be governed?
12. Which copies must a deletion workflow cover?
13. Does pseudonymization automatically make data anonymous?
14. What evidence proves geographic policies are enforced in production?

Geographic partitioning is not merely picking a region for a database. The architecture must govern **the entire data lifecycle and every path data takes**, including primaries, replicas, caches, backups, logs, analytics, support, and subprocessors. When data classification, residency matrices, tenant placement, transfer policies, and key/access boundaries are clearly engineered, teams can deploy multi-region systems while upholding residency, reliability, and performance. Decisions must be verified through data-flow reviews, policy automation, audits, and recovery drills within the permitted geographic scope.
