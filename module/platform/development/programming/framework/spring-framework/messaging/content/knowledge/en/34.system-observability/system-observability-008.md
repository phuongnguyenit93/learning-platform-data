# Limiting Label Values and Avoiding User Identifiers in Metrics

## Objectives

Metrics help answer operational questions such as: how many messages per second is the system processing, is the error rate rising or falling, how is handler latency changing, and which channel is bottlenecked. To slice data, metrics usually carry labels (or tags) such as destination, protocol, outcome, and region.

Every combination of metric name and label pairs creates a distinct time series. Putting userId, email, sessionId, or requestId into labels can cause the number of time series to grow with the number of users or requests. As a result, memory, CPU, storage, and query costs of the monitoring system spike rapidly; dashboards and alerts also become harder to aggregate.

This lesson explains cardinality, how to design labels with finite value sets, how to handle user identifiers in metrics, and how to use Micrometer Observation/MeterFilter to keep cardinality within bounds.

After this lesson, you can:

- Explain cardinality and the relationship between labels and time series.
- Estimate series counts from a metric's dimensions.
- Spot labels at risk of unbounded growth.
- Choose meaningful replacements such as route templates, enums, status groups, or error categories.
- Distinguish low-cardinality and high-cardinality key values in Micrometer Observation.
- Use MeterFilter to enforce protective limits on a MeterRegistry.
- Move identifier data into controlled logs or traces and test the metric schema.

## 1. What Is Cardinality?

Cardinality is the number of distinct values a dimension can take. For metrics, consider two levels:

- **Cardinality of a single label:** the number of distinct values of a tag key, for example outcome having three values: success, rejected, and error.
- **Cardinality of a metric:** the number of distinct labelset combinations across all tag keys sharing the same metric name. Every combination that occurs creates one time series.

For example, the metric messaging.messages.total has two labels:

~~~text
destination = orders.create | orders.cancel
outcome     = success | rejected | error
~~~

At most there are:

~~~text
2 destinations × 3 outcomes = 6 time series
~~~

Every time a new combination appears, the monitoring system must store another series. Each series' counter value grows over time, yet each labelset remains an independent data stream.

A general formula:

~~~text
Maximum number of series for a metric
    ≈ distinct values of tag 1
      × distinct values of tag 2
      × ...
      × distinct values of tag N
~~~

This is the upper bound when every combination occurs. The actual number of series may be lower if some combinations never happen. Backend-added labels such as job, instance, pod, or region also multiply the total number of series system-wide.

## 2. Why Does Cardinality Grow Quickly?

### 2.1. Labels with unbounded value sets

Values like status, protocol, or operation usually have a small set of choices. Conversely, per-user or per-request identifiers can continually generate new values.

| Tag key | Example values | Assessment |
|---|---|---|
| protocol | rsocket, stomp | Usually low |
| outcome | success, rejected, error | Low |
| error_category | connection, protocol, conversion, business, other | Low if backed by a fixed enum |
| destination | orders.create, orders.cancel | Low if routes are bounded |
| region | ap-southeast-1, eu-west-1 | Controllable if region list is finite |
| user_id | u-10001, u-10002, ... | High, grows with user count |
| email | a@example.com, b@example.com | High and contains personal data |
| request_id | UUID per request | Nearly one value per request |
| session_id | UUID per session | High, changes per session |
| trace_id | Unique trace ID | High |
| order_id | ID of each order | High |
| exception_message | Free-form exception text | High, unpredictable |
| raw_url | /orders/10001, /orders/10002 | High if containing dynamic IDs |

User identifiers are not the only hazard. Any value derived from free-form data or unique IDs can inflate cardinality: SQL queries, filenames, full URLs, IP addresses, transaction codes, error strings, and arbitrary headers.

### 2.2. Multiplicative effect across labels

Suppose a messaging metric has:

- 4 destinations.
- 2 protocols.
- 3 outcomes.
- 3 regions.

The maximum number of combinations is:

