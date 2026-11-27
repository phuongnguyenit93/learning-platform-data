# Comparing Application References, DBRef, DocumentReference, and $lookup

## 1. The Document Linking Problem in MongoDB

In the **Document References** chapter of **Spring Data MongoDB**, we must decide how to represent and retrieve relationships between two documents residing in different collections. For example, a book belongs to an author, with a document in the `authors` collection:

~~~json
{
  "_id": "author-7",
  "name": "Nguyen An",
  "country": "VN"
}
~~~

And a document in the `books` collection:

~~~json
{
  "_id": "book-42",
  "title": "Practical MongoDB",
  "status": "PUBLISHED",
  "authorId": "author-7"
}
~~~

If a book list screen only needs the author's name, the application has several options:

1. **Application-managed reference** (*manual/application reference*): store `authorId`, then explicitly query the `authors` collection.
2. **`@DBRef`**: store a special DBRef structure (with `$ref` and `$id`), letting Spring Data assist in resolving it when reading objects.
3. **`@DocumentReference`**: by default stores the target document's ID as a concise reference and lets Spring Data resolve it using mapping metadata.
4. **`$lookup`**: executes a collection join inside an **aggregation pipeline** on the MongoDB server when results need combined data from both collections.

Core insight: **the first three are ways to store or represent references in the data model; `$lookup` is a query operation**. A system storing `authorId` can readily combine data using `$lookup` without needing `@DBRef` or `@DocumentReference`.

This article targets Java 17+, Spring Boot 3.x, and Spring Data MongoDB 4.x. Exact APIs around lazy loading, mapping, and configuration may vary across versions; verify against your project's actual dependencies.

## 2. Comparison Table of the Four Options

| Criterion | Application reference | `@DBRef` | `@DocumentReference` | `$lookup` |
|---|---|---|---|---|
| Typical stored format | `authorId: "author-7"` | `author: { "$ref": "authors", "$id": "author-7" }` | `author: "author-7"` by default | Does not dictate storage format |
| Who joins the data? | Service/repository code | Spring Data's reference resolver mechanism | Spring Data's reference resolver mechanism | MongoDB server via aggregation |
| Java representation | Separate ID and independently queried object, manually assembled | Property mapped as target entity | Property mapped as target entity | Pipeline output as projection/DTO |
| Control over load timing | Explicit | Can be eager/lazy | Can be eager/lazy | When aggregation runs |
| Batching capability | Explicitly collect IDs and query `$in` | Depends on resolver behavior and reference shape | Depends on resolver behavior and mapping config | Server executes join in pipeline |
| Custom link conditions | Defined by application | Follows stored DBRef | Supports custom `lookup` in annotation | Flexible with `localField`/`foreignField` or pipeline |
| When preferred | Safe default, clear query count | Compatibility with existing DBRef data | Want object-typed property with simple reference storage | Searches/reports needing server-side joined data |
| Primary risks | Boilerplate query code, forgetting to batch | Hidden reads, N+1, DBRef structure | Hidden reads, N+1, reliance on resolution mechanism | Complex pipelines, join/sort/memory overhead |

No option is universally faster or better. Round trips, indexes, payload sizes, read frequency, consistency models, and testability matter far more than annotation names.

### Decision Flow

~~~mermaid
flowchart TD
    A["Need to link data across collections"] --> B{"Only need to store ID and control loading manually?"}
    B -->|"Yes"| C["Application reference + batch as needed"]
    B -->|"No"| D{"Returning lists or reports joining multiple collections?"}
    D -->|"Yes"| E["$lookup aggregation + projection + indexes"]
    D -->|"No"| F{"Want Java property to be an object resolved by Spring Data?"}
    F -->|"Yes"| G{"Existing schema already uses DBRef?"}
    G -->|"Yes"| H["Use @DBRef, plan migration if needed"]
    G -->|"No"| I["Consider @DocumentReference"]
    F -->|"No"| C
    C --> J["Measure query count, latency, and check missing targets"]
    E --> J
    H --> J
    I --> J
