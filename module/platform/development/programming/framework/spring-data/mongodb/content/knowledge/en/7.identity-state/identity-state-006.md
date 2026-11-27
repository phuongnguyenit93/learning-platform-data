# Distinguishing Missing IDs From Existing Documents

In MongoDB, the `_id` field identifies a document within **a collection**. In a Java application using **Spring Data MongoDB**, an object's `id` field may be auto-generated, pre-assigned by the application, or loaded from stored data. However, **having an ID does not mean a corresponding document already exists in the database**.

This distinction is decisive across creation, modification, replacement, and create-or-update workflows. For example, an application pre-assigns the code `"ORD-2026-001"` to a new order; this code exists in Java memory, yet the database might not contain that document yet. Calling the wrong API can cause the application to unintentionally insert, overwrite, or resurrect a deleted document.

This lesson belongs to the **Identity and State** chapter of the `SPRING_DATA_MONGODB` module. This knowledge underpins document mapping, using `MongoTemplate` or repositories, query/update design, optimistic locking, transactions, reactive access, testing, and data diagnostics.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish four concepts: **assigned ID**, **document existence in the collection**, **entity considered new by Spring Data**, and **business operation intent**.
2. Understand `@Id`, `@MongoId`, `_id` mapping, and automatic ObjectId generation.
3. Explain how Spring Data determines `isNew` with `@Id`, `@Version`, or the `Persistable` interface.
4. Choose among `insert`, `save`, `updateFirst`, `findAndModify`, and `upsert` based on create vs. update requirements.
5. Interpret `existsById`, `findById`, `matchedCount`, `modifiedCount`, `upsertedId`, and exceptions.
6. Prevent lost updates, duplicate creations, resurrection of deleted documents, and race conditions in existence checks.
7. Design appropriate APIs and test suites for both auto-generated and application-assigned IDs.

## 2. Four States That Must Be Kept Separate

When writing a Spring Data MongoDB service, never use a single boolean like `hasId` as a stand-in for every state question.

| Question | Scope | Example |
| --- | --- | --- |
| Does the Java object **have an ID value**? | **In-memory** state | `entity.getId() != null`. |
| Does the collection contain a document for that ID? | **Database state at read time** | `repository.existsById(id)`. |
| Does Spring Data **treat the entity as new**? | Mapping/framework rules | `@Id`, `@Version`, or `Persistable.isNew()`. |
| Does the user want to **create**, **edit**, or **upsert**? | **Business** rule | POST create-only, PATCH update-only, import with upsert. |

Example:

```text
Java object:  { id: "CUS-42", name: "Lan" }
Database:     customers collection does not have _id = "CUS-42"

Conclusions:
- Java object has an ID                  -> TRUE
- Document already exists in MongoDB     -> FALSE
- This may be a new business entity      -> TRUE
- Choice of insert/save/upsert           -> DEPENDS ON business intent
```

An ID can be generated with a UUID as soon as a request arrives. Generating a UUID writes nothing to MongoDB. Conversely, a document may already exist while a Java entity currently has `id == null` because the application omitted the ID during DTO mapping, instantiated a fresh object, or used the wrong ID format.

### Scenario Matrix

Assume the document belongs to the `customers` collection, has no `@Version`, and uses default ID-based detection:

| Java `id` | Document in DB | Spring Data treats entity as new by default? | Key Takeaway |
| --- | --- | --- | --- |
| `null` | Does not exist under a new ID | **Yes** | An ID may be generated on insert. |
| `"CUS-42"` | Does not exist | **No** | An assigned ID makes the framework infer "not new" even though DB is empty. |
| `"CUS-42"` | Exists | **No** | Fits update operations, though concurrency still needs handling. |
| `null` | Another document holds the same business data | **Yes** | Generating a new ID does not prevent duplicate emails/external codes without unique indexes. |

This table reflects the **default `isNew` rule**, not a claim that the framework queries the database before every write.

## 3. MongoDB `_id` and Spring Data ID Mapping

### 3.1. MongoDB Requires `_id` on Every Document

MongoDB stores documents with an `_id` field. The `_id` value must be unique **within the collection**. It can be an ObjectId, string, or another valid BSON type within MongoDB's constraints.

```javascript
db.customers.insertOne({
  _id: "CUS-42",
  name: "Lan",
  status: "ACTIVE"
});
```

If the collection already contains a document with the same `_id`, another insert triggers a **duplicate key error**; it does not turn into an update.

