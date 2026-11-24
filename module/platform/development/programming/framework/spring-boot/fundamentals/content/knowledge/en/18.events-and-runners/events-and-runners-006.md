# ApplicationFailedEvent and Startup Failure Information

A Spring Boot application can fail right while preparing the `Environment`, during `ApplicationContext` creation, when instantiating beans, or while executing a startup task. Because these errors happen **before the application is truly ready to serve**, HTTP monitoring endpoints or business-handling beans may not even be active yet.

**ApplicationFailedEvent** is the event Spring Boot publishes when the startup process managed by `SpringApplication` encounters an error. This event carries the exception that caused the failure and, if already created, a reference to the application context. It serves as an extension point to collect startup failure details, write extra logs, or notify monitoring mechanisms capable of operating at an early stage.

This lesson belongs to the **Events and Runners** topic because failures can arise both before and during the execution of `ApplicationRunner` or `CommandLineRunner`. To use the event effectively, you need to understand when it is published, what data can be read, and the limitations of uninitialized components.

## 1. What Is ApplicationFailedEvent?

`ApplicationFailedEvent` belongs to package:

~~~java
org.springframework.boot.context.event.ApplicationFailedEvent
~~~

It is a Spring Boot lifecycle event published when `SpringApplication` handles an error that prevents startup from completing. It belongs to `SpringApplication`'s event group, rather than merely reporting a failure from a single isolated bean.

Examples of situations that can lead to this event:

- Invalid configuration or a configuration value that fails to bind to a Java object.
- A bean failing to instantiate due to a missing dependency, circular dependency, or constructor exception.
- The embedded server failing to bind to a port already in use.
- A `@Bean` factory method throwing an exception when the container creates the bean.
- An `ApplicationRunner` or `CommandLineRunner` throwing an exception.
- A callback during startup causing `SpringApplication.run(...)` to fail.

Important point: **ApplicationFailedEvent reports that startup encountered an error; by itself, it does not fix the error or keep the application running.** Typically Spring Boot proceeds with failure handling, closes the context if necessary, and propagates the exception to the caller of `run(...)`.

This event is not guaranteed to fire for failures outside the startup flow that `SpringApplication` can catch and publish, such as errors occurring before calling `run(...)`, abrupt JVM termination, or the process being killed by the operating system.

## 2. Position of the Event in the Spring Boot Lifecycle

In a successful startup, the main milestones are typically:

~~~text
main()
  |
  v
SpringApplication.run(args)
  |
  v
Prepare Environment and ApplicationContext
  |
  v
Load config, create bean definitions, refresh context
  |
  v
ApplicationStartedEvent
  |
  v
Run ApplicationRunner / CommandLineRunner
  |
  v
ApplicationReadyEvent
  |
  v
Application ready
~~~

If an exception causes startup to fail, execution shifts to the failure-handling branch:

~~~text
SpringApplication.run(args)
       |
       +-- Prepare environment ------ error --+
       |                                      |
       +-- Prepare/refresh context -- error --+--> ApplicationFailedEvent
       |                                      |      |
       +-- Run runners -------------- error --+      v
       |                                      |   Handle failure
       +-- Complete startup --------- error --+   and end run
       |
       +-- No error --> ApplicationReadyEvent
~~~

This is an overview diagram and does not list every internal Spring Boot event and callback.

Two consequences to remember:

1. If an error occurs **before the context is created**, `ApplicationFailedEvent` can still be published, but there is no `ApplicationContext` to access.
2. If an error occurs inside a runner, the context has typically refreshed and `ApplicationStartedEvent` has usually been published, while `ApplicationReadyEvent` has not been published successfully.

The second distinction is very helpful: **Started** means the context refreshed and Spring Boot is about to run runners; **Ready** means startup passed through runners and reached the ready stage.

## 3. Information Contained in ApplicationFailedEvent

Frequently used APIs:

| API | Meaning | Usage |
|---|---|---|
| `event.getException()` | Returns the `Throwable` associated with the startup failure | Log full stack trace, analyze cause chain |
| `event.getApplicationContext()` | Returns the context if already created, may be `null` | Read simple context info if it exists |
| `event.getSpringApplication()` | Returns the associated `SpringApplication` object | Identify the application being run |
| `event.getArgs()` | Returns the startup arguments array | Use only when strictly needed; avoid logging secrets from command line |

Example:

~~~java
@Override
public void onApplicationEvent(ApplicationFailedEvent event) {
    Throwable failure = event.getException();

    ConfigurableApplicationContext context =
            event.getApplicationContext();

    System.err.println("Error type: " + failure.getClass().getName());

    if (context != null) {
        System.err.println("Context ID: " + context.getId());
    } else {
        System.err.println("ApplicationContext has not been created.");
    }
}
~~~

The snippet above illustrates reading the event; in real applications, use a proper logger instead of `System.err` once the logging system is ready.

### Why Can getApplicationContext() Be Null?

Spring Boot has to perform several tasks **before a context exists**, such as processing initial configuration sources and preparing the environment. If startup halts during this stage, there is no context to supply to listeners.

Even when `getApplicationContext()` is non-null, the context is not guaranteed to have refreshed successfully, remain active, or contain all normal beans. Therefore, **never infer that because a context exists, you can call every service inside it**.

A safe listener needs to tolerate all three states:

- Context not yet created: `null`.
- Context created, but refresh failed.
- Context refreshed, then a runner or startup callback threw an exception.

## 4. Registering a Listener Early Enough to Catch Startup Failures

Because failures can happen before application beans are created, the clearest and most reliable approach for this example is **registering the listener directly on SpringApplication before calling run**.

Suppose the Spring Boot project has package `com.example.startup`.

File `DemoApplication.java`:

~~~java
package com.example.startup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.addListeners(new StartupFailureListener());
        application.run(args);
    }
}
~~~

File `StartupFailureListener.java`:

~~~java
package com.example.startup;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;

public final class StartupFailureListener
        implements ApplicationListener<ApplicationFailedEvent> {

    private static final Logger log =
            LoggerFactory.getLogger(StartupFailureListener.class);

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable failure = event.getException();
        ConfigurableApplicationContext context =
                event.getApplicationContext();

        String contextId = context == null
                ? "(no context yet)"
                : context.getId();

        log.error("Spring Boot startup failed; context=" + contextId,
                failure);
    }
}
~~~

Here:

1. `main()` constructs `SpringApplication` explicitly.
2. `addListeners(...)` registers the listener before `run(args)` starts.
3. When Spring Boot publishes `ApplicationFailedEvent` during startup, the listener receives the event.
4. The listener reads the context in a `null`-safe manner.
5. Calling `log.error(message, failure)` passes the `Throwable`, allowing the logger to record the stack trace.

These two files use standard APIs from Spring Boot, Spring Context, and SLF4J. In a project with `spring-boot-starter` or appropriate Boot starters, the required libraries are already in the dependency graph.

### Why Register on SpringApplication?

The usual shorthand:

~~~java
SpringApplication.run(DemoApplication.class, args);
~~~

is concise, but does not give you a `SpringApplication` variable to call `addListeners(...)` before running. When an early listener is needed, creating the instance and registering explicitly makes the sequence obvious to readers.

**No dependency injection is needed to instantiate StartupFailureListener in this example.** The listener only uses a logger and data passed via the event, so it works independently of business services that may not have been initialized.

## 5. Should You Use @EventListener or @Component?

In Spring, events are commonly handled using methods annotated with `@EventListener`:

~~~java
@Component
public class FailureEventHandler {

    @EventListener
    public void onFailed(ApplicationFailedEvent event) {
        // Handle error details.
    }
}
~~~

