# Logging Configuration File Names in Java

## 1. What Does the Configuration File Name Determine?

When a Java application starts, the logging backend needs to know the level, appender/handler, message format, destination, and related policies. Some backends automatically look for configuration by a **conventional file name** on the classpath; others use the JDK's default configuration or a path specified via a system property. If you use the wrong name, wrong directory, or syntax from another backend, the program may still run while falling back to the default configuration, leading to subtle issues: DEBUG logs disappear, the format is wrong, or logs are not written to the expected file.

**Three concepts must be distinguished:**

- **Configuration file name:** for example `logback.xml`, `log4j2.xml`, `logback-spring.xml`, or `logging.properties`. This is the backend configuration document.
- **Configuration lookup path:** the root of the runtime classpath, an explicitly specified classpath resource, or an external file path outside the application.
- **Log output file name:** for example `application.log` or `/var/log/orders/service.log`. This is the output data created by an appender/handler; it is not the configuration file.

A file with the right name in the wrong place may still not be found. A file in the right place with invalid syntax will also not be processed as expected.

## 2. Quick Reference Table

| Logging system | Common configuration file names | How it is selected | Notes |
| --- | --- | --- | --- |
| Java Util Logging (JUL, java.util.logging) | logging.properties | Defaults to the JDK configuration; path can be specified explicitly via `java.util.logging.config.file` | JUL does not automatically treat every `logging.properties` file in `src/main/resources` as the default configuration file |
| Logback classic | logback.xml | Automatically searched on the classpath when no higher-priority configuration exists | Common XML configuration for Java applications using SLF4J + Logback |
| Logback classic, running tests | logback-test.xml | When present on the classpath, takes precedence over `logback.xml` in the standard XML discovery mechanism | Place in `src/test/resources` so it is not packaged by mistake |
| Log4j 2 Core | log4j2.xml, log4j2.properties, log4j2.json, log4j2.yaml, or log4j2.yml | Automatically discovered according to the factories/formats supported at runtime | Do not use Log4j 1's `log4j.xml` name as the default for Log4j 2 |
| Log4j 2 Core, running tests | log4j2-test.xml or `log4j2-test` with a supported configuration extension | Test file group is searched before the regular file group | Place test files only on the test classpath |
| Spring Boot + Logback | logback-spring.xml; `logback.xml` is also supported | Spring Boot manages logging integration | Prefer `logback-spring.xml` when `springProfile`/`springProperty` is needed |
| Spring Boot + Log4j 2 | log4j2-spring.xml; `log4j2.xml` is also supported | Spring Boot manages Log4j 2 integration | Files with the `-spring` suffix require Boot's mechanism |
| Spring Boot, application-level configuration | application.properties or application.yaml/application.yml | Spring Boot reads `logging.*` properties from the `Environment` | Does not replace all advanced Logback/Log4j 2 configurations |

This table applies to common configuration approaches. Logger factories, service providers, class loaders, versions, and instrumentation can alter the actual discovery mechanism; in operation, you must verify **which backend is actually loaded**.

**SLF4J is an API/facade, not a logging backend itself.** There is no single universal XML configuration file name for every application just because the code calls `org.slf4j.Logger`. When SLF4J uses Logback, configure it for Logback; when it is bridged to Log4j 2, configure it for Log4j 2. Nor should you look only at transitive dependencies and assume which framework is active.

## 3. Classpath and File Location

With a typical Maven structure:

~~~text
logging-demo/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/example/LoggingDemo.java
│   │   └── resources/
│   │       └── logback.xml
│   └── test/
│       └── resources/
│           └── logback-test.xml
└── target/
    ├── classes/
    │   └── logback.xml
    └── test-classes/
        └── logback-test.xml
~~~

During a build, Maven typically copies main resources into `target/classes` and test resources into `target/test-classes`. When running tests, both areas may be on the classpath at the same time, so Logback encounters `logback-test.xml` before `logback.xml` according to its XML configuration lookup rules. When packaging a normal application, resources in `src/test/resources` should not be included in the release artifact.

