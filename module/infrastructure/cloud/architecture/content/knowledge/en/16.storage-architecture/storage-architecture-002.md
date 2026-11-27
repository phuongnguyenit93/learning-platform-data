# Designing Namespaces, Object Keys, and Data Partitioning

## 1. Why Data Organization Is an Architectural Decision

When data grows from a few thousand records to billions of objects or multiple terabytes, asking "where do we store it?" is no longer enough. A system needs an organizational structure to know **who owns the data, what scope it belongs to, how it is queried, how it is distributed, and how it will be moved or deleted**. If namespaces, object keys, and partitions are designed without intent, a system can suffer from hot partitions, high query costs, difficult tenant isolation, painful structural changes, or an inability to meet retention and deletion requirements.

Three related yet distinct concepts:

- **Namespace:** a logical naming scope that groups, identifies, and delineates data ownership. Examples include a bucket/container, schema, database, tenant namespace, or prefix.
- **Object key:** the identifier of an object within a namespace, typically used to read, write, delete, and look up the object. In object storage, keys are usually strings; slashes typically only create an illusion of hierarchy rather than physical directories.
- **Partition:** a way of dividing data into segments that can be managed, stored, queried, or distributed independently. Partitioning can be based on time, tenant, hash key, range, or a combination of dimensions.

In the **CLOUD_ARCHITECTURE** module, storage design must connect business requirements with data, network, compute, and deployment model choices. The goal is to balance **reliability, security, performance, scalability, cost, and operations** with a Well-Architected mindset.

Running example: a booking platform storing room photos, invoices, attachments, booking records, and analytics events. The system serves multiple enterprise customers (tenants), data grows daily, queries run by tenant and time range, and policies require retention, backup, auditing, and deletion.

## 2. Distinguishing Namespaces Across Storage Layers

The term namespace is used across many technologies, but its scope and semantics differ. Designs must state clearly **which layer's namespace is being discussed**.

| Layer | Common structure/namespace | Role |
| --- | --- | --- |
| Object storage | Account/project → bucket/container → object key | Separates data areas, permissions, lifecycles, and object identifiers |
| Relational database | Instance/cluster → database → schema → table → partition | Logical organization, access control, querying, and data distribution |
| Key-value / NoSQL | Table/collection → partition key → sort key | Partitions data and enables retrieval by access pattern |
| Distributed cache | Cluster → keyspace or key convention | Isolates cache by application/tenant and prevents key collisions |
| Data lake/warehouse | Catalog/database/schema → dataset/table → partition columns | Manages metadata and optimizes data scanning |
| Kubernetes | Cluster → namespace → resource names | Logically isolates resources and permissions in a cluster; not an object storage namespace |

**A logical namespace is not automatically a strong security boundary.** A tenant prefix in an object key does not stop another tenant from reading the object if IAM/bucket policies allow broad access. Likewise, a PostgreSQL schema helps group objects, but does not replace row-level security or database role permissions.

### 2.1. Choosing Namespace Boundaries

An organization may choose a shared namespace, per-tenant namespaces, per-environment namespaces, per-business-domain namespaces, or per-data-classification namespaces. Each approach has trade-offs:

| Organization model | Advantages | Limitations / trade-offs |
| --- | --- | --- |
| Shared, distinguishing tenants by key/column | Fewer administrative resources, easy capacity and pipeline sharing | Requires strict access control; noisy neighbors and mis-scoped tenant queries carry a large blast radius |
| Separate namespace per tenant | Logical isolation, easier to apply distinct policies/retentions | Many buckets/databases/schemas increase metadata, quotas, costs, and automation complexity |
| Separate by environment | Reduces risk of accidental operations between dev and prod | Uses more resources and requires managing copies/anonymization of test data |
| Separate by domain | Clear ownership and lifecycle, convenient permission assignment | Requires rules for cross-domain integration and lookups |

There is no single tenant count or data size threshold that dictates splitting namespaces. Evaluate isolation needs, tenant count, growth rate, administrative privileges, service limits, lifecycle, cost, and automation capability.

