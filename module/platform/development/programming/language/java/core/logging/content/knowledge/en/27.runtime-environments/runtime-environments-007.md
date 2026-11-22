# System Properties in Java Logging

## 1. What Is a System Property and How Does It Relate to Logging?

A **Java system property** is a string key–value pair belonging to **a single JVM process**. Applications and libraries can read these values using `System.getProperty(...)`. When starting a program, they can be supplied via the `-Dkey=value` JVM option:

```bash
java -Dapp.log.level=DEBUG -jar application.jar
```

In the example above, `app.log.level` is an **application-defined** key. Java does not automatically enable DEBUG just because a property with that name is present; the application code or logging framework must actively read and use it.

System properties are useful for logging because development, test, staging, and production environments often require different log levels, appender configurations, paths, or formats without recompiling code. Some logging backends have **special keys** that they support out of the box; others are custom keys used for interpolation in configuration files.

Distinguish between three common configuration sources:

| Source | How It Is Provided | How Java Reads It | Example |
| --- | --- | --- | --- |
| JVM system property | `-Dkey=value` when running the JVM or `System.setProperty(...)` in-process | `System.getProperty("key")` | `-Djava.util.logging.config.file=logging.properties` |
| OS environment variable | Set in the process environment before the JVM runs | `System.getenv("KEY")` | `LOG_LEVEL=DEBUG` |
| Application argument | Placed after the class name or `-jar app.jar` | `main(String[] args)` or parsed by the framework | `--logging.level.root=DEBUG` in Spring Boot |

These three sources are **distinct**; a framework may combine them into a unified configuration model, but not every `--flag` or environment variable should be treated as a system property. A system property belongs to the current JVM and does not automatically change system-wide settings or other JVMs.

## 2. The `-D` Syntax and When Values Are Provided

Basic form:

```text
java [JVM options, including -Dkey=value] <main-class> [application arguments]
java [JVM options, including -Dkey=value] -jar application.jar [application arguments]
```

Correct examples:

```bash
java -Ddemo.log.level=FINE SystemPropertyLoggingDemo
java -Dlogging.config=classpath:logback-spring.xml -Dlogging.level.root=INFO -jar application.jar
```

In the second command, `logging.config` and `logging.level.root` only take effect if the program is launched with a framework that understands those keys, such as Spring Boot in the appropriate setup.

Commonly confused example:

```bash
java SystemPropertyLoggingDemo -Ddemo.log.level=FINE
```

Here, `-Ddemo.log.level=FINE` appears **after the class name**, so it is only an element of `args` passed to `main` and is not interpreted by the JVM as a system property. Similarly, `java -jar application.jar -Dlogging.level.root=DEBUG` passes the `-D...` string to the application and does not create a JVM property.

If a value contains spaces or special characters, quote it appropriately for your shell. In Windows PowerShell, syntax like `java "-Ddemo.log.level=FINE" SystemPropertyLoggingDemo` makes it clear that this is a single JVM argument. For paths, use actual paths suited to the environment and keep the current working directory in mind when using relative paths.

A few important points:

- `-Dname=value` creates/sets the value before the program initializes; suitable for backends that read configuration at startup.
- `-Dname` typically sets the value to an empty string, though you should verify whether the application accepts an empty string.
- Multiple `-D` options can appear on the same command; avoid declaring duplicate keys as this can cause confusion about the value's source.
- Java's `System.getProperty("app.log.level")` returns `null` when the key does not exist; the overload `System.getProperty("app.log.level", "INFO")` allows specifying a default.
- `System.setProperty("app.log.level", "DEBUG")` changes the value in the running JVM, but **does not guarantee that the logging backend will automatically reload its configuration**.

## 3. Java 17: Reading a System Property Manually to Set the Log Level

The first example uses **`java.util.logging` (JUL)** built into the JDK. The program reads a custom-defined property, applies the level to a logger, and writes records to `stderr` with a deterministic formatter.

