# Impact of Slow Listeners on Requests

In Spring Framework Application Events, when an HTTP request calls `ApplicationEventPublisher.publishEvent(...)`, listeners run synchronously **by default** on the event-publishing thread if the application uses `SimpleApplicationEventMulticaster` with its default configuration. Therefore, a listener performing slow work (sending emails, calling HTTP APIs, writing files, waiting on a database, or `Thread.sleep`) can keep the request waiting until the listener finishes. This directly affects **response time, concurrency capacity, and endpoint stability**.

This lesson focuses on the synchronous case: what happens inside a request, why the system slows down under load, the impact of listener errors, and how to choose an appropriate handling strategy. Moving to asynchronous execution is discussed as a design decision, not the default behavior of Spring Events.

## 1. Where Does a Slow Listener Sit in the Request Lifecycle?

In a Spring MVC application using the standard servlet thread-per-request model, the typical path is:

~~~text
Client
  | POST /orders
  v
HTTP request thread
  -> Controller
     -> Service
        -> publisher.publishEvent(orderCreatedEvent)
           -> EventMulticaster
              -> Listener A (20 ms)
              -> Listener B (600 ms, calls external service)
              -> Listener C (30 ms)
        <- publishEvent() completes
     <- Service returns
  <- Controller creates HTTP response
Client receives response
~~~

These numbers are only a **hypothetical scenario** for illustration, not timings guaranteed by Spring. When all listeners run sequentially, the event-publishing step alone takes around `20 + 600 + 30 = 650 ms`, excluding controller, service, network, or other overhead.

Key point: `publishEvent(...)` does not automatically mean "put into a queue and return immediately." Under the default synchronous mechanism, Spring invokes matching listeners before this call returns. Consequently, code placed **after** `publishEvent(...)` in the same call stack must wait for the running listeners to finish.

`ApplicationEventPublisher` only defines event publication; the actual dispatch behavior is governed by the multicaster and application configuration. If a custom executor or `@Async` is enabled, execution timing and threads can differ.

### Distinguishing "Not Using a Listener Result" from "Not Waiting for the Listener"

A listener can return `void` and supply no value to the controller, yet still consume request time in synchronous mode. Not using a return value **does not mean** the listener runs in the background.

In default Spring behavior, listeners typically execute on the **same thread** where `publishEvent` is called, so no thread switch is needed to filter or invoke listeners. That also means the request bears the duration of slow listeners.

## 2. Illustrating Wait Time and Request Latency

Suppose a request takes 40 ms to validate input and save data, a listener performs I/O taking 600 ms, and the framework then takes 10 ms to finalize the response:

| Phase | Hypothetical duration | What is the request doing? |
| --- | ---: | --- |
| Controller and service before event | 40 ms | Business processing |
| Synchronous listener | 600 ms | Waiting for listener completion on the same call stack |
| Response finalization | 10 ms | Building and sending response |
| **Total server-side time** | **650 ms** | Excluding network between client and server |

You can approximate it as:

~~~text
Response time
 ≈ pre-publish time
 + dispatch and all synchronous listeners time
 + post-publish time
 + other HTTP / I/O overhead
~~~

If a listener occasionally takes 5 seconds due to a timeout calling an external system, the corresponding request can become abnormally slow even though the core business steps took only tens of milliseconds. This is a common cause of sharp increases in **tail latency** (p95, p99).

When there are multiple listeners, `SimpleApplicationEventMulticaster` invokes them on the publishing thread by default in an order determined by Spring; do not rely on arbitrary ordering. You can use `@Order` when order matters. However, changing order does not eliminate the total wait time if all of them still run synchronously.

## 3. Runnable Java 17+ Example with Spring Framework

This example simulates an HTTP request thread using a thread named `http-request-demo`. It uses a **real Spring Context**, a real `@EventListener`, and the default synchronous multicaster; the program **does not start an HTTP server**. This simulation lets you observe exactly where blocking occurs without configuring a Servlet container.

Create a Gradle project with the structure:

~~~text
slow-listener-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/SlowListenerRequestDemo.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'slow-listener-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'demo.SlowListenerRequestDemo'
}
~~~

File `src/main/java/demo/SlowListenerRequestDemo.java`:

~~~java
package demo;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class SlowListenerRequestDemo {

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                 new AnnotationConfigApplicationContext(DemoConfig.class)) {

            // Simulate a thread serving an HTTP request.
            Thread requestThread = new Thread(
                () -> context.getBean(RequestHandler.class).handleRequest(),
                "http-request-demo"
            );

            requestThread.start();
            requestThread.join();
        }
    }

    @Configuration
    static class DemoConfig {
        @Bean
        RequestHandler requestHandler(ApplicationEventPublisher publisher) {
            return new RequestHandler(publisher);
        }

        @Bean
        SlowListener slowListener() {
            return new SlowListener();
        }
    }

    static class OrderSubmittedEvent extends ApplicationEvent {
        OrderSubmittedEvent(Object source) {
            super(source);
        }
    }

    static class RequestHandler {
        private final ApplicationEventPublisher publisher;

        RequestHandler(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void handleRequest() {
            System.out.println(
                "request: before publishEvent (" +
                Thread.currentThread().getName() + ")"
            );

            publisher.publishEvent(new OrderSubmittedEvent(this));

            System.out.println(
                "request: after publishEvent (" +
                Thread.currentThread().getName() + ")"
            );
            System.out.println("request: ready to return response");
        }
    }

    static class SlowListener {
        @EventListener
        public void onOrderSubmitted(OrderSubmittedEvent event) {
            System.out.println(
                "listener: started (" +
                Thread.currentThread().getName() + ")"
            );

            try {
                Thread.sleep(600); // Only to simulate slow I/O.
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                    "Listener interrupted", ex
                );
            }

            System.out.println(
                "listener: finished (" +
                Thread.currentThread().getName() + ")"
            );
        }
    }
}
~~~

With JDK 17+ and Gradle installed, run from the project directory:

~~~bash
gradle run --quiet
~~~

If the project has a Gradle Wrapper, you can substitute `./gradlew run --quiet` (macOS/Linux) or `gradlew.bat run --quiet` (Windows).

**Stdout lines printed by the program in exact order** (ignoring environment logs if any):

~~~text
request: before publishEvent (http-request-demo)
listener: started (http-request-demo)
listener: finished (http-request-demo)
request: after publishEvent (http-request-demo)
request: ready to return response
~~~

Because `Thread.sleep(600)` is called inside the synchronous listener, the line "request: after publishEvent" appears only **after** the line "listener: finished". Both the request and the listener show the same thread name: `http-request-demo`. Exact elapsed time can vary due to scheduling and environment startup, yet this sequence demonstrates that the call stack is blocked. `Thread.sleep` is strictly a demonstration tool; do not use it to "simulate background work" in production code.

**Applying to a real Controller:** In Spring MVC, the thread in the example corresponds to the thread handling the controller invocation. If a controller or service publishes an event and then returns `ResponseEntity`, the response is normally created only after synchronous listeners finish or an error is handled. Placing event publication in the service layer does not make it run asynchronously.

## 4. Impact Under Load: Request Threads Held Too Long

One slow request delays that specific client. Many concurrent requests can trigger cascading effects:

1. **Holding request-serving threads:** Spring MVC on a Servlet container usually uses a bounded thread pool to accept and process requests. While a listener waits on I/O, that thread cannot serve new requests.
2. **Reduced effective throughput:** As demand rises, busy threads and queued requests grow. Endpoints that do not even use that event can suffer if they share the same resources.
3. **Elevated p95/p99:** Listeners calling external APIs often have fluctuating response times; a few slow calls can dominate tail latency.
4. **Hitting timeouts:** Clients, reverse proxies, load balancers, or the server can time out. A client-side timeout **does not automatically** stop a running Java listener; cancellation depends on cancellation design and individual components.
5. **Increased resource pressure:** If the listener also holds connections, locks, memory, CPU, or transactions, the slowdown is no longer confined to the request thread alone.

A useful estimate using arrival rate and service time: suppose there are **50 requests/second**, and each request spends an extra **0.4 seconds** just waiting for listeners; in steady state the system needs roughly `50 × 0.4 = 20` concurrent requests on average **just for this added wait**. This is a quantitative illustration, not a measurement of a specific application; reality depends on load distribution, thread limits, and implementation details.

With Spring WebFlux, the harm can be even worse if a blocking listener runs directly on an event-loop thread: a `Thread.sleep` or inappropriate synchronous I/O can block handling of many other connections. In reactive pipelines, respect the non-blocking model and offload blocking work to an appropriate scheduler. This lesson uses **synchronous Spring MVC** as its primary model.

