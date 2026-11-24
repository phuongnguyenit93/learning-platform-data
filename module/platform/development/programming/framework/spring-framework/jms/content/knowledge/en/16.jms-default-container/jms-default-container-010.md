# ErrorHandler and ExceptionListener in DefaultMessageListenerContainer (Spring JMS)

> **Parent topic:** Default container — Spring Framework JMS.  
> **Goal:** Distinguish `org.springframework.util.ErrorHandler` and `jakarta.jms.ExceptionListener`; understand which channels carry business errors, message conversion errors, JMS/infrastructure errors, and connection errors; configure both callbacks via `DefaultJmsListenerContainerFactory` / `DefaultMessageListenerContainer`; and design rollback, redelivery, DLQ, connection recovery, and system observability without losing messages.

**Version context:** Spring Framework 6.2.x, Spring Boot 3.5.x, Jakarta Messaging 3.1, Java 17+, and Apache ActiveMQ Artemis examples. APIs use `jakarta.jms` (not `javax.jms` from older Java EE/JMS stacks).

**Big idea:** Both callbacks primarily **detect and report errors**. They **do not themselves decide** whether the JMS transaction commits, the message is ACKed, or how many retries occur. Those decisions belong to the listener container, session/transaction configuration, and broker policies.

## 1. All Called "Errors" Yet Living at Different Layers

In Spring JMS, a message passes through multiple layers:

~~~text
Producer -> Broker / Queue
               |
               v
      JMS Connection / Session / Consumer
               |
       DefaultMessageListenerContainer
               |
      JMS-to-Spring message conversion
               |
            @JmsListener
               |
          Business handler
               |
      JMS commit / rollback / ACK
~~~

Depending on where an error occurs, the exact same symptom—"the listener is not getting work done"—can have very different causes:

1. **Business error:** the handler throws `IllegalStateException` due to DB failure, invalid data, downstream API timeout, or violated invariants.
2. **Conversion/binding error:** JSON violates schema, `@Header` is missing, or `MessageConverter` throws an exception before entering the handler body.
3. **`JMSException` on the receive path:** creating a consumer/session, receiving a message, JMS transaction operations, or JMS API calls fail.
4. **Asynchronous connection error:** the provider detects a connection failure and may notify via `jakarta.jms.ExceptionListener` attached to the `Connection`.
5. **Startup or recovery error:** broker unavailable, wrong URL/credentials, missing destination, session recreation, connection retries, or resource exhaustion.
6. **Operational error:** queue backlog, expired message TTL, poison message routed to DLQ, stopped listener, zero concurrency, or dead workers.
7. **Publisher error:** `JmsTemplate.convertAndSend(...)` throws an exception on the sending thread, outside any independent listener container's callbacks.

Therefore, designing with only `ErrorHandler` or only `ExceptionListener` is **not sufficient** for resilience. First classify errors and understand **when commit/rollback happens**.

## 2. Quick Comparison: ErrorHandler vs. ExceptionListener

| Criterion | Spring `ErrorHandler` | Jakarta JMS `ExceptionListener` |
| --- | --- | --- |
| Interface type | `org.springframework.util.ErrorHandler` | `jakarta.jms.ExceptionListener` |
| Method | `handleError(Throwable t)` | `onException(JMSException ex)` |
| Data scope | `Throwable`, covering many runtime/adapter errors | `JMSException`, JMS-related errors forwarded to the callback |
| When used in Spring container | Monitors uncaught errors during JMS message processing | Receives `JMSException` notifications through the listener container per Spring API |
| When attached directly to JMS Connection | Not a `Connection` callback | Provider may invoke **asynchronously** when the connection encounters trouble |
| Automatically rolls back JMS session? | **No** | **No** |
| Automatically routes message to DLQ? | **No** | **No** |
| Automatically fixes the connection? | **No** | **No** |
| Where configured on Spring factory | `factory.setErrorHandler(...)` | `factory.setExceptionListener(...)` |
| Where configured on container | `container.setErrorHandler(...)` | `container.setExceptionListener(...)` |
| Typical purpose | Logs, metrics, alerts for message-processing errors | Logs, metrics, alerts for JMS-related errors |
| Common trap | Thinking the error callback must rethrow to trigger rollback | Thinking the callback catches every business exception or every broker outage |

**Very important:** `DefaultMessageListenerContainer` is a **polling message listener container** with built-in self-recovery. The `ExceptionListener` callback on the Spring container and the asynchronous callback invoked by the JMS provider on a `Connection` are **two API contexts to distinguish**; do not assume every broker network disconnect invokes the exact same callback at the exact same moment across all implementations.

### 2.1. Exact Java Signatures

~~~java
@FunctionalInterface
public interface ErrorHandler {
    void handleError(Throwable t);
}
~~~

This is a **simplified signature for learning**, not a Spring definition that the application should copy. Spring already provides `org.springframework.util.ErrorHandler`.

~~~java
@FunctionalInterface
public interface ExceptionListener {
    void onException(JMSException exception);
}
~~~

This is a **simplified signature** of `jakarta.jms.ExceptionListener`, not code to redefine with the same name. `JMSException` belongs to `jakarta.jms`.

### 2.2. Why Do Parameter Types Differ?

`Throwable` covers runtime errors inside listeners and certain adapter-layer errors. `JMSException` is a specialized checked exception of the JMS provider/API, typically carrying `getErrorCode()`, `getLinkedException()`, and `getCause()` for diagnostics.

You cannot funnel every business `IllegalArgumentException` into `onException(JMSException)` without wrapping it as a `JMSException` in your own layer; doing so usually muddies error classification.

## 3. Error-Handling Flow in AbstractMessageListenerContainer

`DefaultMessageListenerContainer` extends `AbstractPollingMessageListenerContainer` and `AbstractMessageListenerContainer`. Spring 6.2 Javadoc describes that errors thrown by a listener **are not automatically propagated raw to the JMS provider** as in a bare callback API; the container handles acknowledgment/transactions and records the error.

When a handler throws an unchecked exception:

~~~text
Receive JMS Message
       |
       v
Invoke @JmsListener / MessageListener
       |
       +--> success --> commit/ack per session policy
       |
       +--> error
               |
               v
       rollback if transaction/ack mode requires
               |
               v
       Spring handleListenerException(Throwable)
               |
       +-------+--------+
       |                |
    ErrorHandler     Default log if
    (if present)     no handler
~~~

Exact ordering for specific exception types, transaction managers, and container subtypes must be read against the API/source of your running version. The **unchanging** design rule is: an error-observation callback **must not be treated as a switch to re-decide commit** after the container has already handled it.

