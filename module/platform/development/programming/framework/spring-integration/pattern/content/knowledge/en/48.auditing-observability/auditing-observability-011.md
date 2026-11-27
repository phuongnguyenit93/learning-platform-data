# Linking Logs, Metrics, and Traces with Correlation IDs in Spring Integration

## 1. Why Link All Three Signal Types?

An Enterprise Integration Patterns (EIP) flow can traverse **Gateway → Router → Transformer → QueueChannel → Service Activator → Aggregator**. When troubleshooting failures, the three observability signals typically supply different pieces of the puzzle:

- **Logs:** Which message took which branch? At which step did the error occur?
- **Metrics:** How are error rates, latency, and throughput shifting across the whole system?
- **Distributed traces:** Which spans, across which services or threads, did a specific execution traverse?

If logs, metrics, and traces cannot be linked together, operators see error-rate metrics spiking without knowing which requests were affected; they see error logs without knowing which invocation or Router branch produced them.

A **Correlation ID** tracks *one business journey* across disparate steps. However, **putting a correlation ID everywhere is not always right**: metric labels with excessive cardinality bloat the monitoring system, and client-supplied IDs must be validated to prevent spoofing or data leakage.

This lesson belongs to the **Audit and observability** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module focuses on implementing Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows; practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation while testing and monitoring branches. Here, we design a **cross-flow identifier contract** and use it intentionally across logs, metrics, traces, and audit trails.

After this lesson, you will be able to:

1. Distinguish a business correlation ID from Spring Integration's EIP correlation header and from `traceId`/`spanId`.
2. Establish and preserve the ID across message boundaries.
3. Record the correlation ID in structured logs/MDC without leaking context across threads.
4. Attach the correlation ID to traces as an appropriate attribute, while **not** using it as a metric label.
5. Pivot from a metric alert to the related traces, logs, and audit records for the affected requests.
6. Test ID propagation, request isolation, MDC restoration, and retry/async handling.

## 2. Four Identifiers That Are Often Confused

In Spring Integration, the word "correlation" can refer to several distinct purposes. Name them explicitly from the start.

| Identifier | Scope | Purpose | When Can It Change? |
| --- | --- | --- | --- |
| **Business correlation ID** | One business operation/journey | Links logs, traces, and audit events of a single request | Usually preserved across steps, potentially spanning multiple retries |
| **EIP `correlationId`** | One message group in Splitter/Aggregator/Barrier | Groups related fragments or signals accurately | Can differ when splitting groups or starting new attempts |
| **`traceId`** | One distributed trace created by tracing | Finds all spans belonging to one trace | Can change if a workflow starts a new trace, an old trace ends, or context is not propagated |
| **`spanId`** | One unit of work within a trace | Distinguishes a specific Router/handler/HTTP call | Changes per span |

In Spring Integration, the EIP header typically uses:

~~~java
IntegrationMessageHeaderAccessor.CORRELATION_ID
~~~

It is usually represented by the `correlationId` header. **Do not overwrite this header solely for logging** if the flow contains a Splitter, Aggregator, Barrier, or components relying on grouping; doing so can alter message aggregation behavior.

To avoid conflicts, examples in this lesson use an application header:

~~~text
obsCorrelationId = "c-76e6f41c"
~~~

This is the **business correlation ID used for observability**. The name `obsCorrelationId` is purely an application convention, not a mandatory Spring Integration header. A system may use `requestId`, `workflowId`, or `businessCorrelationId` if producers and consumers agree.

### Example of Two Attempts for the Same Order

~~~text
orderId               = order-17
obsCorrelationId      = corr-order-17          (preserved across retries)
attemptId             = attempt-2             (changes on new attempt)
EIP correlationId     = order-17/attempt-2    (keys a Barrier group)
traceId               = 7c6e...               (tracing context)
spanId                = a9f1...               (specific span)
~~~

Use **`obsCorrelationId`** to find the full business timeline, **`attemptId`** to tell attempts apart, **EIP `correlationId`** for accurate grouping, and **`traceId`** to follow parent–child span relationships.

## 3. The Big Picture: Linking Logs → Metrics → Traces

