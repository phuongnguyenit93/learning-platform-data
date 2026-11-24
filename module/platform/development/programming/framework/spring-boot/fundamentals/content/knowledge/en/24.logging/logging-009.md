# Early Logging Initialization and Why Some Configuration Sources Arrive Too Late

Logging is one of the infrastructures that Spring Boot prepares **very early** during startup. This is necessary because if the application fails while reading configuration, creating the `ApplicationContext`, or registering beans, we still need logs to see what happened.

However, an important consequence is that **not every configuration source is available when the logging system starts operating**. A property declared in `@PropertySource`, a `@Configuration` bean, or code inside `@PostConstruct` may appear too late to affect the earliest log lines. Sometimes it even arrives too late to reconfigure logging in the way Spring Boot supports.

This lesson explains the logging initialization sequence, distinguishes early vs late configuration sources, shows how to use `logging.*`, `logback-spring.xml`, and appropriate extension points, and covers how to diagnose when logging does not run as expected.

## 1. Logging must work before the application itself

A typical Spring Boot application:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Inside `SpringApplication.run(...)`, many steps occur **before** `@Component` or `@Service` beans are created:

- Preparing listeners and bootstrap steps.
- Creating, preparing, and populating data sources into the `Environment`.
- Determining initial logging configuration.
- Creating the `ApplicationContext` and loading bean definitions.
- Refreshing the context, running BeanPostProcessors, and instantiating singletons.
- Executing runners and publishing the application-ready event.

If an error occurs in one of the earliest steps, the application does not yet have a complete `ApplicationContext`. Therefore, Spring Boot must initialize logging via a mechanism **outside the regular bean lifecycle**, rather than waiting for a `@Bean LoggingService` to be instantiated.

### Diagram of two key milestones

~~~text
main()
  |
  v
SpringApplication.run(...)
  |
  v
ApplicationStartingEvent
  |             Environment not yet fully prepared
  |             ApplicationContext not yet created
  |             Logging may be in very early initialization mode
  v
Prepare Environment and configuration data
  |
  v
ApplicationEnvironmentPreparedEvent
  |             Environment is ready for this stage
  |             Logging is configured according to Environment
  |             Context still not fully constructed
  v
Create and prepare ApplicationContext
  |
  v
Load @Configuration / @PropertySource / bean definitions
  |
  v
Refresh context, instantiate beans, @PostConstruct
  |
  v
ApplicationStartedEvent, runners, ApplicationReadyEvent
~~~

This is a conceptual diagram. Spring Boot executes internal Environment processing steps and listeners in a version-specific order; what to remember is that logging already begins operating **before application beans are instantiated**.

## 2. Distinguishing initial logging setup from Environment-based logging configuration

During bootstrap, two phases with different characteristics appear:

1. **Very early initialization:** the system must be able to emit initial messages even before the Environment has been fully processed.
2. **Environment-based configuration:** once appropriate property sources are prepared, Spring Boot can apply log levels, patterns, output files, and logging framework settings from the known values.

In Spring Boot, `LoggingApplicationListener` is a key component participating in these phases. It listens to early `SpringApplication` events, uses the `LoggingSystem` matching the present logging infrastructure, and configures logging based on information available at that point.

You can picture it as:

~~~text
     Bootstrap logging
             |
             | receives appropriate config sources
             v
     Environment-based logging
             |
             | application context created afterward
             v
     Logs from service/repository/controller
~~~

Do not assume every single startup log line must share the exact same pattern or level. Messages emitted **before the final configuration is applied** cannot be retroactively "reformatted" or re-filtered later.

### 2.1. Why is it important to know both phases?

Suppose the application wants to enable debug for its package:

~~~properties
logging.level.com.example.catalog=DEBUG
~~~

If this property is read in time during Environment preparation, messages emitted after `LoggingSystem` applies the configuration will use the new level. However, if a `DEBUG` log was already filtered out **before** that point, it will not reappear just because configuration later switched to `DEBUG`.

Similarly, changing the console pattern after startup cannot re-print lines already written to the console in the new pattern.

## 3. Which logging framework does Spring Boot use?

Spring Boot provides the `LoggingSystem` abstraction to work with supported logging backends. In applications using standard `spring-boot-starter` and `spring-boot-starter-logging`, the common backend is **Logback**, with SLF4J serving as the logging API in application code.

Example service:

~~~java
package com.example.catalog.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private static final Logger log =
            LoggerFactory.getLogger(CatalogService.class);

    public void refreshCatalog() {
        log.info("Refreshing catalog");
    }
}
~~~

The service does not need to know which file holds the specific Logback configuration. It calls SLF4J, and the configured logging system determines levels, patterns, appenders, and output destinations.

Projects can swap the backend to **Log4j2** or use Java Util Logging depending on dependencies. Native configuration file names and integration capabilities depend on the chosen backend. The XML examples in this lesson primarily use Logback.

