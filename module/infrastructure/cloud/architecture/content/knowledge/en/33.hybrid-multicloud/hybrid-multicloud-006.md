# Standardize Application Contracts and Components Requiring Portability

Hybrid cloud and multi-cloud architectures often begin with a practical need: some workloads must remain in a private data center, others run on public cloud, or the organization wants the ability to move services between providers due to cost, geography, compliance, and reliability requirements. Yet deploying the same application in two environments does not automatically create portability. APIs, schemas, identity, storage, messaging, observability, and operational procedures may carry different semantics even when service names look similar.

**Standardizing application contracts** means defining the interfaces, semantics, data, and behaviors components must adhere to so they can interoperate regardless of where they are deployed. **Portability** is the degree to which a workload or component can be built, deployed, operated, and migrated to another environment with controlled changes. Not every component needs total portability. The goal is to define boundaries: which parts should use shared contracts, which are allowed to leverage provider-specific services, and which adapters/anti-corruption layers protect the domain from platform differences.

This lesson belongs to the **Hybrid and Multi-Cloud** chapter of the **Cloud Architecture** learning path. The path guides designing cloud application architectures from business requirements through networking, compute, data, and deployment models, balancing reliability, security, scalability, cost, and operations. This lesson focuses on standardizing high-value contracts, choosing portability boundaries, and managing change when workloads span multiple platforms.

After this lesson, you will be able to:

- Distinguish portability across source, artifact, runtime, data, operations, and business contracts.
- Define stable application contracts for APIs, events, schemas, and error semantics.
- Select open standards and common protocols at integration boundaries.
- Design ports/adapters to isolate provider-specific services.
- Distinguish useful abstractions from lowest-common-denominator platforms.
- Evaluate portability across compute, storage, identity, messaging, and observability.
- Manage schema/version compatibility and contract testing.
- Plan data migration, cutover, rollback, and dual-run phases.
- Measure lock-in, switching costs, and operational readiness.

## 1. Portability Is More Than Running the Same Container

A container image can run on multiple Kubernetes clusters, yet the application may still depend on a provider’s managed database, object storage API, identity provider, messaging service, KMS, DNS, load balancer, and observability services. When moving runtimes, those dependencies may require replacement or migration.

Evaluate portability across multiple layers:

| Layer | Question |
| --- | --- |
| Source code | Does domain logic depend on proprietary SDKs/APIs? |
| Build artifact | Can artifacts be built from the same source with pinned dependencies? |
| Runtime | Does it require a specific OS, kernel, architecture, or orchestrator? |
| Configuration | Are there contracts and mappings across environments? |
| Identity/security | Can workload identities, roles, and policies map to another platform? |
| Data | Can schemas, export/import, consistency, and encryption keys be moved? |
| Integration | Do APIs, events, queues, and protocols have provider-independent contracts? |
| Operations | Are logging, metrics, tracing, deployment, and incident workflows equivalent? |
| Governance | Are policies, auditing, residency, and control evidence preserved? |

Compute-layer portability alone may be insufficient to move a workload if data and integrations cannot move within the allowed RTO/RPO.

## 2. Define Portability Goals Before Standardizing

Multi-cloud is not a goal in itself. Identify why portability is needed:

- **Exit strategy:** ability to leave a provider if pricing, contracts, or services change.
- **Regulatory/data residency:** deploy part of a workload in an approved location.
- **Resilience:** maintain an alternate recovery location if a provider/region suffers an outage.
- **Acquisition or divestiture:** separate workloads into another account/organization.
- **Hybrid integration:** connect data centers/on-premises systems with public cloud.
- **Workload placement:** pick runtime locations suited to latency, GPUs, data gravity, or cost.
- **Vendor negotiation:** reduce leverage imbalance through credible switching capability.

Different goals require different degrees of portability. Cross-region disaster recovery may need backup/restore and redeployment rather than running active-active on two clouds. An exit strategy may require exporting data and redeploying within a few months rather than abstracting every service from day one.

## 3. Application Contracts Are Stable Boundaries

A good contract describes the behavior consumers can rely upon rather than how a provider implements it internally.

An application contract typically covers:

- Operations, resources, and payloads.
- Request/response schemas or event schemas.
- Authentication and authorization expectations.
- Error model and retryability.
- Timeouts/deadlines and cancellation.
- Idempotency, ordering, and consistency.
- Pagination, filtering, and rate limits.
- Versioning and compatibility policies.
- Data classification and retention.
- SLO, availability, and support expectations.

Contracts must be specific enough that two different implementations remain interchangeable without forcing consumers to understand the provider.

## 4. Standardize API Contracts

For HTTP APIs, standardize resource semantics, methods, status codes, pagination, error envelopes, idempotency, and trace contexts. OpenAPI is one way to describe contracts to generate clients/servers, validate payloads, and review breaking changes.

Example error envelope:

~~~json
{
  "type": "https://api.example.com/errors/version-conflict",
  "title": "Resource version conflict",
  "status": 409,
  "code": "VERSION_CONFLICT",
  "correlationId": "corr-82a1",
  "retryable": false
}
~~~

Consumers should rely on documented statuses/codes and semantics, never parse free-form messages or depend on provider exception names. Avoid returning raw provider errors because they can leak internal details and couple clients to a specific implementation.

### 4.1. Standardize Error Semantics

Two databases or queues may return different errors for the same situation. Adapters must map errors to stable domain/application errors:

| Situation | Application contract |
| --- | --- |
| Resource does not exist | NOT_FOUND |
| Version mismatch | CONFLICT |
| Caller lacks permission | FORBIDDEN |
| Over quota | RATE_LIMITED or QUOTA_EXCEEDED |
| Dependency temporarily unavailable | UNAVAILABLE, retryable per policy |
| Payload violates schema | INVALID_ARGUMENT |
| Commit result indeterminate | UNKNOWN_OUTCOME, requires query/reconciliation |

Do not map every provider error to 500 and retry indefinitely. Retryability and unknown-outcome semantics directly affect correctness.

## 5. Schema and Version Compatibility

API/event contracts outlive individual deployments. Producers and consumers may upgrade at different times; multi-cloud setups may also span multiple release channels. Backward/forward compatibility must be managed.

Common practices:

- Prefer additive changes: add optional fields instead of changing existing field meanings.
- Never reuse old fields for new meanings.
- Consumers ignore unknown fields when the schema contract allows.
- Never turn optional fields into required ones in a minor version.
- Use an explicit enum evolution policy.
- Version events/schemas independently of application builds.
- Maintain deprecation windows, owners, and migration dates.
- Run contract tests between producers and consumers.
- Store versioned, audited schema registry/contract artifacts.

### 5.1. Expand–Migrate–Contract

1. Expand: add new fields/schemas while remaining compatible.
2. Deploy consumers capable of reading both old and new formats.
3. Deploy producers to start emitting the new fields.
4. Backfill data or replay events if needed.
5. Measure legacy consumers and confirm migration completion.
6. Contract: remove old fields after the deprecation window and verification.

For cross-provider migrations, a dual-read/dual-write phase can ease gradual cutover, but requires handling ordering, duplicates, and the source of truth.

## 6. Event Contracts and Messaging Portability

Message brokers differ in partitioning, ordering, retention, transactions, delivery guarantees, consumer groups, acknowledgments, and schema integration. An abstraction exposing only publish/subscribe methods is insufficient if it hides critical semantics.

An event contract should specify:

- Event ID, type, source, and schema version.
- Aggregate/business key and partitioning expectations.
- Correlation/causation context.
- Ordering scope.
- Delivery semantics and duplicate handling.
- Retention/replay expectations.
- Dead-letter behavior.
- Payload size and throughput limits.
- Security identity, encryption, and tenant context.

### 6.1. Semantic Portability

Suppose an application needs event ordering per booking ID. One implementation may use partition keys, while another uses subjects/sessions. Adapters must ensure consumers receive the promised ordering scope. If a provider guarantees ordering only within a partition, the contract cannot promise global ordering without additional coordination.

Avoid generic “exactly once” claims in contracts. Specify which boundary achieves an exactly-once effect, which transactions are covered, and how external side effects outside the broker are handled.

## 7. Data Contracts and Database Portability

Database portability is more than transferring SQL schemas. Engines differ in transaction isolation semantics, JSON handling, collations, sequences, locking, indexes, stored procedures, generated columns, and query planners.

