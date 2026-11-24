# Review Checklist for Application Events in Spring Framework

## 1. Purpose of the Checklist

Spring Framework supports internal publish–subscribe via **ApplicationEventPublisher**, **ApplicationListener**, **@EventListener**, and **@TransactionalEventListener**. This pattern reduces coupling between publishers and components reacting to events. However, having annotations does not automatically guarantee the right transaction, the right thread, zero lost events, or duplicate-processing protection.

This checklist is for reviewing a PR that uses **Spring Framework Application Events**, belonging to the **Practice and Summary** group. Reviewers must confirm:

- **Event contract**: what business fact does the event represent, when is it published, and what data does it carry?
- **Publisher and listener ownership**: who publishes, who listens, and in which context are they registered?
- **Transactions**: is the event handled before commit, after commit, or on rollback?
- **Execution**: synchronous or async, and how do exceptions affect the caller?
- **Reliability**: what happens if the JVM dies, the broker retries, or events arrive duplicated or out of order?
- **Security and observability**: are sensitive data, traces, metrics, and alerts sufficient?
- **Verification**: are there tests proving behavior beyond mocking the publisher?

For each item, mark **PASS/FAIL/N/A** with evidence. Unrelated items (such as an outbox for best-effort telemetry events) can be marked N/A with justification. However, for critical payment or invoicing events, an in-memory listener alone cannot be declared a delivery guarantee.

## 2. Determining Whether Events Are the Right Fit

An **Event** should describe a fact that has occurred, such as **OrderPlaced**, **PaymentCaptured**, or **StockReserved**. A **Command** requests an action to be performed, such as **ChargePayment** or **SendInvoice**. Names like **ProcessOrderEvent** often hide a command behind an event, blurring ownership.

| Question | Good sign | Warning sign |
| --- | --- | --- |
| Are listeners independent? | An analytics failure does not invalidate the order | A secondary listener decides the use case outcome |
| Is a strict order required? | An application service/orchestrator owns step transitions | Relying solely on `@Order` across listeners |
| Must an overall result be returned? | Clear workflow owner and state | Caller publishes and reports the entire chain succeeded |
| Does the event have multiple subscribers? | Each consumer owns a distinct responsibility | Multiple consumers perform the same side effect |
| Must integration events cross service boundaries? | Durable broker/outbox per SLA | Using only Spring in-process events |

An event chain A -> B -> C can make sense for independent reactions, yet when a flow needs retries, timeouts, compensation, and resume after restarts, **orchestration** is usually easier to review. **@Order** is not a workflow engine, does not guarantee async completion, and does not provide a shared transaction.

## 3. Reviewing the Event Contract

A plain Java 17 event:

~~~java
public record OrderPaid(
        String eventId,
        String orderId,
        String paymentId,
        long aggregateVersion) {}
~~~

This is an illustrative data type, not a standalone program. Spring can publish POJOs without requiring classes to extend **ApplicationEvent**. The domain does not need to import Spring merely to define business facts; application/infrastructure adapters can add envelopes, tracing metadata, and transport concerns.

**Contract checklist:**

- [ ] Event name clearly states a fact that has occurred; do not publish **OrderPaid** before payment is genuinely confirmed per contract.
- [ ] Event has a stable identity (**eventId**) if retries/redelivery are needed; do not mint a new ID for a redelivery of the same occurrence.
- [ ] **aggregateId** and **aggregateVersion/sequence** are present when ordering or projections need them.
- [ ] Integration events include **eventType/schemaVersion** so old and new consumer versions can coexist.
- [ ] Payload is a meaningful immutable/snapshot object, not holding mutable JPA entities or lazy proxies across async boundaries.
- [ ] Data is minimal, avoiding serializing entire object graphs or secrets/PII beyond permitted scope.
- [ ] **occurredAt** has clear semantics, and is not used as proof of absolute commit order.
- [ ] Trace/correlation IDs are not used in place of event IDs or business keys.

When contracts change, review compatibility, version migration, and producer/consumer tests. Event classes can be plain Java in the domain while integration messages carry separate metadata; do not force the domain to depend on Kafka or Spring.

## 4. Reviewing the Publisher and Context Scope