### 3.1. A JMSException Can Pass Through Both Callbacks

`AbstractMessageListenerContainer` Javadoc notes that when a `JMSException` arises in the listener/invocation infrastructure and enters the container's error dispatch, `ExceptionListener` is notified, and **then** `ErrorHandler` may also be invoked. Therefore:
- Do not treat the two counters as mutually exclusive error classes.
- A single `JMSException` can emit **two log/metric events**.
- To avoid double counting, classify/correlate events by context or label metrics appropriately.
- Do not claim every asynchronous provider error flows through the exact same dispatch path as a `JMSException` inside a listener.

### 3.2. When Only ErrorHandler Applies

If the handler throws:

~~~java
throw new IllegalStateException("Database temporarily unavailable");
~~~

this is an unchecked application exception. It fits `ErrorHandler`'s scope, **not** `jakarta.jms.ExceptionListener`, which by contract only accepts `JMSException`. A properly registered `ExceptionListener` will not be called in this scenario, and that is **not** a sign of misconfiguration.

### 3.3. If No ErrorHandler Is Configured

The Spring container usually logs the exception via default behavior, without shutting down the JVM just because a message handler threw an unchecked exception. This can leave the service looking "still healthy" while the broker repeatedly redelivers a poison message. Installing a custom `ErrorHandler` helps emit metrics/alerts, yet **does not replace** DLQ/transaction configuration.

## 4. ErrorHandler API and Proper Responsibilities

In Spring Framework:

~~~java
import org.springframework.util.ErrorHandler;

ErrorHandler handler = throwable -> {
    // Log/metric/trace; handle quickly, thread-safe.
};
~~~

This is a Java snippet, not a standalone app. The `throwable` parameter may be a business exception or a wrapper exception generated by Spring's adapter. Do not classify solely by the outer exception class; walk `getCause()` with a bounded depth if needed.

### 4.1. What to Do

- Record a clear error category (`CONVERSION`, `BUSINESS_TRANSIENT`, `BUSINESS_PERMANENT`, `JMS_API`).
- Log exception class, root cause, and stack trace with appropriate sampling/rate limits.
- Increment counters by listener factory/endpoint or destination known from context.
- Mark tracer spans/Micrometer observations if available.
- Alert when error rate crosses thresholds rather than alerting per message.
- Protect the handler from slow work: emit logs/metrics quickly, never make blocking external network calls.
- Keep the handler **thread-safe** because multiple JMS listeners can share the same factory/callback.
- Avoid logging payloads containing PII, tokens, or user data; log sanitized message metadata when available.

### 4.2. What Not to Do

- Do not call `session.commit()`, `rollback()`, `acknowledge()`, or `close()` from `ErrorHandler` without a session-management contract.
- Do not manually resend the raw message from the throwable without JMS message/transaction context: easy to create duplicates.
- Do not call `container.stop()` or exit the JVM inside the callback for every exception type.
- Do not catch all errors inside the listener and return normally just to "avoid triggering `ErrorHandler`"; that can cause the transaction to commit even though business work failed.
- Do not let `ErrorHandler` rethrow an unchecked exception as a way to "request a retry": the container already handles rollback, and throwing from the callback can cause secondary errors or mask the root cause.
- Do not use `ErrorHandler` as a global business exception mapper for REST/APIs/scheduled tasks; its scope is the configured JMS listener container.

### 4.3. Observation-Only Callback Example

~~~java
@Bean
ErrorHandler listenerErrorHandler() {
    return ex -> {
        String category =
                ex instanceof IllegalArgumentException
                        ? "VALIDATION_OR_CONTRACT"
                        : "LISTENER_OR_ADAPTER";
        System.err.println("JMS_ERROR category=" + category
                + " class=" + ex.getClass().getSimpleName());
    };
}
~~~

This is a **Spring `@Bean` method**, not a standalone Java program. It requires `@Bean` and `ErrorHandler` imports; in production replace stdout with structured logging and metrics. Do not infer wrapped `IllegalArgumentException` causes from the outermost exception alone.

## 5. ExceptionListener API in Jakarta Messaging

`jakarta.jms.ExceptionListener` is for cases where the JMS provider/connection detects a serious asynchronous error:

~~~java
import jakarta.jms.ExceptionListener;
import jakarta.jms.JMSException;

ExceptionListener listener = exception -> {
    // Callback from JMS; work quickly and thread-safely.
    String code = exception.getErrorCode();
    Exception linked = exception.getLinkedException();
    // Log/metrics; do not rely on the failed connection.
};
~~~

The JMS specification states:
- The provider may report a **Connection problem** via `Connection.getExceptionListener().onException(JMSException)` when no other appropriate place exists to report the error.
- If a JMS call on a calling thread already throws an exception **synchronously**, the provider must not treat calling the asynchronous callback as a substitute for throwing on that thread.
- The provider should attempt to resolve connection issues before notifying the callback.
- Callbacks on **the same Connection** are serialized by the provider; **the same listener object attached to multiple Connections** can still be invoked concurrently.
- A callback firing **does not guarantee** the connection remains usable for further JMS operations.

### 5.1. Example Attached to a Connection You Own

~~~java
// Java snippet in a direct JMS app, not using a shared
// connection managed by a Spring listener container.
Connection connection = connectionFactory.createConnection();
try {
    connection.setExceptionListener(ex -> {
        System.err.println("ASYNC_JMS_FAILURE code="
                + ex.getErrorCode());
    });

    connection.start();
    // Create Session/Consumer and use per app lifecycle.
} finally {
    connection.close();
}
~~~

Requires imports `jakarta.jms.Connection`, `ConnectionFactory`, `JMSException`; the enclosing method must declare or catch `JMSException`. This is an **illustrative code snippet**, not a standalone class. `connection.setExceptionListener` must follow **ownership**: never grab a shared `Connection` from a container or pooling/caching wrapper and overwrite its listener, inadvertently clobbering infrastructure callbacks.

### 5.2. Spring Container ExceptionListener vs. Connection ExceptionListener

With Spring:

~~~java
factory.setExceptionListener(ex -> {
    // Spring listener-container JMSException notification.
});
~~~

The API above sets the callback used by the container per `AbstractMessageListenerContainer` Javadoc, covering `JMSException` from the registered listener/invocation infrastructure. It is **not a guarantee** that every socket drop, every destination lookup failure, or every asynchronous provider exception goes through this callback identically to setting `Connection.setExceptionListener` on an app-owned connection.

