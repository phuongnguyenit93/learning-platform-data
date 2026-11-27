# Managing Sensitive Data and the Analytical Data Lifecycle

## 1. Why Must Analytical Data Be Governed Like Transactional Data?

A data platform typically aggregates information from many systems: orders, payments, user accounts, mobile apps, websites, CRMs, operational logs, devices, and partners. As data is copied into data lakes, warehouses, feature stores, notebooks, or test environments, the number of users with access and the number of copies proliferate rapidly. Data carefully protected inside a transactional application can end up in exported files, analytical tables, caches, backups, logs, or model training datasets.

**Sensitive data does not lose its sensitivity when moved to an analytics platform.** A table stripped of usernames can still identify individuals through unsalted hashed emails, phone numbers, fine-grained locations, timestamps, or combinations of multiple attributes. Even an aggregated dataset can leak information if groups are too small or if repeated queries allow inferring an individual.

Managing sensitive data must therefore span the entire lifecycle: collection, transmission, storage, transformation, analysis, sharing, backup, long-term archiving, and deletion. The goal is letting the right people and workloads use the right data for the required duration—while proving who accessed it and verifying that data was processed per policy.

In the **CLOUD_ARCHITECTURE** module, this is an architectural decision tied directly to security, reliability, scalability, cost, and operations. Good design balances analytical utility against privacy, retention requirements, availability, and auditability under Well-Architected principles.

After this lesson, you will be able to:

- Classify data by sensitivity tier, intended purpose, and owner.
- Design data minimization, masking, pseudonymization, tokenization, and encryption.
- Establish identity, access controls, row/column-level security, and auditing.
- Distinguish retention, archiving, legal holds, and deletion.
- Design the data lifecycle from ingestion through raw, curated, serving, and archive tiers.
- Track lineage, catalogs, quality, consent, and usage rights.
- Define lifecycle policies and test deletion/recovery across all copies.

## 2. Data Classification and Protection Tiers

You cannot govern effectively if the system does not know what data it holds. The first step is identifying datasets, fields, sources, owners, purposes, and sensitivity levels.

### 2.1. Example Classification Tiers

| Tier | Characteristics | Examples | Typical Controls Required |
| --- | --- | --- | --- |
| Public | Approved for broad public release | Public product catalogs, approved marketing materials | Integrity, change control, and authoritative source |
| Internal | Internal organizational use, not public | Internal reports, internal SKU codes | Corporate identity, least privilege, auditing |
| Confidential | Could cause harm if disclosed | Contract pricing, revenue figures, business plans | Group-based permissions, encryption, auditing, export restrictions |
| Restricted / Highly sensitive | High impact on individuals, finances, safety, or legal obligations | Credentials, personal identifiers, payment data, sensitive records | Specific purpose, narrow permissions, masking/tokenization, export controls, enhanced monitoring |

Tier names and enforcement must align with organizational policies and applicable regulations. Never assume a generic "PII" label implies identical protections across every country or industry.

### 2.2. Identifying Sensitive Data at the Field Level

A single table can contain fields across multiple sensitivity tiers:

| Field | Suggested Classification | Rationale |
| --- | --- | --- |
| `order_id` | Internal or Confidential | Transaction ID can link to other records |
| `customer_email` | Restricted/PII | Direct identifier and contact channel |
| `phone_number` | Restricted/PII | Direct identifier and contact channel |
| `shipping_address` | Restricted/PII | Location and personal information |
| `product_category` | Public/Internal | Typically low sensitivity when detached from customers |
| `order_total` | Confidential | Transaction value and purchasing behavior |
| `payment_token` | Restricted | May grant access to payment services or link accounts |
| `event_timestamp` | Context-dependent | Can reveal behavior and aid re-identification when combined |

Individual fields are not the only concern. Age, postal code, gender, and timestamp combined can form a rare fingerprint identifying an individual. Classification must evaluate linkability and access context.

### 2.3. Dataset Inventory

Every critical dataset should maintain minimum metadata:

- Dataset name, business description, schema, and storage location.
- Data owner, technical custodian, and steward.
- Collection source, purpose, legal/usage basis, and consumer groups.
- Classification, sensitive fields, tenant/jurisdiction, and consent/usage constraints where applicable.
- Retention, legal holds, backups, deletion method, and enforcement deadlines.
- Downstream consumers, exports, replicas, caches, and copies.
- Lineage, quality checks, access policies, and audit log locations.

Do not wait for a perfect catalog before protecting data. For datasets with unknown classification, quarantine them under restricted access until an owner confirms classification.

## 3. Data Minimization: Collect and Retain Only What Is Needed

The most effective risk reduction often starts before encryption: **do not collect or ingest attributes unnecessary for the stated purpose**.

### 3.1. Minimal Collection

For each field, ask:

1. Which feature or analysis actually requires this field?
2. Can a less sensitive attribute suffice?
3. Is full precision required, or do buckets/percentiles work?
4. Does the raw value need long-term storage, or only transient processing?
5. Can values be aggregated at the source so only summaries are transmitted?
6. Once the purpose ends, must the data be deleted or transitioned to another state?

For example, campaign reporting may only need province/city and month—not street addresses and second-level timestamps. Age analysis may need age brackets, not birth dates. Payment analytics may need a provider transaction reference, not full card details.

### 3.2. Separating Identifying Data from Analytical Data

A common pattern stores identifying attributes in a tightly restricted vault while analytical datasets use surrogate keys or tokens:

~~~mermaid
flowchart LR
    Source["Business sources"] --> Ingest["Ingestion + validation"]
    Ingest --> PII["Identity vault / restricted zone"]
    Ingest --> Transform["Minimize + tokenize"]
    PII --> Map[("Token mapping store")]
    Transform --> Lake["Analytics zone"]
    Lake --> Curated["Curated datasets"]
    Curated --> BI["BI / data science"]
    BI -->|Only with approved justification| Broker["Controlled re-identification service"]
    Broker --> PII
~~~

Analysts typically see only tokens, age brackets, or generalized regions. A separate service resolves tokens only when legitimately required—under explicit approval, auditing, and purpose limitation.

Zone separation alone does not guarantee security. Restrict join paths, credentials, networking, exports, and notebooks that might pull mappings outward.

### 3.3. Purpose Separation

Data collected to fulfill an order is not automatically authorized for unrelated purposes like advertising, profiling, or model training. Catalogs should store purpose/usage tags, and pipelines or access layers must enforce those limits. When purpose changes, reassess permissions, notice/consent where applicable, retention, and impacts on shared datasets.

## 4. Masking, Pseudonymization, Tokenization, and Anonymization

These techniques are not interchangeable. Choose based on required protection and downstream data utility.

| Technique | Mechanism | Can Identity Be Restored? | Best Suited For |
| --- | --- | --- | --- |
| Masking | Hides part of a value or replaces with fixed characters | Possible if original data remains elsewhere | Support UIs, demo environments |
| Pseudonymization | Replaces identifiers with stable pseudonyms/tokens | Yes, if mappings or linking keys exist | Analytics tracking the same entity without real names |
| Tokenization | Replaces sensitive values with tokens; mapping stored separately | Yes, via a protected token vault/service | Payment references, customer identities |
| Hashing | One-way algorithmic transformation | Not directly, though low-entropy inputs can be brute-forced | Integrity checks or controlled matching; requires salt/pepper per purpose |
| Generalization | Reduces granularity, e.g., dates to months or ages to brackets | Not directly, though combination risk remains | Statistical reporting and dashboards |
| Anonymization | Transforms data to eliminate reasonable identification in context | Intended to prevent re-identification by available means | Data sharing after formal re-identification risk review |

Pseudonymized data remains personal data whenever a re-linking path exists. Hashing emails does not automatically anonymize them: attackers can hash lists of common emails and compare. Partially masked phone numbers can still identify individuals when paired with country, name, or history.

### 4.1. Masking Example

~~~text
Original email:    linh.nguyen@example.test
Displayed email:   l***@example.test

Phone number:      +84 912 345 678
Displayed:         +84 ****** 678

Date of birth:     1994-08-17
Report:            age group 30-39
~~~

Display masking does not mean values are masked in storage. If analysts can query raw tables or export underlying files, UI-level masking is insufficient.

### 4.2. Purpose-Appropriate Hashing

Keyless hashing is suited for things like integrity checks, whereas password hashing requires slow, salted specialized algorithms like Argon2id, scrypt, or bcrypt. For pseudonymization, HMAC with a separately managed secret key resists dictionary attacks better than plain hashing on low-entropy inputs:

~~~text
subject_token = HMAC-SHA-256(secret_key, canonical_customer_id)
~~~

This formula is conceptual, not a DIY key management guide. Normalize inputs, isolate secrets by environment/purpose, version keys, and restrict token-minting privileges. If tokens must stay stable over time, key rotation requires a migration plan or versioned mappings.

### 4.3. Re-Identification Risk

A dataset with names stripped can still be re-identified when:

- Joined with public datasets or partner data.
- Groups are tiny or contain rare attributes.
- Timestamps, locations, and behavioral sequences form a unique fingerprint.
- A user runs repeated queries to infer hidden values.
- Stable tokens are reused across systems, increasing linkability.

Evaluating anonymization requires modeling adversaries, accessible auxiliary data, sharing scope, group sizes, and query capabilities. Techniques like k-anonymity, l-diversity, or differential privacy help certain statistical releases, but are not automatic certificates of safety.

