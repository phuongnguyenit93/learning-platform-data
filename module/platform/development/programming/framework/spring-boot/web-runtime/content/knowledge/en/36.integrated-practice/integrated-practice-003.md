# Comparing the Same Task Across MVC with Platform Threads, Virtual Threads, and WebFlux

**Scope:** Spring Boot → web-runtime → **Integrated Practice**.

This practice puts **the same I/O-latency HTTP task** on three request-serving models:

1. **Spring MVC + Tomcat + platform threads**: each synchronous request typically occupies one worker servlet thread from the pool while waiting on the backend.
2. **The same Spring MVC/Tomcat + virtual threads**: you still write synchronous code and blocking HTTP calls, but Java 21+ lets many virtual threads park while awaiting JVM-supported I/O without holding carrier threads.
3. **Spring WebFlux + Reactor Netty + WebClient**: expresses the task with `Mono`, executes non-blocking HTTP, and resumes the pipeline when the response arrives; never blocks event-loop threads during the wait.

The main learning point is **not to declare one model universally faster**, but to understand why **the exact same workload** differs in thread usage, concurrency bounds, error propagation, and backpressure. The lesson provides a **JDK 21 runnable** Maven multi-module project, three HTTP services across four processes, unit/integration smoke tests, a benchmark tool built with the Python standard library, guidance on measuring p50/p95/p99, RPS, CPU, threads, backend resources, high-load failures, and architecture selection criteria.

**Version requirements:** Spring Boot 3.5.16 (Spring Framework 6.2), shared Java **21** for a fair comparison. Spring Boot 3.5 has a minimum of Java **17**, so **MVC platform/WebFlux** can run on Java 17 with corresponding code; **virtual threads specifically require Java 21+**, and `Thread.currentThread().isVirtual()` also requires Java 21. Boot 3.5.16 is the final OSS release of the 3.5 line (6/2026); for production systems, pick a supported/maintained release. Do not mix Boot 4.x APIs into a 3.5 project.

> **A valid comparison:** all three gateways call the **same backend** `GET /delay?ms=300` over real localhost HTTP, receive the same JSON `{"result":"ok","waitMs":300}`, and differ only in gateway execution model. The backend uses `Mono.delay` to simulate **non-event-loop-blocking wait latency**, resembling a slow downstream HTTP service; it **does not** model full production database or remote API details. This is a **simulated latency workload**, not a technology throughput certification.

## 1. The Problem: A Request Waiting 300 ms Downstream

A client calls `GET /task?ms=300`. The gateway must call downstream `GET /delay?ms=300`, await the JSON, and return a response containing:
- `mode`: the gateway model running (`mvc` or `webflux`);
- `waitMs`: requested downstream delay;
- `backendResult`: value returned by downstream (`ok`);
- `virtualThread`: `Thread.currentThread().isVirtual()` at the recording point;
- `threadName`: the Java thread name at that same point.

~~~text
                       HTTP GET /task?ms=300
                               │
                               ▼
                       Client / Load Tool
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
    MVC platform          MVC virtual            WebFlux
    Tomcat :8080          Tomcat :8082            Netty :8083
    synchronous           synchronous            reactive Mono
    RestClient            RestClient             WebClient
          │                    │                    │
          └────────────────────┼────────────────────┘
                               │
                    HTTP GET /delay?ms=300
                               ▼
                      WebFlux backend :8081
                 Mono.delay(Duration.ofMillis(ms))
                               │
                      JSON {"result":"ok",...}
                               ▼
                    Gateway returns same schema
~~~

Performing the **same functional task** means all three accept the same query parameter, validate the same bounds, call the real backend over a socket, and verify the same response content. They do **not** return the same `threadName`, since the thread model is what is being measured.

**Do not choose three different workloads** (MVC `Thread.sleep(300)`, WebFlux `Mono.delay(300)`, and virtual threads calling SQL) and compare RPS; in that case backend CPU, sockets, network, validation, and latency semantics all differ. In this lab, the shared backend uses `Mono.delay`, while the gateways use blocking `RestClient` or non-blocking `WebClient` to talk to that same backend.

## 2. Proper Definitions: Concurrency, Parallelism, Throughput, and Latency

- **Concurrency:** multiple requests making progress within overlapping time windows; most may be waiting on I/O.
- **Parallelism:** multiple CPU cores executing instructions simultaneously. More threads do not add CPU cores.
- **Latency:** time from client request to response; focus on p50, p95, and p99 rather than mean alone.
- **Throughput:** requests completed per second (RPS).
- **In-flight:** requests currently being processed and not yet finished.
- **Saturation:** whichever limit runs out first: servlet worker pool, TCP connections, DB pool, downstream, CPU, heap, file descriptors, or event-loop capacity.
- **Backpressure:** downstream/consumer mechanism regulating upstream production rate to avoid unbounded allocation; Reactive Streams provides demand signals, **which does not automatically protect the whole HTTP system from overload**.
- **Queueing:** requests waiting rather than executing immediately due to thread/connection/semaphore/worker limits; tail latency rises even while backend service time stays ~300 ms.

A useful steady-state estimation relationship is **Little's Law**:

\[
L \approx \lambda W
\]

where `L` is average in-flight requests, `λ` is RPS, and `W` is average response time (seconds). For instance, a 0.3-second latency causes concurrent demand to scale with RPS. This is a **mathematical consequence under steady-state assumptions**, not a promise that an app will hit a fixed RPS.

### 2.1. Why I/O-Bound Workloads Differ from CPU-Bound Workloads

When the gateway waits 300 ms for downstream:
- Gateway CPU is mostly **idle**; time passes waiting on network/timers.
- With platform threads, the request thread is usually held in a waiting state.
- With virtual threads, the JVM can unmount a virtual thread parked on supported I/O, freeing the carrier platform thread for other work.
- With WebFlux, Reactor registers an async continuation; when the response arrives, the event loop resumes the processing pipeline.

When the task is video encoding or continuous SHA hashing that saturates CPU, virtual threads add no CPU cores, and WebFlux does not turn a blocking CPU loop async. You must bound CPU parallelism/work stealing/worker scheduling and benchmark separately.

### 2.2. The Three Models Differ Across Layers

| Dimension | MVC platform | MVC virtual | WebFlux non-blocking |
| --- | --- | --- | --- |
| Server in lab | Embedded Tomcat | **Same embedded Tomcat** | Reactor Netty |
| Controller style | Returns DTO directly | **Same MVC code** | Returns `Mono<DTO>` |
| Downstream client | Blocking `RestClient` | **Same blocking `RestClient`** | Reactive `WebClient` |
| Thread waiting on downstream | Servlet worker platform thread usually blocks | Virtual thread waits; carrier is usually released | No event-loop worker held during wait |
| Request processing | Thread-per-request (Servlet) | Conceptually thread-per-request, virtual threads cheaper | Event-loop + callbacks/operators |
| Error programming model | Synchronous exceptions | Synchronous exceptions | Error signals in Reactor pipeline |
| Context | ThreadLocal/MDC per Servlet scope | ThreadLocal still works, though many virtual threads | Reactor Context, context propagation |
| Natural concurrency limit | Worker pool / queue | Backend pools / network / semaphores and resource budgets | Event loop, connection pool, operator concurrency / queues |
| Blocking I/O compatibility | Yes, but consumes workers | Yes, often fits virtual threads | **Never block event loop**; offload when unavoidable |
| Java minimum | Boot 3.5: Java 17 | Java 21+ | Boot 3.5: Java 17 |
| Complexity | Easy imperative authoring/debugging | Close to classic MVC, plus VT-specific operations | Requires understanding Mono/Flux, cancellation, scheduling, context |

**Important:** "MVC + virtual" is not Reactor WebFlux in disguise. It still uses `DispatcherServlet` and the Servlet API, with synchronized business flows and blocking request/response calls. "WebFlux non-blocking" does not automatically use virtual threads. Setting `spring.threads.virtual.enabled=true` in WebFlux does not turn the Reactor Netty event loop into a virtual-thread-per-request server.

## 3. MVC with Platform Threads: Requests Hold Workers

Synchronous request model:

~~~text
Tomcat acceptor
     └─ HTTP request assigned to http-nio-8080-exec-N (platform)
           ├─ controller method
           ├─ RestClient GET /delay?ms=300
           │    └─ thread waits for network response
           ├─ JSON deserialize
           └─ response to client → thread reused
~~~

