# Startup Information and `spring.main.log-startup-info`

When launching Spring Boot, the console usually displays a banner and several log lines: the application class being run, Java version, process ID (PID), active profiles, `ApplicationContext` creation, the initialized web server, and startup duration. These lines help developers see which step the application has reached, yet **not all of them are produced by the same component**.

The **`spring.main.log-startup-info`** property controls the group of **startup information actively logged by `SpringApplication`**. Understanding the exact scope of this property helps reduce unnecessary messages while keeping important diagnostic logs from libraries, the web server, and business code.

## 1. Reading Common Startup Information

Under default logging settings, a Spring Boot application may print messages like:

~~~text
INFO  ... c.example.StartupInfoDemo : Starting StartupInfoDemo using Java 21 ...
INFO  ... c.example.StartupInfoDemo : The following 1 profile is active: "dev"
INFO  ... o.s.b.w.embedded.tomcat.TomcatWebServer : Tomcat initialized with port 8080 (http)
INFO  ... o.s.b.w.embedded.tomcat.TomcatWebServer : Tomcat started on port 8080 (http) with context path '/'
INFO  ... c.example.StartupInfoDemo : Started StartupInfoDemo in 2.345 seconds (process running for 2.789)
~~~

This is an **illustrative sample of message groups**, not fixed output for every run. Timing, PID, Java version, class names, paths, web server, and the ordering of lines coming from libraries vary by application and environment.

| Displayed Group | Information Provided | Typical Logging Component |
| --- | --- | --- |
| `Starting StartupInfoDemo ...` | Application/launcher class name, Java version, PID, launch location, and environment details if present | `SpringApplication`'s startup info logger |
| `The following 1 profile is active ...` or `No active profile set ...` | Active profiles or default profile | `SpringApplication` |
| `Tomcat initialized ...`, `Tomcat started ...` | Embedded HTTP server status | Tomcat / Spring Boot Web Server classes |
| `Started StartupInfoDemo in ...` | Elapsed time from start until `ApplicationContext` has been created and refreshed successfully | `SpringApplication`'s startup info logger |
| Logs from `@Service`, `@Component`, or other libraries | Bean initialization results, connections, business checks, and component diagnostics | Respective component loggers |

**Do not infer that every line appearing during startup is `SpringApplication`'s "startup info".** For example, Tomcat logs also appear during startup, yet they are managed by a different logger.

## 2. What Is `spring.main.log-startup-info`?

`spring.main.log-startup-info` is a boolean Spring Boot property bound to `SpringApplication`'s configuration. Its default value is **`true`**.

- **`true` (default):** `SpringApplication` is allowed to log the session opening message, active profiles, and the `Started ...` message once context initialization succeeds, subject to the active log threshold.
- **`false`:** omits the startup messages listed above emitted by `SpringApplication` itself, including the profile message and `Started ...`. The application still executes the normal initialization process.

In Spring Boot 3.3, this flag is used at two main points: when preparing `ApplicationContext` to decide whether to call `logStartupInfo(...)` and `logStartupProfileInfo(...)`; and after refreshing the context successfully to decide whether to log `Started ...`.

### What Can Still Be Displayed When Set to `false`?

| Output Type | Directly Disabled by `log-startup-info=false`? | Explanation |
| --- | --- | --- |
| `Starting ...` for the main class | **Yes** | Part of the opening log group written by `SpringApplication` |
| `No active profile ...` / `The following ... profile ...` | **Yes** | Profile information written by `SpringApplication` |
| `Started ... in ... seconds` for the main class | **Yes** | Part of the context creation/refresh completion log group |
| Spring Boot Banner | **No** | Banner is controlled separately by `spring.main.banner-mode` |
| Startup logs from Tomcat, Hibernate, HikariCP, or libraries | **No** | They use their own loggers; still governed by their logging configuration |
| `log.info(...)` in application code | **No** | Determined by the application's loggers and log thresholds |
| `System.out.println(...)` in application code | **No** | Prints directly to the standard output stream |
| Startup errors, exceptions, and error handling | **No** | The flag does not turn off error reporting or prevent startup from failing |

Some log lines may still be hidden by **logging levels** configured elsewhere. Therefore, to draw conclusions about this flag's effect, keep logging configuration constant and change only `spring.main.log-startup-info` between two runs.

This flag **does not disable bean loading, does not change profiles, does not skip web server startup, does not shorten the application lifecycle, and does not alter business results**. It only toggles a group of messages used to observe the startup process.

