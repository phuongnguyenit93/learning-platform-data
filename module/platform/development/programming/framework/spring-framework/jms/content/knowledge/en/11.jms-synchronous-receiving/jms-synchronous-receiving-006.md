# Impact of Synchronous Receiving on HTTP Request Threads or Task Workers

> **Topic:** Synchronous Receiving in Spring Framework JMS. `JmsTemplate.receive(...)` and `receiveAndConvert(...)` allow pulling a message directly inside the currently executing Java thread. This is simple, yet **the calling thread must wait until a message arrives, the timeout expires, or an error occurs**. When called directly inside an HTTP controller or a task executor with limited workers, the application can exhaust all processing threads even while CPU is nearly idle.

## 1. Learning objectives

After this lesson, you will be able to:
1. Distinguish **synchronous JMS receiving** from **asynchronous message processing with `@JmsListener`**.
2. Explain why calling `receive` in a controller increases HTTP response latency, holds servlet threads, and reduces throughput when the queue is empty.
3. Distinguish `receiveTimeout = 0` (indefinite wait), positive values (bounded wait), and negative values such as `-1` (no wait).
4. Evaluate the same impact inside schedulers, `@Async`, thread pools, or virtual threads.
5. Run a **Java 17 + Spring Boot 3.3.5 + ActiveMQ Artemis** example to observe HTTP 204 after a wait window and HTTP 200 when a message is received.
6. Choose among **HTTP 202 + background consumer**, **bounded polling**, and **JMS request–reply with deadline** according to business needs.
7. Identify failures involving acknowledgement, stolen messages, mismatched HTTP/JMS timeouts, capacity exhaustion, and cancellation.

**Core message:** `receiveTimeout` limits the wait duration of a single JMS receive; it **does not turn a synchronous API into an asynchronous one**, nor is it an overall deadline for the HTTP request.

## 2. What does synchronous receiving mean?

JMS supports consumer receiving through the classic API:

~~~java
// Snippet: consumer created from a Session belonging to a started Connection.
Message message = consumer.receive();        // May wait indefinitely.
Message message2 = consumer.receive(2000L);  // Waits up to ~2 seconds.
Message message3 = consumer.receiveNoWait();  // Does not wait for messages.
~~~

Each call above runs **on the current thread**. When `receive()` waits for a message, the thread cannot proceed to subsequent Java lines until the receive operation finishes.

Spring JMS wraps that logic with `JmsTemplate`:

~~~java
// Snippet: jmsTemplate already configured with ConnectionFactory and appropriate queue.
jmsTemplate.setReceiveTimeout(2_000L);
Object body = jmsTemplate.receiveAndConvert("demo.sync.receive");
~~~

`JmsTemplate` also offers `receive(queueName)` (returning raw `jakarta.jms.Message`), `receiveSelected(...)`, and `receiveSelectedAndConvert(...)` when a JMS selector is needed. `receiveAndConvert` adds a `MessageConverter.fromMessage` step after receiving. Even with a converter, **waiting for the message remains synchronous**.

Per Spring Framework, synchronous receive **blocks the calling thread**; the `receiveTimeout` property controls the wait limit in the consumer receive operation. Unconfigured, `JmsTemplate` itself defaults to **indefinite wait**. Do not confuse this with the default `receiveTimeout` of certain polling listener containers: that belongs to a **different component type**.

## 3. Three `receiveTimeout` values to remember

| `JmsTemplate.setReceiveTimeout(...)` | Meaning in Spring JMS | Result when queue is empty | Risk in HTTP |
| --- | --- | --- | --- |
| `0L` | `RECEIVE_TIMEOUT_INDEFINITE_WAIT`: calls receive waiting until a message arrives or an error occurs | May wait indefinitely | A request thread can be held for an unbounded time |
| `2_000L` | Waits up to roughly 2000 ms for a message | `receive` returns `null` on expiry; `receiveAndConvert` returns `null` | Each HTTP request can still occupy a thread for ~2 seconds |
| `-1L` or another negative number | `RECEIVE_TIMEOUT_NO_WAIT`: calls receiveNoWait | Returns `null` almost immediately if no message is available | Less waiting for messages, yet still incurs JMS/connection overhead; not an async API |

**Do not confuse:** `-1` is **no wait**, whereas `0` is **indefinite wait** in `JmsTemplate`. This is easy to get wrong because many HTTP APIs use "-1" or "0" with opposite timeout conventions.

