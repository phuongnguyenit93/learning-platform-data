# Explicit Index Management and the Risks of Auto-Index Creation at Startup

A Spring Boot application using **Spring Data MongoDB** can declare indexes directly on Java entities using `@Indexed` or `@CompoundIndex`. This approach is very convenient: developers can look at a class and see some of the query requirements and data constraints. Yet between **declaring intent** and **changing the actual index structure in MongoDB**, there is a critical operational gap.

Imagine an application running across 20 pods, with a `customer_accounts` collection holding 80 million documents. A developer adds:

```java
@Indexed(unique = true)
private String email;
```

and enables:

```yaml
spring:
  data:
    mongodb:
      auto-index-creation: true
```

When the new application version rolls out, multiple instances may attempt to create the index at startup. If existing data contains duplicate emails, creating the unique index fails. If the collection is very large, the index build can drive high CPU, I/O, and disk usage and elevate application latency. If the index definition differs from an existing index sharing the same name, MongoDB can report an **index options conflict**. If switched to a TTL index, eligible expired data may be deleted once the TTL monitor runs. What looked like a simple Java annotation change therefore turns into a **production database schema migration**.

This lesson, **"Explicit Index Management and the Risks of Auto-Index Creation at Startup"**, in the **Spring Data MongoDB** chapter analyzes how Spring Data discovers index metadata, how to create indexes proactively via `MongoTemplate`, the risks of auto-index creation, and a controlled index rollout workflow with pre-checks, post-checks, and rollback.

Three guiding principles throughout:

1. **Annotations express intent; actual indexes are MongoDB objects.** Never assume the two states are always in sync.
2. **Application startup and schema/index upgrades are two separate lifecycles.** Avoid letting every application pod perform DDL at startup.
3. **A good index must be safe for data, performance, and operations**, not merely make a single query faster.

> **Version note:** Starting in Spring Data MongoDB **3.0**, auto-index creation is no longer enabled by default. Properties, annotation attributes, and APIs can vary across Spring Data MongoDB and Spring Boot releases; verify against the official documentation for your exact version before deploying.

---

## 1. Why Must Indexes Be Managed as Part of the Schema?

MongoDB allows flexible document structures, but that does not mean database structure needs no management.

A MongoDB deployment has several elements that must remain consistent:

```text
Application source code
       │
       ├── Java entities (@Document, @Field, @Indexed)
       ├── Repository query methods
       ├── Aggregation pipelines
       ├── Mongotemplate queries
       └── Business rules
                    │
                    ▼
           Database schema contract
                    │
       ┌────────────┼────────────┐
       │            │            │
  Data shape     Indexes      Constraints
       │            │            │
       └────────────┼────────────┘
                    │
                    ▼
          MongoDB production data
```

Indexes serve two categories of responsibility:

- **Performance optimization**: supporting filters, sorts, ranges, pagination, and projections.
- **Invariant enforcement**: unique indexes prevent duplicate keys, and TTL indexes enforce retention policies.

Adding an index can touch every existing document in a collection; dropping an index can degrade performance or eliminate a uniqueness guarantee. Therefore, indexes form part of the **database contract** between the application and its data.

### 1.1. Problem Example

A collection:

```javascript
{
  _id: ObjectId("..."),
  tenantId: "TENANT-01",
  emailNormalized: "alice@example.com",
  status: "ACTIVE",
  createdAt: ISODate("2026-11-10T08:00:00Z"),
  lastSeenAt: ISODate("2026-11-14T03:00:00Z"),
  expiresAt: null
}
```

Queries:

```javascript
// Find account by tenant and normalized email
db.customer_accounts.findOne({
  tenantId: "TENANT-01",
  emailNormalized: "alice@example.com"
});

// List newest ACTIVE accounts
db.customer_accounts.find({
  tenantId: "TENANT-01",
  status: "ACTIVE"
})
.sort({ createdAt: -1 })
.limit(20);
```

Candidate indexes:

```javascript
{ tenantId: 1, emailNormalized: 1 }             // unique per tenant
{ tenantId: 1, status: 1, createdAt: -1 }        // hot query
{ expiresAt: 1 }                                // TTL if needed
```

Every index must have a **reason to exist** and a lifecycle plan.

## 2. Three Layers to Distinguish

In Spring Data MongoDB there are three layers:

| Layer | Example | Meaning |
|---|---|---|
| Entity metadata | `@Indexed`, `@CompoundIndex` | Index declaration in Java code |
| Index management API | `MongoTemplate.indexOps(...).ensureIndex(...)` | Request to MongoDB to create an index |
| MongoDB catalog | `db.collection.getIndexes()` or `listIndexes()` | Actual index state on the server |

For example:

```java
@Indexed(name = "idx_email")
private String emailNormalized;
```

This **does not prove** that the index `idx_email` exists in the database. If automatic index creation is disabled, the annotation remains in code while MongoDB has not necessarily created the index.

Conversely, an index created previously by a DBA can exist in MongoDB even if the entity has no matching annotation.

### 2.1. Questions That Must Be Answered Separately

1. Which indexes does the application **expect**?
2. Which indexes does MongoDB **currently have**?
3. Which process is **allowed to modify** indexes?
4. When a mismatch is detected, should the system fail, alert, or auto-remediate?
5. Who approves changes that affect data?

These form the foundation of explicit index management.

## 3. How Auto-Index Creation Works in Spring Data MongoDB

Spring Data MongoDB supports discovering index declarations on mapped entities and creating the corresponding indexes when auto-index creation is enabled.

Per behavior described in Spring Data documentation, when enabled:

- Indexes declared on initial entities can be processed when the application context starts.
- An entity accessed for the first time at runtime can also trigger resolution of its index metadata.
- Index creation depends on the mapping context, entity discovery, configuration, and database access.

When **disabled**, declaring annotations does not automatically trigger `createIndexes` operations on MongoDB.

### 3.1. Why Did Spring Data Change the Default in 3.0?

Enabling auto-index creation on every startup can cause unintended impacts on:

- Collections with existing data;
- Collection recovery or recreation flows;
- Data that violates unique constraints;
- Performance risks;
- Database administration workflows independent of the application;
- Multiple application instances deploying simultaneously.

That is why index creation should be treated as **a dedicated database structure management step**, rather than a side effect of deploying a service.

### 3.2. Defaults Are Not Permanent Guarantees

Check the exact versions of:

- Spring Boot;
- Spring Data MongoDB;
- Spring Data Commons;
- MongoDB Java Driver;
- MongoDB Server;
- Custom `MongoMappingContext` configuration;
- The actual `MongoTemplate`/`ReactiveMongoTemplate` in use.

If an application configures its own mapping context, behavior can differ from an application relying purely on Spring Boot auto-configuration.

## 4. Enabling or Disabling via Spring Boot Properties

On Spring Boot versions supporting this property, you can configure:

```yaml
spring:
  data:
    mongodb:
      auto-index-creation: false
```

Or in `application.properties`:

```properties
spring.data.mongodb.auto-index-creation=false
```

When enabled:

```properties
spring.data.mongodb.auto-index-creation=true
```

Spring Boot can configure index creation from mapping metadata through the corresponding auto-configuration.

### 4.1. Recommended Configuration for Production

A common setup:

```yaml
# application-prod.yml
spring:
  data:
    mongodb:
      auto-index-creation: false
```

Then create indexes through a **controlled migration job** instead of letting every API pod act on its own.

Do not apply this property blindly if your project overrides MongoDB configuration with custom beans. Confirm runtime behavior via configuration inspection and logs in a test environment.

### 4.2. Java Configuration via `AbstractMongoClientConfiguration`

Spring Data exposes an extension point for index creation when configuring MongoDB manually:

```java
import org.springframework.data.mongodb.config.AbstractMongoClientConfiguration;

public abstract class BaseMongoConfiguration
        extends AbstractMongoClientConfiguration {

    @Override
    protected boolean autoIndexCreation() {
        return false;
    }
}
```

The snippet illustrates **the method to override**, not a complete configuration: an actual subclass must also provide the database name and client according to the API of your version. Avoid creating multiple competing MongoDB configurations in the same context.

### 4.3. Do Not Rely on Developer Environments

If dev sets `auto-index-creation=true` while production sets `false`, an integration test in dev may succeed because the index appears automatically, whereas production will miss the index if migrations do not run.

You must **verify the index contract independently** of query tests returning correct results.

## 5. `@Indexed`: Declaring an Index on a Single Field

Entity example:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

import java.time.Instant;

@Document(collection = "customer_accounts")
public class CustomerAccount {

    @Id
    private String id;

    private String tenantId;

    @Field("email_normalized")
    @Indexed(name = "idx_email_normalized")
    private String emailNormalized;

    private String status;
    private Instant createdAt;

