# Message Parameterization and Logging Exceptions with Stack Traces

In a Spring Boot application, logging is not merely printing a few lines of text to the console. Logs show which operation occurred, which contextual data was involved, where an error originated, and which methods the stack trace passed through. However, if logging is done improperly, an application can become both slower and lacking the information needed to diagnose incidents.

The two most important techniques in this lesson are:

1. **Message parameterization:** using SLF4J's `{}` placeholders instead of string concatenation or calling `String.format(...)` before every log call.
2. **Proper exception logging:** passing the `Throwable` object in the right position so the logging framework prints the stack trace, rather than logging only `exception.getMessage()`.

This lesson belongs to the **Logging** chapter of **Spring Boot Fundamentals**. We will use the `org.slf4j.Logger` and `LoggerFactory` APIs, observe how Spring Boot integrates the logging backend, distinguish overloads accepting `Throwable`, examine performance, log levels, structured logging, and write clear Spring Boot code applicable to error diagnostics.

## 1. What layers make up logging in Spring Boot?

When you write:

```java
private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);
```

you are using the **SLF4J API**. SLF4J is a facade: it provides a unified logging call interface, while formatting and output are handled by the logging provider/backend.

In a typical Spring Boot application:

```text
Service / Controller / Component
              │
              ▼
       SLF4J Logger API
              │
              ▼
      Logging provider/backend
        (usually Logback)
              │
              ▼
   Console / file / log collector
```

Standard Spring Boot starters bring in `spring-boot-starter-logging`, which configures Logback as the default backend. Spring Boot can also integrate other backends such as Log4j2 when dependencies are configured accordingly.

**Do not confuse the API with the backend:**

- `Logger`, `LoggerFactory`, `{}` placeholders: programming with SLF4J.
- Pattern layouts, appenders, rolling files, JSON encoders: how the backend actually outputs logs.
- `logging.level.*` in Spring Boot: log level configuration by package/class, passed by Boot to the logging system.

### 1.1. Logger example in a service

```java
package com.example.demo.order;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);

    public void process(String orderId) {
        log.info("Starting order processing: orderId={}", orderId);
    }
}
```

The message portion might look like:

```text
Starting order processing: orderId=ORD-123
```

The timestamp, INFO level, thread, and logger name can be added by the backend. Those parts are not content you concatenate manually inside `log.info(...)`.

### 1.2. Where should loggers be placed?

Usually use one logger per class:

```java
private static final Logger log =
        LoggerFactory.getLogger(MyService.class);
```

This approach:

- Identifies which class emitted the log.
- Aligns with `logging.level.com.example...` configuration.
- Avoids creating a new logger inside every method.
- Makes switching backends easier through SLF4J.

You can use Lombok's `@Slf4j` annotation to generate the logger field, though that is a compile-time convenience. This lesson uses plain Java to show the API clearly without depending on Lombok.

## 2. Why parameterize messages?

Suppose a service processes an order:

```java
String orderId = "ORD-123";
int attempt = 2;
```

There are at least three ways to log this information.

**Approach 1 — String concatenation:**

```java
log.debug(
        "Retrying order " + orderId + " at attempt " + attempt
);
```

**Approach 2 — Pre-formatting:**

```java
log.debug(String.format(
        "Retrying order %s at attempt %d",
        orderId,
        attempt
));
```

**Approach 3 — Using SLF4J placeholders:**

```java
log.debug(
        "Retrying order {} at attempt {}",
        orderId,
        attempt
);
```

All three can produce the same message, yet approach 3 is the standard and best choice with SLF4J.

The main reason: **SLF4J can defer message formatting work** until it knows whether the corresponding log level is enabled.

### 2.1. When DEBUG is disabled

Suppose:

```properties
logging.level.com.example.demo=INFO
```

Then `log.debug(...)` is not emitted.

With string concatenation:

```java
log.debug("Order " + orderId + " attempt " + attempt);
```

Java still has to evaluate the string concatenation before calling `debug(...)`. The log statement may write nothing, yet part of the string construction work was already performed.

With placeholders:

```java
log.debug(
        "Order {} attempt {}",
        orderId,
        attempt
);
```

SLF4J can skip formatting the string when DEBUG is disabled.

**Important limitation:** Java still evaluates argument expressions before calling the method. If you write `expensiveOperation()` in an argument position, that method will still execute even when logging is disabled. We address this in the performance section.

### 2.2. Why not use printf-style?

SLF4J uses `{}`, not `%s` or `%d`.

Incorrect if expecting SLF4J to substitute values automatically:

```java
log.info("Order %s has %d items", orderId, itemCount);
```

The `%s` and `%d` tokens belong to `String.format`, not SLF4J's parameterized message syntax.

Correct:

```java
log.info("Order {} has {} items", orderId, itemCount);
```

Similarly, `{0}` typically belongs to `MessageFormat`, not SLF4J placeholders.

## 3. Basic {} placeholder syntax

SLF4J uses empty curly braces:

```text
{}
```

Example with one parameter:

```java
log.info("Order created: {}", orderId);
```

Two parameters:

```java
log.info(
        "Order {} has status {}",
        orderId,
        status
);
```

Three parameters:

```java
log.info(
        "Order {} for customer {} has {} items",
        orderId,
        customerId,
        itemCount
);
```

In these examples, each placeholder maps to one argument in left-to-right order.

### 3.1. Include field names right inside the message

A context-rich message is usually easier to search when using `key=value`:

```java
log.info(
        "Order created: orderId={} customerId={} amount={}",
        orderId,
        customerId,
        amount
);
```

Example:

```text
Order created: orderId=ORD-123 customerId=C-42 amount=250000
```

This helps readers recognize each value without guessing positions.

However, `key=value` inside a message is still **text**, not synonymous with the backend emitting true structured fields. For JSON logging or structured logging, use the appropriate API/encoder supporting structured fields.

### 3.2. Non-String arguments

SLF4J accepts many types:

```java
log.info("Retry count={}", retryCount);
log.info("Payment successful={}", successful);
log.info("Created at={}", createdAt);
log.info("Currency={}", currency);
```

The backend/message formatter converts them to strings during formatting.

Keep in mind that an object's `toString()` can expose sensitive data or be expensive to compute. Not every object should be passed directly into a log call.

### 3.3. When placeholder and argument counts do not match

Example:

```java
log.info("Order {} status {}", orderId);
```

There are two placeholders yet only one normal argument. The output can leave an unsubstituted placeholder:

```text
Order ORD-123 status {}
```

Conversely:

```java
log.info("Order {}", orderId, status);
```

There may be an unused argument when building the message, depending on overload resolution and `Throwable` handling. Keep placeholder count aligned with the **number of arguments supplying message data**.

Not every argument is a substitution value: a trailing `Throwable` can be extracted as the cause rather than filling a placeholder.

## 4. Use parameterization instead of string concatenation

Compare:

```java
log.info("Received order " + orderId);
```

with:

```java
log.info("Received order {}", orderId);
```

The second form is cleaner and allows skipping formatting when the level is disabled.

Example with multiple variables:

```java
log.debug(
        "Calculated shipping: orderId={} distanceKm={} fee={}",
        orderId,
        distanceKm,
        shippingFee
);
```

instead of:

```java
log.debug(
        "Calculated shipping: orderId="
                + orderId
                + " distanceKm="
                + distanceKm
                + " fee="
                + shippingFee
);
```

The difference becomes even more noticeable in code running many times per request.

### 4.1. Watch out for String.format

Bad for efficient logging:

```java
log.debug(String.format(
        "Batch %s processed %d records",
        batchId,
        processedCount
));
```

`String.format` is called **before** `log.debug`, regardless of whether DEBUG is enabled or disabled.

Better:

```java
log.debug(
        "Batch {} processed {} records",
        batchId,
        processedCount
);
```

Similarly, avoid `MessageFormat.format(...)` or `String#formatted(...)` when simply building an SLF4J message.

### 4.2. Do not pre-format data just for logging

Example:

```java
String formattedAmount = formatCurrency(amount);
log.debug("Order amount={}", formattedAmount);
```

Even with `{}`, `formatCurrency` already ran before the log statement.

If formatting incurs significant cost and is only for DEBUG, you can use a guard:

```java
if (log.isDebugEnabled()) {
    log.debug(
            "Order amount={}",
            formatCurrency(amount)
    );
}
```

Or use the SLF4J 2.x Fluent API with a supplier shown later.

## 5. What information does an exception carry?

In Java, exceptions such as `IllegalArgumentException`, `IOException`, and `DataAccessException` inherit from `Throwable` in the type hierarchy.

An exception typically includes:

- **Type:** class name, e.g., `java.io.IOException`.
- **Message:** short description, possibly `null`.
- **Stack trace:** stack frames showing the call path when the throwable was created/filled.
- **Cause:** root or wrapped exception.
- **Suppressed exceptions:** auxiliary info, commonly seen when closing resources.

Example:

```java
try {
    throw new IllegalStateException("Inventory unavailable");
} catch (IllegalStateException ex) {
    System.out.println(ex.getClass().getName());
    System.out.println(ex.getMessage());
}
```

Those two lines alone do not reveal which file/method/line triggered the exception.

### 5.1. What does a stack trace show?

A simple stack trace:

```text
java.lang.IllegalStateException: Inventory unavailable
    at com.example.demo.InventoryClient.fetch(InventoryClient.java:42)
    at com.example.demo.OrderService.reserve(OrderService.java:85)
    at com.example.demo.OrderController.place(OrderController.java:31)
```

It helps trace backward from where the throwable originated to the call site.

When an exception has a cause:

```text
com.example.demo.OrderProcessingException: Cannot reserve inventory
    at com.example.demo.OrderService.reserve(OrderService.java:91)
Caused by: java.net.SocketTimeoutException: Read timed out
    at ...
```

If you only log the exception message, you can lose both the stack trace and the cause chain. That is why passing the `Throwable` object directly to the logger is usually necessary when logging diagnostic errors.

## 6. The right way to log an exception with its stack trace

SLF4J has an overload accepting `Throwable`:

```java
logger.error(String message, Throwable throwable);
```

Example:

```java
try {
    inventoryClient.reserve(orderId);
} catch (RuntimeException ex) {
    log.error("Inventory reservation failed", ex);
    throw ex;
}
```

When ERROR is enabled, the backend normally prints both the message and the stack trace of `ex`.

Illustrative log snippet:

```text
ERROR ... Inventory reservation failed
java.lang.IllegalStateException: Inventory unavailable
    at com.example.demo.InventoryClient.reserve(InventoryClient.java:42)
    at com.example.demo.OrderService.process(OrderService.java:85)
    ...
```

That is how `log.error("...", ex)` differs from `log.error("{}", ex.getMessage())`.

### 6.1. Pass Throwable, not just the message

Insufficient when a stack trace is needed:

```java
log.error("Inventory failed: {}", ex.getMessage());
```

This line logs a string and does not pass a `Throwable` to the logger. You usually only see:

```text
Inventory failed: Inventory unavailable
```

Exception type, stack frames, cause chain, and suppressed exceptions may all be absent.

Correct when a stack trace is needed:

```java
log.error("Inventory reservation failed", ex);
```

### 6.2. Do not call ex.printStackTrace()

Avoid:

```java
catch (Exception ex) {
    ex.printStackTrace();
}
```

`printStackTrace()` usually writes to `System.err`, bypassing the application's configured logging backend. It is hard to align with log levels, appenders, structured logging, correlation IDs, or collection policies.

Better:

```java
catch (Exception ex) {
    log.error("Unexpected failure during import", ex);
}
```

The code must still have an appropriate error-handling policy: logging does not replace propagating, retrying, rolling back, or returning a response.

### 6.3. Do not pass getStackTrace() as a log argument

Incorrect:

```java
log.error("Unexpected failure: {}", ex.getStackTrace());
```

`getStackTrace()` returns a `StackTraceElement[]` array, not a `Throwable`. Formatting an array is not equivalent to a full exception stack trace, especially with cause/suppressed chains.

Correct:

```java
log.error("Unexpected failure", ex);
```

## 7. Combining placeholders and Throwable properly

In real applications, we want both business context and the stack trace.

Example:

```java
try {
    paymentGateway.charge(orderId, amount);
} catch (PaymentGatewayException ex) {
    log.error(
            "Payment failed: orderId={} amount={}",
            orderId,
            amount,
            ex
    );
    throw ex;
}
```

The message portion can be:

```text
Payment failed: orderId=ORD-123 amount=250000
```

followed by the stack trace of `ex`.

### 7.1. Why are there two placeholders yet three arguments?

The first two arguments supply values for `{}`:

- `orderId`.
- `amount`.

The final argument is `Throwable`. SLF4J detects a throwable in the final position of the argument list and can extract it as the **cause** for the backend to print the stack trace.

Therefore:

```java
log.error(
        "Failed orderId={}",
        orderId,
        ex
);
```

is the common pattern to log both business context and a stack trace.

### 7.2. Throwable should come last

Write:

```java
log.error(
        "Failed to publish event: eventId={} topic={}",
        eventId,
        topic,
        ex
);
```

Avoid writing:

```java
log.error(
        "Failed to publish event: eventId={} topic={}",
        ex,
        eventId,
        topic
);
```

In the second case, `ex` sits in the middle of the arguments. It is no longer in the trailing cause position under standard rules; the message can format unexpectedly and the stack trace may be missing.

**Easy rule to remember:** when you need both a parameterized message and a stack trace, place `Throwable` as the **last argument**.

### 7.3. Do not count the trailing Throwable in placeholder count

Correct:

```java
log.error(
        "Cannot load customerId={} region={}",
        customerId,
        region,
        ex
);
```

Inappropriate:

```java
log.error(
        "Cannot load customerId={} region={} exception={}",
        customerId,
        region,
        ex
);
```

With overloads/formatters treating trailing `ex` as the cause, `ex` is not used to fill the `exception={}` placeholder. Output can still contain an unsubstituted placeholder.

If you want the exception type inside the message **and** the stack trace, pass the type as a separate data argument:

```java
log.error(
        "Cannot load customerId={} errorType={}",
        customerId,
        ex.getClass().getSimpleName(),
        ex
);
```

Here two placeholders are filled with `customerId` and the exception type name, while the trailing `ex` provides the stack trace.

## 8. Important note on Java overload resolution: log.error("...", ex)

Some developers write:

```java
log.error("Unexpected error: {}", ex);
```

expecting `{}` to be replaced with the exception string.

However, SLF4J has a dedicated overload:

```java
void error(String message, Throwable t);
```

Because `Throwable` is a more specific type than `Object`, calling with an exception `ex` causes Java to select the `error(String, Throwable)` overload. Thus `"Unexpected error: {}"` is kept literally as the message, while `ex` is treated as the cause.

The output can look like:

```text
Unexpected error: {}
java.lang.IllegalStateException: ...
    at ...
```

To avoid ambiguity, express your intent clearly.

**Need only a fixed message and stack trace:**

```java
log.error("Unexpected error occurred", ex);
```

**Need one context value and stack trace:**

```java
log.error(
        "Unexpected error: orderId={}",
        orderId,
        ex
);
```

**Need only the exception text, no stack trace:**

```java
log.warn(
        "Recoverable error message={}",
        ex.getMessage()
);
```

The third approach may fit a handled error where you intentionally do not need a full trace. Do not use it as a substitute for exception logging when root-cause investigation is needed.

### 8.1. A few easily confused cases

| Code | Typical behavior |
|---|---|
| `log.error("Database unavailable", ex)` | Logs message and Throwable cause |
| `log.error("Database failed: id={}", id, ex)` | Fills `id` and logs stack trace from `ex` |
| `log.error("Database failed: {}", ex)` | Selects `Throwable` overload; `{}` is not filled |
| `log.error("Database failed: {}", ex.getMessage())` | Fills message string only, no Throwable cause |
| `log.error("Database failed: id={} cause={}", id, ex)` | Last placeholder may remain unfilled because `ex` is treated as cause |
| `log.error("Database failed: id={} causeType={}", id, ex.getClass().getSimpleName(), ex)` | Two data placeholders and one Throwable cause |

Even though SLF4J supports detecting a trailing Throwable in parameterized overloads, code should **pass the cause clearly**, avoiding confusing arguments.

### 8.2. Logger.error(String, Object, Object) and varargs

SLF4J provides optimized overloads for one or two arguments and a varargs overload for more arguments. This is an API/performance detail.

For example:

```java
log.error("Order {} failed", orderId, ex);
```

is a valid call with a data placeholder and trailing throwable, even though Java selects the two-`Object` overload. The message formatter detects the trailing argument as a Throwable for the backend to process.

With a longer argument list:

```java
log.error(
        "Failed: orderId={} itemId={} warehouse={}",
        orderId,
        itemId,
        warehouseId,
        ex
);
```

the trailing Throwable rule still applies.

## 9. Choosing the right log level for exceptions

`Logger` has common levels:

- `TRACE`: very detailed information, usually for investigating low-level processing flows.
- `DEBUG`: diagnostic data intended for developers.
- `INFO`: operational milestones worth noting.
- `WARN`: abnormal situation where the application can continue or recover.
- `ERROR`: error causing an operation to fail or requiring investigative action.

A thrown exception **does not automatically mean you must log at ERROR**. Consider the impact and handling policy.

Expected input error example:

```java
if (quantity <= 0) {
    log.warn(
            "Rejected invalid order quantity: orderId={} quantity={}",
            orderId,
            quantity
    );

    throw new IllegalArgumentException(
            "Quantity must be positive"
    );
}
```

You can log WARN, or omit logging in the service and let the boundary handle it under a unified policy. Printing full stack traces for every expected validation error creates noise.

Unexpected database error example:

```java
catch (DataAccessException ex) {
    log.error(
            "Database operation failed: orderId={}",
            orderId,
            ex
    );
    throw ex;
}
```

Here logging ERROR with a trace can be helpful, though beware of duplicate logging if an upper layer logs it again.

### 9.1. Suggested guidelines table

| Scenario | Commonly considered log level | Stack trace needed? |
|---|---|---|
| Task started successfully | INFO | No |
| Internal values for debugging | DEBUG | No |
| Retrying a transient recoverable error | WARN or DEBUG | Depends on need |
| Expected invalid input under business rules | WARN/INFO or no log | Usually no full trace needed |
| Unexpected database query failure | ERROR | Usually yes |
| Optional secondary feature intentionally disabled | INFO | No |
| System error causing request failure | ERROR at handling boundary | Usually yes |

No log-level table replaces your team's operational policy. What matters is consistency, context, and actionable data.

## 10. Where to log to avoid duplicate stack traces?

An exception can travel through multiple layers:

```text
Repository throws DataAccessException
             │
             ▼
Service wraps OrderProcessingException
             │
             ▼
Controller / exception handler
             │
             ▼
HTTP 500 response
```

If every layer logs `ERROR` with a stack trace, the exact same error can appear three times.

Example prone to duplication:

```java
// Repository
catch (DataAccessException ex) {
    log.error("Repository failed", ex);
    throw ex;
}

// Service
catch (DataAccessException ex) {
    log.error("Service failed", ex);
    throw new OrderProcessingException("Cannot process", ex);
}

// Controller
catch (OrderProcessingException ex) {
    log.error("Request failed", ex);
    throw ex;
}
```

Consequences:

- Log volume rises rapidly.
- One incident can look like multiple independent failures.
- Wastes storage and search overhead.
- Harder to pinpoint where primary action is needed.

### 10.1. Principle of intentional logging or propagation

A useful practical rule:

**At an error boundary, log once with sufficient context; in lower layers, prefer adding context to the exception or propagating the cause cleanly unless there is a specific operational reason to log.**

Example where the service layer only wraps:

```java
public Receipt placeOrder(String orderId) {
    try {
        return repository.createReceipt(orderId);
    } catch (DataAccessException ex) {
        throw new OrderProcessingException(
                "Cannot create receipt for order " + orderId,
                ex
        );
    }
}
```

Boundary handling the log:

```java
log.error(
        "Order request failed: orderId={}",
        orderId,
        ex
);
```

From the trace, you still see `Caused by: DataAccessException` if the exception was wrapped with its original cause.

### 10.2. When should lower layers log too?

Logging is appropriate when:

- The exception is **handled and not propagated**; otherwise the incident signal would be lost.
- There is an independent operational event worth observing, such as a third retry being skipped.
- A layer holds important context that upper layers cannot reconstruct, and that context should not be placed in the exception.

