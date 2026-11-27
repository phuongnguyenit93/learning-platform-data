# Field Projection, Sort, Limit, and Skip

## 1. The Problem: Querying the Right Data, Right Order, and Right Size

A product listing API might need to return **20 active products in the BOOK category**, sorted newest to oldest, displaying only SKU, name, and price. Reading the entire collection and then filtering, sorting, and slicing in Java wastes network bandwidth and memory while putting extra load on MongoDB.

In **SPRING_DATA_MONGODB**, Spring Data MongoDB provides **Query** and **Criteria** to express queries, where:

- **Criteria** describes which documents match the conditions.
- **Query.fields()** describes which fields will be returned (*field projection*).
- **Query.with(Sort)** describes the sort order.
- **Query.limit(int)** caps the number of returned documents.
- **Query.skip(long)** skips an initial number of documents in the sorted set.

These pieces complement repository and MongoTemplate operations when building queries, aggregations, indexes, and synchronous/reactive data-access paths. They must be used together intentionally rather than just producing results that look right on a small dataset.

After this lesson, you will be able to:

1. Build filters with Criteria and Query on a Spring Data MongoDB entity.
2. Include fields, exclude fields, and handle the **_id** exception.
3. Sort by one or multiple keys, especially adding a stable tie-breaker key for pagination.
4. Distinguish **limit**, **skip**, **Pageable**, **Slice**, and total counts.
5. Avoid deep-pagination pitfalls, non-deterministic ordering, and accidentally saving partially loaded entities.
6. Understand how projection and sort affect indexes, aggregation, and performance.
7. Test a query against real MongoDB and verify filter, order, size, and BSON shape.

## 2. Sample Data and Java Entity

Suppose the **products** collection stores documents:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  sku: "BOOK-001",
  name: "Learning Spring Data MongoDB",
  category: "BOOK",
  active: true,
  priceMinor: NumberLong("159000"),
  stock: NumberInt(8),
  supplier: {
    code: "SUP-01",
    internalNote: "Internal business terms"
  },
  createdAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  sku: "BOOK-002",
  name: "Hands-on MongoDB",
  category: "BOOK",
  active: true,
  priceMinor: NumberLong("129000"),
  stock: NumberInt(5),
  supplier: {
    code: "SUP-02",
    internalNote: "Do not publish"
  },
  createdAt: ISODate("2025-06-02T09:00:00Z")
}
~~~

In Java:

~~~java
package com.example.catalog;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public record ProductDocument(
    @Id ObjectId id,
    String sku,
    String name,
    String category,
    boolean active,
    long priceMinor,
    int stock,
    Supplier supplier,
    Instant createdAt
) {
    public record Supplier(String code, String internalNote) {}
}
~~~

**_id** is the BSON field name, while **id** is the Java property mapped by `@Id`. `priceMinor` uses `long` because it stores the smallest currency unit; `createdAt` uses `Instant` to map to BSON Date. The collection name is taken from **@Document(collection = "products")** when using MongoTemplate with `ProductDocument`.

## 3. Dividing Responsibilities Between Query and Criteria

Example finding active products in category BOOK:

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("category").is("BOOK")
        .and("active").is(true)
);
~~~

This query is equivalent to the `mongosh` filter:

~~~javascript
db.products.find({
  category: "BOOK",
  active: true
});
~~~

**Criteria determines which documents match**, without specifying returned fields, ordering, or count. Those options are attached to Query:

~~~java
import org.springframework.data.domain.Sort;

query.fields()
    .include("sku")
    .include("name")
    .include("priceMinor");

query.with(Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
));
query.skip(0);
query.limit(20);
~~~

~~~mermaid
flowchart TD
    A["Criteria: category=BOOK, active=true"] --> B["Query"]
    B --> C["fields: sku, name, priceMinor, _id by default"]
    C --> D["sort: createdAt DESC, _id DESC"]
    D --> E["skip: 0, limit: 20"]
    E --> F["MongoDB find"]
    F --> G["Mapped BSON results"]
~~~

When writing a query, answer four independent questions: **what to filter, which fields to keep, in what order, and how many records to take**. Separating them prevents bugs when API requirements evolve.

## 4. Field Projection with include

In MongoDB, projection describes the shape of returned documents. A projection can **select specific fields** (*inclusion*):

~~~javascript
db.products.find(
  { category: "BOOK", active: true },
  { sku: 1, name: 1, priceMinor: 1 }
);
~~~

Illustrative output:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  sku: "BOOK-001",
  name: "Learning Spring Data MongoDB",
  priceMinor: NumberLong("159000")
}
~~~

**_id still appears even without _id: 1** because MongoDB returns `_id` by default unless you explicitly exclude it.

In MongoTemplate:

~~~java
Query query = Query.query(
    Criteria.where("category").is("BOOK")
);
query.fields()
    .include("sku")
    .include("name")
    .include("priceMinor");
~~~

The **include** method can accept multiple fields in compatible API versions; writing separate calls as above is clear and easy to cross-check against results.

### 4.1. Return Only Necessary Fields

For a public listing, selecting only `sku`, `name`, and `priceMinor` omits unnecessary fields such as `supplier.internalNote`, `stock`, and `createdAt`. This acts as a **whitelist of permitted output fields**, helping avoid accidentally exposing new fields added in the future.

