# CompletionListener Confirms the Send Operation, Not Consumption Completion (Spring JMS)

## 1. The Problem: What Does "Send Succeeded" Mean?

An order service sends an `OrderCreated(order-42)` event to a JMS queue. After calling send, the app wants to return a result to the user. However, there are at least four distinct milestones:

1. **Send request initiated:** producer invokes the `send` API.
2. **Send operation confirmed:** JMS provider reports that the send succeeded with a guarantee equivalent to a synchronous send on the same provider.
3. **Consumer receives the message:** JMS provider delivers the message to an eligible consumer.
4. **Business work completed:** the receiver processes and commits business state changes (if the workflow has transactions).

`jakarta.jms.CompletionListener` provides a signal at **milestone 2** for **asynchronous send**, not a signal for milestone 3 or 4.

For example: the producer sends `OrderCreated` and receives `onCompletion` even when no consumer is online, as long as the broker/provider accepts the message under current configuration. A consumer can also receive the message later, fail processing, and trigger redelivery. Both scenarios remain completely consistent with the sender having received `onCompletion`.

Practical consequence: if an HTTP API immediately returns `"order has been processed"` from `onCompletion`, that response can **contradict the receiver's actual state**. If you need to know business work finished, design a separate confirmation signal from the consumer or the system owning that business state.

**Lesson goal:** understand `CompletionListener`, the asynchronous send mechanism, the two success/failure callbacks, how to use it alongside Spring `JmsTemplate`, threading/transaction/lifecycle limits, and how to design proper business confirmation.

## 2. The CompletionListener API

`CompletionListener` belongs to Jakarta Messaging (since JMS 2.0). In Spring Boot 3.x/Spring Framework 6.x, imports use the `jakarta.jms` namespace:

```java
package jakarta.jms;

public interface CompletionListener {
    void onCompletion(Message message);
    void onException(Message message, Exception exception);
}
```

This is an **API signature illustration**, not an interface you need to rewrite.

| Callback | What It Confirms | What It Does Not Confirm |
| --- | --- | --- |
| `onCompletion(Message)` | The **send** operation completed successfully per the provider's guarantee level | Consumer received, ACKed, finished logic, or committed database |
| `onException(Message, Exception)` | Provider detected a send error that could not be thrown directly inside the `send` call | Message was definitely never received by the broker |
| Exception thrown directly from `send` | Operation failed immediately on the calling thread | Provider will also call `onException` afterwards |

Per Jakarta Messaging 3.1 `7.3.1–7.3.2`, when `send` encounters an error that can be thrown directly on the calling thread, the provider must throw it there and **never call** `onCompletion` or `onException` for that same send. When a failure is detected after `send` returned, the provider invokes `onException`.

The specification also states: **if an exception occurs during sending, it cannot be determined for certain whether the message was sent successfully or not**. The broker may have received the message before a network disconnect dropped the confirmation. Therefore `onException` and timeouts do not automatically mean `NOT_SENT`.

### States That Should Be Kept Separate

| Application State | Source of Evidence |
| --- | --- |
| `SEND_REQUESTED` | Application asked the producer to send |
| `SEND_PENDING` | No send confirmation result yet |
| `SEND_CONFIRMED` | `onCompletion` has been called |
| `SEND_UNCERTAIN` | Exception/timeout insufficient to prove whether broker received it |
| `CONSUMER_RECEIVED` | Observed on the receiving side (listener/tracing) |
| `BUSINESS_COMPLETED` | Evidence business state committed per the two-system contract |

The state names above are **application conventions**, not built-in Jakarta Messaging enums. Never merge `SEND_CONFIRMED` into `BUSINESS_COMPLETED`.

## 3. Asynchronous Send and Where the Callback Fits

Jakarta Messaging offers two main ways to register a `CompletionListener`:

- **Classic API:** `jakarta.jms.MessageProducer.send(...)` overloads accepting an extra `CompletionListener`.
- **Simplified API:** calling `jakarta.jms.JMSProducer.setAsync(listener)` followed by `send(destination, ...)`.

Classic API example, **snippet inside a method with a valid `MessageProducer producer` and `Message message`**:

```java
producer.send(message, new jakarta.jms.CompletionListener() {
    @Override
    public void onCompletion(jakarta.jms.Message sent) {
        System.out.println("SEND_CONFIRMED");
    }

    @Override
    public void onException(
            jakarta.jms.Message attempted, Exception failure) {
        System.err.println("SEND_UNCERTAIN: "
                + failure.getClass().getSimpleName());
    }
});
```

