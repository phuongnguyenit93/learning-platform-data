# Customizing Pollable Sources with MessageSourceCustomizer

In Spring Cloud Stream, most consumers receive messages in a **message-driven** style: the binder registers a listener, the broker pushes messages, and the framework invokes the corresponding function or consumer. A **pollable consumer** works differently: the application actively requests one message using `PollableMessageSource.poll(...)`. This is useful when work must run on a schedule, when the application needs to cap message-fetch rates, or when pulling data must align with downstream system capacity.

When connecting a pollable source to Kafka, RabbitMQ, or another binder, standard configuration still lives in YAML. Occasionally, however, you need to adjust an advanced attribute on the **concrete `MessageSource` object** created by the binder. Spring Cloud Stream provides `MessageSourceCustomizer<T>` for that purpose.

This lesson focuses on the source customization mechanism for pollable bindings, when the customizer is invoked, an `AmqpMessageSource` example with RabbitMQ, the relationship between source customization and scaling pollers, and how to avoid acknowledgment bugs or duplicate processing. Examples use Spring Cloud Stream's Supplier/Function/Consumer model and bindings, while **active polling is driven by the application**.

## 1. Distinguishing Source, Binding, Binder, and Poller

| Concept | Responsibility | Does it decide the poll schedule? |
|---|---|---|
| **Binder** | Connects bindings to middleware such as Kafka or RabbitMQ | Does not decide when the application calls `poll()` |
| **Binding** | Maps logical input/output names to a destination and consumer group | No |
| **`PollableMessageSource`** | Spring Cloud Stream API the application calls to fetch a message | No; only executes when invoked |
| **`MessageSource`** | Concrete source adapter created by the binder, e.g., `AmqpMessageSource` | Usually only provides how to receive from the broker |
| **`MessageSourceCustomizer<T>`** | Customizes the source adapter after the binder sets initial properties | No |
| **Application scheduler / poller** | Decides when and how often to invoke `poll()` | Yes |

A common design mistake is declaring a customizer and expecting the system to poll faster automatically. The customizer is called when configuring the source; it is neither a scheduler nor a per-message processor. If you need to change polling intervals or thread counts, adjust the scheduler, instance count, and broker/consumer capacity.

## 2. When Is MessageSourceCustomizer Needed?

Prefer Spring Cloud Stream and binder properties in YAML whenever they meet your requirements. Use a customizer when you need advanced source-adapter APIs not covered by standard configuration, for example:

- Replacing `MessagePropertiesConverter` for a pollable RabbitMQ source to control how AMQP message properties and headers are converted.
- Replacing `AmqpHeaderMapper` when custom header mapping rules differ from defaults.
- Supplying a `MessageConverter` tailored to the protocol/format expected at the adapter.
- Enabling capturing the raw AMQP message in a header for error investigation, when genuinely needed and memory cost has been weighed.
- Applying customizations to a specific destination and group without affecting other pollable sources.

A customizer does **not** replace connection, destination, group, retry, DLQ, or binder selection configuration. Built-in properties should remain in standard configuration where they are easier to inspect and deploy.

## 3. The MessageSourceCustomizer Contract

In Spring Cloud Stream, the interface is located at:

~~~java
org.springframework.cloud.stream.config.MessageSourceCustomizer<T>
~~~

Core signature:

~~~java
@FunctionalInterface
public interface MessageSourceCustomizer<T> {
    void configure(
        T source,
        String destinationName,
        String group
    );
}
~~~

Meaning of the three parameters:

| Parameter | Meaning | What does the application typically do? |
|---|---|---|
| `source` | The `MessageSource` object created by the binder | Call advanced setters supported by the source |
| `destinationName` | The destination name associated with the source | Select configuration by logical topic/exchange/queue |
| `group` | The consumer group used by the binding | Scope customization to the desired processing group |

According to the JavaDoc, if a matching `MessageSourceCustomizer` **bean** exists in the application context, the binder can invoke it after configuring standard properties on the pollable source. The callback is a **configuration** step, not a per-message callback. If the new configuration overrides a setter the binder just applied, the customizer's value may become the effective value: verify to avoid conflicts.

In applications with multiple binders/source types, do not assume every binder creates the same adapter class. The generic type `T` must match the actual implementation; for instance, `AmqpMessageSource` belongs to Spring Integration AMQP and a Kafka source cannot be cast to it. Provide a clearly scoped customizer and verify its behavior on your running binder version.