This approach is convenient for events published **after the context is ready to accept events**. However, `ApplicationFailedEvent` may be published while Spring is still building the context or after failing before listeners from beans are fully registered.

Therefore, **do not rely solely on an `@EventListener` inside an application bean if the requirement is to observe startup failures across all early stages**. Even a `@Component` implementing `ApplicationListener<ApplicationFailedEvent>` shares a similar limitation if Spring has not yet created or registered that bean.

Comparison:

| Registration Method | Advantage | Main Limitation |
|---|---|---|
| `application.addListeners(new StartupFailureListener())` before `run()` | Listener is registered from the start on `SpringApplication` | Must manage listener dependencies manually |
| `@Component` combined with `ApplicationListener` | Easy integration with application beans | Bean/listener may not be ready during early startup failure |
| `@EventListener` method inside a bean | Concise, familiar for runtime events | Depends on context instantiation and annotation processing |

A startup failure listener should have **minimal dependencies**, require no business beans, and handle a missing context gracefully.

## 6. ApplicationFailedEvent When ApplicationRunner Fails

`ApplicationRunner` and `CommandLineRunner` allow running tasks after the context has refreshed but before the application's ready milestone.

Example of a runner throwing an error to simulate initial data preparation failing:

~~~java
package com.example.startup;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class StartupTaskConfiguration {

    @Bean
    ApplicationRunner prepareInitialData() {
        return args -> {
            System.out.println("Preparing initial data...");
            throw new IllegalStateException(
                    "Unable to prepare initial data");
        };
    }
}
~~~

If this component is discovered by Spring Boot:

1. Spring creates and refreshes the context.
2. Spring Boot publishes `ApplicationStartedEvent`.
3. Spring Boot calls `prepareInitialData()` via the `ApplicationRunner` mechanism.
4. The runner throws `IllegalStateException`.
5. `SpringApplication` handles the error and publishes `ApplicationFailedEvent`.
6. `ApplicationReadyEvent` is not published as a successful startup milestone.

If `StartupFailureListener` from the earlier section is registered, the listener logs an error message and the corresponding stack trace. Receiving `ApplicationFailedEvent` does not cause Spring Boot to continue running remaining runners or transition to the ready state.

### What About CommandLineRunner?

`CommandLineRunner` shares a similar execution point:

~~~java
@Bean
CommandLineRunner validateStartupState() {
    return args -> {
        if (!isStartupStateValid()) {
            throw new IllegalStateException(
                    "Invalid startup state");
        }
    };
}
~~~

`isStartupStateValid()` is an illustrative application-defined method. The key point is: **if an unhandled exception escapes a runner, it can cause the entire startup attempt to be treated as failed** and lead to `ApplicationFailedEvent`.

In real projects, do not intentionally throw errors in production to observe the event. You can use a simulated configuration or runner in a separate learning environment.

## 7. Distinguishing ApplicationStartedEvent, ApplicationReadyEvent, and ApplicationFailedEvent

These three events indicate three distinct states during startup:

| Event | Typical Timing | What Can Be Concluded |
|---|---|---|
| `ApplicationStartedEvent` | Context has refreshed, before runners execute | Container passed refresh; startup still has next steps |
| `ApplicationReadyEvent` | Runners completed and Spring Boot reached ready stage | Main startup process completed successfully |
| `ApplicationFailedEvent` | Error prevented `SpringApplication` from completing startup | Need to inspect exception and handle application failure to start |

Examples:

**Scenario A — Very early misconfiguration:** `ApplicationFailedEvent` may be received without a context; `ApplicationStartedEvent` and `ApplicationReadyEvent` have not occurred.

**Scenario B — BeanCreationException during refresh:** Context may have been created, yet failed to finish initialization. `ApplicationStartedEvent` has usually not been published.

**Scenario C — ApplicationRunner throws an exception:** `ApplicationStartedEvent` usually already occurred; `ApplicationFailedEvent` is published; the application does not reach the successful ready milestone.

