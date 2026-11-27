# Soft Deletes, Data Retention, and Consistent Filtering Strategies

In many applications, deleting a record does not mean immediately removing the document from Elasticsearch. Users may need to restore deleted data, the system may need to retain an audit trail, or data may have to be kept for a period before physical deletion. These requirements lead to three concepts that must be designed together: **soft deletes, retention, and consistent filtering**.

Soft delete typically marks a document as deleted using a field like `deleted=true` or `deletedAt`. Normal queries must exclude these documents from results. After the recovery window expires, a job can physically delete documents or process them per retention policy. If you only add a `deleted` field and forget to filter in one endpoint, deleted data can still leak in search, aggregations, autocomplete, exports, or get-by-ID APIs.

With Spring Data Elasticsearch, Elasticsearch does not automatically enforce a global soft-delete filter like some ORMs do. The application must organize queries and data-access APIs so `deleted=false` is applied consistently across every read path. You must also define the authoritative source, projection synchronization mechanisms, late-event handling, and when data truly disappears from search.

## 1. Distinguishing soft delete and physical delete

**Soft delete** updates document state to indicate the data is no longer active in normal operations. The document remains in the index and can be retrieved by restore, audit, or cleanup workflows.

**Physical delete** removes the document from the index via the Delete API, Bulk API, or Delete By Query. Once deleted and related storage mechanisms are handled, the document is no longer part of the data served by that index.

| Criterion | Soft delete | Physical delete |
|---|---|---|
| Document remains in index | Yes | No, after delete is applied |
| Directly restorable | Possible if data and permissions allow | Usually requires backup/authoritative source to rebuild |
| Normal search | Must filter deleted documents | Document is no longer returned |
| Index storage | Still consumes space | Can be reclaimed after merges/segment cleanup |
| Audit | Can retain actor/time/reason | Requires separate audit events if history is needed |
| Best suited for | Undo, retention windows, archive workflows | Expired retention, deletion requests, data not needing retention |

Soft delete does not remove data from Elasticsearch. It only changes logical state. Therefore, `deleted=true` must never be treated as proof of legal or security data erasure while data remains in `_source`, snapshots, logs, or other copies.

## 2. When should you use soft delete?

Soft delete fits when there is an explicit requirement for recovery or retention:

- Users can undo deletions within a time window.
- Administrators need to inspect or restore deleted records.
- Systems must preserve deletion state for cross-service synchronization.
- Business rules require auditing who deleted what and when.
- Records must be hidden from normal operations before purging.
- Data is retained for a defined retention period.

Do not add soft deletes simply because it feels safer. It adds complexity to every query, aggregation, update, reindex, and cleanup. If data does not require restoration, has no audit requirement, and policy permits immediate removal, physical deletion can be simpler.

### Soft delete does not replace authorization

The `deleted` field is not an authorization mechanism. Users must never read another tenant's data even if that document is not deleted. Conversely, administrators might be allowed to view deleted records on a dedicated screen. Authorization and deletion state must remain independent conditions.

## 3. Designing fields for soft delete

A basic model might use:

```json
{
  "id": "p-100",
  "tenantId": "tenant-42",
  "name": "Wireless Mouse",
  "deleted": true,
  "deletedAt": "2026-11-13T10:30:00Z",
  "deletedBy": "user-123",
  "deleteReason": "USER_REQUEST"
}
```

Common fields:

| Field | Type | Purpose |
|---|---|---|
| `deleted` | boolean | Whether deleted or not; convenient for exact filtering |
| `deletedAt` | date | Timestamp marked deleted, used for retention and audit |
| `deletedBy` | keyword | Actor performing the action, if business requires |
| `deleteReason` | keyword | Controlled deletion reason code |
| `retentionUntil` | date | Timestamp after which purging is allowed |
| `legalHold` | boolean | Prevents purging when a valid hold exists |
| `sourceVersion` | long | Source version applied to the projection |

Not every field is required. Choose based on business policy and avoid storing unnecessary personal information. `deletedBy` should be a controlled ID or actor code; never store tokens or secrets in documents.

### Using a boolean or only `deletedAt`?

You can use `deletedAt=null` for active and a timestamp for deleted. However, a boolean `deleted` field makes filters simpler, clearer, and easier to inspect. If using both, maintain an invariant:

- When `deleted=false`, `deletedAt` must be null.
- When `deleted=true`, `deletedAt` must be populated.

Never allow the two fields to contradict each other. If using only `deletedAt`, queries must combine `must_not exists` or `exists` properly and consistently everywhere.

### Explicit mapping

Example entity:

```java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products-read")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Boolean)
    private boolean deleted = false;

    @Field(type = FieldType.Date)
    private Instant deletedAt;

    @Field(type = FieldType.Keyword)
    private String deletedBy;

    @Field(type = FieldType.Keyword)
    private String deleteReason;

    @Field(type = FieldType.Date)
    private Instant retentionUntil;

    @Field(type = FieldType.Boolean)
    private boolean legalHold;

    @Version
    private Long version;

    // Constructors, getters and setters
}
```

Explicit field type mappings prevent critical status fields from being dynamically mapped to unsuitable types. `deleted` should be `boolean`; `deletedAt` and `retentionUntil` should be `date`; status/actor codes should be `keyword` when exact filtering is needed.

The default `deleted=false` should be applied when creating new documents. However, do not rely solely on Java defaults if documents are created via bulk imports, ingest pipelines, or other services. Mappers/projectors must ensure the field is explicitly populated.

## 4. Every read path must enforce the same rule

The most common soft-delete bug is filtering only on the main search screen. A system may have many ways to read documents:

- Full-text search.
- Lookup by ID.
- Derived repository queries.
- Hand-built Query DSL.
- `count` and aggregations.
- Autocomplete/suggestions.
- Exports, scroll, PIT, and batch processing.
- Related-document lookups or enrichment.
- Internal APIs and background jobs.
- Caches holding results from before deletion.

If even one read path omits the filter, deleted documents can resurface. Establish one uniform rule: **every normal business query must include `deleted=false` and required access-control filters**. Only administrative endpoints or retention workflows may read deleted records, under separate authorization.

### Basic filter rule

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "deleted": false } },
        { "term": { "tenantId": "tenant-42" } }
      ],
      "must": [
        { "match": { "name": "wireless mouse" } }
      ]
    }
  }
}
```

`deleted=false` and `tenantId` sit in the filter context because they are mandatory constraints that do not affect relevance scores. The text query stays in the query context for scoring.

## 5. Why filter both search and get-by-ID?

A search query might include `deleted=false`, yet repository `findById(id)` normally fetches by ID without knowing the application's soft-delete rules. If a service directly returns `findById` results, deleted documents can still be read.

Do not assume Spring Data Elasticsearch applies a global filter automatically. Define methods or service APIs with explicit semantics:

```java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Optional<ProductDocument> findByIdAndTenantIdAndDeletedFalse(
        String id,
        String tenantId
    );

    List<ProductDocument> findByTenantIdAndDeletedFalse(String tenantId);

    long countByTenantIdAndDeletedFalse(String tenantId);
}
```

Derived query methods make filters explicit at the repository level. Verify property names match the model and mapping. Default methods such as `findById`, `findAll`, `existsById`, or `count` retain their standard semantics; never use them in ordinary services if they can return deleted data or bypass tenant scope.

### Wrapping repositories with a service/facade

One pattern exposes only business services to controllers:

```java
public Optional<ProductDocument> findActiveProduct(String id, String tenantId) {
    return repository.findByIdAndTenantIdAndDeletedFalse(id, tenantId);
}
```

Controllers do not inject repositories directly. Other jobs and services also call through the facade enforcing the same rules. This reduces the risk of a caller accidentally calling an unfiltered method.

## 6. Centralizing query filters in Spring Data Elasticsearch

For complex queries, create a dedicated component to build mandatory constraints. Example:

```java
public class ProductQueryFactory {

