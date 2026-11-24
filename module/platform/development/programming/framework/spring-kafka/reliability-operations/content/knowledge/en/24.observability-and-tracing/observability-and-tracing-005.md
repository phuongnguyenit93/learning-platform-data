# Consumer trace context

In a Spring Kafka system, an event may originate from an HTTP request, be sent to Kafka by a producer, and traverse multiple consumers, retry topics, or dead-letter topics (DLTs) before yielding a final outcome. When each service logs in isolation, operations teams struggle to answer: **where did this record originate, which services did it pass through, and which step failed or slowed down?**

**Consumer trace context** is the tracing metadata carried alongside a Kafka record so the consumer can adopt upstream context from the producer and relate its processing work to the upstream workflow. Spring Kafka 3.x integrates with **Micrometer Observation**; when paired with Micrometer Tracing, a propagator, and a suitable tracing exporter, listeners can create spans that link back to the producer trace.

In operations, distinguish: **propagation** carries context via Kafka headers; **observation/span** models activity inside the JVM; **export** sends spans to the tracing backend. Having a trace header does not automatically mean the trace appears in Jaeger/Tempo. Conversely, a span without a parent does not prove the record failed; the record may simply have lacked upstream context.

## 1. What problems does trace context solve?

Consider an ordering workflow:

~~~text
HTTP POST /orders
       |
       v
order-api
       |
       +--> Kafka: orders.created
                     |
                     v
                order-validator
                     |
                     +--> Kafka: orders.validated
                                    |
                                    v
                                billing-service
                                    |
                                    +--> HTTP payment API
~~~

A working tracing pipeline helps operators trace relationships across the initial HTTP request, producer send, listener execution, database operations, and downstream HTTP calls. Questions it answers include:

- Which producer created the record and under which request context?
- Which consumer group and listener received the record?
- How long did the listener take, and which step consumed the time?
- On which attempt did the record fail, and did it route to a retry topic or DLT?
- Was the event redelivered due to a rebalance, restart, or manual replay?
- Is the consumer slow due to business processing or because lag accumulated before the record arrived?

**Trace ID is not an event ID.** A trace ID links observed operations; the same event can be replayed under a new trace. An event ID must stay stable across deliveries to support idempotency and auditing.

## 2. Trace, span, context, and propagation

| Term | Meaning |
|---|---|
| Trace | A collection of spans describing a cross-service flow. |
| Trace ID | Shared identifier of the trace. |
| Span | An observed operation, such as an HTTP request, producer send, or consumer processing. |
| Span ID | Individual identifier of a span. |
| Parent/span link | Relationship between spans, depending on instrumentation and messaging semantic conventions. |
| Trace context | Data telling downstream services what upstream info is needed to continue or link the trace. |
| Propagator | Component that injects/extracts context via HTTP/Kafka headers. |
| Baggage | Metadata carried alongside context when configured; requires access and size controls. |

Example:

~~~text
Trace T
  HTTP request                         span A
      |
      +-- Kafka producer send          span B
              |
              +-- Kafka listener       span C
                      |
                      +-- DB operation  span D
                      +-- HTTP call     span E
~~~

This diagram is illustrative. OpenTelemetry messaging conventions may model relationships as parent-child or **span links**, especially in asynchronous or batched flows. When testing, never assume every consumer span is always a direct child of the producer span; account for the chosen instrumentation version and semantic conventions.

## 3. Kafka headers carry trace context

A Kafka `ConsumerRecord` has topic, partition, offset, key, value, and **headers**. The Kafka broker stores headers as metadata; the broker does not generate trace IDs or inspect trace headers to decide offsets.

Example record carrying W3C Trace Context:

~~~text
topic       = orders.created
partition   = 2
offset      = 1875
key         = order-4821
value       = {...}
headers:
  traceparent = 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
  tracestate  = ...
  event-id    = order-4821-created
~~~

The `traceparent` header has the structure:

~~~text
version-trace-id-parent-id-flags
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

The trace ID is 32 hex characters, parent/span ID is 16 hex characters, and flags carry details such as the sampling decision. This is the W3C format, **not the only format**: B3 propagation uses different headers.

Producer and consumer must agree on a propagator. A consumer looking only for `traceparent` might mistakenly conclude "tracing is broken" while the producer is emitting B3; the right check is inspecting propagation configuration on both sides.

## 4. Producer injection and consumer extraction flow

~~~text
HTTP request
    |
    v
