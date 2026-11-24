# Virtual Threads and Capabilities Dependent on JDK and Spring Boot Versions

Virtual threads are lightweight threads managed by the JVM, introduced as a preview feature in JDK 19/20 and finalized in **JDK 21**. They allow an application to create one thread per task without maintaining a dedicated OS thread for each task. For Spring Boot applications handling many concurrent requests or tasks that primarily wait on I/O, virtual threads can improve concurrency capacity and make blocking code easier to read.

However, virtual threads are not a CPU speedup mode, do not give databases or remote APIs infinite capacity, and are not integrated identically across all Java/Spring Boot versions. You must distinguish **JDK capabilities**, **Spring Framework integrations**, **Spring Boot auto-configuration**, and **web server or third-party library behavior**.

This lesson covers how virtual threads work, version requirements, Spring Boot configuration, impacts on task execution/scheduling, transactions and `ThreadLocal`, pinning and resource constraints, and a workflow for deciding whether to enable the feature.

## 1. Platform Threads vs. Virtual Threads

Java has long provided threads through the `Thread` class. A platform thread typically maps fairly directly to an OS thread. The OS is responsible for scheduling and managing those threads.

A virtual thread is also a `Thread`, but the JVM manages scheduling it onto a pool of platform threads called **carrier threads**. When a virtual thread executes a runtime-supported blocking operation, the JVM can suspend the virtual thread and release the carrier to run another virtual thread.

| Characteristic | Platform Thread | Virtual Thread |
|---|---|---|
| Management | Tied to an OS thread | JVM schedules onto carrier threads |
| Creation/retention cost | Higher | Significantly lower |
| Suitable count | Typically limited to smaller numbers | Can be created in very large numbers |
| Blocking I/O | May hold the OS thread while waiting | Many blocking operations can unmount and free the carrier |
| CPU-bound tasks | Uses CPU like any other thread | Does not add extra CPU capacity |
| Thread pooling | Commonly pooled to bound resources | Typically one virtual thread per task |
| Java API | Traditional `Thread` and Executor | Still `Thread`, plus builders/executors for virtual threads |

If thousands of requests wait simultaneously on a database or remote API, platform threads can remain tied up while waiting. Virtual threads let the JVM pause waiting tasks and reuse carriers for other tasks, reducing the number of OS threads needed for the same concurrency level.

### High-Level Execution Diagram

~~~text
Application tasks
   |       |       |
   v       v       v
Virtual Virtual Virtual
thread  thread  thread
   \       |       /
    \      |      /
     v     v     v
 JVM virtual-thread scheduler
          |
          v
 Carrier platform threads
          |
          v
       OS threads
~~~

When a virtual thread blocks on a supported operation, the JVM can unmount it from its carrier. Once the operation completes, the virtual thread is scheduled to resume on an available carrier.

Do not think of virtual threads as “lighter” OS threads provided by the operating system. They are a JVM abstraction with their own lifecycle and scheduler.

## 2. Which JDK Versions Support Virtual Threads?

| JDK | Virtual Thread Status |
|---|---|
| JDK 19 | Preview feature |
| JDK 20 | Preview feature undergoing refinement |
| JDK 21 | Final (standard), no preview flag required |
| JDK 22 and later | Standardized feature with ongoing improvements |

Virtual threads were finalized under JEP 444 and became a standard feature in JDK 21.

### Using Preview on JDK 19/20

On JDK 19 or 20, applications must enable preview at both compile time and runtime per that JDK version's rules:

~~~bash
javac --enable-preview --release 20 Example.java
java --enable-preview Example
~~~

The example above illustrates JDK 20; adjust the version number to match the JDK you use. Preview APIs can change across JDK releases, so do not apply JDK 21 instructions verbatim to a JDK 19/20 project.

### Using on JDK 21+

Starting with JDK 21, the virtual thread API is standard:

~~~java
Thread thread = Thread.ofVirtual()
        .name("report-task")
        .start(() -> generateReport());

thread.join();
~~~

No `--enable-preview` flag is required.

When choosing a JDK for a Spring Boot application, verify all of the following:
- The JDK used to compile.
- The JDK used to run the application.
- The JDK configured in the IDE.
- The JDK used by the Gradle/Maven daemon.
- The JDK inside containers and production.

A project compiled with JDK 21 while production runs JDK 17 cannot use virtual threads as a standard JDK 21 feature.

## 3. Creating Virtual Threads with the Java API

The JDK provides several ways to create and run virtual threads.

### Thread.ofVirtual()

~~~java
Thread thread = Thread.ofVirtual()
        .name("report-task")
        .start(() -> generateReport());

thread.join();
~~~

`Thread.ofVirtual()` returns a builder to configure a name or supported attributes, then starts the virtual thread.

### Thread.startVirtualThread()

For simple tasks:

~~~java
Thread thread = Thread.startVirtualThread(() -> {
    System.out.println("Running on a virtual thread");
});
~~~

This API creates and starts a virtual thread in a single call.

### Executors.newVirtualThreadPerTaskExecutor()

