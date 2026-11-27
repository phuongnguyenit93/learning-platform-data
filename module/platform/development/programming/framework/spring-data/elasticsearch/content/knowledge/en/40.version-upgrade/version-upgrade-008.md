# Rebuilding Indexes When Changing Field Types or Analyzers

In Elasticsearch, mappings and analyzers govern how documents are stored in the inverted index and how fields are matched, sorted, and aggregated. Once a field already contains data, changing its type, tokenization rules, or structure requires more than editing entity annotations or calling the update mapping API. Previously indexed data is not automatically re-read and rebuilt under the new rules.

The safe approach for incompatible changes is creating a new physical index with the updated settings and mappings, reloading the data, reconciling results, and switching an alias to the new index. This process is commonly called reindexing or index migration.

For example, an application currently uses `products-v1` with `name` mapped as `text` and an old analyzer. New requirements need `name` changed to `keyword` for exact matching, or a custom analyzer to strip diacritics and normalize terms. The existing index holds terms produced by the old analyzer. Creating `products-v2` and reindexing allows the data to be re-analyzed under the new mapping.

This guide covers field type and analyzer changes, rebuilding indexes with Elasticsearch, integrating the workflow with Spring Data Elasticsearch, alias cutover, and preserving rollback capability if migration fails.

## 1. Why can mapping changes require rebuilding an index?

Elasticsearch does not store documents like a simple relational table. When indexing a document, it uses the mapping to determine how each field is stored and uses analyzers to convert text into inverted-index tokens.

Example document:

```json
{
  "product_id": "P-100",
  "name": "Mechanical Keyboard",
  "price": 2500000,
  "active": true
}
```

The mapping may declare:

```json
{
  "properties": {
    "product_id": { "type": "keyword" },
    "name": { "type": "text", "analyzer": "standard" },
    "price": { "type": "long" },
    "active": { "type": "boolean" }
  }
}
```

With `name` mapped as `text`, the analyzer processes strings into tokens for full-text search. `price` is stored as a numeric type for range queries and sorting. `product_id` is `keyword` for exact matching.

When a mapping changes, Elasticsearch does not automatically fetch every document source and re-index it under the new rules. The current mapping describes how data has already been indexed; it is not an automatic schema migration that rewrites existing documents.

### 1.1. Changes that typically require a new index

| Change | Why Rebuilding/Reindexing Is Usually Needed |
|---|---|
| `text` to `keyword` or vice versa | Term storage and query mechanics differ; existing fields cannot change type directly. |
| `long` to `date`, `double` to `keyword` | Values were indexed under the old type; mapping types conflict. |
| `object` to `nested` | Index layout and query semantics change. |
| Changing index-time analyzer | Existing terms in the inverted index were produced by the old analyzer. |
| Changing tokenizer or token filters | Text must be re-analyzed to generate new terms. |
| Changing document denormalization | Source documents must be reconstructed in the new shape. |
| Changing routing or ID generation rules | Documents must move according to new routing/identity rules. |
| Changing index settings unmodifiable on a live index | Creating a new versioned index is safer and easier to control. |

Not every mapping change requires a new index. You can add new fields or update certain properties permitted by Elasticsearch. However, adding a field to a mapping does not mean old documents have indexed values for that field. If old documents need values in the new field, you must still run update-by-query or reindex to backfill.

### 1.2. Existing mappings cannot arbitrarily change types

Suppose an index currently has:

```json
{
  "properties": {
    "price": { "type": "long" }
  }
}
```

You cannot submit a mapping update to directly change it to:

```json
{
  "properties": {
    "price": { "type": "scaled_float", "scaling_factor": 100 }
  }
}
```

Elasticsearch will reject the conflicting change. The standard approach is creating a new index with the desired type and loading documents into it.

### 1.3. Adding a multi-field does not backfill old documents either

You can add a subfield to a `text` field, such as adding `name.keyword` for sorting or exact matching:

```http
PUT /products-v1/_mapping
Content-Type: application/json

{
  "properties": {
    "name": {
      "type": "text",
      "fields": {
        "keyword": { "type": "keyword" }
      }
    }
  }
}
```

The new mapping may be accepted, yet previously indexed documents will not automatically have terms in the new subfield. You must run update-by-query to re-index documents or reindex into a new index. If the migration also changes multiple fields/analyzers, creating a new versioned index is usually easier to manage.

