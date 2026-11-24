# Sampling for high-volume traffic

A Spring Kafka application can process thousands to hundreds of thousands of messages per second. Generating and exporting full distributed traces for every record, every Kafka send, every receive, every database query, and every HTTP call can overwhelm the observability stack with an enormous volume of spans. Storage costs climb, collectors or exporters saturate, and telemetry itself becomes a source of pressure on business services.

**Sampling for high-volume traffic** is the policy of selecting a subset of traces to record, transmit, or store while preserving incident investigation capability. In Spring Kafka Reliability Operations, sampling must sit in the context of **Micrometer Observation, distributed tracing, Kafka header propagation, retries/DLTs, and operational signals that must never be lost**.

The most important principle: **reducing stored traces must never reduce the accuracy of core operational metrics**. Consumer lag, processed record counts, error counts, DLT rates, latency, and rebalance health must be monitored independently—never derived solely by counting sampled traces.

## 1. Why do Kafka workloads need a sampling policy?

Consider a typical pipeline:

```text
HTTP request / batch job
          |
          v
Spring service + KafkaTemplate.send()
          |
          v
Kafka topic orders
          |
          v
Spring @KafkaListener
          |
          +--> PostgreSQL
          +--> Inventory HTTP API
          +--> KafkaTemplate.send("orders-result")
          |
          v
Downstream listeners
```

A single order event can emit many spans: an HTTP server span, a Kafka send span, a listener processing span, DB/HTTP client spans, and downstream Kafka publish spans. One record **does not equal one span**; an event can also be reprocessed across retries, rebalances, restarts, or DLT replays.

If a pipeline ingests 5,000 events/second, each averaging four spans, and every span is exported, baseline emission is 20,000 spans/second—roughly **1.728 billion spans per day**, before errors or retries. A policy keeping 1% of traces can cut stored span volume sharply, though actual reduction depends on where sampling happens, trace size, and whether sampling decisions inherit across services.

Never pick a sampling rate by gut feel. Start from throughput, average spans per trace, cost/size per span, retention period, business-flow criticality, and rare-failure investigation requirements.

## 2. Distinguishing Observation, span, trace, and metrics

**Micrometer Observation** is an abstraction for measuring an operation and notifying observation handlers. Depending on configuration, the same observation can contribute to both metrics and tracing:

| Component | Responsibility | Relationship to sampling |
|---|---|---|
| Observation | Represents an observed operation, e.g., listener processing a record | Can still be created and measured even when traces are not exported |
| Span | Unit of work within a distributed trace | Recorded or skipped per tracing sampler |
| Trace | Set of spans linked by trace context | Usually the logical unit for sampling decisions |
| Micrometer timer/counter | Measures counts, durations, processing outcomes | Should not degrade due to trace sampling |
| Kafka client/broker metrics | Measures fetch, poll, lag, rebalances, bytes, requests | Separate monitoring source, independent of trace sampling |
| Logs / audits | Explains events and business state | Separate filtering/retention policies; dropping a trace does not drop all logs |

A `@KafkaListener` processing 100,000 records successfully must still be reflected by matching metrics and committed offsets, even if sampling keeps traces for roughly 1,000 records. If dashboards treat total trace count as total record count, figures skew because one trace can span multiple records or one event can have multiple processing attempts.

**Trace sampling is different from metric tag cardinality.** Dropping tracing from 100% to 1% will not fix attaching `orderId` or `eventId` to metric tags. Both costs require independent policies.

## 3. Main sampling strategies

| Strategy | Decision point | Strengths | Tradeoffs |
|---|---|---|---|
| Head-based probabilistic | When a trace starts or root span is created | Cuts overhead early; saves CPU/network/exporter | Can miss rare errors occurring later |
| Parent-based | When a child span receives upstream trace context | Keeps sampling decisions consistent per trace | Depends on propagation and upstream policy |
| Rules-based / priority | Based on attributes or workload kind known at decision time | Retains more of critical flows | Risk of bias; high-cardinality and complex rules |
| Tail-based | Once the collector receives enough or waits for part of a trace | Can prioritize errors, high latency, DLT paths | Collector must receive and buffer many spans before deciding |
| Adaptive / rate-limited | Adjusts by load, budget, or throughput | Caps costs under traffic spikes | Harder to interpret representative ratios; requires clear metrics/audits |

