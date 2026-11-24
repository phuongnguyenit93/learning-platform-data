# Managing Timeouts, Concurrency, and Process Cleanup After Checks

## 1. Objective and Scope

A Spring Boot test pipeline often starts many components outside the Maven/Gradle JVM: web applications, databases, message brokers, Docker containers, mock servers, browser drivers, subprocesses, and multiple test workers. If any task hangs or fails to clean up properly, CI can time out, TCP ports remain occupied, databases retain stale data, child processes keep running, or subsequent test jobs get disrupted.

Three problems must be solved separately:

1. **Timeouts:** define how long an operation may run, what the overall test/job deadline is, and what happens when the limit is exceeded.
2. **Concurrency:** run concurrent tests and tasks within bounded limits, avoid port/file/database contention, and avoid spawning too many processes or threads.
3. **Cleanup:** whether tests pass, fail, time out, or get interrupted, stop applications/processes/containers, close resources, and collect necessary logs.

A reliable design coordinates **JUnit timeouts, Maven/Gradle test workers, Java `ExecutorService`, `ProcessBuilder`, Docker cleanup, and CI job timeouts**. No single timeout flag protects every layer.

After this lesson, you will be able to:

- Distinguish timeouts across tests, HTTP requests, subprocesses, test JVMs, and the entire CI job.
- Use monotonic-time deadlines to prevent unintended timeout accumulation.
- Write Java 17 code running subprocesses with `ProcessBuilder`, timeouts, output capture, and best-effort process-tree termination.
- Run `Callable` tasks concurrently with a bounded thread pool, handle cancellation/interruption, and await executor termination.
- Configure JUnit 5, Maven Surefire/Failsafe, and Gradle test workers.
- Start test servers/containers on dedicated ports, poll readiness with a timeout, and clean up resources along every exit path.
- Use shell traps and CI timeouts to clean up Docker containers when scripts fail or get canceled.
- Spot process leaks, output-pipe deadlocks, non-interruptible threads, port conflicts, and cleanup masking the root failure.

**Example versions:** Java 17, **Spring Boot 3.3.5**, JUnit Jupiter 5.10.2, Maven Surefire/Failsafe 3.2.5, Gradle Java `Test` task, and Docker CLI. These versions keep illustrative code consistent; use versions approved by your project.

## 2. Timeouts Must Be Layered

A pipeline can have several nested deadlines:

~~~text
CI job deadline:             20 minutes
  |
  +-- Maven/Gradle test task: 12 minutes
        |
        +-- Integration test: 60 seconds
              |
              +-- HTTP readiness: 20 seconds
              |
              +-- HTTP request: 5 seconds
              |
              +-- Child process: 10 seconds
~~~

Numbers are illustrative. Allocate real budgets based on your CI environment, application startup time, and check criticality.

| Layer | Controlled Timeout | On Expiration |
| --- | --- | --- |
| HTTP client/request | A single API call or connection | Cancel request/socket and report error |
| Test method | A single test case | Mark test failed/aborted per test framework |
| Subprocess | An external command outside the JVM | Stop the process and child processes within controllable scope |
| Test suite/task | An entire test group or Maven/Gradle task | Stop workers/processes and collect logs |
| CI job | Entire job/step | CI runner cancels job; cleanup hooks run depending on termination mode |

**Outer timeouts must exceed inner timeouts.** If a test has a 30-second deadline while the CI job has only 20 seconds left, the runner may be killed before the test can stop processes and save logs. Leave a cleanup margin after test/task deadlines.

### 2.1. Timeout Is Not Cancellation

- **Timeout** is the conclusion that a deadline has expired.
- **Cancellation** is the request to stop ongoing work.
- **Interruption** is the Java signal sent to a thread asking it to stop or release resources.
- **Termination** means the process or thread has actually stopped.

Calling `Future.cancel(true)` only requests interrupting the executing thread. It does not guarantee the code stops: the task must call blocking APIs that honor interruption or actively check the interrupt flag. Likewise, canceling an HTTP future does not always close an underlying socket managed by a third-party library.

**Never use `Thread.stop()`** to force-stop code. It is unsafe with shared state and is not a valid cancellation mechanism.

## 3. Choosing Deadlines and Avoiding Timeout Accumulation

If three sequential steps each receive a 30-second timeout, total elapsed time can approach 90 seconds. If the whole workflow must finish within 30 seconds, use **one shared deadline** and pass the remaining time to each step.

Use `System.nanoTime()` to measure elapsed time and deadlines within the current process. Never use `System.currentTimeMillis()` for durations because wall-clock time can jump.

~~~java
import java.time.Duration;

public final class Deadline {
    private final long endNanos;

    private Deadline(Duration budget) {
        if (budget.isNegative() || budget.isZero()) {
            throw new IllegalArgumentException("budget must be positive");
        }
        this.endNanos = System.nanoTime() + budget.toNanos();
    }

