# Idempotency, Side Effects, and the Risk of Duplicate Writes in Spring Reactive

In Project Reactor and Spring WebFlux, the `retry` or `retryWhen` operator can automatically retry a failing operation. This is useful when the network is flaky or an auxiliary service is temporarily unavailable. However, **retrying a publisher with write side effects is not the same as retrying safely**: the previous request may have actually written the data and merely lost the response. The next attempt can write a second time unless the side-effecting side has an appropriate **idempotency** mechanism.

For example: a service deducts 100,000 VND and the client loses connection before receiving HTTP 200. If the client or `retryWhen` re-sends the command "deduct another 100,000 VND" as a new transaction, the account can be charged twice. Increasing wait times, adding backoff, or limiting to two retries **does not solve the root cause of duplicate writes**. You need to identify *one logical business operation* with a unique key and allow the writing side to recognize resends of the same operation.

This lesson belongs to the **Errors and retry** group in Spring Framework - reactive. Its focus is the relationship between **error signals, resubscription, side effects, idempotency keys, data transactions, and observability**.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Explain accurately what `retry(n)` and `retryWhen(...)` do to a cold publisher source.
- Distinguish **re-executing** a publisher from **replaying** cached values; distinguish retry from repeat and fallback.
- Identify the "**written successfully but response lost**" failure window, a common cause of duplicate writes.
- Distinguish **idempotent operations**, **non-idempotent operations**, **side-effect-free reads**, and **side-effecting writes**.
- Design **stable idempotency keys**, payload-matching rules, UNIQUE/transaction constraints, and returning previously stored results.
- Know when to use `Retry.backoff`, transient error filtering, retry limits, timeouts, and how to avoid harmful retries.
- Write a Java 17+ example with Reactor proving retry causes duplicate writes, and test it with `StepVerifier`.
- Connect these concepts to WebClient, R2DBC, reactive transactions, outbox, and the limits of "exactly once" guarantees.

## 2. Retry in Reactor Means Re-subscribing Upstream

A `Mono<T>` or `Flux<T>` is a publisher. For many cold sources, each downstream `subscribe()` can trigger the work again: an HTTP request, DB query, computation flow, or side effect. **`retry(1)` allows one retry after the first error** (up to two subscriptions total for a sequence of one failure followed by success). It does not "continue from the failure point" in the old subscription; the old subscription already ended with `onError`, and Reactor **re-subscribes upstream**.

~~~text
Subscriber
   |
   v
[retry(1)] -- subscribe #1 --> [cold source] --> WRITE COMMITTED
   ^                                          \
   |                                           \-- ACK lost --> onError
   |
   +-- subscribe #2 --> [cold source] --> WRITE AGAIN --> onNext/complete
~~~

If upstream includes a write operation, **two subscriptions can lead to two writes**. This is protocol-correct: Reactor cannot tell on its own whether an error response came from "write never happened" or "write succeeded but response was lost".

### Distinguishing operators

| Approach | Reacts to which condition? | What to remember about side effects |
| --- | --- | --- |
| `retry(1)` | Upstream emits `onError` | Re-subscribes upstream at most once; can re-execute writes |
| `retryWhen(Retry.max(2))` | Errors matching the Retry policy | Up to two retries after initial attempt; still resubscribes |
| `retryWhen(Retry.backoff(...))` | Retryable errors, spaced waits | Reduces pressure when retrying; **does not prevent duplicate writes on its own** |
| `repeat(n)` | Upstream completes normally | Re-subscribes even when there is no error; can repeat side effects |
| `onErrorResume(fn)` | Upstream errors | Switches to a fallback publisher; does not retry old source by default |
| `timeout(duration)` | No signal within operator semantics limit | Produces timeout error; external operation may still have completed |
| `cache()` | Reuses stored results/signals per configuration | Can avoid repeated subscriptions within one scope, but is **not** durable idempotency across instances/restarts |

With a multi-element `Flux`, retrying after an error on the third element can cause **the first two elements to be re-emitted** on the next subscription. If those earlier elements triggered side effects, those side effects also risk being executed again.

## 3. Exact Definition of Idempotency

An operation `f` is **idempotent** if applying it multiple times has the same state effect as applying it once: `f(f(state)) = f(state)`. In distributed systems, the practical meaning is **re-sending the same logical operation creates no extra unintended business effects**.

Comparison examples:

| Request | When is it idempotent? | Risk when repeated |
| --- | --- | --- |
| "Set order #42 status to PAID" | Can be idempotent in final state if designed not to create extra side effects | Audit events, emails, callbacks may re-fire if uncontrolled |
| "Increment view count by 1" | Not idempotent with ordinary increment | Each retry adds another view |
| "Deduct balance by 100,000" | Not idempotent if every call deducts again | Charges money twice |
| "Create new order" with random ID each time | Not idempotent | Produces two orders |
| "Create order" with same operation ID durably deduplicated | Can achieve once-per-operation-ID effect | Must prevent races, store results, and handle crashes |
| "Save document by ID with same content" | Can be data-idempotent | Triggers, versions, and emitted events may still differ |
| Read account without modifying state | Usually safer to retry | Still creates load, audits, and may return updated data |