## 5. Encryption and Key Management

Encryption protects data against unauthorized access at specific storage/transport layers, but it does not replace access control. Once an authorized application or analyst decrypts data, it is visible in plaintext in memory or query outputs.

### 5.1. Encryption Layers

| Data State | Control | Considerations |
| --- | --- | --- |
| In transit | TLS across sources, ingestion, storage, query engines, and clients | Verify certificates, hostnames, and protocol versions |
| At rest | Encryption on objects, disks, databases, warehouses, snapshots, and backups | Verify every copy and export |
| In use | Access restrictions, isolation, secure enclaves/confidential computing where required | Hard to apply broadly; carries performance/feature limits |
| Field-level | Encrypting specific sensitive columns or attributes | Complicates querying, indexing, joins, and key access |

Encryption at rest may use provider-managed keys by default or customer-managed keys (CMKs). Verify everything actually covered: object versions, replicas, logs, temporary spill files, snapshots, exports, and caches.

### 5.2. Key Management

- Use an approved KMS/HSM or key management service; never store master keys in the same bucket/database.
- Separate key-usage permissions from key-administration permissions. Analysts do not need permission to disable or rotate keys just to read a table.
- Design rotation, key versioning, re-encryption, and decryption of older data.
- Maintain backup/recovery procedures for key metadata and permissions in DR regions.
- Audit key creation, usage, rotation, disabling, and deletion.
- Alert prior to key expiration and test applications after rotation.

Customer-managed keys increase control while introducing an operational dependency. Accidentally disabling a key renders data inaccessible even when storage remains healthy.

### 5.3. Impact of Field-Level Encryption on Analytics

Encrypting emails or identifiers at the field level complicates equality lookups, joins, grouping, and search. Deterministic encryption permits equality checks but leaks repetition patterns; randomized encryption hides patterns better but blocks direct equality joins. Never invent custom cryptography; use vetted libraries/services and review threat models with security specialists.

## 6. Identity and Data Access Control

A data platform serves diverse roles: data engineers, analysts, data scientists, dashboard viewers, application services, pipeline service accounts, and administrators. Never grant sweeping permissions like "everyone on the project can read the whole lake."

### 6.1. Least Privilege and Separation of Duties

| Role | Permissions Typically Needed | Permissions to Restrict |
| --- | --- | --- |
| Ingestion service | Write to designated landing/raw paths | Reading all datasets or deleting backups |
| Data engineer | Read assigned sources, write curated outputs | Accessing PII unnecessary for transforms |
| Analyst | Read curated/aggregated datasets per business domain | Reading raw restricted data and mapping vaults |
| Data scientist | Access minimized or approved datasets | Exporting raw identifiers into notebooks |
| BI viewer | Query assigned semantic models/dashboards | Direct SQL against the raw zone |
| Security/audit | Read audit evidence and metadata for investigations | Altering business data |
| Platform admin | Administer infrastructure and policies per process | Routine consumption of business data |

Separating duties across dataset creators, access approvers, and key/backup operators reduces abuse risk. Privileged access should be time-bound and audited.

### 6.2. RBAC and ABAC

- **RBAC (Role-Based Access Control):** binds permissions to roles; straightforward to manage by job function and team.
- **ABAC (Attribute-Based Access Control):** bases decisions on attributes like classification, tenant, region, purpose, project, time, or device.

Architectures often combine both: an analyst's role grants access to curated data, while ABAC restricts queries to datasets matching their approved classification, tenant, and project.

### 6.3. Row-Level and Column-Level Security

Row-level security limits which records a user sees—for instance, each tenant sees only its own orders. Column-level security hides or masks sensitive fields—for instance, analysts see order totals and product categories without emails.

Illustrative logic:

~~~sql
-- Illustrative tenant isolation policy.
CREATE POLICY tenant_isolation
ON curated.orders
USING (tenant_id = current_setting('app.tenant_id'));
~~~

Exact syntax depends on the engine and how session context is set. Never trust a client-supplied session variable as proof of tenant identity; backend services must authenticate identity and tenant context, ensuring connection pools never leak context across requests.

Test row/column security with negative tests: confirm a Tenant A user cannot read Tenant B rows, and an analyst cannot extract restricted columns via views, exports, alternate query engines, or notebooks.

### 6.4. Data Sharing and Exports

Sharing data via views, clean rooms, APIs, or file exports requires contracts defining:

- Who the recipient is and permitted purposes.
- Which datasets/fields are shared, granularity, and retention.
- Whether joining with external datasets is allowed.
- Authentication, encryption, auditing, and revocation mechanisms.
- Accountability when recipients create downstream copies.

Never email attachments containing restricted data simply because provisioning direct access seems inconvenient. Use time-bounded sharing, watermarking/auditing, and export controls where supported.

