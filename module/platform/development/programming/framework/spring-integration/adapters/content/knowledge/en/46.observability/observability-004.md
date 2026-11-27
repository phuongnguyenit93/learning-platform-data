# Metrics for Adapters and Channels in Spring Integration

## 1. Why Measure Metrics at Adapters and MessageChannels?

A Spring Integration application may ingest data from **files/SFTP**, **HTTP**, **JMS**, **AMQP**, **Kafka**, or **databases**, then pass it through **MessageChannel**s, filters, routers, transformers, and handlers toward a destination system. A flow can be functionally correct in code yet still cause operational incidents: a poller stops picking up files, a queue fills up, a consumer falls behind on lag, outbound HTTP times out, a broker redelivers, a database commit slows down, or a connector keeps retrying the same record.

**Metrics** turn those phenomena into quantitative signals trackable over time: **throughput, latency, error rate, backlog level, retry outcomes, and connectivity**. In the **Observability** chapter of the **SPRING_INTEGRATION_ADAPTERS** module, the goal is to observe integration flows across inbound/outbound adapters, gateways, pollers, and MessageChannels while controlling **message contracts, errors, and connection lifecycles**.

For example, a dashboard showing only “sent 2,000 messages” cannot answer:

- How many messages were **successfully processed** versus filtered/rejected?
- Does the send count represent **attempts** or unique business events?
- Are records **waiting** in a QueueChannel or broker?
- Did an HTTP outbound gateway receive **2xx from the remote service**, or did it merely send to the channel?
- Is latency measured **from file appearance to confirmed completion**, or only inside a single handler?
- If a Kafka consumer fails and retries, how many times did the counter increment?

### Learning Goals

After this lesson, you can:

1. Distinguish metrics for **channels, endpoints/handlers, adapters, pollers**, and external systems.
2. Use **Micrometer**, Spring Boot Actuator, and Spring Integration's management/observation capabilities appropriately for your library version.
3. Name endpoints/metrics and choose **low-cardinality tags**, avoiding message IDs or filenames as labels.
4. Design **SLIs/SLOs** measuring successful message processing, latency, and backlog rather than just CPU or HTTP 200.
5. Build dashboards, alerts, and runbooks for File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC/databases.
6. Test metrics, diagnose missing or misleading metrics, and combine metrics with logs, traces, and message history.

> **Limitation:** Meter names, tags, and built-in Spring Integration instrumentation options vary by version and management/observation configuration. Application metrics in this lesson prefixed with `app.integration.*` are **illustrative conventions we explicitly create**, not a guarantee that Spring Integration exports them automatically.

## 2. Where Do Metrics Fit in the Observability Triad?

| Signal Type | Answers | Examples in Integration Flows |
|---|---|---|
| **Metrics** | How many? How long? How frequent are errors? | Messages/s, p95 handler latency, queue depth, redelivery rate |
| **Structured logs** | Which specific event occurred? | `event=HTTP_TIMEOUT`, `correlation_ref=...`, status code, target |
| **Distributed traces** | Which services did a request/message cross and how long did each span take? | HTTP → IntegrationFlow → Kafka producer → consumer service |
| **Message history** | Which Spring Integration components did a message traverse when history is enabled? | Transformer, router, service activator, adapter |
| **Audit/business events** | Which business action or state change did the system actually accept? | Order accepted/paid, file processed, transaction committed |

Metrics reveal **patterns over time**, not necessarily where an individual message failed. Therefore combine:

- **Counters/gauges/timers** for early incident detection.
- **Correlation IDs and trace context** to locate affected messages/transactions.
- **MessageHistory** to inspect the path within a process, if history is enabled.
- **Source/target audits and broker metadata** to verify real effects in external systems.

An unusual p99 histogram spike tells you the flow is slow, but does not prove whether the cause is SFTP, CPU, the broker, or the database. Drill down using the other signals.

## 3. Measurement Architecture Across Adapter–Channel Flows

~~~mermaid
flowchart LR
    SRC[File / SFTP / HTTP / JMS / AMQP / Kafka / DB] --> IN[Inbound Adapter or Gateway]
    IN --> CH1[Input MessageChannel]
    CH1 --> PROC[Filter / Router / Transformer / Handler]
    PROC --> CH2[Output MessageChannel]
    CH2 --> OUT[Outbound Adapter or Gateway]
    OUT --> DST[Remote System]
    IN -. polling / input metrics .-> REG[Micrometer MeterRegistry]
    CH1 -. channel metrics .-> REG
    PROC -. handler metrics .-> REG
    CH2 -. send / queue metrics .-> REG
    OUT -. outbound attempts .-> REG
    SRC -. source / broker telemetry .-> REG
    DST -. acknowledgement / outcome .-> REG
    REG --> EXP[Actuator / Metrics Exporter]
    EXP --> OBS[Prometheus / Monitoring Backend]
    OBS --> DASH[Dashboard / Alert / On-call]
~~~

The diagram illustrates **measurement sources**; it does not mean Spring Integration automatically collects every metric from brokers or remote services. Telemetry for Kafka, RabbitMQ, JMS providers, databases, SFTP servers, and HTTP targets typically requires **dedicated instrumentation/client metrics or exporters**.

### 3.1. Four Boundaries to Distinguish

1. **Inbound acceptance:** did the adapter fetch or receive the message into the application?
2. **Channel delivery:** did the channel accept dispatching/enqueuing the message downstream?
3. **Processing outcome:** did the handler process it according to the business contract?
4. **External confirmation:** did the target system ack/commit/write the file/return a successful HTTP response?

Collapsing all four measurement points into a single `success` counter makes dashboards look green even when messages are lost after a gateway timeout or unconfirmed broker publish.

## 4. Metrics Vocabulary: Counter, Timer, Gauge, Distribution

| Meter Type | Suited For | Points to Watch |
|---|---|---|
| **Counter** | Received messages, attempts, retries, rejections/errors | Monotonically increasing cumulative value; compute rate over a time window to see speed |
| **Timer** | Handler duration, HTTP call, DB processing, or full flow | Must clearly define **start/end**; typically provides count and total time, plus histogram if configured |
| **Gauge** | Queue depth, in-flight requests, active connections, oldest backlog age | Point-in-time sampled value; a gauge is not a history of every change |
| **Distribution summary** | File size, message bytes, batch size | Does not replace timers; distribution and buckets require proper configuration |
| **Long task timer** | Long-running tasks needing observation before completion | Consider for long-lived polling/transfers/jobs |

### 4.1. A “Success” Name Must Have a Contract

Example definitions:

- `received_total`: inbound adapter creates a Spring Message from the source.
- `accepted_total`: message passes validation/filters and is accepted by handlers.
- `delivery_attempt_total`: number of outbound calls (including retries).
- `delivery_confirmed_total`: target confirmed according to its protocol semantics.
- `failed_total`: terminal failure after retry policy and routing to DLQ/failed state.
- `inflight`: number of messages currently in flight at a defined boundary.

**Never equate** a send attempt with a unique business event: the same message may be sent multiple times after timeouts or redeliveries.

### 4.2. Units and Timestamps

Timers in Micrometer are unit-converted when exported by backends; with Prometheus, names are normalized and durations are commonly exported in seconds. When building panels, keep **ms/s** consistent. Never compare a gauge in milliseconds directly against a histogram in seconds to infer p95.

## 5. MessageChannel Metrics: Same Name, Different Semantics