**"Idempotent" does not mean "no side effects".** A PUT command can write the same value many times with an unchanged final state, yet triggers, messages, or logs may grow with each call. Guarantees must be defined in terms of the **business effects to protect**: number of transfers, number of order records, number of invoices, or emails actually sent.

In HTTP, methods like GET/HEAD are normally considered safe, while PUT/DELETE carry standard idempotent semantics at the requested-effect level; POST is normally not idempotent by default. **Do not rely on HTTP method alone to conclude a real implementation is safe to retry.** A GET endpoint that mutates data violates expectations; a POST with an idempotency key can still be designed to prevent duplicate writes.

## 4. Three Distinct Milestones: Sending, Executing, and Receiving Response

Follow an invoice-creation command:

~~~text
Client                           Service                         Database
  | POST /invoices key=K            |                                |
  |-------------------------------->|                                |
  |                                 | INSERT invoice(id=777)         |
  |                                 |------------------------------->|
  |                                 | COMMIT succeeded               |
  |                                 |<-------------------------------|
  | X network drop / timeout        |                                |
  |<--- HTTP 201 never received --- |                                |
  |                                 |                                |
  | RETRY same command              |                                |
  |-------------------------------->|                                |
  |                                 | Without dedup: second INSERT   |
  |                                 |------------------------------->|
  |                                 | Duplicate invoice #778         |
~~~

The client only knows "no response received", **not** whether the server committed or not. A client timeout signals that the wait limit expired; it does not prove a rollback. Likewise, client subscription cancellation stops waiting, yet the database or payment provider may still have executed the request.

Three outcomes of the first attempt must be distinguished:

1. **Write never executed:** retry may be necessary to finish the business operation.
2. **Written, success response never received:** blind retry can create duplicates.
3. **In progress, state uncertain:** a concurrent retry can race against the original request.

A safe design must answer all three, even across application crashes or multiple replicas.

## 5. Why Side Effects Inside Operators Also Repeat

A side effect does not have to live inside a repository. It can be an HTTP call, sending an email, publishing a message, incrementing a counter, creating a file, or a callback in `doOnNext`.

~~~java
Flux<Order> stream = orders
    .doOnNext(order -> sendEmail(order))
    .map(this::convert)
    .retry(1);
~~~

This is an illustrative fragment requiring `Order`, `orders`, `sendEmail`, and `convert`. If a step after `doOnNext` reports an error, the entire upstream of `retry` is re-subscribed: **emails for orders that already passed through can be sent again**. `doOnNext` callbacks should be used primarily for observation/logging/metrics with matching semantics; asynchronous side effects should be modeled as publishers with error and idempotency management.

Operator order matters:

~~~java
// Retry wraps the upstream write operation too:
Mono<Result> a = writeOrder()
    .retryWhen(retryPolicy);

// Retry wraps only the read step after writing; write errors still need handling:
Mono<Result> b = writeOrder()
    .flatMap(saved -> readRemoteStatus(saved)
        .retryWhen(retryPolicy));
~~~

These are fragments requiring implementations of `writeOrder`/`readRemoteStatus`/`retryPolicy`. In case b, retrying `readRemoteStatus` does not automatically re-run `writeOrder` once writing succeeded. However, it **does not** make writing safe if `writeOrder` itself is retried elsewhere, or if the client resends the whole HTTP request. Retry placement must be evaluated across client, gateway, controller, service, repository, and job/broker.

**`Mono.just(writeBlocking())` is not a way to manage side effects per subscription.** `writeBlocking()` is called immediately when building the publisher, usually blocks the calling thread, and can obscure re-execution behavior. Use non-blocking APIs, or when blocking integration is unavoidable, put it in `Mono.fromCallable(...)` with an appropriate scheduler; that defers the side effect until subscription, though **it does not make it idempotent on its own**.

## 6. Runnable Java 17+ Example: Retry Causes Duplicate Writes

This demo deliberately simulates a scenario where the first attempt **wrote successfully**, yet the program reports `IOException("ACK_LOST")` before returning the result. Two strategies are compared:

- **Naive:** each new subscription writes again.
- **With idempotency key:** uses the same key to return the first write's result; stored in `ConcurrentHashMap` as an example to demonstrate the principle inside one JVM.

Create a Maven project:

~~~text
reactor-retry-idempotency/
├── pom.xml
├── src/main/java/RetryIdempotencyDemo.java
└── src/test/java/RetryIdempotencyTest.java
~~~