Simplified API example, **snippet with an existing `JMSContext context`, `Destination queue`, and `CompletionListener listener`**:

```java
context.createProducer()
        .setAsync(listener)
        .send(queue, context.createTextMessage("OrderCreated:order-42"));
```

Timeline diagram:

```text
Producer thread                   JMS provider                    Consumer
---------------                   ------------                    --------
send(message, listener)  -------> starts send processing
send() returns                   ... confirms send operation ...
app continues                    calls onCompletion()
or awaits explicitly             or onException()                   |
                                                                   may be offline,
                                                                   receive late, roll back,
                                                                   fail processing...
                                                                   |
                                                              business commit?
```

The provider decides how much work runs before `send` returns and how much runs in the background. The callback must run on a **different thread from the one calling asynchronous `send`**, yet you must not assume the callback always runs after log lines immediately following `send`: threads can be scheduled very closely.

**Reliability level of `onCompletion`:** Jakarta Messaging states the callback is invoked only when sending succeeds with a reliability level **matching a synchronous send on the same provider**. This does not upgrade non-persistent to persistent, does not verify business transactions, and does not implicitly create a request/reply mechanism to the consumer.

## 4. CompletionListener Differs from Spring JmsTemplate Callbacks

`JmsTemplate` is Spring JMS's convenience API. Example:

```java
jmsTemplate.send("orders.in", session ->
        session.createTextMessage("OrderCreated:order-42"));
```

The lambda parameter here is **`org.springframework.jms.core.MessageCreator`**. Spring supplies a `Session` so the app can construct a JMS `Message`, and then `JmsTemplate` performs the send. This is **not** a completion callback.

| API | What Does the Callback Receive? | What Is It Used For? |
| --- | --- | --- |
| `JmsTemplate.send(..., MessageCreator)` | `Session` provided by the template | Creating `TextMessage`, `MapMessage`, attaching properties/headers before sending |
| `JmsTemplate.convertAndSend(..., MessagePostProcessor)` | Converted `Message` | Adjusting the message before sending |
| `JMSProducer.setAsync(CompletionListener)` | Succeeded `Message` or failed `Message + Exception` | Observing asynchronous send outcome |
| `@JmsListener` | Payload/`Message` received on the consumer side | Running consumer receive and processing logic |

`JmsTemplate.send(String, MessageCreator)` is a `void` method with no `CompletionListener` parameter in Spring Framework 6.2's standard API. If you want Jakarta Messaging asynchronous send directly, inject the Spring Boot-configured `ConnectionFactory` and create a `JMSContext`/`JMSProducer` as shown below.

**Two notes:**

1. Wrapping `jmsTemplate.send(...)` in a Spring `@Async` method merely moves the template call onto a worker thread. That method's returned Future represents **the send call finishing**, not becoming a `CompletionListener` or notifying that the consumer processed it.
2. Do not stuff asynchronous `MessageProducer.send(..., CompletionListener)` into `JmsTemplate.execute(...)` and let the callback outlive the template-managed resource lifecycle. Closing producers/sessions has callback-waiting rules, so ownership and completion must be explicitly designed.

If an application only needs standard sending, `JmsTemplate` may be enough. Add asynchronous send callbacks only when you genuinely need to track send completion boundaries in ways synchronous APIs do not provide.

## 5. Complete Example: Spring Boot 3.x/Java 17+ and JMSProducer.setAsync

This example builds a **Spring Boot application running standalone as a Java SE client**, connecting to an ActiveMQ Artemis broker running at `tcp://localhost:61616`. It assumes the broker has queue `orders.in` and the application account has send permission. This example depends on Spring Boot and a Jakarta JMS provider—**not a standalone Java SE program run solely with `javac`**.

The example **explicitly awaits `onCompletion`** so learners can observe the distinction between `send()` returning and the send being confirmed. Because this method awaits the result, it should not be advertised as a fully non-blocking API.

### 5.1. Dependencies

In a Spring Boot Groovy DSL project `build.gradle` already configured with the Boot plugin and dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
```

Spring Boot 3.x uses the `jakarta.jms` namespace; do not mix in old `javax.jms`.

### 5.2. application.yml

File `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: "${JMS_BROKER_URL:tcp://localhost:61616}"
    user: "${JMS_USER}"
    password: "${JMS_PASSWORD}"

app:
  jms:
    queue: "${JMS_QUEUE_NAME:orders.in}"
