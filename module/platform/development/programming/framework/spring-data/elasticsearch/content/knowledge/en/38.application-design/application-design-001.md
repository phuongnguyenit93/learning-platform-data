# Separating Search Documents from Business Database Entities

In a Spring application, database entities and Elasticsearch documents usually serve two different purposes. A business entity models authoritative data, rules, and domain lifecycle. A search document is organized for fast querying, filtering, sorting, aggregation, and displaying results according to search needs.

If the same class is used for both places, the database storage model will gradually become dictated by how Elasticsearch needs the data; conversely, search mappings may become constrained by the normalized structure of the database. When adding search-specific fields, changing analyzers, denormalizing data, or building another index, changes can spill over into business entities and unrelated write flows.

A clear design separates three concepts:

- **Domain model / database entity:** represents business data and serves as the authoritative source.
- **Search document:** a projection designed specifically for read queries.
- **Projection pipeline:** a mechanism for turning business changes into Elasticsearch documents, which can run asynchronously and be rebuilt.

This is a common application of CQRS: the command side updates business state; the query side reads a separately optimized model. Separating models does not force every application to implement complex CQRS, but it keeps data boundaries clear when search requirements differ from persistence requirements.

## 1. Why shouldn't you share a single entity?

Suppose a product management system has a relational database:

~~~text
Product
  id
  sku
  name
  description
  category_id
  brand_id
  price
  status
  created_at
  updated_at

Category
  id
  name

Brand
  id
  name

Inventory
  product_id
  warehouse_id
  available_quantity
~~~

The database is normalized to avoid data duplication and enforce business rules. A product search page, on the other hand, needs flat data:

~~~json
{
  "id": "p-100",
  "sku": "KB-100",
  "name": "Wireless Keyboard",
  "description": "Compact keyboard for work",
  "categoryName": "Accessories",
  "brandName": "Northwind",
  "price": 49.90,
  "status": "ACTIVE",
  "available": true,
  "availableQuantity": 18,
  "searchText": "Wireless Keyboard Compact keyboard for work Northwind Accessories"
}
~~~

The search document can duplicate `categoryName`, `brandName`, and some inventory fields to avoid joins or multiple lookups at query time. `searchText` can be a field created specifically for full-text search. This is a read model, not a normalized entity used for business updates.

If the same `Product` class is used for both JPA and Elasticsearch:

- JPA and Elasticsearch annotations appear together in the same model.
- An Elasticsearch mapping change can affect the persistence class.
- Denormalized fields may be mistaken for writable authoritative data.
- The entity may carry lazy relationships or proxies that a search converter should not handle.
- A save operation risks updating the wrong system or writing incomplete data.
- Multiple indices with different structures are hard to model separately.

Separating documents allows each model to evolve according to its own needs.

## 2. Distinguishing Domain Entity, Database Entity, and Search Document

These three concepts are related, but they do not have to be a single class.

| Model | Goal | Example responsibilities |
|---|---|---|
| Domain entity/aggregate | Protect invariants and business behavior | Product changes status, validates SKU |
| Database entity | Map persistence schema | ProductEntity, CategoryEntity |
| Search document | Optimize read queries | ProductSearchDocument |

In small applications, the domain entity and database entity can be shared. However, the search document should still be separated when the search structure differs significantly.

Domain example:

~~~java
public class Product {

    private final ProductId id;
    private final Sku sku;
    private String name;
    private ProductStatus status;
    private Money price;

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Product name is required");
        }
        this.name = newName.trim();
    }

    public void activate() {
        this.status = ProductStatus.ACTIVE;
    }
}
~~~

The database entity can use JPA annotations and relationships:

~~~java
@Entity
@Table(name = "products")
public class ProductEntity {

    @Id
    private UUID id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private String name;

    @ManyToOne(fetch = FetchType.LAZY)
    private CategoryEntity category;

    @ManyToOne(fetch = FetchType.LAZY)
    private BrandEntity brand;

    @Enumerated(EnumType.STRING)
    private ProductStatus status;

    private BigDecimal price;

    @Version
    private long version;
}
~~~

The search document has its own mapping:

~~~java
@Document(indexName = "products-read")
public class ProductSearchDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text, analyzer = "product_text")
    private String name;

    @Field(type = FieldType.Text, analyzer = "product_text")
    private String description;

    @Field(type = FieldType.Keyword)
    private String categoryId;

    @Field(type = FieldType.Keyword)
    private String categoryName;

    @Field(type = FieldType.Keyword)
    private String brandId;

    @Field(type = FieldType.Keyword)
    private String brandName;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Boolean)
    private boolean available;

    @Field(type = FieldType.Long)
    private long sourceVersion;
}
~~~

