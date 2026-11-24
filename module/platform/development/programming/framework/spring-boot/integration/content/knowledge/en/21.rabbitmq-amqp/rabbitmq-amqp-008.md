# Retries, Requeueing, and Avoiding Poison-Message Loops in RabbitMQ/AMQP

An `order-service` consumer reads `OrderPaid` events from RabbitMQ to create shipments. If the shipping API temporarily returns HTTP 503, **retrying** can succeed. Yet if a message is missing an order ID, redelivering it 10,000 times will never fix the data. A third failure is even trickier: the service saved the shipment to the database, then lost its connection before acknowledging RabbitMQ. The message can arrive again and must be **deduplicated**.

In the **RabbitMQ and AMQP** chapter of **SPRING_BOOT_INTEGRATION**, the job goes far beyond adding `@RabbitListener`. You must align publishing/consuming mechanics, data contracts, retry caps, acknowledgments, requeueing, dead-letter exchanges, transactions, idempotency, and operational monitoring. Three easily confused terms must be kept strictly separate:

- **Retry**: re-executing a failed operation. This can happen within *the same RabbitMQ message delivery to the listener*, or by dispatching a subsequent delivery after a delay.
- **Requeue**: asking the broker to return an uncompleted delivery to the queue, usually for redelivery. `requeue=true` by itself **provides no backoff** or attempt cap.
- **Dead-letter**: removing a message from its source queue when a broker-supported trigger fires—such as reject/nack with `requeue=false`; with a configured DLX, the broker routes it to a dedicated destination (typically a DLQ).

A reliable system defines explicit paths for **success**, **transient failures**, **non-retryable errors**, and **exhausted retry budgets**.

> Example scope: Spring Boot 3.x, Spring AMQP/Spring Rabbit via `spring-boot-starter-amqp`, and RabbitMQ supporting AMQP 0-9-1. `listener.simple` properties apply to Simple containers; if using Direct containers, custom factories, or different versions, configure the matching policies. Quorum queue, DLX, and policy behavior vary across broker versions and configurations.

## 1. From Publish to Ack: Where Do Messages Go When Consumers Fail?

A typical layout:

~~~mermaid
flowchart LR
    P["order-service publisher"] --> E["Exchange: orders.events"]
    E --> Q[("Queue: shipping.jobs")]
    Q --> C["shipping-service @RabbitListener"]
    C -->|Success + ACK| OK["Delivery complete"]
    C -->|Reject/Nack requeue=false| DLX["Exchange: orders.dlx"]
    DLX --> DLQ[("Queue: shipping.dead")]
    C -->|Nack requeue=true| Q
~~~

The **producer** publishes to an *exchange* with a routing key; the exchange distributes messages to matching bound queues. The consumer receives deliveries from a queue and responds using the **channel's delivery tag**. The broker manages queue message state based on ack/nack/reject and queue policies.

Fundamental AMQP operations:

| Operation | Meaning for a Delivery | Key Note |
| --- | --- | --- |
| `basicAck(tag, false)` | Processing finished; broker may remove delivery from queue | Send only after protected side effects are durable |
| `basicReject(tag, true)` | Reject and request requeue | Can redeliver immediately, causing a tight loop |
| `basicReject(tag, false)` | Reject without requeue | Dead-letters if the queue has a DLX; otherwise may discard the message |
| `basicNack(tag, false, true)` | Negative acknowledgment, requeue one delivery | Does not add delay between deliveries |
| `basicNack(tag, false, false)` | Negative acknowledgment without requeue | Typically terminates in configured DLX/DLQ |
| `basicNack(tag, true, ...)` | Can affect **multiple** unacked deliveries up to tag on the same channel | Understand `multiple=true` before using so unrelated messages are not affected |
| Channel/connection drops while unacked | Broker may return messages to ready state for redelivery | Consumer may already have committed side effects prior to disconnect |

Distinguish **AMQP consumer ack** from **publisher confirm**: a producer receiving a broker confirm does not mean a consumer succeeded; a consumer sending ack does not confirm any subsequent publish made by the consumer was persisted by the broker. Each signal serves a different segment of the pipeline.

### Spring `AUTO` Acknowledgment Is Not RabbitMQ `autoAck`

With Spring AMQP's `acknowledge-mode: auto`, the **Spring container** sends the ack once the listener method returns normally; on exceptions, the container decides reject/nack based on error type and configuration. This is not RabbitMQ's `autoAck=true` mode, where deliveries are considered settled immediately upon dispatch without awaiting processing.

If choosing `acknowledge-mode: manual`, application code must explicitly ack the right delivery tag and handle errors, shutdowns, and double-ack prevention. Use manual only when fine-grained control is needed; most flows work well combining Spring `AUTO`, bounded retries, and dead-lettering.

## 2. Why `requeue=true` Is Dangerous

Suppose `shipping.jobs` holds an invalid message `{"orderId":null}`. The listener always throws an exception. If the container rejects/nacks with `requeue=true`:

1. The broker delivers the bad message to consumer A.
2. A throws and requeues.
3. The broker places the message back in the queue, potentially delivering it right away to A or consumer B.
4. The consumer fails again. The cycle spins rapidly, burning CPU, logs, network, connections, and starving healthy messages.

~~~mermaid
flowchart TD
    Q[("shipping.jobs")] --> C["Listener"]
    C --> V{"Valid data?"}
    V -->|No| N["NACK requeue=true"]
    N --> Q
    V -->|Yes| W["Business processing"]
    W --> A["ACK"]
~~~

No delay exists in that loop. Prefetch, queue ordering, and consumer counts alter redelivery placement; **requeue guarantees neither fair distribution nor moving the message to the back indefinitely**. Adding more workers often just accelerates the failure loop.

The `redelivered` flag in delivery metadata only says the broker previously attempted delivery—**it is not a reliable retry counter**. It ignores in-process Spring Retry attempts within *the same delivery* and cannot replace a bounded retry budget.

A safer approach: retry transiently within a finite budget, then **reject without requeue** to send the message to a DLQ alongside controlled remediation and replay procedures.

## 3. Classify Errors Before Choosing a Policy

Two Java exceptions can carry completely different business implications:

| Error Group | Examples | Recommended Policy |
| --- | --- | --- |
| **Transient, recoverable** | HTTP 503, network timeout, DB lock/deadlock, rate limit | Finite retry + backoff; optionally route to a delayed retry queue |
| **Invalid data** | Malformed JSON, missing required field, unsupported enum/schema | Reject without requeue; route to DLQ to fix producer/contract |
| **Permanent business violation** | Order already cancelled, permanently missing entity | Do not retry blindly; route to investigation queue or record rejection |
| **Dependency down long-term** | 30-minute partner outage, maintenance window, scheduled quota reset | Broker-level delay, circuit breaker, and alerting |
| **Unknown outcome** | DB committed then connection lost before ack; timeout after side effect completed | Redelivery may occur; enforce idempotency and status reconciliation |
| **Application bug** | Code `NullPointerException`, memory leak, broken mapping | Isolate, alert, fix, and replay; rapid retries do not help |

Never classify solely by HTTP status code. For instance, HTTP 409 could be a benign duplicate or a business conflict; HTTP 404 could be transient under eventual consistency or permanent. The domain layer must define retryability, terminal states, and compensation.

Practical rule: retry only when **the failure reason can clear**, the operation is **safe to re-execute**, and **total time/attempts stay bounded**. Otherwise, route the message to another controlled flow.

## 4. Retries Exist in Three Places with Three Different Semantics

| Mechanism | Where It Runs | Pros | Limitations |
| --- | --- | --- | --- |
| **Local/in-process retry** | Inside listener container via Spring Retry | Easy to configure; handles brief blips | Holds consumer/thread; long backoffs hurt throughput and do not survive restarts |
| **Broker requeue** | `BasicReject`/`Nack` with `requeue=true` or connection loss pre-ack | Simple; broker redelivers | Usually immediate with no attempt cap; risks infinite loops |
| **Delayed redelivery** | TTL/DLX retry queues, delayed exchange plugin, or scheduler | Enables long backoffs and protects downstream load | Requires managing topology, attempt counts, routing, publisher confirms, and idempotency |

**Local retry** may invoke a handler three times while RabbitMQ sees **one unacked delivery**; broker-level redelivery occurs only on nack/requeue or lost channels. Hence, RabbitMQ headers alone cannot count all application attempts.

**Broker requeue** is not **delayed retry**. Putting `Thread.sleep(5_000)` inside a listener before requeueing blocks consumer threads and cripples throughput as errors climb.

**Delayed redelivery** typically routes failing messages to a holding queue and later back to the main queue. Return them only while retry budget remains; otherwise route to the DLQ. A TTL → DLX → main queue cycle without an attempt counter or stop condition still loops indefinitely or triggers broker cycle detection. Never treat broker cycle detection as a business retry policy.

## 5. Spring Boot Configuration: Bounded Retry, Then DLQ

Baseline dependency using `spring-boot-starter-amqp` with Spring Boot 3.x:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

An `application.yml` config for Boot's default **SimpleRabbitListenerContainerFactory**:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: ${RABBITMQ_USER}
    password: ${RABBITMQ_PASSWORD}
    listener:
      simple:
        acknowledge-mode: auto
        default-requeue-rejected: false
        prefetch: 20
        retry:
          enabled: true
          max-attempts: 3
          initial-interval: 300ms
          multiplier: 2.0
          max-interval: 2s
~~~

Meaning:

- `acknowledge-mode: auto`: Spring acks after the listener finishes; exceptions pass through container error handling.
- `retry.enabled: true`: enables retry advice on auto-configured listener containers.
- `max-attempts: 3`: includes **the initial invocation** plus up to two retries within the same delivery—not three broker redeliveries.
- `initial-interval`, `multiplier`, `max-interval`: bound local retry backoff. Blocking the listener during retries can reduce throughput.
- `default-requeue-rejected: false`: on final failure, rejects/nacks **without requeue**; with a matching DLX, the message enters the dead-letter flow.
- `prefetch: 20`: one consumer can pre-buffer up to 20 unacked messages; when downstream slows or retries, large prefetch holds messages too long. Measure before tuning concurrency/prefetch.

