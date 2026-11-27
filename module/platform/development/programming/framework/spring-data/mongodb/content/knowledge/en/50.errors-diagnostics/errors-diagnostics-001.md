# Classifying DataAccessException and Errors Translated from the MongoDB Driver

In a **Spring Data MongoDB** application, a `MongoTemplate`, repository, or `ReactiveMongoTemplate` operation can fail for many reasons: unique key collisions, lost connectivity, insufficient account permissions, invalid queries, update conflicts, or transaction failures. These causes require different handling strategies. Simply catching `Exception` and retrying or returning a generic HTTP 500 can cause duplicate requests, hide programming bugs, and make production diagnostics difficult.

Spring provides the **`DataAccessException`** data access exception hierarchy to express error categories relatively independently of the underlying storage technology. Spring Data MongoDB uses **exception translation** to convert many MongoDB Java driver errors into appropriate `DataAccessException` types. This lesson explains how to identify errors, choose handling strategies, log safely, and test in the context of connectivity, document mapping, queries, indexes, transactions, and reactive access.

## 1. An Error Can Pass Through Multiple Layers

Consider a user registration flow using an email address, where the `customers` collection has a unique index on `email`. An `insert` operation using an already-existing email can pass through the following layers:

~~~mermaid
flowchart TD
    A[Service calls MongoTemplate.insert] --> B[Spring Data MongoDB]
    B --> C[MongoDB Java driver]
    C --> D[(MongoDB server)]
    D --> E[Server returns duplicate key, code 11000]
    E --> F[Driver creates MongoWriteException or related type]
    F --> G[MongoExceptionTranslator / Spring Data]
    G --> H[DuplicateKeyException]
    H --> I[Service handles according to business rules]
~~~

Three layers to distinguish:

1. **Errors at the MongoDB server**: error code, error name, message, failed operation details, and error labels in supported cases.
2. **MongoDB Java driver exceptions**: typically part of the `com.mongodb.MongoException` family, such as `MongoWriteException`, `MongoCommandException`, `MongoTimeoutException`, `MongoSocketException`, or `MongoBulkWriteException`.
3. **Exceptions represented by Spring**: typically a subclass of `org.springframework.dao.DataAccessException`, such as `DuplicateKeyException`, `DataIntegrityViolationException`, or `DataAccessResourceFailureException`.

`DataAccessException` is an **unchecked exception**, so business code can handle specific error categories without depending directly on every MongoDB driver exception class. However, translation is **not a one-to-one mapping**: multiple driver errors can become the same Spring type, an error may lack a specialized Spring type, and code paths that use the driver directly may expose the raw exception.

## 2. Spring Data MongoDB's Exception Translation Mechanism

Spring Data MongoDB includes `MongoExceptionTranslator`, which implements the `PersistenceExceptionTranslator` contract. When using Spring Data APIs such as `MongoTemplate` or repositories, many driver errors are converted into types within Spring's data access exception hierarchy. The reactive execution path also provides corresponding error translation through the `onError` stream.

The `@Repository` annotation can participate in Spring's proxy-based exception translation for exception types supported by the translator. However, **annotating with `@Repository` does not automatically turn every `RuntimeException` into a `DataAccessException`**. Code that calls the MongoDB Java driver directly, third-party libraries, or custom callbacks must be checked individually to see which actual exception surfaces at each call boundary.

Example of common imports:

~~~java
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.data.mongodb.core.MongoTemplate;
~~~

You should not rely on **only the class name** to assume a driver exception will always be translated into a specific Spring class across all versions. Check the Spring Data MongoDB version, MongoDB Java driver version, operation type, and `cause` chain in actual logs and tests.

## 3. Classification by Meaning and Handling Action

The following table is a **common diagnostic guide**, not a rigid mapping rule that applies to every error and version:

| Category | Common Exception Type | Meaning | Initial Action |
| --- | --- | --- | --- |
| Unique constraint violation | `DuplicateKeyException` | Duplicate `_id` or unique index value; MongoDB typically reports code `11000` | Check duplicate key, return business error or handle idempotency; do not retry unconditionally |
| Data integrity violation | `DataIntegrityViolationException` | Write operation violates a data constraint or rule recognized by the translator | Read the actual cause and schema/index rules; fix the data or write flow |
| Version lock conflict | `OptimisticLockingFailureException` | Spring Data detects an update with a stale `@Version` | Re-read state, decide conflict resolution; may return `409 Conflict` for appropriate APIs |
| Resource inaccessible | `DataAccessResourceFailureException` or related driver exception | MongoDB is unavailable, connection/server selection failed, or required resource is unreachable | Check topology, network, pool, timeout, health; bounded retry if safe |
| Timeout | `QueryTimeoutException` or corresponding MongoDB driver exception | Query/operation exceeded time limit at some layer | Determine whether timeout occurred at server, driver, or application; check `explain`, load, and safety before retrying |
| Invalid API or argument usage | `InvalidDataAccessApiUsageException` | Misused API contract, invalid parameter, or access-layer configuration error | Fix code, check data types and mapping; usually do not retry |
| Insufficient permissions | `PermissionDeniedDataAccessException` or `MongoSecurityException`/`MongoCommandException` | Unauthenticated or unauthorized to execute command | Verify user, roles, database, and authentication mechanism configuration |
| Unclearly classified error | A generic `DataAccessException` or original MongoDB driver exception | Translator has no specialized type, or error went through another call path | Inspect cause, error code, labels, command, and context; avoid concluding from the outer wrapper alone |

Note the difference between **exception type** and **retry policy**. A `DataAccessResourceFailureException` may stem from a transient incident, yet repeating a write operation after a lost connection can still be dangerous if you cannot determine whether the first write succeeded. Conversely, `DuplicateKeyException` usually will not resolve itself even if retried.

### Common Underlying Driver Classes to Recognize

| Driver Exception | Situation to Investigate |
| --- | --- |
| `MongoWriteException` | A single write operation was rejected by the server; check error code, write error, unique index, or validator |
| `MongoBulkWriteException` | Bulk operation encountered errors on one or more items; **partial writes may have succeeded** when outside an enclosing transaction |
| `MongoCommandException` | Command failed, e.g., insufficient privileges or unsupported option |
| `MongoWriteConcernException` | Write did not satisfy the requested write concern acknowledgment; verify actual state |
| `MongoTimeoutException` | Failed to select a server or operation timed out by specific type/layer; check timeout settings, topology, and load |
| `MongoSocketException` | Network socket communication failure; may occur before or after the server processed the request |
| `MongoSecurityException` | Authentication, credential, or security mechanism failure |

Read the **class + error code + error labels + cause + running operation** together, because each piece explains a different aspect.

## 4. `DuplicateKeyException`: Constraint Violation or Duplicate Request?

Suppose an application has a `customers` collection and requires emails to be unique:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("customers")
public class Customer {
    @Id
    private String id;

    @Indexed(unique = true)
    private String email;

    private String displayName;

    // Constructors, getters, and setters omitted.
}
~~~

`@Indexed(unique = true)` declares the intent to create a unique index. In real projects, you must **verify that the index actually exists** in MongoDB. Modern versions of Spring Data MongoDB do not automatically create indexes by default solely from the annotation; indexes must be configured or created via a dedicated deployment mechanism. If no unique index exists in the database, two concurrent writes can both succeed.

Example service handling `DuplicateKeyException` at the business boundary:

~~~java
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class CustomerRegistrationService {
    private final MongoTemplate template;

    public CustomerRegistrationService(MongoTemplate template) {
        this.template = template;
    }

    public Customer register(Customer customer) {
        try {
            return template.insert(customer);
        } catch (DuplicateKeyException ex) {
            throw new CustomerAlreadyExistsException(
                "Cannot register because identifier key already exists", ex);
        }
    }
}

