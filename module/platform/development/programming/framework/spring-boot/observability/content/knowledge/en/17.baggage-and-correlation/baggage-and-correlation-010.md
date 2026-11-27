# Protecting Baggage Data in Distributed Tracing

In a multi-service Spring Boot system, **baggage** carries selected contextual information across processing boundaries so downstream services can read it. For example, `orders.channel=web` can help distinguish web and batch flows in logs. However, baggage can also become an unintended data broadcast channel: a client sends an arbitrary header, a service trusts that value, an HTTP client automatically forwards it across multiple services, and eventually that metadata lands in logs or the trace backend.

Therefore, the question is not merely "can baggage propagate?" but **"which data is permitted to propagate, who is allowed to set it, which services may read it, and which systems can store it?"** Baggage must be governed like data crossing multiple trust boundaries, with an allowlist policy, source verification, value normalization, size limits, and per-sink usage rules.

This lesson belongs to the **Baggage and Correlation** chapter, focusing on **Protecting Baggage Data** in the **SPRING_BOOT_OBSERVABILITY** module. The content situates baggage within overall Spring Boot observability using Micrometer Observation, metrics, logs, and distributed tracing; emphasizing propagation, span attributes, cardinality, exporters, and troubleshooting incidents without exposing sensitive data.

## Learning Objectives

After this lesson, you will be able to:

1. Identify risks when baggage travels across HTTP, messaging, proxies, and downstream services.
2. Distinguish trace identity data, baggage, span attributes, log fields, and metric labels.
3. Design allowlists by data source, trust boundary, usage permission, and lifetime.
4. Validate, normalize, reject, or strip invalid baggage right at the trust boundary.
5. Limit baggage size and handle headers within client, proxy, gateway, and server limits.
6. Configure Spring Boot/Micrometer Tracing to propagate and correlate only approved fields.
7. Test spoofing, PII, secrets, oversized headers, async context, and log leakage scenarios.
8. Investigate data exposure or broken baggage propagation while preserving the ability to correlate metrics, logs, and traces.

## 1. Why Is Baggage a Security Boundary?

W3C Baggage defines the `baggage` header to carry key-value pairs during trace context propagation. Example:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
baggage: orders.channel=web,deployment.region=ap-southeast
~~~

Headers can be injected into HTTP requests by instrumentation. When a receiving service extracts context, values can enter current baggage and continue propagating downstream if configuration permits.

This helps correlation, yet creates a **data movement path**:

~~~mermaid
flowchart LR
    Client["Client / upstream"] --> Gateway["API gateway"]
    Gateway --> A["order-service"]
    A --> B["inventory-service"]
    B --> C["payment-service"]
    A --> Collector["OTel Collector"]
    B --> Collector
    C --> Collector
    Collector --> Backend["Trace backend"]
    A --> Logs["Log backend"]
    B --> Logs
    C --> Logs
~~~

A baggage field can appear across multiple hops, logs, spans, or telemetry systems. If values are uncontrolled, **every downstream service can become another point of data dissemination**.

### 1.1. Risk Categories

| Risk | Example | Consequence |
| --- | --- | --- |
| **PII leakage** | Email, phone number, address | Personal data spreads into logs/traces across multiple systems |
| **Secret leakage** | Access token, cookie, API key | Anyone with telemetry read access can obtain credentials |
| **Header injection/spoofing** | Client sends `tenant.tier=premium` | Downstream trusts externally controlled metadata |
| **Cross-tenant contamination** | Prior request's baggage stays in thread context | Tenant A's data appears in Tenant B's processing |
| **Header amplification** | Each service appends more key-values | Requests hit header limits or raise network overhead |
| **Cardinality explosion** | Request ID or customer ID becomes span/log/metric field | Increases indexing costs and metric series |
| **Untrusted control data** | Baggage alters retries, routing, or access control | Behavioral distortion and potential logic flaws |
| **Retention expansion** | Metadata exported to multiple backends | Expands storage, access control, and deletion scope |

### 1.2. Baggage Is Not a Security Channel

Baggage is metadata for context propagation, **not an authentication or authorization mechanism**. A `tenant.id` or `tenant.tier` value in a header does not prove the request genuinely belongs to that tenant. Likewise, `user.role=admin` sent by a client cannot be used to grant privileges.