~~~mermaid
flowchart TD
    IN["Gateway receives request\nobsCorrelationId=c-123"] --> R["Router"]
    R --> T["Transformer"]
    T --> Q["Queue / Async Worker"]
    Q --> H["Handler"]
    H --> OUT["Output / Reply"]
    R -. "Log with obsCorrelationId" .-> LOG["Structured logs"]
    T -. "Log with obsCorrelationId" .-> LOG
    H -. "Log with obsCorrelationId" .-> LOG
    R -. "Metric: flow, route, outcome" .-> MET["Metrics: low-cardinality"]
    H -. "Metric: duration, outcome" .-> MET
    IN -. "Trace context" .-> TRACE["Traces: traceId/spanId"]
    Q -. "Spans, if instrumentation enabled" .-> TRACE
    H -. "Span attribute: obsCorrelationId" .-> TRACE
    TRACE -. "traceId" .-> LOG
    MET -. "Exemplar or time + route" .-> TRACE
    LOG -. "obsCorrelationId" .-> AUDIT["Audit store when durable storage needed"]
~~~

A sound linkage design:

1. **Logs** contain `obsCorrelationId`; when tracing/MDC is enabled, logs can also include `traceId` and `spanId`.
2. **Traces** can carry `obsCorrelationId` as a **high-cardinality span attribute**; `traceId` and `spanId` are managed by the tracing framework.
3. **Metrics** use only finite grouping dimensions such as `flow`, `pattern`, `route`, `outcome`, and normalized `exceptionType`.
4. **Metrics → traces** use exemplars if supported and enabled by the backend, or narrow down by time window/service/route to find traces/logs; **never** attach individual correlation IDs as metric labels.
5. **Audit trails**, when required for reconciliation, must be persisted via a durable mechanism rather than relying on debug logs or sampled spans.

**Core principle:** Correlation IDs are keys to *query individual cases*, whereas metrics are *aggregations across many cases*.

## 4. Designing the ID Contract at the Inbound Boundary

A sample rule set for a Gateway or inbound adapter:

| Scenario | Recommended Handling |
| --- | --- |
| Request has no ID yet | Generate a new ID at ingress |
| Request has an ID from a trusted source | Validate type, length, and format, then preserve it |
| ID sent by an untrusted client | Do not trust by default; generate an internal ID and store the external ID in a separate field |
| ID is too long or contains newlines | Reject or normalize to prevent log injection |
| Business ID exists, yet EIP needs a different correlation | Use two separate headers; never overwrite |
| Retrying the same operation | Keep the business correlation ID, increment `attemptId` |

Example normalizing an inbound message with `obsCorrelationId`:

~~~java
package example;

import java.util.UUID;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class CorrelationHeaders {

    public static final String OBS_CORRELATION_ID = "obsCorrelationId";

    private CorrelationHeaders() {
    }

    public static <T> Message<T> ensureAtIngress(Message<T> source) {
        Object raw = source.getHeaders().get(OBS_CORRELATION_ID);

        if (raw == null) {
            return MessageBuilder.fromMessage(source)
                    .setHeader(
                            OBS_CORRELATION_ID,
                            UUID.randomUUID().toString())
                    .build();
        }

        if (!(raw instanceof String value)
                || !value.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException(
                    "obsCorrelationId is invalid");
        }

        return source;
    }
}
~~~

This function illustrates *one sample contract*, not a universal validator for every enterprise. When communicating across services, agree on format, length, and ID authority. Some organizations prefer generating a fresh backend UUID while storing a validated `externalRequestId` for reconciliation.

**Never use email addresses, phone numbers, tokens, or entire payloads as a correlation ID.** The ID will appear widely in logs and traces; it should be non-sensitive and hard to guess within the system's access context.

## 5. Which Boundaries Must Preserve the Correlation ID?

Spring Integration supports header propagation across many endpoints. However, **never assume every component preserves every header**: out-of-JVM adapters, broker mappers, custom Transformers, or Aggregators can alter message packaging.