Contents of `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>reactor-retry-idempotency</artifactId>
  <version>1.0-SNAPSHOT</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.6.9</version>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <version>3.6.9</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.10.3</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <version>3.13.0</version>
        <artifactId>maven-compiler-plugin</artifactId>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <version>3.2.5</version>
        <artifactId>maven-surefire-plugin</artifactId>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Contents of `src/main/java/RetryIdempotencyDemo.java`:

~~~java
import java.io.IOException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Mono;

public class RetryIdempotencyDemo {

    private static final AtomicInteger naiveWrites = new AtomicInteger();
    private static final AtomicInteger safeWrites = new AtomicInteger();
    private static final AtomicInteger safeAttempts = new AtomicInteger();
    private static final ConcurrentHashMap<String, String> results =
        new ConcurrentHashMap<>();

    private static Mono<String> unsafeWrite() {
        return Mono.defer(() -> {
            int count = naiveWrites.incrementAndGet(); // already committed
            if (count == 1) {
                return Mono.error(new IOException("ACK_LOST"));
            }
            return Mono.just("ok");
        });
    }

    private static Mono<String> writeWithKey(String key) {
        return Mono.defer(() -> {
            String value = results.computeIfAbsent(key, ignored -> {
                int serial = safeWrites.incrementAndGet(); // write once per key
                return "saved-" + serial;
            });

            int attempt = safeAttempts.incrementAndGet();
            if (attempt == 1) {
                return Mono.error(new IOException("ACK_LOST"));
            }
            return Mono.just(value);
        });
    }

    public static void main(String[] args) {
        System.out.println("naive result: "
            + unsafeWrite().retry(1).block());
        System.out.println("naive writes: " + naiveWrites.get());

        System.out.println("safe result: "
            + writeWithKey("order-42").retry(1).block());
        System.out.println("safe writes: " + safeWrites.get());
        System.out.println("safe attempts: " + safeAttempts.get());
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=RetryIdempotencyDemo
~~~

Exact stdout from the program:

~~~text
naive result: ok
naive writes: 2
safe result: saved-1
safe writes: 1
safe attempts: 2
~~~

Mechanism explanation:

1. `unsafeWrite()` returns a cold `Mono.defer`. On first subscription, `naiveWrites` increments from 0 to 1 before emitting ACK_LOST: simulating **write succeeded then acknowledgment lost**.
2. `retry(1)` re-subscribes; on the second run `naiveWrites` rises to 2. Business-wise, **two writes** occurred even though the client only received `ok` once.
3. `writeWithKey("order-42")` is also subscribed twice. Yet `ConcurrentHashMap.computeIfAbsent` for the same key creates `saved-1` only once in the demo JVM, so `safeWrites=1` while `safeAttempts=2`.
4. The result `safe result: saved-1` proves the idea "**same logical operation → same key → same stored result**".

**Mandatory limitation of this demo:** `ConcurrentHashMap` only lives in one process's memory; data is lost on restart, not shared across replicas, and provides no atomicity with a database or external provider. Therefore **never use this map as a production idempotency mechanism**. Simulating a "commit" here is just incrementing a counter, not a real data transaction.

The example uses `block()` only to print output in the console. In a WebFlux controller or Netty event loop, **return Mono/Flux**; do not wait synchronously.

## 7. Idempotency Key: Identifying a Logical Operation

An **idempotency key** is a stable key bound to **one business intent**. When the same intent is re-sent, the server can recognize it and **not execute the side effect a second time**.

For example, a user clicks "Pay" for order 42:

~~~text
Logical operation: pay order #42, amount 100000 VND
Idempotency-Key: pay-order-42-attempt-group-8d7f...
       |
       +-- HTTP attempt 1 ──> server
       +-- HTTP attempt 2 ──> server (after timeout)
       +-- worker redelivery ─> server (if same logical operation)
       |
       └-- All must converge to the same business effect
~~~

A **genuinely new** operation must have a new key. Do not generate a new key on every retry of the same operation: doing so breaks deduplication. Conversely, do not reuse one key across two different commands.

Design rules:

- **Key scope:** usually `tenantId + operationType + key`; use a single global UUID only if the system contract ensures proper namespacing.
- **Payload fingerprint:** store a hash/canonical representation of significant parameters such as resource, amount, currency, and recipient. Same key with a different payload must be explicitly rejected, **never silently returning the old command's result**.
- **Stable outcome:** once a command succeeds, duplicate requests receive back the stored resource ID, result, or status per contract without creating a new resource.
- **In-flight operations:** concurrent requests arriving with the same key may receive 202, 409, an in-progress status, or wait for the result, depending on design. Never run two identical business executions in parallel.
- **Retention/TTL:** keep keys long enough to cover retry windows, reconnects, redeliveries, and audit requirements. Once expired, an old command may be treated as new, so assess the risk explicitly.
- **Do not use sensitive info as raw keys:** keys should be sufficiently unpredictable random values or protected identifiers; enforce access control by tenant/owner.
- **Do not trust the client alone:** the server can also enforce unique business IDs such as externalOrderId or paymentIntentId to protect business invariants.

A key can be sent via the HTTP header `Idempotency-Key` or a field in the body/message per protocol; the header name does not create idempotency by itself. **The receiving side must enforce** comparison, locking/unique constraints, state persistence, and returning prior results.

## 8. Durable Deduplication with a Database

Production designs commonly use an **idempotent-operation record table** or a **UNIQUE constraint on the business key**. Example PostgreSQL schema:

~~~sql
CREATE TABLE idempotent_operation (
    tenant_id          TEXT NOT NULL,
    operation_type     TEXT NOT NULL,
    idempotency_key    TEXT NOT NULL,
    request_hash       TEXT NOT NULL,
    status             TEXT NOT NULL,
    resource_id        TEXT,
    response_payload   JSONB,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, operation_type, idempotency_key)
);
~~~

This is a **schema sketch**, not a full concurrency handler or production migration. Principles:

1. Receive request, verify authorization, construct/validate operation key and payload hash.
2. Attempt to **claim the key atomically** (e.g., insert with UNIQUE/`ON CONFLICT`, or appropriate row locking). Never do an unlocked "SELECT if missing then INSERT", because two concurrent requests can both read "missing".
3. If the key already exists, verify tenant, operation type, and hash. If the payload differs, report conflict; if status is succeeded, return the stored result; if in progress, apply the in-progress policy; if failed, apply the defined retry rules.
4. Execute business work and store the result in **the same DB transaction when feasible**. Ensure recording the idempotency record and the related data effect share an atomic boundary.
5. Commit, then return the response. If the response is lost, repeated requests follow the path returning the stored result.

### What if two requests carrying the same key arrive simultaneously?

Relying on `if (!exists(key)) { write(); }` is **unsafe** under concurrency: both can observe it does not exist. You need an atomic server-side mechanism, such as a UNIQUE index and a transaction handling contention. With PostgreSQL, you can use `INSERT ... ON CONFLICT DO NOTHING` to claim, yet **you still must decide transaction lifecycle, locking, status, and recovery**; that SQL statement alone does not guarantee every side effect runs once.

### What if a crash occurs after writing data but before updating the key record?

If both writes live inside **one real DB transaction**, they can commit/roll back together. If writes span two different systems (DB + email, DB + payment gateway), a normal DB transaction **does not cover** the external system. In that case, another strategy is needed: provider-side idempotency key, transactional outbox, reconciliation state, or saga/compensation. Never claim "wrapping with `@Transactional`" is enough to protect external calls.

A system achieving **once-per-business-effect** within its protected boundary does not mean every network layer sends each request only once. Retries and redeliveries may still occur; the server must process them as multiple observations of **one operation ID**.

## 9. Reactive Transactions and Transaction Boundaries

Spring supports `ReactiveTransactionManager` and `TransactionalOperator` for reactive data operations with compatible drivers/transaction managers. A transaction can cover DB operations participating in that same transaction; it does not automatically protect HTTP requests sent to another service.

Illustrative snippet inside a service with a reactive repository and transactional operator:

~~~java
Mono<Receipt> createReceipt(CreateCommand cmd, String key) {
    Mono<Receipt> action = repository
        .insertOrReadExistingByOperationKey(key, cmd)
        .flatMap(record -> repository.loadReceipt(record.receiptId()));

    return action.as(transactionalOperator::transactional);
}
~~~

**This is not a standalone Java program**: `Receipt`, `CreateCommand`, repository, and `TransactionalOperator` must be defined. The `insertOrReadExistingByOperationKey` method is a **contract you must implement properly with UNIQUE/transaction/hash**, not a built-in Spring API. A transaction alone without idempotency logic can still **commit two separate transactions** when two retries are both valid.

### Placing retry relative to the transaction boundary

- When `retryWhen` is **outside** the transactionalized publisher, a retry can start a **new transaction**. If the previous one committed and lost its response, there is a risk of writing again without deduplication.
- When retry is placed **inside** the transaction pipeline, depending on the error and transaction state, reusing an already-failed transaction may be invalid. Do not "fix" it by moving operators randomly; ensure the whole transaction can be retried and idempotency is enforced.
- If the source is cancelled because the client disconnects, Spring reactive transactions have rollback semantics for cancellation while the transaction is still open under framework management; however, **cancellation after commit cannot undo an already-committed record**, and a DB transaction does not roll back an independent external call.

Key takeaway: **transactions guarantee atomicity within their managed boundary**, whereas **idempotency handles the same logical request being sent multiple times**. The two mechanisms complement each other.

## 10. WebClient HTTP Client: Conditional Retries

When WebClient calls a status-reading endpoint, retrying transient connection errors may be appropriate. When calling a **transaction-creating POST**, there must be an idempotency contract from the server before enabling automatic retries.

Integration example:

~~~java
Mono<PaymentReceipt> submit(PaymentCommand command, String operationKey) {
    return webClient.post()
        .uri("/payments")
        .header("Idempotency-Key", operationKey)
        .bodyValue(command)
        .retrieve()
        .bodyToMono(PaymentReceipt.class)
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
                .filter(this::isTransient));
}
~~~

This is a **fragment** requiring `webClient`, `PaymentCommand`, `PaymentReceipt`, and `isTransient(Throwable)` from the application. Also requires importing `java.time.Duration` and `reactor.util.retry.Retry`. It is only safe if the `/payments` endpoint **actually deduplicates the same key and payload**, not merely because the header is present.

Explicitly define `isTransient` (such as network errors or HTTP 503 converted by an adapter into an appropriate exception) and exclude errors that should not be retried, such as validation failures, denied permissions, key reuse with different payloads, security errors, or non-idempotent requests. For HTTP 4xx, retry decisions must depend on each status and contract. Never retry infinitely.

`Retry.backoff(2, ...)` means up to **two retries after the initial attempt**, not two requests total. Backoff can include jitter to prevent multiple clients from retrying simultaneously; do not write tests assuming intervals between attempts are always exactly 200 ms.

**Where a timeout is placed also matters:** a per-attempt timeout differs from an overall operation deadline. If each attempt has its own timeout and there are two retries, total time can exceed a single attempt's timeout. Design the time budget from client/gateway to server; when the deadline expires, do not assume the operation rolled back.

## 11. Which Errors Should Be Retried?

| Failure type | What to usually do? | Why |
| --- | --- | --- |
| Transient connection error before outcome is known | Can retry **if the operation is duplicate-safe** | May or may not have been sent; outcome is ambiguous |
| HTTP 502/503/504 from downstream | Bounded retry per policy and idempotency | Could be a gateway error after the server already processed it |
| HTTP 429 (rate limit) | Honor `Retry-After`/quotas and limits | Avoid overloading further |
| 400 Validation | Do not retry the same payload | Bad data will still be bad |
| Unauthorized/Forbidden | Do not retry blindly | Needs auth/permission fix |
| Conflict from same key, different payload | Do not retry the wrong request | Business/contract conflict |
| DB unique violation with duplicate operation ID | Find and return stored result if payload matches; handle race | Do not treat duplicate as "create new again" |
| DB deadlock/serialization failure | Can retry whole transaction conditionally with clear idempotency | Previous transaction may have rolled back, yet scope must be verified |
| Timeout after calling payment/external service | Do not assume unwritten; reconcile/provider idempotency | May have already committed in the external system |

**Do not lump every exception into "transient".** A good retry policy retries only allowed errors, has a max attempt limit, backoff with jitter, an overall deadline, metrics, and circuit breaker/rate limiting when appropriate. Even so, **a retry policy does not replace idempotent design on the receiving side**.

## 12. Outbox and Message Delivery: Side Effects Outside Transactions

A classic flow: create an order in the DB and then publish an `OrderCreated` event. If the DB commit succeeds yet publishing fails, retrying the whole handler can create a second order. If publishing succeeds yet the app crashes before acknowledging, the event may be re-sent upon recovery.

**Transactional outbox** is one approach:

1. Within **one DB transaction**, insert/update the order and insert an outbox event with a unique `eventId` or operation ID.
2. Commit the transaction: business data and the outbox record are persisted together.
3. A worker reads the outbox and publishes to the broker. The worker can retry publishing if it receives no ack.
4. Consumers use the event ID and dedup/unique constraints to avoid repeating side effects when an event is redelivered.
5. Mark outbox entries as processed appropriately and run a cleanup/backlog-monitoring job.

~~~text
HTTP command (operationKey=K)
     |
     v
DB transaction: [Order #42] + [Outbox Event E42]   (single commit)
     |
     v
Outbox publisher --> Broker --> Consumer
                       |            |
                  may redeliver     +-- dedup eventId before side effect
~~~

An outbox does not promise "the network sends exactly one message". It prevents losing notifications between **DB write and outbox write**, while downstream still needs deduplication when delivery is at-least-once. If the consumer sends an email or calls a payment API, the event ID/correlation ID must map to that side effect's idempotency key.

**Difference between idempotency and dedup:** dedup identifies multiple messages as the same operation; idempotent processing ensures repeated execution causes no extra unwanted effects. A "seen message ID" cache marked **before** the side effect that then crashes can cause **lost processing**; marked **after** the side effect that then crashes can cause **duplicate processing**. Make it atomic in the DB or use provider-side idempotency/reconciliation.

## 13. Reactor Retry and Dangerous Side-Effect Placements

### Retrying the whole Flux can re-emit already-succeeded items

~~~java
Flux<Integer> result = Flux.just(1, 2, 3)
    .doOnNext(n -> System.out.println("received " + n))
    .map(n -> {
        if (n == 3) throw new IllegalStateException("boom");
        return n;
    })
    .retry(1);
~~~

If a subscriber requests all data, stdout from `doOnNext` can print `received 1`, `received 2`, `received 3` **twice**, because each new subscription starts over from element 1. If `doOnNext` performs an insert, email, or debit, elements 1 and 2 can be processed twice. The stream still ends with an error after retries are exhausted.

To handle errors **per individual element**, move recovery/retry into that element's inner publisher:

~~~java
Flux<Result> results = orders
    .concatMap(order ->
        processOneIdempotently(order)
            .retryWhen(perItemPolicy)
            .onErrorResume(error -> Mono.just(
                Result.failed(order.id(), error.getClass().getSimpleName()))));
~~~

This fragment requires `Order`, `Result`, `orders`, `processOneIdempotently`, and `perItemPolicy`. This illustrates **retry scope**: only the corresponding item's subscription is retried, yet `processOneIdempotently` must still be designed safely against duplicate execution. For concurrent processing requirements, you can consider bounded `flatMapSequential`; output ordering **does not** guarantee side effects happen sequentially.

### Do not use side effects inside doOnNext instead of composing a publisher

Wrong composition semantics:

~~~java
Mono<Order> result = repository.save(order)
    .doOnNext(saved -> webClient.post()
        .uri("/notify")
        .bodyValue(saved)
        .retrieve()
        .bodyToMono(Void.class));  // creates Mono but never subscribes/composes!
~~~

This is a fragment requiring repository/webClient/Order. The `doOnNext` callback constructs the notify request publisher but **does not wire that publisher into the pipeline**, so the notification may never be sent. Proper composition:

~~~java
Mono<Order> result = repository.save(order)
    .flatMap(saved ->
        sendNotificationWithIdempotency(saved).thenReturn(saved));
~~~

`sendNotificationWithIdempotency` must return a Mono and define its own deduplication mechanism. Even when composed, if the entire chain is retried, both save and notify can still re-run; place retries at the right scope and protect both side effects. You can use an outbox instead of holding an HTTP call inside a transaction when consistency is needed.

## 14. Testing with StepVerifier: Count Effects, Not Just Results

In the Maven project from section 6, create `src/test/java/RetryIdempotencyTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