Trace the path from the REST controller, job, or consumer to where **ApplicationEventPublisher.publishEvent(Object)** is called:

1. Which **ApplicationContext** does the publisher bean belong to?
2. How many code paths publish the same business event?
3. Is the event published **inside an open transaction or after the method finishes**?
4. When a command is retried, does it emit duplicate state transitions or events?
5. If the service uses **@Transactional**, do callers go through the Spring proxy, or does self-invocation bypass advice?
6. If using Spring Data **@DomainEvents**, which repository methods actually publish and when are pending events cleared?
7. If the event must not be lost, is publishing intent persisted **in the same database transaction** as the state change?

Snippet example:

~~~java
@Transactional
public void pay(String id) {
    Order order = orders.load(id);
    order.markPaid();
    orders.save(order);
    publisher.publishEvent(new OrderPaidEvent(id));
}
~~~

This is not a standalone compilable file. **publishEvent(...)** is not a commit boundary. Plain listeners can run before commit; transactional listeners register phase callbacks.

**Context hierarchy:** In a parent–child ApplicationContext, events from a child context can propagate up to the parent. Parent listeners can observe lifecycle events from both parent and child. To handle **ContextRefreshedEvent** only for the listener's own context, compare **event.getApplicationContext()** with the owning context. With POJO payloads, do not infer the true origin solely from **PayloadApplicationEvent.getSource()** in an ancestor; use explicit event metadata with a clear contract.

## 5. Reviewing Listener Registration

Spring needs the listener to be a **managed bean**; calling an annotated method directly in Java does not prove Spring registered it.

- [ ] Listener is created via `@Bean`, `@ComponentScan`, or an appropriate container mechanism.
- [ ] Listener declares the exact expected type rather than listening to all **ApplicationEvent** instances when only one business type is needed.
- [ ] **@EventListener(condition=...)** SpEL expressions and parameter metadata are covered by tests.
- [ ] Generic event types are not mismatched due to type erasure.
- [ ] No duplicate bean registrations from scanning the same package in both parent and child contexts.
- [ ] No infinite event-publishing loops or ownerless event chains.
- [ ] Subscription scope aligns with module, tenant, and business boundaries.

**Returning events from `@EventListener`:** Synchronous listeners can return an object/`Collection`/array for Spring to publish follow-up events. **Async listeners do not support return-value event publishing**; call the publisher explicitly if needed. Do not use return-value chaining for complex sagas lacking state, retries, and compensation.

## 6. Reviewing Transaction Phases

| Listener type | Timing | What to check |
| --- | --- | --- |
| **@EventListener** | Dispatched immediately on publish; sync by default | Are side effects running before commit valid? |
| **@TransactionalEventListener(BEFORE_COMMIT)** | Before commit | Do not assume DB already committed |
| **AFTER_COMMIT** | After successful commit | Do new DB writes use proper transactions and recovery? |
| **AFTER_ROLLBACK** | After rollback | Is cleanup/compensation properly scoped? |
| **AFTER_COMPLETION** | Both commit and rollback | Does handler distinguish outcomes when needed? |
| **fallbackExecution=true** | Allows running outside a transaction | Does it violate "only after commit"? |

By default, **@TransactionalEventListener** uses **AFTER_COMMIT** and **fallbackExecution=false**. Events published outside a compatible transaction will not trigger default transactional listeners.

### Counter-Example 1: Side Effect Before Rollback

~~~text
BEGIN TX
  save Order(status=PAID)
  publish OrderPaid
      -> @EventListener calls invoicing API
  exception -> ROLLBACK
~~~

An invoice may have been created even though the Order did not commit. This is a bug if business rules allow invoicing only after commit. **@TransactionalEventListener(AFTER_COMMIT)** selects the right timing, yet still risks losing the callback after commit if the JVM crashes.

### Counter-Example 2: DB Write in `AFTER_COMMIT` Without a New Transaction

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderPaidEvent event) {
    auditRepository.save(new AuditEntry(event.orderId()));
}
~~~

This is a counter-example snippet. During the completion phase, resources from the committed transaction may still be bound, yet **there is no further commit** for new writes. If you must write audits or read models after commit, use **@Transactional(propagation = Propagation.REQUIRES_NEW)** on a separate Spring-managed service called through its proxy, or **TransactionTemplate** with **PROPAGATION_REQUIRES_NEW**, plus an integration test verifying the persisted row.

