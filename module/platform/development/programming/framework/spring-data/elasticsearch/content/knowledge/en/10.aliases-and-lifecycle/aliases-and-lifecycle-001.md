# What an Alias Is and How to Decouple Logical Names from Physical Indices

## 1. What is an alias?

In Elasticsearch, an **index alias** is a logical name that points to one or more physical indices. An application can send queries or write operations through an alias without needing to know the name of the index currently holding the actual data.

For example, the system is storing data in the index:

~~~text
products-v1
~~~

Instead of letting the application depend directly on that name, we create an alias:

~~~text
products  ->  products-v1
~~~

The application only uses the name `products`. When it is necessary to replace the physical index, an administrator or deployment pipeline can switch the alias to `products-v2` without modifying the index name across every service.

An alias is metadata in the cluster, not a second index, and it does not duplicate data. It has no shards, mappings, or documents of its own. All data remains in the physical index that the alias points to.

## 2. Distinguishing logical names and physical index names

A physical index name usually indicates the generation or creation time of the data. An alias name represents the business concept that the application wants to access.

| Component | Example | Role |
|---|---|---|
| Physical index | `products-v1` | Where documents, mappings, and shards are actually stored |
| Logical alias | `products` | Stable name used by the application |
| New physical index | `products-v2` | New index generation that can change mappings or settings |
| Read alias | `products-read` | Logical name used for read queries |
| Write alias | `products-write` | Logical name used for write operations |

Diagram:

~~~text
Spring Data Elasticsearch application
              |
              | uses name "products"
              v
        Alias: products
              |
              v
        Index: products-v1
              |
              v
        Documents and shards
~~~

After switching to the new generation:

~~~text
Spring Data Elasticsearch application
              |
              | still uses name "products"
              v
        Alias: products
              |
              v
        Index: products-v2
              |
              v
        Documents and shards
~~~

The application continues using the same logical name. The change lies in the relationship between the alias and the physical index.

Aliases are especially useful when:

- You need to change mappings or analyzers when the old mapping cannot be modified in place.
- You want to deploy a new-generation index and switch over while minimizing disruption.
- You want to decouple the name used by the application from index naming conventions based on version or date.
- You want to provide stable read/write names for multiple indices.
- You want to restrict search scope using an alias filter or routing.

## 3. Creating an index and attaching an alias

You can create the physical index first:

~~~http
PUT /products-v1
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      }
    }
  }
}
~~~

Then attach the alias `products` to the index:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-v1",
        "alias": "products"
      }
    }
  ]
}
~~~

From that point on, you can query through the alias:

~~~http
GET /products/_search
{
  "query": {
    "match": {
      "name": "wireless headphones"
    }
  }
}
~~~

Elasticsearch resolves the name `products` to the physical index that the alias currently points to. The application does not need to send the name `products-v1`.

You can inspect the alias:

~~~http
GET /_alias/products
~~~

Or view all aliases:

~~~http
GET /_cat/aliases?v
~~~

An alias can point to one index or multiple indices. When an alias points to multiple indices, read queries are typically executed across all target indices. Therefore, you must ensure that the mappings across those indices are compatible with the queries the application sends through the alias.

An alias name cannot simultaneously be the name of another physical index. Reserve a logical naming namespace such as `products`, `products-read`, and `products-write`, while physical indices use versioned names such as `products-v1` and `products-v2`.

## 4. Read aliases and write aliases

In larger systems, you can separate the read alias and write alias:

~~~text
products-read   -> indices serving search queries
products-write  -> index receiving new documents and updates
~~~

Separating the two aliases helps the application clearly control read and write flows. For example, the read alias can point to multiple time-based indices, while the write alias points only to the current active index.

