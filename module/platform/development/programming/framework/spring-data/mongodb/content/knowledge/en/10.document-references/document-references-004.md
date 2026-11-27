# Customizing Lookups and Reference Value Converters

In **Spring Data MongoDB**, documents can link via an identifier value instead of embedding all data. The `@DocumentReference` mechanism supports storing references as an **ID**, a **business value**, or a **small BSON document containing multiple fields**. The key point is keeping both directions aligned: **the value written to the source document** and **the query used to find the target document**.

In default mode, `@DocumentReference` stores the ID of the referenced object and uses that ID to look up the object. When you need to reference by publisher code, external system code, a composite tenant–code key, or a reverse lookup from another collection, you can customize `lookup` and use a **writing converter returning `DocumentPointer`**. This capability belongs to the Spring Data MongoDB mapping layer; MongoDB Server still executes queries, indexes, and aggregations.

This lesson belongs to the **Document References** chapter of the `SPRING_DATA_MONGODB` module. After this lesson, you will be able to:

- Explain `@DocumentReference`, `lookup`, `#target`, `#self`, and how Spring Data reads references.
- Customize references by **a key other than `_id`** and register a `Converter<TargetType, DocumentPointer<...>>` to write the right value.
- Use **document-shaped pointers** for composite keys; create **reverse references** with `@ReadOnlyProperty`.
- Distinguish `@DocumentReference`, `@DBRef`, manual ID references, and `$lookup`.
- Choose indexes, control BSON types, manage consistency, handle lazy loading, account for reactive limitations, and test against real data.

## 1. From Default References to Custom Lookups

Suppose an application manages books and publishers. One publisher is used by many books and has an independent lifecycle, so it is typically stored in a separate collection:

```javascript
// publishers
{ _id: "PUB-001", code: "NXB-A", name: "Publisher A" }

// books
{ _id: "BOOK-001", title: "Learning MongoDB", publisher: "PUB-001" }
```

With default mapping:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.DocumentReference;

@Document(collection = "publishers")
public record Publisher(
        @Id String id,
        String code,
        String name
) {}

@Document(collection = "books")
public class Book {
    @Id
    private String id;

    private String title;

    @DocumentReference
    private Publisher publisher;

    protected Book() {}

    public Book(String id, String title, Publisher publisher) {
        this.id = id;
        this.title = title;
        this.publisher = publisher;
    }

    public Publisher getPublisher() {
        return publisher;
    }
}
```

In the default configuration, the reference value of `publisher` is taken from `Publisher.id`. On read, Spring Data issues a query equivalent to:

```javascript
db.publishers.findOne({ _id: "PUB-001" });
```

The default lookup is conceptually:

```java
@DocumentReference(lookup = "{ '_id' : ?#{#target} }")
```

Here `#target` is the **reference value stored in the `books` document**, such as `"PUB-001"`. Spring Data uses the target type's metadata to resolve it into `Publisher` when loading `Book`. References are loaded **eagerly by default**; `lazy = true` only defers the query until accessed.

**Remember:** `@DocumentReference` does not create a MongoDB foreign key and **does not cascade saves**. You must save `Publisher` separately before referencing it. If the target object is deleted, the application must decide whether to allow orphan references, hide the link, reject deletion, or keep historical snapshots.

### 1.1. Comparing Link Representations

| Approach | Value in source document | Who loads the related object? |
| --- | --- | --- |
| `String publisherId` field | Plain ID, e.g., `"PUB-001"` | Service manually calls repository, `MongoTemplate`, or aggregation |
| Default `@DocumentReference` | Target entity's ID | Spring Data resolves reference when reading entity |
| `@DocumentReference(lookup = ...)` | ID, another scalar, or document pointer per mapping | Spring Data builds filter from `lookup` |
| `@DBRef` | BSON DBRef structured with `$ref` and `$id` | Spring Data DBRef resolver |
| `$lookup` aggregation | Does not define storage format; uses existing fields | MongoDB Server performs the join inside pipeline |

When you need tight control over query counts or related datasets can be very large, **manual IDs and batch loading** may fit better than an auto-resolved object field.

## 2. Understanding `lookup`, `#target`, and `#self` Syntax

