# Creating Observations for Critical Listeners in Spring Framework Application Events

## 1. Why create Observations manually for listeners?

A Spring application can use `ApplicationEventPublisher.publishEvent(...)` to emit business events and use `@EventListener`, `ApplicationListener`, or `@TransactionalEventListener` to process them. A critical listener might request invoice generation, update a search index, synchronize orders, or call a downstream system. If you only know that an event was published, you cannot answer key operational questions:

- Which listener is slow, and by how much?
- What is the error rate for each event type?
- Is an HTTP request slow because of the main flow or because of a synchronous listener?
- Which event corresponds to which trace or originating request?
- After switching to async, can we still correlate the event with the originating request?
- A post-commit listener failed: the database already committed, so where did the post-commit task fail?

**Spring Framework does not automatically generate an Observation for each `@EventListener` invocation.** The Spring documentation states that application events are published and handled synchronously on the same thread by default, so there are no clear enough semantics for the framework to auto-instrument every listener. When specific observability is required, the application should **create a Micrometer `Observation` around the critical processing**.

Basic example:

~~~java
@EventListener
public void on(OrderPlaced event) {
    Observation.createNotStarted("app.event.listener", observationRegistry)
        .contextualName("handle OrderPlaced")
        .lowCardinalityKeyValue("event.type", "OrderPlaced")
        .lowCardinalityKeyValue("listener", "order-notification")
        .highCardinalityKeyValue("order.id", event.orderId())
        .observe(() -> notificationService.notifyOrder(event.orderId()));
}
~~~

This is an **integration snippet**, requiring `ObservationRegistry`, `OrderPlaced`, `notificationService`, imports, and matching Spring beans. `observe(...)` manages start, scope, timing, recording escaping exceptions, and stop; on its own, it does not guarantee metrics or traces if the registry is not configured with corresponding handlers.

### Lesson objectives

1. Distinguish `Observation`, `ObservationRegistry`, `ObservationHandler`, and `MeterRegistry`.
2. Record timing, errors, and metadata for **critical listeners** without creating endless duplicate metrics.
3. Use low/high cardinality tags properly, avoiding turning `orderId` into an unbounded metric tag.
4. Build a runnable Java 17 + Spring Framework + Micrometer example testing two executions (success/failure).
5. Understand scope, trace context, async context propagation, and transaction/event lifecycle boundaries.
6. Define actionable tests, dashboards, alerts, and error policies.

## 2. The Micrometer Observation model

Micrometer provides an abstraction to **instrument an action once** and connect multiple observability capabilities depending on configuration.

| Component | Role | Things to remember |
|---|---|---|
| `Observation` | One tracked operation: start, stop, error, event, metadata | Has its own lifecycle; must stop properly |
| `ObservationRegistry` | Manages configuration, handlers, filters, predicates, current observation | Should inject the application-configured registry |
| `ObservationHandler` | Receives lifecycle callbacks to produce metrics, spans, or other actions | Without useful handlers, observations may emit no telemetry |
| `MeterRegistry` | Creates/stores/exports meters such as `Timer` and `Counter` | Not synonymous with `ObservationRegistry` |
| `DefaultMeterObservationHandler` | Converts observations into metrics in `MeterRegistry` | Creates timers and tags from appropriate key values |
| Tracing observation handler | Connects observations to tracing/spans per backend | Requires configured bridge/tracer/exporter |
| `Observation.Context` | Metadata and state of an observation | Does not replace event payloads or repositories |

Conceptual flow:

~~~text
OrderPlaced event
    |
    v
@EventListener(OrderPlaced)
    |
    +-- Observation.createNotStarted("app.event.listener", registry)
    |       +-- low cardinality: event.type, listener
    |       +-- high cardinality: order.id (when appropriate)
    |
    +-- observation.start()
    |       +-- Handler.onStart(...)
    |
    +-- observation.openScope()
    |       +-- business processing
    |       +-- optional child observations
    |       +-- on error: observation.error(exception)
    |
    +-- close scope
    |
    +-- observation.stop()
            +-- Meter handler -> Timer, error tag
            +-- Tracing handler (if configured) -> span
~~~

**An Observation is not a business event.** A Spring event is an internal message carrying domain meaning such as `OrderPlaced`. An Observation describes **one execution** of a listener for monitoring purposes. One event can trigger three listeners and three distinct observations; one listener can also receive the same event multiple times when the application retries.

## 3. Where should you instrument?

There are three different measurement boundaries:

| Measurement boundary | Start / end | Meaning |
|---|---|---|
| Publisher's `publishEvent(...)` | Before and after the publication call | Measures total dispatch time in the synchronous model; may include multiple listeners |
| Body of an `@EventListener` | Start and end of a specific handler | Measures **listener duration**; matches this lesson's goal |
| Async work / job / message consumer | When the worker actually picks up and processes the task | Measures worker execution time, not queue wait time |

