# Port, thread, or resource still alive after tests finish

## 1. Why does JUnit report green yet the process refuses to exit?

You run `mvn test`. Inside your IDE, the test method already shows a green checkmark; several seconds later, Maven still has not returned the prompt. Or the first test starts an HTTP server on port 8080 and the second fails with `Address already in use`. Or CPU keeps spiking even after JUnit finished; the console still logs output from `@Scheduled`; a PostgreSQL Testcontainers container still shows as running; or another test accidentally connects to a WireMock server started by an earlier test.

These symptoms can come from **two completely different lifecycle categories**:

- **Legitimately live resources**: Spring TestContext **caches the `ApplicationContext` across test methods and classes**, so an embedded web server, Hikari pool, listener container, or executor Spring bean legitimately remains active until the context actually closes. A test method ending does **not** mean the context or every Spring-managed resource should shut down immediately.
- **Resource leaks**: test or application code directly creates `new ServerSocket`, `Executors.newSingleThreadExecutor()`, an HTTP client, a `Scheduler`, a file stream, a `Thread`, or a Docker container **without an owner or matching cleanup lifecycle**. The resource outlives its intended boundary, cross-contaminating the suite or preventing the JVM from exiting.

This lesson belongs to **Test Troubleshooting**. The goal is to accurately identify **which resource is still alive, who owns it, when it should close, and what evidence proves it closed**—instead of spotting a Tomcat/Hikari thread name and immediately calling it a “memory leak”.

### After this lesson, you will be able to

1. Distinguish the lifecycles of a `@Test`, a JUnit test class, a cached Spring `ApplicationContext`, a JVM fork, Docker/Testcontainers resources, and external services.
2. Recognize `BindException: Address already in use`, `Connection refused`, Surefire forks failing to exit, hanging non-daemon threads, and resource contention.
3. Use `@SpringBootTest(webEnvironment = RANDOM_PORT)` properly without holding a fixed HTTP port across incompatible integration tests.
4. Explain why `@DirtiesContext` closes the context yet is **not a cleanup mechanism for every resource** and should not be overused.
5. Use Spring `@Bean` destroy callbacks, `@PreDestroy`, `DisposableBean`, `SmartLifecycle`, and `ThreadPoolTaskExecutor` to manage resources.
6. Use Java `AutoCloseable`/try-with-resources, `ExecutorService.shutdown()`/`awaitTermination()`, and `Future.get(timeout)` in tests.
7. Distinguish daemon vs non-daemon threads, blocked threads, threads alive because the context stays open, and genuine leaked threads.
8. Diagnose using `jps`, `jcmd Thread.print`, `jstack`, `ss`, `lsof`, `netstat`, `Get-NetTCPConnection`, or JFR without destroying evidence.
9. Understand pitfalls around `@Async`, `@Scheduled`, Reactor Netty, servlet servers, Hikari, Testcontainers, embedded Kafka/WireMock, and file descriptors.
10. Write regression tests proving a port is released after an **isolated context** closes, an executor Spring bean shuts down, and test-owned sockets close.
11. Avoid asserting JVM-wide thread counts must be 0 or “no ports in LISTEN state” after every `@Test`, since other components may legitimately remain running.
12. Work with a **Java 17 + Spring Boot 3.5.16 + Maven + JUnit 5** project illustrating both a full Spring context and explicitly closed isolated contexts/resources.
13. Design CI diagnostics with timeouts, thread dumps, process owner/PID tracking, resource-close checks, and sound lifecycles.
14. Report the true root cause instead of bumping timeouts, rotating ports blindly, or relying on `kill -9` as a workaround.

## 2. Four lifecycle clocks to map clearly

~~~text
JVM / Maven Surefire fork
  |
  +-- JUnit test class A
  |     |
  |     +-- @BeforeAll
  |     +-- @BeforeEach -> @Test -> @AfterEach
  |     +-- ...
  |     +-- @AfterAll
  |
  +-- JUnit test class B
  |     |
  |     +-- @BeforeEach -> @Test -> @AfterEach
  |
  +-- Spring TestContext cache (per JVM)
  |     |
  |     +-- ApplicationContext key K
  |           |
  |           +-- embedded server / port
  |           +-- ThreadPoolTaskExecutor
  |           +-- HikariDataSource
  |           +-- listeners/schedulers
  |           +-- Spring-managed Testcontainers beans
  |
  +-- Unmanaged resources created by test/application
  |     |
  |     +-- new Thread(...)
  |     +-- Executors.newScheduledThreadPool(...)
  |     +-- new ServerSocket(...)
  |     +-- file stream / HTTP client / Process
  |
  +-- JVM exit / context cache shutdown hook
        |
        +-- cached contexts are closed
        +-- Spring-managed beans destroyed
        +-- remaining non-daemon/blocked/shutdown hooks
             may delay or interfere with termination
~~~

**Key insight:** `@AfterEach` only ensures that the JUnit callbacks for that test invocation completed under normal lifecycle rules; it does **not** mean all Spring singleton beans have been destroyed. The Spring TestContext cache lets test classes with matching configurations save startup time; a context may only close upon `@DirtiesContext`, LRU eviction, or the JVM shutdown hook.

### 2.1. Owners and proper release milestones

| Resource | Typical owner | Expected release point | True leak symptom |
| --- | --- | --- | --- |
| `@TempDir` directory | JUnit | End of extension/test scope | Open file handle prevents temp directory deletion |
| Test-created `ServerSocket` | Test method/fixture | `try-with-resources` or `@AfterEach` | Port remains `LISTEN` after fixture closes |
| Test-created `ExecutorService` | Test fixture | `shutdown` + bounded await | Non-daemon worker stays alive after test |
| Spring `ThreadPoolTaskExecutor` bean | `ApplicationContext` | Context close / Spring destroy lifecycle | Worker threads remain after **context close** |
| Embedded Tomcat/Jetty/Netty | `ApplicationContext` | Context close | Port remains `LISTEN` after close and grace period |
| `HikariDataSource` | `ApplicationContext` | Bean destroy / context close | Pool threads/connections remain after close |
| `@Scheduled` jobs | Scheduler + context | Scheduler stop / context close | Scheduled task still causes side effects unintentionally |
| Testcontainers `@Container` | JUnit extension | Per-method or per-class per annotation | Container fails to stop per declared JUnit lifecycle |
| Testcontainers `@Bean` | Spring `ApplicationContext` | When context closes | Container stays running after the context actually closes |
| Manual singleton Testcontainers | Test suite / JVM | Explicit owner stop / JVM cleanup | Outlives owner lifetime or breaks shared tests |
| Reactor scheduler from `Schedulers.new...` | Call site | `dispose()` within owner scope | `reactor-*` thread from custom scheduler persists |
| HTTP client / socket pool | Library owner or Spring bean | Client close / destroy | TCP connections/threads persist after close |
| Borrowed JDBC `Connection` | Caller / service | Returned to pool after operation | Pool exhaustion, connection leak |
| Open file `InputStream` | Caller | Try-with-resources | File descriptor count climbs across tests |
| OS child process | Test / launcher | Process exit/destroy + bounded wait | Child PID keeps running after suite ends |

A resource can stay alive inside the **application context cache** without being a leak. Judge survival against the **owner's lifetime**, not merely the end of a single test method.

### 2.2. What does “the test finished” actually mean?

- **JUnit test method complete**: The method's assertions and callbacks have finished.
- **Test class complete**: `@AfterAll` has run; the Spring context **may** still stay cached.
- **ApplicationContext closed**: Spring invokes stop/destroy callbacks for beans it manages.
- **Surefire fork exited**: The forked JVM terminated; no Java threads from that fork remain.
- **Docker container stopped**: The Docker resource ended—distinct from its Java wrapper object being garbage-collected.
- **Network port released**: The OS no longer holds a listening socket on that address/protocol/port—distinct from the test finishing.

When debugging, specify exactly which milestone you are checking. “Port still open after test method” can be completely expected; “port still open after `context.close()` in an isolated test” warrants investigation.

## 3. Quick symptom-based triage

### 3.1. `mvn test` finishes yet the terminal hangs

Symptoms:
- Surefire reports all tests finished, yet the build refuses to exit.
- The JVM still holds active non-daemon platform threads.
- Stack dumps show workers from `newSingleThreadExecutor`, a scheduler, or a stuck shutdown hook.
- An `@AfterAll` blocks on an unbounded `CountDownLatch.await()`.
- A thread `join` or `Future.get` waits without a timeout.
- A test-spawned child process is still running or has undrained I/O streams.

**Do not conclude from a single thread name:** Hikari housekeeper, Tomcat, JUnit, Attach Listener, `ForkJoinPool`, GC, and test runners can all have valid threads. Focus on **non-daemon threads + owner + stack trace + context close timing**.

Maven Surefire forks have their own shutdown timeout; some versions/configurations force-halt after waiting a period for non-daemon threads. Thus a leak may look like a **long pause followed by a forced fork halt** rather than hanging forever. Never say “Maven eventually exited, so there is no leak”.

### 3.2. `BindException` or port already in use

Example:

~~~text
java.net.BindException: Address already in use: bind

org.springframework.boot.web.server.WebServerException:
  Unable to start embedded Tomcat
~~~

Possible causes:
- Another process is already listening on fixed `server.port=8080`.
- Test A opened a raw server on that port and forgot to close it.
- Spring Context A stays cached, so the port is still legitimately in use.
- Two Spring contexts configure `DEFINED_PORT` and run in parallel.
- Test B attempts to reuse a mapped Docker or host port incorrectly.
- A lingering process from a prior IDE/build run never exited.

**Identify the owning PID and socket state** before fixing. Switching to a random port prevents collisions across independent contexts, yet it does not cure leaks or fix mismatched ownership.

### 3.3. `Connection refused` right after another class

This can be the **opposite** of a leak: the backend closed too early while a cached Spring context or client stayed alive.

Example:
- JUnit stops `static @Container` at the end of Class A.
- Spring TestContext retains `DataSource` inside the cached context for Class B.
- Class B hits the dead port → `Connection refused`.

When a backing resource stops **before** its consumers, synchronize lifetimes (Spring-managed Testcontainers `@Bean @ServiceConnection` or explicit singleton ownership) instead of reaching for `shutdownNow`.

### 3.4. Logs keep printing after assertions finish

Possible causes:
- A scheduled job keeps firing.
- An async worker has not completed yet.
- A Kafka/Rabbit listener continues consuming messages.
- Delayed retries/backoffs are still executing.
- In-flight requests remain active.
- The cached context stays open, keeping scheduled components active.

If that background activity is **unwanted** inside tests, disable scheduling via profiles/properties, invoke jobs manually, await worker completion, or close dedicated isolated contexts. Never assume `@SpringBootTest` disables `@Scheduled` automatically.

### 3.5. A test passes alone yet fails in the full suite

Inspect primarily for:
- Fixed ports or shared singletons.
- Stateful static fields and caches.
- Unmanaged executors left behind by earlier tests.
- Per-class Testcontainers stops vs cached Spring contexts.
- WireMock server lifecycles.
- `@DirtiesContext` triggered by another class.
- Full-table deletes or Redis `FLUSHALL` in a parallel suite.
- Mock/stubbing overriding beans inside a shared Spring context.

Running one class alone uses a fresh JVM/context with no lingering resources, which is why cross-class bugs vanish in isolation.

## 4. Network ports: understanding `LISTEN`, `ESTABLISHED`, and `TIME_WAIT`

### 4.1. Server listening ports

An HTTP server typically binds a TCP socket in `LISTEN` state. When the server stops, its listener socket must close. Verify:
- PID / socket owner;
- bind address (IPv4, IPv6, loopback, or all interfaces);
- protocol (TCP/UDP);
- port.