### 5.1. DirectChannel

`DirectChannel` typically dispatches synchronously on the sender thread to a subscriber. `send` execution duration may include downstream processing depending on channel/handler type and instrumentation. Therefore, **never label a DirectChannel send timer as “network latency.”**

What to observe:

- Send attempts and failures.
- Dispatch/send duration per actual meter definition.
- Separate handler latency at resource-intensive endpoints.
- Exceptions/rejections, including missing subscribers.

### 5.2. ExecutorChannel

`ExecutorChannel` delegates dispatch to an executor. A send can return very quickly while the task **waits in the executor queue** long before the handler executes. Therefore:

- Low channel send latency **does not guarantee** fast end-to-end processing.
- Monitor executor queue size, active threads, task rejection count, and task wait time.
- Count in-flight items at the right boundary; if an async handler fails, never count a successful channel send as business success.
- Test tracing context and MDC propagation across thread switches.

### 5.3. QueueChannel

`QueueChannel` buffers messages for a consumer/poller to fetch later; key metrics include:

| Metric | Meaning |
|---|---|
| **Queue depth** | Number of messages remaining in the queue at sample time |
| **Oldest age** | How long the oldest message has waited |
| **Enqueue rate** | Rate of messages placed into the queue |
| **Dequeue/consumption rate** | Rate of messages taken for further processing |
| **Capacity usage** | Utilization relative to configured capacity |
| **Rejected/blocked sends** | Send timeouts/capacity exhausted depending on channel config |

Queue depth **can be 0** when consumers pull fast while remote outbound is slow, or very large when downstream is backed up. To diagnose the cause, compare ingress, egress, in-flight counts, and errors.

### 5.4. PublishSubscribeChannel

One message can fan out to multiple subscribers; channel send count typically differs from total per-subscriber deliveries. If one subscriber fails while another succeeds, track **per-branch outcomes** and error-handling policies. Never conclude a business event completed all branches merely because the channel accepted the send.

### 5.5. Comparison Table

| Channel | Signals to Prioritize | What Must Not Be Inferred |
|---|---|---|
| Direct | Dispatch/send count, latency, handler timer | Remote network ACK |
| Executor | Executor wait/queue, handler timer, task rejections | Accepted send = handler executed |
| Queue | Depth, oldest age, enqueue/dequeue, capacity | Depth 0 = business completed |
| Publish-subscribe | Per-subscriber outcomes, fan-out failures | One send = all subscribers succeeded |

## 6. Endpoint and Message Handler Metrics

Endpoints/handlers execute actions like validation, transformation, routing, database persistence, or HTTP calls. Key signals:

1. **Handler invocation/attempt count:** how many processing executions started.
2. **Processing duration:** execution time of logic inside the handler.
3. **Success/failure count:** policy-defined outcomes; distinguish retried exceptions from terminal errors.
4. **Discard/reject count:** why filters dropped messages and whether they went to a discard channel.
5. **Payload/batch size:** byte size or item count processed.
6. **Concurrency/in-flight:** how many handler executions are concurrently active.
7. **Timeout/retry:** timed-out tasks, network retries, or target rejections.

### 6.1. Handler Time Differs from Flow Time

If a message waits in a `QueueChannel` for 30 seconds and the handler runs in 20 ms, the handler timer dashboard looks great while users still experience **30 seconds of latency**. Define an end-to-end SLI measured from **accepted/received** to **completed/confirmed** per contract.

### 6.2. Filters, Routers, and Aggregators

- **Filter:** `accepted` and `rejected` counters plus bounded `reason_code` groups; never log raw payloads.
- **Router:** counters for bounded destination groups, unmapped branches, and router errors.
- **Splitter:** input batch count, output item count, batch size distribution, item failures.
- **Aggregator:** group count, outstanding groups, completion latency, timeouts/expiries, group store capacity.
- **Resequencer:** waiting group count, ordering completion delay, timed-out messages.

**Cardinality warning:** never use `correlationId` or `batchId` as a metric tag for an aggregator; those are nearly unbounded labels. Keep specific IDs in logs/traces and group metrics by flow, handler, and result.

## 7. Poller and Inbound Channel Adapter Metrics

A poller can **run successfully yet find no data**. If you only count messages, you cannot tell whether there is “nothing to do” or the scheduler stopped.

### 7.1. Four Poll States to Separate

| State | Meaning | Appropriate Observation |
|---|---|---|
| **Poll executed, empty** | Poller ran; source had no new items or items were filtered | Poll count, empty count, source scan result |
| **Poll executed, received** | Poller produced messages | Poll count, received count, and handler flow |
| **Poll executed, failed** | Connect/read/filter/conversion failure | Error count, bounded exception class, latency |
| **Poll did not execute** | Scheduler stopped, lock held, executor saturated, or app down | Last successful tick, expected cadence, scheduler health |

### 7.2. Useful Timestamps and Durations

- `last_poll_at`: most recent poll trigger (if instrumented by the application).
- `last_nonempty_poll_at`: last poll that actually yielded data.
- `source_oldest_item_age`: age of the oldest unprocessed file/record.
- `processing_lag`: delta from source event time to acceptance or completion.
- `poll_duration`: duration of the poll read/scan.

An alert like “no messages for 10 minutes” can misfire in a nightly batch file flow. Compare against **source schedule, poll cadence, data SLA, and business calendar**.

### 7.3. Throttling, maxMessagesPerPoll, and Backpressure

Pollers can configure max messages per poll, schedules, and transactions. When the source produces data faster than polling/handling speed, backlogs grow even without exceptions. Measure **ingress rate, egress rate, queue age, and capacity** instead of endlessly increasing poll frequency, which can overload the target.

## 8. Outbound Adapter and Gateway Metrics

Outbound adapters/gateways form the boundary from Spring Integration to external systems. Distinguish:

- **Attempt:** the application initiates a send/call.
- **Transport accepted:** the client library/adapter accepts or buffers the request.
- **Remote ACK/response:** the partner/broker responds per protocol.
- **Business committed:** the business action is durably persisted at the target per contract.

For instance, with Kafka, a producer callback can confirm the broker received a record according to `acks`; that **does not** mean the downstream consumer finished processing it. With HTTP, a 200 response might mean “accepted asynchronously” rather than proving final business commit.

### 8.1. One-Way Adapters

One-way outbound adapters usually do not return a direct business reply to the flow. The count of messages dispatched to the adapter is insufficient to know real publish/upload outcomes. Collect **callbacks/confirms/error channels** or client/broker telemetry whenever available.

### 8.2. Request/Reply Outbound Gateways

Measure:

| Metric | Meaning |
|---|---|
| Request attempts | Actual send attempts, including retries |
| Request duration | Client wait time for reply/timeout |
| Response class | 2xx/4xx/5xx, or domain status |
| Timeouts | Calls with uncertain outcomes |
| Retry attempts | Additional attempts, grouped by cause |
| Circuit breaker state | Open/half-open/closed state if used |
| Confirmed business outcome | Real contract outcome, when verifiable |

If a timeout occurs **after the remote system committed**, retrying without idempotency can create duplicate records. Retry metrics are warnings, not replacements for **idempotency keys, remote state checks, and reconciliation**.

## 9. Micrometer in the Spring Integration Ecosystem

