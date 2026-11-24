# Filtering Listeners with Conditions in Spring Framework Application Events

## 1. Context and Objectives

Within the **Practice and Summary** group of **Spring Framework Application Events**, a very practical question arises: an application publishes the same `OrderPlaced` event for every order, yet wants certain listeners to react only when **the order has high value**, when **the order comes from the WEB channel**, or when **the order qualifies for a notification**. Is it always necessary to create a separate event class and an `if` check method for each case?

Spring supports the `condition` attribute on `@EventListener` to write a **Spring Expression Language (SpEL)** expression. The expression is evaluated for matching events; only when the condition evaluates to `true` is the listener method invoked. This allows you to express a small, explicit filter right at the registration point.

Example:

```java
@EventListener(condition = "#a0.totalCents() >= 100000")
public void onHighValueOrder(OrderPlaced event) {
    // Runs only when the order total is at least 100,000 minor currency units.
}
```

This is an **illustrative snippet**, assuming `OrderPlaced` is a record/class with a `totalCents()` method. The value `100000` is measured in **the minor currency unit** defined in the demo system, not a fixed exchange rate or a default currency.

This lesson targets the following capabilities:

1. Understand the order of **listener selection by event type** followed by **SpEL condition evaluation**.
2. Correctly use `#a0`, `#p0`, `#root.args[0]`, and parameter names when metadata is available.
3. Know the limits of `condition` regarding security, reliability, transactions, and async execution.
4. Distinguish annotation-based filtering from `if` checks inside handlers, or creating separate event types.
5. Run a **Java 17+ / Spring Framework 6.1** example and verify exactly which listeners execute.
6. Write unit/integration tests for true branches, false branches, boundary values, invalid input, and the effects of multicaster configuration.
7. Avoid expensive SpEL expressions, expressions depending on mutable state, or expressions causing side effects.

**Short rule:** `@EventListener(condition = "...")` is a **callback execution filter**, not an authorization boundary and not a filter at the database or message broker.

## 2. How Spring Selects and Invokes Listeners

Conceptual flow:

```text
ApplicationEventPublisher.publishEvent(event)
                  |
                  v
       ApplicationEventMulticaster
                  |
        Filter by event type
                  |
      Select matching listeners
                  |
        For @EventListener adapter:
                  |
          Evaluate SpEL condition
              /             \
           true             false
            |                 |
   Invoke listener method   Skip method
            |
       Business logic
```

Suppose the application has three listeners for the same `OrderPlaced` type:
- `onEveryOrder`: no `condition`.
- `onHighValueOrder`: condition total amount >= 100000.
- `onWebOrder`: condition order channel equals `"WEB"`.

When publishing a small order from WEB, Spring identifies all three adapters belonging to `OrderPlaced`. Then, `onHighValueOrder`'s condition evaluates to false so **the method body does not run**, while `onWebOrder`'s condition is true so the WEB handler runs.

### Two Different Levels of Filtering

| Level | What does Spring decide? | Timing and cost |
| --- | --- | --- |
| **Event-type matching** | Does the listener accept this event type? | Candidate selection by multicaster/adapter; may cache by event type/source |
| **Condition matching** | Does this specific event satisfy the expression? | Evaluated at runtime for each candidate event |
| **Business guard in method** | Should the operation proceed after domain checks? | Once the method has been invoked |
| **Authorization** | Does the caller have permission to execute the action? | Must be enforced at trusted service/consumer boundaries |

A SpEL condition does not turn a listener into a remotely broker-filtered subscription. The event is still published inside the Spring context, and other listeners can still receive it. `condition=false` only prevents **that callback** from executing.

### Event Type Does Not Replace Event State

An `@EventListener(OrderPlaced.class)` listener filters by event *type*. `condition="#a0.totalCents() >= 100000"` filters by *data inside the received instance*. Separating these two decisions keeps code readable, though if a state represents **a distinctly different business fact**, creating a dedicated event type may still be more appropriate.

## 3. `@EventListener(condition)` Syntax

General form:

```java
@EventListener(condition = "<SpEL expression returns boolean>")
public void handle(MyEvent event) {
    // ...
}
```

This is a **syntax template**; the placeholder `<SpEL expression returns boolean>` explains where the expression goes, not a literal value to use in a project. In actual runnable code, replace it with a SpEL expression like the examples below.

A standard `@EventListener` method has **at most one event parameter**. If you want a zero-argument listener, you must specify the event classes via the annotation; however, an expression relying on `#a0` will then have no method argument and will not fit. For payload-based filtering, **declaring one typed event parameter** is the simplest choice.