    // Constructor, getters, setters per application needs.
}
```

This defines a single-field index on `emailNormalized`, mapped to the physical field `email_normalized` per mapping metadata.

### 5.1. Java Field Names and BSON Field Names Can Differ

`@Field("email_normalized")` stores the field under a different key name. When declaring indexes through Spring mapping metadata, verify the **actual key** in MongoDB rather than assuming it matches the Java field name.

If creating indexes manually using a collection name and raw `Document`, you must specify the **physical BSON field names** yourself.

### 5.2. `@Indexed` Does Not Dictate Which Queries Use the Index

MongoDB's query planner selects plans based on query shape, selectivity, sort, and available indexes.

Simply adding the annotation does not guarantee:

- The query becomes faster;
- The planner chooses the index;
- `COLLSCAN` disappears;
- The index supports every sort order;
- The index does not slow down writes.

Use `explain("executionStats")` and measure read/write p95/p99.

## 6. `@CompoundIndex`: Designing for Query Shapes

Suppose a frequent query is:

```javascript
db.customer_accounts.find({
  tenantId: "TENANT-01",
  status: "ACTIVE"
})
.sort({ createdAt: -1 })
.limit(20);
```

Entity:

```java
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customer_accounts")
@CompoundIndex(
    name = "idx_tenant_status_created_desc",
    def = "{'tenantId': 1, 'status': 1, 'createdAt': -1}"
)
public class CustomerAccount {
    // Fields and methods omitted.
}
```

A compound index is usually preferable to three separate single-field indexes when the workload primarily filters by tenant/status and sorts by creation time.

### 6.1. Key Order Matters

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

is not equivalent for all queries to:

```javascript
{ createdAt: -1, tenantId: 1, status: 1 }
```

For equality predicates, sorts, and range queries, evaluate key ordering (such as the ESR heuristic) and benchmark against real data.

### 6.2. Index Prefixes

A compound index can assist queries filtering on its leading fields, yet it is not guaranteed to be optimal for a query filtering solely on `status` without `tenantId`.

Do not delete a single-field index simply because its field name also appears inside a compound index.

### 6.3. Repeatable Annotations

Spring Data supports declaring multiple compound indexes via repeatable annotations or `@CompoundIndexes` depending on version. However, **many index annotations do not automatically form a sound indexing strategy**. Each index requires a query shape, an owner, and a business justification.

## 7. Unique Indexes: Turning an Annotation into a Constraint

Suppose a requirement states: emails must be unique **within the same tenant**.

```java
@CompoundIndex(
    name = "uq_tenant_email",
    def = "{'tenantId': 1, 'emailNormalized': 1}",
    unique = true
)
```

MongoDB enforces uniqueness on that compound key whenever the index exists and data satisfies it.

### 7.1. Do Not Use a Global Unique Email Index If Tenants May Share Emails

Wrong if the same email is allowed across multiple tenants:

```java
@Indexed(unique = true)
private String emailNormalized;
```

This definition requires emails to be unique **across the entire collection**, not per tenant.

The right definition must reflect the business key, e.g., `(tenantId, emailNormalized)`.

### 7.2. Unique Does Not Auto-Fix Duplicate Data

Suppose the collection already contains:

```javascript
{ tenantId: "T-01", emailNormalized: "alice@example.com" }
{ tenantId: "T-01", emailNormalized: "alice@example.com" }
```

Attempting to build a unique index on those two fields will fail due to duplicate keys.

This is one reason **auto-index creation at startup** is hazardous: a new application deployment can immediately crash when connecting to an existing database containing unclean data.

### 7.3. Validation in Java Cannot Replace a Unique Index

A block like:

```java
if (!repository.existsByEmailNormalized(email)) {
    repository.save(customer);
}
```

suffers from a race condition:

```text
Request A checks: does not exist
Request B checks: does not exist
Request A inserts
Request B inserts
```

If uniqueness is mandatory, you need an actual unique index in MongoDB and proper duplicate-key exception handling.

## 8. Unique Indexes on Missing or Null Data

A common mistake is turning on:

```java
@Indexed(unique = true)
private String phoneNumber;
```

when most documents do not yet have a `phoneNumber`.

Standard unique indexes have specific rules regarding missing and `null` values. For example, a single-field unique index typically rejects multiple documents sharing a null/missing key value.

If the business rule is "only **valid provided** phone numbers must be unique", consider a **partial unique index**.

### 8.1. Define the Business Rule First

Questions to resolve:

- Is a missing phone treated differently from `null`?
- Does an empty string count as a phone number?
- Should numbers be normalized with country codes?
- Can a phone number be reused after soft-deleting an account?
- Is uniqueness per tenant or system-wide?
- Does uniqueness apply only to verified numbers or all entered numbers?

An index cannot infer these answers. Audit existing data and normalization rules before creating a unique index.

## 9. Partial Indexes: Restricting the Indexed Document Set

A partial index includes only documents matching a `partialFilterExpression`.

Example business rule:

> Normalized email must be unique among active accounts (`deleted: false`) within a tenant; soft-deleted accounts do not hold the lock.

Candidate MongoDB index:

```javascript
db.customer_accounts.createIndex(
  { tenantId: 1, email_normalized: 1 },
  {
    name: "uq_active_tenant_email",
    unique: true,
    partialFilterExpression: {
      deleted: false
    }
  }
);
```

Benefits:

- Smaller index footprint if many accounts are soft-deleted;
- Unique constraint applies only to records matching the filter;
- Lower write and storage overhead compared to indexing the entire collection.

### 9.1. Do Not Treat a Partial Index Like a Full Index

Query:

```javascript
db.customer_accounts.find({
  tenantId: "T-01",
  deleted: false,
  email_normalized: "alice@example.com"
});
```

can leverage the partial index per query planner rules. However, a query that does not restrict `deleted: false` may require records outside the partial index, so it cannot safely use that index and still return complete results.

### 9.2. Spring Data Index API

In Spring Data MongoDB, `Index` and `PartialIndexFilter` express a partial index:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.index.PartialIndexFilter;
import org.springframework.data.mongodb.core.query.Criteria;

Index index = new Index()
    .on("tenantId", Sort.Direction.ASC)
    .on("emailNormalized", Sort.Direction.ASC)
    .named("uq_active_tenant_email")
    .unique()
    .partial(
        PartialIndexFilter.of(
            Criteria.where("deleted").is(false)
        )
    );
```

When using class-based `indexOps(CustomerAccount.class)`, verify physical field name mapping in your Spring Data version and inspect the resulting index on the server.

### 9.3. Partial Unique Indexes Also Have Edge Cases

If an account transitions from `deleted: true` back to `deleted: false`, MongoDB must insert the key into the partial index; the update will be rejected if another active account already holds that key.

Creating a partial unique index does not clean existing data or guarantee that restore/reactivation updates will always succeed.

## 10. Sparse vs Partial: Do Not Confuse Them

Two options:

- **Sparse index:** generally indexes documents containing the indexed field per MongoDB/index-type rules.
- **Partial index:** indexes documents satisfying an explicit filter expression.

These are not equivalent:

```javascript
{ phoneNumber: { $exists: true } }
```

versus:

```javascript
{ verified: true, deleted: false }
```

If the business rule requires the second condition, `sparse` is not expressive enough.

Do not specify both `sparse: true` and `partialFilterExpression` on the same index, as MongoDB forbids combining those options.

## 11. TTL Indexes: Risk of Immediate Data Deletion After Creation

A TTL index is a special index enabling MongoDB to automatically remove expired documents over time.

Example `login_sessions` collection:

```javascript
{
  _id: "SESSION-001",
  userId: "U-101",
  expiresAt: ISODate("2026-11-14T06:00:00Z")
}
```

Index:

```javascript
db.login_sessions.createIndex(
  { expiresAt: 1 },
  {
    name: "ttl_expires_at",
    expireAfterSeconds: 0
  }
);
```

Here `expireAfterSeconds: 0` means the document becomes eligible for expiration once `expiresAt` is reached, per TTL semantics.

### 11.1. TTL Indexes Do More Than Optimize Queries

They establish a **data deletion policy**. Creating a TTL index on a collection containing millions of documents whose `expiresAt` is already in the past allows the MongoDB TTL monitor to begin deleting large volumes of data right after index creation.

Consequently, adding `@Indexed` with expiration options alongside auto-index creation is a **data retention** risk, not merely a performance change.

### 11.2. TTL Deletion Is Asynchronous

The TTL monitor does not guarantee a document disappears at an exact millisecond. Expired records may persist briefly until the background pass processes them.

Do not use TTL as a second-accurate scheduler or as your sole authorization control. Application logic must still check expiration at access time for security.

### 11.3. Defining a TTL Index via the Spring Data API

Explicit creation example:

```java
import java.time.Duration;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;

Index ttl = new Index()
    .on("expiresAt", Sort.Direction.ASC)
    .named("ttl_expires_at")
    .expire(Duration.ZERO);
```

Confirm the API/version and stored field type. Traditional TTL requires Date fields (or arrays of Dates) and a compatible single-field index; a `String` containing a timestamp does not automatically behave as a Date.

### 11.4. Do Not Change a TTL Period Like a Routine Annotation Tweak

If an existing TTL index has a 30-day period and needs to change to 7 days, editing the annotation **does not guarantee** the live MongoDB index updates automatically. Modifying TTL parameters requires dedicated administrative commands (`collMod` depending on server version) or a supported recreation procedure.

**Never blindly drop and recreate a TTL index**, as that can trigger a massive delete wave and heavy I/O/replication load.

## 12. Other Index Types Spring Data Can Describe

Spring Data MongoDB supports various annotations and index definitions depending on version, such as:

| Type | Purpose | Things to Watch |
|---|---|---|
| `@Indexed` | Single-field index, unique/TTL and options | Fails when existing data violates constraints |
| `@CompoundIndex` | Compound B-tree index | Key order, prefix, sort alignment |
| `@GeoSpatialIndexed` | Geospatial index | Geometry validity, index type |
| `@TextIndexed` | MongoDB text index | Not identical to MongoDB Search/Lucene |
| `@WildcardIndexed` | Dynamic document paths | Index bloat |
| `@HashIndexed` | Hashed index | Supports equality; limited for ranges |
| `Index`/`IndexDefinition` | Programmatic index creation | Allows explicit option specification |

Verify exact capabilities and annotation attributes against the Spring Data version you use.

### 12.1. MongoDB Search / Vector Search Differ from Database B-Tree Indexes

Atlas Search / MongoDB Search and Vector Search have their own index management mechanisms, formats, and lifecycles. Do not assume `@Indexed` or `MongoTemplate.indexOps().ensureIndex(...)` automatically provisions Search or Vector Search indexes.

If your system relies on `$search` or `$vectorSearch`, maintain a separate migration/manifest and account for indexing lag, Search Nodes, field mappings, and authorization.

## 13. Nested Objects, Maps, and the Mapping Context

Spring Data can extract index metadata from the entity model, though nested objects and `Map` structures follow specific rules.

Example:

```java
@Document(collection = "products")
public class Product {
    @Id
    private String id;

    private Map<String, Object> attributes;
}
```

Keys inside `attributes` may vary per tenant or product type.

### 13.1. Map Keys Are Dynamic Data

Do not assume a resolver will automatically index every key that might appear inside a `Map`. Doing so would be unpredictable and unbounded.

Spring Data index resolution has dedicated rules for map-like properties; wildcard indexing is an option when warranted. If queries only target `attributes.color`, a targeted index is typically cheaper and simpler to operate than indexing all `attributes`.

### 13.2. Nested Fields and Index Names

When entities embed nested classes or use `@Field`, index paths and names resolve according to mapping metadata and entity scope. When diffing desired vs actual indexes, inspect the **actual mapped BSON keys**.

### 13.3. Do Not Assume Every Java Class Is Scanned