Large systems often combine layers: a sensible head-sampling rate to limit SDK load, service policies at the collector, and backend storage caps. Yet once a head sampler **drops a trace**, a tail sampler at the collector **cannot recover spans that were never exported**. In particular, never advertise "100% error retention" at the collector when the SDK dropped most failing traces before seeing the final outcome.

## 4. How does head-based probabilistic sampling work?

With sampling probability `p = 0.01`, roughly 1% of **new traces** are chosen to record/export. The decision is normally computed when a trace begins—often derived from trace ID or an SDK sampler algorithm to avoid re-rolling on every span.

```text
100,000 Kafka records
       |
       v
Tracing SDK applies ~1% sampling probability
       |
       +--> most traces are not exported
       |
       +--> selected traces
                    |
                    v
             producer / consumer / DB / HTTP spans
                    |
                    v
              Collector + trace backend
```

This is a conceptual diagram: the count of sampled records **is not always exactly 1% of records** because one trace may span multiple records, trace lengths vary, and upstream services may decide sampling before the consumer. Random sampling is a statistical approximation; in short windows, observed ratios fluctuate around 1%.

Its strength is shedding telemetry load early. Its drawback is that at trace start, the system does not yet know whether the record will fail, breach latency SLOs, or route to a DLT.

## 5. Parent-based sampling and asynchronous Kafka context

In distributed tracing, spans usually inherit **trace context** from upstream operations. Over HTTP, context travels in headers. Over Kafka, frameworks/bridges carry context in **record headers** when producer and consumer Observation/tracing are properly configured.

```text
Service A: HTTP POST /orders
   traceId = T1, sampled = true
        |
        v
KafkaTemplate sends orders (tracing headers)
        |
        v
Kafka broker stores record + headers
        |
        v
Service B: @KafkaListener receives record
   reads upstream trace context
   applies parent-based sampling
        |
        v
Service C / database spans can share trace T1
```

When parent context propagates properly and the sampler uses a parent-based policy, child spans honor the upstream decision. A trace selected upstream has a chance to remain continuous across producer, Kafka consumer, and downstream calls. A trace marked unsampled will not normally "turn itself back on" at each service.

With Kafka, exercise caution: a record may be processed long after the producer span ended, retried on another topic, and a batch listener can hold **many records with many trace contexts**. Verify how Spring Kafka creates/continues observations and parent/span links for your exact version and instrumentation. Never assume an entire batch belongs to one trace.

If a service fails to inject or extract tracing headers, the consumer may start a new root trace and make a fresh sampling decision. That leaves cross-service traces fragmented even when every service reports "tracing enabled."

## 6. Enabling Observation for Spring Kafka listeners

In Spring Kafka with Micrometer Observation, enable it via `ContainerProperties` on the right listener container factory:

```java
@Configuration
public class OrdersKafkaObservabilityConfig {

    @Bean("ordersKafkaListenerContainerFactory")
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties().setObservationEnabled(true);

        return factory;
    }
}
```

Listener using that factory:

```java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "order-service",
        containerFactory = "ordersKafkaListenerContainerFactory")
public void onOrder(OrderEvent event) {
    orderService.processIdempotently(event);
}
```

`OrderEvent` and `orderService` are illustrative components. `ConsumerFactory` needs matching deserializers, broker properties, and security settings. Setting `observationEnabled=true` activates Observation on supported container versions; **it does not set a sampling rate** or supply an exporter/collector by itself.

If the application has multiple container factories, enable Observation on **the exact factory the listener uses**. Enabling it on another bean adds no tracing to the running listener. For batch listeners, verify Observation behavior for your exact Spring Kafka version; do not assume an independent span per record in a batch.

## 7. Enabling Observation for Kafka producers

For tracing context to travel from producer across Kafka to consumer, the sending side needs matching instrumentation. `KafkaTemplate` supports Observation in Spring Kafka versions with this feature:

```java
@Bean
KafkaTemplate<String, OrderEvent> observedKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory) {

    KafkaTemplate<String, OrderEvent> template =
            new KafkaTemplate<>(producerFactory);

    template.setObservationEnabled(true);
    return template;
}
```