For multiple independent tasks, the JDK provides an executor that creates one virtual thread per task:

~~~java
try (var executor =
        Executors.newVirtualThreadPerTaskExecutor()) {

    Future<String> first = executor.submit(
            () -> loadCustomer("C-100")
    );

    Future<String> second = executor.submit(
            () -> loadOrders("C-100")
    );

    System.out.println(first.get());
    System.out.println(second.get());
}
~~~

The executor closes upon exiting the `try` block. Closing the executor waits for submitted tasks to finish per `ExecutorService` lifecycle semantics.

### Why Shouldn't Virtual Threads Be Pooled Like Platform Threads?

Virtual threads are designed to be created per task. A fixed pool of a few dozen virtual threads can reintroduce the very concurrency bottleneck you are trying to avoid.

Instead:
- Use one virtual thread per task to run work.
- Use connection pools to bound database connections.
- Use semaphores/bulkheads to limit calls to low-capacity external services.
- Use rate limiters when request rates must be throttled.

Virtual threads are cheaper than platform threads, but the downstream resources tasks consume remain finite.

## 4. Which Workloads Suit Virtual Threads?

Virtual threads are especially useful for workloads with significant waiting time:

- HTTP requests calling one or more external APIs.
- Database queries with noticeable latency.
- File or socket reads/writes.
- Message-processing tasks that mostly wait on I/O.
- A single request coordinating multiple independent blocking operations.

Example:

~~~java
public OrderDetails loadOrderDetails(String orderId) {
    Customer customer = customerClient.findCustomer(orderId);
    List<OrderItem> items = orderRepository.findItems(orderId);
    Payment payment = paymentClient.findPayment(orderId);

    return new OrderDetails(customer, items, payment);
}
~~~

If all three operations are independent and blocking, the request's virtual thread can wait on each I/O operation without tying up a platform thread throughout the wait.

However, the example above still executes sequentially. Running all three concurrently requires an explicit concurrency construct such as an executor or structured concurrency matching your JDK version. Virtual threads by themselves do not turn sequential calls into parallel execution.

### CPU-Bound Workloads

Computation example:

~~~java
public BigInteger calculatePrimeRange(int start, int end) {
    // Long-running arithmetic computation.
}
~~~

If a task spends most of its time burning CPU, virtual threads do not make the computation faster. Carrier threads remain bounded by the scheduler and available CPU cores.

For CPU-bound workloads:
- Bound concurrent tasks according to CPU capacity.
- Use an executor suited for CPU parallelism.
- Optimize the algorithm before switching thread models.
- Measure actual throughput, CPU utilization, and latency.

Virtual threads are a tool for high-blocking concurrency, not a substitute for CPU optimization.

## 5. From Which Version Does Spring Boot Support Virtual Threads?

Spring Boot integrates virtual thread configuration through the property:

~~~properties
spring.threads.virtual.enabled=true
~~~

This property was introduced in **Spring Boot 3.2**. Support relies on Spring Framework 6.1 capabilities and requires **JDK 21 or later** so virtual threads are a standard feature.

| Platform | Condition |
|---|---|
| JDK 21+ | Standard virtual threads available |
| Spring Framework 6.1+ | Abstractions/integrations supporting virtual threads available |
| Spring Boot 3.2+ | `spring.threads.virtual.enabled` property available for auto-configured support |
| Spring Boot 3.1 or earlier | Lacks this Boot 3.2 property; may need manual API configuration matching JDK/framework |
| JDK 17 runtime | Lacks standard JDK 21 virtual thread API |

Spring Boot 3.2 has a Java 17 baseline, yet running the app on Java 17 **does not mean** you can enable virtual threads. The feature requires JDK 21+.

### Distinguishing Boot's Minimum JDK from the JDK Required for Virtual Threads

- A Spring Boot version may support running on JDK 17.
- That same Boot version can support virtual threads when run on JDK 21+.
- On a lower JDK, standard virtual thread APIs cannot be used.

When choosing a specific combination, check the release notes and compatibility matrix for your exact Spring Boot, Spring Framework, JDK, and embedded server versions. Do not upgrade a single Spring module to a version outside the BOM just to obtain virtual thread APIs.

## 6. Enabling Virtual Threads in Spring Boot

With Spring Boot 3.2+ and JDK 21+, enable it in your configuration file:

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
~~~

Or:

~~~properties
spring.threads.virtual.enabled=true
~~~

When enabled, Spring Boot can configure compatible task execution and scheduling components to use virtual threads, provided the application does not define replacement beans and matching auto-configuration conditions are met.

Application example:

~~~java
@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

There is no need to manually spawn a virtual thread per bean or annotate every service. Spring Boot integrates the feature via abstractions such as `TaskExecutor` and `TaskScheduler`.

### Enabling via Command Line

~~~bash
java -jar app.jar --spring.threads.virtual.enabled=true
~~~

Or with Gradle:

~~~bash
./gradlew bootRun --args='--spring.threads.virtual.enabled=true'
~~~

With the Maven Spring Boot plugin, pass the property via application arguments according to your plugin setup:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--spring.threads.virtual.enabled=true
~~~

