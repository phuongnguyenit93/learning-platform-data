# Enabling Virtual Threads in Spring Boot via `spring.threads.virtual.enabled` (Java 21+)

## 1. Goal and key takeaways

In a Spring Boot web application, many requests spend time waiting on databases, external HTTP services, or file/network I/O. With a **thread-per-request** model, traditional platform threads are relatively expensive to keep tied up while waiting. Java's **virtual threads** let you keep readable synchronous code while serving many more waiting tasks on a smaller number of OS threads actually executing Java code.

To tell Spring Boot to enable virtual thread support on a compatible runtime, use:

```properties
spring.threads.virtual.enabled=true
```

Primary requirement: **the application must run on Java 21 or newer** using a Spring Boot version that supports this property (**Spring Boot 3.2+**; examples here use Spring Boot 3.x with Spring MVC and embedded Tomcat). Setting only Java source/target compatibility to 21 is insufficient if the runtime process actually launches on an older JDK.

**Remember first:** enabling virtual threads changes how certain tasks/requests are executed; it **does not turn an HTTP request into something else**, does not automatically speed up CPU-bound code, and does not expand database connection pools.

## 2. What is a virtual thread and why does it fit the web runtime?

`Thread` in Java 21 comes in two primary forms:

- **Platform thread:** typically maps fairly directly to an OS thread; the operating system schedules the OS thread. If a platform thread waits on blocking I/O, it occupies that OS thread resource throughout the wait.
- **Virtual thread:** still a `java.lang.Thread`, but the JVM manages scheduling. A virtual thread runs on a platform thread called a **carrier**. When encountering supported blocking operations, the JVM can *unmount* the virtual thread from its carrier so the carrier can run another virtual thread; once ready, it is scheduled to resume.

Illustration of a request waiting on a DB:

```text
Platform thread:
  receive request -> process -> wait on DB (holds OS thread) -> resume -> response

Virtual thread:
  receive request -> process -> wait on DB (virtual thread parks;
                                            carrier can run other tasks)
                  -> resume -> response
```

Virtual threads **do not execute code faster**. Their main value is enabling **much higher concurrency for I/O-waiting work** with fewer OS threads sitting idle. For CPU-heavy work, CPU core count and CPU utilization remain the real limits. Creating many virtual threads does not create more cores.

| Property | Platform thread | Virtual thread |
| --- | --- | --- |
| Who schedules it? | Primarily the operating system | JVM schedules onto carrier platform threads |
| Per-thread cost | Relatively high | Significantly lower; can be created per task |
| JVM-supported I/O wait | Typically holds an OS thread | Usually parks and yields the carrier |
| Common pattern | Bounded worker thread pool | One virtual thread per task; do not pool virtual threads |
| Best suited for | General tasks, CPU tasks, or tuned pool setups | Many independent, short-lived blocking I/O tasks |
| Is it a Java `Thread`? | Yes | Yes; `Thread.currentThread().isVirtual()` returns `true` on a virtual thread |

Do not confuse a **virtual thread** with an HTTP request, session, socket, reactive stream, or CPU core. A keep-alive socket can deliver many separate requests to the server; the server can handle each request on its own virtual thread.

## 3. Prerequisites and configuration

### 3.1. Minimum requirements

1. Install **JDK 21+** and verify the process running Spring Boot uses that JDK. Check with `java -version` and `mvn -version` (or `./mvnw -version` if using Maven Wrapper).
2. Use Spring Boot **3.2 or newer** with integrated virtual-thread support. Java 21 alone does not make older Boot versions recognize the property.
3. For the servlet web example, use `spring-boot-starter-web` (Spring Boot 3.x, Spring MVC with default embedded Tomcat). Request thread behavior also depends on server type and custom executors.
4. Set the property and **restart** the application for runtime configuration to take effect; check that no profile or environment variable overrides the value.

`--enable-preview` is not needed: virtual threads are a finalized feature in Java 21.

### 3.2. `application.properties`

In `src/main/resources/application.properties`:

```properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
```

The first line enables virtual threads. The second keeps the JVM alive if only daemon threads remain; this is especially worth considering for apps running `@Scheduled` or background tasks. A normal web server may already have non-daemon threads keeping the process alive, yet setting `spring.main.keep-alive=true` is Spring Boot's recommended choice when using virtual threads.

### 3.3. Equivalent YAML configuration

In `src/main/resources/application.yml`:

```yaml
spring:
  threads:
    virtual:
      enabled: true
  main:
    keep-alive: true
```

Pick only one format if both describe the same configuration to avoid conflicting config sources. Per Spring Boot's externalized configuration, you can override on the command line:

```bash
java -jar app.jar --spring.threads.virtual.enabled=true --spring.main.keep-alive=true
```

Here `app.jar` stands for your built JAR filename; replace it with the project's actual JAR. With environment variables, the equivalent name is `SPRING_THREADS_VIRTUAL_ENABLED=true`. Check profile/env/CLI precedence if runtime behavior differs from expectations.

## 4. When the property is enabled, what does Spring Boot change?

For components auto-configured by Spring Boot, virtual threads apply at supported integration points; **it does not mean every thread inside the JVM becomes virtual**.

### 4.1. Spring MVC on embedded servlet servers

As introduced in Spring Boot 3.2, **embedded Tomcat and Jetty** can use virtual threads for HTTP request handling when the property is enabled on Java 21+. Spring MVC controllers keep their familiar style:

```java
@GetMapping("/orders/{id}")
public Order find(@PathVariable long id) {
    return orderService.find(id);
}
```

This is an **illustrative snippet**: `Order` and `orderService` belong to your application and cannot compile standalone. When a request runs on a virtual thread, compatible blocking JDBC/HTTP client calls can keep straightforward sequential syntax. You do not need to rewrite controllers to reactive or add `@Async` just to see `Thread.currentThread().isVirtual()`.

Note: proxies, acceptors, event loops, carriers, GC, and other internal threads may remain platform threads; a custom filter or component using its own executor can move work onto another thread. When using custom servlet containers or executors, verify actual runtime behavior instead of assuming every controller always executes on a virtual thread.

### 4.2. Task execution and `@Async`

When no custom executor alters auto-configuration, Spring Boot configures `AsyncTaskExecutor` backed by a virtual-thread `SimpleAsyncTaskExecutor` when the property is enabled. Integrations that can use it include `@EnableAsync`/`@Async`, Spring MVC async processing, and other components.

- Adding `@Async` to a method alone is not enough without `@EnableAsync`, or if self-invocation within the same object bypasses the Spring proxy.
- If the application defines a custom `Executor`, `AsyncConfigurer`, or `applicationTaskExecutor` bean, that executor may take precedence and **not necessarily use virtual threads**.
- `SimpleAsyncTaskExecutor` creates a thread per task; it is **not a thread pool**. Settings such as `spring.task.execution.pool.core-size`, `max-size`, and `queue-capacity` do not apply to it the way they do to `ThreadPoolTaskExecutor`.
- Depending on Boot version, advanced executor properties exist to force auto-configuration preference; always check the documentation for your exact version before changing them.

### 4.3. Scheduled tasks

When Spring Boot auto-configures a scheduler with virtual threads enabled, it uses `SimpleAsyncTaskScheduler` instead of `ThreadPoolTaskScheduler`. Thus scheduler pool-size properties (such as `spring.task.scheduling.pool.size`) no longer apply like they do for a traditional pool.

**Easy-to-miss detail:** in `SimpleAsyncTaskScheduler`, `fixedDelay` tasks execute on a single scheduler thread, whereas `fixedRate`/cron tasks may spawn separate execution threads. Measure and test carefully if scheduled tasks are long-running or must not overlap.

Virtual threads are always **daemon threads**. If an application has no non-daemon thread keeping the JVM alive (notably apps running only scheduled tasks), the JVM can exit. Use `spring.main.keep-alive=true` to prevent premature exit where appropriate.

### 4.4. WebFlux and Netty

This property does not turn Spring WebFlux's Netty event loop into virtual threads. WebFlux continues using a reactive/event-loop architecture; blocking tasks integrated via `applicationTaskExecutor` may use virtual threads if auto-configuration applies.

Therefore, the most direct, observable benefit in this article lies in **Spring MVC + Tomcat/Jetty**. Do not treat enabling virtual threads as an excuse to run blocking I/O carelessly on WebFlux event loops.

## 5. Runnable example: verifying HTTP requests run on virtual threads

Create a **Spring Boot 3.x (3.2 or newer)**, **Java 21+** project with **Spring Web** (`spring-boot-starter-web`). This example uses package `com.example.demo` and default embedded Tomcat.