**Also monitor** recovery logs, broker connectivity health, failed receive/setup metrics, and container states. Do not use an `onException` count of 0 to claim the broker has never failed.

## 6. Direct Configuration on DefaultMessageListenerContainer

If creating a container Java bean directly instead of `@JmsListener`:

~~~java
@Bean
DefaultMessageListenerContainer ordersContainer(
        ConnectionFactory connectionFactory,
        MessageListener ordersListener,
        ErrorHandler errorHandler,
        ExceptionListener exceptionListener) {

    var container = new DefaultMessageListenerContainer();
    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("orders.in");
    container.setMessageListener(ordersListener);
    container.setSessionTransacted(true);
    container.setConcurrency("1");
    container.setErrorHandler(errorHandler);
    container.setExceptionListener(exceptionListener);
    return container;
}
~~~

This is a **method snippet** inside Spring `@Configuration`, requiring imports:
- `jakarta.jms.ConnectionFactory`, `MessageListener`, `ExceptionListener`;
- `org.springframework.jms.listener.DefaultMessageListenerContainer`;
- `org.springframework.util.ErrorHandler`;
- `org.springframework.context.annotation.Bean`.

This container bean participates in the Spring lifecycle automatically. Do not both create a direct container like this **and** add a `@JmsListener` on the same queue expecting just one consumer: you will have two competing consumers on the Queue.

### 6.1. When to Use the Container Directly?

- You already have code managing a raw `jakarta.jms.MessageListener` and want Spring lifecycle integration.
- You need fine-grained control over polling/caching/recovery/sessions/executors.
- The endpoint does not fit the annotation mechanism.
- You want separate factories/listeners with different policies.

With `@JmsListener`, the simpler approach is configuring **`DefaultJmsListenerContainerFactory`** for annotated endpoints. That is the main focus of the next section.

## 7. Configuring for @JmsListener via DefaultJmsListenerContainerFactory

`DefaultJmsListenerContainerFactory` extends `AbstractJmsListenerContainerFactory` and has two setters:

~~~java
factory.setErrorHandler(errorHandler);
factory.setExceptionListener(exceptionListener);
~~~

The callbacks apply to `DefaultMessageListenerContainer` instances created by the factory. One factory can serve multiple `@JmsListener`s, so:
- One `ErrorHandler` can receive errors from multiple endpoints.
- One `ExceptionListener` can receive `JMSException`s from multiple containers.
- If you need clear separation of policies/budgets/metrics between two groups, use **two factories** or include reliably supplied context.
- `@JmsListener(containerFactory = "someFactory")` determines which factory is actually used. Having an `ErrorHandler` bean in the context **does not guarantee** the active factory has attached it.

Explicit configuration example:

~~~java
@Configuration(proxyBeanMethods = false)
class JmsListenerFactoryConfiguration {

    @Bean("reliableListenerFactory")
    DefaultJmsListenerContainerFactory reliableListenerFactory(
            ConnectionFactory connectionFactory,
            ErrorHandler handler,
            ExceptionListener jmsExceptions) {

        var result = new DefaultJmsListenerContainerFactory();
        result.setConnectionFactory(connectionFactory);
        result.setSessionTransacted(true);
        result.setConcurrency("1-3");
        result.setErrorHandler(handler);
        result.setExceptionListener(jmsExceptions);
        return result;
    }
}
~~~

This is an **illustrative Spring class**, requiring imports for `@Configuration`, `@Bean`, `ConnectionFactory`, `ExceptionListener`, `ErrorHandler`, and `DefaultJmsListenerContainerFactory`. With Spring Boot 3.5, you can use `DefaultJmsListenerContainerFactoryConfigurer` to preserve Boot defaults; the lab below does so.

### 7.1. Avoiding Two Common Injection Mistakes

1. **Multiple `ExceptionListener` beans:** use `@Qualifier` to pick the right listener for the factory; do not let Spring resolve by type when multiple beans exist.
2. **Not using the factory you just configured:** if the annotation says `containerFactory="jmsListenerContainerFactory"` while you only attached callbacks on `reliableListenerFactory`, the endpoint will not use the new callbacks.

If the system declares both a default `jmsListenerContainerFactory` and another named factory, verify ID/factory mapping via config/integration tests instead of guessing by bean name.

## 8. Spring Boot 3.5's DefaultJmsListenerContainerFactoryConfigurer

Spring Boot creates `JmsTemplate`, `ConnectionFactory`, and a default factory when infrastructure is present. If you define your own factory, you can reuse Spring Boot settings via:

~~~java
@Bean("observedListenerFactory")
DefaultJmsListenerContainerFactory observedListenerFactory(
        ConnectionFactory connectionFactory,
        DefaultJmsListenerContainerFactoryConfigurer configurer,
        ErrorHandler handler,
        ExceptionListener jmsExceptions) {

    var factory = new DefaultJmsListenerContainerFactory();
    configurer.configure(factory,
        ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
    factory.setSessionTransacted(true);
    factory.setConcurrency("1");
    factory.setErrorHandler(handler);
    factory.setExceptionListener(jmsExceptions);
    return factory;
}
~~~

This is a **Spring Boot 3.5 method snippet**, requiring imports:
- `org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer`
- `org.springframework.boot.jms.ConnectionFactoryUnwrapper`
- `org.springframework.jms.config.DefaultJmsListenerContainerFactory`
- `jakarta.jms.ConnectionFactory`, `jakarta.jms.ExceptionListener`
- `org.springframework.util.ErrorHandler`

**Order matters:** call `configurer.configure(...)` **first**, then override transactions, concurrency, and handlers per contract. `ConnectionFactoryUnwrapper.unwrapCaching(...)` is a Boot 3.5 utility to avoid passing a caching wrapper into a listener container that already manages caching/recovery itself. Do not assume unwrapping suits every custom provider if the application uses specialized wrapper layers; test the real configuration.

### 8.1. Why Is sessionTransacted Needed?

If a listener throws an exception while the JMS session is transacted, the Spring container can roll back so the broker redelivers the message per policy. With `DefaultMessageListenerContainer`'s default `AUTO_ACKNOWLEDGE`, the container may ACK **before the listener runs**, so an exception does not automatically yield reliable redelivery.

Configuring:

~~~java
factory.setSessionTransacted(true);
~~~

does not causally link `ErrorHandler` to rollback. **Rollback is a container and transaction decision**, while the handler records the error.

## 9. Error Matrix: Which Callback Is Expected?

| Scenario | ErrorHandler | ExceptionListener | Delivery Outcome Depends On |
| --- | --- | --- | --- |
| Handler throws `IllegalStateException` | Usually invoked when error escapes listener | Not the standard path for `RuntimeException` | JMS transaction/ACK and broker retries |
| `MessageConversionException` before method | May be invoked if error enters listener container | Not automatically a `JMSException` | Converter, transaction, DLQ |
| Header/argument resolver fails | May go through listener error path | Not by default | Listener adapter, transaction |
| Handler directly throws `JMSException` | Spring has a `JMSException` notification path | May be invoked per Javadoc when `JMSException` enters handling | How adapter wraps and container receives error |
| Container JMS session receive/commit exception | Depends on origin and error-dispatch | Depends on Spring/container notification mechanism | Recovery, session & broker |
| Sudden broker disconnect | Not guaranteed for every outage | JMS provider may notify async; Spring container recovery is a separate channel | Reconnect/backoff, broker health |
| `JmsTemplate.send(...)` on another thread throws `JmsException` | Does not belong to that listener factory | Does not belong to that listener factory | Caller retry/outbox |
| Poison message repeatedly redelivered | May be invoked many times | Not necessarily | Max delivery attempts / DLQ |
| Broker disk/quota failure | Not guaranteed | Not guaranteed for all error types | Broker metrics/alerts |
| `ErrorHandler` itself throws an exception | Can cause secondary errors | Should not be used to measure responses | Container logging/handling |

**This table is an observation guide, not a guarantee that every path calls one exact callback.** Each container implementation, JMS provider, error wrapper, and transaction manager can alter dispatch order/paths. Test on your actual stack.

### 9.1. Errors with a JMSException Root Cause Wrapped in RuntimeException

A `JMSException` may be converted by Spring into an unchecked `JmsException` or wrapped in `ListenerExecutionFailedException`. Classify by walking the cause chain (with a depth bound) rather than just checking `instanceof JMSException` on the outer throwable:

~~~java
static boolean hasJmsCause(Throwable throwable) {
    for (int depth = 0; throwable != null && depth < 10;
            depth++, throwable = throwable.getCause()) {
        if (throwable instanceof jakarta.jms.JMSException) {
            return true;
        }
    }
    return false;
}
~~~

This is a **static Java method snippet**, not a standalone app. `getCause()` can contain deeply nested exceptions; avoid infinite loops if a custom `Throwable` returns unusual causes. If JMS-specific metadata is needed, `JMSException.getLinkedException()` may hold provider errors in addition to `getCause()`.

## 10. Transactions and Commit/Rollback Order Decide Retries

### 10.1. With a Transacted Session

~~~text
Message received in a transacted JMS Session
                    |
                    v
               Invoke listener
                 /      \
            Success      Exception
               |             |
               v             v
          JMS commit      JMS rollback
               |             |
          ACK/complete     Eligible for redelivery
                              |
                        ErrorHandler observes
~~~

This is an intent diagram. If session commit/rollback itself fails, the flow generates an additional `JMSException`, recovery, and broker state to reconcile. Callbacks do not verify that the transaction actually completed cleanly.

**Business rule:** If processing fails and you want redelivery, let the exception escape the listener so the container sees the failure; do not catch it and return as if it succeeded.

~~~java
@JmsListener(destination = "invoices.commands")
public void onInvoice(String invoiceId) {
    invoiceService.createInvoice(invoiceId);
    // On failure, throw exception so container rolls back per policy.
}
~~~

The snippet above requires the service and a transacted-configured container. It is **not** a standalone Java file.

### 10.2. Exception-Swallowing Anti-Pattern

~~~java
@JmsListener(destination = "invoices.commands")
public void onInvoice(String invoiceId) {
    try {
        invoiceService.createInvoice(invoiceId);
    } catch (RuntimeException ex) {
        logger.error("Invoice failed", ex);
        // Return normally: container may commit the message!
    }
}
~~~

This is an **intentional anti-pattern**. Never use it for work that must not be lost. A container's `ErrorHandler` **is not invoked** if the error was swallowed by the handler and the method returns normally.

### 10.3. Why Is Idempotency Still Needed?

If:
1. The handler writes to DB successfully.
2. The JVM dies before the JMS session commits.
3. The broker redelivers the message.

...then business side effects can still repeat even when `ErrorHandler`/`ExceptionListener` are configured perfectly. Solutions: stable event IDs, inbox/dedup with unique constraints, clear DB transactions, transactional outbox for producers, reconciliation processes, and DLQ.

### 10.4. Session Transacted Is Not XA

`factory.setSessionTransacted(true)` is a **local JMS transaction**. It does not automatically merge DB transactions or HTTP APIs into a global transaction. Using `@Transactional` on a DB service can ensure a DB transaction, yet coordination between the two commits must be designed and tested. When coordinated XA/JTA is required, use an appropriate transaction manager/provider and understand recovery complexity.

## 11. Broker Retries, Redelivery, and DLQ Differ from ErrorHandler

An `ErrorHandler` can record each listener failure, yet how many times **a message is redelivered** depends on the broker:

- For JMS transacted session rollbacks, the broker/provider controls redelivery delay, max attempts, and dead-letter destination routing.
- `JMSRedelivered` and `JMSXDeliveryCount` help identify redeliveries, provided they are read from the raw JMS message or a suitable metadata mapper.
- A malformed JSON message may never reach the handler body; converter exceptions must still be observed at the container.
- Multiple redeliveries produce multiple `ErrorHandler` invocations—do not mistake two callbacks for two distinct messages.
- DLQs typically must be configured on the broker (ActiveMQ Artemis address settings), not inside `ErrorHandler`.
- Without a sensible DLQ/max attempts on the broker, poison messages can loop endlessly and cause backlog.

### 11.1. Distinguishing Business Retries from Connection Retries

| Mechanism | Actor | Example |
| --- | --- | --- |
| Redelivery from listener rollback | JMS provider/broker | Handler throws, session rolls back, message is redelivered |
| Recovery from broker disconnect | Spring `DefaultMessageListenerContainer` | Recreates JMS connection/session/consumer |
| Producer send retry | Application/outbox/job scheduler | `JmsTemplate.send` fails, needs reconciliation |
| Internal handler retry | HTTP/DB service retry | Can increase latency and hold JMS Session open longer |
| DLQ/quarantine | Broker/application per contract | Exceeded redelivery count or permanently invalid payload |

Do not confuse the container's recovery interval with the broker's redelivery delay.

## 12. How Does DefaultMessageListenerContainer Self-Recover?

Spring's `DefaultMessageListenerContainer` supports **self-recovery** when the broker is temporarily unavailable. Javadoc notes:
- Polling mechanism on a task executor.
- Can recreate connections/sessions/consumers upon errors.
- `setRecoveryInterval(long)` defaults to roughly **5,000 ms**.
- `setBackOff(BackOff)` enables flexible retry backoff policies.
- `setBackOff` and `setRecoveryInterval` have precedence interactions; the method configured last may replace the earlier setting per API.

Example:

~~~java
factory.setRecoveryInterval(5_000L);
~~~

The call above is a Spring JMS factory configuration snippet, not a per-message redelivery count. For severe infrastructure failures, pair the recovery loop with broker health checks, alerts, readiness/liveness probes, network timeouts, and resource quotas.

**Do not repeatedly call `connection.close()` or `container.start()` from `ExceptionListener`** to "recover faster": the container manages its own lifecycle. Likewise, do not implement reconnect loops inside `ErrorHandler` causing multiple threads to race creating sessions/connections.

### 12.1. When Must the Container Be Stopped?

Only in scenarios with explicit operational policies, such as:
- Controlled shutdown.
- Pausing consumption to deploy an incompatible schema.
- Business circuit breaking, after evaluating queue backlog/retention capacity.
- Waiting for ACL/credential fixes or an unrecoverable configuration error.

Do not stop the entire listener over a single invalid message when the broker has proper DLQ/poison-message handling.

## 13. Java 17+ Spring Boot 3.5 Lab: Business Error and Both Callbacks

The lab uses a **single queue** `lab.error-callbacks` and one `@JmsListener`. Message `task-1` is rejected **on the very first attempt only** with `IllegalStateException`, and then processed successfully on redelivery. The container is configured **transacted**, so retries rely on JMS rollback rather than `ErrorHandler` resending manually.

`ErrorHandler` increments a counter and signals the test when seeing the runtime error. `ExceptionListener` has its own counter, yet is not expected to receive non-`JMSException` business errors.

### 13.1. Maven Project

Create the project at https://start.spring.io/:
- Maven, Java 17+, supported patch of Spring Boot 3.5.x.
- Group `com.example`.
- Artifact `jms-error-callback-demo`.
- Package `com.example.jmserrorlab`.
- Dependency Spring for Apache ActiveMQ Artemis (`spring-boot-starter-artemis`).

Add the embedded broker dependency to the Initializr-generated `pom.xml` (using the Spring Boot BOM):

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

Do not pin an Artemis version different from the BOM without checking compatibility. This is **not the full `pom.xml`**. The Java files below use package names matching the project.

### 13.2. application.properties

Create `src/main/resources/application.properties`:

~~~properties
spring.application.name=jms-error-callback-demo
spring.main.web-application-type=none
spring.artemis.mode=embedded
spring.artemis.embedded.queues=lab.error-callbacks
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

The lab is not meant to prove data persistence; `persistent=false` is only suited for test environments. Never run intentional exception-throwing tests on production queues.

### 13.3. File 1 — CallbackState.java

Save `src/main/java/com/example/jmserrorlab/CallbackState.java`:

~~~java
package com.example.jmserrorlab;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.jms.JMSException;
import org.springframework.stereotype.Component;

@Component
public class CallbackState {

    private final AtomicInteger attempts = new AtomicInteger();
    private final AtomicInteger handlerErrors = new AtomicInteger();
    private final AtomicInteger jmsExceptions = new AtomicInteger();

    private final CountDownLatch failureObserved = new CountDownLatch(1);
    private final CountDownLatch completed = new CountDownLatch(1);

    private volatile String processed;

    public boolean shouldFailThisAttempt() {
        return attempts.incrementAndGet() == 1;
    }

    public void onHandlerError(Throwable error) {
        handlerErrors.incrementAndGet();
        failureObserved.countDown();
        // Observe only, do not rethrow, do not decide rollback.
    }

    public void onJmsException(JMSException exception) {
        jmsExceptions.incrementAndGet();
        // JMS error path; do not open a new connection in callback.
    }

    public void markProcessed(String body) {
        processed = body;
        completed.countDown();
    }

    public boolean awaitBoth(long timeout, TimeUnit unit)
            throws InterruptedException {
        long deadline = System.nanoTime() + unit.toNanos(timeout);
        long remaining = deadline - System.nanoTime();

        if (!failureObserved.await(
                Math.max(0L, remaining), TimeUnit.NANOSECONDS)) {
            return false;
        }

        remaining = deadline - System.nanoTime();
        return completed.await(
                Math.max(0L, remaining), TimeUnit.NANOSECONDS);
    }

    public int attempts() {
        return attempts.get();
    }

    public int handlerErrors() {
        return handlerErrors.get();
    }

    public int jmsExceptions() {
        return jmsExceptions.get();
    }

    public String processed() {
        return processed;
    }
}
~~~

`AtomicInteger` fits callback threads; `CountDownLatch` lets the test wait for both **an observed error** and **a successful processing**. `volatile processed` safely publishes the value; the lab does not use the latch to guarantee the JMS transaction committed.

### 13.4. File 2 — ErrorCallbacksDemoApplication.java

Save `src/main/java/com/example/jmserrorlab/ErrorCallbacksDemoApplication.java`:

~~~java
package com.example.jmserrorlab;

import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class ErrorCallbacksDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorCallbacksDemoApplication.class, args);
    }

    @Bean("observedListenerFactory")
    DefaultJmsListenerContainerFactory observedListenerFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            CallbackState state) {

        var factory = new DefaultJmsListenerContainerFactory();

        configurer.configure(factory,
                ConnectionFactoryUnwrapper.unwrapCaching(
                        connectionFactory));

        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        factory.setErrorHandler(state::onHandlerError);
        factory.setExceptionListener(state::onJmsException);
        return factory;
    }

    @Bean
    ApplicationRunner demonstrate(
            JmsTemplate template,
            CallbackState state) {

        return args -> {
            template.convertAndSend(
                    "lab.error-callbacks", "task-1");

            if (!state.awaitBoth(12, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "No error callback or successful redelivery");
            }

            System.out.println("ATTEMPTS=" + state.attempts());
            System.out.println(
                    "HANDLER_ERRORS=" + state.handlerErrors());
            System.out.println("PROCESSED=" + state.processed());
            System.out.println(
                    "JMS_EXCEPTIONS=" + state.jmsExceptions());
        };
    }
}
~~~

