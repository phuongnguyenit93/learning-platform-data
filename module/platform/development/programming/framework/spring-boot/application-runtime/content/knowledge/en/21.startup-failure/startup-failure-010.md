# Releasing Resources and Returning Exit Codes on Spring Boot Startup Failure

## 1. Why do startup failures need two independent mechanisms?

When a Spring Boot application fails to start, at least **two consequences** must be handled properly:

1. **Resources allocated** during startup stages prior to the error must be cleaned up: connections, threads, executors, file handles, sockets, message consumers, temporary files, subscriptions, and external resources.
2. **The process must signal failure status** to the shell, CI/CD, container orchestrator, or job scheduler with a **non-zero exit code**, when the app runs under that process/CLI model.

These two concerns are related yet **not identical**:

- A log line saying `APPLICATION FAILED TO START` does not mean every resource has been cleaned up.
- Running `@PreDestroy` does not automatically guarantee the JVM returns the right exit code.
- Calling `System.exit(1)` is not a resource cleanup strategy: it can cause cleanup steps the normal flow would run to be skipped.
- `SpringApplication.exit(context)` is not an "alternative exit" when `SpringApplication.run()` already threw an exception before returning a context.

In Spring Boot 3.3.x / Spring Framework 6.1.x and Java 17+, a sound strategy is:

**Let Spring manage the lifecycle of properly registered resources; use `try/finally` or `try-with-resources` for resources outside the container; throw exceptions expressing startup failure; define exit codes at a controlled boundary; and verify exit codes at the process level.**

### 1.1. High-level overview diagram

```text
SpringApplication.run(...)
       |
       +-- Prepare Environment / configuration
       |
       +-- Create ApplicationContext
       |
       +-- Load bean definitions / refresh
       |     +-- Some beans already initialized
       |
       +-- ApplicationStartedEvent
       |
       +-- ApplicationRunner / CommandLineRunner
       |
       +-- ApplicationReadyEvent, if successful
       |
       +-- Return context, if successful

On failure:
       |
       +-- Spring Boot determines exit code (if mapped)
       +-- Notify ApplicationFailedEvent appropriately
       +-- Report failure cause
       +-- Close context if already created
       |     +-- Stop eligible lifecycle components
       |     +-- Destroy still-managed singletons
       |
       +-- Rethrow failure to caller
       +-- Process exits per launcher/JVM mechanism
```

This describes the **primary flow**, not absolute log ordering, nor does it imply a context always exists on every failure. On a very early error during environment preparation, the context may **not have been created yet**. During a refresh failure, Spring Framework also runs cleanup for already-created singletons before propagating the failure up to Spring Boot.

## 2. Classifying failures by timing to identify who cleans up resources

| Stage | Example error | Context at error time | What to watch |
| --- | --- | --- | --- |
| Before context creation | Invalid arguments, missing config file, environment parse error | May be `null` | No bean destruction protects manually opened resources |
| Creating context / loading definitions | Initializer, metadata, or bean definition error | May exist yet unrefreshed | Only some infrastructure and objects exist |
| Inside `refresh()` | Missing dependency, constructor throws, `@PostConstruct` error, bind/validation error | Context created, refresh incomplete | Spring tries to clean up created singletons, while the **unfinished** failing bean may have no destructor registered |
| After refresh, inside runner | `ApplicationRunner`/`CommandLineRunner` throws exception | Context refreshed successfully | Boot runs failure handlers and closes context |
| In `ApplicationReadyEvent` callback / ready phase | Listener error or ready callback throws exception | Context may be active | Ensure cleanup and do not declare startup successful |
| Error outside startup path, after `run()` returns | Failing HTTP request, failing scheduled job | Context running | **Not by default** a startup failure; needs runtime failure handling |

This classification matters because many resources are created **before** Spring can own them.

For example, the code:

```java
Socket socket = new Socket(host, port);
SpringApplication.run(DemoApplication.class, args);
```

is **pseudo-code** with undefined variables and imports. If `SpringApplication.run` fails, the socket is only guaranteed to close if wrapped in an explicit ownership/cleanup mechanism. There is no guarantee Spring knows about the local variable `socket`.

Conversely, a singleton bean that finished construction with a registered destructor is normally cleaned up by Spring when closing the context or when refresh fails. Still, never claim every bean's destruction callback ran on every failure type.

## 3. What is ApplicationContext responsible for cleaning up?

When Spring manages a singleton bean and knows its destruction callback, the framework can invoke:

- `@PreDestroy` — the Jakarta annotation in Spring Boot 3.
- `DisposableBean.destroy()` — direct Spring contract.
- Custom destroy method — e.g., `@Bean(destroyMethod = "close")` or `@Bean(destroyMethod = "shutdown")`.
- Inferred `close()` / `shutdown()` methods via `@Bean` conventions when applicable.
- `SmartLifecycle.stop(Runnable callback)` for eligible lifecycle beans during normal context closing.

Simple example:

```java
@Configuration
class ClientConfiguration {

    @Bean(destroyMethod = "close")
    ClientHandle clientHandle() {
        return new ClientHandle();
    }
}
```

This is a **snippet**: it requires defining `ClientHandle implements AutoCloseable` and importing `Configuration`/`Bean`. Once the instance is returned cleanly and registered as a singleton bean, Spring calls `close()` when destroying the bean.

### 3.1. Ownership responsibility

A very practical rule:

> **Whichever party completes taking ownership of a resource is responsible for ensuring the resource is closed.**

This breaks down as:

| Resource | Who owns it? | Recommended mechanism |
| --- | --- | --- |
| Singleton bean completely created by Spring | Spring container | Registered bean destructor |
| Local `AutoCloseable` opened in a method | Method/caller | `try-with-resources` |
| Resource opened mid-constructor/factory before throwing | Constructor/factory | `try/catch/finally` right at allocation site |
| Worker thread started before `SpringApplication.run` | Bootstrap code | Explicit cleanup or dedicated ownership |
| `prototype` bean | Caller after Spring supplies instance | Caller closes it; Spring does not track/destroy every prototype |
| External resource like lock/lease | Lease/lock holder | Bounded-deadline release + expiration/recovery mechanism |
| Virtual thread/executor created manually outside container | Code creating executor | Manage cancellation/shutdown directly |

A destruction callback cannot close a resource the container **never knew existed**. If a bean never finished initializing, do not assume Spring registered that bean's destructor.

## 4. Why does a refresh failure still usually clean up created singletons?

Spring Framework's `AbstractApplicationContext.refresh()` includes error handling for the refresh phase. When an applicable error occurs, Spring attempts to:

1. Stop refresh from continuing.
2. Destroy singletons already created in the bean factory.
3. Mark the context as no longer successfully refreshed.
4. Propagate the exception to the caller/Boot for application-level failure handling.

In Spring Framework 6.1, destroying already-created singletons when refresh fails is a key part of `refresh()`'s contract.

Still, practical limits apply:

- A bean failing **between constructor execution and registration completion** may not have a destructor for the container to call.
- A resource held in a local variable inside a `@Bean` factory method **before returning** may be unknown to the container.
- `prototype` beans do not have container-managed destruction like singletons.
- External processes, sockets, threads, or files opened in custom static initializers sit outside bean lifecycles.
- A destroy callback itself may throw, block, or hit environment deadlines.
- If the JVM is forcibly killed, cleanup paths may never execute.

Hence **Spring's auto-cleanup is an important safety net, not an absolute guarantee for every resource allocation**.

### 4.1. Failure inside a @Bean factory method

A leak-prone pattern:

```java
@Bean(destroyMethod = "close")
RemoteSession remoteSession() {
    RemoteSession session = new RemoteSession();
    session.connect(); // If it fails here, @Bean has not returned session to container.
    return session;
}
```

This is **pseudo-code** since `RemoteSession` needs a separate definition. If `connect()` opens partial resources and throws, the bean was never returned cleanly; do not expect Spring to call `close()` on the local variable `session`.

Written with proper ownership:

```java
@Bean(destroyMethod = "close")
RemoteSession remoteSession() throws Exception {
    RemoteSession session = new RemoteSession();

    try {
        session.connect();
        return session;  // Hand over ownership to Spring.
    } catch (Exception | Error failure) {
        try {
            session.close();
        } catch (Exception closeFailure) {
            failure.addSuppressed(closeFailure);
        }
        throw failure;
    }
}
```

This snippet assumes `RemoteSession.connect()` and `close()` have matching contracts inside a `@Configuration` bean factory method. If an error occurs before `return`, the method closes the resource itself and preserves the original cause (attaching cleanup errors as *suppressed exceptions*).

**An even better option:** design `RemoteSession` so construction/connect is failure-safe and rolls back each step internally. Never allocate multi-step connections or background tasks without rollback.

### 4.2. Failure inside a constructor

Example:

```java
public final class SocketWorker {

    private final ResourcePart partA;
    private final ResourcePart partB;

    public SocketWorker() throws Exception {
        ResourcePart openedA = openPartA();

        try {
            ResourcePart openedB = openPartB();
            this.partA = openedA;
            this.partB = openedB;
        } catch (Exception | Error failure) {
            try {
                openedA.close();
            } catch (Exception cleanupFailure) {
                failure.addSuppressed(cleanupFailure);
            }
            throw failure;
        }
    }
}
```

This is a **design illustration**; `ResourcePart`, `openPartA`, and `openPartB` are undefined. The point is: once resource A is open, if opening B fails, the constructor must close A itself. You cannot rely on `@PreDestroy` of an unfinished bean to guard those steps.

If `openPartB` can allocate partial state before failing, `openPartB` itself must also ensure rollback of what was not handed over.

## 5. Runnable example: failure in ApplicationRunner and bean cleanup

The demo below uses **Java 17+**, **Spring Boot 3.3.x**, and requires only `spring-boot-starter`. A resource bean is created cleanly, then `ApplicationRunner` deliberately throws an exception.

The goal of this example is verifying:

1. The resource bean is created and owned by Spring.
2. A runner failure is a **startup-phase** failure even though context refreshed.
3. Spring Boot handles the failure and closes the context.
4. The resource's custom destroy method is invoked.
5. An exception implementing `ExitCodeGenerator` feeds a specific exit code into Boot's exit-handling mechanism.

### 5.1. Project structure

```text
startup-failure-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          failure/
            StartupFailureApplication.java
      resources/
        application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'startup-failure-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

This uses a Spring Boot 3.3 branch version to illustrate the API; production projects should pick a supported version per organizational policy. This setup requires a compatible Gradle/Gradle wrapper and JDK 17+. `./gradlew` is only present once a wrapper is generated for the project.

`src/main/resources/application.properties`:

```properties
spring.application.name=startup-failure-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
```

Using `web-application-type=none` avoids needing an HTTP server, letting us focus on lifecycle and exit codes without touching network ports.

### 5.2. Complete Java source

File `src/main/java/demo/failure/StartupFailureApplication.java`:

```java
package demo.failure;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class StartupFailureApplication {

    public static void main(String[] args) {
        SpringApplication.run(StartupFailureApplication.class, args);
    }

    @Bean(destroyMethod = "close")
    DemoResource demoResource() {
        return new DemoResource();
    }

    @Bean
    ApplicationRunner failingRunner(DemoResource resource) {
        return args -> {
            if (resource.isClosed()) {
                throw new IllegalStateException("Resource closed too early");
            }

            System.out.println("runner.start");
            throw new StartupRejectedException();
        };
    }
}

final class DemoResource implements AutoCloseable {

    private final AtomicBoolean closed = new AtomicBoolean(false);

    DemoResource() {
        System.out.println("resource.open");
    }

    boolean isClosed() {
        return closed.get();
    }

    @Override
    public void close() {
        if (closed.compareAndSet(false, true)) {
            System.out.println("resource.close");
        }
    }
}