Create the file **`SystemPropertyLoggingDemo.java`**:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class SystemPropertyLoggingDemo {
    public static void main(String[] args) {
        String configured = System.getProperty("demo.log.level", "INFO");
        Level level = Level.parse(configured);

        Logger logger = Logger.getLogger("demo.runtime");
        logger.setUseParentHandlers(false);
        logger.setLevel(level);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + ": "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        logger.addHandler(console);
        try {
            logger.fine("detail");
            logger.info("ready");
            logger.warning("retry");
        } finally {
            console.flush();
            logger.removeHandler(console);
            console.close();
        }
    }
}
```

Compile with JDK 17+:

```bash
javac SystemPropertyLoggingDemo.java
```

Run **without passing `-D`**:

```bash
java SystemPropertyLoggingDemo
```

Output on **`stderr`**:

```text
INFO: ready
WARNING: retry
```

Run with level `FINE`:

```bash
java -Ddemo.log.level=FINE SystemPropertyLoggingDemo
```

Output on **`stderr`**:

```text
FINE: detail
INFO: ready
WARNING: retry
```

Run with level `WARNING`:

```bash
java -Ddemo.log.level=WARNING SystemPropertyLoggingDemo
```

Output on **`stderr`**:

```text
WARNING: retry
```

The commands above do not actively write data to `stdout`. JUL's `ConsoleHandler` writes to `System.err`; terminals typically display both `stdout` and `stderr`, so you need to distinguish between them when piping or redirecting.

Explanation:

1. `System.getProperty("demo.log.level", "INFO")` retrieves the configuration at call time, defaulting to `INFO`.
2. `Level.parse(...)` understands JUL values such as `FINE`, `INFO`, `WARNING`, `SEVERE`, `ALL`, and `OFF`. `DEBUG` **is not a standard JUL level name**; `Level.parse("DEBUG")` is invalid unless the application defines a custom level.
3. `logger.setLevel(level)` sets the logger threshold; `console.setLevel(Level.ALL)` ensures the handler does not block events already accepted by the logger.
4. `setUseParentHandlers(false)` avoids writing an extra copy through the default root handler.
5. `Formatter` keeps the demonstration output deterministic, independent of `SimpleFormatter`'s timestamp or locale.
6. `finally` removes and closes the handler created by the example. Do not close handlers owned by frameworks or other parts of an application.

If you pass `-Ddemo.log.level=UNKNOWN`, `Level.parse` will throw `IllegalArgumentException` before the logger is configured. Production applications should decide explicitly: reject invalid configuration or fall back to a default with a warning signal; never silently coerce arbitrary strings into valid levels.

## 4. Built-in JUL System Property: `java.util.logging.config.file`

JUL has a mechanism to read a `logging.properties` configuration file via **`LogManager`**. You do not need to write Java code to read `-Djava.util.logging.config.file`: this key is understood by the JDK's JUL initialization mechanism.

Create the file **`logging.properties`** in the working directory:

```properties
handlers=java.util.logging.ConsoleHandler
.level=INFO

java.util.logging.ConsoleHandler.level=FINE
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.SimpleFormatter.format=%4$s: %5$s%6$s%n

demo.file.level=FINE
```

Meaning:

- `handlers`: the root logger's handlers in the JUL configuration.
- `.level=INFO`: the root logger's level.
- `java.util.logging.ConsoleHandler.level=FINE`: the handler accepts logs from `FINE` and above; if the handler remains at `INFO`, `FINE` logs from child loggers may be blocked.
- `java.util.logging.ConsoleHandler.formatter`: the formatter class name.
- `java.util.logging.SimpleFormatter.format`: format string using the arguments supported by `SimpleFormatter` documentation. `%4$s` is the level, `%5$s` is the message, `%6$s` is the exception text (if any), and `%n` is a newline.
- `demo.file.level=FINE`: the level for the logger named `demo.file`.

Save the program **`JulFileConfigDemo.java`**:

```java
import java.util.logging.Logger;

public class JulFileConfigDemo {
    private static final Logger LOG = Logger.getLogger("demo.file");

