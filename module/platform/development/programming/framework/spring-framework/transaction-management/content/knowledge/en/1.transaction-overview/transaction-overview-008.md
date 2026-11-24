# Transaction Guarantees Not Automatically Provided for Remote Calls

> **Context:** Spring Framework — transaction management, Overview section. In this lesson, a "remote call" means HTTP/REST, gRPC, or any call to another service over the network. A called service may also use Spring and its own database, but that does not mean both services participate in the same transaction.

## 1. The core problem

`@Transactional` manages transactions for **resources that actually participate in the transaction manager** on the current application side. For example, with `JpaTransactionManager`, JPA operations on the managed data source can commit or roll back together. However, an HTTP request sent to a payment, inventory, or third-party service **does not automatically become an operation capable of rolling back with that JPA transaction**.

Consider an order creation flow:

1. Service A writes the order to database A.
2. Service A makes an HTTP call to service B to charge payment.
3. Service B records the payment transaction in database B or calls a payment provider.
4. Service A encounters an error and rolls back database A's transaction.

The outcome can be **A has no order while B has recorded a payment charge**. Spring cannot automatically recall a completed HTTP call or roll back B's database simply because A's transaction was aborted.

Key distinction to maintain:

- **Local transaction:** a commit/rollback boundary over resources coordinated by the transaction manager.
- **Remote call:** network communication with its own response, timeouts, and processing state on the receiving side.
- **Distributed business workflow:** a sequence of effects across multiple systems; requires explicit guarantees for consistency, deduplication, recovery, and compensation.

`@Transactional` is not a distributed transaction protocol; both services using `@Transactional` does not create a shared transaction between them.

## 2. What exactly does Spring guarantee?

In the common imperative programming model, Spring uses `PlatformTransactionManager` and binds the transaction to the current thread's execution context. Calls passing through a Spring proxy with `@Transactional` can open, join, commit, or roll back a transaction as configured. JDBC/JPA operations using the matching data source and transaction manager can join that transaction.

That guarantee is **conditional and scoped**:

| Capability | When can it be expected? | Limitations to remember |
| --- | --- | --- |
| Atomicity of database A commands | Commands participate in the same database A transaction | Excludes HTTP requests and database B |
| Rollback when code throws an error | Transaction is active and rollback rules match | Defaults to rollback on `RuntimeException`/`Error`; checked exceptions do not roll back by default |
| Isolation/locking | Database supports the isolation level, locks, and transaction is properly configured | Does not lock or isolate records in service B |
| Transaction timeout | Transaction manager/resource enforces timeout | Does not mean B canceled its effect; HTTP timeout is a separate mechanism |
| Propagation such as `REQUIRED`, `REQUIRES_NEW` | Across transaction-managed calls within the same application/context | Does not propagate transactions over REST/gRPC |
| Successful commit at A | Database A accepts commit | Does not prove B finished, executed once, or will always be available |

A common Spring detail: under default proxy mode, calling a `@Transactional` method from another method **in the same instance** bypasses the proxy, so the annotation on the self-invoked method may have no effect. This is an additional note about **local boundaries**; even when proxies work perfectly, they still do not extend atomicity across HTTP.

Reactive transactions use `ReactiveTransactionManager` and Reactor context instead of the usual thread-bound mechanism. That technical difference likewise **does not turn an ordinary network call into a transaction participant**.

## 3. False expectation example: "if it rolls back, the payment disappears too"

The following example is an **illustrative excerpt**, assuming `OrderRepository` and `PaymentClient` are defined in a Spring project. This is not a standalone Java file:

```java
@Service
class CheckoutService {
    private final OrderRepository orders;
    private final PaymentClient payments;

    CheckoutService(OrderRepository orders, PaymentClient payments) {
        this.orders = orders;
        this.payments = payments;
    }

    @Transactional
    public void checkout(UUID orderId) {
        orders.markPending(orderId);      // Writes to database A
        payments.charge(orderId);         // HTTP to service B
        throw new IllegalStateException("Failure after charging payment");
    }
}
```

If `payments.charge(...)` was already processed successfully by B, the exception at the end of the method rolls back database A's transaction per default rules. **The payment charge at B can still exist.** Spring throwing an exception and returning HTTP 500 to A's caller does not mean B rolled back.

Reordering does not create atomicity either:

- **Call B before committing A:** B may complete, then A's commit fails.
- **Commit A then call B:** A may complete, then the process crashes, the network drops, or B rejects before B's effect occurs.
- **Call B and wait for the response inside A's transaction:** A's transaction holds connections/locks longer while still having no control over B's transaction.

