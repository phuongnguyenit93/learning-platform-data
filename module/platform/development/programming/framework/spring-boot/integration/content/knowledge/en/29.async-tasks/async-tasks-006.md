# Java 21 Virtual Threads and External Resource Limits

## Context and objectives

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot organizes system integrations through HTTP clients, databases, caches, message brokers, and Spring Integration adapters. What matters is not just calling an API, reading a table, or receiving a message: the system must also manage configuration, data contracts, transactions, errors, deduplication, testing, and end-to-end observability across the integration flow.

A common scenario: Order Service receives 1,000 concurrent requests; each request must call an Inventory API, query PostgreSQL, read Redis, and write to an outbox to emit events. With traditional platform threads, vast numbers of threads sit **waiting on I/O** rather than computing. Java 21 introduces **virtual threads** as a standard feature (JEP 444): enabling a thread-per-task model with substantially lower thread overhead across many I/O-waiting workloads.

However, **virtual threads do not let the Inventory API accept unlimited requests, give HikariCP extra JDBC connections, allow PostgreSQL infinite transactions, or let brokers process infinite messages**. Moving everything onto hundreds of thousands of virtual threads without bounding concurrency simply shifts failures from "out of Java worker threads" to "DB pool exhausted," "HTTP 429," "rising RabbitMQ unacked," OOM, or cascading timeouts.

This lesson belongs to the **Async Tasks** chapter, topic **Java 21 Virtual Threads and External Resource Limits**. Its focus is understanding virtual threads as an **execution threading model**, not a mechanism guaranteeing throughput, transactions, or delivery semantics.

After this lesson, you will be able to:

1. Distinguish Java platform threads, virtual threads, carrier threads, and blocking I/O.
2. Recognize when virtual threads improve throughput/simplicity and when they offer no benefit.
3. Use `Thread.ofVirtual()` and `Executors.newVirtualThreadPerTaskExecutor()` on Java 21.
4. Configure `spring.threads.virtual.enabled=true`, `@Async`, `TaskExecutor`, and `@Scheduled` appropriately in Spring Boot.
5. Identify pinning caused by `synchronized`/native code in Java 21 and diagnostic tools.
6. Bound concurrency for HTTP pools, JDBC/HikariCP, Redis, and broker listeners.
7. Avoid losing transaction/security contexts, early ACKs, and losing in-RAM tasks on process crash.
8. Design semaphores/bulkheads, timeouts, retry budgets, cancellation, idempotency, and outboxes.
9. Test virtual-thread execution, resource saturation, failure windows, and observability.

> **Core thesis:** Virtual threads **scale the number of tasks that can wait on I/O**, yet external resource limits remain. Sound design requires **bounded concurrency, bounded waiting, deadlines, controlled retries, and durability**.

## 1. How do platform threads and virtual threads differ?

### 1.1. Platform threads: relatively expensive OS resources

In traditional Java, `new Thread(...).start()` typically creates a **platform thread** mapped to an operating-system thread. Stacks, schedulers, and context switching carry real costs. When 500 worker threads wait on HTTP responses, hundreds of OS threads sit occupied doing no useful CPU work.

In a thread-pool model:

~~~text
Incoming requests
       |
       v
Executor queue
       |
       v
Fixed platform-thread workers: 32
       |
       +-- wait HTTP 200 ms
       +-- wait JDBC 50 ms
       +-- wait broker confirm 100 ms
       |
       v
Completed requests
~~~

When all 32 threads are waiting, the 33rd task must queue—even if CPU sits idle.

### 1.2. Virtual threads: lightweight JVM-managed threads

A Java 21 virtual thread is a `java.lang.Thread` instance that is not permanently bound 1:1 to an OS thread for its lifetime. The JVM scheduler uses a pool of **carrier platform threads** to execute virtual threads.

When a virtual thread performs a blocking operation **that the JDK supports unmounting for**, the JVM can unmount the virtual thread from its carrier. The freed carrier then runs another virtual thread.

~~~mermaid
flowchart TD
    A["Virtual Thread A"] --> C["Carrier thread 1"]
    B["Virtual Thread B"] --> D["Carrier thread 2"]
    C --> E["HTTP I/O wait: A unmount"]
    D --> F["CPU work: B running"]
    E -. "Carrier can run other virtual thread" .-> G["Virtual Thread C"]
    G --> C
    E --> H["I/O ready: A becomes runnable"]
    H --> I["Mount A on an available carrier"]
~~~

A virtual thread still has identity, stack traces, interruption, and `ThreadLocal` semantics; the main difference lies in **execution scheduling and carrier resources**.

**Do not confuse:** the JVM does not turn every blocking call in every native library into non-blocking I/O. Some operations pin carriers or issue blocking native calls; Java 21 has limitations that require real measurement.

### 1.3. Quick comparison

| Dimension | Platform thread | Virtual thread (Java 21) |
| --- | --- | --- |
| Java unit | `Thread` | `Thread` |
| Dedicated OS thread | Usually one OS thread | Mounted onto a carrier when running |
| Cost of creating many threads | Relatively high | Usually substantially lower |
| JDK-supported I/O wait | Platform thread blocked | Can unmount; carrier runs other work |
| CPU-bound tasks | Consumes CPU cores | Still consumes CPU cores |
| ThreadLocal | Supported | Supported, though many threads raise memory cost |
| Interruption | Supported | Supported |
| Needs remote concurrency limits? | Yes | **Still yes** |
| Auto-transactions across systems? | No | **No** |
| Replaces message broker/durable queue? | No | **No** |

Virtual threads suit many **blocking I/O tasks**, not as a trick to run CPU computations faster than available cores.

## 2. Virtual threads are thread-per-task, not a classic thread pool

A JDK 21 usage example:

~~~java
import java.util.concurrent.Executors;

public class VirtualThreadDemo {

    public static void main(String[] args) throws Exception {
        try (var executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            var future = executor.submit(() -> {
                System.out.println(
                        "virtual=" +
                        Thread.currentThread().isVirtual());

                Thread.sleep(200);
                return "Inventory loaded";
            });

            System.out.println(future.get());
        }
    }
}
~~~

`Executors.newVirtualThreadPerTaskExecutor()` spawns a **new virtual thread for every submitted task**. It is not a fixed pool of 10 or 100 threads, though the JVM uses an internal set of carrier threads.

- `Thread.sleep(...)` on a virtual thread normally unmounts, avoiding occupying a carrier while sleeping.
- `Future.get()` waits for the result and blocks the calling thread; if the caller is a virtual thread, waiting can also be cheaper in OS threads.
- `try-with-resources` closes the `ExecutorService`; executor `close()` waits for submitted tasks to finish, so beware tasks that never complete.
- If a task throws an exception, `Future.get()` throws `ExecutionException`; never equate successful submission with business success.

### 2.1. `Thread.ofVirtual()`

~~~java
Thread worker = Thread.ofVirtual()
        .name("inventory-lookup-", 0)
        .start(() -> {
            // Blocking I/O call or task logic.
            loadInventory();
        });

worker.join();
~~~

`Thread.ofVirtual()` fits small tasks or lifecycle experiments. With Spring Boot, prefer Spring-managed `TaskExecutor`/integration components rather than spawning ad-hoc threads across controllers and services.

### 2.2. Why not pool virtual threads?

Virtual threads are designed to be cheap enough to **create per task**. Using a fixed pool of virtual threads merely to "reuse threads" is usually unnecessary and can throttle concurrency in the wrong place.

If you need to cap **tasks calling Inventory**, enforce it with a **semaphore, bulkhead, rate limiter, or bounded executor admission**, because that cap reflects Inventory API capacity, not the cost of creating virtual threads.

### 2.3. Virtual threads do not add CPU cores

