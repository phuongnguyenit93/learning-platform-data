# Denormalized Design Instead of Relational Joins

Elasticsearch is a document-oriented search engine. An application stores independent JSON documents and queries over indexed fields. This model differs from a relational database, where an application can normalize data into multiple tables and combine them with JOINs in each SQL statement.

In Elasticsearch Query DSL, there is no general-purpose JOIN between two arbitrary indexes or two arbitrary sets of documents. Elasticsearch has a parent-child mechanism based on a `join` field, but this is a specialized feature with routing requirements and is typically more expensive than querying a single document. Therefore, the common approach is to design documents around how data will be read and searched: storing the required attributes together and accepting some data duplication to reduce query steps.

That is **denormalization**. It is not arbitrary data copying. The application needs to identify the canonical data source, the read models to serve, which data should be embedded into a document, which data should be copied for filtering/searching, and how to update copies when the source changes.

## 1. Why doesn't the relational model map directly to Elasticsearch?

In a relational database, a sales application might store:

~~~sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200),
    brand_id BIGINT
);

CREATE TABLE brand (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100)
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT,
    product_id BIGINT,
    quantity INTEGER,
    unit_price DECIMAL(12, 2)
);
~~~

When searching for order lines by product name or brand, SQL can JOIN `order_line` with `product` and then JOIN `brand`. The database manages foreign keys and joins the data at query time.

In Elasticsearch, documents are indexed independently. A search query on a single index does not automatically join fields from one document with a document in another index via a foreign key. If a query frequently needs the product name, brand name, and price at order time, the required data should be placed into the document serving that query.

For example, an order line can store a snapshot:

~~~json
{
  "orderId": "ORD-2026-1001",
  "lineId": "LINE-01",
  "productId": "P-1042",
  "sku": "KB-1042",
  "productName": "Mechanical Keyboard",
  "brandName": "KeyWorks",
  "quantity": 2,
  "unitPrice": 129.5,
  "currency": "USD"
}
~~~

The document can directly answer questions about the order without needing to look up product and brand documents to merge in.

### 1.1. The traded costs

Denormalization reduces read and query work, but shifts part of the cost to writes and synchronization:

| Aspect | Normalized model | Denormalized model |
| --- | --- | --- |
| Data | An attribute is usually stored in one place | May be repeated across multiple documents |
| Reads | May require joining multiple sources | Usually read from a single document/read model |
| Writes | Update a single source record | May have to update multiple copies |
| Consistency | Foreign keys and transactions in a relational DB | Requires synchronization mechanisms and event handling |
| Search | JOIN then filter/sort | Filter directly on indexed fields |
| Storage | Typically less duplication | Increases with the number of copied attributes |

Neither model is always better. You must choose based on critical queries, update frequency, data volume, and the consistency level required by the business.

## 2. Designing from access patterns

Before deciding whether to embed or split documents, list how the application actually reads data. The same dataset may require several different read models.

For example, an e-commerce system has queries such as:

- Opening a product detail page, needing name, description, brand, category, and variants.
- Searching products by name, brand, category, price, and status.
- Opening an order, needing a snapshot of the purchased products and prices.
- Viewing review history by product, which can have millions of reviews.
- Finding products by attributes of a specific offer.

You should not force a single document model to serve every case if they have different requirements. A product can be represented in the product index, in order snapshots, and in a search suggestion index.

### 2.1. Questions to answer

When designing a document, determine:

1. Which queries need to run frequently and have strict latency requirements?
2. Which fields are always read together?
3. Is the relationship one-to-one, one-to-many, or many-to-many?
4. Is the number of child elements bounded or unbounded?
5. Are child elements updated independently?
6. Does the application need to search on parent fields from a child document, or vice versa?
7. Is the copied data a historical snapshot or must it always reflect the latest state?
8. What level of synchronization lag is acceptable?
9. When updating the source, could it require updating thousands or millions of documents?

These answers define document boundaries and the update strategy.

### 2.2. Modeling around read queries

~~~text
Canonical data source
       |
       v
Critical queries
       |
       v
Read model design
       |
   +---+---+
   |       |
   v       v
 Embed   Copy fields
   |       |
   +---+---+
       |
       v
 Elasticsearch document
       |
       v
 Direct search
~~~

Documents are optimized for reading. If a query has to join multiple documents on every request, consider putting the needed fields into the same read model.

## 3. Embedding objects when data is always read together

One-to-one relationships, or one-to-one from the document's perspective, usually fit nested JSON objects well.

For example, a product with brand information:

~~~json
{
  "id": "P-1042",
  "name": "Mechanical Keyboard",
  "brand": {
    "id": "B-10",
    "name": "KeyWorks",
    "country": "US"
  }
}
~~~

The application can read both the product name and brand name in a single document fetch.

### 3.1. Spring Data entity

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Object)
    private BrandInfo brand;

    // Constructors, getters, and setters
}

public class BrandInfo {

    @Field(type = FieldType.Keyword)
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Keyword)
    private String country;

    // Constructors, getters, and setters
}
~~~