    public NativeQuery activeProducts(String tenantId, String text, int page, int size) {
        return NativeQuery.builder()
            .withQuery(q -> q.bool(b -> {
                b.filter(f -> f.term(t -> t
                    .field("deleted")
                    .value(false)
                ));
                b.filter(f -> f.term(t -> t
                    .field("tenantId")
                    .value(tenantId)
                ));

                if (text != null && !text.isBlank()) {
                    b.must(m -> m.multiMatch(mm -> mm
                        .query(text)
                        .fields("name^3", "description")
                    ));
                }
                return b;
            }))
            .withPageable(PageRequest.of(page, size))
            .build();
    }
}
```

This example uses the Java API Client builder integrated with Spring Data Elasticsearch; exact lambda syntax varies by version. The key idea is that soft-delete and tenant filters are constructed server-side, never taken from client raw queries.

### Never concatenate filters onto user-entered strings

Never do:

```java
String query = userQuery + " AND deleted:false";
```

If `userQuery` contains boolean syntax, parentheses, or field expressions, string concatenation can alter query meaning. Place the user query inside a `bool.must` branch while server-managed `deleted=false` stays inside `bool.filter`.

## 7. There is no automatic global soft-delete filter

Spring Data Elasticsearch provides repository abstractions and Query APIs, but it does not automatically inject `deleted=false` into all repository methods. Unlike some ORMs with session/entity-level global filters, Elasticsearch queries are sent exactly as built by repositories or application code.

Therefore, choose an explicit organizational pattern:

- Dedicated repository methods suffixed with `AndDeletedFalse` for simple queries.
- Custom repository fragments to centralize complex queries.
- A shared query factory for mandatory filters.
- Application services/facades restricting direct repository access.
- Contract tests for every endpoint/query type confirming the filter is always present.

Do not rely solely on code reviews or method naming conventions. An integration test seeded with deleted documents can catch any endpoint missing the filter.

## 8. Search, count, and aggregations must stay consistent

If search excludes deleted documents while counts or aggregations include them, the UI will display totals that disagree with the returned list.

Example aggregation query:

```json
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        { "term": { "deleted": false } },
        { "term": { "tenantId": "tenant-42" } }
      ]
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "categoryId"
      }
    }
  }
}
```

Filters placed on the outer query apply to both hits and aggregations in the request. If using `global` aggregations or separate filter aggregations, verify semantics because `global` can bypass outer query filters. Never use special aggregations while forgetting to include soft-delete and tenant constraints in the bucket scope.

`count` endpoints, dashboard metrics, facets, suggestions, and exports must share the same policy. If an administrative endpoint needs to count deleted records too, give it a distinct name and permission rather than accidentally dropping the filter.

## 9. Autocomplete, suggestions, and secondary read paths

Autocomplete is often implemented with completion suggesters, prefix queries, or a secondary index. If source data is soft-deleted without updating the suggestion index, deleted item names can still appear in suggestions.

When a soft delete occurs:

- Update projection documents serving suggestions.
- Exclude deleted documents in suggestion queries if the index stores deletion state.
- Update secondary indices or keyword caches.
- Process synchronization events across all related read models.
- Test autocomplete and search within the same test suite.

Do not test only `/search`; inspect every feature capable of exposing document names, IDs, or metadata.

## 10. Soft delete via a Spring Data service

A simple service can locate an active document, update its state, and save it:

```java
import java.time.Clock;
import java.time.Instant;

public class ProductLifecycleService {

    private final ProductRepository repository;
    private final Clock clock;

    public ProductLifecycleService(ProductRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    public ProductDocument softDelete(
            String id,
            String tenantId,
            String actor) {

        ProductDocument product = repository
            .findByIdAndTenantIdAndDeletedFalse(id, tenantId)
            .orElseThrow(() -> new ProductNotFoundException(id));

        product.setDeleted(true);
        product.setDeletedAt(Instant.now(clock));
        product.setDeletedBy(actor);
        product.setDeleteReason("USER_REQUEST");

        return repository.save(product);
    }
}
```

This snippet illustrates a synchronous flow. In systems with concurrent updates, protect the operation with version/optimistic concurrency or conditional updates so concurrent modifications between read and save are not overwritten. If Elasticsearch is a projection from a database, deletion must begin at the authoritative source; projectors receive events and update search documents.

### Soft delete should be idempotent

If the same delete request is retried, the system needs clear semantics. You can:

- Return the current state if the document is already deleted.
- Return not-found for APIs operating strictly on active documents.
- Record a single deletion event per command/event ID.

Do not overwrite `deletedAt` on every retry if the initial deletion timestamp is needed for retention calculations. Preserve the original timestamp and avoid generating duplicate audit events.

## 11. Restoring deleted documents

If the business permits restoration, restore must be a dedicated operation with authorization. Never let clients send `deleted=false` through a generic update endpoint.

Example:

```java
public ProductDocument restore(String id, String tenantId, String actor) {
    ProductDocument product = repository
        .findByIdAndTenantIdAndDeletedTrue(id, tenantId)
        .orElseThrow(() -> new ProductNotFoundException(id));

    if (product.getRetentionUntil() != null
            && Instant.now(clock).isAfter(product.getRetentionUntil())) {
        throw new RestoreWindowExpiredException(id);
    }

    product.setDeleted(false);
    product.setDeletedAt(null);
    product.setDeletedBy(null);
    product.setDeleteReason(null);

    return repository.save(product);
}
```

This example assumes a policy storing `retentionUntil` and allowing restore only within that window. In practice, you may want to keep deletion history in a separate audit event rather than clearing metadata from the document. If retaining `deletedAt` after restore for history, use another field such as `lastDeletedAt` or an event log to avoid violating current-state invariants.

### Restore can collide with new IDs

While a document is deleted, another document may be created with the same business ID. Explicitly define whether restore may overwrite or must be rejected. Versions, unique keys, and authoritative source rules must govern behavior; do not blindly restore with `save()` if it risks replacing a newer record.

## 12. Optimistic concurrency during deletes and restores

Two operations can occur concurrently:

1. User A updates the product name.
2. User B soft-deletes the product.
3. Both read the same version.
4. One writes first; the other can overwrite state or data without concurrency control.

Spring Data Elasticsearch supports versioning via `@Version` in compatible versions. On a version conflict, the service must reload state and decide according to business rules; do not blindly retry with stale objects.

With direct Elasticsearch APIs, use `if_seq_no` and `if_primary_term` for optimistic concurrency. These tokens belong to Elasticsearch document concurrency, distinct from `sourceVersion` managed by domain services.

For deletes originating from an authoritative database, the source transaction updates state and emits an event via outbox/CDC. Projectors must prevent stale events from overwriting newer state.

## 13. Consistent filtering for repositories and custom queries

With query builders, you can define helpers for shared filters:

```java
private Query filterActiveTenant(String tenantId) {
    return NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
            .filter(f -> f.term(t -> t.field("deleted").value(false)))
            .filter(f -> f.term(t -> t.field("tenantId").value(tenantId)))
        ))
        .build();
}
```

This is an illustrative query fragment; depending on how complex queries are built, pass a builder or use a query factory returning the condition clauses rather than trying to merge two standalone `Query` objects.

With custom repository fragments, all tenant-scoped search operations can live in one place:

```java
public interface ProductSearchRepository {
    SearchPage<ProductDocument> searchActive(
        String tenantId,
        ProductSearchCriteria criteria);
}
```

The implementation builds the `bool.filter` containing `deleted=false`, tenant scope, and business filters. Controllers and services avoid crafting raw queries in multiple places.

### Avoid multiple ways of interpreting status

Avoid having one endpoint check `deleted=false`, another check `deletedAt` missing, and another check `status != DELETED`. If multiple fields represent deletion state, maintain a single invariant and a single mapper so they never diverge.

## 14. Administrative queries to view deleted records

Some features need to inspect deleted data, such as a trash bin or audit screen. Never drop the filter on a general endpoint and let clients choose whether to view deleted items.

Design separate APIs:

- `searchActive`: returns only `deleted=false` documents.
- `searchDeleted`: returns only `deleted=true` documents, requiring appropriate admin roles.
- `searchAllForAudit`: may return both states, tightly restricted and audit-logged.

Example filter for a trash view:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "deleted": true } },
        { "term": { "tenantId": "tenant-42" } }
      ]
    }
  }
}
```

