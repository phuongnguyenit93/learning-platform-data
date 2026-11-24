# Testing Idempotency and Behavior Under Repeated Operations

## 1. Business Problem: A Request May Be Sent Multiple Times

In a Spring Boot application, a user clicks “Place Order” twice; a mobile app retries a request on flaky Wi-Fi; a message broker redelivers the same message; a scheduler reruns after a process restart; or a client misses the HTTP response even though the server already finished processing. These scenarios can produce **multiple invocations for the exact same business intent**.

If creating orders, deducting inventory, charging cards, or publishing events executes blindly a second time, the system risks duplicate records, double stock deduction, double charges, or duplicate notifications. A **business unit test** therefore must clarify: when the same operation arrives a second time, what result must the service return and which side effects are permitted?

In this lesson, *idempotency* refers to repeatability without causing further state or outcome changes beyond the contract. The goal is not simply invoking a service twice and seeing neither call throw; you must **measure final state, returned outcomes, and side-effect invocation counts**.

Example expectations:

```text
Call 1: PlaceOrder(tenant=A, key=k-01, sku=BOOK, qty=2)
  -> creates order-42; deducts stock twice? NO, deducts 2 units once
  -> response {orderId: "order-42", status: "CREATED"}

Call 2: same tenant, same key, same request
  -> does not create a new order, does not deduct stock again
  -> returns same order-42 result (or contract-equivalent response)

Call 3: same tenant and key, but qty=3
  -> reports idempotency key conflict; creates/writes no further data
```

**Scope:** defining the contract and testing business logic with Java 17+, JUnit Jupiter, and Mockito; later sections identify guarantees unit tests cannot provide alone and where integration tests with a real database/gateway are required.

## 2. Proper Definition: Outcomes and Side Effects Do Not Multiply

For an operation $C$ acting on state $S$, the core idea of idempotency is:

\[
C(C(S)) = C(S)
\]

In practice, you must also define **which inputs count as the same operation**. A command “increment stock by 1” is not inherently idempotent; however, “apply event ID e-123 at most once to increment stock by 1” becomes idempotent when the system tracks processed event IDs.

| Operation | Is retrying the same intent naturally idempotent? | What to verify |
| --- | --- | --- |
| `setStatus("PAID")` when already PAID | Potentially, if no duplicate side effects emit | Status stays PAID and events fire only per contract |
| `incrementBalance(100)` | No | Safe retries require a command/ledger ID |
| `createOrder(request)` | Not by default | Same key → one order; different key → new intent |
| `charge(card, amount)` | Not by default | One payment command → never double-charge |
| `DELETE /items/{id}` | Considered HTTP idempotent in **intended effect** | Resource remains absent across calls; status codes may differ |
| `PUT /items/{id}` with identical representation | HTTP idempotent as state replacement | Resource ends in target state; audit logging may have its own documented effect |
| `POST /orders` | Not idempotent by default | API may add an idempotency key and dedup rules |

For HTTP, an idempotent operation **does not have to** return the identical status code every time. For example, a first DELETE may return `204` while a second returns `404`, yet the resource remains deleted. If an API **explicitly guarantees** replaying the identical response per idempotency key, tests must verify that exact contract rather than inferring “byte-for-byte identical response” from HTTP semantics alone.

A complete operation typically has three observable layers:

1. **State invariant:** objects/ledgers/databases receive no additional mutations after initial processing.
2. **Side-effect invariant:** payment gateways, message publishers, email senders, or repository writes are not invoked redundantly beyond allowed scope.
3. **Response contract:** repeated calls return the recorded result, appropriate status, or a conflict error if the key is reused with a different payload.

Unit tests should select invariants observable directly within the class boundary. Mockito call-count verification is particularly valuable when dependency invocation counts are part of the contract.

## 3. “Repeated Calls” Happen for Distinct Reasons

Often conflated scenarios:

- **Double click:** user fires two requests close together; potentially concurrently on two threads or instances.
- **Timeout retry:** client does not know whether the first request succeeded or failed; it may already have committed before the socket dropped.
- **At-least-once delivery:** consumer receives the same event/message ID again; brokers do not guarantee single delivery.
- **Batch replay:** a job restarts and re-reads items already processed.
- **User genuinely submits a new command:** identical payload with a **different key**; must not be treated as a duplicate when the domain permits multiple similar orders.
- **Old key with changed payload:** client reused a key improperly; must detect conflict rather than returning a response belonging to a different request.

Four facts to align on before writing tests:

**Command identity:** is it determined by `idempotencyKey`/message ID, a unique-constrained business key, or domain state? Matching SKU and quantity **is not enough** to infer two orders are the same command.

**Key scope:** `(tenantId, key)`, `(userId, key)`, `(merchantId, key)`, or another scope. Identical key strings from two tenants are not automatically the same command.

**Payload equivalence check:** compare canonical payloads/fingerprints of business-significant fields. Exclude irrelevant headers or request timestamps from the fingerprint, while never omitting amount, currency, recipient, SKU, or quantity.

**Retention period:** how long is replay guaranteed? Once a key expires, requests after TTL may count as new commands per contract. Time-based unit tests should inject `Clock`, never `Thread.sleep`.

## 4. Establish the Contract Before Mocking

Suppose a service accepts:

```text
placeOrder(tenantId, requestId, OrderRequest(sku, quantity))
```

Sample contract:

1. Reject blank `tenantId`, `requestId`, SKU, or non-positive quantity **before** calling the writer.
2. For an unseen `(tenantId, requestId)`: execute order creation once and store the successful outcome.
3. Same tenant, key, and payload: return the prior successful result; never create a second order.
4. Same tenant and key, different payload: reject with a conflict exception; never write again.
5. Different key: treat as a distinct request, even with an identical payload.
6. Same key string under a different tenant: do not share dedup records.
7. If the first attempt **definitely failed before committing side effects**, a subsequent attempt may retry.
8. If an error occurs **after side effects committed yet before saving the idempotency record**, a simple in-memory test **cannot guarantee** duplicate prevention; durable design at the storage/gateway layer is required.

Never write tests backwards from existing code details and treat them as the contract: first establish what the product expects on retries, especially errors, TTL, and scope.

### Scenario matrix to cover

| Scenario | Expected outcome | New side effect? |
| --- | --- | --- |
| New key, valid payload | Creates initial result | Once |
| Same key and payload after success | Replays result | No |
| Same key with changed quantity/amount | Conflict | No |
| New key with identical payload | New intent per sample contract | Once for new intent |
| Same key under different tenant | Independent command | Once for new tenant |
| Invalid input | Validation error | No |
| Failure before commit then retry | Retry can succeed | Only the successful creation |
| Two concurrent calls with same key | One logical result | No double creation; synchronization must be tested |
| Committed yet response lost | Replay result on retry | Needs durable storage; mock unit test insufficient |
| Expired key | Per published retention policy | May be treated as new command |

## 5. Runnable Java 17+ Project: JUnit Jupiter and Mockito

The following example tests **an in-memory service** accepting an idempotency key. It runs standalone without a Spring context so failures point squarely to business logic rather than framework configuration.

Structure:

```text
idempotency-unit-demo/
├── settings.gradle
├── build.gradle
└── src/test/java/com/example/testing/
    └── IdempotentOrderServiceTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'idempotency-unit-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'org.mockito:mockito-junit-jupiter:5.15.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

These versions form a **concrete illustrative set**, not a claim of being the latest releases. Real Spring Boot projects should let Boot's BOM manage testing dependencies, typically via `spring-boot-starter-test`.

### Modeling approach

- `OrderRequest` is the business payload; Java 17 `record` gives `equals/hashCode` across all components.
- `ScopedKey(tenantId, requestId)` identifies a command within a tenant.
- `OrderWriter` represents **an order-creation port**. In unit tests it is a Mockito mock; in real integration it can be a transactional/repository service.
- `Stored` saves **the processed payload and returned result** to catch invalid key reuse.
- `ConcurrentHashMap.computeIfAbsent` ensures the same key executes the mapping function once upon successful completion within **a single JVM**, even under concurrent calls.
- When the mapping function throws, no entry is stored; a subsequent call can invoke the writer again.

This is a **model for unit testing**, not a multi-instance production idempotency engine. Specifically, **never place slow HTTP/DB calls inside `computeIfAbsent` in production and assume you have achieved exactly-once**: map callbacks run during table updates, may hold locks/degrade throughput, and do not protect across crashes or multiple JVMs.

## 6. Complete Example: Repeated Commands Still Write Only Once

Create `src/test/java/com/example/testing/IdempotentOrderServiceTest.java`:

```java
package com.example.testing;