`FieldType.Object` is appropriate when the child object's attributes do not need to be queried together on the same element within an array of objects. If there is only a single brand object, object mapping is usually sufficient.

### 3.2. When is there no need to split brand into a separate index?

If the product page always needs the brand name, the brand has few fields, and brand name changes do not happen too frequently, embedding a copy of the brand in the product document is usually simple.

If a brand has hundreds of fields, large content, or is managed independently, it is not necessary to embed the entire brand. Only copy the attributes that product queries need, such as `brand.id`, `brand.name`, and `brand.logoUrl`.

## 4. Embedding child arrays: object or nested?

A product may have variants:

~~~json
{
  "id": "P-1042",
  "name": "Mechanical Keyboard",
  "variants": [
    {
      "sku": "KB-1042-BLK",
      "color": "black",
      "price": 129.5
    },
    {
      "sku": "KB-1042-WHT",
      "color": "white",
      "price": 139.5
    }
  ]
}
~~~

If you only display all variants alongside the product and do not need to query multiple fields on the same variant, an object array may suffice. If you need correlated conditions, such as finding a product that has a variant that is both `black` and priced under 130, you should consider `nested`.

### 4.1. The cross-object matching problem with object arrays

With regular `object` mapping, Elasticsearch can index child fields as multi-valued sets. The relationship between the fields of each individual element can be lost at query time.

For example:

~~~json
{
  "variants": [
    { "color": "black", "price": 150 },
    { "color": "white", "price": 100 }
  ]
}
~~~

A query with conditions `color=black` and `price<130` can match the document because the individual values exist, even though no single variant satisfies both.

### 4.2. Nested array

Declaring `nested`:

~~~java
@Field(type = FieldType.Nested)
private List<ProductVariant> variants;
~~~

Nested query:

~~~json
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "variants.color": "black"
              }
            },
            {
              "range": {
                "variants.price": {
                  "lt": 130
                }
              }
            }
          ]
        }
      }
    }
  }
}
~~~

`nested` mapping preserves the relationship between fields within the same element. The query only matches when a single variant satisfies both conditions.

### 4.3. Cost of nested

A nested object is indexed as a hidden document linked to the parent. A parent with many nested elements increases the internal document count and indexing/query cost.

Use `nested` when you need to preserve relationships between fields within each array element. Do not use `nested` just because the JSON contains nested objects. For a single object or an array of objects used only for display, `object` mapping can be simpler and more economical.

## 5. One-to-many: embed child data or split into documents?

One-to-many relationships are the most important decision in document design.

For example, an order with order lines:

~~~json
{
  "orderId": "ORD-2026-1001",
  "customerId": "C-100",
  "status": "PAID",
  "lines": [
    {
      "lineId": "L-1",
      "productId": "P-1042",
      "sku": "KB-1042",
      "productName": "Mechanical Keyboard",
      "quantity": 2,
      "unitPrice": 129.5
    },
    {
      "lineId": "L-2",
      "productId": "P-2077",
      "sku": "MS-2077",
      "productName": "Wireless Mouse",
      "quantity": 1,
      "unitPrice": 49.9
    }
  ]
}
~~~

### 5.1. Embed when the element count is bounded

Embedding `lines` in an order is suitable if:

- An order has a finite number of lines that is usually not too large.
- The order page always needs the order lines.
- Order lines do not need to be searched or paginated independently of the order.
- Order updates are typically performed as a single aggregate.

The advantage is fetching the order in one request without joining against the product index.

### 5.2. Snapshotting data at transaction time

An order line should usually store the product name, SKU, and unit price at the time of purchase. This is a historical snapshot, not a copy that needs to be synchronized with every product change.

If the product changes its name or price after the order is placed, order history must still display the data from the time of the transaction. Therefore, distinguish between:

- Business-immutable snapshot: keep the transacted value as-is.
- Denormalized current value: a copy that must reflect the latest data.

You should not bulk-update order history when a product changes price if that field represents the purchase price at order time.

### 5.3. When to split order lines into separate documents?

If the system needs to search hundreds of millions of order lines, filter by product, analyze individual lines, or update them independently, each line can be indexed as a separate document:

~~~json
{
  "lineId": "L-1",
  "orderId": "ORD-2026-1001",
  "customerId": "C-100",
  "orderStatus": "PAID",
  "productId": "P-1042",
  "sku": "KB-1042",
  "productName": "Mechanical Keyboard",
  "quantity": 2,
  "unitPrice": 129.5
}
~~~

The fields `orderStatus`, `customerId`, and `productName` are copied so lines can be queried directly. In return, if the order status changes, the line documents may need to be updated.

### 5.4. Do not embed unbounded arrays

You should not embed an entire activity history, event stream, or review list into a parent document if the number of elements grows continuously.

The risks:

- Documents grow increasingly large and expensive to read/write.
- Updating one element can cause the entire large document to be reindexed.
- Oversized documents can put pressure on heap, network, and segment merges.
- It is difficult to paginate child elements separately.
- Document size and nested object limits can be reached.