### 3.1. Using `#a0` or `#p0` by Parameter Position

```java
@EventListener(condition = "#a0.totalCents() >= 100000")
public void handleHighValue(OrderPlaced event) {
    // ...
}

@EventListener(condition = "#p0.channel() == 'WEB'")
public void handleWeb(OrderPlaced event) {
    // ...
}
```

`#a0` and `#p0` both refer to **the first parameter** (index 0) of the listener method. They do not depend on whether parameter names are retained in bytecode.

- `#a0.totalCents()`: calls the `totalCents()` accessor on the event.
- `>= 100000`: numeric comparison.
- `#p0.channel() == 'WEB'`: string comparison using the SpEL operator.
- SpEL string literals use single quotes `'WEB'`.
- The condition should return a boolean (or a result cleanly convertible to boolean), without relying on ambiguous types.

**When using a Java record**, call the accessors explicitly like `totalCents()` and `channel()`, avoiding confusing record accessors with JavaBean getters like `getTotalCents()` if the class does not define such getters.

### 3.2. Using `#root.args[0]`

Spring provides an expression root object containing invocation-related information:

```java
@EventListener(
    condition = "#root.args[0].channel() == 'WEB'"
)
public void onWebOrder(OrderPlaced event) {
    // ...
}
```

`#root.args` holds the arguments passed to the listener method. With a single-parameter listener as here, `#root.args[0]` is `OrderPlaced`.

You may encounter `#root.event` in documentation on Spring event expressions. **Do not always assume `#root.event` is the POJO payload**: when code publishes a plain object that does not extend `ApplicationEvent`, Spring can wrap it in `PayloadApplicationEvent`. Therefore, `#a0` or `#root.args[0]` is clearer and more reliable when accessing the declared method parameter directly.

### 3.3. Using the Parameter Name (When Metadata Is Available)

```java
@EventListener(condition = "#event.channel() == 'WEB'")
public void onWebOrder(OrderPlaced event) {
    // ...
}
```

This is an **integration snippet** that depends on Spring knowing the Java parameter name `event`, for instance via compiling with the `-parameters` flag and a supporting environment. If parameter names are unavailable, the expression may fail or fail to resolve the variable. To keep demos and libraries independent of build flags, use `#a0` or `#p0`.

### 3.4. Commonly Used Boolean Operators

| Operator | Example | Meaning |
| --- | --- | --- |
| `==` / `eq` | `#a0.channel() == 'WEB'` | Equal |
| `!=` / `ne` | `#a0.channel() != 'POS'` | Not equal |
| `>=` / `ge` | `#a0.totalCents() >= 100000` | Greater than or equal |
| `>`, `<`, `<=` | `#a0.totalCents() < 50000` | Numeric comparison |
| `and` | `#a0.totalCents() >= 100000 and #a0.channel() == 'WEB'` | Both true |
| `or` | `#a0.channel() == 'WEB' or #a0.channel() == 'APP'` | Either true |
| `!` / `not` | `!#a0.cancelled()` | Boolean negation |
| `?.` | `#a0.customer()?.tier() == 'GOLD'` | Null-safe property/method navigation in SpEL |

**Note:** some expressions like `#a0.customer()?.tier()` are integration examples requiring an actual model with those accessors. Do not include such an expression in a demo if the model does not match.

In SpEL, `and`/`or` short-circuit according to boolean semantics. Still, avoid relying on getters with side effects just because one branch is normally skipped.

### 3.5. Do Not Use `#` for Literals or Operators

Wrong:

```java
@EventListener(condition = "#a0.channel() == #WEB")
```

Because `#WEB` is interpreted as a variable in the evaluation context, **not** the string `"WEB"`. Right:

```java
@EventListener(condition = "#a0.channel() == 'WEB'")
```

These are illustrative lines, not complete Java files.

## 4. Order Example: Multiple Conditions on the Same Event

Suppose the event is:

```java
public record OrderPlaced(
    String orderId,
    long totalCents,
    String channel
) {}
```

And three listeners:

```java
@EventListener
public void everyOrder(OrderPlaced event) {
    // Always invoked for OrderPlaced.
}

@EventListener(condition = "#a0.totalCents() >= 100000")
public void highValue(OrderPlaced event) {
    // Only orders >= 100000.
}

@EventListener(condition = "#a0.channel() == 'WEB'")
public void webOrder(OrderPlaced event) {
    // Only orders from the WEB channel.
}
```