class RetryIdempotencyTest {

    @Test
    void retryResubscribesAndRepeatsUnsafeSideEffect() {
        AtomicInteger writes = new AtomicInteger();

        Mono<String> source = Mono.defer(() -> {
            int count = writes.incrementAndGet();
            if (count == 1) {
                return Mono.error(new IOException("ack lost"));
            }
            return Mono.just("ok");
        });

        StepVerifier.create(source.retry(1))
            .expectNext("ok")
            .verifyComplete();

        assertEquals(2, writes.get());
    }

    @Test
    void sameKeySuppressesDuplicateEffectInOneProcess() {
        ConcurrentHashMap<String, String> store = new ConcurrentHashMap<>();
        AtomicInteger writes = new AtomicInteger();
        AtomicInteger attempts = new AtomicInteger();

        Mono<String> source = Mono.defer(() -> {
            String result = store.computeIfAbsent("invoice-7", key -> {
                writes.incrementAndGet();
                return "committed";
            });

            if (attempts.incrementAndGet() == 1) {
                return Mono.error(new IOException("ack lost"));
            }
            return Mono.just(result);
        });

        StepVerifier.create(source.retry(1))
            .expectNext("committed")
            .verifyComplete();

        assertEquals(2, attempts.get());
        assertEquals(1, writes.get());
    }