Even then, choose an appropriate level and amount of detail. Lower layers do not always need to log a stack trace at ERROR.

## 11. Preserve the cause when wrapping exceptions

When translating an infrastructure exception into a business exception, preserve the cause.

Poor:

```java
catch (IOException ex) {
    throw new ImportFailedException(
            "Cannot read import file"
    );
}
```

The new exception has no link to the original `IOException`, stripping root-cause information from the trace.

Good:

```java
catch (IOException ex) {
    throw new ImportFailedException(
            "Cannot read import file",
            ex
    );
}
```

Custom exception:

```java
package com.example.demo.importer;

public class ImportFailedException extends RuntimeException {

    public ImportFailedException(
            String message,
            Throwable cause
    ) {
        super(message, cause);
    }
}
```

When logged:

```java
log.error("Import workflow failed: batchId={}", batchId, ex);
```

the stack trace will include `Caused by: java.io.IOException`, letting you see the original failure.

### 11.1. Do not create a new exception just to log

Inappropriate:

```java
catch (IOException ex) {
    log.error(
            "Import failed",
            new RuntimeException("Import failed")
    );
}
```

You created a new Throwable lacking `ex` as its cause, and the stack trace starts where the new exception was constructed rather than at the original I/O failure.

Correct:

```java
catch (IOException ex) {
    log.error("Import failed", ex);
}
```

Or wrap with the cause and propagate per the service API.

## 12. Exception message is not a stack trace

The following two calls are not equivalent:

```java
log.error(
        "Failed to load order: {}",
        ex.getMessage()
);
```

```java
log.error(
        "Failed to load order",
        ex
);
```

The first call only formats a string; the second passes a Throwable to the logging backend.

Typically:

- `ex.getMessage()` provides only a short description and may be `null`.
- `ex.toString()` usually includes the exception type and message.
- `ex.getStackTrace()` returns an array of frames without automatically presenting cause/suppressed chains.
- Passing `ex` as the cause to the logger lets the backend render the exception per configuration.

### 12.1. Why not use ex.toString() for every error?

Example:

```java
log.error(
        "Failed: {}",
        ex.toString()
);
```

You might see:

```text
Failed: java.io.IOException: Connection reset
```

Yet you still lack the full call path.

When diagnosing system failures, use:

```java
log.error("Failed to communicate with remote service", ex);
```

### 12.2. When is message-only logging reasonable?

When the error is expected and handled, such as a user submitting an expired coupon code:

```java
log.info(
        "Coupon rejected: couponId={} reason={}",
        couponId,
        "expired"
);
```

There is no need to throw and log a stack trace for a normal business condition.

**Message parameterization** and **stack trace logging** are two distinct techniques. You must consciously decide when to use both.

## 13. Efficient logging when levels are disabled

One advantage of `{}` is deferring formatting, but do not mistakenly assume all arguments are lazily evaluated by default.

Example:

```java
log.debug(
        "Order snapshot={}",
        buildExpensiveOrderSnapshot(order)
);
```

Java evaluates `buildExpensiveOrderSnapshot(order)` before calling `debug(...)`. If DEBUG is off, this work still happens.

### 13.1. Use isDebugEnabled when computation is expensive

```java
if (log.isDebugEnabled()) {
    log.debug(
            "Order snapshot={}",
            buildExpensiveOrderSnapshot(order)
    );
}
```

This avoids computing the snapshot when DEBUG is disabled.

There is no need to wrap every `log.debug("id={}", id)` in `isDebugEnabled()`. For simple existing variables, placeholders already meet performance goals; extra guards only clutter code unnecessarily.

### 13.2. toString can also be expensive or leak data

```java
log.debug("Order object={}", order);
```

If DEBUG is enabled, SLF4J converts `order` to text, typically via `toString()`. `toString()` might:

- Traverse a huge object graph.
- Trigger lazy-loaded relations if the implementation accesses related data.
- Contain customer data or payment details.
- Produce long, hard-to-search logs.

Therefore, even when using placeholders, prefer explicitly logging permitted, diagnostically useful fields:

```java
log.debug(
        "Order state: orderId={} status={} itemCount={}",
        order.id(),
        order.status(),
        order.itemCount()
);
```

## 14. Fluent Logging API in SLF4J 2.x

SLF4J 2.x provides a **Fluent API** via methods such as `atDebug()` and `atError()`.

Example:

```java
log.atInfo()
        .addArgument(orderId)
        .addArgument(status)
        .log("Order {} moved to status {}");
```

This is similar to:

```java
log.info(
        "Order {} moved to status {}",
        orderId,
        status
);
```

The Fluent API is useful when you need suppliers, key-value pairs, or explicitly specified causes.

**Version note:** Fluent APIs `atInfo()`, `addArgument(...)`, `addKeyValue(...)`, and `setCause(...)` belong to SLF4J 2.x. Modern Spring Boot projects typically use this SLF4J line; older Boot applications with SLF4J 1.7 do not have these APIs. Check actual dependency versions before applying.

### 14.1. Suppliers defer computation

```java
log.atDebug()
        .addArgument(() -> buildExpensiveOrderSnapshot(order))
        .log("Order snapshot={}");
```

Here the argument is supplied via a `Supplier`. When DEBUG is disabled, SLF4J can skip invoking the supplier.

Compare:

```java
// Expression is evaluated immediately by Java.
log.debug(
        "Snapshot={}",
        buildExpensiveOrderSnapshot(order)
);

// Use supplier to defer computation.
log.atDebug()
        .addArgument(() -> buildExpensiveOrderSnapshot(order))
        .log("Snapshot={}");
```

**Limitation:** suppliers must only build data for logging, without causing business side effects. If DEBUG is disabled, the supplier may never run; never place database updates or state mutations inside a supplier.

### 14.2. setCause clarifies the exception

The Fluent API allows:

```java
log.atError()
        .setCause(ex)
        .log("Cannot complete payment");
```

Or together with data arguments:

```java
log.atError()
        .addArgument(orderId)
        .addArgument(amount)
        .setCause(ex)
        .log("Payment failed: orderId={} amount={}");
```

This explicitly states that `ex` is the cause, not a value filling `{}`.

### 14.3. Key-value pairs

```java
log.atError()
        .addKeyValue("orderId", orderId)
        .addKeyValue("attempt", attempt)
        .setCause(ex)
        .log("Payment gateway call failed");
```

Key-value pairs are attached to the logging event per SLF4J 2.x capabilities. **They only render as JSON fields or text according to how the backend/layout/encoder is configured**. Do not assume every console pattern prints key-value pairs completely without checking backend configuration.

### 14.4. Do not forget log(...) at the end of the chain

Correct:

```java
log.atInfo()
        .addKeyValue("orderId", orderId)
        .log("Order created");
```

Without `.log(...)`, the event is never emitted. The fluent builder prepares the event; the terminal `log(...)` call actually requests logging.

## 15. Structured logging and message parameterization