These are integration snippets. They demonstrate that `condition` is evaluated **independently** on each listener: an order can match both high-value and WEB conditions, only one of them, or neither while still being processed by `everyOrder`.

### Truth Table

| Event | totalCents | channel | everyOrder | highValue | webOrder |
| --- | ---: | --- | :---: | :---: | :---: |
| ORD-1 | 50000 | WEB | Yes | No | Yes |
| ORD-2 | 150000 | POS | Yes | Yes | No |
| ORD-3 | 200000 | WEB | Yes | Yes | Yes |
| ORD-4 | 99999 | POS | Yes | No | No |
| ORD-5 | 100000 | APP | Yes | Yes | No |

Boundary values matter greatly: `100000` must match when the expression uses `>= 100000`; `99999` must not.

**For monetary data**, the record in the example stores integers in minor units (`long totalCents`) to avoid floating-point rounding traps in conditions. If production uses `BigDecimal`, standardize units, compare with compatible types, and verify currency/tax/discount semantics before writing conditions.

## 5. Runnable Java 17+ Example with Spring Framework 6.1.21

We build a minimal Spring Context application **without Spring Boot, a web server, a database, or an external broker**. The program creates an `AnnotationConfigApplicationContext`, registers a bean with three handlers, publishes three events, and prints the list of order IDs each handler actually received.

### 5.1. Project Structure

```text
conditional-event-listeners/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ConditionalEventListenersDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'conditional-event-listeners'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
}

application {
    mainClass = 'demo.ConditionalEventListenersDemo'
}
```

Requires **JDK 17+**, Gradle, and access to download dependencies from Maven Central.

### 5.2. Complete Java File

`src/main/java/demo/ConditionalEventListenersDemo.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class ConditionalEventListenersDemo {

    public record OrderPlaced(
        String orderId,
        long totalCents,
        String channel
    ) {}

    public static final class OrderListeners {
        private final List<String> allOrders = new ArrayList<>();
        private final List<String> highValueOrders = new ArrayList<>();
        private final List<String> webOrders = new ArrayList<>();

        @EventListener
        public void onEveryOrder(OrderPlaced event) {
            allOrders.add(event.orderId());
        }

        @EventListener(
            condition = "#a0.totalCents() >= 100000"
        )
        public void onHighValueOrder(OrderPlaced event) {
            highValueOrders.add(event.orderId());
        }

        @EventListener(
            condition = "#a0.channel() == 'WEB'"
        )
        public void onWebOrder(OrderPlaced event) {
            webOrders.add(event.orderId());
        }

        public void printReport() {
            System.out.println("ALL=" + allOrders);
            System.out.println("HIGH=" + highValueOrders);
            System.out.println("WEB=" + webOrders);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public OrderListeners orderListeners() {
            return new OrderListeners();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            context.publishEvent(
                new OrderPlaced("ORD-1", 50000, "WEB")
            );
            context.publishEvent(
                new OrderPlaced("ORD-2", 150000, "POS")
            );
            context.publishEvent(
                new OrderPlaced("ORD-3", 200000, "WEB")
            );

            context.getBean(OrderListeners.class).printReport();
        }
    }
}
```

Run:

```bash
gradle run --quiet
```

**Expected business stdout**:

```text
ALL=[ORD-1, ORD-2, ORD-3]
HIGH=[ORD-2, ORD-3]
WEB=[ORD-1, ORD-3]
```

These results can be cross-checked against the truth table in Section 4.

### 5.3. Mechanism Explanation

1. `@Configuration` and `@Bean` create `OrderListeners` under Spring management. Spring discovers the three `@EventListener` methods and registers appropriate adapters.
2. `OrderPlaced` is a Java record **not extending `ApplicationEvent`**. Spring supports publishing POJO events by wrapping the payload when needed; the adapter passes the properly typed payload into the method.
3. `onEveryOrder` receives every published `OrderPlaced`.
4. `onHighValueOrder` runs only when `totalCents() >= 100000`: ORD-2 and ORD-3. ORD-1 does not meet the threshold.
5. `onWebOrder` runs only when `channel() == 'WEB'`: ORD-1 and ORD-3. ORD-2 has `POS`, so it does not run.
6. The default `SimpleApplicationEventMulticaster` dispatches synchronously when no executor or `@Async` is configured. Therefore, after the three `publishEvent(...)` calls return, the lists already contain all values.
7. Each handler's list preserves the order of **event publications**; the order **between different handlers** does not need to be fixed for the output to be correct, because the program only prints the report at the end.
8. `ArrayList` is suitable in a synchronous, single-main-thread demo; if switched to async/multi-threaded execution, collections must be replaced with thread-safe types and tests must wait for handlers to finish.