If the audit must be atomic with business state, write it in the original transaction. **@Async** does not make a worker thread join the publisher's imperative transaction.

### Testing Transactions

In Spring TestContext, test methods annotated with **@Transactional** usually roll back at the end, preventing `AFTER_COMMIT` from firing. To test commits inside the same test, use **TestTransaction.flagForCommit(); TestTransaction.end()**, or use **TransactionTemplate** in a test without `@Transactional`.

## 7. Reviewing Sync/Async and Exception Handling

The default **SimpleApplicationEventMulticaster** invokes listeners on **the publisher thread**. A slow listener slows down the caller; if a listener throws an exception without an appropriate `ErrorHandler`, the exception can propagate back to the publisher. A non-critical analytics observer must not unintentionally fail a payment.

Two primary async mechanisms:
- **@Async** per listener, with `@EnableAsync` and a Spring-managed `TaskExecutor`.
- A custom **applicationEventMulticaster** using **setTaskExecutor(...)**.

**ApplicationListener.supportsAsyncExecution()** can cause certain listeners—especially transaction-synchronized listeners—to run on the publisher thread to register callbacks properly, even when the multicaster has an executor.

Async checklist:
- [ ] Know which executor is actually used; avoid accidental double scheduling.
- [ ] Pool size, queue capacity, rejection policy, and graceful shutdown are configured.
- [ ] Exceptions from `void @Async` listeners have an **AsyncUncaughtExceptionHandler**, logs/metrics, or retries per contract.
- [ ] **ThreadLocal/MDC/current trace context** are propagated when needed; **ContextPropagatingTaskDecorator** with appropriate Micrometer accessors can be used.
- [ ] Do not expect async listeners to return events to automatically drive a chain.
- [ ] Do not expect `@Async` to carry the caller's transaction to workers.
- [ ] Critical events use a durable queue/outbox rather than an in-memory queue alone.
- [ ] Async tests use `CountDownLatch`/Awaitility/polling, never fixed `Thread.sleep`.

**`@Order` only prioritizes dispatch**; it does not guarantee async completion order, persist workflow state, or replace transactions.

## 8. Reviewing Reliability, Retries, and Idempotency

If the domain DB commits and the JVM dies before sending the event, **Spring `ApplicationEventPublisher`** has no durable record to replay. **AFTER_COMMIT** is not a durable queue.

For critical events, a common pattern is:

~~~text
BEGIN PRODUCER DB TRANSACTION
   update business state
   insert outbox(eventId, aggregateId, payload)
COMMIT
     |
     v
outbox relay -> broker ACK -> consumer
     |
     +-- relay crashes after send before ACK: may re-send
~~~

The outbox row and business state must share **the same real transaction**, not two independent `REQUIRES_NEW` transactions. The relay marks `SENT` only after confirmation per broker contract, with retries/backoff, claims/leases, and monitoring. If an ACK is lost, the same `eventId` can be sent again.

Consumers should implement idempotency:

~~~text
BEGIN CONSUMER DB TRANSACTION
   insert processed_events(consumer_name,eventId)
   if new: apply business DB effect
   if duplicate: skip
COMMIT
ACK
~~~

The dedup marker and DB effect must share the same local transaction. For external APIs like payments or email, a local inbox does not cover the external side effect; use provider idempotency keys or reconciliation.

- [ ] Classified whether events are best-effort or critical.
- [ ] Critical events have durable publication and recovery.
- [ ] `eventId` remains stable across retries.
- [ ] Consumers are idempotent under duplicates and redelivery.
- [ ] Stale or out-of-order events are handled using proper versions/sequences.
- [ ] Backoff, parking/DLQ, and repair paths exist.
- [ ] Alerts exist for outbox pending age and consumer lag.
- [ ] Backup/retention policies never purge pending events.
- [ ] Replaying projections does not re-send emails or re-charge cards.
- [ ] Business-outcome reconciliation exists rather than trusting broker ACKs alone.

**At-least-once** inherently permits duplicates; **exactly-once business effects** do not happen automatically without idempotency where the real side effect occurs.