These classes are illustrative examples; getters, constructors, mapping settings, and ID types need to fit your project. The key point is that `ProductSearchDocument` holds fields for querying and does not contain behavior that mutates business state like the `Product` aggregate.

## 3. Search document is a projection, not the source of truth

A projection is a representation built from authoritative data. For a product, the projection might combine:

- Product from the database.
- Category name from the category table.
- Brand name from the brand table.
- Stock status from the inventory service or database.
- Search fields generated from name/description.

A single document can contain data from multiple aggregates or tables. This makes sense for a read model because the goal is to return results quickly and fit the use case.

However, when a document duplicates data from multiple sources, you need to define:

- Which source owns each field.
- Which events require the projection to update.
- How stale the data is allowed to be at most.
- When one source changes, how the projection is recomputed.
- Whether the entire document can be regenerated from the source of truth.

Do not allow APIs to directly update `categoryName` in the search document if the authoritative category name resides in `CategoryEntity`. Consumers should read the authoritative source or receive events with enough information to build the correct projection.

## 4. Design documents for queries, do not copy the database schema

A search document should reflect the queries it needs to serve.

For example, a search screen needs:

- Full-text search on name and description.
- Filtering by category, brand, and status.
- Range queries by price.
- Sorting by price and update date.
- Aggregations counting products by category.
- Displaying category and brand names directly in the results.

The corresponding mapping could be:

~~~json
{
  "settings": {
    "analysis": {
      "analyzer": {
        "product_text": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "sku": { "type": "keyword" },
      "name": {
        "type": "text",
        "analyzer": "product_text",
        "fields": {
          "keyword": { "type": "keyword" }
        }
      },
      "description": {
        "type": "text",
        "analyzer": "product_text"
      },
      "categoryId": { "type": "keyword" },
      "categoryName": {
        "type": "text",
        "fields": {
          "keyword": { "type": "keyword" }
        }
      },
      "brandId": { "type": "keyword" },
      "brandName": { "type": "keyword" },
      "price": { "type": "scaled_float", "scaling_factor": 100 },
      "status": { "type": "keyword" },
      "available": { "type": "boolean" },
      "sourceVersion": { "type": "long" }
    }
  }
}
~~~

The mapping above is an example; choose `scaled_float`, `double`, or another numeric type based on currency precision and query patterns. If using `scaled_float`, standardize the scaling factor and rounding rules. Do not store monetary amounts as `text` if numeric range/sort queries are needed.

`name` is `text` for full-text search and has a `keyword` multi-field for exact sort/aggregation. `categoryId` is `keyword` for exact filtering. `categoryName` can be `text` or `keyword` depending on search and aggregation requirements.

## 5. Intentional denormalization

Databases typically normalize data, whereas search documents typically denormalize to optimize reads. Denormalization is not a design flaw if there are clear synchronization rules.

For example, `categoryName` is copied into many product documents. When a category is renamed:

~~~text
Category "Accessories" -> "Computer Accessories"
                 |
                 v
          CategoryRenamed event
                 |
                 v
       Find affected product IDs
                 |
                 v
      Update product search documents
~~~

There are several ways to update:

1. A consumer receives the event and updates the affected product documents.
2. A consumer receives the event and re-reads the category and products from the database to build new projections.
3. Create a separate read model index or use query-time enrichment if data volume and SLAs permit.

If a category has a very large number of products, a rename event can trigger a huge volume of updates. This should be processed in batches, with checkpoints and retries, rather than keeping a synchronous request open to update everything.

### 5.1. Store ID and label together

A search document should usually keep both the ID and the display name:

~~~json
{
  "categoryId": "cat-7",
  "categoryName": "Accessories"
}
~~~

The ID is used for exact filtering, routing to domains/APIs, and synchronization. The name is used for display, full-text search, or aggregation. Storing only the name can cause difficulties when names change or collide.

### 5.2. Choosing nested, object, or flatten

If a document contains a list of variants:

~~~json
{
  "variants": [
    { "color": "black", "size": "M", "stock": 5 },
    { "color": "white", "size": "L", "stock": 2 }
  ]
}
~~~

If you need to preserve the relationship between fields of the same element when querying (for example, color `black` and size `M` must belong to the same variant), consider `nested` mapping. With regular `object` mapping, array values can be flattened and queries combining fields may match across different elements.

`nested` has its own storage and query overhead. Do not choose it just because JSON has an array of objects; choose based on query semantics. A search document is a read model, so it can be structured differently from the database as long as it satisfies the search conditions correctly.

## 6. Building a projection from database entities

Do not let controllers or search repositories arbitrarily convert database entities into documents. Create a mapper or projection factory with clear responsibilities:

~~~java
public class ProductSearchDocumentMapper {

    public ProductSearchDocument toDocument(
            ProductEntity product,
            CategoryEntity category,
            BrandEntity brand,
            InventorySummary inventory
    ) {
        ProductSearchDocument document =
                new ProductSearchDocument();

        document.setId(product.getId().toString());
        document.setSku(product.getSku());
        document.setName(product.getName());
        document.setDescription(product.getDescription());
        document.setCategoryId(category.getId().toString());
        document.setCategoryName(category.getName());
        document.setBrandId(brand.getId().toString());
        document.setBrandName(brand.getName());
        document.setPrice(product.getPrice());
        document.setStatus(product.getStatus().name());
        document.setAvailable(inventory.availableQuantity() > 0);
        document.setSourceVersion(product.getVersion());

        return document;
    }
}
~~~

The mapper should only perform data transformation. Deciding which sources to fetch, handling missing data, and ensuring the latest version belong to the projection service or query handler.

If multiple tables are needed, avoid calling repositories repeatedly per product, which causes N+1 queries. You can fetch data using a join/projection query in the database or batch-load references by a set of IDs and then map in memory.

### 6.1. Avoiding lazy proxy dependencies

JPA entities have `LAZY` relationships. If a mapper accesses a relationship after the transaction closes, it may throw a `LazyInitializationException`. If mapping happens inside the transaction but each entity triggers its own query, it can cause N+1 queries.

Solutions:

- Use a query projection/DTO in the database to fetch exactly the data needed for the search document.
- Use fetch joins or entity graphs where appropriate.
- Batch-load categories/brands/inventory by list of IDs.
- Only build search documents from fully loaded data.

Do not serialize an entire JPA entity directly to Elasticsearch. Doing so can drag along proxies, circular relationships, internal fields, and unnecessary data.

## 7. Synchronizing database and Elasticsearch: avoiding dual writes

A seemingly simple approach:

~~~java
@Transactional
public void renameProduct(UUID id, String newName) {
    ProductEntity product = productRepository.findById(id)
            .orElseThrow();

    product.setName(newName);
    productRepository.save(product);

    elasticsearchOperations.save(
            mapper.toDocument(product)
    );
}
~~~

This code has a dual-write risk. The database and Elasticsearch are two independent systems. Consider one scenario:

1. The database commit succeeds.
2. Elasticsearch is unavailable.
3. The method throws an exception.
4. The database transaction may already have committed depending on ordering and the transaction manager; there is no shared rollback guaranteeing both sides return to their previous state.

Or Elasticsearch writes successfully while the database rolls back. The two places will drift out of sync.

Do not rely on an ordinary `@Transactional` annotation to make two systems commit atomically. You need a recoverable synchronization mechanism.

## 8. Transactional Outbox for projections

Outbox solves the gap between database commit and event publishing by writing the event within the same transaction as the business change.

Flow:

~~~text
Command
  |
  v
Database transaction
  |                    |
  v                    v
Update Product      Insert Outbox Event
  |                    |
  +---------+----------+
            |
            v
          Commit
            |
            v
      Outbox Publisher
            |
            v
        Message/Event
            |
            v
     Projection Consumer
            |
            v
  Build ProductSearchDocument
            |
            v
   ElasticsearchOperations.save
~~~

Example:

~~~java
@Transactional
public void renameProduct(UUID productId, String newName) {
    ProductEntity product = productRepository.findById(productId)
            .orElseThrow();

    product.rename(newName);
    productRepository.save(product);

    outboxRepository.save(
            OutboxEvent.productChanged(
                    product.getId(),
                    product.getVersion()
            )
    );
}
~~~

The publisher reads committed events and sends them to a broker or consumer. The consumer can receive the ID and version, read the current data from the database, rebuild `ProductSearchDocument`, and write it to Elasticsearch.

Outbox does not make Elasticsearch part of the database transaction. It ensures the event is durably stored alongside the source change so the publisher can resend it after failures.

### 8.1. Should events carry data or only IDs?

There are two common forms:

**Events carrying a snapshot/payload:** contain the data needed for the projection. The consumer does not need to re-read multiple tables, but events can be large and schemas/versions must be managed.

**Events carrying only aggregate ID and version:** the consumer re-reads the current data from the source of truth. Events are small and projections are always built from the latest state, but the consumer needs database access and must handle backlogs of multiple accumulated events.

Minimal event example:

~~~java
public record ProductChanged(
        UUID productId,
        long aggregateVersion,
        Instant occurredAt
) {
}
~~~

If the consumer receives an event for version 8 while the database is already at version 10, it can build the projection from the version 10 state. This fits when the goal is updating the read model to the latest state, rather than replaying every intermediate state.

If exact transitions, auditing, or side effects must be reflected, events must carry enough information and be processed in order.

## 9. Idempotent consumers and handling duplicate events

Outbox publishers typically operate with at-least-once delivery: if unsure whether publishing succeeded, they may resend. Consumers must tolerate duplicate events.

For absolute-state projections:

- Use a stable document ID, such as the product ID.
- Store `sourceVersion` in the search document.
- Do not apply an event whose version is older than the already indexed version.
- If a duplicate event with the same version and content arrives, rewriting or skipping must keep the result consistent.

Pseudo-code:

~~~java
public void handle(ProductChanged event) {
    ProductEntity current =
            productRepository.findById(event.productId())
                    .orElseThrow();

    ProductSearchDocument candidate =
            mapper.toDocument(current);

    ProductSearchDocument indexed =
            searchDocumentReader.findById(candidate.getId());

    if (indexed != null
            && indexed.getSourceVersion() >= candidate.getSourceVersion()) {
        return;
    }

    elasticsearchOperations.save(candidate);
}
~~~

This illustrates the logic, not an atomic compare-and-set operation. Two concurrent consumers could both read an old version and then write in an undesired order. Under real concurrency, you need to serialize by aggregate key, use external versioning or optimistic concurrency in Elasticsearch, or use an atomic conditional update mechanism.

Do not treat a get-then-save sequence as if it were compare-and-set. Between those two operations there is still a race condition.

### 9.1. External versioning and optimistic concurrency

Elasticsearch supports document-level version control mechanisms. You can use `if_seq_no`/`if_primary_term` for operations based on a read document version, or external versioning when business versions meet the requirements and the API supports it.

Choose the mechanism based on semantics:

- Elasticsearch internal version protects operations based on the storage version that was read.
- Aggregate version in the event indicates the order of business states.
- External version can reject writes of an older version when used in the right mode.

These two types of versions are not synonymous. `@Version` on a Spring Data Elasticsearch entity is typically used for optimistic locking of the document, not automatically as the aggregate version from the database. If you need to protect the projection by database version, map and apply the business version explicitly.

## 10. Handling updates and deletes in projections

The projection consumer must handle every type of change:

| Domain event | Action on search index |
|---|---|
| ProductCreated | Create document |
| ProductRenamed | Update document |
| ProductPriceChanged | Update price and version |
| ProductDeactivated | Update status or delete per search requirement |
| ProductDeleted | Delete document or create tombstone |
| CategoryRenamed | Update categoryName on related documents |

### 10.1. Deletes and late-arriving events

Suppose `ProductDeleted` version 12 arrives before `ProductUpdated` version 11. If the consumer deletes the document and then the old version 11 event arrives, it could recreate the deleted document.

To prevent resurrection:

- Retain the deleted entity's version/tombstone for a necessary period.
- Ignore events with a version less than or equal to the tombstone version.
- Or guarantee event ordering by aggregate ID and process sequentially in the consumer.

If a document is completely deleted, version metadata may no longer exist to compare against old events. A tombstone projection can retain the ID, `deleted=true`, and `sourceVersion` to block late events. After a retention period, tombstones can be purged once you are certain old events will no longer be replayed.

### 10.2. Soft deletes and search filters

If the database uses soft deletes, the search document needs to reflect the corresponding state. You can:

- Not index deleted documents.
- Keep documents with `deleted=true` and add a mandatory filter in queries.
- Keep separate tombstones to protect version/ordering.

Choose based on audit, restore, and search requirements. If using `deleted=true`, every public query must always add a server-side filter so deleted records are never exposed.

## 11. Search API reads documents, command API reads business entities

When separating models, APIs should use the right source:

~~~text
Command: rename product
    |
    v
Product application service
    |
    v
Domain / database repository
    |
    v
Database transaction + outbox

Query: search products
    |
    v
Product search service
    |
    v
ElasticsearchRepository / ElasticsearchOperations
    |
    v
ProductSearchDocument
~~~

The command API needs to validate invariants and update the source of truth. The search API needs to query a read-optimized projection. If a user opens a detail page requiring the latest exact data, you can take the ID from the search result and read the business entity from the database.

A combined pattern:

1. Elasticsearch search returns IDs, scores, and summary fields.
2. The user selects a product.
3. The detail service reads the product from the database by ID.
4. Business actions are performed on the domain entity/database.

Do not use search documents as direct input for critical commands if they may be stale or lack business fields.

## 12. Search documents can differ by use case

There does not have to be only one document per aggregate. Different screens may need different read models:

- `ProductSearchDocument`: product search.
- `ProductSuggestionDocument`: autocomplete/suggest.
- `ProductInventoryDocument`: inventory lookup by warehouse.
- `CatalogLandingDocument`: pre-aggregated data for category pages.

Each projection can have its own index, analyzer, and fields. Avoid creating too many duplicate indices if queries can be served from one reasonable document; but also do not bloat a single document to satisfy every screen.

Decide based on query patterns and SLAs, update frequency of each source, document size and number of data copies, fan-out update cost, rebuildability, security requirements, and retention.

## 13. Do not put all related data into a single document

Denormalization reduces lookups but increases update costs. If a product has millions of views and each view changes a counter, continuously updating the product document can cause contention.

Consider:

- Which fields need direct filtering/sorting/aggregation.
- Which fields can be fetched from the detail API after searching.
- Which fields can be computed in batches.
- Which fields need real-time updates and which can tolerate delay.
- Whether to split read models by update frequency.

Do not index a massive object just because the database entity has many relationships. Every field added to a document affects storage size, mapping, indexing cost, and update speed.

## 14. Rebuilding the search index from the source of truth

A major benefit of separating projections is being able to delete and rebuild the search index from the database/event history.

Basic rebuild process:

1. Create a new index with the new mapping/settings.
2. Read source data in batches and build search documents.
3. Bulk index into the new index.
4. Track per-item errors, retry transient item failures, and save checkpoints.
5. Synchronize changes that occurred during the backfill.
6. Verify counts, versions, key queries, and sample data.
7. Switch the read alias to the new index.
8. Keep the old index for a period to roll back if needed.

Do not delete the production index before the new index is verified. Use an alias to switch over:

~~~http
POST /_aliases
Content-Type: application/json

{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-read"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-read"
      }
    }
  ]
}
~~~

