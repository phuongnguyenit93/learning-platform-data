# Changing Mappings via Reindexing and Alias Switching

Mappings define how Elasticsearch stores, analyzes, and queries each field. When a schema evolves, certain properties cannot be modified directly on an index that already holds data. For example, changing a field from text to keyword, swapping an analyzer, converting an object into nested, or backfilling a new multi-field on older documents all require an appropriate reindexing plan.

The standard workflow is to create a new index with the desired mapping and settings, copy documents using the Reindex API, verify the destination index, and switch the alias from the old index to the new one. The application continues using a stable alias while physical index names are versioned to support migration and rollback.

Reindexing and alias switching are only two pieces of the procedure. A production migration must also handle new writes arriving during the copy, documents failing the new mapping, routing, access permissions, refreshes, consistency, task monitoring, and post-cutover writes. This lesson explains how to run the entire workflow in a Spring Data Elasticsearch context.

## 1. Why Is a New Index Needed When Changing Mappings?

Elasticsearch allows adding new fields to an existing mapping in many cases. However, many properties that determine how data is indexed cannot be altered arbitrarily once documents exist.

Situations that typically require creating a new index:

- Changing a field type, such as text to keyword, keyword to long, or object to nested.
- Changing the analyzer or tokenizer of a text field.
- Adding a multi-field when older documents need terms/doc values for the subfield.
- Restructuring object, nested, or flattened fields.
- Changing index settings that can only be applied at index creation time.
- Changing vector storage options or dense_vector dimensions.
- Normalizing data, renaming fields, or transforming schemas.
- Modifying any mapping property that does not support in-place updates on existing fields.

Example old mapping:

~~~json
{
  "properties": {
    "status": {
      "type": "text"
    }
  }
}
~~~

The application now needs exact filtering, sorting, and aggregations by status. The new mapping wants keyword:

~~~json
{
  "properties": {
    "status": {
      "type": "keyword"
    }
  }
}
~~~

You cannot simply change the type on an index already containing documents and expect Elasticsearch to rebuild internal structures for old data. Create a new index, ingest documents under the new mapping, and switch traffic.

### 1.1. Adding a Multi-Field Also Needs Backfilling

A common misconception is adding status.keyword to a status field mapped as text:

~~~json
{
  "properties": {
    "status": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword"
        }
      }
    }
  }
}
~~~

Elasticsearch permits adding a multi-field to the mapping, but previously indexed documents are not automatically re-analyzed to generate terms and doc values for the new subfield. If sorting or aggregations must cover all existing data, you must reindex or update those documents.

Reindexing into a new index makes schema changes easier to review, test, and roll back cleanly.

## 2. Aliases Decouple Applications from Physical Index Names

An alias is a logical name pointing to one or more indices. Applications can target the alias as a stable endpoint:

~~~text
products-v1  <--- products
~~~

After creating the new index and cutting over:

~~~text
products-v1
products-v2  <--- products
~~~

Application code continues calling products. Switching from products-v1 to products-v2 happens inside the Elasticsearch cluster.

Aliases can serve as:

- Read alias: reads documents from the target index or indices.
- Write alias: designates the index receiving writes.
- Filter alias: exposes only a matching subset of documents.
- Routing alias: routes requests to specific shards.
- Switch point between index versions.

### 2.1. Versioning Index Names

A simple naming convention:

~~~text
products-v1
products-v2
products-v3
products       (stable alias)
~~~

Never reuse the same name for an alias and a physical index. Keep physical indices versioned and the alias constant. This lets you build the next index while the current one serves traffic, and keep the old index around for rollback.

### 2.2. Read Aliases and Write Aliases

If an alias points to a single index, Elasticsearch can use it for both reads and writes. When an alias points to multiple indices, writes must know which index is the write index. You set is_write_index on one index.

Split alias pattern:

~~~text
products-read  -> products-v2
products-write -> products-v2 (is_write_index)
~~~

Splitting read and write aliases helps when reading across multiple indices or isolating write control. For simpler applications, a single alias suffices when pointing to one index at a time.

An alias is not a dual-write mechanism. Pointing an alias at multiple indices does not automatically replicate a write to all of them.

## 3. Pre-Migration Inventory