**File 1 — `src/main/java/com/example/demo/DemoApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

**File 2 — `src/main/java/com/example/demo/ThreadProbeController.java`**

```java
package com.example.demo;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ThreadProbeController {

    @GetMapping("/thread-info")
    public ThreadInfo threadInfo() {
        Thread current = Thread.currentThread();
        return new ThreadInfo(current.isVirtual(), current.threadId());
    }

    @GetMapping("/wait")
    public ThreadInfo waitFor(
            @RequestParam(defaultValue = "200") long ms
    ) throws InterruptedException {
        if (ms < 0 || ms > 2000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "ms must be between 0 and 2000"
            );
        }

        Thread.sleep(ms);
        return threadInfo();
    }

    public record ThreadInfo(boolean virtual, long threadId) {}
}
```

**File 3 — `src/main/resources/application.properties`**

```properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
server.port=8080
```

Run the project:

```bash
java -version
mvn spring-boot:run
```

Open another terminal:

```bash
curl -s http://localhost:8080/thread-info
curl -s "http://localhost:8080/wait?ms=200"
```

With default Tomcat, applied configuration, and no interfering custom executor, the JSON looks like:

```json
{"virtual":true,"threadId":73}
```

`threadId` here is **only an example value**: the actual number varies by JVM and request. In a supported environment, `"virtual":true` is the decisive indicator. `/wait` returns a similar structure after sleeping ~200 ms; `Thread.sleep` illustrates waiting and is **not a data-processing example or real throughput benchmark**. HTTP responses are serialized after the handler returns; this example inspects the thread directly inside the handler.

To compare, change only:

```properties
spring.threads.virtual.enabled=false
```

Then **restart** and call `/thread-info`. With default embedded Tomcat, the expected result is `"virtual":false` because requests run on platform threads. If the result does not change, check the actual runtime JDK, Boot version, active profiles, and custom server/executor configuration.

**Important:** the controller does not create threads manually. It queries the thread currently executing the handler. This check is far more reliable than guessing from thread names: virtual threads may have empty names or names depending on executor and version.

## 6. Practical benefits and unchanged limits

### 6.1. When is it worth trying?

Consider an endpoint doing:

```text
HTTP request
  -> read DB (mostly waiting on I/O)
  -> call remote API (more waiting)
  -> brief computation
  -> HTTP response
```

When many such requests arrive concurrently, the platform-thread-per-request model needs many blocked worker threads; virtual threads allow higher concurrency with fewer occupied carriers. The outcome can be **higher throughput or more efficient resource usage under heavy blocking I/O load**.

However, virtual threads **do not guarantee faster individual requests** and provide little help for CPU-bound algorithms. If the DB hits CPU/connection limits, an upstream system enforces rate limits, or the host runs out of RAM, enabling virtual threads does not remove those limits.

### 6.2. Limits you still must enforce

- **JDBC connection pools** (such as HikariCP) still have a maximum connection count; many virtual threads can end up waiting for connections. `spring.datasource.hikari.maximum-pool-size` is separate and does not scale automatically with virtual threads.
- **Outbound HTTP connection pools**, rate limits, socket counts, request caps, queues, and timeouts of other services still apply.
- **Servlet container limits** on connections, requests, and non-worker-thread resources still apply.
- **Backpressure and downstream protection:** removing the platform-worker thread cap allows the app to send far more concurrent calls to DBs/dependent services. When concurrency must be capped, use mechanisms like `Semaphore`, connection pool caps, or rate limiters; **do not pool virtual threads solely to cap concurrency**.
- **ThreadLocal, transactions, security context:** virtual threads still support `ThreadLocal`, yet each task may get a fresh thread. Do not rely on thread reuse to cache heavy objects; preserve request/transaction scopes, close resources, and avoid shared mutable state in singleton controllers.
- **Traditional pool settings:** once Tomcat uses a virtual-thread executor, settings like `server.tomcat.threads.max` and `server.tomcat.threads.min-spare` no longer cap platform-worker threads as before. Do not confuse them with connection, DB pool, or memory limits.

Brief example protecting a limited resource:

```java
// Illustrative snippet inside a service; externalCall() is application-defined logic.
private final java.util.concurrent.Semaphore permits =
        new java.util.concurrent.Semaphore(10);

