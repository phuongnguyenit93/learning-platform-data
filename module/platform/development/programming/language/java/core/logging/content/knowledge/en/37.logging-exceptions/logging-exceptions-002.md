# Service-Layer Logging in Java: Exceptions, Responsibilities, and Business Context

## 1. Lesson Objectives

In a layered Java application, the **service layer** is where business rules are executed, repositories are coordinated, external services are called, state is validated, and processing outcomes are decided. Because of this, the service layer often holds very useful context for logging: **which order is being processed, why it was rejected, which retry attempt this is, which dependency is failing, and whether state has changed**.

However, logging in the service layer does not mean **every service method must log** or **every exception must be logged right where it is thrown**. Logging at the wrong point can cause a single error to produce three or four identical stack traces; logging too early can declare a business operation successful even if the transaction rolls back; logging raw data can expose PII or credentials.

After this lesson, you will be able to:

1. Determine **when a service should log** and when it should only return a result or throw an exception.
2. Distinguish between a **business event**, **diagnostic event**, **technical failure**, and **terminal error at the boundary**.
3. Avoid the **log-and-throw** anti-pattern that duplicates exceptions when multiple layers log the same failure.
4. Use INFO/WARN/ERROR/DEBUG, class-based loggers, message templates, exception causes, error codes, and correlation IDs properly.
5. Understand the difference between **the service deciding success** and **the database transaction actually committing**.
6. Write, compile, and run a **pure Java 17 JUL** example with three scenarios: success, business rejection, and dependency failure.
7. Apply these concepts to **Spring @Service, @Transactional, @RestControllerAdvice, scheduled jobs, message consumers, and async tasks**.
8. Design tests that verify **log event counts, log levels, content, security, and consistency when propagating exceptions**.

## 2. Where Is the Service Layer in the Processing Flow?

A Java web application typically has multiple layers:

~~~text
HTTP client
    │
    ▼
Servlet filter / Spring Security / Controller
    │
    ▼
OrderService (business logic)
    │
    ├── OrderRepository / database
    ├── InventoryClient / remote API
    ├── PaymentService
    └── Message publisher / outbox
    │
    ▼
Result or exception returned to controller
    │
    ▼
Exception handler / HTTP response
    │
    ▼
Access log / trace / metrics
~~~

In the service layer, the code author has a lot of **business** information that the HTTP layer may not know. For example:

- OrderService knows an order was rejected because inventory is out of stock.
- PaymentService knows the third retry attempt failed.
- AccountService knows an operation was blocked due to an invalid state transition.
- InventoryService knows a record encountered an optimistic locking conflict.
- ImportService knows 12 malformed rows were skipped while the remaining 988 rows were processed.

However, the service layer **does not necessarily know the final HTTP response**. A business exception might be mapped by a controller to 400, 404, 409, or 422; a background job has no HTTP response; a gateway might send a different status. Therefore, the service should log **the business meaning and technical cause it is responsible for**, rather than guessing the final status just to log it.

### 2.1. Two Questions to Clarify Responsibility

Before adding a logger call in a service, ask:

- **Has the service made a decision or performed an action with its own observable meaning?**
- **If an error occurred, has this layer handled the error, retried, fallen back, or reached the end of its responsibility?**

If both answers are **no**, logging the same stack trace and rethrowing is usually redundant.

## 3. Distinguishing Four Types of Information Commonly Logged in Services

| Event Type | Example | Appropriate Log | Notes |
| --- | --- | --- | --- |
| **Business state transition** | Order accepted, transitioning from PENDING to RESERVED. | INFO event with a stable name and allowed identifiers. | Do not claim **committed** if the transaction has not committed yet. |
| **Business rejection** | Out of stock, disallowed state, version conflict. | INFO or WARN per policy, with a **reason code**. | May be an expected outcome; do not default to ERROR. |
| **Handled technical problem** | Retry after a network error; switching to fallback. | WARN, sometimes DEBUG for individual attempts; final event should reflect the outcome. | If handled completely, logging at the service may be necessary because no exception propagates upward. |
| **Unhandled technical failure** | Dependency down, database exception, unexpected bug. | Usually throw an exception preserving the cause; log the stack trace at the **boundary that owns the final outcome**. | Avoid having the service log ERROR with the same exception and the controller also log ERROR. |

The goal is for operators reading the logs to distinguish **an independent business event** from **an unhandled error**.

For example, the following two records have different meanings:

~~~text
INFO  event=order.rejected orderId=O-204 reason=OUT_OF_STOCK
ERROR event=request.failed errorCode=INVENTORY_UNAVAILABLE cause=ConnectException
~~~

The first record is a **business decision** that the API might return as 409. The second record is an **unhandled technical failure at the boundary**, which the API might return as 503. There is no rule that every HTTP 409 must be logged as ERROR.

## 4. Foundational Principle: Log Once per Failure Chain

A classic anti-pattern:

~~~java
// Bad example: in the repository.
catch (SQLException ex) {
    log.error("Cannot query order", ex);
    throw ex;
}
~~~

~~~java
// Bad example: in the service.
catch (Exception ex) {
    log.error("Cannot place order", ex);
    throw ex;
}
~~~

~~~java
// Bad example: in the controller.
catch (Exception ex) {
    log.error("Request failed", ex);
    throw ex;
}
~~~

A single exception has been logged **three times**, with three stack traces. In systems with more layers and retries, the number of records grows even larger. This:

- Causes dashboards to count more errors than actual failed requests.
- Increases ingest/storage costs and noise.
- Misleads investigators into thinking there are three independent errors.
- Can leak the same sensitive data across multiple destinations.
- Obscures where the failure is finally translated into a response or a retry/fallback.

