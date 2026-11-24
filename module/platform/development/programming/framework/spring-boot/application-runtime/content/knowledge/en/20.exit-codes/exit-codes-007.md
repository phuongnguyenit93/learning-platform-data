# Observing Exit Codes with ExitCodeEvent in Spring Boot

**Module:** Spring Boot Application Runtime → **Exit Codes**. This lesson focuses on `org.springframework.boot.ExitCodeEvent` — a Spring application event allowing listeners to **observe the exit code determined by Spring Boot**, especially when `SpringApplication.exit(...)` or startup failure handling resolves a non-zero exit code. It distinguishes the computed code, the published event, when `ApplicationContext` closes, and the **actual process termination code** observed by the shell, OS, or orchestrator.

The main example uses **Java 17+**, **Spring Boot 3.5.x**, a **command-line application with no web server**, Maven, and `spring-boot-starter`. Experiments cover exit 0, exit 7, startup failure with code 19, observation via `@EventListener`, and verification with `$?`/`$LASTEXITCODE`. Sections on multiple generators, exception mapping, and web apps are clearly marked so snippets are not confused with standalone programs.

## 1. Learning objectives

After this lesson, learners can:

1. Correctly import `ExitCodeEvent` from package `org.springframework.boot` and read `event.getExitCode()`.
2. Describe the relationship among `ExitCodeGenerator`, `SpringApplication.exit(context)`, `ExitCodeEvent`, `ApplicationContext.close()`, and `System.exit(code)`.
3. Explain why **exit code 0 does not publish `ExitCodeEvent`** on Spring Boot 3.5's standard exit path.
4. Create an `ExitCodeGenerator` bean and an `@EventListener(ExitCodeEvent.class)` or typed-parameter listener.
5. Observe a non-zero event published **before** `ContextClosedEvent` when calling `SpringApplication.exit(context)`.
6. Distinguish the **code returned by Spring Boot** from the **code returned by the JVM to the OS**; know why `System.exit(code)` is needed in CLIs.
7. Run the example with codes 0, 7, and 19; compare console markers and shell status.
8. Explain `ExitCodeGenerator` on exceptions and `ExitCodeExceptionMapper` during startup failure.
9. Know that multiple generators are sorted by `Ordered`/`@Order` and pick the **first non-zero code**, not the largest code by default.
10. Avoid confusing `ExitCodeEvent` with `ApplicationFailedEvent`, `ApplicationReadyEvent`, `ContextClosedEvent`, and Unix signals.
11. Recognize that the event will not necessarily appear on `SIGKILL`, JVM crashes, `Runtime.halt(...)`, or direct context closing.
12. Design logging, testing, and operational policies suited for batch jobs, CLIs, Docker, Kubernetes, and CI/CD.

**Key takeaway:** `ExitCodeEvent` reports the **exit code Spring Boot is processing**; it is not an API that terminates the JVM itself and **does not cover every reason a process stops**. To verify accurately, observe both the **event** and the **actual process exit status**.

## 2. Distinguishing five easily confused objects

| Object/API | Role | What it does **not** guarantee |
|---|---|---|
| `ExitCodeGenerator` | Computes an integer exit code via `getExitCode()` | Does not close the context or terminate the JVM itself |
| `SpringApplication.exit(context)` | Collects generators, computes code, publishes event if non-zero, then closes context | Does not call `System.exit` itself to return the code to the OS |
| `ExitCodeEvent` | Event carrying the determined code; `getExitCode()` returns `int` | Not an OS signal; does not catch every JVM death mode |
| `ContextClosedEvent` | Signals that the context is starting to close | Does not carry OS exit code; does not guarantee cleanup finished |
| `System.exit(code)` | Requests the JVM to terminate with the status code | Does not compute Spring codes itself; does not necessarily publish `ExitCodeEvent` |

**Two more events to distinguish:**

- `ApplicationReadyEvent`: Boot finished startup (including runners) on a successful run; **does not mean it is exiting**.
- `ApplicationFailedEvent`: Boot failed startup; **does not automatically guarantee `ExitCodeEvent` exists**. The exit event only occurs when a code path resolves a non-zero code and has a suitable context to publish. If failure occurs very early, listener beans may not exist yet.

### 2.1. Correct package for ExitCodeEvent

~~~java
import org.springframework.boot.ExitCodeEvent;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
~~~

**Do not import** `ExitCodeEvent` from `org.springframework.boot.context.event`. Namespace `org.springframework.boot.context.event` holds other Boot lifecycle events like `ApplicationReadyEvent`/`ApplicationFailedEvent`, whereas `ExitCodeEvent` resides directly in `org.springframework.boot`.

`ExitCodeEvent` is an `org.springframework.context.ApplicationEvent`. It has a constructor accepting `source` and an `int` code, plus `getExitCode()`. On the `SpringApplication.exit(context)` path, the source used by Boot is the application context.

## 3. Standard mechanism when closing a Spring Boot CLI application

Flow when startup succeeds and code intentionally decides to exit:

~~~text
public static void main(...)
    |
    v
SpringApplication.run(...)
    |
    +-- ApplicationContext refresh
    +-- ApplicationRunner / CommandLineRunner
    +-- ApplicationReadyEvent
    |
    v
SpringApplication.exit(context)
    |
    +-- collect ExitCodeGenerator beans in context
    +-- collect ExitCodeGenerator passed to exit(...) if any
    +-- sort by Ordered / @Order
    +-- pick first non-zero exit code (if any)
    |
    +-- if code != 0:
    |      context.publishEvent(new ExitCodeEvent(context, code))
    |         -> @EventListener / ApplicationListener observes
    |
    +-- close(context)
    |      -> ContextClosedEvent
    |      -> SmartLifecycle stop / bean destruction
    |
    v