**Micrometer** provides `MeterRegistry` and meters such as `Counter`, `Timer`, and `Gauge`. Spring Boot Actuator exposes meters and exports data through configured registries. Spring Integration provides management/metrics/observation capabilities for channels and handlers, though exact activation and emitted meters depend on version.

### 9.1. Components to Distinguish

| Component | Role |
|---|---|
| `MeterRegistry` | Registry where application meters are registered/recorded |
| `Counter`, `Timer`, `Gauge` | Measurement primitives |
| Spring Integration management/instrumentation | Creates/registers measurements for channels, handlers, pollers depending on version/features |
| `ObservationRegistry` | Context for Micrometer Observation, unifying metrics and tracing |
| Spring Boot Actuator | Management/observability endpoints such as `/actuator/metrics` |
| Registry/exporter | Prometheus or equivalent backend |
| Logging/tracing | Adds per-request/message investigative context |

**Important:** adding a Micrometer registry **does not guarantee** all File/SFTP/JMS/Kafka/JDBC adapters automatically expose identical meters, tags, and timings. Some metrics come from underlying clients or connectors, and others must be built specifically for business needs.

### 9.2. Spring Integration Management

In supported Spring Integration versions, management features can be enabled/configured via `@EnableIntegrationManagement` or corresponding management configuration; check properties and Observation support for your library generation.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.EnableIntegrationManagement;

@Configuration
@EnableIntegration
@EnableIntegrationManagement
public class IntegrationManagementConfig {
    // Verify actual meters/observations with the version in use.
}
~~~

This is an **illustrative enablement example**, not a guarantee of complete meters in every Spring Boot application. Before production configuration, check whether Spring Boot auto-configuration already registers integration-management beans to avoid overlapping config or misunderstanding defaults.

### 9.3. Do Not Hardcode Meter Names from Memory

Depending on version, channel/handler metrics may be exported under different names and tags or via metrics/observation mechanisms. A safe workflow:

1. Enable appropriate management/observation support.
2. Run a representative integration flow.
3. List meters actually present in the registry/Actuator.
4. Record **meter name, base unit, type, tags, and increment conditions**.
5. Build dashboards/alerts from the verified list and lock them in integration tests.

Never assume a specific `spring.integration.*` meter name remains unchanged across dependency upgrades.

## 10. Spring Boot Example: Dependencies and Actuator

In a Spring Boot application using Spring Integration, add Actuator and your chosen registry. Maven dependency snippet example:

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
    </dependency>
</dependencies>
~~~

Manage versions via a compatible Spring Boot BOM/parent rather than picking Micrometer/Spring Integration versions arbitrarily.

### 10.1. Actuator Configuration Example

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: integration-adapters-demo
~~~

**Security warning:** `/actuator/metrics` and `/actuator/prometheus` can expose operational details. Expose endpoints only to authorized monitoring systems using proper authentication and network controls; never deploy this example exposure on the public Internet.

### 10.2. Discovering Actual Meters

In an authorized dev environment:

~~~bash
# Check that the metrics endpoint is enabled and secured:
curl -s http://localhost:8080/actuator/metrics

# Pick an actual meter name present in the output:
curl -s http://localhost:8080/actuator/metrics/METER_NAME

# With Prometheus registry configured:
curl -s http://localhost:8080/actuator/prometheus
~~~

`METER_NAME` is a placeholder, **not a default meter name**. Trigger several message sends/receives before inspecting; many meters appear only after components are exercised or registries are configured.

## 11. Java DSL Example: Naming Endpoints and Observing the Flow

Stable IDs make it easy to inspect metrics and traces by component without confusing auto-generated endpoint names:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class OrderFlowConfig {

    @Bean
    IntegrationFlow ordersFlow() {
        return IntegrationFlow.from("ordersInput")
                .filter(String.class,
                        text -> !text.isBlank(),
                        endpoint -> endpoint.id("validateOrderText"))
                .transform(String.class,
                        String::trim,
                        endpoint -> endpoint.id("normalizeOrderText"))
                .channel("ordersValidated")
                .handle(message -> {
                    // Process the normalized message.
                }, endpoint -> endpoint.id("ordersSink"))
                .get();
    }
}
~~~

Key point: `validateOrderText`, `normalizeOrderText`, `ordersSink`, and clearly named channels aid observability. **Do not infer exact meter names** from these IDs alone: they provide logical flow identity, whereas meter naming depends on instrumentation and version.

### 11.1. Verifying Meters Against Specific Events

Send a valid message and then a blank message to the input:

- The valid message traverses filter → transform → handler.
- The blank message is rejected by the filter → never reaches the handler.
- Inspect meter/filter counters or custom counters (if created) to verify the difference.
- Verify **valid message count** and **attempt count**, not just “meter exists.”

Do not treat a test sending a message to a channel as proof that remote Kafka/JMS/HTTP completed, since this flow has no outbound protocol adapter.

## 12. Proactively Adding Business Metrics with MeterRegistry

Built-in metrics show framework components; many projects also need domain-specific metrics such as “orders confirmed by target” or “batches rejected for schema errors.” You can use Micrometer directly.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class OrderFlowMetrics {
    private final MeterRegistry registry;
    private final Timer processingTimer;

    public OrderFlowMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.processingTimer = Timer.builder(
                "app.integration.processing.duration")
                .description("Duration of order processing logic")
                .tag("flow", "orders")
                .register(registry);
    }

    public void recordProcessing(Runnable action) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";
        try {
            action.run();
        } catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        } finally {
            sample.stop(processingTimer);
            Counter.builder("app.integration.events")
                    .tag("flow", "orders")
                    .tag("outcome", outcome)
                    .register(registry)
                    .increment();
        }
    }
}
~~~

### 12.1. Reading the Example's Exact Semantics

- `processing.duration` measures **the code passed into `action`**, not wait time in a QueueChannel or end-to-end latency.
- `events` counts **each invocation of `recordProcessing`**, not unique business messages automatically.
- If `action.run()` retries internally or the handler receives redeliveries, the counter can increment multiple times for the same business event.
- `outcome=success` here means **`action` did not throw a `RuntimeException`**; it does not prove durable target commit if `action` only enqueues data.
- The example catches `RuntimeException`, so it does not fully cover `Error`s or asynchronous execution; adapt to your application model.

### 12.2. Why Must Tags Be Fixed?

The example uses only `flow=orders` and `outcome=success|failure`. Avoid:

~~~text
Avoid:
tag("orderId", orderId)
tag("filename", filename)
tag("userId", userId)
tag("correlationId", correlationId)
tag("exceptionMessage", exception.getMessage())
~~~

These values are effectively unbounded over time, causing **high cardinality**, inflating memory/monitoring costs, and risking PII exposure. Put them in **secured structured logs/traces** rather than metric labels.

## 13. Designing a Metric Contract for an Integration Flow

### 13.1. Auditable State Milestones

~~~mermaid
stateDiagram-v2
    [*] --> SOURCE_AVAILABLE
    SOURCE_AVAILABLE --> RECEIVED: Inbound read succeeded
    RECEIVED --> ACCEPTED: Validate pass
    RECEIVED --> REJECTED: Validate fail
    ACCEPTED --> IN_FLIGHT: Processing
    IN_FLIGHT --> DELIVERY_ATTEMPTED: Outbound call
    DELIVERY_ATTEMPTED --> CONFIRMED: Target confirmed
    DELIVERY_ATTEMPTED --> RETRYABLE_FAILURE: Retryable
    RETRYABLE_FAILURE --> DELIVERY_ATTEMPTED: Valid retry
    RETRYABLE_FAILURE --> TERMINAL_FAILURE: Budget exhausted / DLQ
    CONFIRMED --> [*]
    REJECTED --> [*]
    TERMINAL_FAILURE --> [*]