No simple reordering of two independent operations eliminates all gaps between them.

## 4. Failure modes that must be distinguished

| Scenario | What does A know for sure? | What may have happened at B? | How to handle |
| --- | --- | --- | --- |
| B returns an error before executing per API contract | Request failed per received response | No effect if the contract genuinely guarantees that | Classify errors per contract; do not blindly retry every status code |
| A times out waiting for B | A **does not know** the outcome | B never received it, is processing, or already committed | Query status by stable ID; safely retry with an idempotency key |
| B finished executing but response was lost | A sees timeout/network error | Effect already occurred | Deduplicate and reconcile; avoid sending a brand-new mutation command |
| A rolls back after B returned success | A rolled back locally | B may have committed | Compensate/reconcile per business logic; rolling back A is not enough |
| A commits then crashes before sending request | A persisted locally | B never received it | Durable outbox or another durable work-queue mechanism |
| B receives duplicates due to retry/redelivery | Request may have been delivered multiple times | Risk of double charging / double inventory deduction | Deduplicate on B using a unique constraint and B's transaction |
| B completes slowly or callbacks arrive out of order | A has temporary observed state | Stale outcomes may arrive after newer ones | State machine, version/sequence, idempotent handling |

**Timeout does not equal "B did nothing"; retry does not equal "first attempt."** Even HTTP 200 or 202 only carries meaning according to the **API contract**: 200 may report the operation completed, while 202 typically indicates accepted for further processing. Never infer commit timing or durability from status codes alone.

Specifically, if A calls a payment API and receives `SocketTimeoutException`, never automatically conclude the charge failed and issue a new request with a fresh transaction ID. Keep the original request key to query status or retry idempotently.

## 5. Why is each service's ACID not enough for the whole chain?

- **Atomicity:** A and B can each be atomic individually, yet lack shared atomicity without participating in a distributed commit protocol.
- **Consistency:** A's local data constraints cannot inspect or enforce business invariants spanning A–B. For instance, "do not confirm an order without payment" must be modeled via state and application rules.
- **Isolation:** DB A's isolation does not isolate work running in B from other users. B's effects can become visible before A commits.
- **Durability:** after B commits, rolling back A does not erase B's persisted data.

Transaction guarantees are contracts of each participating resource. Do not deduce "the whole workflow is ACID" because every service uses Spring Data/JPA or every handler has `@Transactional`.

Even making remote calls inside an open transaction increases operational risk: holding DB connections and locks while waiting on the network raises contention, cascading timeouts, and connection pool exhaustion risks. Therefore, in standard designs, **avoid holding a local transaction open while waiting on slow or unpredictable network calls**.

## 6. Choosing guarantees based on business requirements

Before selecting a technique, write down the invariants to uphold. For example:

- "Each valid payment request records **at most one financial effect**."
- "Do not transition an order to `PAID` without proof of successful payment."
- "Every `PENDING_PAYMENT` order must eventually resolve or enter a state requiring attention."
- "Canceling a charged order must create a trackable refund, even if the refund finishes later."

These four statements require **idempotency**, **state transition rules**, **retry/monitoring mechanisms**, and **compensation** respectively. A single transaction annotation does not do all of that.

Separate clearly:

1. **Local transaction outcome:** committed, rolled back, or unknown due to a crash.
2. **Remote request status:** not sent, sent, accepted, executed, terminal failure, or unknown.
3. **Overall business status:** `PENDING`, `PROCESSING`, `COMPLETED`, `COMPENSATING`, `FAILED`, etc. depending on the domain.

Client timeouts should transition to **UNKNOWN/PENDING_RECONCILIATION** when there is no proof of terminal failure; never default to marking them "failed."

## 7. Transactional Outbox: persisting the intent to send in the same local transaction

**The dual-write problem:** saving an order in database A while also publishing an event/calling B involves two operations on two systems. If A commits and the process dies before publishing, the event is lost; if publishing happens before commit and A rolls back, B receives an event for a non-existent state.

**Transactional Outbox** shifts where responsibility is stored:

```text
Single local transaction at A:
    INSERT/UPDATE orders
    INSERT outbox_event (event_id, aggregate_id, type, payload, status)
    COMMIT

Post-commit (independent process):
    Poll/CDC reads committed outbox_event
    Sends event or request to B
    Once validly acknowledged, marks as delivered
    Transient failure -> retry with the same event_id
```

The order and the outbox record reside in the **same database and same transaction**, so either both commit or both roll back. The relay can crash after B processes the message but before marking the outbox row as sent; thus **outbox typically provides at-least-once delivery, not guaranteed exactly-once processing at B**. B must still deduplicate.