SpringApplication.exit returns int code
    |
    v
System.exit(code)
    |
    v
OS / shell receives process exit status
~~~

**Important in Spring Boot 3.5:** `ExitCodeEvent` is published **only if the determined code is non-zero**. When every `ExitCodeGenerator` returns 0, `SpringApplication.exit(...)` still closes the context and returns 0, yet **there is no `ExitCodeEvent(0)`** on the standard path. Therefore, never use `ExitCodeEvent` count as a counter of every application exit.

**Event ordering relative to close:** On a non-zero `SpringApplication.exit(context)` path, the exit event fires **before** Boot calls close on the context. Context listeners still have a chance to log the code. Only afterward come `ContextClosedEvent` and stop/destroy steps. Do not run complex cleanup directly inside an exit listener; lifecycle shutdown already has dedicated hooks.

### 3.1. SpringApplication.exit is not yet System.exit

Code snippet:

~~~java
int exitCode = SpringApplication.exit(context);
System.out.println("exit code = " + exitCode);
~~~

**does not yet return this code to the parent process**. `SpringApplication.exit` closes the context and returns an integer. If `main` merely returns normally, the JVM usually exits with **0** absent other errors/anomalies, even though you just printed `exit code = 7`. A `System.exit(exitCode)` call (or an equivalent entrypoint exit mechanism) passes the desired status to the OS.

In continuously serving web applications, do not call `SpringApplication.exit(...)`/`System.exit(...)` at the end of `main` right after `run`, as it closes the newly started server. This pattern is specifically suited for **CLIs/batch jobs with a clear endpoint**.

### 3.2. ExitCodeEvent is not a "listener to mutate the exit code"

`getExitCode()` only reads the event's value; there is no setter to alter the outcome. If you want to change the exit code, adjust `ExitCodeGenerator`, `ExitCodeExceptionMapper`, or the generators passed into `SpringApplication.exit(...)` **before the event fires**. The event is purely an observation layer.

Avoid manually publishing `new ExitCodeEvent(this, 9)` and claiming the process exited 9: that is only an event published by yourself; it **does not** cause Boot to execute exit lifecycle or `System.exit`. To test framework behavior, go through the real `SpringApplication.exit` API.

## 4. Exit code 0, non-zero, and observation limits

Typical conventions for a CLI/batch process:

| Code | Application convention interpretation | Event under `SpringApplication.exit` |
|---:|---|---|
| `0` | Completed successfully | Does **not** publish `ExitCodeEvent` |
| `7` | Business error/condition intentionally chosen by the lab | Publishes `ExitCodeEvent` with code 7 |
| `19` | Mapped startup failure in the lab | May publish event if Boot resolves code 19 and context can publish |
| `1` | Non-zero code often used for general error | Publishes event if coming from a valid generator on exit path |
| `130` / `143` | Typical shell conventions for interrupt/TERM signals in Unix environments | **Do not infer** `ExitCodeEvent` from those numbers |
| `137` | Commonly indicates process killed/SIGKILL in Unix containers | **Must not** be taken as proof that exit listeners ran |

Codes **7 and 19 are conventions specific to this lab**, not a code table defined by Spring Boot. When designing production systems, define codes per contracts with schedulers/CI/CD and avoid colliding with codes reserved by environments for signals. On many Unix shells, effective exit status is only 8 bits wide; returning negative values or numbers over 255 can be mapped/truncated, so this lab uses small positive numbers under 128.

**No event** does not necessarily mean shutdown failed: for success code 0, **emitting no event is the normal behavior**.

## 5. Runnable practice project: Java 17 + Spring Boot 3.5

### 5.1. Create the project

Create a Maven project with Java 17, Spring Boot 3.5.x, group `com.example`, artifact `exit-code-event-lab`, package `com.example.exitcodelab`. This is a command-line app—**no Spring Web or Actuator needed**; the `spring-boot-starter` dependency suffices.

If using Spring Initializr, keep the Maven Wrapper `mvnw`, `mvnw.cmd` and create/update `pom.xml` with the equivalent dependencies below. You may use an installed Maven instead of the Maven Wrapper.

Structure:

~~~text
exit-code-event-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/exitcodelab/
    ExitCodeEventLabApplication.java
    ExitEventObserver.java
    DemoStartupException.java
  src/main/resources/application.properties
~~~

### 5.2. Minimal pom.xml

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>exit-code-event-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>exit-code-event-lab</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot 3.5.16 is just **one concrete 3.5.x release** so the example pins dependencies consistently with docs; if your organization's Maven repo uses another 3.5.x release, keep your approved version and verify corresponding behavior. Java 17 is sufficient for all APIs in the example. Do not add the web starter just to observe exit codes.

### 5.3. Main: boot, compute code, close context, return code to OS

File `src/main/java/com/example/exitcodelab/ExitCodeEventLabApplication.java`:

~~~java
package com.example.exitcodelab;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ExitCodeEventLabApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(
                        ExitCodeEventLabApplication.class, args);

        int code = SpringApplication.exit(context);
        System.out.println("LAB_EXIT_RETURNED=" + code);

        // This is the single place that passes the Spring exit code to the OS.
        System.exit(code);
    }

    @Bean
    ExitCodeGenerator configuredExitCode(Environment env) {
        int configured = env.getProperty(
                "lab.exit-code", Integer.class, 0);

        return () -> configured;
    }

    @Bean
    CommandLineRunner demoRunner(Environment env) {
        return args -> {
            System.out.println("LAB_RUNNER_BEGIN");

            boolean fail = env.getProperty(
                    "lab.fail-startup", Boolean.class, false);

            if (fail) {
                throw new DemoStartupException(
                        "intentional startup failure");
            }

            System.out.println("LAB_RUNNER_DONE");
        };
    }
}
~~~