## 2. How do analyzers affect already indexed data?

An analyzer typically consists of three parts:

1. **Character filters:** transform the input string before tokenization, such as replacing or normalizing characters.
2. **Tokenizer:** splits the string into tokens.
3. **Token filters:** transform tokens, such as lowercasing, asciifolding, stemming, or synonyms.

Example custom analyzer:

```json
{
  "analysis": {
    "analyzer": {
      "product_name_v2": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": [
          "lowercase",
          "asciifolding"
        ]
      }
    }
  }
}
```

The string `"Máy Tính Xách Tay"` can be normalized into lowercase, diacritic-stripped tokens depending on the analyzer. This directly affects full-text search results.

### 2.1. Index analyzer vs. search analyzer

Distinguish two points in time:

- **Index analyzer:** runs when a document is indexed/updated, creating tokens stored in the inverted index.
- **Search analyzer:** runs when query text is analyzed before looking up terms.

If you change the index analyzer, already stored terms are not regenerated simply by changing the query. Documents must be re-indexed to produce the new tokens.

Certain search analyzer configurations can be updated within Elasticsearch mapping/settings limits and version rules. Changing the search analyzer affects only how queries are analyzed at search time; it does not re-analyze stored tokens. If you need to change how indexed data is tokenized, you must reindex.

### 2.2. Changing an analyzer is more than editing an annotation name

Suppose an entity declares:

```java
@Field(type = FieldType.Text, analyzer = "standard")
private String name;
```

And you change it to:

```java
@Field(type = FieldType.Text, analyzer = "product_name_v2")
private String name;
```

The new annotation only describes the mapping Spring Data uses when creating a new index or putting a mapping. If the physical index already exists with the old mapping, changing the code does not re-index existing data.

Ensure the new analyzer is declared in index settings before creating a mapping that references it.

### 2.3. Testing analyzers with the Analyze API

Before running a large migration, inspect actual tokens:

```http
POST /products-v2/_analyze
Content-Type: application/json

{
  "analyzer": "product_name_v2",
  "text": "Máy Tính Xách Tay"
}
```

Inspect the returned tokens to confirm lowercasing, folding, tokenization, and token filters behave as expected. Test representative inputs: accented characters, mixed casing, punctuation, SKU codes, compound words, and empty strings.

You can test analyzers before indexing production documents. This small step catches misconfigured analyzers before reindexing millions of documents.

## 3. Planning the new schema version

Before creating a new index, clearly define the schema changes:

- Name of the new physical index.
- Mapping for every field.
- Analyzers, normalizers, and synonym configurations.
- Data types and date formats.
- `object`/`nested` structures.
- Required, optional, and default fields.
- Data transformation rules from the old schema.
- ID and routing rules.
- Read alias and write alias.
- Strategy for synchronizing writes occurring during migration.
- Validation criteria and rollback conditions.

Version your indexes:

```text
products-v1  (old mapping/analyzer)
products-v2  (new mapping/analyzer)
products     (stable alias)
```

Applications use the `products` alias. Physical indexes are managed by the migration process. Once migration succeeds, the alias shifts from v1 to v2 without repository code having to change index names.

### 3.1. Versioning mappings and settings

Store configurations in source control:

```text
src/main/resources/elasticsearch/
  products-v1-settings.json
  products-v1-mapping.json
  products-v2-settings.json
  products-v2-mapping.json
```

Or use index templates and versioned migration scripts. What matters is that index creation configurations are reproducible, reviewable, and deployed identically across dev, staging, and production.

Do not rely on dynamic mapping to infer types for critical business fields. A single initial document with an unexpected value type can lock the entire index into the wrong type.

## 4. Example of changing field types and analyzers

Suppose v1 has the mapping:

```http
PUT /products-v1
Content-Type: application/json

{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1
  },
  "mappings": {
    "properties": {
      "product_id": { "type": "keyword" },
      "name": {
        "type": "text",
        "analyzer": "standard"
      },
      "price": { "type": "long" },
      "active": { "type": "boolean" }
    }
  }
}
```

New requirements:

- `name` uses a custom analyzer with `lowercase` and `asciifolding`.
- Add a `name.raw` subfield of type `keyword` for sorting/exact match.
- Convert `price` to `scaled_float` to support fractional prices.
- Add a `brand` field of type `keyword`.

