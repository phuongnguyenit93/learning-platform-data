# Identifying Source Systems, Data Owners, and Data Consumers

A data model accurately reflects the business only when we know where data originates, who is responsible for its meaning and quality, and which systems or user groups consume it. An attribute such as customer status, product price, or inventory quantity may appear across multiple applications. Without clearly defining the authoritative source and governance accountability, copies easily drift out of sync, engineering teams may pick the wrong source for decisions, and users will not know whom to contact when discrepancies arise.

During data model requirements analysis, three related yet distinct roles must be investigated:

- **Source system:** Where data is created, recorded, or supplied to a processing flow.
- **Data owner:** The individual or business unit accountable for definitions, usage rules, quality, and governance decisions for a data domain.
- **Data consumer:** A system, business group, partner, or workflow that receives data to perform a specific job.

These three roles do not necessarily belong to the same organization or application. A CRM system may be where staff enter contact details, customer care may own customer profile rules, while the analytics platform and notification service act as data consumers. Analysis must clarify responsibilities and data flows across parties before deciding entities, keys, relationships, replicas, and integration patterns.

## 1. Distinguishing Data Sources, Authoritative Sources, and Storage Locations

### 1.1. What Is a Source System?

A source system is a system that supplies data to another workflow or system. A source may be:

- An operational application where users create or update data.
- A transaction-recording service, such as a payment or order management service.
- A device, sensor, or operational software generating data automatically.
- A partner platform sending data via APIs, messages, or files.
- A data warehouse, reference system, or curated dataset processed from multiple upstream sources.
- A manual source such as a spreadsheet, form, or import file managed by the business.

Never assume all data in a source system is accurate or authoritative. An application may capture initial data yet still require validation, reconciliation, or approval. A data warehouse may be a good source for standardized reporting yet unsuitable for updating transactional state.

### 1.2. Distinguishing Commonly Confused Concepts

| Concept | Meaning | Question to Answer |
|---|---|---|
| System of origin | Where data is originally created or captured | Where does the data first appear? |
| Source system | System supplying data to the flow under consideration | Which system is sending this data? |
| System of record | System designated to hold authoritative records for a data scope | Where is official state authorized to be confirmed? |
| Authoritative source | Recognized authoritative source for a specific domain, attribute, or purpose | Which source wins when conflicts occur? |
| Data warehouse/lake | Place aggregating, storing, and processing data for analytics or other uses | How was the data transformed and how much lag does it have? |
| Data consumer | System or user receiving and using data | Who uses the data, for what purpose, and at what quality level? |

An organization can have multiple authoritative systems for different data domains. The sales system governs order status; the warehouse system governs physical stock quantities; the payment provider is the external settlement authority for payment transactions; the customer platform governs contact details. No single system must necessarily be the authoritative source for every attribute.

Even within a single data domain, authority may be split by attribute or by point in time. For example, CRM governs display name and customer-provided contact details; the identity verification service governs verification status; the subscription service governs notification consent status. When two sources provide different values, you must know which source governs which attribute.

### 1.3. Do Not Equate Data Entry Location with Authoritative Source

A staff member may enter customer details into a sales form, while the official profile is created in the customer system only after deduplication checks. Similarly, warehouse staff may scan a package with a mobile app, while the warehouse management service is what confirms the received quantity.

Document separately:

- Where data is collected.
- Where data is validated or approved.
- Where data is authoritatively stored.
- Where data is replicated or transformed.
- Where data is used to make decisions.

This distinction prevents a read-only display copy from being misused as an authoritative update source.

## 2. Identifying Data Domains and Authoritative Sources

### 2.1. Starting from Business Domains

Before listing applications, identify the data domains the business cares about. Examples in an online store:

- Customers and contact profiles.
- Products and catalogs.
- Pricing, promotions, and selling terms.
- Orders and line items.
- Inventory and reservations.
- Payments and refunds.
- Shipping and fulfillment.
- Invoices and accounting vouchers.
- Accounts, roles, and access permissions.

A data domain is a group of concepts with relatively cohesive business meaning and governance rules. One application may manage multiple domains; one domain may span multiple applications. Therefore, do not mechanically treat application boundaries as data domain boundaries.