**Core point:** Spring Boot manages logging very early, rather than waiting for `CatalogService` or any logger bean to appear.

## 4. Configuration source groups by arrival timing

Not all property sources are processed at the same time.

| Configuration source | Relevant timing | Usable to configure logging when Boot prepares Environment? |
|---|---|---|
| JVM system properties passed at launch | Present from JVM start | Usually yes |
| Process environment variables | Present before application starts | Usually yes |
| Command-line arguments to `SpringApplication` | Added to Environment during bootstrap | Usually yes |
| `application.properties` / `application.yml` via Config Data | Processed during Environment preparation | Yes, for the Environment-based logging stage |
| `application-{profile}.yml` | Processed per profile in config data | Yes, if the profile is determined in time |
| Boot-supported config imports | Processed during Config Data bootstrap | Yes, depending on source and integration |
| Early-registered `EnvironmentPostProcessor` | Participates in Environment processing | Potentially yes, if applied before logging reads config |
| `@PropertySource` on `@Configuration` | When context processes configuration classes | **Too late for logging bootstrap** |
| `@ConfigurationProperties` beans | When bean binding/creation runs | **Too late for logging bootstrap** |
| `@Bean` / `@PostConstruct` | During bean instantiation lifecycle | **Too late for already-emitted logs** |
| Runtime property changes | After context is running | Does not retroactively replay old logs or auto-sync all backends |

This table describes **Spring Boot's logging initialization mechanism**, not whether a property source can still be read by beans later. A late-arriving `@PropertySource` can still be useful for regular beans; it is simply not the right tool to govern logging from the initial stages.

## 5. Typical logging configuration with application.yml

For most applications, `application.yml` or `application.properties` is the natural choice for common logging settings:

~~~yaml
spring:
  application:
    name: catalog-service

logging:
  level:
    root: INFO
    com.example.catalog: DEBUG
    org.springframework.web: WARN
  pattern:
    console: "%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n"
~~~

Meaning:

- `logging.level.root`: default level of the root logger.
- `logging.level.com.example.catalog`: level for the relevant logger/package.
- `logging.level.org.springframework.web`: lowers or changes log verbosity for a framework area.
- `logging.pattern.console`: overrides the console display pattern when supported by the backend/logging configuration.

Equivalent `application.properties` version:

~~~properties
logging.level.root=INFO
logging.level.com.example.catalog=DEBUG
logging.level.org.springframework.web=WARN
logging.pattern.console=%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n
~~~

These properties are read by Boot during the `Environment`-based logging configuration step, before normal application singleton beans are used.

### 5.1. What if logging already started before application.yml is read?

Very early messages can appear before all Config Data is processed. Therefore, there is a distinction between:

- Logs right as `SpringApplication` begins.
- Logs after the Environment is prepared and `LoggingSystem` applies configuration.

Placing `logging.level.*` in `application.yml` is the Boot-supported approach for application logging, yet **it does not guarantee retroactively affecting logs emitted before configuration was applied**.

## 6. Why does @PropertySource arrive too late?

This is an important case.

Suppose you create `src/main/resources/custom-logging.properties`:

~~~properties
logging.level.com.example.catalog=DEBUG
logging.pattern.console=%d{HH:mm:ss} %-5level %logger - %msg%n
~~~

And import it via a configuration class:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration
@PropertySource("classpath:custom-logging.properties")
public class CatalogConfiguration {
}
~~~

When does Spring process `@PropertySource`? During `@Configuration` parsing of the application context, which is **after SpringApplication has already begun preparing logging**.

~~~text
SpringApplication initializes logging
             |
             v
Environment-based logging setup
             |
             v
Create ApplicationContext
             |
             v
Parse CatalogConfiguration
             |
             v
Process @PropertySource
             |
             v
custom-logging.properties added to Environment
             |
             v
Other beans can read the property
~~~

Therefore, even though a bean can later read `logging.level.com.example.catalog` from the Environment, **the logging system already passed the point where it reads that configuration**.

### 6.1. How to spot this

A common situation:

~~~java
@Component
class Diagnostics {

    private final Environment environment;

    Diagnostics(Environment environment) {
        this.environment = environment;
    }

    @PostConstruct
    void show() {
        System.out.println(
                environment.getProperty(
                        "logging.level.com.example.catalog"
                )
        ); // May print DEBUG
    }
}
~~~

Yet application `DEBUG` logs still do not appear. Two facts can be true at the same time:

1. The property exists in the Environment **when the Diagnostics bean runs**.
2. `LoggingSystem` was configured **before that property was added**.

This is a **configuration timing issue**, not necessarily a binder bug or a misspelled property name.

### 6.2. Do not try to fix early logging with @PropertySource

A misguided attempt is adding more `@Import` annotations or reordering `@Configuration` classes hoping `@PropertySource` runs before `LoggingSystem`. That cannot move bean/configuration-class processing ahead of bootstrap events.

