# Using Filters, Projections, Sorts, and Updates for CRUD in the MongoDB Java Driver

In Java, MongoDB offers several ways to express BSON queries and updates. Rather than concatenating JSON strings or manually assembling raw `Document` objects for every operator, the MongoDB Java Sync Driver provides **builder classes**: **Filters** to select data, **Projections** to limit returned fields, **Sorts** to define ordering, and **Updates** to describe server-side mutations.

These four builder families pair naturally with `MongoCollection` CRUD APIs. They make code cleaner, easier to test, and less prone to manual syntax mistakes. However, builders do not automatically guarantee business correctness: you still must enforce tenant authorization, data types, indexes, concurrency guards, and write-result handling.

~~~text
                       MongoCollection<Document>
                                |
             +------------------+------------------+
             |                  |                  |
           CREATE              READ           UPDATE/DELETE
             |                  |                  |
         insertOne        find(Filters)        updateOne(Filters, Updates)
         insertMany        projection           updateMany(Filters, Updates)
                           (Projections)        findOneAndUpdate
                           sort(Sorts)          replaceOne
                           skip/limit           deleteOne(Filters)
                                               deleteMany(Filters)
~~~

This lesson belongs to the **Java Driver** chapter of the **Database Engine Document MongoDB** module and focuses on CRUD operations with the **MongoDB Java Sync Driver**. Examples use a dedicated lab database without touching any production environment.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Connect to MongoDB using `MongoClient` and `MongoCollection`.
2. Understand **`Bson`** and why builders can be passed across many driver APIs.
3. Use `Filters` for equality, ranges, boolean logic, value sets, arrays, nested fields, and null/missing checks.
4. Use `Projections.include`/`exclude`/`fields` to return only required fields.
5. Use `Sorts.ascending`/`descending`/`orderBy` for deterministic ordering and pagination.
6. Use `Updates.set`/`inc`/`unset`/`combine` and array operators for server-side updates.
7. Execute `insertOne`, `find`, `updateOne`, `updateMany`, `replaceOne`, `deleteOne`, and `findOneAndUpdate`.
8. Understand `matchedCount`/`modifiedCount`, upserts, and preventing lost updates.
9. Design tenant-scoped CRUD, indexes, error handling, and tests.
10. Distinguish single-document atomic updates from multi-document modifications.

**Version scope:** Examples follow the modern MongoDB Java Sync Driver. Some overloads, operators, and server features require compatible versions. Choose dependencies aligned with your actual driver and server documentation rather than assuming all deployments share the same version.

## 2. Environment Setup

You need a compatible JDK, an accessible MongoDB deployment, the **`org.mongodb:mongodb-driver-sync`** dependency, and a URI supplied via the `MONGODB_URI` environment variable.

Example Maven dependency:

~~~xml
<dependency>
    <groupId>org.mongodb</groupId>
    <artifactId>mongodb-driver-sync</artifactId>
    <version>CHOOSE_COMPATIBLE_VERSION</version>
</dependency>
~~~

`CHOOSE_COMPATIBLE_VERSION` is a placeholder, not a buildable version. Use a release verified for compatibility and managed consistently in your project.

Common imports:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.FindIterable;

import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import com.mongodb.client.model.Updates;
import com.mongodb.client.model.UpdateOptions;

import org.bson.Document;
import org.bson.conversions.Bson;
~~~

### 2.1. Minimal Connection

~~~java
String uri = System.getenv("MONGODB_URI");

if (uri == null || uri.isBlank()) {
    throw new IllegalArgumentException(
        "Missing MONGODB_URI environment variable"
    );
}

try (MongoClient client = MongoClients.create(uri)) {
    MongoDatabase db = client.getDatabase(
        "java_driver_crud_lab"
    );
    MongoCollection<Document> products =
        db.getCollection("products");

    System.out.println(products.countDocuments());
}
~~~

### 2.2. MongoClient Lifecycle

In web services, reuse `MongoClient` and let the framework/container manage its lifecycle. Never create and close a new client per HTTP request; the driver handles connection pooling and server discovery internally.

### 2.3. Protecting Secrets

Never log a full MongoDB URI if it contains a username/password. Use a secret manager, TLS, and least-privilege credentials.

## 3. Sample Dataset Used Throughout

This lesson uses three collections: **products**, **orders**, and **customers**. Examples are independent and updates will modify lab state; if you need the initial dataset again, re-seed on an authorized test database.

`mongosh` seed script on an empty lab database:

~~~javascript
use java_driver_crud_lab

db.products.insertMany([
  {
    _id: "p-001",
    tenantId: "tenant-a",
    sku: "BOOK-001",
    name: "MongoDB Basics Book",
    category: "books",
    price: 220000,
    stock: 12,
    tags: ["mongodb", "java", "backend"],
    attributes: { language: "vi", edition: 2 },
    active: true,
    version: 1,
    createdAt: ISODate("2026-11-01T09:00:00Z")
  },
  {
    _id: "p-002",
    tenantId: "tenant-a",
    sku: "BOOK-002",
    name: "Advanced Java Book",
    category: "books",
    price: 350000,
    stock: 4,
    tags: ["java", "backend"],
    attributes: { language: "vi", edition: 1 },
    active: true,
    version: 1,
    createdAt: ISODate("2026-11-02T09:00:00Z")
  },
  {
    _id: "p-003",
    tenantId: "tenant-a",
    sku: "DEV-001",
    name: "Developer Keyboard",
    category: "devices",
    price: 890000,
    stock: 0,
    tags: ["hardware", "accessories"],
    attributes: { color: "black" },
    active: false,
    version: 3,
    createdAt: ISODate("2026-11-03T09:00:00Z")
  },
  {
    _id: "p-004",
    tenantId: "tenant-b",
    sku: "BOOK-001",
    name: "Tenant B Private Doc",
    category: "books",
    price: 150000,
    stock: 8,
    tags: ["private"],
    attributes: { language: "en" },
    active: true,
    version: 1,
    createdAt: ISODate("2026-11-04T09:00:00Z")
  }
]);

db.orders.insertMany([
  {
    _id: "o-001",
    tenantId: "tenant-a",
    status: "PENDING",
    customerId: "c-001",
    items: [
      { sku: "BOOK-001", qty: 2, price: 220000 },
      { sku: "BOOK-002", qty: 1, price: 350000 }
    ],
    total: 790000,
    version: 1,
    createdAt: ISODate("2026-11-05T09:00:00Z")
  },
  {
    _id: "o-002",
    tenantId: "tenant-a",
    status: "PAID",
    customerId: "c-002",
    items: [
      { sku: "BOOK-001", qty: 1, price: 220000 }
    ],
    total: 220000,
    version: 2,
    createdAt: ISODate("2026-11-06T09:00:00Z")
  }
]);
~~~

### 3.1. Why Include `tenant-b`?

SKU `BOOK-001` exists in two tenants. A CRUD operation filtering only by `sku` can accidentally touch another tenant's record. This illustrates authorization scoping and composite keys.

### 3.2. Sample `_id` Values Are Strings

In this seed, `_id` has BSON type String. If production uses `ObjectId`, filters must pass `ObjectId` rather than a matching hex string.

### 3.3. Monetary Types

`price` is shown as integer currency units. For currencies requiring fractional amounts, consider `Decimal128` or integer minor units; never arbitrarily use floating-point for money.

## 4. `Bson` as the Common Interface

Builder methods return **`org.bson.conversions.Bson`** or compatible implementations.

~~~java
Bson filter = Filters.eq("category", "books");
Bson projection = Projections.include("name", "price");
Bson sort = Sorts.descending("createdAt");
Bson update = Updates.inc("stock", 1);
~~~

The driver converts these objects into BSON commands sent to MongoDB. They do not execute any query until passed to an API such as `find` or `updateOne`.

### 4.1. `Document` and `Bson`

`Document` also implements `Bson` and can be passed anywhere `Bson` is expected:

~~~java
Bson rawFilter = new Document(
    "category", "books"
);
~~~

However, builders are usually much easier to read:

~~~java
Bson builderFilter = Filters.eq(
    "category", "books"
);
~~~

### 4.2. Builders Are Not Java Streams

`Filters` define **server-side** predicates—not in-memory filtering of a `List` already loaded into Java. MongoDB evaluates filters on the server and can leverage indexes.

### 4.3. Never Concatenate JSON Strings Manually

Poor design:

~~~java
String query = "{tenantId:'" + requestTenant +
    "', price:{$gte:" + minPrice + "}}";
~~~

Hand-built query strings suffer from escaping/type bugs and risk accepting injected operators. Use `Filters` and strict allowlists. Still, builders do not replace authorization.

## 5. `Filters.eq`: Equality Comparison

~~~java
Bson books = Filters.eq("category", "books");

products.find(books).forEach(
    doc -> System.out.println(doc.toJson())
);
~~~

Equivalent to:

~~~javascript
db.products.find({ category: "books" });
~~~

