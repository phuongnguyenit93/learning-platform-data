# Classpath configuration in Java Core Logging

## 1. What is classpath configuration?

**Classpath configuration** is the practice of packaging a logging configuration file as a **resource** that can be loaded through the application's class loader. At runtime, the logging framework or the application itself locates the resource by name, reads the configuration rules, and initializes loggers, handlers/appenders, formatters, filters, log levels, and output destinations.

For example, projects using Maven/Gradle typically store configuration at:

```text
src/
  main/
    java/
      com/example/App.java
    resources/
      logback.xml
  test/
    resources/
      logback-test.xml
```

After a standard build, `src/main/resources/logback.xml` appears **at the root of the resource classpath** (not under a path prefixed with `src/main/resources`). The application only needs to look up the resource named `logback.xml`. In tests, `src/test/resources` is typically added to the test runtime classpath, allowing a separate configuration to be used.

Points to distinguish:

- **Classpath resource:** located by a class loader, such as `getResourceAsStream("logging.properties")`; it may reside in a classes directory or inside a JAR.
- **Filesystem path:** such as `/etc/myapp/logback.xml` or `C:\\config\\logging.properties`; located on disk by the OS/JVM and does not automatically become a classpath resource.
- **System property / environment variable / framework configuration:** may instruct the backend to read a file from another location; each logging framework defines its own keys and precedence rules.
- **Logger API:** a `logger.info(...)` call does not by itself indicate which backend is active. The configuration lookup mechanism depends on JUL, Logback, Log4j2, Spring Boot, or the integrated system.

**There is no single automatic rule shared across all Java libraries:** placing a file named `logging.properties` into `resources` does not guarantee that every logger will pick up that file.

## 2. How does Java locate resources on the classpath?

Suppose there is a resource `config/logging.properties` in `src/main/resources`. It can be opened with:

```java
try (var input = MyApplication.class.getClassLoader()
        .getResourceAsStream("config/logging.properties")) {
    if (input == null) {
        throw new IllegalStateException("Missing config/logging.properties");
    }
    // Read the data or pass the InputStream to the logger configurator.
}
```

This is an **illustrative snippet** that must be placed inside a method of a `MyApplication` class; it only opens the resource and does not configure a logger yet. `ClassLoader.getResourceAsStream` takes a name **without a leading `/`**. By contrast, `MyApplication.class.getResourceAsStream("/config/logging.properties")` uses `/` to look up from the classpath root; without `/`, `Class.getResourceAsStream` resolves the path relative to the class's package.

The lookup order depends on the **actual class loader**, how the application is launched, and the classpath order. A resource may reside at:

```text
build/classes/java/main/com/example/App.class
build/resources/main/logback.xml
```

or inside a JAR:

```text
app.jar
  com/example/App.class
  logback.xml
```

In an executable Spring Boot JAR, the same resource may be packaged under `BOOT-INF/classes/` and exposed on the internal classpath by Spring Boot's launcher. Do not infer a resource's physical path from its source path.

### Duplicate resource names

If `logback.xml` or `logging.properties` appears in multiple JARs or directories, `getResource(...)` typically returns one copy according to the class loader's lookup algorithm. Determinism and ordering among copies **depend on the runtime/class loader**; duplicate filenames should not be treated as a reliable override mechanism in deployment.

You can inspect visible locations with:

```java
import java.net.URL;
import java.util.Enumeration;

Enumeration<URL> urls = Thread.currentThread()
        .getContextClassLoader().getResources("logback.xml");
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
```

This snippet is for diagnostics only and has no fixed stdout because paths vary across machines and packaging types. The thread context class loader may differ from the current class's class loader, especially in a server or plugin container. When diagnosing, use the exact loader that the logging framework actually uses. If multiple configuration resources exist, remove the unintended copy or explicitly specify the desired location using a mechanism supported by the framework.

## 3. How does each logging stack read configuration?

| Logging stack | Typical configuration resource | Key mechanism |
| --- | --- | --- |
| JDK's **java.util.logging (JUL)** | `logging.properties` | JUL **does not automatically search for an arbitrary `logging.properties` on the classpath**. The JVM typically uses the default JUL configuration, or `-Djava.util.logging.config.file=...` pointing to a file on the filesystem; a classpath resource can be loaded via `LogManager.readConfiguration(InputStream)`. |
| **SLF4J 2.x** | Does not dictate `logback.xml` or `log4j2.xml` itself | SLF4J is a facade. It locates a **provider** on the runtime classpath, and the selected backend then reads its corresponding configuration. |
| **Logback Classic** (commonly used with SLF4J) | `logback-test.xml` in tests, `logback.xml` in applications | Logback searches for configuration according to its own discovery flow; the dedicated test file can take precedence. A file can be specified explicitly via the `logback.configurationFile` system property. |
| **Log4j 2 Core** | `log4j2-test.xml`, `log4j2.xml`, or other supported formats | Log4j2 locates configuration files according to its own rules, including a test-specific variant; a location can be specified explicitly with `log4j2.configurationFile`. |

