# @Version, Optimistic Locking, and Conflict Handling in Spring Data MongoDB

A MongoDB document can be read and edited concurrently by multiple users, requests, or Spring Boot application instances. For example, two staff members open an edit form for the same article. The first user edits the title and clicks Save; the second user, still holding the stale data, edits the body and clicks Save. If both requests overwrite the **entire document** in arrival order at the server, the first user's change vanishes without any warning.

In the **Spring Data MongoDB** chapter of the **Database Engine Document MongoDB** module, **"@Version, Optimistic Locking, and Conflict Handling"** explains how to use the `@Version` annotation to detect and prevent **lost updates**, how version-checked conditional writes work, how to return errors in APIs, when to retry, and the boundaries of this mechanism with other update paths, multi-document transactions, and external business side effects.

After this lesson, you will be able to:

1. Identify **read–modify–write** scenarios that cause lost updates.
2. Map a version field using `org.springframework.data.annotation.Version`.
3. Understand why Spring Data checks **`_id` plus `version`** when saving an existing entity.
4. Handle `OptimisticLockingFailureException` instead of silently overwriting someone else's changes.
5. Pass **`expectedVersion`** from clients to detect stale forms across HTTP requests.
6. Apply compare-and-set (CAS) using `MongoTemplate.updateFirst()` or `findAndModify()` when avoiding full-document saves.
7. Distinguish version checking from atomic updates, unique indexes, pessimistic locks, and MongoDB transactions.
8. Design retries, conflict resolution, auditing, migrations, monitoring, and concurrency tests.

> **Scope:** Examples assume Spring Boot with Spring Data MongoDB and a MongoDB replica set or standalone lab supporting the illustrated operations. APIs, initial version values, codecs, and error outcomes may vary by Spring Data version. Code snippets are learning exercises—run them in a test environment rather than modifying production data directly.

## 1. What Is a Lost Update?

Suppose the `articles` collection contains:

```javascript
{
  _id: "article-1001",
  title: "MongoDB Basics",
  body: "Initial content"
}
```

Two users open the same article:

```text
Time            User A                      User B
   |
   |       GET article-1001
   |       title = "MongoDB Basics"
   |       body  = "Initial content"
   |
   |                                    GET article-1001
   |                                    title = "MongoDB Basics"
   |                                    body  = "Initial content"
   |
   |       edits title to
   |       "Advanced MongoDB"
   |
   |       SAVES full document
   |       -> succeeds
   |
   |                                    edits body to
   |                                    "New CRUD example"
   |
   |                                    SAVES stale full document
   |                                    -> succeeds
   |
   v

Possible outcome:
  title = "MongoDB Basics"      <-- User A's edit is lost
  body  = "New CRUD example"
```

The issue is not that MongoDB applied two concurrent writes to one document non-atomically. **Each single-document write remains atomic in MongoDB.** The bug arises because **the business operation includes a prior read before the write**, and the second write relies on a stale snapshot.

### Lost Updates Differ from Duplicate Key Errors

- **Duplicate key:** two operations insert values violating a unique index.
- **Lost update:** a valid change is overwritten by an older read snapshot.
- **Write conflict:** a conflict raised at the database/transaction layer.
- **Optimistic locking failure:** the application detects that the version a client intended to update is no longer current.

These can occur in the same system, yet they represent distinct concepts.

## 2. Solution: Attach a Version to Every Document

Add a `version` field:

```javascript
{
  _id: "article-1001",
  version: NumberLong("4"),
  title: "MongoDB Basics",
  body: "Initial content"
}
```

Both users read **version 4**. On save, instead of matching solely on `_id`, the application requires:

```text
Accept the update only if:
  _id == "article-1001"
  AND
  version == 4
```

If matched, update the data and increment `version` to `5` **inside the same atomic single-document write**.

```text
User A reads v4                User B reads v4
     |                              |
     v                              v
SAVE where id=1001, version=4    SAVE where id=1001, version=4
     |                              |
     v                              v
Document matched                  version=4 no longer matches
     |                              |
     v                              v
Write data + version=5           CONFLICT: write rejected
```

In Spring Data MongoDB, `@Version` automates this mechanism for framework-supported entity operations, notably `save()`.

## 3. What Is Optimistic Locking?

**Optimistic locking** assumes write conflicts are the exception rather than the rule. It does not hold an exclusive mutex or database lock from the moment a user opens a form until they click Save. Instead:

1. Read the document along with its **current version**.
2. The user or service computes changes.
3. Write with the condition that **`version` still equals the previously read value**.
4. If the write succeeds, increment `version`.
5. If the condition fails to match, raise a **conflict** and resolve it explicitly.

This is document-level **compare-and-set (CAS)**.

### Optimistic vs. Pessimistic Locking

| Criterion | Optimistic Locking | Pessimistic Locking |
| --- | --- | --- |
| Protection mechanism | Detects concurrent changes at write time | Holds locks/blocks contention per protocol |
| When no conflict occurs | Minimal coordination overhead | May still acquire and hold locks |
| When a conflict occurs | One writer fails and must handle it | Other writers may block waiting |
| Impact of long user edits | No lock held while editing a form | Long-held locks cause severe contention |
| Common Spring Data MongoDB approach | `@Version` and CAS | No built-in "form lock" via `@Version` |

Do not let the word **locking** mislead you into thinking Spring Data "locks the document for minutes." `@Version` is a **conflict-detection token**, not an exclusive multi-minute lease for viewers.

## 4. Where Does `@Version` Live in Spring Data MongoDB?

Annotation:

```java
import org.springframework.data.annotation.Version;
```

This is a **Spring Data** annotation, not `jakarta.persistence.Version` from JPA. Both share the optimistic locking concept, while MongoDB mapping and persistence behavior are implemented specifically by Spring Data MongoDB.

Domain document:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "articles")
public class Article {

    @Id
    private String id;

    @Version
    private Long version;

    private String title;
    private String body;

    public Article() {
    }