Many log collection systems want an event with separate fields:

```json
{
  "level": "ERROR",
  "message": "Payment gateway call failed",
  "orderId": "ORD-123",
  "attempt": 2,
  "exception": "java.net.SocketTimeoutException: Read timed out"
}
```

This is a conceptual example. Actual fields, how stack traces serialize, and key names depend on the backend/encoder and Spring Boot version.

Compare two styles:

**Text with placeholders:**

```java
log.error(
        "Payment failed orderId={} attempt={}",
        orderId,
        attempt,
        ex
);
```

**Fluent key-value:**

```java
log.atError()
        .addKeyValue("orderId", orderId)
        .addKeyValue("attempt", attempt)
        .setCause(ex)
        .log("Payment failed");
```

With a suitable structured encoder, the second style allows log systems to query by field `orderId` rather than only string search.

### 15.1. Having key=value in a message does not make it JSON

```text
Payment failed orderId=ORD-123 attempt=2
```

is still a message string. A collector can parse text if a parser is configured, but that differs from the backend emitting structured attributes natively.

### 15.2. Parameterization does not automatically mask sensitive data

Whether logging with `{}` or structured fields, if you pass a password/token into the logger, that data can still be recorded.

Example **never to write**:

```java
log.info(
        "User login: username={} password={}",
        username,
        password
);
```

Do not write:

```java
log.debug("Authorization header={}", authorizationHeader);
```

Formatting techniques do not replace data classification, redaction, and access control.

## 16. Which contextual information should be logged with exceptions?

A stack trace shows which call path raised the error, yet usually **lacks sufficient business context**.

Example:

```java
log.error("Connection timed out", ex);
```

has a stack trace yet does not tell you which order the request was processing.

Better:

```java
log.error(
        "Payment request timed out: orderId={} gateway={} attempt={}",
        orderId,
        gatewayName,
        attempt,
        ex
);
```

Useful fields depending on context:

- Non-sensitive business IDs: `orderId`, `batchId`, `jobId`.
- Dependency or integration name: `paymentGateway`, `inventory-service`.
- Operation type: `reserve`, `publish`, `import`.
- Attempt number: `attempt`.
- State or phase: `validation`, `commit`.
- Stable error code: `errorCode`.
- Trace/correlation ID if the application has corresponding observability mechanisms.

### 16.1. Messages should describe the event, not repeat the exception message

Low context:

```java
log.error("Error", ex);
```

Better:

```java
log.error(
        "Failed to reserve inventory: orderId={} warehouseId={}",
        orderId,
        warehouseId,
        ex
);
```

You do not need to concatenate `ex.getMessage()` into the message. When Throwable is passed properly, the backend usually displays the exception type and message in the stack trace section.

### 16.2. Avoid logging entire payloads

Inappropriate example if the payload contains personal data:

```java
log.error(
        "Payment failed for request={}",
        paymentRequest,
        ex
);
```

`paymentRequest.toString()` may contain card details, addresses, or private data.

Better:

```java
log.error(
        "Payment failed: orderId={} methodType={} attempt={}",
        orderId,
        paymentMethodType,
        attempt,
        ex
);
```

Select fields in accordance with the system's data policy and log access permissions.

## 17. Logging in Spring Boot: levels and configuration

Spring Boot allows configuring log levels by package or class.

Example `application.yml`:

```yaml
logging:
  level:
    root: INFO
    com.example.demo: DEBUG
    org.springframework.web: WARN
```

Here:

- The root logger defaults to logging INFO and above.
- Loggers under `com.example.demo` can log DEBUG.
- Loggers under `org.springframework.web` are dialed down to WARN and ERROR.

Example `application.properties`:

```properties
logging.level.root=INFO
logging.level.com.example.demo.order=DEBUG
```

### 17.1. If DEBUG is off, where do logs go?

A statement:

```java
log.debug("Order id={}", orderId);
```

may not emit an output event if the logger's effective level does not allow DEBUG.

This does not mean `orderId` is wrong or the backend is broken. Check the effective level first.

### 17.2. Run commands can override logging levels

Example:

```bash
java -jar demo.jar --logging.level.com.example.demo.order=DEBUG
```

Command-line arguments can override config files under Spring Boot's precedence rules.

In production applications, be careful when enabling DEBUG: log volume, request details, and internal data can increase markedly.

### 17.3. Console, file, and JSON logs

Whether `logger.error(...)` goes to the console or a file depends on the backend and configuration:

- Console logging.
- File logging.
- Rolling files.
- Structured/JSON logging if configured.
- External log aggregation (container stdout, collector, observability platform).

Do not manually prepend timestamps, thread names, PIDs, or levels to individual messages if the pattern/encoder already supplies them.

## 18. MDC and correlation IDs: adding context across calls

When a request travels through controller, service, and repository, multiple logs relate to the same operation.

SLF4J provides `MDC` (Mapped Diagnostic Context) to bind key-value context to the current thread under the corresponding backend mechanism.

Example:

```java
import org.slf4j.MDC;

String requestId = "req-123";

try {
    MDC.put("requestId", requestId);

    log.info("Received request");
    orderService.process("ORD-123");
} finally {
    MDC.remove("requestId");
}
```

If the logging pattern/encoder supports displaying MDC key `requestId`, logs may look like:

```text
requestId=req-123 INFO Received request
requestId=req-123 INFO Processing order ORD-123
```

### 18.1. MDC differs from placeholders

Placeholders:

```java
log.info("Order id={}", orderId);
```

only supply arguments for that single message.

MDC:

```java
MDC.put("requestId", requestId);
```

attaches context that corresponding log events can use, depending on thread/context propagation and backend configuration.

Both can be combined.

### 18.2. MDC must be cleaned up

Thread pools reuse threads. If you `put` without `remove` or `clear`, context from a previous request can leak into a later task.

Safe example with `finally`:

```java
MDC.put("jobId", jobId);

try {
    executeJob(jobId);
} finally {
    MDC.remove("jobId");
}
```

Only call `MDC.clear()` when you genuinely own the entire context on the thread, because `clear()` can wipe keys set by other libraries.

### 18.3. Async/reactive contexts require dedicated propagation

MDC is typically tied to thread-local context. When code switches to `@Async`, another executor, or a reactive pipeline, keys do not automatically follow the execution context.

Spring Boot Micrometer/Observability can supply correlation/tracing mechanisms when appropriately configured, but do not assume every application has MDC propagation built in out of the box.

If you need request IDs across threads, select a context propagation solution compatible with the application model in use.

## 19. Logging in a Spring MVC exception handler

A web application typically has a centralized exception-handling point.

Example:

```java
package com.example.demo.web;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log =
            LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(OrderProcessingException.class)
    public ResponseEntity<ErrorResponse> handleOrderError(
            OrderProcessingException ex
    ) {
        log.error(
                "Order processing failed: errorCode={}",
                "ORDER_PROCESSING_FAILED",
                ex
        );

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ErrorResponse(
                        "ORDER_PROCESSING_FAILED",
                        "Unable to process the order"
                ));
    }

    public record ErrorResponse(
            String code,
            String message
    ) {
    }
}
```