~~~text
100 CPU-heavy tasks
  -> 8 CPU cores
  -> virtual threads still contend for 8 cores
~~~

For CPU-bound workloads like bulk encryption, compression, image processing, or huge JSON validation, a pool sized near CPU core count usually makes more sense. Spawning 100,000 CPU-heavy virtual threads only increases scheduling/heap overhead and latency.

## 3. Spring Boot and version requirements

Spring Boot 3.2+ on Java 21 supports virtual threads via configuration:

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
~~~

With **compatible Boot/Spring Framework versions and auto-configurations**, this property can switch several Spring-managed execution paths—such as task execution/scheduling and supported servlet web container request handling—to virtual threads.

It **does not mean** every thread in the JVM is virtual:

- WebFlux's Netty event loop still follows the event-loop model.
- Kafka consumer `poll()` threads do not turn into virtual threads just because of this property.
- RabbitMQ connection/client threads and listener container strategies must be checked against your Spring AMQP version.
- JDBC drivers, native Redis clients, and HTTP transport threads have their own lifecycles.
- An application-defined `ThreadPoolTaskExecutor` still runs per its own bean config.
- Third-party SDKs creating their own platform threads do not switch to virtual threads.

### 3.1. Configuration example

~~~yaml
spring:
  threads:
    virtual:
      enabled: true

  main:
    keep-alive: true
~~~

`spring.main.keep-alive=true` helps applications running **only scheduled/background tasks** without other non-daemon threads keeping the JVM alive: virtual threads are **daemon threads** and do not keep the process running by themselves. If a web server or other lifecycle already keeps the process alive, evaluate whether you need it instead of enabling it blindly.

### 3.2. Check which properties still apply

When Boot uses a virtual-thread-oriented task executor instead of a traditional thread pool, several `spring.task.execution.pool.*` options (`core-size`, `max-size`, `queue-capacity`...) may **no longer govern resources as before**. Never copy "pool size=200" from a platform-thread config assuming it caps virtual threads.

When you need to bound work, declare a named executor/bean with an explicit concurrency policy or apply bulkheads at HTTP/DB adapters; verify which bean Spring injects and check `isVirtual() == true` at runtime.

## 4. `@Async` does not automatically mean virtual threads

`@Async` in Spring routes method calls through a configured `Executor`. Whether it runs on virtual or platform threads depends on **the actual executor**, not the annotation itself.

### 4.1. Enabling `@Async`

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfiguration {
}
~~~

In Spring Boot, `@EnableAsync` must be enabled in configuration to activate annotation interception (unless another configuration already enables it). Never confuse having `@Async` on a method with having an active proxy and executor.

### 4.2. Named `SimpleAsyncTaskExecutor` using virtual threads

~~~java
// AsyncIntegrationConfiguration.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.core.task.SimpleAsyncTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class AsyncIntegrationConfiguration {

    @Bean("inventoryTaskExecutor")
    AsyncTaskExecutor inventoryTaskExecutor() {
        var executor =
                new SimpleAsyncTaskExecutor("inventory-vt-");

        executor.setVirtualThreads(true);
        executor.setConcurrencyLimit(24);
        return executor;
    }
}
~~~

`SimpleAsyncTaskExecutor.setVirtualThreads(true)` is available in Spring Framework versions supporting virtual threads (Spring 6.1+). It does not reuse a fixed virtual-thread pool: each task gets a fresh thread, while `setConcurrencyLimit(24)` caps concurrent tasks via the executor's throttle.

**Note:** `setConcurrencyLimit` is not a bounded queue with rejection semantics. Once the limit is hit, callers may block waiting depending on implementation/version behavior. Measure request latency and enforce submission wait timeouts or rejections at the proper layer; for latency-sensitive APIs, consider a `tryAcquire(timeout)` bulkhead to fail fast.

### 4.3. `@Async` returning `CompletableFuture`

~~~java
// InventoryLookupService.java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class InventoryLookupService {

    private final InventoryGateway gateway;

    public InventoryLookupService(InventoryGateway gateway) {
        this.gateway = gateway;
    }

    @Async("inventoryTaskExecutor")
    public CompletableFuture<InventoryRecord> load(String sku) {
        InventoryRecord result = gateway.getStock(sku);

        return CompletableFuture.completedFuture(result);
    }
}
~~~

`InventoryGateway` and `InventoryRecord` are application-defined domain ports/DTOs. Here `gateway.getStock(...)` is a **blocking HTTP call** on a virtual thread. The `@Async` proxy returns a future to the caller; the method body still executes synchronously **inside the executor's thread**.

If the method body throws an exception, the future should represent the failure; never return `completedFuture(null)` to mask an HTTP timeout.

### 4.4. `@Async` proxies and self-invocation

~~~java
@Service
public class OrderService {

    public void process() {
        runAsync(); // Self-invocation: bypasses @Async proxy.
    }

    @Async("inventoryTaskExecutor")
    public void runAsync() {
        // May run synchronously on the caller thread!
    }
}
~~~

In default proxy-based Spring AOP, calling `this.runAsync()` inside the same bean **bypasses the proxy**. As a result, the method may still execute on the platform HTTP request thread with no async boundary.

**Fix:** move the async method to another Spring bean, inject that bean, and call through the proxy; or orchestrate explicitly with `AsyncTaskExecutor`.

### 4.5. Why return a Future instead of `void`?

With `@Async void`, callers receive no exception through a future; you need a dedicated `AsyncUncaughtExceptionHandler` and metrics. With `CompletableFuture<T>`, callers can handle failures, combine tasks, and enforce timeouts/deadlines. Still, a completed future alone never proves a remote business operation did not execute twice.

## 5. `@Scheduled` and virtual threads

With Spring Framework 6.1+ and supporting Boot versions, enabling virtual threads can make Spring use `SimpleAsyncTaskScheduler` instead of `ThreadPoolTaskScheduler` for scheduled tasks.

~~~java
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class OutboxScheduler {

    private final OutboxRelay relay;

    public OutboxScheduler(OutboxRelay relay) {
        this.relay = relay;
    }

    @Scheduled(fixedDelayString =
            "${app.outbox.interval-ms:1000}")
    public void poll() {
        relay.publishDueEvents();
    }
}
~~~

To activate `@Scheduled`, the application needs `@EnableScheduling` in configuration. `OutboxRelay` is an application-defined service.

### 5.1. Fixed delay vs. fixed rate

- `fixedDelay`: the next execution starts after a delay measured from **when the previous execution finished**.
- `fixedRate`: triggers on a periodic schedule; slow tasks can behave differently depending on scheduler/concurrency.
- Cron: calendar-based; must account for time zones, clocks, and daylight saving time.

With `SimpleAsyncTaskScheduler`, **fixed-delay tasks run on a single scheduler thread** per Spring 6.1 semantics. Keep this caveat in mind: virtual threads do not automatically make every fixed-delay job run concurrently on virtual threads. For fixed-rate or cron tasks, the scheduler can spawn separate worker threads per execution.

### 5.2. Never increase job concurrency on a hunch

An outbox relay must claim rows/leases durably so multiple pods do not accidentally publish duplicates; `@Scheduled` and virtual threads do not provide a distributed lock. With Quartz, clustered scheduling coordination also depends on persistent job store/cluster settings, independent of whether jobs run on virtual threads.

### 5.3. The JVM can exit when only daemon virtual threads remain

Java virtual threads are daemon threads. A batch program with only virtual-thread scheduled activity can exit if no non-daemon threads remain. In job-only Spring Boot apps, configure keep-alive, lifecycle, and shutdown properly so the process stays up as required.

## 6. What do virtual threads improve in blocking I/O?