Current context in order-api
    |
    v
KafkaTemplate.send()
    |
    +-- Producer observation/span
    +-- Propagator injects context into record.headers()
    |
    v
Kafka broker stores record and headers
    |
    v
Consumer poll()
    |
    +-- Propagator extracts from headers
    +-- Listener observation/span
    +-- Current scope activated accordingly
    |
    v
@KafkaListener
    |
    +-- DB / HTTP / downstream producer
    |
    v
Observation finishes -> span exporter
~~~

Crucial point: **a producer's `ThreadLocal` cannot cross a Kafka broker into the consumer's JVM on its own**. Metadata must be serialized into headers or an equivalent context-transfer mechanism.

If the producer is not instrumented, the consumer still needs to process business logic normally. Depending on configuration, it may start a new root trace. Never use "missing `traceparent`" as a default reason to drop a Kafka record.

## 5. Enabling Spring Kafka Observation on the listener

In Spring Kafka 3.x, enable observation on `ContainerProperties`:

~~~java
@Configuration
public class KafkaObservationConfig {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            observedKafkaListenerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setObservationEnabled(true);

        return factory;
    }
}
~~~

Imports:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
~~~

Use that exact factory on the listener:

~~~java
@Component
public class OrderConsumer {

    @KafkaListener(
        id = "observed-orders",
        topics = "orders.created",
        groupId = "order-validator",
        containerFactory = "observedKafkaListenerFactory"
    )
    public void consume(ConsumerRecord<String, String> record) {
        orderService.validate(record.value());
    }
}
~~~

Calling `setObservationEnabled(true)` allows Spring Kafka's infrastructure to create observations in the listener; to achieve distributed tracing, you still must configure **`ObservationRegistry`, a tracing bridge, and a propagator**.

If Spring Boot already auto-configures a default listener factory, do not create a second factory and forget to set `containerFactory` on the listener. In projects with multiple factories, know **which listener uses which factory**.

## 6. Enabling observation on the producer KafkaTemplate

On the producer side:

~~~java
@Bean
KafkaTemplate<String, String> observedKafkaTemplate(
        ProducerFactory<String, String> producerFactory) {

    KafkaTemplate<String, String> template =
            new KafkaTemplate<>(producerFactory);

    template.setObservationEnabled(true);
    return template;
}
~~~

When `KafkaTemplate` uses a proper observation/tracing bridge, producer instrumentation can create spans and inject context into Kafka record headers.

~~~java
kafkaTemplate.send(
        "orders.created",
        "order-4821",
        "{\"orderId\":\"order-4821\"}");
~~~

**Consumer observation does not add headers for producers in other services.** If an upstream producer uses a raw `KafkaProducer`, Kafka Connect, or a non-Java client, check the instrumentation of that producer itself. An auto-instrumentation agent may instrument the Kafka client via its own mechanism; avoid enabling two overlapping layers of producer instrumentation without understanding how their spans interact.

## 7. Micrometer Tracing and the tracing backend

A complete Spring Boot pipeline typically requires:

1. Actuator / Micrometer Observation infrastructure.
2. A tracing bridge such as Micrometer Tracing bridge to OpenTelemetry or Brave.
3. A propagator compatible with upstream (W3C Trace Context, B3, or organizational standard).
4. A span exporter/agent shipping data to a collector/backend.
5. Observation enabled on the actual running template and listener containers.

Example sampling configuration for supported Spring Boot versions:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
~~~

`0.10` is a 10% target sampling rate per sampler policy; parent sampling and exporters can make actual observed ratios differ. Java configuration `setObservationEnabled(true)` does not install a bridge or exporter. Your project needs dependencies matching your Spring Boot and tracing backend versions.

~~~text
Spring Kafka
   |
   +--> ObservationRegistry
   |      |
   |      v
   |   Micrometer Tracing bridge
   |      |
   |      +--> Propagator (inject/extract)
   |      +--> Span scope
   |
   v
Exporter / Agent
   |
   v
OTel Collector -> Jaeger / Tempo / other
~~~

A record carrying a `traceparent` header while the backend stays empty can be caused by **sampling, exporter, collector ingestion, retention**, or a listener not creating spans. Inspect each layer.

## 8. Reading the current trace ID inside a listener

When the tracing bridge is active, you can inject Micrometer's `Tracer` to inspect the active span:

~~~java
@Component
public class TracedOrderConsumer {

