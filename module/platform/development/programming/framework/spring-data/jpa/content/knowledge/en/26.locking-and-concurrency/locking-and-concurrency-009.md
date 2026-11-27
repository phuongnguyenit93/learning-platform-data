# Bounded Retries, Idempotency, and Fresh Transactions After Failure

## Objectives

In a Spring Data JPA system, a transaction can fail transiently due to an optimistic locking conflict, deadlock, lock acquisition failure, or database resource error. Retrying lets the application attempt an operation again when the cause is likely to clear. However, retrying is unsafe if it runs unboundedly, duplicates side effects, or reuses a rolled-back transaction.

Three principles must go together:

1. **Bounded retries:** set a maximum number of attempts, increasing wait delays, jitter, and an appropriate deadline.
2. **Idempotency:** submitting the same request multiple times produces only one business effect and returns the same recorded result.
3. **Fresh transaction after failure:** each attempt must run in a new transaction/persistence context; a failed transaction must roll back before retrying.

This article classifies retryable errors, explains transaction boundaries and idempotency keys, handles cases where it is unknown whether a transaction committed, presents the outbox pattern for external side effects, and provides a runnable Java 17+ example with Spring Boot, Spring Data JPA, and H2.

## 1. Why are retries needed?

Not every database error is permanent. Some errors disappear if the operation runs again after a competing transaction finishes:

- Optimistic locking conflict: another transaction updated the version first.
- Deadlock: the database chose to abort one transaction to break a lock-wait cycle.
- Lock timeout or lock acquisition failure: the resource was held by another transaction.
- Transient resource error: brief connection interruption or temporary database unavailability.

For an entity with `@Version`: two transactions both read version 4. Transaction A updates and commits version 5. Transaction B still tries to write based on version 4, so B's UPDATE matches zero rows and JPA reports an optimistic locking failure. If the business rule remains valid after re-reading fresh data, the application can rerun the entire use case in a new transaction.

Retrying does not make an invalid operation valid. If balance is insufficient, stock is out, input is invalid, or the user lacks permission, retrying the same input will usually keep failing. Such business errors should be returned to the caller or handled by separate rules.

## 2. Distinguishing retryable and non-retryable errors

Retry only errors that are likely transient and recoverable by re-running the entire operation:

| Error group | Examples | Handling |
| --- | --- | --- |
| Concurrency conflicts | `OptimisticLockingFailureException`, `PessimisticLockingFailureException` | Can retry if the use case is safely designed and within the time budget. |
| Deadlock/transient lock | `DeadlockLoserDataAccessException`, `CannotAcquireLockException` | Can retry in a new transaction with backoff. |
| Transient resource | Certain `TransientDataAccessResourceException` | Retry only when knowing the operation can be safely re-run. |
| Data integrity violation | `DataIntegrityViolationException`, unique/check/foreign-key violation | Normally do not retry; fix data or handle duplicates via idempotency. |
| Business error | Out of stock, insufficient balance, existing reservation | Do not auto-retry under the same conditions. |
| Input/authorization error | Validation, authentication, authorization | Do not retry. |
| Query/config error | Invalid JPQL, wrong mapping, missing schema column | Do not retry; fix code or schema. |

Spring has the `DataAccessException` hierarchy. `TransientDataAccessException` represents a group of errors considered potentially transient; optimistic/pessimistic locking failures typically sit in the corresponding concurrency branch. Even so, do not catch every `DataAccessException` and retry: non-transient errors will keep repeating and mask the root cause.

Exact exception classification also depends on the JPA provider, JDBC driver, and database. Observe actual exceptions on the production database and only add error types to your retry policy after confirming their semantics.

## 3. Limiting the number of attempts

Retries must be bounded. A policy typically defines:

- `maxAttempts`: total number of calls, including the first attempt.
- `initialDelay`: wait time after the first failure.
- `maxDelay`: maximum wait cap.
- `multiplier`: delay growth factor, typically 2.
- `jitter`: randomness added to delay so many clients do not retry at the exact same instant.
- `deadline`: maximum total time the request or job is allowed to continue.

Example policy:

```text
maxAttempts = 4
initialDelay = 50 ms
multiplier = 2
maxDelay = 500 ms
jitter = 50% .. 100% of delay
```

Base delay grows as follows:

| Failure # | Base delay before jitter |
| ---: | ---: |
| 1 | 50 ms |
| 2 | 100 ms |
| 3 | 200 ms |