The **classpath root** is the starting point for resource lookup, not necessarily the current directory where you run the command. For example, if the backend is looking for the `logback.xml` resource at the classpath root, then:

~~~text
src/main/resources/logback.xml             # default name: can be found
src/main/resources/config/logback.xml      # NOT the same location; requires an explicit path or another loading method
src/main/java/logback.xml                  # NOT the default Maven configuration resource location
src/test/resources/logback-test.xml        # test-specific configuration
~~~

In a Spring Boot executable JAR, the internal physical structure of the JAR differs from a standard library JAR, yet resources from `src/main/resources` remain accessible through the classpath set up by Boot. Do not infer OS file paths inside the JAR from classpath paths.

### The Name Must Be Exact

On case-sensitive operating systems (commonly Linux), `Logback.xml` and `logback.xml` are two different names. Whitespace, extra extensions, or the wrong extension can cause the file to be ignored: `logback.xml.txt` is not `logback.xml`. On Windows, a configuration may work on a developer machine but fail to load on a Linux server if it relies on case differences.

## 4. Java Util Logging (JUL): logging.properties

JUL is the logging API built into the JDK. For JDK 17, the default configuration typically resides at:

~~~text
<JDK_HOME>/conf/logging.properties
~~~

In the example above, `JDK_HOME` is the JDK installation directory. **It does not scan `src/main/resources/logging.properties` by name by default** the way Logback searches for `logback.xml`. To use a different file, it is typically specified explicitly via a JVM system property:

~~~bash
java -Djava.util.logging.config.file=conf/dev-logging.properties -cp out example.LoggingDemo
~~~

Key points:

- The `java.util.logging.config.file` property is the **path to the JUL configuration file**, not the path to the output log file.
- The contents must follow JUL's Java `.properties` format; giving a file a `.xml` extension and passing it to JUL will not make it parse XML syntax.
- The property should be passed at JVM startup, before `LogManager` initializes.
- JUL also supports a custom configuration mechanism via `java.util.logging.config.class`. If this mechanism is used, you cannot determine the loaded configuration solely from a file name.
- Calling `LogManager.readConfiguration()` or runtime configuration update APIs has its own rules; do not assume modifying the file on disk guarantees automatic reloading.

### Standalone Java 17 Example with a Custom File Name

This example **does not require Maven or any library outside the JDK**. We intentionally name the file `dev-logging.properties` to demonstrate that the name can be arbitrary when the path is explicitly specified.

Directory structure:

~~~text
logging-demo/
├── conf/
│   └── dev-logging.properties
└── src/
    └── main/
        └── java/
            └── example/
                └── LoggingDemo.java
~~~

**conf/dev-logging.properties**

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=FINE
java.util.logging.ConsoleHandler.level=FINE
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.SimpleFormatter.format=%4$s: %5$s%n
~~~

**src/main/java/example/LoggingDemo.java**

~~~java
package example;

import java.util.logging.Logger;

public final class LoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(LoggingDemo.class.getName());

    public static void main(String[] args) {
        LOG.info("INFO_VISIBLE");
        LOG.fine("FINE_VISIBLE");
    }
}
~~~

Run from the `logging-demo` directory using JDK 17 or later:

~~~bash
javac -encoding UTF-8 src/main/java/example/LoggingDemo.java
java -Djava.util.logging.config.file=conf/dev-logging.properties -cp src/main/java example.LoggingDemo
~~~

Output produced by `ConsoleHandler` on **stderr**:

~~~text
INFO: INFO_VISIBLE
FINE: FINE_VISIBLE
~~~

The `javac` command generates `LoggingDemo.class` under `src/main/java/example`. You can replace this with your project's build tool if you do not want to compile directly inside the source tree.

**Why does this work?** The system property points `LogManager` to `dev-logging.properties` from the moment the JVM starts. The configuration sets the `FINE` level for the root logger and `ConsoleHandler`; the `SimpleFormatter` format outputs only the level and message, making the result easy to verify. The name `dev-logging.properties` has no special auto-discovery feature: if you omit the system property, JUL falls back to the default configuration source or another active configuration mechanism, and the `FINE_VISIBLE` output is no longer guaranteed.

