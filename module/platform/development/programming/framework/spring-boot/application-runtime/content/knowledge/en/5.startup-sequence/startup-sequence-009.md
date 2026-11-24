# Failure Branches and Cleanup When the Spring Boot Startup Sequence Is Interrupted

## 1. The Problem to Understand

A single call to **SpringApplication.run(...)** goes through many stages: preparing **Environment**, building **ApplicationContext**, loading bean definitions, **refresh**, starting web infrastructure or background components, executing **ApplicationRunner/CommandLineRunner**, and only then announcing the application is ready. An exception at any stage can cause the startup run to fail.

Analyzing a startup failure requires answering four questions: **which stage did the failure occur in**, **does the context already exist / has refresh finished**, **which resources were created and who owns them**, and **does the calling system detect the failure via logs, readiness, or exit code**.

An application may already have bound an HTTP port or logged "Started ..." while runners have not yet finished. A context may have been created yet not be safe enough to retrieve beans from. Conversely, some failures occur before the context even exists. Therefore, no single generic cleanup callback can guarantee cleaning up every resource across all scenarios.

## 2. Map of the Startup Stages

Spring Boot publishes key events in a typical logical order:

1. **ApplicationStartingEvent**: application starts; neither Environment nor ApplicationContext exists yet.
2. **ApplicationEnvironmentPreparedEvent**: Environment has been prepared at an appropriate level, before context creation.
3. **ApplicationContextInitializedEvent**: context has been created and initializers have run; bean definitions are not yet fully loaded.
4. **ApplicationPreparedEvent**: context has been prepared and bean definitions loaded, yet not refreshed.
5. **Context refresh**: Spring finalizes the bean factory, dependency injection, non-lazy singletons, initialization callbacks, and related infrastructure. For web apps, the web server is typically set up during this process.
6. **ApplicationStartedEvent**: context has refreshed successfully; startup runners have not run yet.
7. **AvailabilityChangeEvent (LivenessState.CORRECT)** occurs along the default event sequence.
8. **ApplicationRunner/CommandLineRunner**: startup tasks to run at startup are invoked.
9. **ApplicationReadyEvent**: runners complete successfully.
10. **AvailabilityChangeEvent (ReadinessState.ACCEPTING_TRAFFIC)**: application announces it is ready to accept traffic.

When an exception interrupts **SpringApplication.run(...)**, Spring Boot switches to the failure-handling path, usually publishing **ApplicationFailedEvent**. Events situated after the failure point on the success path are not guaranteed to occur.

~~~text
STARTING
   |
   v
ENVIRONMENT -> CREATE CONTEXT -> PREPARE -> REFRESH
    |                 |             |          |
    +-----------------+-------------+----------+---> FAILURE
                                                   |
                         STARTED -> RUNNERS -> READY
                             |          |
                             +----------+------------> FAILURE
~~~

This is a conceptual diagram, not a mandatory line-by-line log sequence. **ApplicationFailedEvent** is a signal of startup failure; by itself it does not prove all resources have been cleaned up.

## 3. Failure Branches and Consequences

| Timing | Example cause | Context state | What to watch out for |
| --- | --- | --- | --- |
| Before Environment preparation | Exception in `main` code or bootstrap listener | May not exist yet | Clean up externally allocated resources yourself |
| Environment/config | Config loading error, invalid property, or unreachable config source | May not exist yet | Do not rely on `@PreDestroy` of uncreated beans |
| Creating/preparing context | Initializer throws exception, early config error | May exist, not yet refreshed | Do not assume `getBean(...)` can be called |
| During refresh | `BeanCreationException`, dependency injection, singleton init failure, web port occupied | Created, yet refresh failed | Spring destroys managed singletons; check resources outside the container |
| After refresh, before ready | `ApplicationRunner`/`CommandLineRunner` throws exception | Context refreshed | Spring Boot handles failure and closes context; matching destroy callbacks run |
| After ready | HTTP request, consumer, or background scheduler fails | Context running | Usually a runtime error; handle per request/event and operational policy |

### 3.1. Before `ApplicationContext` Exists

In very early failures, **ApplicationFailedEvent.getApplicationContext() may be null**. Because the container has not been fully built yet, an **@EventListener** inside a bean cannot be relied upon to catch all pre-startup failures. If you manually open a socket, file, or thread directly in `main` or before calling `run(...)`, use **try/finally** or **try-with-resources** within the scope that owns that resource.

