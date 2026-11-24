# Measuring Failures, Retries, and Dead-Letter Messages

## 1. Context: Observing an Integration Flow with Failures

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot connects systems via HTTP clients, databases, caches, message brokers, and Spring Integration adapters. These flows must manage configuration, data contracts, transactions, failures, deduplication, testing, and observability. A failing HTTP request, a consumer reprocessing a message, or a message routed to dead-letter all impact business quality yet **cannot be measured by a single vague counter named `errors`**.

Example flow receiving an **OrderPaid** message from RabbitMQ or Kafka:

~~~mermaid
flowchart TD
    A["Broker / inbound adapter"] --> B["Receive one message delivery"]
    B --> C["Validate + process business logic"]
    C --> D{"Processing result"}
    D -->|"Success"| E["Commit/ACK appropriately"]
    D -->|"Transient error"| F["Bounded retry"]
    F --> C
    D -->|"Non-retryable error"| G["Handle terminal failure"]
    F -->|"Retries exhausted"| G
    G --> H{"Recovery policy"}
    H -->|"Confirmed dead-letter"| I["DLQ or DLT"]
    H -->|"Failed to publish"| J["Publish failure / incident needing action"]
    H -->|"Keep for reprocessing"| K["Requeue / error flow"]
~~~

A delivery can fail on its first execution yet succeed on retry. Therefore, you must answer separately:

1. **How many executions actually failed?**
2. **How many retries actually ran?**
3. **How many deliveries or events ended in failure?**
4. **How many messages actually reached the dead-letter queue/topic?**

Lesson objectives:

- Identify the exact events to count, when to increment counters, and metric scope.
- Use Micrometer, Spring Boot Actuator, and Spring Integration's built-in observability.
- Instrument counters for retries, final failures, dead-letters, and recovery without altering broker semantics.
- Design dashboards, alerts, logs/traces, and tests proving metrics are accurate.
- Distinguish application errors, delivery errors, redeliveries, poison messages, duplicates, and downstream overload.

## 2. Distinguishing Message, Delivery, Attempt, and Outcome

Before naming metrics, establish a shared vocabulary:

| Unit | Meaning | How many can one event produce? |
| --- | --- | --- |
| **Business event** | Logical event identified by business `eventId` or `operationId` | One |
| **Delivery** | One broker/adapter delivery of an event to the application | One or more due to redelivery |
| **Processing attempt** | One execution of processing logic, including initial attempt and each retry | One or more within a delivery |
| **Retry started** | A subsequent attempt executed after the prior attempt failed | From 0 up to the retry limit |
| **Attempt failure** | One handler execution throwing an error | Possibly multiple for the same delivery |
| **Final failure** | A delivery ending unsuccessfully after the retry policy | Usually at most one final outcome per delivery |
| **Dead-letter intent** | App decides to route or reject the message toward DLQ/DLT | Does not prove the broker received it |
| **Dead-letter confirmed** | Evidence of successful publish or verified broker routing | Does not mean a DLQ consumer processed it |
| **Dead-letter observed** | A consumer or broker metric observes a message at the DLQ/DLT | Can repeat if DLQ messages are also redelivered |

**Received delivery ≠ unique business event**: if the broker delivers the same `eventId` three times, the adapter's received counter may increment three times. Counting unique events requires deduplication/idempotency state or a count over an authoritative store.

### Arithmetic Example

Over 5 minutes, the application receives 100 deliveries:

- 60 deliveries succeed on the first attempt.
- 30 deliveries fail on the first attempt, retry once, and succeed.
- 10 deliveries fail on the first attempt, retry once, still fail, and are confirmed routed to dead-letter.

Results:

| Metric | Value |
| --- | ---: |
| Delivery received | 100 |
| Processing attempts | 140 |
| Retry attempts started | 40 |
| Attempt failures | 50 |
| Final delivery successes | 90 |
| Final delivery failures | 10 |
| Dead-letter confirmed | 10 |

Here the **per-attempt failure rate** is 50/140 ≈ 35.7%, whereas the **final delivery failure rate** is 10/100 = 10%. Those two numbers answer different questions. If a dashboard displays 35.7% and labels it "failed orders", operators will draw the wrong conclusion.

When setting business targets, measure **business success** or **unique operation success** at a verifiable commit point rather than inferring from ACKs or HTTP 200 alone.

## 3. Starting with Spring Boot Actuator and Micrometer

### 3.1. Dependencies

Maven example using Spring Boot parent/BOM version management:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

If using retries via **RetryTemplate** as shown later, add **org.springframework.retry:spring-retry** at a project-compatible version. Kafka, RabbitMQ, or JDBC adapters require their own starters/modules; Actuator does not automatically create brokers, DLQs, or retry policies.