Notes:
- The unit is **milliseconds**, not seconds.
- Expiring with no message normally returns `null`, rather than throwing a "timeout exception."
- The `receive` timeout is not a hard cap covering **connection creation, session acquisition from a pool, TLS handshake, DNS, broker reconnect, payload conversion, business logic, or HTTP response serialization**. Those steps have their own timeouts and can extend total duration.
- When the broker fails, `JmsTemplate` normally throws `org.springframework.jms.JmsException` (runtime) instead of returning `null`. Distinguish "empty queue" from "JMS service unavailable."
- Timeout configuration on a shared `JmsTemplate` bean should be set **once at initialization**. Do not raise/lower `setReceiveTimeout` per HTTP request because concurrent requests can pick up the wrong setting.

## 4. What happens if `receive` is called inside an HTTP controller?

A Spring MVC HTTP controller runs on a thread allocated by the servlet container (e.g., Tomcat). If the method calls `receiveAndConvert`, that thread must wait on the broker:

~~~text
HTTP Client
    |
    | POST /demo/receive
    v
Tomcat HTTP worker thread #17
    |
    | controller.receive()
    v
JmsTemplate.receiveAndConvert("demo.sync.receive")
    |
    |  Empty queue: waits for a message for 2 seconds
    |  [thread #17 is held; cannot handle other requests]
    |
    +--> Message present: returns data
    +--> Timed out: returns null
    +--> JMS error: throws exception
    |
    v
Controller builds HTTP response
    |
    v
HTTP Client receives 200 / 204 / 503 depending on case
~~~

While waiting on the broker, the thread's CPU usage can be low because the JVM/provider is blocked waiting on I/O. **Low CPU does not mean the system can accept more requests**: worker threads and JMS connections/sessions are still finite resources.

### 4.1. HTTP latency

Suppose:
- Controller input validation takes `10 ms`.
- The queue is empty and `receiveTimeout=2000 ms`.
- Response serialization takes around `5 ms`.

An HTTP request can take roughly `2015 ms`, excluding network, pool contention, and broker setup. This is only an **arithmetic example**, not a strict latency guarantee. If the broker delivers a message after 50 ms, the same request can finish much faster.

If the HTTP gateway timeout is `1 second` while JMS receives with a `5-second` timeout, the caller may already receive `504 Gateway Timeout` **while Java is still waiting on JMS for several more seconds**. A client closing its socket does not guarantee the provider immediately cancels a blocking JMS receive.

### 4.2. Capacity under concurrent requests

Suppose there are **20 HTTP worker threads** and every request calls receive on an empty queue, waiting `2 seconds` each:

~~~text
T=0s:
  Request #01..#20 occupy all 20 threads -> receive waits 2s
  Request #21..#40 have no free worker -> wait in HTTP queue

T≈2s:
  #01..#20 finish with 204
  #21..#40 finally execute, waiting another 2s

T≈4s:
  #21..#40 finish (assuming no upstream error/timeout)
~~~

If **all** worker capacity is consumed by empty receives with average wait time `W`, theoretical throughput for this request type is roughly:

~~~text
throughput ≈ worker count / worker hold time

20 workers / 2 seconds ≈ 10 requests/second
~~~

This is a simplified model illustrating **thread starvation**, not a real broker benchmark. Creating JMS consumers/sessions, network overhead, and response serialization make actual throughput lower. If the HTTP server must also handle login, health endpoints, and other business requests, tying up 20 threads can degrade the **entire API**.

### 4.3. When an HTTP request calls receive, it is consuming a message

A JMS `receive` on a queue is not a safe "peek" query like HTTP GET:
- The message can be **removed from the queue** and acknowledged according to the mode/session.
- A user request can steal a message meant for a background business worker.
- A user closing a browser tab or an HTTP response failing after JMS receipt **does not automatically restore** an acknowledged message.
- Two HTTP requests calling receive concurrently may compete for **two different messages** or one may time out; you cannot assume deterministic ordering across clients.

Therefore, the demo endpoint in the lab uses **HTTP POST**, not GET, for a message-consuming operation. Never run the sample against a production queue with active business consumers.

## 5. Background task threads are also affected

The issue is not limited to HTTP requests. A background job calling `receive` also occupies a thread until a message arrives or it times out:

~~~text
TaskExecutor (pool size = 4)
   |
   +-- task A -> receive() waiting
   +-- task B -> receive() waiting
   +-- task C -> receive() waiting
   +-- task D -> receive() waiting
   |
   +-- task E -> no free thread to run
~~~

### 5.1. `@Async` does not make JMS receive non-blocking

When an `@Async` method calls `jmsTemplate.receive(...)`:
- The HTTP caller may return a response sooner because it **offloaded the work to another thread**.
- Yet the **`TaskExecutor` thread still blocks** inside JMS receive.
- If the executor has 4 workers, 4 indefinite receives can force all remaining tasks to queue up.
- An unbounded executor queue can grow backlog/memory and hide capacity exhaustion; configure a bounded queue and explicit rejection policy.

`CompletableFuture.supplyAsync(() -> template.receive(...), executor)` is also **offloaded blocking I/O**, not a true asynchronous JMS receiver. `CompletableFuture.cancel(...)` or HTTP client disconnection does not guarantee every JMS provider can be interrupted and stop consuming immediately at that instant.

### 5.2. `@Scheduled` polling

A scheduler calling `receive` with an overly long timeout can delay subsequent runs. With a small scheduler thread pool, one job waiting on JMS can delay unrelated scheduled jobs. If you only need a **quick check before doing other work**, use a dedicated template with `receiveTimeout=-1` and an appropriate polling interval. Still, continuous polling incurs connection/session overhead, broker requests, and latency between polls.

**Do not use `Thread.sleep` in an infinite loop on an HTTP thread** to "wait for a message in the queue." When long-lived message consumption is needed, prefer a listener container.

### 5.3. Virtual threads and reactive web

Virtual threads can reduce the cost of holding an **OS platform thread** while blocked, but they do not eliminate timeouts, broker quotas, session ownership, JMS connection pools, business CPU processing, or ACK/transaction requirements. Pinning behavior and I/O support depend on the JVM and provider. Benchmark realistically before changing capacity assumptions.

In Spring WebFlux / event-loop architectures, calling blocking `JmsTemplate.receive` directly on an event-loop thread is especially dangerous. Offloading to a bounded worker scheduler can protect the event loop, **yet the JMS operation still blocks on that worker**. When architecture calls for a long-lived consumer, use `@JmsListener` or an appropriate adapter instead of polling JMS directly in the request path.

## 6. Runnable example: synchronous receive inside an HTTP endpoint

The example uses **Java 17 + Spring Boot 3.3.5 + Spring MVC + ActiveMQ Artemis**. Two endpoints:

- `POST /demo/send?text=hello` sends a String to a test queue.
- `POST /demo/receive` receives **one** message from the queue; if the queue is empty, it waits up to 2 seconds and returns **204 No Content**.

**Purpose:** demonstrate that the HTTP worker waits inside `receiveAndConvert`. This experiment illustrates the drawback; it is **not a recommended API architecture for production**.

### 6.1. Broker and queue

Requires an Artemis broker at `tcp://localhost:61616`, credentials `demo/demo`, and anycast queue `demo.sync.receive`. On a learning broker with auto-create queues enabled, the resource can be created automatically. For clean diagnostics, pre-provision a dedicated queue with no competing consumers. These credentials are for test environments only; use a secret manager and TLS in production.

If the broker is down, the application may still start, while send/receive will fail when accessing the broker. Do not mistake connection errors for empty-queue timeouts.

### 6.2. Project structure

~~~text
http-blocking-jms/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/
    │   ├── BlockingReceiveApplication.java
    │   └── DemoController.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'http-blocking-jms'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
spring:
  artemis:
    mode: native
    broker-url: "tcp://localhost:61616"
    user: "demo"
    password: "demo"
~~~

Spring Boot configures `ConnectionFactory` from `spring.artemis.*`. This configuration is a local demo; never commit real passwords in enterprise applications.

### 6.3. Configuring JmsTemplate with a finite timeout

`src/main/java/demo/BlockingReceiveApplication.java`:

~~~java
package demo;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class BlockingReceiveApplication {

    public static void main(String[] args) {
        SpringApplication.run(BlockingReceiveApplication.class, args);
    }

    @Bean
    JmsTemplate demoJmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setReceiveTimeout(2_000L);
        return template;
    }
}
~~~