Still, if the application needs the ID to open a product detail page, keep `_id`. If the ID is not needed, you can exclude it using the special rule in the next section.

### 4.2. Include Every Field Needed by the DTO

If the API also needs the creation timestamp, you must include `createdAt`:

~~~java
query.fields().include("createdAt");
~~~

Do not declare a field in the DTO yet forget to load it from MongoDB expecting the mapper to fill in the missing part. Query projection decides what BSON the framework receives to construct results.

## 5. Exclude and the _id Exception

Exclusion projection specifies which fields you do not want returned:

~~~javascript
db.products.find(
  { active: true },
  { "supplier.internalNote": 0 }
);
~~~

The result still contains `sku`, `name`, `category`, `priceMinor`, `stock`, `supplier.code`, `createdAt`, and `_id`. If a new field is added to documents later, that new field will also appear because exclusion **is not a whitelist**.

In MongoTemplate:

~~~java
Query query = Query.query(Criteria.where("active").is(true));
query.fields()
    .exclude("supplier.internalNote");
~~~

### 5.1. Do Not Arbitrarily Mix include and exclude

In standard `find` projections, MongoDB does not allow simultaneously including field A and excluding another field B, **except for _id**.

| Projection | Valid? | Explanation |
| --- | --- | --- |
| { name: 1, priceMinor: 1 } | Yes | Inclusion |
| { stock: 0, supplier: 0 } | Yes | Exclusion |
| { name: 1, _id: 0 } | Yes | Inclusion, _id exception |
| { stock: 0, _id: 0 } | Yes | Exclusion, _id exception |
| { name: 1, stock: 0 } | No | Mixing both modes outside _id |
| { name: 1, "supplier.internalNote": 0 } | No | Mixing both modes outside _id |

Therefore, if the goal is only `name` and `priceMinor`:

~~~java
query.fields()
    .include("name")
    .include("priceMinor")
    .exclude("_id");
~~~

This combination is **valid** because `_id` is the allowed exception.

**Do not write:**

~~~java
// Invalid: mixing include/exclude on regular fields.
query.fields()
    .include("name")
    .exclude("supplier.internalNote");
~~~

Instead of excluding `internalNote`, simply include `name` along with other approved fields. If you do not need the ID, add **exclude("_id")**.

### 5.2. When Should You Exclude _id?

A report printing only a list of names can use:

~~~javascript
db.products.find(
  { active: true },
  { name: 1, _id: 0 }
);
~~~

Conversely, a screen with a "View details" button usually needs the ID. Decide based on the API contract rather than excluding `_id` mechanically. The `_id` exception also matters for **covered queries**: if an index does not include `_id`, returning `_id` by default forces MongoDB to fetch the root document.

## 6. Projection for Embedded Documents

Product has a `supplier` object. If you only need `supplier.code`:

~~~java
Query query = new Query();
query.fields()
    .include("supplier.code")
    .exclude("_id");
~~~

The resulting BSON will have the shape:

~~~javascript
{
  supplier: {
    code: "SUP-01"
  }
}
~~~

**Dot notation** selects a field inside the embedded object rather than flattening `supplier.code` into a top-level field.

### 6.1. Mapping with @Field

If an entity has a `supplierCode` property stored under a different BSON name:

~~~java
import org.springframework.data.mongodb.core.mapping.Field;

@Field("supplier_code")
private String supplierCode;
~~~

When the query is mapped via an entity type, Spring Data translates the Java property into the corresponding BSON field name. In `mongosh` or raw MongoDB Java Driver calls, you must use the real BSON name. For custom converters or complex nested paths, test the exact final BSON projection.

### 6.2. Array Projection Is Not Element Filtering

Suppose a product has:

~~~javascript
{
  variants: [
    { color: "RED", stock: 0 },
    { color: "BLUE", stock: 5 }
  ]
}
~~~

Projection:

~~~javascript
{ "variants.color": 1, _id: 0 }
~~~

returns **the colors of both elements**, without automatically filtering for only in-stock variants. If you want to keep only elements matching a condition, use an appropriate projection operator like **$elemMatch** in simple cases or aggregation **$filter** for more complex array transformations.

## 7. Why Should You Never Load a Partially Projected Entity and Save It?

For example, `ProductDocument` is defined as a record with several properties where `priceMinor` and `stock` are primitives. If a query returns only `name`, the framework can run into materialization issues, assign default values to missing fields, or produce an object lacking required data, depending on converters and domain types.

Avoid doing this:

~~~java
Query query = new Query();
query.fields().include("name");

List<ProductDocument> partial =
    mongoTemplate.find(query, ProductDocument.class);

// Do not save a partial element back as if it were a full entity.
~~~

If an application saves a partially loaded entity, an inappropriate replace/update can wipe out unloaded fields. This is a **data integrity bug**, not merely a performance issue.

To return a product card, prefer a **dedicated DTO/projection**:

~~~java
public record ProductCard(
    String id,
    String sku,
    String name,
    long priceMinor
) {}
~~~

A transparent approach is fetching projection results as **Document** and mapping to a DTO. The example in section 13 demonstrates this clearly. With repository APIs, you can use interface projections or DTOs with matching constructors. Do not assume an arbitrary class can always be instantiated successfully from results missing required properties.