### 3.2. Controlled Metric Exposure

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"
  metrics:
    tags:
      application: order-integration
~~~

This example exposes **/actuator/metrics** and **/actuator/prometheus** when the app has the required dependencies and permissions. Secure management endpoints with network controls, authentication, and authorization policies; never expose all endpoints or put management endpoints on the public Internet.

Once real traffic flows:

~~~text
GET /actuator/metrics
GET /actuator/metrics/app.integration.delivery.received
GET /actuator/prometheus
~~~

Custom metrics appear only after registration/invocation or eager initialization. Across multiple instances, Prometheus scrapes each instance and dashboards aggregate; **in-process counters reset when an app restarts**. Never naively sum cumulative counter values while ignoring resets.

## 4. What Do Built-In Spring Integration Metrics Measure?

Spring Integration integrates Micrometer across many components such as channels, handlers, and message sources. However, **framework metrics measure component activity**; they do not inherently know whether business work finished, whether a retry began, or whether a message actually reached a DLQ.

With Spring Integration's traditional meter mechanism:

| Common meter | Meaning |
| --- | --- |
| **spring.integration.send** | Timer for sending to a channel or processing at a handler; usually tagged with result/exception |
| **spring.integration.receive** | Counter for receiving from a pollable channel or message source |
| **spring.integration.channel.queue.size** | Gauge for `QueueChannel` depth |
| **spring.integration.channel.queue.remaining.capacity** | Gauge for remaining `QueueChannel` capacity |
| **spring.integration.channels / handlers / sources** | Gauges for component counts in the application context |

Depending on version, instrumentation using **Micrometer Observation** also creates metrics such as **spring.integration.gateway**, **spring.integration.handler**, **spring.integration.producer**, and related long-task timers. Observations can combine metrics and tracing.

### 4.1. Enabling Observation for Components to Monitor

In Spring Integration 6.x+ you can use:

~~~java
@Configuration
@EnableIntegration
@EnableIntegrationManagement(observationPatterns = "order*")
public class IntegrationManagementConfiguration {
}
~~~

For components matching the **order*** pattern to be instrumented with Observation, the app needs a configured **ObservationRegistry** (typically via Spring Boot Actuator) and active management. Setting **observationPatterns = "*"** covers all components yet adds load and span volume; choose patterns that keep overhead controlled. Never assume adding the annotation alone produces metrics without a registry or export pipeline.

**Note:** **traditional Micrometer meters** and **Observation** are two mechanisms with distinct naming/tagging conventions; some paths supersede others. Before building dashboards, check the actual metrics emitted by your Spring Boot/Spring Integration version. **Never sum both metric sets as if they were two independent executions.**

### 4.2. Why Custom Business Metrics Are Still Needed

A handler might catch an exception, retry, and return success. The outer handler timer records **success**, even though two internal downstream failures occurred. Conversely, an error flow may consume an `ErrorMessage` and finish cleanly while the original business operation remains incomplete.

Beyond built-in meters, explicitly instrument key events such as:

- A **processing attempt** actually starting.
- A **retry attempt** actually starting.
- Handler failing transiently or permanently using a stable classification.
- Delivery finishing with **success** or **failure**.
- A message chosen for DLQ/DLT routing, confirmed published, and queued pending in the dead-letter destination.

## 5. Designing a Counter Contract

A consistent contract keeps development, QA, and operations aligned on definitions.

| Proposed Micrometer name | Type | When incremented? | Recommended tags |
| --- | --- | --- | --- |
| **app.integration.delivery.received** | Counter | Adapter admits a delivery into the flow | flow, source |
| **app.integration.processing.attempts** | Counter | Before each invocation of processing logic | flow, operation |
| **app.integration.processing.attempt.failures** | Counter | An attempt throws an error | flow, error_kind |
| **app.integration.retry.started** | Counter | A second or subsequent attempt starts | flow, operation |
| **app.integration.delivery.outcomes** | Counter | Delivery finishes as success or failure | flow, result |
| **app.integration.deadletter.decisions** | Counter | Choosing to route to DLQ/DLT | flow, reason |
| **app.integration.deadletter.confirmed** | Counter | Appropriate confirmation that DLQ/DLT publish succeeded | flow, destination |
| **app.integration.deadletter.observed** | Counter | A consumer reads a message at the DLQ/DLT | destination, source |
| **app.integration.redrive.completed** | Counter | A redrive is confirmed complete per policy | destination, result |
| **app.integration.handler.duration** | Timer | Duration of an attempt or full delivery—pick one | flow, result |

These names are **proposed conventions for the example application**, not default metrics from Spring Integration or RabbitMQ/Kafka.

