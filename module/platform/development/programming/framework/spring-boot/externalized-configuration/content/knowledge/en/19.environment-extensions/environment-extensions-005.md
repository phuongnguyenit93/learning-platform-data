# Early-Read Properties Such as logging.* and spring.main.*

## 1. Problem: Some Properties Must Be Present Before Beans Are Created

Spring Boot supports **externalized configuration**: developers place values in **application.properties**, **application.yml**, environment variables, Java system properties, or command-line arguments; the application reads these values at runtime.

For many business properties, we can inject them with **@Value**, read from **Environment**, or bind via **@ConfigurationProperties** after the container has been prepared. However, **not every property is read at the same time**.

Some properties control **the application startup process itself**. Spring Boot needs to determine the logging system, web application type, startup info, or Config Data locations **before the ApplicationContext finishes refreshing**.

The two most common groups are:

- **logging.***: for example **logging.level.root**, **logging.file.name**, **logging.config**.
- **spring.main.***: for example **spring.main.banner-mode**, **spring.main.web-application-type**, **spring.main.log-startup-info**.

If you put these keys in a source that is only added **after** they have already been read, that source may still appear in Environment later, yet **fail to alter startup decisions that have already occurred**.

Spring Boot 3.3 documentation explicitly states: configuration sources from **@PropertySource** on **@Configuration** classes are only added while the context is refreshing, and are therefore **too late for certain properties like logging.* and spring.main.***.

This lesson explains the meaning of "early-read", processing timing, suitable configuration sources, how to extend Environment using **EnvironmentPostProcessor**, and how to diagnose cases where a property exists yet startup behavior does not match expectations.

Example context: **Spring Boot 3.3.x**, **Java 21**, JAR run from the command line. Commands are technical examples; no external service connection is required.

## 2. Distinguishing Three Important Moments

To understand early-read properties, separate:

1. **Before the ApplicationContext exists**: SpringApplication prepares the Environment and initial configuration sources.
2. **During ApplicationContext preparation/refresh**: Spring creates bean definitions, reads @Configuration, processes @PropertySource, and instantiates beans.
3. **After the context is ready**: ApplicationRunner, CommandLineRunner, and application logic start using beans.

Simplified diagram:

~~~text
main(String[] args)
        |
        v
SpringApplication.run(args)
        |
        v
Prepare Environment
  - default properties
  - system properties / OS env
  - command-line arguments
  - Config Data: application.yml, profile files, imports
  - EnvironmentPostProcessor
        |
        v
Startup mechanisms read early configuration
  - logging configuration
  - spring.main.* decisions
        |
        v
Create and prepare ApplicationContext
        |
        v
Refresh ApplicationContext
  - @Configuration, @PropertySource
  - create beans and bind @ConfigurationProperties
        |
        v
ApplicationRunner / CommandLineRunner
        |
        v
Application ready to handle work
~~~

**This is a conceptual diagram, not an absolute ordering of every internal callback.** Spring Boot has many events and setup steps; logging and environment preparation can involve multiple phases. The takeaway is that **@PropertySource during the refresh phase cannot turn back time to configure decisions already made earlier**.

### 2.1. Early-Read Does Not Mean All Properties Are Read in the Same Nanosecond

For example:

- **spring.config.name**, **spring.config.location**, **spring.config.additional-location** must exist early enough to determine where to search for Config Data.
- **logging.config** or **logging.level.root** is used by the logging infrastructure during startup.
- **spring.main.web-application-type** helps SpringApplication decide the context/web application type.
- A field inside **@ConfigurationProperties(prefix = "app")** is typically bound when the configuration properties bean is created.

Therefore, saying "just have the value before the app is ready" is **not enough**. You must know **which component consumes the property and when it consumes it**.

## 3. @PropertySource Is Usually Too Late for logging.* and spring.main.*

An easily misleading example:

**src/main/java/com/example/boot/LatePropertiesConfiguration.java**:

~~~java
package com.example.boot;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:late-startup.properties")
public class LatePropertiesConfiguration {
}
~~~

**src/main/resources/late-startup.properties**:

~~~properties
logging.level.root=DEBUG
spring.main.banner-mode=off
spring.main.web-application-type=none
~~~

The property names may be valid, the file may exist on the classpath, and later **Environment.getProperty("logging.level.root")** may even see **DEBUG**. However, that **does not prove** logging was initialized at DEBUG from the start, that the banner was turned off, or that the web context type was re-selected.

**Reason:** @PropertySource is added during context refresh. The startup decisions mentioned above may have already been executed beforehand.

Do not expect the following statements to "rewrite the past":

~~~java
@Value("${spring.main.banner-mode}")
private String bannerMode;
~~~

or:

~~~java
@ConfigurationProperties(prefix = "spring.main")
public record MainSettings(String bannerMode) {
}
~~~

Those APIs can **read a value**, but that does not mean SpringApplication will re-apply the new value to an already-completed startup step.

### 3.1. Is @PropertySource Useless?

No. **@PropertySource** remains useful when you need to add an optional **.properties** file to Environment for regular beans to use later.

Example:

~~~properties
app.report.title=Monthly Report
app.report.max-rows=200
~~~

If a bean only needs these values during or after refresh, @PropertySource can fit the design.

Problems only happen when **the wrong source or wrong timing** is chosen for properties consumed very early.