Spring Boot's configurer preserves JMS factory settings prepared by Boot. `factory.setSessionTransacted(true)` makes the failed attempt eligible for rollback. Two method references attach **two callbacks of distinct interfaces** to the same factory without parameter confusion.

### 13.5. File 3 — RetryingTaskListener.java

Save `src/main/java/com/example/jmserrorlab/RetryingTaskListener.java`:

~~~java
package com.example.jmserrorlab;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class RetryingTaskListener {

    private final CallbackState state;

    public RetryingTaskListener(CallbackState state) {
        this.state = state;
    }

    @JmsListener(
            id = "retryingTaskListener",
            destination = "lab.error-callbacks",
            containerFactory = "observedListenerFactory")
    public void onTask(String task) {
        if (state.shouldFailThisAttempt()) {
            throw new IllegalStateException(
                    "Intentional failure on first delivery");
        }

        state.markProcessed(task);
    }
}
~~~

This is a Java 17+ application with **three separate Java files per class** and `application.properties`. No other bean/listener shares the queue in the lab. The first `IllegalStateException` is an intentional error **in the business method**, not a `JMSException`. It must pass through `ErrorHandler`; there is no need—and you should not—fake a broken connection just to make the second callback fire.

### 13.6. Run

Linux/macOS:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Given these conditions:
- embedded broker starts normally;
- test queue starts empty;
- a single listener with concurrency `1`;
- Artemis redelivery policy allows at least a second attempt;
- no connection outage occurs during the run;

