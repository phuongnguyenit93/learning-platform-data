# Comparing Asynchronous Messaging with Synchronous HTTP Calls

> **Context:** The JMS big picture in Spring Framework. This lesson compares two ways components in a system coordinate: calling HTTP and waiting for a response, or sending a message through a broker to be processed later. The focus is on when results are received, service dependencies, error handling, and implementation with Spring JMS.

## 1. Execution Models and the Meaning of "Synchronous" and "Asynchronous"

**Synchronous HTTP (synchronous request–response):** the caller sends an HTTP request to the receiver and waits for the HTTP response for that operation. If API A needs a result from API B to finish its work, A must wait for B to process or return an error/timeout. Example: an order API calls an inventory-check service and waits for the result before deciding to confirm the order.

**Asynchronous JMS messaging:** the sender (producer) creates a message, sends it to a broker (such as ActiveMQ Artemis), and then continues its work without waiting for the consumer to finish business processing. The broker holds/delivers the message to the consumer according to configuration. Example: after accepting an order, the API emits an invoice-creation command to a queue; a worker generates the invoice when it has capacity.

Two milestones to distinguish:
- **Sent / accepted by the broker:** the producer receives the outcome of the send operation. This does not yet mean the consumer has processed successfully.
- **Business processing completed:** the consumer has processed and updated the outcome; this can happen milliseconds, minutes, or longer later if the queue has a backlog.

In Spring, `JmsTemplate.convertAndSend(...)` is a send call **on the current thread**, which may wait on the connection/broker and throw exceptions. The asynchronicity lies in the producer **not waiting for the consumer's business processing result**, not that the send operation is always non-blocking.

~~~text
Synchronous HTTP:
Client -> Order API -> HTTP POST -> Inventory API
Client <- Order API <- HTTP response (OK / error)
         [Order API waits for Inventory API result]

Asynchronous JMS:
Client -> Order API -> JMS Producer -> Broker/Queue -> JMS Consumer -> Process
Client <- 202 Accepted              [consumer may process later]
         [202 does not mean processing is finished]
~~~

**Terminology note:** HTTP can also be designed asynchronously at the business level (returning `202 Accepted` followed by polling/webhook), and JMS can use request–reply or synchronous receiving via `JmsTemplate.receive(...)`. Therefore, compare **concrete interaction patterns** rather than concluding "HTTP is always synchronous, JMS is always asynchronous".

## 2. Comparison Across Decisive Criteria

| Criterion | Synchronous HTTP Call | Asynchronous JMS Messaging |
| --- | --- | --- |
| Result received by caller | Result/HTTP status of the invoked operation, within the same request–response cycle | Result of sending to the broker; final processing outcome requires another channel to query/notify |
| Temporal dependency | Receiver must respond promptly while caller is waiting | Producer and consumer do not need to be active simultaneously if the broker persists messages |
| When processing service pauses | Caller may hit timeouts, errors, or require retries | Messages can sit in the queue for later processing; depends on storage config, TTL, and broker health |
| When broker/target service fails | HTTP error is received directly if detectable | If broker cannot accept, producer still errors; if consumer fails after broker accepts, it can reprocess later |
| Perceived latency | Response time typically includes downstream processing time | Producer can respond early; **completion** time also includes queue wait time |
| Traffic spikes | Can cause request pile-up, thread/connection exhaustion, or increased timeouts | Queue absorbs load spikes within capacity limits; queue latency rises if consumption lags |
| Scaling | Scale HTTP service and regulate with timeouts, rate limits, circuit breakers | Scale queue consumers (subject to broker capacity and ordering requirements) |
| Processing order | Order across multiple independent requests is not implicitly guaranteed | Queues do not guarantee global completion order with multiple consumers, retries, or redelivery |
| Reliability | Must design retries, idempotency, and handling ambiguous timeout outcomes | Must design persistence, ack/transactions, redelivery, DLQ, idempotency, and backlog monitoring |
| Consistency | Easy to represent immediate outcomes, but no automatic cross-service transactions | Typically accepts eventual consistency and designs an in-progress state |
| Operations | Monitor HTTP latency, error rate, timeouts, saturation | Additionally monitor queue depth/age, consumer lag, retries, DLQ, and broker health |
| Complexity | Usually more intuitive for interactions needing immediate results | More complex around broker, message schemas, job state, and duplicate handling |

Neither model is automatically "faster" or "more reliable" in every scenario. With HTTP, user wait time is roughly equal to downstream processing time. With JMS, the **accepted** reply is usually quick, while **completion time** can be longer due to queueing. A broker does not automatically turn slow processing into fast processing.

## 3. Business Example: Generating an Invoice After Placing an Order