If there are three listeners and you instrument only the publisher, an `event.publish` timer cannot tell which listener is slow. If a critical listener executes multiple stages such as validate → call API → write DB, you can add child observations for expensive steps, but avoid creating spans for every trivial method.

**Principle:** choose the boundary operators want dashboards/SLOs for, such as `app.event.listener` for "processing event notifications", rather than blindly measuring every annotated method.

### Naming observations stably

~~~java
Observation.createNotStarted("app.event.listener", registry)
    .contextualName("handle OrderPlaced")
    .lowCardinalityKeyValue("event.type", "OrderPlaced")
    .lowCardinalityKeyValue("listener", "notification");
~~~

- The name `app.event.listener` is a stable **operation type** that changes rarely across invocations.
- `contextualName` describes the operation in a trace/span-friendly way; do not embed dynamic IDs into the name.
- `event.type` and `listener` have bounded value sets when the application manages the list of event/handler types.
- Use a shared observation name for a group of operations with the same semantics, or split names if contracts and dashboards differ substantially.

Do not create dynamic names:

~~~java
// Avoid: one Observation/meter name per order.
Observation.createNotStarted("handle.order." + event.orderId(), registry);
~~~

This fragments metric data, inflates series counts, and makes aggregation difficult.

## 4. Low cardinality and high cardinality: boundaries to enforce strictly

**Cardinality** is the number of distinct values a key can take.

- **Low-cardinality key values:** bounded groups, such as `event.type=OrderPlaced`, `listener=notification`, `result=success|error`, `phase=after_commit`. Metric handlers use these as tags to slice series.
- **High-cardinality key values:** nearly unique per execution, such as `order.id`, `event.id`, `request.id`, `user.id`. Do not place these in metric tags; if genuinely needed, consider high-cardinality metadata for tracing under strict access and security policies.

Micrometer `DefaultMeterObservationHandler` uses **low-cardinality values** for meter tags; high-cardinality values are **not** used as meter tags by this handler. This protects the metric registry from unbounded series counts.

| Example key | Suggested classification | Reason |
|---|---|---|
| `event.type=OrderPlaced` | Low | Bounded number of event types |
| `listener=order-notification` | Low | Bounded number of critical listeners |
| `phase=after_commit` | Low | Few transaction phases |
| `outcome=success|failure` | Low | Small value set |
| `tenant.tier=free|pro|enterprise` | Low (if catalog-controlled) | Few values, operationally meaningful |
| `order.id=ORD-244` | High | Unique value per object |
| `event.id=UUID` | High | Unique value per event |
| `email.address` | Usually **do not collect** | PII, sensitive, and unnecessary for timers |
| `exception.message` | **Do not use as metric tag** | May contain IDs, URLs, sensitive data; unbounded values |

API example:

~~~java
Observation observation =
    Observation.createNotStarted("app.event.listener", registry)
        .lowCardinalityKeyValue("listener", "payment-confirmation")
        .lowCardinalityKeyValue("event.type", "PaymentSucceeded")
        .highCardinalityKeyValue("payment.id", paymentId);
~~~

This illustrative snippet only **creates the observation** without starting it; `observation.observe(...)` or `start()/stop()` is needed to complete it.

**Do not assume high-cardinality metadata is always safe:** traces may be exported to external vendors or retained long-term; apply masking, sampling, and retention policies. For user-identifying IDs, sometimes store only a suitably processed correlation ID or omit the ID altogether.

## 5. Using observe(...) to record timing and errors cleanly

Micrometer provides the API:

~~~java
Observation.createNotStarted("app.event.listener", registry)
    .lowCardinalityKeyValue("event.type", "OrderPlaced")
    .observe(() -> importantWork());
~~~

For a `Runnable` lambda, `observe(...)` performs:

1. Calls `start()`, triggering handlers.
2. Opens a scope so the observation becomes the current observation during execution.
3. Executes the lambda.
4. If the lambda throws, records `observation.error(thrown)` and **rethrows the error**.
5. Closes the scope and calls `stop()` in all cases.

This keeps errors visible: the publisher still receives exceptions under the default listener dispatch path, while metric handlers can record error tags.

For a function returning a result, you can use the `Supplier<T>` overload:

~~~java
Receipt result = Observation
    .createNotStarted("app.event.listener", registry)
    .observe(() -> receiptService.buildReceipt(event.orderId()));
~~~

This is **integration code** with an assumed `Receipt` type and service. Micrometer provides matching overloads to return values from lambdas.

### What if errors are handled inside the lambda?

~~~java
Observation observation =
    Observation.createNotStarted("app.event.listener", registry)
        .lowCardinalityKeyValue("listener", "notification");

observation.observe(() -> {
    try {
        externalClient.send();
    } catch (IllegalStateException ex) {
        log.warn("External service failed", ex);
        // Do not rethrow -> observe(...) sees the lambda complete normally.
    }
});
~~~

This snippet is **illustrative code**. If an exception is caught and ignored, `observe(...)` does not know an error occurred. If business logic intentionally recovers yet still wants to record the error on the observation:

~~~java
observation.observe(() -> {
    try {
        externalClient.send();
    } catch (RuntimeException ex) {
        observation.error(ex);
        fallback.sendLater();
    }
});
~~~

Here, the collaborators must be defined in the application. Choose this pattern when you want metrics to report downstream errors even though business logic falls back and the listener returns normally. You can add a bounded `outcome` tag if you need to distinguish `recovered` from `failed`; avoid recording the error manually twice if the exception is rethrown for `observe(...)` to handle automatically.

## 6. Runnable example: Java 17 + Spring Framework 6.2 + Micrometer

This example uses:

- **Java 17+** and Maven.
- Spring Framework **6.2.8** (`spring-context`).
- Micrometer **1.16.7** (`micrometer-core` and `micrometer-observation`).
- `SimpleMeterRegistry` holding metrics in memory for immediate inspection after publishing events.
- `DefaultMeterObservationHandler` turning observations into `Timer`s and `error` tags.

The program creates a critical `@EventListener` bean, publishes one successful `OrderPlaced` and one `OrderPlaced` that intentionally fails, and then inspects the timers. This is an **in-process illustration**, requiring no Spring Boot, database, broker, tracing exporter, or web server.

### Structure

~~~text
important-listener-observation/
├── pom.xml
└── src/main/java/demo/ImportantListenerObservationDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>important-listener-observation</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.16.7</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-observation</artifactId>
            <version>1.16.7</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/ImportantListenerObservationDemo.java

~~~java
package demo;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class ImportantListenerObservationDemo {

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            SimpleMeterRegistry meters = ctx.getBean(SimpleMeterRegistry.class);

            // Success: handler runs inside a complete observation.
            ctx.publishEvent(new OrderPlaced("ORD-OK", false));

            // Error: handler records error and rethrows to the publisher.
            try {
                ctx.publishEvent(new OrderPlaced("ORD-FAIL", true));
            } catch (IllegalStateException expected) {
                System.out.println("caught=" + expected.getMessage());
            }

            long successCount = meters.find("app.event.listener")
                .timers().stream()
                .filter(t -> "none".equals(t.getId().getTag("error")))
                .mapToLong(Timer::count).sum();

            long failureCount = meters.find("app.event.listener")
                .timers().stream()
                .filter(t -> !"none".equals(t.getId().getTag("error")))
                .mapToLong(Timer::count).sum();

            System.out.println("success observations=" + successCount);
            System.out.println("failed observations=" + failureCount);
            System.out.println("total observations=" +
                    (successCount + failureCount));
        }
    }

    public record OrderPlaced(String orderId, boolean fail) {}

    public static final class ImportantOrderListener {
        private final ObservationRegistry registry;

        public ImportantOrderListener(ObservationRegistry registry) {
            this.registry = registry;
        }

        @EventListener
        public void on(OrderPlaced event) {
            Observation.createNotStarted("app.event.listener", registry)
                .contextualName("handle OrderPlaced")
                .lowCardinalityKeyValue("event.type", "OrderPlaced")
                .lowCardinalityKeyValue("listener", "important-order-listener")
                .highCardinalityKeyValue("order.id", event.orderId())
                .observe(() -> {
                    System.out.println("handling=" + event.orderId());
                    if (event.fail()) {
                        throw new IllegalStateException(
                            "simulated downstream failure");
                    }
                });
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public SimpleMeterRegistry meterRegistry() {
            return new SimpleMeterRegistry();
        }

        @Bean
        public ObservationRegistry observationRegistry(
                SimpleMeterRegistry meters) {
            ObservationRegistry registry = ObservationRegistry.create();
            registry.observationConfig()
                .observationHandler(
                    new DefaultMeterObservationHandler(meters));
            return registry;
        }

        @Bean
        public ImportantOrderListener importantOrderListener(
                ObservationRegistry registry) {
            return new ImportantOrderListener(registry);
        }
    }
}
~~~

### Running the program

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ImportantListenerObservationDemo
~~~

Lines printed by **application code** in the default synchronous model:

~~~text
handling=ORD-OK
handling=ORD-FAIL
caught=simulated downstream failure
success observations=1
failed observations=1
total observations=2
~~~

Maven/Spring logs may appear depending on the environment; the lines above are the program's output.

### Execution analysis

1. `AnnotationConfigApplicationContext` registers the listener bean, `SimpleMeterRegistry`, and `ObservationRegistry`.
2. `observationConfig().observationHandler(...)` registers `DefaultMeterObservationHandler` on the registry, so observations produce metrics.
3. Spring publishes `OrderPlaced("ORD-OK", false)`; the `@EventListener` method calls `observe(...)` and completes normally. The timer records duration with tag `error=none`.
4. The second event reaches the same listener, prints `handling=ORD-FAIL`, and throws `IllegalStateException`.
5. `observe(...)` records the error and stops the observation in `finally`, and the exception propagates back to the `publishEvent` caller. `main` catches the error to continue reading metrics.
6. `meters.find("app.event.listener").timers()` returns the `Timer` instances created for the observation name. `getTag("error")` distinguishes non-error timers from error timers.
7. `successCount=1` and `failureCount=1` confirm that **two executions** were measured. `Timer.count()` is the number of recorded timings, not execution duration; duration can be read via `Timer.mean(TimeUnit.MILLISECONDS)` or `Timer.max(...)`.