Create both aliases pointing to the first index:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-v1",
        "alias": "products-read"
      }
    },
    {
      "add": {
        "index": "products-v1",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
~~~

The application uses:

- `products-read` for search, filtering, and aggregations.
- `products-write` for indexing, updating, and deleting documents.

If an alias points to exactly one index, Elasticsearch can treat that index as the write index by default. However, when an alias points to multiple indices, you must explicitly designate the index that receives writes using `is_write_index: true`. If no write index is defined in a multi-index case, write operations through the alias can fail because Elasticsearch does not know where to write.

Having an alias with multiple target indices does not mean write operations will automatically write to all indices. An alias has only one designated write index for write operations. Read queries through a multi-index alias can search across all target indices.

If there is only one target index, you can use the same alias for both reads and writes. Separating read and write aliases is an architectural choice, not a mandatory requirement.

## 5. Switching aliases between indices atomically

One of the most important benefits of aliases is the ability to redirect from an old index to a new index in a single `_aliases` request.

Suppose currently:

~~~text
products -> products-v1
~~~

We have created `products-v2` and loaded the required data. We can switch the alias:

~~~http
POST /_aliases
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

The remove and add actions in the same alias request are applied as an atomic cluster state update. Clients do not observe an intermediate state where the alias has been removed from the old index but not yet attached to the new index.

Before switching:

~~~text
products -> products-v1
~~~

After switching:

~~~text
products -> products-v2
~~~

The application continues sending requests to `products`. The new alias points to the new index once the update completes.

If using separate read and write aliases, switch both in the same operation:

~~~http
POST /_aliases
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

Atomic alias switching makes request redirection consistent. However, it does not move data automatically, does not synchronize changes that occur during reindexing, and does not guarantee that the new index already contains complete data. Those tasks must be handled before switching the alias.

## 6. Using aliases to upgrade mappings and reindex

The mapping of an already indexed field usually cannot be changed arbitrarily in place. For example, `name` was originally `text`, but the new system needs a different analyzer configuration. The common approach is to create a new index with the new mapping/settings and then reindex the data.

General workflow:

~~~text
products-v1
    |
    | current data
    v
Create products-v2 with new mapping
    |
    v
Reindex from products-v1 to products-v2
    |
    v
Verify document count and query results
    |
    v
Switch alias products to products-v2
    |
    v
Application continues using alias products
~~~

### Step 1: create the new index

~~~http
PUT /products-v2
{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "standard"
      },
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      },
      "brand": {
        "type": "keyword"
      }
    }
  }
}
~~~

### Step 2: copy documents

Use the Reindex API to copy data from the old index to the new index:

~~~http
POST /_reindex
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

Reindex reads documents from the source and writes them to the destination. It does not copy aliases; aliases must be created or switched separately.

### Step 3: verify the new index

You can compare document counts:

~~~http
GET /products-v1/_count
GET /products-v2/_count
~~~

Then verify mappings, important queries, representative documents, and aggregations. Matching document counts alone is not enough to prove the new data is accurate; you must check the changed fields and critical business cases.

### Step 4: switch the alias

Once the new index is ready, use `_aliases` to switch the alias from `products-v1` to `products-v2`.

### Step 5: keep the old index for rollback

Do not delete the old index immediately after switching the alias. Keep it for a period of time for comparison or rollback if an error is discovered. Only delete the old index once you are certain it is no longer needed, according to the data lifecycle management process.

### Notes when the system still receives writes during reindex

Reindex does not automatically create a continuously synchronized replica. If the application continues writing to `products-v1` after reindex has already read past the corresponding document, new changes may not appear in `products-v2`.

You must choose an appropriate synchronization strategy:

- Pause writes briefly, run a final sync, verify, and then switch the alias.
- Use a transactional outbox or change data capture to record changes that occur during reindexing and apply them to the new index.
- Use a controlled dual-write workflow, ensuring proper error handling and update ordering between both indices.
- Split the migration into phases with catch-up and a short controlled cutover window.

Do not simply run `_reindex`, see roughly equal document counts, and switch the alias while the system still has heavy write traffic. The alias switch is atomic, but the preceding data copy process is not an atomic transaction with application writes.

## 7. An alias can point to multiple indices

An alias can represent a set of indices. For example, a system stores product data by year:

~~~text
products-2025
products-2026
products-2027

products-all -> products-2025
             -> products-2026
             -> products-2027
~~~

When searching through `products-all`, Elasticsearch can query all indices that the alias points to. This approach is useful for time-partitioned data or datasets sharing the same model.

Example of creating a read alias across multiple indices:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-2025",
        "alias": "products-all"
      }
    },
    {
      "add": {
        "index": "products-2026",
        "alias": "products-all"
      }
    }
  ]
}
~~~

If an alias has multiple indices, keep in mind:

- Index mappings must be compatible with shared queries.
- A field with different types across indices can cause errors or inconsistent results.
- Queries and aggregations can consume more resources because they must process multiple indices.
- Write operations need an explicitly designated write index.
- When multiple indices contain copies of the same document, search results may show business-level duplicates.

