# Handling Listener Exceptions During Spring Boot Startup

## 1. What Happens When a Startup Listener Throws an Exception?

In Spring Boot, **application events** are the mechanism for announcing lifecycle milestones. A listener can be registered via `SpringApplication.addListeners(...)`, by implementing `ApplicationListener<E>`, or by using `@EventListener` on an `ApplicationContext` bean. If a listener is invoked synchronously and throws an unhandled exception, the exception can propagate back to the event publisher and cause `SpringApplication.run(...)` to fail.

Under Spring Framework's default mechanism, application events are typically multicast by `SimpleApplicationEventMulticaster` and listeners run **synchronously on the same thread as the publisher**. Spring Boot therefore advises against performing long-running tasks in startup listeners. When an application fails during startup, Boot publishes `ApplicationFailedEvent` to signal the failure and execute failure handling.

**Do not equate** these three situations:

| Situation | What happens | Practical conclusion |
| --- | --- | --- |
| Synchronous listener throws an uncaught `RuntimeException` | Error typically propagates to publisher and can fail startup | Must address the root cause, not merely hide logs |
| Listener catches and continues | Publisher sees no error if the listener swallowed it completely | Only reasonable for genuinely non-essential auxiliary errors |
| Listener runs asynchronously or multicaster uses an `ErrorHandler` | Errors may be handled in executor/handler instead of propagating by default | Must explicitly design a failure policy; never use to mask mandatory startup checks |

**Scope of lesson:** focuses on listeners triggered during `SpringApplication.run(...)`, from very early events through `ApplicationStartedEvent` and `ApplicationReadyEvent`. Events published at runtime after the application is ready share Spring's event foundation, but their impact on startup state differs.

## 2. Startup Milestones and Where Listeners Can Fail

Main sequence in Spring Boot 3.x:

~~~mermaid
flowchart TD
    A["SpringApplication.run(args)"] --> B["ApplicationStartingEvent"]
    B --> C["ApplicationEnvironmentPreparedEvent"]
    C --> D["ApplicationContextInitializedEvent"]
    D --> E["ApplicationPreparedEvent"]
    E --> F["refresh ApplicationContext"]
    F --> G["ApplicationStartedEvent"]
    G --> H["AvailabilityChangeEvent: LivenessState.CORRECT"]
    H --> I["ApplicationRunner / CommandLineRunner"]
    I --> J["ApplicationReadyEvent"]
    J --> K["AvailabilityChangeEvent: ReadinessState.ACCEPTING_TRAFFIC"]

    B -. "If startup fails" .-> X["ApplicationFailedEvent"]
    E -. "If startup fails" .-> X
    F -. "If startup fails" .-> X
    G -. "If startup fails" .-> X
    I -. "If startup fails" .-> X
    J -. "If startup fails" .-> X
~~~

This is a summary diagram: `ApplicationFailedEvent` is published along the **startup failure path**, not as a mandatory step after every milestone; the diagram also omits `ContextRefreshedEvent`, web server events, bean post-processors, and other internal steps.

Key milestones to understand:

- `ApplicationStartingEvent`: very early, before regular processing starts, except listener/initializer registration.
- `ApplicationEnvironmentPreparedEvent`: `Environment` is prepared for the context, but the context has not been created yet.
- `ApplicationContextInitializedEvent` and `ApplicationPreparedEvent`: the context is prepared and bean definitions are loaded step-by-step, still before refresh.
- `ApplicationStartedEvent`: **after context refresh** yet **before** `ApplicationRunner` / `CommandLineRunner`.
- After started, Boot publishes an availability event marking `LivenessState.CORRECT`.
- `ApplicationReadyEvent`: **after runners complete**; after this event, Boot publishes `ReadinessState.ACCEPTING_TRAFFIC`.
- `ApplicationFailedEvent`: published when an exception causes startup to fail.

### Errors at Different Milestones Have Different Consequences