## 3. Designing Namespaces from Requirements and Trust Boundaries

Before naming buckets, tables, or prefixes, gather the following:

1. **Data owner:** which domain/team is responsible for creating, modifying, reading, and deleting?
2. **Accessors:** applications, service accounts, tenants, end users, or analytics systems?
3. **Classification and location:** public/internal/confidential data; which regions are permitted; do backups/logs share the same requirements?
4. **Query patterns:** lookup by ID, list by tenant, query by time range, filter by status, or batch scan?
5. **Growth rate and scale:** object counts, object sizes, write/read rates, largest tenant, and burst levels.
6. **Lifecycle:** retention period, storage class transitions, archiving, legal hold, deletion, and recovery.
7. **Migration path:** will key formats, partition keys, buckets, databases, or regions need to change in the future?

Example logical layout for the booking platform:

~~~text
organization/
  production/
    booking/
    customer-documents/
    property-media/
    billing/
    audit/
    analytics/
  non-production/
    booking/
    synthetic-test-data/
~~~

This is a conceptual diagram. On object storage, branches can be separate buckets/containers or prefixes inside a bucket. On a database, they can be separate schemas/tables or separate databases. Choose the implementation after evaluating access controls, namespace limits, lifecycles, and operational requirements.

### 3.1. Namespaces Must Carry Ownership and Policy

Every important namespace should have metadata:

| Attribute | Example | Purpose |
| --- | --- | --- |
| namespaceId | prod-property-media | Stable ID, independent of display labels |
| owner | property-platform | Accountable team |
| environment | prod | Lifecycle separation |
| dataClassification | confidential | Guides control and retention selection |
| region | approved-region-1 | Location constraint |
| retentionPolicy | media-7y | Business retention period |
| encryptionPolicy | managed-key-policy-a | How data is protected |
| costCenter | CC-104 | Cost allocation |

Do not embed secrets in namespace names. Display labels may change, but IDs and policy mappings should remain stable or have a clear migration process.

## 4. Object Key Design: Stable and Operable Identifiers

An object key is the address used to manipulate an object within a namespace. A good key is stable, unique within its namespace, aligned with access patterns, free of sensitive information, easy to manage for lifecycle/auditing, and supports a migration path.

### 4.1. Key Structure Pattern

A conceptual pattern:

~~~text
<domain>/<tenant-ref>/<object-type>/<time-bucket>/<stable-id>/<variant>
~~~

Examples:

~~~text
property-media/tnt-8f2a/room-image/2026/12/obj-01J8K2/original.jpg
property-media/tnt-8f2a/room-image/2026/12/obj-01J8K2/thumbnail-640.webp
booking-documents/tnt-8f2a/invoice/2026/12/obj-01J8M4/invoice.pdf
~~~

The key uses a pseudonymous tenant reference, time bucket, and stable ID. `tenant-ref` should not be an email address or organization name; `stable-id` should be a random/opaque ID or generated by a rule that does not leak internal information.

### 4.2. Folders in Object Storage Are Usually Logical Prefixes

Many object stores model objects as bucket-and-key pairs. Slash characters are commonly used to group prefixes for listings and UIs; they do not necessarily represent physical directories. Therefore:

- Deleting a "folder" may actually list and delete all objects matching a prefix.
- Prefix-based permissions depend on what the service's policy engine supports; do not assume folders have independent ACLs.
- A key with many slashes does not mean the object sits inside nested filesystem directories.
- Prefix listing tools can incur costs and pagination limits; avoid designs that require listing millions of objects per request.

### 4.3. Character, Encoding, and Length Rules

Adopt a consistent key ruleset: prefer lowercase ASCII letters, digits, and simple separators; avoid spaces, Vietnamese diacritics, control characters, and characters encoded inconsistently across URLs/shells; standardize percent-encoding when keys appear in URLs; avoid ambiguous delimiters; stay within the object storage service's length limits.

Never treat a key as a safe filesystem path. If an application joins keys onto a local path, normalize and guard against path traversal.

### 4.4. Keep Secrets Out of Keys