Declaring a dedicated bean ensures the timeout is configured **before serving HTTP requests**. `JmsTemplate` is generally reusable across threads at the application layer, yet each `receiveAndConvert` call still waits for a message and uses JMS resources per the `ConnectionFactory` configuration.

### 6.4. Controller that sends a message and receives synchronously

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import java.util.concurrent.TimeUnit;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jms.JmsException;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private static final String QUEUE = "demo.sync.receive";
    private final JmsTemplate template;

    public DemoController(JmsTemplate template) {
        this.template = template;
    }

    @PostMapping("/demo/send")
    public ResponseEntity<String> send(
            @RequestParam(defaultValue = "hello") String text) {

        if (text.length() > 100) {
            return ResponseEntity.badRequest().body("TEXT_TOO_LONG");
        }

        try {
            template.convertAndSend(QUEUE, text);
            return ResponseEntity.ok("SENT");
        } catch (JmsException ex) {
            System.err.println(
                    "SEND_FAILED type=" + ex.getClass().getSimpleName());
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("JMS_UNAVAILABLE");
        }
    }

    @PostMapping("/demo/receive")
    public ResponseEntity<String> receive() {

        String threadName = Thread.currentThread().getName();
        long started = System.nanoTime();

        try {
            // This HTTP request thread itself will wait here.
            Object result = template.receiveAndConvert(QUEUE);

            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started);

            System.out.println("RECEIVE_THREAD=" + threadName
                    + " ELAPSED_MS=" + elapsedMs
                    + " EMPTY=" + (result == null));

            if (result == null) {
                return ResponseEntity.noContent().build(); // HTTP 204
            }
            if (!(result instanceof String text)) {
                throw new IllegalStateException(
                        "Expected String payload");
            }
            return ResponseEntity.ok("RECEIVED " + text); // HTTP 200

        } catch (JmsException ex) {
            System.err.println("RECEIVE_FAILED type="
                    + ex.getClass().getSimpleName());
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("JMS_UNAVAILABLE"); // HTTP 503
        }
    }
}
~~~

