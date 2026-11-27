# Designing Denormalized Models by Use Case

Elasticsearch is a document-oriented search engine. Therefore, an effective data model is usually designed from how the application searches and reads data, rather than copying a relational table structure as-is and expecting every query to perform well.

Denormalization is the deliberate practice of storing the same information across multiple documents or duplicating part of related data so a query can read results in fewer steps. For example, a product document can store the brand name and category name upfront so a catalog page does not have to look up multiple additional resources on every render.

Denormalization speeds up reads and simplifies queries, but it increases the responsibility for updates, synchronization, and controlling duplicated data. A good design must clearly define which read use case is being optimized, which data is the authoritative source, what information is copied, what latency is acceptable, and how to recover when a projection drifts.

## 1. Use-case-driven design mindset

### 1.1. Start from queries, not from tables

In relational databases, models are typically normalized to avoid data duplication and guarantee consistent updates. When reading, applications use JOINs to combine tables.

Elasticsearch stores JSON documents and optimizes for searching, filtering, sorting, aggregation, and returning matching documents. A query usually performs well when the fields needed for filtering or display are already inside the searched document.

For example, a catalog page needs to:

- Search products by keyword.
- Filter by category and brand.
- Filter by in-stock status.
- Sort by price or popularity score.
- Display product name, brand name, price, and image directly in results.

If data is stored across separate normalized structures, the application must combine product, brand, category, and inventory status. With Elasticsearch, you can design a catalog document containing copied fields so the query returns sufficient data in a single search.

### 1.2. One index does not have to represent one table

An index should represent a collection of documents serving one or more use cases that share:

- Query patterns.
- Mappings and data types.
- Data lifecycle.
- Access permissions.
- Freshness requirements.
- Scale and load characteristics.

A product can appear in multiple projections:

| Projection | Goal | Priority fields |
|---|---|---|
| Product catalog | Search and filter products | Name, description, brand, category, price, status |
| Product autocomplete | Suggestions while typing | Normalized name, aliases, keywords, popularity |
| Product analytics | Time-based aggregations | Grouping labels, category, brand, timestamp, metrics |
| Product detail | Display detail page | Full content and necessary related information |

Do not force a single document to serve every query if use cases differ significantly in required fields, freshness, or load.

### 1.3. Read models can differ from write models

An application can keep authoritative data in a relational database or owning service, and build a search projection in Elasticsearch.

This mindset is close to CQRS (Command Query Responsibility Segregation):

- The write model handles business rules and owns the authoritative data.
- The read model is designed to serve queries.
- Events or change streams propagate changes from the write model to the read model.
- The read model may lag behind the authoritative source by a controlled period of time.

Elasticsearch is usually suitable as a read model/search projection when the system needs flexible search. Do not treat a search index as the sole transactional data store if the business requires transactions or integrity constraints that Elasticsearch does not provide.

### 1.4. Typical architecture diagram

~~~mermaid
flowchart LR
    A[Order or Catalog Service] --> B[(Source of Truth)]
    B --> C[Outbox or Change Stream]
    C --> D[Projection Consumer]
    D --> E[Transform and Enrich]
    E --> F[(Elasticsearch Read Model)]
    G[Search API] --> F
    G --> H[Search Result DTO]
~~~

The write model owns business rules. The projection consumer transforms data into query-friendly documents. The Search API reads the projection and returns DTOs for the UI.

### 1.5. Document the contract of each use case

Before choosing a document structure, describe:

- Who reads the data?
- Which fields does the query need?
- Which fields are used for filtering, sorting, aggregation, or full-text search?
- Do results require a consistent snapshot, or is eventual consistency acceptable?
- How often does the data change per minute/hour?
- How many documents does a single source change affect?
- How large can a document grow?
- Are cross-queries across document groups needed?
- Is there sensitive data that must not be copied?

These answers determine whether to embed, duplicate fields, create a separate projection, or keep a reference.

## 2. Normalization and denormalization

### 2.1. Normalization reduces duplicate data

A normalized model typically separates entities:

~~~text
Product(id, name, brand_id, category_id)
Brand(id, name)
Category(id, name)
Inventory(product_id, available_quantity)
Price(product_id, amount, currency)
~~~

Each piece of information has one owner. Renaming a brand only requires updating a single Brand record.

This approach reduces duplication and fits relational write models. However, to return a catalog page, the application needs to combine multiple sources.

### 2.2. Denormalization optimizes the read path

A catalog document can contain related information:

~~~json
{
  "productId": "P1001",
  "name": "Wireless Keyboard",
  "brand": {
    "id": "B10",
    "name": "Northwind"
  },
  "category": {
    "id": "C20",
    "name": "Computer Accessories"
  },
  "price": {
    "amount": 49.9,
    "currency": "USD"
  },
  "availability": {
    "inStock": true,
    "quantity": 42
  }
}
~~~

The catalog page can filter by `brand.name`, `category.name`, `price.amount`, and `availability.inStock` without calling additional services just to retrieve those fields.

### 2.3. Trade-offs of duplicated data

| Aspect | Normalized model | Denormalized model |
|---|---|---|
| Data duplication | Minimal | Intentional |
| Queries across multiple entities | Require JOINs or multiple requests | Typically read one document |
| Updating shared fields | One place | May fan out to many documents |
| Write complexity | Usually centralized | Adds projection synchronization |
| Read latency | Can increase due to combining data | Usually lower for designed queries |
| Consistency | Easy to control in one transaction | Typically eventual consistency across projections |
| Use-case mapping | Less flexible | Flexible per read model |

Denormalization is not a goal in itself. Only copy data when read benefits or use-case isolation outweigh synchronization costs.

## 3. Deciding between embed, reference, or duplicate fields

### 3.1. Embed objects when data shares the lifecycle

Embedding an object is suitable when:

- The child object is small.
- It is usually read together with the parent object.
- Its lifecycle is tied to the parent object.
- It does not frequently need independent queries.
- The number of child objects is reasonably bounded.

Example of a snapshot shipping address inside an order:

~~~json
{
  "orderId": "O1001",
  "customerId": "C100",
  "shippingAddress": {
    "recipient": "Alex",
    "city": "Ho Chi Minh City",
    "district": "District 1",
    "postalCode": "700000"
  }
}
~~~

The address is snapshotted at order placement time. If the customer later updates their profile address, old orders still must preserve the address used for that transaction.

This is an example of denormalization with business meaning, not merely query optimization.

### 3.2. Use references when data is large or changes independently

If a related document is large, has an independent lifecycle, or updates frequently, store only the ID:

~~~json
{
  "orderId": "O1001",
  "customerId": "C100"
}
~~~

The application fetches the customer profile from the owning service when needed. This reduces copied data but introduces network calls and read-time coupling.

Another option is to copy a few stable/display fields and keep the ID for detail lookups:

~~~json
{
  "orderId": "O1001",
  "customer": {
    "id": "C100",
    "displayName": "Alex",
    "membershipTier": "Gold"
  }
}
~~~

### 3.3. Duplicate fields when queries need to filter or sort

If the catalog page filters by brand, copy `brandId` and `brandName` into the product document. If brand name is only displayed after the user opens the detail page, a reference may suffice.

Do not copy every field of `Brand` into every product. Select fields by query:

- `brandId`: filtering and linking.
- `brandName`: display, aggregation, or sorting if needed.
- `brandLogoUrl`: card display if required by the use case.
- Internal administrative fields: usually not needed in the search document.

### 3.4. Snapshots and live data have different meanings

Not all copied data should be updated when the source changes.

For example:

- Brand names in a catalog usually need to update when the brand is renamed.
- Shipping addresses in placed orders usually must remain a snapshot.
- Product names in historical invoices may need to preserve the name at the time of sale.
- Inventory status requires higher freshness than descriptive text.

Classify fields into snapshot, live projection, or derived value. This determines whether fan-out updates are needed.

## 4. Choosing object, nested, or separate document structures

### 4.1. Object fits ordinary child objects

Example entity mapping:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Object)
    private BrandSnapshot brand;
}

public class BrandSnapshot {

    @Field(type = FieldType.Keyword)
    private String id;

    @Field(type = FieldType.Text)
    private String name;
}
~~~

Object mapping works when each child field is accessed as a property of the same document. Object arrays by default can be flattened in a way that conditions on multiple fields no longer bind to the same element.

### 4.2. The problem with arrays of objects

Suppose a product has offers:

~~~json
{
  "offers": [
    { "seller": "A", "price": 100 },
    { "seller": "B", "price": 200 }
  ]
}
~~~

If `offers` is mapped as a regular `object`, Elasticsearch flattens fields into arrays of values. A query requiring `seller = A` and `price = 200` can match the document even though the two conditions come from different offers.

This is cross-object matching.

### 4.3. Use nested when you need to preserve relationships within each element

If conditions must match on the same offer, use `nested` mapping:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Nested)
    private List<Offer> offers;
}

public class Offer {