With an `ObservationRegistry`, tracing handlers, and a matching propagator, Spring Kafka creates producer observations and injects trace context into Kafka record headers. Actual transmission depends on Micrometer Tracing/OpenTelemetry/Brave libraries, propagation config, and framework version.

Never blindly copy all Kafka headers without understanding data provenance. When replaying from a DLT or transforming records, decide policies for retaining trace context, business correlation IDs, and provenance. A `traceparent` header or another propagation format **is not a business idempotency key**; it only correlates telemetry.

If the pipeline uses Kafka transactions, a producer span recording `send()` success does not prove the transaction committed. Pair telemetry with transaction outcomes and `read_committed` consumers whenever business processing must observe only committed data.

## 8. Configuring sampling probability in Spring Boot

On Spring Boot versions supporting Micrometer Tracing and this sampling property, configure a global sampling ratio:

```yaml
management:
  tracing:
    sampling:
      probability: 0.01
```

A value of `0.01` corresponds to **roughly 1% of new trace roots**, not 1% of Kafka partitions or 1% of committed records. Some environments use the equivalent `.properties` syntax:

```properties
management.tracing.sampling.probability=0.01
```

This setting requires a matching tracing stack for your Spring Boot version: Micrometer Observation/Tracing, a bridge to Brave or OpenTelemetry, and a configured backend exporter. **Do not confuse this property with `management.metrics.*`**, as metrics and traces are separate telemetry channels.

`management.tracing.sampling.probability` primarily controls sampling at the Boot-configured tracing layer. If you provide a custom tracer, sampler, OpenTelemetry SDK, or separate Java agent, that setting may be handled differently or no longer be the sole source of truth. Verify the **effective sampler** at runtime, especially when a Java agent and SDK auto-configuration coexist.

Downstream services receiving a parent context can inherit upstream decisions. Setting `0.01` on service B does not mean service B always drops 99% of traces if many parents were already sampled by service A at a higher rate.

## 9. Example OpenTelemetry SDK sampler configuration

When an application configures the OpenTelemetry SDK directly rather than relying solely on Spring Boot auto-configuration, a common strategy is **parent-based trace ID ratio sampling**:

```java
import io.opentelemetry.sdk.trace.samplers.Sampler;

Sampler sampler = Sampler.parentBased(
        Sampler.traceIdRatioBased(0.01));
```

Meaning: if a span has a parent context, the sampler honors the parent's decision; if it is a new root, sample at roughly 1%. This snippet **builds a sampler object**—it is not a bean that automatically wires into Spring Kafka simply by pasting it into any class. To take effect, the sampler must be attached to the exact `SdkTracerProvider`/SDK used by the application and instrumentation.

An SDK configuration that overrides auto-configuration can affect exporters, propagation, resource attributes, shutdown, and the OpenTelemetry bridge. In production, prefer one consistent tracing configuration source to prevent Spring Boot and a Java agent from creating duplicate SDKs or exporters.

Avoid tying a sampler to business IDs without evaluating privacy and stability. Uniform sampling over trace IDs is usually much better than hashing `customerId` and permanently tracing one group of customers while never observing another.

## 10. Calculating sampling budgets from real throughput

A rough estimate starts with:

```text
exported spans/sec ≈ new trace roots/sec
                     × sampling probability
                     × avg spans / sampled trace

exported spans/day ≈ exported spans/sec × 86,400
```

Illustrative example: assume an application starts around 5,000 new trace roots/second, averaging 4 spans per trace:

| Sampling probability | Expected sampled trace roots/sec | Estimated spans/sec | Estimated spans/day |
|---:|---:|---:|---:|
| 100% | 5,000 | 20,000 | 1,728,000,000 |
| 10% | 500 | 2,000 | 172,800,000 |
| 1% | 50 | 200 | 17,280,000 |
| 0.1% | 5 | 20 | 1,728,000 |

These are hypothetical capacity figures, not measurements from a real cluster. Kafka records may not map 1:1 to trace roots, spans/trace vary with fan-out and errors, and parent-inherited traces may be selected upstream. Accurate budgeting requires measuring **actual exported spans per second**, span byte sizes, and backend retention.