The right fix is usually moving logging properties to `application.yml`, environment variables, JVM system properties, or a Config Data source loaded during bootstrap.

## 7. @ConfigurationProperties also arrives too late for bootstrap logging

`@ConfigurationProperties` is great for organizing business configuration into Java objects, yet such classes are bound when Spring manages application beans.

Example:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.monitoring")
public record MonitoringProperties(boolean detailedLogs) {
}
~~~

~~~yaml
app:
  monitoring:
    detailed-logs: true
~~~

Do not write a bean using `MonitoringProperties` inside `@PostConstruct` expecting it to govern logs emitted while Boot was loading configuration:

~~~java
@Component
class LoggingInitializer {

    private final MonitoringProperties properties;

    LoggingInitializer(MonitoringProperties properties) {
        this.properties = properties;
    }

    @PostConstruct
    void initialize() {
        if (properties.detailedLogs()) {
            // Too late to affect logs already emitted earlier.
        }
    }
}
~~~

Property binding and logging bootstrap serve two different phases.

If an `app.monitoring.detailed-logs` value must influence early logging decisions, pull that value **directly from the Environment or Config Data during an appropriate bootstrap stage**, without going through a properties bean created later.

## 8. Why aren't @Bean, CommandLineRunner, and ApplicationReadyEvent early enough?

A bean declared in `@Configuration`:

~~~java
@Configuration(proxyBeanMethods = false)
class LoggingConfiguration {

    @Bean
    StartupLogConfigurer startupLogConfigurer() {
        return new StartupLogConfigurer();
    }
}
~~~

is processed after the context exists. `@PostConstruct` runs during the bean instantiation lifecycle. `CommandLineRunner` and `ApplicationRunner` are even later: they execute after context refresh completes.

You can picture it as:

~~~text
LoggingSystem is prepared
           |
           v
Spring context is created
           |
           v
@Bean / @PostConstruct
           |
           v
ApplicationStartedEvent
           |
           v
ApplicationRunner / CommandLineRunner
           |
           v
ApplicationReadyEvent
~~~

A runner can call APIs to **change levels from that moment forward**, yet it cannot recover logs already filtered out during bootstrap steps. For logging after the application is ready, runners and event listeners remain very useful; they simply cannot govern every message from the start of startup.

## 9. Choosing sources that arrive early enough

To ensure `logging.*` properties are present when Spring Boot applies Environment-based configuration, choose an appropriate source.

### 9.1. JVM system property

Example:

~~~bash
java -Dlogging.level.root=DEBUG -jar catalog.jar
~~~

`-Dlogging.level.root=DEBUG` is set by the JVM before `main()` runs. Place `-D...` **before** `-jar` so the Java launcher treats it as a JVM option.

### 9.2. Environment variable

POSIX shell example:

~~~bash
export LOGGING_LEVEL_ROOT=DEBUG
java -jar catalog.jar
~~~

PowerShell example:

~~~powershell
$env:LOGGING_LEVEL_ROOT = 'DEBUG'
java -jar catalog.jar
~~~

Spring Boot supports relaxed binding for many property name forms. For package-level logging, a variable such as:

~~~text
LOGGING_LEVEL_COM_EXAMPLE_CATALOG=DEBUG
~~~

can represent `logging.level.com.example.catalog`.

**Watch out for class-named loggers:** environment-variable mapping usually lowercases names, so it may not preserve exact casing of a fully-qualified class name. When configuring a specific class logger, `SPRING_APPLICATION_JSON` or a property source preserving exact names may be more suitable.

### 9.3. SpringApplication command-line argument

~~~bash
java -jar catalog.jar --logging.level.com.example.catalog=DEBUG
~~~

Arguments are added to the Environment by Spring Boot via the standard mechanism, suitable for Environment-based logging configuration. Still, this argument does not alter logs emitted before the Environment is processed.

### 9.4. application.yml

~~~yaml
logging:
  level:
    root: INFO
    com.example.catalog: DEBUG
~~~

This is usually the simplest way to version-control non-sensitive logging policies alongside the application.

### 9.5. Choosing the right source for the requirement

| Requirement | Source to consider |
|---|---|
| Default application log policy | `application.yml` or `application.properties` |
| Deployment-specific overrides | Environment variables / externalized config |
| Quick local check | Command-line argument |
| Value needed from JVM startup | JVM system property / pre-startup environment |
| Custom Config Data needing early load | `spring.config.import` or appropriate `EnvironmentPostProcessor` |
| Changing levels after startup | `LoggingSystem` or Actuator loggers, not bootstrap config |

Do not use beans or `@PropertySource` as channels to deliver logging configuration to steps that already ran before they are processed.

## 10. logging.config: specifying the logging configuration file

When needs go beyond `logging.level.*` or `logging.pattern.*`, an application can use the logging backend's configuration file.