**Notes:**

1. `SpringApplication.run(...)` builds the context, creates listener/generator beans, and runs `CommandLineRunner`. On the success flow, it returns the context to `main`.
2. `configuredExitCode` is an `ExitCodeGenerator` bean returning the value of `lab.exit-code`. Default is 0, overridable via `--lab.exit-code=7`.
3. `SpringApplication.exit(context)` evaluates the generator bean, publishes `ExitCodeEvent` **only when code is non-zero**, closes the context, and returns the code.
4. `LAB_EXIT_RETURNED` confirms the Java helper result **after closing the context**.
5. `System.exit(code)` forwards that outcome to the shell. Never place `System.exit` inside controllers, bean callbacks, listeners, or unit tests.
6. If `lab.fail-startup=true`, the runner throws `DemoStartupException` and `SpringApplication.run(...)` does not return a successful context; `LAB_EXIT_RETURNED` in `main` **does not run**. Boot has a separate startup-failure path observed in section 8.

**Note:** `System.exit(0)` still instructs the JVM to terminate; `System.exit(7)` exposes non-zero to the OS unless a wrapper alters the status. Loggers or framework shutdown hooks may print unrelated lines between markers.

### 5.4. Listener: receiving ExitCodeEvent and ContextClosedEvent

File `src/main/java/com/example/exitcodelab/ExitEventObserver.java`:

~~~java
package com.example.exitcodelab;

import org.springframework.boot.ExitCodeEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationContext;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ExitEventObserver {

    @EventListener
    public void onExitCode(ExitCodeEvent event) {
        System.out.println(
                "LAB_EXIT_EVENT=" + event.getExitCode());
        System.out.println(
                "LAB_EXIT_SOURCE_IS_CONTEXT="
                + (event.getSource() instanceof ApplicationContext));
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("LAB_APPLICATION_READY");
    }

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        System.out.println("LAB_CONTEXT_CLOSED");
    }
}
~~~

When Spring manages this bean, `@EventListener` creates corresponding method-based event listeners. Method `onExitCode(ExitCodeEvent event)` reads the code via `getExitCode()`. `ApplicationReadyEvent` is printed to separate successful startup from exit; `ContextClosedEvent` proves the context has started closing.

On the intentional exit path, verify this order:

~~~text
LAB_APPLICATION_READY
LAB_EXIT_EVENT=7
LAB_EXIT_SOURCE_IS_CONTEXT=true
LAB_CONTEXT_CLOSED
LAB_EXIT_RETURNED=7
~~~

`ApplicationReadyEvent` appears before `SpringApplication.exit(...)` because `run(...)` finished. When the code is non-zero, the exit event arrives before the close event. Extra framework logs may interleave, yet the relative order of lab markers is the primary evidence.

Do not rely on async log flush timing in production to establish semantics; the lab uses `System.out.println` for direct observation. Production should use loggers/structured telemetry with timestamps and correlation IDs.

### 5.5. Exception carrying its own exit code

File `src/main/java/com/example/exitcodelab/DemoStartupException.java`:

~~~java
package com.example.exitcodelab;

import org.springframework.boot.ExitCodeGenerator;

public final class DemoStartupException
        extends RuntimeException implements ExitCodeGenerator {

    public DemoStartupException(String message) {
        super(message);
    }

    @Override
    public int getExitCode() {
        return 19;
    }
}
~~~

When the runner throws this exception, the startup failure carries an `ExitCodeGenerator`. Spring Boot searches for codes from exceptions (including the cause chain on appropriate paths), and can publish `ExitCodeEvent` carrying code **19** before closing the context if the context already exists and the event publisher is available. Because the error happens inside `CommandLineRunner` **after refresh**, the observer bean has already been created in the sample project.

This is the **startup failure** path; `SpringApplication.exit(context)` at the end of `main` is not reached because `run()` failed. Never write `catch (Exception ex) { System.exit(0); }`—that hides failures and misleads CI/CD into treating the job as successful.

### 5.6. application.properties

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=exit-code-event-lab
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR

lab.exit-code=0
lab.fail-startup=false
~~~

The application opens no web server. `logging.level.root=ERROR` reduces noise so markers are easy to spot, though on startup failure you may still see stack traces/error logs printed by Boot and the JVM. Spring Boot exiting with the right code does **not** depend on logger settings.

## 6. Experiment A — Exit code 0, no ExitCodeEvent

### 6.1. Build JAR

Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw clean package
~~~

Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd clean package
~~~

If not using the Maven Wrapper, `mvn clean package` is also valid with compatible Maven installed. The JAR path from the `pom.xml` above is `target/exit-code-event-lab-0.0.1-SNAPSHOT.jar`.

### 6.2. Run and read status in a Unix shell

~~~bash
java -jar target/exit-code-event-lab-0.0.1-SNAPSHOT.jar
echo $?
~~~

Expected **key markers** (aside from any other logs):

~~~text
LAB_RUNNER_BEGIN
LAB_RUNNER_DONE
LAB_APPLICATION_READY
LAB_CONTEXT_CLOSED
LAB_EXIT_RETURNED=0
~~~

Running `echo $?` **immediately after the java command** prints:

~~~text
0
~~~

**Point to confirm:** **no `LAB_EXIT_EVENT=0` line appears** because Spring Boot 3.5 does not publish `ExitCodeEvent` when the determined code is 0. Do not treat the absent event as a bug or misregistered listener in Experiment A.

### 6.3. Run and read status in PowerShell

~~~powershell
java -jar target/exit-code-event-lab-0.0.1-SNAPSHOT.jar
$LASTEXITCODE
~~~