    @Test
    void doNotRetryBusinessValidationFailures() {
        AtomicInteger attempts = new AtomicInteger();

        Mono<String> source = Mono.defer(() -> {
            attempts.incrementAndGet();
            return Mono.error(new IllegalArgumentException("invalid"));
        });

        StepVerifier.create(
                source.retryWhen(
                    Retry.max(2).filter(IOException.class::isInstance)))
            .expectError(IllegalArgumentException.class)
            .verify();

        assertEquals(1, attempts.get());
    }
}
~~~

Run:

~~~bash
mvn -q test
~~~

When all three tests pass, Maven returns exit code 0; depending on `-q`, detailed result lines may not be printed. These tests focus on **how many times the side effect actually executed**:

- The first test shows the source is subscribed twice and the "write" counter increments twice.
- The second test proves the same key inside one JVM produces only one effect despite two attempts; do not treat an in-memory map as a production mechanism.
- The third test proves the filter in `Retry.max(2)` does not retry `IllegalArgumentException`, so business-invalid requests are not repeated.

With a real database, add **integration tests for concurrency and crashes**: two requests with the same key arriving concurrently; same key with different payload; server dying before/after commit; lost response; retries from multiple instances; duplicate messages from a broker; expired TTL. Unit tests mocking repositories do not prove real-world data atomicity.