Fetch by ID:

~~~java
Document product = products.find(
    Filters.eq("_id", "p-001")
).first();

if (product == null) {
    System.out.println("Not found");
}
~~~

### 5.1. `eq` Compares BSON Types

~~~java
Filters.eq("stock", 0);
Filters.eq("active", true);
Filters.eq("tenantId", "tenant-a");
~~~

Do not pass the string `"0"` to match a field stored as integer `0`.

### 5.2. Comparing `ObjectId`

When `_id` is an `ObjectId`:

~~~java
import org.bson.types.ObjectId;

Bson filter = Filters.eq(
    "_id",
    new ObjectId("507f1f77bcf86cd799439011")
);
~~~

The string `"507f..."` and `ObjectId` look similar when printed, yet have different BSON types.

## 6. `Filters.ne` and Value Sets

Not equal:

~~~java
Bson notArchived = Filters.ne(
    "status", "ARCHIVED"
);
~~~

Status within an allowed list:

~~~java
Bson allowed = Filters.in(
    "status", "PENDING", "PAID"
);
~~~

Excluding a list:

~~~java
Bson excluded = Filters.nin(
    "status", "CANCELLED", "FAILED"
);
~~~

### 6.1. `ne` and `nin` Match Missing Fields

MongoDB `$ne`/`$nin` also match documents **lacking the field**. If business rules only allow `PENDING` or `PAID`, use **`in(PENDING, PAID)`** rather than merely excluding `CANCELLED`.

### 6.2. `in` vs. `all`

With a `tags` array:

~~~java
Filters.in(
    "tags", "java", "mongodb"
);
~~~

matches when at least one value matches.

Whereas:

~~~java
Filters.all(
    "tags", List.of("java", "backend")
);
~~~

requires the array to contain all specified values.

### 6.3. Do Not Use Negation as Validation

A document missing `status` does not become valid merely because it is not `"CANCELLED"`. Enforce required states with schema validation and positive allowlists.

## 7. `Filters.gt`, `gte`, `lt`, `lte`

Find prices from 200,000 up to (excluding) 500,000:

~~~java
Bson range = Filters.and(
    Filters.gte("price", 200000),
    Filters.lt("price", 500000)
);
~~~

| Builder | MongoDB Operator | Meaning |
| --- | --- | --- |
| `gt` | `$gt` | Greater than |
| `gte` | `$gte` | Greater than or equal |
| `lt` | `$lt` | Less than |
| `lte` | `$lte` | Less than or equal |
| `eq` | `$eq` | Equal |
| `ne` | `$ne` | Not equal |

### 7.1. Half-Open Intervals for Dates

~~~java
import java.time.Instant;
import java.util.Date;

Date from = Date.from(
    Instant.parse("2026-11-01T00:00:00Z")
);
Date until = Date.from(
    Instant.parse("2026-12-01T00:00:00Z")
);

Bson filter = Filters.and(
    Filters.gte("createdAt", from),
    Filters.lt("createdAt", until)
);
~~~

Using `[from, until)` ensures adjacent time windows never overlap on boundaries.

### 7.2. BSON Date Differs from ISO Strings

If `createdAt` is BSON Date, do not query with a `String` expecting a match. Keep query types aligned with your schema and codecs.

## 8. `Filters.and`, `or`, `nor`, `not`

Find active products for `tenant-a`:

~~~java
Bson filter = Filters.and(
    Filters.eq("tenantId", "tenant-a"),
    Filters.eq("active", true)
);
~~~

Books or devices:

~~~java
Bson filter = Filters.or(
    Filters.eq("category", "books"),
    Filters.eq("category", "devices")
);
~~~

Combined:

~~~java
Bson filter = Filters.and(
    Filters.eq("tenantId", trustedTenantId),
    Filters.eq("active", true),
    Filters.or(
        Filters.eq("category", "books"),
        Filters.eq("category", "devices")
    )
);
~~~

Other methods:

~~~java
Filters.nor(
    Filters.eq("status", "FAILED"),
    Filters.eq("status", "CANCELLED")
);

Filters.not(
    Filters.gt("stock", 10)
);
~~~

### 8.1. Clear Boolean Semantics

- **`and`:** every condition must match.
- **`or`:** at least one condition matches.
- **`nor`:** no condition matches.
- **`not`:** negates the expression per MongoDB semantics.

Be careful with `NOT`/`NOR` and missing fields; do not assume classic two-valued boolean logic always aligns with absent/`null` fields.

### 8.2. Tenant Must Always Be Controlled

`trustedTenantId` must come from a backend-verified auth context, never from arbitrary client input.

## 9. Null and Missing Fields

A document containing:

~~~javascript
{ discount: null }
~~~

differs from a document lacking `discount`. However, MongoDB null equality matches both:

~~~java
Filters.eq("discount", null);
~~~

### 9.1. Checking Existence

~~~java
Filters.exists("discount", true);
Filters.exists("discount", false);
~~~

### 9.2. Field Present and Equal to Null

~~~java
Bson explicitNull = Filters.and(
    Filters.exists("discount", true),
    Filters.eq("discount", null)
);
~~~

### 9.3. Soft Delete Conventions

If the app treats `deletedAt` as **absent** when not deleted:

~~~java
Bson notDeleted = Filters.exists(
    "deletedAt", false
);
~~~

If the app stores `deletedAt: null` on active records, design the filter accordingly. Never mix both conventions accidentally.

## 10. Nested Fields and Dot Notation

Given:

~~~javascript
attributes: {
  language: "vi",
  edition: 2
}
~~~

use:

~~~java
Bson filter = Filters.and(
    Filters.eq("attributes.language", "vi"),
    Filters.gte("attributes.edition", 2)
);
~~~

### 10.1. Dot Paths Differ from Whole-Document Equality

~~~java
Filters.eq(
    "attributes",
    new Document("language", "vi")
);
~~~

is not equivalent to matching `attributes.language == "vi"` when `attributes` contains other fields.

### 10.2. BSON Paths Follow the Stored Schema

If a Java POJO property name differs from the stored BSON field name, builder paths must use the actual mapped BSON field name.

### 10.3. Nested Paths Can Be Indexed

If queries frequently filter on `attributes.language`, consider indexing that path and verifying with `explain` and metrics.

## 11. Arrays and `$elemMatch`

With `tags` as an array of strings:

~~~java
Filters.eq("tags", "java");
Filters.size("tags", 3);
Filters.all("tags", List.of("java", "backend"));
~~~

MongoDB supports element-matching semantics across multiple array predicates.

With `orders` containing an `items` array of subdocuments:

~~~javascript
items: [
  { sku: "BOOK-001", qty: 2 },
  { sku: "BOOK-002", qty: 1 }
]
~~~

To require that **the exact same item** has both `sku == "BOOK-001"` and `qty >= 2`:

~~~java
Bson filter = Filters.elemMatch(
    "items",
    Filters.and(
        Filters.eq("sku", "BOOK-001"),
        Filters.gte("qty", 2)
    )
);
~~~

### 11.1. Why Not Just Two Dot Paths?

~~~java
Filters.and(
    Filters.eq("items.sku", "BOOK-001"),
    Filters.gte("items.qty", 2)
);
~~~

can match across **two different array elements**. `$elemMatch` binds all inner conditions to a single array element.

### 11.2. Multi-Tenant Array Queries

~~~java
Bson scoped = Filters.and(
    Filters.eq("tenantId", trustedTenantId),
    Filters.elemMatch(
        "items",
        Filters.eq("sku", "BOOK-001")
    )
);
~~~

### 11.3. `size` Is Not Pagination

`Filters.size("items", 2)` filters documents whose array has exactly two elements—it does not limit the number of documents returned.

## 12. Regex and Text Filters

Find names starting with `"Book"`:

~~~java
import java.util.regex.Pattern;

Bson startsWith = Filters.regex(
    "name",
    Pattern.compile("^Book")
);
~~~

### 12.1. Regex Does Not Replace Full-Text Search

Regex suits simple prefix or format matches. For large-scale content search, consider text indexes, Atlas Search, or dedicated search engines.

### 12.2. Indexes and Anchors

An anchored prefix regex generally uses indexes better than unanchored regexes, subject to collation and the query planner. Always verify with `explain`.

### 12.3. Escape User Input

Never let users supply uncontrolled arbitrary regular expressions. When searching literal substrings, escape regex metacharacters and bound input length.

### 12.4. `Filters.text`

~~~java
Bson filter = Filters.text(
    "MongoDB Java"
);
~~~

Requires a text index and follows text-search semantics, distinct from regex or vector embeddings.

## 13. Building Dynamic Filters with a Condition List

In a REST API, `category`/`minPrice`/`maxPrice`/`active` may be optional, while `tenantId` is mandatory.

~~~java
import java.util.ArrayList;
import java.util.List;