    @Field(type = FieldType.Keyword)
    private String seller;

    @Field(type = FieldType.Double)
    private Double price;
}
~~~

Nested query:

~~~json
{
  "query": {
    "nested": {
      "path": "offers",
      "query": {
        "bool": {
          "filter": [
            { "term": { "offers.seller": "A" } },
            { "range": { "offers.price": { "lte": 150 } } }
          ]
        }
      }
    }
  }
}
~~~

`nested` stores each element as a separate nested Lucene document and preserves the relationship between fields within an element. This increases indexing and query cost compared to regular objects.

Only use `nested` when query semantics truly require same-element binding. Do not choose `nested` simply because JSON contains an array of objects.

### 4.4. Create a separate document when child objects have independent queries and lifecycles

If offers are updated independently, exist in large quantities, or are searched as standalone entities, consider indexing offers separately:

~~~json
{
  "offerId": "OF100",
  "productId": "P1001",
  "sellerId": "S10",
  "sellerName": "Seller A",
  "price": 100,
  "currency": "USD"
}
~~~

Then an offer can be updated without rewriting a large product document. In return, queries needing product info may have to rely on duplicated fields or perform multiple steps at the application layer.

### 4.5. Parent-child is not the default solution

Elasticsearch supports `join` fields for parent-child relationships within the same index. Parents and children must be routed to the same shard.

Parent-child may fit when:

- One parent has very many children.
- Children are updated independently.
- Duplicating all parent data into children is undesirable or impractical.
- Queries need to join along this relationship.

Drawbacks include expensive join queries, routing requirements, and global ordinals management overhead. For most typical search use cases, denormalizing needed fields into the read document is simpler.

## 5. Designing documents by query

### 5.1. Catalog use case example

Suppose a catalog API supports:

- Full-text search by name and description.
- Filtering by brand, category, and in-stock status.
- Sorting by price and popularity.
- Displaying product cards.
- Opening detail pages by product ID.

A document can be designed as:

~~~json
{
  "id": "P1001",
  "name": "Wireless Keyboard",
  "description": "Compact wireless keyboard",
  "brandId": "B10",
  "brandName": "Northwind",
  "categoryId": "C20",
  "categoryName": "Computer Accessories",
  "priceAmount": 49.9,
  "currency": "USD",
  "inStock": true,
  "availableQuantity": 42,
  "popularityScore": 87,
  "thumbnailUrl": "https://cdn.example.test/p1001.jpg",
  "updatedAt": "2026-11-13T10:00:00Z"
}
~~~

This document holds enough fields for catalog cards and filters. It does not need to contain full price history, every warehouse, or complete brand details.

### 5.2. Choosing field types by query operation

| Field | Recommended type | Why |
|---|---|---|
| id, brandId, categoryId | keyword | Exact match and aggregation |
| name | text | Full-text search |
| name.keyword | keyword multi-field | Sort or aggregate by name |
| description | text | Full-text search |
| priceAmount | scaled_float or double | Range filter and sort |
| currency | keyword | Exact filter |
| inStock | boolean | Filter |
| availableQuantity | integer/long | Range and sort |
| popularityScore | integer/float | Sort or ranking |
| updatedAt | date | Range and sort |

The exact types depend on numeric precision, currency calculation, and query requirements. For monetary values, store amounts with explicit precision rules and always store the currency; do not sum amounts across different currencies in the same aggregation without conversion.

### 5.3. Use multi-fields when one value serves multiple query types

A product name may need both full-text search and exact sorting:

~~~java
@MultiField(
    mainField = @Field(type = FieldType.Text, analyzer = "standard"),
    otherFields = {
        @InnerField(suffix = "keyword", type = FieldType.Keyword)
    }
)
private String name;
~~~

Multi-fields allow the same value to be indexed in multiple ways. The `text` field is used for search; the `keyword` subfield is used for exact matching, sorting, or aggregation.

Do not create multi-fields for every string. Each subfield increases mapping and index size, so declare them only when queries need them.

### 5.4. Store derived values when they serve frequent queries

For example, `inStock` can be computed from `availableQuantity` greater than 0. If nearly every catalog query filters by in-stock status, storing a precomputed boolean simplifies queries.

However, if both `availableQuantity` and `inStock` are stored, you must define the update source so the two fields do not diverge. You can compute `inStock` in the projection consumer from `quantity` each time a document is built.

### 5.5. Denormalize labels for aggregations

If reports frequently group by category name, you can store `categoryName` alongside `categoryId`. Use the ID as the stable key and the name as the display label.