## 4. Declaring a Pollable Binding

Suppose an invoicing service should only pull orders from RabbitMQ when it is ready to process them. Declaration:

~~~yaml
spring:
  cloud:
    stream:
      pollable-source: ordersPoll
      bindings:
        ordersPoll-in-0:
          destination: orders.pending
          group: billing-worker
          binder: rabbit
app:
  polling:
    delay-ms: 250
~~~

Each element has a distinct role:

- `spring.cloud.stream.pollable-source=ordersPoll` requests creating a pollable source named `ordersPoll`.
- The binding is named `ordersPoll-in-0` following the functional input binding convention.
- `destination` is the broker-side logical address; with the RabbitMQ binder, the binder manages exchange/queue mapping by group and Rabbit-specific properties.
- `group=billing-worker` lets instances in the same group consume from the corresponding queue, depending on binder semantics.
- `binder=rabbit` selects the RabbitMQ binder. This can be omitted when RabbitMQ is already explicitly chosen as the default binder.
- `app.polling.delay-ms` is an application-specific property for the scheduler; it is not a `MessageSourceCustomizer` property.

The application requires a Spring Cloud Stream–compatible RabbitMQ binder dependency. Configuring `pollable-source` only creates the source; it **does not create an automatic polling loop**.

## 5. Active Polling with a Scheduler

Example poller class that reads one message at a time, runs one business step, and then returns. Assume `InvoiceService` is the project's business service:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.stream.binder.PollableMessageSource;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableScheduling
class SchedulingConfiguration { }

@Component
class InvoicePollingTask {
    private final PollableMessageSource source;
    private final InvoiceService invoiceService;

    InvoicePollingTask(
        @Qualifier("ordersPoll-in-0") PollableMessageSource source,
        InvoiceService invoiceService
    ) {
        this.source = source;
        this.invoiceService = invoiceService;
    }

    @Scheduled(fixedDelayString = "${app.polling.delay-ms:250}")
    void pollOnce() {
        source.poll(message -> {
            invoiceService.createInvoice(message);
        });
    }
}
~~~

With `fixedDelay`, the next run is scheduled after the current run finishes. The handler must **complete critical work before the callback returns** if relying on default auto-acknowledgment. Do not execute asynchronous fire-and-forget work and return immediately if downstream work is unfinished and no dedicated acknowledgment strategy is in place.

This scheduler actively invokes `poll()` once per trigger. If the queue is empty, `poll` returns `false`, indicating no message was processed. Adjust the polling schedule when data is consistently absent to avoid excessive empty requests.

## 6. Customizing AmqpMessageSource at the Right Extension Point

The RabbitMQ binder supports customizing pollable sources via `MessageSourceCustomizer<AmqpMessageSource>`. The canonical case from the Spring documentation is replacing `MessagePropertiesConverter`.

This is a standalone configuration class that can be placed in a Spring Boot component-scanned package:

~~~java
import org.springframework.amqp.rabbit.support.DefaultMessagePropertiesConverter;
import org.springframework.amqp.rabbit.support.MessagePropertiesConverter;
import org.springframework.cloud.stream.config.MessageSourceCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.inbound.AmqpMessageSource;

@Configuration(proxyBeanMethods = false)
class RabbitPollableSourceConfiguration {

    @Bean
    MessagePropertiesConverter pollingPropertiesConverter() {
        // LongString header <= 4096 bytes is converted to String.
        return new DefaultMessagePropertiesConverter(4096);
    }

    @Bean
    MessageSourceCustomizer<AmqpMessageSource> rabbitSourceCustomizer(
        MessagePropertiesConverter pollingPropertiesConverter
    ) {
        return (source, destinationName, group) -> {
            if ("orders.pending".equals(destinationName)
                    && "billing-worker".equals(group)) {
                source.setPropertiesConverter(pollingPropertiesConverter);
            }
        };
    }
}
~~~

Expected behavior:

1. Spring Cloud Stream configures the `ordersPoll-in-0` pollable binding.
2. The Rabbit binder creates the AMQP source adapter and applies standard properties.
3. The framework calls `configure(source, destinationName, group)` on the customizer bean.
4. If destination and group match, the adapter uses the application-supplied converter.
5. When the application calls `poll()`, messages are pulled from the configured source.

