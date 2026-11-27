# Data Sovereignty, Residency, and Cross-Border Data Transfers

## 1. Why Is Data Location an Architectural Decision?

Cloud applications often distribute compute and storage across multiple regions to reduce latency, improve resilience, and scale. However, a single customer's data can traverse many places: collected in one country, processed in another region, backed up to a third region, displayed on a support team's dashboard in another country, and accessed by a provider or subcontractor during operations.

Therefore, asking “which region is the database in?” is not enough to determine whether data is properly governed. You must understand the entire lifecycle and path of the data, including primaries, replicas, snapshots, backups, logs, telemetry, caches, file exports, derived data, and administrative access.

Three commonly used concepts:

- **Data residency:** where data is geographically stored or where infrastructure is located.
- **Data sovereignty:** which country/territory's laws, jurisdiction, or control govern the data under legal and contractual contexts.
- **Data localization:** a requirement or policy mandating that certain types of data be stored, processed, or have copies maintained within a defined territory.

These concepts are related but not synonymous. A database located in country A may still be subject to different legal requirements if the organization, data subject, processing activity, or provider falls under another jurisdiction. Conversely, a requirement to store data in one country does not necessarily prohibit all forms of remote access or cross-border transfers; the scope depends on the specific regulations and context.

In the **CLOUD_ARCHITECTURE** module, decisions regarding data sovereignty and location must be translated into concrete architecture: region placement, replication, backups, network paths, identity, key management, telemetry, support access, and provider contracts. The goal is to meet business and legal requirements with controllable reliability, security, performance, cost, and operations according to Well-Architected thinking.

After this lesson, you will be able to:

- Distinguish between sovereignty, residency, localization, and cross-border transfer.
- Identify which data is subject to restrictions and at which stages it may be transferred.
- Map data flows from collection through backup, support, and deletion.
- Design regional placement, replication, backups, logging, and key controls.
- Evaluate remote access, providers, and subprocessors.
- Collaborate with legal, privacy, security, and procurement to verify data transfer conditions.
- Turn data location requirements into guardrails, policy-as-code, and audit evidence.

## 2. Distinguishing Residency, Sovereignty, and Localization

| Concept | Focus | Questions to Answer |
| --- | --- | --- |
| Data residency | Where data is stored or processed | Which country/region are databases, backups, logs, and replicas in? |
| Data sovereignty | Jurisdiction and control rights | Which laws/authorities may apply to the data, organization, and provider? |
| Data localization | Obligation to keep data within a territory | Which data types must be stored, processed, or kept as domestic copies? |
| Cross-border transfer | Transmission/access of data across borders | Does data or access cross from one jurisdiction to another? |

For example, an organization might store its primary database in Vietnam but use a support team in another country to view error records containing customer information. Even though the primary data bytes are not copied onto the support team's servers, remote access may still create transfer/access implications under applicable regulations and contracts. You must evaluate precisely with legal and privacy teams, rather than concluding based solely on disk location.

### 2.1. Defining Data Scope

Not all data carries the same requirements:

- Personal data and sensitive data.
- Financial, payment, or transaction data.
- Health data, biometric data, or special-category data.
- Enterprise customer records, trade secrets, and intellectual property.
- Government agency data or data under public-sector contracts.
- Metadata, identifiers, logs, and derived data linkable to individuals/organizations.
- Public data, aggregated data, and data assessed as non-identifiable.

Classification needs to consider fields and linkability. A log containing IP addresses, account IDs, timestamps, and URLs can contain sensitive data even without names or street addresses.

### 2.2. Distinguishing Storage, Processing, and Access Locations

For each dataset, establish at least three perspectives:

1. **At rest:** where are primaries, replicas, snapshots, backups, caches, and file exports stored?
2. **In transit/in process:** through which regions, services, networks, or runtimes is data transmitted and processed?
3. **Access location:** from which countries can users, administrators, support engineers, subprocessors, or automation access it?

Some requirements pertain only to storage; some regulations may apply to processing, disclosure, or access. The architecture team needs to translate policy/legal wording into concrete constraints across these three perspectives.

## 3. Data Flow Mapping: Knowing Where Data Goes

Before choosing regions or enabling replication, build a data map. Without a data flow inventory, you cannot prove a dataset truly remains within allowed boundaries.

### 3.1. Typical Data Flow Model