Suppose an Inventory lookup waits 250 ms while payload CPU work takes just 5 ms. With 32 platform worker threads, most worker time is spent waiting on the network. Virtual threads allow many more concurrent waiting requests without hundreds of OS threads.

An estimate via **Little's Law**:

\[
L = \lambda \times W
\]

Where:

- \(L\): average concurrent in-flight operations.
- \(\lambda\): average throughput, e.g., 300 requests/second.
- \(W\): average operation duration, e.g., 0.15 seconds.

Then \(L \approx 300 \times 0.15 = 45\) average concurrent waiting/active operations. If the service's DB pool has only 12 connections and each request holds a JDBC connection for most of those 150 ms, Java thread count is no longer the bottleneck.

### 6.1. Virtual threads remove one bottleneck, not downstream ones

~~~mermaid
flowchart TD
    A["10,000 virtual threads"] --> B["HTTP connection pool: 32"]
    B --> C["Inventory API: max 100 req/s"]
    A --> D["HikariCP: 12 JDBC connections"]
    D --> E["PostgreSQL: locks + SQL execution"]
    A --> F["Redis client / broker channels"]
    F --> G["Redis or RabbitMQ capacity"]
    C --> H["429 / 503 / rising latency"]
    E --> I["pool wait / timeouts"]
    G --> J["backlog / unacked"]
~~~

**Expanding concurrency inside the JVM can hit external systems with sudden traffic spikes.** Enforce explicit limits per downstream.

### 6.2. Why not simply increase max connections?

If the Inventory API handles only 100 req/s, raising the HTTP pool from 32 to 500 floods it with concurrent requests and triggers 429/503 responses. If PostgreSQL tolerates only 80 connections system-wide, setting Hikari max to 100 on each pod overloads the DB instead of raising throughput.

### 6.3. Cheap threads do not mean cheap operations

Every virtual thread still allocates stack frames, Java objects, contexts, headers, payloads, and buffers. 100,000 concurrent virtual threads each holding several KB or MB can trigger GC pressure or OOM. Memory cost is never zero; only thread scheduling/stack management scales better than platform threads while waiting.

## 7. JDBC and HikariCP: connection-limit example

A `@Transactional` method using Spring Data JDBC/JPA normally needs a JDBC connection from `DataSource`/HikariCP. Using virtual threads **does not change connection counts**.

~~~yaml
spring:
  datasource:
    url: ${DB_URL:jdbc:postgresql://db.internal:5432/orders}
    username: ${DB_USER}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: order-db
      maximum-pool-size: 12
      connection-timeout: 2000
      max-lifetime: 1800000
~~~

In this example, the pool allows up to 12 JDBC connections **per application instance** per configuration. With 8 pods running, total potential connections reach ~96 before counting admin tools, jobs, or other services.

### 7.1. Virtual threads waiting on Hikari without a JDBC connection

~~~text
200 virtual threads call repository.findById()
    |
    +-- 12 threads borrow JDBC connections
    |
    +-- 188 threads wait for a pool slot
               |
               +-- 2s timeout → SQLException/DataAccessException
~~~

Virtual threads let waiting for a pool slot consume fewer OS threads. Yet **DB throughput does not rise**; excessive waiting still consumes heap, inflates request time, and times out clients.

### 7.2. Holding a transaction connection across an HTTP call is an anti-pattern

~~~java
@Transactional
public void confirmOrder(Long id) {
    OrderEntity order = orders.findById(id).orElseThrow();
    order.confirm();

    // Even on a virtual thread, the JDBC transaction remains open.
    inventoryGateway.reserve(order.getExternalId());
}
~~~

When partner HTTP takes 10 seconds, the SQL transaction, connection, and locks stay held for the whole wait. Replacing a platform thread with a virtual thread **does not free the JDBC connection** held by the transaction.

Better design:

1. In a short local SQL transaction: update the order and insert an outbox intent.
2. Commit the transaction and release the JDBC connection.
3. Have an outbox relay call Inventory/Kafka outside any SQL transaction.
4. Persist outcomes/attempts in short SQL transactions.
5. Use idempotency/reconciliation when a partner times out after processing.

### 7.3. Transaction context does not automatically cross thread boundaries

Standard Spring transactions use thread-bound contexts. Example:

~~~java
@Transactional
public void placeOrder(PlaceOrder command) {
    orders.save(command.toEntity());
    asyncNotifier.notifyInventory(command.orderId());
}
~~~

If `asyncNotifier.notifyInventory(...)` runs on another thread, it **does not join `placeOrder`'s JDBC transaction** just because the caller is `@Transactional`. The async task may miss uncommitted data or execute even if the caller's transaction rolls back.

**Rule:** never place `@Async` in the middle of steps meant to be atomic under a single local transaction. Persist a durable outbox inside the transaction, then process outside it.

## 8. HTTP clients: connection pools, quotas, and backpressure

`RestClient` is a blocking HTTP API; virtual threads let many callers wait for responses without tying up many OS threads. Yet HTTP transport still enforces:

- Global and per-route connection pool limits.
- Connection acquisition timeouts.
- TCP connect and TLS handshake timeouts.
- Response/read timeouts.
- Server-side rate limits, concurrency caps, and circuit breakers.
- Maximum payload/body sizes and buffering.
- Connection idle/max lifetimes and proxy behavior.

### 8.1. `RestClient` is an API, not a pool

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class InventoryHttpConfiguration {

    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("https://inventory.example.org")
                .build();
    }
}
~~~

The underlying `ClientHttpRequestFactory`/HTTP client governs connection reuse. Never assume calling `RestClient.builder()` automatically picks production pool sizes or timeouts. When using Apache HttpClient 5, JDK HttpClient, or another transport, explicitly configure the request factory and connection manager.

### 8.2. Semaphore bulkhead: capping Inventory calls

A mechanism independent of platform vs. virtual threads:

~~~java
// InventoryGateway.java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class InventoryGateway {

    private final RestClient client;
    private final Semaphore permits = new Semaphore(24);

    public InventoryGateway(
            @Qualifier("inventoryRestClient") RestClient client) {
        this.client = client;
    }

    public InventoryRecord getStock(String sku) {
        boolean acquired;
        try {
            acquired = permits.tryAcquire(
                    200, TimeUnit.MILLISECONDS);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Inventory lookup interrupted", ex);
        }

        if (!acquired) {
            throw new DownstreamBusyException(
                    "Inventory concurrency budget exhausted");
        }

        try {
            return client.get()
                    .uri("/v1/stock/{sku}", sku)
                    .retrieve()
                    .body(InventoryRecord.class);
        } finally {
            permits.release();
        }
    }
}
~~~

`InventoryRecord` and `DownstreamBusyException` are application DTO/exception types to define. `permits` is a per-instance singleton (the `InventoryGateway` bean), capping Inventory lookups at roughly 24 in-flight calls per pod.

Key points:

- This cap protects the **external downstream**, not "total virtual threads in the JVM."
- `tryAcquire(timeout)` ensures callers never block forever waiting to enter the bulkhead.
- `finally` releases the permit even on HTTP timeouts or exceptions.
- With 8 pods, total in-flight calls can reach 8 × 24 = 192; calculate your distributed budget.
- A semaphore is not a rate limiter: 24 concurrent calls taking 10 ms each can still generate high QPS.
- Avoid holding a JDBC transaction while acquiring or holding an HTTP permit whenever possible.

### 8.3. Rate limits vs. concurrency limits

| Tool | Controls | Example |
| --- | --- | --- |
| Semaphore/bulkhead | In-flight operations | Max 24 Inventory calls per pod |
| Rate limiter | Requests per time window | Max 100 calls/second |
| HTTP connection pool | Sockets/HTTP connections | 32 connections per route |
| Circuit breaker | Pauses calls when upstream fails | Opens when error rate exceeds threshold |
| Timeout | Max duration per phase | Pool wait 200 ms; response 2 s |
| Retry budget | Total attempts/backoff | Max 2 attempts within deadline |