Do not call **context.getBean(...)** inside an error-reporting listener if the context is null or unrefreshed. Do not try to "continue" startup in an unverified state.

### 3.2. Context Refresh Fails

During refresh, Spring may already have instantiated singletons and opened connection pools, web servers, executors, or resources. If a subsequent step throws an exception, Spring Framework runs its destruction path for singletons already created and managed by the container. Spring Boot then proceeds to handle the startup failure.

However:

- **@PreDestroy**, **DisposableBean.destroy()**, and **@Bean(destroyMethod=...)** depend on the bean having been created and properly registered in the lifecycle.
- If a **constructor or factory method** opens a resource and then throws an exception before returning the finished bean, the container may not yet hold that resource to invoke destroy on it.
- Resources created in static initializers, self-started threads, or objects instantiated outside Spring must have their own closing mechanism.
- If the error is caused by an occupied web port, resolve the port conflict or fix configuration; do not swallow the exception to declare a service ready without a server.

### 3.3. Runner Fails After Refresh

**ApplicationStartedEvent** is published before invoking startup runners. If a **CommandLineRunner** or **ApplicationRunner** throws an exception:

- Context refresh succeeded, yet **ApplicationReadyEvent** does not appear on the success branch.
- Spring Boot performs failure handling and closes the context created during that startup run.
- Destruction callbacks for resource-managing beans execute as appropriate.
- Side effects already created by the runner outside Spring (DB writes, sent messages, created files, API calls) **do not automatically roll back merely via `context.close()`**.
- The web server may already have opened its port during the window before the error; proper **readiness** is needed so traffic is not routed while startup is incomplete.

### 3.4. Errors After the Application Is Ready

An HTTP request throwing an exception, a failing background scheduler task, or a consumer failing to process a message **does not by default become a startup failure**. **ApplicationFailedEvent is not a catch-all sink for every runtime exception**.

Use per-request/event error-handling policies: exception handlers, retry/backoff, transactions, dead-letter queues, timeouts, health/readiness, and monitoring. Only terminate the entire process if the failure leaves the application unable to operate and operational policy requires it.

## 4. How Spring Boot Reports Startup Failures

**ApplicationFailedEvent** signals that `SpringApplication` did not complete startup; the event carries the exception and the context being created **if available**. Its goal is recognizing a failed startup run, recording minimal telemetry, or aiding diagnostics.

**FailureAnalyzer** processes recognized exceptions to provide descriptions and corrective actions, such as **port 8080 already in use**. Output can be presented via **FailureAnalysisReporter**. Not every exception has a FailureAnalyzer, and an analyzer **does not fix errors automatically**.

| Mechanism | Role | What cannot be assumed |
| --- | --- | --- |
| `ApplicationFailedEvent` | Startup failure signal | Context is always non-null or all cleanup has completed |
| `FailureAnalyzer` | Translates exceptions into root cause and remediation hints | Automatic retry or config repair |
| Error log and cause chain | Diagnoses the actual error source | The outermost log is always the root cause |
| `@PreDestroy`, `DisposableBean`, `destroyMethod` | Cleans up managed beans | Cleans up partially constructed objects and non-Spring resources |
| `try/finally`, `try-with-resources` | Closes resources within the allocating scope | Replaces the entire container lifecycle |
| Exit code and workload status | Reports failure to parent process, CI, or scheduler | Conveys full business root causes |

### Listeners Must Be Registered Early Enough

Events prior to context creation cannot be reliably received by listeners registered only as beans. If you need to observe startup failures early, attach a listener via **SpringApplication.addListeners(...)** before **run(...)**, or via a Spring Boot-supported early listener registration mechanism.

Listeners should be concise, tolerate a null context, avoid opening new hard-to-close resources, avoid logging sensitive data, and avoid long network I/O. If a listener fails while reporting an error, recovery becomes even harder.

## 5. Designing Cleanup at the Right Ownership Level

### 5.1. Letting Spring Manage Resource-Holding Beans

When a resource is created and lives alongside the context, register an explicit callback:

~~~java
@Bean(destroyMethod = "close")
MyClient myClient() {
    return new MyClient();
}
~~~