If the category name changes, the projection can be updated via events. If aggregations need historical analysis by the label at transaction time, store a snapshot instead of updating old names.

## 6. Spring Data Elasticsearch example for a read model

### 6.1. Create a separate entity for the search projection

You do not need to use the relational database entity as the Elasticsearch entity. Create a document class reflecting the search use case:

~~~java
@Document(indexName = "products-catalog-v1")
public class ProductCatalogDocument {

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

    @Field(type = FieldType.Double)
    private Double priceAmount;

    @Field(type = FieldType.Keyword)
    private String currency;

    @Field(type = FieldType.Boolean)
    private Boolean inStock;

    @Field(type = FieldType.Date)
    private Instant updatedAt;
}
~~~

This class is a read model. It can differ from the domain `Product` or JPA entity. The separation lets search mappings evolve for queries without forcing changes to the transactional model.

### 6.2. Repository for read use cases

~~~java
public interface ProductCatalogRepository
        extends ElasticsearchRepository<ProductCatalogDocument, String> {

    List<ProductCatalogDocument> findByBrandId(String brandId);

    List<ProductCatalogDocument> findByCategoryIdAndInStockTrue(
        String categoryId
    );
}
~~~

Derived queries fit simple conditions. For queries with multiple filters, nested clauses, aggregations, or ranking, use `ElasticsearchOperations` and the query builder for your Spring Data version.

### 6.3. Building a projection from source data

A mapper can transform source data into a document:

~~~java
public ProductCatalogDocument toCatalogDocument(
        Product product,
        Brand brand,
        Category category,
        Inventory inventory) {

    ProductCatalogDocument document =
        new ProductCatalogDocument();

    document.setId(product.getId());
    document.setName(product.getName());
    document.setBrandId(brand.getId());
    document.setBrandName(brand.getName());
    document.setCategoryId(category.getId());
    document.setCategoryName(category.getName());
    document.setPriceAmount(product.getPrice());
    document.setCurrency(product.getCurrency());
    document.setInStock(inventory.getAvailableQuantity() > 0);
    document.setUpdatedAt(Instant.now());

    return document;
}
~~~

This is an example of mapping at the projection layer. In production, avoid calling each related service per product if you can batch data or receive events already containing the needed snapshot. If the mapper uses `Instant.now()`, distinguish the projection build time from the source modification time.

### 6.4. Using ElasticsearchOperations when finer control is needed

Repositories fit CRUD and simple queries. For bulk indexing, index operations, update queries, or advanced projection operations, `ElasticsearchOperations` provides the right abstraction.

~~~java
@Service
public class ProductCatalogIndexer {

    private final ElasticsearchOperations operations;

    public ProductCatalogIndexer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public ProductCatalogDocument index(
            ProductCatalogDocument document) {
        return operations.save(document);
    }
}
~~~

When using `save`, a document with the same ID is written with index operation semantics. If you need to update a few fields without replacing the entire source, use the version-appropriate update API/`UpdateQuery` rather than assuming `save` always merges fields.

### 6.5. Separating source entities and projections

A service can have:

- `Product` as the domain/write model.
- `ProductEntity` as the JPA persistence model.
- `ProductCatalogDocument` as the Elasticsearch read model.
- `ProductSuggestionDocument` as the autocomplete model.

A single class does not need to represent all of them. Separating models prevents a search mapping change from impacting the transactional schema.

## 7. Updating denormalized data

### 7.1. The fan-out update challenge

Suppose a brand has 10,000 products and the brand name is copied into each product document. When the brand is renamed, the projection must update the affected documents.

This is a fan-out update:

~~~mermaid
flowchart TD
    A[Brand name changed] --> B[BrandUpdated event]
    B --> C[Find affected product IDs]
    C --> D[Build update batches]
    D --> E[Bulk update catalog documents]
    E --> F[Record failures and retry]
~~~

If only `brandId` is stored, no fan-out is needed on rename, but catalog queries must look up the brand on display. Which approach to choose depends on read frequency, rename frequency, and acceptable latency.

### 7.2. Synchronous updates in the same request

You can update the source and Elasticsearch directly within the same application service flow. This is easy to understand, but the two systems have no shared ACID transaction.

If the database commit succeeds while the Elasticsearch update fails, data becomes inconsistent. If Elasticsearch is updated first and the database rolls back, the search projection contains uncommitted data.

Only use synchronous dual writes when partial states are acceptable and handled. For critical systems, an outbox is usually safer.

### 7.3. Transactional outbox

