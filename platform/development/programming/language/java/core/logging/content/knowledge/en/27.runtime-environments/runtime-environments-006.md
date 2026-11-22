# Environment Variables in Java Core Logging

## 1. How Do Environment Variables Relate to Logging?

A Java program often runs across multiple environments: developer machines, test machines, staging, production, containers, or CI servers. The same logging code may need different policies:

- **Development:** output detailed logs (`DEBUG`, `TRACE`, or `FINE`, depending on the library) to diagnose issues quickly.
- **Production:** prioritize `INFO`, `WARN`/`WARNING`, or `ERROR`/`SEVERE`; limit log volume and sensitive data.
- **Container:** typically send logs to stdout/stderr for collection by the deployment platform.
- **Temporary incident investigation:** adjust log levels for a group of components with controlled duration and cost.

An **environment variable** is a string key–value pair provided to the Java **process** by the operating system or launch tool. The application reads the variable to select configuration at runtime, rather than modifying source code or recompiling just to change the logging level.

For example, setting `APP_LOG_LEVEL=FINE` before starting the application. If the code or logging backend is configured to read that variable, the application can enable detailed logging. **The JDK itself does not define `APP_LOG_LEVEL` as a standard logging variable.** Setting a variable name does not automatically cause all Loggers to change their level.

The core takeaway: an environment variable is only a **configuration input**; the application, framework, or backend must actively **read and apply** it.

## 2. Distinguishing Environment Variables, JVM System Properties, and Configuration Files

| Mechanism | How It Is Read in Java | Example | Scope |
| --- | --- | --- | --- |
| OS environment variable | `System.getenv("APP_LOG_LEVEL")` | `APP_LOG_LEVEL=INFO` | Provided to the process at startup |
| JVM system property | `System.getProperty("app.log.level")` | `java -Dapp.log.level=FINE ...` | JVM property table, modifiable via API |
| Configuration file | Logging backend or code reads a file | `logging.properties`, `logback.xml`, `log4j2.xml` | Logger rules, handlers/appenders, layouts, filters, paths |
| Framework configuration | Framework aggregates multiple sources | `LOGGING_LEVEL_ROOT=DEBUG` in Spring Boot | Depends on mapping rules, precedence, and framework lifecycle |

**`System.getenv` differs from `System.getProperty`:**

~~~java
String fromEnvironment = System.getenv("APP_LOG_LEVEL");
String fromJvmProperty = System.getProperty("app.log.level");
~~~

These two calls read from two different configuration stores. If a program only calls `System.getenv("APP_LOG_LEVEL")`, the `-Dapp.log.level=FINE` argument **has no effect**, unless the code or framework has a mechanism to read the corresponding system property. Likewise, `System.setProperty("app.log.level", "FINE")` does not modify the operating system's environment variables.

**Scope and timing:** a Java process typically receives a snapshot of the environment when it starts. Setting or modifying a variable in another terminal **after Java has started** does not cause `System.getenv()` in the running process to update automatically. For frameworks with reload support or management APIs, runtime reconfiguration may be possible through **the framework's own mechanism**, not because the process environment changes on its own.

On Linux/macOS, environment variable names are typically **case-sensitive**. On Windows, the OS rules for environment variable names differ; for cross-platform portability, consistently use names like `APP_LOG_LEVEL` and avoid creating variables that differ only by case. Values read from the environment are always strings and must be validated before converting them into enums, levels, or paths.

## 3. Standalone Java 17 Example: Controlling the Logger from the Environment

The example below uses **`java.util.logging` (JUL)**, built into the JDK. We define our own precedence rule:

1. If the JVM property `app.log.level` is present and non-blank, use that value.
2. Otherwise, use the environment variable `APP_LOG_LEVEL` if present and non-blank.
3. If neither is set, default to `INFO`.

To demonstrate accurately, the program accepts four JUL values: `FINE`, `INFO`, `WARNING`, `SEVERE`. For any other value, it reports a configuration error instead of silently guessing a level. Values like `DEBUG` and `ERROR` commonly seen in Logback/Log4j 2 **are not used directly in this JUL example**.

