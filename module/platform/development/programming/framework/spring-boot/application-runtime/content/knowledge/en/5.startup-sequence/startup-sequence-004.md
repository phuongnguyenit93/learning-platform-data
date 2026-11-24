# Early Logging Initialization and Banner Display in Spring Boot

When running a Spring Boot application, you usually see the Spring Boot logo (banner), followed by "Starting ..." log lines, active profiles, web server information, and finally the startup message. However, **the order shown on the terminal is not the bean creation order**. Logging is prepared very early to capture bootstrap errors, whereas the banner is printed after `Environment` has been prepared and before `ApplicationContext` finishes initializing.

This lesson explains how early logging works, why some properties have no effect at the very start, how to control the banner, and how to verify the startup order yourself. The sample code uses **Java 17+ and Spring Boot 3.3.x**; the workflow is also useful for other Boot 3.x applications.

## 1. Logging Must Be Ready Before Beans Exist

Every Java program starts from `main(String[] args)`. Yet when calling `SpringApplication.run(...)`, Spring Boot must still read configuration, determine profiles, prepare the environment, create the context, read bean definitions, perform dependency injection, and possibly open an HTTP server. **Errors can occur at any step**.

If you waited until `@Configuration`, `@Service`, or `CommandLineRunner` beans were active before setting up logging, the system could not record failures occurring earlier. That is why Boot has a logging initialization step belonging to **bootstrap**.

Three concepts to distinguish:

| Component | Responsibility |
|---|---|
| Logging API, usually SLF4J | Provides calls such as `log.info(...)` and `log.error(...)` to emit messages. |
| Logging backend, usually Logback | Determines log levels, formatting, appenders, files, or console output. |
| Spring Boot's `LoggingSystem` | Coordinates the backend based on the classpath and configuration known during startup. |

With the default starter, Spring Boot usually brings `spring-boot-starter-logging` onto the classpath and uses Logback. If an application switches to Log4j2, the corresponding dependencies must be configured; do not leave two backends and conflicting logging bindings on the classpath.

**"Logging is initialized early" does not mean the final configuration exists right before calling `run`.** A logger created in a static field can exist prior to bootstrap. Log statements running too early may be governed by the default backend configuration before Spring Boot's properties are applied.

## 2. Where Does Logging Sit in the Startup Sequence?

Here is the conceptual sequence of a successful startup:

~~~mermaid
flowchart TD
    A["JVM enters main()"] --> B["SpringApplication.run(args)"]
    B --> C["ApplicationStartingEvent"]
    C --> D["Prepare Environment and configuration sources"]
    D --> E["ApplicationEnvironmentPreparedEvent"]
    E --> F["Finalize logging configuration from Environment"]
    F --> G["Print banner if enabled"]
    G --> H["Create/prepare ApplicationContext"]
    H --> I["Refresh context, create beans and server if needed"]
    I --> J["ApplicationStartedEvent"]
    J --> K["ApplicationRunner / CommandLineRunner"]
    K --> L["ApplicationReadyEvent"]
    L --> M["run() returns context"]
~~~

Note that this is a **milestone diagram**, not Spring Boot's line-by-line source code.

During this process:

1. `ApplicationStartingEvent` occurs very early, before `ApplicationContext` or a complete `Environment` exists. Boot's bootstrap listeners, including the component handling logging, can perform initial setup here.
2. Boot prepares `Environment` from appropriate configuration sources such as config data files, system properties, environment variables, and command-line arguments.
3. When `ApplicationEnvironmentPreparedEvent` is published, relevant listeners can use the discovered configuration to set up logging in greater detail.
4. Spring Boot selects and prints the banner according to the configured mode.
5. The context is created and refreshed; beans, runners, web server, and lifecycle events are processed in turn.

For a normal startup, **the banner appears before the application is ready**. A printed banner does not prove that beans have finished instantiating, that the server is accepting requests, or that the application can serve traffic.