### 2.2. Building an Authority Matrix

For each domain, identify the authoritative source for key attributes, where they originate, where the master copy lives, and how other systems receive the data.

Example:

| Domain / Attribute | Authoritative Source | Origin or Entry Point | Primary Consumers | Notes |
|---|---|---|---|---|
| Customer contact profile | CRM | Website, support staff | Sales, customer care, analytics | Requires duplicate-profile merge rules |
| Customer verification status | Verification service | Verification workflow | Registration, payments, risk control | CRM displays only a replicated copy of status |
| Product information | PIM or designated catalog system | Product management team | Website, search, orders | Names and descriptions may be replicated |
| Active selling price | Pricing management service | Pricing team | Cart, orders, promotions | Orders must preserve locked purchase prices |
| Sellable inventory | Warehouse management system | Warehouses, POS, supplier integrations | Ordering, allocation, operations | Must distinguish on-hand stock from sellable stock |
| Order status | Order management system | Order placement and processing flow | Customer, warehouse, shipping, support | Delivery statuses may arrive from partners |
| Payment outcome | Payment provider and internal ledger per reconciliation rules | Payment gateway, payment service | Orders, accounting, support | Must specify final confirmation authority |
| Delivery events | Shipping partner or designated orchestration platform | Scanners, partners | Customer, support, analytics | May receive late or duplicate events |

System names in the table are examples illustrating how to analyze. When applying to a real project, replace them with the systems confirmed by the organization.

### 2.3. Authority Can Depend on Attribute and Purpose

One data field can be used across multiple contexts. For example:

- A customer's current default address is governed by CRM.
- An order's shipping address is a snapshot confirmed by the customer at placement time.
- An address used to issue tax documents may be subject to separate retention rules.
- An address standardized by a shipping carrier may exist solely for delivery routing.

Simply saying "CRM is the source of addresses" may lead developers to accidentally overwrite historical transaction addresses with the current profile address. Specify the meaning of each attribute, its applicable scope, and when its value is considered effective.

### 2.4. Handling Multiple Sources Supplying the Same Value

When multiple sources exist, define conflict resolution rules. Common approaches include:

- Designating one authoritative source for that attribute.
- Prioritizing sources by verification status or trust tier.
- Having an accountable business owner approve the final value.
- Retaining separate observations tagged with source and timestamp, then merging by rule.
- Computing the value from multiple inputs rather than picking one source.

Avoid a "latest update wins" rule when sources differ in reliability, clocks are unsynchronized, or updates arrive late. Recording time in one system does not necessarily reflect business effective time.

For every conflict, specify:

1. Which attribute conflicts.
2. Which sources can emit values.
3. Which source or rule holds decision authority.
4. How invalid or unknown-source values are handled.
5. Who is responsible for resolving exceptions.
6. Whether original values, sources, and merge history must be retained.

## 3. Identifying Data Owners and Governance Responsibilities

### 3.1. The Data Owner Is Accountable for Business Decisions

A data owner is typically an individual or business unit holding ultimate accountability for a data domain. They understand what the data means, what purposes it serves, and which rules must be upheld.

Responsibilities may include:

- Approving business definitions and terminology.
- Designating authoritative sources for the data.
- Deciding quality rules and acceptance thresholds.
- Approving access rights and sharing purposes.
- Setting retention, correction, and data handling policies.
- Assigning stewards for day-to-day data management.
- Resolving conflicts among consuming units.
- Approving changes that impact shared data.

A data owner is not necessarily someone who writes code, administers databases, or directly operates systems.

### 3.2. Distinguishing Related Roles

Role titles may vary across organizations. What matters is identifying actual responsibilities and decision authority.

| Role | Typical Responsibility | Example |
|---|---|---|
| Data owner | Business accountability and rule approval for a data domain | Head of customer experience accountable for customer profile definitions |
| Data steward | Manages definitions, quality, classification, and day-to-day issues | Data specialist reviewing duplicate profiles and catalog codes |
| Data custodian / platform owner | Ensures storage platform, backups, technical permissions, and operations | Database team or data platform team |
| System owner | Accountable for lifecycle and operation of an application | CRM product owner or operating unit |
| Data producer | Generates or supplies data under agreed contracts | Order service emitting `OrderConfirmed` events |
| Data consumer | Receives data and is accountable for compliant usage | Analytical warehouse or delivery service |
| Security / privacy specialist | Advises on and oversees security and privacy compliance | InfoSec team or privacy officer |