class CustomerAlreadyExistsException extends RuntimeException {
    CustomerAlreadyExistsException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

This example simplifies the business policy. **Do not assume** every `DuplicateKeyException` on `customers` is a duplicate email: the error could stem from `_id` or another unique index. If you need to return an "email already in use" message, identify the relevant constraint using the index structure and reliable error details rather than guessing from the service name.

In a diagnostic environment, you can inspect the indexes and the operation that triggered the error:

~~~javascript
db.customers.getIndexes();
db.customers.findOne({ email: "test@example.com" });
~~~

The error typically contains **code `11000`** (`E11000 duplicate key error`) when the server detects a unique index violation. Do not write business logic based on parsing the `E11000` string or extracting index names from the message: message formatting can change, may expose sensitive values, and is not a stable API. Rely on the exception type/code at the appropriate layer and known business data.

**Do not solve this with a plain "check first, then insert":** between `find` and `insert`, another request can still write the same key. A unique index is the boundary that guarantees uniqueness; application code must handle conflicts when concurrent flows race.

## 5. `DataIntegrityViolationException` and Invalid Data Errors

`DataIntegrityViolationException` is a general exception for certain data integrity violations. `DuplicateKeyException` is a more specific type in Spring's DAO hierarchy. Therefore, if you need to distinguish both, catch the more specific type first:

~~~java
try {
    template.insert(customer);
} catch (DuplicateKeyException ex) {
    // Handle duplicate key according to business rules.
    throw ex;
} catch (DataIntegrityViolationException ex) {
    // Investigate other integrity constraints if classified by the translator.
    throw ex;
}
~~~

MongoDB supports collection validation rules, unique indexes, type/value checks, and various application-layer constraints. However, **there is no guarantee** that every MongoDB validator error will always become a `DataIntegrityViolationException` across all Spring Data versions. An error may surface as `MongoWriteException`, `MongoCommandException`, or a less specialized Spring exception. You must inspect the code, cause, and operation source.

When a document is rejected by validation, check whether it conforms to the JSON Schema/validator, BSON types (`Date`, numeric types, string, `ObjectId`), nullability policies, and `@Field` mappings. Do not retry the exact same payload if the input has not changed; fixing the data or the code producing it is the proper solution.

## 6. `OptimisticLockingFailureException` and Concurrent Updates

Spring Data MongoDB supports **optimistic locking** via a `@Version` field. Suppose two requests both read a `ProductStock` document with `version = 7`. Request A saves first and increments the version. Request B still attempts to save the document with the stale version; when the version condition does not match, Spring Data can throw `OptimisticLockingFailureException`.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("product_stock")
public class ProductStock {
    @Id
    private String id;

    @Version
    private Long version;

    private int availableQuantity;