A **bounded thread pool** absorbs blocking. When in-flight requests exceed the threads able to run concurrently, incoming requests queue in the accept queue/connector or get rejected/timed out. With 32 workers and ~300 ms downstream waits, roughly ~32 request threads can **wait simultaneously** in this simple model (ignoring other pools); the app can hit a thread ceiling before CPU saturates.

Example configuration:

~~~properties
server.tomcat.threads.max=32
spring.threads.virtual.enabled=false
~~~

This setting is **for the MVC platform part of the lab**. It does not bound every source of concurrency (async tasks, connection pools, downstream capacity, socket accept queues). In a real app, tune thread max and request timeouts via load testing rather than assuming more threads is always better.

### 3.1. What Platform Threads Still Do Very Well

- Straightforward imperative Java code with per-request stack traces.
- Rich Spring MVC / JDBC / servlet filter / ecosystem support.
- For moderate traffic and short blocking waits, a standard thread pool is plenty.
- Minimal Reactor code; no need to rewrite repositories from JDBC to R2DBC.
- If CPU, DB, or an external service is the true bottleneck, changing the threading model may help little.

**Do not equate platform threads with "bad architecture."** WebFlux and virtual threads are not mandatory for every Spring Boot web runtime.

## 4. MVC with Virtual Threads: Same Blocking Code, Different Execution Threads

A **Java virtual thread** is a `java.lang.Thread` scheduled by the JVM onto carrier platform threads. When a virtual thread performs JVM-supported **blocking I/O**, it can unmount, returning the carrier to other work. This allows the "one logical thread per task/request" model to scale further for I/O-waiting workloads.

Enable in Spring Boot 3.5:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

Key conditions:
1. **Run on JDK 21+**; a Java 17 JVM cannot provide virtual threads even if the property is declared.
2. For Boot-managed **embedded Tomcat/Jetty servlet servers**, Boot 3.5 integrates virtual threads for request processing when the flag is enabled. That is why we can run the **exact same `mvc/target/mvc-1.0.0.jar`** twice—once false, once true.
3. With a virtual-thread executor, platform pool properties such as `spring.task.execution.pool.*` no longer behave the same way. `server.tomcat.threads.max` is also **no longer the concurrency ceiling for the virtual request executor** like a platform pool; backend/network/DB limits must be enforced separately.
4. Virtual threads are **daemon threads**, so apps with only virtual daemon threads could let the JVM exit even with scheduled tasks; `spring.main.keep-alive=true` keeps the JVM alive per Boot guidance when needed.
5. Defining a custom `Executor`/task executor bean can **partially disable Boot's default auto-configuration**; verify the actual executor, `applicationTaskExecutor`, and integrations.
6. Virtual threads do not make every blocking syscall or library "automatically non-blocking." Native/foreign calls, lock contention, thread-local caches, and resource pools still carry costs.

Inside the same MVC controller:

~~~java
public Result task(long ms) {
    // This line is IDENTICAL in both MVC runs:
    DelayReply remote = client.get()
            .uri("/delay?ms={ms}", ms)
            .retrieve()
            .body(DelayReply.class);

    return new Result("mvc", ms, remote.result(),
            Thread.currentThread().isVirtual(),
            Thread.currentThread().getName());
}
~~~

This is a **code fragment**; the full project is in section 8. The exact same blocking RestClient call runs. The difference lies in **Tomcat's thread executor**, not rewriting code into Reactor.

### 4.1. Virtual Threads Differ from Large Thread Pools

A platform thread normally maps 1:1 to an OS thread and OS stack; creating too many increases context switching and memory overhead. A virtual thread has a JVM-managed stack that can park/store frames while waiting and run across carrier pool threads.

**Do not pool virtual threads** like platform threads. To run many concurrent tasks, spawn a virtual thread per task, e.g., `Executors.newVirtualThreadPerTaskExecutor()`. To throttle traffic, do not create a "pool of 50 virtual threads"—use a **Semaphore, rate limiter, DB pool, or connection limits** to protect downstream from overload.

~~~java
private final Semaphore slots = new Semaphore(20);

void callLimitedBackend() throws InterruptedException {
    slots.acquire();
    try {
        // Call downstream with a bounded timeout here.
    } finally {
        slots.release();
    }
}
~~~

Illustrative **fragment**; import `java.util.concurrent.Semaphore`. In real APIs, return 429/503 or use a deadline-bounded queue rather than waiting indefinitely on a semaphore. `HikariCP maximumPoolSize` or max HTTP connections can still become the bottleneck **after** removing the servlet worker thread limit.

### 4.2. Pinned Virtual Threads Depend on JDK Version

**JDK 21–23:** blocking while holding a `synchronized` monitor or inside a native/foreign method can **pin** the carrier thread, hurting scalability if operations are long or frequent. **JDK 24+** includes **JEP 491**, which improves/eliminates Java `synchronized` pinning; native/foreign cases and resource saturation still require monitoring. Do not apply JDK 21 diagnostics blindly to JDK 24+.

Example **anti-pattern on JDK 21**:

~~~java
synchronized (lock) {
    callSlowRemoteApi(); // Can pin the carrier if blocking takes long.
}
~~~

Do not replace every `synchronized` block just because virtual threads exist; profile with JFR first to locate real long-blocking spots, then switch necessary critical sections to an appropriate lock strategy or narrow the scope. On JDK 21:

~~~bash
java -Djdk.tracePinnedThreads=full -jar mvc/target/mvc-1.0.0.jar \
  --spring.threads.virtual.enabled=true \
  --server.port=8082
~~~

This diagnostic property targets **JDK 21–23** and may be removed in newer JDKs. On JDK 24+, use **JFR `jdk.VirtualThreadPinned`** and thread dumps rather than copying old flags across versions.

### 4.3. ThreadLocal Does Not Become Reactor Context

Virtual threads **still support ThreadLocal/MDC** just like platform threads. However, spawning a new virtual thread per task means expensive objects cached in `ThreadLocal` may be allocated **many times**, unlike a small pool of platform threads. MDC must be scoped and cleared properly so sensitive data does not linger. Across `@Async` boundaries, trace/security/request context propagation is still needed where appropriate.

## 5. WebFlux and the Event Loop: Never Hold a Worker Waiting Downstream

Spring WebFlux uses Reactor `Mono/Flux` and typically runs on Reactor Netty. Code:

~~~java
return webClient.get()
        .uri("/delay?ms={ms}", ms)
        .retrieve()
        .bodyToMono(DelayReply.class)
        .map(reply -> new Result(...));
~~~

**No `.block()`**. `WebClient` registers non-blocking network I/O and returns a `Mono<Result>`. Reactor Netty handles socket events; when the downstream response arrives, `map` executes. During the ~300 ms wait, the event-loop thread serves many other connections.

~~~text
reactor-http-nio-* event loop
       ├─ parse request A → subscribe to WebClient A → return
       ├─ parse request B → subscribe to WebClient B → return
       ├─ request C ...
       ├─ backend response B available → map/serialize B
       └─ backend response A available → map/serialize A
~~~

This is a conceptual diagram, not a fixed scheduler sequence. **`Mono` does not mean every request immediately spawns a new thread.** Typically, operators execute on the thread emitting the signal unless altered by `publishOn`/`subscribeOn`/library scheduling.

### 5.1. Absolute Rule: Never Block the Event Loop

Wrong in WebFlux:

~~~java
@GetMapping("/task")
public Mono<String> broken() {
    Thread.sleep(300);              // Blocks request thread!
    return Mono.just("done");
}
~~~

This is an **anti-pattern** (the Java method above would need `InterruptedException` handling to compile; do not copy and run). It stalls the event-loop/handler thread for the delay duration. Equally dangerous:

~~~java
return webClient.get().uri("/delay")
        .retrieve().bodyToMono(String.class)
        .map(text -> jdbcBlockingRepository.load(text)); // Blocking!
~~~

When blocking JDBC/APIs cannot be replaced, offload **locally**:

~~~java
return Mono.fromCallable(() -> blockingRepository.load())
           .subscribeOn(Schedulers.boundedElastic());
~~~

**Illustrative fragment**: requires `reactor.core.publisher.Mono`, `reactor.core.scheduler.Schedulers`, a `blockingRepository` instance, and error handling; it does not turn JDBC into a reactive driver. `boundedElastic` has thread/queue caps, not infinite capacity. `Schedulers.parallel()` is meant for non-blocking/CPU tasks—never push JDBC or `Thread.sleep` onto it.

### 5.2. Reactive Backpressure Is Not a DDoS Shield