~~~mermaid
flowchart LR
    User["User / device"] --> Edge["CDN / WAF / API edge"]
    Edge --> App["Application region A"]
    App --> DB["Database region A"]
    DB --> Replica["Replica region B"]
    DB --> Backup["Backup region C"]
    App --> Logs["Logs / traces / metrics"]
    Logs --> Observability["Observability platform"]
    DB --> Lake["Data lake / warehouse"]
    Support["Support / operator"] -. "Remote access" .-> App
    Vendor["Cloud provider / subprocessor"] -. "Operational access" .-> DB
~~~

This diagram is illustrative only. An actual map must specify protocol, identity, purpose, data class, region, retention, encryption, and owner at each flow.

### 3.2. Data Flow Register

| Component/Flow | Data | Origin / Destination | Governance Questions |
| --- | --- | --- | --- |
| Client → API | Profile, identifier, request payload | User country → ingress region | Is collection excessive? Do TLS and edge logs store bodies? |
| API → Database | Transactions and profiles | Application region → DB region | Is primary placement appropriate? |
| Database → Replica | WAL/change stream or records | Region A → Region B | Is replication allowed? Sync or async? |
| Database → Backup | Snapshots/log archives | Region A → another bucket/vault | Where are backup location, retention, and keys? |
| App → Observability | Logs, traces, metrics, crash dumps | Runtime → telemetry service | Any PII/secrets? Which region processes telemetry? |
| Data lake → BI | Curated/aggregate data | Data zone → warehouse/BI region | Are masking and purpose controls applied? |
| Support → Production | Queries, sessions, or screen shares | Staff in another country | Is remote access permitted, audited, and restricted? |
| Provider/subprocessor | Metadata or customer content | Cloud/service provider | DPA, subprocessor list, support locations, and transfer terms? |

### 3.3. Commonly Overlooked Copies

- Read replicas, cross-region replicas, and disaster recovery copies.
- Snapshots, point-in-time recovery logs, backup catalogs, and exports.
- Caches, CDN origins/shields, search indexes, and materialized views.
- Application logs, trace spans, crash dumps, analytics events, and alert payloads.
- Notebook local storage, query result caches, temporary spill files, and developer exports.
- Support tickets, email threads, chat attachments, and screen recordings.
- Test/staging environments and synthetic datasets generated from production.
- Subprocessors, managed support, security monitoring, and anti-fraud services.

A “temporary” copy can still contain data and create protection obligations. The inventory must also record transient data if it crosses a boundary or is retained for a meaningful period.

### 3.4. Attributes to Record for Each Flow

Each flow should capture source, destination, data subject/owner, fields/classification, purpose, protocol, direction, location/jurisdiction, identity, encryption, retention, downstream copies, transfer basis/approval reference, and evidence. If a destination or support access path is unclear, treat it as a gap to close before deploying restricted data.

## 4. Evaluating Legal and Contractual Requirements Before Designing

Cloud architects should not unilaterally interpret a legal clause as “allowed” or “prohibited” without sufficient context. Architecture's role is to provide accurate technical facts for legal/privacy/security to evaluate, then translate approved conclusions into verifiable configurations and controls.

### 4.1. Sources of Requirements

- Regulations in the country where the organization is incorporated, operates, or provides services.
- Regulations where data subjects reside or where data is collected/processed.
- Industry regulations such as finance, healthcare, telecommunications, or public sector.
- Customer contracts, data processing agreements (DPAs), confidentiality terms, and security addenda.
- Internal policies on data classification, retention, acceptable use, and access.
- Audit/certification requirements to which the organization has committed.
- Terms of cloud providers, managed services, and subprocessors.

A single dataset may be subject to multiple requirement sources simultaneously. Do not rely solely on the cloud region's country to conclude which laws apply.

### 4.2. Assessment Process

1. Identify the data controller/processor/owner and data recipients by role in the specific context.
2. Classify data, subjects, purpose, volume, sensitivity, and identifiability.
3. Build a data flow map covering storage, processing, remote access, backups, and downstream flows.
4. List jurisdictions of sources, destinations, the organization, providers, and support personnel.
5. Cross-check regulations, DPAs, transfer terms, localization, and retention with legal/privacy.
6. Identify authorization conditions, supplementary measures, notices/consents, or restrictions.
7. Document decisions, owners, timeframes, data scope, and approval evidence.
8. Translate decisions into architecture requirements, policy-as-code, and tests.
9. Re-evaluate when changing providers, regions, subprocessors, data purposes, or data types.