    public static Deadline after(Duration budget) {
        return new Deadline(budget);
    }

    public Duration remaining() {
        long nanos = endNanos - System.nanoTime();
        return Duration.ofNanos(Math.max(0L, nanos));
    }

    public boolean expired() {
        return endNanos - System.nanoTime() <= 0L;
    }
}
~~~

Usage example:

~~~java
Deadline deadline = Deadline.after(Duration.ofSeconds(20));

callService(deadline.remaining());

if (deadline.expired()) {
    throw new java.util.concurrent.TimeoutException("workflow deadline exceeded");
}

runDatabaseCheck(deadline.remaining());
~~~

`callService` and `runDatabaseCheck` must actually apply the passed duration to their HTTP/client/driver APIs. Passing a duration that a library ignores does not enforce a real timeout.

### 3.1. Propagating Deadlines Across Layers

A workflow should pass the deadline or remaining budget across layers rather than letting each layer reset to its own default timeout. This avoids infinite retries or granting every HTTP call a brand-new full budget.

- Configure separate connect and read timeouts when supported by the HTTP client.
- Cap retry counts and total retry budget.
- Never retry unrecoverable errors like invalid credentials or bad coordinates.
- Once the deadline expires, do not start new tasks.
- Reserve a separate buffer to close resources and save logs.

## 4. Timeouts for JUnit 5 Tests

JUnit Jupiter supports `@Timeout` and timeout assertions. Example:

~~~java
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class ServiceTimeoutTest {

    @Test
    @Timeout(value = 3, unit = TimeUnit.SECONDS)
    void serviceRespondsWithinBudget() throws Exception {
        // Call test service; client also needs its own timeout.
    }
}
~~~

`@Timeout` bounds the test method duration. It is a test-framework guardrail and **does not replace HTTP client, JDBC, subprocess, or container timeouts**. If a test blocks inside a non-timeout API, the thread may remain stuck in the external layer.

### 4.1. assertTimeout and assertTimeoutPreemptively

~~~java
import static org.junit.jupiter.api.Assertions.assertTimeout;
import static org.junit.jupiter.api.Assertions.assertTimeoutPreemptively;

import java.time.Duration;
import org.junit.jupiter.api.Test;

class TimeoutAssertionTest {

    @Test
    void checksElapsedTimeAfterWorkCompletes() {
        assertTimeout(Duration.ofSeconds(1), () -> {
            performQuickCheck();
        });
    }

    @Test
    void requestsPreemptiveCancellationWhenBudgetExpires() {
        assertTimeoutPreemptively(Duration.ofSeconds(1), () -> {
            performInterruptibleCheck();
        });
    }

    private void performQuickCheck() {
        // Work expected to have a short duration.
    }

    private void performInterruptibleCheck() throws InterruptedException {
        Thread.sleep(100);
    }
}
~~~

Differences:

- `assertTimeout`: runs the callback to completion and then evaluates elapsed time. If the callback hangs forever, the assertion cannot interrupt it at the deadline.
- `assertTimeoutPreemptively`: executes the callback on a separate thread and requests cancellation once the budget expires. It can break code relying on `ThreadLocal`, transaction context, or test-framework state bound to the original thread.
- Preemptive cancellation still relies on the code honoring interruption. A task ignoring interrupts can keep running after the assertion times out.

Do not mechanically wrap an entire Spring test suite in preemptive timeouts. Prefer real timeouts on the underlying APIs/processes that need protection, apply `@Timeout` intentionally, and ensure resource cleanup does not depend solely on the interrupted thread.

## 5. Maven Surefire and Failsafe: Managing Test JVMs

Maven commonly uses:

- **Surefire** to run unit tests in the `test` phase.
- **Failsafe** to run integration tests via `integration-test` and `verify` goals.

When tests run in forked JVMs, Maven plugins can limit how long a forked process is allowed to run. Example Surefire configuration:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.2.5</version>
    <configuration>
        <forkCount>2</forkCount>
        <reuseForks>true</reuseForks>
        <forkedProcessTimeoutInSeconds>180</forkedProcessTimeoutInSeconds>
    </configuration>
</plugin>
~~~

You can configure Maven Failsafe similarly if integration tests run in forked JVMs:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.2.5</version>
    <configuration>
        <forkCount>1</forkCount>
        <reuseForks>true</reuseForks>
        <forkedProcessTimeoutInSeconds>300</forkedProcessTimeoutInSeconds>
    </configuration>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

These are plugin configuration snippets; merge them into your existing POM rather than creating duplicate plugin declarations. `forkedProcessTimeoutInSeconds` bounds the lifetime of the forked JVM, **not individual HTTP requests or single methods**.

### 5.1. forkCount and Concurrency

`forkCount` sets how many test JVM forks can run concurrently. For example, `forkCount=2` runs up to two test JVMs in parallel. `reuseForks=true` reuses forks across test classes per Surefire behavior.

