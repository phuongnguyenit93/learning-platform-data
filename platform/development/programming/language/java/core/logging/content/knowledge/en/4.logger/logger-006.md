# Child Loggers in Java Logging

When an application has dozens of packages and hundreds of classes, configuring log levels for each class individually becomes difficult to manage. **Child loggers** solve this by placing loggers into a **name-based hierarchy**, allowing them to inherit certain settings from a parent logger and, depending on the logging system, forward generated events to the parent's output destinations.

The most important point: **level inheritance** and **forwarding records to a parent's handler/appender** are two separate mechanisms. Understanding both mechanisms helps you enable DEBUG for a group of classes, keep INFO for the rest, and avoid lost or duplicated logs.

## 1. What Is a Child Logger?

A logger hierarchy can have names like:

~~~text
(root)
  |
  +-- com.example
        |
        +-- com.example.orders
              |
              +-- com.example.orders.payment
              |
              +-- com.example.orders.shipping
~~~

In this example, **com.example.orders.payment** is a child logger of **com.example.orders** if the backend or JUL establishes the parent–child relationship properly; **com.example** is a higher-level ancestor.

Dot-separated names help represent package or component boundaries. However:

- The parent–child logger relationship is **not Java class inheritance** via `extends`. The `PaymentService` class does not need to `extends OrderService` for its logger to sit under the `com.example.orders` namespace.
- A child logger is also **not a child thread** or child process. Two threads can emit events concurrently through a logger with a fixed name.
- **An arbitrary string prefix is not enough to be a parent**: `com.example.order` and `com.example.orders` are two different branches. The hierarchy is based on name segments separated by dots.
- You do not necessarily have to create a logger for every node in the diagram. Depending on the framework, a logger is attached to the nearest existing ancestor or the closest matching configuration.

In the JDK's **java.util.logging (JUL)**, you can inspect the actual parent logger with **Logger.getParent()**. A logger is typically obtained via **Logger.getLogger("name")**; the name is the logger's identity and can be used to group configuration.

In **SLF4J**, source code uses the **org.slf4j.Logger** facade, while how the logger tree, inheritance levels, and output destinations are managed is the behavior of the implementation/backend, such as Logback. There is no common `getParent()` method on the SLF4J `Logger` interface.

### Logger Names Usually Follow Package or Class Names

Two common patterns:

~~~java
// JUL: class-based name
private static final java.util.logging.Logger LOG =
        java.util.logging.Logger.getLogger(PaymentService.class.getName());
~~~

~~~java
// SLF4J: class-based name (illustrative snippet; requires slf4j-api)
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(PaymentService.class);
~~~

If `PaymentService` is in the **com.example.orders.payment** package, the logger name usually corresponds to the fully qualified class name **com.example.orders.payment.PaymentService**. Because of this, you can configure by package to affect all classes underneath it.

Do not create new loggers whose names include `requestId`, `orderId`, `userId`, or a timestamp. Values that vary per request belong in **record context**, not as part of the logger name: dynamic names increase the number of loggers to manage and make configuration hard to control.

## 2. First Mechanism: Level Inheritance

The level determines whether an event at a given severity is accepted by the logger. In JUL, each logger can carry its own level or **null** to inherit the level from the nearest parent logger that has a specific level configured.

Example:

~~~text
Logger "com.example.orders"          -> WARNING
           |
Logger "com.example.orders.payment"  -> null (inherited)
~~~

When the payment logger calls:

~~~java
child.info("request started");
child.warning("payment retry");
~~~

The child logger has **effective level = WARNING**. The `INFO` event is discarded immediately at the emitting logger; `WARNING` is allowed to proceed.

If the code runs:

~~~java
child.setLevel(java.util.logging.Level.FINE);
~~~

The child logger now has its own threshold **FINE**, allowing `FINE`, `INFO`, `WARNING`, and more severe levels. The parent logger still has level `WARNING`; other loggers can continue inheriting `WARNING`.

For JUL:

- **child.setLevel(null)**: clears the logger's own level override and reverts to inheriting from the parent.
- **child.getLevel()**: returns the directly assigned level; a **null** result does not mean logging is disabled.
- **child.isLoggable(Level.INFO)**: indicates whether `INFO` is accepted by the logger under its current effective level.
- **Level.OFF**: disables normal levels on the logger; **Level.ALL** lets all levels pass the logger's level check, though downstream handlers/filters can still block them.