    private static final Logger log =
            LoggerFactory.getLogger(TracedOrderConsumer.class);

    private final Tracer tracer;

    public TracedOrderConsumer(Tracer tracer) {
        this.tracer = tracer;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-validator",
        containerFactory = "observedKafkaListenerFactory"
    )
    public void consume(ConsumerRecord<String, String> record) {
        Span current = tracer.currentSpan();

        String traceId = current == null
                ? "missing"
                : current.context().traceId();

        log.info(
            "Kafka record received: traceId={}, topic={}, partition={}, offset={}",
            traceId,
            record.topic(),
            record.partition(),
            record.offset());

        orderService.validate(record.value());
    }
}
~~~

Key imports:

~~~java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
~~~

This example requires an actual `Tracer` bean. If `currentSpan()` returns `null`, verify listener observation, the bridge, the active scope, and whether the listener runs on an instrumented thread/execution path.

Never use trace ID as an **idempotency key**. A replayed event may get a new trace; deduplication requires a stable event ID.

## 9. Reading raw trace headers for diagnostics

When you need to verify what actually crossed Kafka, inspect header bytes:

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;

void inspectHeader(ConsumerRecord<String, String> record) {
    Header h = record.headers().lastHeader("traceparent");

    if (h == null) {
        log.info("W3C traceparent absent: topic={}, partition={}, offset={}",
                record.topic(), record.partition(), record.offset());
        return;
    }

    String raw = new String(h.value(), StandardCharsets.UTF_8);
    log.debug("W3C traceparent present: {}", raw);
}
~~~

This is an **inspection technique**, not a complete propagator. Keep in mind:

- A missing `traceparent` header can be completely normal if upstream uses B3.
- Kafka `Headers` may contain multiple headers with the same key.
- Not every UTF-8 value resembling `traceparent` is valid; propagators validate structure.
- Kafka Connect, custom producers, recoverers, or gateways can alter or copy headers.
- Avoid logging raw trace headers or full payloads in production unless necessary.

Do not craft a new `traceparent` by randomly assembling strings when the tracing library already manages injection.

## 10. Trace context and MDC logging

A tracing bridge can populate `traceId` and `spanId` into MDC so logs within a consumer invocation link to spans in the backend.

~~~text
timestamp=2026-11-15T12:00:00Z
service=order-validator
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=9124ab77cc881234
topic=orders.created
partition=2
offset=1875
eventId=order-4821-created
message="validation started"
~~~

This is an illustrative custom application log format, not Spring Kafka's default output.

Three kinds of identifiers should coexist:

| ID / metadata | Used for |
|---|---|
| `traceId` | Finding spans/logs belonging to the same trace. |
| `topic-partition-offset` | Locating a specific record occurrence in Kafka. |
| `eventId` | Tracking the same business event across retries, DLTs, and replays. |
| `causationId` | Linking a new event to the event that caused it per business policy. |

If logs omit trace IDs while the backend still shows spans, check your **MDC/logging pattern** configuration, not just Kafka headers. If trace IDs appear in logs yet the backend has no spans, check sampling/exporter. The two observability channels can be configured independently.

## 11. Propagation across threads and async callbacks

Trace scopes normally bind to the current execution context. When a consumer hands work off to another thread, do not assume context follows automatically.

~~~text
Kafka consumer thread
    |
    +-- current trace A
    |
    +-- executor.submit(task)
                  |
                  v
           Worker thread
           current trace may be empty
~~~

Example:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "observedKafkaListenerFactory"
)
public void consume(String payload) {
    executorService.submit(() -> {
        // Do not assume this thread shares the consumer thread's
        // tracing scope.
        paymentService.process(payload);
    });
}
~~~

Use **Micrometer Context Propagation**, `TaskDecorator`, executor wrappers, or Reactor's context mechanism appropriate for your framework and version. Never pass thread-local state via a static variable; concurrent listener threads handle different traces and would leak context across them.

**Do not confuse context propagation with acknowledgment.** If a listener submits an async task and returns before the task completes, offsets may commit prematurely depending on the container ack mode. Getting trace links right does not guarantee business side effects or Kafka delivery semantics are sound.

## 12. Consumer sending output to another topic

When a consumer processes input and publishes output, there are two consecutive tracing boundaries: receiving input and sending output.