| Failure location | Is the context refreshed? | What you should not expect |
| --- | --- | --- |
| `ApplicationStartingEvent` listener | Not yet | Cannot inject beans from a context that does not exist yet |
| `ApplicationEnvironmentPreparedEvent` listener | Not yet | Cannot rely on a regular `@Component` to catch this failure |
| `ApplicationPreparedEvent` listener | Refresh not complete yet | Cannot treat beans and infrastructure as ready yet |
| `@EventListener` for `ContextRefreshedEvent` | Completing refresh | Cannot assume startup has reached `ApplicationStartedEvent` |
| `@EventListener` for `ApplicationStartedEvent` | Refreshed | Runners may not have run yet; readiness is not accepting yet |
| `ApplicationRunner` / `CommandLineRunner` | Refreshed | May already be live, yet not ready |
| `@EventListener` for `ApplicationReadyEvent` | Refreshed, runners complete | Standard readiness accepting event is not necessarily published if a ready listener fails |

A synchronous listener throwing an exception at started can prevent Boot from running subsequent runners. A synchronous listener throwing an exception at ready runs after runners have executed, yet can still cause `SpringApplication.run(...)` to report failure and block the normal readiness-accepting publication path.

**Liveness and readiness are distinct states.** When a failure happens after started, the application may already have published `LivenessState.CORRECT` without reaching `ReadinessState.ACCEPTING_TRAFFIC`. Do not equate "already live" with "startup succeeded completely."

## 3. Why Do Exceptions Usually Propagate Back to SpringApplication?

On the default path, the publisher emits an event to eligible listeners. `SimpleApplicationEventMulticaster` can call each listener on the same thread; if a listener throws an exception not handled by an error handler, the call stack receives the exception back.

~~~mermaid
sequenceDiagram
    participant Boot as SpringApplication
    participant Bus as ApplicationEventMulticaster
    participant L as StartupListener
    participant Fail as Startup failure handling

    Boot->>Bus: publish ApplicationStartedEvent
    Bus->>L: onApplicationEvent(event)
    L--xBus: throw IllegalStateException
    Bus--xBoot: exception propagates
    Boot->>Fail: handle startup failure
    Fail->>Bus: publish ApplicationFailedEvent (if possible)
    Boot-->>Boot: run does not complete successfully
~~~

This models synchronous listeners under default settings, not the exact method-by-method implementation across every version. With a custom `ErrorHandler`, `TaskExecutor`, `@Async`, or another multicaster mechanism, error propagation behavior can differ.

### Exceptions Worth Classifying

- **`IllegalStateException` or `IllegalArgumentException` from a listener:** validation failure or unmet invariant; can intentionally halt startup.
- **`BeansException`, such as `BeanCreationException`:** a dependency could not be instantiated or injected; inspect nested causes. Do not assume every stack trace mentioning `ApplicationEvent` originated inside a listener.
- **IOException or HTTP timeout from a listener's own call:** an I/O failure may only come from logging, audit, or telemetry; assess whether it truly must gate whether the app serves traffic.
- **Fatal errors such as `OutOfMemoryError`:** never swallow with `catch (Throwable)` to try keeping an unreliable process starting up.

Java checked exceptions do not automatically turn into one uniform Spring Boot error: annotation listeners/reflection may wrap exceptions depending on the API. When diagnosing, follow the **root cause** down the chain rather than relying on the outermost exception name.

### ApplicationFailedEvent Is for Observing, Not "Reversing" Startup Failure

`ApplicationFailedEvent` carries the exception and whatever context may exist depending on when failure occurred. It is useful for recording diagnostics or sending a brief failure signal. It is **not** a hook for marking the application successful again by swallowing the exception; on the failure path, the context may not have been created or may already be closing.

Listeners for failure events must stay minimal and safe, because error handling itself should not throw another exception that obscures the original cause. At very early stages, loggers, beans, or resources you expect may not be prepared yet.

## 4. Which Listener to Register at Which Time?

### A. Early Listeners: SpringApplication.addListeners

Some events fire before `ApplicationContext` exists, so you **cannot** rely on a `@Component` / `@Bean` to catch them. Programmatic registration is explicit:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

// Inside main():
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners((ApplicationListener<ApplicationFailedEvent>) event ->
        System.err.println("STARTUP_FAILED_EVENT"));
app.run(args);
~~~

This is an illustrative snippet; `MyApplication` must be the project's actual startup configuration class, and the code must sit inside an appropriate method. The listener is attached **before calling `run`**, giving it a chance to observe failures even when the context fails to initialize completely. Do not inject beans into this anonymous listener and assume beans exist in every phase.

Early listeners can also be registered via `SpringApplicationBuilder.listeners(...)` or `META-INF/spring.factories` metadata with key `org.springframework.context.ApplicationListener` for Boot to auto-load per documented mechanisms. Do not write a bean definition and wait for it to receive `ApplicationStartingEvent`.

