# Enabling Logs to Trace the Multicaster in Spring Application Events

## 1. Diagnostic Objective

A common Spring Application Events issue is that a service calls `ApplicationEventPublisher.publishEvent(...)` yet no listener appears to run, or a listener runs slowly / right when a transaction rolls back without logs explaining why. In that situation, you must observe **the path from publisher -> ApplicationEventMulticaster -> listener** rather than staring at a single log line in the service.

In a typical `ApplicationContext`, Spring uses `ApplicationEventMulticaster`; the default implementation is usually `SimpleApplicationEventMulticaster`. It looks up listeners matching the event type and delivers the event to them. By default, listeners are invoked **synchronously on the publisher's thread**, unless the application enables `@Async` on listeners or changes the executor/dispatch mechanism.

From an operations standpoint, a single publish may need to answer:

1. Did code **actually** call `publishEvent(...)`?
2. What is the runtime event type, and does it match the listener signature?
3. Did the context register the listener? Are there multiple contexts or duplicate listeners?
4. Did the multicaster receive the event and select the expected listener?
5. Did the handler start processing, finish successfully, or throw an exception?
6. Which thread did the handler run on—synchronously or asynchronously?
7. If the listener is transaction-bound, is the callback waiting for commit/rollback and therefore not yet executed?
8. Was an event skipped due to an `@EventListener(condition=...)` or generic mismatch?
9. Did a single event trigger side effects multiple times due to retries or duplicate registrations?

**Enabling logs is the first step, not the sole answer.** Spring does not promise that raising one logging level yields detailed logs for every event and every listener across all versions. When exact evidence is needed, add structured logs at publisher/listener boundaries or instrument the multicaster.

## 2. Spring Event Flow Diagram and Where to Log

```text
Controller / Service / Scheduler
    |
    | (1) log PUBLISH eventId, type, thread
    v
ApplicationEventPublisher.publishEvent(event)
    |
    v
ApplicationContext
    |
    v
ApplicationEventMulticaster
    | (2) select listeners by type / ResolvableType
    | (3) dispatch to matching listeners
    |
    +----> ApplicationListener<E>
    |         | (4) START, SUCCESS, FAILURE
    |
    +----> @EventListener method adapter
    |         | (5) condition, proxy, method
    |
    +----> @Async / executor (if configured)
    |         | (6) queue, thread, errors
    |
    +----> @TransactionalEventListener adapter
              | (7) register transaction synchronization
              | (8) callback at matching phase
```

When publisher and listener are synchronous, listener execution time falls inside the `publishEvent(...)` call. If a listener throws an unchecked exception without a custom `ErrorHandler`, the exception can propagate back to the publisher. Conversely, with async execution, the publisher may return before the listener finishes; errors must be observed on the worker.

**Important distinction:** the multicaster may **have invoked the adapter** for an `@EventListener` method yet the method's SpEL condition returned `false`, so the listener body **did not run**. Thus a log saying "multicaster invoked adapter" does not always equal "business handler processed event". Add logging inside the handler body itself to tell them apart.

## 3. Enabling TRACE/DEBUG via Spring Boot Configuration

In a Spring Boot application using default logging, start with `src/main/resources/application.properties`:

```properties
# Temporary diagnostics for Spring context event classes.
logging.level.org.springframework.context.event=TRACE

# When needing broader context refresh/registration visibility:
logging.level.org.springframework.context.support=DEBUG

# Application code emitting structured event logs.
logging.level.com.example.order.events=DEBUG

# Pattern including timestamp, thread, level, logger name.
logging.pattern.console=%d{HH:mm:ss.SSS} [%thread] %-5level %logger{40} - %msg%n
```

The package name `com.example.order.events` is **only an example**; replace it with your application's actual package. Spring Boot also supports equivalent YAML configuration:

```yaml
logging:
  level:
    org.springframework.context.event: TRACE
    org.springframework.context.support: DEBUG
    com.example.order.events: DEBUG
  pattern:
    console: "%d{HH:mm:ss.SSS} [%thread] %-5level %logger{40} - %msg%n"
```

Pick **one** of the two configuration formats; there is no need to declare both at the same time.

### What You Can and Cannot Expect