Create v2:

```http
PUT /products-v2
Content-Type: application/json

{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1,
    "analysis": {
      "analyzer": {
        "product_name_v2": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "asciifolding"
          ]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "product_id": { "type": "keyword" },
      "name": {
        "type": "text",
        "analyzer": "product_name_v2",
        "search_analyzer": "product_name_v2",
        "fields": {
          "raw": { "type": "keyword" }
        }
      },
      "price": {
        "type": "scaled_float",
        "scaling_factor": 100
      },
      "active": { "type": "boolean" },
      "brand": { "type": "keyword" }
    }
  }
}
```

The v2 mapping and settings are created before loading documents. The Reindex API does not copy mappings/settings from v1 to v2 automatically.

### 4.1. Verifying the target mapping

Read mapping:

```http
GET /products-v2/_mapping
```

Read settings:

```http
GET /products-v2/_settings
```

Test the analyzer:

```http
POST /products-v2/_analyze
Content-Type: application/json

{
  "field": "name",
  "text": "Máy Tính Xách Tay"
}
```

Pass `field` so Elasticsearch applies the analyzer declared for that field. Compare tokens against application expectations.

## 5. Data sources for rebuilding an index

There are two primary sources:

| Source | When Appropriate | Limitations |
|---|---|---|
| Old Elasticsearch index | `_source` has all needed fields and data to build v2 documents. | Cannot recover fields stripped from `_source` or data never indexed. |
| Database/domain source of truth | Need to recompute projections, join extra data, or change document logic. | Requires batch readers, watermarks/CDC, and application-side transformations. |

### 5.1. Reindexing from the old index

If `_source` is enabled and contains all required fields, `_reindex` can read documents from v1 and write to v2. This is fast when changes are mainly mappings/analyzers and no external source data is needed.

### 5.2. Rebuilding from the database

If v1 omitted required fields, or v2 documents combine new data from multiple tables, rebuild from the authoritative source.

For example, v1 only stored:

```json
{
  "product_id": "P-100",
  "name": "Keyboard",
  "price": 2500000
}
```

Meanwhile, v2 requires brand name, category path, and availability. If those fields are absent from v1's `_source`, reindexing cannot synthesize them. Read from the database or event store to build complete projections.

### 5.3. Checking _source

Reindexing from an old index depends on `_source`. If the index disabled `_source` or source filtering stripped needed fields, use another source or accept that the data cannot be reconstructed from the current index.

Do not begin a large migration before verifying the source holds complete data and all documents can be read.

## 6. Basic Reindex API

Once `products-v2` is created, copy documents from v1:

```http
POST /_reindex
Content-Type: application/json

{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
```

Reindex reads document sources and writes them to the destination. It does not copy:

- Mappings.
- Index settings.
- Analyzer definitions.
- Index templates.
- Aliases.
- ILM policies or related operational configurations.

Those components must be created/configured separately prior to running reindex.

### 6.1. Reindexing with a field transformation script

If v1 used `price_cents` while v2 requires `price` in major currency units, transform using a script:

```http
POST /_reindex
Content-Type: application/json

{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  },
  "script": {
    "lang": "painless",
    "source": "if (ctx._source.price_cents != null) { ctx._source.price = ctx._source.price_cents / 100.0; } ctx._source.remove('price_cents');"
  }
}
```

The script runs per document. Check null handling, types, overflow, precision, and business rules. This example only illustrates transformation; if the target mapping is `scaled_float`, define units and scaling factors carefully.

### 6.2. Using an ingest pipeline

You can create a v2 ingest pipeline and specify it on the destination:

```http
POST /_reindex
Content-Type: application/json

{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2",
    "pipeline": "products-projection-v2"
  }
}
```

Create and test the pipeline before migration. Version the pipeline so results are reproducible. If a pipeline changes mid-job, documents in the same run may be transformed inconsistently.

### 6.3. Choosing operation semantics

Destination defaults to `index` semantics by ID. To create only documents that do not yet exist, set `op_type: create`. When an ID already exists, that item triggers a version conflict instead of overwriting.

Do not ignore conflicts blindly without knowing why they happened. Conflicts may be expected because the destination already received newer writes, or they may signal migration data colliding/overwriting.