`127.0.0.1:8080` and `0.0.0.0:8080` can conflict. Dual-stack IPv4/IPv6 behavior also depends on the OS. Do not grep merely for `"8080"` and assume you found the right process.

### 4.2. `ESTABLISHED` does not mean the listener is still open

HTTP clients with keep-alive can maintain `ESTABLISHED` connections. When the server shuts down or connections close, sockets transition through `FIN_WAIT`, `CLOSE_WAIT`, and `TIME_WAIT` per the TCP state machine.

A `TIME_WAIT` socket still appearing in `netstat` **does not prove** the HTTP server is still `LISTEN`ing or leaking Java threads. The OS manages TCP connection teardown; watch closely when diagnosing ephemeral vs remote port numbers.

### 4.3. Inspect the exact address and port

Example:

~~~text
Local Address        State          PID      Assessment
127.0.0.1:18081      LISTEN         12345    Listener on loopback
0.0.0.0:18081        LISTEN         45678    Listener on all IPv4 interfaces
127.0.0.1:18081      TIME_WAIT      -        Old connection, not a listener
127.0.0.1:54321      ESTABLISHED    12345    Client or server connection
~~~

This is an illustrative table, not measured output. When tests collide on a port, inspect the **PID of the `LISTEN` endpoint**, then verify its command line and JVM identity.

### 4.4. Random ports in Spring Boot tests

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpTest {
    @LocalServerPort
    int port;
}
~~~

`RANDOM_PORT` lets the OS pick an available port (Boot effectively configures `server.port=0`), avoiding hardcoded 8080. `@LocalServerPort` injects the bound port. **Never** read a port from static config or guess it.

However, `RANDOM_PORT`:
- Does not force resources to close at the end of every `@Test`.
- Does not convert your raw `new ServerSocket` into a Spring bean.
- Does not cure non-daemon executor leaks.
- Does not replace cleanup policies when apps spawn numerous background workers.
- Does not eliminate resource exhaustion if too many simultaneous contexts are created.

### 4.5. `WebEnvironment` and real sockets

| `@SpringBootTest` web environment | Embedded server? | Port usage |
| --- | --- | --- |
| `MOCK` (default) | Usually mock servlet/reactive web context, no HTTP socket bound | No listener port needed |
| `RANDOM_PORT` | Embedded server when appropriate web stack present | OS assigns dynamic port |
| `DEFINED_PORT` | Embedded server on configured port | Prone to collisions |
| `NONE` | Non-web application context | No HTTP listener |

Service-only tests need no HTTP port and can use `NONE`; controller tests via MockMvc usually use `@WebMvcTest`/`@AutoConfigureMockMvc`. When true HTTP/TCP behavior is required, choose `RANDOM_PORT`.

### 4.6. Never misuse port 0

Port 0 means “ask the OS for an ephemeral available port” **when binding a server socket**, after which clients must connect to the **actually bound port**, never to `127.0.0.1:0`. With Testcontainers, internal container ports and mapped host ports also differ; retrieve `getMappedPort`/service connection details.

## 5. Threads: what keeps the JVM alive?

### 5.1. Daemon vs non-daemon

Every Java platform thread has a daemon flag:
- **Non-daemon threads** keep the JVM alive while running unless the process is halted/killed or shutdown is forced.
- **Daemon threads** do not keep the JVM alive; the JVM exits once only daemon threads remain.
- Being a daemon does not mean “cleanly stopped”: a daemon thread can still hold open files, sockets, or DB connections and mutate shared state mid-suite.

Calling `Thread#setDaemon(true)` to hide an executor leak is not a fix. Assign clear ownership, stop/cancel tasks, and perform bounded waits; daemon flags belong strictly to overall runtime policy.

### 5.2. Manually created `ExecutorService`

Anti-pattern:

~~~java
@Test
void badExample() {
    ExecutorService executor =
            Executors.newSingleThreadExecutor();

    executor.submit(() -> {
        while (!Thread.currentThread().isInterrupted()) {
            // work
        }
    });

    // No shutdown, no waiting for the task to finish.
}
~~~

This is an **anti-pattern snippet**, excluded from the runnable project. On JDK 17, `newSingleThreadExecutor` defaults to non-daemon threads; without shutdown and task termination, the fork can hang or delay exit unexpectedly. Adding `Thread.sleep` or an unrelated `@AfterEach` elsewhere will not stop this thread.

Right approach:

~~~java
ExecutorService executor =
        Executors.newSingleThreadExecutor();

