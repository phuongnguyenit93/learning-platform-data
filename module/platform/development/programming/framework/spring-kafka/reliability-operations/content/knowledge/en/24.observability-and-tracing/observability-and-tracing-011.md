# Do not put sensitive payloads into spans

In **Spring Kafka Reliability Operations**, **Observation and tracing** show how a Kafka event travels from producer, through a topic, into a listener, database, and downstream services. Yet every span opens a new data pipeline: the application ships telemetry to tracing exporters, collectors, backends, dashboards, and incident tooling. If spans contain **sensitive Kafka payloads**, business data is replicated into places that lack the same ACLs, retention, or access policies as Kafka and your database.

Core principle of this lesson: **a span describes an operation; a span is not a copy of the Kafka record**. To investigate throughput, retries, timeouts, or deadlocks, spans typically need only topic, operation, processing duration, outcome, error category, and retry stage—not emails, phone numbers, addresses, tokens, payment details, or raw JSON.

Protection must cover **span names, attributes, events, exception details, baggage, Kafka keys/values/headers, and downstream HTTP/DB spans**. Merely avoiding `setAttribute` with payloads is insufficient if another framework or library still emits exception messages containing raw data.

## 1. What parts does a span contain?

| Part | Useful operational example | Risk |
|---|---|---|
| Span name | `kafka receive`, `order.process` | Embedding emails or payloads in the name |
| Attributes | `messaging.system=kafka` | `record.value`, `customer.email` |
| Span events | `retry_scheduled`, `validation_failed` | Entire JSON payload in an event |
| Status | `ERROR` | Description carrying raw exception text |
| Exception event | `exception.type` | Stack/message containing tokens |
| Links | Connecting trace context between spans | Link attributes holding customer data |
| Baggage | Approved opaque correlation reference | JWT, phone, account ID |
| Resource attributes | `service.name`, `environment` | Secrets or tenant identities |

Trace exporters ship these fields out of process. Span events are not ephemeral logs that vanish: backends can persist and index them.

## 2. Why do Kafka payloads need a dedicated policy?

A Kafka record contains topic, partition, offset, timestamp, **key**, **value**, and **headers**.

- **Value** may be JSON, Avro, or Protobuf carrying PII, payment data, or business secrets.
- **Key** may be an email, phone number, or account ID.
- **Headers** may carry Authorization, cookies, baggage, or tenant/customer metadata.
- **Exceptions** during deserialization may contain raw bytes or partial payloads.
- **DLTs** may store failed records and failure metadata.
- **Logs** emitted by interceptors may print the entire `ConsumerRecord`.

**Unsafe** example:

~~~java
span.setAttribute("kafka.value", record.value().toString());
span.setAttribute("kafka.key", String.valueOf(record.key()));
span.setAttribute("kafka.headers", record.headers().toString());
~~~

`DTO.toString()` may be auto-generated and print every field. Header values and record keys must never be treated as public by default.

**Never put `record.key()`, `record.value()`, raw headers, or raw exception messages directly onto spans.**

## 3. How does data leave the application?

~~~mermaid
flowchart LR
    A["Kafka producer"] --> B["Kafka topic"]
    B --> C["Spring Kafka listener"]
    C --> D["Business processing"]
    C --> E["Micrometer Observation"]
    D --> E
    E --> F["Tracing exporter"]
    F --> G["OTel collector"]
    G --> H["Trace backend"]
    H --> I["Dashboard / support"]
~~~

A Kafka topic may be protected by ACLs and short retention. Yet a trace backend may allow broad engineering query access or be hosted by an external vendor. An attribute carrying payload **multiplies copies and increases who can access the data**.

Data minimization inside the application is the first line of defense. Encryption, collector redaction, RBAC, and retention are secondary layers—never replacements for not capturing payloads in the first place.

## 4. Classify data before adding attributes