final class StartupRejectedException
        extends RuntimeException implements ExitCodeGenerator {

    StartupRejectedException() {
        super("Demonstration startup failure");
    }

    @Override
    public int getExitCode() {
        return 23;
    }
}
```

Notes:

- Within one Java file, only `StartupFailureApplication` is top-level `public`; the other two classes are package-private and valid.
- `DemoResource` implements `AutoCloseable`; `@Bean(destroyMethod = "close")` explicitly declares Spring's cleanup responsibility.
- `isClosed()` is solely for checking state in the demo.
- `failingRunner` injects `DemoResource`, ensuring Spring constructed the resource before the runner executes.
- `StartupRejectedException` is an illustrative domain exception with a fixed message implementing `ExitCodeGenerator`.
- `getExitCode() == 23` represents a non-zero error code; this is a **demo convention**, not a universal exit code for all apps.
- Never call `System.exit` inside beans, runners, destructors, or failure listeners.

### 5.3. Running the application

Once the project has a Gradle wrapper:

```bash
./gradlew bootRun
```

Or:

```bash
./gradlew bootJar
java -jar build/libs/startup-failure-demo-1.0.0.jar
```

The JAR name above matches the demo build's group/name/version; if your project uses different coordinates, run the actual built file.

**Markers printed by the demo code** when the runner fails:

```text
resource.open
runner.start
resource.close
```

Spring Boot may also print stack traces and `Application run failed`, and Gradle may print task failure output. Those three lines are **not the complete stdout/stderr**, only the relative ordering of logs produced by the demo app.

When running the normal `main` path with Spring Boot 3.3's failure handler, the exception is detected through the cause chain and `getExitCode()` supplies **23** to the exit-code handler. Inspect the external Java process's final exit status, because surrounding wrappers (Gradle, IDEs, test runners) may enforce their own exit-reporting rules.

On a POSIX shell, run the JAR directly and inspect the exit code:

```bash
java -jar build/libs/startup-failure-demo-1.0.0.jar
printf 'exit=%s\n' "$?"
```

Expected output when Spring Boot uses `main`'s default failure handler:

```text
exit=23
```

This line is printed by the shell's `printf` **after the Java process exits**, not by `DemoResource`. On PowerShell, read `$LASTEXITCODE` after the native command.

### 5.4. Why did resource.close still run?

The failure occurred **in the runner after context refresh completed**. `SpringApplication.run` enters Spring Boot's failure handling path; the handler holds the created context, processes the failure, and closes the context. Closing the context destroys the `DemoResource` singleton bean via its custom destroy method `close()`.

This contrasts with creating `new DemoResource()` as a local variable without registering it as a bean: Spring has no knowledge of that resource and cannot invoke `close()` on behalf of its owner.

### 5.5. Do not call System.exit inside a runner

Do not rewrite the runner as:

```java
@Bean
ApplicationRunner dangerousRunner() {
    return args -> {
        System.err.println("Invalid startup input");
        System.exit(23);
    };
}
```

This is an **anti-pattern**. While JVM shutdown hooks may run under normal termination, calling `System.exit` directly makes process control hard to test and can bypass cleanup code following the method. If running inside an IDE, test runner, or shared JVM, it terminates the entire process.

Better: **throw an exception with an exit code or mapping**, let Spring Boot run failure handling, and let the process launcher propagate exit status.

## 6. Three ways to determine an exit code

Distinguish **startup failure mechanisms** from **intentional exit mechanisms after startup succeeds**.

| Approach | When to use | What to understand |
| --- | --- | --- |
| Exception implements `ExitCodeGenerator` | Startup fails due to a domain-meaningful exception | Boot can read the exit code from the exception/cause chain |
| `ExitCodeExceptionMapper` bean | Mapping multiple exception types by policy | Mapper bean is only available when context is active and built enough to look up |
| `SpringApplication.exit(context, generators...)` | `run` already returned context; app exits intentionally | Computes exit code and closes context; **does not terminate the JVM itself** |

Additionally, a **top-level launcher** may have a `catch` block to enforce CLI-specific exit codes. Avoid computing exit codes in two independent places that could conflict.

### 6.1. ExitCodeGenerator on an exception

`ExitCodeGenerator` is a Spring Boot interface:

```java
public interface ExitCodeGenerator {
    int getExitCode();
}
```

This is an **illustrative signature**; import `org.springframework.boot.ExitCodeGenerator` rather than redefining it in application code.

It can be implemented on an exception:

```java
public final class InvalidStartupConfigurationException
        extends RuntimeException implements ExitCodeGenerator {

    public InvalidStartupConfigurationException() {
        super("Startup configuration is invalid");
    }

    @Override
    public int getExitCode() {
        return 64;
    }
}
```

This is a standalone Java class for `InvalidStartupConfigurationException.java` in an appropriate package, importing `ExitCodeGenerator`. Code `64` is strictly an **application policy**, not a mandatory Spring Boot code.

Advantages:

- Error logic directly expresses its exit code.
- No active context is required to read the value from the exception itself.
- Works for very early failures or runner failures caught by Spring Boot.
- Can walk the cause chain to locate an exception implementing the interface when wrapped.

Remember: having an exit code does not mean every caller of `SpringApplication.run` immediately calls `System.exit`. `run` still throws the exception for callers to handle; Spring Boot supports default exception handling when launched from the main thread.

### 6.2. ExitCodeExceptionMapper

If you prefer keeping domain exceptions decoupled from Spring interfaces, use a mapper bean:

```java
@Configuration
class ExitCodeConfiguration {

    @Bean
    ExitCodeExceptionMapper startupExitMapper() {
        return exception -> {
            Throwable cursor = exception;

            while (cursor != null) {
                if (cursor instanceof InvalidInputException) {
                    return 64;
                }
                cursor = cursor.getCause();
            }

            return 0;
        };
    }
}
```

This is an **integration snippet** requiring imports for `Configuration`, `Bean`, `ExitCodeExceptionMapper`, and a definition of `InvalidInputException`. You do not need `ExitCodeGenerator` on the exception when policy lives in the mapper.

**Major limitation:** Boot retrieves mapper beans **only when the context exists and is active**. Failures before context creation or before refresh completes can make bean mappers unavailable. Therefore do not expect a bean mapper to handle **every** early startup failure.

In Spring Boot 3.3's `SpringApplication` source, exit-code computation on failure checks bean mappers when the context is active, then checks the exception/cause chain for `ExitCodeGenerator` if no other code was found. When defining precedence rules, verify against your deployed Spring Boot version.

### 6.3. ExitCodeEvent

Spring Boot publishes `ExitCodeEvent` to announce non-zero exit codes along paths supporting the event. This is a **notification about the exit code**, not a command to close sockets or destroy beans.

A listener:

```java
@Component
class ExitStatusObserver {

    @EventListener
    void onExitCode(ExitCodeEvent event) {
        System.out.println("app.exitCode=" + event.getExitCode());
    }
}
```

This snippet requires imports for `Component`, `EventListener`, and `org.springframework.boot.ExitCodeEvent`. For very early errors, **do not rely on a late-created bean listener**: the context may not be active or event infrastructure may not be registered yet.

Moreover, not every exit-code event is observed by every listener across all phases. To monitor ultra-early startup failures, prefer listeners registered before `run` or external process supervision.

### 6.4. SpringApplication.exit when run has succeeded

Example for an **intentionally exiting CLI**:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(BatchApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
```

This requires defining `BatchApplication` and importing `SpringApplication` and `ConfigurableApplicationContext`. It applies when **`run` returns successfully**.

`SpringApplication.exit(context)`:

- Collects eligible `ExitCodeGenerator` beans alongside any passed generators.
- Orders and selects a value per Boot's contract when multiple generators exist.
- Closes the context when possible.
- **Returns an integer** without calling `System.exit(...)` itself.