~~~java
@Component
public class OrderValidator {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderValidator(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
        topics = "orders.created",
        containerFactory = "observedKafkaListenerFactory"
    )
    public void handle(ConsumerRecord<String, String> record) {
        String normalized = normalize(record.value());
        kafkaTemplate.send("orders.validated", record.key(), normalized);
    }
}
~~~

If listener observation and template observation operate within the same scope, producer instrumentation can pick up the current context and inject headers for downstream. However, if the template was built from an uninstrumented factory or the code uses `KafkaProducer` directly, propagation can break.

If an application copies **all Kafka headers** from input to output, be careful: an old raw `traceparent` could be retained unintentionally, causing duplicate headers or wrong span relationships. Let the propagator handle trace injection; business metadata like `eventId`/`causationId` should live in separate headers.

## 13. Batch listeners and multiple upstream traces

A batch can contain records from multiple producers with different contexts:

~~~text
poll():
   record A -> trace A
   record B -> trace B
   record C -> trace C

@KafkaListener(List<ConsumerRecord<...>> batch)
~~~

You cannot assume there is **one parent trace** suitable for the whole batch. Tracing/batch observation support and how span links are created depend on the Spring Kafka version and specific instrumentation.

If per-record tracing in a batch is needed:

- Verify to what extent your Spring Kafka version supports observations on batch listeners.
- Preserve `eventId` and `topic-partition-offset` for each record.
- If creating per-record spans manually, extract context with the standard propagator—never apply the first record's context to the entire batch.
- Balance span volume against throughput and sampling.
- Test partial batch failures and offset semantics separately; tracing does not fix acknowledgments.

Never use the trace ID of one record in a batch as a shared idempotency key.

## 14. Retry, DLT, and trace context

A failing record can be retried immediately inside the consumer (blocking retry), published to a retry topic (non-blocking retry), or sent to a DLT.

~~~text
orders.created
      |
      v
consumer attempt 1 -- error -->
      |
      v
orders-retry-1000
      |
      v
consumer attempt 2 -- error -->
      |
      v
orders.DLT
~~~

Distinguish these cases:

| Case | Impact on tracing |
|---|---|
| Blocking retry in the same container | Reprocesses the record with the same upstream headers; how observations/spans appear per attempt depends on the framework. |
| Non-blocking retry | Record is republished to another topic, potentially generating a new producer span and new headers. |
| DLT publishing | Recoverer sends the failed record to a destination, potentially copying/updating headers. |
| Manual replay | May start a new trace even while preserving the business event ID. |

With `DeadLetterPublishingRecoverer` and `@RetryableTopic`, downstream context depends on the producer template, tracing instrumentation, header copying behavior, and Spring Kafka version. **Do not assume every retry or DLT message keeps the same trace ID**, and do not assume every forwarding step generates a new observation without checking configuration.

When investigating failed records, retain:

- A stable business event ID.
- Original topic/partition/offset and current topic/partition/offset.
- Attempt and recovery metadata.
- Exception class, sanitized message, and DLT publish status.
- Current trace ID; if needed, original trace ID or causation ID in a **separate** field.

Do not turn `traceparent` into a log of "all historical trace IDs"; let the propagator manage its format while provenance/audit lives in event metadata.

## 15. Replaying days later does not require continuing the old trace

Example:

~~~text
Day 1:
  HTTP -> event E -> consumer fail -> DLT
  trace ID = T1

Day 3:
  Operator replays event E -> consumer success
  trace ID = T2 (possible)
  event ID = E (preserved)
~~~

Starting a fresh trace for a replay workflow days later often makes more sense than trying to extend the old trace: backends have their own retention, sampling, and semantics. Durable correlation belongs in **`eventId`, `causationId`, `replayId`**, and audit logs—not in assuming the old trace ID still exists in the tracing backend.

Replays must have idempotency and proper operational authorization; tracing cannot prevent charging a payment twice.

## 16. Span success does not mean committed offset

A logical processing flow:

~~~text
poll record
    |
    v
listener observation starts
    |
    v
@KafkaListener processes
    |
    v
listener returns / observation ends
    |
    v
container commits offset per ack mode or transaction
~~~

The exact ordering among observation, acknowledgment, error handler, and transaction commit depends on listener mode, container, and Spring Kafka version.

**Never treat a successful span as proof that the offset committed.** The app can crash after the listener returns and before the offset commits, causing redelivery. Likewise, an error span may trigger retry or DLT recovery while the container continues per error policy.

To evaluate delivery reliability, combine traces with:

- Consumer group committed offsets and lag.
- Listener exceptions, `DefaultErrorHandler`, and after-rollback policies.
- Kafka transaction commits/aborts if applicable.
- DLT ingress and recovery failures.
- Business idempotency and side effects.

Trace context provides observability, not exactly-once delivery or database rollback capability.

## 17. Sampling and why a header exists without a backend span

High-throughput systems usually sample traces to reduce overhead:

~~~text
Record has traceparent
        |
        v
Consumer extracts context
        |
        v
Sampling policy
    /            \
sampled        not sampled
   |                |
export span      backend may have no span
~~~

Possible reasons for missing spans:

- Upstream trace was not sampled under parent policy.
- Consumer uses a low sampling probability.
- Collector or exporter filtered/dropped spans under overload.
- Spans did not flush before pod shutdown.
- Tracing backend retention expired.
- Incompatible propagator or listener observation disabled.

Do not raise sampling to 100% across all production Kafka consumers without evaluating CPU, network, exporter queues, and storage cost. During an incident investigation, temporarily raise sampling or use controlled tail-sampling depending on your platform.

## 18. Baggage, privacy, and trust boundaries

Kafka headers can persist for the topic's retention period, get copied to retry topics/DLTs, and be read by any authorized consumer group. **Never put sensitive data into tracing context** just because it is convenient to access.

Avoid putting verbatim:

- Access tokens, API keys, cookies, or passwords.
- Emails, phone numbers, payment cards, and unnecessary personal data.
- Large business payloads and stack traces containing input data.
- High-cardinality tenant/user IDs as metric tags.
- Unbounded baggage without an allowlist and size limits.

**Trace context is not an authentication mechanism.** An untrusted producer can send a forged `traceparent`; consumers must never use trace IDs or baggage to enforce tenant isolation or identify authenticated users.

If tenant info is needed in tracing, apply allowlisting/anonymization, retention policies, and proper access controls. Authorization data must come from trusted authentication mechanisms.

## 19. Trace context failure matrix

| Symptom | Likely cause | How to investigate |
|---|---|---|
| Producer span exists, consumer starts a new trace | Header not injected, stripped, or mismatched propagators. | Inspect raw Kafka headers and W3C/B3 config. |
| Record has `traceparent`, `currentSpan()` is null | Listener observation disabled, missing tracing bridge, or lost scope. | Check factory, `Tracer` bean, and active context. |
| Logs lack trace ID while backend has spans | MDC/logging pattern not configured. | Check log correlation and thread scope. |
| Logs have trace ID while backend lacks spans | Sampling/exporter/Collector/retention. | Inspect sampling and the tracing pipeline. |
| Trace breaks after `@Async` or executor | Context did not cross to the new thread. | Add appropriate context propagation / task decorator. |
| Retry/DLT gets a new trace | Forwarder injects fresh context, copies headers differently, or replay is a new workflow. | Inspect recoverer, template observation, and event ID. |
| Batch is tied to the first record's trace | Multiple upstream contexts not handled properly. | Check batch semantics and span links. |
| Tracing spikes CPU or latency | High sampling, large attributes, or congested exporter. | Check span rate, queues/drops, CPU, and exporter. |

Never "fix" `traceparent` via string replacement without understanding the propagation specification; fabricated trace relationships hinder debugging even more than missing traces.

## 20. Runbook: consumer loses trace link

Suppose `order-api` has an HTTP trace and producer span, yet the trace omits the `order-validator` step.

**Step 1 — Verify data flow.** Did the record actually reach the topic/partition? Did the consumer group read it? Use event ID, offset, and logs to locate it rather than relying solely on the tracing backend.

**Step 2 — Check the producer.** Does the producer use an observed `KafkaTemplate`, an auto-instrumented `KafkaProducer`, or another publish path? Are headers injected?

**Step 3 — Check the propagator.** Do both sides use W3C, B3, or another format? Is the header valid and untouched by bridges/proxies/connectors?

**Step 4 — Check the listener container.** Is `setObservationEnabled(true)` set on the **actual factory**? Are there multiple listener factories or custom containers?

**Step 5 — Check the current context.** Inside the listener, is `Tracer.currentSpan()` non-null? If so, does its link to upstream match instrumentation conventions?

**Step 6 — Check sampling and export.** Was the span created but never exported due to sampling, collector failures, quotas, or retention?

**Step 7 — Check async boundaries.** Does the listener hand work to an executor, Reactor, or callback that drops scope?