~~~

## 3. Shared Source Model

The following examples define author and book in package `com.example.library`. In the examples, IDs are stored as **BSON Strings** for easy comparison across options; real applications may choose `ObjectId` or another type if used consistently.

**Author.java**

~~~java
package com.example.library;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "authors")
public class Author {
    @MongoId(FieldType.STRING)
    private String id;
    private String name;
    private String country;

    public Author() {}

    public Author(String id, String name, String country) {
        this.id = id;
        this.name = name;
        this.country = country;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getCountry() { return country; }
    public void setCountry(String country) { this.country = country; }
}
~~~

**Book.java** — model storing an application reference:

~~~java
package com.example.library;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "books")
public class Book {
    @MongoId(FieldType.STRING)
    private String id;
    private String title;
    private String status;
    private String authorId;

    public Book() {}

    public Book(String id, String title, String status, String authorId) {
        this.id = id;
        this.title = title;
        this.status = status;
        this.authorId = authorId;
    }

    public String getId() { return id; }
    public String getTitle() { return title; }
    public String getStatus() { return status; }
    public String getAuthorId() { return authorId; }
}
~~~

In the examples, we share the `authors` collection across relationship styles while using separate `books`, `books_dbref`, and `books_docref` collections to observe BSON differences. This is strictly for learning; real systems do not need three collections storing the same books.

## 4. Application Reference: Storing Keys and Querying Explicitly

With the `Book` model, MongoDB simply stores `authorId` as a regular field:

~~~json
{
  "_id": "book-42",
  "title": "Practical MongoDB",
  "status": "PUBLISHED",
  "authorId": "author-7"
}
~~~

Spring Data does not automatically load the author when querying `Book` because there is no reference annotation. This is a helpful property: **reading books never unexpectedly triggers extra author reads**.

Define two repositories:

~~~java
package com.example.library;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface BookRepository extends MongoRepository<Book, String> {
    List<Book> findByStatus(String status);
}
~~~

~~~java
package com.example.library;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface AuthorRepository extends MongoRepository<Author, String> {
}
~~~

### 4.1. Simple Approach: Load Each Referenced Object

~~~java
Book book = bookRepository.findById("book-42").orElseThrow();
Author author = authorRepository.findById(book.getAuthorId())
        .orElseThrow();
~~~

These are two read operations. This fits a detail screen showing a single book. If a list displays 100 books and code calls `findById` per book, query count can reach **1 + N** (*N+1 query problem*), adding significant latency even when every query uses an index.

### 4.2. Optimizing Lists: Collect IDs and Batch

Instead of loading authors one by one, fetch the book list first, collect unique `authorId`s, and fetch authors in one batch:

~~~java
package com.example.library;

public record BookView(String id, String title, String authorName) {
}
~~~

~~~java
package com.example.library;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;

@Service
public class BookViewService {
    private final BookRepository books;
    private final AuthorRepository authors;

    public BookViewService(BookRepository books, AuthorRepository authors) {
        this.books = books;
        this.authors = authors;
    }

    public List<BookView> published() {
        List<Book> results = books.findByStatus("PUBLISHED");

        Set<String> authorIds = results.stream()
                .map(Book::getAuthorId)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());

        Map<String, Author> byId = new HashMap<>();
        authors.findAllById(authorIds).forEach(
                author -> byId.put(author.getId(), author));

        return results.stream()
                .map(book -> {
                    Author author = byId.get(book.getAuthorId());
                    return new BookView(
                            book.getId(),
                            book.getTitle(),
                            author == null ? null : author.getName());
                })
                .toList();
    }
}
~~~

You can usually fetch authors with `_id in (...)` instead of one query per book. For very large ID sets, **paginate and chunk batches** rather than passing an entire catalog into a massive `$in`. The snippet deliberately expresses a missing-author policy: return `authorName = null`. In real applications, you might throw a data error, display a snapshotted author name, or hide the book depending on business rules.