Argument syntax for build plugins may need adjustment depending on plugin version and project setup. Once running, verify that the app actually picked up the property and runs on the right JDK.

## 7. What Does Spring Boot Change When This Property Is Enabled?

The property does not turn every thread in the JVM into a virtual thread. It affects components Spring Boot auto-configures that carry matching integration support.

| Area | Role of Virtual Threads |
|---|---|
| Auto-configured task executor | Can execute tasks on virtual threads |
| Auto-configured task scheduler | Can use a virtual-thread-enabled scheduler |
| `@Async` | Can use Boot's configured executor unless replaced by another executor |
| `@Scheduled` | Can use Boot's configured scheduler unless replaced by other configuration |
| Servlet request processing | Depends on the web server and matching configuration/version |
| Database connections | Does not change connection count or pool capacity |
| Reactive pipelines | Does not automatically convert reactive execution into virtual threads |

Treat this property as an **auto-configuration integration**, not a JVM-wide switch.

### Custom Beans Can Override Auto-Configuration

If the application declares its own `TaskExecutor` or `TaskScheduler`, Spring Boot may back off from the corresponding auto-configuration. In that case, enabling `spring.threads.virtual.enabled` does not ensure the application's custom executor uses virtual threads.

Example custom executor using a platform thread pool:

~~~java
@Bean
ThreadPoolTaskExecutor applicationTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(32);
    executor.setQueueCapacity(200);
    return executor;
}
~~~

This bean follows `ThreadPoolTaskExecutor` semantics. Do not assume it automatically turns into a virtual-thread executor just because Boot's property is enabled.

Verify which bean is actually injected at task execution sites and whether custom configurations back off auto-configuration.

## 8. TaskExecutor and @Async

`@Async` delegates method calls to a Spring-selected executor. With Boot's virtual thread support, the auto-configured executor can use virtual threads when the property is enabled and no other configuration overrides it.

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

~~~java
@Service
public class InvoiceService {

    @Async
    public CompletableFuture<String> generateInvoice(String invoiceId) {
        String result = loadAndGenerate(invoiceId);
        return CompletableFuture.completedFuture(result);
    }

    private String loadAndGenerate(String invoiceId) {
        // Work may involve blocking I/O.
        return "invoice-" + invoiceId;
    }
}
~~~

When the method is called through the Spring proxy, the task is submitted to the executor chosen for async processing.

### Does Enabling the Property Automatically Enable @Async?

No. Distinguish between:
- `spring.threads.virtual.enabled`: configures virtual thread support on the corresponding auto-configured task infrastructure.
- `@EnableAsync`: enables `@Async` annotation processing in proxy mode.
- `@Async("executorName")`: selects an executor by explicit name/qualifier.

If `reportExecutor` is a custom bean using a platform thread pool, a method annotated with `@Async("reportExecutor")` can still execute on platform threads even when Boot virtual threads are enabled.

### Checking the Running Thread

In diagnostic code, you can inspect:

~~~java
boolean virtual = Thread.currentThread().isVirtual();
String threadName = Thread.currentThread().getName();
~~~

`Thread.isVirtual()` exists since JDK 21. Tests should verify the actual executor used in a real context rather than merely asserting that the property equals `true`.

Self-invocation still bypasses the async proxy regardless of whether the executor uses virtual threads. Calling an `@Async` method from another method on the same bean may not dispatch to the executor.

## 9. TaskScheduler and @Scheduled

`@Scheduled` uses Spring's task scheduling infrastructure. Spring Framework 6.1 includes virtual-thread-friendly scheduler support via `SimpleAsyncTaskScheduler`.

~~~java
@Configuration
@EnableScheduling
public class SchedulingConfiguration {
}
~~~

~~~java
@Component
public class CleanupJob {

    @Scheduled(fixedRate = 30_000)
    public void cleanExpiredSessions() {
        // Work may wait on I/O.
    }
}
~~~

When Boot configures a scheduler backed by virtual threads, scheduled tasks can run according to that scheduler's execution model.

### Fixed-Rate, Cron, and Fixed-Delay

`SimpleAsyncTaskScheduler` is designed around a scheduler thread and can launch tasks on dedicated virtual threads. However, fixed-delay tasks have special semantics: the task runs on the scheduler thread instead of always forking a new virtual thread like other trigger types.

Therefore:
- Do not assume every scheduled task runs on its own virtual thread.
- Do not assume multiple tasks can overlap unboundedly.
- For long-running tasks, understand overlap, fixed-rate/fixed-delay semantics, and duplicate-execution prevention.

If business rules require a job to run only once at a time across multiple application instances, use an appropriate lock/distributed scheduler mechanism. `@Scheduled` inside a single JVM is not a distributed lock.

## 10. Virtual Threads and Servlet Request Processing

A Spring MVC application normally handles requests on servlet container threads. Enabling virtual threads for task executors **does not by itself guarantee** HTTP requests run on virtual threads.

