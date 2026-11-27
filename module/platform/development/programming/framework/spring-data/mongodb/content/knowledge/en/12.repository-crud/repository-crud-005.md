# existsById, count, and Checking Before Writing

## 1. Scenario: checking first before creating a record

In the **Repository CRUD** chapter of **Spring Data MongoDB**, two operations frequently appear before a write command: `existsById(...)` and `count()`. For example, a membership registration service might need to answer:

- Does registration code `reg-101` already exist in MongoDB?
- How many registrations are currently in `ACTIVE` status?
- If the code does not exist yet, can we call `save(...)` to guarantee creating a new record?
- If the current count is below the quota limit, can we safely add another registration?

The first two questions can be answered with repository methods; the last two concern **correctness when multiple requests run concurrently**. A read result reflects data at the moment the query executes, yet **it does not lock data for a subsequent write**.

Lesson objectives:

1. Understand `existsById`, `count`, conditional count methods, and query costs.
2. Know when pre-write checks are useful and when they create a false sense of safety.
3. Distinguish `save`, `insert`, unique indexes, and conditional updates.
4. Apply optimistic locking, compare-and-set, and reservations to protect business invariants.
5. Test duplicate keys, concurrent writes, and inaccurate counts under parallel execution.

Examples use Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x, MongoDB Java Sync Driver, and a real MongoDB database. Exact ID mapping, version handling, and driver commands should be verified against your project's versions.

## 2. Which checks does a repository provide?

`MongoRepository<T, ID>` inherits basic CRUD operations from the Spring Data repository infrastructure. With a repository managing the `Registration` entity, we can use:

| Method | Question answered | Return type | Semantic limitation |
|---|---|---|---|
| `existsById(id)` | Does a document with this ID exist at query time? | `boolean` | Does not guarantee the ID will stay present or available on the next write |
| `count()` | How many documents are in the repository scope? | `long` | Not a reservation or quota lock |
| `countByStatus(status)` | How many documents satisfy the condition? | `long` | Count can change immediately after reading |
| `existsByEmailKey(emailKey)` | Does a document satisfy this business key? | `boolean` | Does not replace a unique index |
| `findById(id)` | Retrieve one document by ID | `Optional<T>` | Reads more data than needed when only existence matters |
| `findAllById(ids)` | Load multiple documents by a set of IDs | `Iterable<T>` | Do not use instead of count/existence when document payloads are unnecessary |

In a typical application, `existsById` may execute as an existence query in MongoDB; `count` may execute using the document-counting mechanism appropriate for the Spring Data/driver version. Do not rely on a fixed assumption that every version emits one exact BSON command; use MongoDB command monitoring, the profiler, or real query tests when optimizing.

Because `_id` has a default unique index, existence checks **by ID** usually have an efficient access path. For `countByStatus` or `existsByEmailKey`, performance depends on indexes and the number of matching documents.

## 3. Example Java model and repository

Suppose each registration has an application-assigned ID, a normalized email, and a registration status. Choose `@MongoId(FieldType.STRING)` to guarantee string Java IDs are persisted as **BSON String**, even when their content resembles an ObjectId string.

**Registration.java**

~~~java
package com.example.registration;

import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "registrations")
public class Registration {
    @MongoId(FieldType.STRING)
    private String id;

    @Version
    private Long version;

    private String emailKey;
    private String status;

    protected Registration() {
        // For materialization via Spring Data.
    }

    public Registration(String id, String emailKey, String status) {
        this.id = id;
        this.emailKey = emailKey;
        this.status = status;
    }