### Renaming the File Without Updating the Path

If you rename `dev-logging.properties` to `local.properties` while keeping the old run command, this is a **configuration source selection error**, not a bug in `Logger.info`. You must update the system property to `conf/local.properties`, or revert to the old name. Check the working directory because relative paths are resolved against the process's current working directory.

## 5. Logback: logback.xml and logback-test.xml

Logback is commonly the backend for applications using SLF4J. In the standard automatic XML configuration lookup mechanism, when no higher-priority custom configuration is present, Logback tries **`logback-test.xml` first**, then **`logback.xml`** on the classpath. If neither is found, it may fall back to a basic console-logging configuration; the exact initialization details depend on the Logback version and any registered configurators.

Common names:

~~~text
src/main/resources/logback.xml          # normal application execution
src/test/resources/logback-test.xml     # unit/integration tests
~~~

**Example `logback.xml` content:**

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>LB %level %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

The XML snippet above is a valid Logback configuration file when the application has the appropriate Logback logging backend. With an SLF4J `log.info("started")` call, the pattern will display:

~~~text
LB INFO started
~~~

It is **not** a standalone Java program. It requires a dependency such as `logback-classic` compatible with `slf4j-api` and code that uses a logger. With Logback, do not name a file `log4j2.xml` and expect Logback to recognize it automatically.

### Selecting a Logback Path Outside the JAR

You can pass a JVM system property:

~~~bash
java -Dlogback.configurationFile=/etc/orders/logback-prod.xml -jar orders.jar
~~~

The `logback.configurationFile` property can point to a file path, URL, or classpath resource as supported by Logback. Set the property **before the first logger is created**. Do not set it too late in business code after the backend has already initialized and expect the configuration to switch automatically.

In projects deployed differently per environment, keep a simple default file on the classpath or specify an external file. When the external file name is no longer `logback.xml`, successful loading comes from the **path property**, not because Logback automatically searches for every `.xml` file in the directory.

### Tests Can Shadow the Main Configuration

If `logback-test.xml` is accidentally packaged with the production application, it can cause the observed configuration to differ from `logback.xml`. Keep test files in `src/test/resources` and inspect the packaged artifact. Do not rely on seeing a `logback.xml` file in the repository to conclude that the runtime is using it.

### Version Notes

Recent Logback versions add several configuration mechanisms, such as configurators loaded via service providers and serialized model formats. The official documentation describes the detailed initialization order. The `logback-test.xml` then `logback.xml` rule above is the **common XML discovery branch**, which does not mean every Logback application ignores advanced configurators.

## 6. Log4j 2: log4j2.xml and log4j2-test.xml

Log4j 2 is a different system from both Logback and Log4j 1.x. **Log4j 2 Core** uses the `ConfigurationFactory` mechanism to locate configuration. Familiar names include:

~~~text
src/main/resources/log4j2.xml
src/main/resources/log4j2.properties
src/main/resources/log4j2.json
src/main/resources/log4j2.yaml
src/test/resources/log4j2-test.xml
~~~

Not all formats work in every runtime: the corresponding `ConfigurationFactory` and parser libraries are required. For JSON/YAML, check the application's dependencies instead of simply changing an XML file's extension to `.json` or `.yaml`.

### Discovery Order in Log4j 2

The Log4j 2 documentation describes the file name groups by priority:

1. `log4j2-test` with the **LoggerContext** name and a supported extension.
2. `log4j2-test` with a supported extension.
3. `log4j2` with the LoggerContext name and a supported extension.
4. `log4j2` with a supported extension.

For the common case without a custom context name, the key point to remember is that **`-test` files take precedence over regular files**. When multiple formats coexist (for example `log4j2.xml` and `log4j2.properties`), the order also depends on `ConfigurationFactory`; therefore, keep **one primary file** and remove old copies rather than betting on discovery order.

**Example `log4j2.xml` content:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="L4J2 %level %msg%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