**Pros:** simple BSON, easy to use with drivers/aggregations, full query control, easy to cache or batch per use case. **Cons:** services must organize link loading and handle missing references manually.

## 5. @DBRef: Referencing in DBRef Format

MongoDB has a DBRef convention representing references as documents containing fields such as `$ref` (collection name), `$id` (target document ID), and sometimes `$db` (database name). Spring Data MongoDB supports mapping this with `@DBRef`.

**BookDbRef.java**:

~~~java
package com.example.library;

import org.springframework.data.mongodb.core.mapping.DBRef;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "books_dbref")
public class BookDbRef {
    @MongoId(FieldType.STRING)
    private String id;
    private String title;
    @DBRef(lazy = true)
    private Author author;

    public BookDbRef() {}

    public BookDbRef(String id, String title, Author author) {
        this.id = id;
        this.title = title;
        this.author = author;
    }

    public String getId() { return id; }
    public String getTitle() { return title; }
    public Author getAuthor() { return author; }
}
~~~

For an author with `_id = "author-7"`, the stored BSON reference looks like:

~~~json
{
  "_id": "book-dbref-42",
  "title": "Practical MongoDB",
  "author": {
    "$ref": "authors",
    "$id": "author-7"
  }
}
~~~

`@DBRef` stores **reference metadata**, without embedding the full `Author` document. When materializing the `author` property, Spring Data uses DBRef metadata to locate the target document.

### 5.1. Eager and Lazy

- `@DBRef` **without `lazy = true`**: during document mapping, Spring Data normally resolves the reference right away (*eager*).
- `@DBRef(lazy = true)`: the framework attempts to defer querying the target document until the proxy is accessed.

Example:

~~~java
BookDbRef book = mongoTemplate.findById(
        "book-dbref-42", BookDbRef.class);

// Accessing author can trigger reference resolution.
String authorName = book.getAuthor().getName();
~~~

On some Java/module setups, creating lazy proxies may hit access restrictions or type incompatibilities; test on your target JDK and Spring Data version. Calling `toString()`, inspecting objects in a debugger, or serializing to JSON can also touch the proxy and trigger extra queries.

**Do not treat lazy as free.** If you loop over 100 books and call `getAuthor().getName()`, the system can still run many extra queries. Some collection-reference resolution paths can batch queries in favorable situations, yet never assume batching always occurs.

### 5.2. DBRef Does Not Manage Relationships Like a Foreign Key

`@DBRef` does not cause MongoDB to create a foreign key constraint. If the author is deleted, the DBRef can remain in the book; depending on mapping and access path, the target document may fail to resolve.

Spring Data MongoDB also **does not cascade-save by default** for objects referenced via `@DBRef`. Save `Author` first or via its own flow. Similarly, deleting `BookDbRef` should not automatically delete an `Author` shared by many books.

DBRef is useful when a project **already stores data in DBRef format**, needs compatibility with legacy collections, or specifically requires that integration format. Without such constraints, simple ID references are usually easier to manage.

## 6. @DocumentReference: Spring Data Managed References

`@DocumentReference` maps a property as a related object without **forcing the DBRef structure**. Under default behavior, Spring Data MongoDB can store the **target document's ID** and use that ID to query on read.

**BookDocRef.java**:

~~~java
package com.example.library;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.DocumentReference;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "books_docref")
public class BookDocRef {
    @MongoId(FieldType.STRING)
    private String id;
    private String title;
    @DocumentReference(lazy = true)
    private Author author;

    public BookDocRef() {}

    public BookDocRef(String id, String title, Author author) {
        this.id = id;
        this.title = title;
        this.author = author;
    }

    public String getId() { return id; }
    public String getTitle() { return title; }
    public Author getAuthor() { return author; }
}
~~~

Illustrative BSON with default reference settings:

~~~json
{
  "_id": "book-docref-42",
  "title": "Practical MongoDB",
  "author": "author-7"
}
~~~

Compared to `@DBRef`, this representation is concise and avoids storing `$ref` and `$id` on every reference. It still requires **additional queries when resolving the property**; `@DocumentReference` does not convert reading a book into a server-side `$lookup`.