If you want the process to return that status, the `main`-level caller can pass it to `System.exit(code)`. Never place this blindly in a long-running server or test framework.

**Trap:** if `SpringApplication.run(...)` throws an exception, `context = ...` never completes; there is no valid context variable to pass to `SpringApplication.exit(context)` along this path. Boot already runs failure cleanup inside `run`; do not create a new context just to call exit.

## 7. What do exit code 0 and non-zero mean?

By OS and CI tool conventions:

- `0`: process reports successful completion.
- Non-zero: process reports failure or abnormal termination.
- Exact meanings of `2`, `23`, `64`, or other codes must be **defined by the application**.

Illustrative policy table:

| Code | Application-defined meaning |
| ---: | --- |
| 0 | Success |
| 2 | Invalid CLI arguments |
| 10 | Failed to load required configuration |
| 20 | Unable to connect to primary dependency |
| 23 | Task startup rejected (demo) |
| 30 | Startup data check failed |
| 70 | Uncategorized internal error |

This is an **example convention table**, not standard Spring Boot constants. Production systems should publish codes needed by automation and maintain backward compatibility.

Do not simply do:

```java
System.err.println("Startup failed");
return;
```

in `main` and expect the shell to receive non-zero. If `main` returns normally without another exit-code mechanism, the process typically returns `0`.

Likewise, logging `error` **does not change exit status**. Exit code is a **process outcome**; inspect it at the process level.

### 7.1. Observing exit codes in the shell

On Linux/macOS:

```bash
java -jar app.jar
code=$?
printf 'exit=%s\n' "$code"
```

On PowerShell:

```powershell
java -jar app.jar
Write-Output ("exit=" + $LASTEXITCODE)
```

These are shell snippets. Exact values depend on the Java process's exit code and Boot/launcher policies. When launching via Gradle, Maven, Docker, or Kubernetes, distinguish the **Java process exit code** from the wrapper's return code.

### 7.2. Do not call System.exit during cleanup

Never call `System.exit` inside:

- `@PreDestroy`.
- `DisposableBean.destroy()`.
- `SmartLifecycle.stop(Runnable)`.
- `ApplicationFailedEvent` listeners.
- A resource's `close()`.
- Async callbacks from a thread pool being shut down.

Because those callbacks execute **inside the resource cleanup flow**, terminating the JVM there can truncate other cleanup logic, hinder testing, and leave unpredictable state.

Define exit status at the **process boundary**; let Spring finish contractual cleanup before the process terminates whenever possible.

## 8. ApplicationFailedEvent: observing failures without replacing cleanup

Spring Boot publishes `ApplicationFailedEvent` when `SpringApplication` hits an eligible startup error. The event carries the exception and may carry the application context—yet **the context can be null if failure occurred before context creation**.

### 8.1. Why can an @EventListener bean miss early failures?

A bean:

```java
@Component
class StartupFailureLogger {

    @EventListener
    void onFailure(ApplicationFailedEvent event) {
        // Runs only if the listener bean already exists and was registered.
    }
}
```

needs proper imports and is only a snippet. If failure occurs **before bean creation**, this listener does not exist in event infrastructure yet and may never receive the event.

To observe early-stage errors, register the listener directly **before `SpringApplication.run(...)`**:

```java
SpringApplication app = new SpringApplication(BatchApplication.class);
app.addListeners(new EarlyFailureObserver());
app.run(args);
```

This snippet requires `BatchApplication` and `EarlyFailureObserver` to be declared, following a pattern placed inside `main`.

### 8.2. Early listener that does not require a context

Standalone class example:

```java
package demo.failure;

import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

public final class EarlyFailureObserver
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        String type = event.getException().getClass().getSimpleName();
        boolean contextExists = event.getApplicationContext() != null;

        System.err.println("startup.failureType=" + type);
        System.err.println("startup.contextExists=" + contextExists);
    }
}
```

To use it, register `new EarlyFailureObserver()` via `SpringApplication.addListeners(...)` before `run`. This listener is **not a bean** and uses no Spring injection; therefore never access repositories, datasources, or services that may not exist.

**Note:** the exception class may be a framework wrapper rather than the business root cause. To classify failures, walk the cause chain with a hop bound and avoid logging unredacted sensitive messages.

### 8.3. Event callbacks may run before cleanup finishes

In Spring Boot 3.3's failure handler, failure listeners are notified while processing the failure. Do not treat receiving `ApplicationFailedEvent` as a guarantee that:

- All singletons have already been destroyed.
- Bean-held resources have all closed.
- External compensating actions have finished.
- The process already has its final exit code.
- Other beans are safe to invoke.

**Use the event to record/observe the failure**, not to replace `try/finally` or bean destruction.

## 9. Cleanup principles when failures occur in each phase

### 9.1. Before context creation: bootstrap resources

For example, reading an auxiliary config file before calling Spring:

```java
try (InputStream in = Files.newInputStream(path)) {
    // Validate required data.
    // Start SpringApplication only after requirements pass.
}
SpringApplication.run(BatchApplication.class, args);
```

This is a **snippet** with `path` defined, `InputStream` and `Files` imported, and `BatchApplication` valid. The file stream closes upon leaving the block, even if validation throws.

If a resource must live throughout runtime, hand off ownership explicitly to a bean or manager rather than leaving resources in static fields hoping the JVM handles them.

### 9.2. During bean creation: partially opened resources

Place `try/catch` directly around allocation steps. If a factory method cannot return the bean, **the creator** must roll back opened resources. Preserve the original exception and attach cleanup failures as suppressed exceptions when appropriate.

### 9.3. During refresh: completed singletons vs failing singleton

Spring attempts to clean up singletons that finished construction earlier. Do not rely on the destructor of the **failing bean itself** if it never finished construction/initialization.

Check these callbacks:

- The failing bean's `@PostConstruct` may have opened resources before throwing.
- That bean's `@PreDestroy` may never have been registered or invoked.
- Dependent singletons **that succeeded earlier** can receive their destructors.
- External resources opened by the bean via static helpers or threads may need separate cleanup.

### 9.4. Runner failure after refresh

This is a cleaner situation for Spring-managed resources: the context already refreshed and required singletons were registered. Boot handles the failure and closes the context.

However, `ApplicationReadyEvent` **is not emitted as a successful startup event** when a runner throws. Monitoring software must not treat a pre-runner "Started application" log line as proof the app is business-ready.

### 9.5. Post-startup errors are not ApplicationFailedEvent

Once `SpringApplication.run` returns a context and a scheduled job throws later, that is a **runtime failure**. `ApplicationFailedEvent` serves failures during run/startup, not as a global event for every exception.