## 3. How It Is Handled When `SpringApplication.run(...)` Is Called

You can visualize the milestones related to startup info as follows:

~~~text
main(String[] args)
    |
    v
SpringApplication.run(args)
    |
    +-- Prepare Environment, read spring.main.* configuration
    |
    +-- Print banner if banner mode permits
    |
    +-- Create and prepare ApplicationContext
    |      |
    |      +-- log-startup-info=true?
    |             +-- Yes: Starting ... and profile info
    |             +-- No: skip this log group
    |
    +-- Refresh ApplicationContext, initialize beans and web server if any
    |      +-- Other components may write their own logs
    |
    +-- log-startup-info=true?
    |      +-- Yes: Started ... and startup duration info
    |      +-- No: skip this log group
    |
    +-- Publish ApplicationStartedEvent and invoke ApplicationRunner / CommandLineRunner
    |
    +-- Publish ApplicationReadyEvent when runners finish
    |
    v
Application ready per Spring Boot lifecycle
~~~

The diagram illustrates **the flow relevant to this lesson**, rather than listing every internal callback or listener.

Three things to distinguish:

1. **Seeing `Started ...` does not mean every subsequent task has finished.** In Spring Boot 3.3, the context-initialization completion message is logged before running `ApplicationRunner` and `CommandLineRunner`. `ApplicationReadyEvent` comes after the runners.
2. **Hiding `Started ...` does not mean the application is not running.** You can inspect state via lifecycle events or health/readiness mechanisms if the application has configured them.
3. **The duration in the log is not the time until the app is ready to serve all business requests.** For instance, runner work may need extra time, external dependencies may not be healthy yet, or readiness may not yet allow receiving traffic.

## 4. Configuring via Files, Command Line, and Environment Variables

There are multiple ways to supply the same property. Within a single experiment, choose one clear source for easy comparison.

### Option A — `application.properties`

In `src/main/resources/application.properties`:

~~~properties
spring.main.log-startup-info=false
~~~

To return to default behavior, remove this line or set:

~~~properties
spring.main.log-startup-info=true
~~~

### Option B — `application.yml`