`lookup` accepts a **string representing a BSON/JSON query**. Spring Data evaluates SpEL placeholders before sending the query to MongoDB Server. Some patterns:

| Expression | Meaning |
| --- | --- |
| `"{ '_id' : ?#{#target} }"` | Matches target document's `_id` against stored pointer value |
| `"{ 'code' : ?#{#target} }"` | Finds by business code `code` using scalar pointer |
| `"{ 'tenantId' : ?#{tenant}, 'externalCode' : ?#{code} }"` | Extracts `tenant` and `code` from a document-shaped pointer |
| `"{ 'publisherId' : ?#{#self._id} }"` | Finds target documents by source document's `_id` when building a reverse reference |

- **`#target`:** the pointer being read, i.e., the actual stored value of the reference field. If it is a document, you can access subfields of the pointer.
- **`#self`:** the source document being mapped; commonly used for **reverse references** that do not store an ID array on the source side.
- **`?#{...}`:** SpEL evaluation placeholder. Keep the value type consistent with the target field's BSON type, especially between `String` and `ObjectId`.

Never concatenate user input directly into annotation strings to build dynamic queries. `lookup` is **static mapping configuration**; for filters that vary per request, use `MongoTemplate`/repositories or aggregations and parameterize values at the business layer.

## 3. Main Example: Referencing Publisher by `code`

Suppose `Publisher.id` is strictly internal, while `code` such as `"NXB-A"` is the stable key that books store. Desired layout:

```javascript
// Collection: publishers
{ _id: "PUB-001", code: "NXB-A", name: "Publisher A" }

// Collection: books
{ _id: "BOOK-001", title: "Learning MongoDB", publisher_code: "NXB-A" }
```

When reading `Book.publisher`, the application should query:

```javascript
db.publishers.findOne({ code: "NXB-A" });
```

And when writing `Book`, the application must store **`Publisher.code`**, not `Publisher.id`.

### 3.1. Declaring Read Mapping

Keep `Publisher` as in section 1. In `Book`, replace the `publisher` field declaration with:

```java
import org.springframework.data.mongodb.core.mapping.DocumentReference;
import org.springframework.data.mongodb.core.mapping.Field;

@Field("publisher_code")
@DocumentReference(lookup = "{ 'code' : ?#{#target} }")
private Publisher publisher;
```

`@Field("publisher_code")` controls the **BSON field name in `books`**. `lookup` controls **how `publishers` is searched**. They are two separate concepts: omitting `@Field` stores the property as `publisher`, yet lookups by `code` are still governed by `lookup`.

Adding only `lookup` as above **is not enough** to ensure `"NXB-A"` is written. Spring Data cannot infer from the `#target` expression that it should extract `Publisher.code` instead of `Publisher.id`; you must define the write side.

### 3.2. Writing a `DocumentPointer` Converter

`DocumentPointer<T>` represents the **value that will be stored** as the pointer. To store a code string instead of an ID:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.mongodb.core.mapping.DocumentPointer;

@WritingConverter
public class PublisherPointerConverter
        implements Converter<Publisher, DocumentPointer<String>> {

    @Override
    public DocumentPointer<String> convert(Publisher source) {
        if (source.code() == null || source.code().isBlank()) {
            throw new IllegalArgumentException(
                    "Publisher code must be set before creating a reference");
        }
        return () -> source.code();
    }
}
```

The key point is that the **converter's return type** is `DocumentPointer<String>`: its `getPointer()` method (expressed as a lambda) returns the exact string `"NXB-A"`. Spring Data stores this string in `books.publisher_code`. On read, `#target` receives `"NXB-A"` and the query searches for `publishers.code == "NXB-A"`.

`@WritingConverter` specifies that the converter applies in the **write direction**. It is **not** a direct `String → Publisher` converter; Spring Data reads the `Publisher` entity from the document returned by the lookup query. Do not mechanically create bidirectional converters unless there is a clear requirement and well-defined rules.

### 3.3. Registering the Converter So Spring Data Actually Uses It

Merely declaring the `PublisherPointerConverter` class or adding `@WritingConverter` **is not enough**: the converter must be registered with `MongoCustomConversions` or the project's equivalent converter configuration mechanism. Example with Java configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;

@Configuration
public class MongoReferenceConfiguration {