## 7. Large reindexes via the Task API

For large datasets, avoid holding a single HTTP connection open for the entire migration. Run asynchronously:

```http
POST /_reindex?wait_for_completion=false
Content-Type: application/json

{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
```

The response returns a task ID. Store the task ID in migration metadata for tracking.

Inspect the task:

```http
GET /_tasks/<task_id>
```

List reindex tasks:

```http
GET /_tasks?actions=*reindex&detailed=true
```

Cancel a task if necessary:

```http
POST /_tasks/<task_id>/_cancel
```

Canceling a task does not roll back documents already written to the destination. The target index may contain partial data; mark it incomplete and clean up or resume per plan.

### 7.1. Throttling and slicing

Commonly used options:

- `requests_per_second`: throttles batch rate.
- `slices`: splits reindexing into parallel slices.
- `max_docs`: limits document count for dry runs or scoped migrations.
- `wait_for_completion=false`: runs as a background task.

Example:

```http
POST /_reindex?wait_for_completion=false&requests_per_second=300&slices=auto
Content-Type: application/json

{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
```

Adding more slices is not always faster. Too many slices increase search contexts, requests, and cluster pressure. Measure CPU, disk, indexing pressure, queues, and search latency before increasing concurrency.

### 7.2. Recording migration results

Record the following metadata:

- Source index and destination index.
- Mapping/settings version.
- Reindex task ID.
- Start/end timestamps.
- Total, created, updated, version conflicts, and failures.
- Watermark/CDC position if concurrent writes occurred.
- Validation and cutover status.
- User/job that initiated the migration.

Do not declare success merely because the task finished. Inspect failures, conflicts, and actual data.

## 8. Handling writes occurring during reindexing

Reindexing does not automatically stream changes occurring while the job runs.

Suppose reindexing starts at 10:00. While running:

- 10:01: product `P-100` has its price updated.
- 10:02: product `P-200` is created.
- 10:03: product `P-300` is deleted.
- 10:05: reindex reaches that portion of old data.

Without capturing inserts/updates/deletes, v2 may miss `P-200`, still hold `P-300`, or keep the old price of `P-100`.

### 8.1. Short downtime strategy

If writes can be paused:

1. Put the application in read-only/maintenance mode or stop write producers.
2. Wait for in-flight requests to finish.
3. Reindex all data from source to destination.
4. Refresh the destination.
5. Reconcile counts, sample IDs, and queries.
6. Switch the alias to the destination.
7. Verify reads/writes.
8. Resume write traffic.

The advantage is simplicity and strong consistency. The drawback is downtime proportional to dataset size and reindex duration.

### 8.2. Online strategy with dual-write

Dual-write writes new changes to both the old and new indexes during migration.

High-level flow:

```text
Application write
       |
       +----> products-v1
       |
       +----> products-v2

Initial backfill
       |
       +----> products-v2

Validate both indexes
       |
       v
Atomic alias cutover
```

Enabling dual-write alone is not enough. Race conditions exist:

1. Reindex reads `P-100` with its old price.
2. Dual-write writes `P-100` with its new price to v2.
3. Reindex writes the old price afterward, overwriting it.

If backfill overwrites newer data, v2 ends up stale. You need versioning, ordered replay, or backfill followed by catching up from a change log.

Dual-write is also not an atomic transaction across both indexes. A write may succeed on v1 and fail on v2. Retries, idempotency, and reconciliation are necessary.

### 8.3. CDC or transactional outbox

When a database is the authoritative source, CDC/outbox provides cleaner change control:

1. Record watermark `W0` of the change log.
2. Retain events from `W0` onward.
3. Create v2 and load the snapshot.
4. Replay events from `W0` in order with proper versioning.
5. Reconcile up to watermark `W1`.
6. Drain final events or briefly serialize writes.
7. Switch the alias.
8. Keep consumers targeting v2.

Snapshot and watermark must align. If the snapshot already includes an event that gets replayed again, the operation must be idempotent. If the snapshot is older than the watermark and skips events, data will be lost.

### 8.4. Handling deletes

Deletes are also data changes. If you dual-write inserts/updates while ignoring deletes, v2 can retain documents deleted from the source.

