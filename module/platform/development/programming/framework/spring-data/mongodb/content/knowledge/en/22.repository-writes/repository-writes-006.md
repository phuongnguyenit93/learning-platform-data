# Derived Delete Methods and Return Types

## 1. Problem: Conditional deletion differs from deletion by ID

In a Spring Data MongoDB application, deleting a single document by ID is straightforward: call **deleteById(id)** on the repository. However, business requirements frequently call for conditional deletion, such as:

- Deleting support tickets with **status = EXPIRED** for a given tenant.
- Deleting draft records created before a cutoff timestamp.
- Deleting test data under a controlled classification tag.
- Deleting a group of documents and needing to know **how many were deleted**, or retaining a **list of the deleted items** for business recording.

Spring Data MongoDB supports **derived delete queries**: declare a repository method prefixed with **delete...By** or **remove...By**; the framework infers the filter from the method name. Notably, the **return type** can change how the operation executes: returning the count of deleted documents, or retrieving and returning the entities selected for deletion.

The lesson **Derived Delete Methods and Return Types** belongs to the **Repository Writes** chapter of the **SPRING_DATA_MONGODB** module. The module uses Spring Data MongoDB to connect, map documents, and operate on MongoDB via `MongoTemplate` or repositories; this knowledge supports query design, indexing, transactions, reactive access, testing, and data performance diagnostics.

After this lesson, you will be able to:

1. Read and write **deleteBy...**, **removeBy...**, and **deleteAllBy...** method names.
2. Distinguish **long/Long** and **List<Entity>** return types for derived deletes.
3. Compare derived deletes with **deleteById**, **delete(entity)**, and **MongoTemplate.remove**.
4. Understand that returning deleted entities may require **reading data prior to deletion**, and does not make the entire operation a transaction.
5. Protect filters by tenant, status, and timestamp conditions.
6. Design bulk deletions, authorization, retries, soft deletes, and optimistic locking appropriately.
7. Test actual deletion results and verify out-of-scope documents remain untouched.

## 2. Sample document: support tickets

Suppose a service has a **support_tickets** collection:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  status: "EXPIRED",
  category: "RETURN",
  subject: "Return request",
  createdAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

Another document belonging to a different tenant:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  tenantId: "shop-b",
  status: "EXPIRED",
  category: "RETURN",
  subject: "Delivery inquiry",
  createdAt: ISODate("2025-06-02T09:00:00Z")
}
~~~

Critical requirement: when deleting expired tickets for **shop-a**, tickets belonging to **shop-b** must never be deleted, even though they share the same status.

Java entity:

~~~java
package com.example.support;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "support_tickets")
public record TicketDocument(
    @Id ObjectId id,
    String tenantId,
    String status,
    String category,
    String subject,
    Instant createdAt
) {}
~~~

The **@Document** annotation identifies the collection; **@Id** maps Java property **id** to BSON **_id**. Other properties in the example use BSON names matching the Java names. Timestamps use `Instant`/BSON Date to avoid confusion with plain date strings.

## 3. Minimal repository and derived delete methods

~~~java
package com.example.support;

import java.time.Instant;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface TicketRepository
        extends MongoRepository<TicketDocument, ObjectId> {

    long deleteByTenantIdAndStatus(
        String tenantId,
        String status
    );

    List<TicketDocument> removeByTenantIdAndCategory(
        String tenantId,
        String category
    );

    long deleteByTenantIdAndStatusAndCreatedAtBefore(
        String tenantId,
        String status,
        Instant cutoff
    );

    List<TicketDocument> findByTenantId(String tenantId);
}
~~~

**You do not write implementation classes manually** for the three derived delete methods above in a valid MongoDB repository configuration. Spring Data parses the method names and constructs the corresponding operations through repository infrastructure.

Method names describe:

- **deleteByTenantIdAndStatus**: deletes tickets matching `tenantId` and `status`.
- **removeByTenantIdAndCategory**: deletes tickets matching `tenantId` and `category`, while returning the entities selected for deletion.
- **deleteByTenantIdAndStatusAndCreatedAtBefore**: deletes tickets belonging to a tenant, with a given status and `createdAt` before `cutoff`.
- **findByTenantId**: read method used for verification or testing; deletes nothing.

**Most examples use signatures returning long or List<TicketDocument>**, as those are the two primary result patterns to understand clearly. Other return types must be evaluated against the repository contract, Spring Data version, and how the app intends to consume the result.

## 4. Method naming language: deleteBy and removeBy

Spring Data recognizes delete/remove prefixes in derived methods. For example:

~~~java
long deleteByTenantIdAndStatus(
    String tenantId, String status
);

long removeByTenantIdAndStatus(
    String tenantId, String status
);
~~~

With identical predicates and return types, these two signatures express the same filter-based deletion intent. Choosing **delete** vs. **remove** is mainly an API naming convention; never assign meanings like "delete means hard delete, remove means soft delete".

### 4.1. All does not mean deleting the entire collection when a filter exists

~~~java
long deleteAllByTenantIdAndStatus(
    String tenantId, String status
);
~~~

In derived methods, **All** can serve as descriptive phrasing in the subject portion. The query still includes the predicates after **By**. It does not equate to an unconditional **repository.deleteAll()**.

Comparison:

| Method | Scope |
| --- | --- |
| deleteByTenantIdAndStatus("shop-a", "EXPIRED") | Documents matching tenant and status |
| deleteAllByTenantIdAndStatus("shop-a", "EXPIRED") | Same derived filter style |
| deleteById(id) | Document by ID |
| deleteAll() | All documents managed by the repository, with no business filter |

**Never create an unfiltered delete method just to save a few characters.** In multi-tenant data, filtering by tenant is an essential safety boundary.