Permission to view deleted data must be verified server-side. Never assume an endpoint named `/deleted` is protected by obscurity.

## 15. What is a retention policy?

A retention policy specifies how long data is kept, when it is hidden, when it is archived, and when it must be deleted. Policies can vary by data type, tenant, jurisdiction, contract, or processing purpose.

A policy should answer:

- Which data falls under the retention scope?
- Does the clock start at created time, closed time, or deleted time?
- What are the minimum and maximum retention periods?
- Are there legal holds or exceptions?
- Upon expiration, is data archived, anonymized, or hard-deleted?
- How is related data in secondary indices, caches, snapshots, and logs handled?
- Who is allowed to modify policies and who is allowed to purge?
- How do we prove the job processed all eligible data?

Do not apply a single global TTL to every document when datasets carry different retention obligations.

## 16. Separating the retention window from soft-delete time

Deletion time and purge eligibility time can differ. For example, a document is marked deleted today yet kept for 30 days so users can restore it.

You can compute:

\[
\text{retentionUntil} = \text{deletedAt} + \text{recoveryWindow}
\]

Or base the policy on case closure dates, contract expiration dates, or other source timestamps. Document the retention anchor explicitly in your model/policy.

Example:

```java
Instant deletedAt = Instant.now(clock);
Instant retentionUntil = deletedAt.plus(Duration.ofDays(30));

document.setDeleted(true);
document.setDeletedAt(deletedAt);
document.setRetentionUntil(retentionUntil);
```

This shows a 30-day recovery window example, not a universal default recommendation. Real policies must derive from business requirements and applicable regulations.

### Use UTC and consistent date types

Store timestamps in UTC (`Instant`) with proper Elasticsearch `date` mappings. Never compute retention using locale date strings or local times without timezones. Convert to user timezones only at the presentation layer.

## 17. Elasticsearch does not auto-delete documents by date fields

Mapping an `expiresAt` or `retentionUntil` field as `date` does not make Elasticsearch automatically delete documents when that timestamp passes. A date field is simply stored and queryable.

To purge expired documents, you need an active mechanism:

- A scheduled job querying by `retentionUntil` and issuing deletes.
- A worker receiving retention events and deleting by ID.
- Delete By Query for matching sets of documents.
- Index Lifecycle Management (ILM) or data stream lifecycles for data organized into appropriate time-based backing indices.

Do not confuse this with automatic TTL features in some other databases. Never assume data was deleted upon expiration just because a date mapping exists.

## 18. Hard purging by expiration with Delete By Query

If you need to physically delete soft-deleted documents whose recovery window has expired, you can use `_delete_by_query`:

```http
POST /products-write/_delete_by_query?conflicts=proceed&wait_for_completion=false
Content-Type: application/json

{
  "query": {
    "bool": {
      "filter": [
        { "term": { "deleted": true } },
        { "term": { "legalHold": false } },
        {
          "range": {
            "retentionUntil": {
              "lt": "2026-10-14T00:00:00Z"
            }
          }
        }
      ]
    }
  }
}
```

The example uses a fixed cutoff timestamp for illustration. In real jobs, compute the cutoff from policy via `Clock` and pass a normalized timestamp. If `legalHold` can be missing on older documents, the query must handle missing states per policy rather than assuming every document has `false`.

`wait_for_completion=false` tells Elasticsearch to run the task asynchronously and return a task ID. The job must poll the task and record deleted counts, version conflicts, failures, and final status. `conflicts=proceed` continues past version conflicts; it does not mean every eligible document was guaranteed deleted.

### Delete By Query is not an atomic operation

Delete By Query searches for documents and dispatches batched delete operations. Documents can change while the job runs; version conflicts and failures must be handled. Partial success can occur. Jobs must inspect response/task results and implement retry/reconciliation procedures.

### Throttling purge job load

On large indices, use throttling (`requests_per_second`) and appropriate slices so purges do not starve search/indexing resources. Run in batches or partitions, monitor task progress, and prevent overlapping purge jobs from piling up uncontrollably.

## 19. Legal holds and retention exceptions

Some records must not be purged even past normal expiration, such as during disputes or special preservation obligations. This can be represented as `legalHold=true` or managed in a separate policy system.

Key points:

- Holds must have an owner and reason.
- Include start/end times or review mechanisms.
- Only authorized roles may toggle holds.
- Purge queries must exclude held documents.
- Hold changes require auditing.
- Purge jobs must read up-to-date hold status and handle concurrency.

If holds are managed in the source database, do not rely solely on a potentially lagging projection field. For critical purges, verify policy against the authoritative source or sync hold status tightly before deleting.

## 20. Document-level retention vs. index-level ILM

Elasticsearch ILM (Index Lifecycle Management) manages **index** lifecycles across phases/actions such as rollover, shrink, force merge, migrate, searchable snapshots, and delete. It is not the default mechanism for deleting individual documents by `deletedAt`.

| Need | Suitable mechanism |
|---|---|
| Delete one expired document | Delete API or Delete By Query |
| Delete many documents by `retentionUntil` field | Scheduled purge job / Delete By Query |
| Delete entire old indices by index age | ILM |
| Append-only time-series data in a data stream | Data stream lifecycle / ILM per backing index |
| Keep hot data then move to cold/frozen | Appropriate ILM phases |

If an index mixes documents across tenants and retention dates, ILM deleting the index can wipe out active unexpired data. Use index-level retention only when data partitioning guarantees the entire index shares one policy and can be deleted together.

### Example monthly indices

```text
events-2026.09
events-2026.10
events-2026.11
```

If every event in a backing index shares a 90-day retention from creation without per-record legal holds, index-level lifecycles work well. If individual events have varying retention periods or holds, use document-level mechanisms or partition indices by policy.

## 21. Deleting related data across multiple indices

A product might appear in:

- Main search index.
- Autocomplete index.
- Analytics/rollup index.
- History or audit index.
- Application caches.
- Tenant/locale search projections.

Soft-deleting or purging only the main index does not remove data from other read models. Maintain a list of dependent projections and emit events that each projector handles.

Example event:

```json
{
  "eventId": "evt-9010",
  "aggregateId": "p-100",
  "aggregateVersion": 13,
  "eventType": "ProductSoftDeleted",
  "deletedAt": "2026-11-13T10:30:00Z"
}
```

Projectors update status in the main index, suggestion projectors remove suggestions, application caches evict related keys, and analytics projections act per their policy. For hard purges, events must clarify the scope of data to delete and track completion across systems.

## 22. Synchronizing soft deletes via Outbox/CDC

When the database is the authoritative source and Elasticsearch is a read model, deletions should start in the database:

```text
Delete command
    |
    v
Source DB transaction
    +--> set deleted=true, deleted_at=...
    +--> insert ProductSoftDeleted outbox event
    |
    v
Commit
    |
    v
Outbox publisher / CDC
    |
    v
Projection consumer
    |
    v
Update Elasticsearch document
```

Writing both the state and the outbox event in the same transaction avoids committing the DB without recording the event. Projectors must be idempotent because events can be redelivered.

### Event ordering and versions

Suppose `ProductUpdated` version 12 arrives after `ProductSoftDeleted` version 13. If the projector applies event 12 afterward, it can resurrect the document. Store `sourceVersion` and reject events older than the applied version; when needed, use conditional updates or serialization by aggregate ID to check and write atomically.

### Soft deletes and tombstones