public static Bson productFilters(
    String trustedTenantId,
    String category,
    Integer minPrice,
    Integer maxPrice,
    Boolean active
) {
    List<Bson> conditions = new ArrayList<>();

    conditions.add(
        Filters.eq("tenantId", trustedTenantId)
    );
    conditions.add(
        Filters.exists("deletedAt", false)
    );

    if (category != null && !category.isBlank()) {
        conditions.add(
            Filters.eq("category", category)
        );
    }

    if (minPrice != null) {
        conditions.add(
            Filters.gte("price", minPrice)
        );
    }

    if (maxPrice != null) {
        conditions.add(
            Filters.lte("price", maxPrice)
        );
    }

    if (active != null) {
        conditions.add(
            Filters.eq("active", active)
        );
    }

    return Filters.and(conditions);
}
~~~

### 13.1. Validate Before Building

Validate `minPrice <= maxPrice`, permitted numeric bounds, and allowlisted categories where needed.

### 13.2. Never Accept Raw Operators from Clients

A flexible search API should map public filter names to allowlisted BSON paths rather than accepting arbitrary JSON/BSON predicates.

### 13.3. Never Return an Empty Filter When Auth Fails

If the tenant cannot be authenticated, throw an authorization error rather than falling back to an unscoped query.

## 14. `find` and `FindIterable`

~~~java
Bson filter = Filters.and(
    Filters.eq("tenantId", "tenant-a"),
    Filters.eq("active", true)
);

products.find(filter).forEach(
    doc -> System.out.println(
        doc.getString("name")
    )
);
~~~

### 14.1. `find().first()`

~~~java
Document product = products.find(
    Filters.eq("_id", "p-001")
).first();
~~~

`first()` returns **`null`** when no document matches.

### 14.2. `for-each`

~~~java
for (Document product : products.find(filter)) {
    System.out.println(product.toJson());
}
~~~

### 14.3. Queries Run on the Server

The driver does not download the whole collection to filter in Java streams.

### 14.4. Large Datasets

Never collect millions of documents into an unbounded `List`; use cursors, pagination, or batch processing.

## 15. `Projections.include` and `exclude`

Return only `name`, `sku`, and `price`:

~~~java
Bson projection = Projections.include(
    "name",
    "sku",
    "price"
);

products.find(
    Filters.eq("tenantId", "tenant-a")
).projection(projection)
 .forEach(doc -> System.out.println(doc.toJson()));
~~~

### 15.1. `_id` Is Returned by Default

To suppress `_id`:

~~~java
Bson projection = Projections.fields(
    Projections.include(
        "name", "sku", "price"
    ),
    Projections.excludeId()
);
~~~

### 15.2. `exclude`

~~~java
Bson projection = Projections.exclude(
    "secretKey",
    "internalNotes"
);
~~~

### 15.3. Do Not Mix Include and Exclude Arbitrarily

Per projection semantics, do not mix inclusion and exclusion across different fields (`_id` being the standard exception). Pick one clear strategy.

### 15.4. Projections and Authorization

Projections trim payloads and help avoid returning extra fields, yet do not replace access control. For public APIs, prefer allowlisted DTOs/projections plus record- and field-level authorization.

## 16. `Projections.fields`, Nested Fields, and Arrays

A combined projection:

~~~java
Bson projection = Projections.fields(
    Projections.include(
        "sku",
        "name",
        "attributes.language"
    ),
    Projections.excludeId()
);
~~~

### 16.1. Nested Projections Do Not Flatten Automatically

`attributes.language` stays nested inside the `attributes` subdocument rather than becoming a top-level `language` field. DTO mappers control the final API shape.

### 16.2. Slicing Arrays

~~~java
Projections.slice("items", 2);
~~~

Limits the elements returned inside **each document's `items` array**, not the number of documents.

### 16.3. `elemMatch` Projection

~~~java
Projections.elemMatch(
    "items",
    Filters.eq("sku", "BOOK-001")
);
~~~

Selects array elements using `$elemMatch` projection semantics. For multiple matching items or complex transformations, use an aggregation pipeline.

### 16.4. Text Score

With an appropriate text-index query:

~~~java
Projections.metaTextScore("textScore");
~~~

Text score is not a calibrated probability and applies only to text searches.

## 17. Computed Projections

When server and driver versions support expression projections:

~~~java
Bson projection = Projections.computed(
    "inventoryValue",
    new Document(
        "$multiply",
        List.of("$price", "$stock")
    )
);
~~~

### 17.1. Computed Fields Are Not Persisted

In a projection, expressions compute return values only; they do not update `inventoryValue` on disk.

### 17.2. When to Use Aggregation?

For `$group`, `$lookup`, or multi-stage transformations, an aggregation pipeline is clearer.

### 17.3. Types and Overflow

If `price` and `stock` have mixed numeric types, multiplication follows BSON numeric promotion and bounds. Use appropriate monetary types.

## 18. `Sorts.ascending` and `descending`

Price ascending:

~~~java
Bson sort = Sorts.ascending("price");
~~~

Newest `createdAt` first:

~~~java
Bson sort = Sorts.descending("createdAt");
~~~

Usage:

~~~java
products.find(
    Filters.eq("tenantId", "tenant-a")
).sort(Sorts.ascending("price"))
 .forEach(System.out::println);
~~~

### 18.1. Sorts Do Not Reorder Stored Data

`Sorts` govern query output ordering, not physical document order in MongoDB.

### 18.2. Without a Sort, Business Order Is Not Guaranteed

Never rely on natural insertion order in APIs.

### 18.3. Mixed BSON Types

If `price` mixes strings and numbers, sort ordering follows BSON type comparison rules and yields surprising results. Standardize your schema.

## 19. `Sorts.orderBy` and Tie-Breakers

~~~java
Bson sort = Sorts.orderBy(
    Sorts.ascending("category"),
    Sorts.descending("price"),
    Sorts.ascending("_id")
);
~~~

### 19.1. Deterministic Sorting

When multiple documents share identical `createdAt`, append `_id` as a tie-breaker:

~~~java
Bson stableSort = Sorts.orderBy(
    Sorts.descending("createdAt"),
    Sorts.descending("_id")
);
~~~

### 19.2. Sorting by a Non-Unique Timestamp

Without a unique tie-breaker, consecutive pages can repeat or skip records sharing the same timestamp.

### 19.3. Concurrent Changes

A tie-breaker stabilizes ordering for a point-in-time state, though inserts/updates between requests can still shift offset pages.

## 20. Combining `Filters`, `Projections`, `Sorts`, and `limit`

A practical read query:

~~~java
Bson filter = Filters.and(
    Filters.eq("tenantId", trustedTenantId),
    Filters.eq("active", true),
    Filters.gte("price", 200000)
);

Bson projection = Projections.fields(
    Projections.include(
        "sku", "name", "price", "stock"
    ),
    Projections.excludeId()
);

Bson sort = Sorts.orderBy(
    Sorts.ascending("price"),
    Sorts.ascending("sku")
);

products.find(filter)
    .projection(projection)
    .sort(sort)
    .limit(20)
    .forEach(doc -> {
        System.out.println(doc.toJson());
    });
~~~

### 20.1. Query Semantics vs. Method Call Order

MongoDB executes filter/projection/sort/limit per `find` semantics rather than sorting client-side.

### 20.2. Supporting Indexes

For `tenantId`, `active`, and a `price` range, design and benchmark an appropriate compound index. Builders do not create indexes automatically.

### 20.3. API Responses

Never expose raw `Document.toJson()` to public clients in production; map to DTOs and restrict fields per policy.

## 21. Offset Pagination: `skip`/`limit`

Example: page 3, 10 items per page:

~~~java
int page = 3;
int pageSize = 10;
int offset = (page - 1) * pageSize;

Bson sort = Sorts.orderBy(
    Sorts.descending("createdAt"),
    Sorts.descending("_id")
);

products.find(
    Filters.eq("tenantId", trustedTenantId)
).sort(sort)
 .skip(offset)
 .limit(pageSize)
 .forEach(System.out::println);
~~~

### 21.1. Validate `page` and `pageSize`

Enforce `page >= 1`, cap `pageSize`, prevent integer overflow on `offset`, and block absurdly deep skips.

### 21.2. Large Skips Are Expensive

MongoDB must still traverse and discard skipped entries, making deep offset pagination slow.

### 21.3. Concurrent Inserts and Deletes

Offset pages can duplicate or skip items when records change between requests. Keyset pagination is generally superior for large lists.

## 22. Keyset Pagination with `Filters` and `Sorts`

Sort `createdAt` desc, then `_id` desc:

~~~java
Bson sort = Sorts.orderBy(
    Sorts.descending("createdAt"),
    Sorts.descending("_id")
);
~~~

Given cursor `(lastCreatedAt, lastId)`:

~~~java
Bson after = Filters.or(
    Filters.lt("createdAt", lastCreatedAt),
    Filters.and(
        Filters.eq("createdAt", lastCreatedAt),
        Filters.lt("_id", lastId)
    )
);