A data contract should specify:

- Entity/aggregate ownership.
- Schemas and field meanings.
- Primary/business keys.
- Nullability and constraints.
- Transaction boundaries and isolation requirements.
- Ordering/version semantics.
- Timestamps/time zones and precision.
- Decimal/currency precision.
- Retention, deletion, and export formats.
- Encryption, key management, and residency.

### 7.1. Avoid Implicit Engine Dependencies

If domain logic relies on stored procedures or vendor-specific queries, switching engines may require rewriting logic. That is not always wrong; stored procedures can be sound choices for performance and correctness. However, such dependencies should be documented as provider-specific boundaries rather than assuming standard SQL is portable.

### 7.2. Data Export/Import Contracts

Export formats must specify encoding, schema versions, ordering, checkpoints, checksums, encryption, metadata, and resume behavior. CSV does not preserve data types, null semantics, or time zones on its own. Large migrations require snapshots plus CDC/log replay or an equivalent strategy.

## 8. Identity Contracts and Authorization Mapping

IAM models differ across cloud providers, Kubernetes, on-premises directories, and SaaS identity platforms. Applications should use identity abstractions grounded in business meaning: principal, subject, tenant, roles/permissions, audience, and authorization decisions.

Do not force every policy into a single common role string when semantics diverge. A contract can specify:

- Workload identity authenticated via platform mechanisms.
- Principal subjects/audiences in a published format.
- Authorization based on application permissions/resources.
- Tenant scope verified from a trusted source.
- Token lifetimes, refresh, and revocation behavior.
- Audit fields and policy decisions.

Adapters map cloud roles/service accounts to application principals. Never allow applications to trust caller-supplied claims without verifying issuer/signature/audience.

## 9. Secret, KMS, and Certificate Portability

Every provider exposes different secret manager, KMS, and certificate service APIs/policies. Standardize required behaviors instead of abstracting every cryptographic primitive.

A secret port can expose get/version/rotate metadata, but should not dump all secrets to applications. A KMS port can expose encrypt/decrypt/wrap/unwrap by key reference. Exporting raw key material may be prohibited by policy or HSM boundaries; migrations may require re-encryption rather than copying keys.

Define:

- Key ownership and key custody.
- Algorithms/key sizes/usages.
- Envelope encryption formats.
- Key ID/version metadata embedded in ciphertext.
- Rotation and decryption retention.
- Certificate trust chains and renewal.
- Workload identities authorized for access.
- DR/key availability and residency.

Portability must never weaken security. If one provider supports HSM policies or customer-managed keys lacking an equivalent on another provider, treat that as a capability gap and decide explicitly whether it is acceptable.

## 10. Object Storage Contracts

Object storage APIs can appear similar while differing in consistency, versioning, multipart uploads, lifecycles, ACLs/IAM, event notifications, retention locks, metadata, and error semantics.

A storage port should express business needs:

- Put/get objects with keys and content metadata.
- Conditional writes/version checks.
- Multipart uploads when needed.
- Range reads.
- Object versioning/retention policies.
- Delete semantics and legal holds.
- Encryption/key references.
- Lifecycle tiering.
- Event notification contracts.
- Checksums and integrity validation.

Do not embed bucket names or provider ARNs in the domain model when only logical storage locations are needed. Map logical containers/object keys to provider resources in the adapter/configuration layer.

## 11. Compute and Runtime Portability

VMs, containers, Kubernetes, serverless functions, and managed application platforms offer differing portability levels.

| Model | Portability | Common dependencies |
| --- | --- | --- |
| OCI container | Relatively high if image is portable | Kernel/architecture, runtime, networking, storage, and secret integration |
| Kubernetes workload | Higher within the Kubernetes ecosystem | API versions, CRDs, CNI/CSI, ingress, identity, and policies |
| VM image | Depends on formats/drivers/hypervisors | Boot modes, device drivers, licensing, and cloud-init |
| Serverless function | Usually more provider-coupled | Event sources, IAM, timeouts/runtimes, deployment packages |
| Managed application platform | Platform-coupled | Scaling, routing, buildpacks, config, and add-ons |

Select runtimes based on real benefits. Do not migrate every workload to Kubernetes just to appear portable if the team lacks cluster operating skills and managed services fit better.