**Follow Prometheus naming conventions:** Micrometer accepts dotted names like **app.integration.retry.started**. The Prometheus exporter normalizes this to **app_integration_retry_started_total**. Never append an extra **_total** suffix when defining a `Counter` in Java and then add another in PromQL. Always inspect actual names on **/actuator/prometheus**, as naming conventions can vary across registries and versions.

### Low-Cardinality Tags

Suitable tags:

~~~text
flow = paid-order | inventory-sync | shipment-updates
source = rabbitmq | kafka | http
error_kind = timeout | unavailable | invalid_payload | conflict | other
result = success | failure
destination = paid-order-dlq | inventory-dlt
~~~

**Never** place these values into metric tags: `eventId`, `requestId`, `orderId`, `customerId`, URLs containing dynamic IDs, stack traces, raw messages, arbitrary library exception names, or `tenantId` with millions of values. They explode time-series counts, Prometheus costs, and query latency.

For exceptions, **classify** into a fixed set:

| error_kind | Examples | Usually retryable? |
| --- | --- | --- |
| timeout | Read/connect timeout, response deadline | Possibly, depending on idempotency |
| unavailable | Downstream DB/broker/HTTP temporarily unreachable | Possibly, with bounded backoff |
| rate_limited | HTTP 429 or downstream limiter | Follow `Retry-After` and budget |
| invalid_payload | Malformed JSON/schema, missing required fields | No; fix data or DLQ |
| business_rejected | Insufficient stock, business conflict | Do not retry blindly |
| duplicate | Already-processed event | Usually not a system error |
| other | Unclassified error | Investigate and assign explicit policy |

## 6. Minimal Instrumentation with `MeterRegistry`

A dedicated meter helper keeps handlers free of repetitive Micrometer boilerplate. The example below uses a static **flow** tag from configuration; raw `eventId` is never passed as a tag.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class IntegrationMeters {

    private final MeterRegistry registry;

    public IntegrationMeters(MeterRegistry registry) {
        this.registry = registry;
    }

    public void received(String flow, String source) {
        registry.counter("app.integration.delivery.received",
                "flow", flow, "source", source).increment();
    }

    public void attempt(String flow, String operation) {
        registry.counter("app.integration.processing.attempts",
                "flow", flow, "operation", operation).increment();
    }

    public void attemptFailure(String flow, String errorKind) {
        registry.counter("app.integration.processing.attempt.failures",
                "flow", flow, "error_kind", errorKind).increment();
    }

    public void retryStarted(String flow, String operation) {
        registry.counter("app.integration.retry.started",
                "flow", flow, "operation", operation).increment();
    }

    public void finalOutcome(String flow, String result) {
        registry.counter("app.integration.delivery.outcomes",
                "flow", flow, "result", result).increment();
    }

    public void deadLetterDecision(String flow, String reason) {
        registry.counter("app.integration.deadletter.decisions",
                "flow", flow, "reason", reason).increment();
    }

    public void deadLetterConfirmed(String flow, String destination) {
        registry.counter("app.integration.deadletter.confirmed",
                "flow", flow, "destination", destination).increment();
    }
}
~~~

**Usage preconditions:** `flow`/`source`/`errorKind`/`operation`/`result`/`destination` must come from an **application-controlled finite value set**, never directly from message payloads. Under very high throughput, pre-register fixed `Counter` instances in the constructor instead of looking up by tags each call; Micrometer still caches meters by ID. Incrementing a `Counter` mutates in-process state and does not substitute for business transactions.

### Why Not Count Failures in Every Catch Block?

Suppose an HTTP client throws an exception, the service catches it to retry, and an endpoint wraps it in `MessageHandlingException`. If all three layers increment the same **processing.failure**, dashboards report three errors for a **single failed attempt**.

Instead, choose **one canonical boundary**:

- **Attempt failure**: at the wrapper executing each attempt.
- **Final failure**: outside the retry policy, once the delivery ends in failure.
- **Dead-letter confirmed**: when the publish path or broker reports valid confirmation.

Lower-level errors can still have their own HTTP/JDBC/client metrics; never mix them into failed delivery counts.

## 7. Counting Retries Accurately with `RetryTemplate`

Example using Spring Retry 2.x via **RetryTemplate** and an operation idempotent by business event ID. The code demonstrates counting **retries that actually started**, not retries merely planned by policy.

~~~java
@Configuration
public class RetryPolicyConfiguration {
    @Bean
    RetryTemplate paymentRetryTemplate() {
        return RetryTemplate.builder()
                .maxAttempts(3)
                .exponentialBackoff(200, 2.0, 2000, true)
                .retryOn(TransientDownstreamException.class)
                .build();
    }
}

