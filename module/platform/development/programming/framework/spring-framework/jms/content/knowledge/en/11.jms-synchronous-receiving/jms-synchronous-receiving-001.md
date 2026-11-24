# receive and the Message-Waiting Thread in Spring JMS

**Topic:** Synchronous Receiving (Spring Framework – JMS). This lesson focuses on `receive`, thread blocking while waiting for a message, timeouts, `null` results, connection/session management, transactions, polling limitations, and how to choose `@JmsListener`. Examples use Java 17+, Spring Framework 6.x / Spring Boot 3.x, Jakarta Messaging, and the Apache ActiveMQ Artemis broker.

**Key takeaway:** `JmsTemplate.receive(...)` **does not register a callback for Spring to invoke later**. It makes the **calling thread** wait until a message arrives, a timeout expires, or an error/resource-closing condition occurs. If called from an HTTP request thread with an infinite timeout, that request thread can be held for a very long time. Conversely, with `@JmsListener`, Spring operates a listener container and dedicated message-receiving threads.

## 1. What does synchronous receiving mean?

~~~text
                         [JMS broker]
                              │
                              │ message available?
                              ▼
[Java worker thread] ── receive("jobs.queue") ──► [WAIT FOR MESSAGE]
                              │                         │
                              │     message / timeout    │
                              ◄─────────────────────────┘
                              │
                              ▼
                    Code after receive() continues

During wait: the thread calling receive() does not execute subsequent code.
Other threads: can continue running if threads and resources remain.
~~~

Synchronous receiving does not mean JMS is limited to a single consumer, nor does it mean the JVM continuously uses CPU to poll the broker. The provider typically waits using network I/O or synchronization primitives, but the **thread, session, and consumer** attached to the call still require resources. `Thread.State.BLOCKED` in Java also has the narrow meaning of waiting for a monitor lock; a blocking receive may show `WAITING`, `TIMED_WAITING`, or `RUNNABLE` depending on the implementation path. Therefore, thread dumps must be read by **call stack**, not just by state name.

**Comparing the two receiving styles:**

| Criterion | `receive` | `@JmsListener` |
| --- | --- | --- |
| Who initiates receiving? | Application code calls the method at a specific point | Spring's listener container |
| Which thread waits? | The thread calling `receive` | Worker thread managed by the container |
| Return value | `Message`/Object or `null` | Callback method processes the message when delivered |
| When no message is available | May wait until timeout or indefinitely | Container continues operating according to polling/recovery configuration |
| Resource management | `JmsTemplate` opens/closes per call; app manages the receive loop itself | Container manages consumer lifecycle, concurrency, and restart |
| Suitable use cases | Fetching a message on demand, administrative tools, bounded poll | Workers consuming messages continuously |

This difference is about **control over when to receive**, not "listeners do not use threads." A `@JmsListener` callback still runs on a thread and can be blocked if DB/HTTP processing is slow.

## 2. Three ways to receive in the classic JMS API

`jakarta.jms.MessageConsumer` provides:

| API | How long does it wait? | Returns |
| --- | --- | --- |
| `receive()` | Indefinitely; ends when a message arrives, closed concurrently, or on error | `Message`, may be `null` when consumer closes |
| `receive(long timeout)` | `timeout > 0`: waits up to roughly the specified milliseconds; `timeout == 0`: waits indefinitely | `Message` or `null` if timeout/consumer closes |
| `receiveNoWait()` | Fetches immediately if a message is already available, does not wait for future messages | `Message` or `null` |

~~~java
Message message1 = consumer.receive();        // Wait until a message arrives
Message message2 = consumer.receive(2_000L);  // Up to about 2 seconds
Message message3 = consumer.receiveNoWait();  // Do not wait for new messages
~~~

The snippet above requires a valid `MessageConsumer consumer`. Each call can **consume a real message**. This is not a "peek" operation to inspect without altering delivery state. If you want to observe messages in a queue without taking them for processing, consider `QueueBrowser` or broker management metrics, rather than calling receive and hoping the message stays there.

**Common trap:** `receive(0)` does **not** mean "return immediately." In JMS, `0` means **wait indefinitely**. To avoid waiting, call `receiveNoWait()`.

## 3. Classic JMS requires Connection.start() to receive

Before a classic `MessageConsumer` begins delivery, `Connection.start()` must be called. Without calling it, `receive(timeout)` can time out even while the broker holds messages; `receive()` can wait indefinitely.