## 5. Slow Listeners Inside Transactions Hold Resources Longer

Consider a typical scenario:

~~~java
@Transactional
public void createOrder(CreateOrderCommand command) {
    Order order = repository.save(toOrder(command));
    publisher.publishEvent(new OrderCreatedEvent(this, order.getId()));
}
~~~

This is an **illustrative snippet placed inside an existing service** (types `Order`, `CreateOrderCommand`, `OrderCreatedEvent`, `repository`, and `toOrder` belong to the application domain, not a standalone program).

If the listener is a synchronous `@EventListener`, it executes **right at publish time**, usually **before the transactional method finishes and commits**. A slow listener extends how long the transaction remains open and increases how long transaction-associated connections or locks are held. That can also affect other requests waiting on the same data.

Note the differences:

- A synchronous `@EventListener` can execute inside the current transaction when called on the same thread with an active transaction.
- `@TransactionalEventListener` binds by default to the `AFTER_COMMIT` phase, allowing execution once the transaction has committed successfully; it **does not automatically move the listener to a background thread**. In a thread-bound transaction model, the callback may still run at transaction completion on the request thread, so the request may still wait.
- By default, if no matching transaction exists, `@TransactionalEventListener` **does not execute**; you can change this with `fallbackExecution = true` if business logic genuinely requires it.
- Moving execution to post-commit separates processing timing from the transaction, yet **does not automatically lower latency** if the callback stays synchronous.

If work must occur **after data is saved successfully**, evaluate commit timing and durability of the processing mechanism rather than merely adding an annotation to cut wait time.

## 6. Listener Errors Can Also Become Request Errors

Suppose a synchronous listener calls a notification service and throws a `RuntimeException`. With the default `SimpleApplicationEventMulticaster` and no custom error handler, that exception can propagate back to `publishEvent(...)`. When that happens:

- Code lines after `publishEvent(...)` in the service/controller may not run.
- The HTTP request can return an error if the exception is not caught at the application layer.
- If the exception crosses a `@Transactional` method boundary, the transaction can roll back according to the transaction manager's rollback rules.
- Subsequent listeners may not be called if dispatch is aborted by the error; do not build business logic assuming "every listener always runs" when one listener fails.

This is beneficial when the listener is **an essential part of the synchronous business flow**: the caller knows every mandatory step must succeed before returning a result. However, for secondary emails or notifications, having an external API outage fail an order-placement endpoint may be an unwanted coupling.

If you need to catch errors inside a listener, define clear retry mechanisms, failure recording, and business states. "Swallowing exceptions" just to make a request succeed can silently drop work without making the system more reliable.

## 7. Choosing a Solution Based on Business Requirements

| Approach | Does the request wait? | Suitable use cases | Things to watch out for |
| --- | --- | --- | --- |
| Default synchronous `@EventListener` | Yes, until the listener finishes | Validation, mandatory rule checks, processing that must return errors with the request | Latency, transactions, exceptions, time limits |
| `@Async` on `@EventListener` with async support enabled | Usually does not wait for **work handed to the executor**, though still pays submission overhead | Secondary tasks where post-response completion is acceptable | Bounded executor, queue, rejections, background errors, lost work on process crash |
| Multicaster with `TaskExecutor` | Depends on listener type and async capability | Centralized control over dispatch strategy | Listeners that do not support async can still run synchronously; configure carefully |
| `@TransactionalEventListener(phase = AFTER_COMMIT)` | Can still wait | Processing only after successful commit | **Not automatically async**; transaction callbacks have distinct semantics |
| Queue/broker with outbox | Request waits only for durable work recording, not worker processing | Emails, system integrations, tasks requiring durable execution after commit | Retries, idempotency, monitoring, eventual consistency |

### When Using `@Async`: Configure an Executor and Error Handling

Spring supports combining `@Async` with `@EventListener`, provided async support is enabled, such as with `@EnableAsync`. Example bounded executor configuration for **an existing Spring application** (this is an integration snippet, not a standalone runnable program):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class EventExecutorConfig {

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("app-event-");
        executor.initialize();
        return executor;
    }
}
~~~

When the listener is managed as a Spring bean, the listener method can declare:

~~~java
@Async("eventExecutor")
@EventListener
public void onOrderSubmitted(OrderSubmittedEvent event) {
    processNotification(event);
}
~~~