    @Bean
    public MongoCustomConversions mongoCustomConversions() {
        return MongoCustomConversions.create(adapter ->
                adapter.registerConverter(new PublisherPointerConverter()));
    }
}
```

The example above illustrates a project with no other custom converters declared. If the application **already has** a `MongoCustomConversions` bean or an `AbstractMongoClientConfiguration` setup, **register the new converter within the existing configuration** so you do not discard other converters and conversion rules. Exact configuration syntax depends on the Spring Data MongoDB / Spring Boot version used by your project.

You can consult the official documentation on document references at:
`https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/document-references.html`.

### 3.4. Save the Target First, Then Save the Source

Example in a service with `MongoTemplate` injected:

```java
Publisher publisher = mongoTemplate.insert(
        new Publisher("PUB-001", "NXB-A", "Publisher A"));

mongoTemplate.insert(
        new Book("BOOK-001", "Learning MongoDB", publisher));
```

After writing, inspect raw BSON in `mongosh`:

```javascript
db.books.findOne(
  { _id: "BOOK-001" },
  { _id: 1, publisher_code: 1 }
);
// Expected: { _id: "BOOK-001", publisher_code: "NXB-A" }
```

Do not expect the full `Publisher` object to be embedded in `books`. When reading back via `mongoTemplate.findById("BOOK-001", Book.class)`, Spring Data uses `lookup` and restores `Book.publisher` to the saved `Publisher` object.

Saving `Book` **does not automatically create or update `Publisher`**. Explicitly sequence saves and define how to handle cases where `code` does not exist yet, changes, or is duplicated.

## 4. Customizing a BSON Document Pointer

A scalar string is only sufficient when there is **a single unique lookup key**. In a multi-tenant system, the same `externalCode` may appear across different tenants. Searching solely by `externalCode` could return data from the wrong tenant.

Suppose:

```javascript
// suppliers
{ _id: "SUP-1", tenantId: "TENANT-A", externalCode: "ABC",
  name: "Supplier A" }
{ _id: "SUP-2", tenantId: "TENANT-B", externalCode: "ABC",
  name: "Supplier B" }
```

The application wants each product to store a two-property pointer:

```javascript
// products
{
  _id: "PROD-1",
  name: "Work desk",
  supplier_ref: { tenant: "TENANT-A", code: "ABC" }
}
```

### 4.1. Mapping by Two Fields

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "suppliers")
public record Supplier(
        @Id String id,
        String tenantId,
        String externalCode,
        String name
) {}
```

In the `Product` entity, declare:

```java
import org.springframework.data.mongodb.core.mapping.DocumentReference;
import org.springframework.data.mongodb.core.mapping.Field;

@Field("supplier_ref")
@DocumentReference(
        lookup = "{ 'tenantId' : ?#{tenant}, "
               + "'externalCode' : ?#{code} }")
private Supplier supplier;
```

`tenant` and `code` in SpEL are **fields inside the pointer document**, equivalent to accessing `#target.tenant` and `#target.code`. Spring Data constructs a filter with both conditions; MongoDB Server evaluates the match on both fields.

### 4.2. Writing Converter Returning `DocumentPointer<Document>`

This is an **independent example** from `PublisherPointerConverter` in section 3. A `Supplier` object is converted into a small BSON document:

```java
import org.bson.Document;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.mongodb.core.mapping.DocumentPointer;

@WritingConverter
public class SupplierPointerConverter
        implements Converter<Supplier, DocumentPointer<Document>> {

    @Override
    public DocumentPointer<Document> convert(Supplier source) {
        return () -> new Document("tenant", source.tenantId())
                .append("code", source.externalCode());
    }
}
```

Register alongside other converters in `MongoCustomConversions`:

```java
return MongoCustomConversions.create(adapter -> {
    adapter.registerConverter(new PublisherPointerConverter());
    adapter.registerConverter(new SupplierPointerConverter());
});
```

This is an **illustrative method body from a configuration class**, not a standalone complete Java class. Validate that `tenantId`/`externalCode` inputs are valid and stable before creating references. For composite keys, indexes should match the query:

```javascript
db.suppliers.createIndex(
  { tenantId: 1, externalCode: 1 },
  { unique: true }
);
```