    public Article(String id, String title, String body) {
        this.id = id;
        this.title = title;
        this.body = body;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public Long getVersion() {
        return version;
    }

    public void setVersion(Long version) {
        this.version = version;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getBody() {
        return body;
    }

    public void setBody(String body) {
        this.body = body;
    }
}
```

Explanation:

- `@Document(collection = "articles")` maps the class to the MongoDB collection.
- `@Id` maps `id` to BSON `_id`.
- `@Version` marks the property Spring Data uses as the **entity version**.
- Using `Long` (wrapper) represents an **unversioned/new** state as `null` prior to initial insert.
- Application code should **not manually increment `version`** when calling `Repository.save()`; the framework manages it along supported paths.

### Why Not Use `@jakarta.persistence.Version`?

Projects containing both JPA and MongoDB dependencies can easily import the wrong annotation. For Spring Data MongoDB entities, always use:

```java
org.springframework.data.annotation.Version
```

Never assume the MongoDB converter honors JPA annotations identically.

## 5. Adding the Repository

Spring Data MongoDB repository interface:

```java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ArticleRepository
        extends MongoRepository<Article, String> {
}
```

In Spring Boot, the starter dependency in Maven is:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
```

Manage versions consistently through the **Spring Boot dependency management/BOM**. Never mix Spring Data artifacts across different major versions.

Also configure the URI, authentication, TLS, and database name properly for your environment; for example:

```properties
# Placeholder; obtain real URI from secret management.
spring.data.mongodb.uri=${MONGODB_URI}
```

This uses environment-variable placeholder syntax in Spring configuration. Never commit real passwords to `application.properties`.

## 6. Creating a New Document and Initial Version

A service creates a document:

```java
Article article = new Article(
    "article-1001",
    "MongoDB Basics",
    "Initial content"
);

Article saved = articleRepository.save(article);

System.out.println(saved.getVersion());
```

Spring Data MongoDB applies initialization rules when inserting a new versioned entity. By the standard convention documented in Spring Data, **wrapper numeric versions** like `Long` typically start at **`0`**, whereas **primitive numeric versions** often initialize to **`1`** due to how the framework distinguishes new entities.

Therefore, **never hardcode a single initial version across all models and versions**. Choosing nullable `Long version`, letting Spring Data handle initial insert state, and verifying the persisted value in integration tests avoids subtle bugs.

### Never Accept Arbitrary Versions on Create Requests

Never allow the frontend to supply an arbitrary version and copy it onto a new entity:

```json
{
  "id": "article-1001",
  "version": 99,
  "title": "MongoDB Basics"
}
```

`version` is **server-managed concurrency metadata**. Create request DTOs should carry business fields while the persistence layer initializes the version. On updates, clients can send **`expectedVersion`** to identify the snapshot they edited, never as a value to overwrite directly.

## 7. How Does Spring Data Execute `save()`?

For an existing versioned entity, Spring Data MongoDB performs a version-checked update. Conceptually, the condition resembles:

```javascript
db.articles.updateOne(
  {
    _id: "article-1001",
    version: NumberLong("4")
  },
  {
    $set: {
      title: "Advanced MongoDB",
      body: "Initial content"
    },
    $inc: { version: NumberLong("1") }
  }
);
```

This is **conceptual pseudocode**, not a guarantee that `Repository.save()` emits that exact `updateOne` operator layout in every case. The converter/framework may structure the BSON update differently depending on version and entity mapping. The essentials are:

- The write is **conditional on `version`**.
- `version` increments atomically upon a successful update via supported persistence paths.
- If the expected version no longer matches, Spring Data throws an **optimistic locking failure**.

**You do not need a unique index on `{_id, version}`** for CAS to work: `_id` already has a unique index, and `version` acts as an additional predicate within the atomic write.

### Why Is MongoDB Atomicity Still Required?

Two concurrent requests checking:

```text
WHERE id = X AND version = 4
```

must evaluate the condition **at write time**. If an application instead runs:

```text
SELECT version
IF version = 4:
    UPDATE by id only
```

another writer can slip in between `SELECT` and `UPDATE`. MongoDB's single-document conditional update closes that gap.

## 8. Illustrating Two Stale Copies and a Conflict

Sequential code simulating two requests that both read before either writes:

```java
Article copyA = articleRepository
    .findById("article-1001")
    .orElseThrow();

Article copyB = articleRepository
    .findById("article-1001")
    .orElseThrow();

// Assume both read version 4.

copyA.setTitle("Advanced MongoDB");
Article savedA = articleRepository.save(copyA);

// Database is now at version 5.
copyB.setBody("New CRUD example");

// Second save cannot proceed as if version were still 4.
articleRepository.save(copyB);
```

With optimistic locking active in a supported configuration and an acknowledged write concern, `save(copyB)` fails with an exception in the hierarchy of:

```java
org.springframework.dao.OptimisticLockingFailureException
```

This **prevents silent overwrites**; it **does not automatically merge** A's new title with B's new body.

### Document State After This Example

```javascript
{
  _id: "article-1001",
  version: NumberLong("5"),
  title: "Advanced MongoDB",
  body: "Initial content"
}
```

User B's body edit **was not saved**. The application must notify the user or resolve the conflict according to business rules.

## 9. Exceptions and Prerequisites for Conflict Detection

Typical exception:

```java
import org.springframework.dao.OptimisticLockingFailureException;
```

Spring Data throws this when updating a versioned entity and **no document matches both ID and expected version** per operation semantics.

Example:

```java
try {
    articleRepository.save(copyB);
} catch (OptimisticLockingFailureException ex) {
    // Do not overwrite the newer version; return conflict or
    // reload and apply an explicit merge policy.
    throw ex;
}
```

**Never catch and swallow the exception**:

```java
try {
    articleRepository.save(copyB);
} catch (OptimisticLockingFailureException ex) {
    // WRONG: silently ignored and returning "Saved successfully".
}
```

Doing so deceives the client into thinking the write succeeded when it was rejected.

### An Acknowledged Write Concern Is Required

Optimistic locking relies on write feedback reporting whether a document matched/modified. **Unacknowledged writes (`w: 0`) do not return reliable write acknowledgment** for Spring Data to detect a version mismatch. Always use an **acknowledged write concern**.

Database-level example:

```java
import com.mongodb.WriteConcern;

MongoDatabase db = mongoClient
    .getDatabase("appdb")
    .withWriteConcern(WriteConcern.ACKNOWLEDGED);
```

This illustrates the principle, not the only way to configure Spring Data. When failover durability is required, evaluate `MAJORITY` based on topology and RPO: **`ACKNOWLEDGED` enables write feedback**, while `MAJORITY` provides stronger replication durability guarantees—not a separate optimistic locking mechanism.

## 10. @Version Alone Does Not Protect Stale HTTP Forms

Consider two web requests minutes apart:

```text
10:00  User A GET /articles/1001    -> version 4
10:01  User B edits and SAVES       -> version 5
10:05  User A submits stale form    -> intends to save changes based on v4
```

A service implementation that **fails to catch stale forms**:

```java
public Article update(String id, UpdateRequest request) {
    Article current = articleRepository.findById(id)
        .orElseThrow();

    current.setTitle(request.title());
    current.setBody(request.body());

    return articleRepository.save(current);
}
```

Because the service **just reloaded the latest version** and immediately saved, User A's request silently overwrites User B's edits with zero conflict! `@Version` only protects the window **between the service's own read and write**; it cannot know the client started from v4 unless the application passes `expectedVersion` over HTTP.

### Solution: Client Sends `expectedVersion`

`GET` response:

```json
{
  "id": "article-1001",
  "version": 4,
  "title": "MongoDB Basics",
  "body": "Initial content"
}
```

Update request:

```json
{
  "expectedVersion": 4,
  "title": "MongoDB Basics",
  "body": "New CRUD example"
}
```

The backend compares `expectedVersion` against the current version and **still executes a CAS write**. Checking version in a separate prior read alone does not close the race window after that check.

## 11. Designing an Update DTO with `expectedVersion`

Example Java record:

```java
public record UpdateArticleRequest(
    Long expectedVersion,
    String title,
    String body
) {
}
```

Service implementation:

```java
import java.util.Objects;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.stereotype.Service;

@Service
public class ArticleService {

    private final ArticleRepository repository;

    public ArticleService(ArticleRepository repository) {
        this.repository = repository;
    }

    public Article updateArticle(
            String id, UpdateArticleRequest request) {

        if (request.expectedVersion() == null) {
            throw new IllegalArgumentException(
                "expectedVersion is required");
        }

        Article current = repository.findById(id)
            .orElseThrow(() ->
                new IllegalArgumentException("Article not found"));

        if (!Objects.equals(
                current.getVersion(),
                request.expectedVersion())) {
            throw new OptimisticLockingFailureException(
                "Document has changed; reload before saving");
        }

        current.setTitle(request.title());
        current.setBody(request.body());

        // Database-level CAS is still mandatory:
        return repository.save(current);
    }
}
```

This provides **two layers of defense**:

1. Early check: gives a clear error when the client submitted a stale form.
2. Database CAS on `save()`: catches concurrent edits arriving **between the read and the save**.

If the service ran only the early check and then called a raw `updateOne({_id: id}, ...)` without a version predicate, the race condition would remain.

### Never Use the Persistence Entity Directly as a Request DTO

Never bind incoming request JSON straight onto an `@Version` `Article` entity and call `save()` with uncontrolled fields. Clients could supply or omit fields arbitrarily, overwriting attributes absent from the UI form.

Use a dedicated **request DTO** separate from the entity and whitelist updatable fields.

## 12. Returning HTTP 409 Conflict for Optimistic Locking

When a request attempts to save over a stale version, a common API response is:

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "code": "VERSION_CONFLICT",
  "message": "Data has been modified. Reload before saving."
}
```

Spring maps the exception via `@RestControllerAdvice`:

```java
import java.util.Map;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ConflictExceptionHandler {

    @ExceptionHandler(
        OptimisticLockingFailureException.class)
    public ResponseEntity<Map<String, String>> conflict(
            OptimisticLockingFailureException ex) {

        return ResponseEntity
            .status(HttpStatus.CONFLICT)
            .body(Map.of(
                "code", "VERSION_CONFLICT",
                "message",
                "Data has changed; reload the latest version"));
    }
}
```

Never leak raw exception messages containing internal entity or database details to clients. Log correlation IDs and stack traces server-side under your security policy.

### Is 409 Always Mandatory?

Not every API must return 409. When designing HTTP **conditional requests** using `If-Match`/ETag, a failed precondition maps to **412 Precondition Failed**. When an API uses `expectedVersion` in the request body instead of HTTP preconditions and detects a domain conflict, **409 Conflict** is standard.

More important than the specific status code is maintaining a **stable API contract** with distinguishable errors so clients know how to recover.

## 13. ETag and If-Match: Optimistic Concurrency at the HTTP Layer

A REST API can expose version via an `ETag` header:

```http
HTTP/1.1 200 OK
ETag: "v4"
Content-Type: application/json

{
  "id": "article-1001",
  "title": "MongoDB Basics",
  "body": "Initial content"
}
```

The client sends:

```http
PUT /articles/article-1001
If-Match: "v4"
Content-Type: application/json

{
  "title": "Advanced MongoDB",
  "body": "Initial content"
}
```

The backend translates the ETag into an expected version **per server-defined contract** and performs a CAS write. If the current version is already `5`, return:

```http
HTTP/1.1 412 Precondition Failed
```

**An ETag is an HTTP representation token** and does not have to expose raw MongoDB fields directly. ETags may encode versions, representation hashes, or opaque tokens; define **strong vs. weak ETag** rules and comparison semantics per HTTP conditional request standards.

### Does ETag Replace CAS?

No. Reading `If-Match` and comparing it against a `findById()` read **is insufficient**. The database write must still include the version condition so no concurrent request slips in between.

## 14. MongoTemplate.save() with @Version

Beyond repositories, Spring Data MongoDB provides `MongoTemplate`:

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class ArticleTemplateService {
    private final MongoTemplate template;

    public ArticleTemplateService(MongoTemplate template) {
        this.template = template;
    }

    public Article rename(String id, String newTitle) {
        Article current = template.findById(
            id, Article.class);

        if (current == null) {
            throw new IllegalArgumentException(
                "Article does not exist");
        }

        current.setTitle(newTitle);
        return template.save(current);
    }
}
```

For an `Article` annotated with `@Version`, `MongoTemplate.save()` also performs optimistic version checking on existing entities.

**Like repositories**, however, this protects only the window between the template's read and save in the same execution flow. It **cannot detect** an already-stale HTTP form unless the client passes `expectedVersion`.

## 15. Partial Updates: CAS via MongoTemplate.updateFirst()

Loading and saving the entire document is not always appropriate. Suppose an API only edits `title` and must never touch `body`.

Direct CAS update:

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public void updateTitle(
        MongoTemplate template,
        String id,
        long expectedVersion,
        String newTitle) {

    Query query = Query.query(
        Criteria.where("_id").is(id)
            .and("version").is(expectedVersion)
    );

    Update update = new Update()
        .set("title", newTitle)
        .inc("version", 1L);

    UpdateResult result =
        template.updateFirst(query, update, Article.class);

    if (result.getMatchedCount() == 0) {
        throw new OptimisticLockingFailureException(
            "Version mismatch or document was deleted");
    }
}
```

This executes **a single atomic MongoDB update on one document** conditioned on ID + version.

### Why Check `getMatchedCount()`?

If no document matches `{_id, version}`, the CAS condition failed. `getMatchedCount() == 0` reliably signals a failed match (even though it does not by itself distinguish a deleted document from a bumped version).

`getModifiedCount()` reports documents whose values actually changed, which can differ from matched count in certain updates; to verify whether the CAS predicate matched, **matched count** is the direct signal.

### Spring Data May Auto-Increment Version in the Update API

In documented Spring Data MongoDB versions, entity-mapped update operations may **automatically increment the `@Version` field if the `Update` does not already modify it**. In the snippet above, `.inc("version", 1L)` is written **explicitly**, so verify that your framework/mapping configuration does not increment the version twice.

More importantly: **auto-incrementing version without an expected-version predicate in the `Query` does not provide optimistic locking CAS**. When using `updateFirst()`, `updateMulti()`, or bulk writes, verify the exact query and update BSON emitted by that code path.

### Watch Mapped Field Names

If the domain version property is mapped with `@Field("revision")` or another naming strategy, align queries and updates accordingly. Through `MongoTemplate` with an entity class, Spring Data maps Java property names to BSON names; through the raw driver, always use **exact stored BSON field names**.

## 16. findAndModify: CAS Returning the Updated Document

An API needing the newly updated version right away can use `findAndModify()`:

```java
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public Article updateTitleReturningNew(
        MongoTemplate template,
        String id,
        long expectedVersion,
        String newTitle) {

    Query query = Query.query(
        Criteria.where("_id").is(id)
            .and("version").is(expectedVersion));

    Update update = new Update()
        .set("title", newTitle)
        .inc("version", 1L);

    Article updated = template.findAndModify(
        query,
        update,
        FindAndModifyOptions.options().returnNew(true),
        Article.class
    );

    if (updated == null) {
        throw new OptimisticLockingFailureException(
            "Target version not found for update");
    }

    return updated;
}
```

`returnNew(true)` requests the **post-update document**. If the filter fails to match, the call returns `null`.

Never enable `upsert(true)` on an operation that **must only update an existing document at `expectedVersion`**. With upsert accidentally enabled, a version conflict could insert a brand-new document contrary to the business contract.

## 17. Comparing Save vs. Field-Level Updates

| Approach | Strengths | Risks / Notes |
| --- | --- | --- |
| `repository.save(entity)` | Simple; Spring Data manages `@Version` on entities | Reads/writes full entity; still needs client `expectedVersion` for stale forms |
| `mongoTemplate.save(entity)` | Similar to repository with template flexibility | Still full-entity read–modify–write and version handling |
| `updateFirst(query id+version, update)` | Partial field write with explicit CAS | Developer must maintain filter and version increment |
| `findAndModify(id+version, update)` | CAS and returns updated document in one logical round trip | Must handle `null` no-match and avoid accidental `upsert` |
| Raw MongoDB driver CAS update | Full control over exact BSON command | No automatic Spring Data version management |
| Broad `updateMany()` | Fits intentional bulk transitions | Does not provide per-entity stale-state protection |

In CRUD systems with full edit forms, `Repository.save()` + `expectedVersion` is clear and readable. In APIs updating a single field or status, **conditional CAS updates** express intent more cleanly and reduce the risk of clobbering unrelated fields.

## 18. Never Assume Every Write Goes Through @Version

`@Version` does not turn the MongoDB server into a gatekeeper that **automatically rejects every stale writer**. It operates only through Spring Data's mapped operations.

Other write paths may include:

- `MongoRepository.save()`.
- `MongoTemplate.save()`.
- `MongoTemplate.updateFirst()`, `findAndModify()`.
- Bulk operations.
- `MongoCollection.updateOne()` via the Java Sync Driver.
- `mongosh` or MongoDB Compass.
- Migration scripts and data-repair jobs.
- CDC/ETL writers and background processors.

If a script runs:

```javascript
db.articles.updateOne(
  { _id: "article-1001" },
  { $set: { title: "Title from script" } }
);
```

that command **has no awareness of Java's `@Version` annotation**. It updates `title` **without incrementing `version`**. A Spring Data request still holding the prior version can then pass CAS and overwrite the script's change.

### Rule for All Writers

Once a system adopts `version` to prevent lost updates, **every path updating protected fields** must honor the shared contract:

1. Include expected version (unless intentionally designed as an independent atomic update).
2. Filter by ID and version (or equivalent state precondition).
3. Update data and increment `version` **in the same atomic operation**.
4. Verify matched count / no-match.
5. Handle conflicts and emit metrics.

Automated scripts must never bypass the contract merely because they run outside Spring Boot.

## 19. Writing CAS with the MongoDB Java Sync Driver

Processes outside Spring Data can still participate in optimistic locking using MongoDB atomic updates:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

UpdateResult result = collection.updateOne(
    Filters.and(
        Filters.eq("_id", "article-1001"),
        Filters.eq("version", 4L)
    ),
    Updates.combine(
        Updates.set("title", "New title"),
        Updates.inc("version", 1L)
    )
);

if (result.getMatchedCount() == 0) {
    // Conflict: expected (_id, version) not found.
}
```

This assumes `collection` is a `MongoCollection<Document>` and `version` is stored as BSON `Int64`. If the schema uses `Int32` or a different field name, match the exact type and naming convention.

This is the same CAS pattern that `@Version` automates for supported repository operations.

## 20. Why Reading Version First and Updating by ID Alone Is Wrong

Broken implementation:

```java
Article current = repository.findById(id).orElseThrow();

if (current.getVersion().equals(expectedVersion)) {
    // WRONG: query filters only by id, not version at write time.
    template.updateFirst(
        Query.query(Criteria.where("_id").is(id)),
        new Update().set("title", newTitle),
        Article.class
    );
}
```

Between the read and the update, another writer can modify the document. Even if Spring Data auto-increments `version` on update, this command **overwrites the newer title** because it never required the current version to equal `expectedVersion`.

Correct version:

```java
Query query = Query.query(
    Criteria.where("_id").is(id)
        .and("version").is(expectedVersion));

Update update = new Update()
    .set("title", newTitle)
    .inc("version", 1L);
```

The version check must live inside the **same atomic database operation** as the mutation.

## 21. Does @Version Replace Atomic Updates Like `$inc`?

No. Many operations do not need a full read–modify–save cycle:

```javascript
db.counters.updateOne(
  { _id: "views-article-1001" },
  { $inc: { count: 1 } }
);
```

Two concurrent writers executing `$inc` will never suffer a **lost increment** the way two clients reading `count` and calling `save(count + 1)` would. Every `$inc` is atomic at the document level.

### Choosing the Right Tool for the Invariant

| Problem | Typically Appropriate Technique |
| --- | --- |
| Two users concurrently editing an entire form | `@Version` + `expectedVersion` |
| Incrementing a view counter | Atomic `$inc` |
| Adding an ID to a unique set | Atomic `$addToSet` |
| Transitioning `NEW` → `APPROVED` if still `NEW` | Conditional update on `status` (plus `version` if desired) |
| Decrementing inventory if sufficient | Filter `available >= quantity` + atomic `$inc` |
| Writing two collections requiring global atomicity | Multi-document transaction / business workflow |

**Version alone does not enforce business invariants.** CAS blocks a stale writer, yet still allows a current writer to set stock negative unless domain validation or conditional predicates prevent it.

## 22. Example: Keeping Inventory Non-Negative

Suppose the document is:

```javascript
{
  _id: "SKU-A",
  available: 10,
  version: NumberLong("7")
}
```

A request reserves 3 units. Loading `10` and calling `save(7)` causes constant contention under concurrency. When business rules only require atomic decrement given sufficient stock:

```java
Query query = Query.query(
    Criteria.where("_id").is("SKU-A")
        .and("available").gte(3));

Update update = new Update()
    .inc("available", -3)
    .inc("version", 1L);

UpdateResult result =
    template.updateFirst(query, update, InventoryItem.class);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
        "Insufficient stock or SKU does not exist");
}
```

Here the **inventory precondition** is `available >= 3`, rather than gating purely on `version`. Incrementing `version` still alerts `@Version`-based writers that the document changed.

### Caution: Two Distinct Concurrency Strategies

- **Version-based CAS:** fails if any writer modified the document since the client read it.
- **Business-state atomic conditional update:** permits concurrent writers to succeed as long as the domain invariant holds.

Both can be combined, yet avoid putting an unnecessary version gate on a hot counter receiving thousands of updates per second—it will cause needless conflicts and retries where `$inc` already prevents lost increments.

## 23. What Happens When Two Users Edit Different Fields?

Suppose:

```text
User A: edits title
User B: edits body
```

If both hold version 4, document-level optimistic locking **allows only one to save first**. Even though their edits touch disjoint fields, the document's version increments, causing the second writer to hit a conflict.

This is a **conservative conflict**, not a framework bug. It prevents blind auto-merges when domain invariants span fields.

### Resolution Options

1. Return a conflict and prompt the user to reload and reapply changes.
2. Implement an explicit **field-level merge** check (e.g., if `title` has not changed since v4, apply A's title safely).
3. Use targeted atomic `PATCH` updates on independent fields with domain guards.
4. Split large documents into separate aggregates if contention is excessive.
5. Adopt a different concurrency pattern for high-write-frequency subfields.

Never assume "different fields are always safe to merge." One field can affect another's validation—for instance, changing `status` may make `approvedBy` mandatory.

## 24. Distinguishing Version Conflicts from Deleted Documents

When CAS runs:

```text
WHERE _id = X AND version = 4
MatchedCount = 0
```

possible causes include:

- The document exists, but has advanced to version 5.
- The document was deleted.
- Incorrect ID or query field mapping.
- Legacy record lacking `version` or storing a different BSON type.

A follow-up `findById()` can **classify the error for a clearer message**, keeping in mind that under concurrency this extra read reflects only the moment it ran.

API mapping examples:

- **404 Not Found** if the resource no longer exists and policy permits disclosing that.
- **409 Conflict** if the resource exists with a different version.
- **412 Precondition Failed** if `If-Match` failed.

Never leak another tenant's resource existence when classifying errors. Enforce authorization both before and after reads and updates.

## 25. Does Delete Interact with @Version?

Spring Data MongoDB provides **version-checked entity deletion** paths. In supporting versions, deleting an entity loaded with `@Version` checks the version and throws an optimistic locking failure if the document changed prior to deletion.

Example:

```java
Article current = repository.findById(id)
    .orElseThrow();

repository.delete(current);
```

Deleting **by entity** can apply version preconditions. By contrast, deleting **by ID or query** has no version precondition unless the API explicitly receives and enforces `expectedVersion`.

### Two Delete APIs Are Not Equivalent

```java
repository.delete(current);  // Has entity and version to verify.
repository.deleteById(id);   // Has ID only; unaware of what version the client read.
```

Verify exact behavior of each delete method against your active **Spring Data MongoDB version**. Never assume `deleteById` protects stale client requests.

### Deletes from a UI

If a user clicks Delete on a v4 form while the server is already at v5, the API should accept `expectedVersion`/ETag and perform a conditional delete.

For instance, with `MongoTemplate`:

```java
Query query = Query.query(
    Criteria.where("_id").is(id)
        .and("version").is(expectedVersion));

DeleteResult result =
    template.remove(query, Article.class);

if (result.getDeletedCount() == 0) {
    throw new OptimisticLockingFailureException(
        "Cannot delete: document no longer at expected version");
}
```

When compiling, import `com.mongodb.client.result.DeleteResult` and Spring Data query classes. For audited systems, soft delete may be preferable to hard delete.

## 26. Soft Deletes and State Transitions

Some applications use:

```javascript
{
  _id: "article-1001",
  version: NumberLong("8"),
  status: "ACTIVE",
  deletedAt: null
}
```

instead of physical deletion. Soft deletes should execute as **conditional state transitions**:

```javascript
db.articles.updateOne(
  {
    _id: "article-1001",
    version: NumberLong("8"),
    status: "ACTIVE"
  },
  {
    $set: {
      status: "DELETED",
      deletedAt: ISODate("2026-11-14T08:00:00Z")
    },
    $inc: {
      version: NumberLong("1")
    }
  }
);
```

This illustrates the CAS logic. In Spring Data, use `MongoTemplate` or a domain service with the equivalent query, update, and matched-count verification.

**Never check only `version` while ignoring business state**: a version-8 document that is already locked or archived must still reject deletion when policy forbids it.

## 27. Does @Version Replace Transactions?

No. `@Version` protects **concurrent updates to a single entity/document**. It does not make writes across multiple collections atomic together.

Order creation example:

```text
1. Decrement inventory.available
2. Insert orders document
3. Insert payment-intent record
```

If step 1 succeeds and step 2 fails, even with `@Version` on `inventory`, the system must still coordinate cross-record consistency.

Options:

- MongoDB **multi-document transactions** when topology, driver, and session support them and atomicity is required.
- Application-level workflows or sagas with compensating actions.
- Redesigning aggregate boundaries so tightly coupled invariants live in one document where practical.
- Idempotent event processing and the outbox pattern for external side effects.

### Transactions Also Experience Concurrency Conflicts

Transactions do not eliminate all conflicts. Concurrent transactions can suffer write conflicts or transient transaction errors requiring retries per driver/Spring transaction semantics. `@Version` adds business-level stale-form detection, serving a distinct boundary.

**Never wrap the entire multi-minute duration a user spends editing a form inside a MongoDB transaction.** Database transactions are not built to hold locks across multi-minute user think time.

## 28. @Transactional and @Version

Spring provides:

```java
import org.springframework.transaction.annotation.Transactional;
```

For MongoDB, using Spring Data transactions requires configuring a transaction manager, MongoDB sessions, and a transaction-capable deployment (e.g., replica set or sharded cluster per server version). Simply adding `@Transactional` to a method does not automatically enlist MongoDB operations in a transaction without proper setup.

Conceptual example:

```java
@Transactional
public void changeTwoDocuments(...) {
    // Repository/template operations running inside a
    // MongoDB transaction when properly configured.
}
```

Inside a transaction:

- Writes commit or abort together per supported semantics.
- An optimistic locking failure must roll back/abort cleanly.
- Retrying an entire transaction can duplicate external side effects if external APIs are called mid-method.

Never treat `@Version` and `@Transactional` as interchangeable switches.

## 29. Retrying Optimistic Locking: When to Retry and When Not To

When `OptimisticLockingFailureException` occurs, one option is retrying:

```text
Read v4
  |
Save v4 -> conflict
  |
Reload v5
  |
Recompute change on v5
  |
Save v5 -> succeeds or hits another conflict
```

However, **blindly retrying the stale request** turns a caught lost update into an **intentional overwrite**.

### Operations Often Safe for Controlled Retries

- Recomputing a derived value from fresh state.
- Merging verified independent edits.
- Recomputing a side-effect-free derived field.
- Clearly guarded conditional state transitions.

### Operations You Must Not Auto-Retry to Overwrite

- A user edited a form from a stale snapshot and needs to review the other user's changes.
- Updating monetary amounts, permissions, or approval states without an explicit merge policy.
- Code producing external side effects outside MongoDB without idempotency.
- An update assuming "status is still `NEW`" when it has already transitioned to `APPROVED`.

**Right mindset:** an optimistic conflict is a **business decision signal**, not always a transient network glitch to auto-retry.

## 30. Bounded Retries with Reload and Invariant Checks

Service example for a transformation the domain allows recomputing on fresh state:

```java
import org.springframework.dao.OptimisticLockingFailureException;

public Article addSuffixToTitle(
        ArticleRepository repository,
        String id,
        String suffix) {

    int maxAttempts = 3;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        Article latest = repository.findById(id)
            .orElseThrow(() ->
                new IllegalArgumentException("Article does not exist"));

        // Example only when domain permits repeating/recomputing this edit.
        latest.setTitle(latest.getTitle() + suffix);

        try {
            return repository.save(latest);
        } catch (OptimisticLockingFailureException ex) {
            if (attempt == maxAttempts) {
                throw ex;
            }
            // Next attempt reloads fresh state and re-evaluates.
        }
    }

    throw new IllegalStateException("Unreachable");
}
```

Notice the code intentionally **discards the stale object** upon catching the exception. Even so, it does not suit every domain: two concurrent requests appending the same suffix would duplicate it unless domain idempotency prevents that.

Under heavy contention, add overall time budgets and exponential backoff with jitter rather than spinning immediately. And if the operation is simply incrementing a counter, **atomic `$inc` is far better** than an optimistic retry loop.

## 31. Never Retry Side Effects Twice

Consider this broken flow:

```text
1. Send confirmation email
2. Load entity
3. Save entity -> optimistic conflict
4. Retry method from the top
5. Send confirmation email a second time
```

This is a **side-effect duplication** bug. The same applies to charging payment gateways, publishing Kafka messages, or triggering external webhooks.

### Better Design Patterns

- Trigger side effects **only after the business state update commits** per contract.
- For event publication, use a **transactional outbox** or reliable message-consistency pattern.
- Pass an **idempotency key** so external services deduplicate repeated requests.
- Never place non-idempotent network calls inside a block that retries automatically on version conflicts.
- Persist completion markers or business tokens to prevent duplicate execution.

**`@Version` prevents lost updates on documents; it does not provide exactly-once delivery for emails, payments, or events.**

## 32. Conflicts Across Multiple Service Instances

In production, the same collection can be updated concurrently by:

```text
Spring Boot instance A
Spring Boot instance B
Background worker C
Scheduled job D
Data migration process E
```

`synchronized` on a Java object inside instance A cannot protect a multi-process cluster.

With `@Version` and MongoDB conditional updates, every instance **sharing the database** participates in document-level CAS—provided all writers follow the contract.

### Why Is CAS Superior to In-Memory Locks?

JVM `synchronized` or `ReentrantLock` guards only threads inside that single JVM. When a service scales across replicas, each JVM holds independent locks.

`@Version` evaluates its predicate on the MongoDB server where the document lives, providing a shared synchronization point.

### Every Writer Must Participate

If worker C executes raw `updateOne({_id}, {$set...})` without touching `version`, instances A and B lose visibility into that edit. Standardize the data-access contract across all services, not just one repository.

## 33. @Version and MongoDB Write Concern

Two orthogonal concepts:

**Optimistic concurrency:** checks `version` to reject writes built from stale reads.

**Durability / replication acknowledgment:** defines when a write is considered durable per `WriteConcern`.

Flow:

```text
Update WHERE id=1 AND version=4
  |
  v
Database matched version 4
  |
  v
Write acknowledged per write concern
  |
  v
Spring Data returns success and updated entity version
```

With `w: 0`, the client gets no reliable acknowledgment indicating whether the version matched, starving optimistic locking of its required signal.

In replica sets, `w: "majority"` improves durability and rollback safety over `w: 1` during failovers, yet it **never turns a version conflict into success** or replaces business conflict handling.

### Timeouts Differ from Conflicts

- **`OptimisticLockingFailureException`:** CAS predicate failed to match per framework semantics.
- **`MongoSocketTimeoutException`/timeout:** client does not know whether the server applied the write.
- **WriteConcern timeout:** durability acknowledgment missed the deadline; the write may still have been applied.

Never lump all three into identical retry behavior. Unknown-outcome timeouts require idempotency and state reconciliation.

## 34. Version Properties in New Entities vs. Legacy Data

Suppose an older collection never had a `version` field:

```javascript
{
  _id: "article-old",
  title: "Legacy record"
}
```

After adding:

```java
@Version
private Long version;
```

the `version` property decodes as `null`. Spring Data also inspects the version property in certain code paths to **distinguish new entities from existing ones**. Calling `save()` on a legacy entity whose `version` is `null` can treat it as a brand-new entity and trigger an unexpected insert / duplicate key error instead of a clean CAS update.

### Migration Plan When Enabling @Version

1. Inventory documents with and without the `version` field.
2. Inspect existing version field types (`Int32`/`Int64`/`string`/`null`).
3. Choose a consistent convention for existing records.
4. Backfill missing `version` fields using an approved workflow.
5. Upgrade or gate any writers that do not manage versions.
6. Verify indexes and repository behavior in staging.
7. Coordinate a controlled rollout while mixed app versions coexist.
8. Monitor optimistic locking failure rates.

### Staging-Only Backfill Example

```javascript
db.articles.updateMany(
  { version: { $exists: false } },
  { $set: { version: NumberLong("0") } }
);
```

This is purely a technical example of **initializing `version`** when policy permits. Never run it directly on production with mixed old/new writers without a cutover plan and verification of how your Spring Data version represents initial versions.

### Why Backfilling Legacy Documents Requires Care

If backfilling runs concurrently alongside older non-versioned writers, updates can slip through without incrementing `version`, causing subsequent saves to miss conflicts. Coordinate a proper **migration cutover** rather than setting the field once and assuming safety.

## 35. Primitive `long` vs. Wrapper `Long`?

```java
@Version
private long version;   // primitive, defaults to 0
```

versus:

```java
@Version
private Long version;   // wrapper, nullable
```

Differences:

- Primitive `long` cannot represent `null`; its default value is `0`.
- Wrapper `Long` distinguishes an unsaved/unversioned entity (`null`) from a persisted entity at version `0`.
- Spring Data applies different **new-entity detection and version initialization rules** for primitives vs. wrappers.
- Consider JSON serialization of `Long` and client-side validation.

For new entities, nullable `Long` expresses entity lifecycle cleanly, though you should still verify behavior on your exact driver and framework version. Never switch `long` to `Long` mid-production without verifying stored document formats and DTO tests.

### Version Is Not a Business Revision String

If the UI displays labels like `v1.2.0` or `draft-2026-11`, store that in a separate **`businessRevision`** field. `@Version` should remain an incrementing numeric concurrency token. Never overload a business revision label as a concurrency counter if their lifecycles differ.

## 36. Never Manually Increment Version When the Repository Manages It

Anti-pattern:

```java
Article current = repository.findById(id).orElseThrow();
current.setTitle(newTitle);
current.setVersion(current.getVersion() + 1);
repository.save(current);
```

Because `save()` treats the entity's current `version` as the expected version in the database filter, manually incrementing it first causes Spring Data to query for the wrong version, triggering spurious failures or broken contracts.

**Right approach with repository entity saves:** modify business fields only and let Spring Data manage `version`.

Conversely, **when writing raw CAS updates**, you must explicitly increment `version` in the update command because MongoDB does not know about Java annotations. The rule depends on **which write path owns version management**.

## 37. Should You Index the Version Field?

In a typical CAS update:

```javascript
{ _id: "article-1001", version: NumberLong("4") }
```

MongoDB looks up the document via the unique `_id` index and checks `version` on that document. Thus, **you do not need a dedicated index on `version`** for standard CAS updates.

An index:

```javascript
db.articles.createIndex({ version: 1 });
```

does not make optimistic locking more accurate, while adding storage and write overhead since `version` changes on every update. Only index `version` if an actual query workload filters or sorts by it, validated via `explain`.

### Unique Indexes Do Not Replace Version

The unique index on `_id` prevents two documents from sharing the same ID—it does not prevent two sequential requests from overwriting **the same document**. Optimistic locking uses the version predicate to prevent lost updates, not ID collisions.

## 38. @Version and Domain Invariants

Suppose an order is:

```javascript
{
  _id: "ORD-1001",
  version: NumberLong("3"),
  status: "PAID",
  amount: NumberDecimal("125000.00")
}
```

A request carrying the valid version `3` tries to move status backward from `PAID` to `NEW`. CAS matches version `3`, yet the **business state transition is invalid** if the domain forbids moving backward.

The service must enforce:

```text
expectedVersion == currentVersion
AND
status transition permitted by business policy
AND
user authorized to act
AND
all other invariants satisfied
```

For atomic state transitions, encode the invariant right inside the query:

```javascript
db.orders.updateOne(
  {
    _id: "ORD-1001",
    version: NumberLong("3"),
    status: "PAID"
  },
  {
    $set: { status: "SHIPPED" },
    $inc: { version: NumberLong("1") }
  }
);
```

Both `version` and business state are verified **in one atomic update**, backed by validation, schema rules, and authorization at their respective layers.

## 39. Splitting Documents When Write Contention Is Too High

A large document with unrelated fields changing at different rates:

```javascript
{
  _id: "user-1001",
  version: NumberLong("100"),
  profile: {...},
  preferences: {...},
  lastSeenAt: ISODate("..."),
  counters: {...}
}
```

If every `lastSeenAt` ping or counter update increments `version`, a user editing their profile suffers constant conflicts.

Mitigations:

1. Use atomic operators and guard only relevant invariants.
2. Separate high-frequency telemetry and counters from the profile/aggregate document.
3. Reduce the scope of full-save entities.
4. Define explicitly which mutations share the concurrency token.
5. When splitting documents, assess whether cross-document invariants need transactions.

**Never skip incrementing `version` merely to reduce error counts** if other writers rely on it to detect document mutations. Adjust aggregate boundaries and concurrency policies rather than reintroducing lost updates.

## 40. Integration with Spring Data Auditing

Spring Data provides:

```java
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
```

Example:

```java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant updatedAt;

@Version
private Long version;
```

**Auditing timestamps and `@Version` are distinct mechanisms**:

- `updatedAt` records modification time per application/auditing callback policy.
- `version` is a concurrency token.
- Timestamps have clock drift and resolution limits and should not replace numeric version tokens by default.

When auditing is enabled and supported by mapping/codecs, callbacks populate timestamps automatically. Just like `@Version`, **raw MongoDB writers do not trigger Spring Data auditing callbacks automatically**.

### Should You Use `updatedAt` as a CAS Token?

While timestamp-based conditional updates are possible in certain schemas, they suffer from clock skew across app nodes, millisecond collisions, and precision limits. A monotonically incremented numeric `version` is far cleaner and more reliable for optimistic concurrency.

## 41. Testing Optimistic Locking with Two Copies

A clear integration test should:

1. Create a new entity in an **isolated test database**.
2. Read it into two **distinct Java object instances**.
3. Save copy A.
4. Attempt to save copy B with its stale version.
5. Assert that `OptimisticLockingFailureException` is thrown.
6. Reload from the database and verify copy A was not overwritten.

JUnit 5 example with an injected Spring Data repository:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.OptimisticLockingFailureException;

import static org.junit.jupiter.api.Assertions.*;

class ArticleOptimisticLockTest {

    @Autowired
    ArticleRepository repository;

    @Test
    void staleCopyMustNotOverwriteNewerVersion() {
        String id = "test-article-optimistic-lock";

        repository.save(
            new Article(id, "Initial", "Old body")
        );

        Article copyA = repository.findById(id)
            .orElseThrow();
        Article copyB = repository.findById(id)
            .orElseThrow();

        copyA.setTitle("Title A");
        Article savedA = repository.save(copyA);

        copyB.setBody("Body B");

        assertThrows(
            OptimisticLockingFailureException.class,
            () -> repository.save(copyB)
        );

        Article actual = repository.findById(id)
            .orElseThrow();

        assertEquals("Title A", actual.getTitle());
        assertEquals("Old body", actual.getBody());
        assertEquals(savedA.getVersion(), actual.getVersion());
    }
}
```

This is the **core test logic**, not the complete harness: add `@DataMongoTest`/Spring context, an isolated database, test cleanup, and a real MongoDB instance. Fixed IDs suit tests that clean up properly; avoid colliding IDs in shared environments.

### Why Does a Sequential Test Still Prove Optimistic Locking?

Because both `copyA` and `copyB` were **read before A wrote**. Once A saves, B holds a stale version. That directly exercises the CAS mechanism even without concurrent threads.

## 42. Testing Real Concurrency with Multiple Threads

For critical services, add a multi-writer integration test:

```text
Thread A: reads v0 ------\
                        +--> Barrier: both hold v0
Thread B: reads v0 ------/
                        |
                        +--> both attempt save
                        |
                   one write wins
                   one write conflicts
```

Use `CountDownLatch` or `CyclicBarrier` to synchronize threads, making sure to:

- Give each thread **its own distinct entity instance**.
- Never share one mutable object across threads (which causes Java data races).
- Use an isolated test database/collection.
- Await thread completion and assert exact exception types.
- Never hardcode which thread (A or B) wins; assert the invariant that **exactly one save succeeds from the shared initial version**.
- Confirm acknowledged write concern against a live MongoDB instance.

In realistic load tests, also measure **conflict rates**, p95/p99 latency, retry counts, total committed operations, and end-state business correctness.

## 43. Testing Conflicts at the API / HTTP Layer

End-to-end integration test flow:

```text
1. POST /articles
   -> article id = X, version = 0

2. GET /articles/X
   -> snapshot v0 for User A

3. GET /articles/X
   -> snapshot v0 for User B

4. PUT /articles/X, expectedVersion=0, title="A"
   -> 200 OK, version=1

5. PUT /articles/X, expectedVersion=0, body="B"
   -> 409 Conflict or 412 per API contract

6. GET /articles/X
   -> title="A", body was not overwritten by B
```

If a service reloads the latest entity from the repository and saves without comparing `expectedVersion` from the request, step 5 will **wrongly succeed**. That is why tests must cover the **API layer**, not only `Repository.save()`.

### Verify Authorization

An unauthorized user must never bypass permission checks merely by supplying a valid `expectedVersion`. Versions are not security tokens. `ObjectId`, `version`, and `ETag` may be visible to authorized readers, yet never replace AuthN/AuthZ.

## 44. Monitoring Optimistic Locking in Production

Useful metrics:

| Metric / Signal | Meaning |
| --- | --- |
| Optimistic conflicts per endpoint | Frequency of requests rejected due to stale versions |
| Conflicts per entity type | Which document types experience high contention |
| Retry attempts / successes | Whether automated retries succeed or waste load |
| Conflict-to-success ratio | Guides UX and workload design |
| Time between `GET` and `save` | Long-open forms go stale more often |
| HTTP 409/412 rate | Client experience and API behavior |
| Database write latency | Widens race windows when elevated |
| Version jump rate | Entities mutated at abnormally high frequency |
| Raw writer version drift | Writers bypassing the version contract |
| Side-effect duplicates | Retries causing duplicate emails/events/payments |

### Are Rising Conflicts Always an Outage?

Not necessarily. Optimistic locking **is protecting your data** when it reports conflicts. Still, a sudden spike can indicate:

- UI screens letting users keep forms open too long.
- A background job updating the same documents overly frequently.
- Multiple services issuing full-entity saves instead of partial updates.
- Overly aggressive retry loops.
- Poorly bounded aggregates.

Never suppress errors by **removing the version predicate**. Fix the source of contention or improve the workflow.

## 45. Conflict Troubleshooting Runbook

When logs or APIs report `OptimisticLockingFailureException`:

### Step 1 — Identify the Operation

- Entity type and document ID (masked where sensitive).
- Endpoint or worker performing the write.
- Expected version vs. current stored version via an appropriate read.
- Operation type: full save, partial update, delete, or raw driver write.

### Step 2 — Inspect Write Paths

- Does the entity carry Spring Data's `@Version`?
- Does the repository/template operation enforce version checking?
- Is any writer updating documents directly without incrementing `version`?
- Is write concern acknowledged?
- Is the client passing `expectedVersion`, or is the service reloading the latest version blindly?

### Step 3 — Classify the Conflict

1. **Stale user edit:** return 409/412 and guide user to reload, compare, or merge.
2. **Idempotent background transform:** reload, recompute, and perform bounded retry.
3. **Business state changed:** halt and re-evaluate workflow validity.
4. **Document deleted:** return Not Found per API policy.
5. **Legacy record missing version:** execute migration/compatibility plan.
6. **Non-version-aware writer:** fix the write path or enforce direct CAS.

### Step 4 — Protect Side Effects

- Verify request idempotency.
- Never re-publish messages or re-charge payments when prior outcomes are uncertain.
- Reconcile downstream state, audit trails, and outbox records.

### Step 5 — Monitor and Improve

- Add stale-form and two-copy regression tests.
- Measure conflict rates and hotspot contention.
- Evaluate atomic operators or splitting aggregates.
- Add compare-and-resolve UX for manual edits.

## 46. Common Misconceptions

| Misconception | Why It Is Wrong | Accurate Understanding |
| --- | --- | --- |
| "MongoDB single-document writes are atomic, so lost updates can't happen" | Atomic writes do not protect read–modify–write across stale snapshots | Requires CAS/`version` or atomic operators |
| "`@Version` creates a long-lived database lock" | Uses an optimistic version predicate at write time | Never locks user forms |
| "With `@Version`, the API doesn't need to send version" | Reloading latest then saving still overwrites stale forms | Client must pass `expectedVersion`/ETag |
| "Checking version via `findById` is enough" | Race window remains between read and write | CAS predicate must live inside the update |
| "`@Version` blocks all raw MongoDB updates" | MongoDB server ignores Java annotations | All writers must honor the version contract |
| "Call `setVersion(v + 1)` before `save`" | Framework needs the old version to match | Let the repository manage version |
| "`MongoTemplate.updateFirst` performs CAS automatically" | It may increment version without adding `expectedVersion` to the filter | Add the version predicate explicitly |
| "On conflict, just retry the old form" | Overwrites someone else's edits | Reload and apply an explicit merge policy |
| "409 means the server is down" | Data conflict is a valid business outcome | Clients handle reload/merge |
| "`@Version` guarantees exactly-once emails" | External side effects sit outside the DB write | Use idempotency keys / outbox |
| "`@Version` replaces multi-document transactions" | Protects one entity only | Use transactions or workflows |
| "Transactions make `@Version` useless" | Both solve different problems | They complement each other |
| "Every `deleteById` checks the form's version" | ID-only deletes lack `expectedVersion` | Use conditional deletes |
| "`version` must have its own index" | CAS looks up by unique `_id` and filters `version` | Index only if a query workload needs it |
| "`version` equals `updatedAt`" | Timestamps are not reliable concurrency counters | Separate auditing from CAS |
| "Matching version means every state transition is valid" | Domain invariants are independent | Validate status, permissions, and rules |
| "Legacy data without `version` is automatically safe" | Can be treated as a new entity/insert | Plan controlled version backfills |
| "Every update increments version identically" | Varies by operation and framework version | Verify code paths and tests |
| "Conflicts are always bugs to eliminate" | They prevent silent data loss | Measure and reduce real contention |
| "`@Version` authorizes edits" | Not a security token | Enforce AuthN/AuthZ independently |

## 47. Exercises and Answers

### Exercise 1. Lost Update

Two services both read an entity at version 3. Service A saves successfully; Service B saves its stale copy. With `@Version` and an acknowledged write concern, what happens?

**Answer:** A updates the document and bumps version. B no longer matches version 3 and fails with an optimistic locking failure; A's edit is not silently overwritten.

### Exercise 2. Importing the Annotation

Which annotation should a Spring Data MongoDB entity use?

**Answer:** `org.springframework.data.annotation.Version`, not the JPA annotation.

### Exercise 3. Why Reading Version Alone Is Insufficient

A developer reads version 4, sees it matches, then updates solely by `_id`. Is there still a race?

**Answer:** Yes. Another request can mutate the document between read and write. The version check must sit inside the same atomic update.

### Exercise 4. `@Version` and Client Forms

User A opens form v4; User B saves v5. When A submits, the service calls `findById()` to load v5 and saves A's form fields. Does this catch the stale form?

**Answer:** No. The service used v5 as its expected version. The client must send v4 (the version it edited) and the server must validate/CAS against v4.

### Exercise 5. HTTP Status Codes

An API detects a stale `expectedVersion`. Which status codes are standard?

**Answer:** `409 Conflict` for domain-level conflicts; `412 Precondition Failed` when HTTP `If-Match` fails. Keep the contract consistent.

### Exercise 6. `Repository.save()`

When using `repository.save(entity)` with `@Version`, should you increment `version` manually beforehand?

**Answer:** No. Spring Data manages `version` on the save path; incrementing manually causes the CAS filter to look for the wrong version.

### Exercise 7. `MongoTemplate.updateFirst()`

The filter checks only `_id` while the `Update` increments `version`. Does that implement CAS against stale writes?

**Answer:** No. Incrementing `version` alone is not enough; the query filter must also match `expectedVersion`.

### Exercise 8. Matched Count

A CAS update returns `matchedCount = 0`. Does that prove the document was deleted?

**Answer:** No. The document may still exist with a newer version. A follow-up read and error-classification policy are needed.

### Exercise 9. `findAndModify`

To run CAS and return the post-update document, which option should you set?

**Answer:** `FindAndModifyOptions.options().returnNew(true)` paired with an ID+version query and a version-incrementing update. Handle `null` when nothing matches.

### Exercise 10. Upsert

When performing CAS on a document that must already exist, should you enable `upsert(true)`?

**Answer:** Usually no. A version mismatch could unexpectedly insert a new document.

### Exercise 11. Raw Driver

A background job executes `updateOne({_id: X}, {$set: {title: ...}})` without incrementing `version`. Does this affect Spring Data `@Version`?

**Answer:** Yes. Spring Data will not know the document changed, allowing a stale save to overwrite it later. Every writer must honor the concurrency contract.

### Exercise 12. Counters

1,000 users concurrently increment page views. Should you use `save(count + 1)` with `@Version` and retries, or `$inc`?

**Answer:** Atomic `$inc` is far better for counters, avoiding lost increments and pointless contention retries.

### Exercise 13. Decrementing Stock

You need to reserve 3 units if at least 3 are available. Is checking `version` alone sufficient?

**Answer:** No. Enforce the domain predicate `available >= 3` inside the atomic update (alongside `version` if policy requires).

### Exercise 14. Different Fields

User A edits `title` and User B edits `body` from the same version. Why does one still hit a conflict?

**Answer:** `version` tracks the whole document. The mechanism does not assume disjoint edits are independent; merging requires an explicit domain policy.

### Exercise 15. Retries

A service catches a conflict and immediately calls `save(staleEntity)` in a loop. Is this correct?

**Answer:** No. Reload the latest version and recompute/merge per domain rules; use bounded retries only when safe.

### Exercise 16. External Payments

Code calls a payment gateway, then saves an entity and hits a version conflict. What is the danger of auto-retrying the whole method?

**Answer:** Charging the customer multiple times. Use idempotency keys, outbox/side-effect management, and reconciliation for uncertain outcomes.

### Exercise 17. Transactions

Does `@Version` on `Order` guarantee that updating `Inventory` and inserting `Payment` succeed or roll back together?

**Answer:** No. Use multi-document transactions or a coordinated workflow where supported.

### Exercise 18. Deletes

A delete API takes only an ID while the form was opened on an older version. Can `deleteById(id)` alone detect stale forms?

**Answer:** Not reliably. Accept `expectedVersion`/ETag and execute a conditional delete.

### Exercise 19. Primitive Versions

What is the difference between `long version` and `Long version`?

**Answer:** Primitive `long` cannot be `null` and defaults to `0`; wrapper `Long` can be `null`. Spring Data uses different new-entity detection and initialization rules for each.

### Exercise 20. Legacy Records

Documents created before adding `@Version` lack a `version` field. Can you deploy the new code assuming every `save()` is safe?

**Answer:** No. Plan data migration, test new-vs-existing entity detection, and coordinate legacy writers.

### Exercise 21. Unique Indexes

A collection has a unique `_id` index. Does that prevent lost updates?

**Answer:** No. Unique indexes prevent duplicate IDs, not sequential writes overwriting stale reads.

### Exercise 22. Version Index

Must you create `{version: 1}` for repository CAS to work?

**Answer:** No. CAS looks up by unique `_id` and filters `version` on that document; a standalone index on `version` is not required.

### Exercise 23. Auditing

Are `updatedAt` and `version` equivalent?

**Answer:** No. Timestamps serve auditing; numeric `version` serves CAS. Precision and clock behavior differ.

### Exercise 24. Multi-Instance

Two Spring Boot instances in separate JVMs save version 6 of the same entity. Is `synchronized` inside each instance enough?

**Answer:** No. JVM locks do not coordinate across processes; MongoDB CAS on `version` provides the shared check.

### Exercise 25. Write Concern

Why must you avoid `w: 0` with optimistic locking?

**Answer:** Without acknowledged write results, the client cannot reliably tell whether the version condition matched.

### Exercise 26. Conflicts Are Not Data Loss

An endpoint sees more 409s after adding `@Version`. Should you remove the version check to lower error counts?

**Answer:** No. Those conflicts are likely preventing lost updates. Investigate contention, UX, partial updates, and retry policies instead.

### Exercise 27. Status Transitions

Order version 4 currently has status `PAID`. A request wants to transition it to `SHIPPED`. Is matching `version == 4` alone enough?

**Answer:** Not necessarily. Also require `status == "PAID"` and relevant business invariants in the atomic predicate/logic.

### Exercise 28. ETag

The server returns `ETag: "v4"`, the client sends `If-Match: "v4"`, and the resource is already at v5. Which HTTP status code fits?

**Answer:** `412 Precondition Failed` when following `If-Match` semantics.

### Exercise 29. Proper Testing

An integration test creates two copies at v0 and saves A then B. What is the key invariant to assert?

**Answer:** Only one save from the shared stale version succeeds; the other is rejected, and the winner's changes are preserved.

### Exercise 30. Business Approval

Two requests both hold valid `expectedVersion` values at their respective times. One tries to move status `APPROVED` → `DRAFT`, which the workflow forbids. Does `@Version` block this?

**Answer:** No. `@Version` only protects concurrency tokens, not state machines or authorization. Enforce business validation separately.

## 48. Project Checklist for Adopting @Version

### Mapping and Persistence

- [ ] Use `org.springframework.data.annotation.Version` on MongoDB entities.
- [ ] Choose an appropriate numeric type, usually nullable `Long`.
- [ ] Let Spring Data manage `version` during entity saves.
- [ ] Verify initial insert/version behavior with integration tests.
- [ ] Establish a migration plan for legacy documents missing `version`.
- [ ] Align all writers and migrations on the shared version contract.
- [ ] Use an acknowledged write concern so CAS failures are reported.

### API and UI

- [ ] `GET` responses expose `version` or `ETag` when stale-form detection is needed.
- [ ] Update requests carry `expectedVersion` or `If-Match`.
- [ ] APIs never bind arbitrary raw client fields straight onto persistence entities.
- [ ] Database CAS runs at write time, not just an early read check.
- [ ] Return clear 409/412 responses instructing clients to reload/merge.
- [ ] UI preserves unsaved user input and displays fresh state on conflict.
- [ ] Conflict responses never leak unauthorized data.

### Updates and Business Logic

- [ ] Clearly separate full saves from partial updates.
- [ ] For `updateFirst`/`findAndModify`, include the `version` predicate when CAS is required.
- [ ] For raw driver writes, increment `version` in the same atomic update.
- [ ] Never enable `upsert` unintentionally on CAS updates.
- [ ] Use atomic `$inc`/`$addToSet` where appropriate instead of full-document CAS.
- [ ] Enforce business invariants, statuses, and authorization alongside `version`.
- [ ] Protect deletes and soft deletes with `expectedVersion` when stale UI state matters.
- [ ] Never treat `@Version` as a multi-document transaction.

### Retries, Testing, and Operations

- [ ] Keep retries bounded, reloading and recomputing rather than re-saving stale entities blindly.
- [ ] Protect external side effects with idempotency keys or the outbox pattern.
- [ ] Test two-copy conflicts and stale-form HTTP flows.
- [ ] Test concurrent multi-instance requests where critical.
- [ ] Monitor conflict rates, retries, and user impact.
- [ ] Evaluate contention and performance before splitting aggregate boundaries.
- [ ] Maintain a runbook distinguishing conflicts, deletions, timeouts, and write-concern errors.

## 49. Summary

**`@Version` in Spring Data MongoDB** provides **optimistic locking** to stop previously read entities from silently overwriting newer versions. Along supported `Repository.save()` and `MongoTemplate.save()` paths, Spring Data includes the current version in the write predicate, increments it upon success, and throws **`OptimisticLockingFailureException`** when it no longer matches.

Yet the annotation **does not solve every concurrency scenario on its own**. A service that reloads the newest version right before saving will still overwrite a **stale HTTP form** unless the client supplies **`expectedVersion`/`ETag`**. A background job writing through the raw driver without incrementing `version` blinds Spring Data writers to its changes. And when updating a single field or enforcing state invariants, a **conditional atomic update** combining ID, version, and business predicates is often cleaner than a full-document save.

When conflicts happen, never blindly retry stale payloads. Instead, **reload, compare, apply an explicit merge policy, or return 409/412** to the caller. Use bounded retries only when operations can be safely recomputed, keep external side effects idempotent, and use dedicated transactions or workflows for multi-document invariants.

Keep the core rule in mind: **"only write if the version you read is still current."** That check must execute inside the **same atomic database update**, and every write path touching the document must obey the same contract. Applied consistently, optimistic locking surfaces conflicts explicitly instead of silently losing user data.

### Official References

- [Spring Data MongoDB Reference — Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking)
- [Spring Data MongoDB Reference — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)
- [Spring Data MongoDB Reference — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html)
- [Spring Data MongoDB — MongoRepository API](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — updateOne](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [HTTP Semantics — If-Match and Precondition Failed](https://www.rfc-editor.org/rfc/rfc9110.html)
