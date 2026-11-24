# Designing Safe, Idempotent, and Bounded Resource Closing in Spring Boot

## 1. The Problem: A Second `close()` Call Must Not Break the System

In a Spring Boot application, a resource with its own lifecycle can be an `ExecutorService`, HTTP client, connection pool, message consumer, file writer, cache with background threads, socket, scheduler, or an integration component talking to an external service. A resource may need to close when:

- The application exits normally and Spring closes `ApplicationContext`.
- A bean is destroyed per the container's lifecycle.
- An administrative task explicitly calls `close()` or `stop()`.
- Initialization fails mid-way and the system must clean up already allocated resources.
- A severe failure forces a component to stop before the entire application shuts down.
- Multiple components or threads issue stop requests almost simultaneously.

Never design on the assumption that "`close()` will be called exactly once, on one specific thread, at one exact moment." A good resource-closing API should have two properties:

1. **Safe when called multiple times (idempotent shutdown):** multiple calls do not repeat dangerous side effects, do not close another owner's resource, and do not create races that leak in-flight work.
2. **Bounded with an explicit outcome (bounded shutdown):** the procedure has a reasonable deadline; the caller knows whether it finished cleanly, had to force-stop, was interrupted, or could not confirm the resource stopped.

Logical relationships to remember:

```text
One close() call          -> stop requested
Multiple close() calls    -> converge on one terminal state
Graceful timeout          -> wait bound, does NOT prove stopped
Forced shutdown           -> attempts to request stop, does NOT always succeed
Actual completion         -> evidence the resource stopped running
ApplicationContext.close  -> coordinates lifecycle, does NOT understand every business invariant
```

**Lesson goal:** design a close mechanism that is *safely repeatable, safe under contention, and never waits forever*, and connect it properly to Spring Boot. This lesson is about application resources, **not** an exactly-once promise for data operations across multiple running processes.

## 2. "Idempotent Close" Does Not Mean "Ignore Any Subsequent Call Immediately"

A common naive implementation:

```java
private boolean closed;

public void close() {
    if (!closed) {
        closed = true;
        connection.close();
    }
}
```

This is **pseudocode illustrating risks**, not a complete program. It has at least three issues:

- `closed` is unsynchronized: two threads can both observe `false` and both invoke `connection.close()`.
- The flag is set to `true` **before** closing actually succeeds. If `connection.close()` throws an exception or closes asynchronously, later callers may be told it is closed while the resource is still alive.
- If thread A takes several seconds to close, thread B sees `closed=true` and returns immediately. If B's contract is "when `close()` returns, no tasks are running," that contract is violated.

In practice, distinguish at least:

| State | Meaning |
|---|---|
| `OPEN` | Accepting work and resource is ready |
| `CLOSING` | Not accepting new work; cleanup/drain in progress |
| `CLOSED` | Cleanup/termination confirmed successful |
| `FAILED_TO_CLOSE` | Stop requested, yet completion could not be confirmed under allowed conditions |

An `AtomicBoolean closingStarted` variable helps elect **one executor of cleanup**, yet **is insufficient** for other callers to know when cleanup finished. You also need a completion signal such as a `CountDownLatch` or `CompletableFuture`.

### Invariants to preserve

In a one-owner, many-callers model:

1. Accept no new work once the system transitions to closing.
2. Never allow two independent threads to perform destructive cleanup concurrently on the resource.
3. Subsequent callers observe **the same terminal outcome**, rather than imagining `closingStarted=true` means `CLOSED`.
4. Never return success before termination has been verified.
5. Never wait indefinitely; timeouts and interrupts have an exit path and are reported accurately.
6. Never reset `CLOSED` back to `OPEN` just because a new start call arrives, unless the application explicitly designs a **restart cycle**.

**Note:** "idempotent" describes the effect of repeating an operation. It **does not** require every `close()` call to never throw an error. If the resource fails to stop, throwing an exception is more meaningful than pretending to succeed.

## 3. Resource Ownership: Who Creates It Is Responsible for Closing It

Before picking an annotation, answer **who owns** the resource.

| How the Resource Is Obtained | Typical Owner | Appropriate Closing Mechanism |
|---|---|---|
| Singleton bean created by `@Bean`, fully container-managed | Spring container / bean responsible for internal resource | `@Bean(destroyMethod="close")` or explicit destroy mechanism |
| `@Component` holding a resource created in constructor/init | The component bean itself | `@PreDestroy` / `DisposableBean` or `SmartLifecycle` as needed |
| Executor/connection obtained from a shared bean | Infrastructure bean providing the resource | Consumers **must not** call shutdown on the shared resource |
| Resource created in a short scope and not registered in container | Block or object creating the resource | `try-with-resources` / `finally` |
| Client wrapper for an externally owned resource | External owner | Wrapper closes only the parts it actually owns |
| Resource managed by the framework, such as a server or scheduler | Framework lifecycle | Never manually call close and break infrastructure prematurely |

**Principle:** *ownership* matters more than whether an object has a `close()` method. If service A is only injected with a shared `ExecutorService` from bean B, A must not call `executor.shutdown()` inside its `@PreDestroy` while other services still need that executor.

Risky example:

```java
@Service
class ReportService {

    private final ExecutorService sharedExecutor;

    ReportService(ExecutorService sharedExecutor) {
        this.sharedExecutor = sharedExecutor;
    }

    @PreDestroy
    void cleanup() {
        sharedExecutor.shutdown(); // Wrong if the executor belongs to another infrastructure bean.
    }
}
```

This snippet merely illustrates an ownership error; real Spring/JDK imports and an executor bean are needed. Assign closing responsibility back to the bean that allocates the executor, and have consumers stop submitting new work before the executor is shut down.

## 4. Spring Resource-Closing Hooks

Spring supports multiple bean destruction mechanisms:

### 4.1. @PreDestroy

A method invoked when a **Spring-managed bean** is destroyed during the appropriate context-closing cycle:

```java
@Component
class LocalCache {

    @PreDestroy
    void release() {
        // Close resources owned by LocalCache.
    }
}
```

In Spring Boot 3.3, `@PreDestroy` uses `jakarta.annotation.PreDestroy`. It fits moderate synchronous teardown. There is no built-in contract for Spring to wait for an asynchronous chain started inside this method just because the method returns.

### 4.2. @Bean(destroyMethod = "close")

When a resource is created by a factory method:

```java
@Configuration
class ResourceConfiguration {

    @Bean(destroyMethod = "close")
    ManagedResource managedResource() {
        return new ManagedResource();
    }
}
```

This is an **integration snippet**: it requires a `ManagedResource` class with `public void close()` plus imports. Spring invokes the destroy method when the container-owned singleton bean is destroyed.

Spring Framework also has a destroy-method **inference** mechanism for beans created via `@Bean` if the object has a matching `close` or `shutdown` method. Writing `destroyMethod="close"` explicitly makes the contract easier to read, especially in learning examples.

### 4.3. AutoCloseable and try-with-resources

`AutoCloseable` is a Java interface:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

A class may override `close()` without declaring `throws Exception`. When a resource is owned by a Java block, `try-with-resources` calls close at the end of the block:

```java
try (SomeResource resource = openResource()) {
    use(resource);
}
```

This is a generic pattern requiring real `SomeResource`, `openResource()`, and `use(...)` implementations. Never both place a resource in `try-with-resources` and hand the exact same resource to Spring management without understanding that it may be asked to close from **two paths**. An idempotent `close()` reduces risk, yet **does not replace assigning one clear owner**.

### 4.4. DisposableBean

`org.springframework.beans.factory.DisposableBean.destroy()` is a Spring-level destruction callback. It fits when you need a direct contract with the framework; for business/library classes meant to stay Spring-independent, `AutoCloseable` or an explicit destroy method is usually easier to test.

### 4.5. SmartLifecycle

`SmartLifecycle` is used when **phase-ordered start/stop** or asynchronous stopping with a callback is required:

```java
void stop(Runnable callback);
```

`DefaultLifecycleProcessor` coordinates stopping in descending phase order, waiting for callbacks or phase timeouts before advancing. It differs from `@PreDestroy` or `@Bean(destroyMethod=...)`: **the callback coordinates the stopping phase**, whereas destroy methods handle bean destruction.

Do not stack all mechanisms onto one bean assuming "more callbacks means safer." If a bean has `SmartLifecycle.stop(Runnable)`, `@PreDestroy`, and `close()`, clearly separate responsibilities, order, and duplicate invocation handling. A common pattern: the stop phase halts intake and drains; final destroy only checks/closes as a fallback once already stopped.

## 5. What Does Spring Boot's Shutdown Timeout Cover?

In Spring Boot 3.3:

```properties
spring.lifecycle.timeout-per-shutdown-phase=20s
```

This property configures how long **`LifecycleProcessor` waits per phase group**, applying to stopping lifecycle beans including `SmartLifecycle`. It is **not a global timeout for every Java statement during shutdown**.

Do not deduce:

```text
spring.lifecycle.timeout-per-shutdown-phase=20s
=> every @PreDestroy and every @Bean(destroyMethod="close")
   is guaranteed to return within 20 seconds.
```

That deduction is **wrong**. A synchronous destroy method can block on I/O or locks; a phase timeout will not interrupt that method automatically. When a bounded close is required, the resource itself or its caller must enforce a **resource-level deadline**.

An application may follow:

```text
A. SIGTERM from orchestrator
         |
B. SpringApplicationContext closes
         |
C. SmartLifecycle stop (per-phase timeout)
         |
D. Destroy singleton beans (@PreDestroy, close, destroy)
         |
E. JVM exits if no non-daemon threads keep the process alive
```

The time budget at layer A may be shorter than the sum of stages C+D. On `SIGKILL` or `kill -9`, the JVM has no opportunity to run normal cleanup.

### Graceful Web shutdown does not automatically close business workers

For Spring Boot 3.3 Web applications:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Spring Boot tells the Web server to stop accepting new requests and gives in-flight requests a configured window to complete. However, **message consumers, custom executors, and file writers** still need their own stop designs. Do not assume enabling graceful Web shutdown flushes every external client connection, in-memory queue, and database transaction.

## 6. ExecutorService: Requesting Stop Differs from Confirming Stopped

In Java 17, `ExecutorService` provides these APIs:

| API | Meaning | Waits for Completion? |
|---|---|---|
| `shutdown()` | Stops accepting new tasks; lets submitted tasks finish | **No** |
| `isShutdown()` | Shutdown has been requested | Does not mean all tasks finished |
| `awaitTermination(timeout, unit)` | Waits for executor termination, deadline expiry, or interrupt | **Yes**, returns boolean |
| `isTerminated()` | Confirms executor terminated after shutdown | Status check |
| `shutdownNow()` | Attempts to interrupt running tasks and returns unstarted ones | **No guarantee** of stopped |
| `Future.get(timeout, unit)` | Waits for **a single task** to finish within a duration | Does not replace shutting down the whole executor |

A classic trap:

```java
executor.shutdown();
closed = true;
```

If tasks are still running, `closed=true` cannot be interpreted as "executor terminated." Design with clear names like `shutdownRequested`, `acceptingNewTasks`, and `terminated`.

### Two phases: graceful → forced

A basic workflow:

```text
Turn off application intake
        |
executor.shutdown()
        |
awaitTermination(gracePeriod)
        |
   +----+----+
   |         |
   v         v
terminated   timeout
   |         |
   |         v
   |    executor.shutdownNow()
   |         |
   |    awaitTermination(forcePeriod)
   |         |
   |       +-- terminated?
   |       |   +-- yes: controlled forced termination
   |       |   +-- no: report UNKNOWN / FAILED_TO_CLOSE
   v
Success (with evidence)
```

`shutdownNow()` is only **best-effort**. If a task is stuck in native I/O or ignores interrupts, it can keep running after `shutdownNow()` returns. In that case, **never declare close successful** merely because the wait expired.

Calling `shutdownNow()` can also discard unstarted tasks from the queue. If they carry critical business work, the application must record and handle lost work/retries/checkpoints properly rather than treating it as consequence-free cleanup.

## 7. Runnable Example: AutoCloseable with Safe Repeated Closing and a Two-Stage Bound

The following **Java 17 + Spring Boot 3.3.5** project demonstrates:

- A `GuardedJobResource` bean that **owns** the executor it creates.
- `submit(...)` and intake shutdown share **the same lock**.
- `AtomicBoolean` elects **exactly one caller** to perform shutdown.
- `CountDownLatch` tells subsequent close callers **whether the first close has completed**.
- Two explicit wait intervals: up to **1 second graceful**, then **1 second after a force-stop request**.
- If the executor fails to terminate, the method throws an error instead of pretending it closed cleanly.
- `@Bean(destroyMethod="close")` lets Spring call `close()` again when destroying the bean; subsequent calls do not double-close.
- The runner explicitly closes the resource twice, and then context closing triggers a third call to verify idempotency.