public String callLimitedService() throws InterruptedException {
    permits.acquire();
    try {
        return externalCall();
    } finally {
        permits.release();
    }
}
```

This snippet **cannot compile standalone** because `externalCall()` is defined by the application. Its purpose: permit at most 10 concurrent calls to a sensitive resource even when thousands of virtual threads are waiting.

## 7. Pinning, Java versions, and operational choices

**Pinning** occurs when a virtual thread cannot unmount from its carrier during a blocking operation, holding the carrier occupied. When pinning happens frequently and for long durations, scalability can degrade.

- On **Java 21–23**, blocking inside certain `synchronized` blocks and native code can pin the carrier. Not every `synchronized` causes an issue: significant risk arises when long or frequent blocking happens inside it.
- **Java 24+** includes **JEP 491**, eliminating most monitor/`synchronized`-related pinning. Certain cases involving native/foreign code still require monitoring. That is why Spring Boot documentation recommends Java 24+ for a better virtual-thread experience when your environment allows.
- On Java 21 environments, JDK Flight Recorder can capture `jdk.VirtualThreadPinned` events alongside thread-dump tools. Specific flags and diagnostic capabilities depend on JDK version; do not apply JDK 21 debugging flags to newer JDKs without verifying version documentation.

Generate a thread dump showing virtual threads (run on a machine with a supporting JDK):

```bash
jcmd <pid> Thread.dump_to_file -format=json threads.json
```

Replace `<pid>` with the Java process's actual PID. This produces `threads.json` for analysis; counts, states, and thread names depend on active load. It is an observational tool with **no fixed stdout**, and thread counts alone do not prove the system got faster.

When evaluating in staging/production, compare **before and after** under identical workloads: requests/second, p95/p99 latency, errors/timeouts, CPU, RAM/GC, DB pool wait, outbound pools, open connections, thread dumps, and JFR if needed. A single demo request sleeping 200 ms confirms execution mechanics; it does not prove a performance improvement.

## 8. Configuration mistakes and troubleshooting

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| Property enabled yet `isVirtual()` stays `false` | Runtime Java below 21; Boot version lacks support; profile override; custom server/executor | Check actual `java -version`, Boot version, effective config sources, servlet container type |
| `@Async` still runs on platform threads | Missing `@EnableAsync`, self-invocation, or custom `Executor`/`AsyncConfigurer` | Check active executor bean and Spring proxy invocation |
| Changing `spring.task.execution.pool.max-size` has no effect | Executor switched to virtual-thread `SimpleAsyncTaskExecutor`, which has no pool to resize | Inspect executor type; bound downstream with appropriate mechanisms |
| Changing `server.tomcat.threads.max` no longer caps concurrency as before | Tomcat handles requests with virtual threads | Separate worker-thread pools from connection/DB limits |
| App running only scheduled tasks exits immediately | Virtual threads are daemon; no non-daemon thread keeps JVM alive | Set `spring.main.keep-alive=true` and verify lifecycle |
| Throughput does not improve or drops | CPU-bound work, pinning, small DB/HTTP pools, rate limits, locks, or contention | Check profiler/JFR, p95/p99, and the real bottleneck before tuning |
| WebFlux on Netty still uses event-loop threads | Property does not turn the whole Netty event loop into virtual threads | Check whether blocking tasks use `applicationTaskExecutor` |

Never infer from seeing the property in a file that virtual threads are definitely active. **Verify the real thread along the exact code path you care about**, like `/thread-info`, and inspect custom executors.

## 9. Self-check questions

1. **Which Java version is required to enable virtual threads with this property?** Java **21 or newer**, on a supporting Spring Boot version (3.2+).
2. **Does setting `spring.threads.virtual.enabled=true` make CPU-bound controllers run faster?** No; virtual threads improve concurrency when most time is spent waiting on I/O, not raw CPU speed.
3. **Why might `@Async` still run on a platform thread?** It may be using a custom executor/`AsyncConfigurer`, or the call bypassed the Spring proxy.
4. **Does Tomcat's `server.tomcat.threads.max` still limit virtual threads the old way?** No. That configures the traditional worker pool; other resource limits still apply.
5. **Why can an application running only `@Scheduled` tasks exit on its own?** Virtual threads are daemon threads; consider `spring.main.keep-alive=true`.
6. **Once enabled, how do you verify an MVC request runs on a virtual thread?** Print/check `Thread.currentThread().isVirtual()` directly inside the handler under the proper server setup.
7. **Should you create a pool of virtual threads to avoid overloading the DB?** No; rely on DB pool bounds and use semaphores/rate limiters when needed.

## 10. Official documentation by version

- Spring Boot — Virtual threads: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html#features.spring-application.virtual-threads
- Spring Boot — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.2 Release Notes — virtual thread support for Tomcat/Jetty and executors: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.2-Release-Notes
- Oracle — Virtual Threads (Java 21): https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- OpenJDK — JEP 491, pinning improvements in Java 24: https://openjdk.org/jeps/491

**Conclusion:** with **Spring Boot 3.2+ and Java 21+**, set `spring.threads.virtual.enabled=true` so supported Spring Boot components use virtual threads. Start by testing Spring MVC + Tomcat, verify with `Thread.currentThread().isVirtual()`, keep DB/downstream limits intact, and measure real load before rolling out broadly.