This matters when reading logs: seeing `ApplicationStartedEvent` is not enough to conclude the application is ready to accept traffic. If runners still need to execute, the ready milestone lies further ahead.

## 8. Reading Exceptions Properly

`event.getException()` returns a `Throwable`. The exception observed at the outer layer may be a container exception, while the underlying technical cause lies deeper in the `cause` chain.

Example cause chain:

~~~text
BeanCreationException
  |
  +-- UnsatisfiedDependencyException
        |
        +-- IllegalArgumentException
              |
              +-- "Invalid configuration value"
~~~

The stack trace and `Caused by` chain help determine:

- Which bean or factory method failed.
- Which dependency could not be satisfied.
- Which class and line of code threw the original exception.
- Whether there is an underlying I/O, configuration, connectivity, or type error.

### Log the Entire Throwable, Not Just the Message

Uninformative logging:

~~~java
log.error("Startup failed: {}", event.getException().getMessage());
~~~

That line only logs the message. It drops the stack trace and nested `cause` entries needed for investigation.

More complete approach:

~~~java
Throwable failure = event.getException();
log.error("Spring Boot failed to start", failure);
~~~

If you need to display the error type:

~~~java
log.error("Startup failed; type=" +
        failure.getClass().getName(), failure);
~~~

When the logger receives the `Throwable` object directly, the full exception chain is typically formatted according to your logging configuration.

### Extracting the Deepest Cause for Additional Diagnostics

You can walk the `getCause()` chain:

~~~java
static Throwable deepestCause(Throwable failure) {
    Throwable current = failure;

    while (current.getCause() != null &&
           current.getCause() != current) {
        current = current.getCause();
    }
    return current;
}
~~~

Usage:

~~~java
Throwable failure = event.getException();
Throwable root = deepestCause(failure);

log.error("Startup failed; deepestCause=" +
        root.getClass().getSimpleName() +
        "; message=" + root.getMessage(), failure);
~~~

This illustrates walking standard cause chains. When writing a general utility to inspect `Throwable` instances from untrusted sources, you may also need to guard against more complex reference cycles among causes.

**Never replace the full stack trace with just the root cause.** The outermost error is equally important because it identifies which bean or startup stage failed.

## 9. Common Startup Failures and Investigation Approaches

| Log Symptom | Potential Issue to Check | Approach |
|---|---|---|
| `UnsatisfiedDependencyException` | Matching dependency not found or multiple candidates unresolved | Check component scanning, `@Bean`, `@Qualifier`, `@Primary`, and profiles |
| `BeanCreationException` | Constructor, init method, or factory method failed | Inspect `Caused by` and the exact throw location |
| `NoSuchBeanDefinitionException` | Expected bean missing | Check bean registration config, conditional configuration, and scan scope |
| `@ConfigurationProperties` binding error | Config value type mismatch or validation failed | Check config file, property names, format, and constraints |
| Port already in use message | Embedded web server could not bind port | Check process occupying the port or `server.port` config |
| DB or external service connection error | Endpoint, credentials, DNS, network, or migration issue | Inspect root exception, verify connectivity and environment config |
| Error inside `ApplicationRunner` | Data preparation task or startup check failed | Read runner stack trace, check input conditions |
| Circular reference error | Beans depend on each other in a cycle | Redesign dependencies to break the cycle |

Exception names may vary by throwing class and library version. The table provides initial log-reading guidance; final diagnosis must rest on the actual message, causes, and configuration.

### Example: Missing Bean Due to Component Scanning

Suppose `OrderService` requires `PaymentGateway` via constructor injection, but its implementation sits outside the component scan area. The container may report a missing dependency while creating the service. A listener receives `ApplicationFailedEvent` and logs the stack trace, yet the listener itself cannot register the missing dependency to let the current startup proceed.

The fix is to adjust scan configuration or register the bean properly, then restart.

### Example: A Runner Validating Required Data