Even 1% still yields **17.28 million spans/day** under those assumptions. Thus "only 1%" is not necessarily cheap at high scale. Conversely, dropping to 0.1% can make rare-error investigation difficult. Pick policies based on SLOs, cost, and diagnosability.

## 11. Never use trace sampling to count real errors

Suppose a system processes 1,000,000 records, 100 of which hit business errors. At 1% random sampling, the **expected** number of retained error traces is around one; it is entirely possible to see zero error traces even though failures genuinely occurred.

```text
1,000,000 records
     |
     +--> 999,900 succeeded
     |
     +--> 100 failed

1% trace sampling:
  retained error traces might be 0, 1, 2, ...
```

Therefore, **error rates, retry counts, DLT publish success/failure, consumer lag, and latency SLOs must rely on full-coverage metrics**. Traces provide root-cause detail for a **sample** of transactions, not an exact accounting system for record counts.

Useful counters include:

- `app.kafka.records.processed` by pipeline, outcome, and bounded reason.
- `app.kafka.retry.attempts` by listener/error category.
- `app.kafka.dlt.published` and `app.kafka.dlt.publish_failed`.
- Kafka consumer group lag, rebalance counts, and poll/commit errors.
- Listener processing duration histograms for per-pipeline p95/p99.

Never place `record.key`, Kafka offset, request ID, exception messages, or JSON payloads into metric tags. A low trace sampling rate **does not reduce** metric cardinality tagged per message.

## 12. Prioritizing errors and high latency: limits of head sampling

An error-based sampling rule sounds tempting: "keep all failing traces, drop most successful traces." However, at **head sampling** time, the listener has not finished running and the outcome is unknown. A head sampler cannot predict the future based on an exception thrown seconds later.

You can raise sampling on flows **known upfront to be critical**, such as payment services, settlement workflows, or recovery topics. Yet SDK-level business sampling requires attributes to be visible **before** the sampling decision and disciplined rule management. With Kafka, topic names or headers may be visible at the consumer boundary, whereas a root trace may already have been decided at the upstream producer, leaving the consumer unable to override it.

When the goal is keeping traces on **`status=ERROR`** or **high latency**, tail-based sampling at the collector fits functionally better. The tradeoff is that all candidate span data must reach the tail-sampling decision point; you cannot achieve 100% error capture if upstream head sampling already dropped most traces.

## 13. Tail-based sampling at the OpenTelemetry Collector

**Tail sampling** defers the decision until the collector has gathered spans for a trace over a waiting window. It can retain traces matching conditions such as error spans, high latency, or a baseline random percentage.

```text
Spring Kafka services (exporting full spans)
                 |
                 v
       OpenTelemetry Collector
                 |
          group by trace ID
                 |
        buffer/inspect trace
                 |
        +--------+---------+
        |                  |
     ERROR trace       normal trace
        |                  |
      retain        retain small % (e.g., 2%)
                 |
                 v
              Trace backend
```

An **illustrative** configuration snippet for the `tail_sampling` processor in an OpenTelemetry Collector version supporting it:

```yaml
processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 2048
    spike_limit_mib: 512

  tail_sampling:
    decision_wait: 15s
    num_traces: 50000
    policies:
      - name: keep-errors
        type: status_code
        status_code:
          status_codes: [ERROR]
      - name: baseline
        type: probabilistic
        probabilistic:
          sampling_percentage: 2

  batch: {}
```

This is a **processor excerpt**, not a complete Collector configuration. A working deployment also needs `receivers`, `exporters`, `service.pipelines.traces`, and security/network settings. Processor and policy support must be confirmed for your deployed OpenTelemetry Collector / Collector Contrib release. Parameters `decision_wait` and `num_traces` must be sized to actual trace roots/second, fan-out, memory, and trace duration.

If spans arrive after the tail-sampling decision window, traces can end up fragmented or trigger late-span handling depending on version. With multiple collector replicas, spans sharing the same trace ID must route consistently to the same decision node using trace-ID-aware load balancing; scattering spans across replicas prevents policies from seeing every error signal in the trace.