public class TransientDownstreamException extends RuntimeException {
    public TransientDownstreamException(String message) {
        super(message);
    }
}
~~~

**maxAttempts(3)** means **one initial attempt + at most two retries**. **retryOn** limits retries to designated exceptions; e.g., **IllegalArgumentException** from bad payloads should not be retried. Randomized backoff reduces thundering-herd retries across instances. Your project's Spring Retry version determines available builder overloads; check dependency compatibility with Spring Boot/Java.

Handler:

~~~java
@Service
public class PaidOrderProcessor {
    private static final String FLOW = "paid-order";
    private static final String OPERATION = "apply-payment";

    private final RetryTemplate retryTemplate;
    private final IntegrationMeters meters;
    private final PaidOrderService paidOrderService;

    public PaidOrderProcessor(
            RetryTemplate paymentRetryTemplate,
            IntegrationMeters meters,
            PaidOrderService paidOrderService) {
        this.retryTemplate = paymentRetryTemplate;
        this.meters = meters;
        this.paidOrderService = paidOrderService;
    }

    public void handle(OrderPaid event) {
        meters.received(FLOW, "rabbitmq");

        try {
            retryTemplate.execute(context -> {
                meters.attempt(FLOW, OPERATION);
                if (context.getRetryCount() > 0) {
                    meters.retryStarted(FLOW, OPERATION);
                }

                try {
                    paidOrderService.applyIdempotently(event);
                    return null;
                } catch (RuntimeException ex) {
                    meters.attemptFailure(FLOW, classify(ex));
                    throw ex;
                }
            });

            meters.finalOutcome(FLOW, "success");
        } catch (RuntimeException ex) {
            meters.finalOutcome(FLOW, "failure");
            // Hand back to adapter/recoverer to decide ACK, broker retry,
            // requeue, or dead-letter; throwing does not equal publishing to DLQ.
            throw ex;
        }
    }

    private String classify(Throwable error) {
        if (error instanceof TransientDownstreamException) {
            return "unavailable";
        }
        if (error instanceof IllegalArgumentException) {
            return "invalid_payload";
        }
        return "other";
    }
}
~~~

**OrderPaid** and **PaidOrderService** are application business types, not Spring classes. **applyIdempotently** must itself guard against duplicate writes in the database or target API; client-side retries alone do not make repeated writes safe.

Properties of this counting logic:

1. **received** increments once when the handler receives a delivery; broker redelivery creates a new delivery and increments again.
2. **attempts** increments before each business-logic run, including the initial attempt.
3. **retry.started** increments when **getRetryCount() > 0** inside the callback, meaning the retry has begun—not merely scheduled for backoff and canceled.
4. **attempt.failures** increments exactly once per exception escaping the attempt wrapper.
5. **delivery.outcomes{result=success|failure}** increments once when retries either succeed or exhaust into final failure for the delivery.

When combined with **adapter/broker retries**, the same event can enter **handle** again upon redelivery; delivery metrics increment, while out-of-process retries need their own metrics. Never add Spring Retry counts and broker redeliveries as if they were the same unit.

### When Retries Are Canceled or Miss Deadlines

Suppose policy schedules a retry after a 2-second backoff, yet the service shuts down before it starts. Incrementing a counter at **schedule** time reports a retry that never ran. Measuring **retry_started** inside the callback after backoff finishes is more accurate; if you want to monitor retry pressure, add a separate **retry_scheduled** metric with its own definition.

End-to-end flow deadlines must also account for backoff duration, HTTP/DB calls, and queue wait times. A retry counter alone cannot tell whether requests breached SLOs; pair it with Timers/Observations and underlying client timeouts.

## 8. Dead-Letter: Count at the Right Moment

**Dead-letter queues (DLQ)** in RabbitMQ/JMS and **dead-letter topics (DLT)** in Kafka move failed messages differently. A processing failure and a decision to dead-letter **do not guarantee a message arrived at the destination**.

### 8.1. Three Milestones to Observe Separately

~~~mermaid
flowchart LR
    A["Handler exhausted / invalid payload"] --> B["DLQ/DLT decision"]
    B --> C["Publish, broker reject/nack, route"]
    C --> D["Destination received or confirmed"]
    D --> E["DLQ/DLT consumer reads"]
    B --> F["deadletter.decisions +1"]
    D --> G["deadletter.confirmed +1 if sufficient evidence"]
    E --> H["deadletter.observed +1"]
~~~

- **deadletter.decisions**: counts how often the system intended to route a message to the error path, useful for policy diagnostics.
- **deadletter.confirmed**: increments only when the adapter/publisher receives concrete confirmation of publish/routing per its mechanism. Never mark confirmed merely because code called an asynchronous **send()** method.
- **deadletter.observed**: counts deliveries read by a DLQ/DLT consumer. This proves messages arrived at the DLQ consumer input, though it can repeat if the DLQ consumer also experiences redeliveries.

