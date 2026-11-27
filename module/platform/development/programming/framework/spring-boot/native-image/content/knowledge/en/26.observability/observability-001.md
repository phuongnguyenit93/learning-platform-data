# Logging and Dynamically Loaded Configuration or Layout Components

Spring Boot initializes the logging system very early, before the `ApplicationContext` is created. Configuration can come from files on the classpath, an external file specified via `logging.config`, or properties such as `logging.level.*` and `logging.file.name`. Logback and Log4j2 also allow configuration files to reference an appender, encoder, layout, converter, filter, or plugin by class name.

With GraalVM Native Image, you must distinguish between two things:

- **Loading configuration at runtime:** the process reads an external XML/properties/YAML file to choose log levels, patterns, appenders, or file outputs. This works as long as the file and required components are available when the process runs.
- **Loading code components dynamically:** the configuration asks to instantiate an appender, layout, encoder, or converter by class name. That class must be part of the code included in the native image, and any dynamically accessed constructors/members must have appropriate metadata.

An external configuration file can change after release, but it cannot add new class bytecode to an already compiled executable. Reflection hints only describe how to access classes that already exist; they do not bring new dependencies into the image.

This lesson belongs to the **Observability** chapter of the `SPRING_BOOT_NATIVE_IMAGE` module. We will explore when logging is initialized, how to choose configuration files, how to use Logback/Log4j2, which components can be dynamically configured, the required Runtime Hints, and how to test logging in a native executable.

## 1. Logging Is Initialized Before ApplicationContext

Spring Boot uses the `LoggingSystem` abstraction to select and configure the logging backend based on the classpath. When using standard starters, Logback is typically the default choice. Log4j2 or Java Util Logging can be used if the corresponding dependencies and configuration are present.

Logging is prepared very early, before the `ApplicationContext` is complete. Therefore, you cannot rely on `@PropertySource` in a `@Configuration` class to choose the logging system or provide all properties needed for the initial setup step.

Common early configuration sources:

- Environment variables, such as `LOGGING_CONFIG` or `LOGGING_LEVEL_COM_EXAMPLE_ORDERS`.
- Java system properties, such as `-Dlogging.config=...`.
- Command-line properties accepted by Spring Boot during startup.
- Configuration files in standard locations or explicitly specified locations.

| Need | Commonly used property |
| --- | --- |
| Change package log level | `logging.level.com.example.orders=DEBUG` |
| Select logging config file | `logging.config=file:/etc/orders/logback-spring.xml` |
| Write logs to file | `logging.file.name=/var/log/orders/orders.log` |
| Select default log level | `logging.level.root=INFO` |
| Set application name | `spring.application.name=orders-service` |

With a native image, these properties can still be supplied when the process starts. However, if the logging file references a custom class, that class and the necessary metadata must be handled during the build.

## 2. Distinguishing Configuration Files, Resources, and Code Components

A logging XML file can contain several kinds of information:

1. **Configuration values:** log levels, patterns, file paths, rolling policies, timeouts, or endpoints.
2. **Resource references:** included files, properties files, or auxiliary files.
3. **Class references:** custom appenders, encoders, layouts, converters, filters, or plugins.
4. **Reload mechanisms:** watching a file and re-reading configuration when its contents change.

These categories have different native requirements:

| Component | Example | Native image handling required |
| --- | --- | --- |
| Property | `logging.level.root=DEBUG` | Provide before/at startup or via logger management mechanism |
| Classpath configuration file | `logback-spring.xml` | Ensure the resource is packaged if runtime needs to read it |
| External configuration file | `/etc/orders/logback-spring.xml` | Mount the file and grant read permissions at runtime |
| Custom appender | `com.example.logging.AuditAppender` | Class must exist in the image; add reflection hints if needed |
| Custom converter/layout | Class specified in XML | Class and required constructors/members must be retained |
| Included file | `logging/includes/console.xml` | Ensure the resource is in the image or the external file exists |
| File reload | Logback scan or backend-specific reconfiguration | Only changes configuration of existing components; must be tested per backend/version |

A native executable can read external files, but the executable's classpath is fixed at build time. This is a boundary to keep clear in your logging design.

## 3. Selecting Logging Config with logging.config

Spring Boot automatically discovers logging configuration according to the backend's conventions. You can specify a different location using the `logging.config` property.

Example with an external file:

```bash
LOGGING_CONFIG=file:/etc/orders/logback-spring.xml ./orders-service
```

In a container environment, the configuration file can be mounted from a ConfigMap, volume, or separate deployment artifact. The process needs read permissions for the file and any included files referenced by the configuration.

```dockerfile
FROM debian:bookworm-slim
WORKDIR /app

COPY orders-service /app/orders-service
ENV LOGGING_CONFIG=file:/etc/orders/logback-spring.xml

ENTRYPOINT ["/app/orders-service"]
```

You can mount the file at runtime:

```bash
docker run --rm \
  -v ./logging:/etc/orders:ro \
  -e LOGGING_CONFIG=file:/etc/orders/logback-spring.xml \
  orders-service:native
```

Do not expect a bean or `@PropertySource` to provide `logging.config` early enough. Use a configuration source available immediately when the process starts.

## 4. Using logback-spring.xml with Spring Boot

If the backend is Logback and you need Spring Boot extensions, use `logback-spring.xml`. The standard `logback.xml` file is loaded by Logback itself too early, preventing Spring Boot from fully applying its extensions.

Example:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration scan="false">
    <include resource="org/springframework/boot/logging/logback/defaults.xml"/>
    <include resource="org/springframework/boot/logging/logback/console-appender.xml"/>

    <springProperty scope="context"
                    name="applicationName"
                    source="spring.application.name"
                    defaultValue="orders-service"/>

    <springProfile name="dev">
        <logger name="com.example.orders" level="DEBUG"/>
    </springProfile>

    <springProfile name="prod">
        <logger name="com.example.orders" level="INFO"/>
    </springProfile>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

The example uses `<springProperty>` to read a property from the Spring Environment and `<springProfile>` to apply configuration by profile.

Set `scan="false"` when using Spring Boot Logback extensions. The Spring Boot documentation explicitly states that these extensions are incompatible with Logback configuration scanning: when Logback re-reads the file itself, it lacks the Spring extension actions and can fail on `springProperty` or `springProfile`.

Profiles used in logging must match the profiles supplied when starting the native process. AOT does not turn the logging file into a place where new beans or classes can be added.

## 5. Changing Log Levels Without Custom Layouts

If the only requirement is changing log levels or enabling/disabling logs for a package, there is no need to create a custom appender/layout. Use standard properties:

```yaml
logging:
  level:
    root: INFO
    com.example.orders: DEBUG
    org.springframework.web: WARN
```

You can override them with environment variables:

```bash
LOGGING_LEVEL_ROOT=INFO
LOGGING_LEVEL_COM_EXAMPLE_ORDERS=DEBUG
./orders-service
```

Spring Boot also supports `--debug` and `--trace` for certain core logger groups. They do not mean enabling DEBUG/TRACE for every logger in the application.

With Spring Boot Actuator, the `/actuator/loggers` endpoint can view and change log levels at runtime. Example:

```http
POST /actuator/loggers/com.example.orders
Content-Type: application/json

{
  "configuredLevel": "DEBUG"
}
```

This changes logger state in a running process, rather than loading a new layout class. Expose management endpoints only on trusted networks, apply appropriate authentication/authorization, and avoid exposing this endpoint without control.

When the process restarts, log levels revert to the startup configuration unless the configuration management system supplies the new values again.

## 6. Which Components Are Dynamically Loaded from Logging Configuration?

Logging backends typically allow configuration to reference classes by name:

| Component | Role | Example |
| --- | --- | --- |
| Appender | Sends logs to console, file, socket, or external system | `AuditAppender` |
| Encoder | Converts a logging event into bytes/text | `PatternLayoutEncoder` |
| Layout | Formats an event into a string or structure | `JsonLayout` |
| Converter | Converts a pattern token into a value | Custom Logback converter |
| Filter | Decides whether an event is accepted | Custom threshold/tenant filter |
| Plugin | Extension component per backend mechanism | Log4j2 plugin |
| Configurator/Provider | Participates in backend initialization | Logback Configurator via service provider |

Example Logback XML referencing a custom appender:

```xml
<appender name="AUDIT"
          class="com.example.logging.AuditAppender">
    <destination>/var/log/orders/audit.log</destination>
</appender>
```

The backend must instantiate the class and configure the corresponding properties. This process may rely on reflection or its own discovery mechanism. Native Image cannot implicitly infer every class that only appears in an XML string.