**Configuration pitfall:** `spring.rabbitmq.listener.simple.*` affects only Boot's Simple container. If using `listener.direct.*` or defining a custom `SimpleRabbitListenerContainerFactory` without Boot's configurer, behavior may differ from this example.

An explicit Java customization approach when managing retry policy directly:

~~~java
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ShippingListenerConfig {

    @Bean
    SimpleRabbitListenerContainerFactory boundedRetryFactory(
            ConnectionFactory connectionFactory,
            SimpleRabbitListenerContainerFactoryConfigurer configurer) {

        var factory = new SimpleRabbitListenerContainerFactory();
        configurer.configure(factory, connectionFactory);

        factory.setDefaultRequeueRejected(false);
        factory.setAdviceChain(
            RetryInterceptorBuilder.stateless()
                .maxAttempts(3)
                .backOffOptions(300L, 2.0, 2_000L)
                .recoverer(new RejectAndDontRequeueRecoverer())
                .build()
        );
        return factory;
    }
}
~~~

Then reference it on the listener: `@RabbitListener(queues = "shipping.jobs", containerFactory = "boundedRetryFactory")`. This is an **alternative** to YAML auto-configured retries: if Boot's configurer already attached retry advice from properties, do not attach a second advice and accidentally multiply invocations. Disable `spring.rabbitmq.listener.simple.retry.enabled` when providing explicit custom advice.

`RejectAndDontRequeueRecoverer` ends retries by throwing `AmqpRejectAndDontRequeueException`, instructing the container to reject without requeue. It **does not create a DLQ by itself**; declare the DLX/queue/binding on RabbitMQ or rejected messages will not land where expected.

### When to Use Stateless vs. Stateful Retry?

- **Stateless retry**: attempts execute inside one listener invocation/delivery via the interceptor. Simple for brief errors like few-hundred-millisecond HTTP timeouts.
- **Stateful retry**: retains retry state keyed by message identity across multiple deliveries/invocations, carrying specific transaction and requeue semantics. Requires stable message IDs/keys, explicit recoverers, and testing of actual delivery counts.

Do not enable `stateful` expecting "retries survive process restarts." In-memory retry state on a consumer is not durable storage across restarts. For long-running durable retries, use broker queues/headers or a persistent business state table.

## 6. Declaring Primary and Dead-Letter Queue Topology

A useful DLQ requires a **real route**, not merely a queue named `*.dead`. Example declaring exchanges/queues/bindings with Spring AMQP:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ShippingRabbitTopology {
    public static final String MAIN_EXCHANGE = "orders.events";
    public static final String MAIN_ROUTING_KEY = "order.paid";
    public static final String MAIN_QUEUE = "shipping.jobs";
    public static final String DEAD_EXCHANGE = "orders.dlx";
    public static final String DEAD_ROUTING_KEY = "shipping.dead";
    public static final String DEAD_QUEUE = "shipping.dead";

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(MAIN_EXCHANGE, true, false);
    }

    @Bean
    Queue shippingQueue() {
        return QueueBuilder.durable(MAIN_QUEUE)
                .deadLetterExchange(DEAD_EXCHANGE)
                .deadLetterRoutingKey(DEAD_ROUTING_KEY)
                .build();
    }

    @Bean
    Binding shippingBinding(@Qualifier("shippingQueue") Queue shippingQueue,
                            @Qualifier("ordersExchange") DirectExchange ordersExchange) {
        return BindingBuilder.bind(shippingQueue)
                .to(ordersExchange)
                .with(MAIN_ROUTING_KEY);
    }

    @Bean
    DirectExchange ordersDeadExchange() {
        return new DirectExchange(DEAD_EXCHANGE, true, false);
    }

    @Bean
    Queue shippingDeadQueue() {
        return QueueBuilder.durable(DEAD_QUEUE).build();
    }

    @Bean
    Binding deadBinding(@Qualifier("shippingDeadQueue") Queue shippingDeadQueue,
                        @Qualifier("ordersDeadExchange") DirectExchange ordersDeadExchange) {
        return BindingBuilder.bind(shippingDeadQueue)
                .to(ordersDeadExchange)
                .with(DEAD_ROUTING_KEY);
    }
}
~~~

When consumers reject from `shipping.jobs` with `requeue=false`, the broker dead-letters the message to `orders.dlx` with routing key `shipping.dead`, and the binding delivers it to `shipping.dead`.

Operational details:

1. **The DLX must exist** with a matching binding. Misconfigured dead-letter routing, deleted exchanges, altered policies, or full/unavailable target queues can break error routing.
2. A `durable` queue alone does not make every publish durable; producers must use persistent delivery mode and the broker must operate persistent storage properly. DLXs carry their own durability and safety conditions.
3. For quorum queues, RabbitMQ provides version-dependent dead-lettering and delivery-limit policies; test the chosen dead-letter mode if SLAs require zero loss during handoff.
4. Modifying `x-dead-letter-exchange` or `x-dead-letter-routing-key` by redeclaring an existing queue with different arguments triggers `PRECONDITION_FAILED`. In production, prefer RabbitMQ policies and planned topology migrations per broker capabilities.
5. DLQs also need capacity/retention limits, access controls, alerts, and a replay runbook. An unmonitored DLQ just hides failures.