### 4.2. Predicates follow Java properties

Method names are parsed against **Java entity properties**, not arbitrary string concatenation. For example, `createdAt` uses the Java property name, while MongoDB stores a corresponding BSON Date.

~~~java
long deleteByTenantIdAndCreatedAtBefore(
    String tenantId,
    Instant cutoff
);
~~~

The framework expresses a condition similar to:

~~~javascript
db.support_tickets.deleteMany({
  tenantId: "shop-a",
  createdAt: { $lt: ISODate("2025-07-01T00:00:00Z") }
});
~~~

This is a **conceptual visualization of the filter semantics**, not a claim that every derived delete return type executes an identical `deleteMany` command. Execution strategy changes with the return type; the next sections cover that core distinction.

## 5. Long/long: returning the deleted document count

When the caller needs to know **how many documents were deleted**, choose a numeric count return type:

~~~java
long deleteByTenantIdAndStatus(
    String tenantId, String status
);
~~~

In a service:

~~~java
public long purgeExpired(String tenantId) {
    return repository.deleteByTenantIdAndStatus(
        tenantId,
        "EXPIRED"
    );
}
~~~

Suppose before calling there are seven EXPIRED tickets for `shop-a` and three EXPIRED tickets for `shop-b`. Without concurrent writes and assuming all operations succeed, the result can be:

~~~text
purgeExpired("shop-a") -> 7
~~~

Only `shop-a` tickets matching the filter are removed. The value **7** is the **number of documents reported deleted by the operation**, not the number of remaining elements in the collection.

### 5.1. How do long and Long differ in Java?

~~~java
long deleteByTenantIdAndStatus(String tenantId, String status);

Long removeByTenantIdAndStatus(String tenantId, String status);
~~~

**long** is primitive; **Long** is a wrapper. For derived deletes counting deleted documents, both express the same count semantics in common repository contracts.

If the application has no reason to return `null`, **long** is cleaner and simpler. Never use a nullable `Long` to mean "deletion hasn't run yet": a repository operation can legitimately complete with **0** records deleted.

### 5.2. Zero is not necessarily an error

~~~text
deleteByTenantIdAndStatus("shop-a", "EXPIRED") -> 0
~~~

This can mean:

- No tickets match the filter anymore.
- Tickets were already deleted in a previous run.
- Status or tenant did not match.
- Tickets transitioned to another status before deletion.

**0 is a valid database-level result.** The business layer decides whether to return "nothing to delete", HTTP 200 with `deletedCount=0`, or an unsatisfied-precondition error. Do not assume deleting 0 documents indicates a database failure.

### 5.3. Deleted count differs from pre-delete count

Do not write:

~~~java
long totalBefore = repository.countByTenantIdAndStatus(
    tenantId, "EXPIRED"
);
repository.deleteByTenantIdAndStatus(tenantId, "EXPIRED");
return totalBefore;
~~~

If another writer runs between **count** and **delete**, the earlier count may no longer match the actually deleted count. When business logic needs the deletion operation's outcome, **return the derived delete's own value directly**.

## 6. List<Entity>: returning entities selected for deletion

When the caller needs the contents of the deleted tickets, declare:

~~~java
List<TicketDocument> removeByTenantIdAndCategory(
    String tenantId,
    String category
);
~~~

Example:

~~~java
List<TicketDocument> removed =
    repository.removeByTenantIdAndCategory(
        "shop-a",
        "TEST"
    );

for (TicketDocument ticket : removed) {
    auditLogger.recordDeletedTicket(
        ticket.id(),
        ticket.subject()
    );
}
~~~

**auditLogger** is an illustrative application-layer dependency. The **removed** list holds the entities retrieved for the delete operation, letting the application inspect fields such as `id`, `subject`, or `createdAt`.

Unlike the count-returning form, returning **List<TicketDocument>** requires entity payloads to hand back. Because standard MongoDB `deleteOne`/`deleteMany` commands only return counts, Spring Data must use a strategy that **finds matching entities and deletes them** (or an equivalent mechanism in the deployed version).

### 6.1. The returned list reflects pre-deletion content

With three TEST tickets:

~~~text
removeByTenantIdAndCategory("shop-a", "TEST")
    -> [TicketA, TicketB, TicketC]
~~~

Once the operation succeeds, the corresponding documents are no longer in the collection under the delete criteria. The returned `List` represents the **read data of the affected entities**, not entities still residing in MongoDB.

**Do not rely on List ordering if the method defines no sort**, since query result ordering is not an implicit stability contract.

### 6.2. The list is not proof of a transactional snapshot

Suppose Spring Data reads the documents first and then deletes them. Between those two steps, another writer could update or delete a matching document. In that case, the read list and actual deletion state might not reflect the exact same snapshot.

**Do not promise that every element in the List was locked at read time and successfully deleted**, unless your system provides verified guarantees from transactions or the underlying execution mechanism.

If the application strictly requires recording the exact deleted content, use a proper audit/transaction or outbox architecture—do not simply switch the return type to `List` and assume atomicity.

### 6.3. Cost differences from returning a count

| Aspect | long/Long | List<Entity> |
| --- | --- | --- |
| Data returned to Java | A single number | Multiple entities |
| Need to read entities before deleting | Not needed to build return value | May require pre-reading data |
| Caller RAM cost | Minimal | Scales with returned entity count |
| Network and mapping cost | Typically lower | Can be significantly higher |
| Content immediately available for audit? | No | Contains entity data |
| Suitable for very large bulk deletes? | Usually more suitable | Must enforce limits and memory bounds |

If you only need **deletedCount**, choose the numeric return type. If you genuinely need pre-deletion data, choose `List` with bounds, audit workflows, and appropriate consistency guarantees.

## 7. A return type does not replace semantic testing