| Data | Example | Policy |
|---|---|---|
| Messaging system | `kafka` | Allowed |
| Operation | `send`, `receive` | Allowed |
| Logical topic name | `orders.events` | Allowed if naming policy is clean |
| Consumer group | `order-service` | Check whether it contains tenant IDs |
| Partition | `2` | May be allowed |
| Offset | `104` | Weigh need, cardinality, and privacy |
| Fixed event type | `OrderCreated` | Allowlist only |
| Error category | `timeout`, `schema_validation` | Allowlist only |
| Retry stage | `original`, `retry`, `dlt` | Allowed |
| Customer details | Email, phone, address | Never record |
| Payment/health data | Card number, medical data | Never record |
| Message value | JSON/Avro/Protobuf payload | Never record |
| Raw message key | Email or user ID | Do not record by default |
| Raw Kafka headers | Authorization, JWT | Never copy |
| Exception message | May contain input | Only if strictly sanitized |

Even topic names can embed customer identifiers in dynamic-topic systems. Metadata also needs practical review with no automatic exemptions.

## 5. Low cardinality does not mean private

Micrometer Observation distinguishes **low-cardinality key values** suitable for metrics from **high-cardinality key values** normally exported only to tracing.

However, that distinction measures **value count**, not sensitivity:

- `event.type=OrderCreated` is usually low cardinality and may be approved.
- `customer.email` is high cardinality and **unsafe**, even when set via `highCardinalityKeyValue`.
- A sensitive enum can also be disallowed despite low cardinality.

Never treat high-cardinality as a safe zone for storing customer data. Those values can still be exported as span attributes.

## 6. Spring Kafka and Micrometer Observation

Key components involved:

- **`KafkaTemplate`** creates producer observations when enabled.
- **`MessageListenerContainer`** can create consumer/listener observations.
- **`ObservationRegistry`** manages observations.
- **`ObservationConvention`** defines names and key-values.
- **Micrometer Tracing / OpenTelemetry bridge** turns observations into spans.
- **OTLP exporter/collector** ships telemetry to the backend.

Example listener factory on a Spring Kafka version supporting observation:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
observedListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setObservationEnabled(true);

    return factory;
}
~~~

Producer:

~~~java
@Bean
KafkaTemplate<String, OrderEvent> observedKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory) {

    var template = new KafkaTemplate<>(producerFactory);
    template.setObservationEnabled(true);
    return template;
}
~~~

Spring Boot may auto-configure `KafkaTemplate` or listener factories. Do not declare duplicate beans without checking project configuration. Observation APIs and tracer/exporter wiring depend on your Spring Kafka/Boot version.

**Enabling observation never requires recording record values.** Metadata and timings usually suffice for diagnostics.

## 7. Why must custom instrumentation be audited?

Standard instrumentation may avoid copying payloads, yet custom code frequently leaks data:

- Custom `KafkaListenerObservationConvention` or `KafkaTemplateObservationConvention`.
- Business observations appending `event.toString()`.
- `ProducerInterceptor`/`ConsumerInterceptor` logging `ConsumerRecord`.
- Exception recording carrying raw input.
- Database spans containing SQL literal values.
- HTTP spans containing raw URLs/queries.
- OpenTelemetry Java agent running with different configuration.
- Collector processors or exporters injecting extra attributes.

Review **the entire span export path**, not just a single listener. A clean Kafka span does not prove the whole trace is safe.

## 8. Allowlist attributes instead of denylisting

An observability schema may allow:

| Attribute | Example value | Purpose |
|---|---|---|
| `messaging.system` | `kafka` | System type |
| `messaging.operation` | `send` / `receive` | Operation kind |
| `messaging.destination.name` | `orders.events` | Topic |
| `event.type` | `OrderCreated` | Classification |
| `processing.outcome` | `success` / `failed` | Result |
| `retry.stage` | `original` / `retry` / `dlt` | Recovery |
| `error.kind` | `timeout` / `db_deadlock` | Error classification |
| `schema.version` | `3` | Schema migration |
| `component` | `order-projector` | Processing unit |

Attribute names are examples combining semantic conventions and application-defined tags; OpenTelemetry standard names can vary by version.

Exclude:

~~~text
record.value
record.key
full.kafka.headers
customer.email
customer.phone
http.request.body
request.authorization
payment.card_number
exception.raw_input
db.bound_parameter
~~~

Every approved attribute should have an owner, purpose, format, length/cardinality cap, and tests. Never add a field just because it exists on a DTO.

## 9. Event types must be normalized

An untrusted producer could send an `event.type` containing an email or secret. Never record that value verbatim.

~~~java
import java.util.Set;

public final class SafeTraceTags {

    private static final Set<String> TYPES =
        Set.of("OrderCreated", "OrderUpdated", "OrderCancelled");

    private SafeTraceTags() {
    }

    public static String eventType(String candidate) {
        if (candidate != null && TYPES.contains(candidate)) {
            return candidate;
        }
        return "other";
    }
}
~~~

This function returns only approved enum-like values. Use the same pattern for retry stage, processing outcome, and error category.

Simply truncating strings to 100 characters is not redaction: 100 characters is plenty to expose a token.

## 10. Safe business observations

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class ObservedOrderProcessor {

    private final ObservationRegistry registry;
    private final OrderService service;

    public ObservedOrderProcessor(
            ObservationRegistry registry,
            OrderService service) {
        this.registry = registry;
        this.service = service;
    }

    public void process(OrderEvent event) {

        String type = SafeTraceTags.eventType(event.type());

        Observation.createNotStarted("orders.process", registry)
            .lowCardinalityKeyValue("event.type", type)
            .lowCardinalityKeyValue("component", "orders")
            .observe(() -> service.apply(event));
    }
}
~~~

`OrderEvent` and `OrderService` are illustrative domain classes. This code adds no keys, values, or raw headers. When the listener already has a default observation, create a business child observation only if it provides clear diagnostic value, avoiding unnecessary duplicate spans.

Continue auditing **exception recording**: handlers/exporters may record exception messages from callbacks depending on instrumentation.

## 11. Bad example: POJO.toString() on the current span

~~~java
@KafkaListener(topics = "orders.events")
public void handle(OrderEvent event) {

    Observation current = Observation.currentObservation();

    if (current != null) {
        current.highCardinalityKeyValue(
            "record.value",
            event.toString()
        );
    }

    orderService.apply(event);
}
~~~

This is risky because `toString()` may print addresses, names, phone numbers, or tokens. `highCardinalityKeyValue` is not a masking tool.

Safe alternative:

~~~java
@KafkaListener(topics = "orders.events")
public void handle(OrderEvent event) {

    Observation current = Observation.currentObservation();

    if (current != null) {
        current.lowCardinalityKeyValue(
            "event.type",
            SafeTraceTags.eventType(event.type())
        );
    }

    orderService.apply(event);
}
~~~

This example applies only when an observation context is active. In larger systems, a centralized instrumentation policy is easier to audit than letting each listener invent attributes.

## 12. Span names must remain stable

Good span names:

~~~text
kafka receive
kafka send
order.process
inventory.reserve
payment.authorize
~~~

Bad span names:

~~~text
process order customer@example.invalid
receive user-123456
handle token=TEST_SECRET
~~~

Never concatenate raw customer IDs, Kafka keys, URL query strings, payloads, or exception messages into span names. Backends heavily index span names, compounding both exposure risk and cardinality.

## 13. Span events can also leak data

Events such as `validation_failed`, `retry_scheduled`, or `db_commit_completed` help trace analysis. Never put raw values into events:

~~~java
// Unsafe:
span.addEvent("invalid_record=" + record.value());
~~~

Replace with a fixed event name and classified attributes:

~~~text
event: validation_failed
error.kind: schema_validation
retry.stage: original
schema.version: 3
~~~

Span events are not ephemeral in-JVM breadcrumbs. Exporters can ship them and backends can store them.

## 14. Exception messages are a leak vector

An exception can contain JSON input or SQL parameters:

~~~text
Failed to deserialize:
{"email":"canary@example.invalid","token":"TEST_SECRET"}
~~~