**Why is this a runnable program?**

- Each Java file has a single `public class` matching its filename, package `demo` is consistent, and Spring MVC + Artemis JMS dependencies provide both endpoints.
- `JmsTemplate` has `receiveTimeout=2000`, so when **the broker is running and the queue is empty**, receive does not wait indefinitely.
- The default `SimpleMessageConverter` turns a String into a `TextMessage` on send and returns a String on `receiveAndConvert`.
- `TimeUnit.NANOSECONDS.toMillis` measures elapsed time inside Java (including JMS receive and setup), without promising an exact 2000 ms.
- `Thread.currentThread().getName()` reveals that the request runs on the servlet container's HTTP worker thread.
- `POST` is used for receiving because taking a message off the queue **modifies state**, and should not be exposed as a read-only GET.
- The pattern catches `JmsException` to return 503 when JMS infrastructure fails, distinct from 204 on an empty queue. Other validation/non-JMS errors are not silently turned into "empty queue."

**Do not use this endpoint as a production API.** It omits HTTP authentication/authorization, rate limiting, retries, auditing, and business-appropriate acknowledgement design.

### 6.5. Running and testing over HTTP

In the project directory, with JDK 17+, Gradle, and the broker available:

~~~bash
gradle bootRun
~~~

**Test A: empty queue.** With no messages yet, call:

~~~bash
curl -i -X POST http://localhost:8080/demo/receive
~~~

Expected status line:

~~~text
HTTP/1.1 204
~~~

Actual output may display `HTTP/1.1 204 No Content`, depending on server/client. Latency is usually near `2 seconds` when the queue is empty; check with `curl -w` or inspect `ELAPSED_MS` in logs. On PowerShell, use `curl.exe` to avoid the legacy `curl` alias.

**Test B: message available.** Send and receive sequentially:

~~~bash
curl -i -X POST "http://localhost:8080/demo/send?text=hello"
curl -i -X POST http://localhost:8080/demo/receive
~~~

Expected HTTP bodies:

~~~text
SENT
RECEIVED hello
~~~

This receive is typically faster because a message is waiting. If the queue contains leftover messages or another consumer competes, the body may differ or time out. To keep results deterministic, use a dedicated cleaned queue, or design ID-based selectors for more complex tests.

**Test C: observing waiting threads.** Open 2 terminals and call `/demo/receive` on an empty queue in both windows nearly simultaneously. Logs will show two `RECEIVE_THREAD` lines with different thread names after the wait finishes. Concurrent requests hold multiple HTTP worker threads throughout the wait period.

### 6.6. Observing thread starvation under higher load

Test only in an isolated environment with bounded load:
1. Deliberately set a small HTTP thread pool, e.g. `server.tomcat.threads.max: 4` in a test config copy.
2. Keep the queue empty and send 8 concurrent `POST /demo/receive` HTTP requests using a bounded load-testing tool.
3. Observe the first 4 requests waiting on JMS nearly simultaneously; the remaining requests must wait for a free server worker.
4. Measure total request latency, `http.server.requests`, thread utilization, JMS connections, and queue depth.

