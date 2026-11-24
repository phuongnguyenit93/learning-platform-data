# Common Interview Questions on Spring Framework Application Events

## 1. Review Goals and How to Answer in Interviews

Spring Framework Application Events is an **in-process publish–subscribe mechanism within an application context**, commonly used to decouple a business operation that publishes an event from components reacting to it. In interviews, interviewers do not just want to hear the `@EventListener` annotation name—they evaluate your ability to explain **the execution path**, **transactions**, **async**, **errors**, **consistency**, and **architectural trade-offs**.

This lesson compiles questions from basic to advanced, complete with reasoned answers, examples, and common traps. The strongest way to structure answers to design questions typically follows four parts:

1. **State the default mechanism:** same JVM/context, listeners are normally synchronous.
2. **Point out the limits:** no built-in durable queue, retries, cross-service transactions, or exactly-once delivery.
3. **Choose the right tool:** `@EventListener`, `@TransactionalEventListener`, `@Async`, outbox, broker, or application service.
4. **State how to verify:** integration tests, logging/tracing, transaction boundaries, retry/idempotency tests, and performance measurement.

Never repeat slogans like "events are always asynchronous" or "publish succeeding means processing finished". Both are **false in the default model**.

### Quick Knowledge Map

| Question group | Capabilities to demonstrate |
| --- | --- |
| Fundamentals | Publisher, listener, payload object, `ApplicationEvent`, `ApplicationContext`. |
| Mechanics | Multicaster, type matching, ordering, conditions, return-value publication. |
| Async | `@Async`, executors, exceptions, thread context, ordering, and shutdown. |
| Transactions | `@TransactionalEventListener`, phases, rollbacks, no-transaction handling. |
| Spring Boot | Lifecycle events, early listener registration. |
| Design | Immutability, metadata, versioning, idempotency, outbox/broker. |
| Operations | Security, observability, testing, performance, troubleshooting. |

## 2. Basic Questions: Concepts and APIs

### Q1. What are Spring Application Events?

**Answer:** An event-based communication mechanism inside the Spring container: a component calls `ApplicationEventPublisher.publishEvent(...)` to announce a fact or state change; matching listeners are invoked by the framework without the publisher needing direct references to each listener.

For example: when an order is placed, `OrderService` publishes `OrderPlaced`; `AuditListener` writes an audit log and `StatisticsListener` updates metrics. Direct dependencies from `OrderService` to both listeners are replaced by an event contract.

**Worth adding:** this is **in-process event dispatch**, not equivalent to Kafka/RabbitMQ, and does not automatically preserve events after the process crashes.

### Q2. Which components participate in an event's path?

**Short answer:** `ApplicationEventPublisher` (the publishing API), `ApplicationContext` (the usual publishing entry point), `ApplicationEventMulticaster` (manages and dispatches to listeners), and `ApplicationListener` or `@EventListener` methods (handlers).

~~~text
Service -> ApplicationEventPublisher.publishEvent(event)
                   |
                   v
          ApplicationContext
                   |
                   v
       ApplicationEventMulticaster
                   |
            +------+------+
            |             |
      @EventListener A  ApplicationListener B
~~~

`SimpleApplicationEventMulticaster` is the standard implementation. Applications can replace/customize the bean named `applicationEventMulticaster` to configure an executor and error handling.

### Q3. What is the difference between `ApplicationEvent` and a payload object?

**Answer:** Older event classes extend `ApplicationEvent`; since Spring 4.2, you can also publish **any arbitrary Java object**. If the payload does not extend `ApplicationEvent`, Spring wraps it in `PayloadApplicationEvent` when passing it through the multicaster.

~~~java
public record OrderPlaced(String orderId) {}

publisher.publishEvent(new OrderPlaced("ORD-1"));
~~~

*Illustrative snippet inside a Spring bean with a publisher; requires defining/importing `ApplicationEventPublisher`.*

You do not need to write `extends ApplicationEvent` just to have a domain event. Java records fit shallowly immutable payloads well, though **a record is not deeply immutable** if a field holds a mutable list or map.

### Q4. Is `ApplicationEventPublisher` a message broker?

**No.** It is an event-publishing API inside a Spring application. It has no built-in durable message storage, acknowledgments, consumer offsets, dead-letter queues, broker-level retries, or cross-JVM delivery.

If cross-service delivery or processing across application restarts is required, design an appropriate broker, event store, or outbox. You can use Spring Application Events to decouple modules inside one service **and** a broker at inter-service boundaries; they are not mutually exclusive.

### Q5. How does `ApplicationListener` differ from `@EventListener`?

| `ApplicationListener<E>` | `@EventListener` |
| --- | --- |
| Implements an interface, usually `onApplicationEvent(E)`. | Method annotation on a Spring bean. |
| Explicit listener type on the interface, handy for startup/early registration in some cases. | Concise, supports SpEL `condition`, can declare multiple event types. |
| Can register listener objects programmatically. | Discovered by Spring during bean processing. |
| Can pair with `GenericApplicationListener` to filter type/source. | Can return events to publish follow-up events synchronously. |

**Choose by problem:** in regular business code, `@EventListener` is more readable; when you need a listener before beans exist, explicit programmatic registration, or custom type/source matching, `ApplicationListener` fits better.

### Q6. Must an `@EventListener` method return `void`?

**No.** A method can return an object, and Spring will publish it as a follow-up event. If the method returns a `Collection` or array, **each element** is published as a separate event.

~~~java
@EventListener
public List<Object> afterOrderPlaced(OrderPlaced e) {
    return List.of(
        new AuditRequested(e.orderId()),
        new MetricsRequested(e.orderId()));
}
~~~