## 7. Auditing, Monitoring, and Abuse Detection

Access policies define who *may* access data; audit logs record who *did* access it. Both are mandatory.

### 7.1. Events Worth Logging

- Logins, token issuance, role assumptions, and identity changes.
- Reads of sensitive tables, views, objects, columns, or files.
- Exports/downloads, snapshot creation, dataset shares, and signed URL issuance.
- Changes to IAM, ACLs, row/column policies, KMS keys, and retention rules.
- Dataset creation/deletion, schema changes, transform runs, and lineage updates.
- Anomalous access by volume, time of day, location, or query behavior.

Audit records should capture principal, action, resource, timestamp, source context, outcome, request/job ID, and policy decision context. Avoid logging raw payloads, secrets, or full query literals containing personal data unless required for investigation.

### 7.2. Protecting Audit Logs

Audit logs are themselves sensitive assets. You must:

- Write to an isolated zone separating append/write permissions from edit/delete permissions.
- Synchronize clocks and retain metadata needed for investigations.
- Enforce encryption, integrity protection, and policy-defined retention.
- Replicate or forward logs to an independent security/governance account where risk warrants.
- Alert on logging stoppages, sudden volume drops, or retention edits.

Never allow a single administrator to both manipulate business data and erase their own audit trail.

### 7.3. Detecting Anomalous Queries

An analyst who normally queries a few curated tables suddenly downloads tens of millions of restricted rows, scans multiple tenants, or runs exports at unusual hours. Alert on:

- Sudden spikes in query volume or bytes scanned.
- Repeated probing queries attempting to infer hidden values.
- Exports/downloads exceeding user, role, or dataset thresholds.
- Raw zone queries originating from unauthorized notebooks or projects.
- Off-hours access or unusual contexts per internal policy.

Combine alerts with business context to reduce false positives, supported by investigation runbooks, token revocation, audit preservation, and owner notification.

## 8. Consent, Purpose Limitation, and Usage Rights

Technical read permission does not grant carte blanche to use data for any purpose. Pipelines must track the purpose under which data was collected, consent/condition flags, and permitted downstream uses.

### 8.1. Purpose Metadata

A catalog or governance registry can track:

- Processing purpose and business owner.
- Data/subject category, jurisdiction, and classification.
- Consent or opt-in/opt-out state where applicable.
- Allowed uses, prohibited uses, and sharing limits.
- Effective dates, evidence source, and policy version.
- Dependent downstream datasets.

Not all data processing relies on consent; legal bases vary by law and context. The architectural challenge is preserving metadata needed to enforce decisions approved by the business and legal teams.

### 8.2. Propagating Privacy Signals

When a user withdraws consent or requests deletion, pipelines must know how curated tables, aggregates, feature stores, caches, training datasets, exports, and backups are impacted. Design deletion/tombstone events or keyed workflows to locate every copy.

Some broad aggregates may no longer reasonably link back to individuals, whereas some models or features may memorize training attributes. Whether deletion or retraining is needed requires legal, technical, and re-identification risk evaluation—never assume deleting a raw row settles everything.

## 9. Retention: How Long Should Data Be Kept?

Retention defines how long or under what conditions data may persist before archiving, deletion, or state transition per policy. Keeping data forever inflates costs, attack surfaces, and deletion complexity; deleting too early breaks audits, investigations, reconciliations, and trend analysis.

### 9.1. Defining Retention per Dataset

| Dataset | Purpose | Retention Considerations |
| --- | --- | --- |
| Raw events | Replay, pipeline debugging, rebuilding curated layers | Replay window, privacy obligations, storage cost |
| Curated transaction history | Reporting, reconciliation, business analysis | Record-keeping mandates, usage purpose, deletion requests |
| Aggregated metrics | Trends and planning | Analytical value, re-identification risk, expiry |
| Application logs | Troubleshooting and security investigations | Investigation window, cost, data minimization |
| Notebook/temp outputs | Short-term experimentation | Short TTLs, automated cleanup |
| Backups | Recovery from bugs or accidental deletion | Backup policies, legal holds, immutability, RPO/RTO |

Never hardcode legal retention periods in code without an owner- and legal-approved policy. Systems should consume retention rules as versioned metadata/configuration with owners and review dates.

### 9.2. Retention vs. Lifecycle Storage Tiers

Retention governs *whether* data is kept; lifecycle tiers govern *where* it is stored and at what cost/retrieval speed. An object might move to Archive after 90 days yet be retained for 7 years. Conversely, logs might be deleted after 30 days even if cheap storage remains available.

### 9.3. Legal Holds and Exceptions

A legal or investigation hold temporarily suspends deletion under authorized orders. Track:

- Who placed the hold and the legal/investigative basis.
- Affected datasets, tenants, time ranges, and copies.
- Review dates, release criteria, and audit trails.
- Lifecycle mechanisms honoring holds so automated cleanup jobs never delete held data.

Never let holds turn into permanent default retention; review and release them once the basis expires.

## 10. Data Lifecycle in an Analytical Platform

Data platforms organize data into zones with distinct purposes and trust levels. Zone names vary across architectures, but provenance, transformation level, ownership, and permissions must stay explicit.

~~~mermaid
flowchart LR
    Sources["Operational DB / Apps / Events"] --> Ingest["Ingestion + schema validation"]
    Ingest --> Raw["Landing / Raw zone"]
    Raw --> Validate["Quality + privacy transform"]
    Validate --> Curated["Curated / Trusted zone"]
    Curated --> Serve["Serving / Semantic models"]
    Serve --> BI["BI / ML / Data products"]
    Raw --> Archive["Archive / Retention"]
    Curated --> Archive
    Raw --> Delete["Expiry / deletion workflow"]
    Curated --> Delete
    Serve --> Delete
~~~

### 10.1. Landing and Raw Zones

Landing/Raw retains received or near-source payloads for replay, auditing, and investigation. Because this zone typically holds the most sensitive fields:

- Restrict ingestion identities to writing only their designated paths/topics.
- Isolate the restricted raw zone from areas analysts access daily.
- Validate schemas, source identities, timestamps, checksums, and formats.
- Attach metadata for source, arrival time, batch/event ID, classification, and retention.
- Enforce encryption, auditing, overwrite protection, or versioning as required.
- Never use Raw as the default sharing zone for notebooks, BI, or exports.

Raw does not have to persist indefinitely. You can keep a bounded window for replay and retain only necessary curated/aggregated datasets afterward.

### 10.2. Validated and Curated Zones

The Curated zone contains standardized, quality-checked, deduplicated data with business rules and privacy transforms applied. This is typically where most analysts work.

A strong pipeline should:

- Verify schema contracts and compatibility before publishing.
- Standardize timezones, currencies, encodings, identifiers, and null semantics.
- Handle duplicates, late-arriving events, and bad records with quarantine.
- Apply masking, tokenization, and minimization per approved purpose.
- Record lineage from outputs back to sources and transform versions.
- Store quality metrics, freshness, owners, and update timestamps.
- Publish atomically or via versioned snapshots so consumers never read half-written datasets.

Never overwrite valid data with incomplete or corrupt outputs. For batch, write to staging paths/tables, validate, and swap/publish atomically; for streaming, maintain checkpoints and state recovery.

### 10.3. Serving and Semantic Layers

The Serving zone/semantic model delivers data per use case: dashboards, metric layers, APIs, feature stores, or data products. Never let individual dashboards join raw restricted tables and invent conflicting metric formulas.

The semantic model should govern:

- Metric, dimension, and grain definitions.
- Row/column security and tenant filtering.
- Freshness/SLAs, data owners, and certification status.
- Aggregation rules preventing inference from tiny groups.
- Query logging, export policies, and quotas.

## 11. Data Catalog, Lineage, and Ownership

Once datasets are copied and transformed across pipelines, you must know where each dataset came from, who owns it, and where copies reside. Catalogs and lineage answer those questions.

### 11.1. Data Catalog

The catalog stores metadata describing datasets and usage rules. Useful entries include:

| Metadata | Contents |
| --- | --- |
| Identity | Name, location, format, schema, partitions, and version |
| Business context | Description, domain, owner, steward, and data product |
| Classification | Sensitivity, PII fields, tenant/jurisdiction, allowed uses |
| Lifecycle | Created/updated times, retention, tier, deletion/hold status |
| Quality | Freshness, completeness, validity, uniqueness, and known issues |
| Access | Roles, policies, approved purposes, and access request paths |
| Lineage | Upstream sources, jobs/versions, downstream datasets, and consumers |

Catalog metadata also requires access control and auditing. Never expose sensitive schemas, sample rows containing PII, or query previews to unauthorized users.

### 11.2. Lineage

Lineage maps which sources feed which datasets through which jobs, and which consumers read them. Lineage helps you:

- Find all downstream tables impacted when a field's classification changes.
- Locate every place requiring deletion or redaction upon privacy requests.
- Investigate defects caused by upstream schema or transform changes.
- Assess impact before retiring a dataset or changing retention.
- Prove which sources and logic produced a given report.

Table-level lineage is the starting point; for sensitive data, track column/field-level and key transform lineage where feasible. Not every tool captures full lineage automatically; pipelines may need explicit instrumentation and conventions.

### 11.3. Owners and Stewards

Data owners are accountable for business purpose, quality, and authorized uses; platform/data custodians operate infrastructure, protections, and pipelines; data stewards maintain metadata, definitions, and rules. Keep responsibilities explicit so no dataset ends up "owned by nobody" while read by many.