**Note:** a `status_code=ERROR` rule only matches when instrumentation actually sets span status to `ERROR`. A business error caught and turned into a normal return may not mark `ERROR`. Similarly, successful DLT publishing does not automatically mark the listener span as failed. Align error status semantics in instrumentation before relying on error rules.

## 14. Head vs. tail sampling: choosing by cost

| Requirement | Head-based | Tail-based |
|---|---|---|
| Cut telemetry CPU/network right at the app | Good | No; apps still export spans to the collector |
| Retain traces on final error outcomes | Not guaranteed | Feasible if all relevant spans reach the collector |
| Retain high-latency traces | Limited when latency is unknown upfront | Feasible with suitable policy and decision window |
| Collector memory footprint | Relatively low | Can be high from buffering traces |
| Multi-replica collector operations | Simpler | Requires routing/aggregation by trace ID |
| Cross-service consistency | Requires propagation + parent-based | Requires trace ID and complete spans arriving in time |
| Completeness when upstream dropped traces | Cannot recover dropped traces | Also cannot recover traces that never reached the collector |

A pragmatic architecture uses head-based sampling on normal high-volume paths to save telemetry upfront, while critical paths or dedicated investigation environments export full spans for tail sampling on errors and high latency. Always document **which layer can see which traces**; never claim the system retains every error if an upstream sampler drops data earlier.

## 15. Kafka retries, DLT, and sampling decisions

Spring Kafka may process a record multiple times: inline retries in `DefaultErrorHandler`, forwarding to retry topics via `@RetryableTopic`, and publishing to a Dead Letter Topic (DLT). One business event can undergo multiple deliveries and multiple listener spans.

```text
orders
   |
   v
@KafkaListener (attempt 1) -> error
   |
   v
orders-retry (attempt 2) -> error
   |
   v
orders.DLT
   |
   v
Controlled replay -> orders (another execution)
```

When a record is published to retry/DLT topics, tracing metadata may be copied, updated, or altered depending on the recoverer, serializer/header mapper, and Spring Kafka version. Do not assume context is automatically preserved across every topology. When tracing headers remain intact and Observation is configured properly, attempts may link to the original trace or create new related traces/spans per instrumentation semantics.

Operationally, maintain **two kinds of identifiers**:

- **Trace/correlation identity:** observes an execution path; may change on replay or when context is not propagated.
- **Stable business event ID:** supports idempotency, auditing, and distinguishing original records from retries/replays; never use trace ID as an exactly-once key.

If sampling dropped the original event's trace, only logs and metrics may remain when the event lands in the DLT. Therefore, the DLT must retain original topic/partition/offset, exception class, business event ID, and retry metadata sufficient for investigation **even without a trace**. Tracing is a supplementary diagnostic aid, never the sole source of evidence.

## 16. When a rare error occurs and its trace was sampled out

An incident affecting one in a million records must still be diagnosable via:

1. **Structured logs** containing event ID, topic, partition, offset, listener ID, error category, and correlation ID per security policy.
2. **DLT/quarantine** retaining failed records with provenance and appropriate retention.
3. **Full-coverage metrics** for failure counts, timeouts, retry attempts, and DLT publish outcomes.
4. **Business audits** or inbox/outbox records when side effects are critical.
5. **On-demand diagnostic sampling** or controlled replay environments to reproduce traces at a higher sampling rate when needed.

Never crank sampling to 100% cluster-wide at the first sign of a single error under extreme traffic. A global spike can overload exporters/collectors right in the middle of an incident. Prefer scoped diagnostics by service, approved tenant, or targeted event set with **explicit expiration and rate limits**.

When running controlled replays at 100% sampling, avoid copying sensitive payloads into span attributes. Sampled traces must still respect data minimization and access controls.

## 17. Cardinality: sampling does not fix badly designed tags

A common mistake is adding `order.id` to span/metric attributes and relying on sampling to keep costs down. For spans, high-cardinality attributes bloat event sizes and risk data leaks; for metrics, `orderId` creates a time series per order **even when that record's trace is never sampled**.