~~~

Not every system transitions to `CONFIRMED` immediately. An HTTP API returning 202 may only accept async work; if business completion guarantees are required, collect callbacks/status events or run target reconciliation.

### 13.2. Example Application Meter Definitions

| Logical Meter | Type | Suggested Labels | Meaning |
|---|---|---|---|
| `app.integration.events` | Counter | flow, stage, outcome | Events passing a defined milestone |
| `app.integration.processing.duration` | Timer | flow, handler | Processing time of a logic segment |
| `app.integration.end_to_end.duration` | Timer | flow, outcome | Duration from received → confirmed/failed |
| `app.integration.queue.depth` | Gauge | flow, queue | Depth of a defined queue |
| `app.integration.oldest_item.age` | Gauge | flow, source | Age of oldest unprocessed item |
| `app.integration.poll.events` | Counter | source_type, outcome | Empty/nonempty/error polls |
| `app.integration.delivery.attempts` | Counter | target_type, outcome | Target call attempts and transport results |
| `app.integration.dlq.events` | Counter | flow, reason_class | Messages routed to DLQ |
| `app.integration.connections.active` | Gauge | dependency, state | Status or count of connections from client pool |

These metrics **must be coded/instrumented explicitly** if the project needs them. Never register dummy gauges always returning 0 when the real state source is unknown; alerting on fake data is misleading.

### 13.3. Clear Rules for Success and Retries

Suppose 100 business events enter: 95 complete immediately, 3 succeed after one retry, and 2 exhaust retries → DLQ:

- **Received unique events:** 100.
- **Successfully confirmed unique events:** 98.
- **Terminal failures:** 2.
- **Delivery attempts:** at least 103 if only the 3 events retried once; higher if the 2 failed events also retried.
- **Success rate by business events:** 98/100, not successful attempts divided by total attempts.

Without idempotency and business identity, computing unique events from attempts can be inaccurate. Align SLI definitions with domain owners.

## 14. SLIs and SLOs for Integration: What Is Good Enough?

An **SLI (Service Level Indicator)** is a quantitative measure of service quality; an **SLO (Service Level Objective)** is the target for an SLI over a window. Metrics are useful only when tied to system expectations.

### 14.1. Common SLIs

| SLI | Conceptual Formula | Must Clarify |
|---|---|---|
| **Delivery success rate** | Unique events confirmed / eligible events | Which system defines eligible and confirmed? |
| **End-to-end latency** | Confirmed time − accepted/source time | Does it include queues, remote APIs, downstream consumers? |
| **Freshness** | Now − event time of newest successfully processed item | Are clocks/timezones and event-time sources reliable? |
| **Backlog age** | Now − timestamp of oldest pending item | Pending at inbound source, in-memory queue, or broker? |
| **Processing error ratio** | Failed processing attempts / all processing attempts | Retryable errors or terminal failures? |
| **Availability of adapter path** | Fraction of window probes can receive and process | Do probes represent real transactions? |

### 14.2. Illustrative SLO Examples

- 99.9% of valid business events confirmed by target within the organization's measurement window.
- 95% of inbound files processed to target within a defined duration after the **file becomes ready to read**, excluding incomplete uploads.
- Order flow backlog age stays below a defined threshold during service hours.
- For end-of-day batch integrations, meeting the deadline matters more than per-minute messages/s.

**Never adopt these numbers as default SLAs**; align with business owners, actual throughput, batch windows, external system capabilities, and what events are in scope.

### 14.3. Inbound SLO Pitfall

If a poller checks SFTP only every 5 minutes, measuring latency from **poll time** ignores how long the file already sat on the server. To measure freshness, you may need the timestamp when the remote file finished uploading, safe metadata, and synchronized clocks. Never use local processing duration to claim “files entered the system on time.”

## 15. Designing Names and Labels Without High Cardinality

### 15.1. Naming

A reasonable convention:

~~~text
app.integration.<domain>.<signal>
Example:
app.integration.events
app.integration.processing.duration
app.integration.poll.events
app.integration.queue.depth
~~~

Metric names should convey **consistent units and semantics**; avoid putting `total` in code if your backend exporter already appends counter suffixes by convention, unless you know the exact export behavior.

### 15.2. Which Labels Are Appropriate?

| Label | Recommended? | Reason |
|---|---|---|
| `flow=orders` | Yes | Bounded set of flows |
| `adapter_type=kafka` | Yes | Bounded list of protocols |
| `direction=inbound|outbound` | Yes | Bounded |
| `outcome=success|failure|timeout` | Yes | Bounded |
| `error_class=auth|network|schema` | Yes if taxonomy is stable | Bounded, operationally meaningful |
| `environment=prod` | Yes if governed | Bounded environments |
| `host/instance` | Consider per collector | More instances multiply series, though sometimes needed for debugging |
| `file_path` | No | Cardinality/PII/sensitive paths |
| `message_id`, `order_id` | No | One series per message |
| `kafka_partition` | Consider | Scales with partition count; use only when needed |
| `exception_message` | No | Practically unbounded; may leak secrets |
| `http_url_full` | No | Dynamic paths and sensitive query params |

### 15.3. How Does Cardinality Explode?

With 10 flows × 5 endpoints × 4 outcomes × 50 tenant IDs × 2,000 filenames, combinations reach **2 million series** before even multiplying by instances and histogram buckets. By contrast, fixed flow/endpoint/outcome labels typically yield only hundreds of series. Never attach specific tenants/files/messages to metrics; put an **opaque correlation reference** in logs/traces.

## 16. File Adapter: Throughput, File Age, and Durability

### 16.1. Inbound File

Common issues:

- Poller runs yet finds no files due to file filters or directory configuration.
- File appears while an external writer has not finished writing; reading early causes parse errors.
- Duplicate files are picked up again due to incorrect metadata store/idempotency filter config.
- Old files pile up; low message counts leave unclear whether there is no data or an error.

What to measure:

| Metric | Source | Meaning |
|---|---|---|
| File discovered/eligible count | Scanner/filter | Eligible file count |
| File accepted count | Inbound adapter | Files turned into Spring Messages |
| File size distribution | File metadata | Distribution of file sizes |
| Oldest eligible file age | Directory/file inventory | Freshness SLA |
| Parse/validation failure | Handler/error channel | Payload errors |
| Duplicate/ignored count | Accept-once filter/metadata store | Files skipped by policy |
| Successful downstream outcome | Target/biz audit | Processing completed, not just file read |

### 16.2. Outbound File

File write attempts differ from files completed and readable by the target. For safe delivery, track **write temp → rename/commit protocol**, checksum/size, and I/O errors; never conclude a durable write just because channel send succeeded.

**Never use full filenames as metric labels**. To investigate a specific file, use log references or an audit file ID.

## 17. SFTP Adapter: Polls, Remote Sessions, and Transfer Outcomes

SFTP involves at least three metric scopes:

1. **Remote connectivity:** session establishment, auth failures, timeouts, stale connections.
2. **Remote discovery/transfer:** listing counts, eligible files, bytes transferred, transfer duration, retries, partial transfers.
3. **Downstream processing:** parse, transform, publish, ACK/DB commit after file receipt.