...the output printed by **`ApplicationRunner`** is expected to be:

~~~text
ATTEMPTS=2
HANDLER_ERRORS=1
PROCESSED=task-1
JMS_EXCEPTIONS=0
~~~

Spring/JMS/Artemis may emit additional logs; do not claim total stdout is strictly four lines. If the broker has a redelivery delay longer than 12 seconds, `awaitBoth` may time out—adjust the **test policy** or timeout, not infinite retries in production.

**Explanation:**
1. The producer sends `task-1` to the queue.
2. The first call increments `attempts` to 1, and the listener throws `IllegalStateException`.
3. The container's transacted session rolls back per policy, and Spring invokes `ErrorHandler` to report the error.
4. The broker redelivers the message; the second call increments `attempts` to 2, and the listener calls `markProcessed`.
5. Once both latches are tripped, the runner prints the snapshot. Because no JMS-level error occurred, `ExceptionListener` is not expected to fire.

**Verification limitation:** `markProcessed` runs **inside** the handler, potentially **before** the container finishes JMS commit. The lab proves the callbacks, expected rollback/redelivery flow, and in-memory test state; **it does not prove** durable message commit, exactly-once side effects, or provider failover. To verify commit, inspect broker queue state/transactions afterward.

## 14. How to Test ExceptionListener Without Confusing It with Business Errors

Do not "test `ExceptionListener`" by throwing `RuntimeException` inside `@JmsListener`: that tests `ErrorHandler`/rollback, not connection exceptions.

### 14.1. Testing JMSException at Listener/Infrastructure

In a separate test, you can use a raw `jakarta.jms.MessageListener` or suitable adapter that raises a `JMSException` along the container's handling path and verify:
- Spring invokes the `JMSException` callback if the path is indeed recognized by the container.
- Spring may also invoke `ErrorHandler` for the same error.
- Session rollback/recovery is tested separately.
- Logs/metrics do not count one failure as two distinct business incidents.

**Never turn real errors into fake `JMSException`s in production just to bump callback metrics.** Callbacks must reflect root causes.

### 14.2. Testing Provider Disconnection

In staging with an **external** broker:
1. Configure connection factory, queue, consumer, and running container.
2. Verify the listener receives a message normally.
3. Stop the broker process in an authorized test environment, then restart it.
4. Record provider logs, `DefaultMessageListenerContainer` recovery logs, registry state, connection metrics, and the `ExceptionListener` callback if invoked.
5. Verify the consumer **resumes** and processes new messages after broker recovery; if backlog survival is needed, enable appropriate broker persistence/retention.
6. If `ExceptionListener` is not called yet the container reconnects, do not conclude "Spring failed to handle the outage"; inspect the recovery channel separately.
7. If the broker stays down longer than retry budget/backoff, evaluate readiness, alarms, and failover policies.

**Do not use embedded Artemis** to simulate a network outage independent of the JVM, because stopping an in-process broker usually invalidates connection-recovery testing.

### 14.3. Distinguishing Synchronous JMS Call Errors from Async Callbacks

~~~java
try {
    jmsTemplate.convertAndSend("orders.in", "order-1");
} catch (org.springframework.jms.JmsException ex) {
    // Synchronous error on sending thread: handle/record state/outbox.
}
~~~

This is a **code snippet** inside a service with `JmsTemplate`. Errors on the sending thread **do not belong** to the listener container's `ErrorHandler`. Jakarta Messaging specifies that exceptions thrown synchronously by API calls must not be replaced by `ExceptionListener`.

## 15. Observability, Logging, and Metrics: Measure Accurately Without Double Counting

A system should measure at least four dimensions:

| Observation Group | Suggested Metrics | Why |
| --- | --- | --- |
| Business listener | Attempts, successes, failures by exception category | Know whether messages actually succeeded |
| ErrorHandler | Listener callback errors, exception types, endpoint/factory | Detect unhandled adapter/handler errors |
| JMS infrastructure | `JMSException` callbacks, reconnect counts, recovery duration | Distinguish provider/connection issues |
| Broker | Queue depth, oldest message age, redeliveries, DLQ, expiries | See real impact on backlog |

`ErrorHandler` and `ExceptionListener` can both receive the same `JMSException`. Therefore:
- Label clearly: `source=listener-error-handler` or `source=jms-exception-listener`.
- Do not add the two counters straight together to infer failed message count.
- To count **message attempts**, measure at the listener/container and use JMS message ID/redelivery metadata where appropriate.
- To count **business outcomes**, rely on idempotent DB records/success metrics, not total callback errors.
- For logs, prioritize error class, correlation ID/destination, timestamp, `errorCode`, and linked exception; never dump full JMS payloads if they contain PII.
- With one factory shared across many endpoints, `ErrorHandler` typically only receives a `Throwable`, **with no automatic destination/message argument**. To separate endpoints, use separate factories, lifecycle-safe tracing/MDC, or instrumentation where message context exists.

### 15.1. Controlled Exception Classification