For unbounded child data, you should usually split children into separate documents and copy the parent fields needed for searching.

## 6. Copying parent attributes into child documents

Suppose the application needs to find all reviews for products belonging to the brand `KeyWorks`. Reviews are stored as separate documents:

~~~json
{
  "reviewId": "R-10001",
  "productId": "P-1042",
  "productName": "Mechanical Keyboard",
  "brandId": "B-10",
  "brandName": "KeyWorks",
  "rating": 5,
  "content": "Excellent keyboard"
}
~~~

The review document contains `brandName` and `productName` copied from the product. When a user searches for reviews by brand, the query runs directly on the `reviews` index:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "brandId": "B-10"
          }
        },
        {
          "range": {
            "rating": {
              "gte": 4
            }
          }
        }
      ]
    }
  }
}
~~~

There is no need to JOIN reviews with products and brands to filter. `brandId` is a stable field for filtering; `brandName` is a copy for display or full-text search.

### 6.1. Be careful when parent attributes change

If a brand changes its name, all reviews holding the old `brandName` may need to be updated. A brand with millions of reviews will trigger a massive fan-out write.

Options:

- Copy only the stable ID and fetch the brand name from a cache/service at display time.
- Copy the name as well, accepting eventual consistency.
- Use an aggregated read model index updated via events.
- Keep the name at review time if it is a historical snapshot.

The decision depends on whether the name must reflect the current state or historical state.

### 6.2. Denormalize only the needed fields

There is no need to copy the entire parent object. Only copy the fields that child queries require:

~~~json
{
  "reviewId": "R-10001",
  "productId": "P-1042",
  "brandId": "B-10",
  "brandName": "KeyWorks",
  "productCategory": "keyboards",
  "rating": 5
}
~~~

Keeping documents lean reduces index size, synchronization cost, and read time.

## 7. Many-to-many: tags, categories, and memberships

Many-to-many relationships in relational databases are typically represented with a join table. In Elasticsearch, many cases can store an array of IDs or an array of objects directly inside the document.

For example, an article with multiple tags:

~~~json
{
  "articleId": "A-100",
  "title": "Elasticsearch Data Modeling",
  "tagIds": ["search", "database", "java"],
  "tagNames": ["Search", "Database", "Java"]
}
~~~

Query to find articles with the `database` tag:

~~~json
{
  "query": {
    "term": {
      "tagIds": "database"
    }
  }
}
~~~

With a multi-valued `keyword` field, a `term` query matches if any value matches.

### 7.1. When per-relationship attributes are needed

If the article-tag relationship has extra attributes such as display order, who tagged it, when it was tagged, or priority, store an array of objects:

~~~json
{
  "articleId": "A-100",
  "tags": [
    {
      "id": "search",
      "name": "Search",
      "position": 1
    },
    {
      "id": "database",
      "name": "Database",
      "position": 2
    }
  ]
}
~~~

If you need to query by attributes that must belong to the same relationship entry, use `nested`:

~~~json
{
  "query": {
    "nested": {
      "path": "tags",
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "tags.id": "database"
              }
            },
            {
              "range": {
                "tags.position": {
                  "lte": 2
                }
              }
            }
          ]
        }
      }
    }
  }
}
~~~

### 7.2. When is a separate relation index needed?

If a relationship has a large volume, an independent lifecycle, or needs to be queried and paginated as an entity, you can create a separate relation index:

~~~json
{
  "articleId": "A-100",
  "tagId": "database",
  "tagName": "Database",
  "position": 2,
  "createdAt": "2026-03-01T10:00:00Z"
}
~~~

The relation document can copy `articleTitle` or `tagCategory` if queries need to filter by them. There is no automatic join to fetch information from `article` and `tag`.

## 8. One document can serve multiple queries using selective copies

For example, a product document:

~~~json
{
  "id": "P-1042",
  "name": "Mechanical Keyboard",
  "brand": {
    "id": "B-10",
    "name": "KeyWorks"
  },
  "category": {
    "id": "C-KEY",
    "name": "Keyboards"
  },
  "searchText": "Mechanical Keyboard KeyWorks Keyboards",
  "price": 129.5,
  "available": true
}
~~~

The document supports the detail page, brand/category filtering, and full-text search at the same time. However, duplicated fields like `brand.name` and `category.name` must be updated when the source data changes.

Not every duplicated field has to be stored in the same form:

- IDs are used for exact filtering and logical linking.
- Names are used for display or full-text search.
- `keyword` subfields are used for sorting/aggregations.
- `text` fields are used for `match` queries.
- Snapshots are used for transaction history.

Mappings should reflect the query purpose of each field.

## 9. Spring Data Elasticsearch: storing denormalized documents

Spring Data Elasticsearch does not automatically perform relational joins. An entity maps to a single Elasticsearch document. All objects and fields included in the entity are written together in the same document according to the mapping.

For example, a product read model:

~~~java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductSearchDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String brandId;

    @Field(type = FieldType.Keyword)
    private String brandName;

    @Field(type = FieldType.Keyword)
    private String categoryId;

    @Field(type = FieldType.Keyword)
    private String categoryName;

    @Field(type = FieldType.Nested)
    private List<ProductVariant> variants;

    // Constructors, getters, and setters
}

public class ProductVariant {

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String color;

    @Field(type = FieldType.Double)
    private double price;

    // Constructors, getters, and setters
}
~~~

This document pre-stores brand/category names for search and display. `variants` is mapped as `nested` because queries may require correlated conditions across `color`, `sku`, and `price` within the same variant.

### 9.1. Building a read model document from canonical sources

Controllers should not assemble objects manually and write directly to Elasticsearch. Create a dedicated mapper or projector:

~~~java
public ProductSearchDocument toSearchDocument(
        Product product,
        Brand brand,
        Category category) {

    ProductSearchDocument document = new ProductSearchDocument();
    document.setId(product.getId());
    document.setName(product.getName());
    document.setBrandId(brand.getId());
    document.setBrandName(brand.getName());
    document.setCategoryId(category.getId());
    document.setCategoryName(category.getName());
    document.setVariants(product.getVariants().stream()
        .map(this::toVariant)
        .toList());

    return document;
}
~~~

This code illustrates a projector reading canonical data sources and producing a document tailored to the query model. In an actual project, the source classes and mapper depend on your domain architecture.

### 9.2. Saving with ElasticsearchOperations

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchIndexer {

    private final ElasticsearchOperations operations;

    public ProductSearchIndexer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void index(ProductSearchDocument document) {
        operations.save(document);
    }
}
~~~

`save` writes the document by ID and mapping metadata. It does not look up other brand/category documents to merge automatically. Denormalized data must be prepared before calling `save`.

### 9.3. Repositories and queries

~~~java
public interface ProductSearchRepository
        extends ElasticsearchRepository<ProductSearchDocument, String> {

    List<ProductSearchDocument> findByBrandId(String brandId);

    List<ProductSearchDocument> findByCategoryId(String categoryId);
}
~~~

These query methods run on fields copied into the product document. There is no need to query the brand index for names or the category index for filtering.

## 10. Maintaining consistency when source data changes

Denormalization raises an important question: if a source attribute changes, how are its copies across multiple documents updated?

Suppose brand `B-10` renames from `KeyWorks` to `KeyWorks Labs`. This name is copied into 500,000 product documents and 2 million review documents.

The application must decide:

- Should all copies be updated immediately or is lag acceptable?
- Should updates happen synchronously in one request or in the background?
- If part of a batch fails, where should it resume from?
- How do we prevent stale events from overwriting newer data?
- How do we detect missed documents?

### 10.1. Choosing the canonical data source

Every attribute must have a clear canonical source:

| Attribute | Canonical source | Copies |
| --- | --- | --- |
| Product name | Product database/service | Product search document, suggestion index |
| Current brand name | Brand database/service | Product search document, review read model |
| Purchase price at order time | Order line | Order document, order line index |
| Order status | Order service | Order document, line read model if needed |
| Suggestion selection count | Analytics/event stream | Completion weight |

Do not use an Elasticsearch read model as the canonical source for transactional data if it was only designed to serve search.

### 10.2. Event-driven projection

A common approach is updating read models via events:

~~~text
Canonical data source
       |
       v
 Write transaction
       |
       v
   Outbox event
       |
       v
  Event publisher
       |
       v
 Projector / consumer
       |
       v
 Elasticsearch index
~~~

Example `BrandRenamed` event:

~~~json
{
  "eventId": "EVT-9001",
  "eventType": "BrandRenamed",
  "brandId": "B-10",
  "newName": "KeyWorks Labs",
  "version": 42,
  "occurredAt": "2026-03-12T09:00:00Z"
}
~~~

The consumer receives the event and updates product documents with `brandId=B-10`. If large fan-out is needed, updates can be dispatched in batches or the read model can be rebuilt from the canonical source.

### 10.3. Transactional outbox

If writing to the DB and publishing a message are two independent operations, the following can occur:

- DB commit succeeds, but publishing fails.
- Publishing succeeds, but the DB transaction rolls back.

The transactional outbox writes the business change and the event within the same DB transaction. A separate publisher reads the outbox and sends the event. This reduces the risk of losing events between the two systems.

Elasticsearch is still updated asynchronously, so the read model typically has eventual consistency.

### 10.4. Idempotent consumers

Events can be redelivered when a consumer retries. Projectors should be idempotent so processing the same event multiple times does not corrupt state.

Common techniques:

- Use an event ID to detect already-processed events.
- Use stable document IDs to overwrite the same read model.
- Use the source version to reject stale events.
- Design updates as deterministic value assignments rather than unguarded increments.
- Record failures so they can be retried or routed to a dead-letter queue.

### 10.5. Preventing stale events from overwriting newer data

Suppose event version 42 changes the brand name, and then version 43 changes it again. If event 42 arrives late, the consumer must not overwrite the newer name with the old one.

