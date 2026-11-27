# ID Values Returned After Insert or Save

## 1. Why Care About the ID After Writing?

In MongoDB, every document has an **_id** field used to uniquely identify it within a collection. When creating a new document, the application can either supply _id itself or let the persistence layer generate an ID. A very practical question arises: **after calling insert or save, where do you retrieve the persisted ID, and does it match the ID prior to the call?**

In the **SPRING_DATA_MONGODB** module, this question comes up in both **MongoTemplate** and **MongoRepository**. IDs also tie into BSON-to-Java entity mapping, key-based queries, updates, optimistic locking, transactions, reactive access, testing, and diagnosing errors such as duplicate writes or documents not found. Knowing exactly what ID value a write returns lets an application return IDs from APIs, link related documents, and avoid persisting the same entity twice.

**Main takeaway:** High-level insert/save methods in Spring Data MongoDB typically **return the persisted entity**, not a standalone ID. To obtain the ID, read it from the **entity returned by the method**. If the entity is immutable or uses custom mapping, never assume the input object was mutated in place.

After this lesson, you will be able to:

1. Distinguish BSON _id, the Java ID field, and the returned ID value type.
2. Retrieve the ID after **MongoTemplate.insert**, **MongoTemplate.save**, **MongoRepository.insert**, and **MongoRepository.save**.
3. Handle cases where the ID is auto-generated, pre-assigned, or duplicated.
4. Handle IDs properly with mutable, immutable, and reactive entities.
5. Distinguish ID from new/existing state and from **@Version** fields.
6. Write ID lifecycle tests and diagnose unexpected ID behavior.

## 2. How Are MongoDB IDs Represented?

A MongoDB document looks like:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  orderNumber: "ORD-1001",
  customerName: "Lan"
}
~~~

**_id** is the document's identifier field. MongoDB creates a unique index on _id for standard collections; two documents in the same collection cannot share the same _id value. If a document is created without supplying _id, the driver typically generates an **ObjectId**. MongoDB can also use other valid ID types such as String or UUID/Binary depending on application design; ObjectId is a popular choice, not a requirement.

In Java, Spring Data MongoDB typically maps a property annotated with **@Id** to the **_id** field:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;

@Id
private ObjectId id;
~~~

| Concept | Example | Meaning |
| --- | --- | --- |
| BSON Field | _id | Key stored inside the MongoDB document. |
| Java Property | id | Where the entity represents the document key. |
| ObjectId Value | ObjectId("507f1f77bcf86cd799439011") | 12-byte BSON value, usually displayed as 24 hex characters. |
| API String ID | "507f1f77bcf86cd799439011" | Representation at the HTTP/JSON boundary; the string itself is not a BSON ObjectId. |
| Returned ID Value | saved.getId() | ID read from the entity returned by the save operation. |

An important note: **an ObjectId and a String with identical display characters still have different BSON types**. Querying with a plain string may fail to find a document whose _id is an ObjectId if type conversion is not performed. Establish a consistent ID policy right from the entity declaration.

## 3. What Do `insert` and `save` Return?

In common Spring Data MongoDB APIs, these methods return the entity:

| API | Illustrative Signature | Where Do You Get the ID? |
| --- | --- | --- |
| MongoTemplate.insert | T insert(T objectToSave) | Read the ID from the returned object. |
| MongoTemplate.save | T save(T objectToSave) | Read the ID from the returned object. |
| MongoRepository.insert | S insert(S entity) | Read the ID from the returned entity. |
| MongoRepository.save | S save(S entity) | Read the ID from the returned entity. |
| ReactiveMongoTemplate.insert/save | Mono<T> | Read the ID when the Mono emits the persisted entity. |
| ReactiveMongoRepository.insert/save | Mono<S> | Read the ID inside the reactive stream after a successful write. |

General pattern:

~~~java
OrderDocument saved = repository.insert(order);
ObjectId id = saved.getId();
~~~