This XML configures Log4j 2 Core, which differs from Logback's `<configuration>` structure. If the application has valid Log4j 2 API and Core dependencies, an INFO `"started"` message will look like:

~~~text
L4J2 INFO started
~~~

This snippet represents a configuration fragment, not a standalone runnable Java program.

### Selecting a Log4j 2 File Outside the Classpath

For Log4j 2.x:

~~~bash
java -Dlog4j2.configurationFile=/etc/orders/log4j2-prod.xml -jar orders.jar
~~~

The `log4j2.configurationFile` property selects a specific configuration file. Set it at JVM startup so it takes effect as soon as the backend initializes.

**Avoid confusing with Log4j 1.x:** `log4j.properties` and `log4j.xml` are familiar names from Log4j 1, which has reached end of life. Log4j 2 does not read them as Log4j 2 configuration by default. If a legacy project has files with old names, identify which compatibility runtime/plugin is in use and migrate the configuration properly.

## 7. Spring Boot: The -spring Suffix and application.properties

Spring Boot has its own logging integration layer. In a Spring Boot application using the default logging starter, the common backend is Logback; when a project switches to the Log4j 2 starter, the configuration file name must change accordingly.

### Using Logback with Spring Boot

The typical recommendation:

~~~text
src/main/resources/logback-spring.xml
~~~

Spring Boot recognizes `logback-spring.xml`, whereas standalone Logback **does not treat the `-spring` suffix as a default name**. The benefit of `-spring` files is that Boot can manage configuration timing and provide extensions such as `<springProfile>` and `<springProperty>`.

**Example `logback-spring.xml`:**

~~~xml
<configuration>
    <springProfile name="dev">
        <appender name="DEV" class="ch.qos.logback.core.ConsoleAppender">
            <encoder>
                <pattern>DEV %level %msg%n</pattern>
            </encoder>
        </appender>
        <root level="DEBUG">
            <appender-ref ref="DEV"/>
        </root>
    </springProfile>

    <springProfile name="prod">
        <appender name="PROD" class="ch.qos.logback.core.ConsoleAppender">
            <encoder>
                <pattern>PROD %level %msg%n</pattern>
            </encoder>
        </appender>
        <root level="INFO">
            <appender-ref ref="PROD"/>
        </root>
    </springProfile>
</configuration>
~~~

This is an example for **Spring Boot + Logback**, not for a plain Logback program. The file defines appender/root settings only for the `dev` and `prod` profiles; one of those profiles must be active to get the desired configuration. Do not use `<springProfile>` tags in standard `logback.xml` because that file may be initialized by Logback too early, before Boot's extensions are ready. Boot's extensions are also incompatible with standard Logback configuration scanning.

### Using Log4j 2 with Spring Boot

When choosing Log4j 2 as the backend for Boot:

~~~text
src/main/resources/log4j2-spring.xml
~~~

Spring Boot supports this name and its own extensions. Standalone Log4j 2 Core normally looks for `log4j2.xml`/`log4j2.properties`... according to its own conventions; `log4j2-spring.xml` is not a standard auto-discovered name in standalone Log4j 2.

**Do not include both Logback and Log4j 2 simultaneously as primary backends** just to test file names. Choose the right dependency/provider first, then name the file accordingly.

### application.properties and logging.config

Spring Boot can accept `logging.*` properties in `application.properties` or `application.yaml`. For example:

**src/main/resources/application.properties**

~~~properties
spring.profiles.active=dev
logging.level.root=INFO
logging.level.example=DEBUG
logging.config=classpath:config/logback-custom.xml
~~~

With this configuration, **`logging.config`** instructs Boot to use the `config/logback-custom.xml` resource on the classpath, provided the backend is Logback and the file has valid syntax. The resource must exist at `src/main/resources/config/logback-custom.xml` before packaging. This is an example of selecting a file with an arbitrary name, not an auto-discovered default name.

You can specify an external file outside the JAR when deploying:

~~~properties
logging.config=file:/etc/orders/logback-prod.xml
~~~

