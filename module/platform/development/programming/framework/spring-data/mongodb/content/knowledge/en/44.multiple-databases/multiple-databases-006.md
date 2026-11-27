# Designing Indexes, Schema Validation, and Migrations for Multiple Tenants

In a **multi-tenant** system, multiple customers (tenants) share the same application, yet their data must be separated in terms of access control, reliability, and operability. With **SPRING_DATA_MONGODB**, the application uses `MongoClient`, `MongoDatabaseFactory`, `MongoTemplate`, or repositories to connect, map documents, query, and manage multiple MongoDB databases. As the number of tenants grows, **indexes**, **schema validation**, and **migrations** must be applied consistently to each tenant's exact database or collection.

This lesson belongs to the **Multiple databases** chapter. The focus is on how to design and deploy these three components without mixing data across tenants, avoiding conflicts during schema updates, and enabling tracking and safe re-execution when a migration fails.

## 1. Real-world problem and objectives

Suppose an order management platform serves two tenants:

- `north` stores data in the `commerce_north` database.
- `south` stores data in the `commerce_south` database.

Both have an `orders` collection, and each tenant is allowed to have an order with the same code `ORD-001`. The application needs to search orders by status and creation time, validate document structure, and upgrade the schema from version 1 to version 2.

After this lesson, learners will be able to:

1. Choose a tenant isolation strategy considering how it shapes index structure and unique constraint scope.
2. Design indexes for actual query patterns, avoid redundant indexes, and understand sharding constraints.
3. Configure MongoDB `$jsonSchema` validators on collections and handle invalid historical data.
4. Execute migrations in phases: backward compatibility, backfill, verification, and tightening validation.
5. Implement per-tenant operations via Spring Data MongoDB, test thoroughly, and diagnose operational issues.

## 2. Choosing a tenant isolation model

Not every multi-tenant system requires a separate database per tenant. Your storage choice determines the **scope** of indexes, validators, and migrations.

| Model | Example | Indexes and uniqueness | Schema validation and migrations |
| --- | --- | --- | --- |
| **Shared database, shared collection** | `app.orders` has a `tenantId` field | Query indexes should lead with `tenantId` where appropriate; unique indexes usually include `tenantId` and the business key | One shared validator for the collection; migrations filter by tenant if rolled out in batches |
| **Database per tenant** | `commerce_north.orders`, `commerce_south.orders` | Each database has its own indexes; `orderNo` is unique within one tenant's collection | Create/adjust validators and run migrations on **each tenant database** |
| **Cluster per tenant** | Tenant has a dedicated MongoDB deployment | Indexes and uniqueness are completely separated per deployment | Must coordinate migrations, connections, credentials, and MongoDB versions per cluster |

In the **Multiple databases** chapter, we primarily practice **database per tenant**. Two databases can reside on the same cluster. When sharing a cluster, credentials, and driver parameters, you can reuse **one `MongoClient`** and create factories/templates with different default databases. If tenants sit on different clusters or credential groups, manage the corresponding `MongoClient`s. Never create a new client per HTTP request.

Responsibility diagram:

```text
JWT / auth context -> tenant registry -> authorized tenantId
                                             |
                                             v
                                TenantTemplateResolver
                                             |
                        +--------------------+-------------------+
                        |                                        |
                 commerce_north                           commerce_south
                        |                                        |
                MongoTemplate N                          MongoTemplate S
                        |                                        |
                orders, indexes,                         orders, indexes,
                validator, ledger                        validator, ledger
                        +--------------------+-------------------+
                                             |
                                    Shared MongoClient
                                    (same deployment)
```

**Security principle:** the tenant must come from an authenticated/authorized identity checked against a tenant registry; never concatenate an arbitrary `tenantId` value from a URL or body into a database name. All business operations and migrations must pass through a controlled database selection mechanism.

## 3. Defining schemas and queries before designing indexes

For example, order document **v1**:

```javascript
{
  _id: ObjectId("65e000000000000000000001"),
  orderNo: "ORD-001",
  customer: "customer-17",
  status: "PAID",
  createdAt: ISODate("2026-01-10T10:00:00Z"),
  amountCents: NumberLong("259900")
}
```

Target schema **v2** renames `customer` to `customerId` and adds `schemaVersion`:

