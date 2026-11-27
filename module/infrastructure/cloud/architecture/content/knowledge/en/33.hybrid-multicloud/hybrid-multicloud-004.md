# Partition Workloads by Dependencies, Data, and Latency

## 1. Why Partition Workloads Before Choosing a Cloud?

An enterprise system typically spans multiple workload types: transactional applications, legacy systems in a data center, data analytics, partner APIs, batch jobs, IoT devices, and low-latency services. These workloads do not share the same requirements for data, connectivity, compliance, latency, availability, or operations. Moving everything to a single cloud or spreading everything across multiple providers without analyzing dependencies can increase cost, latency, and risk.

**Workload placement** is the decision of where a workload runs and where its data is stored: on-premises, private cloud, public cloud, multiple regions, edge, or multiple cloud providers. This decision should be based on the relationship between the workload and its dependent systems, data location, latency requirements, regulatory constraints, and operational capability.

In the **CLOUD_ARCHITECTURE** module, cloud architecture is designed from business requirements through networking, compute, data, and deployment models, while balancing reliability, security, scalability, cost, and operations under Well-Architected principles. Hybrid and multi-cloud are architectural options to satisfy real constraints, not goals in themselves.

After this lesson, you will be able to:

- Build a dependency map and classify workloads before making placement decisions.
- Evaluate data gravity, data locality, latency, and network paths.
- Decide which components remain on-premises/private cloud and which move to public cloud.
- Distinguish between hybrid cloud, multi-cloud, and multi-region.
- Select placement models for transactional, analytics, batch, edge, and integration workloads.
- Design data replication, ownership, consistency, and migration boundaries.
- Evaluate cross-environment connectivity, identity, security, observability, resilience, and cost.
- Build a workload placement matrix and validate it with measurements.

## 2. Start from Workloads and Business Constraints

### 2.1. The Workload Is the Unit of Analysis

Do not decide to “move the ERP system to the cloud” as if the ERP were a single monolith. Decompose it into identifiable workloads or capabilities:

- API/frontend.
- Transaction processing.
- Batch and scheduled jobs.
- Databases and object storage.
- Search/indexing.
- Integration adapters to legacy systems.
- Analytics/warehouses.
- Identity, auditing, and security services.
- Control plane/management tooling.

A single application can consist of workloads placed across multiple environments. However, the more granular the placement split, the greater the number of boundaries and network dependencies. Find sensible boundaries based on data ownership, failure domains, and independent deployability.

### 2.2. Workload Profile

Each workload should have a profile:

| Attribute | Question |
|---|---|
| Business capability | Which user journey does the workload serve? What is its criticality? |
| Owner | Which team owns the code and operations? |
| Dependencies | Which services, databases, queues, identities, or partners must it call? |
| Data | Which data does it read/write? Who is the source of truth? |
| Latency | What are the p95/p99 targets and timeout budget? |
| Throughput | RPS, concurrent users, batch volume, data growth? |
| Availability | SLO, RTO, RPO, and degraded mode? |
| Security | Classification, identity, network boundaries, keys, and auditing? |
| Compliance | Residency, retention, transfer, and access constraints? |
| Lifecycle | Release cadence, scaling pattern, maintenance windows? |
| Cost | Compute, storage, egress, licensing, support, and operations? |

Do not choose placement before knowing which data and dependencies a workload needs to access. A stateless service is easier to move than a database or a system relying on legacy protocols tied to an internal network.

## 3. Dependency Mapping: Workloads Do Not Run in Isolation

### 3.1. Dependency Classification

| Dependency type | Example | Impact on placement |
|---|---|---|
| Synchronous API | Booking calls Inventory | Every network round trip can increase latency |
| Database transaction | ERP writes order and inventory | Transaction boundaries and consistency limit splitting |
| Event/message | Order event to notification worker | Can be asynchronous, but requires delivery/replay semantics |
| Shared identity | SSO, directory, token issuer | Auth paths must be reachable with a failure strategy |
| File/data transfer | ETL reads object storage or NAS | Data volume and egress can dominate cost |
| Legacy protocol | Mainframe, SMB, proprietary TCP | May need adapters, gateways, or network extension |
| External provider | Payment, tax, SMS | Placement depends on endpoints, quotas, and contracts |
| Operational dependency | KMS, DNS, monitoring, secrets | Workloads fail if control/service planes are unreachable |