A class carrying annotations that has not yet been registered in the Mongo mapping context or accessed at runtime may not yet have indexes created under auto-index lifecycles.

Maintain an inventory of entity types rather than treating current index counts as proof that every annotation has taken effect.

## 14. Managing Indexes Explicitly with Spring Data `MongoTemplate`

Key API:

```java
MongoTemplate#indexOps(...)
```

This returns `IndexOperations`, providing:

- `ensureIndex(IndexDefinition)`;
- `getIndexInfo()`;
- `dropIndex(...)`;
- Other version-dependent index management methods.

Example:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.index.IndexOperations;

public final class CustomerIndexDefinitions {

    public static void ensureLookupIndex(
            MongoTemplate template) {

        IndexOperations operations =
            template.indexOps(CustomerAccount.class);

        Index index = new Index()
            .on("tenantId", Sort.Direction.ASC)
            .on("status", Sort.Direction.ASC)
            .on("createdAt", Sort.Direction.DESC)
            .named("idx_tenant_status_created_desc");

        String name = operations.ensureIndex(index);

        System.out.println("Index name: " + name);
    }
}
```

### 14.1. What Does `ensureIndex` Actually Do?

Conceptually, this API asks MongoDB to ensure an index matching the given definition exists as supported by the server. It creates the index if absent, or succeeds as a no-op when MongoDB already has an equivalent index.

**It is not a full database schema diff/migration engine.** If an index with the same name exists with different keys or options, MongoDB can return a conflict error; it will not automatically alter unique, partial, TTL, or collation settings to match the new intent.

### 14.2. `indexOps(Class<?>)` vs `indexOps(String)`

```java
template.indexOps(CustomerAccount.class);
```

relies on entity mapping and collection metadata.

```java
template.indexOps("customer_accounts");
```

targets the named collection directly.

Especially when combining `@Field`, collection naming strategies, custom converters, and inheritance, inspect the actual mapped field names so you do not create indexes on the wrong BSON paths.

### 14.3. `ensureIndex` Is a Production Change

It can trigger an index build, consume CPU/disk/I/O, and fail. Never invoke it casually inside request handlers, controllers, or unbounded scheduled jobs.

## 15. Reading Index Metadata with Spring Data

One way:

```java
import java.util.List;
import org.springframework.data.mongodb.core.index.IndexInfo;

List<IndexInfo> indexes =
    template.indexOps(CustomerAccount.class).getIndexInfo();

for (IndexInfo indexInfo : indexes) {
    System.out.println(indexInfo.getName());
}
```

`IndexInfo` exposes metadata per API and version, though detailed diffing often requires inspecting `key`, `unique`, `partialFilterExpression`, `collation`, `expireAfterSeconds`, and other options.

### 15.1. Reading the Raw Catalog via the MongoDB Driver

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

MongoCollection<Document> collection =
    template.getCollection("customer_accounts");

for (Document spec : collection.listIndexes()) {
    // In production, redact sensitive metadata before logging.
    System.out.println(spec.toJson());
}
```

`listIndexes()` is read-only. Output may reveal data structures, field names, and sensitive business rules; store evidence in controlled locations.

### 15.2. mongosh

```javascript
db.customer_accounts.getIndexes();
```

An index document can look like:

```javascript
{
  v: 2,
  key: {
    tenantId: 1,
    email_normalized: 1
  },
  name: "uq_tenant_email",
  unique: true
}
```

**The definition on the server** is the authoritative proof that an index actually exists, not merely an annotation in source code.

## 16. Why Doesn't `ensureIndex` Replace Versioned Migrations?

Suppose release A has:

```javascript
{ tenantId: 1, email_normalized: 1 }
```

non-unique.

Release B wants:

```javascript
{ tenantId: 1, email_normalized: 1 }
```

unique.

A call to `ensureIndex` cannot silently transform an existing index into a unique one without preflight checks, data cleanup, and proper procedures. You may need to:

1. Check for duplicate keys.
2. Remediate duplicates per business policy.
3. Plan creating/modifying the index per server version support.
4. Verify backward compatibility across old and new app versions.
5. Execute a dedicated migration.
6. Verify unique enforcement.
7. Record migration history and close the change.

### 16.1. Changing `@Indexed(unique=false)` to `true` Is Not a Migration

The updated annotation merely declares the **desired** attribute. The old index in the database is not automatically replaced.

You must diff actual vs desired state and plan the transition.

### 16.2. Renaming an Index Is Not as Simple as Renaming a File

Changing:

```java
@Indexed(name = "idx_email_v1")
```

to:

```java
@Indexed(name = "idx_email_v2")
```

can either create a second index with the same keys/options or run into MongoDB's equivalent-index rules. Depending on server version and index type, do not assume the old index name will be dropped automatically.

### 16.3. Maintaining Equivalent Indexes Wastes Resources

Keeping two near-identical indexes increases disk footprint and write maintenance overhead even though the query planner only uses one. Inventory existing indexes and analyze overlap before adding a new one.

## 17. Why Shouldn't Every Pod Run DDL at Startup?

A deployment topology:

```text
                    Deployment rollout
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
           Pod A          Pod B        Pod C
              │            │            │
              ├── createIndex()...
              ├────────── createIndex()...
              └──────────────── createIndex()...
                           │
                           ▼
                   MongoDB collection
```

If every pod runs auto-index creation:

- All pods may issue concurrent create-index requests;
- If the index is absent, redundant coordination happens;
- If index options drift, conflict errors arise;
- Heavy index builds raise resource pressure;
- Startup and readiness probes degrade;
- An index migration failure can abort the entire application rollout;
- Old and new pods running together with differing definitions create hard-to-control drift and conflicts.

### 17.1. This Does Not Mean MongoDB Builds Three Identical Physical Copies

MongoDB detects equivalent index definitions when handling `createIndexes`; identical requests do not typically create three separate physical indexes. The primary risks are **concurrent DDL side effects, cross-version drift, and lack of orchestration**, not a literal claim that every pod creates its own separate index copy.

### 17.2. Startup and Readiness Have Different Meanings

An API service might be ready to serve requests yet stall during startup on an index build or crash on a duplicate key. Conversely, if the app ignores index creation errors and reports `READY`, queries may slow down or uniqueness may go unenforced.

Never conflate **API serving readiness** with **schema migration status** inside an ambiguous startup step.

### 17.3. Lazy Index Creation on First Entity Access

The risk is not confined to startup. With auto-index creation enabled, if a mapped entity is only touched by a rarely executed job, index creation can trigger **well after the app is online**.

This is why index lifecycles belong in explicit migrations rather than assuming all changes happen nicely during a startup window.

## 18. What Happens When Creating an Index on a Large Collection?

An index build must scan existing documents to extract keys, write the index structure, and replicate across topology members.

Potential costs include:

- Data scanning;
- CPU for key extraction and sorting;
- Disk I/O;
- Memory and temporary spill files;
- Disk headroom consumption;
- Replication and member coordination;
- Higher query and write p95/p99 latency;
- Long build durations;
- Unique failures if duplicates exist;
- Interaction with backups, balancing, or shard operations.

### 18.1. Do Not Equate Modern Builds with Legacy Full Collection Locks

MongoDB index build behavior varies by server release. Do not claim index builds always lock the entire collection from start to finish, nor that index builds have zero latency impact. Read the documentation for your exact server version regarding concurrent index builds, commit quorum, and locking phases.

### 18.2. Enough Disk for Normal Traffic May Not Suffice for an Index Build

If a volume has 3% free space left, an index build on a large collection may run out of temporary working space or permanent footprint.

Preflight checks must estimate index size and headroom, including room for rollback/rebuilds.

### 18.3. Never Build a Critical Index for the First Time During Peak Hours

If a new application release depends on an index, plan to **create and verify the index before routing dependent traffic**. Never force pods to boot and build it right at peak traffic.

## 19. Specific Risks with Unique Indexes

Unique index migrations commonly fail when:

1. Duplicate data accumulated over years of operation.
2. Many records have missing/`null` values.
3. Email casing or whitespace was not normalized.
4. Soft-deleted or archived accounts still hold keys.
5. Global uniqueness was declared instead of per-tenant uniqueness.
6. Live app writers keep inserting duplicates during the build.
7. A unique index on a sharded collection violates shard-key constraints.
8. Another index shares the name with different options.
9. Collation causes two strings to collide unexpectedly under business rules.

### 19.1. Finding Duplicates Before Migration

Read-only `mongosh` aggregation example in an authorized environment:

```javascript
db.customer_accounts.aggregate([
  {
    $match: {
      email_normalized: { $type: "string" }
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        email: "$email_normalized"
      },
      count: { $sum: 1 }
    }
  },
  {
    $match: {
      count: { $gt: 1 }
    }
  },
  {
    $limit: 100
  }
]);
```

This pipeline finds **a sample of duplicate groups** matching the illustrative rule. It can be resource-intensive on large collections; run it under a planned schedule with suitable filters/indexes and do not treat it as an exhaustive verification by itself. If uniqueness applies only to `deleted: false`, match that exact predicate.

### 19.2. Avoid Automated Deduplication Without a Business Policy

When two accounts share an email, the business may need to:

- Merge records;
- Designate a primary account;
- Notify users;
- Preserve audit history;
- Fulfill GDPR or data retention rules if applicable.

Never delete duplicates with `deleteMany()` just to force an index build to succeed.

### 19.3. Guard Write Paths During the Transition Window

If you clean up duplicates while an older app version continues writing unvalidated duplicates before the unique index completes, the migration can fail again. You may need phased deployments, application-level validation, migration gating, and unique enforcement at the end.

## 20. Specific Risks with TTL Indexes

Creating a new TTL index can trigger mass deletion of already-expired records.

Example:

```text
Collection sessions: 25 million documents
expiresAt in the past: 12 million documents
```

If a deployment enables both the TTL annotation and auto-index creation, the TTL monitor may immediately start purging 12 million documents, causing:

- Elevated delete throughput;
- Increased replication traffic;
- Heavy disk I/O and cache pressure;
- Degradation for concurrent queries;
- Data loss if the expiration rule was misconfigured.

### 20.1. Measure the Candidate Deletion Set First

Before creating a TTL index, count eligible documents:

```javascript
db.login_sessions.countDocuments({
  expiresAt: { $lte: new Date() }
});
```

This query can be expensive on large unindexed collections; run it in an appropriate preflight process. Beyond total counts, verify business retention policies for each session category.

### 20.2. Handling Large Backlogs of Expired Data

Plan controlled batch cleanup beforehand or alongside migration to prevent a sudden TTL deletion storm. Do not temporarily inflate `expireAfterSeconds` and forget to restore it.

### 20.3. TTL Does Not Replace Authorization Checks

An expired session must still be rejected by application logic even if the TTL monitor has not deleted the document yet.

## 21. Risks with Partial Indexes, Collations, and Index Options

Two indexes can share the same key pattern yet differ in:

- `unique`;
- `partialFilterExpression`;
- `sparse`;
- `collation`;
- `expireAfterSeconds`;
- `hidden`;
- Other version-specific options.

### 21.1. Collation Changes the Definition of Uniqueness

Suppose an application treats `"ALICE@example.com"` and `"alice@example.com"` as the same email.

A unique index with an appropriate collation enforces uniqueness differently from simple binary comparison.

However, verify:

- Locale and strength settings;
- Field normalization rules;
- Existing duplicates under the new collation;
- Driver and query collation alignment;
- Sort behavior;
- Index constraints.

Do not just add `.unique()` assuming case-insensitive uniqueness is achieved.

### 21.2. Partial Filter Changes Unique Scope

Changing the filter from:

```javascript
{ deleted: false }
```

to:

```javascript
{ status: "ACTIVE" }
```

alters which documents are governed by the unique constraint. This requires data auditing and business sign-off—do not treat it as a minor rename.

### 21.3. When an Index Shares a Name with a Different Definition

Never swallow `IndexOptionsConflict` and let the application keep running silently without alerts. If the new app depends on the new index while the database keeps the old one, correctness or performance regressions can occur.

## 22. Risks of Index Creation on a Sharded Cluster

In sharded MongoDB, a logical collection is distributed across shards.

```text
Spring Boot application
          │
          ▼
        mongos
          │
     ┌────┼─────┐
     ▼    ▼     ▼
   Shard A B     C
```

Creating an index impacts multiple shards, cluster resources, and metadata. Additionally:

- Unique indexes on sharded collections are restricted by shard-key rules.
- Indexes are created across the collection per sharded deployment semantics.
- Queries lacking the shard key still scatter-gather even with good indexes on every shard.
- Builds on individual shards may finish at different times.
- Chunk migrations or resharding interact with resources.
- Rollbacks must consider the entire cluster.

A Java annotation **lacks the context** to verify whether a unique constraint satisfies sharding topology rules. Preflight checks must verify MongoDB sharding/index rules for your exact server version.

## 23. Atlas vs Self-Managed: Division of Responsibility

| Area | Atlas | Self-Managed |
|---|---|---|
| Creating B-tree indexes | Via driver / Atlas workflows | Via driver / DBA workflows |
| Index lifecycle | App team / DBA remain responsible | App team / DBA |
| Monitoring | Atlas metrics/alerts depending on tier | Self-operated tools/observability |
| Storage headroom | Tier / cloud storage metrics | Disk / volume / container metrics |
| Replica topology | Atlas manages many details | Team orchestrates directly |
| Search indexes | API / Atlas Search workflows | Per supported Search deployment |
| Authorization | Database users / Atlas roles | MongoDB users / roles |
| Migration approvals | Defined by your organization | Defined by your organization |

A managed service **does not automatically design indexes for every query or clean up duplicate business data**.

If indexes are applied via a migration job, the migration identity needs sufficient privileges, whereas regular API pods should not hold index create/drop privileges.

## 24. Least Privilege: API Services Do Not Need DDL Privileges

Enabling auto-index creation requires granting index-creation privileges to the application runtime identity.

This encourages an anti-pattern:

```text
Public-facing API
   ├── Read customer data
   ├── Write customer data
   └── Create/drop database indexes
```

If the API service is compromised, DDL privileges could be abused to induce heavy load/disk pressure or alter schema constraints.

Better separation:

```text
API identity:
  read/write required collections
  no unnecessary index-admin privileges

Migration identity:
  createIndexes + related scoped DDL
  used only during migration windows

Operator identity:
  administrative access under approval
```

### 24.1. Not Every Migration Needs Root

Creating indexes on a few collections does not justify granting `root@admin`. Use custom roles or organization-approved scoped permissions to minimize blast radius.

### 24.2. Test in Staging Using Real Service Credentials

If staging runs as root while the production API user lacks `createIndex`, auto-index creation will fail on production deployment. Separating DDL from startup ensures service credentials never need those privileges.

## 25. Explicit Index Management Workflow

A recommended architecture:

```text
Source code / index manifest
           │
           ▼
Preflight / schema review
           │
           ├── Scan current indexes
           ├── Check data constraints
           ├── Check compatibility
           └── Estimate impact
           │
           ▼
Approved migration job
           │
           ├── Create new index
           ├── Verify index definitions
           ├── Verify business invariants
           └── Record migration version
           │
           ▼
Deploy application version
           │
           ▼
Observe SLO and query plans
           │
           ▼
Cleanup obsolete index in later change
```

Most importantly: **run migrations before the application depends on the index**, or follow an engineered backward-compatible rollout order. Never let new API pods migrate schemas simultaneously at startup.

## 26. Designing an Index Manifest

A team can store index intentions in version control, for example in YAML:

```yaml
database: commerce
collection: customer_accounts
indexes:
  - name: uq_tenant_email_active_v2
    keys:
      tenantId: 1
      email_normalized: 1
    unique: true
    partialFilterExpression:
      deleted: false

  - name: idx_tenant_status_created_desc
    keys:
      tenantId: 1
      status: 1
      createdAt: -1

owner: customer-platform
changeId: DB-INDEX-2026-041
```

This is an **illustrative team-defined manifest**, not an official file format parsed natively by Spring Data.

It should document:

- Index name;
- Exact key fields and sort order;
- Options: unique, TTL, partial, collation, hidden;
- Target collection;
- MongoDB/Spring versions;
- Business purpose;
- Supported query shapes;
- Risk level;
- Rollback plan.

### 26.1. Why Versioning Matters

An index can evolve across releases:

```text
v1: { tenantId, email }
v2: { tenantId, emailNormalized } unique
v3: partial unique for active accounts only
```

Without versioning, updating annotations erases the transition trail from v1 to v3.

## 27. Dedicated Migration Runner Instead of API `ApplicationRunner`

Some teams call `ensureIndex()` from a Spring `ApplicationRunner` embedded inside the API service itself:

```java
@Component
class IndexBootstrapRunner implements ApplicationRunner {
    // ...
}
```

While convenient at startup, it still couples the **DDL lifecycle to API deployment**. If 30 pods start, 30 runners may execute concurrently.

### 27.1. Recommended Pattern

Package within the codebase if desired, yet run via an **isolated migration task**:

```text
CI/CD
  │
  ▼
Migration approval
  │
  ▼
One-off Kubernetes Job / CLI task
  │
  ▼
MongoDB indexes verified
  │
  ▼
Roll out API pods
```

You are not forced into one specific migration framework. Versioned scripts or organization-approved tooling work well provided they support:

- Versioning;
- Locking/coordination when needed;
- Auditing;
- Preflight checks;
- Rollback planning;
- Idempotency;
- Post-creation verification.

### 27.2. Separating Execution Modes with Profiles

If shipped in the same Spring Boot artifact, isolate the runner under a dedicated profile:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Profile("mongo-index-migration")
@Component
public class MongoIndexMigrationRunner
        implements ApplicationRunner {

    private final MongoIndexMigrationService migrationService;

    public MongoIndexMigrationRunner(
            MongoIndexMigrationService migrationService) {
        this.migrationService = migrationService;
    }

    @Override
    public void run(ApplicationArguments args) {
        migrationService.applyApprovedMigrations();
    }
}
```

`MongoIndexMigrationService` is an **application service you implement**, not a built-in Spring Data class. Profiles are only an orchestration boundary: the migration job still needs its own identity, lock, deployment controls, and must not run alongside normal API pods.

### 27.3. A Profile Does Not Guarantee Singleton Execution

If two Kubernetes Jobs enable the same profile concurrently, both will run. Your orchestrator or distributed lease must guarantee single-writer coordination.

## 28. Example Migration Class Creating Two Indexes

Assuming `customer_accounts` collection and configured Spring mapping:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.index.IndexOperations;

public final class CustomerAccountIndexMigration {

    private final MongoTemplate template;

    public CustomerAccountIndexMigration(
            MongoTemplate template) {
        this.template = template;
    }

    public void apply() {
        IndexOperations ops =
            template.indexOps(CustomerAccount.class);

        Index emailUnique = new Index()
            .on("tenantId", Sort.Direction.ASC)
            .on("emailNormalized", Sort.Direction.ASC)
            .named("uq_tenant_email_v2")
            .unique();

        Index statusSort = new Index()
            .on("tenantId", Sort.Direction.ASC)
            .on("status", Sort.Direction.ASC)
            .on("createdAt", Sort.Direction.DESC)
            .named("idx_tenant_status_created_desc");

        ops.ensureIndex(emailUnique);
        ops.ensureIndex(statusSort);
    }
}
```

**This example only illustrates the API.** In production, calling `apply()` must follow:

1. Checking tenant/email duplicates.
2. Checking existing index names and options.
3. Confirming index build support.
4. Verifying storage and resource headroom.
5. Obtaining change approval.
6. Having monitoring and rollback ready.
7. Running postcondition verification against the actual spec.

Never call `apply()` inside a constructor or bean initialization hook.

### 28.1. Watch Out for Field Aliases

If the entity maps `emailNormalized` to `email_normalized`, verify the actual index key in the catalog. When absolute precision is needed, base migration scripts directly on the **decided BSON field names**.

### 28.2. Index Creation Does Not Belong Inside a Business Transaction

Index DDL carries distinct constraints and is generally not part of business transactions alongside order/payment writes. Never design "start transaction -> create index -> update 50,000 documents -> commit" as if it were a single atomic business unit.

## 29. Using `MongoPersistentEntityIndexResolver` as a Metadata Source