Request thread behavior depends on:
- Embedded server version (Tomcat, Jetty, or Undertow).
- The server's virtual thread support.
- How Spring Boot wires the executor into the server.
- Specific server/connector configuration.
- Deployment setup if using an external servlet container.

Certain servers and versions support virtual-thread-based request executors, so check the matching server and Boot documentation. Do not infer from `@Async` running on virtual threads that controller requests run on virtual threads too.

You can observe this inside a controller:

~~~java
@RestController
@RequestMapping("/diagnostics")
public class ThreadDiagnosticsController {

    @GetMapping("/thread")
    public Map<String, Object> threadInfo() {
        Thread thread = Thread.currentThread();

        return Map.of(
                "name", thread.getName(),
                "virtual", thread.isVirtual()
        );
    }
}
~~~

This is an illustrative diagnostic endpoint. Do not expose internal runtime details on public production APIs without clear need and security controls.

If request threads remain platform threads, virtual thread configuration has not necessarily failed; the server may be using its own executor untouched by the task execution property.

## 11. Virtual Threads and Spring MVC Blocking I/O

Spring MVC commonly uses an imperative/blocking programming model. Inside a request, controllers or services may call synchronous repositories or HTTP clients.

~~~java
@GetMapping("/orders/{id}")
public OrderView getOrder(@PathVariable String id) {
    Order order = orderService.findById(id);
    Customer customer = customerClient.getCustomer(order.customerId());

    return OrderView.from(order, customer);
}
~~~

If requests are handled on virtual threads and blocking calls are JVM-supported, threads can unmount while waiting on I/O. This is a natural fit.

Still check:
- Whether the client is genuinely blocking.
- Whether libraries use native/foreign calls or special blocking primitives.
- Whether the database connection pool has sufficient capacity.
- Whether semaphores/rate limits protect downstream dependencies.
- Whether request timeouts and cancellation are handled properly.

Virtual threads do not eliminate remote service latency. They only help utilize threads more efficiently while waiting.

## 12. Virtual Threads and Spring WebFlux

Spring WebFlux is built around a reactive/non-blocking model, typically powered by an event loop and reactive streams.

| Criterion | Spring MVC + Virtual Threads | Spring WebFlux |
|---|---|---|
| Programming model | Imperative/blocking optionally using virtual threads | Reactive, non-blocking |
| Waiting for I/O | Virtual thread can park/unmount on supported blocking calls | Event loop continues serving other work while I/O isn't ready |
| APIs | Typically synchronous return types or async per design | `Mono`/`Flux` and reactive composition |
| Thread context | `ThreadLocal` tied to each thread | Requires attention to context propagation |
| Goal | Make blocking concurrency cheaper | Handle high non-blocking I/O via event-driven model |

Do not rewrite a WebFlux application onto virtual threads just because virtual threads sound faster. If an app already uses non-blocking clients and reactive pipelines effectively, switching may yield little benefit.

Conversely, if a system relies mainly on blocking libraries and benefits from readable imperative code, Spring MVC on virtual threads can be a strong option.

**Do not block event-loop threads with blocking code just because the JDK has virtual threads.** The WebFlux event loop follows its own execution contract; genuinely unavoidable blocking calls must still be offloaded to an appropriate scheduler.

## 13. ThreadLocal and Context Propagation

Virtual threads are still threads. They support `ThreadLocal` and `InheritableThreadLocal` per Java semantics, with each virtual thread maintaining its own state.

~~~java
private static final ThreadLocal<String> REQUEST_ID =
        new ThreadLocal<>();

Thread.startVirtualThread(() -> {
    REQUEST_ID.set("req-123");
    try {
        process();
    } finally {
        REQUEST_ID.remove();
    }
});
~~~

### ThreadLocal Is Not Shared Automatically Across Virtual Threads

If a task spawns a new virtual thread, the parent's `ThreadLocal` value does not automatically become a shared mutable context. `InheritableThreadLocal` inherits values at thread creation time, yet it should not be used casually to pass data across thousands of tasks.

Each virtual thread holds its own `ThreadLocal` storage. If massive numbers of virtual threads are created and each stores large objects in `ThreadLocal`, memory usage can still climb substantially.

### MDC and Logging Context

Some logging frameworks store MDC in `ThreadLocal`. When work switches to another thread, never assume the caller's MDC context propagates across every executor or callback.

Verify:
- Whether the executor supports a context decorator.
- Whether the Spring Security context propagates across the selected executor.
- Whether trace/correlation IDs propagate.
- Whether MDC is cleaned up after task completion.

Virtual threads do not automatically solve every context propagation problem.

### ThreadLocal and Transactions

Spring imperative transactions typically bind resources and transaction state to the current thread through transaction synchronization infrastructure.

If a method sits inside a transaction on a virtual thread and continues executing synchronously on that exact thread, normal imperative transaction semantics work as expected.

However, if code hops to another thread—even another virtual thread—the thread-bound transaction context **does not automatically migrate to the new thread**. The same holds true for platform threads.

~~~java
@Transactional
public void processOrder() {
    orderRepository.save(order);
    asyncService.processNextStep();
}
~~~