Reactor supports **Reactive Streams demand** across Publisher/Subscriber chains. For a single-item HTTP `Mono`, signal-level backpressure means something different than in a multi-million-event `Flux` pipeline. Even with WebFlux, the system still faces:
- Unbounded incoming requests if ingress does not throttle;
- Connection pool max/pending acquire queues;
- Memory pressure from request bodies and pending subscribers;
- Downstream API rate limits;
- Database pools, transactions, and authorization;
- Timeout and retry storms.

Explicitly bound fan-out calls:

~~~java
return Flux.fromIterable(ids)
        .flatMap(id -> webClient.get()
                .uri("/data/{id}", id)
                .retrieve()
                .bodyToMono(Data.class),
                16) // Cap concurrent inner subscriptions.
        .collectList();
~~~

Illustrative fragment needing `Flux`, `webClient`, `ids`, and record `Data`; not part of the lab project. `flatMap(..., 16)` **bounds concurrency within this pipeline**, not total requests across all clients. Under high traffic, global concurrency/rate limits or bounded server resources are still required.

### 5.3. What If Both Web Starters Are Present?

In Spring Boot 3.5, if both `spring-boot-starter-web` and `spring-boot-starter-webflux` are on the classpath, **Spring MVC is chosen by default**, because many MVC apps add WebFlux solely to use outbound `WebClient`. Trying to "switch to WebFlux" by adding the starter while leaving MVC in place can leave the benchmark **still running MVC**.

This lesson uses **two separate Maven modules**:
- `mvc` has only `spring-boot-starter-web`.
- `webflux` has only `spring-boot-starter-webflux`.
- `backend` also uses WebFlux to generate delayed async responses.

Check actual startup logs: MVC uses Tomcat, WebFlux defaults to Netty. Never guess solely from a `Mono` return type on a controller.

## 6. Designing a Fair Experiment

### 6.1. What Stays Constant

| Component | Value in Lab |
| --- | --- |
| JDK | **Same JDK 21** for all three gateways |
| Boot version | **3.5.16** from parent Maven BOM |
| Gateway endpoint | `GET /task?ms=300` |
| Backend | **Same process** `127.0.0.1:8081` |
| Backend contract | `GET /delay?ms=300` → JSON `{"result":"ok","waitMs":300}` |
| Data volume | One small JSON object per request |
| Authentication | None, **localhost-only lab** |
| Timeouts | Should be aligned equally in serious benchmarks |
| Hardware | Same CPU/RAM/JDK/GC limits and background load |
| Client concurrency | Same set of levels: 1, 10, 50, 100, 200... |
| Measurements | Success count, error count, RPS, p50/p95/p99, CPU/threads/memory |

### 6.2. What Intentionally Varies

- MVC platform gateway: bounded Tomcat platform worker pool.
- MVC virtual gateway: same MVC JAR with `spring.threads.virtual.enabled=true`.
- WebFlux gateway: Reactor Netty + non-blocking WebClient.
- Concurrency behavior / scheduler; this is the independent variable under study.

**Caution:** MVC uses blocking `RestClient` while WebFlux uses non-blocking `WebClient`. Thus, the overall comparison evaluates **three execution stacks for the same task**, rather than **isolating virtual thread overhead at the microbenchmark level**. To isolate virtualization effects specifically, comparing **MVC platform vs MVC virtual with identical code/JDK/dependencies** is the strongest controlled pair. MVC vs WebFlux also differs in HTTP client implementation, connection pools, server engine, JSON/filters; state that clearly in conclusions.

## 7. Runnable Maven Multi-Module Project Structure

Create the structure:

~~~text
same-task-lab/
├── pom.xml
├── backend/
│   ├── pom.xml
│   └── src/
│       ├── main/
│       │   ├── java/com/example/backend/
│       │   │   ├── BackendApplication.java
│       │   │   └── DelayController.java
│       │   └── resources/application.properties
│       └── test/java/com/example/backend/
│           └── BackendHttpTest.java
├── mvc/
│   ├── pom.xml
│   └── src/
│       ├── main/
│       │   ├── java/com/example/mvc/
│       │   │   ├── MvcApplication.java
│       │   │   └── MvcGatewayController.java
│       │   └── resources/application.properties
│       └── test/java/com/example/mvc/
│           └── MvcContractTest.java
├── webflux/
│   ├── pom.xml
│   └── src/
│       ├── main/
│       │   ├── java/com/example/webflux/
│       │   │   ├── WebFluxApplication.java
│       │   │   └── FluxGatewayController.java
│       │   └── resources/application.properties
│       └── test/java/com/example/webflux/
│           └── FluxContractTest.java
└── scripts/
    └── load.py
~~~

**Why three Maven modules?** A single executable JAR containing both web starters causes Boot to pick MVC over WebFlux; separating modules clarifies classpaths and lets all run simultaneously for inspection. MVC platform/virtual run **the exact same module/JAR**, differing only in runtime flags. The WebFlux backend is shared by all, rather than giving MVC its own separate backend.

**Lab security configuration:** every server binds to `127.0.0.1`; there is no login, TLS, or circuit breaker, so **never expose to the Internet**. Extreme load tests must cap concurrency/total requests so you do not exhaust your personal machine's resources.

### 7.1. Parent `pom.xml`

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
    <artifactId>same-task-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <modules>
        <module>backend</module>
        <module>mvc</module>
        <module>webflux</module>
    </modules>
    <properties>
        <java.version>21</java.version>
    </properties>
</project>
~~~

`<java.version>21</java.version>` ensures the Java 21 API `Thread.isVirtual()` compiles and all three modules target the same Java runtime. **JDK 17 cannot build this project** because it intentionally uses Java 21 methods; to run MVC platform/WebFlux on Java 17, replace `isVirtual()` and the Maven Java version, and leave virtual threads disabled.

### 7.2. `backend/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>same-task-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>backend</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

The backend module stays identical across all gateways. `spring-boot-starter-webflux` brings in Netty and Reactor; do not add the servlet starter.

### 7.3. `mvc/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>same-task-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>mvc</artifactId>
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

The MVC module uses **RestClient** from Spring Framework 6.2 via `spring-web`. Do not declare Reactor Netty/WebFlux to avoid altering HTTP client selection relative to the baseline.

### 7.4. `webflux/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>same-task-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>webflux</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

When built via the parent Maven POM, the Spring Boot BOM aligns Micrometer, Reactor, Tomcat, and Netty versions. Do not manually pin an unrelated Reactor Netty version or add `spring-boot-starter-web` into the WebFlux module while assuming Netty remains the default server.

## 8. WebFlux Backend: A Shared Delay Source

### 8.1. `backend/src/main/java/com/example/backend/BackendApplication.java`

~~~java
package com.example.backend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BackendApplication {
    public static void main(String[] args) {
        SpringApplication.run(BackendApplication.class, args);
    }
}
~~~

### 8.2. `backend/src/main/java/com/example/backend/DelayController.java`

~~~java
package com.example.backend;

import java.time.Duration;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class DelayController {

    @GetMapping("/delay")
    public Mono<DelayReply> delay(
            @RequestParam(defaultValue = "300") long ms) {

        if (ms < 0 || ms > 3000) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "ms must be 0..3000"));
        }

        return Mono.delay(Duration.ofMillis(ms))
                .map(ignored -> new DelayReply("ok", ms));
    }

    public record DelayReply(String result, long waitMs) {
    }
}
~~~

**Why does the backend use `Mono.delay`?** It emits a signal after the requested duration **without calling `Thread.sleep` on the Netty event loop**. Thus, the backend can serve many delayed responses without dedicating a sleeping platform thread per request. It models time-to-first-response of a slow service so the gateway remains the primary focus of comparison.

**Note:** `Mono.delay` uses a Reactor Scheduler timer, not a real HTTP DB query. This benchmark investigates the overhead and concurrency of **HTTP waiting**, not JDBC/R2DBC performance. Even with `ms=0`, the task goes through asynchronous scheduling, so response time is never literally 0.

### 8.3. `backend/src/main/resources/application.properties`

~~~properties
spring.application.name=lab-backend
server.address=127.0.0.1
server.port=8081
~~~

Backend configuration remains identical regardless of gateway mode. Do not swap the backend implementation between variants, nor run different backends on different ports assuming equivalent functionality means equal resource behavior.

### 8.4. `backend/src/test/java/com/example/backend/BackendHttpTest.java`