Example with Logback:

~~~properties
logging.config=classpath:logback-spring.xml
~~~

Or:

~~~yaml
logging:
  config: classpath:logback-spring.xml
~~~

`logging.config` is used by Boot to locate the configuration file while configuring `LoggingSystem`.

The value can be supplied via environment:

~~~bash
export LOGGING_CONFIG=file:/etc/catalog/logback-spring.xml
java -jar catalog.jar
~~~

For startup to succeed, the specified resource must be accessible when `LoggingSystem` reads the file. Do not place the path inside a bean created only after application context refresh.

### 10.1. logback.xml differs from logback-spring.xml

With Logback:

- `logback.xml` is the native filename Logback can discover on its own during its own initialization.
- `logback-spring.xml` is the variant Spring Boot controls loading for and supports Spring-specific extensions in.

Spring Boot extension example:

~~~xml
<configuration>
    <springProperty
            scope="context"
            name="serviceName"
            source="spring.application.name"
            defaultValue="catalog"/>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%property{serviceName}] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <springProfile name="dev">
        <logger name="com.example.catalog" level="DEBUG"/>
    </springProfile>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Place the file at:

~~~text
src/main/resources/logback-spring.xml
~~~

`<springProperty>` and `<springProfile>` tags are Spring Boot extensions for Logback. When using them, let Boot orchestrate loading via `logback-spring.xml` or an appropriate `LoggingSystem` setup.

If you rename the exact example to `logback.xml` so native Logback reads it very early, Spring extensions may not be recognized at that moment.

### 10.2. Why can logback.xml "arrive before" Spring Boot?

A logging backend can initialize itself if code calls SLF4J/Logback before Spring Boot prepares the Environment. In that case:

~~~text
Native Logback finds logback.xml
            |
            v
Logback configures itself
            |
            v
Spring Boot only then begins preparing Environment
            |
            v
Spring Environment values are not ready for initial native config
~~~

Thus, **the earlier initialization happens, the less Spring-specific data is available**. `logback-spring.xml` lets Boot control loading to support Environment-dependent extensions.

`logback.xml` is not always wrong. A native file works fine if it uses only standard Logback syntax. Trouble arises when you expect it to read Spring profiles, Spring properties, or Boot extensions before the environment is ready.

### 10.3. Note on Logback auto-scan

Spring Boot does not support safely using all Spring-specific extensions with Logback's automatic reconfiguration (`scan`). If Logback reloads the file itself and parses `<springProfile>` or `<springProperty>` tags outside Boot's managed phase, tag recognition errors can occur.

When using Spring Boot extensions inside `logback-spring.xml`, avoid carelessly enabling Logback `scan="true"`. If runtime log level updates are needed, consider supported APIs or Actuator rather than relying solely on native auto-scan.

## 11. Logback native substitution and Spring placeholders are not the same

The Spring Environment and Logback handle property substitution differently. For example, in `application.yml`, Spring placeholders look like:

~~~yaml
app:
  log-directory: ${APP_LOG_DIRECTORY:/var/log/catalog}
~~~

In Logback XML, property references use Logback semantics or the corresponding `<springProperty>` extension.

### 11.1. springProperty reads from the Environment

~~~xml
<springProperty
        scope="context"
        name="logDir"
        source="app.log-directory"
        defaultValue="./logs"/>
~~~

The file can then use `logDir` in Logback syntax where appropriate.

### 11.2. Do not substitute with @Value in a bean

A bean such as:

~~~java
@Value("${app.log-directory}")
String logDirectory;
~~~

is injected only after the bean is created. It does not supply early values to Logback if the logging system already configured the file appender earlier.

### 11.3. Defaults and property names must match each system's syntax

Spring placeholders, Logback variable substitution, and Spring Boot's `springProperty` do not use the exact same parser. Do not copy default syntax verbatim from YAML to XML without checking the documentation of the tool parsing that string.

## 12. Logging to files: configuring at the right time

Spring Boot supports common properties for log files such as:

~~~properties
logging.file.name=logs/catalog.log
~~~

or:

~~~properties
logging.file.path=logs
~~~

Under Boot's mechanism, `logging.file.name` specifies the exact file; `logging.file.path` specifies the directory (using a default conventional filename when no specific name is set). If both are declared, precedence follows Boot semantics; in standard configurations, the explicit filename usually wins.

### 12.1. Volumes must exist before logging opens the file

An appender may need to open its file during logging initialization. If a mount directory does not exist yet, lacks permissions, or the disk is full, errors can happen **before beans finish initializing**.

For example, container deployments must mount volumes and set permissions beforehand:

~~~text
Container start
      |
      v
Filesystem / mounted log directory available
      |
      v
JVM and Spring Boot start
      |
      v
Logging backend opens file
      |
      v
ApplicationContext is created
~~~