If `processNextStep()` runs via `@Async` on another virtual thread, the caller's open transaction does not propagate to the worker thread. The worker needs its own transaction boundary if it performs transactional data work.

Do not confuse virtual threads with reactive transaction contexts. Reactive transactions are managed via reactive context under their own model.

## 14. Virtual Threads, Spring Security, and Request Context

Several frameworks store per-request state in `ThreadLocal`, such as security context or request context in imperative stacks.

When requests run on virtual threads, `ThreadLocal` works within that thread's scope. When tasks are dispatched to another executor, context propagation depends on executor configuration and framework integrations.

For Spring Security:
- Use an executor configured to propagate `SecurityContext` when required.
- Do not manually copy context across tasks without understanding its lifecycle.
- Ensure context is cleared when tasks finish.
- Test authorization checks in actual async execution flows.

For request-scoped beans:
- Request scope has a lifecycle tied to the HTTP request.
- An async task may run after the request finishes.
- Never hold references to request-scoped objects and access them beyond the request lifecycle.
- Pass needed values via immutable command/value objects.

Virtual threads do not extend a request context's lifetime beyond the request itself.

## 15. Pinning: When a Virtual Thread Holds Its Carrier

A virtual thread can become **pinned** to its carrier in certain situations, preventing the JVM from unmounting it while blocking. If many virtual threads stay pinned for long periods, scalability gains shrink.

On JDK 21–23, a notable cause is a virtual thread performing a blocking operation inside a `synchronized` monitor in cases where the runtime must keep the carrier thread attached. Native methods and some foreign function calls can also cause pinning.

~~~java
synchronized (lock) {
    blockingNetworkCall();
}
~~~

If the blocking call lasts inside the monitor, the virtual thread can tie up its carrier for that duration. If many tasks do this concurrently, carrier thread occupancy rises.

### JDK 24 and Synchronized Improvements

JDK 24 introduced changes via JEP 491, allowing virtual threads to unmount while waiting inside monitors in scenarios that previously caused `synchronized` pinning. Consequently, the blanket advice “never block inside `synchronized` because it always pins” no longer holds across all modern JDKs.

Still:
- Native/foreign calls can still impose limits or pinning.
- Lock contention still carries overhead.
- Holding a lock across slow external calls still hurts throughput and causes bottlenecks.
- Older libraries may exhibit suboptimal blocking behavior.

When supporting multiple JDKs, test behavior on the **actual runtime JDK** instead of applying a single blanket rule.

### Diagnosing Pinning

You can use Java Flight Recorder (JFR) to observe virtual thread events, including `jdk.VirtualThreadPinned` on JDKs supporting that event.

Some JDK versions provide diagnostic options such as `-Djdk.tracePinnedThreads`; exact flag names, capabilities, and support vary by release. Prefer JFR and observability tools documented for your exact JDK version.

Do not rewrite code solely because you see the `synchronized` keyword. Measure pinning duration, held carrier counts, and impact on latency/throughput.

## 16. Synchronized, Locks, and Contention

Virtual threads do not eliminate synchronization concerns.

~~~java
private final Object lock = new Object();

public void update() {
    synchronized (lock) {
        updateSharedState();
    }
}
~~~

Even without pinning on newer JDKs, multiple virtual threads competing for the same lock still wait on one another. Only one thread can hold a monitor at a time.

Important principles still apply:
- Keep critical sections short.
- Avoid remote I/O while holding locks.
- Avoid global locks across all requests when state can be partitioned.
- Measure contention before replacing `synchronized` with another abstraction.
- Clearly identify which invariants need protection.

`ReentrantLock` and other concurrency primitives remain useful, though you should not rewrite everything mechanically just because you enabled virtual threads.

## 17. Database Connection Pools Remain a Limit

A common misconception is that enabling virtual threads lets you open thousands of simultaneous database connections.

In reality, connection pools like HikariCP still enforce a physical connection limit. If an app spawns 10,000 virtual threads all waiting on a 30-connection pool, only a small number hit the database simultaneously; the rest wait.

~~~text
10,000 virtual threads
         |
         v
   HikariCP pool
   maxPoolSize = 30
         |
         v
   30 DB connections
         |
         v
      Database
~~~

This can actually be desirable: databases have bounded capacity and pools protect them. Still, excessive tasks queued waiting for connections consume heap, request state, and time.

You should:
- Size pools based on actual database capacity.
- Configure connection acquisition timeouts.
- Bound concurrency at the business layer when appropriate.
- Configure request timeouts and backpressure/bulkheads.
- Monitor pending connection requests and acquisition latency.
- Avoid spawning unbounded tasks when downstream systems are overloaded.

Virtual threads make waiting cheap, not make the awaited resource infinite.

## 18. Remote APIs, Rate Limits, and Bulkheads

Suppose a payment provider allows only 100 concurrent requests. If an app spawns 10,000 virtual threads calling that provider, the provider may return HTTP 429, time out, or suffer elevated error rates.

A semaphore can cap concurrency:

~~~java
@Component
public class PaymentGatewayAdapter {

    private final Semaphore permits = new Semaphore(100);

    public PaymentResult authorize(PaymentRequest request)
            throws InterruptedException {

        permits.acquire();
        try {
            return callProvider(request);
        } finally {
            permits.release();
        }
    }
}
~~~

This illustrates a simple bulkhead. Production code should add permit acquisition timeouts, interruption handling, metrics, and rejection policies. You can also use an established resilience library for bulkheads and rate limiting.

Avoid unbounded permit waits; if a provider slows down, queued tasks can pile up and inflate end-to-end latency.

## 19. Virtual Threads and Structured Concurrency

Virtual threads are often discussed alongside structured concurrency, yet they are separate features.

- Virtual threads provide lightweight concurrent task execution.
- Structured concurrency organizes the lifecycle of child subtasks within a parent task's scope.

Structured concurrency went through preview cycles with API changes across multiple JDK releases. Do not copy preview code from one JDK directly onto another JDK version.

In Spring Boot applications, master virtual-thread-per-task and executors first. Adopt structured concurrency only when your project's JDK supports the required API and the team accepts its lifecycle and version commitments.

Do not assume `spring.threads.virtual.enabled` turns on structured concurrency for every request.

## 20. Keeping the JVM Alive: Virtual Threads Are Daemon Threads

Virtual threads are daemon threads. Daemon threads do not prevent the JVM from exiting once no non-daemon threads remain alive.

This matters in small apps or programs that spawn virtual threads for background work. If the main thread exits and no non-daemon thread stays alive, the JVM can terminate before virtual threads finish.

~~~java
public static void main(String[] args) {
    Thread.startVirtualThread(() -> {
        performLongRunningWork();
    });
}
~~~

The program may exit before the task completes unless lifecycle management or explicit waiting keeps it alive.

The right approach depends on the application:
- Wait for tasks with `join()` or futures when needed.
- Manage executors inside a lifecycle with proper close/shutdown.
- In Spring Boot, rely on the application lifecycle and managed schedulers/executors.
- If virtual thread settings cause background work to rely solely on daemon virtual threads, consider `spring.main.keep-alive=true` per your Boot version's documentation.

Example:

~~~yaml
spring:
  main:
    keep-alive: true
  threads:
    virtual:
      enabled: true
~~~

`spring.main.keep-alive` tells Spring Boot to keep the JVM alive when necessary while using daemon virtual threads. Do not enable this blindly in every project; understand what keeps your process alive and test shutdown behavior.

## 21. Virtual Threads and Application Shutdown

Server applications have their own lifecycle, yet background tasks still require clean management:

- Are in-flight tasks awaited on shutdown?
- Can tasks respond cleanly to interruption/cancellation?
- Are executors closed when `ApplicationContext` stops?
- Do message consumers stop polling before closing resources?
- Do running scheduled tasks terminate per policy?

Virtual threads do not automatically give tasks clean shutdown lifecycles. Use Spring-managed executors/schedulers or bind custom executors into bean lifecycle callbacks.

If creating your own executor:

~~~java
try (ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor()) {
    // Submit tasks and wait for results.
}
~~~

In long-lived Spring beans, never instantiate a fresh executor per request without managing shutdown. Declare executors as lifecycle-managed beans and close them properly.

## 22. Manually Configuring a Spring Boot Task Executor

When explicit executor control is needed, configure Spring's abstractions directly.

Example using a virtual-thread-per-task executor directly:

~~~java
@Configuration(proxyBeanMethods = false)
public class VirtualTaskConfiguration {

    @Bean(destroyMethod = "close")
    ExecutorService virtualTaskExecutor() {
        return Executors.newVirtualThreadPerTaskExecutor();
    }
}
~~~

Then inject `ExecutorService` where tasks run. Keep bean names and qualifiers clear when multiple executors exist.

In Spring Framework versions providing `VirtualThreadTaskExecutor`, you can use that abstraction when compatible:

~~~java
@Bean
TaskExecutor taskExecutor() {
    return new VirtualThreadTaskExecutor("app-");
}
~~~

Confirm the class/API exists in the Spring Framework version managed by Boot. Not all older Spring Boot projects include it.

### Avoid Creating Extra Executors Without Reason

Creating an executor per bean or per request complicates lifecycle management and observability. Choose executor counts by workload type and isolation requirements, not by class count.

When relying on Boot's auto-configuration, let Boot manage the default executor unless customization is genuinely needed. When customizing, clearly document which executor serves `@Async`, scheduling, and other components.

## 23. Verifying That the Application Actually Uses Virtual Threads

Enabling the property is only a configuration step. Verify actual runtime behavior.

~~~java
log.info(
        "Thread name={}, virtual={}",
        Thread.currentThread().getName(),
        Thread.currentThread().isVirtual()
);
~~~

Log this inside:
- Controller request handlers.
- Methods annotated with `@Async`.
- Scheduled tasks.
- Custom executor tasks.

Do not check only in `main`; the main thread may be a platform thread while specific tasks execute on virtual threads.