A runner can verify required schemas or resources before the application becomes ready. When mandatory conditions fail, the runner throws an exception so Spring Boot does not announce a ready state. The listener logs the full cause, while runner logic provides a clear message explaining the invalid data or condition.

## 10. What Error Information Does Spring Boot Already Provide Before Writing a Listener?

Spring Boot normally logs details automatically when startup fails. For errors recognized by the **FailureAnalyzer** mechanism, output can look like:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:
    Description of the condition leading to the startup failure.

Action:
    Suggested configuration or remediation step.
~~~

This is an illustrative format. Actual output depends on the exception type and whether a matching `FailureAnalyzer` exists.

Related components:

- **FailureAnalyzer:** recognizes specific exceptions and translates them into a readable `FailureAnalysis`.
- **FailureAnalysis:** holds the description and remediation action when analysis succeeds.
- **FailureAnalysisReporter:** displays or reports the analysis result.

`ApplicationFailedEvent` and `FailureAnalyzer` solve different problems:

| Mechanism | Primary Purpose |
|---|---|
| `ApplicationFailedEvent` | Notifies listeners that startup failed and provides the Throwable/context if available |
| `FailureAnalyzer` | Translates a known exception type into cause description and fix suggestions |
| Boot's default logging | Records the error and necessary details on startup failure |

For ordinary applications, **read Boot's default logs first**. Add a listener only when you need to record system-specific data or integrate with other observability tools.

### When to Use `--debug`?

You can run the application with:

~~~bash
java -jar app.jar --debug
~~~

In situations involving auto-configuration, debug mode displays more detailed information, usually including the **Condition Evaluation Report** to distinguish which configuration conditions matched or did not match.

`--debug` does not mean every bean, every SQL statement, or every network request is automatically logged in detail. When investigating a specific package, configure the corresponding logging level rather than enabling overly broad logs.

## 11. Designing StartupFailureListener Without Causing Secondary Errors

A startup failure listener runs at a sensitive time: the application itself is failing. A complex listener can raise a new exception and make logs harder to read.

Design principles:

1. **Minimal dependencies:** Prefer reading `event.getException()` and simple context info.
2. **Do not fetch business beans:** Avoid calling `context.getBean(...)`; the context might not have refreshed or is failing.
3. **Do not rely on the web server:** HTTP endpoints, Actuator, and application networking services might not be running yet.
4. **Do not mask the original exception:** When logging or sending notifications, prevent listener logic from throwing new uncaught errors.
5. **Do not log secrets:** Startup arguments, connection strings, tokens, passwords, and environment entries can contain sensitive data.
6. **Keep handling brief:** Avoid long or blocking work that delays failure reporting and process exit.

A listener with a failure-prone secondary task, such as sending an alert via an external channel, can guard that task separately:

~~~java
@Override
public void onApplicationEvent(ApplicationFailedEvent event) {
    Throwable startupFailure = event.getException();

    log.error("Startup failed", startupFailure);

    try {
        notifyMonitoringWithoutSpringBeans(startupFailure);
    } catch (Exception notificationFailure) {
        log.warn("Failed to send startup failure notification",
                notificationFailure);
    }
}
~~~

`notifyMonitoringWithoutSpringBeans(...)` is a hypothetical system-defined method, not a Spring API. It must operate independently of application beans. The example illustrates **preserving the original startup error** if the secondary reporting step fails.

In many systems, letting an external monitoring agent collect process/container logs is simpler and more reliable than opening a new network connection inside a startup listener.

## 12. Notes on Logging and Sensitive Data

At an early stage, logging might not be fully configured as desired. Failures occurring while initializing the logging system itself can also restrict what a custom listener or logger can write.

Furthermore, **exception messages are not always safe to forward verbatim everywhere**. For example, a library may include a URL containing credentials or part of a connection string inside an exception message.

When integrating with monitoring systems:

- Prefer error type, application name, environment, timestamp, and access-controlled stack traces.
- Avoid dumping the entire `Environment` or `event.getArgs()`.
- Do not put passwords, API keys, or secrets into custom messages constructed inside runners.
- Distinguish internal diagnostic data from information safe to show end users.

`ApplicationFailedEvent` itself does not enforce data-masking policies; the application is responsible for what listeners log or transmit.

## 13. When the Context Exists but Is Not Usable

Consider these scenarios:

~~~text
A. Reading configuration fails very early
   getApplicationContext() -> may be null

B. Context created, bean creation fails
   getApplicationContext() -> may be non-null
   but refresh has not completed

C. Context refreshed, runner throws error
   getApplicationContext() -> usually non-null
   but startup will fail and context may be closed
~~~

No `context != null` check can guarantee that all beans are ready. Even `context.isActive()` only reflects context state at the instant of checking; it does not prove all dependencies or startup tasks succeeded.

Therefore, most listeners should use the context only for simple information such as `getId()`, if present, and draw primary diagnostics from `getException()`.

If you need to handle bean states after the application is already ready, that is a separate concern: use `ApplicationReadyEvent`, runtime events, health indicators, or suitable monitoring mechanisms.

## 14. ApplicationFailedEvent Does Not Replace Error Management Inside Runners

Suppose a runner loads a resource from an external service. Not every error needs to fail the application.

There are two distinct business directions:

**Mandatory error:** The application cannot function properly without the required data. The runner should throw an exception with a clear message. Boot transitions to the failure path and listeners have the opportunity to receive `ApplicationFailedEvent`.

**Recoverable error:** The application can still start with degraded functionality or retry later. The runner can handle the error according to the system's retry/fallback policy. If no exception escapes and other startup steps succeed, that case alone does not trigger `ApplicationFailedEvent`.

Example illustrating a mandatory decision:

~~~java
@Bean
ApplicationRunner verifyRequiredConfiguration(
        ApplicationSettings settings) {

    return args -> {
        if (!settings.hasRequiredEndpoint()) {
            throw new IllegalStateException(
                    "Missing required endpoint for operation");
        }
    };
}
~~~

`ApplicationSettings` and `hasRequiredEndpoint()` are illustrative application-defined types/methods.

Here, **the runner decides the success condition of the startup step**; `ApplicationFailedEvent` merely reflects the outcome when that condition causes startup to fail. Do not use a failure listener to re-run business tasks or try to rescue a context that Spring Boot is closing after a failure.

## 15. A Practical Startup Failure Investigation Workflow

When a Spring Boot application fails to run, follow this sequence:

1. **Identify the run and timestamp of failure:** collect logs from the exact process or container.
2. **Find the main error message:** look for `APPLICATION FAILED TO START` if present, along with exception lines.
3. **Read the `Caused by` chain:** identify the root error as well as the associated bean or runner.
4. **Determine the phase:** did it fail reading config, refreshing context, starting the server, or running runners?
5. **Inspect environment configuration:** active profiles, config values, environment variables, actual dependencies.
6. **Use auto-configuration info when relevant:** try `--debug` for hard-to-explain conditional configuration issues.
7. **Fix the root cause and restart:** receiving the event does not automatically restart the process.

Simple log example:

~~~text
INFO  ... Application context initialized
INFO  ... Starting startup runner
ERROR ... Startup failed
java.lang.IllegalStateException: Unable to prepare initial data
    at com.example.startup.StartupTaskConfiguration...
~~~

If this log comes from the runner described earlier, you can deduce that the failure occurred **after the refresh phase**, yet before the application completed startup. You need to fix the runner's work or its input conditions.

In an orchestrated environment, process restarts or retry policies are decided at the application runtime layer. `ApplicationFailedEvent` is only a signal source inside Spring Boot; it does not establish a restart policy on its own.

## 16. Practice: Observing the Event Through Three Failure Types