Another note: **@PropertySource** does not directly load multi-document YAML files with Config Data semantics; Spring Boot recommends using the Config Data mechanism for application.yml and profile files.

## 4. Sources to Use for Early-Read Properties

Typically, the safest and simplest choice is one of the sources Spring Boot supports **before context refresh**:

| Source | Example | Meaning |
| --- | --- | --- |
| **Command-line arguments** | **--logging.level.root=DEBUG** | Provided for a single launch |
| **OS environment variables** | **LOGGING_LEVEL_ROOT=DEBUG** | Provided for the process/container |
| **Java system properties** | **-Dlogging.level.root=DEBUG** | Provided to the JVM before running the JAR |
| **Config Data** | **application.yml**, profile files, imports | Loaded by Spring Boot during Environment preparation |
| **SpringApplication default properties** | **setDefaultProperties(...)** | Supplies low-priority values as fallbacks |
| **EnvironmentPostProcessor** | Adds an early PropertySource | For special Environment extension needs |

**Choose the source based on deployment requirements**, not based on which annotation happens to be handy.

If you only want to change the log level between local and production, **application.yml** or environment variables usually suffice. Only write an **EnvironmentPostProcessor** when you have a specific integration need that standard sources do not handle cleanly.

## 5. Early Configuration with application.yml

**src/main/resources/application.yml**:

~~~yaml
spring:
  main:
    banner-mode: "off"
    log-startup-info: false

logging:
  level:
    root: INFO
    com.example.boot: DEBUG
  file:
    name: "logs/sample-app.log"
~~~

Meaning:

- **spring.main.banner-mode=off**: disables the Spring Boot banner at startup.
- **spring.main.log-startup-info=false**: controls startup info logged by SpringApplication.
- **logging.level.root=INFO**: configures the root logger level.
- **logging.level.com.example.boot=DEBUG**: applies DEBUG level to the corresponding logger/package.
- **logging.file.name**: specifies the log filename, depending on the logging system and existing configuration.

This configuration is processed through **Config Data**. It differs from specifying a separate file with @PropertySource inside a @Configuration class.

**Note:** relative log file paths such as **logs/sample-app.log** are resolved relative to the process working directory depending on the logging setup. The container must have the appropriate path and write permissions; in many container/cloud systems, writing logs to stdout/stderr is simpler than managing log files inside the container.

### 5.1. Equivalent application.properties

~~~properties
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=INFO
logging.level.com.example.boot=DEBUG
logging.file.name=logs/sample-app.log
~~~

Use one consistent Config Data format in the application, avoiding having both application.properties and application.yml in the same location with conflicting values.

### 5.2. "Early" Does Not Mean Putting Everything on the Command Line

**application.yml is a Config Data source processed early by Spring Boot** during the startup lifecycle. You can certainly configure many **logging.*** and **spring.main.*** properties in this file.

The common mistake is not "using files" in general, but **using a file that is only introduced into Environment too late**.

## 6. Early Configuration via Command-Line Arguments

Example running a JAR:

~~~bash
java -jar app.jar \
  --logging.level.root=DEBUG \
  --spring.main.banner-mode=off \
  --spring.main.log-startup-info=false
~~~

These are application **option arguments**, not Java **-D** system properties.

Spring Boot by default converts options starting with **--** into Environment properties. Therefore, they are supplied as soon as SpringApplication processes arguments.

Example disabling the web server:

~~~bash
java -jar app.jar \
  --spring.main.web-application-type=none
~~~

When **web-application-type=none** takes effect, the application does not initialize a regular web application context. If the project serves a REST API, having no web server is the **expected result**, not necessarily a startup error.

### 6.1. Command-Line Properties Can Be Disabled in Code

By default, command-line properties are added to Environment. However, a program can call:

~~~java
springApplication.setAddCommandLineProperties(false);
~~~

When that happens, **--...** options are no longer added to Environment through the default mechanism described above. Thus, if the command line has no effect, check whether the application customizes SpringApplication.

Do not conclude every application supports command-line overrides just because Spring Boot does so by default; bootstrap code can alter this behavior.

## 7. Early Configuration via Java System Properties

System properties use the **-Dkey=value** syntax and must be placed in the JVM arguments section, before **-jar**:

~~~bash
java \
  -Dlogging.level.root=DEBUG \
  -Dspring.main.banner-mode=off \
  -jar app.jar
~~~

With **logging.config**:

~~~bash
java \
  -Dlogging.config=classpath:logback-spring.xml \
  -jar app.jar
~~~

This example assumes the application uses a compatible logging system with a **logback-spring.xml** resource on the classpath.

Distinction:

~~~text
-Dlogging.level.root=DEBUG       -> Java system property
--logging.level.root=DEBUG       -> Spring Boot command-line property
LOGGING_LEVEL_ROOT=DEBUG         -> OS environment variable
~~~

They may describe the same key, yet originate from different PropertySources with different precedence positions.

### 7.1. Putting -D in the Wrong Place

The command:

~~~bash
java -jar app.jar -Dlogging.level.root=DEBUG
~~~

does not mean the same thing as placing **-D** before **-jar**. After **-jar**, that string belongs to the application arguments, not JVM system properties set by the launcher in standard syntax.

If you want to pass a Spring Boot application argument after the JAR, use **--logging.level.root=DEBUG**.

## 8. Early Configuration via Environment Variables

Environment variables are especially well suited for containers and deployment pipelines.