An ObjectId is an **identifier**, not proof that a document exists in the DB. You can instantiate an ObjectId in your application and never insert it.

### 3.2. `@Id` and `ObjectId`

Spring Data MongoDB can map a Java `id` field to MongoDB `_id`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("customers")
public class Customer {
    @Id
    private String id;
    private String name;

    public Customer() {}

    public Customer(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}
```

A `String` field annotated with `@Id` is typically converted automatically by the converter into a BSON `ObjectId` **if the string is a valid hex ObjectId**. If it cannot be converted, the value can be kept as a string. This causes subtle bugs if some records in a collection store `_id` as ObjectId while others store `_id` as string despite looking identical.

Example:

```text
Java id = "507f1f77bcf86cd799439011"

With @Id String:
  MongoDB _id is typically ObjectId("507f1f77bcf86cd799439011")

With @MongoId String:
  MongoDB _id is stored as string "507f1f77bcf86cd799439011"
```

These two values have **different BSON types**, so you should not assume a raw string lookup across tools will yield the same result.

### 3.3. Using `@MongoId` to Control the ID Type

```java
import org.springframework.data.mongodb.core.mapping.MongoId;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("external_orders")
public class ExternalOrder {
    @MongoId
    private String id;

    private String description;

    public ExternalOrder() {}

    public ExternalOrder(String id, String description) {
        this.id = id;
        this.description = description;
    }
}
```

`@MongoId` without arguments keeps string IDs as strings, even when the string happens to resemble a hex ObjectId. If you truly want `@Id`-like conversion, specify `@MongoId(FieldType.OBJECT_ID)` on a compatible type.

When integrating legacy data, **verify the actual type of `_id`** before changing annotations. Changing entity annotations without migrating data can cause `findById`/`existsById` to miss documents that still exist.

### 3.4. An Auto-Generated ID Does Not Mean Immediately Saved

If an entity has `@Id String id` with `id == null`, an appropriate insert/save can generate a BSON ObjectId and assign the corresponding string back to the entity. This commonly applies to `String`, `ObjectId`, and `BigInteger` under default mapping.

```java
Customer newCustomer = new Customer(null, "Lan");
Customer saved = mongoTemplate.insert(newCustomer);

// After a successful insert, saved.getId() has a value.
System.out.println(saved.getId());
```

However, **not every ID type auto-generates cleanly for every Java model**. If you want `Long` IDs or business codes like `CUS-2026-001`, the application usually has to generate/assign a compatible value before insert. A JPA-style `@GeneratedValue` does not turn MongoDB into a relational sequence generator.

Never treat "an ID that looks valid" as proof that an insert succeeded.

## 4. How Does Spring Data Detect New Entities?

At the repository layer, Spring Data must decide whether an entity takes the **insert** branch or the **save** branch. This classification relies on entity metadata, **not an `existsById` query before every write**.

| Rule | What Spring Data Checks | When Is It Considered New? |
| --- | --- | --- |
| **No `@Version`, default by `@Id`** | The entity's ID | ID is `null` (or `0` for primitive types under general rules). |
| **Has `@Version`** | The version value | Wrapper version `null` or primitive version `0` is considered new. |
| **Implements `Persistable`** | Result of `isNew()` | The entity decides via `isNew()`. |

### 4.1. Pre-Assigned ID Where Entity Is Still New

```java
Customer customer = new Customer("CUS-42", "Lan");
System.out.println(customer.getId() != null); // true
```

Without `@Version` or `Persistable`, Spring Data classifies `customer` as **not new** by default simply because its ID is non-null. That is an **application-tier assumption**; MongoDB might not hold `_id: "CUS-42"` yet.

This causes the common misconception: "because `save()` received an object with an ID, the DB must already have the document."

### 4.2. `@Version` Adjusts New-Entity Detection

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("members")
public class Member {
    @Id
    private String id;

    private String displayName;

    @Version
    private Long version;

    public Member() {}

    public Member(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public String getId() { return id; }
    public String getDisplayName() { return displayName; }
    public Long getVersion() { return version; }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

With:

```java
Member member = new Member("member-42", "Lan");

// id = "member-42"
// version = null
Member saved = memberRepository.save(member);
```

In the repository, `@Version Long version == null` signals that the entity is **new**, even though the ID is already assigned. The write branch will be **insert**. If the collection already contains `_id = "member-42"`, insert raises a duplicate key error. If insert succeeds, the framework initializes the starting version, typically `0` for wrapper types like `Long`.

Note: with primitive version types like `long`, the new-state rule and initial value differ. For this lesson and pre-assigned IDs, wrapper `Long` clearly represents "unsaved" via `null`.

### 4.3. `Persistable.isNew()` Lets the Entity Decide

If IDs are always assigned by the application, you can implement `org.springframework.data.domain.Persistable<ID>`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.domain.Persistable;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("invoices")
public class Invoice implements Persistable<String> {
    @Id
    private String id;

    private long totalCents;

    @Transient
    private boolean newlyCreated = true;

    public Invoice() {}

    public Invoice(String id, long totalCents) {
        this.id = id;
        this.totalCents = totalCents;
    }

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newlyCreated;
    }

    public void markPersisted() {
        newlyCreated = false;
    }
}
```

The `newlyCreated` field is annotated with `@Transient` so it is **not written to MongoDB**. When saving or loading an existing document, the application must flip this flag to `false` using lifecycle callbacks or appropriate rehydration logic.

Example callbacks for the mutable entity above:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.mapping.event.AfterConvertCallback;
import org.springframework.data.mongodb.core.mapping.event.AfterSaveCallback;

@Configuration(proxyBeanMethods = false)
class InvoiceCallbacks {