Before creating the new index, capture the current state and every dependent component.

Record:

- Current physical index name.
- Read/write aliases and any filter or routing settings.
- Current mappings and settings.
- Document count, storage size, shard count, and replica count.
- Analyzers, normalizers, ingest pipelines, and index templates.
- Which queries, sorts, aggregations, and repositories use which fields.
- Any applications or batch jobs writing directly to a physical index name.
- Refresh and retention policies.
- Write rate during migration.
- Acceptable downtime window, if any.
- Snapshots/backups and rollback plan.

Check aliases:

~~~http
GET _cat/aliases?v
~~~

Inspect mappings and settings:

~~~http
GET products-v1/_mapping
GET products-v1/_settings
~~~

Check document count and index status:

~~~http
GET products-v1/_count
GET _cat/indices/products-v1?v
~~~

If any service still writes directly to products-v1 after cutover, new data will miss the active index. Move all writers onto the alias or coordinate them with the migration job.

### 3.1. Plan Rollback Before Starting

Before beginning, define:

- Under what conditions rollback is permitted.
- Whether writes continue into the new index after cutover.
- If rolling back, how post-cutover writes will be replayed.
- Whether a durable event log or outbox exists for recovery.
- When the old index may safely be deleted.

Rolling back an alias does not automatically copy writes sent to the new index back into the old index. Flipping the alias back can leave applications seeing stale data unless post-cutover writes are reconciled.

## 4. Creating the New Index with Complete Mappings and Settings

Create the destination index with fully reviewed settings and mappings. Never create an index with default settings and let the application infer mappings during ingestion.

Example:

~~~http
PUT products-v2
{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1,
    "analysis": {
      "normalizer": {
        "lowercase_normalizer": {
          "type": "custom",
          "filter": ["lowercase"]
        }
      }
    }
  },
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "name": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      },
      "status": {
        "type": "keyword",
        "normalizer": "lowercase_normalizer"
      },
      "priceInCents": {
        "type": "long"
      },
      "createdAt": {
        "type": "date"
      },
      "active": {
        "type": "boolean"
      }
    }
  }
}
~~~

Shard and replica counts in the example are illustrative. Choose them based on data size, node count, workload, and cluster policy.

### 4.1. Verify the Mapping Before Reindexing

Read back mappings and settings after creation:

~~~http
GET products-v2/_mapping
GET products-v2/_settings
~~~

Verify:

- Field types are correct.
- Analyzers and normalizers exist.
- Multi-fields have exact names.
- Dynamic mapping policy is correct.
- Date formats match source data.
- Numeric types cover the required range.
- Object/nested structures match expectations.
- Dense vectors have exact dimensions and similarity if used.
- Shard/replica counts are appropriate.

If the mapping is wrong, recreate the index while it is still empty. Never reindex into an unverified schema.

### 4.2. Index Templates

If indices follow versioned or rollover naming conventions, manage schemas with index templates. Verify the template applied properly before reindexing:

~~~http
GET _index_template/products-template
~~~

Templates ensure new indices share a consistent schema. They do not retroactively fix existing indices and do not replace verifying the destination index.

## 5. How Does the Reindex API Copy Data?

The Reindex API reads documents from a source index and indexes them into a destination index. By default, Elasticsearch preserves source document IDs.

Example:

~~~http
POST _reindex
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

The new mapping applies as documents are indexed into the destination. Reindex does not automatically know business transformation rules. If an old field contains values incompatible with the new mapping, documents can fail or require transformation.

### 5.1. Preserving Document IDs and Routing

By default, Reindex preserves _id. This is essential if applications fetch documents by identifier.

If the source uses custom routing, ensure the destination preserves proper routing. Losing routing can place documents on different shards, causing routing-scoped queries to miss data or altering performance. Check routing contracts and Reindex API routing options for your version.

If IDs must change, check for collisions and uniqueness. Never assign fresh random IDs on reruns, as that creates duplicates.

### 5.2. Using Scripts to Transform Sources

Suppose legacy status values have mixed casing and need normalization:

~~~http
POST _reindex
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  },
  "script": {
    "lang": "painless",
    "source": """
      if (ctx._source.status != null) {
        ctx._source.status = ctx._source.status.toLowerCase();
      }
    """
  }
}
~~~