Switching an alias in a single request is an appropriate operation for shifting the read target. Ensure the alias exists properly and the new index has completed backfill/validation before switching.

### 14.1. Synchronizing changes during backfill

If you only scan the database and switch the alias at the end, changes occurring during the scan might be missing from the new index or overwritten by stale snapshots.

A common approach:

- Record a watermark/event position before starting the backfill.
- Backfill snapshots in batches.
- Replay events from the watermark to apply new changes.
- Use aggregate versions to skip old events or detect gaps.
- Only switch the alias once the projection catches up.

Another option is temporary dual projection to both the old and new indices, though ordering and idempotency must be controlled. Do not arbitrarily write to two indices in business requests without a recovery mechanism.

## 15. Search document schema versioning

Search documents can evolve independently from database entities. For example:

- v1 stores `categoryName`.
- v2 adds `categoryPath` and changes the analyzer.
- v3 splits `suggestName` into a separate field.

Do not assume that changing a class's mapping will automatically update an existing index. Certain field type or analyzer changes require creating a new index and reindexing.

Manage:

- Mapping/index versions.
- Event schema versions if events contain snapshots.
- Mappers from database/domain to each projection version.
- Backfill/rebuild procedures.
- Read/write aliases and cutover timing.

If events only carry ID and version and the consumer reads the current source, rebuilding a new document version can be simpler because the new mapper builds the new projection from the same source data.