**Practical rule:** if a service **does not handle the error and only propagates it**, preserve the cause/context and **let the boundary log the terminal failure once**. The service may still emit its own **business/diagnostic event** if that event carries independent meaning, rather than duplicating the stack trace.

~~~text
Repository throws error
       │
       ▼
Service adds exception context (if needed), does not log stack
       │
       ▼
Boundary decides final outcome
       │
       └── ERROR + exception cause + request context (once)
~~~

### 4.1. This Is a Guideline, Not a Ban on Logging in Every Layer

If a service **legitimately catches an exception, performs a fallback or retry, and returns normally**, the boundary will **not see the original error**. In that case, the service is responsible for logging that it handled the issue, if the event is worth observing:

~~~text
WARN event=inventory.lookup.fallback dependency=inventory reason=TIMEOUT
INFO event=order.created source=CACHED_INVENTORY
~~~

Similarly, when a background worker is the **final boundary** for a message/job, the worker/service may need to log the terminal error because no controller exists to log it instead.

A useful rule of thumb is that **each failure chain has one owner for the terminal error log**, while other layers only log **independent events** or **meaningful retry/fallback states**.

## 5. When Should a Service Log?

### 5.1. Significant Business State Changes

For example, an order is in PENDING and the service transitions it to RESERVED. A structured event helps with analysis and traceability:

~~~text
INFO event=order.reservation.requested orderId=O-101 from=PENDING to=RESERVED
~~~

However, if the method is inside an uncommitted transaction, **requested** or **attempted** is more accurate than **committed**. See the transaction section below to avoid false success announcements.

You do not need to emit an event in every getter or setter. Choose **business milestones** that are genuinely useful and have a retention policy.

### 5.2. An Operationally Meaningful Rejection Rule

~~~text
INFO event=order.rejected orderId=O-102 reason=OUT_OF_STOCK
~~~

Rejecting an order due to being out of stock can be completely normal behavior. Logging INFO helps analyze rejection rates; if policy treats this as an alertable condition, WARN or a dedicated metric can be used. Do not automatically assign ERROR to every business exception.

### 5.3. Retries or Fallbacks Actually Controlled by the Service

~~~text
WARN event=inventory.retry attempt=2 maxAttempts=3 reason=TIMEOUT
WARN event=inventory.fallback mode=CACHED_STOCK reason=DEPENDENCY_UNAVAILABLE
~~~

If a service has three retries, it does not necessarily need to print three ERROR stack traces. Individual attempts can be logged at DEBUG/WARN per policy, followed by a single terminal error only if the entire chain fails and no other layer owns the failure.

Note: retries should not be used by default for every request, especially for **non-idempotent** operations; retry decisions require appropriate timeouts, backoff, idempotency, circuit breakers, and attempt limits. Logging alone does not make retries safe.

### 5.4. Detecting Broken Business Invariants or Anomalous Data

If the service encounters a state that **should be impossible by design**, it can log an appropriate event and then fail or emit a monitoring signal. Avoid both extremes: ignoring the error or logging the stack at every layer. A clear exception type and error code help the boundary handle it.

### 5.5. A Batch Job or Consumer Is the End of Responsibility

A service called from a scheduled job or message listener may not go through an HTTP exception handler. If the worker **decides to skip a message, send it to a dead-letter queue, or mark a job FAILED**, that decision is worth logging at the job/consumer boundary.

Distinguish **one message being retried multiple times** from **multiple different messages**; include the message ID, attempt number, and outcome so duplicate logs are not mistaken for new incidents.

## 6. When Should a Service NOT Log?

- **Every method invocation** at INFO under high traffic without operational value: increases volume and cost.
- **Every exception that is caught and rethrown**, when the boundary already logs terminal failures.
- **Every request/response body** for debugging convenience; they may contain PII, tokens, or payment details.
- **A "success" message before commit** while ignoring the possibility of transaction rollback.
- **Information already derivable from access logs** without adding business context.
- **Experimental code** using `System.out.println`/`System.err.println` in production instead of a configurable logging backend.
- **Unescaped/unvalidated input values** concatenated directly into log text, causing log injection.
- **Full `exception.getMessage()` from external sources** if the message contains URLs, headers, SQL parameters, or personal data.
- **ERROR level for expected business errors**, increasing false alarms.
- **Too many repeated events during retries**, causing dashboards to count a single incident multiple times.

A key deciding question: **in real operations, who will use this log line to make what decision?** If there is no answer, consider lowering the severity, using a metric, or removing the event.

## 7. Standalone Java 17 Example: Service Logs Events, Boundary Logs Exceptions

This model uses **java.util.logging (JUL)** built into JDK 17 to demonstrate separation of responsibilities. No Spring Boot, Maven, or external libraries are needed.

Three scenarios:

1. **O-100 / OK:** the service completes the simulated processing step and logs an INFO business event; the entry point returns the result.
2. **O-200 / OUT_OF_STOCK:** the service decides to reject, logs an INFO event with a reason code, and throws a business exception; the entry point maps the result to a simulated **409** response code, **without logging the same failure again**.
3. **O-300 / INVENTORY_DOWN:** the service encounters a dependency error, preserves the exception, and throws it upward; the entry point is the **terminal boundary**, logs one ERROR/SEVERE with the cause, and produces a simulated **503** response code.

This is **not a real web server**, and the "HTTP" lines are only **simulated results at the boundary**. The goal is to observe event counts and log placement, not to test HTTP networking.

### 7.1. Complete Source Code