- The `org.springframework.context.event` logger category enables logs emitted by Spring classes that actually log at that level, such as adapter/multicaster/event-listener infrastructure.
- **There is no guarantee** that `SimpleApplicationEventMulticaster` always prints a `dispatch event X to listener Y` line on every publish. Exact content, log levels, and messages of internal classes depend on the version.
- `org.springframework.context.support=DEBUG` can emit heavy logs about lifecycle and bean/context initialization; it is not dedicated solely to the multicaster.
- If the application uses Logback with custom logger hierarchies or filters, a `TRACE` category might still be suppressed on the console/appender you are watching.
- If listeners execute on another executor, inspect worker and thread-pool logs rather than only request-thread logs.
- In Spring MVC/Tomcat, multiple events can fire close together; use `eventId`/`aggregateId`/`traceId` to correlate logs rather than relying solely on timestamps.

**Recommendation:** start with targeted categories and short time windows, widening only as needed. Never leave `TRACE` enabled across all of `org.springframework` long-term under high load; heavy logging causes I/O pressure and can accidentally expose data.

### Temporary Overrides at Runtime/Deployment

You can pass a Spring Boot argument:

```bash
java -jar app.jar --logging.level.org.springframework.context.event=TRACE
```

Or an environment variable:

```bash
LOGGING_LEVEL_ORG_SPRINGFRAMEWORK_CONTEXT_EVENT=TRACE java -jar app.jar
```

The syntax above is for POSIX shells; in PowerShell, environment variables are set differently. For containers/Kubernetes, pass the variable in the corresponding manifest or runtime deployment. For levels targeting **a single specific class**, Spring Boot has limitations when converting environment variable names (relaxed binding can lose uppercase letters), so prefer config files or explicit system properties if the category is case-sensitive.

If the application exposes the Actuator loggers endpoint with proper permissions, log levels can be changed without restarting. **Never expose logger-mutating endpoints publicly**; enforce authentication, authorization, auditing, and time limits on `TRACE`. Without Actuator, changing configuration typically requires a restart/redeploy per your configuration management process.

## 4. What Are the Most Useful Logs?

To trace an event end-to-end, log these milestones:

| Location | Minimum fields | Conclusion you can draw |
| --- | --- | --- |
| Before `publishEvent` | `eventType`, `eventId`, `aggregateId`, `thread` | Producer started publishing |
| After `publishEvent` | `eventId`, duration, outcome | Publisher call returned or threw |
| When multicaster selects/invokes listener | `eventId`, listener identity, thread | Infrastructure is dispatching the event to a listener |
| Start of listener body | `eventId`, listener, `START`, thread | Handler code actually began |
| End of listener body | `eventId`, `SUCCESS`, duration | Tracked handler code completed normally |
| Inside catch/exception handler | `eventId`, `FAILED`, error class | Handler failed; check retry/recovery |
| Inside async executor | pool, active count, queue, rejects | Tasks are queued, congested, or rejected |
| Inside transaction-bound listener | phase, tx state, commit outcome | Callback depends on transaction milestone |

Never log raw payloads containing passwords, access tokens, cookies, or sensitive data. Prefer event metadata and approved business fields; for sensitive fields, hash or mask per policy.

### Good Log Sample

```text
PUBLISH eventId=e-81 type=OrderPlaced orderId=ORD-81
LISTENER_START eventId=e-81 listener=ProjectionUpdater
LISTENER_SUCCESS eventId=e-81 listener=ProjectionUpdater durationMs=14
PUBLISH_RETURN eventId=e-81 durationMs=16
```

This is an **illustrative pattern**, not automatic Spring output. It includes `eventId` to link steps, `durationMs` to spot slow handlers, and `listener` to avoid confusion when one event has multiple subscribers.

If the listener is async, `PUBLISH_RETURN` may appear **before** `LISTENER_START` or `LISTENER_SUCCESS`. If both synchronous and asynchronous listeners handle the same event type, logs from the two paths can interleave.

## 5. Runnable Java 17+ Example: Seeing Multicast to @EventListener

This example uses **Spring Framework 6.2.13, Java 17+, Maven, and Logback**. No Spring Boot, database, or web server is required; the goal is isolating a single `ApplicationContext` to observe the mechanism.

We build:

- A concrete event `OrderAcceptedEvent extends ApplicationEvent`.
- A bean with an `@EventListener` method.
- An extended `SimpleApplicationEventMulticaster` logging at **listener adapter invocation** level.
- Loggers for publisher, multicaster, and listener.
- A JUnit integration test verifying real Spring event dispatch.

**Note:** Subclassing the multicaster is an instrumentation technique **for controlled demos/investigations**, not a mandatory Spring requirement. In production, most apps only need logs at publisher/listener boundaries plus standard metrics/tracing, avoiding changes to dispatch infrastructure unless necessary.

### 5.1. Project Structure

```text
multicaster-diagnostics/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/events/MulticasterDiagnostics.java
    │   └── resources/logback.xml
    └── test/
        └── java/example/events/MulticasterDiagnosticsTest.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>multicaster-diagnostics</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.13</version>
        </dependency>

        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.18</version>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. src/main/resources/logback.xml

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger{40} - %msg%n</pattern>
        </encoder>
    </appender>

    <!-- Enable TRACE for Spring event infrastructure in this demo. -->
    <logger name="org.springframework.context.event" level="TRACE"/>

    <!-- Logs emitted by the example classes themselves. -->
    <logger name="example.events" level="INFO"/>

    <root level="WARN">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Appenders in real projects may have additional filtering/thresholds; here only a single `ConsoleAppender` is used. The pattern prints `%thread` so threads are visible. Setting `TRACE` does not add logs where Spring itself has no log statements.

### 5.4. src/main/java/example/events/MulticasterDiagnostics.java

```java
package example.events;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;

public class MulticasterDiagnostics {

    private static final Logger log =
            LoggerFactory.getLogger(MulticasterDiagnostics.class);

    public static final class OrderAcceptedEvent extends ApplicationEvent {
        private final String orderId;

        public OrderAcceptedEvent(Object source, String orderId) {
            super(source);
            this.orderId = Objects.requireNonNull(orderId);
        }

        public String getOrderId() {
            return orderId;
        }
    }

    public static final class OrderHandler {
        private final AtomicInteger handled = new AtomicInteger();
        private static final Logger handlerLog =
                LoggerFactory.getLogger(OrderHandler.class);

        @EventListener
        public void on(OrderAcceptedEvent event) {
            handled.incrementAndGet();
            handlerLog.info("HANDLED id={}", event.getOrderId());
        }

        public int handledCount() {
            return handled.get();
        }
    }