### 3.2. Dependency Graph

Example BookingCloud system:

~~~mermaid
flowchart TB
    WEB["Web / mobile API"] --> BOOK["Booking service"]
    BOOK --> INV["Inventory service"]
    BOOK --> PAY["Payment provider"]
    BOOK --> DB[("Booking database")]
    INV --> LEGACY["On-prem inventory ERP"]
    BOOK --> BUS[("Event broker")]
    BUS --> NOTIFY["Notification worker"]
    BUS --> ANALYTICS["Analytics pipeline"]
    ANALYTICS --> LAKE[("Cloud data lake")]
    WEB --> IDP["Corporate / cloud identity"]
~~~

If the Booking service runs on public cloud while the Inventory ERP remains on-premises, a booking request may have to traverse the hybrid link. If that path has high latency or instability, synchronous transactions can suffer. Another option is placing an adapter or inventory capability near the ERP and exposing an API/event interface to the cloud.

### 3.3. Distinguish Hard and Soft Dependencies

- **Hard dependency:** the workload cannot complete the operation if the dependency is unreachable, such as authorizing payment in a synchronous checkout flow.
- **Soft dependency:** can be deferred or degraded, such as sending a confirmation email via a queue after the booking commits.
- **Optional dependency:** serves secondary features only, such as recommendations.

This distinction helps determine which dependencies need high-speed links, which can become event-driven, and which should stay off the critical path.

### 3.4. Critical Path

Map the critical path for each user journey. For booking:

1. Authenticate caller.
2. Check availability.
3. Hold inventory.
4. Save booking.
5. Authorize payment if required by the flow.
6. Publish event.
7. Send notification asynchronously.

Steps requiring consistency or immediate response usually belong on the critical path. Notifications/reporting can run asynchronously to reduce cross-cloud/on-premises calls.

## 4. Data Gravity and Data Ownership

### 4.1. Data Gravity

Large datasets with many consumers or continuous writes tend to pull compute and services closer to where the data is stored. Moving small compute close to a data store can be cheaper and less risky than transferring terabytes of data over the network.

Evaluate:

- Total volume and data growth rate.
- Read/write rates and query counts.
- Number of dependent workloads.
- Network egress and replication costs.
- Data residency, encryption, and key management.
- Backup/restore and lifecycle.
- Time required to switch the source of truth.

### 4.2. Source of Truth

Each data domain needs a clear authoritative location. For example:

- On-premises ERP is the source of truth for legacy inventory.
- The cloud booking database is the source of truth for the booking lifecycle.
- The data lake is for analytics, not a replacement for the transactional database.
- The search index is a derived view that can be rebuilt from the authoritative source.

If two environments both write the same record without ownership or conflict resolution, the system risks split-brain and data inconsistency.

### 4.3. Data Placement Matrix

| Data class | Authoritative location | Replicas/consumers | Appropriate consistency |
|---|---|---|---|
| Booking transaction | Primary cloud region | DR replica | Strong/transactional per domain |
| Legacy inventory | On-prem ERP | Cloud API/cache | Needs freshness bounds; holds via owner service |
| Public catalog | Cloud object store | CDN/edge cache | Eventual/cacheable |
| Analytics events | Broker/data lake | Warehouse | Eventual, replayable |
| Identity directory | Chosen identity platform | Workload tokens/caches | Per token/revocation policy |
| Audit records | Security-controlled store | SIEM/archive | Durable, tamper-resistant |

### 4.4. Avoid Copying All Data

Replicas reduce latency or improve availability, but increase data movement, key/secret distribution, deletion complexity, and compliance surface. Replicate only what consumers actually need; select minimal schemas/fields; define TTLs and purge semantics.

For personal data, deletion at the source may need to propagate to caches, search indexes, lakes, backups, and other providers under retention policies. Placement design must cover the full lifecycle, not just initial migration.

## 5. Latency and Network Paths

### 5.1. End-to-End Latency