```

Provide `JMS_USER` and `JMS_PASSWORD` environment variables; store real credentials only in proper secrets management. If you have multiple brokers/environments, set the right `JMS_BROKER_URL` and `JMS_QUEUE_NAME`. A queue name alone does not prove the physical resource is provisioned.

### 5.3. Service Creating JMSContext and CompletionListener

File `src/main/java/demo/jms/AsyncOrderPublisher.java`:

```java
package demo.jms;

import jakarta.jms.CompletionListener;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

@Service
public class AsyncOrderPublisher {
    private final ConnectionFactory connectionFactory;
    private final String queueName;

    public AsyncOrderPublisher(
            ConnectionFactory connectionFactory,
            @Value("${app.jms.queue}") String queueName) {
        this.connectionFactory = connectionFactory;
        this.queueName = queueName;
    }

    public void sendAndWait(String orderId, String eventId)
            throws Exception {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is blank");
        }
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId is blank");
        }

        CompletableFuture<Void> sendFinished = new CompletableFuture<>();

        try (JMSContext context =
                     connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
            Queue queue = context.createQueue(queueName);
            TextMessage message =
                    context.createTextMessage("OrderCreated:" + orderId);
            message.setStringProperty("eventId", eventId);

            CompletionListener listener = new CompletionListener() {
                @Override
                public void onCompletion(Message sent) {
                    sendFinished.complete(null);
                }

                @Override
                public void onException(
                        Message attempted, Exception failure) {
                    sendFinished.completeExceptionally(failure);
                }
            };

            context.createProducer()
                    .setAsync(listener)
                    .send(queue, message);

            System.out.println("send() returned");
            sendFinished.get(10, TimeUnit.SECONDS);
            System.out.println("onCompletion confirmed send succeeded");
        }
    }
}
```

Step-by-step explanation:

1. `ConnectionFactory` is supplied by Spring Boot; the service creates its own `JMSContext` per attempt without sharing contexts/sessions across threads.
2. `context.createQueue(queueName)` creates a JMS object representing the queue. Brokers may require the queue to pre-exist; calling this method is not a standard way to provision physical queues.
3. `TextMessage` carries body `OrderCreated:order-42` and property `eventId` set by the app before sending.
4. `setAsync(listener)` registers the callback. `onCompletion` completes the `CompletableFuture`; `onException` fails it via `completeExceptionally`.
5. `sendFinished.get(10, TimeUnit.SECONDS)` forces the demo thread to **wait for the send result**. `ExecutionException` can carry a callback exception, while `TimeoutException` means the callback wait timed out: **send status is then indeterminate**.
6. `try-with-resources` closes `JMSContext`. Per Jakarta Messaging `7.3.4`, closing context/producer/session/connection must wait for unfinished asynchronous sends and their callbacks to return; the 10-second `get` timeout **is not a hard upper bound on the entire method**. Never use this pattern to promise an HTTP request always finishes in 10 seconds.

Never call `context.close()`, `commit()`, or `rollback()` inside the callback. Never read or modify `message` from the calling thread while async send is still in flight.

### 5.4. Runner Class

File `src/main/java/demo/jms/AsyncSendApplication.java`:

```java
package demo.jms;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;

@SpringBootApplication
public class AsyncSendApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncSendApplication.class, args);
    }

    @Bean
    @Profile("completion-demo")
    ApplicationRunner demo(AsyncOrderPublisher publisher) {
        return args -> publisher.sendAndWait(
                "order-42", "event-order-42-created");
    }
}
```

Start the broker with queue `orders.in` and valid credentials, then run inside the project with the `bootRun` task:

```bash
./gradlew bootRun --args='--spring.profiles.active=completion-demo'
```

If both `send` and callback succeed, the two lines **printed by application code** appear in this order (alongside Spring Boot logs):

```text
send() returned
onCompletion confirmed send succeeded
```

Because both `println` calls live on the calling thread, the second line prints only after the `CompletableFuture` completes successfully. The provider may invoke the callback before or after the first line prints; this code does not enforce callback thread timing, only the order of **the app's two output lines**.

If `send(...)` throws immediately, the first line may not appear. If the callback reports an error or times out, the second line does not appear. **There is no consumer in this project**, yet the producer can still receive send confirmation as long as the broker accepts the message: that is the exact point to observe.

Never enable the `completion-demo` profile in production because every startup would try to emit another event with the same ID.

### 5.5. Optional Listener to Observe the Receive Milestone

To explicitly observe the receive milestone, add a consumer to the same project:

```java
package demo.jms;