A unique index on the pair of fields prevents **ambiguous** references when two documents in the same tenant share the same code. If legacy data already contains duplicates, resolve them before creating the index.

### 4.3. Pointers with Additional Filter Conditions

You can add filters in `lookup`, such as loading only active suppliers:

```java
@DocumentReference(
        lookup = "{ 'tenantId' : ?#{tenant}, "
               + "'externalCode' : ?#{code}, 'active' : true }")
private Supplier supplier;
```

When `active = false`, the entity document still exists, yet **the lookup does not return** that supplier. Clarify expected business behavior: the linked field may remain unresolved even though the ID/code is still valid. Enforcing tenant access control in the service layer remains necessary; **filtering tenant in `lookup` does not replace authorization**.

## 5. Reverse References: `#self` and `@ReadOnlyProperty`

The source document does not always store a pre-built list of pointers. For example, each book has `publisherId`, but one publisher can have **millions of books**. You should not maintain an unbounded `bookIds` array inside the `publishers` document.

You can create a query-only property on the `Publisher` side:

```java
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.ReadOnlyProperty;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.DocumentReference;

@Document(collection = "publishers")
public class PublisherWithBooks {
    @Id
    private String id;

    private String code;

    @ReadOnlyProperty
    @DocumentReference(
            lookup = "{ 'publisherId' : ?#{#self._id} }",
            sort = "{ 'title' : 1 }")
    private List<BookWithPublisherId> books;

    public List<BookWithPublisherId> getBooks() {
        return books;
    }
}

@Document(collection = "books")
class BookWithPublisherId {
    @Id
    private String id;

    private String title;
    private String publisherId;
}
```

With data:

```javascript
// publishers
{ _id: "PUB-001", code: "NXB-A" }

// books
{ _id: "BOOK-001", title: "Java", publisherId: "PUB-001" }
{ _id: "BOOK-002", title: "MongoDB", publisherId: "PUB-001" }
```

When Spring Data loads `PublisherWithBooks`, the expression `#self._id` reads the ID from the current `publishers` document, then finds `BookWithPublisherId` documents where `publisherId == "PUB-001"`. `@ReadOnlyProperty` ensures the `books` property **is not written as a pointer array into the publisher document**. It is a link **inferred on read**.

To support the lookup on the server:

```javascript
db.books.createIndex({ publisherId: 1, title: 1 });
```

**Important risk:** `List<BookWithPublisherId>` is a reference collection resolved on access, **not a paginated API**. If a publisher has millions of books, loading the entire list is inappropriate. Instead, keep only `publisherId` on `Book` and query with pagination:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface BookWithPublisherIdRepository
        extends MongoRepository<BookWithPublisherId, String> {

    Page<BookWithPublisherId> findByPublisherId(
            String publisherId, Pageable pageable);
}
```

In a standard API, you can use `findByPublisherId("PUB-001", PageRequest.of(0, 20))`. When total counts are unnecessary, a `Slice` or keyset pagination strategy can reduce counting/`skip` overhead. The choice depends on record volume, page style, and actual queries.

### 5.1. Why Must BSON Types Match?

Suppose `publishers._id` is actually stored as BSON `ObjectId`, whereas `books.publisherId` is a BSON `String` containing 24 hex characters. Those two values **are not equal** in MongoDB; a reverse query using `#self._id` may return an empty list.

With `@Id String id`, Spring Data MongoDB can convert a valid 24-hex string to a BSON ObjectId when writing the ID, whereas a plain String field like `publisherId` remains a BSON String. Therefore, you must **standardize BSON types** across IDs and reference keys—do not look only at Java types or displayed text.

One way to eliminate ambiguity for business IDs is using `@MongoId String id` on documents explicitly stored with String `_id`, or using `ObjectId` on both sides. If existing data already has mismatched types, changing annotations is not enough: controlled inspection and migration are required.

## 6. Loading References: Eager, Lazy, Query Counts, and Ordering

### 6.1. Default Eager and Lazy Option

`@DocumentReference` resolves references **eagerly by default**. You can defer via:

```java
@DocumentReference(lazy = true)
private Publisher publisher;
```

When lazy, Spring Data sets up deferred resolution and executes the query when the related object is accessed. This can reduce work for requests that only need `Book.title` and not `Publisher.name`.