If you still want annotations as your declaration source without auto-creating indexes on every startup, Spring Data offers `MongoPersistentEntityIndexResolver` to **read index definitions from the mapping context**.

Conceptual example:

```java
import org.springframework.data.mongodb.core.index.IndexDefinition;
import org.springframework.data.mongodb.core.index.IndexOperations;
import org.springframework.data.mongodb.core.index.MongoPersistentEntityIndexResolver;

var mappingContext =
    mongoTemplate.getConverter().getMappingContext();

var resolver =
    new MongoPersistentEntityIndexResolver(mappingContext);

IndexOperations indexOps =
    mongoTemplate.indexOps(CustomerAccount.class);

for (IndexDefinition definition :
        resolver.resolveIndexFor(CustomerAccount.class)) {

    indexOps.ensureIndex(definition);
}
```

This keeps index declarations close to the domain model while **moving execution timing** into a controlled migration job. Adapt exact method signatures/overloads to your Spring Data version.

### 29.1. The Resolver Is Not a Migration Framework

The resolver discovers index metadata; it does not:

- Diff all options against the live catalog;
- Plan dropping obsolete indexes;
- Remediate duplicate data;
- Estimate build duration;
- Coordinate concurrent migration runners;
- Guarantee rollback;
- Version schema state;
- Verify postconditions.

If multiple app versions run simultaneously, differing entity annotations cause drift. You need a **versioned desired-state contract**.

### 29.2. Do Not Blindly Scan Every Entity Across Special Scopes

A package may hold entities targeting multiple databases or dynamic tenant collections. Running the resolver over all entities indiscriminately can create indexes in the wrong place.

Define the migration's collection/database scope and enforce an allowlist.

## 30. Preflight: Comparing Desired Indexes Against Actual Indexes

Before migrating, gather two sets:

```text
Desired indexes (source/manifest)
            │
            ▼
     Normalize definitions
            │
            ├── key pattern + order
            ├── name
            ├── unique
            ├── partial filter
            ├── TTL
            ├── collation
            └── other options
            │
            ▼
Actual indexes (listIndexes)
            │
            ▼
       Compare
            │
     ┌──────┼───────────┐
     ▼      ▼           ▼
   MATCH  MISSING    CONFLICT
     │      │           │
     │      ▼           ▼
   PASS   APPROVE     BLOCK RELEASE
          CREATE      + DESIGN MIGRATION
```

Never turn a `CONFLICT` into an automatic drop-and-recreate command.

### 30.1. Compare Semantically, Not by Raw JSON String

MongoDB includes server-generated metadata fields (`v`, `ns`, etc.) and defaults that may be omitted from specs. Normalization must compare **key-pattern and option semantics**, not raw JSON formatting or unrelated key ordering.

However, **field order inside the index key pattern** IS meaningful; never sort key-pattern fields alphabetically during normalization or you will erase compound index ordering.

### 30.2. MISSING Does Not Always Mean "Create Immediately"

If an index is missing on a large collection, verify:

- Data constraint checks;
- Performance/capacity estimates;
- Permissions;
- Change window;
- Approvals;
- Ownership;
- Fallback plan.

### 30.3. ORPHAN / EXTRA Indexes

An existing index absent from the manifest might be:

- A legacy index slated for removal;
- An index created by a DBA;
- A unique/TTL index serving another policy;
- A rarely run reporting/DR index;
- An index managed by a different release.

Never automatically drop "unlisted" indexes. Audit ownership and query usage first.

## 31. Migration History Records

A migration tracking collection might look like:

```javascript
{
  _id: "mongo-index-2026-041",
  collection: "customer_accounts",
  state: "COMPLETED",
  appliedAt: ISODate("2026-11-14T04:00:00Z"),
  definitionHash: "sha256:...",
  appliedBy: "migration-job",
  changeId: "DB-INDEX-2026-041"
}
```

This is an example **application-designed internal schema**. An actual migration framework may use a different collection or format.

### 31.1. When Should `COMPLETED` Be Recorded?

Only after:

- MongoDB confirms the index creation/build finished per deployment semantics;
- The actual index specification has been read back;
- Postconditions pass;
- No conflicts exist;
- Associated data constraints are verified.

Never write the completion marker before `ensureIndex`, because the job could crash after recording completion yet before the index exists.

### 31.2. Crashing After Index Creation Before Writing the Marker

This requires **safe resumability**:

```text
ensureIndex success
       │
    Job crashes
       │
Migration record not COMPLETED
       │
       ▼
Next run:
  inspect actual index
  if exact desired spec exists -> mark completed
  else -> handle conflict / resume according to policy
```

This is why migrations must be idempotent at the **desired-state level** rather than blindly re-running commands regardless of catalog state.

### 31.3. A Migration Marker Does Not Prevent Races

If two jobs read `PENDING` concurrently and proceed, a status document alone is not a distributed lock. Use external orchestration or a lease with expiry/fencing when concurrent executors are possible.

## 32. Separating Database User Privileges

A clean privilege model:

| Identity | Required Privileges | Should NOT Have |
|---|---|---|
| API service | CRUD on business collections | `createIndex`, `dropIndex`, user admin |
| Index migration job | Index DDL on scoped DB/collections | Cluster-wide `root` unless required |
| Monitoring service | Read-only status/metrics | Write access to customer data |
| Backup agent | Backup/restore privileges per tool | Broad business write access |
| DBA break-glass | Audited administrative privileges | Used as routine API credentials |

Once API startup no longer builds indexes, the service account can drop `createIndex` by design—a substantial security improvement.

### 32.1. Run Migrations with Dedicated Secrets

Do not embed long-lived admin credentials into standard application configs. Issue time-bounded migration credentials via a secrets vault or workload identity and revoke them afterward.

### 32.2. Audit Who Changed Indexes

Maintain a clear trace:

```text
Change ID
DB/collection/index name
Executor identity
Timestamp
Desired spec hash
Before/after evidence
Approval
Outcome
```

Never log raw credentials or connection strings.

## 33. Deployment Sequencing: Expand -> Migrate -> Switch -> Contract

Example replacing an old email index with a new one:

```text
Release N: app uses legacy email
              │
              ▼
Expand:
  add emailNormalized field; app writes both
              │
              ▼
Backfill:
  normalize historical data with revision guard
              │
              ▼
Preflight:
  check duplicates / normalization
              │
              ▼
Index migration:
  create uq_tenant_email_normalized
              │
              ▼
Switch:
  app queries/validation use emailNormalized
              │
              ▼
Observe:
  measure correctness / performance
              │
              ▼
Contract:
  drop legacy index in a later release
```

### 33.1. Do Not Drop the Old Index Before the New App Is Ready

During a rolling deployment, older pods still running may rely on the legacy index. Dropping it prematurely triggers p99 spikes, timeouts, and CPU saturation.

### 33.2. Concurrent Writes During Backfill

If a backfill reads a stale document and writes `emailNormalized`, it may overwrite a fresh value written concurrently by the app. Use revision/conditional update guards and dual-write/CDC policies as needed.

### 33.3. Contract Is a Separate Change

Schedule dropping the old index only after confirming all clients/queries have switched and no rollback path still depends on it. Never bundle creating the new index and dropping the old index into one irreversible step.

## 34. Handling Index Name Conflicts

A conflict scenario:

```text
Existing index:
  name: idx_status_created
  key: { status: 1, createdAt: -1 }

Desired:
  name: idx_status_created
  key: { tenantId: 1, status: 1, createdAt: -1 }
```

Changing the key structure while reusing the same name causes a creation conflict.

### 34.1. Do Not Automatically Drop the Old Index Name

If you immediately run:

```javascript
db.customer_accounts.dropIndex("idx_status_created");
```

older queries may lose their index. Instead:

1. Give the new index a clear versioned/scoped name.
2. Create the new index deliberately.
3. Verify query plans.
4. Switch the application.
5. Observe behavior.
6. Drop the old index under separate approval.

### 34.2. Keep Names Stable and Descriptive

Example naming convention:

```text
uq_tenant_email_active_v2
idx_tenant_status_created_desc
ttl_session_expires_at
idx_geo_store_location
```

You do not need to encode everything into the name, yet it should convey purpose and avoid accidental collisions.

### 34.3. Do Not Use Index Names as Business Keys

Index names are administrative metadata; never expose them to frontends as business identifiers. If code uses `hint("idx_...")`, renaming an index directly affects those queries and must be reviewed.

## 35. Hidden Indexes to Test Safe Removal

Depending on server version, MongoDB supports **hidden indexes** so the query planner ignores an index without dropping its structure.

Example **state-changing command, run only when approved**:

```javascript
db.customer_accounts.hideIndex("idx_tenant_status_created_desc");
```

While hidden:

- The planner cannot select the index;
- Even `hint()` cannot force its use;
- The index **is still maintained on writes**;
- The index **still consumes storage**;
- Unique constraints remain enforced if unique;
- TTL expiration still runs if it is a TTL index.

### 35.1. Hiding Does Not Measure Write Throughput Gains from Dropping

Because a hidden index still incurs write maintenance:

```text
Before hide:
  Reads use index; writes maintain index.

After hide:
  Reads cannot use index; writes still maintain it.

After drop:
  Reads cannot use index; writes no longer maintain it.
```

A hidden test evaluates **read regression** prior to dropping, not how much write throughput improves after dropping.

### 35.2. Never Hide or Drop the `_id` Index

The `_id` index follows special server rules and cannot be managed like a secondary index.

### 35.3. Hiding Is Still DDL

`hideIndex`/`unhideIndex` alters query planner choices and can induce `COLLSCAN` spikes. Never treat it as a harmless read-only command in production.

## 36. Measuring Index Usage Before Dropping

In `mongosh`, inspect:

```javascript
db.customer_accounts.aggregate([
  { $indexStats: {} },
  {
    $project: {
      name: 1,
      key: 1,
      host: 1,
      accesses: 1
    }
  }
]);
```

`$indexStats` reports index usage counts per MongoDB semantics and node scope.

### 36.1. Zero Accesses Does Not Prove an Index Is Useless

Reasons include:

- Recent server restart;
- Newly built index;
- Periodic batch job has not run yet;
- Index is used on a secondary or another node;
- Key tenant has not sent traffic yet;
- Index enforces uniqueness or TTL;
- Index only matters during failover;
- Observation window was too short.