| Boundary | Risk | Assertion to Verify |
| --- | --- | --- |
| Gateway → Flow | Gateway builds a new message | `obsCorrelationId` is present after ingress |
| Router → Selected branch | Secondary branch misses header | Header exists on the right output route |
| Transformer | Builds new message, forgets to copy headers | Business ID remains intact |
| Filter → Discard | Only success branch is logged | Discard branch still retains ID for diagnostics |
| Splitter | One request spawns many fragments | Every fragment keeps the business correlation ID |
| Aggregator | Group output may copy headers from a representative message | Final result keeps ID; EIP `correlationId` still performs grouping |
| QueueChannel/ExecutorChannel | Thread switch | Header survives; MDC must be re-established on the consumer |
| Kafka/JMS/HTTP adapter | Process/protocol switch | Header mapping and tracing propagation actually work |
| Retry/Error channel | Exception or redelivery | Correlation, `attemptId`, and failure cause remain traceable |
| Gateway reply | New response message | Attach ID to reply if required by the caller contract |

### Example Headers Before and After a Splitter

~~~text
Request:
  obsCorrelationId = c-123
  payload = [item-A, item-B]

Splitter output 1:
  obsCorrelationId = c-123
  correlationId = <group-X>
  sequenceNumber = 1
  sequenceSize = 2

Splitter output 2:
  obsCorrelationId = c-123
  correlationId = <group-X>
  sequenceNumber = 2
  sequenceSize = 2
~~~

This separates responsibilities cleanly: **`obsCorrelationId`** tracks the entire order journey, while **`correlationId`** is managed by EIP so the Aggregator reassembles the right group. Never modify `sequenceNumber` or `correlationId` just to tidy up logs.

## 6. Structured Logging: Which Fields to Record?

Unstructured text logs make querying difficult when a flow spans many components. An illustrative JSON log:

~~~json
{
  "timestamp": "2026-11-21T08:00:00Z",
  "level": "INFO",
  "service": "order-integration",
  "flow": "checkout",
  "stage": "router.vip",
  "event": "message.routed",
  "obsCorrelationId": "c-123",
  "traceId": "9d4a6e8b1fc2a310e5db87c64311df09",
  "spanId": "184ef19a56b90dc1",
  "attemptId": 1,
  "outcome": "success",
  "durationMs": 7
}
~~~

Values are **illustrative dummy data**, not logs automatically emitted by Spring Integration. In practice, `traceId`/`spanId` are available only when tracing is configured and context is active on the processing thread.

Distinguish three field groups:

- **Fields for routine filtering:** `service`, `flow`, `stage`, `route`, `outcome`.
- **Fields for tracing individual cases:** `obsCorrelationId`, `traceId`, `spanId`, `attemptId`.
- **Fields requiring caution:** Payloads, headers containing tokens, customer details, addresses, URL query strings.

Not every operation needs an `INFO` log. Log at key milestones (received, routed, retried, rejected, completed, timed out) and rely on metrics for high-volume traffic to avoid generating millions of low-value "message received" log lines.

## 7. MDC: Making the Correlation ID Appear in Handler Logs

With SLF4J and an MDC-capable logging backend, you can place `obsCorrelationId` into the **Mapped Diagnostic Context (MDC)** while handling a message:

~~~java
package example;

import java.util.function.Supplier;
import org.slf4j.MDC;
import org.springframework.messaging.Message;

public final class CorrelationLogContext {

    private static final String KEY = "obsCorrelationId";

    private CorrelationLogContext() {
    }

    public static <T> T within(
            Message<?> message, Supplier<T> work) {
        Object raw = message.getHeaders().get(KEY);
        if (!(raw instanceof String id) || id.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing obsCorrelationId header");
        }

        String previous = MDC.get(KEY);
        try {
            MDC.put(KEY, id);
            return work.get();
        } finally {
            if (previous == null) {
                MDC.remove(KEY);
            } else {
                MDC.put(KEY, previous);
            }
        }
    }
}
~~~

Inside a handler:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.Message;

public final class OrderHandler {
    private static final Logger log =
            LoggerFactory.getLogger(OrderHandler.class);

    public String process(Message<String> message) {
        return CorrelationLogContext.within(message, () -> {
            log.info("Processing order");
            // Logs in methods on the same thread also have MDC.
            return "accepted:" + message.getPayload();
        });
    }
}
~~~

Example log pattern with Logback/Spring Boot (adjust to match your logging config):

~~~properties
logging.pattern.level=%5p [corr:%X{obsCorrelationId:-}] [trace:%X{traceId:-},span:%X{spanId:-}]
~~~