## 12. Platform Capability Matrix

Before standardizing, build a matrix comparing capabilities across environments. Do not compare service names alone.

| Capability | Provider/on-prem A | Provider B | Application contract |
| --- | --- | --- | --- |
| Container runtime | Kubernetes | Managed Kubernetes | OCI images, health/port/resource contracts |
| Object storage | S3-compatible | Native object API | Logical object store contract + adapter |
| Queue | Managed queue | Kafka-like broker | Event delivery/ordering contract |
| Database | PostgreSQL-compatible | Managed relational engine | SQL feature subset + migration tests |
| Identity | Cloud IAM | Federated IAM | Workload principals + app authorization |
| Secrets | Vault | Native secret manager | Secret references/access lifecycle |
| Observability | OpenTelemetry collector | Native monitoring | OTLP/resource attributes + SLO contract |
| KMS | HSM-backed KMS | Managed KMS | Envelope encryption metadata and rotation |

“S3-compatible” does not mean every S3 API/feature behaves identically. “PostgreSQL-compatible” does not guarantee identical extensions, replication, and planner semantics. The matrix must record versions, quotas, SLAs, limitations, and operational ownership.

## 13. Ports and Adapters / Hexagonal Architecture

Ports and adapters ensure domain/application logic depends on application-defined interfaces. Adapters implement those interfaces using specific databases, queues, object stores, or identity systems.

~~~mermaid
flowchart TB
    API["HTTP / Event entry adapters"] --> APP["Application use cases"]
    APP --> D["Domain model"]
    APP --> P1["Storage port"]
    APP --> P2["Message port"]
    APP --> P3["Identity port"]
    A1["Provider A adapter"] --> P1
    A2["Provider B adapter"] --> P1
    B1["Queue adapter A"] --> P2
    B2["Queue adapter B"] --> P2
    I1["IAM adapter A"] --> P3
    I2["IAM adapter B"] --> P3
~~~

Ports should reflect real use-case needs. For instance, `BookingRepository` defines contracts for reserve/confirm/cancel with version semantics; do not build a generic database interface with hundreds of methods mirroring every engine feature.

### 13.1. Anti-Corruption Layer

When integrating legacy/on-premises systems or provider-specific APIs, an anti-corruption layer translates external models, errors, and semantics into domain contracts. It prevents external models from leaking into the core application.

Adapters must do more than rename methods. They must enforce behavioral contracts: timeouts, retries, consistency, partial failures, idempotency, and error mapping.

## 14. Open Standards and Common Protocols

Open standards can lower integration costs and improve replaceability, though maturity and feature coverage must be evaluated.

Examples:

- HTTP/REST, gRPC, and OpenAPI for APIs.
- W3C Trace Context and OpenTelemetry for tracing/telemetry.
- OCI image format for container artifacts.
- Kubernetes API for orchestration where appropriate.
- CloudEvents or schema-defined event envelopes for event metadata.
- SQL/standard data formats such as Parquet/Avro/JSON by use case.
- OIDC/OAuth 2.0 and SAML for identity federation.
- Terraform/OpenTofu or suitable IaC standards for provisioning.

Standards do not automatically guarantee interoperability. Two implementations may differ in versions, extensions, defaults, or semantics. Conformance tests and documented profiles/subsets are required.

## 15. Right-Sized Abstraction

Good abstractions hide differences irrelevant to consumers while preserving needed capabilities. Overly broad abstractions degrade into the lowest common denominator, stripping useful features and adding complexity.

Three tiers can be used:

1. **Direct provider API:** accept intentional lock-in when a service delivers major benefits.
2. **Application port + adapter:** the domain needs a narrow set of operations, and adapters map them to providers.
3. **Portable platform contract:** shared across multiple workloads/teams requiring identical, verifiable semantics.

Do not invent shared abstractions just to make every service look identical. If a provider-native service offers huge advantages and migration is not a realistic near-term goal, direct usage paired with an exit plan can make more sense.

## 16. What Should and Should Not Be Portable