Bson filter = Filters.and(
    Filters.eq("tenantId", trustedTenantId),
    Filters.eq("active", true),
    after
);

products.find(filter)
    .sort(sort)
    .limit(20)
    .forEach(System.out::println);
~~~

### 22.1. Why `lt`?

Under descending order, items after the cursor have a smaller timestamp, or an equal timestamp with a smaller `_id`.

### 22.2. Bind Cursors to Query Scope

Never pass a cursor generated under `tenant-a` into a `tenant-b` query, or change sort order without resetting the cursor.

### 22.3. Match the `_id` Type

If stored `_id` is `ObjectId`, decode `lastId` back to `ObjectId`. This lab uses `String`.

### 22.4. Keyset Does Not Create an Immutable Snapshot

If sort keys mutate between requests, results can still shift. If snapshot consistency is required, use an appropriate read concern/snapshot mechanism.

## 23. Counting and `distinct`

Count matching documents:

~~~java
long count = products.countDocuments(
    Filters.and(
        Filters.eq("tenantId", trustedTenantId),
        Filters.eq("active", true)
    )
);
~~~

Distinct categories within a tenant:

~~~java
products.distinct(
    "category",
    Filters.eq("tenantId", trustedTenantId),
    String.class
).forEach(System.out::println);
~~~

### 23.1. `countDocuments` vs. `estimatedDocumentCount`

`estimatedDocumentCount` reads collection metadata estimates when applicable; never use it in place of `countDocuments(filter)` when you need an exact tenant-scoped count.

### 23.2. `distinct` Target Type

Ensure the field's BSON values match the Java result class passed to `distinct`.

### 23.3. Exact Counts Can Be Costly

On large collections, measure count latency and consider UX or maintained counters if exact totals are unnecessary on every request.

## 24. CREATE with `insertOne`

~~~java
Document product = new Document("_id", "p-005")
    .append("tenantId", trustedTenantId)
    .append("sku", "BOOK-005")
    .append("name", "Learning MongoDB with Java")
    .append("category", "books")
    .append("price", 280000)
    .append("stock", 5)
    .append("active", true)
    .append("version", 1)
    .append("createdAt", new Date());

products.insertOne(product);
~~~

### 24.1. `insertMany`

~~~java
List<Document> batch = List.of(
    new Document("_id", "p-101")
        .append("tenantId", trustedTenantId)
        .append("name", "A"),
    new Document("_id", "p-102")
        .append("tenantId", trustedTenantId)
        .append("name", "B")
);

products.insertMany(batch);
~~~

### 24.2. Duplicate Key

MongoDB enforces a unique index on `_id`. Duplicate `_id` triggers a duplicate key error. If SKUs are unique per tenant, add a compound unique index.

### 24.3. Never Copy Entire Client JSON Straight into the Database

Validate required fields, ownership, and numeric bounds, and prevent clients from setting fields like `tenantId`, `createdBy`, or `paidAt` unless authorized.

## 25. `Updates.set`, `unset`, `rename`

Update `name`:

~~~java
Bson filter = Filters.and(
    Filters.eq("_id", "p-001"),
    Filters.eq("tenantId", trustedTenantId)
);

products.updateOne(
    filter,
    Updates.set("name", "Practical MongoDB Book")
);
~~~

Remove an unused field:

~~~java
Updates.unset("deprecatedField");
~~~

Rename a field:

~~~java
Updates.rename(
    "oldFieldName",
    "newFieldName"
);
~~~

### 25.1. `set` on Nested Fields

~~~java
Updates.set("attributes.language", "en");
~~~

Targets only that nested field via dot notation.

### 25.2. Do Not Overwrite the Whole Subdocument When Changing One Field

~~~java
Updates.set(
    "attributes",
    new Document("language", "en")
);
~~~

replaces all of `attributes`, wiping out sibling fields like `edition`.

### 25.3. `unset` Differs from Setting `null`

`unset` removes the key completely, whereas setting `null` leaves the key present with value `null`; `$exists`/null queries behave differently.

## 26. `Updates.combine` for Multiple Operators

~~~java
Bson update = Updates.combine(
    Updates.set("name", "New MongoDB Book"),
    Updates.set("active", true),
    Updates.currentDate("updatedAt"),
    Updates.inc("version", 1)
);

products.updateOne(
    Filters.and(
        Filters.eq("_id", "p-001"),
        Filters.eq("tenantId", trustedTenantId)
    ),
    update
);
~~~

### 26.1. Single-Document Atomicity

One `updateOne` applying combined operators to the same document executes atomically at the document level.

### 26.2. Never Update the Same Field with Conflicting Operators

Combining `set` and `inc` on `version` in the same update causes a conflict. Express one consistent transformation.

### 26.3. Do Not Split into Two Calls Without Reason

If `name` and `version` must change together, combining them inside one `updateOne` avoids intermediate inconsistent states.

## 27. `Updates.inc` to Prevent Lost Updates

Concurrency bug:

~~~text
Thread A reads stock=10
Thread B reads stock=10
Thread A sets stock=11
Thread B sets stock=11
Expected 12 but actual 11
~~~

Server-side increment:

~~~java
products.updateOne(
    Filters.eq("_id", "p-001"),
    Updates.inc("stock", 1)
);
~~~

### 27.1. Two Increments Serialize Safely at the Document Level

MongoDB evaluates the increment when the write applies on the server, independent of stale client snapshots.

### 27.2. Negative `inc`

~~~java
Updates.inc("stock", -1);
~~~

Not safe by itself if stock must never drop below zero; add a conditional filter `stock >= 1`.

### 27.3. Nulls and Numeric Types

`$inc` requires a numeric target field. Updating a `null` field fails; schema validation helps guard against bad types.

### 27.4. `$inc` Is Not Workflow-Idempotent

If an API retries the same business request twice, stock changes twice. Track operation IDs / idempotency keys when workflows require exactly-once effects.

## 28. Safe Stock Deduction with Conditional Updates

~~~java
import com.mongodb.client.result.UpdateResult;

int quantity = 3;

Bson filter = Filters.and(
    Filters.eq("_id", "p-001"),
    Filters.eq("tenantId", trustedTenantId),
    Filters.eq("active", true),
    Filters.gte("stock", quantity)
);

Bson update = Updates.combine(
    Updates.inc("stock", -quantity),
    Updates.currentDate("updatedAt")
);

UpdateResult result = products.updateOne(
    filter, update
);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
        "Insufficient stock or invalid product"
    );
}
~~~

### 28.1. Filter and Update Are One Atomic Operation

The `stock >= quantity` predicate is evaluated atomically with the write. Two buyers cannot simultaneously deduct past zero as long as the filter preserves the invariant.

### 28.2. `matchedCount=0` Has Multiple Possible Reasons

The product may not exist, belong to another tenant, have `active=false`, or lack stock. Never leak another tenant's product state in error responses.

### 28.3. Multi-Product Orders Need Transactions/Workflows

One `updateOne` cannot atomically decrement stock across multiple products and insert an order. When all-or-nothing is required, use a multi-document transaction on a supporting topology.

## 29. `Updates.min`, `max`, `mul`, and `currentDate`

~~~java
Updates.min("lowestPrice", 190000);
Updates.max("highestPrice", 900000);
Updates.mul("stock", 2);
Updates.currentDate("updatedAt");
~~~

### 29.1. `min` / `max`

`$min` and `$max` update the field only when the supplied value is smaller or larger than the current value per BSON comparison order.

### 29.2. `mul`

`$mul` multiplies numeric fields; check numeric types and missing/null behavior for your version.

### 29.3. `currentDate`

Lets MongoDB set the timestamp server-side, helpful when client clocks skew.

### 29.4. Never Pick an Operator by Name While Ignoring Invariants

For example, `mul(stock, 2)` does not represent valid restocking twice. Always define the required business state transition first.

## 30. Arrays: `push`, `addToSet`, `pull`

Append tag, allowing duplicates:

~~~java
products.updateOne(
    Filters.eq("_id", "p-001"),
    Updates.push("tags", "database")
);
~~~

Append only if no equivalent element exists:

~~~java
products.updateOne(
    Filters.eq("_id", "p-001"),
    Updates.addToSet("tags", "database")
);
~~~

Remove matching elements:

~~~java
products.updateOne(
    Filters.eq("_id", "p-001"),
    Updates.pull("tags", "legacy")
);
~~~

### 30.1. `addToSet` Does Not Deduplicate Existing Entries

If the array already holds two `"java"` strings, `addToSet("java")` does not clean them up—it only avoids appending another duplicate.

### 30.2. `addToSet` Does Not Create a Collection-Wide Unique Index

To keep SKUs unique across documents, create a unique index rather than relying on array operators.

### 30.3. Array Size and Document Growth

Unbounded array growth bloats documents, increases write contention, and approaches the BSON document size limit. When one-to-many relationships grow unboundedly, use a separate collection.