To use a custom component in a native image, you need to verify:

1. Is the class in the build's source/dependencies?
2. Is the class retained in the native executable?
3. Does the logging framework instantiate the class via reflection, service loading, or a plugin registry?
4. Which constructors, setters, or members are accessed dynamically?
5. Does the dependency already provide reachability metadata?
6. If not, does the application need to declare Runtime Hints?

## 7. Custom Logback Appender Example

Suppose an application has an appender that writes audit events to a separate file. This is a simplified example to illustrate a class referenced by XML:

```java
package com.example.logging;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.AppenderBase;

public class AuditAppender extends AppenderBase<ILoggingEvent> {

    private String destination;

    public void setDestination(String destination) {
        this.destination = destination;
    }

    @Override
    protected void append(ILoggingEvent event) {
        if (destination == null || destination.isBlank()) {
            addError("Audit destination is not configured");
            return;
        }

        try {
            Path path = Path.of(destination);
            Path parent = path.getParent();
            if (parent != null) {
                Files.createDirectories(parent);
            }
            Files.writeString(
                    path,
                    event.getFormattedMessage() + System.lineSeparator(),
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);
        }
        catch (IOException ex) {
            addError("Cannot write audit event", ex);
        }
    }
}
```

In a real-world application, an appender must handle lifecycle, buffering, concurrency, backpressure, I/O errors, and sensitive data. The example above only demonstrates the class and setter that Logback can instantiate/configure from XML.

Configuration:

```xml
<appender name="AUDIT"
          class="com.example.logging.AuditAppender">
    <destination>/var/log/orders/audit.log</destination>
</appender>

<root level="INFO">
    <appender-ref ref="CONSOLE"/>
    <appender-ref ref="AUDIT"/>
</root>
```

The `AuditAppender` class must be in the dependency graph before the native image is built. Changing the XML file after release to point to `com.vendor.NewAppender` cannot make that class appear in the executable if it was not built with the application.

## 8. Adding Runtime Hints for Custom Logging Components

If Logback instantiates the appender via reflection and Spring AOT/dependency metadata does not yet describe the required constructor or setter, the application can register hints.

```java
package com.example.logging;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class LoggingRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
                AuditAppender.class,
                MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS);
    }
}
```

Attach the registrar to the AOT configuration:

```java
package com.example.logging;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(LoggingRuntimeHints.class)
public class LoggingNativeConfiguration {
}
```

The example registers constructors and public methods because Logback needs to instantiate the appender and invoke the `setDestination` setter. Choose categories according to how the backend actually accesses the class. Do not register all members of every logging class out of habit.

If a dependency already packages native metadata for that component, do not duplicate the hint in the application. If a class is named in XML but not directly referenced elsewhere, having hints still needs to be verified with a native build and tests. Hints cannot replace a dependency or bring a class not present in the build into the executable.

## 9. Classpath Configuration Files and External Configuration Files

There are two ways to provide configuration:

| Source | Example | Characteristics |
| --- | --- | --- |
| Classpath resource | `src/main/resources/logback-spring.xml` | Packaged inside the artifact; modifying the file usually requires rebuilding |
| External file | `/etc/orders/logback-spring.xml` | Can be mounted/changed independently of the native executable |
| External include | `/etc/orders/includes/audit.xml` | Must exist and have read permissions at runtime |
| External properties | `/etc/orders/logging.properties` | May be supported by the backend according to its format/mechanism |

If a classpath file is read by the logging backend using a dynamic resource name, verify that the resource has been included in the native image. Spring AOT can automatically infer some resources from integrations the framework knows about, but you should not assume every file read by third-party libraries is discovered.

If a resource hint is missing, you can declare it:

```java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

class LoggingResourceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("logback-spring.xml");
        hints.resources().registerPattern("logging/includes/audit.xml");
    }
}
```

Only register classpath resources that are actually used. For an external file such as `/etc/orders/logback-spring.xml`, the file does not need to be embedded in the executable; it needs to be present on the container/host filesystem and readable by the process.

Do not put configuration files containing credentials, tokens, or sensitive internal endpoints into an image layer unnecessarily. Supply sensitive values via a secret/config mechanism at runtime.

## 10. Referencing Properties in Logback Configuration