If a decision affects authorization, financial data, pricing, tenant isolation, or resource access, the application must pull information from an authoritative source (authenticated principal, verified token, database, or policy service) and check it independently. Baggage may only carry a copy of verified context for correlation, never act as the source of truth.

## 2. Classifying Data Before Putting It into Baggage

Before adding a field, determine which category the value belongs to and which boundaries it is allowed to cross.

| Data category | Example | Default stance |
| --- | --- | --- |
| Low-sensitivity technical context | `orders.channel=web`, `workflow.name=order-create` | Can allow if downstream needs it |
| Deployment metadata | `deployment.region=ap-southeast` | Can allow, using normalized value set |
| Business grouping | `experiment.variant=control` | Only when approved and reveals no sensitive info |
| Pseudonymous identifier | Random internal correlation code | Weigh necessity, lifetime, and re-identification risk |
| PII | Email, phone, name, address | Do not propagate by default |
| Secrets/credentials | Passwords, bearer tokens, cookies, API keys | Never put into baggage |
| Business payload | JSON body, item list, payment details | Never use baggage |
| Security decision | Role, permission, tenant privilege from client | Never trust and never use for authorization |

### 2.1. Use Data with a Finite Value Set

A field like `orders.channel` should have a defined set of values, such as `web`, `batch`, or `partner`. Never take arbitrary strings from HTTP headers and write them straight into baggage. Normalization helps:

- prevent values containing PII or payloads from entering context;
- prevent one field from spawning unbounded variants due to casing or whitespace differences;
- constrain header size;
- provide a foundation for aggregatable logs and metrics.

### 2.2. Pseudonymous Identifiers Can Still Be Sensitive Data

A UUID without a username can still link back to a specific database record or customer profile. If the organization can reverse-link it, that value still needs to be governed under the corresponding data policy. "Hashed" or "encrypted" does not automatically make data anonymous; stable values can be correlated across many traces and systems.

### 2.3. Never Put Request Bodies into Baggage

Baggage suits a handful of short key-value pairs. Request bodies can hold payment details, addresses, personal notes, or large data. Stuffing bodies or arbitrary JSON into baggage both bloats headers and multiplies storage scope. When payload inspection is needed, use synthetic test data or controlled business storage mechanisms; never turn telemetry into a payload store.

## 3. Trust Boundaries and Data Provenance

Not all received baggage carries the same level of trust. A field created inside a service after authentication has a different provenance from a field sent directly by an Internet client.

~~~mermaid
flowchart TD
    External["External client<br/>untrusted headers"] --> Gateway["API Gateway / ingress"]
    Gateway --> Strip["Strip disallowed<br/>baggage keys"]
    Strip --> Authenticate["Authenticate + authorize"]
    Authenticate --> Normalize["Create context from trusted source"]
    Normalize --> Order["order-service"]
    Order --> Downstream["Downstream services<br/>propagate allowlist only"]
    Downstream --> Telemetry["Logs / traces / backend"]
~~~

### 3.1. Rules at Ingress

At external entry points:

1. Define which baggage fields are permitted from agreed partners; distrust undeclared fields by default.
2. Strip or overwrite client-supplied values if they collide with internal fields.
3. Authenticate and authorize requests as normal.
4. Create baggage from verified, normalized data; e.g., derive channel from the route, API credentials, or integration config.
5. Propagate only approved fields downstream.

For instance, a client sending `orders.channel=internal` does not mean the request is an internal flow. The application should determine channel from the caller contract itself.

### 3.2. Distinguishing External Context from Internal Context

In systems with multiple partners, certain public fields may be accepted, yet you must specify which source may set which field, what values are valid, and which services may trust it. There is no "internal so implicitly trusted" rule merely because a request arrives from a private subnet; credentials/service identity and trust relationships must still be authenticated.

A policy should specify at least:

| Policy attribute | Question |
| --- | --- |
| Key | Which field is allowed? |
| Owner/source | Who may create or update it? |
| Allowed values | Which set of values is accepted? |
| Trust level | Is the data verified or merely caller-supplied? |
| Propagation scope | Across which services/regions? |
| Sinks | Permitted in spans, logs, or metrics? |
| Retention | How long stored in backends? |
| Removal | Where is it dropped when wrong, expired, or during an incident? |

### 3.3. Do Not Use Baggage to Carry Authorization

Do not design:

~~~http
baggage: user.role=admin,tenant.access=all
~~~

for downstream to make permission decisions. If a service wants to avoid repeated authentication, use identity propagation and token/delegation mechanisms engineered for security, with proper signatures, audience, expiry, and policy. Baggage provides none of those guarantees.

## 4. Allowlisting, Validation, and Normalization

A safe policy should be **deny by default**: fields absent from the allowlist are not propagated. Avoid "allow everything except a few bad keys" because enumerating all sensitive data is always incomplete.

Allowlist example:

| Key | Allowed values | Source | Propagated? | Logged? |
| --- | --- | --- | --- | --- |
| `orders.channel` | `web`, `batch`, `partner` | Gateway post-auth | Yes | Yes |
| `deployment.region` | Deployment region set | Runtime config | Yes | Yes |
| `experiment.variant` | `control`, `treatment` | Experiment assignment service | Yes, if approved | Conditional |
| `customer.email` | Not applicable | Rejected | No | No |
| `authorization` | Not applicable | Security layer | No | No |
| `request.body` | Not applicable | Request payload | No | No |

### 4.1. Example Validator for Channel

A small Java validator can turn untrusted input into a valid value set:

~~~java
package com.example.orders.tracing;

import java.util.Locale;
import java.util.Set;

public final class BaggageValuePolicy {
    private static final Set<String> ALLOWED_CHANNELS =
            Set.of("web", "batch", "partner");

    private BaggageValuePolicy() {
    }

    public static String normalizeChannel(String candidate) {
        if (candidate == null || candidate.isBlank()) {
            return "unknown";
        }

        String normalized = candidate.trim().toLowerCase(Locale.ROOT);
        if (!ALLOWED_CHANNELS.contains(normalized)) {
            return "unknown";
        }
        return normalized;
    }
}
~~~

Never put invalid raw input strings into baggage for "easier debugging." The value `unknown` has a finite set and leaks no input. If you need to investigate offending requests, emit **a sanitized security event** per policy rather than echoing raw headers.

### 4.2. Do Not Check Only Key Names

Key allowlisting is necessary but insufficient. Values must also:

- be bounded in length;
- be normalized by fixed rules;
- belong to an approved value set or defined format;
- contain no control characters or log-injection strings;
- contain no sensitive data;
- not inflate cardinality unexpectedly.

For example, `orders.channel` has an allowlisted key, yet accepting any string from callers would let an attacker send an email or long random string, inflating header size and log volume.

### 4.3. Controlling W3C Baggage Metadata

W3C Baggage permits members to carry attached metadata. Do not assume such metadata fields are handled uniformly across every service, proxy, or backend. If the system lacks a concrete use case, **do not use arbitrary metadata**. Account for keys, values, and metadata within your total size budget and policy; never treat metadata as a place to hide secrets.

## 5. Limiting Size and Preventing Header Amplification

Baggage is serialized into an HTTP header, so it is subject to limits of:

- HTTP clients;
- API gateways/ingress;
- reverse proxies/load balancers;
- HTTP servers/containers;
- service meshes or sidecars;
- subsequent hops.

An upstream permitting large headers does not mean every downstream accepts the same size. When baggage is too large, requests can be rejected (e.g., 400, 413, or 431 depending on the component), stripped, or fail with errors.

### 5.1. Baggage Budget

Define an organization/application-level budget instead of relying on the highest limit of a single proxy:

| Rule | Internal policy example |
| --- | --- |
| Number of members | Only a few approved fields |
| Key length | Short and namespaced |
| Value length | A few dozen characters for classification fields |
| Total header size | Below the lowest limit in the gateway/client/server chain |
| Character set | Per W3C Baggage and application contract |
| Metadata | Disabled or restricted to specific keys |
| Repeated fields | Normalized and deduplicated per policy |

