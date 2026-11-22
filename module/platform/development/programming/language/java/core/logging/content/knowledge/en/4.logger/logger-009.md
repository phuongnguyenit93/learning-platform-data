# Reusing Loggers in Java

## 1. Why Should Loggers Be Reused?

When a Java class handles many consecutive or concurrent requests, it often needs to log recurring events for the same kind of work: starting order processing, updating status, detecting invalid input, calling external services, or handling exceptions.

**Reusing a logger** means a class or component reuses an already defined and properly configured logging object, instead of creating a new logger, attaching handlers/appenders, or reconfiguring the logging pipeline on every method call. In idiomatic Java, each class holds a logger in a `private static final` field:

```java
private static final Logger LOG =
        Logger.getLogger(OrderService.class.getName());
```

This snippet is a **class-level declaration pattern**, not a standalone program. It uses `java.util.logging.Logger` (JUL) built into the JDK.

To understand this properly, separate three things:

- **The logger object**: the entry point where Java code calls `info`, `warning`, `log`, etc. It typically has a name and filtering rules.
- **Handlers/appenders and configuration**: the components that decide whether events go to the console, a file, or another destination, and with what log level and format. This configuration is usually set at the application scope.
- **Per-execution data**: request ID, order ID, actor, outcome, error, etc. These values **change with every event**; they must not be turned into shared state that another thread could overwrite.

Reusing a logger provides stable log source names, consistent configuration, and concise code. It does not mean every class in the application must share a single logger with the same name, nor does it mean every request must share the same metadata.

## 2. Model: Many Instances, One Logger per Class

A Java application can create many `OrderService` instances. If the logger is a `static final` field of the class, those instances all access the same logger:

```text
new OrderService() ──┐
                     ├──> OrderService.LOG ──> Handler / Appender ──> Log destination
new OrderService() ──┤
                     │
new OrderService() ──┘

new PaymentService() ───> PaymentService.LOG ──> Handler / Appender ──> Log destination
```

The logger object **can be shared** while each log call still produces an independent event with its own message and context. Loggers from different classes can share the underlying handler/appender system according to configuration; each class does not need to open its own file or connection.

Three characteristics to note:

1. `static`: there is a single logger field for the **class** rather than a separate field initialized for each instance.
2. `final`: the field cannot be reassigned to point to a different logger after initialization. This does **not** make the `Logger` object itself immutable; its log level, handlers, and filters can still be changed via API or configuration.
3. `private`: external code cannot directly modify the class's logger; the class only uses it to emit events. The name `LOG` or `LOGGER` is a convention and has no effect on logging behavior.

In the `Logger.getLogger(OrderService.class.getName())` pattern, the logger name is usually the fully qualified class name (for example, `com.example.orders.OrderService`). This makes it easy to trace records by origin and supports dot-separated logger hierarchies.

## 3. Compilable and Runnable Java 17+ Example

The program below demonstrates:

- Two `OrderService` instances sharing a `static final` logger field.
- Calling `Logger.getLogger(...)` with the same name in the same JUL system returns the already registered logger while it still exists.
- Configuring `ConsoleHandler` **once at the example's startup**; each order processing call only logs an event.
- Different `order_id` values across calls, even though the logger is a single shared object.