## 8. Sort: Single Field and Multiple Fields

MongoDB sort syntax:

~~~javascript
db.products.find(
  { active: true },
  { sku: 1, name: 1 }
).sort({
  createdAt: -1
});
~~~

Value **1** in sort means ascending, **-1** means descending. They differ from 1/0 used in projection.

Spring Data MongoDB:

~~~java
import org.springframework.data.domain.Sort;

Query query = Query.query(Criteria.where("active").is(true));

query.with(
    Sort.by(Sort.Order.desc("createdAt"))
);
~~~

To sort by category ascending, then price descending:

~~~java
query.with(Sort.by(
    Sort.Order.asc("category"),
    Sort.Order.desc("priceMinor")
));
~~~

MongoDB sorts by **data fields**, not by the order in which elements arrive in Java. Queries needing sorting should let MongoDB execute the sort directly so it can leverage indexes and result limits.

### 8.1. Sort Can Use a Field Omitted from Projection

For example, returning only `name` and `priceMinor` while sorting by `createdAt`:

~~~java
Query query = Query.query(Criteria.where("active").is(true));
query.fields()
    .include("name")
    .include("priceMinor")
    .exclude("_id");

query.with(Sort.by(Sort.Order.desc("createdAt")));
~~~

**`createdAt` does not have to be returned** even though it is used for sorting. MongoDB can sort by it before applying projection. However, for cursor-based pagination keyed on `createdAt`, the API needs a way to retain or retrieve that cursor value.

## 9. Stable Sorting: Always Think About a Tie-Breaker Key

If two products share the same `createdAt`, sorting solely by `createdAt` does not establish a deterministic order between them. During pagination, this can cause records to shift positions across pages.

A common solution is appending **_id**:

~~~java
Sort stableSort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

Query query = Query.query(Criteria.where("active").is(true))
    .with(stableSort);
~~~

In entity mapping, Java property **id** maps to BSON **_id**. Equivalent in `mongosh`:

~~~javascript
db.products.find({ active: true })
  .sort({ createdAt: -1, _id: -1 });
~~~

### 9.1. Sorting Does Not Mean an Index Exists

A valid sort can still be slow if MongoDB has to sort many documents in memory outside an index. Evaluate indexes against filter, sort, and selectivity. A query filtering **category = BOOK**, **active = true**, sorted **createdAt DESC, _id DESC** can consider a compound index matching those exact fields.

### 9.2. String Sorting, Collation, and Missing Data

Sorting on Strings is affected by **collation**, BSON data types, and server comparison rules. If an API requires language-specific or case-insensitive ordering, configure an appropriate collation and check whether an index shares that collation. Sorting by `name` does not automatically follow Vietnamese alphabetical order in every setup.

Missing or null fields also follow specific BSON sort rules. With heterogeneous data, never infer sort order from inspecting just a few sample documents.

## 10. Limit: Capping the Number of Documents

**limit(n)** caps the maximum number of results returned by a query:

~~~java
Query query = Query.query(Criteria.where("active").is(true));
query.with(Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
));
query.limit(20);
~~~

Equivalent:

~~~javascript
db.products.find({ active: true })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
~~~

If only 7 documents match the filter, the result contains at most 7—it does not pad up to 20. **limit does not mean the server counted all matching documents**.

### 10.1. Always Bound Client-Requested Sizes

If a client can pass `size=1,000,000`, passing it straight to **query.limit(size)** easily triggers huge queries. The service layer should enforce a max size and validate:

~~~java
if (size < 1 || size > 100) {
    throw new IllegalArgumentException(
        "Page size must be between 1 and 100"
    );
}

query.limit(size);
~~~

In Spring Data `Query`, **limit(0)** typically represents no limit per MongoDB convention; therefore do not use 0 to mean "return zero elements" in pagination APIs. Validate inputs and return an empty page intentionally if business rules demand it, rather than expecting `limit(0)` to be safe.

### 10.2. Do Not Use take() Instead of MongoDB limit()

Do not load all results into Java and slice them:

~~~java
// Avoid on large datasets: may have already loaded vast numbers of documents.
List<ProductDocument> all = mongoTemplate.find(
    Query.query(Criteria.where("active").is(true)),
    ProductDocument.class
);

List<ProductDocument> firstTwenty =
    all.subList(0, Math.min(20, all.size()));
~~~

Limits must be pushed down to the server query. A similar caution applies to `ReactiveMongoTemplate`: set **Query.limit** before producing the `Flux` instead of reading an unbounded `Flux` and collecting everything.

## 11. Skip: How Many Documents to Skip?

**skip(n)** bypasses the first `n` documents in the result set after applying the filter and sort order, and then takes up to `limit` records.

~~~java
Query query = Query.query(
    Criteria.where("category").is("BOOK")
        .and("active").is(true)
);

query.with(Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
));

query.skip(20);
query.limit(20);
~~~

The example above retrieves **the second page** when each page holds 20 records and pages are 0-indexed. Equivalent:

~~~javascript
db.products.find({
  category: "BOOK",
  active: true
})
.sort({ createdAt: -1, _id: -1 })
.skip(20)
.limit(20);
~~~

### 11.1. Offset Formula

With `pageNumber` starting at 0:

\[
\text{offset} = \text{pageNumber} \times \text{pageSize}
\]