### 6.1. Customizing Lookup and Writing

With `@DocumentReference`, mapping can specify a `lookup` expression to match target documents by a non-`_id` key, such as a **guaranteed-unique** natural code. Keep in mind that customizing `lookup` only tells Spring Data **how to search**; **what value is written** depends on the mapping's writing/reference-value rules.

For instance, if you want to store an author's `externalCode` instead of ID, explicitly design how the reference is emitted on write and resolved by `lookup` on read. Never swap annotations over existing ID-stored data expecting old values to turn into codes automatically.

Attributes like `lazy` share the same caveats as DBRef: a property looks like a plain Java object, yet invoking getters can trigger I/O queries. Avoid letting bulk entity serialization silently trigger many reads. In REST APIs, clear DTOs/projections are safer than returning entities holding lazy references.

### 6.2. A Collection of Multiple References

When a post has multiple tags:

~~~java
@DocumentReference(lazy = true)
private java.util.List<Tag> tags;
~~~

This illustrates **a property inside an entity**; `Tag` must be a properly mapped type. Under default reference settings, the source document can store a list of IDs instead of embedding each `Tag`.

Verify how Spring Data resolves collection references, handles missing tags, and orders results. **Java list order should not be assumed always preserved** across resolution changes or multi-object queries unless specifically guaranteed. When display order matters, model explicit positions or sort rules.

### 6.3. No Automatic Cascades or Referential Integrity

Like `@DBRef`, `@DocumentReference` does not turn MongoDB into a foreign-key database. When an author is deleted, book documents can still carry the stale ID. Likewise, saving a book does not automatically ensure the author is saved or updated in the same transaction.

**When to choose:** you want a domain model allowing `book.getAuthor()`, prefer simple reference storage, and accept Spring Data's resolution mechanics. **When to reconsider:** you need strict control over query counts, list-API latency, or shared MongoDB access across multiple languages/frameworks with clear query conventions.

## 7. $lookup: Joining Collections Directly on MongoDB Server

`$lookup` is a MongoDB aggregation pipeline stage that joins documents from a target collection. With `books.authorId` and `authors._id`, an equality lookup generally behaves like a **left outer join**: each book receives an array of matching authors, or an empty array if none match.

~~~javascript
db.books.aggregate([
  { $match: { status: "PUBLISHED" } },
  {
    $lookup: {
      from: "authors",
      localField: "authorId",
      foreignField: "_id",
      as: "authorDocs"
    }
  },
  {
    $unwind: {
      path: "$authorDocs",
      preserveNullAndEmptyArrays: true
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      authorName: "$authorDocs.name"
    }
  }
]);
~~~

Stage-by-stage breakdown:

1. `$match` filters to published books only. Filtering early typically reduces how many documents enter the join.
2. `$lookup` finds documents where `authors._id = books.authorId` and attaches them to the `authorDocs` array.
3. `$unwind` flattens the array into a single element. `preserveNullAndEmptyArrays: true` keeps books without a matching author; omitting it drops such books from output.
4. `$project` returns only the fields needed by the screen, avoiding sending whole author documents unnecessarily.

In this example, `authors._id` is unique so each book matches at most one author. If joining on a non-unique field, `$lookup` can return multiple matches and `$unwind` multiplies output rows. Check cardinality before choosing projections.

### 7.1. Implementing with MongoTemplate and Aggregation

Create a DTO:

~~~java
package com.example.library;

public record BookWithAuthor(
        String title,
        String authorName) {
}
~~~

Service building the aggregation:

~~~java
package com.example.library;

import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.stereotype.Service;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

@Service
public class BookAggregationService {
    private final MongoTemplate mongo;