This differs from the lower-level MongoDB Java Driver: **insertOne** returns an **InsertOneResult** and can expose **getInsertedId()**. Do not confuse the driver's return type with MongoRepository or MongoTemplate.

### 3.1. Difference in Intent Between `insert` and `save`

- **insert** expresses the intent to create a new document. If _id collides with an existing document, MongoDB reports a duplicate key error instead of overwriting it.
- **save** generally persists entity state. For a new entity, it can result in an insert; for an entity with an ID, depending on the API, new-entity detection, and optimistic locking, it can execute a replace/update or upsert.
- **MongoTemplate.save** usually replaces the document by _id or inserts when none exists, whereas **MongoRepository.save** uses entity state information to pick the insert or save path. Thus, never infer from the name `save` that a single driver command is always used.

**Both can return an entity carrying an ID.** Yet having an ID does not prove a brand-new document was just created: saving with an existing ID can overwrite an existing record.

## 4. Complete Example: Entity With ObjectId

Define a mutable entity:

~~~java
package com.example.orders;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public class OrderDocument {

    @Id
    private ObjectId id;

    private String orderNumber;
    private Instant createdAt;

    public OrderDocument() {
    }

    public OrderDocument(String orderNumber, Instant createdAt) {
        this.orderNumber = orderNumber;
        this.createdAt = createdAt;
    }

    public ObjectId getId() {
        return id;
    }

    public void setId(ObjectId id) {
        this.id = id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public void setOrderNumber(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }
}
~~~

Before the first write, an instance created via the two-argument constructor has **id == null**:

~~~java
OrderDocument draft = new OrderDocument(
    "ORD-1001",
    Instant.parse("2025-05-20T09:00:00Z")
);
System.out.println(draft.getId()); // null
~~~

During persistence, Spring Data MongoDB and the MongoDB driver process the document, can generate an ObjectId for _id, and return that value on the entity. The specific value changes on each creation, so never hardcode an example ID as an expected test value.

~~~mermaid
sequenceDiagram
    participant A as Java application
    participant S as Spring Data MongoDB
    participant M as MongoDB
    A->>S: insert(entity, id = null)
    S->>M: Insert BSON document
    M-->>S: Acknowledge write with _id
    S-->>A: Result entity has ID
    A->>A: saved.getId()
~~~

**Do not rely on every input entity being mutated directly.** Treat the returned object as the authoritative source of persisted state, especially when using immutable entities or custom converters.

## 5. `MongoTemplate.insert`: Getting the ID After Insert

Example inside a service using `MongoTemplate`:

~~~java
import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;

public class CreateOrderWithTemplate {
    private final MongoTemplate mongoTemplate;

    public CreateOrderWithTemplate(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public ObjectId create(String orderNumber) {
        OrderDocument draft = new OrderDocument(
            orderNumber,
            Instant.now()
        );

        OrderDocument inserted = mongoTemplate.insert(draft);
        ObjectId generatedId = inserted.getId();

        if (generatedId == null) {
            throw new IllegalStateException("Insert returned entity without id");
        }
        return generatedId;
    }
}
~~~

When calling **mongoTemplate.insert(draft)**, Spring Data chooses the collection from **@Document(collection = "orders")**. Returning the generated ID to the API layer lets clients call subsequent lookup endpoints by ID.

For a mutable entity like `OrderDocument`, the mapping layer may assign the ID onto the passed-in object as well. Even so, writing **inserted.getId()** is safer, because Spring Data also supports immutable entities or mappings that yield a separate instance.

### 5.1. Specifying the Collection Directly

`MongoTemplate` has an overload accepting a collection name:

~~~java
OrderDocument saved =
    mongoTemplate.insert(draft, "orders_archive");
ObjectId id = saved.getId();
~~~

The ID is still read from the returned entity. However, the actual document is written into **orders_archive**, not the default **orders** collection in `@Document`. Subsequent reads must target the right database/collection; having the right ID while querying the wrong collection still returns null.

## 6. `MongoTemplate.save`: IDs After Initial Save and Re-Save

The `save` command has two distinct scenarios:

### 6.1. Saving a New Entity With No ID Yet

~~~java
OrderDocument draft = new OrderDocument(
    "ORD-1002",
    Instant.now()
);

OrderDocument saved = mongoTemplate.save(draft);
ObjectId id = saved.getId();
~~~

In the default scenario with a null ObjectId ID, **save can create a new document and return the entity with an assigned ID**.

### 6.2. Saving an Entity That Already Has an ID

~~~java
OrderDocument existing = mongoTemplate.findById(
    id,
    OrderDocument.class
);

if (existing != null) {
    existing.setOrderNumber("ORD-1002-UPDATED");
    OrderDocument savedAgain = mongoTemplate.save(existing);
    ObjectId sameId = savedAgain.getId();
}
~~~

For the same document, **the ID does not increment or change on each save**. The ID represents document identity; changing the order number or other attributes is not a reason to generate a new _id. If you want a separate document, the application must create a new one with an appropriate ID.

### 6.3. Saving With an Application-Supplied ID

~~~java
ObjectId chosenId = new ObjectId();

OrderDocument order = new OrderDocument(
    "ORD-1003",
    Instant.now()
);
order.setId(chosenId);

OrderDocument saved = mongoTemplate.save(order);
System.out.println(saved.getId().equals(chosenId)); // true if write succeeds
~~~

**Having an ID beforehand does not mean the document already exists.** With `MongoTemplate.save` and no `@Version` or extra constraints, the operation can upsert by _id. This makes it easy for an operation intended as an "update" to create a new document instead.

If the business requires "update only an existing document", use a conditional update command, check `matchedCount`, or choose an appropriate concurrency/optimistic locking mechanism rather than relying blindly on `save`.

## 7. `MongoRepository.insert` and `MongoRepository.save`

Repository declaration:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, ObjectId> {
}
~~~

Example usage:

~~~java
import java.time.Instant;
import org.bson.types.ObjectId;

public class RepositoryOrderService {
    private final OrderRepository repository;

    public RepositoryOrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public ObjectId create(String orderNumber) {
        OrderDocument entity = new OrderDocument(
            orderNumber,
            Instant.now()
        );

        OrderDocument inserted = repository.insert(entity);
        return inserted.getId();
    }

    public ObjectId save(OrderDocument entity) {
        OrderDocument saved = repository.save(entity);
        return saved.getId();
    }
}
~~~

In both methods, the ID is retrieved via **getId()** on the returned entity. The repository does not return `ObjectId` directly from insert/save calls.

**Key distinction:** `MongoRepository.save` determines whether an entity is new or existing from Spring Data's entity information, including ID, `@Version`, or the `Persistable` interface if used. Thus:

- An entity with **id == null** is typically treated as new.
- An entity with a non-null ID may be treated as existing, though that is no proof the database holds that record.
- If the entity implements **Persistable**, the result of **isNew()** can govern which persistence path the repository chooses.
- When **@Version** is present, version-based new-entity detection and write-conflict checks also affect how `save` behaves.

Choose `insert` when the intent is **create new without overwriting**. Choose `save` when persisting entity state per repository contract, while clearly understanding your new/existing detection and optimistic locking policies.

## 8. Can You Read the ID Directly From the Input Entity?

This depends on the entity's **mutability** and the mapping mechanism.

### 8.1. Mutable Entities

~~~java
OrderDocument input = new OrderDocument(
    "ORD-1004",
    Instant.now()
);

OrderDocument output = repository.insert(input);

ObjectId reliableId = output.getId();
~~~

With a mutable JavaBean, the ID can often be populated onto the `id` property during a successful write. Still, writing code that depends on **input.getId()** changing in place becomes brittle if you later refactor to records, immutable constructors, or custom converters. Always read resulting state from **output**.

### 8.2. Immutable Entities / Java Records

Spring Data supports immutable models where objects have no setters:

~~~java
import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record ImmutableOrder(
    @Id ObjectId id,
    String orderNumber,
    Instant createdAt
) {}
~~~

Usage:

~~~java
ImmutableOrder input = new ImmutableOrder(
    null,
    "ORD-1005",
    Instant.now()
);

ImmutableOrder persisted = mongoTemplate.insert(input);
ObjectId id = persisted.id();

// Read ID from persisted; input is an immutable record.
~~~

With immutable entities, Spring Data can construct **a new instance** reflecting the ID after writing. Never inspect **input.id()** to confirm the persisted ID. When migrating code from mutable classes to records, relying on the return value avoids subtle bugs.

### 8.3. Entity State Includes More Than Just ID

If an entity carries properties updated by Spring Data during writes, such as **@Version**, retain the returned instance rather than holding onto the input object:

~~~java
OrderDocument saved = repository.save(order);
// Use saved as the updated state after persistence.
~~~

Never assume the input object, returned object, and database document are always identical at every instant. Callbacks, converters, default values, concurrent writers, and update policies can all affect stored state.

## 9. Auto-Generated IDs vs. Application-Chosen IDs

### 9.1. ObjectId Generated When ID Is Missing

With **@Id ObjectId id** and **id == null**, the MongoDB driver or persistence layer can generate an ObjectId for the new document. An ObjectId can be formatted as a hex string:

~~~java
ObjectId generatedId = repository.insert(order).getId();
String hex = generatedId.toHexString();
~~~

**hex** is convenient for HTTP APIs or logs, yet BSON ObjectId and Java String remain distinct representations. When an API receives hex back, it can parse it:

~~~java
ObjectId parsed = new ObjectId(hex);
~~~

Validate the input format and handle errors cleanly if a client sends malformed strings; avoid leaking unnecessary internal details from parse exceptions.

### 9.2. String-Typed IDs

Spring Data MongoDB supports **@Id String id**, though converting ObjectId-formatted strings into BSON ObjectId can happen under default mapping rules. Therefore, distinguish **the returned Java type** from **the actual stored BSON type**.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public class CustomerWithStringId {
    @Id
    private String id;
    private String name;

    // Constructor, getters, and setters omitted.
}
~~~

With a null String ID, ObjectId generation typically returns the hex string representation to Java after mapping. When a String ID is supplied upfront, whether it is saved as BSON ObjectId or BSON String must be checked against converter rules.

If the goal is **always storing _id as BSON String**, declare the policy explicitly with **@MongoId**:

~~~java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "external_orders")
public class ExternalOrder {
    @MongoId(FieldType.STRING)
    private String id;
    private String externalReference;

    // Constructor, getters, and setters omitted.
}
~~~

For business String IDs, **the application should generate and assign the ID before insert**; do not assume ObjectId generation fits a BSON String policy. `@MongoId` lets you specify the stored `_id` type explicitly and avoid `@Id`'s implicit conversions.

### 9.3. Business IDs Differ From Technical IDs

An order can hold simultaneously:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  orderNumber: "ORD-1001",
  externalReference: "PAY-9988"
}
~~~