Do not rely on `@PostConstruct` creating the log directory and assume it always runs before `FileAppender`. If a logging path is required, prepare the filesystem in deployment or bootstrap before `LoggingSystem` uses that path.

In containers, logging to stdout/stderr for collection systems is usually simpler than managing file appenders inside each instance, unless specific operational requirements dictate otherwise.

## 13. Profile-specific logging can be configured from Config Data

Example:

`application.yml`:

~~~yaml
logging:
  level:
    root: INFO
    com.example.catalog: INFO
~~~

`application-dev.yml`:

~~~yaml
logging:
  level:
    com.example.catalog: DEBUG
~~~

`application-prod.yml`:

~~~yaml
logging:
  level:
    root: WARN
    com.example.catalog: INFO
~~~

When profile `dev` or `prod` is determined during Environment preparation, Boot can load the corresponding configuration data before applying Environment-based logging.

How to specify a profile externally:

~~~bash
java -jar catalog.jar --spring.profiles.active=dev
~~~

Or:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
java -jar catalog.jar
~~~

### 13.1. Why doesn't @Profile on @Configuration solve early initialization logs?

~~~java
@Configuration
@Profile("dev")
class DebugLoggingConfiguration {
    // ...
}
~~~

Class `DebugLoggingConfiguration` is still evaluated when the Spring context processes configuration classes. It does not alter logging for `ApplicationStartingEvent` or earlier steps.

Use `application-dev.yml` or Logback `<springProfile>` in a Boot-loaded file at the right stage, rather than trying to configure early logging via `@Profile` + `@Bean`.

### 13.2. Profiles set in code can arrive too late

If a bean tries calling an API to add an active profile after context refresh, that does not make Spring Boot re-read all Config Data and reconfigure logging as if starting fresh.

Profiles must be provided/defined while Boot prepares the Environment if they are to influence config data and logging bootstrap.

## 14. EnvironmentPostProcessor: adding properties before logging uses the Environment

When an application/library needs to add a `PropertySource` **during bootstrap**, Spring Boot provides `EnvironmentPostProcessor`.

Example adding non-sensitive logging defaults:

~~~java
package com.example.catalog.boot;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public final class LoggingDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        Map<String, Object> defaults = Map.of(
                "logging.level.com.example.catalog", "INFO"
        );

        environment.getPropertySources().addLast(
                new MapPropertySource("catalogLoggingDefaults", defaults)
        );
    }
}
~~~

In the application/library JAR, register the processor via:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Content:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=com.example.catalog.boot.LoggingDefaultsEnvironmentPostProcessor
~~~

Spring Boot discovers properly registered processors and executes them during Environment processing.

### 14.1. Why addLast?

`addLast` places this property source at lower precedence than sources already in the Environment. This fits **defaults**, ensuring environment variables, command-line arguments, or operator-supplied config are not unintentionally overridden.

If you want to override other sources, carefully evaluate precedence policy and insertion position. Do not place a custom source first just so a debug level always beats production config.

### 14.2. EnvironmentPostProcessor still has its own timing

`EnvironmentPostProcessor` is designed for the Environment stage and can influence logging configuration applied afterward when registered/ordered properly. It **does not necessarily alter messages emitted before Environment processing**, such as logs from the very earliest bootstrap steps.

If ordering relative to another `EnvironmentPostProcessor` matters, check ordering and bootstrap dependencies. Do not rely on component scanning or `@Component` to register this processor, because component scanning runs too late.

### 14.3. Do not invoke complex loggers/beans too early in the processor

An `EnvironmentPostProcessor` must not depend on repository/service beans. Even logging itself requires care because logging may not yet be in its final configuration. Keep the processor small, deterministic, and free of AOP or database dependencies.

If logic reads remote config, it can stall or fail startup; establish appropriate timeouts and failure policies instead of treating environment processing as business execution.

## 15. spring.config.import and external configuration sources

Since Spring Boot 2.4, the Config Data mechanism allows using `spring.config.import` to load additional configuration data from supported locations.

Example:

~~~yaml
spring:
  config:
    import: "optional:file:/etc/catalog/logging-extra.properties"
~~~

If the file exists and is loaded properly during the Config Data stage, properties such as:

~~~properties
logging.level.com.example.catalog=DEBUG
~~~

can be available before `LoggingSystem` applies Environment-based configuration.

### 15.1. "optional" is not a security or config-assurance tool

The `optional:` prefix permits the import location to be absent under Config Data semantics. If external logging config is mandatory under operational policy, consider removing `optional:` or adding deployment checks.

### 15.2. Custom config sources must participate in the right bootstrap phase

If a library defines a custom config import location or remote configuration, it must integrate with Config Data/Environment processing at the appropriate point. A bean appearing after refresh and injecting properties into the Environment cannot act identically to a Config Data source loaded during bootstrap.

## 16. Why doesn't mutating the Environment after startup automatically update logging?