~~~java
package com.example.backend;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class BackendHttpTest {

    @LocalServerPort int port;

    @Test
    void delayReturnsExpectedJsonOverRealHttp() {
        String body = RestClient.create().get()
                .uri("http://127.0.0.1:" + port
                     + "/delay?ms=10")
                .retrieve()
                .body(String.class);

        assertTrue(body != null
                && body.contains("\"result\":\"ok\""));
        assertTrue(body.contains("\"waitMs\":10"));
    }

    @Test
    void negativeDelayReturns400() {
        int status = RestClient.create().get()
                .uri("http://127.0.0.1:" + port
                     + "/delay?ms=-1")
                .exchange((request, response) ->
                        response.getStatusCode().value());

        assertEquals(400, status);
    }
}
~~~

This is a **real socket HTTP test** because `RANDOM_PORT` starts a live Netty server. No external backend process is needed to run JUnit; the test context launches its own backend instance. `contains(...)` verifies the minimal JSON contract without relying on field order or unstable timestamps.

## 9. MVC Gateway: One Codebase Running Platform or Virtual

### 9.1. `mvc/src/main/java/com/example/mvc/MvcApplication.java`

~~~java
package com.example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcApplication.class, args);
    }
}
~~~

### 9.2. `mvc/src/main/java/com/example/mvc/MvcGatewayController.java`

~~~java
package com.example.mvc;

import java.util.Objects;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class MvcGatewayController {
    private final RestClient client;

    public MvcGatewayController(
            RestClient.Builder builder,
            @Value("${lab.backend-url:http://127.0.0.1:8081}")
            String backendUrl) {

        // Boot-injected RestClient.Builder preserves customizers/observability.
        this.client = builder.baseUrl(backendUrl).build();
    }

    @GetMapping("/task")
    public TaskResult task(
            @RequestParam(defaultValue = "300") long ms) {

        if (ms < 0 || ms > 3000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "ms must be 0..3000");
        }

        // Blocking HTTP call: current MVC request thread waits for JSON.
        DelayReply remote = Objects.requireNonNull(
                client.get()
                        .uri("/delay?ms={ms}", ms)
                        .retrieve()
                        .body(DelayReply.class),
                "backend returned an empty body");

        Thread handlingThread = Thread.currentThread();

        return new TaskResult(
                "mvc",
                ms,
                remote.result(),
                handlingThread.isVirtual(),
                handlingThread.getName());
    }

    public record DelayReply(String result, long waitMs) {
    }

    public record TaskResult(String mode, long waitMs,
                             String backendResult,
                             boolean virtualThread,
                             String threadName) {
    }
}
~~~

**Crux of the experiment:** **do not write one controller for platform and another for virtual**. The exact same `MvcGatewayController` class, blocking `RestClient` call, and JSON contract are used. Only the runtime flag decides whether Tomcat dispatches requests on virtual threads or platform threads.

`RestClient.Builder` is injected by Spring Boot rather than calling `RestClient.create()` in the runtime app; it retains Boot customizers needed for observability/tracing in real applications. Inside the JUnit test client, `RestClient.create()` is fine since it only needs to send localhost HTTP calls.

**Production note:** default HTTP client connect/read timeouts depend on the underlying request factory/JDK; configure timeouts and max connections/connection pooling explicitly in serious benchmarks. This demo avoids a complex custom client factory to focus on threading; therefore results are **not** a benchmark of optimized client transports.

### 9.3. `mvc/src/main/resources/application.properties`

~~~properties
spring.application.name=lab-mvc
server.address=127.0.0.1
server.port=8080

lab.backend-url=http://127.0.0.1:8081

# Baseline platform mode; virtual instance CLI will override.
spring.threads.virtual.enabled=false

# Use a bounded worker pool to observe platform saturation.
server.tomcat.threads.max=32
~~~

In virtual mode, `server.tomcat.threads.max` **does not mean "allow only 32 virtual request threads."** Tomcat's virtual executor does not operate like that fixed platform worker pool. Connections, downstream capacity, and CPU remain finite; enforce true concurrency caps with separate resource bounds.

### 9.4. `mvc/src/test/java/com/example/mvc/MvcContractTest.java`

~~~java
package com.example.mvc;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class MvcContractTest {

    @LocalServerPort int port;

    @Test
    void invalidDelayIsRejectedBeforeDownstreamCall() {
        int status = RestClient.create().get()
                .uri("http://127.0.0.1:" + port
                     + "/task?ms=5000")
                .exchange((request, response) ->
                        response.getStatusCode().value());

        assertEquals(400, status);
    }
}
~~~

In this test the backend is not started; the request is rejected at the controller because `ms>3000`, so **no outbound RestClient call runs**, keeping the test standalone. Positive functional verification across two processes is tested via `curl` in section 11.

### 9.5. Launching the Two MVC Instances

One application, two independent processes:
- platform `8080`: `spring.threads.virtual.enabled=false`.
- virtual `8082`: `spring.threads.virtual.enabled=true`, JDK 21.

Do not run both variants in the same process by toggling a property per request; the thread factory/executor is created at startup, not switched via query parameter. `mode= "mvc"` stays the same because the application stack is MVC in both cases; **the `virtualThread` field indicates the execution mode inside the controller**.

## 10. WebFlux Gateway: Same Backend Call, Without Blocking the Event Loop

### 10.1. `webflux/src/main/java/com/example/webflux/WebFluxApplication.java`

~~~java
package com.example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxApplication.class, args);
    }
}
~~~

### 10.2. `webflux/src/main/java/com/example/webflux/FluxGatewayController.java`

~~~java
package com.example.webflux;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class FluxGatewayController {
    private final WebClient client;

    public FluxGatewayController(
            WebClient.Builder builder,
            @Value("${lab.backend-url:http://127.0.0.1:8081}")
            String backendUrl) {

        this.client = builder.baseUrl(backendUrl).build();
    }

    @GetMapping("/task")
    public Mono<TaskResult> task(
            @RequestParam(defaultValue = "300") long ms) {

        if (ms < 0 || ms > 3000) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "ms must be 0..3000"));
        }

        // No .block(): event loop does not hold a thread while waiting on network.
        return client.get()
                .uri("/delay?ms={ms}", ms)
                .retrieve()
                .bodyToMono(DelayReply.class)
                .map(remote -> {
                    Thread callbackThread = Thread.currentThread();
                    return new TaskResult(
                            "webflux",
                            ms,
                            remote.result(),
                            callbackThread.isVirtual(),
                            callbackThread.getName());
                })
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.BAD_GATEWAY,
                                "backend returned empty response")));
    }

    public record DelayReply(String result, long waitMs) {
    }

    public record TaskResult(String mode, long waitMs,
                             String backendResult,
                             boolean virtualThread,
                             String threadName) {
    }
}
~~~

**Fair comparison:** both MVC and WebFlux share the exact same path, query param, validation range, backend JSON, and output schema. However, WebFlux's `TaskResult.virtualThread` is captured **inside `map` when the backend signal arrives**, not on a Servlet "request-owner thread." A reactive request can switch threads across operators; do not infer from this single value that the entire request ran on one thread.

**Why not call `subscribe()` manually in the controller?** Spring WebFlux **subscribes** to the `Mono` you return to manage response, errors, and cancellation. Calling `subscribe()` manually and returning early detaches the response lifecycle from the downstream result, causing leaks and swallowed errors. Calling `block()` inside a Netty controller can trigger `IllegalStateException` from Reactor or stall the event loop.

### 10.3. `webflux/src/main/resources/application.properties`

~~~properties
spring.application.name=lab-webflux
server.address=127.0.0.1
server.port=8083

lab.backend-url=http://127.0.0.1:8081
spring.threads.virtual.enabled=false
~~~

Do not put `server.tomcat.threads.max` into WebFlux/Netty expecting it to control Netty: that is a Tomcat setting, irrelevant to Netty's event loop. Use Reactor Netty client/server pool settings if tuning after profiling. Leave virtual threads disabled here to keep the **WebFlux non-blocking baseline** clear.

### 10.4. `webflux/src/test/java/com/example/webflux/FluxContractTest.java`

~~~java
package com.example.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class FluxContractTest {

    @LocalServerPort int port;

    @Test
    void invalidDelayIsRejectedBeforeNetworkRequest() {
        int status = RestClient.create().get()
                .uri("http://127.0.0.1:" + port
                     + "/task?ms=5000")
                .exchange((request, response) ->
                        response.getStatusCode().value());

        assertEquals(400, status);
    }
}
~~~

JUnit sends **real HTTP to Netty on `RANDOM_PORT`**, using invalid input so no backend process is required. This confirms the WebFlux module boots a reactive web server rather than MockMvc. These contract tests do not measure throughput or prove WebFlux is faster; load measurement is handled separately by the script below.

### 10.5. Code Path Comparison Summary