Do not use a multi-index alias to arbitrarily combine incompatible mapping generations. When upgrading mappings, you typically switch the alias to a new-generation index after reindexing rather than keeping both generations under the same read alias long-term.

## 8. Filtered alias: restricting the document set on read

An alias can have a filter so that search operations through the alias only see documents matching a condition.

Example of creating an alias that only shows active products:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-v2",
        "alias": "active-products",
        "filter": {
          "term": {
            "status": "ACTIVE"
          }
        }
      }
    }
  ]
}
~~~

Querying through the alias:

~~~http
GET /active-products/_search
{
  "query": {
    "match_all": {}
  }
}
~~~

The alias filter is combined with the search query to restrict matching documents. The application can use logical names such as `active-products` and `archived-products` for different datasets.

Keep in mind that an alias filter is not a security mechanism. It does not replace authentication, authorization, or document-level security. Filters primarily apply to read queries; do not rely on them to prevent an application from writing a document with an inappropriate `status` through the alias. If data access restrictions are required, security must be configured at the Elasticsearch or application layer.

## 9. Aliases and routing

An alias can also configure routing to limit which shards a request hits. This is useful when the system intentionally uses custom routing, such as partitioning documents by tenant.

Example of an alias attached to fixed routing:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-v2",
        "alias": "tenant-42-products",
        "index_routing": "tenant-42",
        "search_routing": "tenant-42"
      }
    }
  ]
}
~~~

Where:

- `index_routing` specifies the routing used when writing through the alias.
- `search_routing` specifies the routing used when searching through the alias.

Routing can reduce the number of shards queried if data distribution is designed appropriately. However, routing must be consistent with how documents are indexed. If a document was written with different routing, queries through the alias may not find that document.

Do not use routing as a substitute for access control. Routing only controls how Elasticsearch routes to shards; it does not authenticate users or guarantee that one tenant cannot access another tenant's data.

## 10. Using aliases in Spring Data Elasticsearch

Spring Data Elasticsearch works with indices through entity metadata. The `indexName` attribute in `@Document` can be set to the logical alias name.

Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(
    indexName = "products",
    createIndex = false
)
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    // Constructors, getters and setters
}
~~~

In this example:

- `indexName = "products"` is the alias name used by the repository or operations.
- `createIndex = false` prevents the entity's automatic index creation mechanism from attempting to create a physical index named `products` when this alias is already managed externally.
- The actual physical index may be `products-v1`, `products-v2`, or another name managed by the deployment process.

When the repository saves or searches for `ProductDocument`, Spring Data uses the index coordinates obtained from the entity metadata. If the `products` alias has already been created and points to the right index, the application can operate through the alias.

Repository example:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
~~~

The service does not need to know the physical index:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public ProductDocument save(ProductDocument product) {
        return productRepository.save(product);
    }
}
~~~

If you want to separate read and write aliases, you can pass the corresponding `IndexCoordinates` when calling the operations API or design separate repositories/services for each flow. Ensure that write operations go through an alias with a designated write index.

One important note: index creation operations from `IndexOperations` operate on physical indices. Do not invoke index creation with an existing alias name as if the alias were a new index. The provisioning process should create the physical index, mapping, and alias first; the application then uses the alias to access data.

## 11. Managing aliases with IndexOperations and Elasticsearch APIs

Spring Data Elasticsearch provides abstractions to operate on indices, mappings, and aliases via `IndexOperations`. You can obtain the operations object by entity or by `IndexCoordinates`.

Example of obtaining `IndexOperations`:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

IndexOperations indexOperations =
    operations.indexOps(IndexCoordinates.of("products-v2"));
~~~

From `IndexOperations`, the application can perform index and mapping operations supported by the abstraction. Specific alias APIs may vary across Spring Data Elasticsearch versions; when complex alias operations such as changing multiple aliases in one request are needed, using the Elasticsearch Java API Client or the `_aliases` REST API is a direct approach that maps cleanly to the Elasticsearch documentation.

Do not let every application instance create, delete, or switch aliases on startup. Multiple replicas running migrations concurrently can cause contention or unexpected state changes. Index/alias lifecycles should be managed by a controlled deployment step or migration job, while application instances only use provisioned aliases.

## 12. Aliases and rollover

An application writing data continuously can use a write alias combined with rollover to create a new physical index when the current index meets conditions on size, age, or document count.