    public String getId() { return id; }
    public Long getVersion() { return version; }
    public String getEmailKey() { return emailKey; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
}
~~~

**RegistrationRepository.java**

~~~java
package com.example.registration;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface RegistrationRepository
        extends MongoRepository<Registration, String> {

    long countByStatus(String status);

    boolean existsByEmailKey(String emailKey);
}
~~~

With `spring-boot-starter-data-mongodb`, a configured URI, and proper package scanning, Spring Data creates the repository implementation at runtime. The business layer can inject the interface without writing a CRUD implementation class.

An illustrative stored document:

~~~json
{
  "_id": "reg-101",
  "version": 0,
  "emailKey": "lan@example.test",
  "status": "ACTIVE"
}
~~~

The initial version value and other metadata may depend on the write path and Spring Data mapping; the shape above is illustrative only. `@Version` is used for concurrent update handling, not as a replacement for an identifier.

### 3.1. Querying counts and existence

~~~java
package com.example.registration;

import org.springframework.stereotype.Service;

@Service
public class RegistrationReadService {
    private final RegistrationRepository registrations;

    public RegistrationReadService(RegistrationRepository registrations) {
        this.registrations = registrations;
    }

    public boolean hasRegistration(String id) {
        return registrations.existsById(id);
    }

    public long totalRegistrations() {
        return registrations.count();
    }

    public long activeRegistrations() {
        return registrations.countByStatus("ACTIVE");
    }
}
~~~

`existsById("reg-101")` returns `true` if the query finds the matching document, `false` otherwise. `count()` counts documents in the associated collection—**not** the number of array elements inside each document. `countByStatus("ACTIVE")` filters by the `status` field. If some registrations have `DELETED` or `INACTIVE` status, they are still included in `count()` unless physically deleted; this directly impacts how statistics are named and defined.

## 4. Checking before writing: the TOCTOU problem

The following code often looks reasonable:

~~~java
public Registration createIfAbsent(Registration input) {
    if (registrationRepository.existsById(input.getId())) {
        throw new IllegalStateException("ID is already in use");
    }
    return registrationRepository.save(input);
}
~~~

However, **you should not use this pattern to guarantee uniqueness**. It has two flaws:

1. `existsById` and `save` are two separate operations. Another request can write the document after your check and before your save.
2. `save` means **persist entity state**, and can perform an insert or update depending on ID, version metadata, and existence. It is not an API that clearly expresses "create only, reject if key already exists".

Suppose two requests A and B both try to create `reg-101`:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant DB as MongoDB
    participant B as Request B
    A->>DB: existsById("reg-101")
    DB-->>A: false
    B->>DB: existsById("reg-101")
    DB-->>B: false
    A->>DB: Write reg-101
    DB-->>A: success
    B->>DB: Write reg-101
    DB-->>B: duplicate key or update conflict
~~~

The exact ordering and error returned depend on the final write command, schema, and optimistic locking. The invariant issue: **both A and B can observe "does not exist"**. This is a *time-of-check to time-of-use* (**TOCTOU**) bug.

A pre-check does not automatically create a transaction or lock, even when the Java code looks sequential inside a single request. In multi-instance deployments, putting `synchronized` on a Java object does not resolve contention across processes either.

### When pre-checks are still valuable

- **User experience:** warn early that a code or email appears taken before form submission; the result is advisory only.
- **Skipping expensive work:** check beforehand to reduce unnecessary processing steps, as long as write-time protection remains in place.
- **Observability and branching:** count current records to render a dashboard or decide presentation logic.
- **Read-only endpoints:** endpoints checking existence or returning totals when strict real-time freshness is not required.

Whenever a condition **must never be violated** (unique keys, registration quotas, stock deductions, once-only state transitions), move the check into a **database-enforced invariant** or a suitable transactional/synchronization workflow.

## 5. Safe creation: insert and unique indexes

When the goal is "create a new document, fail if the ID already exists", `MongoTemplate.insert(...)` expresses intent far more clearly than `save(...)`:

~~~java
package com.example.registration;

import java.util.Locale;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class RegistrationCreateService {
    private final MongoTemplate mongo;

    public RegistrationCreateService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public Registration create(
            String id, String email, String initialStatus) {
        String emailKey = canonicalEmail(email);
        Registration registration =
                new Registration(id, emailKey, initialStatus);

        // MongoDB rejects insert if _id already exists.
        return mongo.insert(registration);
    }

    private static String canonicalEmail(String email) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email must not be blank");
        }
        return email.trim().toLowerCase(Locale.ROOT);
    }
}
~~~

