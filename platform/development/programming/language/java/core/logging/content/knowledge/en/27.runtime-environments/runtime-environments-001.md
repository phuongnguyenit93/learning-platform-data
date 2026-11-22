# Development Configuration for Java Core Logging

## 1. Goals of Logging in the Development Environment

**Development** is the environment for coding, testing, and local debugging. The logging configuration here needs to answer quickly: *which code ran, at what time, on which thread, with what identifying data, and why did an error occur?* The goal is to clearly observe the execution flow without having to scatter `System.out.println(...)` statements everywhere.

A useful development configuration should provide:

- **Readable console output:** timestamp, log level, thread, logger/class name, message, and stack trace when an exception occurs.
- **Selective log levels:** root is typically set to `INFO`; enable `DEBUG` for the application package under investigation, and enable `TRACE` only in a very narrow scope when truly needed.
- **Easy switching by environment:** detailed logs in `dev`, while avoiding accidentally leaking this level into `test`/`staging`/`production`.
- **Correlation across logs:** include `requestId`/`traceId`/`jobId` to link events belonging to the same request or task.
- **No exposure of sensitive data:** dev still uses real data in some cases; do not log passwords, tokens, cookies, API keys, or entire arbitrary payloads.
- **No unnecessary noise:** avoid duplicate logs, extremely long lines, third-party libraries emitting massive `DEBUG` output, and log files filling up the disk.

In Java, the **logging API** is how code emits events (for example, SLF4J or `java.util.logging`), while the **backend/handler/appender** decides filtering, formatting, and output destination. The configuration file must match the backend actually present on the classpath. For example, `logback.xml` will not control an application that only uses `java.util.logging` without a bridge.

## 2. Choosing the Right Log Level During Development

With SLF4J/Logback and Log4j 2, the standard order is:

~~~text
TRACE < DEBUG < INFO < WARN < ERROR
~~~

| Level | When to use in development | Example |
| --- | --- | --- |
| `ERROR` | An operation failed and needs handling | Failed to write data; attach exception |
| `WARN` | Recoverable anomaly, unexpected outcome | Retry, fallback, or missing configuration |
| `INFO` | Meaningful business or lifecycle milestone | Startup complete, job received, order completed |
| `DEBUG` | Details for root-cause investigation | Cache miss, conditional branch, truncated parameters |
| `TRACE` | Very fine-grained execution flow, potentially high volume | Stepping through a parser/algorithm |

If root is `INFO` and logger `com.example.checkout` is `DEBUG`, classes in the `com.example.checkout` package can emit `DEBUG` logs; other packages still typically show only `INFO` and above. A child logger inherits the level of its nearest configured ancestor if it does not declare its own level.

**Distinguish two concepts:**

1. **Logger level** decides whether an event is created/propagated, based on the logger name and inheritance hierarchy.
2. **Appender/handler level or filter** can filter further afterward. Therefore, raising a logger to `DEBUG` is **not enough** if the `ConsoleHandler`/appender still blocks `DEBUG`.

With `java.util.logging` (JUL), the corresponding level names are `FINE`, `FINER`, `FINEST`, `INFO`, `WARNING`, `SEVERE`. Do not confuse `FINE` with a `DEBUG` constant that does not exist in JUL.

## 3. Standalone Logback: Console Configuration for Development

**Example scope:** a Java application using **SLF4J API + Logback Classic**. Compatible dependencies must be on the classpath; the XML below does not add libraries on its own. Create **`logback-dev.xml`**:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger{36} requestId=%X{requestId} - %msg%n%ex</pattern>
        </encoder>
    </appender>

    <!-- Enable DEBUG only for packages you own -->
    <logger name="com.example" level="DEBUG"/>

    <!-- Verbose libraries can be lowered to WARN -->
    <logger name="org.apache.http" level="WARN"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

For a standalone Java application with SLF4J + Logback, you can select this file at startup:

~~~bash
java -Dlogback.configurationFile=logback-dev.xml -cp "..." com.example.Main
~~~

`...` represents the **classpath provided by your build tool/actual application**; this command only illustrates how to specify the configuration file and is not a standalone runnable command. With Gradle/Maven, how you pass VM options depends on the task/plugin/IDE. Do not confuse JVM `-D...` options (before the main class or `-jar`) with application arguments.

Parts to understand in the XML:

- `ConsoleAppender` outputs logs to the console, suitable when running from an IDE/terminal. `encoder` formats them as UTF-8 strings.
- `%d{HH:mm:ss.SSS}` is the local timestamp (hours:minutes:seconds.milliseconds), `[%thread]` is the current thread, `%-5level` is the log level, `%logger{36}` shortens the logger name, `%msg` is the message, and `%n` is a newline.
- `%X{requestId}` retrieves the request ID from MDC if present. The field may be empty if not set; the pattern configuration **does not automatically generate or propagate** the request ID.
- `%ex` displays the exception/stack trace when the log record has a throwable. You do not need to manually concatenate `exception.toString()` and lose the stack trace.
- `<logger name="com.example" level="DEBUG"/>` raises the level only for the application namespace. Root has a console appender to also receive logs enabled on child loggers.

Example with SLF4J code in a class (library-dependent snippet, **not a standalone Java program**):

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

final class CheckoutService {
    private static final Logger LOG =
            LoggerFactory.getLogger(CheckoutService.class);

    void submit(String requestId, String orderId) {
        LOG.debug("event=submit_started requestId={} orderId={}",
                requestId, orderId);
        try {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("orderId is blank");
            }
            LOG.info("event=order_submitted requestId={} orderId={}",
                    requestId, orderId);
        } catch (RuntimeException e) {
            LOG.error("event=order_submit_failed requestId={} orderId={}",
                    requestId, orderId, e);
            throw e;
        }
    }
}
~~~

This pattern uses SLF4J's `{}` placeholders and passes the exception as the **last argument** so the backend can log the stack trace. `requestId` is passed explicitly in the log statement; if you want to use `%X{requestId}` in the pattern, the application must set the corresponding MDC entry (see later section). Choose one place responsible for logging the stack trace: do not re-log the entire exception multiple times across caller layers and cause duplicate logs.

### Logger Inheritance and Duplicate Log Lines

Child loggers in Logback typically have `additivity=true`: events pass through appenders attached directly to them as well as appenders of ancestor loggers. If `CONSOLE` is already attached to `root`, you **do not need** to attach the same appender to `com.example`. Attaching it in both places can cause one event to print two lines. Only use `additivity=false` when intentionally isolating a logger branch to its own appender; in that case, make sure that branch has all required appenders attached, otherwise output may be lost.

### Loading Configuration by Environment

There are two easy-to-control approaches:

1. **Plain Java applications:** keep a separate file such as `logback-dev.xml` and specify it via a VM option in the dev run configuration; production uses a different file/values.
2. **Spring Boot:** prefer `application-dev.properties` or `application-dev.yml` to change `logging.level.*` by profile; use `logback-spring.xml` if you need custom layouts/appenders with Spring extensions support.

Do not leave a dev configuration file with root `DEBUG` in the production runtime without a reliable environment selection mechanism.

## 4. Spring Boot: Enabling Log Levels by Development Profile

If the module uses **Spring Boot with default Logback**, place the files under `src/main/resources`:

**`application.properties`** — baseline values for all environments:

~~~properties
logging.level.root=INFO
logging.level.com.example=INFO
logging.level.org.springframework=WARN
~~~

**`application-dev.properties`** — applies only when the `dev` profile is active:

~~~properties
logging.level.root=INFO
logging.level.com.example=DEBUG
logging.level.org.springframework.web=INFO
logging.level.org.hibernate.SQL=WARN
~~~

Run the built Spring Boot application with the dev profile:

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