CDC/outbox must represent deletes with events/tombstones, and consumers must apply deletes by ID/version. Checking total counts alone might miss leftover stale documents if new documents mask the discrepancy.

## 9. Reconciling the new index before cutover

Do not switch the alias simply because the Reindex API reports `completed`. Verify the destination against the exact data scope and watermark.

### 9.1. Refresh the destination

```http
POST /products-v2/_refresh
```

Refreshing makes previously indexed documents visible to the Search API. If CDC/replay is still running, final validation must wait until the defined synchronization point.

### 9.2. Compare document counts

```http
GET /products-v1/_count
```

```http
GET /products-v2/_count
```

Counts are meaningful only when both indexes reflect the same snapshot/watermark. If v1 still receives writes while v2 has not finished replaying, differing counts may be valid at that moment.

### 9.3. Inspect sample documents

Pick representative IDs:

- Recently created documents.
- Recently updated documents.
- Documents with optional/`null` fields.
- Documents with boundary numeric values.
- Documents containing Vietnamese text, Unicode, punctuation, and compound words.
- Documents with `nested`/`object` fields or arrays.
- Documents with renamed or type-changed fields.

Fetch by ID from both indexes and compare according to transformation rules. Do not demand byte-for-byte equality when the migration intentionally altered document structure.

### 9.4. Verify query semantics

Run the application's real query suite:

- Full-text matches with the new analyzer.
- Exact matches on `keyword` fields.
- Range filters/sorting on numeric/date fields.
- Queries using new multi-fields.
- `nested` queries if structures changed.
- Aggregations and cardinality.
- Alias filters/routing if used.

Pay special attention to strings affected by analyzer changes: accented characters, casing, punctuation, abbreviations, SKUs, and synonyms. An index with matching document counts can still yield unexpected search results.

### 9.5. Verify errors and data distribution

Confirm:

- Reindex failures equal zero, or every failure was resolved.
- Version conflicts are categorized.
- Counts grouped by tenant/category/status are reasonable.
- Required fields show expected missing-value rates.
- No bulk rejections or out-of-bounds CDC lag remain.
- Target mapping matches the desired schema version.

## 10. Switching the alias to the new index

Aliases let applications use a stable logical name while physical indexes change across versions.

Before migration:

```text
products-v1  <--- products
```

After migration:

```text
products-v2  <--- products
```

Use a single `_aliases` request to remove the alias from v1 and add it to v2:

```http
POST /_aliases
Content-Type: application/json

{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products",
        "is_write_index": true
      }
    }
  ]
}
```

Elasticsearch applies actions in a single alias update request atomically at the cluster state level. Do not split this into separate remove and add requests, which creates a window where the alias does not exist.

### 10.1. Separating read and write aliases

You can use:

- `products-read` for queries.
- `products-write` for index/update/delete.

If both aliases switch versions together, combine the removes and adds into one request:

```http
POST /_aliases
Content-Type: application/json

{
  "actions": [
    { "remove": { "index": "products-v1", "alias": "products-read" } },
    { "remove": { "index": "products-v1", "alias": "products-write" } },
    { "add": { "index": "products-v2", "alias": "products-read" } },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
```

If an alias points to multiple indexes, designate the write index explicitly. Aliases do not fan out writes to all backing indexes.

### 10.2. Preserving alias metadata

If the old alias had a filter or routing, recreate that exact configuration on the new alias. Forgetting filters/routing can alter the visible document set or request routing after cutover.

## 11. Integrating with Spring Data Elasticsearch

Applications should reference the stable alias in entities:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products", createIndex = false)
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String productId;

    @Field(
        type = FieldType.Text,
        analyzer = "product_name_v2",
        searchAnalyzer = "product_name_v2"
    )
    private String name;

    @Field(type = FieldType.Scaled_Float, scalingFactor = 100)
    private double price;

    @Field(type = FieldType.Keyword)
    private String brand;

    // constructors, getters, setters
}
```

The annotations illustrate the v2 mapping. Annotation enum/attribute names may vary by Spring Data Elasticsearch version; check your project's dependency API. `createIndex = false` fits when indexes/aliases are managed by dedicated migrations and applications must not auto-create indexes on startup.

The repository continues using the alias:

```java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
```

When `products` switches to `products-v2`, the repository seamlessly keeps using the declared alias name.

### 11.1. Managing indexes with IndexOperations

Spring Data provides `IndexOperations` to inspect and manage indexes:

```java
IndexOperations indexOperations =
        operations.indexOps(IndexCoordinates.of("products-v2"));