One person may wear multiple hats in a small organization. However, avoid leaving a critical responsibility unowned or defaulting every business decision onto the engineering team.

### 3.3. Assigning Decision Rights

Use a responsibility matrix to clarify who executes, who holds final accountability, who must be consulted, and who must be informed.

| Activity | Data owner | Data steward | System/platform owner | Consumer |
|---|---|---|---|---|
| Approve business definitions | Accountable | Propose and maintain | Technical consultation | Requirements consultation |
| Select authoritative source | Approve | Coordinate and document | Provide system context | State usage needs |
| Define quality rules | Approve | Author and monitor | Implement technical checks | Report usage defects |
| Operate data pipelines | Informed | Monitor quality | Technically accountable | Monitor outputs |
| Grant data access | Approve per policy | Review purpose and classification | Enforce technical permissions | Request access |
| Change schema or contract | Approve business impact | Coordinate notifications | Manage release | Assess compatibility |

Adapt the matrix to organizational structure. Never treat database admin privileges as authority to decide business meaning or permitted data usage.

### 3.4. Defining Contacts for Data Incidents

When users report a duplicate customer, wrong product price, or mismatched report figures, everyone must know who handles which part:

- Data steward verifies definitions and data quality.
- Data owner decides business values or rules during disputes.
- System owner investigates entry errors or upstream application logic bugs.
- Platform owner investigates transport, storage, permission, or operational failures.
- Consumer identifies workflow impact and supplies reproduction details.

Document intake channels, priority levels, response times, and escalation paths where business needs require them. Resolving bad data must never depend on users knowing the name of the engineer who built the system.

## 4. Identifying Consumers and Data Needs

### 4.1. Listing Consumers by Purpose

A dataset may be used by multiple groups, each with distinct needs. Identify consumers by the work they perform.

| Consumer Group | Purpose | Example Need |
|---|---|---|
| Operational applications | Execute direct transactions or workflows | Check inventory before confirming an order |
| Support applications | Display context for staff handling tickets | View order status history |
| Integrated systems | Forward data to other services | Send confirmed order info to delivery partner |
| Management reporting | Track KPIs and steer operations | Total revenue by day or region |
| Data analytics | Spot trends, forecast, or segment | Analyze customer repeat-purchase rate |
| Audit and controls | Reconcile, investigate, and prove compliance | Trace the origin of a change |
| External partners | Deliver contracted services | Receive shipping address and parcel code |

Do not stop at system names. For each consumer, ask the users or workflow owners what decision the data supports, when it is needed, and what happens if data is missing or delayed.

### 4.2. Gathering Specific Usage Requirements

Each consumer should be described across at least these dimensions:

- **Purpose:** Which workflow or decision does the data serve?
- **Scope:** Is the full data domain needed, or only a subset of attributes?
- **Granularity:** Is a single record, an event, a daily aggregate, or line-level detail needed?
- **Freshness:** Must data update immediately, within minutes, hourly, or daily?
- **History:** Is current state enough, or are versions and events required?
- **Volume:** Record count, generation rate, and peak timing.
- **Availability:** During which hours does the consumer need data, and how does it cope when the source is down?
- **Quality:** What levels of completeness, accuracy, uniqueness, and consistency are required?
- **Protection:** Who may access it, and which attributes must be masked or omitted?
- **Lifecycle:** How long does the consumer keep copies, and how are copies handled once the purpose ends?

For example, an order confirmation screen needs inventory fresh enough to decide stock reservation. An end-of-day inventory report may accept batch data, provided cutoff times and late-arriving transactions are well defined. These two consumers should not automatically share one update mechanism merely because both read inventory data.

### 4.3. Distinguishing Read Access from Write Authority

A consumer may need to read data without permission to update the source. For example, an analytics service reads order events to compute metrics; it must never write aggregated figures back into the order management system.