### Thread Dumps and JFR

Modern JDK tools include virtual threads in thread dumps. Depending on JDK version and tooling, formatting differs from traditional platform thread dumps.

When investigating:
- Inspect how many virtual threads exist.
- Check where tasks are waiting.
- Look for busy or pinned carrier threads.
- Inspect lock contention.
- Combine thread dumps with JFR and application metrics.

Do not judge effectiveness solely from thread counts shown. Measure throughput, p95/p99 latency, heap, CPU, connection pools, and downstream error rates.

## 24. Impact on ThreadPoolTaskExecutor and Third-Party Libraries

Many libraries were written assuming fixed thread pools. When adopting virtual threads, verify:

- Does the library maintain its own internal thread pool?
- Does it rely on thread affinity or long-lived worker `ThreadLocal` caches?
- Does it assume repeated tasks share the same underlying thread?
- Does it size queues/concurrency from pool size?
- Does code inspect thread names to classify workers?

Virtual threads created per task are typically short-lived. `ThreadLocal` should not hold heavy caches or long-lived resources.

If a library uses a pool to bound connections or outbound calls, preserve resource-level bounds. Do not strip away resource limits simply because virtual threads are lightweight.

## 25. Virtual Threads Are Not a Universal Reactive Replacement

When choosing between Spring MVC with virtual threads and WebFlux, look at your existing ecosystem:

- If code and libraries are predominantly blocking, MVC + virtual threads can simplify concurrency.
- If the system already uses non-blocking clients, reactive streams, and end-to-end backpressure, WebFlux remains a great fit.
- If an application mixes blocking and reactive styles, manage boundaries carefully.
- Never block an event loop expecting virtual threads to help.
- Do not rewrite every `Mono`/`Flux` API into blocking code merely because JDK 21 ships virtual threads.

Both models handle high concurrency well when designed properly. Neither wins across every workload.

## 26. Observing Performance Before and After Enabling

Meaningful benchmarks require identical workloads and environmental conditions.

| Metric | What to Observe |
|---|---|
| Throughput | Requests/tasks completed per second |
| p50/p95/p99 latency | Response time distribution |
| CPU utilization | Whether workload is actually CPU-bound |
| Heap / GC | Whether task counts and contexts add memory pressure |
| Connection pool pending | Whether many tasks queue waiting for DB connections |
| HTTP client pools | Downstream connection saturation or rate limits |
| Thread pinning | Whether virtual threads hold carriers for long durations |
| Error/timeout rate | Whether higher concurrency triggers downstream failures |

A reliable load test should:
1. Use a representative workload.
2. Keep data and environment identical.
3. Run long enough to eliminate startup noise.
4. Compare both latency and throughput.
5. Verify downstream dependencies are not overloaded.
6. Test slow or failing downstream scenarios.
7. Check memory behavior and clean shutdown.

If throughput rises while p99 latency or error rates spike sharply, the change is not necessarily an improvement for users.

## 27. Common Issues When Enabling Virtual Threads

### Build Reports Virtual Thread API Not Found

Possible causes:
- Compiling with a JDK below 21.
- Build toolchain points to a different JDK than the terminal.
- Spring Framework version lacks the imported abstraction.
- Using preview APIs without proper preview flags on an older JDK.

Check:

~~~bash
java -version
./gradlew -version
mvn -version
~~~

Gradle/Maven daemons may run on a different JDK than your interactive shell. Inspect build-tool toolchain and runtime settings.

### spring.threads.virtual.enabled Has No Effect

Verify:
- Does the Spring Boot version support the property?
- Is the runtime JDK 21+?
- Are the profile and config properties loaded?
- Did a custom `TaskExecutor`/`TaskScheduler` cause auto-configuration to back off?
- Does the method actually run through the selected executor?

### @Async Still Runs on Platform Threads

Verify:
- Is `@EnableAsync` active?
- Does the call go through the Spring proxy?
- Is `@Async("customExecutor")` specified?
- What type is the custom executor?
- Which bean is picked when multiple `TaskExecutor` beans exist?

### Request Threads Remain Platform Threads

This can be normal if the servlet container uses its own executor. Check embedded server docs and request executor settings; do not infer request thread behavior from Spring's task executor.

### Database Timeouts Increase After Enabling

More concurrent tasks may compete for the connection pool or database. Bound concurrency, check pool metrics, and tune timeouts/backpressure; do not merely raise pool size without evaluating database capacity.

### CPU Usage Increases Without Latency Decreasing

The workload may be CPU-bound, or higher concurrency increased contention. Virtual threads do not add CPU cores. Profile CPU, locks, and algorithms.

### ThreadLocal or MDC Gets Lost

Execution switched threads or the executor does not propagate context. Use proper context propagation, pass values explicitly as parameters, or design explicit logging context handling.

### JVM Exits While Background Tasks Still Run

Virtual threads are daemon threads. Manage lifecycles and await tasks explicitly; consider `spring.main.keep-alive` if a Spring Boot app needs to stay alive for background daemon work.

## 28. Decision Matrix by JDK and Spring Boot Version