With **broker-side dead-letter routing**, the application publisher normally receives no direct confirm for internal broker routing. In that case, **avoid forcing `deadletter.confirmed` inside the handler**; instead read broker metrics or observe the destination queue/topic, and only label metrics "confirmed" when backed by real evidence.

### 8.2. RabbitMQ: Dead-Letter Exchange and Republish Are Two Different Paths

**Path 1 — Broker dead-lettering:**

- The source queue must be configured with a dead-letter exchange/routing key or matching broker policy.
- When a consumer rejects/nacks with **requeue=false** or another dead-letter trigger fires, RabbitMQ can route to the DLX.
- If the DLX/route/target queue does not exist or broker policy changes, an exception in the app proves nothing about DLQ arrival.
- **AmqpRejectAndDontRequeueException** expresses a decision to reject without requeue; it does not prove DLQ delivery succeeded.

**Path 2 — Application republish:**

- **RepublishMessageRecoverer** in Spring AMQP can publish failed messages to a target exchange/topic after retries exhaust.
- When the recoverer completes without throwing, the container can ACK the original message; the broker does not automatically dead-letter simply because the class is named "recoverer".
- When publish confirmation is needed, consider **RepublishMessageRecovererWithConfirms** and matching publisher confirms/returns config. **Never increment confirmed before the publish/confirm succeeds.**

Pseudocode example for application republish with an explicit confirmation boundary:

~~~java
public void handleTerminalFailure(Envelope envelope, Throwable error) {
    meters.deadLetterDecision("paid-order", "retries_exhausted");

    // Application abstraction: returns only after publisher confirm succeeds;
    // throws an exception for recovery policy if publishing fails.
    confirmedDeadLetterPublisher.publishAndConfirm(
            "paid-order-dlq", envelope, error);

    meters.deadLetterConfirmed("paid-order", "paid-order-dlq");
}
~~~

**Envelope** and **ConfirmedDeadLetterPublisher** are application-defined interfaces, not built-in Spring APIs. Production implementations must use the corresponding broker adapter, handling publisher confirms, returns/unroutable messages, and transactions/ACKs. For stricter guarantees, an outbox can coordinate publishing and ACKs.

### 8.3. Kafka: DLT and DLT Consumers

With Spring Kafka, **DefaultErrorHandler**, **DeadLetterPublishingRecoverer**, or **@RetryableTopic** can forward messages to a DLT per configured retry policy. Distinguish:

- Synchronous retries inside the listener container.
- Non-blocking retries via retry topics creating records on intermediate topics.
- Internal Kafka client producer retries, which do not necessarily count as new business attempts.
- DLT publishing may be asynchronous; calling `send` is not proof the broker wrote the record.

A listener dedicated solely to **observing deliveries entering a DLT** can look like:

~~~java
@Component
public class DeadLetterObserver {
    private final MeterRegistry meters;

    public DeadLetterObserver(MeterRegistry meters) {
        this.meters = meters;
    }

    @KafkaListener(
            topics = "orders.DLT",
            groupId = "orders-dlt-observer")
    public void observe(ConsumerRecord<String, String> record) {
        meters.counter("app.integration.deadletter.observed",
                "destination", "orders.DLT",
                "source", "kafka").increment();

        // Payload handling, ACK/commit, and redrive decisions must be
        // designed separately. This only measures one DLT delivery.
    }
}
~~~

This snippet requires Spring Kafka dependencies and matching consumer/deserializer config. It counts **DLT record deliveries to the listener**, not unique logical events or current DLT backlog. If this consumer is strictly an observer, factor in offset commits and read cost; do not spin up a new consumer just to count if broker/exporter metrics already cover it.

### 8.4. Spring Integration `errorChannel` Is Not a DLQ

In asynchronous flows, Spring Integration can wrap exceptions into an **ErrorMessage** and send it to **errorChannel**. With **RequestHandlerRetryAdvice**, **ErrorMessageSendingRecoverer** can route final errors to a recovery channel. That is an **in-application error-handling channel**, not a broker dead-letter queue/topic.

Completing an error flow does not prove a message reached a DLQ. Measure the **actual publish/routing action**, its confirmation, and subsequent ACK. If the flow only logs `ErrorMessage` and ACKs the source, name the metric **error_handled** or **terminal_failure**, never **deadletter.confirmed**.

## 9. Combining Application Metrics with Broker Data

Application counters and broker gauges/stats view the flow from opposite sides:

| Data source | Answers well | Cannot answer by itself |
| --- | --- | --- |
| App **retry.started** counter | How many in-process retries started | How many broker redeliveries or client producer retries occurred |
| App **delivery.outcomes** counter | How often handler returned success/failure | How many unique business events finished |
| App **deadletter.decisions** counter | How many dead-letter routing decisions occurred | Whether the destination received them |
| Broker **DLQ depth/lag** | How many messages remain unconsumed/queued | All-time total messages ever dead-lettered |
| Broker **DLQ ingress/publish rate** | Rate of messages written/routed to destination per exporter | Which handler failed without correlation |
| DLQ consumer **observed** | How many deliveries were seen at the DLQ | How many unique logical events; whether handled cleanly |

Reconciliation example:

~~~text
Application decided dead-letter 40 times
   ↓
Publisher confirmed success 37 times
   ↓
Broker recorded 37 traceable publishes/routes
   ↓
DLQ still holds 32 messages after processing/redrive
~~~

The three failed publishes need their own retry/alert path; never assume they reached the DLQ. **DLQ depth** also reflects consumers, TTLs, deletions, redrives, and broker policies; never expect depth to equal total DLQ decisions.

**Never increment a Counter by polling queue depth.** Queue depth is a gauge capturing a point-in-time snapshot; a counter tracks cumulative occurrences over time. A queue can currently hold 0 messages even after 10,000 messages passed through and finished.

## 10. Dashboards and Prometheus Queries

The examples below assume Micrometer exports these Counters under matching Prometheus names:

### Delivery and Retry Rates

~~~promql
sum by (flow) (
  rate(app_integration_delivery_received_total[5m])
)
~~~

~~~promql
sum by (flow) (
  rate(app_integration_retry_started_total[5m])
)
~~~

### Final Delivery Failure Ratio

~~~promql
sum by (flow) (
  rate(app_integration_delivery_outcomes_total{result="failure"}[5m])
)
/
clamp_min(
  sum by (flow) (
    rate(app_integration_delivery_outcomes_total[5m])
  ),
  1e-9
)
~~~

This ratio's denominator is **deliveries with a final outcome**. It does not measure unique events and can skew if many deliveries are still in flight. For end-to-end SLOs, add latency and business-pending counts.

### Confirmed Dead-Letters in One Hour

~~~promql
sum by (flow, destination) (
  increase(app_integration_deadletter_confirmed_total[1h])
)
~~~

To see whether dead-letters are piling up, pair with a **DLQ depth / Kafka consumer lag gauge** from your broker exporter using its real metric name, as `IntegrationMeters` does not emit that gauge.

### Why Numbers Might Not Sum Cleanly

Never write rigid assertions like:

~~~text
received = success + failure + dead-letter
~~~

Because:

1. **dead-letter** may be a sub-outcome of **failure**, so adding both double-counts.
2. Deliveries in progress, awaiting backoff, or pending ACK have no final outcome yet.
3. Redelivered messages make delivery counts exceed unique event counts.
4. Process restarts reset counters, and scrape alignment or dropped samples cause temporary skew.
5. Broker-routed dead-letters or out-of-process producer retries may not appear in app counters.

Accurate reconciliation requires matching **the same unit, message set, time window, and commit boundary**.

## 11. Alert on Behavior, Not a Single Isolated Number

| Signal | Operational meaning | First action |
| --- | --- | --- |
| Final failure rate climbing steadily | Downstream service, payload, or code broken | Break down by `error_kind`, deployments, and traces |
| `retry.started` rising while final failures stay flat | Transient glitches currently masked by retries | Check latency and retry budgets |
| Both retries and final failures rising | Retries are not recovering | Check availability/rate limits and shed load |
| Dead-letter decisions rising without confirmed rising | DLQ publishing may be failing or losing confirms | Check publisher confirms, returns/unroutable |
| DLQ depth or Kafka DLT lag growing steadily | Error-handling/redrive team falling behind | Triage poison messages, scale handling safely |
| Retries low yet p99 latency climbing | Waiting on connections, locks, pools, or uninstrumented retries | Inspect timers, queues, and client metrics |
| Same poison message looping repeatedly | Validator/retry policy misclassifying errors | Route non-retryable errors to dead-letter |

No universal threshold like **5 errors/min** or **DLQ > 0** fits every system. Base thresholds on traffic, SLOs, event criticality, baselines, and business impact. In payment flows, even one poison message may demand investigation; in analytics pipelines, occasional errors may fit within an agreed budget.

Dashboards should bring together **traffic, errors, latency, saturation, and dead-letter backlog**, with links from alerts to logs/traces. Never alert simply because a cumulative counter is non-zero: counters never decrease and can retain errors resolved days ago.

## 12. Linking Metrics, Logs, and Distributed Tracing

Metrics reveal scale, logs reveal cause, and traces locate the failing hop across services. An investigation path:

~~~text
Alert: retry.started rising on flow=paid-order
   ↓
Metric: attempt.failures{error_kind="timeout"} rising
   ↓
Trace: inbound AMQP/Kafka → handler → downstream HTTP
   ↓
Log: timeout calling payment-gateway, retry attempt=2
   ↓
Assess: slow upstream, overly long deadline, or exhausted pool?
~~~

Useful attributes in **controlled logs or spans**:

- `traceId`/`spanId`, flow name, operation, and adapter.
- Business event ID or request ID handled per data policy.
- Delivery attempt, retry index, classified `error_kind`.
- Downstream name, HTTP/SQL/broker status, and wait time.
- DLT/DLQ publish outcome and correlation ID upon confirm.

**Distinguish high cardinality between logs/traces and metrics:** `eventId` may be essential in access-controlled logs to trace one event, yet **must not** become a `Counter` tag. Across brokers, verify trace context propagation between producer and consumer alongside sampling; a sampled-out trace does not mean processing failed to run.

### Retries or DLQs Can Lose Context

When an event moves to a retry topic or DLQ, the new message may have different headers/baggage or start a new trace. To maintain continuity, preserve safe correlation metadata (original topic/queue, `eventId`, attempt, `error_kind`) without stuffing unbounded stack traces or sensitive data into headers. Agree on retention, size limits, and access controls for dead-letter payloads.

## 13. Testing Metrics Against the Contract

Tests checking only that "the handler ran once" are not enough to trust dashboards. Use **`SimpleMeterRegistry`** in unit tests to verify counters, and real brokers in integration tests to verify requeues, ACKs, and dead-letter routing.

### 13.1. Testing `RetryTemplate`: Two Retries After Initial Attempt

Broker-independent example:

~~~java
@Test
void twoRetriesAreCountedAsTwoStarts() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    IntegrationMeters meters = new IntegrationMeters(registry);

    RetryTemplate retry = RetryTemplate.builder()
            .maxAttempts(3)
            .fixedBackoff(1)
            .retryOn(TransientDownstreamException.class)
            .build();

    AtomicInteger invocations = new AtomicInteger();

    retry.execute(context -> {
        meters.attempt("paid-order", "apply-payment");
        if (context.getRetryCount() > 0) {
            meters.retryStarted("paid-order", "apply-payment");
        }
        if (invocations.incrementAndGet() < 3) {
            meters.attemptFailure("paid-order", "unavailable");
            throw new TransientDownstreamException("Temporary");
        }
        return null;
    });

    assertEquals(3, invocations.get());
    assertEquals(3.0, registry
            .get("app.integration.processing.attempts")
            .tag("flow", "paid-order")
            .tag("operation", "apply-payment")
            .counter().count());
    assertEquals(2.0, registry
            .get("app.integration.retry.started")
            .tag("flow", "paid-order")
            .tag("operation", "apply-payment")
            .counter().count());
    assertEquals(2.0, registry
            .get("app.integration.processing.attempt.failures")
            .tag("flow", "paid-order")
            .tag("error_kind", "unavailable")
            .counter().count());
}
~~~

JUnit 5, `AtomicInteger`, `RetryTemplate`, and `SimpleMeterRegistry` imports are omitted. The test proves callback-level attempt/retry counting; **it does not prove broker ACKs or DLQ publishing**.

### 13.2. Integration Test Scenarios

| Scenario | Expected counts | Non-metric checks |
| --- | --- | --- |
| Succeeds immediately | attempts=1, retry=0, final success=1 | Commit/ACK succeeded |
| Two transient errors, third succeeds | attempts=3, retry=2, attempt failures=2, final success=1 | No duplicate side effects |
| Invalid payload | retry=0, final failure=1 | Poison message routed per policy |
| Retries exhausted, dead-letter publish succeeds | final failure=1, decision=1, confirmed=1 | Message exists in target broker queue/topic |
| Dead-letter publish fails | decision=1, confirmed=0 | Original message retains a recovery path |
| Broker redelivers an event after crash | received delivery increments | Business effect stays idempotent |
| Worker dies during backoff | `retry_scheduled` may exist, `retry_started` does not increase | Message properly recovered/re-dispatched |
| DLQ consumer reads message again | `observed` increments per delivery | Not mistaken for unique events |
| Two instances process same `eventId` | Metrics aggregate per instance; do not infer exactly-once | Idempotency store blocks duplicate effects |

For RabbitMQ, test real queues, DLXs, and publisher confirms; for Kafka, test real consumer config, error handlers, DLT topics, and producer acks. Testcontainers or managed test brokers are far more valuable than mocking `send()` to return success.

### 13.3. End-to-End Metric Verification