If a runtime failure must terminate the app, define an explicit policy:

- Record unhealthy/readiness status appropriately.
- Stop accepting new work.
- Cancel tasks and close resources.
- Close the application context.
- Decide the exit code at the process boundary.

Do not throw an exception on a background thread and assume the whole JVM will exit with your desired error code.

## 10. Cleaning up concurrent resources: threads, executors, schedulers

A bean may start a background thread inside its constructor or `@PostConstruct`. When startup fails later, those threads can keep running unless stopped.

Custom resource design example:

```java
public final class WorkerGroup implements AutoCloseable {

    private final ExecutorService executor =
            Executors.newSingleThreadExecutor();

    public void submit(Runnable task) {
        executor.execute(task);
    }

    @Override
    public void close() {
        executor.shutdown();

        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        } catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

This is a complete Java class in `WorkerGroup.java`, needing imports:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
```

Register it via `@Bean(destroyMethod = "close")` or `try-with-resources` to enforce ownership. `close()` uses a bounded wait so it does not block indefinitely.

**Limitation of the example:** if threads/tasks ignore interruption or hang in untimed I/O, `shutdownNow()` only signals cancellation and cannot guarantee resources stopped safely. Production requires domain-specific shutdown policies rather than relying solely on one `shutdownNow` call.

### 10.1. Why is starting threads inside constructors risky?

A constructor can launch a thread before Spring finishes registering the bean. If the constructor throws in a subsequent step, the thread is already running while the framework has no completed bean on which to invoke a destructor.

Instead, prefer:

- Minimal resource setup in constructors.
- Starting active work in `SmartLifecycle.start()` or an appropriate lifecycle point.
- Explicitly rolling back if `start` fails.
- Stopping intake and awaiting/canceling tasks with bounds on `stop`.
- Releasing remaining resources on `destroy`.

### 10.2. SmartLifecycle and stop order

Across multiple lifecycle components, Spring stops them in reverse `phase` order and by dependency relationships:

```text
START:
DatabaseConnection (phase -100)
        ↓
JobConsumer (phase 100)

STOP:
JobConsumer (phase 100)
        ↓
DatabaseConnection (phase -100)
```

This model holds when beans are registered and coordinated properly.

If `JobConsumer` needs the database to checkpoint during shutdown, stopping the consumer before the database is vital. Closing all connections blindly in a random `@PreDestroy` can break in-flight job completion.

**In very early refresh failures**, do not assume all start/stop phases ran. Components that open resources before lifecycle processors notice them require special care.

## 11. @PreDestroy, DisposableBean, and destroyMethod when the app fails

The three standard destruction callbacks on one bean normally run in order:

1. `@PreDestroy`.
2. `DisposableBean.destroy()`.
3. Custom destroy method on the bean definition if distinct and registered.

Remember they apply only when the bean is Spring-managed and progressed far enough for the container to register destruction callbacks.

Example:

```java
@Component
class TemporaryCache implements DisposableBean {

    @PreDestroy
    public void clear() {
        System.out.println("cache.preDestroy");
    }

    @Override
    public void destroy() {
        System.out.println("cache.disposableBeanDestroy");
    }
}
```

This snippet needs `Component`, `DisposableBean`, and `jakarta.annotation.PreDestroy` imports. It does not prove every startup failure invokes both callbacks; if the bean was never created or never finished creating, there is no guarantee.

Do not stack all three mechanisms "just to be safe", as that can double-close resources. Instead, define **one cleanup owner** and use the fitting callback.

### 11.1. Prototypes are not automatically destroyed

Spring creates prototype beans on demand yet does not track destruction of individual instances like singletons. If a prototype holds a file handle, the recipient receiving the prototype must close it.

This trap applies to both successful and failed startups: adding `@PreDestroy` to a prototype does not make it self-releasing.

### 11.2. Lazy beans that were never created

When `spring.main.lazy-initialization=true` or `@Lazy` is set on a bean, an unrequested singleton may **have no instance** when startup fails. With no instance, there is no destructor to run. That is expected behavior, not missed cleanup.

If the bean was already instantiated and registered in the container, its destructor can run when the context destroys singletons on the failure path.

## 12. What if cleanup itself throws an exception?

When both **operation** and **cleanup** fail, preserve the **root startup failure cause** rather than accidentally replacing it with an `IOException` from `close()`.

In Java, `try-with-resources` automatically preserves the primary failure and attaches the close error as a **suppressed exception**.

Standalone pure Java 17 example:

```java
public class SuppressedFailureDemo {

    static final class Resource implements AutoCloseable {

        @Override
        public void close() {
            System.out.println("resource.close");
            throw new IllegalStateException("close failed");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            throw new IllegalArgumentException("startup failed");
        } catch (RuntimeException failure) {
            System.out.println("primary=" + failure.getMessage());
            System.out.println(
                    "suppressed=" + failure.getSuppressed().length);
            System.out.println(
                    "suppressedType=" +
                    failure.getSuppressed()[0].getClass().getSimpleName());
        }
    }
}
```

Run:

```bash
javac SuppressedFailureDemo.java
java SuppressedFailureDemo
```

Exact output:

```text
resource.close
primary=startup failed
suppressed=1
suppressedType=IllegalStateException
```

Explanation:

- The primary error `IllegalArgumentException("startup failed")` occurs inside the block.
- Upon exiting the block, Java calls `close()` and catches the secondary `IllegalStateException`.
- Java preserves the primary error and attaches the cleanup error as suppressed.
- That way, investigators see **why startup failed first** and **where cleanup failed second**.

With a manual `finally`, if `close()` throws unhandled, it can mask the original startup failure. Prefer `try-with-resources`, or `addSuppressed` in complex cleanup paths.

### 12.1. Should close() swallow all errors?

No. Destructors should apply a **best-effort** strategy and record errors appropriately, never pretending closing always succeeded. When connections or leases cannot be released, operations need telemetry and recovery mechanisms.

Sound practice:

- Log error types and safely categorized resource identifiers.
- Never log passwords, tokens, or connection strings.
- Enforce bounded wait times.
- Preserve the startup failure root cause.
- If cleanup errors risk data loss, alert at appropriate priority.
- Avoid infinite retries during shutdown.

## 13. ExitCodeGenerator with multiple exit code sources

An app can register multiple `ExitCodeGenerator` beans or pass generators to `SpringApplication.exit(...)`. Per Boot 3.3 Javadoc, generators can be ordered via `Ordered` or `@Order`, and **the first non-zero code in order** is used.

Example:

```java
@Bean
ExitCodeGenerator validationExitCode() {
    return () -> 0;
}

@Bean
ExitCodeGenerator jobExitCode() {
    return () -> 12;
}
```

This is a snippet in `@Configuration` needing `Bean` and `ExitCodeGenerator` imports. It shows two generators, **not a guarantee of which runs first** without explicit ordering.

A cleaner design uses **one component deciding the batch outcome**, or an explicitly ordered policy, instead of multiple generators returning inconsistent codes.

**Do not confuse:** an `ExitCodeGenerator` bean for `SpringApplication.exit(context)` differs from an **exception implementing ExitCodeGenerator** during Boot's startup failure handling. They share an interface yet are collected at **different times**.

## 14. Handling errors before SpringApplication.run

If validation runs right in `main` **before Boot creates a context**, you can return an explicit exit code at the program boundary.

Pure Java 17 example:

```java
public final class PreflightCli {

    public static void main(String[] args) {
        int code = execute(args);
        System.exit(code);
    }

    private static int execute(String[] args) {
        if (args.length != 1 || !"--check".equals(args[0])) {
            System.err.println("Usage: java PreflightCli --check");
            return 2;
        }

        System.out.println("preflight.ok");
        return 0;
    }
}
```

Run:

```bash
javac PreflightCli.java
java PreflightCli --check
```

Output:

```text
preflight.ok
```

With invalid arguments:

```bash
java PreflightCli --unknown
```

Stderr output:

```text
Usage: java PreflightCli --check
```

And the process exits with code 2. This is a Java program **not using Spring Boot**, deliberately placing validation before bootstrap to contrast with `ApplicationRunner`, which runs after refresh.

When integrating into a Spring Boot app, you can run lightweight preflight checks before `SpringApplication.run(...)` and invoke Boot only once inputs qualify. Avoid allocating hard-to-close resources during preflight; if any resources are opened, wrap them in `try-with-resources`.

### 14.1. Why not use ApplicationRunner for all validation?

`ApplicationRunner` runs **after context refresh**. If an argument must be valid **before constructing expensive beans or opening a web server**, checking in a runner may be too late. For property-based config, consider `@ConfigurationProperties` validation; for simple CLI flags, preflight in `main` can also fit.

Always **distinguish preflight failures before context** from **runner failures after refresh** when evaluating resource cleanup.

## 15. FailureAnalyzer and remediation messages

Spring Boot provides `FailureAnalyzer` to translate common exceptions into actionable startup failure notices, typically formatted as:

```text
APPLICATION FAILED TO START

Description:
...

Action:
...
```

For example, an occupied HTTP port produces a failure analysis describing the cause and remediation. This is a **diagnostic interface**, not a resource cleanup or sole exit-code mechanism.

You can write a custom `FailureAnalyzer` when a domain exception needs clearer guidance. Note that Boot loads analyzers via early metadata/infrastructure—do not just sprinkle `@Component` expecting it to run on every pre-context error.

**Design principle:**

- `FailureAnalyzer` answers: *What failed and how to fix it?*
- `ExitCodeGenerator`/`ExitCodeExceptionMapper` answers: *Which status should the process report?*
- `ApplicationFailedEvent` answers: *Who needs to observe startup failures?*
- Bean destructors/`AutoCloseable` answer: *Who frees the resources?*

Never use one mechanism to substitute for the other three.

## 16. Errors during context closing: stop and destroy order

For a context that started lifecycle components, `close()` normally executes:

```text
ContextClosedEvent
      |
      v
LifecycleProcessor.onClose()
      |
      +-- Stop SmartLifecycle beans by phase
      +-- Wait for stop(Runnable) within bounds
      |
      v
Destroy singleton beans
      |
      +-- @PreDestroy
      +-- DisposableBean.destroy()
      +-- custom destroyMethod
      |
      v
Context close completes
```

However, in a **refresh failure**, lifecycle state may be only partially initialized. Never claim all stop phases run on every pre-refresh failure. Spring cleans up existing singletons, while tasks started early outside the lifecycle still need explicit owners.

### 16.1. stop(Runnable) must signal completion

An asynchronous `SmartLifecycle` stop must invoke `callback.run()` **after actually finishing**, not immediately after sending a stop signal.

```java
@Override
public void stop(Runnable callback) {
    stopAcceptingWork();

    completionFuture.whenComplete((value, failure) -> {
        try {
            running = false;
        } finally {
            callback.run();
        }
    });
}
```

This is **pseudo-code**: define `stopAcceptingWork`, `completionFuture`, and `running` in real implementations.

If the callback is never invoked, the lifecycle processor waits until the shutdown phase timeout. A timeout does not guarantee background tasks actually stopped; destruction may begin while tasks still use dependencies.

### 16.2. Shutdown timeout

Spring Boot 3.3 supports:

```properties
spring.lifecycle.timeout-per-shutdown-phase=20s
```

This is the timeout **per phase** in lifecycle shutdown, not a strict global deadline for all cleanup. Multiple phases, destructors, and scheduler/container delays can make total time longer.

If infrastructure kills the process before cleanup completes, destructors are no longer guaranteed to finish. On Kubernetes or other orchestrators, align termination grace periods with your application's deadlines.

## 17. Why isn't ApplicationFailedEvent "the moment everything is already closed"?

In Spring Boot 3.3 source code, the failure handler computes exit codes, notifies run listeners of the failure, reports the cause, and closes the context. Therefore a listener receiving `ApplicationFailedEvent` **may execute while some singletons still exist**.

That is why you should:

- Never treat this event as a signal that all resources are released.
- Never call repositories or clients that may be broken or closing.
- Never spawn new long-lived threads from a failure listener.
- Never call `System.exit` from a failure listener.
- Never call `context.close()` redundantly in a listener without a special reason; Boot already coordinates failure cleanup.

If you need to record that **cleanup has completed**, place instrumentation/metrics in the resource owner or the outer process/test wrapper rather than inferring it from receiving the failure event.

## 18. Verifying exact exit codes in end-to-end tests

A unit test calling `getExitCode()` directly only proves **the object returns the right number**. It does not prove the Java process actually exits with that status.

Layer your tests:

### 18.1. Unit test for exit code

```java
StartupRejectedException failure = new StartupRejectedException();
System.out.println(failure.getExitCode());
```

This snippet requires `StartupRejectedException` from Section 5's demo in a method/test with package access. Output:

```text
23
```

Yet this test builds no context and verifies no cleanup.

### 18.2. Integration test for bean cleanup

An integration test can launch an isolated context with the demo resource, trigger runner failure, and verify the `resource.close` marker.

Keep in mind:

- Test runners may bypass `main`'s default uncaught-exception exit handling.
- `run(...)` throwing an exception does not terminate the test JVM.
- Never call `System.exit` inside the test process.
- Use a recorder/`AtomicBoolean` to assert resource `close` was called rather than parsing full logs.
- Avoid sharing the cached test context when intentionally triggering startup failures.

### 18.3. Process-level test for exit status

Build the JAR, run it as a child process, and wait for termination with a timeout. In Java use `ProcessBuilder`, or run `java -jar` from a shell to inspect status.

With the demo:

```bash
java -jar build/libs/startup-failure-demo-1.0.0.jar
status=$?
printf '%s\n' "$status"
```

When running Boot's default failure handler on a normal main thread, the expected status is:

```text
23
```

Do not rely on `./gradlew bootRun` as sole proof of code 23, since Gradle may report task/wrapper codes by its own rules. To verify Java process status, run **the JAR directly**.

On Windows PowerShell, after `java -jar ...`, read `$LASTEXITCODE`; do not substitute `$?` indiscriminately.

### 18.4. Verifying zero resource leaks

Additional checks:

- Are files, ports, and sockets released after startup failure?
- Do DB pool active connections return to an appropriate state?
- Have background workers stopped accepting work?
- Should temporary files be deleted or retained for incident forensics?
- Do leases/locks have deadlines and recovery when the process is killed?
- Are cleanup exceptions preserved as suppressed or logged separately?
- Is any sensitive data left in failure reports?

**A single passing test run does not prove safety under every crash scenario.** Combine code-level cleanup with idempotency and external recovery.

## 19. Common mistakes when handling startup failures

| Symptom | Common cause | Remediation |
| --- | --- | --- |
| Failure logged yet process exits 0 | `main` returned normally or wrapper swallowed error | Inspect exception/exit path and process-level status |
| `System.exit(1)` called yet resources unclosed | Called exit too early in runner/callback | Let Spring close context; do not exit mid-cleanup |
| `@PreDestroy` of failing bean never runs | Bean never finished init/destructor registration | Roll back allocation steps inside constructor/factory |
| Other created singleton beans never released | Missing destructor or resource managed outside Spring | Add `@Bean(destroyMethod=...)`/`@PreDestroy` and confirm ownership |
| Prototype resource leaked | Spring does not destroy prototype instances | Caller uses `try-with-resources`/`close` |
| `ApplicationFailedEvent` bean listener did not run | Failure occurred too early before listener bean existed | Register listener before `run` |
| Failure listener hits null context | Failure happened before context creation | Check `event.getApplicationContext() != null` |
| Close exception hides startup exception | Cleanup threw inside `finally` | Use `try-with-resources`/`addSuppressed` |
| Later runner expected to run after earlier runner failed | Failure aborts runner chain | Never put critical cleanup only in a final runner |
| `SpringApplication.exit(context)` not called after failure | `run` returned no context | Distinguish startup failure from intentional post-success exit |
| `ExitCodeExceptionMapper` misses ultra-early env errors | Mapper is a bean; context not yet active | Use `ExitCodeGenerator` exception or pre-context preflight |
| Spring Boot reports stack trace containing token | Exception message/args included secret | Never embed sensitive data into exceptions; sanitize logs |
| App failed yet threads keep running | Threads spawned outside bean lifecycle | Manage executors via resource beans or explicit ownership |
| `SmartLifecycle` callback never finishes | Missing `callback.run()` or infinitely blocked task | Fix stop protocol, timeouts, and cancellation |
| App reported Started before runner failed | Started fires before runners | Monitor `ApplicationReadyEvent`/readiness |
| Lock remains after `SIGKILL` | No shutdown hook runs | Use lease timeouts, idempotency, and recovery |
| Cleanup runs twice | Resource closed manually and by container | Assign one owner; make cleanup idempotent |
| Exit code 23 turns into 1 in CI | CI/Gradle/wrapper translates codes | Test Java process directly and verify pipeline contract |

### 19.1. Diagnostic workflow

1. Identify the **first exception** and failure milestone: environment, context creation, refresh, runner, ready, or runtime.
2. Identify **resources already created** up to that point; who owns them?
3. Check whether the failing bean had **finished creation** and registered a destructor with the container.
4. If a resource was opened in constructor/`@Bean` and failed before returning, check rollback at the allocation site.
5. If a runner failed after refresh, check that Spring Boot's failure handler closed the context and ran appropriate destructors.
6. If the resource is a thread/executor, verify it actually stopped, not merely received a signal.
7. Identify how exit codes are determined: `ExitCodeGenerator` exception, mapper bean, or explicit `SpringApplication.exit`.
8. Run the JAR directly rather than relying solely on Gradle/IDE logs.
9. Check whether anything called `System.exit` early or swallowed exceptions returning 0.
10. Verify failure logs do not leak passwords, tokens, connection URLs, or user inputs.
11. Test scenarios where cleanup itself throws, not only happy paths.
12. Cross-check timeouts against deployment environment deadlines.

## 20. Policy for protecting secrets in failure logs

Startup errors often cause Spring Boot to print causes and stack traces. That helps debugging, yet can leak secrets if exception messages are built carelessly.

Do not:

```java
throw new IllegalStateException(
        "Cannot connect with token=" + apiToken);
```

Safer approach:

```java
throw new IllegalStateException(
        "Required upstream authentication is unavailable");
```

These two are snippets assuming `apiToken` exists. Never log:

- Raw `ApplicationArguments.getSourceArgs()`.
- Passwords, tokens, or JDBC URLs containing credentials.
- Unsanitized full environments or property sources.
- Contents of sensitive configuration files.
- Stack traces of custom exceptions whose messages embed secrets.

Log fields **known to be safe**: exception types, app error codes, non-sensitive config key names, and actions operators can take.

**Cleanup is also a leak vector:** if `close()` throws an exception containing a URL/token, the suppressed exception enters reports too. Craft messages for both primary errors and cleanup errors per log security policy.

## 21. Guarantees of graceful shutdown

No Java callback is guaranteed to run when:

- The JVM receives `SIGKILL`/`kill -9`.
- Power fails or the kernel crashes.
- The process is forcibly killed past its deadline.
- The runtime cannot allocate resources needed for cleanup.
- Code hangs in an operation that cannot finish within shutdown time.

Therefore, for resources external to the application:

- Transactions need DB-level rollback/consistency policies.
- Distributed locks need leases/expiration.
- Message processing needs idempotency and redelivery policies.
- Temporary files need janitors/reconciliation on restart.
- External sessions need server-side timeouts/expiration.
- Scheduled jobs/runs need restartable state/checkpoints.