A tracing handler/SDK may record exception messages, stack traces, or status descriptions. Therefore, do not audit only custom attributes.

Recommendations:

1. Use **exception class** and **`error.kind`** instead of raw messages.
2. Never build custom exception messages by concatenating raw payloads.
3. Never call `recordException` on sensitive exceptions without a sanitization policy.
4. Inspect the exact fields your exporter produces from exceptions.
5. Audit your logging pipeline too.
6. When forensics are needed, use a DLT/quarantine with ACLs and retention.

Safe domain exception example:

~~~java
public class InvalidOrderSchemaException
        extends RuntimeException {

    public InvalidOrderSchemaException() {
        super("INVALID_ORDER_SCHEMA");
    }
}
~~~

Do not assume all exceptions are safe simply because your custom exception message is standardized. Third-party library exceptions often embed raw inputs into their messages.

## 15. Error classification table

| `error.kind` | Meaning |
|---|---|
| `deserialization` | Unable to decode message |
| `schema_validation` | Invalid against schema |
| `dependency_timeout` | API or DB timeout |
| `db_deadlock` | Database deadlock |
| `authorization` | Insufficient permissions |
| `transient_broker` | Temporary broker/network fault |
| `business_rejected` | Domain rule rejection |
| `unknown` | Unclassified |

Record only allowlisted values. Never assign `exception.getMessage()` to `error.kind` even if it currently looks free of PII.

## 16. Never copy all Kafka headers

Unsafe example:

~~~java
for (Header header : record.headers()) {
    observation.highCardinalityKeyValue(
        "header." + header.key(),
        new String(header.value(), StandardCharsets.UTF_8)
    );
}
~~~

Headers may carry `Authorization`, `X-User`, tenant identities, JWTs, or baggage. Even header names can be controlled by the producer.

Proper approach:

- Never copy all headers into attributes.
- Let the framework manage trace propagation.
- Read only allowlisted headers for business processing.
- Keep raw customer/tenant identifiers out of tracing.
- Enforce trust boundaries when Kafka accepts messages from external producers.

## 17. Traceparent, tracestate, and baggage

Kafka tracing may propagate context via headers:

- **`traceparent`** for trace/span identity.
- **`tracestate`** for W3C vendor extensions.
- **baggage** for key/values propagated across services.

**Baggage is not a user data store.** Never put emails, account numbers, customer names, JWTs, or payloads into baggage.

Baggage can propagate from Kafka into HTTP and across many downstream services. Some instrumentation may log or record baggage. Even if the current tracing backend drops baggage, data has already crossed security boundaries.

Trace context links spans—it does not authenticate identities or grant permissions.

## 18. Safe Correlation IDs

When locating a workflow, use a policy-approved **opaque operation ID** rather than an email or customer ID.

One design:

1. Generate a random opaque ID at the entry point.
2. Keep the mapping from ID to business entity inside an ACL-protected database.
3. Put the ID into tracing only with privacy owner approval.
4. Limit retention and reverse-lookup permissions.
5. Never derive the ID directly from PII.
6. Never use trace ID as an authorization credential.

Even a UUID can be an indirect identifier if it links directly to a customer profile, so never assume every opaque ID is public.

## 19. Hashing PII does not automatically make data safe

Hashing an email or phone number and attaching it to spans still carries risks:

- Email/phone spaces can be guessed via dictionary attacks.
- Deterministic hashes allow linking multiple traces for the same person.
- Hashed identifiers may still count as personal data under policy.
- Multiple systems using the same hash enable unintended correlation.

If pseudonymization is mandatory, consider HMAC with securely managed secrets, key rotation, clear purpose, and a security review. Better yet, keep customer-level identifiers off spans whenever not strictly required.

## 20. Sampling is not a privacy mechanism

Example:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

10% sampling reduces stored traces, yet every sampled trace still exposes any captured payload. Tail sampling may also receive and buffer spans at the collector before deciding to keep or drop them.

Never use low sampling as an excuse to record sensitive data. The right priority order is **never capture at source → redaction/allowlist → exporter protection → sampling per operational need**.