Request duration is affected by:

\[
T_{\text{total}} =
T_{\text{client}} +
T_{\text{network}} +
T_{\text{queue}} +
T_{\text{compute}} +
T_{\text{data}} +
T_{\text{external}}
\]

When two workloads sit in different environments, every synchronous call typically adds DNS/routing, firewall/proxy, TLS, and network round-trip overhead. If the critical path contains several sequential calls, that overhead compounds.

### 5.2. Multi-Hop Example

Suppose a request travels:

Client → Cloud API → On-prem adapter → ERP database → Cloud API → Payment provider.

If each hybrid round trip takes 35 ms and the flow has 4 sequential round trips, network overhead is already around 140 ms before processing time. In practice, measure from actual network zones and peak hours; never treat illustrative numbers as commitments.

### 5.3. Reduce Round Trips

- Coalesce requests/batch queries if business semantics allow.
- Move notifications/reporting to event-driven flows.
- Place adapters close to legacy systems.
- Cache frequently read data with clear freshness contracts.
- Co-locate services with their authoritative databases.
- Avoid deep call chains across multiple clouds/providers.
- Use connection pooling, HTTP keep-alive, and gRPC/HTTP2 where appropriate.

Do not turn every synchronous call into an async one just to reduce latency. If users need immediate commit confirmation or resource ownership requires an online check, an eventual response may be inappropriate.

## 6. Hybrid Cloud, Multi-Cloud, and Multi-Region

| Model | Meaning | Typical rationale |
|---|---|---|
| Hybrid cloud | Combines on-premises/private cloud with public cloud | Legacy systems, residency, low-latency plant/branch, gradual migration |
| Multi-cloud | Uses two or more cloud providers for workloads or capabilities | Provider-specific capabilities, acquisitions, risk diversification, contracts |
| Multi-region | Runs the same provider across multiple regions | Geographic latency, disaster recovery, regional resilience |
| Hybrid + multi-cloud | On-prem/private combined with multiple public providers | Multiple simultaneous constraints, typically high operational complexity |

Multi-region is not automatically multi-cloud; two regions of the same provider are still one cloud provider. Hybrid does not necessarily involve two public cloud providers either.

### 6.1. Why Choose Hybrid?

- Legacy systems have protocols/hardware that are difficult to migrate.
- Data or processing must stay in a specific physical location.
- Workloads need direct connectivity to devices, factories, or branches.
- Phased migration to reduce cutover risk.
- Parts of the system have licenses or dependencies supported only in specific environments.

### 6.2. Why Choose Multi-Cloud?

- Provider-specific capabilities fit a workload well.
- Acquisitions or contracts introduce multiple clouds.
- Need to reduce dependence on a single provider for a critical capability.
- Workloads have differing deployment/market requirements.
- There is a proven, valuable portability strategy.

Do not choose multi-cloud assuming it automatically increases resilience. If applications, data, and operators are not designed to fail over across providers, having multiple cloud accounts can increase risk rather than reduce it.

## 7. Placement Patterns by Workload Type

### 7.1. Keep, Move, Split, Replace

| Pattern | Description | When suitable |
|---|---|---|
| Keep | Leave workload in its current location | High migration cost, tight dependencies, or no driver to change |
| Move | Migrate both workload and data | Clean boundary can be moved together with few cross-environment calls |
| Split | Separate a capability into an independent workload | Clear domain boundaries and data contracts |
| Replace | Swap an old component for a managed service/new API | Improves operations and migration is acceptable |
| Replicate | Create a read model/cache/copy near consumers | Read-heavy, with defined freshness and lifecycle |
| Edge | Process near data sources or users | Latency/volume needs local processing and logic is compact |

### 7.2. Transactional Workloads

Transactions requiring atomicity, isolation, and consistency should generally keep the service close to its authoritative data store. If a transaction must write across two environments, design distributed transactions, sagas, or explicit ownership boundaries; never rely on the network being “usually fast.”

### 7.3. Analytics and Batch

Analytics can run where the data lake/warehouse lives to minimize moving large datasets. Batch jobs can be scheduled off-peak or near data sources to reduce network load. Verify residency, export policies, throughput, and data freshness.