Concrete numbers depend on your environment; the table above states principles, not mandatory spec limits. **Do not set max-size equal to the gateway's ceiling**, because headers also carry `traceparent`, cookies, authentication, and other headers.

### 5.2. Never Concatenate Headers Manually

Do not do this:

~~~java
request.header("baggage",
        request.getHeader("baggage") + ",orders.channel=web");
~~~

This can create duplicate keys, broken encoding, retained untrusted fields, and header size overflows. Use your tracing stack's baggage/propagator APIs, inject only allowlisted fields, and enforce policy at trust boundaries.

### 5.3. Handling Invalid Fields

When incoming baggage is invalid:

1. Never propagate the raw value verbatim.
2. Strip the offending field or replace it with a normalized value if the use case allows.
3. Never log the raw value.
4. Record an aggregated drop counter if monitoring is needed, using a small-cardinality reason label.
5. On security policy violations, emit a safe audit event in the appropriate place.

Rejecting the entire business request is not always necessary just because an optional baggage field is malformed. Request rejection decisions must follow API/security contracts, not observability convenience alone.

## 6. Controlled Spring Boot/Micrometer Tracing Configuration

With Spring Boot 3.x and a matching Micrometer Tracing bridge, illustrative dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Versions should be managed via the Spring Boot BOM. Baggage configuration is part of tracing integration, not a Prometheus registry setting.

### 6.1. Declaring Fields Permitted to Propagate and Log-Correlate

Example `application.yml`:

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    baggage:
      remote-fields:
        - orders.channel
        - deployment.region
      correlation:
        fields:
          - orders.channel
          - deployment.region
    sampling:
      probability: 0.1
~~~

Meaning:

- `remote-fields` is the group of fields configured for propagation across service boundaries via the matching Spring Boot integration.
- `correlation.fields` is the group of fields used for log correlation/MDC when logging integration supports it.
- Sampling determines the fraction of traces recorded; **it is not a baggage data filter**.

Review the two lists independently. A field can be propagated without being logged; a field correlated in local logs does not automatically need to be sent across every service. Never add `customer.email` or `authorization` to either list.

Properties may vary by Spring Boot/Micrometer version. Before upgrading, verify property binding and test output on the exact version in use.

### 6.2. Creating Baggage After Data Verification

Example of a service receiving `channel` from an authoritative source and normalizing it:

~~~java
package com.example.orders.tracing;

import io.micrometer.tracing.BaggageInScope;
import io.micrometer.tracing.Tracer;
import org.springframework.stereotype.Service;

@Service
public class OrderContextService {
    private final Tracer tracer;

    public OrderContextService(Tracer tracer) {
        this.tracer = tracer;
    }

    public void process(String verifiedChannel) {
        String channel =
                BaggageValuePolicy.normalizeChannel(verifiedChannel);

        try (BaggageInScope ignored =
                     tracer.createBaggageInScope("orders.channel", channel)) {
            processOrder();
        }
    }

    private void processOrder() {
        // Call appropriately instrumented downstream.
    }
}
~~~

The security hinge lies in the **origin of `verifiedChannel`**: it must come from an authenticated context or server-side routing/configuration, not an unverified raw `baggage` header. Closing the scope when processing finishes prevents values from staying active on reused threads.

### 6.3. Do Not Read Baggage for Authorization

A service may read `orders.channel` to add a log field or pick a dashboard filter. Never read `tenant.role` or `user.permission` from baggage to decide whether an API call is allowed. Security decisions must rely on a verifiable principal/authorization context.

### 6.4. Correlation to MDC/Logs

When correlation fields are configured, Spring Boot/Micrometer logging integration can populate baggage into MDC. Inspect a real log event to confirm key names and formatting; do not assume MDC always holds literal key names.

Safe log example:

~~~text
INFO service=inventory-service traceId=4bf92f...
spanId=00f067... orders.channel=web event=reservation_started
~~~

Unsafe log example:

~~~text
INFO traceId=... baggage=customer.email=alice@example.com
authorization=Bearer eyJ... request.body={...}
~~~

Log correlation must have its own allowlist. If a baggage field propagates downstream yet is unnecessary in logs, do not automatically log all baggage members.