Notes:

1. Auto-discovery mechanisms, supported formats, and exact precedence orders can change across library versions. Check the actual backend version in the dependency tree when troubleshooting.
2. The SLF4J **API** and **provider** serve two different roles. Having only `slf4j-api` without a suitable provider may cause the application to use a no-op logger and emit a warning; conversely, multiple providers on the classpath also produce unexpected results.
3. SLF4J 2.x uses a provider mechanism that differs from the earlier 1.7.x line; an old binding cannot be assumed to be a compatible provider. For example, Logback 1.4/1.5 typically pairs with SLF4J 2.x; always verify actual version compatibility.
4. `logback-test.xml` and `log4j2-test.xml` are **naming conventions**, not security privileges. If they are accidentally included in the production runtime, they can be picked up according to the backend's configuration discovery rules.
5. Avoid placing opposing bridges/adapters together in a way that creates a logging loop (for example, routing Log4j API to SLF4J while simultaneously routing SLF4J back to Log4j through an incorrect dependency combination). Define one clear target backend.

## 4. Complete Java 17 example: loading JUL from the classpath

To observe the mechanism without downloading extra libraries, we use the JDK's `java.util.logging` and **explicitly** read `logging.properties` via the class loader.

Directory structure:

```text
classpath-logging-demo/
  ClasspathLoggingDemo.java
  resources/
    logging.properties
```

Contents of `resources/logging.properties`:

```properties
handlers=java.util.logging.ConsoleHandler
.level=INFO

java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.SimpleFormatter.format=%4$s: %5$s%n

demo.app.level=FINE
```

Quick explanation: the `demo.app` logger is set to `FINE`, while `ConsoleHandler` is set to `INFO`. Because an event must pass **both the logger level and the handler level**, `FINE` will not appear, whereas `INFO` and `WARNING` will. `SimpleFormatter.format` prints only the level and message, making the output easy to verify accurately.

Contents of `ClasspathLoggingDemo.java`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.util.logging.LogManager;
import java.util.logging.Logger;

public final class ClasspathLoggingDemo {
    private ClasspathLoggingDemo() {}