Never launch an unbounded test that exhausts threads. Never run concurrent load tests against production. Real metrics are also influenced by thread pools, connection factories, OS scheduling, the broker, and client configuration.

## 7. Why must HTTP timeouts and JMS timeouts be coordinated?

A request usually traverses multiple layers:

~~~text
Client timeout
      |
      v
CDN / Load Balancer / Gateway timeout
      |
      v
Servlet container / HTTP worker
      |
      v
JmsTemplate.receiveTimeout
      |
      v
JMS provider: connection / session / broker
      |
      v
Message delivery, converter, business logic
~~~

If each layer configures timeouts independently, the system can behave unpredictably. For example:

| Layer | Example timeout |
| --- | --- |
| HTTP client | 1.5 seconds |
| HTTP gateway | 1.0 second |
| JMS receive | 5.0 seconds |
| JMS connection recovery | May wait even longer |

The HTTP client/gateway may time out **before** JMS receive finishes. If a message is delivered in the meantime, the consumer can take/ack the message even though the HTTP caller has already disconnected.

### 7.1. Overall deadline is not equal to `receiveTimeout`

Suppose an API must respond within `1500 ms`. You cannot simply set `receiveTimeout=1500` and assume it suffices: JMS setup, conversion, business logic, and HTTP transmission all add time. Design rule:

~~~text
remainingBudget =
    HTTP_deadline
    - pre-JMS processing time
    - conversion/response budget
    - safety margin
~~~

If you must wait for a result, wait only within the **remaining budget** and define an expiry handling policy. With a shared `JmsTemplate`, do not mutate `receiveTimeout` per request due to race conditions. Use a template with a fixed timeout for that workload class, or an API/abstraction designed for per-request timeouts.

### 7.2. HTTP cancellation does not equal JMS rollback

Under `AUTO_ACKNOWLEDGE`, a successful synchronous receive is normally already acknowledged by the JMS runtime per session rules, **without waiting for the HTTP response to be sent successfully**. If the HTTP 200 response fails to reach the client, the message may still be gone from the queue. Conversely, when ack/commit must follow a business operation, configure a dedicated transacted session/container and plan for redelivery and duplicate side effects.

Never promise "retrying the HTTP request will see the same message again" after the first receive succeeded. A queue is not a result store queryable by request ID.

## 8. Comparing three alternative architectures

### 8.1. Approach A: HTTP request directly calls `receive`

~~~text
HTTP request ──> Controller ──> JMS receive (waits) ──> HTTP response
                                   |
                             Empty queue / timeout
~~~

**Suitable for:** local admin tools, tests, experimental tasks, or very low-concurrency operations with explicit timeouts and a dedicated queue. **Unsuitable for:** high-traffic public APIs, low-latency requirements, frequently polled health checks, or workflows where multiple workers compete on the queue.

### 8.2. Approach B: HTTP accepts command; listener processes in background

~~~text
HTTP POST /jobs
      |
      +-- Validate request + create jobId
      +-- Publish persistent message to jobs.queue
      +-- HTTP 202 Accepted + jobId
                     |
                     v
              JMS Broker / Queue
                     |
                     v
        @JmsListener (dedicated worker threads)
                     |
                     +-- Process business logic
                     +-- Write status DONE / FAILED
                     +-- ACK / Commit per configuration
                     |
                     v
         HTTP GET /jobs/{jobId} to check status
~~~

**This is usually the better choice** for time-consuming work or when immediate results are unnecessary. HTTP requests do not hold workers waiting for messages. The listener container manages consumers/concurrency and drives retries/acks by policy.

Listener example (snippet; do **not** attach to the `demo.sync.receive` queue used in the lab because it would compete for messages):

~~~java
// Separate Spring bean snippet, with JMS listener infrastructure enabled.
@Component
public class JobConsumer {

    @JmsListener(destination = "demo.jobs", concurrency = "2-4")
    public void handle(String body) {
        // Validate, process business logic, and record job status.
        System.out.println("JOB_RECEIVED=" + body);
    }
}
~~~

Requires imports `org.springframework.stereotype.Component` and `org.springframework.jms.annotation.JmsListener`, plus Spring Boot JMS listener factory configuration or `@EnableJms`. `@JmsListener` **also uses worker threads**, yet they belong to a **dedicated listener pool**, not holding HTTP request threads waiting on an empty queue. Tune concurrency and transactions to broker/database capacity; do not scale concurrency unboundedly.