Here:

- **_id** is the MongoDB document identifier.
- **orderNumber** is the user-facing order number.
- **externalReference** is a reference code to an external system.

Business fields may require their own unique indexes if uniqueness is required. They do not become `_id` merely because their name resembles an identifier. When designing APIs, decide whether to expose the technical ID, business ID, or both, and document their meaning for clients.

### 9.4. Application-Generated IDs

If a system needs to generate an ID before writing so it can include it in events or link related records, the application can instantiate an **ObjectId**:

~~~java
ObjectId preassignedId = new ObjectId();

OrderDocument order = new OrderDocument(
    "ORD-1006",
    Instant.now()
);
order.setId(preassignedId);

OrderDocument saved = repository.insert(order);
ObjectId returnedId = saved.getId();
~~~

When the write succeeds, **returnedId** matches **preassignedId**. However, **generating an ID does not prove the insert succeeded**: treat the ID as persisted only after the persistence call completes successfully.

For non-ObjectId identifiers such as UUIDs or business string codes, define BSON encoding and ID generation rules in the application layer. Do not expect MongoDB to invent arbitrary custom ID types automatically when null.

## 10. Duplicate Key: What If the ID Already Exists?

MongoDB forbids two documents in the same collection from sharing the same `_id`. Calling **insert** with an existing ID is rejected by the server:

~~~java
ObjectId sameId = new ObjectId();

OrderDocument first = new OrderDocument(
    "ORD-2001", Instant.now()
);
first.setId(sameId);
repository.insert(first); // Succeeds if this _id does not exist yet.

OrderDocument second = new OrderDocument(
    "ORD-2002", Instant.now()
);
second.setId(sameId);
repository.insert(second); // May throw DuplicateKeyException.
~~~

In Spring Data applications, duplicate key errors are typically translated to **DuplicateKeyException** in the Spring DAO exception hierarchy. Handle this at the appropriate layer—for instance, returning a conflict status from the API without reporting a newly created order.

**Never "fix" a duplicate key by mechanically swapping `insert` for `save`.** If `save` turns into a replace/upsert on a colliding ID, existing data can be overwritten. That alters business semantics rather than fixing ID generation.

When an operation fails, the Java object may already carry an application-assigned ID or one populated by an intermediate layer. Having an ID on the object **is not proof of a successful write**. Rely on operation outcomes, exceptions, transactions, and write concern policies.

## 11. ID and Entity State: New, Existing, Version

IDs and persistence state are related but distinct:

| Situation | Java ID | Guaranteed to Exist in DB? | Action to Consider |
| --- | --- | --- | --- |
| New entity not yet persisted | null | No | `insert` or `save` per contract. |
| New entity with application-assigned ID | non-null | No | `insert` to guarantee no overwrite. |
| Entity successfully loaded from database | non-null | Yes at read time | May change before being written back. |
| Entity just successfully inserted | non-null | Yes at write completion | Use returned ID for subsequent steps. |
| Entity just successfully saved | non-null | Yes at write completion | Does not prove the document was newly created. |

