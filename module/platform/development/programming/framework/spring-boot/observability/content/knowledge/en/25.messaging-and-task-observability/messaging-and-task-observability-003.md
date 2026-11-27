# JMS instrumentation in Spring Boot

In the **Messaging and task observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module, JMS instrumentation observes message sending and receiving operations over Java Message Service. Spring Boot applications commonly send messages using `JmsTemplate` and process messages with a listener container such as `@JmsListener`. When instrumented, these operations can produce metrics and tracing context so operations teams know how many messages producers send, how long consumers take to process them, where errors occur, and which services a message traversed.

JMS is a messaging API; brokers such as ActiveMQ Artemis or IBM MQ handle storing and routing messages according to queue/topic configuration. Micrometer Observation and tracing integration observe application-side activity. They do not replace broker monitoring: queue depth, consumer count, enqueue/dequeue rates, redelivery, and broker storage still need to be monitored from the broker itself.

In **SPRING_BOOT_OBSERVABILITY**, messaging observability complements HTTP, database, metrics, logs, and distributed tracing. This lesson focuses on producer/consumer instrumentation, message lifecycle, context propagation via JMS properties, metrics and spans, retry/DLQ handling, cardinality, and end-to-end verification.

## 1. JMS flow and observation points

```text
orders-service (producer)
      |
      | JmsTemplate.convertAndSend(...)
      | message + trace context properties
      v
   JMS broker
      |
      | queue / topic
      v
payment-service (consumer)
      |
      | @JmsListener
      | extract context + process
      v
  database / downstream service
```

There are at least two operations to distinguish:

| Operation | Observation start/end point | Question |
| --- | --- | --- |
| Publish/send | Producer starts sending until the JMS provider completes the send operation | Is message sending failing or slow? |
| Process/receive | Consumer receives the message and executes the callback | How long does consumer processing take, and did it succeed or fail? |

A successful send duration does not mean the consumer has finished processing. Likewise, a completed consumer callback does not by itself prove the message has been committed/acknowledged according to transaction/session semantics. Distinguish broker acceptance, consumer processing, and acknowledgement.

## 2. JMS instrumentation in Spring Boot

Spring Boot can configure `ConnectionFactory`, `JmsTemplate`, and listener infrastructure based on dependencies and properties. Spring JMS's Micrometer Observation integration can instrument send and receive operations when enabled and supported by the version.

Common integration points:

- `JmsTemplate` for publish/send and request-reply operations.
- `@JmsListener` executed by a Spring-managed listener container.
- `ObservationRegistry` providing the registry for observations.
- Micrometer Tracing bridge/propagator capable of placing trace context into message properties and restoring context on the consumer when integration is configured.

Do not assume every Spring Boot/Spring Framework version automatically instruments in the exact same way. Check the dependencies, auto-configuration, observation conventions, and listener container factory in use. If you manually instantiate a `JmsTemplate` or container outside Spring configuration, Boot's customizers and observation wiring may not be applied.

### Dependencies and baseline configuration

Example dependencies for a Spring Boot application using JMS:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-artemis</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

The exact broker starter depends on the deployed provider. For other providers, use the corresponding starter/client. If tracing is needed, add a Micrometer Tracing bridge and exporter according to your application's observability architecture; do not install multiple tracing bridges at the same time.

Illustrative configuration example:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://artemis:61616
    user: JMS_USER
    password: retrieved from secret management/environment
  jms:
    template:
      qos:
        delivery-mode: persistent
        priority: 4
        time-to-live: 60000
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

Exact properties depend on the broker starter and Spring Boot version. Use secret management/environment injection for credentials; never commit real usernames/passwords into the repository or logs. Delivery mode, priority, and time-to-live settings must follow business requirements, not observability defaults.

## 3. Producer: observing sends with JmsTemplate

`JmsTemplate` is the Spring abstraction for sending and receiving messages. Example:

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
class OrderEventPublisher {
    private final JmsTemplate jmsTemplate;

    OrderEventPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    void publish(OrderCreated event) {
        jmsTemplate.convertAndSend("orders.created", event);
    }
}
```

When observation integration is wired, a send operation can create an observation/span with metadata such as destination, operation, and message context per convention. A successful `convertAndSend` call generally indicates the provider accepted the send operation under the current API; it does not prove the consumer has received or finished processing it.

If you add a manual timer around `convertAndSend`, clearly define the goal as measuring producer API call duration. Do not add a duplicate timer alongside built-in observation with the same semantics, or metrics will be double-counted or misleading.

### Low-cardinality message metadata

Producer metrics should generally be grouped by stable destination name, operation, and outcome. Avoid using message IDs, order IDs, customer IDs, correlation IDs, or raw payloads as metric tags.

| Dimension | Good example | Avoid |
| --- | --- | --- |
| Destination | orders.created | Queue name dynamically created per tenant |
| Operation | send, publish | Message ID |
| Result | success, error | Exception message |
| Broker cluster | Stable cluster name | Arbitrary per-request host/header |

Dynamic destinations per tenant or request can create very high cardinality. If the application has multiple tenants sharing a queue, keep tenant metadata in logs/traces per policy; do not make it a default metric tag.

## 4. Consumer: observing @JmsListener and listener containers

The Spring JMS listener container receives messages from the broker and invokes methods annotated with `@JmsListener`:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class PaymentEventListener {

    @JmsListener(destination = "orders.created")
    void onOrderCreated(OrderCreated event) {
        paymentService.startAuthorization(event);
    }
}
```

Consumer observation should cover message processing time. Depending on the listener container, transaction/session, and integration, the span/observation may start when the message is dispatched to the listener and end when the callback completes. Verify the exact behavior of your configured version and factory.

A consumer can receive a message, process it successfully, and acknowledge/commit; throw an exception causing transaction rollback or message redelivery; time out or have the process stop mid-flight; or send the message to a dead-letter queue per broker/redelivery policy.

Do not collapse all of these outcomes into a single "message received" metric. Separate receive/processing outcomes, redeliveries, and broker-level queue metrics if the system requires complete visibility.

## 5. Trace context propagation over JMS

HTTP typically passes trace context using `traceparent`/`tracestate` headers. JMS does not transmit HTTP headers; tracing instrumentation must inject/extract context via message properties or an appropriate carrier.

```text
Producer span
    |
    | inject trace context into JMS message properties
    v
Broker / queue
    |
    | message properties travel with message
    v
Consumer extracts context
    |
    v
Consumer processing span
```

When context propagation is configured properly, the consumer span can link to the producer's trace according to the propagator and messaging semantic conventions. Logs in the consumer can include the current context's Trace ID/Span ID. Metrics can use exemplars to link a sample to a trace if supported by the registry/backend.

Do not manually set a JMS property named `traceId` and assume W3C propagation is complete. Trace context has specific formatting and semantics; use the Micrometer Tracing/OpenTelemetry propagator or the stack's official integration.

### Parent-child or span link?

Messages may be processed asynchronously, delayed significantly, or fanned out to multiple consumers. The appropriate trace relationship depends on messaging semantic conventions and instrumentation version:

- Some integrations represent the consumer span as a child of the producer context.
- For batches or multiple message parent contexts, span links may be more appropriate than a single parent.
- Redelivery can create multiple processing attempts for the same message; each attempt needs its trace/span context represented clearly.

Do not assume every JMS provider/instrumentation uses the exact same span relationship. Verify actual traces in your backend and the conventions in effect.

## 6. Correlation ID, Message ID, and Trace ID

| ID | Meaning | Where used |
| --- | --- | --- |
| JMS Message ID | Message identifier assigned by the provider or per provider semantics | Broker diagnostics, duplicate investigation |
| Correlation ID | Application-defined convention linking request/reply or workflows | Logs and message headers |
| Trace ID | Distributed trace identifier | Tracing backend and log correlation |
| Span ID | Operation/span identifier | Identifying a specific processing step |
| Business ID | E.g., order ID/payment ID | Authorized business lookup |

In JMS, the `JMSCorrelationID` property is commonly used for request/reply correlation per API/provider convention. Do not overwrite `JMSCorrelationID` with Trace ID by default if doing so conflicts with the application's request/reply semantics. Trace propagation should use the carrier/property mapping managed by instrumentation; keep business correlation separate.

Message IDs and business IDs are nearly unique and unsuitable as metric tags. You may record them in logs or trace attributes per privacy/retention policy if genuinely needed for investigation.

## 7. Key metrics for producers and consumers

Micrometer/Spring integrations and broker exporters may provide different metrics. Useful metric concepts include:

| Metric concept | Side | Meaning |
| --- | --- | --- |
| Send count/rate | Producer | Number of messages sent over time |
| Send duration | Producer | Duration of the send operation via the JMS API |
| Send errors | Producer | Message send failures |
| Listener processing count | Consumer | Number of callback processing invocations |
| Processing duration | Consumer | Message processing time |
| Processing errors | Consumer | Exceptions or failed processing |
| Redelivery count | Consumer/broker | Messages redelivered |
| Queue depth | Broker | Number of messages currently waiting |
| Oldest message age | Broker | Age of the oldest waiting message if exposed by the broker |
| Consumer count | Broker | Number of active consumers |

Not all metrics are provided by the Micrometer JMS binder. Send/processing observations live in the application; queue depth, enqueue/dequeue, consumer count, and broker storage usually come from broker management/exporters.

