# Atomic Alias Switching When Changing Index Versions

In Elasticsearch, an **alias** is a name that references one or more indices. Applications can access data through a stable alias such as **products-current**, while physical indices are created by version such as **products-v1** and **products-v2**. When mappings, analyzers, or data structures need to change, the development team can prepare a new index and switch the alias to it.

Elasticsearch supports updating multiple alias operations in a single **_aliases** request. When a valid request is processed, the alias changes in the request are applied atomically in the cluster state. As a result, the application observes the alias pointing to either the old index or the new index, avoiding a gap where the alias is removed from the old index before being attached to the new index.

The key point to understand is that an atomic alias operation only makes switching the access target seamless. It does not move data automatically, does not guarantee the new index already holds complete documents, and does not synchronize writes occurring during reindexing. Therefore, the index versioning workflow must prepare data, verify it, switch the alias, and have a recovery plan.

## 1. What is an alias and why is it needed?

An Elasticsearch index is typically tied to a specific name. If an application accesses **products-v1** directly, changing the index structure to **products-v2** requires updating application code or deployment configuration accordingly.

An alias provides a stable logical name in front of the physical index:

~~~text
Spring Data Elasticsearch application
              |
              v
       products-current
           (alias)
              |
              v
         products-v1
       (physical index)
~~~

After switching versions:

~~~text
Spring Data Elasticsearch application
              |
              v
       products-current
           (alias)
              |
              v
         products-v2
       (physical index)
~~~

The application continues using **products-current**. Replacing the physical index is performed on the Elasticsearch side via an alias update operation.

Aliases are useful in scenarios such as:

- Changing mappings when adding fields or changing how fields are indexed.
- Changing analyzers to improve search behavior.
- Organizing indices by version or data period.
- Migrating data to a new index without changing the index name in the application.
- Maintaining a stable access name for repositories and services.

Aliases do not store documents. Data remains in the physical indices referenced by the alias.

## 2. Distinguishing index, alias, and write index

For example, a product system has the following names:

| Name | Type | Role |
|---|---|---|
| **products-v1** | Physical index | Stores data with mapping version 1 |
| **products-v2** | Physical index | Stores data with mapping version 2 |
| **products-current** | Alias | Stable access name used by the application |

An alias can point to one or more indices. If an alias points to multiple indices, read queries can search across all indices attached to that alias.

For write operations, Elasticsearch needs to know which index receives new documents. The **is_write_index** attribute designates the index that receives write operations through the alias.

Example of attaching an alias to an index and marking it as the write index:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-v1",
        "alias": "products-current",
        "is_write_index": true
      }
    }
  ]
}
~~~

When an alias points to only one index, Elasticsearch may default to treating that index as the write index in many cases. However, explicitly declaring **is_write_index: true** makes system intent clearer and avoids ambiguity when the alias might point to multiple indices.

If an alias points to multiple indices without specifying a write index, write operations can fail because Elasticsearch does not know where to write. For an alias used for both reads and writes, explicitly designate the write target.

Another design is using two aliases:

- **products-read** points to the index or set of indices serving reads.
- **products-write** points to the single index receiving writes.

This separation is useful when the system needs to read from multiple indices during a transition or has distinct write rules. If using two aliases, update both in the same request when switching synchronously.

## 3. Using a stable alias in Spring Data Elasticsearch

In Spring Data Elasticsearch, a document class typically declares the index name using **@Document**. If the application wants to operate through an alias, it can use the alias name as the **indexName** value:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products-current", createIndex = false)
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    public Product() {
    }

    // Constructors, getters, and setters omitted.
}
~~~

In this example, **products-current** is an alias. Repositories or **ElasticsearchOperations** use this name when performing document operations.

Repository example:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

When calling **save**, **findById**, or search queries through the repository, Spring Data Elasticsearch uses the name declared in the document class metadata. Elasticsearch resolves the alias to the target index.

The **createIndex = false** attribute is appropriate when indices and aliases are managed by a separate deployment process. The application should not auto-create an index with the alias name if that name is reserved for an alias. Create the physical index, then attach the alias to it via the administrative workflow.

If using **ElasticsearchOperations** directly, you can specify the alias with **IndexCoordinates**:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

IndexCoordinates coordinates = IndexCoordinates.of("products-current");

operations.save(product, coordinates);
~~~

Specific overloads of **save** and repository configuration details may vary across Spring Data Elasticsearch versions. What matters is that all document operations in the application use the stable alias name rather than pointing directly to an index with a version suffix.

