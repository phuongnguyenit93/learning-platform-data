# Loggers and Backends in Java

When a Java application writes a log, the logger call is only the starting point. The component that actually decides **whether a log record is emitted, how it is formatted, and where it goes** is the logging system behind it. Distinguishing between a logger, an API/facade, and a backend helps you choose the right dependencies, configure log levels properly, and troubleshoot issues such as missing logs or duplicate log entries.

## 1. What Is a Logger and What Does a Backend Do?

A **log event** typically consists of a level, a logger name, a message, a timestamp, and optionally an exception or context. For example, an application may need to record an INFO event when a task completes.

- A **Logger** is the object that source code calls to create a log event, such as a logger bound to the running Java class. The logger name is usually a class or package name so log levels can be tuned by scope.
- A **Logging API** defines the Logger type, methods, and levels that source code uses.
- A **Facade** is a common API layer placed in front of multiple implementation systems. For example, source code calls SLF4J without depending directly on Logback or Log4j Core.
- A **Provider / binding / adapter** connects an API/facade to an appropriate receiving system. The exact terminology and mechanism depend on the library and version.
- A **Backend (implementation)** processes the event: applying levels/filters, formatting it, and forwarding it to its destination.
- A **Handler** (in `java.util.logging`, abbreviated JUL) or **appender** (in Logback/Log4j 2) is the component that outputs records to the console, a file, or another target. A formatter/layout determines how the record is rendered.

~~~mermaid
flowchart LR
    A["Application code"] --> B["Logger / logging API"]
    B --> C["Provider or adapter if needed"]
    C --> D["Backend processes event"]
    D --> E["Handler / appender"]
    E --> F["Console, file, centralized system"]
~~~

This is a conceptual model; **not every system has each box separately**. With JUL, the Logger and the logging processor are both part of the JDK—no extra facade or provider is needed. With SLF4J, the API sits on the application side and requires a compatible provider/backend at runtime for logs to actually be processed.

Common flow examples:

- **Plain JUL:** Java code → `java.util.logging.Logger` → JUL processor → `ConsoleHandler`/`FileHandler`.
- **SLF4J + Logback:** Java code → `org.slf4j.Logger` → SLF4J provider supplied by Logback → Logback appender.
- **SLF4J + Log4j 2:** Java code → `org.slf4j.Logger` → Log4j 2's SLF4J 2 adapter/provider → Log4j Core → appender.

Calling `LoggerFactory.getLogger(...)` or `Logger.getLogger(...)` **does not mean** opening a log file, and executing a log statement **does not guarantee** the message will appear: it also depends on level configuration, filters, the backend, and the output destination.

## 2. Easily Confused Names

| Component | Primary Role | Key Takeaway |
| --- | --- | --- |
| **java.util.logging (JUL)** | Built-in JDK API and logging implementation | Uses `java.util.logging.Logger`, `Handler`, `Formatter`, `LogManager`; requires no external logging dependencies. |
| **SLF4J** | Facade/API for application and library code | `org.slf4j.Logger` is the logging call interface; `slf4j-api` itself is not a logging backend. |
| **Logback** | Logging backend, commonly paired with SLF4J | `logback-classic` provides an SLF4J provider; appenders, encoders, and configuration control the output. |
| **Log4j 2** | Logging suite with its own API and Core | `log4j-api` is the API; `log4j-core` handles output; includes an adapter to receive logs from SLF4J. |
| **Bridge / adapter** | Forwards events between two APIs/systems | Check the **forwarding direction** and avoid creating loops between bridges. |

Two Java classes named `Logger` are not necessarily the same type: `java.util.logging.Logger` is different from `org.slf4j.Logger` and different from `org.apache.logging.log4j.Logger`. Always check the **import** to know which API a log statement is going through.

A library should prefer the logging API expected by its ecosystem, commonly SLF4J; the **final running application** decides which backend will be on the runtime classpath. A library using a facade should generally not force the application to carry competing backends.

### API and Backend Are Not Interchangeable

For example, the `slf4j-api` dependency lets you compile code that uses `org.slf4j.Logger`. However, with **SLF4J 2.x**, if no compatible SLF4J provider is found at runtime, SLF4J warns and falls back to a no-operation (NOP) logger that produces no output. Adding a compatible backend completes the processing pipeline.

Conversely, adding `logback-classic` to an application **does not automatically route all JUL calls to Logback**: code using `java.util.logging` still goes through JUL unless a bridge is installed and configured appropriately.

## 3. Complete Example Without External Libraries: JUL

JUL is a useful way to understand the relationship between Logger, log levels, and Handler without needing Gradle or Maven.

Create the file **JulDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class JulDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger(JulDemo.class.getName());

        // Avoid duplicate output via parent/root logger handlers.
        logger.setUseParentHandlers(false);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        // FINE events must pass through both Logger and Handler.
        logger.setLevel(Level.FINE);
        logger.addHandler(console);

        logger.fine("cache warmup");
        logger.info("service ready");
        logger.warning("retry requested");

        console.flush();
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac JulDemo.java
java JulDemo
~~~

