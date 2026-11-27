# Reviewing Data Correctness, Security, and Deployment Readiness

A **Spring Data MongoDB** application can run smoothly on a developer laptop yet fail critically in production: duplicate orders created after a retry, orders accessed across tenants, missing indexes in production, or legacy documents failing to deserialize after a schema change. Testing that an endpoint returns HTTP 200 proves only a tiny slice of system correctness.

This **capstone practice** establishes a pre-release review (*release readiness review*) for an ordering service using `MongoTemplate`, repositories, transactions, and optional reactive access. It centers on three questions:

1. **Is the data correct?** Are business rules enforced under concurrent writes, retries, partial failures, and schema evolution?
2. **Is the data safe?** Does the app enforce authentication, tenant authorization, sensitive-data protection, and least-privilege MongoDB access?
3. **Is the system ready to deploy?** Is there verified evidence from tests, performance measurements, backup/restore drills, monitoring, migrations, and incident runbooks?

The end goal is producing a **GO/NO-GO decision record** backed by real verification evidence, not a gut feeling that the code looks finished.

## 1. Capstone Context and Review Scope

Suppose the application serves multiple stores (*tenants*) across four collections:

| Collection | Core data | Critical operations |
| --- | --- | --- |
| `customers` | Customers per `tenantId`, normalized email, status | Register, read, and update customer info |
| `products` | Products, SKUs, and current prices | Catalog lookup, price updates, hiding products |
| `inventory` | Stock per `(tenantId, productId)` pair | Concurrent reservation, commitment, restocking |
| `orders` | Orders, line items, purchase-price snapshots | Create order, state transitions, view history |

Illustrative order document:

~~~javascript
{
  _id: "ord_1001",
  tenantId: "shop_a",
  idempotencyKey: "create-order-req-78",
  requestFingerprint: "sha256:...",
  customerId: "cus_100",
  status: "CREATED",
  currency: "VND",
  totalMinor: NumberLong("250000"),
  lines: [
    {
      productId: "prd_10",
      nameAtPurchase: "Insulated Bottle",
      unitPriceMinor: NumberLong("125000"),
      quantity: 2,
      lineTotalMinor: NumberLong("250000")
    }
  ],
  createdAt: ISODate("2026-11-20T03:00:00Z"),
  version: NumberLong("0")
}
~~~

This sample is an **exercise data contract**, not a mandatory Spring Data MongoDB schema. Money uses agreed minor units; businesses handling decimals must define rounding rules, `long`/`Decimal128` storage, and arithmetic bounds. Addresses, payment metadata, or personal details may need separate snapshots, retaining only fields genuinely required.

Verification scope must span **API → service → Spring Data → MongoDB → external systems**. When emitting events or calling payment gateways, MongoDB success alone does not prove end-to-end success.

## 2. Defining Invariants Before Testing

An *invariant* is a condition that must always hold across defined business boundaries, even when requests run concurrently or components fail. Every invariant needs an **enforcement point** and a **verification check**.

| ID | Invariant | Primary enforcement | How to prove |
| --- | --- | --- | --- |
| D1 | No two orders share `idempotencyKey` within a tenant | Unique index, duplicate-request logic | Two concurrent requests with same key yield one business outcome |
| D2 | Orders contain no products from another tenant | Tenant checks in service/queries | Creating an order with another tenant's `productId` fails |
| D3 | Never sell past available stock | Atomic conditional update or transaction | Under competing requests, total reserved never exceeds available |
| D4 | `totalMinor` equals sum of lines per pricing/discount rules | Domain service and data validation | Negative prices, zero quantity, overflow, and recalculation checks caught |
| D5 | Confirmed orders preserve price/name at purchase time | Snapshot inside `orders.lines` | Catalog edits never alter order history |
| D6 | Order state transitions follow state machine | Conditional update on state/version | Cannot transition `CANCELLED → PAID` when disallowed |
| D7 | Users only read/write authorized tenant data | Authorization, tenant predicate on every query | Cross-tenant tests on every endpoint and internal job |
| D8 | A single business event never triggers duplicate side effects | Event ID, idempotent consumers, outbox if needed | Replayed events never double-charge, re-notify, or double-credit points |