With 4 attempts, after the fourth failure the application stops and returns the final error. Jitter staggers retry timings across clients, reducing the thundering herd effect when the database recovers.

Do not set `maxAttempts` excessively high to compensate for poorly designed transactions. Consider API latency, HTTP caller timeouts, request hold times, and database resource limits. Retrying can outlast the request deadline, causing the caller to time out while the server keeps working.

## 4. Backoff and jitter

Exponential backoff increases wait times exponentially:

```java
long delay = Math.min(maxDelay, initialDelay * (1L << failedAttempt));
```

Do not let all clients use the exact same fixed delay. If thousands of requests fail together and all retry after 100 ms, they create another simultaneous load spike.

Jitter can pick a random value between 50% and 100% of the base delay:

```java
long actualDelay = ThreadLocalRandom.current()
        .nextLong(Math.max(1, delay / 2), delay + 1);
```

Bound the shift/multiplication to avoid overflow and always cap at `maxDelay`. In tests, you can inject a clock/sleeper or use a 0 delay to test call counts without slowing tests down.

### Do not retry forever when the database is overloaded

Retries increase the number of requests sent to the database. If the database is overloaded, unbounded retries can make matters worse. Use small attempt counts, backoff with jitter, sensible connection pools, and circuit breakers/bulkheads when the system needs resource protection at scale.

For background jobs, you can persist attempt state and retry schedules into a queue instead of keeping a thread sleeping for a long time. For synchronous APIs, once the deadline expires, return an appropriate temporary error so the caller decides when to try again.

## 5. Every attempt must get a fresh transaction

This is the single most important rule when retrying JPA operations:

**Do not catch an error inside a failed transaction and continue using that transaction.**

When an optimistic lock, deadlock, or persistence error occurs, the transaction may already be marked rollback-only. The persistence context may also hold entities in a state no longer consistent with the database. Calling repository methods again inside the same transaction may continue failing or lead to `UnexpectedRollbackException` on commit.

Correct flow:

```text
Retry facade (holds no transaction)
    |
    +-- attempt 1 --> New transaction A --> error --> rollback A
    |
    +-- backoff
    |
    +-- attempt 2 --> New transaction B --> re-read state --> commit/rollback B
    |
    +-- ... up to maxAttempts
```

This can be implemented with two separate Spring beans:

- `RetryFacade`: controls attempt counts and backoff; does not open a transaction around the loop.
- `TransactionalWorker`: executes one business attempt inside `@Transactional(propagation = REQUIRES_NEW)`.

Each retry invokes the worker through a Spring proxy, so the transaction interceptor creates a fresh transaction. If the worker throws a runtime exception, that attempt's transaction rolls back before the exception reaches the facade.

### Why split into two beans?

Spring applies `@Transactional` via proxies. If a method in a class directly calls another method in the same class (self-invocation), the internal call usually bypasses the proxy, so annotations on the target method may not apply as expected.

Splitting the retry facade and transactional worker into two beans establishes a clean boundary: the facade calls the worker through the proxy on every attempt.

### REQUIRES_NEW and NOT_SUPPORTED

`REQUIRES_NEW` creates a fresh transaction for each execution, suspending any active transaction if one exists. The retry facade can use `NOT_SUPPORTED` to ensure the loop does not run inside an outer transaction.

Not every application needs both annotations. What is essential is that the failed transaction has completed before the next attempt begins and the new attempt has its own persistence context.

## 6. Idempotency: same request, same effect

Retries can send the same command multiple times. Moreover, the same business operation may be called repeatedly because:

- The client timed out and resent the request even though the server committed.
- A gateway or message broker redelivered a message.
- The server retried after a connection drop without knowing whether commit succeeded.
- A user clicked a button multiple times.

Idempotency means processing the same request identity multiple times does not duplicate business effects or alter the recorded result. A common approach is requiring clients to send a unique **idempotency key** for a logical operation.

Example:

```http
POST /purchases
Idempotency-Key: order-2026-000123
```

The server stores the key along with key payload fields and the result. If the same key with the same payload is submitted again, the server returns the stored result without deducting stock a second time.

### The unique constraint must live in the database

Do not merely call `existsByRequestKey(key)` and then insert. Two transactions can check simultaneously and both see the key missing. Create a unique constraint on the idempotency key:

```sql
create table processed_requests (
    id bigint generated by default as identity primary key,
    request_key varchar(100) not null unique,
    item_id bigint not null,
    quantity integer not null,
    remaining_after integer not null
);
```

The database arbitrates two requests sharing the same key. One transaction inserts successfully; the other waits and then receives a unique violation if the first commits.

In multi-tenant systems or systems with multiple command types, keys should be scoped by tenant and operation type, e.g., unique `(tenant_id, operation_type, request_key)`, to prevent two customers from accidentally colliding on the same key string.

### Same key with different payload must be rejected

Never return an old result for a request with the same key but different content. Store enough fields to compare or store a hash of the canonicalized payload.

For example, key `order-123` first buys item 10 quantity 2; later the same key arrives buying item 11 quantity 5. The server must report an idempotency key reuse conflict, rather than returning the first order's result as if the second request succeeded.

In the example at the end of this lesson, payload is compared using `itemId` and `quantity`. For complex requests, use a canonical payload hash and scope the key by user/tenant and operation type.

## 7. Recording the idempotency record and business logic in the same transaction

To ensure the database never records a request as succeeded without applying the business logic (or vice versa), write the operation record and update business data in the **same transaction**:

```text
BEGIN
  INSERT processed_request(request_key, payload...)
  UPDATE inventory ...
  UPDATE processed_request SET result = ...
COMMIT
```

If updating inventory fails or the transaction rolls back, the idempotency record rolls back as well. On retry, a new transaction can attempt to insert the same key and execute again.

If commit succeeds but the response is lost on the way back to the client, the retry finds the committed idempotency record and returns the previous result. This is why the idempotency record must commit atomically with the business mutation.

### Handling concurrent duplicate requests

Two requests with the same key may initially read and see no record. Both attempt to insert:

1. The first transaction inserts the key and proceeds with business logic.
2. The second transaction inserts the same key; the unique constraint makes it wait on the first transaction.
3. If the first transaction commits, the second transaction receives a duplicate-key violation.
4. The second transaction rolls back; the facade reads the committed record in a fresh read transaction and returns the result.

If the first transaction rolls back, the second transaction can succeed in inserting and become the transaction executing the business operation.

Do not catch duplicate-key and continue querying inside the failed transaction itself. That transaction must roll back first; afterward use a separate read bean or a new transaction to fetch the saved result.

### Should business failure outcomes be stored?

Consider a purchase failing due to out-of-stock. Two policies exist:

- **Do not store business errors:** the transaction rolls back the idempotency record as well. If stock is replenished, the same key can be retried and succeed. The example at the end uses this policy.
- **Store rejection results:** record a REJECTED status and response per the idempotency policy. This requires designing an explicit transaction to persist the rejection without deducting stock.

Choose the policy according to your API contract. Never accidentally persist an incomplete request as if it had completed.

## 8. Retrying when it is unknown whether commit happened

A difficult scenario is a connection drop during commit. The application receives an exception without knowing whether the database committed or not.

You cannot resolve this situation merely by inspecting the exception and guessing. An idempotency key enables safe retrying:

- If the old transaction rolled back, the key does not exist yet; the new attempt can execute.
- If the old transaction committed, the key already exists; the new attempt hits a duplicate key, rolls back, and reads the previous result.

The facade should distinguish a duplicate caused by the idempotency key from other data violations by looking up the record by key after rollback and matching the payload. If no matching record is found, rethrow the original error.

This is a recovery mechanism for ambiguous commit outcomes. It does not mean every external side effect outside the database becomes automatically exactly-once.

## 9. External side effects and transactional outbox

Suppose a transaction deducts inventory and then sends an email or calls a payment gateway. A database transaction cannot roll back an email already sent or an HTTP request already processed by another system.

Do not naively place external side effects inside a retry loop:

```text
Attempt 1:
  update database
  charge payment gateway successfully
  database commit fails

Attempt 2:
  update database again
  charge payment gateway again
```

The customer could be charged twice.

For side effects requiring reliable delivery, use a **transactional outbox**:

1. Within the same database transaction, write the business mutation, idempotency result, and an outbox event.
2. Commit the transaction.
3. A separate worker reads the outbox and dispatches the message/API call.
4. Mark the event as sent or record delivery status.
5. Downstream consumers use the event ID or idempotency key to deduplicate repeated deliveries.