import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class IdempotentOrderServiceTest {

    record OrderRequest(String sku, int quantity) {
    }

    record OrderReceipt(String orderId, String sku, int quantity) {
    }

    record ScopedKey(String tenantId, String requestId) {
    }

    record Stored(OrderRequest request, OrderReceipt receipt) {
    }

    interface OrderWriter {
        OrderReceipt create(String tenantId, OrderRequest request);
    }

    static final class KeyConflictException extends RuntimeException {
        KeyConflictException() {
            super("idempotency key reused with another payload");
        }
    }

    static final class IdempotentOrderService {
        private final OrderWriter writer;
        private final ConcurrentMap<ScopedKey, Stored> completed =
                new ConcurrentHashMap<>();

        IdempotentOrderService(OrderWriter writer) {
            this.writer = Objects.requireNonNull(writer);
        }

        OrderReceipt place(
                String tenantId,
                String requestId,
                OrderRequest request) {

            if (tenantId == null || tenantId.isBlank()
                    || requestId == null || requestId.isBlank()
                    || request == null || request.sku() == null
                    || request.sku().isBlank()
                    || request.quantity() <= 0) {
                throw new IllegalArgumentException("invalid order");
            }

            ScopedKey key = new ScopedKey(tenantId, requestId);

            Stored stored = completed.computeIfAbsent(
                    key,
                    ignored -> new Stored(
                            request,
                            Objects.requireNonNull(
                                    writer.create(tenantId, request)))
            );

            if (!stored.request().equals(request)) {
                throw new KeyConflictException();
            }

            return stored.receipt();
        }
    }

    private static final OrderRequest REQUEST =
            new OrderRequest("BOOK", 2);

    private static final OrderReceipt RECEIPT_1 =
            new OrderReceipt("order-42", "BOOK", 2);

    @Mock
    OrderWriter writer;

    private IdempotentOrderService service;

    @BeforeEach
    void setUp() {
        service = new IdempotentOrderService(writer);
    }

    @Test
    void sameKeyAndPayloadReplayFirstSuccess() {
        when(writer.create("tenant-a", REQUEST))
                .thenReturn(RECEIPT_1);

        OrderReceipt first =
                service.place("tenant-a", "req-1", REQUEST);
        OrderReceipt replay =
                service.place("tenant-a", "req-1", REQUEST);

        assertEquals(RECEIPT_1, first);
        assertEquals(first, replay);
        verify(writer, times(1)).create("tenant-a", REQUEST);
    }

    @Test
    void sameKeyWithDifferentPayloadIsRejected() {
        when(writer.create("tenant-a", REQUEST))
                .thenReturn(RECEIPT_1);

        service.place("tenant-a", "req-1", REQUEST);

        OrderRequest changed = new OrderRequest("BOOK", 3);

        assertThrows(
                KeyConflictException.class,
                () -> service.place("tenant-a", "req-1", changed)
        );

        verify(writer, times(1)).create("tenant-a", REQUEST);
        verify(writer, never()).create("tenant-a", changed);
    }

    @Test
    void differentKeysAreDifferentBusinessCommands() {
        OrderReceipt second =
                new OrderReceipt("order-43", "BOOK", 2);

        when(writer.create("tenant-a", REQUEST))
                .thenReturn(RECEIPT_1, second);

        OrderReceipt first =
                service.place("tenant-a", "req-1", REQUEST);
        OrderReceipt next =
                service.place("tenant-a", "req-2", REQUEST);

        assertNotEquals(first.orderId(), next.orderId());
        verify(writer, times(2)).create("tenant-a", REQUEST);
    }

    @Test
    void keyIsScopedPerTenant() {
        OrderReceipt tenantBReceipt =
                new OrderReceipt("order-99", "BOOK", 2);

        when(writer.create("tenant-a", REQUEST))
                .thenReturn(RECEIPT_1);
        when(writer.create("tenant-b", REQUEST))
                .thenReturn(tenantBReceipt);

        OrderReceipt a =
                service.place("tenant-a", "same-key", REQUEST);
        OrderReceipt b =
                service.place("tenant-b", "same-key", REQUEST);

        assertNotEquals(a.orderId(), b.orderId());
        verify(writer).create("tenant-a", REQUEST);
        verify(writer).create("tenant-b", REQUEST);
    }

    @Test
    void invalidRequestHasNoSideEffects() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.place(
                        "tenant-a", "req-1", new OrderRequest("BOOK", 0))
        );
        assertThrows(
                IllegalArgumentException.class,
                () -> service.place(
                        "tenant-a", " ", REQUEST)
        );

        verifyNoInteractions(writer);
    }

    @Test
    void failureBeforeCommitAllowsRetry() {
        when(writer.create("tenant-a", REQUEST))
                .thenThrow(new IllegalStateException("before commit"))
                .thenReturn(RECEIPT_1);

        assertThrows(
                IllegalStateException.class,
                () -> service.place("tenant-a", "req-1", REQUEST)
        );

        OrderReceipt recovered =
                service.place("tenant-a", "req-1", REQUEST);
        OrderReceipt replay =
                service.place("tenant-a", "req-1", REQUEST);

        assertEquals(RECEIPT_1, recovered);
        assertEquals(recovered, replay);
        verify(writer, times(2)).create("tenant-a", REQUEST);
    }

    @Test
    void simultaneousCallsForSameKeyProduceOneWrite()
            throws Exception {
        when(writer.create("tenant-a", REQUEST))
                .thenReturn(RECEIPT_1);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<OrderReceipt> call = () -> {
            start.await();
            return service.place("tenant-a", "req-1", REQUEST);
        };

        try {
            Future<OrderReceipt> first = pool.submit(call);
            Future<OrderReceipt> second = pool.submit(call);
            start.countDown();

            assertEquals(RECEIPT_1, first.get(10, TimeUnit.SECONDS));
            assertEquals(RECEIPT_1, second.get(10, TimeUnit.SECONDS));
            verify(writer, times(1)).create("tenant-a", REQUEST);
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

Run with Gradle Wrapper (if the project includes a Wrapper):

```bash
./gradlew test --tests 'com.example.testing.IdempotentOrderServiceTest'
```

On Windows use:

```powershell
.\gradlew.bat test --tests "com.example.testing.IdempotentOrderServiceTest"
```

If using a pre-installed Gradle binary, replace `./gradlew` with `gradle`. **Expected result: 7 test methods PASS** provided the environment resolves and runs dependencies. Tests produce no fixed stdout; Gradle's default report can be viewed at `build/reports/tests/test/index.html`. The example uses neither a Spring context nor a database.

### 6.1. Verifying replay and exactly once

In `sameKeyAndPayloadReplayFirstSuccess`, we actually call `place(...)` **twice** with the same key and payload. Two assertions:

```java
assertEquals(RECEIPT_1, first);
assertEquals(first, replay);
```

verify the business result. Then:

```java
verify(writer, times(1)).create("tenant-a", REQUEST);
```

verifies the writer was invoked only once. Asserting only the result without measuring side effects lets a service create two orders while coincidentally returning the same receipt. Asserting only call counts without the result lets a service return the wrong receipt. **Both are required** when the contract covers both output and write count.

### 6.2. Verifying same key with different payload

`sameKeyWithDifferentPayloadIsRejected` confirms a second request cannot “overwrite” an already-used key. `record OrderRequest` compares both SKU and quantity; changing quantity from 2 to 3 yields a distinct payload. The test requires `KeyConflictException`, plus:

```java
verify(writer, never()).create("tenant-a", changed);
```

to prove no extra order is created from the altered payload. In an HTTP API, this domain error might map to `409 Conflict` per endpoint contract. Choosing an HTTP status belongs to the API layer and is not inherently proven by service unit tests.

### 6.3. Distinguishing duplicates from a new command

Two calls with identical payloads **are still two distinct orders** when their request keys differ, provided the domain defines the key as command identity. `differentKeysAreDifferentBusinessCommands` requires two writer calls and distinct orderIds. Never blindly use a payload hash as the sole key everywhere; doing so can wrongly collapse two intentional identical orders.

### 6.4. Tenant scoping

`keyIsScopedPerTenant` checks that `same-key` in `tenant-a` does not affect `tenant-b`. In multi-tenant systems, forgetting to scope keys risks leaking another customer's order result. A dedup key should include tenant/user/merchant scope per security and data design.

### 6.5. Invalid data causes zero side effects

`invalidRequestHasNoSideEffects` checks both a blank request ID and quantity 0, then uses `verifyNoInteractions(writer)`. This protects **validate before mutating**; throwing the right exception after already writing to a DB is still a bug.

### 6.6. Retry after failure before commit

In `failureBeforeCommitAllowsRetry`, the mock simulates a first attempt that **definitely never committed** and threw, while the second attempt succeeds. `computeIfAbsent` stores no entry if the lambda throws, allowing the same key to be retried. The expectation is **two write attempts**, with only the second succeeding under the simulated assumption.

If the first attempt had actually created the order before losing its response/ack, this in-memory model would not be safe: the writer created a side effect that the service failed to remember. Never conclude from this test that every timeout can be safely retried.

### 6.7. Concurrent calls for the same key

`simultaneousCallsForSameKeyProduceOneWrite` releases two tasks using `CountDownLatch` and awaits both `Future` results. It verifies both callers get the same receipt and the mock writer is called once on **that single service instance**.

A single execution may not hit production thread interleavings; this is a **unit test with parallel execution**, not mathematical proof that all races are eliminated. Multi-instance or durable systems require integration/concurrency tests checking unique constraints and transaction boundaries.

## 7. Testing Domain-State-Based Idempotency

Not every operation relies on an idempotency key. Some behaviors are expressed directly through **state transitions**:

```text
Shipment: CREATED --ship()--> SHIPPED
Shipment: SHIPPED --ship()--> SHIPPED
```

If business rules allow repeated “mark as shipped” calls, the second call must preserve `SHIPPED`, never decrement stock again, and never emit duplicate domain events. Tests should be named clearly, such as:

- `shipChangesCreatedToShipped`: initial transition changes state.
- `shipAgainPreservesShippedState`: second call stays SHIPPED.
- `shipAgainDoesNotPublishSecondEvent`: publisher receives no extra call.
- `shipFromCancelledIsRejected`: transition from an invalid state is rejected without emitting events.

Pseudo-code illustrating the idea:

```java
if (shipment.status() == Status.SHIPPED) {
    return; // Perform no extra transition or side effect.
}
shipment.markShipped();
events.publishShipmentShipped(shipment.id());
```

This is an **illustrative snippet** requiring full domain classes and infrastructure to run. It conveys repeated transitions, though the **state update followed by publish** order shown is unsafe if the publisher throws: the state moved to SHIPPED while the event might remain unpublished. For production, consider recording events in a **transactional outbox** within the state-changing transaction, with a worker publishing and idempotent consumers handling duplicates.

A command like “deduct 2 items from inventory” does not become idempotent simply by sitting inside an `if` state check; you must track **which order/command** already applied that deduction, especially under concurrent orders.

## 8. Unit Tests Alone Cannot Guarantee Exactly-Once in Distributed Systems

The example uses `ConcurrentHashMap` to hold state purely in memory. Three scenarios break in-memory protection:

1. **Restarts:** when the JVM dies, the map vanishes; an old request retried after restart can create a duplicate order.
2. **Horizontal scaling:** two instances hold two separate maps; the same key hitting both instances can create two orders.
3. **Crash between side effect and recording result:** the writer completes the order/charge yet crashes before saving the mapping; the retry creates another.

Common failure sequence:

```text
Client                 Service A               Database/Payment
  |  POST req-1           |                         |
  |---------------------->|                         |
  |                       | create/charge            |
  |                       |------------------------>|
  |                       |           COMMIT OK     |
  |                       |<------------------------|
  |      TCP timeout      X (crash before saving result)
  |       ...                                       |
  |  POST req-1 retry     | Service B               |
  |---------------------->|                         |
  |                       | In-memory key missing    |
  |                       | 2nd create/charge       |
  |                       |------------------------>|
```

**End-to-end “exactly once” is a demanding contract:** the system must avoid not just calling code twice, but ensure **a single net business effect** across transactional and external boundaries susceptible to partial failures. For payments, leverage the payment provider's idempotency key/contract where available; for messaging, use unique keys, inbox/outbox tables, or state ledgers.

### Common durable persistence pattern

An illustrative command-tracking table:

```sql
CREATE TABLE idempotency_records (
    tenant_id       VARCHAR(100) NOT NULL,
    request_key     VARCHAR(200) NOT NULL,
    request_hash    VARCHAR(128) NOT NULL,
    status          VARCHAR(20) NOT NULL,
    response_body   TEXT,
    created_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, request_key)
);
```

Persistence-layer workflow:

1. Canonicalize the payload and hash business-significant fields.
2. Inside a transaction or proper synchronization mechanism, attempt to insert **a record with the unique key**.
3. If the key already exists, compare hashes: differing payload → conflict; matching payload and completed → return stored response.
4. If currently processing, define behavior explicitly: wait, return in-progress/accepted, or retry-after; never execute concurrently.
5. Persist business mutations and idempotency results within consistency-preserving transaction boundaries.
6. When emitting events outside DB transactions, consider same-transaction outbox and idempotent consumers.
7. Define retention, cleanup, and expiration policies for keys.

This is an **architectural outline**, not production-ready code: locking, isolation levels, hashing, unique-violation handling, recovery from `IN_PROGRESS`, retention periods, and retries must be tailored to your database and domain. In particular, never call a remote HTTP payment inside a DB transaction and assume a DB rollback undoes the payment provider's charge.

### Processing states worth distinguishing

```text
NEW -> IN_PROGRESS -> SUCCEEDED
                  \-> FAILED_RETRYABLE
                  \-> FAILED_FINAL
```

Not all failures allow the same retry policy. Validation errors are terminal and must cause zero side effects; network timeouts to a gateway may represent an **unknown outcome**, requiring a status query or retrying with the same provider idempotency key rather than charging under a brand-new key.

For `FAILED_RETRYABLE`, reprocess only when evidence confirms no prior duplicate effect occurred or the provider/storage enforces deduplication.

## 9. Layered Test Strategy: Unit, Integration, API

| Test level | Question to prove | Tools and approach |
| --- | --- | --- |
| Service unit test | Does replaying the same key return the same receipt and call writer once? | JUnit Jupiter + Mockito; `verify(times(1))` |
| Validation unit test | Do bad payloads or key mismatches block side effects? | `assertThrows` + `verifyNoInteractions` / `never()` |
| State-machine unit test | Do repeated transitions preserve state and skip duplicate events? | Real domain objects + mock event publisher |
| Clock/TTL unit test | Do valid vs expired keys behave properly? | Inject `Clock.fixed(...)`/fake clock; no sleep |
| Repository integration | Do unique keys and transactions block duplicate inserts? | Spring Boot Test + Testcontainers real DB |
| API slice | Are idempotency-key headers, statuses, and bodies right? | `@WebMvcTest` + MockMvc + mock service |
| HTTP integration | Are duplicate requests and timeouts/retries handled end-to-end? | `@SpringBootTest`, HTTP client, real DB |
| Distributed / fault injection | Do crashes or two instances after commit duplicate work? | Integration/system tests with persistence and fault injection |

A **passing unit test** proves object logic given stubbed collaborator behavior. It does not prove database transactions, message brokers, or remote providers behave properly. Yet unit tests remain invaluable: when invariants are clear, they catch duplicate-execution logic bugs before expensive integration tests run.

## 10. Designing Additional High-Value Test Cases

### 10.1. Replay same key without assuming object identity

In `sameKeyAndPayloadReplayFirstSuccess`, `assertEquals(first, replay)` compares record values. Do not use `assertSame(first, replay)` unless **returning the identical Java object instance** is explicitly the contract; in real APIs, responses are serialized/deserialized into fresh objects so object identity is meaningless.

### 10.2. New command with identical payload

Never enforce “two identical payloads must produce one order” if the domain lets a user place two orders for the same SKU/quantity at different times. Testing distinct keys prevents overly broad dedup logic.

### 10.3. Retrying after commit failure or lost acknowledgement

Unit tests can simulate a gateway returning “unknown outcome”, yet cannot prove external commits across process boundaries. Write integration tests with durable keys and stateful mock/fake providers, observing behavior across restarts/instances. Key assertions: business record count and requests actually accepted by the provider.

### 10.4. Message consumer receiving duplicates

A contract might state that calling `handle(Event(id="evt-7"))` twice updates a projection only once. Use the event ID as an inbox key with a unique constraint, and assert projection totals do not increase further. Never rely on how many times a broker calls a listener as a business metric: brokers **may** legitimately redeliver.

### 10.5. Concurrent requests with different keys

Two requests with distinct keys may still contend for the same scarce resource (e.g., two orders buying the last remaining item in stock). **Idempotency keys do not prevent overselling** across distinct commands. Enforce independent locking/optimistic versioning/inventory constraints, and test concurrency at the repository/transaction layer.

### 10.6. Permitted side effects on replay

Systems may write access logs, increment a “duplicate_request” metric, or update `lastSeenAt` on every replay. Permitted side effects do not mean a new order was created. In Mockito tests, verify the **critical business-mutating collaborator** runs once, rather than slapping `verifyNoMoreInteractions` on loggers/metrics allowed to repeat.

### 10.7. Caching initial failure outcomes

Many APIs persist and replay terminal failure results (such as business rejections), while transient pre-commit errors remain retryable. This is a domain/API decision: define explicitly **which failures are cached**, which release the key, and how unknown outcomes recover. The sample code in section 6 caches **successes only**.

## 11. Common Pitfalls When Writing Idempotency Tests

**Asserting only HTTP 200/201.**  
Two successful responses do not prove two orders were not created. Verify orderId, record counts, and side effects.

**Retrying after resetting the service object.**  
Creating a fresh service instance between calls wipes the in-memory `Map`. While useful to **demonstrate limitations** after restarts, it is wrong when testing replay within the same instance. For durable idempotency, test across fresh service instances sharing a real repository.

**Using `verify(times(1))` on one mock and claiming the whole system is exactly-once.**  
Mocks observe only calls on that mock object; they know nothing of DB commits, provider charges, or other consumers. Keep claims bounded to test scope.

**Using payload hashes as the sole command identity.**  
Two independent orders with identical payloads would wrongly merge. Use fingerprints **to verify payload consistency for an existing key**, not as an automatic replacement for keys.

**Skipping payload comparison when replaying an old key.**  
Clients can accidentally reuse a key for a different amount. Silently returning the stale receipt causes incorrect transactions. Tests must catch conflicts and halt further mutations.

**Omitting tenant or user scope on keys.**  
Two customers generating common keys like `request-1` can read each other's responses if dedup storage is global. Test multi-tenant scoping.

**Assuming retries are safe because `@Retryable` is enabled.**  
Retry mechanisms merely coordinate **re-calling** after exceptions; they do not turn non-idempotent commands into idempotent ones. Implement dedup or ensure dependencies receive the same idempotency key on retry.

**Using `atLeastOnce()` when the contract is exactly once.**  
`verify(writer, atLeastOnce()).create(...)` still PASSES if the writer ran twice. When duplicate side effects are forbidden, use `times(1)` or assert aggregate state appropriately.

**Depending on callback ordering or thread scheduling.**  
Race tests relying on `Thread.sleep(50)` flake easily. Coordinate with latches/barriers, and still verify DB unique constraints/transactions in integration tests.

**Believing `ConcurrentHashMap.computeIfAbsent` protects across processes.**  
The map lives inside a single JVM; across restarts or horizontal scaling, there is no shared dedup. Moreover, remote side effects inside a mapping function are not rolled back by an exception.

**Ignoring the crash window.**  
Happy paths pass, yet a server crashing after charging and before saving the receipt triggers a second charge. Payment systems therefore need provider-level idempotency and transaction/reconciliation flows.

**Forgetting TTL/retention.**  
Unbounded keys bloat storage indefinitely; keys expiring too soon trigger unintended replays. Test retention policies with a fake clock and check post-expiration behavior.

## 12. Design and Verification Checklist

Before finalizing a service needing safe retries, answer:

1. How is “same operation” defined by **which key**? Is the key scoped by tenant/merchant/user?
2. Which payload fields must match when reusing a key? Which fields may vary without altering business intent?
3. How identical must replays be: same orderId, same domain state, same response body, or just the same intended effect?
4. Which side effects must happen strictly once: order creation, inventory mutation, payment charge, events, emails?
5. Are invalid inputs and payload conflicts rejected **before** touching dependencies?
6. How are “definitely not committed” errors distinguished from “unknown commit status” errors?
7. If two threads/JVMs receive the same key, which unique constraint or transaction arbitrates?
8. Do dedup records survive server restarts?
9. When publishing messages, are transactional outbox and idempotent consumers present where needed?
10. When may idempotency records be purged? What does a replay mean after TTL?
11. Do unit tests measure both **state/outcomes and side-effect counts**?
12. Have integration tests verified the real database/provider and at least one key concurrency/failure scenario?

## 13. Hands-On Exercise and Self-Grading

Using `IdempotentOrderServiceTest`:

1. Remove `completed.computeIfAbsent` and call `writer.create(...)` directly. Rerun: replay tests FAIL because the writer is called twice, and duplicate conflicts are unhandled.
2. Change the key from `ScopedKey(tenantId, requestId)` to `requestId` alone. `keyIsScopedPerTenant` exposes that two tenants with the same key collide.
3. Remove the `stored.request().equals(request)` comparison. Reusing a key with a different quantity FAILS because the service returns the stale receipt instead of a conflict.
4. Change the test to `verify(writer, atLeastOnce()).create(...)` and deliberately invoke the writer twice: why is the test weaker? Restore `times(1)`.
5. Escalate “failed before commit” to “writer created the order then threw timeout”. Explain why an in-memory service may call the writer again despite the same key and why Mockito stubbing alone cannot fix this.
6. Design a DB unique-key table + transaction for a two-instance system; write an integration test firing two same-key requests and verify exactly **one** order record exists.

Items 1–4 can be observed directly in unit tests. Items 5–6 require understanding real persistence boundaries and crash windows; never claim unit tests already cover them.

### References

- [JUnit Jupiter User Guide](https://docs.junit.org/5.11.4/user-guide/) — organizing unit tests and assertions.
- [Mockito documentation](https://site.mockito.org/) — `verify`, `times`, `never`, strict stubbing.
- [Spring Boot testing reference](https://docs.spring.io/spring-boot/3.3/reference/testing/) — Spring Boot Test, test slices, and integration tests.
- [RFC 9110 — HTTP Semantics, idempotent methods](https://www.rfc-editor.org/rfc/rfc9110.html) — distinguishing idempotency of intended effect from HTTP responses.
- [Testcontainers Java](https://java.testcontainers.org/) — real databases/services for integration testing.

## 14. Conclusion

An idempotent operation must be verified under **the same business intent invoked repeatedly**: state undergoes no additional mutation, critical side effects do not duplicate, and responses/conflicts adhere to the contract. Unit tests with JUnit and Mockito protect replay paths, validation, key scoping, payload mismatches, and writer invocation counts very effectively. Nevertheless, recognize unit test boundaries: durable idempotency across timeouts, crashes, and multiple instances demands persisted records, unique constraints, transactions, outboxes, or provider-side idempotency verified by corresponding integration tests.