~~~java
// Function snippet illustrating root-cause classification on Spring side.
static String classify(Throwable error) {
    Throwable current = error;
    for (int depth = 0; current != null && depth < 8;
            depth++, current = current.getCause()) {
        if (current instanceof jakarta.jms.JMSException) {
            return "JMS_API";
        }
        if (current instanceof
                org.springframework.jms.support.converter.MessageConversionException) {
            return "CONVERSION";
        }
    }
    return "BUSINESS_OR_ADAPTER";
}
~~~

This classification is only a **starting point**, not a final taxonomy. `MessageConversionException` in Spring Messaging/JMS can reside in different packages depending on the converter; inspect actual exception stacks in tests. Do not treat every error as "transient" merely because it is wrapped in `RuntimeException`.

### 15.2. Preventing Alert Storms

If the broker redelivers a poison message 10,000 times, firing 10,000 alerts causes alert fatigue. Instead:
- Use metric rates/thresholds and group by destination/exception class.
- Log full stack traces via sampling or first N events only.
- Bound retries and route to DLQ.
- Maintain a backlog/DLQ dashboard, not just error counts.
- Create a single runbook for contract-invalid messages.

## 16. Common Configuration Mistakes

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Handler throws yet `ErrorHandler` does not run | Error caught and swallowed inside method | Let errors propagate to container when rollback is needed |
| `ErrorHandler` bean exists yet no callback runs | Endpoint's factory has not attached that bean | Check `containerFactory` and `factory.setErrorHandler` |
| `ExceptionListener` does not run when handler throws `IllegalStateException` | That is a runtime business error, not `JMSException` | Use `ErrorHandler` |
| Two log entries for one `JMSException` | Spring may invoke `ExceptionListener` then `ErrorHandler` | Label and avoid double counting |
| `ErrorHandler` exists yet messages are lost | `AUTO_ACK` or handler returns normally | Use transacted Session and proper exception propagation |
| Message processed endlessly | Rollback without broker retry cap/DLQ | Configure max delivery attempts/delay/DLQ |
| Broker disconnects yet callbacks do not fire as expected | DMLC recovery uses its own path; provider async differs from sync | Inspect recovery logs/broker health |
| One conversion error stalls the whole queue | Poison message redelivery with no quarantine | Classify errors, DLQ, bounded retries |
| `ErrorHandler` calls JMS send and fails further | Callback lacks clear transaction/message context | Never manually redeliver inside callback |
| `ExceptionListener` operates on broken `Connection` | Provider callback does not guarantee usable `Connection` | Only log/metrics; let container recover |
| Cannot tell which endpoint failed | One factory shares handler, throwable lacks metadata | Separate factories or add valid instrumentation |
| Custom factory loses Boot configuration | Bypassed Boot configurer or wrong override order | Use `DefaultJmsListenerContainerFactoryConfigurer` |
| App looks healthy while backlog grows | Listener stopped, broker down, selector mismatch, poison message | Monitor registry, queue depth, consumer count |
| DB repeats side effects after retry | JMS rolled back while DB already committed | Inbox/idempotency + outbox |
| Failover test on embedded broker inconclusive | Broker and app share the same lifecycle | Use standalone broker with persisted storage |
| Shutdown causes JMS errors | SIGTERM mid-flight, timeouts too short | Graceful shutdown, transactions, retries, broker retention |
| `ExceptionListener` fires with no stack log | Callback logged only `errorCode`, skipping `getLinkedException`/causes | Structured logging with data sanitization |

## 17. Distinguishing Transient vs. Permanent Business Errors

An invoice-processing app may encounter:

**Transient:** database unavailable, external API timeout, broker reconnect, temporary rate limiting. Usually retriable with backoff, circuit breakers, and thresholds.

**Permanent:** unfixable malformed schema payload, unsupported enum/type ID, invalid ID, unrecoverable business constraint violation. Infinite retries are wrong. Route to DLQ/quarantine or record an explicit contract rejection.

`ErrorHandler` observes errors; **when deciding which message is committed/quarantined/retried**, use:
- A domain-specific error policy inside the business service.
- Proper transaction boundaries so DLQ/rejection writes and ACKs leave no data-loss window.
- Broker redelivery max attempts, DLQ policies, and monitoring.
- Idempotency to avoid duplicate side effects.
- Versioned message schemas and contract validation.

### Do Not "Fix" by Catching Everything

~~~java
@JmsListener(destination = "orders.in")
public void handle(String payload) {
    try {
        process(payload);
    } catch (Exception ex) {
        // This is an anti-pattern if the work has not finished.
        return;
    }
}
~~~

When the Spring container sees the method return normally, it may commit the local JMS Session. Distinguish **controlled message rejection with a durable recorded outcome** from **unfinished failed processing**; the latter must propagate the error per retry policy.

## 18. Relationship to Spring Messaging / Spring Integration

Do not confuse JMS listener container callbacks with:
- `org.springframework.integration.channel.PublishSubscribeChannel` error channels or Spring Integration `errorChannel`: handles errors along Spring Integration message flows, separate from `DefaultMessageListenerContainer`'s lifecycle.
- `org.springframework.amqp.rabbit.listener.RabbitListenerErrorHandler`: RabbitMQ/AMQP callback, not Jakarta JMS.
- `@ControllerAdvice` or web `ErrorController`: HTTP MVC exception handling.
- `CompletionListener` on JMS asynchronous producer sends: callback for success/failure of **async sends**, not a consumer `ErrorHandler`.
- `JmsTemplate` send/receive exception path: usually throws Spring `JmsException` on the calling thread, bypassing the listener container's `ErrorHandler`.

Understanding the exact layer ensures logs, metrics, and transactions live where they actually take effect.

## 19. Reliable Testing Plan

### 19.1. Unit Tests for Callbacks

- Feed `IllegalStateException` into `ErrorHandler.handleError`: increments counter properly and does not throw.
- Feed `JMSException` into `ExceptionListener.onException`: increments counter, logs `errorCode`/linked cause safely.
- Call callbacks concurrently from multiple threads: thread-safe metrics.
- Feed multi-layered wrapped exceptions: bounded root-cause classification, no infinite loop.
- Never write sensitive data to logs.
- Callbacks perform no blocking network I/O or self-reconnection.

### 19.2. Layered Integration Tests