    @Bean
    AfterConvertCallback<Invoice> invoiceLoaded() {
        return (invoice, document, collection) -> {
            invoice.markPersisted();
            return invoice;
        };
    }

    @Bean
    AfterSaveCallback<Invoice> invoiceSaved() {
        return (invoice, document, collection) -> {
            invoice.markPersisted();
            return invoice;
        };
    }
}
```

This example only illustrates maintaining the flag for repositories when reading/writing through Spring Data. Additional constructor/hydration design is needed for immutable entities or code paths bypassing callbacks. If `isNew()` always returns `true`, every `repository.save` call attempts an **insert**, causing duplicate key errors once the document exists.

**Which approach should you choose?**

- Auto-generated ID and simple model: use default `@Id`-based detection.
- Pre-assigned ID with optimistic locking needed: consider `@Version`.
- Complex creation rules or specialized requirements: `Persistable` with carefully managed lifecycle state.
- Guaranteed create-only or update-only behavior: choose the **right write API** rather than relying solely on `isNew`.

## 5. `Repository.save` Does Not Mean "Update Only"

The standard `SimpleMongoRepository.save` implementation can be summarized conceptually as:

```java
// Illustrates branch selection logic, not code you need to write:
if (entityInformation.isNew(entity)) {
    return mongoOperations.insert(entity, collectionName);
}
return mongoOperations.save(entity, collectionName);
```

In MongoDB, `mongoOperations.save` on an entity **without optimistic locking** can behave like an **upsert/replacement**: if a document with that ID exists, it is replaced; if not, a new document can be created.

Therefore, when calling `MongoRepository.save` on an entity with an application-assigned ID:

- If Spring Data classifies it as **new**, the repository takes the **insert** branch.
- If Spring Data classifies it as **not new**, the repository delegates to `MongoOperations.save`.
- The second branch **does not guarantee** the document already exists.
- For an entity with `@Version`, optimistic locking adds a version predicate and can fail when the document changed or was deleted; do not generalize unversioned `save` behavior to versioned entities.

### Example: ID Assigned When MongoDB Has No Document Yet

```java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerRepository
        extends MongoRepository<Customer, String> {
}
```

```java
Customer candidate = new Customer("CUS-42", "Lan");
Customer saved = customerRepository.save(candidate);
```

Without `@Version` or `Persistable`, when MongoDB does not yet have `CUS-42`, this call can **create a new document** even though Spring Data classified the entity as "not new". If MongoDB already had it, the existing document can be **replaced** with the saved entity's contents. That is quite different from "updating just one field".

Watch out for DTOs missing fields: constructing a new entity with only `id` and `name` and calling `save` risks wiping out other fields of the existing document due to full replacement.

### When to Use `repository.insert`

```java
Customer created = customerRepository.insert(
    new Customer("CUS-42", "Lan")
);
```

`insert` expresses **create-only** intent. If the same `_id` already exists, the operation fails with a duplicate key error (typically translated by Spring into `DuplicateKeyException`) rather than overwriting. When IDs are pre-assigned, `insert` is the clearest choice for create-only endpoints.

## 6. Comparing `insert`, `save`, `updateFirst`, `findAndModify`, and `upsert`

| Operation | When no matching document exists | When a matching document exists | Best Used For |
| --- | --- | --- | --- |
| `MongoTemplate.insert(entity)` | Creates new | Duplicate key if same `_id` | **Create-only** |
| `MongoRepository.insert(entity)` | Creates new | Duplicate key if same `_id` | **Create-only** |
| `MongoRepository.save(entity)` | Follows `isNew` branch; may insert or save/upsert | May fail duplicate insert or save/replace depending on entity state | Saving per repository semantics; requires understanding `isNew` |
| `MongoTemplate.save(entity)` | Usually upserts (when unversioned) | Save/replacement; with `@Version`, applies optimistic locking | Full-entity persistence |
| `MongoTemplate.updateFirst(query, update, type)` | Does **not** create new | Modifies first document matching query | **Update-only** |
| `MongoTemplate.findAndModify(query, update, options, type)` | Does not create new by default | Finds and modifies atomically, can return document | Update-only or upsert **if option enabled** |
| `MongoTemplate.upsert(query, update, type)` | **Creates new** | Updates matching document | **Create-or-update** |

In this table, `save` descriptions reflect standard behavior and can vary with `@Version`, event callbacks, or custom configuration.

### Case 1 — Create Only

Use `insert`. Duplicate key is the exact conflict signal when an ID is pre-assigned and cannot be reused.

```java
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;

@Service
public class CustomerCreationService {
    private final CustomerRepository repository;