Create the file `EnvLoggingDemo.java`:

~~~java
import java.util.Locale;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class EnvLoggingDemo {
    private static Level configuredLevel() {
        String value = System.getProperty("app.log.level");
        if (value == null || value.isBlank()) {
            value = System.getenv("APP_LOG_LEVEL");
        }
        if (value == null || value.isBlank()) {
            value = "INFO";
        }

        return switch (value.trim().toUpperCase(Locale.ROOT)) {
            case "FINE" -> Level.FINE;
            case "INFO" -> Level.INFO;
            case "WARNING" -> Level.WARNING;
            case "SEVERE" -> Level.SEVERE;
            default -> throw new IllegalArgumentException(
                    "Unsupported log level: " + value);
        };
    }

    public static void main(String[] args) {
        Level level = configuredLevel();
        Logger logger = Logger.getLogger("demo.env");

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + ": "
                        + formatMessage(record) + System.lineSeparator();
            }
        });

        logger.setUseParentHandlers(false);
        logger.setLevel(level);
        logger.addHandler(handler);

        try {
            System.out.println("effectiveLevel=" + level.getName());

            logger.fine("loading configuration");
            logger.info("service started");
            logger.warning("retry scheduled");
        } finally {
            handler.flush();
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

**Explanation:**

- `configuredLevel()` reads two sources according to a rule defined by **the application itself**. This is not a universal precedence order across all frameworks.
- `isBlank()` handles whitespace-only values; `trim().toUpperCase(Locale.ROOT)` normalizes the input value.
- `switch` returns a `java.util.logging.Level` object. Using a restricted set of values ensures misconfigurations are caught clearly.
- `logger.setLevel(level)` determines the minimum level of the **source logger**; `handler.setLevel(Level.ALL)` ensures the handler does not further filter out events permitted by the logger.
- `setUseParentHandlers(false)` prevents an event from being logged a second time through a handler attached to the parent logger in this example.
- `Formatter` prints exact `LEVEL: message` lines; JUL's `ConsoleHandler` writes to **stderr**. The `effectiveLevel` line is printed to **stdout**.
- Upon completion, the handler is flushed, removed from the logger, and closed. This is a standalone demo program; real-world server applications typically let the logging framework manage handler lifecycles.

Compile with JDK 17 or later:

~~~bash
javac EnvLoggingDemo.java
~~~

If **neither** `APP_LOG_LEVEL` nor `app.log.level` is set, run:

~~~bash
java EnvLoggingDemo
~~~

Stdout:

~~~text
effectiveLevel=INFO
~~~

Stderr:

~~~text
INFO: service started
WARNING: retry scheduled
~~~

The `FINE` line does not appear because the logger is at level `INFO`. The stdout and stderr streams may be interleaved in different display orders by the operating system or terminal; here they are shown **separately per stream** so the verification output is clear.

## 4. Setting Environment Variables Before Starting Java

### 4.1. Linux/macOS: Bash or Compatible Shells

~~~bash
export APP_LOG_LEVEL=FINE
java EnvLoggingDemo
~~~

Stdout:

~~~text
effectiveLevel=FINE
~~~

Stderr:

~~~text
FINE: loading configuration
INFO: service started
WARNING: retry scheduled
~~~

You can also set the variable for **a single process invocation**:

~~~bash
APP_LOG_LEVEL=WARNING java EnvLoggingDemo
~~~

In that case, stdout is `effectiveLevel=WARNING`, while stderr only has `WARNING: retry scheduled`. Assigning a variable immediately before `java` using this shell syntax does not alter the environment of other processes.

To remove an `export`ed variable from the current shell, use `unset APP_LOG_LEVEL`.

### 4.2. Windows PowerShell

~~~powershell
$env:APP_LOG_LEVEL = "FINE"
java EnvLoggingDemo
~~~

The stdout/stderr output matches the `FINE` case in section 4.1. When this value is no longer needed in the current PowerShell session:

~~~powershell
Remove-Item Env:APP_LOG_LEVEL
~~~

In Windows CMD, the syntax is different:

~~~bat
set APP_LOG_LEVEL=FINE
java EnvLoggingDemo
~~~

**Do not use** `export APP_LOG_LEVEL=FINE` in PowerShell or CMD; likewise, do not use CMD's `set APP_LOG_LEVEL=FINE` as a substitute for Bash shell syntax. On Windows, `setx` sets environment variables for **future processes**, and does not immediately update the running shell's environment.

### 4.3. JVM Property `-D` and Precedence in the Example

Suppose `APP_LOG_LEVEL=FINE` is already set. Run:

~~~bash
java -Dapp.log.level=WARNING EnvLoggingDemo
~~~

In the example, stdout is:

~~~text
effectiveLevel=WARNING
~~~

Stderr:

~~~text
WARNING: retry scheduled
~~~

The JVM property wins because the code checks `System.getProperty("app.log.level")` before `System.getenv("APP_LOG_LEVEL")`. If an application's design chooses a different precedence, the result will differ. Place `-Dapp.log.level=WARNING` **before the main class name**; if placed after `EnvLoggingDemo`, that string becomes a command-line argument to `main` and is no longer a JVM option.

**Self-check question:** If `APP_LOG_LEVEL=FINE` is set but `-Dapp.log.level=INFO` is passed, will `FINE` be printed? No. The code takes `INFO` from the system property, ignoring the environment variable in this case.

## 5. Environment Variables and JUL's `logging.properties`

JUL has a mechanism to select a configuration file via a standard **JVM system property**:

~~~bash
java -Djava.util.logging.config.file=config/logging.properties MyApplication
~~~

This is completely different from setting:

~~~text
JAVA_UTIL_LOGGING_CONFIG_FILE=config/logging.properties
~~~

The arbitrarily named environment variable on the second line **is not automatically recognized by JUL** as a file-selection flag. If you want to specify the path via an environment variable, a **launch script** can pass its value to the JVM option:

~~~bash
export APP_JUL_CONFIG=config/logging.properties
java "-Djava.util.logging.config.file=$APP_JUL_CONFIG" MyApplication
~~~

This example can only run when `MyApplication` and a valid `config/logging.properties` file exist. For Windows PowerShell, the equivalent syntax is:

~~~powershell
$env:APP_JUL_CONFIG = "C:/app/config/logging.properties"
java "-Djava.util.logging.config.file=$env:APP_JUL_CONFIG" MyApplication
~~~

How it works:

~~~text
APP_JUL_CONFIG (environment variable)
             |
             v
Launch script reads the value
             |
             v
-Djava.util.logging.config.file=<path>
             |
             v
JUL LogManager loads logging.properties
             |
             v
Logger/Handler/Formatter are configured
~~~

In `logging.properties`, you can set levels for loggers and handlers such as:

~~~properties
.level = INFO
handlers = java.util.logging.ConsoleHandler
java.util.logging.ConsoleHandler.level = FINE
demo.env.level = FINE
~~~

**Note:** when a program creates its own handlers, changes levels programmatically, or disables parent handlers (as in `EnvLoggingDemo`), the configuration calls in code affect the final outcome. Therefore, do not use this demo program to infer that file-based settings always override programmatic configuration. In production systems, there should be **a single clear owner of configuration** to avoid multiple places overriding each other.

## 6. How Do Logback, Log4j 2, and Spring Boot Read Environment Variables?

Each logging backend has its own syntax and mechanism. An environment variable **only takes effect if the backend or framework reads it**.

### 6.1. Logback (Typically Paired with SLF4J)

Example `logback.xml` configuration with the root level taken from `APP_LOG_LEVEL` and defaulting to `INFO`:

~~~xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="${APP_LOG_LEVEL:-INFO}">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

In Logback configuration, the property substitution syntax `${APP_LOG_LEVEL:-INFO}` requires Logback to look up the value in its supported property sources, which include process environment variables. With Logback, level values are `DEBUG`, `INFO`, `WARN`, `ERROR`, `TRACE`, etc., rather than mapping one-to-one with JUL levels. If `APP_LOG_LEVEL=DEBUG`, the root logger can allow debug logs when the runtime actually uses Logback and loads the right `logback.xml`.

Place `logback.xml` on the classpath (typically `src/main/resources` in Maven/Gradle projects) or configure an external file location using the backend's mechanism. **SLF4J is an API**, so adding only the `slf4j-api` dependency does not guarantee Logback is present: an appropriate provider/backend is required.

### 6.2. Log4j 2

In `log4j2.xml`, Log4j 2 supports environment lookups through the `env:` prefix. For example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout pattern="%p %c - %m%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="${env:APP_LOG_LEVEL:-info}">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
~~~

The `${env:APP_LOG_LEVEL:-info}` syntax uses an environment lookup with a default value of `info` when the variable is absent. This example only works for programs running a Log4j 2 version/configuration that supports these lookups. Do not use `log4j2.xml` to configure Logback or JUL.

### 6.3. Spring Boot

Spring Boot provides externalized configuration: the `logging.level.root` property can be supplied via an environment variable following its property-name binding rules, for example:

~~~bash
LOGGING_LEVEL_ROOT=DEBUG java -jar app.jar
~~~

With PowerShell:

~~~powershell
$env:LOGGING_LEVEL_ROOT = "DEBUG"
java -jar app.jar
~~~

If the Spring Boot application has a suitable logging system and no higher-precedence configuration source overrides it, `LOGGING_LEVEL_ROOT` will control the root log level. In `application.properties`, the equivalent property name and value are:

~~~properties
logging.level.root=DEBUG
~~~

**Note:** Spring Boot has multiple property sources such as command-line arguments, system properties, environment variables, and config files; **the precedence order is defined by Spring Boot**. Do not assume `-D` takes precedence over environment variables in the same way `EnvLoggingDemo` does. Boot's log levels generally follow the configured backend and are not always JUL level names.

If configuring a specific logger/class name that contains uppercase letters, environment variable names may be normalized to lowercase by binding rules; in some cases another configuration format (such as `SPRING_APPLICATION_JSON`) is needed to preserve the exact logger name. Meanwhile, `LOGGING_LEVEL_ROOT` is a straightforward case that is easy to verify.

## 7. Environment-Specific Deployment: Terminal, IDE, Docker, and Services

**Terminal/IDE.** Environment variables must be passed to the exact Java process. IDEs typically have an "Environment variables" section in their run configurations. If a variable was set in a terminal but the application is launched from an IDE that was opened earlier, you cannot assume the IDE will inherit the new value. Inspect the environment of the actual process launched by the IDE or service.

**Docker.** With an image containing an application that supports `APP_LOG_LEVEL`:

~~~bash
docker run --rm -e APP_LOG_LEVEL=INFO my-app-image
~~~

This illustrative command assumes the `my-app-image` image already exists. Docker only provides the variable to the process inside the container; the application must still read the variable or the logging backend must be configured to read it. If using Docker Compose, you can pass it as follows:

~~~yaml
services:
  app:
    image: my-app-image
    environment:
      APP_LOG_LEVEL: INFO
~~~

The YAML file is an **integration configuration snippet**, not a standalone application. When changing values, you may need to recreate the container or restart the application depending on the deployment model. Do not expect a change in the host shell to propagate immediately into a Java process already running inside a container.

**Servers/CI/Kubernetes.** Each platform has its own way of injecting variables before startup (service manager, pipeline config, Deployment, ConfigMap, etc.). The general principle is to verify **the deployed value source**, **the process receiving the value**, and **when it is restarted**. Merely editing a file or variable on the host is not enough to conclude that Java has picked up the change.

**Consistent configuration design practices:**

- Use clear, namespaced names (`APP_LOG_LEVEL`, `APP_LOG_FORMAT`) to avoid collisions between components.
- Allow only valid levels for the active backend; emit a clear error message on invalid values.
- Define a conservative default (e.g., `INFO`) and document the precedence order.
- In production, consider stdout/stderr alongside the log collection system; format and destination depend on operational requirements.
- Never use an environment variable to store a **single request ID/trace ID** for all requests. Per-request correlation IDs belong in request context/MDC/tracing, not process-wide configuration.

## 8. Security, Performance, and Limitations of Environment-Based Configuration

**Level configuration also has security implications.** `DEBUG`/`TRACE` or `FINE` can inadvertently print payloads, file paths, user data, or system information. When enabling detailed logging for incident investigation, limit the scope, define when to turn it off, and verify sensitive-data masking mechanisms.

Do not log passwords, tokens, or secrets just to verify environment variables. Some platforms may expose environment variables in admin UIs, diagnostic tools, crash dumps, or to users with system access. Even though log levels are not secrets, avoid putting secrets into logging configuration or log output.

**Performance:** environment variables do not make logging free. When verbose levels are enabled, the number of generated events and the costs of formatting, I/O, networking, and buffering can increase significantly. With async logging, you must also check whether the queue can fill up, block, or discard events. On hot paths, read configuration **once at initialization or through an appropriate config management mechanism**, rather than calling `System.getenv()` on every log event.

**Runtime changes:** system properties can be modified inside the JVM via API, but the logger/backend may have already read and cached the configuration at startup. Changing a property **does not guarantee** that the logging system will reload automatically. Verify the reconfiguration capabilities of the logging system in use, and have a rollback plan when changing log levels or destinations.

## 9. Troubleshooting Table

| Symptom | Causes to Check | Resolution |
| --- | --- | --- |
| `APP_LOG_LEVEL` is set but logs do not change | Application/backend does not read that variable | Check `System.getenv` code, XML lookup, Spring property mapping |
| Terminal has the variable but Java reads `null` | Variable set in another session or after process startup | Set the variable in the proper parent process and restart |
| `APP_LOG_LEVEL=DEBUG` is rejected as invalid | JUL uses `FINE` instead of `DEBUG` in the pure-Java example | Use a valid backend value or write an explicit mapping layer |
| Passing `-D...` has no effect | Flag placed after main class/JAR, wrong key used, or code does not read that key | Place `-D` before class/`-jar` and verify the key |
| `FINE` logs still do not appear | Handler blocked them, or effective logger level is not `FINE` | Check both logger level and handler/appender/filter |
| `LOGGING_LEVEL_ROOT` is set but nothing changes | Not running Spring Boot, a higher-precedence config source overrides it, or backend differs from expectation | Verify the framework and the final effective config source |
| Running Docker but logs ignore configuration | Variable not passed properly to container, or container not recreated | Check deployment config and restart/recreate as needed |
| Variable changed on server but service logs the same | Process is running with the old environment or backend does not reload | Apply changes via a supported mechanism and verify restart |
| Too many logs or sensitive data exposed | Overly verbose level enabled in production | Lower the level, filter/redact data, and limit how long it stays enabled |
| Log lines lack request/trace ID | MDC/tracing propagation not configured | Set per-request context; do not use a process-wide variable |

## 10. Self-Check Exercises

1. **No environment variable or property set:** Which level does `java EnvLoggingDemo` use? → `INFO`, printing two logs (`INFO` and `WARNING`) to stderr.
2. **With `APP_LOG_LEVEL=FINE`:** Which logs are printed? → `FINE`, `INFO`, `WARNING`; stdout prints `effectiveLevel=FINE`.
3. **With both environment `FINE` and JVM property `WARNING`:** Which value wins? → `WARNING`, because the code intentionally prioritizes `System.getProperty`.
4. **Passing `APP_LOG_LEVEL=DEBUG` to the JUL example program:** What happens? → Throws `IllegalArgumentException` before creating logs because `DEBUG` is outside the allowed list.
5. **Setting only `APP_JUL_CONFIG` without forwarding it to JVM `-Djava.util.logging.config.file`:** Does JUL load that file automatically? → No, unless a supporting script or code forwards it.
6. **Changing the variable in the terminal while the JVM is still running:** Do subsequent logs automatically change level? → You cannot assume so. A reload mechanism or proper restart is required.

**Remember:** Environment variables are the channel for delivering configuration into a process, while the logger/framework decides how to use it. To control Java logging safely per environment, identify the actual backend, supported variable names, precedence order, valid levels, and configuration reload timing.