**Demo limitations:** `SimpleMeterRegistry` stores data in memory only and does not automatically export metrics to Prometheus/Grafana. The code also does not produce distributed traces because **no tracing handler is registered**. Do not assume having Micrometer dependencies means spans or exporters are active by default.

## 7. Managing Observations manually with start/openScope/error/stop

`observe(...)` is concise and safe when processing fits a synchronous lambda. When you need to extend the processing context or work with APIs requiring manual lifecycle control:

~~~java
Observation observation =
    Observation.createNotStarted("app.event.listener", registry)
        .lowCardinalityKeyValue("listener", "inventory-reservation")
        .lowCardinalityKeyValue("event.type", "OrderPlaced");

observation.start();
try (Observation.Scope scope = observation.openScope()) {
    reserveInventory(orderId);
} catch (RuntimeException ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

This is **integration code**; `reserveInventory` and `orderId` are defined by the application. Rules:

- Call `start()` before the work whose timing needs to be measured.
- Use `try-with-resources` to close the scope even when logic fails.
- Call `error(ex)` when exceptions are handled outside `observe(...)`, so handlers recognize the failure.
- **Always call `stop()` in `finally`**. Forgetting it leaves timers incomplete and makes scopes/metrics hard to analyze.
- Never call `stop()` twice or arbitrarily open/close scopes across different threads.
- If a callback must not rethrow exceptions due to business policy, record the recovered/dropped state clearly and ensure errors remain observable.

For simple critical listeners, prefer `observe(...)` to reduce lifecycle management mistakes.

## 8. Scope, parent observations, and trace linkage

When an `Observation` has an open scope, observations created within the same context can attach to the current observation to reflect parent–child relationships. In a pre-instrumented HTTP application:

~~~text
http.server.requests
    |
    +-- OrderController -> OrderService
            |
            +-- publishEvent(OrderPlaced)
                    |
                    +-- app.event.listener
                            |
                            +-- http.client.requests (if the listener calls an instrumented HTTP client)
~~~

This is the **intended structure**, not guaranteed output across every configuration. With default synchronous dispatch, the listener runs on the publisher thread, so Micrometer's scope/ThreadLocal can persist along the same call chain. With proper tracing configuration, the listener span can become a child span of the request or enclosing observation.

**Do not confuse:**

- `ObservationRegistry` has the **ability to manage observations**, but may not have a `TracingObservationHandler`.
- `MeterRegistry` + `DefaultMeterObservationHandler` generates metrics, **not distributed traces**.
- Exporters (OTLP/Zipkin/Prometheus) are only effective when properly configured with a receiving backend.
- `contextualName` is a descriptive operation name; do not put per-execution IDs into span names.
- Trace sampling may cause not every event to appear in the trace backend even when metrics still record on the application side if configured.

A single observation can be processed by multiple handlers to emit metrics and traces simultaneously. Having listener code depend only on `ObservationRegistry` decouples business logic from monitoring backends.

## 9. Spring Boot and Actuator: use the existing registry

If an application uses Spring Boot with Micrometer/Actuator, you generally **do not need to call `ObservationRegistry.create()` inside each listener**. Inject the Boot-configured registry:

~~~java
@Component
public class ImportantPaymentListener {

    private final ObservationRegistry observations;

    public ImportantPaymentListener(ObservationRegistry observations) {
        this.observations = observations;
    }

    @EventListener
    public void on(PaymentCaptured event) {
        Observation.createNotStarted("app.event.listener", observations)
            .contextualName("handle PaymentCaptured")
            .lowCardinalityKeyValue("event.type", "PaymentCaptured")
            .lowCardinalityKeyValue("listener", "payment-receipt")
            .observe(() -> sendReceipt(event.paymentId()));
    }
}
~~~

This is an **integration snippet**; it requires `@Component`, `@EventListener`, the `PaymentCaptured` event, and the system's `sendReceipt` function. With Spring Boot, provide `spring-boot-starter-actuator` and configure metric/tracing exporters suitable for your stack. Which exact beans/handlers are auto-configured depends on versions, dependencies, and management properties; do not assume Actuator alone means all tracing is active.

### Observing via Actuator/metric endpoints

When configured and permitted, `/actuator/metrics` can list meters; query `/actuator/metrics/app.event.listener` once the meter has been recorded. With a Prometheus registry and exposed actuator endpoint, time-series names may be normalized per the backend's naming rules. Do not treat dashboard names generated by one registry version as an immutable contract across all monitoring systems.

**Security:** do not expose management endpoints, metric tags, or trace links containing internal information without access restrictions.

### Can @Observed replace manual instrumentation?

Micrometer provides the `@Observed` annotation for certain AOP scenarios; it requires **Aspect/Proxy and corresponding configuration** to work. It is not a rule that "just putting the annotation on every `@EventListener` makes Spring Framework auto-observe it". For listeners needing payload-derived tags, custom error handling, and clear boundaries, writing `Observation.createNotStarted(...).observe(...)` directly in the service/handler remains easier to control.

Avoid enabling AOP observation while also wrapping the same method with a manual observation unless you intentionally want **two layers of observation**; doing so can cause dashboards to double-count.

## 10. Synchronous, asynchronous listeners, and context propagation

Spring Framework dispatches application events synchronously on the publisher's thread by default. However, an application can:

- Put `@Async` on an `@EventListener` method and supply an executor.
- Configure a custom `ApplicationEventMulticaster` with a `TaskExecutor`.
- Spawn another job/thread/callback inside the listener.

When execution switches threads, **ThreadLocal-based context, MDC, security context, or observation scopes do not automatically follow**. Therefore, separate two problems:

1. **Instrument the worker in real time:** create/open the observation when the worker actually runs to measure processing duration.
2. **Link it to the publisher's parent trace:** propagate context via a supported mechanism, or carry a correlation ID in the event payload.

### ContextPropagatingTaskDecorator

Spring Framework provides `ContextPropagatingTaskDecorator`, working with Micrometer Context Propagation, to carry supported context from task submission to executor workers in supported cases. It requires `io.micrometer:context-propagation` on the classpath and proper executor/task decorator configuration.

**Integration configuration** example:

~~~java
@Bean(name = "eventExecutor")
public ThreadPoolTaskExecutor eventExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("event-worker-");
    executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
    executor.initialize();
    return executor;
}
~~~