**Step 8 — Check retry/DLT.** Was the record forwarded to another topic, changing headers or trace context? Is a stable event ID available to reconstruct history?

**Step 9 — Verify with a fresh record.** Publish a test event with a unique ID; inspect Kafka headers, listener logs, backend spans, and downstream hops together.

**Step 10 — Record postmortem details.** Document the Spring Kafka/Boot versions, tracer bridge, propagator, sampling, and exporter settings for future reference.

Never trigger a large-scale replay just to find a trace; replays can cause side effects and must follow dedicated data procedures.

## 21. Trace latency vs. consumer lag

Example:

~~~text
Producer span:
  10:00:00.000 -> 10:00:00.035

Kafka record sits in topic

Consumer span:
  10:00:03.200 -> 10:00:03.280
~~~

The gap between producer and consumer can stem from backlog, container pauses, retry topic delays, scheduling, or broker/network latency. **Do not label that entire gap as broker latency**.

To diagnose accurately, combine:

- Producer send completion and transaction commit.
- Record timestamp, producer timestamp, and consumer receive time.
- Consumer lag, assignment, pause/resume, and poll rate.
- Listener processing duration and dependency spans.
- Retry/DLT, backoff delays, and business processing delays.

If computing message age from timestamps, verify whether the topic uses `CreateTime` or `LogAppendTime` and check clock skew across hosts. Never treat clock skew as an exact "Kafka queue time."

## 22. Propagation integration testing

An integration test scenario should use a real Kafka broker (Testcontainers or embedded Kafka) with a tracing test exporter/handler:

1. Create a dedicated topic and consumer group for the test.
2. Configure producer and listener with compatible observation/tracing bridges and propagators.
3. Open an upstream observation/span in the test and publish a record with a unique event ID.
4. Wait for the listener to receive the record with a bounded timeout.
5. Assert the record carries propagation headers matching the chosen format.
6. Assert the consumer creates an observation/span and trace linkage matching the instrumentation contract.
7. Have the consumer publish to an output topic and observe downstream context.
8. Test a record **without trace headers** to confirm business logic still executes normally.
9. Test async boundaries, retry topics, or DLTs if used by the system.
10. Assert the exporter/test collector receives spans when sampling is enabled, then clean up test resources.

Avoid hardcoding brittle assertions on exact span names or parent-child structures if version upgrades can evolve semantic conventions. Focus on verifying propagation, record handling, and trace output per your running version's contract.

## 23. Operations checklist

- [ ] Producer and consumer use compatible propagators, e.g., W3C Trace Context.
- [ ] Actual `KafkaTemplate` and listener factories enable Micrometer Observation when using Spring Kafka instrumentation.
- [ ] `ObservationRegistry`, tracing bridge, exporter, and tracing backend are completely configured.
- [ ] A diagnostic method exists to inspect raw headers on a test record.
- [ ] Logs include `traceId`/`spanId` and `topic-partition-offset` appropriately without leaking sensitive payloads.
- [ ] Trace IDs never replace event IDs, idempotency keys, or authentication.
- [ ] Context propagation is configured for executors, `@Async`, Reactor, and callbacks where needed.
- [ ] For batch listeners, actual version-specific tracing behavior is verified.
- [ ] For retry/DLT, header copy/replacement behavior is known and event IDs stay stable.
- [ ] Span success is clearly distinguished from offset acknowledgment/commit.
- [ ] Sampling, cardinality, and baggage privacy policies are established.
- [ ] Dashboards pair tracing with lag, producer latency, retry/DLT, and transaction metrics.
- [ ] Runbooks separate propagator, context scope, sampling, and exporter issues.
- [ ] At least one end-to-end integration test covers producer, broker, and consumer.

## 24. Conclusion

**Consumer trace context** ties observability together across asynchronous services on Kafka. Producers inject context into record headers, consumers extract it to create appropriate observations/spans, and downstream calls continue or link the trace through tracing instrumentation. Spring Kafka and Micrometer Observation streamline integration, yet end-to-end visibility only works when propagators, bridges, sampling, and exporters are configured consistently.

Tracing is an **investigation tool**, not a delivery or business consistency guarantee. Keep event IDs, offsets, retry metadata, and idempotency separate; guard sensitive data in headers; and preserve propagation across async threads and retries/DLTs. Done right, traces pinpoint root causes quickly without obscuring the true state of Kafka records and consumer groups.