    // Constructors, getters, and setters omitted.
}
~~~

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as MongoDB
    A->>DB: Read stock version=7
    B->>DB: Read stock version=7
    A->>DB: Save with condition version=7
    DB-->>A: Success, version=8
    B->>DB: Save with condition version=7
    DB-->>B: Version mismatch
    B-->>B: OptimisticLockingFailureException
~~~

Key points:

- You must use Spring Data operations that support `@Version` in the proper context. If you update via the driver directly or a custom statement that omits version from the filter condition, the protection can be bypassed.
- Use an **acknowledged write concern** so that an operation modifying zero documents can be detected; without write acknowledgment, you cannot reliably use modified document counts to detect conflicts.
- A conflict results from concurrent updates, **not** a lost connection. You can re-read and reapply the command if business logic permits; do not repeatedly retry saving the stale object.
- When an API uses optimistic locking to prevent lost updates, returning `409 Conflict` is a common choice; the application must decide whether to surface the updated state to the user.

Inventory examples must also consider the atomicity of decrementing quantities. For a "deduct only when sufficient stock remains" rule, a conditional database `update` may be more suitable than a read–compute–write cycle, while still handling the case where zero documents are updated.

## 7. Connection Loss, Timeouts, and Uncertain Outcome States

Socket or server selection errors are fundamentally different from duplicate key errors. They can happen at different points:

1. **Before sending the request**: for example, the client cannot find a suitable server. No write operation may have occurred yet.
2. **While sending or waiting for the response**: the client may not know whether the server executed the operation.
3. **After the server processed it**: the connection drops before the client receives the acknowledgment, leaving the outcome uncertain to the client.

These errors typically involve `MongoSocketException`, `MongoTimeoutException`, server selection exceptions, and are sometimes represented by Spring as `DataAccessResourceFailureException`. `MongoExecutionTimeoutException` can occur if a query exceeds a server-side execution time limit; this scenario requires different diagnostics than failing to establish a connection.

When errors involve connectivity or timeouts, check the MongoDB URI (without exposing passwords), DNS, TLS, replica set/shard topology, connection permissions, pool settings, `serverSelectionTimeout`, `connectTimeout`, `socketTimeout`/applicable timeout settings, execution limits such as `maxTimeMS`, CPU/I/O load, and currently running commands.

**Never infer "the write definitely failed" from a client-side timeout alone.** If an order creation request loses its response, automatically re-sending the same command can create a second order if the first one actually committed. Use an idempotency key or stable identifier, a unique index, and a state reconciliation query before deciding to write again.

The MongoDB driver has its own retryable reads/writes mechanism and rules depending on configuration, topology, and operation type. Custom retries built in Spring must account for the fact that the driver **may have already retried**. For non-idempotent commands or those with side effects outside MongoDB, multi-layer retries increase the risk of duplicate outcomes.

## 8. Transaction Errors: Distinguishing Full-Transaction Retry from Commit Retry

MongoDB transactions can encounter conflicts, network failures, or uncertain commit states. Some driver exceptions carry **error labels** to help callers choose a recovery strategy. Two important labels:

| MongoDB Label | Operational Meaning | Recommended Handling Direction |
| --- | --- | --- |
| `TransientTransactionError` | Transaction encountered a potentially transient error before commit completed | Consider re-running the **entire transaction** from the beginning with appropriate data and a bounded attempt count |
| `UnknownTransactionCommitResult` | Client is uncertain how the commit result was acknowledged | Use a **commit retry** procedure; do not automatically re-run the entire business logic as a new transaction |

The `UnknownTransactionCommitResult` case is very sensitive: a commit may have succeeded even though the client never received confirmation. Calling an order-creation API again from scratch is completely different from retrying `commitTransaction` within the same transaction handling flow.

If using `MongoTransactionManager` and `@Transactional` in Spring Data MongoDB, clearly understand transaction completion mechanics and retry boundaries. Do not mechanically put `@Retryable` on an entire method, especially when the method also sends emails, calls a payment gateway, or emits events before commit. Side effects external to the database should be coordinated using patterns such as a **transactional outbox** and idempotent consumers where appropriate.

Error labels can be obscured by Spring wrapper exceptions if you only inspect the outer exception. When diagnosing, walk the `cause` chain to locate `MongoException`, while still respecting the transaction-handling contract of the framework in use.

## 9. Choosing Retries Based on Cause and Idempotency

| Scenario | Retry Immediately? | Appropriate Condition / Solution |
| --- | --- | --- |
| `DuplicateKeyException` | Usually **no** | Handle conflict via unique index; if it is a valid repeated request, return the previous result by idempotency key |
| Invalid validation/schema | **No** | Fix the data, mapping, or write command |
| `OptimisticLockingFailureException` | **Conditional** | Re-read latest state and re-evaluate rules with a bounded attempt limit |
| Connection loss before read | **Conditional** | Retry with backoff/jitter when the service can recover, with timeout/budget |
| Timeout during write | **Inconclusive** | Check write outcome, idempotency, retryable-write semantics, and attempt limit |
| `TransientTransactionError` | **Conditional** | Retry entire transaction per driver/framework guidance; avoid duplicate side effects |
| `UnknownTransactionCommitResult` | **Do not retry business logic from scratch** | Handle commit retry per transaction contract and state reconciliation |
| Insufficient permissions / bad credentials | **No** | Fix user, role, secret, and authentication configuration |
| Invalid API usage | **No** | Fix query, parameters, mapping, or code |

A proper retry policy needs a **total time budget**, a maximum attempt count, exponential backoff/jitter, observability on retry counts, and backpressure control on the failing system. Never use `retryWhen(Retry.indefinitely())` on a business write flow.

## 10. Inspecting `cause` and Error Metadata Without Locking onto Message Text

When Spring throws `DataAccessException`, the outer wrapper expresses the **error category**; `getCause()` may preserve the underlying driver exception, providing error codes and error labels. A small diagnostic helper:

~~~java
import com.mongodb.MongoException;

public final class MongoErrorDetails {
    private MongoErrorDetails() {}

    public static MongoException findMongoCause(Throwable error) {
        for (Throwable current = error; current != null;
             current = current.getCause()) {
            if (current instanceof MongoException mongo) {
                return mongo;
            }
        }
        return null;
    }
}
~~~

Applications can use the helper to log **safe metadata**:

~~~java
import com.mongodb.MongoException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;

public class MongoErrorReporter {
    private static final Logger log = LoggerFactory.getLogger(MongoErrorReporter.class);