This canonicalization function is only an **example convention**, not a universal email normalization standard. Real applications must define exact rules for Unicode, case sensitivity, format limits, and whether two addresses truly share the same identity.

MongoDB maintains a unique index on `_id` by default, so two concurrent `insert` commands with the same ID cannot both succeed in the same collection. Spring Data generally translates duplicate key errors into `DuplicateKeyException`. The HTTP layer can map this to **409 Conflict**, while distinguishing conflict types in business terms rather than exposing raw database errors to clients.

### 5.1. Business keys need their own unique indexes

Different IDs can still carry the same email:

~~~json
{ "_id": "reg-101", "emailKey": "lan@example.test", "status": "ACTIVE" }
{ "_id": "reg-102", "emailKey": "lan@example.test", "status": "ACTIVE" }
~~~

If business rules require **at most one registration per emailKey**, create a unique index on that field:

~~~javascript
db.registrations.createIndex(
  { emailKey: 1 },
  { unique: true, name: "uq_registrations_email_key" }
);
~~~

`existsByEmailKey(emailKey)` only checks, whereas a **unique index** is a constraint enforced by MongoDB on write. If duplicate data already exists, clean it up before creating the index. In multi-tenant setups, a compound unique index (`tenantId`, `emailKey`) may be required; define uniqueness scope clearly per business requirements.

For optional fields or fields with `null`/missing values, design unique indexes carefully, potentially using a **partial index** if uniqueness only applies to documents meeting a condition. Avoid creating unique indexes just to "be safer" without defining missing-data semantics.

### 5.2. Is existsById needed before insert?

It is not required to guarantee ID uniqueness. You may check proactively to fail fast, yet **insert/unique indexes remain the final line of defense**:

~~~java
// Optional UX check; can be omitted.
if (repository.existsById(id)) {
    return "Code appears to be already in use";
}

// State may have already changed: must still handle DuplicateKeyException.
mongo.insert(new Registration(id, emailKey, "ACTIVE"));
~~~

If a request is retried after a client timeout, receiving a duplicate error alone is not enough to know whether **the earlier request succeeded or collided with someone else**. When idempotent creation is required, define an idempotency key, canonical request payload, response replay policy, and key retention duration.

## 6. save, insert, and updates by ID

| Method | Business intent to attach | When to be cautious |
|---|---|---|
| `MongoTemplate.insert(entity)` | Create a new document | Duplicate ID or unique business key will be rejected |
| `MongoRepository.save(entity)` | Persist a new or existing entity | Do not use as create-only; pay attention to `@Version` |
| `MongoTemplate.updateFirst(query, update, Type.class)` | Update a document when criteria match | Check `matchedCount`, state conditions, and version |
| `MongoTemplate.findAndModify(...)` | Read and update one document atomically | Needs exact criteria and reading return value per desired semantics |
| `MongoTemplate.remove(query, Type.class)` | Delete documents matching criteria | `deletedCount` reports how many documents were deleted at execution time |

In the `Registration` example with `@Version`, calling `save` on a loaded entity can leverage optimistic locking, detecting version changes and throwing `OptimisticLockingFailureException`. This helps keep entity updates safe, but works reliably only when **every relevant write path respects the version**.

Example:

~~~java
package com.example.registration;

import org.springframework.stereotype.Service;

@Service
public class RegistrationStatusService {
    private final RegistrationRepository registrations;

    public RegistrationStatusService(RegistrationRepository registrations) {
        this.registrations = registrations;
    }

    public Registration activate(String id) {
        Registration current = registrations.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Registration not found"));

        current.setStatus("ACTIVE");
        return registrations.save(current);
    }
}
~~~

Under contention, two requests can both read version `3`, yet only one save based on that version succeeds; the other request must handle the optimistic locking failure and decide whether to retry or report a conflict. Retrying **does not** mean blind overwriting: reload the entity and re-evaluate business rules against the fresh state.

## 7. Checking and writing in the same command: compare-and-set