### 11.1. `@Version` Is Not `@Id`

Spring Data MongoDB supports optimistic locking via **@Version**:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "carts")
public class CartDocument {
    @Id
    private ObjectId id;

    @Version
    private Long revision;

    private String status;

    // Constructor, getters, and setters omitted.
}
~~~

**id** identifies the document, whereas **revision** detects concurrent updates. When saving an existing document, Spring Data can verify the version value and increment `revision` if the update succeeds. **The ID stays the same.** If the version mismatches because another writer updated first, the operation can throw **OptimisticLockingFailureException** instead of overwriting.

When using optimistic locking, configure an appropriate write concern so operations are acknowledged; write paths bypassing Spring Data's version mechanism must also be designed consistently. Do not assume raw updates increment `@Version` automatically.

### 11.2. `save` Does Not Mean "Update Guaranteed-Existing Document"

If the business requirement is "only update the status of an existing order", instead of relying on `save` with an assigned ID, run a filtered update and inspect the result:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

Query query = Query.query(Criteria.where("_id").is(existingId));
Update update = new Update().set("status", "PAID");

UpdateResult result = mongoTemplate.updateFirst(
    query,
    update,
    "orders"
);

boolean matched = result.getMatchedCount() == 1;
~~~

Here `matchedCount` indicates whether a matching document existed at update time. Such an update operation **does not return an entity with an ID**, as it is a different API from `MongoTemplate.insert`/`save`. If optimistic locking is needed, add a version predicate and an appropriate version increment policy.