### Testing without timing flakiness

Backoff with jitter varies retry timing. Unit tests should verify **attempt counts, retryable error types, results, and number of business effects**; when timing logic must be tested, use virtual time and do not assert exact wall-clock scheduler timestamps. Avoid `Thread.sleep` to "wait for retries" in reactive tests.

## 15. Four Different Safety Levels

**Level 1 — No retry:** sends only once. Duplicates can still come from client double-clicks, gateways, brokers, or user resends. "There is no `retry` in this source code" is not enough to prove duplicate writes never happen.

**Level 2 — Retry with error filtering/backoff:** reduces transient failures and prevents spam. Yet if the operation is not idempotent, duplicate writes can still occur.

**Level 3 — Single-process key memory:** a cache/ConcurrentHashMap or in-memory state can prevent duplicates within a narrow scope. It does not survive restarts, scaling, or eviction, and gives no guarantee for external side effects.

**Level 4 — Durable idempotent business operation:** clearly scoped key, payload hash, unique constraint/locking, transaction and outcome state, in-progress/crash handling policy, TTL, reconciliation; external systems integrated via provider keys or outbox/dedup as appropriate. This is the right level for critical write operations.

Do not claim "end-to-end exactly once" when independent systems do not share a transaction. The practical goal is **at-least-once delivery with dedup/idempotency so only one business effect occurs within the defined protection boundary**.

