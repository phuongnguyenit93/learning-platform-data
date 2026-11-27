# Read Alias, Write Alias, and is_write_index

In Elasticsearch, an alias is a logical name pointing to one or more indices. Applications can use an alias to read data without needing to know the physical index name currently storing the data. When creating a new index, switching the alias to the new index allows the application to keep using the same stable name.

For systems with multiple time-based indices or zero-downtime deployment requirements, you should clearly distinguish between a **read alias** and a **write alias**. A read alias defines which indices should be searched. A write alias defines the index that receives write operations. The **is_write_index** attribute indicates which index is the write target when an alias points to multiple indices.

This lesson explains how aliases work, how to configure read/write aliases, how Elasticsearch selects the write index, how to change aliases safely, and how to integrate aliases with Spring Data Elasticsearch.

## 1. What is an alias?

An alias is an alternate name for an index or a group of indices. Applications send requests to an alias just as if working with an index:

~~~http
GET /products-read/_search
~~~

If products-read is an alias pointing to products-000001, Elasticsearch executes the search on that index. The application does not need to know that the physical index has the suffix 000001.

An alias does not contain its own documents and does not store data. Data remains in the physical indices. An alias only provides a routing layer and a stable name for supported operations.

For example, the system has the following indices:

~~~text
products-000001
products-000002
products-000003
~~~

You can create the alias products-read pointing to all three indices. A search request to the alias searches across member indices and merges the results.

An alias can point to:

- A single index.
- Multiple indices simultaneously.
- A data stream in cases where Elasticsearch supports corresponding aliases.

An alias name must not conflict with an existing index or data stream name. Use a clear naming convention to distinguish physical index names from alias names, such as -read and -write suffixes.

### Aliases decouple applications from physical index names

If an application accesses products-000001 directly, every time it switches to a new index, configuration must change or the application must be redeployed. If the application accesses products-read, administrators can change the index behind the alias while the code keeps using the old name.

This is the foundation for:

- Switching indices after reindexing.
- Blue/green deployments.
- Managing daily or periodic indices.
- Rolling over when an index reaches a size or age threshold.
- Separating read and write flows.

## 2. How do read aliases and write aliases differ?

The two types of aliases serve different purposes.

A **read alias** represents the set of indices that the application needs to read. It often points to one or more indices. When searching through a read alias, Elasticsearch searches across the indices referenced by the alias.

A **write alias** represents the target receiving write operations. It must identify an index capable of receiving index/update/create/delete operations appropriate to the API being called. If the alias points to multiple indices, Elasticsearch needs to know which index is the write index.

Example for a catalog application:

~~~text
products-read  ---> products-000001
              ---> products-000002
              ---> products-000003

products-write ---> products-000003 (write index)
~~~

The application reads through products-read so it can find documents from both old and new indices. The application writes through products-write so new documents are written to the current index.

A read alias and a write alias can be two separate aliases. They can also be the same alias if the system wants a single name for both reads and writes. When an alias both points to multiple indices and accepts writes, is_write_index determines the write target.

### A read alias can point to multiple indices

A read alias can include all indices holding data:

~~~http
GET /products-read/_search
{
  "query": {
    "match": {
      "title": "keyboard"
    }
  }
}
~~~

Elasticsearch dispatches work to shards belonging to the indices referenced by the alias. Responses are merged like a multi-index search.

The indices behind the alias should have compatible mappings. If one index declares price as double while another index declares the same field as keyword, sorting or aggregations can fail or behave inconsistently.

### A write alias requires a clear write target

When an alias points to exactly one index, that index is considered the write index by default unless configured otherwise. When an alias points to multiple indices, one index must be marked with is_write_index: true.

If an alias points to multiple indices without a write index, write operations through the alias will fail because Elasticsearch cannot choose the target index automatically.

This is why read aliases commonly have multiple members, while write aliases require a single write target.

## 3. What does is_write_index mean?

is_write_index is an attribute of the relationship between an alias and an index. It tells Elasticsearch which index is the write target when an alias has multiple target indices.

Example:

~~~json
{
  "actions": [
    {
      "add": {
        "index": "products-000001",
        "alias": "products-write",
        "is_write_index": false
      }
    },
    {
      "add": {
        "index": "products-000002",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
~~~

In this configuration:

- products-write points to two indices.
- products-000001 does not receive writes through the alias.
- products-000002 is the write index.
- Write requests through products-write are routed to products-000002.

is_write_index is not a document property, not a mapping field, and does not change access permissions. It only determines the write target for an alias.

### If an alias points to only one index

When an alias points to a single index, Elasticsearch treats that index as the write index by default. You can still explicitly set is_write_index: true for readability and to avoid confusion when adding indices later.

### If an alias points to multiple indices without specifying a write index

Elasticsearch has no basis to select a write index. Write operations through the alias will return an error asking to designate a write index.

Do not expect Elasticsearch to pick the newest index by name or date. Index names do not determine the write target; alias metadata is the authoritative source of truth.

### If all indices are set to is_write_index: false

The alias has no write index. Searches through the alias may still work, but write operations through the alias have no valid target and will fail.

### Can there be multiple write indices for the same alias?

An alias cannot have multiple write indices simultaneously. When configuring an alias pointing to multiple indices, only one index is marked as the write index. Having multiple write targets would make write routing non-deterministic.

If you need to write to multiple indices, the application must perform multiple intentional write operations or use an appropriate ingest/replication mechanism. Do not use an alias with multiple write indices expecting Elasticsearch to replicate requests automatically.

## 4. Creating indices and configuring read/write aliases

Suppose we start with the index products-000001. First, create the index with its mapping:

~~~http
PUT /products-000001
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      },
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
~~~

Then attach the two aliases to this index:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-000001",
        "alias": "products-read"
      }
    },
    {
      "add": {
        "index": "products-000001",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
~~~

At this point:

- Searches through products-read read from products-000001.
- Writes through products-write write to products-000001.

You can verify the aliases:

~~~http
GET /_alias/products-read
GET /_alias/products-write
~~~

Or inspect aliases of a specific index:

~~~http
GET /products-000001/_alias
~~~

The API returns the index information and associated aliases. Inspect is_write_index in the write alias metadata to confirm the write target.

### Using a single alias for both reads and writes

Another pattern is using only products as a shared alias. The alias can point to multiple indices for reads while designating one write index:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-000001",
        "alias": "products",
        "is_write_index": false
      }
    },
    {
      "add": {
        "index": "products-000002",
        "alias": "products",
        "is_write_index": true
      }
    }
  ]
}
~~~

Searches through products read both indices; write operations through products only go to products-000002.

This approach is simple for applications that only need a single name. However, separating read and write aliases makes access permissions and usage intent clearer, especially when application components have different read/write policies.

## 5. Routing operations through aliases

Aliases are used in API paths just like index names.

### Reading and searching

~~~http
GET /products-read/_doc/p-100
~~~

~~~http
POST /products-read/_search
{
  "query": {
    "term": {
      "category": "accessories"
    }
  }
}
~~~

When a read alias points to multiple indices, Elasticsearch searches for documents across member indices. For get-by-ID operations, if multiple indices might contain the same ID, understand the search scope and avoid data designs where duplicate IDs cause ambiguous results.

### Writing documents

~~~http
POST /products-write/_doc
{
  "title": "Wireless Keyboard",
  "category": "accessories",
  "price": 89.5
}
~~~

If the alias has a valid write index, Elasticsearch creates the document in that index and generates an ID.

With an application-supplied ID:

~~~http
PUT /products-write/_doc/p-100
{
  "title": "Wireless Keyboard",
  "category": "accessories",
  "price": 89.5
}
~~~

Index, update, and delete APIs through an alias all require a valid write target. Do not confuse is_write_index with writing to every index in the alias.

### Alias filter and routing

An alias can also contain a filter or routing to restrict searchable documents or designate shards. Example of a read alias for a data subset:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-000001",
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

When searching through active-products, the alias filter is applied to restrict results according to the condition. An alias filter serves read/search operations; it is not a security barrier for write operations. Writing through a filtered alias does not mean Elasticsearch automatically validates whether the new document matches the filter.

Do not use alias filters as a replacement for authorization. Access permissions to indices and sensitive data must be designed using security roles and appropriate security mechanisms.

Routing aliases can direct operations to appropriate shards. When using routing, ensure index and search operations remain consistent with the chosen routing key; otherwise, documents may not appear in queries as expected.