This snippet requires imports for `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` and `org.springframework.core.task.support.ContextPropagatingTaskDecorator`, along with Spring bean configuration and the propagation dependency. If using `@Async("eventExecutor")`, valid `@EnableAsync`/Spring AOP infrastructure is needed and calls must go through the proxy. It **does not create a new DB transaction** in the worker and does not replace durable delivery.

### Common misconceptions

- "An async listener shares the same ThreadLocal transaction": **false**; JDBC transactions are thread-bound, so another worker does not automatically join T1.
- "Propagating trace context also propagates transaction context": **false**; tracing context propagation is not transaction propagation.
- "Having a `correlationId` means there is already a child span": **false**; a correlation ID helps correlate business logs, but does not automatically create trace/parent-span links.
- "A metric in an HTTP callback that returns immediately also measures async work": **false**; the observation must wrap the worker execution or the target execution stage.

With Reactor/R2DBC, there is also **Reactor Context** rather than ThreadLocal alone. Observations must be placed properly at subscription/execution time rather than creating an observation and stopping it as soon as a method returns a `Mono` before the pipeline runs.

## 11. Reactive listeners: why must you not stop when returning a Mono?

If listener logic returns a publisher, **assembly** time differs from **subscription** time:

~~~java
// Conceptual anti-pattern: measures only Mono assembly, not actual async processing.
Observation.createNotStarted("app.event.listener", registry)
    .observe(() -> service.processAsync(event)); // Returns Mono, not yet subscribed.
~~~

If you only call the method returning `Mono` and exit the lambda, the observation ends **before data is processed**. The snippet above is an anti-pattern and does not imply `@EventListener` automatically subscribes to reactive publishers.

The right design is to **wrap the observation lifecycle around subscription/execution** and ensure stopping on success/error/cancel, typically using supported Reactor instrumentation helpers or tested composition with `Mono.defer(...)`/`doFinally(...)`/context handling. When parent tracing across subscribers is needed, use appropriate Reactor Context propagation instead of relying on a ThreadLocal scope opened at assembly time.

Conceptual structure illustration:

~~~text
Mono.defer(...)
  |
  +-- onSubscribe -> create/start Observation
  +-- onNext / onComplete / onError -> process and record status
  +-- doFinally(...) -> stop Observation with success/error/cancel
~~~

Do not copy the `Observation.openScope()` pattern across thread boundaries without understanding the contract; many applications should prefer supported Micrometer Reactor instrumentation over building complex custom context propagation.

If an event is processed by `@TransactionalEventListener` with **reactive transactions**, the transaction context needs to be present in the **event source** (Spring 6.1+), typically via `TransactionalEventPublisher`. This is **different** from Observation Context and trace propagation. The three context types must not be conflated.

## 12. Transaction phases: what does an Observation measure and not measure?

When a critical listener is bound to a transaction, execution timing is part of its contract:

| Listener | When it runs | What Observation typically measures |
|---|---|---|
| Synchronous `@EventListener` | Immediately at publish inside transaction T1 (if inside T1) | Listener duration within the publisher call path |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Before commit | Pre-commit callback preparation time |
| `@TransactionalEventListener(AFTER_COMMIT)` | After successful commit | Post-commit processing time, **not T1 commit time** |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | After rollback | Compensation/failure-recording duration |
| `@TransactionalEventListener(AFTER_COMPLETION)` | After commit or rollback | Cleanup/post-completion duration |

Example:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    Observation.createNotStarted("app.event.listener", observations)
        .lowCardinalityKeyValue("event.type", "OrderPlaced")
        .lowCardinalityKeyValue("listener", "post-commit-indexer")
        .lowCardinalityKeyValue("phase", "after_commit")
        .observe(() -> searchIndexer.refresh(event.orderId()));
}
~~~

This is **integration code** requiring transaction beans, the event, `ObservationRegistry`, and the search indexer. If the search indexer fails, the observation may record an error, but transaction T1 has already committed so this exception **cannot roll back T1**.

Spring Javadoc notes that transaction resources may still remain temporarily bound during completion callbacks; post-commit DB writes needing a new transaction should use a separate boundary, such as calling another bean with `@Transactional(propagation = REQUIRES_NEW)`. Never treat "having an Observation" as having started a transaction, committed data, or durably published a message.

### Independent observation and error handling

For email, webhooks, message brokers, or services outside the JVM, separate:

- **Business transaction outcome:** did the order commit or roll back?
- **Listener processing outcome:** did the post-commit task succeed or fail?
- **Delivery outcome:** did the message/notification actually reach the target system?
- **Retry outcome:** is the task pending, retrying, dead-lettered, or completed?

A listener timer alone does not prove the recipient processed the message or that durable retries exist.

## 13. Designing metrics for critical listeners

With `DefaultMeterObservationHandler`, an observation named `app.event.listener` typically produces a `Timer` with low-cardinality tags and an `error` tag. The timer measures:

- `count()`: number of completed and timed invocations.
- `totalTime(TimeUnit)`: total recorded duration.
- `mean(TimeUnit)`: average duration.
- `max(TimeUnit)`: maximum duration in the current statistics window.
- Percentiles/histograms if `MeterRegistry` is configured accordingly; **do not assume p95/p99 are available on every registry**.

Example reading from `MeterRegistry`:

~~~java
Timer t = meters.find("app.event.listener")
    .tag("event.type", "OrderPlaced")
    .tag("listener", "important-order-listener")
    .tag("error", "none")
    .timer();

if (t != null) {
    System.out.println(t.count());
    System.out.println(t.mean(TimeUnit.MILLISECONDS));
}
~~~

This is an integration snippet requiring imports for `io.micrometer.core.instrument.Timer` and `java.util.concurrent.TimeUnit`. If the meter has never been recorded or there is no metric handler, `timer()` can return `null`. Never write production code assuming it always exists.

### Suggested dashboard

For a critical listener, a dashboard can include:

1. **Throughput:** invocations/sec by `listener` and `event.type`.
2. **Error rate:** error count divided by total executions, using the same tag set.
3. **Latency:** p50/p95/p99 if histograms/summaries and backend support are configured; otherwise show mean/max with clear labels.
4. **Async queue depth and task age:** dedicated metrics from the executor/broker, not derived from listener timers.
5. **Post-commit success:** ratio of post-commit tasks actually completing, distinguishing business success from callback completion.
6. **Trace exemplars:** if the metrics/tracing stack supports them, use exemplars/trace IDs to drill down into slow executions.

Set alert thresholds grounded in SLOs, such as "critical listener p95 sustained above baseline" and "error rate exceeds acceptable limit"; do not generate thousands of alerts by having one label per `orderId`.

## 14. One Observation does not equal one event

Distinguish the counting units:

~~~text
OrderPlaced(eventId=E1)
  |
  +-- Listener A execution 1 -> Observation A1
  |
  +-- Listener B execution 1 -> Observation B1
  |
  +-- Listener B retry        -> Observation B2
~~~

There is **one business event occurrence E1**, yet **three listener executions**. A listener metric dashboard counts **handler attempts**, and should not be assumed to count unique events.

To know whether an event was **finally processed successfully** after retries, you need separate metrics/state: outcome, attempt count, queue acknowledgments, or processed event records. Observations are runtime telemetry, not a durable idempotency store.

If a listener attaches `eventId` to high-cardinality trace metadata, evaluate security and sampling. If deduplication is needed, store application state keyed by `eventId`/consumer name in a database or durable store; **do not use metric counts for deduplication**.

### Retries and long-running listeners

A retry policy can either run one observation covering all attempts or create a child observation per attempt. The two options answer different questions:

- Observing the **entire operation**: total latency experienced by the caller/worker, including backoff.
- Observing **each attempt**: speed and failure rate of each downstream call.
- Both levels: useful for root-cause analysis, but distinguish names and parent/child relationships so you do not think business request volume doubled.