If multiple systems have permission to edit the same attribute, define coordination rules and decision authority. Otherwise, the model easily suffers multi-writer conflicts, sync loops, or silent overwrites.

For every data flow, classify access as:

- Read-only.
- Write directly to the authoritative source.
- Submit a change request for the authoritative source to execute.
- Consume events or read-only replicas.
- Submit proposed data for another role to confirm.

## 5. Investigating Data Flows and Inter-System Relationships

### 5.1. Mapping Flows from Creation to Consumption

A data flow diagram clarifies sources, transformation steps, storage locations, and consumers. A high-level diagram might look like this:

~~~mermaid
flowchart LR
    A["Website / Staff"] --> B["CRM"]
    C["Warehouse app"] --> D["Warehouse management system"]
    E["Payment gateway"] --> F["Payment service"]
    B --> G["Integration platform"]
    D --> G
    F --> G
    G --> H["Order service"]
    G --> I["Data warehouse"]
    H --> J["Support application"]
    H --> K["Shipping partner"]
    I --> L["Reporting and analytics"]
~~~

The diagram above illustrates only one possibility. Real projects may exchange data directly via APIs, events, CDC, or files. Clearly record data direction, protocol, owners, and control checkpoints.

For every arrow, answer:

- Who emits the data and who receives it?
- By what mechanism is data transmitted?
- Which entity or event triggers transmission?
- Are there transformation, filtering, enrichment, or aggregation steps?
- Does the consumer receive full records or partial subsets?
- Where are copies persisted?
- Who monitors errors and performs reconciliation?
- How is an output record traced back to its original source?

### 5.2. Choosing Integration Methods by Need

| Exchange Method | Characteristics | Suitable When | Details to Clarify |
|---|---|---|---|
| Synchronous API | Consumer calls source and receives response in the same flow | Immediate validation or mutation is needed | Latency, rate limits, error handling, auth, availability |
| Events / messaging | Producer emits events; consumers process independently | Changes must notify multiple consumers | Duplicates, ordering, retries, dead-letter queues, schema versioning |
| CDC | Reads changes from source logs or capture mechanisms | Low-latency change replication is required | Transaction boundaries, deletes, ordering, access rights, load on source |
| Batch / file | Transfers datasets on a schedule or in batches | Reporting, reconciliation, or non-real-time integration | Schedule, format, encryption, completeness checks, reprocessing |
| Replication | Maintains data copies in another system | Read scaling or isolating separate workloads | Lag, write permissions, failover, drift, replica ownership |

No single integration pattern fits every flow. APIs can be simple for immediate-response calls while introducing availability coupling across systems. Events decouple timing while requiring consumers to handle late or duplicate deliveries. Batch works well for certain reports while failing decisions that need real-time state.

### 5.3. Recording Data Transformation Points

Data is frequently transformed in transit: normalizing names, mapping codes, converting currencies, stripping sensitive fields, merging records, summing totals, or deriving attributes.

Every transformation step needs:

- Inputs and outputs.
- Transformation rules.
- Rule or code version when reproducibility is required.
- Business owner approving the semantics.
- Operational owner.
- Handling for invalid inputs.
- Lineage back to the source.

For example, a revenue report may exclude canceled orders, subtract refunds, and convert foreign currencies using the transaction-date exchange rate. Without documenting the definition and origin of these steps, two reports both labeled "revenue" can produce conflicting numbers.

## 6. Establishing Data Contracts Between Producers and Consumers

### 6.1. What Is a Data Contract?

A data contract documents the agreement between producer and consumer regarding structure, semantics, quality, delivery method, and operational responsibilities for data. Contracts help teams know exactly what data is supplied and which changes could impact consumers.

A contract may include:

| Component | Content to Agree Upon |
|---|---|
| Name and purpose | What task the dataset or event serves |
| Producer and owner | Supplying team and business-accountable owner |
| Authorized consumers | Permitted groups or systems |
| Schema | Fields, data types, required/optional, nested structure |
| Semantics | Business definitions, units, timezone, status codes |
| Identifiers | Primary key, business key, uniqueness rules |
| Quality | Validity, completeness, uniqueness, consistency rules |
| Freshness | Update cadence or maximum acceptable lag |
| Delivery | API, topic, CDC, shared table, or file |
| Protection | Classification, permissions, purpose, and sharing limits |
| History | How updates, deletes, versions, and late-arriving data are represented |
| Operations | Monitoring, alerting, support, and incident response |
| Changes | Compatibility rules, notice periods, and version deprecation |