If a document is hard-deleted immediately, version markers can disappear. A late-arriving old event could recreate the document. Tombstones retain the ID, version, and deleted state long enough for projectors to recognize stale events and avoid resurrecting data.

Once the replay/retention window closes and stale events can no longer arrive, tombstones can be purged per policy.

## 23. Consistency and when data becomes hidden

In eventually consistent architectures, the database may mark a record deleted immediately while Elasticsearch updates only after the event is processed. During that gap, search may still return the document.

Define the requirement:

- **Eventual hiding:** tolerate brief lag; search projections update via outbox/CDC.
- **Near-synchronous hiding:** commands wait for the projector to update and confirm search visibility, if SLAs permit.
- **Immediate revocation:** APIs verify status against the authoritative source or authorization layer before returning data, rather than trusting projections alone.

For sensitive data or access revocation, never rely solely on eventual filters in Elasticsearch. Stale search results can surface during synchronization windows; APIs must verify state/permissions at the authoritative source or use synchronous mechanisms built for that requirement.

### Write acknowledgement does not mean search visibility

After updating a document, Elasticsearch may not have refreshed yet, so search queries do not immediately see the change. When measuring or awaiting visibility, use an appropriate refresh policy (`wait_for` in required use cases) or a canary verification mechanism. Avoid forcing refreshes on every operation unnecessarily.

## 24. Bulk soft delete

When marking many documents, use Bulk Update or Update By Query. Bulk Update fits when IDs are known and fields must be updated per document:

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "update": { "_id": "p-100" } }
{ "doc": { "deleted": true, "deletedAt": "2026-11-13T10:30:00Z" } }
{ "update": { "_id": "p-101" } }
{ "doc": { "deleted": true, "deletedAt": "2026-11-13T10:30:00Z" } }
```

Bulk Updates still experience partial failures; inspect every item. Use a consistent timestamp across the same command if audits should reflect a single operation.

### Update By Query

When marking all documents matching a condition:

```http
POST /products/_update_by_query?conflicts=proceed&wait_for_completion=false
Content-Type: application/json

{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "status": "ARCHIVED" } },
        { "term": { "deleted": false } }
      ]
    }
  },
  "script": {
    "lang": "painless",
    "source": "ctx._source.deleted = true; ctx._source.deletedAt = params.deletedAt;",
    "params": {
      "deletedAt": "2026-11-13T10:30:00Z"
    }
  }
}
```

This is a batch update operation that can run asynchronously, encounter version conflicts, and suffer partial failures. Queries must restrict tenant/status properly; scripts must be controlled by the application. Monitor the task and verify updated counts.

Never use Update By Query as a substitute for authoritative source transactions if Elasticsearch is only a projection. In that architecture, update the authoritative source and let projectors sync state.

## 25. Caching and soft deletes

Application caches may continue returning stale documents after Elasticsearch marks them deleted. When a soft delete succeeds, address:

- Evicting detail caches by ID.
- Evicting or versioning search page caches.
- Evicting autocomplete/suggestion caches.
- Clearing caches by tenant/namespace if all affected keys cannot be enumerated.
- Never caching responses containing deleted records beyond allowed TTLs.

Cache keys must include tenant and proper authorization scopes. Never cache a response prior to soft-delete filtering and reuse it for endpoints or users with different policies.

In event-driven architectures, `ProductSoftDeleted` events can drive cache eviction. Still, event-driven eviction is eventual; sensitive endpoints must verify state at the authoritative source.

## 26. Retention and sensitive data

Soft delete keeps documents in the index, making it insufficient as the sole measure when requirements demand erasing personal data or secrets. Erasure requests must cover:

- Source databases.
- Elasticsearch indices and all secondary projections.
- Caches in JVM/Redis.
- Brokers/retry queues/DLQs if payloads contain data.
- Logs and traces if payloads/PII were logged.
- Snapshots/backups under their respective retention policies.
- Exports or downstream service copies.

Elasticsearch snapshots can retain data as of snapshot time. Deleting documents from a live index does not automatically modify older snapshots. Backup retention, expiration, and restore procedures must be designed alongside deletion policies.

If an audit trail of the deletion must be kept without retaining sensitive content, store minimal audit events—such as a protected internal ID, timestamp, actor code, and action—under separate retention. Never copy full deleted payloads into audit logs.

## 27. Permissions for deleted documents and purging

Permissions should be clearly separated:

- Regular users: read only active documents in authorized tenants.
- Users with restore permission: read trash and restore within allowed windows.
- Administrators: inspect deletion status within granted scopes.
- Retention workers: query and purge only data matching policy.
- Audit readers: read audit metadata without necessarily reading deleted payloads.

Do not grant broad `delete_by_query` permissions to every application user. Retention worker credentials should have least-privilege access on target aliases/indices and be managed separately. Purge logs should record task ID, policy version, cutoff, document counts, and outcome, without logging document contents.

## 28. Tenant isolation in every filter

In multi-tenant indices, soft-delete and tenant filters must always combine:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "deleted": false } }
      ]
    }
  }
}
```