| Runtime / Framework | Can Virtual Threads Be Used? | Approach |
|---|---|---|
| JDK 17 + Boot 3.2+ | No standard virtual threads | Use platform threads; do not enable property expecting virtual threads |
| JDK 19/20 + matching framework | Preview | Use only if preview is acceptable and flags are properly enabled |
| JDK 21 + Boot 3.2+ | Yes | Can enable `spring.threads.virtual.enabled=true` |
| JDK 21+ + newer compatible Boot | Yes | Use Boot integration and verify custom executors/servers |
| Older Boot + JDK 21 | Java API available | Configure manually using available Spring Framework/JDK APIs; no Boot property if unsupported |
| JDK 24+ | Yes, with runtime improvements such as JEP 491 | Evaluate pinning on newer JDK, still benchmark realistic workloads |

This matrix is a general guide. When picking a concrete combination, review release notes and compatibility matrices for Spring Boot, Spring Framework, JDK, and your embedded server.

## 29. Process for Migrating an Application to Virtual Threads

Proceed step by step:

**Step 1 — Inventory runtimes.** Verify JDK versions locally, in CI, in containers, and in production. Confirm Spring Boot/Framework versions and embedded server.

**Step 2 — Classify workloads.** Identify what is blocking I/O, what is CPU-bound, and what depends on pools or rate limits.

**Step 3 — Audit existing executors.** List auto-configured and custom `TaskExecutor`/`TaskScheduler` beans alongside library and server executors.

**Step 4 — Check context propagation.** Map where transactions, security, MDC, request scope, and `ThreadLocal` are used.

**Step 5 — Enable in a test environment.** With JDK 21+ and Boot 3.2+, enable the virtual threads property in a controlled profile/environment.

**Step 6 — Verify runtime threads.** Observe actual execution points: requests, async tasks, and scheduled jobs.

**Step 7 — Validate resource limits.** Measure DB pools, HTTP client pools, semaphores, queues, and rate limits.

**Step 8 — Run representative load tests.** Compare throughput, p95/p99 latency, CPU, heap, GC, and downstream errors.

**Step 9 — Test failures and shutdown.** Exercise slow downstream calls, timeouts, cancellation, in-flight tasks during shutdown, and context propagation.

**Step 10 — Roll out with observability.** Deploy progressively across environments, monitor metrics/logs, and retain quick config rollback.

You do not need to convert every executor or task at once. Start with a well-suited blocking workload and expand based on measured evidence.

## 30. Complete Spring Boot Configuration Example

A Spring Boot 3.2+ application running on JDK 21+ can start with:

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
  main:
    keep-alive: true

logging:
  level:
    com.example: INFO
~~~

Application:

~~~java
@SpringBootApplication
@EnableAsync
@EnableScheduling
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Async service:

~~~java
@Service
public class OrderNotificationService {

    @Async
    public CompletableFuture<Void> sendNotification(OrderId orderId) {
        notificationClient.send(orderId);
        return CompletableFuture.completedFuture(null);
    }
}
~~~

Scheduled task:

~~~java
@Component
public class ExpiredOrderCleanup {

    @Scheduled(fixedDelayString = "PT1M")
    public void clean() {
        orderRepository.deleteExpiredOrders();
    }
}
~~~

This example assumes collaborators such as `notificationClient` and `orderRepository` are constructor-injected along with matching infrastructure beans. If the application configures custom executors/schedulers or uses a separate server executor, verify which components actually use virtual threads.

`spring.main.keep-alive` is only necessary when the application lifecycle risks having no non-daemon threads left to keep the JVM alive. In a typical web application server, verify actual lifecycle behavior before setting it.

## 31. Key Principles to Remember

- Virtual threads became standard in **JDK 21**; JDK 19/20 used preview.
- The `spring.threads.virtual.enabled` integration appeared in **Spring Boot 3.2** and requires JDK 21+.
- Spring Framework supplies executor/scheduler abstractions; Boot auto-configures supported components.
- Enabling the property does not convert every thread in the JVM into a virtual thread.
- `@Async` still requires async processing enabled and proxy-dispatched invocations.
- Custom executors can replace auto-configured executors.
- Servlet request threads depend on the embedded server and its configuration.
- Virtual threads help blocking I/O, not CPU-bound compute speed.
- Database connection pools, HTTP client pools, and rate limits remain bounded.
- `ThreadLocal` works per virtual thread, yet context does not automatically cross thread boundaries.
- Imperative transactions are thread-bound; switching to another virtual thread does not carry the transaction over.
- Pinning behavior depends on JDK version; JDK 24 improved monitor pinning via JEP 491.
- Virtual threads are daemon threads; manage lifecycle and shutdown explicitly.
- Benchmark realistic workloads before concluding the feature improves performance.

Virtual threads offer a more efficient execution model for blocking concurrency, yet real-world results depend on your JDK version, Spring Boot version, chosen executors, and downstream system capacity. Understanding these boundaries lets you apply virtual threads to suitable workloads while keeping transactions, security context, schedulers, and resource management predictable.