### 7.4. Legacy Integration

Keeping a legacy system in place while placing an integration adapter in the same network zone is a common pattern. The adapter translates protocols, validates identity, maps schemas, and publishes events/APIs to the cloud. The adapter must have HA, retries, idempotency, monitoring, and queuing/buffering during link outages.

### 7.5. SaaS/Third-Party

Sometimes a workload does not need to be hosted in your own cloud and can be consumed as SaaS. Evaluate data location, identity federation, exports, API quotas, auditing, service continuity, egress, contracts, and exit strategies.

## 8. Designing Hybrid and Multi-Cloud Connectivity

### 8.1. Connectivity Options

| Connection | Description | Trade-offs |
|---|---|---|
| Site-to-site VPN | Encrypted tunnel over the Internet | Faster to deploy; latency/jitter and throughput depend on Internet paths |
| Dedicated private circuit | Private connection to a provider | More consistent throughput/latency depending on route; higher cost and lead time |
| Transit hub/gateway | Connects multiple VPCs/VNets/on-prem | Centralized route management; must avoid route leaks and shared blast radius |
| Private endpoint | Accesses managed services over private paths | Reduces public exposure; requires DNS/routing/resource policies |
| Public API over TLS | Connects over the Internet to published endpoints | Easy to connect, but requires secure egress, certificates, auth, and rate limits |
| Service mesh federation | Connects service identities/policies across clusters/environments | Can improve L7 consistency, but adds control plane and complexity |

### 8.2. Network Segmentation

Do not connect entire on-prem and cloud networks as one flat network. Establish boundaries by environment, data tier, and trust domain; route only to required CIDRs/services; enforce firewalls, security groups, DNS policies, and egress controls.

### 8.3. Cross-Environment Identity

- Use federation/workload identity instead of shared static credentials.
- Verify issuer, audience, subject, and trust domain.
- Use mTLS for service connections requiring mutual authentication.
- Separate roles per environment/provider.
- Short-lived credentials and rotation.
- Audit cross-cloud role assumptions and privileged access.

Private connectivity does not mean a caller is authorized. Network reachability, service authentication, and application authorization are three distinct layers.

### 8.4. DNS and Service Discovery

Define private DNS zones, resolver forwarding, and naming conventions. Avoid having the same hostname resolve to different endpoints without a clear contract. DNS failover can be cached; coordinate TTLs, connection pools, health checks, and retries.

### 8.5. Cross-Environment Observability

Standardize service names, trace contexts, correlation IDs, timestamps, and resource attributes so traces span across cloud/on-prem/providers. Never include secrets, customer payloads, or sensitive identifiers in telemetry just for debugging convenience.

## 9. Consistency and Integration Patterns

### 9.1. Synchronous APIs

Suitable when callers need immediate results and dependencies meet latency/availability requirements. Must include timeouts, deadlines, budgeted retries, circuit breakers, and operation idempotency.

### 9.2. Event-Driven Integration

Suitable when consumers can process later, links may drop, or buffering is needed. Requires event schemas/versions, delivery semantics, idempotent consumers, replay, DLQs, and domain-appropriate ordering.

### 9.3. Store-and-Forward

An on-prem adapter can persist messages durably locally and forward them when the cloud link recovers. Define disk limits, retention, encryption, deduplication, and backpressure. When the buffer fills, enforce clear prioritization or rejection policies.

### 9.4. Data Synchronization

Replication/CDC must define:

- Source of truth.
- Ordering and transaction boundaries.
- Schema evolution.
- Duplicate/replay behavior.
- Conflict resolution.
- Lag SLAs and alerts.
- Delete/tombstone propagation.
- Recovery from full snapshots and incremental logs.

Do not use last-write-wins for every domain. Inventory/booking systems have business invariants that require explicit conflict policies.

## 10. Resilience: When an Environment Becomes Unreachable

### 10.1. Failure Scenarios

- VPN/private circuit cut.
- Provider region/service outage.
- DNS forwarding or identity federation failure.
- Misconfigured firewall/route update.
- Expired certificate.
- Rising replication lag.
- Provider API throttling or quota exhaustion.
- Control plane in one environment unable to deploy resources.