| MVC platform/virtual | WebFlux |
| --- | --- |
| `TaskResult task(long ms)` | `Mono<TaskResult> task(long ms)` |
| `RestClient.get().retrieve().body(...)` | `WebClient.get().retrieve().bodyToMono(...)` |
| Current Servlet request thread waits synchronously | No wait-block on event loop while downstream processes |
| Response built after blocking call returns | Response built inside `map` when signal arrives |
| `throw new ResponseStatusException(...)` | `return Mono.error(new ResponseStatusException(...))` |
| Same path/payload/schema | Same path/payload/schema |
| Run same MVC JAR with virtual false/true | Separate module with reactive starter |

**You do not need** `CompletableFuture`, `@Async`, or a manual thread pool in MVC to get virtual request threading; Boot/Tomcat handles it based on the flag. If you want to fan out multiple downstream calls inside one request, virtual threads + structured concurrency (depending on JDK API support) is a **separate problem**, not required by this lab.

## 11. Building and Running All Four Processes

From `same-task-lab`:

~~~bash
java -version
mvn --version
mvn clean verify
~~~

**Requirement:** both `java -version` and the Java used by Maven must point to **JDK 21+**; `mvn clean verify` compiles all three modules, runs JUnit tests (1 backend class with 2 tests, 1 MVC test, 1 WebFlux test), and packages executable JARs. Only running the commands verifies results; outcomes described below are **expected** from the listed source code.

Four terminals (Linux/macOS Bash; collapse onto one line if using PowerShell):

**Terminal A — backend always runs on port 8081:**

~~~bash
java -jar backend/target/backend-1.0.0.jar
~~~

**Terminal B — MVC platform (8080):**

~~~bash
java -jar mvc/target/mvc-1.0.0.jar \
  --server.port=8080 \
  --spring.threads.virtual.enabled=false
~~~

**Terminal C — same MVC JAR with virtual threads (8082):**

~~~bash
java -jar mvc/target/mvc-1.0.0.jar \
  --server.port=8082 \
  --spring.threads.virtual.enabled=true \
  --spring.main.keep-alive=true
~~~

**Terminal D — WebFlux/Netty (8083):**

~~~bash
java -jar webflux/target/webflux-1.0.0.jar
~~~

Start the **backend first**, verify it is ready, then start the gateways. If a port is busy, locate the owning process with `ss`/`lsof` or override ports and adjust benchmark URLs accordingly. Never randomly kill someone else's process. In Docker, `127.0.0.1` is **container-local loopback**; if each module runs in its own container, set the backend URL to the network hostname, adjust bindings, and protect the network with policies. These commands target a **single host machine**.

### 11.1. Verify the Backend First

~~~bash
curl -i 'http://127.0.0.1:8081/delay?ms=300'
~~~

Expected JSON body (key order independent):

~~~json
{"result":"ok","waitMs":300}
~~~

Expect ~300 ms timer delay plus HTTP/JVM overhead. HTTP headers may vary slightly across Java versions. If the backend does not return 200, **do not** run the benchmark: when the backend fails, gateway RPS and error metrics do not reflect the execution model.

### 11.2. Verify Platform MVC

~~~bash
curl -sS 'http://127.0.0.1:8080/task?ms=300'
~~~

Expected shape (thread name illustrative):

~~~json
{
  "mode": "mvc",
  "waitMs": 300,
  "backendResult": "ok",
  "virtualThread": false,
  "threadName": "http-nio-8080-exec-1"
}
~~~

`virtualThread:false` indicates `Thread.currentThread().isVirtual()` inside the MVC platform handler is false. Thread names and numbering are not fixed, and the JVM may use other threads for internal work.

### 11.3. Verify Virtual MVC

~~~bash
curl -sS 'http://127.0.0.1:8082/task?ms=300'
~~~

Expected shape:

~~~json
{
  "mode": "mvc",
  "waitMs": 300,
  "backendResult": "ok",
  "virtualThread": true,
  "threadName": "tomcat-handler-virtual-example"
}
~~~

**This thread name is illustrative, not a Spring Boot/Tomcat guarantee**. Virtual threads may have blank names or a different naming format depending on the executor. What matters is asserting **`virtualThread:true`**, proving the handler executed on a virtual thread with your Boot/Tomcat/JDK setup. If false, check Java version, property flag, server type, custom Executors, and auto-config rather than trusting a green startup log.

### 11.4. Verify WebFlux

~~~bash
curl -sS 'http://127.0.0.1:8083/task?ms=300'
~~~

Expected shape (thread name illustrative):

~~~json
{
  "mode": "webflux",
  "waitMs": 300,
  "backendResult": "ok",
  "virtualThread": false,
  "threadName": "reactor-http-nio-3"
}
~~~

`virtualThread:false` here reflects **the thread running the `map` operator**, not a claim that WebFlux handles each request on a single platform thread. A reactive request can hop across event loops/callback contexts; adding `publishOn` would change the thread name seen in `map`.

### 11.5. Smoke-Test with jq (Optional)

If `jq` is installed:

~~~bash
for port in 8080 8082 8083; do
  curl -fsS "http://127.0.0.1:$port/task?ms=300" |
    jq '{mode,waitMs,backendResult,virtualThread,threadName}'
done
~~~

**Expected:** all three responses report `waitMs=300` and `backendResult="ok"`, while mode, virtualThread, and threadName differ. `$port` is a Bash shell variable and will not work directly in PowerShell.

### 11.6. Verify Input Validation

~~~bash
curl -i 'http://127.0.0.1:8080/task?ms=-1'
curl -i 'http://127.0.0.1:8082/task?ms=5000'
curl -i 'http://127.0.0.1:8083/task?ms=5000'
curl -i 'http://127.0.0.1:8081/delay?ms=5000'
~~~

Expected **400 Bad Request** across all endpoints. Default error bodies of MVC and WebFlux can **differ**; this lab guarantees the common status for invalid input rather than comparing exact framework error JSON details. A deeper contract would unify error schemas and security filters for stricter cross-stack testing.

## 12. Load-Testing Script Using Python Standard Library

Goal: measure **one gateway at a time** without installing external benchmarking tools. File `scripts/load.py`:

~~~python
#!/usr/bin/env python3
import argparse
import json
import math
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

parser = argparse.ArgumentParser()
parser.add_argument("--base", required=True)
parser.add_argument("--total", type=int, default=300)
parser.add_argument("--concurrency", type=int, default=30)
parser.add_argument("--ms", type=int, default=300)
args = parser.parse_args()

if args.total < 1 or args.concurrency < 1:
    parser.error("--total and --concurrency must be >= 1")
if not 0 <= args.ms <= 3000:
    parser.error("--ms must be between 0 and 3000")

url = args.base.rstrip("/") + "/task?ms=" + str(args.ms)

def send_one(index):
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            data = json.load(response)
            ok = (response.status == 200
                  and data.get("waitMs") == args.ms
                  and data.get("backendResult") == "ok")
            status = response.status
    except urllib.error.HTTPError as exc:
        ok, status = False, exc.code
    except Exception as exc:
        ok, status = False, type(exc).__name__
    elapsed_ms = 1000 * (time.perf_counter() - started)
    return (ok, status, elapsed_ms)

begin = time.perf_counter()
with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
    results = list(executor.map(send_one, range(args.total)))
wall_seconds = time.perf_counter() - begin

latencies = sorted(row[2] for row in results)
success = sum(1 for row in results if row[0])
errors = len(results) - success

def pct(p):
    idx = max(0, math.ceil(p / 100 * len(latencies)) - 1)
    return latencies[idx]

print("url:", url)
print("requests:", len(results))
print("success:", success, "errors:", errors)
print("duration_s:", round(wall_seconds, 3))
print("rps:", round(len(results) / wall_seconds, 2))
print("latency_ms_p50:", round(pct(50), 2))
print("latency_ms_p95:", round(pct(95), 2))
print("latency_ms_p99:", round(pct(99), 2))
print("latency_ms_avg:", round(statistics.mean(latencies), 2))
if errors:
    from collections import Counter
    print("failed_statuses:",
          dict(Counter(str(row[1]) for row in results if not row[0])))
~~~

**Why the script uses `ThreadPoolExecutor` on the load client:** that is the **load generator**, not the gateway execution model. It issues concurrent HTTP requests over real sockets. Do not infer anything about WebFlux or virtual threads from the Python client using threads. Python clients have GIL/socket creation/CPU limits and can become the **benchmark bottleneck**; for production conclusions, use `wrk`, `hey`, `k6`, Gatling, or a calibrated load generator on a separate host.