**Scope of the example:** the program does not demonstrate transaction commit, security, retries, cross-thread ordering, or durable delivery. It only proves the correctness of SpEL `condition` in Spring Application Events. The transaction, async, and security snippets below are **illustrative integrations**, not required parts to run the demo.

### 5.4. Why Not Print Inside Each Listener?

If each listener printed a line inside its method, multiple listeners receiving the same event could make output depend on invocation order. In this demo, each handler only records into its own list; `main` prints the report once all synchronous callbacks have finished. This keeps **stdout deterministic without relying on `@Order`** or a scheduler.

To control order for synchronous handlers, Spring provides ordering mechanisms such as `@Order`. However, registration/call order does not guarantee **completion order** once switched to an asynchronous executor. Do not use listener ordering to model a workflow with mandatory dependencies; use orchestration/services or queues with explicit contracts.

## 6. Multiple Conditions with `and`/`or` and Null Handling

### 6.1. Combining Small Business Criteria

Example of sending an alert for large WEB orders:

```java
@EventListener(
    condition = "#a0.totalCents() >= 100000 and #a0.channel() == 'WEB'"
)
public void onLargeWebOrder(OrderPlaced event) {
    // ...
}
```

The condition is true only for ORD-3 in the demo dataset.

A condition for WEB or APP:

```java
@EventListener(
    condition = "#a0.channel() == 'WEB' or #a0.channel() == 'APP'"
)
public void onDigitalOrder(OrderPlaced event) {
    // ...
}
```

The snippets above are **integration templates**, not part of the runnable file.

### 6.2. Nulls in Optional Data

If `customerTier` or `channel` can be null, a method invocation like `#a0.customerTier().equals('GOLD')` can throw an exception. Reverse the comparison or use null-safe navigation:

```java
@EventListener(
    condition = "#a0.customerTier() == 'GOLD'"
)
public void onGoldCustomer(OrderPlacedWithTier event) {
    // ...
}
```

This example assumes an `OrderPlacedWithTier` event type with a `customerTier()` accessor. SpEL equality compares nulls more safely than calling `equals` on null. Even so, a condition is not a validator: if the channel, currency code, or total amount is invalid, the application must validate inputs and domain invariants at an authoritative boundary.

In particular, do not use `condition` to **silently skip an event that violates an important invariant** and treat the workflow as complete. When invalid data affects consistency or reliability, raise an error/alert or take an explicit handling path rather than just returning false and ignoring it.

## 7. Filtering with `condition` or `if` Inside the Method?

Both have their place.

### 7.1. Short, Pure, Side-Effect-Free `condition`

Suitable when the condition is just a lightweight rule:

```java
@EventListener(condition = "#a0.channel() == 'WEB'")
public void onWeb(OrderPlaced event) {
    // Logic solely for the WEB channel.
}
```

Pros:
- Reading the annotation immediately tells you whether the listener handles every `OrderPlaced`.
- The handler body focuses on what to do when the condition is true.
- Can improve clarity for simple callbacks without creating event subclasses.

Cons:
- The expression is a **string**, so refactoring accessor names may not be caught by the compiler.
- Runtime SpEL evaluation has overhead.
- Long rules are harder to test and debug than ordinary Java code.
- Conditions may depend on external state, breaking determinism.

### 7.2. Java Guard

A handler with a guard:

```java
@EventListener
public void on(OrderPlaced event) {
    if (event.totalCents() < 100000) {
        return;
    }
    // Logic for large orders.
}
```

Pros:
- The Java compiler checks types and method names.
- Easy to set breakpoints, write unit tests, and call domain services.
- Fits multi-step rules that need to explain why an event was skipped or emit metrics per decision.

Cons:
- The method is still invoked for every event of that type.
- Duplicating guard logic across multiple handlers can clutter code unless extracted into a proper policy in the right layer.

### 7.3. Creating a Dedicated Event Type

If the domain actually produces the fact **OrderFlaggedForManualReview** after a policy service has analyzed an order, consider publishing a dedicated event:

```java
public record OrderFlaggedForManualReview(
    String eventId, String orderId, String reasonCode
) {}
```