You can store the source version in the read model:

~~~json
{
  "brandId": "B-10",
  "brandName": "KeyWorks Labs",
  "brandVersion": 43
}
~~~

The projector only applies events with a version newer than the stored version. For conditional updates, you can use Elasticsearch optimistic concurrency or version-checking logic at the application layer depending on the model.

## 11. Fan-out updates and update costs

When a field is copied into many documents, a change to that field may require updating many documents. This is a fan-out write.

Examples:

| Source of change | Dependent documents | Impact |
| --- | ---: | --- |
| Renaming a brand | 500,000 products | Update `brandName` in the product index |
| Renaming a category | 2,000,000 products | Update `categoryName` |
| Changing an order's status | 50 order lines | Update line read models if filtering by status is required |

### 11.1. Batch updates

You should not send an individual update request for each document when the count is large. You can use the Bulk API, scroll/PIT to iterate through IDs and update in batches, or rebuild the read model index.

Batch workflow:

1. Identify dependent documents via a stable ID field.
2. Fetch a batch of IDs or documents.
3. Build updates from the canonical source.
4. Send a bulk update/index request.
5. Record success/failure counts.
6. Retry failed items according to policy.
7. Continue until finished.
8. Record a watermark/version to resume after an outage.

Batch size should be tuned based on payload size, latency, heap, and cluster load. Overly large batches can cause memory pressure and increase processing time.

### 11.2. Update by query

Elasticsearch supports `_update_by_query` to update multiple documents matching a condition. For example, updating a copied field:

~~~http
POST products/_update_by_query
{
  "query": {
    "term": {
      "brandId": "B-10"
    }
  },
  "script": {
    "source": "ctx._source.brandName = params.name",
    "params": {
      "name": "KeyWorks Labs"
    }
  }
}
~~~

`_update_by_query` is useful for a simple, uniform change across matching documents. However, it does not replace a canonical data source or a full synchronization pipeline. If a document must be reconstructed from multiple sources, an application-side projector is generally safer than patching a single field in `_source`.

Update by query can run for a long time, hit version conflicts, or be bounded by task/cancel/timeout limits. Monitor the task and have a plan to handle partial failures.

## 12. Reindexing and rebuilding read models

When changing document structure or denormalization rules, you may need to create a new index and rebuild the data.

~~~text
Canonical data source
       |
       v
 New projector version
       |
       v
 products-v2
       |
       v
 Data verification
       |
       v
 Switch products alias
~~~

A safe workflow:

1. Create a new index with updated mappings and settings.
2. Run backfill from the canonical source or a trustworthy read model.
3. Continue receiving change events during the backfill.
4. Catch up on events emitted after the watermark.
5. Verify document counts, required fields, and query results.
6. Switch the read alias to the new index.
7. Monitor errors and latency after cutover.
8. Keep the old index for an appropriate rollback window before deleting it.

You should not simply reindex from the old Elasticsearch index if the old read model was missing fields or contained stale data. When fixing denormalization rules, the canonical source should be the original data or an event log sufficient to reconstruct it.

## 13. CQRS and denormalized read models

A commonly used architecture is CQRS: the write model and read model are optimized for different goals.

- The write model protects business rules and transactional consistency.
- The read model is designed for fast queries and may contain duplicated data.
- Events or sync pipelines update the read model from the write model.

~~~text
Command
   |
   v
Write model
   |
   v
Transaction
   |
   v
Domain event
   |
   v
Projector
   |
   v
Elasticsearch read model
   |
   v
Search API
~~~

Spring Data Elasticsearch typically sits on the read model or search projection side. You do not need to force application domain entities to match Elasticsearch documents one-to-one.

### 13.1. Multiple read models for the same source

A single product event can update:

- Product search index: serves full-text search and filtering.
- Product suggestion index: serves autocomplete.
- Category summary index: serves category statistics.
- Inventory view: serves displaying the latest stock.

Each read model has its own schema and update cadence. This prevents a single document from bloating to satisfy every query.

### 13.2. Eventual consistency

After the write model commits, the read model may not be updated immediately. The application needs to decide how to handle this:

- Show a notice that data may take a few seconds to update.
- Read the latest state directly from the write service on critical transactional screens.
- Use versions to know whether the read model has caught up.
- Allow lookup by ID from the canonical source when read-after-write is required.

You should not claim Elasticsearch data is always immediately consistent if updates happen asynchronously.

## 14. When is a parent-child join field worth considering?

Elasticsearch has a `join` mapping type to represent parent-child relationships within the same index. This is an intentional exception to the denormalized model.

Parent-child can be useful when:

- One parent has a very large number of child documents.
- Children are updated independently and frequently.
- You want to avoid reindexing the entire parent whenever a child is added or edited.
- Queries genuinely need to select parents by children or children by parents.

For example, a product is the parent and reviews are children. Each review can be indexed/updated separately.

### 14.1. Join field mapping

Mapping JSON:

~~~json
{
  "mappings": {
    "properties": {
      "relation": {
        "type": "join",
        "relations": {
          "product": "review"
        }
      },
      "sku": {
        "type": "keyword"
      },
      "rating": {
        "type": "integer"
      },
      "content": {
        "type": "text"
      }
    }
  }
}
~~~

Parent document:

~~~json
{
  "sku": "KB-1042",
  "relation": "product"
}
~~~

Child document:

~~~json
{
  "rating": 5,
  "content": "Excellent keyboard",
  "relation": {
    "name": "review",
    "parent": "P-1042"
  }
}
~~~

### 14.2. Routing requirements

Parent and child must reside on the same shard. When indexing a child, the routing value must match the parent's routing value. If the parent uses its ID as default routing, the child must be sent with the parent's routing.

This is a critical constraint: being in the same index is not enough—they must be on the same shard. If routing does not match, parent-child queries may fail to find the relationship or indexing the child may fail depending on the operation.

### 14.3. has_child query

Find products that have at least one review with a rating of 4 or higher:

~~~json
{
  "query": {
    "has_child": {
      "type": "review",
      "query": {
        "range": {
          "rating": {
            "gte": 4
          }
        }
      },
      "score_mode": "max"
    }
  }
}
~~~

### 14.4. has_parent query

Find reviews belonging to the product with SKU `KB-1042`:

~~~json
{
  "query": {
    "has_parent": {
      "parent_type": "product",
      "query": {
        "term": {
          "sku": "KB-1042"
        }
      }
    }
  }
}
~~~

### 14.5. Parent-child costs

Parent-child avoids embedding all children inside the parent, but join queries are more expensive than direct field queries. Elasticsearch must perform relationship resolution based on global ordinals and intra-shard links.

Some points to keep in mind:

- Parent and child must be in the same index and shard.
- Children require proper routing based on the parent.
- Join queries can consume more CPU and heap than regular queries.
- Adding multiple levels of relationships increases model and query complexity.
- Do not use parent-child just to simulate every SQL foreign key.

If queries frequently need a few parent fields on the child, copying those fields into the child is usually simpler and faster.

### 14.6. Parent-child in Spring Data Elasticsearch

Spring Data Elasticsearch provides abstractions for join fields, including `JoinField` and `@JoinTypeRelations`/`@JoinTypeRelation` annotations in supported versions.

Conceptual example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelation;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelations;
import org.springframework.data.elasticsearch.core.join.JoinField;

@Document(indexName = "product-relations")
@JoinTypeRelations(
    relations = {
        @JoinTypeRelation(
            parent = "product",
            children = {"review"}
        )
    }
)
public class ProductRelationDocument {

    @Id
    private String id;

    private String sku;
    private Integer rating;
    private String content;

    private JoinField<String> relation;

    // Constructors, getters, and setters
}
~~~

A parent can use `new JoinField<>("product")`; a child uses the relation name and parent ID according to the constructor provided by your Spring Data version. You must set the child's routing to match the parent and ensure the write API actually passes that routing.

Join field APIs and routing configuration mechanisms may vary across Spring Data Elasticsearch versions. Check the Javadoc of your project's dependency before applying specific code. For many applications, a projector producing denormalized documents remains easier to operate than parent-child.

## 15. Comparing embed, copy fields, and parent-child

| Criterion | Embed object/nested | Copy fields into document | Parent-child |
| --- | --- | --- | --- |
| Reading data together | Very suitable | Suitable for copied fields | May require join queries |
| Updating child independently | May require updating parent | Update documents containing copies | Child can be updated independently |
| Large number of children | Unsuitable if unbounded | Suitable when children are separate documents | May be suitable |
| Finding parent by child | Nested query if `nested` | Query on a read model with the appropriate fields | `has_child` |
| Finding child by parent | Nested query/parent document | Copy parent ID into child | `has_parent` |
| Complexity | Low to medium | Requires synchronizing copies | Higher, requires routing |
| Query cost | Typically low when document model fits | Typically low since fields are in the same document | Join queries are more expensive |

A practical rule of thumb:

- Embed small, bounded child data that is usually read with the parent.
- Copy parent fields into child documents when children need to be filtered/searched independently.
- Use parent-child when children are numerous, have an independent update lifecycle, and the benefit of avoiding large parent updates outweighs join query costs.

## 16. Snapshot or current-state copy?

Not all duplicated data needs to be synchronized under the same policy.

| Field | Data type | When source changes |
| --- | --- | --- |
| Product name in an order line | Transaction snapshot | Keep unchanged |
| Paid unit price | Transaction snapshot | Keep unchanged |
| Brand name in product search | Current-state copy | Update |
| Category name in product search | Current-state copy | Update |
| Reviewer name in a review | Depends on privacy/history policy | May anonymize or update |

Before copying a field, decide whether it carries historical or current meaning. Otherwise, a sync job could corrupt historical records or a stale copy could skew search results.

## 17. Designing documents that aren't too large