## 4. Preparing the new index version

Suppose the application is using **products-v1**. The old mapping has product name and category fields:

~~~json
{
  "properties": {
    "name": {
      "type": "text"
    },
    "category": {
      "type": "keyword"
    }
  }
}
~~~

The new version needs a custom analyzer, multi-fields, or a field type change. Do not attempt to apply incompatible mapping changes on an index that already contains data. Instead, create a new index, such as **products-v2**, with the desired settings and mapping.

Example of creating the new index:

~~~http
PUT /products-v2
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 1,
    "analysis": {
      "analyzer": {
        "product_name_analyzer": {
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
      "name": {
        "type": "text",
        "analyzer": "product_name_analyzer",
        "fields": {
          "raw": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
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

In Spring Data Elasticsearch, you can create an index using **IndexOperations** from document class metadata or via an index administration workflow. When different mapping versions are needed, manage index configurations per version so new indices can be recreated consistently.

Example with a document class and IndexOperations:

~~~java
IndexOperations indexOperations =
        operations.indexOps(IndexCoordinates.of("products-v2"));

if (!indexOperations.exists()) {
    indexOperations.create();
    indexOperations.putMapping(mappingDocument);
}
~~~

The snippet above illustrates creating an index and applying a mapping. **mappingDocument** must be a mapping object built or loaded according to the API of the Spring Data Elasticsearch version in use. If settings must be declared, provide them during index creation. Do not call **create()** with default configuration and assume custom analyzers are already installed.

Before switching the alias, verify that the new index has the appropriate settings, mappings, and access permissions. An alias only redirects the access name; it does not fix index structure.

## 5. Moving data from the old index to the new index

After creating **products-v2**, migrate data from **products-v1**. Elasticsearch provides the **_reindex** API:

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

This request copies documents from the source index to the destination index. Document IDs are preserved unless configured otherwise with transformations. You can add a script or query to transform data during reindexing if the new schema requires it.

Example of migrating only active products:

~~~http
POST /_reindex
{
  "source": {
    "index": "products-v1",
    "query": {
      "term": {
        "status": "ACTIVE"
      }
    }
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

Before switching the alias, inspect the reindex results:

- Whether the request completed.
- Number of documents processed and number of failed documents.
- Whether there were ID conflicts or mapping errors.
- Whether document counts between the old and new indices match the filter criteria.
- Whether representative documents retain accurate content and data types.

You can count documents:

~~~http
GET /products-v1/_count

GET /products-v2/_count
~~~

The two counts do not necessarily have to match if reindexing used a filter query or transformation script. What matters is that results match the defined transformation rules.

### Controlling writes during reindexing

If the application continues writing to **products-v1** while reindexing is running, new documents or updates occurring after reindex read the data may not appear in **products-v2**. Therefore, reindex completion does not automatically prove the two indices are identical at the moment of alias switching.

There are several strategies:

**Pause writes during cutover.** This is simple and easy to control. Stop or queue write requests, complete reindexing, verify data, switch the alias, and then resume writes. Pause duration depends on data volume and reindex speed.

**Reindex first, then sync final changes.** You can run an initial reindex while the system stays live, then briefly pause writes, synchronize remaining changes, and switch the alias. You need a mechanism to identify new changes or capture incoming writes; simply running a plain reindex again may not properly handle all updates and deletes.

**Dual-write or use a CDC mechanism.** The application writes to both the old and new indices, or a data change stream syncs to the new index. This reduces write downtime but is more complex: you must handle one-sided failures, update ordering, document deletions, duplicate writes, and event replay capability.

For simple applications, pausing writes during cutover is usually easier to operate and verify. For high-availability systems, design a dedicated data synchronization mechanism and test it before switching.

## 6. Updating aliases atomically in a single request

This is the critical cutover step. Do not send two separate requests to remove the alias from the old index and then add it to the new index. If the first request succeeds and the second fails, the application may experience a period where the alias points to no index.

Execute both actions in a single **POST /_aliases** request:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-current"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-current",
        "is_write_index": true
      }
    }
  ]
}
~~~

Elasticsearch processes the actions in a single alias update. Once the request is accepted, the alias moves from **products-v1** to **products-v2** in one cluster state change. The application continues accessing **products-current**, and new requests are routed according to the alias after the change takes effect.

Important points:

- **remove** only detaches the alias from the specified index.
- **add** attaches the alias to the new index.
- **is_write_index: true** designates the new index as the write target through the alias.
- Both actions reside in the same **actions** array of the same request.
- If the request fails, handle the error and inspect the actual alias state before retrying.

Do not perform it like this:

~~~http
POST /products-v1/_alias/products-current

DELETE /products-v1/_alias/products-current

PUT /products-v2/_alias/products-current
~~~

Separate requests create intermediate state windows. That approach does not guarantee an atomic cutover.

### Switching read alias and write alias together

If the system uses two aliases, **products-read** and **products-write**, you can switch both in a single request:

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

Changes to both read and write aliases are sent in one update. As a result, the application does not observe a state where reads have switched to the new index while the write alias still points to the old index due to two separated admin operations.

If the alias has a filter or routing, redeclare those properties in the **add** action. Removing and re-adding an alias while forgetting the filter or routing can alter the document scope visible to the application.

## 7. Why are alias operations atomic?

The **_aliases** API accepts a set of actions to update aliases in the cluster. Elasticsearch applies alias changes as a single cluster state update unit. Applications observe either the state before or after the update is applied, rather than passing through an intermediate state created by two separate requests.

However, understand the exact scope of atomicity:

- Changing the aliases in one request is applied as a single unit.
- Data reindexing is not part of the alias transaction.
- Verifying data before switching the alias does not automatically lock new writes.
- In-flight requests at the moment of alias switching may already have been routed to the old index.
- Aliases do not copy documents or synchronize writes between indices.

Therefore, the workflow must ensure the new index is ready before the alias is switched. An atomic alias switch solves the access-path cutover problem, while data completeness and consistency remain the responsibility of the migration workflow.

## 8. Verifying aliases after switching

After the update request succeeds, inspect the alias state:

~~~http
GET /_alias/products-current
~~~

Or inspect all aliases:

~~~http
GET /_cat/aliases/products-current?v
~~~

Results to confirm:

- Alias **products-current** points to **products-v2**.
- The alias no longer points to **products-v1**, unless reading from multiple indices is intended.
- **products-v2** is the write index if the alias is used for writes.
- Filters, routing, and other alias attributes remain accurate.

You can inspect the physical index:

~~~http
GET /products-v2/_mapping

GET /products-v2/_settings

GET /products-v2/_count
~~~

Then test reading and writing through the alias:

~~~http
GET /products-current/_search
{
  "query": {
    "match_all": {}
  }
}
~~~

Example of writing a document through the alias:

~~~http
POST /products-current/_doc
{
  "name": "Wireless Keyboard",
  "category": "accessories",
  "price": 79.9
}
~~~

The new document must be written into the index marked as the write index. You can verify this by reading the document from **products-v2** or checking document metadata after writing.

## 9. Controlled cutover workflow

An index version migration workflow typically consists of these stages:

~~~text
1. Prepare products-v2
          |
          v
2. Reindex data from products-v1
          |
          v
3. Verify data and queries
          |
          v
4. Control or pause writes
          |
          v
5. Sync final changes
          |
          v
6. Update alias in a single request
          |
          v
7. Verify reads/writes through alias
          |
          v
8. Monitor and retain old index for recovery
~~~

This can be broken down as follows:

**Preparation stage**

- Finalize mappings and settings for the new index.
- Create the new physical index.
- Verify analyzers, mappings, access permissions, and storage capacity.
- Confirm the current alias points to the old index.

**Data migration stage**

- Run reindex or the designed synchronization mechanism.
- Monitor errors and document counts.
- Verify sample documents, new fields, and search results.
- Synchronize data generated during reindexing.

**Cutover stage**

- Pause writes or ensure dual-write/CDC mechanisms have caught up.
- Confirm the new index is ready to receive writes.
- Send a single **_aliases** request containing full remove and add actions.
- Verify the alias and write index after the request succeeds.
- Reopen the write flow if it was paused earlier.

**Monitoring stage**

- Check application error logs.
- Monitor read and write error rates.
- Monitor query latency and search results.
- Retain the old index long enough to confirm system stability.

## 10. Recovering when the new version encounters errors

If errors are detected after switching the alias, you can switch the alias back to the old index using a similar request:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v2",
        "alias": "products-current"
      }
    },
    {
      "add": {
        "index": "products-v1",
        "alias": "products-current",
        "is_write_index": true
      }
    }
  ]
}
~~~