PowerShell displays `0` when the run succeeds and the Java process returns 0. `$LASTEXITCODE` is the status of the most recent native process; running another native command before reading it overwrites it. Do not compare PowerShell's `$?` directly against numeric code 7: `$?` reflects command success/failure per shell semantics, whereas `$LASTEXITCODE` holds the specific numeric code.

## 7. Experiment B — Exit code 7, with ExitCodeEvent

### 7.1. Linux/macOS

~~~bash
java -jar target/exit-code-event-lab-0.0.1-SNAPSHOT.jar --lab.exit-code=7
echo $?
~~~

Expected key markers:

~~~text
LAB_RUNNER_BEGIN
LAB_RUNNER_DONE
LAB_APPLICATION_READY
LAB_EXIT_EVENT=7
LAB_EXIT_SOURCE_IS_CONTEXT=true
LAB_CONTEXT_CLOSED
LAB_EXIT_RETURNED=7
~~~

Running `echo $?` **immediately after java**:

~~~text
7
~~~

This experiment verifies **three layers**:

1. The generator returned **7** to `SpringApplication.exit`.
2. The listener observed **`ExitCodeEvent.getExitCode()==7`** before context close.
3. `System.exit(7)` made the shell receive **7**.

Do not assert OS code solely from the event marker. If the program omits `System.exit(code)`, you may still see the event and `LAB_EXIT_RETURNED=7` while the shell receives 0 when `main` returns normally.

### 7.2. Windows PowerShell

~~~powershell
java -jar target/exit-code-event-lab-0.0.1-SNAPSHOT.jar --lab.exit-code=7
$LASTEXITCODE
~~~

Expected numeric result: `7`. Use `java -jar` rather than checking only `./mvnw spring-boot:run`, because the Maven plugin and wrapper have their own process/failure-status handling that can make verifying raw OS codes less direct.

### 7.3. Change the code to 42

~~~bash
java -jar target/exit-code-event-lab-0.0.1-SNAPSHOT.jar --lab.exit-code=42
echo $?
~~~

Markers `LAB_EXIT_EVENT=42`, `LAB_EXIT_RETURNED=42`, and shell status `42` are expected if no other generator intervenes. This lesson assigns no special system meaning to 42.

## 8. Experiment C — Startup failure carrying ExitCodeGenerator

Run in a new process:

~~~bash
java -jar target/exit-code-event-lab-0.0.1-SNAPSHOT.jar --lab.fail-startup=true
echo $?
~~~

Expected markers:

~~~text
LAB_RUNNER_BEGIN
LAB_EXIT_EVENT=19
LAB_EXIT_SOURCE_IS_CONTEXT=true
LAB_CONTEXT_CLOSED
~~~

Additionally, there will be stack traces or error logs containing `DemoStartupException` / `intentional startup failure`. There will **not** be `LAB_RUNNER_DONE`, `LAB_APPLICATION_READY`, or `LAB_EXIT_RETURNED` for that failed startup run.

In Spring Boot 3.5's direct `java -jar` launch model, a non-zero exit code recorded by a mapper/exception generator is typically passed by Spring Boot to its exception handler; the expected OS status per `getExitCode()` is **19**, though you must verify via `echo $?`/`$LASTEXITCODE` on your actual JDK, launcher, and environment. If a wrapper catches the exception, changes the exit code, or runs it as a child process, the externally reported status may differ.

**Why can `ExitCodeEvent` still appear when the app fails?** Because the exception occurred **after the context refreshed** inside the runner, so Boot still had an opportunity to publish an event with a non-zero exit code and the observer bean already existed. If failure occurred earlier—classpath errors, uncreated context, bean initialization failures before event-method registration—you **cannot promise** the same listener bean will see the event.

### 8.1. ApplicationFailedEvent and ExitCodeEvent are different

| Event | Triggered when | Has `int` exit code? |
|---|---|---|
| `ApplicationFailedEvent` | `SpringApplication` fails to start | Does not provide `getExitCode()` like `ExitCodeEvent` |
| `ExitCodeEvent` | Boot resolves a non-zero exit code and can publish | Has `getExitCode()` |
| `ApplicationReadyEvent` | Startup succeeds and runners finish | Carries no exit code |
| `ContextClosedEvent` | Context enters close lifecycle | Carries no exit code |

A startup failure can produce both `ExitCodeEvent` and `ApplicationFailedEvent`, yet **not every failure** produces both. To inspect the root cause, use `ApplicationFailedEvent.getException()` or exception logs; to observe the computed code, use `ExitCodeEvent.getExitCode()`. Never force one listener to play the role of the other.

## 9. Registering a listener with ApplicationListener instead of @EventListener

In the sample project, `@EventListener` works because Spring created the observer bean. If you need a standalone listener, implement the interface:

~~~java
package com.example.exitcodelab;

import org.springframework.boot.ExitCodeEvent;
import org.springframework.context.ApplicationListener;

public final class EarlyExitCodeLogger
        implements ApplicationListener<ExitCodeEvent> {

    @Override
    public void onApplicationEvent(ExitCodeEvent event) {
        System.out.println(
                "LAB_EARLY_EXIT_CODE=" + event.getExitCode());
    }
}
~~~

This is a **complete additional Java file** if you want to experiment with early registration. To register before calling `run`, replace the startup portion of `main` (extended lab variant):

~~~java
SpringApplication app =
        new SpringApplication(ExitCodeEventLabApplication.class);
app.addListeners(new EarlyExitCodeLogger());

ConfigurableApplicationContext context = app.run(args);
int code = SpringApplication.exit(context);
System.exit(code);
~~~

This is a **snippet replacing the body of `main`**, not creating a second `main` method. With it, the early listener can receive events even if a context-scoped listener bean was not yet registered, **provided Boot has a publisher and actually publishes the event**. If an exception occurs before an application context even exists or Boot creates no event, an early-registered listener cannot observe an event that does not exist.