**This is illustrative code**: `MyClient` is a hypothetical domain type with a `close()` method; it is not a standalone program. Depending on the resource, you can use **@PreDestroy**, **DisposableBean**, or **SmartLifecycle**. Do not register multiple overlapping close mechanisms for the same resource if closing is not idempotent.

**Important condition:** the container only manages a bean once creation succeeds sufficiently. A partially constructed bean may already have caused side effects without yet being fully managed by Spring.

### 5.2. Cleaning Up Yourself If Creation Fails Midway

Suppose a factory method opens a connection and then continues configuring it; if the configuration step fails, close the opened resource right there:

~~~java
Resource resource = openResource();
try {
    configureResource(resource);
    return resource;
} catch (RuntimeException | Error failure) {
    try {
        resource.close();
    } catch (Exception closeFailure) {
        failure.addSuppressed(closeFailure);
    }
    throw failure;
}
~~~

**This is Java pseudocode**, as `Resource`/`openResource`/`configureResource` represent application-specific APIs. It illustrates an important rule: **do not wait for Spring to call `destroyMethod` if the factory method has not returned the bean successfully**. When cleanup also fails, use **addSuppressed(...)** to preserve the original exception.

If a resource is managed by **try-with-resources**, prefer that form whenever ownership does not need to be handed off to Spring or another object.

### 5.3. Technical Cleanup Differs From Business Rollback

Closing **ApplicationContext**, connection pools, or executors does not undo every external side effect. If a startup runner already wrote data, sent Kafka events, called APIs, or created files before failing, retries can produce duplicate effects.

Apply proper transaction boundaries, outbox patterns, idempotency keys, checkpoints, and compensating workflows where appropriate. Do not delete data merely to "clean up an error" if another system has already consumed that data. Rollback decisions must follow business contracts.

### 5.4. Avoiding `System.exit` Inside Beans

A bean calling **System.exit(0)** on error can trick orchestrators into thinking startup succeeded while bypassing SpringApplication-level failure reporting. Let errors that must fail startup propagate and be reported clearly. For CLI jobs needing custom exit codes, use **ExitCodeGenerator**, **ExitCodeExceptionMapper**, or **SpringApplication.exit(...)** in a scope matching the process contract.

## 6. Spring Boot 3.x / Java 17+ Example: Two Reproducible Failure Branches

The following example is **a standalone Spring Boot 3.x application** using Java 17+ and the **spring-boot-starter** dependency. Create **`src/main/java/example/StartupFailureDemo.java`**:

~~~java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class StartupFailureDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(StartupFailureDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        app.addListeners((ApplicationListener<ApplicationFailedEvent>) event -> {
            System.out.println("EVENT_FAILED");
            System.out.println("CONTEXT_PRESENT="
                    + (event.getApplicationContext() != null));
        });

        // Only assigned when SpringApplication.run(...) succeeds.
        ConfigurableApplicationContext context = app.run(args);
        context.close();
    }

    @Bean(destroyMethod = "close")
    DemoResource demoResource() {
        return new DemoResource();
    }

    @Bean
    StartupGuard startupGuard(DemoResource resource, Environment environment) {
        String phase = environment.getProperty("demo.fail-phase", "none");
        if ("refresh".equals(phase)) {
            throw new IllegalStateException("demo refresh failure");
        }
        return new StartupGuard();
    }

    @Bean
    CommandLineRunner startupWork(
            StartupGuard guard, Environment environment) {
        return args -> {
            System.out.println("RUNNER_ENTER");
            String phase = environment.getProperty("demo.fail-phase", "none");
            if ("runner".equals(phase)) {
                throw new IllegalStateException("demo runner failure");
            }
        };
    }

    static final class StartupGuard {
    }

    static final class DemoResource implements AutoCloseable {
        DemoResource() {
            System.out.println("RESOURCE_OPEN");
        }

        @Override
        public void close() {
            System.out.println("RESOURCE_CLOSE");
        }
    }
}
~~~

The model is structured to observe the lifecycle:

- **DemoResource** is initialized as a bean with **destroyMethod="close"**.
- **StartupGuard** depends on `DemoResource`, so the resource is created before checking the **refresh** failure branch.
- **startupWork** depends on `StartupGuard`, so the runner only executes if refresh succeeds.
- The **ApplicationFailedEvent** listener is attached directly to `SpringApplication` before **run(...)**.
- **context.close()** in `main` runs only when **run(...) returns successfully**. On the failure path, Spring Boot handles and closes the context via its startup failure mechanism.