| Symptom | Metrics to Check | Diagnosis |
|---|---|---|
| No new messages | Poll count/last success, listing errors, remote file age | Poller stopped or remote directory empty? |
| File transfer errors | SFTP transfer errors, retries, session opens | Auth/network/permissions/remote disk? |
| Throughput drops | Bytes/s, transfer latency, concurrent sessions | Bandwidth, server throttling, file sizes? |
| Files re-read | Filter metadata state, duplicate count | Accept-once/filter persistence or rename? |
| Files downloaded but unprocessed | Local queue age, downstream errors | SFTP fine but flow backed up? |

**Connection lifecycle:** session pool metrics and remote status are not automatically exported by Spring Integration under one standard name; you may need metrics from the SSH/SFTP client, wrappers, or health probes. Avoid probing by opening sessions continuously at excessive rates that trigger rate-limiting.

## 18. HTTP Inbound/Outbound Gateway: Requests, Status, and Latency

### 18.1. HTTP Inbound

In addition to handler/channel metrics, track:

- HTTP request rate, latency, response status, 4xx/5xx, and timeouts.
- Requests converted into messages by the adapter and accepted by business handlers.
- In-flight requests, thread pool saturation, and bucketed request body sizes.
- **Client disconnects**/cancellations and cases where business processing continues after caller timeout.

If HTTP returns 202 right after enqueuing onto a QueueChannel, that is **acceptance**, not necessarily completion of the business event. Never use `2xx` rate as a confirmed-outcome SLI for async contracts.

### 18.2. HTTP Outbound

Measure request attempts, connection pool state, DNS/TLS errors, status class, response time, timeouts, retries, and circuit breakers if used. Separate:

- **Network/transport outcome:** connectivity/HTTP status.
- **Application outcome:** business response body/code.
- **Business completion:** remote committed vs. merely accepted asynchronously.

### 18.3. Safe HTTP Labels

Never use full URLs like `/customers/7812/orders/934` or query tokens as tags. Use bounded **route templates/endpoint classes**, status classes, and fixed client names; ensure framework HTTP metrics sanitize routes.

## 19. JMS Adapter: Ack, Transactions, Consumers, and DLQ

With JMS, Spring Integration handler metrics reflect only **in-process execution**, and do not guarantee JMS session commit/ack.

### 19.1. Broker/Client Signals

| Metric | Question |
|---|---|
| Queue depth/oldest age | How long are messages waiting? |
| Consumer count/in-flight | Are consumers connected and processing? |
| Delivery/redelivery count | Are messages being redelivered after rollback? |
| Acknowledge/transaction commit | Did processing commit per JMS semantics? |
| DLQ size/ingress | Where are terminally failed messages landing? |
| Connection/session failures | Did the broker disconnect or fail auth? |

### 19.2. Avoiding Double Counting

If a message rolls back and is redelivered three times, **handler invocation count = 3** while **unique business event = 1**. Define separate `attempt` and `confirmed unique` metrics keyed by business ID/deduplication. Never use a handler counter alone to claim exactly-once processing.

### 19.3. Transaction Boundaries

When a JMS consumer coordinates with database transactions, verify whether **ack and DB commit** share a transaction, how redelivery behaves, and DLQ thresholds. A short timer or handler success does not prove atomicity; test failure and recovery paths.

## 20. AMQP/RabbitMQ: Publish Confirms and Consumer Acks

Layers to observe:

1. **Producer:** publish attempts, confirm ack/nack, and returned messages if mandatory routing is enabled.
2. **Broker:** queue depth, ready/unacked messages, consumer count, ingress/deliver rates.
3. **Consumer:** processing attempts, ack/nack/requeue, errors, retries, and DLQ.
4. **Connection/channel:** reconnects, heartbeats, auth failures, channel closures.

**Distinctions:**

- Producer confirms show the broker handled publishing under confirm mode, **not that a consumer processed the message**.
- Consumer acks reflect protocol behavior, not guaranteed exactly-once database side effects.
- Requeueing can cause loops and inflate attempts; monitor **redelivery ratio and age of oldest message**, not just deliveries/s.

### 20.1. Warning on “High Throughput Without Progress”

If `deliveries/s` and `nack/requeue` are both high while backlog never shrinks, the system may be in a **poison-message loop**. A throughput-only dashboard leads to the wrong conclusion. Break down status by terminal success, DLQ, and error category.

## 21. Kafka Adapter: Partition/Offset, Lag, and Commit

### 21.1. Inbound Kafka

Kafka consumers should observe:

- Records polled/processed and failure attempts.
- **Consumer lag** by group/topic/partition when available.
- Rebalances, pauses, seek/retry, poll duration, and processing latency.
- Offset commit failures, DLQ/retry topic backlog.
- Elapsed time from record timestamp to processing/confirmation when timestamps are reliable.

**Consumer lag does not equal processing latency.** A record can be polled and processed slowly even with small lag; conversely, after a rebalance, lag may look high while the consumer is catching up.

### 21.2. Outbound Kafka

Monitor producer client metrics:

| Metric | Meaning |
|---|---|
| Publish/send attempts | Records passed to the producer API |
| Send callback success/failure | Broker publish outcome per producer semantics |
| Retry/buffer pressure | Producer congestion, backpressure |
| Batch/bytes/compression | Throughput characteristics |
| Broker request latency | Client/broker send and ack latency |
| Producer errors/timeouts | Transport failures or uncertain outcomes |

**Do not equate a successful send callback with downstream business processing.** If the contract requires consumer B to persist to a DB, obtain confirmation/reconciliation events from B.

### 21.3. Topic, Group, and Partition Tags

Topics/consumer groups are typically bounded and managed; partitioning multiplies series by partition count, so choose granularity to fit scale. Never use Kafka keys or payloads as metric labels. To inspect an individual record, record topic/partition/offset in **secured logs/traces**.

### 21.4. Exactly-Once and Outcome Metrics

Kafka supports transactional/offset features and idempotent producers depending on configuration, yet **end-to-end exactly-once** also depends on external side effects, DBs, and flows. Metrics alone do not verify that property; test under failures, replays, and rebalances.

## 22. JDBC/Database Adapter: Polling Watermark, Transactions, and Data Freshness

Common JDBC flows include inbound polling queries, outbound updates/inserts, or request/reply gateways. Required metrics:

- SQL/transaction duration, pool active/idle/wait counts, connection errors.
- Rows selected, processed, updated/inserted by outcome.
- **Watermark/cursor progress** and lag from source record creation to processing.
- Deadlocks, lock waits, serialization/constraint errors, retries.
- Rows re-selected after rollbacks/restarts and duplicate rates.

### 22.1. Do Not Measure Only Selected Rows

If an inbound poller SELECTs 1,000 rows but only processes/commits 100, the selected counter climbs rapidly while the **real backlog** does not shrink. Separate `selected`, `accepted`, `processed`, and `committed`.

### 22.2. Transactions and Idempotency

In multi-step DB → outbound API → DB status update flows, an HTTP timeout may happen after the remote system committed while the DB status remains un-updated. On retry, records can be processed twice. Add metrics for **reconciliation/unknown outcomes** alongside idempotency keys rather than inferring completion from SQL query timers.

### 22.3. Data Sensitivity

Never put SQL queries containing literal parameters, customer IDs, or record keys into labels. To group endpoints, use fixed **query names**, SQL operation types, or bounded repository method names, with proper access controls on metrics/logs.