## 16. Observability and Reconciliation

Metrics to measure:

- **Logical operations:** count of newly created operation keys that succeeded.
- **Attempts:** total request attempts, separating initial attempts from retries.
- **Duplicate detected:** count of requests where the key already existed and the stored result was returned.
- **Conflicts:** count of same key with a different payload hash.
- **In-progress collisions:** count of duplicate-key requests arriving while work is still in flight.
- **Outcome:** committed, rejected, failed, unknown/reconciling.
- **Retry causes:** timeout, connection, 5xx, rate limit, DB transient error.
- **Outbox:** backlog, oldest event age, publish retries, consumer-side dedup.
- **End-to-end effect:** actual payment/order records created vs. valid operation keys.

Use correlation IDs to link logs of the same logical operation across attempts. Never use attempt count as the count of "new orders", and avoid logging raw tokens, payment details, or sensitive payloads. If operation IDs have high cardinality, do not put raw IDs as metric labels; use logs/tracing for per-ID lookup and metrics aggregated by status.

A scenario needing **reconciliation**: the provider already charged the payment, yet the service never recorded status DONE. If you only read local status and retry without checking externally, you can create a second payment. Query status by provider operation ID or resend the **same provider-supported idempotency key**, and settle the outcome status per the actual contract.

## 17. Common Implementation Mistakes

1. **Enabling `retry(3)` on a money-writing POST without an idempotency key.** Can produce four executions of the side effect.
2. **Generating a new key on every attempt.** The receiver treats each attempt as a distinct operation.
3. **Checking "already exists?" first and then doing INSERT.** Two concurrent requests can both pass the check; unique constraints/atomic claims are needed.
4. **Using Redis/in-memory markers without an atomic rule with the side effect.** Marker and effect can diverge on crash.
5. **Treating an HTTP timeout as proof nothing was written.** The response may have been lost after commit.
6. **Putting `doOnNext` to send emails and then retrying the whole Flux.** Already-processed items can re-send.
7. **Retrying every exception, including 400/validation/auth.** Repeating requests cannot succeed when input/permissions have not changed.
8. **Using backoff and believing it prevents duplicates.** Backoff only changes retry timing.
9. **Not binding keys to payloads.** Clients can reuse a key for a different request, causing wrong results or security flaws.
10. **Storing key results without handling IN_PROGRESS state.** Two concurrent requests can race to write.
11. **Marking DONE before the external effect completes.** A crash after the marker can lose the effect.
12. **Marking DONE after the external effect without a provider key.** A crash before the marker can cause retries to repeat the effect.
13. **Assuming a DB transaction covers email/payment gateways.** Only resources participating in the transaction are protected.
14. **Ignoring retention.** Keys expiring before the redelivery window can unintentionally create new operations.
15. **Forgetting retries in other layers.** Client libraries, load balancers, gateways, scheduled jobs, and broker consumers can all resend.
16. **Using `collectList().block()` in a WebFlux handler.** Blocks the event loop, increases latency, and complicates cancellation.
17. **Never testing two same-key requests concurrently.** Sequential demos do not prove race-condition protection.
18. **Confusing result order with effect order.** `flatMapSequential` keeps downstream emission order, not DB write execution order.
19. **Using `cache()` to prevent system-wide duplicate transactions.** Cache lives per publisher/process with its own lifecycle policy.
20. **Having no way to reconcile uncertain states.** When an ack is lost, reconcile instead of retrying blindly.