## 31. Array Filters and Positional Updates

Given order:

~~~javascript
{
  _id: "o-001",
  tenantId: "tenant-a",
  items: [
    { sku: "BOOK-001", qty: 2 },
    { sku: "BOOK-002", qty: 1 }
  ]
}
~~~

Update `qty` for the item with `sku == "BOOK-002"`:

~~~java
Bson filter = Filters.and(
    Filters.eq("_id", "o-001"),
    Filters.eq("tenantId", trustedTenantId)
);

Bson update = Updates.set(
    "items.$[item].qty", 5
);

UpdateOptions options = new UpdateOptions()
    .arrayFilters(
        List.of(
            new Document("item.sku", "BOOK-002")
        )
    );

orders.updateOne(filter, update, options);
~~~

### 31.1. Identifier Must Match

In `items.$[item].qty`, the `item` identifier must be referenced in `arrayFilters`. Mismatched or missing identifiers fail.

### 31.2. Can Match Multiple Elements

If `items` contains two entries with the same SKU, `arrayFilters` updates both. If business logic targets a single entry, assign a unique line-item ID.

### 31.3. Positional `$`

~~~java
orders.updateOne(
    Filters.and(
        Filters.eq("_id", "o-001"),
        Filters.eq("items.sku", "BOOK-001")
    ),
    Updates.inc("items.$.qty", 1)
);
~~~

Positional `$` relies on the array predicate in the query filter to identify the matched element.

### 31.4. All Positional `$[]`

~~~java
orders.updateOne(
    Filters.eq("_id", "o-001"),
    Updates.set("items.$[].selected", false)
);
~~~

Updates every element in `items`. Use only when intending to modify all elements.

## 32. `updateOne` and `updateMany`

Single document:

~~~java
UpdateResult result = products.updateOne(
    Filters.and(
        Filters.eq("_id", "p-001"),
        Filters.eq("tenantId", trustedTenantId)
    ),
    Updates.set("active", false)
);
~~~

Multiple documents:

~~~java
UpdateResult result = products.updateMany(
    Filters.and(
        Filters.eq("tenantId", trustedTenantId),
        Filters.eq("category", "books")
    ),
    Updates.set("featured", true)
);
~~~

### 32.1. `updateMany` Is Not a Multi-Document Transaction

Each document write is atomic individually, but the overall `updateMany` does not execute as an all-or-nothing transaction.

### 32.2. Never Omit Tenant Scope in `updateMany`

Omitting `tenantId` can corrupt data across multiple customers. Enforce repository guardrails and carefully review bulk updates.

### 32.3. Bulk Preview

Before large bulk operations, inspect matching counts and sample documents, and enforce change-approval and backup policies.

## 33. `UpdateResult`: Matched vs. Modified

~~~java
UpdateResult result = products.updateOne(
    Filters.eq("_id", "p-001"),
    Updates.set("active", true)
);

System.out.println(result.getMatchedCount());
System.out.println(result.getModifiedCount());
System.out.println(result.getUpsertedId());
~~~

### 33.1. `matchedCount`

Number of documents matching the filter (at most 1 for `updateOne`).

### 33.2. `modifiedCount`

Number of documents actually changed. If `active` is already `true`, setting it to `true` yields `matched=1` and `modified=0`.

### 33.3. `modified=0` Does Not Mean Not Found

Check `matchedCount` to tell "not found" apart from "no change needed."

### 33.4. Acknowledgment

Under unacknowledged writes, result counts are unavailable. Choose write concerns aligned with durability and SLOs.

## 34. Upsert with `UpdateOptions`

Update if matched, otherwise insert:

~~~java
Bson filter = Filters.and(
    Filters.eq("tenantId", trustedTenantId),
    Filters.eq("sku", "BOOK-010")
);

Bson update = Updates.combine(
    Updates.set("name", "Applied MongoDB Book"),
    Updates.set("price", 310000),
    Updates.setOnInsert(
        "createdAt", new Date()
    ),
    Updates.currentDate("updatedAt")
);

UpdateResult result = products.updateOne(
    filter,
    update,
    new UpdateOptions().upsert(true)
);
~~~

### 34.1. `setOnInsert`

Sets `createdAt` only when the upsert inserts a new document, leaving existing records' `createdAt` intact.

### 34.2. Filter Must Be a Stable Business Identity

Never upsert with a broad filter like `category="books"` or without `tenantId`. You risk updating the wrong document or inserting identity-less records.

### 34.3. Unique Compound Index

If SKU is unique per tenant:

~~~javascript
db.products.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true }
);
~~~

A unique index prevents race duplicates; applications must still handle duplicate key errors if concurrent writers upsert simultaneously.

### 34.4. Idempotency

Upserts keyed by stable identity are easier to retry than inserts generating fresh random IDs each attempt, though `$inc` or external side effects still require business operation IDs.

## 35. `replaceOne` vs. `Updates.set`

~~~java
Document replacement = new Document(
    "_id", "p-001"
).append("tenantId", trustedTenantId)
 .append("sku", "BOOK-001")
 .append("name", "New Name")
 .append("price", 250000)
 .append("stock", 10);

products.replaceOne(
    Filters.and(
        Filters.eq("_id", "p-001"),
        Filters.eq("tenantId", trustedTenantId)
    ),
    replacement
);
~~~

### 35.1. Replace Deletes Fields Absent from Replacement

If the original held `tags`, `attributes`, `version`, and `createdAt` missing from `replacement`, those fields are erased.

### 35.2. Changing One Field? Use `set`

`Updates.set("name", ...)` is safer and cleaner than `replaceOne` when updating a few fields.

### 35.3. `_id` Is Immutable

You cannot change a document's `_id` via `replaceOne` or `update`.

### 35.4. `ReplaceOptions`

`replaceOne` supports `upsert` via `ReplaceOptions`; keep full-document replacement semantics distinct from update operators.

## 36. `findOneAndUpdate`: Update and Return Document

~~~java
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.ReturnDocument;

Bson filter = Filters.and(
    Filters.eq("_id", "p-001"),
    Filters.eq("tenantId", trustedTenantId),
    Filters.gte("stock", 1)
);

FindOneAndUpdateOptions options =
    new FindOneAndUpdateOptions()
        .returnDocument(ReturnDocument.AFTER)
        .projection(
            Projections.include("sku", "stock")
        );

Document after = products.findOneAndUpdate(
    filter,
    Updates.inc("stock", -1),
    options
);
~~~

### 36.1. `ReturnDocument.AFTER`

Returns the post-update document state. Alternatively, `ReturnDocument.BEFORE` returns the pre-update state.

### 36.2. Returns `null` When Unmatched

Handle `null` when stock is exhausted or the product belongs to another tenant.

### 36.3. Limit Projection

Projections prevent returning internal fields when the API only needs the remaining stock after reservation.

### 36.4. When to Use?

When you need an atomic update plus the resulting value without issuing two separate operations.

## 37. Optimistic Locking with `version`

Document:

~~~javascript
{
  _id: "p-001",
  tenantId: "tenant-a",
  version: 5,
  name: "Old Name"
}
~~~

When the client read version 5:

~~~java
Bson filter = Filters.and(
    Filters.eq("_id", "p-001"),
    Filters.eq("tenantId", trustedTenantId),
    Filters.eq("version", 5)
);

Bson update = Updates.combine(
    Updates.set("name", "New Name"),
    Updates.inc("version", 1),
    Updates.currentDate("updatedAt")
);

UpdateResult result = products.updateOne(
    filter, update
);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
        "Version conflict or document does not exist"
    );
}
~~~

### 37.1. Compare-and-Set

If another writer incremented `version` from 5 to 6, updating with `version == 5` fails to match. The app can return HTTP `409`, reload, or merge.

### 37.2. Preventing Lost Updates

Reading an old name and writing blindly without checking `version` silently overwrites concurrent changes.

### 37.3. Do Not Retry Conflicts Infinitely

For user edits, notify the user that data changed. For counters, use server-side `$inc` where suitable.

## 38. Conditional State Transitions

An order can only transition from `PENDING` to `PAID`:

~~~java
Bson filter = Filters.and(
    Filters.eq("_id", "o-001"),
    Filters.eq("tenantId", trustedTenantId),
    Filters.eq("status", "PENDING")
);

Bson update = Updates.combine(
    Updates.set("status", "PAID"),
    Updates.inc("version", 1),
    Updates.currentDate("updatedAt")
);

UpdateResult result = orders.updateOne(
    filter, update
);

if (result.getMatchedCount() != 1) {
    throw new IllegalStateException(
        "Order is no longer in PENDING state"
    );
}
~~~

### 38.1. Race Between `PAID` and `CANCELLED`

If two workflows read `PENDING` and blindly set their target status, last-writer-wins corrupts state. Filtering on `status == "PENDING"` lets only the first transition match.

### 38.2. Business-Level Side Effects