import org.springframework.context.annotation.Profile;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
@Profile("consumer-demo")
public class OrderConsumer {
    @JmsListener(destination = "${app.jms.queue}")
    public void receive(String body) {
        System.out.println("consumer received: " + body);
    }
}
```

Save this file at `src/main/java/demo/jms/OrderConsumer.java` and add `@EnableJms` (importing `org.springframework.jms.annotation.EnableJms`) on `AsyncSendApplication` to enable annotation-driven listeners explicitly. When `consumer-demo` is enabled, the listener can print:

```text
consumer received: OrderCreated:order-42
```

This line signals that **the consumer method was invoked**. It does not prove the consumer committed a business transaction; the example does not even have a database yet. Running both profiles `completion-demo,consumer-demo` simultaneously may interleave producer and consumer logs in various orders; never treat log order as a JMS guarantee contract.

## 6. Three Send Outcome Types and Error Handling

### 6.1. onCompletion: A Positive Signal for Send

When the provider calls `onCompletion(message)`, the application can record `SEND_CONFIRMED` for an event with an immutable ID. You can measure latency from `sendRequestedAt` to `sendConfirmedAt` to monitor send infrastructure health. **Do not** increment a `business_completed` counter here.

### 6.2. onException: Error Outcome, Yet Possibly Ambiguous

Suppose the broker received event `E-901`, but the connection dropped before the producer received confirmation. An exception may be raised even though the message already reached the broker. The specification does not permit the app to conclude with certainty that "the message was not sent."

Therefore, when deciding to retry:

- Keep the same `eventId` for the same business intent.
- Apply retry/backoff and max attempt limits; monitor indeterminate states.
- Consumers use idempotency or inbox/deduplication to handle duplicate events.
- When combining database changes with publishing, consider transactional outbox and reconciliation workflows; never assume a send error makes uncontrolled re-sending safe.

### 6.3. Exceptions from the send Call Itself

If `send(...)` throws immediately (e.g., failing to create a producer/destination or early connection loss), the callback **need not and must not** be invoked for that same failure per rule `7.3.2`. Application code must catch exceptions at the **`send` call** if it needs to record or handle immediate failures.

In the simplified API, operations can throw `JMSRuntimeException`; calling `TextMessage` setters can also throw checked `JMSException`. In the demo code, the method declares `throws Exception` so the Runner surfaces startup failures; real apps should clearly distinguish transient errors, permanent errors, and indeterminate states.

## 7. CompletionListener and Transactions

In a local JMS transaction, the callback can fire once the send operation completes even while the transaction is **not yet committed**. Jakarta Messaging specification `7.3.4` requires `commit()`/`rollback()` to wait for incomplete asynchronous sends and their callbacks to complete before finalizing the transaction.

```text
begin local JMS transaction
     |
     +-- async send(message, listener)
     |        |
     |        +-- onCompletion => send operation completed
     |
     +-- commit() or rollback()
              |
              +-- outcome of the JMS transaction