An outbox writes business changes and events in the same database transaction. A publisher reads the outbox and sends events to a broker or projection worker.

~~~mermaid
flowchart TD
    A[Application command] --> B[(Database transaction)]
    B --> C[Update source rows]
    B --> D[Insert outbox event]
    D --> E[Outbox publisher]
    E --> F[Message broker]
    F --> G[Projection consumer]
    G --> H[Elasticsearch]
~~~

Outbox reduces the risk of the database committing while the event is lost. Consumers still require idempotency because messages may be redelivered.

### 7.4. CDC and change streams

Change Data Capture (CDC) can read database change logs and emit events for projections. CDC works well when you want to build read models from source data changes without adding event publishing to every service method.

However, row-level changes do not always contain all related data needed to build a document. The consumer may need to enrich from sources or maintain state to reconstruct the projection.

### 7.5. Choosing event payloads based on projection needs

There are two common patterns:

- Events contain only entity ID and version; the consumer re-reads the authoritative source to build the projection.
- Events contain a snapshot with sufficient fields; the consumer can update the projection without calling multiple services.

Snapshot events reduce lookups but increase payload size and versioning responsibilities. ID-only events reduce payload coupling but might read a newer state if an old event is processed late.

Always record the event version, aggregate ID, event ID, and source timestamp/sequence.

## 8. Guaranteeing ordering and idempotency

### 8.1. Events can arrive duplicated or out of order

Message brokers typically provide at-least-once delivery in many configurations. A consumer may reprocess a message after a crash or timeout.

If an older event arrives after a newer event, the projection can revert to an older state.

An ordering rule is required:

- Monotonically increasing aggregate version.
- Sequence number from the source.
- Controlled event timestamp.
- Partition key by aggregate to preserve in-partition order, if supported by the broker.

Untrusted client timestamps may not be sufficient to determine order.

### 8.2. Storing the projection version

A document can contain the source version:

~~~json
{
  "id": "P1001",
  "sourceVersion": 42,
  "name": "Wireless Keyboard",
  "brandName": "Northwind"
}
~~~

When receiving event version 41 after version 42, the consumer ignores the older event. Checking the version and writing the document must be performed using an appropriate atomic mechanism so two consumers do not pass the check simultaneously.

You can use Elasticsearch external versioning if the source version meets the required semantics, or use OCC/conditional updates to protect the projection.

### 8.3. Idempotency by event ID

If an event can be processed multiple times, use an event ID to deduplicate or design projection writes so the final result is identical when re-executed.

Indexing documents with a stable ID and a versioned snapshot payload is usually easier to make idempotent than scripts that increment counters or append to arrays.

Do not use an additive-only operation without deduplication if messages can be redelivered.

### 8.4. Fan-out updates require batching and per-item retries

A brand rename event can affect thousands of product documents. Do not send a single huge request or fire unbounded per-product requests.

Use:

- Stable batch IDs.
- Size-bounded bulk requests.
- Bounded concurrency.
- Per-failed-item retries.
- Dead-letter queues for permanent failures.
- Checkpoints or progress markers to resume after a crash.

Bulk HTTP 200 does not guarantee every item succeeded; you must inspect `errors` and individual item responses.

### 8.5. Handling partial failures

If 9,900 out of 10,000 documents updated, do not blindly rerun the entire batch. Record failed items and classify them:

- 409: conflict/version.
- 404: document or index missing.
- 429: overload, back off.
- 400: mapping/payload.
- 401/403: credentials/privileges.

Only retry recoverable errors and ensure the operation is idempotent.

## 9. Denormalization for frequently changing data

### 9.1. Rapidly changing fields can cause excessive fan-out

If inventory changes continuously and a product appears in multiple projections, each change can generate many writes.

Consider:

- Does the exact quantity need to appear in search results?
- Can only `inStock` be stored with acceptable freshness?
- Can the latest quantity be fetched from the inventory service when the user opens the detail page?
- Can an inventory index be split out or a separate projection used?
- Can multiple events be coalesced into a single update?

Do not copy high-churn fields into every document if queries do not truly need them.

### 9.2. Use coarse states or buckets instead of every detail

If the catalog only needs to know whether an item is in stock or out of stock, an `inStock` boolean may suffice. If filtering by stock tier is needed, buckets can be used:

- `out_of_stock`
- `low_stock`
- `available`

Buckets reduce update frequency when quantity changes without changing tiers.

Only use buckets if the business accepts losing granularity. When placing an order, the inventory service must still confirm the exact quantity.

### 9.3. Price and currency data

