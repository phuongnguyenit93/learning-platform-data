# ApplicationFailedEvent and the Case Where ApplicationContext Does Not Exist Yet

In Spring Boot, a startup failure does not necessarily happen after the application has created an `ApplicationContext`. Errors can occur while preparing `Environment`, loading config data, or executing a bootstrap listener; at that point **no context exists yet to access beans**. Another failure might occur later while instantiating beans, refreshing the context, opening the HTTP port, or running `ApplicationRunner`. Both fall under **startup failure**, yet context usability differs.

`ApplicationFailedEvent` (`org.springframework.boot.context.event` package) is the event Spring Boot emits when a `SpringApplication` run fails. Two critical points:

- `event.getException()` returns the cause of failure as a `Throwable`.
- `event.getApplicationContext()` can return **`null`**, because Spring Boot can emit the failure event before creating a context. **Even when non-null, the context may not have refreshed successfully or may already be undergoing cleanup**.

This lesson uses Java 17+ and Spring Boot 3.3.x, focusing on registering listeners early enough, handling absent contexts safely, and distinguishing startup failures from runtime errors after the application is ready.

## 1. Position of ApplicationFailedEvent in the Startup Sequence

Main flow of a normal startup:

~~~text
main(String[] args)
    |
    v
SpringApplication.run(args)
    |
    +-- ApplicationStartingEvent
    |
    +-- Prepare Environment / config data
    |      |
    |      +-- ApplicationEnvironmentPreparedEvent
    |
    +-- Create ApplicationContext
    |
    +-- ApplicationContextInitializedEvent
    |
    +-- Load bean definitions
    |
    +-- ApplicationPreparedEvent
    |
    +-- Refresh ApplicationContext
    |
    +-- ApplicationStartedEvent
    |
    +-- ApplicationRunner / CommandLineRunner
    |
    +-- ApplicationReadyEvent
    |
    +-- run() returns context
~~~

This is a diagram of Spring Boot milestones, not a transcript of every internal call. During startup, if an exception passes through `SpringApplication.run(...)`'s failure-handling path, Boot emits `ApplicationFailedEvent` to listeners able to receive events at that time, while performing appropriate failure handling and cleanup.

Examples:

~~~text
Branch A: failure reading config / processing Environment
         |
         +-- ApplicationFailedEvent
             getApplicationContext() == null

Branch B: context created, yet refresh/bean creation fails
         |
         +-- ApplicationFailedEvent
             getApplicationContext() != null
             (context is not necessarily active or usable)

Branch C: context refreshed, yet runner throws an exception
         |
         +-- ApplicationFailedEvent
             (startup is still treated as failed)
~~~

**Do not infer backward that a failure event guarantees a context exists.** Receiving `ApplicationFailedEvent` signals that *this startup run* failed, not that `ApplicationContext` was created or is ready for use.

## 2. APIs to Know

Key methods:

| API | Meaning | Notes |
|---|---|---|
| `ApplicationFailedEvent.getException()` | Returns the `Throwable` that led to the startup failure. | May be a wrapper exception; inspect `getCause()` and stack trace for the root cause. |
| `ApplicationFailedEvent.getApplicationContext()` | Returns the initializing `ConfigurableApplicationContext`, **or `null`**. | Do not call `getBean()` or `getEnvironment()` on the result before checking `null`. |
| `ApplicationFailedEvent.getArgs()` | Returns the arguments of the `SpringApplication` run. | Do not log verbatim if arguments contain passwords/tokens. |
| `ApplicationFailedEvent.getSpringApplication()` | Identifies the `SpringApplication` that emitted the event. | Helpful when orchestrating multiple applications/contexts. |
| `SpringApplication.addListeners(...)` | Registers a listener before calling `run()`. | Proper way to receive events that happen before beans exist. |
| `SpringApplicationBuilder.listeners(...)` | Registers listeners on the builder. | Useful when launching via builder or context hierarchies. |

The constructor of `ApplicationFailedEvent` accepts application, arguments, context, and exception; per the Javadoc, the context parameter may be `null`.

Types to import:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
~~~

Do not confuse `ApplicationFailedEvent` with `ContextClosedEvent` or `ContextRefreshedEvent`:

- `ApplicationFailedEvent`: a `SpringApplication` startup failed.
- `ContextClosedEvent`: a context is closing; normal closing does **not** mean startup failed.
- `ContextRefreshedEvent`: the context has refreshed; not a signal that all Boot startup runners finished.
- `ApplicationReadyEvent`: a normal startup passed its runners and signaled ready.

## 3. Why Is There Sometimes No Context Yet?

Before creating `ApplicationContext`, Spring Boot must still initialize bootstrap machinery, prepare `Environment`, process property sources, and resolve settings needed early. Failures can occur, for example, when:

- A custom `EnvironmentPostProcessor` throws an exception.
- Required config data or configuration sources are invalid, causing environment preparation to fail.
- An early-registered listener for `ApplicationEnvironmentPreparedEvent` throws an exception.
- Another bootstrap component fails before code reaches `ApplicationContext` creation.

In these cases, Spring Boot **cannot provide an instantiated context**. The API still retains the application, arguments, and exception, while `getApplicationContext() == null`.

Note: not *every error in the JVM* becomes an `ApplicationFailedEvent`. If an error occurs before `SpringApplication.run(...)` actually begins (such as code in `main` throwing before calling `run`, class initialization errors, or errors constructing `SpringApplication` itself), `run(...)`'s failure-event mechanism may not be active yet. Exceptions in requests, schedulers, or message listeners **after startup succeeded** also do not automatically emit this event.

Therefore, when designing monitoring, `ApplicationFailedEvent` is **a startup failure diagnostic hook**, not a catch-all for every error in the process.

## 4. Registering the Listener Early Enough

### Right Approach: Register Before run()

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners(new StartupFailureListener());
app.run(args);
~~~

This is an **API usage snippet**, not a standalone Java file: `MyApplication` and `StartupFailureListener` must be defined as in your application.

Listeners meant to handle startup failures should be registered **before** calling `run()` so Boot knows about them from the bootstrap phases onward. When an application needs a listener automatically regardless of who calls `SpringApplication.run(...)`, Spring Boot also supports registration via `META-INF/spring.factories` under the `org.springframework.context.ApplicationListener` key.

### Error-Prone Approach: Creating the Listener Only as a Bean

~~~java
@Component
public class TooLateForEarlyFailure
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        System.err.println(event.getException());
    }
}
~~~

This **illustrates a class with full interface implementation but without imports declared**. The issue is not receiving events after the bean is created: the issue is that **this bean cannot exist yet if failure happens before ApplicationContext creation or before the bean is registered/instantiated**. You should not rely on a plain `@Component`/`@Bean` as the **sole mechanism** for catching bootstrap failures.

Similarly, `@EventListener(ApplicationFailedEvent.class)` on a bean cannot solve cases where no context exists. For listeners that must run very early, register at the `SpringApplication` or `SpringApplicationBuilder` level, or via registration config processed by Boot before run.

## 5. Runnable Example: Pre-Context Failure and Bean-Creation Failure

The following project has **a listener registered right before `run()`**. It drives two scenarios via command-line arguments:

- `--demo.fail-phase=environment`: deliberately throws an exception inside an `ApplicationEnvironmentPreparedEvent` listener, before Boot creates the context.
- `--demo.fail-phase=bean`: allows the environment to be prepared and the context created, then throws an exception when running a `@Bean` factory method during refresh.

### Project Structure

~~~text
failed-event-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── failed/
                        └── FailedEventDemo.java
~~~

Create `pom.xml` at the project root:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>failed-event-demo</artifactId>
    <version>1.0.0</version>

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

Create `src/main/java/com/example/failed/FailedEventDemo.java`:

~~~java
package com.example.failed;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication(proxyBeanMethods = false)
public class FailedEventDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(FailedEventDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);

        // Important: listener is registered BEFORE run().
        app.addListeners(new EarlyStartupListener());

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("[main] STARTED");
        }
        catch (RuntimeException ex) {
            // Demo intentionally catches the error to display observable milestones.
            System.out.println("[main] run() threw exception");
        }
    }

    @Bean
    DemoMarker demoMarker(@Value("${demo.fail-phase:none}") String phase) {
        if ("bean".equals(phase)) {
            throw new IllegalStateException("failure-in-bean");
        }
        return new DemoMarker();
    }

    static final class DemoMarker {
    }

    static final class EarlyStartupListener
            implements ApplicationListener<ApplicationEvent> {

        @Override
        public void onApplicationEvent(ApplicationEvent event) {
            if (event instanceof ApplicationEnvironmentPreparedEvent prepared) {
                String phase = prepared.getEnvironment()
                        .getProperty("demo.fail-phase", "none");

                if ("environment".equals(phase)) {
                    System.out.println("[probe] fail before context");
                    throw new IllegalStateException("failure-before-context");
                }
            }
            else if (event instanceof ApplicationFailedEvent failed) {
                System.out.println("[failed] context-null="
                        + (failed.getApplicationContext() == null));
                System.out.println("[failed] root-message="
                        + rootMessage(failed.getException()));
            }
        }

        private String rootMessage(Throwable throwable) {
            Throwable root = throwable;
            while (root.getCause() != null && root.getCause() != root) {
                root = root.getCause();
            }
            return root.getMessage();
        }
    }
}
~~~

In this example:

1. The listener implements `ApplicationListener<ApplicationEvent>` and uses `instanceof` to classify both events, so it does not rely on a bean listener being created in time.
2. `SpringApplication.addListeners(...)` is called **before `run(...)`**. The listener can receive events before any context exists.
3. The `environment` branch throws an exception as soon as `Environment` is ready, **before** context creation.
4. The `bean` branch throws an exception from the `demoMarker(...)` factory method once Boot has begun creating/refreshing the context.
5. The `ApplicationFailedEvent` branch always checks whether context is `null` before interpreting it.
6. `rootMessage(...)` walks the `getCause()` chain to retrieve the deepest cause message; real systems must also retain stack traces and related exceptions so context is not lost.
7. `catch (RuntimeException)` in `main` is strictly for this hands-on demo. **Production applications should not swallow startup errors and exit with success status**; the supervisor/orchestrator must know the process failed to start.

The example uses `WebApplicationType.NONE` to avoid web server setup and `Banner.Mode.OFF` to keep output clear. `spring-boot-starter` provides Spring context, logging, and the APIs used here.

### Compile and Run

Requires JDK 17+ and a compatible Maven version:

~~~bash
mvn package
java -jar target/failed-event-demo-1.0.0.jar --demo.fail-phase=environment
~~~

In Windows PowerShell, the same two commands work. To test an error occurring after the context has been created:

~~~bash
java -jar target/failed-event-demo-1.0.0.jar --demo.fail-phase=bean
~~~

And to test a normal startup:

~~~bash
java -jar target/failed-event-demo-1.0.0.jar
~~~

This is a complete Spring Boot project with required sources and dependencies; it **cannot run standalone with only `javac FailedEventDemo.java`** without Spring on the classpath.

### Scenario A: Pre-Context Failure

Command:

~~~bash
java -jar target/failed-event-demo-1.0.0.jar --demo.fail-phase=environment
~~~

The **lines printed by the lab code itself**, in order:

~~~text
[probe] fail before context
[failed] context-null=true
[failed] root-message=failure-before-context
[main] run() threw exception
~~~

Logs and stack traces emitted by Spring Boot may appear between these milestones, with varying timestamps and logger formatting. The key fact to observe is **`context-null=true`** because the exception occurred while handling `ApplicationEnvironmentPreparedEvent`, before context creation.

### Scenario B: Post-Context-Creation Failure

Command:

~~~bash
java -jar target/failed-event-demo-1.0.0.jar --demo.fail-phase=bean
~~~

The **lines printed by the code itself**, in order:

~~~text
[failed] context-null=false
[failed] root-message=failure-in-bean
[main] run() threw exception
~~~

When the `@Bean` factory method throws `IllegalStateException`, Spring may wrap it in `BeanCreationException` or another bean creation exception. Still, the deepest cause message intentionally thrown by the program is `failure-in-bean`. Spring Boot had already created the context object before proceeding with refresh and bean instantiation, so the failure event holds a non-null context reference (`!= null`).

**Do not infer `context-null=false` as `context.isActive()==true`, and certainly not as application ready.** At the moment of failure, the context may be newly created, mid-refresh, or unusable.

### Scenario C: Successful Startup

Command:

~~~bash
java -jar target/failed-event-demo-1.0.0.jar
~~~

Line printed from `main`:

~~~text
[main] STARTED
~~~