Suppose after the application is already running:

~~~java
ConfigurableEnvironment environment = ...;

environment.getPropertySources().addFirst(
        new MapPropertySource(
                "runtimeOverride",
                Map.of("logging.level.com.example.catalog", "TRACE")
        )
);
~~~

This modifies the properties `Environment` returns from that point forward. However, **`LoggingSystem` does not automatically register a watcher on all `Environment` property source mutations** to reconfigure the backend whenever values change.

Therefore:

~~~text
Environment value is modified
            |
            v
Environment.getProperty(...) returns new value
            |
            X
Does not automatically force LoggingSystem to reinitialize
            |
            v
Actual logger level can remain at old value
~~~

The proper way when dynamic level changes are needed is calling an appropriate logging management API or using Spring Boot Actuator if permitted by the application.

### 16.1. LoggingSystem.setLogLevel(...)

Example illustrating changing log levels while the application is running:

~~~java
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.logging.LoggingSystem;

public class RuntimeLogLevelManager {

    private final LoggingSystem loggingSystem;

    public RuntimeLogLevelManager(LoggingSystem loggingSystem) {
        this.loggingSystem = loggingSystem;
    }

    public void enableDebug() {
        loggingSystem.setLogLevel(
                "com.example.catalog",
                LogLevel.DEBUG
        );
    }
}
~~~

This is the logging system's level-management API; it **takes effect from when it is called onward**, without recovering logs already filtered out in the past. How the `LoggingSystem` instance is obtained depends on configuration/framework setup; the example illustrates using the API once an appropriate instance is available.

Do not call this API inside `@PostConstruct` solely as a "workaround" for a late-loaded `@PropertySource`. If the property can be placed in initial Config Data, that approach is cleaner and easier to operate.

### 16.2. Actuator loggers endpoint

When Spring Boot Actuator is present, the `loggers` endpoint can allow viewing and—in suitable configurations—adjusting logger levels at runtime.

Viewing example (when the endpoint is exposed and authorized):

~~~text
GET /actuator/loggers/com.example.catalog
~~~

Endpoint exposure and write permissions must be controlled. Never expose runtime log-level adjustment to the public internet without authentication/authorization and operational policies.

## 17. Listener ordering and the risk of intervening too late

Spring Boot initializes the logging system via bootstrap listeners/infrastructure. If application code also registers listeners for early events, **listener ordering** can affect whether properties are ready when `LoggingSystem` reads configuration.

Example:

~~~java
SpringApplication app = new SpringApplication(CatalogApplication.class);
app.addListeners(new CustomEnvironmentListener());
app.run(args);
~~~

If `CustomEnvironmentListener` listens to `ApplicationEnvironmentPreparedEvent` and modifies property sources, verify its order relative to Boot's internal listeners.

A listener running **after** Boot has read logging properties cannot retroactively change already-emitted logs. Rather than relying on internal order numbers and behaviors that can change across versions, a more resilient way to supply configuration data is `spring.config.import` or a Boot-managed `EnvironmentPostProcessor`.

### 17.1. Early listeners are not @EventListener beans

The following is not a reliable way to process the Environment before the context exists:

~~~java
@Component
class EarlyLoggingBeanListener {

    @EventListener
    void onEnvironmentPrepared(
            ApplicationEnvironmentPreparedEvent event) {
        // This bean is created only after the context starts processing beans.
    }
}
~~~

The event already fired before the `EarlyLoggingBeanListener` bean was created. Register listeners via `SpringApplication` or bootstrap metadata if you genuinely need early events. However, when the primary goal is adding logging properties, prefer configuration extension points over listeners.

## 18. Backend logging config and application.properties can coexist

An application can have:

~~~text
src/main/resources/
├── application.yml
└── logback-spring.xml
~~~

In `application.yml`:

~~~yaml
spring:
  application:
    name: catalog-service

logging:
  level:
    root: INFO
    com.example.catalog: DEBUG
~~~

In `logback-spring.xml`, you can declare appenders, encoders, patterns, or specific loggers per backend needs.

What matters is **understanding who owns each setting**. If you declare a level in the Logback file while also setting `logging.level.com.example.catalog` in the Environment, Spring Boot can apply Environment levels through `LoggingSystem` depending on initialization order. Operators need a clear policy on where levels are configured, avoiding conflicting sources that make outcomes hard to explain.

### 18.1. Do not use a bean to configure appenders from scratch

Creating an `AppenderConfigurator` bean and waiting for it to run after refresh is not a natural way to establish a file appender from the very first log line. With backends like Logback/Log4j2, use a backend config file loaded by Boot at the right time or a clearly designed bootstrap extension point.

If custom appenders or advanced integration are needed, account for backend lifecycle, class loading, and pre-context initialization rules.

## 19. Logs appear on the console yet are missing from the file

A common symptom is:

- Early startup log lines appear on the console.
- Later log lines appear in the file.
- Or conversely, some initial output is absent from the expected file.

This can happen when the logging backend uses a temporary configuration early on before applying the file appender from the Environment. Lines already printed are not automatically buffered and replayed into the file appender later.

Check:

1. Were `logging.file.name`/`logging.file.path` supplied before the logging setup step?
2. Does `logging.config` point to the right resource and backend?
3. Did the filesystem path exist and have write permissions before the file appender opened?
4. Did Logback/Log4j2 initialize very early using a different native config?
5. Are multiple backends/bindings on the classpath causing a different logging system than expected to be selected?

Do not try to use `@PostConstruct` to "rewrite all startup logs into the file", because the framework does not automatically buffer every previously emitted line.

## 20. Impact of logging configuration on performance and safety

Enabling `DEBUG` or `TRACE` too broadly in production can generate huge log volumes starting right from the bootstrap phase, impacting I/O, disk space, and visibility of real errors.

A balanced configuration usually looks like:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework: INFO
    com.example.catalog: INFO
~~~

When investigating a package:

~~~yaml
logging:
  level:
    com.example.catalog.integration: DEBUG
~~~

Beyond volume, logs can contain sensitive data:

- URLs with tokens/query parameters.
- Authentication headers and cookies.
- Passwords/secrets on configuration errors.
- Request/response payloads or SQL parameters.
- Exception messages concatenating user data.

Keep detailed log levels scoped strictly as needed, do not print the whole Environment to debug one property, and avoid enabling debug on entire framework packages in production without evaluating the impact.

### 20.1. Very early logging lacks full observability context

When the context does not exist yet, features such as tracing context, request correlation IDs, MDC populated by servlet filters, or Spring-bean-based exporters are not active yet.

Thus, very early logs may lack `traceId`/`requestId` compared to later request logs. This is not necessarily a pattern bug; request context and observability beans simply have not been created yet.

If you need to tie bootstrap logs to an instance, use non-sensitive deployment metadata such as pod name or process identifier where supported by the backend/pattern, rather than expecting a servlet filter to run before the context exists.

## 21. Diagnosis: a property is present yet logging still does not change

Suppose a bean prints:

~~~java
System.out.println(
        environment.getProperty(
                "logging.level.com.example.catalog"
        )
);
~~~

and prints `DEBUG`, yet logs remain at `INFO`.

To investigate, separate two questions:

1. **What is the current value in the Environment?**
2. **Which value did `LoggingSystem` read and apply, and at what time?**

Walk through in order:

- Identify the source creating the property: `application.yml`, command line, environment, config import, `@PropertySource`, or a source added after startup.
- Verify whether the property existed during Environment preparation or appeared only when the context processed beans.
- Verify the exact logger name; the logger might be a fully-qualified class rather than a package.
- Check the effective level of the logger in the backend; parent/root levels may take effect.
- Check whether a custom `logback-spring.xml`, `logback.xml`, or `logging.config` exists and conflicts.
- Verify which backend was selected on the classpath; do not assume every project uses Logback.
- If changed at runtime, verify the level-changing API was called rather than merely mutating the Environment.
- If the issue affects only very early logs, check whether those logs emitted **before** Boot applied the configuration.

### 21.1. Do not rely solely on logs inside @PostConstruct

`@PostConstruct` occurs later than logging bootstrap. Logging/printing there shows state at bean initialization time, not proof that logging used that same value at `ApplicationStartingEvent`.

### 21.2. Enabling debug intentionally in test environments

You can run:

~~~bash
java -jar catalog.jar --logging.level.org.springframework.boot=DEBUG
~~~

or:

~~~bash
java -jar catalog.jar --debug
~~~

`--debug` in Spring Boot is not equivalent to enabling TRACE for the entire application. It enables useful debug modes/logger groups and can produce the Condition Evaluation Report according to the active version's behavior.

Do not leave such debug settings on long-term in production without a data and log-volume management plan.

## 22. Testing logging configuration requires matching bootstrap timing

A test checking only:

~~~java
assertThat(environment.getProperty(
        "logging.level.com.example.catalog"
)).isEqualTo("DEBUG");
~~~

is not sufficient to prove `LoggingSystem` applied that level **at the right time**.

You can test in two layers:

### 22.1. Testing config data/binding

Ensure properties in config files or test environments are loaded properly. This test verifies config structure and property source ordering.

### 22.2. Testing actual startup logging

Run a small `SpringApplication` or test app using the real startup mechanism to observe logs emitted at the appropriate phase.

Example illustrating a non-web context:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Configuration;

public class LoggingStartupProbe {

    @Configuration(proxyBeanMethods = false)
    static class ProbeConfiguration {
    }

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ProbeConfiguration.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setDefaultProperties(
                java.util.Map.of(
                        "logging.level.com.example.catalog",
                        "DEBUG"
                )
        );

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            // Context is running; observe startup logs from the process.
        }
    }
}
~~~