```javascript
{
  _id: ObjectId("65e000000000000000000001"),
  orderNo: "ORD-001",
  customerId: "customer-17",
  status: "PAID",
  createdAt: ISODate("2026-01-10T10:00:00Z"),
  amountCents: NumberLong("259900"),
  schemaVersion: NumberInt(2)
}
```

Product queries to support:

| Requirement | Typical query | Guarantee needed |
| --- | --- | --- |
| Find order by code | `find({ orderNo: "ORD-001" })` | Order code is unique **within each tenant** |
| List recently paid orders | `find({ status: "PAID" }).sort({ createdAt: -1 }).limit(50)` | Filter by status and return in chronological order |
| List a customer's orders | `find({ customerId: "customer-17" }).sort({ createdAt: -1 })` | After migration, query on the new field |
| Clean up expired temporary data | Queries/TTL on `sessions.expiresAt` | Clear retention policy; never delete data that must be preserved |

A good index must derive from filters, sorts, selectivity, read/write frequency, and data size. Do not index every field simply because it appears in the model. Indexes increase write cost, memory usage, disk space, and deployment time across **all tenants**.

## 4. Designing indexes for each tenant database

With database per tenant, an administrator or migration workflow selects each specific database and creates its indexes. The example below runs in `mongosh` with appropriate privileges.

```javascript
const tenantDb = db.getSiblingDB("commerce_north");

// Ensure each tenant has only one orderNo.
tenantDb.orders.createIndex(
  { orderNo: 1 },
  { name: "ux_orders_order_no", unique: true }
);

// Support status filtering and descending createdAt sorting.
tenantDb.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "ix_orders_status_created_at" }
);

// Create only after the application and backfill use customerId.
tenantDb.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  { name: "ix_orders_customer_created_at" }
);
```

Creating indexes in `commerce_north` **does not automatically apply** to `commerce_south`. Provisioning/migration tooling must run the same definitions on every database in scope. Use stable index names to identify and inspect status; if an existing index has the same name with different keys or options, re-creating it will fail with a conflict. When changing an index structure, typically create the new index under a new name, verify it, and only then drop the old index when safe.

### 4.1. Uniqueness and dirty data before creating unique indexes

Each collection has its own namespace, so `ORD-001` can appear once in `commerce_north.orders` and once in `commerce_south.orders`. A unique index on `orderNo` only prevents duplicates **within the current collection**.

Before deploying a unique index on a collection with existing data, check for duplicates:

```javascript
tenantDb.orders.aggregate([
  { $group: { _id: "$orderNo", count: { $sum: 1 } } },
  { $match: { count: { $gt: 1 } } },
  { $sort: { count: -1 } }
]);
```

Also handle documents **missing `orderNo` or having `null`**: a regular single-field unique index does not allow multiple documents with `null`/missing key values as many business systems expect. Fix the data or define a partial index matching the real constraint; never use a partial index merely to hide an unresolved data issue.

If business codes are case-insensitive, decide on a normalization policy or collation when creating the unique index; queries intending to use a collated index must match that collation.

### 4.2. Case where multiple tenants share a collection

If instead using `app.orders` with `tenantId`, indexes must reflect tenant scope:

```javascript
const sharedDb = db.getSiblingDB("app");

sharedDb.orders.createIndex(
  { tenantId: 1, orderNo: 1 },
  { name: "ux_orders_tenant_order", unique: true }
);

sharedDb.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "ix_orders_tenant_status_created_at" }
);
```

A unique index on `orderNo` alone would accidentally forbid two tenants from using the same order code. Every query, update, and delete on a shared collection must include a **tenant condition** controlled by the authorization layer; having a `tenantId` index prefix does not create a security boundary by itself.

For sharded collections, check unique index rules tied to the shard key: a unique index on a sharded collection normally requires the **shard key as a prefix** of the index; certain shard keys/indexes have specific restrictions. Never apply the template above verbatim to a sharded collection without checking the actual sharding configuration.

### 4.3. TTL, partial indexes, and performance measurement strategies

For temporary sessions (not orders that must be retained long-term), a TTL index can automatically remove expired records:

```javascript
tenantDb.sessions.createIndex(
  { expiresAt: 1 },
  { name: "ttl_sessions_expires_at", expireAfterSeconds: 0 }
);
```