Three lines are written to **stderr** by `ConsoleHandler` (formatted as fixed in the example):

~~~text
FINE | cache warmup
INFO | service ready
WARNING | retry requested
~~~

Notable mechanics:

1. The Logger named `JulDemo` creates events with a level and a message.
2. **logger.setLevel(Level.FINE)** allows `FINE` and more severe levels to pass through the Logger's filter.
3. **console.setLevel(Level.ALL)** ensures the Handler does not separately drop `FINE` events. If the Handler were set to `INFO`, `FINE` would still be blocked even though the Logger allows it.
4. **setUseParentHandlers(false)** disables forwarding events to parent logger handlers; if the same event reaches multiple handlers, duplicate logs can appear.
5. The Formatter in the example outputs only the level and message for predictable output. Production formatters can also include timestamps, logger names, and stack traces; to print full exceptions, a custom formatter must handle `record.getThrown()`.

JUL has levels such as `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER`, `FINEST`, `ALL`, and `OFF`. This is **not the same set of level names** as SLF4J (`ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE`). When passing through a bridge, levels are mapped according to the bridge's rules; do not assume the two APIs have identical level names or exact equivalents.

## 4. Application Example Using SLF4J and a Logback Backend

This example uses Java 17+, Gradle, and **SLF4J 2.x**. Application code only imports SLF4J; Logback is selected at runtime. The versions below form a compatible set for illustration and are not meant to prescribe the latest version for every project.

**build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.17'
    runtimeOnly 'ch.qos.logback:logback-classic:1.5.18'
}

application {
    mainClass = 'demo.Slf4jDemo'
}
~~~

**src/main/java/demo/Slf4jDemo.java**:

~~~java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class Slf4jDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(Slf4jDemo.class);

    public static void main(String[] args) {
        String taskName = "sync";

        LOG.info("Job {} completed", taskName);
        LOG.debug("Debug code {}", 42);
    }
}
~~~

**src/main/resources/logback.xml**:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Run from the project directory using **gradle run** (or **./gradlew run** if the project has a Gradle Wrapper). The log line from the application looks like:

~~~text
INFO demo.Slf4jDemo - Job sync completed
~~~

The `DEBUG` line is not printed because the backend sets `root level = INFO`. The full command output may also contain Gradle build messages.

Why split dependencies this way?

- **implementation slf4j-api:** source code compiles against the stable facade interface.
- **runtimeOnly logback-classic:** the backend is provided at runtime; it registers a compatible SLF4J provider. If your application or framework already provides a backend, use the framework-managed dependency configuration instead of adding another backend.
- **logback.xml:** the backend reads appender and level configuration. Switching from Logback to another SLF4J backend usually does not require modifying `LOG.info(...)` calls in source code; however, the configuration file, features, and backend dependencies will change.

The **{}** parameter placeholder syntax in the example belongs to SLF4J. It does not apply verbatim to JUL: each API has its own methods and formatting mechanisms.

### One Selected Backend Can Be Shared by Many Loggers

A Logger is typically declared as a `static final` field per class. Multiple loggers all write through the backend system configured for the application; there is no need to create a separate appender or file per class. Logger names allow setting levels by package—for example, raising `DEBUG` only for the code under investigation while keeping the rest at `INFO`.

## 5. Levels and the Path of a Log Event

Not seeing a log record does not necessarily mean the logger is broken. An event can be dropped at any of several places:

1. **Call site / logger:** If the level is not enabled, the API can discard the event right away.
2. **Effective configuration:** A logger may inherit the level of its package or root logger when it does not define its own level.
3. **Backend/handler/appender filters:** The event is accepted by the Logger but blocked at a later stage.
4. **Dispatching:** An event can be sent to multiple appenders/handlers. If additivity or parent-logger forwarding is misconfigured, the same event may be printed multiple times.
5. **Destination:** Console output may go to stdout or stderr, a file may be at a relative path, or the backend may push logs to a centralized system.

In JUL, both the logger and each handler have a level; `setUseParentHandlers` controls forwarding to parent logger handlers. In Logback, the root logger and named loggers have levels, while appenders and filters handle further processing; the **additivity** attribute controls forwarding logs to parent loggers. These are two different configuration models for similar needs, not a single shared API.

An event processing flow can be visualized as follows:

~~~text
logger.info(...)
   |
   +--> logger/backend allows INFO level? -- no --> discard
   |
  yes
   |
   +--> filter/appender/handler accepts? -- no --> discard
   |
  yes
   |
   +--> format --> console / file / collection system
~~~

When troubleshooting, first identify which API the logger uses, then trace the actual backend and destination. Raising the level in one place will not help if a downstream step still blocks the event.

## 6. Bridges: When Multiple Logging Systems Coexist

A real-world application may use SLF4J while another dependency logs via JUL or the Log4j 2 API. A **bridge** receives events from one API and routes them to another system so a central backend can process them.