Scripts should perform only well-defined, testable transformations. For complex transformations, use an ingest pipeline or application-level ETL.

### 5.3. Handling Invalid Data

If the new mapping requires priceInCents as long while the source holds non-numeric strings, reindex will report failures on those documents.

Options:

- Clean source data beforehand.
- Transform values in a script per business rules.
- Route failing documents to a quarantine store for later remediation.
- Adjust the mapping if real data legitimately has multiple valid shapes.
- Report failure counts and resolve them before cutover.

Never silently turn invalid values into 0 if 0 carries business meaning. Every transformation needs rules, logs, and auditability.

## 6. Running Reindex Asynchronously and Tracking Tasks

For large indices, reindexing takes significant time. Use wait_for_completion=false to run asynchronously:

~~~http
POST _reindex?wait_for_completion=false
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

The response returns a task ID. Monitor the task:

~~~http
GET _tasks/<task_id>
~~~

List active reindex tasks:

~~~http
GET _tasks?detailed=true&actions=*reindex
~~~

The task status can show total documents, created/updated counts, batch counts, version conflicts, noops, failures, and throttle durations. Exact field names and structure depend on Elasticsearch version; inspect actual responses.

Save the task ID so you can monitor, investigate, or cancel if needed. Canceling a task does not roll back documents already written.

### 6.1. Slicing and Throttling

Reindex supports slicing to parallelize work. More slices can raise throughput at the cost of higher cluster load.

You can tune requests_per_second to throttle speed. Measure CPU, I/O, indexing pressure, merges, and search latency when choosing concurrency. Never run maximum-concurrency reindexing on a live production cluster serving traffic without a capacity plan.

## 7. Reindex Does Not Automatically Catch Up with New Writes

This is the single biggest catch when reindexing a live index.

Reindex reads the source while executing. Documents created or updated after the scan has already passed them may not be reflected in the destination.

Example:

~~~text
T0: products-v1 has 1,000,000 documents
T1: start reindex to products-v2
T2: application updates product P-100
T3: reindex already read P-100 before the update
T4: reindex completes
~~~

products-v2 may hold the stale pre-update version of P-100. Reindex is not CDC and does not continuously tail mutations made after it starts.

You need a strategy to synchronize writes during migration.

## 8. Migration Strategies While the Application Keeps Writing

Three common strategies exist. Pick based on downtime tolerance and complexity.

### 8.1. Pausing Writes During the Migration Window

Workflow:

1. Pause all writers and consumers.
2. Wait for in-flight requests/batches to complete.
3. Reindex source to destination.
4. Verify data and queries.
5. Switch the alias.
6. Resume writers through the alias.

Pros: simple to reason about with no dual-write or replay logic. Cons: write downtime for the duration of reindexing. Fits systems with maintenance windows.

### 8.2. Dual-Writing During the Transition

The application writes to both the old and new indices simultaneously:

~~~text
Application write
       |
       +------> products-v1
       |
       +------> products-v2
~~~

Dual-writing must be enabled before or alongside reindexing, while guarding against the race where reindex overwrites a newer dual-written document in the destination with stale data.

A workable sequence:

1. Enable dual-writing with source version or sequence guards.
2. Start reindexing.
3. Ensure reindex never overwrites newer dual-written documents.
4. Monitor errors on both targets.
5. Wait for reindex completion.
6. Reconcile any documents with differing versions.
7. Switch the alias.
8. Disable dual-writing after verification.

Two writes are not a single transaction. One index can succeed while the other fails. Keep independent retries and reconciliation for each target.

### 8.3. Outbox/CDC and Change Replay

A more flexible approach records every mutation in an ordered outbox or change stream:

~~~text
Database/source of truth
       |
       +----> products-v1
       |
       +----> durable change log
                       |
                       v
                 replay worker
                       |
                       v
                   products-v2
~~~

Workflow:

1. Record the change log checkpoint/sequence.
2. Start reindexing the current snapshot.
3. During reindexing, continue appending change events to the durable log.
4. Once reindexing finishes, replay events from the checkpoint in order.
5. Wait until the destination catches up to the current watermark.
6. Switch the alias.
7. Continue consuming on the new destination.

