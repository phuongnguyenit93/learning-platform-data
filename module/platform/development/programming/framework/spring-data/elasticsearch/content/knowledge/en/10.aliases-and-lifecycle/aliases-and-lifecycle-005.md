# Workflow for Creating a New Index, Reindexing, Verifying, and Switching Aliases

When you need to change the mapping, analyzer, or primary shard count of an Elasticsearch index, an application typically cannot modify the existing structure directly in place. The common approach is to create a new versioned index, copy data using the Reindex API, verify the new index, and then switch the alias so the application continues using the same logical name.

For example, the application currently reads and writes through the `products` alias, which points to the physical index `products-v1`. When structural changes are needed, you create `products-v2`, migrate data there, verify it, and switch the `products` alias to the new index. Application code continues using the stable alias name.

## 1. Physical indices and aliases

A physical index is where Elasticsearch stores documents, shards, mappings, and settings. An alias is a logical name pointing to one or more indices. Applications can send requests to an alias in nearly the same way as sending requests to an index name.

~~~mermaid
flowchart LR
    A["Spring Data Elasticsearch"] -->|"products"| B["Alias products"]
    B --> C["products-v1"]
    D["Migration workflow"] --> E["products-v2"]
    B -. "after switching alias" .-> E
~~~

Key benefits of aliases:

- The application keeps the same access name when the physical index changes.
- You can prepare and verify the new index before switching the application to the new data.
- You can switch the alias with a single alias update operation, avoiding any window where the alias points to no index.
- You can keep the old index for a period of time to support rollback.

An alias does not store documents of its own and does not replace index mappings/settings. It simply routes requests to target indices, optionally with filters, routing, or a designated write index.

### 1.1. Versioned index naming

Separate physical index names from alias names. For example:

| Type | Name | Role |
| --- | --- | --- |
| Old physical index | `products-v1` | Holds current data and mapping. |
| New physical index | `products-v2` | Target of the migration. |
| Application alias | `products` | Stable name used by the application for reads and writes. |

Do not create a physical index named `products` if you want to use `products` as an alias; a name cannot simultaneously be both an index name and an alias. You can use version suffixes, deployment dates, or sequence numbers to manage index generations.

### 1.2. Read and write aliases

An alias can point to multiple indices for reads. When an alias points to multiple indices, you must specify which index receives write operations using `is_write_index: true`. Without an explicit write index in a multi-index setup, write operations through the alias may be rejected.

For a simple model, a single `products` alias can handle both reads and writes and point to one physical index at a time. During a version upgrade, the alias is switched from `products-v1` to `products-v2`.

For systems with special requirements, you can use two aliases such as `products-read` and `products-write`. In that case, the application must be configured with the proper role for each alias; do not separate aliases without a specific need.

## 2. General migration workflow

An index change typically consists of the following steps:

1. Identify the current index, alias, and applications using them.
2. Design settings and mappings for the new versioned index.
3. Create the new index with a distinct physical name.
4. Reindex data from the old index to the new index.
5. Verify counts, contents, mappings, settings, and query behavior.
6. Synchronize changes that occurred during reindexing.
7. Switch the alias to the new index.
8. Monitor the application and keep the old index during the rollback window.
9. Delete the old index once the retention period expires and rollback is no longer needed.

An important point is that **the Reindex API only copies documents**. It does not automatically copy settings, mappings, analyzers, or aliases from the source index to the destination index. The destination index must be created and configured beforehand.

## 3. Surveying the current index

Before creating the new index, check where the alias currently points:

~~~http
GET /_alias/products
~~~

You can inspect the alias using the cat API:

~~~http
GET /_cat/aliases/products?v
~~~

Read the mapping and settings of the current physical index:

~~~http
GET /products-v1/_mapping
~~~

~~~http
GET /products-v1/_settings?include_defaults=true
~~~

Record the necessary information:

- Physical index name and alias currently in use.
- Mappings of all fields, including `text`, `keyword`, object, nested, date, and business fields.
- Analyzers, normalizers, and important index settings.
- Document count, index size, and normal write throughput.
- Filters, routing, and write index configured on the alias.
- Whether applications, background jobs, or other consumers access the physical index directly or through the alias.

Do not assume every client uses the alias. If a job still calls `products-v1` directly, switching the alias will not move that job to the new index. Locate and switch consumers to the alias if you want centralized lifecycle management.

## 4. Creating the new index version