**Duplicate registration warning:** If you annotate `EarlyExitCodeLogger` with `@Component` and also instantiate `new` + `app.addListeners(...)`, you can create two listener instances for the same event. Since this lesson only observes the exit code, choose one registration path; if using both, label logs clearly so you do not mistake one event for two emissions.

### 9.1. @EventListener vs API vs factories

| Approach | Example | Suitable when |
|---|---|---|
| Bean method listener | `@EventListener void onExit(ExitCodeEvent e)` | Context already refreshed, logic needs DI |
| Interface listener bean | `@Component implements ApplicationListener<ExitCodeEvent>` | Bean exists inside context |
| `SpringApplication` API | `app.addListeners(new EarlyExitCodeLogger())` | Pre-startup registration, minimal bean dependencies |
| `META-INF/spring.factories` | Key `org.springframework.context.ApplicationListener` | Libraries wanting auto-registered listeners |
| Context hierarchy | Parent/child contexts | Must filter source/context if events propagate to parent |

`ExitCodeEvent` is not part of the usual startup `SpringApplicationEvent` sequence; it is an event tied to **exit code computation**. It can be dispatched through Spring's application event publishing mechanism, though that does not mean every context or every shutdown publishes it.

### 9.2. Do not perform heavy I/O in an ExitCodeEvent listener

Event listeners run synchronously with the publisher by default. If a listener calls a slow external API or throws an exception, shutdown duration and even exit handling can be impacted. Use listeners for **lightweight logs/metrics, recording the computed status**, and correlation; transaction flushing/acks belong in appropriate lifecycle/resource owners without unbounded delays.

If your logging/metrics backend is async, calling `System.exit` immediately afterward can cut off unflushed buffers. Never guarantee 100% of logs reach remote storage merely because code called `println` or a logger. Design bounded flushes, supervisor log capture, and independent external outcome checks.

## 10. Multiple ExitCodeGenerators: ordering and first non-zero code

Spring Boot 3.5 uses `ExitCodeGenerator` instances passed directly to `SpringApplication.exit(context, generators...)` **and** beans implementing that interface in the context. They are sorted by `Ordered` or `@Order`. The **first non-zero code in priority order** is selected.

Therefore:

- **Smaller** `getOrder()` means **higher** priority.
- A generator returning **0** means "no error code imposed"; the framework can continue checking other generators.
- Do not assume it selects the largest number, most negative number, or "last created generator."
- For generators with equal priority, do not build a business contract on undefined tie-breaking order.

### 10.1. Example of two generators with deterministic priority

This is an **alternative configuration sample**—do not paste it into the sample project while `configuredExitCode` remains if you want to predict output cleanly without checking extra priorities:

~~~java
package com.example.exitcodelab;

import org.springframework.boot.ExitCodeGenerator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration(proxyBeanMethods = false)
public class OrderedExitCodes {

    @Bean
    ExitCodeGenerator firstGenerator() {
        return new FixedCode(0, -100);
    }

    @Bean
    ExitCodeGenerator secondGenerator() {
        return new FixedCode(12, 100);
    }

    private record FixedCode(int code, int order)
            implements ExitCodeGenerator, Ordered {

        @Override
        public int getExitCode() {
            return code;
        }

        @Override
        public int getOrder() {
            return order;
        }
    }
}
~~~

This class compiles with Java 17 and Spring Boot dependencies when placed in the right package. When **only these two generators** are configured, the order `-100` generator returns 0 so Boot evaluates the order `100` generator returning **12**. Both the exit code and event are 12. If you change `firstGenerator()` to return 5, it wins and the result is 5. That proves **ordering + first non-zero**, not comparing code magnitudes.

In a production setup, rather than having multiple generators compete over the same business result, establish one owner that aggregates the outcome, precedence policy, and corresponding unit tests.

### 10.2. Generator passed directly to SpringApplication.exit

Spring Boot lets you pass extra generators:

~~~java
int code = SpringApplication.exit(context, () -> 9);
System.exit(code);
~~~

This snippet replaces the last two lines in `main` (after `run`). If the lab's generator bean returns **0**, the directly passed generator returning 9 yields result **9**, event 9, and OS status 9. If other non-zero generators exist, the result depends on ordering and first-non-zero logic; **never** assert that explicit arguments always beat beans in every configuration.

### 10.3. Non-zero code when a listener callback throws

`SpringApplication.exit` tries to return a code even if some closing steps throw exceptions; the Javadoc states it does not propagate errors under its normal contract, though it may print stack traces and fall back depending on circumstances. Do not treat listeners as a safe place to perform actions that throw arbitrarily. In production code, decouple computing the exit code from potentially failing reporting steps, and check the actual return value of `SpringApplication.exit`.

## 11. ExitCodeExceptionMapper: mapping startup failures

`org.springframework.boot.ExitCodeExceptionMapper` is a functional interface:

~~~java
int getExitCode(Throwable exception);
~~~

It maps an exception to an exit code, typically when `SpringApplication.run(...)` fails. For example, add this bean to your app configuration to map `IllegalArgumentException` to 64:

~~~java
@Bean
ExitCodeExceptionMapper argumentFailureMapper() {
    return failure -> {
        for (Throwable current = failure;
                current != null;
                current = current.getCause()) {
            if (current instanceof IllegalArgumentException) {
                return 64;
            }
        }
        return 0;
    };
}
~~~

This is a **method snippet**, requiring `import org.springframework.boot.ExitCodeExceptionMapper`, inside a Spring configuration class. `getExitCode(...)` returns 0 when the error is unrecognized, deferring to other rules. Looping through `getCause()` helps because Spring may wrap root exceptions in another layer.

**Differences:**