### Running Experiments

The project uses the Spring Boot Gradle plugin; the corresponding commands are:

~~~bash
./gradlew bootRun
./gradlew bootRun --args="--demo.fail-phase=refresh"
./gradlew bootRun --args="--demo.fail-phase=runner"
~~~

On Windows PowerShell, replace **./gradlew** with **.\gradlew.bat**.

### What to Look For in Logs/Stdout

| Mode | Signals printed by our code | What is proven |
| --- | --- | --- |
| `demo.fail-phase` not specified | `RESOURCE_OPEN`, `RUNNER_ENTER`, `RESOURCE_CLOSE` | Refresh/runner succeeded; `main` closed context |
| `demo.fail-phase=refresh` | `RESOURCE_OPEN`, `RESOURCE_CLOSE`, `EVENT_FAILED` | Bean failed during refresh; runner was not called |
| `demo.fail-phase=runner` | `RESOURCE_OPEN`, `RUNNER_ENTER`, `EVENT_FAILED`, `RESOURCE_CLOSE` | Refresh finished, runner threw exception; startup failure occurred |

**The table lists the lines expected to appear, without imposing a strict absolute order across every line.** On the refresh branch, Spring Framework may destroy already-created beans while aborting refresh before the failure listener is invoked. Spring Boot/Gradle logs and stack traces may interleave; there is no single fixed stdout.

**`RESOURCE_CLOSE` on the refresh branch** shows that **DemoResource** was already successfully managed before **StartupGuard** failed. It does not prove Spring will automatically clean up every resource partially created by a failing constructor.

**`EVENT_FAILED` on the runner branch** occurs even though the context already refreshed. **ApplicationStartedEvent** may already have been published, yet **ApplicationReadyEvent** is not published on the success branch.

### Deeper Verification

For automated testing, you can add early-registered listeners for **ApplicationStartedEvent** and **ApplicationReadyEvent**, and verify a failing runner does not publish ready. Beyond logs, confirm resources actually release: connection pools return connections, sockets no longer hold ports, executors shut down, and background threads do not block JVM exit.

Do not use this example to evaluate DB/message rollbacks: it only creates a dummy resource and throws intentional exceptions.

## 7. Readiness, Liveness, and Graceful Shutdown

**Liveness** indicates the application remains in a baseline state considered alive; **readiness** indicates the instance can receive traffic. Per Spring Boot's event sequence, readiness is usually published as **ACCEPTING_TRAFFIC after startup runners complete**. The web server binding a port does not mean the instance is ready.

When a normally running service receives a stop signal, graceful shutdown can be used on supported web infrastructure:

~~~yaml
server:
  shutdown: graceful
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

However, a **startup failure** can happen before beans, lifecycle processors, or the web server finish initializing. Therefore, do not assume every graceful shutdown procedure of an already-ready service applies unchanged when refresh fails. Cleanup depends on the stage that failed.

**ApplicationFailedEvent** is a failure diagnostic signal; **@PreDestroy** is a bean cleanup mechanism; **graceful shutdown** is a controlled stop policy. They solve different parts of the problem.

## 8. Exit Codes and Operations When Startup Fails

For CLIs/jobs, **exit code 0** typically means success and a **non-zero code** means failure. Unhandled startup exceptions normally fail the Java process, yet you must ensure non-container threads do not keep the JVM alive and that wrappers/IDEs/Gradle propagate the right exit code.

For services, never catch initialization errors and pretend to run normally. An unready service must be marked unready or fail startup so the scheduler/container orchestrator acts according to policy.

Design mistakes that cause serious trouble:

- **Catching exceptions in a runner without rethrowing**, allowing Spring to proceed to `ApplicationReadyEvent` even though mandatory initialization failed.
- **Calling `System.exit(0)` in a catch block**, masking startup errors.
- **Throwing a new exception while dropping the cause**, losing the real root error.
- **Infinite retries directly during startup**, holding readiness in a waiting state and hammering dependencies; use finite timeouts and backoff.
- **Spawning raw threads without a stop mechanism**, keeping the JVM alive after startup fails.
- **Confusing context close with business rollback**, leading to duplicate messages, duplicate records, or unreverted external side effects.
- **Using readiness for per-request business errors**, causing a single HTTP 500 request to be misinterpreted as the entire application being dead.