Save **ServiceLoggingDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ServiceLoggingDemo {

    enum Scenario {
        OK, OUT_OF_STOCK, INVENTORY_DOWN
    }

    static final class OutOfStockException extends RuntimeException {
    }

    static final class InventoryUnavailableException
            extends RuntimeException {
    }

    record Receipt(String orderId) {
    }

    static final class OrderService {
        private static final Logger LOG =
                Logger.getLogger("demo.orders.OrderService");

        Receipt create(String orderId, Scenario scenario) {
            if (scenario == Scenario.OUT_OF_STOCK) {
                LOG.info("order.rejected orderId=" + orderId
                        + " reason=OUT_OF_STOCK");
                throw new OutOfStockException();
            }

            if (scenario == Scenario.INVENTORY_DOWN) {
                // Do not log stack trace and rethrow in the service.
                throw new InventoryUnavailableException();
            }

            LOG.info("order.accepted orderId=" + orderId);
            return new Receipt(orderId);
        }
    }

    static final class EntryPoint {
        private static final Logger LOG =
                Logger.getLogger("demo.orders.EntryPoint");
        private final OrderService service = new OrderService();

        void handle(String orderId, Scenario scenario) {
            try {
                Receipt receipt = service.create(orderId, scenario);
                System.out.println(
                        "HTTP 201 orderId=" + receipt.orderId());
            } catch (OutOfStockException ex) {
                // Business rejection was already logged as an event by the service.
                // No need to log the same exception again.
                System.out.println("HTTP 409 code=OUT_OF_STOCK");
            } catch (InventoryUnavailableException ex) {
                // The boundary owns logging the terminal error once.
                LOG.log(Level.SEVERE,
                        "request.failed orderId=" + orderId, ex);
                System.out.println(
                        "HTTP 503 code=INVENTORY_UNAVAILABLE");
            }
        }
    }

    private static Handler stdoutHandler() {
        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(getFormatter().format(record));
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String cause = record.getThrown() == null
                        ? ""
                        : " cause="
                                + record.getThrown()
                                        .getClass().getSimpleName();

                return record.getLevel().getName() + " "
                        + record.getLoggerName() + " "
                        + record.getMessage() + cause;
            }
        });
        return handler;
    }

    public static void main(String[] args) {
        Logger packageLogger = Logger.getLogger("demo.orders");
        packageLogger.setLevel(Level.ALL);
        packageLogger.setUseParentHandlers(false);
        Handler handler = stdoutHandler();
        packageLogger.addHandler(handler);

        try {
            EntryPoint entry = new EntryPoint();
            entry.handle("O-100", Scenario.OK);
            entry.handle("O-200", Scenario.OUT_OF_STOCK);
            entry.handle("O-300", Scenario.INVENTORY_DOWN);
        } finally {
            packageLogger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

### 7.2. Compile and Run

~~~bash
javac ServiceLoggingDemo.java
java ServiceLoggingDemo
~~~

**Expected stdout on JDK 17 or later:**

~~~text
INFO demo.orders.OrderService order.accepted orderId=O-100
HTTP 201 orderId=O-100
INFO demo.orders.OrderService order.rejected orderId=O-200 reason=OUT_OF_STOCK
HTTP 409 code=OUT_OF_STOCK
SEVERE demo.orders.EntryPoint request.failed orderId=O-300 cause=InventoryUnavailableException
HTTP 503 code=INVENTORY_UNAVAILABLE
~~~

Why the output is predictable:

- The program runs sequentially on a single thread without timestamps or randomness.
- Child loggers **demo.orders.OrderService** and **demo.orders.EntryPoint** inherit configuration from **demo.orders**; this parent holds the single handler and calls **setUseParentHandlers(false)** so duplicates are not printed through the JUL root handler.
- The formatter intentionally prints only **level, logger name, message, and exception class name** so the output does not depend on timestamps or stack trace line numbers.
- The OUT_OF_STOCK scenario produces **one business event in the service**, and the entry point does not log the exception a second time.
- The INVENTORY_DOWN scenario does not produce a success business event; **the boundary logs one terminal failure** and retains the Throwable object in the LogRecord.
- The "HTTP 201/409/503" lines are only simulated application outcome mappings, with no sockets or servlets involved.

### 7.3. Limitations of the Example

In production, **do not use the demo's minimal handler**. The formatter here prints only the **exception class name**, intentionally omitting stack traces so the lesson has stable stdout. A real backend should support **Throwable + stack trace** at the terminal failure log point, along with redaction/structured fields policies and appropriate buffering.

The demo code uses known static orderIds; if orderId comes from a client, **validate and encode it according to the log format** to avoid CRLF/log forging or sensitive data exposure. The 201 result also **does not prove a database transaction committed** because the program has no transactions.

Try changing the OUT_OF_STOCK catch block to:

~~~java
// Anti-pattern: logging the same exception after it was already handled.
LOG.log(Level.SEVERE, "Order failed", ex);
System.out.println("HTTP 409 code=OUT_OF_STOCK");
~~~

If you add such a log, the same business rejection produces both an INFO "order.rejected" and a SEVERE stack trace, making severity metrics noisy. Decide **which events need to be logged and at what level**, rather than automatically logging an exception whenever you catch one.

## 8. Logging Exceptions Properly in Services

### 8.1. Do Not Drop the Cause When Wrapping Exceptions

If a service needs to **translate an infrastructure exception into a clearer business/technical exception**, preserve the cause:

~~~java
// Illustrative snippet; requires classes from a real project.
try {
    inventoryClient.reserve(orderId);
} catch (RemoteInventoryException ex) {
    throw new InventoryUnavailableException(
            "Inventory service unavailable", ex);
}
~~~

The snippet above assumes `InventoryUnavailableException` has a matching `(String, Throwable)` constructor in the project. It is **not standalone code** and does not use the empty exception class from Section 7.

A bad pattern:

~~~java
// BAD: loses the original cause.
catch (RemoteInventoryException ex) {
    throw new RuntimeException("Cannot reserve inventory");
}
~~~

When the cause is lost, the boundary struggles to distinguish timeouts, network resets, permission denied errors, or bugs. **A service can add business context via exception types/codes without logging the error immediately**.

### 8.2. Keep Error Messages Safe

Exception messages can contain data from external APIs, SQL, paths, URLs, HTTP headers, or user input. When wrapping, use a stable error code; do not embed tokens, passwords, bodies, or entire exception texts into the new message unchecked.

Distinguish between:

- **Internal engineering information:** exception type, cause chain, stack trace, service/dependency, traceId.
- **Information returned to clients:** approved error code/short description, without exposing internal stacks/credentials.
- **Information in logs:** only fields needed for investigation and permitted by policy.

### 8.3. SLF4J: Pass the Throwable to the Backend

In a project using SLF4J 2.x and a compatible provider, a clear way to log a terminal exception is:

~~~java
// Illustrative snippet; requires logger, orderId, and Throwable ex variables.
logger.atError()
      .addKeyValue("event", "order.request.failed")
      .addKeyValue("orderId", orderId)
      .addKeyValue("errorCode", "INVENTORY_UNAVAILABLE")
      .setCause(ex)
      .log("Order request failed");
~~~

The SLF4J 2.x fluent API supports setting the cause on an event; however, **the backend/layout determines how the Throwable and key-value pairs are printed**. If the encoder does not include key-value pairs in the output, they may not appear on dashboards. Verify the actual configuration.

With standard SLF4J style:

~~~java
// Illustration: log the exception object, not just its message.
logger.error("Order request failed, orderId={}", orderId, ex);
~~~

In common SLF4J versions, a `Throwable` as the final argument is recognized by the backend as the cause. Avoid turning it into a string:

~~~java
// BAD: only logs the message string, losing the stack/cause.
logger.error("Order request failed: {}", ex.getMessage());
~~~

However, **preserving the cause does not mean logging at every layer**. Choose only the layer responsible for the terminal failure.

### 8.4. JUL: Logging with a Throwable Parameter

JUL provides an overload:

~~~java
// Illustration, not a standalone main.
logger.log(
        java.util.logging.Level.SEVERE,
        "Inventory operation failed",
        exception);
~~~

This creates a `LogRecord` with a `Throwable`; the formatter/handler decides how to output the stack. If you only do:

~~~java
// BAD: exception.toString() does not automatically log the full stack trace.
logger.severe("Inventory operation failed " + exception);
~~~

you typically get only the exception class and message without a detailed stack trace. The same principle applies to other Java logging backends.

## 9. Service Exceptions and Mapping at the HTTP Boundary

A Spring Boot architecture typically separates responsibilities as follows:

~~~text
OrderController
    │
    ▼
OrderService
    │
    ├── success → return result
    ├── business conflict → throw OutOfStockException
    └── infrastructure failure → throw InventoryUnavailableException
    │
    ▼
@RestControllerAdvice / framework exception resolver
    │
    ├── 201 or 200 (from controller)
    ├── 409 (business conflict)
    └── 503 (dependency unavailable)
    │
    ▼
Access log records HTTP status; terminal error logged at the appropriate point
~~~

**The HTTP codes are only API contract examples.** Another system might use 422 for business rule violations, 404 when a resource does not exist, or 500 when unknown. **Do not infer HTTP status codes directly from Java exception names**.

### 9.1. Distinguishing @Service and @RestControllerAdvice

In Spring, a `@Service` method is often called by multiple types of callers: HTTP controllers, scheduled jobs, Kafka consumers, and batch tasks. Therefore, a service should have an exception contract and business events that are **independent of HTTP**.

An exception handler at the web boundary can log the terminal failure when needed:

~~~java
// Illustration in a Spring Web app with imports, types, and logger already defined.
@ExceptionHandler(InventoryUnavailableException.class)
public ResponseEntity<ApiError> inventoryFailure(
        InventoryUnavailableException ex) {
    logger.error("HTTP request failed: inventory unavailable", ex);

    ApiError body = new ApiError("INVENTORY_UNAVAILABLE");
    return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(body);
}
~~~

The snippet above is **not a standalone program**: it requires `@RestControllerAdvice`, `ApiError`, the exception class, a logger, and Spring dependencies. If another centralized exception handler already logs the `Throwable`, do not log it again in this handler.

A business conflict such as `OutOfStockException` may only need to return 409 and rely on the INFO business event in the service. If the access log already records `status=409`, adding an ERROR log is not mandatory.

### 9.2. Should Exceptions Be Logged in Both Controller and Advice?

Usually **no**, if both log the same stack trace. Pick **one owner for terminal errors** at the web boundary. Other layers propagate or normalize exceptions according to the contract.

Keep in mind that **@RestControllerAdvice does not catch every error source**: security filters may reject requests before reaching the controller, the servlet container has its own error dispatch, and async/background jobs have different boundaries. The logging policy must cover all actual entry point types.

## 10. Transactions: Do Not Log "Succeeded" Too Early

This is a critical mistake when logging in services.

### 10.1. Why Can Logging Inside @Transactional Be Wrong?

Suppose you have Spring code:

~~~java
// Illustration in a service using Spring Transaction Management.
@Transactional
public OrderReceipt createOrder(CreateOrderCommand command) {
    Order saved = repository.save(buildOrder(command));
    logger.info("order.created orderId={}", saved.getId());
    return toReceipt(saved);
}
~~~

Right after `logger.info`, the transaction **may not have committed yet**. With standard Spring transaction proxies, the commit typically happens when the method returns and the transaction advice finishes; the transaction can still roll back due to a flush/commit error, or because an outer transaction continues processing and later rolls back.

The log line "order.created" is easily interpreted as **durably saved**, even though the database ultimately **did not commit**. Logs do not roll back along with a transaction.

### 10.2. Expressing the Stage Accurately

If logging inside a transaction, name the event to reflect **the actual intent or processing milestone**:

~~~text
INFO event=order.create.attempted orderId=O-350
INFO event=order.validation.passed orderId=O-350
~~~

Do not use **committed** without evidence of commit. Consider whether both events are even needed; usually you should not log every small step at INFO.

### 10.3. Logging Events After Commit

With Spring, you can design domain events and a subscriber that runs after commit via **@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)**. Flow illustration:

~~~text
@Service @Transactional
    │
    ├── Save Order
    ├── Publish domain event inside transaction
    └── Method returns
            │
            ▼
      Transaction commits
            │
            ▼
  AFTER_COMMIT listener → log "committed" event
~~~

This is **an architectural option**, not an absolute delivery guarantee. A listener running after commit **can still fail to write a log** if the process crashes or the sink fails. When you need certainty that downstream business events are not lost, use a durable mechanism such as a **transactional outbox**, idempotent consumers, and controlled retries.

Additionally, an `AFTER_COMMIT` listener **does not run automatically when there is no active transaction** unless configured with fallback; be sure to understand the framework version and lifecycle.

### 10.4. Nested Transactions and Retries

A service method returning does not mean the entire workflow is complete. An outer transaction may roll back, a message consumer may retry, or a payment gateway may accept a request while completing via a later callback. Name events to reflect **the business reality at the time of logging**, without overstating the state.

## 11. Choosing Log Levels in Services

| Service Situation | Typically Appropriate Level | Reason |
| --- | --- | --- |
| Well-defined business milestone | INFO | Has operational value; manage volume. |
| Rejected outcome per normal rules | INFO or WARN | Not a bug; use reason codes and metrics. |
| Debugging an internal decision branch | DEBUG | Details needed only during diagnosis. |
| Very detailed trace | TRACE | High volume; do not enable broadly in production. |
| Temporary retry within limits | DEBUG/WARN depending on significance | Avoid ERROR stack traces on every attempt. |
| Retries exhausted and exception propagated | Not required in service | The final boundary can log ERROR once. |
| Fallback succeeded with degraded service | WARN | Service handled the incident; boundary may return success. |
| Critical invariant violated | ERROR if service owns terminal failure; otherwise propagate | Investigate cause where full context is available. |
| Unhandled dependency down | Propagate Throwable or wrap with cause | Do not default to logging stacks in both service and upper layers. |
| Audit event with retention obligation | Use audit/event pipeline per policy | Standard logging does not guarantee durability or integrity. |

**There is no automatic mapping** where checked exception = WARN and unchecked = ERROR. Exception type is a Java language mechanism; log level reflects **event severity and handling responsibility**.

Similarly, if a service returns `Optional.empty` per its contract, that is not an exception and not automatically an error. You may need no log at all, or a meaningful business event.

## 12. Log Context: Correlation IDs, Error Codes, and Logger Names

A useful service record should include **stable identifiers** to link with requests/tracing:

~~~json
{
  "event": "order.reservation.failed",
  "service": "order-service",
  "environment": "prod",
  "logger": "com.example.orders.OrderService",
  "order_id": "O-401",
  "error_code": "INVENTORY_UNAVAILABLE",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "attempt": 3
}
~~~

This is **illustrative JSON**, not the default output of SLF4J, JUL, or Spring Boot. **trace_id** must come from a valid tracing context; do not invent fake values in production. You can use span ID, request ID, or message ID depending on the entry point and infrastructure.

### 12.1. Class-Based Logger Names

Common practice with SLF4J:

~~~java
// Illustration in an OrderService class with an SLF4J dependency.
private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);
~~~