## 6. Safely updating aliases when creating a new index

A major benefit of aliases is switching indices without changing endpoint names in the application.

Suppose the system is running:

~~~text
products-read  ---> products-000001
products-write ---> products-000001 (write index)
~~~

We want to switch writes to products-000002 and allow reading both old and new data:

~~~text
products-read  ---> products-000001
              ---> products-000002

products-write ---> products-000002 (write index)
~~~

First, create the new index with compatible mappings:

~~~http
PUT /products-000002
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      },
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
~~~

Then update the aliases in a single _aliases request:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-000002",
        "alias": "products-read"
      }
    },
    {
      "remove": {
        "index": "products-000001",
        "alias": "products-write"
      }
    },
    {
      "add": {
        "index": "products-000001",
        "alias": "products-write",
        "is_write_index": false
      }
    },
    {
      "add": {
        "index": "products-000002",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
~~~

The actions in _aliases are applied as an atomic metadata update. Clients do not observe an intermediate state where an alias was removed but not yet re-added. Switching the write target can therefore be performed in a single update.

However, updating an alias does not automatically copy documents from the old index to the new index. If products-000002 does not yet contain old data, the read alias after updating only finds new data in the new index while old data remains in the old index. If you want the read alias to return full history or migrate to a single index, you need reindexing or a corresponding data strategy before switching.

### When should you keep the old index in the read alias?

You can keep the old index in the read alias if:

- The old index still holds documents that need to be queried.
- The old index's mapping is compatible with the new index.
- The application needs to read history across multiple indices.
- Keeping old data complies with retention policies.

If you have already reindexed all data to the new index and verified the results, you can remove the old index from the read alias. Delete the old index only after confirming it is no longer needed and backup/retention requirements are satisfied.

## 7. Rollover and write aliases

Rollover creates a new index when the current index meets one or more conditions, such as age, document count, or shard size. Rollover is commonly used with a write alias so the application always writes through a stable name.

For example, the alias events-write currently points to events-000001 with is_write_index: true. When the index meets the conditions, call the Rollover API:

~~~http
POST /events-write/_rollover/events-000002
{
  "conditions": {
    "max_age": "30d",
    "max_docs": 1000000
  }
}
~~~

Elasticsearch creates the new index if conditions are satisfied and updates the write alias so the new index becomes the write index. If conditions are not yet met, the API reports that it did not roll over.

The conditions in this example are illustrative. Choose thresholds based on shard capacity, write throughput, retention period, and cluster query capabilities.

### Rollover alias and separate read alias

If the system uses events-read to read multiple indices and events-write for writes, both aliases must be managed.

- The Rollover API switches the write alias to the new index.
- The read alias needs the new index added if the application needs to read newly written data.
- If the read alias needs to query full history, keep old indices in the read alias until their retention period expires or data has been migrated.

Do not assume that rolling over a write alias automatically updates every other related alias. Check metadata after rollover and update the read alias according to your system's strategy.

### Rollover does not replace reindex

Rollover creates a new index to continue accepting writes. It does not move existing documents into the new index. Each post-rollover index holds a separate slice of data. This model suits append-only or time-based data, but does not resolve mapping migrations for historical data.

## 8. Integrating read/write aliases with Spring Data Elasticsearch

Spring Data Elasticsearch works with indices via entity metadata and IndexCoordinates. The indexName value in @Document can be an alias name instead of a physical index name.

Example:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String title;
    private String category;
    private Double price;
}
~~~

If products is an alias, the repository uses this alias name for corresponding operations. A shared alias can both read multiple indices and write to a single write index if is_write_index is configured properly.

### Repository with a shared alias

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

With the entity @Document(indexName = "products"), the repository can invoke:

~~~java
List<Product> products = productRepository.findByCategory("accessories");
Product saved = productRepository.save(product);
~~~

If products is an alias pointing to multiple indices, search operations run across member indices. The save operation routes to the write index. This only works when the alias has a valid write target.

### Separating read alias and write alias using IndexCoordinates

If the application needs two separate aliases, a repository with a fixed @Document(indexName = "...") does not automatically know when to use the read alias and when to use the write alias. You can call ElasticsearchOperations with explicit IndexCoordinates:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexCoordinates;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Query;

public class ProductStore {

    private final ElasticsearchOperations operations;

    public ProductStore(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Product> search(Query query) {
        return operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products-read")
        );
    }

    public Product save(Product product) {
        return operations.save(
            product,
            IndexCoordinates.of("products-write")
        );
    }
}
~~~

IndexCoordinates allows specifying an alias or index at call time. Queries still use the field mapping of Product, while the read/write target is selected separately.

Method names and overloads may vary across Spring Data Elasticsearch versions. When applying this to a project, verify the ElasticsearchOperations API of the release train in use. The design principle remains passing the read alias for read operations and the write alias for write operations.

### When to use a repository, and when to use operations?

| Need | Approach |
|---|---|
| Single shared alias for both reads and writes | @Document(indexName = "alias") and repository |
| Separate read alias and write alias | ElasticsearchOperations with explicit IndexCoordinates |
| Simple queries by method name | Repository method |
| Complex queries, multi-index, or aggregations | ElasticsearchOperations and appropriate queries |
| Managing indices, mappings, and aliases | Dedicated index administration workflow or Elasticsearch API |

Repositories are convenient for CRUD and derived queries. ElasticsearchOperations is suitable when the application needs explicit control over the index/alias per operation.

### Do not let a repository accidentally write to a read alias

A read alias may point to multiple indices and have no write index. If you configure @Document(indexName = "products-read") and then call repository save, the write operation will fail if the alias has no write target.

This is a common design mistake when separating read and write aliases. Check all repository CRUD operations: save, delete, findById, search, and custom operations may use the same default indexName. If aliases are separated, use operations or structure repositories/configurations appropriately so each operation uses the right alias.

## 9. Aliases and compatible mappings

A read alias can point to multiple indices. In that case, fields shared in queries, sorts, and aggregations need compatible mappings across all indices.

Example:

| Index | Mapping of price |
|---|---|
| products-000001 | double |
| products-000002 | double |
| products-000003 | keyword |

A sort or aggregation query on price may fail or behave unexpectedly because the same field name has different types.

Checks to perform before adding an index to a read alias:

- Are field names and field types consistent?
- Are analyzers and search analyzers compatible?
- Do multi-fields such as title.keyword exist on all indices?
- Are date formats consistent?
- Do fields have doc values enabled when needed for sorting/aggregations?
- Do older indices lack newly added fields?

If mappings differ, you can use field_caps to inspect field capabilities across the alias:

~~~http
GET /products-read/_field_caps?fields=title,title.keyword,price
~~~

The Field Capabilities API helps identify fields with the same name that have different types across indices. Based on the results, decide whether to standardize mappings, remove incompatible indices from the alias, or migrate data to a new index.

## 10. Managing aliases via APIs and Spring Data

Elasticsearch provides the primary APIs for managing aliases:

| API | Purpose |
|---|---|
| GET /_alias/{name} | Inspect indices that the alias points to |
| GET /{index}/_alias | Inspect aliases of an index |
| POST /_aliases | Add, remove, or update multiple aliases in one request |
| POST /{alias}/_rollover | Create a new index and switch the write alias based on conditions |
| GET /_cat/aliases?v | View the list of aliases in tabular format |

POST /_aliases is the key choice when atomic alias switching is required. You can add and remove alias associations in the same request.

Spring Data Elasticsearch also has index management abstractions through IndexOperations and alias action APIs in supported versions. However, alias operations are typically tied to index administration, migration, and deployment workflows. Consolidate alias changes into a controlled deployment step rather than letting every application instance alter aliases on startup.

### Who should have permission to modify aliases?

Business applications typically only need permissions to read and write documents through aliases. Permissions to create indices, delete indices, update mappings, and modify aliases should belong to deployment pipelines or dedicated administrative accounts.

Separating these permissions reduces the chance that an application bug switches an alias incorrectly or accidentally deletes an index. Elasticsearch privileges should be granted according to the exact APIs and index scope each component requires.

## 11. Checking alias and write index status

When writes through an alias fail, verify metadata before changing code.

### View all aliases

~~~http
GET /_cat/aliases?v
~~~

The output shows aliases, target indices, and related information. For more details:

~~~http
GET /_alias/products-write
~~~

Check the alias relationship to each index and the value of is_write_index.

### Verify the write index

If an alias has multiple members, only one member should have is_write_index: true. Verify that:

- There is exactly one write index.
- The write index exists and is in a healthy state.
- The application calls the exact alias name.
- No outdated configuration is writing through a deprecated alias.
- Application nodes have loaded the updated configuration if the alias name changed.

### Verify with a controlled write operation

In a test environment, you can write a document with an explicit ID through the write alias:

~~~http
PUT /products-write/_doc/alias-check-001
{
  "title": "Alias verification",
  "category": "internal",
  "price": 1.0
}
~~~

Then determine which index holds the document using the Get API or search metadata. Do not use test documents in production without an appropriate cleanup process.

### Common errors

| Symptom | Possible cause | What to check |
|---|---|---|
| Write request reports unable to determine write index | Alias points to multiple indices without is_write_index: true | Inspect alias metadata and designate the write target |
| Write request reports alias not found | Alias has not been created yet or name is wrong | GET /_alias/{name} |
| Search returns incomplete results | Read alias does not yet include the index to read | Check alias membership and data |
| Search through alias fails with mapping error | Indices have incompatible field types | Use _field_caps and inspect mappings |
| Save via Spring Data fails | @Document points to a read alias with no write target | Use write alias or IndexCoordinates |
| New data missing on read after rollover | Read alias has not added the new index | Inspect and update the read alias |
| Writes going to old index | Write alias not switched or application uses concrete index name directly | Check URI/coordinates and alias metadata |
| Alias update returns an error | Index does not exist, alias name conflict, or invalid action | Read error response and verify before/after state |

## 12. Zero-downtime index switchover scenario

Suppose the application currently reads and writes through the alias catalog. The alias points to catalog-v1, which is the write index.

We want to create catalog-v2 with a new mapping.

A workflow can be executed as follows:

1. Create catalog-v2 with the new mapping.
2. Reindex documents from catalog-v1 to catalog-v2.
3. Synchronize writes occurring during reindexing if the application remains active.
4. Verify document count, mapping, queries, sorting, and aggregations.
5. Use a single _aliases request to add catalog-v2 to the alias and switch the write index to v2.
6. Verify application reads/writes through the alias after cutover.
7. Keep v1 during the rollback window if needed.
8. Remove v1 from the alias and delete it per retention policy after confirmation.

Example alias update:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "catalog-v1",
        "alias": "catalog"
      }
    },
    {
      "add": {
        "index": "catalog-v2",
        "alias": "catalog",
        "is_write_index": true
      }
    }
  ]
}
~~~