`app.jar` represents the built executable JAR of your application, not a pre-existing sample file. Alternatively, set the `SPRING_PROFILES_ACTIVE=dev` environment variable in your IDE/container run configuration. Do not put `spring.profiles.active` inside `application-dev.properties` itself and expect it to activate its own file; the profile must be selected from a valid configuration source outside the profile-specific document.

**Precedence order:** Spring Boot loads the base configuration and the configurations applicable to active profiles, then applies property source precedence such as command-line/environment; a `logging.level.com.example=DEBUG` value in the dev profile can override the base `INFO` value. When multiple profiles are active simultaneously, verify the application's ordering policy.

When you only need to adjust log levels, `logging.level.*` is the most maintainable option. Avoid configuring complex roots/appenders in XML while also setting many level overrides across multiple sources without knowing the final effective value.

If you need richer layouts, colors, or specialized filters, use **`logback-spring.xml`** so Spring Boot can manage logging early and support extensions such as `<springProfile>`. A traditional `logback.xml` file does not support Spring Boot extensions the way `logback-spring.xml` does. Filenames and configuration capabilities also depend on the backend in use (Logback or Log4j 2); do not apply Logback rules to every backend.

### Choosing Between Console and File During Development

Usually **console is enough** for local runs and IDE debugging: logs appear alongside stdout/stderr without needing to manage file disk usage. Only when you need history longer than the terminal lifecycle should you add `FileAppender`/`RollingFileAppender` with size limits, backup counts, and retention policies. Do not start by writing unbounded files into the project directory or committing log files to Git.

You can use ANSI colors to distinguish log levels more easily in the terminal, though colors depend on the IDE/terminal/backend; logs sent to text/JSON pipelines should avoid escape codes if unnecessary. Log time, timezone, and timestamp format should be consistent when correlating multiple applications.

## 5. Standalone Dependency-Free Java 17 Example: JUL with a Dev Config File

This example uses `java.util.logging` built into the JDK to demonstrate how **root level**, **logger level**, and **handler level** together affect output. It does not use SLF4J/Logback; the `FINE`/`WARNING` levels correspond in purpose to `DEBUG`/`WARN` in the examples above.

Create **`logging-dev.properties`** in the working directory:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=ALL
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.ConsoleHandler.encoding=UTF-8
java.util.logging.SimpleFormatter.format=%4$s [%3$s] %5$s%6$s%n

com.example.catalog.level=FINE
~~~

Here:

- `.level=INFO` is the default level of the root logger;
- `com.example.catalog.level=FINE` enables detailed logging on this logger;
- `java.util.logging.ConsoleHandler.level=ALL` ensures the handler does not block `FINE` events already allowed by the child logger;
- `SimpleFormatter.format` specifies the level, logger name, message, and throwable. This console configuration writes to **stderr**, unlike `System.out.println`.

Create **`DevelopmentLoggingDemo.java`**:

~~~java
import java.util.logging.Level;
import java.util.logging.Logger;

public class DevelopmentLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger("com.example.catalog");

    public static void main(String[] args) {
        LOG.info("event=app_started env=dev");
        LOG.fine("event=cache_miss key=item-42");

        try {
            validate(-1);
        } catch (IllegalArgumentException error) {
            LOG.log(Level.WARNING,
                    "event=validation_rejected requestId=req-42", error);
        }

        System.out.println("demo_done");
    }

    private static void validate(int id) {
        if (id <= 0) {
            throw new IllegalArgumentException("id must be positive");
        }
    }
}
~~~

Compile and run in the directory containing both files:

~~~bash
javac -encoding UTF-8 DevelopmentLoggingDemo.java
java -Djava.util.logging.config.file=logging-dev.properties DevelopmentLoggingDemo
~~~

**Exact stdout** (`System.out` only):

~~~text
demo_done
~~~

JUL log records go to **stderr**. Expected message excerpt (stack trace line numbers depend on how the file is saved):