The example uses `setDefaultProperties` to supply values into the Environment before Boot starts its run sequence. However, that still belongs to Environment configuration, not re-printing logs emitted before Environment setup.

When writing automated tests, use appropriate output-capture utilities and avoid brittle assertions on exact log formatting or timestamps across different backends/versions. If a test modifies global logging state, isolate the test so it does not affect other tests in the same JVM.

## 23. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| `logging.level.*` in `@PropertySource` has no effect | `@PropertySource` processed after logging bootstrap | Move to `application.yml`, ENV, system property, or Config Data |
| Bean reads `DEBUG` yet logs stay `INFO` | Property arrived late or logger/backend did not reapply | Check when source is added; use runtime log-level API if needed |
| `@PostConstruct` sets logger level yet misses early startup logs | Bean runs after logs already emitted | Move logging configuration to bootstrap |
| `<springProfile>` not recognized by Logback | `logback.xml` loaded too early by native Logback | Use Boot-managed `logback-spring.xml` |
| Logback throws extension errors on reload | Native scan enabled with Spring-specific tags | Avoid careless scanning with extensions; use appropriate update mechanisms |
| First log lines missing from file | File appender not yet applied when lines emitted | Understand two-phase logging; configure output early enough |
| File appender fails to open | Directory missing or lacks permissions | Prepare filesystem/volumes before starting the JVM |
| Class logger level wrong from ENV | Case lost in relaxed environment-variable mapping | Use case-preserving property source or `SPRING_APPLICATION_JSON` |
| Remote config for logging fails to affect startup | Source read by bean after refresh | Integrate early with Config Data/Environment |
| Runtime property changed yet level unchanged | `LoggingSystem` does not watch all Environment mutations | Use `LoggingSystem`/Actuator loggers or reconfiguration mechanism |
| Startup logs lack trace ID | Tracing/request infrastructure not ready yet | Distinguish bootstrap logs from request logs |
| Actuator loggers unreachable | Endpoint not exposed or lacks permissions | Configure exposure/authentication under control |
| Two logging backends on classpath | Dependencies/bindings select unintended backend | Inspect dependency tree and active logging system |

## 24. Choosing the right mechanism by requirement

| What do you need? | Mechanism to use |
|---|---|
| Set default log levels per package | `logging.level.*` in `application.yml` |
| Override levels per deployment | Environment variables, command line, or external Config Data |
| Log from the earliest bootstrap notices | Built-in logging infrastructure and options supplyable at/before startup |
| Logback patterns/appenders with Spring profiles/properties | `logback-spring.xml` |
| Simple native Logback file without Spring extensions | `logback.xml` may be suitable |
| Load logging config from a file outside JAR | `logging.config` via a source present at bootstrap |
| Add a property source before context creation | `EnvironmentPostProcessor` or Config Data extension |
| Add application config for beans after context creation | `@PropertySource` if appropriate, **never** to govern early logging |
| Adjust logger levels at runtime | `LoggingSystem` API or Actuator loggers |
| Diagnose why logs are missing | Check event timing, property source timing, backend, and effective level |

### Design checklist

1. Identify **which phase logs need to be affected**: before Environment, during bootstrap, or post-context.
2. Place `logging.*` properties needed for bootstrap into sources **processed early enough by Boot**.
3. Do not depend on `@PropertySource`, `@Bean`, `@PostConstruct`, or runners to configure already-emitted logs.
4. When Spring-specific Logback extensions are needed, use `logback-spring.xml` and avoid incompatible native scanning.
5. Verify backend selection and file/volume readiness before `LoggingSystem` opens appenders.
6. Do not assume Environment mutations automatically reconfigure all logging.
7. When dynamic log levels are needed, use an appropriate management API and secure diagnostic endpoints.
8. For custom `EnvironmentPostProcessor`, keep logic lightweight and independent of late-created Spring beans.
9. Do not let overly verbose logging expose secrets or overload the system.
10. Verify behavior with a real startup when the issue involves **timing** of log emission.

## 25. Summary

Spring Boot logging initializes early so the application can record failures occurring even **before the ApplicationContext exists**. Consequently, a property eventually appearing in `Environment` does not prove it was present when `LoggingSystem` read configuration.

`application.yml`, environment variables, JVM properties, and Config Data sources processed at the right stage are the proper ways to configure logging from bootstrap. Conversely, `@PropertySource`, `@Bean` methods, `@ConfigurationProperties` beans, and `@PostConstruct` are processed once the context is being built, which can be too late for this purpose.

**The most important principle:** to control logging at a given point, supply the configuration **before or right when `LoggingSystem` consumes it**. Distinguishing bootstrap logging, Environment-based logging, and runtime log-level changes prevents "the property is there yet the logs didn't change" bugs and makes Spring Boot operations far more predictable.