## 23. Asynchronous Flows, Backpressure, and Queue Age

An integration flow can produce zero errors while growing steadily slower because arrival rate exceeds completion rate.

### 23.1. Relationship Between Ingress, Egress, and Backlog

Intuitively:

~~~text
backlog(t+Δt) ≈ backlog(t) + arrivals(Δt) - completed(Δt)
~~~

This equality holds only when both counters share the exact same scope and there are no duplicates, expirations, purges, or retry/delayed queues outside the counted set. In practice, define **which states belong to backlog**.

### 23.2. Little's Law and Its Limits

For a stable system under applicable conditions, **Little's Law** relates average work-in-progress, average throughput, and average wait time:

\[
L = \lambda W
\]

Where `L` is the average number of items in the system, `λ` is the steady-state average arrival/completion rate, and `W` is the average time spent in that system. Use it as a consistency check between **in-flight/queue depth**, throughput, and latency; do not apply it to instantaneous bursts, outages, or unstable systems.

### 23.3. Signs of Backpressure

| Signal | Likely Cause |
|---|---|
| Queue age rises, egress rate drops | Downstream slow or failing |
| Executor queue grows, active threads maxed out | Pool saturated |
| Producer buffer pressure increases | Broker/remote slow, insufficient throughput |
| Outbound HTTP p99 rises | Target/network/connection pool slow |
| Poller errors/timeouts increase | Source unavailable or pool exhausted |
| Retry attempts climb while success stays flat | Poison message / prolonged remote outage |

Blindly adding more workers can overload databases or brokers. Use **throttling, bounded queues, max in-flight limits, retry backoff, circuit breakers, and capacity planning**.

## 24. Error Channels, Retries, and DLQ: Measuring Errors Without Miscounting

### 24.1. Three Failure Types to Distinguish

1. **Transient failure:** timeouts, network resets, rate limits, broker temporarily unavailable. Retryable with backoff.
2. **Permanent failure:** bad payload schema, invalid credentials/permissions, unsupported format. Retrying identically will not fix it.
3. **Unknown outcome:** request timed out while the remote system may have committed; requires readback/reconciliation before retrying.

### 24.2. Counters to Keep Separate

- `processing_attempts`: every handler invocation.
- `retry_attempts`: every additional retry attempt.
- `recovered_after_retry`: unique events that ultimately succeeded after retrying.
- `terminal_failures`: unique events that failed terminally.
- `dlq_published`: events confirmed published to the DLQ per protocol.
- `dlq_reprocessed`: DLQ events reprocessed via operational procedure.
- `unknown_outcomes`: events with uncertain target state.

### 24.3. ErrorMessage Does Not Equal “One Terminal Failure”

Spring Integration provides `errorChannel`/`ErrorMessage` paths depending on endpoints and configuration. An exception may be caught, retried, routed to an error channel, rolled back, or returned to the caller. Identify **which error flow is responsible for emitting terminal outcomes** so `terminal_failures` is not incremented on the first retryable failure.

**Do not count 3 failed attempts as 3 failed business events** when it is a single event being retried.

## 25. Metrics, Message History, and Tracing: Connecting Measurements to Root Cause

### 25.1. Typical Drill-Down Workflow

~~~mermaid
flowchart TD
    ALERT[Alert: end-to-end latency increased] --> FLOW[Flow dashboard]
    FLOW --> STAGE[Stage: poller / queue / handler / outbound]
    STAGE --> METRIC[Metrics: age, timer, error, retry]
    METRIC --> TRACE[Trace/span by correlation]
    TRACE --> LOG[Structured logs, error code, endpoint]
    LOG --> HISTORY[Local MessageHistory if available]
    HISTORY --> TARGET[Reconcile ACK / broker / database]
    TARGET --> ACTION[Root cause, remediation, verification]
~~~

Not every system has full tracing across all adapters; instrument and propagate context properly, especially across `QueueChannel`, `ExecutorChannel`, brokers, and HTTP. `MessageHistory` only records traversed Spring Integration components when enabled and headers are preserved; it does not contain per-hop durations.

### 25.2. Correlation ID Is Not a Metric Tag

To investigate a specific message:

~~~text
Dashboard:
  flow=orders, target=kafka, outcome=timeout

Structured log/trace:
  correlation_ref=corr-82
  business_ref=order-opaque-ref
  endpoint=publishOrders
  error_code=BROKER_TIMEOUT

Spring Integration message history:
  validateOrder -> transformOrder -> publishOrders
~~~

Put `correlation_ref` in traces/logs, **never** in counter/timer tags. This keeps metric cardinality low while supporting detailed investigations.

## 26. Operational Dashboards by Flow and Dependencies

A useful dashboard starts from the **service journey** rather than listing hundreds of unexplained meters.

### 26.1. Sample “orders-file-to-kafka” Dashboard

| Dashboard Row | Panels | Question |
|---|---|---|
| **Business outcome** | Confirmed unique events, success %, end-to-end p95/p99 | Are orders being accepted on time? |
| **Inbound** | Files eligible, file age, poll empty/error, bytes | Are files appearing and being read? |
| **Processing** | Filter reject %, transform error %, handler timer | Are payloads or logic failing? |
| **Queue** | Depth, oldest age, enqueue/dequeue rate | Is there an internal backlog? |
| **Outbound Kafka** | Send attempts, confirmations, producer errors, retries | Are producer/broker confirming sends? |
| **Downstream** | Consumer lag, DLQ, completion events | Are consumers keeping up with records? |
| **Dependency health** | SFTP session failures, broker availability, DB pool | Are external dependencies unhealthy? |

### 26.2. Three Viewing Levels

1. **Service overview:** SLOs, freshness, end-to-end success, oldest backlog age.
2. **Component drill-down:** channels, handlers, adapters, pools, retries, error classes.
3. **Case investigation:** traces/logs and external target acknowledgments by correlation/business reference.

Restrict dashboards from showing personal data; enforce viewer permissions, retention, and alert routing per operations team.

## 27. Illustrative Prometheus Queries

The examples below assume you **explicitly created** counter `app.integration.events` and timer `app.integration.processing.duration` as in section 12, exported them via Prometheus registry, and checked actual series names. Prometheus names are normally normalized, so **verify them on `/actuator/prometheus`** before use.

### 27.1. Successful Event Rate

~~~promql
sum(
  rate(app_integration_events_total{
    flow="orders",outcome="success"
  }[5m])
)
~~~

This measures the **success rate of `recordProcessing`** as defined in the example application, not unique target-confirmed orders.

### 27.2. Attempt Error Ratio

~~~promql
sum(rate(app_integration_events_total{
  flow="orders",outcome="failure"
}[5m]))
/
clamp_min(
  sum(rate(app_integration_events_total{
    flow="orders"
  }[5m])),
  0.001
)
~~~

During low traffic, rates over short windows are noisy; add a **minimum traffic condition** or separate burn-rate policy instead of paging P0 because one event caused a 100% error ratio.

### 27.3. p95 Processing Duration

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(app_integration_processing_duration_seconds_bucket{
      flow="orders"
    }[5m])
  )
)
~~~

This query **works only when histogram buckets are actually configured and exported** for that timer. A timer without percentile histograms will lack `_bucket` series; in that case configure histogram/SLO buckets or use another measurement.

### 27.4. Backlog Age Alert