## 16. Testing the boundary between the two models

You should have the following test groups:

### 16.1. Mapper tests

Pass database entities/DTOs and references into the mapper, and verify that the search document has the right fields, ID, version, status, and denormalized values.

Test cases where category/brand does not exist or was deleted, inventory has no data yet, price/currency has different scales, status is not searchable, and nullable fields.

### 16.2. Projection consumer tests

Verify that valid events create/update the right document ID; duplicate events produce no duplicate side effects; old events do not overwrite newer versions; delete events create tombstones or delete per policy; and Elasticsearch errors are retried or moved to a pending state.

### 16.3. Integration tests with Elasticsearch

Use a compatible real Elasticsearch instance to verify that mappings and analyzers are installed properly, documents serialize properly, filter/sort/full-text queries return expected results, aggregations use the right fields, bulk partial failures are handled per item, and aliases point to the right index.

### 16.4. End-to-end consistency tests

Execute a command updating the database, wait for the outbox consumer to process it, and then query Elasticsearch:

~~~text
Rename product in database
          |
          v
Outbox event committed
          |
          v
Consumer processes event
          |
          v
Search document updated
          |
          v
Search API returns new name
~~~

Tests should have a bounded wait timeout and report status if the projection does not converge. Do not use long fixed sleeps assuming an event has been processed; poll conditions with a deadline or wait on test-specific signals.