Updating MongoDB state does not atomically charge a payment gateway or send email. Use idempotency/outbox patterns and reconciliation with external systems.

## 39. DELETE: `deleteOne` and `deleteMany`

~~~java
import com.mongodb.client.result.DeleteResult;

DeleteResult result = products.deleteOne(
    Filters.and(
        Filters.eq("_id", "p-003"),
        Filters.eq("tenantId", trustedTenantId)
    )
);

System.out.println(result.getDeletedCount());
~~~

Delete multiple matching records:

~~~java
DeleteResult result = products.deleteMany(
    Filters.and(
        Filters.eq("tenantId", trustedTenantId),
        Filters.eq("active", false)
    )
);
~~~

### 39.1. Empty Filters Are Dangerous

~~~java
products.deleteMany(new Document());
~~~

deletes the entire collection. Never construct an empty delete filter if a request supplies no criteria.

### 39.2. Hard Delete vs. Retention

Physical deletion may violate audit or legal-hold policies. Choose soft delete or archival per compliance requirements.

### 39.3. `deleteMany` Is Not All-or-Nothing

Each document deletion is atomic individually; `deleteMany` is not a multi-document transaction.

## 40. Soft Delete with `Updates`

~~~java
Bson filter = Filters.and(
    Filters.eq("_id", "p-003"),
    Filters.eq("tenantId", trustedTenantId),
    Filters.exists("deletedAt", false)
);

Bson update = Updates.combine(
    Updates.currentDate("deletedAt"),
    Updates.set("active", false)
);

products.updateOne(filter, update);
~~~

### 40.1. Default Read Filter

~~~java
Bson activeScope = Filters.and(
    Filters.eq("tenantId", trustedTenantId),
    Filters.exists("deletedAt", false)
);
~~~

### 40.2. Stick to One Convention

If active records store `deletedAt: null`, do not blindly apply `exists(false)`. Combining status + timestamp works if kept consistent everywhere.

### 40.3. Unique Indexes with Soft Delete

Soft-deleted records remain in standard unique indexes. To allow SKU reuse after soft deletion, use a partial unique index aligned with business policy.

### 40.4. Compliance

Soft deletion does not erase bytes on disk; records persist in the database and backups until purged per retention policy.

## 41. Tenant-Safe Repository Pattern

~~~java
public final class ProductRepository {
    private final MongoCollection<Document> products;

    public ProductRepository(
        MongoCollection<Document> products
    ) {
        this.products = products;
    }

    public Document findVisibleById(
        String trustedTenantId,
        String productId
    ) {
        Bson filter = Filters.and(
            Filters.eq(
                "tenantId", trustedTenantId
            ),
            Filters.eq("_id", productId),
            Filters.exists("deletedAt", false)
        );

        Bson projection = Projections.include(
            "sku", "name", "price", "stock"
        );

        return products.find(filter)
            .projection(projection)
            .first();
    }
}
~~~

### 41.1. Trusted Tenant

The tenant ID comes from verified auth middleware/service context—never directly from arbitrary client parameters.

### 41.2. Scope Writes and Deletes Too

Repositories often scope `find` yet forget `updateOne`/`deleteOne`. Enforce tenant scoping uniformly.

### 41.3. API Field Allowlist

Never return `Document.toJson()` containing internal metadata or secrets. Use DTOs and allowlisted projections.

### 41.4. Business-Oriented Repository Methods

Prefer `findVisibleById`, `reserveStock`, `transitionOrder`, and `softDelete` over endpoints accepting arbitrary MongoDB operators from clients.

## 42. Indexes for Filters and Sorts

Common query:

~~~java
Bson filter = Filters.and(
    Filters.eq("tenantId", trustedTenantId),
    Filters.eq("active", true)
);

Bson sort = Sorts.orderBy(
    Sorts.descending("createdAt"),
    Sorts.descending("_id")
);
~~~

Candidate index:

~~~javascript
db.products.createIndex({
  tenantId: 1,
  active: 1,
  createdAt: -1,
  _id: -1
});
~~~

### 42.1. Equality, Sort, Range

Compound index design commonly orders equality predicates, sort keys, and ranges, though optimal key order depends on real workload cardinality.

### 42.2. Unique Constraints

~~~javascript
db.products.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true }
);
~~~

Allows identical SKUs across different tenants while enforcing uniqueness within each tenant.

### 42.3. Indexes Have Costs

Every index consumes storage and write maintenance overhead. Never index every field indiscriminately.

## 43. Explaining Queries in Java

~~~java
import com.mongodb.ExplainVerbosity;

Document plan = products.find(
    Filters.and(
        Filters.eq("tenantId", trustedTenantId),
        Filters.eq("active", true)
    )
).sort(
    Sorts.descending("createdAt")
).explain(
    ExplainVerbosity.EXECUTION_STATS
);

System.out.println(plan.toJson());
~~~

Inspect:

- Winning plan.
- `IXSCAN` vs. `COLLSCAN`.
- Blocking `SORT`.
- `totalKeysExamined` / `totalDocsExamined`.
- `nReturned`.
- `executionTimeMillis`.

### 43.1. Index Usage Does Not Replace Security

An indexed query can still leak data if it omits the tenant predicate.

### 43.2. `explain` Is Not End-to-End Latency

Measure application, driver, network, and server load as well.

### 43.3. Tiny Datasets

With four sample products, `COLLSCAN` is normal. Benchmark on representative data volumes.

## 44. Cursors and Memory

~~~java
import com.mongodb.client.MongoCursor;

Bson filter = Filters.eq(
    "tenantId", trustedTenantId
);

try (MongoCursor<Document> cursor =
         products.find(filter).iterator()) {

    while (cursor.hasNext()) {
        Document doc = cursor.next();
        System.out.println(
            doc.getString("name")
        );
    }
}
~~~

### 44.1. Close Cursors

`try-with-resources` guarantees cursor closure upon completion or exception.

### 44.2. Never Load an Entire Collection into a `List`

Loading a million documents blows out the JVM heap. Use cursors, limits, or batch processing.

### 44.3. Timeouts and Cancellation

Align timeouts with SLOs, handle server selection/network failures, and stop streaming when HTTP clients disconnect.

### 44.4. Shared `MongoClient`

Creating/closing clients per request wastes resources and forfeits connection pooling.

## 45. POJO Codecs Instead of `Document`

You can define:

~~~java
public class Product {
    private String id;
    private String tenantId;
    private String sku;
    private String name;
    private long price;
    private int stock;

    public Product() {}

    // Getters/setters/annotations per POJO codec.
}
~~~

With a configured codec registry:

~~~java
MongoCollection<Product> products =
    db.getCollection("products", Product.class);
~~~

### 45.1. Builders Still Use BSON Field Names

~~~java
products.find(
    Filters.eq("tenantId", trustedTenantId)
);
~~~

When a Java property maps to a different BSON field name, builders must reference the stored BSON path.

### 45.2. POJOs Do Not Replace Database Validation

Other services, shells, or legacy jobs can still write mismatched types. Use MongoDB `$jsonSchema` validation.

### 45.3. `Decimal128` and `Date` Types

Keep money and timestamp codecs consistent across services and BSON storage.

## 46. `BulkWrite` and Transaction Boundaries

~~~java
import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.WriteModel;
import com.mongodb.client.model.BulkWriteOptions;

List<WriteModel<Document>> writes = List.of(
    new UpdateOneModel<>(
        Filters.eq("_id", "p-001"),
        Updates.inc("stock", 1)
    ),
    new UpdateOneModel<>(
        Filters.eq("_id", "p-002"),
        Updates.inc("stock", 1)
    )
);

products.bulkWrite(
    writes,
    new BulkWriteOptions().ordered(true)
);
~~~

### 46.1. Bulk Does Not Mean Multi-Document Atomicity

`bulkWrite` batches operations but is not all-or-nothing by default. Use a transaction when business invariants demand atomicity.

### 46.2. Ordered vs. Unordered

Configuration affects execution order and error handling. Never pick unordered when operations depend on sequence.

### 46.3. External Side Effects

MongoDB transactions do not include payment APIs, email, or object storage. Use outbox, idempotency, or saga patterns where needed.

## 47. Error Handling and Retries

| Error | Likely Cause | Approach |
| --- | --- | --- |
| Duplicate key | Unique index conflict | Handle conflict / conditional retry |
| Server selection timeout | Network / election / URI | SDAM logs, backoff |
| Write concern error | Acknowledgement not met | Verify commit state |
| Validation error | Invalid field/type | Fix input or schema |
| Unauthorized | Roles / credentials / TLS | Fix privileges |
| No match | Not found / tenant / state conflict | Return clear business outcome |
| Timeout after write | Outcome uncertain | Idempotency; never retry blindly |
| Cursor error | Network / slow query | Timeouts, indexes, resource cleanup |

### 47.1. Duplicate Key 11000

MongoDB duplicate key errors typically carry error code `11000`. Inspect driver exception types and error codes rather than brittle string matching.