### Why Spring's Error Handler Also Matters

Not every bad message even reaches the `@RabbitListener` method. Wrong content type, conversion failures, unmatched handler methods, or incompatible payloads fail **before the listener executes**. Spring AMQP uses container error handlers (such as `ConditionalRejectingErrorHandler`) to classify fatal errors so broken conversions do not requeue infinitely.

When customizing error handlers or listener containers, verify pre-listener error policies, exception wrapping, and handling of previously dead-lettered messages. Never assume a `try/catch` inside a listener method catches serialization failures.

## 7. Writing the Listener: Permanent Errors Go to DLQ, Transient Errors Retry

Scenario: handling `OrderPaid` in `shipping-service`. We read the raw Spring AMQP `Message` JSON body and map it explicitly to avoid relying on implicit conversion while illustrating error classification.

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class ShippingConsumer {

    private final ObjectMapper objectMapper;
    private final ShipmentService shipmentService;

    public ShippingConsumer(ObjectMapper objectMapper,
                            ShipmentService shipmentService) {
        this.objectMapper = objectMapper;
        this.shipmentService = shipmentService;
    }

    @RabbitListener(
        queues = ShippingRabbitTopology.MAIN_QUEUE,
        containerFactory = "boundedRetryFactory"
    )
    public void onOrderPaid(Message message) {
        OrderPaid event;

        try {
            event = objectMapper.readValue(
                    message.getBody(), OrderPaid.class);
        } catch (JsonProcessingException ex) {
            throw new AmqpRejectAndDontRequeueException(
                    "Unable to parse OrderPaid JSON", ex);
        }

        if (event.eventId() == null
                || event.eventId().isBlank()
                || event.orderId() == null
                || event.orderId().isBlank()) {
            throw new AmqpRejectAndDontRequeueException(
                    "Missing eventId or orderId");
        }

        // Use @Transactional on ShipmentService with inbox idempotency.
        // On transient failure, throw an exception so the retry interceptor handles it.
        shipmentService.createShipmentOnce(event);
    }
}

record OrderPaid(String eventId, String orderId) {}
~~~

`ShipmentService` is a project-defined business service. In production, `createShipmentOnce` must coordinate SQL transactions, unique constraints, and external side effects.

**Interceptor ordering note:** `AmqpRejectAndDontRequeueException` tells the container not to requeue once the final exception surfaces. It does **not mean every retry advice skips local retries** for that exception. With the basic `RetryInterceptorBuilder.stateless()` in Section 5, if you want malformed-payload errors to **terminate immediately** without three local attempts, configure an exception classifier on the retry policy or separate validation/consumers so permanent errors bypass generic retry advice.

### How Should Retryable Exceptions Be Handled?

The service layer can throw `TransientPartnerException` when the shipping API returns 503 or times out. The listener lets the exception propagate, Spring Retry retries within budget, and once attempts are exhausted, the recoverer rejects without requeue so the broker dead-letters it.

Conversely, if code writes:

~~~java
try {
    shipmentService.createShipmentOnce(event);
} catch (Exception ex) {
    log.error("Shipment creation failed", ex);
    // Returns normally.
}
~~~

Spring `AUTO` ack treats the delivery as successful. The message vanishes from the queue even though business processing failed. Always **rethrow, persist failure state intentionally, or hand off safely to another durable flow**—never just log and swallow.

### Use `ImmediateRequeueAmqpException` Very Sparingly

Spring AMQP offers `ImmediateRequeueAmqpException` to force an immediate requeue even when the default reject policy is false. It is a specialized control tool, not a general "retry whenever" mechanism—it can easily recreate infinite loops. Every explicit requeue path needs throttling or a state guard ensuring the message cannot loop identically forever.

## 8. Manual Ack: Who Precisely Owns Settling the Delivery?

Some systems require manual acknowledgment to align tightly with database writes or forwarding workflows. Configure `ackMode = "MANUAL"` on the listener:

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class ManualShippingConsumer {

    private final ShipmentService shipmentService;

    public ManualShippingConsumer(ShipmentService shipmentService) {
        this.shipmentService = shipmentService;
    }

    @RabbitListener(
        queues = "shipping.manual.jobs",
        ackMode = "MANUAL"
    )
    public void handle(Message message, Channel channel) throws IOException {
        long tag = message.getMessageProperties().getDeliveryTag();

        try {
            shipmentService.processRawOnce(message.getBody());
            channel.basicAck(tag, false);
        } catch (PermanentMessageException ex) {
            channel.basicReject(tag, false);  // DLX if declared.
        } catch (TransientProcessingException ex) {
            channel.basicNack(tag, false, false); // Route to DLQ for later handling.
        }
    }
}
~~~