This is a different fact from `OrderPlaced`. Consumers simply listen by type instead of re-evaluating the same business policy inside multiple callbacks. When an event carries a distinct domain meaning, a dedicated type makes authorization, auditing, versioning, and testing clearer.

**Do not create dozens of event classes just to replace every small field comparison** if they do not represent distinct business events.

### Decision Table

| Scenario | Approach to consider |
| --- | --- |
| Very simple field/enum/threshold check | `@EventListener(condition=...)` |
| Complex rule needing unit tests and rejection reasons | Java guard / domain policy service |
| Event represents a new business fact | Dedicated event type |
| Filtering a very broad event category | Type-specific listener first, condition only as a secondary layer |
| Condition requires database/network or external API | Do not put in SpEL condition; move into handler/service with transaction/error handling |
| Checking user permissions, tenant, sensitive data | Authorization at service/consumer boundary; condition is insufficient |
| Filtering in broker/SQL to reduce traffic | Broker subscription/filter or query at that layer, not Spring condition |

## 8. `@TransactionalEventListener` with `condition`: Understanding Timing

Spring supports `condition` on transaction-bound listeners:

```java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    condition = "#a0.totalCents() >= 100000"
)
public void onCommittedHighValueOrder(OrderPlaced event) {
    // Perform side effect after the transaction commits.
}
```

This is an **integration snippet** requiring a transaction manager, a service that actually publishes the event within a transaction, and imports for `@TransactionalEventListener` and `TransactionPhase`.

Two independent aspects:
- **Condition** determines whether the callback applies to a specific event.
- **Transaction phase** determines when the callback becomes eligible to run based on the transaction outcome.

If the transaction rolls back, an `AFTER_COMMIT` listener does not run even if the payload condition is true. If published outside a transaction with the default `fallbackExecution=false`, a transaction-bound listener normally does not run.

**Do not equate `condition == true` with "committed".** The expression inspects the event snapshot and does not replace the transaction lifecycle. And `AFTER_COMMIT` does not turn an in-memory event into a durable queue: if the process crashes after DB commit and before the callback runs, the side effect can still be lost.

### Condition Does Not Guarantee Data After Commit Matches Publish Time

A mutable event or a reference to a managed JPA entity can change before the callback executes. A condition reading mutable state at evaluation time while the body reads state at another time creates a **TOCTOU** issue. Use an immutable snapshot in the event or query authoritative state inside the handler per contract, especially when listeners run after commit or asynchronously.

When critical work must be retried after a crash, store a durable outbox/job in the same DB transaction instead of relying solely on `@TransactionalEventListener(AFTER_COMMIT)`.

## 9. `@Async` and Conditions: Execution Boundaries

A method can combine both:

```java
@Async("eventExecutor")
@EventListener(condition = "#a0.channel() == 'WEB'")
public void onWebOrderAsync(OrderPlaced event) {
    // ...
}
```

This is an **integration pattern** requiring `@EnableAsync`, an executor named `eventExecutor`, a Spring-managed listener bean, and invocation through an async proxy. When Spring applies an async proxy to a method, the body executes on the thread pool while the multicaster dispatches according to its own mechanism. Do not assume every SpEL expression and every body runs on the same thread if configuration changes; dispatch/condition cost should be measured on **the actual execution path**.

Key points to remember:
- `publishEvent()` can return before the async handler finishes.
- `condition=false` means the callback body does not run, but it does not automatically emit a "filtered out" monitoring notification.
- If a listener uses a dedicated executor, configure a `TaskDecorator`/context propagation on that exact executor.
- `SecurityContextHolder` and MDC are thread-bound by default in the servlet stack and do not automatically follow tasks.
- Exceptions from `@Async void` do not propagate back to the publisher; use an `AsyncUncaughtExceptionHandler`, logging/metrics, or test signals.
- Do not use `Thread.sleep(...)` and assert results; use `CountDownLatch`, `CompletableFuture`, or Awaitility with a timeout.

**Specifically:** if a condition truly depends on runtime transaction/session/security context, design and test the execution boundary instead of letting a SpEL expression read `ThreadLocal` state that may no longer exist.

## 10. `@Order`, Multiple Listeners, and Independence

Two listeners whose conditions are true for the same event **can both run**:

```java
@EventListener(condition = "#a0.totalCents() >= 100000")
public void sendHighValueAlert(OrderPlaced event) {
    // ...
}

@EventListener(condition = "#a0.channel() == 'WEB'")
public void updateWebDashboard(OrderPlaced event) {
    // ...
}
```