**Why restore MDC in `finally`?** Worker threads are reused. If processing message A leaves an ID on the thread, logs for message B could carry A's ID by mistake. The snippet restores the previous value if an outer scope existed; calling `MDC.clear()` indiscriminately would wipe keys set by other components.

MDC is **thread-local state**, not a message header and not a transport mechanism across brokers. In an `ExecutorChannel`, `QueueChannel`, or async handler, re-establish MDC from the **message header** at the worker boundary. Tracing context (`traceId`/`spanId`) needs the tracing framework's own propagation mechanism.

## 8. Micrometer Observation and Tracing: Attaching Attributes in the Right Place

In a Spring Boot/Spring Integration app configured with **Micrometer Observation**, you can wrap a handler in an observation. Observations support two metadata tiers:

- **Low-cardinality key values:** Small, repeating set of values suitable as metric labels.
- **High-cardinality key values:** Many distinct values suitable for traces/spans and individual case lookup, **never** as metric tags.

Example:

~~~java
package example;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.messaging.Message;

public final class ObservedOrderHandler {

    private final ObservationRegistry observations;

    public ObservedOrderHandler(ObservationRegistry observations) {
        this.observations = observations;
    }

    public String handle(Message<String> message) {
        String correlationId = (String) message.getHeaders()
                .get(CorrelationHeaders.OBS_CORRELATION_ID);

        Observation observation = Observation.createNotStarted(
                        "integration.orders.handle", observations)
                .lowCardinalityKeyValue("flow", "orders")
                .lowCardinalityKeyValue("stage", "handler")
                .highCardinalityKeyValue(
                        "app.obs_correlation_id", correlationId);

        observation.start();
        try (Observation.Scope ignored = observation.openScope()) {
            return CorrelationLogContext.within(message, () -> {
                // Place to invoke the real service/Transformer.
                return "processed:" + message.getPayload();
            });
        } catch (RuntimeException error) {
            observation.error(error);
            throw error;
        } finally {
            observation.stop();
        }
    }
}
~~~

In this example, `flow=orders` and `stage=handler` are **low-cardinality** and safe for metric aggregation. `app.obs_correlation_id` is **per-request**, so it is added as a high-cardinality key value.

**Configuration note:** Creating an `Observation` does not automatically guarantee distributed traces appear in your backend. You must configure `ObservationRegistry`, an appropriate `ObservationHandler`, a Micrometer Tracing bridge, and an exporter/backend. Depending on version, enable Spring Integration instrumentation or observe endpoints explicitly; verify in tests and your trace backend. Without a tracing bridge, observations can still feed metrics or other handlers without necessarily producing spans.

### traceId Is Not a Business Correlation ID

Let the tracer generate and manage `traceId`/`spanId`. Never coerce `obsCorrelationId` into `traceId` by forcing arbitrary strings: trace IDs have strict formats and semantics, and tracing can sample or start fresh traces per protocol.

For long-running asynchronous workflows, **multiple traces** may share a single business correlation ID. In that case, `obsCorrelationId` connects them across logs and audits, while trace context or span links describe technical relationships if supported by instrumentation.

## 9. Metric Cardinality: Why Not Add Correlation ID as a Label?

Metrics are typically stored as time series distinguished by metric name and **label combinations**. Attaching a fresh correlation ID per message means every request can create a brand-new label combination.

**Bad** example:

~~~text
integration_messages_total{
  flow="checkout",
  outcome="success",
  obsCorrelationId="c-123"
} 1
~~~

**Good** example:

~~~text
integration_messages_total{
  flow="checkout",
  route="vip",
  outcome="success"
} 1734
~~~

These two values are purely illustrative, not default metrics emitted automatically by Spring Integration. When investigating request `c-123`, search **logs** or **span attributes** rather than looking for a dedicated metric time series for `c-123`.

### Metric Label Selection Table