Exact metric names depend on version and provider. Check the Actuator metrics endpoint, Prometheus exposition, and broker metrics before building dashboards.

## 8. Measuring processing duration and business outcomes

A consumer callback may finish quickly while the business workflow continues in another service. Clearly define what duration is being measured: listener callback duration; synchronous business service processing inside the callback; transaction/acknowledgement duration; or time from publish to consumer completion (end-to-end message age).

These intervals differ. A listener timer does not include the time a message spent in the queue before dispatch. Measuring queue delay requires enqueue timestamps or appropriate broker metrics and handling clock skew.

Example custom observation for business processing:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Component;

@Component
class InvoiceMessageProcessor {
    private final ObservationRegistry observationRegistry;

    InvoiceMessageProcessor(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    void process(InvoiceRequested message) {
        Observation.createNotStarted(
                    "invoice.message.process",
                    observationRegistry)
                .lowCardinalityKeyValue("message.type", "invoice-requested")
                .observe(() -> invoiceService.createInvoice(message));
    }
}
```

This example illustrates creating an observation around a business operation. Message type must be a bounded, managed set of values. Do not add invoice IDs to low-cardinality values. If built-in listener observation already measures the callback, a custom business observation should have a distinct name and purpose—for example, separating business processing time from listener/transaction overhead.

## 9. Retry, redelivery, and dead-letter queues

A JMS consumer may receive a message again if processing fails or acknowledgement/transaction does not complete. Therefore, a single message can produce multiple processing attempts:

```text
Message published
      |
      v
Attempt 1: processing exception
      |
      v
Broker redelivery
      |
      v
Attempt 2: timeout
      |
      v
Broker redelivery policy
      |
      +----> Attempt 3 succeeds
      |
      +----> or routed to DLQ
```

Track separately: the number of logical messages published, the number of consumer delivery/processing attempts, the number of redeliveries, the number of messages eventually processed successfully, and the number of messages moved to a dead-letter queue.

Do not sum processing attempts as the logical business message count. If one message is tried 5 times, the producer dashboard may record only 1 publish while the consumer shows 5 attempts.

DLQs require separate metrics and alerts. Rising queue depth, rising oldest message age, or rising DLQ rates can indicate the consumer is unable to process messages. Messages moving to a DLQ do not necessarily mean the broker is broken; it could be a poison message, schema incompatibility, or business validation failure.

## 10. Cardinality and data inside messages

Message payloads often contain order IDs, customer IDs, emails, account numbers, or business data. Do not put payloads or these IDs into metric tags.

| Value | Metric tag? | More appropriate place |
| --- | --- | --- |
| Fixed destination | Yes | Metrics and traces |
| Normalized message type | Yes | Metrics |
| Processing outcome | Yes | Metrics |
| Finite redelivery category | Yes | Metrics |
| JMS Message ID | No | Logs/traces per policy |
| Request-specific JMSCorrelationID | No | Logs/traces |
| Order/customer ID | No | Controlled business logs/traces |
| Raw payload | No | Do not log; or strict redaction/allowlist |
| Exception message | No | Standardized exception type |

Do not log entire JMS messages for debugging. Payloads may contain PII, secrets, or payment data. Prefer message type, schema version, destination, outcome, and approved identifiers.

## 11. Transaction and acknowledgement semantics

The JMS session/transaction determines when a message is acknowledged or rolled back. Observability must distinguish normal listener method return, successful transaction commit, message acknowledgement, and transaction rollback causing redelivery.

If instrumentation closes the span as soon as the listener method returns while the transaction commits afterward, the span duration might exclude part of the acknowledgement/commit path depending on the container. Check the transaction manager, listener container configuration, and observation boundary.

With transacted sessions, an exception can roll back the transaction and trigger redelivery. With other acknowledgement modes, semantics differ. Do not write listener-success alerts solely based on callbacks not throwing exceptions if commit/ack can still fail afterward.

## 12. Verifying instrumentation in Spring Boot

Verification process:

1. Confirm Spring Boot, Spring JMS, Micrometer Observation, and tracing bridge/exporter versions are compatible.
2. Confirm `JmsTemplate` and the listener container are Spring-managed and have received observation configuration.
3. Send a test message to a stable destination.
4. Check the producer observation/span and metric count/duration.
5. Let the consumer receive the message; check the consumer observation/span and outcome.
6. Verify trace context is injected into JMS message properties and extracted on the consumer per convention.
7. Trigger a message that throws a controlled exception; observe errors, rollback/redelivery, and DLQ policy.
8. Correlate application metrics with broker queue depth/consumer metrics.
9. Verify metric tags do not contain message IDs, business IDs, or raw payloads.
10. Verify logs contain the necessary destination, message type, and correlation/trace context without exposing sensitive payloads.

### Test matrix

| Test | Expected verification |
| --- | --- |
| Publish a valid message | Producer send observation is recorded |
| Consumer processes successfully | Processing observation finishes per configured semantics |
| Consumer throws exception | Error recorded; rollback/redelivery per policy |
| Message traverses multiple services | Trace context injected/extracted or linked per convention |
| Message is redelivered | Attempt/redelivery is distinguished |
| Message goes to DLQ | DLQ metrics/logging indicate destination and error type |
| Send many order IDs | Metric series stay grouped by destination/type, not order ID |
| Broker temporarily unavailable | Producer error/latency reflects connection failure |
| Consumer stopped | Broker queue depth/oldest age rises; app processing rate drops |
| Transaction commit fails | Callback return is not mistaken for acknowledged success |

## 13. Messaging dashboards and alerts

A dashboard should combine application and broker metrics:

| Panel | Source | Meaning |
| --- | --- | --- |
| Publish rate/error rate | Producer observations | Are producers able to send? |
| Send duration p95/p99 | Producer observations | Are broker/API calls slow? |
| Processing rate/duration | Consumer observations | How fast/slow are consumers processing? |
| Processing error rate | Consumer observations | How many consumer errors are occurring? |
| Queue depth | Broker metrics | Is the message backlog growing? |
| Oldest message age | Broker metrics | Are messages waiting too long? |
| Consumer count | Broker metrics | Are enough consumers active? |
| Redelivery/DLQ rate | Broker + application | Are there poison messages or recurring failures? |

Combined signals:

- Queue depth and oldest message age rising together: consumer throughput cannot keep up with producers.
- Queue depth rising while consumer count is 0: listener/container or broker connection may be down.
- Processing duration rising and queue depth rising: consumers are slow or a downstream dependency is congested.
- Redeliveries and DLQ rising: message processing is failing repeatedly.
- Producer send errors rising: check broker availability, credentials, network, and destination policies.

Do not alert solely on absolute queue depth if the queue carries high baseline traffic. Use baselines, growth rate, message age, and processing SLAs per destination.

## 14. Scenario exercise

`orders-service` publishes 1,000 messages per minute to the `orders.created` queue. `payment-service` can only process 700 messages per minute. After 20 minutes, queue depth increases continuously; the processing error rate rises and a subset of messages are redelivered multiple times before landing in the DLQ.

**Questions:**

1. Why is looking only at producer send success insufficient to evaluate the system?
2. Which metrics show that the consumer is falling behind the producer?
3. Why must redelivery attempts not be counted as new logical messages?
4. At which boundaries must trace/log context be inspected?
5. What causes can route messages to the DLQ?

**Analysis hints:**

- Producer send success only indicates the broker accepted the send operation; it does not prove the consumer processed it.
- Compare publish rate with processing rate, queue depth, oldest message age, consumer count, processing duration, and error rate.
- A single message can be delivered multiple times; track logical publish count separately from delivery/attempt counts.
- Check that the producer injects context into message properties, the broker preserves properties, and the consumer extracts context before processing; correlate Correlation ID/Message ID separately.
- Poison messages, schema incompatibility, validation errors, dependency timeouts, or redelivery limits can lead to the DLQ depending on broker policy.

### Completion checklist

| Topic | Able to explain/verify |
| --- | --- |
| JMS flow | Distinguish producer, broker, and consumer |
| JmsTemplate | Observe send/publish |
| @JmsListener | Observe consumer processing |
| Observation | Understand registry, conventions, and lifecycle |
| Trace propagation | Inject/extract context via JMS properties |
| Correlation IDs | Distinguish Message ID, JMSCorrelationID, Trace ID, and business ID |
| Metrics | Separate send, processing, retry, and broker queue metrics |
| Cardinality | Do not use message/business IDs or payloads as metric tags |
| Retry/redelivery | Distinguish logical messages from delivery attempts |
| DLQ | Monitor poison messages and failure routing |
| Transactions | Distinguish callback return, commit, and acknowledgement |
| End-to-end | Verify producer, broker, consumer, traces, logs, and metrics |

**Remember:** JMS instrumentation observes both producer publishing and consumer processing. A successful `JmsTemplate` send does not mean the consumer has processed the message; listener callback return must also be distinguished from transaction commit/acknowledgement. Use Micrometer Observation and appropriate tracing integration to record metrics/spans, inject/extract trace context via JMS properties, and keep Message ID, `JMSCorrelationID`, Trace ID, and Business ID true to their semantics. Monitor application send/process metrics alongside broker queue depth, oldest message age, redelivery, and DLQ; keep tags low-cardinality and never put raw payloads into logs or metrics.