*Illustrative snippet inside a bean; `OrderPlaced`, `AuditRequested`, and `MetricsRequested` records must be defined. Return-value publication is **not supported for asynchronous listeners**.*

If you want a single event containing a list, wrap it like `BatchReady(List<String> ids)` instead of returning `List<String>` directly.

### Q7. Can one listener handle multiple event types?

Yes. You can use `@EventListener({ContextStartedEvent.class, ContextRefreshedEvent.class})` when the method does not require a single specific parameter type, or create separate typed methods per event. When using one method for unrelated types, mind the signature and inspect metadata appropriately.

For domain events, separating `onOrderPlaced(OrderPlaced)` and `onPaymentCaptured(PaymentCaptured)` is usually clearer than one catch-all method branching with `instanceof`.

### Q8. Does a listener have to be a Spring bean?

For `@EventListener`, **yes**: the method must reside on a container-managed bean and be discovered by the event listener processor. Creating an object via `new MyListener()` outside the context will not register it automatically.

For `ApplicationListener`, you can register a listener instance via `SpringApplication.addListeners(...)` (in Boot) or multicaster APIs per lifecycle needs. Registering too late, listening in the wrong context, or excluding the bean via profiles are common reasons events are missed.

### Q9. Can events be published from any service?

Yes, inject `ApplicationEventPublisher` into any Spring-managed component and call `publishEvent(event)`, as long as the code has the right publisher/context.

~~~java
@Service
class OrderService {
    private final ApplicationEventPublisher publisher;

    OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    void place(String orderId) {
        // Execute business logic...
        publisher.publishEvent(new OrderPlaced(orderId));
    }
}
~~~

*Illustrative integration snippet; `OrderPlaced` is a domain record. Required imports include `@Service` and `ApplicationEventPublisher`.*

Publish events describing **meaningful business facts**, rather than replacing every method call with events or hiding a mandatory synchronous workflow.

### Q10. Why prefer immutable events?

Listeners may run later, on another thread, or read the event after the producer modified the original object. Immutable payloads keep data consistent, reduce race conditions, and simplify testing. Avoid exposing JPA entities or lazy proxies as public event contracts; use IDs and minimal snapshots instead.

When a record holds collections, use `List.copyOf(...)` in a compact/canonical constructor for defensive copying. Restrict sensitive data per recipient rather than "publishing the whole entity for convenience".

## 3. Questions on Dispatch Mechanics, Filtering, and Ordering

### Q11. How does Spring find matching listeners?

The multicaster selects listeners by event type; for generic events it can use `ResolvableType`. Specialized listeners like `GenericApplicationListener` can inspect both `supportsEventType(...)` and `supportsSourceType(...)`. Spring caches pre-filtered candidate lists for eligible event/source types to avoid repeated matching.

**Matching caches are not processing caches.** The same event type still triggers handlers on every publish; `@EventListener(condition=...)` is still evaluated against each event's data.

### Q12. What is `@EventListener(condition)`?

`condition` is a SpEL expression that decides whether the method is invoked for a **specific event**:

~~~java
@EventListener(condition = "#p0.totalMinorUnits() >= 10000")
public void onLargeOrder(OrderPlaced event) { }
~~~

*Illustrative snippet; `OrderPlaced` must have a `totalMinorUnits()` method.*

`#p0` or `#a0` refers to the first parameter; `#root.args[0]` is the listener's argument. `#event` is only safe when parameter names exist via Java compiler metadata (`-parameters`). `#root.event` is the **actual `ApplicationEvent`**; when publishing an arbitrary payload, it is usually `PayloadApplicationEvent`, not the payload directly.

### Q13. In what order should you debug a `condition` that is always false?

1. Ensure the publisher emits **the exact expected object/type/value**, not just guessing from DB state.
2. Add a probe listener without a condition in the same context to verify the event arrives.
3. Try `condition="true"` to separate routing/registration from filter logic.
4. Replace parameter names with `#p0`; check compiler `-parameters` if using `#namedParameter`.
5. Check String casing, enums, nulls, currency units, and `>` vs `>=`.
6. Distinguish boolean false from `SpelEvaluationException`: invalid property/method access throws rather than silently returning false.
7. For `@TransactionalEventListener`, check whether a transaction and matching phase exist.

Interview tip: explain **how to prove the root cause**, not randomly tweaking the expression.

### Q14. Does `@Order` guarantee processing order?

`@Order` orders matching listeners within a **synchronous** dispatch path. Smaller numbers indicate higher priority. Never infer that events going through an async executor will finish in that order; `@Order` cannot serve as a durable cross-service ordering protocol.

If business rules require step A to succeed before running B, an application service or workflow orchestration is usually clearer than a chain of listeners implicitly relying on order.

### Q15. If one listener throws an exception, do other listeners still run?

In the default synchronous `SimpleApplicationEventMulticaster` **without a custom `ErrorHandler`**, an exception from one listener can stop multicasting and propagate back to the publisher, preventing later listeners from running. Configuring `setErrorHandler(...)` or an executor can change that behavior.

Therefore never state "one failing listener affects nobody". For independent side effects, design isolated error handling/queues; for synchronous transactions, evaluate rollbacks and already-executed side effects.

### Q16. Does `@EventListener` automatically run on its own thread?

**No.** By default, `SimpleApplicationEventMulticaster` invokes listeners on the event-publishing thread. A 300 ms listener can block `publishEvent(...)` by 300 ms when synchronous.