## 12. Data Quality, Schema Evolution, and Reproducibility

Well-protected sensitive data that is inaccurate can still drive harmful decisions. Quality and governance must accompany security.

### 12.1. Quality Dimensions

- **Completeness:** required fields are populated as expected.
- **Validity:** values conform to domains, formats, and business rules.
- **Accuracy:** data reflects verifiable business truth.
- **Uniqueness:** no duplicates outside defined semantics.
- **Consistency:** rules across tables and sources do not conflict.
- **Timeliness/freshness:** data updates within committed timeframes.
- **Integrity:** keys, checksums, and source constraints remain intact.

Every critical dataset needs quality rules, thresholds, owners, alerts, and quarantine handling. Never merely log an error and keep publishing bad data as clean.

### 12.2. Schema Evolution

Schema changes affect pipelines, dashboards, models, and access policies. Classify changes carefully:

| Change | Risk | Handling |
| --- | --- | --- |
| Adding an optional field | Older consumers can usually ignore it if contracts allow | Version schema, test consumers, update catalog |
| Changing type or semantics | Existing queries/logic may fail or miscompute | Introduce new field/version, migrate, time-boxed dual-read |
| Removing a field | Downstream models, retention, or deletion workflows may depend on it | Lineage impact analysis, migrate consumers, deprecate |
| Changing identifiers | Joins, token mappings, and dedup may break | Mapping versions, backfills, validation |
| Increasing field sensitivity | Existing permissions may become overly broad | Reclassify, tighten policies, audit |

### 12.3. Reproducibility

Reproducing analytical outputs requires versioning source snapshots or watermarks, schemas, transform code, dependencies, parameters, reference data, and runtime environments. You do not need to retain raw PII forever just for reproducibility; pseudonymized/aggregated snapshots or minimized immutable events may suffice depending on purpose.

## 13. Data Deletion: Deleting Properly and Proving It

Deleting a row from a primary table does not delete all copies. Data may persist in raw files, curated tables, materialized views, warehouse caches, search indexes, feature stores, exports, notebooks, object versions, replicas, and backups.

### 13.1. Building a Deletion Workflow

1. Authenticate the request and verify subject/tenant/dataset scope.
2. Check purpose, legal basis, legal holds, and approved exceptions.
3. Query the catalog/lineage to locate sources, downstreams, replicas, caches, exports, and processors.
4. Issue a tracked deletion job ID and status; never rely on ad-hoc manual steps.
5. Delete or redact per policy at sources and online stores; emit tombstone/deletion events to pipelines.
6. Rebuild aggregates, indexes, or materialized views where single-record deletion is unsupported.
7. Handle backups/archives per policy: scheduled expiration, crypto-erasure, or restore-and-redact where mandated and supported.
8. Verify via controlled queries/scans, catalog state, and processor acknowledgements.
9. Store minimal completion evidence (status, errors, exceptions, timestamps) without retaining the deleted PII inside audit logs.

### 13.2. Deletion Propagation

~~~mermaid
flowchart TB
    Request["Verified deletion request"] --> Registry["Subject / tenant registry"]
    Registry --> Lineage["Catalog + lineage lookup"]
    Lineage --> Source["Source / OLTP"]
    Lineage --> Raw["Raw lake"]
    Lineage --> Curated["Curated tables"]
    Lineage --> Serving["Views / indexes / features"]
    Lineage --> Export["Exports / downstream processors"]
    Source --> Verify["Verification + evidence"]
    Raw --> Verify
    Curated --> Verify
    Serving --> Verify
    Export --> Verify
    Verify --> Done["Closed / exception tracked"]
~~~

Workflows often run asynchronously; "request accepted" does not mean "deletion completed." Track states distinctly: pending, completed, failed, and legally retained.

### 13.3. Deletion in Backups

Immutable backups or retention locks may prohibit deleting individual records immediately. Organizations must define approved policies: expire backups on schedule, isolate and restrict restore access, or apply crypto-erasure where key scoping and semantics allow. When restoring an older backup, replay the deletion ledger/tombstones before returning data to active service.

Never claim "completely erased" if data persists in retained backups. Status reports should clearly distinguish online systems purged, copies awaiting backup expiry, and legal exceptions.

### 13.4. Crypto-Erasure

Crypto-erasure renders ciphertext unreadable by destroying or revoking its encryption key. It works only when key scope, key backups, replicas, caches, and plaintext copies are tightly controlled. If multiple tenants share a data encryption key or plaintext exports sit outside storage, destroying one key will not erase every copy. Evaluate it as a careful architectural choice, not a universal delete button.

## 14. Storage Lifecycle: Hot, Warm, Cold, and Archive