`expiresAt` must be a valid BSON Date value. The TTL monitor deletes asynchronously, so documents do not disappear at the exact instant of expiration; enforce access and expiration checks in the application layer if immediate rejection is required. Never use TTL as a substitute for legal/compliance retention or controlled tenant deletion.

A partial index includes only documents matching `partialFilterExpression`, reducing index size in some scenarios. Queries aiming to use it generally need predicates compatible with the partial index filter. Never assume a smaller index is always faster.

To evaluate indexes against real queries:

```javascript
tenantDb.orders
  .find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(50)
  .explain("executionStats");
```

Inspect `winningPlan`, `IXSCAN`/`COLLSCAN`, `totalKeysExamined`, `totalDocsExamined`, execution time, and write latency. `IXSCAN` does not automatically mean a query is optimal; examine scanned documents, sorts, index coverage, and actual load. Very large tenants may require a different index set than small tenants, but every exception must be version-controlled.

## 5. Managing indexes with Spring Data MongoDB

With `MongoTemplate`, Spring Data MongoDB provides `IndexOperations` and `ensureIndex`. Use them during **per-tenant** provisioning/migration rather than creating indexes ad hoc on every request.

Java example:

```java
package com.example.multitenant.migration;

import org.springframework.data.domain.Sort.Direction;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.index.IndexOperations;

public final class OrderIndexInstaller {

    public void ensureIndexes(MongoTemplate template) {
        IndexOperations indexes = template.indexOps("orders");

        // Run only after duplicate orderNo values have been checked and resolved.
        indexes.ensureIndex(new Index()
                .on("orderNo", Direction.ASC)
                .unique()
                .named("ux_orders_order_no"));

        indexes.ensureIndex(new Index()
                .on("status", Direction.ASC)
                .on("createdAt", Direction.DESC)
                .named("ix_orders_status_created_at"));

        indexes.ensureIndex(new Index()
                .on("customerId", Direction.ASC)
                .on("createdAt", Direction.DESC)
                .named("ix_orders_customer_created_at"));
    }
}
```

To run for `north`, pass the template pointing to `commerce_north`; for `south`, pass the template pointing to `commerce_south`. The method above ensures the index definition exists by name/keys/options when no conflict occurs; it **does not** automatically inspect or fix data violating uniqueness, nor does it alter an existing index with differing options.

You can use `@Indexed` or `@CompoundIndex` on models, but **do not rely on auto-index creation by default when working with multiple databases**. Spring Data MongoDB disables auto-index creation by default in current versions; and even if enabled, you must ensure the right template, mapping context, and collection are targeted for each tenant. In production, a versioned and well-tested migration process provides better control over index changes.

## 6. Schema validation with MongoDB `$jsonSchema`

### 6.1. Defining schema v2

MongoDB supports collection-level JSON Schema validators with `$jsonSchema` syntax (MongoDB JSON Schema includes BSON types like `int`, `long`, `date`). Full example for `orders` v2:

```javascript
const ordersV2Schema = {
  bsonType: "object",
  required: [
    "orderNo", "customerId", "status",
    "createdAt", "amountCents", "schemaVersion"
  ],
  properties: {
    orderNo: {
      bsonType: "string",
      minLength: 1,
      description: "Required order code"
    },
    customerId: {
      bsonType: "string",
      minLength: 1
    },
    status: {
      enum: ["NEW", "PAID", "CANCELED"]
    },
    createdAt: {
      bsonType: "date"
    },
    amountCents: {
      bsonType: "long",
      minimum: 0
    },
    schemaVersion: {
      bsonType: "int",
      enum: [2]
    }
  }
};

const ordersV2Validator = { $jsonSchema: ordersV2Schema };
```

Meaning:

- `required` mandates field presence; `bsonType`/`enum`/`minimum` check concrete values.
- `amountCents` uses BSON `long` to store integer amounts in the smallest currency unit; the Java application can map it to `Long`. Never replace it with `double` when monetary precision is required.
- `schemaVersion` uses BSON `int`; application code and migrations must write the exact type, such as `NumberInt(2)`.
- A validator does not create unique constraints or indexes. Both a **validator** and a **unique index** are needed to enforce structure and uniqueness simultaneously.
- Not every field must appear in `properties`; to forbid unlisted fields, account for `_id` and `additionalProperties` rules carefully to avoid breaking valid documents or application mapping.