The outbox guarantees the business change and the intent to emit an event are recorded atomically in the database. Outbound delivery can still repeat; consumers must be idempotent. With payment providers, pass a matching idempotency key if the API supports it.

Do not claim system-wide exactly-once solely because an outbox exists. In practice, it is at-least-once delivery combined with deduplication to achieve effectively-once processing.

## 10. What should NOT be retried

- Validation errors or malformed input data.
- Unauthorized users.
- Business rule rejections such as out of stock, insufficient balance, or closed account.
- Unique violations unrelated to idempotency keys.
- Query syntax, mapping, or schema errors.
- Requests past their deadline or already canceled by the caller.
- Non-idempotent side effects without deduplication mechanisms.

Retrying an error that cannot resolve itself only increases load, adds latency, and obscures the root failure.

## 11. Hand-written retry loop or library?

### Explicit retry loop

A small hand-written loop works well when you need clear control over exceptions, attempt counts, backoff, and transaction boundaries. It is easy to read in a focused use case and adds no extra dependencies.

### Spring Retry

Spring Retry provides `@Retryable`, `@Recover`, and policies. Use it when the application already has the dependency/configuration and wants annotation-driven retries.

You still need to verify:

- Retry advice wraps outside transaction advice so each attempt goes through a new transaction interceptor.
- Methods are invoked through a Spring proxy; self-invocation bypasses retry/transaction advice.
- `@Recover` is not used to pretend a business operation succeeded when every attempt failed.
- Exception classifiers select only truly retryable errors.
- Retry and transaction are not placed on the same proxy in an order that makes multiple attempts share one transaction.

### Resilience4j

Resilience4j Retry fits well when the system already uses Resilience4j modules. You can configure attempt counts, wait intervals, exponential backoff, and exception predicates.

Regardless of the library chosen, the principles remain unchanged: retry facade outside transactions, worker creating a fresh transaction, request carrying an idempotency key, and retrying only transient errors.

## 12. Runnable example with Java 17+, Spring Boot 3.4.5, and H2

The example creates an inventory item. A purchase request carries `requestKey`, `itemId`, and `quantity`. The transactional worker:

1. Inserts the idempotency record with a unique request key.
2. Reads the item with `@Version`.
3. Validates quantity and reduces stock.
4. Stores the remaining quantity into the idempotency record.
5. Commits both changes.

The facade checks whether the request already completed, retries transient errors up to three times, and handles duplicate keys by reading back the committed result.

### Project structure

```text
bounded-retry-idempotency/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/retry/
    │   │   ├── RetryApplication.java
    │   │   ├── InventoryItem.java
    │   │   ├── ProcessedRequest.java
    │   │   ├── InventoryRepository.java
    │   │   ├── ProcessedRequestRepository.java
    │   │   ├── PurchaseCommand.java
    │   │   ├── PurchaseResult.java
    │   │   ├── PurchaseReceipt.java
    │   │   ├── BoundedRetryExecutor.java
    │   │   ├── PurchaseTransactionService.java
    │   │   ├── PurchaseLookupService.java
    │   │   └── PurchaseService.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/retry/BoundedRetryExecutorTest.java
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>bounded-retry-idempotency</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:retrydb;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=10000
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `InventoryItem.java`

```java
package com.example.retry;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import org.hibernate.annotations.Check;

@Entity
@Table(name = "inventory_items")
@Check(constraints = "available >= 0")
public class InventoryItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 60)
    private String sku;

    @Column(nullable = false)
    private int available;

    @Version
    private long version;

    protected InventoryItem() {
    }

    public InventoryItem(String sku, int available) {
        this.sku = sku;
        this.available = available;
    }

    public Long getId() {
        return id;
    }

    public int getAvailable() {
        return available;
    }

    public void decrease(int quantity) {
        if (quantity <= 0 || available < quantity) {
            throw new OutOfStockException("Insufficient stock");
        }
        available -= quantity;
    }
}
```

### `ProcessedRequest.java`

```java
package com.example.retry;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "processed_requests")
public class ProcessedRequest {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "request_key", nullable = false, unique = true, length = 100)
    private String requestKey;

    @Column(nullable = false)
    private Long itemId;

    @Column(nullable = false)
    private int quantity;

    @Column(nullable = false)
    private int remainingAfter;

    protected ProcessedRequest() {
    }

    public ProcessedRequest(String requestKey, Long itemId, int quantity) {
        this.requestKey = requestKey;
        this.itemId = itemId;
        this.quantity = quantity;
    }

    public void complete(int remainingAfter) {
        this.remainingAfter = remainingAfter;
    }

    public String getRequestKey() {
        return requestKey;
    }

    public Long getItemId() {
        return itemId;
    }

    public int getQuantity() {
        return quantity;
    }

    public int getRemainingAfter() {
        return remainingAfter;
    }
}
```

### Repository interfaces

`InventoryRepository.java`:

```java
package com.example.retry;