You can use a minimal Spring Boot project for three experiments. Keep the listener registered via `application.addListeners(...)`, then trigger each failure in a development environment.

### Experiment 1: Error from ApplicationRunner

Add `StartupTaskConfiguration` from section 6, start the application, and observe the exception message from the listener. Then remove the exception in the runner, run again, and observe the application complete startup.

Key takeaway: if a runner throws an exception, the application does not reach the successful ready milestone.

### Experiment 2: Error During Bean Creation

Create a sample bean:

~~~java
@Configuration(proxyBeanMethods = false)
public class BrokenBeanConfiguration {

    @Bean
    SampleStartupResource sampleStartupResource() {
        throw new IllegalStateException(
                "Unable to create resource at startup");
    }
}
~~~

`SampleStartupResource` is a hypothetical type you declare while practicing. You can replace it with a simple empty class.

This error occurs while Spring creates singletons, before runners execute. The listener still receives the startup error if it falls within `SpringApplication`'s failure handling flow.

### Experiment 3: Early Configuration Error

Try supplying an invalid configuration value to a component with binding/validation in the project. Observe whether a context exists when the failure listener runs. Depending on the configuration type and parsing timing, the context may not exist yet or may be partially created.

**Do not assume every configuration error makes `getApplicationContext()` return `null`.** This depends on the stage where the error is detected.

### What to Record

| Observation Question | Runner failure | Bean creation failure | Configuration failure |
|---|---|---|---|
| What is the root exception? | Exception from runner | Exception in bean/factory method | Exception reading/binding/validating config |
| Might `ApplicationStartedEvent` have fired? | Usually yes | Usually no | Depends on stage, usually no |
| Is context always non-`null`? | Should not rely on as a universal guarantee | May exist but not yet usable | May or may not exist |
| Successful `ApplicationReadyEvent`? | No | No | No |

The experiment demonstrates that failure timing determines which objects already exist, while an early-registered listener still has the chance to capture `ApplicationFailedEvent`.

## 17. Common Misconceptions

**"Having ApplicationFailedEvent means the context has been created."** False. `getApplicationContext()` can be `null`.

**"Just adding @EventListener to a service guarantees catching startup failures."** Not guaranteed, because the service or event method registration mechanism might not have been initialized prior to failure.

**"ApplicationStartedEvent means the application is ready."** No. Runners still execute after the started event.

**"If ApplicationRunner throws an error, ApplicationReadyEvent still runs."** With an unhandled error causing `run()` to fail, the application does not reach a successful ready milestone.

**"Reading getException().getMessage() is enough to debug."** Usually insufficient. You need the stack trace and cause chain.

**"A listener can rescue startup by fixing the broken bean."** The failure listener receives the event while Spring Boot is handling a failed startup; configuration fixes must be applied at the source followed by a restart.

**"Whenever context is non-null, calling getBean() works."** Unsafe. The context may be mid-refresh or about to close.

**"ApplicationFailedEvent will appear for every JVM crash."** No. It handles startup errors caught by `SpringApplication`'s machinery.

## Conclusion

`ApplicationFailedEvent` lets you observe a failed Spring Boot startup attempt. The two most important pieces of information are **`getException()`**, used to read the full exception chain, and **`getApplicationContext()`**, which may return `null` or an unready context.

To catch early failures, implement `ApplicationListener<ApplicationFailedEvent>` and register it directly using `SpringApplication.addListeners(...)` before calling `run(...)`. Keep the listener simple, independent of business beans, log the stack trace, and avoid triggering new exceptions on the failure path.

In the **Events and Runners** topic, remember: `ApplicationStartedEvent` occurs before runners, `ApplicationReadyEvent` marks successful startup completion, and an exception from `ApplicationRunner` or `CommandLineRunner` can lead the application to `ApplicationFailedEvent`. When investigating, prioritize Spring Boot's default logs, the root exception, and relevant configuration details, then fix the cause preventing startup from completing.