The "Started ... in ... seconds" log line should also not be equated with `ApplicationReadyEvent`: runners can still execute after the "Started" line, and a runner throwing an error can still cause that startup to fail.

## 3. Configuring Logging Early Enough with `application.properties`

In a typical Spring Boot project, `application.properties` and `application.yml` files are processed as config data during the `Environment` preparation phase. Example:

~~~properties
spring.application.name=boot-startup-demo
spring.main.banner-mode=console

logging.level.root=INFO
logging.level.com.example.startup=DEBUG
logging.level.org.springframework=INFO
~~~

Explanation:

- `logging.level.root=INFO` applies INFO to the root logger; DEBUG messages from packages without specific settings generally do not appear.
- `logging.level.com.example.startup=DEBUG` enables DEBUG logs from code in this package and matching loggers.
- `logging.level.org.springframework=INFO` keeps framework logs at the INFO level.
- `spring.application.name` specifies the application name, which can also be interpolated into the banner.
- `spring.main.banner-mode=console` instructs the banner to print to the console.

If you only need to change log levels, in most cases you do not need to create a `logback-spring.xml` file.

Configuration can be passed from the command line, for example with the Gradle Boot plugin:

~~~bash
./gradlew bootRun --args='--logging.level.com.example.startup=TRACE'
~~~

From Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--logging.level.com.example.startup=TRACE"
~~~

These commands run in a project directory that already has the Gradle wrapper and `bootRun`. Arguments after `--args` are passed to the **Java application**, allowing them to override corresponding values in `application.properties` per Spring Boot's precedence rules.

### Why Might `@PropertySource` Have No Effect on Early Logging?

Suppose a configuration class contains:

~~~java
@Configuration
@PropertySource("classpath:extra-logging.properties")
public class ExtraConfiguration {
}
~~~

The snippet above is **only a declaration example**, requiring imports for `org.springframework.context.annotation.Configuration` and `PropertySource` along with a corresponding configuration file. When Boot performs initial logging setup, the `ExtraConfiguration` class has usually not yet been processed by the container, so `logging.level.*` placed in `extra-logging.properties` can arrive too late. Move early logging configuration into Boot config data, command-line arguments, or appropriate JVM system properties.

Similarly, an `@EventListener(ApplicationStartingEvent.class)` bean is not a reliable way to catch ultra-early events: that bean has not been created yet when the event is emitted. If you need to observe bootstrap, register a listener directly on `SpringApplication` **before** calling `run`.

## 4. Runnable Java Example: Observing Logging, Banner, and Context

Create a Spring Boot 3.3.x application with `spring-boot-starter`. Place the following class in `src/main/java/com/example/startup/StartupLoggingDemo.java`:

~~~java
package com.example.startup;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class StartupLoggingDemo {

    private static final Logger log =
            LoggerFactory.getLogger(StartupLoggingDemo.class);

    public static void main(String[] args) {
        System.out.println("[1] main: before run()");

        SpringApplication application =
                new SpringApplication(StartupLoggingDemo.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        // This listener is registered before the context exists.
        application.addListeners(
                (ApplicationListener<ApplicationEnvironmentPreparedEvent>)
                        event -> System.out.println(
                                "[2] environment: "
                                        + event.getEnvironment().getProperty(
                                                "spring.application.name", "unknown")
                        )
        );

        ConfigurableApplicationContext context = application.run(args);

        System.out.println("[4] after run: " + context.isActive());
        context.close();
    }

    @Bean
    CommandLineRunner startupRunner() {
        return args -> {
            log.info("INFO from startup runner");
            log.debug("DEBUG from startup runner");
            System.out.println("[3] runner: executed");
        };
    }
}
~~~

To avoid HTTP server side effects on the output, the code uses `WebApplicationType.NONE`. The `@SpringBootApplication` class still initializes the Spring context, auto-configuration, and runner bean as usual.

Place `src/main/resources/application.properties`:

~~~properties
spring.application.name=boot-startup-demo
spring.main.banner-mode=console
logging.level.root=INFO
logging.level.com.example.startup=DEBUG
~~~

Place `src/main/resources/banner.txt`:

~~~text
=========================================
 STARTUP APP: ${spring.application.name}
 SPRING BOOT: ${spring-boot.version}
=========================================
~~~

Run with `./gradlew bootRun` or `.\gradlew.bat bootRun`. For a Maven project with the Spring Boot Maven plugin, you can run `./mvnw spring-boot:run` and specify the appropriate main class.

**The milestone lines printed by the example itself**, in relative order, are:

~~~text
[1] main: before run()
[2] environment: boot-startup-demo
... banner containing STARTUP APP ...
... INFO/DEBUG log lines from Spring and the runner ...
[3] runner: executed
[4] after run: true
~~~

Lines with `...` are **explanatory notes**, not verbatim stdout. In an actual run, the banner interpolates the name `boot-startup-demo` and the concrete Spring Boot version; logs include timestamps, PID, and other fields. Spring Boot may interleave additional logs at various points. What is verified is:

- Milestone `[1]` runs before `run()`.
- Milestone `[2]` receives the application name from `Environment` and occurs before the banner is printed.
- The default `console` mode banner is processed before the context finishes initializing.
- The runner bean executes after the context refresh step, before `run()` returns.
- Line `[4]` runs after `run()` has returned a still-active context; the program then proactively closes the context to exit cleanly.

The `log.info` and `log.debug` calls in the runner use SLF4J to verify that the log configuration for `com.example.startup` is applied. Deliberately using `System.out.println` at the two bootstrap milestones lets you observe the order without depending on whether the logger has finalized its configuration yet.

## 5. How Is the Banner Located and Processed?

If not disabled, Spring Boot has a default text banner. To customize its content, place a `banner.txt` file at the classpath root:

~~~text
src/main/resources/
├── application.properties
└── banner.txt
~~~

These are files inside the project's source tree. Depending on build configuration, they are placed onto the runtime classpath when running `bootRun` or packaging a JAR.

A banner can use placeholders such as:

| Placeholder | Purpose |
|---|---|
| `${spring.application.name}` | Application name if the property already exists in `Environment`. |
| `${spring-boot.version}` | Running Spring Boot version. |
| `${spring-boot.formatted-version}` | Spring Boot version in formatted display form. |
| `${application.version}` | Version from package/manifest when supported by launcher and metadata. |
| `${AnsiColor.GREEN}` | ANSI color code if the output supports it. |

Note that variables related to `application.version` and `application.title` may not resolve in every kind of run from an IDE/Gradle; these values are tied to manifest information and how the app is launched. If you simply want the service name to always appear, setting `spring.application.name` directly is usually easier to control.

Change the banner location with:

~~~properties
spring.banner.location=classpath:banners/project-banner.txt
~~~

Then save the file at `src/main/resources/banners/project-banner.txt`. If using Vietnamese characters, save as UTF-8, matching the default `spring.banner.charset`; check the actual terminal font and encoding if characters render garbled.

The banner should contain the name, version, and non-sensitive identification info. Do not put secrets, tokens, passwords, or personal data into the banner because terminals, build logs, or log collection systems may persist that content.

## 6. Three Banner Modes: `console`, `log`, `off`

The `spring.main.banner-mode` setting controls **the banner**, not all logging:

| Value | Behavior |
|---|---|
| `console` | Prints the banner to `System.out`; this is the default behavior. |
| `log` | Sends the banner through the logging system, subject to loggers, levels, appenders, and filters. |
| `off` | Does not print the banner. |

Example:

~~~properties
spring.main.banner-mode=off
~~~

It can be changed at launch time:

~~~bash
./gradlew bootRun --args='--spring.main.banner-mode=log'
~~~

Or configured in Java before launching:

~~~java
SpringApplication application =
        new SpringApplication(StartupLoggingDemo.class);
application.setBannerMode(org.springframework.boot.Banner.Mode.OFF);
application.run(args);
~~~

The snippet above **illustrates replacing the configuration portion inside the `main` method**, not a standalone program. If multiple sources set banner mode, apply actual configuration precedence rules to avoid misunderstanding why a value was overridden.

**Two common misconceptions:**

- `spring.main.banner-mode=off` does **not** disable INFO/WARN/ERROR logs. It only disables the banner.
- `logging.level.root=OFF` does not necessarily hide the banner in `console` mode, because the banner prints directly via `System.out` rather than through an ordinary logger.

When switching the banner to `log` mode, it can go into log files or be suppressed by logging configuration. When choosing `console`, the banner can appear on the terminal even if you write logger messages only to a file.

## 7. Controlling Startup Log Lines

Spring Boot typically prints log lines containing the main class name, Java version, active profiles, web server, and startup duration. Illustrative template:

~~~text
2026-01-01T10:00:00.000+07:00  INFO 1234 --- [boot-startup-demo] [main] c.e.startup.StartupLoggingDemo : Starting StartupLoggingDemo
~~~

This is a **formatting example**, not a fixed output. Timestamp, PID, thread, and pattern depend on the Boot version and backend configuration.

To reduce startup announcements written by `SpringApplication` itself, you can set:

~~~properties
spring.main.log-startup-info=false
spring.main.banner-mode=console
~~~

`spring.main.log-startup-info=false` turns off a group of startup informational logs from `SpringApplication`, including the active profile log. It **does not disable all loggers**, does not disable error logs, and does not automatically disable the banner.

### `--debug` Mode Is Not `logging.level.root=DEBUG`

- `--debug` or `debug=true` increases verbosity for **a set** of core loggers related to Boot/embedded servers and can help display the condition evaluation report.
- `logging.level.root=DEBUG` enables DEBUG on the root logger, dramatically increasing log volume from libraries.
- `logging.level.com.example.startup=DEBUG` targets only the specified package, making it more suitable when debugging your own startup code.

When investigating an issue, prefer enabling DEBUG selectively. Keeping the entire root logger at DEBUG/TRACE for long periods can generate huge logs and easily leak sensitive data into logging systems.

### Writing Logs to a File

When using Spring Boot's default Logback configuration:

~~~properties
logging.file.name=logs/boot-startup-demo.log
spring.main.banner-mode=console
~~~

`logging.file.name` directs logs to be written to a file while normally keeping console output. However, the banner in `console` mode goes straight to stdout and therefore **is not guaranteed** to appear in the log file. If you want the banner to go through the logger, consider `banner-mode=log` and check your actual appenders/filters.

## 8. When to Use `logback-spring.xml`?

If you only need to set log levels, `application.properties` is simple and clear enough. When you need custom patterns, multiple appenders, rolling policies, complex formatting, or profile-based conditions, use Logback's native configuration.

With Spring Boot 3.3, prefer `logback-spring.xml` when you need Boot extensions. A standard `logback.xml` file can be processed by Logback itself **very early**, before Boot supports extensions such as `<springProfile>` or `<springProperty>`. By contrast, `logback-spring.xml` is coordinated by Spring Boot once the appropriate environment is ready.

Example at `src/main/resources/logback-spring.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <include resource="org/springframework/boot/logging/logback/defaults.xml"/>
    <include resource="org/springframework/boot/logging/logback/console-appender.xml"/>

    <springProfile name="dev">
        <logger name="com.example.startup" level="DEBUG"/>
    </springProfile>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

This snippet assumes the project uses **Logback with Spring Boot 3.3's standard include structure**. When the `dev` profile is active, the application package's logger has level DEBUG; root stays at INFO. If the project already has another backend configuration file, consolidate them rather than keeping competing configuration files.

When placing a native configuration file in a non-default location, you can set:

~~~properties
logging.config=classpath:logging/custom-logback-spring.xml
~~~

And make sure the file actually exists at `src/main/resources/logging/custom-logback-spring.xml`. When switching to Log4j2, you must use the corresponding configuration and starter; a Logback file has no effect on another backend.

An important point: **native configuration does not alter the bootstrap order**. It only specifies how the logging backend behaves at the points where Spring Boot can apply that configuration.

## 9. Distinguishing Banner, Logs, and Ready State

| Signal | What can be concluded | What cannot yet be concluded |
|---|---|---|
| Banner appears | Bootstrap has reached the banner-printing step. | Beans are fully initialized or the server is accepting requests. |
| "Starting ..." log | Startup is underway and the logger has written the message. | Startup will succeed. |
| "Started ..." log | The context has passed the main initialization steps. | Runners have completed. |
| `ApplicationReadyEvent` | The normal startup flow has finished the runners. | Every external dependency will always remain healthy. |
| Readiness probe succeeds | The application is reporting ready per the system's check at that moment. | Every future request will succeed. |

If the application fails after the banner appears, look for the exception's root cause in the logs. If an error occurs **before environment preparation completes or before printing the banner**, there may be no banner and part of the logging configuration may not yet have been fully applied.

The `APPLICATION FAILED TO START` notice provided by Spring Boot's failure analysis is **startup error diagnostic information**, not the application identification banner read from `banner.txt`.

## 10. Troubleshooting When Banner or Logs Do Not Behave as Expected

**Banner not visible**

- Check `spring.main.banner-mode`; a command-line property might override file configuration.
- Confirm `banner.txt` is on the runtime classpath or `spring.banner.location` points to the right file.
- If mode is `log`, check loggers, appenders, and log files. Content may be going to a file rather than the terminal.
- Check whether the application failed too early. Not every failed startup reaches the banner-printing step.
- If the banner has broken Vietnamese diacritics or colors, check UTF-8, terminal fonts, and ANSI support.

**DEBUG/INFO logs not visible**

- Check whether the active backend is Logback or another library, and inspect classpath dependencies.
- Compare logging levels of root, packages, and individual loggers; check filters/appenders.
- Confirm configuration lives in a source loaded **early enough**; `@PropertySource` does not replace bootstrap config data.
- If using a native file, verify `logback-spring.xml` or `logging.config` was actually found.
- If writing only to a file, do not conclude "the logger isn't running" just because the terminal shows nothing.
- Do not confuse Boot's `--debug` with enabling DEBUG for every logger.

**Logs before `run()` ignore properties**

This can happen because Boot has not finalized logging yet. Relying on configuration loaded **after `run()` starts** to format lines already emitted earlier is unreasonable. If you need diagnostics for ultra-early code, design minimal bootstrap logging and know what state the backend is in.

**Want to inspect startup order without noisy logs**

Start from the example in section 4. Set breakpoints in `main`, the `ApplicationEnvironmentPreparedEvent` listener, the runner, and the line after `run`. Use `System.out.println` only for practice milestones; in real applications, use logging APIs and selective levels.

## 11. Short Self-Verification Exercises

1. Run the example with `spring.main.banner-mode=console` and verify the banner appears between the environment milestone and the runner.
2. Switch to `off`. The banner disappears, while the runner and log lines still execute.
3. Switch to `log`, and observe the banner under logger formatting or in the log file if you configured file logging.
4. Change `logging.level.com.example.startup=INFO`, and compare the presence/absence of the `log.debug(...)` line in the runner.
5. Enable `spring.main.log-startup-info=false` and compare `SpringApplication`'s startup lines; confirm the banner still displays when mode is `console`.

### References for Spring Boot 3.3

- Logging: https://docs.spring.io/spring-boot/3.3/reference/features/logging.html
- SpringApplication and banner: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html

**Remember:** logging must be prepared from bootstrap so information is available if the application fails before the context is created. The banner is an identification display step during bootstrap, controlled by `spring.main.banner-mode`. The banner, the "Started ..." log, runner completion, and readiness state are **distinct milestones**; distinguishing them helps you configure and diagnose startup accurately.