## 9. Reviewing Read Models and Ordering

Application Events often update read models or search indexes. Clarify whether **read-after-write is required**:

- Same DB with strong consistency: write projection and domain state in the same transaction when appropriate.
- `AFTER_COMMIT`: update after commit using a new transaction for DB writes, accepting the crash window.
- Outbox + consumer: eventual consistency requiring versioning, lag monitoring, and rebuild capability.

Read models can be stale; never rely on them as the sole source of truth for critical invariants like balances, inventory, or payment completion.

~~~text
OrderPaid(order=A,version=2)      -> projection PAID
OrderPlaced(order=A,version=1)    -> stale event arrives late
~~~

If a projector overwrites by arrival order, it can regress `PAID` back to `CREATED`. Snapshot projections can use atomic version guards/CAS; delta events need per-event deduplication and strict sequencing if steps depend on one another. Across multiple sources, never compare versions of different aggregates as a single sequence.

If an index corrupts, is there **event history, a retained topic, an outbox archive, or a write-store snapshot** to rebuild it? **ApplicationEventPublisher has no default replay.** When replaying, keep projection handlers separate from business side effects.

## 10. Reviewing Security, Observability, and Operations

Security checklist:
- [ ] Payloads contain no secrets, tokens, passwords, or unnecessary PII.
- [ ] Consumers/topics/queues have appropriate ACLs and data classification.
- [ ] Tenant identity is verified at trust boundaries, not blindly trusted from external metadata.
- [ ] Payload size limits and protections against event loops/storms are in place.
- [ ] Logs, DLQs, archives, and trace baggage have retention and redaction policies.
- [ ] `eventId`/`correlationId` are not mistaken for authentication credentials.

Useful observability fields:

| Field/metric | Meaning |
| --- | --- |
| `eventId`, `eventType`, `schemaVersion` | Identification and contract |
| `aggregateId`, `aggregateVersion` | Business identity/ordering |
| `publisher`, `listenerName`, `contextId` | Dispatch path |
| `traceId`, `correlationId` | Linking requests and workflows |
| `phase`, `threadName` | Transaction and async diagnostics |
| `outcome`, `attempt`, `duration` | Success/failure/retries |
| `executor queue depth`, `rejection count` | Async pressure |
| `outbox pending count`, `oldest pending age` | Stuck events |
| `consumer lag`, `parked count`, `dedup total` | Delivery health |
| `business completion lag` | End-to-end outcome |

Trace context across thread pools needs propagation; across brokers it requires injecting/extracting headers. **A broker ACK does not prove the consumer completed business processing.** For critical events, measure terminal outcomes such as `InvoiceIssued` after `OrderPaid`, not only send-success metrics.

## 11. Minimum Test Matrix

| Scenario | Result to prove |
| --- | --- |
| Publish in TX then commit | `AFTER_COMMIT` runs at the right time |
| Publish in TX then roll back | `AFTER_COMMIT` does not run; data rolls back |
| Exception after publish | Ordinary listener may run; phases match outcome |
| Publish outside TX | `fallbackExecution` follows contract |
| Sync listener throws exception | Caller or `ErrorHandler` handles properly |
| Async listener fails / rejected | Error policy and monitoring work |
| Duplicate / redelivery | Side effects do not double |
| Stale / out-of-order event | Projection does not regress |
| Child context publishes event | Parent listener does not cause unintended duplicate handling |
| Worker crashes after broker ACK before marking `SENT` | Retries may duplicate, consumer deduplicates |
| Crash after business commit | Outbox/recovery restores if event is critical |
| Replay / rebuild | Projection stays accurate without re-firing old side effects |
| Schema version mismatch | Consumer stays compatible or parks safely |

**Testing listener methods directly** only verifies Java logic; it does not prove Spring annotations were registered or ran in the right phase. Use integration tests with a real `ApplicationContext` and transaction manager. For async, use latches/timeouts, never fixed sleeps.

## 12. Runnable Java 17+ Example for Self-Review

The project uses **Spring Framework 6.2.9**, **Spring JDBC**, **H2 2.3.232**, **Java 17+**, and **Gradle 8.x**, without Spring Boot. The demo illustrates an immediate listener, `AFTER_COMMIT`, `AFTER_ROLLBACK`, and out-of-transaction publishing.