For ORD-3 in the demo, both methods are selected—this is not `else if`. Spring multicasting is fan-out: `condition` has no "first matching listener wins" mechanism.

If you genuinely need mutually exclusive branches, model the policy/dispatch in a single layer or distinguish event types; **do not rely on listener order** and expect later listeners not to run.

`@Order` can help Spring determine invocation order for synchronous listeners, but it does not guarantee **completion order** when listeners run asynchronously. Do not use `@Order` as a substitute for a saga/workflow with dependencies or transactional atomicity.

### When Listeners Return Another Event

Spring `@EventListener` can use a method's return value to publish a follow-up event (per Spring's supported contract). When `condition` is false, the method does not run and produces no return event; when `condition` is true, fan-out can include the returned event. With `@Async`, automatically publishing an event from a return value is not supported the same way as with sync listeners; use `ApplicationEventPublisher` explicitly if needed.

Watch out for event loops: a listener receiving event A and continuously publishing a new event A can cause recursion or a queue storm. Conditions help select callbacks, **they do not protect against loops**, duplicates, or infinite retries.

## 11. Performance: Conditions Are Not Free

Distinguish `N` registered listeners, `K` listeners **matching by type**, and `M` listeners **passing the condition**:

```text
N total listener beans/adapters
    |
    +-- Select by event type/source --> K candidates
                                         |
                                         +-- SpEL condition true --> M handlers
                                         +-- SpEL condition false -> skipped methods
```

When an application publishes a high volume of events, costs can include:
- Spring looking up listeners matching the event type/source.
- The adapter evaluating the SpEL expression for matching events.
- Reflection/proxy/argument resolution.
- Executor submission (if async).
- Business handler execution, logging/tracing/metrics.
- I/O to databases, APIs, caches, and brokers.

In Spring, type-based listener lookup results are cached inside `AbstractApplicationEventMulticaster` in eligible cases. **Caching type selection does not mean condition results are cached per event instance.** Values like `totalCents()` and `channel()` can differ on every event, so the condition must be evaluated per event.

Example of a **condition you should avoid**:

```java
@EventListener(
    condition = "@orderRepository.isEligible(#a0.orderId())"
)
public void notifyEligibleOrder(OrderPlaced event) {
    // ...
}
```

This is an **illustrative anti-pattern**, assuming a repository bean exists. SpEL allows bean references and method calls depending on evaluation context configuration, but calling the DB inside an expression will:
- Obscure I/O, timeouts, retries, and transaction scope;
- Potentially run for huge numbers of events even when the handler body never runs;
- Block dispatch in a synchronous multicaster when failures occur;
- Make the condition hard to test and dependent on external state;
- Hide business authorization inside an annotation string that is difficult to audit.

Instead, have the handler invoke a domain service/policy with explicit error handling and transactions; or publish a dedicated fact event after the service has already checked the required conditions.

### Measuring Performance at the Right Layer

You can measure:
- `publishEvent` duration for the sync/handoff path.
- `listener.execution.duration` for the method body.
- `event.condition.rejected.count` if you genuinely need to know how many events were filtered—this must be instrumented intentionally, as Spring does not emit this metric automatically for every condition.
- Queue wait / executor rejections when async is used.

Do not use `eventId`, `orderId`, or `correlationId` as metric tags because of high cardinality. Use bounded tags such as `eventType`, `listener`, and `outcome`. If you want to benchmark SpEL overhead, use JMH or profiling with warmup and a no-op listener; do not measure once with `System.nanoTime()` and declare the framework "slow".

## 12. Security and Data: Conditions Are Not Authorization

An expression like:

```java
@EventListener(condition = "#a0.tenantId() == 'tenant-A'")
public void exportCustomerData(CustomerExportRequested event) {
    // This is NOT an authorization check.
}
```

does not verify:
- Whether the event came from an application service that authenticated the principal;
- Whether `tenantId` came from a trusted record or was supplied by a client;
- Whether the user has permission to export **the exact data** being requested;
- Whether permissions are still valid when the listener executes later;
- Whether the data is being sent to a verified recipient.

Any bean in the same context can construct an event object and publish it directly; `@EventListener` is a routing mechanism, **not a security boundary**. For sensitive operations, enforce authentication and object-level authorization at the service boundary, and have the listener/worker verify intent, aggregate, and tenant against an authoritative source.

`eventId`, `actorId`, `correlationId`, and `tenantId` are metadata, not credentials. Do not put access tokens or a full Spring Security `Authentication` inside an event for use after the request ends. Pass only minimal data, protect PII in events/outboxes/logs/traces, and define retention policies.