Tenant ID should come from the server-side principal/security context. Never trust a client-supplied `tenantId` without verifying membership/permissions.

For purge jobs, add tenant filters too when jobs run per tenant. If a policy purges an entire index, verify the index/alias contains only the intended data scope. A query missing a tenant filter can wipe data across multiple tenants.

## 29. Handling older documents missing the `deleted` field

When adding soft delete to an existing populated index, older documents may lack the `deleted` field. In Elasticsearch, `term deleted=false` does not match documents missing that field.

Three approaches:

1. Reindex/backfill so all old documents gain `deleted=false`.
2. During transition, use `should` in queries to accept either missing or `false`.
3. Create a new index version, build documents under the new schema, and switch the alias.

Example transition query:

```json
{
  "query": {
    "bool": {
      "filter": [
        {
          "bool": {
            "should": [
              { "term": { "deleted": false } },
              { "bool": { "must_not": { "exists": { "field": "deleted" } } } }
            ],
            "minimum_should_match": 1
          }
        }
      ]
    }
  }
}
```

This is a backward-compatibility query during migration. Once backfilling finishes and every document has the field, simplify to the explicit `deleted=false` rule.

Never let each endpoint pick its own way of handling documents missing the field. Compatibility rules belong in the shared query factory with a defined migration end date.

## 30. Reindexing and updating mappings for soft delete

If an older mapping lacks status fields or needs structural changes, create a new index version:

```text
products-v1  <- old data
products-v2  <- new mapping + deleted/deletedAt
products-read -> products-v1 (currently serving)
```

General workflow:

1. Create `products-v2` with explicit mappings.
2. Backfill documents from the authoritative source, setting `deleted=false` on active records.
3. Sync new events during backfill via watermark/CDC/outbox.
4. Verify counts, versions, and filter behavior.
5. Switch the `products-read` alias to the new index.
6. Retain the old index for a suitable rollback window before deleting per policy.

Never halfway modify production mappings and queries so some documents have the field while others lack it without a migration plan.

## 31. Retention jobs need checkpoints and resumability

Purge jobs may process millions of documents and get interrupted mid-run. Job design should include:

- Policy ID/version.
- Fixed cutoff timestamp for a single run.
- Index/alias scope.
- Complete query filter including deleted, retention, legal hold, and tenant if applicable.
- Task ID or batch checkpoints.
- Expected, processed, failed, and remaining document counts.
- Retry policy for transient failures.
- Audit record for the execution.
- Dry-run/count capability before purging if required by business.
- Rate throttling to protect the cluster.

Never recompute cutoff as `now` on every batch if the job needs a stable scope. Capture the cutoff when the job starts so retries/restarts do not shift the target dataset.

### Dry-runs and scope checks

Before a major purge, run a count query with the exact same filter to estimate eligible documents. Count does not substitute for execution results because data can change between steps, yet it catches wrong indices/tenants or bad cutoffs before deleting.

For irreversible operations, require operational approvals if organizational policy mandates them. Automated jobs must still log the exact policy and scope applied.

## 32. Measuring and monitoring retention

Useful metrics:

- Count of `deleted=true` documents.
- Count of documents past `retentionUntil` yet unpurged.
- Age of the oldest overdue document.
- Count of documents under legal hold.
- Purge throughput (documents/second).
- Purge task duration and failure count.
- Version conflicts and retry counts.
- Remaining documents after job completion.
- Number of cache/projection consumers confirming deletion.

Do not measure only purged document counts. If the job steadily deletes 10,000 documents while 100,000 expire daily, backlog still grows. Track both the arrival rate of expiring documents and the processing rate of purge workers.

## 33. Testing soft deletes and filter consistency

Tests should cover every important read path:

1. Newly created documents have `deleted=false`.
2. Soft delete sets `deleted=true`, `deletedAt`, actor, and reason accurately.
3. Normal search does not return deleted documents.
4. Lookup by ID does not return deleted documents.
5. Counts and aggregations exclude deleted documents.
6. Autocomplete/suggestions do not return deleted data.
7. Exports, pagination, and batch scans apply the filter.
8. Admin endpoints return deleted records only to authorized roles.
9. Tenant A cannot read/delete/restore tenant B's documents.
10. Restore works only inside the policy window and never overwrites newer records.
11. Duplicate events do not alter `deletedAt` or create duplicate audit events unintentionally.
12. Old events do not resurrect deleted documents.
13. Purge removes only eligible documents and spares legal holds.
14. Old documents missing the field follow migration policy.
15. Caches and suggestion indices are invalidated.
16. Search visibility is verified per refresh semantics.