## 7. Protecting Data at Sinks: Traces, Logs, and Metrics

Baggage is only a context source. Once extracted, code or instrumentation can copy values to other systems. Every sink needs its own policy.

| Sink | Risk | Rule |
| --- | --- | --- |
| HTTP `baggage` header | Broadcast across multiple services/hops | Remote allowlist, verify source, cap size |
| Span attributes | Trace backend stores/indexes values over time | Attach only needed attributes, strip PII/secrets |
| Logs/MDC | Broad access and long retention | Correlation allowlist, masking/redaction, retention |
| Metric labels | Cardinality explosion and data multiplied into series | Use finite values only, never request/customer IDs |
| Collector processors | Data may be transformed/exported to other systems | Verify filters/redaction before export |
| Dashboards/alerts | Broader audience can view fields | Access controls and queries must not expose data |

### 7.1. Low and High Cardinality Both Need Protection

In Micrometer Observation:

- **Low-cardinality key-values** can usually enter metrics and span attributes.
- **High-cardinality key-values** serve span metadata per policy, unsuitable as metric labels.

Yet high cardinality does not imply safety. A `customer.id` can be high-cardinality and still be an identifying datum. Both **cardinality review** and **privacy/security review** are required.

### 7.2. Trace ID Is Also Data to Govern

A Trace ID is usually a random technical identifier, not a credential, yet when linked to logs or user records it can become a lookup key leading to sensitive data. Restrict telemetry viewing permissions and avoid putting trace IDs into metric labels.

### 7.3. Do Not Use Baggage Instead of Local Log Context

If a field is only needed in one service's logs, add it to structured logs in that service instead of propagating it across the whole system. Each hop adds a header and another metadata copy. Propagate only if downstream truly needs it.

## 8. Context Propagation, Async, and Data Lifecycle

Baggage is bound to the execution/tracing context. During synchronous processing, scopes keep fields active for the operation. When moving to executors, Reactor, messaging, or batches, ensure context is captured and restored accurately.

### 8.1. Thread Pools Can Leak Context

If a scope is left unclosed, a thread pool can reuse a thread carrying a prior request's baggage. Dangerous scenario:

~~~text
Request A: orders.channel=partner
  -> worker thread 3
  -> scope never closed

Request B: orders.channel=web
  -> worker thread 3 reused
  -> may observe stale context if propagation/cleanup fails
~~~

Always manage scopes with `try-with-resources` or matching lifecycle APIs. For executors, use only supported context propagation mechanisms; test both **context propagated** and **context cleaned/restored**.

### 8.2. ContextPropagatingTaskDecorator