Identical method names with different return types can cause Spring Data to pick different execution paths:

~~~java
// Method 1: want to know how many documents were deleted.
long deleteByTenantIdAndStatus(String tenantId, String status);

// Method 2: want to receive entities involved in deletion.
List<TicketDocument> removeByTenantIdAndCategory(
    String tenantId, String category
);
~~~

Do not assume that:

- A `List`-returning method is always just **`deleteMany` + driver-generated list**.
- A count-returning method always builds a `List` first and calls **`size()`**.
- Both return types share identical cost, event, and transaction semantics.

Spring Data implementations can vary by store, version, and return type. In production apps, test against your exact **Spring Data MongoDB and MongoDB Server versions**, especially when relying on entity callbacks, auditing, or transactions.

### 7.1. Other return types

Some repository designs may use **void** when the caller does not need the count. Still, for conditional deletion logic, **long/Long and List<Entity>** make the contract clearer: either get the count, or get the entity data.

Avoid arbitrarily declaring **Optional<T>**, **Page<T>**, **Stream<T>**, or custom DTOs on derived deletes without verifying API support. The return type is not a free-form instruction to make the framework perform arbitrary transformations; it must belong to the types accepted by repository query infrastructure.

## 8. Comparing with inherited CRUD methods

`MongoRepository` inherits common deletion operations such as:

~~~java
repository.deleteById(id);

repository.delete(ticket);

repository.deleteAllById(ids);

repository.deleteAll();
~~~

These operations are not derived from business predicates in the method name like **deleteByTenantIdAndStatus**.

| Method | Input | Java result | Notes |
| --- | --- | --- | --- |
| deleteById(ID id) | One ID | void | Deletes by identifier |
| delete(T entity) | One entity | void | May apply `@Version` semantics depending on entity/store |
| deleteAllById(Iterable<ID>) | Set of IDs | void | Deletes specified IDs |
| deleteAll() | No filter | void | Extremely dangerous on production collections |
| deleteByTenantIdAndStatus(...) | Derived predicate | long/Long | Returns deleted document count |
| removeByTenantIdAndCategory(...) | Derived predicate | List<TicketDocument> | Returns entity data for records involved in deletion |

**deleteById(id) is not deleteByIdAndTenantId(id, tenantId).** In multi-tenant applications, merely knowing an `ObjectId` does not prove the caller is authorized to delete that document.

### 8.1. When both ID and tenant must match

You can define:

~~~java
long deleteByIdAndTenantId(
    ObjectId id,
    String tenantId
);
~~~

Here the filter enforces both ID and tenant. The count is typically 0 or 1 when `_id` is unique.

The service must obtain `tenantId` from the **authenticated context**; never treat an arbitrary client-supplied `tenantId` parameter as proof of access rights.

## 9. Derived delete is a filtered deletion, not a soft delete

The method prefix **removeBy...** can be mistaken for soft deletion, yet no rule states `remove` means setting **`deleted=true`**.

~~~java
long removeByTenantIdAndStatus(String tenantId, String status);
~~~

This method expresses **deleting documents** matching the filter. If business logic needs to keep documents for recovery or auditing, implement soft deletion separately.

Example with `MongoTemplate` (assuming the schema has **deleted** and **deletedAt**):

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Query query = Query.query(
    Criteria.where("tenantId").is(tenantId)
        .and("status").is("EXPIRED")
        .and("deleted").is(false)
);

Update update = new Update()
    .set("deleted", true)
    .currentDate("deletedAt");

var result = mongoTemplate.updateMulti(
    query,
    update,
    TicketDocument.class
);
~~~

This is a **soft-delete design pattern**: `TicketDocument` at the start did not declare `deleted`/`deletedAt`, so schema and query policies must be extended when applying it in practice.

With soft deletion, update every read path (repositories, `MongoTemplate`, aggregations), indexes, and retention policies. Never simply rename a method from `deleteBy` to `removeBy` expecting data to be preserved.

## 10. Writing safe derived delete filters

### 10.1. Enforce tenant directly inside the query

~~~java
long deleteByTenantIdAndStatus(
    String tenantId, String status
);
~~~

Compare with:

~~~java
// Dangerous if used in a multi-tenant system.
long deleteByStatus(String status);
~~~

The second method can delete all EXPIRED tickets across multiple tenants if the MongoDB account has write privileges and the service lacks another restriction layer.

**Security must live in the deletion operation design itself**, not merely in a read check beforehand.

### 10.2. Restrict deletable statuses

Business rules might only allow deleting EXPIRED or DRAFT tickets, never OPEN:

~~~java
long deleteByTenantIdAndStatus(
    String tenantId, String status
);
~~~

The service must validate that status belongs to the allowed set:

~~~java
if (!"EXPIRED".equals(status) && !"DRAFT".equals(status)) {
    throw new IllegalArgumentException(
        "This status cannot be deleted"
    );
}
~~~

Never allow clients to pass **arbitrary status values** into a derived delete when policy restricts deletion to specific statuses.

### 10.3. Deleting by data age

~~~java
long deleteByTenantIdAndStatusAndCreatedAtBefore(
    String tenantId,
    String status,
    Instant cutoff
);
~~~

Example:

~~~java
Instant cutoff = Instant.parse("2025-07-01T00:00:00Z");

long deleted = repository
    .deleteByTenantIdAndStatusAndCreatedAtBefore(
        tenantId,
        "EXPIRED",
        cutoff
    );
~~~

**Before** expresses strictly less than `cutoff`. Watch timezones when clients enter dates; `Instant` fixes points in time in UTC rather than relying on implicit local time.

### 10.4. Nulls and legacy data

If `status` is missing, null, or stored with the wrong BSON type, `status = EXPIRED` will not match. Do not loosen deletion filters just because some legacy documents have a different schema.