### 10.2. Degraded Mode

Define which operations can continue when a dependency is lost:

| Capability | When hybrid link drops | Possible behavior |
|---|---|---|
| Reading cacheable catalog | Can continue | Serve cache within freshness bounds |
| Creating booking needing authoritative inventory | May be unsafe | Reject/mark pending; do not confirm false availability |
| Notifications | Can be deferred | Queue and retry with bounds |
| Analytics ingestion | Can buffer | Store-and-forward and process later |
| Payment authorization | Depends on provider path | Unknown outcomes require reconciliation; never blindly recharge |
| Admin operations | Can be blocked | Fail closed and use audited break-glass |

### 10.3. RTO/RPO and Failover

RTO is the target time to restore service; RPO is the maximum acceptable data loss. In hybrid/multi-cloud, also account for DNS, credentials, network routes, quotas, image/secret availability, data replication, and operator actions.

A copy of data on another provider does not prove DR. Run restore/failover tests with real workloads and dependencies.

## 11. Cross-Cloud Security and Governance

### 11.1. Control Consistency

Standardize baselines for:

- Identity federation, MFA, privileged access, and short-lived credentials.
- Encryption in transit/at rest and key ownership.
- Network segmentation, private endpoints, and egress controls.
- Logging/auditing with retention and access policies.
- Vulnerability/image scanning and patching policies.
- Backups, restores, data classification, and deletion.
- Policy-as-code and exception expiration.

Provider-specific controls must map back to the same security requirements; never assume services with similar names share identical semantics.

### 11.2. Data Residency and Cross-Border Transfers

Identify which data classes are stored, processed, replicated, backed up, or supported from each geography. Cross-cloud transfers, telemetry exports, and backup replication can all count as data movement requiring review.

For specific legal obligations, legal/security/privacy owners must confirm based on data type, market, contracts, and processing purpose; architecture cannot infer compliance solely from region selection.

### 11.3. Shared Responsibility

Each provider defines different responsibility boundaries between provider and customer. Managed services reduce hardware operations, yet customers typically remain responsible for identity, data access, configuration, secrets, logging, and workload security. Maintain a control ownership matrix for each platform/service.

## 12. The True Cost of Hybrid and Multi-Cloud

### 12.1. Frequently Overlooked Costs

- Egress and inter-region/inter-cloud data transfers.
- Dedicated connectivity, VPN gateways, transit hubs, and firewalls.
- Replication, CDC, backups, and duplicate storage.
- Observability ingestion/export across systems.
- License portability, support plans, and marketplace charges.
- Network/security appliances and certificate lifecycles.
- Cross-cloud identity, DNS, and secrets integration.
- Operating skills across multiple control planes and on-call coverage.
- Migration, testing, compliance, and exit/egress when switching providers.

### 12.2. Total Cost of Ownership

Do not compare VM or database prices alone. TCO should include compute, storage, networking, managed services, software licenses, support, operations, security, compliance, migration, and DR.

Measure using:

\[
\text{Cost per business transaction} =
\frac{\text{Total hybrid/multi-cloud cost}}
{\text{Successful business transactions}}
\]

Allocate shared costs using consistent rules. Compare equal workloads, SLOs, retention, security, and availability assumptions.

### 12.3. Data Transfer Amplification

A small payload can trigger multiple queries, log/trace exports, retries, CDC events, and replica updates. Measure actual bytes by source/destination/workload. Caching or batching can reduce transfers, but requires freshness and consistency policies.

## 13. Operating Model for Multiple Environments

### 13.1. Platform Ownership

Identify the teams responsible for:

- Landing zones/accounts/subscriptions and network hubs.
- Identity federation and secrets/key management.
- Connectivity, DNS, and firewalls.
- IaC modules, pipelines, and policies.
- Observability, incident response, and cost allocation.
- Data governance, backups, and recovery.

### 13.2. Golden Paths

Create pre-vetted deployment templates for new workloads: networking patterns, identity, logging, metrics, tracing, deployment, quotas, backups, and tagging. Product teams select from supported patterns instead of reinventing every provider integration.

### 13.3. Cross-Environment Incident Command