### 6.2. New collection: creating with a validator

If the collection does not exist yet and the application only writes schema v2:

```javascript
const tenantDb = db.getSiblingDB("commerce_north");

tenantDb.createCollection("orders", {
  validator: ordersV2Validator,
  validationLevel: "strict",
  validationAction: "error"
});
```

With `validationAction: "error"`, writes violating the validator are rejected (typically `DocumentValidationFailure`, code 121). `validationLevel: "strict"` applies validation to inserts and updates according to MongoDB rules. If the collection already exists, `createCollection` is not the command to change the validator; use `collMod` in the next section.

### 6.3. Live collection: rolling out the validator in phases

While v1 documents still exist, immediately enforcing `strict + error` can block valid writes/updates from legacy logic. Start with warning mode to observe:

```javascript
tenantDb.runCommand({
  collMod: "orders",
  validator: ordersV2Validator,
  validationLevel: "strict",
  validationAction: "warn"
});
```

`warn` permits writes while logging validation warnings for investigation. `strict` validates inserts and updates; depending on your transition strategy, `moderate` can be considered so updates to already-invalid old documents are not rejected once `error` is enabled. Understand that `moderate` does not guarantee all writes satisfy the target schema. Either way, you must backfill and count violating documents.

**Important:** changing a validator does not cause MongoDB to automatically scan or fix preexisting documents. To confirm all stored documents meet the rules, run an explicit verification query (section 8).

Once the application is v2-compatible and the violating document count is 0, switch to blocking mode:

```javascript
tenantDb.runCommand({
  collMod: "orders",
  validator: ordersV2Validator,
  validationLevel: "strict",
  validationAction: "error"
});
```

Both `createCollection` and `collMod` affect only the selected database. Commands run on tenant `north` do not change the validator of tenant `south`. Validator changes should be restricted to a migration account rather than letting normal application accounts modify schemas freely.

### 6.4. Shared collection schema and tenant limitations

With a shared collection, all tenants share **a single validator**. Multiple accepted document versions can be expressed using constraints (`oneOf`/`anyOf` within validator capabilities), though this increases complexity and prolongs compatibility windows. For tenants requiring long-term divergent schemas, evaluate separate databases/collections or conditional versioning rather than maintaining a massive validator that is hard to reason about.

A schema validator has no knowledge of the authenticated user, so it cannot prevent a request from writing into the wrong tenant's collection or database. Tenant isolation must still come from authorization, connection routing, and testing.

## 7. Schema migration v1 → v2 using expand–migrate–contract

Data migrations must account for live traffic and the possibility that different tenants are on different versions.

**Phase 0 — Preparation.** Inventory tenant count, server versions, collection sizes, existing indexes, percentage of v1 documents, and malformed data. Take backups and **verify restore capability**. Define the v2 specification, rollout order, load budgets, maintenance windows, and success/failure criteria. Pick a pilot group of tenants first.

**Phase 1 — Expand the application.** Release application code that can **read both `customer` and `customerId`**, while writing `customerId` and `schemaVersion = 2` for new records. Ensure read/write logic and indexes work while v1 and v2 data coexist. Never rename a Java field alone and assume historical MongoDB documents will convert themselves.

**Phase 2 — Observe schema.** Enable `collMod` with `validationAction: "warn"` per tenant to catch writes violating v2 structure. Confirm no old processes continue writing v1 documents (or build compatibility handling if needed).

**Phase 3 — Idempotent backfill.** Operate only on the selected tenant. Example for small/medium datasets:

```javascript
const tenantDb = db.getSiblingDB("commerce_north");

// Migrate v1 documents with a valid customer field to customerId.
const renameResult = tenantDb.orders.updateMany(
  {
    customerId: { $exists: false },
    customer: { $type: "string" }
  },
  [
    {
      $set: {
        customerId: "$customer",
        schemaVersion: NumberInt(2)
      }
    },
    { $unset: "customer" }
  ]
);

// Fill in schemaVersion for documents that already have customerId.
const versionResult = tenantDb.orders.updateMany(
  {
    customerId: { $type: "string" },
    schemaVersion: { $ne: NumberInt(2) }
  },
  { $set: { schemaVersion: NumberInt(2) } }
);

printjson({
  renamed: renameResult.modifiedCount,
  versioned: versionResult.modifiedCount
});
```