For migrations, first measure and classify the data; then build a dedicated deletion policy with explicit conditions, backups/audits, and thorough testing.

## 11. Indexes: helping locate the right documents to delete

Derived queries still require MongoDB to locate documents matching the filter. For workload:

~~~java
long deleteByTenantIdAndStatus(
    String tenantId,
    String status
);
~~~

An index to evaluate:

~~~javascript
db.support_tickets.createIndex({
  tenantId: 1,
  status: 1
});
~~~

For cutoff-based deletion:

~~~javascript
db.support_tickets.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: 1
});
~~~

Indexes help select target documents, yet deletion itself also updates data and corresponding index entries. **You cannot conclude a delete will always be fast simply because it uses an `IXSCAN`.**

### 11.1. Inspecting the filter with find before executing delete

On a test database or when verifying before a controlled purge:

~~~javascript
db.support_tickets.find({
  tenantId: "shop-a",
  status: "EXPIRED",
  createdAt: { $lt: ISODate("2025-07-01T00:00:00Z") }
}).limit(20);
~~~

Evaluating the query path:

~~~javascript
db.support_tickets.find({
  tenantId: "shop-a",
  status: "EXPIRED"
}).explain("executionStats");
~~~

Inspect **winningPlan**, **totalKeysExamined**, **totalDocsExamined**, and **nReturned**. Running `explain` on `find` checks the corresponding document lookup path; it **does not reflect the full cost** of deleting or maintaining indexes.

### 11.2. Do not create indexes based solely on method names

A collection may have many different delete methods. Every index adds write and storage overhead, so measure frequent queries, selectivity, collection size, and read paths before deciding.

## 12. Differences from MongoTemplate.remove

With `MongoTemplate`, you can explicitly construct a `Query` and receive **DeleteResult**:

~~~java
import com.mongodb.client.result.DeleteResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("tenantId").is(tenantId)
        .and("status").is("EXPIRED")
);

DeleteResult result =
    mongoTemplate.remove(query, TicketDocument.class);

long deletedCount = result.getDeletedCount();
~~~

**This matches the goal** of a count-returning derived delete. `MongoTemplate` fits best when filters are built dynamically, complex criteria are needed, or explicit query options must be controlled.

### 12.1. Why is derived delete more concise?

~~~java
long deleted =
    repository.deleteByTenantIdAndStatus(
        tenantId,
        "EXPIRED"
    );
~~~

The repository encodes the filter right in the method name without repeating `Criteria` code in the service. For common, stable conditions, this is easy to read and test.

### 12.2. When you need the entity list before deletion

`MongoTemplate` provides an API like:

~~~java
List<TicketDocument> removed =
    mongoTemplate.findAllAndRemove(
        Query.query(
            Criteria.where("tenantId").is(tenantId)
                .and("category").is("TEST")
        ),
        TicketDocument.class
    );
~~~

This explicitly expresses the need to **retrieve entity data and delete**. Still, verify exact consistency semantics under concurrent writes and transactions in your library version; do not assume `findAllAndRemove` is a multi-document transaction.

### 12.3. Deleting one document and returning its data

When the condition targets a single document, `MongoTemplate` also offers **findAndRemove**:

~~~java
TicketDocument removed = mongoTemplate.findAndRemove(
    Query.query(Criteria.where("_id").is(id)),
    TicketDocument.class
);
~~~

This command targets **one document**. If the query matches nothing, the result can be `null`. Do not use `findAndRemove` to delete all documents by status; its purpose differs from multi-record derived deletes.

## 13. List-returning deletes and large data costs

A method like:

~~~java
List<TicketDocument> removeByTenantIdAndStatus(
    String tenantId,
    String status
);
~~~

can return **hundreds of thousands of entities** when the filter is broad. When that happens:

1. The driver must transfer entity payloads to satisfy the return value.
2. Spring Data must map BSON into Java objects.
3. Java retains a huge `List` in memory.
4. Deletion still touches many documents and indexes.
5. Audit/loggers may incur significant additional load.

If you only need the count, **returning `long`/`Long`** is far more suitable. If compliance requires saving deleted contents, design small batches, retention/audits, and recovery workflows instead of loading every document into a `List`.

### 13.1. Do not convert List into a count out of convenience

~~~java
// Avoid if the sole goal is counting deletions.
long deleted =
    repository.removeByTenantIdAndStatus(
        tenantId, "EXPIRED"
    ).size();
~~~

The snippet above may read many entities only to compute one number. Using **`long deleteBy...`** is the proper contract.

### 13.2. There is no "delete exactly N records" just from returning List

A `List` return type imposes no deletion limit. If business logic requires deleting in batches of 500 documents, build a separate workflow: select a bounded, deterministically sorted ID set, delete by IDs and safety conditions, record checkpoints, and loop under control.

Selecting IDs and deleting are multiple steps; concurrent updates can happen in between. If the process demands strict accuracy, design conditional writes/transactions or an explicit state machine.

## 14. Atomicity: one document vs. multiple documents

MongoDB guarantees **a write operation on a single document is atomic**, whereas deleting multiple documents via a derived delete **does not imply "all or nothing"** across multiple documents.

For example, deleting 10,000 expired tickets:

~~~java
long deleted =
    repository.deleteByTenantIdAndStatus(
        "shop-a", "EXPIRED"
    );
~~~

Do not assume:

- All 10,000 documents are deleted inside a default transaction.
- On mid-way failure, already-deleted documents automatically roll back.
- A pre-delete `List` of entities is an immutable snapshot.
- Prior counts and contents always reflect the exact same point in time.

### 14.1. When a multi-document transaction is required