| Component | Typical sound direction | Rationale |
| --- | --- | --- |
| Domain rules | Portable in core application | Should not depend on cloud SDKs |
| API/event contracts | Standardized | Multiple consumers/providers must interoperate |
| Container artifacts | Portable when workload fits | Simplifies runtime movement |
| Observability fields | Standardized | Enables correlation and tool switching |
| Secret values | Not shared across environments | Requires separate scoping and custody |
| Data store implementations | Can be provider-specific | Consistency/performance vary |
| KMS/HSM | Can be native with a migration strategy | Key protection is a sensitive capability |
| Analytics/AI managed services | Can be provider-specific | Capabilities/pricing evolve rapidly |
| Deployment workflows | Standardized interface, dedicated adapters | Cloud APIs differ |
| Business workflow state | Portable via data contracts | Required for recovery/migration |

Choose portability based on business value, not the count of abstract interfaces.

## 17. Contract and Conformance Testing

An API contract test verifies that a new provider/adapter honors the exact behavior consumers expect. Consumer-driven contract testing is valuable when producers and consumers deploy independently.

Test categories:

- Schema validation and compatibility tests.
- API behavior/status/error contracts.
- Idempotency/retry/timeout behavior.
- Ordering and duplicate message semantics.
- Transaction isolation and concurrency.
- Object storage consistency/versioning/conditional writes.
- Identity claim/policy mappings.
- Encryption/decryption and key rotation compatibility.
- Observability propagation and audit fields.
- Performance/quotas/load limits.
- Disaster recovery/export/import.

### 17.1. Golden Conformance Suite

Maintain a test suite executed against every adapter/provider candidate. Tests must cover both success paths and edge cases: timeouts after commit, duplicate events, stale versions, permission denied, quota exceeded, partial batch failures, and reconnects after network partitions.

An adapter is deemed compatible only after passing the conformance suite for the published version/profile.

## 18. Adapter Versioning and Capability Discovery

Provider capabilities vary by region, plan, and version. Do not inspect provider names alone; perform capability discovery at provisioning/deployment time.

A capability record might look like:

~~~yaml
platform:
  name: provider-b
  region: region-2
  profileVersion: 3
capabilities:
  objectVersioning: true
  conditionalWrite: true
  orderedMessagesByKey: true
  transactionalOutbox: false
  customerManagedKey: true
limits:
  maxMessageBytes: 1048576
  maxBatchItems: 100
~~~

This is illustrative; parameters must be verified against the actual platform. Applications should select behavior from the capability contract rather than assuming every feature exists in every region.

## 19. Data Portability and Migration

Data is typically the hardest layer to move due to volume, dependencies, consistency, downtime, and egress costs.

Approaches:

- **Offline migration:** stop writes, export, import, validate, then cut over; simple but incurs long downtime.
- **Snapshot + delta/CDC:** copy baseline then replay changes; reduces downtime at the cost of complexity.
- **Dual-write:** write to both locations during transition; requires handling partial success and ordering.
- **Read shadowing:** send reads to the new system for comparison while returning results only from the primary source.
- **Progressive tenant migration:** move tenants/partitions in cohorts.
- **Rebuild derived data:** recreate search/caches/analytics from the source of truth instead of migrating every index.

### 19.1. Data Migration Sequence

1. Inventory datasets, owners, volumes, sensitivity, and residency.
2. Define schema mappings, type conversions, and invariants.
3. Choose snapshot/export methods and encrypted transport.
4. Transfer baseline data.
5. Capture CDC/log deltas or pause writes for the cutover window.
6. Import/replay and monitor lag.
7. Compare row counts, checksums, and business aggregates.
8. Run application conformance/synthetic transactions.
9. Cut over readers/writers with fencing and versioning.
10. Monitor discrepancies and the rollback window.
11. Retire the old system after retention/approvals.

Do not delete the old source the moment DNS or routing flips. Keep it read-only or backed up long enough for investigation and recovery.

## 20. Dual-Run, Shadow Traffic, and Cutover

Before shifting live traffic, run the new application in shadow mode: receive copied read requests without executing side effects. Compare responses, latency, and error semantics.

On write paths, shadowing must avoid real writes or triggering duplicate payments/emails/jobs. Run validation in read-only mode, using synthetic tenants, or in an isolated test environment.

Cutover requires:

- Freezing/coordinating schema changes.
- Establishing write authority.
- Draining inflight requests.
- Finalizing CDC checkpoints.
- Fencing the old writer.
- Switching routing and identity.
- Verifying data and business invariants.
- Monitoring rollback criteria.