Spring Boot transfers several logging properties to system properties so the backend can use them. For example, `logging.file.name` can provide `LOG_FILE`; `logging.pattern.console` provides `CONSOLE_LOG_PATTERN`.

A configuration can use these properties:

```xml
<configuration scan="false">
    <include resource="org/springframework/boot/logging/logback/defaults.xml"/>
    <include resource="org/springframework/boot/logging/logback/console-appender.xml"/>

    <property name="AUDIT_LOG" value="${LOG_PATH:-/var/log/orders}/audit.log"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Pay attention to placeholder syntax. In Logback XML, Logback's default value syntax typically uses `:-`. When using placeholders in properties processed by Spring Boot, use the corresponding Spring Boot syntax and do not mix them arbitrarily. Consult the backend documentation for each property type.

Some Spring Boot properties transferred to system properties:

| Spring Environment property | Commonly used system property |
| --- | --- |
| `logging.file.name` | `LOG_FILE` |
| `logging.file.path` | `LOG_PATH` |
| `logging.pattern.console` | `CONSOLE_LOG_PATTERN` |
| `logging.pattern.file` | `FILE_LOG_PATTERN` |
| `logging.charset.console` | `CONSOLE_LOG_CHARSET` |
| `logging.pattern.level` | `LOG_LEVEL_PATTERN` |

These properties help change runtime values without replacing encoder/layout classes. If you only need to change a pattern or file path, prefer supported properties before creating custom components.

## 11. Dynamic Reload with Logback Scan

Logback supports watching a configuration file and re-reading it when the file changes via the `scan` attribute:

```xml
<configuration scan="true" scanPeriod="30 seconds">
    <!-- appender and logger configuration -->
</configuration>
```

This mechanism can be useful when running on the JVM and needing to reload external configuration. However, there are important limitations:

- Spring Boot extensions such as `<springProfile>` and `<springProperty>` are incompatible with Logback configuration scanning.
- When Logback re-parses the file itself, the reload process does not necessarily go through Spring Boot logging extensions.
- Reloading can change log levels, appenders, or patterns that already exist; it does not add new class bytecode to the native executable.
- Classpath files inside the executable are not external mutable files that operators can edit directly.
- Reconfigured custom components must still have their classes and required metadata in the binary.

With `logback-spring.xml` using Spring extensions, keep `scan="false"`. If you need to reload configuration, verify the behavior of the specific backend and version using an actual native executable; do not assume JVM behavior will be identical to native.

If the goal is only to change log levels, the Actuator Loggers endpoint or re-supplying properties on restart is usually easier to control than reloading the entire XML.

## 12. Log4j2 and Plugin Configuration

If the application uses Log4j2, Spring Boot supports `log4j2-spring.xml` to use extensions such as profiles and lookups from the Spring Environment. The standard `log4j2.xml` file is read by Log4j2 too early for Spring Boot to apply all extensions.

Log4j2 has its own plugin mechanism. Plugins are typically discovered through metadata generated by an annotation processor/plugin tooling, such as a plugin cache in the JAR. When using a custom Log4j2 appender, layout, or filter, you must:

1. Ensure the plugin is compiled/packaged properly.
2. Ensure the plugin metadata is generated and included in the dependency/artifact.
3. Check the reachability metadata or hints needed for the native image.
4. Build and run native tests with the exact plugin configuration.
5. Verify that transitive dependencies of the appender/layout are present in the runtime image.

Do not mechanically apply Logback Runtime Hints to Log4j2. The two backends have different discovery mechanisms, plugin registries, and component instantiation. Use the plugin mechanism and native metadata supported by the Log4j2 version you are using.

## 13. Custom Structured Logging Formatter

Spring Boot versions provide a structured logging API that lets you choose formats such as ECS, GELF, or Logstash. If you need a custom format, you can implement `StructuredLogFormatter` appropriate for the backend.

Example with Logback:

```java
import ch.qos.logback.classic.spi.ILoggingEvent;
import org.springframework.boot.logging.structured.StructuredLogFormatter;