`DefaultMessagePropertiesConverter(4096)` merely illustrates an AMQP `LongString` header conversion policy. The default usually converts `LongString` values up to 1,024 bytes into `String`; the new limit is 4,096 bytes. Headers above the threshold may remain as `LongString`. Raising the threshold can increase memory allocation, so ensure there is a clear contract requirement and test with realistic payloads/headers.

Do not confuse `MessagePropertiesConverter` with Spring Cloud Stream's content-type conversion. This converter belongs to Spring AMQP and handles properties at the AMQP protocol boundary; turning a JSON payload into a Java object still depends on other message converters and content-type settings.

## 7. Customizing by Destination and Group

An application may have multiple pollable sources: an order processing queue, a reconciliation queue, and a retry queue. Do not apply specialized customizations to all of them just because they all use RabbitMQ.

~~~java
@Bean
MessageSourceCustomizer<AmqpMessageSource> scopedCustomizer(
    MessagePropertiesConverter converter
) {
    return (source, destinationName, group) -> {
        if (!"reconciliation.events".equals(destinationName)) {
            return;
        }
        if (!"reconciliation-worker".equals(group)) {
            return;
        }
        source.setPropertiesConverter(converter);
        source.setRawMessageHeader(true);
    };
}
~~~

In a real application, **declare only one** `MessageSourceCustomizer` bean for the binder scope in use. This example is an alternative to the bean in the previous section, not an extra bean to add alongside it. To handle multiple destinations, use a single callback and branch inside it.

`setRawMessageHeader(true)` can attach the raw AMQP message to a header for error handling. This is useful when inspecting raw bytes, but increases memory retention and the risk of exposing sensitive payloads/headers in logs or traces. Enable it only when genuinely required.

Do not concatenate `destinationName` and `group` into a bean name or assume they are always non-`null`. With anonymous consumer groups, `group` may be undeclared. Use null-safe comparisons such as `"billing-worker".equals(group)`.

## 8. Advanced Setters to Consider on AmqpMessageSource

Spring Integration's `AmqpMessageSource` exposes several extension points, each altering a specific behavior:

| API on source | Purpose | Notes |
|---|---|---|
| `setPropertiesConverter(...)` | Converts Rabbit client `BasicProperties` to Spring AMQP `MessageProperties` | Check special headers and conversion cost |
| `setHeaderMapper(...)` | Maps message properties to Spring Integration headers | Avoid dropping essential correlation/tracing headers |
| `setMessageConverter(...)` | Converts payloads at the Spring AMQP source layer | Avoid conflicting with Spring Cloud Stream content-type conversion |
| `setRawMessageHeader(true)` | Attaches the raw AMQP message | Consumes memory and requires data protection |
| `setTransacted(true)` | Uses AMQP channel transactions for acknowledgment per adapter capabilities | Does not create distributed transactions with databases/Kafka |
| `setBatchingStrategy(...)` | Customizes de-batching when consuming batched messages | Must align with producer batching and error semantics |

These APIs belong to a specific binder's adapter class. Do not copy RabbitMQ configurations to Kafka or Pulsar. When library versions change, consult the JavaDoc for the exact running version and verify in integration tests.

## 9. How Does MessageSourceCustomizer Differ from ListenerContainerCustomizer?

Spring Cloud Stream provides other hooks, each serving a distinct target:

| Hook | Invoked for | Example |
|---|---|---|
| `MessageSourceCustomizer<T>` | Source created by the binder for a **pollable consumer** | `AmqpMessageSource.setPropertiesConverter(...)` |
| `ListenerContainerCustomizer<T>` | Listener container for a **message-driven consumer** | Setting an advice chain or listener container property |
| `ConsumerEndpointCustomizer<E>` | Consumer endpoint created by the binder | Adjusting adapter endpoints via implementation APIs |
| `ProducerMessageHandlerCustomizer<H>` | Producer message handler | Customizing the handler that sends messages to the broker |

If your consumer uses a standard `Function<String, String>` and the framework invokes the function whenever the broker delivers a message, look at `ListenerContainerCustomizer` or appropriate binding properties. `MessageSourceCustomizer` only applies on the pollable path. If no pollable binding is configured, the customizer—even if instantiated by Spring—will not create a polling source.

## 10. Do Not Confuse Configuration Time with Runtime

Typical timeline:

~~~text
Application context start
  -> Binder resolves pollable binding and destination/group
  -> Binder creates underlying MessageSource
  -> Binder applies standard properties
  -> MessageSourceCustomizer.configure(source, destination, group)
  -> Application scheduler starts invoking PollableMessageSource.poll(...)
  -> Source receives one message per successful poll
  -> Handler completes; acknowledgment/error policy is applied