If the goal is "transition `PENDING` to `CONFIRMED` only once", place the condition **directly inside the update command** instead of calling `existsById` then `save`:

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public boolean confirmIfPending(
        MongoTemplate mongo, String id, long expectedVersion) {
    Query query = Query.query(
            Criteria.where("id").is(id)
                    .and("status").is("PENDING")
                    .and("version").is(expectedVersion));

    Update update = new Update()
            .set("status", "CONFIRMED")
            .inc("version", 1);

    UpdateResult result = mongo.updateFirst(
            query, update, Registration.class);
    return result.getMatchedCount() == 1;
}
~~~

This snippet illustrates a method in an application class taking `MongoTemplate` for easy testing. Because the query executes with `Registration.class`, Spring Data maps the `id` property to BSON `_id` and applies relevant mapping metadata.

**Why is this safer?** Comparing ID, status, version, and applying the change on **one document** is executed by MongoDB as a single atomic operation. If A transitions to `CONFIRMED` first, B will no longer find a document matching `status = PENDING` and the old version.

Interpreting the result:

- `matchedCount == 1`: one document satisfied the criteria when MongoDB executed the update.
- `matchedCount == 0`: the ID might not exist, the status already changed, or the version no longer matches. If the API needs to distinguish causes, run a follow-up read **to explain the outcome**, not to guard the past write.
- `modifiedCount` can be checked when you need to know how many documents actually changed values. Never assume `modifiedCount = 0` always means the ID does not exist.

Because the example uses `@Version`, the update explicitly increments `version` so subsequent `save` calls detect the change. When writing custom conditional updates, keep versioning consistent across all write paths; if a write skips incrementing version or edits BSON directly, repository optimistic locking cannot protect fully.

### 7.1. Conditional delete instead of check-then-delete

If deletion is allowed **only while PENDING**, use:

~~~java
import com.mongodb.client.result.DeleteResult;

public boolean deleteIfPending(MongoTemplate mongo, String id) {
    Query query = Query.query(
            Criteria.where("id").is(id)
                    .and("status").is("PENDING"));
    DeleteResult deleted = mongo.remove(query, Registration.class);
    return deleted.getDeletedCount() == 1;
}
~~~

Placing the condition inside `remove` avoids the race gap between `existsById` and `deleteById`. If deletion also depends on version, add the expected version condition. For audit/history requirements, consider soft-delete via a conditional status update instead of physical removal.

## 8. Why count cannot protect a quota limit

Suppose the system allows at most **100 ACTIVE registrations**. The code below is unsafe under concurrency:

~~~java
if (registrations.countByStatus("ACTIVE") < 100) {
    registrations.save(
            new Registration(newId, emailKey, "ACTIVE"));
}
~~~

When 99 registrations exist, two requests both count `99`, and both insert a new one. The final count can reach `101`. Reading a count and inserting a document are two separate operations, and a unique `_id` does not stop exceeding a **collection-wide** quota.

Even with a stronger read concern, a standalone `count → insert` sequence does not become an atomic **check-and-reserve** operation. Multi-document transactions also require analyzing actual write conflicts; reading the same set of documents and writing **two distinct documents** does not automatically eliminate every race condition.

### 8.1. Using a quota document as a synchronization point

One design stores **remaining slots** in a quota document and decrements **conditionally** on that exact document:

~~~json
{
  "_id": "registration-limit",
  "remaining": 1
}
~~~

**RegistrationQuota.java**

~~~java
package com.example.registration;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "registration_quotas")
public class RegistrationQuota {
    @MongoId(FieldType.STRING)
    private String id;
    private long remaining;

    protected RegistrationQuota() {}

    public String getId() { return id; }
    public long getRemaining() { return remaining; }
}
~~~

**Function to reserve one slot:**

~~~java
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public boolean reserveOne(MongoTemplate mongo, String quotaId) {
    Query query = Query.query(
            Criteria.where("id").is(quotaId)
                    .and("remaining").gt(0));
    Update decrement = new Update().inc("remaining", -1);

    RegistrationQuota result = mongo.findAndModify(
            query,
            decrement,
            FindAndModifyOptions.options().returnNew(true),
            RegistrationQuota.class);
    return result != null;
}
~~~