For async, use `@Async` with `@EnableAsync` and an appropriate executor, or supply a `TaskExecutor` to the `applicationEventMulticaster` bean. The two approaches differ in configuration points, error handling, and scope of impact.

### Q17. How does `@Async` on a listener differ from an async multicaster?

- `@Async`: applied at the listener method via Spring proxy, typically picking an executor by name/qualifier or the default executor.
- Async multicaster: configures `SimpleApplicationEventMulticaster.setTaskExecutor(...)`, affecting listeners the multicaster can execute asynchronously.
- Since Spring Framework 6.1, listeners reporting `supportsAsyncExecution() == false` still run on the publishing thread at the multicaster level, such as transaction-bound listeners.
- Using both can introduce **multiple thread hops** and make tracing, transactions, and ordering harder to reason about.

In either case, neither provides a durable queue or retries by default.

### Q18. Why shouldn't an `@Async` listener return an event?

Spring documents that **asynchronous event listeners do not support publishing events via return values**. To emit an event after async processing succeeds, inject `ApplicationEventPublisher` and call `publishEvent(...)` explicitly at the right moment.

~~~java
@Async
@EventListener
public void handle(PaymentCaptured event) {
    // Process...
    publisher.publishEvent(new ReceiptPrepared(event.paymentId()));
}
~~~

*Illustrative integration snippet requiring a publisher bean, `@EnableAsync`/executor, and the corresponding event types.*

Do not return `List<Object>` from an `@Async` method expecting Spring to publish each item; that is a misconception about async result handling.

### Q19. Do `ThreadLocal`, `SecurityContext`, and MDC follow `@Async` listeners?

**Not automatically.** When a listener runs on a thread pool, the publisher's `ThreadLocal`, MDC, and Spring Security `SecurityContextHolder` are not inherited as on the same thread. Use proper propagation, such as `ContextPropagatingTaskDecorator` (Micrometer) for logging/observation and `DelegatingSecurityContextAsyncTaskExecutor` when security context propagation is genuinely required.

Do not copy a JDBC transaction or `EntityManager` to workers via `ThreadLocal`. Thread-bound transactions have independent lifecycles; if an async listener needs a DB transaction, open a new transaction at the right boundary.

### Q20. Does publishing an event mean all listeners have finished?

You can only infer based on actual configuration. With the default **synchronous** multicaster and normal completion, `publishEvent(...)` usually returns after those listeners finish. With `@Async` or an async multicaster, the publisher can return immediately once listeners are scheduled, before side effects finish.

Even synchronously, "the listener ran" does not mean an email was permanently delivered, a DB transaction committed, or the event was durably persisted.

## 4. Questions on Transactions and Data Consistency

### Q21. How does `@EventListener` differ from `@TransactionalEventListener`?

An ordinary `@EventListener` receives the event when it is published in the context and does not wait for the current transaction to commit.

`@TransactionalEventListener` binds handling to **a transaction phase**, defaulting to `TransactionPhase.AFTER_COMMIT`. It fits when you only want to react after a successful commit, avoiding acting on data that later rolls back.

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderPlaced event) {
    // Runs after the event-publishing transaction commits.
}
~~~

*Illustrative integration snippet requiring a transaction manager, a real transaction, and imports for `@TransactionalEventListener`/`TransactionPhase`.*

### Q22. Which transaction phases are supported?

| Phase | When is the listener triggered? | Scenario |
| --- | --- | --- |
| `BEFORE_COMMIT` | Before transaction commit. | Extra checks/aggregation inside the commit flow when strictly needed. |
| `AFTER_COMMIT` (default) | When the transaction completes with a successful commit. | Side effects that should occur only if the business fact committed. |
| `AFTER_ROLLBACK` | When the transaction ends with a rollback. | Recording failure state or explicitly designed compensation. |
| `AFTER_COMPLETION` | After the transaction completes, whether commit or rollback. | Cleanup/telemetry. |

If no matching transaction is active, `@TransactionalEventListener` **does not run** by default unless `fallbackExecution=true` is set. Never enable fallback just to "fix a silent listener" without revisiting business requirements.

### Q23. If published inside `@Transactional` and then rolled back, which listeners ran?

Assuming `service.placeOrder()` is inside a transaction:

- A synchronous `@EventListener` may already have run right at publish time, before commit/rollback outcome was known.
- `@TransactionalEventListener(AFTER_COMMIT)` does not run if the transaction rolls back.
- An `AFTER_ROLLBACK` listener runs during the rollback phase.
- `@Async` or custom-executor listeners are not automatically coordinated with the source DB transaction.

Never trigger un-rollbackable emails or HTTP calls inside a synchronous listener if business rules require post-commit execution.

### Q24. Can you write to the DB inside an `AFTER_COMMIT` callback?

Yes, provided you understand the boundary: the source transaction has already committed; transaction resources may still be bound during the callback, yet new writes will not receive a subsequent commit on the old transaction. When a separate DB update is needed, open a **new transaction**, such as via a service with `@Transactional(propagation = Propagation.REQUIRES_NEW)` called through a proper proxy.

Do not make the method `private` or use self-invocation and expect transaction annotations to work if the AOP proxy is bypassed.

### Q25. Does `@TransactionalEventListener` work with reactive transactions?

Yes, starting in Spring Framework 6.1 there is dedicated support for reactive transaction contexts. Imperative transactions typically bind to `ThreadLocal` via `PlatformTransactionManager`; reactive transactions rely on **Reactor Context**. In reactive flows, transaction context must pass through **the event source** per Spring's guidance; `TransactionalEventPublisher` is the API for publishing events with the appropriate transaction context.