1. Send a test message with a known `eventId` and a controllable transient error.
2. Verify the handler retries the expected number of times, returns the expected outcome, and commits business state only once.
3. Query **/actuator/metrics** or **/actuator/prometheus**; confirm exact exported names, tags, and values.
4. Trigger a non-retryable error into the terminal failure branch; verify DLQ/DLT in the real broker.
5. Reconcile decision, confirmed, observed, and backlog after waiting for exporter/scrape convergence.
6. Restart one instance to verify dashboards handle counter resets and redelivery semantics cleanly.

## 14. Common Misconceptions

**"First attempt failed then retry succeeded still counts as a failed message."** Not if the metric measures final failure. Count attempt failures and final outcomes separately.

**"Putting Counters inside catch blocks across three layers gives more accurate counts."** It easily counts the same exception multiple times. Pick one canonical measurement point per unit.

**"RetryTemplate `maxAttempts=3` means three retries."** False. It means at most three attempts total, including the initial attempt.

**"Calling `deadLetterSender.send()` guarantees a message is in the DLQ."** Insufficient with async publishers, unroutable exchanges/topics, or broker-side DLXs. Measure confirms or broker stats.

**"Counting `ErrorMessage` on `errorChannel` counts dead-letters."** Error channels are in-app error routing; attach dead-letter metrics only when the flow actually publishes a dead-letter.

**"DLQ queue depth is the total errors for the day."** Queue depth is current remaining messages; messages may enter and be consumed or redriven.

**"A message redelivered twice means two business events."** Use stable event IDs and unique counting if you want unique business events.

**"In-app counters don't need reset handling."** Cumulative counters reset on process restart; in Prometheus, use `rate`/`increase` with proper instance labels.

**"Just tag `eventId` to find errors fast."** `eventId` causes high cardinality; use log/trace correlation instead of metric tags.

**"Micrometer is enabled, so all retry and DLQ metrics come automatically."** Frameworks provide component meters, while retry policies, DLQ publish results, and business outcomes require explicit instrumentation at proper boundaries.

**"Sent to DLT means it's always safe to ACK."** Check publisher confirms, transactions, error handlers, and adapter semantics; if DLT publishing fails while the original is ACKed, messages can be lost.

## 15. Pre-Operations Checklist

1. Document definitions for **delivery, attempt, retry_started, final_failure, DLQ decision, DLQ confirmed, DLQ observed**.
2. Identify who drives retries: Spring Retry, Spring Integration advice, Kafka retry topics, Rabbit redelivery, HTTP client, or producer; avoid double counting.
3. Instrument attempts at execution start, final outcomes after retry completion, and dead-letters at verifiable evidence points.
4. Expose Actuator/Prometheus in a controlled manner; verify real metric names per version and registry.
5. Restrict `flow`, `operation`, `source`, `error_kind`, and `destination` tags to bounded value lists.
6. Classify errors into retryable vs. permanent, applying `maxAttempts`, backoff, jitter, deadlines, and idempotency.
7. On brokers, verify ACK/requeue, retry topics or DLXs, producer confirms, `errorChannel`, and fallback policy when DLT/DLQ publishing fails.
8. Pair application counters with broker ingress, DLQ backlog, consumer lag, and traces; never let one number represent the whole chain.
9. Test error taxonomy, retry counts, failure counts, dead-letter success/failure, restarts, and redeliveries.
10. Dashboards display traffic, errors, retries, latency, saturation, and backlog; alerts follow trends and SLOs with links to logs/traces.

**Conclusion:** To measure the true reliability of an integration flow, separate **per-attempt failures**, **executed retries**, **final delivery outcomes**, and **confirmed dead-letter events**. Spring Boot Actuator, Micrometer, and Spring Integration provide the observation foundation; the application must add contract-driven counters and reconcile them against broker metrics so failed messages are never misread.

## References

- [Spring Integration Reference — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html): channel/handler meters, `ObservationRegistry`, `@EnableIntegrationManagement`, and observation patterns.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `errorChannel`, `ErrorMessage`, and asynchronous error routing.
- [Spring Integration Reference — Provided Advice Classes](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html): `RequestHandlerRetryAdvice` and recovery channels.
- [Spring Boot Reference — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint exposure and security configuration.
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer, metric exporters, and naming conventions.
- [Spring Retry API — RetryTemplateBuilder](https://docs.spring.io/spring-retry/docs/2.0.x/apidocs/spring.retry/org/springframework/retry/support/RetryTemplateBuilder.html): `maxAttempts`, `retryOn`, and backoff.
- [Spring AMQP Reference — Resilience and Message Recovery](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html): `RepublishMessageRecoverer`, confirms, and ACK behavior.
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, and listener recovery.