Two requests both seeing 1 remaining slot cannot **both** decrement from 1 to 0 with the `remaining > 0` filter on the same document: one succeeds and the other matches nothing. This enforces the **invariant on the quota document**.

However, **reserving a slot and creating a registration touch two separate documents**. If reservation succeeds but inserting the registration fails, the slot can leak. When business logic demands consistency between quota and registration, design the workflow accordingly:

- Multi-document MongoDB transactions on a supported topology, with `MongoTransactionManager` or matching session and proper retry handling; **or**
- Reservations with explicit IDs, states, expiration times, compensation/reconciliation, and clearly defined idempotency.

Do not treat the standalone `reserveOne` snippet as a complete registration workflow. A shared quota document can also become a contention hotspot under high load; measure throughput and consider sharding/partitioning quotas by business scope.

### 8.2. When is count appropriate for quotas?

`countByStatus` fits **displaying utilization, forecasting, and near-limit warnings**. It can also act as an early fast-fail filter if occasional over-checking is acceptable. Whenever 100 is a **hard invariant**, enforcement must rely on a conditional write or contention-safe resource allocation mechanism.

## 9. Performance of existsById and count

### 9.1. Checking by _id

`existsById` is usually concise and efficient when you only need to know whether a document exists. With `_id` indexed, the query avoids loading a large object solely to check presence. Still, there is connection, round-trip, and server read cost; calling it thousands of times inside a loop adds up quickly.

To check existence for many IDs, batch IDs and query `_id: { $in: [...] }` with bounded batch sizes. When you only need to count matching IDs, run a targeted query over the ID set; never pull the entire collection into memory.

### 9.2. Full collection count and conditional count

`count()` returns a `long` count, not a zero-cost estimate. Exact counting can be resource-intensive depending on collection size, criteria, indexes, MongoDB version, and topology. With a filter on `status`, consider an index:

~~~javascript
db.registrations.createIndex({ status: 1 });
~~~

Then inspect using:

~~~javascript
db.registrations.find({ status: "ACTIVE" })
  .explain("executionStats");
~~~

`explain` on the find query shows index/keys/docs examined; for count operations, verify the corresponding count execution plan in your real environment. When filtering on multiple fields and sorting, pick indexes based on actual workload rather than indexing every property blindly.

### 9.3. Estimated counts when only a dashboard needs them

When an approximate **whole-collection** figure suffices, the MongoDB Java Driver offers `estimatedDocumentCount()`, which uses metadata instead of scanning or counting exact documents:

~~~java
long estimate = mongoTemplate
        .getCollection("registrations")
        .estimatedDocumentCount();
~~~

`estimatedDocumentCount()` **does not accept a `status` filter**, and estimates can drift from exact counts, especially around active writes/deletes or specific metadata/topology states. Never use estimated counts for quotas, billing decisions, exact conditional statistics, or uniqueness enforcement.

### 9.4. Read configuration and distributed instances

Results of `existsById`/`count` also depend on read path, read preference, read concern, and replication lag. Reading from secondaries can observe stale data relative to the primary depending on configuration. Fast `_id` lookups do not mean "guaranteed latest truth" in every topology.

Consequently, pre-checks guarding a write are even less reliable when reads and writes may observe different data versions. Embed invariants inside write commands and configure appropriate consistency instead of relying on separate read-then-write pairs.

## 10. Do reactive repositories differ in guarantees?

When using `ReactiveMongoRepository` and `ReactiveMongoTemplate`, return types become publishers:

~~~java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

public interface ReactiveRegistrationRepository
        extends ReactiveMongoRepository<Registration, String> {
}
~~~

~~~java
Mono<Boolean> existing = reactiveRegistrations.existsById("reg-101");
Mono<Long> total = reactiveRegistrations.count();
~~~