### 4.3. Regulatory Requirements Matrix

| Question | Example Evidence to Collect | Architectural Output |
| --- | --- | --- |
| Which datasets are regulated? | Data inventory, schema, classification | Scope tags and zone placement |
| Are there localization requirements? | Legal/contractual clauses confirmed by legal | Allowed region list, deny cross-border replication |
| Under what conditions can data transfer abroad? | Corresponding transfer mechanism/assessment/contract approval | Approved flows and transfer gates |
| Who can access remotely? | Provider support terms, staff locations, access logs | JIT access, support approval, customer-managed controls |
| What are retention and deletion rules? | Records schedule, legal hold, privacy policy | Lifecycle, immutable retention, and deletion workflow |
| Are there incident notification duties? | Incident clauses/regulatory duties | Data location inventory, notification runbook |
| Are subprocessors permitted? | DPA, list, change notifications, and objection rights if applicable | Vendor allowlist and subprocessor register |

Do not hardcode legal interpretations into a fixed configuration if requirements still depend on facts. Store references to the legal decision and accountable person rather than turning technical observations into legal advice.

## 5. Jurisdiction-Based Placement Architecture

Once you know where data is allowed to be stored/processed, architects can define a placement strategy by data class and tenant.

### 5.1. Single-Region Data Boundary

For strictly restricted datasets, an organization can place primary, replica, backup, and processing within a single region or approved geographic boundary. This simplifies data residency but may reduce DR options, increase latency for distant users, and require a plan to protect data within that same boundary.

Do not assume a single region means zero transfers. Provider support, global control planes, telemetry, and administrative access still need evaluation.

### 5.2. Regional Cells / Data Partitioning by Jurisdiction

A common pattern is deploying independent cells per jurisdiction. Requests are routed to the corresponding cell; data stores, encryption keys, backups, and operational access are restricted by policy.

~~~mermaid
flowchart TB
    Global["Global entry / DNS / WAF"] --> Router["Tenant and jurisdiction router"]
    Router --> CellA["Regional cell A"]
    Router --> CellB["Regional cell B"]
    subgraph A["Jurisdiction A boundary"]
        CellA --> AppA["Application A"]
        AppA --> DBA[("Database A")]
        AppA --> ObjA["Object storage A"]
        DBA --> BkpA["Backup A"]
    end
    subgraph B["Jurisdiction B boundary"]
        CellB --> AppB["Application B"]
        AppB --> DBB[("Database B")]
        AppB --> ObjB["Object storage B"]
        DBB --> BkpB["Backup B"]
    end
~~~

The cell model reduces the risk of data mixing across tenants/jurisdictions and limits blast radius. In return, it duplicates infrastructure, deployments, monitoring, and support, and can complicate global analytics.

### 5.3. Shared Control Plane, Regional Data Plane

Some platforms use a global control plane to manage deployments, policies, or metadata, while the data plane processes data regionally. Evaluate whether the control plane stores tenant names, query metadata, resource identifiers, IPs, logs, or secrets, and what data is visible to global operations staff.

If metadata is also sensitive, limit fields, pseudonymize, segregate tenant identifiers, and apply retention. Do not label a control plane as “containing no customer data” if it stores linkable logs or metadata.

### 5.4. Global Services and Regional Restrictions

A globally shared service may receive only minimized or aggregated data. Raw data remains restricted to regional cells; aggregates are exported only after privacy review, group-size thresholds, and purpose approval. This separates global analytics from regional identifiable records, though it does not automatically eliminate re-identification risk.

## 6. Replication, Backups, and Disaster Recovery Under Location Constraints

Multi-region DR can conflict with localization requirements. Designing full-copy replication to a standby region is only valid when the dataset is permitted to go there and transfer conditions are approved.

### 6.1. Classifying Data by Replication Policy

| Data Type | Selectable Replication | Conditions to Verify |
| --- | --- | --- |
| Restricted/localized | Replicas within allowed boundary | Whether AZs/regions provide sufficient resilience and clear policies |
| Transfer-permitted confidential | Controlled cross-region | Transfer approval, encryption, access, and retention |
| Public | Broad replication/CDN per purpose | Integrity, cache invalidation, and authoritative source |
| Pseudonymized/aggregated | Transferable per assessment | Re-identification risk and whether mapping keys are separated |
| Backups/logs | Separate policy, not defaulting to primary | Backup location, support access, retention, and immutable copies |