~~~text
4 × 2 × 3 × 3 = 72 series
~~~

If you add user_id with 100,000 distinct values, the upper bound becomes:

~~~text
72 × 100,000 = 7,200,000 series
~~~

Adding just one label turns an easily manageable metric into millions of series. If the metric is a histogram, each labelset also creates additional series for buckets, sum, and count; costs can grow even further.

Do not judge a tag solely by how many values exist today in dev. A tag with 20 values today derived from user ID, request ID, or tenant ID can still climb to hundreds of thousands under real production load.

### 2.3. Impact on the system

High cardinality imposes multiple costs:

- **Memory and CPU:** each series requires its own metadata, state, and update operations.
- **Storage:** each series accumulates samples over time; more series increase disk usage and retention costs.
- **Slow queries:** PromQL or equivalent queries must scan far more series.
- **Unreadable dashboards:** a chart splits into too many lines or groups.
- **Hard-to-manage alerts:** rules can spawn numerous alert instances, creating noisy alerts.
- **Platform bills:** monitoring services billed per series, sample, or storage volume can spike significantly in cost.
- **Personal data risk:** emails, phone numbers, or user IDs can leak into metrics systems with broader access permissions than intended.

Cardinality is an instrumentation design problem from day one. Once a metric with dynamic labels is exported, removing a label can require changing code, dashboards, alerts, and deployment pipelines.

## 3. Principles for Designing Low-Cardinality Labels

### 3.1. Use finite value sets

A good tag has a known value set or one bounded by an enum/allowlist.

Suitable examples for messaging:

| Tag key | Suggested value set |
|---|---|
| protocol | rsocket, stomp, jms, other |
| destination | orders.create, orders.cancel, notifications.send, other |
| outcome | success, rejected, error |
| error_category | connection, protocol, conversion, business, other |
| consumer_group | Consumer group name declared in configuration |
| environment | local, test, staging, production |

Do not take values directly from client headers without validation. Clients can send arbitrary routes, event types, or tenant names. Map incoming values to a server-defined enum or group.

For example, instead of recording a raw destination, normalize it:

~~~java
enum MetricDestination {
    ORDERS_CREATE("orders.create"),
    ORDERS_CANCEL("orders.cancel"),
    NOTIFICATIONS_SEND("notifications.send"),
    OTHER("other");

    private final String tagValue;

    MetricDestination(String tagValue) {
        this.tagValue = tagValue;
    }

    String tagValue() {
        return tagValue;
    }

    static MetricDestination from(String destination) {
        return switch (destination) {
            case "orders.create" -> ORDERS_CREATE;
            case "orders.cancel" -> ORDERS_CANCEL;
            case "notifications.send" -> NOTIFICATIONS_SEND;
            default -> OTHER;
        };
    }
}
~~~

Unrecognized routes are grouped into other. That prevents a client sending unusual destinations from creating a new time series per value.

### 3.2. Use route templates instead of full URLs

URLs with dynamic IDs:

~~~text
/orders/12345
/orders/12346
/orders/12347
~~~

Should be normalized into a route template:

~~~text
/orders/{orderId}
~~~

In messaging, use fixed logical destinations like orders.find or orders.update instead of concatenated strings containing orderId. Route templates still show which operation type is being monitored without creating per-resource series.

Do not use raw URLs, query strings, or filenames in metrics. When you need to locate a specific request, use logs or traces.

### 3.3. Use error categories instead of exception messages

Do not do:

~~~java
counterBuilder.tag("exception", exception.getMessage());
~~~

Error messages can contain SQL, IDs, filenames, URLs, or user input. Two failures of the same type can produce two different strings.

Classify into a finite set instead:

~~~java
enum ErrorCategory {
    CONNECTION,
    PROTOCOL,
    CONVERSION,
    BUSINESS,
    OTHER
}
~~~

If you need the specific exception class, log it or attach it to a trace. Only include exception class in a metric when the set of classes is controlled and serves a clear analytical purpose; never put free-form exception messages into tags.