### B. Bean Listeners: @EventListener

Once the context is created, bean methods can catch events such as `ApplicationStartedEvent`, `ApplicationReadyEvent`, and most runtime events:

~~~java
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class StartupValidationListener {
    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("STARTED_LISTENER_CALLED");
    }
}
~~~

This bean is discovered by component scanning if its package lies within the scan scope. Do not arbitrarily mark a listener bean as `@Lazy` and expect `@EventListener` methods to be registered at the proper milestone; Spring Framework notes that making listener beans lazy can prevent event listeners from being set up as expected.

### C. How Do ApplicationListener<E> and @EventListener Differ?

`ApplicationListener<E>` is an interface with `onApplicationEvent(E event)`. `@EventListener` marks a method, allowing multiple methods inside one bean. Both participate in Spring's event publishing mechanism; **exception handling depends on dispatch/handler mode**, not solely on listener syntax.

### D. @Order Does Not Solve Startup Failures

`@Order` or `Ordered` helps determine relative order among eligible listeners. It does not turn a mandatory error into a non-critical one. When a synchronous listener throws an unhandled exception, do not assume listeners ordered after it for the same event will still run.

## 5. Rules for Choosing an Error-Handling Strategy

Not every exception should block startup. Distinguish listener intent:

| Purpose | If it fails | Appropriate policy |
| --- | --- | --- |
| Validate mandatory config for the app to run properly | Unfit to serve traffic | Fail-fast with a clear exception stating the cause |
| Load core state required before accepting traffic | Not loaded yet | Block startup/ready via an appropriate hook and clear error |
| Emit auxiliary startup metrics | Monitoring backend temporarily down | Log and ignore when genuinely non-impacting to business logic |
| Send non-critical audit notification | One notification fails | Best effort, with separate retry tracking if needed |
| Record mandatory compliance event before processing data | Cannot record as required | May need to fail startup depending on system spec |
| Warm-up that can run after ready | Warm-up incomplete | Consider a monitored async task; decouple from startup path |
| Clean up resources when startup fails | Cleanup fails | Log secondary error while preserving root cause |

**Rule:** if failing a condition would make the application serve incorrectly or risk data integrity, do not `catch`, print a "warning," and proceed. If the error genuinely belongs to observability or auxiliary utilities, handle it inside the listener so it does not dictate startup fate.

~~~java
@EventListener
public void onStarted(ApplicationStartedEvent event) {
    try {
        telemetryClient.sendStartupNotice();
    } catch (RuntimeException ex) {
        logger.warn("Could not send optional startup notice", ex);
    }
}
~~~

This is a **snippet**, not a full class: it requires `telemetryClient`, `logger`, and imports for `@EventListener`/the event type. It makes sense only when the notification is optional and errors remain observable. Avoid `catch (Exception ignored) { }`, which hides failures without operational evidence.

### Choosing a Better Hook for Long Work

Spring Boot recommends `ApplicationRunner` / `CommandLineRunner` for tasks that must run during startup, rather than placing long tasks in event listeners. Runners execute after `ApplicationStartedEvent` and before `ApplicationReadyEvent`. If a runner throws an exception, startup can still fail; that is intentional behavior when the runner's work is a precondition for readiness.

When readiness needs to wait on external resources, build a process that controls `ApplicationAvailability` and proper health probes; never install an infinitely blocking listener that makes the process appear hung.

## 6. Complete Java 17+ Example: Succeeding Listener vs. Startup-Failing Listener

The example uses Spring Boot 3.5.16, Java 17+, Maven, and only the core starter. There is no web server to minimize noise; startup events still occur in a command-line application. Running in two modes shows the difference when an `ApplicationStartedEvent` listener throws an exception.

Structure:

~~~text
startup-listener-demo/
├── pom.xml
└── src/main/java/com/example/listener/
    ├── ListenerDemoApplication.java
    └── StartupGuardListener.java
~~~

**File `pom.xml`:**

~~~xml
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
    <artifactId>startup-listener-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

**File `src/main/java/com/example/listener/ListenerDemoApplication.java`:**