Rolling back after the new system has accepted writes cannot be done by merely flipping DNS back. Reverse replication, reconciliation, or keeping the new platform as the source of truth is required.

## 21. Configuration and Deployment Portability

Do not hardcode provider resource IDs, ARNs, project names, or endpoints in domain logic. Use logical configuration keys with provider-specific mappings in the deployment layer.

However, config contracts must describe differences affecting behavior: storage consistency, queue ordering, KMS key access, network timeouts, autoscaling limits, and service quotas.

IaC modules can expose shared interfaces for common resources while providing extension points and capability flags. Do not force provider-specific features into one shared boolean when semantics differ.

### 21.1. Artifact Promotion

Build artifacts once, sign them, and promote the same digest across dev/staging/production or other environments when compatibility allows. Do not rebuild different artifacts per provider without provenance tracking. Inject configuration and secrets per environment.

## 22. Cross-Platform Observability and Operations

When workloads span providers, metrics/logs/traces easily diverge in schemas and naming. Standardizing resource attributes, service identities, regions/environments, trace contexts, error taxonomies, and SLOs makes comparisons possible.

Areas needing contracts:

- Service name/version/environment.
- Region/provider/cluster attributes.
- Log severity and structured fields.
- Trace propagation and sampling policies.
- Metric naming/units/temporality.
- SLO/error budget semantics.
- Alert ownership/escalation.
- Audit trails and retention.
- Incident IDs/correlation IDs.

OpenTelemetry provides a standard instrumentation/transport layer, though exporters/backends may still differ. Review sampling, cardinality, cost, and data residency.

## 23. Security, Policy, and Compliance Portability

Common policies should express control objectives, while adapters/platform policies map to concrete enforcement points.

For example, the control objective “storage objects must be encrypted with organization-controlled keys” can be implemented via different KMS/object storage APIs. Conformance tests must prove encryption is actually enabled, key ownership is correct, audit logs exist, and cross-region copies obey policy.

Do not inspect only option names in IaC. Verify actual state, effective policies, identity permissions, and audit evidence. Multi-cloud does not remove obligations around data classification, deletion requests, residency, and access reviews.

## 24. Measuring Lock-In and Portability Risk

Lock-in is not binary. Evaluate it across:

- Count of provider-specific APIs/dependencies in domain code.
- Number of adapters needing replacement.
- Data volume to export and transfer duration.
- Ability to recreate infrastructure from IaC in another environment.
- Compatibility gaps in databases/queues/object storage.
- Key custody and cryptographic migration constraints.
- Network egress and data transfer costs.
- Number of operational runbooks requiring rewrites.
- Vendor-specific skills and support dependencies.
- Time to reach production readiness after switching.

Portability tiers can help classify workloads:

| Tier | Description | Example |
| --- | --- | --- |
| P0: Native | Uses provider services directly with no exit abstraction | Specialized managed AI/services |
| P1: Adaptable | Has adapters or known export paths | Storage/queues behind application ports |
| P2: Portable | Contracts and artifacts run across multiple tested platforms | OCI workloads + open APIs |
| P3: Proven portable | End-to-end switchover rehearsed within target RTO/RPO | Workloads/data tested via migration drills |

Never claim P3 based on paper architecture alone; migration drill evidence is required.

## 25. Example: Hybrid and Multi-Cloud Booking Platform

A SaaS platform runs core booking on public cloud, warehouse hardware in an on-premises data center, and analytics on another cloud. The goal is to be able to relocate the booking service if the current provider raises prices or suffers regional outages, while keeping payment and inventory consistency intact.

### 25.1. Contract Boundaries

- The booking domain has provider-independent API contracts and event schemas.
- The inventory adapter connects to the on-prem system via an API/event gateway.
- Database implementations sit behind repository/domain boundaries, with transaction semantics and migration constraints documented explicitly.
- Object storage uses a logical document port; adapters map metadata/versioning/retention.
- Identity federates workload identities, while application authorization uses the domain permission model.
- Observability fields are standardized with OpenTelemetry and structured logging.
- Payment provider integration retains a dedicated adapter due to idempotency, webhook, and reconciliation semantics.