Keys frequently show up in access logs, pre-signed URLs, traces, cost reports, and admin tools. Never place raw email addresses, phone numbers, full names, home addresses, tokens, session IDs, credentials, or sensitive payloads in keys.

Even if a key is opaque, assess whether it can be correlated with identities from another system. Object access control must be enforced at the authentication/authorization layer, not by relying on keys being hard to guess.

## 5. Choosing IDs and Overwrite-Protection Strategies

Object keys are commonly built from domain, tenant reference, object type, time, and an ID. The ID plays an important role in scalability and correctness.

| ID type | Advantages | Trade-offs |
| --- | --- | --- |
| Random UUID | Easy to generate distributedly, harder to guess than sequential IDs | Long keys; prefix distribution must be considered |
| ULID / time-ordered ID | Roughly time-sortable, convenient for debugging | Can create write hot spots if many IDs share a prefix; timestamp portion can leak creation time |
| Monotonic sequence | Short, easy to order | Can concentrate writes, leak business scale, and is hard to generate uniquely across producers |
| Hash of identifier | Distributes fairly evenly and masks part of the input | Not easily reversible; must handle collisions and secrets if using HMAC |
| Composite key | Encodes access patterns explicitly | Long keys; structural changes cause migrations and field coupling |

For file objects, a sufficiently long server-issued random ID is usually appropriate. To prevent accidental overwrites, use conditional writes or create-only mechanisms supported by the service; do not simply check "object does not exist" and then write, because two concurrent writers can still race.

### 5.1. Conditional Object Writes and Immutability

For invoices or transactional documents, you can use immutable keys tied to an object ID and version. Edits create a new version or update a metadata record pointing to the current version. This supports auditing, though it increases storage and requires clear retention rules.

Do not let users upload files to arbitrary keys they choose inside a shared namespace. Generate the object ID server-side, verify ownership, and validate metadata before publishing a reference.

## 6. Partitioning: Splitting Data by Access Pattern

**Partitioning** divides a large dataset into smaller parts according to a rule. The goal is to reduce scanned data volume, distribute reads/writes across multiple nodes or shards, bound backup/restore/maintenance scope, support time-based or tenant-based deletion, and lower query cost through partition pruning.

Partitioning does not automatically make queries faster. If a query lacks the partition key, the system may have to fan out across many partitions. If data distribution is skewed, one partition can become much hotter than the rest.

### 6.1. Range Partitioning

Data is split by value ranges, commonly time, ID, or region. Example monthly partitioning for an events table:

~~~sql
CREATE TABLE booking_events (
    event_id       UUID NOT NULL,
    tenant_id      TEXT NOT NULL,
    occurred_at    TIMESTAMPTZ NOT NULL,
    event_type     TEXT NOT NULL,
    payload        JSONB NOT NULL
) PARTITION BY RANGE (occurred_at);

CREATE TABLE booking_events_2026_12
PARTITION OF booking_events
FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');
~~~

The upside is efficient time-range queries and retention, especially when the database skips irrelevant partitions. The downside is that continuous writes to the current partition can create a hot partition; partitions must be pre-created before data arrives, and late-arriving data must be handled.

### 6.2. Hash Partitioning

Data is assigned to a partition by hashing a key:

~~~text
partition = hash(tenantId + ":" + objectId) mod N
~~~

Hashing spreads skewed values more evenly than range partitioning in many cases. However, changing `N` remaps many keys to new partitions, forcing a reshard/migration. Hashing does not guarantee perfect balance if one tenant has vastly more volume or request rate than others.

### 6.3. List Partitioning

Data is split by an explicit list of values, such as region, data type, or tenant tier. This works well when the number of groups is bounded and administrative boundaries are clear. If the tenant count grows unboundedly, creating a dedicated partition per tenant can make metadata and operations unwieldy.

### 6.4. Composite Partitioning

You can combine range and hash—for example, partitioning by month and subpartitioning by tenant hash. This supports time-based retention and reduces hot spots for part of the load, but the partition count grows as months × hash buckets. Estimate partition counts, indexes, metadata, backups, and migration time before choosing it.