~~~java
package com.example.listener;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ListenerDemoApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                ListenerDemoApplication.class);

        // Listener attached before run; does not depend on @Component.
        app.addListeners((ApplicationListener<ApplicationFailedEvent>) event ->
                System.err.println("EVENT=FAILED"));

        app.run(args);
    }

    @Bean
    CommandLineRunner runner() {
        return args -> System.out.println("RUNNER=EXECUTED");
    }
}
~~~

**File `src/main/java/com/example/listener/StartupGuardListener.java`:**

~~~java
package com.example.listener;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class StartupGuardListener {

    private final Environment environment;

    public StartupGuardListener(Environment environment) {
        this.environment = environment;
    }

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("EVENT=STARTED");

        boolean fail = environment.getProperty(
                "demo.fail-on-started", Boolean.class, false);

        if (fail) {
            throw new IllegalStateException(
                    "DEMO_STARTUP_GUARD_REJECTED");
        }
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("EVENT=READY");
    }
}
~~~

Here `StartupGuardListener` is a bean instantiated by the container before the started milestone. `@EventListener` catches `ApplicationStartedEvent`, checks the CLI flag via `Environment`, and either returns normally or intentionally throws `IllegalStateException`. The `ApplicationFailedEvent` failure listener is attached via `SpringApplication.addListeners(...)` so it can operate even in phases before the context is ready.

### Building and Running Normally

~~~bash
mvn -q -DskipTests package
java -jar target/startup-listener-demo-0.0.1-SNAPSHOT.jar
~~~

The lines **printed by the example itself**, in order along a successful startup path:

~~~text
EVENT=STARTED
RUNNER=EXECUTED
EVENT=READY
~~~

Spring Boot may print additional logging, including the banner and startup info. Those lines are the listener/runner output, not the entire stdout.

### Triggering an Intentional Failure on ApplicationStartedEvent

~~~bash
java -jar target/startup-listener-demo-0.0.1-SNAPSHOT.jar \
  --demo.fail-on-started=true
~~~

With default synchronous listeners, the lines explicitly printed by the example before/along the failure path are:

~~~text
EVENT=STARTED
EVENT=FAILED
~~~

Spring Boot also logs the startup failure stack trace, in which you can find the message:

~~~text
DEMO_STARTUP_GUARD_REJECTED
~~~

**Expected result:** this `SpringApplication.run(...)` call does not finish successfully; the Java process running from the JAR typically exits with a non-zero exit code after Boot handles the error. `RUNNER=EXECUTED` and `EVENT=READY` are not printed in this branch because the `ApplicationStartedEvent` listener interrupted startup before Boot invoked the runner.

Do not claim stderr contains only a single `EVENT=FAILED` line or that every Boot version wraps the root cause in the exact same wrapper exception type. What must be verified is **the initial cause**, the event sequence, and that the ready branch was not reached.