In the second snippet, `reactiveRegistrations` is an injected field of type `ReactiveRegistrationRepository`, and `reactor.core.publisher.Mono` must be imported. Publishers execute only when subscribed to in an appropriate reactive context.

**Non-blocking execution does not make an `existsById → save` sequence atomic.** Race conditions still occur when multiple subscribers or requests run concurrently. For consistency-critical flows, use conditional update APIs / reactive transactions properly and avoid blocking the event loop with synchronous driver calls.

## 11. Testing against a real MongoDB

A unit test mocking `existsById` and checking whether `save` was called will not catch **TOCTOU bugs** or unique index behavior. You need integration tests with a real MongoDB, such as via Testcontainers. In Spring Boot 3.x, `@DataMongoTest` sets up MongoDB mapping/repository test slices, yet **does not automatically launch a MongoDB server**.

### 11.1. Testing existence, counts, and duplicate keys

~~~java
package com.example.registration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;

@DataMongoTest
class RegistrationRepositoryTest {
    @Autowired
    RegistrationRepository registrations;

    @Autowired
    MongoTemplate mongo;

    @BeforeEach
    void prepare() {
        registrations.deleteAll();
        mongo.indexOps(Registration.class).ensureIndex(
                new Index()
                        .on("emailKey", Sort.Direction.ASC)
                        .unique());
    }

    @Test
    void existenceAndCountsReflectSavedDocuments() {
        assertThat(registrations.existsById("reg-101")).isFalse();

        mongo.insert(new Registration(
                "reg-101", "lan@example.test", "ACTIVE"));
        mongo.insert(new Registration(
                "reg-102", "minh@example.test", "PENDING"));

        assertThat(registrations.existsById("reg-101")).isTrue();
        assertThat(registrations.count()).isEqualTo(2);
        assertThat(registrations.countByStatus("ACTIVE")).isEqualTo(1);
    }

    @Test
    void insertRejectsDuplicateBusinessKey() {
        mongo.insert(new Registration(
                "reg-101", "lan@example.test", "ACTIVE"));

        assertThatThrownBy(() -> mongo.insert(
                new Registration(
                        "reg-102", "lan@example.test", "ACTIVE")))
                .isInstanceOf(DuplicateKeyException.class);
    }
}
~~~

The index is created **explicitly in the test** because mapping annotations or Boot defaults do not guarantee automatic index creation in every environment. When running tests in parallel, use isolated collections/databases so `deleteAll()` does not affect other tests. Never run this test setup against live production data.

### 11.2. Concurrency test cases to include

| Scenario | Outcome to prove |
|---|---|
| Two threads concurrently insert `_id = reg-101` | At most one new document; duplicate ID error handled intentionally |
| Two threads insert distinct IDs with identical `emailKey` | Unique index blocks duplicate business key |
| Two requests both observe `existsById = false` then insert | Only the decisive write enforces uniqueness; pre-check does not protect |
| Two requests both read `version = 3` then `save` | One update succeeds; stale update is caught when all writes honor version |
| Two concurrent `confirmIfPending` requests with same version | At most one conditional state transition succeeds |
| Two threads concurrently reserve the last quota slot (`remaining = 1`) | At most one thread decrements successfully |
| Slot reserved then insert fails | Transaction/compensation/idempotency prevents leaking the slot |
| Counting `ACTIVE` during concurrent writes/deletes | Clear timing and consistency bounds defined for statistics |
| Replaying the same request after a timeout | No duplicate record created and prior outcome can be determined |

When writing concurrency integration tests, use synchronization primitives so both threads start at the check/write barrier simultaneously and assert final state **after both finish**. Sequential tests cannot prove race condition protection.

### 11.3. Performance diagnostics

To understand cost, observe:

- Number of MongoDB commands and round trips for `existsById → insert` versus direct `insert`.
- Duration of `count()`/`countByStatus(...)` relative to collection size and indexes.
- Frequency of `DuplicateKeyException`, `OptimisticLockingFailureException`, and retries at peak traffic.
- `matchedCount`, `modifiedCount`, and `deletedCount` from conditional write commands.
- p95/p99 latency, connection pool utilization, replication lag, and query plans under high load.