### 47.2. Retryable Writes

The driver retries eligible writes under supported topologies/semantics. However, API-level workflow retries can double business side effects without an `operationId`.

### 47.3. Idempotency of `$inc`

An HTTP retry on a stock-increment endpoint can increment twice. Record business operations or idempotency keys when operations must be exactly-once.

### 47.4. Logging

Log trace IDs, tenant-safe identifiers, operation categories, latency, and error classes. Never log credentials, PII, or full documents.

## 48. Complete Combined Java Example

This small lab program combines `Filters`, `Projections`, `Sorts`, `Updates`, readback, and `UpdateResult`. Place it in a project configured with `mongodb-driver-sync` and `MONGODB_URI`.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;

import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import com.mongodb.client.model.Updates;
import com.mongodb.client.model.UpdateOptions;

import com.mongodb.client.result.UpdateResult;

import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Date;

public class CrudBuildersDemo {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                "MONGODB_URI is required"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase(
                "java_driver_crud_lab"
            );

            MongoCollection<Document> products =
                db.getCollection("products");

            String id = "demo-p-001";
            String tenant = "tenant-a";

            Bson identity = Filters.and(
                Filters.eq("_id", id),
                Filters.eq("tenantId", tenant)
            );

            Bson upsertUpdate = Updates.combine(
                Updates.set("name", "Demo Builders"),
                Updates.set("sku", "DEMO-001"),
                Updates.set("category", "demo"),
                Updates.set("price", 100),
                Updates.setOnInsert("stock", 10),
                Updates.setOnInsert(
                    "createdAt", new Date()
                )
            );

            products.updateOne(
                identity,
                upsertUpdate,
                new UpdateOptions().upsert(true)
            );

            Bson filter = Filters.and(
                Filters.eq("tenantId", tenant),
                Filters.eq("category", "demo"),
                Filters.gte("price", 50)
            );

            Bson projection = Projections.fields(
                Projections.include(
                    "sku", "name", "price", "stock"
                ),
                Projections.excludeId()
            );

            Bson sort = Sorts.orderBy(
                Sorts.ascending("price"),
                Sorts.ascending("sku")
            );

            products.find(filter)
                .projection(projection)
                .sort(sort)
                .limit(10)
                .forEach(doc ->
                    System.out.println(
                        "READ: " + doc.toJson()
                    )
                );

            UpdateResult result = products.updateOne(
                identity,
                Updates.combine(
                    Updates.inc("stock", 2),
                    Updates.currentDate("updatedAt")
                )
            );

            System.out.println(
                "matched=" + result.getMatchedCount()
                + ", modified=" + result.getModifiedCount()
            );

            Document after = products.find(
                identity
            ).first();

            if (after == null) {
                throw new IllegalStateException(
                    "Demo record not found"
                );
            }

            System.out.println(
                "AFTER: " + after.toJson()
            );

            // Cleanup optional in lab:
            // products.deleteOne(identity);
        }
    }
}
~~~

### 48.1. Repeatable Demo

Upserting by a stable `_id` inserts the record if absent. `setOnInsert(stock, 10)` does not reset `stock` on subsequent runs; each run still executes `$inc +2`, illustrating the difference between repeatable upserts and workflow increments.

### 48.2. Do Not Auto-Delete Records

The delete line is commented out because cleanup is a destructive write. Enable it only on an authorized lab database.

### 48.3. Demo Limitations

This demo omits auth middleware, DTO mapping, logging, metrics, retries, unique business indexes, and full integration tests.

## 49. Test Plan for CRUD Builders

At minimum, test:

1. Equality matching on exact fields.
2. Inclusive/exclusive range boundaries.
3. AND/OR boolean logic.
4. Missing vs. `null` behavior.
5. Nested dot paths.
6. `$elemMatch` on the same array element.
7. Tenant isolation with identical SKUs across tenants.
8. Projection `include`/`exclude` and `_id`.
9. Sorting with tie-breakers.
10. Offset and keyset pagination.
11. Atomic `$inc` under concurrent requests.
12. Conditional decrement preventing negative stock.
13. `matchedCount` and `modifiedCount`.
14. Upsert insert vs. update paths.
15. Unique indexes under concurrent upserts.
16. Version-based optimistic locking.
17. State transitions `PENDING → PAID`.
18. `arrayFilters` targeting the right elements.
19. Soft-deleted records excluded from public reads.
20. `deleteMany` bounded by tenant scope.
21. Cursor resource cleanup.
22. `explain`/index usage with representative data.

### 49.1. Test in an Isolated Environment

Never run insert/update/delete tests against production. Use a lab database, Testcontainers, or a dedicated staging environment.

### 49.2. Test Real Concurrency

When testing lost-update prevention, execute concurrent threads/requests and assert final stock/version; sequential tests cannot prove race safety.

### 49.3. Test Schema Edge Cases

Test missing `version`, string `price`, and `null` numeric fields to verify validation and failure handling.

## 50. Common Pitfalls

| Pitfall | Consequence | Prevention |
| --- | --- | --- |
| Concatenating raw JSON filters | Syntax/type bugs, injection risk | Builders + allowlists |
| Missing tenant filter | Cross-tenant read/modify/delete | Trusted auth scope |
| Querying `ObjectId` with a `String` | No matches | Match BSON type |
| Numeric field stored as `String` | Broken ranges/sorts | Schema validation |
| Assuming `eq(null)` matches only `null` | Also matches missing fields | `exists`/`type` checks |
| Assuming `ne`/`nin` requires field existence | Matches missing fields | Positive allowlists |
| Two array dot filters instead of `elemMatch` | Matches across two elements | `$elemMatch` |
| Not checking `first() == null` | `NullPointerException` | Not-found handling |
| Returning entire documents from API | Leaks internal fields | Projections + DTOs |
| Mixing include/exclude illegally | Query error | Consistent projection policy |
| Forgetting `_id` default behavior | Unexpected payload fields | `excludeId()` when needed |
| Sorting only by `createdAt` | Broken pagination on ties | Add `_id` tie-breaker |
| Huge `skip` offsets | Expensive scans | Keyset pagination |
| Sorting without supporting index | Blocking in-memory sort | Compound index/`explain` |
| Read-then-set `stock + 1` | Lost updates | `$inc` |
| Decrementing stock without `gte` filter | Negative stock | Conditional update |
| Setting entire `attributes` subdocument | Wipes sibling fields | Dot notation |
| `push` instead of `addToSet` | Duplicate array items | Pick right operator |
| Treating `addToSet` as collection-wide uniqueness | Duplicate SKUs | Unique index |
| Wrong `arrayFilters` identifier | Update fails or targets wrong element | Tests and stable IDs |
| `updateMany` missing tenant scope | Bulk corruption | Guardrails |
| Treating `modifiedCount=0` as not found | False not-found | Check `matchedCount` |
| Overly broad upsert filter | Modifies wrong document | Stable business identity |
| Missing unique index for concurrent upsert | Race duplicates | Compound unique index |
| Using `replaceOne` to edit one field | Loses unmapped fields | `Updates.set` |
| Retrying `$inc` workflow without idempotency | Double increment | Operation IDs |
| `deleteMany` with empty filter | Wipes entire collection | Scope checks / approval |
| Public reads forgetting soft-delete filter | Exposes deleted records | Shared scope helper |
| Testing only with admin account | Misses app permission bugs | Least privilege |
| Loading all results into a `List` | Memory pressure / OOM | Cursors and limits |
| Creating `MongoClient` per request | Resource overhead | Shared client |
| Ignoring `explain`/indexes | Degrades at scale | Benchmarking |
| Treating `bulkWrite` as a transaction | Partial changes | Transactions when needed |

## 51. Exercises on Filters

### Exercise 1 — Equality
Write a filter finding `tenant-a` products in category `books` with `active=true`. Identify the source of `trustedTenantId` in the backend.

### Exercise 2 — Range
Find products with `price` from `200000` to under `500000` and `stock > 0`.

### Exercise 3 — `in` / `nin`
Find orders in `PENDING` or `PAID`. Why might `nin(CANCELLED)` match documents missing `status`?

### Exercise 4 — Null and Missing
Write filters for `discount` missing vs. `discount` present and equal to `null`.

### Exercise 5 — Nested
Find `attributes.language = "vi"` and `edition >= 2`.

### Exercise 6 — Arrays
Find `tags` containing both `"java"` and `"backend"`. Compare `all` with `in`.

### Exercise 7 — `elemMatch`
An order has `BOOK-001` (`qty=1`) and `BOOK-002` (`qty=3`). What does an `$elemMatch` filter requiring the same item to have `BOOK-001` and `qty >= 2` return?

### Exercise 8 — Dynamic Filter
Design `buildProductFilter` accepting nullable `minPrice`/`maxPrice`/`category` while always enforcing `tenantId` and `deletedAt` filters.

## 52. Exercises on Projections and Sorts