In this scenario the program does not intentionally throw an exception; `ApplicationFailedEvent` is not emitted. After printing the marker, `try-with-resources` actively closes the context so the console application exits cleanly.

## 6. Handling the Event Safely When Context May Be Null

A practical handling pattern should:

1. **Always inspect the exception first**, since the failure cause is the primary payload of the failure event.
2. **Check whether the context is null**, rather than assuming a context always exists.
3. **Never require accessing beans** to record the incident. Use a pre-existing error-reporting channel independent of the Spring context.
4. **Never use the context as if it were refreshed** even when the object is non-null.
5. Keep listener logic **fast, minimal, and unlikely to cause secondary errors**.

Illustrative example of a dedicated listener (placed in its own class and registered via `app.addListeners(...)`):

~~~java
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;

public final class StartupFailureLogger
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable failure = event.getException();
        ConfigurableApplicationContext context =
                event.getApplicationContext();

        System.err.println("Startup failed: "
                + failure.getClass().getName());

        if (context == null) {
            System.err.println("Phase: before context creation");
            return;
        }

        // Context object exists; this does not mean refresh succeeded.
        System.err.println("Context object exists; do not fetch beans");
    }
}
~~~

The snippet above describes **`StartupFailureLogger.java`** in a package of your choice; when adding to a real project, include the appropriate `package` declaration. This listener needs no Spring bean to work, provided you register an instance before `run()`.

Consider logging errors idempotently: Spring Boot already performs error reporting, so a custom listener does not necessarily need to print the full stack trace a second time. If sending metrics or alerts to external systems, use short timeouts and fallbacks, and avoid letting an alerting failure mask the root cause of the startup failure.

### Why Not Call getBean() in ApplicationFailedEvent?

The following snippet is **unsafe**:

~~~java
ConfigurableApplicationContext context = event.getApplicationContext();
AlertService service = context.getBean(AlertService.class);
service.notifyFailure(event.getException());
~~~

This is anti-example code: `AlertService` is assumed to be a Spring-managed service; it is not a runnable snippet. It can throw `NullPointerException` if `context == null`, or `IllegalStateException`/`BeanCreationException` if the context object exists yet did not finish refreshing. Even if the bean is retrieved, its dependencies may be in an unusable state.

Safer alternatives:

- Use an error reporter **initialized independently** before Boot startup, with known resources and lifecycle.
- Or record only minimal cause, phase, and correlation IDs, letting the process's logging/observability agent collect them.
- If alerts must be sent after startup failures, systems outside the JVM (orchestrator, process supervisor, CI, deployment controller) are usually more reliable places to observe exit status and logs.

## 7. Failures After Context Creation but Before Ready

The `context != null` case can arise in several distinct phases:

| Failure point | Context exists? | Can beans/context be used normally? |
|---|---|---|
| Preparing config data or environment | Not yet | No. |
| Creating `ApplicationContext` fails before returning object | Possibly not | No. |
| Applying `ApplicationContextInitializer` or loading bean definitions | Possibly yes | Must not assume refreshed. |
| Instantiating singletons, dependency injection, `@PostConstruct` | Yes | Container may be in a broken state and will be cleaned up. |
| Binding web server port during refresh | Yes | May not be serving HTTP successfully yet. |
| `ApplicationRunner` / `CommandLineRunner` throws | Yes, usually refreshed | Still a startup failure; does not mean ready. |

Once the event is emitted and Boot handles the failure, the application may close the failed context to release resources. Therefore, **do not keep references from `ApplicationFailedEvent` for long-term use**, do not run tasks on failed beans, and do not attempt to call `refresh()` inside a failure listener as an automatic recovery hack.

If retries are desired, enforce a **retry policy at the orchestration layer** (max attempts, backoff, alerting, distinguishing permanent misconfiguration from transient errors). Retry only when root causes and prior cleanup are understood.

## 8. ApplicationFailedEvent Does Not Replace Application-Wide Exception Handling

Distinction table across mechanisms:

| Scenario | Appropriate mechanism |
|---|---|
| Boot startup fails inside `run(...)` | `ApplicationFailedEvent`; logs, failure analysis, process exit status. |
| HTTP request error while app is running | Web framework exception handler, observability/logging. |
| Error in `@Scheduled` task after ready | Scheduler error handler and monitoring. |
| Message consumer listener throws while running | Message framework error handler/retry/DLQ. |
| Normal requested context shutdown | `ContextClosedEvent` / lifecycle shutdown callbacks. |
| Want clear explanation of invalid startup condition | `FailureAnalyzer` or an exception with a helpful message. |