Typical JUL levels in order from most detailed to most severe are `FINEST`, `FINER`, `FINE`, `CONFIG`, `INFO`, `WARNING`, `SEVERE`. SLF4J/Logback typically use `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`. **Do not mix level names from the two APIs** when writing examples or configuration.

In Logback, a child logger can also inherit its level from a parent logger when no own level is specified; setting a level for a package lets you enable `DEBUG` selectively. The API mechanisms and configuration names differ from JUL.

## 3. Second Mechanism: Forwarding Logs to the Parent Logger

After an event is accepted by the child logger, the system can forward that event to handlers/appenders attached to the parent logger. In JUL, this behavior is controlled by:

~~~java
child.setUseParentHandlers(true);  // forward to parent's handlers
child.setUseParentHandlers(false); // do not forward to parent's handlers
~~~

By default, a normal JUL logger uses its parent's handlers unless disabled. A logger with no handlers of its own can still produce log output because events are passed up to the parent logger's or root logger's handlers.

**Especially important:** In JUL, when an event travels from a child logger up to a parent's handler, **the parent logger's level and filter are not re-checked for an event already accepted by the child**. The receiving handler checks **the handler's own** level and filter.

Example:

~~~text
parent logger level = WARNING
child logger level  = FINE
parent handler      = ALL
~~~

A `FINE` event emitted by **child** can still reach the **parent handler**, even though the parent logger's level is `WARNING`. Conversely, if the parent handler only accepts `WARNING` and above, the `FINE` event will be dropped by the handler.

This rule makes the statement “every record from a child logger must pass through the parent logger's level threshold again” **false for JUL**. You must clearly separate **the event creation/acceptance threshold** from **the threshold at the destination**.

Scenario table:

| Configuration | child.info / child.fine | Expected Result |
| --- | --- | --- |
| Parent WARNING; child inherits | INFO | Dropped at child logger; handler does not receive it |
| Parent WARNING; child inherits | WARNING | Accepted and can be forwarded to parent handler |
| Parent WARNING; child FINE; parent handler ALL | FINE | Output at parent handler |
| Parent WARNING; child FINE; parent handler WARNING | FINE | Passes child logger but blocked by parent handler |
| Child FINE; no own handler; parent handlers disabled | FINE | Accepted by logger but has no output destination |
| Child has own handler and still forwards to parent | WARNING | Can be output at both handlers, depending on configuration |

**Handler forwarding is not level inheritance.** Disabling parent handlers does not automatically change the child logger's effective level; setting a separate `FINE` level does not automatically disable forwarding to parent handlers.

## 4. Complete Java 17+ Example: Observing Both Mechanisms

The program below uses only **java.util.logging**, with no external dependencies. It creates a parent and child logger, attaches a handler to the parent, and then adds a separate handler to the child. The custom handler prints to **stdout** so the output is short and easy to inspect; this is a choice for the example, whereas JUL's default `ConsoleHandler` writes to **stderr**.

Create the file **ChildLoggerDemo.java**:

~~~java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ChildLoggerDemo {
    private static final class NamedHandler extends Handler {
        private final String name;

        NamedHandler(String name) {
            this.name = name;
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                System.out.println(name + " | " + record.getLevel().getName()
                        + " | " + record.getMessage());
            }
        }

        @Override
        public void flush() {}

        @Override
        public void close() {}
    }

    public static void main(String[] args) {
        Logger parent = Logger.getLogger("demo.orders");
        Logger child = Logger.getLogger("demo.orders.payment");

        parent.setUseParentHandlers(false);
        parent.setLevel(Level.WARNING);
        parent.addHandler(new NamedHandler("PARENT"));

        child.setLevel(null);
        System.out.println("parent=" + child.getParent().getName());

        child.info("inherited INFO");
        child.warning("inherited WARNING");

        child.setLevel(Level.FINE);
        child.fine("child FINE");

        child.addHandler(new NamedHandler("CHILD"));
        child.warning("two destinations");

        child.setUseParentHandlers(false);
        child.warning("local only");
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac ChildLoggerDemo.java
java ChildLoggerDemo
~~~

Exact **stdout** output:

~~~text
parent=demo.orders
PARENT | WARNING | inherited WARNING
PARENT | FINE | child FINE
CHILD | WARNING | two destinations
PARENT | WARNING | two destinations
CHILD | WARNING | local only
~~~

### Step-by-Step Analysis

**Step 1 — Establishing the parent–child relationship.** Logger `demo.orders` is created before `demo.orders.payment`. Calling `child.getParent().getName()` confirms the direct parent in this example is `demo.orders`. In JUL, the actual direct parent may be the nearest existing ancestor logger.

**Step 2 — Level inheritance.** `parent` has level `WARNING`, and `child.setLevel(null)` sets the child to inherit. Therefore `child.info("inherited INFO")` produces no output, while `child.warning("inherited WARNING")` is output through the parent's handler.

**Step 3 — Overriding the log level on the child.** After `child.setLevel(Level.FINE)`, `child.fine("child FINE")` is accepted. Even though the parent logger is set to `WARNING`, the `PARENT` handler still prints `FINE` because this handler accepts `ALL`; the parent logger does not re-filter events coming from the child.

**Step 4 — Having two output destinations.** `child.addHandler(...)` adds the `CHILD` handler. By default the child still forwards events up to the parent, so `"two destinations"` is printed once by `CHILD` and once by `PARENT`. These are two handlers seeing the same log event; in a real application this can become **duplicate logging** if both handlers write to the same destination.

**Step 5 — Disabling forwarding.** `child.setUseParentHandlers(false)` causes `"local only"` to go only to the `CHILD` handler. The `FINE` level on `child` remains unchanged.

The example intentionally configures everything in `main` so learners can see each step. In a large application, you should configure handlers/levels centrally at startup or in a configuration file rather than repeating configuration in every class; adding handlers multiple times across initializations can cause duplicate logs.

## 5. Hierarchical Configuration with JUL's logging.properties

With JUL, you can set log levels for a namespace without modifying the code of individual classes. Example standalone **logging.properties** file:

~~~properties
# Root logger handlers
handlers = java.util.logging.ConsoleHandler

# Default level at root
.level = INFO

# Allow ConsoleHandler to display FINE as well
java.util.logging.ConsoleHandler.level = ALL

# Most of the orders application only needs WARNING
com.example.orders.level = WARNING

# The payment group specifically needs more detailed logs
com.example.orders.payment.level = FINE
~~~

When the application actually creates loggers with these names, loggers at the `payment` level receive their own `FINE` level, while other loggers under `com.example.orders` can inherit `WARNING` if no other level is set. The root handler receives events forwarded to it and filters them according to its `ALL` configuration.

JUL reads the configuration file when `LogManager` initializes if you specify the JVM property:

~~~bash
java -Djava.util.logging.config.file=logging.properties MyApplication
~~~

This is an illustrative command for a compiled **MyApplication** program, not a command for `ChildLoggerDemo` above: that program explicitly resets levels and handlers in `main`, which would override part of the properties configuration.

Points to note:

- Package names in the configuration file must match the logger names actually used in code.
- A logger with its own level **does not continue automatically inheriting** its parent's level until its own level is set back to `null`.
- **Handlers have their own thresholds.** Enabling `FINE` on a child while keeping `ConsoleHandler` at `INFO` can prevent `FINE` from appearing.
- A logger can receive output through the root's handler even if it has no handler of its own; you do not need to attach a `ConsoleHandler` to every logger.
- Configuration may be managed by the running framework or container; identify which file is actually loaded before editing.

## 6. Child Loggers with SLF4J and Logback

SLF4J is a **facade**: the application calls `org.slf4j.Logger`, while organizing the hierarchy, configuring levels, and managing appenders belong to the chosen backend. **Logback** is a popular backend that provides a hierarchical name-based logger mechanism.

Suppose calls are made in classes named:

~~~text
com.example.orders.OrderService
com.example.orders.payment.PaymentService
com.example.orders.payment.RetryPolicy
com.example.orders.shipping.ShippingService
~~~

You can configure the entire `orders` group at `INFO` while setting `payment` specifically to `DEBUG`. An illustrative **logback.xml** file:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger{60} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders" level="INFO"/>
    <logger name="com.example.orders.payment" level="DEBUG"/>

    <root level="WARN">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Meaning:

- Loggers named under **com.example.orders**, if they have no more specific level, use the `INFO` threshold.
- Loggers named under **com.example.orders.payment**, if not further overridden, use `DEBUG`.
- Root has level `WARN` for events **emitted directly from loggers inheriting the root level**. The root appender can still output a `DEBUG` event already accepted by the `payment` logger and forwarded to root, because the root logger's level is not re-applied while propagating events through Logback's appender hierarchy.
- If the appender has a `ThresholdFilter` or another filter, the event can still be blocked there.

The example above only needs **one appender at root** to receive events from child loggers via the default **additivity = true** mechanism. This is an illustrative Logback configuration snippet; the project must have compatible SLF4J API and Logback backend/provider dependencies.

### When Is additivity="false" Needed?

Suppose the `CONSOLE` appender is already attached to `root`, and you also attach **the same appender** to the `payment` logger:

~~~xml
<logger name="com.example.orders.payment" level="DEBUG">
    <appender-ref ref="CONSOLE"/>
</logger>
~~~

If default additivity is kept, a log event emitted by `payment` can pass through the appender on `payment` and then continue to the appender on `root`, resulting in two identical lines on the console. When you want the `payment` logger to output to its own appender and **not forward to ancestor appenders**, configure:

~~~xml
<logger name="com.example.orders.payment"
        level="DEBUG"
        additivity="false">
    <appender-ref ref="CONSOLE"/>
</logger>
~~~

The two snippets above are **alternatives**—do not place both in the same configuration file at the same time. When using `additivity=false`, ensure the logger has an appropriate output path; without a direct appender or another output route, events may go nowhere.

In Logback, **additivity** controls forwarding events to appenders on parent loggers. It is not the same as disabling level inheritance. A logger without its own level can still inherit a level from its parent even when `additivity=false`.

## 7. JUL, Logback, Log4j 2: Similarities and Differences

| Aspect | JUL | SLF4J + Logback | Log4j 2 |
| --- | --- | --- | --- |
| Commonly used logger object in code | java.util.logging.Logger | org.slf4j.Logger | org.apache.logging.log4j.Logger, or SLF4J via adapter |
| Logger name hierarchy | Dot-separated hierarchical names | Dot-separated hierarchical logger names in Logback | LoggerConfig can match by name/namespace; handled via configuration |
| Level inheritance | setLevel(null) inherits from parent | Logger without its own level inherits effective level via hierarchy | Effective level based on matching LoggerConfig |
| Output destination | Handler | Appender | Appender |
| Forwarding to parent | setUseParentHandlers(boolean) | additivity | additivity in LoggerConfig |
| Inspect parent via facade? | JUL has getParent() | SLF4J API has no common getParent() | Not identical to JUL getParent() |

Do not assume two APIs share the same configuration syntax. For example, **setUseParentHandlers(false)** is a JUL method, whereas **additivity=false** is an option in backends like Logback/Log4j 2; both relate to routing, but their syntax is not interchangeable.

With Log4j 2, distinguish between **Logger** used in application code and **LoggerConfig** used by the backend to apply levels, filters, and appenders by name. Do not assume a Java `Logger` object must have a direct parent `Logger` object like JUL; one `LoggerConfig` can be shared by many logger names. The backend still provides ways to set levels and output destinations by namespace.

SLF4J itself is a facade; without a valid provider/backend at runtime, log calls may not reach the intended destination. Editing hierarchy configuration will not fix a missing backend or conflicting providers.

## 8. Using Child Loggers in Real Applications

### Lowering Log Granularity Without Editing the Entire Application

When you only want to investigate one area of code, such as `payment`:

1. Set the default level to an appropriate value for the application, such as `INFO`.
2. Enable `DEBUG`/`FINE` **for the payment namespace**, not for the whole application.
3. Keep appender/handler thresholds low enough so detailed events reach the observed destination.
4. Revert the level once the investigation is over to avoid excessive logs, I/O overhead, and unnecessary data exposure.

This is the classic operational benefit of the hierarchy: changing one package without editing individual log statements across many classes.

### Separating Log Destinations by Component

A child logger can attach a dedicated appender for technical auditing, batch jobs, or a module under investigation. When doing so, you must decide explicitly whether logs should also continue up to `root`.

If the goal is to have **both centralized records and separate records**, you can intentionally leave `additivity=true` and attach two appenders pointing to **two different destinations**. If both appenders point to the same file/console, events can be duplicated. Test with a real event to confirm each destination receives the expected number of lines.

For data requiring audit guarantees or durable storage, merely creating a child logger named `audit` is **not enough** to provide storage guarantees. You must design appropriate auditing, access control, and data durability mechanisms as well.

### Relationship with MDC and Correlation IDs

Child loggers are for **categorizing the code source**; correlation IDs are for **linking records belonging to the same request**. Do not replace `requestId` with dynamic logger names.

For example, a request passing through three loggers:

~~~text
com.example.orders.OrderController
com.example.orders.OrderService
com.example.orders.payment.PaymentGatewayClient
~~~

Each logger keeps a stable class-based name, while `requestId`/`traceId` is placed in the record context. When querying, filter by `requestId` to trace across loggers; filter by namespace to inspect the behavior of a code group.

## 9. Common Pitfalls with Child Loggers

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Parent set to INFO, but child does not print DEBUG | Child still inherits INFO, or handler/appender is filtering DEBUG | Check child's effective level, handler/appender threshold, and filters |
| Child has level FINE, but no FINE lines appear | Parent-level handler is set to INFO/WARNING, or parent routing is disabled | Check child.isLoggable, handler level, and setUseParentHandlers |
| FINE record appears via parent despite parent WARNING | Child accepts FINE; parent handler allows FINE | This may be expected behavior: parent logger level does not re-filter events already accepted by child |
| A single event is output twice | Child and parent both have handlers/appenders writing to the same destination | Check JUL parent handlers or Logback additivity and appender list |
| Adding additivity=false causes logs to disappear | Child logger has no suitable appender of its own | Attach the needed appender or allow forwarding to parent |
| Package-level configuration has no effect | Logger name in code does not match configured namespace | Check Logger.getName() or the logger name printed in logs |
| Calling getParent() on SLF4J Logger fails to compile | SLF4J facade does not expose that API | Only use getParent() on java.util.logging.Logger; inspect hierarchy via the backend |
| Abnormal logs after adding a bridge | The same event is routed through multiple paths or a bridge loop | Review the JUL/SLF4J/Log4j 2 forwarding diagram and runtime dependencies |
| Naming loggers per user/request makes the system hard to manage | Too many dynamic logger names are created | Keep loggers per class/package; put IDs in structured fields/MDC |

Do not treat duplicate logging by arbitrarily raising the level from `INFO` to `ERROR`. That hides useful events without fixing the routing path causing duplication.

## 10. Reasoning Exercise

Suppose you have the following JUL settings:

~~~text
Parent:         app.orders, level = INFO
Child:          app.orders.payment, level = null
Parent handler: level = WARNING
Child:          useParentHandlers = true, no own handler
~~~

Questions:

1. When the child calls `info("created")`, is it accepted by the logger? Is it output at the parent handler?
2. When the child calls `warning("retry")`, is it output?
3. After `child.setLevel(Level.FINE)`, when the child calls `fine("debug")`, is it output?
4. If the parent handler is changed to `Level.ALL`, how does the answer to question 3 change?
5. If `child.setUseParentHandlers(false)` is called with no own handler, what happens to `WARNING`?

**Answers with Explanations:**

1. `INFO` is accepted by the child because it inherits `INFO`, **but it is not output** because the parent handler requires `WARNING`.
2. `WARNING` is accepted by both the child and the parent handler, so it **is output**.
3. `FINE` is accepted by the child after the override, but it is **blocked by the parent handler** at the `WARNING` threshold.
4. `FINE` **is output** when the handler allows `ALL`; the `INFO` level on the parent logger does not re-filter events from the child.
5. `WARNING` can still be accepted by the child in terms of level, but it **no longer has an output destination** under this configuration.

This exercise shows that you must check **both the event acceptance condition and the route to the handler**, not just the level property alone.

## 11. Best Practices

When designing child loggers:

- Use stable package/class-based names; keep naming conventions consistent across modules.
- Set default levels at parent namespaces; only override in child namespaces that have special needs.
- Clearly distinguish **level inheritance** from **event propagation** when diagnosing missing or duplicate events.
- Check handler/appender thresholds, filters, and additivity rather than inferring everything from the root level alone.
- If a framework already manages the backend and hierarchy, prefer the framework's configuration file over adding handlers in individual classes.
- Include useful context in logs without logging secrets; correlation IDs belong in message content/context, not in logger names.
- When you need to verify behavior, emit a test event at multiple levels and check **the actual receiving destination**.

**Key Takeaway:** Child loggers help group and control logs by namespace. A child logger can **inherit a level** from its parent or **set its own level**, and it can also **forward events to its parent's handlers/appenders** or stop forwarding. These two decisions are independent, and the final result also depends on filters and output destinations.