**Accuracy notes:** `rps` here is `total requests / wall duration`, including errors; when errors occur, always report `success` and `errors` alongside it rather than claiming high RPS with HTTP 500s/timeouts as a "win." `p50/p95/p99` measure client-observed latency including queueing, HTTP transfer, and backend delay—not server processing time alone. `statistics.mean` is informational only; tail percentiles matter far more under load.

### 12.1. Run a Light Baseline First

~~~bash
python3 scripts/load.py --base http://127.0.0.1:8080 \
  --total 60 --concurrency 10 --ms 300

python3 scripts/load.py --base http://127.0.0.1:8082 \
  --total 60 --concurrency 10 --ms 300

python3 scripts/load.py --base http://127.0.0.1:8083 \
  --total 60 --concurrency 10 --ms 300
~~~

Only after seeing **success=60, errors=0** across all three should you ramp up. Small tests rarely expose thread-pool saturation, so differences may be negligible. Never fabricate numbers like "10,000 RPS" without running on real hardware.

### 12.2. Repeatable Load Levels

~~~bash
# Level 1 — low concurrency:
python3 scripts/load.py --base http://127.0.0.1:8080 \
  --total 300 --concurrency 10 --ms 300

# Level 2 — many requests waiting on I/O:
python3 scripts/load.py --base http://127.0.0.1:8082 \
  --total 600 --concurrency 100 --ms 300

# Level 3 — reactive:
python3 scripts/load.py --base http://127.0.0.1:8083 \
  --total 600 --concurrency 100 --ms 300
~~~

The commands above **illustrate syntax** and are **not** a fair controlled benchmark matrix (they vary both concurrency and total). To compare formally, run **all three variants with identical `--total`, `--concurrency`, and `--ms` at each level**, repeat multiple times, and record median/variance. **Never draw winner/loser conclusions from three commands with different loads.**

Recommended matrix:
- `ms=0`: observe baseline overhead with minimal wait.
- `ms=50`: short wait.
- `ms=300`: medium I/O latency.
- `ms=1000`: large tail wait.
- Concurrency `1, 10, 32, 50, 100, 200` depending on machine capacity.
- Run each combination multiple times after warm-up, alternating run order to reduce JVM/JIT/cache bias.

### 12.3. Why Platform MVC May Hit a Ceiling

In platform MVC, `server.tomcat.threads.max=32` forces requests to wait for a worker when 100–200 outbound blocking calls run concurrently. As queueing grows, p95/p99 climb even while backend delay stays fixed at `ms=300`. Virtual MVC can bypass that worker ceiling, only to hit the next limit: **HTTP connection pool**, file descriptors, backend throughput, memory, or CPU. WebFlux can hold very few event-loop threads during waits, yet remains bounded by network/client pools/backpressure. **Never predict exact RPS numbers from code**; measure them.

## 13. Reading Benchmarks Properly: Throughput vs Latency vs Resources

A template table to fill after running your own tests (placeholders only, **not measured results**):

| Model | C | wait(ms) | Success | Errors | RPS | p50/p95/p99 (ms) | CPU (%) | Threads/RSS |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |
| MVC platform | 100 | 300 | measure | measure | measure | measure | measure | measure |
| MVC virtual | 100 | 300 | measure | measure | measure | measure | measure | measure |
| WebFlux | 100 | 300 | measure | measure | measure | measure | measure | measure |

When analyzing:
1. Compare **success RPS** (not total RPS alone).
2. Compare **p95/p99** at the same offered load, not only peak server throughput.
3. Compare **CPU % under the same core limit**; higher RPS that blows the CPU budget is still a trade-off.
4. Compare **RSS, heap, GC pauses**, thread counts, and socket/file descriptors.
5. Check backend p95/CPU/active requests. If the backend saturates, gateway differences get masked.
6. Verify the client load generator is not starved of CPU/sockets or queueing internally.
7. Check against **SLOs**: e.g., p95 < target, error rate below budget, memory within budget.
8. Test **overload recovery** after traffic drops; a model that pushes more requests downstream and triggers timeout storms is not a "winner."
9. Weigh developer complexity, debugger/profiling ergonomics, security/instrumentation, library compatibility, and operations.
10. Repeat on another JDK version before treating JDK 21 pinning as a permanent law.

### 13.1. This Script Does Not Generate Constant-Arrival-Rate Load

`ThreadPoolExecutor(max_workers=C)` maintains at most `C` in-flight tasks. When a request slows down, the Python worker waits before issuing the next request: this is a **closed-loop fixed concurrency** model. It can **hide latency collapse** (coordinated omission) compared to an open-loop arrival rate independent of response time.

To test SLOs under spikes or independent arrivals, use a tool supporting **constant arrival rate/open-loop** load and monitor server queueing. Always state the load model when presenting results—never compare closed-loop RPS directly against open-loop RPS as the same metric.

### 13.2. Does Running All Processes on One Machine Introduce Noise?

Yes. If all four JVMs sit on the same laptop:
- The backend serves all tests, so test **one gateway under load at a time**.
- Idle JVMs still consume resources via GC, JIT, and background tasks.
- OS scheduler, turbo boost, laptop thermal throttling, and CPU topology affect measurements.
- With virtual threads, carrier parallelism depends on available processors and JVM/CPU constraints.
- WebFlux Netty event-loop count also usually defaults from processor count.
- When changing container CPU quotas, always record JVM `availableProcessors` and thread configs.

For rigorous benchmarks, deploy each gateway with identical resource limits on separate hosts/pods, a dedicated stable backend, an independent load generator, proper warm-up, and randomized repeated runs.

## 14. Runtime Observation: Thread Dumps, JFR, and Metrics

### 14.1. Verify the Thread Model Instead of Guessing from Responses

In MVC JSON responses:
- `virtualThread=false` on port 8080;
- `virtualThread=true` on port 8082 with Java 21+ and proper Boot/Tomcat auto-config;
- `threadName` in the response merely illustrates a thread name.

In WebFlux:
- `virtualThread=false` inside `map` is expected;
- event-loop threads commonly have names like `reactor-http-nio-*`, though code should never assert exact names;
- a reactive request is not pinned to one thread for the full 300 ms.

In production, use distributed tracing (HTTP server spans, client spans) rather than putting thread names in public responses. The lab returns thread names for learning; **never expose runtime implementation details or unauthenticated diagnostic endpoints on the Internet**.

### 14.2. JDK 21 Thread Dumps

~~~bash
jcmd <JAVA_PID> Thread.dump_to_file -format=json threads.json
~~~

This is a **template command**; replace `<JAVA_PID>` with the actual process ID. JSON thread dumps are valuable when large numbers of virtual threads make traditional `jstack` output hard to read. Never capture dumps containing stack secrets/SQL/tokens and share them publicly. Inside containers, ensure JDK tools/attach permissions and target the right PID namespace.

### 14.3. Java Flight Recorder

~~~bash
jcmd <JAVA_PID> JFR.start name=compare \
  settings=profile duration=30s filename=compare.jfr
~~~

Records thread activity, CPU samples, allocations, socket I/O, and (on supporting JDKs) `jdk.VirtualThreadPinned`. Account for recorder overhead, file size, security, GC, and sampling configuration. JDK 21 pinning diagnostics differ from JDK 24 JEP 491; record the **exact JDK runtime version** in benchmark notes.

### 14.4. Spring Boot Actuator and Micrometer

You can add `spring-boot-starter-actuator` to each module and export metrics cleanly. Watch:
- `http.server.requests` timers and exception/status tags (meter names vary by Boot/config);
- JVM memory, GC, and threads;
- Tomcat busy/current threads (platform instance);
- Reactor Netty connection pool / pending-acquire / event-loop utilization (when instrumented);
- Outbound HTTP client metrics, timeouts, and retries;
- Process CPU, heap allocation, and off-heap RSS.

Never use `traceId`/`requestId` as high-cardinality metric labels, and never expose `/actuator/metrics` publicly. A ~300 ms request wait in the backend does not automatically mean latency came from gateway thread scheduling.