~~~text
INFO [com.example.catalog] event=app_started env=dev
FINE [com.example.catalog] event=cache_miss key=item-42
WARNING [com.example.catalog] event=validation_rejected requestId=req-42
java.lang.IllegalArgumentException: id must be positive
    at DevelopmentLoggingDemo.validate(...)
    at DevelopmentLoggingDemo.main(...)
~~~

This is an illustrative excerpt of stderr, **not full stdout for exact character-by-character matching**. If you omit the `-Djava.util.logging.config.file=...` VM option, the JVM uses the default logging configuration (or an environment-provided configuration), so `FINE` typically will not appear. If you change `ConsoleHandler.level` from `ALL` to `INFO`, `FINE` events can be filtered out even if the logger allows them; if you change the level of `com.example.catalog` to `INFO`, events are dropped right at the logger.

`java.util.logging.config.file` is a **JDK system property**; Logback will not read `logging-dev.properties` through that mechanism. This helps identify cases where you edit one configuration while the actual application uses a different framework.

## 6. Request ID, Thread, and MDC in Development

For servers handling multiple concurrent requests, logs with only timestamp and thread are not enough. Thread names can be reused across many requests. Dedicated identifiers (`requestId`, `traceId`, `jobId`) help filter related events.

With **SLF4J MDC** and an MDC-capable backend, you can set the request ID for the handling scope and clear it in `finally`:

~~~java
import org.slf4j.MDC;

// Illustrative snippet inside a request handler, not a standalone program.
static void withRequestId(String requestId, Runnable action) {
    try {
        MDC.put("requestId", requestId);
        action.run();
    } finally {
        MDC.remove("requestId");
    }
}
~~~

The `%X{requestId}` pattern in Logback outputs the MDC value on the **thread currently logging**. MDC does not automatically propagate from the submitting thread to worker threads in `ExecutorService`/`CompletableFuture`; you must propagate context intentionally and clean it up after each task to avoid leaking data from a previous request. If a flow has nested contexts, instead of blindly removing, save and restore the previous value. Do not log user-supplied IDs without bounding their length or stripping control characters that can cause log injection.

## 7. Keeping Dev Logs Detailed Yet Safe

Several mistakes are very easy to make when `DEBUG` is enabled:

- **Data leaks:** method arguments, URL queries, `Authorization` headers, cookies, passwords, OTPs, tokens, personal data, connection strings containing secrets, or full request/response bodies. Log only selected fields, and mask/redact before passing them to the logger.
- **Message noise:** setting `logging.level.root=DEBUG` causes every library to emit massive logs. Keep root at `INFO` and raise only the specific namespace you are investigating.
- **Wrong level:** using `ERROR` for every valid user-input error triggers false alarms on dashboards; using `INFO` for every item in a loop can generate huge log volumes.
- **Missing stack trace:** `LOG.error("failed: {}", error.getMessage())` only logs the message. To investigate exceptions, pass the exception object per the appropriate API, e.g. `LOG.error("failed", error)`.
- **Duplicate logging:** the same throwable gets logged at repository, service, and controller layers; each layer should only add context if truly needed, with one agreed-upon point responsible for logging the error.
- **Expensive string concatenation:** `LOG.debug("data=" + expensiveToString())` computes the string before the backend knows whether `DEBUG` will be emitted. Use placeholders or check `isDebugEnabled()` for genuinely expensive operations.
- **Unidentified backend:** adding multiple SLF4J providers/bindings or overlapping bridges leads to warnings, duplicate logs, or ignored configurations. Check the dependency tree, startup output, and active backend.
- **Editing the config file with no effect:** the file is not on the classpath, wrong filename, profile not active, IDE not passing VM options, filter/appender blocking the log level, or the application is not using that library.
- **Colors and encoding:** UTF-8 in the logger does not automatically fix a terminal that cannot display Unicode; check file charset, console, and log viewer tools.
- **Debugging only via logs:** when you need to inspect state at an exact point in time, a debugger, unit test, or trace may be more suitable than prolonged `TRACE` logging.