### 3.4. Set a cardinality budget before adding a tag

Before adding a tag, answer:

1. What is the maximum number of distinct values for this tag?
2. Are values derived from IDs or free-form input?
3. Can they be grouped into an enum or template?
4. Do on-call operators truly need to filter metrics by this dimension?
5. How many series does combining the new tag with existing tags produce?
6. Does the tag contain personal data, secrets, or sensitive identifiers?

There is no single universal threshold for every backend. Prometheus recommends keeping the cardinality of most metrics low; metrics with higher cardinality should be scrutinized carefully to reduce dimensionality. Guidance numbers are not hard technical limits for all systems.

## 4. Do Not Put User Identifiers into Metrics

### 4.1. Identifiers to avoid

Do not use the following values as metric tags in standard instrumentation:

- user_id, account_id, customer_id.
- Email, phone number, or username.
- session_id, cookie, or access token.
- request_id, correlation_id, trace_id, message_id.
- order_id, payment_id, transaction ID.
- IP addresses or URLs containing identifying info.
- Tenant ID if tenant count is large or can grow without bound.

Some B2B systems have a small, fixed, managed set of tenants. In those special cases, a tenant tag should only be used after establishing a cardinality budget, access controls, and a concrete operational justification. Never assume tenant ID is always low cardinality.

### 4.2. Use metrics for trends, not per-user lookups

Metrics are suited for aggregate questions:

- How many messages are processed per minute?
- What is the success rate by destination?
- What is the p95 latency of the orders.create handler?
- Is the connection or conversion error category increasing?
- Which consumer group has high backlog or processing time?

Metrics are not a database for directly answering:

- Which user created this request?
- Which request UUID failed?
- Which email was rejected?
- Which specific order is pending?

For per-entity questions, use structured logs, traces, or an appropriate business datastore. Metrics hold aggregate dimensions; logs/traces hold the context of a single processing run.

### 4.3. Splitting data across metrics, logs, and traces

| Data type | Appropriate place | Examples |
|---|---|---|
| Aggregate counts and trends | Metrics | destination=orders.create, outcome=error |
| Details of a single event | Structured logs | messageId, requestId, userId if policy allows |
| Path of one request across services | Distributed traces | traceId, span ID, operation, diagnostic attributes |
| Authoritative business state | Database or event store | order ID, payment ID, transaction status |

Identifying data in logs and traces still requires protection policies. Moving a field out of metrics does not mean it can be logged everywhere. Consider intended usage, access control, masking, retention, sampling, and personal data protection requirements.

Trace ID or message ID can help stitch related events together. They should not become metric labels. If your backend supports exemplars, a metric sample can link to a representative trace without creating a time series for every trace ID.

## 5. Low-Cardinality and High-Cardinality in Micrometer Observation

Micrometer Observation distinguishes two kinds of key values:

- **Low-cardinality key values:** small, bounded value sets; included in both metrics and traces.
- **High-cardinality key values:** unbounded or very large value sets; included in traces, never used as meter tags.

This is a helpful boundary allowing instrumentation to declare explicitly which data may participate in creating time series.

Example:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public class MessageProcessor {

    private final ObservationRegistry observationRegistry;
    private final OrderService orderService;

    public MessageProcessor(
            ObservationRegistry observationRegistry,
            OrderService orderService) {
        this.observationRegistry = observationRegistry;
        this.orderService = orderService;
    }

    public void process(
            OrderCommand command,
            String userId,
            String messageId) {

        Observation.createNotStarted(
                        "messaging.process",
                        observationRegistry)
                .lowCardinalityKeyValue(
                        "messaging.destination",
                        "orders.create")
                .lowCardinalityKeyValue(
                        "messaging.protocol",
                        "rsocket")
                .highCardinalityKeyValue(
                        "user.id",
                        userId)
                .highCardinalityKeyValue(
                        "messaging.message.id",
                        messageId)
                .observe(() -> orderService.process(command));
    }
}
~~~