Example on Linux/macOS:

~~~bash
LOGGING_LEVEL_ROOT=DEBUG \
SPRING_MAIN_BANNER_MODE=off \
SPRING_MAIN_LOGSTARTUPINFO=false \
java -jar app.jar
~~~

PowerShell:

~~~powershell
$env:LOGGING_LEVEL_ROOT = "DEBUG"
$env:SPRING_MAIN_BANNER_MODE = "off"
$env:SPRING_MAIN_LOGSTARTUPINFO = "false"

java -jar app.jar
~~~

Variable names follow Spring Boot's rules for **relaxed binding**:

1. Dots **.** are converted to underscores **_**.
2. Dashes **-** inside each segment are **removed**.
3. Letters are converted to uppercase.

| Canonical property | Environment variable |
| --- | --- |
| **logging.level.root** | **LOGGING_LEVEL_ROOT** |
| **logging.file.name** | **LOGGING_FILE_NAME** |
| **logging.config** | **LOGGING_CONFIG** |
| **spring.main.banner-mode** | **SPRING_MAIN_BANNERMODE** |
| **spring.main.log-startup-info** | **SPRING_MAIN_LOGSTARTUPINFO** |
| **spring.main.web-application-type** | **SPRING_MAIN_WEBAPPLICATIONTYPE** |
| **spring.main.lazy-initialization** | **SPRING_MAIN_LAZYINITIALIZATION** |
| **spring.config.name** | **SPRING_CONFIG_NAME** |
| **spring.config.additional-location** | **SPRING_CONFIG_ADDITIONALLOCATION** |

**A very easy mistake:** the canonical name for **spring.main.banner-mode** is **SPRING_MAIN_BANNERMODE**, not **SPRING_MAIN_BANNER_MODE**. Dashes are removed, not replaced with new underscores. Therefore when experimenting, follow the names Spring Boot documents for relaxed binding.

Some tools may apply custom rules when translating environment variables to properties. When a variable does not work, check the exact canonical name, the variable name set, and how it is passed into the **Java process**.

### 8.1. Docker Compose Example

~~~yaml
services:
  app:
    image: example/boot-early-config:1.0.0
    environment:
      LOGGING_LEVEL_ROOT: "INFO"
      SPRING_MAIN_BANNERMODE: "off"
      SPRING_MAIN_LOGSTARTUPINFO: "false"
      SPRING_MAIN_WEBAPPLICATIONTYPE: "servlet"
~~~

This is an example with an existing image. Docker Compose injects string values into the container environment; Spring Boot picks them up when the process starts.

If using **SPRING_MAIN_WEBAPPLICATIONTYPE=none** on an HTTP-only service, do not expect mapping ports and curling to still receive responses from an embedded server. That is the effect of this startup property.

## 9. logging.* Properties: What Exactly Should You Understand?

**logging.*** controls different aspects of the logging infrastructure.

Common examples:

~~~properties
logging.level.root=INFO
logging.level.org.springframework.web=DEBUG
logging.file.name=logs/app.log
logging.config=classpath:logback-spring.xml
~~~

Not every key has the same effect:

- **logging.level.root**: log level of the root logger.
- **logging.level.<logger-name>**: level of a logger or package.
- **logging.file.name**: log filename when supported by the logging system.
- **logging.config**: instructs loading a specific logging configuration file.

**logging.config** is notable because the logging system may need this file when it itself initializes. If the value is only placed into Environment by a bean or a late @PropertySource, the logging system may have already loaded the default configuration.

### 9.1. Changing Package Level Differs from Changing a Specific Class Level

Standard environment variables are convenient for package-level logging:

~~~text
LOGGING_LEVEL_ORG_SPRINGFRAMEWORK_WEB=DEBUG
~~~

When binding names from the system environment, Spring Boot applies lowercasing rules. This can cause issues with **case-sensitive Java class names**.

If you need to target an exact logger/class such as **com.example.payment.PaymentService**, using an all-uppercase environment variable name may not preserve the uppercase letters of the class name. You can use:

~~~properties
logging.level.com.example.payment.PaymentService=DEBUG
~~~

in properties/YAML, or use **SPRING_APPLICATION_JSON** with the appropriate key name when you need a JSON structure containing exact logger names.

### 9.2. Why Should You Not Use a Bean to Configure Logging Too Late?

Example:

~~~java
@Component
public class LateLogConfig {
    public LateLogConfig(Environment environment) {
        String level = environment.getProperty(
                "logging.level.root");
        System.out.println(level);
    }
}
~~~

The bean can read **DEBUG**, but by the time the constructor runs, initial logging startup has already occurred. Reading a value does not mean logging was re-initialized with that value.

Some logging systems allow dynamically adjusting levels through a separate API, but that is **a different mechanism** from configuring **logging.*** at startup.

### 9.3. Logback and Custom Configuration Files

When using Logback, Spring Boot generally recommends the name **logback-spring.xml** for configurations using Spring Boot extensions, rather than relying on **logback.xml** loaded traditionally by the logging framework.

With custom configuration:

~~~properties
logging.config=classpath:logback-spring.xml
~~~

If the file is missing or uses unsupported syntax at load time, logging initialization can fail. Do not put the logging filename in @PropertySource expecting the logging system to reload it automatically.

## 10. spring.main.* Properties: Shaping How SpringApplication Starts

The **spring.main.*** group affects decisions made by **SpringApplication**.