Never mechanically apply "the thread has an active transaction" reasoning to a Reactor pipeline. Always identify the transaction stack (JDBC/JPA vs. R2DBC/reactive) before choosing listeners.

### Q26. Does `AFTER_COMMIT` guarantee an event is never lost after DB commit?

**No.** A post-commit callback still runs inside the application process and can be lost if the JVM crashes at that moment without durable storage. It solves **timing relative to the transaction**, not **durable delivery**.

When the requirement is "once committed, a message must exist to be processed", consider a **transactional outbox**: write an outbox row in the same transaction as domain data, have a relay forward it to a broker, and make consumers retryable and idempotent.

### Q27. What problem does the transactional outbox solve?

It prevents situations where the DB commits successfully while publishing to a broker fails with no durable record left to retry.

~~~text
@Transactional
  UPDATE orders
  INSERT outbox(eventId, type, payload, ...)
  COMMIT
        |
        v
Outbox relay -> broker -> consumer
                    |
                    +-- idempotent processing by eventId
~~~

An outbox does not automatically make the whole system exactly-once. Relays can send duplicates; consumers still need side-effect deduplication, per-aggregate ordering where required, and monitoring for pending/failed rows.

### Q28. Does event-driven design replace transaction management?

**No.** Events are a communication/coordination mechanism; transactions are a resource-consistency mechanism. The two concepts relate yet are distinct. For changes that must be atomic in one database, use explicit transactions. For cross-service workflows, combine events with idempotency, retries, compensation/sagas, or outboxes depending on the model—never assume `publishEvent` gives global atomicity.

## 5. Questions on Spring Boot Lifecycle and Early Listener Registration

### Q29. What are the main lifecycle events published by `SpringApplication`?

A typical sequence on successful startup in Spring Boot 3.5:

1. `ApplicationStartingEvent`: at the very start of `run`, before most processing.
2. `ApplicationEnvironmentPreparedEvent`: `Environment` is prepared, context not yet created.
3. `ApplicationContextInitializedEvent`: context prepared and initializers applied, before loading application bean definitions.
4. `ApplicationPreparedEvent`: before refresh, after bean definitions are loaded.
5. `ApplicationStartedEvent`: context refreshed, before application/command-line runners execute.
6. `ApplicationReadyEvent`: after runners finish; signals the app is ready to serve traffic.
7. `ApplicationFailedEvent`: published if startup fails.

Alongside `SpringApplicationEvent`s, there are `ContextRefreshedEvent` and others like `WebServerInitializedEvent` depending on application type. Do not force every event into one rigid order across all environments; distinguish sources and lifecycles.

### Q30. Why doesn't an `@EventListener` bean receive `ApplicationStartingEvent`?

Because several Boot events fire **before the `ApplicationContext` and application listener beans exist**. Annotated methods on beans are not registered yet and cannot receive them.

Solution for very-early Boot events: register `ApplicationListener` before `SpringApplication.run(...)` via `SpringApplication.addListeners(...)`, `SpringApplicationBuilder.listeners(...)`, or `META-INF/spring.factories` when packaging a library.

`@EventListener` fits events occurring after listener beans are managed and registered.

### Q31. How does `ApplicationStartedEvent` differ from `ApplicationReadyEvent`?

`ApplicationStartedEvent` occurs **after context refresh but before application/command-line runners**. `ApplicationReadyEvent` occurs **after runners finish**, indicating readiness within Boot's lifecycle.

If you need startup preparation that might slow boot time, consider `ApplicationRunner`/`CommandLineRunner`, background initialization, or an appropriate lifecycle mechanism instead of putting heavy synchronous work on `ApplicationReadyEvent`.

### Q32. What is `ApplicationFailedEvent`, and does it always reach listener beans?

`ApplicationFailedEvent` is sent by Boot when startup fails, yet the context may be incomplete or have failed before listener beans were registered. Therefore, to catch **early startup failures**, register a listener via `SpringApplication`/`spring.factories` rather than relying solely on an `@EventListener` bean.

Do not confuse it with runtime error monitoring or a process manager's restart mechanism; it specifically reports **startup** failures.

### Q33. Why might the same lifecycle event be received twice in one application?

When Spring Boot uses a **parent–child context hierarchy**, events published in a child context can propagate up to the ancestor context. Listeners in the hierarchy can observe multiple instances of the same event type. Inspect `event.getApplicationContext()` (for lifecycle events exposing it) and compare it against the context owning the listener bean.

Do not immediately blame the listener cache or assume `@EventListener` double-sends. Check context hierarchies, duplicate beans, and listener registration first.

## 6. Advanced Questions: Contracts, Event Chains, Observability, and Security

### Q34. What is the difference between a domain event and a command?

A **domain event** asserts a fact that has happened, such as `OrderPlaced` or `PaymentCaptured`. A **command** requests an operation to be performed, such as `CapturePayment` or `SendReceipt`. Event names should be past-tense with stable semantic contracts.

If an event forces a single listener to execute a mandatory action while the publisher implicitly waits for the result, the architecture may be disguising a command or a direct service call.

### Q35. What are the risks of one listener emitting multiple follow-up events?

Returning a `Collection`/array lets Spring publish each item, creating **fan-out** or **event chaining**. Risks:

- `A -> B -> A` loops when a listener returns an event that triggers itself.
- A downstream listener failing halts the rest of a synchronous chain.
- Hidden ordering dependencies among listeners.
- Replaying the input event re-triggers side effects.
- Using `@Async` while still expecting return-value publication to work.