**Graceful cleanup is a safety optimization under normal conditions; crash recovery is the defense line when cleanup does not run.** Critical systems need both.

## 22. Practice exercises

### Exercise 1 — Failure after refresh

Run Section 5's demo. Predict the marker order:

```text
resource.open
runner.start
resource.close
```

Explain why `resource.close` runs even though `SpringApplication.run` did not return a healthy context.

### Exercise 2 — Failure before bean return

Replace the resource factory with:

```java
@Bean(destroyMethod = "close")
DemoResource brokenResource() {
    DemoResource resource = new DemoResource();
    throw new IllegalStateException("failure before return");
}
```

This is a **replacement** variant of the old factory. Without internal cleanup code, is `resource.close` guaranteed to run? **No**: the resource was never handed over to Spring. Fix it with `try/catch` and `resource.close()` at the allocation site.

### Exercise 3 — Failure inside @PostConstruct

Create a bean that opens a file in `@PostConstruct` and intentionally throws. Explain why you cannot rely on `@PreDestroy` of **that same bean** to protect the opened file if initialization fails before the destructor is registered. Move file opening into `try-with-resources` or design immediate rollback inside initialization.

### Exercise 4 — ExitCodeGenerator

Change `StartupRejectedException.getExitCode()` from 23 to 42. Rebuild the JAR, run directly, and check shell status. Never treat a log message containing "42" as a substitute for checking `$?` / `$LASTEXITCODE`.

### Exercise 5 — ExitCodeExceptionMapper

Create `InvalidInputException` without implementing `ExitCodeGenerator`, and add a mapper bean returning 64 if the cause chain contains it. Test failure **after refresh in a runner**, then compare with failure **before context becomes active**. Explain why the mapper may be unavailable in the early case.

### Exercise 6 — Suppressed exceptions

Run `SuppressedFailureDemo`. Why are there two errors yet one `catch(RuntimeException)` and `suppressed=1`? Rewrite it with a flawed `finally` to see cleanup errors hide the root error, then fix with `addSuppressed`.

### Exercise 7 — Shutdown with a background executor

Register `WorkerGroup` with `@Bean(destroyMethod="close")`. Make a runner throw an exception. Observe `shutdown` calls and in-flight task handling; do not just check thread count at the instant startup fails.

### Exercise 8 — Failure before main SpringApplication

Add a preflight check for a mandatory flag **before** `SpringApplication.run`. If the flag is invalid, print safe usage and exit 2. What must happen to any files/sockets opened before preflight?

### Exercise 9 — Testing without killing the test runner JVM

Instead of calling `System.exit(23)` in JUnit, assert the exception, cleanup flags, and Spring Boot's exit code reporting; then run the JAR as a child process to verify the actual exit code.

## 23. Pre-production checklist

- [ ] Identified all startup phases that can fail.
- [ ] Every resource has a clear owner.
- [ ] Resource-owning singleton beans have registered destructors.
- [ ] Resources opened in constructors/factories roll back when initialization fails.
- [ ] Do not rely on `@PreDestroy` for beans that failed before finishing initialization.
- [ ] Prototypes and non-Spring resources are closed by callers.
- [ ] No background threads launched without shutdown/cancellation policies.
- [ ] No `System.exit` in runners, destructors, or failure listeners.
- [ ] Non-zero exit status on startup failure in process mode.
- [ ] Application error codes are governed by policy and documented.
- [ ] Distinguished `ExitCodeGenerator` exceptions from `SpringApplication.exit(context)`.
- [ ] Mapper beans are not assumed available across every failure stage.
- [ ] Early failure listeners registered before `run` when early errors must be observed.
- [ ] Listeners do not assume a non-null context.
- [ ] Cleanup does not mask the primary exception, attaching suppressed errors properly.
- [ ] Error messages contain no secrets.
- [ ] Timeouts defined for shutdown and external calls.
- [ ] Policy exists for failures occurring during shutdown itself.
- [ ] Verified `SIGTERM` and orchestrator deadlines.
- [ ] Recovery mechanism exists for `SIGKILL`/crashes.
- [ ] Real exit status verified with `java -jar`, not just logs or Gradle.
- [ ] Do not mistake `ApplicationStartedEvent` for runner completion / `ApplicationReadyEvent`.
- [ ] Tested pre-context, mid-refresh, and post-refresh failures.

## 24. Summary

1. On startup failure, **Spring Boot handles the failure and closes the context if created**, while Spring Framework cleans up already-created singletons when refresh fails. That protects many bean-managed resources, yet **does not protect every partially opened resource**.
2. **`@PreDestroy`, `DisposableBean`, and `destroyMethod`** release beans properly managed by the container. Resources in constructors/factory methods **not yet handed over** require direct cleanup via `try/catch/finally` or `try-with-resources`.
3. **`ExitCodeGenerator` on exceptions** binds exit codes to startup failure causes. **`ExitCodeExceptionMapper`** maps exceptions as a bean, which is limited if the context is not active yet. **`SpringApplication.exit(context)`** applies when a context exists and exits intentionally, not as a replacement for a failed `run`.
4. **`ApplicationFailedEvent`** is useful to observe startup failures, yet context may be `null` and bean listeners may not exist on very early errors. The event **does not confirm cleanup has finished**.
5. **`System.exit` belongs at the process boundary**, not in destructors. Exiting early in callbacks can abort needed cleanup; process-level tests confirm real exit status.
6. **Cleanup failures must not hide the primary error**; preserve suppressed exceptions, enforce timeouts, and keep secrets out of logs.
7. **No callback runs in every kind of crash**. For critical resources, pair lifecycle cleanup with recovery, idempotency, and lease expiration.

### Official documentation

- [Spring Boot 3.3 — SpringApplication, Application Exit and Startup Failure](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): application events, `ExitCodeGenerator`, startup failure messages.
- [Spring Boot 3.3 — SpringApplication Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html): `run(...)` and `exit(...)`.
- [Spring Boot 3.3 — ExitCodeGenerator Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeGenerator.html): exit-code return contract.
- [Spring Boot 3.3 — ExitCodeExceptionMapper Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeExceptionMapper.html): mapping exceptions to exit codes.
- [Spring Boot 3.3 — ApplicationFailedEvent Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html): context may be `null` when failing before context creation.
- [Spring Framework 6.1 — AbstractApplicationContext](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html): refresh errors, `destroyBeans`, closing context.
- [Spring Framework — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `@PreDestroy`, `DisposableBean`, and custom destruction callbacks.
- [Java 17 — try-with-resources](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html): automatic resource closing and suppressed exceptions.