These are examples. Real systems add invariants from domain specs: taxes, refunds, fulfillment, erasure rights, retention limits, and financial reconciliation.

### Turning Invariants into Testable Criteria

Avoid vague checks like "orders must be accurate." Specify preconditions, concurrent actions, and postconditions. For D3: "Given an inventory document with `available = 3` and two independent concurrent requests each reserving `quantity = 2`, at most one succeeds, remaining stock is non-negative, and no confirmed order exists without reserved stock per design."

Note that many invariants **cannot be enforced by Java annotations alone**. `@NotNull` and `@Valid` validate request shapes, yet cannot replace unique indexes, conditional updates, or database transactions.

## 3. Reviewing Schemas, Mapping, and Indexes

In MongoDB, documents with differing shapes and BSON types can coexist. After migrations or Java refactors, a field may be a `String` in older documents and a BSON Date in newer ones; repositories keep running, yet filters and sorts return wrong results.

Minimum checks:

- Do required fields exist across legacy documents, new writes, and batch imports?
- Do monetary, quantity, timestamp, and ID fields use expected BSON types? Are `null`, missing fields, and empty strings distinguished properly?
- Do `@Id`, `@MongoId`, `@Field`, `@Version`, converters, and enums match physical storage contracts? Are ObjectId-formatted strings unexpectedly converted?
- Do embedded arrays grow unboundedly toward the **16 MiB** document limit? Are products/order histories embedded against their lifecycle?
- Are references (`customerId`, `productId`) checked for existence and `tenantId`? MongoDB does not enforce foreign key integrity automatically on arbitrary reference fields.
- Are database validators, if enabled, compatible with historical data and every writer (web, jobs, CLI, imports)?

### Unique Constraints Must Live in MongoDB

In `mongosh`, inspect actual indexes and verify required unique indexes:

~~~javascript
db.orders.getIndexes();

// Run during controlled migration/index deployment after resolving duplicates.
db.orders.createIndex(
  { tenantId: 1, idempotencyKey: 1 },
  { unique: true, name: "uq_orders_tenant_idempotency" }
);

db.products.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true, name: "uq_products_tenant_sku" }
);

db.inventory.createIndex(
  { tenantId: 1, productId: 1 },
  { unique: true, name: "uq_inventory_tenant_product" }
);
~~~

In this example, every order **must have** `idempotencyKey`. If a field is optional, redesign the unique index (e.g., an explicit partial index) and define policies for missing/`null` values. Check for existing duplicates before creating indexes, as MongoDB refuses invalid unique index builds. On **sharded collections**, verify shard-key and unique-index compatibility rules; never assume arbitrary unique compound indexes guarantee global uniqueness.

Annotations such as `@Indexed(unique = true)` state mapping intent, yet do not prove an index exists in production. Modern Spring Data MongoDB disables auto-index creation by default; deploy indexes via controlled migrations and verify afterward.

### Checking Two-Layer Validation

At the API layer, Bean Validation rejects malformed payloads. At the database layer, consider JSON Schema validators to stop alternative writers from bypassing basic invariants:

~~~javascript
// Example for an existing collection; apply only after auditing legacy data.
db.runCommand({
  collMod: "orders",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["tenantId", "status", "totalMinor", "lines"],
      properties: {
        tenantId: { bsonType: "string" },
        status: { enum: ["CREATED", "PAID", "CANCELLED"] },
        totalMinor: { bsonType: ["long", "int"] },
        lines: { bsonType: "array" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

This validator checks **basic structure only**; it does not prove `totalMinor` matches line sums, validate reference existence, or enforce state machines. `validationLevel: "strict"` with `validationAction: "error"` rejects updates to non-conforming legacy documents, so test impact carefully before enabling in production.

## 4. Reviewing Concurrency, Idempotency, and Transactions

### Single-Document Atomic Updates

Inventory updates should embed the "sufficient stock" guard inside **the update command itself**. The example below uses `MongoTemplate` and BSON `Document` to highlight the technical boundary:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public final class InventoryReservation {
    private final MongoTemplate mongo;

    public InventoryReservation(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public boolean reserve(String tenantId, String productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        Query filter = Query.query(Criteria.where("tenantId").is(tenantId)
            .and("productId").is(productId)
            .and("available").gte(quantity));

        Update update = new Update()
            .inc("available", -quantity)
            .inc("reserved", quantity);

        Document updated = mongo.findAndModify(
            filter,
            update,
            FindAndModifyOptions.options().returnNew(true),
            Document.class,
            "inventory"
        );

        return updated != null;
    }
}
~~~

Because filter and update run atomically **on one document**, two competing requests cannot both deduct against stale stock. However, `false` is ambiguous: missing document, wrong tenant, or insufficient stock. The service must map outcomes according to domain contracts without leaking another tenant's resource state.

**Critical limit:** when an order spans multiple products, updating several `inventory` documents and inserting an `order` do not form a transaction automatically. When all-or-nothing commit/rollback is required, use `MongoTransactionManager`, `@Transactional` at the right service boundary, and a replica set/sharded cluster supporting transactions—and test mid-flight failures and uncertain commits. Never run long transactions backfilling millions of documents.

### State Machines and Optimistic Locking

In an ordering system, `CREATED → PAID` and `CREATED → CANCELLED` may be valid, whereas `CANCELLED → PAID` must be blocked. Calling `save` with stale full documents risks *lost updates*.

- When using `@Version` in Spring Data, verify write paths go through optimistic-locking-aware APIs with acknowledged write concern. Raw driver calls or custom updates bypassing version checks defeat protection.
- For targeted state changes, put the **source state** in the query filter (`tenantId`, `_id`, `status = CREATED`), update to the target state, and check modified counts. Never assume reading state first and writing later suffices.
- On conflict, the service must decide whether to reload, return `409 Conflict`, or reapply per rules; never blind-retry using stale copies.

### Retried Requests and Unknown Commit Outcomes

A client timing out on `POST /orders` does not prove the server failed to create the order. Generating a fresh ID on retry and deducting stock again causes duplicate side effects. Use an **idempotency key** scoped by user/tenant with a request fingerprint:

1. Extract `idempotencyKey`, validate format and scope, and store it with `tenantId` under a unique index.
2. Only one creation request may claim the key. On subsequent calls with the same key, compare fingerprints: matching payloads return the recorded result; differing payloads return a conflict error.
3. Persist the order, reserve inventory, and write outbox events in the same transaction **when** atomic consistency is required and infrastructure supports it.
4. When clients lose responses, reconcile by the stable key before deciding to retry; handle `DuplicateKeyException` from the unique index rather than relying solely on `find` then `insert`.

For transactions, drivers attach labels such as `TransientTransactionError` or `UnknownTransactionCommitResult`. Each requires distinct recovery: transient transaction errors may warrant retrying **the entire transaction**; unknown commit results require **commit retry/reconciliation** per driver/framework contracts. Never automatically replay external side effects like payments, emails, or webhooks.

### Outboxes and External Events

When order creation must emit `OrderPlaced` to external systems, consider a **transactional outbox**: inside the transaction, save `orders` and an `outbox_events` record with a unique `eventId`; a publisher relays events after commit. Publishers can still double-send if they crash after broker ACK and before checkpointing. Consumers must therefore be idempotent by `eventId` and domain logic. MongoDB change streams can wake publishers promptly, though change streams report raw data mutations while outbox records formalize domain event contracts.

## 5. Tenant Authorization: Enforce Directly Inside Queries

In multi-tenant architectures, `tenantId` must come from a **trusted authentication/authorization context**, never blindly from request bodies or query strings. A `GET /orders/{id}` endpoint filtering solely by `_id` can return another tenant's data, even if IDs look unguessable.

Sample tenant-scoped read query:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public final class TenantOrderReader {
    private final MongoTemplate mongo;

    public TenantOrderReader(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    // tenantId must come from a verified security context.
    public Document findById(String tenantId, String orderId) {
        Query filter = Query.query(Criteria.where("_id").is(orderId)
            .and("tenantId").is(tenantId));
        return mongo.findOne(filter, Document.class, "orders");
    }
}
~~~

This query returns `null` if no matching document exists in the allowed tenant. The API boundary can return `404 Not Found` per contract to avoid disclosing whether the ID exists in another tenant. This assumes `_id` is stored as a BSON string matching Java `orderId`; if using `ObjectId`, align types and mappings accordingly.

Surfaces easily missed during tenant isolation reviews:

| Surface | Mandatory check |
| --- | --- |
| `findById`, `updateFirst`, `remove` | Every tenant-authenticated operation filters by tenant or uses a verified scoped layer |
| Repository/`@Query` methods | Do method names, annotations, and custom fragments include tenant predicates? |
| Aggregation `$lookup` | Can source or joined collections link records across tenants? |
| Pagination, exports, reports | Does tenant filtering persist across sorts, `$facet`, `$group`, and batch exports? |
| Batch jobs, message consumers | Does every message verify tenant context rather than trusting unauthenticated payloads? |
| `@DBRef` / `@DocumentReference` | Are loaded targets scoped by tenant/authorization? Never treat lazy loading as security |
| Admin/support endpoints | Cross-tenant access must be explicitly authorized, audited, and narrowly scoped |

**Mandatory test:** seed two tenants with valid documents and identical ID formats. Tenant A must be rejected on every read/write/export path targeting tenant B's data, even when swapping path IDs, filters, and pagination cursors. Never test only with nonexistent IDs.

## 6. Securing MongoDB Connections and Sensitive Data

### Authentication, Privileges, and Transport

- Enable environment-appropriate authentication; grant application accounts only required privileges on target databases/collections. Migrations, backups, and admins should use separate identities/roles when broader access is needed.
- Enforce TLS with certificate and hostname verification, and restrict network reachability to authorized components. Never disable certificate validation as a "quick fix" in production.
- Load credentials from a secret manager/injection mechanism; never commit passwords to Git, config files, CLI arguments, or logs. Establish key rotation, secret-leak incident response, and access audits.
- Evaluate encryption at rest, backup encryption, and key management; for highly sensitive fields, evaluate client-side field-level encryption or pre-designed safeguards.
- API/domain authorization **differs from** MongoDB account permissions. An app allowed to read a collection must still enforce tenant, object, and action permissions per user.

Example Spring Boot configuration via environment variables, keeping real credentials out of files:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

The actual `MONGODB_URI` must be supplied by a secret manager with proper topology, TLS, authentication mechanism, and database settings. Never print full URIs containing credentials to startup debug logs.

### Protecting Against Unintended Queries

With `MongoTemplate`, `Criteria`, and repositories, construct queries from validated fields and typed parameters. Avoid concatenating user input into JSON query strings or accepting client `Document` payloads containing arbitrary `$where`, `$ne`, `$regex`, or `$lookup` stages.

Pagination must enforce a maximum `limit`. Filters and sorts must map through server **allowlists**, backed by sensible timeouts and request size caps. `maxTimeMS` and client timeouts bound runaway cost partially, yet cannot substitute for query limits, indexes, and API rate limiting.

### Minimizing Data Exposure

- Return only necessary fields via DTOs/projections; never expose raw documents over APIs. Verify entity ↔ JSON ↔ BSON mapping.
- Logs should capture `traceId`, operation, collection, error code, latency, and policy-safe tenant ID; never print full documents, tokens, addresses, emails, or connection strings.
- MongoDB profiler/slow query logs and monitoring may capture sensitive filters/fields; restrict access, retention, and log shipping.
- Anonymize datasets before copying production snapshots to staging; control backups, dumps, and lower-environment access.
- Align TTL and deletion policies with legal/business retention rules; never place TTLs on orders/records requiring long-term retention merely to save disk space.

## 7. Checking MongoDB Operational Readiness

Data correctness also depends on topology, read/write settings, and cluster health:

| Area | Pre-deployment verification |
| --- | --- |
| Topology | Replica set/sharded cluster configured properly; transactions/change streams supported if used |
| Read/write concern | Durability and consistency guarantees match requirements; failover behavior tested |
| Connection pool | Pool size, wait queues, timeouts, socket counts, and backpressure sized for expected load |
| Indexes | Unique/compound/TTL/partial indexes exist in reality, without duplicates, collation mismatches, or excessive write drag |
| Queries | Critical queries checked with `explain("executionStats")` on representative datasets |
| Transactions | Small scope, zero external side effects pre-commit, retry/error handling, proper write concern |
| Change streams (if used) | Resume tokens/checkpoints, recovery past expired oplog tokens, dedup rules, oplog retention window |
| Capacity | Headroom for data, indexes, growth, and operational tasks; disk/CPU/memory monitored |
| Backups | Automated, encrypted, access-controlled, and **verified with restore drills** |

### `writeConcern` and `readConcern` Are Not Slogans

An *acknowledged* write does not guarantee identical durability across every failover scenario. For critical data, evaluate `majority` write concern, journaling policies, and latency trade-offs. `readConcern` and read preferences determine which nodes serve reads and what consistency guarantees hold; never assume secondary reads immediately see newly committed writes.

Optimal settings cannot be picked from a generic table. State explicit business rules: after creating an order, must the client read it immediately? Can reports tolerate slight lag? Could a primary loss ever discard the latest acknowledgment? Match those answers against real MongoDB semantics and failover tests.

## 8. Checking Performance, Scale, and Reactive Access

Core operations need empirical evidence:

| Query/workload | Example | What to monitor |
| --- | --- | --- |
| Read order by tenant + ID | `findOne({ tenantId, _id })` | Tenant scope, latency, documents examined |
| List orders by tenant/status | Filter + sort `createdAt` + limit | Compound index usage, no broad scans/sorts |
| Customer history | Filter `tenantId`, `customerId`, sort | Indexed pagination and deterministic tie-breaker |
| Reserve inventory | Conditional single-document update | Contention rate, p95/p99 latency, hot-SKU bottlenecks |
| Aggregation reports | `$match`, `$group`, `$lookup` | Memory, disk spill, stage doc counts, concurrent load |
| Bulk imports/migrations | Batched updates | Write throughput, replication lag, per-batch results |

Example order-list check in `mongosh`:

~~~javascript
db.orders.find({ tenantId: "shop_a", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(30)
  .explain("executionStats");
~~~

Record `winningPlan`, `indexName`, `nReturned`, `totalKeysExamined`, `totalDocsExamined`, `executionTimeMillis`, and any `COLLSCAN`/`SORT` stages. Never declare an `IXSCAN` plan healthy if it scans hundreds of thousands of keys for 30 rows; conversely, a `COLLSCAN` on a tiny collection is not automatically an error.

For **reactive access** (`ReactiveMongoTemplate`, `ReactiveMongoRepository`), verify subscription lifecycles, consumer backpressure, concurrency/buffer bounds, and `onError`/timeout handling. Replaying writes via `retryWhen` can trigger duplicate side effects; never enable unbounded retries. With synchronous `MongoTemplate`, never run blocking database calls on reactive event-loop threads.

When using `@DocumentReference` or `@DBRef`, count actual database commands on list screens to catch **N+1 queries**. For aggregations, confirm `$lookup` joins within tenant scope, early `$match`/`$sort` leverage indexes, and intermediate memory stays bounded.

## 9. Migrations, Schema Evolution, and Fallback Paths

A single release may bundle new app code, new indexes, data migrations, and event-schema changes. They do not all have to deploy simultaneously. Renaming `customers.name` to `customers.displayName` should follow **expand → backfill → verify → switch → contract**:

1. Deploy new code able to read both old and new schemas while ensuring all writers produce compatible data.
2. Run a versioned migration via controlled jobs/tooling: batched updates with checkpoints, locks, checksums, and idempotent reruns.
3. Verify independently: count missing new fields, check conflicting values, inspect samples, and test consumers.
4. Switch readers/writers to the new schema while monitoring latency and errors.
5. Remove legacy fields or indexes only in a later release after confirming zero active dependencies.

For destructive migrations, **rolling back code does not roll back data**. Dropping a field may be irreversible without backups/snapshots or retained source data. Prepare a *roll-forward* fix migration, tested restore path, or dual-schema overlap window.

Migration logs should track `migrationId`, checksum, status, timestamps, affected counts, checkpoints, and error details. Never mark `APPLIED` before verifying postconditions. When multiple workers compete to run, locks need lease expiration handling and fencing against stale workers still writing.

## 10. Acceptance Testing: From Real Failures to Evidence

Test suites should run against real MongoDB and representative data. Testcontainers fits integration tests well; transactions/change streams require a replica set or sharded cluster. Pure mocked repositories cannot prove unique index semantics, transactions, or failover behavior.

| Test ID | How to reproduce scenario | PASS criteria |
| --- | --- | --- |
| T01 | Two requests with same `(tenantId, idempotencyKey)` and payload | Single order and reservation; replay receives matching result |
| T02 | Same idempotency key with different payload | Returns conflict; no new order or reservation |
| T03 | Two tenants use identical SKU | Unique index allows across tenants, blocks duplicates within one |
| T04 | Tenant A queries tenant B's ID | Never reads, modifies, deletes, or exports tenant B data |
| T05 | Two threads reserve 2 items when `available = 3` | At most one succeeds; stock stays non-negative |
| T06 | Inject error between order creation and stock update | Transaction rollback or designed compensation preserves invariants |
| T07 | Two requests update the same order version | Stale update detected or invalid transition rejected |
| T08 | Timeout after DB commit before client gets response | Retry/reconciliation avoids duplicate side effects |
| T09 | Bulk migration interrupted mid-run and restarted | No skipped/overwritten records; checkpoint and history stay accurate |
| T10 | Legacy document missing new field or wrong BSON type | Reader handles cleanly or migration detects and blocks release |
| T11 | API receives MongoDB filter/operator outside allowlist | Request rejected; query never expands past granted permissions |
| T12 | Wrong secret, under-privileged DB user, or invalid TLS | Connection fails cleanly without logging secrets or bypassing TLS |
| T13 | List/aggregation queries across multiple tenants & large data | Appropriate indexes used, zero cross-tenant mix, latency within SLO |
| T14 | Restore backup into isolated environment | Data consistent, app reads cleanly, recovery time meets target |

In concurrency tests, synchronize thread start times to create genuine contention; sequential calls do not prove concurrency safety. For timeouts/failover, use fault injection or real failure environments; merely mocking a `MongoTimeoutException` does not verify commit uncertainty handling.

### Data Reconciliation Checks

Beyond integration tests, run invariant-checking reconciliation queries:

~~~javascript
// Detect duplicate idempotency keys within a tenant.
db.orders.aggregate([
  { $group: {
      _id: { tenantId: "$tenantId", key: "$idempotencyKey" },
      n: { $sum: 1 }
  }},
  { $match: { n: { $gt: 1 } } },
  { $limit: 20 }
]);

// Negative stock (must return 0 documents in this design).
db.inventory.find({
  $or: [
    { available: { $lt: 0 } },
    { reserved: { $lt: 0 } }
  ]
}).limit(20);
~~~

On large collections, schedule reconciliation queries with proper indexes, batching, and load caps. Full-collection aggregations belong in scheduled maintenance windows under controlled load. "Zero invalid records" must be verified across **the entire intended scope**, not just the first 20 documents after `$limit`.

## 11. Metrics, Alerting, and Operations Runbooks

In production, monitor **both application and MongoDB**, correlated via trace IDs or operation context:

| Metric / signal | Purpose |
| --- | --- |
| API latency p50/p95/p99, error rate | Detect degraded UX even when DB reports no errors |
| MongoDB query duration, slow queries, `docsExamined`/`keysExamined` | Catch poorly indexed queries or plan regressions |
| Connection pool wait, active connections, server selection timeout | Spot pool saturation or topology/network issues |
| Duplicate keys, optimistic locks, transaction retries | Separate normal contention from system errors and retry storms |
| Successful/failed reservations, unlinked orders | Detect threats to domain invariants |
| Replication lag, disk headroom, index size, CPU/I/O | Spot capacity and durability risks early |
| Outbox backlog, publish lag, duplicate handling | Track integration event delivery and recovery |
| Backup age, restore drills, migration state | Confirm recoverability and track release progress |

Every alert needs an **owner**, thresholds tied to real SLOs, a dashboard link, and an actionable runbook. For instance, if outbox backlog spikes, the runbook should guide inspecting publisher/broker health, checkpoints, retention, and idempotent replay—not merely "restart the service."

### Defining Recovery Targets

- **RPO (*Recovery Point Objective*)**: maximum acceptable data loss window during disaster recovery per business requirements.
- **RTO (*Recovery Time Objective*)**: maximum acceptable time to restore service to an operational state.

System owners must sign off on RPO and RTO and **validate them via restore drills**. Unverified backups do not prove deployment readiness. After restoring, reconcile data and coordinate recovery ordering across brokers, outboxes, and external systems.

## 12. Setting Verifiable GO/NO-GO Criteria

No single p95 threshold, connection count, or index size fits every system. In a capstone, propose **illustrative** targets (such as order-read API p95 under 200 ms at stated load), then replace them with project-approved SLOs. What matters is knowing at what load, on what dataset, and against which goals measurements were taken.

### Proposed Release Gates

| Gate | Minimum evidence | GO when | NO-GO when |
| --- | --- | --- | --- |
| **G1 – Correctness** | Tests D1–D8, concurrency tests, data reconciliation | All critical invariants PASS | Potential for duplicate orders, overselling, or unhandled data loss |
| **G2 – Security** | Cross-tenant tests, role/secret/TLS and log audits | Zero critical unauthorized access paths remain | Cross-tenant leaks, exposed secrets, or unchecked write privileges |
| **G3 – Migration** | Dry run, legacy data metrics, history/checksums, rollback/roll-forward test | Migration is safely rerunnable and data compatible | Destructive migration lacks verified recovery path |
| **G4 – Performance** | Load tests and `explain` for key queries | Approved SLOs met at target load with headroom | Timeouts, scans/sorts, or write costs exceed budget |
| **G5 – Recovery** | Recent backups, restore drill, measured RPO/RTO | Recovery meets targets cleanly | Cannot restore or missing mandatory data |
| **G6 – Operations** | Dashboards, alerts, safe logs, on-call/runbooks | Clear ownership and incident procedures exist | Cannot detect or respond to critical failures |

**Decision rule:** If any critical gate fails and lacks an explicit risk exception approved by an authorized owner, the decision is **NO-GO**. "NOT TESTED" must be distinguished from "PASS"; never infer safety from missing evidence. Approved exceptions require an expiration date, accountable owner, and mitigating controls.

### Readiness Sign-off Template

~~~text
Release: orders-service <version>
MongoDB deployment: <cluster/topology>, driver/Spring Data: <versions>
Scope: <APIs, collections, migrations, indexes, integrations>
Review timestamp: <UTC time>

G1 Correctness: PASS | FAIL | NOT TESTED  Evidence: <link/test id>
G2 Security:    PASS | FAIL | NOT TESTED  Evidence: <link/test id>
G3 Migration:   PASS | FAIL | NOT TESTED  Evidence: <link/job id>
G4 Performance: PASS | FAIL | NOT TESTED  Evidence: <dashboard/report>
G5 Recovery:    PASS | FAIL | NOT TESTED  Evidence: <restore drill>
G6 Operations:  PASS | FAIL | NOT TESTED  Evidence: <runbook/alert>

Open risks: <issue, severity, owner, deadline>
Decision: GO | NO-GO
Approved by: <responsible owner>
Rollback/roll-forward plan: <documented procedure>
~~~

Never record secrets, credentials, or real user data in readiness records. Link to access-controlled test and monitoring evidence instead.

## 13. Deployment and Recovery Runbook

A release sequence can follow:

1. **Pre-deploy:** verify recent backups and restore drill, assess migration risk, inspect existing indexes/validators, capture query and alert baselines.
2. **Expand:** deploy code compatible with both old and new schemas, prepare planned indexes, confirm all writers honor data contracts.
3. **Migrate:** execute versioned job with locks/checkpoints, monitor progress, verify record counts and invariants before advancing.
4. **Phased rollout:** shift canary/partial traffic if supported; monitor p95/p99, error rates, pool wait, conflicts, and integration backlogs.
5. **Post-deploy verification:** run tenant-scoped smoke tests, create/read order checks, minimal concurrency checks, schema/index checks, and key business metrics.
6. **Advance or halt:** finish rollout if gates hold; if a gate fails, halt expansion, drain traffic, and trigger the proper recovery path.
7. **Contract after stabilization:** drop legacy fields/indexes in a later release only after verifying zero active consumers remain.

A "rollback" plan must explicitly separate **what is reversible from what is not**. Redeploying older app binaries is safe only if they can still read the updated schema; committed transactions, emitted events, or external payments require compensation/reconciliation rather than code rollback. Only restore a production backup after weighing the impact on newer writes and downstream systems.

## 14. Final Capstone Submission Package

Learners assemble a **deployment evidence package** for the ordering service containing:

1. Request flow and collection diagrams, D1–D8 table with enforcement points and test IDs.
2. BSON samples, Spring Data mappings, live index lists, and `explain("executionStats")` results for critical queries.
3. Concurrency, idempotency, and transaction test results, including at least one duplicate request and one mid-flow multi-document failure.
4. Security report covering tenant isolation, MongoDB accounts, TLS, secrets, sensitive data, and log audits.
5. Versioned migration plan with rollback/roll-forward criteria and legacy data reconciliation evidence.
6. Load report, SLOs, alerts, RPO/RTO, restore drill results, and a signed GO/NO-GO decision record.

### Suggested Evaluation Rubric

| Category | Weight | Criteria |
| --- | ---: | --- |
| Data correctness | 35% | Clear invariants, enforced at proper layers, reliable concurrency and idempotency tests |
| Security | 25% | Cross-tenant isolation, least privilege, safe TLS/secrets, zero leaks in APIs/logs |
| Deployment readiness | 25% | Migrations, backup/restore, observability, actionable GO/NO-GO gates and runbooks |
| Evidence & justification | 15% | Real metrics, actual queries, tests, and system-appropriate trade-off explanations |

A passing design clearly distinguishes **which errors are stopped by MongoDB constraints, which require Spring Data/domain rules, and which require operational procedures**. `MongoTemplate`, repositories, transactions, indexes, and reactive APIs all play specific roles; true deployment readiness is proven only when those choices are verified together against real data, security boundaries, and recovery conditions.