Here:

- Server-side logs can record the full stack trace.
- Clients receive a safe error code and message.
- Internal exception messages/stack traces are not exposed directly in the HTTP response.
- This handler can serve as the single error-logging point, avoiding duplicates in services.

The example assumes `OrderProcessingException` is defined in the application with appropriate imports.

### 19.1. Do not return stack traces to clients

Avoid:

```java
return ResponseEntity.internalServerError()
        .body(ex.getStackTrace());
```

Stack traces can reveal package names, implementation details, libraries, or private data. Log traces to a protected server logging channel; HTTP responses should use an appropriate error contract.

### 19.2. Validation errors may not need an ERROR trace

Example:

```java
@ExceptionHandler(IllegalArgumentException.class)
public ResponseEntity<ErrorResponse> handleInvalidInput(
        IllegalArgumentException ex
) {
    log.warn("Request rejected: reasonCode={}", "INVALID_INPUT");

    return ResponseEntity.badRequest()
            .body(new ErrorResponse(
                    "INVALID_INPUT",
                    "Invalid request"
            ));
}
```

Not every invalid input is a system incident. Logging policy should distinguish client errors from unexpected server errors.

## 20. Logging when calling external services and retrying

When an application calls an HTTP client, database, or message broker, retries can generate multiple exceptions for the same operation.

Suppose a call is tried three times:

```text
attempt 1 -> timeout
attempt 2 -> timeout
attempt 3 -> failure
```

If each attempt logs ERROR with a full stack trace and the boundary also logs ERROR, the incident produces four stack traces.

A reasonable policy might be:

- Transient failed retry: WARN or DEBUG with order ID, attempt, error code.
- Once retries are exhausted and the operation fails: one ERROR with the final error's stack trace (or an aggregated exception preserving cause).
- If there are no retries and the error fails immediately: log at the error boundary.

### 20.1. Simple retry example

```java
public Receipt submitWithRetry(String orderId) {
    RuntimeException lastFailure = null;

    for (int attempt = 1; attempt <= 3; attempt++) {
        try {
            return gateway.submit(orderId);
        } catch (TransientGatewayException ex) {
            lastFailure = ex;

            log.warn(
                    "Transient gateway failure: orderId={} attempt={}",
                    orderId,
                    attempt
            );
        }
    }

    log.error(
            "Gateway retries exhausted: orderId={} attempts={}",
            orderId,
            3,
            lastFailure
    );

    throw new OrderProcessingException(
            "Cannot submit order " + orderId,
            lastFailure
    );
}
```

This example is intentionally simplified to illustrate log policy. In real systems, classify retryable errors, apply backoff, timeouts, idempotency, and cancellation. Do not retry every exception or loop continuously without delay.

### 20.2. Do not lose the final exception

If you only log a string:

```java
log.error("Retries exhausted: orderId={}", orderId);
```

you lose whether the timeout was `SocketTimeoutException`, `ConnectException`, or a response parsing error.

Pass `lastFailure` as the cause to preserve the trace when this is a diagnosable failure.

## 21. Security: data that must not be logged

Logs are data that may be shared broadly across operational environments. Message parameterization optimizes formatting, yet **does not protect data automatically**.

Things to avoid logging verbatim unless explicitly permitted by policy:

- Passwords, OTPs, recovery codes.
- API keys, bearer tokens, session cookies.
- Full payment card data, CVVs.
- Secrets in connection strings.
- Payload contents containing personal information.
- Authorization headers.
- Private keys or access credentials.
- Exception messages containing URLs with tokens/secret query params.

### 21.1. Unsafe example

```java
log.error(
        "Payment request failed: payload={}",
        paymentRequest,
        ex
);
```

If `paymentRequest.toString()` returns card details or personal information, logs become a leak vector.

Better:

```java
log.error(
        "Payment request failed: orderId={} paymentMethodType={}",
        orderId,
        paymentMethodType,
        ex
);
```

### 21.2. Exception messages can contain secrets

Even if you simply write:

```java
log.error("Remote request failed", ex);
```

some libraries' exception messages can include URLs or query parameters. Do not assume full stack traces are always safe to emit everywhere.

When deploying to production, consider redaction policies, backend encoders, log retention, access control, and log destinations. For error types involving sensitive data, sanitize or design exception messages from the outset so secrets are never placed inside Throwables.

### 21.3. Log injection

If user input contains newline characters:

```text
ORD-123
ERROR Admin access granted
```

writing it directly into text logs can make multi-line logs look like separate events, especially with unescaped layouts.

Example:

```java
log.warn("Rejected orderId={}", untrustedOrderId);
```

Parameterization does not automatically make output safe against log injection. Use structured logging/encoders that escape control characters, validate/sanitize untrusted fields, and never allow user input to impersonate event metadata.

## 22. Stack traces and performance

Logging a stack trace can be costly:

- Capturing or processing stack frames.
- Converting the Throwable, cause chain, and suppressed exceptions to text.
- Increasing bytes written to console/files or sent to log systems.
- Increasing I/O load and storage costs.
- Making genuinely critical events harder to find amidst repeated logs.

Therefore, do not log ERROR stack traces inside every loop or for every expected validation condition.

### 22.1. Log level decides whether an event is emitted

```java
log.debug("Detailed diagnostic", ex);
```

If DEBUG is disabled, the backend can skip the event, including formatting the stack trace for that call. However, the exception `ex` was already constructed before reaching the log line; disabling DEBUG does not mean the JVM avoids the cost of creating the Throwable.

### 22.2. Do not create exceptions frequently just to capture stack traces

Inappropriate in a hot path:

```java
log.debug("Trace current call path", new Exception("trace"));
```

Creating an exception just to obtain a call stack for debugging can be expensive, especially if executed thousands of times per second.

If you need sampling, profiling, or tracing, use the appropriate tools. Logging should not be turned into a makeshift profiler by continuously constructing Throwables.

### 22.3. Balance verbosity

A good message usually contains:

- Action name and outcome.
- A few stable context keys.
- Appropriate log level.
- Throwable when exception diagnostics are needed.
- No sensitive data outside policy.

Do not dump entire object graphs into every DEBUG log simply because placeholders accept any `Object`.

## 23. Complete example: logging success and failure in a Spring Boot service

Let's build a simple file-import service.

### 23.1. Service interface

```java
package com.example.demo.importer;

public interface ImportService {
    int importFile(String fileId);
}
```

### 23.2. Illustrative repository interface

```java
package com.example.demo.importer;

import java.io.IOException;

public interface ImportRepository {
    int importRecords(String fileId) throws IOException;
}
```

### 23.3. Business exception

```java
package com.example.demo.importer;

public class ImportFailedException extends RuntimeException {

    public ImportFailedException(
            String message,
            Throwable cause
    ) {
        super(message, cause);
    }
}
```