    public BookAggregationService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<BookWithAuthor> publishedWithAuthors() {
        Aggregation pipeline = newAggregation(
                match(org.springframework.data.mongodb.core.query.Criteria
                        .where("status").is("PUBLISHED")),
                lookup("authors", "authorId", "_id", "authorDocs"),
                unwind("authorDocs", true),
                project("title")
                        .and("authorDocs.name").as("authorName"));

        return mongo.aggregate(
                pipeline, "books", BookWithAuthor.class)
                .getMappedResults();
    }
}
~~~

This is an explicit pipeline in `MongoTemplate`. Field names in `lookup(...)` match the stored BSON directly. If entities rename fields via `@Field` or the pipeline uses raw BSON stages, verify field-name mapping at each stage and test against real data.

`@Aggregation` on repositories can also declare fixed pipelines; doing so **does not turn `@DBRef` and `@DocumentReference` into `$lookup`**. Choose between repository `@Aggregation` and `MongoTemplate` based on code organization and pipeline dynamism.

### 7.2. Pipeline-Form $lookup and Limits

MongoDB also supports pipeline-form `$lookup` with `let` and `pipeline` to join on complex conditions, filter, or project target documents during the join. Index usage for join expressions, data limits, and `$lookup` behavior can depend on MongoDB version, pipeline structure, index types, and topology.

Never assume every join optimizes like an RDBMS join. Measure **input document counts, joined document counts, sorts, latency, and intermediate memory/disk usage**, and run `explain` in an appropriate environment. When book result sets are large, use `$match`, `$sort`, `$skip`/`$limit`, lean projections, and indexes properly.

**Pros:** single server-side pipeline, convenient for reporting DTOs or filtering across fields from multiple collections. **Cons:** long pipelines can be hard to read/debug, 1-to-many joins multiply rows, and it does not solve missing reference data or business consistency by itself.

## 8. Latency, N+1, and Indexes

Choose APIs based on actual query counts and result shapes:

| Scenario | Recommended approach | What to measure |
|---|---|---|
| View details of one book and author | Store `authorId`, query on demand; or reference if suitable | 1–2 round trips, caching, access timing |
| List 50–100 books with author names | Batch IDs or `$lookup` | Round trips, payload size, p95 latency, indexes |
| Aggregate report by author country | `$lookup` + `$group`, or read model | Stage count, docs examined, memory |
| Historical record must never change display name | Store snapshot of name at business event time | Historical accuracy, source mutations |
| Many screens only need author ID | Application reference, skip resolution | Avoid querying unused data |
| Active legacy DBRef collection | Keep `@DBRef`, optimize access or plan migration | N+1, compatibility, migration |

Foundational indexes:

~~~javascript
// MongoDB creates a unique index on _id by default.
db.books.createIndex({ authorId: 1 });
db.books.createIndex({ status: 1, authorId: 1 });
~~~

`books.authorId` helps find all books by an author; joining on `authors._id` uses the `_id` index on `authors`. The compound `{ status, authorId }` index is only a candidate; sorting needs and selectivity determine the best index. Do not create both indexes everywhere without measuring write overhead.

When using default `@DocumentReference` where field `author` holds the ID, reverse queries by ID may need an index on `books_docref.author`. With DBRef, reference storage differs; inspect the actual BSON field before creating indexes or raw queries.

**N+1 is not solely a relational ORM problem.** Lazy references in MongoDB can also cause many round trips. Count actual commands via the MongoDB profiler, command monitoring, or approved observability tools rather than guessing from concise-looking Java code.

## 9. Data Consistency and Reference Lifecycle

MongoDB does not create foreign key constraints just because an ID, DBRef, or DocumentReference exists. Links can become **dangling** when targets are deleted, moved across collections, or migrated.

### 9.1. Save in Order and Validate Existence

Suppose you create a book referencing an author:

1. Verify the author exists and the caller is permitted to use that author.
2. Save the book with a stable author ID.
3. On read, define policy when the author no longer exists: return null, business error, preserve snapshot, or hide the book.

“Check existence then save book” as **two separate operations** does not give absolute integrity: the author could be deleted in between. If an invariant must hold atomically across documents, design appropriate sessions/transactions on a supported MongoDB topology, or choose a data model where invariants are easier to enforce.