However, lazy has costs:

- Accessing the property inside a loop can trigger many extra reads, leading to **N+1 queries**.
- Logging, debuggers, JSON serializers, or `toString()` can accidentally trigger data loading.
- Proxies can hit restrictions from Java classes, `final` types, constructors, and JDK module accessibility, especially on Java 16+.
- Accessing lazy properties after closing a processing lifecycle or switching contexts can cause unexpected behavior that must be tested in the real application.

Do not pick `lazy` simply because the annotation looks “lighter”; verify round trips and real endpoint needs.

### 6.2. Reference Collections and Ordering

If a field is declared as `List<Publisher>` or `List<Book>` with `@DocumentReference`, Spring Data can combine collection lookups using the **`$or`** operator to load links in groups. The framework attempts to restore the original order per lookup where possible. For non-equality filters or complex criteria, **do not rely on automatic order restoration**; when needed, specify:

```java
@DocumentReference(
        lookup = "{ 'publisherId' : ?#{#self._id} }",
        sort = "{ 'title' : 1 }")
private List<BookWithPublisherId> books;
```

`sort` here is applied to the server-side query. A long linked list still incurs substantial overhead even when sorted; for true pagination, use repository queries or `MongoTemplate` with `limit`/`Pageable`.

### 6.3. When Is Manual Loading Better?

Suppose a page displays 40 books, each with a publisher. If each object read triggers a separate lookup, many network queries can occur. If only publisher names are needed, an alternative is:

1. Query the 40 books and collect unique publisher codes.
2. Use `PublisherRepository.findByCodeIn(...)` to load publishers in a single batch by codes.
3. Build a `code → publisher` map and assemble data in the service.

Or design a `$lookup` aggregation if appropriate:

```javascript
db.books.aggregate([
  { $match: { active: true } },
  { $limit: 40 },
  {
    $lookup: {
      from: "publishers",
      localField: "publisher_code",
      foreignField: "code",
      as: "publisherDetails"
    }
  }
]);
```

`$lookup` runs on MongoDB Server; `@DocumentReference` is resolved by Spring Data during object mapping. The two approaches have different execution models, so neither is unconditionally faster. Compare query plans, returned document counts, network bytes, and server load on realistic data.

## 7. Indexes, Stable Keys, and Consistency

When customizing `lookup` to search by a field other than `_id`, ask yourself:

1. **Is the lookup field unique?** If each code is expected to point to exactly one publisher, a unique index is a useful constraint.
2. **Can the field change?** Changing `code` in the target document will cause old pointers to stop matching unless you run a process to update sources.
3. **Do BSON types match?** `"123"` (String) and `123` (Number) differ; the same holds for hex String vs. ObjectId.
4. **Are there additional status or tenant filters?** Every condition in `lookup` needs a matching index and business policy.
5. **How large are record counts and query rates?** Measure before choosing eager/lazy or a combined query.

Example using `code` as the key:

```javascript
db.publishers.createIndex({ code: 1 }, { unique: true });

db.publishers.find({ code: "NXB-A" })
  .explain("executionStats");
```

If legacy data has duplicate codes, creating the unique index will fail. Clean the data and design how code changes are handled before deploying. Using a human-readable code as a reference can be convenient, but it turns **renaming a business code** into a link change. For fields that change frequently, an immutable technical ID is usually a more durable pointer.

### 7.1. References Do Not Automatically Provide Transactions

A `Book` pointing to a `Publisher` does not prevent someone from deleting that `Publisher`. Likewise, changing a publisher's code and updating thousands of books does not become atomic simply because `@DocumentReference` is used.

If business logic requires cross-document consistency, design appropriate write operations:

- Disallow code changes, or use immutable IDs.
- Keep a historical publisher name snapshot in `Book` when generating invoices or statements.
- For operations that truly require multi-document commit/rollback, consider **MongoDB transactions** on a supported deployment with the proper Spring Data transaction manager.
- For bulk data changes, plan migrations, transitional states, retries, and link reconciliation.

Do not rely on `@DocumentReference` for “cascading saves” or relational-style foreign key enforcement.

### 7.2. Diagnosing an Unresolved Reference

A sensible diagnostic order:

1. Read the **raw BSON** of the source document: is the pointer `"NXB-A"` or `"PUB-001"`?
2. Check the **actual lookup query**: does it search by `code`, `_id`, or `tenantId`/`externalCode`?
3. Run the equivalent query in `mongosh` to see whether it returns 0, 1, or multiple results.
4. Compare the **BSON types** of the pointer and target field; inspect `@Id`/`@MongoId` and converters.
5. Verify the converter is **registered**; do not just check that the annotation exists in code.
6. Verify actual BSON field names when using `@Field`, soft-delete/active conditions, and indexes.
7. If an issue only occurs during serialization or logging, check for unintended lazy proxy triggers.

Do not log full documents containing sensitive data in production just to debug; log redacted query keys, query counts, timings, and error types instead.

## 8. Limitations with Reactive Access

Spring Data MongoDB provides `ReactiveMongoTemplate` and `ReactiveMongoRepository` for non-blocking I/O. However, **according to the Spring Data MongoDB 4.5 and 5.1 documentation, reading `@DocumentReference` is not supported in the reactive infrastructure**. Do not assume a `@DocumentReference` field will be resolved automatically in a reactive flow just because the repository returns `Mono`/`Flux`.

If your application is reactive, a clear approach is **storing codes/IDs manually** and explicitly querying the target collection with `ReactiveMongoTemplate` or a reactive repository:

```java
import reactor.core.publisher.Mono;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// BookRow holds a publisherCode field instead of @DocumentReference.
public Mono<Publisher> loadPublisher(
        ReactiveMongoTemplate template,
        String publisherCode
) {
    Query query = Query.query(
            Criteria.where("code").is(publisherCode));
    return template.findOne(query, Publisher.class);
}
```

This is an **illustrative method inside a service**, which must be placed in an appropriate Java class. For multiple items, organize batching/queries/aggregations properly so you do not introduce N+1 inside `Flux`. Check the documentation for the **exact Spring Data version** your project uses, as framework capabilities may evolve.

Never call blocking `MongoTemplate` on a reactive event loop as a workaround for reference resolution. Reactive programming only changes the I/O orchestration model; it does not create indexes or reduce MongoDB Server query counts.

## 9. Testing Mappings and Custom Lookups on Real MongoDB

Unit tests calling `PublisherPointerConverter.convert(...)` directly verify the pointer output, yet **do not prove** Spring Data registered the converter, wrote the right BSON, or can load the publisher via the real lookup. Write **integration tests** against an isolated MongoDB test instance—such as Testcontainers—using `@DataMongoTest` and your converter configuration.

### 9.1. Testing Both Write and Read Paths

The example below uses `Publisher`, `Book`, `PublisherPointerConverter`, and `MongoReferenceConfiguration` defined in sections 1 and 3. Note when integrating: `Book` must use the `@Field("publisher_code") @DocumentReference(lookup = ...)` declaration from section 3.1 rather than the default `@DocumentReference`.

```java
import static com.mongodb.client.model.Filters.eq;
import static org.assertj.core.api.Assertions.assertThat;

import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
@Import(MongoReferenceConfiguration.class)
class CustomDocumentReferenceTest {

    @Autowired
    MongoTemplate template;

    @Test
    void storesCodePointerAndResolvesPublisher() {
        Publisher publisher = template.insert(
                new Publisher("PUB-101", "NXB-TEST", "Test Publisher"));

        template.insert(
                new Book("BOOK-101", "MongoDB Testing", publisher));

        // Read raw BSON without going through Book mapping.
        Document rawBook = template.getCollection("books")
                .find(eq("_id", "BOOK-101"))
                .first();

        assertThat(rawBook).isNotNull();
        assertThat(rawBook.getString("publisher_code"))
                .isEqualTo("NXB-TEST");
        assertThat(rawBook.containsKey("publisher")).isFalse();

        // Verify the lookup query resolves into Publisher.
        Book loaded = template.findById("BOOK-101", Book.class);
        assertThat(loaded).isNotNull();
        assertThat(loaded.getPublisher()).isNotNull();
        assertThat(loaded.getPublisher().code()).isEqualTo("NXB-TEST");
        assertThat(loaded.getPublisher().id()).isEqualTo("PUB-101");
    }
}
```

