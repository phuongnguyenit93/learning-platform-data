# Cause Chain in Java Exception Logging

## 1. What is a cause chain?

In Java, a **cause chain** (exception cause chain) is the link from an exception at the current processing layer to the exception that caused it, and continuing to deeper causes if any exist. Java provides this mechanism through **Throwable.getCause()** and constructors that accept a **Throwable cause** argument.

When an application layer catches an exception from a lower layer and needs to express the error in a higher-level context, it can **wrap the original exception** inside a new exception:

~~~text
OrderProcessingException: Unable to process order
    caused by QuantityFormatException: Invalid quantity
        caused by NumberFormatException: Unable to parse integer
~~~

These three exceptions form **one cause chain**, not three independent incidents. The outermost exception explains the business impact; the inner exception indicates the component and operation that failed; the exception at the end of the chain is usually closest to the technical root cause.

A cause chain is especially useful when reading error logs: if you only see "Unable to process order", you do not know whether the failure came from input data, the inventory service, or the database. If the log preserves and displays the cause chain, operators can trace from the **high-level symptom** down to the **low-level cause**.

**Goal of this article:** understand how to create, preserve, read, and log cause chains properly in Java 17+, while avoiding information loss, duplicate logging, and sensitive data leaks.

## 2. Where does the cause chain live in the Throwable hierarchy?

In Java, **Throwable** is the base class of two common branches:

- **Exception**: describes exceptional conditions that an application may need to handle; includes checked exceptions and **RuntimeException**.
- **Error**: typically indicates a serious environment/JVM issue; normal applications do not try to handle every Error by recovering from it.

Each Throwable object can hold the following information:

| Information | API | Meaning |
| --- | --- | --- |
| Message | getMessage() | Error description of the current exception |
| Cause chain | getCause() | The exception that caused the current exception; may be null |
| Exception type name | getClass().getName() | Specific exception type for investigation |
| Stack trace | getStackTrace(), printStackTrace() | Code locations related to where the exception was created or its stack was updated |
| Suppressed exceptions | getSuppressed() | Suppressed errors, commonly raised when closing resources |
| General description | toString() | Usually the class name plus the message, if present |

A **cause chain** consists of single links **Throwable → cause → next cause**. When **getCause() == null**, the chain ends. An exception does not necessarily have a cause; for example, an exception thrown directly during data validation without catching any prior exception.

**Do not confuse cause with stack trace:**

- Cause tells you **which error caused which error**.
- Stack trace tells you **the method call path / creation point of each Throwable**.
- A stack trace can be very long without having any cause.
- A cause chain can contain multiple Throwables, and **each Throwable has its own stack trace**.

When using **printStackTrace()**, Java can display both the stack trace of the outermost exception and **Caused by:** blocks for the inner causes; line numbers and details depend on the execution path.

## 3. Why wrap an exception instead of only passing the message?

Suppose the data persistence layer cannot parse a numeric value. The business layer wants to report the failure in language appropriate for orders.

**Wrong approach: losing the original cause**

~~~java
try {
    saveOrderData();
} catch (NumberFormatException e) {
    throw new OrderProcessingException("Cannot save order");
}
~~~

The snippet above assumes the methods/classes already exist and is a **snippet**, not a standalone program. Because the new constructor does not accept **e**, **getCause()** of the thrown exception may be null, and when reading logs, an investigator no longer has a direct link to the original NumberFormatException.

**Right approach: keep the original Throwable as the cause**

~~~java
try {
    saveOrderData();
} catch (NumberFormatException e) {
    throw new OrderProcessingException("Cannot save order", e);
}
~~~

In the OrderProcessingException class, you need a constructor that passes the cause to the superclass:

~~~java
public class OrderProcessingException extends RuntimeException {
    public OrderProcessingException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

The example above illustrates **how to declare an exception class**, which can be saved as OrderProcessingException.java if you want to use it standalone with appropriate calling code. The **super(message, cause)** constructor preserves both the business-layer message and the caught exception.

For checked exceptions, a similar mechanism can be used:

~~~java
public class OrderStorageException extends Exception {
    public OrderStorageException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

When a method throws a checked exception, it must declare **throws** or handle it according to Java rules. Wrapping an error does not automatically convert a checked exception into an unchecked one; the new exception class type determines the compile-time contract.

**Note:** there are cases where you only need **throw e;** to preserve the original exception and stack trace, if the current layer does not need to translate the error type. Do not catch and wrap exceptions in every method just to create extra layers with no new information.

## 4. Mechanisms for creating and linking a cause chain

There are three common ways:

### A. Constructor accepting a cause

~~~java
throw new IllegalStateException("Order processing failed", original);
~~~

This constructor is the common choice when you want to **change the error context** while preserving the original Throwable.

### B. Custom class constructor accepting message and cause

~~~java
final class ServiceException extends RuntimeException {
    ServiceException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

This pattern is used when the business layer wants a stable exception type to distinguish it from library exceptions.

### C. initCause() for legacy exception types

~~~java
Exception legacy = new Exception("Legacy operation failed");
legacy.initCause(original);
throw legacy;
~~~

**initCause(Throwable)** is only used when the cause **has not been initialized yet**. Calling it again on the same Throwable after the cause has been set may throw **IllegalStateException**. Java also does not allow a Throwable to be set as its own cause via **initCause()**. For standard constructors that already initialize the cause—including constructors that accept a cause even if null—do not call initCause again.

In modern code, prefer **constructor(message, cause)** when available. **initCause()** is mainly for legacy exception classes that lack an appropriate constructor.

### What should each layer add?

A readable chain usually corresponds to **real responsibility boundaries**:

~~~text
Controller / API
  OrderProcessingException: order validation failed
      |
      +-- Domain / validation layer
            QuantityFormatException: quantity must be an integer
                |
                +-- Java parser
                      NumberFormatException: invalid decimal input
~~~

The Controller layer does not have to wrap the exception in yet another exception if an appropriate OrderProcessingException type already exists and only needs to be converted into an HTTP response. If every layer creates a wrapper carrying the same "operation failed" message, the cause chain becomes longer without adding value.

## 5. Reading a cause chain with getCause()

The simplest traversal starts from the outermost Throwable and repeatedly calls **getCause()**:

~~~java
Throwable current = error;
while (current != null) {
    System.out.println(current.getClass().getSimpleName());
    current = current.getCause();
}
~~~

This is a **snippet** assuming an existing **error** variable. It is suitable for explaining the mechanism, but production code should guard against abnormal chains.

### What does "Root cause" mean?

Typically, **root cause** is understood as the last Throwable reachable via **getCause()**; it is the deepest position in the cause chain, for example NumberFormatException. However, the deepest exception **is not always the business cause that needs fixing**. A timeout error in an HTTP library may be a symptom of an overloaded downstream service; finding the operational root cause also requires other logs, metrics, and tracing.

Java SE does not provide a universal business rule for picking the most important exception. The **getRootCause()** helper name in some libraries does not mean it is a built-in method on **java.lang.Throwable**. In plain Java, you can traverse getCause() yourself.

### Avoiding cycles and excessive depth

You should not assume every chain is short, especially when receiving Throwables from libraries or custom code. **initCause()** prevents a Throwable from setting itself as its own cause, but an abnormal reference cycle can still exist across multiple Throwables, so a general-purpose analysis utility should limit depth or detect repeated elements.

Example of a safe traversal helper using object identity instead of **equals()**:

~~~java
static Throwable deepestCause(Throwable error) {
    java.util.Set<Throwable> seen =
            java.util.Collections.newSetFromMap(
                    new java.util.IdentityHashMap<>());

    Throwable current = error;
    Throwable deepest = null;
    int depth = 0;

    while (current != null && depth < 64 && seen.add(current)) {
        deepest = current;
        current = current.getCause();
        depth++;
    }
    return deepest;
}
~~~

This is a **static method snippet** that can be placed inside a Java class. It uses an **object identity** set and a 64-step limit to avoid hanging on abnormal data; if a chain has more than 64 levels, the result is only the deepest cause **traversed**, not necessarily the end of the chain.

In many applications, you do not need to write traversal yourself because the logging framework already displays the cause chain when given the full **Throwable**.

## 6. Logging cause chains properly with JUL

With **java.util.logging.Logger**, the API to use when logging an error with a cause is:

~~~java
logger.log(Level.SEVERE,
        "event=order.persist.failed requestId=" + requestId
                + " errorCode=STORAGE_ERROR",
        exception);
~~~

This is a **snippet** assuming **logger**, **requestId**, and **exception** variables along with the necessary imports. The third argument is **Throwable**, which is attached to the **LogRecord** via **getThrown()**. If an appropriate Formatter (such as **SimpleFormatter**) is used, the exception's stack trace and **Caused by** sections can be included in the output.

**Do not replace it with:**

~~~java
logger.severe("Order failed: " + exception.getMessage());
~~~

This approach only prints the message string. It usually **loses the exception type, stack trace, and cause chain** in the log record. If exception.getMessage() is null, the content is even less useful.

Also avoid:

~~~java
logger.severe("Order failed: " + exception);
~~~

Although this usually includes the class name and message from **toString()**, it is still just a **string** and does not attach the Throwable to the LogRecord. To allow the formatter to process the cause chain, pass the **Throwable** using the proper overload.

### At which layer should you log?

A useful rule of thumb:

- **Low layer:** throw an exception with context or wrap the cause; avoid logging the stack trace multiple times and rethrowing.
- **Business layer:** translate technical errors into errors meaningful to the business contract if needed; preserve the cause.
- **Processing boundary (HTTP/job/message consumer):** write **one primary error log** with requestId/jobId, operation code, error code, and the full Throwable, where the final impact is known.
- **When an error is handled:** you can log INFO/WARNING as appropriate to reflect a retry, fallback, or rejection decision; not every caught exception is SEVERE.

If the repository layer logs ERROR with a stack trace and rethrows, the service layer logs ERROR again, and the Controller logs ERROR once more, a single error can generate **three log records** that are easily counted as three incidents. Establish clear logging responsibilities; only log at additional layers when there is new information or a genuine investigation need.

### Exception log levels

**Level.SEVERE** is typically appropriate when an unrecoverable error causes a request or critical feature to fail. **Level.WARNING** can fit degraded states or retries; **Level.INFO** can fit an intentional business decision to reject input. Choose the level based on **impact and recoverability**, not on whether a Throwable is present or how many layers are in the chain.

## 7. Standalone compilable and runnable Java 17+ example

The following program simulates three error layers:

1. **Integer.parseInt("abc")** throws NumberFormatException.
2. **parseQuantity()** wraps it into QuantityFormatException to represent a business format error.
3. **processOrder()** wraps it further into OrderProcessingException to express that order processing failed.
4. **main()** logs only at the final boundary, passing the Throwable to **Logger.log(Level, String, Throwable)**.

To make stdout easy to verify, the program uses an illustrative Formatter that prints **the type name, message, and cause order**. This Formatter **does not print stack traces**; in a real system, use a formatter/encoder that supports Throwable and stack traces appropriately.

Save as **CauseChainDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class CauseChainDemo {
    private static final Logger LOG =
            Logger.getLogger("examples.logging.cause");

    static class QuantityFormatException extends RuntimeException {
        QuantityFormatException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static class OrderProcessingException extends RuntimeException {
        OrderProcessingException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                StringBuilder text = new StringBuilder();
                text.append(record.getLevel().getName())
                        .append(" | ")
                        .append(formatMessage(record))
                        .append('\n');

                Throwable current = record.getThrown();
                int depth = 0;
                while (current != null && depth < 10) {
                    text.append("cause[").append(depth).append("] ")
                            .append(current.getClass().getSimpleName())
                            .append(": ")
                            .append(current.getMessage())
                            .append('\n');
                    current = current.getCause();
                    depth++;
                }
                return text.toString();
            }
        }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };

        output.setLevel(Level.ALL);
        LOG.addHandler(output);
        try {
            processOrder("ORD-17", "abc");
        } catch (OrderProcessingException e) {
            LOG.log(Level.SEVERE,
                    "event=order.failed orderId=ORD-17", e);
        } finally {
            LOG.removeHandler(output);
            output.flush();
        }
    }

    private static void processOrder(
            String orderId, String quantityText) {
        try {
            int quantity = parseQuantity(quantityText);
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
        } catch (QuantityFormatException e) {
            throw new OrderProcessingException(
                    "order validation failed", e);
        }
    }

    private static int parseQuantity(String text) {
        try {
            return Integer.parseInt(text);
        } catch (NumberFormatException e) {
            throw new QuantityFormatException(
                    "quantity must be an integer", e);
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac CauseChainDemo.java
java CauseChainDemo
~~~

**Expected stdout of the example** on a standard JDK 17:

~~~text
SEVERE | event=order.failed orderId=ORD-17
cause[0] OrderProcessingException: order validation failed
cause[1] QuantityFormatException: quantity must be an integer
cause[2] NumberFormatException: For input string: "abc"
~~~

**Detailed explanation:**

- **Integer.parseInt("abc")** cannot parse an integer, so it throws NumberFormatException.
- **parseQuantity()** catches the exception and creates **QuantityFormatException("quantity must be an integer", e)**, giving the format error clear context while preserving NumberFormatException.
- **processOrder()** wraps it further into **OrderProcessingException("order validation failed", e)**; this is the error type that main understands and catches.
- **LOG.log(Level.SEVERE, ..., e)** attaches the OrderProcessingException to the LogRecord. The Formatter retrieves the exception via **record.getThrown()**, then traverses **getCause()**.
- **cause[0]** in the example is the **outermost exception being logged**, **cause[1]** is its direct cause, and **cause[2]** is the deeper cause. This is a **numbering convention of the illustrative Formatter**, not JUL's standard output syntax.
- **LOG.setUseParentHandlers(false)** prevents the parent Logger's default Handler from also writing logs to stderr. **StreamHandler(System.out, ...)** is used to produce clean output on stdout.
- Overriding **publish()** and calling **flush()** ensures StreamHandler outputs each event immediately rather than relying on buffer flushing; the program avoids closing a Handler attached to System.out.
- The default message of **NumberFormatException** when parsing "abc" on common JDKs is **For input string: "abc"**; this is an internal number-parsing detail, and business logic should not depend on the exact library message text.

In production, you normally let SimpleFormatter or an appropriate logging backend output the full stack trace. The program above intentionally prints a **compact, deterministic** cause chain so you can directly see the link across the three layers.

### If you want to see the full stack trace

With the same Throwable **e**, one way to inspect it in learning code is:

~~~java
e.printStackTrace();
~~~

This is a snippet placed inside a catch block that has variable **e**, not a standalone program. **printStackTrace()** typically writes to **System.err** and includes the Throwable's stack trace along with any **Caused by** sections. In production applications, prefer passing the Throwable to a logger rather than calling printStackTrace() directly, because the logging system may need to configure levels, formatting, shipping to a collector, and correlating requestId.

## 8. Cause chain vs. stack trace: differences during investigation

Consider an abbreviated representation:

~~~text
OrderProcessingException: order validation failed
    at OrderService.processOrder(...)
Caused by: QuantityFormatException: quantity must be an integer
    at QuantityParser.parse(...)
Caused by: NumberFormatException: For input string: "abc"
    at java.lang.Integer.parseInt(...)
~~~

This is an **illustrative example**, not verbatim stack trace output from a specific run. Java may print many more frames and abbreviated lines such as **... N more** to avoid repeating stack frames.

When reading a stack trace that has causes:

1. Find the **outermost exception** to see which operation failed and at which layer.
2. Follow the **Caused by** sections to determine which exceptions were wrapped and where.
3. Look at the first frames belonging to **your application code** near the error source to identify the code to inspect.
4. Combine **requestId**, timestamp, permitted logged data, and related logs to understand the situation.
5. Verify your conclusion: the last exception in the chain is the closest technical symptom, but the systemic cause may lie in configuration, dependencies, data, or earlier steps.

**Do not just jump to the last "Caused by" and ignore the upper layers.** For example, NumberFormatException tells you that data could not be parsed as a number, but the business layer tells you that the field was used to validate order quantity. Both are needed to distinguish a client error from an application bug that generated bad data.

## 9. How does a cause differ from a suppressed exception?

In Java, a **suppressed exception** is not part of the getCause() chain. It is stored in a separate list, retrieved via **Throwable.getSuppressed()**.

The classic case is **try-with-resources**:

~~~java
try (java.io.BufferedReader reader =
        new java.io.BufferedReader(
                new java.io.StringReader("sample"))) {
    // Read data; an error may occur in the try body.
}
~~~

The snippet above only illustrates try-with-resources syntax; BufferedReader wrapping StringReader does not normally throw an error on close. In a case where a resource fails in **close()** while the try body has already thrown an exception, Java can retain the error from close() as a **suppressed** exception attached to the primary exception, instead of replacing the primary exception.

The structure can look like this:

~~~text
PrimaryException
  |
  +-- getCause()           -> RootCause (if any)
  |
  +-- getSuppressed()[0]   -> CloseFailureA
  +-- getSuppressed()[1]   -> CloseFailureB
~~~

Therefore:

- **getCause()**: follows the *cause chain*.
- **getSuppressed()**: retrieves Throwables retained as *suppressed errors*; there can be multiple elements.
- Java's **printStackTrace()** can display both **Caused by** and **Suppressed**, with distinct indentation structures.
- An analyzer that only traverses **getCause()** will **not see suppressed exceptions**. When resource-closing errors matter, use a formatter or logging tool capable of outputting the full Throwable.

Do not manually turn every suppressed exception into a new cause: doing so can distort the semantics of the primary error and lose other suppressed errors.

## 10. Cause chains across multiple layers and multiple services

### Within the same JVM

A cause chain works when layers pass Throwable objects directly through method calls or when an upper layer wraps a lower layer's exception. For example:

~~~text
Repository/Parser  -> NumberFormatException
Domain/Service     -> QuantityFormatException(cause=NumberFormatException)
Application        -> OrderProcessingException(cause=QuantityFormatException)
HTTP boundary      -> log Throwable, convert to appropriate response
~~~

This is an illustrative path. Not every error needs all four layers, and not every API should return internal details to clients.

### Across HTTP/message queues or process boundaries

Java Throwable objects **do not automatically cross** REST/JSON, message brokers, or other languages as a continuous cause chain. Typically, the receiving service gets an **HTTP status, errorCode, response message, and correlation ID**, and then creates a local exception—such as **RemoteServiceException**—describing the impact on the current service.

If you need to trace an error's origin across services:

- Use a consistent **correlationId/traceId** across the services involved.
- Log the Throwable at the **originating service** with permitted data.
- Propagate appropriate error codes and protocol information, avoiding leaking stack traces or sensitive messages externally.
- Combine **tracing** and per-service logs to determine the system-level cause chain.

Do not assume an exception in service A will appear intact via **getCause()** in service B's JVM if the protocol does not support transmitting such information.

## 11. When to wrap, rethrow, handle, or log?

| Situation | Appropriate choice | Reason |
| --- | --- | --- |
| Exception already has the right type and semantics for the current layer | throw e; if the contract allows | Avoids creating redundant cause layers |
| Want to translate a library error into a meaningful business error | new DomainException(message, e) | Preserves the original cause and adds context |
| Error is completely handled by a fallback | Handle it and record an appropriate event if needed | Avoids making a recovered request look failed |
| Error must propagate to the HTTP/job boundary | Wrap if needed, then rethrow | One final place logs it with overall context |
| Final boundary confirms the operation failed | logger.log(level, context, e) | Includes message, error code, stack trace, and cause |
| Error is defined as a valid outcome, e.g., invalid input | Return result/exception per contract; log INFO if useful | Not every rejection is a SEVERE incident |

**Assign clear responsibilities:** lower layers create and preserve the cause; boundary layers know the final outcome and can log it. If a service catches and logs SEVERE but the controller still retries and succeeds, the initial SEVERE log line can trigger false alerts.

In asynchronous processing, an exception may be wrapped by **ExecutionException** (when retrieving a Future result) or **CompletionException** (in some CompletableFuture completion paths), depending on the API and call site. When investigating, follow **getCause()** to inspect the task error, while keeping the wrapper if it carries useful information about how the error was propagated through the async mechanism.

## 12. Adding context to error logs without losing the cause

A cause chain tells you **which exception led to which exception**; it is usually not enough to know which specific request or order was affected. A good error log record should include:

- A stable **event**: for example, order.persist.failed.
- **requestId/jobId** to correlate logs along the same processing flow.
- Searchable **operation** and **errorCode**.
- **service/component** emitting the log; optionally the name of the dependency involved.
- **Full Throwable** passed to the logging API, not truncated to getMessage().
- **outcome** or final task status if needed to distinguish from a recovered retry.

Illustrative JSON example, **not JUL's default format**:

~~~json
{
  "level": "SEVERE",
  "event": "order.persist.failed",
  "service": "order-service",
  "requestId": "req-42",
  "orderId": "ORD-17",
  "errorCode": "INVALID_QUANTITY",
  "exceptionType": "OrderProcessingException",
  "causeTypes": [
    "QuantityFormatException",
    "NumberFormatException"
  ]
}
~~~

A real-world formatter can add the stack trace or a Throwable description field, while balancing cost and sensitive data. The example above only illustrates separating **searchable fields** from **exception details**.

**Security:** library exception messages may contain file paths, SQL, endpoints, tokens, snippets of input data, or personal information. Do not log every raw message to inappropriate channels. Control read permissions, retention, redaction, and encoders. Do not return internal cause chains and stack traces to clients outside trusted environments.

## 13. Costs and limits of logging the full cause chain

Logging long stack traces is helpful when investigating errors, but the cost can be significant:

- **Volume:** multiple wrappers and long stack traces turn a single event into tens or hundreds of lines.
- **Performance:** generating and formatting stack traces incurs CPU, memory, and I/O costs; logging inside a retry loop can make matters worse.
- **Incident counting:** logging the same error at multiple layers inflates event counts inaccurately.
- **Searchability:** if a formatter turns a stack trace into a multiline string that the collector does not merge properly, the log system may split one exception into multiple records.
- **Privacy:** cause messages may carry data that should not be stored long-term.

Therefore, log full stack traces at the **appropriate location and log level**, keep context/tracing consistent, avoid repeating the same Throwable across retries, and configure a pipeline that supports multiline or structured exception fields. Do not strip causes just to save space: choose a logging policy suited to each destination and use metrics/aggregation to observe high-frequency events.

## 14. Common mistakes with Cause chains

| Mistake | Consequence | Fix |
| --- | --- | --- |
| throw new DomainException(e.getMessage()) | Loses original Throwable | Use a constructor that accepts cause |
| logger.severe(e.getMessage()) | Loses error type, stack trace, cause | Use logger.log(Level, message, e) |
| Wrapping at every layer without adding context | Long, hard-to-read chain | Only wrap when changing semantics/responsibility |
| Logging stack traces in repository, service, and controller | One incident becomes multiple log records | Choose one primary error-logging point |
| Looking only at the outermost exception | Misses the lower-level source of error | Check getCause()/Caused by |
| Looking only at the deepest cause | Loses business meaning and handling path | Read both the outer exception and intermediate layers |
| Confusing suppressed with cause | Misses resource-closing errors | Check getSuppressed() when needed |
| Traversing cause without a limit | Can hang on abnormal chains | Limit depth or track identity |
| Logging error messages containing raw user data | Secret leaks, log injection | Minimize data and escape/redact appropriately |
| Returning raw stack traces to API clients | Exposes internal structure | Convert to safe error codes and messages |
| Assuming cause propagates automatically over HTTP | Cannot connect errors across services | Use traceId/correlationId and per-service logs |
| Treating the technical root cause as the final operational cause | Diagnosis lacks context | Combine metrics, tracing, configuration, and valid data |

## 15. Checklist for logging exceptions with multiple causes

1. Identify **where the original exception is caught** and whether this layer truly needs to wrap it.
2. If wrapping, use **super(message, cause)** or a standard constructor that accepts cause; do not discard the caught Throwable.
3. Keep each layer's message short and clear about the **new context**, avoiding repeating the exact exception message at every layer.
4. At the final boundary, log with **Logger.log(Level, message, Throwable)** or the equivalent API of your actual framework.
5. Verify that your formatter/collector outputs **stack traces and Caused by sections** when needed; understand how it represents **suppressed** exceptions.
6. Add safe **event, requestId/jobId, operation, and errorCode** fields; do not put secrets or full payloads into logs.
7. Log errors only at points with a clear purpose; do not duplicate stack traces across layers.
8. Distinguish **technical errors**, **valid rejection outcomes**, and **recovered retries** when choosing INFO/WARNING/SEVERE.
9. For concurrent or multi-service processing, propagate correlation context and use linked tracing/logs; do not rely solely on line order.
10. Test a case that actually throws an exception, read the resulting log, and verify that it shows **the outermost exception, each cause, the failing step, and the business impact**.

**Conclusion:** A cause chain preserves the **"which exception caused which exception"** relationship as an error travels through Java layers. Preserving the cause with a Throwable-accepting constructor and logging **with the Throwable** enables investigation from business impact down to the technical fault without losing context.