Prices often vary by market, time, and customer segment. Before denormalizing prices, clarify:

- Standard price or customer-segment price?
- Is currency uniform?
- Do prices have effective periods?
- Do queries sort by current price or historical price?
- Are taxes/discounts computed in the projection?

An ambiguous `price` field easily leads to wrong results. Use clear names like `listPriceAmount`, `salePriceAmount`, `currency`, `priceEffectiveAt`.

### 9.4. Temporal data and snapshots

For historical transaction data, store snapshots of key labels at transaction time. If only the ID is stored and the current name is looked up, historical reports can change when category or customer names change.

For example, an order line can retain:

~~~json
{
  "productId": "P1001",
  "productNameAtPurchase": "Wireless Keyboard",
  "unitPriceAtPurchase": 49.9,
  "currency": "USD",
  "quantity": 2
}
~~~

This is an intentional snapshot. These fields should not be updated when the catalog changes.

## 10. Limiting document size and complexity

### 10.1. Do not embed unbounded lists

If a product document contains all reviews, price history, every inventory movement, and every offer over many years, the document will grow continually and every update becomes expensive.

Split into a separate index when a collection:

- Can grow without bound.
- Is queried independently.
- Has a different update rate from the parent.
- Has different access permissions.
- Has a different retention policy.
- Does not need to be read in full alongside the parent.

### 10.2. Avoid overly wide documents and mapping explosion

Do not generate dynamic field names per user key or uncontrolled attribute. Every new field mapping has a cost and can cause field counts to grow huge.

If you need to store dynamic multi-key metadata, consider the `flattened` field type (if supported by your Elasticsearch/Spring Data version) or store an opaque structure suited to your queries. `flattened` fits flexible key-value metadata but has query limitations compared to per-field mappings.

### 10.3. Nested documents have their own cost

Each nested object is indexed as a nested Lucene document. A parent containing thousands of nested entries can inflate Lucene document counts and update costs.

If an array is large and updated independently, a separate child index is usually better.

### 10.4. Choose _source and stored fields based on need

`_source` is normally kept to return documents, reindex, and process updates. Do not disable `_source` just to save disk space if the application needs updates, reindexing, or full document retrieval.

Only optimize source/stored/doc values after measuring and identifying which queries need them.

## 11. Multi-tenancy and security when duplicating data

### 11.1. Do not copy sensitive fields if queries do not need them

When building projections, include only fields serving search/read use cases. Do not copy email addresses, phone numbers, street addresses, or sensitive data into every document if the UI does not need them.

Copied data widens the blast radius if an index or API key is accessed without authorization.

### 11.2. Keep the tenant ID in the document

If an index holds multiple tenants, documents usually need a tenant ID field for filtering and permission checks. However, client-submitted query filters are not the sole security layer.

Use service-level authorization and appropriate Elasticsearch security. If strong isolation is required, consider separate indices, separate API keys, or document-level security depending on license/capabilities.

### 11.3. Copied fields must respect tenant boundaries

A projection consumer may join/enrich data from multiple sources. You must verify tenant ownership when combining records. Do not pull a brand/category from another tenant just because IDs match or a lookup lacked a tenant filter.

### 11.4. Data deletion and privacy rights

When source data is deleted for privacy compliance, identify every projection containing copies of those fields and delete or mask them accordingly.

A field duplicated into catalog, autocomplete, analytics, and caches does not vanish automatically when the source record is deleted.

Maintain a list of dependent projections and a verifiable deletion propagation workflow.

## 12. Rebuilding and versioning read models

### 12.1. Projections must be rebuildable

If Elasticsearch is a read model, you should be able to rebuild it from the authoritative source or a replayable event log.

Rebuilding is useful when:

- Mappings change.
- Projection logic is fixed.
- Denormalized fields drift.
- Analyzers change.
- A new field needs backfilling.
- An index is corrupted or data is accidentally deleted.

If it cannot be rebuilt, the projection effectively becomes the sole data store even when the architecture did not intend it.

### 12.2. Use a new index version for major mapping changes

For example:

- `products-catalog-v1`
- `products-catalog-v2`

Create a new index with the new mapping, backfill data, catch up on new events, and switch the alias once verified.

~~~mermaid
flowchart TD
    A[Source of truth] --> B[Build products-catalog-v2]
    A --> C[Continue event stream]
    C --> B
    B --> D[Validate counts and queries]
    D --> E[Switch read alias]
    E --> F[Retire v1 after rollback window]
~~~

This avoids incompatible mapping changes on an existing index and provides a clear rollback path.