Do not set a huge `forkCount` just because a CI runner reports many CPUs:

- Each JVM consumes heap, metaspace, threads, and file descriptors.
- Concurrent tests may contend for ports or database connections.
- CPU/memory contention can slow tests down and trigger false timeouts.
- Race conditions may cause failures that appear only under parallel execution.

The Maven reactor can also build modules in parallel via `-T`. Combining parallel Maven modules with increased Surefire forks multiplies total JVMs exponentially. Calculate total concurrency across both the reactor and test plugins.

### 5.2. Diagnostic Maven Commands

~~~bash
./mvnw -B -ntp test
./mvnw -B -ntp verify
./mvnw -B -ntp -T 2 test
~~~

- `test` runs the unit-test lifecycle.
- `verify` also runs integration tests/verification if configured in the POM.
- `-T 2` allows up to two Maven threads for reactor scheduling; this is a separate source of concurrency from Surefire's `forkCount`.

When investigating flaky tests, run a sequential pass to separate logic bugs from resource contention. Then re-enable bounded concurrency and record the runner configuration.

## 6. Gradle Test Workers and Concurrency

Gradle's `Test` task executes tests inside worker JVMs. You can bound the fork count:

~~~groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()
    maxParallelForks = 2
}
~~~

`maxParallelForks` limits concurrent test worker JVMs for that task. If multiple test tasks or multiple Gradle builds run simultaneously, total concurrency can still exceed this number.

### 6.1. When Should You Increase Workers?

Increase workers when:

- Test classes are independent and share no mutable state.
- Test databases/services use isolated namespaces or schemas.
- Ports are allocated dynamically or test servers use port 0.
- Runners have sufficient CPU, memory, and connection headroom.
- Test output/logging does not depend on execution order.

Keep workers low when:

- Tests share the same account or database records.
- Tests mutate global system properties or environment variables.
- Tests depend on ordering or shared filesystem paths.
- Docker daemon or registry faces resource limits.
- Runners have limited memory.

### 6.2. Do Not Use Parallelism to Mask Race Conditions

If a test passes sequentially yet fails when run concurrently, identify the shared resource:

- Fixed file path such as `target/test-output.json`.
- Hardcoded port `8080`.
- Shared database table row IDs.
- Static singletons or global caches.
- Shared queue/topic or consumer group.
- Fixed container names.
- Tests mutating the same system property.

Allocate unique resources per test/run ID, or guard truly shared resources with explicit locks. Never just bump timeouts to paper over contention.

## 7. ExecutorService: Running Concurrent Tasks Within Bounds

Use a bounded thread pool to prevent unbounded thread creation. `Executors.newFixedThreadPool(2)` creates a pool of at most two worker threads; excess tasks wait in a queue.

Java 17 example:

~~~java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class BoundedTasksDemo {

    private static String work(String name, long millis)
            throws InterruptedException {
        try {
            Thread.sleep(millis);
            return name + ": completed";
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw ex;
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);

        List<Callable<String>> tasks = List.of(
                () -> work("fast", 100),
                () -> work("slow", 5000)
        );

        try {
            List<Future<String>> results =
                    pool.invokeAll(tasks, 1, TimeUnit.SECONDS);

            for (int i = 0; i < results.size(); i++) {
                Future<String> result = results.get(i);

                if (result.isCancelled()) {
                    System.out.println("task " + (i + 1) + ": timed out");
                } else {
                    System.out.println(result.get());
                }
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw ex;
        } finally {
            pool.shutdownNow();

            try {
                if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
                    System.err.println("executor did not terminate");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 BoundedTasksDemo.java
java BoundedTasksDemo
~~~

With two independent tasks as shown, expected output in future list order is:

~~~text
fast: completed
task 2: timed out
~~~

`invokeAll(..., timeout, unit)` waits up to the specified duration and cancels unfinished tasks. `Future.isCancelled()` identifies canceled tasks. `shutdownNow()` asks workers to stop via interruption; `awaitTermination()` gives the application a bounded window to wait for workers to finish.

### 7.1. Why Call shutdown and awaitTermination?

- `shutdown()` stops accepting new tasks while letting submitted tasks finish.
- `shutdownNow()` requests interrupting active tasks and returns queued waiting tasks.
- `awaitTermination()` waits up to a limit for the pool to terminate completely.
- `Future.cancel(true)` sends an interrupt request to that task; it does not guarantee stopping an uncooperative task.

In the example, `slow` calls `Thread.sleep`, an interruptible API. If a task calls native code, an uninterruptible library, or a CPU loop that ignores interrupts, it can keep running. Tasks must be designed to cooperate with cancellation.

### 7.2. Never Create Unbounded Thread Pools per Test

Avoid `newCachedThreadPool()` or creating a fresh unmanaged pool per request or test. When many tests run concurrently and each spawns its own pool, thread counts can explode rapidly.

- Size bounded pools according to CPU/I/O workload.
- Configure bounded queues and backpressure.
- Close pools in the owning component or `finally`.
- Never hand a shut-down executor to the next test.
- Never let background tasks leak across test boundaries.

## 8. ProcessBuilder: Timeouts and Cleaning Up Child Processes

When tests need to run commands outside the JVM, use `ProcessBuilder` with an explicit argument list. Never concatenate untrusted input into a shell command string.

**Do not do this:**

~~~java
Runtime.getRuntime().exec("sh -c " + userInput);
~~~

Shell command strings can be parsed unexpectedly, are hard to quote safely, and make killing the full process tree harder.

Use:

~~~java
new ProcessBuilder("git", "status", "--short");
~~~

Each element is a discrete argument. `ProcessBuilder` does not invoke a shell when given an executable and arguments as a list.

### 8.1. Java 17 Runnable Example

Create `ProcessTimeoutDemo.java`:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class ProcessTimeoutDemo {

    static void runWithTimeout(List<String> command, Duration timeout)
            throws Exception {
        if (timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("timeout must be positive");
        }

        Path output = Files.createTempFile("process-output-", ".log");
        Process process = null;

        try {
            ProcessBuilder builder = new ProcessBuilder(command)
                    .redirectErrorStream(true)
                    .redirectOutput(output.toFile());

            process = builder.start();

            long timeoutMillis = Math.max(1L, timeout.toMillis());
            if (!process.waitFor(timeoutMillis, TimeUnit.MILLISECONDS)) {
                terminateTree(process);
                throw new TimeoutException(
                        "command exceeded " + timeoutMillis + " ms"
                );
            }

            String captured = Files.readString(output);
            if (process.exitValue() != 0) {
                throw new IOException(
                        "command exited with " + process.exitValue()
                                + System.lineSeparator() + captured
                );
            }

            if (!captured.isBlank()) {
                System.out.print(captured);
            }
        } finally {
            if (process != null && process.isAlive()) {
                terminateTree(process);
            }
            Files.deleteIfExists(output);
        }
    }

    private static void terminateTree(Process process)
            throws InterruptedException {
        List<ProcessHandle> descendants =
                process.toHandle().descendants().toList();

        // Request child processes to exit before the root process.
        for (int i = descendants.size() - 1; i >= 0; i--) {
            descendants.get(i).destroy();
        }

        process.destroy();

        // Allow a short window for graceful termination.
        process.waitFor(1, TimeUnit.SECONDS);

        // Force-stop surviving processes if graceful termination was insufficient.
        for (ProcessHandle child : descendants) {
            if (child.isAlive()) {
                child.destroyForcibly();
            }
        }

        if (process.isAlive()) {
            process.destroyForcibly();
        }

        process.waitFor(2, TimeUnit.SECONDS);
    }

    public static void main(String[] args) throws Exception {
        if (args.length > 0 && args[0].equals("child")) {
            System.out.println("child started");
            System.out.flush();
            Thread.sleep(30_000);
            return;
        }

        String executable = Path.of(
                System.getProperty("java.home"),
                "bin",
                System.getProperty("os.name").toLowerCase().contains("win")
                        ? "java.exe" : "java"
        ).toString();

        String classPath = System.getProperty("java.class.path");

        try {
            runWithTimeout(
                    List.of(
                            executable,
                            "-cp",
                            classPath,
                            ProcessTimeoutDemo.class.getName(),
                            "child"
                    ),
                    Duration.ofSeconds(1)
            );
            System.out.println("child completed");
        } catch (TimeoutException ex) {
            System.out.println("TIMEOUT: " + ex.getMessage());
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 ProcessTimeoutDemo.java
java ProcessTimeoutDemo
~~~

Exact stdout of the parent process:

~~~text
TIMEOUT: command exceeded 1000 ms
~~~

The child process writes `child started` to the temporary log file, while the parent times out before reading output; the file is deleted in `finally`. The example intentionally omits printing child logs to keep stdout deterministic.

### 8.2. Why Redirect Output to a File?

If you write:

~~~java
process.getInputStream().readAllBytes();
process.waitFor(timeout, TimeUnit.SECONDS);
~~~

the stream read can block indefinitely **before reaching `waitFor` timeout**. Furthermore, if the child writes lots of stdout/stderr that the parent never drains, the pipe buffer can fill up and block the child.

Three common patterns:

- Redirect stdout/stderr to a temporary file, wait for the process, then read the file as shown.
- Drain streams concurrently in a reader task with its own lifecycle and timeout.
- Redirect output to `DISCARD` if logs are unneeded, or to a CI-collected log file.

Never leave output pipes unconsumed when a process can emit substantial output.

### 8.3. ProcessHandle Descendants Are Best-Effort

`ProcessHandle.descendants()` captures a snapshot of child processes visible to the JVM when called. Processes may spawn additional children concurrently with cleanup; OS permissions, platforms, and daemonization can affect termination.

When test commands spawn complex process trees, run them inside a **container, cgroup, process group, or job object** with explicit ownership boundaries. Never run global commands like `killall java` or `taskkill /IM java.exe`, which can kill build/test processes belonging to other jobs.

### 8.4. Never Ignore Exit Codes

A process finishing within its timeout does not mean the command succeeded. Verify:

- Did `waitFor` return `true` or `false`?
- Is `exitValue()` `0` or non-zero?
- Do stdout/stderr contain errors that should be preserved?
- Are any descendant processes still alive?
- Did cleanup finish within budget?

Distinguish three outcomes: **completed successfully**, **completed with non-zero exit**, and **timed out/canceled**. Never collapse all of them into a single "done" boolean.

## 9. Waiting for Service Readiness Instead of Fixed Sleeps

Integration tests often start a Spring Boot app and send a request. Weak pattern:

~~~java
startApplication();
Thread.sleep(5000);
callEndpoint();
~~~

Five seconds can be unnecessarily slow on a fast machine yet too short on a busy CI runner. Poll readiness against a deadline instead:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class ReadinessCheck {

    public static void waitUntilReady(URI healthUri, Duration budget)
            throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();

        long deadline = System.nanoTime() + budget.toNanos();
        Exception lastFailure = null;

        while (System.nanoTime() < deadline) {
            HttpRequest request = HttpRequest.newBuilder(healthUri)
                    .timeout(Duration.ofSeconds(2))
                    .GET()
                    .build();

            try {
                HttpResponse<Void> response = client.send(
                        request,
                        HttpResponse.BodyHandlers.discarding()
                );

                if (response.statusCode() == 200) {
                    return;
                }
            } catch (Exception ex) {
                lastFailure = ex;
            }

            Thread.sleep(200);
        }

        throw new java.util.concurrent.TimeoutException(
                "service did not become ready within " + budget
                        + (lastFailure == null ? "" :
                        "; last failure: " + lastFailure)
        );
    }
}
~~~

This code uses Java 11+ APIs and runs on Java 17. `connectTimeout` bounds TCP connection establishment, `HttpRequest.timeout` bounds each request, and the polling loop enforces the overall deadline. The example accepts only HTTP 200; real services may use other readiness conventions.

**Never check liveness instead of readiness.** A process can be alive while the application context is still refreshing, database migrations are still running, or dependent services are unready.

## 10. Cleaning Up Spring Boot Apps, HTTP Servers, and Test Fixtures

When a test creates resources itself, the resource owner is responsible for closing them.

### 10.1. Use try/finally for Resources That Do Not Implement AutoCloseable

~~~java
var server = com.sun.net.httpserver.HttpServer.create(
        new java.net.InetSocketAddress("127.0.0.1", 0), 0
);

try {
    server.start();
    // Send HTTP requests and assert responses.
} finally {
    server.stop(0);
}
~~~

Port `0` asks the OS to assign a free ephemeral port. Read the bound port via `server.getAddress().getPort()`. Never hardcode `8080` across parallel tests.

### 10.2. Spring Boot Test Server with a Random Port

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApplicationHttpTest {

    @LocalServerPort
    int port;

    // Call endpoints using the dynamically assigned port.
}
~~~

The Spring test framework manages application context caching and lifecycles. If your tests also spawn external processes, servers, or containers outside that context, you must clean those up explicitly.

### 10.3. Cleanup in JUnit Lifecycle Methods

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ExternalProcessTest {

    private Process process;

    @BeforeEach
    void startFixture() throws Exception {
        // Start process fixture and keep handle.
    }

    @AfterEach
    void stopFixture() throws Exception {
        if (process != null && process.isAlive()) {
            process.destroy();
            if (!process.waitFor(1, java.util.concurrent.TimeUnit.SECONDS)) {
                process.destroyForcibly();
                process.waitFor(2, java.util.concurrent.TimeUnit.SECONDS);
            }
        }
    }

    @Test
    void checksFixture() {
        // Test.
    }
}
~~~

This is a condensed pattern; real projects should use a process-tree helper and capture logs before deleting temp files. `@AfterEach` runs after each test in normal JUnit flow, even on assertion failures. If the whole JVM receives `kill -9` or the runner vanishes abruptly, you cannot rely on this callback.

### 10.4. Cleanup Must Be Idempotent

Proper cleanup can be invoked multiple times without breaking state:

- Check whether a handle/resource exists before closing.
- Close sockets, servers, executors, and containers in dependency order.
- Save logs before deleting containers or temp directories.
- Never let a cleanup exception mask the original test failure.
- Bound how long shutdown is allowed to wait.
- Delete temporary directories only after processes stop writing into them.

In Java, `try-with-resources` fits `AutoCloseable`; `finally` fits coordinating multiple resources or process shutdowns.

## 11. Docker Containers in Integration Tests

When tests use Docker, assign a unique container name per job/test run. Avoid fixed names like `spring-test` if CI runs jobs concurrently.

Detached run example:

~~~bash
docker run -d \
  --name "$CONTAINER_NAME" \
  -p 127.0.0.1::8080 \
  "$IMAGE"
~~~

Docker assigns a random host port to container port 8080. Retrieve the port:

~~~bash
BINDING="$(docker port "$CONTAINER_NAME" 8080/tcp)"
HOST_PORT="${BINDING##*:}"
HEALTH_URL="http://127.0.0.1:$HOST_PORT/actuator/health"
~~~

If the Actuator health endpoint is absent from the image, substitute the application's readiness endpoint. Never assume `/actuator/health` is always enabled or public.

### 11.1. Waiting for Readiness with a Deadline

~~~bash
READY=0
DEADLINE=$((SECONDS + 30))

while (( SECONDS < DEADLINE )); do
  if curl --fail --silent "$HEALTH_URL" >/dev/null; then
    READY=1
    break
  fi
  sleep 1
done

if (( READY == 0 )); then
  echo "container did not become ready" >&2
  docker logs "$CONTAINER_NAME" >&2 || true
  exit 1
fi
~~~

Bash `SECONDS` counts elapsed seconds in the shell. The loop has a deadline and never waits forever. If image startup is slower, adjust the budget per environment and inspect logs rather than removing the timeout.

## 12. Shell Trap: Cleanup When Scripts Pass or Fail

In Bash on Linux CI, `trap` ensures cleanup runs whether the script exits normally or fails:

~~~bash
#!/usr/bin/env bash
set -Eeuo pipefail

CONTAINER_NAME="spring-it-$CI_JOB_ID-$$"
IMAGE="example/spring-service:test"

cleanup() {
  STATUS=$?
  trap - EXIT INT TERM

  docker logs "$CONTAINER_NAME" >&2 || true
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

  exit "$STATUS"
}

trap cleanup EXIT

docker run -d \
  --name "$CONTAINER_NAME" \
  -p 127.0.0.1::8080 \
  "$IMAGE"

BINDING="$(docker port "$CONTAINER_NAME" 8080/tcp)"
HOST_PORT="${BINDING##*:}"
HEALTH_URL="http://127.0.0.1:$HOST_PORT/actuator/health"

READY=0
DEADLINE=$((SECONDS + 30))
while (( SECONDS < DEADLINE )); do
  if curl --fail --silent "$HEALTH_URL" >/dev/null; then
    READY=1
    break
  fi
  sleep 1
done

if (( READY == 0 )); then
  echo "readiness timeout" >&2
  exit 1
fi

curl --fail --show-error "$HEALTH_URL"
~~~

`cleanup` saves the original exit status, clears traps to prevent recursion, captures container logs, and force-removes the container. `|| true` applies only to secondary cleanup calls so a `docker logs` failure does not mask the primary error.

**Limitation:** traps cannot guarantee execution if the runner loses power, receives `kill -9`, or is reclaimed abruptly. Ephemeral CI runners and runner-level container labels/TTLs/orphan cleanup remain valuable.

Never share a fixed `CONTAINER_NAME` across parallel jobs. Combine the CI job/run ID with the process ID to prevent collisions; substitute equivalent IDs for other CI providers.

## 13. CI Job Timeouts and Cancellation

The CI timeout is the outermost guardrail. GitHub Actions example:

~~~yaml
jobs:
  integration-tests:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - name: Verify
        run: ./mvnw -B -ntp verify
~~~

`timeout-minutes` bounds the entire job. It does not replace test-level or process-level cleanup. When a job is canceled or times out, the CI runner sends stop signals; cleanup behavior depends on the runner, shell, and remaining grace period.

A CI pipeline should:

1. Set the job timeout larger than total test budgets plus a cleanup margin.
2. Apply timeouts to individual network calls and subprocesses rather than waiting for the job deadline.
3. Fail fast on unrecoverable errors; never retry indefinitely.
4. Capture logs and artifacts before cleanup if needed for investigation.
5. Assign unique IDs to containers, temp dirs, schemas, queues, and ports.
6. Clean up resources via `trap`, `finally`, or `@AfterEach`.
7. Scope runner-level orphan cleanup by label/job ID in case runners are aborted suddenly.
8. Never kill all Java processes on a shared runner; stop only processes owned by that job/test.

### 13.1. Timeouts and Retries Must Share a Budget

For example, a 5-second HTTP request timeout with at most two retries. Total duration must not exceed the integration test deadline. If each retry waits 5 seconds plus a 5-second backoff, total time escalates quickly.

Use bounded exponential backoff with jitter for transient errors; never retry authentication errors, invalid configuration, assertion failures, or non-retryable 4xx errors. As the deadline approaches, stop retrying and begin cleanup.

## 14. Concurrency and Shared Resources

Parallel execution speeds up independent tests, yet these shared resources frequently conflict:

| Resource | Failure Mode Under Concurrency | Isolation Strategy |
| --- | --- | --- |
| TCP port | Address already in use | Port 0 or random host port; query bound port |
| Temp directory/file | Tests overwrite or read each other's files | Unique directory per test/run ID |
| Database | Shared records/schemas; tests wipe each other's data | Isolated schema/database, transactions, or unique IDs |
| Docker container | Name or volume collisions | Unique names and job-scoped labels |
| Message broker | Consumers steal messages; queues retain leftover data | Isolated topic, queue, or consumer group |
| External API quota | Rate limits and test flakiness | Bounded concurrency, mocks/stubs, or isolated test quotas |
| JVM system properties | Tests overwrite shared global config | Avoid mutating globals; serialize tests when required |
| Filesystem locks | One test holds lock, another times out | Small lock scopes and `finally` cleanup |

### 14.1. Calculating Total Concurrency

Example:

- CI runs 3 matrix jobs.
- Each Maven job builds 2 modules in parallel.
- Each module's Surefire spawns 3 forks.

Theoretical peak is up to 18 test JVMs, before counting application processes and Docker containers. At 512 MB heap per JVM, heap alone could require around 9 GB before overhead.

Never tune each layer independently while ignoring total worker count. Balance CPU, RAM, file descriptors, database connections, registry pulls, and API quotas.

### 14.2. Bounded Queues and Backpressure

`Executors.newFixedThreadPool` uses an unbounded queue by default. Under heavy task volume, queued tasks can grow and pin lots of objects in memory. When controlled load is needed, construct a `ThreadPoolExecutor` with a bounded queue and explicit rejection policy:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ThreadPoolExecutor executor = new ThreadPoolExecutor(
        4,
        4,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(20),
        new ThreadPoolExecutor.AbortPolicy()
);
~~~

At most four workers and twenty queued tasks. When the queue fills, `AbortPolicy` throws `RejectedExecutionException`; callers must handle backpressure and rejection. Never silently drop tasks when test results must be complete.

## 15. Interruption: Tasks Must Cooperate with Stopping

Long-running code should poll the interrupt flag or call interruptible blocking APIs:

~~~java
void pollUntilDone() throws InterruptedException {
    while (!Thread.currentThread().isInterrupted()) {
        checkStatus();
        Thread.sleep(200);
    }
}
~~~

When catching `InterruptedException`:

~~~java
try {
    Thread.sleep(1000);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw ex;
}
~~~

Restore the interrupt flag if not propagating the exception directly, or rethrow to the caller. Never catch and swallow interruption:

~~~java
try {
    blockingOperation();
} catch (InterruptedException ignored) {
    // Must not silently swallow if callers rely on stopping the task.
}
~~~

`Future.cancel(true)` and `ExecutorService.shutdownNow()` send interrupt requests, not force-kills. If a library ignores interruption, rely on its dedicated timeout/cancel API or isolate it in a subprocess or container for a stronger termination boundary.

## 16. Cleanup Ordering and Preserving Failure Evidence

When an integration test fails, proper cleanup order keeps diagnostic logs intact:

~~~text
Test assertion / request fails
          |
          v
Capture application + container logs
          |
          v
Stop HTTP clients / scheduled tasks
          |
          v
Stop application process / child processes
          |
          v
Stop containers and close connections
          |
          v
Delete temp files / schemas / queues
          |
          v
Return original test failure to CI
~~~

Key principles:

- **Capture logs before removing containers or processes.** Deleting first destroys the evidence.
- Close clients/connections before tearing down server or database fixtures.
- Stop scheduled executors before deleting temp directories they still write to.
- Use `finally`, `@AfterEach`, `@AfterAll`, `AutoCloseable`, or CI traps aligned with resource ownership.
- Bound cleanup with timeouts; never let shutdown hang forever.
- Preserve the original exception. If cleanup also throws, log it as suppressed/secondary rather than masking the primary test failure.
- Clean up by job ID/label; never delete another job's containers or files.
- On test retries, ensure the prior attempt cleaned up completely before starting the next attempt.

### 16.1. Do Not Rely Solely on Shutdown Hooks for Cleanup

JVM shutdown hooks help during normal exits, yet are not guaranteed to run under `kill -9`, lost runners, or abrupt host shutdowns. Use hooks as a secondary safety net alongside `finally`, test lifecycles, and CI resource ownership.

### 16.2. Cleanup After Test Failures and Timeouts

- On assertion failures, `@AfterEach` remains the right place to close resources.
- If `@Timeout` interrupts a test thread, cleanup code must handle the interrupted state cleanly.
- On subprocess timeouts, the parent must stop the process and descendants before deleting logs/temp dirs.
- On CI cancellations, traps may execute during the grace window; otherwise runner-level orphan cleanup sweeps remaining resources.
- On container crashes, capture logs and exit codes before removing the container.

## 17. Anti-Patterns and Common Mistakes

| Anti-Pattern / Symptom | Why It Is Dangerous | Fix |
| --- | --- | --- |
| `Thread.sleep(5000)` to wait for a service | Slow or flaky depending on runner speed | Poll readiness against a deadline |
| HTTP client without timeouts | Threads/sockets can hang until CI job timeout | Set connect, request, and read timeouts |
| `assertTimeout` on code that can hang | Waits for callback completion before checking | Use preemptive timeout carefully or API-level timeouts |
| Assuming `Future.cancel(true)` kills tasks instantly | Interruption is a cooperative request | Tasks check interrupts; isolate in processes/containers when needed |
| Reading process output before `waitFor(timeout)` | Can block forever or deadlock pipes | Redirect to file or drain streams concurrently |
| Calling only `process.destroy()` | Process may ignore graceful signal; children survive | Graceful wait then force-kill scoped process tree |
| Running `killall java` | Can kill Maven/Gradle or unrelated jobs | Stop only test-owned handles and containers |
| Thread pool never shut down | JVM hangs; tasks leak across tests | Call `shutdownNow` and `awaitTermination` |
| Overly large fixed pool | Memory/CPU contention slows tests | Bound concurrency to total runner capacity |
| Hardcoded port `8080` | Parallel tests collide on port | Use port `0` or random host ports |
| Fixed container name | Concurrent jobs collide | Use unique names + job ID |
| Cleanup deletes logs before saving them | Destroys root-cause evidence | Capture logs prior to removal |
| Cleanup exception masks assertion failure | CI displays wrong primary error | Preserve original exception; log/suppress cleanup error |
| Outer timeout smaller than inner timeout | CI kills runner before cleanup finishes | Layer deadlines and reserve margin |
| Infinite retries | Prolongs jobs and overloads dependencies | Bound retries, share deadline, use backoff |
| Shared `SNAPSHOT`/test data | Non-repeatable tests | Use immutable versions and unique test data |
| Relying solely on CI job timeout | Unclear which step hung; hard to clean up | Set test/request/process and job timeouts |
| Assuming shutdown hooks always run | Skipped on force-kill or host loss | Combine owner cleanup with ephemeral runners/orphan policies |

## 18. Practice Exercises and Completion Criteria

Practice in an experimental branch of a Spring Boot project:

1. Add JUnit `@Timeout` to a test that can hang; distinguish test timeouts from HTTP client timeouts.
2. Write a readiness polling helper using `System.nanoTime()` and a shared deadline; avoid fixed sleeps.
3. Run `BoundedTasksDemo.java` with two tasks, confirming the fast task completes and the slow task is canceled after one second.
4. Ensure executors invoke `shutdownNow()` and `awaitTermination()` inside `finally`.
5. Run `ProcessTimeoutDemo.java` with Java 17; verify the parent catches `TimeoutException` after 1000 ms and requests child termination.
6. Verify output redirection prevents pipe deadlocks; keep exit codes distinct from timeouts.
7. Configure Surefire/Failsafe forked process timeouts and bounded concurrency.
8. Configure Gradle `maxParallelForks` to match CI resources, then run sequentially and in parallel to catch races.
9. Start a Spring Boot integration test server on a random port and poll HTTP readiness.
10. Run a Docker container detached with a unique name, random host port, and deadline-bounded health polling.
11. Add a Bash `trap` to save logs and remove the container on script exit/failure.
12. Intentionally break the health endpoint; verify the script fails within the timeout and cleans up the container.
13. Cancel a CI job; inspect logs, leftover processes/containers, and runner cleanup behavior.
14. Run multiple jobs concurrently; verify temp directories, database schemas, queue names, ports, and container names never collide.
15. Measure total concurrency across CI matrix × Maven reactor × Surefire forks/Gradle workers.
16. Document timeout budgets, resource owners, cleanup order, and log evidence in CI documentation.

**Completion criteria:** no test, process, or container waits forever; timeouts trigger controlled cancellation; concurrency stays bounded; child processes and resources are cleaned up across pass, fail, and timeout paths; CI preserves logs and returns the exit status of the original failure.

## Official References

- [Java 17 – Process API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Process.html)
- [Java 17 – ProcessHandle API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessHandle.html)
- [Java 17 – ExecutorService API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java 17 – Future API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [JUnit 5.10 – Timeout for Tests](https://junit.org/junit5/docs/5.10.2/user-guide/#writing-tests-timeouts)
- [Maven Surefire – Fork Options and Timeouts](https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options-and-timeouts.html)
- [Maven Failsafe Plugin – Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Gradle – Java Testing](https://docs.gradle.org/current/userguide/java_testing.html)
- [Docker – Run Containers](https://docs.docker.com/engine/containers/run/)
- [Docker – Stop Containers](https://docs.docker.com/reference/cli/docker/container/stop/)
- [GitHub Actions – Workflow Syntax: timeout-minutes](https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions#jobsjob_idtimeout-minutes)