This deliberately uses a separate queue `shipping.manual.jobs` so two listeners do not compete on the main queue. `PermanentMessageException`, `TransientProcessingException`, and `ShipmentService.processRawOnce` are application-defined. The manual queue also needs its own DLX topology so `requeue=false` does not lose messages.

Key points:

- Ack only after the business transaction commits. ACKing beforehand risks losing the message if DB commit fails.
- If DB commits yet the connection drops before ack, the broker may redeliver; inbox idempotency is mandatory.
- `basicReject` and `basicNack` use the delivery tag from **the exact channel** delivering the message. Never reuse tags across channels or ack twice.
- When catching specific exceptions, ensure unexpected errors have an explicit policy (e.g., container closes channel and unacked deliveries are redelivered) rather than silently hiding bugs.
- Manual ack helps when forwarding publishes, yet **source ack + target publish do not form an atomic transaction** merely by sharing one Java method.

For typical workloads, `AUTO` ack combined with bounded retries and DLQ is simpler to operate; pick manual ack only when exact settlement control is required.

## 9. Delayed Retry via Broker: Avoid Holding Consumers in Long Backoffs

If a partner can be offline for 15 minutes, three local retries 300 ms apart are insufficient. Sleeping a listener for 15 minutes ties up consumers/prefetch and blocks scaling. Instead, route to waiting queues with TTL that dead-letter back to the main exchange.

A conceptual topology:

~~~mermaid
flowchart LR
    EX["orders.events<br/>routing: order.paid"] --> MAIN[("shipping.jobs")]
    MAIN --> WORKER["shipping-service"]
    WORKER -->|Transient failure, budget left| RETRYEX["orders.retry"]
    RETRYEX --> R5[("shipping.retry.5s<br/>TTL 5s")]
    RETRYEX --> R30[("shipping.retry.30s<br/>TTL 30s")]
    R5 -->|TTL expired, DLX| EX
    R30 -->|TTL expired, DLX| EX
    WORKER -->|Permanent error / budget exhausted| DLX["orders.dlx"]
    DLX --> DLQ[("shipping.dead")]
~~~

**Unlike auto-requeue:** the listener must check the **attempt budget** and route transient failures to the chosen retry queue; once attempts are exhausted, reject/nack without requeue to land in the DLQ. Wiring main queue dead-letter to retry and retry dead-letter back to main **without a stop condition** still creates an infinite loop.

### Declaring Two TTL Holding Queues

Topology additions using queue-level TTL:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ShippingRetryTopology {

    @Bean
    DirectExchange retryExchange() {
        return new DirectExchange("orders.retry", true, false);
    }

    @Bean
    Queue retryFiveSecondsQueue() {
        return QueueBuilder.durable("shipping.retry.5s")
                .ttl(5_000)
                .deadLetterExchange("orders.events")
                .deadLetterRoutingKey("order.paid")
                .build();
    }

    @Bean
    Queue retryThirtySecondsQueue() {
        return QueueBuilder.durable("shipping.retry.30s")
                .ttl(30_000)
                .deadLetterExchange("orders.events")
                .deadLetterRoutingKey("order.paid")
                .build();
    }

    @Bean
    Binding bindRetryFiveSeconds(
            @Qualifier("retryFiveSecondsQueue") Queue retryFiveSecondsQueue,
            @Qualifier("retryExchange") DirectExchange retryExchange) {
        return BindingBuilder.bind(retryFiveSecondsQueue)
                .to(retryExchange)
                .with("delay.5s");
    }

    @Bean
    Binding bindRetryThirtySeconds(
            @Qualifier("retryThirtySecondsQueue") Queue retryThirtySecondsQueue,
            @Qualifier("retryExchange") DirectExchange retryExchange) {
        return BindingBuilder.bind(retryThirtySecondsQueue)
                .to(retryExchange)
                .with("delay.30s");
    }
}
~~~

Retry queues must have no direct consumers in this model: they hold messages until TTL expires and dead-letter back to `orders.events`. The main queue and DLQ were declared in Section 6. Once TTL expires, the broker creates a fresh delivery to the main queue; the original producer does not resend.

To trigger it, the application must **republish** the message to `orders.retry` with routing key `delay.5s` or `delay.30s` when an error is retryable. Conceptual design:

~~~text
on transient error:
    nextAttempt = readValidatedAttempt(message) + 1

    if nextAttempt <= MAX_RETRIES:
        publish original business event with nextAttempt to retry.exchange
        wait for broker publish confirm and handle unroutable return
        acknowledge original delivery
    else:
        reject original delivery with requeue=false   # final DLQ

on permanent error:
    reject original delivery with requeue=false       # final DLQ
~~~

This is **flow pseudo-code**, not an atomic transaction. Publishing the retry and ACKing the original message has a failure window: if the publish succeeds yet the ACK fails, **two copies** exist; if the original is ACKed before broker confirmation, **work can be lost**. Use publisher confirms, mandatory returns/routing checks, and durable state/outbox or idempotency where strong guarantees are needed. Publisher confirm only tells whether the broker accepted the publish under its config—it does not prove the target queue received and processed it.