```

`onCompletion` does not equal `commit`. If the transaction rolls back, the message's validity follows the transaction. If commit fails or the connection drops, evaluate the outcome and retry options separately.

- Never call `close`, `commit`, or `rollback` from inside the callback itself.
- `@Transactional` in Spring has meaning only relative to the active transaction manager; a database transaction and a JMS transaction are not implicitly atomic.
- When safe coordination between database state and publishing is needed, design outbox/XA or another appropriate mechanism. That is an architectural boundary that cannot be solved merely by registering a `CompletionListener`.

## 8. Threading, Message Ownership, and JMSContext Lifecycle

### 8.1. Callback Runs on a Different Thread

Jakarta Messaging requires providers **not** to invoke the callback on the thread calling asynchronous `send`. A `Session` runs only one callback at a time; callbacks on the same `MessageProducer` or `JMSContext` must be invoked in the order of their corresponding asynchronous send calls.

However, callback order on the same producer **is not** consumer business completion order. With multiple consumers, messages can execute in parallel or be redelivered.

Keep callbacks short: record outcomes by `eventId`, complete a future, or forward a status event to another component. Never run slow I/O or complex broker operations directly on the callback thread.

### 8.2. Do Not Read Message While Asynchronous Send Is In Flight

After `send` returns and before `CompletionListener` runs, code **must not read or modify headers, properties, or body of the in-flight `Message`**, because the provider may be mutating it on another thread. Specification `7.3.9` states that premature access may cause the provider to throw `JMSException`; if it does not throw, behavior is undefined.

After `onCompletion`, provider-generated headers such as `JMSMessageID` can be accessed per API rules. After `onException`, provider-set headers/properties have undefined state. Accordingly, real applications should hold `eventId` as immutable data separate from the `Message` object.

### 8.3. Do Not Share Session Casually

A `Session` must not be used concurrently by multiple threads per Jakarta Messaging rules. `CompletionListener` must not touch the `Session` if application threads may still be using it. Never store a `JMSContext` in a singleton field and access it concurrently across requests without explicit synchronization and lifecycle design.

### 8.4. close() Can Block Waiting for Callbacks

When an application closes a producer/session/connection or `JMSContext`, the provider must wait for incomplete sends and their callbacks to return. That is why the code below **does not guarantee non-blocking fire-and-forget**:

```java
try (JMSContext context = connectionFactory.createContext()) {
    context.createProducer()
            .setAsync(listener)
            .send(queue, message);
}
// close() must wait for incomplete sends/callbacks.
```

This is purely a **lifecycle illustration snippet**, assuming `connectionFactory`, `listener`, `queue`, and `message` are properly configured; it is not a standalone program. High-throughput systems need a dedicated component keeping contexts/producers alive, tracking pending sends, handling controlled shutdown, and enforcing backpressure. Never return a future to a caller and immediately close the context expecting JMS work to run independently as you wish.

### 8.5. Restrictions in Jakarta EE Containers

Per Jakarta Messaging `7.3.5`, asynchronous send with `CompletionListener` is **not permitted** inside a Jakarta EE web container or Enterprise Beans container. Providers may throw `JMSException`/`JMSRuntimeException` on the relevant APIs. The Section 5 example is standalone Spring Boot running like Java SE. If deploying a WAR/EJB inside a Jakarta EE application server, verify container constraints and valid send models; never blindly copy `setAsync(listener)` into EJBs or Jakarta EE servlets.

## 9. Wanting to Know When Consumption Finishes: Build a Separate Outcome Protocol

Suppose Order Service needs to know Inventory Service deducted stock, **committed its database**, and published the result. Desired flow:

```text
Order Service                    Broker                   Inventory Service
-------------                    ------                   -----------------
send eventId=E-901 -----------> queue orders.in
onCompletion
  => SEND_CONFIRMED
                                  ---------------------> consume E-901
                                                        check idempotency
                                                        update inventory
                                                        COMMIT database
                                                        publish processed outcome
                                  <--------------------- ProcessingCompleted(E-901)
receive ProcessingCompleted(E-901)
match eventId
  => BUSINESS_COMPLETED