### 6.2. DR Within the Same Jurisdiction

If data must remain within one country, multiple AZs or multiple domestic regions can be used if offered by the provider and approved by legal/security. If only one eligible region exists, consider offline/immutable backups, cross-account vaults within the same boundary, restore tests, spare capacity, and recovery from logical errors.

Do not sacrifice recoverability without business risk acceptance. If localization makes RTO/RPO hard to meet, document the gap, alternatives, and approver.

### 6.3. Backups and Archives

Backups can contain full original data, including fields masked in curated datasets. Dedicated policies are needed for:

- Storage locations and key locations.
- Encryption, immutability, and restore/delete permissions.
- Retention, legal holds, and expiration.
- Catalog copies, metadata, log archives, and database WALs.
- Access by provider support/managed backup services.
- Handling deletion requests for backups still within retention.

A snapshot in another region is still data copied across borders if it contains restricted-scope data.

### 6.4. Crypto-Erasure and Key Boundaries

Customer-managed keys or regional KMS keys can help control decryption permissions within a boundary. However, placing a key in a domestic region does not by itself prove data residency, and deleting a key does not guarantee deletion of plaintext exports/caches. You must map encryption contexts, key usage, replicas, backups, and operator permissions.

## 7. Cross-Border Transfers and Remote Access

Cross-border data transfers can happen through many mechanisms: object/database copies, replication, API calls, telemetry exports, support sessions, or direct access by overseas staff. Transfer scope and valid conditions must be determined by legal/privacy based on data, subjects, destinations, and applicable regulations.

### 7.1. Classifying Transfer Flow Types

| Mode | Example | Architectural Controls |
| --- | --- | --- |
| Bulk transfer | Database export, bucket copy, migration | Approval, encryption, checksums, transfer logs, destination controls |
| Continuous replication | Database replica, object replication, event stream | Region allowlist, scope filters, lag monitoring, key separation |
| API/service-to-service | Sending profiles or transactions to a processor | Purpose, schema minimization, TLS, service identity, recipient contract |
| Remote interactive access | Support engineer opens console or runs queries | JIT access, MFA, approval, session recording/auditing, and masking |
| Telemetry transfer | Logs, traces, crash dumps sent to global observability | Scrubbing, field allowlists, regional collectors, retention |
| Derived data | Aggregates, pseudonymous features, or reports | Re-identification assessment, query controls, and purpose limitation |

It is not only permanently stored data that requires assessment. Payloads sent over APIs, support screens, logs, or query results can also expose information.

### 7.2. Transfer Assessments and Safeguards

Depending on the applicable legal framework and contracts, transfers may require a legal mechanism, impact assessment, contractual clauses, notice/consent, supplementary technical measures, or other conditions. Architects need to:

1. Identify the exporter, importer, data subjects, dataset, and purpose.
2. Identify the country/jurisdiction of each party and service endpoint.
3. Cross-check the transfer mechanism approved by legal/privacy for the scenario.
4. Describe accessible data, duration, subprocessors, and onward transfers.
5. Select safeguards such as encryption, pseudonymization, minimization, access restrictions, logging, and key controls.
6. Record assessment evidence, approvals, contracts, and review dates.
7. Test that technical controls enforce the exact approved scope.

Encryption or pseudonymization can reduce risk, but they do not by themselves establish a legal basis for transfer. Do not use a generic technical checklist to replace a legal assessment.

### 7.3. Remote Access Is Also a Data Flow

Support engineers can read data via queries, consoles, screen sharing, or remote desktops. Determine:

- Where personnel access from and whether they belong to a provider/subprocessor.
- Whether they can view raw values, query results, exports, or downloads.
- Whether session contents are recorded in tickets, logs, or recordings in another region.
- Whether role-based masking and temporary per-incident permissions can be enforced.
- Who approves, who monitors, and where evidence is retained.

Common control patterns include just-in-time (JIT) access, MFA, ticket/incident references, time-bound roles, command/session auditing, field masking, and break-glass approvals. Emergency support paths must be tested before a disaster; if the approval workflow is unavailable during an incident, a controlled and audited break-glass path is required.

### 7.4. Telemetry, Logs, and Traces

Logs often unintentionally capture:

- URL query strings, headers, cookies, and authorization tokens.
- Emails, phone numbers, account IDs, IPs, and device identifiers.
- Request/response bodies or stack traces containing customer data.
- Database query literals, SQL parameters, and object keys.
- Screenshots, crash dumps, memory dumps, and trace baggage.

Design telemetry around field allowlists and schemas rather than relying on “developers remembering not to log PII.” Redact at the source, use correlation IDs without direct identifiers, partition collectors by jurisdiction, limit sampling/exports, and run tests detecting secrets/PII. For traces, avoid stuffing payloads into span attributes.

## 8. Cloud Provider and Subprocessor Governance

A cloud provider may offer many regions, yet not every service, support feature, control plane, billing system, abuse monitoring, or backup option has the same data-location capabilities. Evaluate per service and contract, rather than inferring from VM/database regions.

### 8.1. Vendor Due Diligence

| Topic | Questions to Clarify |
| --- | --- |
| Region availability | Is the specific service available in allowed regions? Are there feature limitations? |
| Data location | Where do primaries, replicas, metadata, backups, logs, and support data reside? |
| Administrative access | Where can provider/subprocessor staff access from? Under what conditions? |
| Subprocessors | List, countries, services, change notifications, and onward transfers? |
| Encryption/keys | Provider-managed or customer-managed keys? Under what situations can provider support decrypt? |
| Deletion/retention | When are data and backups deleted? Are there exceptions or legal holds? |
| Incidents | Notification timelines and channels, evidence, cooperation, and audit rights? |
| Portability | Can data/metadata be exported and migrated to another provider upon termination? |
| Assurance | Are audit reports/certifications aligned with scope and timeframe? |

Provider certifications or audit reports are supporting evidence; they do not automatically prove a customer's specific architecture meets all obligations. Cross-check service scope, shared responsibility, and actual configuration.

### 8.2. Shared Responsibility

The provider may secure physical infrastructure and portions of the service; the customer remains responsible for configuring regions, IAM, data classification, access, keys, retention, exports, and applications. With managed services, operational duties may differ from self-managed setups, but responsibility for purpose, datasets, and recipients does not disappear.

Build a matrix:

| Control | Provider | Customer |
| --- | --- | --- |
| Physical facility | Designs and operates per service | Evaluates assurance and selects region |
| Region/replica configuration | Provides capabilities and constraints | Selects location, enables/disables replication |
| IAM/data access | Provides mechanisms | Designs roles, policies, and permission reviews |
| Encryption | Provides encryption/KMS options | Chooses key model, scope, and lifecycle |
| Retention/deletion | Executes per feature/contract | Sets policy, verifies copies and workflows |
| Support access | Provider staffing and operational policies | Selects support plan, approvals, and data provided |
| Incident response | Notifies and assists per contract | Coordinates customer impact, assessments, and reporting duties |

The actual matrix must be completed for each service, contract, and shared responsibility model.

### 8.3. Subprocessor Change Management

A provider may change subprocessors, support locations, or telemetry paths over time. You should:

- Track change notifications and objection deadlines.
- Re-evaluate transfers/data flows when a new subprocessor is added.
- Update vendor registers, DPAs, and architecture decisions.
- Review rights to object or terminate under contractual terms.
- Maintain a migration/exit plan if changes invalidate acceptance conditions.

## 9. Policy-as-Code and Guardrails for Data Location

Residency requirements are only trustworthy when enforced at resource creation and during runtime operations. Policy documents should be translated into automated rules, always paired with owners and an exception process.

### 9.1. Region Allowlist

Example policy logic:

~~~text
IF dataset.classification == "restricted"
THEN
  allowed_regions = approved_regions_for(dataset.jurisdiction)
  deny_replication_to_any_unapproved_region
  require_customer_managed_key_if_policy_demands
  require_backup_location_in_approved_boundary
  require_access_role_with_matching_jurisdiction
END
~~~

This is illustrative pseudo-policy, not a specific cloud provider's syntax. When implementing, map it to the corresponding cloud organization policies, IaC validations, admission controllers, resource policies, and runtime monitoring.

### 9.2. Enforcement Layers

- **Preventive:** block creation of buckets/databases/networks/resources in disallowed regions.
- **Detective:** scan resources, replicas, backups, and IAM to detect drift.
- **Corrective:** automatically quarantine or open tickets; only auto-delete or move data when actions are safe and approved.
- **Evidence:** record policy version, decision, resource, principal, timestamp, and exceptions.