A simpler strategy is **short local retry + final DLQ**, paired with operations/workers that triage DLQs and schedule controlled replays. Only build delayed retry topologies when SLAs truly demand automated multi-minute or multi-hour retries.

### Why Use Multiple Fixed-TTL Queues?

Queue-level TTL (e.g., every message in `shipping.retry.5s` waits 5 seconds) is far more predictable than mixing varying per-message TTLs inside one queue, where expiration/dead-lettering can stall behind earlier messages (*head-of-line blocking*). If dynamic per-message delays are needed, evaluate delayed-message exchange plugins, persistent schedulers, or platforms supporting scheduled delivery; plugin availability depends on RabbitMQ version and deployment policies.

**Important:** TTL queues still consume memory and disk. During an extended partner outage, retry backlogs can swell to millions of messages; enforce quotas, retention, disk alarms, and circuit-breaker / stop-the-world policies.

## 10. Counting Attempts Without Creating Loops

A retry system must track two distinct numbers:

- **Local attempts**: how many times the interceptor invoked the handler within one delivery (e.g., `max-attempts=3`).
- **Broker redeliveries/round trips**: how many times the message was redelivered via nack/requeue/TTL DLX or republished by the app as a new message.

Never collapse both into `redelivered=true`. RabbitMQ may attach death/trace headers to dead-lettered messages, yet those do not track total handler executions.

### RabbitMQ's `x-death` Header

When broker dead-lettering occurs, RabbitMQ typically records information such as the source queue, reason, and dead-letter count in `x-death` (aggregated by properties of each death cycle). Reasons such as `rejected` and `expired` can be distinguished.

However:

- `x-death` reflects **broker dead-lettering events**, not individual local Spring retry invocations.
- A message republished as a **new message** may lose previous `x-death` history unless the application intentionally preserves or maps metadata.
- RabbitMQ manages `x-death` internally per broker policy; never let clients dictate retry budgets simply by submitting a header named like the broker's.
- In pipelines spanning multiple queues and reasons, summing all `count` entries does not necessarily equal "business executions."

If a stable retry budget across multiple delay tiers is required, the application can define its own `retryAttempt` field in the envelope or an internally controlled header, incrementing it **whenever deciding to reschedule**. Enforce a finite `MAX_RETRIES`, validate the incoming value, keep `eventId` unchanged, and restrict publish permissions. You can also persist retry state in the database to prevent header spoofing/copying or state loss across republishes.

Quorum queues also offer a poison-message delivery count/limit (exact features, defaults, and semantics depend on RabbitMQ version). When using it, verify behavior alongside `nack`, `reject`, DLX, quorum policies, and actual consumer handling; it **does not replace** business-error retry strategies and does not count in-process Spring Retry executions within the same delivery.

### Illustrative Budget Table

| Business Invocation | Where It Runs | Expected Retry Counter | Action on Continued Failure |
| --- | --- | --- | --- |
| First delivery, local call #1 | Main listener | attempt=0 (broker cycle) | Local retry #2 |
| Local call #2 | Same delivery | attempt=0 | Local retry #3 |
| Local call #3 | Same delivery | attempt=0 | Republish to 5s delay if transient |
| Redelivered after 5s delay | Main listener | attempt=1 | Up to 3 local retries |
| Redelivered after 30s delay | Main listener | attempt=2 | If still failing, final DLQ |

This table illustrates a **hypothetical application-defined policy**. With the default `RejectAndDontRequeueRecoverer` in Section 5, messages go to the DLQ after local retries finish; to schedule delayed retries, replace that recoverer/handler with an explicit **publish + confirm + ack** strategy. Do not enable both expecting them to coordinate automatically per the table.

## 11. Idempotency: Surviving Duplicates After Retries, Requeues, or Disconnects

Even when normal deliveries run once, standard AMQP consumers must be built for **at-least-once delivery**: the same event can arrive multiple times.

Scenario:

1. Consumer receives `eventId=EVT-1042`.
2. `shipmentService` saves the shipment in SQL and commits.
3. Before Spring container sends ACK, the channel disconnects.
4. The broker redelivers the event once connectivity/consumers recover.
5. If the service inserts a new shipment without checking `eventId`, one order gets two shipments.

Use an **inbox/idempotency table** with a unique constraint:

~~~sql
CREATE TABLE processed_shipping_events (
    subscriber_id VARCHAR(100) NOT NULL,
    event_id      VARCHAR(120) NOT NULL,
    processed_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (subscriber_id, event_id)
);
~~~

Inside **one SQL transaction**, the consumer:

1. Validates schema, signature/trusted origin if required, and `eventId`.
2. Attempts to insert `(shipping-service, eventId)` into the inbox (backed by unique constraint).
3. If the key already exists, returns normally without reapplying side effects.
4. If new, creates/updates the shipment in the same transaction and commits.
5. Lets the listener return cleanly so Spring ACKs.