messaging.destination and messaging.protocol have finite value sets, so they can serve as meter tags. user.id and messaging.message.id can change on every execution; they are marked high-cardinality to assist traces without creating separate metric series.

The example assumes the application has its own OrderCommand and OrderService. The ObservationRegistry must be configured with matching ObservationHandlers to export metrics or traces. Without suitable handlers, creating an Observation alone does not guarantee data reaches a backend.

**Security note:** high-cardinality does not mean permissible to record. If userId can identify an individual or falls under restricted data rules, consider omitting it from traces altogether, using a pseudonymous identifier, restricting access, and setting appropriate retention. Emails, phone numbers, tokens, and authentication credentials should not be added merely because the API permits them.

### 5.1. Custom ObservationConvention

When instrumentation needs to extract tags from context, you can create an ObservationConvention. The convention cleanly separates low and high values:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.http.server.observation.ServerRequestObservationContext;
import org.springframework.http.server.observation.ServerRequestObservationConvention;

public class CustomRequestConvention
        implements ServerRequestObservationConvention {

    @Override
    public String getName() {
        return "http.server.requests";
    }

    @Override
    public String getContextualName(
            ServerRequestObservationContext context) {
        return "http request";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ServerRequestObservationContext context) {
        return KeyValues.of(
                KeyValue.of(
                        "request.method",
                        context.getCarrier().getMethod()));
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(
            ServerRequestObservationContext context) {
        return KeyValues.empty();
    }
}
~~~

This example illustrates how a convention is structured: HTTP method has a small value set. In real applications, extend Spring's default convention to retain standard tags like status, outcome, and exception; do not replace the entire convention unless intentionally changing the metric schema.

For HTTP paths, use only route templates or normalized values in low-cardinality tags. Actual paths containing IDs must not go into metrics. If you need full URIs for diagnostics, use a high-cardinality trace attribute governed by data policies.

## 6. Recording Custom Metrics with a Controlled Tag Set

If you do not need Observation, you can build Counters or Timers directly with Micrometer. Tag values should be normalized before registering the meter.

Example:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public class MessagingMetrics {

    private final MeterRegistry registry;

    public MessagingMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordProcessed(
            String rawDestination,
            MessageOutcome outcome) {

        String destination =
                MetricDestination.from(rawDestination).tagValue();

        Counter.builder("messaging.messages.processed")
                .description("Number of processed messages")
                .tag("destination", destination)
                .tag("outcome", outcome.tagValue())
                .register(registry)
                .increment();
    }

    enum MessageOutcome {
        SUCCESS("success"),
        REJECTED("rejected"),
        ERROR("error");

        private final String tagValue;

        MessageOutcome(String tagValue) {
            this.tagValue = tagValue;
        }

        String tagValue() {
            return tagValue;
        }
    }
}
~~~

This snippet uses the MetricDestination enum declared earlier. On every call, the incoming destination is mapped to a fixed set of values; outcome also has only three choices. User ID, message ID, and request ID never participate in the meter ID.

If you need to count errors by group, add an error_category enum tag with finite values. Never use exception messages as tags. Apply the same rules to Timers, since every tag combination still creates a separate meter.

## 7. Setting Guardrails with MeterFilter

Good label design is the first line of defense. You can add MeterFilter rules to cap the number of tag values or total registered meters.

Example:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;

public final class MetricsConfiguration {

    public static void configure(MeterRegistry registry) {
        registry.config()
                .meterFilter(
                        MeterFilter.maximumAllowableTags(
                                "messaging.messages",
                                "destination",
                                20,
                                MeterFilter.deny()))
                .meterFilter(
                        MeterFilter.maximumAllowableMetrics(10_000));
    }
}
~~~

Meaning:

- The first filter applies to meters whose names start with messaging.messages.
- For the destination tag key, at most 20 distinct values are allowed.
- Once exceeded, MeterFilter.deny() rejects registering new meters with values over the threshold.
- The second filter caps the total number of meters in the registry.

The numbers 20 and 10,000 are illustrative; choose values based on your system's series budget. maximumAllowableMetrics is a global circuit breaker that does not distinguish which metrics are more important. If set too low, critical meters may also be denied.

maximumAllowableTags does not automatically roll new values into other; with deny() it rejects meters past the limit. Therefore, normalize values before registering meters. Filters are a safety net for instrumentation bugs, not a substitute for schema design.

### 7.1. Dropping unsafe tags during a transition

Micrometer offers MeterFilter.ignoreTags(...) to strip tag keys from meters. It can be used temporarily when you need to stop a dangerous tag from being exported while fixing instrumentation call sites.

Example:

~~~java
registry.config().meterFilter(
        MeterFilter.ignoreTags(
                "userId",
                "user_id",
                "requestId",
                "sessionId"));
~~~

This filter has broad registry-wide scope; do not apply it carelessly if a legitimate meter needs that tag. Nor does it sanitize previously exported data or replace fixing/removing the source instrumentation. After deploying, verify the actual meter schema and dashboards that depend on tags.

## 8. Measuring Cardinality and Checking the Metric Schema

### 8.1. Pre-release checks

For each custom metric, write down a schema table:

| Metric | Tag key | Max value set | Source |
|---|---|---:|---|
| messaging.messages.processed | destination | 4 | Server enum |
| messaging.messages.processed | outcome | 3 | Server enum |
| messaging.messages.processed | protocol | 3 | Adapter config |
| messaging.process.duration | error_category | 5 | Fixed error categories |

From this, calculate the upper bound of combinations. If a tag's value set cannot be enumerated, that is a signal to revisit the design before release.

### 8.2. Unit tests ensuring no identifiers appear in meter tags

You can use SimpleMeterRegistry to inspect generated meters. Example:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MessagingMetricsTests {

    @Test
    void meterTagsDoNotContainUserOrRequestIdentifiers() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        MessagingMetrics metrics = new MessagingMetrics(registry);

        for (int i = 0; i < 1_000; i++) {
            metrics.recordProcessed(
                    "orders.create",
                    MessagingMetrics.MessageOutcome.SUCCESS);
        }

        assertFalse(registry.getMeters().isEmpty());

        assertTrue(registry.getMeters().stream().allMatch(meter -> {
            Meter.Id id = meter.getId();

            return id.getTag("userId") == null
                    && id.getTag("user_id") == null
                    && id.getTag("requestId") == null
                    && id.getTag("sessionId") == null;
        }));

        assertTrue(registry.getMeters().size() <= 2);
    }
}
~~~