import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryRepository extends JpaRepository<InventoryItem, Long> {
}
```

`ProcessedRequestRepository.java`:

```java
package com.example.retry;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProcessedRequestRepository extends JpaRepository<ProcessedRequest, Long> {
    Optional<ProcessedRequest> findByRequestKey(String requestKey);
}
```

### Command and result records

`PurchaseCommand.java`:

```java
package com.example.retry;

public record PurchaseCommand(String requestKey, Long itemId, int quantity) {
}
```

`PurchaseResult.java`:

```java
package com.example.retry;

public record PurchaseResult(String requestKey, int remaining) {
}
```

`PurchaseReceipt.java`:

```java
package com.example.retry;

public record PurchaseReceipt(
        String requestKey, Long itemId, int quantity, int remainingAfter) {
}
```

### `BoundedRetryExecutor.java`

```java
package com.example.retry;

import java.util.concurrent.ThreadLocalRandom;
import java.util.function.Supplier;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.stereotype.Component;

@Component
public class BoundedRetryExecutor {
    private final int maxAttempts;
    private final long initialDelayMillis;
    private final long maxDelayMillis;

    public BoundedRetryExecutor() {
        this(3, 20, 250);
    }

    BoundedRetryExecutor(int maxAttempts, long initialDelayMillis, long maxDelayMillis) {
        if (maxAttempts < 1 || initialDelayMillis < 0 || maxDelayMillis < 0
                || maxDelayMillis < initialDelayMillis) {
            throw new IllegalArgumentException("Invalid retry policy");
        }
        this.maxAttempts = maxAttempts;
        this.initialDelayMillis = initialDelayMillis;
        this.maxDelayMillis = maxDelayMillis;
    }