**Approach 1 – Synchronous HTTP:**
1. Client sends `POST /orders`.
2. Order Service calls Invoice Service over HTTP and waits for invoice generation.
3. Only after Invoice Service replies does Order Service complete the response to the client.
4. If Invoice Service is slow or unavailable, the client may wait a long time or time out even though the order was already created in an earlier step.

Pros: the invoice generation outcome can be returned immediately if all steps succeed. Cons: the request path depends on the uptime and performance of another service; timeouts also create an ambiguous "did the other side process it or not" situation.

**Approach 2 – Asynchronous JMS:**
1. Order Service validates the request and records the order/pending processing state.
2. Producer sends a `CreateInvoice` message (containing `orderId`, `requestId`, schema version) to a queue.
3. Once request acceptance and job dispatch/scheduling are safe enough per the API contract, the client can receive `202 Accepted` with a `jobId` or status lookup URL.
4. Consumer uses `@JmsListener` to receive the message and generate the invoice. State transitions `PENDING → PROCESSING → SUCCEEDED` or `FAILED`.
5. Client calls `GET /jobs/{id}`, receives a webhook, or gets notified via a separate channel to learn the **final outcome**.

**Critical design point:** if writing to the database and sending the message are two separate operations, a "committed order but failed to send message" case can occur. When no job may be lost, consider a **transactional outbox**: save a job/outbox record in the same transaction as the order, then a separate publisher sends it to the broker and marks it published; the consumer must still guard against duplicates.

~~~text
Synchronous HTTP:
Order API ──POST /invoices──> Invoice Service
          <── result ────────
          -> return result to client

Asynchronous JMS:
Order API ── CreateInvoice(orderId, requestId) ──> Queue
          <── sent / accepted ────────────────────
          -> 202 + jobId
Queue ──> Invoice Worker ──> Invoice DB / job status
Client ── GET /jobs/{id} or webhook ──> final result
~~~

## 4. Demonstration with Spring Boot 3.3, Java 17, and ActiveMQ Artemis

The following example shows **two different entry points**: one endpoint calls HTTP and waits for the result, and one endpoint sends to a JMS queue and returns `202`. To run the demo in a single small app, the `/internal/process` endpoint acts as a **mock downstream HTTP service**; in a real system it would normally live in a separate service. The listener only logs to show independent message processing, and is not a production state-management implementation.

**Project structure:**

~~~text
spring-jms-comparison/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/
    │   ├── ComparisonApplication.java
    │   ├── TaskController.java
    │   └── TaskListener.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'spring-jms-comparison'
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
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
~~~

Before running, you need an **ActiveMQ Artemis broker** with JMS/Netty port `61616`, account `demo/demo`, and queue `demo.jobs` (or broker config allowing queue auto-creation). These are local demo credentials; real environments must use secret management, authentication, and broker authorization.