| Page | Size | Skip | Limit |
| --- | --- | --- | --- |
| 0 | 20 | 0 | 20 |
| 1 | 20 | 20 | 20 |
| 2 | 20 | 40 | 20 |
| 5 | 10 | 50 | 10 |

**Do not mistake page=1 for the first page** in Spring Data's `PageRequest`, because page indexes start at 0. A UI showing "Page 1" may need to convert that to `page=0` before calling the service.

### 11.2. Always Sort Before Using Skip

In the query API, the order in which you call `skip`/`limit`/`with` methods should not be thought of as Java execution stages; they configure fields of the query sent to the server. What matters is having **an explicit sort**.

Without a sort, `skip` relies on an unguaranteed result order. An index change, different query plan, or concurrent writes can cause the same offset to yield inconsistent results.

## 12. Pageable and Query.with(Pageable)

Instead of manually computing `skip` and `limit`, you can use **Pageable**:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
    2,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

Query query = Query.query(
    Criteria.where("category").is("BOOK")
        .and("active").is(true)
);
query.with(pageable);
~~~

`Pageable` here carries **offset=40**, **limit=20**, and sorting by `createdAt`, `id`. `Query.with(Pageable)` applies those components to `Query`.

**Do not arbitrarily combine** `Query.with(pageable)` with separate `skip`/`limit` calls unless there is a clear reason. Later calls can overwrite earlier configuration, returning a different page than requested by the client.

### 12.1. Avoid Double-Applying Offset

An easy mistake:

~~~java
Query query = Query.query(Criteria.where("active").is(true));
query.skip(pageable.getOffset());
query.with(pageable);
~~~

Do not write this thinking the two calls accumulate offsets. Simply use **query.with(pageable)** or configure **skip, limit, and sort** consistently in one place.

### 12.2. Which Approach Should You Pick?

| Scenario | Suitable Choice |
| --- | --- |
| Paginated API with page, size, sort | Pageable + Query.with(pageable) |
| Report taking only the top N newest products | Query.with(sort) + Query.limit(N) |
| Cursor/seek pagination | Cursor filter in Query + sort + limit |
| Dynamic queries with many filters | Dynamic Criteria + Query + appropriate pagination method |

Keep a single source of truth for offset/limit on every code path to simplify code review and testing.

## 13. Complete Service Example: Projection + Sort + Skip + Limit

To return a lean DTO, the following example queries **raw BSON Documents**, then explicitly maps to a public type:

~~~java
package com.example.catalog;

import java.util.List;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public record ProductCard(
    String id,
    String sku,
    String name,
    long priceMinor
) {}

public class ProductCatalogService {

    private final MongoTemplate mongoTemplate;

    public ProductCatalogService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<ProductCard> listActiveBooks(int page, int size) {
        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException("Invalid page/size");
        }

        long offset = Math.multiplyExact((long) page, size);

        Query query = Query.query(
            Criteria.where("category").is("BOOK")
                .and("active").is(true)
        );
        query.fields()
            .include("_id")
            .include("sku")
            .include("name")
            .include("priceMinor");

        query.with(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("_id")
        ));
        query.skip(offset);
        query.limit(size);

        List<Document> docs =
            mongoTemplate.find(query, Document.class, "products");

        return docs.stream()
            .map(this::toCard)
            .toList();
    }

    private ProductCard toCard(Document doc) {
        ObjectId id = doc.getObjectId("_id");
        return new ProductCard(
            id.toHexString(),
            doc.getString("sku"),
            doc.getString("name"),
            doc.getLong("priceMinor")
        );
    }
}
~~~

The example uses **Document.class** and an explicit collection name so BSON projection is straightforward to inspect. It assumes `priceMinor` is stored as BSON Int64 and `_id` is an ObjectId. If legacy data uses Int32/String for price or a different `_id` type, normalize the data and adjust mapping rather than assuming any type automatically converts to `Long`/`ObjectId`.

Another option is using entity metadata with an appropriate DTO/interface projection so you do not have to handle `Document` manually. Even then, fetching only needed fields and **never saving partial entities** remain crucial principles.

### 13.1. Query Sorting by an Unreturned Field

The service above sorts by `createdAt`, yet projection omits `createdAt`. This works cleanly for offset pagination: MongoDB uses `createdAt` during sorting and then returns only the selected fields.

If migrating to keyset pagination, the cursor needs `createdAt` and `_id` from the last record. In that case, retain `createdAt` in the returned data or use a dedicated cursor carrier rather than omitting the pagination anchor field.

### 13.2. Service Not Returning Total Count

`listActiveBooks` returns a **`List<ProductCard>`** for a single page. The list size does not equal the total number of matching products. If the UI needs **`totalElements`**, execute a separate count query with the exact same filter; section 15 explains how.

## 14. Getting hasNext Without Counting: limit(size + 1)

Suppose the client needs a "Load more" button without needing total page counts. Instead of counting, you can fetch **one extra record**:

1. Client requests `page=2, size=20`.
2. Compute `skip=40` as usual.
3. Set `limit=21`.
4. If the query returns 21 records, `hasNext=true`; expose only the first 20 records.

~~~java
int page = 2;
int size = 20;
long offset = Math.multiplyExact((long) page, size);