If SQL commits yet ACK fails, redelivery hits the existing inbox row. Handle concurrent consumers reading the same `eventId` via a real database unique constraint rather than an unprotected "check-then-insert" query.

### Side Effects Outside SQL

If business logic calls a partner HTTP shipping API, a SQL inbox alone **does not guarantee** preventing duplicate external calls in all cases—for instance, HTTP succeeds then the consumer crashes before SQL commits. Pass a partner-supported **idempotency key** (such as `orderId` or an event-derived key), persist transaction state, and reconcile/query status before retrying. When committing SQL and then emitting another event, consider a **transactional outbox** to bridge the DB–RabbitMQ gap.

**Rabbit transactions, publisher confirms, consumer acks, and database transactions have separate scopes.** Never infer exactly-once business effects solely from `deliveryMode=PERSISTENT` or `acknowledge-mode=auto`.

## 12. Dead-Lettering on Time and Operating the DLQ

A useful DLQ carries metadata enabling investigation and replay:

| Field to Store/Observe | Purpose |
| --- | --- |
| `eventId`, `orderId`, `schemaVersion`, event type | Identify and deduplicate; trace source data |
| Original timestamp, reject timestamp, message age | Measure delay and SLA impact |
| Original exchange/routing key/queue | Route back accurately after remediation |
| `x-death` reason, queue, count | Distinguish rejections, TTL expirations, and death cycles |
| Exception name, sanitized error classification | Separate data errors, code bugs, and downstream outages |
| Service version, trace/correlation ID | Correlate logs/traces and pinpoint deployed version |
| App-managed retry budget and retry history | Decide whether replay is still permitted |

**The broker does not attach full consumer Java stack traces to DLQ messages automatically.** To capture error details, use an appropriate message recoverer/republisher or a dedicated error log/store, keeping sensitive data out of uncontrolled headers. Spring AMQP's `RepublishMessageRecoverer` can attach exception info on republish, provided you manage header sizes, security, dedicated exchange/routing, publisher confirms, and internal detail exposure.

Safe replay workflow:

1. Assess root cause: bad payload, fixed bug, dependency outage, or schema drift.
2. Quantify blast radius, affected event IDs, sensitive fields, and replay safety.
3. Select individual messages or bounded batches, preserving business IDs, recording audit logs and responsible owners.
4. Verify broker exchange/routing keys, DB state, and idempotency before republishing.
5. Throttle replay speed using small batches first while monitoring partner/DB health.
6. ACK/delete messages from the DLQ only after forwarding is confirmed reliable—never bulk-delete just to "make the dashboard green."

Never configure a DLQ to automatically loop back to the main queue indefinitely without caps and terminal persistence. After bug fixes, DLQ replays must also respect schema versions and causal ordering between events.

## 13. Metrics and Alerts to Catch Retry Storms

A RabbitMQ system can show "connected with active consumers" while making zero business progress because messages spin in requeue loops.

| Metric | How to Read It |
| --- | --- |
| `messages_ready` on main queue | Messages waiting to be delivered |
| `messages_unacknowledged` | Dispatched yet unacked deliveries; persistently high implies slow handlers, oversized prefetch, or local retries |
| Publish/deliver/ack/requeue/redelivery rates | High redelivery paired with low ACK/throughput signals a retry loop |
| DLQ depth, ingress rate, oldest message age | Whether errors are piling up and breaching SLAs |
| Retry queue ready/oldest age | Whether retries are backing up due to partner outages or broken TTL/routing |
| Consumer count, connection/channel errors | Missing consumers or connection churn |
| Local retry attempts by exception/route | Whether real transient errors or bad payloads/bugs are being retried |
| Idempotency duplicate hits | Shows how often redeliveries/republishes hit deduplication |
| Publisher confirm failures, returns | Catches retry/replay publishes failing to reach the broker or route |
| RabbitMQ memory/disk alarms, queue policy breaches | Whether backlogs exceed capacity and threaten the whole broker |

When messages fail and requeue rapidly, tweaking concurrency only treats symptoms. Inspect error types, add retry stop conditions, and establish a DLQ path. If the DLQ climbs, find whether producer schemas or consumer code broke; **purging a DLQ does not fix the system**.

### Impact of Concurrency and Prefetch

- With multiple consumers, consecutive failures can bounce across different pods; single-pod logs may hide the loop.
- High prefetch lets slow consumers hoard unacked messages, hurting fairness and crash recovery times.
- Long local retries tie up handler threads, potentially collapsing overall consumer throughput.
- Simultaneous retries when a downstream recovers can trigger a *thundering herd*. Apply jittered backoff, quotas, and circuit breakers where appropriate.

## 14. Recommended Integration Test Matrix

Critical tests require a real broker or RabbitMQ inside an integration test environment. Listener mocks cannot test ACK/NACK/DLX semantics or RabbitMQ headers.