For example, the `APPLICATION FAILED TO START` log shown by Spring Boot via `FailureAnalyzer` is diagnostic output. A `FailureAnalyzer` turns known exceptions into readable "Description" and "Action" sections; it does not mean the application has an active context. `ApplicationFailedEvent`, by contrast, lets listeners receive the failure signal and exception for lightweight tasks like metrics or auditing.

If custom failure reporting is needed, avoid heavy processing inside `ApplicationFailedEvent`. The listener executes along an already-failing path; if it throws another exception, diagnostics become harder or trigger listener-error warnings.

## 9. Common Traps

**Trap 1 — Always calling `event.getApplicationContext().getBean(...)`.**

Wrong because the context may be `null` or unusable. Inspect the exception first, check for null, and avoid relying on beans to report bootstrap failures.

**Trap 2 — Registering only `@EventListener(ApplicationFailedEvent.class)` inside a bean.**

This cannot guarantee catching errors before beans/contexts are created. Use `SpringApplication.addListeners(...)`, builder listeners, or intentional bootstrap registration.

**Trap 3 — Treating `context != null` as startup success.**

Incorrect: the context may be mid-refresh or already entering cleanup. Do not call business beans and do not treat it as ready.

**Trap 4 — Assuming every exception after the app starts emits ApplicationFailedEvent.**

This event is tied to `SpringApplication` startup failures. Post-startup HTTP requests, scheduled tasks, and message consumers have their own error-handling mechanisms.

**Trap 5 — Reacting with `System.exit(...)` inside the listener.**

That can cut off failure analysis, context cleanup, and log flushing; it affects the entire JVM, which is especially dangerous with multiple Spring contexts. Let Boot finish its failure path and let the orchestrator decide restarts.

**Trap 6 — Thinking catching the exception in `main` lets Boot keep starting.**

Once `run(...)` throws an exception, no successfully running context is returned. If `main` catches and swallows the error, the process may exit with status 0, misleading deployment tooling into thinking startup succeeded. Do not use the demo's `catch` block as a production policy.

**Trap 7 — Logging all of `getArgs()` to centralized logging.**

Arguments can contain secrets, tokens, internal hostnames, or sensitive data. Redact data and log only metadata needed for diagnostics.

**Trap 8 — Assuming the listener catches every error even before `run()`.**

Not guaranteed. Exceptions in Java code before Boot sets up its listener system fall outside `ApplicationFailedEvent`'s scope.

## 10. Checklist for Investigating a Startup Failure

Upon receiving `ApplicationFailedEvent`, ask in order:

1. **Was the event caught?** Was the listener registered before `run()`? Did the error occur within Boot's startup sequence?
2. **Is the context `null`?** If yes, investigate config data, environment, bootstrap listeners/processors, and pre-context steps first.
3. **What is the root exception?** Read `getException()`, all `cause`s, suppressed exceptions, and stack traces; avoid capturing only the line "Application failed to start."
4. **If a context exists, which phase did it reach?** Context creation does not mean refresh completed. Check logs for refresh, binding, bean creation, and runners.
5. **Did a secondary error happen in the listener?** Failure listeners should not depend on beans; check timeouts and fallback logging.
6. **Was lifecycle cleanup done properly?** Do not retain references to failed contexts or run background tasks on partially initialized beans.
7. **Do the process/CI/orchestrator know it failed?** Exit status, restart policies, health probes, and alerts must reflect the actual startup outcome.

### References

- Spring Boot 3.3 — `ApplicationFailedEvent` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html
- Spring Boot 3.3 — `SpringApplicationRunListener.failed(...)`, context parameter may be null: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplicationRunListener.html
- Spring Boot — Application Events and Listeners, Startup Failure: https://docs.spring.io/spring-boot/reference/features/spring-application.html

**Takeaway:** `ApplicationFailedEvent` signals a failed Boot startup and always carries the exception. **`getApplicationContext()` is not guaranteed to be non-null**, and a non-null context does not prove refresh succeeded. Register failure listeners **before `SpringApplication.run(...)`**, handle errors independently of beans, and let Boot's failure/shutdown machinery complete.