Runbooks must specify who can:

- Check provider status and open support cases.
- Reroute traffic or disable integrations.
- Revoke credentials/certificates.
- Fail over data/compute.
- Replay events and reconcile state.
- Notify the business/customers.

Cross-cloud incidents can span multiple support organizations and time zones; prepare correlation IDs, evidence bundles, and escalation contacts in advance.

## 14. Migration and Placement Changes

### 14.1. Migration Patterns

| Pattern | Description | Key risks |
|---|---|---|
| Rehost | Move nearly as-is | Retains technical debt and network dependencies |
| Replatform | Swap parts of the runtime/managed services | Compatibility and behavior changes |
| Refactor | Split workloads by domain/API/events | Data ownership and distributed complexity |
| Repurchase | Move to SaaS | Integration, data export/exit, and contracts |
| Retain | Keep workload in place | Ongoing legacy operations |
| Retire | Decommission unneeded workloads | Hidden dependencies and unclear owners |

### 14.2. Migration Waves

Group workloads by dependencies and data boundaries. Move loosely coupled components first, followed by adapters/integrations and workloads handling critical transactions. Do not organize waves solely by department if systems share databases or transactions.

### 14.3. Cutover and Rollback

- Synchronize data prior to cutover.
- Define freeze/write ownership.
- Use planned DNS/routing or feature flags.
- Compare record counts, checksums, and business invariants.
- Monitor errors, latency, and replication lag.
- Establish a rollback window and clear trigger criteria.
- Avoid letting two environments accept writes without a conflict policy.

### 14.4. Strangler Pattern

Place a façade/API gateway in front of the legacy system and migrate capabilities incrementally to new workloads. The façade routes by domain/operation while data and events transition gradually. Avoid turning the proxy into a bottleneck or a dumping ground for new business logic.

## 15. Placement Decision Matrix

Score each workload against criteria while enforcing hard constraints before scoring:

| Criterion | Question | Example weight |
|---|---|---:|
| Dependency locality | How many critical dependencies reside in the same environment? | 20% |
| Data locality/gravity | Data size, write ownership, and transfer cost? | 20% |
| Latency | Does the critical path meet p95/p99 targets? | 20% |
| Compliance/security | Are residency, identity, and controls satisfied? | Hard gate |
| Reliability | Failure modes, RTO/RPO, and provider dependencies? | 15% |
| Cost | Compute, egress, operations, and support? | 15% |
| Operability | Does the team have skills, tooling, and on-call readiness? | 10% |

Weights are illustrative only. If residency or security is a hard requirement, high cost/performance scores cannot compensate for it. Options failing hard gates must be eliminated before comparing total scores.

### 15.1. Example Placement for BookingCloud

| Workload | Proposed placement | Rationale |
|---|---|---|
| Public API/frontend | Public cloud region near users | Scaling, ingress, and managed compute |
| Booking service | Same region as authoritative booking DB | Transaction latency/consistency |
| Legacy inventory ERP | On-premises/private environment | Data ownership and legacy dependencies |
| Inventory adapter | Near ERP, exposing secured APIs/events | Avoids multiple round trips over hybrid links |
| Notification worker | Cloud region | Can process asynchronously, scales independently |
| Analytics pipeline | Cloud near data lake/warehouse | Compute close to large datasets |
| Audit store | Location approved by security/data policy | Retention, integrity, and residency |
| DR workload | Separate region per RTO/RPO | Failure-domain separation |

This is a reference layout. Actual placement requires measuring hybrid links, database latency, data residency, provider quotas, and costs.

## 16. Well-Architected Assessment

| Perspective | Review questions | Required evidence |
|---|---|---|
| **Operational Excellence** | Who owns each environment, network, identity, and incident handoff? | Dependency map, golden paths, runbooks, service catalog |
| **Security** | Are identity, encryption, egress, data residency, and auditing consistent? | Trust model, access reviews, data-flow maps, policy tests |
| **Reliability** | If a link/provider/region fails, which operations continue and how does failover work? | RTO/RPO, store-and-forward, restore/failover exercises |
| **Performance Efficiency** | Does the critical path have many cross-environment hops? Is compute near data? | p95/p99, traces, replication lag, data transfers |
| **Cost Optimization** | Are egress, duplicate data, and operational overhead justified? | TCO, cost per transaction, network bills, utilization |
| **Sustainability** | Are there redundant copies, compute, or network traffic? | Data lifecycles, idle resources, transfer efficiency |