| Data | Metric tags | Trace attributes / log fields |
|---|---|---|
| Service, environment, pipeline | Suitable if bounded | Suitable |
| Topic and listener ID | Conditional on cardinality | Suitable in Kafka context |
| Partition | Weigh partition count × labels | Useful for investigation |
| Retry attempt | Can normalize into small buckets | Useful on sampled traces |
| Event ID, order ID | Should not | Only when needed, with masking/access/retention |
| Kafka offset | Should not | Can record in logs/traces when debugging |
| Payload, token, PII in exception message | Should not | Avoid or redact; requires security review |

Micrometer distinguishes **low-cardinality key values** typically used for metrics from **high-cardinality key values** intended for tracing in Observation conventions. Using high-cardinality keys in traces does not automatically make data safe; still enforce limits on count, size, and sensitive content.

## 18. How does sampling affect latency analysis?

Random uniform sampling by trace ID lets sampled traces reveal request shapes and dependency chains. Still, never rely solely on sampled traces to compute accurate p95/p99 latency SLOs across all traffic—especially when sampling rates are low or policies bias toward errors/slow traces.

For example, suppose tail sampling keeps 100% of traces over 5 seconds and only 2% of normal traces. The average latency of **stored traces** will look much higher than the true traffic average because selection was biased. Computing latency SLOs from that biased sample without proper weighting produces skewed dashboards.

For SLO monitoring, use Micrometer timers and cardinality-bounded histograms to compute threshold breaches and percentiles in the metrics backend. Use traces to investigate **why** tail-latency records were slow, not as a replacement for accurate metric baselines.

When sampling rates change over time, a rise or drop in stored error trace counts does not automatically mean the real error rate changed. Trace-volume dashboards should display the active sampling config and effective sample rate to prevent misinterpretation.

## 19. Observability pipeline load: exporters, queues, and collectors

Even after sampling reduces emitted data, the telemetry pipeline still has resource limits to manage:

```text
Spring Kafka Observation/Tracing
          |
          v
Tracing SDK sampling + span processor
          |
          v
Exporter queue / batch
          |
          v
OTLP / Collector
          |
          v
Batch / tail sampling / routing
          |
          v
Trace backend
```

Monitor `spans created`, `spans sampled`, `spans exported`, dropped spans, queue sizes, exporter failures, collector memory, and backend ingestion throttling. A trace selected by the sampler yet dropped by a full exporter queue is still invisible in the backend.

With tail sampling, collectors hold trace data in memory until decisions fire. A 10× traffic spike during peak load expands memory footprints and can cause evictions or drops. Size `decision_wait`, `num_traces`, tail policies, and collector replicas for peak traffic—not just average throughput.

Trace drops in exporters/collectors must never cause lost Kafka records or corrupted offset commits. Avoid synchronous exporters that block consumer threads indefinitely; configure timeouts, bounded queues, graceful degradation, and telemetry overhead controls per your library. During observability backend outages, business services must continue running and core metrics/alerts should have resilient paths.

## 20. Monitoring the effective sampling rate

A configured sampling probability of 1% does not prove the backend actually receives 1% of **complete traces**. Parent-based decisions, lost context, collector drops, exporter failures, traffic skew, or tail policies can shift the real ratio.

Signals to watch:

| Signal | Question to answer |
|---|---|
| Incoming Kafka record rate | How many records were actually received? |
| Observation invocation count | How many operations were instrumented? |
| Tracing sampled spans/traces | How much data is the SDK selecting? |
| Exporter queue / dropped spans | Are selected spans failing to leave the process? |
| Collector received/exported spans | Is the collector dropping spans due to memory, policy, or network? |
| Backend ingested traces | Does actual stored trace volume fit budget? |
| Trace completeness | Are producer/consumer/downstream spans breaking context? |
| Sampling policy version | When did the rate change and who changed it? |

Treat sampling policies as versioned operational configurations with changelogs. Dropping from 10% to 1% is expected to cut trace counts; error rates and business throughput **must not** drop proportionally.

Tail-based rules that keep nearly all error traces can cause ingestion spikes during outages when error rates jump from 0.1% to 50% even at constant traffic. Put rate budgets on error-retention rules or define graceful degradation rules in advance.

## 21. Multi-replica scenarios and cross-service consistency