boolean exists = indexOperations.exists();
```

You can use `IndexOperations` for version-supported admin tasks like checking existence, reading mappings, or deleting indexes. Creating a new versioned index requires complete settings and mappings. For custom analyzer configurations, use the REST API/Java API Client or dedicated index migration tooling to provision settings/mappings first, then use Spring Data for CRUD/search.

Do not call `createWithMapping()` on a live index just because entity annotations changed and expect it to transform existing fields. Putting a new mapping does not re-index existing documents.

### 11.2. Preventing applications from auto-creating the wrong physical index

When managing indexes with aliases and migrations, align startup configuration. A repository starting before the alias exists may attempt to create a physical index named after the alias, or fail because custom analyzer/mapping settings are missing.

Run migrations/index provisioning before application instances accept traffic, or configure entities so applications do not auto-create indexes. Verify exact behavior in your Spring Data version.

### 11.3. Using IndexCoordinates when targeting versioned indexes

Certain migration operations must target physical indexes directly:

```java
IndexCoordinates oldIndex = IndexCoordinates.of("products-v1");
IndexCoordinates newIndex = IndexCoordinates.of("products-v2");
```

You can pass `IndexCoordinates` to appropriate operations APIs to read/write specific indexes. Standard application repositories should keep using the stable alias; only migration/admin components need to know physical version names.

## 12. Changing analyzers in Spring Data mappings

Entities can declare analyzers via annotations:

```java
@Field(
    type = FieldType.Text,
    analyzer = "product_name_v2",
    searchAnalyzer = "product_name_v2"
)
private String name;
```

However, the analyzer definition must exist in index settings. Mapping annotations do not define custom tokenizers/filters by themselves.

Example settings JSON managed separately:

```json
{
  "analysis": {
    "analyzer": {
      "product_name_v2": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": ["lowercase", "asciifolding"]
      }
    }
  }
}
```

If using annotation-referenced settings/mapping files or resource paths, keep those files versioned alongside code. Index creation order must be settings/analyzers first, mappings second, and document ingestion last.

## 13. Rollback strategy

Before cutover, if reindexing or validation fails, keep the alias on v1. You can delete the incomplete v2 index and recreate it after fixing the mapping/script.

After cutover, switching the alias back to v1 is fast:

```http
POST /_aliases
Content-Type: application/json