With Spring Framework 6.1+ and Micrometer Context Propagation, a Spring executor can use `ContextPropagatingTaskDecorator` when matching context accessors are registered:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class SecureContextExecutorConfiguration {
    @Bean
    ThreadPoolTaskExecutor contextAwareExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

The decorator captures/restores registered contexts; **it is not a data allowlisting mechanism**. If baggage contains an unsafe field, the decorator can still transfer that context. Sanitize/control baggage before submitting tasks.

### 8.3. Messaging and Batch

With Kafka/RabbitMQ, propagators or instrumentation can inject/extract trace context and baggage in message headers. A message can sit in a queue longer than the initial request; baggage should not contain ephemeral or secret data because it persists in broker headers and may be stored with the message.

A batch processing multiple messages from different traces cannot naively merge all baggage into one shared context. Define span links/parent relationships semantically rather than bleeding one message's baggage onto every other message.

## 9. Testing Baggage Protection Policies

Tests must verify **invalid values are stripped**, **valid values propagate accurately**, and **no leaks occur via logs/async**. Testing baggage getters/setters alone is not enough to prove a safe policy.

### 9.1. Validator Unit Test

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BaggageValuePolicyTest {

    @Test
    void normalizesAllowedChannel() {
        assertEquals("web",
                BaggageValuePolicy.normalizeChannel(" WEB "));
        assertEquals("batch",
                BaggageValuePolicy.normalizeChannel("batch"));
    }

    @Test
    void rejectsUnknownOrUntrustedValues() {
        assertEquals("unknown",
                BaggageValuePolicy.normalizeChannel("internal-admin"));
        assertEquals("unknown",
                BaggageValuePolicy.normalizeChannel("alice@example.com"));
        assertEquals("unknown",
                BaggageValuePolicy.normalizeChannel(null));
    }
}
~~~

This test protects the value set for `channel`. The application must still validate data sources and other fields; one validator alone cannot replace the entire policy.

### 9.2. Allowlist Propagation Test over HTTP

An integration test with tracing-instrumented HTTP client/server should:

1. Create valid baggage `orders.channel=web` in scope.
2. Inject a disallowed field into test input (e.g., `customer.email`).
3. Send the request to the test server.
4. Verify the server receives the allowlisted field via the parsed baggage API.
5. Verify the forbidden field never appears in downstream context or logs.
6. Verify trace context remains connected when W3C propagation is enabled.

Tests should use parser/context accessor APIs rather than comparing raw headers alone, since headers can be encoded or ordered differently.

### 9.3. Log Redaction and MDC Cleanup Test

Capture log events in tests:

- Emit logs while valid baggage is active; confirm only approved fields appear.
- Feed inputs containing emails/tokens at the boundary; confirm raw values never appear in logs.
- Close the scope and log a subsequent event on the same thread; confirm prior request baggage is gone.
- Verify exception messages also exclude tokens, payloads, or sensitive data.

### 9.4. Header Size and Duplicate Keys Test

Create baggage with member counts/values exceeding the defined budget; policy must drop, reject, or bound per application behavior and never propagate bloated headers. Test duplicate keys and values with unusual characters; define rules to take one value, reject, or normalize. Do not let each service invent different handling.

### 9.5. Async Context Isolation Test

Use an executor with one worker thread to force reuse:

1. Task A sets normalized baggage `orders.channel=partner`.
2. Task A finishes; scope must close.
3. Task B receives no baggage; it must not see A's value.
4. Task C has its own context `orders.channel=web`; it must see only C's value.
5. Repeat tests to catch races/contamination.

If using a context propagation decorator, test both propagated and unpropagated paths to confirm expected policy. Never assume a task reading baggage is sufficient if cleanup has not been proven.

## 10. Troubleshooting and Incident Response

| Symptom | Possible cause | Action |
| --- | --- | --- |
| Downstream receives email in baggage | Ingress failed to strip/validate field | Halt propagation, fix allowlist, remove field |
| Client baggage overwrites internal context | Source and trust level not separated | Strip/overwrite at trust boundary |
| Logs emit tokens or PII | Overly broad log correlation, raw baggage logged | Stop export, redact, remediate stored logs |
| HTTP 431/400 | Baggage too long or broken encoding/duplicates | Cap size/members and standardize parser |
| Stale baggage appears in next request | Scope unclosed or context unrestored | Check `try-with-resources` and executor propagation |
| Baggage disappears across a gateway | Header stripped or capped | Check gateway config and contract |
| Metric series spike suddenly | Baggage values copied into labels | Remove dynamic fields from metric tags |
| Traces lack attributes after filtering | Policy/processor strips fields or backend limits | Check each sink and exporter/Collector |
| Baggage present yet trace missing | Sampling/exporter/backend failure | Inspect tracing pipeline separately |
| Channel differs between two services' logs | Services normalize differently or propagation broken | Normalize in one place and verify extraction |

### 10.1. Response Playbook When Baggage Leaks Data

1. **Isolate the field:** identify which key/value leaked, starting from which service and timestamp.
2. **Stop dissemination:** temporarily remove the key from remote/correlation allowlists or configure stripping at ingress and downstream boundaries.
3. **Stop further recording:** disable affected instrumentation/logging paths if needed, while keeping safe operational telemetry to monitor impact.
4. **Identify receiving systems:** gateway logs, service logs, Collectors, trace backends, metric backends, broker headers, and exports/backups.
5. **Assess access exposure:** who can read the data, retention periods, and downstream copies.
6. **Remediate credentials if exposed:** revoke/rotate leaked tokens or API keys per secrets management procedures.
7. **Delete/expire data:** apply each backend's retention, deletion, and incident-response policies; never assume deleting a trace deletes all log copies.
8. **Verify again:** add regression tests confirming data is blocked at trust boundaries and all sinks.

If personal data or credentials were exposed, invoke the organization's security/privacy incident process and applicable legal obligations. Never delete necessary audit trails without coordinating with incident responders.

### 10.2. Safe Metrics for Policy Monitoring

You can count rejected baggage fields using a counter with finite reason labels, e.g., `reason=unknown_key`, `reason=invalid_value`, `reason=too_large`. Never put raw incoming keys/values into labels. This metric helps detect clients sending abnormal headers without duplicating sensitive data into monitoring systems.

## 11. Production Checklist

| Criterion | Required evidence |
| --- | --- |
| Baggage fields inventoried | Every key has an owner, use case, and data source |
| Deny by default | Only approved remote allowlist fields enabled |
| Trust boundaries defined | External baggage stripped/validated before trusting |
| Values normalized | Enum/format/length validated |
| No secrets/PII | Security review and log/header tests |
| No baggage used for authorization | Permissions come from authenticated source, not caller metadata |
| Header size within budget | Limit set below proxy/client/server chain minimum |
| Correlation fields separated | Only approved fields written to logs |
| Span attributes governed by policy | No auto-copying all baggage |
| Low-cardinality metric labels | No request/customer IDs or free-form values |
| Async/messaging isolation tested | No context loss and no leakage to other tasks |
| Exporters/backends audited | Know where traces/logs reside and retention windows |
| Incident response ready | Procedures to block, rotate secrets, locate and purge copies |
| Regression tests present | Spoofing, PII, header size, duplicate keys, cleanup |

## 12. Hands-On Exercise: Hardening Baggage for `order-service`

**Scenario:** `order-service` receives requests from web and partners, then calls `inventory-service` and `payment-service`. Recently the team discovered `baggage` headers could contain arbitrary client-sent fields and those fields sometimes appeared in logs.

**Tasks:**

1. Inventory needed baggage fields, keeping only `orders.channel` and `deployment.region` in this example.
2. Establish a trusted source for `channel` (gateway/API integration config) rather than using caller-supplied raw values.
3. Write a validator for `channel` (`web`, `batch`, `partner`); map other values to `unknown` or drop per policy.
4. Configure `management.tracing.baggage.remote-fields` and `correlation.fields` separately.
5. Create baggage with `Tracer.createBaggageInScope` inside the service after authentication/normalization.
6. Call `inventory-service` via an instrumented HTTP client; confirm the `baggage` header carries only approved fields while trace context stays linked.
7. Send `customer.email`, `authorization`, and a very long string from the client; prove these values never reach downstream or logs.
8. Capture log events, verifying MDC holds only trace/span IDs and the approved `channel`; once scope closes, no stale context remains.
9. Run two tasks on the same executor thread to test async context isolation.
10. Create a metrics counter tracking dropped baggage by finite `reason`; never attach raw keys/values as labels.
11. Simulate an incident where a sensitive field reached the Collector; write steps to halt propagation, handle credentials, and locate copies per retention policy.

**Expected deliverables:** allowlist policy, validation code, Spring configuration, propagation tests, log redaction tests, async isolation tests, and an incident playbook.

## 13. Key Takeaways

**Baggage is a context propagation channel, not a trust channel or secrets store.** Every field can cross multiple services, proxies, Collectors, and log/trace backends. Therefore, define its origin, trust level, valid values, propagation scope, permitted sinks, and retention period.

Enforce a **deny-by-default allowlist**, validate/normalize values, limit member counts and size, strip external data at trust boundaries, close scopes per lifecycle, and never use baggage to grant permissions. Span attributes, MDC/log fields, and metric labels require separate policies: do not copy all baggage to every sink, never put PII/secrets into telemetry, and never use high-cardinality values as metric labels.

Effective baggage protection must be tested across **creation, injection, extraction, async propagation, logging, metrics, and export**. During an incident, stop dissemination first, identify all backends that received data, handle credentials/retention per incident policy, and add regression tests to prevent recurrence.

**References:**

- [W3C — Baggage](https://www.w3.org/TR/baggage/)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [OpenTelemetry — Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/)