Denormalization does not mean cramming all related data into a single document. Oversized documents increase read, write, network transfer, and segment merge costs.

Signs that data should be split:

- Child arrays grow without bound.
- Child elements are updated frequently and independently.
- Only certain screens need child elements.
- Separate pagination or aggregations are needed on child data.
- A single document is updated concurrently by multiple writers.
- Child data has a different lifecycle and retention policy than the parent.

### 17.1. Splitting out event history

You should not store the entire status history inside an order document if an order can accumulate many events.

Instead, the order document holds the current state:

~~~json
{
  "orderId": "ORD-2026-1001",
  "status": "SHIPPED",
  "updatedAt": "2026-03-12T09:00:00Z"
}
~~~

Each event is a separate document:

~~~json
{
  "eventId": "EVT-100",
  "orderId": "ORD-2026-1001",
  "orderStatus": "SHIPPED",
  "eventType": "OrderShipped",
  "occurredAt": "2026-03-12T09:00:00Z"
}
~~~

`orderStatus` or other parent fields can be copied into the event if history queries need fast filtering on them. If the event status is a snapshot at the time of occurrence, do not update it to match the current order status.

## 18. Handling concurrent updates and overwrites

With denormalized documents, multiple event sources may update the same document. If two projectors both write the entire entity, the later write can overwrite fields managed by the other projector.

For example:

- The product projector updates `name` and `price`.
- The inventory projector updates `available` and `stock`.
- The brand projector updates `brandName`.

If each projector constructs a full `ProductSearchDocument` from incomplete data and calls `save`, they can erase fields managed by the other projectors.

### 18.1. Partitioning field ownership

Clearly define which projector owns which fields. You can:

- Have a single projector build the entire read model from canonical sources.
- Have projectors update partial fields using update scripts or controlled partial updates.
- Use an aggregate event to produce a complete update.
- Split indexes by read model or bounded context if update groups are independent.

Do not call `save` with a partial entity if overwrite behavior could drop other fields.

### 18.2. Optimistic concurrency and versioning

Elasticsearch supports sequence numbers and primary terms to protect updates from unintended overwrites. Spring Data may expose corresponding versioning/concurrency mechanisms depending on the API.

For event-driven projectors, a business version in the event is often more useful than relying solely on arrival time. Consumers can compare the source version to discard stale events.

## 19. Building an index from multiple sources

A product read model may require product, brand, category, and inventory data. The projector needs to combine them.

~~~text
Product source ----+
                   |
Brand source ------+----> Product projector ---> products index
                   |
Category source ---+
                   |
Inventory source --+
~~~

There are two common strategies:

**Synchronous composition:** the projector reads the required sources and writes a complete document. This fits imports or updates that can run synchronously, though latency and dependency failures must be controlled.

**Event-driven projection:** each source change emits an event; the projector maintains the read model by updating the corresponding fields. This scales better for asynchronous pipelines but requires handling event ordering, retries, and rebuilds.

If one source is temporarily unavailable, you should not write a document with missing fields and accidentally wipe out previously good data. You can retry, preserve the current read model, or mark the projection state as incomplete.

## 20. Reconciliation: detecting drifted copies

Event-driven projections can drop events due to operational errors, bugs, or migrations. There must be a way to reconcile the read model with the canonical source.

Some techniques:

- Store the source version or `updatedAt` in the read model.
- Compare document counts by tenant/category.
- Sample documents and cross-check critical fields.
- Run rebuild jobs by partition or ID range.
- Track the last processed event.
- Route failed items to a dead-letter queue and have a replay process.

Reconciliation does not have to run continuously across the entire dataset if the cost is high. It can run on a schedule, by partition, or after a migration event.

## 21. When should you use multiple indexes?

Some data shares the same source but serves different queries. Splitting indexes can provide better-suited mappings and lifecycles:

| Index | Document model | Primary query |
| --- | --- | --- |
| `products` | Product + brand/category summary + variants | Searching products |
| `reviews` | Review + `productId`/`brandId`/`categoryId` | Searching and analyzing reviews |
| `orders` | Order + bounded line snapshots | Reading orders |
| `order-lines` | One document per line + order/product summary | Line-item reporting |
| `product-suggestions` | Input, weight, contexts | Autocomplete |

Splitting indexes increases synchronization work, but each index can independently optimize mappings, shards, refresh intervals, retention, and access permissions.

Do not create one index per relational table simply because the source data has many tables. Each index should represent a read model/query set with a clear justification.

## 22. Modeling decision workflow

When migrating a relational model to Elasticsearch, you can follow this sequence:

1. List critical read queries and required return fields.
2. Identify the aggregate or root entity for each screen/search.
3. Embed one-to-one objects when they are typically read together.
4. For arrays of objects, choose `object` or `nested` based on whether relationships between fields must be preserved.
5. Embed child arrays that are bounded and tied to the parent's lifecycle.
6. Split large or unbounded collections into separate documents.
7. Copy IDs and parent attributes needed for filtering/searching into child documents.
8. Distinguish historical snapshots from current-state copies.
9. Identify the canonical source and the mechanism to update copies.
10. Use events/outbox, batch updates, versions, and retries to manage eventual consistency.
11. Consider parent-child only when children are independent, numerous, and joins are genuinely required.
12. Check document sizes, nested object counts, latency, and fan-out costs.
13. Plan for rebuilds/reindexing and reconciliation when schemas or projection rules change.