{
  "actions": [
    { "remove": { "index": "products-v2", "alias": "products" } },
    {
      "add": {
        "index": "products-v1",
        "alias": "products",
        "is_write_index": true
      }
    }
  ]
}
```

However, rolling back the alias only changes the target pointer; it does not sync writes made to v2 back into v1.

For example:
1. Alias switches to v2 at 12:00.
2. `P-500` is created at 12:05 and written only to v2.
3. `P-100` is updated at 12:06 and written only to v2.
4. Alias switches back to v1 at 12:10.

v1 lacks `P-500` and holds the old price for `P-100`. Therefore, rollback requires a data plan.

### 13.1. Keeping v1 synchronized during the rollback window

You can maintain dual-write or retain CDC/outbox long enough to replay changes back to v1. On rollback, v1 must catch up to the latest watermark before receiving traffic.

### 13.2. Pausing writes and syncing the delta

If dual-write is not maintained, when rollback is needed:
1. Temporarily block writes.
2. Drain in-flight requests.
3. Replay the change log or rebuild the delta from the source of truth into v1.
4. Refresh and reconcile.
5. Switch the alias back to v1.
6. Re-enable writes.

### 13.3. Retaining the old index long enough

Do not delete v1 right after cutover. Retain the old index for the rollback window to:
- Compare v1/v2 results.
- Investigate mapping/analyzer bugs.
- Recover if v2 fails.
- Replay data or perform reconciliation.

Only retire v1 once v2 is stable, the rollback window has elapsed, and necessary data is preserved per retention policy.

## 14. Testing migration before production

Migration tests should run on a production-compatible Elasticsearch version with representative data and deployment-like mappings.

### 14.1. Testing mappings and analyzers

- Create v2 from versioned settings/mappings.
- Read back mappings and confirm field types.
- Call the Analyze API with representative inputs.
- Verify token outputs.
- Test full-text and exact-match queries.

### 14.2. Testing reindex

- Create v1 and index sample documents.
- Create v2 with the new mapping.
- Run reindex.
- Refresh v2.
- Compare counts and sample documents.
- Verify field transformation scripts/pipelines.
- Check failures and version conflicts.

### 14.3. Testing alias cutover

- Create an alias pointing to v1.
- Execute the remove/add alias update in one request.
- Verify the alias points to v2.
- Read and write through the alias.
- Check write index and filters/routing if present.
- Test alias rollback and validate the data consistency strategy.

### 14.4. Testing writes during migration

If the system runs online:
- Create/update/delete documents while reindexing runs.
- Verify change capture records every event.
- Test races between backfill and dual-write.
- Replay events in version order.
- Verify v2 matches source at the cutover watermark.
- Practice rollback and confirm no post-cutover writes are lost.

Testcontainers can spin up Elasticsearch for integration tests. Pin the image version, and never use production clusters or shared indexes to test destructive create/delete flows.

## 15. Monitoring migration in operations

A migration job should emit technical metrics and events:

| Metric | Purpose |
|---|---|
| Reindex task status | Track whether the task is running, completed, or canceled. |
| Source/target document count | Detect missing or extra documents. |
| Reindex failures | Track items that failed to migrate. |
| Version conflicts | Detect write contention or duplicate IDs. |
| Reindex duration/throughput | Estimate time to completion. |
| Target indexing latency | Detect destination overload. |
| 429/rejections | Monitor cluster capacity. |
| CDC/outbox lag | Determine whether target has caught up with writes. |
| Validation mismatches | Count discrepancies after transformation. |
| Alias cutover timestamp | Correlate alias switch with incidents. |

Do not log full document sources or exception messages containing PII. Log task ID, index version, counts, duration, error type, and safe correlation IDs.

## 16. Common mistakes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Mapping API rejects field type change | Field already exists with old type. | Create a new index and reindex. |
| Changed annotation yet old data searches the same | Mapping annotations do not re-index existing documents. | Create a new versioned index and reload data. |
| New analyzer not recognized | Analyzer not declared in target index settings. | Apply settings before mappings. |
| New query analyzer yet old docs do not match | Stored tokens in inverted index still use old analyzer. | Reindex if index-time analyzer changed. |
| New multi-field has no data for old docs | Mapping update does not backfill indexed values. | Run update-by-query or reindex. |
| Reindex succeeds yet target fields are wrong | Target mapping/script/pipeline is incorrect. | Inspect mapping, Analyze API, and sample docs. |
| Destination misses new documents | Writes during reindex were not captured. | Freeze writes or use CDC/outbox/dual-write. |
| Destination has stale data after update | Backfill overwrote newer writes. | Use versioning or ordered change-log replay. |
| Deleted documents reappear in v2 | Delete events were not replayed. | Capture tombstones/deletes and reconcile. |
| App still reads v1 after alias switch | Some code paths hardcode physical index names. | Locate all read/write paths and switch to stable alias. |
| Alias rejects writes | Multiple backing indexes with no write index designated. | Set `is_write_index` on the target index. |
| Alias rollback loses new writes | Post-cutover writes went only to v2. | Sync delta/replay to v1 before rolling back. |
| Reindex too slow or overloads cluster | Batch size/slicing/concurrency too high. | Throttle, watch node stats, and tune rate. |
| Canceled reindex task leaves partial data | Cancel does not roll back already written items. | Mark target incomplete, clean up, or re-run safely. |
| Document counts differ between indexes | Compared at different watermarks or catch-up incomplete. | Sync to the same watermark before reconciling. |
| App auto-creates wrong index on startup | Index provisioning and alias lifecycle are misaligned. | Run index migrations before startup/traffic or disable auto-create appropriately. |

## 17. Pre-rebuild checklist

**Schema and mapping**
- Identified which fields change type/analyzer and why.
- Selected the new versioned index name.
- Versioned custom analyzer/normalizer/synonym settings.
- Validated v2 mapping on a test index.
- Documented rules for new fields, renames, and transformations.

**Data source**
- Confirmed `_source` holds sufficient data if reindexing from old index.
- Identified authoritative source of truth if data is missing.
- Checked IDs/routing and delete handling.
- Established watermark if using CDC/outbox.

**Reindex**
- Created destination with complete settings and mappings.
- Tested scripts/pipelines.
- Recorded and monitored the task ID.
- Tuned batching/throttling/slicing for cluster capacity.
- Classified failures and conflicts.

**Reconciliation**
- Refreshed destination.
- Compared counts at the same watermark.
- Verified sample documents.
- Verified analyzer outputs on representative inputs.
- Verified production queries, sorting, aggregations, and filters.
- Confirmed CDC lag is within cutover threshold.

**Cutover and rollback**
- Repositories target the stable alias.
- Preserved alias filters/routing.
- Configured explicit write index for read/write aliases.
- Switched alias in a single atomic request.
- Executed post-cutover smoke tests.
- Retained old index for the rollback window.
- Ensured replay/dual-write prevents write loss on rollback.
- Delete old index only after the rollback window closes.

## 18. Sample migration workflow

```text
Phase A — Prepare
  - Identify mapping/analyzer changes
  - Version settings and mappings
  - Create products-v2