A few examples:

| Property | General Meaning |
| --- | --- |
| **spring.main.banner-mode** | Print banner to console, log, or turn off |
| **spring.main.log-startup-info** | Whether to log startup info managed by SpringApplication |
| **spring.main.web-application-type** | Application type such as **none**, **servlet**, **reactive** |
| **spring.main.lazy-initialization** | Enables broad lazy initialization when turned on |
| **spring.main.allow-bean-definition-overriding** | Controls whether bean definition overriding is permitted under appropriate config |

Different properties may be consumed at different steps, but the common thread is that many properties in this group **must exist before or during context preparation**, not after all beans have been created.

### 10.1. Disabling the Banner from Config Data

~~~yaml
spring:
  main:
    banner-mode: off
~~~

The value **off** is an enum/configuration value supported by Spring Boot for banner mode. Putting it in **application.yml** is normal.

If the program only needs the banner disabled for a single run:

~~~bash
java -jar app.jar --spring.main.banner-mode=off
~~~

there is no need to write a @Configuration class or manipulate the banner after startup.

### 10.2. Switching to a Non-Web Application

~~~bash
java -jar app.jar \
  --spring.main.web-application-type=none
~~~

This scenario suits batch jobs, CLI tools, or applications that do not need an embedded web server.

However, if the program actually needs to initialize servlet infrastructure, changing the web application type can stop web components from being created or functioning as before. This is a **startup architectural decision**, not just an ordinary flag.

### 10.3. Lazy Initialization Is Not Config Refresh

~~~properties
spring.main.lazy-initialization=true
~~~

This property controls whether beans are initialized lazily. It does not mean the application reloads configuration files automatically, nor does it mean all configuration errors are caught immediately at startup. Some lazy beans may cause errors to surface only when used.

Therefore, when enabling lazy initialization, it is even more important to understand when critical configuration/validation beans are created.

## 11. Config Data and Properties Used Very Early to Locate Files

Another group of properties is consumed **even earlier than normal configuration**:

~~~text
spring.config.name
spring.config.location
spring.config.additional-location
~~~

They help Spring Boot determine which filenames and locations to search **during Config Data loading**.

Example:

~~~bash
java -jar app.jar \
  --spring.config.name=myservice
~~~

Spring Boot will look for configuration filenames matching **myservice** in the applicable locations.

Or:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./local-config/
~~~

At launch, this property must be present early enough for Spring Boot to know it needs to inspect the **local-config** directory.

### 11.1. The Self-Referential Loop Mistake

Suppose you want to load **custom/application.yml** and only write:

~~~yaml
spring:
  config:
    location: "file:./custom/"
~~~

inside another default file, expecting Spring Boot to use that property to go back and re-determine all searched locations. Boot documentation requires **spring.config.name**, **spring.config.location**, and **spring.config.additional-location** to be supplied as **early environment properties**, typically via OS env, system property, or command line.

Do not design a workflow of "read a file first to find out where to search for files" for these bootstrap keys.

### 11.2. Environment Variable Form

~~~text
SPRING_CONFIG_NAME=myservice
SPRING_CONFIG_ADDITIONALLOCATION=optional:file:./local-config/
~~~