### 12.3. Aliases decouple logical names from physical names

The application can query the `products-catalog` alias while the alias points to a versioned index.

Aliases let you switch the read target after a rebuild without changing every client. For write aliases, define the write index and corresponding permissions.

### 12.4. Backfill must coordinate with new events

If backfilling starts while the source continues to change, ensure events are neither lost nor overwritten out of order.

Several strategies:

- Record a source checkpoint, backfill up to the checkpoint, then replay events after the checkpoint.
- Run controlled dual-writes during the transition period.
- Use source versions to discard older events.
- Rebuild from a consistent snapshot and then catch up on the change stream.

Do not simply scan the entire source and switch the alias immediately afterward if data could have changed during the scan.

### 12.5. Validate projections before switching aliases

Compare:

- Document counts by tenant/category.
- Missing or duplicate IDs.
- A representative set of queries.
- Key aggregations.
- Mappings and analyzers.
- Projection freshness.
- Indexing errors and dead-letter backlog.

Switch the alias once checks meet the defined criteria.

## 13. Deletes, soft deletes, and tombstones

### 13.1. Deletes must propagate to every projection

If a product is deleted at the source, consumers must delete the corresponding documents from catalog and autocomplete. If only the source is deleted, search projections can still return stale results.

You can emit a `ProductDeleted` event with ID, tenant, and version for every projection to handle.

### 13.2. Tombstones prevent old events from resurrecting data

A late-arriving update event can upsert an already deleted document. Tombstones or deletion versions tell the consumer at which version an entity was deleted so it can discard older events.

If using soft deletes, documents can store `deleted=true` and search queries always filter `deleted=false`. Verify that every query path and aggregation applies this condition.

### 13.3. Physical deletion and privacy requirements

Soft delete is insufficient for deleting sensitive data if the content remains in `_source`. Data must be deleted or masked according to retention/privacy policies, while also addressing snapshots, backups, and old indices.

## 14. Observing projection quality

### 14.1. Freshness

Track the gap between when the source changed and when the projection was updated. You can store:

- `sourceUpdatedAt`
- `projectedAt`
- `sourceVersion`
- `eventId`

Do not use `projectedAt` alone to claim data is the newest if events can arrive out of order.

### 14.2. Synchronization and dead-letter queues

Monitor:

- Event lag.
- Consumer lag.
- Successful/failed projection updates.
- Bulk item failures by error type.
- Retry counts.
- Dead-letter queue size.
- Rebuild/backfill duration.
- Out-of-sync document counts.

If the error queue grows while the search API still returns 200, the read model may be stale even though the system looks healthy.

### 14.3. Sample-based consistency checks

You can run reconciliation jobs:

1. Sample IDs from the authoritative source.
2. Read the corresponding documents in Elasticsearch.
3. Compare fields defined to be identical.
4. Categorize mismatches.
5. Rebuild or repair documents.
6. Record metrics and audits.

Do not compare every field if the projection intentionally transforms or snapshots values. Clearly define which fields require equality and which have different semantics.

### 14.4. Distinguishing stale projections from wrong queries

When search results are missing or outdated, check:

- Was the event emitted?
- Did the consumer process it?
- Was the document indexed with the right ID?
- Has refresh made the document searchable yet?
- Does the query filter by the right tenant/status?
- Does the alias point to the right index version?

Do not conclude the Query DSL is wrong when the cause is an un-updated projection.

## 15. Testing denormalized models

### 15.1. Testing projection mappers

Verify source data is transformed into documents correctly:

- Stable IDs.
- Fields duplicated accurately.
- Derived fields computed accurately.
- Snapshot fields retain values at business event time.
- Tenant ID is never lost.
- Null/missing values handled consistently.

### 15.2. Integration tests for queries on real Elasticsearch

Use Testcontainers or a compatible Elasticsearch environment to verify:

- Object/nested mappings.
- Nested queries do not cross-match.
- Keyword filters and aggregations.
- Multi-field search/sort.
- Numeric and date range queries.
- Aliases and index versions.
- Upsert/update semantics.

### 15.3. Testing duplicate and out-of-order events

Send the same event twice and verify the projection does not change erroneously. Send an old-version event after a new event and verify the document does not roll back to an older state.

### 15.4. Testing fan-out updates

Create multiple products sharing a brand. Rename the brand and verify all related projections are updated in batches.

Simulate some failed items to verify retry/dead-letter handling without re-updating already succeeded items.

### 15.5. Testing deletion propagation

Delete an entity at the source and verify:

- The catalog document is no longer returned.
- The autocomplete projection is updated.
- Analytics indices follow the proper retention/snapshot semantics.
- Old events do not recreate the deleted document.

### 15.6. Performance testing with realistic queries

Measure query latency, indexing throughput, document size, and fan-out cost with near-production-scale data. A small model may run well yet struggle when one brand has millions of products or one product has very many nested offers.

## 16. Common design mistakes

| Symptom | Cause | Solution |
|---|---|---|
| Queries require multiple service calls | Document lacks fields serving the use case | Denormalize needed read fields |
| Brand name in results is stale | Copied field without update propagation | Event fan-out or explicit snapshot semantics |
| Updating one child rewrites huge document | Embedded collection changes independently | Split child index or redesign projection |
| Nested queries are slow | Too many nested entries or unnecessary nested | Use regular object or separate index |
| Nested queries return wrong results | Regular object array causes cross-object matching | Use nested when conditions must match same element |
| Mapping explosion | Uncontrolled dynamic fields | Whitelist fields or use flattened appropriately |
| Document size grows continuously | Embedded unbounded history/lists | Split indices by lifecycle and queries |
| Many documents stale after events | Failing consumer, lost events, or bad version order | Outbox/CDC, retries, checkpoints, and reconciliation |
| Old event overwrites new data | Source version not checked | Version ordering or conditional writes |
| Retries increment counters multiple times | Non-idempotent updates | Event ID and deduplication |
| Rebuilds produce drifted data | Backfill not coordinated with new events | Checkpoints and versioned replay |
| Search returns deleted data | Deletes do not reach every projection | Deletion events and tombstones |
| Cross-tenant data leaks | Projection enrichment lacks tenant boundary | Check tenant ownership and authorization |
| Projections store unnecessary sensitive data | Copying entire source entity | Project only fields required by use case |
| Excessive write amplification | One changing field causes huge fan-out | Split projections, bucketize, or live lookup |

## 17. Use-case-driven design process

When designing a document model for a Spring Data Elasticsearch application:

1. List real queries and fields needed for filtering, sorting, aggregating, searching, or display.
2. Identify the authoritative data source and owning service for each field.
3. Classify fields into snapshots, live projections, or derived values.
4. Choose embedded objects, nested structures, duplicated fields, references, or separate documents.
5. Evaluate document size, cardinality, and update frequency.
6. Create separate read models per use case if mappings or freshness differ significantly.
7. Select field types and analyzers according to queries.
8. Design events/outbox/CDC to update projections.
9. Ensure event ordering, idempotency, and source versioning.
10. Handle fan-out with batches, concurrency limits, and item-level retries.
11. Design delete propagation, tombstones, and privacy cleanup.
12. Version indices and use aliases for mapping migrations.
13. Measure query latency, indexing throughput, projection lag, and document size.
14. Test queries, mappings, duplicate events, out-of-order events, and rebuilds against real Elasticsearch.
15. Run periodic reconciliation to detect projection drift.

## 18. Key takeaways

- Design Elasticsearch around queries and use cases, not by copying relational table models as-is.
- Denormalization lets a single query read multiple related fields, but adds synchronization costs for duplicated data.
- Separate the write model/source of truth from the read model/search projection when needed.
- Embed objects when data is small and shares the parent's lifecycle; use references when data is large or changes independently.
- Duplicate fields only when queries need them for filtering, sorting, aggregation, or display.
- Object arrays can cause cross-object matching; use `nested` when conditions must match the same element.
- Split into separate documents when children have independent queries, volume, updates, or lifecycles.
- Parent-child carries join and routing overhead; it is not the default choice.
- Use stable IDs, source versions, idempotency, and event ordering to protect projections.
- Fan-out updates require batching, concurrency limits, and per-item retries.
- Outbox or CDC reduces the risk of losing changes when updating both the source and Elasticsearch.
- Historical snapshots and live projections have different semantics; do not accidentally update snapshots.
- Version indices, backfill, reconcile, and then switch aliases on major mapping changes.
- Deletes must propagate to every projection; tombstones prevent old events from resurrecting data.
- Copy only necessary fields and maintain tenant/security boundaries.
- Monitor freshness, consumer lag, bulk errors, dead-letter queues, and consistency drift.

A good denormalized model quickly answers the queries the application actually needs, while maintaining clear data ownership and synchronization processes. When decisions to embed, duplicate, or separate documents are grounded in queries, lifecycles, and field churn rates, Spring Data Elasticsearch can serve read workloads efficiently while preserving rebuildability and consistency control.