Illustrative **Spring Boot 3.x / Java 17+** excerpt showing only where to place the transaction boundary; assumes entities and Spring Data repositories are declared in the application:

```java
@Service
class OrderApplicationService {
    private final OrderJpaRepository orders;
    private final OutboxJpaRepository outbox;

    OrderApplicationService(OrderJpaRepository orders,
                            OutboxJpaRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public UUID createOrder(UUID customerId, long amountMinorUnits) {
        UUID orderId = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();

        orders.save(new OrderEntity(
                orderId, customerId, amountMinorUnits, "PENDING_PAYMENT"));
        outbox.save(new OutboxEntity(
                eventId, orderId, "PaymentRequested", amountMinorUnits));

        return orderId; // Both records commit together or roll back together
    }
}
```

`OrderEntity`, `OutboxEntity`, and both repositories in the example are application-defined types, **not built-in Spring APIs**. Monetary amounts should use the smallest currency unit (e.g., cents) or `BigDecimal` with explicit scale and rounding rules, rather than `double`.

A production outbox should store a unique `event_id`, `aggregate_id`, `event_type`/schema version, payload, creation timestamp, delivery status, attempt count, next retry timestamp, and error details. The relay needs a safe claim/lease strategy when running multiple instances so two workers do not pick up the same unlocked row and emit uncontrollably. On databases that support it, `FOR UPDATE SKIP LOCKED` or reliable CDC/connectors can be used. Poison-message/dead-letter handling and alerts for stale unpublished events are also needed.

### On ordering and state transitions

If a single order emits multiple events, use a monotonically increasing per-aggregate version/sequence so the receiver detects stale or out-of-order events. Never assume multiple consumers, partitions, and retries always preserve order. Also note: outbox solves **atomicity between A's data and the intent to send**; it does not make B part of the local transaction.

## 8. Idempotency and Inbox: preventing duplicate effects on the receiving side

**Idempotency** means applying the same business request multiple times yields the **same business effect** as applying it once. It is especially vital when A does not know whether B processed the request.

An HTTP contract may specify:

```http
POST /payments
Idempotency-Key: 7cb0c613-76a1-491d-a747-5ae194b4f52f
Content-Type: application/json

{"orderId":"9fd3e0e4-9fb7-467b-8396-1eeab0b98f14","amountMinorUnits":125000}
```

At B, the `Idempotency-Key` belongs to **one logical operation**, never generating a fresh key per retry. B must persist the key and outcome durably and enforce a unique constraint, such as on `(client_id, idempotency_key)`. If a repeated request has the **same key but a different payload**, return a conflict error per contract. If the same key and valid payload already completed, return the stored response without charging again.

Implementation principles:

- Deduplication/condition checking and mutating database B must be coordinated **atomically** using a transaction and unique constraint; doing "SELECT to check if key exists" followed by "INSERT" is insufficient when two requests arrive concurrently.
- Persist `IN_PROGRESS`/`SUCCEEDED`/`FAILED_FINAL` status as needed. A second request seeing `IN_PROGRESS` must receive an in-progress response, wait/poll, or retry later; never silently execute again.
- Choose key retention longer than the maximum possible retry/redelivery window per system contract. Expiring too early can turn an old request into a brand-new execution.
- If B in turn calls a third service, B must also forward an appropriate idempotency key to the downstream side-effecting step if that API supports it. A unique key inside B's database alone **cannot prevent** duplicates at an external provider if B crashes between calling the provider and recording the result.
- For event consumers, the **Inbox/Processed Messages** pattern stores a unique `(consumer_id, event_id)` in the **same transaction as the business update**. Redelivery will not apply the effect twice.

```sql
-- PostgreSQL, illustrating the core constraint:
CREATE TABLE processed_messages (
    consumer_id text NOT NULL,
    event_id uuid NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_id, event_id)
);
```

After claiming the event successfully inside B's transaction, update business data and commit; if the transaction rolls back, both the processed marker and business changes roll back too. On a unique constraint conflict, identify it as an already-processed event and skip applying side effects again. For external HTTP requests with side effects outside B's transaction, add durable state tracking and separate reconciliation.

**"Exactly once" is a claim that must always be scoped.** A broker may provide exactly-once processing semantics **within the boundary it controls**, without guaranteeing that a payment request to an external system executes exactly once. The practical goal is typically **at-least-once delivery + idempotent processing + reconciliation**, yielding a business effect equivalent to once.