~~~

Consequences:

- Do not run business processing or fetch messages from the broker inside `configure`.
- Do not increment a counter named `messages.processed` inside this callback, because one customizer call does not equal one message.
- Do not rely on the customizer to update `@Scheduled` delays; the scheduler is an independent component.
- A binding can be recreated across lifecycle changes; do not write logic assuming the callback runs strictly once per JVM lifetime.
- Customization should be short configuration logic, deterministic, free of hard-to-undo side effects, and must not retain references to the source after it is no longer managed.

## 11. Ack, Reject, and Requeue When Polling

`PollableMessageSource.poll(handler)` processes one message at a time through a callback. By default, when the handler finishes normally, the message is usually acknowledged. If the handler throws an exception, Spring Cloud Stream's error handling flow can be triggered.

Key nuances to understand:

- Each poll attempts to fetch **one message**; the boolean return value indicates whether a message was processed.
- If the handler throws an exception, the framework can send an `ErrorMessage` to `<destination>.<group>.errors` and the global `errorChannel`.
- If no subscriber handles the error channel, the error may simply be logged and the message still acknowledged as successful. Do not assume an arbitrary exception always triggers a requeue.
- `RequeueCurrentMessageException` is the way to request requeuing the current message per binder-supported mechanisms.
- `AcknowledgmentCallback.noAutoAck()` transfers ack/nack responsibility to the application. Once used, you must complete the ack or nack; do not leave callbacks dangling and leaking resources.

Example actively requeuing transient failures:

~~~java
@Scheduled(fixedDelayString = "${app.polling.delay-ms:250}")
void pollOnce() {
    source.poll(message -> {
        try {
            invoiceService.createInvoice(message);
        }
        catch (TemporaryDependencyException ex) {
            throw new RequeueCurrentMessageException(
                "Billing dependency is temporarily unavailable", ex);
        }
    });
}
~~~

In the example above, `TemporaryDependencyException` is an application-defined business exception. Permanent data errors should not be requeued indefinitely; establish separate reject, DLQ, alerting, and investigation procedures.

With Kafka, requeuing interacts with offsets and can cause already-processed records to be redelivered later. With RabbitMQ, requeuing can disrupt ordering and create redelivery loops. Idempotency, consumer groups, partitions, and DLQs must be tested against a real broker.

## 12. When Is Manual Acknowledgment Needed?

Only use manual ack when there is a concrete reason—such as handing work off to another worker and acknowledging only after that worker finishes.

~~~java
source.poll(message -> {
    AcknowledgmentCallback ack =
        StaticMessageHeaderAccessor.getAcknowledgmentCallback(message);
    ack.noAutoAck();

    // The application must later call acknowledge(ACCEPT,
    // REJECT or REQUEUE) on every path including failures.
    asyncWorker.submit(message, ack);
});
~~~

This pattern illustrates responsibility, **not a complete production example**: a real worker must define timeouts, graceful shutdown behavior, whether the callback is safe to ack from another thread, and exception handling. Never design fire-and-forget flows where the broker considers a message done before the work is actually persisted.

If a handler can finish synchronously, letting it complete successfully and allowing the framework to auto-ack is usually safer and simpler.

## 13. Scaling Pollers: Customizers Do Not Control Concurrency

To raise pollable consumer throughput, examine these limits:

1. **Polling rate.** If the scheduler polls too slowly, the broker still has queued messages while workers sit idle.
2. **Processing time.** If each poll processes synchronously for 500 ms, a single poller can complete at most roughly two messages/second, excluding broker round-trip time.
3. **Number of pollers/instances.** You can add instances, but you must understand how the binder and broker distribute work.
4. **Broker capacity.** Rabbit queues, Kafka partitions, or network I/O can become bottlenecks.
5. **Downstream limits.** Databases, APIs, thread pools, and memory may not sustain overly high concurrency.

For example, if a poller takes 40 ms on average to process a message with negligible delay, theoretical single-threaded capacity is roughly 25 messages/second. Adding a 200 ms delay after each execution lowers throughput significantly. You cannot speed it up by changing `setPropertiesConverter(...)`; you must adjust the schedule, increase valid parallelism, or optimize the work.