try {
    Future<String> future =
            executor.submit(() -> "done");

    String result = future.get(3, TimeUnit.SECONDS);
    assertThat(result).isEqualTo("done");
}
finally {
    executor.shutdown();
    if (!executor.awaitTermination(
            5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        if (!executor.awaitTermination(
                5, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                    "executor did not terminate");
        }
    }
}
~~~

This snippet requires JUnit/AssertJ/concurrency imports; the complete runnable version appears in the lab. Never call `shutdownNow` expecting instant magic if tasks ignore interruption—it relies on cooperative interruption. Tasks blocked in uninterruptible native I/O or ignoring interrupts can exceed the termination deadline.

### 5.3. `Future.get` timeouts do not replace executor cleanup

`future.get(3, SECONDS)` bounds only how long the caller waits for a result. Upon timeout, the background task may keep running. Always cancel/shut down with an explicit policy, await termination, and then clean up fixtures. Never treat a future timeout as proof the worker actually stopped.

### 5.4. `ThreadFactory` and meaningful names

Thread names reveal owners quickly:

~~~java
ThreadFactory factory = task -> {
    Thread thread =
            new Thread(task, "payment-test-worker");
    thread.setDaemon(false);
    return thread;
};
~~~

This snippet creates only a factory without an executor. In production, use component prefixes (`"invoice-worker-"`, `"sync-listener-"`) plus metrics. Generic names like `Thread-1` make thread dumps painful to analyze.

### 5.5. `ThreadLocal` and MDC leaks

Thread pools reuse threads. If a task sets `ThreadLocal`/MDC values without restoring them:
- Task B inherits Task A's correlation ID.
- Sensitive context leaks across requests.
- Even idle pooled threads retain object references until overwritten or cleared.

Use `try/finally`:
- Capture the prior context.
- Set the new context.
- Execute the task.
- Restore the prior context or remove it if previously null.

Do not confuse a `ThreadLocal` leak with a non-daemon thread hang; they are distinct failure modes that can occur together.

### 5.6. Read thread states alongside stack traces

Thread dumps show states such as:
- `RUNNABLE`: executing Java code or native I/O.
- `WAITING`: waiting indefinitely, e.g., `LockSupport.park`.
- `TIMED_WAITING`: timed wait/sleep/park.
- `BLOCKED`: waiting to enter an intrinsic monitor lock.
- Native stack/selector: I/O polling.

A worker thread `WAITING` on an idle task queue inside an **open cached context executor** can be completely valid. A worker `WAITING` after its owner closed and should have terminated indicates a problem. Always correlate thread names and stacks with owner lifecycles rather than reacting to state alone.

## 6. Spring-managed executors and schedulers

### 6.1. `ThreadPoolTaskExecutor` as a managed bean

Spring `ThreadPoolTaskExecutor` implements Spring lifecycle and destruction callbacks. Register it as a `@Bean` so Spring manages shutdown when the context closes:

~~~java
@Bean("diagnosticExecutor")
ThreadPoolTaskExecutor diagnosticExecutor() {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

    executor.setThreadNamePrefix("diag-managed-");
    executor.setCorePoolSize(1);
    executor.setMaxPoolSize(2);
    executor.setQueueCapacity(10);
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(5);

    return executor;
}
~~~

Spring initializes the executor bean and invokes its destroy hook on context close. `setWaitForTasksToCompleteOnShutdown(true)` prioritizes draining queued/running tasks; `setAwaitTerminationSeconds(5)` caps shutdown waiting. **This is a trade-off, not a universal recipe:**
- Some tasks must finish because they persist critical work.
- Other tasks should cancel immediately because external dependencies are shutting down.
- Tasks with infinite loops still ignore a 5-second grace period unless cancelled properly.
- Large queues require shutdown timeouts aligned with SLAs and draining capacity.
- Spring Framework 6.2 adds lifecycle phases/options affecting shutdown ordering; inspect actual configuration rather than assuming every scheduler stopped early.

### 6.2. Spring Boot task execution auto-configuration

Spring Boot 3.5 auto-configures an `AsyncTaskExecutor` when no conflicting custom executor exists. Registering custom `Executor` beans can cause Boot's auto-configuration to back off. For Spring MVC async handling/WebFlux/GraphQL, Boot enforces specific rules around the `applicationTaskExecutor` bean name in several integration paths.

**Important:** Never register `@Bean ExecutorService` and simply assume `@Async` picks it up automatically; resolution depends on `@EnableAsync`, `AsyncConfigurer`, bean names/types, and Boot properties. Tests should verify tasks actually execute on the expected executor and shut down properly.

### 6.3. Spring task shutdown properties

Properties like:

~~~properties
spring.task.execution.pool.max-size=16
spring.task.execution.pool.queue-capacity=100
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=10s
~~~

configure Boot's **auto-configured task executor**, and do not automatically override a custom manually constructed `ThreadPoolTaskExecutor` like the one in the lab. When declaring custom beans, configure setters or builders explicitly instead of assuming properties control every pool.

### 6.4. `@Scheduled` tasks can fire during tests

When an app declares `@EnableScheduling` + `@Scheduled`:
- The scheduler activates inside the context.
- `@SpringBootTest` triggers real scheduled executions.
- Because contexts are cached, jobs continue firing between test methods and classes.
- Jobs can mutate DB/caches right during test setup or teardown.
- Console logs can keep appearing after test assertions pass.

This is not inherently a leak, yet it causes **test isolation violations**. Design cleanly:
- Decouple business job logic from the schedule trigger.
- Unit/integration test the job method by calling it directly.
- Gate `@EnableScheduling`/trigger configuration behind profiles or conditional properties in tests.
- For scheduler integration tests, use dedicated test config, completion latches, or virtual clocks where suitable.
- Close contexts/schedulers per owner.

### 6.5. Dedicated profile for scheduling

Pattern:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("scheduled")
@EnableScheduling
class SchedulingConfiguration {
}
~~~

This snippet needs corresponding imports; excluded from the main Maven lab. Under `@ActiveProfiles("test")` without `"scheduled"`, scheduling from this config stays disabled. Still audit the entire configuration graph in case another `@EnableScheduling` or custom bean starts its own scheduler.

### 6.6. `@Async` and completion

`@Async` normally dispatches via a Spring proxy; self-invoking `this.asyncMethod()` bypasses the proxy and runs synchronously. When testing:
- Invoke through the Spring-managed proxy.
- Await `CompletableFuture`/`Future` completion with bounded timeouts.
- Identify the owning executor.
- Ensure pending async work cannot mutate fixtures after `@AfterEach`.
- Disable scheduling only where unneeded—never turn off async infrastructure when testing `@Async` itself.

### 6.7. `SmartLifecycle` and shutdown phases

Spring `SmartLifecycle` supports auto-start, asynchronous stop callbacks, and phase ordering. When a context closes, phases stop listeners, servers, executors, and dependent beans in order; Spring Boot 3.5 graceful web shutdown participates in this lifecycle.

Custom non-Spring threads remain **invisible to the framework**. To join lifecycle management properly, wrap resources in beans implementing `AutoCloseable`, `DisposableBean`, or `SmartLifecycle` with bounded stop semantics.

### 6.8. `@PreDestroy` / `DisposableBean` / `@Bean(destroyMethod)`

Example:

~~~java
@Component
public class PollingClient {

    private final ExecutorService worker =
            Executors.newSingleThreadExecutor();

    @PreDestroy
    void close() {
        worker.shutdown();
        // Production code should call awaitTermination and handle timeouts.
    }
}
~~~

This snippet needs Jakarta `@PreDestroy` imports and error handling. Prefer injecting a Spring-managed executor bean over creating pools inside services, yet if a library mandates direct resource ownership, attach explicit destroy hooks.

An `AutoCloseable` bean:

~~~java
@Bean(destroyMethod = "close")
RemoteClient remoteClient() {
    return new RemoteClient(...);
}
~~~

Snippet assuming `RemoteClient` implements `close()`. Spring infers destroy methods for standard closeable types, though declaring `destroyMethod` explicitly clarifies ownership. **Never** close a shared singleton client inside `@AfterEach` if other cached tests still rely on it.

## 7. Context caching and `@DirtiesContext`: understand before diagnosing a leak

### 7.1. TestContext caching is intentional

Spring Framework 6.2 maintains a static per-JVM context cache. Test classes with matching configuration keys reuse contexts. By default, the cache holds up to 32 contexts using LRU eviction.

Contexts close via:
1. `@DirtiesContext`.
2. LRU cache eviction.
3. The JVM shutdown hook when the test runner exits.

Therefore:
- Test method A finishes and Tomcat still listens → **can be completely normal** because Class B reuses that context.
- Class A finishes and the Hikari housekeeper thread persists → **can be completely normal**.
- Context K genuinely closes yet K-owned threads survive past the shutdown budget → investigate.
- The JVM fails to exit due to unmanaged resources outside Spring → find the non-Spring owner.

### 7.2. Use `@DirtiesContext` only when the context is genuinely “dirty”

~~~java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest
class DedicatedDirtyContextTest {
}
~~~

This snippet fits when a test intentionally mutates context-wide state that cannot be reset safely. It is **not mandatory teardown for every `@SpringBootTest`**; overusing it slows suites down, repeatedly restarts containers/pools/servers, and causes races against parallel tests sharing contexts.

Remember it closes only the **Spring context**: `@DirtiesContext` will never close raw `new ServerSocket`, `Executors.new...`, or unmanaged external processes you created outside beans.

### 7.3. Never call `context.close()` on an `@Autowired` shared context

Anti-pattern:

~~~java
@Autowired
ConfigurableApplicationContext context;

@AfterEach
void cleanup() {
    context.close(); // Can break the TestContext cache for other tests.
}
~~~

Never do this inside a shared `@SpringBootTest`. If you want to test port release on shutdown, create a **programmatically owned isolated context** inside a plain JUnit test and call `close()` in `finally`; the Maven lab demonstrates this cleanly.

### 7.4. `@DirtiesContext` and parallel tests

Spring Framework docs caution against or advise disabling parallelism on tests using `@DirtiesContext`, bean overrides, or shared external systems without isolation. If Class A closes Context K while Class B is executing against it, B fails with `ApplicationContext ... no longer active`—a test topology race, not a Tomcat leak.

### 7.5. Distinct cache keys → multiple servers/pools

`@ActiveProfiles`, `@SpringBootTest(properties=...)`, `@DynamicPropertySource`, `@MockitoBean`, web environment modes, imported configs, and parent contexts all alter cache keys. A suite with multiple `RANDOM_PORT` contexts legitimately opens multiple concurrent HTTP ports; never assert “only one listening port may exist in the JVM”.

Measure context cache hits/misses via:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Never tweak cache `maxSize` to hide a leaked raw socket. Ownership and resource lifetimes are separate concerns.

## 8. Diagnosing with OS and JVM tools

### 8.1. Step one: find the test process PID

On machines with a JDK:

~~~bash
jps -lv

jcmd -l
~~~

`jps`/`jcmd -l` list Java processes when attach permissions allow. Under Maven Surefire forks, the forked test JVM's PID **often differs from the Maven launcher's PID**; check command lines and parent processes. Inside containers/CI, run tools inside the matching PID namespace with proper attach rights.

Never assume a stale PID from an earlier run still belongs to your test: OSes reuse PIDs. Record timestamps and command lines.

### 8.2. JVM thread dumps

~~~bash
jcmd <PID> Thread.print
jstack <PID>
~~~

`<PID>` is a placeholder to substitute with the real terminal PID, **not a literal command**. Grab the concrete PID from `jps`. Capture thread dumps **before killing**, ideally 2–3 snapshots spaced a few seconds apart to see whether stacks advance or remain stuck.

Look for:
- Application-configured thread name prefixes.
- `daemon` flag and thread state.
- `java.util.concurrent.ThreadPoolExecutor.getTask`.
- `ScheduledThreadPoolExecutor`.
- `CountDownLatch.await`, `FutureTask.get`, `LockSupport.park`.
- Netty event loops, Kafka consumer polls, Rabbit listeners, Tomcat workers.
- Hikari housekeepers and connection adders.
- `SpringContextShutdownHook` waiting to destroy beans.
- `@AfterAll`/`@AfterEach` methods failing to return.

A single stack dump does not always reveal the allocator; combine it with the Spring bean graph, app logs, and allocation stack traces/profilers when needed.

### 8.3. Linux: inspect listeners by port/PID

~~~bash
ss -ltnp

sudo lsof -nP -iTCP -sTCP:LISTEN

sudo lsof -nP -p 12345
~~~

These commands show TCP listeners, owning processes, and open file descriptors for a given PID. Use `sudo` only when permitted and needed; viewing your own user's processes needs no root privileges. On Linux containers/CI, network namespaces can make listeners look different between host and container.

Filter a single port with `ss -ltnp 'sport = :8080'` or `lsof -nP -iTCP:8080 -sTCP:LISTEN`. Treat only `LISTEN` as proof of an active listener; interpret `TIME_WAIT` separately.

### 8.4. macOS

~~~bash
lsof -nP -iTCP -sTCP:LISTEN

lsof -nP -iTCP:8080 -sTCP:LISTEN

ps -p 12345 -o pid,ppid,command
~~~

Checking port 8080 is just an example. Never kill a process until you confirm it belongs to your test run.

### 8.5. Windows PowerShell

~~~powershell
Get-NetTCPConnection -State Listen |
  Select-Object LocalAddress,LocalPort,OwningProcess

Get-NetTCPConnection -LocalPort 8080 |
  Select-Object LocalAddress,LocalPort,State,OwningProcess

Get-Process -Id 12345

netstat -ano
tasklist /FI "PID eq 12345"
~~~

To inspect a process's command line:

~~~powershell
Get-CimInstance Win32_Process -Filter "ProcessId = 12345" |
  Select-Object ProcessId,ParentProcessId,CommandLine
~~~

Replace sample ports/PIDs with values observed on your machine. `Get-NetTCPConnection` may be unavailable on very old PowerShell/Windows builds, where `netstat -ano` works instead. Confirm process ownership **before** running `Stop-Process`; killing is an emergency cleanup step after saving evidence, not a code fix.

### 8.6. Linux `/proc` and file descriptors

~~~bash
ls -l /proc/12345/fd
cat /proc/12345/status
~~~

Useful Linux diagnostics when permissions allow. A rising FD count across test iterations points toward file or socket leaks. Compare against a warm-up baseline: JVM/Netty/Hikari legitimately allocate pools/caches and then plateau. Never call “one open FD” a leak on its own.

### 8.7. JDK Flight Recorder / Mission Control

JFR helps investigate:
- Thread starts/exits and lock contention.
- Socket read/write events.
- File reads/writes.
- Allocation pressure and GC.
- Execution hot spots.
- Shutdown latency.

Example bounded recording:

~~~bash
jcmd 12345 JFR.start name=test-leak settings=profile duration=60s filename=leak-check.jfr
~~~

Protect recording files carefully since they can hold sensitive runtime data. Do not leave heavy profiling JFR enabled across every CI job without measuring overhead; run it in reproduction environments. JFR shines when thread dumps alone cannot separate busy work from gradual leaks across classes.

### 8.8. JVM heap memory is only one kind of resource leak

Heap leaks, thread leaks, FD/socket leaks, native/direct buffer leaks, and external Docker leaks are distinct:
- Growing heap usage: heap dump / GC roots.
- Thread counts failing to drop after teardown: `ThreadMXBean` / dumps.
- Growing open file/socket FDs: OS `lsof` / handle tools.
- Rising direct memory: Netty / JFR / native memory tracking when enabled.
- Exhausted database connections: Hikari / DB metrics.
- Docker containers outliving suites: `docker inspect` / `ps` + owner tracking.
- Ports stuck in `LISTEN`: OS socket table + PID.

Never equate `OutOfMemoryError` with “forgot `ServerSocket.close()`” without evidence.

## 9. Tests must observe the right layer

### 9.1. Verifying port release in a self-owned server test

A sound lifecycle test can:
1. Boot a **dedicated isolated** Spring application context with `port=0`.
2. Read the actual bound port.
3. Send a test HTTP request.
4. Close the context via `context.close()` inside `finally`.
5. Verify the port can be rebound on loopback.
6. Leave the shared TestContext cache untouched.

This verifies behavior **after the owner closes**, making it a meaningful lifecycle test.

### 9.2. Asserting “port closed after `@Test`” on a shared context is usually wrong

~~~java
@SpringBootTest(webEnvironment = RANDOM_PORT)
class WrongAssumptionTest {
    @LocalServerPort
    int port;

    @AfterEach
    void assertPortIsClosed() {
        // Wrong assumption: context remains cached after the method finishes.
    }
}
~~~

Exclude this anti-pattern from the lab. Other tests legitimately depend on the cached context/web server staying live; a listener remaining in `LISTEN` after a method finishes is not a bug.

### 9.3. Asserting “zero remaining threads” must be scoped

Avoid:

~~~java
assertThat(Thread.activeCount()).isZero();
~~~

The JVM and test runtime always run background threads, and `activeCount()` is only an estimate rather than a reliable JVM-wide check.

Prefer:
- Assign a clear thread-name prefix on test-owned resources.
- Assert `isShutdown` / `awaitTermination` on the executor when its owner closes.
- Assert worker `Future`s completed or cancelled.
- Optionally verify no threads with that prefix stay live **after await**, without making thread enumeration your sole assertion (lifecycles can lag slightly at snapshot boundaries).
- Inspect thread dumps when threads persist unexpectedly.

### 9.4. Rebinding a closed port also has caveats

Attempting to rebind the old port right after close is practical evidence **in an isolated environment**, yet watch out for:
- Another process grabbing the ephemeral port in between.
- Bind-address differences changing outcomes.
- OS-specific TCP `TIME_WAIT` semantics for prior connections.
- OS variations in `SO_REUSEADDR`/`SO_REUSEPORT`.
- IPv4/IPv6 dual-stack nuances allowing one bind while blocking another.

In the lab, the context binds strictly to `127.0.0.1`, the probe socket binds the exact same address with `setReuseAddress(true)`, and the test suite shares no fixed ports with external processes. On noisy CI hosts, supplement rebinds with OS listener/PID checks instead of relying on rebind alone, and never replace real checks with `Thread.sleep`.

### 9.5. Negative assertions require completion signals

An assertion like:

~~~java
assertThat(repository.findAll()).isEmpty();
~~~

right after `executor.submit(...)` can pass solely because the worker has not written yet. To prove “no side effects after cancellation”:
- Stop producing new work.
- Cancel pending tasks where appropriate.
- Wait on a task-termination/shutdown barrier.
- Only then assert durable state.
- For asynchronous external systems, use bounded observation/settling semantics.

Never replace synchronization with `Thread.sleep(500)`.

## 10. Runnable Maven project: port and executor cleanup

### 10.1. Lab scope

The project contains three test groups:

1. **`RandomPortAndManagedTaskTest`**: `@SpringBootTest(RANDOM_PORT)` proving the web server legitimately runs inside the *cached context*, serves HTTP responses, and completes tasks on the managed executor bean. **Never closes** the shared Spring context.
2. **`PortOnlyContextLifecycleTest`**: plain JUnit booting an isolated Spring web context via `SpringApplicationBuilder`, probing the live HTTP port, closing the context in `finally`, and rebinding the port. Also tests try-with-resources around a raw `ServerSocket`.
3. **`ManagedResourcesLifecycleTest`**: plain JUnit creating dedicated `AnnotationConfigApplicationContext` instances holding an executor bean or an `AutoCloseable` socket bean, closing each context, and verifying shutdown/closure. Also covers an ad-hoc `ExecutorService` and `@TempDir` cleanup.

Expected count: **8 JUnit methods** with **zero deliberate hang/leak tests in the default suite**. The objective is teaching how to build **controllably owned resources**, not hanging Maven with infinite non-daemon threads. Anti-patterns remain standalone snippets outside the runnable project.

### 10.2. Directory layout

~~~text
resource-lifecycle-diagnostics/
├── pom.xml
├── src/main/
│   ├── java/com/example/lifecycle/
│   │   ├── ResourceLifecycleApplication.java
│   │   ├── ProbeController.java
│   │   ├── ManagedExecutorConfiguration.java
│   │   └── ManagedJobService.java
│   └── resources/
│       └── application.properties
└── src/test/java/com/example/
    ├── lifecycle/
    │   └── RandomPortAndManagedTaskTest.java
    ├── portprobe/
    │   └── PortOnlyContextLifecycleTest.java
    └── resourcesprobe/
        └── ManagedResourcesLifecycleTest.java
~~~

**Why keep test-only configs in separate packages?** `ResourceLifecycleApplication` scans `com.example.lifecycle`. Placing `@Configuration` classes meant solely for programmatic contexts under `com.example.portprobe` or `com.example.resourcesprobe` prevents accidental component scanning into the shared `@SpringBootTest`.

### 10.3. `pom.xml`

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
  <artifactId>resource-lifecycle-diagnostics</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
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

Dependencies:
- `spring-boot-starter-web`: Spring MVC, embedded Tomcat, and `RestClient`.
- `spring-boot-starter-test`: Spring Boot Test, JUnit Jupiter, AssertJ.
- Spring Context/task-execution classes come through Boot starters without needing a separate scheduling/integration starter for `ThreadPoolTaskExecutor`.
- JDK 17 supplies `ServerSocket`, `ExecutorService`, `Future`, and JMX diagnostics.
- No Docker/DB/external services keep lifecycle focus crystal clear.

### 10.4. `application.properties`

`src/main/resources/application.properties`:

~~~properties
spring.application.name=resource-lifecycle-diagnostics
spring.main.banner-mode=off

# Bind loopback only for this lesson; RANDOM_PORT assigns a dynamic port.
server.address=127.0.0.1

# Do not enable @EnableScheduling in this sample.
logging.level.com.example.lifecycle=INFO
~~~

Do not hardcode `server.port=8080`. `@SpringBootTest(webEnvironment=RANDOM_PORT)` selects a dynamic port. In programmatic contexts, we pass `server.port=0` into `SpringApplicationBuilder`. Binding loopback avoids exposing test HTTP endpoints on external interfaces.

### 10.5. `ResourceLifecycleApplication.java`

`src/main/java/com/example/lifecycle/ResourceLifecycleApplication.java`:

~~~java
package com.example.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ResourceLifecycleApplication.class, args);
    }
}
~~~