## 9. Saga and compensation when workflows span multiple services

For workflows made of multiple steps with separate transactions, a **Saga** defines the local transactions and semantically meaningful compensating actions:

```text
Create PENDING order at A
    -> Reserve stock at Inventory
    -> Charge payment at Payment
    -> Confirm order at A

If payment fails terminally:
    -> Release stock reservation
    -> Mark order PAYMENT_FAILED

If payment succeeded but a later step fails:
    -> Request refund (a new transaction)
    -> Track refund until terminal state
```

Coordination can use **orchestration** (one coordinator holds state and issues commands) or **choreography** (services react to events). Both require correlation IDs, idempotent commands/events, timeouts, retries, durable state, and handling when compensation itself fails.

**Compensation is not a cross-system database rollback.** A refund can create a separate transaction, incur fees, be rejected, or settle late; others may observe intermediate states. A Saga also **does not provide global isolation**: concurrent behavior, reservations, versioning, and valid state transitions must be managed explicitly.

**TCC (Try–Confirm–Cancel)** fits when services support reserving/confirming/canceling resources with explicit contracts. TCC requires API design and time-bounded resource holds, not something generated automatically by `@Transactional`.

## 10. When to use distributed transactions / XA / 2PC?

A distributed transaction with **two-phase commit (2PC)** can coordinate multiple protocol-capable resources, typically via XA/JTA and `JtaTransactionManager` in compatible environments. However, **every involved participant** must be able to enlist/prepare/commit with the same coordinator. An ordinary HTTP API or third-party payment service is **not naturally an XA resource**.

2PC adds complexity, coordination overhead, and the risk of participants holding locks while waiting. Nor does it unconditionally solve every failure mode, compensation policy, or external action. Consider it only when strict atomicity is mandatory, all resources genuinely support it, and the team can operate coordinator recovery. For HTTP-communicating microservices, outbox, idempotency, state machines, and Sagas are usually more practical.

Do not mistake configuring `@Transactional(transactionManager = "...")` or `Propagation.REQUIRES_NEW` for having 2PC. `REQUIRES_NEW` merely creates **an independent local transaction** within the scope of that transaction manager.

## 11. What does `@TransactionalEventListener(AFTER_COMMIT)` help with, and what does it lack?

Spring provides a listener that can run according to transaction phases:

```java
@Component
class OrderNotificationListener {
    private final PaymentClient payments;

    OrderNotificationListener(PaymentClient payments) {
        this.payments = payments;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void onOrderPlaced(OrderPlaced event) {
        payments.requestPayment(event.orderId());
    }
}
```

This is also an **integration excerpt**, assuming `PaymentClient` and the `OrderPlaced` record are defined by the application.

Running the listener after commit **avoids sending a request for an A transaction that rolled back**. However, a gap remains: if the process crashes after A commits and before/during listener dispatch, the in-memory event can be lost, and there is no durable retry by default. Thus, the listener **does not replace transactional outbox** when "once committed, it must eventually be sent" is required.

Additionally, during `AFTER_COMMIT`/`AFTER_COMPLETION` phases, transaction resources may still be accessible yet the original transaction has already ended; new DB writes must not be assumed to auto-commit. When DB writes are needed inside a post-commit callback, use a genuinely new transaction (e.g., a proxied method with `REQUIRES_NEW`), or place durable recording in the initial transaction as with an outbox.

## 12. Synchronous design when direct calls are unavoidable

Not every workflow needs a queue. If B must be called synchronously for an immediate decision:

1. Verify whether B offers an **idempotent request** contract and a status-lookup endpoint keyed by business request ID. If not, design reconciliation before enabling automatic retries for side effects.
2. Keep the HTTP call outside DB A's transaction if possible; open only short transactions to record verified outcomes. Never claim that splitting them creates cross-system atomicity.
3. Configure sensible connect and response timeouts, bounded retries with exponential backoff and jitter, and only for retryable errors. Consider rate limits, circuit breakers, and bulkheads to prevent cascading failures.
4. Put unknown outcomes into `PENDING_RECONCILIATION`; poll B's status using the request ID, handle authenticated callbacks if available, and provide a manual resolution path if still unverified.
5. Enforce valid state transition order using version/optimistic locking or conditional updates. Stale callbacks must never overwrite newer outcomes.
6. Return "completed" only when the business condition is genuinely satisfied. When async processing is needed, return a contract-appropriate status (e.g., HTTP 202 with a status URL/ID) and provide a tracking mechanism.

A well-designed workflow **never confuses successful sending with a successful business effect**.