## 15. Common Pitfalls and How to Self-Check

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| MVC virtual returns `virtualThread=false` | Not JDK 21+, flag disabled, Tomcat not using Boot executor, custom config | Check `java -version`, startup args, thread executor/server |
| `spring.threads.virtual.enabled=true` on Java 17 | Virtual threads unavailable | Use JDK 21+ or stick to MVC platform |
| WebFlux log still shows Tomcat | Both MVC and WebFlux starters on classpath | Split modules, remove servlet starter from reactive app |
| WebFlux returns `Mono` yet RPS is very low | `block()`/`Thread.sleep`/JDBC on event loop | Use non-blocking APIs or offload to `boundedElastic` |
| MVC platform RPS drops at high C | 32 Tomcat workers saturated by blocking | Check busy threads, queues, downstream latency |
| MVC virtual raises RPS then DB times out | JDBC/Hikari pool is the bottleneck | Cap concurrency, tune pool and timeouts |
| WebFlux times out heavily under load | WebClient connection pool or downstream saturated | Tune pool size, pending acquire, backpressure, rate limits |
| Too many virtual threads, heap grows | ThreadLocal objects, request objects, unbounded in-flight | Avoid per-thread caches, enforce admission bounds |
| Virtual JDK 21 shows carrier pinning | Blocking inside `synchronized`/native code | JFR/profile, refactor hot spots, consider JDK 24+ |
| `spring.task.execution.pool.max-size` has no effect | Boot virtual executor is not a platform pool | Use admission/semaphores/resource limits |
| WebFlux `map` reads ThreadLocal missing trace | Reactor context does not propagate ThreadLocal across all operators by default | Enable tracing/context-propagation integration |
| Enabling VT leaves WebFlux event loop on platform threads | WebFlux reactive pipeline does not become VT-per-request | Expected behavior, not a bug |
| `curl` returns 502/500 when backend is off | Gateway cannot reach backend | Start backend first, verify URL |
| Ports 8080/8081/8082/8083 already in use | Multiple instances/collisions | Identify PID or change ports cleanly |
| Python load generator reports slow times | Client CPU/connection creation bottleneck | Use calibrated external load generator |
| p99 spikes at high concurrency | Queueing, GC, backend saturation, pool limits | Break down spans/metrics/profiling |
| CPU 100%, VT is no faster | CPU-bound bottleneck | Optimize CPU/processes; don't expect VT magic |
| Client tests return 400 | Query `ms` outside 0..3000 | Test within bounds; 400 is the contract |
| WebFlux returns empty body with no error | Upstream body emitted no `onNext` | Add `switchIfEmpty` and error contract |
| Stream hits memory pressure | Excessive fan-out, eager buffering | `flatMap` concurrency caps, bounded queues |
| Browser blocks cross-origin calls | CORS/Origin policy missing | Don't disable security recklessly for benchmarks |
| Spring MVC WebClient returns Mono, assumed Netty | MVC takes priority when both starters exist | Verify actual context/server |
| "WebFlux wins" declared after 1 run | JIT/GC/warmup/cache/client noise | Warm up, run multiple trials, track error/SLO budgets |
| Duplicate side effects from overload retries | Missing idempotency | Idempotency-Key / transactional design |
| Java 21 virtual vs Java 25 WebFlux benchmark | JVM version is a confounder | Benchmark on the same JDK runtime |

### 15.1. `block()/blockFirst()` Incident in WebFlux

Calling:

~~~java
String value = someMono.block();
~~~

on Reactor non-blocking threads causes Reactor to throw an error like "block()/blockFirst()/blockLast() are blocking, which is not supported in thread reactor-http-nio..." or severely degrade throughput. **Do not try to fix this by making the event-loop thread count huge.** Return `Mono` or compose asynchronously with `flatMap`/`zip`. If legacy blocking JDBC is unavoidable, isolate only the blocking segment on `Schedulers.boundedElastic()` with limits and timeouts.

### 15.2. `Mono.delay` Semantics Are Not HTTP Deadlines

The backend `Mono.delay(Duration.ofMillis(ms))` only waits before emitting data; it does not simulate:
- TCP slow-start/retransmission;
- database locks or connection pool waits;
- TLS certificate negotiation;
- network bandwidth limits;
- HTTP client read timeouts;
- multi-chunk streaming responses;
- request cancellation or error rates;
- server-side CPU spikes.

For greater realism, replace the backend with an instrumented server featuring network latency injection, error rates, and controlled concurrency, keeping that exact backend across all three gateway variants.

## 16. Advanced Exercises Using the Same Task

### 16.1. Replacing Simulated Delay with a Real API

Enhancements:
1. Backend returns 200 or 503 with controllable probability (deterministic random seed for comparison).
2. Gateway configures matching connect/read/response timeouts and retry policies.
3. Add request ID/`traceparent` propagation and capture HTTP client spans in both MVC and WebFlux.
4. Measure client connection pool saturation (max connections/pending acquire), not just threads.
5. Disconnect clients mid-delay and observe how WebFlux cancellation and MVC blocking call handling differ.
6. Test large JSON payloads/serialization CPU to observe mixed CPU-bound + I/O behavior.
7. Enable TLS on the backend to measure handshake/connection reuse—kept identical across variants.
8. Inject 1% backend 500s to observe retry storms and tail latency.

Verify **service contract**, security, and idempotency before calling any performance results production-ready.

### 16.2. Fan-Out of Two Calls: MVC vs WebFlux

This is a **follow-on exercise**, not a modification to the base code:

**Sequential blocking MVC:**

~~~java
var a = restClient.get().uri("/delay?ms=300")
        .retrieve().body(DelayReply.class);
var b = restClient.get().uri("/delay?ms=300")
        .retrieve().body(DelayReply.class);
return combine(a, b);
~~~

Two sequential calls normally add their latencies. With virtual threads, you can fan out concurrently using `Executors.newVirtualThreadPerTaskExecutor()`/`Future`, while managing lifecycle, cancellation, timeouts, and downstream rate limits. Java 21 structured concurrency is preview-status, so do not depend on it in the lab project.

**Parallel non-blocking WebFlux:**

~~~java
Mono<DelayReply> a = webClient.get()
        .uri("/delay?ms=300")
        .retrieve().bodyToMono(DelayReply.class);
Mono<DelayReply> b = webClient.get()
        .uri("/delay?ms=300")
        .retrieve().bodyToMono(DelayReply.class);

return Mono.zip(a, b)
        .map(tuple -> combine(tuple.getT1(), tuple.getT2()));
~~~

Both snippets are illustrative and assume `restClient`/`webClient`/`DelayReply`/`combine` exist; do not paste directly into runnable source. Keep concurrency caps, since 100 clients × 2 outbound calls generate 200 backend requests. This cleanly separates **call concurrency** from **how an HTTP request is served**.

### 16.3. CPU-Bound Control Experiment

Replace the backend delay with a heavy computation endpoint under a fixed CPU budget and re-run the benchmark. **Qualitative expectation:** adding threads can increase contention/GC without raising CPU capacity, and WebFlux must also avoid long CPU loops stalling the event loop—offload to a bounded CPU executor if needed. Exact percentages depend on payload, cores, and JIT, so do not guess figures beforehand.

### 16.4. JDBC/Hikari Comparison

Replace the backend with a blocking DB query:
- MVC platform: standard JDBC/Hikari; platform threads may wait on the pool.
- MVC virtual: JDBC remains blocking at the API level while virtual threads park more cheaply; Hikari `maximumPoolSize` still caps active connections.
- WebFlux: calling JDBC on the Netty event loop is wrong; use a reactive R2DBC driver or isolate JDBC in `boundedElastic` (with pool and queue bounds).
- DB locking and transactions reshape the workload, so all modes must share identical SQL, indexes, connection pool size, DB host, and fixtures.

Never call JDBC "non-blocking" merely because it was wrapped in `Mono.fromCallable`.

## 17. Practical Selection Guide

| Project / Condition | Option Often Worth Considering | Why |
| --- | --- | --- |
| Traditional Spring MVC + JDBC CRUD API, moderate concurrency | **MVC platform** | Stable, simple, plenty fast when pool and DB are well sized |
| MVC + heavy outbound blocking HTTP/SQL, JDK 21+, needs higher request concurrency | **MVC virtual threads** | Keeps imperative code while lowering waiting overhead on workers |
| End-to-end non-blocking HTTP/R2DBC/streaming, very high connection counts | **WebFlux** | Reactive pipelines, event loops, and backpressure composition |
| Legacy blocking libraries mixed into WebFlux | **Reconsider WebFlux or offload to boundedElastic** | Never block event loops |
| CPU-intensive processing | **Any stack + bounded CPU design** | Optimize CPU cores, queues, and batching first |
| Team unfamiliar with Reactor working with blocking domain code | **MVC virtual/platform** | Avoids compositional, cancellation, and context bugs |
| Server-Sent Events, high-fan-out reactive flows | **WebFlux can fit well** | Non-blocking streaming with Reactor operators |
| Strict memory/thread budget | **Measure all three modes** | Fewer threads does not automatically mean lower RSS |
| Complex TLS/HTTP2/proxy/metrics/security requirements | **Pick the stack with matching tooling** | Simple benchmarks ignore production constraints |