Data platforms use storage tiers to balance cost and retrieval speed. Lifecycle rules transition data automatically based on age, access patterns, classification, and purpose.

| Tier | Characteristics | Used For |
| --- | --- | --- |
| Hot | Frequent access, low latency, direct queries | Active datasets, dashboards, live pipelines |
| Warm | Periodic or batch access, lower cost depending on service | Recent history, investigative datasets |
| Cold | Rare access, slower retrieval acceptable | Long-term history, infrequently queried data |
| Archive | Low storage cost, but restores take significant time/fees | Long-term compliance records, backups, policy audits |

Tier mappings vary across cloud providers. Some charge per GB, others per throughput or API request; archive tiers often require explicit restore steps before reading. Always verify minimum storage durations, retrieval fees, restore times, early deletion penalties, and direct query support.

### 14.1. Lifecycle Policies by Data Class

Do not move every dataset to Archive after the same number of days. Policies should weigh:

- Classification and legal/contractual limits.
- Data owner and business purpose.
- Access frequency and retrieval SLAs.
- Retention/holds, backups, and deletion workflows.
- Formats, compression, partitioning, and future readability.
- Storage, retrieval, API request, and network costs.

Restricted datasets may require stricter encryption, isolated keys, and narrower archive permissions. Public data may prioritize CDN/caching and space-optimized lifecycles.

### 14.2. File Formats and Partitioning

In data lakes, columnar formats like Parquet/ORC let queries read only required columns with strong compression. Partitioning by date, tenant, or domain cuts bytes scanned, though tiny partitions or excessive small files add metadata overhead and slow queries.

Partition keys should not expose raw PII when folder paths appear in logs or catalogs. Choose partition grain from query patterns and privacy boundaries; never partition so finely that each individual gets a separate file or directory.

### 14.3. Compaction and Small Files

Streaming ingestion can generate millions of tiny files. Compaction merges files within partitions/time windows, reducing metadata overhead and speeding up queries. Compaction must preserve idempotency, schemas, lineage, watermarks, and deletion markers; when running alongside live consumers, use atomic snapshot publishing.

## 15. Data Sharing, Analytics, and Machine Learning

Analytical datasets are frequently reused across teams and tools. Broad sharing increases business value while multiplying copies and attack surfaces.

### 15.1. Curated Data Products

Instead of granting raw access, domain teams can publish data products with:

- Defined schemas and metrics.
- Owners and freshness/availability SLAs.
- Classification, permitted purposes, and retention.
- Row/column policies or aggregate-only interfaces.
- Quality scores, lineage, and versions.
- Access request workflows, auditing, and deprecation policies.

Data products give consumers stable contracts and curb ad-hoc joins against sensitive sources.

### 15.2. Notebooks and Data Science Environments

Notebooks often allow local downloads, caching, cell outputs, or file exports. Enforce:

- Managed workspaces with strict identity and network policies.
- No raw access broader than experimental needs.
- Masked or synthetic samples for development.
- Managed output/temp storage with automated cleanup.
- Controls on notebook sharing, logs, packages, and external connectors.
- Restrictions against exporting to personal devices or public buckets.

### 15.3. Feature Stores and Model Training

Feature stores hold user-related attributes used in online and offline predictions. Track lineage from sources to features, event-time timestamps, consent/permitted uses, retention, and deletion workflows. Offline training sets and online serving stores hold separate copies; synchronize updates and expirations across both.

Models trained on personal data may memorize certain attributes. Deleting source rows does not automatically erase learned influences. When required, evaluate retraining, unlearning methods, or model scoping under policy and risk assessments.

### 15.4. Aggregates and Differential Privacy

Aggregation reduces granularity but does not eliminate risk when groups are small. Apply minimum cell thresholds, suppression, query budgets, noise, or differential privacy for sensitive statistical releases. Differential privacy quantifies an individual's influence on query outputs; it requires strict privacy budget accounting and rigorous implementation—not ad-hoc random noise.

## 16. Well-Architected: Data Lifecycle Trade-Offs

| Pillar | Design Decisions | Trade-Offs |
| --- | --- | --- |
| **Operational Excellence** | Catalogs, ownership, lineage, policy-as-code, deletion workflows, and runbooks | Automation cuts manual toil but demands clean metadata and accountable owners |
| **Security** | Classification, minimization, IAM, encryption, masking, auditing, and private networking | Deep controls add governance effort and can complicate ad-hoc queries |
| **Reliability** | Backups, immutable copies, restore tests, quality checks, and lineage | Multiple copies improve durability but complicate deletions and consistency |
| **Performance Efficiency** | Partitioning, columnar formats, compaction, caching, and tiering | Query optimization adds preprocessing and metadata maintenance |
| **Cost Optimization** | Retention, lifecycles, archiving, and data minimization | Archiving cuts storage spend while increasing retrieval time/cost |
| **Sustainability** | Reducing duplicate copies, unneeded fields, wasteful scans, and retention bloat | Shrinking footprint must still preserve audit and business needs |