Spring Data MongoDB integrates with transactions when the deployment supports them and **MongoTransactionManager** is configured:

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void purgeAndWriteAudit(String tenantId) {
    long deleted =
        ticketRepository.deleteByTenantIdAndStatus(
            tenantId, "EXPIRED"
        );

    auditService.recordPurge(tenantId, deleted);
}
~~~

This example illustrates **a service transaction boundary** only. For audit and deletion to share a real transaction, `auditService` must write via a mechanism managed by `MongoTransactionManager`, the call must go through Spring's transactional proxy, and the MongoDB deployment must support transactions. If `auditService` makes an HTTP call or sends a message to an external system, **MongoDB `@Transactional` does not roll back that external effect**.

### 14.2. Transactions do not replace validation

Even inside a transaction, the caller must be authorized to delete, the tenant filter must be accurate, and business states must be valid. Transactions can roll back a group of writes, yet **cannot prevent accidentally deleting documents matched by an overly broad filter**.

## 15. Optimistic locking with @Version

Spring Data MongoDB supports **@Version** on entities that need concurrent modification detection:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "support_tickets")
public record VersionedTicket(
    @Id ObjectId id,
    String tenantId,
    String status,
    @Version Long version
) {}
~~~

When deleting **a specific versioned entity**, repository operations supporting optimistic locking can check version and detect stale state per framework contract/version.

However, a derived delete:

~~~java
long deleteByTenantIdAndStatus(
    String tenantId, String status
);
~~~

**receives no `expectedVersion` from a Java entity**: its parameters are only `tenantId` and `status`. Never assume `@Version` on the entity automatically makes status-based derived deletes check each document's version like `delete(entity)`.

### 15.1. Constraining version in the filter

If you need to delete a document **only when its version is still 4**, use an explicit query:

~~~java
Query query = Query.query(
    Criteria.where("_id").is(id)
        .and("tenantId").is(tenantId)
        .and("version").is(4L)
);

DeleteResult result =
    mongoTemplate.remove(query, VersionedTicket.class);
~~~

If `deletedCount=0`, the ID may not exist, tenant may mismatch, or version changed. The application must report conflicts without leaking other tenants' data.

This is a **conditional delete** driven by the filter; there is no need to read and then unconditionally delete.

## 16. Tenant control, permissions, and sensitive data

Deletion is usually hard to reverse, so it requires stricter authorization checks than many read APIs.

### 16.1. Tenant must come from an authenticated context

Do not write controllers accepting an arbitrary `tenantId` query parameter and passing it straight through:

~~~java
repository.deleteByTenantIdAndStatus(
    requestTenantId,
    "EXPIRED"
);
~~~

Even with `tenantId` in the filter, a caller could supply another tenant's ID. The service must verify the tenant from an authenticated principal/session/token or enforced authorization policy.

### 16.2. Data returned in List can be sensitive

If `TicketDocument` holds customer names, phone numbers, or incident descriptions, **List<TicketDocument>** from a derived delete can send sensitive internal data into logs, responses, or messages.

Never return deleted entities directly from public APIs unless explicitly required and authorized. Map them to a DTO containing only **ID, status, and publishable fields**, or return just `deletedCount`.

### 16.3. Audits differ from logs

Printing deletion info to logs does not guarantee audit integrity or durability. If legal/compliance trails are required, design dedicated audit documents/events with write permissions, retention, tamper protection, and proper transaction/outbox rules.

## 17. Bulk deletion: avoiding overly broad filters

A method like:

~~~java
long deleteByStatus(String status);
~~~

can be extremely dangerous if `tenantId` is missing. A buggy controller passing an empty, null, or unexpected status can produce a derived filter very different from what was intended.

### 17.1. Pre-deletion guards

~~~java
public long deleteExpiredTickets(
        String tenantId,
        Instant cutoff
) {
    if (tenantId == null || tenantId.isBlank()) {
        throw new IllegalArgumentException(
            "Tenant is required"
        );
    }
    if (cutoff == null) {
        throw new IllegalArgumentException(
            "Cutoff is required"
        );
    }

    return repository
        .deleteByTenantIdAndStatusAndCreatedAtBefore(
            tenantId,
            "EXPIRED",
            cutoff
        );
}
~~~

Java validation is a protective layer, yet must pair with authorization checks. **Never treat input validation as a substitute for authorization**.

### 17.2. Dry-run workflow

Before a large purge, you can run a read query with the **same filter** to inspect a few sample IDs and the estimated count. However, dry-run results are only a point-in-time snapshot; data can change between dry-run and delete.

If you must guarantee "delete only the approved IDs", design the operation around the **approved ID list**, paired with tenant/version conditions and concurrency handling—never just count first and run an unbounded `deleteByStatus`.

## 18. Retries and idempotency of delete

In terms of final state, deleting by a fixed filter often behaves as:

~~~text
Run 1: deletes 5 documents -> deletedCount = 5
Run 2: no matching documents remain -> deletedCount = 0
~~~

Still, **you cannot conclude every derived delete retry has zero side effects**:

- A new document matching the filter might be created between two calls.
- Audit events, notifications, or callbacks might be emitted twice.
- The caller might lose connection after the server deleted the records but before receiving the response.
- `List`-returning deletes may perform a pre-read and observe different data across attempts.

### 18.1. Do not retry indefinitely on timeout

If a large delete times out, do not keep retrying with a broad filter without reconciliation. Limit retries, inspect errors, check remaining data, and use checkpoints or stable IDs when traceability is required.

### 18.2. Creating an operation key for critical purges

A large deletion run can be tracked with:

- **jobId**: identifier for the purge command.
- **tenantId** and approved filter.
- **cutoff** kept constant across retries.
- **processed IDs/chunks** or checkpoint.
- **deletedCount confirmed** and any indeterminate portion.