**Evidence-based decisions:** build a representative workload, benchmark realistic concurrency levels, measure p99/errors/CPU/DB pool saturation, and weigh regression and operational complexity. Never rewrite an entire Spring MVC/JPA codebase based on a `Thread.sleep` chart, nor assume virtual threads solve rate limiting and circuit breaking on their own.

### 17.1. Checklist Before Enabling Virtual Threads in Production

- [ ] JDK 21+ (prefer a patched LTS JDK) and a supported Spring Boot version.
- [ ] Confirmed servlet request handlers actually run on virtual threads via instrumentation/`Thread.isVirtual()`.
- [ ] Benchmarked p95/p99/RPS/CPU/heap on the exact same workload as the platform baseline.
- [ ] Audited HTTP connection pools, HikariCP, downstream quotas, and file descriptors.
- [ ] Monitored pinning on JDK 21–23; JDK 24+ has JEP 491, though native cases still need monitoring.
- [ ] Audited ThreadLocal, MDC, security context, and per-thread caches.
- [ ] Enforced admission/rate limits instead of assuming "unlimited virtual threads."
- [ ] Verified timeouts, cancellation, retries, and idempotency.
- [ ] Checked `@Async`/custom executors and scheduler keep-alive properties.
- [ ] Tested graceful shutdown with in-flight requests and resource cleanup.
- [ ] Do not rely on `spring.task.execution.pool.*` to cap virtual threads.

### 17.2. Checklist Before Migrating to WebFlux

- [ ] Controllers genuinely run on **WebFlux**, not MVC with an extra WebFlux dependency.
- [ ] All primary outbound I/O uses non-blocking clients, with zero `block()` on event loops.
- [ ] Database uses an R2DBC driver or bounded blocking offloading with explicit limits.
- [ ] Team knows `map`, `flatMap`, `zip`, `onErrorResume`, `timeout`, and cancellation.
- [ ] Reactor Context / trace / security context propagation managed explicitly rather than assuming ThreadLocal works everywhere.
- [ ] Concurrency/fan-out, connection pools/pending acquires, and body buffering are bounded.
- [ ] `WebFilter`/`SecurityWebFilterChain` tested distinctly from Servlet `Filter`/`SecurityFilterChain`.
- [ ] Integration tests cover real Netty and proxy/streaming paths.
- [ ] Benchmarked under production-like traffic and service times, not just delay microbenchmarks.
- [ ] Team can debug Reactor stack traces and operator assembly issues.

## 18. Self-Check Questions and Answers

1. Why must all three solutions call the same HTTP backend for a valid comparison?
2. What is Spring Boot 3.5's minimum Java version, and what Java version do virtual threads require?
3. In MVC platform, what kind of thread is held by a blocking RestClient call?
4. In MVC virtual, does RestClient automatically become a non-blocking API?
5. When a virtual thread waits on supported I/O, what resource can it release?
6. Why do virtual threads not speed up CPU-bound work on their own?
7. Which property enables virtual threads in Spring Boot 3.5?
8. Why should `spring.main.keep-alive` be considered?
9. In Boot MVC virtual mode, is `server.tomcat.threads.max=32` still a 32-thread cap on virtual threads?
10. Why should virtual threads not be pooled like platform threads?
11. Besides virtual threads, what resources must still be bounded to protect a DB?
12. How does JDK 21–23 `synchronized` pinning differ from JDK 24+?
13. How does WebFlux wait for an HTTP response without holding the event loop?
14. Why does `Mono.just(blockingCall())` fail to make the blocking call non-blocking?
15. What does `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` accomplish?
16. Does `boundedElastic` provide unbounded threads and memory?
17. When both MVC and WebFlux starters are on the classpath in Boot 3.5, which does Boot choose?
18. Why does a WebFlux response thread name not prove the entire request ran on one thread?
19. Why should `.block()` never be placed inside a WebFlux request handler?
20. What does `flatMap(publisher, 16)` limit, and what does it **not** limit?
21. Why is high RPS with HTTP 500 errors a dangerous benchmark conclusion?
22. Why do p95/p99 matter more than mean latency under queueing?
23. Why can raising load-generator concurrency turn the client into the bottleneck?
24. What relationship does Little's Law describe?
25. Does a Python `ThreadPoolExecutor` load client imply the gateway uses platform threads?
26. If MVC virtual achieves higher RPS and DB timeouts spike, where might the bottleneck be?
27. Why does `Mono.delay(300ms)` not fully represent JDBC?
28. Do the three models produce identical default error response bodies?
29. What benefit comes from using Boot-injected `RestClient.Builder` and `WebClient.Builder`?
30. Why does enabling VT on WebFlux not convert the Reactor Netty event loop into virtual-thread-per-request?
31. When comparing MVC platform vs virtual using the same JAR, what is the primary differing variable?
32. When comparing MVC against WebFlux, which library/server differences act as confounders?
33. What is the difference between closed-loop fixed-concurrency and open-loop arrival-rate load?
34. In production, should you choose a stack by highest raw RPS or by p99/SLO/error/resource budgets?
35. If an API retries a POST after overload, why is idempotency required?
36. Why is `@WebMvcTest` insufficient to verify the runtime thread model?
37. Which JVM tools inspect real pinning and virtual thread counts?
38. Should a long CPU-bound WebFlux operator run on the event loop?
39. Does using JDBC in virtual MVC eliminate connection pool limits?
40. If a benchmark with WebFlux or virtual threads counts many errors, does that prove better scalability?

**Key answers:** (1) Isolates task and downstream latency. (2) Boot Java 17, VT Java 21+. (3) Platform servlet worker. (4) No, still a blocking API on a virtual thread. (5) Carrier OS/platform thread. (6) Core count does not increase. (7) `spring.threads.virtual.enabled=true`. (8) Virtual threads are daemon threads. (9) Not a cap on the virtual executor. (10) Spawn per-task; bound downstream with semaphores/pools. (11) Connection pools, rate limiters, quotas. (12) JDK 24/JEP 491 addresses monitor pinning. (13) Event loop continues serving while async network I/O is pending. (14) Blocking already ran before Mono assembly. (15) Offloads blocking off the event loop. (16) No, it has caps. (17) MVC/Servlet. (18) Reactive runs across callbacks/schedulers. (19) Blocks event loop / throws `IllegalStateException`. (20) Caps concurrent inner subscriptions in that pipeline, not global admission. (21) Fast errors inflate fake RPS. (22) Captures tail queueing delays. (23) Python/socket/CPU limits on client. (24) In-flight ≈ throughput × latency. (25) No, that is only the test client. (26) Hikari/downstream saturation. (27) Only a timer wait, no DB/locks. (28) No. (29) Preserves Boot instrumentation/customizers. (30) Reactor event loops remain non-blocking. (31) Flag + request executor. (32) Tomcat vs Netty, RestClient vs WebClient, pools. (33) Completion-driven vs independent arrivals. (34) SLO/error/cost. (35) Side effects may have committed before timeout. (36) MockMvc starts no real HTTP server. (37) JFR, `jcmd` thread dumps. (38) No, offload to a bounded CPU executor. (39) No, DB pool still bounds connections. (40) No.

## 19. Official Documentation

- Spring Boot 3.5 — **Virtual Threads** (`spring.threads.virtual.enabled`, `spring.main.keep-alive`, JDK 21+): https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 — **Task Execution and Scheduling**, MVC async/`applicationTaskExecutor` and executor auto-config: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.5 — **Reactive Web Applications**, WebFlux/Netty, MVC priority when both starters: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Boot 3.5 — **Servlet Web Applications**, Tomcat/MVC: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — **Embedded Web Servers**, different Servlet/Reactive HTTP servers: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 3.5 — **System Requirements**, Boot 3.5.16 Java 17 minimum: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Framework — **Spring WebFlux Concurrency Model and Blocking I/O**: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html
- Project Reactor — **Threading and Schedulers**, boundedElastic/parallel/event-loop caveats: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Oracle Java 21 — **Virtual Threads Developer Guide**, carriers, I/O blocking, semaphore, ThreadLocal: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- OpenJDK — **JEP 444: Virtual Threads**: https://openjdk.org/jeps/444
- OpenJDK — **JEP 491: Synchronize Virtual Threads without Pinning (JDK 24)**: https://openjdk.org/jeps/491
- Spring Boot 3.5.16 release, **End of OSS Support**: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/