```

This is an **application-designed architectural flow**, not behavior produced automatically by `CompletionListener`. The completion signal is trustworthy only if emitted consistently with the receiver's transaction, such as via an outbox after business state commits.

Signal layers commonly confused:

| Signal | Who Produces It | What It Actually Tells You |
| --- | --- | --- |
| `onCompletion` | Producer-side JMS provider | Send completed with equivalent synchronous reliability |
| Broker enqueue/dequeue metrics | Broker | Storage/distribution activity per broker definitions |
| JMS consumer ACK | Receiving-side consumer/container/transaction | JMS acknowledgement status, not necessarily a business commit |
| `@JmsListener` finished | Consumer side | Listener method returned; transaction/ACK still depends on config |
| `ProcessingCompleted(eventId)` | Business service | Completion milestone per the contract published by that service |

For request/reply, use a response destination, `JMSCorrelationID`, or `eventId` for correlation, and handle timeouts, duplicates, late replies, and cases where processing committed but the reply was lost.

Never equate the provider-assigned `JMSMessageID` from send with the business `eventId`: an event may retry and receive a different message ID while the business intent remains the same.

## 10. Testing and Operational Observability

Tests should separate **send success** from **consumption completion**.

| Scenario | Evidence to Collect | Conclusion |
| --- | --- | --- |
| Broker running, no consumer | `onCompletion`, queue metrics | Sending can succeed before any consumer exists |
| Slow consumer | Send callback timestamp vs. business commit timestamp | Two distinct milestones |
| Consumer rollback/retry | Producer callback, consumer redelivery | Send success does not guarantee business success |
| Network loss right at send | Exception/timeout and broker inspection | Outcome may be indeterminate |
| Local JMS transaction rollback | Send callback and transaction outcome | `onCompletion` does not replace commit |
| Multiple messages/consumers | Tracing via `eventId` and per-event status | Callback order does not confirm business completion order |

### How Do Unit Tests and Integration Tests Differ?

Unit tests can mock `onCompletion`/`onException` callbacks to verify producer-side state update logic. They **do not test** the broker, provider threading, send reliability levels, or consumer processing.

Integration tests require a real broker, test queues, and a separate consumer. Run scenarios with consumers stopped, consumers failing, and callbacks failing. Use `CountDownLatch`/`CompletableFuture`, bounded timeouts, and `eventId`; never rely on an arbitrary `Thread.sleep(...)` to claim "callbacks always run before consumers."

Useful application metrics include:

- `send_requested_total`: number of publish requests.
- `send_confirmed_total`: number of successful `onCompletion` calls.
- `send_uncertain_total`: errors/timeouts where broker receipt is uncertain.
- `consumer_received_total`: receive count, potentially including redeliveries.
- `business_completed_total`: events reaching committed business completion.
- `send_confirmation_latency` and `business_completion_latency`: two distinct latencies.

Never log raw sensitive payloads inside callback logs. Include `eventId`, destination, timestamp, exception class, and correlation ID as needed for investigation.

## 11. Common Mistakes

| Misconception / Mistake | Consequence | How to Fix |
| --- | --- | --- |
| `onCompletion = consumer finished` | Reports business state too early | Track business replies/results after commit |
| `send() returned = send confirmed` | Misses errors detected later | Use completion signals / await callbacks when needed |
| `onException = definitely not sent` | Retries cause duplicates | Preserve `eventId`, use idempotency and unknown states |
| Passing `CompletionListener` to `JmsTemplate.send` like a `MessageCreator` | Confused APIs, invalid code | Distinguish message-creation callbacks from send-completion callbacks |
| Spring `@Async` = asynchronous JMS send | Confuses method future with JMS completion | Distinguish worker threads from `JMSProducer.setAsync` |
| Reading `Message` before callback | Data race with provider | Read only after callback per specification |
| Closing context expecting non-blocking behavior | Provider must wait for pending sends/callbacks | Design lifecycles and shutdown properly |
| Calling `close/commit/rollback` inside callback | Violates reentrancy rules | Manage resources/transactions outside callbacks |
| Treating `onCompletion` as transaction commit | Rollbacks/commit failures can still happen | Track transaction outcomes separately |
| Equating consumer ACK with DB commit | Business state might not be durable yet | Reply after commit / use outbox properly |
| Using async send in Jakarta EE web/EJB container | API forbidden by specification | Follow container/provider rules |
| Timing out and retrying with a new `eventId` each time | Can duplicate business intent | Keep stable identity and reconcile |

## 12. Self-Check

1. Who invokes `CompletionListener.onCompletion`? Which milestone does it confirm in the producer → broker → consumer → database chain?
2. If a queue has no consumers, can the producer still receive `onCompletion`? Which conditions depend on the broker/provider?
3. If `send` throws an exception on the calling thread, should you still wait for `onException` for that same send?
4. Why must the application not read/modify the `Message` object after async `send` returns and before the callback runs?
5. Why does a `sendFinished.get(10, TimeUnit.SECONDS)` timeout not guarantee the entire method finishes within 10 seconds?
6. Why is `onCompletion` inside a local JMS transaction insufficient to prove the transaction committed?
7. What signal must be built if the sender needs to know the receiver updated its database successfully? What failure do `eventId` and idempotency prevent?

**Takeaway:** `CompletionListener` confirms only **the outcome of an asynchronous send operation** at the JMS provider's guarantee level. It does not confirm consumer receipt, ACK, or business commit. When final processing status is needed, establish a separate reply contract from the consuming service.

### References

- Jakarta Messaging 3.1 Specification — `7.3 Asynchronous send`, `7.3.1–7.3.9` (exceptions, close/transaction, threading, message access, Jakarta EE restrictions): https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging 3.1 API — `CompletionListener`: https://javadoc.io/static/jakarta.jms/jakarta.jms-api/3.1.0/jakarta.messaging/jakarta/jms/CompletionListener.html
- Jakarta Messaging 3.1 API — `MessageProducer`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer
- Spring Framework 6.2 — Sending a Message, `JmsTemplate`, and `MessageCreator`: https://docs.spring.io/spring-framework/reference/integration/jms/sending.html
- Spring guide — Messaging with JMS: https://spring.io/guides/gs/messaging-jms/
