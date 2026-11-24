# Differences Between ThreadLocal and Reactor Context in Reactive Transaction Events

## 1. Why does event handling in reactive transactions need a different way to hold context?

In a traditional Spring application, a `@Transactional` method can update data and then call `ApplicationEventPublisher.publishEvent(...)`. With synchronous transactions managed by `PlatformTransactionManager`, Spring binds transaction state to the **currently executing Java thread**. Synchronous listeners typically run on the same thread, so they can see the transaction context bound to that thread.

In a WebFlux/R2DBC application using Reactor, however, a `Mono` or `Flux` chain can resume on another thread after `publishOn(...)`, `subscribeOn(...)`, or an asynchronous I/O operation. Threads are reused across many tasks, so "which thread is running right now?" no longer reliably identifies a reactive chain's transaction.

Spring solves this with **Reactor Context**: context attached to the **subscriber/subscription of the reactive chain**, not to thread identity. `ReactiveTransactionManager` stores and retrieves transaction information through this context. Since Spring Framework 6.1, `@TransactionalEventListener` also supports reactive transactions, provided that when publishing an event the transaction context is placed into the **event source** so the listener can identify the right transaction.

Conceptual flow:

~~~text
Imperative (e.g., Spring MVC + JDBC/JPA)

Thread T1
  |
  +-- @Transactional -> PlatformTransactionManager
  |      +-- TransactionSynchronizationManager (thread-bound)
  |
  +-- repository.save(...)
  +-- publishEvent(event)
           +-- @TransactionalEventListener registers with T1's transaction
  |
  +-- commit / rollback on T1's transaction


Reactive (e.g., WebFlux + R2DBC)

Subscription S1 + Reactor Context containing TransactionContext
  |
  +-- @Transactional Mono/Flux -> ReactiveTransactionManager
  +-- databaseClient.sql(...).then(...)
  |
  +-- may switch threads T1 -> T2, still belongs to Subscription S1
  |
  +-- TransactionalEventPublisher.publishEvent(payload)
           +-- event carries S1's TransactionContext in source
           +-- @TransactionalEventListener registers with S1's transaction
  |
  +-- pipeline completes -> commit / rollback
~~~

**Decisive point:** `ThreadLocal` follows the thread, whereas `Reactor Context` follows the **subscriber chain**. Switching threads does not inherently lose Reactor Context; however, creating an independent subscription does not automatically inherit the original subscription's context either.

## 2. What is ThreadLocal? How does Spring use it?

`java.lang.ThreadLocal<T>` lets each thread hold its own value for the same variable:

~~~java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

public void handleRequest() {
    REQUEST_ID.set("req-123");
    try {
        // Code running on this current thread can read REQUEST_ID.get().
    } finally {
        REQUEST_ID.remove(); // Avoid leaking leftover data in a thread pool.
    }
}
~~~

The snippet above illustrates a custom variable, **not** code for creating a Spring transaction. For imperative transactions, Spring uses `org.springframework.transaction.support.TransactionSynchronizationManager` to hold thread-bound resources and transaction synchronizations. `PlatformTransactionManager` is responsible for setting up and cleaning up that context when the transaction begins, commits, or rolls back.

Because `ThreadLocal` belongs to **each thread**, the following scenarios have consequences:

- Direct method calls on the same thread can usually still access ThreadLocal.
- Handing work off to a new thread or another executor does not automatically copy regular `ThreadLocal` values.
- Threads in a pool are reused, so using ThreadLocal manually and forgetting `remove()` can leak data from a previous task into a subsequent one.
- `InheritableThreadLocal` only supports conditional inheritance when creating child threads; it does not generally solve hand-offs across existing pooled threads and is not a reactive transaction management solution.

**Not every Spring call automatically has a transaction.** `ThreadLocal` is only where the framework stores context for an active imperative transaction. Creating an arbitrary `ThreadLocal`, or checking the current thread, does not create a transaction and does not guarantee a commit.

## 3. How does Reactor Context work?

In Project Reactor, `reactor.util.context.Context` is an **immutable** set of key-value pairs; `put(...)` returns a new Context. `ContextView` allows reading the context. Context is associated with the subscriber and propagated via Reactor's subscription mechanism.

Two foundational APIs:

- `contextWrite(...)`: adds/modifies context for the appropriate portion of the reactive chain at subscription time.
- `Mono.deferContextual(ctx -> ...)`: retrieves the `ContextView` present when that segment of the chain executes.

Minimal example:

~~~java
Mono<String> greeting = Mono.deferContextual(ctx ->
        Mono.just("Hello " + ctx.get("user")))
    .contextWrite(ctx -> ctx.put("user", "Lan"));
~~~

*Illustrative code snippet placed in a program with Reactor Core; `Mono` is `reactor.core.publisher.Mono`.*

When subscribed to, the chain above emits `"Hello Lan"`. Even though `contextWrite(...)` appears lower down in the written chain, context information flows from the subscriber upward to upstream operators during the subscribe phase. This explains why **the position of `contextWrite(...)` matters**; placing it on a different branch or too early in the chain does not mean every operator sees the same value.

Another subscription on a publisher without an appropriate context write may not find the `"user"` key. Reactor Context is **not a global variable** and is not an automatic copy of every ThreadLocal.

### Key comparison table

| Criterion | `ThreadLocal` | `Reactor Context` |
| --- | --- | --- |
| Where context is attached | Current `Thread` instance. | `Subscriber` / subscription in the reactive pipeline. |
| Typical APIs | `set`, `get`, `remove`. | `contextWrite`, `deferContextual`, `ContextView.get`. |
| Switching to another thread | Regular ThreadLocal is not automatically inherited. | Still accessible if execution stays within the chain and appropriate Context scope. |
| Independent reactive chains | May run on the same thread without sharing business context. | Has its own subscription/context; does not automatically carry another chain's context. |
| How values change | Mutates value for the current thread. | Produces a new Context; visibility follows chain structure. |
| Spring transaction problem | `PlatformTransactionManager`, JDBC/JPA. | `ReactiveTransactionManager`, R2DBC, and matching reactive APIs. |
| Common pitfall | Believing another executor still sees the transaction. | Believing every new `subscribe()` or `block()` reuses the current transaction. |

## 4. Runnable Java 17+ example: switching threads and comparing two contexts

This example **only uses an illustrative `flowId` key** to demonstrate the context storage mechanism; it **does not create a real transaction**. For real Spring reactive transactions, an application must use `ReactiveTransactionManager` and reactive resources such as R2DBC.

Create the structure:

~~~text
context-comparison/
├── pom.xml
└── src/main/java/ContextComparisonDemo.java
~~~