    public void report(String operation, DataAccessException error) {
        MongoException driverError = MongoErrorDetails.findMongoCause(error);
        if (driverError == null) {
            log.warn("mongo operation={} springType={}",
                operation, error.getClass().getSimpleName());
            return;
        }

        log.warn("mongo operation={} springType={} driverType={} code={} "
                + "transientTx={} unknownCommit={}",
            operation,
            error.getClass().getSimpleName(),
            driverError.getClass().getSimpleName(),
            driverError.getCode(),
            driverError.hasErrorLabel("TransientTransactionError"),
            driverError.hasErrorLabel("UnknownTransactionCommitResult"));
    }
}
~~~

The snippet above is **diagnostic**; `MongoException.getCode()` may not yield a useful server code for connection-layer failures. For bulk writes, details inside `writeErrors` must be handled separately. In production, also log `requestId`/`traceId`, collection, operation name, latency, retry state, and MongoDB environment (without exposing secrets).

Do not unconditionally log full MongoDB connection strings containing credentials, payloads containing personal data, entire documents, or `error.getMessage()`: some error messages can include field names and sensitive data values. Do not rely on regex matching over message strings to route errors; prefer exception types, structured error codes, and business-contract data.

## 11. Exception Handling in Blocking and Reactive Applications

### With `MongoTemplate` or Synchronous Repositories

Place error handling at the appropriate layer:

- **Repository / data access**: execute data operations and let exceptions propagate if they cannot be meaningfully handled there.
- **Service**: translate data conflicts into business decisions, such as existing email or version conflicts.
- **API boundary**: map business errors to stable HTTP responses without leaking stack traces or database messages.
- **Observability**: record type, code, trace ID, latency, and retry state for diagnostics.

`catch (DataAccessException ex)` is the last catch-all for recording general data access failures. If you already catch a specific type (`DuplicateKeyException`), place that `catch` **before** `DataAccessException`; reversing the order makes the specific branch unreachable.

Not every data access error should be turned into the same HTTP 500. For example, a `DuplicateKeyException` tied to a well-defined uniqueness rule can map to `409 Conflict`, whereas an unavailable MongoDB system can map to a temporary `503 Service Unavailable` response with a client retry policy. Actual response conventions must align with the API contract and write operation state.

### With `ReactiveMongoTemplate` or `ReactiveMongoRepository`

Exceptions in a reactive pipeline are normally propagated through the **`onError`** signal after subscription. Wrapping the creation of a `Mono` or `Flux` in `try/catch` will not catch most errors that occur later when MongoDB executes. You can use `onErrorMap`, `onErrorResume`, and `retryWhen` with appropriate error filters.

~~~java
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Mono;

public class ReactiveCustomerRegistrationService {
    private final ReactiveMongoTemplate template;