## 7. Choosing a Partition Key by Access Pattern

Do not pick a partition key just because a field is handy. List the critical queries first:

| Access pattern | Example query | Attributes to consider |
| --- | --- | --- |
| Read a single booking | Get booking by ID | `bookingId`; may need a lookup index or routing table |
| List a tenant's bookings over time | Tenant + time range | `tenantId` and `occurredAt`/`createdAt` |
| Find events for a booking | `aggregateId` + sequence/time | `aggregateId`, sequence, or stream partition key |
| List media objects of a property | Tenant + property + type | Tenant reference, property reference, and object type |
| Delete data by retention | Time range or tenant + time | Time/tenant partition aligned with deletion workflow |
| System-wide analytics | Time + event type | Partition column for pruning; avoid unnecessary scans |

### 7.1. Cardinality and Skew

- **Low cardinality:** few distinct values; one value may receive most of the traffic.
- **High cardinality:** many distinct values; can distribute better, though skew still needs checking.
- **Skew:** uneven distribution where a few keys/partitions carry disproportionate data or load.
- **Hot key:** a single key receiving high request frequency, turning its node/partition into a bottleneck.

If you partition only by `eventType`, a handful of common event types can create hot partitions. If you partition by `tenantId`, one huge tenant can overwhelm its partition. If you partition by daily timestamp, all new writes land on today's partition.

### 7.2. Designing Keys That Distribute While Remaining Queryable

One usable pattern:

~~~text
partitionKey = hash(tenantId + ":" + objectId) mod 32
sortKey      = occurredAt + "#" + eventId
~~~

This pattern spreads writes across the hash buckets, though queries by tenant and time must know or scan the relevant buckets. Another design uses tenant ID as the partition key and scales per tenant, paired with a mechanism to move huge tenants onto dedicated shards once they cross a threshold.

No single key optimizes every query. Typically you optimize for the primary access patterns, add indexes or secondary projections for secondary queries, and let certain analytics queries run in batches.

## 8. Designing Namespaces and Keys for Object Storage

Object storage generally fits images, videos, invoices, backups, log archives, and large data files. Common operations are put/get/delete/list by bucket/container and key. Design keys around how objects are accessed, not like a personal computer's folder tree.

| Layout | Example | Best for | Limitations |
| --- | --- | --- | --- |
| Tenant-first | `tenant/id/media/date/object-id` | Tenant-scoped listing/retention/permissions when tooling supports prefixes | A large tenant can concentrate load on one prefix |
| Time-first | `media/year/month/tenant/id` | Daily/monthly batches, archiving, and analytics | Listing a tenant across many days requires fan-out |
| Hash-shard-first | `media/hash-prefix/tenant/id` | Spreading keys across hash prefixes based on service behavior | Hard to list by tenant/time without an external index |

Do not blindly apply random-prefix tricks to every object store. Service scaling behavior and prefix limits vary by provider and evolve over time. Read current service documentation, measure your workload, and only add shard prefixes when evidence calls for it. Hash prefixes also make querying/listing harder without a metadata catalog.

### 8.1. Use a Catalog/Index Instead of Scanning Buckets

When the UI needs to list "all invoices for tenant A this month," maintain a metadata index in a database:

| objectId | tenantId | objectType | createdAt | objectKey | status |
| --- | --- | --- | --- | --- | --- |
| obj-01J8 | tnt-8f2a | invoice | 2026-12-18 | billing/tnt-8f2a/2026/12/obj-01J8/invoice.pdf | active |
| obj-01J9 | tnt-8f2a | invoice | 2026-12-19 | billing/tnt-8f2a/2026/12/obj-01J9/invoice.pdf | archived |

The application queries the catalog by tenant/time/type and then fetches the object. The catalog becomes critical metadata: it needs consistency, backups, indexes, permissions, and reconciliation when object uploads or deletes partially fail.

### 8.2. Secure Upload Workflow