These two updates are conditional and can therefore be **safely re-run** if an error occurs mid-way; once converted, documents no longer match the rename predicate. However:

- Documents missing both `customer` and `customerId`, or having unexpected data types, must go to an exception list; never invent a dummy customer.
- `updateMany` is not an atomic transaction across all documents. For large collections, chunk by `_id` ranges or cursors, use `bulkWrite` with moderate batches, throttle load, and store checkpoints.
- If another process updates the same document during backfill, design concurrency rules or update guards to avoid overwriting changes. The example above assumes rollout already ensured writers use v2.
- Never convert monetary fields from `double` to `long` by multiplying by 100 and rounding arbitrarily; if legacy types exist, define an exact conversion specification and test monetary calculations thoroughly.

**Phase 4 — Verify and create v2 indexes.** Inspect data, reconcile counts, detect duplicate order codes, and verify both new fields and query results. Deploy unique indexes only after data satisfies the constraints. Before running on each tenant, estimate index build duration and load impact.

**Phase 5 — Contract.** Once data for all tenants in the release scope is valid and no v1 writers remain, switch the validator to `strict + error`; then remove legacy field-reading code and obsolete v1 indexes/logic. Never drop old fields or indexes until there is proof that both application code and data have transitioned completely.

These phases describe an **expand-then-contract process**, not an assumption that all tenants upgrade simultaneously. Each tenant should have its own migration status, verification timestamp, and deployment outcome.

## 8. Checking data cleanliness before tightening the validator

After backfill, check for unconverted v1 records:

```javascript
tenantDb.orders.countDocuments({
  $or: [
    { customerId: { $exists: false } },
    { schemaVersion: { $ne: NumberInt(2) } }
  ]
});
```

Count documents violating the **entire v2 schema** (including other fields like `amountCents` and `createdAt`):

```javascript
tenantDb.orders.countDocuments({
  $nor: [{ $jsonSchema: ordersV2Schema }]
});
```

The query above uses `ordersV2Schema` defined in section 6, so run it in the same `mongosh` session or reload the schema definition first. A count of 0 proves stored data met the validator during that scan; concurrent writes could still introduce discrepancies. Therefore, tighten to blocking mode once writers are controlled, and monitor write errors post-deployment.

Inspect current indexes:

```javascript
tenantDb.orders.getIndexes();
```

And verify target queries with `explain("executionStats")`. Mark a tenant complete only when data complies, indexes are in place, application reads/writes are stable, and rollback/remediation details are recorded.

## 9. Tenant routing in Spring Data MongoDB

### 9.1. One client, multiple MongoTemplates on the same deployment

The example below shows how to share one `MongoClient` across two databases. The tenant→database map is fixed for illustration; in production, load it from an authenticated tenant registry supporting controlled updates.

```yaml
app:
  mongo:
    uri: ${MONGODB_URI:mongodb://localhost:27017}
```

```java
package com.example.multitenant.config;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory;
import org.springframework.stereotype.Component;

@Configuration(proxyBeanMethods = false)
class MongoConnectionConfig {

    @Bean(destroyMethod = "close")
    MongoClient sharedMongoClient(
            @Value("${app.mongo.uri}") String uri) {
        return MongoClients.create(uri);
    }
}

@Component
public class TenantTemplateResolver {

    private static final Map<String, String> DEMO_DATABASES = Map.of(
            "north", "commerce_north",
            "south", "commerce_south"
    );

    private final MongoClient sharedClient;
    private final ConcurrentMap<String, MongoTemplate> templates =
            new ConcurrentHashMap<>();

    public TenantTemplateResolver(MongoClient sharedClient) {
        this.sharedClient = sharedClient;
    }

    public MongoTemplate forTenant(String authorizedTenantId) {
        String database = DEMO_DATABASES.get(authorizedTenantId);
        if (database == null) {
            throw new IllegalArgumentException(
                    "Unknown or unauthorized tenant");
        }

        return templates.computeIfAbsent(
                database,
                name -> new MongoTemplate(
                        new SimpleMongoClientDatabaseFactory(
                                sharedClient, name)));
    }
}
```