Example:

~~~text
events-write -> events-000001
~~~

When the rollover condition is met, Elasticsearch creates the next index and switches the write alias to the new index:

~~~text
events-write -> events-000002
~~~

Example of calling the rollover API:

~~~http
POST /events-write/_rollover
{
  "conditions": {
    "max_age": "30d",
    "max_primary_shard_size": "50gb"
  }
}
~~~

The Rollover API checks the conditions, creates a new index according to the appropriate configuration, and updates the write alias. Subsequent write operations through `events-write` go to the new index. This pattern is commonly used for logs, events, and append-heavy data.

Physical indices can be named with an incrementing numeric sequence such as `events-000001`, `events-000002`. The application only needs to use `events-write` for writes and an appropriate read alias for searches.

Rollover is not the same as reindex:

- **Rollover** creates the next index to receive new data; old indices retain old data.
- **Reindex** copies documents from a source index to a destination index, usually used when changing mappings or data structures.

If you need to manage time-based data with lifecycle policies, you can combine aliases with Index Lifecycle Management (ILM) or an appropriate data stream mechanism. Choose the model based on the data type and query requirements.

## 13. Common mistakes when using aliases

**Confusing an alias with a physical index.** An alias does not store documents of its own. Deleting an alias does not delete the target index; deleting the target index can leave the alias without a target.

**Application auto-creating an index with the same name as an alias.** If `products` is already an alias, automatic index creation can fail because that name is already in use. For entities using pre-provisioned aliases, consider `createIndex = false`.

**Multi-index alias without a write index.** Read queries may work while write operations fail because Elasticsearch cannot determine which index receives the data. Set `is_write_index` explicitly.

**Switching the alias before data is ready.** An alias switch is very fast, but it does not verify data completeness. Switch only after reindexing, catch-up, and verification are complete.

**Ignoring writes occurring during migration.** Reindex does not automatically synchronize new changes. You need pause/catch-up, CDC, or a controlled dual-write strategy.

**Incompatible mappings across indices.** A read alias spanning multiple indices can encounter query or aggregation errors when a field has different types. Unify mappings before adding an index to a shared alias.

**Using an alias filter for security.** Filters do not replace authorization. Access control must be configured with proper security mechanisms.

**Deleting the old index immediately after switching.** Keep the old index long enough for verification and rollback according to your system's retention policy.

**Letting every application instance manage aliases.** Provisioning should be a controlled deployment step, avoiding multiple instances concurrently performing cluster state changes.

## 14. Alias design workflow in a project

You can implement this in the following sequence:

1. Choose a stable logical name for the application to use, such as `products`.
2. Name physical indices by generation, such as `products-v1`.
3. Create the physical index with defined settings and mappings.
4. Create read/write aliases or a shared alias, designating the write index if needed.
5. Configure the Spring Data entity with `@Document(indexName = "products", createIndex = false)` when the alias is provisioned externally.
6. Test repository and operations reads/writes through the alias.
7. When a mapping change is needed, create a new-generation index, reindex, and synchronize incoming changes.
8. Verify data, mappings, queries, and document counts before switching the alias.
9. Use a single `_aliases` request to atomically redirect the alias.
10. Monitor the application, keep the old index during the rollback window, and then delete it according to policy.

## Conclusion

Aliases decouple the logical name used by the application from the physical index name where Elasticsearch actually stores documents. The application can continue working with `products` while the system replaces `products-v1` with `products-v2`, or use separate read/write aliases to manage access flows.

Aliases also support multiple indices, write indices, filters, routing, and rollover. Their greatest value in the index lifecycle is allowing redirection via an atomic cluster state update. For a safe migration, you still need to prepare mappings, reindex, synchronize data produced during the transition, and verify the target index before changing the alias.

In Spring Data Elasticsearch, setting `@Document(indexName = "products")` lets repositories and operations use a stable logical name. Creating physical indices and managing aliases should be performed as a controlled provisioning step so the application does not depend on generation-specific index names.

## References

- [Elasticsearch — Aliases](https://www.elastic.co/docs/manage-data/data-store/aliases)
- [Elasticsearch — Add and remove aliases](https://www.elastic.co/docs/manage-data/data-store/aliases#alias-management)
- [Elasticsearch — Reindex documents](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-reindex)
- [Elasticsearch — Rollover API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-rollover)
- [Spring Data Elasticsearch — Object Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