1. The client asks the API to create an upload session.
2. The server authenticates the user/tenant and issues an object ID along with the target key.
3. The server issues a time-limited pre-signed URL scoped to that object if the design uses pre-signed uploads.
4. The client uploads to object storage; size, content type, and checksum are enforced per service capabilities.
5. The backend verifies upload completion, runs malware/content scanning if needed, and updates the catalog.
6. Only expose the object to consumers after confirming valid status.

Never treat a client-supplied `Content-Type` as proof of safety. Unverified newly uploaded objects should not appear at public download endpoints. Enforce URL expiration, permissions, object size, checksums, and cleanup of incomplete uploads.

## 9. Namespaces, Tenant Isolation, and Access Control

In multi-tenant systems, namespace boundaries are part of the security model:

| Model | Isolation level | Suitable when |
| --- | --- | --- |
| Dedicated bucket/container per tenant | Clear namespace separation, easy per-tenant policy/retention | Tenant count is bounded or customers demand strong isolation |
| Dedicated prefix in a shared bucket | Simple and namespace-efficient | Policies can reliably restrict prefixes and the application validates tenants |
| Dedicated database/schema | Allows per-tenant permissions and lifecycle separation | Fewer tenants or distinct governance requirements |
| Shared table with `tenant_id` | Easy to share schemas and connection pools | Row-level policies, query scoping, and isolation tests are strong enough |
| Sharded by tenant group | Distributes capacity across multiple databases | Need scale-out, large tenants, and shard management automation |

### 9.1. Do Not Trust Client-Supplied Tenant IDs

Tenant IDs must be derived from or verified against an authenticated identity/token/session with checked membership. Never let clients pass an arbitrary `tenantId` and use it directly to construct object keys or query databases.

Across all operations, ensure:

- The request's tenant is verified.
- The object/row belongs to that tenant before reading, modifying, or deleting.
- Keys cannot be manipulated to access another prefix.
- Workers and event consumers preserve tenant context, without trusting a `tenantId` in a payload from an unauthenticated producer.
- Admin/support access follows a dedicated workflow with auditing and least privilege.

### 9.2. Row-Level Security and Schema Separation

In relational databases, shared tables can use `tenant_id` and row-level security (RLS) to enforce access predicates in the database. This is an additional defense layer, not a replacement for application-level checks. Inspect connection pooling and how session context is set; if tenant context leaks across reused connections, data exposure can happen.

Separate schemas create an administrative boundary but still require permissions, connections, backups, and migrations. If a single application role has read access to all schemas, separating schemas provides no real isolation.

## 10. Hot Partitions, Noisy Neighbors, and Load Shedding

A single key or partition receiving excessive traffic can spike latency even while overall system capacity has headroom. Monitor request rates, read/write throughput, and throttling per partition/key, largest tenant capacity, p95/p99 latency, retries, and errors.

| Mitigation | How it works | Trade-off |
| --- | --- | --- |
| Hash suffix/bucket | Splits one hot key into multiple logical shards | Aggregated reads/writes must fan out |
| Salting | Adds a dispersing component to the key | Readers must know the salt or query an index |
| Time bucketing | Splits data by minute/hour/day/month | Multi-range queries must read multiple partitions |
| Tenant isolation | Moves huge tenants to dedicated shards/namespaces | Increases operational and migration overhead |
| Caching | Reduces reads hitting the data source | Cache invalidation, stale data, and stampedes |
| Queuing/write buffering | Smooths write bursts | Increases latency and requires idempotency |
| Rate limits/quotas | Caps noisy tenants or workloads | Needs fairness and quota-increase processes |

### 10.1. Example: Salting a Hot Counter

If one property gets massive view traffic, a single counter can face heavy concurrent writes. You can use 16 buckets:

~~~text
counterKey = property-42#bucket-(hash(requestId) mod 16)
~~~

Each request updates one bucket; to read the total, the system sums all 16 values. This spreads writes but increases reads/aggregation work and relies on an evenly distributed hash. If an exact real-time value is needed for a booking decision, a sharded counter may not be suitable as an authoritative source of truth.

## 11. Partitioning in Databases and Data Lakes

Partitioning is implemented differently by each engine:

- **Table partitioning:** one logical table made of multiple physical/logical partitions by range/list/hash.
- **Sharding:** distributing data across multiple database nodes or clusters; the application/router must locate the shard.
- **Partition keys in NoSQL:** routes records to partitions or replica sets per the service's semantics.
- **Data lake partitioning:** organizes files/datasets by columns such as date, region, or `event_type` to reduce bytes/files scanned.

### 11.1. Partition Pruning

If a table is partitioned by `occurred_at`, a query with a time predicate can read only the relevant partitions:

~~~sql
SELECT tenant_id, COUNT(*)
FROM booking_events
WHERE occurred_at >= TIMESTAMPTZ '2026-12-01 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2027-01-01 00:00:00+00'
GROUP BY tenant_id;
~~~

The query planner can skip partitions outside the range if the expression and schema support pruning. If the application wraps the column in a function or cast that prevents range inference, pruning can become ineffective. Check the execution plan on the actual engine rather than relying on SQL that merely looks right.

### 11.2. Partition Keys and Indexes Are Different Concepts

A partition key determines how data is split; an index helps locate rows within a data scope or index structure. Having partitions does not make every query fast. Having indexes does not mean data is evenly distributed across nodes.

For example, a monthly partitioned table may still need an index on `(tenant_id, occurred_at)` inside each partition to query tenant history efficiently. However, indexes also add storage overhead, write amplification, and maintenance time.

### 11.3. Choosing Time Granularity

| Granularity | Benefit | Risk |
| --- | --- | --- |
| Daily | Granular retention and daily queries | Many partitions if kept for years |
| Monthly | Fewer partitions, fits many monthly reports | Current partition grows large under heavy load |
| Quarterly/yearly | Simpler metadata management | Harder to scan and delete fine-grained slices |
| Tenant + month | Clear per-tenant querying and retention | Partition count grows as tenants × periods |

Estimate concurrent partition counts, size per partition, data skew, index counts, and maintenance costs. For large event datasets, you can partition a data lake by date and tenant bucket instead of creating physical partitions for every tenant.

## 12. Migrating and Evolving Keys/Partitions

Namespaces and keys often outlive application versions. Changing a key or partition structure can affect URLs, database references, events, caches, backups, analytics, jobs, and operational tooling.

### 12.1. Expand–Migrate–Contract

1. **Design the new layout:** define the key format, version, access patterns, permissions, and lifecycle.
2. **Expand the catalog:** add an `objectKeyV2` field or old → new mapping; do not delete old references.
3. **Dual-read:** the application reads the new key first, falling back to the old key during a controlled migration phase.
4. **Backfill/copy:** migrate objects/records in batches with checkpoints, checksums, and idempotent retries.
5. **Dual-write or routing:** apply only when semantics and reconciliation are clear; avoid two competing sources of truth.
6. **Verify:** reconcile counts, checksums, metadata, permissions, retention, and readability.
7. **Cutover:** move consumers/producers to the new key or partition in controlled waves.
8. **Contract:** retire old read paths only after no references, consumers, backups, or jobs depend on them.

### 12.2. Mapping Catalog for Object Keys

| objectId | keyV1 | keyV2 | migrationStatus |
| --- | --- | --- | --- |
| obj-01J8 | media/tnt-8f2a/2026/12/obj-01J8.jpg | property-media/7f/tnt-8f2a/2026/12/obj-01J8/original.jpg | verified |
| obj-01J9 | media/tnt-8f2a/2026/12/obj-01J9.jpg | property-media/3a/tnt-8f2a/2026/12/obj-01J9/original.jpg | copied |

The catalog lets the application rely on a stable `objectId` while the physical object key changes. Old keys are deleted only after retention policies and all references are verified.

### 12.3. Changing Partition Keys or Shard Counts

Changing the hash bucket count from 16 to 32 alters where old and new keys map. You cannot simply change the formula and let the application read blindly; you must know which shard holds existing data, build a mapping or versioned partition scheme, support dual-reads during transition, migrate in batches, verify checksums/counts, handle concurrent writes, and cut over with rollback capability.

Even when sharding with consistent hashing or virtual nodes, changing node membership still requires checking the percentage of keys that move and rebalancing capacity.