With the HTTP 202 pattern, also include:
- A stable job/event ID and **durable status store** for client lookup.
- Duplicate send/receive protection via idempotency keys.
- Explicit `PENDING/RUNNING/DONE/FAILED` states and business timeouts.
- DLQ/retry and safe replay mechanisms.
- Transactional outbox when database writes and JMS publishing must stay consistent.

### 8.3. Approach C: JMS request–reply with timeout

Some APIs genuinely must return a synchronous result to the caller. In that case, JMS request–reply may be used:

~~~text
HTTP request
   |
   v
Producer sends request message (correlationId, replyTo)
   |
   v
Worker consumes and processes
   |
   v
Worker sends reply to reply queue
   |
   v
HTTP caller waits for reply with matching correlationId
   |
   +-- reply arrives in time -> HTTP 200
   +-- past deadline -> HTTP 504/202 or appropriate status
~~~

This approach may require a blocking wait or a callback/state mechanism to coordinate asynchronous replies. **Timeouts and held resources still exist** if waiting directly in an HTTP worker. You must design:
- Accurate `JMSCorrelationID`/`JMSReplyTo` and selectors; do not share a reply queue where any consumer grabs arbitrary replies.
- Request and reply deadlines/TTLs; handling late replies arriving after HTTP has timed out.
- Bounded outstanding requests without creating unbounded temporary queues/consumers.
- Idempotency when clients retry and workers may redeliver.
- Alignment with gateway timeouts and resilience patterns.

If work routinely takes seconds or minutes and immediate results are not strictly required, HTTP 202 + a status endpoint is simpler and sturdier than blocking request–reply.

## 9. Polling in a background job: bounded usage

Sometimes you do not want a continuously running listener container (for example, a batch job with a fixed operating window). Then **polling on a dedicated worker** can make sense, provided you use a finite timeout or no-wait and clear start/stop scheduling.

Illustrative snippet:

~~~java
// Snippet: place inside @Configuration, requires Spring/JMS imports.
@Bean
JmsTemplate pollTemplate(ConnectionFactory factory) {
    JmsTemplate template = new JmsTemplate(factory);
    template.setReceiveTimeout(-1L);  // receiveNoWait
    return template;
}
~~~

And the polling task:

~~~java
// Snippet: @EnableScheduling must be enabled in configuration.
@Component
public class QueuePoller {

    private final JmsTemplate pollTemplate;

    public QueuePoller(@Qualifier("pollTemplate") JmsTemplate pollTemplate) {
        this.pollTemplate = pollTemplate;
    }

    @Scheduled(fixedDelay = 5_000L)
    public void poll() {
        Object msg = pollTemplate.receiveAndConvert("demo.scheduled");
        if (msg != null) {
            process(msg); // Application-defined business method.
        }
    }

    private void process(Object message) {
        System.out.println("TASK_RECEIVED=" + message);
    }
}
~~~

Requires importing `jakarta.jms.ConnectionFactory`, `org.springframework.context.annotation.Bean`, `org.springframework.stereotype.Component`, `org.springframework.beans.factory.annotation.Qualifier`, `org.springframework.scheduling.annotation.Scheduled`, and `org.springframework.jms.core.JmsTemplate`. Both blocks above are **snippets**, not a standalone runnable project.

Be careful: `receiveAndConvert` inside a scheduled method normally receives/acks the message per session settings before `process(msg)` finishes. To ensure redelivery if business processing fails, use a transacted listener container or wrap the entire poll+process in an explicit JMS transaction. Do not treat polling with `receiveTimeout=-1` as automatically reliable.

### 9.1. Calculating polling throughput

If you poll every 5 seconds while receive/convert takes 1 second and fetches one message at a time, maximum throughput is only about **1 message / 6 seconds** with single-worker `fixedDelay`, ignoring other overhead. Backlogs can grow rapidly if the queue receives dozens of messages per second.

Polling too fast (e.g., spinning without sleep) increases overhead; polling too slow increases latency. For continuous event-driven processing, a listener container is usually more appropriate.

## 10. Transactions and acknowledgement in synchronous receiving

An easy-to-miss detail when embedding `receive` in HTTP or tasks: receiving a message **does not necessarily** belong to the same transaction as subsequent business logic.

### 10.1. Auto-acknowledge

With `Session.AUTO_ACKNOWLEDGE`, a successful synchronous receive is acknowledged by the JMS runtime per contract when returning the message. If your code then calls a database and the database fails, **do not assume the message will be redelivered** merely because HTTP returned 500. That is why you should not design "HTTP consumes message then performs database side effects" without an explicit transaction design.