### Structure and Gradle

~~~text
spring-event-review/
  build.gradle
  src/main/java/demo/SpringEventReview.java
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'application'
}
repositories {
    mavenCentral()
}
dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
    implementation 'org.springframework:spring-jdbc:6.2.9'
    runtimeOnly 'com.h2database:h2:2.3.232'
}
application {
    mainClass = 'demo.SpringEventReview'
}
~~~

### src/main/java/demo/SpringEventReview.java

~~~java
package demo;

import javax.sql.DataSource;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public final class SpringEventReview {

    public record OrderSubmitted(String id) {}

    public static final class Listeners {
        @EventListener
        public void immediate(OrderSubmitted event) {
            System.out.println("immediate: " + event.id());
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void committed(OrderSubmitted event) {
            System.out.println("after-commit: " + event.id());
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_ROLLBACK)
        public void rolledBack(OrderSubmitted event) {
            System.out.println("after-rollback: " + event.id());
        }
    }

    public static final class Service {
        private final JdbcTemplate db;
        private final TransactionTemplate tx;
        private final ApplicationEventPublisher publisher;

        public Service(
                JdbcTemplate db,
                PlatformTransactionManager manager,
                ApplicationEventPublisher publisher) {
            this.db = db;
            this.tx = new TransactionTemplate(manager);
            this.publisher = publisher;
        }

        public void submit(String id, boolean rollback) {
            tx.executeWithoutResult(status -> {
                db.update("INSERT INTO orders(id) VALUES (?)", id);
                publisher.publishEvent(new OrderSubmitted(id));
                if (rollback) {
                    status.setRollbackOnly();
                }
            });
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:review_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            JdbcTemplate db = new JdbcTemplate(ds);
            db.execute(
                "CREATE TABLE IF NOT EXISTS orders "
                + "(id VARCHAR(80) PRIMARY KEY)");
            return db;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        Listeners listeners() {
            return new Listeners();
        }

        @Bean
        Service service(
                JdbcTemplate db,
                PlatformTransactionManager manager,
                ApplicationEventPublisher publisher) {
            return new Service(db, manager, publisher);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            Service service = context.getBean(Service.class);
            JdbcTemplate db = context.getBean(JdbcTemplate.class);

            System.out.println("case: commit");
            service.submit("A", false);

            System.out.println("case: rollback");
            service.submit("B", true);

            System.out.println("case: outside");
            context.publishEvent(new OrderSubmitted("C"));

            int count = db.queryForObject(
                "SELECT COUNT(*) FROM orders", Integer.class);
            System.out.println("db rows: " + count);
        }
    }
}
~~~

Run in the **spring-event-review** directory:

~~~bash
gradle --console=plain -q run
~~~

**Stdout printed by the program itself** with the default synchronous multicaster:

~~~text
case: commit
immediate: A
after-commit: A
case: rollback
immediate: B
after-rollback: B
case: outside
immediate: C
db rows: 1
~~~

Explanation: A commits so both immediate and `AFTER_COMMIT` run. B publishes and rolls back, so immediate ran while `AFTER_ROLLBACK` was called instead of `AFTER_COMMIT`; B does not exist in the DB. C is published outside any transaction so only the plain listener runs. The database retains only A.

**Practice questions:** If the immediate listener sent an email, would B send an erroneous email? If `AFTER_COMMIT` writes to the DB, where is a new transaction needed? If an async worker dies before processing, is there a durable outbox? If the event is redelivered, is the downstream idempotent?

The demo implements no outbox/broker/async or security; do not use this output to claim critical events have durability.

## 13. Severity Levels for PR Review Findings

**Blocker:**
- Critical events can be lost after business commit with no durable recovery.
- External side effects run before commit when business rules forbid it.
- Payments/inventory/invoices repeat on redelivery without idempotency.
- Async listener depends on the publisher's transaction.
- Events carry credentials or violate tenant/data privacy boundaries.
- Two handlers execute the same mandatory effect without clear ownership.
- Missing tests for transaction/failure paths protecting business invariants.

**Major:**
- Missing `eventId`/version when retries or ordering are needed.
- Missing executor rejection, shutdown, or error policies.
- `@Order` used in place of orchestration.
- No monitoring of pending age or consumer lag for events with SLAs.
- Schema migration does not preserve consumer compatibility.
- Tests only verify `publishEvent` without verifying listener transaction behavior.

**Improvement:**
- Standardizing event naming, metadata, docs, and structured logging.
- Adding dashboards or extended tests for low-risk paths.
- Trimming payloads, splitting oversized listeners, or data-driven performance tuning.

A finding can be a blocker for payments yet merely an improvement for best-effort telemetry. **Reviewers must state impact and evidence** rather than treating all events identically.

### Sample Review Comment

**Finding:** "`@EventListener` currently calls the invoicing API before the domain transaction commits."

**Impact:** "If the transaction rolls back, an invoice may still be created."

**Suggestion:** "Move the side effect to a post-commit boundary; if it must not be lost on JVM crash, write a transactional outbox alongside business state and make the consumer idempotent. Add rollback and crash-window tests."

## 14. Final Pre-Approval Checklist

### A. Contract/ownership
- [ ] Event expresses a clear fact at the right moment.
- [ ] Event-driven fits better than direct calls or orchestration.
- [ ] Publisher, consumer, and side-effect owners are clear.
- [ ] Payload is immutable, compact, and contains no prohibited data.
- [ ] Event ID, aggregate ID, version, and schema exist where needed.

### B. Spring wiring
- [ ] Listener is a Spring-managed bean with the right type and condition.
- [ ] No unintended duplicate registration.
- [ ] Parent–child contexts and lifecycle events considered if applicable.
- [ ] Neither `@Order` nor return-value chaining is confused with a workflow.
- [ ] Executor/`AsyncUncaughtExceptionHandler`/error policies configured where needed.

### C. Transaction/reliability
- [ ] Publisher's transaction boundary is known.
- [ ] `@TransactionalEventListener` phase and fallback match the contract.
- [ ] Rollback causes no invalid external side effects.
- [ ] DB writes inside `AFTER_COMMIT` use a new transaction where needed.
- [ ] Critical events have durability, retries, and recovery.
- [ ] Consumers are idempotent and handle out-of-order and replay safely.
- [ ] Reconciliation, parking, and monitoring exist where needed.

### D. Security/observability
- [ ] Payloads, logs, and trace baggage satisfy security and retention policies.
- [ ] Consumers verify tenant/trust boundaries.
- [ ] Trace/event/correlation IDs are traceable across executors and brokers.
- [ ] Metrics, pending-age alerts, lag tracking, and business-completion checks exist.

### E. Tests
- [ ] Integration tests prove Spring dispatch works properly.
- [ ] Commit, rollback, and out-of-transaction cases are covered.
- [ ] Async error and rejection tests exist if async is used.
- [ ] Duplicate, stale, and replay tests exist if redelivery can occur.
- [ ] Crash, restart, and broker-outage tests exist if events are critical.
- [ ] Tests verify **persisted business outcomes**, not only publisher calls.

## 15. 60-Second Quick Review

1. What **fact** is the event, and who publishes it?
2. Does any subscriber carry a mandatory business step without a workflow owner?
3. Does the listener run **before or after commit**; what happens on rollback?
4. Where do synchronous and async exceptions go?
5. Will a JVM crash right after commit lose a critical event?
6. Can retries or redelivery duplicate side effects?
7. Can out-of-order events corrupt projections?
8. Could the listener be registered twice or receive events from a child context?
9. Are security, logging, tracing, and monitoring enough to investigate incidents?
10. What do tests prove beyond the happy path?

**Conclusion:** Reviewing Spring Application Events means reviewing **business semantics, wiring, transactions, async execution, delivery guarantees, and operations**. Not every telemetry event needs an outbox, yet for critical payment or invoicing events, an in-memory callback is no delivery guarantee. Approve only once essential risks are mitigated with matching tests or technical evidence.

### Official Documentation

- Spring Framework Reference — *Standard and Custom Events*: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework Reference — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework Javadoc 6.2.9 — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework Javadoc 6.2.9 — *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework Javadoc 6.2.9 — *EventListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html
- Spring Framework Javadoc 6.2.9 — *TransactionalEventListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