    public CustomerCreationService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer create(String id, String name) {
        try {
            return repository.insert(new Customer(id, name));
        } catch (DuplicateKeyException duplicate) {
            throw new IllegalStateException(
                "Customer ID already exists", duplicate);
        }
    }
}
```

In HTTP APIs, map conflicts to HTTP **409 Conflict** when matching your API contract. Never rely on `existsById` followed by `insert` to guarantee uniqueness; only a unique index/`_id` constraint protects reliably under concurrent requests.

### Case 2 — Update Only When the Document Exists

Use an update command with a query targeting the document.

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class CustomerUpdateService {
    private final MongoTemplate template;

    public CustomerUpdateService(MongoTemplate template) {
        this.template = template;
    }

    public boolean renameExisting(String id, String newName) {
        Query query = Query.query(Criteria.where("_id").is(id));
        Update update = new Update().set("name", newName);

        UpdateResult result =
                template.updateFirst(query, update, Customer.class);

        return result.getMatchedCount() == 1;
    }
}
```

If no document matches that ID at write time, `matchedCount == 0` and **no new document is created**. Returning `false` can map to HTTP 404 when a missing target is treated as an error.

**Why check `matchedCount` instead of only `modifiedCount`?** When setting `name` to the same existing value, a document matched even though no field changed. `matchedCount=1`, `modifiedCount=0` still represents a valid update on an existing document.

The example assumes the entity has a string `_id` such as `"CUS-42"`. For other ID types, verify `@Id`/`@MongoId` conversion rules.

### Case 3 — Update Only When State Matches

If an order may transition from `DRAFT` to `SUBMITTED` at most once:

```java
Query query = Query.query(
    Criteria.where("_id").is(orderId).and("status").is("DRAFT")
);
Update update = new Update()
    .set("status", "SUBMITTED")
    .set("submittedAt", java.time.Instant.now());

UpdateResult result =
    mongoTemplate.updateFirst(query, update, Order.class);

if (result.getMatchedCount() != 1) {
    // Order does not exist or is no longer DRAFT.
}
```

The predicate check and state change execute in a single atomic write on **one document**, avoiding a "read status then modify later" race. If you need to distinguish not found from wrong state for error messaging, you can query afterward to build the message, while keeping the write decision anchored on the conditional update result.

### Case 4 — Create or Update: Upsert

```java
Query query = Query.query(Criteria.where("_id").is(customerId));

Update update = new Update()
    .set("name", newName)
    .setOnInsert("createdAt", java.time.Instant.now());

UpdateResult result = mongoTemplate.upsert(
    query, update, Customer.class
);
```

When no document matches, MongoDB inserts a new document; when one matches, it updates the specified fields. `$setOnInsert` applies only on insert, leaving `createdAt` untouched on existing documents.

For a single-document upsert, `result.getUpsertedId() != null` indicates the command inserted a new document (subject to API and acknowledged write concern). `matchedCount` reflects how many existing documents matched before the update.

**Important:** Use upsert only when the business logic **explicitly allows creation**. A PATCH endpoint meant to "edit an existing order only" must never accidentally upsert a deleted order.

### Case 5 — Returning the Document After Update

```java
import org.springframework.data.mongodb.core.FindAndModifyOptions;

Customer updated = mongoTemplate.findAndModify(
    Query.query(Criteria.where("_id").is(customerId)),
    new Update().set("name", newName),
    FindAndModifyOptions.options().returnNew(true),
    Customer.class
);

if (updated == null) {
    // Document not found; does not insert by default.
}
```

`findAndModify` combines a conditional query and returns the before/after document in one atomic command. Remember that enabling `upsert(true)` switches its semantics to creating a document when none matches.

## 7. Optimistic Locking: When a Document Exists but Has Changed

A valid ID and an existing document are still not enough to guarantee a safe update. Two requests can read the same document and modify it concurrently.

Suppose `Member` has `@Version Long version` as in Section 4:

```text
T0: Member(_id="member-42", displayName="Lan", version=0)

T1: Request A reads version=0
T2: Request B reads version=0
T3: A changes name and saves successfully => version=1
T4: B saves its version=0 copy => OptimisticLockingFailureException
```

Spring Data MongoDB adds a version predicate to updates for operations that support optimistic locking. If the version no longer matches, the operation can throw `OptimisticLockingFailureException`; the application avoids silently overwriting newer data.

```java
import org.springframework.dao.OptimisticLockingFailureException;

Member member = memberRepository.findById(id).orElseThrow();
member.setDisplayName("New Name");

try {
    memberRepository.save(member);
} catch (OptimisticLockingFailureException conflict) {
    // Concurrent modification or deletion occurred: report conflict
    // or reload and apply a business retry strategy.
}
```

Important notes:

- Optimistic locking requires an **acknowledged write concern** to reliably detect failure.
- Not every custom update API automatically guards against the version you previously read. When writing custom queries, check how that API handles `@Version`; add an explicit version criterion when needed.
- If the document was deleted after loading, saving a **stale version** typically fails rather than resurrecting it arbitrarily.
- For entities **without `@Version`**, replacement-style `save` can cause lost updates when two requests concurrently modify the full entity.
- Version does not replace unique indexes; two requests creating the same `_id` still require handling duplicate key errors.

### Updating With `expectedVersion` in the Query

```java
Query query = Query.query(
    Criteria.where("_id").is(memberId)
            .and("version").is(expectedVersion)
);

Update update = new Update().set("displayName", newName);

UpdateResult outcome = mongoTemplate.updateFirst(
    query, update, Member.class
);
```

For entities with `@Version`, Spring Data MongoDB can automatically increment the version field on supported update methods when `Update` does not touch version. Do not increment version **twice** by manually calling `inc("version", 1)` alongside automatic incrementing. When `matchedCount == 0`, either the document is missing or the version changed; distinguish them according to your API contract.

## 8. What `existsById` Tells You—and What It Does Not

`existsById(id)` tells you whether a document was found **at the moment that query ran**. It places no lock, does not mark the Java entity as saved, and does not guarantee the document still exists when the next statement executes.

Error-prone pattern:

```java
if (!repository.existsById(id)) {
    repository.save(new Customer(id, "Lan"));
}
```

If two requests run concurrently:

```text
Request A                          Request B
---------                          ---------
existsById("CUS-42") => false
                                   existsById("CUS-42") => false
save(new Customer(...))
                                   save(new Customer(...))
```

Both requests believe the ID does not exist yet; because `save` can upsert/replace, the second request can overwrite the first without raising a duplicate key error.

**Right approach for create-only:** call `insert` directly and catch duplicate key errors. **Right approach for update-only:** run a conditional update and inspect `matchedCount`. **Right approach for create-or-update:** use an explicit `upsert`.

Reading before writing is still necessary for complex business calculations, but it must be paired with update predicates, optimistic locking, or transactions to close the gap between read and write.

## 9. Deleted Documents Coming Back to Life

This is a serious bug when a service uses unversioned `save` as an "edit".

1. User A reads document `_id="CUS-42"`.
2. User B deletes that document.
3. User A edits the name and calls `repository.save`.
4. If execution hits unversioned `save`/upsert semantics, the document can be **re-created**.

This is unintended "resurrection" caused by failing to separate updating an existing document from permission to create one.

Remediation options by requirement:

- **Update-only:** `updateFirst` querying `_id` and business predicates, which does not upsert by default.
- **Optimistic locking:** store version so updates fail when the document changed or was deleted (with version-aware operations).
- **Soft delete:** add `deletedAt` or `status` and filter `deletedAt: null` in queries expecting active documents; keep this consistent across all write paths.
- **Guarantee non-reuse of IDs:** retain history/tombstones or non-reusable ID rules if required by the business; hard-deleting and checking existence before creation does not eliminate race conditions.

Do not delete and then rely on `save` to "restore" unless the API has an explicitly verified recovery workflow.

## 10. REST APIs: Express Intent Explicitly Instead of Guessing From IDs

| Endpoint / Operation | Intent | Suggested Operation | Status When Missing / Duplicate |
| --- | --- | --- | --- |
| `POST /customers` | **Create new** | `insert` | 409 if ID/unique key collides; 201 on creation |
| `PUT /customers/{id}` with **replace-only** contract | **Replace if exists** | Conditional replace/update, **no upsert** | 404 if document does not exist |
| `PUT /customers/{id}` with **create-or-replace** contract | **Intentional upsert** | `upsert` or replace with upsert option | 201 if created, 200/204 if updated per contract |
| `PATCH /customers/{id}` | **Edit subset of fields if exists** | `updateFirst` or `findAndModify` without upsert | 404 if missing |
| `DELETE /customers/{id}` | **Delete** | Conditional delete by ID/version per business rules | 404 or 204 if absent per contract |
| External data import/sync | **Create or update** | Upsert with appropriate unique key | Record accurate inserted/updated counts |

These HTTP codes are API design choices, not mandatory Spring Data behavior. What matters is stating clearly **whether a missing document should be created or rejected**.

### Distinguishing ID From Business Keys

A customer may have:

```json
{
  "_id": "CUS-42",
  "email": "lan@example.test",
  "displayName": "Lan"
}
```

A unique `_id` does not protect `email`. If emails must be unique, create a **unique index** and handle duplicate key errors accordingly. Checking `existsByEmail` before `insert` is insufficient against concurrent conflicts.

Similarly, when syncing from external systems, design stable IDs or appropriate unique keys for safe, idempotent upserts. Never treat the absence of a business code in a cache as proof that the collection does not already hold that record.

## 11. Reading With the Right Type and Collection

When `findById` returns `Optional.empty()`, several causes must be checked:

- The document truly does not exist in the collection.
- The connection points to a different **database** or **collection**.
- The Java ID was converted to `ObjectId`, whereas the document stored `_id` as a string (or vice versa).
- The data was just deleted, or read preference/consistency did not match business timing expectations.
- Additional query filters (if any) did not match, such as excluding soft-deleted documents.

Debugging example in the Mongo shell:

```javascript
db.customers.findOne({ _id: "CUS-42" });

// Only to illustrate BSON differences:
db.customers.findOne({
  _id: ObjectId("507f1f77bcf86cd799439011")
});
db.customers.findOne({
  _id: "507f1f77bcf86cd799439011"
});
```

The last two queries look for **two different BSON types**. Check `@Id`/`@MongoId` annotations and Spring Data conversions rather than merely comparing logged strings.

If repository `findById` returns empty while a raw `MongoTemplate` query returns the document, first inspect mapping, collection name, and ID type; do not rush to "fix" it by creating a new document.

## 12. Reactive Spring Data MongoDB Faces the Same Problem

With reactive access, `ReactiveMongoRepository` and `ReactiveMongoTemplate` return `Mono`/`Flux`, yet the core concepts remain identical:

- An assigned ID does not prove the database contains a document.
- `save` follows repository semantics and state detection; `insert` clearly expresses create-only.
- `updateFirst` does not upsert automatically; check the matched document count.
- Two-step existence-check-then-write in reactive pipelines is still vulnerable to race conditions.

Example:

```java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

public interface ReactiveCustomerRepository
        extends ReactiveMongoRepository<Customer, String> {
}
```

```java
reactiveCustomerRepository.insert(new Customer("CUS-42", "Lan"))
    .onErrorMap(
        org.springframework.dao.DuplicateKeyException.class,
        ex -> new IllegalStateException("Customer ID already exists", ex)
    );
```

Do not call `block()` arbitrarily inside reactive pipelines. For conditional updates, `ReactiveMongoTemplate` provides reactive equivalents; inspect `matchedCount` when `Mono<UpdateResult>` emits.

## 13. Testing Commonly Confused Scenarios

When building integration tests, use a dedicated collection/database. You can use a MongoDB test container running the same target MongoDB Server series. Test these scenarios:

| Scenario | Operation | Expectation |
| --- | --- | --- |
| **Null ID, create-only** | `insert(new Customer(null, ...))` | Generates an appropriate ID and persists the document. |
| **Pre-assigned ID, empty DB** | `insert(new Customer("CUS-42", ...))` | Creation succeeds. |
| **Pre-assigned ID, existing doc** | `insert` with same ID | Duplicate key error; old document is not overwritten. |
| **Pre-assigned ID, empty DB** | `repository.save` on unversioned entity | May upsert a new document; do not treat as update-only. |
| **Pre-assigned ID, empty DB** | `updateFirst` | `matchedCount == 0`, no new document created. |
| **Pre-assigned ID, empty DB** | `upsert` | Creates new document; observe `upsertedId`. |
| **`@Version` null, pre-assigned ID** | `repository.save` on versioned entity | Takes insert branch; existing same ID triggers duplicate key. |
| **Stale version** | Two saves of copies with the same initial version | Second save fails with optimistic locking conflict. |
| **Document deleted after read** | Update-only without upsert | Deleted document is not resurrected unintentionally. |
| **Different `@Id` vs `@MongoId`** | Query 24-character hex string | Reveals BSON type mismatch; aligns mapping. |
| **Two concurrent creates** | Concurrent `insert` with the same ID | One succeeds, one fails with duplicate key. |
| **Two check-then-save requests** | Same ID, unversioned | Can overwrite; tests must expose the flaw. |

### Sample Test: Rejecting Duplicate IDs

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DuplicateKeyException;

@SpringBootTest
class CustomerIdentityIntegrationTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void insertRejectsDuplicateId() {
        // Use a unique ID per run to avoid depending on stale data.
        String id = "CUS-" + java.util.UUID.randomUUID();