Never drop an index solely because `accesses.ops=0` over a single day.

### 36.2. Watch the `since` Timestamp

Reading:

```text
accesses.ops = 0
accesses.since = 5 minutes ago
```

is completely different from:

```text
accesses.ops = 0
accesses.since = 90 days ago
```

Counters reset on restart or index operations. In replica sets and sharded clusters, inspect all relevant nodes/shards.

### 36.3. Combine Query Plans and Metrics Before Deciding

Evaluate together:

- `getIndexes()`;
- `$indexStats`;
- `explain("executionStats")`;
- Slow query patterns;
- Read/write p95/p99;
- Index size;
- CPU, I/O, and working set size.

A rarely used index that prevents a critical admin query from scanning hundreds of millions of documents may still be worth keeping.

## 37. Index Contract Testing: Verifying the Actual Catalog

An integration test can query `MongoTemplate`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.IndexInfo;

class CustomerAccountIndexContractTest {

    @Autowired
    MongoTemplate template;

    @Test
    void shouldHaveRequiredIndex() {
        List<IndexInfo> infos =
            template.indexOps(CustomerAccount.class)
                    .getIndexInfo();

        assertThat(infos.stream()
            .map(IndexInfo::getName))
            .contains("uq_tenant_email_v2");
    }
}
```

This snippet is a **test skeleton**; running it requires project test framework dependencies, MongoDB connectivity, and fixture lifecycle setup.

### 37.1. Checking Index Name Alone Is Not Enough

An index sharing the expected name could have wrong keys or options during a migration conflict. A thorough contract test compares:

```text
name
key pattern and order
unique
partialFilterExpression
expireAfterSeconds
collation
hidden / other relevant options
```

Use `listIndexes()` to inspect the raw catalog and normalize specs.

### 37.2. Test Against Real MongoDB When Verifying Index Behavior

A mocked `MongoTemplate` can return a fake list, yet proves nothing about MongoDB enforcing uniqueness, TTL, or collations.

Testcontainers or a managed MongoDB test cluster verifies:

- Duplicate-key enforcement;
- Index build failures;
- Actual index catalog;
- Partial unique semantics;
- TTL expiration behavior over test windows;
- Query explain plans.

For sharded topologies, a standalone test container does not validate sharded unique-index/shard-key rules.

### 37.3. Never Test Against Production Data

Integration tests should create isolated test collections, clean up afterward, and never use production credentials.

## 38. Verifying That Auto-Index Creation Is Disabled

In the target environment, verify:

1. Effective production configuration sets `auto-index-creation=false`.
2. The API identity needs no DDL privileges.
3. Application startup performs no unintended index creation.
4. The migration job is the sole source of approved DDL.
5. Index contract tests verify indexes exist prior to API rollout.

### 38.1. Do Not Just Grep YAML

Spring Boot enforces configuration precedence: environment variables, CLI flags, active profiles, external configs, and custom beans can override YAML. Seeing `false` in a YAML file does not prove the runtime mapping context disabled auto-creation.

### 38.2. Verify Runtime Behavior Safely

In staging, use controlled logging/auditing or read-only catalog inspection before and after startup. Avoid logging raw secrets or enabling overly broad profiling.

### 38.3. What If You Use `ReactiveMongoTemplate`?

Spring Data Reactive has different APIs and lifecycles from blocking `MongoTemplate`; never copy blocking snippets directly onto an event loop. Separate migration workflows can use an appropriate driver/client and await completion through controlled subscription mechanics.

## 39. Failure Scenario 1: Application Restart Fails Due to Duplicates

Scenario:

```text
Release 1: no unique email index
Release 2: adds @Indexed(unique=true)
Auto index creation: true

Production data:
  User A: email = "alice@example.com"
  User B: email = "alice@example.com"
```

When the new application boots, unique index creation fails.

### 39.1. What NOT to Do

- Do not delete one duplicate account arbitrarily;
- Do not temporarily grant `root` to the API;
- Do not suppress errors just to turn deployment status green;
- Do not ignore the error and assume the constraint is enforced.

### 39.2. Proper Remediation Process

1. Pause the rollout.
2. Keep the compatible previous version serving traffic.
3. Clarify the business rule for uniqueness.
4. Export duplicate groups within the target scope.
5. Execute owner-approved data remediation.
6. Backfill/normalize if needed.
7. Build the unique index via an approved migration.
8. Verify unique enforcement.
9. Roll out the new application version.
10. Monitor and close the incident/finding.

## 40. Failure Scenario 2: Slow Rollout Caused by Index Build

Scenario:

```text
Collection: 100 million documents
New index annotation: { tenantId: 1, createdAt: -1 }
Pods: 25
auto-index-creation: true
```

During rolling rollout:

- Startup duration climbs;
- Database disk I/O spikes;
- Read/write p99 degrades;
- Several pods fail readiness probes;
- Kubernetes restarts pods repeatedly, adding rollout noise.

### 40.1. Distinguish the Root Causes

Twenty-five pods do not make MongoDB build 25 separate physical indexes. Still, building one real index on a large collection can saturate resources, while 25 concurrent clients complicate coordination and log analysis.

### 40.2. Prevention

- Pre-create the index in a migration window;
- Monitor CPU, disk, and build progress;
- Wait until the index is ready;
- Then roll out the application;
- Keep DDL detached from app readiness;
- Define alerts and stop conditions.

## 41. Failure Scenario 3: Index Unchanged Despite Editing the Annotation

Old code:

```java
@Indexed(name = "idx_email", unique = false)
private String email;
```

New code:

```java
@Indexed(name = "idx_email", unique = true)
private String email;
```

The application restarts, yet the MongoDB index remains non-unique or the build errors out with a conflict.

**Lesson:** editing a Java annotation does not upgrade an existing index when options conflict. Transition explicitly with a dedicated migration, clean data, and postcondition checks.

## 42. Failure Scenario 4: TTL Accidentally Deletes Historical Data

An archival entity has:

```java
// Illustrative TTL declaration; verify semantics/version.
@Indexed(expireAfterSeconds = 0)
private Instant archivedAt;
```

If the business intended to retain records indefinitely, placing a TTL index on `archivedAt` immediately makes historical records eligible for purge.

### 42.1. Questions to Verify

- Which field actually holds the expiration timestamp?
- How long is the retention window?
- How many existing records qualify for deletion?
- Will the purge trigger a massive delete throughput spike?
- Do backups and recovery points exist?
- Have legal and compliance approved?

In newer Spring Data releases, certain TTL annotation attributes may evolve; what governs data survival is **actual MongoDB server TTL semantics**, not just Java attribute names.

## 43. Failure Scenario 5: Staging Has the Index, Production Misses It

In dev:

```properties
spring.data.mongodb.auto-index-creation=true
```

In production:

```properties
spring.data.mongodb.auto-index-creation=false
```

A repository query flies in dev because the annotation auto-created the compound index. Production skipped migrations, so the query degrades into a `COLLSCAN`.

### 43.1. How to Prevent It

- Every release carries a list of required index specs.
- CI and staging run the exact same migration workflow.
- Contract tests inspect the index catalog.
- Production preflight verifies indexes before app rollout.
- Slow queries and query plans are monitored.
- Never assume entity annotations generate indexes everywhere.

## 44. Failure Scenario 6: Multiple App Versions With Divergent Index Metadata

During a rolling rollout:

```text
Old pods: @CompoundIndex(name="idx_v1", def="...")
New pods: @CompoundIndex(name="idx_v2", def="...")
```

If both enable auto-index creation, the database may end up holding both `v1` and `v2` or rejecting conflicting creations. If you roll back the app, expected metadata diverges again.

### 44.1. Better Approach

- The migration job owns index state;
- Both old and new apps remain compatible during the overlap window;
- Create the new index first;
- Deploy the new app;
- Observe metrics;
- Drop the old index in a subsequent release;
- Never let old pod startups "recreate" retired indexes.

## 45. Planning Rollback for an Index Change

No single rollback fits every index change.

| Change | Feasible Rollback? | Risks |
|---|---|---|
| Add performance index | Drop index after review | Query plan regression, maintenance, resources |
| Hide index | Unhide index | Slow queries while hidden |
| Drop index | Recreate index | Rebuild takes time and disk headroom |
| Add unique index | Drop only if approved | Loss of invariant, duplicate accumulation |
| Add TTL index | Drop/modify per runbook | Deleted data **cannot return automatically** |
| Change partial filter | New migration | Unique scope and data semantics shift |
| Change collation | New migration | Query matching and uniqueness change |
| Modify shard-related index | Restricted by sharding | May not be directly reversible |

### 45.1. Code Rollback Is Not Data Rollback

If a TTL index purged 2 million documents, reverting the Java annotation **does not bring back** those 2 million documents. If a unique constraint was dropped, duplicates inserted in the meantime can block rebuilding the unique index.

Use backups, approval gates, and assess irreversible consequences first.

### 45.2. Rebuilding an Index Is Not Instantaneous

If an index on a large collection is dropped by mistake, rebuilding it requires substantial time and resources; never define RTO assuming `createIndex()` finishes in seconds.

## 46. Index Size and Write Cost

Every index adds storage footprint and write-maintenance overhead.

Suppose a system has:

```text
Collection size: 40 GiB
Total index size: 26 GiB
Writes: 3,000/s
```

Adding compound indexes indiscriminately for "one index per query" expands total index size, working set demand, and write I/O dramatically.

### 46.1. Inspect Index Statistics

In `mongosh`:

```javascript
db.customer_accounts.stats({
  scale: 1024 * 1024
});
```

Inspect `totalIndexSize`, `indexSizes`, and `nindexes` per server output and version.

### 46.2. Indexes Are Not the Entire Disk Budget

The storage engine, journal, metadata, snapshots, oplog/logs, and backups consume space too. Plan capacity across the whole cluster, including replica set members.

### 46.3. Optimize for Hot Queries

Every new index should be backed by:

```text
Query shape
Frequency
Read p95/p99
Docs/keys examined
Expected benefit
Write penalty
Disk size
Operational owner
```

Do not index every Java field just so every repository method has its own dedicated index.

## 47. MongoDB Query Plans Verify Performance

Query:

```javascript
db.customer_accounts.find({
  tenantId: "T-01",
  status: "ACTIVE"
})
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");
```

Inspect:

- `winningPlan`;
- `IXSCAN`/`COLLSCAN` or corresponding stages;
- `totalDocsExamined`;
- `totalKeysExamined`;
- `nReturned`;
- `executionTimeMillis`;
- Blocking sorts;
- Memory/disk spill behavior under workload.

### 47.1. `explain` Does Not Replace Load Testing

A single `explain` call does not reflect driver connection pool waits, network RTT, concurrent writes, cache warmth, or production p99 traffic.

### 47.2. Creating an Index Does Not Guarantee the Planner Selects It

The query planner weighs selectivity, sort efficiency, and data skew. If a query still chooses the old plan after creating an index, analyze the plan instead of blindly stacking more indexes.

## 48. Designing Dry-Run Migrations

A migration tool can expose two modes:

```text
DRY_RUN:
  read desired specs
  read actual specs
  compute differences
  validate permissions/capacity
  output plan
  NO write operations