public class AuditJsonFormatter
        implements StructuredLogFormatter<ILoggingEvent> {

    @Override
    public String format(ILoggingEvent event) {
        return "{\"level\":\"" + event.getLevel()
                + "\",\"message\":\""
                + escape(event.getFormattedMessage()) + "\"}";
    }

    private String escape(String value) {
        return value.replace("\\", "\\\\")
                .replace("\"", "\\\"");
    }
}
```

You can select the formatter by class name via the corresponding structured logging property, such as `logging.structured.format.console` or `logging.structured.format.file`. The property can accept a built-in format identifier or a formatter class name depending on the Spring Boot version.

Because the custom class is selected by a configuration name, you must ensure the class is in the build and that the required constructors/metadata are retained by the native image. If the formatter has constructor dependencies or requires complex configuration, check the instantiation contract of the Spring Boot version you are using instead of assuming it is created like a regular Spring bean.

Structured logging also requires checking escaping, newlines, Unicode, exceptions/stack traces, MDC, and sensitive data. Building JSON with string concatenation is only a minimal example; production should use a proper serializer to avoid invalid JSON.

## 14. Choosing a Mechanism Based on the Required Level of Change

Not every "change logging at runtime" requirement needs XML reloading or a custom layout.

| Operational need | Mechanism to consider | Native rebuild required? |
| --- | --- | --- |
| Change root/package log level | Startup environment/property or Actuator Loggers | No |
| Change output file/path | `logging.file.name` or external config | No, if supported by backend and path is valid |
| Change pattern/rolling policy | Spring Boot property or external config | No, if only changing values and components already exist |
| Select an appender already in the binary | External config if supported by backend | No |
| Select a new custom appender not in the image | Add dependency/code then rebuild native | Yes |
| Switch custom formatter/layout to a new class | Add class and metadata, rebuild | Yes |
| Install arbitrary logging plugins after deploy | Native executable is not a classloader plugin host by default | Requires rebuild or separating into a plugin process/service |
| Change appender secret/endpoint | Runtime secret/config mount if supported by component | No, though restart/reload may be needed |
| Reload external XML | Backend-specific scan/reconfiguration; verify native behavior | Usually no if only using existing components |

Practical rule: **configuration can change data and choices; code components must reside in the built codebase**.

## 15. Testing Logging Configuration in Native Image

You should test across multiple layers:

1. JVM startup test to confirm the XML file is valid and the backend initializes properly.
2. AOT/native build to detect dynamic classes/resources missing metadata.
3. Native executable test to confirm the appender/layout is instantiated and writes logs.
4. Runtime configuration test with an external config mount if production uses external files.
5. Reload test if scanning/reconfiguration is actually enabled.

A behavioral test can confirm that the custom appender writes events:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

class AuditLoggingTests {

    @Test
    void writesAuditMessage() {
        Logger logger = LoggerFactory.getLogger("com.example.orders.audit");
        logger.info("invoice-created");

        Path output = Path.of("/tmp/orders-audit.log");
        await().atMost(Duration.ofSeconds(3))
                .untilAsserted(() ->
                        assertThat(Files.readString(output))
                                .contains("invoice-created"));
    }
}
```

This is an illustrative example; configure the appender destination and test dependencies accordingly. In CI, use a separate temporary directory per test, clean up files after running, and avoid relying on hardcoded paths from a developer's machine.

For the native executable, verify:

- The process starts with the right configuration file.
- Custom appender/layout classes are instantiated.
- Events are written to the expected output.
- Log levels and patterns follow the configuration.
- Included files/resources are found.
- The process running under the actual container UID has write permissions.
- External config is read properly.
- If using reload, changes are applied without causing Spring extension errors.

Do not just check for the "Started" log on the console. A custom appender can fail later when writing the first event.

## 16. Investigating Common Errors

| Symptom | Cause to check | Resolution |
| --- | --- | --- |
| Native image cannot find Logback XML file | Classpath resource not included in image or `logging.config` is wrong | Check resource hints, AOT output, and runtime path |
| External config is not read | `LOGGING_CONFIG` missing at logging init time or file not mounted | Supply the variable before process start and check read permissions |
| `springProperty`/`springProfile` errors on reload | Logback scan re-parses the file itself without Spring extensions | Disable `scan` or use an appropriate reload mechanism |
| Custom appender is not created | Class missing from image or missing constructor/member metadata | Check dependencies, Runtime Hints, and native stack trace |
| Appender is created but setter does not run | Reflection access for public methods/property setter insufficient or XML property wrong | Verify setter and exact metadata |
| Custom converter is not recognized | Conversion rule not registered or class missing from binary | Check XML, converter class, and hints |
| Log4j2 cannot find plugin | Plugin metadata/cache not generated or packaged | Check annotation processor, plugin cache, and dependencies |
| Log file is not written in container | Directory does not exist or UID lacks write permissions | Create/mount directory and grant appropriate permissions |
| Reloading XML does not swap the class | New class is not in the native executable | Rebuild with the new class/dependency |
| Actuator does not change log level | Endpoint not exposed/authorized or logger name is wrong | Check management endpoints and security policy |