## 17. Security and sensitive data in projections

Search documents often copy data from multiple sources. That increases the number of places storing data and requires clear security policies.

- Do not put passwords, tokens, secrets, or unneeded fields into documents.
- Do not index personal information just because it is present in the entity.
- Define which fields are visible to each user group.
- Enforce mandatory tenant/security filters in server-side queries.
- Delete or update projections when access permissions or data status changes.
- Set retention and data deletion workflows aligned with the source of truth.

If a search document contains copied sensitive data, deleting it from the database while forgetting to delete it from Elasticsearch can still expose data via search. The projection pipeline must handle delete/privacy events and have verification/repair mechanisms.

## 18. Common design mistakes

| Mistake | Consequence | Solution |
|---|---|---|
| Using JPA entity directly as search document | Model tightly coupled to two storages, hard to change mapping | Create a separate projection class |
| Writing database and Elasticsearch sequentially in the same service | Dual-write inconsistency when one side fails | Transactional outbox |
| Search document used as source of truth | Stale data can drive business decisions | Commands read/update source of truth |
| Denormalizing without tracking field sources | Copied fields go stale when source data changes | Events and projection rebuild |
| Mapping JPA lazy relations directly | N+1 or lazy initialization errors | Projection query/batch fetch |
| Non-idempotent consumer | Duplicate events create incorrect state | Event ID, version, and idempotent writes |
| Old event written after new event | Search document regresses to stale data | Aggregate version/ordering |
| Delete without tombstone or version | Old update event can resurrect document | Tombstone and stale-event guard |
| Rebuild overwrites newer changes | New index misses updates | Watermark and event replay |
| Changing mapping on live index | Incompatible mapping or index errors | Versioned index and alias switch |
| Indexing every field of entity | Increased cost and data exposure | Include only query-serving fields in projection |

## 19. Process for designing a Search Document

1. List the queries/use cases the index needs to serve.
2. Identify fields needed for full-text, exact filters, sorting, aggregation, and display.
3. Identify the source of truth for each field.
4. Design a flat/denormalized document around the queries.
5. Choose mappings, analyzers, nested/object types, and multi-fields.
6. Create a separate search document class rather than reusing the business entity when the two models serve different purposes.
7. Write a mapper/projection factory from the source data.
8. Choose event payload or ID+version for the projection pipeline.
9. Use outbox or a durable delivery mechanism.
10. Make consumers idempotent and protect event ordering/versioning.
11. Handle updates, deletes, retries, and partial bulk failures.
12. Establish procedures for rebuild, backfill, versioned indices, and alias cutover.
13. Test mappers, consumers, mapping/search, and eventual consistency.
14. Monitor projection lag, consumer errors, and document drift counts.

## 20. Conclusion

Database entities and Elasticsearch search documents serve two different purposes. Business entities protect authoritative data and invariants; search documents are projections organized around query patterns that can be denormalized and evolved independently. Separating the two models lets mappings, analyzers, search fields, and multiple read models evolve without tangling domain persistence.

Projections need to be updated by a recoverable pipeline. When the database is the source of truth, a transactional outbox stores business changes and events in the same transaction; consumers turn events into search documents and handle duplicates, event ordering, versions, and deletes. Do not rely on dual writes or an ordinary `@Transactional` to commit the database and Elasticsearch as one transaction.

Design search documents for actual queries, identify the source of each denormalized field, control concurrency, and ensure the index can be rebuilt from source data. When a search index is simply a regenerable read model, the application maintains clear boundaries: commands protect business rules, projections serve search, and eventual consistency is managed through events, versions, and operational procedures.