With a custom instrumented gauge:

~~~promql
max(app_integration_oldest_item_age_seconds{
  flow="orders"
}) > 300
~~~

The 300-second threshold is illustrative only. Account for **no data**, off-hours/non-batch windows, producer downtime, and freshness business rules; a missing gauge may indicate an exporter failure rather than zero backlog.

## 28. Alerting: Avoiding False Positives and Missed Incidents

### 28.1. Symptom-Based Business Alerts

Prioritize alerts such as:

- **Confirmed end-to-end success** rate drops below target in the measurement window.
- **Oldest pending item age** exceeds threshold while the source has data.
- **Queue backlog grows steadily** with insufficient completion throughput.
- **Consumer lag or DLQ** grows unusually and persistently.
- **Remote publish confirmations** drop while retries/timeouts rise.
- **Poller stops running** relative to expected schedule, even when no inbound data arrives.

### 28.2. Supporting Cause-Based Alerts

Alerts for connection errors, TLS/auth failures, thread pool saturation, DB pool waits, or broker unavailability are valuable **supporting signals**, though they do not always map 1:1 to immediate user impact.

### 28.3. Sample Severity Table

| Reference Level | Symptom | Response |
|---|---|---|
| **Critical** | Critical data stream stalled and backlog threatens deadline | Page on-call, coordinate source/target owners, contain and recover |
| **High** | Delivery confirmations drop sharply, DLQ climbs, age stays elevated | Investigate connector/broker/handler, prioritize fix |
| **Medium** | One batch source delayed but still within recovery window | File ticket and monitor closely |
| **Low** | Minor metric shift, no SLO impact | Review during business hours |

These are not universal thresholds. **Never alert on a single cumulative counter** without rate/window, baseline, and traffic volume. Always define a fallback when the monitoring pipeline itself loses data.

## 29. Runbook MET-01 — Channel/Adapter Metrics Missing

**Symptom:** messages are flowing, yet `/actuator/metrics` lacks expected meters.

1. **Check dependencies:** are Micrometer, Actuator, and the exporter compatible versions?
2. **Check enablement:** is Spring Integration management/Observation enabled or auto-configured in the right `ApplicationContext`?
3. **Check flow execution:** meters may not be registered until the channel/handler is actually invoked.
4. **Check endpoint IDs and beans:** does the channel/handler you are inspecting actually belong to the flow that ran?
5. **Check the registry:** is the exporter reading the same `MeterRegistry`, and is any `MeterFilter` dropping meters?
6. **Check exposure/security:** is the metrics endpoint disabled, permission-restricted, or exposed only internally?
7. **Check actual names/tags:** never hardcode names from other examples/versions.
8. **Check adapter origin:** does the metric come from the underlying client/broker rather than Spring Integration itself?
9. **Check measurement:** send a representative message/trigger a poll and observe which meters actually increment.
10. **Write regression tests** protecting critical naming/semantics once verified for your version.

**Do not rush to fix by creating a fake custom meter with the same name** as a built-in meter; that causes label conflicts and masks configuration bugs.

## 30. Runbook MET-02 — Metrics Exist but Report Misleading Results

### 30.1. High Throughput with Low Business Outcome

Check: attempts vs. unique events, retry/requeue loops, successful channel send vs. outbound ACK, database commit vs. handler return, filter rejections, and DLQ.

### 30.2. Low Handler p95 with Slow End-to-End Latency

Check: poll interval, source file age, QueueChannel/executor wait, broker lag, remote processing, response callbacks, and clock skew.

### 30.3. Sudden 100% Error Rate

Check: a short window with only 1 failing request, a newly deployed service with no success traffic yet, missing success series in the exporter, changed label mappings, counter resets after restarts, or scheduled batch boundaries.

### 30.4. “Backlog = 0” When Users Report Missing Data

Check: which queue are you measuring? Are messages unpolled at the source, sitting in another broker, routed to DLQ, or dequeued by a handler that hasn't confirmed? Monitor **source pending + channel queue + broker/remote pending** across the SLI scope.

### 30.5. Duplicate or Doubled Metrics

Check overlapping instrumentation, wrapper counters added on top of built-in counters, retries, redeliveries, multiple subscribers, duplicate scrape targets, and multi-instance aggregation. Never divide by 2 blindly before finding the root cause.

## 31. Testing Strategy for Metrics

Metrics are part of the **operational contract** and must be tested, without coupling tests tightly to every internal library meter name.

### 31.1. Testing Custom Meters with SimpleMeterRegistry

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderFlowMetricsTest {
    @Test
    void countsSuccessfulProcessing() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            OrderFlowMetrics metrics = new OrderFlowMetrics(registry);
            metrics.recordProcessing(() -> {
                // Simulate one successful processing execution.
            });

            double count = registry.counter(
                    "app.integration.events",
                    "flow", "orders",
                    "outcome", "success")
                    .count();

            assertEquals(1.0d, count);
        }
    }
}
~~~

This example tests the **custom counter according to `recordProcessing` semantics**; it does not prove end-to-end correctness of any specific adapter. In real applications, add compatible JUnit dependencies and organize tests in the proper test environment; this snippet is illustrative, not an executed test run.

### 31.2. Other Tests to Include

| Test | Simulated Input/Incident | Expectation |
|---|---|---|
| Handler success | Valid message | Success counter increments, timer records sample |
| Handler throws | Processing error | Failure counter increments, exception not swallowed |
| Filter reject | Invalid schema | Reject counter increments, outbound not called |
| Empty poll | No files/records | Poll counter increments if tracked, received does not |
| Source unavailable | SFTP/DB connect fail | Error counter increments, alerts per policy |
| Queue saturation | Slow consumer | Queue depth/age rises, send success not counted as business success |
| Retry/redelivery | Single event processed multiple times | Attempts rise, unique outcome not double-counted |
| Broker timeout | Unknown publish outcome | Confirmed not incremented automatically; requires callback/reconciliation |
| HTTP 202 async | Remote accepts request | Accepted rises, completed increments only when confirmation arrives |
| Missing series | Scraper failure | Missing-data alert fires; no data never treated as zero |
| High cardinality | Many unique IDs | No series created per message/file/user ID |

### 31.3. Version-Dependent Integration Tests

For built-in channel/handler metrics, build a small flow, send messages, and verify **meters confirmed in your exact application version**. When upgrading dependencies, review meter/tag names and dashboard compatibility; avoid locking down every internal framework meter unless it is part of a maintained contract.

## 32. Security, Privacy, and Observability Cost

### 32.1. Never Leak Payloads or Credentials

Metric labels are not the place for:

- JWTs, OAuth access/refresh tokens, API keys, SSH private keys.
- Cookies, Authorization headers, SFTP usernames/passwords.
- Personal names, emails, customer IDs, or personally identifiable order numbers.
- Full file paths, URL queries, or SQL containing literal data.
- Raw stack traces/exception messages.

### 32.2. Access Control and Retention

Actuator endpoints, exporters, dashboards, and alerts must enforce role-based access control. Configure retention per organizational policy; sensitive business audits require separate storage from aggregate metrics. Connection monitoring can also reveal internal topology/services.

### 32.3. Instrumentation Cost

Every timer with histogram buckets and labels multiplies time series. Before enabling histograms on every handler/endpoint:

1. Identify SLIs that truly require percentiles.
2. Pick buckets suited to your latency range.
3. Measure series count, storage, and scrape overhead.
4. Avoid unbounded label values.
5. Rely on sampling/tracing for drill-downs instead of bloating metrics.

### 32.4. The Metrics Pipeline Can Fail Too

Prometheus exporters, scrape networks, registries, or monitoring backends can go down. Distinguish **missing telemetry** from **healthy service**. Alerting on missing data/telemetry pipeline health is part of observability.

## 33. Practice Scenarios with Guided Solutions

### Scenario A — File Poller Produces No Messages

The dashboard shows zero `received` events for 15 minutes while new files appear in the source directory.

**Resolution:** check poll ticks, last successful poll, file eligibility, file filters, read permissions, scheduler state, and age of the oldest file. If the poller is not running, you cannot conclude “no data” from a `received` count of 0.

### Scenario B — QueueChannel Depth Grows While Handler Timer Looks Good

Waiting messages climb steadily. Handler p95 is only 10 ms, yet customers see a one-minute delay.

**Resolution:** inspect enqueue/dequeue rates, consumer concurrency, poller schedule, queue age, and end-to-end latency. Queue wait time is excluded from the handler timer; address backpressure and capacity at the real bottleneck.

### Scenario C — SFTP Transfer Count Rises but Kafka Has No Records

Inbound SFTP downloads files and transformers succeed, yet downstream Kafka has no records.

**Resolution:** separate SFTP inbound success, handler success, outbound send attempts, and Kafka producer confirmations. Check serializer/topic/permissions/callbacks/DLQ; never treat inbound metrics as proof of broker publish.

### Scenario D — HTTP 202 Returned Yet Users See No Result

The inbound gateway returns 202 immediately after enqueuing the message, but the downstream consumer is slow.

**Resolution:** separate HTTP acceptance from QueueChannel depth/age, downstream completion events, and the business success SLI. Never use 2xx rate as the success rate of an async workflow.

### Scenario E — JMS Redeliveries Inflate Error Counts

A message rolls back and is redelivered repeatedly; the dashboard shows 200 errors for only 20 business events.

**Resolution:** inspect attempt/redelivery/unique-event counters, transaction ACKs, and DLQ. Separate terminal failures from retry attempts, apply deduplication/idempotency, and verify outcomes.

### Scenario F — RabbitMQ Throughput Very High Yet Queue Never Drains

Consumers continuously receive messages and nack/requeue due to schema errors.

**Resolution:** measure redelivery ratio, nack/requeue rates, DLQ, and oldest backlog age. Cap retries, classify permanent errors, and break the poison-message loop instead of scaling consumers indefinitely.

### Scenario G — Kafka Consumer Lag Is Low Yet DB Updates Lag Behind

Kafka polling/acks look healthy, yet data is not persisted in time.

**Resolution:** check offset commit semantics, DB pool waits/transaction latency, async queues/in-flight work, and end-to-end confirmations. Low lag does not prove DB transactions committed.

### Scenario H — Gauge Drops to 0 Because Exporter Disconnected

Dashboards show queue depth as 0 after the monitoring exporter fails.

**Resolution:** check for missing series, `up`/scrape health, and the live application. Alert on missing data; never treat null or missing series as 0.

### Scenario I — Metrics Backend Overloaded by Labels

A developer adds `filename` and `orderId` to tags, causing a sudden spike in time series.

**Resolution:** remove per-message variable labels, keep bounded flow/adapter/outcome tags, and move IDs into structured logs/traces. Estimate histogram × tag cost before re-enabling.

### Scenario J — Error Ratio Rises After Retry Rollout

After adding retries, the handler failure counter increases while terminal DLQ count drops.

**Resolution:** this can reflect a change in **attempt semantics**, not necessarily worse health. Compare retry attempts, recovered-after-retry, terminal failures, remote confirmations, and end-to-end latency.

### Scenario K — JDBC Polling Processes the Same Row Twice

The poller SELECTs unprocessed rows; an HTTP timeout occurs after the remote system committed, leaving DB status un-updated.

**Resolution:** separate selected, attempt, and confirmed outcomes; use idempotency keys, remote reconciliation, transactions/watermarks, and duplicate counts. Never infer completion from SQL query timers.

### Scenario L — DirectChannel Send Latency p99 Spikes

A synchronous channel dashboard reports slow sends while the outbound adapter sits at the end of the flow.

**Resolution:** inspect downstream handlers/calls on the same thread, CPU, external HTTP/DB latency, queues, and circuit breakers. A DirectChannel send timer can encompass downstream execution rather than the channel itself being “slow.”

## 34. Metrics Implementation Checklist for Adapters and Channels

### 34.1. Pre-Code Design

- [ ] Defined success/error/attempt/confirmed per **business contract**.
- [ ] Mapped boundaries: inbound → channel → handler → outbound → remote ACK.
- [ ] Assigned stable endpoint/channel names, noting which are sync vs. async.
- [ ] Agreed on SLIs: success rate, end-to-end latency, queue age/freshness.
- [ ] Instrumented poll ticks and source backlogs, not just message counts.
- [ ] Defined adapter-specific telemetry for File/SFTP/HTTP/JMS/AMQP/Kafka/DB.
- [ ] Selected low-cardinality labels; excluded business IDs/PII from tags.

### 34.2. Configuration and Testing

- [ ] Verified Micrometer/Actuator/registry versions are compatible.
- [ ] Configured Spring Integration management/observation in the right context.
- [ ] Secured access to metrics exporters; never exposed publicly.
- [ ] Listed and verified actual meter names/tags/types.
- [ ] Tested custom counters/timers for happy path, failures, and retries.
- [ ] Measured end-to-end confirmations at the proper target/ACK boundary.
- [ ] Ensured retries/redeliveries are not counted as unique successes/failures.
- [ ] Configured histograms/percentiles before querying `_bucket` series.
- [ ] Added missing-data alerts and checked series cardinality.

### 34.3. Operations and Verification

- [ ] Built dashboards starting from business SLOs, drilling down to adapters/channels.
- [ ] Monitored both queue depth and **age**.
- [ ] Tracked SFTP/File poller last tick and oldest item age.
- [ ] Properly interpreted broker ACK, DLQ, consumer lag, and commit semantics.
- [ ] Avoided equating HTTP 2xx/202 with business completion.
- [ ] Clearly separated Database SELECT/processed/committed boundaries.
- [ ] Configured alerts with windows, traffic floors, owners, escalation, and runbooks.
- [ ] Verified logs/traces/message history support root-cause tracing without leaking data.
- [ ] Re-verified metric contracts and dashboards after adapter/registry changes.

## 35. Conclusion

**Metrics for adapters and channels** go beyond “counting messages passing through Spring Integration.” A reliable integration system clearly distinguishes **what inbound received, what MessageChannels transferred, how handlers processed it, how many times outbound attempted delivery, and what the target confirmed**. Queue age, poll cadence, retries, connection health, and business freshness expose cases where throughput looks fine while real data is delayed or lost.

In **Spring Integration Adapters**, Micrometer and Spring Boot Actuator provide a solid foundation for collecting and exporting metrics; channel/handler instrumentation must be verified against your library version, and telemetry for File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC must align with each protocol's semantics. Combining **well-contracted metrics, SLI/SLO dashboards, logs/traces/message history, and destination verification**—while keeping labels bounded and protecting sensitive data—enables operations teams to accurately distinguish **sent – received – processed – confirmed complete**.