| Field | Should It Be a Metric Label? | Reason |
| --- | --- | --- |
| `flow` | Yes, if a fixed set | Groups by integration flow |
| `route` | Yes, if bounded to known routes | Monitors Router |
| `outcome` | Yes: success/error/timeout | Computes error rates |
| `exceptionType` | Conditionally, normalized error buckets | Avoids unbounded exception messages |
| `tenantTier` | Conditionally: a few known tiers | Never use raw tenant ID when tenants are numerous |
| `obsCorrelationId` | **No** | Nearly every request has a distinct value |
| `traceId`, `spanId` | **No** | Every trace/span has a distinct ID |
| `messageId`, `orderId`, `userId` | **No** | High cardinality, potentially sensitive |

If a system processes \(N\) distinct correlation IDs and uses the ID as a label, that single label alone can produce up to **\(N\) time series combinations** for each combination of the remaining labels. Adding `route`, `stage`, and `outcome` multiplies combinations further. This is why cardinality caps should be enforced before deploying dashboards and alerts.

### How to Go from Metrics to Traces Without a Correlation Label?

Use one of two paths:

1. **Exemplars**: the metrics system attaches a sample `traceId` to a measurement point, and the backend/dashboard supports jumping to that trace; this must be configured and is not guaranteed on every sample.
2. **Narrowing down**: from metrics you know the time window, service, route, and outcome → search related traces/logs in that window → grab `traceId` or `obsCorrelationId` to investigate.

Metric alerts start investigations using statistical signals; **they do not promise every single metric sample links to an exact trace**.

## 10. How Audits Differ from Logs, Metrics, and Traces

**Audit trails** answer: *Who or which component performed what action, on which entity, when, and with what outcome?* Many systems require durable audits with retention and tamper-protection policies; logs, metrics, and traces mainly serve operations and may be sampled or expire sooner.

Example business audit event:

~~~json
{
  "auditEventId": "evt-0024",
  "occurredAt": "2026-11-21T08:00:01Z",
  "operation": "order.confirm",
  "entityType": "order",
  "entityReference": "opaque-order-reference",
  "obsCorrelationId": "c-123",
  "attemptId": 2,
  "outcome": "accepted",
  "sourceService": "order-integration",
  "traceId": "9d4a6e8b1fc2a310e5db87c64311df09"
}
~~~

This is dummy data. If audit events contain identifiers or personal data, enforce appropriate RBAC, masking, retention, and access controls.

Questions to clarify:

- When is an audit event considered **committed**?
- If the business operation succeeds yet writing the audit fails, is there recovery or an outbox?
- If retries lead to the same outcome, do we record each attempt or only one business event?
- Who is allowed to query audits, and are audit accesses themselves audited?
- How do we prove ordering and integrity when multiple services emit events?

**Logging a correlation ID alone is not enough to guarantee auditing.** When strict reconciliation is required, use durable event storage, transactions, or an outbox with schema versioning and idempotency keys.

## 11. Testing Whether a Spring Integration Flow Preserves Correlation IDs

The following JUnit 5 example uses **Java 17, Spring Integration Java DSL 6.x, Spring Test, and AssertJ**. Its goal is to prove a Transformer preserves the **business correlation header** and does not overwrite the **EIP correlation header**.

With Spring Boot, use compatible dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Create `src/test/java/example/CorrelationPropagationTest.java`:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(CorrelationPropagationTest.TestFlow.class)
class CorrelationPropagationTest {

    @Autowired
    @Qualifier("orders.input")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.output")
    QueueChannel output;

    @Test
    void transformer_preserves_business_and_eip_correlation_ids() {
        Message<String> original = MessageBuilder
                .withPayload("  order-17 ")
                .setHeader("obsCorrelationId", "c-order-17")
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        "group-17")
                .build();

        assertThat(input.send(original)).isTrue();
        Message<?> processed = output.receive(1_000);