Resilient systems usually **combine** these controls rather than relying on a single one.

### 8.4. Do not cap all virtual threads to HTTP socket counts

One task might wait on the database, another on HTTP, and another on payload serialization. Capping all app virtual threads at 24 just because the HTTP pool is 24 starves unrelated tasks. Place bulkheads at the exact **resource boundary** of Inventory HTTP, alongside separate bounds for DB, brokers, and memory.

## 9. WebClient, Reactor Netty, and virtual threads

`WebClient` is a reactive API typically running on Reactor Netty event loops. Virtual threads and reactive programming solve overlapping problems (avoiding tying up OS threads during I/O waits), yet they are **two distinct execution models**.

| Case | Recommendation |
| --- | --- |
| Spring MVC + blocking `RestClient` | Virtual threads can help if I/O-bound |
| Spring WebFlux + reactive `WebClient` chain | Keep the pipeline non-blocking; never block Netty event loops |
| Library exposing only blocking JDBC API | Virtual threads reduce OS-thread blocking overhead; DB pool remains the limit |
| CPU-bound transform in Reactor | Appropriate scheduler/bounded worker pool; virtual threads add no CPU |
| Calling `WebClient.block()` on an event loop | Anti-pattern; can cause errors or stalls |
| Calling a blocking SDK on a virtual thread off the event loop | Can make sense if SDK is compatible; measure pinning and resources |

### 9.1. Never call `.block()` on a Netty event loop