In `src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    log-startup-info: false
~~~

Avoid declaring both `application.properties` and `application.yml` simultaneously for the same test, as that makes tracking the actual configuration source harder.

### Option C — Application Arguments When Running a JAR or Gradle

With an executable JAR built by a Spring Boot project:

~~~bash
java -jar build/libs/startup-info-demo.jar --spring.main.log-startup-info=false --spring.profiles.active=dev
~~~

With Gradle's `bootRun` task:

~~~bash
./gradlew bootRun --args="--spring.main.log-startup-info=false --spring.profiles.active=dev"
~~~

In PowerShell on Windows:

~~~powershell
.\gradlew.bat bootRun --args="--spring.main.log-startup-info=false --spring.profiles.active=dev"
~~~

`startup-info-demo.jar` is an illustrative JAR name; use the actual file name produced by your project. The two `--`-prefixed arguments are passed to the application, allowing Spring Boot to put them into the configuration system via the default mechanism. Even though the `dev` profile message no longer appears in startup logs, **the `dev` profile is still activated**.

You can pass a system property to the **application JVM**:

~~~bash
java -Dspring.main.log-startup-info=false -jar build/libs/startup-info-demo.jar
~~~

For `java -jar`, place `-D...` **before** `-jar`. When running via Gradle, do not assume `./gradlew -Dspring.main.log-startup-info=false bootRun` automatically forwards Gradle's system property to the application JVM. Use `--args` as above or configure `bootRun` explicitly if VM options are needed.

### Option D — Environment Variables

Example in Bash:

~~~bash
SPRING_MAIN_LOG_STARTUP_INFO=false java -jar build/libs/startup-info-demo.jar
~~~

Example in PowerShell:

~~~powershell
$env:SPRING_MAIN_LOG_STARTUP_INFO = "false"
java -jar build/libs/startup-info-demo.jar
~~~

Spring Boot supports binding configuration properties from environment variables according to its naming rules; the variable name here corresponds to `spring.main.log-startup-info`.

If a property is set in multiple sources, **configuration source precedence rules** decide which value Spring Boot receives. For example, the application argument `--spring.main.log-startup-info=true` typically takes precedence over `false` in `application.properties`. When testing, check overriding sources before concluding a property does not work.

## 5. Enabling or Disabling in Java

With the standard entry point, Spring Boot binds the property from configuration automatically:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StartupInfoDemo {
    public static void main(String[] args) {
        SpringApplication.run(StartupInfoDemo.class, args);
    }
}
~~~

If you need to configure the `SpringApplication` instance directly before running, you can write:

~~~java
public static void main(String[] args) {
    SpringApplication application = new SpringApplication(StartupInfoDemo.class);
    application.setLogStartupInfo(false);
    application.run(args);
}
~~~

The second `main` snippet is an **alternative** to the first `main` snippet, living inside the same `StartupInfoDemo` class and requiring the imports shown. The `setLogStartupInfo(false)` method expresses the same intent at the API level. When testing, avoid setting conflicting values across multiple sources simultaneously without checking binding precedence.

If you only need to turn off startup info per environment, configuration files or command-line arguments are usually easier to manage. Setting it in Java fits cases where the application itself builds and customizes `SpringApplication`.

## 6. Runnable Hands-On Example in a Spring Boot 3.x Project

Create a **Spring Boot 3.x project using Java 17 or newer** with at least `spring-boot-starter` and Gradle or Maven. In package `com.example.runtime`, create `StartupInfoDemo.java`:

~~~java
package com.example.runtime;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class StartupInfoDemo {

    public static void main(String[] args) {
        SpringApplication.run(StartupInfoDemo.class, args);
    }

    @Bean
    ApplicationRunner showProfiles(Environment environment) {
        return arguments -> System.out.println(
                "APP_DIAGNOSTIC activeProfiles="
                        + Arrays.toString(environment.getActiveProfiles()));
    }
}
~~~

This is a complete program **inside a project that already has Spring Boot and its dependencies**, rather than something that can be compiled with `javac StartupInfoDemo.java` alone without Spring Boot on the classpath.

### Run 1: Startup Info Enabled

Run via Gradle Wrapper:

~~~bash
./gradlew bootRun --args="--spring.profiles.active=dev --spring.main.log-startup-info=true"
~~~

You can observe these message groups (assuming INFO level is enabled):

- The `Starting StartupInfoDemo ...` message.
- The message stating profile `dev` is active.
- The `Started StartupInfoDemo in ...` message if context initialization succeeds.
- The line printed by **the example code**: `APP_DIAGNOSTIC activeProfiles=[dev]`.

Other logs depend on project dependencies. With an example having only `spring-boot-starter`, there is no reason for Tomcat startup logs to appear automatically. If `spring-boot-starter-web` is added, lines from the embedded web server can appear.

### Run 2: Startup Info Disabled

Keep the same project and run:

~~~bash
./gradlew bootRun --args="--spring.profiles.active=dev --spring.main.log-startup-info=false"
~~~

Results to compare:

| Indicator | `true` | `false` |
| --- | --- | --- |
| `Starting StartupInfoDemo ...` logged by `SpringApplication` | Yes, if logger permits INFO | No |
| `dev` profile message logged by `SpringApplication` | Yes, if logger permits INFO | No |
| `Started StartupInfoDemo in ...` logged by `SpringApplication` | Yes, if logger permits INFO | No |
| `APP_DIAGNOSTIC activeProfiles=[dev]` from `ApplicationRunner` | Yes | Yes |
| Beans initialized, runner invoked | Yes, barring other errors | Yes, barring other errors |
| Banner or logs from other components | Per their own config | Per their own config |

Running via Gradle may emit **Gradle** logs such as task status or `BUILD SUCCESSFUL` after the application process exits; those lines are likewise not controlled by `spring.main.log-startup-info`.

The `APP_DIAGNOSTIC activeProfiles=[dev]` line is the key verification: profile configuration still takes effect even though `SpringApplication`'s profile log is gone. If the project has other startup runners, their timing or line order depends on runner ordering; the toggle behavior of the property itself remains as shown above.

## 7. Distinguishing from Banner, Log Levels, and `--debug`

These configuration groups handle different tasks:

| Goal | Appropriate Configuration | Scope |
| --- | --- | --- |
| Hide opening, profile, and `Started ...` logs from `SpringApplication` | `spring.main.log-startup-info=false` | One specific startup log group |
| Hide the Spring Boot banner art | `spring.main.banner-mode=off` | Banner, not all logs |
| Hide most INFO messages | `logging.level.root=WARN` or granular logger config | All loggers governed by that threshold; broader impact |
| View extra diagnostics for auto-configuration conditions | `--debug` and appropriate logging config | Diagnostics, not for toggling startup info alone |

Example to reduce both commonly seen outputs:

~~~properties
spring.main.log-startup-info=false
spring.main.banner-mode=off
~~~

These two lines are **not complete silence mode**. Logs from the framework, libraries, and application can still appear. If you need to change log levels, configure the exact target logger or logger group while keeping necessary error messages.

Additional note: setting `logging.level.root=ERROR` just to hide `Starting ...` can accidentally lose useful INFO messages from Hibernate, the web server, database connections, or application code. When you only want cleaner startup logs, `spring.main.log-startup-info=false` has a narrower scope.

## 8. Startup Information and Readiness Are Two Different Things

The `Started ...` log only provides an **observational signal** that a startup phase has passed. For real system orchestration, rely on appropriate lifecycle events or status-check endpoints:

- `ApplicationStartedEvent`: published after `ApplicationContext` is refreshed, before invoking `ApplicationRunner` and `CommandLineRunner`.
- `ApplicationReadyEvent`: published after runners finish; indicates the application has reached the ready stage of the Spring Boot lifecycle.
- **Readiness/health checks**: if the application has enabled appropriate checks, they provide operational signals for the orchestrator to decide whether to route traffic to the application.

Changing `spring.main.log-startup-info` does not alter when these events are published. For example, when using container orchestration, do not rely on the presence or absence of the string `Started` as the sole way to evaluate application health. When an app encounters a real initialization error, it can still fail even with startup info disabled.

## 9. Common Misunderstandings

**Scenario 1: Set `false` yet still seeing Tomcat logs.** This is normal. Tomcat logs come from the embedded server's logger. To control them, find the corresponding logger and log level; do not expect `spring.main.log-startup-info` to turn them off.

**Scenario 2: Set `true` yet not seeing `Starting ...`.** Check the log threshold for the main/root class, overriding configuration sources, how the app is launched, and where logs are collected. `true` permits `SpringApplication` to log; it does not force every logging setup to display INFO.

**Scenario 3: Not seeing profile logs and assuming profiles are inactive.** `false` suppresses the message without changing `Environment.getActiveProfiles()`. Check active profiles via `Environment`, effective configuration, or appropriate diagnostic tools.

**Scenario 4: Turned off the banner too, yet still seeing `Started ...`.** `spring.main.banner-mode=off` only handles the banner. Set `spring.main.log-startup-info=false` if you want to omit `SpringApplication`'s startup information.

**Scenario 5: Saw `Started ...` and assumed all initialization work is complete.** Runners may not have finished yet. Observe `ApplicationReadyEvent` or readiness when you need to confirm the right moment for traffic.

**Scenario 6: Passed the property to the wrong process.** `java -Dspring.main.log-startup-info=false -jar ...` affects the application JVM. However, `./gradlew -Dspring.main.log-startup-info=false bootRun` may only set the property on Gradle's JVM; to be explicit, use `bootRun --args="--spring.main.log-startup-info=false"`.

**Scenario 7: Using `false` to "hide" all details when startup fails.** This property is neither an error-handling tool nor a security control. Error messages are emitted by other mechanisms, and printing sensitive data must be controlled at the log source.

## 10. Self-Check Questions

1. If `spring.main.log-startup-info=false` and `spring.main.banner-mode=console` are both set, can the banner appear? **Yes.** These are two independent configuration groups.
2. If you pass `--spring.profiles.active=dev` together with `--spring.main.log-startup-info=false`, which profile is active? **`dev`.** Only the profile log line emitted by `SpringApplication` is hidden.
3. Why is changing `logging.level.root=WARN` different from changing `spring.main.log-startup-info=false`? **Because log levels apply broadly across many loggers**, whereas the startup info property controls only one message group from `SpringApplication`.
4. When the `Started` log is no longer present, what should you rely on to know the application is ready? **`ApplicationReadyEvent`, appropriate readiness/health checks, and operational verification**, depending on the need.
5. After adding `spring-boot-starter-web` and seeing `Tomcat started ...` despite disabling startup info, is that a misconfiguration? **No.** That is a log from the web server component.

**Key takeaway:** `spring.main.log-startup-info` decides whether to log **opening, profile, and startup-completion information from `SpringApplication`**. It **does not alter the execution flow**, **does not turn off the banner**, **does not disable logs from other components**, and **is not a readiness signal**.

### References

- Spring Boot 3.3 — `SpringApplication` API, `setLogStartupInfo(boolean)`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot — SpringApplication / Startup Information: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot 3.3 — `SpringApplication` source code to verify the `logStartupInfo` branch: https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/SpringApplication.java