    public static void main(String[] args) throws IOException {
        ClassLoader loader = ClasspathLoggingDemo.class.getClassLoader();

        try (InputStream config =
                     loader.getResourceAsStream("logging.properties")) {
            if (config == null) {
                throw new IllegalStateException(
                        "Missing classpath resource: logging.properties");
            }
            LogManager.getLogManager().readConfiguration(config);
        }

        Logger logger = Logger.getLogger("demo.app");
        logger.fine("detail");
        logger.info("started");
        logger.warning("slow-operation");
    }
}
```

Inside the `classpath-logging-demo` directory, compile:

```bash
javac -d out ClasspathLoggingDemo.java
```

Run on Linux/macOS (`:` separates classpath entries):

```bash
java -cp "out:resources" ClasspathLoggingDemo
```

Run on Windows (`;` separates classpath entries):

```powershell
java -cp "out;resources" ClasspathLoggingDemo
```

Exact **stderr** output from `ConsoleHandler` under the configuration above:

```text
INFO: started
WARNING: slow-operation
```

There is no `FINE` line and the program writes nothing to stdout. If `resources` is omitted from `-cp`, `getResourceAsStream("logging.properties")` returns `null`; the program explicitly throws `IllegalStateException` with a message naming the missing resource. Merely placing the file in the working directory without adding that directory to the classpath does not make it visible to the class loader either.

**Key takeaway:** the example must call `LogManager.readConfiguration(config)` explicitly. That is how an application loads `logging.properties` from the classpath into JUL; placing the resource in a JAR does not automatically cause JUL to use it.

### Configuring JUL with an external file outside the classpath

JUL also supports pointing to a **filesystem file** at JVM startup:

```bash
java -Djava.util.logging.config.file=/path/to/logging.properties -cp out ClasspathLoggingDemo
```

However, the sample program **still calls `readConfiguration` itself**, so the configuration it loads from the classpath can replace the file configuration specified via the system property. To demonstrate the behavior of `-Djava.util.logging.config.file`, use a program that **does not reload the configuration itself**. Do not assume these two sources are automatically merged.

## 5. Example Logback configuration on the classpath

An application using `slf4j-api` with a compatible `logback-classic` can place `src/main/resources/logback.xml` as follows:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.noisy" level="WARN"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

This is an **XML configuration for Logback, not a standalone Java program**. When the Logback backend is selected and reads the file successfully:

- The root logger is at `INFO`; child loggers inherit this level unless configured otherwise.
- The `com.example.noisy` logger has level `WARN`, so its regular `INFO` calls will not produce events.
- `STDOUT` defines a console appender with a layout containing the timestamp, level, thread name, logger name, and message.
- If multiple appenders or additivity are configured, logs may be sent multiple times to multiple destinations; this is a configuration issue, not necessarily two logger calls.

To test without modifying the production file, place `logback-test.xml` in `src/test/resources`. On the test runtime classpath, Logback typically prioritizes the test-specific file; outside tests, package only the resources intended for runtime. When you need to specify a file outside the classpath, Logback supports a similar option:

```bash
java -Dlogback.configurationFile=/etc/myapp/logback.xml -cp "app.jar:lib/*" com.example.App
```

The paths and classpath syntax in this example are for Linux/macOS; Windows uses `;` to separate entries. This command only illustrates the override mechanism; actual classes, dependency JARs, and the configuration file must be supplied to run.

With **Log4j2 Core**, applications typically place `src/main/resources/log4j2.xml`; a test configuration such as `log4j2-test.xml` can be used and overridden with `-Dlog4j2.configurationFile=...` according to the version in use. Do not pass a `logback.xml` structure to Log4j2 or a `log4j2.xml` structure to Logback: the XML schema and appender initialization of the two backends are different.

## 6. Classpath in Maven, Gradle, JARs, and tests

### Standard Maven/Gradle layout

Under a typical Java project structure:

| Source | Used at runtime as | Purpose |
| --- | --- | --- |
| `src/main/java` | Compiled classes | Application code |
| `src/main/resources` | Resources in `classes` output or JAR | Logging configuration shipped with the application |
| `src/test/java` | Compiled test classes | Test code |
| `src/test/resources` | Resources only on the test runtime classpath | Test configuration and data |

Plugins/build scripts can customize source sets, resource processing, excludes, or filenames. Therefore, inspect the **actual built artifact**, not just files in the source tree.

Example of inspecting a standard JAR:

```bash
jar tf build/libs/my-app.jar
```

Look for `logback.xml`, `log4j2.xml`, or `logging.properties` in a location the class loader can reach. In a Spring Boot executable JAR, contents typically live under `BOOT-INF/classes/` and dependencies under `BOOT-INF/lib/`; Spring Boot's launcher handles this layout. Do not apply flat-JAR classpath assumptions mechanically to every packaged launcher.

### Differences between `java -cp` and `java -jar`

- `java -cp "classes:resources:lib/*" com.example.App` explicitly sets the application classpath entries on Linux/macOS; on Windows, replace `:` with `;`.
- `java -jar app.jar` runs the main class specified in the JAR manifest and **ignores the `-cp` classpath option passed by the user**. Nor does it automatically read every file in the working directory; additional classpath entries may come from the manifest or a launcher mechanism.
- A framework-packaged executable JAR may use its own class loader and rules; tests should mirror the production launch method.

The test classpath is not identical to the production runtime classpath. For example, `logback-test.xml` is present on `testRuntimeClasspath`, but it must not be accidentally packaged into the release JAR. If logs appear in the IDE but disappear when running `java -jar`, check the resource location, logger provider, and appender configuration in the production artifact.

### Libraries vs. applications

Shared libraries should prefer calling a logging API (such as SLF4J) and let the **host application** choose the provider, appenders, and levels. A library dependency that bundles its own `logback.xml` can create resource conflicts with the application. If a library needs special internal configuration, establish an explicit contract rather than imposing a global configuration on consuming applications.

## 7. Precedence and configuration overrides

Classpath configuration is only one of several possible configuration sources:

```text
Application's intended configuration
    |
    +-- resource file packaged on the classpath
    |
    +-- external file outside the JAR selected by system property/framework
    |
    +-- initialization code or reconfiguration API
    |
    +-- backend's default policy