APPLY:
  require approval/change ID
  acquire migration ownership
  execute steps
  verify postconditions
  record migration result
```

### 48.1. A Dry-Run Does More Than Print Commands

A useful dry-run checks:

- Target database and collection names;
- Existing index names and options;
- Existing duplicate records;
- TTL expiration candidates;
- Resource headroom;
- Sharding/topology constraints;
- Driver and server compatibility;
- Concurrent rollout hazards;
- Rollback readiness.

### 48.2. Classifying Outcomes

| Outcome | Meaning | Action |
|---|---|---|
| MATCH | Actual index satisfies spec | PASS |
| MISSING | Index absent | Plan creation |
| CONFLICT | Same name/key with differing critical options | BLOCK + manual migration |
| UNSUPPORTED | Feature/version unsupported | BLOCK |
| DATA_INVALID | Duplicate or invalid data present | Remediate data |
| RESOURCE_RISK | Insufficient disk/capacity | Choose maintenance window / scale capacity |
| EXTRA | Index outside manifest | Investigate owner; do not auto-drop |

## 49. CI/CD Coordination Flow

A controlled pipeline can follow:

```text
Pull request
   │
   ├── Review index manifest
   ├── Review query/load impact
   └── Approve migration
           │
           ▼
      Integration tests
           │
           ▼
      Staging migration
           │
           ▼
      Staging app rollout
           │
           ▼
      Load/failure tests
           │
           ▼
      Production preflight
           │
           ▼
      One-off migration job
           │
           ▼
      Verify actual indexes
           │
           ▼
      Application rollout
           │
           ▼
      Monitor / rollback gate
```

### 49.1. Do Not Use Long-Lived Privileged CI Credentials

The migration runner should obtain short-lived/managed credentials with audit logging. Once migration finishes, API services run with restricted least-privilege identities.

### 49.2. Do Not Mark a Release Ready Before Indexes Are Built

If a new API release relies on a compound index to hit p99 SLOs, wait until the live index build completes per MongoDB semantics—do not merely rely on an HTTP 200 from the pipeline.

## 50. Multi-Tenant and Multi-Collection Considerations

A multi-tenant architecture may use:

1. Shared database / shared collection keyed by `tenantId`.
2. Database per tenant.
3. Collection per tenant.
4. Hybrid topology.

### 50.1. Shared Collection

Indexes usually need the tenant field in the compound key to support tenant-scoped queries and performance:

```javascript
{ tenantId: 1, email_normalized: 1 }
```

Never omit the tenant predicate in application queries; an index does not enforce row-level authorization.

### 50.2. Collection per Tenant

With thousands of dynamic collections, auto-index creation tied to a single static entity class will not guarantee every tenant collection holds the right indexes.

Design migration enumeration, ownership, rate limiting, and tenant-provisioning lifecycles explicitly.

### 50.3. Database per Tenant

`MongoTemplate`/`MongoDatabaseFactory` can route databases dynamically. Migrations must target each tenant database intentionally rather than running once against a default database and assuming all tenants are indexed.

### 50.4. Tenant Onboarding Needs a Schema Gate

When onboarding a new tenant:

```text
Provision database/collection
       │
       ▼
Apply required indexes
       │
       ▼
Verify index catalog
       │
       ▼
Enable tenant traffic
```

Do not send live user traffic to a newly provisioned collection lacking required indexes when SLOs or uniqueness depend on them.

## 51. Application Readiness and Health Checks

A practical requirement is preventing an app from serving requests if a mandatory index is missing—yet never turning a readiness probe into a DDL migration engine.

### 51.1. Read-Only Index Contract Check

You can run a **read-only** catalog check at startup:

```text
Required index exists and matches -> READY
Required index missing/conflict -> NOT READY + alert
```

Keep these safeguards in mind:

- Do not call `listIndexes` every few seconds across thousands of pods inside readiness probes;
- Cache the startup check result or rely on monitoring;
- Do not block the whole cluster over a non-critical index if degraded operation is acceptable per policy;
- Attach alerts and clear ownership;
- Never auto-create or repair indexes inside a readiness handler.

### 51.2. Fail Closed on Correctness Constraints

If a service depends on a unique index to prevent duplicate transactions, a missing index is a **blocker**. For a performance-only index, operations may allow bounded degraded mode.

Classify index severity before building health gates instead of treating all indexes equally.

## 52. Spring Data Repositories Do Not Materialize Indexes

A repository method:

```java
public interface CustomerAccountRepository
        extends MongoRepository<CustomerAccount, String> {

    Optional<CustomerAccount> findByTenantIdAndEmailNormalized(
        String tenantId,
        String emailNormalized
    );
}
```

is translated by Spring Data into an appropriate MongoDB query. Yet **declaring a repository method does not create an index** on `(tenantId, emailNormalized)`.

You still need to:

- Design the index around the query shape;
- Apply it via migration;
- Inspect `getIndexes` and `explain`;
- Measure under load;
- Test uniqueness if it is an invariant.

### 52.1. `save()` Is Not Always a Simple Insert

Spring Data `save()` performs either insert or replace/update depending on entity ID and mapping. Once a unique index exists, `save` calls can start raising duplicate-key errors. Map them explicitly to domain errors rather than crashing unexpectedly.

### 52.2. Duplicate Key Exception

Spring DAO translates MongoDB duplicate-key errors into `DuplicateKeyException` under Spring's `DataAccessException` hierarchy when configured. Handle it as a business conflict instead of retrying blindly.

Example:

```java
try {
    repository.save(account);
} catch (org.springframework.dao.DuplicateKeyException ex) {
    throw new IllegalStateException(
        "Account business key already exists",
        ex
    );
}
```

This illustrates the flow; in a real API, return a controlled domain/HTTP conflict response without leaking raw MongoDB exceptions or PII.

## 53. Common Anti-Patterns

| Anti-Pattern | Risk | Better Practice |
|---|---|---|
| Enabling auto-index in production for convenience | DDL at startup | Separate migration job |
| Every pod calls `ensureIndex` | Concurrent DDL, drift | Coordinated one-off migration |
| `@Indexed(unique=true)` on unaudited legacy data | Duplicate errors | Audit and remediate first |
| Global unique email in multi-tenant | Rejects valid tenant accounts | Compound tenant key |
| Ignoring null/missing values | Unique index build fails | Partial index / explicit semantics |
| Editing unique/TTL only via annotation | Live index unchanged | Explicit versioned migration |
| Forgetting TTL deletes records | Data loss | Retention preflight |
| Assuming `@Indexed` guarantees index presence | Missing indexes in production | Catalog contract checks |
| Running API with root account | Large blast radius | Least privilege |
| Calling `ensureIndex` in HTTP requests | Surprise load and latency | Dedicated migration phase |
| Calling `ensureIndex` in liveness probes | Restart loops | Read-only health checks |
| Dropping indexes automatically on conflict | Query/correctness regressions | Versioned staged migrations |
| Dropping indexes without a rollback plan | Slow rebuilds | Approved change windows |
| Dropping unique/TTL just because `$indexStats=0` | Loss of invariants | Classify index purpose |
| Skipping build headroom checks | Disk full / failed build | Capacity preflight |
| Testing only on empty collections | Misses duplicates and load | Realistic staging datasets |
| Auto-index on in staging, off in prod | Index drift | Identical migration pipeline |
| Comparing names without keys/options | Broken contract | Full semantic comparison |
| Ignoring physical `@Field` names | Index built on wrong field | Verify actual BSON keys |
| Treating indexes like transactional writes | False rollback assumptions | DDL runbook |
| Creating many single-field indexes | Write and storage overhead | Query-shape driven design |
| Assuming hiding an index saves writes | Wrong; hidden still maintained | Use only to test read impact |
| Ignoring sharding uniqueness rules | Invalid constraint | Version-specific sharded rules |
| Neglecting dynamic tenant collections | Some tenants lack indexes | Provisioning schema gate |
| Treating Search indexes like `@Indexed` | Missing lifecycle/cost controls | Search-specific migrations |
| Logging raw index diffs with internal metadata | Leaks schema/topology | Redact logs |
| Writing migration marker before completion | Skipped index | Verify postconditions first |
| Lacking an owner or alert | Unhandled broken rollouts | Operational runbook |

## 54. Practice Exercises

### Exercise 1 — Distinguishing Annotation and Actual Index

A class declares:

```java
@Indexed(name = "idx_email")
private String email;
```

Production sets `auto-index-creation=false`.

1. Can you conclude the index already exists?
2. Which command checks the MongoDB catalog?
3. Which API can create the index programmatically?
4. Who should hold index DDL privileges?
5. How should readiness behave if a critical index is missing?

### Exercise 2 — Tenant Compound Index

A repository queries by `tenantId`, `status`, and sorts descending by `createdAt`.

1. Write `@CompoundIndex`.
2. Write the equivalent `Index` builder.
3. Why does field order matter?
4. Will a query filtering only on `status` definitely use this index?
5. What should you inspect in `explain`?

### Exercise 3 — Unique Index with Duplicate Data

A collection holds three accounts in the same tenant, two sharing an email.

1. Write an aggregation to find duplicates.
2. Propose a business remediation workflow.
3. When should the unique index be created?
4. If live traffic is still writing concurrently, how do you prevent new duplicates?
5. Why is startup auto-index likely to fail here?

### Exercise 4 — Nullable Phone Number

One million accounts, 90% missing `phoneNumber`.

1. What happens if you build a plain single-field unique index?
2. What filter condition suits a partial unique index?
3. How should empty string, `null`, and missing fields be distinguished?
4. Should the key include `tenantId`?
5. How should the app handle a user entering a duplicate phone number?

### Exercise 5 — TTL Risk

A `sessions` collection has 10 million expired documents.

1. What can happen if you add a TTL index at startup?
2. How do you measure the eligible deletion count?
3. Does TTL delete documents at the exact expiration millisecond?
4. Do you need a backup before migrating?
5. How do you prevent a delete storm?

### Exercise 6 — Spring Configuration

Compare:

```properties
spring.data.mongodb.auto-index-creation=true
```

and:

```properties
spring.data.mongodb.auto-index-creation=false
```

1. What behavior does each enable?
2. Why might the property get overridden?
3. How does `AbstractMongoClientConfiguration#autoIndexCreation()` affect it?
4. What must you verify when defining a custom `MongoTemplate`?
5. Which strategy should production choose?