A pipeline may run 20 producer pods, 30 consumer pods, and several downstream services. If each pod starts a new root trace with independent random sampling whenever context is lost, the backend fills with disconnected trace fragments. To preserve correlation:

1. Use one standardized propagation format, such as W3C Trace Context where supported.
2. Enable Observation/tracing on both producer and consumer on the right factories/templates.
3. Align parent-based sampling or equivalent policies across participating services.
4. Preserve tracing headers across message converters, Kafka bridges, retries/DLTs, and replays.
5. Maintain a stable business correlation ID outside tracing to tie events together when traces are sampled out or replayed.

On multi-replica collectors running tail sampling, spans with the same trace ID must route to the same decision instance via a trace-ID-aware load-balancing layer. Simply scaling collector replicas without trace affinity causes each replica to see only partial traces.

Never confuse `consumer group.id` with `trace ID`. A consumer group governs Kafka partition assignment and committed offsets, whereas a trace ID links observed operations. A record redelivered after a rebalance can create a new processing span while keeping its business ID; never use trace ID to deduplicate financial operations.

## 22. End-to-end sampling testing for Spring Kafka

To verify configuration, use a real test Kafka broker or Testcontainers alongside an OpenTelemetry/Micrometer test exporter. Do not merely check that a property exists in YAML; confirm traces and metrics land in the right places.

Key test scenarios:

1. **Listener and producer Observation:** both `KafkaTemplate` and containers emit telemetry when enabled with tracing configured.
2. **100% head sampling in tests:** send an event and verify trace context crosses Kafka headers and producer/consumer spans link per your version's instrumentation.
3. **0% head sampling in tests:** no sampled trace is exported, while listener metrics and business outcomes still record normally.
4. **1% sampling over large event batches:** verify statistical ratios over trace roots rather than asserting every 100 records produces exactly one trace.
5. **Parent sampled/unsampled:** verify downstream honors upstream decisions or clearly verify where new root traces begin.
6. **Retry/DLT:** verify failures recover and DLT metadata remains complete even when traces are unsampled; verify propagation across retry topics for your actual config.
7. **Exporter outage:** observe telemetry drops without causing listeners to lose records or commit wrong offsets.
8. **Error tail sampling:** when SDKs export full spans to the collector, verify error traces are kept if span statuses/attributes match rules.
9. **Multi-replica collectors:** verify trace routing and completeness so producer spans on replica A and consumer spans on replica B do not evaluate independently.
10. **PII/cardinality:** verify trace/span attributes contain no sensitive payloads, and metrics contain no `eventId`/`orderId` tags.
11. **Batch listeners:** verify how the framework creates batch/record observations without assuming a batch shares one trace context.
12. **Runtime/deploy policy changes:** verify dashboards mark policy change timestamps and never misread trace volume as real message volume.

Never write tests expecting "exactly one sampled trace" at 1% over 100 events; randomness makes such tests flaky. For propagation tests, use a 100% sampler to assert trace structure; for probabilistic tests, use large sample sizes with sensible statistical tolerances.

## 23. Troubleshooting sampling and tracing

| Symptom | Likely cause | Remediation |
|---|---|---|
| Metrics exist, no traces appear | Low/0% sampling, exporter/collector fault, or Observation/tracing bridge not enabled | Check effective sampler, instrumentation, export queues, and backend |
| Consumer has span, not linked to producer | Kafka tracing headers not propagated/extracted or mismatched SDK formats | Verify producer/consumer Observation, propagators, and message headers |
| Rare error trace missing | Head sampling dropped trace before outcome was known | Use metrics/logs/DLT; consider tail sampling where warranted |
| Backend overloaded despite 1% sampling | Very high traffic, many spans/trace, retry storms, or tail rules retaining errors | Measure actual spans/s, exporter queues, and collector capacity |
| Tail sampling keeps only the tail of traces | Late-arriving spans or trace spans split across collector replicas | Tune `decision_wait` and trace-ID-aware routing |
| `status_code=ERROR` misses business errors | Span status not marked `ERROR` by instrumentation | Align error handling and observation conventions |
| Trace volume drops after deploy while system stays healthy | Sampling probability changed | Check changelog and verify full-coverage business metrics |
| Two separate tracing pipelines active | Java agent and manual SDK running side by side | Standardize on one instrumentation/exporter source and check for duplicates |
| Looking up a DLT record with no trace | Record unsampled, context lost, or exporter dropped it | Look up DLT provenance, business event ID, and structured logs |
| Prometheus series count grows unboundedly | High-cardinality metric tags, unrelated to tracing sampler | Standardize tags and remove `eventId`/`orderId` from metric labels |