Contracts can be expressed as documentation, schema registries, API specifications, or machine-readable configs. Format matters less than ensuring all parties understand and honor the same commitment.

### 6.2. Defining Clear Field Semantics

A field named `amount` is not clear enough. You must know:

- Is it pre-tax or tax-inclusive?
- Which currency?
- Is it amount paid, amount due, or remaining balance?
- What do negative values mean?
- What are the precision and rounding rules?

Similarly, a `status` field requires an enumerated list of states, meanings, transition conditions, and rules for potential new states. A timestamp field must specify timezone and whether it represents business occurrence time or system recording time.

If consumers interpret fields their own way, the exact same schema can yield incompatible business outcomes.

### 6.3. Managing Cross-System Keys and Identifiers

One entity can have multiple identifiers:

- Internal database primary key.
- Customer-facing business code.
- Partner-issued identifier.
- Identifier from a source system.
- Identifier generated when merging duplicate profiles.

Determine which keys are stable, which are meaningful only inside one system, and how mappings work between them. Never assume two systems can share the same auto-increment integer as a customer or product key.

An identity mapping table can link internal IDs to external source IDs. The mapping table should store source type, external code, internal ID, and effective validity or status when needed. Uniqueness constraints must reflect true scope: a code may be unique within one source yet collide with codes from another source.

### 6.4. Managing Schema Evolution

When a producer adds, renames, changes the type of, or removes a field, consumers can break or misread data. Contracts must define:

- Which changes are backward-compatible?
- Must consumers tolerate newly added fields?
- When are deprecated fields removed?
- Which versions are supported and for how long?
- Who is notified and with how much advance notice?
- How is compatibility tested before release?
- How to roll back or support un-upgraded consumers?

A seemingly minor technical change can alter business semantics. For example, redefining "completed" status to include partially delivered orders affects downstream reports and accounting workflows. Evaluate both semantics and structure.

## 7. Setting Data Quality Requirements Per Consumer

### 7.1. Quality Dimensions to Investigate

| Quality Dimension | Question | Example Check |
|---|---|---|
| Accuracy | Do values accurately reflect reality or rules? | Total matches line items and pricing policy |
| Completeness | Are required fields or records missing? | Confirmed orders must have customer ID and line items |
| Uniqueness | Are there duplicate records within business scope? | One payment transaction ID is not recorded twice |
| Validity | Do values match type, domain, and format? | Positive quantity, status within valid catalog |
| Consistency | Do fields or systems contradict each other? | Line count and total amount match the order |
| Timeliness | Does data arrive before the consumer needs it? | Order-confirmed event reaches shipping service within SLA |
| Traceability | Can source and transformations be identified? | Report indicates source and extraction timestamp |

Not every consumer needs identical quality levels. A trend report may tolerate a small share of late-arriving records if documented; an authorization or payment system demands stricter checks.

### 7.2. Assigning Quality Rules to Accountable Parties

For each rule, document:

- The rule and its business rationale.
- Applicable data scope.
- When validation executes.
- Warning thresholds or blocking thresholds.
- Team handling violations.
- How data is corrected and history preserved.
- How resolution is verified.

For instance, if customer codes duplicate, the system can detect and route them to a review queue. The data steward determines which profiles merge under owner-approved rules; engineering executes the merge safely and logs an audit trail. Never auto-delete a profile merely because two display names match.

### 7.3. Checking at Multiple Points in the Flow

Data can be validated at:

1. Data entry or creation point.
2. Authoritative source prior to commit.
3. Ingestion boundary from upstream sources.
4. Post-transformation steps.
5. Prior to publishing to consumers.
6. During consumer usage.

Validation at source blocks bad data from entering the ecosystem. Validation at ingestion catches integration bugs. Post-transformation validation ensures conversion rules did not corrupt data. Consumers still validate preconditions required by their own workflows.

Never rely solely on checks in final downstream reports, as pinpointing root causes and remediating upstream at that stage can be prohibitively expensive.