Handle duplicates, ordering, delete events, and late arrivals. Use event IDs and document versions for idempotent application and stale-event rejection.

Do not rely solely on wall-clock timestamps when the source offers reliable sequence numbers or offsets. Checkpoints must have clear ordering and completeness semantics.

## 9. Version Guards to Prevent Stale Writes Overwriting New Data

If documents carry a monotonically increasing sourceVersion, the destination needs a version-checked write strategy.

Example document:

~~~json
{
  "productId": "P-100",
  "sourceVersion": 42,
  "name": "Wireless Mouse"
}
~~~

Each write carries its version and applies only if it is newer than the currently indexed version. You can use external versioning or conditional update scripts supported by your API/version.

Notes:

- Reindex may preserve Elasticsearch internal versions with its own semantics, which do not automatically equate to your database's sourceVersion.
- External versioning must be configured through the right API parameters.
- Scripts checking sourceVersion must handle the case where the document does not exist yet.
- Deletes require tombstones or version tracking so older events cannot resurrect deleted documents.
- If versions are not monotonic, another ordering mechanism is required.

Never assume the Reindex API automatically uses your sourceVersion field as an external version. Check the exact request parameters or have the replay worker enforce source versions per system contract.

## 10. Verifying Data Before Cutover

Seeing a completed task is not enough to prove the new index is right. Verify both data and application behavior.

Verification checklist:

1. Compare document counts.
2. Compare counts broken down by tenant, status, and category.
3. Spot-check sample documents by ID.
4. Check null/missing fields.
5. Verify routing.
6. Inspect mappings and field capabilities.
7. Run critical queries against both old and new indices.
8. Verify sorting, aggregations, nested queries, scripts, and kNN if used.
9. Verify ACL/security filters.
10. Measure query latency and resource usage.
11. Resolve all reindex failures.
12. Confirm the destination caught up to the change log watermark.

### 10.1. Comparing Counts

~~~http
GET products-v1/_count
GET products-v2/_count
~~~

Matching total counts are a useful signal, not proof of identical contents. Some documents may have failed while others were duplicated, leaving totals equal.

### 10.2. Inspecting Sample Documents

~~~http
GET products-v1/_doc/P-100
GET products-v2/_doc/P-100
~~~

Compare source fields, routing, and metadata. If the new mapping normalizes status, differences may be intentional; verify against transformation rules.

### 10.3. Checking Field Capabilities

~~~http
POST products-v2/_field_caps?fields=status,name,name.keyword,priceInCents,createdAt
~~~

Field capabilities confirm field types and whether fields are searchable and aggregatable. When an alias reads across multiple indices, run this on the alias to detect mapping conflicts.

## 11. Switching Aliases in One Atomic Operation

When the new index is ready, use the Aliases API to remove the alias from the old index and add it to the new index in a single request.

~~~http
POST _aliases
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
~~~

Elasticsearch applies these actions in a single cluster-state update. Clients observe the alias either before or after the update, avoiding any window where the alias is missing from two separate requests.

Never issue a DELETE alias on the old index followed by a separate ADD alias on the new index. Requests arriving in between will fail with alias-not-found errors.

### 11.1. When Separate Read and Write Aliases Exist

Switch both in the same request:

~~~http
POST _aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-read"
      }
    },
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-write"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-read"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
~~~

If the alias carried filter, routing, hidden, or other attributes, redeclare them accurately when adding. Never assume attributes carry over automatically if omitted from the request.

### 11.2. Verifying Aliases After Cutover

~~~http
GET _cat/aliases/products?v
GET _alias/products
~~~

Confirm the alias points to the expected index, write index is right, filters/routing match, no stale index remains unexpectedly attached, and applications target the alias rather than physical index names.

## 12. Cutover and Write Traffic

An atomic alias switch does not automatically make in-flight requests atomic across the index change. A write started before cutover may already have resolved to the old index and complete after the alias flips.

A controlled cutover sequence:

- Pause or flush writers briefly if possible.
- Wait for in-flight bulk requests to finish.
- Capture the change log watermark.
- Replay up to the watermark before switching.
- Switch the alias.
- Confirm new writes land in the new index.
- Resume consumers and monitor lag.