Ensure the application has read permission for that file and that the path applies to the actual runtime environment. `Environment` values must be available during early logging initialization; do not assume that properties loaded late via `@PropertySource` can override `logging.config` from the start.

**Distinguish `logging.config` from `logging.file.name`:**

~~~properties
logging.config=classpath:logback-spring.xml
logging.file.name=/var/log/orders/application.log
~~~

- `logging.config`: specifies the **backend configuration source**.
- `logging.file.name`: specifies the **log output file name** in Boot logging configurations that support it; if you define a custom appender in XML, make sure that appender actually uses the file name setting as designed.
- `application.properties`: holds application/Spring Boot configuration properties, not Logback XML or Log4j 2 XML.

If you only need simple logging level changes in Boot, `logging.level.*` keys may already be enough; creating a separate XML file just for log levels is not required.

## 8. Selection Scope and Precedence: Understanding It Correctly

You should not build a single precedence list that applies to every Java application. The selection system depends on the backend and the startup mechanism:

| Situation | Configuration source to check first |
| --- | --- |
| Plain Java + JUL | `java.util.logging.config.file` if passed; otherwise, the LogManager/JDK default configuration |
| Plain Java + SLF4J/Logback | `logback.configurationFile` or registered configurator; then the `logback-test.xml`/`logback.xml` XML branch |
| Plain Java + Log4j 2 Core | `log4j2.configurationFile`; if absent, `log4j2-test`/`log4j2` names supported by the runtime |
| Spring Boot + Logback | `logging.config` if declared; otherwise locations/names supported by Boot, especially `logback-spring.xml` |
| Spring Boot + Log4j 2 | `logging.config` if declared; otherwise names supported by Boot, especially `log4j2-spring.xml` |
| Unit tests using test classpath | `logback-test.xml` or `log4j2-test.xml` may take precedence depending on the backend |
| Application running in a container | Check file names inside the image, volume mounts, working directory, and actual JVM/system properties |

JVM `-D...` flags are **Java system properties** and must appear before the main class name or before `-jar` in the `java` command. For example:

~~~bash
java -Dlogback.configurationFile=/etc/app/logback.xml -jar app.jar
~~~

Unlike:

~~~bash
java -jar app.jar -Dlogback.configurationFile=/etc/app/logback.xml
~~~

In the second command, the `-D...` string is an **application argument** passed to `main` rather than a JVM system property, unless the application explicitly parses and handles it. Spring Boot also has its own mechanism for accepting application arguments like `--logging.config=...`; do not mix the two mechanisms without knowing which one reads the property.

### Multiple JARs on the Classpath Containing the Same Resource

A library may accidentally package `logback.xml` or `log4j2.xml`, resulting in multiple resources with the same name. The outcome depends on the class loader and discovery mechanism. A **library** should keep its logging configuration in test resources rather than imposing a mandatory configuration on every application that uses it. The main application should own its own configuration.

## 9. Diagnosing Wrong Configuration Names or Locations

**Scenario 1: Created `logback.xml`, but the application still logs only with defaults.**

Check whether the actual backend is Logback; whether the file is at the runtime classpath root; whether the name has exact lowercase spelling and the right extension; and whether `logback-test.xml`, `logback.configurationFile`, or a custom `Configurator` is overriding it. If running Spring Boot and needing Boot-specific extensions, use `logback-spring.xml`.

**Scenario 2: `logback-spring.xml` has no effect when running a plain Java `main`.**

That name is supported by Spring Boot. Standalone Logback normally looks for `logback.xml` or `logback-test.xml`. Switch to a valid `logback.xml` or specify the path explicitly via `logback.configurationFile`.

**Scenario 3: A Log4j 2 project has `log4j.xml`, but the log level does not change.**

`log4j.xml` belongs to Log4j 1.x conventions. For Log4j 2, use `log4j2.xml` or another supported format; verify the Log4j 2 Core dependency. Do not merely rename the file if its XML content still uses Log4j 1 syntax.

**Scenario 4: Placed `logging.properties` in `src/main/resources`, but JUL ignores it.**