## 8. Rules for Access, Sharing, and Data Protection

### 8.1. Defining Sharing Purpose and Scope

Every consumer needs a confirmed usage purpose. Determine:

- Which fields does the consumer need and why?
- Can aggregated or anonymized data be used instead?
- Does the consumer need permission to view personal data?
- Does data cross organizational or system boundaries?
- How long is the consumer allowed to keep local copies?
- Is onward sharing to third parties permitted?
- When the purpose ends, how must data and copies be handled?

Data minimization prevents sending entire customer profiles when a consumer needs only customer ID and order status.

### 8.2. Role- and Scope-Based Access Model

Access permissions must tie to actions and data scope. For example, a customer care app may read names, contact info, and order statuses within its assigned scope; an analytics app may receive only pseudonymized data; a shipping partner receives only details needed for the assigned parcel.

If the system serves multiple organizations or tenants, define how data isolation is maintained across APIs, shared tables, background tasks, and reports. A consumer granted access to a shared table must still be restricted to its authorized scope.

### 8.3. Protecting Copies and Derived Data

Data replicated to data warehouses, caches, search engines, exports, or test environments may still contain sensitive information. Policies must define:

- Which attributes may be replicated.
- Whether encryption, masking, or pseudonymization is required.
- Who may access copies.
- Retention durations and deletion procedures.
- How data inside backups is handled.
- How onward sharing or exports are audited.

Never assume that once data leaves the source system it leaves the owner's accountability. Coordination across producers, consumers, and data stewards is required to enforce policy.

## 9. Handling Late, Missing, Duplicate, and Out-of-Order Data

### 9.1. Defining Behavior During Source Outages

Every consumer must know how to act when a source is unreachable, data arrives late, or records are invalid.

Questions to answer:

- Can operations continue using the most recent cached data?
- How stale can data get before it must no longer be used?
- Must a "data may be outdated" indicator be displayed?
- Are requests queued for retry?
- Who is alerted when a source stops sending data?
- When the service recovers, what are the catch-up sync and reconciliation procedures?

For critical transactional decisions, using stale copies can cause severe errors. For a trend report, displaying the latest available figures may continue provided the last-updated timestamp is clearly shown.

### 9.2. Preventing Duplicates and Out-of-Order Processing

Messages or events may be redelivered when a producer misses an acknowledgment or a consumer fails. Consumers need a way to recognize already-processed events, typically via `event_id`, transaction ID, or idempotency keys.

If multiple events for the same entity arrive out of order, a reliable version number, sequence, or business timestamp is needed to establish ordering. Never compare consumer arrival timestamps alone, as networks and queues can reorder deliveries.

### 9.3. Handling Deletes and Late-Arriving Data

A sync pipeline must define how deleted records are represented. Simply omitting deleted rows leaves consumers holding stale data indefinitely. Depending on technology, tombstones, delete events, or inactive statuses may be required.

Late-arriving data must be handled according to business semantics. A transaction recorded today that took effect on an earlier date may alter historical reports. Contracts must specify whether closed reporting periods may be restated, and if so, how versions or adjustments are recorded.

## 10. End-to-End Example: Online Sales System

Suppose an enterprise operates a website, CRM, product management system, warehouse, payments, orders, delivery, and an analytics platform.

### 10.1. Identifying Sources and Owners by Domain

| Domain | Authoritative Source | Data Owner (Example) | Data Steward (Example) |
|---|---|---|---|
| Customers | CRM | Customer management department | Customer data operations team |
| Products | PIM / product catalog | Product department | Catalog governance team |
| Selling price | Pricing service | Pricing department | Pricing management specialist |
| Inventory | Warehouse management system | Warehouse operations department | Inventory control team |
| Orders | Order management service | E-commerce department | Order operations team |
| Payments | Internal ledger reconciled against provider | Finance department | Payment reconciliation team |
| Fulfillment / delivery | Orchestration platform or confirmed partner data | Logistics department | Delivery tracking team |

Roles in the table are illustrative. A real project must confirm exact department names, accountable individuals, and decision scopes.

### 10.2. Identifying Consumers and Needs