### Integration tests with Elasticsearch

Create one active document and one deleted document in a test index. Call the real repository/query service and assert through search APIs that only the active document appears. Test counts/aggregations and ID lookups separately. For searches immediately after writes, use explicit refresh policies or index refreshes; never rely on `Thread.sleep()`.

Unit tests on query factories verify filter structure, while integration tests prove real queries exclude deleted documents under current mappings.

## 34. Common design mistakes

### Adding `deleted` without filtering everywhere

Documents still leak through endpoints or aggregations missing the filter. Build a query factory/facade and test every read path.

### Assuming Spring Data has a global soft-delete filter

Repositories do not automatically append `deleted=false` to every method. Use derived queries/custom fragments and restrict repository access.

### Filtering search while forgetting `findById`

Read-by-ID can return deleted documents. Create `findByIdAndTenantIdAndDeletedFalse` or equivalent service lookups.

### Forgetting counts, aggregations, and autocomplete

Lists look right while totals, facets, or suggestions still count deleted documents. Apply the same policy across all read models.

### Treating soft delete as actual data erasure

Payloads remain in indices and snapshots. When erasure is required, implement hard purges with broader cleanup scope.

### Treating a date field as automatic TTL

Elasticsearch does not delete documents simply because `retentionUntil` passed. Use purge jobs or index-level lifecycles where appropriate.

### Using ILM to delete individual documents

ILM manages indices. If an index mixes unexpired and expired data, deleting the index destroys valid data.

### Purging without excluding legal holds

Purge queries must verify hold status against authoritative policies and handle races when holds change.

### Old events resurrecting documents

Use source versions, ordering, and tombstones to block stale events after deletes.

### Caches still serving deleted data

Evict related caches, version keys, or cap TTLs by freshness; sensitive endpoints check the authoritative source.

### Using full-document `save` for soft delete without concurrency control

A save can overwrite concurrent edits. Use versions/conditional updates and handle conflicts.

## 35. End-to-end design process

When implementing soft deletes and retention for a document type:

1. Identify the authoritative data source and the service owning deletion state.
2. Clarify why soft delete is needed: restore, audit, workflow, or retention.
3. Design `deleted`, `deletedAt`, actor/reason, and minimal retention metadata fields.
4. Define state invariants and defaults for new documents.
5. Expose repository/service APIs reading only active documents for normal flows.
6. Centralize query filters so search, get-by-ID, count, aggregations, suggestions, and exports align.
7. Separate admin endpoints for viewing/restoring deleted data with authorization checks.
8. Use outbox/CDC to update search projections and caches when Elasticsearch is a read model.
9. Use versions/ordering/tombstones so stale events cannot overwrite or resurrect documents.
10. Define retention windows, legal holds, and purge schedules by data type.
11. Choose document-level purge or index-level ILM based on data partitioning.
12. Run purges with checkpoints, throttling, task monitoring, and audits.
13. Test filter consistency and search visibility against real Elasticsearch.
14. Monitor deleted counts, overdue counts, purge backlogs, sync lag, and cache invalidation.

## 36. Conclusion

Soft delete is a business state, not removal of data from Elasticsearch. A document commonly uses `deleted`, `deletedAt`, actor/reason, and retention metadata; normal queries must apply `deleted=false` alongside tenant/security filters. Spring Data Elasticsearch does not automatically inject a global soft-delete filter, so repository methods, custom query factories, and service facades are needed to keep search, get-by-ID, counts, aggregations, autocomplete, exports, and caches consistent.

Retention policies must define starting anchors, recovery windows, legal holds, and post-expiration actions. Elasticsearch does not auto-delete documents by date fields; use purge jobs/Delete By Query for document-level retention, while ILM/data stream lifecycles suit data organized into indices sharing one lifecycle. When Elasticsearch is a projection, update state at the authoritative source via outbox/CDC, guard against duplicate/out-of-order events with versions and tombstones, and monitor search visibility. For sensitive data requiring true erasure, address secondary indices, caches, queues, logs, and snapshots under the corresponding policy.

## References

- [Spring Data Elasticsearch – Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html)
- [Spring Data Elasticsearch – ElasticsearchOperations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Elasticsearch – Delete API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete)
- [Elasticsearch – Delete By Query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete-by-query)
- [Elasticsearch – Update By Query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update-by-query)
- [Elasticsearch – Index Lifecycle Management](https://www.elastic.co/docs/manage-data/lifecycle/index-lifecycle-management)
- [Elasticsearch – Data stream lifecycle](https://www.elastic.co/docs/manage-data/lifecycle/data-stream)
- [Elasticsearch – Optimistic concurrency control](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/optimistic-concurrency-control)
- [Elasticsearch – Refresh API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-refresh)