## 23. Comprehensive example: modeling a catalog and reviews

Suppose a system needs to:

- Search products by name, brand, category, price, and variants.
- Search reviews by product, brand, and rating.
- Display a few recent reviews on the product page.
- Support reviews growing to millions of records.

A suitable model might include:

### Product search document

~~~json
{
  "id": "P-1042",
  "name": "Mechanical Keyboard",
  "brandId": "B-10",
  "brandName": "KeyWorks",
  "categoryId": "C-KEY",
  "categoryName": "Keyboards",
  "price": 129.5,
  "variants": [
    {
      "sku": "KB-1042-BLK",
      "color": "black",
      "price": 129.5
    }
  ],
  "reviewSummary": {
    "count": 1250,
    "averageRating": 4.7
  }
}
~~~

The product document embeds bounded variants, copies brand/category names for filtering, and keeps a review summary for fast display.

### Review document

~~~json
{
  "reviewId": "R-10001",
  "productId": "P-1042",
  "productName": "Mechanical Keyboard",
  "brandId": "B-10",
  "brandName": "KeyWorks",
  "rating": 5,
  "content": "Excellent keyboard",
  "createdAt": "2026-03-12T09:00:00Z"
}
~~~

Reviews are stored independently due to high volume and the need for separate pagination, search, and aggregations. Product/brand fields are copied for direct filtering.

### Update flows

- Product renamed: update the product index and review read models if `productName` must reflect the current name.
- Brand renamed: update denormalized fields on products and reviews via batches/events.
- New review: write the review document and update the product's `reviewSummary` via a projector.
- Review deleted: update count/average via recalculation or a controlled aggregation process.

If the name in a review must be a snapshot at write time, do not update `productName` when the product is renamed. Data policy determines which fields a projector updates.

## 24. Common mistakes

**Turning every SQL table into a separate index and expecting Elasticsearch to JOIN them automatically.** Query DSL does not provide general-purpose JOINs across indexes. Design read models with the required fields.

**Embedding every relationship into a single document.** Documents can become too large, hard to update, and impossible to paginate child elements efficiently. Only embed small, bounded data that is typically read with the parent.

**Using an object array when conditions must match on the same element.** Cross-object matching can occur. Use `nested` when field relationships within each object must be preserved.

**Using nested for every object.** `nested` carries indexing and query overhead. Only use it when query semantics require `nested`.

**Copying the entire parent object into the child.** Duplicated data becomes large and increases update costs. Copy only the fields needed for filtering, searching, or display.

**Not defining a canonical source.** When data drifts, you won't know which copy is correct. Every field needs a clear owner.

**Confusing snapshots with current-state data.** Updating historical copies can corrupt transaction records. Define semantics before synchronizing.

**Updating the DB and Elasticsearch in two unguaranteed operations.** Events can be lost. Use a transactional outbox or a durable sync mechanism.

**Non-idempotent consumers.** Retries can corrupt data or increment counters multiple times. Use event IDs, versions, and deterministic updates.

**Writing a full entity from incomplete data.** You can overwrite fields managed by another projector. Partition field ownership or use controlled partial updates.

**Choosing parent-child just to avoid copying a few fields.** Join queries are expensive and require routing. Copying small fields is usually simpler.

**Having no rebuild process.** When mappings or projection logic change, old read models may not be fixable with new incremental events alone. Prepare backfill and reindex procedures.

## 25. References

- [Elasticsearch - Data modeling](https://www.elastic.co/guide/en/elasticsearch/reference/current/data-modeling.html): document design choices and relationships.
- [Elasticsearch - Arrays](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/array): how Elasticsearch handles multi-valued fields.
- [Elasticsearch - Object field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/object): object mapping and relationship limitations in object arrays.
- [Elasticsearch - Nested field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/nested): nested documents, nested queries, and costs.
- [Elasticsearch - Joining queries](https://www.elastic.co/docs/reference/query-languages/query-dsl/joining-queries): `has_child`, `has_parent`, and `nested` queries.
- [Elasticsearch - Join field](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/parent-join): parent-child mapping, routing, and limitations.
- [Elasticsearch - Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk): writing multiple documents and updating in batches.
- [Elasticsearch - Update by query](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update-by-query): updating multiple documents by query.
- [Spring Data Elasticsearch - Object mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html): mapping entities and documents.
- [Spring Data Elasticsearch - Join types](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/misc.html): join field support and related annotations.

Annotation names, packages, and APIs may vary across Spring Data Elasticsearch versions. Consult your project dependency's Javadoc before implementing parent-child; the JSON mapping and Query DSL examples illustrate Elasticsearch-side semantics.