## 18. Scenario Exercises

**Exercise 1.** How many times can `Mono.defer(this::saveOrder).retry(2)` call `saveOrder` when the first two attempts emit eligible errors?  
**Answer:** Up to three subscriptions/calls if errors keep qualifying: one initial attempt and two retries. If each write committed before failing, there can be three side effects.

**Exercise 2.** A client's order-creation POST hits an HTTP timeout. Can you conclude the server did not create the order?  
**Answer:** No. Timeout means not receiving a result in time, not proof of rollback. You need a key and stored-result lookup/replay.

**Exercise 3.** Why must the same idempotency key be paired with payload matching?  
**Answer:** To prevent a key from being reused for a different amount/resource where the server returns the wrong result or drops the new operation. Valid duplicates must be distinguished from key conflicts.

**Exercise 4.** Two requests with the same key arrive concurrently. Is "SELECT first, then INSERT if absent" enough?  
**Answer:** No. You need a UNIQUE constraint/atomic claim and a transaction/locking policy to prevent races.

**Exercise 5.** A DB transaction writes an order and then sends an external email. Does rolling back the transaction automatically delete the sent email?  
**Answer:** No. Email is outside the DB transaction; outbox/idempotency and proper error-handling strategies are required.

**Exercise 6.** Does `Retry.backoff(3, Duration.ofMillis(100))` prevent duplicate writes?  
**Answer:** No. It slows down and caps at three retries, yet still re-subscribes the write source.

**Exercise 7.** A publisher emitted items 1 and 2 with side effects, errored on item 3, and retried the whole Flux. Can items 1 and 2 be processed again?  
**Answer:** Yes, if the cold source re-emits from the beginning. To avoid this, design per-item/operation idempotency or place retries inside an appropriate per-item processing branch.

**Exercise 8.** A transaction ID was processed on replica A. After A restarts, replica B receives the request again. Can an in-memory map protect it?  
**Answer:** No. Durable/shared state with unique constraints and scoped atomic execution is needed.

**Exercise 9.** An outbox message was published, yet the worker crashed before marking it sent. What happens?  
**Answer:** It may be published again. Consumers need deduplication by event ID or idempotent processing.

**Exercise 10.** A request creates a "new" payment command with the same amount and user as an old command. Should the old key be reused?  
**Answer:** No if it is a **different business intent**. Keys must bind to logical operations, not simply a hash of amount + user.

**Exercise 11.** In WebFlux, is calling `subscribe()` to "make sure the DB write runs" and then returning `Mono.just("ok")` safe?  
**Answer:** No. It detaches the write task from the response's lifecycle, outcome, and errors. Return the composed publisher for WebFlux to manage, paired with proper idempotency/transactions.

**Exercise 12.** You use `retryWhen` with a filter retrying only `IOException`; what happens if a validation error occurs?  
**Answer:** The validation error is emitted downstream per policy with no retry; that is the desired behavior for invalid payloads.

## 19. Deployment Checklist for Retried Write Operations

Before deploying or enabling automatic retries, answer:

- **What is the logical operation?** Order, payment, transfer, email, or which record write?
- **Who generates the key and when?** Does the key survive all attempts, gateway retries, and broker redeliveries?
- **What is the key's scope?** Tenant, operation type, resource, API version?
- **How is same key with different payload handled?**
- **Who owns the side effects?** DB repository, external service, broker, gateway, or multiple places?
- **Are durable anti-race constraints in place?** Proper UNIQUE/transactions/locking?
- **Are previous outcomes and in-progress states stored?**
- **If a crash occurs between two systems, is there reconciliation/outbox/provider idempotency?**
- **Which errors are truly transient?** Are there retry limits, jitter/backoff, and an overall deadline?
- **Where does retry sit in the Reactor chain?** Could it accidentally wrap already-committed writes?
- **Which items can a Flux retry re-emit?**
- **Were concurrent same-key requests, lost ACK after commit, restarts, duplicate deliveries, and key conflicts tested?**
- **Do metrics separate attempt counts from logical operation counts?**
- **Is the key TTL long enough for retry windows, reconciliation, and business requirements?**

**Core principle:** `retry`/`retryWhen` only manages **the retry mechanism on error**. Idempotency must be engineered at **the side-effect execution boundary**, using stable operation IDs and proper durable protection. Even if the client receives a single response, the system may have received multiple attempts; the goal is for those multiple attempts to still produce **one business effect per contract**.

### References

- Project Reactor, [Reactor Reference – Error Handling and Retrying](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- Project Reactor, [Retry API](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html).
- Spring Framework, [Programmatic Transaction Management – TransactionalOperator](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html).
- Spring Framework, [Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html).
- MDN, [HTTP Idempotency-Key header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Idempotency-Key).
- [Reactive Streams Specification](https://www.reactive-streams.org/).