| Test Case | How to Execute | What to Observe |
| --- | --- | --- |
| Valid message | Publish event with fresh `eventId` | Processed once; queue empties and ACK increments |
| HTTP 503 twice then succeeds | Stub partner to fail twice, succeed on third | Listener runs up to 3 local attempts, ACKs; does not enter DLQ |
| Persistent HTTP 503 | Stub always fails; bounded local retries | Final reject without requeue; DLQ receives the message |
| Unparseable JSON | Publish schema-invalid payload | Does not spin on main queue; lands in error inspection path |
| Missing DLX/binding | Deliberately misconfigure in test env | Observe message failing to reach DLQ and verify topology fix |
| Continuous `requeue=true` | Controlled test consumer | Observe rapid redelivery, then immediately disable/reconfigure |
| DB commit then lost ACK | Simulate channel close pre-ACK | Redelivery blocked by idempotency; no second shipment created |
| 15-minute partner downtime | Route to delay queues (if implemented) | Main consumer stays unblocked; retries follow schedule and budget |
| Delay queue TTL expires | Publish to `shipping.retry.5s` | Message returns to main exchange/queue on TTL expiry |
| Exceeds `MAX_RETRIES` | Publish event near retry limit | Terminates in final DLQ rather than returning to main |
| Confirm fails during republish | Drop connection at publish moment | Source message is not lost via premature ACK; duplicates blocked |
| Quorum delivery limit (if used) | Nack/requeue up to policy limit | Message handled per configured delivery-limit/DLX |
| DLQ replay | Fix root cause, republish same `eventId` | Zero duplicate side effects; audit record captures replay |

Because certain publisher confirm/ack failure windows cannot be triggered deterministically in unit tests, fault injection, disconnect tests, and idempotency checks are far more reliable than happy-path-only tests.

## 15. Common Misconceptions

**"Throwing an exception from `@RabbitListener` makes RabbitMQ automatically retry after 5 seconds?"**

No. Behavior depends on container configuration, retry interceptors, and broker policies. `requeue=true` has no 5-second delay; Spring Retry offers local backoff yet occupies consumer resources while waiting.

**"`max-attempts: 3` means the broker redelivers the message three times?"**

Not in standard stateless Spring Retry configurations. It means up to three interceptor invocations of the handler within *a single delivery*. Broker redelivery counts are separate from local retries.

**"`default-requeue-rejected=false` loses failed messages?"**

It only disables requeueing. With a properly configured DLX and binding, messages are dead-lettered; without them, the broker can discard them. Always pair changing this property with topology checks.

**"Enabling DLX on the main queue and wiring a TTL retry queue back to the main queue is enough?"**

Not yet. You must stop loops with a retry budget and a clear terminal path. If every error cycles through the same loop, poison messages still spin endlessly.

**"If a message has `redelivered=true`, how many times has it been retried?"**

You cannot tell from that boolean. Local retries, `basicNack`, dead-letter cycles, and app-level republishes are distinct mechanisms that must be tracked at their respective levels.

**"Adding idempotency turns ACK and SQL into one atomic transaction?"**

No. It makes processing safe when messages redeliver across the DB-commit–ACK gap. External side effects or chained publishes still require dedicated idempotency/outbox designs.

**"You just create a DLQ and leave it alone?"**

A DLQ needs alerting, retention policies, diagnostic metadata, and a replay workflow. Without monitoring, failures simply move from consumers into an invisible backlog.

### Implementation Checklist

1. Classify transient, permanent, and unknown-outcome failures at the business layer.
2. Define a finite retry budget, backoff, and terminal destination when errors persist.
3. With Spring `AUTO` listeners, understand `default-requeue-rejected`, `retry.max-attempts`, and Simple vs. Direct container differences.
4. Ensure the main queue has a tested DLX/route/DLQ; never leave `requeue=true` as the default for poison messages.
5. If using delayed retries, design TTL queues, attempt counters, and safe confirm–ack handling; break infinite main–retry loops.
6. Use immutable `eventId`, a unique inbox, and business transactions to prevent double side effects.
7. Monitor ready/unacked/redelivery counts, local retries, DLQ depth, message age, publisher confirms, and business duplicates.
8. Test malformed schemas, downstream outages, broker reconnects, DB-commit-before-ACK crashes, and DLQ replays.
9. Document remediation/replay procedures in runbooks, enforce least privilege, and strip sensitive data from logs/headers.

### Version References

- [RabbitMQ – Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): semantics of `basicAck`, `basicReject`, `basicNack`, requeue, and publisher confirms.
- [RabbitMQ – Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): dead-letter triggers, routing, configuration, and dead-lettering risks.
- [RabbitMQ – Time-To-Live and Expiration](https://www.rabbitmq.com/docs/ttl): message TTL and expiration behavior.
- [Spring AMQP Reference – Exception Handling / Listener Retry](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html): exception classification, rejection, and error handlers.
- [Spring AMQP Reference – Resilience and Recovering from Errors](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html): retry/recoverer configuration and limitations.

**Key takeaway:** **Retry** is the decision to re-attempt an operation, **requeue** simply returns a delivery to the queue, and **dead-lettering** moves messages out of the primary flow. To make RabbitMQ integration in Spring Boot reliable, every retry needs sensible bounds and backoff, every error path needs an observable terminal state, and every critical side effect must tolerate redeliveries and duplicates.