## 12. IDs in Reactive Access

With **ReactiveMongoTemplate** or **ReactiveMongoRepository**, write operations return a **Mono<Entity>**. Never read the ID before the write stream completes:

~~~java
import java.time.Instant;
import org.bson.types.ObjectId;
import reactor.core.publisher.Mono;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;

public class ReactiveOrderService {
    private final ReactiveMongoTemplate template;

    public ReactiveOrderService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Mono<ObjectId> create(String orderNumber) {
        OrderDocument draft = new OrderDocument(
            orderNumber,
            Instant.now()
        );

        return template.insert(draft)
            .map(OrderDocument::getId);
    }
}
~~~

The **create** method returns a `Mono` that emits the `ObjectId` **after the insert succeeds**. If a connection error, duplicate key error, or validation failure occurs, the `Mono` emits an error and downstream steps must not assume the ID was persisted.

With a reactive repository:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, ObjectId> {
}

// In service:
Mono<ObjectId> idPublisher =
    reactiveRepository.save(order).map(OrderDocument::getId);
~~~

**Never call `block()` inside a WebFlux/reactive pipeline** to read an ID synchronously; instead, compose downstream steps using `map`, `flatMap`, or appropriate reactive operators. When combining `insert` with further actions, design error handling, retries, and idempotency. Re-subscribing to a write publisher can re-trigger the operation, so never auto-retry `insert` without duplicate-write safeguards.

## 13. Working at the MongoDB Java Driver Layer

`MongoTemplate` allows dropping down to the driver, whose lower-level API signatures differ from Spring Data mapping:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.InsertOneResult;
import org.bson.BsonValue;
import org.bson.Document;

MongoCollection<Document> collection =
    mongoTemplate.getCollection("orders");

Document raw = new Document("orderNumber", "ORD-3001");
InsertOneResult result = collection.insertOne(raw);

BsonValue insertedId = result.getInsertedId();
System.out.println(insertedId);
~~~

**getInsertedId()** here belongs to **InsertOneResult**, not `MongoTemplate.insert`. The driver may generate `_id` on the input `Document` before sending the command. Depending on write concern and driver usage, result APIs can have observability limits that must be verified.

Another example is a lower-level **upsert** returning `UpdateResult`, which can provide **getUpsertedId()** when a new document was inserted by the upsert. That **does not mean** `MongoRepository.save` returns `UpdateResult` or exposes `upsertedId`.

Avoid mixing code that reads IDs from **BsonValue** with code reading IDs from Java entities. When using Spring Data MongoDB at the application layer, prefer the returned entities from template/repository calls to stay consistent with your converters.

## 14. Sending the ID Back Over an HTTP API

An order-creation endpoint typically needs to return the identifier to the client. You can design a DTO containing just the string ID:

~~~java
public record CreateOrderResponse(String id) {}
~~~

Example in a service:

~~~java
public CreateOrderResponse createOrder(String number) {
    OrderDocument draft = new OrderDocument(number, Instant.now());
    OrderDocument inserted = repository.insert(draft);

    return new CreateOrderResponse(
        inserted.getId().toHexString()
    );
}
~~~

Illustrative JSON response:

~~~json
{
  "id": "507f1f77bcf86cd799439011"
}
~~~

This is the ID representation in the API. **Do not force clients to know about Java's `ObjectId` class.** If the technical ID should not be exposed externally, return a separate public code while keeping the mapping between that code and MongoDB `_id` clear.

For resource-creation APIs, returning **201 Created** with a resource URL in **Location** is a common REST convention when appropriate. Building a success response should occur only after the write completes under the system's write concern/transaction requirements.

### 14.1. Inside Transactions

Inside a transaction, `insert`/`save` can return an entity with an ID before **the transaction commits**. If the transaction later rolls back, that ID does not prove the document was durably persisted in the database. Separate **ID has been allocated** from **transaction has committed** before emitting events or returning responses to external systems.