Do not rely solely on developer-declared tags. Combine identity, account/project boundaries, dataset metadata, destinations, and runtime checks.

### 9.3. Infrastructure as Code

IaC can declare regions, encryption keys, backup vaults, replication destinations, logging endpoints, and access policies. Pipelines should verify:

1. Region is in the dataset's allowlist.
2. No replication/export to unapproved destinations.
3. Encryption and key policies match classification.
4. Logging/telemetry does not emit raw payloads outside the boundary.
5. Backup lifecycles and retention are appropriate.
6. Support roles have time limits and scope.

Config drift can occur via console/manual changes or services created outside the pipeline. Periodic scans and a drift-handling process are required.

### 9.4. Exception Management

If an exception is needed, require business justification, dataset/scope, destination, duration, compensating controls, risk owner, legal/security approval, and an expiration date. Exceptions expire automatically and are reviewed; never use wildcard regions or open-ended exceptions to bypass guardrails.

## 10. Retention, Deletion, and Cross-Border Data Subject Requests

Data sovereignty involves not only where data is stored, but how it is retained, copied, provided, and deleted. A deletion or processing-restriction request can affect multiple regions, backups, processors, and derived datasets.

### 10.1. Retention Register

Each dataset should specify:

- Purpose and business owner.
- Classification and jurisdiction.
- Retention duration/trigger, policy source, and review date.
- Active legal holds or exceptions.
- Primary/replica/backup/archive locations.
- Deletion method and downstream notifications.
- Owner responsible for confirming expiration.

Retention for databases, event logs, object versions, snapshots, backups, and telemetry may differ. Do not apply a single global TTL across all copies when requirements differ.

### 10.2. Deletion Propagation

~~~mermaid
flowchart TB
    Request["Verified request / retention expiry"] --> Policy["Policy and legal hold check"]
    Policy --> Inventory["Lineage + location inventory"]
    Inventory --> Primary["Primary data"]
    Inventory --> Replica["Replicas / secondary regions"]
    Inventory --> Derived["Warehouse / index / feature"]
    Inventory --> Export["Exports / processors / cache"]
    Inventory --> Backup["Backup / archive schedule"]
    Primary --> Verify["Verification and evidence"]
    Replica --> Verify
    Derived --> Verify
    Export --> Verify
    Backup --> Verify
~~~

Workflows should distinguish accepted, in progress, completed, exception/held, and failed states. Do not report deletion as complete if immutable backups are still retained under retention policy. When an old backup is restored, apply a deletion ledger or tombstone before returning the dataset to service.

### 10.3. Data Portability and Exit Plan

The ability to move data off a provider is part of governance. Define:

- Export formats, schemas, metadata, key mappings, and lineage.
- Whether the transfer destination is permitted to receive the dataset.
- Egress costs, bandwidth, duration, and API limits.
- Encryption in transit, integrity/checksums, and chain of custody.
- How to transfer keys/secrets safely or re-encrypt at the destination.
- How to stop replication, revoke identities, and delete copies at the old provider.
- Evidence of deletion/termination, backup expiration, and subprocessor offboarding.

Exit plans should be tested at a representative level. A contract granting export rights without a practical procedure or key recovery still leads to operational lock-in.

## 11. Incident Response and Data Disclosure Requests

Data-related incidents can arise from unauthorized disclosure, credential compromise, accidental transfer to the wrong region, subprocessor changes, public buckets, or PII leaks in logs. Processes must coordinate security, legal/privacy, cloud operations, and business owners.

### 11.1. Detection and Containment

1. Identify affected datasets, fields, data subjects, tenants, and jurisdictions.
2. Determine where data was stored, accessed, downloaded, or onward-transferred.
3. Preserve audit logs, cloud trails, session records, and evidence with restricted access.
4. Revoke/restrict compromised credentials or transfer paths without destroying evidence.
5. Identify involved providers/subprocessors and trigger contractual incident channels.
6. Legal/privacy determines notification duties, timelines, and authorities/recipients under applicable rules.
7. Remediate policies, rotate keys/tokens, delete unauthorized copies, or isolate per approved plans.
8. Record timeline, impact, root cause, corrective actions, and effectiveness checks.

### 11.2. Data Requests from Authorities or Third Parties

Legal requests from government agencies, courts, or third parties must be handled through the organization's legal process and provider terms. Technical teams must never unilaterally hand over data based solely on an email or ticket.