## 21. Collector redaction is a second layer

An OpenTelemetry Collector can apply processors or policies to scrub attributes. However:

- Data has already left the application before reaching the collector.
- The collector may buffer or log data.
- Config may drift across environments.
- Raw data may sit inside span events or exception fields.
- Another exporter may bypass the intended processor.
- Newly added attributes may miss the denylist.

~~~mermaid
flowchart LR
    A["Kafka record"] --> B["Application allowlist"]
    B --> C["Observation / spans"]
    C --> D["Exporter"]
    D --> E["Collector redaction"]
    E --> F["Backend RBAC + retention"]
~~~

**Application-side allowlisting is the primary control; collector redaction is defense in depth.**

## 22. Producer spans need the same protection as consumer spans

A producer could record payloads when calling `KafkaTemplate.send`:

~~~java
// Unsafe:
observation.highCardinalityKeyValue(
    "producer.payload",
    orderCreated.toString()
);
~~~

Replace with operation and metadata:

~~~text
messaging.system = kafka
messaging.operation = send
messaging.destination.name = orders.created
event.type = OrderCreated
~~~

When the producer uses Kafka transactions, a successful send future does not prove the Kafka transaction committed. Never set `processing.outcome=committed` merely because `send()` was invoked. Tracing outcomes must reflect actual lifecycle states.

## 23. Deserialization failures and DLT

With `ErrorHandlingDeserializer` or similar deserialization failure paths, exceptions/headers may carry raw bytes of the failing record.

- Record `error.kind=deserialization`.
- Record topic/partition/offset if approved.
- Never put raw bytes/Base64 onto spans.
- Never copy exception headers onto spans.
- Use an ACL-protected DLT/quarantine if failed records must be kept.
- Apply dedicated retention/masking to DLTs and replay tools.

Base64 is not security encryption.

When a record passes through retry/DLT, do not create multiple payload copies on spans of the main, retry, and DLT listeners. Use only retry stage, attempt category, and error kind.

## 24. Kafka transactions and recovery

A transactional pipeline may emit spans for consume, produce, commit/abort, and `AfterRollbackProcessor`. These spans are valuable when investigating exactly-once failures:

| Attribute | Example |
|---|---|
| `transaction.outcome` | `committed` / `aborted` / `unknown` |
| `retry.stage` | `original` / `retry` |
| `processing.outcome` | `failure` |
| `error.kind` | `dependency_timeout` |
| `messaging.destination.name` | `orders.events` |

Never attach payloads or keys "to make it obvious which transaction aborted." If needed, use the trace ID and approved topic/partition/offset to look up data in controlled Kafka/DLT storage.

A transaction abort does not grant permission to dump raw failed records into telemetry.

## 25. HTTP and database spans must stay clean too

A Kafka consumer often calls databases or REST APIs. Downstream spans can leak data even when Kafka spans are clean.

Avoid:

~~~java
String sql =
    "SELECT * FROM customers WHERE email='" + email + "'";

span.setAttribute("db.statement", sql);
~~~

Use parameterized SQL and avoid capturing bound values. When query text is needed, use operation names or properly normalized statements.

HTTP tracing should use route templates:

~~~text
Safe:   GET /customers/{customerId}/orders
Unsafe: GET /customers/canary@example.invalid/orders?token=TEST_SECRET
~~~

Never record `Authorization`, cookies, request/response bodies, or raw query parameters on spans.

## 26. Multi-tenant metadata can be sensitive

In multi-tenant Kafka, topic or group names can embed tenant identities:

~~~text
tenant-123.orders
orders-customer-name
~~~

Never assume `topic.name`, `consumer.group`, or `tenant.tier` are always public. Use logical classifications like `workload=order-processing` and `topic.family=orders` per policy.

When multiple tenants access the same tracing backend, data minimization matters even more. Never let trace attributes disclose another tenant's data.

## 27. Centralized tagging policy

Use a centralized helper or custom `ObservationConvention`:

~~~java
import java.util.Map;
import java.util.Set;