| Tool | How code is supplied | Common timing |
|---|---|---|
| `ExitCodeGenerator` bean | Parameterless `getExitCode()` | Intentional exit path via `SpringApplication.exit(...)` |
| Exception `implements ExitCodeGenerator` | Exception carries `getExitCode()` itself | Startup failure / exception cause chain |
| `ExitCodeExceptionMapper` bean | `getExitCode(Throwable exception)` | Mapping failure cause when Boot handles errors |
| `ExitCodeEvent` | `getExitCode()` to **read** the determined code | Observing non-zero codes published by Boot |

In startup-failure handling, if mapper beans exist and yield a non-zero code, Boot can use the mapper's code. Otherwise, the framework can look for `ExitCodeGenerator` on the exception/cause chain. However, **if the context is not active or mapper beans do not exist yet**, bean-based mapping may be unavailable; exceptions directly implementing `ExitCodeGenerator` can still be inspected when appropriate.

Never use `ExitCodeExceptionMapper` to "catch and swallow" exceptions. It chooses a failure status; root causes still need independent logging/analysis. If a startup failure prevents `main` from returning from `run(...)`, do not expect `SpringApplication.exit(context)` afterward to run.

## 12. An observed event does not cover every process termination

### 12.1. Cases that do not publish an event along the standard path

| Action | Guaranteed to emit ExitCodeEvent? | Reason |
|---|---|---|
| `SpringApplication.exit(context)`, code 0 | **No** | Branch does not publish when `exitCode == 0` |
| `SpringApplication.exit(context)`, code 7 | **Yes on normal flow**, if publisher works | Non-zero branch publishes event before close |
| Direct `context.close()` | **No** | Close only closes the context; computes no exit code |
| Direct `System.exit(7)` without `SpringApplication.exit` | **No** | JVM exit does not mean Boot publishes an exit event |
| `Runtime.getRuntime().halt(7)` | **Not guaranteed** | Skips normal hooks/cleanup |
| JVM receives `SIGKILL` | **No** reliable Java listener mechanism | Process forcibly terminated |
| Startup fails before context has event publisher | **Not guaranteed** | Context/listeners may not exist yet |
| Startup fails in runner, non-zero generator exception | **Observable** in the lab | Context refreshed and Boot processes exit code |
| Graceful `SIGTERM` with shutdown hook | **Not automatically equivalent to `SpringApplication.exit`** | Context closes; does not necessarily evaluate generators |
| Kubernetes/Docker container killed due to timeout/OOM | **Do not infer an event fired** | OS/runtime supplies its own exit code |

### 12.2. Why doesn't ExitCodeEvent appear when a process is killed?

Application events are an **in-JVM** mechanism. If a process is forcibly killed, the kernel or container runtime assigns an exit status from the signal, leaving no time for Spring to publish events. Consequently, you cannot use this listener as the sole source for counting every crash or restart.

A complete observability setup should collect:

- `ExitCodeEvent` logs when the application determines a non-zero code itself.
- `ApplicationFailedEvent` and root causes when startup fails.
- `ContextClosedEvent` / shutdown logs for normal lifecycles.
- Exit codes and termination reasons from the **process supervisor, Docker/Kubernetes, CI/CD, or systemd**.
- OOM/restart/health probe and node/system events from infrastructure.
- Business job state and transaction outcomes from durable storage.

### 12.3. ExitCodeEvent does not replace ContextClosedEvent

`ExitCodeEvent` focuses on **determining a non-zero code**; `ContextClosedEvent` focuses on the **context close lifecycle**. In the `code=7` demo, both appear; in the `code=0` demo, only close appears. In a `SIGTERM` shutdown, close may appear without an exit event. That is valid behavior, not missing logs.

## 13. Operating CLIs, Docker, Kubernetes Jobs, and CI/CD

### 13.1. CLI or scheduled batch jobs

For command-line jobs that run to completion and exit, combine `ExitCodeGenerator` with `SpringApplication.exit` and `System.exit` so the parent process receives a meaningful status. Conventions:

- 0: completed.
- 7: business outcome requiring different upstream handling.
- 19: unable to start / initial preconditions failed.

These are **lab-specific conventions**; production environments need explicit contracts for schedulers, shell scripts, and monitoring. If part of a job succeeds and part fails, define an aggregation policy rather than grabbing an arbitrary number from a listener.

### 13.2. Bash/script pipelines

A script checking results can run:

~~~bash
java -jar target/exit-code-event-lab-0.0.1-SNAPSHOT.jar --lab.exit-code=7
status=$?
printf 'Observed Java process status: %s\n' "$status"

if [ "$status" -ne 0 ]; then
  echo "Job did not succeed"
  exit "$status"
fi
~~~

The script must read `$?` **immediately after Java**, not after `echo` or another command. When piping via `java ... | tee log.txt`, some shells return `tee`'s status unless `pipefail` or `PIPESTATUS` is used properly; never use a logging pipeline to assert raw Java exit status without handling that case.

### 13.3. Windows PowerShell

~~~powershell
java -jar target/exit-code-event-lab-0.0.1-SNAPSHOT.jar --lab.exit-code=7
$code = $LASTEXITCODE
Write-Host "Observed Java process status: $code"

if ($code -ne 0) {
    exit $code
}
~~~

PowerShell has distinct semantics for native processes and `ErrorAction`/terminating errors, so reading `$LASTEXITCODE` is the transparent way to capture Java's `System.exit` code. Do not confuse the exit codes of Maven Wrapper, IDEs, and raw JARs if an intermediate launcher alters them.

### 13.4. Docker / Kubernetes

When Java is the container's main process, Java's exit code is normally recorded by the container runtime. The Kubernetes Job controller uses exit status/restart policy to determine container termination and retry policy. **Spring Boot's `ExitCodeEvent` is not read directly by infrastructure**; infrastructure sees only the process exit status recorded by the runtime.