This operation only reroutes the alias. It does not move documents written into **products-v2** back into **products-v1**.

If the application already received new writes after cutover, switching the alias back may cause those changes to disappear from the alias view. Before rolling back, determine what data was produced on the new index and how to sync back or replay those changes.

You can apply one of these approaches:

- Pause writes, sync new documents from the new index back to the old index, and then switch the alias.
- Replay write events from the source system or event log.
- Maintain dual-write for a period if architecture permits and clear error handling exists.

Do not delete the new index immediately after rollback. Keep it to investigate root causes, reconcile data, and test fixes.

## 11. Handling an alias already pointing to multiple indices

An alias can point to multiple indices. Before switching versions, inspect the current state:

~~~http
GET /_alias/products-current
~~~

If the alias points to **products-v1** and **products-archive**, the remove action only targets the specified index:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-current"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-current",
        "is_write_index": true
      }
    }
  ]
}
~~~

After the operation, the alias may continue pointing to **products-archive**. This may be intentional if the archive needs to be read alongside current data. If you want the alias to point only to the new index, handle the remaining links according to an explicit plan.

For multi-index aliases, pay special attention to:

- Read queries may return results from all indices referenced by the alias.
- Indices with different mappings can produce inconsistent results.
- Writes through the alias require a designated write index.
- Alias filters and routing can alter the accessed document set.
- Do not delete all alias links if you only intend to replace one specific index.