public final class KafkaTraceTagPolicy {

    private static final Set<String> ALLOWED =
        Set.of("OrderCreated", "OrderUpdated", "OrderCancelled");

    private KafkaTraceTagPolicy() {
    }

    public static Map<String, String> safeTags(
            String type,
            boolean isRetry) {

        String safeType =
            type != null && ALLOWED.contains(type)
                ? type
                : "other";

        return Map.of(
            "event.type", safeType,
            "retry.stage", isRetry ? "retry" : "original"
        );
    }
}
~~~

Spring Kafka provides `KafkaListenerObservationConvention` and `KafkaTemplateObservationConvention` in versions supporting customization. When implementing them, return `KeyValues` only from an allowlist; never iterate across all of `record.value()` or headers.

A helper alone cannot block every instrumentation path: review the Micrometer bridge, OpenTelemetry agent, and backend configs as well.

## 28. Unit testing helpers with JUnit

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class SafeTraceTagsTest {

    @Test
    void untrustedValueMustNotAppear() {

        String input = "OrderCreated token=TEST_SECRET";
        String result = SafeTraceTags.eventType(input);

        assertThat(result).isEqualTo("other");
        assertThat(result).doesNotContain("TEST_SECRET");
    }

    @Test
    void knownTypeIsAllowed() {
        assertThat(
            SafeTraceTags.eventType("OrderCreated")
        ).isEqualTo("OrderCreated");
    }
}
~~~

Use synthetic test data, never real secrets. Testing the helper is necessary yet insufficient because exception handlers or agents can attach attributes on other paths.

## 29. Integration testing with the exporter

A critical test must inspect **the final exported span data** using an in-memory span exporter or fake OTLP collector:

1. Create a Kafka record with a canary email, token, and fake nested private field.
2. Process it successfully with a Spring Kafka listener.
3. Capture producer, consumer, and business spans.
4. Inspect names, attributes, events, exception fields, and status descriptions.
5. Assert none contain canary values or raw JSON.
6. Assert approved attributes are still present.
7. Trigger an exception containing a canary string.
8. Test deserialization failures, retry topics, and DLT.
9. Test keys/headers containing synthetic sensitive values.
10. Test downstream HTTP/DB spans.
11. Repeat whenever upgrading Micrometer, Spring Kafka, or the OpenTelemetry agent.

Do not inspect only `ObservationRegistry` before export; the tracing bridge/SDK can append data afterward.

## 30. Canary test payload

~~~json
{
  "eventType": "OrderCreated",
  "eventId": "test-event-001",
  "customer": {
    "email": "canary-person@example.invalid",
    "address": "PRIVATE_CANARY_ADDRESS"
  },
  "credential": {
    "token": "TEST_SECRET_DO_NOT_EXPORT"
  }
}
~~~

All values are synthetic. Exporter tests scan for canary strings across span attributes, events, statuses, and exception details. Where applicable, also check encoded forms such as Base64 or URL encoding.

Canary scanning does not replace allowlisting: the policy must remain never adding raw payloads to spans in the first place.

## 31. Investigating incidents without payloads in traces

When a record fails:

1. Use the trace ID to locate the service and listener.
2. Check topic/partition/offset if permitted by policy.
3. Inspect `event.type`, `schema.version`, and `retry.stage`.
4. Inspect `error.kind` and latency.
5. Check consumer lag, transaction commits/aborts, and DLT.
6. If raw payloads are needed, use ACL-protected, audited, masked Kafka/DLT/quarantine tools.
7. Reconcile business state in the database within granted permissions.
8. Never copy payloads into spans, shared tickets, or logs for query convenience.

Tracing is meant to **point to where to investigate**, not turn the tracing backend into a business data warehouse.

## 32. Protecting exporters and backends

A production system needs:

- TLS and authentication for exporters/collectors.
- Network policies and approved endpoints.
- RBAC on the trace backend.
- Tenant isolation.
- Bounded retention.
- Access/export auditing.
- Controls on debug exporters and collector logs.
- Policies governing pasting traces into chats, tickets, or dashboards.
- Purge/delete procedures when leaks occur.
- Secret rotation if tokens leak.