In this example, `authorizedTenantId` **must come from the authorization layer**; the resolver still checks that the tenant name exists in the registry. This layout fits a small, stable set of tenants; with thousands of tenants, an unbounded `MongoTemplate` cache can consume excessive mapping resources and memory. Evaluate bounded caches, registry governance, or dynamic database-selecting factories to limit instances while preserving explicit per-tenant configuration for converters, mapping, and indexes.

When using `@EnableMongoRepositories`, `mongoTemplateRef` binds a repository group to a **fixed template**. Such repositories do not switch databases per tenant at runtime. For dynamically selected tenants, use `MongoTemplate` via a controlled resolver or implement a dedicated factory/repository routing layer with context-isolation tests. Never store the current tenant in a global static variable or shared mutable state across requests.

### 9.2. Running migrations on the right template

A per-tenant index setup step can reuse `OrderIndexInstaller` from section 5:

```java
package com.example.multitenant.migration;

import com.example.multitenant.config.TenantTemplateResolver;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class TenantIndexMigration {

    private final TenantTemplateResolver resolver;
    private final OrderIndexInstaller installer;

    public TenantIndexMigration(TenantTemplateResolver resolver) {
        this.resolver = resolver;
        this.installer = new OrderIndexInstaller();
    }

    public void migrateOneTenant(String authorizedTenantId) {
        MongoTemplate template = resolver.forTenant(authorizedTenantId);

        // Run after data cleanup and before marking the migration
        // as completed in the migration ledger.
        installer.ensureIndexes(template);
    }
}
```

This snippet only illustrates the **index step** of a migration. Backfill, `collMod`, and ledger updates must be invoked separately by an orchestrator following section 7's order; never execute `migrateOneTenant` on every request. For many tenants, prefer a dedicated managed job with concurrency limits and logging keyed by logical tenant code.

### 9.3. Tracking migration versions per tenant

Keep a `schema_migrations` collection inside **each tenant database**. Example record:

```javascript
{
  _id: "orders_v2",
  status: "APPLIED",
  appliedAt: ISODate("2026-11-20T00:00:00Z"),
  sourceVersion: 1,
  targetVersion: 2,
  updatedCount: 18450,
  schemaChecksum: "sha256:..."
}
```

`_id` is the default unique key per collection, identifying a migration within one tenant. Record `APPLIED` **after** verifying data, indexes, validators, and critical queries. On failure, record the status and controlled retry/checkpoint details to resume from where it stopped. Do not rely solely on the ledger record to conclude the database is healthy if indexes/schemas might have been altered manually.

When multiple instances or job runners exist, use lease-based locking to prevent two workers from migrating the same tenant concurrently; when a lease expires, prevent the stale runner from continuing to write conflicting changes. Provisioning/migration commands need permissions to alter indexes and validators, whereas runtime application credentials should be restricted to business operations.

## 10. Testing and monitoring multi-tenant rollouts

### 10.1. Minimum test matrix

| Case | Expected outcome |
| --- | --- |
| Tenant `north` has `ORD-001` and `south` also has `ORD-001` | Both are valid in the database-per-tenant model |
| Writing two orders with duplicate `orderNo` into the same tenant database | Unique index rejects the duplicate record |
| Missing `customerId` when validator is `strict + error` | MongoDB rejects the write (typically code 121) |
| v1 data backfilled and migration re-run | No duplicate records created; schema v2 remains valid |
| Tenant not in registry or unauthorized | Request rejected before selecting a `MongoTemplate` |
| Repository/template uses the wrong database | Integration test detects tenant leakage or wrong target database |
| Network failure after migrating half of a tenant | Checkpoint/status allows safe re-execution |
| Index creation when an existing name has a different structure | Does not silently treat as success; requires an explicit index migration |

### 10.2. Testing against a real MongoDB environment

Use Testcontainers with MongoDB or an equivalent test environment. Create two tenant databases, run provisioning, insert v1/v2 documents, run the migration, and inspect `getCollectionInfos()`/`getIndexes()`, validators, and verification queries.

Basic verification snippet:

```java
MongoTemplate north = resolver.forTenant("north");
MongoTemplate south = resolver.forTenant("south");

assertEquals("commerce_north", north.getDb().getName());
assertEquals("commerce_south", south.getDb().getName());

assertTrue(north.indexOps("orders").getIndexInfo().stream()
        .anyMatch(i -> "ux_orders_order_no".equals(i.getName())));
```