| Case | Input / Failure | What to Prove |
| --- | --- | --- |
| Business fail-once | Handler throws on 1st attempt | `ErrorHandler` observes, session rolls back, broker redelivers |
| Business success | Handler returns | ACK/commit, queue backlog reaches expected state |
| Broken payload | Invalid JSON/schema | Conversion exception reported, handler body need not run |
| Missing required header | Annotation argument resolution fails | Container error handling, rollback/DLQ per policy |
| `JMSException` path | Container sees JMS API exception | `ExceptionListener` path verified properly |
| Broker unavailable at startup | Broker down | DMLC setup/recovery and alerts, not equating callback with recovery |
| Broker restart mid-processing | Container reconnects | Processing resumes after restart, reconcile message IDs |
| Poison retry limit | Message always fails | Moves to DLQ after configured broker attempts |
| Duplicate redelivery | Crash between DB commit and JMS commit | Idempotency prevents duplicate side effects |
| Graceful shutdown | SIGTERM while job running | In-flight handling per shutdown budget, rollback if needed |
| Multiple factories | Two endpoints on different factories | Each callback follows expected policy/factory |
| Shared callback | One handler used by multiple listeners | Counter labels prevent double counting |

### 19.3. Which Environment to Use?

- **Unit tests:** no broker needed.
- **Embedded Artemis lab:** good for comparing error callbacks and basic fail-once redelivery; does not prove network failover.
- **Standalone test broker:** suited for connection outages, persistence, HA, DLQ, quotas, and recovery.
- **Production-like staging:** verifies full retry delays, concurrency, transactions, DB idempotency, and operational alerts.

Never break real production connections just to see if callbacks fire. Never run poison-message tests on customer-facing queues.

## 20. Production Checklist

- Classified business, conversion, and JMS infrastructure exceptions?
- Attached `ErrorHandler` to the **exact factory/container** used by `@JmsListener`?
- Verified `ExceptionListener` is `jakarta.jms.ExceptionListener` with no wrong class imported?
- Understood the difference between Spring container callbacks and provider-level asynchronous `Connection` callbacks?
- Prevented double counting when a `JMSException` passes through both callbacks?
- Confirmed `ErrorHandler` is thread-safe, fast, throws no secondary errors, and leaks no sensitive payloads?
- Confirmed `ExceptionListener` avoids operating on failed connections or blocking long?
- Configured `sessionTransacted=true` or another transaction policy matching SLA?
- Propagated errors needing retry out of the handler instead of swallowing them?
- Configured broker redelivery delay, max attempts, DLQ/expiry, and alerts?
- Separated message retries from connection recovery intervals?
- Tested DMLC reconnect against a standalone broker, not just embedded?
- Ensured idempotency when DB commits before JMS?
- Set up logs/metrics for listener errors, `JMSException`s, queue age, DLQ, and consumer counts?
- Monitored `JmsListenerEndpointRegistry` and container running/recovery states?
- Used Boot's factory configurer so critical defaults are not lost?
- Tested pre-method conversion errors, missing headers, and rollback behavior?
- Tested graceful shutdown/worker restarts with in-flight messages?
- Clarified ownership of `Connection`, `Session`, and JMS resources?
- Maintained runbooks for broker outages, poison messages, and business failures?

## 21. Reinforcement Exercises

1. A `@JmsListener` throws `IllegalStateException`. Which callback applies? Why does `ExceptionListener` not receive this error by default?
2. Compare the signatures of `ErrorHandler.handleError(Throwable)` and `ExceptionListener.onException(JMSException)` and their two import packages.
3. When the Spring container receives a `JMSException` from listener invocation, why can both callbacks fire? How do you prevent double counting?
4. Why does `ErrorHandler` returning normally **not mean** the message committed successfully? What decides the transaction?
5. A handler catches a DB error, logs it, and returns. What is the risk to the JMS transaction? How do you fix it?
6. The broker goes down for 20 seconds without an `onException` callback, and then the container reconnects. Does that prove the listener is "blind to errors"? What else should you observe?
7. `JmsTemplate.convertAndSend` on an HTTP thread throws Spring `JmsException`. Are callbacks on the listener factory guaranteed to run? Design producer-side handling.
8. Why does `setRecoveryInterval(5000)` not mean a message will redeliver after 5 seconds?
9. Write a factory bean explicitly configuring `setErrorHandler`, `setExceptionListener`, `setSessionTransacted(true)`, and concurrency.
10. If a shared factory serves three endpoints, `ErrorHandler` receives only `Throwable`. How do you tell which queue failed without parsing the message body?
11. Run the fail-once lab and explain why `HANDLER_ERRORS=1` and `ATTEMPTS=2`. Which mechanism returned the message to the queue?
12. Change `sessionTransacted(false)` in the lab and analyze how reliability changes under DMLC's `AUTO_ACKNOWLEDGE`.
13. Use a standalone test broker to restart while a message is in-flight; describe which metrics and message IDs to reconcile.
14. Use a malformed message that always fails; choose appropriate max redelivery, DLQ, and alert policies.
15. A JMS callback catches an error and calls `connection.close()` immediately inside `onException`. What is dangerous about this in Spring-managed infrastructure?
16. In the lab, the app prints `PROCESSED=task-1`. Why is that insufficient proof of JMS commit and exactly-once DB side effects?
17. A message reaches Spring `ErrorHandler` twice. Is that guaranteed to be two different events? Check redelivery IDs.
18. When a Spring Boot custom factory uses `configurer.configure(...)`, why must settings be overridden **after** the configurer call?
19. Distinguish a conversion error occurring before the handler, an error inside the handler, and a JMS connection error after the handler ran.
20. Write a runbook for when the broker is down while readiness stays green, queue backlog grows, and `ExceptionListener` prints no logs.

## Official References

- Spring Framework 6.2 — `AbstractMessageListenerContainer` Javadoc, `setErrorHandler`, `setExceptionListener`, `handleListenerException`, and transactions: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html
- Spring Framework 6.2 — `DefaultMessageListenerContainer` Javadoc, recovery, default ACK, `setBackOff`, and `setRecoveryInterval`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Framework 6.2 — `AbstractJmsListenerContainerFactory`, factory setters: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/AbstractJmsListenerContainerFactory.html
- Spring Framework 6.2 — Message Listener Containers and transaction handling: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2 — Receiving a Message: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Boot 3.5 — `DefaultJmsListenerContainerFactoryConfigurer`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jms/DefaultJmsListenerContainerFactoryConfigurer.html
- Spring Boot 3.5 — How-to Messaging, `ConnectionFactoryUnwrapper`: https://docs.spring.io/spring-boot/3.5/how-to/messaging.html
- Jakarta Messaging 3.1 — `ExceptionListener` Javadoc: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/exceptionlistener
- Jakarta Messaging 3.1 Specification, section **6.1.7 ExceptionListener**: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Apache ActiveMQ Artemis — Message Redelivery and Undelivered Messages: https://artemis.apache.org/components/artemis/documentation/latest/undelivered-messages