    public static void main(String[] args) {
        LOG.fine("detail");
        LOG.info("ready");
        LOG.warning("slow sink");
    }
}
```

Compile and run on JDK 17+:

```bash
javac JulFileConfigDemo.java
java -Djava.util.logging.config.file=logging.properties JulFileConfigDemo
```

Lines written to **`stderr`** when JUL reads the configuration file above properly:

```text
FINE: detail
INFO: ready
WARNING: slow sink
```

How it works:

1. The JVM receives the `java.util.logging.config.file` system property before loading the application class.
2. JUL's `LogManager` reads the file configuration during its initialization.
3. Logger `demo.file` has level `FINE`, and the root handler also accepts `FINE`.
4. `SimpleFormatter` uses the specified format, so the output does not include timestamps.

`java.util.logging.config.file` is **the path to a JUL configuration file**, not a logger name. If the path is wrong, the file is unreadable, or its contents have errors, logging may run with an unexpected configuration; check the path, current working directory, read permissions, initialization messages, and test events.

You can use an absolute path when running in a container or service to avoid depending on the `working directory`:

```bash
java -Djava.util.logging.config.file=/opt/app/conf/logging.properties -jar application.jar
```

This command only matters if `application.jar` uses JUL or an appropriate bridge; if the application's loggers are handled by another backend, changing the JUL file alone may not control those loggers.

### 4.1. Other Notable JUL System Properties

- `java.util.logging.config.class`: instructs JUL to use a custom configuration class via `LogManager`; this is an advanced approach requiring the class to be available at startup and a clear understanding of initialization order.
- `java.util.logging.SimpleFormatter.format`: provides the format string for `SimpleFormatter`; can be used directly as a system property. The syntax contains `$` and `%`, so it requires careful shell quoting; using `logging.properties` is usually easier to manage.
- `java.util.logging.config.file`: selects the configuration file at JUL initialization; **setting the property after JUL has already been configured does not automatically trigger a reload**.

Do not confuse `java.util.logging.ConsoleHandler.level` in `logging.properties` with a `-D...` property guaranteed to be read directly by JUL at any time. Many JUL configuration lines are **properties in a file read by LogManager**—not all of them are special JVM system properties.

## 5. System Properties in Logback and SLF4J

In projects using **SLF4J + Logback Classic**, `org.slf4j.Logger` is used to write logs, while **Logback** determines levels, appenders, and patterns. Logback has a commonly used system property:

```text
logback.configurationFile
```

Example of launching an application packaged and configured to use Logback:

```bash
java -Dlogback.configurationFile=/opt/app/conf/logback.xml -jar application.jar
```

This file must exist, be readable, and match the running Logback version. The `logback.configurationFile` property must be provided **before Logback initializes itself** if you want to change where it loads configuration at startup.

A complete, minimal `logback.xml` example:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders" level="${app.log.level:-INFO}"/>

    <root level="WARN">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Run command:

```bash
java -Dlogback.configurationFile=/opt/app/conf/logback.xml -Dapp.log.level=DEBUG -jar application.jar
```

When Logback loads the file above and interpolates the property successfully:

- `app.log.level` is a **custom key we chose**, used by the `${app.log.level:-INFO}` expression.
- `:-INFO` is the fallback value in Logback's variable substitution syntax when no defined value is found.
- Logger `com.example.orders` has level `DEBUG`; root has level `WARN`.
- Child loggers have **additivity** enabled by default, so events accepted by this logger can propagate to the root appender. Thus, `DEBUG` can still appear via the `STDOUT` appender, depending on any other configured filters. The root level does not necessarily re-filter events already accepted by a child logger before passing them to appenders.
- This is **Logback** configuration; you cannot copy the exact property names across all logging backends.

You cannot run the XML example standalone with just `java` without an application, dependencies, and a valid main class or JAR. Nor is there a fixed `stdout` output, since messages and timestamps come from the actual application.

### 5.1. Do Not Mistake SLF4J for Having a Unified System Property Across All Backends

SLF4J is a facade, so `-Dapp.log.level=DEBUG` on its own **does not force** any SLF4J provider to change its level. It only takes effect when Logback, Log4j 2, Spring Boot, or the application itself reads that property.

If an application only has the SLF4J API without a suitable provider/backend, Logback configuration will not take effect as expected. Check your actual dependencies and provider, and avoid loading multiple incompatible providers.

## 6. Log4j 2: Selecting a Configuration File via JVM Property

In applications using Log4j 2, the common property for specifying the configuration source is:

```bash
java -Dlog4j2.configurationFile=/opt/app/conf/log4j2.xml -jar application.jar
```

This key is specific to **Log4j 2**. Its value points to a configuration accessible by the Log4j 2 version in use. It differs from `logback.configurationFile` and `java.util.logging.config.file`.

To use a system property's value **inside** a Log4j 2 configuration, the framework provides a property lookup mechanism according to Log4j 2's syntax and version. A conceptual example in XML configuration supporting lookups:

```xml
<Root level="${sys:app.log.level:-INFO}">
    <AppenderRef ref="Console"/>