Suppose we need to create `products-v2` with a new mapping and two primary shards. Declare settings and mappings in the index creation request:

~~~http
PUT /products-v2
Content-Type: application/json

{
  "settings": {
    "number_of_shards": 2,
    "number_of_replicas": 0,
    "analysis": {
      "analyzer": {
        "catalog_text_v2": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "catalog_text_v2",
        "fields": {
          "raw": {
            "type": "keyword"
          }
        }
      },
      "sku": {
        "type": "keyword"
      },
      "priceInCents": {
        "type": "long"
      },
      "active": {
        "type": "boolean"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
~~~

The new index has settings and mappings independent from the old index. Choose the number of primary shards at creation time because `index.number_of_shards` cannot be changed directly afterward. Analyzer definitions must exist in settings before mapping fields reference those analyzers.

Inspect the newly created index:

~~~http
GET /products-v2/_mapping
~~~

~~~http
GET /products-v2/_settings
~~~

Do not attach the application alias to the new index at this step. We need to complete copying and verification before switching traffic.

## 5. Copying data using the Reindex API

### 5.1. Synchronous reindex

For small datasets or learning environments, you can run a synchronous reindex:

~~~http
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
~~~

Elasticsearch reads documents from `products-v1` and writes them to `products-v2`. By default, document `_id` values are preserved, allowing the application to continue looking up by old IDs.

Reindex requires `_source` in the source index to read document contents. If the source index does not store `_source`, you cannot use the standard reindex workflow to copy full contents as shown in the example.

### 5.2. Asynchronous reindex for large datasets

For large indices, you can run a background request to receive a task ID:

~~~http
POST /_reindex?wait_for_completion=false&slices=auto
Content-Type: application/json

{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

The response returns a `task` ID. Monitor progress with:

~~~http
GET /_tasks/<task-id>
~~~

When the task completes, inspect fields such as `total`, `created`, `updated`, `version_conflicts`, `noops`, `retries`, and `failures`. An HTTP 200 response alone is not enough to conclude all documents were copied; you must read the task result and address any reported failures.

You can throttle the reindex rate using `requests_per_second` to reduce impact on a cluster serving live traffic. Depending on scale, monitor heap, CPU, disk I/O, search/write latency, and shard allocation throughout the process.

### 5.3. Transforming data during reindex

Reindex supports scripts to transform `_source` while copying. For example, renaming field `oldName` to `name`:

~~~http
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
    "source": "if (ctx._source.containsKey(\u0027oldName\u0027)) { ctx._source.name = ctx._source.remove(\u0027oldName\u0027); }"
  }
}
~~~

When using scripts, clearly define how to handle documents missing the field, null values, legacy data types, and field name conflicts. Test on a small dataset before running on the entire index.

## 6. Synchronizing changes that occur during reindex

This step is easy to overlook. Reindex reads a snapshot-like view of data from the source at the time it starts. If the application continues writing to the old index while reindex is running, changes occurring after the read point may be missing in the destination index. Deletions are also not automatically propagated to the destination just by running the initial reindex.

There are two common strategies:

### 6.1. Migration with a write-freeze window

This is simple and easy to control for small systems or environments that permit a maintenance window:

1. Pause APIs/jobs writing to the source index.
2. Wait for in-flight requests to complete.
3. If the destination index already holds data from an earlier test run, delete and recreate the destination index or ensure it is in a clean state as planned.
4. Run a full reindex from source to destination.
5. Refresh the destination index, verify counts and contents.
6. Switch the alias to the new index.
7. Confirm the application reads/writes through the alias successfully, then reopen writes.

Because no new writes or deletes occur during copying, source data stays stable and reindex results can be compared more accurately. Estimate the write-freeze duration beforehand based on index size and reindex throughput.

### 6.2. Near-zero-downtime migration

For systems that must continue accepting writes during backfill, you need a dedicated change synchronization mechanism, for example:

- Have the application dual-write to both the old and new indices temporarily.
- Record changes in an outbox/event log and replay them to the new index.
- Use change data capture or a synchronization pipeline capable of tracking updates and deletes.

The workflow typically consists of initial data backfill, replaying change events in order, briefly pausing writes to drain remaining events, verifying, and switching the alias.

Simply running `_reindex` a second time is not sufficient to accurately sync all changes. A document deleted from the source after the first read may still remain in the destination; reindex does not automatically remove stale documents from the destination. When using dual-write or event replay, you must handle inserts, updates, deletes, event ordering, retries, and idempotency.

## 7. Verifying the target index before switching the alias

Only switch the alias when the new index meets data and query requirements. You can verify across multiple layers.

### 7.1. Checking reindex results

For synchronous reindex, read the response and verify:

- `timed_out` is `false`.
- Processed documents (`total`) match the source count at migration time.
- `created` and `updated` match the state of the destination index.
- `version_conflicts` is `0`, unless conflicts were expected and have a handling plan.
- The `failures` array is empty.

For background reindex, monitor the task until completion and read the final response payload, rather than only checking that the task disappeared from the running tasks list.

### 7.2. Refreshing and comparing counts

Ensure newly indexed documents are searchable:

~~~http
POST /products-v2/_refresh
~~~

Count documents in both indices:

~~~http
GET /products-v1/_count
~~~

~~~http
GET /products-v2/_count
~~~

Comparing counts is only meaningful when source data is stable or all changes have been fully synchronized. If the application is still writing to the source, the two numbers may legitimately differ during migration.

### 7.3. Checking mappings and settings

Read back destination mappings and settings to ensure the configuration matches the design:

~~~http
GET /products-v2/_mapping
~~~

~~~http
GET /products-v2/_settings
~~~

Check critical items such as field types, analyzers, normalizers, nested paths, primary shard count, and replicas. Reindex does not carry mappings from source to destination; an incorrect mapping can let documents index successfully while causing subsequent queries to behave unexpectedly.

### 7.4. Checking documents and query behavior

Fetch several representative documents by ID from both source and destination indices:

~~~http
GET /products-v1/_doc/KB-001
~~~

~~~http
GET /products-v2/_doc/KB-001
~~~

Compare `_source`, key fields, null values, collections, nested objects, and transformed fields. Then execute key business queries on the destination index: full-text search, exact filtering, range queries, sorting, aggregations, and nested queries if applicable.

You can use aggregations or verification queries to compare data distributions, such as active product counts, counts grouped by status, or price ranges. For critical data, maintain a set of sample IDs and business invariants to verify beyond simple count checks.

### 7.5. Checking cluster health

~~~http
GET /_cluster/health/products-v2?pretty
~~~

Verify primary shards are allocated and replicas reach the expected status. A `yellow` status in a single-node cluster may occur because replicas have no second node; evaluate this based on the environment's topology and replica policy.

## 8. Switching the alias with an atomic operation

Once the new index is ready, switch the `products` alias from `products-v1` to `products-v2` with a single `_aliases` request containing remove and add actions:

~~~http
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
~~~

Elasticsearch applies the alias actions within a single cluster state update. Clients accessing the alias are routed according to the new configuration once the update takes effect. This avoids the gap caused by removing an alias in one request and re-adding it in another.

If the current alias has filters or routing, preserve those attributes in the `add` action. If the alias points to multiple indices, clearly define read indices and the write index after switching; do not remove or add aliases in a way that drops needed routing/filter settings.

Verify the result:

~~~http
GET /_alias/products
~~~

~~~http
GET /_cat/aliases/products?v
~~~

You can create the alias initially using:

~~~http
POST /_aliases
Content-Type: application/json

{
  "actions": [
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

There is no need to rename physical indices or move documents just to change the logical name. The application continues sending requests to `products`, while Elasticsearch routes to whichever index the alias references.

## 9. Using aliases in Spring Data Elasticsearch

A Spring Data entity can specify the alias name in `@Document` so the repository operates through the alias:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products", createIndex = false)
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String sku;

    // Constructor, getters, and setters
}
~~~

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository extends ElasticsearchRepository<Product, String> {
}
~~~

Here `products` is an alias managed by the migration process. `createIndex = false` prevents Spring Data from automatically creating an index named after the alias when initializing entity metadata; the physical index is created and configured separately before the alias is switched to it.

When calling `productRepository.save(product)` or `findById`, the client sends requests to `products`. After the alias switch, requests route to `products-v2` without changing the index name in repository code.

For migrations, use the REST API or `IndexOperations` with specific physical index names such as `products-v2` to create and inspect the destination index. Do not use the application alias as a physical index name during creation. Index and alias management APIs can have differing method signatures across Spring Data Elasticsearch versions; the REST APIs above express the Elasticsearch operations directly.

If the application uses multiple aliases or separates read/write aliases, configure `@Document(indexName = "...")` according to the alias the repository actually needs to use and verify write behavior through the write alias. Do not point the repository to a versioned physical index name if you want index replacements to be independent of application code.

## 10. Rollback and retaining the old index

Do not delete `products-v1` immediately after switching the alias to `products-v2`. Retain the old index during an observation window so you can revert if mapping, data, or query issues are discovered.

If no new writes occurred on the destination index after cutover, you can switch the alias back with an atomic request:

~~~http
POST /_aliases
Content-Type: application/json

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

**Note on post-cutover writes:** once the application has written new documents or updated documents on `products-v2`, switching the alias back to `products-v1` can hide those changes from the application. Before rolling back, decide how to sync post-cutover writes back to the old index, or accept restoring to an earlier data point as an operational decision. An alias switch only changes routing; it does not copy data between the two indices.

Retain the old index along with migration details, mappings, settings, and the cutover timestamp. After the observation period, once you confirm rollback is no longer needed and proper backups exist, delete the old index by its specific physical name.

~~~http
DELETE /products-v1
~~~

Do not send a DELETE command to the application alias when the goal is to delete an old index. Verify the exact physical index name before deleting to avoid wiping active production data.

## 11. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Reindex succeeds but destination mapping is wrong | Assumed the Reindex API copies mappings/settings. | Create the destination index with settings and mappings before reindexing. |
| Source and destination counts differ | Source still receives writes/deletes, reindex had errors, or destination had data from a previous run. | Check response/task, failures, version conflicts, and change-sync strategy. |
| New documents do not appear in destination index | Documents were written to source after reindex read past that point. | Pause writes or use dual-write/CDC to catch up inserts, updates, and deletes. |
| Alias fails to switch | Wrong alias/index name, missing alias admin permissions, or invalid action. | Check current alias, index names, privileges, and `_aliases` response. |
| Writes through alias rejected | Alias points to multiple indices without an explicit write index. | Set `is_write_index: true` on the write-receiving index. |
| Repository auto-creates an index named as the alias | Entity configuration allows auto-create or migration has not created the alias yet. | Manage schema/aliases separately and consider `createIndex = false`. |
| Rollback loses new data | Application already wrote to the new index after cutover. | Sync changes back or choose a controlled recovery plan before switching the alias. |

## 12. Migration deployment checklist

### Before starting

- [ ] Identify the alias and all consumers accessing the index.
- [ ] Save mappings, settings, document counts, and key business queries of the old index.
- [ ] Design new mappings/settings and choose a versioned physical index name.
- [ ] Decide whether migration uses a write-freeze window or requires dual-write/CDC.
- [ ] Prepare a rollback plan and retention period for the old index.

### During migration

- [ ] Create the destination index before reindexing.
- [ ] Monitor the reindex task, retries, version conflicts, and failures.
- [ ] Synchronize incoming changes, including deletes.
- [ ] Refresh the destination index and verify counts, mappings, settings, sample documents, queries, and cluster health.
- [ ] Switch the alias via a single atomic `_aliases` request and set the write index explicitly.

### After switching the alias

- [ ] Confirm the alias points to the new index.
- [ ] Test repository reads and writes through the alias.
- [ ] Monitor logs, query errors, latency, throughput, and shard status.
- [ ] Keep the old index for the defined rollback window.
- [ ] Delete the old index only after confirming the new data is stable and rollback is no longer needed.

## 13. Condensed practice workflow

For a learning environment where writes can be paused, a sample workflow is:

1. Create `products-v2` with the desired settings and mapping.
2. Pause the application or write stream to `products-v1`.
3. Run `POST /_reindex` from `products-v1` to `products-v2`.
4. Refresh `products-v2`, read the reindex response, and compare `_count`.
5. Verify mappings, settings, sample documents, and key queries.
6. Switch the `products` alias via a single `_aliases` request removing the old index and adding the new index with `is_write_index: true`.
7. Inspect the alias and run a test read/write through the repository.
8. Reopen the write stream and monitor the system.
9. Retain `products-v1` until the rollback window ends.

In Spring Data Elasticsearch, repositories should access data through a stable alias declared in `@Document`. Physical indices are created and migrated independently. Reindexing moves documents between two existing indices; data and mapping verification confirms the destination index is ready; the alias switch updates where the application reads/writes without changing logical names in code. Synchronizing incoming writes/deletes and keeping a rollback plan are essential to ensure migrations do not lose data.