## 13. Mandatory test scenarios

| Intentionally injected failure | Observation to verify |
| --- | --- |
| A rolls back after B has already processed | B's effect does not vanish; system detects and compensates/reconciles properly |
| B succeeds but response is dropped | A retries with the **same idempotency key**; B does not repeat the side effect |
| Stop process A right after committing order + outbox | Relay still picks up the event after restart |
| Stop relay after B receives but before marking sent | Event may be resent; B safely deduplicates |
| Two A/relay workers process the same event concurrently | Claim/lease/unique constraint prevents corrupt updates or duplicate effects |
| Two concurrent requests with the same idempotency key | Unique constraint at B establishes one unique logical operation |
| B fails for an extended period, then recovers | Backoff/retries, pending status, alerts, and eventual completion |
| Out-of-order, delayed, or duplicate event/callback | State machine/version never regresses state |
| Compensation fails | Status and retry/escalation schedule remain tracked; request is never "lost" |
| Transaction encounters a checked exception | Rollback rules are configured and proven as expected |

In real integration tests, use a test database and a mock HTTP server or simulated service B environment; inject faults **at the boundaries between commit, send, receive, and acknowledgment**. Happy-path-only integration tests miss critical gaps. With real payment providers, avoid triggering real financial transactions when testing failures; use sandboxes or stub adapters.

Metrics to monitor: age of unpublished outbox events, retry counts, dead-letter message counts, commands in unknown state, idempotency-key collision rate, number of active compensating sagas, and latency from local commit to business completion. Correlation IDs/request IDs are needed across logs and traces, but **correlation IDs for tracing differ from idempotency keys for deduplication** unless intentionally designed together.

## 14. Common misconceptions

| Claim | Reality |
| --- | --- |
| "With `@Transactional`, every step in the method rolls back." | Only resources participating in the transaction are coordinated; HTTP side effects do not auto-rollback. |
| "A and B both use Spring, so they share a transaction." | Each service has its own transaction manager/transaction unless an actual distributed transaction protocol is designed. |
| "HTTP timeout means B did not charge." | Outcome is **unknown**; B may have completed while the response was lost. |
| "Retries are guaranteed to finish safely." | Retries can cause duplicate side effects if B is not idempotent. |
| "Sending events in `AFTER_COMMIT` can never lose events." | The process can crash before sending; an outbox is needed for durable publishing. |
| "Outbox guarantees system-wide exactly-once." | Outbox guarantees saving the send intent atomically with A's data; the relay can still deliver duplicates. |
| "Saga rollback is like ACID." | Sagas use separate transactions and compensations, have intermediate states, and may require intervention. |
| "`REQUIRES_NEW` propagates the transaction to service B." | It is a propagation rule on the local Spring transaction manager, not a network protocol. |

## 15. Checklist for remote calls with side effects

- [ ] Clearly map database/transaction manager boundaries and services outside the transaction.
- [ ] Write down business invariants: what must never happen, and what may become eventually consistent.
- [ ] Assign a unique request/event ID **and preserve it across retries**; specify key/payload/version semantics.
- [ ] Define success, terminal failure, and unknown outcomes; provide a lookup endpoint or reconciliation.
- [ ] Protect side effects with unique constraints and deduplication logic right on the executing side.
- [ ] When reliable publishing after A's commit is required, save an outbox record in the same local transaction.
- [ ] Implement relay/retry/claim/monitoring and handle duplicates, out-of-order delivery, and poison messages.
- [ ] For multi-step chains, model Saga/TCC with a state machine and idempotent compensations.
- [ ] Keep DB transactions short; avoid holding locks while waiting on network calls whenever possible.
- [ ] Test timeouts after success, crashes at handoff points, concurrent retries, and compensation failures.

**Conclusion:** `@Transactional` manages the integrity of transactions that Spring actually controls. Correctness across a multi-service chain comes from **API contracts, idempotency, durable intent recording, state machines, compensation, and reconciliation**. "Local transaction succeeded" and "distributed business operation completed" are two distinct milestones that must be modeled and observed separately.

## Reference documentation

- Spring Framework — [Declarative Transaction Management / Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).
- Spring Framework — [Declarative transaction semantics](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html).
- Spring Framework — [Transaction-bound events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html).
- AWS Prescriptive Guidance — [Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html).
- Microservices.io — [Transactional outbox](https://microservices.io/patterns/data/transactional-outbox.html), [Idempotent consumer](https://microservices.io/patterns/communication-style/idempotent-consumer.html), [Saga](https://microservices.io/patterns/data/saga.html).