With a RabbitMQ queue, multiple instances in the same group can compete to pull messages from the queue; measure real behavior, especially when generating many empty poll requests. With Kafka, partitions and consumer groups/offsets bound parallelism. Do not call `poll()` concurrently on the same source from multiple threads unless the binder guarantees thread safety and acknowledgment semantics. When scaling out, prefer scaling instances with clear consumer boundaries and benchmarking.

## 14. Polling Schedules and Strategies to Reduce Empty Polls

When a queue is mostly empty, an unthrottled `while(true)` loop places unnecessary load on the broker and CPU. One option is a bounded fixed delay; if polling needs to be fast when messages exist and slow when idle, use a dynamic scheduler or controlled backoff.

~~~java
boolean received = source.poll(message -> handle(message));
if (received) {
    // Record one successfully handled poll; next run can be sooner.
}
else {
    // No message available; wait according to an idle backoff policy.
}
~~~

Do not `Thread.sleep` for long periods inside callbacks if occupying a thread shared by multiple pollers. With `@Scheduled`, prefer tuning intervals via configuration and watching empty-poll rates. If running multiple pollers on the same node, size the scheduler thread pool deliberately and ensure each source has clear concurrency boundaries.

## 15. Observability and Setting SLOs for Pollable Pipelines

Measure at least:

| Metric | Purpose | Where to measure |
|---|---|---|
| `poll.attempts` | How many times the application invokes poll | Scheduler around `poll()` |
| `poll.empty` | Ratio of empty polls | When `poll()` returns `false` |
| `poll.handled` | Messages successfully processed | After successful handler callback |
| `poll.duration` | Poll + processing duration | Timer around `poll()` invocation |
| `poll.errors` | Reception/processing errors | Error handler and correlated logs |
| Queue depth / consumer lag | Remaining broker backlog | RabbitMQ/Kafka monitoring |
| Oldest-message age | How long messages wait | Broker/metadata and timestamps |
| Redelivery / DLQ count | Recovery health, repeat failures | Broker and error pipeline |

Do not increment `poll.handled` when the customizer runs. The customizer executes only during configuration lifecycle. Avoid attaching message IDs, customer IDs, or raw payloads as metric labels due to high cardinality and data-leak risks. Use normalized, bounded destination/group names if permitted by your observability policy.

Example target: process at least 100 messages/second, keep p95 time from broker arrival to completion under 2 seconds, keep empty-poll ratio below infrastructure cost thresholds, and lose zero acknowledged messages. All of these goals must be measured in an environment with a real broker under realistic load.

## 16. Testing Customizers Across Appropriate Test Layers

Testing can be split into three tiers:

**Tier 1 — Configuration Logic Tests**

- Instantiate an appropriate `AmqpMessageSource` or use a mock, then invoke `configure(source, destination, group)`.
- Verify `setPropertiesConverter` is called only when destination and group match.
- Verify other destinations/groups remain unaffected.
- Verify the customizer does not depend on runtime data or side effects.

**Tier 2 — Message Processing Tests**

- Use the Spring Cloud Stream Test Binder to verify code calling `PollableMessageSource.poll()`, payload mapping, and success/error handling.
- The Test Binder uses an in-JVM simulated source; it **does not verify** that the real RabbitMQ binder created an `AmqpMessageSource` and applied your customizer.

**Tier 3 — Integration Tests with Real RabbitMQ**

- Start RabbitMQ in Testcontainers or a dedicated test broker and run the application with the Rabbit binder.
- Verify the callback runs for the right destination/group when the binding is created.
- Publish messages with `LongString` headers sized on both sides of the configured threshold.
- Poll messages and inspect received headers/payloads; measure memory and latency with large headers.
- Test successful processing, transient errors triggering requeue, permanent errors, restarts, and duplicates.
- Run multiple valid instances/pollers and verify throughput, message distribution, and queue depth.

Never conclude a customizer works against a broker solely from unit tests with mocks or the Test Binder. Production deployments need at least one integration test running through the target binder.