</Root>
```

This is a **configuration snippet**, valid only in the proper place within a Log4j 2 file that has an appender named `Console` and a version supporting that substitution syntax. Do not use Log4j 2's `<Root>` as Logback's `<root>` element; their schemas and attribute names differ.

In systems using auto-reload, a new configuration may overwrite levels changed at runtime. When using system properties to determine startup configuration, know clearly **whether configuration is reloaded** and how runtime changes are managed.

## 7. Spring Boot: System Properties Flow Through Environment

Spring Boot has its own application configuration system. A JVM system property typically becomes **a configuration source in the Spring Environment** and can be used to configure logging. Example for a packaged Spring Boot application:

```bash
java -Dlogging.level.root=INFO -Dlogging.level.com.example.payment=DEBUG -jar application.jar
```

According to how Spring Boot maps the corresponding logging properties:

- `logging.level.root=INFO`: the root log level.
- `logging.level.com.example.payment=DEBUG`: the log level for the corresponding logger/package.
- `logging.file.name=/var/log/app/application.log`: example specifying a log file name if the backend configuration and deployment environment are appropriate.
- `logging.config=classpath:logback-spring.xml`: example specifying the logging configuration location; the resource must actually exist on the classpath and be compatible with the backend.

You can also pass **application arguments**:

```bash
java -jar application.jar --logging.level.root=INFO --logging.level.com.example.payment=DEBUG
```

In Spring Boot, the `--logging.level...` syntax is parsed as an application configuration source; it is **not** a JVM system property created by `-D`. Which source takes higher precedence depends on the configuration order of the framework/version and any other overrides the application uses. Avoid declaring the same key with conflicting values across multiple sources.

In Spring Boot, logging is typically initialized **very early**. Calling `System.setProperty("logging.level.root","DEBUG")` after the application is already running does not guarantee that the logging system will change levels immediately; you need a runtime configuration management mechanism supported by the Boot/backend version. In particular, `logback-spring.xml` is a Spring Boot convention, not a standard JUL configuration file.

## 8. How Does `System.getProperty` Differ from `System.getenv`?

Standalone Java 17 example, saved as **`LoggingPropertySourcesDemo.java`**:

```java
public class LoggingPropertySourcesDemo {
    public static void main(String[] args) {
        String jvmLevel = System.getProperty("app.log.level", "UNSET");
        String envLevel = System.getenv("APP_LOG_LEVEL");

        System.out.println("JVM property: " + jvmLevel);
        System.out.println("Environment defined: " + (envLevel != null));
    }
}
```

Compile:

```bash
javac LoggingPropertySourcesDemo.java
```

If the runtime environment **does not have** `APP_LOG_LEVEL` and you run:

```bash
java -Dapp.log.level=DEBUG LoggingPropertySourcesDemo
```

Then `stdout` is:

```text
JVM property: DEBUG
Environment defined: false
```

If the OS has `APP_LOG_LEVEL` set, the `Environment defined` line becomes `true`, while the JVM property value remains `DEBUG`. The example only prints whether the environment variable is present or absent to avoid assuming a specific OS setup.

A system may define its own precedence policy, such as: JVM property `app.log.level` → environment variable `APP_LOG_LEVEL` → default value `INFO`. This is an **application-written convention**; the JVM does not automatically map these two names to one another.

`System.setProperty` modifies the properties table in the current JVM; `System.getenv` reads the process environment, and there is no equivalent standard Java API to universally mutate the process-wide environment.

## 9. Initialization, Caching, and Changing Logging at Runtime

Two questions should be separated:

1. **What value does the property currently hold?** `System.getProperty("app.log.level")` answers this at read time.
2. **What level/config is the logging backend currently applying?** This can only be known by inspecting the backend's state and active configuration.

For example:

```java
System.setProperty("app.log.level", "DEBUG");
```

This statement updates the property, but the logger may have already read `INFO` at startup. There is no general rule requiring backends to re-call `System.getProperty` on every log event.

Actual ways to change levels depend on the framework:

- **JUL:** `logger.setLevel(Level.FINE)` directly affects the active logger; `LogManager.readConfiguration(...)` can reload JUL configuration broadly, so you must understand its impact on other handlers.
- **Logback:** change the level on `ch.qos.logback.classic.Logger` or reload the configuration via Logback's API/lifecycle.
- **Log4j 2:** use a supported configuration API such as `Configurator`, or change the configuration source via the backend's reload mechanism.
- **Spring Boot:** manage log levels through configuration and the appropriate runtime mechanism (if enabled), avoiding arbitrary mutations of system properties inside business controllers.

Because system properties are **shared state for the entire JVM**, multiple threads and libraries can read or modify them. Do not use `System.setProperty` for a specific request to store a correlation ID: the value will not be thread-isolated and can mix data across requests. Use a logging context/MDC or trace propagation mechanism designed for logging, and clean up the context according to the lifecycle.

When temporarily updating a log level, save the original level, limit the duration, coordinate concurrent changes, and safely restore the previous state. Changing the root logger in a multi-component environment can cause log spikes, increase I/O overhead, or expose debug data.

## 10. Debugging When a System Property Does Not Affect Logs

When `-D` is passed but logs remain at the old level, check in order:

1. **Argument position:** `-D` must be in the JVM options section, before the main class name or before `-jar`.
2. **Correct key name:** `java.util.logging.config.file` is for JUL, `logback.configurationFile` for Logback, `log4j2.configurationFile` for Log4j 2, and `logging.level.*` is a Spring Boot convention. Keys do not substitute for one another.
3. **Correct active backend:** SLF4J may be wired to Logback or another backend; a JUL file does not necessarily control loggers through another provider.
4. **Whether code/configuration reads the property:** a custom key `app.log.level` only works if consumed by code or a substitution mechanism.
5. **Whether it was set before logger/backend initialization:** calling `System.setProperty` too late usually does not affect configuration that has already been loaded.
6. **Whether the value is valid:** JUL uses `FINE`, `WARNING`, `SEVERE`; Logback typically uses `DEBUG`, `WARN`, `ERROR`. Do not pass level names arbitrarily between frameworks.
7. **Whether the path or resource exists:** if the config file is unreadable or malformed, the backend may fall back and emit startup logs on another channel.
8. **Whether the level is blocked at the sink:** if a logger enables `FINE` but a JUL handler is set to `INFO`, `FINE` will still not appear.
9. **Whether another configuration source overrides it:** a config file, environment variable, framework bootstrap, or reload may determine the final value.
10. **Whether logs are actually emitted and collected:** check package loggers, filters, appenders, `stdout`/`stderr`, async queues, and collectors.

When you need to verify a specific property in code, you can read it in a controlled manner:

```java
String level = System.getProperty("app.log.level", "<unset>");
System.out.println("Configured level property = " + level);
```

This is an **illustrative code snippet**, not a standalone program. Only print properties confirmed to be non-sensitive. Avoid dumping all of `System.getProperties()` into logs: it may contain internal paths, system details, or secrets if the application passes credentials via `-D`.

## 11. Security and Operations

- **Do not pass passwords/tokens via `-D` if a proper secrets management option is available.** JVM arguments can appear in process inspection tools, diagnostic output, and command history.
- **Do not use system properties as a store for request/thread state.** They are JVM-scoped and can be overwritten by other threads.
- **Do not trust arbitrary input for logging file paths.** Validate paths, read/write permissions, and allowed directories before loading external configuration.
- **Do not allow anyone to enable TRACE/DEBUG in production indefinitely.** Verbose logs can increase I/O, leak sensitive information, and cause backpressure in async logging.
- **Tie runtime changes to authorization and auditing.** When multiple people change levels concurrently, rollback rules must be clear.
- **Do not rely on system properties as persistent state.** Values set with `System.setProperty` are lost when the JVM exits; configuration must be supplied again when starting a new process.
- **Distinguish JVM values from backend state.** Diagnose the property value, the loaded configuration file, the effective logger level, and the actual handlers/appenders.

## 12. Real-World Scenarios

**Scenario A — Running a small Java tool:** use `-Ddemo.log.level=FINE` and `System.getProperty` in code as in the first example. This is a straightforward way to adjust log levels from the launch command without adding dependencies.

**Scenario B — Using JUL in a service:** create `logging.properties` and pass `-Djava.util.logging.config.file=...` before the process starts. Check logger levels, handler levels, format, and file location. When deploying multiple instances, each instance receives system properties from its own launch command.

**Scenario C — Using SLF4J + Logback:** specify `-Dlogback.configurationFile=...` and interpolate custom properties in `logback.xml`. This lets the same artifact run with different logging levels across environments.

**Scenario D — Using Spring Boot:** use `-Dlogging.level.com.example.payment=DEBUG` or the configuration source `--logging.level.com.example.payment=DEBUG` according to Spring Boot's configuration model. When runtime changes are needed, use the appropriate management/logging system interface instead of assuming `System.setProperty` triggers a reload.

**Core principle:** `-D` supplies a configuration value to the JVM, but whether it changes logging depends on **the right key, the right backend, the right initialization timing, and the right level/filter at the log output**. Checking these four factors resolves most system-property logging configuration issues.