The main app creates no raw threads or sockets inside static initializers or constructors. Managed resources come strictly from Spring bean definitions.

### 10.6. `ProbeController.java`

`src/main/java/com/example/lifecycle/ProbeController.java`:

~~~java
package com.example.lifecycle;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {

    @GetMapping("/probe")
    public String probe() {
        return "PONG";
    }
}
~~~

A single plain-text endpoint. Making a real HTTP call over the bound port proves the server bound properly and `DispatcherServlet` handles requests without DB or scheduler noise.

### 10.7. `ManagedExecutorConfiguration.java`

`src/main/java/com/example/lifecycle/ManagedExecutorConfiguration.java`:

~~~java
package com.example.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class ManagedExecutorConfiguration {

    @Bean("diagnosticExecutor")
    ThreadPoolTaskExecutor diagnosticExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setThreadNamePrefix("diag-managed-");
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(10);

        // Actively finish queued/running tasks on context close.
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);

        return executor;
    }
}
~~~

Notes:
- `ThreadPoolTaskExecutor` is a Spring bean initialized and destroyed by Spring.
- Thread prefixes expose the owner clearly in thread dumps.
- Bounded queue capacity avoids unbounded buildup in the sample.
- Waits up to 5 seconds at shutdown; production services need SLA-backed timeouts and cooperatively cancellable tasks if exceeded.
- `@SpringBootTest` never closes the shared context in `@AfterEach`; the executor stays legitimately alive in the cached context.
- In isolated-context tests, Spring shuts down the bean upon `context.close()`, allowing us to assert termination.

### 10.8. `ManagedJobService.java`

`src/main/java/com/example/lifecycle/ManagedJobService.java`:

~~~java
package com.example.lifecycle;

import java.util.concurrent.Future;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class ManagedJobService {

    private final ThreadPoolTaskExecutor executor;

    public ManagedJobService(
            @Qualifier("diagnosticExecutor")
            ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    public Future<String> reportWorkerThread() {
        return executor.submit(
                () -> Thread.currentThread().getName());
    }
}
~~~

A minimal service running a short task without `@Async` so executor ownership and completion remain directly observable. Returning the thread name lets tests confirm execution happened inside the managed pool.

### 10.9. `RandomPortAndManagedTaskTest.java`

`src/test/java/com/example/lifecycle/RandomPortAndManagedTaskTest.java`:

~~~java
package com.example.lifecycle;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ResourceLifecycleApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RandomPortAndManagedTaskTest {

    @LocalServerPort
    int port;

    @Autowired
    ManagedJobService jobs;

    @Test
    void webServerIsLiveOnItsAssignedRandomPort() {
        assertThat(port).isBetween(1, 65535);

        RestClient client = RestClient.create(
                "http://127.0.0.1:" + port);

        String body = client.get()
                .uri("/probe")
                .retrieve()
                .body(String.class);

        assertThat(body).isEqualTo("PONG");
    }

    @Test
    void taskRunsOnManagedExecutorAndCompletes() throws Exception {
        String threadName = jobs.reportWorkerThread()
                .get(3, TimeUnit.SECONDS);

        assertThat(threadName)
                .startsWith("diag-managed-");
    }
}
~~~

**What is verified:**
- The context loads with a real embedded servlet server on a dynamic port.
- Real HTTP requests return the expected response.
- The Spring-managed executor runs the task and completes the future before the deadline.
- No manual context close occurs in the test body or `@AfterEach`, since Spring TestContext owns the cached context.
- The test **does not claim** the port or executor disappears right after a test method—that is not a cached `@SpringBootTest` contract.

`RestClient` uses the default classpath HTTP request factory. When real applications configure HTTP clients with custom connection pools, register/close those pools via proper owners; the test above does not prove arbitrary custom client pools shut down.

### 10.10. `PortOnlyContextLifecycleTest.java`

`src/test/java/com/example/portprobe/PortOnlyContextLifecycleTest.java`:

~~~java
package com.example.portprobe;

import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;

import org.junit.jupiter.api.Test;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

class PortOnlyContextLifecycleTest {

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class PortOnlyConfiguration {

        @Bean
        PortOnlyEndpoint portOnlyEndpoint() {
            return new PortOnlyEndpoint();
        }
    }

    @RestController
    static class PortOnlyEndpoint {

        @GetMapping("/probe")
        public String probe() {
            return "PONG";
        }
    }

    private static void canBindLoopbackPort(int port)
            throws IOException {

        try (ServerSocket verification = new ServerSocket()) {
            verification.setReuseAddress(true);
            verification.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), port));

            assertThat(verification.isBound()).isTrue();
        }
    }

    @Test
    void explicitlyClosedSpringContextReleasesHttpListener() {
        int usedPort;

        ConfigurableApplicationContext context =
                new SpringApplicationBuilder(
                        PortOnlyConfiguration.class)
                        .web(WebApplicationType.SERVLET)
                        .properties(
                                "server.address=127.0.0.1",
                                "server.port=0",
                                "spring.main.banner-mode=off")
                        .run();

        try {
            WebServerApplicationContext web =
                    (WebServerApplicationContext) context;

            usedPort = web.getWebServer().getPort();
            assertThat(usedPort).isBetween(1, 65535);

            RestClient client = RestClient.create(
                    "http://127.0.0.1:" + usedPort);

            assertThat(client.get()
                    .uri("/probe")
                    .retrieve()
                    .body(String.class))
                    .isEqualTo("PONG");
        }
        finally {
            // Owner of the isolated context must close it even if assertions fail.
            context.close();
        }

        // After the owner closes, the listener port is released.
        // Rebind on the same loopback address; never hardcode 8080.
        try {
            canBindLoopbackPort(usedPort);
        }
        catch (IOException problem) {
            throw new AssertionError(
                    "port still unavailable after context.close: "
                            + usedPort, problem);
        }
    }

    @Test
    void rawServerSocketUsesTryWithResources()
            throws Exception {

        int usedPort;

        try (ServerSocket socket = new ServerSocket(
                0, 50, InetAddress.getLoopbackAddress())) {

            usedPort = socket.getLocalPort();
            assertThat(socket.isBound()).isTrue();
            assertThat(socket.isClosed()).isFalse();
        }

        canBindLoopbackPort(usedPort);
    }
}
~~~

**Important practical takeaways:**
- Plain JUnit test with no `@SpringBootTest` on the class; it builds and closes its own isolated Spring context.
- `PortOnlyConfiguration` lives in `com.example.portprobe`, **outside the `com.example.lifecycle` scan root**.
- Uses `@Configuration` + `@EnableAutoConfiguration` and `SpringApplicationBuilder.web(SERVLET)`, registering only the test-owned controller.
- Port 0 lets the OS assign `usedPort` dynamically with zero fixed ports.
- `finally` guarantees `context.close()` even when HTTP assertions fail.
- Rebinding on loopback verifies post-close port release.
- Raw `ServerSocket` uses try-with-resources before rebinding.

**Limitations:** Post-close port rebinding can still face OS port reuse/`TIME_WAIT` timing or an external process grabbing the port. On noisy CI hosts, combine OS listener/PID evidence (`ss`/`lsof`/`Get-NetTCPConnection`) instead of using fixed sleeps or asserting zero OS sockets overall. Never apply this `context.close()` pattern to an `@Autowired` cached context shared by `@SpringBootTest` classes.

### 10.11. `ManagedResourcesLifecycleTest.java`

`src/test/java/com/example/resourcesprobe/ManagedResourcesLifecycleTest.java`:

~~~java
package com.example.resourcesprobe;

import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import static org.assertj.core.api.Assertions.assertThat;

class ManagedResourcesLifecycleTest {

    @Configuration(proxyBeanMethods = false)
    static class WorkerOnlyConfiguration {