This is a **single-JVM demo** with short, cooperative tasks. It does not automatically provide durable queues, retries, exactly-once semantics, unhangable threads, or full restart semantics.

### 7.1. Project structure

```text
bounded-resource-close/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/boundedclose/
    ├── BoundedCloseApplication.java
    └── GuardedJobResource.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'bounded-resource-close'
```

**`build.gradle` (Gradle Groovy DSL):**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

No Web server or database is needed. To run `./gradlew`, the project needs an already generated Gradle Wrapper (e.g., via Spring Initializr) or a compatible installed Gradle; writing `build.gradle` alone does not generate the Wrapper scripts.

### 7.2. Resource owning the executor and guarding close

**`src/main/java/com/example/boundedclose/GuardedJobResource.java`:**

```java
package com.example.boundedclose;

import java.util.List;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class GuardedJobResource implements AutoCloseable {

    private final Object admissionLock = new Object();

    private final ExecutorService executor =
            Executors.newSingleThreadExecutor(task ->
                    new Thread(task, "owned-job-worker"));

    private final AtomicBoolean closeStarted = new AtomicBoolean(false);
    private final CountDownLatch closeFinished = new CountDownLatch(1);

    // These fields are read after the latch signals completion.
    private volatile boolean terminated;
    private volatile String closeFailure = "unknown";

    // All access to this variable is guarded by admissionLock.
    private boolean accepting = true;

    public Future<String> submit(String jobId) {
        Objects.requireNonNull(jobId, "jobId");

        synchronized (admissionLock) {
            if (!accepting) {
                throw new RejectedExecutionException(
                        "Resource is closing; new jobs are rejected");
            }

            return executor.submit(() -> {
                // Simulate I/O that cooperates with interruption.
                Thread.sleep(100);
                return "done:" + jobId;
            });
        }
    }

    @Override
    public void close() {
        if (closeStarted.compareAndSet(false, true)) {
            // Only the first caller owns the shutdown path.
            try {
                synchronized (admissionLock) {
                    accepting = false;
                    executor.shutdown();
                }
                System.out.println("CLOSE: requested");

                boolean stopped =
                        executor.awaitTermination(1, TimeUnit.SECONDS);

                if (!stopped) {
                    List<Runnable> pending = executor.shutdownNow();
                    System.err.println(
                            "CLOSE: forced; not-started jobs = "
                            + pending.size());

                    stopped = executor.awaitTermination(
                            1, TimeUnit.SECONDS);
                }

                terminated = stopped;

                if (!stopped) {
                    closeFailure =
                            "executor still running after stop deadline";
                    throw new IllegalStateException(closeFailure);
                }

                System.out.println("CLOSE: terminated");
            } catch (InterruptedException ex) {
                // Do not forget to request stop if the caller is interrupted.
                executor.shutdownNow();
                closeFailure = "close thread was interrupted";
                Thread.currentThread().interrupt();
                throw new IllegalStateException(closeFailure, ex);
            } finally {
                // Always mark the close attempt as FINISHED;
                // does not mean it succeeded.
                closeFinished.countDown();
            }
        } else {
            // Later callers do not confuse CLOSING with CLOSED.
            try {
                if (!closeFinished.await(2, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "another close call is still in progress");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "interrupted while waiting for close", ex);
            }

            if (!terminated) {
                throw new IllegalStateException(
                        "previous close did not terminate: "
                        + closeFailure);
            }

            System.out.println("CLOSE: already terminated");
        }
    }
}
```

**Explanation by invariant:**

1. `GuardedJobResource` implements `AutoCloseable`, so callers independent of Spring can manage it with `try-with-resources`.
2. It creates `ExecutorService` itself and is the **owner**; hence it has the right to call `shutdown()` and `shutdownNow()`. Never apply that right to an application-wide shared executor.
3. `submit` acquires `admissionLock` to check `accepting` and submit the job **within the same critical section**. When `close` acquires the lock to set `accepting=false` and call `shutdown()`, no new work can slip in **after intake has closed**.
4. `compareAndSet(false,true)` elects exactly one thread to own the closing work. Without this step, two threads could wait or trigger force-stop uncontrollably.
5. `closeFinished` serves **later callers**. They do not mistake a close that has *started* for one that has *succeeded*.
6. `awaitTermination(1, SECONDS)` waits up to one second for normal termination. If unfinished, `shutdownNow()` issues a stronger stop request and waits up to one more second.
7. If tasks still do not finish, `terminated=false` and `close()` throws `IllegalStateException`. **Threads may still be running**; the exception signals a need for investigation, not proof cleanup finished.
8. `closeFinished.countDown()` runs in `finally` even if the closing thread is interrupted or the close attempt fails. The latch only signals **the first close attempt has produced a result**; `terminated` is the flag recording the confirmed outcome.
9. Another caller invoking `close()` after the first succeeded waits on the latch (which completes immediately), checks `terminated`, and does not call `shutdown()` again.
10. If the first attempt fails, later calls **do not treat it as success**. This example does not automatically retry shutdown after failure because that needs its own recovery/force-close policy, which a single boolean cannot solve.

**Time bounds to understand accurately:** the code uses **two 1-second `awaitTermination` calls**, plus lock acquisition, JVM scheduling, and error handling overhead. This is a per-step wait budget, **not an absolute wall-clock guarantee that the method returns in strictly under 2,000 ms** on every machine and resource. If a stricter total deadline is required, compute remaining time via `System.nanoTime()` at each step and bound synchronous I/O during cleanup too.

**Concurrency limitation of the demo:** never call `close()` from inside a job running on **the exact executor that `close` waits for**; doing so would wait on its own thread (pool starvation/self-join). Normally an admin path, lifecycle callback, or independent coordinator thread runs close.

### 7.3. Spring Boot class registering the destroy method and closing three times

**`src/main/java/com/example/boundedclose/BoundedCloseApplication.java`:**