A safe way to view `condition`: it is a **small callback-selection optimization**, while trust logic and security remain at the responsible service/consumer.

## 13. Error Handling When an Expression or Handler Fails

A condition can fail because of:
- A misspelled accessor name: `#a0.totalCent()` instead of `totalCents()`.
- Invalid expression syntax or mismatched string quotes.
- A null value when invoking a method on null.
- Wrong event type or expecting `#root.event` to be the payload.
- A method/bean called from the expression throwing an exception.
- A condition relying on context that does not exist on the current thread.

When SpEL evaluation fails, it is a **runtime error** in the event pipeline, not a safe `"condition=false"` skip in all situations. With a synchronous multicaster and no suppressing error handler, the exception can propagate back to the publisher. With async, errors can go to an `ErrorHandler`, executor, or async uncaught exception handler. Always test actual behavior under your chosen configuration.

If another listener already processed the event before a later listener fails, retrying the entire `publishEvent(event)` call can cause the earlier handler to run again. For critical side effects, use stable event IDs, idempotency, and durable work as required. Never treat a condition false/error as a successful workflow acknowledgment.

### A Wrong Condition Can Silently Drop Important Data

If `condition` is written as `> 100000` instead of `>= 100000`, orders right at the threshold will never be processed by the handler. This is a business bug that can **go silently unnoticed**. Therefore, test boundaries, nulls, enums/strings, and invalid data rather than testing only one obvious value.

For handlers performing mandatory business work, use durable controls and reconciliation rather than relying solely on an unobservable annotation expression.

## 14. Testing Conditional Listeners

### 14.1. Testing the Happy Path Against the Truth Table

For the Section 5 demo:
1. Publish `ORD-1(50000, WEB)` -> all + web; not high.
2. Publish `ORD-2(150000, POS)` -> all + high; not web.
3. Publish `ORD-3(200000, WEB)` -> all + high + web.
4. Assert `ALL=[ORD-1, ORD-2, ORD-3]`, `HIGH=[ORD-2, ORD-3]`, `WEB=[ORD-1, ORD-3]`.

If a test calls `listeners.onHighValueOrder(event)` directly in Java, you are **bypassing the Spring event adapter**: the method body will run regardless of `condition`! To test the annotation condition, publish the event via `ApplicationEventPublisher` inside a Spring context where the listener is registered.

### 14.2. Testing Boundary Values

Add cases for:
- Total `99999`: high-value condition false.
- Total `100000`: high-value condition true.
- Total `100001`: true.
- Channel `WEB` uppercase: true.
- Channel `web` lowercase: false under the current equality expression.
- Channel `null`: equality against `'WEB'` is false, though a validation policy is needed if channel is required.

Avoid testing only `200000` and forgetting the exact `100000` threshold.

### 14.3. Testing Expression Failures

Create an isolated test listener whose condition intentionally accesses a non-existent accessor, publish an event through the Spring context, and verify the error behavior under **the chosen configuration**. Do not register that broken listener in the same context as normal tests and cause unrelated suites to fail mysteriously.

If the handler is moved to async, do not wrap the publisher in `assertThrows` and conclude there is no error. Wait on the `ErrorHandler`/`AsyncUncaughtExceptionHandler` or an appropriate test signal.

### 14.4. Testing Conditions and Transactions

With `@TransactionalEventListener(AFTER_COMMIT, condition=...)`:
- Publish an event matching the condition **inside a real transaction**, commit, and assert the handler ran.
- Publish an event matching the condition but roll back, and assert the `AFTER_COMMIT` handler did not run.
- Publish an event with a false condition and commit, and assert the handler did not run.
- Publish an event outside a transaction with the default fallback, and assert it did not run.

Do not simply put `@Transactional` on a Spring Test and expect `AFTER_COMMIT` to fire, since many integration tests automatically roll back at the end of the test method. Use `TransactionTemplate`/`TestTransaction` to explicitly commit according to the contract.

### 14.5. Non-Flaky Async Testing

When the multicaster/`@Async` uses an executor:
- Publish events with distinct IDs.
- Use `CountDownLatch` or `CompletableFuture` keyed by `eventId` to wait for the right handler.
- When `condition` is true, wait for the completion signal and assert the result.
- When `condition` is false, to verify "not invoked", establish a barrier ensuring all related work has passed the dispatcher/queue or design a harness with a sentinel; do not claim it was never called merely by waiting 100 ms.
- Clean up executors and contexts after tests; do not let workers from an earlier test leak into the next test.