        @Bean
        ThreadPoolTaskExecutor workerExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();

            executor.setThreadNamePrefix("owned-worker-");
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(2);
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);

            return executor;
        }
    }

    static final class PortLease implements AutoCloseable {

        private final ServerSocket socket;

        PortLease() throws IOException {
            this.socket = new ServerSocket(
                    0, 50, InetAddress.getLoopbackAddress());
        }

        int port() {
            return socket.getLocalPort();
        }

        boolean isClosed() {
            return socket.isClosed();
        }

        @Override
        public void close() throws IOException {
            socket.close();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class PortOnlyResourceConfiguration {

        @Bean(destroyMethod = "close")
        PortLease portLease() throws IOException {
            return new PortLease();
        }
    }

    private static void canBindLoopbackPort(int port)
            throws IOException {
        try (ServerSocket verification = new ServerSocket()) {
            verification.setReuseAddress(true);
            verification.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), port));

            assertThat(verification.isBound()).isTrue();
        }
    }

    @Test
    void executorBeanIsShutdownWhenItsContextCloses()
            throws Exception {

        ThreadPoolTaskExecutor executor;

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             WorkerOnlyConfiguration.class)) {

            executor = context.getBean(
                    ThreadPoolTaskExecutor.class);

            Future<String> result = executor.submit(
                    () -> Thread.currentThread().getName());

            assertThat(result.get(3, TimeUnit.SECONDS))
                    .startsWith("owned-worker-");
        }

        // Context closed -> Spring destroyed the executor bean.
        assertThat(executor.getThreadPoolExecutor().isShutdown())
                .isTrue();

        assertThat(executor.getThreadPoolExecutor()
                .awaitTermination(5, TimeUnit.SECONDS))
                .isTrue();
    }

    @Test
    void autoCloseableBeanClosesOwnedServerSocket()
            throws Exception {

        PortLease owned;
        int usedPort;

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             PortOnlyResourceConfiguration.class)) {

            owned = context.getBean(PortLease.class);
            usedPort = owned.port();

            assertThat(owned.isClosed()).isFalse();
        }

        assertThat(owned.isClosed()).isTrue();
        canBindLoopbackPort(usedPort);
    }

    @Test
    void adHocExecutorIsAlwaysShutdownInFinally()
            throws Exception {

        ExecutorService worker =
                Executors.newSingleThreadExecutor(task -> {
                    Thread t = new Thread(
                            task, "ad-hoc-test-owned");
                    t.setDaemon(false);
                    return t;
                });

        try {
            Future<String> future = worker.submit(
                    () -> Thread.currentThread().getName());

            assertThat(future.get(3, TimeUnit.SECONDS))
                    .isEqualTo("ad-hoc-test-owned");
        }
        finally {
            worker.shutdown();

            if (!worker.awaitTermination(
                    5, TimeUnit.SECONDS)) {

                worker.shutdownNow();

                if (!worker.awaitTermination(
                        5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "test executor did not terminate");
                }
            }
        }

        assertThat(worker.isTerminated()).isTrue();
    }

    @Test
    void temporaryFileFixtureBelongsToThisTest(
            @TempDir Path temporaryDirectory)
            throws IOException {

        Path file = temporaryDirectory.resolve(
                "diagnostic-marker.txt");

        Files.writeString(file, "owned-by-current-test");

        assertThat(Files.readString(file))
                .isEqualTo("owned-by-current-test");

        assertThat(Files.exists(file)).isTrue();
        // @TempDir extension cleans up the directory after the test lifecycle.
    }
}
~~~

### 10.12. Explaining the `ManagedResources` test group

**Executor bean shutdown:**
- Builds a standalone `AnnotationConfigApplicationContext` without touching the shared TestContext cache.
- Spring initializes `ThreadPoolTaskExecutor`.
- Submits one task and waits for its result with `Future.get(timeout)`.
- Closes the context via try-with-resources.
- Asserts `isShutdown` and `awaitTermination`, directly **measuring the owning executor's shutdown** rather than demanding zero threads JVM-wide.

**`PortLease` `AutoCloseable`:**
- `PortLease` owns a `ServerSocket`.
- Registered as a bean with `@Bean(destroyMethod="close")`.
- After the context closes, asserts the socket is closed and the port can be rebound.
- Instantiating `new PortLease()` outside Spring without closing it would leave Spring unable to clean up that object.

**Ad-hoc `ExecutorService`:**
- No Spring bean owns the pool.
- The test method itself must shut it down in `finally`.
- Uses a short task, bounded `get`, graceful `shutdown`, and `shutdownNow` fallback.
- Verifies `isTerminated()` afterward so no non-daemon worker leaks.

**`@TempDir`:**
- JUnit owns the temporary directory.
- `Files` API writes and reads without leaving streams open.
- JUnit's extension deletes the directory after invocation.
- Never assert directory deletion **inside the test body**, since cleanup runs afterward.

### 10.13. Summary of what the lab does not claim

The lab **does not prove**:
- That every Spring Boot/Tomcat/Hikari thread disappears immediately after one `@Test`.
- That every OS TCP state (`TIME_WAIT`) vanishes instantaneously upon server close.
- That PostgreSQL/Redis/Kafka pool lifecycles behave identically to H2 or simple executors.
- That `@DirtiesContext` cleans up raw non-Spring sockets or threads.
- That a passing JUnit test guarantees production graceful shutdown across all in-flight deployments.
- That the JVM exits even if a test spawns an unclosed non-daemon thread outside the context.
- That servlet and Netty graceful shutdown behave identically across web servers.
- That Docker Testcontainers was exercised; the project uses no Docker.

To verify production listener shutdown, connection pools, Kafka consumers, Reactor event loops, or WebFlux behavior, expand the setup with the real backend and test at its actual boundary.

### 10.14. Running Maven

From the `resource-lifecycle-diagnostics` directory:

~~~bash
mvn -q clean test

mvn -q -Dtest=RandomPortAndManagedTaskTest test

mvn -q -Dtest=PortOnlyContextLifecycleTest test

mvn -q -Dtest=ManagedResourcesLifecycleTest test
~~~

Expected counts:
- `RandomPortAndManagedTaskTest`: **2** methods.
- `PortOnlyContextLifecycleTest`: **2** methods.
- `ManagedResourcesLifecycleTest`: **4** methods.
- **8 JUnit test methods** in total.

When running for real, inspect Maven's exit code, executed/skipped/failed test counts, and Surefire reports under `target/surefire-reports`. The Spring context test class may remain cached across methods, whereas the isolated-context tests close explicitly.

**Verification status:** The code/project was designed against Java 17, Spring Boot 3.5.16, and Spring Framework 6.2/JUnit 5 APIs and reviewed structurally; **Maven has not been executed** while authoring this Knowledge article. Therefore all assertions and expected counts are design expectations, not observed CI PASS numbers.

### 10.15. Never stall the whole suite just to “see a leak”

When studying non-daemon executor leaks:
- Isolate the anti-pattern in a **dedicated fork/process** with a timeout and automatic teardown.
- Capture a thread dump before force-stopping.
- Never commit an intentionally infinite thread test into the default Maven suite.
- Never call `Runtime.halt` inside team-shared test suites.
- Never stop resources owned by another class or the shared cached context.

A lesson about resource leaks should never leak across the learning environment itself.

## 11. When to use `@PreDestroy`, `DisposableBean`, or `SmartLifecycle`?

### 11.1. `@PreDestroy`

Fits lightweight cleanup of a single bean:
- Closing a socket or client.
- Cancelling a subscription.
- Stopping a resource heartbeat.
- Flushing/clearing locally owned buffers.
- Restoring bean-owned global state when intentionally designed.

~~~java
@Component
class SubscriptionOwner {

    private final AutoCloseable subscription;

    SubscriptionOwner(AutoCloseable subscription) {
        this.subscription = subscription;
    }

    @PreDestroy
    void close() throws Exception {
        subscription.close();
    }
}
~~~

This snippet needs matching imports and bean wiring. **Never** share one subscription bean across multiple owners that each close it, causing double-close errors or breaking active beans. Keep ownership single or make `close` idempotent.

### 11.2. `DisposableBean`

~~~java
class LegacyClientOwner implements DisposableBean {

    private final ExecutorService executor =
            Executors.newSingleThreadExecutor();

    @Override
    public void destroy() throws Exception {
        executor.shutdown();
        if (!executor.awaitTermination(
                5, TimeUnit.SECONDS)) {
            executor.shutdownNow();
        }
    }
}
~~~

Illustrative snippet needing imports; if `awaitTermination` remains false after forced shutdown, log/handle according to policy. `DisposableBean` tells Spring to invoke `destroy()` when the owning context closes; Java objects instantiated outside Spring receive no automatic management. For modern code, `@Bean(destroyMethod="close")` / `AutoCloseable` keeps coupling lower.

### 11.3. `SmartLifecycle`

Use when a resource needs phase ordering and asynchronous stop callbacks:

~~~java
class ConsumerLifecycle implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        // start consumer
    }

    @Override
    public void stop(Runnable callback) {
        try {
            // stop consumer and wait for in-flight work within deadline
            running = false;
        }
        finally {
            callback.run();
        }
    }

    @Override
    public void stop() {
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
~~~

This snippet **illustrates only the lifecycle contract**, not a production-ready consumer (no real consumer client or async completion is wired). In production clients, invoke `callback` only once shutdown finishes or hits a handled failure/timeout policy; calling `callback` too early lets Spring destroy backing pools before work finishes.

Spring Boot graceful web shutdown relies on lifecycle phases; declare dependencies and phases cleanly so clients close before servers/brokers rather than guessing from class declaration order.

### 11.4. `ContextClosedEvent`

`@EventListener(ContextClosedEvent.class)` observes when a context starts closing to signal shutdown. Yet if you keep a static singleton outside Spring, listeners stop it only when loaded inside the owning context; never register multiple listeners that tear down a global resource still serving other contexts.

### 11.5. Shutdown ordering across dependent resources

If a background worker needs the database to flush its final message:
- Stop accepting new tasks.
- Wait for in-flight workers.
- Close producers/clients.
- Close the database pool.
- Stop backing Testcontainers services.
- Finally release OS sockets/processes.

In Spring, bean dependencies and lifecycle phases establish ordering, whereas custom ad-hoc threads execute outside framework control. That is why you inject **managed executors** instead of calling `new Thread` from services.

## 12. Common resources that are easy to forget

### 12.1. `HikariDataSource` / JDBC `Connection`

Common bugs:
- Test code calls `dataSource.getConnection()` without closing it.
- Cached contexts retain valid pools, leading someone to mistake `HikariPool-1 housekeeper` for a leak.
- A test instantiates `new HikariDataSource()` directly and forgets `close()`.
- A hung transaction holds a physical connection indefinitely.
- An integration test with pool size 2 runs 10 concurrent workers → timeout under contention.

Fixes:
- Use `JdbcTemplate` or try-with-resources for borrowed `Connection`s.
- Keep `HikariDataSource` as a Spring bean when owned by the context so Spring destroys it on close.
- When a test builds a raw pool manually, the test must `close()` it.
- Monitor Hikari active/idle/pending/total metrics and `leakDetectionThreshold` **for diagnosis**, without mistaking leak detection settings for a fix.
- Never close a shared pooled `DataSource` inside `@AfterEach`.

### 12.2. HTTP clients and connection pools

HTTP clients manage connection pools or dispatcher threads:
- Apache HttpClient `CloseableHttpClient` must close per its owner.
- `OkHttpClient` owns a `Dispatcher` and `ConnectionPool` requiring shutdown/eviction per API and ownership.
- Reactor Netty `HttpClient` owns resources/event loops; custom `ConnectionProvider`/`LoopResources` must be disposed by their owner.
- Java `HttpClient` and Spring `RestClient` depend on the underlying request factory implementation; do not assume one identical close rule across factories.

When created per test:
- Construct inside the fixture.
- Close via the right API when closeable.
- Await/cancel in-flight requests.
- Only then verify threads/sockets cleared.

When registered as a singleton Spring bean, follow bean lifecycle rather than closing after each method while the context lives.

### 12.3. Reactor schedulers

Counterexample:

~~~java
Scheduler scheduler =
        Schedulers.newBoundedElastic(
                2, 100, "test-reactor-owned");

// Missing scheduler.dispose().
~~~

Snippet requiring Reactor dependencies/imports, excluded from the servlet Maven lab. For custom test-created schedulers:
- Call `dispose()` at scope end.
- Verify disposal/termination per your Reactor API/version when needed.
- Never call global `Schedulers.shutdownNow()` to clean up a test scheduler: it breaks apps/tests relying on global schedulers.
- When resources are managed by Reactor Netty loops/containers, check the corresponding owner.

### 12.4. Servlet servers and keep-alive

Embedded Tomcat/Jetty/Undertow manage:
- Listener sockets.
- Worker/event threads.
- Persistent HTTP connections.
- Graceful shutdown deadlines.
- In-flight requests.

Upon Spring context close, Boot 3.5 enables graceful shutdown by default on supported embedded servers. It stops accepting new requests and grants in-flight work up to `spring.lifecycle.timeout-per-shutdown-phase`. Never label a few milliseconds/seconds of normal transition inside the grace window a leak.

### 12.5. Netty event loops

WebFlux/Reactor Netty uses event-loop threads such as `reactor-http-nio-*`, which persist legitimately while contexts or global Reactor resources stay alive. Distinguish:
- Framework-reused global Reactor resources;
- Test-created custom `LoopResources`/`ConnectionProvider`;
- In-flight TCP connections;
- Undisposed context/client resources.

Never shut down global schedulers inside an isolated test while the suite still depends on them. Use test-scoped owners or match the context lifecycle.

### 12.6. Kafka/RabbitMQ listeners

Listener containers and consumer threads stay active after a test method while the context remains live:
- A `@KafkaListener` can consume another test's message.
- A Rabbit listener can drain a queue unexpectedly.
- Check auto-startup settings from profiles/config.
- Async commits/acks/deliveries can fire after assertions.

When testing pure business logic, disable listener auto-startup or use profiles. When testing listeners, use unique consumer groups/topics/queues, bounded waits, and worker completion before cleanup. Close consumer factories/listeners with the context; never let Class A shut down a shared broker needed by Class B.

### 12.7. Testcontainers + context cache

Two ownership models:
- JUnit `@Testcontainers` + `@Container`: per-method or per-class lifecycle.
- Spring Boot 3.5 `@TestConfiguration @Bean @ServiceConnection`: Spring-managed container tied to `ApplicationContext` lifetime.

With context caching, Spring-managed containers prevent “JUnit stopped the DB before Spring's DataSource closed”. For JVM-wide singleton containers, do not annotate `@Container` so JUnit stops it per class; bind cleanup to the JVM/test-run owner. Reusable containers across runs do not suit default CI state isolation.

Never call a running Docker container after one test class a leak if a cached Spring context manages it for subsequent tests.

### 12.8. WireMock / `MockWebServer` / embedded HTTP

A self-created `WireMockServer`:

~~~java
WireMockServer server =
        new WireMockServer(options().dynamicPort());
server.start();

try {
    // exercise HTTP client using server.baseUrl()
}
finally {
    server.stop();
}
~~~

Snippet requiring WireMock dependency/imports, omitted from the minimal Maven project. When managed by a JUnit extension, avoid double-stopping or hardcoding fixed ports. When a Spring client bean targets the mock server's URL, never stop the server before the client finishes and its context closes.

### 12.9. File handles and `@TempDir`

~~~java
try (InputStream stream =
             Files.newInputStream(path)) {
    // read
}
~~~

Unclosed streams cause `@TempDir` deletion failures, especially on Windows where file locks behave differently from Unix. Use `Files` helpers and try-with-resources; close ZIP filesystems, watch services, memory-mapped files, and `Channel`s explicitly. Note that JUnit cannot release handles locked by another external process.

### 12.10. Test-spawned OS processes

~~~java
Process process = new ProcessBuilder(
        "some-command").start();

try {
    // bounded interaction / drain output
}
finally {
    process.destroy();
    if (!process.waitFor(5, TimeUnit.SECONDS)) {
        process.destroyForcibly();
        process.waitFor(5, TimeUnit.SECONDS);
    }
}
~~~

Illustrative skeleton; `some-command` does not exist and is never invoked in the lab. For OS child processes:
- Prevent deadlocks by draining stdout/stderr.
- Wait for exit with bounded deadlines.
- Manage grandchild processes spawned by the child.
- Never kill unrelated PIDs outside the test.
- Capture diagnostic logs before calling `destroyForcibly` during investigations.

### 12.11. File watchers and native library resources

`WatchService`, native handles, sockets, timers, compression streams, and RocksDB instances retain OS resources that Java heap snapshots miss. Close explicitly at the owner, monitor FD counts and native memory, and cycle lifecycles repeatedly to catch cumulative leaks.

## 13. Why do resource leaks make test suites unstable?

### 13.1. Leaks compound with test count

Suppose every test opens a 2-thread `ExecutorService` without shutting down:
- After 1 test: barely noticeable.
- After 100 tests: 200 leaked threads.
- CPU, context switching, and memory climb.
- Execution slows down or hits unable-to-create-native-thread errors.
- Surefire forks stall or get force-halted at teardown.

One passing test proves nothing about leaks. Run repeated lifecycle loops and check **post-close resource counts**.

### 13.2. Fixed ports create order dependencies

Class A boots Tomcat on port 8080 and keeps its context cached; Class B uses a different cache key and tries port 8080 → bind conflict. B passes alone yet fails in the suite. Right fixes:
- Use `RANDOM_PORT` unless a fixed port contract applies.
- When fixed ports are mandatory, serialize ownership/port allocation or isolate environments.
- Never manually close a shared cached context just so Class B can grab the port.
- Never kill another process without confirming ownership.

### 13.3. Threads from an earlier test mutate later tests

Test A:
- Submits an async write.
- Never awaits completion.
- `@AfterEach` clears fixtures.

Test B:
- Reuses the same test database.
- Sees an unexpected row written by Test A's lingering background worker.

The root bug is **work outliving cleanup**, not necessarily a JVM hang. Fix with `Future` completion, listener acknowledgments/barriers, and isolated data namespaces.

### 13.4. Context caching can mask task leaks

An executor bean stays legitimately alive in the context cache; if tests submit non-terminating jobs, after 200 tests the queue fills up even if thread counts remain steady. Check:
- Queue depth / active task counts.
- Accepted vs rejected tasks.
- Pending futures.
- Task deadlines.
- Per-test cleanup.
- Context close behavior.

Steady thread counts alone never prove an executor is not leaking queued tasks.

### 13.5. Testcontainers resource starvation

A suite booting a fresh PostgreSQL container **per test method** or forcing unique contexts via unique properties can exhaust:
- Docker RAM/CPU.
- Container/network IDs.
- File descriptors.
- Database connections.
- CI wall-clock time.

Leverage context caching, Spring-managed containers, grouping, and per-test unique IDs whenever feasible—without sharing unisolated mutable data just to save startup time.

## 14. Graceful shutdown: timing and limits

### 14.1. Spring Boot 3.5 web shutdown

Spring Boot 3.5 enables graceful shutdown by default for supported embedded web servers. On context close, the web server enters `SmartLifecycle` shutdown phases. Timing policy:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

This example targets environments allowing 20 seconds per phase. In small unit/integration tests, avoid needlessly long grace periods; production services need budgets sized to in-flight requests/side effects per SLA.

`server.shutdown=immediate` changes web shutdown mode without curing custom executor or socket leaks. Use immediate shutdown only when appropriate to requirements, never to hide hanging tests.

### 14.2. JVM shutdown hooks are not `@AfterAll`

Spring's JVM shutdown hook closes remaining open contexts upon JVM termination, yet `@AfterAll` executes **before** JVM shutdown hooks when the suite finishes normally. Any test verifying resource closure upon context shutdown must **instantiate and explicitly close its own isolated context**, or belong to a dedicated lifecycle suite.

### 14.3. Dependency-graph shutdown order

When an executor task still uses the database during context close:
- Shutting down and awaiting tasks first lets them finish before the DB pool destroys.
- Yet tasks ignoring interrupts or exceeding deadlines still fail cleanup.
- Never block `@PreDestroy` indefinitely.
- Stop message consumers from accepting new deliveries, finish in-flight work, and only then close clients/backends.

Boot starts Spring-managed Testcontainers beans before dependent beans and stops them after dependent beans destroy; keep ownership clean so clients never hit dead backends.

### 14.4. Bounded awaits require a clear policy

Three strategies:
- **Graceful**: stop accepting new work, drain queued/in-flight tasks within a deadline.
- **Fast cancel**: interrupt/cancel tasks and roll back or reconcile partial work.
- **Drain and persist**: checkpoint durable state for resume after restart.

No universal `shutdownNow()` guarantees consistency. Pick per workload semantics and test mid-flight failure cases where critical.

## 15. Using JUnit lifecycles properly

### 15.1. `@BeforeEach` / `@AfterEach`

**Per-method** owned resources:
- Create inside `@BeforeEach` or the test body.
- Clean up in `@AfterEach` or try-with-resources.
- Use unique IDs and temp paths.
- Avoid overwriting static resources shared with other classes.
- Confirm background work finishes before cleanup runs.

JUnit callbacks generally execute even when assertions fail, yet cannot run if the JVM/process is force-killed, crashes, or hangs infinitely before reaching teardown.

### 15.2. `@BeforeAll` / `@AfterAll`

**Test-class** owned resources:
- Start in `@BeforeAll`.
- Stop in `@AfterAll`.
- Under `@TestInstance(PER_CLASS)` or static lifecycles, synchronize field access carefully.
- Never stop a Spring-managed resource **still serving a cached context** for other classes.

A JUnit static `@Container` has a different owner from Spring TestContext cache. Never equate `static` fields with JVM-wide lifetime.

### 15.3. Extensions and `CloseableResource`

JUnit 5 provides extension stores scoped to root/class/method contexts so extensions can store resources and auto-close them by scope. When authoring custom extensions:
- Choose the exact root/class/method store scope.
- Verify close callbacks register and run.
- Avoid creating multiple clients while cleaning only one.
- With cached contexts, never close resources still held by active Spring beans.

### 15.4. `@ResourceLock` and parallel tests

`@ResourceLock` coordinates tests in the same engine sharing a lock key (such as System properties or a global port registry). It does **not** lock:
- Separate processes/JVMs.
- Real Docker host ports.
- Arbitrary worker threads outside JUnit.
- Shared Spring singletons mutated by background jobs.

Use resource locks when mutating global state is unavoidable; prefer per-test dynamic ports and unique IDs to eliminate global shared state.

### 15.5. `@Timeout` and preemptive pitfalls

JUnit `@Timeout` detects hung methods and can dump threads depending on configuration. Yet timeouts do not guarantee:
- Child tasks stopped.
- Executors shut down.
- Worker DB transactions rolled back.
- Network clients closed.
- `@AfterEach` no longer races with workers.

Spring test-managed `@Transactional` binds to the test thread; preemptive timeouts or worker threads escape that transaction. Use bounded awaits at explicit boundaries.

## 16. Diagnosing via Spring Boot logs and Actuator

### 16.1. Key logs to monitor

- `Tomcat started on port ...` or server startup lines.
- `Stopping service [Tomcat]` / web server shutdown.
- Hikari pool startup/closure.
- Task executor initializing / shutting down.
- Listener container start/stop.
- Testcontainers container ID/start/stop.
- Spring TestContext cache hits/misses.
- Errors thrown inside `@PreDestroy` or shutdown callbacks.
- Surefire fork exits and elapsed timings.

Never assert exact framework log strings/timestamps as business contracts; use logs strictly for lifecycle diagnosis.

### 16.2. Actuator metrics

With Spring Boot Actuator/Micrometer enabled:
- `jvm.threads.live`.
- Executor active/queued/completed metrics (when bound/observed).
- Hikari active/idle/pending/timeout connections.
- HTTP server connections/requests.
- Container/broker client metrics.
- Open process file descriptors on supported OS/JVMs.

Non-zero metrics while a cached context is legitimately live are normal. Track **trends and values after owner close** rather than demanding 0 threads in the test JVM.

### 16.3. Java `ThreadMXBean`

~~~java
ThreadMXBean mxBean =
        ManagementFactory.getThreadMXBean();

long[] threadIds = mxBean.getAllThreadIds();
ThreadInfo[] infos =
        mxBean.getThreadInfo(threadIds, 100);
~~~

Snippet requiring `java.lang.management.*` imports. Captures snapshots of threads and stack depths, though not every non-thread resource. Filter by owned thread-name prefixes. Avoid asserting exact total JVM thread counts since JIT, GC, and framework threads legitimately fluctuate.

### 16.4. Leak trend tests

When a resource owner offers start/close APIs:
- Warm up the backend/context.
- Record baseline thread/FD/connection-pool counts.
- Loop create→use→close 20–100 times with unique IDs.
- Await termination after each close.
- Assert zero active owned resources/ports rather than exact global counts.
- Capture metrics/traces if counts trend upward.
- Avoid running unbounded resource loops in default CI jobs.

This is a **lifecycle test**, not a precision memory benchmark. For heavy containers, lower iterations and isolate in a dedicated CI job.

## 17. Maven Surefire configuration and fork behavior

### 17.1. Surefire can isolate test processes

Surefire exposes `forkCount` and `reuseForks`; when forked:
- Spring's static TestContext cache lives **inside each fork JVM**, unshared across forks.
- Threads live inside that fork; the Maven launcher stays in its parent PID.
- External Docker containers/processes can outlive forks depending on ownership.
- Shutdown hooks run at JVM exit unless hard-killed.
- Forced shutdown timeouts can truncate final destroy logs.

Record fork settings in bug reports. “JVM refuses to exit after `@Test`” requires identifying **which fork process** stalled.

### 17.2. `forkedProcessExitTimeoutInSeconds`

Surefire configures how long to wait for a forked JVM exit:

~~~xml
<configuration>
  <forkedProcessExitTimeoutInSeconds>30</forkedProcessExitTimeoutInSeconds>
</configuration>
~~~

Snippet belonging to `maven-surefire-plugin`, not `spring-boot-maven-plugin`. A forced halt after timeout **does not mean cleanup worked**. It is only a safeguard keeping CI from hanging forever; always gather thread dumps, fix the owner, and verify clean termination.

### 17.3. Rerunning failures does not fix leaks

`rerunFailingTestsCount` retries failing methods, leaving resources leaked by the first attempt alive if running in the same fork/context without cleanup. Even if the second run passes, treat the first failure as real diagnostic evidence—never use reruns as a permanent workaround.

### 17.4. Exit codes vs executed tests

An exit code 0 suite can mean:
- All tests legitimately passed.
- Some tests were disabled/skipped.
- A fork timed out and got force-cleaned per plugin policy.
- External Docker resources kept running outside the JVM.
- A test failed initially and passed on rerun (recorded as flaky).

Always check Surefire XML counts, flake logs, and resource owners afterward. Never equate exit code 0 with a healthy port/thread/resource lifecycle.

### 17.5. CI isolation

On shared runners:
- Use dynamic ports.
- Use unique file and temp names.
- Namespace Docker containers and networks where needed.
- Attach process-level cleanup hooks for job-owned child processes.
- Never kill unrelated processes occupying a port.
- Avoid unisolated reuse of durable external DB state.
- Apply bounded timeouts collecting diagnostics before hard-stopping.

## 18. Specific bugs and how to fix them

### 18.1. Test port 8080 conflicts

**Wrong:**

~~~properties
server.port=8080
~~~

across multiple full integration tests with divergent contexts running concurrently. **Right when no fixed-port requirement exists:** use `RANDOM_PORT`/`server.port=0` and inject the bound port. When fixed ports are mandatory, serialize ownership or isolate environments.

### 18.2. Test manually stops the embedded server while Spring still uses it

**Wrong:** calling `webServer.stop()` from `@AfterEach` inside `@SpringBootTest(RANDOM_PORT)`; the next class reuses the cached context and hits a dead port while beans/cache still appear active.

**Right:** let Spring manage the server with its context; to test shutdown, build an isolated context and close it, or use a dedicated non-parallel/unshared `@DirtiesContext` class.

### 18.3. Unclosed executors

**Wrong:**

~~~java
static final ExecutorService EXECUTOR =
        Executors.newFixedThreadPool(4);
~~~

in a utility class with no end-of-suite owner. It outlives tests and holds non-daemon threads open. **Right:** inject a Spring-managed `ThreadPoolTaskExecutor` or instantiate within test scope and call shutdown + bounded await in `finally`/`@AfterAll`.

### 18.4. Unclosed `ScheduledExecutorService`

`Executors.newSingleThreadScheduledExecutor()` spawns threads and holds queued scheduled tasks. Stop accepting schedules, cancel periodic futures, and shut down the scheduler at the right owner. For Spring `ThreadPoolTaskScheduler`, let the context own it with explicit shutdown policies.

### 18.5. `@PreDestroy` logs an error yet continues

When cleanup throws, Spring often logs a warning and continues destroying remaining beans. Tests can still pass despite a leaked resource. In critical lifecycle tests, assert **post-close state** and capture cleanup exceptions instead of merely asserting `context.close()` threw nothing.

### 18.6. Hikari pool still running

Normal if the cached context remains active. A leak if the test manually ran `new HikariDataSource()` without `close()`. Distinguish by bean ID/name and owner.

### 18.7. WireMock still listening

Valid for its scope if managed by a class/root-scoped JUnit extension. A leak if the test called `server.start()` without `server.stop()`. Use dynamic ports, scope cleanup cleanly, and never wipe shared mappings while parallel tests send requests.

### 18.8. Lingering Testcontainers Docker resources

Stops upon context close when Spring-managed in a cached context. Stops per singleton owner for JVM singletons. Stays up intentionally across runs if local reuse is enabled. Verify ownership/policy before calling `docker stop`; **never** stop containers still serving another suite.

### 18.9. Leftover Reactor Netty schedulers

Test-created custom `Scheduler`/`LoopResources` without `dispose()` leak threads. Framework-managed global reactor resources legitimately serve multiple contexts. Dispose only test-owned schedulers without shutting down global schedulers arbitrarily.

### 18.10. Files fail to delete on Windows

Keeping `FileInputStream`/`FileChannel` open breaks `@TempDir` cleanup under Windows file locking. Use try-with-resources and wait for background workers before returning. Never hack around locks with sleep-retry loops.

### 18.11. SQL pool exhaustion

Rising Hikari pending connections stem from unclosed `Connection`s, long-held transactions, tiny pool sizes, or DB failures. Log borrower stacks and metrics to separate real leaks from legitimate contention. Increase pool size only after confirming the root cause.

### 18.12. JUnit `@Timeout` thread hops

Under test-managed transactions or worker threads, preemptive timeouts prevent `ThreadLocal` context propagation. Assert shutdown/transactions cleanly after completion at explicit boundaries.

### 18.13. Orphaned child processes

When launching servers with `ProcessBuilder`, destroying only the parent PID can leave child processes running. Track OS process trees/ownership, terminate gracefully with bounded waits and emergency force cleanup, without ever killing an unrelated reused PID.

### 18.14. Post-test logs do not automatically prove a “leak”

If a cached context hosts a valid `@Scheduled` bean, logs naturally appear between tests. The real question is whether that job **should run in test environments**; if not, gate triggers via profiles or isolate instead of demanding logs go silent right after every `@Test`.

## 19. Troubleshooting matrix

| Symptom | Possible cause | Evidence to gather | Right fix |
| --- | --- | --- | --- |
| `Address already in use` | Fixed port or unclosed socket | PID, `LISTEN` address, context key | `RANDOM_PORT` / close owner |
| Port open after method | Cached Spring context | TestContext cache stats | Do not call it a leak while context lives |
| Port open after explicit `context.close` | Listener/custom socket unclosed | OS PID/port + bean lifecycle | Fix destroy callback |
| Maven passes yet fork hangs | Non-daemon worker, shutdown hook | `jcmd Thread.print` | Shutdown / await tasks |
| Worker thread `WAITING` | Idle managed executor or leak | Owner + stack + context state | Act only if it outlives owner |
| Executor queue growing | Tasks fail to drain/complete | Queue/active metrics | Bounded queue + task completion |
| Scheduled logs after test | Scheduler still active | `@EnableScheduling`/profile/context | Disable / manual trigger |
| DB connection refused in next class | Container stopped early | Docker port/lifecycle + context cache | Spring-managed Testcontainers |
| Hikari pool threads remain | Cached context or unclosed raw pool | Bean ownership + Hikari metrics | Scope `close()` properly |
| Too many open files | Unclosed channels/sockets | `lsof` / `/proc/fd` trend | Try-with-resources |
| `TempDir` cleanup error | Open stream/lock | File owner / Windows handles | Close file resources |
| Test A breaks Test B | Unawaited background work, stale state | Future completion / event timeline | Await + unique fixtures |
| Reactor threads remain | Un-disposed custom scheduler | Thread names + scheduler owner | Dispose owned scheduler |
| Kafka consumer still active | Listener in cached context | Listener lifecycle, group/topic | Stop / namespace |
| WireMock port collision | Per-class static server unstopped | PID/port + JUnit extension scope | Dynamic port / `afterAll` |
| `@DirtiesContext` breaks other test | Context closed during parallel run | TestContext logs | Isolate / avoid parallel |
| Docker resources multiply | New container per context | `docker ps` + context counts | Share with explicit lifetimes |
| Build green due to skipped tests | Integration tests never ran | Surefire reports | Enforce executed counts |
| High timeouts still fail | Leaked owner / wrong port | Thread/port ownership | Fix code, not timeout |
| Forced fork halt | Non-daemon / shutdown hook | Surefire shutdown logs | Fix cleanup |
| Socket in `TIME_WAIT` | Normal TCP teardown | Socket `STATE` | Do not confuse with `LISTEN` |
| Port rebind test flaky | OS reuse / external process race | Bind address / PID | Isolate + gather evidence |
| Cross-process test conflict | Global fixed port/shared resource | CI job PID/namespace | Unique ports/resources |
| Shutdown close throws | Buggy destroy callback | Logs + post-close state | Repair idempotent cleanup |
| Rising JVM memory | Heap/native leak or retained data | JFR / heap / FD / threads | Isolate actual resource type |

## 20. Step-by-step investigation workflow

### Step 1 — Define the expected lifetime

Fill in this sheet:

~~~text
Resource: port 18081 / thread diag-managed-1 / datasource...
Created by: test method? Spring bean? JUnit extension? Docker?
Used until: end of method? end of class? context close? JVM exit?
Close owner: who calls close/shutdown/stop?
Evidence: PID, thread dump, bean name, ContextClosedEvent?
Expected state after owner closes: ...
~~~

Without identifying the owner, you cannot scientifically diagnose a leak.

### Step 2 — Reproduce in a narrow scope

- Run the test alone.
- Run its class.
- Run two classes in sequence.
- Run the suite randomly/in parallel if overlap triggers it.
- Record dynamic ports, context cache keys, thread prefixes, and PIDs.
- Use synthetic test data only; stay off production endpoints.

### Step 3 — Identify the resource owner

- Java try-with-resources or a Spring bean?
- JUnit Testcontainers extension or a Spring container bean?
- Executor created by `@Async` infrastructure or `Executors.new...`?
- Is a cached context legitimately still active?
- Were file streams closed before cleanup?
- Is an OS process a child of the test process?

### Step 4 — Gather diagnostics before stopping anything

- `jcmd Thread.print`.
- `ss`/`lsof`/`netstat`/`Get-NetTCPConnection`.
- Hikari/executor metrics.
- TestContext cache `DEBUG` logs.
- Maven Surefire/fork logs.
- `docker inspect`/`ps` if relevant.
- Socket `LISTEN` vs `TIME_WAIT` state.
- Root exception stack traces.

### Step 5 — Fix at the right owner

- Test-owned resource: `try-with-resources`/`finally`/`@AfterEach`.
- Class-owned resource: `@AfterAll`/JUnit extension close scope.
- Spring bean: `@PreDestroy`/`@Bean(destroyMethod)`/managed executor.
- `ApplicationContext`: close only in matching test scenarios; never close shared cached contexts manually.
- External containers/brokers: stop at the right owner and only after consumers close.
- Background tasks: bounded completion/cancellation + idempotent cleanup.

### Step 6 — Verify with post-close assertions

- Isolated context closed: listener port released on the same address.
- Executor bean destroyed: `isShutdown`/`awaitTermination`.
- Ad-hoc pool: zero pending work, `isTerminated`.
- Sockets/streams: closed state and resource reusable.
- Data fixtures: never mutated by lingering workers after cleanup.
- Suite: zero cross-class collisions or hangs.

### Step 7 — Prevent regressions

- Add lifecycle tests to CI.
- Run multiple iterations for sporadic bugs.
- Never demand zero JVM threads or sockets globally.
- Never rely on fixed sleeps.
- Track performance/resource trends.
- Document unavoidable OS/window/network caveats.
- Never accept “`mvn test` PASS” if forced fork halts or skips hid a bug.

## 21. Exercises

1. Run `RandomPortAndManagedTaskTest`; inspect `@LocalServerPort` and identify the bound port.
2. Experiment with `DEFINED_PORT` and `server.port=8080` across two contexts and analyze the collision; never leave this in shared CI.
3. Use `ss -ltnp` or `Get-NetTCPConnection` to locate the PID of a test-owned listener.
4. Run `PortOnlyContextLifecycleTest` and explain why it constructs an isolated context.
5. Temporarily omit `context.close()` in an isolated branch and watch the socket stay `LISTEN`; restore cleanup immediately afterward.
6. Set `server.address=127.0.0.1` vs `0.0.0.0` and observe differences in socket binding/visibility.
7. Bind `ServerSocket(0)` so the OS assigns an ephemeral port, log it, and verify close/rebind.
8. Run `ManagedResourcesLifecycleTest` and inspect `ThreadPoolTaskExecutor.isShutdown` after context close.
9. Add a task waiting on a bounded `CountDownLatch` and observe shutdown with `setWaitForTasksToCompleteOnShutdown(true)`.
10. Test a task ignoring interruption inside a **dedicated bounded process** and take a thread dump; never add infinite tasks to the default suite.
11. Instantiate an `ExecutorService` in a test, shut it down in `finally`, and check `awaitTermination`.
12. Swap to early `shutdownNow` and explain which tasks get cancelled along with potential business side effects.
13. Declare `@Bean(destroyMethod="close")` owning a `ServerSocket` and verify closure after context close.
14. Add `@PreDestroy` to a custom client and verify idempotent closing.
15. Design a `SmartLifecycle` wrapper for a message consumer defining phases and completion callbacks.
16. Enable `@EnableScheduling` in a separate profile and observe background logs in a cached context.
17. Disable scheduler triggers in the test profile, invoke the job method directly, and assert DB state.
18. Add an `@Async` service returning `CompletableFuture` and await with a bounded timeout before cleanup.
19. Try `@DirtiesContext(AFTER_CLASS)`, measure context startup cost and listener closure; avoid running in parallel with shared-context classes.
20. Compare a Spring-managed Testcontainers bean against JUnit `static @Container` close ordering.
21. Instantiate a raw test-owned `HikariDataSource` and verify closure when the fixture finishes.
22. Borrow a JDBC `Connection` with try-with-resources and inspect active pool counts afterward.
23. Open a file handle inside `@TempDir` without closing it on a learning branch; observe Windows cleanup failures and fix it.
24. Run `jcmd Thread.print` while `ad-hoc-test-owned` is executing to locate it, then verify it disappears after cleanup.
25. Record 60s of JFR while reproducing a leak and compare thread starts/ends before and after.
26. Distinguish a `TIME_WAIT` socket from `LISTEN` in `netstat` output.
27. Start a `WireMockServer` on a dynamic port and stop it in `@AfterAll` at its owning class.
28. With a shared Redis/Kafka container, use unique keys/topics/groups and close scoped listeners/clients.
29. Run Maven Surefire with multiple forks and explain per-JVM context caching vs OS process/PID differences.
30. Inspect Surefire shutdown timeout settings and report forced process halts rather than calling them clean passes.
31. Expose metrics for executor active/queued tasks and Hikari active/idle connections.
32. Loop create/use/close 50 times on a small test-owned resource and track FD/thread trends.
33. Write an ADR documenting owners and teardown paths for every external client, scheduler, and socket in the module.
34. Review an existing test using `Thread.sleep(3000)` before a negative async assertion and replace it with a completion signal.
35. Assemble a full bug report including PID, socket state, thread stacks, context key, owner lifetime, and fix verification.

## 22. Pre-merge checklist

- [ ] Distinguished method end, class end, context close, and JVM exit?
- [ ] Every resource has a clear owner and shutdown policy?
- [ ] Understood that Spring TestContext cache legitimately keeps shared resources live across tests?
- [ ] Never asserted ports/threads vanish right after a `@SpringBootTest` method ends?
- [ ] Embedded server tests use `RANDOM_PORT` unless fixed ports are strictly required?
- [ ] Testcontainers host ports are never hardcoded?
- [ ] Verified bind addresses and TCP `LISTEN` vs `TIME_WAIT` states?
- [ ] Confirmed owning PID before killing any process on a port collision?
- [ ] Never called `close()` on a shared cached context inside `@AfterEach`?
- [ ] Created and explicitly closed an isolated context when testing server shutdown?
- [ ] Java `ServerSocket`/file streams wrapped in try-with-resources?
- [ ] Test-created `ExecutorService` instances shut down/`awaitTermination` with deadlines?
- [ ] Futures/tasks awaited or cancelled before fixture cleanup?
- [ ] `Thread.sleep` never used to fake synchronization?
- [ ] Threads carry clear prefixes so owners stand out in `jcmd`/stack dumps?
- [ ] Daemon flags never abused to hide resource leaks?
- [ ] Spring `ThreadPoolTaskExecutor` beans configured with intentional shutdown policies?
- [ ] `@PreDestroy`/`DisposableBean`/`destroyMethod` wired at the proper owners?
- [ ] `SmartLifecycle` stop ordering protects dependent resources?
- [ ] `@Scheduled` jobs disabled/gated when unneeded in tests?
- [ ] `@Async` methods have completion signals, timeouts, and error handling?
- [ ] `HikariDataSource`/JDBC connections closed within proper scopes?
- [ ] HTTP clients, Reactor schedulers, and broker listeners closed/disposed by owners?
- [ ] Testcontainers lifecycles aligned with Spring context caching?
- [ ] `@DirtiesContext` never sprayed broadly to mask symptoms?
- [ ] Parallel tests never wipe shared global resources belonging to others?
- [ ] Captured `jcmd`/OS port/FD snapshots when investigating real hangs?
- [ ] Distinguished live JVM threads from OS child processes and Docker resources?
- [ ] No secrets or customer data exposed in thread dumps, logs, or artifacts?
- [ ] CI never masks leaks behind forced fork halts or skipped tests?
- [ ] Post-close state explicitly verified instead of trusting `"closing"` log lines?
- [ ] Maven/Surefire executed counts and actual results verified upon running?
- [ ] Regression tests guard discovered failure modes?
- [ ] Lifecycle tests never introduce deliberate infinite hangs into the default suite?

**Conclusion:** A port, thread, or connection remaining open **after a single test method** does not automatically signify a leak. Spring Boot and Spring TestContext intentionally cache `ApplicationContext` instances, keeping servers, executors, DataSources, and listeners alive for reuse across tests. Real leaks occur when resources **outlive their owner's lifetime or lack a close/destroy path**. Proper debugging identifies the owner → identifies the expected release milestone → captures port/PID/thread/resource evidence → fixes the owner's lifecycle → verifies post-close state. Use try-with-resources/`finally` for test-owned resources, Spring lifecycle/destroy callbacks for managed beans, bounded waits and completion signals for async work, and random ports with context-scoped shutdown for embedded servers. Never raise timeouts, force-kill, set daemon flags, abuse `@DirtiesContext`, or sleep to mask broken ownership.

## 23. Official references

- Spring Framework 6.2 — TestContext Context Caching (scope, default 32, LRU, shutdown hook): https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework 6.2 — `@DirtiesContext` semantics and context close: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html
- Spring Framework 6.2 — Parallel Test Execution: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html
- Spring Boot 3.5 — Testing Spring Boot Applications, RANDOM_PORT and `@LocalServerPort`: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Graceful Web Server Shutdown and lifecycle timeout: https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html
- Spring Boot 3.5 — Task Execution and Scheduling / shutdown configuration: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.5 — Testcontainers, managed `@Bean` + `@ServiceConnection` lifecycle: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Framework 6.2 — `ThreadPoolTaskExecutor` API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework 6.2 — `ExecutorConfigurationSupport` shutdown/await policies: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html
- Spring Framework 6.2 — `SmartLifecycle` API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Java SE 17 — `ExecutorService` shutdown and `awaitTermination`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 — `ServerSocket` and `AutoCloseable`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html
- Java SE 17 — `ThreadMXBean` and thread inspection: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- JDK — `jcmd` diagnostic command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- JDK — Java Flight Recorder: https://docs.oracle.com/en/java/javase/17/jfapi/
- Maven Surefire — Forked JVM Shutdown, forced exit timeout: https://maven.apache.org/surefire/maven-surefire-plugin/examples/shutdown.html
- Maven Surefire — Fork options and parallel execution: https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options-and-parallel-execution.html
- JUnit Jupiter 5 — Test lifecycle and `@TempDir`: https://docs.junit.org/5.12.0/user-guide/#writing-tests-built-in-extensions-TempDirectory
- Testcontainers Java — JUnit 5 lifecycle: https://java.testcontainers.org/test_framework_integration/junit_5/
- Testcontainers Java — Singleton Containers: https://java.testcontainers.org/test_framework_integration/manual_lifecycle_control/#singleton-containers