When diagnosing, walk from **business processing/metrics**, through **Observation and SDK samplers**, to **exporter/Collector**, and finally to the **trace backend**. Each tier drops data differently. Never blame `sampling.probability` when spans were actually sampled yet dropped by the exporter.

## 24. Runbook when sampling must be increased during an incident

A practical operations strategy never keeps 100% tracing system-wide long-term, yet can temporarily boost visibility within a narrow scope:

1. **Define the target:** which topic, consumer group, listener, service, or workflow is failing; are you investigating latency, exceptions, or data inconsistency?
2. **Verify baseline signals:** confirm the incident via Kafka lag, DLT, retries, non-responsive consumer events, error rates, and downstream latency.
3. **Check current budget:** inspect spans/s, collector memory, exporter drops, ingest throttling, and remaining retention.
4. **Pick a tight scope:** only the affected service/pipeline or an approved replay workflow—never knee-jerk 100% across the entire cluster.
5. **Choose sampling mode:** raise head rate if you need more ordinary traces; use tail sampling when prioritizing errors/slow traces and collector capacity allows.
6. **Verify propagation:** check Kafka headers, parent-based sampling, retries/DLT, and trace affinity across collectors.
7. **Enforce time and rate limits:** set an expiration, rate budget, and clear owner responsible for rolling back the sampling policy.
8. **Watch overhead:** monitor exporter drops, collector queues, app CPU/heap, Kafka listener latency, and tracing backend lag.
9. **Collect evidence:** record trace links, business event IDs, and DLT provenance under proper access controls; never put sensitive payloads into spans.
10. **Revert:** restore baseline sampling after the incident and document findings and investigation limits.

If the sampler does not support dynamic reloads, changing policy may require a rolling deployment; weigh the impact of Kafka consumer group rebalances. During rollout, pods with differing sampling policies can coexist; note version/config timestamps when interpreting transition metrics.

## 25. Production principles

1. **Sampling selects tracing telemetry**; it never alters Spring Kafka delivery semantics, offset commits, or idempotency.
2. Budget from trace roots/s, spans/trace, span size, retention, and peak load; 1% can still emit millions of spans/day.
3. Prefer parent-based sampling and consistent propagation via Kafka record headers to preserve producer/consumer links.
4. Head sampling sheds overhead early yet can miss rare errors; tail sampling retains errors/slow traces better when collectors receive complete spans.
5. **Tail sampling cannot recover spans dropped by the SDK**; never promise 100% error capture if upstream head sampling discards traces.
6. Enable Observation on the right listener container factory and `KafkaTemplate`; verify the tracing bridge/exporter before interpreting results.
7. Metrics for throughput, error rates, consumer lag, retries, and DLT must maintain full coverage independent of trace sampling.
8. Never use trace ID as a business idempotency key; keep stable event IDs for retries, replays, and audits.
9. Bound metric tag cardinality, redact PII in spans/logs, and never export raw payloads just because a trace was sampled.
10. Monitor SDK/exporter/collector drops, tail memory, trace completeness, and effective backend sampling rates.
11. Test head/parent/tail semantics, Kafka header propagation, batch listeners, retries/DLT, and collector outages before rollout.
12. Maintain a clear procedure for temporary, scoped, budgeted, time-boxed sampling increases during production investigations.

**Conclusion:** High-volume sampling enables Spring Kafka systems to keep the value of distributed tracing without turning observability into a bottleneck. A durable strategy combines **full-coverage metrics**, **intentionally sampled traces**, **consistent context propagation**, and **DLTs/audits with provenance**. Understanding the difference between head and tail sampling—alongside each telemetry tier's limits—lets operations control costs while retaining enough evidence to investigate rare errors, high latency, and retry/recovery incidents.