| Consumer | Data Needed | Freshness | Write Permissions |
|---|---|---|---|
| Website | Products, prices, sellable stock, customer's order status | Varies by action; stock and price must be fresh at checkout | Submits order creation requests; never edits product master directly |
| Warehouse app | Line items, pick quantities, required shipping details | Near real-time for order fulfillment | Records warehouse actions into the warehouse system |
| Delivery service | Parcel ID, address, required contact details | Once order qualifies for shipping | Submits shipping requests; updates delivery events per contract |
| Customer care | Customer profile, orders, payment and delivery statuses per permission | Near real-time for active tickets | Submits adjustment requests per workflow |
| Data warehouse | Standardized events and business data | Scheduled or within agreed lag | Read-only |
| Management reports | Aggregated revenue, orders, inventory | Per reporting cycle | Read-only |

### 10.3. Tracing a Data Flow

When a customer places an order:

1. Website sends an order creation request to the order management service.
2. Order management service fetches pricing from the authoritative pricing source and locks the confirmed price on the order.
3. Order management service requests the warehouse system to reserve stock.
4. Payment service creates or confirms the transaction per its contract with the payment provider.
5. Once the order qualifies, the order management service emits events to the warehouse system, delivery system, and analytics platform.
6. Delivery system receives the minimum dataset required for the shipment.
7. Analytics platform ingests the event, standardizes it, and stores source and processing timestamp for reporting.

In this flow, the website initiates the request, yet is not the authoritative source for inventory or payment status. The analytics platform is a consumer and may become a data source for reports, yet must never unilaterally update order status. Each party holds distinct responsibilities.

### 10.4. Resolving a Data Discrepancy

Suppose the support screen displays a customer with two duplicate profiles:

- The data steward checks duplicate detection rules and the creation source of both profiles.
- The data owner confirms merge rules, especially for attributes with differing business meanings.
- The system owner investigates why the profile creation workflow failed to detect the duplicate.
- Consumers are notified of the canonical profile ID and how legacy IDs map to it.
- The system retains a merge audit trail to explain prior references.

Deleting a profile in CRM without updating foreign references across orders, reports, or other services leaves orphaned or inconsistent data. Quality remediation must account for the entire flow and all consumers.

## 11. Translating Survey Findings into Data Model Requirements

After identifying sources, owners, and consumers, turn findings into concrete design decisions.

| Survey Finding | Modeling or Integration Decision |
|---|---|
| Data domains and definitions | Entities, attributes, data types, and canonical glossary |
| Authoritative sources | Create/update rules, write permissions, reference sources |
| Multiple identifiers | Business keys, internal keys, and identity mapping tables |
| Multiple consumers | Appropriate read models, replicas, views, or data products |
| History requirements | Snapshots, version tables, events, or temporal data |
| Freshness requirements | APIs, events, CDC, batch, or replication |
| Quality rules | Constraints, data checks, alerts, and remediation workflows |
| Access permissions | Classification, access policies, role or tenant filtering |
| Data transformations | Mapping rules, lineage, and logic versioning |
| System changes | Schema contracts, compatibility, and migration plans |

### 11.1. Separating Master Data, Reference Data, and Transactional Data

When investigating sources, identify data categories:

- **Master data:** Describes core business entities such as customers, products, or suppliers.
- **Reference data:** Standardized lists or codes such as currencies, statuses, regions, or unit codes.
- **Transaction data:** Captures business activities such as orders, payments, and goods issue slips.
- **Event data:** Records something that occurred at a point in time.
- **Analytical data:** Data organized or transformed to answer analytical questions.

Each data category has different lifecycles and update rules. Reference catalogs may require approval workflows and versioning; transactions must preserve facts at occurrence time; analytical data must store lineage and refresh timestamps.

### 11.2. Designing Canonical Models and Consumer-Serving Models

A data domain can have a shared canonical model alongside models serving individual consumers. For instance, canonical customer data may live in a normalized structure; the website needs a read model optimized for product pages; reporting needs daily summary tables.

When creating serving models, specify:

- Which source supplies input data.
- How fields are transformed or derived.
- Which consumers are authorized.
- Freshness and accuracy bounds.
- How synchronization occurs when the source changes.
- Who is accountable if results are wrong.