The assertions assume JUnit 5 `assertEquals` and `assertTrue` are imported and migration has run. This test verifies wiring and index names; add actual insert/query tests to prove data does not cross tenant boundaries and that unique indexes and validators work properly. Two databases on the same cluster can still suffer misrouting if the tenant registry is wrong.

### 10.3. Organizing the rollout

A rollout should track explicit states, for example:

```text
PENDING -> RUNNING -> VERIFYING -> APPLIED
                  \-> FAILED_RETRYABLE
                  \-> FAILED_MANUAL_REVIEW
```

A deployment pipeline can:

1. Lock migration history and confirm the target tenant/database/cluster before each run.
2. Select a small canary tenant group, complete it, and monitor before expanding.
3. Limit concurrency for index builds and backfills to avoid exhausting I/O, CPU, or connection pools.
4. Track % of tenants completed, invalid document count, query latency, duplicate/validation errors, index progress, latency, and retry failures.
5. Block the contract phase if any tenant in the batch fails criteria; failed tenants must record status, cause, and recovery steps.

Rollbacks must distinguish **application rollback** from **data reversal**. After changing documents from `customer` to `customerId` and enabling the v2 validator, reverting to an app that only reads v1 can break even if the deployment rolls back. Keep backward-compatible code long enough; plan recovery via backup/restore or reverse migrations if truly viable, while accounting for new data created during the transition. Never bulk-drop indexes or validators just to force a rollback without evaluating impact.

## 11. Common errors and troubleshooting

| Symptom | Typical cause | Resolution |
| --- | --- | --- |
| Tenant A is fast, tenant B is slow for the same query | Index not deployed on B; different data distribution | Compare `getIndexes()`, `explain()`, and collection sizes per tenant |
| `E11000 duplicate key error` when creating unique index | Existing duplicate `orderNo` or multiple null/missing values | Inventory and clean data first; recheck unique scope |
| App hits error code 121 after schema upgrade | v1 writer or wrong BSON field type | Inspect validator, writer flows, format conversions, and compatibility plan |
| Re-running `createIndex` reports conflict | Same index name with different keys/options | Write a versioned index migration; create new/verify before dropping old |
| Some tenants still have `schemaVersion=1` after rollout | Tenant skipped, job failed, or old writer still running | Reconcile per-tenant ledger, continue backfill, and inspect running apps |
| Queries hit the wrong tenant's database | Unauthenticated tenant context or wrong resolver mapping | Source tenant from auth, registry allowlist, and run isolation tests |
| Backfill spikes system-wide latency | Batches too large or too many tenants running concurrently | Reduce batch size/concurrency, stagger runs, monitor I/O and write load |
| App rollback breaks reads/writes | v1 fields or compatibility logic removed too early | Keep the expand phase long enough; test rollback against a data copy |

## 12. Checklist before marking a tenant complete

- [ ] Tenant is authenticated; mapping points to the intended database and deployment.
- [ ] Actual queries measured; indexes match, unique scope is right, no duplicate/missing keys before creating unique indexes.
- [ ] v2 validator applied on the right collection; all historical documents verified.
- [ ] Backward-compatible code deployed, idempotent backfill run, exceptions handled.
- [ ] Switched to `strict + error` after data cleanup; post-deploy write errors monitored.
- [ ] Ledger, checkpoints, timestamps, document counts, and migration status stored per tenant.
- [ ] Cross-tenant isolation, duplicate key, invalid schema, retry, and rollback scenarios tested.
- [ ] `explain()` and metrics compared after index creation; changes stayed within load budgets.

**Remember:** In MongoDB, indexes and validators belong to a **collection within a specific database**, not to a Java class shared across all tenants. Therefore, the Spring Data MongoDB application must route to the right database, while the migration process must deploy, verify, and record outcomes **independently for each tenant**. Reading/writing via `MongoTemplate` or repositories is only safe when tenant boundaries, schemas, and indexes are managed consistently.

## References

- [Spring Data MongoDB — Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html)
- [Spring Data MongoDB — MongoTemplate](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html)
- [MongoDB — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB — $jsonSchema](https://www.mongodb.com/docs/manual/reference/operator/query/jsonSchema/)
- [MongoDB — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB — collMod command](https://www.mongodb.com/docs/manual/reference/command/collMod/)
- [MongoDB — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
