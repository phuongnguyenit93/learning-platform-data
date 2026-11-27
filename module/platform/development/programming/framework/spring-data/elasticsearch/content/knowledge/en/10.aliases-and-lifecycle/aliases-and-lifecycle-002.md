# Creating, Updating, and Deleting Aliases with the Appropriate APIs

In Elasticsearch, an **alias** is a logical name pointing to one or more indices. Applications can access data through an alias instead of coupling directly to a physical index name. As a result, the system can swap indices, migrate data versions, create separate read/write endpoints, or restrict the set of searchable documents without changing the index name everywhere in the application.

For example, instead of letting the application access `products-v1` directly, we create an alias `products` pointing to that index:

```text
Spring Data Elasticsearch application
              |
              | indexName = "products"
              v
        Alias: products
              |
              v
       Index: products-v1
```

When a mapping or analyzer needs to change, you can create `products-v2`, copy the data, and switch the `products` alias to the new index. The application still uses the logical name `products` in its configuration.

Elasticsearch provides the following main APIs for managing aliases:

| Purpose | Commonly used API |
|---|---|
| Create alias | `PUT /<index>/_alias/<alias>` or `POST /_aliases` with action `add`. |
| Update/switch alias | `POST /_aliases` with one or more `add`, `remove` actions. |
| Inspect alias | `GET /_alias/<alias>`, `GET /<index>/_alias/<alias>`, or `_cat/aliases`. |
| Delete alias | `DELETE /<index>/_alias/<alias>` or `remove` action in `POST /_aliases`. |
| Delete physical index | `DELETE /<index>`; this is a different operation from deleting an alias. |

## 1. What is an alias and what is it used for?

An alias is an alternate name for an index. One alias can point to a single index or multiple indices at the same time. Multiple aliases can also point to the same index.

Some common use cases:

- **Stable index name:** the application uses `products`, while physical indices are versioned as `products-v1`, `products-v2`.
- **Version cutover:** after creating a new index and completing reindexing, switch the alias from the old index to the new index.
- **Separating reads and writes:** a read alias can point to multiple indices; a write alias points to the index receiving new data.
- **Filtering data:** an alias with a filter ensures search queries through the alias only see a subset of documents.
- **Routing:** an alias can specify routing for search or write operations to limit the shards accessed.
- **Lifecycle management:** an alias can serve as a write alias for rollover when the system moves to the next physical index.

An alias is not an index and does not store documents independently. Data remains in the physical indices that the alias points to.

## 2. Creating an alias

Suppose the index `products-v1` already exists. You can create the `products` alias using the single-index API:

```http
PUT /products-v1/_alias/products
```

Once the request succeeds, the application can search through the alias:

```http
GET /products/_search
{
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
```

Or use the Aliases API to add an alias:

```json
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
```

Both approaches create the alias association. `PUT /<index>/_alias/<alias>` is convenient when operating on a single index; `POST /_aliases` is useful when coordinating multiple changes in a single request.

### Creating an alias with a write index

An alias can point to multiple indices. If an alias is used for writes and points to multiple indices, Elasticsearch needs to know which index is the write target. You can declare `is_write_index` upon creation:

```json
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-v1",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
```

If an alias points to only one index, that index is treated as the write index by default. When an alias points to multiple indices, you should explicitly designate a write index. Without a designated write index, write operations through a multi-index alias will be rejected because Elasticsearch cannot choose a write target.

### Creating a filtered alias

An alias can apply a filter to search queries going through the alias. For example, create an alias that only exposes active products:

```json
PUT /products-v1/_alias/active-products
{
  "filter": {
    "term": {
      "active": true
    }
  }
}
```

When calling:

```http
GET /active-products/_search
```

Elasticsearch automatically combines the alias filter into the search query. The application does not need to repeat the `active = true` condition in every query.

An alias filter is a convenience for search queries, not an authorization mechanism or security boundary. Do not use an alias filter to prevent users from accessing sensitive data. Configure appropriate security roles and index permissions. Furthermore, an alias filter is not applied as a constraint for every document read/write API; you need to understand the exact API being used.

### Creating an alias with routing

If the application uses custom routing, an alias can attach routing to reduce the scope of shards accessed. Example:

```json
PUT /tenant-events-v1/_alias/tenant-42-events
{
  "search_routing": "tenant-42",
  "index_routing": "tenant-42"
}
```

`search_routing` is applied to search queries through the alias; `index_routing` is applied to write operations through the alias. Routing must be consistent with how documents are written into the index. If a document was indexed with a different routing value, queries through an alias with fixed routing may fail to find that document.

Do not use alias routing as a security mechanism replacing authorization. Routing primarily aids shard routing and optimizes operation scope.

## 3. Checking where an alias points

To inspect a specific alias:

```http
GET /_alias/products
```

The response shows the indices that the `products` alias points to along with alias metadata such as filter, routing, and write index if configured.

To view an alias for a specific index:

```http
GET /products-v1/_alias/products
```

To list aliases in a readable tabular format:

```http
GET /_cat/aliases?v
```

You can inspect indices and aliases together using the corresponding cat APIs:

```http
GET /_cat/indices?v
GET /_cat/aliases?v
```

When troubleshooting, verify which index the alias actually points to before inspecting mappings or documents. A query returning wrong results may happen because the alias still points to an old index, points to multiple indices with inconsistent mappings, or has a filter/routing changing the accessed dataset.

## 4. Updating an alias

In practice, updating an alias usually means changing alias metadata or switching the alias from one index to another.

### Switching an alias from an old index to a new index

Suppose:

- `products-v1` is the current index.
- `products-v2` has been created with the new mapping and has received the reindexed data.
- `products` is the alias the application is using.

You can switch the alias using a single `_aliases` request containing remove and add actions:

```json
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
```

The actions in a single update aliases request are applied as an atomic cluster state change. Clients do not see an intermediate state where the alias has been removed from the old index but not yet added to the new index. This is why remove/add operations should be combined into one request rather than sent as two separate requests.

After switching, verify again:

```http
GET /_alias/products
```

The `products` alias must point to `products-v2`. The application continues sending requests to `products` as before.

### Adding an index to a multi-index alias

A read alias can point to multiple indices, such as monthly data:

```json
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "orders-2026-10",
        "alias": "orders-history"
      }
    },
    {
      "add": {
        "index": "orders-2026-11",
        "alias": "orders-history"
      }
    }
  ]
}
```

Queries through `orders-history` will search across the referenced indices. Ensure the mappings across indices are compatible with the fields used by queries. If the same field has incompatible types in different indices, search or sort operations may fail or yield inconsistent results.

### Updating filter or routing

When you want to change an alias's filter or routing, you can use the `add` action with `is_write_index` and new metadata, or remove the old alias and re-add it with the desired configuration in the same request:

```json
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v2",
        "alias": "active-products"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "active-products",
        "filter": {
          "term": {
            "status": "PUBLISHED"
          }
        }
      }
    }
  ]
}
```

In this example, the alias filter is changed from the old condition to `status = PUBLISHED`. If the alias has additional metadata such as routing or `is_write_index`, redeclare all attributes that need to be preserved when recreating the alias.

## 5. Deleting an alias

To detach the `products` alias from the `products-v1` index, use:

```http
DELETE /products-v1/_alias/products
```

Or use the Aliases API with the `remove` action:

```json
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products"
      }
    }
  ]
}
```

This operation only removes the alias association from the index. The `products-v1` index and the documents inside it still exist.

If an alias points to multiple indices and you want to detach it from all of them, specify the appropriate indices or index pattern in the remove action. Before executing, inspect the current alias via `GET /_alias/<alias>` to avoid missing any links.

### Distinguishing deleting an alias and deleting an index

The following two operations have very different meanings:

```http
DELETE /products-v1/_alias/products
```

Detaches the `products` alias from the `products-v1` index; the index data remains intact.

```http
DELETE /products-v1
```

Deletes the physical index `products-v1` along with its data. If an alias points to that index, the alias no longer has that corresponding target.

The Aliases API also has a `remove_index` action to delete a physical index:

```json
POST /_aliases
{
  "actions": [
    {
      "remove_index": {
        "index": "products-obsolete"
      }
    }
  ]
}
```

`remove_index` is an index data deletion operation, not the normal way to delete an alias. Use it only when you genuinely want to delete the index and have confirmed retention/backup policies.

## 6. Write index when an alias points to multiple indices