~~~mermaid
flowchart TB
    API["Booking API contract"] --> APP["Booking application/domain"]
    APP --> DBP["Repository port"]
    APP --> INV["Inventory port"]
    APP --> DOC["Document storage port"]
    APP --> PAY["Payment port"]
    DBP --> DBA["Cloud A database adapter"]
    DBP --> DBB["Cloud B database adapter"]
    INV --> ONP["On-prem inventory adapter"]
    DOC --> OA["Object store adapter A"]
    DOC --> OB["Object store adapter B"]
    PAY --> PSP["Payment provider adapter"]
~~~

### 25.2. Migration Sequence

1. Decouple provider SDKs from domain logic and build adapters for database/storage/identity.
2. Build a conformance suite for contracts and error semantics.
3. Provision the target platform with IaC and dedicated workload identities.
4. Copy baseline data, enable CDC, and verify schemas/invariants.
5. Run shadow reads and synthetic bookings without real side effects.
6. Measure latency, quotas, consistency, and operational capability.
7. Migrate a small tenant/cohort while retaining single write authority.
8. Expand cutover after reconciliation passes.
9. Keep the old system read-only during the rollback window.
10. Retire only after backups, retention, auditing, and support sign-offs are complete.

### 25.3. Trade-Offs

- Native databases can optimize performance but increase migration effort.
- Open protocols can reduce adapter cost but do not unify transaction semantics.
- Multi-cloud active-active writes can raise availability but make booking/inventory invariants harder to enforce.
- Hybrid on-prem integration cuts latency to local hardware but increases network/security operations.
- Standardized observability lowers switching costs, though telemetry pipelines still need provider-specific tuning.

## 26. Common Design Mistakes

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Goal is “portable everywhere” | Overly broad abstractions, lost capabilities | Tie portability to business objectives |
| Using containers and claiming portability | Data/identity/queues remain locked in | Evaluate all dependency layers |
| Lowest-common-denominator interfaces | Cannot leverage critical semantics | Design ports per use case with explicit capabilities |
| Hiding transaction semantics in adapters | Duplicates/lost updates when switching providers | Explicit consistency/idempotency contracts |
| Using standard SQL while relying on extensions | Failed migrations or changed behavior | Feature inventory and conformance tests |
| Assuming S3-compatible stores are identical | Versioning/consistency/ACLs differ | Test exact API profiles |
| Replicating all data globally | Higher costs and residency violations | Data classification and placement policies |
| Dual-write without reconciliation | Data sources diverge | Outbox/CDC, idempotency, and authority |
| Cutover by flipping DNS only | Old writers and inflight sessions keep mutating | Fencing, draining, and data checkpoints |
| Rollback ignoring new writes | Data loss after cutback | Reverse sync/reconciliation or fail-forward |
| Returning raw provider errors to clients | Consumers couple to the provider | Error mapping and stable contracts |
| Ignoring quotas/limits | Adapters pass tests yet fail under load | Capability/limit matrices and load tests |
| Untested identity mappings | Excessive privileges or denied requests | Principal/policy conformance tests |
| Standardizing observability by field names only | Sampling/units/retention diverge | Telemetry contracts and dashboard tests |
| Measuring portability by adapter count | Does not reflect real migration duration | Migration drills and portability tiers |
| Ignoring egress and data gravity | Exit plans become unaffordable or unfeasible | Cost models and data transfer rehearsals |

## 27. Standardization and Implementation Process

1. **Identify portability drivers:** exit, DR, residency, hybrid integration, latency, or workload placement.
2. **Inventory dependencies:** SDKs, APIs, databases, queues, storage, identity, KMS, observability, and operations.
3. **Classify dependencies:** portable, adaptable, provider-native, or unmovable by policy.
4. **Define contracts:** APIs, events, schemas, errors, identity, storage, and SLOs.
5. **Define capability profiles:** versions, quotas, consistency, ordering, retention, and limitations per platform.
6. **Design ports/adapters:** keep domain logic independent without hiding critical semantics.
7. **Standardize artifacts/configs:** pin image digests, schemas, config contracts, and secret references.
8. **Build conformance suites:** run identical tests across all adapter/platform candidates.
9. **Design data migration:** snapshots, CDC, reconciliation, authority, and cutover.
10. **Design security/operations:** identity, KMS, residency, observability, auditing, and on-call.
11. **Benchmark and model costs:** latency, throughput, egress, support effort, and quotas.
12. **Rehearse migration/exit:** move one workload/tenant end-to-end and measure duration.
13. **Review periodically:** track provider API changes, deprecations, lock-in risks, and capability gaps.