        assertThat(processed).isNotNull();
        assertThat(processed.getPayload())
                .isEqualTo("normalized:order-17");
        assertThat(processed.getHeaders().get("obsCorrelationId"))
                .isEqualTo("c-order-17");
        assertThat(processed.getHeaders().get(
                IntegrationMessageHeaderAccessor.CORRELATION_ID))
                .isEqualTo("group-17");
        assertThat(output.receive(0)).isNull();
    }

    @Test
    void two_requests_do_not_share_business_correlation() {
        input.send(MessageBuilder.withPayload(" A ")
                .setHeader("obsCorrelationId", "c-A")
                .build());
        input.send(MessageBuilder.withPayload(" B ")
                .setHeader("obsCorrelationId", "c-B")
                .build());

        Message<?> first = output.receive(1_000);
        Message<?> second = output.receive(1_000);
        assertThat(first).isNotNull();
        assertThat(second).isNotNull();
        assertThat(first.getHeaders().get("obsCorrelationId"))
                .isEqualTo("c-A");
        assertThat(second.getHeaders().get("obsCorrelationId"))
                .isEqualTo("c-B");
        assertThat(output.receive(0)).isNull();
    }

    @Configuration
    @EnableIntegration
    static class TestFlow {

        @Bean("orders.output")
        QueueChannel output() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow orderFlow() {
            return IntegrationFlow.from("orders.input")
                    .transform(String.class,
                            value -> "normalized:" + value.trim())
                    .channel("orders.output")
                    .get();
        }
    }
}
~~~

**What does this test prove?** With the standard Transformer used in the example, the required headers survive at the output; two requests with distinct business correlation IDs never mix. The test **does not** prove every custom Transformer or every broker adapter preserves all headers automatically. Those boundaries require dedicated tests.

If an endpoint constructs a new `Message` manually, use `MessageBuilder.fromMessage(original)` or copy **only allowlisted headers** per the application contract, avoiding indiscriminate copying of tracing metadata or internal reply channels to external systems.

## 12. Testing That MDC Does Not Leak Across Messages

A worker thread typically serves many messages sequentially. Therefore, test **MDC restoration even when a handler throws an exception**.

Add a test class for `CorrelationLogContext`:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class CorrelationLogContextTest {

    static Message<String> request(String id) {
        return MessageBuilder.withPayload("payload")
                .setHeader("obsCorrelationId", id)
                .build();
    }

    @Test
    void restores_previous_mdc_after_normal_processing() {
        String previous = MDC.get("obsCorrelationId");
        try {
            MDC.put("obsCorrelationId", "outer");
            String result = CorrelationLogContext.within(
                    request("c-A"),
                    () -> {
                        assertThat(MDC.get("obsCorrelationId"))
                                .isEqualTo("c-A");
                        return "ok";
                    });

            assertThat(result).isEqualTo("ok");
            assertThat(MDC.get("obsCorrelationId"))
                    .isEqualTo("outer");
        } finally {
            restore(previous);
        }
    }

    @Test
    void restores_previous_mdc_after_exception() {
        String previous = MDC.get("obsCorrelationId");
        try {
            MDC.put("obsCorrelationId", "outer");
            assertThatThrownBy(() -> CorrelationLogContext.within(
                    request("c-B"), () -> {
                        assertThat(MDC.get("obsCorrelationId"))
                                .isEqualTo("c-B");
                        throw new IllegalStateException("test failure");
                    })).isInstanceOf(IllegalStateException.class);

            assertThat(MDC.get("obsCorrelationId"))
                    .isEqualTo("outer");
        } finally {
            restore(previous);
        }
    }

    private static void restore(String value) {
        if (value == null) {
            MDC.remove("obsCorrelationId");
        } else {
            MDC.put("obsCorrelationId", value);
        }
    }
}
~~~

The test requires an MDC-supporting SLF4J logging backend (such as Logback in a standard Spring Boot test setup). If the environment uses a **no-op MDC adapter**, MDC assertions are meaningless; configure a real logging backend before testing.

### Testing Asynchronous Boundaries

To test `ExecutorChannel` or a poller, add a scenario where a single worker processes A and then B:

1. A has `obsCorrelationId=c-A`, B has `obsCorrelationId=c-B`.
2. Each time the handler runs, call `CorrelationLogContext.within` with the **current message**.
3. Record the ID inside the handler and assert `[c-A, c-B]`.
4. After each handler call, verify the thread's context no longer holds the previous message's ID.
5. Use a `CountDownLatch` or observable queue with a finite timeout; never use `Thread.sleep` to guess when a thread finished.

**Do not pass MDC using `InheritableThreadLocal` for all worker threads** and assume brokers/processes will preserve context too. Message headers and tracing framework propagation are the right boundaries for carrying context.

## 13. Testing That Metrics and Traces Link Properly

The header/MDC tests above do not yet prove traces are actually exported. Add two more test layers:

### Metric Tests

Register an `ObservationRegistry`/test meter registry. Send multiple requests with different IDs along the same route, then verify:

- The counter or timer for `flow=orders`, `outcome=success` increments the expected number of times.
- No labels exist for `obsCorrelationId`, `traceId`, `spanId`, `orderId`, or `userId`.
- An error on one request lands in `outcome=error` without incrementing `success`.
- `route` takes only declared values, never reading raw paths or dynamic payloads.

### Trace Tests

With a tracing bridge and a test/in-memory exporter:

- The flow creates/continues spans according to instrumentation config.
- `traceId` links spans of the same trace when context propagation is active.
- Spans carry attribute `app.obs_correlation_id=c-123` when code explicitly attaches it.
- `traceId` is never generated from `obsCorrelationId`.
- When trace sampling drops a span, audits/logs can still be queried by business correlation ID if required operationally.

### Integration Tests With a Broker or HTTP

When messages cross Kafka/JMS/HTTP, test end-to-end:

1. Is the `obsCorrelationId` header serialized/mapped to the consumer?
2. Is trace context injected into the carrier via the configured Micrometer/OTel propagation mechanism?
3. Does the worker in the other process log the right business correlation ID?
4. Do retries/redeliveries keep the business ID while distinguishing attempts?
5. Are sensitive headers or spoofed IDs rejected rather than trusted just because a client sent them?

Do not rely on unit tests with `DirectChannel` to claim cross-service tracing works.

## 14. Investigation Workflow: From a Metric Alert to a Failing Message

Suppose a dashboard shows the error rate on route `vip` spiking unusually:

~~~text
Metric alert:
  integration_messages_total{flow="checkout", route="vip", outcome="error"}
  increases in the observation window
~~~

An investigation workflow to follow:

1. **Scope the incident:** Service, flow, route, outcome, and affected time window.
2. **Find a related trace:** Use the exemplar `traceId` if supported by the backend; otherwise search traces by service/route within that window.
3. **Inspect the trace:** Examine spans Gateway → Router → Handler → downstream call; identify the failing span or prolonged wait.
4. **Extract `obsCorrelationId`:** From span attributes if present, or from logs tagged with `traceId`.
5. **Search logs by correlation ID:** Combine logs from the processing branch, retries, error channel, and reply to reconstruct the business journey.
6. **Reconcile with audits:** Verify final business state, `attemptId`, retry outcomes, or compensation if needed.
7. **Fix and verify:** Watch metrics after the fix and use a new correlation ID to confirm flow health; do not equate errors disappearing on the dashboard with all older requests having been resolved.

If a trace was sampled out or lost propagation at one step, the **cross-message business correlation ID** still serves as a vital bridge between logs and audits. However, if the ID is dropped at an adapter or custom Transformer, that link breaks—which is why every boundary must be tested.

## 15. Common Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Using `IntegrationMessageHeaderAccessor.CORRELATION_ID` for all IDs | Can break Splitter/Aggregator grouping | Keep `obsCorrelationId` separate from EIP `correlationId` |
| Trying to use `obsCorrelationId` as `traceId` | Breaks tracing semantics | Let the tracer manage `traceId`; attach business ID as an attribute |
| Attaching correlation ID as a metric label | Very high cardinality, wastes resources | Use low-cardinality labels; look up IDs in logs/traces |
| Writing to MDC and forgetting to clear | Message B logs carry A's ID | Restore in `finally` |
| Assuming MDC crosses `ExecutorChannel`/brokers automatically | Context breaks on thread/process switch | Propagate headers and re-establish MDC at the consumer |
| Assuming trace context crosses every adapter automatically | Traces split into disconnected fragments | Configure and test propagation per protocol |
| Logging full payloads | Data leakage, bloated logs | Schema-based structured logs with masking |
| Relying solely on sampled traces for auditing | Missing business evidence | Use a dedicated durable audit store |
| Copying all headers downstream | Leaks tokens or internal reply channels | Propagate only contract headers |
| Generating new uncontrolled correlation IDs on retry | Hard to join attempts of the same operation | Keep business ID, add attempt ID |
| Testing only the happy path | Misses ID loss in Filters/error channels | Test error, discard, and timeout branches |
| Using `requestId` as a metric label | Exploding time-series count | Group by flow, route, outcome |