| Component | Typical Forwarding Direction |
| --- | --- |
| **jul-to-slf4j** | JUL → SLF4J; requires installing `SLF4JBridgeHandler` and handling existing JUL handlers to avoid duplicate logs. |
| **log4j-to-slf4j** | Log4j 2 API → SLF4J. |
| **log4j-slf4j2-impl** | SLF4J 2.x → Log4j 2; used when choosing Log4j Core as the backend. |
| **logback-classic** | Provides an SLF4J provider and the Logback backend; this is not a JUL bridge. |

For example, if your program and libraries use SLF4J but the desired backend is Log4j 2, the proper pipeline is **SLF4J API → log4j-slf4j2-impl → Log4j Core**. In this pipeline, do not add `logback-classic` as a second backend.

**Do not combine `log4j-to-slf4j` with `log4j-slf4j2-impl` in the same runtime pipeline.** One forwards the Log4j API to SLF4J, while the other forwards SLF4J back to Log4j 2, creating an invalid forwarding loop. Likewise, for other bridges, always verify the direction before adding dependencies.

If you want JUL to route through SLF4J, merely adding the `jul-to-slf4j` JAR is not enough to redirect all JUL events automatically. You need to install the bridge handler into JUL, consider removing old JUL handlers, and evaluate the conversion overhead at verbose log levels. In many frameworks, this is already set up for you; do not manually install it on top of the framework's configuration.

In an application that uses only JUL or already has a single matching API/backend, **no bridge is needed**.

## 7. Choosing the Right Backend for Your Project Type

- **Small Java SE applications needing only basic logging:** JUL is built into the JDK, has minimal dependencies, and is sufficient with `ConsoleHandler`/`FileHandler` and `logging.properties`.
- **Applications with many libraries or needing a swappable backend:** use SLF4J as the common facade and choose **one** compatible provider/backend for your deployment environment, such as Logback or Log4j 2.
- **Projects using a framework with pre-configured logging:** prefer the framework's built-in configuration. Check the classpath before adding backends or bridges; many starters already pull in the required dependencies.
- **Shared libraries:** depend on the chosen API/facade and do not force every application to use a specific backend unless there is a clear design reason.

Configuration file names also depend on the backend: **logging.properties** is typically used for JUL; **logback.xml** for Logback; **log4j2.xml** for Log4j 2. A `logback.xml` file cannot configure plain JUL, and switching backends usually entails changing the configuration file.

## 8. Common Issues and How to Check Them

| Symptom | Common Cause | How to Check or Fix |
| --- | --- | --- |
| Calling `LOG.info(...)` produces no output | Missing SLF4J provider, level higher than INFO, dropped by filter, or output goes elsewhere | Check startup warnings, runtime classpath, root/logger levels, appenders, and stdout/stderr. |
| SLF4J reports no provider found | Only `slf4j-api` is present, or an incompatible implementation/binding is on the classpath | Choose a provider matching the SLF4J major version in use; check runtime dependencies. |
| SLF4J reports multiple providers | More than one backend/provider is present on the runtime classpath | Keep only the chosen provider and exclude the dependency pulling in the extra one. |
| A log line appears twice | JUL still uses parent handlers; logger/appender additivity; or the same event traverses two bridge paths | Check parent loggers, handler/appender lists, bridge configuration, and event routing. |
| `DEBUG` does not appear even after configuring Logger | Backend or appender still has a higher threshold; wrong config file edited | Verify the exact API/backend, effective level, and the config file actually loaded at runtime. |
| JUL logs do not reach Logback | JUL and SLF4J are separate APIs; JUL bridge is not installed or enabled | If centralized output is truly needed, configure `jul-to-slf4j` in the right direction and avoid duplicate handlers. |
| Runtime errors after switching backends | Missing runtime artifact, API/provider version conflict, or a bridge loop | Inspect the dependency tree and startup messages; fix the classpath rather than only changing Logger imports. |

With Gradle, you can inspect the dependencies actually participating at runtime:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency slf4j --configuration runtimeClasspath
~~~

These commands only work in a Gradle project with a Wrapper and the corresponding configuration. When reading the output, look for **slf4j-api**, the provider (such as **logback-classic** or **log4j-slf4j2-impl**), and any bridges; watch for transitive dependencies that pull in an unexpected backend.

## 9. Best Practices and Key Takeaways

When adding logging to a Java class, follow this order: **identify the API → choose the backend at the application level → configure levels and handlers/appenders → verify actual output**. Do not choose an implementation based solely on the imported Logger type name.

For frequently executed task logs, use appropriate levels (`INFO` for operational milestones, `DEBUG`/`TRACE` for detailed diagnostic information) and prefer parameterized messages to avoid costly string concatenation when the level is disabled. When logging errors, pass the exception using the method supported by your API so the backend can print the stack trace. Avoid putting passwords, tokens, or sensitive data into logs regardless of which backend is used.

**Remember:** A Logger is the entry point that creates events; a facade provides a common calling interface; a provider/adapter connects systems when needed; and the backend, filters, and handlers/appenders determine the path and how logs are emitted. A clear logging pipeline helps you control log levels, storage locations, and avoid dependency conflicts.