**Important:** `@DataMongoTest` only sets up the test slice and required MongoDB components; it **does not guarantee a MongoDB Server exists** in every environment. Provide a real MongoDB test instance with a dedicated database and clean data between tests. `@Import` brings the lesson's converter configuration into the test. If your project already has a custom converter configuration, use that instead of creating a conflicting `MongoCustomConversions` bean.

This test verifies simultaneously:

1. **Write path:** raw BSON contains `publisher_code: "NXB-TEST"`.
2. **Read path:** `lookup` by `code` finds the right `Publisher`.
3. **No embedding:** the book document does not contain the entire `publisher` object.
4. **No ID confusion:** the pointer is not `"PUB-101"`.

### 9.2. Edge Cases to Test

| Test case | Data | Outcome to evaluate |
| --- | --- | --- |
| Valid and unique code | One `Publisher` with `code = "NXB-A"` | Lookup resolves the exact object |
| Converter not registered | Book written with mapping missing converter | Raw BSON test reveals wrong value or write error; reading entities alone is insufficient |
| Publisher code changes | Book still holds old pointer | Define pointer update policy, alias retention, or immutable ID usage |
| Two publishers share the same code | Legacy data violates uniqueness | Unique index/migration prevents ambiguous reference results |
| Publisher was deleted | Pointer remains in book | Unresolved link behavior follows business rules |
| Pointer has mismatched BSON type | String at source, ObjectId at target | Lookup does not auto-coerce types; caught by raw test |
| Composite tenant–code key | Two tenants share the same code | Must never return a publisher from another tenant |
| Reverse lookup for many books | `publisherId` stored on book | `@ReadOnlyProperty` does not write a book array into publisher |
| Lazy reference | Fetch only book title then access publisher | Determine when queries fire and detect any N+1 |
| Book from legacy import | Different field name or pointer shape | Check compatibility and migration strategy |

### 9.3. Checking Indexes and Queries on MongoDB Server

For custom lookups finding publishers by code:

```javascript
db.publishers.getIndexes();

db.publishers.find({ code: "NXB-TEST" })
  .explain("executionStats");
```

Inspect `totalDocsExamined`, `totalKeysExamined`, plan type, and result count. On tiny collections, MongoDB Server may pick `COLLSCAN` even when an index exists; to evaluate performance, generate test data large enough and close to production distribution.

For composite keys, also verify:

```javascript
db.suppliers.find({
  tenantId: "TENANT-A",
  externalCode: "ABC"
}).explain("executionStats");
```

This query must match the BSON types of the written `tenant`/`code` pointer. When results differ from expectations, inspect raw data and indexes before turning up debug logs.

## 10. Common Mistakes When Customizing References

| Mistake | Symptom | Fix |
| --- | --- | --- |
| Changing `lookup` to `code` without changing pointer writes | Book still stores `publisherId`; lookup by `code` finds nothing | Create a `DocumentPointer` writing converter or align lookup expression with stored data |
| Converter class exists but is not registered | BSON keeps default format or fails to write | Register via `MongoCustomConversions` and verify with raw BSON test |
| Defining a new `MongoCustomConversions` bean that drops existing converters | `Decimal128`, date, or other custom type mappings change | Merge new converter into the existing configuration |
| Looking up by a non-unique key | One code matches multiple target documents | Add a unique index or change key; clean duplicates first |
| Target key changes frequently | Orphan pointers after renaming codes | Use an immutable ID or manage migrations/snapshots |
| `String` and `ObjectId` mismatch | `#self._id` yields ObjectId while target field is String | Standardize BSON types; test raw queries |
| Overusing lazy inside loops | Query count and latency spike | Batch IDs, use repository queries/aggregations, or adjust DTOs |
| Putting an unbounded list in a reverse reference | One request loads thousands/millions of objects | Paginate by source key; never load the whole collection |
| Treating `@DocumentReference` as a foreign key | Deleting target document leaves dangling pointers | Build deletion/reconciliation policy; use transactions if truly required |
| Assuming reactive auto-resolves references | Reactive entity reads lack expected behavior | Use explicit IDs/codes and reactive queries per supported version |
| Assuming references enforce permissions | Returns publisher/supplier from the wrong tenant | Enforce authorization independently with clear boundaries |