Save the entire code as **`LoggerReuseDemo.java`**:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggerReuseDemo {
    private LoggerReuseDemo() {
    }

    static final class OrderService {
        private static final Logger LOG =
                Logger.getLogger(OrderService.class.getName());

        void submit(String orderId) {
            LOG.log(Level.INFO,
                    "event=order_submitted order_id={0}", orderId);
        }
    }

    public static void main(String[] args) {
        Logger configured =
                Logger.getLogger(OrderService.class.getName());
        configured.setUseParentHandlers(false);
        configured.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        configured.addHandler(console);

        try {
            OrderService first = new OrderService();
            OrderService second = new OrderService();

            first.submit("ORD-101");
            second.submit("ORD-202");

            Logger byNameAgain =
                    Logger.getLogger(OrderService.class.getName());
            System.out.println(
                    "sameNamedLogger=" + (configured == byNameAgain));
            System.out.println(
                    "sameClassLogger=" + (configured == OrderService.LOG));
        } finally {
            configured.removeHandler(console);
            console.close();
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 LoggerReuseDemo.java
java LoggerReuseDemo
```

**stderr output** (because `ConsoleHandler` defaults to `System.err`, even for `INFO`):

```text
INFO event=order_submitted order_id=ORD-101
INFO event=order_submitted order_id=ORD-202
```

**stdout output** (from `System.out.println`):

```text
sameNamedLogger=true
sameClassLogger=true
```

The stdout and stderr streams may be interleaved by the terminal when displayed; therefore, do not rely on the interleaving order between **the four lines across the two streams** to verify the result. The presentation above separates them by output stream.

### Why is the result `true`?

- `configured` holds a strong reference to the logger named `LoggerReuseDemo$OrderService`. `OrderService.LOG` then requests the logger with that exact name, so within this example's runtime context JUL returns the same object.
- `byNameAgain` calls `Logger.getLogger` again with the same name while the logger already exists and is still referenced; it receives that same object.
- The `first` and `second` instances differ only in `OrderService` instance state; they do not own two separate `LOG` fields.
- Each `submit` call passes the **current call's** `orderId` into the `LogRecord`; the order ID is not stored in a `static` variable that could be overwritten.

The call `LOG.log(Level.INFO, "event=order_submitted order_id={0}", orderId)` uses JUL's parameter formatting. The `Formatter` calls `formatMessage(record)` to replace `{0}` with the order ID when building the string. Thus, the output does not print `{0}` literally.

**Example limitations:** the code only simulates submitting an order and does not interact with a database. The handler is configured programmatically for easy observation; in a real application, configuration should be managed at startup or by the framework. This example does not prove that every logger is a JVM-wide singleton or can be shared across multiple processes.

## 4. How Does `getLogger(name)` Reuse Loggers in JUL?

`java.util.logging.Logger.getLogger(String name)` is the API for obtaining a **named logger** through the logger management system (`LogManager`). When a logger with that name has already been registered in the current management context and still exists, requesting that name again usually returns the same object.

This differs from assuming that writing:

```java
Logger logger = Logger.getLogger("com.example.orders.OrderService");
```

will always create a new logger. The statement calls a lookup/retrieval method, not a `new Logger(...)` constructor. However, repeatedly calling the lookup in every method still makes the code verbose and obscures the class-naming convention. A `static final` field clearly expresses that the class intends to hold and reuse a single logger.

### Lifecycle Caveat

**JUL may hold weak references to named loggers** in its manager. If application code does not keep a strong reference and nothing else references that logger, the object can be garbage-collected; a later `getLogger(name)` call may receive a newly recreated logger instance.

Therefore, claiming that "every `getLogger` call with the same name will forever return the exact same object for the lifetime of the JVM" is too strong. The safe rule for a typical class is to **keep the logger in a `static final` field**. This keeps the logger alive for the lifetime of the class and avoids depending on internal reference management details.

Additional boundaries:

- **The logger name** is a logical identity used in the logger management system, not an identifier for an individual transaction.
- In standard setups, the logger name is the fully qualified class name; loggers named `a.b.Service` and `a.b.Repository` are two distinct names even though they may inherit configuration and share handlers from a parent logger.
- If an application uses a custom logging manager, multiple class loaders, or custom isolation mechanisms, logger management/registration behavior may differ. Do not rely on `==` reference equality across components of a complex system as a business contract.
- `Logger.getAnonymousLogger()` creates an unnamed logger for specialized cases; it does not perform the same stable name-based lookup semantics as `getLogger(name)`.

## 5. Why Choose **One Logger per Class**?

Suppose you have `OrderService`, `PaymentService`, and `OrderRepository`. They can share the same console output destination, yet should have distinct logger names:

```java
// Inside OrderService:
private static final Logger LOG =
        Logger.getLogger(OrderService.class.getName());

// Inside PaymentService:
private static final Logger LOG =
        Logger.getLogger(PaymentService.class.getName());

// Inside OrderRepository:
private static final Logger LOG =
        Logger.getLogger(OrderRepository.class.getName());
```

These are **three sample declarations in three separate classes**, not a single Java file you can paste as-is to compile.

With per-class loggers, operators can set the `FINE` level for `com.example.payment.PaymentService` while investigating an issue without enabling verbose logs for the entire application. Class names also help identify the source and analyze logs sharing a package prefix.

There is no 100% mandatory rule that loggers must be named after classes. A logger **per event category** such as `com.example.business.audit` can be useful if that category has its own routing or retention policy. However, when naming by category, you must make sure the event origin remains clear and avoid losing visibility into which class emitted the log.

### Avoid Logger Names per Business Entity

A poor practice is creating dynamically named loggers such as `order.ORD-101`, `order.ORD-202` for each order. When order volume is large, this bloats the logger namespace, complicates configuration and management, and prevents operators from filtering conveniently by source class.

To track individual orders, keep the class logger and put **`order_id` as a field in the log record**:

```java
LOG.log(Level.INFO, "event=order_paid order_id={0}", orderId);
```

When many requests are processed concurrently, you can also include a corresponding `correlation_id` or `trace_id` in each event. The logger name represents the **origin**, while request/entity IDs represent the **per-execution context**.

## 6. Is Sharing a Logger Thread-Safe?

Standard loggers in popular Java frameworks are designed to be called concurrently from multiple threads on the same object. JUL `Logger` allows concurrent calls to its logging methods; in an example logging two requests:

```text
Thread-A: OrderService.submit("ORD-101") ──> OrderService.LOG
Thread-B: OrderService.submit("ORD-202") ──> OrderService.LOG
                                                |
                                                v
                                      Handler / Formatter / destination
```

Each call creates a separate event. **Reusing a logger does not mean requests share a single `LogRecord` or `orderId` variable.** The `orderId` values are separate arguments to each `submit` invocation.

However, two points must be kept distinct:

1. **Logger thread safety does not make all accompanying data thread-safe.** If you store the current request in a mutable `static` field, two threads can still overwrite each other before logging.
2. **Multi-threaded log order does not automatically reflect exact business order.** Threads interleave; async handlers, network collectors, and search systems may delay or reorder events. For accurate tracing, log timestamps, request identifiers, and appropriate business milestones.

Custom stateful `Handler`/`Appender` or `Formatter` implementations must be designed and tested for thread safety independently. Do not assume every team-written plugin or formatter is thread-safe just because the logger is shared.

## 7. Anti-Pattern: Storing Request Context in a `static` Field

Look at the following code that **should not be used**:

```java
class BadOrderService {
    private static final Logger LOG =
            Logger.getLogger(BadOrderService.class.getName());

    private static String currentOrderId;

    void process(String orderId) {
        currentOrderId = orderId;
        // Another thread could change currentOrderId before this statement.
        LOG.info(() -> "Processing " + currentOrderId);
    }
}
```

If request A sets `currentOrderId="ORD-101"` and pauses, request B can set `currentOrderId="ORD-202"`. When A resumes and logs, A's log record may carry the wrong order ID.

The right and simple approach is to pass the call's context in **local variables or parameters**:

```java
class OrderService {
    private static final Logger LOG =
            Logger.getLogger(OrderService.class.getName());

    void process(String orderId) {
        LOG.log(Level.INFO, "Processing order_id={0}", orderId);
    }
}
```

The two snippets above are standalone class design examples; to run them separately, you must add `import java.util.logging.Logger;` and, for the second snippet, `import java.util.logging.Level;` along with an application entry point.

This is the core principle:

- **The logger is shared** per class.
- **Event data is provided separately** for each log call.
- **Log levels and handlers are configured by policy**, not mutated continuously per request.

Do not call `LOG.setLevel(...)`, `LOG.addHandler(...)`, or `LOG.setFilter(...)` inside each order-processing call. Those operations mutate the shared logger configuration, can affect other requests, and cause duplicate logs or unpredictable behavior.

## 8. Logger Reuse and Correlation Context (MDC)

In web and microservice systems, a single request may be handled across multiple classes, threads, or services. Fields such as `request_id`, `correlation_id`, and `trace_id` allow linking related log records together.

Some frameworks support **Mapped Diagnostic Context (MDC)**: placing key-value pairs into the execution context so log events can automatically include that metadata according to formatter/appender configuration.

Conceptual example with **SLF4J + a compatible MDC implementation** (not part of the standard JDK; requires appropriate dependencies and configuration):

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public class OrderService {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderService.class);

    public void submit(String orderId, String correlationId) {
        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("correlation_id", correlationId)) {
            LOG.info("event=order_submitted order_id={}", orderId);
        }
    }
}
```

The snippet above is **an illustrative class snippet requiring the SLF4J library**, not a Java program runnable with only JDK `javac`. `MDC.putCloseable` helps restore/remove the key just set when exiting the `try` scope as designed by the API; the actual MDC mechanism depends on the implementation, and whether `correlation_id` appears in the output depends on the system's formatter/encoder.

Key points to remember when using MDC:

- The logger remains **`static final`**: there is no need to create a new logger for each request.
- MDC values belong to the **per-execution context**, not the logger; never store `correlation_id` in a `static` class field.
- In thread-pool environments, **clean up scoped data** after the request finishes; otherwise, a reused thread can carry stale metadata.
- When processing asynchronously or handing off across threads, do not assume MDC propagates automatically. You need a context-propagation mechanism supported by your framework/runtime or explicit passing of correlation fields.
- Propagate correlation IDs across network boundaries and log policy-safe fields; avoid putting passwords, tokens, or sensitive personal data into MDC or logs.

In basic JUL, correlation information can be logged as `LogRecord` parameters or handled via a custom formatter/handler integrated with your own context mechanism. Do not assume default JUL provides the same `MDC` API as SLF4J.

## 9. `private static final` vs. `private final`: How to Choose?

Both patterns below work:

**Common pattern: class field**

```java
private static final Logger LOG =
        Logger.getLogger(InventoryService.class.getName());
```

**Instance field pattern**

```java
private final Logger log =
        Logger.getLogger(InventoryService.class.getName());
```

With the instance field pattern, each instance holds its own reference field, yet calling `Logger.getLogger` with the same name may still return **the same existing logger object**, rather than automatically creating a distinct logger per instance. The difference lies in **where the reference is stored and when the lookup runs**.

For typical service classes, `static final` is usually simpler and clearer because the logger does not depend on instance data. An instance field makes sense when the logger is an injected dependency passed via constructor in special cases, when a component selects a logger name/implementation based on instance configuration, or when building specialized logging utilities.

One common pitfall: if you use `LoggerFactory.getLogger(getClass())` in a class that is proxied by a framework or subclassed, the runtime class name may differ from the declaring class you expected. For a stable per-class logger, using `SomeService.class` is usually more predictable. If you intentionally design loggers per subtype, actively control the naming convention and lifecycle.

Do not mechanically apply `static final` to every variable named "logger". For example, a **network-connected appender** or **stateful handler** has different responsibilities and resource lifecycles than a logger; sharing or closing those resources should be managed by the framework's configuration mechanism.

## 10. Reusing Loggers with SLF4J, Logback, and Log4j 2

The per-class logger reuse pattern is not unique to JUL. In Java applications using a logging backend through SLF4J, you commonly see:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class PaymentService {
    private static final Logger LOG =
            LoggerFactory.getLogger(PaymentService.class);

    public void authorize(String paymentId) {
        LOG.info("event=payment_authorization_requested payment_id={}",
                paymentId);
    }
}
```

This is an **example class using an external library**; compiling and running it requires providing the SLF4J API and a compatible backend (such as Logback), not just bare JDK 17.

In this example:

- `LoggerFactory.getLogger(PaymentService.class)` retrieves a logger named after the class through the configured logging system.
- `{}` is the placeholder syntax in this SLF4J call; it **differs** from the `{0}`/`MessageFormat` style in JUL. Do not mix the two placeholder styles.
- `static final` holds a single reference reused across calls and across `PaymentService` instances.
- Logback/Log4j 2 and other implementations determine filtering, appender writing, formatting, and event routing; SLF4J is the logging API called by source code.

When using the Log4j 2 API directly, the analogous pattern is `private static final org.apache.logging.log4j.Logger LOG = org.apache.logging.log4j.LogManager.getLogger(PaymentService.class);`. Similarity in code structure does not mean different implementations have identical registration, caching, reference management, or configuration behavior to JUL.

**Do not create multiple separate logging backends per class just to "reuse loggers".** An application should have a consistent API/implementation strategy and configure it at the appropriate scope. When migrating from JUL to SLF4J, evaluate how bridges and backends interact to avoid forwarding loops, duplicate logs, or configuration conflicts.

## 11. Configure Handlers/Appenders Once to Avoid Duplicate Logs

A common mistake is not creating loggers, but **attaching a new handler on every execution**:

```java
// Example NOT recommended for per-request use:
Logger log = Logger.getLogger("com.example.OrderService");
log.addHandler(new ConsoleHandler());
log.info("Processing");
```

Suppose this code runs three times and the handlers remain attached: on the third call, the same event can be dispatched to three attached `ConsoleHandler` instances, plus any parent logger handlers if event propagation is still enabled. Output is duplicated/triplicated, and handlers may hold unreleased resources.

A better design is:

1. Configure handlers/appenders, formatters, filter levels, destinations, and retention policies in **application configuration or during startup**.
2. Hold the logger on the class with `static final`.
3. Inside processing methods, only call `LOG.info(...)`, `LOG.warning(...)`, or equivalent methods.
4. On application shutdown, let the logging framework or resource owner close handlers/appenders according to their lifecycle.

Specifically in JUL, **loggers are hierarchical**. A child logger can forward events to its parent logger's handlers; if you attach handlers to both, logs may appear twice. When independent configuration is needed, `setUseParentHandlers(false)` disables parent propagation for that logger, though it should be applied intentionally at the configuration point rather than scattered arbitrarily across every class.

## 12. Logger Reuse and Logging Overhead

Keeping a logger in a `static final` field saves code from repeating name-based logger lookups. However, the significant cost in log-heavy applications usually comes from **message construction, converting objects to strings, running formatters, disk I/O, network I/O, and storage**, so you cannot claim every program gains noticeable performance simply by replacing `getLogger(...)` with a field.

Pay attention to *message evaluation* when a log level is disabled:

```java
// First approach: string concatenation is performed before the call.
LOG.fine("details=" + computeDetails());

// Second approach: JUL only invokes the Supplier if logging is enabled at this level.
LOG.fine(() -> "details=" + computeDetails());
```

These are **two illustrative call styles inside a class that has `LOG`**. The second uses JUL's `Supplier<String>`, which is useful when `computeDetails()` is expensive and the `FINE` level may be disabled.

To use it properly:

- The `Supplier` should only build the **message** and must not contain business side effects. If logging is disabled, the supplier may never be invoked.
- Do not put sensitive information into a message just because it is lazily evaluated.
- With SLF4J, overloads accepting `{}` arguments generally avoid unnecessary message formatting; however, if **computing an argument** itself is expensive, consider that separately because arguments are evaluated before the method is called.
- Do not use logger reuse as an excuse to skip sampling policies, log-level management, or storage quotas; a single logger can still generate massive log volume.

## 13. Application Lifecycles and Special Cases

**Simple applications:** the `static final` field is initialized when the class is first initialized; the logger is used until the class and its class loader are no longer retained. There is no need to create or destroy loggers per object.

**Spring or dependency-injection applications:** per-class loggers still typically use `private static final`. Bean lifecycles, request scope, or singleton beans are separate concepts from a `static` field; even if a bean is recreated, the class-level logger can still be reused. If the logging framework provides auto-configuration, do not manually create extra `ConsoleHandler` instances just because you have a logger.

**Shared libraries:** name loggers after the library's packages/classes so consuming applications can filter them independently. Avoid hardcoding fixed file paths or endpoints directly from library code.

**Plugin / class-loader applications:** fully qualified class names may collide across class loaders or follow different isolation rules depending on the logging system. Do not rely on a "JVM-wide unique class name" assumption to design shared mutable state or access application data.

**Short-lived tasks or batch jobs:** multiple jobs may run within the same process. The class logger is reused, while `job_id` or `batch_id` must be supplied per run and context must be cleaned up carefully.

**Shutdown:** emitted logs may still sit in handler/appender buffers. Resource closing and flushing should be managed by the logging system owner. Never close a shared handler when **a single request** completes: doing so can cut off logs from other requests.

## 14. Comparison of Logger Organization Approaches

| Approach | Is the logger reused? | Assessment |
| --- | --- | --- |
| `private static final Logger LOG = Logger.getLogger(MyClass.class.getName());` | One class field holds a stable reference | **Generally recommended** for typical Java classes using JUL |
| `private final Logger log = Logger.getLogger(MyClass.class.getName());` | May resolve to the same named object, but each instance holds a reference and performs a lookup | Valid, though usually unnecessary if the logger name is fixed |
| Calling `Logger.getLogger(MyClass.class.getName())` in every method | May retrieve the existing logger; not guaranteed to create a new one | Works, but harder to maintain conventions and repeats lookup logic |
| One logger named `"application"` for all classes | Shares a logger with the same name | Can lose origin distinction; choose only with a specific reason |
| Logger named `"order." + orderId` | Creates a namespace per business entity | **Avoid**: put `order_id` in the log record instead |
| Adding `ConsoleHandler` on every request | Logger may be reused, but handlers accumulate repeatedly | **Wrong lifecycle**, causes duplicate logs and resource leaks |
| One logger per class, `request_id` metadata per call | Shared logger, separated event data | **Well-suited** for concurrent multi-request systems |

## 15. Common Mistakes and How to Fix Them

**1. Creating dynamic loggers per entity ID.** Use stable class names and record entity IDs in event fields. Logger names are not lifecycle management tools for individual orders.

**2. Equating "reuse" with "system-wide singleton".** The `static final` pattern only keeps one field per class. Each class typically has its own logger; those loggers may share backends and handlers depending on configuration.

**3. Assuming `static final` makes a logger immutable.** It only locks field reassignment. Do not change levels, handlers, or filters per request because those remain shared state.

**4. Storing `currentUser` or `currentOrderId` in `static` variables for the logger to read.** This risks mixing data across threads. Pass arguments at log time or use properly managed and cleaned-up per-request context.

**5. Adding a handler per instance to a logger with the same name.** In many configurations, the logger outlives instances; handlers accumulate and records are duplicated. Configure once at the logging management point.

**6. Confusing JUL placeholders with SLF4J placeholders.** JUL uses `{0}` when its formatter processes parameters; SLF4J commonly uses `{}`. Mixing the two can cause literal placeholders to appear in logs.

**7. Assuming a single logger guarantees strict log ordering.** With multiple threads and asynchronous collectors, events can interleave or arrive out of order. Include correlation IDs and timezone-aware timestamps, and check authoritative state when needed.

**8. Ignoring MDC lifecycle.** If MDC lives on a thread-pool thread and is not cleared when a request ends, metadata from a previous request can leak into the next.

**9. Relying on a logger staying alive forever via `getLogger(name)` alone.** In JUL, `LogManager`'s weak references mean an unreferenced logger can be garbage-collected. Keep an appropriate strong reference such as a `static final` field.

**10. Optimizing logger lookups while over-logging sensitive content.** Protecting data, choosing appropriate log levels, and controlling log volume matter far more than saving a few logger lookup calls.

## 16. Self-Check Questions

1. **Two `OrderService` instances have `private static final Logger LOG`. Do they have two different loggers?** No: they access the same class-level `LOG` field; log calls still produce separate events.
2. **Does calling `Logger.getLogger("x.y.Service")` twice always create two objects?** No. When a logger with that name still exists and is managed in the same JUL context, the subsequent call can return the existing logger; in the runnable example, it is the same object.
3. **Why hold a JUL logger in a `static final` field?** It reuses a stable reference, preserves the source name, and avoids relying on the manager's weak reference keeping the object alive.
4. **Should you create a logger named `order.ORD-101` to track a specific order?** Usually no. Use a class-based logger name and an `order_id=ORD-101` field in the event.
5. **Does a shared logger make `correlation_id` identical across all requests?** No. The correlation ID is per-request data and must be attached separately to each execution flow/event.
6. **What can happen if a `ConsoleHandler` is attached every time a method runs?** Handlers accumulate, events are output multiple times, and resources become hard to manage. Configure handlers at the application level.
7. **Does `static final Logger` guarantee the log level cannot change?** No. `final` does not make the `Logger` object immutable; logger configuration can still be modified.
8. **Why does the Java example have two separate stderr lines and two stdout lines?** `ConsoleHandler` writes JUL messages to stderr; `System.out.println` prints reference comparison results to stdout. The order when a terminal interleaves both streams is not guaranteed.
9. **Does calling `MDC.putCloseable` create a new logger for the request?** No. It only manages metadata for the execution scope; the class logger continues to be reused.
10. **When the `FINE` level is disabled, why is `LOG.fine(() -> computeDetails())` helpful?** The supplier may not be invoked, avoiding message construction cost; do not use the supplier to perform business logic with side effects.

**Key takeaway:** code typically **holds one class-named logger**, reuses it across many instances and executions, configures handlers/appenders at the application lifecycle level, and supplies **dynamic context in each log record**. Logger reuse keeps logging consistent; the correctness and safety of logged data still depend on how parameters are passed, how request context is managed, and how destinations are designed.