This request switches the alias from v1 to v2 in a single metadata update. If you need to keep both indices readable during a transition phase, add v2 while keeping v1 in the alias, and set only v2 as the write index.

### Rollback

If an issue is discovered after cutover, you can switch the write index back to v1 with another alias update, provided v1 still exists and mappings/application remain compatible.

However, if new documents were already written to v2 after cutover, switching the alias back to v1 does not automatically move those documents back. Define a data synchronization strategy before rolling back. An alias switch only changes routing; it does not copy or merge data.

## 13. Principles to follow

- Use a read alias so the application queries one or more indices without depending on physical names.
- Use a write alias to route writes to the current active index.
- When an alias points to multiple indices, set exactly one is_write_index: true if writes go through the alias.
- If an alias points to a single index, that index is the write index by default unless configured otherwise.
- Do not treat is_write_index as an authorization or mapping mechanism.
- Use _aliases to modify multiple alias relationships atomically.
- Ensure compatible mappings across indices behind a read alias.
- After rollover, verify whether the read alias includes the new index.
- When separating read/write aliases in Spring Data, pass the appropriate IndexCoordinates per operation or structure repositories clearly.
- Do not let business applications manage aliases on their own if they only need to read and write documents.
- Remember that an alias switch does not reindex, copy data, or automatically handle data rollback.

Aliases provide a stable name for applications to interact with indices across lifecycle stages. Read aliases define read scope, write aliases define the write target, and is_write_index clarifies which index receives data when an alias has multiple members. When combining these three concepts properly with consistent mappings and a controlled cutover workflow, systems can scale and replace indices without forcing applications to depend on physical index names.