## 15. Testing the ID Lifecycle

Tests should run against a dedicated MongoDB instance, such as Testcontainers or a controlled test deployment. Mocking repositories only verifies method invocations, not real driver ObjectId generation or ID mapping.

Integration test example with Spring Boot / JUnit 5:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.UUID;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class OrderIdIntegrationTest {

    @Autowired
    private OrderRepository repository;

    @Autowired
    private MongoTemplate template;

    @Test
    void insertReturnsEntityWithIdAndCanBeReadById() {
        OrderDocument draft = new OrderDocument(
            "TEST-" + UUID.randomUUID(),
            Instant.now()
        );
        assertThat(draft.getId()).isNull();

        OrderDocument inserted = repository.insert(draft);
        ObjectId id = inserted.getId();

        assertThat(id).isNotNull();
        try {
            OrderDocument found = template.findById(
                id,
                OrderDocument.class
            );
            assertThat(found).isNotNull();
            assertThat(found.getId()).isEqualTo(id);
            assertThat(found.getOrderNumber())
                .isEqualTo(inserted.getOrderNumber());
        } finally {
            repository.deleteById(id);
        }
    }
}
~~~

This test verifies three key behaviors: **ID starts null**, **returned ID after insert is non-null**, and **the document can be read back with that ID**. Use an isolated test connection configuration and ensure test data never affects production.

Additional test cases:

| Scenario | Expectation |
| --- | --- |
| Insert entity without ID | Returned entity has a valid ID and can be queried by ID. |
| Insert entity with assigned ID | Returned entity retains the assigned ID when write succeeds. |
| Insert duplicate ID | Duplicate key error; previous document remains intact. |
| Save existing entity | ID remains unchanged; data updates per contract. |
| Save entity with assigned ID that does not exist | Actual behavior matches template/repository and new/existing detection policy. |
| Insert immutable entity | Retrieve ID from returned object without relying on input mutation. |
| Entity with `@Version` | Verify ID remains stable, version changes, and conflicts are detected. |
| String ID / BSON ObjectId | Verify actual stored BSON type and query behavior after parsing ID. |
| Reactive insert failure | Publisher emits error rather than emitting an ID as if persisted. |
| Transaction rollback | ID was generated, yet document is absent after rollback succeeds. |

## 16. Common Errors When Retrieving IDs

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `getId()` returns null before insert | New object has not been assigned an ID yet | Call `insert`/`save` and read from the returned entity after success. |
| Reading ID from input object is inaccurate | Immutable entity or mapping returns a new instance | Use the return value of repository/template. |
| Calling `insert` with an existing ID fails | Hits `_id` unique index | Verify business logic and ID; do not switch to `save` just to hide the error. |
| `save` returns the same ID even though data changed | ID is document identity, not an update counter | Use `@Version` if write conflict tracking is needed. |
| API receives String ID but query finds nothing | BSON type of `_id` mismatches filter | Inspect `@Id`/`@MongoId` and convert String/ObjectId properly. |
| Has ID yet lookup returns nothing | Wrong database/collection, transaction rolled back, or document deleted | Check connection, collection, transaction outcome, and write results. |
| `save` creates unexpected documents | ID assigned with no existing doc, causing upsert | Use conditional updates when editing only existing records. |
| Reactive code observes null ID | Read before publisher completes or improper subscription | Read ID inside `map`/`flatMap` of the resulting `Mono`. |
| Unit test assumes a fixed ID | ObjectId is generated per write | Assert ID is non-null, valid format, and verify by reading back. |
| `@Version` field changes after `save` | Version tracks write state, unlike ID | Keep the returned entity to continue with the latest version. |

### 16.1. Inspecting With `mongosh`

Example inspecting the `_id` field in a collection:

~~~javascript
db.orders.find(
  { orderNumber: "ORD-1001" },
  { _id: 1, orderNumber: 1 }
);
~~~