Naming loggers by class makes it easy to filter logs by package or service. If using custom-named loggers, maintain a clear naming convention and avoid mixing unrelated categories that make log-level configuration difficult.

### 12.2. Stable Event Names and Error Codes

Instead of logging only free-form sentences:

~~~text
Failed unexpectedly!
~~~

keep event names and error codes stable so dashboards and queries do not depend on prose:

~~~text
event=inventory.reserve.failed errorCode=REMOTE_TIMEOUT orderId=O-401
~~~

Human-readable messages are still helpful, but stable event names/error codes enable aggregation and alerting. Do not use raw exception messages as error codes, because their wording can change across vendors/versions or contain untrusted data.

### 12.3. MDC and ThreadLocal Context

With SLF4J/Logback or Log4j2, MDC/ThreadContext helps attach context like `traceId`/`requestId` to logs. It is usually bound to a **thread or execution context**, and does not automatically propagate across every `ExecutorService`, `@Async`, `CompletableFuture`, Reactor pipeline, or message consumer.

Illustrative example in an SLF4J application:

~~~java
// Illustration: requestId was validated at the boundary.
try {
    MDC.put("requestId", requestId);
    orderService.createOrder(command);
} finally {
    MDC.remove("requestId");
}
~~~

In systems with multiple MDC values, use a **capture/restore** mechanism appropriate to your backend and framework; do not accidentally clear context owned by the caller. If execution crosses threads, use verified instrumentation/context propagation. **Do not put passwords or tokens into MDC** just for search convenience.