Therefore, if code only calls `SpringApplication.exit(context)` and ignores the returned `int`, Kubernetes may observe status 0 and consider the job succeeded even though internal logs recorded exit code 7. That is why `System.exit(code)` is especially critical for batch containers.

In Kubernetes, inspect container termination reason/code from Pod status—for instance `status.containerStatuses[].state.terminated.exitCode` or `lastState.terminated.exitCode` depending on whether the container stayed terminated or restarted. Do not conclude from code 137/143 that Boot published an `ExitCodeEvent`; those codes can come from signals/container runtimes rather than generators.

### 13.5. Long-running web applications

For 24/7 REST APIs, do not put this at the end of `main`:

~~~java
System.exit(SpringApplication.exit(
        SpringApplication.run(WebApplication.class, args)));
~~~

This is an **anti-pattern snippet**; `WebApplication` is just an illustrative name outside the CLI lab. It closes the context as soon as `run` returns, leaving the web service unable to serve traffic as intended. For long-lived servers, use shutdown lifecycle, readiness, Actuator, and supervisors. Only call `SpringApplication.exit`/`System.exit` when business logic or an operator explicitly requests process termination, with proper authorization, draining, and resource cleanup.

## 14. Testing properly without killing the test process

### 14.1. End-to-end tests via a separate process

To test OS exit status, use an **independent Java process** from a shell or integration test harness. This is the cleanest test for `System.exit` without hooking or mocking `SecurityManager` (which has changed heavily across Java versions).

Matrix:

| JAR invocation | Event marker | Context close | Helper returned | Process status |
|---|---|---|---|---:|
| Default | No `LAB_EXIT_EVENT` | Yes | 0 | 0 |
| `--lab.exit-code=7` | `LAB_EXIT_EVENT=7` | Yes | 7 | 7 |
| `--lab.exit-code=42` | `LAB_EXIT_EVENT=42` | Yes | 42 | 42 |
| `--lab.fail-startup=true` | `LAB_EXIT_EVENT=19` when observer receives it | Yes in lab after refresh | None | Typically 19; measure in practice |

OS status assertions apply when running `java -jar` directly in a standard environment with no intermediate launcher altering status. If startup fails in an early phase, tests must adjust event/close expectations to that failure phase.

### 14.2. Unit/integration tests in the same JVM

If a test class must verify events yet **must not kill the JUnit runner**, never call `System.exit`. Create an `ApplicationContext` yourself, register a recording listener, call `SpringApplication.exit(context)`, and assert both the returned code and captured events. **Caution:** `SpringApplication.exit` **closes the context**; never call it on a `@SpringBootTest` context cached by the test suite for reuse.

One technique is building an isolated context via `SpringApplicationBuilder` with `WebApplicationType.NONE` so the test owns its lifecycle. When shell status must be verified, launch a Java subprocess and read its exit value. Never "test" by manually publishing a synthetic `ExitCodeEvent`: that fails to prove Boot has a non-zero code path or helper close.

### 14.3. Scoped assertions

- Correct event code confirms only the **value published by Boot**.
- Correct `SpringApplication.exit` return value confirms the **helper computed the code**.
- Correct `System.exit` status confirms the **launcher returned the code to the OS**.
- `ContextClosedEvent` confirms **close has begun**.
- Business job outcomes require inspecting real data; you cannot infer them from exit codes if generators are misconfigured.

Do not substitute one of these five assertions for all of them.

## 15. Common errors and how to diagnose them

| Symptom | Possible cause | Diagnostic step |
|---|---|---|
| No exit event for code 0 | Boot does not publish events for 0 | Change `lab.exit-code=7` and observe |
| `LAB_EXIT_RETURNED=7` yet shell sees 0 | Omitted `System.exit(code)` or wrapper altered status | Inspect `main`, run raw `java -jar` |
| `ExitCodeEvent` import not found | Wrong package imported | Use `org.springframework.boot.ExitCodeEvent` |
| Listener misses event in early startup failure | Listener bean not created/registered yet | Register early via `addListeners` if appropriate; check if event really fired |
| Only `ContextClosedEvent` appears | Direct context close or exit code 0 | Check where `SpringApplication.exit` is called |
| Event appears yet process does not exit | Missing `System.exit`, remaining non-daemon threads, or web server | Inspect entrypoint, thread dump, shutdown hooks |
| Direct `System.exit(7)` produces no event | Bypassed `SpringApplication.exit` | Call helper before terminating if code/event is needed |
| Only `ApplicationFailedEvent` appears | No non-zero mapping or context could not publish | Check generators/exception mappers/failure phase |
| Exit code differs from expectation | Competing generators, wrong order | Log generator outputs, `Ordered`/`@Order` |
| Generator always returns 0 | Property unbound or wrong rule | Print `lab.exit-code` and test with 7 |
| Error sits in cause yet mapper returns 0 | Matcher checks only top exception | Walk cause chain, distinguish permanent/transient |
| Exit listener slows shutdown | Blocking I/O or synchronous logging | Move long I/O to cleanup owner with deadline |
| `ContextClosedEvent` arrives before exit event in logs | Different close path, async listener, or multiple contexts | Log source, context ID, thread, and code path |
| Event appears multiple times | Multiple contexts, repeated publish, duplicate listener registration | Check event source and listener identity |
| CI sees success while business job failed | `ExitCodeGenerator` does not reflect real outcome | Derive code rules from persisted outcome |
| Maven task reports different status than raw JAR | Build tool/wrapper reports its own code | Use `java -jar` to inspect OS status |
| Docker status 137 with no exit event | OS/runtime kill without graceful Java callbacks | Check `OOMKilled`/signals, Pod events |
| JUnit process dies during tests | Called `System.exit` inside test runner | Isolate in subprocess or omit `System.exit` |
| Startup exception without `LAB_EXIT_RETURNED` | `SpringApplication.run` threw before returning context | Inspect failure logs and exception generators |
| Context keeps running after `main` returns | Active web server or non-daemon thread | Distinguish Spring exit helper vs process lifetime |