```java
package com.example.boundedclose;

import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BoundedCloseApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BoundedCloseApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            System.out.println("MAIN: closing context");
        }

        System.out.println("MAIN: closed");
    }

    @Bean(destroyMethod = "close")
    GuardedJobResource guardedJobResource() {
        return new GuardedJobResource();
    }

    @Bean
    ApplicationRunner runDemo(GuardedJobResource resource) {
        return args -> {
            Future<String> job = resource.submit("job-7");

            System.out.println(
                    "RESULT: " + job.get(3, TimeUnit.SECONDS));

            resource.close(); // 1st call: actual shutdown.
            resource.close(); // 2nd call: safe no-op after success.

            try {
                resource.submit("late");
            } catch (RejectedExecutionException ex) {
                System.out.println("SUBMIT: rejected after close");
            }
        };
    }
}
```

The runner waits up to three seconds for a cooperative job to complete **before** closing. Then a second close occurs inside `ApplicationRunner`, and Spring invokes `close()` via `destroyMethod` when `ApplicationContext` closes. Those are three close requests on **the same object**, without creating three executors.

Intentional points of the demo:

- Bean `GuardedJobResource` is managed by Spring because it comes from `@Bean`.
- `@Bean(destroyMethod="close")` explicitly tells Spring to invoke cleanup when destroying the singleton bean.
- `ApplicationRunner` can use the bean after the context refreshes.
- `WebApplicationType.NONE` keeps the example as a console program without starting a Web server.
- `try-with-resources` on **the context** causes Spring to execute the lifecycle closing path; this differs from closing the resource manually in plain Java.
- `@PreDestroy` is not added on `GuardedJobResource` because there is no need to add a redundant close path just to "be sure."

### 7.4. Run command

In the project with Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

If you do not have a Wrapper yet, generate the project from Spring Initializr or use a compatible Gradle installation. Java 17+ is required for Spring Boot 3.3, and this project targets Java 17.

### 7.5. Key output

Lines explicitly printed by the demo code in logical order, ignoring Spring Boot/Gradle banners and logs:

```text
RESULT: done:job-7
CLOSE: requested
CLOSE: terminated
CLOSE: already terminated
SUBMIT: rejected after close
MAIN: closing context
CLOSE: already terminated
MAIN: closed
```

Explanation:

- The first job finishes and returns `done:job-7`.
- The first close shuts off intake, calls `shutdown()`, and confirms executor termination.
- The second close simply verifies the prior successful outcome without shutting down again.
- `submit("late")` is rejected because `accepting=false`.
- When the context closes, Spring invokes the destroy method again; that third close also causes no destructive side effects.
- `MAIN: closed` appears only after Spring `close()` finishes.

**If you remove `resource.close()` from the runner**, Spring will still invoke `close()` once during destruction via `@Bean(destroyMethod="close")`. The log lines will then differ from the example; note that you changed the scenario before comparing stdout.

## 8. Why Use One Lock for Both Submit and Shutdown?

A classic bug:

```java
if (!closed.get()) {
    executor.submit(job);
}
```

Between `get()` and `submit()`, another thread can execute `shutdown()`. As a result:

- The caller believes the resource is still open, yet `submit` throws `RejectedExecutionException`.
- With a custom queue/sentinel, a job may still be accepted past the cutoff and become **lost work**.
- Log state fails to account for jobs accepted at close time.

With standard executors, `RejectedExecutionException` is a valid error path and must be handled; it is not necessarily a bug when occurring right at shutdown. However, if the application contract requires "every job accepted before close must have a chance to run," you need a **linearization point for intake**.

In the demo, that is `synchronized(admissionLock)`:

```text
Submit A:
  acquire lock -> check accepting -> executor.submit -> release

Close B:
  acquire lock -> accepting=false -> executor.shutdown -> release

Submit C:
  acquire lock -> sees accepting=false -> reject -> release
```

Because both operations synchronize on the same lock, there can never be a state where **Submit A passed the check but has not yet submitted** while Close B has already shut down the executor. The outcome may vary depending on which thread acquires the lock first, yet every observable ordering obeys the contract.

This is **thread-safe admission** for the example. It **does not** automatically solve the business state of an accepted task (e.g., committing DB work and crashing before returning the `Future`). Durable systems still need transactions, checkpoints, idempotency, or proper broker acknowledgments.

## 9. When the First Close Fails: Idempotency Must Preserve Failure State

An often overlooked point: if the first `close()` call fails, what should subsequent calls do?

Three common policies:

| Policy | Behavior | Suitable When |
|---|---|---|
| **Fail-closed, no auto-retry** | Rejects new work; reports that termination is unconfirmed | Closing again could be dangerous; needs operator/another owner |
| **Controlled retry** | Lets a new caller run missing cleanup steps after `FAILED` | Cleanup is safely repeatable, bounded, and loses no data |
| **Escalate/force-close** | Uses forcible APIs, records unfinished work, and escalates | System has an explicit policy for uncooperative resources |

The Section 7 demo picks the first policy. On timeout/interrupt, `closeFinished` still signals so subsequent callers **do not wait forever**, yet `terminated=false` causes them to receive an exception. Never write:

```java
if (closeStarted.get()) {
    return; // Wrong if you need to know whether close actually succeeded.
}
```

If a real project requires retries, extend the state machine so only one caller retries at a time, keep resource ownership intact, block new submissions, record attempt outcomes, and avoid repeating non-idempotent steps.

### Is exactly-once cleanup necessary?

Many Java close operations like `ExecutorService.shutdown()` are designed to be harmless when repeated; some other close APIs are too. However, **not all business cleanup steps are idempotent**. For example:

- Writing a "job completed" record on a second close can duplicate business logs.
- Committing the same message offset a second time can violate protocol semantics.
- Deleting files or returning resources to a pool repeatedly can cause errors.
- Sending a "workflow finished" notification multiple times can cause external side effects.

Therefore **execute once-only side effects under a single owner**, while later callers observe the outcome. Do not mistake calling a Java method multiple times for a distributed exactly-once transaction.

## 10. Use a Total Deadline Instead of Arbitrary Additive Timeouts

The demo uses 1 second graceful + 1 second forced for clarity. In real applications, accept a total budget `Duration totalBudget` and allocate based on **remaining** time.

Diagram:

```text
closeStartedAt = System.nanoTime()
deadline = closeStartedAt + totalBudget
           |
           +-- stop intake
           +-- issue graceful close
           +-- wait up to min(graceBudget, remaining)
           +-- if not done: force-close/cancel
           +-- wait up to remaining
           +-- confirm result or report incomplete
```