### 12.4. Why Context Must Not Determine Authorization

A trace ID or tenant ID sent by a client can be forged. Validate against a grammar, distinguish an authenticated tenant from a tenant header, and encode per the output format. **Do not use client-controlled MDC values to grant log read access or route secrets**.

## 13. Services Calling Remote APIs: Logging Requests and Failures

When a service calls an HTTP client, database, or broker, separate:

- **Outcome of the dependency attempt:** timeout, connection refused, 429, 503, parse failure.
- **Outcome of the service operation:** retry succeeded, fallback, exception thrown.
- **Outcome of the entry point:** HTTP 201/409/503, job success/failure, message ACK/NACK.

An attempt receiving 503 does not mean the overall business request returns 503, because the service may retry and succeed. If you log ERROR on the first attempt and the overall operation later succeeds, dashboards may turn red even though the transaction did not fail.

Reasonable pattern:

~~~text
DEBUG event=inventory.call.retry attempt=1 reason=HTTP_503
WARN  event=inventory.call.retry attempt=2 reason=HTTP_503
INFO  event=order.created inventorySource=LIVE
~~~

Or when retries are exhausted:

~~~text
WARN  event=inventory.call.retry_exhausted attempts=3
ERROR event=http.request.failed errorCode=INVENTORY_UNAVAILABLE
~~~