This is a dedicated operational architecture—not something obtained automatically by declaring a `deleteBy...` method.

## 19. Reactive derived deletes and return types

In reactive applications, repositories extend **ReactiveMongoRepository**:

~~~java
package com.example.support;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveTicketRepository
        extends ReactiveMongoRepository<TicketDocument, ObjectId> {

    Mono<Long> deleteByTenantIdAndStatus(
        String tenantId,
        String status
    );

    Flux<TicketDocument> removeByTenantIdAndCategory(
        String tenantId,
        String category
    );

    Mono<Long> deleteByTenantIdAndStatusAndCreatedAtBefore(
        String tenantId,
        String status,
        Instant cutoff
    );
}
~~~

Intended semantics:

- **Mono<Long>** emits the number of deleted documents.
- **Flux<TicketDocument>** emits entities involved in the delete operation, which may require reading data to supply payloads.

**Never call `block()` to get the count inside WebFlux.** Return the `Mono` or compose with `map`/`flatMap`.

### 19.1. Subscription executes the work

~~~java
Mono<Long> deletion =
    reactiveRepository.deleteByTenantIdAndStatus(
        tenantId, "EXPIRED"
    );
~~~

Merely constructing a `Mono` does not guarantee MongoDB executed the command. Only when WebFlux or a subscriber subscribes does the pipeline run.

### 19.2. Avoid subscribing multiple times

~~~java
// Avoid: subscribing manually and returning the Mono for WebFlux to subscribe again.
deletion.subscribe();
return deletion;
~~~

Two subscriptions can run two separate deletion passes. The second pass may encounter newly arrived matching data, so counts need not match the first run. For critical delete APIs, design idempotency/operation keys if requests can be retried or publishers resubscribed.

### 19.3. Flux-returning deletes are not a safe stream for arbitrary scale

Do not assume swapping `List` for `Flux` automatically turns deleting 1 million entities into a low-resource, strictly audited stream. Depending on implementation, entity-returning deletes may locate records and then delete them; cancellation, backpressure, and concurrent writes must be verified. For large purges, use bounded, checkpointed batch workflows.

## 20. When to choose MongoTemplate over derived methods?

Derived deletes work well for short, stable filters:

~~~java
long deleteByTenantIdAndStatus(String tenantId, String status);
~~~

`MongoTemplate` scales better when you have:

- Many optional request-driven filters, all still requiring authorization.
- Complex logical conditions (`$or`, `$elemMatch`, multi-branch date ranges).
- Workflow-dependent combinations of ID + version + business status.
- Deletions over bounded ID lists with checkpoints.
- Need to directly inspect **DeleteResult**, set query options, or run `findAndRemove`.

Example filter with tenant, status, and cutoff:

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is(tenantId)
        .and("status").is("EXPIRED")
        .and("createdAt").lt(cutoff)
);

DeleteResult result =
    mongoTemplate.remove(query, TicketDocument.class);
~~~

If you end up writing several repository methods just to cover arbitrary filter combinations, creating a custom repository fragment backed by `MongoTemplate` is much cleaner.

### 20.1. When should you use a TTL index?

If a collection holds documents that merely need to auto-expire after a timestamp and **do not require exact immediate deletion or auditing**, a MongoDB TTL index may suit better than scheduled derived deletes.

TTL deletion **does not run instantaneously at the exact timestamp** and requires configuring a BSON Date field properly; nor does it understand tenant permissions or complex business states. Never replace an audited purge workflow with TTL just to reduce delete commands.

## 21. Integration testing count-returning methods

Unit tests mocking repositories only confirm the service called the method; they **do not prove** Spring Data parsed the method name or MongoDB deleted with the right filter. Write integration tests against a dedicated MongoDB test instance (e.g., Testcontainers).

JUnit 5 example:

~~~java
package com.example.support;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.UUID;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class TicketDerivedDeleteTest {

    @Autowired TicketRepository repository;
    @Autowired MongoTemplate template;

    private TicketDocument ticket(
            String tenant,
            String status,
            String category,
            String subject) {
        return new TicketDocument(
            new ObjectId(),
            tenant,
            status,
            category,
            subject,
            Instant.parse("2025-06-01T09:00:00Z")
        );
    }

    @Test
    void returnsDeletedCountWithoutTouchingOtherTenant() {
        String tenant = "TEST-" + UUID.randomUUID();
        String otherTenant = "OTHER-" + UUID.randomUUID();

        TicketDocument a = repository.insert(
            ticket(tenant, "EXPIRED", "RETURN", "A")
        );
        TicketDocument b = repository.insert(
            ticket(tenant, "EXPIRED", "DELIVERY", "B")
        );
        TicketDocument keep = repository.insert(
            ticket(tenant, "OPEN", "RETURN", "C")
        );
        TicketDocument other = repository.insert(
            ticket(otherTenant, "EXPIRED", "RETURN", "D")
        );

        try {
            long deleted =
                repository.deleteByTenantIdAndStatus(
                    tenant, "EXPIRED"
                );

            assertThat(deleted).isEqualTo(2L);
            assertThat(repository.existsById(a.id())).isFalse();
            assertThat(repository.existsById(b.id())).isFalse();
            assertThat(repository.existsById(keep.id())).isTrue();
            assertThat(repository.existsById(other.id())).isTrue();

            assertThat(repository.deleteByTenantIdAndStatus(
                tenant, "EXPIRED"
            )).isZero();
        } finally {
            template.remove(
                Query.query(Criteria.where("tenantId").is(tenant)),
                TicketDocument.class
            );
            template.remove(
                Query.query(Criteria.where("_id").is(other.id())),
                TicketDocument.class
            );
        }
    }
}
~~~

This test seeds three tickets for a test tenant and one ticket for another tenant. It confirms:

1. **deletedCount=2** matches the two EXPIRED tickets.
2. The OPEN ticket in the same tenant is preserved.
3. The EXPIRED ticket in the other tenant is preserved.
4. Calling delete again with the same filter and no new data returns **0**.

Fixtures are created in a test database and cleaned up afterward; never run such deletion tests against production.

### 21.1. Do not depend on document ordering

When testing derived queries returning `List`, assert IDs with **containsExactlyInAnyOrder** or a `Set`, rather than relying on MongoDB natural order. If an API requires sorted results, design and explicitly test that ordering.

## 22. Testing methods returning an entity list

In the same test class from the previous section, add:

~~~java
@Test
void returnsEntitiesSelectedForDeletion() {
    String tenant = "TEST-" + UUID.randomUUID();

    TicketDocument first = repository.insert(
        ticket(tenant, "OPEN", "DEMO", "First")
    );
    TicketDocument second = repository.insert(
        ticket(tenant, "CLOSED", "DEMO", "Second")
    );
    TicketDocument keep = repository.insert(
        ticket(tenant, "OPEN", "OTHER", "Keep")
    );

    try {
        java.util.List<TicketDocument> deleted =
            repository.removeByTenantIdAndCategory(
                tenant, "DEMO"
            );

        assertThat(deleted)
            .extracting(TicketDocument::id)
            .containsExactlyInAnyOrder(
                first.id(),
                second.id()
            );

        assertThat(repository.existsById(first.id())).isFalse();
        assertThat(repository.existsById(second.id())).isFalse();
        assertThat(repository.existsById(keep.id())).isTrue();
    } finally {
        template.remove(
            Query.query(Criteria.where("tenantId").is(tenant)),
            TicketDocument.class
        );
    }
}
~~~

The test uses **List<TicketDocument>** to verify returned entity contents, while also confirming both documents were removed and the OTHER ticket stayed intact.

Never assert only **deleted.size() == 2** without checking IDs: if the method deleted the wrong two documents, a count-only test would still pass.

### 22.1. Additional test matrix

| Case | Expectation |
| --- | --- |
| Filter matches 0 documents | `long = 0`; empty `List` |
| Filter matches one document | `long = 1`; `List` holds matching entity |
| Filter matches many documents | Exact count; `List` holds exact IDs |
| Two tenants share same status | Only authorized tenant affected |
| `createdAt` exactly equals cutoff | `Before` does not delete items at exact cutoff |
| Missing status or legacy schema | Filter does not silently relax |
| Ticket changes status before delete | Deleted only if filter still matches at execution |
| Entity has `@Version` | Distinguish `delete(entity)` from derived delete |
| Missing appropriate index | Measure query and latency on sizable fixture |
| Returning `List` of many entities | Establish memory limits/costs |
| Soft-delete policy | No accidental hard delete calls |
| Mandatory transaction/audit | Verify rollback and external effects separately |

## 23. Common mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `deleteBy...` returns 0 despite existing data | Wrong tenant/status/BSON type filter or data changed | Inspect query and real documents |
| Deletes another tenant's tickets | Missing `tenantId` or unverified client tenant | Enforce tenant scoping and authorization |
| Intended a count but repo returns huge `List` | Wrong return type chosen | Use `long`/`Long` when only count is needed |
| `List` treated as guaranteed audit log | Reading and deleting may be separate steps | Design transaction/outbox/audit |
| Expected `removeBy...` to soft-delete | `remove` prefix does not mean setting `deleted` | Use update commands for soft deletion |
| Called `deleteAll()` on production | Confused with filtered `deleteAllBy...` | Restrict delete APIs, review code |
| `save`/`delete(entity)` and derived delete differ on concurrency | `@Version` does not auto-apply to every query | Use `expectedVersion`/conditional delete |
| Running `count` then `delete` reports wrong number | Two operations ran at different moments | Use `deletedCount` from delete itself |
| Deleting millions of records causes high load | Broad filter without batching | Plan checkpointed purge batches |
| Reactive delete appears to do nothing | Publisher was never subscribed | Return `Mono`/`Flux` in pipeline |
| Reactive deletes run multiple times | Duplicate subscriptions/retries | Add idempotency and avoid manual `.subscribe()` |
| Deletion very slow despite index | Many documents to remove or index maintenance | Inspect `find` explain and write metrics |
| Derived delete fails at startup | Wrong Java property name or unsupported return type | Check parser, entity, and return type |
| API returning deleted entities exposes sensitive fields | Returning raw `List<Entity>` in response/logs | Map to safe DTO and check permissions |

### 23.1. Diagnostic workflow

1. Confirm the repository actually targets the intended collection.
2. Read the method name: **delete/remove**, properties after **By**, operators **And/Before/In**.
3. Check Java property names and **@Field/@Id** mappings to BSON.
4. Cross-check tenant/status/cutoff against documents and permissions.
5. Verify return type: **long/Long** or **List<Entity>**.
6. Distinguish `deletedCount=0` from database/driver exceptions.
7. If returning `List`, confirm memory safety and do not treat `List` as a transactional snapshot.
8. For timeouts/concurrent writes, check retries, versioning, and auditing.
9. For slow queries, check indexes/`find` explain and actual delete metrics.
10. Reproduce with an integration test on an isolated fixture to avoid touching production data.

## 24. Practice exercises

### Exercise 1: choosing return type

A service must delete EXPIRED tickets of `shop-a` and return only the deleted count. Which signature should it use?

**Answer:** **long** or **Long**, e.g.:

~~~java
long deleteByTenantIdAndStatus(
    String tenantId, String status
);
~~~

There is no need for `List<TicketDocument>` when entity data is not needed.

### Exercise 2: returning data for recording