Do not create new timers with dynamic names based on retry index, such as unbounded `retry.1`, `retry.2`, ...; use a bounded `attempt.bucket`/`outcome` or a dedicated counter.

## 15. Recording errors properly without hiding exceptions

A listener can encounter an error without throwing outward due to a fallback policy:

~~~java
@EventListener
public void on(OrderPlaced event) {
    Observation obs = Observation.createNotStarted(
        "app.event.listener", observationRegistry)
        .lowCardinalityKeyValue("listener", "post-payment-email");

    obs.observe(() -> {
        try {
            emailGateway.send(event.orderId());
        } catch (RuntimeException ex) {
            obs.error(ex);
            retryStore.enqueue(event.orderId());
        }
    });
}
~~~

This is integration code; `emailGateway` and `retryStore` are provided by the application. If enqueueing succeeds, the listener can finish without throwing while the observation still records the email-sending error. However, **if `retryStore` itself fails**, the new exception should be handled/recorded separately rather than swallowing everything to keep metrics green.

For `@TransactionalEventListener(AFTER_COMMIT)`, callback errors do not roll back the original commit. For synchronous `@EventListener` running in T1, uncaught exceptions can roll back T1; **adding an Observation must not accidentally alter the rollback policy**. `observe(...)` preserves outward error propagation, while `obs.error(...)` only records telemetry; it is **not** equivalent to `TransactionStatus.setRollbackOnly()`.

## 16. Testing metrics and observations meaningfully

Tests should not assert fixed time durations such as "the listener must run in exactly 12ms" because OS/JVM scheduling varies. Verify:

1. The listener is invoked appropriately for the event type and condition.
2. `Timer.count()` increments accurately when the handler finishes.
3. When the handler throws an exception, the error tag differs from `none` and the exception still propagates per dispatch policy.
4. `order.id` **is absent from metric tags** produced by `DefaultMeterObservationHandler`; that key is high-cardinality metadata.
5. Scopes are closed after processing; child observations (if tracing is enabled) link parent–child properly.
6. With `@Async`, wait using a latch/await condition with a timeout; **do not assert immediately** after publish.
7. With `AFTER_COMMIT`, actually commit the transaction in the test instead of leaving the test transaction uncommitted.

### Using TestObservationRegistry

Micrometer provides dedicated testing utilities in the `micrometer-observation-test` module, including `TestObservationRegistry` and assertion helpers. A test setup can:

~~~java
TestObservationRegistry registry = TestObservationRegistry.create();
// Inject this registry into the ImportantOrderListener under test.
// Invoke the handler and verify the Observation context/name/key values/error.
~~~

This is an **illustrative test snippet**: add the test dependency and matching assertion library. Do not put `TestObservationRegistry` into main runtime code when you want real metrics.

### An integration test for errors

In the section 6 demo, the handler throws `IllegalStateException` when `fail=true`. A test can assert:

- `assertThrows(IllegalStateException.class, () -> ctx.publishEvent(...))` under the default synchronous dispatcher with no `ErrorHandler` swallowing exceptions.
- `successCount == 1` and `failureCount == 1`.
- Timers have tags `listener=important-order-listener` and `event.type=OrderPlaced`.
- No metric series has tags `order.id=ORD-OK` or `order.id=ORD-FAIL`.

If the application switches to an asynchronous dispatcher, tests must change how they wait and observe errors on the executor/worker. Never carry synchronous ordering assertions into async tests.

### Testing transaction phases

A test annotated with Spring Test's `@Transactional` typically rolls back at the end of the test. To test `@TransactionalEventListener(AFTER_COMMIT)`, actually commit (`TestTransaction.flagForCommit()` and `TestTransaction.end()` when appropriate) or invoke a service bean with its own transaction from a non-transactional test method. Otherwise, the post-commit listener will not run, and its timer will not appear.

## 17. Performance: instrument sensibly and curb telemetry explosion

Observations have overhead: creating contexts, invoking handlers, potentially creating metrics/spans, serializing tags, and exporting data. In ultra-hot listeners (hundreds of thousands of events/sec), consider:

- Instrument only **critical listeners** or boundaries with SLO/incident-debugging value.
- Keep names and low-cardinality tags within a controlled catalog.
- Configure trace sampling; metrics are typically aggregated and can therefore record counts that differ from sampled spans.
- Avoid logging stack traces on every successful observation; log errors purposefully.
- Never put bodies, tokens, emails, phone numbers, payment details, or PII in tags.
- If an observation handler throws errors, understand the registry/handler policy; observability must not break business flows simply because a telemetry backend has an outage.
- Monitor time-series cardinality cost across the product of tag dimensions (`event.type × listener × phase × outcome × region`).
- Create a shared configured `ObservationRegistry` rather than calling `ObservationRegistry.create()` inside every callback.