Contents of `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>context-comparison</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.11</version>
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

Contents of `src/main/java/ContextComparisonDemo.java`:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.util.context.Context;

public class ContextComparisonDemo {

    private static final ThreadLocal<String> THREAD_VALUE = new ThreadLocal<>();

    public static void main(String[] args) {
        THREAD_VALUE.set("thread-main");
        Scheduler worker = Schedulers.newSingle("context-worker");

        try {
            System.out.println("Main ThreadLocal: " + THREAD_VALUE.get());

            String result = Mono.just("order-1")
                .publishOn(worker)
                .flatMap(orderId -> Mono.deferContextual(ctx ->
                    Mono.just(orderId
                        + " | ThreadLocal=" + THREAD_VALUE.get()
                        + " | ReactorContext=" + ctx.get("flowId"))))
                .contextWrite(Context.of("flowId", "subscription-42"))
                .block();

            System.out.println(result);

            String outside = Mono.deferContextual(ctx ->
                Mono.just(ctx.getOrDefault("flowId", "absent")))
                .block();

            System.out.println("New subscription: " + outside);
        } finally {
            THREAD_VALUE.remove();
            worker.dispose();
        }
    }
}
~~~

Run with Java 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ContextComparisonDemo
~~~

Stdout printed by the program in this standalone example (excluding Maven's own messages):

~~~text
Main ThreadLocal: thread-main
order-1 | ThreadLocal=null | ReactorContext=subscription-42
New subscription: absent
~~~

**Why does this output occur?**

1. `THREAD_VALUE.set("thread-main")` only sets a value for the thread calling `main`.
2. `Schedulers.newSingle(...)` creates a scheduler backed by another thread. The `publishOn(worker)` operator runs the downstream segment on this scheduler. Regular ThreadLocal on the new thread lacks the value set on `main`, so `get()` returns `null`.
3. `contextWrite(Context.of("flowId", "subscription-42"))` adds the `flowId` key to the pipeline's subscription. `Mono.deferContextual(...)` reads that value even though the code is running on the worker thread.
4. The second `Mono.deferContextual(...).block()` call creates a different subscription with no `contextWrite(...)` setting `flowId`, so it reads `"absent"`.

**Do not infer from this example that `ThreadLocal` is always `null` in every reactive application.** A framework can actively copy certain values via context propagation mechanisms. The example demonstrates Reactor Core's default behavior with a custom ThreadLocal and **no bridge configured**; the fundamental difference remains where context is stored and its lifetime scope.

## 5. Which transaction manager does Spring choose?

Spring has two transaction management models using different APIs:

| Model | Transaction manager | State store |
| --- | --- | --- |
| Imperative, e.g., JDBC/JPA | `PlatformTransactionManager`, such as `DataSourceTransactionManager` or `JpaTransactionManager`. | `ThreadLocal` managed by `org.springframework.transaction.support.TransactionSynchronizationManager`. |
| Reactive, e.g., R2DBC | `ReactiveTransactionManager`, such as `R2dbcTransactionManager`. | `TransactionContext` in Reactor subscriber context, accessed via reactive transaction APIs. |

For reactive transactions, there is **`org.springframework.transaction.reactive.TransactionSynchronizationManager`** (a different package from the imperative class of the same name) and `TransactionContextManager`. For example, `TransactionContextManager.currentContext()` returns `Mono<TransactionContext>`, letting you obtain the transaction context from the current subscriber; if the transaction context is missing, it emits an appropriate error.

Do not use the synchronous `TransactionSynchronizationManager.isActualTransactionActive()` API from `org.springframework.transaction.support` to conclude whether a reactive transaction exists. That API inspects thread-bound state, whereas a reactive transaction is stored in the subscription's context.

When applying `@Transactional`:

- For synchronous methods returning a normal value or `void`, Spring uses the imperative transaction management flow and requires an appropriate `PlatformTransactionManager`.
- For methods returning `Mono`, `Flux`, or a Reactive Streams `Publisher` and using `ReactiveTransactionManager`, Spring opens the transaction when the pipeline is **subscribed** to, not merely when constructing the `Mono` object.
- Data operations that should participate in the same reactive transaction must reside in the same appropriate pipeline/context and use transaction-aware reactive data APIs such as `DatabaseClient` or R2DBC repositories.

Calling blocking JPA/JDBC inside a `Mono` does not turn it into an R2DBC operation nor make it participate in a reactive transaction. If an application uses both JDBC/JPA and R2DBC, you must choose clear transaction managers and processing boundaries for each side.

## 6. Why do reactive transaction events need TransactionContext as the event source?

This is the direct link to Spring Application Events.

In the imperative case, the multicaster invokes a `@TransactionalEventListener` while the current thread still has transaction synchronization. The listener adapter can rely on the transaction context **bound to the current thread** to register the callback for the right phase.

In the reactive case, when Spring receives an event via the `ApplicationEventPublisher` API (a plain API returning `void`), **Reactor Context does not automatically appear as a ThreadLocal on the current thread**. Therefore, Spring requires `TransactionContext` to be placed in `ApplicationEvent.getSource()` of the published event if a listener is to bind to the reactive transaction.

Since Spring Framework 6.1, `org.springframework.transaction.reactive.TransactionalEventPublisher` helps construct events properly:

~~~java
@Bean
TransactionalEventPublisher transactionalEventPublisher(
        ApplicationEventPublisher delegate) {
    return new TransactionalEventPublisher(delegate);
}
~~~

*This is a configuration bean placed inside a `@Configuration` class, not a complete application. Import `org.springframework.context.ApplicationEventPublisher`, `org.springframework.transaction.reactive.TransactionalEventPublisher`, and `org.springframework.context.annotation.Bean`.*

There are two main ways to call it:

~~~java
// Simple: pass a payload that does not extend ApplicationEvent.
Mono<Void> eventTask = transactionalEventPublisher.publishEvent(
        new OrderCreated("ORD-7"));

// Custom event: receive TransactionContext as the source.
Mono<Void> customEventTask = transactionalEventPublisher.publishEvent(
        source -> new OrderCreatedApplicationEvent(source, "ORD-7"));
~~~

*`OrderCreated` is a payload record and `OrderCreatedApplicationEvent` is a custom `ApplicationEvent` class defined by the application; this is an API illustration snippet, not a standalone program.*

For a regular payload, the publisher wraps it into a `PayloadApplicationEvent` with **`TransactionContext` as source**. For a custom event extending `ApplicationEvent`, use the function-accepting overload to supply the source; do not pass an `ApplicationEvent` object directly into the `publishEvent(Object)` overload because that overload is meant for payloads and can reject `ApplicationEvent`.

**Important:** `TransactionalEventPublisher.publishEvent(...)` returns a `Mono<Void>`. If you just call the method and ignore the `Mono`, the publishing work is not subscribed to and **does not actually execute**. You must attach the publisher to an executing pipeline, for example using `then(...)`.

## 7. Spring R2DBC pattern: publishing an event inside a reactive transaction

This is an **illustrative integration snippet** for a Spring Framework/Spring Boot application already configured with R2DBC, `ReactiveTransactionManager`, the `TransactionalEventPublisher` bean from section 6, and an `orders` table. It is not a standalone Maven program; an immediately runnable Java 17+ example is in section 4.

~~~java
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.reactive.TransactionalEventPublisher;
import reactor.core.publisher.Mono;

record OrderCreated(String id) {}

@Service
class ReactiveOrderService {

    private final DatabaseClient db;
    private final TransactionalEventPublisher events;

    ReactiveOrderService(DatabaseClient db,
                         TransactionalEventPublisher events) {
        this.db = db;
        this.events = events;
    }

    @Transactional
    public Mono<Void> createOrder(String id) {
        return db.sql("INSERT INTO orders(id, status) VALUES (:id, :status)")
            .bind("id", id)
            .bind("status", "CREATED")
            .fetch()
            .rowsUpdated()
            .then(events.publishEvent(new OrderCreated(id)));
    }
}

@Component
class OrderCommittedListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreated event) {
        System.out.println("Committed order " + event.id());
    }
}
~~~

### Processing flow explanation

1. The application calls `reactiveOrderService.createOrder("ORD-7")` **through the Spring proxy** and actually subscribes to the pipeline, such as in a WebFlux controller by returning the `Mono` to the framework. Creating the `Mono` alone executes neither SQL nor event publishing.
2. The `@Transactional` interceptor and `ReactiveTransactionManager` attach `TransactionContext` to the Reactor subscriber context.
3. `DatabaseClient` executes the `INSERT` using an R2DBC connection within the reactive transaction.
4. `then(events.publishEvent(new OrderCreated(id)))` causes event publication to occur **after the `INSERT` succeeds and before the transaction pipeline finishes/commits**, within the same reactive context. Thus the listener is registered with the active transaction.
5. `TransactionalEventPublisher` retrieves the current transaction context, builds a `PayloadApplicationEvent` with that context as source, and passes it to `ApplicationEventPublisher`.
6. `@TransactionalEventListener(AFTER_COMMIT)` is invoked when the transaction completes with a successful commit; on rollback, this phase's listener does not run.

Because the event is published **before commit** while the listener is registered for **after commit**, you must distinguish publication time from callback execution time. This is the core behavior of transaction-bound events.

### What if you use ApplicationEventPublisher directly?

Replacing `events.publishEvent(...)` with:

~~~java
Mono.fromRunnable(() ->
        applicationEventPublisher.publishEvent(new OrderCreated(id)));
~~~

*This illustrative snippet only shows how to wrap a synchronous API in a pipeline; it does not guarantee transactional event semantics.*

Placing a regular event-publishing operation inside `Mono.fromRunnable(...)` **does not automatically attach `TransactionContext` to the event source**. `@TransactionalEventListener` for reactive transactions may therefore fail to find a valid transaction and skip the event (when `fallbackExecution` defaults to `false`). Use `TransactionalEventPublisher` or manually create an `ApplicationEvent` whose source is `TransactionContext` if you truly need reactive transaction phase callbacks.

## 8. Reactor Context does not mean all threads/branches share a transaction

Reactor Context follows the subscription and operator scope; it is **not an application-wide global data store**. Understand these cases:

| Operation | Impact to note |
| --- | --- |
| `publishOn(...)` / `subscribeOn(...)` in the pipeline | May switch threads; the appropriate context still follows the reactive subscriber/pipeline. |
| `contextWrite(...)` | Only takes effect for the portion of the chain allowed to see the context; operator placement is crucial. |
| `flatMap(...)` creating an inner publisher | The inner publisher can receive context from the current subscription when composed properly; context written locally in one branch does not automatically spread to sibling branches. |
| Calling `subscribe()` manually inside a service | Creates a separate subscription that does not automatically keep the running pipeline's transaction; makes control flow hard to manage. |
| Calling `block()` in the middle of reactive code | Can create a separate subscription/execution boundary and block the thread, defeating non-blocking execution; avoid in WebFlux/R2DBC pipelines. |
| `CompletableFuture` or a plain executor | Does not automatically carry Reactor subscriber context to a Java task detached from the pipeline unless an explicit context-transfer mechanism is used. |
| Micrometer Context Propagation mechanism | Can bridge certain context values with ThreadLocal when configured appropriately; this is selective bridging, not moving reactive transaction storage back to ThreadLocal. |

To bring additional logic into the same transaction, **compose** the required `Mono`/`Flux` values and let Spring manage the subscription. For example:

~~~java
return repository.save(order)
    .flatMap(saved -> eventPublisher.publishEvent(
        new OrderCreated(saved.getId())).thenReturn(saved));
~~~

*This is an illustrative snippet inside a method managed by `@Transactional`; `repository` is a reactive repository and `eventPublisher` is `TransactionalEventPublisher`.*

Do not write:

~~~java
repository.save(order).subscribe();
eventPublisher.publishEvent(new OrderCreated(order.getId())).subscribe();
return Mono.empty();
~~~

The poorly designed snippet above creates two independent subscriptions and returns a different pipeline, leaving save/publish ordering, transaction boundaries, and errors uncontrolled. It may also publish events outside the reactive transaction.

## 9. Distinguishing Reactor Context, TransactionContext, and event source

Three closely related concepts have distinct roles:

**Reactor Context** is the key-value storage mechanism attached to a subscriber. Users can store `requestId`, tenant name, or data read across operators via `contextWrite(...)`.

**Spring TransactionContext** is an internal object holding reactive transaction state, resources, and synchronizations. Spring `ReactiveTransactionManager` coordinates it inside the Reactor Context; applications normally do not create a `TransactionContext` and place it into Reactor Context manually to simulate a transaction.

**Event source** is the built-in field on `ApplicationEvent` (`getSource()`). Spring uses a `TransactionContext` source so transaction-bound listeners can register synchronization with the **original reactive transaction** when the event travels through the regular event API.

~~~text
Reactor subscriber Context (S1)
    |
    +-- application key: requestId=R-10
    |
    +-- Spring TransactionContext
            |-- resource: R2DBC connection
            |-- transaction state / synchronizations
            |
            +--> TransactionalEventPublisher
                      |
                      +--> PayloadApplicationEvent(
                               source = TransactionContext,
                               payload = OrderCreated(...))
                                    |
                                    +--> @TransactionalEventListener
                                         registers callback by phase
~~~

Do not confuse event source with business payload. When using `TransactionalEventPublisher.publishEvent(new OrderCreated(id))`, a listener can still declare an `OrderCreated` parameter because Spring extracts the payload via `PayloadApplicationEvent`. The source is for the framework to identify the transaction.

## 10. Effects on errors, rollback, and AFTER_COMMIT callbacks

With `@TransactionalEventListener`, the default is `phase = AFTER_COMMIT`. Other phases are `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`.

- If an `INSERT` in the reactive pipeline fails and causes the transaction to roll back, a listener registered only for `AFTER_COMMIT` will not run.
- If an error occurs **before** the publisher Mono executes, the event has not been published and no callback is registered.
- If the event is published outside a transaction and `fallbackExecution` remains at its default `false`, the listener does not run.
- If post-commit processing throws an error or the process stops, Application Events do not provide a durable queue or replay guarantee. Do not design mandatory business workflows relying solely on in-memory callbacks.

In particular, being invoked **after commit** (`AFTER_COMMIT`) does not allow the old transaction to commit again. With some transaction managers, resources might still be accessible during completion callbacks; if you need to write new data, create an independent reactive-supported transaction and compose the handling properly. Do not port `ThreadLocal` style to reactive by copying a variable and assuming a fresh commit occurred.

`@TransactionalEventListener` binds **when** to react to a transaction. It does not by itself imply asynchronous processing or delivery guarantees. Which thread the listener runs on and whether the work is durable are separate concerns.

## 11. Common errors and how to fix them

1. **Using imperative transaction APIs in a reactive flow.** For example, calling `org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive()` and concluding "there is no transaction" while R2DBC actually has a reactive transaction. Use reactive APIs and observe the pipeline subscription in the right place.
2. **Believing the same thread means the same transaction.** A thread pool can execute many independent subscriptions on one thread at different times; transaction identity is based on subscriber context, not thread name.
3. **Believing switching threads always loses the transaction.** For Reactor operators remaining within the same chain/context, switching threads is not a reason to lose a reactive transaction.
4. **Ignoring the `Mono<Void>` returned by `TransactionalEventPublisher.publishEvent(...)`.** Without a subscription, publishing does not run. Use `then(...)`, `flatMap(...)`, or equivalent composition.
5. **Publishing events with a regular publisher without a transaction source.** Reactive `@TransactionalEventListener` may fail to register callbacks; use `TransactionalEventPublisher`.
6. **Calling `subscribe()` manually inside a `@Transactional` method.** The new subscription may run outside the intended transaction boundary; connect all operations into the pipeline managed by the transaction manager.
7. **Calling blocking JPA/JDBC in a reactive chain and expecting it to join the R2DBC transaction.** The two models have different transaction managers and resources; use matching data APIs or design explicit transition boundaries.
8. **Assuming `Context.put(...)` creates a transaction.** Context can hold any arbitrary keys; a real transaction must be opened and managed by `ReactiveTransactionManager`.
9. **Treating post-commit callbacks as a reliable queue.** If cross-process event transfer, retries, and avoiding event loss on process shutdown are needed, consider a transactional outbox and an appropriate broker.

## 12. Self-check

**Question 1.** An R2DBC pipeline using `@Transactional` switches from thread A to B via `publishOn(...)`. Must it necessarily lose the transaction?

**Answer:** No. The reactive transaction resides in the pipeline/subscription's Reactor Context and does not depend on staying on thread A.

**Question 2.** Do two subscriptions running sequentially on the same thread pool automatically share a transaction?

**Answer:** No. Same thread does not mean same subscriber context; each subscription has its own scope.

**Question 3.** Why might `applicationEventPublisher.publishEvent(new OrderCreated(id))` inside a reactive pipeline fail to trigger `@TransactionalEventListener(AFTER_COMMIT)`?

**Answer:** A regular event does not automatically contain `TransactionContext` as its source, whereas a transaction-bound listener needs that context source to register the callback with the reactive transaction. Use `TransactionalEventPublisher` or construct the event source properly.

**Question 4.** `transactionalEventPublisher.publishEvent(payload)` returns `Mono<Void>`. What happens if you call it without attaching it to the pipeline?

**Answer:** A Mono is a description of work; without being subscribed to, the event-publishing operation is not executed.

**Question 5.** Can you call `ThreadLocal.set(...)` and assume Spring has created a reactive transaction?

**Answer:** No. A reactive transaction must be opened and managed by `ReactiveTransactionManager`; state is bound to the Reactor subscriber context. Custom ThreadLocal values do not create transactions.

**Question 6.** In the Java 17+ example, why is `ThreadLocal=null` while `ReactorContext=subscription-42`?

**Answer:** `publishOn` switches processing to a separate thread that does not have the ThreadLocal assigned. The Context was set by `contextWrite` and remains visible within the subscription across the thread switch.

## References

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` with imperative and reactive transactions; event source requirement for reactive.
- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): `PlatformTransactionManager`/`ReactiveTransactionManager` and where transaction state is held.
- [Spring Framework Javadoc — TransactionalEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html): the two `publishEvent(...)` overloads and how `TransactionContext` is attached as event source.
- [Spring Framework Javadoc — TransactionContextManager](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/transaction/reactive/TransactionContextManager.html): accessing the reactive transaction context.
- [Project Reactor Reference — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/3.6.11/reference/advancedFeatures/context.html): `Context`, `contextWrite`, `deferContextual`, and subscriber scope.
- [Spring Blog — Reactive Transactions with Spring](https://spring.io/blog/2019/05/16/reactive-transactions-with-spring/): why ThreadLocal is unsuitable for holding reactive transactions.