## 12. Spring Data Elasticsearch and alias management APIs

Spring Data Elasticsearch provides **IndexOperations** to manage indices and has alias-related APIs depending on the version. This object is typically obtained from **ElasticsearchOperations.indexOps(...)**:

~~~java
IndexOperations indexOperations =
        operations.indexOps(IndexCoordinates.of("products-v2"));
~~~

In applications, **IndexOperations** is suitable for operations such as checking index existence, creating indices, creating or reading mappings, and deleting indices. For atomic alias switches involving multiple actions, use an alias API that supports combining actions into a single request.

Depending on the Spring Data Elasticsearch version, how alias actions are represented and method signatures may differ. You can use the Elasticsearch Java API Client matching the cluster or call the **POST /_aliases** endpoint via an HTTP/client component configured in the application.

What must remain unchanged by design is that all remove and add actions must be sent in the same alias update request. Do not split them into multiple calls just because the API wrapper of the version in use has a different representation.

A REST request example best expresses the alias switch intent:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-current"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-current",
        "is_write_index": true
      }
    }
  ]
}
~~~

If executing from Java, use the proper Elasticsearch Java API Client and a version compatible with the project's Spring Boot/Spring Data Elasticsearch. Do not mix legacy RestHighLevelClient APIs with the newer Elasticsearch Java API Client.

## 13. Common errors when switching aliases

| Symptom | Possible cause | Resolution |
|---|---|---|
| Alias does not point to new index | Add action has wrong index name or request failed | Read response and recheck with **GET /_alias** |
| Request reports alias does not exist | Remove action references wrong alias or index | Check alias state before switching |
| Writes through alias fail | Alias points to multiple indices with no write index | Set **is_write_index: true** on the write-receiving index |
| Application cannot find documents after cutover | New index not fully reindexed or queries rely on different mapping | Verify counts, sample documents, and mappings |
| New data is missing | Writes occurred during reindex or cutover | Pause writes, sync final changes, or use CDC/dual-write |
| Alias still reads old data | Alias still linked to old index or multiple indices | Inspect all aliases and remove links no longer needed |
| Rollback loses new data through alias | Post-cutover writes exist only in new index | Sync back or replay events before switching alias |
| Alias switch succeeds but queries error | New index mapping or analyzer incompatible with application | Verify mapping, query, and schema version |
| Request rejected | Account lacks alias or index admin privileges | Grant appropriate privileges per security policy |

When encountering errors, do not blindly resend requests. First read the actual alias state to know whether the previous request took effect. This is especially important if the client disconnected after sending a request without receiving a response.

## 14. Operational principles to remember

- Use a stable alias in application configuration instead of coupling application code to versioned index names.
- Create and verify the new index before switching the alias.
- Ensure data is synchronized up to the cutover point.
- Explicitly set the write index if the alias receives writes.
- Send remove and add actions in the same **_aliases** request.
- Verify the alias, mapping, and write permissions after switching.
- Have a rollback plan that includes post-cutover incoming data.
- Keep the old index until the new system is confirmed stable.
- Only delete the old index according to approved retention and cleanup procedures.

Atomic alias switching is a key technique for changing index versions without altering access names in the application. In Spring Data Elasticsearch, document classes can use the alias name as **indexName**, while alias administration operations are performed through the corresponding index APIs. By preparing new data, controlling writes, switching aliases in a single request, and verifying after cutover, applications can transition to a new index in a controlled manner.