When an operation in a runner is a mandatory prerequisite for the service to receive traffic, let failures surface during startup. If work can run after the service is ready, design a separate background flow, health check, and monitoring for it.

## 9. Practical Failure Investigation Workflow

1. **Read the root exception** in the cause chain; distinguish wrappers like `BeanCreationException` from real causes (port, binding, dependency, connectivity).
2. **Identify the last completed stage** from events/logs: Environment, ContextPrepared, refresh, `ApplicationStartedEvent`, runner, `ApplicationReadyEvent`.
3. **Inspect `FailureAnalysis`** if present. For example, a port-already-in-use error requires resolving the conflict or configuration, not swallowing the exception.
4. If auto-configuration condition details are needed, enable **--debug** for a diagnostic startup run or DEBUG level for **ConditionEvaluationReportLoggingListener**. Avoid exposing secrets when sharing logs.
5. **Check bean/resource cleanup**: did destroy callbacks run, do sockets/threads/executors remain alive, are there partially created or non-container resources?
6. **Cross-check external side effects**: did the DB commit, did an API receive a request, was a message sent, was a file written; prepare appropriate retry/idempotency handling.
7. **Verify operational status**: correct exit code, unready instance receives no traffic, errors are not hidden by wrappers.
8. **Re-run in a controlled way** on both success and failure branches, observing resource release.

| Question | What to clarify |
| --- | --- |
| Does the context exist and has refresh finished? | Whether bean lifecycles are usable and which startup step was reached |
| Is `ApplicationStartedEvent` present while `ApplicationReadyEvent` is missing? | Check runners or post-refresh failures |
| Was the resource fully created or partially constructed? | Distinguish container cleanup from local cleanup |
| Does the bean have the right destroy method/`@PreDestroy`? | Verify the Spring-managed lifecycle portion |
| Did the error occur after `ApplicationReadyEvent`? | Handle as runtime rather than misclassifying as startup |
| Did DB/broker/file side effects already happen? | Evaluate rollback, idempotency, checkpoints |
| Are non-Spring threads keeping the JVM alive? | Check shutdown of custom executors/workers |

## 10. Misconceptions to Avoid

**"`ApplicationFailedEvent` always has a context."** False; early failures can occur before the context is created.

**"`@PreDestroy` always runs for any opened resource."** False; the resource must be properly registered in a bean's lifecycle or cleaned up locally where allocated.

**"Seeing `ApplicationStartedEvent` means the app is ready."** False; this event occurs before startup runners.

**"Closing `ApplicationContext` deletes or rolls back external data."** False; `context.close()` does not automatically undo files, messages, or API calls.

**"An HTTP request error after ready always publishes `ApplicationFailedEvent`."** False; that is normally a runtime error with its own handling flow.

**"Enabling graceful shutdown means any refresh failure cleans up perfectly."** False; the context state may not be complete yet.

**"Catching exceptions to keep the app alive improves resilience."** Only true when the failure is genuinely tolerable; if a mandatory dependency failed, reporting ready can lead to corrupted processing.

## 11. Self-Check

1. **Bean A opens a connection successfully; Bean B fails during refresh.** Spring can destroy A if A is properly container-managed; partially created resources in B require local cleanup.
2. **`ApplicationStartedEvent` fired, yet `CommandLineRunner` throws an exception.** Startup still fails; `ApplicationReadyEvent` does not appear on the success branch.
3. **Failure in Environment before context creation.** Do not assume a listener can retrieve beans via DI.
4. **An HTTP request returns 500 after the service is ready.** Usually a request/runtime error, not automatically a startup failure.
5. **A runner creates a file and then throws an exception.** Closing the context does not automatically delete the file; handle according to business policy.
6. **The port is already listening while readiness is not yet `ACCEPTING_TRAFFIC`.** Entirely possible; wait for startup runners to complete.

**Remember:** To handle a startup failure properly, you must know **where in the startup sequence the error occurred, which beans are already managed by Spring, and which side effects still live outside Spring**. Combine bean destruction callbacks with `try/finally` for partially constructed resources, report errors honestly, and deliberately test the failure branch.

### References

- [Spring Boot — SpringApplication: Startup Failure and Application Events](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot — ApplicationFailedEvent API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html)
- [Spring Framework — Bean Lifecycle and Context](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