When an error only occurs on native, identify whether it lies in reading a resource, instantiating a class, reflection, file I/O, or the loader. Do not add hints for every logging package before knowing which operation lacks metadata.

## 17. Reproducible Deployment Workflow

1. Choose a backend and version compatible with Spring Boot/GraalVM.
2. Use standard properties for log levels, file output, and patterns if they meet your needs.
3. If detailed configuration is needed, choose `logback-spring.xml` or `log4j2-spring.xml`.
4. Decide whether the configuration file resides on the classpath or is mounted externally.
5. List custom appenders, encoders, layouts, converters, filters, or plugins referenced by XML.
6. Verify that the classes and dependencies are in the build inputs.
7. Check available metadata; only add Runtime Hints for missing dynamic access.
8. Run JVM logging tests and the Spring AOT/native build.
9. Run the native executable in a production-like environment.
10. Verify log output, file permissions, rolling policy, and external config.
11. If using reload, separately verify behavior on the exact backend/version/native image.
12. Version configuration files, plugins, and toolchains for reproducible releases.

## 18. Pre-Release Checklist

- [ ] Logging backend and dependencies are explicitly selected.
- [ ] `logging.config` is supplied before the logging system initializes.
- [ ] `logback-spring.xml` or `log4j2-spring.xml` is used when Spring extensions are needed.
- [ ] Logback `scan` is not enabled if using Spring Boot Logback extensions.
- [ ] Required classpath files are in the native image; external files have proper mounts and permissions.
- [ ] Custom appenders/layouts/encoders/converters/plugins are included in the build inputs.
- [ ] Reflection hints only cover constructors/members actually accessed dynamically.
- [ ] Dependency metadata is checked before creating duplicate hints.
- [ ] Custom structured formatters are verified against the Spring Boot version.
- [ ] Logger levels, patterns, file outputs, and rolling policies have been tested on the native executable.
- [ ] The Actuator Loggers endpoint is secured if runtime log level changes are enabled.
- [ ] There is no expectation that external XML can load classes not compiled into the executable.
- [ ] Credentials, tokens, or sensitive data are not written to logs.
- [ ] The container UID has permission to write log files, or logs are emitted via stdout/stderr per the operating platform.

### Self-Assessment Questions

1. Why must `logging.config` be provided before the `ApplicationContext` is created?
2. What is the difference between changing a log level via a property and loading a custom appender by class name?
3. Why does `logback-spring.xml` require care with the `scan` attribute?
4. An external XML file can be changed after deployment, so why can it not add a new custom layout class to a native executable?
5. When are Runtime Hints needed for a custom appender or converter?
6. Why are a resource hint for a classpath file and mounting an external config two different things?
7. What can Spring Boot Actuator Loggers change, and what can it not change?
8. When native logging fails, in what order should you check resources, class reachability, reflection, or file permissions?

## References

- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): logging system, `logging.config`, Logback/Log4j2 configuration, structured logging, and Actuator integration.
- [Spring Boot — Logging How-to](https://docs.spring.io/spring-boot/how-to/logging.html): configuring Logback, included files, custom logging configuration, and structured formats.
- [Spring Boot — GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html): closed-world, fixed classpath, and metadata requirements for dynamic access.
- [Spring Boot — Advanced Native Image Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html): Runtime Hints, resource hints, and testing custom hints.
- [Logback — Configuration](https://logback.qos.ch/manual/configuration.html): how Logback discovers, reads, and reloads configuration files.
- [Logback — Configuration XML](https://logback.qos.ch/manual/configuration-xml.html): appenders, encoders, layouts, converters, and XML elements.

**Key takeaway:** you can configure logging via properties or external files in a native executable, understand when resource/reflection hints are needed for custom components, and recognize the limits of reloading or dynamic class loading. Configuration files can change at runtime, whereas appender/layout/converter code must be present in the native image from build time.