`src/main/java/demo/ComparisonApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.web.client.RestClient;

@SpringBootApplication
@EnableJms
public class ComparisonApplication {
    public static void main(String[] args) {
        SpringApplication.run(ComparisonApplication.class, args);
    }

    @Bean
    RestClient downstreamClient(RestClient.Builder builder) {
        return builder.baseUrl("http://localhost:8080").build();
    }
}
~~~

`src/main/java/demo/TaskController.java`:

~~~java
package demo;

import java.util.Map;
import java.util.Objects;
import java.util.UUID;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class TaskController {
    private final RestClient downstreamClient;
    private final JmsTemplate jmsTemplate;

    public TaskController(RestClient downstreamClient, JmsTemplate jmsTemplate) {
        this.downstreamClient = downstreamClient;
        this.jmsTemplate = jmsTemplate;
    }

    public record JobRequest(String name) {}

    @PostMapping("/demo/sync")
    public Map<String, String> sync(@RequestBody JobRequest request) {
        String result = downstreamClient.post()
                .uri("/internal/process")
                .body(request)
                .retrieve()
                .body(String.class); // Wait for the downstream endpoint's HTTP response.

        return Map.of("state", "DONE", "result", Objects.requireNonNull(result));
    }

    @PostMapping("/demo/async")
    public ResponseEntity<Map<String, String>> async(@RequestBody JobRequest request) {
        String jobId = UUID.randomUUID().toString();
        jmsTemplate.convertAndSend("demo.jobs", jobId + "|" + request.name());
        // Sent to the broker per JMS operation, without waiting for TaskListener to process.
        return ResponseEntity.accepted()
                .body(Map.of("jobId", jobId, "state", "ACCEPTED"));
    }

    @PostMapping(value = "/internal/process",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public String process(@RequestBody JobRequest request) {
        return "processed:" + request.name();
    }
}
~~~

`src/main/java/demo/TaskListener.java`:

~~~java
package demo;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class TaskListener {
    @JmsListener(destination = "demo.jobs")
    public void consume(String payload) {
        System.out.println("JMS processed: " + payload);
    }
}
~~~

In the example, `JmsTemplate` uses the default converter to send a `String` as a JMS `TextMessage`, while the listener's `String payload` parameter is converted by Spring from the message content. Concatenating with `|` is **for demo purposes only**, not a production-ready message contract; real applications should use versioned JSON/schemas, validate required fields, and define compatibility rules.

Once the broker is ready, in the project directory run with an installed Gradle:

~~~bash
gradle bootRun
~~~

Send two requests (Bash shell syntax; on Windows PowerShell you can use `curl.exe` with appropriate JSON escaping):

~~~bash
curl -i -X POST http://localhost:8080/demo/sync \
  -H 'Content-Type: application/json' \
  -d '{"name":"invoice-42"}'

curl -i -X POST http://localhost:8080/demo/async \
  -H 'Content-Type: application/json' \
  -d '{"name":"invoice-42"}'
~~~

**Observed results:**
- `/demo/sync`: HTTP `200 OK` with fields `state: "DONE"` and `result: "processed:invoice-42"`; the endpoint waits for the downstream HTTP call to return. JSON field order is not guaranteed.
- `/demo/async`: HTTP `202 Accepted` with `state: "ACCEPTED"` and a UUID in `jobId`; the listener logs `JMS processed: <UUID>|invoice-42`, and the log line does not necessarily appear after the HTTP response.
- If the broker cannot be reached, `convertAndSend` can fail; this example **does not** automatically persist a fallback in a database and **has no** endpoint to query actual status.

Because the Spring program needs dependencies and a broker, it cannot be compiled standalone with `javac TaskController.java`. The proper way to run it is `gradle bootRun` with Java 17+ and dependencies resolved by Gradle.

## 5. Reliability: What Happens When Errors Occur?

### 5.1. Errors in Synchronous HTTP

If an HTTP client times out, there are at least two possibilities: the server has not processed it yet, or the server finished processing but the response was lost/delayed. Therefore **a timeout does not mean the task did not run**. Unconditionally retrying an order-creation or payment-charge call can create duplicate data.

Risk mitigation: set explicit timeouts, bounded retries with backoff and jitter, circuit breakers where appropriate, and use an **idempotency key** so the server recognizes repeated calls for one logical operation. For operations requiring atomicity, query server-side state rather than inferring entirely from network errors.

### 5.2. Errors in Asynchronous JMS

| Failure Point | What Can Happen | Required Design |
| --- | --- | --- |
| Producer fails to send because broker is down | No job in the queue; API may return an error | Do not return "accepted for processing" unconditionally; consider outbox if commands must not be lost |
| Broker accepted, consumer is stopped | Message waits in queue if retention config remains valid | Persistent delivery, backlog limits, sensible TTL, alerts when queue grows |
| Consumer throws exception before acknowledging | May rollback/redeliver depending on transaction, ack, and broker | Configure listener transactions, retry/backoff policies, DLQ |
| Consumer writes DB then crashes before JMS ack/commit | Message may be redelivered even though the side effect occurred | Idempotent consumer, unique key per eventId/jobId |
| Invalid or perpetually failing message | Repeated processing clogs/wastes resources | Error classification, max retry attempts, dead-letter queue, controlled replay tools |
| Long queue backlog | Client already got `202` but outcome arrives late | Monitor oldest-message age, queue depth, throughput, business deadlines/timeouts |

**Do not assume JMS provides business-level exactly-once by default.** JMS provides acknowledgment, transaction, redelivery, and delivery mode mechanisms; actual guarantees depend on the broker, client, configuration, and transaction boundaries. The database and JMS broker are usually **two independent transactional resources**. A local JMS transaction does not automatically combine a database update and message ack into one atomic transaction. A common way to achieve **effectively-once business outcome** is:
1. Every message carries an `eventId`/`jobId` stable across redeliveries.
2. The consumer marks it processed via a database operation with a unique constraint or an atomic update in the same transaction as the side effect.
3. If an already-processed ID is encountered, the consumer skips the side effect while still completing the appropriate ack/commit mechanism.
4. Monitor failed messages and replay intentionally; do not assume every exception goes automatically to a DLQ.

For example, place a unique constraint on column `processed_event_id` (or a dedup table) in the same database transaction as the state update. Simply checking "does ID already exist?" with a separate SELECT before writing is not safe enough when multiple consumers run concurrently.

## 6. Frequently Overlooked Differences

**Queue vs. Topic:** in JMS, a **queue** fits work distribution (each message processed by one consumer in a competing group); a **topic** fits publish–subscribe (multiple subscriptions can receive the same message). Topics only receive messages while offline if a durable subscription mechanism and appropriate broker retention are configured; do not infer that every topic retains messages indefinitely.

**Ordering:** increasing listener concurrency improves throughput, but with multiple messages related to the same order, completion order can change. If ordering is a business constraint, design around entity keys, sequences/versions, and proper serialization/partitioning; do not rely on a gut feeling that "queues are always FIFO".

**Data contracts:** HTTP typically has request/response schemas, status codes, and timeouts. JMS needs message schemas and versions, destination names, content types, message ID/correlation ID, TTL, and rules for handling stale messages. Renaming fields or changing message semantics without compatibility management can break older consumers.

**Observability:** for HTTP, measure per-endpoint latency, 4xx/5xx status codes, in-flight requests, and cross-service traces. For JMS, also measure queue wait time, consumer processing time, redelivery counts, queue depth, DLQ, broker health, and correlation IDs linking the job-creation request to processing steps. A "sent" log alone does not prove business success.

**Load throttling:** queues decouple ingestion rate from processing rate **within the limits** of broker capacity and storage policies. If producers stay faster than consumers continuously, backlog and latency will grow. You need rate limits, message quotas, appropriate consumer counts, scaling plans, queue-age alerts, and overload policies.

**Security:** both HTTP and JMS need authentication, authorization, and connection/data protection. For JMS, enforce per-destination publish/consume permissions, TLS, secret management, and avoid putting unnecessary sensitive data into payloads/logs/DLQs. Messages can be persisted on broker disk, so retention policies matter as well.

## 7. Which Model Should You Choose?

**Prefer synchronous HTTP when** the caller needs the result immediately to make a decision within the same interaction, the operation is short, the response SLA is clear, and timeout/idempotency handling is in place. Examples: querying current stock, validating access permissions, calculating charges for user confirmation before payment.

**Prefer asynchronous JMS when** work can complete later, traffic fluctuates, producer–consumer lifecycles need decoupling, or work must be processed after a consuming service pauses. Examples: generating invoices, sending emails, syncing data to external systems, generating reports, post-transaction event processing.

**Combining both** often makes sense: HTTP receives the request, validates it, and returns `202` with a `jobId`; JMS distributes the work; HTTP `GET /jobs/{id}` or a webhook delivers the outcome later. In this architecture, clearly define:
- `ACCEPTED`: under what durable contract has the request been accepted (saved in DB/outbox or confirmed by broker)?
- `PROCESSING`: worker began execution; heartbeat/lease if the job is long-running.
- `SUCCEEDED / FAILED`: final state, timestamp, error cause, and whether it can be retried.
- Business deadlines, message retention/TTL, retry mechanisms, idempotency, and result notification channels.

### A Few Misconceptions to Avoid

1. **"Returning HTTP 202 means processing succeeded."** False: `202` only states the request was accepted for processing; a mechanism to confirm the later outcome is needed.
2. **"With JMS, messages are never lost."** False: it still depends on persistent delivery, broker storage/HA, TTL, transactions, failure policies, and how the producer guarantees sending.
3. **"Retries guarantee exactly-once."** False: retries can create duplicates; idempotency and transaction boundaries must be designed.
4. **"JMS is always faster than HTTP."** False: JMS adds a broker and queue waiting; it optimizes temporal decoupling and load leveling, not automatically total processing time.
5. **"Using `@Async` can replace JMS."** False: `@Async` runs tasks on an executor within the current process, without built-in persistent queues, redelivery, or recovery across restarts.
6. **"Adding more consumers is always better."** False: it can affect ordering, database contention, downstream rate limits, and the number of concurrently processed messages.

## 8. Design Checklist and Self-Check Questions

When moving an operation from synchronous HTTP to JMS, answer: what information does the caller need **immediately**; under what condition is `202` allowed; how is the outcome queried/notified; how long are messages and job states retained; how do broker/consumer/database failures recover; can a redelivered message cause duplicate side effects; and who monitors queues and DLQs?

**Self-check:**
1. Client receives `202` but the consumer has not run yet. What ensures the job is not lost, and how does the client learn the status?
2. Consumer wrote an invoice to the DB and crashed before JMS ack. How will a redelivered message be handled safely?
3. If the user needs to know "is it in stock or not" before clicking confirm, why is synchronous HTTP usually more suitable than putting a command on a queue and waiting for the result?

**Remember:** the most important question is not "is HTTP or JMS more modern", but **whether the business flow needs the result in the same request or can accept later completion**, and how the system will publish, retain, recover, and observe that outcome.

## References

- Spring Framework – JMS Receiving a Message: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring Framework – Annotation-driven JMS Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Boot 3.4 – JMS and ActiveMQ Artemis: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