### Exercise 7 — `MongoTemplate.indexOps()`

Write a migration using:

```java
MongoTemplate.indexOps(CustomerAccount.class)
```

to create:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

Give it a clear name, read back the index list, and record the migration outcome.

### Exercise 8 — `ensureIndex` and Conflicts

MongoDB currently has:

```javascript
{ key: { email: 1 }, name: "idx_email" }
```

The app desires:

```javascript
{ key: { email: 1 }, name: "idx_email", unique: true }
```

1. Why is this not a trivial migration?
2. What duplicate risks exist?
3. What workflow creates/transitions the index safely?
4. How would you roll back?
5. How is correctness impacted if `unique` is omitted?

### Exercise 9 — Multiple Pods

A deployment of 30 API pods all enable auto-index creation.

1. Why is this model suboptimal?
2. Does MongoDB necessarily build 30 physical index copies?
3. What startup/readiness risks arise?
4. Design a one-off migration job.
5. What locking/coordination prevents overlapping job runs?

### Exercise 10 — Index Contract Test

Write an integration test that:

- Connects to a test MongoDB instance;
- Reads `getIndexInfo` or `listIndexes`;
- Verifies index name and key ordering;
- Verifies `unique` and `partialFilterExpression`;
- Fails when an index is missing;
- Does not create indexes during the read-only check.

### Exercise 11 — Migration State

A migration job builds the index successfully yet crashes before recording completion.

1. What should the next run do?
2. Why shouldn't it blindly call `dropIndex()`?
3. When should `COMPLETED` be recorded?
4. How are races between two concurrent executors handled?
5. How does a definition hash help?

### Exercise 12 — Partial Unique and Soft Delete

Business rules allow email reuse once an old account is marked `deleted: true`.

1. Define the partial unique index.
2. Which queries can use it?
3. What error can happen when restoring a deleted account back to active?
4. How do you reconcile historical data?
5. Why does uniqueness remain a business invariant?

### Exercise 13 — Hidden Indexes

A rarely used index consumes 12 GiB.

1. What does hiding it let you measure?
2. Do writes still maintain the index while hidden?
3. Do TTL and uniqueness stop working while hidden?
4. Can `hint()` force its use while hidden?
5. Design a drop plan with rollback.

### Exercise 14 — Dynamic Multi-Tenant Collections

A system manages 500 tenant collections, each needing three indexes.

1. Why isn't a static entity annotation sufficient?
2. Design a rate-limited provisioning migration loop.
3. How should a failure on one tenant collection be handled?
4. How do you avoid building 1,500 indexes during peak hours?
5. Should per-tenant schema versions be audited?

### Exercise 15 — Atlas vs Self-Managed

Draft a responsibility table covering:

- Index creation privileges;
- Storage headroom;
- Query monitoring;
- Backups;
- Index build scheduling;
- Search index lifecycle;
- DDL auditing.

Explain why managed Atlas does not remove application-team responsibilities.

### Exercise 16 — Index Performance Regression

After adding a compound index, read p95 drops from 150 ms to 45 ms while write p99 jumps from 90 ms to 230 ms.

1. Which traffic mix metrics should you inspect?
2. How much did index size and working set grow?
3. Would a partial index help?
4. Should you drop it immediately?
5. Design a benchmark and SLO decision process.

### Exercise 17 — CI/CD Migration Pipeline

Design:

```text
PR review -> staging migration -> tests
-> production preflight -> migrate once
-> verify -> API rollout -> monitor
```

For each stage, specify the owner, evidence, stop condition, and rollback.

### Exercise 18 — Incident Response

Incident: post-release, API pods enter a crash loop; logs show an index options conflict; the collection holds 70 million documents.

1. What read-only evidence should you gather?
2. How do you keep the previous app version healthy?
3. Why shouldn't you blindly drop the conflicting index?
4. How do you estimate the cost of building the replacement index?
5. What criteria decide GO vs NO-GO?

## 55. Checklist Before Creating a Production Index

### Data and Correctness

- [ ] Database, collection, and tenant scope identified.
- [ ] Business purpose of the index documented.
- [ ] Duplicate data audited for unique indexes.
- [ ] Null, missing, and empty values reviewed.
- [ ] Normalization and collation rules verified.
- [ ] Partial filter and soft-delete semantics verified.
- [ ] TTL retention window and candidate deletion volume measured.
- [ ] Backup/recovery point verified where needed.
- [ ] API service privileges are not unnecessarily broadened.

### Compatibility and Performance

- [ ] MongoDB Server and Spring Data versions support the options.
- [ ] Index complies with shard-key/unique constraints if sharded.
- [ ] Adequate disk, CPU, and I/O headroom confirmed for build.
- [ ] Staging benchmarked with representative data.
- [ ] Read and write p95/p99 measured.
- [ ] Existing `getIndexes` and `$indexStats` reviewed.
- [ ] No redundant duplicate indexes added.
- [ ] Query-plan verification prepared.
- [ ] Change window, owner, and on-call assigned.
- [ ] Rollback and post-deploy monitoring planned.

### Process

- [ ] Production auto-index creation is controlled or disabled.
- [ ] Migration runs independently, not across all API pods at once.
- [ ] Migration identity enforces least privilege.
- [ ] Desired and actual index specs diffed.
- [ ] Preflight reports PASS / MISSING / CONFLICT states.
- [ ] Conflicts are not resolved by auto-dropping indexes.
- [ ] Migration marker written only after postcondition checks pass.
- [ ] App rollout proceeds only once required indexes are ready.
- [ ] No secrets or sensitive data logged.
- [ ] Evidence and timestamps recorded.

## 56. Post-Deployment Index Checklist

- [ ] `getIndexes`/`listIndexes` reflects the approved specification.
- [ ] Unique/TTL/partial semantics verified.
- [ ] No index builds remain stuck or failing.
- [ ] Read p95/p99 meets target SLO.
- [ ] Write p95/p99 and throughput remain within SLO.
- [ ] Disk usage and headroom remain healthy.
- [ ] CPU, I/O, and replication lag show no anomalies.
- [ ] Query planner uses the index where intended.
- [ ] No unhandled duplicate-key error spikes occur.
- [ ] API services perform no DDL on restart.
- [ ] Migration history recorded accurately.
- [ ] Owner monitors through the stabilization window.
- [ ] Obsolete indexes are dropped only in a follow-up change with sufficient evidence.

## 57. References

Cross-check with official documentation for your **exact Spring Data MongoDB, Spring Boot, and MongoDB Server versions**:

- [Spring Data MongoDB — Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html)
- [Spring Data MongoDB — Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html)
- [Spring Data MongoDB — Template APIs](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html)
- [Spring Data MongoDB — Repositories](https://docs.spring.io/spring-data/mongodb/reference/repositories.html)
- [Spring Boot Reference — Data](https://docs.spring.io/spring-boot/reference/data/index.html)
- [MongoDB Indexes Overview](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB `createIndexes` Command](https://www.mongodb.com/docs/manual/reference/command/createIndexes/)
- [MongoDB Index Builds](https://www.mongodb.com/docs/manual/core/index-creation/)
- [MongoDB Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/)
- [MongoDB `$indexStats`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexstats/)
- [MongoDB `listIndexes`](https://www.mongodb.com/docs/manual/reference/command/listIndexes/)
- [MongoDB Query Explain](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Sharded Unique Index Constraints](https://www.mongodb.com/docs/manual/core/index-unique/#sharded-clusters)
- [MongoDB Search Documentation](https://www.mongodb.com/docs/search/)
- [MongoDB Vector Search Documentation](https://www.mongodb.com/docs/vector-search/)

## Conclusion

Index management in **Spring Data MongoDB** involves two distinct responsibilities: **declaring indexes in the Java model** and **updating the actual index catalog in MongoDB**. `@Indexed`, `@CompoundIndex`, and related annotations keep schema intent visible alongside entities, yet they do not guarantee the database holds those indexes or that modifying an annotation safely converts an existing index.

Auto-index creation can be convenient in learning labs, prototypes, or small controlled setups. On large production collections with many API pods, historical data, and high-availability requirements, however, it introduces significant hazards: **index builds during startup, duplicate-key failures, unexpected TTL purges, option conflicts, elevated I/O/disk load, excessive DDL privileges, and version drift across rolling deploys**. Because indexes can also resolve on first runtime entity access, the risk extends beyond startup itself.

A sustainable operational approach is:

1. **Disable or strictly govern auto-index creation** in production applications.
2. **Declare versioned, owned desired index state**, combining annotations with a resolver or a dedicated manifest.
3. **Run preflight checks** diffing the live catalog, checking unique/TTL data preconditions, capacity headroom, and compatibility.
4. **Execute migrations separately** via `MongoTemplate.indexOps().ensureIndex()` or controlled migration tooling under a single coordinator and approved change window.
5. **Read back live index specifications**, run integration/performance tests, and only then roll out dependent application changes.
6. **Observe metrics and drop legacy indexes only after gathering evidence**, with dedicated rollback plans tailored to each index change type.

A database index is never just a line of annotation or "a few milliseconds saved". It can govern **which records are allowed to exist, which records get purged, whether queries meet SLOs, and whether application startups remain safe**. Treat indexes as **versioned, approved, evidenced, and recoverable database schema migrations**—not as side effects of application boot.