Verify authenticity, authority, scope, jurisdiction, data types, deadlines, notification duties, and opportunities to challenge/narrow per procedure. Audit the recipient, disclosed data, approvals, and chain of custody. Providers may have their own procedures for notifying customers or handling direct demands; read the relevant contract/service terms carefully.

### 11.3. Evidence and Audit Readiness

You may need to prove:

- Which region resources were created in and who changed locations.
- Which destinations replicas, backups, logs, and telemetry use.
- Who holds access/export rights and actual access events.
- Which keys protect data, who used keys, and policies at that point in time.
- Which transfers were approved and for what purposes.
- How retention/deletion is enforced and which exceptions remain valid.
- Which providers/subprocessors are involved and which contracts apply.

Evidence should have an owner, timestamp, policy/version, and integrity protection. Avoid retaining sensitive payloads just to prove compliance.

## 12. Architectural Patterns by Data Restriction Level

No single model fits every organization. Choose patterns based on classification, residency, RTO/RPO, locality, analytics requirements, and operational capacity.

| Pattern | Characteristics | Pros | Trade-offs |
| --- | --- | --- | --- |
| Single jurisdiction deployment | Data plane, backups, and processing inside one boundary | Easy location control; few transfer flows | DR and capacity may be limited; global latency |
| Regional cells | Each jurisdiction has its own data cell | Isolation, local scaling, and independent policies | Duplicates operations; config sync is harder |
| Global control plane + regional data plane | Shared governance, data processed regionally | Platform standardization while keeping data locality | Metadata/control plane still requires assessment |
| Local raw + global aggregate | Raw data stays regional; only approved aggregates/features exported | Enables broad analytics while limiting raw transfers | Re-identification, metric consistency, and purpose need control |
| Federated query | Queries run near data, returning results to consumer | Can avoid copying raw datasets | Query results can still be sensitive; network and performance complexity |
| Clean room / controlled collaboration | Parties query/share under policies and constrained conditions | Reduces direct raw file exchange | Does not eliminate all risk; rules and participants must be governed |

### 12.1. Federated Query Does Not Mean Zero Transfer

A query engine may run close to the data source, yet results, counts, metadata, query plans, or error messages still travel back to the caller. Examine output granularity, small-cell suppression, query budgets, logs, and caching.

### 12.2. Regional Aggregates Require Thresholds and Purpose

If regional cells send aggregated revenue to a global warehouse, assess whether groups are too small or combinable with public data to infer an individual customer. Apply minimum group sizes, suppression, noise, or query limits per policy. Specific thresholds must be chosen based on risk assessment and purpose, not copied as a universal number for all datasets.

### 12.3. Do Not Route Blindly by IP

Geo-IP or DNS locality can help route to a nearby region, but they do not prove jurisdiction, residency, or tenant ownership. Traveling users, VPNs, proxies, and edge caches cause IP locations to differ from data jurisdictions. Route based on tenant/account policies or verified authoritative metadata; use network location only as a secondary signal.

## 13. Well-Architected: Trade-offs of Data Sovereignty and Location

| Perspective | Architectural Decision | Trade-offs |
| --- | --- | --- |
| **Operational Excellence** | Data flow register, owners, vendor register, policy-as-code, auditing, and exception workflows | Comprehensive governance requires disciplined metadata and continuous updates |
| **Security** | Regional boundaries, least privilege, encryption, JIT support, and telemetry scrubbing | Isolation increases safety but makes support/debugging more complex |
| **Reliability** | In-boundary DR, independent backups, restore tests, and regional cells | Localization may limit region choices and increase redundancy costs |
| **Performance Efficiency** | Local data processing, caching/aggregation, and federated queries | Reduces transfers but increases multi-region compute costs and orchestration |
| **Cost Optimization** | Tiering, minimizing data copies, selecting services by locality | Multi-cell setups, domestic backups, and egress restrictions can raise TCO |
| **Sustainability** | Data minimization, retention, and eliminating unnecessary replicas | Fewer copies shrink footprint, yet sufficient resilience and compliance must remain |

An architecture decision record should capture requirements, dataset scope, jurisdictions, allowed destinations, transfer mechanisms/approvals, support paths, backup/DR, costs, exceptions, and review dates. When providers add regions/services or the organization changes purposes, the ADR must be revisited.