```

This diagram shows **possible sources**, not a fixed precedence order. Actual precedence depends on each backend and initialization timing. A reliable way to manage environments is to designate **one clear owner responsible for selecting the configuration**, and test that exact mechanism.

In Spring Boot, logging configuration is typically managed via `logging.*` properties and Spring Boot's configuration selection mechanism. `logback-spring.xml` is a Spring Boot-supported variant that can leverage Spring-specific configuration features; a plain Java application using Logback should not assume a file with this name will be auto-loaded like `logback.xml`. `logging.config` can specify the file location through Spring Boot's mechanism. Distinguish between **Spring Boot initializing logging** and **Logback self-initializing** to avoid loading configuration too early, ignoring Spring properties, or having configuration overwritten again.

When log levels need to vary by environment, you can keep the classpath configuration as **sensible defaults** and define an override policy supported by your framework version. Do not hardcode sensitive information such as passwords, access tokens, or API keys in configuration files packaged into a JAR; such data can be extracted from the artifact.

Hot reload does not happen automatically just because a resource is on the classpath. Some backends support scanning for file changes or reloading via an API, but resources inside a JAR are usually not files that can be edited in place. If dynamic configuration is needed, design a dedicated override/reload pipeline with proper synchronization, observability, and access controls.

## 8. Diagnosing missing or misloaded logging configuration

| Symptom | Common cause | How to verify |
| --- | --- | --- |
| Logs do not appear | Wrong level, missing appender, facade present without provider, file not found | Check runtime dependencies, startup warnings, effective levels, and output destinations |
| Using JUL but `logging.properties` in resources has no effect | JUL does not automatically read a classpath resource by that name | Use `LogManager.readConfiguration(InputStream)` or a file pointed to by the JUL system property |
| Works in IDE, differs in packaged JAR | Resource excluded, different launcher, different classpath, or missing backend JAR | Inspect the artifact with `jar tf`, startup command, and runtime classpath |
| Logback reads test configuration in production | `logback-test.xml` accidentally included on the runtime classpath | Inspect JAR/dependency contents and the selected resource path |
| Console has logs but file appender does not write | Relative path resolved against a different working directory; missing directory permissions; appender failed to start | Check working directory, absolute path, permissions, and backend status messages |
| Duplicate logs | Multiple appenders targeting the same destination, logger additivity, misconfigured bridges | Inspect the logger/appender tree and transitive dependencies |
| Two `logback.xml` files competing | A dependency and the application package the same resource name | List all matching resources using `getResources` |
| `-D...` is set but has no effect | Wrong framework key, property set after logger initialization, or code/framework reloads config | Check JVM arguments, startup logs, and backend initialization point |
| Logs change unexpectedly across unit tests | Tests share a global logger context and mutate shared appenders/levels | Isolate logger context if the stack supports it; restore configuration after tests |

An effective diagnostic workflow:

1. **Identify the actual backend:** does the application use JUL, Logback, or Log4j2? With SLF4J, check which provider is active and look for warnings about multiple providers or incompatible providers.
2. **Identify the launch method:** `java -cp`, `java -jar`, Gradle/Maven run task, IDE, Spring Boot launcher, or a container? Note the corresponding classpath/resource visibility.
3. **Locate the exact resource:** verify exact name, case sensitivity, path under the resource root, and any duplicate copies. Do not confuse `resources/logback.xml` (source layout) with `logback.xml` (resource name).
4. **Verify loading:** enable the backend's diagnostics/status logging per its version documentation; confirm which file was selected and whether any parse or appender configuration errors occurred.
5. **Trace the event through the filter chain:** logger level → filter → appender/handler level → encoder/formatter → output destination. A missing line may have been filtered out as designed.
6. **Reproduce from the production artifact:** compare behavior in the IDE, tests, and packaged runtime using the same log level and a clearly identifiable event.

With JUL, you can print `getResource("logging.properties")` to **stderr during diagnostics** to locate the resource; do not make environment-dependent paths part of expected output in unit tests. With other backends, prefer the framework's own status logger or diagnostic flags.

## 9. Testing classpath configuration

A valuable configuration test should verify **behavior**, not just file existence:

- **Resource is on the runtime classpath:** the appropriate class loader returns the resource; the production artifact contains it as well.
- **Read by the actual backend:** effective levels, appenders, and formatters match policy; there are no parse errors or dependency mismatches.
- **Test config is isolated:** files in `src/test/resources` do not accidentally end up in the production artifact.
- **Overridable when needed:** path/system property/framework overrides are tested with the exact command line and initialization phase used by the system.
- **No dependence on duplicate resource ordering:** the application controls a single configuration source or detects conflicts explicitly.
- **Startup/shutdown:** logging works during the expected startup phase; async appenders are flushed/closed according to contract on shutdown.
- **No sensitive data leakage:** secrets are not packaged in the config; log output does not accidentally print tokens or passwords via encoders or MDC.

When using multiple profiles such as `dev`, `test`, and `prod`, define which configuration file is allowed in each environment and store the selection rule in deployment configuration. A generic filename inside a JAR is not enough to guarantee every environment will automatically choose the right policy.

**Remember:** classpath logging configuration works when the resource **is actually present in the active class loader** and **the backend actually knows how to read it**. JUL requires reading the resource explicitly if you want to use an arbitrary classpath file; Logback and Log4j2 have their own auto-discovery rules; SLF4J selects a provider rather than defining a config file format itself. When troubleshooting, check the resource name, provider/backend, artifact packaging, precedence, and application launch method together.