This test invokes the same destination/outcome combination 1,000 times. The meter count stays bounded because tag values do not vary per call. Assertions verify that identifier keys do not appear in meter tags.

To also test unexpected input values, send many destinations outside the enum and verify they all map to other. The number of tag values still must not grow with the number of distinct input strings.

### 8.3. Monitoring cardinality at the backend

In Prometheus, you can query series counts by metric name, for example:

~~~promql
count by (__name__) ({__name__=~"messaging_.*"})
~~~

This query counts series for each matching metric name. Depending on the Prometheus version and registry naming conventions, exported metric names may differ from the original Micrometer names. Inspect actual metrics at the scrape endpoint before writing dashboards or alerts.

You can also track:

- New series created within a time window.
- Registered meters in each MeterRegistry.
- Number of meters denied by filters for exceeding limits.
- Tag value counts on key metrics.
- Query cost and latency in the monitoring backend.

Do not watch only total series count. A single surging metric can cause a cardinality explosion even before the global series count hits an alert threshold.

## 9. Logs, Traces, and Exemplars for Detailed Lookups

### 9.1. Structured logs

Structured logs are suited for investigating a specific processing event. You can record fields such as messageId, requestId, correlationId, or userId if policy permits and data handling is controlled.

Illustrative example:

~~~json
{
  "event": "message.processing.failed",
  "destination": "orders.create",
  "messageId": "msg-7f31",
  "requestId": "req-91a2",
  "userId": "user-204",
  "errorCategory": "business"
}
~~~