A read alias can point to multiple indices, but an alias can have at most one write index. When an alias points to multiple indices, mark the index receiving writes with `is_write_index: true`.

Example:

```json
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "orders-2026-10",
        "alias": "orders"
      }
    },
    {
      "add": {
        "index": "orders-2026-11",
        "alias": "orders",
        "is_write_index": true
      }
    }
  ]
}
```

Result:

- Searches through `orders` can read both indices.
- Index requests through `orders` are routed to `orders-2026-11`.
- Old documents in `orders-2026-10` remain searchable.

If no write index is declared for a multi-index alias, write operations through the alias will not route to a single index. When designing aliases, clearly separate read-only aliases from aliases with write capability.

A common design is separating two aliases:

```text
orders-read  ---> orders-2026-10
             ---> orders-2026-11

orders-write ---> orders-2026-11 (is_write_index = true)
```

The read alias serves historical queries; the write alias designates the current index. This pattern is useful for rollover or time-based data partitioning.

## 7. Rollover aliases and the index lifecycle

Elasticsearch provides the Rollover API to switch a write alias to a new index when age, document count, or size conditions are met. The alias must be configured with a write index before rollover.

Example of creating the first index and write alias:

```json
PUT /events-000001
{
  "aliases": {
    "events-write": {
      "is_write_index": true
    },
    "events-read": {}
  }
}
```

When the index meets the conditions, you can roll over:

```json
POST /events-write/_rollover
{
  "conditions": {
    "max_age": "30d",
    "max_docs": 1000000,
    "max_size": "50gb"
  }
}
```

If a condition is met, Elasticsearch creates the next index according to the naming convention and switches the write alias to the new index. The read alias can continue pointing to historical indices according to the appropriate rollover/ILM configuration.

Rollover is often combined with Index Lifecycle Management (ILM) to manage hot/warm/cold/delete phases. Note that `events-read` in the example only points to the first index; rolling over the write alias does not automatically add the new index to every other read alias. If you want `events-read` to include the new index as well, you must add the new index to that alias via the Aliases API or configure an appropriate lifecycle policy/template. When using ILM, declare aliases and lifecycle policies consistently; do not manually switch an alias if ILM controls the same alias without understanding the policy state.

## 8. Using aliases in Spring Data Elasticsearch

In Spring Data Elasticsearch, `@Document(indexName = "...")` defines the logical index name that the entity uses. This name can be an alias already created in Elasticsearch:

```java
@Document(indexName = "products", createIndex = false)
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String sku;
}
```

Here, `products` is an alias pointing to a physical index such as `products-v1` or `products-v2`. The repository can still use the alias:

```java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
```

When calling `save`, `findById`, or repository searches, requests are sent to the logical name declared by the entity; Elasticsearch resolves the alias and routes to the physical index.

`createIndex = false` is used in the example when indices/aliases are already managed by migrations or deployment. If Spring Data is allowed to auto-create indices, clearly define the creation order of settings, mappings, and aliases to avoid the application creating a concrete index with the same name as the intended alias. Annotation attributes and auto-creation behavior should be checked against the project's Spring Data Elasticsearch version.

### Creating and switching aliases via IndexOperations

Spring Data Elasticsearch has `IndexOperations` to manage index and alias metadata. Depending on the version, the API may provide methods to add/remove aliases or manipulate aliases via `AliasQuery`/`AliasAction`. If full control over atomic actions is required, you can use the Elasticsearch Java API Client or the REST API directly.

Example of injecting operations to manage indices:

```java
@Service
public class ProductIndexAdminService {

    private final ElasticsearchOperations operations;

    public ProductIndexAdminService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public boolean indexExists(String indexName) {
        return operations.indexOps(IndexCoordinates.of(indexName)).exists();
    }
}
```

The code above illustrates accessing `IndexOperations`; checking alias existence and performing alias updates require using the exact methods/APIs of the running Spring Data version. Do not assume `exists()` on an arbitrary abstraction always distinguishes a concrete index from an alias in the same way as the Elasticsearch Indices API.

For critical alias operations in production, a `_aliases` request is a clear way to express all changes in a single payload and leverage atomic alias updates. It can be invoked through the Elasticsearch Java API Client injected by Spring Boot or through an application-managed HTTP client.

## 9. Deploying a new index version with aliases

A common workflow for changing mappings or analyzers:

1. The application uses the `products` alias pointing to `products-v1`.
2. Create `products-v2` with the new mapping/settings.
3. Reindex data from `products-v1` to `products-v2`.
4. Verify counts, mappings, sample documents, and key queries.
5. Synchronize changes that occurred during reindexing or pause writes as planned.
6. Switch the `products` alias from `products-v1` to `products-v2` using a single `_aliases` request containing remove and add.
7. Monitor the application after cutover; keep the old index for rollback as long as needed.
8. Only delete `products-v1` once the rollback window has expired and data is backed up according to policy.

Diagram:

```text
Before switching:
  Application -> products -> products-v1

Preparation:
  products-v1 -- reindex --> products-v2
  Verify mapping, count, search relevance

After switching:
  Application -> products -> products-v2
  products-v1 is kept temporarily for rollback
```

Switching an alias does not automatically synchronize data. If writes continue to the old index during reindexing, new changes must be handled before switching. Otherwise, new data may be missing in the target index.

## 10. Common errors when managing aliases

| Symptom | Possible cause | How to check or resolve |
|---|---|---|
| `invalid_alias_name_exception` | Alias name matches an index/data stream name or violates naming rules. | Choose a different logical name; an alias cannot share a name with a concrete index. |
| 404 when creating an alias | Target index does not exist yet or index name is wrong. | Create the index first, then add the alias. |
| Writes through multi-index alias rejected | Alias has no designated write index. | Set `is_write_index: true` on exactly one index. |
| Search returns data from multiple versions | Alias points to multiple indices. | Check `GET /_alias/<alias>` and remove indices that are no longer needed. |
| Search does not find documents | Alias filter/routing or alias pointing to the wrong index. | Inspect alias metadata, routing, and mappings. |
| Query errors after switching alias | Mappings between old and new indices are incompatible. | Check mappings of all indices the alias points to. |
| Spring Data auto-creates an index named as the alias | Auto index creation runs before the alias is set up. | Manage indices/aliases via migrations and configure `createIndex` appropriately. |
| Deleted alias but data disappeared | Deleted the concrete index instead of only deleting the alias. | Distinguish `DELETE /<index>/_alias/<alias>` from `DELETE /<index>`. |

When operating on aliases, inspect state before and after with `GET /_alias/<alias>`. For production changes, record the old index, new index, and alias payload so you can verify or roll back.

## 11. Alias naming and management principles

- Use stable, business-meaningful alias names such as `products`, `orders-read`, `orders-write`.
- Use versioned or timestamped physical index names such as `products-v3`, `orders-2026-11`.
- Create the index and mapping before adding aliases.
- For multi-index aliases, explicitly declare the write index if the alias is used for writes.
- Use a single `_aliases` request for atomic remove/add alias switches.
- Verify mappings across indices if a read alias spans multiple indices.
- Do not treat alias filters or routing as security mechanisms.
- Do not confuse deleting an alias with deleting a physical index.
- Keep the old index during the rollback window and delete only after confirmation.
- If ILM/rollover manages an alias, do not manually modify the alias without checking the policy and current state.

## 12. Key takeaways

- An alias is a logical name pointing to one or more indices; data remains in physical indices.
- Create aliases using `PUT /<index>/_alias/<alias>` or the `add` action in `POST /_aliases`.
- Inspect aliases using `GET /_alias/<alias>` or `GET /_cat/aliases?v`.
- Switch aliases using `remove` and `add` actions in the same `POST /_aliases` request for an atomic update.
- Multi-index aliases require an explicit write index if used for writes; an alias can have at most one write index.
- Alias filters affect search; do not use them to protect sensitive data.
- Alias routing assists shard routing but must match the routing used when indexing documents.
- Deleting an alias with `DELETE /<index>/_alias/<alias>` only removes the link; `DELETE /<index>` deletes index data.
- Spring Data can use an alias as `indexName`; index creation and alias lifecycle must be managed intentionally.
- Aliases support new index version rollouts, rollovers, and rollbacks without forcing the application to change physical index names.

Proper alias management allows a Spring Data Elasticsearch application to maintain a stable access name while physical indices are created, replaced, or partitioned over their lifecycle. Create the index first, verify the data, switch the alias in an atomic operation, and preserve rollback capability so index changes remain under control.