## 16. Hands-On Exercises

### Exercise A — Propagating Across Router and Transformer

Build a `Gateway → Router(VIP/STANDARD) → Transformer → Output` flow. Attach `obsCorrelationId` at ingress; write a JUnit test with two requests carrying distinct IDs. Verify both branches preserve the ID and do not overwrite the EIP correlation header.

### Exercise B — Zero MDC Leakage Between Messages

Build a handler using `CorrelationLogContext.within` to log `obsCorrelationId`. Send A then B on a single-threaded executor, and add a case where the handler throws an exception. Prove B never picks up A's ID and MDC is restored after exceptions.

### Exercise C — Safe Metric Labels

Generate 100 synthetic requests, each with a distinct `obsCorrelationId`, across only two routes and two outcomes. Count the resulting metric time series if using correlation ID as a label vs. using only `route` and `outcome`. Explain why metrics should aggregate while per-request IDs belong in logs/traces.

### Exercise D — Tracing Across QueueChannel or Broker

Attach `obsCorrelationId=c-123` at ingress and send the message across an asynchronous boundary. Enable tracing suitable for your project and inspect traces in a test exporter. Prove downstream spans link when trace context propagates properly, while the business correlation ID remains in message headers.

### Exercise E — Retries, Error Channels, and Audits

Simulate a request failing on the first try and succeeding on the second try. Keep `obsCorrelationId`, change `attemptId`, and write error logs and schema-based audit events. Check error/success metrics by route, and locate both attempts by correlation ID without creating per-request metric labels.

### Exercise F — Investigating an Error from a Dashboard

Introduce a controlled error on the VIP route. Start from the `outcome=error` metric, identify the time window, find a trace by service/route or exemplar (if available), search logs by `traceId` and then `obsCorrelationId`, and finally verify the audit record. Note which step broke the link if any data is missing.

## 17. Pre-Deployment Checklist

1. Is the business correlation ID created/validated at ingress and preserved across flow steps?
2. Are business IDs clearly separated from EIP `correlationId`, `traceId`, and `spanId`?
3. Do Router, Transformer, Splitter, Aggregator, Gateway, and ErrorChannel have explicit propagation contracts?
4. Do `QueueChannel`/`ExecutorChannel`/broker boundaries propagate IDs and re-establish MDC?
5. Do structured logs include `obsCorrelationId`, stage, route, outcome, attempt, and trace IDs when tracing is active?
6. Do metrics use only low-cardinality labels with enforced cardinality limits?
7. Do traces include a span attribute for the business ID, and is trace propagation tested via integration tests?
8. Does the dashboard support pivoting from metrics to traces via exemplars or time/service filtering?
9. When traces are dropped by sampling, can you investigate via logs/audits without losing the linking key?
10. Does the audit trail provide durability, access control, and idempotency matching requirements?
11. Do retries/late replies keep the business ID while distinguishing `attemptId`?
12. Do tests verify MDC restoration when a handler succeeds or throws?
13. Are headers and logs filtered to prevent tokens, personal data, and log injection?
14. Is there operational documentation explaining how to pivot via `obsCorrelationId` from a metric alert to business outcomes?

**Conclusion:** To link logs, metrics, and traces in Spring Integration, maintain a **business correlation ID across messages**, include it in **logs and span attributes**, and **never use it as a metric label**. Tracing provides technical relationships via `traceId`/`spanId`; metrics show trends; audits persist business events needed for reconciliation. Designing propagation boundaries, MDC hygiene, and cardinality carefully—backed by tests for success, error, and async branches—lets you trace any message from a system-wide alert down to its exact execution journey.

### References

- [Spring Integration Reference — Message Headers](https://docs.spring.io/spring-integration/reference/message.html): message structure and metadata across integration flows.
- [Spring Integration Reference — Micrometer Observation](https://docs.spring.io/spring-integration/reference/metrics.html): observability/metrics capabilities for Spring Integration components, depending on version and configuration.
- [Micrometer Observation Documentation](https://docs.micrometer.io/micrometer/reference/observation.html): low-cardinality/high-cardinality key values and observation handlers.
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/): tracing, propagation, and span context.