Even payload-free traces reveal operational and architectural details that require protection.

## 33. Runbook when sensitive data is found in spans

1. Identify the leaking field and data classification.
2. Trace the instrumentation path: Kafka listener, producer, business observation, exception, baggage, or HTTP/DB.
3. Stop capture at the source; consider throttling/blocking the exporter per incident policy.
4. Identify all collectors and backends that received the data.
5. Restrict access to affected traces.
6. Search for copies in logs, dashboards, alerts, tickets, or screenshots.
7. Purge data per backend capabilities and security procedures.
8. Rotate/revoke secrets if tokens were exposed.
9. Notify security/privacy owners per incident severity.
10. Add a canary regression test.
11. Deploy the fix and verify newly emitted spans.
12. Record an audit trail and preventive controls.

Merely hiding an attribute in the UI does not delete data already stored in the backend or downstream exports.

## 34. Common anti-patterns

**Writing `DTO.toString()` onto spans.** Can expose full PII.

**Putting `record.key()` into `highCardinalityKeyValue`.** Keys may be account IDs or emails.

**Copying Kafka headers as attributes.** Headers may hold secrets and baggage.

**Putting customer IDs into span names.** Leaks data and explodes cardinality.

**Recording `exception.getMessage()` unchecked.** May contain raw payloads, SQL, or URLs.

**Using low sampling as a privacy measure.** Sampled traces still leak.

**Relying solely on a collector denylist.** Data has already left the application, and new fields slip through.

**Hashing emails and calling them anonymous.** Hashes can be guessed and correlated.

**Storing failed payloads in a DLT and copying them onto spans too.** Multiplies uncontrolled copies.

**Auditing only Kafka spans.** DB/HTTP spans in the same trace can still leak.

**Treating the tracing backend as a secure business audit store.** Tracing has different retention, access, and purpose.

## 35. Pre-production checklist

**Policy**

- [ ] Keys/values/headers and exception messages are classified.
- [ ] No payloads appear in span names, attributes, or events.
- [ ] Untrusted headers or baggage are never copied.
- [ ] Event types and `error.kind` use allowlists.
- [ ] High cardinality is never treated as privacy-safe.
- [ ] Correlation IDs never directly embed PII.

**Spring Kafka / Micrometer**

- [ ] Observation is enabled intentionally.
- [ ] Custom conventions are reviewed.
- [ ] Business spans never call `DTO.toString()`.
- [ ] Exception capture is audited.
- [ ] Retry/DLT/deserialization paths do not leak.
- [ ] HTTP/DB spans obey the same policy.

**Telemetry**

- [ ] Exporters/collectors use TLS/authentication.
- [ ] Collector redaction acts as defense in depth.
- [ ] Backend enforces RBAC, auditing, and retention.
- [ ] Sampling is not used as a privacy control.
- [ ] Incident playbook exists.

**Testing**

- [ ] Unit tests cover allowlists.
- [ ] Integration tests verify exporter output.
- [ ] Canary data tested in keys, values, headers, and exceptions.
- [ ] Tested success, error, retry, and DLT paths.
- [ ] Regression tests run after upgrading dependencies/agents.

## 36. Conclusion

**Keeping sensitive payloads out of spans** is a core design principle when using Observation and distributed tracing in Spring Kafka. A useful trace describes topic, operation, approved event type, retry stage, error category, and processing duration without containing message values, customer identifiers, or secrets.

Govern **Kafka keys/values/headers, span attributes/events, exception details, baggage, and downstream HTTP/DB spans** together. Enforce allowlists at the source, apply collector redaction and backend RBAC as defense in depth, and verify exported spans with canary tests. Sampling optimizes telemetry cost—it is never a payload-hiding mechanism.

When raw records are needed for debugging, use authorized Kafka/DLT/quarantine and business audit tooling rather than pushing data into tracing. That keeps production reliability observable while protecting sensitive data.