Query query = Query.query(
    Criteria.where("category").is("BOOK")
        .and("active").is(true)
);
query.with(Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
));
query.skip(offset);
query.limit(size + 1);

List<ProductDocument> fetched =
    mongoTemplate.find(query, ProductDocument.class);

boolean hasNext = fetched.size() > size;
List<ProductDocument> content = fetched.subList(
    0, Math.min(size, fetched.size())
);
~~~

Here no partial field projection is used, so `MongoTemplate` materializes full `ProductDocument` instances for this `Slice`-style example. In a real API, you can pair this with a DTO projection as in section 13.

### 14.1. Mistake When Changing Size in PageRequest

**Wrong:** using `PageRequest.of(2, 21)` to read one extra element, because the offset then becomes **42**.

**Right:** keep the offset at **page * size = 40**, and only raise limit to **size+1 = 21**.

If using `Query.with(PageRequest.of(2, 20, sort))`, you can apply **query.limit(21)** afterward, preserving the offset calculated from 20. Verify exact behavior in the Spring Data version your project uses.

### 14.2. hasNext Is Not Total

Finding one extra record only proves at least one record follows the current page at query time. You cannot infer the exact total count or remaining page count. With concurrent inserts/deletes in the collection, subsequent queries can still observe different counts.

## 15. Separate Count: Never Use a Query with skip/limit to Count Totals

When the UI needs "Showing page 3/25" or "482 products found", run a matching filter count:

~~~java
Query countQuery = Query.query(
    Criteria.where("category").is("BOOK")
        .and("active").is(true)
);

long total = mongoTemplate.count(
    countQuery, ProductDocument.class
);
~~~

The count query above has no projection, sort, skip, or limit. Thus `total` represents the **entire set of documents matching the filter** in the database state observed by the query.

**Never directly reuse a Query that already has skip/limit to compute totals**, as count semantics can be affected by pagination options depending on the Spring Data version. Creating **a filter-only Query** is simple and unambiguous.

### 15.1. Page and Slice Differ in Metadata

| Return Type | Has Page Content? | Has hasNext? | Has Total? |
| --- | --- | --- | --- |
| `List<T>` | Yes | Not automatic | No |
| `Slice<T>` | Yes | Yes | No |
| `Page<T>` | Yes | Yes | Yes |

To construct a `Page`:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;

Page<ProductDocument> result = new PageImpl<>(
    content,
    pageable,
    total
);
~~~

This example assumes `content` was loaded for the right page, `pageable` matches the page configuration, and `total` came from a filter-only count. When totals are unnecessary, `Slice`/`hasNext` saves an extra query.

### 15.2. Count and Page Data Can Drift in Time

When two separate queries run, a writer can insert or delete documents in between. Therefore `content` and `total` do not necessarily reflect the exact same snapshot. If business rules demand strict consistency, configure appropriate read concerns, transactions, or snapshots for your MongoDB deployment; combining results in Java does not create a snapshot automatically.

## 16. Deep Skip and Keyset Pagination

Offset pagination is convenient because clients can jump directly to page N. Yet deep skips can be expensive:

~~~javascript
db.products.find({ category: "BOOK", active: true })
  .sort({ createdAt: -1, _id: -1 })
  .skip(100000)
  .limit(20);
~~~

Even though only 20 documents are returned, MongoDB may still walk through many index keys before reaching the skip offset. Having an index does not mean deep `skip` is cheap.

### 16.1. Keyset/Seek by the Last Record

If clients only need "next page", you can use a cursor consisting of:

- **createdAt** of the previous page's last record;
- **_id** of that record.

With sort `createdAt DESC, _id DESC`, subsequent records satisfy:

\[
\text{createdAt} < T
\quad \text{or} \quad
(\text{createdAt} = T \land \_id < I)
\]

In MongoDB:

~~~javascript
db.products.find({
  category: "BOOK",
  active: true,
  $or: [
    { createdAt: { $lt: ISODate("2025-06-02T09:00:00Z") } },
    {
      createdAt: ISODate("2025-06-02T09:00:00Z"),
      _id: { $lt: ObjectId("507f1f77bcf86cd799439012") }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(21);
~~~

In Query/Criteria:

~~~java
import java.time.Instant;
import org.bson.types.ObjectId;

Instant cursorCreatedAt = Instant.parse(
    "2025-06-02T09:00:00Z"
);
ObjectId cursorId = new ObjectId(
    "507f1f77bcf86cd799439012"
);

Criteria afterCursor = new Criteria().orOperator(
    Criteria.where("createdAt").lt(cursorCreatedAt),
    new Criteria().andOperator(
        Criteria.where("createdAt").is(cursorCreatedAt),
        Criteria.where("id").lt(cursorId)
    )
);

Criteria filter = new Criteria().andOperator(
    Criteria.where("category").is("BOOK"),
    Criteria.where("active").is(true),
    afterCursor
);

Query query = Query.query(filter)
    .with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    ))
    .limit(21);
~~~

When running **mongoTemplate.find(query, ProductDocument.class)**, Spring Data maps property `id` to `_id`. On the initial request without a cursor, the query needs only filter/sort/limit; subsequent requests add the cursor condition and never use `skip`.

**The cursor condition must match the sort direction.** If you change sort to ASC while still using `$lt`, items will be skipped or returned erroneously. In real applications, validate and protect cursor tokens, and bind tenant/filter constraints from the authenticated context.

### 16.2. Keyset Is Not an Immutable Snapshot

Keyset reduces duplicate/skip drift caused by new inserts ahead of the cursor, yet does not stop documents behind the cursor from being modified or deleted. For workflows requiring a fully consistent point-in-time export, design explicit snapshot or reconciliation mechanisms rather than relying purely on keyset.

## 17. Indexes for Filters, Sorts, and Projections

A frequent query:

~~~javascript
db.products.find(
  { category: "BOOK", active: true },
  { sku: 1, name: 1, priceMinor: 1, _id: 0 }
)
.sort({ createdAt: -1 });
~~~

You can evaluate an index covering equality filters, sort keys, and fields needed for projection:

~~~javascript
db.products.createIndex({
  category: 1,
  active: 1,
  createdAt: -1,
  sku: 1,
  name: 1,
  priceMinor: 1
});
~~~

This is **one candidate** for this query pattern, not a mandatory index design. If you have many diverse query paths, overly wide indexes raise write cost and index memory footprint. Measure against real data and optimize for critical workloads.

### 17.1. Projection Can Enable Covered Queries

If filters, sorts, and all returned fields can be satisfied directly from the index, MongoDB can avoid fetching root documents. This is known as a **covered query**.

If the index above **omits _id**, a default projection returning `_id` prevents the query from being covered. When an API does not need the ID, adding **_id: 0** makes the query eligible to be covered by the index.

### 17.2. Using explain("executionStats")

~~~javascript
db.products.find(
  { category: "BOOK", active: true },
  { sku: 1, name: 1, priceMinor: 1, _id: 0 }
)
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");
~~~

| Metric / Plan | Meaning |
| --- | --- |
| `winningPlan` | Which execution path MongoDB chose |
| `totalKeysExamined` | Number of index keys traversed |
| `totalDocsExamined` | Number of root documents read |
| `nReturned` | Number of results returned |
| `FETCH` stage | Whether documents had to be fetched from the collection |
| `SORT` stage | Whether an extra in-memory sort occurred outside the index |
| `executionTimeMillis` | Observed execution latency |

In a typical covered query, `totalDocsExamined` can be 0. Still, a small `nReturned` does not prove a query is efficient: deep `skip` can cause `totalKeysExamined` to be enormous.

## 18. ReactiveMongoTemplate Uses the Same Query

`Query`, `Criteria`, `fields`, `sort`, `skip`, and `limit` also work with **ReactiveMongoTemplate**:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;

public Flux<ProductDocument> recentBooks(
        ReactiveMongoTemplate template, int size) {

    if (size < 1 || size > 100) {
        return Flux.error(new IllegalArgumentException("Invalid size"));
    }

    Query query = Query.query(
        Criteria.where("category").is("BOOK")
            .and("active").is(true)
    );

    query.with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    ));
    query.limit(size);

    return template.find(query, ProductDocument.class);
}
~~~

The method returns a **Flux** containing at most `size` `ProductDocument` items. It does not execute the query until subscribed to. Never call **block()** inside WebFlux to convert a `Flux` into a synchronous `List`.

### 18.1. Using Projection in Reactive Queries

~~~java
import org.bson.Document;

Query query = Query.query(Criteria.where("active").is(true));
query.fields()
    .include("sku")
    .include("name")
    .exclude("_id");
query.with(Sort.by(Sort.Order.asc("name")));
query.limit(50);

Flux<Document> cards =
    reactiveTemplate.find(query, Document.class, "products");
~~~

This example assumes `reactiveTemplate` is injected and targets the `products` collection. If you need a DTO, map emitted `Document` items into the desired result type. Reactor backpressure does not replace setting `limit` in MongoDB.

### 18.2. collectList Only After Limiting

~~~java
Mono<List<Document>> batch = cards.collectList();
~~~

Here `batch` is already bounded to 50 elements, so collecting into a `List` has controlled memory cost. Never run **findAll().collectList()** on a large collection just to take the first few records.

## 19. Query vs. Aggregation and Repositories

`MongoTemplate` `Query` fits many dynamic `find` operations. A repository can express filters and sorts through method names, `@Query`, or `Pageable`. When a query needs:

- **`$group`** to aggregate quantities;
- **`$lookup`** to join collections;
- **`$project`** with computed expressions;
- **`$filter`** to filter array elements;
- multi-stage structural transformations;

then aggregation is a better choice than a simple `find` projection.

An example pipeline:

~~~javascript
db.products.aggregate([
  { $match: { category: "BOOK", active: true } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $skip: 20 },
  { $limit: 20 },
  {
    $project: {
      _id: 0,
      sku: 1,
      displayName: "$name",
      priceMinor: 1
    }
  }
]);
~~~

**Note that stage order in aggregation affects results**: `$sort` goes before `$skip`/`$limit` to define pages; putting `$limit` before `$skip` often returns wrong or empty results. With `find`, the `sort`/`skip`/`limit` methods configure a single query; do not infer from Java call order that `find` behaves like arbitrary pipeline stages.

When building multi-step aggregation pipelines in Java, use Spring Data MongoDB's aggregation APIs or `@Aggregation` according to your project version's capabilities.