        repository.insert(new Customer(id, "Lan"));

        assertThatThrownBy(() ->
            repository.insert(new Customer(id, "Minh"))
        ).isInstanceOf(DuplicateKeyException.class);

        Customer stored = repository.findById(id).orElseThrow();
        assertThat(stored.getName()).isEqualTo("Lan");
    }
}
```

This test requires an actual test MongoDB configured; the sample code assumes a project with Spring Boot test starter and the declared repository. Run tests in an environment with write access and synthetic data containing no real personal information.

### Sample Test: Update Does Not Create Missing Documents

```java
@Test
void updateOnlyDoesNotCreateMissingDocument() {
    String id = "CUS-" + java.util.UUID.randomUUID();

    UpdateResult result = mongoTemplate.updateFirst(
        Query.query(Criteria.where("_id").is(id)),
        new Update().set("name", "Lan"),
        Customer.class
    );

    assertThat(result.getMatchedCount()).isZero();
    assertThat(customerRepository.existsById(id)).isFalse();
}
```

In an actual test class, inject `MongoTemplate` and `CustomerRepository`, and add imports for `Query`, `Criteria`, `Update`, `UpdateResult`, and AssertJ. Both tests prove **create-only** and **update-only** semantics rather than merely checking that calls do not throw exceptions.

## 14. Common Misconceptions

**"If ID is non-null, the document must already exist."**  
False. The ID could have been pre-assigned or generated in memory without ever being written to MongoDB.

**"`Repository.save` always updates an existing record."**  
False. The repository relies on `isNew` to pick a branch; `MongoOperations.save` can upsert when unversioned. Update-only endpoints should use non-upserting commands.

**"Adding `@Version` makes every operation automatically safe."**  
No. Optimistic locking applies to operations that support it; custom update queries and external writers must follow the same rules to prevent conflicts.

**"`existsById=false` followed by `insert` guarantees no duplicates."**  
No. Another request can insert between those two calls. Rely on unique constraints and catch duplicate errors.

**"`modifiedCount=0` means the document does not exist."**  
No. The document may have matched while the new value equaled the old value. Use `matchedCount` to determine whether a document matched.

**"If `findById` returns nothing, just `save` a new one."**  
No. Check the database/collection, `_id` conversion, deletion state, and business creation policy.

**"`save` on update won't erase other fields."**  
Do not assume that. Saving an entire entity can replace the document; when updating specific fields, use `Update.set` with an appropriate query.

## 15. Practice Exercises

### Exercise 1 — ID Assigned but Not Yet Saved

Instantiate `Customer("CUS-77", "Ha")` without inserting it. Predict the expected results of:

1. `customer.getId() != null`.
2. `repository.existsById("CUS-77")` (assuming an empty DB).
3. `repository.save(customer)` on an unversioned entity.
4. `repository.insert(customer)` if `save` in step 3 succeeded.

Explain why Java state, database state, and `isNew` must be distinguished.

### Exercise 2 — Choosing APIs by Contract

Design three methods: `createOnly`, `updateOnly`, and `upsertAllowed`. Each accepts `id` and `name`. Choose the right MongoDB API, how to handle duplicate IDs or missing documents, and the corresponding HTTP statuses.

### Exercise 3 — `@Version` With Assigned IDs

Use the `Member` entity with `id = "member-22"` and `version = null`. Predict the repository's insert/save branch choice and the version after insert. Then execute two concurrent read-modify-save flows to observe optimistic locking.

### Exercise 4 — ID Mapping Causing Lookup Failures

Create two documents in a test environment: one with an ObjectId `_id` and one with a string `_id` sharing the same hex display string. Test `@Id String` and `@MongoId String` entities; explain which query matches which value.

### Exercise 5 — Deleted Order Reappears

One request reads Order A, another deletes Order A, and then the first calls `save`. Analyze the outcome with and without `@Version`; propose ways to prevent unintended document resurrection.

### Answer Hints

1. The object has an ID, the DB is initially empty, default `isNew` evaluates "not new" because ID is non-null; `save` can create the document via upsert; the subsequent `insert` collides on ID.
2. Create-only → `insert`; update-only → `updateFirst`/`findAndModify` without upsert; create-or-update → explicit `upsert`.
3. Wrapper `@Version Long` null → detected as "new" and inserted. Once persisted and version advances, saving a stale copy raises an optimistic locking conflict.
4. BSON ObjectId and string are distinct types; ID mapping must align with stored data.
5. Unversioned `save` can recreate the document; use update-only operations, optimistic locking, or an appropriate soft-delete mechanism.

## 16. Pre-Release Feature Checklist

- [ ] Determine whether IDs are auto-generated by MongoDB or pre-assigned by the application.
- [ ] Verify `@Id` or `@MongoId` and the actual BSON type of `_id`.
- [ ] Clarify entity state detection via ID, `@Version`, or `Persistable`.
- [ ] Intentionally select create-only, update-only, or upsert semantics.
- [ ] Never use `existsById` before writing as the sole uniqueness guard.
- [ ] Check `matchedCount` to verify a document matched; do not infer from `modifiedCount`.
- [ ] Guard concurrent updates using conditional queries or optimistic locking.
- [ ] Evaluate the risk of deleted documents resurrecting.
- [ ] Verify unique indexes on business keys and idempotency mechanisms.
- [ ] Test null ID, assigned ID, missing document, duplicate ID, stale version, and query mapping cases.
- [ ] Never conclude "does not exist" without confirming the right database/collection/ID type.

## 17. Official References

1. [Spring Data Commons — Entity State Detection Strategies](https://docs.spring.io/spring-data/data-mongo/reference/4.5/repositories/core-concepts.html): `@Id`, `@Version`, and `Persistable` rules.
2. [Spring Data MongoDB — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `insert`, `save`, `upsert`, `@MongoId`, and optimistic locking.
3. [Spring Data MongoDB — MongoOperations API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/MongoOperations.html): write API semantics.
4. [Spring Data MongoDB — SimpleMongoRepository Source](https://github.com/spring-projects/spring-data-mongodb/blob/main/spring-data-mongodb/src/main/java/org/springframework/data/mongodb/repository/support/SimpleMongoRepository.java): how repositories use `isNew` to choose insert vs. save.
5. [Spring Data MongoDB — Entity Lifecycle Events](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html): `AfterSaveCallback` and `AfterConvertCallback`.
6. [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/): enforcing key uniqueness.
7. [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): atomicity and conditional updates.

**Key takeaway:** An ID is merely an **identifier value**. It does not prove MongoDB holds a matching document, and `isNew` is a Spring Data rule evaluated on the entity rather than an implicit existence query. Choose explicit **insert**, **non-upserting update**, or **upsert** semantics, and protect correctness under concurrent operations.