~~~java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;
import jakarta.jms.Session;

public final class OneShotReceiver {

    private final ConnectionFactory connectionFactory;

    public OneShotReceiver(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public Message receiveOnce() throws JMSException {
        try (Connection connection = connectionFactory.createConnection();
             Session session = connection.createSession(
                     false, Session.AUTO_ACKNOWLEDGE)) {

            Queue queue = session.createQueue("demo.sync.receive");

            try (MessageConsumer consumer = session.createConsumer(queue)) {
                connection.start(); // Start JMS delivery
                return consumer.receive(3_000L);
            }
        }
    }
}
~~~

The class above can compile in a Java 17 project with the JMS API and a compatible provider client added; it **has no `main`**. To run, you need a `ConnectionFactory` bean/instance pointing to a broker, a valid queue, and receive permissions. Creating/closing a physical connection per receive is only suitable for simple examples; systems under load should use caching/pooling and proper lifecycle management mechanisms.

`Connection.stop()` pauses delivery, does not prevent producers from sending messages, and **does not stop the receive timeout clock**: a waiting receive can expire and return `null` while the connection is stopped. With the **simplified JMS API** (`JMSContext`/`JMSConsumer`), the context defaults to auto-start when creating a consumer unless you call `setAutoStart(false)`; that does not apply to classic `Connection`.

**Where does Spring help?** `JmsTemplate.receive` manages the connection/session/consumer and starts delivery appropriately. You do not need to obtain the connection yourself to call `start()` in template-based receiving code.

## 4. Spring JmsTemplate.receive and receiveAndConvert

`org.springframework.jms.core.JmsTemplate` can receive a JMS Message or convert the body:

~~~java
// jmsTemplate is a Spring bean configured with ConnectionFactory.
jakarta.jms.Message raw =
        jmsTemplate.receive("orders.queue");

Object payload =
        jmsTemplate.receiveAndConvert("orders.queue");
~~~

Differences:

- `receive` returns **`jakarta.jms.Message`** so you can read the body, JMS headers, message properties, and redelivery metadata.
- `receiveAndConvert` calls `MessageConverter.fromMessage` to convert the JMS Message into a Java object. With the default `SimpleMessageConverter`, `TextMessage` typically becomes `String`, `BytesMessage` becomes `byte[]`, and `MapMessage` becomes `Map`.
- Both **block the thread**; `convert` is only a conversion step after receive, not asynchronous receiving.
- Both can return `null` when no message arrives within the wait period. Provider/converter errors result in exceptions, not null.

Some important overloads:

| API | Meaning |
| --- | --- |
| `receive()` | Receive from the **default destination** configured on the template |
| `receive(String destinationName)` | Receive directly by destination name |
| `receive(Destination destination)` | Receive from a JMS Destination object |
| `receiveAndConvert()` | Receive then convert to a Java object, from the default destination |
| `receiveAndConvert(String destinationName)` | Receive then convert to a Java object |
| `receiveSelected(String destinationName, String selector)` | Receive a message matching a JMS selector |
| `receiveSelectedAndConvert(String destinationName, String selector)` | Receive with selector then convert |

If you call an overload without a destination when neither `setDefaultDestinationName` nor `setDefaultDestination` is configured, the template may throw an error because it does not know where to receive from. A string name is resolved by `DestinationResolver`; the default is a queue, unless `pubSubDomain=true` or an appropriate resolver for topics is configured.

**Be careful with consecutive read examples:**

~~~java
Message first = jmsTemplate.receive("orders.queue");
Object second = jmsTemplate.receiveAndConvert("orders.queue");
~~~

The two calls can fetch **two different messages** from the same queue. They are not two ways to get metadata and body of the *same* message. If you need both headers and body of one message, receive the raw Message **once**, then process that object in the same scope.

## 5. receiveTimeout in JmsTemplate: 0, positive number, -1

Spring sets the timeout on the template in **milliseconds**:

~~~java
JmsTemplate receiver = new JmsTemplate(connectionFactory);

// Wait up to about 2 seconds.
receiver.setReceiveTimeout(2_000L);

// Do not wait for new messages.
receiver.setReceiveTimeout(-1L);

// Wait indefinitely.
receiver.setReceiveTimeout(0L);
~~~

| Value on `JmsTemplate` | Receiving behavior |
| --- | --- |
| `0L` | **Indefinite** — corresponds to `RECEIVE_TIMEOUT_INDEFINITE_WAIT`, the default |
| `>0L` | Wait until a message arrives or timeout expires |
| `-1L` | **No wait** — corresponds to `RECEIVE_TIMEOUT_NO_WAIT` |
| Other negative numbers | Spring also treats them as no-wait; prefer constants for clarity |

Two constants from `org.springframework.jms.support.destination.JmsDestinationAccessor`:

~~~java
JmsDestinationAccessor.RECEIVE_TIMEOUT_INDEFINITE_WAIT // 0L
JmsDestinationAccessor.RECEIVE_TIMEOUT_NO_WAIT          // -1L
~~~

**Important:** `setReceiveTimeout(0)` is **not** a 0-millisecond limit; it is **indefinite wait**. The same applies to classic JMS: `consumer.receive(0)` waits indefinitely. To check immediately, Spring uses `-1` while classic JMS uses `receiveNoWait()`.

The template's timeout is a **shared property** across receive calls on that instance. Do not repeatedly mutate `setReceiveTimeout` on a singleton `JmsTemplate` used by multiple threads, because changing configuration can affect other calls. When different policies are needed, create **separate beans/templates** or choose an API with explicit timeout in a controlled scope.

In Spring Boot 3.x, the `spring.jms.template.receive-timeout` property can configure the Boot auto-configured template, for example:

~~~yaml
spring:
  jms:
    template:
      receive-timeout: 3s
~~~

**Do not confuse** `spring.jms.template.receive-timeout` with `spring.jms.listener.receive-timeout`. The listener property is for the message listener container and has a different meaning and lifecycle. If you manually construct a new `JmsTemplate` with `new`, the properties of Boot's auto-configured template bean **do not automatically** apply to your manually created instance.

## 6. Timeout returns null, but null does not prove the queue is empty

~~~java
JmsTemplate receiver = new JmsTemplate(connectionFactory);
receiver.setReceiveTimeout(1_000L);

Message message = receiver.receive("jobs.queue");
if (message == null) {
    System.out.println("No message in this receive attempt");
} else {
    System.out.println("Received JMSMessageID="
            + message.getJMSMessageID());
}
~~~

The code above is a snippet inside a Spring method with a configured `ConnectionFactory`. When receive fails to catch a message within the timeout, `null` is a **normal result**, not a `JmsException`.

`null` can occur because:
- The queue has no message at the attempt time, even if a producer is about to send one right afterward.
- Another consumer picked up the message first.
- The message is in-flight or inside another consumer's transacted session.
- The selector did not match (if using `receiveSelected`).
- Wrong destination, different broker routing, or topic subscription did not exist yet.
- Delivery delay, TTL/expiry, or broker policy affected delivery timing.
- Classic connection is stopped, or the receiver is not receiving deliveries in an appropriate state.

Therefore, "`receive` returned null" only means **"no message was received in this attempt."** It does not mean "the queue across the entire system is definitely empty," nor does it mean "all business work is finished."

### JMS receive timeout is not an end-to-end operation timeout

`setReceiveTimeout(3_000)` limits the time spent **waiting for a message** in the receive step. It does not necessarily cover DNS, TCP connect, TLS, authentication, session/consumer creation, recovery, or I/O errors. A system with a 5-second HTTP deadline needs separate budget for connection setup and end-to-end completion, not just `receiveTimeout=5s`.

## 7. While a thread waits, other threads continue running

~~~text
Thread A - Worker                    Thread B - Producer
    |
    +-- receive("orders.queue")
    |        ... waiting ...
    |                                  +-- send(OrderCreated)
    |                                  +-- send returns
    |
    +-- receive returns Message
    +-- parse message
    +-- update business data
    +-- next statement
~~~

Thread A pauses at `receive` and does not advance to `parse` and `update` until a result arrives. Thread B and other threads can still send messages or work independently.

Do not equate "blocking" with "busy-wait": the JMS implementation may not consume significant CPU while waiting, yet the **number of threads, sessions, consumers, and connections in use** still matters. If 200 concurrent HTTP requests all call receive and wait 10 seconds, up to 200 request paths may be holding corresponding threads/resources. When exceeding thread pool limits or broker capacity, new requests may be queued even if CPU usage is still low.

If the queue already has a message, `receive` can return **almost immediately**. It is still a blocking API because **it can wait** when no message is available.

## 8. Runnable Spring Boot 3.x example: one thread waits, another sends

This Java 17 example illustrates a **thread waiting** for a message on a test queue, the main thread sending a message afterward, and then retrieving the result. It uses **Spring Boot 3.5.0** to pin a specific release version rather than defaulting to latest. It requires an external Artemis broker running at `tcp://localhost:61616`, a user with send/receive permissions, and the `demo.sync.receive` queue existing or allowed to auto-create.

### 8.1. Gradle dependencies

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

repositories { mavenCentral() }

java {
    toolchain { languageVersion = JavaLanguageVersion.of(17) }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'spring-sync-receive'
~~~

`src/main/resources/application.yaml`:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
  jms:
    pub-sub-domain: false
~~~

The password should be provided via the `SPRING_ARTEMIS_PASSWORD` environment variable or a secret manager, not committed to Git. If the broker uses different credentials or TCP/TLS endpoints, adjust the configuration accordingly. Client dependencies do not automatically start an external broker.

### 8.2. One complete Java file

`src/main/java/example/jmssync/SyncReceiveApplication.java`:

~~~java
package example.jmssync;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class SyncReceiveApplication {

    public static void main(String[] args) {
        SpringApplication.run(SyncReceiveApplication.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(
            ConnectionFactory connectionFactory,
            JmsTemplate sender) {

        return args -> {
            JmsTemplate receiver = new JmsTemplate(connectionFactory);
            receiver.setReceiveTimeout(3_000L);

            CountDownLatch ready = new CountDownLatch(1);
            ExecutorService executor = Executors.newSingleThreadExecutor();

            try {
                Future<String> result = executor.submit(() -> {
                    System.out.println("WAIT_START");
                    ready.countDown();

                    Message message =
                            receiver.receive("demo.sync.receive");

                    if (message == null) {
                        return "RECEIVE_TIMEOUT";
                    }
                    if (message instanceof TextMessage text) {
                        return "RECEIVED:" + text.getText();
                    }
                    return "RECEIVED_OTHER_MESSAGE_TYPE";
                });

                if (!ready.await(2L, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Receiver worker did not start");
                }

                Thread.sleep(300L); // For demo purposes only.
                sender.convertAndSend("demo.sync.receive", "hello");
                System.out.println("SEND_RETURNED");

                System.out.println(result.get(6L, TimeUnit.SECONDS));
            } finally {
                executor.shutdownNow();
            }
        };
    }
}
~~~

### 8.3. Run command and output

If the project has the Gradle wrapper and the broker is ready:

~~~bash
./gradlew bootRun
~~~

The business output lines observable when the test queue is initially empty and there are no competing consumers:

~~~text
WAIT_START
SEND_RETURNED
RECEIVED:hello
~~~

**The output above is only an expected scenario**, not fixed complete stdout. There will be other Spring/provider logs; if the queue already contains a message, the worker may pick up the old message; if the broker is unreachable or authentication fails, an exception may be thrown; if no message is delivered within 3 seconds, it may return `RECEIVE_TIMEOUT`. The worker thread may **receive the message before** the producer prints `SEND_RETURNED`, yet `Future.get` in the runner causes the `RECEIVED:...` line to be **printed after** `SEND_RETURNED` in the example.

`CountDownLatch` here only confirms the worker is about to call receive, **not proving** the call has already started waiting at the broker; `Thread.sleep(300)` only increases observability. To accurately test the waiting state, use broker tests, timestamps, tracing, or appropriate network control tools.

**Lifecycle note:** `executor.shutdownNow()` sends an interrupt, which is not guaranteed to make a blocked JMS client stop immediately across all providers. It is `receiver.setReceiveTimeout(3_000L)` that keeps the receive duration bounded. This example is for learning only; do not use a raw executor inside `ApplicationRunner` to implement production workers.

## 9. receiveAndConvert and MessageConverter

~~~java
JmsTemplate receiver = new JmsTemplate(connectionFactory);
receiver.setReceiveTimeout(2_000L);

Object payload = receiver.receiveAndConvert("orders.queue");
if (payload == null) {
    System.out.println("Receive timed out or returned no payload");
} else if (payload instanceof String text) {
    System.out.println("Text payload: " + text);
} else {
    System.out.println("Type: " + payload.getClass().getName());
}
~~~

The default `SimpleMessageConverter` converts a `TextMessage` to `String`, `BytesMessage` to a byte array, and `MapMessage` to `Map`. If the app has a custom JSON converter, the result may be a POJO and require compatible schema/type metadata. Conversion errors can throw `MessageConversionException`; do not use `receiveAndConvert` assuming you will always get a `String`.

If you need `JMSMessageID`, `JMSTimestamp`, `JMSRedelivered`, `JMSXDeliveryCount`, or custom properties for tracing/idempotency, you should usually receive with `receive` and read the metadata from the raw `jakarta.jms.Message`. `receiveAndConvert` focuses on the payload and does not automatically expose headers in the returned Java value.

## 10. Polling: do not use no-wait in a hot loop

A loop like the following is very easy to get wrong:

~~~java
while (running.get()) {
    Message message = noWaitTemplate.receive("jobs.queue");
    if (message != null) {
        process(message);
    }
}
~~~

This is a snippet, assuming `running` is a state flag and `process` is written by the app. If the template is in `setReceiveTimeout(-1)` mode and the queue is empty, the loop executes receive nonstop, which can waste CPU, cause connection/session churn, and load the broker.

An approach with **less polling churn**:

~~~java
JmsTemplate receiver = new JmsTemplate(connectionFactory);
receiver.setReceiveTimeout(1_000L);

while (running.get()) {
    Message message = receiver.receive("jobs.queue");
    if (message == null) {
        continue; // Wait window expired, check stop flag.
    }
    process(message);
}
~~~

This is also only **illustrative**: it lacks retry, shutdown, error handling, transactional ACK, thread ownership, or idempotency. Operationally, a listener container that keeps long-lived consumers and manages recovery/concurrency is usually better than looping `JmsTemplate.receive` yourself.

**Do not replace with Thread.sleep:**

~~~java
Thread.sleep(5_000L);
Message message = noWaitTemplate.receive("jobs.queue");
~~~

`sleep` waits for **time**, not for **a message to arrive**. If a message arrives after 10 ms, you still sleep nearly 5 seconds. `receive(5_000)` can return **early as soon as a message arrives**, making long polling more responsive. `sleep/backoff` is only useful for intentionally reducing load when polling is necessary, not as a substitute for receive.

## 11. HTTP requests waiting on JMS: must have a clear deadline

~~~java
// Illustrative snippet; missing imports, controller, and convertToResponse.
@GetMapping("/jobs/next")
public ResponseEntity<String> nextJob() {
    Message message = jmsTemplate.receive("jobs.queue");
    return convertToResponse(message);
}
~~~

If `JmsTemplate` has the default `receiveTimeout` of `0` and there is no message, **the HTTP request thread can wait indefinitely**. Risks include exhausting the servlet thread pool, gateway timeouts while the server is still waiting, user retries causing competing message consumption, and held connections/sessions.

With HTTP long polling, you need to:
1. Set a **positive** `receiveTimeout` appropriate for the request SLA budget, subtracting time for connection setup, serialization, DB, and network.
2. Limit the number of concurrently waiting requests/consumers and manage executors with backpressure; do not spawn unbounded raw threads.
3. Handle `null` as a "no job within the wait window" status per the API contract, rather than as a false broker error.
4. When a client cancels the request, do not assume an interrupt will stop the JMS receive immediately.
5. Define ACK/transaction semantics for job delivery; if a message is received but the HTTP reply is lost, the job may be removed from the queue without the client knowing.
6. Use appropriate idempotency/visibility contracts if the queue is used as a task distribution system.

**Recommendation:** If an HTTP request only needs to enqueue background work, return `202 Accepted` with an operation ID after durably recording the request; use `@JmsListener` for the worker and an outcome store for result lookup. Do not hold a request thread waiting for a message just to simulate "synchronous" processing.

## 12. Executor, Future, and interrupt: moves the thread, does not make it non-blocking

~~~text
Caller thread                           Executor worker
    │                                         │
    ├─ executor.submit(() -> receive()) ────► │ receive() blocks
    │                                         │
    ├─ do other work                          │ ...waiting...
    │                                         │
    └─ future.get() ─────────────────────────►│ result after receive()
~~~

Offloading receive to an `ExecutorService` lets the caller thread do other work **if it does not immediately wait on the Future**. However, an executor worker still waits. If the executor has 10 threads and all 10 are blocked in receive, the 11th task may have to wait in the queue. Do not treat this approach as a non-blocking JMS API.

`Future.get(2, TimeUnit.SECONDS)` bounds **how long the caller waits on the Future**, not directly the JMS receive itself. `Future.cancel(true)` requests an interrupt, but the JMS provider or network stack may not respond immediately, so a finite timeout on receive itself and a verified shutdown mechanism are still required.

**Observing the thread pool:** measure active waiting receives, p95/p99 latency, executor queue length, connection/session count, broker consumer count, and success/timeout/error rates. Low CPU does not mean the system is unblocked if many threads are waiting.

## 13. Selector: waiting for a matching message, not just any message

~~~java
JmsTemplate receiver = new JmsTemplate(connectionFactory);
receiver.setReceiveTimeout(1_000L);

Message message = receiver.receiveSelected(
        "orders.queue",
        "eventType = 'OrderCreated' AND priorityLevel >= 2"
);
~~~

The fields `eventType` and `priorityLevel` must be JMS **properties** set by the producer with the right types. Selectors evaluate headers/properties using the JMS selector language and **do not automatically parse a JSON body**. If no message satisfies the condition during the wait period, `receiveSelected` can return null even if the broker holds many other messages.

JMS message selectors are also not a non-consuming queue history scan tool. The consumer created by receive still has receive/ACK semantics. For the provider-assigned `JMSXDeliveryCount` property at delivery time, JMS does not guarantee selectors work the way you might expect; avoid using it to replace a business retry policy.

### Queue and Topic behave differently

In a queue, consumers can **compete** to receive a single message per delivery. Do not conclude a queue is empty just because one specific consumer received null.

In a topic, a non-durable subscription only receives messages while the subscription is active; a short-lived consumer created by `JmsTemplate.receive` does not automatically become a durable subscriber preserving history. To get durable subscriptions, you must configure identity/lifecycle properly. Merely naming a destination ending in `.topic` does not make it a topic if the template's `pubSubDomain` is still configured for queues.

## 14. ACK and transaction: receiving successfully is not the same as processing business logic successfully

This is a critical risk when using receive to pull jobs:

~~~java
Message message = jmsTemplate.receive("billing.commands");
if (message != null) {
    writeInvoiceToDatabase(message);
}
~~~

`writeInvoiceToDatabase` is a hypothetical business function, not provided by Spring. With the default **non-transacted** `JmsTemplate` using `AUTO_ACKNOWLEDGE`, the JMS receive may be acknowledged when `receive` returns. If the DB insert fails **afterward**, the JMS broker may have already marked the message as consumed and **will not automatically redeliver it**.

**Is enabling sessionTransacted enough?** Not necessarily. If a `JmsTemplate` has `setSessionTransacted(true)` without a **transaction scope wrapping the business logic**, the template may commit the local JMS receive during the receive/cleanup operation itself before subsequent DB code runs. You need to design **transaction boundaries**.

### An intentional local JMS transaction

~~~java
@Bean
JmsTransactionManager jmsTransactionManager(ConnectionFactory cf) {
    return new JmsTransactionManager(cf);
}
~~~

Then:

~~~java
@Service
class InvoicePoller {
    private final JmsTemplate jms;
    private final InvoiceService invoices;

    InvoicePoller(JmsTemplate jms, InvoiceService invoices) {
        this.jms = jms;
        this.invoices = invoices;
    }

    @Transactional(transactionManager = "jmsTransactionManager")
    public void receiveAndProcessOnce() {
        Message msg = jms.receive("billing.commands");
        if (msg == null) {
            return;
        }
        invoices.process(msg);
    }
}
~~~

The two blocks above are **Spring snippets**: they require imports, enclosing classes, the `InvoiceService` bean, and the same `ConnectionFactory` for both the manager and the template. Method calls must go through the **Spring proxy**, not self-invocation within the same class; otherwise, `@Transactional` may have no effect. With a local JMS transaction, an appropriate exception in the handler causes the receive to roll back so the broker can redeliver.

**Important limitation:** `JmsTransactionManager` manages the **JMS resource**, and does not automatically enlist PostgreSQL/MySQL/HTTP in the same transaction. If the DB commits but the JMS commit/ACK is lost due to a crash, the message may arrive again. You need an **idempotent consumer** with a stable business `eventId`, a DB unique constraint/transaction, or external system idempotency. Do not infer exactly-once business effects from `sessionTransacted=true` alone.

### CLIENT_ACKNOWLEDGE does not ack an arbitrary single object only

In classic JMS `CLIENT_ACKNOWLEDGE`, `message.acknowledge()` can acknowledge consumed messages across the entire **Session**, not just one individual message. Do not use that mode to "ack individual jobs independently" without understanding session ownership and scope. `JmsTemplate` manages session lifecycle; if complex ACK/recovery is needed, use an appropriate transaction/container design or a lower-level API with explicit lifecycle.

## 15. When should you use @JmsListener instead of receive?

For a worker that continuously receives jobs, use:

~~~java
@Component
class OrderWorker {
    @JmsListener(destination = "jobs.queue")
    public void handle(String payload) {
        System.out.println("Processing " + payload);
    }
}
~~~

This is a snippet; it requires `@Component`, `@JmsListener`, and JMS/listener container bean configuration in the application. `@JmsListener` lets Spring manage listener threads, lifecycle, recovery/reconnection, concurrency, and transaction integration; however, the listener thread can still block when handler code calls DB/HTTP.

**Choose receive when:**
- An operations/test tool needs to fetch **one message** with a finite timeout and clear understanding of ACK effects.
- A workflow requires bounded on-demand pulling, with explicit scheduling and error handling.
- You need to actively control the exact moment a message is received, without needing a long-lived listener.

**Choose a listener when:**
- You have a continuous-consumption worker, retry/redelivery/DLQ, and multiple competing consumers.
- You need scaling/concurrency and shutdown/recovery managed by the Spring container.
- You do not want each polling cycle to open or hold resources manually.

Neither API automatically guarantees DB commit, proper business retries, or idempotency. The choice also depends on queue/topic semantics, broker policies, and transaction boundaries.

## 16. Closing, stopping, and handling waiting threads

- With a positive timeout, receiving code gets periodic opportunities to return, check the shutdown flag, and update health status.
- With classic JMS, `MessageConsumer.close()` has interaction rules with a waiting `receive`; it may cause a blocking receive to complete, though you must still obey the provider's threading/lifecycle contract.
- `Connection.stop()` stops delivery, **does not** "cancel all receives": timeouts keep counting down.
- Do not share a classic JMS `Session` across multiple threads without understanding Jakarta Messaging restrictions.
- Do not close `JmsTemplate`'s session/connection from business code: the template manages those resources.
- `Thread.interrupt()`/`Future.cancel(true)` must not be assumed to reliably cancel JMS I/O across all providers.
- On application shutdown, stop issuing new receives, let bounded calls finish, close resources, and ensure un-ACKed/uncommitted messages have proper recovery.

**Timeout is not an absolute deadline:** network errors and connection creation can take separate time; measure actual shutdown duration and configure JMS-provider-specific connect/read timeouts when needed.

## 17. Common troubleshooting table

| Symptom | Common root cause | How to check |
| --- | --- | --- |
| `receive()` waits forever | Default timeout `0` and no message, or classic Connection not started | Check timeout/start, stack trace, broker |
| `receive(2000)` returns null even with messages in queue | Competing consumer, selector, delay, in-flight, wrong destination | Broker consumer list, selector, and headers |
| HTTP thread pool exhausted | Indefinite waiting on request threads | Thread dump, active requests, load test |
| High CPU when queue is empty | Unthrottled `receiveNoWait` loop | CPU profile, receive call rate |
| `receiveAndConvert` fails | Converter/schema/type mismatch | JMS Message type, converter config |
| Message lost after "peeking" | Receive is destructive consumption, not peek | Use QueueBrowser/metrics |
| DB fails but broker does not redeliver | AUTO_ACK already acknowledged before business code | Actual transaction boundary |
| Same message received twice | JMS rollback/redelivery or producer sent duplicates | JMSMessageID, eventId, and inbox |
| Async task canceled but worker still waits | Interrupt does not guarantee JMS client exit | Finite receive timeout, provider shutdown |
| Topic loses messages while offline | Non-durable subscriber | Subscription identity/retention |
| 3s timeout but method takes 8s | Network setup and resource acquisition add extra time | Per-phase metrics, provider client settings |

**Do not diagnose a "deadlock" solely because a thread is in `JmsTemplate.receive`.** A waiting receive call is normal behavior for a blocking API. A deadlock requires evidence of a cyclic wait on locks/resources, not just seeing `WAITING`.

## 18. Exercises and self-check questions

1. **Receive timeout:** on an empty test queue, call `setReceiveTimeout(1000)` then `receive`; measure roughly how long it waits and confirm the `null` result.
2. **No-wait:** set `-1` then receive; afterward send a message and receive again. Explain why this is not a peek.
3. **Indefinite:** call default receive on a separate worker, then send a message so it exits; do not use an HTTP request thread.
4. **Classic Connection.start:** create a consumer without starting, try `receive(1000)`; start the connection and try again.
5. **Competing consumers:** two workers receive on the same queue; send one message and explain why only one worker receives per delivery.
6. **Selector:** send different `eventType` properties; pick a selector and observe that a timeout does not mean the queue is empty.
7. **receiveAndConvert:** test `TextMessage`/`BytesMessage` with the default converter, then swap in a JSON converter with a clear contract.
8. **Thread pool:** with a 2-thread pool, submit 3 bounded receives; observe that one task must wait for an executor slot while two workers are blocked.
9. **HTTP request:** use a test endpoint with a positive timeout and one without a timeout, and observe the difference in request thread occupancy.
10. **AUTO_ACK:** receive a message then intentionally throw an error in business code outside receive; observe redelivery or lack of redelivery depending on configuration.
11. **JMS transaction:** wrap receive and processing in `JmsTransactionManager`, throw an exception to observe rollback; do not confuse it with a DB transaction.
12. **Crash after DB commit:** simulate a JVM failure between DB and JMS commit, and verify a unique event ID protects business logic.
13. **Shutdown:** stop the application while a receive is in progress, verifying bounded calls finish and resources do not leak.
14. **Topic:** compare a non-durable subscription online vs. offline, avoiding the misconception that topics retain history for all consumers.

### Completion checklist

- [ ] Know which thread is held when calling `receive`.
- [ ] Remember that `receive(0)` waits indefinitely; `receiveNoWait()` does not wait.
- [ ] Know `JmsTemplate.setReceiveTimeout(0)` = indefinite, `-1` = no-wait, and positive = bounded.
- [ ] Distinguish `receive` (JMS Message) from `receiveAndConvert` (Java Object).
- [ ] Know classic `Connection.start()` is required for delivery, whereas `JmsTemplate` manages connections automatically.
- [ ] Do not treat `null` as proof the entire queue is empty or business work is complete.
- [ ] Do not use no-wait in an uncontrolled busy loop.
- [ ] Do not hold a servlet thread waiting indefinitely for a message.
- [ ] Do not assume `Future.cancel(true)` cancels a JMS receive immediately.
- [ ] Understand ACK/transaction semantics and the consequences if DB fails after JMS has ACKed.
- [ ] Know when `@JmsListener` is better than writing your own polling loop.

**Final check question:** "When there are no messages in the queue, what does `jmsTemplate.receive("jobs.queue")` do by default?" — With the default `receiveTimeout=0`, **the calling thread waits indefinitely** until a message arrives or another condition terminates the call. This is the core characteristic to factor into every decision to use synchronous receive.

## 19. Official documentation

1. [Spring Framework – Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): synchronous receiving and thread blocking, timeouts, message listener containers.
2. [Spring Framework 6.2 – JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `receive`, `receiveAndConvert`, `receiveSelected` overloads and default session settings.
3. [Spring Framework – JmsDestinationAccessor](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/destination/JmsDestinationAccessor.html): `RECEIVE_TIMEOUT_INDEFINITE_WAIT`, `RECEIVE_TIMEOUT_NO_WAIT` constants.
4. [Spring Framework – Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTransactionManager` and JMS resources.
5. [Jakarta Messaging 3.1 – MessageConsumer](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageconsumer): `receive`, `receive(long)`, `receiveNoWait`, `close`.
6. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): `Connection.start/stop`, synchronous reception, ACK/transaction, and threading.
7. [Spring Boot 3.5 – Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.jms.template.receive-timeout` and listener properties.

**Conclusion:** synchronous receiving allows actively pulling a message, at the cost of **blocking the thread**, potentially indefinitely by default. Use it only when timeout, resources, thread ownership, ACK/transaction, and shutdown behavior are clearly defined. For continuous background consumers, prefer a Spring listener container unless there is a specific reason to poll with `receive`.