## 13. Lifecycle, Retention, Archiving, and Deletion

Well-designed namespaces and partitions simplify lifecycle management. Monthly data can be archived or dropped by period; per-tenant objects make it easier to inspect a tenant's data when a contract ends. Still, this must be coordinated with the metadata catalog and copies.

| Policy | Questions to answer |
| --- | --- |
| Retention | How long must data be kept for business, contractual, or legal reasons? |
| Lifecycle tiering | When should data move to a cheaper tier; does access frequency allow it? |
| Archive | Within what time must restores complete; who is authorized to request a restore? |
| Deletion | How are objects, rows, indexes, caches, replicas, archives, and copies deleted? |
| Legal hold | Which data must not be deleted while under a legal preservation order? |
| Backup | How long are independent backups kept; are there immutable protections and restore tests? |

**Deleting a namespace does not necessarily mean all data is gone.** Object versions, replicas, backups, archives, caches, data lake copies, or exports may still remain. Deletion workflows must define scope, proof of deletion, and completion SLAs.

For time-partitioned database tables, dropping a partition can be faster than deleting rows one by one, but it is only safe when the entire partition has expired past retention and has no legal holds. For object storage, deleting a prefix may require listing/deleting many keys and handling versioning; use a checkpointed workflow.

## 14. Security, Encryption, and Auditing by Namespace

Namespaces help structure policies, but must be paired with:

- IAM/roles scoped by bucket, prefix, table, schema, or partition where supported.
- Encryption in transit and at rest; key management, rotation, and decrypt permissions.
- Auditing of access, object lifecycles, schema changes, policy changes, and delete operations.
- Data classification and minimization; never put PII into keys or partition labels.
- Verified tenant context across APIs, workers, events, and batch processing.
- Private endpoints/network policies when access paths must be protected.

Avoid using prefix names as an authentication mechanism. Even if a user knows another tenant's key, the API must still verify object metadata permissions and tenant ownership before issuing a download URL.

### 14.1. Pre-Signed URLs and Object Keys

Pre-signed URLs grant temporary access to a specific object under signed conditions. Protect the URL like a secret while it is valid:

- Use a short TTL tailored to the task.
- Do not log full URLs in application logs or analytics.
- Restrict object key, HTTP method, and content constraints where supported.
- Never share URLs across tenants or use them as permanent IDs.
- After upload, verify the object and update the catalog using server credentials.

## 15. Observability, Capacity, and Partition Health Checks

Tracking total system capacity alone is insufficient. One hot partition can drive high latency while average utilization looks low.

| Metric group | Indicators to monitor |
| --- | --- |
| Namespace | Object/row counts, capacity, growth, owners, percentage of untagged resources |
| Key distribution | Frequency by prefix/partition key, top hot keys, key cardinality, and skew |
| Storage | Read/write requests, p95/p99 latency, throughput, throttling, errors, object size distribution |
| Database | Partition sizes, index sizes, pruning effectiveness, locks, vacuum/maintenance, replication lag |
| NoSQL/sharding | Read/write capacity per partition, throttling, hot partitions, rebalance movement |
| Data lake | File count/size, small-file problem, bytes scanned, partition pruning, and query cost |
| Lifecycle | Objects/rows due for transition, archive/delete backlog, restore times |
| Security | Access denied, cross-tenant attempts, policy changes, unusual downloads/exports |
| Cost | Storage tiers, request/list/egress charges, indexes/replicas, backups, and migration costs |

### 15.1. Check Distribution Before Scaling

When a query is slow, answer: how many partitions and bytes/rows does it read; is any partition/key significantly hotter than others; are partition pruning or indexes actually used in the execution plan; is the request bound by storage IOPS, database CPU, locks, network, or serialization; would changing keys break tenant/time queries; and how much data must move—and for how long—during a scale-out?

Do not try to cure a hot partition by blindly adding nodes; if all requests still route to the same key, extra capacity may not help.

## 16. Practice Exercise: Designing a Storage Layout for a Booking Platform