### 9.2. No Default Cascade-Save

With `@DBRef` and `@DocumentReference`, **authors are not automatically saved** when calling `bookRepository.save(book)`. Developers must persist target objects according to aggregate boundaries and business rules. Do not extrapolate JPA cascading behavior onto MongoDB.

### 9.3. When Should You Embed Instead of Reference?

If an address, purchase price, or receipt metadata must remain historically fixed, usually embed a *snapshot* inside the business document, because reading current source data would rewrite history. If an author updates their name and every book must show the new name, referencing may be more appropriate.

An entity can keep both a live reference and snapshot fields:

~~~json
{
  "_id": "order-line-1",
  "productId": "p-7",
  "titleAtPurchase": "500 ml Water Bottle",
  "unitPriceVndAtPurchase": 129000
}
~~~

Never overwrite `titleAtPurchase` when the product renames; that is a finalized transaction record. Data policy follows business semantics, not annotations.

## 10. Reactive Access and Reference Loading Boundaries

Spring Data MongoDB provides `ReactiveMongoTemplate` and `ReactiveMongoRepository` for *non-blocking* streams. When choosing how to represent links in a reactive application:

- Explicit ID references combined with deliberate reactive queries (using `Flux`/`Mono` and batching) keep I/O timing under control.
- `$lookup` aggregations can run via `ReactiveMongoTemplate`, returning reactive publishers.
- Never assume lazy proxies from reference annotations automatically turn into reactive I/O; check reference resolver support for your exact Spring Data MongoDB version and driver type.
- Avoid calling synchronous APIs or `block()` directly on the WebFlux event loop.

If data needs multiple links loaded together, design **read models/DTOs** and verify query counts early. Returning raw entities carrying lazy references from controllers can cause hard-to-observe extra queries and serialization hazards.

## 11. Testing the Four Options on Real MongoDB

In Spring Boot 3.x, `@DataMongoTest` helps test repository/template mapping, yet does not start a MongoDB server by itself. Use an isolated test MongoDB (such as via Testcontainers) to verify **actual BSON**, reference resolution, and aggregation queries.

Example testing raw stored data for two reference styles (assuming entities save to separate collections):

~~~java
package com.example.library;

import static com.mongodb.client.model.Filters.eq;
import static org.assertj.core.api.Assertions.assertThat;

import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class ReferenceMappingTest {
    @Autowired
    MongoTemplate mongo;

    @Test
    void distinguishesDocumentReferenceFromDbRef() {
        Author author = new Author("author-7", "Nguyen An", "VN");
        mongo.save(author);

        mongo.save(new BookDocRef(
                "book-docref-42", "Practical MongoDB", author));
        mongo.save(new BookDbRef(
                "book-dbref-42", "Practical MongoDB", author));

        Document docRef = mongo.getCollection("books_docref")
                .find(eq("_id", "book-docref-42"))
                .first();
        Document dbRef = mongo.getCollection("books_dbref")
                .find(eq("_id", "book-dbref-42"))
                .first();

        assertThat(docRef).isNotNull();
        assertThat(dbRef).isNotNull();
        assertThat(docRef.get("author")).isEqualTo("author-7");
        assertThat(dbRef.get("author")).isNotEqualTo("author-7");

        BookDocRef restored =
                mongo.findById("book-docref-42", BookDocRef.class);
        assertThat(restored).isNotNull();
        assertThat(restored.getAuthor().getName())
                .isEqualTo("Nguyen An");
    }
}
~~~

This test illustrates expected behavior when default references store String IDs; verify raw BSON on your exact version. For `@DBRef`, the driver/framework may represent raw data as a `com.mongodb.DBRef` object or a document with `$ref`/`$id` components; avoid casting everything to one Java class without checking how the driver deserializes it.

Other important tests:

1. **Manual reference:** create books with `authorId`, verify query counts when reading one book and many books; confirm batching avoids N+1.
2. **DBRef/DocumentReference:** test eager and lazy; check exact query execution timing, serialization, and proxies on your deployment JDK.
3. **Dangling reference:** delete an author and read a book; verify error/null handling rather than assuming targets always exist.
4. **Aggregation:** test `$lookup` with books that have authors, lack authors, and multiple filters; verify `$unwind` with and without preserving missing matches.
5. **Performance:** measure p95 latency, command counts, total BSON transferred, and `explain("executionStats")` at realistic data scale.
6. **Migration:** moving from DBRef to plain IDs or DocumentReference requires reading legacy data during transition and verifying migrated documents.
7. **Concurrency:** create/delete target documents concurrently with referencing documents; test transactional or eventual-consistency policies.

## 12. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
Thinking `@DBRef` runs a server-side join | Actually issues extra reads | Measure query counts; use `$lookup` when server-side joins are needed |
Thinking `@DocumentReference` is a shorthand DBRef with identical BSON | Broken schema migrations, unresolved references | Inspect raw BSON and understand reference formats |
Reading a list then calling lazy getters in a loop | N+1 round trips | Batch IDs, use DTOs/read models, or aggregate |
Swapping `@DBRef` to `@DocumentReference` without migrating data | Legacy data stays `$ref`/`$id`, breaking new mapping | Plan migration or read compatibility |
Assuming references act as foreign keys | Deleting an author leaves broken references in books | Define deletion policies, validation, and reconciliation |
Assuming saving a book cascade-saves the author | Missing target documents on read | Explicitly save aggregates/targets |
1-to-many join followed by `$unwind` without checking cardinality | Multiplies output rows, spikes memory | Check cardinality, filter early, project tightly |
Transferring huge BSON payloads just to display a name | Higher network load and latency | Project only needed fields and paginate properly |
Using String IDs while one side stores BSON ObjectId | References fail to match despite looking identical | Standardize `@Id`/`@MongoId` and BSON types |
Returning lazy entities directly in REST responses | Serialization triggers unexpected I/O | Use DTOs populated with explicit link loading |
Using `$lookup` for every query | Complex pipelines, ignoring indexes/write costs | Compare against ID batching, projections, and embedding per workload |

## 13. Applied Exercises

**Exercise 1 — Compare BSON.** Create one `Author`, then save three book variants: plain `authorId`, `@DBRef`, and `@DocumentReference`. Use MongoDB shell or the Java driver to read raw BSON. Explain why the three storage forms are not equivalent and why changing annotations requires migration.

**Exercise 2 — Spot N+1.** Seed 100 books across 10 authors. Measure MongoDB commands when iterating and reading author names via lazy references. Rewrite the list view by collecting IDs and calling `findAllById`, then re-measure round trips.

**Exercise 3 — Write a $lookup.** From a `books` collection containing `authorId`, write an aggregation returning `title` and `authorName` for published books. Handle deleted authors, comparing outputs with `preserveNullAndEmptyArrays` enabled versus disabled.

**Exercise 4 — Evaluate Indexes.** Create appropriate indexes for finding books by author and status. Run `explain("executionStats")` on a sufficiently large dataset; record keys examined, docs examined, execution time, and payload sizes comparing batching versus `$lookup`.

**Exercise 5 — Consistency Rules.** In an ordering system, classify which information must be snapshotted at purchase time and which should reference live entities. Propose policies when a target document is deleted, changes ID, or is out of sync.

## 14. Key Takeaways

**Application references** store transparent IDs and give the application full control over when data is loaded. **`@DBRef`** uses the DBRef format, fitting data already stored under that convention. **`@DocumentReference`** supports flexible reference mapping, storing simple IDs in BSON by default and resolving into object properties. **`$lookup`** is a server-side MongoDB aggregation join that works directly with regular ID-based fields.

With Spring Data MongoDB, base your choice on **query count, BSON shape, required output fields, latency, indexes, lifecycle, and consistency requirements**. None of these options automatically creates foreign keys or cascade-saves. For list queries, guard against N+1; for aggregations, inspect query plans; for all reference types, test raw BSON and missing-target policies.