### 23.4. Service implementation

```java
package com.example.demo.importer;

import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class DefaultImportService implements ImportService {

    private static final Logger log =
            LoggerFactory.getLogger(DefaultImportService.class);

    private final ImportRepository repository;

    public DefaultImportService(ImportRepository repository) {
        this.repository = repository;
    }

    @Override
    public int importFile(String fileId) {
        log.info("Import started: fileId={}", fileId);

        try {
            int count = repository.importRecords(fileId);

            log.info(
                    "Import succeeded: fileId={} records={}",
                    fileId,
                    count
            );

            return count;
        } catch (IOException ex) {
            throw new ImportFailedException(
                    "Cannot import file " + fileId,
                    ex
            );
        }
    }
}
```

The service logs start and success events, yet on I/O errors wraps with the cause and propagates. It does not need to log ERROR right here if the boundary will log it.

### 23.5. Runner acting as error boundary

```java
package com.example.demo.importer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class ImportRunner implements CommandLineRunner {

    private static final Logger log =
            LoggerFactory.getLogger(ImportRunner.class);

    private final ImportService importService;

    public ImportRunner(ImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(String... args) {
        String fileId = args.length > 0
                ? args[0]
                : "demo-file";

        try {
            importService.importFile(fileId);
        } catch (ImportFailedException ex) {
            log.error(
                    "Import command failed: fileId={}",
                    fileId,
                    ex
            );

            throw ex;
        }
    }
}
```

When an error occurs:

- The service preserves the original cause.
- The runner logs the `fileId` context and full Throwable.
- The runner rethrows so process startup does not report a false success.

**Note:** because the runner rethrows, Spring Boot may also log additional failure info in startup logging. In a real CLI, decide the final logging responsibility and exit code to avoid double logging with the framework's startup failure handler. The example above illustrates passing the cause clearly, rather than asserting startup produces only a single log event.

### 23.6. Main application

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ImportApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ImportApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }
}
```

A non-web application fits when the runner is a CLI/batch job. In a runnable project, a bean implementing `ImportRepository` is needed for dependency injection to succeed.

## 24. Special notes for Java records, arrays, and object toString()

Different argument types can be formatted differently.

### 24.1. Primitives and wrappers

```java
int count = 3;
boolean active = true;

log.debug("count={} active={}", count, active);
```

Autoboxing can occur when passing primitives to overloads accepting `Object`. For one or two normal arguments, this cost is negligible compared to clarity; if a hot-path log is truly performance-critical, measure rather than guess.

### 24.2. Arrays

```java
String[] ids = {"A", "B"};

log.debug("Order ids={}", (Object) ids);
```

The SLF4J formatter supports displaying certain array types. However, if you want a fixed, searchable format without varargs ambiguity, explicitly choose:

```java
log.debug("Order ids={}", java.util.Arrays.toString(ids));
```

`Arrays.toString` computes the string before the log statement; consider `isDebugEnabled` or a supplier if the array is large and DEBUG is usually off.

Casting to `Object` in the first example expresses intent to pass **one array as a single argument** rather than confusing it with a varargs list in overloaded calls.

### 24.3. Java records

```java
public record OrderKey(String orderId, String region) {
}
```

```java
log.debug("Order key={}", orderKey);
```

Records generate a default `toString()` listing field names and values. This is convenient for debugging yet can inadvertently log private values if the record holds sensitive data. Select fields per logging policy rather than logging entire objects by default.

### 24.4. toString can throw exceptions

An unsafe custom `toString()` can throw a `RuntimeException` or access invalid state. Logging formatters usually try to handle some object-to-text conversion errors, though you should not depend on that.

Keep `toString()` simple and side-effect-free, or log specific fields instead of complex objects.

## 25. Common mistakes and fixes

| Pattern / symptom | Problem | Fix |
|---|---|---|
| `log.debug("Order " + orderId)` | Concatenates before knowing whether DEBUG is on | `log.debug("Order {}", orderId)` |
| `log.debug(String.format(...))` | Eager formatting, wrong syntax for SLF4J | Use `{}` and arguments |
| `log.info("id=%s", id)` | SLF4J does not use `%s` | `log.info("id={}", id)` |
| `log.error("Failure: {}", ex.getMessage())` | No Throwable cause, trace lost | `log.error("Failure", ex)` when trace is needed |
| `log.error("Failure: {}", ex)` | `Throwable` overload can leave `{}` literal | `log.error("Failure", ex)` |
| `log.error("Failed id={} cause={}", id, ex)` | Trailing Throwable treated as cause, missing placeholder value | `log.error("Failed id={}", id, ex)` |
| `log.error("Failed", ex.getStackTrace())` | Frame array is not a Throwable cause | `log.error("Failed", ex)` |
| `ex.printStackTrace()` | Bypasses logging backend and levels | Use `log.error("...", ex)` |
| `log.error("Failed " + ex, ex)` | Duplicate info; eager concatenation | Concise message with context and Throwable |
| `log.error("Error", ex)` at every layer | Duplicate stack traces | Pick an error boundary to log |
| `log.debug("value={}", expensive())` | `expensive()` runs even when DEBUG is off | `isDebugEnabled` or Fluent supplier |
| `log.info("payload={}", request)` | May expose sensitive data | Log permitted fields intentionally |
| `log.error("...", ex)` yet no trace seen | Level, appender/encoder, or collection may hide/truncate trace | Check backend configuration and output |
| Expecting `addKeyValue` to auto-produce JSON | Layout does not support structured fields | Configure an appropriate structured encoder |

### 25.1. Seeing the message without the stack trace?

Follow these steps in order:

1. Check that an actual `Throwable` was passed, not just `getMessage()`.
2. Check that the Throwable is last in the parameter list or uses the `(String, Throwable)` overload.
3. Check the log level: is ERROR allowed to emit?
4. Check whether the backend pattern/encoder outputs exceptions.
5. Check whether the collector/UI groups multi-line events, truncates, or hides stack traces.
6. Check whether the exception was wrapped with its cause properly.
7. Check whether logs were converted into structured events where the UI displays the exception in a separate field.

### 25.2. Seeing too many identical stack traces?

Check:

1. Are repository, service, controller, and handler all logging the same exception?
2. Are retries logging full traces on every attempt?
3. Are multiple replicas hitting the same failure?
4. Is Spring Boot's startup failure handler adding a log after a runner throws?
5. Is the collector ingesting duplicates?

A good message does not replace an application-wide logging strategy.

## 26. Practice comparing SLF4J overloads

Suppose:

```java
String orderId = "ORD-123";
RuntimeException ex =
        new IllegalStateException("Connection unavailable");