If a workflow has mandatory sequencing, consider an explicit application service or workflow engine.

### Q36. What should an event contract contain?

At minimum: event type/business name, version, event ID, aggregate ID, occurrence time, minimal payload snapshot, field types/units/nullability, provenance, and emission semantics. For multi-step workflows, add `correlationId` and `causationId`.

**Do not** place mutable `@Entity` objects, full object graphs, or credentials into public event contracts. For money, specify unit and currency; for timestamps, use UTC/`Instant`.

Adding a field is not automatically backward-compatible everywhere: Java constructors, strict JSON deserializers, legacy consumers, expanded enums, and semantic shifts can all break contracts.

### Q37. How do you migrate from event V1 to V2 without breaking consumers?

A common strategy is **expand -> migrate -> contract**:

1. Define V2, mappings, and backward/forward compatibility rules.
2. Upgrade consumers/adapters to read both V1 and V2 before changing the producer.
3. Test against historical event fixtures and the new version.
4. Switch the producer; monitor decode errors and consumer coverage.
5. Retire V1 once no dependencies remain and historical data/replays are handled.

If dual-publishing V1 and V2 for **the same occurrence**, enforce routing and idempotency so two versions never trigger side effects twice. Occurrence `eventId` and `schemaVersion` need clear conventions.

### Q38. How do event ID and correlation ID differ?

`eventId` identifies **one occurrence**; `correlationId` links **multiple occurrences** in the same business flow. `orderId` is an aggregate ID, replacing neither of the two. One workflow can emit `OrderPlaced`, `PaymentCaptured`, and `OrderShipped` sharing a correlation ID while having distinct event IDs.

When retrying the same occurrence, keep the original event ID for deduplication; when emitting a new fact, mint a new event ID. Trace IDs/span IDs serve technical tracing and can change across retries; do not use them as unique business keys.

### Q39. Does Spring automatically provide distributed tracing per `@EventListener`?

Spring Framework **does not automatically create an Observation for every `@EventListener` invocation** just because of the annotation. For synchronous listeners, thread-bound logging/tracing context may remain active; across executors, explicit propagation is needed (such as `ContextPropagatingTaskDecorator` and Micrometer Context Propagation).

To measure individual handler latency/errors, instrument with Micrometer Observation/Tracing as needed. Never use event IDs or correlation IDs as **low-cardinality metric tags** due to high cardinality; put IDs in logs/span attributes when safe.

### Q40. Do Spring Application Events automatically enforce security for listeners?

**There is no automatic authorization check simply because a listener receives an event.** Type-based event routing is not the same as verifying an actor has permission to view or mutate a record. For sensitive side effects:

- Authenticate event origins and actors at trust boundaries.
- Enforce `@PreAuthorize`/`AuthorizationManager` on the service performing the operation (enabling `@EnableMethodSecurity` as needed).
- Check object/tenant permissions against authoritative data.
- For async, propagate `SecurityContext` appropriately or use a least-privilege service identity.
- Never trust `claimedRole="ADMIN"` inside a payload as real authority.

Never persist live JWTs or `Authentication` objects in long-lived event stores just to "keep permissions" across replays.

### Q41. How does the listener cache in the multicaster work?

`AbstractApplicationEventMulticaster` caches candidate listener lists keyed by **the event's `ResolvableType` and source type** whenever safe to cache. This reduces matching overhead when many events share types/sources. When listeners are registered or removed through official APIs, the pre-filter cache is invalidated.

**Caching does not reduce handler executions for matching events.** `@EventListener(condition)` filters still evaluate per payload; never put dynamic feature flags into `supportsEventType(...)` expecting Spring to invoke that predicate on every event.

### Q42. Can `@EventListener` be used for event sourcing?

`@EventListener` can **react** when an event is published, yet is not itself an event store. Event sourcing requires durably persisted events as the source of truth, ordering, versioning, replays, snapshots, migrations, and state reconstruction.

Publishing events in JVM memory that vanish on restart is **not a complete event sourcing implementation**. You need dedicated storage, schemas, idempotency, and replay mechanisms.

### Q43. When should you use Application Events vs. Kafka/RabbitMQ?

| Need | Application Events | Broker / outbox |
| --- | --- | --- |
| Decouple internal modules in same JVM | Good fit, lightweight setup. | Often too heavy if no process boundary is needed. |
| Run short secondary logic in-process | Good fit; mind sync/errors. | Not always necessary. |
| Deliver messages across services/processes | Cannot do on its own. | Good fit. |
| Replay after restart | Not supported by default. | Needs storage/log/retention and proper consumers. |
| Controlled retries, DLQ | Not built-in like brokers. | Designed around broker/outbox/inbox. |
| Atomic DB transaction then message delivery | Not guaranteed on its own. | Transactional outbox + relay is standard. |

Kafka and RabbitMQ have different characteristics; never lump "brokers" into one uniform guarantee. Specify delivery semantics, partitions/ordering, duplicates, and consumer failures per technology.

### Q44. Does Spring guarantee exactly-once event processing?

**Not by default.** Even when a broker offers scoped exactly-once features, external side effects such as sending emails or writing to another DB still require anti-duplication design.

For example, a consumer can insert `(consumerName, eventId)` with a unique constraint inside its transaction for idempotency. For HTTP or email side effects, consider partner idempotency keys, outbox/inbox, retries, and reconciliation.

### Q45. When should you NOT use `@EventListener`?

Avoid using events as an abstraction hiding:

- A mandatory step that must run in strict sequence and return errors directly.
- An operation needing a synchronous return result for the caller to decide next steps.
- A cross-service workflow requiring durable retries and replays.
- A sensitive capability without defined authorization and trust boundaries.
- A high-throughput hot path where hidden coupling/listeners complicate debugging more than module decoupling helps.

Direct service calls, an application orchestrator, or a broker/event store can be far clearer. Events deliver **controlled loose coupling**, not decoupling every call regardless of context.

## 7. Runnable Java 17+ Practice Exercise to Explain in Interviews

This example uses **Spring Framework 6.2.9**, Maven, and Java 17+, without Spring Boot so lifecycle events do not clutter stdout. We demonstrate four key points:

1. A publisher emits a **payload record** without extending `ApplicationEvent`.
2. Synchronous `@EventListener` methods ordered with `@Order`.
3. A SpEL `condition` filtering each event by a business value.
4. A listener returning `List<Object>` so Spring publishes **two independent follow-up events**.

### 7.1. Project Structure

~~~text
spring-event-interview/
├── pom.xml
└── src/main/java/InterviewEventsDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-event-interview</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/InterviewEventsDemo.java`:

~~~java
import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class InterviewEventsDemo {

    public record OrderPlaced(String orderId, long amountMinorUnits) {}

    public record AuditRequested(String orderId) {}

    public record MetricsRequested(String orderId) {}

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Handlers handlers() {
            return new Handlers();
        }
    }

    public static class Handlers {

        @Order(0)
        @EventListener
        public void observe(OrderPlaced event) {
            System.out.println("SEEN " + event.orderId()
                    + " " + event.amountMinorUnits());
        }

        @Order(10)
        @EventListener(condition = "#p0.amountMinorUnits() >= 10000")
        public List<Object> routeLargeOrder(OrderPlaced event) {
            System.out.println("ROUTE " + event.orderId());

            // Each element in the List becomes a separate event.
            return List.of(
                    new AuditRequested(event.orderId()),
                    new MetricsRequested(event.orderId()));
        }

        @EventListener
        public void audit(AuditRequested event) {
            System.out.println("AUDIT " + event.orderId());
        }

        @EventListener
        public void metrics(MetricsRequested event) {
            System.out.println("METRICS " + event.orderId());
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            System.out.println("BEGIN");
            context.publishEvent(new OrderPlaced("ORD-1", 15000));
            context.publishEvent(new OrderPlaced("ORD-2", 5000));
            System.out.println("END");
        }
    }
}
~~~

### 7.2. Running

In the directory containing `pom.xml`, with Maven and Java 17+:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=InterviewEventsDemo
~~~

**Stdout printed by the program** (excluding build/Maven or environment logs):

~~~text
BEGIN
SEEN ORD-1 15000
ROUTE ORD-1
AUDIT ORD-1
METRICS ORD-1
SEEN ORD-2 5000
END
~~~

### 7.3. Line-by-Line Analysis

- `BEGIN` appears before publishing.
- For `ORD-1`, `observe` has `@Order(0)`, so it prints `SEEN` before `routeLargeOrder` which has `@Order(10)`.
- Because `amountMinorUnits = 15000` meets the threshold, SpEL evaluates to true, prints `ROUTE`, and returns `List.of(AuditRequested, MetricsRequested)`.
- Spring publishes each child event: `audit` prints `AUDIT ORD-1`, then `metrics` prints `METRICS ORD-1`. Because calls are synchronous, they complete before the original event finishes.
- For `ORD-2`, `observe` still runs, while `routeLargeOrder`'s condition is false since `5000 < 10000`, producing no audit/metrics events.
- `END` appears only after both synchronous `publishEvent(...)` calls finish.

**Do not infer** that `routeLargeOrder`'s condition is cached by amount: Spring can cache **the candidate set by type**, while SpEL still checks each event's value. Adding `@Async` or an executor removes the log-order guarantees shown here.

### 7.4. Two Changes to Practice

**Exercise A:** change `ORD-2` from `5000` to `10000`. Because the condition uses `>=`, expected output adds `ROUTE ORD-2`, `AUDIT ORD-2`, and `METRICS ORD-2` before `END`.

**Exercise B:** suppose `audit` throws `IllegalStateException` with no `ErrorHandler`. In the default synchronous setup, predict whether `METRICS ORD-1` and `END` will print. Answer: **neither is guaranteed to print**; the exception can abort processing before dispatching the next element and propagate back to `publishEvent(...)`.

**Exercise C:** to make auditing run only after the order-saving transaction commits, add a real transaction and use `@TransactionalEventListener(AFTER_COMMIT)` at the right boundary. Do not just add the annotation to a demo **with no transaction** and expect the listener to fire.

## 8. Scenario Questions for Senior Interviews

### Scenario 1. Order succeeds, yet customers occasionally receive emails even when the DB rolls back

**Premise:** `@Transactional OrderService.placeOrder()` publishes `OrderPlaced`; a synchronous listener sends an email; then the transaction rolls back because a later check fails.

**How to answer:**

- A synchronous `@EventListener` may have executed **before commit**.
- Email is an external side effect that cannot roll back with the DB.
- If post-commit execution within the same JVM suffices, use `@TransactionalEventListener(AFTER_COMMIT)`.
- If the email **must not be lost** on process crash, write an outbox row in the same transaction and use a retrying relay/queue.
- Make the email consumer idempotent or pass an idempotency key when supported by the provider.
- Test rollback before sending, crash after commit, and duplicate delivery.

**Follow-up angle:** Is strictly once-only email required? If so, explain the limits of email APIs and reconciliation rather than promising absolute "exactly once".

### Scenario 2. After adding `@Async`, listener logs no longer have `traceId`

**How to answer:** `@Async` moves execution to an executor; the publisher's MDC/ThreadLocal tracing does not transfer automatically. Check the actual executor, `@EnableAsync`, and Micrometer Context Propagation; use `ContextPropagatingTaskDecorator` with appropriate accessors. Keep business `correlationId` in the payload/envelope to correlate across retries and new traces.

Never use `InheritableThreadLocal` as a general thread-pool solution. Never copy a JDBC transaction just to "preserve context".

### Scenario 3. There are two event handlers; when one fails, the second never runs

**How to answer:** Check synchronous multicasting and exceptions; if one listener throws an unhandled exception, dispatch can halt. Options depend on requirements: handle errors per handler, configure an `ErrorHandler`, split into independent work items, or use a broker/outbox with separate retries. Never swallow exceptions silently: maintain accurate logs, metrics, and outcomes.

### Scenario 4. `@TransactionalEventListener` does not run in a unit test

**How to answer:** Check whether the test has a real Spring-managed transaction, the phase, default `fallbackExecution=false`, and proxy invocation. A test instantiating objects with `new` or publishing outside a matching transaction will not trigger after-commit listeners. Never blindly enable fallback; write an integration test with a transaction manager testing both commit and rollback.

### Scenario 5. After upgrading the producer, an old consumer cannot read events

**How to answer:** Distinguish **Java API compatibility** from **wire schema compatibility**. Changing record constructors, deleting/renaming fields, changing currency units, and adding enum values can all break consumers. Version contracts, use adapters/upcasters and schema registries where suitable, upgrade consumers before producers, retain historical event fixtures, and test replays and type routing.

### Scenario 6. The interviewer asks to design an order/inventory/payment system using events

**How to answer:** Clarify domain boundaries and consistency first: within **one database/one service**, application services/transactions and application events suit decoupling secondary side effects; across **multiple services**, you need a broker/outbox and idempotent consumers. Inventory reservation or payment capture require mandatory outcomes and timeouts, so they typically call for workflow orchestration/sagas, compensation, and explicit state—not firing three events and hoping all succeed.

### Scenario 7. A listener runs twice in Spring Boot

**How to answer:** First check duplicate bean registrations, parent–child context hierarchies, duplicate publisher calls, self-replay logic, application restarts, and broker duplicates. Do not immediately blame the listener cache. Log `eventId`/`correlationId`, context ID, listener bean identity, and thread to locate the source.

### Scenario 8. A listener needs permission to access an order while the event contains `userId`

**How to answer:** `userId` or `claimedRole` in a payload is not Authentication proof. Enforce Spring Security/`@PreAuthorize` at the side-effect service, check owner/tenant against authoritative data, and use least-privilege service identities for background jobs. Under async, propagate `SecurityContext` properly or revalidate; never store expiring user tokens in event stores across replays.

## 9. Five Counter-Questions to Prove Deep Understanding

### "`@TransactionalEventListener(AFTER_COMMIT)` definitely sends the Kafka message after commit, right?"

**Wrong on "definitely".** The callback binds to the commit phase, yet sending to the broker can still fail or the process can die. If messages must not be lost, use an outbox and relay; consumers handle duplicates.

### "`@Order(1)` listener A and `@Order(2)` listener B means A always finishes before B?"

Only within matching synchronous dispatch. Once `@Async`/executors or downstream tasks exist, completion is no longer guaranteed by initial call order. If it is a business invariant, orchestrate explicitly.

### "Can `@EventListener(condition)` be used as an authorization mechanism?"

No. SpEL conditions filter event values, whereas authorization needs actor/source trust, object/tenant permissions, and policies at service/data boundaries. Event payloads may hold self-asserted data, not verified permissions.

### "Does Spring `publishEvent()` guarantee exactly-once processing within the same JVM?"

Do not phrase it that way. One call dispatches to matching listeners, yet exceptions, registration, context hierarchies, event chaining, application retries, and side effects complicate semantics. It is not a transactional exactly-once delivery API.

### "Does a record event containing a `List` make Spring split it into multiple events?"

Incorrect if `List` is **a field inside the record payload**. Spring only publishes multiple events automatically when an **`@EventListener` returns a `Collection`/array** via return-value publication. Distinguish a wrapper event holding a list from a method returning a list.

## 10. Mini Mock Interview: Self-Test in 10 Minutes

Use the set below for mock interviews. Answer each question aloud in 30–60 seconds, then compare against the sections above.

| Round | Question | Sign of a strong answer |
| --- | --- | --- |
| Junior | Can you publish arbitrary objects? | Yes, Spring uses `PayloadApplicationEvent` for objects not extending `ApplicationEvent`. |
| Junior | Are listeners synchronous? | Synchronous by default; `@Async`/executor config changes it. |
| Junior | How does `condition` access the first parameter? | `#p0` or `#a0`. |
| Mid | What happens when a listener throws an exception? | Can halt synchronous multicasting and propagate to publisher. |
| Mid | Why doesn't `AFTER_COMMIT` run? | No active transaction or mismatched phase; default fallback is false. |
| Mid | What happens when a listener returns a `List`? | Publishes each element as a new event if the listener is synchronous. |
| Mid | How do you register a listener for very early Boot events? | `SpringApplication.addListeners(...)` or `spring.factories`. |
| Senior | Send email only after DB commit without losing it? | Outbox + relay + idempotency; not `AFTER_COMMIT` alone. |
| Senior | Trace context lost under `@Async`? | Check executor/context propagation and correlation ID in the event. |
| Senior | Event versioning when schema changes? | Compatibility policy, migrations, adapters, fixture/replay tests. |
| Senior | Where is listener security enforced? | Trusted identity + method/object authorization at service boundaries. |
| Senior | When should you NOT use events? | Strict sequential logic, synchronous return results, durable cross-service steps. |