If the system tolerates eventual consistency, you may allow a brief inconsistency window, provided reconciliation runs and user impact is understood.

Never claim zero downtime solely because alias switching is atomic. True zero downtime depends on write synchronization, client retries, and query behavior throughout cutover.

## 13. Rolling Back If the New Index Has Issues

If issues surface after cutover, you can point the alias back to the old index in one Aliases API request:

~~~http
POST _aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v2",
        "alias": "products"
      }
    },
    {
      "add": {
        "index": "products-v1",
        "alias": "products",
        "is_write_index": true
      }
    }
  ]
}
~~~

However, if the application already wrote to products-v2 after cutover, rolling back the alias makes those post-cutover writes invisible through the old alias.

Before rolling back, decide:

- Can post-cutover writes be discarded?
- Can they be replayed into v1?
- Is there a durable outbox/change log?
- Can v2 be reindexed into a fresh rollback index?
- Must writes be paused to reconcile?

Rollback is a data procedure, not just an alias flip. Keep v1 intact and do not delete it during the rollback window.

## 14. Spring Data Elasticsearch: Managing Indices with IndexOperations

Spring Data Elasticsearch provides IndexOperations for index, mapping, and alias operations at the Spring Data layer.

Obtaining operations for a specific index:

~~~java
IndexOperations indexOperations =
    operations.indexOps(IndexCoordinates.of("products-v2"));
~~~

Creating an index if missing:

~~~java
if (!indexOperations.exists()) {
    indexOperations.create();
}
~~~

Reading mappings:

~~~java
Map<String, Object> mapping = indexOperations.getMapping();
~~~

Creating an index and mapping from an entity:

~~~java
IndexOperations indexOperations =
    operations.indexOps(ProductDocument.class);

if (!indexOperations.exists()) {
    indexOperations.create();
    indexOperations.putMapping(
        indexOperations.createMapping()
    );
}
~~~

Method names, return types, and mapping builders depend on the Spring Data Elasticsearch version. For complex settings or mappings, manage JSON resources or IndexSettings explicitly and call the appropriate APIs.

Never call create blindly on every application startup when an index already exists with an old mapping. Production schemas need a controlled migration workflow.

### 14.1. Entities Should Target a Stable Alias

When repositories or templates operate via @Document(indexName = "products"), products can be an alias:

~~~java
@Document(indexName = "products")
public class ProductDocument {
    @Id
    private String productId;
}
~~~

When the alias switches from products-v1 to products-v2, code keeps referencing products.

Audit every repository and custom query configuration for hardcoded physical index names. A single spot referencing products-v1 will keep reading or writing the old index after cutover.

### 14.2. Controlling Automatic Index Creation

If Spring Data creates indices from entities automatically, the generated mapping must match provisioned schemas. When migrations are driven by scripts or deployment pipelines, ensure applications do not write before indices and mappings are created.

You can configure index lifecycle behavior so runtime services do not auto-create production schemas, depending on version and configuration. The key is having a single source of truth for schema management and verifying actual mappings on the cluster.

## 15. Switching Aliases with the Elasticsearch Java API Client

In Spring Data 5.x, you can call the Elasticsearch Java API Client directly for the Aliases API.

Illustrative example:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;

elasticsearchClient.indices().updateAliases(a -> a
    .actions(action -> action
        .remove(r -> r
            .index("products-v1")
            .alias("products")
        )
    )
    .actions(action -> action
        .add(add -> add
            .index("products-v2")
            .alias("products")
            .isWriteIndex(true)
        )
    )
);
~~~

Builder APIs and multi-action syntax vary by client version. You can construct a list of AliasAction objects and pass it once to updateAliases so all changes run in one request.

Never send remove and add as two separate requests. If using a low-level REST client, send a single POST _aliases request with both actions in the same body.

Some Spring Data versions expose AliasActions or IndexOperations alias APIs. Check the Javadoc for your exact version. If the abstraction cannot express required filter, routing, or is_write_index flags, wrap the Java API Client in a dedicated adapter.

Keep cutover logic inside migration components or deployment jobs—never scatter alias switching across business services.

## 16. Reindexing with Aliases and Write Indices

General flow:

~~~text
Before:
  products (alias) -> products-v1

Create:
  products-v2 (new mapping)