Do not let every consumer invent its own interpretation when shared business definitions exist. Conversely, do not force every consumer onto one physical structure when query needs differ; what must align are semantics and data accountability.

## 12. Writing Acceptance Criteria for Sources, Owners, and Consumers

Requirements need verification criteria. Illustrative scenarios:

**Authoritative source identification scenario**

- Given: Order status appears in both the order service and the data warehouse.
- When: The two places display different statuses.
- Then: Users and systems know which source is authoritative for transactional status, which copy is replicated, and how to check synchronization timestamps.

**Owner assignment scenario**

- Given: A customer attribute has a disputed definition or value.
- When: Engineering and customer care disagree on handling.
- Then: A designated owner exists to decide the definition or rule, alongside a steward coordinating resolution.

**Consumer ingestion scenario**

- Given: A consumer subscribes to order-confirmed events.
- When: The producer publishes an event per contract.
- Then: The consumer receives the agreed fields, can detect duplicate events, and knows how to handle schema versions.

**Contract change scenario**

- Given: A producer needs to rename or deprecate a field.
- When: The change is proposed.
- Then: Consumer impact is assessed, the owner approves business changes, consumers are notified, and a transition window is provided per policy.

**Late-arriving data scenario**

- Given: A report consumes transactional data in batches.
- When: A transaction arrives after the batch cutoff time.
- Then: The report reflects the update timestamp and applies agreed restatement or late-arrival recording rules.

**Purpose-scoped access scenario**

- Given: A shipping partner needs data only to deliver a parcel.
- When: Data is transmitted under the integration contract.
- Then: The partner receives only fields approved for that parcel and never receives the full customer profile.

## 13. Common Discovery Mistakes

- **Treating the first data-entry system as authoritative:** Skipping validation, approval, or deduplication steps.
- **Assigning one authoritative source for an entire large domain:** Failing to recognize authority can vary by attribute and purpose.
- **Treating the engineering team as data owners:** Confusing platform operations with accountability for business meaning.
- **Listing only consumer names:** Missing which fields, freshness, history, and quality they need.
- **Allowing multiple systems to write the same attribute:** Lacking conflict resolution rules or causing sync loops.
- **Omitting field definitions:** Consumers interpret `amount`, `status`, `date`, or `quantity` differently.
- **Ignoring cross-system identifiers:** Misjoining records or losing entity traceability.
- **Checking schema only:** Data matches types yet still holds wrong semantics, missingness, or excessive lag.
- **Neglecting replica management:** Data is deleted or updated at the source while lingering at consumers.
- **Lacking an incident workflow:** Data defects bounce endlessly between teams.
- **Not communicating contract changes:** Producer ships a new schema causing consumers to fail or misinterpret data.
- **Treating a data warehouse as a transactional source:** Using lagged analytical copies for decisions requiring latest state.

## 14. Discovery Completion Checklist

Before moving to detailed design, verify:

- [ ] Data domains and key business definitions have been listed.
- [ ] Where data is created, validated, and authoritatively stored have been identified.
- [ ] Attribute- or purpose-level authority is defined when a domain spans multiple sources.
- [ ] Rules exist for resolving conflicting values across sources.
- [ ] A data owner and day-to-day steward are assigned for every domain.
- [ ] Business accountability, quality governance, and technical operations are clearly separated.
- [ ] Consumers, purposes, required fields, and read/write permissions are listed.
- [ ] Freshness, history, volume, availability, and quality needs are defined for each consumer.
- [ ] Data flows, transformation steps, and lineage paths are documented.
- [ ] Cross-system identifiers and key-mapping rules are defined.
- [ ] Data contracts, semantics, schemas, and change management rules are agreed upon.
- [ ] Handling rules exist for late, missing, duplicate, out-of-order, and deleted data.
- [ ] Access permissions, sharing purposes, and copy lifecycles are specified.
- [ ] Acceptance criteria and data incident escalation contacts are established.

The outcome of this discovery step is a domain map, authoritative source matrix, list of owners and consumers, and data exchange contracts and rules. This information grounds the design of entities, attributes, keys, relationships, integration models, and constraints tailored to how the organization actually creates and uses data.