## 14. Hands-on Exercise: Designing a Multi-Jurisdiction Cloud Platform

A company operates an e-commerce platform for customers in two countries. The application includes customer profiles, orders, payment references, catalogs, clickstreams, logs, and revenue dashboards. The primary database is in one region; the support team works from a second country; the analytics warehouse uses a global service; backups are replicated to a standby region. The organization is evaluating expansion into a new country with different data location requirements.

**Assignment Requirements:**

1. Classify each dataset and field; identify personal data, sensitive data, trade secrets, and linkable metadata.
2. Draw a data flow map including primary, replica, backup, logs, traces, caches, support access, warehouse, and subprocessors.
3. Build a source/destination/processing/access jurisdiction table for each flow.
4. Identify which questions must be escalated to legal/privacy to assess localization and transfers; do not assume one requirement applies to all data.
5. Propose a regional cell or single-boundary design for restricted datasets; explain what metadata the control plane and global services can observe.
6. Define replication/backup/DR strategies within approved boundaries; state impacts on RTO/RPO and cost.
7. Design remote support with JIT, MFA, field masking, approvals, and auditing; address emergency incident scenarios.
8. Propose telemetry schemas/allowlists to prevent logs and traces from sending sensitive data outside the boundary.
9. Build region allowlists, IaC validations, drift detection, and exception expiration.
10. Design retention/deletion/exit workflows for replicas, backups, analytics, and subprocessors.
11. Provide a vendor due diligence checklist and evidence to collect from the cloud provider.
12. Write an ADR comparing regional cells, global aggregates, and federated queries across governance, performance, reliability, and TCO.

### Evaluation Guidance

A strong submission clearly distinguishes data at rest, processing, and remote access. It checks not only the database region, but also backups, KMS, telemetry, support, and subprocessors. Every cross-border flow has a concrete destination, purpose, owner, approval, and safeguards.

The design should demonstrate how tenants are routed to the right cell, how replicas/backups are blocked from unapproved regions, and how drift is detected. Global analytics receives only assessed and minimized data; aggregates are not automatically treated as anonymous. Added RTO/RPO and cost impacts when constraining DR within a jurisdiction must be explicitly stated.

## 15. Checklist Before Deploying Cross-Border Data

- [ ] Data inventory, owner, classification, and purpose exist for each dataset.
- [ ] Residency, sovereignty, localization, and remote access/transfers are clearly distinguished.
- [ ] Data flow map covers primaries, replicas, backups, snapshots, caches, logs, traces, exports, and subprocessors.
- [ ] Locations of storage, processing, control plane, support, and key management are verified.
- [ ] Legal/privacy has confirmed applicable regulations, contracts, and transfer mechanisms for each flow.
- [ ] Data is minimized; raw/restricted fields do not enter unnecessary telemetry/analytics.
- [ ] Region placement and tenant routing rely on verified jurisdiction policies.
- [ ] Replica, backup, and DR destinations are in the allowlist or have corresponding approvals.
- [ ] IAM, JIT support, MFA, break-glass, auditing, and field masking are configured.
- [ ] TLS, encryption at rest, customer-managed keys, and key recovery are evaluated.
- [ ] Providers/subprocessors have due diligence, DPAs, location/support details, and change notifications.
- [ ] Control plane/global metadata does not expose data beyond permitted scope.
- [ ] Retention, legal holds, deletion propagation, and backup expiration have owners.
- [ ] Data export/portability and provider exit plans have been reviewed.
- [ ] Policy-as-code has preventive guardrails, drift detection, corrective workflows, and evidence.
- [ ] Exceptions have scope, compensating controls, approver, expiration, and periodic reviews.
- [ ] Incident/legal request processes, evidence preservation, and stakeholder communication exist.
- [ ] In-boundary DR meets approved RTO/RPO targets or has risk acceptance.
- [ ] Cross-border flows, denied regions, support access, deletion, and restores have been tested.
- [ ] ADRs and data flow registers have review dates when laws, providers, or purposes change.

**Key takeaway:** Data sovereignty cannot be proven by database location alone. You must know where data is stored, processed, copied, and accessed from; who has permissions; which providers/subprocessors are involved; and which purposes are permitted. Maintain a data flow register, have legal/privacy validate transfer conditions, and enforce them through regional placement, IAM, key controls, backup policies, telemetry scrubbing, and policy-as-code. Every exception and copy must have an owner, an expiration, and audit evidence.