There is no single optimal placement for all workloads. Sound boundaries follow capability and ownership: keep transactions with authoritative data; place batch/analytics near large datasets; use events for deferrable dependencies; and expand to additional providers/regions only when benefits are measured and operable.

## 17. Lab Exercise: Partition Workloads for BookingCloud

BookingCloud has an inventory ERP running in a data center, a booking API on public cloud, analytics in a data warehouse, an external payment provider, and users across multiple markets. Some booking requests slow down when the ERP is busy; catalog data is heavily read; the team wants to place additional workloads on a second provider.

Complete the following:

**Task 1 — Workload inventory:** decompose capabilities into API, booking, inventory, payment, notification, analytics, identity, and audit; record owners and SLOs.

**Task 2 — Dependency map:** classify hard/soft and synchronous/event-driven dependencies, and identify the critical path.

**Task 3 — Data ownership:** determine the source of truth for booking, inventory, catalog, and analytics; specify which data is replicated.

**Task 4 — Placement matrix:** compare on-prem, private cloud, Provider A, Provider B, and edge across dependencies, data, latency, residency, reliability, cost, and operability.

**Task 5 — Integration:** design an adapter near the ERP, private connectivity, identity federation, mTLS, DNS, and event buffering.

**Task 6 — Consistency:** handle inventory holds, replica lag, duplicate events, and response timeouts.

**Task 7 — Resilience:** describe degraded modes when the hybrid link/provider fails; calculate RTO/RPO and failover behavior.

**Task 8 — Cost:** calculate egress, replication, duplicate storage, connectivity, observability, and support costs.

**Task 9 — Migration:** plan waves, cutover, validation, rollback, and post-migration ownership.

### Self-Check Framework

| Decision | Must prove |
|---|---|
| Keep ERP on-prem | Specific data/dependency/latency or migration risk rationale |
| Place adapter near ERP | Reduces round trips and buffers during link outages |
| Booking service near database | Transaction path meets latency/consistency targets |
| Replicate catalog | Defined freshness, invalidation, and ownership |
| Use events for notifications | Idempotent consumers, bounded retries/DLQ, and safe replay |
| Add a second provider | Capability and exit/resilience benefits outweigh complexity/TCO |
| Hybrid failover | Working credentials, quotas, routes, data, and runbooks |

## 18. Pre-Finalization Workload Placement Checklist

- [ ] Every workload has an owner, business criticality, SLO, and profile.
- [ ] Dependency graph distinguishes hard/soft and synchronous/asynchronous dependencies.
- [ ] Critical path and network round-trip counts are measured.
- [ ] Sources of truth and data ownership are defined.
- [ ] Data gravity, replication, freshness, conflicts, and deletion are designed.
- [ ] Region/provider/on-prem placement meets latency and residency requirements.
- [ ] Network connectivity, routing, DNS, segmentation, and egress have owners.
- [ ] Workload identity, mTLS, secrets, and authorization are designed across environments.
- [ ] RTO/RPO, degraded modes, failover, and restores have been tested.
- [ ] Quotas/capacity and provider API limits cover steady, peak, and failover loads.
- [ ] Egress, replication, connectivity, licenses, support, and operations are included in TCO.
- [ ] Cross-cloud/on-prem observability correlation is verified.
- [ ] Migration waves, cutover, rollback, and reconciliation plans exist.
- [ ] Incident runbooks, support contacts, and ownership are clearly defined.

Partitioning workloads by dependencies, data, and latency aligns where each capability runs with its true nature. Keep transactions near authoritative data, move compute to large datasets where sensible, convert non-critical dependencies to events, and expand across multiple clouds only when benefits are proven. A sound hybrid/multi-cloud architecture must keep operating when networks, providers, or an environment fail, while keeping consistency, security, residency, performance, and total cost within committed bounds.