## 15. Practice Checklist

- [ ] Clearly distinguish type selection, SpEL `condition`, and business guards inside methods.
- [ ] Listener method parameter type matches the expected event.
- [ ] Use `#a0`/`#p0`/`#root.args[0]` when parameter-name independence is desired.
- [ ] Expression returns boolean with proper SpEL string quotes and operators.
- [ ] Test `>=` / `>` boundaries and case-sensitive channel matching.
- [ ] Condition is short, pure, and neither calls DB/network nor mutates state.
- [ ] Do not use SpEL conditions to hold authorization or complex domain invariants.
- [ ] Do not assume `#root.event` is always the POJO payload for every event type.
- [ ] Do not use `condition` to silently drop severely invalid events.
- [ ] With multiple listeners, understand conditions are independent and can be true simultaneously.
- [ ] When using async, know the executor, error handler, and completion signal.
- [ ] When using transactional listeners, test real commits and rollbacks.
- [ ] Event payloads are immutable, without managed entities or mutable `ThreadLocal` state.
- [ ] Important handler outcomes have metrics/logging without high-cardinality tags.
- [ ] Test conditions via `publishEvent` inside a Spring context, not just direct method calls.
- [ ] If side effects must never be lost, design outbox/jobs/retries/idempotency instead of relying only on `condition`.

## 16. Summary Exercises

**Exercise 1 — Compound condition.** From the demo, add an `onHighValueWebOrder` method with the condition:

```java
@EventListener(
    condition = "#a0.totalCents() >= 100000 and #a0.channel() == 'WEB'"
)
```

Expect only ORD-3 to be added to the new listener's list. Also test ORD-5 right at the threshold on channel APP to prove the condition must satisfy **both branches**.

**Exercise 2 — Boundaries.** Using the same high-value listener, publish `99999`, `100000`, and `100001`, asserting that only the last two values are processed.

**Exercise 3 — Refactor.** Suppose a SpEL condition had to call the DB to check whether a customer is VIP. Move the rule into a policy service inside the handler or have the application publish a dedicated fact event after computing eligibility. Write unit tests for the policy and integration tests for listener registration.

**Exercise 4 — Transactions.** Add `@TransactionalEventListener(AFTER_COMMIT)` with a high-value order condition. Test all four branches: commit-true, commit-false, rollback-true, and no-transaction. Make sure not to confuse the condition with the phase.

**Exercise 5 — Async.** Switch the demo to a `ThreadPoolTaskExecutor` with a bounded queue. Replace `ArrayList` with concurrent structures, wait using `CountDownLatch`, verify final stdout is timing-independent, and test the error handler and shutdown.

**Exercise 6 — Security.** A user submits payload `tenantId=tenant-B` from `tenant-A`. Explain why `condition="#a0.tenantId() == 'tenant-B'"` is not a permission check; instead, add authorization at the application service and tenant-scoped queries.

### Self-Check Questions

1. Does `condition=false` stop `publishEvent` from delivering the event to **all** listeners? **No.** It only prevents the corresponding callback.
2. What does `#a0` point to? **The first parameter** of the listener method.
3. Does `@EventListener(condition=...)` replace type matching? **No.** It is a filtering layer after the listener already matched by type.
4. With an async multicaster, does `publishEvent` returning mean the listener has finished? **Not necessarily.**
5. Does `@TransactionalEventListener(AFTER_COMMIT, condition=true)` run when the transaction rolls back? **No.**
6. Can a SpEL condition be treated as an authorization boundary? **No.**
7. How do you prove an annotation condition works? **Publish through a Spring `ApplicationContext`** and assert the listener is or is not invoked for the right data.
8. Does listener type-selection caching also cache condition results for all events? **You must not assume so; conditions depend on each event's data.**

**Conclusion:** `@EventListener(condition = "...")` is a concise tool for **filtering callbacks by event data** when rules are small, clear, pure, and easy to test. It pairs with Spring's type selection, yet does not replace authorization, transactions, reliability, or business policies. For critical systems, use semantically accurate domain events, immutable payloads, proper error handling, idempotency, and integration tests covering condition, transaction, and async branches.

## References

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.1.21 — EventListener annotation API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework — SpEL Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
- [Spring Framework 6.1.21 — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.1.21 — AbstractApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/AbstractApplicationEventMulticaster.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework 6.1.21 — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