To determine the BSON type of `_id`:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      orderNumber: 1,
      idType: { $type: "$_id" }
    }
  }
]);
~~~

For ObjectId, **idType** is typically **objectId**; for String IDs, the result is **string**. Reading printed strings alone without checking the BSON type is insufficient when diagnosing ID mapping bugs.

## 17. Self-Check Practice

### Exercise 1: Which Entity Carries the Returned ID?

~~~java
OrderDocument draft = new OrderDocument(
    "ORD-4001", Instant.now()
);
OrderDocument saved = repository.insert(draft);
ObjectId id = saved.getId();
~~~

**Question:** Does `insert` return an `ObjectId` directly or an `OrderDocument`? Should you inspect `draft.getId()` to confirm the value?

**Answer:** `repository.insert` returns an **OrderDocument**; call **saved.getId()** to obtain the ID. On mutable entities, `draft` may also receive the ID, but using **saved** is reliable and compatible with immutable entities.

### Exercise 2: Writing Duplicate IDs

Two new entities are assigned the same `ObjectId` and passed to `repository.insert` sequentially. What happens?

**Answer:** The second insert is rejected for duplicate `_id` within the same collection if the first succeeded and remains present. Handle duplicate key errors according to business rules. Switching directly to `save` can overwrite the earlier record and is not a safe default fix.

### Exercise 3: Saving an Existing ID

A document has ID **X** and status PENDING. After updating it to PAID and saving successfully, does the ID become **Y**?

**Answer:** No. The ID remains **X** because it represents document identity. If you need to know how many times a record was updated or detect conflicts, use `@Version` or appropriate metadata.

### Exercise 4: Reactive Insert

Write how to return **Mono<String>** containing the hex ID after inserting `OrderDocument`:

~~~java
Mono<String> idHex =
    reactiveTemplate.insert(order)
        .map(saved -> saved.getId().toHexString());
~~~

**Explanation:** The ID extraction runs **after the insert** in the reactive pipeline. If insert fails, the pipeline does not emit a successful ID.

### Exercise 5: String ID vs. BSON ObjectId

An application uses `@Id String id`, a client sends a 24-character hex string, yet a raw driver query finds no document. What should you inspect?

**Hint:** Verify whether `_id` is stored as BSON **objectId** or **string**, check `@Id`/`@MongoId` mapping, and examine how the driver builds its filter. An ObjectId hex string does not automatically become a BSON ObjectId in the raw driver.

### Exercise 6: Rolled-Back Transaction

An insert inside a transaction returns an entity with an ID, but the transaction rolls back because a later step fails. May the API return success with that ID?

**Answer:** No. An allocated ID does not mean the transaction committed. Announce resource creation only after the transaction and required write conditions have completed.

## 18. Principles to Remember

1. **`_id` is the document identifier key** in MongoDB; the Java property annotated with `@Id` typically maps to `_id`.
2. **`MongoTemplate.insert/save` and `MongoRepository.insert/save` return the entity**, so retrieve the ID from the **returned entity**.
3. **`insert` expresses create-only intent**; `save` carries state-persistence semantics and can touch an existing document with that ID.
4. **Having an ID does not prove the document was written successfully**, especially with application-assigned IDs, exceptions, or rolled-back transactions.
5. **Use `@MongoId` when you need explicit control over the ID's BSON type**, particularly for String IDs.
6. **Retain the returned instance for immutable entities**; for reactive access, read the ID after the `Mono` emits the persisted entity.
7. **ID and `@Version` are two separate concepts**: ID maintains identity, while version supports concurrent update control.
8. **Test with a real MongoDB instance** to verify ID generation, BSON types, read-back paths, and duplicate key handling.

Understanding exactly **what ID values are returned after `insert` or `save`** helps **SPRING_DATA_MONGODB** applications build safe creation flows, return accurate identifiers from APIs, and keep state consistent across `MongoTemplate`, repositories, and reactive access.