    public ReactiveCustomerRegistrationService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Mono<Customer> register(Customer customer) {
        return template.insert(customer)
            .onErrorMap(DuplicateKeyException.class,
                ex -> new CustomerAlreadyExistsException(
                    "Cannot register because identifier key already exists", ex));
    }
}
~~~

In the pipeline above, `onErrorMap` transforms the error type so the API layer understands it; it **does not re-run the operation**. A `retryWhen(...)` should only be added after confirming the condition is retryable and the operation is idempotent; also account for the fact that resubscribing can repeat the entire write operation.

## 12. Bulk Writes, Transactions, and Multi-Document Operations

Bulk writes can partially succeed before encountering an error. With **unordered** bulk writes, the driver can continue processing other items even if one item fails; with **ordered** bulk writes, execution normally stops at the first error, yet preceding operations may already be persisted. Without an enclosing transaction, you cannot treat the entire batch as an all-or-nothing unit.

Suppose an import job processes 1,000 customers, 12 of which have duplicate emails violating a unique index. If a bulk error triggers an uncontrolled retry of all 1,000 records via `insert`, the previously succeeded records will keep throwing duplicate key errors. Inspect individual errors, reconcile already-written records, and organize retries around idempotent keys or smaller batches.

When using transactions, a mid-flight error can abort the transaction; however, you must still distinguish **transaction rollback** from external side effects (emails, webhooks, brokers) that MongoDB cannot automatically roll back. If you need to transition business state and then emit an event, consider persisting an outbox record within the same transaction and having a publisher dispatch it after commit.

## 13. Production Error Diagnostic Workflow

Follow this order to avoid trial-and-error on a loaded system:

1. **Record context:** operation (`insert`/`save`/`update`/`find`/`aggregate`/`bulkWrite`), collection, environment, application version, timestamp, and trace ID.
2. **Identify outer exception type and root cause:** which `DataAccessException`, whether `cause` contains a `MongoException`, and what code/labels exist.
3. **Classify the symptom:** integrity, optimistic conflict, permission, connectivity, timeout, transaction, or programming bug.
4. **Verify actual facts:** inspect document/index/transaction status or write results using safe reconciliation queries, especially on timeouts.
5. **Check system conditions:** replica set/shard health, TLS/DNS, pool, slow queries, `explain("executionStats")`, write concern, and actual load where relevant.
6. **Take bounded action:** return business error, fix data, retry with backoff, fail fast, quarantine bad records, or recover transaction according to error labels.
7. **Monitor after remediation:** frequency by exception type/code, retry rate, MongoDB latency, pool wait, errors per collection, and data quality.

### Quick Diagnostic Examples

| Symptom | Signals to Check | Resolution Direction |
| --- | --- | --- |
| Two requests register the same email concurrently | `DuplicateKeyException`, unique index on `email`, code 11000 | Handle conflict; ensure unique index truly exists and business message is accurate |
| Concurrent stock writes cause lost updates | `@Version`, `OptimisticLockingFailureException`, or unguarded updates | Apply compare-and-set/atomic update; handle conflict on stale versions |
| All queries occasionally time out | Pool/server selection errors, DNS, CPU/I/O, connections, slow queries | Separate infrastructure faults from slow queries; avoid aggressive retries |
| Bulk import job stops midway | `MongoBulkWriteException`, write errors, and partially written results | Reconcile per record, split batches, design idempotent retries |
| Transaction returns an error on commit | Label `UnknownTransactionCommitResult` | Follow commit retry workflow; do not re-execute business logic as a new attempt |
| Query allowed in dev but fails in prod | User/role, authentication DB, command code | Fix permissions and deployment config; do not mask with retries |

## 14. Testing Your Error Classification Strategy

You do not need to mock every internal detail of `MongoExceptionTranslator`; test **observable behavior** at data and business boundaries. For integration tests, use a real MongoDB instance in an appropriate test environment (such as Testcontainers). Transaction tests require MongoDB configured as a replica set or a transaction-capable sharded cluster.

| Scenario | Outcome to Verify |
| --- | --- |
| Two documents with the same unique key | MongoDB rejects the second command; the Spring boundary receives the expected error type in the running version |
| Same operation via `MongoTemplate` and direct driver | Document any differences in exception type and `cause` |
| Saving an entity with stale `@Version` | Does not overwrite the newer document; returns conflict error per contract |
| Connection loss or server selection timeout | System reports infrastructure error, performs bounded retries, and does not enter an infinite loop |
| Write succeeded but client lost the response | Idempotency/reconciliation produces no extra side effects |
| Bulk write with valid and duplicate-key records | Verify written count, failed records, and safe re-run capability |
| Reactive insert hitting duplicate key | `onErrorMap` transforms into business error upon subscription; emits no extra document |
| Transaction failing mid-way | External side effects are not assumed rolled back; error labels handled per policy |

You should also add log assertions to ensure emails, tokens, passwords, connection strings, or full documents are never leaked. When upgrading Spring Data MongoDB or the driver, re-run exception classification tests because mapping details and causes can change.

## 15. Key Takeaways

`DataAccessException` lets Spring code represent **data access error categories**, while `MongoException` and details such as **error codes** or **error labels** explain deeper driver/server causes. Inspect both when diagnosing; do not rely on a single message string or assume every error translates identically across all versions.

With **Spring Data MongoDB**, handle `DuplicateKeyException` via uniqueness/idempotency rules, `OptimisticLockingFailureException` via concurrent update conditions, connectivity and timeout errors according to system health and write certainty, and transaction errors according to their labels. **Choose recovery based on data correctness and business behavior**, and only then decide whether to retry, return an error, or reconcile.