### Self-Scoring Criteria

- **Foundational pass:** accurately explains publisher -> multicaster -> listener, payload objects, and synchronous default.
- **Intermediate pass:** accurately describes conditions, return values, error handling, transaction phases, and async.
- **Advanced pass:** distinguishes consistency/delivery semantics from event dispatch; knows outbox, idempotency, security, schema evolution, and observability.
- **Design-level persuasive:** states conditional trade-offs, surfaces failure scenarios, and proposes integration/chaos tests to verify guarantees.

## 11. Pre-Interview Checklist of Common Traps

1. **"Spring events are async by default"** -> false: synchronous by default on the publisher's thread.
2. **"ApplicationEventPublisher is a mini Kafka"** -> false: no durable log, offsets, or retries.
3. **"Returning a Collection publishes one List as one event"** -> false: Spring publishes **each element** of the result.
4. **"`@Async` listeners can return events to chain publishing"** -> false: must call publisher explicitly.
5. **"`@Order` always guarantees completion order"** -> false under concurrency/async.
6. **"`@TransactionalEventListener` always runs even without a transaction"** -> false under default `fallbackExecution=false`.
7. **"`AFTER_COMMIT` is enough to reliably send emails/broker messages"** -> false: crash window still exists.
8. **"JDBC transactions automatically follow thread pools"** -> false: transaction context is usually thread-bound.
9. **"Any `@EventListener` bean hears `ApplicationStartingEvent`"** -> false because that event fires too early.
10. **"Adding a field or enum value is always backward-compatible"** -> false: depends on Java/wire/parser/semantic contracts.
11. **"Every event has at most one listener"** -> false: multiple matching listeners can receive it.
12. **"Receiving an event means the listener is authorized to act"** -> false: routing differs from authorization.
13. **"`eventId` equals `traceId`"** -> false: business occurrence differs from execution tracing.
14. **"Listener caching makes handlers run only the first time"** -> false: only candidate matching is cached.
15. **"Event sourcing only needs `@EventListener`"** -> false: lacks durable storage, replay, and versioning.
16. **"Seeing a listener run twice means the cache is broken"** -> insufficient evidence; check context hierarchy, registrations, and retries.
17. **"Knowing the method name determines the event type"** -> false: dispatch uses parameter types/signatures or annotations.
18. **"A unit test calling the listener directly tests `@EventListener(condition)`"** -> false: must publish through a Spring context.
19. **"If one listener fails, all side effects roll back"** -> false if emails/HTTP were called or separate DB transactions exist.
20. **"Using `@Async` gives automatic retries when a thread fails"** -> false: needs dedicated retry/idempotency and error tracking.