~~~java
// Anti-pattern if invoked on a Reactor Netty event loop:
InventoryRecord record = webClient.get()
        .uri("/v1/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(InventoryRecord.class)
        .block();
~~~

Enabling `spring.threads.virtual.enabled=true` **does not turn event-loop threads into virtual threads**. In reactive chains, use `flatMap`, operator timeouts, bounded concurrency, and non-blocking DB/HTTP adapters; if blocking code must run, offload it deliberately away from the event loop.

### 9.2. Do not mix models just because something sounds faster

You can use `WebClient` inside MVC apps or `RestClient` on virtual threads. Choose based on system complexity, libraries, observability, and measured throughput. Virtual threads often keep imperative I/O-bound code simpler; reactive excels at compositional backpressure and streams when the team masters scheduler and operator semantics.

## 10. Redis and caches do not become infinite

Spring Data Redis commonly uses `RedisTemplate`/`StringRedisTemplate`, `LettuceConnectionFactory`, and a Redis client. Lettuce runs its own event-loop/network I/O; synchronous Redis calls block the caller.

Virtual threads can make waiting on Redis commands cheaper in OS threads, yet:

- The Redis server and network still have finite capacity and throughput.
- Expensive Redis commands can block the Redis server or client event loop.
- Shared native connections, transactional pipelines, and blocking commands have specific lifecycles.
- Cache stampedes can send thousands of virtual threads to the database on a cache miss.
- Timeout, circuit-breaker, and fallback policies remain essential.
- Redis writes are not automatically atomic with PostgreSQL transactions.

### 10.1. Cache stampedes when concurrency opens up

~~~text
Cache key expires
  -> 5,000 virtual threads read MISS
  -> all call PostgreSQL at once
  -> Hikari pool max 12
  -> huge wait, timeouts, 5xx
~~~

Mitigations include per-key single-flight, jittered TTLs, stale-while-revalidate, bounded DB concurrency, or workload-driven cache warming. Virtual threads do not replace **request coalescing** or **rate limiting**.

### 10.2. ThreadLocal with Redis transactions?

`RedisTemplate` has its own transaction/pipelining semantics and connection lifecycles. Never arbitrarily share a stateful `RedisConnection` across virtual threads. Use framework-managed templates/factories and test transactions, serialization, and timeouts against your real Redis topology.

## 11. Kafka, RabbitMQ, and consumer limits

Virtual threads **do not alter message broker delivery semantics**.

### 11.1. `KafkaConsumer` is not thread-safe

`KafkaConsumer` manages consumer-group membership, the `poll()` loop, partition assignments, and offset commits. Never let 1,000 virtual threads call `poll()` on **the same `KafkaConsumer`**. In Spring Kafka, listener containers manage consumer instances per concurrency setting; partition count in a group bounds useful parallelism.

~~~text
@KafkaListener container
    -> KafkaConsumer poll()
    -> onMessage(record)
    -> DB transaction commit
    -> offset acknowledgement/commit
~~~

### 11.2. Trap: offloading a Kafka record and ACKing early

~~~java
@KafkaListener(topics = "orders.events")
public void unsafeConsume(OrderEvent event) {
    virtualExecutor.submit(() -> processOrder(event));
    // Listener returns; container may advance/commit progress
    // before the async task finishes, depending on ack mode.
}
~~~

This is an **anti-pattern** when at-least-once business processing is required. Partition ordering and offsets do not automatically track detached `Future`s. To parallelize within a partition, you need careful contiguous-offset completion tracking, ordering/idempotency logic, or a durable work queue/inbox.

### 11.3. RabbitMQ remains bounded by prefetch and channels

A `@RabbitListener` relies on container-managed consumers, prefetch, channel ACKs, and retry policies.

- Virtual threads do not automatically raise RabbitMQ queue throughput.
- Returning early from a listener after `executor.submit(...)` lets `AcknowledgeMode.AUTO` ACK the message before the task finishes.
- `AcknowledgeMode.MANUAL` requires ACKing on the proper channel/delivery tag after the business commit.
- Prefetch × consumers × replicas determines in-flight deliveries.
- Dead-letter/requeue behavior does not change just because threads are virtual.

For async handoff, **persist a durable inbox/work item** before ACKing the source, or use official async listener return semantics supported by your Spring AMQP version and test ACK timing.

### 11.4. Broker acknowledgments are not business commits

A successful Kafka producer future or RabbitMQ publisher confirm ACK proves only broker acceptance per policy. Consumer ACK/offset commits record consume progress only. SQL business state and downstream HTTP side effects must be verified separately.

## 12. Spring Integration: `ExecutorChannel` and thread boundaries

Spring Integration provides `DirectChannel`, `ExecutorChannel`, pollers, gateways, and adapters. Using asynchronous channels switches threads, changing transaction, security, and error contexts.

~~~mermaid
flowchart TD
    A["HTTP inbound gateway"] --> B["DirectChannel"]
    B --> C["Validate and persist durable intent"]
    C --> D["ExecutorChannel / async handoff"]
    D --> E["Virtual-thread TaskExecutor"]
    E --> F["HTTP/DB/broker adapter"]
    F --> G["Error channel / result"]
~~~

**Never confuse `ExecutorChannel` with a durable message broker.** An `ExecutorChannel` normally dispatches in **JVM memory**; if the process crashes after accepting a request before the task executes, work can be lost. Virtual threads only change execution threads—not durability.

### 12.1. Transactions do not cross channels automatically

With `DirectChannel`, downstream handlers can execute on the caller's thread. With `ExecutorChannel`, downstream handlers run on another thread; a caller's thread-bound Spring transaction **does not transfer** there.

If a flow requires atomically "write order and record outgoing event intent," execute both in the same SQL transaction **before** switching async, then process and retry from a durable outbox.

### 12.2. Error channels and async failures

Exceptions in background handlers may not return to the HTTP caller synchronously. Return an honest "accepted for processing" status, persist status to the database, configure `errorChannel` and error handlers, and track failures/parking queues separately. Never report "completed" merely because a task was submitted.

## 13. Virtual thread pinning in Java 21

A virtual thread normally **unmounts** when waiting on JDK-supported I/O. On Java 21, however, certain situations **pin** a virtual thread to its carrier while blocking. Two key sources:

1. Performing a blocking operation while inside a `synchronized` method or block.
2. Certain native/foreign function calls or runtime operations that cannot unmount.

**Pinning is not inherently wrong** if the critical section is tiny. It becomes a problem when a virtual thread **blocks for a long time while pinned**, preventing the carrier from running other virtual threads.

### 13.1. Example prone to pinning on Java 21

~~~java
public class UnsafeCatalogClient {

    private final CatalogGateway gateway;

    public UnsafeCatalogClient(CatalogGateway gateway) {
        this.gateway = gateway;
    }

    public synchronized CatalogDto load(String sku) {
        // Blocking HTTP inside a synchronized method:
        // Java 21 virtual thread may pin the carrier.
        return gateway.fetch(sku);
    }
}
~~~

With 100 virtual threads, this method also serializes every request on the monitor lock, on top of pinning during I/O waits. Separate the critical section protecting in-memory state from the network call:

~~~java
public class SaferCatalogClient {

    private final CatalogGateway gateway;
    private long attempts;

    public SaferCatalogClient(CatalogGateway gateway) {
        this.gateway = gateway;
    }

    public CatalogDto load(String sku) {
        synchronized (this) {
            attempts++;
        }

        // Do not hold the monitor while performing blocking I/O.
        return gateway.fetch(sku);
    }
}
~~~

For broader state synchronization, use appropriate concurrency primitives, keep critical sections short, and never hold locks across remote calls. Replacing `synchronized` with `ReentrantLock` can eliminate monitor pinning in Java 21, **yet lock contention and lock-held latency remain**; never wrap network I/O in locks.

### 13.2. Pinning is not pool starvation

| Phenomenon | Cause | Signal |
| --- | --- | --- |
| **Carrier pinning** | Virtual thread blocks when unable to unmount | JFR `jdk.VirtualThreadPinned`, pinned stack traces |
| **JDBC pool starvation** | Too many tasks waiting to borrow JDBC connections | Hikari active near max, rising pending |
| **HTTP pool starvation** | Waiting for HTTP connection slots | Pool leased/max, pending acquisitions |
| **CPU saturation** | Threads running computation | CPU near max, runnable work rising |
| **Partner overload** | Downstream rate/concurrency limits | 429/503, rising latency |
| **Lock contention** | Threads waiting on `synchronized`/`ReentrantLock` | Lock wait/blocked stacks |

An application with **zero carrier pinning** can still fail if 50,000 virtual threads stall waiting on a Hikari pool. Never prioritize micro-optimizing pinning when database capacity is the true bottleneck.

### 13.3. Tools to detect pinning

On Java 21, you can use JVM diagnostics:

~~~text
-Djdk.tracePinnedThreads=full
~~~

or:

~~~text
-Djdk.tracePinnedThreads=short
~~~

These options print stack traces when virtual threads pin in JDK-instrumented cases; use them in test/staging or controlled diagnostics, as they add noise and overhead. Java Flight Recorder emits the **`jdk.VirtualThreadPinned`** event to locate notable blocking stacks; configure event thresholds and JFR tools for your JDK release.

**Version caveat:** Java 24 and newer introduce changes around monitor pinning (JEP 491), so the assumption "every `synchronized` + blocking pins" is specifically tied to **Java 21**; re-measure whenever upgrading the JDK. Native/foreign calls and other blocking mechanisms still require attention.

## 14. ThreadLocal, MDC, and security context

Virtual threads support `ThreadLocal` just like platform threads. Yet because virtual threads can be created in huge numbers, patterns designed around small pools can become expensive or semantically broken:

- Using `ThreadLocal` as a per-thread cache holding large objects.
- Storing JDBC `Connection`/JPA `EntityManager`/Redis transaction state in custom homegrown `ThreadLocal`s.
- Relying on `InheritableThreadLocal` to carry credentials across multiple async boundaries.
- Expecting SLF4J MDC/trace contexts to copy automatically when `@Async` spawns another thread.
- Using thread names/IDs as business identifiers or distributed locks.

### 14.1. Transaction context remains thread-bound

`@Transactional` with Spring JDBC/JPA uses thread-local resource bindings. Switching onto a virtual thread puts you on **another thread**. Spring does not automatically move the caller's transaction onto an `@Async` task.

A `@Transactional` annotation placed directly on a method running inside a virtual thread can **open a local transaction on that thread**; it does not mean it joined the caller's transaction.

### 14.2. MDC and trace context across `@Async`

If caller logs hold `traceId`/`correlationId` in MDC, async tasks can lose them unless propagation is configured on the executor. Use a `TaskDecorator` or observability context propagation supported by your Spring/Micrometer version.

Illustrative decorator propagating MDC only (it does not propagate Spring transactions):

~~~java
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();

            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
~~~

This is a custom decorator example; attach it to executors supporting `setTaskDecorator(...)`. In production, prefer Micrometer/Spring Observation propagation where appropriate, and avoid copying secrets or unnecessary PII into MDC.

### 14.3. `SecurityContext` is not workload identity

`SecurityContextHolder` uses a thread-bound strategy; an inbound HTTP user's context is not automatically valid on a background worker. If an async task genuinely executes on behalf of a user, configure delegated security contexts per framework policy; if a worker calls OAuth2 Client Credentials, use a dedicated **service identity** instead of forwarding user access tokens into long-lived jobs.

Never allow a virtual thread serving tenant A to read tenant B's headers, tokens, or MDC due to faulty propagation or missing cleanup.

## 15. Cancellation, interruption, and deadlines

A virtual thread can be interrupted like a normal thread. Yet **interrupting a request does not automatically undo remote side effects** or roll back committed transactions.

### 15.1. Future timeouts vs. I/O timeouts

~~~java
try {
    InventoryRecord result =
            inventoryFuture.get(2, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    inventoryFuture.cancel(true);
    // Cannot conclude that Inventory API did not process the request.
}
~~~

`Future.get(timeout)` bounds how long **the caller waits on the future**. `cancel(true)` requests interruption if the task supports it, but does not guarantee remote HTTP requests stop or committed DB changes roll back. `CompletableFuture.orTimeout(...)` completes the future exceptionally on timeout, yet likewise does not automatically cancel underlying client I/O.

### 15.2. Distinguishing deadlines

| Deadline/timeout | Where applied | Meaning |
| --- | --- | --- |
| Executor admission | Waiting to submit/start | Prevents infinite waits on queues/bulkheads |
| Hikari connection timeout | Waiting for a JDBC connection | No SQL ran if no connection was acquired |
| HTTP pool acquisition | Waiting for a socket/route slot | Request wasn't sent if no connection was leased |
| TCP connect/TLS | Connecting and verifying server | Distinct from response time |
| HTTP read/response | Waiting for response | Remote may have committed before timeout |
| Broker publish confirm | Waiting for broker ACK | Distinct from consumer processing |
| Business deadline | End-to-end command/event | Total time permitted across retries |
| Graceful shutdown timeout | Letting running tasks finish | Does not automatically cancel remote side effects |

An overall 3-second deadline combined with 3 retry layers × 3-second timeouts breaks your SLA. Track **remaining deadline budget** and cap attempts/callbacks.

### 15.3. Handling `InterruptedException` properly

~~~java
try {
    if (!permits.tryAcquire(
            200, TimeUnit.MILLISECONDS)) {
        throw new DownstreamBusyException("busy");
    }
    try {
        return gateway.load();
    } finally {
        permits.release();
    }
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException(
            "Operation interrupted", ex);
}
~~~

Never swallow `InterruptedException` and keep retrying forever. Remember cancellation only helps if drivers, clients, and protocols support safe cancellation, since a remote request may already have been processed.

## 16. Structured concurrency and `ScopedValue` on Java 21

Java 21 includes **Structured Concurrency** (JEP 453) and **Scoped Values** (JEP 446) as **preview features**. These APIs point toward cleaner child-task lifecycles, cancellation, and scoped contextual data than unmanaged futures.

However, in **Java 21**, they are **not stable default APIs** and require preview flags and matching JDKs. Later Java releases change both APIs and preview status, so a Java 21 `StructuredTaskScope` snippet from a blog may not compile on newer releases.

In this lesson, production baseline examples use **`ExecutorService`, `CompletableFuture`, Spring `TaskExecutor`**, and explicit resource boundaries. If adopting preview APIs in a real project, pin your JDK, enable preview flags consistently across build/runtime/test, and plan upgrades.

### 16.1. Why task structure matters

An HTTP request calls three downstreams in parallel:

~~~text
Order request
  ├── Inventory lookup
  ├── Pricing lookup
  └── Tax lookup
       ↓
Join results or cancel remaining tasks on failure
~~~

If one task fails, do not leave two orphan tasks consuming HTTP permits. Whether using `CompletableFuture` or structured concurrency, enforce **ownership, deadlines, cancellation, and result aggregation**.

### 16.2. Do not spawn unowned fire-and-forget tasks

~~~java
virtualExecutor.submit(() -> inventoryGateway.reserve(orderId));
return ResponseEntity.accepted().build();
~~~

Without a durable work record, HTTP 202 means only that the JVM queued an in-RAM task. A crash loses the work. For long business operations, **HTTP 202 must pair with a durable operation ID/status** and recoverable workers, not an executor alone.

## 17. Designing controlled fan-out

Scenario: a request looks up inventory across multiple SKUs, where each SKU is a blocking HTTP call.

Resource-balanced orchestration:

~~~mermaid
flowchart TD
    A["Request SKU list"] --> V["Validate count and input"]
    V --> C["Bounded fan-out orchestration"]
    C --> B["Inventory bulkhead max 24"]
    B --> H["RestClient / HTTP pool"]
    H --> I["Inventory API"]
    C --> D["Collect results / exceptions"]
    D --> R["Deadline + partial-failure policy"]
~~~

### 17.1. Why a per-task executor alone is not enough

~~~java
try (var executor =
             Executors.newVirtualThreadPerTaskExecutor()) {
    for (String sku : skus) {
        executor.submit(() -> inventoryGateway.getStock(sku));
    }
}
~~~

If `skus` holds 100,000 items, this spawns 100,000 tasks. Even with a semaphore inside `getStock`, all waiting tasks still allocate stacks, contexts, and payloads. Add **bounded input sizes** and **orchestration-level admission policies** so you don't create thousands of idle waiting tasks.

### 17.2. An input-bounded batch orchestrator

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class InventoryBatchReader {

    private final InventoryGateway gateway;

    public InventoryBatchReader(InventoryGateway gateway) {
        this.gateway = gateway;
    }

    public List<InventoryRecord> loadBatch(List<String> skus)
            throws InterruptedException, ExecutionException {

        if (skus.isEmpty() || skus.size() > 24) {
            throw new IllegalArgumentException(
                    "Each batch requires 1..24 SKUs");
        }

        try (var executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<InventoryRecord>> futures =
                    new ArrayList<>();

            for (String sku : skus) {
                futures.add(executor.submit(
                        () -> gateway.getStock(sku)));
            }

            List<InventoryRecord> results = new ArrayList<>();
            for (Future<InventoryRecord> future : futures) {
                results.add(future.get());
            }
            return results;
        }
    }
}
~~~

This illustrates **bounded fan-out** for a single batch. Under concurrent multi-request traffic, `InventoryGateway` must still enforce an app-wide bulkhead as in section 8; otherwise 100 requests × 24 SKUs still trigger 2,400 simultaneous HTTP calls.

**Limitation of this snippet:** if one `future.get()` fails, sibling tasks keep running until the executor closes; `try-with-resources` waits for them to finish. Production code needs an overall deadline and should cancel remaining futures when appropriate, keeping in mind cancellation does not undo remote side effects.

### 17.3. What if you have millions of items?

- Paginate/chunk the input.
- Persist progress/checkpoints durably.
- Bound worker concurrency.
- Use bulk HTTP APIs where the partner supports them.
- Maintain a retry queue/DLQ for failed items.
- Assign per-item `operationId`/idempotency.
- Decouple long-running jobs from HTTP request timeouts.
- Monitor backlog age and completed/retry/failed/unknown counts.

Never spawn a virtual thread for each of millions of rows and hope it finishes overnight without durability and recovery.

## 18. Transactional outbox and async task durability

Virtual threads are a **runtime execution primitive**; they do not preserve tasks across process restarts. For business commands needing guaranteed eventual delivery, use a transactional outbox:

~~~mermaid
sequenceDiagram
    participant A as HTTP Command
    participant D as PostgreSQL
    participant W as Outbox Worker
    participant P as External Partner
    A->>D: BEGIN update order + INSERT outbox intent
    D-->>A: COMMIT
    A-->>A: Return accepted with operationId
    W->>D: Claim due outbox row
    W->>P: Send idempotent request
    P-->>W: Confirm / reject / timeout
    W->>D: Persist outcome or retry lease
~~~

### 18.1. What does an outbox protect?

An outbox prevents **committing business state while losing the async intent**. If the HTTP request or process crashes after SQL `COMMIT`, another worker finds the `PENDING` row and processes it.

An outbox **does not automatically deliver exactly once**. If the partner processed the call and the response dropped, workers can retry. Use stable `eventId`/`operationId` values, partner idempotency keys, or status reconciliation.

### 18.2. Short SQL transactions, network calls outside transactions

~~~java
@Transactional
public String acceptOrder(OrderCommand command) {
    orderRepository.createOrder(command);
    String operationId = operationIds.newId();
    outboxRepository.insert(operationId, command);
    return operationId;
}
~~~

Workers process after the transaction. This snippet assumes `OrderCommand`, `operationIds`, and repositories are application-defined; store commands in the outbox with explicit schema versioning and appropriate encryption. **Never call partner HTTP inside the transaction**, nor fire `@Async` directly hoping the JVM stays alive.

### 18.3. Inbox protection for consumer redelivery

Even if a RabbitMQ/Kafka consumer runs business logic on virtual threads, messages can still be redelivered when DB `COMMIT` succeeds but the consumer ACK fails. Use an inbox table with unique `(consumerName, eventId)` updated inside the **same SQL transaction**.

Never use a `ThreadLocal<Set<eventId>>` or in-memory concurrent map for durable deduplication; a fresh process has no memory of past events.

## 19. Realistic capacity budget scenario

Suppose 6 pods of Order Service are deployed:

| Resource | Limit per pod | Approximate total | Risk of blind scaling |
| --- | ---: | ---: | --- |
| Hikari JDBC connections | 12 | 72 | PostgreSQL runs out of connections / lock contention rises |
| Inventory HTTP concurrent calls | 24 | 144 | Partner rate-limiting / 503s |
| RabbitMQ listener consumers | 4 | 24 | Growing unacked count, DB overload |
| Prefetch per Rabbit consumer | 10 | Up to ~240 in flight | Heavy redelivery after crash |
| Inbound virtual threads | Workload-driven | Can grow huge | Memory/backlog pressure without admission caps |

Numbers are illustrative. 24 Inventory permits per pod do not always equal 24 physical HTTP sockets across every transport: HTTP/2 multiplexing, connection reuse, and per-route caps behave differently.

### 19.1. Tracing bottlenecks by layer

~~~mermaid
flowchart TD
    A["Latency rising"] --> B{"Which layer?"}
    B --> C["Carrier pinning / CPU?"]
    B --> D["JDBC pool pending?"]
    B --> E["HTTP pool pending / 429?"]
    B --> F["Rabbit unacked / Kafka lag?"]
    B --> G["Heap/GC / too many tasks?"]
    C --> H["JFR / thread dumps"]
    D --> I["Reduce tx duration / SQL tuning"]
    E --> J["Bulkhead/rate-limit/timeouts"]
    F --> K["Consumer concurrency/idempotency"]
    G --> L["Bound input and queued work"]
~~~

Never glance at high virtual thread counts and conclude the JVM is "slow." If thread count is high while CPU is low and Hikari pending climbs, the culprit is **DB capacity or transaction duration**.

### 19.2. Budgeting when the partner enforces 100 QPS

If Inventory grants **100 requests/second across the whole client identity**, capping 6 pods at 24 permits each isn't enough: fast calls can exceed 100 QPS. Add distributed rate limiting/quota allocation, or conservative per-pod budgets aligned with autoscaling and partner SLAs. Semaphores bound concurrency, **not QPS**.

## 20. Testing virtual threads and resource limits

### 20.1. Verifying the JVM actually uses virtual threads

Java 21 unit test:

~~~java
import java.util.concurrent.Executors;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class VirtualThreadTest {

    @Test
    void runsOnVirtualThread() throws Exception {
        try (var executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            boolean virtual = executor.submit(
                    () -> Thread.currentThread().isVirtual()).get();

            assertTrue(virtual);
        }
    }
}
~~~

This test only verifies the JDK executor; **it does not prove Spring `@Async` is wired properly**.

### 20.2. Testing `@Async` through the Spring proxy

Create a service with:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ThreadInspectionService {

    @Async("inventoryTaskExecutor")
    public CompletableFuture<Boolean> isVirtual() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().isVirtual());
    }
}
~~~