Do not optimize by switching APIs before examining queries, indexes, data, and real read paths.

## 12. Common pitfalls

| Mistake | Consequence | Solution |
|---|---|---|
| Calling `existsById` then `save` to ensure unused ID | Race condition; may overwrite or conflict | Use `insert` and unique `_id` for creation |
| Calling `existsByEmailKey` without a unique index | Two requests still create the same business key | Add a unique index with proper namespace/scope |
| Treating `save` as "create-only" | Fails to clearly reject existing documents | Choose `insert` for create-only operations |
| Counting before inserting to enforce a hard limit | Two requests both proceed when 1 slot remains | Conditional quota update, transaction, or reservation |
| Assuming `count()` is always cheap | Expensive query on large collections | Inspect indexes, plans, and statistical requirements |
| Using `estimatedDocumentCount` for quota enforcement | Approximate count can be inaccurate | Use slot reservation / write-time invariants |
| Assuming a check stays valid for the next request | TOCTOU, eventual consistency, or replication lag | Embed conditions into the write command |
| Reading, modifying, and `save` without managing version | Lost updates from other requests | `@Version`/compare-and-set with controlled retries |
| Interpreting `modifiedCount = 0` as "ID does not exist" | Misclassified error handling | Check `matchedCount` and business criteria |
| Automatically retrying all duplicate key errors | Can loop or return wrong responses | Separate transient/retryable errors from business conflicts |
| Treating repository mocks as proof of concurrency safety | Misses race conditions and unique constraints | Test against a real MongoDB with multiple threads |

## 13. Practical exercises

**Exercise 1 — Reading exact metrics.** Create a repository for `Registration` with `existsById`, `count`, and `countByStatus`. Save 2 `ACTIVE` and 1 `PENDING` registration. Explain why `count() == 3` while `countByStatus("ACTIVE") == 2`, and why `count()` is not a reservation.

**Exercise 2 — Catching a race condition.** Write two requests that both check `existsById("reg-101")` before inserting. Use a barrier/latch in an integration test so both observe `false` before writing. Add `DuplicateKeyException` handling and verify the collection holds only one `_id`.

**Exercise 3 — Business key.** Require that an email has at most one registration per tenant. Design the normalized key, compound unique index (`tenantId`, `emailKey`), missing-field handling, and error policy when two concurrent requests register the same email.

**Exercise 4 — Comparing insert/save.** Use `MongoTemplate.insert` to create a document, then try inserting the same ID again. Use repository `save` to update a loaded versioned document, then simulate two requests saving the same stale version.

**Exercise 5 — 100-slot quota.** Create a quota document with `remaining = 1`; issue two concurrent requests. Use `findAndModify` with `remaining > 0` to prevent going negative. Propose a workflow to restore the slot if creating the registration fails.

**Exercise 6 — Performance.** With 100,000 registrations, measure `existsById`, `count()`, `countByStatus("ACTIVE")`, and `estimatedDocumentCount()`. Inspect indexes, p95 latency, and accuracy while writes are occurring. Propose where each operation fits for dashboards versus business rules.

## 14. Key takeaways

In **Spring Data MongoDB**, `existsById` answers **whether an ID exists at read time**, while `count` and `countBy...` methods answer **how many documents match a condition**. They are very useful for validation, displaying metrics, and optimizing read paths, yet **they do not make subsequent writes atomic**.

To **create only**, use `insert` and unique indexes. To **update only if status/version still matches**, use `@Version` or a conditional MongoDB update. To **enforce a hard quota**, protect the invariant at write time—such as a quota document with `findAndModify`, paired with transactions or reliable reservations across multiple documents.

When deciding between pre-checking and writing directly, prioritize **business semantics, concurrency conditions, idempotency, metric accuracy requirements, and measured performance**. Only real tests against MongoDB with representative data and contention demonstrate whether your flow preserves invariants under concurrent requests.