Copy:
  products-v1 --_reindex--> products-v2

Validate:
  compare count, sample, queries, mapping

Cutover:
  products (alias) -> products-v2

After:
  products-v1 (retained for rollback)
  products-v2 (active)
~~~

Never point the production alias products at both v1 and v2 simultaneously for the same dataset unless queries carry a generation filter. Doing so causes duplicate hits, inflated counts, and double-counted aggregations.

If you need dual-reads or shadow-reads for validation, query each index directly or use a separate alias. Never point the production alias at both indices just for testing.

## 17. Common Pitfalls When Reindexing

| Symptom | Possible cause | Resolution |
|---|---|---|
| Reindex fails on some documents | Data incompatible with new mapping | Inspect failures, fix transforms/data, and replay |
| Destination count lower than source | Failed items, source query filter, or incomplete task | Check task response and counts |
| New documents missing | Writes occurred after reindex scan passed them | Dual-write, outbox/CDC, or pause writes |
| Newer data overwritten by older data | Race between reindex and dual-write | Version guards and reconciliation |
| New sort/aggregation lacks old data | Multi-field not backfilled | Reindex or update by query |
| Alias has no write target | Missing is_write_index when alias spans indices | Set write index explicitly |
| App still writes to old index | Hardcoded physical index name | Switch configuration to alias |
| Cutover causes brief errors | Remove and add sent in two separate requests | Combine into one updateAliases request |
| Rollback loses post-cutover writes | Flipped alias back without replaying writes | Reconcile or replay change log |
| Routing queries miss documents | Reindex did not preserve routing | Preserve routing settings |
| Reindex overloads cluster | Too many slices or high concurrency | Throttle and schedule during low-load windows |
| New index gains unexpected fields | Uncontrolled dynamic mapping | Use explicit mappings and dynamic templates |
| New index has wrong analyzer | Settings not applied at creation | Recreate empty index before reindexing |
| Alias reading v1 and v2 duplicates hits | Same documents exist in both | Point only to active generation or filter |
| App auto-creates divergent mapping | Inconsistent auto-create lifecycle | Centralize schema ownership |

## 18. Pre-, Mid-, and Post-Cutover Checklists

### Before Migration

- [ ] Confirm current index and aliases.
- [ ] Identify all writers and readers.
- [ ] Save existing mappings/settings and take snapshots per policy.
- [ ] Design destination mappings and settings.
- [ ] Create the new versioned index.
- [ ] Verify analyzers, field types, and templates.
- [ ] Choose pause-writes, dual-write, or outbox/CDC strategy.
- [ ] Prepare rollback and replay procedures.

### During Reindex

- [ ] Record the task ID.
- [ ] Monitor progress, failures, and throttling.
- [ ] Watch CPU, heap, disk, and indexing pressure.
- [ ] Ensure new writes are captured.
- [ ] Verify versions and routing.
- [ ] Handle failed items and rerun selectively.

### Before Cutover

- [ ] Counts and sample documents match expectations.
- [ ] Zero unresolved reindex failures.
- [ ] Change log caught up to watermark.
- [ ] Queries, filters, sorts, and aggregations behave properly.
- [ ] ACLs, tenant filters, and routing work properly.
- [ ] Read/write alias actions are prepared.
- [ ] Writers are in a safe state for cutover.

### After Cutover

- [ ] Confirm aliases point to the new index.
- [ ] Confirm is_write_index is set properly.
- [ ] Verify reads and writes through the alias.
- [ ] Monitor errors, latency, and indexing rate.
- [ ] Reconcile source vs. index versions.
- [ ] Retain the old index throughout the rollback window.
- [ ] Delete the old index only after confirming retention and rollback policies.

## 19. Complete REST API Walkthrough Example

The steps below illustrate a straightforward migration where writes can be paused briefly. Systems that cannot pause writes must add dual-write or outbox/CDC synchronization.

### Step 1: Verify Current Alias

~~~http
GET _alias/products
~~~

Assume alias products currently points to products-v1.

### Step 2: Create the New Index

~~~http
PUT products-v2
{
  "mappings": {
    "properties": {
      "productId": { "type": "keyword" },
      "name": {
        "type": "text",
        "fields": {
          "keyword": { "type": "keyword" }
        }
      },
      "status": { "type": "keyword" },
      "priceInCents": { "type": "long" }
    }
  }
}
~~~