In a Spring test context with `@EnableAsync` and the named `inventoryTaskExecutor`, inject `ThreadInspectionService` and call:

~~~java
boolean virtual = service.isVirtual().get();
assertTrue(virtual);
~~~

Calling `new ThreadInspectionService()` or self-invocation skips testing the Spring proxy. For Boot property auto-configuration, also test without a custom executor to verify the default bean on your version.

### 20.3. Load-testing HTTP and JDBC limits

Use MockWebServer/WireMock for HTTP (with a TLS-enabled test server when testing real TLS), Testcontainers PostgreSQL for SQL, and bounded load generation:

1. Submit 200 I/O-waiting tasks with bounded input.
2. Set Hikari max to 8 and HTTP bulkhead to 16.
3. Measure max active, pending, and timeouts; never assume 200 SQL transactions run concurrently.
4. Inject 300–1,000 ms partner latency plus 429/503 responses.
5. Verify admission caps and retry budgets.
6. Confirm zero permit leaks on exceptions or interruptions.
7. Confirm zero infinite queues or OOMs during bursts.
8. Verify outbox retains unfinished tasks across process stop/restart.

**Never load-test against a production partner** without explicit approval and quotas. Use synthetic data, isolated test tenants/queues, and dedicated environments.

### 20.4. Testing Java 21 pinning