Micrometer provides `ObservationPredicate` to enable/disable observations by name/context and `ObservationFilter` to add/modify metadata. These are good options for cross-cutting policies. Never mutate global configuration per request or add unbounded dynamic tags.

## 18. Common mistakes

| Mistake | Why it is wrong | How to fix |
|---|---|---|
| Thinking `@EventListener` is auto-instrumented | The framework does not auto-create an Observation per event listener | Instrument critical listeners with `Observation` |
| Creating an observation without `start()/observe()` | No useful measurement lifecycle runs | Use `observe(...)` or full start/scope/stop |
| Having `ObservationRegistry` without handlers | No matching metric/trace backend integration | Configure `DefaultMeterObservationHandler` or tracing handlers |
| Confusing `MeterRegistry` with `ObservationRegistry` | Different responsibilities | Bridge them via an observation handler |
| Using `order.id` as a low-cardinality tag | Metric cardinality explodes | Put IDs into high-cardinality context if appropriate |
| Recording exception messages as tags | Dynamic/PII/unbounded | Use bounded error classes/outcomes |
| Catching errors inside the lambda without `obs.error(ex)` | Metrics report success despite downstream failures | Record errors deliberately, distinguishing recovered cases |
| Stopping the observation right after creating a `Mono` | Measures assembly rather than execution | Instrument at subscribe time and stop on terminal signals |
| Treating a listener timer as commit time | Listeners have different phases than transactions | Measure separately at the transaction/DB layer if needed |
| Using `@Async` while expecting parent trace to follow automatically | Context is lost across thread switches | Use proper context propagation/correlation |
| Thinking an observation rolls back transactions | Telemetry is not a transaction manager | Let rollback rules/phases govern transactions |
| Using metric counts to dedupe events | Counts are not durable storage | Use an `eventId`/idempotency store |
| Believing timers automatically provide p95/p99 | Distribution/backend configuration is required | Enable appropriate histograms/SLO buckets |
| Exposing emails/tokens in spans | Sensitive data exposure risk | Minimize or mask metadata before export |
| Double instrumentation when mixing AOP and manual | Causes double counting and extra overhead | Define a single boundary and clear ownership |

## 19. Implementation and operations checklist

1. **Which listeners are truly critical?** Tied to SLOs such as payment emails, ledger sync, search indexing, or fulfillment.
2. **Where is the measurement boundary?** Publisher, listener, downstream attempt, or job worker?
3. **Is the observation name stable?** For example, `app.event.listener`, containing no IDs.
4. **Are low-cardinality tags bounded?** Event type, listener name, phase, outcome.
5. **Are high-cardinality data and PII handled safely?** Not exposed in metric labels or unauthorized trace backends.
6. **Does the registry have handlers?** Which metrics, tracing, and exporters are configured?
7. **Are errors recorded accurately?** Thrown exceptions, caught/recovered cases, and timeouts/cancellations distinguished.
8. **Is sync/async behavior clear?** Dispatch strategy, executor, context propagation.
9. **Is the transaction phase right?** Post-commit observation does not mean rollback control or guaranteed delivery.
10. **Are dashboards actionable?** Throughput, error rate, latency, backlog, and trace drill-down.
11. **Do tests verify counts/errors/tags?** Covering success, error, async, and rollback paths.
12. **Are retry/durable delivery mechanisms in place?** Observation only tells "what happened"; it does not rescue failed tasks on its own.

## 20. Summary

To monitor critical listeners in Spring Framework Application Events, **create an `Observation` directly around the processing logic** using `ObservationRegistry`. Call `Observation.createNotStarted("app.event.listener", registry)`, attach low-cardinality tags such as event type and listener name, add controlled high-cardinality metadata such as business IDs, and execute `observe(...)` or manage start/scope/error/stop properly throughout the lifecycle.

With `DefaultMeterObservationHandler`, Observations can produce `Timer`s and distinguish success/error; tracing appears only when appropriate tracing handlers and exporters are configured. Pay attention to boundaries among synchronous listeners, `@Async`, Reactor, and `@TransactionalEventListener`: an observation does not alter transactions, does not automatically propagate context across every thread, and does not create durable message delivery. Use metrics/traces to detect and diagnose incidents, while using retries, idempotency, outboxes, and transaction boundaries to guarantee business correctness.

### Official documentation for reference

- [Spring Framework — Observability Support, Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/integration/observability.html) — Spring does not auto-instrument individual `@EventListener`s; context propagation when async.
- [Micrometer Reference — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html) — lifecycle, handlers, metric timers, low/high cardinality.
- [Micrometer Reference — Introduction to Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html) — `observe(...)`, errors, and tag conventions.
- [Micrometer Reference — Instrumenting Code](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html) — context, handlers, and naming.
- [Spring Framework Reference — Context Propagation](https://docs.spring.io/spring-framework/reference/integration/observability.html) — `ContextPropagatingTaskDecorator` in async event listeners.
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html) — transaction phases of `@TransactionalEventListener`.
- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — registries/metrics/exporters when using Spring Boot.