Do not treat the dev environment as a place where logging all data is acceptable by default. Prefer mock data for testing, restrict log read permissions, avoid sharing log screenshots containing real data, and remove sensitive logs before committing.

## 8. How to Verify That Configuration Is Effective

### Quick Check in Order

1. **Identify the actual backend:** does the plain Java app use JUL or SLF4J + Logback/Log4j 2? If it is Spring Boot, check the starter/dependency tree and the active logging configuration file being loaded.
2. **Verify the right environment:** is the `dev` profile selected, are the right VM options passed, and is the file on the expected classpath/path?
3. **Emit two intentional events:** one `INFO` and one `DEBUG`/`FINE` from your own application package. With the example configuration, both appear in dev.
4. **Emit an event from another package:** root `INFO` still filters out `DEBUG` outside the selected package. Recheck the logger hierarchy if behavior differs from expectations.
5. **Verify the format:** timestamp, level, thread, logger, `requestId` (when present), and stack trace when an exception occurs.
6. **Verify no data leaks:** use test data with a fake marker such as `TEST_TOKEN_DO_NOT_LOG` and confirm the backend does not log that value; check headers and stack traces as well.
7. **Check for duplicate logs and performance:** each event appears the expected number of times, and requests are not blocked by excessive logging.
8. **Switch to a non-dev configuration:** prove that `DEBUG`/`FINE` no longer appears broadly and detailed logging is enabled only where permitted.

### Diagnostic Table

| Symptom | Possible Cause | Check / Fix |
| --- | --- | --- |
| `INFO` appears, `DEBUG` does not | Root/package at `INFO`, handler filter at `INFO` | Check both logger and appender/handler |
| No logs at all | Backend not loaded, no appender/handler attached, wrong file | Verify classpath, VM options, and startup diagnostics |
| One event prints twice | Appender attached to both child logger and root, or multiple bridges/providers | Check `additivity` and dependencies |
| Changed `application-dev.properties` but level unchanged | `dev` profile not active or value overridden by higher-priority config source | Check active profiles and effective config |
| `requestId` present in request thread, lost in worker | MDC does not automatically propagate across async boundaries | Capture, pass, set, and clean up context per task |
| Too many logs / slow execution | Root `DEBUG`/`TRACE`, SQL/body logs, or heavy formatting | Lower root to `INFO`, narrow package scope, reduce payload |
| Logs missing stack trace | Only logging exception message | Pass throwable to the logging API |
| Dev logs leaking to production | Dev config on classpath and loaded by default | Separate by profile/VM option, check deployment process |

## 9. Recommended Configuration for Daily Development

An easy baseline to start with is:

~~~text
Output       : console; UTF-8; timestamp, level, thread, logger, requestId
Root level   : INFO
Own package  : DEBUG when investigating; back to INFO when done
Third-party  : INFO or WARN depending on noise level
Exceptions   : with stack trace at clear handling boundaries
Security     : do not log secrets or sensitive full payloads
Environment  : separate dev via profile or VM option
Validation   : check expected logs, unexpected logs, and duplicate logs
~~~

There is no single optimal `DEBUG` configuration for every project: the goal is **just enough information to reproduce an issue** without slowing down the program or obscuring important details. Start from root `INFO`, enable `DEBUG` on the right namespace, and have a process to confirm dev settings do not affect production.

### Official References

- Logback Manual — [configuration and console appender](https://logback.qos.ch/manual/configuration.html), [logger hierarchy, level, and additivity](https://logback.qos.ch/manual/architecture.html).
- Spring Boot — [logging properties and configuration files](https://docs.spring.io/spring-boot/reference/features/logging.html), [profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html).
- Java 17 — [java.util.logging](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html), [ConsoleHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html).