## 20. Testing Query, Criteria, Projection, and Paging

Mocking `MongoTemplate` alone does not prove MongoDB executes filter/sort/skip/limit as expected. Write integration tests against an **isolated test** MongoDB instance, such as Testcontainers or a dedicated managed test instance.

### 20.1. Things to Verify

| Scenario | Expectation |
| --- | --- |
| `category=BOOK, active=true` | Does not return products of other categories or inactive ones |
| `limit=2` | Returns at most 2 documents |
| `skip=2, limit=2` | Fetches the third and fourth items under the same sort |
| Two documents with identical `createdAt` | Secondary sort `_id` produces deterministic ordering |
| Include `sku`, `name` | Does not return other regular fields; `_id` still appears |
| Include `sku`, exclude `_id` | Does not return `_id` |
| Include `name` and exclude `stock` | Projection is rejected |
| Exclude `supplier.internalNote` | `internalNote` is absent from BSON |
| Count with filter-only query | Returns total matching filter, unaffected by page limits |
| Page beyond end of data | Returns an empty list |
| Partial field projection | Partial entities are never saved back |
| Index and sort | Measure `explain` under realistic workloads |

### 20.2. Integration Test with MongoTemplate

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class ProductQueryPagingTest {

    @Autowired
    private MongoTemplate template;

    @Test
    void projectionSortSkipAndLimitWorkTogether() {
        String prefix = "TEST-" + UUID.randomUUID() + "-";
        Instant time = Instant.parse("2025-06-01T09:00:00Z");
        List<ObjectId> insertedIds = new ArrayList<>();

        try {
            for (int i = 0; i < 5; i++) {
                ProductDocument saved = template.insert(
                    new ProductDocument(
                        null,
                        prefix + i,
                        "Product " + i,
                        "BOOK",
                        true,
                        (i + 1) * 10_000L,
                        i + 1,
                        new ProductDocument.Supplier("S", "PRIVATE"),
                        time.plusSeconds(i)
                    )
                );
                insertedIds.add(saved.id());
            }

            Query query = Query.query(
                Criteria.where("sku").regex(
                    "^" + java.util.regex.Pattern.quote(prefix)
                )
            );
            query.fields()
                .include("sku")
                .include("name")
                .exclude("_id");
            query.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("_id")
            ));
            query.skip(2);
            query.limit(2);

            List<Document> page = template.find(
                query, Document.class, "products"
            );

            assertThat(page).hasSize(2);
            assertThat(page.get(0).getString("sku"))
                .isEqualTo(prefix + 2);
            assertThat(page.get(1).getString("sku"))
                .isEqualTo(prefix + 1);
            assertThat(page.get(0).containsKey("_id")).isFalse();
            assertThat(page.get(0).containsKey("supplier")).isFalse();
        } finally {
            for (ObjectId id : insertedIds) {
                template.remove(
                    Query.query(Criteria.where("_id").is(id)),
                    ProductDocument.class
                );
            }
        }
    }
}
~~~

This test inserts five documents with increasing timestamps. Sorting `createdAt DESC` orders them 4, 3, 2, 1, 0; skipping two and limiting to two returns **2, 1**. Inspecting raw BSON `Document` confirms **neither `_id` nor `supplier`** is present in the output.

The example requires a configured test MongoDB instance and a Spring Boot version supporting `@DataMongoTest`. Never run tests on production. A thorough test suite should also seed documents with other categories and `inactive` status to verify filters, as well as two documents sharing the same `createdAt`.

### 20.3. Testing Count Separated from skip/limit

~~~java
Query dataQuery = Query.query(
    Criteria.where("category").is("BOOK")
        .and("active").is(true)
);
dataQuery.with(Sort.by(Sort.Order.desc("createdAt")));
dataQuery.skip(20).limit(20);

Query countQuery = Query.query(
    Criteria.where("category").is("BOOK")
        .and("active").is(true)
);
long total = template.count(countQuery, ProductDocument.class);
~~~

Do not rely on shared test data to assert an exact `total` when other tests insert concurrently. Create an isolated dataset or filter by a test run ID / tenant.

## 21. Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Included only `name` yet `_id` still appears | MongoDB returns `_id` by default | Add `exclude("_id")` when unneeded |
| Projection rejected by server | Mixed include/exclude outside `_id` | Use one mode plus the `_id` exception |
| DTO fields become null/default | Missing fields for constructor/properties | Include all needed fields or adjust projection type |
| `save` erases data | Saved an entity loaded with missing fields | Use targeted updates or load the full entity |
| Pages 1 and 2 have duplicate items | Unstable sort or concurrent mutations | Sort with tie-breaker `_id`, consider keyset |
| Wrong starting page | Confused 0-based vs 1-based page numbers | Normalize `pageNumber` at API boundary |
| `limit` does not cap as expected | Passed 0 or unvalidated input | Enforce `1 <= size <= max` |
| Very deep pages are slow | Skip must scan through many entries | Index properly, consider keyset |
| Count is smaller than expected total | Count reused paged query or mismatched filter | Build a filter-only `countQuery` |
| Query misses products | Wrong `category`/`active` or BSON type | Compare filter against real data |
| Sort ignores language rules | No collation configured | Configure matching collation and index |
| API leaks internal fields | Exclusion did not block new fields | Use inclusion whitelist and DTOs |
| Query slow despite projecting few fields | Filter/sort/index mismatch | Run `explain`, check keys/docs examined |
| Reactive code blocks | `block()` or unbounded `collectList` | Push `limit` down to MongoDB, keep `Flux`/`Mono` |