Metrics to monitor:

- Percentage of datasets with complete owners, classifications, retention, and lineage.
- Count of restricted fields minimized/masked in the curated zone.
- Number of accounts with raw access and count of restricted exports.
- Percentage of deletion requests completed within SLA, plus legal hold exceptions.
- Over-retained data volumes and storage breakdown by tier.
- Query bytes scanned, freshness, quality failures, and restore success rate.
- Cost per pipeline/report or per TB of useful data.

## 17. Practice Exercise: Governing Analytical Data for an E-Commerce Platform

An enterprise ingests orders, payments, customer profiles, clickstreams, and application logs into a data lake. Analysts study revenue, campaigns, and customer behavior. Data scientists build churn prediction models. Auditors require historical transaction traceability; users can submit deletion requests or withdraw marketing consent under approved organizational policies.

**Assignment requirements:**

1. Build a data inventory and classify every field across customer, order, payment, clickstream, and log datasets.
2. Identify fields unnecessary for revenue dashboards and propose minimization rules.
3. Design Raw, Curated, and Serving zones; specify which zones hold PII and who can read each.
4. Choose masking, tokenization, or pseudonymization for email, phone, and customer ID; describe the key/mapping vault and approved re-identification flow.
5. Design RBAC/ABAC, tenant row-level security, column-level security, and negative test cases.
6. Propose distinct retention schedules for raw events, curated transactions, aggregates, logs, notebook outputs, and backups, incorporating legal holds.
7. Diagram lineage and deletion workflows from sources across the lake, warehouse, feature store, exports, and backups.
8. Design hot/warm/cold/archive lifecycles, file formats, and partitioning for clickstreams.
9. Propose audits/alerts to catch anomalous exports and out-of-purpose raw access.
10. Define metrics measuring security, privacy, quality, cost, and recoverability.

### Evaluation Hints

A strong design never grants raw access to all analysts. Revenue dashboards use curated aggregates; behavioral analysts use pseudonymous customer keys and generalized attributes; identity mappings live in a tightly locked vault. Data scientists receive purpose-approved datasets with clear source lineage.

Retention must balance audits, analytical utility, and deletion rights; backups carry separate policies and must never be reported as "immediately deleted" while copies remain within retention windows. Every dataset needs an owner, access policy, retention rule, quality checks, and lineage. Lifecycle tiers must factor in retrieval SLAs, not merely storage price per GB.

## 18. Production Readiness Checklist

- [ ] Critical datasets have inventories, owners, stewards, and classifications.
- [ ] Sensitive fields and linkable attributes are tagged.
- [ ] Purposes, allowed uses, consent, and usage conditions are tracked from the source.
- [ ] Unnecessary fields are stripped and granularity reduced before entering analytics zones.
- [ ] Masking, pseudonymization, tokenization, or anonymization match goals and threat models.
- [ ] Mapping/token vaults and keys have separated permissions, encryption, auditing, and rotation/recovery plans.
- [ ] RBAC/ABAC, row/column security, tenant isolation, and negative tests are implemented.
- [ ] Raw/restricted zones are never shared by default with analysts or notebooks.
- [ ] Encryption in transit/at rest covers data, exports, logs, snapshots, and backups.
- [ ] Audit logs record reads, exports, policy edits, and key changes, and are protected against tampering.
- [ ] Retention, lifecycles, legal holds, and deletions have owners, versions, review dates, and runbooks.
- [ ] Lineage can trace all downstream copies for schema or privacy changes.
- [ ] Deletion workflows span sources, raw, curated, serving, indexes, features, exports, caches, and backups.
- [ ] Backup/restore is tested; restores replay the deletion ledger/tombstones before resuming service.
- [ ] Data quality, schema evolution, freshness, and atomic publishing are verified.
- [ ] Hot/warm/cold/archive tiers meet retrieval SLAs and TCO targets.
- [ ] Notebooks, ML feature/training datasets, and external data sharing have dedicated policies.
- [ ] Alerts exist for anomalous queries/exports, retention expiry, quality failures, and deletion SLAs.
- [ ] Access revocation, key rotation, deletion, restore, and incident response drills have been rehearsed.

**Key takeaway:** Managing sensitive data begins with knowing what data exists, why it is needed, and who owns it. Minimize data before protecting it, enforce least privilege and purpose-appropriate identifier transformations, and govern retention/deletion across raw, curated, serving, archive, export, and backup copies. A mature data platform combines catalogs, lineage, quality, auditing, and lifecycle automation so analytical data stays valuable, purpose-bound, time-bounded, and verifiable.