## 28. Well-Architected Assessment

| Perspective | Design questions |
| --- | --- |
| **Reliability** | Do contracts specify timeouts, retries, idempotency, and consistency? Can platforms switch, data recover, and rollbacks complete within targets? |
| **Security** | Are identity, key custody, residency, auditing, and secret scopes preserved across moves? Do adapters enforce tenant authorization? |
| **Performance Efficiency** | Do abstractions add latency? Are key provider capabilities lost? Do cross-cloud transfers stay within SLOs? |
| **Cost Optimization** | Are portability layers worth their operational cost? Are egress, dual-run, duplicate capacity, and adapter maintenance included? |
| **Operational Excellence** | Are capability matrices, conformance tests, dependency inventories, runbooks, owners, and migration drills in place? |

### Acceptance Checklist

- [ ] Portability goals and workload scope are defined by business value.
- [ ] Dependency inventory covers runtime, data, identity, secrets, messaging, and operations.
- [ ] API/event/error contracts have versioning and compatibility policies.
- [ ] Retry, timeout, idempotency, ordering, and consistency semantics are published.
- [ ] Data contracts define schemas, precision, time zones, transactions, and retention.
- [ ] Provider-specific code sits behind adapters or is explicitly documented as a native dependency.
- [ ] Abstractions preserve needed capabilities without hiding critical semantics.
- [ ] Capability matrices cover versions, quotas, limitations, and regional support.
- [ ] Identity/KMS/certificate migration does not weaken security or key custody.
- [ ] Artifact provenance, config contracts, and secret references are managed separately.
- [ ] State/data exports support encryption, checksums, schema versions, and resumption.
- [ ] Contract/conformance tests run against all supported implementations.
- [ ] Shadow/dual-run testing avoids duplicate side effects.
- [ ] Cutover includes checkpoints, writer fencing, reconciliation, and rollback criteria.
- [ ] Data residency covers replicas, backups, logs, and telemetry.
- [ ] Egress, dual-run, support, and operational costs are accounted for.
- [ ] Migration drills prove the declared portability tier.

## 29. Applied Exercise

An enterprise operates a booking platform on Cloud A. The application uses a managed relational database, object storage, a managed queue, provider IAM, and native observability services. One department has data that must remain in an internal data center; leadership wants an exit option to Cloud B within six months. Bookings and payments require clear idempotency/ordering, document archives have long retention, while analytics can be rebuilt.

Design the following:

1. Which dependency inventory should be built, and how would you classify items as portable, adaptable, or native?
2. Which application/API/event contracts should be standardized first?
3. Which database semantics could obstruct switching engines?
4. How should queue ordering, redelivery, and transaction semantics be mapped?
5. Design an object storage port while preserving versioning, retention, and encryption.
6. How can identity/KMS/certificates be federated or migrated?
7. Which adapters should be built, and which services are not worth abstracting?
8. Should data migration use snapshots, CDC, dual-run, or progressive tenant cutover?
9. How do you ensure there are never two simultaneous writers and no lost bookings/payments during cutover?
10. Which conformance suite, cost model, and migration drill would prove the exit option is practical?

A well-grounded approach standardizes API/event/error/data contracts and telemetry first; keeps domain logic independent behind narrow ports; uses adapters for queues/storage/identity; documents database feature gaps rather than assuming SQL portability; and executes snapshot+CDC with reconciliation. Cloud B must pass conformance, load, security, and DR tests before taking production traffic. Managed analytics or native services should be replaced only when the business case is strong enough.

**Core takeaway:** standardize contracts so components agree on behavior, not to make every provider look alike. Portability must be evaluated across source, runtime, data, identity, integration, and operations. Keep domain logic portable where it delivers value, isolate native dependencies with adapters, verify with conformance suites, and prove readiness with migration drills. A credible exit strategy requires data transfer paths, write authority, security, cost models, and operational procedures—not just a container image that runs in multiple places.