Business logic needs the ID and subject of DEMO tickets selected for deletion. Which method fits?

**Suggested answer:**

~~~java
List<TicketDocument> removeByTenantIdAndCategory(
    String tenantId, String category
);
~~~

Extract only the fields needed for recording, minding sensitive data and concurrent modifications. If strict audit guarantees are required, design an appropriate transaction or outbox.

### Exercise 3: understanding removeBy

A developer says "`removeByStatus` performs a soft delete." Is that true?

**Answer:** No. Derived `remove`/`delete` methods perform document deletion by default. Soft deletes require updates toggling status flags alongside updated read policies.

### Exercise 4: tenant protection

In a multi-tenant system, what problem can this method cause?

~~~java
long deleteByStatus(String status);
~~~

**Answer:** It can delete documents with that status across multiple tenants. Include `tenantId` in the filter, verify authorization, and never trust arbitrary client-supplied `tenantId`.

### Exercise 5: zero delete

A `deleteByTenantIdAndStatus` call returns 0. Did MongoDB fail?

**Answer:** Not necessarily. Simply no documents may have matched. The business layer decides whether 0 is a valid result or a condition worth reporting.

### Exercise 6: deleting before a cutoff

Write a method deleting a tenant's EXPIRED tickets created **before** an `Instant` cutoff.

~~~java
long deleteByTenantIdAndStatusAndCreatedAtBefore(
    String tenantId,
    String status,
    Instant cutoff
);
~~~

The **Before** condition is strictly less than `cutoff`; documents whose `createdAt` exactly equals `cutoff` do not match.

### Exercise 7: large List

A job needs to delete 500,000 documents and only report the count. Why is `List<TicketDocument>` costly?

**Answer:** It may have to read/map huge numbers of entities and hold them in a `List`, consuming RAM/network and risking timeouts. Return a count and design batched purges to control load.

### Exercise 8: count then delete

A service counts 12 tickets before deleting, yet the delete actually removes 10. Which number should the service return if reporting deleted count?

**Answer:** Return **10** from the delete result; the earlier count was an observation from a different point in time.

### Exercise 9: optimistic locking

An entity has `@Version`. Does a derived method taking only `tenantId` and `status` guarantee per-document version checks like `delete(entity)`?

**Answer:** Do not assume so. If `expectedVersion` is required, constrain version in the filter or use an entity/version deletion API with the proper contract.

### Exercise 10: reactive

A delete method by tenant/status in `ReactiveMongoRepository` needs to return the count. What is its return type?

**Answer:** **Mono<Long>**. If pre-deletion entity data is needed, a reactive return type like **Flux<TicketDocument>** can be used where supported by the API.

### Exercise 11: transaction and audit

Delete tickets in MongoDB and then send an HTTP audit event. Does placing `@Transactional` on the method guarantee both roll back together?

**Answer:** No. A MongoDB transaction does not cover an HTTP call to another service. Design an outbox/coordination protocol and verify transaction boundaries.

### Exercise 12: accurate testing

A test of a derived delete returning `List` passes `size=2`. Has the test proven the right two documents were deleted?

**Answer:** Not completely. You must check the IDs of the two documents in the `List`, verify they no longer exist in the database, and ensure documents outside the filter remained intact.

## 25. Production checklist

Before shipping a derived delete method:

- **Scope:** does the method name include required tenant, status, time, or business conditions?
- **Authorization:** are `tenantId` and policies verified from an authenticated principal?
- **Return type:** does the caller need `deletedCount` or genuinely need entity contents?
- **Volume:** what is the maximum number of matching documents?
- **Indexes:** is there an index supporting candidate lookup?
- **Concurrency:** could writers modify documents between read and delete?
- **Version:** does the operation require `expectedVersion` or transactions?
- **Soft delete:** do retention/recovery policies permit hard deletion?
- **Audit:** what data is recorded, where, and with what guarantees?
- **Retries:** is there protection against duplicate executions, timeouts, or ambiguous outcomes?
- **Reactive:** are subscriptions managed cleanly without blocking or duplicate subscriptions?
- **Tests:** have `deleted=0`, tenant isolation, exact IDs, and out-of-scope preservation been tested?

A **deleteBy...** method may be only a few lines long, yet deletion correctness relies on every one of these checks.

## 26. Summary

1. **deleteBy... and removeBy...** are Spring Data MongoDB's derived delete query prefixes; method names express filters from Java properties.
2. **long/Long** represents the **deleted document count**, ideal when entity payloads are not needed.
3. **List<Entity>** returns entity data associated with the deletion, potentially triggering a read step and higher memory/network cost.
4. **Return types do not create transactions** and do not guarantee consistent snapshots under concurrent writes.
5. **Deleting 0 documents is not automatically an error**; distinguish valid empty matches from exceptions.
6. **deleteById/delete(entity)** differ from predicate-based derived deletes; **deleteAll()** can wipe the entire collection.
7. **removeBy... does not mean soft delete**; soft deletes require updating status flags and dedicated query policies.
8. **Indexes help find target documents**, yet deletion still incurs write and index maintenance overhead.
9. **@Version, tenant, status, and authorization** must be designed intentionally; never assume they apply automatically to every derived delete.
10. **ReactiveMongoRepository uses Mono<Long>/Flux<Entity>** per return purpose, and must neither block nor subscribe twice.
11. **Real MongoDB integration tests** must verify deleted IDs, surviving IDs, and return values for each method signature.
12. **High-volume deletions need limits, checkpoints, and reconciliation**, not just a `List` return type.

Mastering **derived delete methods and return types** enables **SPRING_DATA_MONGODB** applications to choose intentional deletion paths, control affected data, avoid unnecessary reads, and build repository operations that are safe to test, monitor, and operate.