    public static final class LoggingMulticaster
            extends SimpleApplicationEventMulticaster {

        private static final Logger multicasterLog =
                LoggerFactory.getLogger(LoggingMulticaster.class);

        @Override
        protected void invokeListener(
                ApplicationListener<?> listener,
                ApplicationEvent event) {

            if (!(event instanceof OrderAcceptedEvent accepted)) {
                super.invokeListener(listener, event);
                return;
            }

            multicasterLog.info(
                    "MULTICASTER invoke id={} listener={}",
                    accepted.getOrderId(),
                    listener.getClass().getSimpleName());

            try {
                super.invokeListener(listener, event);

                multicasterLog.info(
                        "MULTICASTER returned id={}",
                        accepted.getOrderId());
            } catch (RuntimeException ex) {
                multicasterLog.error(
                        "MULTICASTER failure id={} error={}",
                        accepted.getOrderId(),
                        ex.getClass().getSimpleName());
                throw ex;
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        // Fixed bean name that ApplicationContext looks up to use
        // a custom ApplicationEventMulticaster for the context itself.
        @Bean("applicationEventMulticaster")
        SimpleApplicationEventMulticaster applicationEventMulticaster() {
            return new LoggingMulticaster();
        }

        @Bean
        OrderHandler orderHandler() {
            return new OrderHandler();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.register(AppConfig.class);
            context.refresh();

            log.info("PUBLISH id=ORD-7");
            context.publishEvent(
                    new OrderAcceptedEvent("demo", "ORD-7"));
            log.info("PUBLISH returned id=ORD-7");
        }
    }
}
```

### 5.5. Running the Program

In the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.events.MulticasterDiagnostics
```

This is a synchronous run publishing one `OrderAcceptedEvent` from the example code. **Five messages generated by the demo code**, in logical order:

```text
PUBLISH id=ORD-7
MULTICASTER invoke id=ORD-7 listener=ApplicationListenerMethodAdapter
HANDLED id=ORD-7
MULTICASTER returned id=ORD-7
PUBLISH returned id=ORD-7
```

With `logback.xml`, each message above is formatted on a full line with **timestamp, thread, level, and logger name**. `ApplicationListenerMethodAdapter` is the typical adapter class name for `@EventListener` methods in Spring 6.2; if Spring changes internal implementations, the `listener=...` field may differ. The example code does not rely on adapter name strings for business logic.

Other logs **emitted by Spring infrastructure TRACE may interleave**; do not match terminal output verbatim against exactly five lines. What to verify is the relationship **PUBLISH -> MULTICASTER invoke -> HANDLED -> MULTICASTER returned -> PUBLISH returned** for event `ORD-7`.

**Note:** the example uses the default synchronous executor and no `@Async`; the log inside `invokeListener(...)` shows the adapter was invoked by Spring's multicaster on this pass. If the handler declares `@EventListener(condition=...)`, `MULTICASTER returned` may still appear even when the handler method is filtered out and does not print `HANDLED`.

### 5.6. Meaning of Those Log Milestones

- `PUBLISH`: application code reached right before `context.publishEvent(...)`; does not yet prove the listener was called.
- `MULTICASTER invoke`: Spring selected a matching listener to invoke at the multicaster layer. The printed class may be an adapter/proxy rather than the original business bean.
- `HANDLED`: the actual business handler method executed and reached the log line; does not prove all external side effects completed if the log sits before the side effect.
- `MULTICASTER returned`: the callback adapter returned normally at the instrumentation point. If the adapter submitted async work, returning **does not mean** the task finished.
- `PUBLISH returned`: the publisher API returned normally; for synchronous dispatch here, callbacks have already returned.

To measure duration, capture `System.nanoTime()` before `super.invokeListener(...)` and compute elapsed time in `finally`; **do not** use a wall-clock timestamp for exact durations since system clocks can jump.

## 6. Integration Test Confirming Wiring Rather Than Just Reading Logs

During troubleshooting, logs provide operational evidence while tests prove behavior.

### 6.1. src/test/java/example/events/MulticasterDiagnosticsTest.java

```java
package example.events;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MulticasterDiagnosticsTest {

    @Test
    void matchingApplicationEventIsDeliveredOnce() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             MulticasterDiagnostics.AppConfig.class)) {

            var handler = context.getBean(
                    MulticasterDiagnostics.OrderHandler.class);

            assertEquals(0, handler.handledCount());

            context.publishEvent(
                    new MulticasterDiagnostics.OrderAcceptedEvent(
                            this, "ORD-TEST"));

            assertEquals(1, handler.handledCount());
        }
    }

    @Test
    void unrelatedPayloadDoesNotInvokeOrderHandler() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             MulticasterDiagnostics.AppConfig.class)) {

            var handler = context.getBean(
                    MulticasterDiagnostics.OrderHandler.class);

            context.publishEvent("a plain string payload");

            assertEquals(0, handler.handledCount());
        }
    }
}
```

Run:

```bash
mvn test
```

The project defines **2 JUnit test methods**; when successful, Maven Surefire reports 2 tests run with 0 failures/errors. Timestamps, thread names, and log durations vary across machines, so tests **assert handler invocation counts** rather than snapshot-matching log timestamps.

The first test proves infrastructure locates the `@EventListener` and invokes the method once. The second test emits a `String` payload, which Spring wraps in `PayloadApplicationEvent<String>`; the handler accepts only `OrderAcceptedEvent` and is not triggered.

This test suite does not cover propagation, ordering across multiple listeners, retries, or transaction callbacks. With an executor-backed app, synchronize tests using a latch/condition with a timeout rather than asserting counts immediately after `publishEvent(...)`.

## 7. When Enabling TRACE Produces No Event Logs

This is common; do not jump to concluding logging is broken.

### Step 1: Verify the Effective Log Level

If using SLF4J/Logback, a logger may be affected by configuration:

- Wrong logger name: e.g., running a Spring class outside the package you enabled.
- A more specific or parent logger level overriding your setting.
- Appender thresholds/filters dropping `DEBUG`/`TRACE` records.
- No log statement exists on the actual code path, or messages log at another level.
- Application started with a different config/profile than the one you edited.
- External logging configuration overriding resources inside the JAR.

**Try emitting an intentional log in an application package**, or in the standalone example verify the `INFO`-level `PUBLISH` line appears. If that line does not appear, fix logging/appender configuration before suspecting multicasting.

### Step 2: Enable Narrow Categories

With Spring Boot:

```properties
logging.level.org.springframework.context.event.SimpleApplicationEventMulticaster=TRACE
logging.level.org.springframework.context.event.AbstractApplicationEventMulticaster=TRACE
```

This enables levels on exact classes, yet **does not guarantee these two classes emit a log on every dispatch**. Use it to capture whatever internal logs exist; if your goal is **proof for every event and every listener**, use instrumentation/structured logging as in section 5.

### Step 3: Check Which Context Actually Publishes the Event

A multi-context application can have a separate multicaster per context. If you customize `applicationEventMulticaster` in a child context while events are published in another context, logs from that custom multicaster will not appear. Verify beans/contexts and where the publisher was injected.

### Step 4: Check the Runtime Event Type

```java
Object event = ...; // The actual object being published.
log.debug("eventType={}", event.getClass().getName());
publisher.publishEvent(event);
```

This is an **illustrative snippet**, not a complete file. If the event is a record/POJO, Spring can wrap it internally in `PayloadApplicationEvent`. If the listener uses `ApplicationListener<ConcreteApplicationEvent>` while the producer sends a different POJO type, the callback is never selected even when logging works.

### Step 5: Distinguish "Listener Selected" from "Method Body Ran"

- With `@EventListener(condition="...")`, the adapter may be called while the condition evaluates false.
- With generic events, insufficient `ResolvableType` metadata can prevent listener matching.
- With `@TransactionalEventListener`, the method may be registered to wait for `AFTER_COMMIT` instead of running immediately.
- With `@Async`, the adapter or proxy submits a task and returns, while the method executes later on a worker.

Do not try to solve everything by turning up log levels; inspect **filtering and lifecycle mechanisms** directly.

## 8. Diagnosing When @Async or a Multicaster Executor Is Present

Two distinct async strategies:

**Strategy A — @Async on the listener method**

```java
@Async("eventExecutor")
@EventListener
public void on(OrderAcceptedEvent event) {
    // Method is submitted to the executor by the async proxy.
}
```

Requirements: `@EnableAsync`, an executor bean named `eventExecutor`, and the listener must be a Spring-managed bean. Calling the method via `this.on(...)` or instantiating with `new` outside Spring bypasses the annotation.

**Strategy B — Executor on the multicaster**

```java
@Bean("applicationEventMulticaster")
SimpleApplicationEventMulticaster multicaster(
        @Qualifier("eventExecutor") TaskExecutor executor) {

    SimpleApplicationEventMulticaster m =
            new SimpleApplicationEventMulticaster();
    m.setTaskExecutor(executor);
    return m;
}
```

This is an **illustrative configuration snippet** requiring imports for `@Bean`, `@Qualifier`, `TaskExecutor`, and the multicaster class. Do not add this **at the same time** as the `applicationEventMulticaster` bean in section 5's example; choose or replace a single bean with that standard name.

When an executor is set on the multicaster, listeners **supporting asynchronous execution** can be submitted to workers. Certain listeners—especially transaction-bound listeners—must be called on the publisher thread to register synchronization and are not arbitrarily offloaded. In Spring Framework 6.1+, `supportsAsyncExecution()` metadata influences this decision.

### Log Set to Collect When Suspecting Async

```text
PUBLISH eventId=e-17 thread=http-nio-8080-exec-7
SUBMIT eventId=e-17 executor=event-worker queueSize=12
HANDLER_START eventId=e-17 thread=event-worker-3
HANDLER_SUCCESS eventId=e-17 thread=event-worker-3 durationMs=44
```

This is a **sample set of fields to instrument**, not logs auto-generated by Spring. If `SUBMIT` appears without `HANDLER_START`, investigate queues, executor shutdown, rejections, waiting tasks, or missing context propagation.

When an executor uses `CallerRunsPolicy` under overload, the task may execute on the submitting thread itself, so the thread name does not change despite having an executor configured. Observing the "same thread" is not enough to conclude `@Async` is broken; inspect pool state and rejection policies.

For `void @Async` listeners, exceptions usually do not propagate to the publisher; configure `AsyncUncaughtExceptionHandler` or catch/record errors inside the handler. Never treat a `"publish success"` log line as a substitute for business completion.

## 9. Diagnosing Transaction-Bound Listeners

Events published **inside an active transaction** can be received by `@TransactionalEventListener`. Example:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderAcceptedEvent event) {
    // Runs after the transaction commits.
}
```

This is an **illustrative method**, assuming Spring transaction event imports and declaration inside a bean.

Things to log:

1. When the event is published and whether a current transaction is active.
2. Which listener phase is configured: `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, or `AFTER_COMPLETION`.
3. Whether the transaction actually committed or rolled back.
4. Whether the handler opens a new DB write transaction when needed upon execution.
5. When no transaction is active, transactional listeners **are not called by default**, unless `fallbackExecution=true`.

When the multicaster "invokes" an event once, it may merely cause the adapter to register synchronization; the business callback only runs after commit. Do not confuse `MULTICASTER returned` timing with `AFTER_COMMIT listener completed`.

During a post-commit callback, the original transaction has already committed; an exception in post-processing **cannot automatically roll back** that DB change. If DB writes are needed after commit, delegate to another service with a new transaction, e.g., `@Transactional(propagation = Propagation.REQUIRES_NEW)` through a Spring proxy, or use an appropriate `TransactionTemplate`.

**If events must not be lost if the process dies after commit**, do not rely solely on `@TransactionalEventListener` or logs: use a transactional outbox/durable queue and design retries/idempotency.

## 10. Tracking Errors in SimpleApplicationEventMulticaster

By default, `SimpleApplicationEventMulticaster` invokes listeners synchronously; an unchecked exception from one listener can propagate to the publisher and interrupt dispatch depending on the setup. You can configure an `ErrorHandler` to define a custom policy:

```java
@Bean("applicationEventMulticaster")
SimpleApplicationEventMulticaster applicationEventMulticaster() {
    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();

    multicaster.setErrorHandler(error ->
            logger.error("Application listener failed", error));

    return multicaster;
}
```

This is an **illustrative snippet**, assuming the configuration class has a `logger` field. If used, it **replaces** section 5's multicaster bean rather than declaring a duplicate bean name.

**Crucial:** an `ErrorHandler` that merely logs and returns can prevent exceptions from **continuing to propagate to the publisher**, differing from the default policy. This can let the original business transaction commit even when a side effect failed. Do not alter error policies just to get more logs without deciding exact semantics.

When needing both logging and exception propagation, you can use an `ErrorHandler` that rethrows appropriately; verify how exceptions cross the multicaster and transaction boundaries. A less invasive option is logging inside the listener and rethrowing per contract, or instrumenting without altering exception propagation.

Typical model:

```text
Publisher
    |
    v
Multicaster
    |
    +--> Listener A succeeds
    |
    +--> Listener B throws
    |         |
    |         v
    |     ErrorHandler (if configured)
    |         |
    |         +--> log/swallow only: publisher may not see error
    |         +--> throw: publisher may see error
    |
    +--> Listener C: whether it runs depends on
                       error handling and dispatch mode
```

Therefore, log **listener identity, eventId, exception class, and error policy**, not just floating stack traces. A failure in listener B does not automatically tell you whether other listeners ran or were skipped.

## 11. Verifying Whether the Listener Was Registered

No callback does not mean the multicaster failed to exist. Common causes:

- Bean not registered or outside component scan.
- `@EventListener` placed on an object created via `new` rather than a Spring bean.
- Using `ApplicationListener<WrongEvent>`, similarly named yet different type.
- POJO/record wrapped in `PayloadApplicationEvent`, while the listener expects a wrapper or different business class.
- Generic event lacking accurate `ResolvableType` metadata.
- Event published **before the context was ready to register listener beans**.
- Spring application has parent/child contexts and the event was published in an unexpected context.
- `@EventListener(condition=...)` evaluates false.
- Callback is `@TransactionalEventListener(AFTER_COMMIT)` and the transaction has not committed, rolled back, or never existed.
- Async executor accepted the task, yet the task has not started or was rejected.

Do not dump the entire bean graph in production to find one listener. Isolate with a small integration test using real configuration, publish a test event, and confirm the handler is invoked. If logs from a custom multicaster never appear, verify the standard **`applicationEventMulticaster`** bean is declared in the right context.

### Applications with Multiple ApplicationContexts

Each context can manage its own multicaster. With hierarchies, events can propagate up to the parent, letting listeners in multiple contexts see the event. A custom multicaster in context A does not automatically instrument context B.

Include `contextId` or appropriate origin identifiers in logs when investigating. Avoid treating `ApplicationEvent.getSource()` as a guarantee that it is always the context; many business events use application-defined sources.

## 12. When TRACE Is Too Noisy: Structured Logging and Metrics

Enabling internal logs can generate thousands of lines during startup or high-throughput business flows. For long-term operations, distinguish:

**Temporary diagnostic logging:**
- Enable only during a short investigation window.
- Target the exact packages/classes needed.
- Narrow back down once the root cause is found.
- Enforce log retention limits and access controls.

**Long-term structured logging:**
- Log `eventId` and listener name at `START`/`SUCCESS`/`FAILED`.
- Log duration and error category, without dumping sensitive full payloads.
- Attach `traceId`/`correlationId` to trace across threads and systems.
- Record idempotency/dedup state when events can be redelivered.

**Long-term metrics:**
- `events.published`: events published by type.
- `listener.started`: handler start counts.
- `listener.succeeded`: successful handler completions.
- `listener.failed`: handler failures.
- `listener.duration`: duration distribution.
- `executor.queue.size`, active/rejected: async bottleneck indicators.
- `outbox.pending`/lag: if a durable delivery pipeline exists.

These are **suggested application metric names**, not built-in Spring metrics. With Micrometer, tag by **event type, listener name, and result**; never attach `eventId`/`orderId` as tags due to excessive cardinality. Keep detailed IDs in controlled logs/traces.

### Tracing Across Threads

MDC is usually thread-bound and does not automatically cross executors. If the publisher logs `traceId=t-1` while an async listener lacks `traceId`, the event is not necessarily lost; **context propagation may simply be missing**. Use `TaskDecorator`/Micrometer Context Propagation where appropriate, or carry an explicit correlation ID inside the event. Never blindly copy transaction `ThreadLocal`s onto async workers.

## 13. Log-Based Debugging Checklist

| Symptom | Hypothesis to check | Useful evidence |
| --- | --- | --- |
| No `PUBLISH` | Producer never ran, code branch unreached | Request/job tracing, breakpoint |
| `PUBLISH` exists yet no multicaster log | Logger category has no statement, custom bean in wrong context, or log level inactive | Logger config, bean name, `contextId` |
| Multicaster invoked yet no `HANDLED` | `@EventListener condition` false, async task pending, transaction waiting | Body logs, executor/tx phase |
| `HANDLED` exists yet no `SUCCESS` | Exception, timeout, deadlock, blocked thread | `FAILED` logs, thread dumps, dependency metrics |
| `RETURN` appears before `HANDLED` | Listener is likely async | Thread name, executor, queue |
| `PUBLISH_RETURN` logged yet business step failed | Async/recovery/`ErrorHandler` suppressed error | Handler status, business outcome |
| Multiple `HANDLED` for one event | Multiple listeners/contexts, retries/duplicate publishes | `eventId`, `contextId`, attempt, bean identity |
| Missing MDC data in `HANDLED` | Thread switch without context propagation | `TaskDecorator`, `traceId` in event |
| `AFTER_COMMIT` listener never runs | No tx, rollback, wrong phase | Tx outcome, `fallbackExecution` |
| Raising `TRACE` adds no dispatch logs | Class/version logs nothing at that level | Explicit instrumentation and tests |
| Event reaches wrong handler | Broad type/generic/wrapper mismatch | Runtime class, `ResolvableType`, method signature |

### A 7-Step Procedure

1. Identify the exact `eventType`/`eventId` emitted by the producer.
2. Enable **narrow** logger categories for application packages and Spring event infrastructure.
3. Log at the publisher before and after `publishEvent(...)`, measuring duration.
4. Log at the start/end of the listener body and on exceptions, using the same `eventId`.
5. If still insufficient, instrument the multicaster in the right context **without** inadvertently altering error policy or ordering.
6. Inspect threads/executors, listener conditions, transaction phases, and generic types if logs look abnormal.
7. Add a regression integration test: publish a production-like object and assert real listener invocation; revert temporary logging levels afterward.

## 14. Common Mistakes

**Mistake 1 — Treating TRACE as a switch that prints every event.** Spring does not guarantee a log statement per dispatch. Add targeted logs or instrumentation when needed.

**Mistake 2 — Enabling unbounded TRACE across all of Spring.** Generates huge logs, load, and data exposure. Use narrow categories, short windows, and proper access control.

**Mistake 3 — Logging only in the publisher.** `publishEvent(...)` being called does not prove handlers ran; observe listeners or the multicaster.

**Mistake 4 — Logging only in the multicaster adapter.** `@EventListener(condition)` may skip the method; async adapters may merely submit tasks. Add logs in the handler body.

**Mistake 5 — Relying on thread names as an eventId.** Pools reuse threads, so names repeat. Use explicit event/correlation IDs.

**Mistake 6 — Adding an exception-swallowing ErrorHandler just to add logs.** Alters error semantics and can let transactions commit unexpectedly.

**Mistake 7 — Using multicast timing to conclude AFTER_COMMIT already ran.** For transactional listeners, business callbacks are deferred until the matching phase.

**Mistake 8 — Overlooking multiple contexts.** A custom `applicationEventMulticaster` bean in one context does not trace all other contexts.

**Mistake 9 — Ignoring payload wrappers.** POJOs can be wrapped in `PayloadApplicationEvent`; log exact types at publisher and handler.

**Mistake 10 — Reading startup logs and concluding business events never fired.** Internal context events occur at different times; filter by distinct `eventId`/types.

**Mistake 11 — Failing to observe executor errors.** Async tasks can be rejected before the listener body runs; watching only `HANDLED` is insufficient.

**Mistake 12 — Testing only log strings.** Logs are observational tools; logic and wiring require real assertions via unit/integration tests.

## 15. Operations Checklist Before Closing an Investigation

1. Are `PUBLISH` and `PUBLISH_RETURN` logged for the same `eventId`?
2. Does the listener log `START`/`SUCCESS`/`FAILED` at **entry and exit of its body**?
3. Are logging levels, categories, and appenders verified on the running instance?
4. Is `applicationEventMulticaster` confirmed to belong to the right context?
5. Have you distinguished the listener adapter being invoked from the handler method body actually running?
6. Do thread names, executors, queues, rejections, and `@Async` explain the log ordering?
7. If transactional, are phase and commit/rollback verified?
8. Are the runtime type and generic metadata of event/handler accurately recorded?
9. Are sensitive data, log retention, and `TRACE` access permissions protected?
10. Is there a Spring-context regression test after fixing the incident?
11. Are business outcomes and retry counts recorded instead of just publish counts?
12. Have temporary log levels been reverted and unintended `ErrorHandler` changes avoided?

**Conclusion:** Enabling `TRACE` on `org.springframework.context.event` is an initial observation step, **not a guarantee that Spring prints every multicast**. For accurate diagnosis, combine logs across publisher, multicaster, and listener with `eventId`/`traceId`, thread/executor details, exceptions, and transaction status. Use temporary instrumentation when necessary, verify with integration tests, and dial logs back down for stable operations.

## References

- [Spring Framework 6.2 — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html): default `ApplicationEventMulticaster`, registration, `@EventListener`, and asynchronous listeners.
- [Spring Framework 6.2 — SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): `setTaskExecutor`, `setErrorHandler`, and `invokeListener`.
- [Spring Framework 6.2 — AbstractApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/context/event/AbstractApplicationEventMulticaster.html): registering and selecting matching listeners.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): no auto-observation for `@EventListener` and thread context propagation.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): handling events bound to transaction phases.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): configuring log levels, patterns, and loggers.
- [JUnit 5 User Guide](https://docs.junit.org/5.11.4/user-guide/): dispatch testing and assertions.