### 10.2. Transacted JMS session

JMS `Session.SESSION_TRANSACTED` groups receive and acknowledgement into a local transaction. On `commit`, the broker considers consumption complete; on `rollback`, the message can be redelivered. However, a local JMS transaction **does not automatically** commit alongside a JDBC database transaction.

A low-level API snippet (not standalone):

~~~java
// Snippet: connection and queue are valid, connection is started.
try (Session session =
             connection.createSession(Session.SESSION_TRANSACTED);
     MessageConsumer consumer = session.createConsumer(queue)) {

    Message message = consumer.receive(2_000L);

    if (message != null) {
        try {
            handleBusiness(message);
            session.commit();
        } catch (Exception failure) {
            session.rollback();
            throw failure;
        }
    }
}
~~~

`handleBusiness`, `connection`/`queue` variables, and `jakarta.jms.*` imports must exist in the application. Idempotency is still required for the case where **the database commits while the JMS commit outcome is uncertain**.

### 10.3. Listener containers and error handling

`@JmsListener` via `DefaultMessageListenerContainer` can be configured with `sessionTransacted=true` or an appropriate transaction manager so errors in the callback govern JMS commit/rollback. This is a major advantage over manual `receive` followed by non-transacted processing, though it still **does not automatically guarantee exactly-once effects across databases or external APIs**.

## 11. Common misconceptions and mistakes

| Claim / Action | Why it is wrong | Proper approach |
| --- | --- | --- |
| `receiveAndConvert` is non-blocking because JMS is "async" | Synchronous receive API still blocks the caller | Use `@JmsListener` or offload with a bounded pool |
| `setReceiveTimeout(0)` means no wait | Spring defines 0 as indefinite wait | `-1` for no-wait; positive number for bounded wait |
| A 2-second timeout guarantees the API replies within 2 seconds | Connection setup, broker recovery, conversion, and HTTP add time | Set end-to-end deadlines and measure real latency |
| Low CPU means HTTP is healthy | Blocked workers do not burn much CPU | Monitor active threads, queue lengths, and latency |
| `@Async` solves all blocking | Moves blocking to another pool, which can also fill up | Bounded executor, bulkhead, prefer listeners |
| Calling JMS receive on a WebFlux event loop | Blocks the event loop, stalling many unrelated requests | Offload to a separate pool or use a listener design |
| Using HTTP GET to pull messages from a JMS queue | Receiving can ack/consume messages | Use POST in demos; production uses explicit job/state APIs |
| HTTP client canceling means JMS receive cancels too | Cancellation is not reliably propagated to providers | Enforce deadlines and cleanup/late-result handling |
| Returning HTTP 500 automatically returns the JMS message | Message may already be ACKed before HTTP finishes | Design proper transactions/ACK and idempotency |
| Increasing Tomcat threads is a long-term fix | Shifts the bottleneck to memory, JMS pools, and the broker | Separate workers, measure capacity, limit concurrency |
| `@JmsListener` uses no threads | Container still runs consumer worker threads | Configure concurrency/transactions to match load |
| `receiveTimeout=-1` suffices to poll millions of messages | Every poll still carries JMS and scheduler overhead | Event-driven listeners or proper throughput design |
| Mutating timeout per request on a singleton template | Race condition across concurrent HTTP callers | Dedicated beans with immutable configuration |

## 12. Observability, monitoring, and testing

### 12.1. Key metrics

- **HTTP:** p50/p95/p99 response times, RPS, HTTP 204/503/5xx counts, gateway timeouts, active servlet threads, queued requests.
- **JMS receiver:** receive count, timeout/null count, receive duration, connection/session acquire latency, broker errors and reconnects.
- **Broker:** queue depth, oldest message age, consumer count, pending vs. delivering, expired/redelivered messages, quotas, and DLQ.
- **Background workers:** active threads, executor queue size, rejected tasks, scheduler lag, processing throughput.
- **Business:** PENDING/RUNNING/FAILED job counts, duplicate event IDs, publish-to-DONE duration, retry counts.

Do not judge health solely by CPU or seeing "RECEIVE_OK" logs. Such systems can show low CPU while RPS collapses due to HTTP thread exhaustion.

### 12.2. Recommended test matrix