## 11. Practice Exercise: Linking by Partner Code

A sales system receives data from multiple suppliers. Each supplier has a `partnerCode`; the code is unique only **within a single tenant**. A product belongs to one supplier, yet the product page does not need supplier details on every request.

Data:

```javascript
// suppliers
{ _id: "S1", tenantId: "T-A", partnerCode: "P-7",
  name: "Unit A", active: true }
{ _id: "S2", tenantId: "T-B", partnerCode: "P-7",
  name: "Unit B", active: true }

// products
{ _id: "PR-1", tenantId: "T-A", name: "Work desk",
  supplierRef: { tenant: "T-A", code: "P-7" } }
```

Requirements:

1. Declare `@DocumentReference` so `supplierRef` resolves using both `tenantId` and `partnerCode`.
2. Write a `@WritingConverter` returning `DocumentPointer<Document>` with two fields, `tenant` and `code`.
3. Specify which unique index `suppliers` should have and explain why indexing only `partnerCode` is insufficient.
4. Propose how to display supplier names for 100 products without triggering N+1 queries.
5. Analyze what happens when a supplier is deactivated (`active = false`) or changes `partnerCode`.

Reference solution:

```java
@DocumentReference(lookup =
        "{ 'tenantId' : ?#{tenant}, 'partnerCode' : ?#{code} }")
private Supplier supplier;
```

And the writing converter:

```java
@WritingConverter
class SupplierReferenceConverter
        implements Converter<Supplier, DocumentPointer<Document>> {

    @Override
    public DocumentPointer<Document> convert(Supplier supplier) {
        return () -> new Document("tenant", supplier.tenantId())
                .append("code", supplier.partnerCode());
    }
}
```

In the snippet above, `Supplier` is the exercise's illustrative class having `tenantId()` and `partnerCode()` methods; declare/import types when placing into a real project. Do not register multiple converters with the same source/target types without a clear strategy, as converter selection can become ambiguous. Appropriate index to ensure a unique lookup key:

```javascript
db.suppliers.createIndex(
  { tenantId: 1, partnerCode: 1 },
  { unique: true }
);
```

To display 100 products, you can collect the required `(tenantId, partnerCode)` pairs and query `suppliers` in batch, or use a `$lookup` aggregation with matching data types; comparing performance rather than defaulting to eager/lazy is best.

In this example, if partner codes can change, consider using a stable `_id` or maintaining an alias/mapping table. `@DocumentReference` does not automatically update old pointers.

## 12. Project Adoption Checklist

Before using custom document references, answer:

1. **What pointer is stored?** ID, business String, or multi-field BSON document?
2. **Which target fields must `lookup` search?** `_id`, `code`, or a composite key?
3. **Is the write layer configured?** If using a scalar or composite key other than ID, is the `DocumentPointer` converter registered?
4. **Is there a uniqueness constraint on the lookup key?** Must a pointer resolve to one exact entity?
5. **Are BSON types consistent?** Especially `@Id String` versus `ObjectId` and regular reference fields.
6. **Does the relationship need pagination or batch loading?** Will eager/lazy or `List` trigger too many round trips?
7. **What are the source of truth and link lifecycle?** How are code changes, entity deletions, and historical data handled?
8. **Are there multi-tenant, authorization, or sensitive-data requirements?** `lookup` does not replace access control.
9. **Is the app blocking or reactive?** Does your Spring Data version support reading document references in that stack?
10. **Has it been tested on real MongoDB?** Did you verify raw BSON, lookup results, indexes, missing/duplicate data, and query counts?

**Key takeaway:** `@DocumentReference.lookup` defines **how to read** a link; `Converter<TargetType, DocumentPointer<...>>` defines **the pointer value written**. `#target` refers to the reference value stored in the document, while `#self` supports reverse lookups from the source document. Any configuration is only trustworthy when **BSON types match on both ends, lookup keys are properly indexed, the converter is registered, and read/write behavior is verified against real MongoDB**.

### References

- [Spring Data MongoDB — Using Document References](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/document-references.html): `@DocumentReference`, `lookup`, `DocumentPointer`, reverse lookups, and performance notes.
- [Spring Data MongoDB — Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html): registration mechanism and writing/reading converter conventions.