Create a `synchronized` + blocking HTTP test server scenario to inspect pinning traces/JFR and compare against keeping blocking I/O outside the monitor. Never generalize a microbenchmark: warmup, GC, CPU core count, carrier scheduler, and driver version all affect behavior.

### 20.5. Testing async boundaries and transactions

A test should demonstrate:

~~~text
Given an open SQL transaction
When the caller submits an @Async task
Then the task must not assume uncommitted data is visible
And the task is not inside the caller's transaction
~~~

Refactor to an outbox or after-commit workflow when guarantees are needed. `TransactionSynchronization.afterCommit()` delays submission until after commit, yet **remains non-durable** if the process crashes between commit and submit; an outbox is safer for critical work.

### 20.6. Testing broker ACK timing

With RabbitMQ/Kafka Testcontainers:

- Ensure listeners never ACK/commit offsets before business transactions or durable handoffs finish.
- Simulate DB `COMMIT` followed by crash before ACK → redelivery is deduplicated by the inbox.
- Simulate listener exceptions/poison messages → proper retries/DLQ.
- Verify virtual threads do not break per-partition/aggregate ordering.
- Ensure graceful shutdown never marks pending work as succeeded.

## 21. Observability and diagnostics

### 21.1. JVM/JFR metrics

Key signals to watch:

| Signal | What you want to know |
| --- | --- |
| JFR `jdk.VirtualThreadPinned` | Virtual threads blocking while pinned to a carrier |
| Carrier/CPU saturation | Runnable tasks relative to CPU cores |
| Heap allocation/GC | Footprint of many tasks/ThreadLocals/payloads |
| Thread dumps/stack traces | I/O waits vs. lock waits vs. deadlocks |
| Executor active/admission wait | How many tasks are waiting to enter bulkheads |
| Request p95/p99 latency | End-to-end delay |
| Error/timeout counts | Deadlines, rate limits, overload |

Several traditional Java 21 APIs/monitors do not count virtual threads the same way as OS/platform threads. Use JFR, virtual-thread-aware JVM thread dumps, and modern instrumentation rather than relying solely on platform `ThreadMXBean` counts.

### 21.2. External resource metrics

| Metric | Diagnoses |
| --- | --- |
| `hikaricp.connections.active` | JDBC connections currently in use |
| `hikaricp.connections.pending` | Tasks waiting for a connection |
| `hikaricp.connections.timeout` | Pool acquisition failures |
| HTTP connection pool leased/pending | HTTP transport bottlenecks |
| HTTP 429/503 and response latency | Partner quotas and overload |
| Redis command latency/errors | Cache/backend bottlenecks |
| Kafka consumer lag/commit failures | Backlogs, processing/commit issues |
| RabbitMQ ready/unacked/consumers | Queue pressure and ACK timing |
| Outbox pending oldest age | Unfinished durable integration work |
| Inbox duplicate count | Replays safely deduplicated |
| End-to-end business completion lag | True time until downstream success |

Exact metric names depend on Micrometer/Actuator/drivers and export config; do not assume pool metrics exist automatically if using an uninstrumented custom HTTP transport.

### 21.3. Tracing across true boundaries

A useful trace includes spans:

~~~text
HTTP Order Command
  -> SQL transaction / save order + outbox
  -> outbox relay attempt
       -> OAuth2 token acquisition (if needed)
       -> Inventory HTTP / connection wait
       -> broker publish ACK
  -> consumer delivery
       -> inbox dedupe + SQL commit
       -> consumer ACK
~~~

Virtual threads alter thread execution, **not trace parent-child semantics**. Propagate contexts across async boundaries and broker headers per policy; never put secrets or PII into span attributes.