JUL defaults to the LogManager/JDK configuration; pass `-Djava.util.logging.config.file=...` explicitly to select the desired file, or load it via JUL management APIs if the application intentionally does so.

**Scenario 5: Tests print DEBUG logs, but running the JAR does not.**

Tests may be picking up `logback-test.xml`/`log4j2-test.xml`, while production uses the main file or default configuration. Compare the runtime classpath and system properties of both modes.

**Scenario 6: Updated the configuration file on the host, but no changes appear.**

The backend may read configuration only at startup; hot reload works only if configured and supported. With Spring Boot extensions such as `<springProfile>`, do not enable Logback scanning indiscriminately. Avoid assuming every change to an external file takes effect immediately.

**Scenario 7: Changed the log output file name, but logs still write to the old location.**

You may have only changed `logging.file.name` while a custom XML appender points directly to a different file. Inspect the appender's actual configuration and referenced property values, rather than checking only the XML file name.

### Quick Troubleshooting Checklist

1. Identify the logging API (JUL, SLF4J, Log4j 2 API) and the **actual execution backend** from dependencies/runtime.
2. Identify whether you are running plain Java, Spring Boot, unit tests, a server, or a container.
3. Cross-check the **exact file name** in the table in section 2; verify case and extension.
4. Verify that the file is actually at the **runtime classpath root** or is pointed to by an intentional path.
5. Check system properties and `logging.config`; ensure they are passed before logging initializes.
6. Look for test file names or configurations bundled by libraries/agents that may be selected unexpectedly.
7. Enable backend diagnostics per the official documentation when you need to verify which file was loaded; seeing a single DEBUG line is not enough to prove the entire configuration is right.
8. Re-verify on a production-like packaged/deployed setup, because the classpath and current working directory can change.

## 10. Practice Exercises

### Exercise 1: JUL with an Arbitrary File Name

Run the section 4 example using `conf/dev-logging.properties` and verify the two INFO/FINE lines. Rename the file to `conf/local-logging.properties` and update the system property accordingly. Explain why renaming the file alone is not enough.

### Exercise 2: Logback in Main and Test

Create two files, `logback.xml` and `logback-test.xml`, in `src/main/resources` and `src/test/resources`. Give each file a different pattern, such as `APP` and `TEST`. Run a test and then run the application; observe which file is selected. Explain the benefit of not packaging test resources into production.

### Exercise 3: Spring Boot Configuration Selection

In a Spring Boot application with a Logback backend, place `src/main/resources/config/logback-custom.xml` and point `logging.config` to `classpath:config/logback-custom.xml`. Compare the result with `logback-spring.xml` at the classpath root, and identify when the `-spring` name is required to enable Spring extensions.

### Exercise 4: Investigating a Deployment Environment

Suppose an application runs on Linux, unlike the Windows development machine. The file is named `LogBack.xml` and the JVM is launched with a `-D` flag placed after `-jar`. Identify the two reasons why the configuration is not picked up, and write the correct startup command and file name.

## 11. Key Takeaways

A logging configuration file name only matters when paired with the **right backend, right startup mode, and right loading location**. JUL normally reads the JDK's `logging.properties` or an explicitly specified file; Logback normally searches for `logback-test.xml`/`logback.xml`; Log4j 2 searches the `log4j2-test`/`log4j2` group; Spring Boot supports `-spring` names and `logging.config`. Configuration files and log output files serve two different purposes. When troubleshooting, always start from the actual backend, classpath, and startup arguments.

### Official Documentation

- Oracle Java 17 – LogManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html
- Oracle Java 17 – ConsoleHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html
- Oracle Java 17 – SimpleFormatter: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/SimpleFormatter.html
- Logback manual – Configuration: https://logback.qos.ch/manual/configuration.html
- Logback FAQ – Classpath location: https://logback.qos.ch/faq.html
- Apache Log4j 2 – Configuration: https://logging.apache.org/log4j/2.x/manual/configuration.html
- Apache Log4j 2 – FAQ: https://logging.apache.org/log4j/2.x/faq.html
- Spring Boot – Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