Two records in the second case make sense only when **retry_exhausted is an independent operational event**; do not duplicate the stack cause in both lines. An implementation can also log only the terminal ERROR if metrics already track retries; do not force every event to emit a log.

### 13.1. Do Not Log Full Request/Response Bodies

Remote responses can contain tokens, customer data, session cookies, card data, or internal information. When diagnosing issues, prefer **allowed host/service, operation, status, elapsed time, attempt, error type, and correlation ID**. Query parameters can be redacted. Large response sizes also cause log flooding.

### 13.2. Measuring Duration for Service Calls

In Java, **`System.nanoTime()`** is suitable for measuring **relative elapsed duration**, not for generating global timestamps:

~~~java
// Illustrative snippet, not a standalone Java class.
long start = System.nanoTime();
try {
    return inventoryClient.reserve(orderId);
} finally {
    long elapsedNanos = System.nanoTime() - start;
    metrics.recordInventoryLatency(elapsedNanos);
}
~~~

Log latency at key milestones when needed; recording via metrics is usually more efficient than emitting INFO logs on every method call. If using tracing/metrics, there is no need to repeat excessive fields when correlation IDs already exist.

## 14. Preventing Data Leaks from Service Logs

Services hold extensive business data, so they carry a higher risk of accidentally logging sensitive data than the access layer.

**Do not log**:

- Passwords, OTPs, API keys, access tokens, refresh tokens, `Authorization`/`Cookie` headers.
- Unpermitted payment data, card numbers, sensitive account details, raw webhook secrets.
- Entire request/response DTOs if DTOs contain PII or uncontrolled fields.
- Raw SQL parameters, connection strings with passwords, internal credentials.
- Exception messages from remote services if they contain untrusted data.
- Large message queue payloads or unescaped user-generated text.

A core principle is to **log the minimum needed for investigation**, rather than logging `toString()` of entire objects out of habit.

### 14.1. Redaction Does Not Replace Access Control

If a user ID is needed for support, consider pseudonymization/masking per policy; however, anonymized IDs can still correlate behavior over multiple actions. Log storage requires appropriate read permissions, retention, and auditing. Do not assume dev/CI environments contain no real data.

### 14.2. Input and Log Injection

An `orderId` or user-provided reason might contain CR/LF, delimiters, or control characters. Use a **structured JSON encoder** or escaping suited to the sink format, validate ID fields, and avoid building JSON via string concatenation. Fixed SLF4J message templates are good, but **they do not automatically prevent** CRLF characters from creating forged lines in plain-text layouts.

### 14.3. Do Not Leak Exceptions Through API Responses

Server logs can retain cause chains where permitted, but clients should not receive stack traces or internal hostnames simply because a service threw an exception. API responses should use **safe error codes and short messages**, with a trace/request ID for support reference.

## 15. Spring @Transactional: Rollback, Retry, and Observable Events

### 15.1. @Transactional Does Not Synchronize Logs

A record printed to the console or sent to a Kafka logger appender **is not part of the database transaction**. If the transaction rolls back, logs already emitted **are not rolled back with it**. Any statement claiming "committed" must be tied to the actual commit point or a corresponding durable event mechanism.

### 15.2. Exceptions and Rollback Rules

By default, Spring declarative transactions typically roll back on **`RuntimeException`/`Error`**, and do not automatically roll back on all **checked exceptions** unless rollback rules are configured. Therefore:

- Do not assume a transaction rolled back just because code caught an `Exception`.
- Do not catch an error and return a success value when a rollback is actually required.
- Understand `rollbackFor`/`noRollbackFor` and outer transactions.
- If code intercepts an exception and swallows it, it can alter the transaction outcome; logging does not replace transaction decisions.

When an error occurs, the service should preserve clear exception semantics; the boundary can map the appropriate response.

### 15.3. Retries After Transaction Failure

A conflicting transaction may be retried. If a service logs "created" on every attempt, the logs may show three "created" records even though only one committed—or none at all. Log **attempt** if needed, and log **committed** only when the event has actually committed per contract.

### 15.4. Critical Business Events Must Not Depend on the Logger

If a payment must emit a downstream event even if the process crashes after commit, store an **outbox row in the same database transaction** and use a publisher with retries/idempotency. An INFO log line is not an event delivery guarantee; logging is typically best-effort and can be dropped due to queues, backpressure, files, or collectors.

## 16. Batch, Scheduler, and Message Consumers: Non-Controller Boundaries

The same `OrderService` can be invoked through many types of entry points:

| Entry Point | Boundary Owning Terminal Outcome | Logging Considerations |
| --- | --- | --- |
| HTTP controller | Exception handler/access log | HTTP status, route, traceId; do not log two stack traces. |
| Scheduled job | Job runner/scheduler | Job ID, run ID, retries, final success/failure. |
| Kafka/RabbitMQ listener | Message listener/consumer adapter | Message ID, partition/offset when permitted, attempt, ACK/NACK/DLQ. |
| CLI command | Command handler/main | Exit code, operation, terminal exception. |
| Async task | Task runner/future completion | Exception not lost in Future; context propagation. |
| Batch import | Chunk/item processor or job step | Success/failure counts; avoid useless per-row logs. |

If a business service always logs ERROR and rethrows, every caller receives an error **that was already logged** and logs another terminal error with its own context. A better design is for **the service to throw meaningful exceptions**, while the specific boundary logs the terminal failure with its context.

### 16.1. Exceptions in CompletableFuture

An async task can fail and hold the exception inside a **`CompletableFuture`**. If no caller observes completion, the failure is hard to detect. Place a terminal handler at the end of the pipeline and use appropriate metrics/logs; avoid having the service log a stack trace and then rethrow through multiple `exceptionally`/`handle` stages.

### 16.2. Message Retries and Duplicate Logging

A message may be reprocessed after a timeout or consumer restart. If events share the same `messageId` across different attempts, distinguish **retries of the same work** from **distinct business events**. Do not log "processed" before ACK/commit per contract and assume the message was handled once.

## 17. Testing: Verify Service Logs, Not Just Return Values

A good service test verifies both **return values/exceptions** and **logging side effects** when logs are part of the observability contract.

### 17.1. Scenario Table

| Scenario | Service Behavior | Expected Logs | Logs to Avoid |
| --- | --- | --- | --- |
| Valid order creation | Returns result | One valid business event (if required by policy). | ERROR stack trace. |
| Out of stock | Throws business exception or returns rejection | Appropriate business reason code. | Duplicate ERROR if the boundary handles it as expected. |
| Remote inventory timeout | Wraps/propagates cause | Terminal error at the final boundary. | Identical stack traces at every layer. |
| Retry then success | Returns final success | Appropriate retry summary/metric and success event. | Multiple terminal ERRORs for recovered attempts. |
| Retries exhausted | Propagates final failure | One terminal error with cause and attempts. | False "success" event. |
| Transaction rollback | Does not commit | Attempt/rollback event if useful. | "committed" event before commit. |
| Background job fails | Job marks failure | Job-level terminal event with job/run ID. | Relying on HTTP advice that never runs. |
| Personal data in DTO | Handled properly | Allowed and redacted fields. | Raw DTO/token/password. |
| Input contains CRLF | Handled per policy | Event remains a single structured record at the sink. | Forged lines from log injection. |
| Async context propagation | Crosses executor | Matching correlation ID or explicitly absent. | Previous request's trace ID leaking via ThreadLocal. |
| Log backend fails | Business flow follows policy | Independent error telemetry when possible. | Assuming the logger always persists durably. |

### 17.2. How to Test Event Counts

With Logback/Log4j2 or JUL, attach a **test appender/handler** to a controlled logger and assert:

- Success scenario has the expected event name, level, and fields.
- Business rejection does not emit duplicate ERRORs in both service and boundary.
- Terminal technical failure has **one event** and a `Throwable` cause.
- Sensitive fields do not appear.
- If async, wait for completion with a bounded timeout; do not rely on fixed sleeps.
- Tests do not leave handlers or global logger state affecting other tests.

In JUL, logger handlers are global state by name in `LogManager`. When a test adds a handler, be sure to **remove/close it in `finally`**, and restore `level`/`useParentHandlers` if modified. With a Logback test appender, also detach and stop it when finished.

### 17.3. Test Real Transactions, Not Just Mocks

A unit test with a mocked repository can show `logger.info("created")` running as expected, without testing commit behavior. For "committed" events or critical audits, use an **integration test** with a real transaction manager and test:

- Successful commit.
- Flush/constraint violation error causing rollback.
- Outer transaction rollback after the method returns.
- Retry/duplicate or after-commit callback.
- Listener not being invoked on rollback.

Do not treat log text as the sole proof that the database committed.

## 18. Real-World Diagnosis: One Request Produces Multiple ERRORs

Suppose an order placement request hits an inventory timeout and **four ERROR records** appear on the dashboard.

### Step 1: Follow the Same Trace/Request ID

Collect events sharing the same `traceId`/`requestId`, and inspect logger names and timestamps. Determine whether they share the same cause chain/stack trace and request, or represent separate attempts.

### Step 2: Trace the Exception Path

~~~text
InventoryClient: timeout
    │
    ├── logger.error(..., ex)  [copy 1]
    ▼
OrderService catch + log.error [copy 2]
    ▼
OrderController catch + log.error [copy 3]
    ▼
GlobalExceptionHandler log.error [copy 4]
~~~

If no intermediate layer handles the failure, four copies are **overlogging**. Do not "reduce alerts" by disabling ERROR globally; fix who owns the terminal log.

### Step 3: Agree on a Single Owner

For example, only **GlobalExceptionHandler** logs the terminal ERROR. `InventoryClient` can record metrics/network attempt data; the service adds error code/cause when wrapping; the controller does not log duplicates.

### Step 4: Keep Genuinely Needed Business Events

If the service makes a fallback, retry-exhausted, or invariant decision, it can still log that event at INFO/WARN **without reprinting the same stack trace**. This keeps traceability without losing business meaning.

### Step 5: Write a Regression Test