Phase B — Verify config
  - Inspect mappings/settings
  - Call Analyze API
  - Run query acceptance tests

Phase C — Capture writes
  - Record watermark W0
  - Enable CDC/outbox or schedule maintenance window

Phase D — Backfill
  - Reindex v1 -> v2 or rebuild from source of truth
  - Monitor task, failures, and throttling

Phase E — Catch-up and validate
  - Replay inserts/updates/deletes
  - Reconcile counts, samples, and queries
  - Wait for watermark W1

Phase F — Cutover
  - Briefly drain/serialize writes if needed
  - Atomic alias switch v1 -> v2
  - Smoke test reads/writes

Phase G — Rollback window
  - Keep v1 and change log
  - Dual-write or ensure replay back to v1
  - Monitor errors and performance

Phase H — Complete
  - Close rollback window
  - Stop legacy sync stream
  - Retire v1 per retention policy
```

## 19. Key takeaways

- Mappings and analyzers determine how data is indexed; changing annotations does not rebuild existing data.
- Existing field types cannot be changed arbitrarily; incompatible changes usually require a new versioned index.
- Changing an index-time analyzer requires reindexing so inverted-index tokens are regenerated.
- Changing a search analyzer affects query parsing only; it does not fix already stored tokens.
- Adding a field or multi-field to a mapping does not backfill values for old documents.
- Create the destination with complete settings/mappings before calling the Reindex API.
- The Reindex API copies document sources, not mappings, settings, aliases, or templates.
- Reindexing from an old index requires full `_source`; otherwise rebuild from the source of truth.
- Writes occurring during reindexing require freezing, dual-write, or capture/replay via CDC/outbox.
- Resolve races between backfill and concurrent writes, and capture inserts, updates, and deletes alike.
- Reconcile counts, sample documents, analyzer outputs, and query semantics at the same watermark.
- Use a single alias update request for atomic alias switching.
- Spring Data repositories should use stable aliases instead of versioned physical index names.
- Alias rollback only redirects access; it does not automatically push new writes back to the old index.
- Keep the old index throughout the rollback window and delete it only after confirming data safety.

Rebuilding an index is a data migration workflow, not just a mapping edit. Create a new versioned index with the proper analyzers and field types, reload data from an authoritative source, catch up concurrent changes, validate results, and switch the alias. Retain the old index alongside the change log during the rollback window so you can revert without losing new writes.

## References

- [Elasticsearch — Reindex API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-reindex.html)
- [Elasticsearch — Mapping](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping.html)
- [Elasticsearch — Analyzer](https://www.elastic.co/guide/en/elasticsearch/reference/current/analysis-analyzers.html)
- [Elasticsearch — Analyze API](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-analyze.html)
- [Elasticsearch — Update mapping API](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-put-mapping.html)
- [Elasticsearch — Index aliases](https://www.elastic.co/guide/en/elasticsearch/reference/current/aliases.html)
- [Elasticsearch — Update aliases API](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-aliases.html)
- [Elasticsearch — Tasks API](https://www.elastic.co/guide/en/elasticsearch/reference/current/tasks.html)
- [Spring Data Elasticsearch — Object mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch — Index operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