For directory locations, the trailing slash **/** matters: Spring Boot can append filenames generated from **spring.config.name** onto the directory path.

### 11.3. spring.config.location Differs from additional-location

- **spring.config.location** can replace the default set of search locations.
- **spring.config.additional-location** adds new locations while preserving the default locations.

Therefore, when you only want to add a deployment config folder, **additional-location** usually makes it easier to avoid losing default Config Data locations.

## 12. spring.config.import: Not Like @PropertySource

**spring.config.import** is processed by the Spring Boot Config Data infrastructure during the configuration loading phase.

Example **application.yml**:

~~~yaml
spring:
  config:
    import: "optional:file:./deployment-extra.properties"

logging:
  level:
    root: INFO
~~~

If **deployment-extra.properties** exists:

~~~properties
logging.level.root=WARN
spring.main.banner-mode=off
~~~

it is treated as Config Data imported through Boot's mechanism. Its data can participate in appropriate startup decisions at Config Data loading time.

**Core difference:**

- **spring.config.import** is part of Config Data processing, which runs early.
- **@PropertySource** on a @Configuration class is added during context refresh, which is later.

The exact same file contents can yield **different behavior** simply because it is loaded via a **different mechanism**.

### 12.1. Optional Import

The prefix:

~~~text
optional:file:./deployment-extra.properties
~~~

allows the application to continue startup when the file does not exist, following Config Data optional location rules.

If the file genuinely contains values required for production, do not casually attach **optional:** and allow the app to start missing configuration without proper validation or guards.

## 13. Programmatic Early Configuration in main()

When writing bootstrap code, you can configure **SpringApplication** before calling **run(...)**.

Example:

~~~java
package com.example.boot;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

public class EarlyConfigApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(EarlyConfigApplication.class);

        application.setDefaultProperties(Map.of(
                "spring.main.banner-mode", "off",
                "logging.level.root", "INFO"
        ));

        application.run(args);
    }
}
~~~

**setDefaultProperties(...)** provides low-priority defaults. Thus, the operator's command line or env can override defaults as appropriate.

When setting SpringApplication attributes directly via API, call setters before **run(...)**:

~~~java
SpringApplication application =
        new SpringApplication(EarlyConfigApplication.class);

application.setWebApplicationType(WebApplicationType.NONE);
application.setLogStartupInfo(false);

application.run(args);
~~~

These are programmatic decisions made earlier than creating application beans.

**Watch out for precedence:** values set on SpringApplication and values bound from Environment may interact according to specific lifecycle rules. If you need a clear override contract for deployers, prefer a standard configuration source and test behavior on your actual Spring Boot version. Do not assume a setter always beats every property or vice versa.

### 13.1. DefaultProperties Is Not the Highest Override

If you set:

~~~java
application.setDefaultProperties(Map.of(
        "logging.level.root", "INFO"));
~~~

and the operator runs:

~~~bash
java -jar app.jar --logging.level.root=DEBUG
~~~

the command line normally takes higher priority than default properties. **Defaults** are fallbacks, not forced policy.

If you need to lock down a setting for security requirements, do not expect **setDefaultProperties** alone to accomplish that.

## 14. When Is EnvironmentPostProcessor Needed?

**EnvironmentPostProcessor** is Spring Boot's extension point to customize Environment **before the ApplicationContext is refreshed**.

It is suitable when:

- The application needs to translate a custom configuration convention into standard Spring Boot properties.
- You need to add a PropertySource from an already-available bootstrap source.
- You need to normalize certain values before startup components consume them.
- You are building a starter/platform library providing early configuration across multiple applications.

You do not need an EnvironmentPostProcessor just to change **logging.level.root** from INFO to DEBUG. For simple cases, command line, env, or Config Data suffices.

### 14.1. Example: Mapping a Custom Bootstrap Variable to logging.level.root

Suppose a deployment environment supplies:

~~~text
COMPANY_BOOTSTRAP_LOG_LEVEL=WARN
~~~

You want to use it as a **default for logging.level.root**, while still letting operators override directly with **LOGGING_LEVEL_ROOT** or CLI.

Create class:

~~~java
package com.example.boot;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.util.StringUtils;

public final class CompanyLoggingEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        String requestedLevel =
                environment.getProperty(
                        "COMPANY_BOOTSTRAP_LOG_LEVEL");

        if (!StringUtils.hasText(requestedLevel)) {
            return;
        }

        MapPropertySource source = new MapPropertySource(
                "companyBootstrapLoggingDefaults",
                Map.of("logging.level.root", requestedLevel));

        environment.getPropertySources().addLast(source);
    }
}
~~~

Explanation:

- **EnvironmentPostProcessor** is invoked by Spring Boot during Environment preparation.
- **MapPropertySource** contains the standard key **logging.level.root**.
- **addLast(...)** places the new source in a low-priority position relative to existing PropertySources.
- **COMPANY_BOOTSTRAP_LOG_LEVEL** is merely an example convention; Spring Boot itself does not require this name.
- If the variable is not provided, the processor adds no new source.
- The processor creates or modifies no business beans.

**Note:** adding the source at the end keeps it as a fallback, so if logging.level.root already exists in Config Data or CLI, the higher-priority value still wins.

### 14.2. Why Not Call addFirst Every Time?

Writing:

~~~java
environment.getPropertySources().addFirst(source);
~~~

places the source at the front of the list and can take higher priority than values the operator intentionally passed via CLI/env, depending on when the source is added.

This may be desired behavior when designing a platform policy, but should not be used mechanically. PropertySource ordering is part of the override contract.

In the logging defaults example, **addLast** makes more sense than **addFirst** because it avoids overriding startup configuration specified by deployment.

### 14.3. Do Not Use a Processor to Perform Heavy I/O

EnvironmentPostProcessor runs early. If it connects to a database, makes long HTTP requests, or depends on beans not yet created, startup becomes unpredictable.

If you must fetch data from an external configuration source, use an appropriate extension/config data mechanism with bounded timeouts and clear failure policies. Do not turn a processor into a full-blown business service.

## 15. Registering EnvironmentPostProcessor in Spring Boot 3.3

Simply writing a class implementing the interface is **not enough**. Spring Boot must be configured to discover it at startup.

Create file:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Contents:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.boot.CompanyLoggingEnvironmentPostProcessor
~~~

In Spring Boot 3.3, **EnvironmentPostProcessor implementations are registered via META-INF/spring.factories**, using the fully qualified interface name as the key.

**Do not confuse** this mechanism with the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

**AutoConfiguration.imports** is for registering auto-configuration; it **does not replace** the EnvironmentPostProcessor registration key in this example.

A common mistake is that the class compiles cleanly in the right package, yet the processor never runs because **spring.factories** is missing or has a wrong fully qualified class name.

### 15.1. Ordering Among EnvironmentPostProcessors

If multiple processors exist, order can affect the final value. Spring Boot allows implementations to use **Ordered** or **@Order**.

**ConfigDataEnvironmentPostProcessor** is a Boot processor responsible for processing Config Data. If your processor depends on properties in application.yml, it must run at an appropriate time **after Config Data is loaded**.

Do not assume custom processors run in alphabetical order by class name or line order in spring.factories. When a specific ordering relationship is required, use the ordering API and write a test proving it.

### 15.2. Logging Inside EnvironmentPostProcessor Itself

Because the processor runs early, the logging system may not yet be fully configured. If you need diagnostic logging at bootstrap, Spring Boot supports **DeferredLogFactory** as an optional constructor parameter in EnvironmentPostProcessor, so logs are emitted once the logging system is prepared.

Do not assume that logging directly from the constructor or the start of postProcessEnvironment will automatically use the logging level/formatter you are about to configure.

## 16. EnvironmentPostProcessor Differs from ApplicationContextInitializer

Two extension points that are easily confused:

| Extension point | Primary impact | Timing and notes |
| --- | --- | --- |
| **EnvironmentPostProcessor** | Customizes Environment during early preparation | Suitable for configuration sources that can affect startup |
| **ApplicationContextInitializer** | Customizes ApplicationContext before refresh | Context is already created; may be too late for decisions like initial banner/logging |
| **@PropertySource** | Adds a source declared on a @Configuration class | Typically processed during context refresh |
| **ApplicationRunner** | Runs logic after context is prepared | Too late for early-read decisions |
| **CommandLineRunner** | Runs after context startup | Not used to change the already-created web application type |
| **@ConfigurationProperties** | Binds a property group to a typed bean | Useful for subsystem config, does not retroactively alter past startup decisions |

If the goal is **adding a logging key before the logging system consumes it**, EnvironmentPostProcessor is a better fit than an ApplicationRunner bean.

### 16.1. ApplicationEnvironmentPreparedEvent

Spring Boot has the **ApplicationEnvironmentPreparedEvent** during startup. This event fires after Environment is prepared and before the context is created.

A listener **registered early enough on SpringApplication** can participate in customizing Environment, though listener ordering relative to subsystems such as logging still needs to be clearly understood.

For standard PropertySource additions, **EnvironmentPostProcessor** is Boot's dedicated mechanism for this job and is usually easier to manage than a listener with ad-hoc custom ordering.

## 17. Why Can Environment.getProperty Be "Right" Yet Behavior Still Be "Wrong"?

A confusing scenario:

1. SpringApplication reads **spring.main.banner-mode** during startup.
2. The banner is decided and printed (or suppressed).
3. @PropertySource is processed during refresh, adding a file declaring **spring.main.banner-mode=off**.
4. Afterward, a service calls **environment.getProperty("spring.main.banner-mode")** and sees **off**.

A developer might say: "Environment already says off, why did the banner still print?"

Because **Environment is the current set of properties**, while banner behavior was a **decision already executed earlier**.

Similarly for logging:

~~~text
Current Environment says logging.level.root=DEBUG
          ≠
The logging system was at DEBUG from the very beginning of startup
~~~

Some logging subsystems support dynamic changes, but that is a separate mechanism; do not treat a late-appearing property as proof that logging was re-initialized.

This is the most important insight when debugging early-read properties.

## 18. When Are @Value and @ConfigurationProperties Used?

Business beans can read config via:

~~~java
@Value("${app.report.max-rows:100}")
private int maxRows;
~~~

or:

~~~java
@ConfigurationProperties(prefix = "app.report")
public record ReportProperties(int maxRows) {
}
~~~

These are sensible tools for component-owned configuration, especially when a subsystem has multiple fields requiring type conversion and validation.

However, the snippet:

~~~java
@ConfigurationProperties(prefix = "spring.main")
public record MainProperties(String bannerMode) {
}
~~~

does not guarantee SpringApplication will re-apply banner mode after this bean is created.

Principle:

- **Reading and binding a value** is one thing.
- **Applying a startup decision** is another.

Choose a configuration source matching the **read timing** and the **consuming component**.

## 19. Source Precedence Order in Spring Boot

Spring Boot defines PropertySource ordering on the principle that **higher-priority sources can override lower-priority sources**.

Common sources:

~~~text
Default properties
      |
@PropertySource (loaded during context refresh)
      |
Config Data (application.properties / .yml)
      |
OS environment variables
      |
Java system properties
      |
SPRING_APPLICATION_JSON
      |
Command-line arguments
~~~

This is a summary diagram of typical sources, **not an exhaustive list of every source**: test properties, servlet init params, devtools settings, and several others have their own positions.

The order above expresses relative priority tiers in Spring Boot documentation; **early vs. late reading is an axis independent of priority**.

A source with "high" priority in Environment after refresh can still be added **too late** for a startup decision. Therefore, when debugging, answer both questions:

1. **Which source does the key ultimately come from?**
2. **Did that source exist when the component needed the key?**

### 19.1. Even with the Key Present, @PropertySource Is Not an Early-Key Override Solution

Even when a @PropertySource file sits in Environment, **logging.*** and **spring.main.*** are highlighted by Boot as examples that may already have been read before refresh.

The usual fix is not raising priority for @PropertySource with late code, but **putting the value into Config Data or an early bootstrap source**.

## 20. An End-to-End Observation Example

Suppose the application has the class:

~~~java
package com.example.boot;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EarlyPropertiesDemo {

    public static void main(String[] args) {
        SpringApplication.run(EarlyPropertiesDemo.class, args);
    }
}
~~~

**application.yml**:

~~~yaml
spring:
  main:
    banner-mode: "console"
    log-startup-info: true

logging:
  level:
    root: INFO
~~~

Default run:

~~~bash
java -jar app.jar
~~~

Then try:

~~~bash
java -jar app.jar \
  --spring.main.banner-mode=off \
  --spring.main.log-startup-info=false \
  --logging.level.root=WARN
~~~

Observations:

- The banner is turned off instead of displayed.
- Startup logs managed by SpringApplication are reduced.
- The root logging level is set to WARN, so normal DEBUG/INFO messages do not appear on the root logger.

**Do not use absolute log line counts as criteria**, because different logging frameworks, dependencies, and application code emit different logs. Check the exact behavior described by the property.

### 20.1. Trying a Late-Loaded Source

Create:

~~~properties
# late-startup.properties
spring.main.banner-mode=off
logging.level.root=DEBUG
~~~

Add @PropertySource to a @Configuration class. Re-run with **application.yml** as before and no CLI arguments.

What can be observed:

- The file is read during context refresh.
- Yet startup decisions already made before that moment do not necessarily change.

The conclusion is not "@PropertySource does not work", but **@PropertySource is unsuitable for early-read property groups**.

### 20.2. Trying Config Data Import

Move those values to:

~~~properties
# deployment-extra.properties
spring.main.banner-mode=off
logging.level.root=DEBUG
~~~

Then in **application.yml** add:

~~~yaml
spring:
  config:
    import: "optional:classpath:deployment-extra.properties"
~~~

Now the file is brought in via **Config Data** instead of @PropertySource, so it can be applied during the Environment preparation phase.

## 21. Common Mistakes

### Mistake 1 — Putting logging.* in @PropertySource and Seeing No Effect at Startup

**Cause:** the source is only added during context refresh.

**Fix:** move the key to application.yml/properties, environment variable, system property, command line, or an early enough EnvironmentPostProcessor.

### Mistake 2 — Reading spring.main.banner-mode=off Yet Seeing the Banner Already Printed

**Cause:** the property appeared after SpringApplication already handled the banner.

**Fix:** use an early source and observe a fresh startup; do not expect an already-printed banner to be "retracted".

### Mistake 3 — Wrong Env Variable Naming for Kebab-Case Keys

**Example:** **SPRING_MAIN_BANNER_MODE** instead of the canonical name **SPRING_MAIN_BANNERMODE**.

**Fix:** convert names per Spring Boot rules: dots become underscores, dashes are removed, letters become uppercase.

### Mistake 4 — Putting spring.config.location Inside the File Expected to Be Found by It

**Cause:** Spring Boot needs to know the location to load files from the very beginning.

**Fix:** use env, system properties, or command line for **spring.config.location** and corresponding bootstrap location flags.

### Mistake 5 — Treating Command-Line Options and -D as Identical

~~~text
-Dspring.main.banner-mode=off
--spring.main.banner-mode=off
~~~

The two syntaxes belong to different mechanisms. **-D** is a Java launcher property before -jar; **--** is a Spring Boot application argument after the JAR.

### Mistake 6 — Environment Variable Not Passed into the Java Process

A variable sitting in a different shell, an .env file not forwarded by Compose into the container, or a variable in another CI job may not appear in the process.

**Fix:** inspect the actual environment of the process/Pod and how variables are passed, not just declaration files.

### Mistake 7 — Assuming logging.config Will Automatically Reload the File

**logging.config** specifies the logging configuration file used when logging is configured. Editing the file after startup does not automatically trigger a reload via Spring Boot. If reloading is desired, understand the logging framework itself and a dedicated mechanism.

### Mistake 8 — EnvironmentPostProcessor Does Not Run

**Cause:** missing **META-INF/spring.factories**, wrong class name, or the file was not packaged into the JAR.

**Fix:** verify the class in build output, that spring.factories has the exact key **org.springframework.boot.env.EnvironmentPostProcessor**, and that the class can be loaded.

### Mistake 9 — Using addFirst and Losing CLI Override Capability

**Cause:** the custom source takes unexpectedly high priority.

**Fix:** if you only want defaults, use **addLast** or an appropriate default source; design precedence clearly.

### Mistake 10 — Making a Custom Processor Depend on Spring Beans

**Cause:** EnvironmentPostProcessor runs before ApplicationContext refresh and before business beans are ready.

**Fix:** keep the processor lightweight and pure; do not assume @Autowired services or database connections exist.

### Mistake 11 — Choosing the Wrong Web Application Type

Setting **spring.main.web-application-type=none** in a service intended to serve a REST API breaks expectations about an embedded server.

**Fix:** determine whether the application is CLI/batch, Servlet web, or Reactive web before setting the property.

### Mistake 12 — Using ApplicationRunner to Fix Startup Properties

ApplicationRunner runs after the context is ready, so it is unsuitable for decisions already used during context creation.

### Mistake 13 — Confusing @ConfigurationProperties with Bootstrap Wiring

A @ConfigurationProperties bean can receive **spring.main.web-application-type**, but the bean's existence does not reconfigure SpringApplication.

### Mistake 14 — Enabling Lazy Initialization and Expecting Every Misconfiguration to Fail Fast

Some lazy beans may be deferred, delaying validation until the bean is used. Do not treat lazy initialization as guaranteeing all config is checked early.

### Mistake 15 — Logging Secrets in EnvironmentPostProcessor

The processor can see many configuration sources, including sensitive data. Do not print the entire Environment or secret values to bootstrap logs.

## 22. Practice Exercises

### Exercise A: Comparing Config Data with @PropertySource

1. Create a minimal Spring Boot app with a main class.
2. Put **spring.main.banner-mode=off** in **application.properties**.
3. Run and observe the banner.
4. Move the property to **late-startup.properties** and load that file only via **@PropertySource**.
5. Re-launch and compare.

**Key takeaway:** not all PropertySources are added to Environment at the same time.

### Exercise B: Overriding Log Level from CLI

1. Set **logging.level.root=INFO** in application.yml.
2. Run with **--logging.level.root=DEBUG**.
3. Run again with **--logging.level.root=WARN**.
4. Observe the logs at each corresponding level.

**Key takeaway:** early configuration can still be externalized and varied across runs of the same JAR.

### Exercise C: Converting Environment Variables Correctly

1. Configure **spring.main.log-startup-info=false** using env.
2. Set **SPRING_MAIN_LOGSTARTUPINFO=false**.
3. Run the application in the same shell/container having that variable.
4. Compare with running without the variable.

**Key takeaway:** dashes in canonical properties are removed when forming env variable names.

### Exercise D: Config Data Location Is a Bootstrap Property

1. Create an **extra-config/** folder containing **application.properties**.
2. In that file set **logging.level.root=WARN**.
3. Launch with **--spring.config.additional-location=optional:file:./extra-config/**.
4. Verify the log level took effect.
5. Remove the argument and re-run to compare.

**Key takeaway:** Config Data paths must be known early enough.

### Exercise E: Writing an EnvironmentPostProcessor

1. Write **CompanyLoggingEnvironmentPostProcessor** as in section 14.
2. Register the class via **META-INF/spring.factories**.
3. Set **COMPANY_BOOTSTRAP_LOG_LEVEL=WARN**.
4. Ensure **logging.level.root** is absent from higher-priority sources if you want to observe the fallback.
5. Run and observe the output.
6. Pass **--logging.level.root=DEBUG** and compare.

**Key takeaway:** a PropertySource added early can serve startup, yet precedence still decides the final value.

### Exercise F: Distinguishing Programmatic Defaults and Command Line

1. Call **setDefaultProperties** before **run(...)** with **spring.main.banner-mode=off**.
2. Run without overrides.
3. Run with **--spring.main.banner-mode=console**.
4. Inspect the behavior.

**Key takeaway:** default properties serve as fallbacks, not necessarily the final value.

### Exercise G: Non-Web Mode

1. Use a Spring Boot app with an embedded web server.
2. Run normally and observe the started port.
3. Run the same JAR with **--spring.main.web-application-type=none**.
4. Observe the difference in web context and embedded server.

**Key takeaway:** startup properties can change the ApplicationContext type, not just a single bean field.

## 23. Diagnostic Checklist for an Early-Read Property

When **logging.*** or **spring.main.*** has no effect, check:

1. Is the canonical key name correct?
2. Was the value provided **before SpringApplication read the key**?
3. Did the value come from Config Data, env, system property, CLI, or @PropertySource?
4. If using @PropertySource, is that source only added during refresh?
5. If using env, did the variable actually enter the Java process?
6. Did the variable name omit dashes according to the rules?
7. Is a higher-priority source overriding it?
8. Is there a custom **setAddCommandLineProperties(false)** call?
9. Is **spring.config.location** causing default locations to be replaced?
10. Was the supplementary file loaded early via **spring.config.import** or late via @PropertySource?
11. Is there programmatic code customizing SpringApplication before run?
12. For EnvironmentPostProcessor, is **spring.factories** correct?
13. Does the processor run in an appropriate order relative to Config Data and logging?
14. Was the new source added via addFirst or addLast, and what is the precedence intent?
15. Does the property affect startup or only business beans?
16. If the property appears in Environment after refresh, at what point did it appear?
17. Is a restart/rolling redeploy needed after changing env or files?
18. Are you using a test harness that does not fully simulate SpringApplication startup?
19. If changing web-application-type, is not starting the server the intended consequence?
20. Are you logging/exposing sensitive information while debugging Environment?

## 24. Summary

- Spring Boot has properties read **before ApplicationContext refresh**, notably several **logging.*** and **spring.main.*** properties.
- **@PropertySource** on a @Configuration class is processed during context refresh, making it too late to control certain startup decisions.
- **Config Data**, command line, Java system properties, and OS env are appropriate sources for supplying values early.
- **spring.config.name**, **spring.config.location**, and **spring.config.additional-location** must be present even earlier to help Spring Boot locate Config Data.
- **spring.config.import** is processed during the Config Data phase, unlike @PropertySource.
- **SpringApplication.setDefaultProperties(...)** provides programmatic fallbacks before run, not an override with absolute precedence.
- **EnvironmentPostProcessor** can add PropertySources before refresh when the application has custom bootstrap needs.
- In Spring Boot 3.3, register EnvironmentPostProcessor via **META-INF/spring.factories**.
- Source precedence and source appearance timing are **two independent axes**, both affecting early-read properties.
- **Environment.getProperty(...)** reading a value after refresh does not prove an earlier startup decision was updated.
- Use **@ConfigurationProperties** for subsystem configuration; use properly timed bootstrap extensions for properties controlling SpringApplication/logging.

## Official References

- Spring Boot 3.3 — *Externalized Configuration*, especially *PropertySource Order*, *Config Data Files*, and *Config Data Location*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — *Logging*: https://docs.spring.io/spring-boot/3.3/reference/features/logging.html
- Spring Boot 3.3 — *EnvironmentPostProcessor API*: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html
- Spring Boot 3.3 — *SpringApplication API*: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Framework — *Environment Abstraction*: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