Assert **1 terminal error event / logical request** at the chosen boundary, with the cause, `errorCode`, and `traceId`; if multiple retries occur, test attempt counts and log levels separately. Do not measure error counts by counting ERROR lines when the pipeline can emit duplicates.

## 19. Common Mistakes

**1. Log-and-throw at every layer.** Leads to duplicate stack traces, signal loss, and higher costs.

**2. Logging only `ex.getMessage()` and dropping the `Throwable`.** Loses the stack trace/cause chain needed for debugging; may expose data from the message.

**3. Returning `null` or `Optional.empty` after swallowing a technical error.** When the business contract does not allow it, the error is hidden and the boundary may return false success.

**4. Logging "success/committed" before transaction commit.** Misleading if the transaction rolls back.

**5. Logging ERROR for every business exception.** Expected out-of-stock or conflicts are not necessarily system errors.

**6. Logging INFO for every getter/method.** Increases volume, hurts performance, and drowns out important logs.

**7. Putting HTTP status in every service log.** Services can be called from schedulers/consumers; status belongs to the HTTP boundary.

**8. Logging inputs/DTOs with unchecked `toString()`.** Risks leaking secrets/PII and overly verbose logs.

**9. Using string concatenation when the logger supports templates.** Loses lazy formatting optimization and mixes input data with log syntax.

**10. Lacking stable error codes/event names.** Queries end up depending on prose that changes across versions.

**11. Losing trace/correlation IDs across thread boundaries.** Makes log correlation hard; `ThreadLocal` context can also leak if not cleaned up.

**12. Assuming logging is a durable audit/event store.** Queues, crashes, filesystems, collectors, and retention policies can all drop events.

**13. Logging multiple times during retries and counting them as separate errors.** Track attempt IDs and terminal outcomes.

**14. Testing only controller advice.** Background consumers, async tasks, or filters outside controllers have different boundaries.

**15. Logging third-party exception messages without security review.** They may contain secrets or strings enabling log forging.

**16. Failing to clean up test handlers/appenders.** Subsequent tests receive extra events, creating the illusion of duplicate production logging.

**17. Logging an ERROR stack trace before a fallback succeeds.** Very noisy diagnostics; prefer retry/fallback events with appropriate levels and context.

**18. Using logs instead of metrics on high-load paths.** Every method call does not need INFO; place metrics or trace spans at appropriate points.

## 20. Service Logging Design Checklist

Before merging code that adds a logger in a service, check:

1. **Purpose:** Who will use this event to investigate what decision?
2. **Responsibility:** Did the service handle, retry/fallback, or make a business decision? Or is it just catch-and-rethrow?
3. **Level:** Does INFO/WARN/ERROR/DEBUG match the frequency and semantics?
4. **No duplicates:** Which layer will log the terminal failure for this exception? Is there more than one stack trace?
5. **Transaction:** Does the message assert something not yet committed or ACKed?
6. **Context:** Does it include event name, error code, service, `traceId`/`requestId`, attempt, and required IDs?
7. **Security:** Are there tokens, passwords, PII, raw bodies, or untrusted exception messages?
8. **Format:** Are structured encoders/escaping and size limits in place?
9. **Backend:** Does SLF4J have the right provider, and do JUL/Logback/Log4j2 have enabled appenders/handlers at appropriate levels?
10. **Reliability:** Must the event never be lost? If so, is an outbox/audit store needed instead of a logger?
11. **Performance:** Is the event emitted on a hot path or high-volume retry loop?
12. **Testing:** Are event counts/levels/fields, cause preservation, and absence of duplicates asserted?

## 21. Review Questions

1. An `OrderService` catches `SQLException`, logs ERROR, and rethrows; the controller also logs ERROR. Where should this be fixed and why?
2. When a service falls back to cache after a timeout and returns success, will the boundary log the original timeout? What should the service log?
3. Why can logging `"order.created"` inside a `@Transactional` method be wrong even after `repository.save` returns?
4. Why should service exceptions not always carry an HTTP status?
5. In SLF4J, what is the difference between logging an error with a `Throwable` versus logging only `ex.getMessage()`?
6. Does an `OUT_OF_STOCK` business exception need to be logged at ERROR? State the criteria for choosing the level.
7. Why can `MDC`/`requestId` go missing when work is handed off to an `ExecutorService`?
8. A scheduled job calls the same `OrderService`, which fails, and `@RestControllerAdvice` does not run. Who must own the terminal error log?
9. A payment state-transition event must never be lost: why is logging INFO insufficient and what mechanism should be used?
10. How can you use a test appender to prove that a failure chain produces only one terminal stack trace log?

## 22. Conclusion

**Proper service-layer logging means recording the business decisions and processing outcomes the service actually owns—not logging every call or every exception.** For unhandled errors, propagate exceptions with clear causes/context and let the appropriate boundary log the terminal failure **once**. When the service handles retries/fallbacks or makes a meaningful rejection decision, it can log an independent event at an appropriate level.

Remember the three boundaries: **the service knows the business logic**, **the entry point knows the final outcome**, and **the transaction manager knows commit/rollback**. Log messages must reflect those boundaries. Combine stable event names, structured fields, trace context, redaction, testing, and dedicated outbox/audit mechanisms for durable events so your logs remain genuinely useful and reliable.

### References

- Oracle JDK 17 — java.util.logging.Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Oracle JDK 17 — Handler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html
- SLF4J Manual — Logger and fluent logging: https://www.slf4j.org/manual.html
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework — Declarative Transaction Rollback: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Exception Handling in MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OpenTelemetry Logs Data Model: https://opentelemetry.io/docs/specs/otel/logs/data-model/