Diagnostic workflow:

1. Verify the actual collection and BSON documents.
2. Check that `Criteria` has accurate conditions and data types.
3. Check whether `fields()` uses inclusion or exclusion, and whether `_id` is handled.
4. Check `Sort` and the deterministic tie-breaker key.
5. Verify `skip`, `limit`, and `PageRequest` use consistent page sizes.
6. If counting, use the same filter without accidentally carrying pagination options.
7. Use `mongosh` and `explain` to separate logic bugs from performance bottlenecks.
8. Add regression tests for missing fields, concurrent updates, and deep pagination.

## 22. Practice Exercises

### Exercise 1: Selecting Fields and Dropping _id

Find active products, returning only `sku` and `name`, without IDs.

**Suggested solution:**

~~~java
Query query = Query.query(Criteria.where("active").is(true));
query.fields()
    .include("sku")
    .include("name")
    .exclude("_id");
~~~

### Exercise 2: Fixing an Invalid Projection

A developer wrote:

~~~java
query.fields()
    .include("name")
    .exclude("supplier.internalNote");
~~~

**Question:** Why is this wrong?

**Answer:** It mixes inclusion and exclusion for two regular fields. If only `name` is needed, use `include("name")` and optionally `exclude("_id")`. `internalNote` is automatically omitted because it is not included.

### Exercise 3: Computing Skip

A client requests the fourth page using 1-based UI numbering, `size=25`. What should the Spring Data `pageNumber` be? How much `skip`?

**Answer:** `pageNumber=3`, `skip=75`, `limit=25`.

### Exercise 4: Stable Sorting

Two products have identical `createdAt` values. How should you sort so pages have a deterministic order?

**Answer:** Sort by `createdAt DESC, id DESC` (mapped to `_id`). If data mutates between requests, offset paging can still shift; consider keyset.

### Exercise 5: hasNext Without Count

`Page=2`, `size=20`. You want to know whether a next page exists without running a count query. How many records do you fetch? What `skip`?

**Answer:** `skip=40`, `limit=21`; expose only the first 20 records. If the query returns 21 records, `hasNext=true`.

### Exercise 6: Separate Count

The data query has `category=BOOK, active=true, sort createdAt DESC, skip=100, limit=20`. What query should you use to count total?

**Answer:** Create a new `Query` containing only `Criteria` `category=BOOK` and `active=true`; do not include sort, skip, or limit for the full-set total.

### Exercise 7: Indexes and Projection

Filter `category`/`active`, sort `createdAt DESC`, project `sku`/`name`/`priceMinor` without needing `_id`. Propose how to determine whether it can be a covered query.

**Hint:** evaluate an index containing the filter, sort, and projected fields, exclude `_id` via `_id:0` if the index lacks IDs, run `explain("executionStats")`, and check for `FETCH`/`totalDocsExamined`. Do not claim a query is covered merely because an index exists.

### Exercise 8: Deep Pagination

An API serving pages at `skip=500,000` is very slow. Should you simply reduce the number of projected fields to fix it completely?

**Answer:** No. Projection shrinks payload transfer, yet the server still has to traverse the huge offset. Review indexes/filters/sorts and switch to keyset/seek if the use case is sequential browsing.

### Exercise 9: Reactive

A reactive service calls `findAll().collectList()` and slices pages in memory. How should it be refactored?

**Answer:** Build a `Query` with `Criteria`, sort, and `skip`/`limit` directly in MongoDB, then call `ReactiveMongoTemplate.find(...)` returning `Flux`. Only call `collectList` once the stream size is bounded.

## 23. Principles to Remember

1. **Criteria filters documents; Query controls projection, sort, skip, and limit.**
2. **`fields().include`** returns selected fields; **`fields().exclude`** omits specified fields.
3. **Never mix inclusion/exclusion outside `_id`**. `_id` is returned by default and can be excluded separately.
4. **Stable sorting needs a tie-breaker key** such as `id`/`_id`, especially during pagination.
5. **`limit` caps returned records**, not counting totals; **`skip` bypasses** leading positions in the sorted order.
6. **`Pageable`** uses 0-based page indexes; maintain one source of truth for skip/limit to avoid errors.
7. **Reading `size+1` for `Slice`** detects `hasNext` without counting; totals require a separate count query.
8. **Full-set count must use a filter-only query**, never carelessly reusing a paginated query.
9. **Deep skip has cost**; keyset/seek is a strong choice for "load more" on large datasets.
10. **Projection and indexes can combine for covered queries**, though you must verify with `explain` on real workloads.
11. **Never save back partially projected entities**; use dedicated DTOs and targeted conditional updates.
12. **Reactive and aggregation have their own patterns**, while still requiring proper sorting, limits, and authorization.

Understanding and properly combining **field projection, sort, limit, and skip** helps **SPRING_DATA_MONGODB** services build clean `MongoTemplate` queries, return lean DTOs, deliver reliable pagination, and optimize performance for real-world needs.