## 17. Common Configuration Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| `rabbitSourceCustomizer` is never called | No pollable binding declared or binder did not create the expected source type | Check `pollable-source`, binder type, and lifecycle |
| App starts but receives no messages | No scheduler is calling `poll()` | Enable scheduling and invoke poll actively |
| Setter has no effect | Destination/group filter mismatch or different implementation | Inspect callback arguments and actual source JavaDoc |
| Changed delay in customizer but poll rate stayed the same | Poll schedule lives in the scheduler, not the source customizer | Configure the scheduler separately |
| Headers lost after conversion | `MessagePropertiesConverter` or header mapper mismatch | Test RabbitMQ header mapping |
| Raw message appears in logs/traces | Enabled `setRawMessageHeader(true)` and logged all headers | Disable raw header or redact logs/tracing |
| Error logged but message not redelivered | Error channel flow treated it as handled | Use an explicit requeue/ack strategy and test with the broker |
| Queue fills up despite idle CPU | Polling too infrequently or scheduler starved for threads | Measure empty rate, interval, and actual throughput |
| CPU/network spikes during low traffic | Polling loop too tight with many empty requests | Add idle backoff and monitoring |
| Duplicates during scale/restart | Ack not tied to work completion or due to requeue | Apply idempotency and verify offset/ack policy |
| Customizer bean conflict | Multiple beans of same type in context or mismatched generic type | Consolidate logic into one bean and check binder support |

## 18. Hands-On Exercise You Can Do Yourself

Build a service that periodically pulls payment commands from RabbitMQ:

1. Create a Spring Boot project with the Spring Cloud Stream RabbitMQ binder and Scheduling.
2. Declare `pollable-source=paymentsPoll`, binding `paymentsPoll-in-0`, destination `payments.pending`, group `payment-worker`.
3. Write a scheduler that calls `PollableMessageSource.poll()` every 250 ms.
4. Add a `MessageSourceCustomizer<AmqpMessageSource>` setting a `DefaultMessagePropertiesConverter(4096)` exclusively for that destination/group.
5. Send 100 messages with normal headers plus several messages containing large `LongString` headers.
6. Verify every message is processed and acknowledged per the expected policy.
7. Increase the poll rate and measure throughput, CPU, empty polls, and p95 latency.
8. Start a second instance; observe queue depth and verify no business operation executes twice when the same event is redelivered.
9. Simulate a transient error with `RequeueCurrentMessageException`, then verify the message is reprocessed cleanly.
10. Add another pollable destination and confirm the customizer does not modify out-of-scope sources.

Completion criteria: the customizer callback receives only the target source, polling is driven by the scheduler, headers convert accurately, the application handles errors, and replays do not corrupt business outcomes.

## 19. Pre-Deployment Checklist

- [ ] Chose a pollable consumer because active polling is required, rather than replacing message-driven consumers out of habit.
- [ ] `<name>-in-0` binding, destination, group, and binder are declared accurately.
- [ ] A scheduler/poller actually invokes `poll()` with a bounded frequency.
- [ ] `MessageSourceCustomizer` is used only for advanced properties not configurable in YAML.
- [ ] Generic type `T` matches the binder's source implementation.
- [ ] Only one matching customizer exists in the context, or bean selection behavior is verified.
- [ ] Null-safe destination/group filtering is applied so other sources are unaffected.
- [ ] Callback does not process business messages, spawn threads, or retain unnecessary source references.
- [ ] Distinguished AMQP properties converter from Spring Cloud Stream content-type converter.
- [ ] Evaluated memory impact, raw headers, and sensitive data exposure.
- [ ] Ack/requeue, error channel, and DLQ tested against a real broker.
- [ ] Measured empty polls, throughput, p95 latency, backlog, and redelivery under scaling.
- [ ] Integration tests run against the real binder instead of relying solely on Test Binder.
- [ ] Confirmed Spring Cloud Stream, Spring Integration, and binder versions support the used APIs.

`MessageSourceCustomizer` is an extension point for customizing a source adapter **after** the binder applies standard properties. For pollable RabbitMQ consumers, you can attach a `MessagePropertiesConverter` to `AmqpMessageSource` for the matching destination and group. However, **poll cadence, parallelism, and acknowledgment correctness remain governed by the application alongside the binder and broker**. To scale safely, combine a cleanly scoped customizer, a bounded scheduler, idempotency, and real-broker backlog/latency monitoring.

## References

- [Spring Cloud Stream — Binding Properties, Advanced Consumer Configuration](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Producing and Consuming Messages, Using Polled Consumers](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream 5.0.2 API — MessageSourceCustomizer](https://javadoc.io/static/org.springframework.cloud/spring-cloud-stream/5.0.2/spring.cloud.stream/org/springframework/cloud/stream/config/MessageSourceCustomizer.html)
- [Spring Integration 6.5.2 API — AmqpMessageSource](https://docs.spring.io/spring-integration/docs/6.5.2/api/org/springframework/integration/amqp/inbound/AmqpMessageSource.html)
- [Spring AMQP — Message Properties Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html)