## 16. Practice exercises

### Exercise A — Difference between 0 and non-zero

Run the project with `lab.exit-code=0` and `7`. Count `LAB_EXIT_EVENT`, `LAB_CONTEXT_CLOSED`, `LAB_EXIT_RETURNED`, and raw shell status. Explain why event count cannot serve as a total count of application exits.

### Exercise B — Remove System.exit in a copy

In a copy of the lab, temporarily replace `System.exit(code)` with a log print and let `main` return normally. Run `--lab.exit-code=7`; verify the event/returned value is still 7 yet the OS may receive 0 once all threads stop. Restore the code immediately after experimenting. This proves **the helper return value is not forwarded to the OS automatically**.

### Exercise C — Exception carrying code 19

Run `--lab.fail-startup=true`. Locate the root cause, `ExitCodeEvent`, `ContextClosedEvent`, and process status. Explain why `LAB_EXIT_RETURNED` does not appear when `run()` throws an exception. Describe a pre-refresh failure case where the observer bean does not exist.

### Exercise D — Two generators with different orders

Use the separate `OrderedExitCodes` configuration, removing the default generator so the experiment stays isolated. Run with first code 0, second code 12; then change first code to 5. Check the event and OS code (12, then 5). Explain why "larger number wins" is false.

### Exercise E — Mapper for argument validation errors

Add an `ExitCodeExceptionMapper` checking for `IllegalArgumentException` in the cause chain and returning 64. Design a test runner throwing this error on invalid input. Check root-cause logs and status, then test an unmatched error to observe fallback. Never use mappers to hide errors or turn all errors into 0.

### Exercise F — Killed process/container

Run a test server or controlled waiting job, then compare normal shutdown vs hard kill in an isolated lab environment. Compare `ContextClosedEvent`, `ExitCodeEvent`, and process status markers. Never run hard kills against real data environments; rely on supervisor metrics to count cases where Spring could not publish events in time.

### Exercise G — Subprocess verification

Write a script running three raw `java -jar` commands. Each checks shell status, event marker, and close marker, saving stdout/stderr separately. Pass criteria: 0 emits no exit event, 7 emits event 7, startup failure shows root cause and policy-mapped non-zero code.

## 17. Acceptance checklist

- [ ] State the exact package `org.springframework.boot.ExitCodeEvent`.
- [ ] Know what value `ExitCodeEvent.getExitCode()` returns.
- [ ] Explain why `SpringApplication.exit` and `System.exit` are two separate steps.
- [ ] Run the Java 17 + Spring Boot 3.5 Maven CLI project successfully.
- [ ] For code 0: no `ExitCodeEvent`, yet `ContextClosedEvent` occurs.
- [ ] For code 7: exit event appears before `ContextClosedEvent`.
- [ ] Correlate helper result 7 with shell status 7.
- [ ] For startup exception code 19: distinguish the failure path from the successful exit path.
- [ ] Understand `ExitCodeExceptionMapper` and exceptions implementing `ExitCodeGenerator`.
- [ ] Know multiple generators use `Ordered`/`@Order` and first non-zero.
- [ ] Do not confuse absence of `ExitCodeEvent` with the process failing to close.
- [ ] Never call `System.exit` inside an event listener.
- [ ] Never call `System.exit` directly inside HTTP controllers or unit tests.
- [ ] Distinguish `ApplicationFailedEvent`, `ApplicationReadyEvent`, and `ContextClosedEvent`.
- [ ] Know `SIGKILL`/OOM/crashes do not guarantee Spring events or cleanup.
- [ ] Read exit status from Unix `$?` or PowerShell `$LASTEXITCODE`.
- [ ] Maintain business exit-code conventions and logs/metrics aligned with the process supervisor.
- [ ] Keep experiments in CLI/subprocesses without breaking test runners or production web servers.

## 18. Official documentation

1. **Spring Boot 3.5 — SpringApplication / Application Exit**: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html — using `ExitCodeGenerator`, `SpringApplication.exit`, and `System.exit`; handling multiple generators.
2. **Spring Boot 3.5 API — ExitCodeEvent**: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ExitCodeEvent.html — package, constructor, and `getExitCode()`.
3. **Spring Boot 3.5 API — ExitCodeGenerator**: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ExitCodeGenerator.html — functional interface and `getExitCode()` contract.
4. **Spring Boot 3.5 API — ExitCodeExceptionMapper**: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ExitCodeExceptionMapper.html — mapping `Throwable` to exit codes.
5. **Spring Boot 3.5 API — SpringApplication.exit(...)**: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html — closing context, generator selection, and returning code.
6. **Java SE 17 — System.exit(int)**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#exit(int) — terminating the JVM with a status code.
7. **Spring Framework 6.2 — Application Events**: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html — `ApplicationListener` and `@EventListener` mechanics.

**Summary:** `ExitCodeEvent` is an observation signal for a **non-zero exit code determined by Spring Boot**, typically published before context closure along the `SpringApplication.exit(context)` path. A listener seeing the event does not terminate the process itself; you must pass the result via `System.exit(code)` if shells/CI/Kubernetes should receive that code. For startup failures, use `ExitCodeGenerator` on exceptions or `ExitCodeExceptionMapper` and verify that the publisher phase is active. When a process is OS-killed, crashes, or closes the context directly, **never assume `ExitCodeEvent` always fires**—combine events, failure logs, context closure, and infrastructure exit statuses to draw accurate conclusions.