**Context:** The system has 5,000 tenants. Three primary datasets: property/room photos totaling 30 million objects, read-heavy with bursty writes; booking events totaling 2 billion events, queried by tenant and time range with 7-year retention; invoices, which are sensitive data requiring strict per-tenant authorization and regulatory retention.

### Tasks

1. Design a namespace layout for production/non-production and the media, booking, billing, and audit domains.
2. Propose object keys for photos and invoices; explain IDs, tenant references, time buckets, variants, and how PII is avoided.
3. List access patterns for booking events; choose range/hash/composite partitioning and justify why.
4. Analyze large tenants at risk of causing hot partitions; propose dedicated shards, salting, hash buckets, or quotas.
5. Design a metadata catalog for object keys to support tenant/time/type listing without scanning buckets.
6. Build namespace access policies, IAM, tenant validation, encryption, retention, and pre-signed URL rules.
7. Plan a key format change from v1 to v2 with dual-read, backfill, checksums, cutover, rollback, and old-key cleanup.
8. Define metrics for hot keys, partition skew, request latency, lifecycle backlogs, and cost.
9. Write an ADR documenting choices, rejected alternatives, risks, and conditions to revisit the design.

### Submission Template

| Component | Namespace | Key/partition strategy | Access pattern | Controls and lifecycle |
| --- | --- | --- | --- | --- |
| Property media | `property-media` | Tenant ref + object ID + variant; hash bucket if needed | List by property, read by object ID | Private, upload scanning, age-based tiering |
| Booking events | `booking-events` | Time range combined with tenant hash or shard strategy | Tenant + time, events per booking | 7-year retention, index/catalog |
| Invoices | `billing-invoices` | Tenant ref + year/month + opaque ID | Lookup by invoice/tenant | Encryption, audit, strict permissions, legal hold |

### Completion Criteria

- Namespaces distinguish owner, environment, domain, and data classification.
- Object keys are stable, unique, free of PII, and aligned with access patterns.
- Partition keys are justified by cardinality, skew, throughput, and query requirements.
- Hot tenants/noisy neighbors are assessed with concrete mitigations.
- The catalog/index includes sync and recovery handling when object uploads or deletes fail.
- Migrations do not break references or delete old copies prematurely.
- Retention, archiving, backups, and deletion have verifiable evidence and clear owners.
- Request, storage, index, replica, egress, and operational costs are accounted for.

## 17. Well-Architected Checklist Before Finalizing Storage Layout

- [ ] Namespace layer (bucket/schema/table/tenant/partition) and actual technology semantics are defined.
- [ ] Every namespace has an owner, environment, classification, region, retention, and cost center.
- [ ] Security boundaries do not rely solely on prefixes or names; IAM and tenant validation are verified.
- [ ] Object keys are stable, unique, free of PII/secrets, and follow encoding/length rules.
- [ ] Access patterns were analyzed before choosing range/hash/list/composite partitioning.
- [ ] Cardinality, skew, hot keys, hot partitions, and noisy neighbors have been evaluated.
- [ ] A catalog/index exists whenever metadata queries are needed instead of listing/scanning all objects.
- [ ] Partition pruning, query plans, index costs, and scale-out/resharding capability have been checked.
- [ ] Storage topology and backups/replicas do not share an unaccepted single failure domain.
- [ ] Lifecycle/retention/deletion covers versions, archives, replicas, backups, and caches.
- [ ] Migrations include mapping, dual-read/cutover, checksums, checkpoints, rollback, and completion criteria.
- [ ] Pre-signed URLs, encryption, key management, auditing, and replay/restore permissions are controlled.
- [ ] Per-partition/key metrics and cost telemetry are sufficient to catch anomalies before users are impacted.
- [ ] An ADR records trade-offs across reliability, security, performance, cost, and operations.

**Core takeaway:** namespaces define the scope of data organization and governance; object keys identify objects under a durable convention; partitioning dictates how data is split and distributed. Good design starts from **access patterns, trust boundaries, growth rates, and data lifecycles**, and is validated through load distribution, access controls, migrability, recoverability, and real cost.