## 22. Runbook when enabling virtual threads triggers errors

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Throughput doesn't improve | DB/partner/broker bottleneck | Hikari pending, HTTP pool/429s, broker lag |
| 100% CPU despite many virtual threads | CPU-bound tasks / JSON processing | CPU profiling, serialization, core count |
| Sharp p99 spike | Many tasks queuing for pools | Bulkhead/admission wait latency |
| OOM after enabling virtual threads | Unbounded tasks/payloads/ThreadLocals | Heap, task count, per-task memory |
| Hikari timeouts | JDBC pool exhausted / long transactions | Transaction duration, SQL locks |
| Rising HTTP 429/503s | Partner quota/concurrency limits | Rate limiter, QPS, bulkhead |
| Rising JFR pinned events | `synchronized` + blocking I/O / native calls | JFR stack traces, JDK version |
| `@Async` not running virtual | Custom platform executor, missing proxy/`@EnableAsync` | Bean selection, `isVirtual()` |
| `@Async` self-invocation | Bypasses Spring proxy | Bean split / explicit executor |
| `@Scheduled` job-only app exits immediately | Only daemon virtual threads left | `spring.main.keep-alive`/lifecycle |
| Batch job runs serially despite VT | Fixed-delay semantics/scheduler | `SimpleAsyncTaskScheduler` fixed-delay behavior |
| Missing MDC/trace ID | Context not propagated across tasks | `TaskDecorator`/Observation |
| SQL transaction not shared | Distinct thread-bound contexts | Transaction boundaries/outbox |
| Rising Rabbit unacked | Hung handlers, wrong prefetch/ACK | Container concurrency, DB pool |
| Out-of-order Kafka data | Async offload with early offset commit | Per-partition ordering/ACK policy |
| HTTP timeout yet remote applied side effect | Unknown outcome | Idempotency/status lookup |
| Process restart loses async jobs | In-RAM executor isn't durable | Outbox/work table/broker |

### 22.1. Do not fix by raising every limit at once

If HTTP 503s from Inventory jump after enabling virtual threads, do not simultaneously raise the HTTP pool, Hikari max, and consumer concurrency. Instead:

1. Pinpoint the constrained resource bottleneck via metrics.
2. Lower concurrency at the overloaded boundary.
3. Enforce fail-fast/backpressure and bounded retries.
4. Re-measure p95/p99, error rate, and throughput.
5. Multiply totals across all replicas.
6. Raise limits only when downstream capacity genuinely allows.

## 23. Anti-patterns to avoid

| Anti-pattern | Why it fails | Alternative |
| --- | --- | --- |
| Spawning millions of virtual threads for unpaginated input | Heap and task backlog explode | Bounded batches/admission |
| Using virtual threads for CPU-bound work expecting speedup | CPU cores don't multiply | CPU-sized executors/profiling |
| Pooling virtual threads to "reuse" threads | Breaks thread-per-task model | New virtual thread per task + resource bulkheads |
| Setting Hikari pool to thousands when enabling VT | DB gains no extra capacity | DB budget and short transactions |
| Holding SQL transactions across HTTP waits | Ties up JDBC connections/locks | Outbox/saga |
| Wrapping blocking network I/O in `synchronized` on Java 21 | Pins carriers and serializes requests | Short critical sections |
| `@Async` self-invocation | Proxy never runs | Cross-bean calls |
| Swallowing errors in `@Async void` | No future to handle failures | `CompletableFuture`/error handler |
| Using `ThreadLocal` as a large data cache | Every virtual thread retains memory | Shared bounded cache |
| Using inbound HTTP user tokens in long background jobs | Expiry/authorization leaks | Dedicated service identity/explicit delegation |
| Offloading Kafka records to executor and committing offsets early | Data loss/reordering on crash | Durable handoff/controlled ACK |
| Rabbit `AUTO` ACK after submitting only to RAM | Message dropped before execution | Durable work/async ACK semantics |
| Concluding remote didn't run after `Future.get(timeout)` | Timeouts do not roll back remotes | Idempotency/reconciliation |
| Treating `ExecutorChannel` as a durable queue | JVM crash loses tasks | Broker/outbox/work table |
| Enabling VT on WebFlux and calling `block()` on event loop | Blocks the event loop | Reactive pipeline or deliberate offload |
| Leaving tasks uncanceled after request failure | Orphan tasks keep holding HTTP permits | Ownership/cancellation/deadlines |
| Measuring success by submitted task count | Submission is not completion | Business outcome metrics |
| Testing only with mocks and declaring concurrency safe | Misses pools, brokers, and transactions | Testcontainers/load tests |

## 24. Checklist before deploying Java 21 virtual threads

- [ ] Project runs on Java 21 and Spring Boot/Spring Framework versions supporting virtual-thread configuration.
- [ ] Verified executors/HTTP handlers genuinely run on virtual threads using `isVirtual()`.
- [ ] Confirmed Kafka/Rabbit/WebFlux native threads are not assumed to become virtual threads automatically.
- [ ] `@Async` has `@EnableAsync`, runs via Spring proxies, and uses explicit executors.
- [ ] Background tasks configure lifecycle/shutdown and `spring.main.keep-alive` where needed.
- [ ] Benchmarked benefits on blocking I/O rather than CPU-only tests.
- [ ] Avoided blocking I/O inside `synchronized` on Java 21; monitored JFR pinning events.
- [ ] Designed and tested safe ThreadLocal/MDC/security context propagation and cleanup.
- [ ] Budgeted capacity for JDBC Hikari max, HTTP pools, Redis, and broker consumer concurrency.
- [ ] Enforced bounded admission, semaphores/bulkheads, and rate limiters for partner quotas.
- [ ] Configured layered timeouts and end-to-end deadlines; retries never multiply indefinitely.
- [ ] Never assumed transactions propagate automatically onto `@Async` threads.
- [ ] Prevented Kafka/Rabbit ACKs before business commits or durable handoffs.
- [ ] Persisted critical tasks in outboxes/work tables/brokers rather than executor RAM alone.
- [ ] Kept `eventId`/`operationId` constant and protected replays with inboxes/idempotency.
- [ ] Implemented cancellation/interruption handling without treating timeouts as guaranteed remote failures.
- [ ] Tested resource exhaustion, 429/503 responses, connection waits, pinning, and broker redelivery.
- [ ] Exported metrics for CPU, JFR pinned events, Hikari, HTTP pools, queue backlogs, and business lag.
- [ ] Excluded secrets/PII from ThreadLocal caches, logs, trace tags, and off-contract broker payloads.
- [ ] Calculated aggregate limits across all replicas and autoscaling ceilings.

**Key takeaway:** **Java 21 virtual threads make waiting on I/O much cheaper in platform threads**, helping blocking code scale across many scenarios. Yet they do not add HikariCP connections, raise partner HTTP quotas, stop Redis cache stampedes, replace Kafka/Rabbit consumer ACKs, or create distributed transactions. Safe Spring Boot integrations bound resources **at the actual downstream boundaries**, keep **transactions short, hand off async work durably, enforce idempotency, bound retries, and maintain full observability**.

## References

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): Java 21 virtual threads design and semantics.
- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): creating, observing, and adopting virtual threads.
- [Oracle Java 21 — Virtual Thread Scheduler](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html#GUID-BB3B8D10-01D6-4B63-96EC-885F3209C7C4): carrier scheduler and blocking behavior.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): monitor pinning changes beyond Java 21.
- [JEP 453 — Structured Concurrency (Preview)](https://openjdk.org/jeps/453): Java 21 structured concurrency preview.
- [JEP 446 — Scoped Values (Preview)](https://openjdk.org/jeps/446): scoped contextual data, preview in Java 21.
- [Spring Boot — Virtual Threads](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html): `spring.threads.virtual.enabled`, task execution and scheduling.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, `@Scheduled`, executors, and schedulers.
- [Spring Framework — SimpleAsyncTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/SimpleAsyncTaskExecutor.html): virtual thread support and concurrency throttling.
- [Spring Framework — Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): thread-bound transaction boundaries.
- [Spring Boot — DataSource Configuration](https://docs.spring.io/spring-boot/reference/data/sql.html): HikariCP and pool sizing.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, `WebClient`, and HTTP transport.
- [Spring Integration — Reference](https://docs.spring.io/spring-integration/reference/): channels, async boundaries, and error handling.
- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): consumer, offset, and ACK lifecycles.
- [Spring AMQP — Listener Containers](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): consumer channels, prefetch, and ACKs.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP): connection pool limits and timeouts.
- [Enterprise Integration Patterns — Idempotent Receiver](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html): duplicate delivery and consumer safety.