The identifier fields here enable searching for a specific event. They are not metric labels. Logging systems still require access controls, encryption, retention, and personal data redaction; do not log tokens, passwords, or sensitive contents purely for debugging convenience.

### 9.2. Distributed tracing

Traces link spans of the same request across multiple services. High-cardinality attributes can help locate a specific execution, though you must weigh storage cost, sampling, access permissions, and sensitive data.

A trace can include:

- Operation: orders.create.
- Protocol: rsocket.
- Destination: normalized route.
- Message ID: if needed to correlate with logs and permitted by policy.
- Pseudonymous user ID: only with valid investigative need and access controls.

Do not make traceId a metric tag. Trace IDs are generated uniquely per trace; placing them into metrics creates a new series for every trace.

### 9.3. Exemplars

An exemplar is a sample reference attached to a metric data point, commonly used to link metrics to traces. When supported by the backend and registry, operators can jump from an anomaly on a histogram or counter directly to a representative trace.

Exemplars enable detailed investigation without putting trace IDs into metric labelsets. Support and configuration depend on the registry, exporter, and backend; check the observability stack you are using.

## 10. Remediation Workflow When High-Cardinality Metrics Are Detected

When dashboards or backends show series counts climbing rapidly:

1. Identify which metric is producing the most series.
2. Inspect its tag keys and count distinct values per key.
3. Look for tags containing UUIDs, emails, IDs, timestamps, URLs, or free-form strings.
4. Locate where the tag is created: ObservationConvention, MeterFilter, Counter/Timer builder, interceptor, or library instrumentation.
5. Replace dynamic values with enums, route templates, or a bounded other bucket.
6. Move per-request lookup data to logs/traces under proper protection policies.
7. Add tests verifying tag schemas and confirming meter counts do not grow with user/request counts.
8. Deploy protective filters if needed, monitor denied meters, and update dashboards/alerts.
9. Verify the backend post-deployment; old time series may remain until their retention expires.

Do not just add MeterFilter.deny() and consider the problem solved. If a filter continually drops important meters, dashboards lose visibility while the app appears to run fine. Alert on denied meter counts and fix the source generating the tag.

## 11. Key Takeaways

- Every combination of metric name and labelset is a time series.
- Metric cardinality grows as the product of each tag key's value counts.
- User IDs, emails, session IDs, request IDs, trace IDs, and unique IDs do not belong in metric tags.
- Use route templates, enums, outcomes, and finite error categories to create analysis dimensions.
- Micrometer Observation sends low-cardinality key values to metrics and traces; high-cardinality key values go only to traces.
- High-cardinality data in traces still requires access control, retention limits, and personal data protection.
- MeterFilter.maximumAllowableTags and maximumAllowableMetrics are guardrails; they do not replace good label schemas.
- Use logs, traces, and exemplars to investigate individual requests; use metrics for aggregate trends and SLOs.
- Test meter tags and cardinality in CI to prevent dynamic IDs from slipping into instrumentation.

Good metric design preserves aggregability and comparability over time. When you need to trace a specific user or request, follow controlled logs/traces instead of turning every identifier into a time series.

## References

- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/1.13/observation/introduction.html)
- [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html)
- [MeterFilter — Micrometer 1.13 API](https://javadoc.io/doc/io.micrometer/micrometer-core/1.13.14/io/micrometer/core/instrument/config/MeterFilter.html)
- [Prometheus — Metric and Label Naming](https://prometheus.io/docs/practices/naming/)
- [Prometheus — Instrumentation Practices](https://prometheus.io/docs/practices/instrumentation/)
- [Prometheus — The Zen of Prometheus](https://prometheus.io/docs/practices/the_zen/)