Illustrative formula:

```java
long deadline = System.nanoTime() + timeout.toNanos();
long remaining = Math.max(0L, deadline - System.nanoTime());

boolean stopped = executor.awaitTermination(
        remaining, TimeUnit.NANOSECONDS);
```

This is an **integration snippet** requiring a valid `Duration timeout` and `executor`. In a production timer, guard against `Duration.toNanos()` overflow for huge values and choose a sensible maximum budget. `System.nanoTime()` fits measuring **elapsed time**; do not use `LocalDateTime.now()` for deadlines vulnerable to system clock adjustments.

**Unavoidable limitation:** a timeout on a wait call does not force an underlying synchronous operation to return on its own. If `driver.close()` blocks indefinitely on I/O without timeout support, a plain `try/finally` cannot enforce the deadline. Choose APIs with real timeouts/cancellation, sometimes using a separate coordinator thread—while still treating hung threads as a risk to handle.

### Multi-layered shutdown budget

Example of a deployment giving the process a 30-second grace period:

```text
Orchestrator SIGTERM grace budget: 30s
    Spring phase stop group 1:   max 8s
    Spring phase stop group 2:   max 8s
    Resource close/destroy:      target 5s
    Logging, network flush, JVM: reserve 4s
    Scheduling margin:           remainder
```

This is an **illustrative allocation example**, not a Spring Boot default. Some steps run in parallel and others sequentially; measure real durations. The lesson is that **individual timeouts must never accidentally add up past the process budget**.

If the orchestrator sends `SIGKILL` after 30 seconds, configuring a 60-second wait timeout in Java **does not** grant the process 30 extra seconds to live.

## 11. Using SmartLifecycle.stop(Runnable) for Ordered Stopping

When a resource is a long-running component that must stop before its dependencies, `SmartLifecycle` can fit better than destroy methods alone. It provides:

- `start()` to activate the component along with the context lifecycle.
- `isRunning()` to reflect current state.
- `getPhase()` to pick ordering across lifecycle beans.
- `stop(Runnable callback)` to run asynchronous shutdown and then **signal completion** to `LifecycleProcessor`.

**Phase order:** start lower phases before higher; stop higher phases before lower. For example, a consumer using a writer might assign phase 200 to the consumer and phase 100 to the writer so the consumer stops and drains before the writer.

Logical pattern:

```text
DefaultLifecycleProcessor:
  calls Consumer.stop(callback)
        |
  Consumer stops intake
        |
  Consumer waits/flushes within worker shutdown deadline
        |
  Consumer confirms finished or stop policy completed
        |
  callback.run()
        |
  Processor can advance to writer phase
```

**Common mistake:** calling `callback.run()` immediately after `executor.shutdown()`. The executor may still be running. Spring considers the stop step complete, causing the lower-phase writer/DB client to begin closing while the consumer is still using it.

Conversely, forgetting to invoke the callback makes `LifecycleProcessor` wait out the entire phase timeout. Invoking the callback is an **obligation** of the implementation. When cleanup fails or the deadline expires, record the failure and apply a force-stop/recovery policy; the callback signals that the coordinated stop step finished, **not a guarantee that all data was processed safely**.

### Distinguishing callback and Future

`stop(Runnable)` takes only a `Runnable`. If a resource-closing library returns a `CompletionStage`:

```java
CompletionStage<Void> completion = client.stopAsync();

completion.whenComplete((ignored, error) -> {
    try {
        if (error != null) {
            recordFailure(error);
        }
    } finally {
        callback.run();
    }
});
```

This is **integration pseudocode** assuming `client` has `stopAsync()`, `recordFailure` exists, and `callback` comes from `stop(Runnable)`. In real usage, verify whether the third-party API's "completion" means intake stopped, socket closed, or merely stop command sent. **Only attach the callback to a future with matching completion semantics**, never to a future meaning "stop request accepted."

A `SmartLifecycle` bean can still have a destroy callback as fallback cleanup. Still, avoid double-closes with side effects: share the same state machine and clear owner contract, or have `stop` handle business draining while `destroy` only verifies/closes any remainder if needed.

## 12. Under Which Circumstances Can @PreDestroy Be Invoked?

`@PreDestroy` is invoked when the container destroys a bean within a valid Spring lifecycle. However, never write code assuming:

- The JVM always has enough time to run shutdown hooks.
- The context always refreshes successfully before cleanup is needed.
- `@PreDestroy` is the only stop step that can happen.
- Merely because Spring invoked the destroy method, all tasks on the resource have stopped.
- All bean scopes manage destruction the same way as singletons.

**Singleton:** the container usually manages full singleton creation and destruction, so destroy callbacks run during normal shutdown.

**Prototype:** the container creates prototypes on demand yet does not manage full per-instance destruction like singletons. The prototype's owner usually must clean up itself.

**Lazy bean:** if a singleton was never instantiated, there may be no instance on which to call destroy. Never use `@PreDestroy` on a lazily created bean as the sole guarantee that an application-wide shutdown action always runs.

**Improperly closed context:** if the process is forcefully killed or crashes, Java callbacks may never run. Critical data needs proper recovery, journaling/checkpoints/transactions, rather than hoping `@PreDestroy` flushes it.

### Should you attach both @PreDestroy and destroyMethod?

On a single bean, declaring multiple destroy mechanisms can trigger multiple callbacks. Spring has deduplication rules in some configurations, yet **you must not treat arbitrary combinations as guaranteed to invoke close only once**. The simplest approach is picking one primary path, such as `@Bean(destroyMethod="close")` for factory-created resources or `@PreDestroy` for components owning their own resources.

If a design requires both, the cleanup method must be safe under repeated calls and independent of unverified ordering. Never add extra callbacks "just in case" without tests.

## 13. Closing Fails Mid-Way: Which Outcome Should You Report?

Not every resource has a binary "closed / not closed" state. Consider a message consumer:

```text
STOP requested
  -> stop accepting new messages
  -> wait for in-flight handlers
  -> persist results and commit transaction
  -> ack/checkpoint
  -> close connection
  -> confirm STOPPED
```

An error can happen after stopping intake and before acking. At that moment the resource may **no longer accept work**, yet business data remains unconfirmed. Returning "CLOSED" just because the socket closed conveys insufficient information.

A clearer outcome model:

| Outcome | Meaning to Record |
|---|---|
| `GRACEFUL_TERMINATED` | All contracted work finished and the resource stopped |
| `FORCED_TERMINATED` | Stopped, though unfinished work may remain and need recovery |
| `TIMED_OUT_UNCONFIRMED` | Budget exhausted; resource stoppage unverified |
| `INTERRUPTED` | Caller interrupted while waiting; resource state needs inspection |
| `FAILED` | A cleanup step threw an error; inspect partially completed state |

In Java, `AutoCloseable.close()` returns `void`, so you can choose to **throw an exception**, store the outcome on the object for metrics, or expose a `closeWithin(Duration)` method returning a custom `CloseOutcome`. Do not mistake these illustrative enums for default Spring APIs—they are **application design**.

If an API returning outcomes is needed, you can design:

```java
public CloseOutcome closeWithin(Duration budget) {
    // Perform stop per state machine; return structured outcome.
}
```

This is an illustrative snippet where `CloseOutcome` is project-defined. There is no need to force a plain Java `AutoCloseable` to hold all operational metadata; what matters is giving callers a way to observe the real outcome.

## 14. Concurrency: How Can Two Callers Closing Together Race?

### 14.1. "Check-then-act" race

```java
if (!closed) {
    closeConnection();
    closed = true;
}
```

Two threads can pass the `if` together. For a file handle, socket, or pool whose close semantics are unsafe to repeat, this causes bugs. Use an atomic state transition or lock to elect one owner.

### 14.2. "Closing reported as already closed" race

```java
if (closing.compareAndSet(false, true)) {
    slowCleanup();
} else {
    return;
}
```

This may fit if the contract is merely "request close," and is **wrong** if the contract is "when the method returns, cleanup is complete." When completion is required, the second caller must await a `CountDownLatch`/`CompletableFuture` with a deadline and inspect the outcome state.

### 14.3. Race between submit and close

If `accepting` flips to false asynchronously relative to enqueuing, a task can be "accepted" after shutdown has passed its cutoff. The fix is creating an **atomic boundary** for work admission and stop state (like `admissionLock` in the demo), or a queue/state machine explicitly built for those semantics.

### 14.4. Blocking oneself during close

A task running on a single-worker pool calls `pool.shutdown()` and then `awaitTermination(...)` on **that very worker**. It waits for the executor to finish while the executor cannot finish until that exact task returns. That is **self-deadlock/starvation**. Run close from an external coordinator thread or use an appropriate non-blocking completion mechanism.

### 14.5. Invoking the callback multiple times

When using `SmartLifecycle.stop(Runnable)` and writing:

```java
try {
    closeResource();
    callback.run();
} finally {
    callback.run();
}
```

if cleanup succeeds, the callback runs twice. This is an **intentionally buggy snippet**. Ensure every stop request receives completion signaling exactly once at the right milestone. With multiple callers, you can maintain a list of callbacks, synchronized so callbacks added right as shutdown finishes are still handled.

## 15. Handling Interruption, Cancellation, and shutdownNow()

Java interruption is a **cooperative request mechanism**, not a thread-kill switch:

```java
try {
    boolean terminated =
            executor.awaitTermination(2, TimeUnit.SECONDS);

    if (!terminated) {
        executor.shutdownNow();
    }
} catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Shutdown interrupted", ex);
}
```

This is an integration snippet requiring a caller-owned `executor` on which `shutdown()` was already called. Restoring the interrupt flag lets higher-level callers see that the thread was interrupted.

**Claims you must never make:**