The method snippet above **illustrates where to place annotations in an existing business listener**; `OrderSubmittedEvent` and `processNotification(...)` are parts of the application itself, so it is not a standalone Java example. If you want to try this with the section 3 demo, you can convert the listener class into an async bean, keep `Thread.sleep(600)` in the method body, and observe that log ordering is no longer guaranteed as before.

Properties to understand when moving to asynchronous execution:

- Once accepted by the executor, the listener usually runs on another thread and the request does not wait for all I/O inside the listener.
- **Executors are not infinite.** When both the pool and queue are full, submissions may be rejected; if `CallerRunsPolicy` is used, work can fall back onto the request thread and still slow the request. Set an explicit overload policy rather than assuming every publish is fast.
- Exceptions occurring **inside an async `void` listener** do not automatically propagate back to the already returned request; you need logging, an `AsyncUncaughtExceptionHandler`, retries, or failure tracking.
- Transactions, `SecurityContext`, MDC/trace context, or `ThreadLocal`-based values **are not automatically** copied to background threads. When needed, use proper context propagation and pass immutable data or IDs in the event.
- Do not pass lazy JPA entities or request/transaction-bound objects to another thread and assume those resources remain valid. Prefer passing IDs or immutable data snapshots and re-querying as needed.
- `@Async` using an in-process thread pool **does not guarantee work durability** if the process stops right after receiving the event. Critical tasks require durable storage and retries.

### When Tasks Must Reliably Execute After Commit

For example, sending a notification when an order is created without losing it if the service restarts: write the order and an **outbox record** in the same transaction, then have a worker read the outbox to send notifications. The worker must handle retries, status updates, and duplicate prevention (idempotency). Queues/brokers decouple work from the request, but the requirement "processed reliably" must be backed by real acknowledgments rather than merely calling `publishEvent`.

## 8. Measuring Performance and Real Behavior

Do not guess from annotations or inspect only controller logs; measure the exact boundaries:

1. Place timers around `publishEvent(...)` to see how much time goes to dispatch and synchronous listeners. Compare against total controller/server time and client-perceived request latency.
2. Log thread names in the publisher and listeners while debugging to verify same-thread vs. different-thread execution. With async, log order is no longer reliable proof of success or failure.
3. Test fast listeners, ~600 ms slow listeners, and listeners throwing exceptions, then verify log order, HTTP status codes, and rollbacks match the business design.
4. Load test at controlled concurrency; monitor p50/p95/p99, busy threads, queues, connection pools, and timeout counts. One slow request is insufficient to prove system-wide throughput limits.
5. When using an executor, monitor active threads, queue depth, rejected tasks, submit-to-execute delay, and failure rates; define a clear backpressure policy.
6. For external I/O, configure connect/read timeouts, bounded retries, and circuit breakers where appropriate. Without timeouts, a listener can block requests far too long.

Spring Framework does not automatically create separate observations for each `@EventListener` invocation to split listener cost out from the request. When precise metrics are needed, instrument listener boundaries with dedicated metrics/traces or use a profiler.

## 9. Common Confusions

- **"Using events decouples the request."** Events decouple the publisher from listeners in source code dependencies; dispatch can still be synchronous.
- **"The listener returns `void`, so it doesn't block."** A `void` method still runs and takes time; the caller waits for it to finish in synchronous mode.
- **"Adding `@TransactionalEventListener` makes the request return immediately."** This annotation schedules timing around transactions; it does not create background threads by itself.
- **"Enabling `@Async` means events can never be lost."** In-memory tasks can be lost when the application stops; executors can also overload.
- **"If the client times out, the listener stops automatically."** Cancellation depends on technology, context, and listener implementation; there is no universal guarantee.
- **"Caching the listener list avoids slow listeners."** Caching only reduces the overhead of finding matching listeners. Every event still calls the listeners, and slow work remains slow.

**Rule of thumb:** If a listener's outcome is a mandatory condition for confirming request success, consider synchronous execution with timeouts and monitoring. If it is independent post-processing (emails, asynchronous auditing, external system sync), consider `@Async` or a queue/outbox according to required reliability. Base the decision on transaction boundaries, durability requirements, and actual latency targets.

### References

- [Spring Framework — Application Events, synchronous and asynchronous listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Observability for Application Events](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Framework — Task Execution and `@Async`](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Maven Central — org.springframework:spring-context](https://central.sonatype.com/artifact/org.springframework/spring-context/6.2.19)