| Case | Setup | What to verify |
| --- | --- | --- |
| Empty queue + `receiveTimeout=2000` | Single HTTP request | 204 after ~2 seconds, waiting thread logged |
| Queue has one String message | Send `hello` before receive | 200, body `RECEIVED hello`, typically fast response |
| Many requests, empty queue | Bounded concurrency in test environment | Active servlet threads rise; request latency may queue |
| Broker down | Stop test broker before send/receive | JMS exception / HTTP 503 per demo logic, not mistaken for 204 |
| Gateway timeout shorter than JMS timeout | Dedicated test gateway config | HTTP may time out before receive finishes; handle late results |
| Two competing consumers | One test queue, two endpoints/workers | Each message goes to at most one queue consumer per delivery; verify actual outcomes |
| Small `@Async` pool | Multiple async tasks with finite receive | Pool saturates, tasks wait/reject; HTTP may return early while tasks still block |
| `@JmsListener` with transaction | Isolated listener on test queue | Verify rollback/redelivery when callback throws |
| Receive succeeds, HTTP response lost | Simulate disconnect after JMS receive | Do not assume the same message will be redelivered; verify ACK/commit |
| Scheduled no-wait polling | Poll test queue on a schedule | Message received on poll; accept latency between intervals |

When testing failover, never run destructive commands or purge on a production broker. When testing message consumption, always use an **isolated queue** and prevent test consumers from stealing real messages.

## 13. Design decision checklist

Before placing `receive` in an HTTP endpoint or a task, answer:

- [ ] Does the caller truly need the message **within the same request**, or just confirmation that the job was accepted?
- [ ] When the queue is empty, what is the timeout? Is it smaller than the **overall HTTP budget**?
- [ ] Is there a cap on concurrent blocking requests/tasks? What is the policy when the pool is full?
- [ ] If the client cancels HTTP while JMS is still waiting, how does the system handle it?
- [ ] Is the received message ACKed before side effects finish?
- [ ] Is there a risk of an HTTP caller consuming a message meant for another worker?
- [ ] If using `@Async`, does the executor have a bounded queue, metrics, and a rejection policy?
- [ ] If using `@Scheduled`, could the polling interval/receiveTimeout cause queue backlog?
- [ ] If using listeners, are queues, concurrency, transactions, retries, DLQ, and idempotency separated and configured?
- [ ] For request–reply, are correlation IDs, reply destinations, deadlines, and late-reply handling in place?
- [ ] Were p95/p99 HTTP latencies, active threads, and queue age measured under realistic load testing?
- [ ] If work takes seconds or minutes, was HTTP 202 + job status considered instead of blocking?

### Self-check questions

1. Why can an HTTP request calling `receiveAndConvert` hold a servlet thread while CPU remains low?
2. In Spring `JmsTemplate`, how do `receiveTimeout = 0` and `receiveTimeout = -1` differ?
3. If 20 threads each wait 2 seconds on an empty queue, why can 40 concurrent HTTP requests cause some requests to take around 4 seconds?
4. Why does a 5-second JMS timeout not guarantee a 1-second gateway timeout will "cancel" the receive?
5. Does `@Async` turn JMS receive into non-blocking I/O for the worker? Why?
6. Why is an HTTP GET just to "peek at a message" on a queue not harmless like a normal read query?
7. Why does `receiveAndConvert` returning a message followed by a failed HTTP response not guarantee the message will be redelivered?
8. When should `@JmsListener` be chosen, and when is bounded scheduled polling still appropriate?
9. In the HTTP 202 pattern, how does the client check job results without holding a request waiting on JMS?
10. If producer and consumer require request–reply under a tight deadline, what metadata and resources must be managed so replies are not mixed up?

**Remember:** JMS synchronous receiving is simple for **targeted probes or strictly bounded request–reply**, yet putting `receive` on HTTP threads or small worker pools scales waiting threads with request volume. **`receiveTimeout` only limits how long one receive waits; it does not create event-driven processing.** For continuous queue processing, choose `@JmsListener` on dedicated consumer threads; for long-running tasks, consider **HTTP 202 + jobId + status store**. Always design ACK/transactions, timeouts, and idempotency independently of thread allocation.

## References

1. Spring Framework — Receiving a Message (synchronous receive blocks, asynchronous listeners): https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
2. Spring Framework — JmsTemplate API (receiveTimeout, receiveAndConvert): https://docs.spring.io/spring-framework/docs/6.1.16/javadoc-api/org/springframework/jms/core/JmsTemplate.html
3. Spring Framework — Using Spring JMS (template, containers, transaction): https://docs.spring.io/spring-framework/reference/integration/jms/using.html
4. Spring Framework — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
5. Spring Boot 3.3 — JMS and Artemis: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
6. Jakarta Messaging 3.1 Specification (MessageConsumer, acknowledge and transaction): https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