- `shutdownNow()` guarantees tasks performing native I/O or ignoring interrupts will stop.
- `Future.cancel(true)` rolls back already committed database transactions.
- `Future.get(...)` timing out stops the task itself (it only ends **the caller's wait**).
- `CompletableFuture.cancel(...)` interrupts the underlying task without explicit cancellation integration.
- An interrupted thread never needs sockets/files closed to unblock I/O.
- Daemon threads replace proper cleanup; the JVM can exit while tasks are incomplete.

When data matters, forcible stops must record unconfirmed in-flight tasks, checkpoints/offsets, and post-restart retry policies. Never log everything as "shutdown success" merely because the process is about to exit.

## 16. Resources Can Close Multiple Times Without Auto-Reopening

Idempotent closing and **restartability** are two separate concerns.

For a single-use resource:

```text
OPEN -> CLOSING -> CLOSED
              \-> FAILED_TO_CLOSE
```

After `CLOSED`, every `submit` is rejected. Those are the demo's semantics.

If a resource supports cycles:

```text
NEW -> STARTING -> RUNNING -> STOPPING -> STOPPED
                 ^                        |
                 +------ restart ----------+
```

then you must **define generations explicitly**: the old executor has terminated, old queues and callbacks are no longer used, brand-new resources are created, and callers know which generation they target. Never just flip `closed=false` on a shut-down `ExecutorService`: that executor **cannot be reopened**.

In Spring, some `SmartLifecycle` components support starting/stopping repeatedly. Yet `@Bean(destroyMethod="close")` under singleton destruction semantics is not an invitation to reuse a destroyed object. If independent restarts are needed, design dedicated lifecycle methods and a state machine with a generation counter.

## 17. Interaction with the Dependency Graph and Close Order

A consumer may use a writer, and the writer may use a database client:

```text
MessageConsumer -> BatchWriter -> DatabaseClient
```

During orderly shutdown, stop the consumer from accepting new work, drain in-flight handlers, flush the writer, and then close the database client. If `DatabaseClient` closes before the consumer finishes flushing, final tasks can fail.

You can design phases:

```text
Start:
  DatabaseClient -> BatchWriter -> MessageConsumer

Stop:
  MessageConsumer -> BatchWriter -> DatabaseClient
```

`SmartLifecycle.getPhase()` supports ascending start order and descending stop order. `@DependsOn` can also influence lifecycle/bean destruction ordering. Yet setting phases alone does not guarantee **every task is drained**; the consumer must still wire its callback to actual completion, and every resource needs matching timeouts.

### Avoid closing shared dependencies from a consumer

If `BatchWriter` and `MessageConsumer` share `DatabaseClient`, neither component should call `databaseClient.close()` itself when stopping. Let the bean owning the database client close it at the proper phase/destroy time after consumers have stopped.

**Reviewer rule:** never allow a service to destroy a shared dependency just because it received that dependency via constructor injection. Injecting a dependency does not transfer resource ownership.

## 18. Testing Idempotency and Deadlines Properly

### 18.1. Testing repeated close calls

With `GuardedJobResource`:

```java
GuardedJobResource resource = new GuardedJobResource();

resource.close();
resource.close();

try {
    resource.submit("not-allowed");
    throw new AssertionError("submit should reject after close");
} catch (RejectedExecutionException expected) {
    // Right: rejects new tasks.
}
```

This is a non-Spring integration Java snippet needing `RejectedExecutionException` and `GuardedJobResource` from the example. Verify **no unexpected exceptions** on the second close and no new work accepted.

### 18.2. Testing two concurrent callers closing

To force a clear race, use a `CountDownLatch` as a barrier instead of `Thread.sleep(5)`:

```java
GuardedJobResource resource = new GuardedJobResource();
CountDownLatch start = new CountDownLatch(1);
CountDownLatch completed = new CountDownLatch(2);

Runnable closeTask = () -> {
    try {
        start.await();
        resource.close();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new RuntimeException(ex);
    } finally {
        completed.countDown();
    }
};

new Thread(closeTask, "closer-a").start();
new Thread(closeTask, "closer-b").start();

start.countDown();

if (!completed.await(5, TimeUnit.SECONDS)) {
    throw new AssertionError("close callers did not finish in time");
}
```

This is an **integration test snippet** needing `CountDownLatch`, `TimeUnit` imports, and a test method with `throws Exception`. It lets two threads contend for closing rights. **Limitation:** exceptions inside worker threads do not automatically propagate to the test thread. In production JUnit tests, capture exceptions in a thread-safe structure or use `Future.get`/`CompletableFuture.allOf` to assert each caller properly. Never just wait on a latch and assume all workers succeeded.

### 18.3. Testing deadlines

Create a cooperative task that sleeps 500 ms and close with a 2-second budget: the normal outcome must be terminated. Next test a task reacting slower than the grace period while honoring interruption: you observe the force-stop path, yet must verify it actually terminated.

Never run an intentionally infinite loop ignoring interruption in the same development JVM and expect the program to exit cleanly. Such a non-daemon worker can keep the JVM alive. When stress-testing that scenario, use a separate test process with an external watchdog and safe kill mechanism.

### 18.4. Testing errors after partial cleanup has already run

Suppose closing a resource has three steps: flush, close socket, release lock. Intentionally make step 2 throw an exception and verify:

- Did step 1 complete?
- Did step 3 still run in fallback cleanup?
- Is the state `CLOSED` or `FAILED_TO_CLOSE`?
- Does a second caller receive the same outcome?
- Were any unintended sockets/workers recreated?
- Are remaining resources logged/recorded in metrics?

This matters far more than merely testing that `close()` does not throw when everything goes well.

### 18.5. Integration tests with a Spring context

In an integration test, build a context containing a `@Bean(destroyMethod="close")` bean, have a runner (or test code) call `close()` once, and then close the context. Measure actual cleanup invocations with an `AtomicInteger` incremented at **the real side-effect site**, not just counting calls to `close()`. The contract is "actual cleanup runs once," while the method itself may be called multiple times.

## 19. Monitoring and Operating Shutdown Incidents

When an application logs only `Closing resources...` without logging the outcome, it is very hard to tell clean closing from timeouts. Monitor:

- Number of close requests and actual cleanup executions.
- Time taken to stop accepting new work.
- Drain duration for in-flight tasks and remaining tasks at budget expiry.
- Status counts: graceful / forced / timed-out / interrupted.
- Connections or threads still running after close.
- Exceptions raised in destroy methods / `SmartLifecycle`.
- Per-phase durations compared against the process shutdown grace period.
- Restart impact: whether unacked jobs are redelivered and whether duplicate processing occurs.

Spring Boot provides Micrometer/Actuator if configured in the project. Yet never assume custom resources already emit metrics; the application must define appropriate counters/timers explicitly. Avoid logging secrets, sensitive payloads, or full task contents in shutdown traces.

### Operationally meaningful success criteria

A "shutdown complete" message should be backed by **measurable criteria** such as:

```text
acceptingNewWork = false
inFlightCount = 0
executor.isTerminated() = true
writerFlushCompleted = true
connectionClosed = true
callbackSignalled = true (if using SmartLifecycle)
```

These are **illustrative states to verify**, not default Java/Spring fields. In systems choosing forced shutdown, criteria differ: explicitly report unfinished tasks and recovery mechanisms rather than slapping on the same "graceful success" label.

## 20. Common Bugs

| Symptom | Cause | Fix |
|---|---|---|
| Two threads calling close cause errors | Check-then-act on `boolean closed` | Elect owner via lock/CAS, share completion |
| Second close returns before the first | Checked only "started" flag | Use latch/future for completion, with deadline |
| `shutdown()` finished yet threads keep running | `shutdown` does not wait for tasks | `awaitTermination` and check `isTerminated` |
| `shutdownNow()` finished yet workers stay alive | Tasks ignore interrupts or block on I/O | Resource timeouts, real force-close, report unconfirmed |
| Closing context hangs a long time | Destroy callback blocks forever on I/O/lock | Resource-level deadline and monitoring |
| Set `spring.lifecycle.timeout-per-shutdown-phase` yet `@PreDestroy` still hangs | Timeout applies only to lifecycle phases | Add explicit time bounds inside destroy callback cleanup |
| Closed resource in runner and also let Spring destroy it | Two close paths on the same bean | Prefer one owner; make close API idempotent if repeated |
| Closed shared executor from consumer service | Confused injection with ownership | Let the bean allocating the executor manage shutdown |
| Bean destruction failed yet `CLOSED=true` | Set success flag too early | Separate `CLOSING`/`CLOSED`/`FAILED` |
| Context closing yet new jobs still accepted | Submit unsynchronized with stop | Admission gate / atomic state mechanism |
| `stop(Runnable)` callback called early | Invoked right after issuing request instead of after drain | Tie callback to completion with matching semantics |
| Callback never called | Dropped error branch or timeout without completion path | Guarantee completion/callback path, report failure |
| Worker closes its own pool and waits | Self-deadlock | Use a different coordinator thread |
| `@PreDestroy` on prototype never runs | Spring does not fully manage prototype destruction | Prototype owner cleans up itself |
| `kill -9` loses data | No orderly shutdown path | Durability, transactions, checkpoints, restart recovery |
| Added huge timeouts to "be safe" | Combined budget exceeds orchestration grace | Allocate measurable deadlines per layer |
| Repeated close creates duplicate audits/messages | Cleanup has non-idempotent side effects | Dedupe/single owner once, store outcome |
| Executor already shut down yet code tries to restart | `ExecutorService` has no reopen API | Create a clear new generation/resource |

### Review checklist

- [ ] Correct resource owner identified; shared dependencies are never closed by consumers.
- [ ] `OPEN`, `CLOSING`, `CLOSED`, `FAILED_TO_CLOSE` states defined.
- [ ] Cutoff blocks new work before draining starts.
- [ ] Admission and shutdown are synchronized.
- [ ] Only one caller executes cleanup; other callers observe the outcome.
- [ ] Repeated close after success causes no duplicate side effects.
- [ ] Repeated close after failure never pretends to succeed.
- [ ] Explicit graceful/forced timeouts defined per resource.
- [ ] `shutdown()`, `shutdownNow()`, and `isShutdown()` are not confused with `isTerminated()`.
- [ ] `InterruptedException` handled, restoring the interrupt flag where appropriate.
- [ ] Pool termination is never awaited from a worker inside that pool.
- [ ] If using `SmartLifecycle`, callback runs after stop and phases match dependencies.
- [ ] Spring phase timeouts are not expected to abort arbitrary destroy methods.
- [ ] Tests cover double-close, concurrent close, timeouts, and cleanup failures.
- [ ] Monitoring tracks forced/timeout/unfinished work.
- [ ] JVM shutdown budget is smaller than infrastructure grace period, with margin.

## 21. Practice Exercises

Use the Section 7 project, changing one thing at a time and restoring before trying the next.

**Exercise A — close once, many times:** run as-is. Count three `close()` calls (two from the runner, one from Spring destroy), yet only one occurrence of `CLOSE: requested` and `CLOSE: terminated`.

**Exercise B — try submitting after close:** verify `submit("late")` is rejected. Because `submit` and `close` share `admissionLock`, no new job is accepted once intake closes.

**Exercise C — concurrent closing:** use two threads and latches as in Section 18. Keep a cooperative job running so the second caller arrives during `CLOSING`; verify it waits for the outcome instead of returning success immediately.

**Exercise D — grace period expiry:** change `Thread.sleep(100)` to longer than 1 second in a test run. Observe the `shutdownNow()` branch and interrupt request; explain the difference between "force requested" and "termination confirmed."

**Exercise E — task ignoring interrupts:** simulate only in an isolated test process with a watchdog. Observe `awaitTermination` can return false even after `shutdownNow()`. Explain why cleanup success cannot be promised by timeouts alone.

**Exercise F — remove admission synchronization:** intentionally move the `accepting` check and `executor.submit` outside the lock and use a barrier/latch to race with close. Observe the `RejectedExecutionException` path and identify the invariant that must be protected.

**Exercise G — failed close state:** in a test, simulate a close that cannot confirm termination. A second close request must see the failure rather than returning as if `CLOSED`.

**Exercise H — compare destroy hooks:** move the resource into a self-owned `@Component` bean using `@PreDestroy`, then compare with `@Bean(destroyMethod="close")`. Pick **one primary path** per demo version to avoid accidentally adding duplicate callbacks.

**Exercise I — add SmartLifecycle:** build a phase-200 consumer depending on a phase-100 writer. Stop intake, drain within a deadline, and invoke the callback only after the consumer finishes; confirm the writer stops after the callback or after timeout if the callback is intentionally omitted.

**Exercise J — production design:** for a message consumer, write the contract: who owns the broker client, executor, and DB pool; which messages are in-flight; when to ack; how to stop intake; graceful/forced deadlines; unacked message count; post-restart retry policy; and alert metrics.

### Self-assessment questions

1. Why is an `AtomicBoolean` marking `closeStarted=true` insufficient to prove a resource is `CLOSED`?
2. Does `shutdown()` wait for submitted tasks to finish?
3. Does `shutdownNow()` guarantee killing tasks that ignore interruption?
4. Why should a second caller learn the first caller's completion if the contract is synchronous close?
5. If a resource belongs to a shared infrastructure bean, does a service injected with it have the right to call `shutdown`?
6. Why does `spring.lifecycle.timeout-per-shutdown-phase` not constrain every `@PreDestroy`?
7. Where is the linearization point between `submit` and `close` in the demo?
8. If the first close misses its deadline, should the second close return "done" or report an unconfirmed state?
9. When should you pick `SmartLifecycle.stop(Runnable)` instead of only `@Bean(destroyMethod="close")`?
10. Why does cleanly closing resources in one JVM not automatically guarantee zero lost/duplicate messages when a process crashes?

## 22. Conclusion

Safe repeated resource closing starts with **proper ownership, an explicit state machine, and shared completion outcomes**. One caller wins the right to close; other callers neither run duplicate cleanup nor confuse `CLOSING` with `CLOSED`. The task-admission boundary must be synchronized with shutdown. Closing deadlines need concrete budgets, graceful-then-forced paths, and error reporting when resource stoppage cannot be confirmed.

In Spring Boot, use `@Bean(destroyMethod="close")`, `@PreDestroy`, or `SmartLifecycle` **according to responsibility and required coordination**, never stacking annotations to patch over races. `spring.lifecycle.timeout-per-shutdown-phase` helps with lifecycle phases, yet **does not automatically bound arbitrary destroy callbacks**. And when a JVM is forcefully killed, only proper durability and recovery protect unfinished work.

**A principle to remember:** **idempotent closing does not mean error-free closing; bounded closing does not mean stopped; stopping a resource does not mean every business transaction was confirmed.**

### Official Documentation

- Spring Boot 3.3 — Graceful Shutdown and `spring.lifecycle.timeout-per-shutdown-phase`: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Framework 6.1 — Bean lifecycle/destroy and `close`/`shutdown` inference: https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-nature.html
- Spring Framework 6.1 — `@Bean` Javadoc, `destroyMethod`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Bean.html
- Spring Framework 6.1 — `SmartLifecycle` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — `DefaultLifecycleProcessor` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Java SE 17 — `ExecutorService` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 — `ThreadPoolExecutor`, `shutdown`/`shutdownNow`/`awaitTermination`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html