**Shell note:** the line-continuation character `\` is for Bash/Unix; on PowerShell/cmd, put `java -jar ... --demo.fail-on-started=true` on a single line or use the appropriate line-continuation syntax.

### Reading Output Reliably

In the error log, look for the message `DEMO_STARTUP_GUARD_REJECTED` and the method `StartupGuardListener.onStarted`. They pinpoint the origin. Only afterward look at framework wrapper lines like `Application run failed`. Seeing `EVENT=FAILED` indicates the failure listener was invoked; it does not turn startup back into a success.

## 7. One Small Change, Three Different Error-Handling Policies

Suppose `onStarted(...)` needs to call an auxiliary service:

~~~java
void sendNotification() {
    notificationService.notifyStartup();
}
~~~

This is a conceptual snippet (requiring a valid `notificationService`) that can fit three policies:

**Policy A — fail-fast:** the notification is a mandatory condition before accepting traffic. Let the exception carry a clear message and propagate out to startup; operators must be able to see the cause and fix configuration/service issues.

**Policy B — best effort:** the notification is purely an auxiliary convenience. Catch the task-specific exception, log with non-sensitive context, emit metrics/tracing, and continue. This must not be applied to security checks, schema checks, or core data integrity errors.

**Policy C — decoupled execution:** the notification can be processed after startup in an executor or queue. You then need to define error storage, retry/backoff, idempotency, and resource limits. Never push a mandatory task into async just to "get past startup"; if a guarantee is needed before serving traffic, coordinate readiness explicitly.

### When a Listener Swallows Exceptions Itself

~~~java
@EventListener
public void onStarted(ApplicationStartedEvent event) {
    try {
        updateOptionalDashboard();
    } catch (Exception ex) {
        logger.warn("Optional dashboard update failed", ex);
    }
}
~~~

This illustrative snippet requires `logger` and `updateOptionalDashboard()` supplied by the application. If the dashboard failure is non-essential, this approach is acceptable. If an error could stem from a mandatory invariant and gets caught broadly by `catch (Exception)`, error boundaries have been blurred. Catch appropriate exception types, log clearly, and never hide programming errors accidentally.

### When Adding a Custom ErrorHandler to ApplicationEventMulticaster

Spring Framework allows replacing the context's `ApplicationEventMulticaster`—for instance by providing a bean named `applicationEventMulticaster` and configuring `SimpleApplicationEventMulticaster.setErrorHandler(...)`. The handler can process/log an exception instead of letting it propagate to the publisher.

This is useful in certain **business** event systems, yet it is an infrastructure-level mechanism. It should not be enabled globally to "let all listeners fail while the app keeps running" when listeners contain mandatory startup validations. Moreover, **very early pre-context events** are handled by `SpringApplication`'s listener mechanism, so a custom multicaster bean in the context cannot be assumed to cover every bootstrap event.

When handling auxiliary failures, a local `try/catch` inside the listener is usually clearer than a global handler that alters semantics across the entire application.

## 8. Async Listeners: Errors Might Not Fail run()

Spring Framework supports `@Async` on an `@EventListener` once the application enables appropriate async infrastructure (such as `@EnableAsync` and an executor). Illustrative example:

~~~java
@Async
@EventListener
public void sendOptionalTelemetry(ApplicationStartedEvent event) {
    telemetryClient.sendStartupNotice();
}
~~~

This snippet requires importing `org.springframework.scheduling.annotation.Async` and `org.springframework.context.event.EventListener`, plus a `telemetryClient` collaborator. It is an example of an **auxiliary task**, not a startup guard.

Consequences to understand:
1. For asynchronous event listeners, exceptions from the worker thread **do not automatically propagate** back to the event-publishing caller as with default synchronous listeners.
2. Errors from `void` async methods must be monitored via `AsyncUncaughtExceptionHandler` and appropriate logging/observability.
3. `ThreadLocal` and logging contexts do not transfer to async threads by default; configure correlation/tracing if needed.
4. Do not use the return value of an `@Async @EventListener` method to publish follow-up events; to publish more events, inject `ApplicationEventPublisher` and publish explicitly.
5. Do not assume every platform event and every listener can be handled asynchronously in the same way; certain listeners/events have special execution support rules, especially during bootstrap.

**Startup trap:** if a security configuration check runs inside an async listener, `SpringApplication.run(...)` can reach ready before the check completes or before an error is recorded. For preconditions that must hold before accepting traffic, use synchronous validation or an explicitly designed lifecycle/readiness gate.

## 9. When to Use ApplicationFailedEvent, FailureAnalyzer, and Direct Exceptions?

| Mechanism | Use for | Do not use to |
| --- | --- | --- |
| Throwing exceptions from listener/runner | Blocking startup when critical preconditions are violated | Drive long retry logic by crashing repeatedly |
| `ApplicationFailedEvent` listener | Emitting/capturing a brief, safe startup failure signal | Treat the event as an opportunity to repair a broken context |
| `FailureAnalyzer` | Returning diagnostic messages with clear description/action for recognizable failure types | Auto-fix errors without addressing the root cause |
| `ApplicationAvailability` / readiness | Controlling traffic acceptance while the instance remains live | Replace mandatory startup failure reporting |
| `ApplicationRunner` / `CommandLineRunner` | Startup work after context refresh | Handle very early events before context creation |

### Which Startup Failures Can ApplicationFailedEvent Catch?

For example, errors during bean creation, context refresh, runners, or synchronous listeners can enter Boot's failure-handling path. An early-registered failure listener can observe `ApplicationFailedEvent`, though it must not rely on using every bean or context at that moment.

If an **`ApplicationFailedEvent` listener itself** throws an exception, error handling can add noise or complicate analysis. Failure-event handlers should therefore avoid mandatory network calls, avoid fetching uncertain beans, and never mask the root cause.

### How Does FailureAnalyzer Differ from ApplicationFailedEvent?

`FailureAnalyzer` focuses on translating an exception type into an actionable message—for example, "port could not be bound because another process is using it." `ApplicationFailedEvent` notifies that startup failed and provides the exception; it does not generate tailored remediation by itself. Use a failure analyzer when building a library/framework with recurring configuration errors where users need clearer guidance.

## 10. Diagnosing Listener Failures in Practice

### Case A: Startup Fails at ApplicationEnvironmentPreparedEvent

**Symptom:** logs report an exception while bootstrapping the Environment, no beans/controllers exist yet, and `@Component`-declared listeners are not called.

**Resolution:** check listeners registered via `addListeners` or `spring.factories`, `PropertySources`/config data ordering, and property reads. Never call `ApplicationContext.getBean(...)` before the context exists. For early configuration, use Boot-supported hooks rather than forcing arbitrary logic into a listener without understanding bootstrap order.

### Case B: @EventListener on ApplicationStartedEvent Prevents Runners from Executing

**Symptom:** logs show started followed by a listener error, with no runner or ready logs.

**Resolution:** read the listener stack trace and classify the exception as a mandatory precondition or auxiliary error. If mandatory, fix the cause and let it fail fast. If auxiliary, place error handling at that task's boundary; do not abuse a global multicaster ErrorHandler.

### Case C: ApplicationReadyEvent Listener Throws an Error

**Symptom:** runners ran and related ready logs appeared, yet startup still fails and readiness probes do not transition to accepting.

**Resolution:** read the `ApplicationReadyEvent` listener stack trace. Do not assume "ready was published" means every ready callback succeeded. If work must be done before ready, place it in an appropriate runner/lifecycle hook; if auxiliary, handle it independently with monitoring.

### Case D: Exception Appears in Async Logs While Startup Still Succeeds

**Symptom:** the application is ready, and an error appears later on an executor thread.

**Resolution:** inspect `@Async`, the executor, `AsyncUncaughtExceptionHandler`, or `ErrorHandler`. Locate where errors are recorded and observed; check whether the async task truly belongs outside the startup path. Do not conclude Spring "swallowed" an error if the application itself configured async/best-effort handling.

### Case E: ApplicationFailedEvent Fires, Yet Logs Lack Root Cause

**Symptom:** only a generic `Application run failed` message or wrapper exception appears.

**Resolution:** expand the full cause chain, find `Caused by`, and locate the first application-owned listener method. `ApplicationFailedEvent.getException()` is a sensible starting point though it may hold wrappers; never print only `getMessage()` and discard the stack trace. If configuration contains credentials, redact sensitive values in logs.

### Case F: A Listener Runs Twice in a Context Hierarchy

In Spring, events from a child context can propagate up to the parent, so a parent listener may see multiple events of the same type. Compare the event's context against the context managed by the listener when filtering is needed. Do not mistake repeated events for listener exceptions or automatic retries.

### Case G: Listener Exception Does Not Surface in SpringApplication.run

Verify whether startup actually published the event, whether the listener runs asynchronously, whether a custom multicaster has an `ErrorHandler`, and whether an internal try/catch absorbed the error. If the event was published **after startup completed**, there is not necessarily a `SpringApplication.run` call stack left to bubble the error back to.

## 11. Testing and Operational Recommendations

Scenarios worth intentionally testing for listeners capable of blocking startup:

- **Happy path:** listener runs normally; startup progresses through runners and ready.
- **Fail-fast path:** trigger a deterministic failure condition; verify exception/root cause, verify ready is not reached, and verify build/deployment receives startup failure.
- **Best-effort path:** auxiliary telemetry dependency fails; app still reaches ready, and error logs/metrics contain actionable details.
- **Async path (if used):** errors are captured by executor/handler; do not expect a synchronous publisher to catch exceptions.
- **Early-failure path:** if pre-context listeners exist, verify failure reporting works even before beans/container exist.

You can use `@SpringBootTest` or launch `SpringApplication` in an appropriate integration test to verify events and failures; if using `ApplicationContextRunner`, understand that it initializes contexts in its own way and **does not automatically simulate the entire `SpringApplication.run` event sequence**. To verify `ApplicationStartedEvent` / `ApplicationFailedEvent` accurately at the Boot level, test through the actual startup path or a controlled `SpringApplication` harness.

In deployment environments:
- Distinguish **exit code/startup failed** from **readiness unhealthy** and **liveness broken**.
- Configure restart/backoff policies so a configuration failure does not trigger a tight pointless crash loop.
- Avoid logging secrets from `Environment` or CLI arguments when recording diagnostics.
- Monitor startup listener latency; long tasks or blocking I/O on the event thread increase deploy and recovery times.
- With Spring Security/web servers, a listener startup error can close the context after web infrastructure partially initialized; do not infer from a "server started" log alone that all of `run(...)` succeeded.

## 12. Symptom-to-Decision Summary

| Observation | First question | Priority action |
| --- | --- | --- |
| `ApplicationStartedEvent` listener throws error | Is the failure a mandatory precondition? | Fail fast if so; fix root cause |
| Runners do not execute | Was there an exception at started or earlier? | Inspect the exception and listener location |
| `ApplicationReadyEvent` appears yet app still fails | Did a ready listener throw an exception? | Identify the failing callback; check final readiness |
| `ApplicationFailedEvent` is published | What is the root exception? | Follow the cause chain and classify the phase |
| Startup succeeds despite listener error | Async, ErrorHandler, or internal catch? | Verify dispatch policy and observability |
| Need to observe errors before context | Was the listener registered before `run`? | `SpringApplication.addListeners` / `spring.factories` |
| `@Component` listener for `ApplicationStartingEvent` never runs | Did the context exist when the event fired? | Move registration to an early mechanism |
| Liveness CORRECT yet not accepting traffic | Have runners/ready finished? | Check readiness; do not infer from liveness |
| Listener runs long, startup is slow | Is there network/blocking work inside the listener? | Move to a runner or monitored job |
| Logger inside failure listener also errors | Did it rely on an uninitialized context? | Reduce failure handler dependencies; preserve root cause |

## 13. Self-Check Questions

**1. A synchronous `@EventListener(ApplicationStartedEvent)` throws an uncaught `IllegalStateException`. Does Boot still run subsequent runners?**  
No. The exception can halt startup before the runner step, and Spring Boot transitions into failure handling.

**2. Why should you not use a `@Component` bean to catch `ApplicationStartingEvent`?**  
That event is published before the context exists. Register the listener with `SpringApplication`/supported metadata before `run`.

**3. Does `ApplicationFailedEvent` automatically recover a failed startup context?**  
No. It serves to signal/observe failure. Fix the underlying error and restart according to your operational workflow.

**4. With `@Async @EventListener`, do exceptions automatically propagate back to the event-publishing thread?**  
Not via the synchronous default; you need appropriate monitoring, handlers, or future handling.

**5. Should you use a global ErrorHandler to ignore all startup listener exceptions?**  
No. It can mask mandatory preconditions; consider it only when you understand its scope and consequences across the event multicaster.

**6. Why can an `ApplicationStartedEvent` listener run while readiness is still refusing?**  
Started is published after refresh yet before runners. Standard readiness accepting is published only after the ready event.

**7. Can an `ApplicationReadyEvent` listener throwing an exception prevent readiness accepting from being published?**  
Yes. The ready event is published before availability accepting; a synchronous error can fail the startup path.

**8. What is the best way to produce an actionable failure message for framework exception types?**  
Implement an appropriate `FailureAnalyzer`; the failure event itself only delivers the failure facts.

**9. When you see a wrapper exception, what should you read?**  
The root cause, stack trace, and original listener method, rather than reading only `Application run failed`.

**10. When startup telemetry fails without impacting business logic, what should you do?**  
Catch/log the error at the telemetry boundary or isolate it into a monitored job; the application does not necessarily need to fail over auxiliary tasks.

## Official References

- [Spring Boot — SpringApplication, Application Events and Listeners](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html)
- [Spring Boot — Application Startup Failure](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html#features.spring-application.startup-failure)
- [Spring Framework — ApplicationContext Events, @EventListener and Async Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Boot — ApplicationFailedEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html)
- [Spring Boot — FailureAnalyzer API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/diagnostics/FailureAnalyzer.html)
- [Maven Central — spring-boot-starter-parent 3.5.16](https://central.sonatype.com/artifact/org.springframework.boot/spring-boot-starter-parent/3.5.16)

Details regarding the dispatcher, async support, and error handlers depend on version and configuration. Verify the exact Spring Boot/Spring Framework versions in your dependency tree before changing exception policies in startup listeners.