## 12. End-of-Lesson Practice Exercises

**Exercise 1.** Create an `OrderPlaced` event and two listeners, one with `@Order(1)` and one with `@Order(10)`. Observe stdout in sync mode, then add `@Async`. Explain why async log order must not be used to infer completion order.

**Exercise 2.** Create `@EventListener(condition = "#p0.totalMinorUnits() >= 10000")` and publish `9999`, `10000`, and `10001`. Verify the exact boundary with an integration test. Then intentionally change `>=` to `>` and explain which test catches the bug.

**Exercise 3.** In a project with a transaction manager, create an `@EventListener` and a `@TransactionalEventListener(AFTER_COMMIT)`. Publish from a `@Transactional` method, then commit and roll back in turn. Document which listener ran, when, and why.

**Exercise 4.** Try creating an `@Async @EventListener` returning `List<Object>`. Why is expecting Spring to publish the list invalid? Fix it with explicit `ApplicationEventPublisher.publishEvent(...)` and test completion using `CountDownLatch`.

**Exercise 5.** Design `PaymentCapturedV2` with `eventId`, `correlationId`, `amountMinorUnits`, and `currency`. Write an adapter reading V1 using **a contractually guaranteed legacy currency rule**, without inventing currencies. Explain how to prevent duplicate processing when V1 and V2 represent the same occurrence.

**Exercise 6.** Design a small outbox (describing only contract and transaction boundaries): when an order commits, the outbox record commits too. If the relay publishes twice, which key does the consumer deduplicate on? Which metrics must be watched to spot backlogs and failures?

**Exercise 7.** Write a test verifying that a listener with global authority is rejected when lacking permission for another tenant's `orderId`; emphasize that `actorId` in the payload is metadata, not authentication.

**Exercise 8.** Answer in at most 90 seconds: "Why should we use Spring Application Events for a metrics module inside a monolith, yet a broker/outbox for critical notifications to another service?" Your answer must cover **process boundaries**, **durable delivery**, **failure semantics**, and operational cost.

## References

- [Spring Framework Reference 6.2 — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html): `ApplicationEventPublisher`, `@EventListener`, SpEL, return values, async, ordering, and generic events.
- [Spring Framework 6.2.9 Javadoc — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html): `publishEvent(Object)` and publication limits.
- [Spring Framework 6.2.9 Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): synchronous default, executor, and error handler.
- [Spring Framework Reference 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html): `@TransactionalEventListener`, phases, fallback, reactive context.
- [Spring Boot 3.5 — SpringApplication Events](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): lifecycle events and early listener registration.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): tracing context in event handlers, `ContextPropagatingTaskDecorator`.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity` and `@PreAuthorize` for business services.