### Step 3: Run Reindex

~~~http
POST _reindex?wait_for_completion=true
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

Inspect the response to verify failures is empty and created/updated counts look right.

### Step 4: Verify Data

~~~http
GET products-v1/_count
GET products-v2/_count
GET products-v2/_mapping
~~~

Execute representative queries and inspect sample documents.

### Step 5: Atomic Alias Switch

~~~http
POST _aliases
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
~~~

### Step 6: Verify Reads and Writes

~~~http
GET _alias/products
GET products/_search
~~~

Verify through the application that reads and writes flow through the new alias. Never insert dummy test records into production just to verify unless a cleanup step is in place.

### Step 7: Retain the Old Index

Keep products-v1 for the duration of the rollback window. Delete it only after verifying traffic, data integrity, backups, and retention policies.

## 20. Operating Migrations in Spring Data Elasticsearch

Isolate migration steps into a dedicated deployment step or job:

- Schema definition: versioned mappings and settings.
- Index provisioner: creates the destination index and verifies schema.
- Reindex runner: starts and tracks reindex tasks.
- Data validator: checks counts, samples, and queries.
- Alias switcher: executes a single atomic Aliases API update.
- Cleanup job: removes the old index after the rollback window.

Business services should reference only the stable alias. Never let individual application replicas decide independently when to flip aliases during rolling deployments.

Configuration can store the stable aliases:

~~~yaml
app:
  elasticsearch:
    read-alias: products
    write-alias: products
~~~

When aliases are the source of truth for the active index, avoid maintaining a second active-index config property that can drift from the alias. Runtime services need only the alias; migration jobs alone need physical index names.

### 20.1. Separating Runtime and Migration Privileges

Runtime applications typically only need read/write access to allowed aliases and indices. Migration jobs need permissions to create indices, run reindex, update aliases, and later delete indices.

Separating runtime roles from migration roles prevents regular services from deleting indices or mutating aliases accidentally. Never grant delete-index permissions to every application instance just because it performs CRUD.

## 21. When to Use Data Streams Instead of Aliases

Data streams fit append-only time-series data such as logs, metrics, or events. Writes go to the current backing index, and rollover creates new backing indices.

For entity data updated or deleted by ID, aliases pointing to versioned indices are usually easier to manage. Data streams follow specific rules regarding write indices, backing indices, and updates/deletes; do not swap them in mechanically for alias migrations.

If your system already uses data streams, consult the corresponding migration APIs and template/rollover policies. This lesson focuses on aliases over regular indices.

## 22. Quick Reference Table

| Need | Approach |
|---|---|
| Change field type | Create a new index and reindex |
| Change analyzer/settings | Create a new index with target settings |
| Backfill a multi-field on old data | Reindex or update by query |
| Keep index name stable | Use an alias |
| Copy documents | Reindex API |
| Track long reindex jobs | wait_for_completion=false and Tasks API |
| Reduce reindex load | Slices and throttling sized to cluster capacity |
| Catch up with live writes | Pause writes, dual-write, or outbox/CDC |
| Prevent stale events overwriting | Source versions and version guards |
| Switch alias without downtime gap | Single Aliases API request with remove + add |
| Alias pointing to multiple indices | Set is_write_index explicitly |
| Validate data | Counts, samples, field caps, and query regressions |
| Rollback | Switch alias back after reconciling writes |
| Keep schemas consistent | Index templates and versioned mappings |
| Spring Data index management | IndexOperations and migration components |
| Delete old index | After rollback window and retention checks |

Changing mappings via reindexing and alias switching provides a controlled schema migration workflow. Create a new versioned index with complete settings and mappings, reindex documents, handle transformations and failures, synchronize writes made during the copy, and verify counts, samples, queries, and field capabilities. Switch read/write aliases in a single Aliases API request for an atomic cluster-state update. Aliases keep application names stable, but they do not automatically dual-write, catch up with mutations, or safeguard rollbacks. Use source versions, outbox/CDC, or planned write pauses; retain the old index for rollback; and delete it only after data, traffic, and retention requirements are verified.