### Exercise 9 — Include Fields
Return only `sku`, `name`, and `price`, excluding `_id`.

### Exercise 10 — Sensitive Fields
A customer API must never return `passwordHash`, `resetToken`, or `internalNotes`. Why are allowlist `include` + DTOs safer than blacklist `exclude`?

### Exercise 11 — Slice
Compare `Projections.slice("items", 2)` and `find.limit(2)`.

### Exercise 12 — Multi-Key Sort
Sort by `category` asc, `price` desc, `_id` asc. Why is a tie-breaker needed?

### Exercise 13 — Offset
Page 4, `pageSize` 25. Describe risks of large `skip` values and concurrent writes.

### Exercise 14 — Keyset
Sort by `createdAt` desc, `_id` desc. Write the next-page filter given `lastCreatedAt` and `lastId`.

### Exercise 15 — Index
Propose a compound index for filtering `tenantId`, `active` and sorting `createdAt` desc, `_id` desc; verify with `explain`.

## 53. Exercises on Updates

### Exercise 16 — Lost Update
Two threads read `stock=10` and both write `stock=11`. Why is this broken? Rewrite using `$inc`.

### Exercise 17 — Conditional Stock
Decrement `stock` by 4 only if `stock >= 4`, product is active, and tenant matches. Handle `matchedCount=0`.

### Exercise 18 — Dot Path
Update only `attributes.language` without losing `edition`.

### Exercise 19 — `combine`
Atomically set `name`, `currentDate("updatedAt")`, and increment `version`.

### Exercise 20 — Array Updates
Add tag `"java"` if missing, append unconditionally, and remove tag `"legacy"`. Choose among `addToSet`/`push`/`pull`.

### Exercise 21 — ArrayFilters
Update `qty` for item `BOOK-002` in an order using `$[item]` and `UpdateOptions`.

### Exercise 22 — Upsert
Use `tenantId + sku` as identity, set `price`/`name`, and `setOnInsert("createdAt")`. Which unique index is required?

### Exercise 23 — CAS
Two users edit a document at `version=5`. Write the filter and update incrementing `version`. What must the second user handle?

### Exercise 24 — State Transition
Transition an order from `PENDING` to `PAID` only when currently `PENDING`. Why is omitting the `status` filter dangerous?

### Exercise 25 — `findOneAndUpdate`
Decrement `stock` by 1 if in stock and return the post-update `stock` using `ReturnDocument.AFTER`.

## 54. Exercises on CRUD and Performance

### Exercise 26 — Integration CRUD
In the lab, insert a record, run `find`/projection, update, read back, and delete. Assert all outcomes.

### Exercise 27 — `replaceOne`
A replacement document includes only `_id`/`name`/`price`. Which older fields can be lost, and when should `Updates.set` be used instead?

### Exercise 28 — `deleteMany`
Why is an empty filter dangerous? Design safeguards requiring `tenantId` and previewing affected rows.

### Exercise 29 — Soft Delete
Design a `deletedAt`-missing convention, default repository filters, and SKU uniqueness after soft deletion.

### Exercise 30 — Count
Compare `countDocuments(filter)` and `estimatedDocumentCount` when counting products per tenant.

### Exercise 31 — Explain
On 1 million records, a range + sort query has high p95 latency. Use winning plan, docs examined, `nReturned`, and indexes to diagnose.

### Exercise 32 — Concurrency
Run 100 concurrent `Updates.inc` calls and compare final stock against expected. Repeat with read-then-set to observe the race condition.

### Exercise 33 — Retry
An HTTP request times out after `$inc` already committed. Why can retrying the whole business request increment twice? Design an idempotency key.

### Exercise 34 — Cursor
Stream 1 million products incrementally without loading everything into the heap, using `MongoCursor` and `try-with-resources`.

### Exercise 35 — Transaction
An order decrements stock for two products and inserts a booking. Why aren't two `updateOne` calls automatically all-or-nothing? When is a multi-document transaction required?

## 55. Production Readiness Checklist for CRUD

1. MongoDB URI and secrets are managed securely.
2. `MongoClient` is reused across requests.
3. Driver and server versions are compatible.
4. `Bson`/`Document`/POJO codecs match the schema.
5. Field names and BSON types are consistent.
6. Every read, update, and delete enforces tenant/authorization scope.
7. Clients cannot submit raw arbitrary BSON predicates.
8. Optional filters are validated.
9. Null, missing, `ne`, and `nin` semantics are tested.
10. Arrays use `$elemMatch` whenever matching the same element.
11. Public APIs use allowlisted projections.
12. DTOs never expose unauthorized secrets or PII.
13. Sorts include deterministic tie-breakers.
14. Page sizes and offsets are bounded.
15. Keyset cursors validate types and tenant scope.
16. `$inc` or conditional updates prevent read-then-write races.
17. Stock and state invariants live inside the update filter.
18. Optimistic locking via `version` protects concurrent edits.
19. `updateOne` vs. `updateMany` matches intent.
20. `matchedCount` and `modifiedCount` are interpreted properly.
21. Upserts use stable identities and unique indexes.
22. `replaceOne` is avoided when editing only a few fields.
23. `arrayFilters` are thoroughly tested.
24. `deleteMany` has strict guardrails.
25. Soft-delete conventions are applied consistently.
26. Multi-document transactions are used when all-or-nothing is required.
27. External side effects use idempotency or outbox patterns.
28. Policies handle duplicate keys, timeouts, and network/election errors.
29. Cursors are always closed.
30. Indexes are benchmarked with `explain`.
31. Read/write concerns match durability and SLOs.
32. Logs never expose credentials or PII.
33. Integration, concurrency, and security tests exist.
34. Bulk modifications have backup and rollback plans.

## 56. Builders Quick Reference Table

| Need | Builder / API |
| --- | --- |
| Equality | `Filters.eq` |
| Inequality | `Filters.ne` |
| Range | `Filters.gt`/`gte`/`lt`/`lte` |
| Boolean AND/OR | `Filters.and`/`or` |
| Set membership | `Filters.in`/`nin` |
| Field existence | `Filters.exists` |
| Same array element | `Filters.elemMatch` |
| Array contains all values | `Filters.all` |
| Regex | `Filters.regex` |
| Include specific fields | `Projections.include` |
| Exclude fields | `Projections.exclude` |
| Exclude `_id` | `Projections.excludeId` |
| Combine projections | `Projections.fields` |
| Limit array output | `Projections.slice` |
| Sort ascending | `Sorts.ascending` |
| Sort descending | `Sorts.descending` |
| Multi-key sort | `Sorts.orderBy` |
| Set field | `Updates.set` |
| Atomic increment/decrement | `Updates.inc` |
| Remove field | `Updates.unset` |
| Rename field | `Updates.rename` |
| Current timestamp | `Updates.currentDate` |
| Combine operators | `Updates.combine` |
| Array append | `Updates.push` |
| Array unique append | `Updates.addToSet` |
| Array remove | `Updates.pull` |
| Set only on upsert insert | `Updates.setOnInsert` |
| Update one document | `updateOne` |
| Update many documents | `updateMany` |
| Update and return document | `findOneAndUpdate` |
| Insert if unmatched | `UpdateOptions.upsert` |
| Delete documents | `deleteOne`/`deleteMany` |

## 57. Conclusion

**Filters, Projections, Sorts, and Updates** form the core toolkit for expressing MongoDB CRUD operations in the Java Sync Driver:

- **Filters** select documents based on predicates. Master null/missing semantics, ranges, arrays, and above all **tenant authorization**.
- **Projections** limit returned fields. Pair allowlist `include` with DTOs to trim payloads and prevent leaking sensitive data.
- **Sorts** define output ordering. Add tie-breakers and prefer keyset pagination for large collections.
- **Updates** describe server-side mutations. Server-side `$inc`, conditional filters, version compare-and-set, and `arrayFilters` eliminate race conditions and accidental subdocument overwrites.
- **`MongoCollection` CRUD methods** execute the operation, while builders provide the BSON expressions passed into those methods.

Production-grade CRUD code goes beyond simply making statements run without exceptions. It must **prevent lost concurrent updates, avoid modifying the wrong documents, enforce tenant isolation, avoid unindexed slow queries, and handle retries and errors cleanly**. By mastering builders, data modeling, indexes, and write semantics together, engineers can build Java repositories that stay readable, concurrent-safe, and scalable as data grows.

## References

- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [MongoDB Java Sync Driver — Query Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)
- [MongoDB Java Sync Driver — Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/)
- [MongoDB Java Sync Driver — Delete Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/delete-documents/)
- [MongoDB Manual — Query Predicates](https://www.mongodb.com/docs/manual/reference/operator/query/)
- [MongoDB Manual — Update Operators](https://www.mongodb.com/docs/manual/reference/operator/update/)
- [MongoDB Manual — Projection](https://www.mongodb.com/docs/manual/tutorial/project-fields-from-query-results/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Single-Document Atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