```

Try each call:

### Case A — Message and exception only

```java
log.error("Order failed", ex);
```

Goal: fixed message + full Throwable.

### Case B — One context field and exception

```java
log.error(
        "Order failed: orderId={}",
        orderId,
        ex
);
```

Goal: fill one placeholder, keep stack trace.

### Case C — Exception message only

```java
log.error(
        "Order failed: reason={}",
        ex.getMessage()
);
```

Goal: log only the reason string. **No cause** is passed to the logger.

### Case D — Ambiguous overload trap

```java
log.error("Order failed: {}", ex);
```

The author might expect to print `ex` into the placeholder, yet Java can pick the `Throwable`-accepting overload. Result differs from intent.

### Case E — Fluent API with cause

```java
log.atError()
        .addArgument(orderId)
        .setCause(ex)
        .log("Order failed: orderId={}");
```

Goal: express data arguments and cause explicitly.

### Case F — Exception type alongside stack trace

```java
log.error(
        "Order failed: orderId={} exceptionType={}",
        orderId,
        ex.getClass().getSimpleName(),
        ex
);
```

Goal: message has 2 values and trailing exception solely outputs the trace.

When learning logging, explain whether each argument serves as a **placeholder value** or the **Throwable cause**. Simply distinguishing those two roles prevents most missing-stack-trace bugs.

## 27. Workflow for designing useful log messages

When adding a log statement, ask:

### Step 1 — What event needs to be recorded?

Example:

```text
Payment request failed
```

Better than a vague message like `Error happened`.

### Step 2 — Which fields aid diagnostics?

Example:

```text
orderId, gatewayName, attempt
```

Do not log unnecessary fields or sensitive data.

### Step 3 — Choose the log level

- INFO for operational milestones.
- DEBUG for technical details.
- WARN for recoverable anomalies.
- ERROR for incidents needing investigation.

### Step 4 — Use {} placeholders

```java
log.warn(
        "Gateway retry: orderId={} attempt={}",
        orderId,
        attempt
);
```

### Step 5 — Is there an exception needing a stack trace?

If yes:

```java
log.error(
        "Gateway failed: orderId={} attempt={}",
        orderId,
        attempt,
        ex
);
```

Place `Throwable` last.

### Step 6 — Was this same error already logged at another layer?

Select a boundary responsible for logging. If a lower layer simply propagates, it may not need to log ERROR there.

### Step 7 — Are there costs or sensitive data?

Check `toString()`, object graphs, payloads, tokens, and expensive calculations done solely for logging.

### Step 8 — Can the log be searched later?

Use stable messages and consistent field names. With log analytics systems, prefer structured logging per an appropriate backend.

## 28. Hands-on exercises

### Exercise 1 — Replace concatenation with placeholders

Write a `CommandLineRunner` logging `orderId` and `status` using concatenation. Switch to `{}`, then set the logger level to INFO to observe DEBUG being suppressed.

### Exercise 2 — Distinguish %s and {}

Try:

```java
log.info("User %s logged in", username);
```

and:

```java
log.info("User {} logged in", username);
```

Compare outputs and explain SLF4J's syntax.

### Exercise 3 — Log Throwable properly

Create an `IllegalStateException`, compare:

```java
log.error("Failure: {}", ex.getMessage());
log.error("Failure", ex);
```

Observe the difference between message-only and stack trace.

### Exercise 4 — Combine two placeholders and an exception

Create variables `orderId`, `attempt`, and an `IOException`. Write `log.error` so both context fields appear in the message and the exception is logged with its stack trace.

### Exercise 5 — Test confusing overload resolution

Try:

```java
log.error("Failed: {}", ex);
```

Then change it to a fixed message or add a data field before the Throwable. Explain why Java overload resolution affects the output.

### Exercise 6 — Preserve cause when wrapping

Create an `IOException`, wrap it in `ImportFailedException` via a constructor accepting `Throwable cause`, then log the wrapper at the boundary. Verify `Caused by` appears in the trace.

### Exercise 7 — Avoid duplicate logging

Build a repository → service → controller flow. Have each layer log the same exception, observe the number of stack traces, then refactor to log at the error boundary.

### Exercise 8 — Expensive argument evaluation

Create an `expensive()` method that increments a counter each time it is called. Disable DEBUG and try:

```java
log.debug("Data={}", expensive());
```

Then try an `isDebugEnabled()` guard and a Fluent supplier. Compare how many times the method executes.

### Exercise 9 — Fluent cause

In a project using SLF4J 2.x, log an error with `log.atError().setCause(ex).log(...)`. Add `addKeyValue("orderId", orderId)` and inspect output under the active backend.

### Exercise 10 — MDC correlation

Put `requestId` into MDC inside `try` and remove it in `finally`. Configure an appropriate log pattern and observe the same ID appearing across multiple log statements.

### Exercise 11 — Protect sensitive data

Simulate a payment request containing a token. Write two log versions: an unsafe one logging the entire request and a safe one logging only order ID, method type, and error code. Explain why the second version is safer.

### Exercise 12 — Spring MVC exception handler

Create a `@RestControllerAdvice` handling system exceptions. Log the trace on the server, return an error code and safe message to the client. Confirm no stack trace is returned directly over HTTP.

### Exercise 13 — Categorize retry logs

Simulate three gateway calls where the first two fail transiently and the last fails. Design WARN logs for retries and ERROR with a stack trace when retries are exhausted. Explain why full traces should not be printed on every attempt.

### Exercise 14 — Diagnose missing stack traces

Write code passing `ex.getMessage()` and observe missing traces. Fix it to pass a trailing `Throwable` and verify output. If the trace still does not appear, inspect appender/encoder configuration instead of only modifying Java code.

## 29. Official reference documentation

- [SLF4J User Manual](https://www.slf4j.org/manual.html): `{}` placeholders, parameterized logging, and Fluent Logging API.
- [SLF4J FAQ — Parameterized Logging](https://www.slf4j.org/faq.html): `{}` syntax, performance, and argument handling.
- [SLF4J Logger API](https://www.slf4j.org/apidocs/org/slf4j/Logger.html): overloads such as `error(String, Throwable)`, `error(String, Object...)`, and log levels.
- [SLF4J LoggingEventBuilder API](https://www.slf4j.org/apidocs/org/slf4j/spi/LoggingEventBuilder.html): `addArgument`, `addKeyValue`, `setCause`, and `log`.
- [Spring Boot Reference — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): configuring log levels, logging systems, and output in Spring Boot.
- [Spring Boot Reference — Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html#features.logging.structured): structured logging capabilities by Spring Boot version.
- [Logback Manual](https://logback.qos.ch/manual/index.html): backend, appenders, layouts, and exception rendering.

**The most important practical principle:** use `logger.info("Order id={}", orderId)` instead of string concatenation to format via SLF4J's mechanism; and when you need to record a stack trace, pass the **exception object** to the logger like `logger.error("Order failed: id={}", orderId, ex)`, with `ex` at the end. Do not confuse `getMessage()` with a full stack trace, avoid creating multiple copies of the same error across layers, and always pick safe contextual information so logs have diagnostic value without leaking sensitive data.