    public <T> T execute(Supplier<T> operation) {
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                return operation.get();
            } catch (TransientDataAccessException failure) {
                if (attempt == maxAttempts) {
                    throw failure;
                }
                sleep(backoffWithJitter(attempt));
            }
        }
        throw new IllegalStateException("Retry loop ended unexpectedly");
    }

    private long backoffWithJitter(int failedAttempt) {
        if (initialDelayMillis == 0 || maxDelayMillis == 0) {
            return 0;
        }

        long base = initialDelayMillis;
        for (int i = 1; i < failedAttempt && base < maxDelayMillis; i++) {
            base = Math.min(maxDelayMillis, base * 2);
        }

        long lowerBound = Math.max(1, base / 2);
        return ThreadLocalRandom.current().nextLong(lowerBound, base + 1);
    }

    private void sleep(long millis) {
        if (millis == 0) {
            return;
        }
        try {
            Thread.sleep(millis);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new RetryInterruptedException("Retry interrupted", interrupted);
        }
    }

    public static class RetryInterruptedException extends RuntimeException {
        public RetryInterruptedException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
```

The executor only catches `TransientDataAccessException`. `DataIntegrityViolationException`, `OutOfStockException`, and `IllegalArgumentException` do not belong to this retry group and propagate immediately.

### `PurchaseTransactionService.java`

```java
package com.example.retry;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseTransactionService {
    private final InventoryRepository inventoryRepository;
    private final ProcessedRequestRepository requestRepository;

    public PurchaseTransactionService(
            InventoryRepository inventoryRepository,
            ProcessedRequestRepository requestRepository) {
        this.inventoryRepository = inventoryRepository;
        this.requestRepository = requestRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public PurchaseResult purchaseOnce(PurchaseCommand command) {
        ProcessedRequest operation = requestRepository.saveAndFlush(
                new ProcessedRequest(
                        command.requestKey(), command.itemId(), command.quantity()));

        InventoryItem item = inventoryRepository.findById(command.itemId())
                .orElseThrow(() -> new ItemNotFoundException(command.itemId()));

        item.decrease(command.quantity());
        inventoryRepository.flush();

        operation.complete(item.getAvailable());
        requestRepository.flush();

        return new PurchaseResult(command.requestKey(), item.getAvailable());
    }

    public static class ItemNotFoundException extends RuntimeException {
        public ItemNotFoundException(Long itemId) {
            super("Inventory item not found: " + itemId);
        }
    }

    public static class OutOfStockException extends RuntimeException {
        public OutOfStockException(String message) {
            super(message);
        }
    }
}
```

`saveAndFlush` claims the idempotency key inside the transaction immediately. `@Version` on `InventoryItem` causes concurrent updates with the same version to raise an optimistic locking conflict. When `flush()` fails, this transaction rolls back; the operation record rolls back along with it.

### `PurchaseLookupService.java`

```java
package com.example.retry;

import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseLookupService {
    private final ProcessedRequestRepository repository;

    public PurchaseLookupService(ProcessedRequestRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true, propagation = Propagation.REQUIRES_NEW)
    public Optional<PurchaseReceipt> find(String requestKey) {
        return repository.findByRequestKey(requestKey)
                .map(row -> new PurchaseReceipt(
                        row.getRequestKey(), row.getItemId(),
                        row.getQuantity(), row.getRemainingAfter()));
    }
}
```

The lookup runs in a fresh read-only transaction. It is called after the failed write transaction has rolled back, so it does not query using a tainted persistence context.

### `PurchaseService.java`

```java
package com.example.retry;

import java.util.Optional;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseService {
    private final PurchaseLookupService lookupService;
    private final PurchaseTransactionService transactionService;
    private final BoundedRetryExecutor retryExecutor;

    public PurchaseService(
            PurchaseLookupService lookupService,
            PurchaseTransactionService transactionService,
            BoundedRetryExecutor retryExecutor) {
        this.lookupService = lookupService;
        this.transactionService = transactionService;
        this.retryExecutor = retryExecutor;
    }

    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public PurchaseResult purchase(PurchaseCommand command) {
        validate(command);

        Optional<PurchaseReceipt> previous = lookupService.find(command.requestKey());
        if (previous.isPresent()) {
            return replayOrReject(command, previous.get());
        }

        try {
            return retryExecutor.execute(
                    () -> transactionService.purchaseOnce(command));
        } catch (DataIntegrityViolationException possibleDuplicateKey) {
            Optional<PurchaseReceipt> committed =
                    lookupService.find(command.requestKey());
            if (committed.isPresent()) {
                return replayOrReject(command, committed.get());
            }
            throw possibleDuplicateKey;
        }
    }

    private PurchaseResult replayOrReject(
            PurchaseCommand command, PurchaseReceipt receipt) {
        boolean samePayload = receipt.itemId().equals(command.itemId())
                && receipt.quantity() == command.quantity();
        if (!samePayload) {
            throw new IdempotencyKeyReuseException(
                    "Request key was already used with a different payload");
        }
        return new PurchaseResult(receipt.requestKey(), receipt.remainingAfter());
    }

    private void validate(PurchaseCommand command) {
        if (command == null || command.requestKey() == null
                || command.requestKey().isBlank() || command.requestKey().length() > 100
                || command.itemId() == null || command.quantity() <= 0) {
            throw new IllegalArgumentException("Invalid purchase command");
        }
    }

    public static class IdempotencyKeyReuseException extends RuntimeException {
        public IdempotencyKeyReuseException(String message) {
            super(message);
        }
    }
}
```

`PurchaseService` holds no transaction during the retry loop. Each call to `purchaseOnce` passes through the `PurchaseTransactionService` bean proxy, receiving a new transaction. When encountering a duplicate key, the service looks up the committed request; if no matching record is found, it rethrows the original error.

### `RetryApplication.java`

```java
package com.example.retry;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class RetryApplication {
    public static void main(String[] args) {
        SpringApplication.run(RetryApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            InventoryRepository inventoryRepository, PurchaseService purchaseService) {
        return args -> {
            InventoryItem item = inventoryRepository.saveAndFlush(
                    new InventoryItem("SKU-1", 5));

            PurchaseCommand firstCommand =
                    new PurchaseCommand("order-1001", item.getId(), 2);

            PurchaseResult first = purchaseService.purchase(firstCommand);
            PurchaseResult replay = purchaseService.purchase(firstCommand);

            System.out.println("First call remaining: " + first.remaining());
            System.out.println("Replay same key remaining: " + replay.remaining());
            System.out.println("Stock after replay: "
                    + inventoryRepository.findById(item.getId()).orElseThrow().getAvailable());

            PurchaseResult secondOrder = purchaseService.purchase(
                    new PurchaseCommand("order-1002", item.getId(), 2));
            System.out.println("Second order remaining: " + secondOrder.remaining());
        };
    }
}
```

### `BoundedRetryExecutorTest.java`

```java
package com.example.retry;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.dao.TransientDataAccessResourceException;

class BoundedRetryExecutorTest {
    @Test
    void retriesTransientFailureButStopsAfterSuccess() {
        BoundedRetryExecutor executor = new BoundedRetryExecutor(3, 0, 0);
        AtomicInteger calls = new AtomicInteger();

        String result = executor.execute(() -> {
            if (calls.incrementAndGet() < 3) {
                throw new TransientDataAccessResourceException("temporary");
            }
            return "done";
        });

        assertThat(result).isEqualTo("done");
        assertThat(calls.get()).isEqualTo(3);
    }

    @Test
    void doesNotRetryBusinessFailure() {
        BoundedRetryExecutor executor = new BoundedRetryExecutor(3, 0, 0);
        AtomicInteger calls = new AtomicInteger();

        assertThatThrownBy(() -> executor.execute(() -> {
            calls.incrementAndGet();
            throw new IllegalArgumentException("invalid request");
        })).isInstanceOf(IllegalArgumentException.class);

        assertThat(calls.get()).isEqualTo(1);
    }

    @Test
    void stopsWhenMaximumAttemptsAreExhausted() {
        BoundedRetryExecutor executor = new BoundedRetryExecutor(3, 0, 0);
        AtomicInteger calls = new AtomicInteger();

        assertThatThrownBy(() -> executor.execute(() -> {
            calls.incrementAndGet();
            throw new TransientDataAccessResourceException("still unavailable");
        })).isInstanceOf(TransientDataAccessResourceException.class);

        assertThat(calls.get()).isEqualTo(3);
    }
}
```

### Running the application and tests

Run the application:

```bash
mvn spring-boot:run
```

Stdout:

```text
First call remaining: 3
Replay same key remaining: 3
Stock after replay: 3
Second order remaining: 1
```

Run the unit tests:

```bash
mvn test
```

The three tests verify that the executor retries transient errors the right number of times, does not retry input errors, and stops when `maxAttempts` is exhausted. The application demo confirms that replaying the same idempotency key does not deduct stock a second time. The executor test snippet does not simulate a real deadlock; concurrency integration tests on the target database remain necessary to verify locking/version behavior.

## 13. Notes for real-world production systems

### Choosing idempotency keys and retention periods

- Keys must be sufficiently unique per tenant/user and operation type.
- Store a payload hash or critical fields to detect key reuse with different content.
- Retain records longer than clients, gateways, or brokers may retry.
- Have an archive/cleanup policy; deleting keys too early can allow stale requests to take effect again.
- Avoid logging full sensitive tokens/keys unnecessarily; log a hash or correlation ID instead.

### Retries must stay within the time budget

Set a deadline for the entire loop, not just individual sleeps. Before each attempt, check remaining time; do not start a new transaction if the request has exceeded its deadline. Configure appropriate JDBC/query/transaction timeouts so a single attempt cannot hang indefinitely.

### Retries do not replace locking or constraints

Retries only react after a conflict is detected. Invariants must still be protected with `@Version`, pessimistic locks, conditional UPDATEs, CHECK/UNIQUE constraints, or appropriate transaction isolation. Without protection mechanisms, retrying might merely repeat a race condition.

### Do not retry half of a business flow

If a use case includes debiting, crediting, and recording a ledger entry, retry the entire transaction as a single unit. Do not retry the credit alone after the debit already committed. If the business flow spans multiple services/databases, use sagas, outboxes, and idempotent consumers per distributed design.

## 14. Testing retries and idempotency

Tests should verify call counts, transaction boundaries, and data state:

1. **Transient failure then success:** transient failures on initial attempts, succeeding later; call count does not exceed policy.
2. **Exhausted attempts:** every attempt fails transiently; final exception is thrown.
3. **Non-retryable error:** validation or business exceptions run only once.
4. **Fresh transaction:** each attempt has a new transaction ID/persistence context; the old transaction rolled back before the next attempt starts.
5. **Same-key replay:** resubmit same key and same payload; result matches and the database reflects only one effect.
6. **Same key, different payload:** request is rejected and leaves data unchanged.
7. **Concurrent requests with same key:** only one operation record commits; the other reads back the result.
8. **Unknown commit outcome:** simulate response failure after commit and verify retry does not duplicate the effect.
9. **Business failure:** out-of-stock or insufficient balance is not retried under transient policies.
10. **Outbox:** transaction rollback leaves no event; transaction commit creates exactly one outbox record; consumer tolerates redelivery.

Do not rely solely on checking mock invocations. Use integration tests with a database to verify unique constraints, `@Version`, rollbacks, and final state.

## 15. Testing on a production-like database

H2 is useful for examples and fast unit/integration tests, but lock modes, deadlocks, isolation, error codes, and exception timing can differ from PostgreSQL, MySQL, SQL Server, or Oracle.

For money, inventory, or booking flows, add Testcontainers or integration environments using the same database engine and major version as production. Verify:

- Actual exception classes on optimistic conflict, deadlock, and lock timeout.
- Whether transaction rollback reverts both the idempotency record and business data.
- Whether the unique constraint arbitrates two concurrent requests sharing a key.
- That lock timeouts and query timeouts do not exceed the retry deadline.
- That retries use backoff/jitter and do not exhaust the connection pool.
- That outbox events are written only when the business logic commits.

## 16. Common mistakes

1. **Unbounded retries:** causes escalating load and hanging requests. Set max attempts and a deadline.
2. **Retrying every exception:** repeats validation, business, or schema errors. Retry only verified transient exceptions.
3. **Retrying inside a failed transaction:** the transaction may be rollback-only. Move the retry loop outside and call a separate transactional worker.
4. **Self-invocation losing the proxy:** split facade and worker into separate beans or use explicit transaction APIs.
5. **Reusing EntityManager after rollback:** the persistence context may be inconsistent. Each attempt uses a fresh transaction/persistence context.
6. **Missing idempotency key:** timeouts after commit can cause request retries to duplicate effects.
7. **Checking key only before insert:** two transactions can still both pass the check. Use a database unique constraint.
8. **Returning old result for same key with different payload:** store payload hash/key fields and reject key reuse conflicts.
9. **Committing idempotency record separately from business logic:** risks recording a request without applying business changes or vice versa. Write in the same transaction.
10. **Catching duplicate key in a failed transaction and continuing to query:** the transaction may be rollback-only. Re-read in a fresh transaction after rollback.
11. **Sending emails/charging payments inside the retry loop:** side effects can repeat. Use an outbox and idempotent downstream handlers.
12. **Not distinguishing business errors from transient errors:** out-of-stock does not resolve via retries.
13. **Backoff without jitter:** many clients retry simultaneously and prolong overload.
14. **Retrying past caller deadline:** the server keeps working after the client timed out. Set an overall time budget.
15. **Testing only with mocks:** fails to verify real locking and unique constraints. Add integration tests on the target database.

## 17. Practical guidelines

- Retry only recoverable transient errors and operations designed to be safe on re-execution.
- Set max attempts, exponential backoff, jitter, and an overall deadline.
- Never retry validation, authorization, business rejections, or schema/query errors.
- Place the retry facade outside transactions; each attempt invokes the transactional worker via a Spring proxy.
- Use `REQUIRES_NEW` or an equivalent transaction boundary so subsequent attempts get a fresh transaction and persistence context.
- Persist idempotency key, payload identity, and result in the same transaction as the business mutation.
- Enforce a unique constraint in the database; same key + same payload returns the old result, same key + different payload must be rejected.
- Handle duplicate keys after rollback using a fresh read transaction.
- Use a transactional outbox for external side effects and idempotent consumers to handle duplicate deliveries.
- Test real exceptions, rollbacks, replays, concurrent duplicates, and production-like databases.

Key takeaway: **Retries are safe only when bounded, targeted at transient errors, and executed with a fresh transaction on every attempt. An idempotency key paired with a unique constraint and an operation record committed atomically alongside business changes ensures resent requests or ambiguous commit outcomes do not create duplicate effects. External side effects require an outbox and safe duplicate handling on the receiving side.**