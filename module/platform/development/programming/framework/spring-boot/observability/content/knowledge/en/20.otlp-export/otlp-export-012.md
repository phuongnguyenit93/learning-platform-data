# Never Export Secrets in Telemetry

A payment request passes through the API Gateway, Order Service, and Payment Service. When investigating an error, the application records full request headers, query parameters, and exception messages into span attributes or logs. An `Authorization` header, session cookie, or access token unexpectedly shows up in the OTLP payload. Once the exporter sends telemetry to the Collector and backend, the secret has left the application process and may be stored across multiple systems, backups, or storage regions.

The **Never export secrets in telemetry** lesson belongs to the **OTLP export** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; understanding context propagation, tags/cardinality, exporters, sampling, and correlating signals to investigate errors, latency, and application behavior in production environments.

> **Core principle:** Prevention must begin where telemetry is created: never collect secrets into spans, metrics, logs, events, baggage, or Resource. Collector processors are an additional defense layer to scrub/filter data before forwarding, not an excuse for applications to send everything to the Collector. Distinguish secrets in OTLP exporter headers/TLS credentials used to authenticate the transport channel from secrets in the telemetry payload, which is observational data that must never contain credentials.

## 1. Learning Objectives

After this lesson, you will be able to:
1. Identify secrets that can leak into traces, metrics, logs, baggage, Resource attributes, and exception events.
2. Distinguish exporter authentication headers from telemetry attributes/bodies.
3. Design data minimization and allowlists directly inside Spring Boot instrumentation.
4. Avoid logging `Authorization`, `Cookie`, `Set-Cookie`, access tokens, passwords, API keys, request bodies, and payment data.
5. Manage OTLP endpoint credentials using secret management, environment injection, and TLS/SSL bundles.
6. Configure Collector `attributes`, `filter`, `redaction`, and `transform` processors.
7. Understand processor limitations with log bodies, nested payloads, and exporter headers.
8. Inspect traces, metrics, and logs before data leaves the system.
9. Test using a fake canary secret and verify it never appears in the backend.
10. Establish an incident response workflow when a secret is accidentally exported.

## 2. Where Can Secrets Appear?

Telemetry is not just span names and durations. Instrumentation can record attributes, events, exception messages, log bodies, baggage, or Resource attributes. If code attaches user input or headers directly to these fields, the OTLP exporter sends them along with observational data.

| Component | Risk Example | Where It Can Leak |
|---|---|---|
| Span attributes | `http.request.header.authorization`, `user.password`, `db.connection_string` | Span/trace payload |
| Span events | Exception message containing a token or SQL parameter | Event attributes |
| Span name | URL with query string containing a token/email | Span name |
| Baggage | `access-token`, `session-id`, `email` | Propagation headers and downstream telemetry |
| Logs | `Authorization` header, cookie, raw request body | Log body/attributes/MDC |
| Metrics | `user_id`/`order_id`/`token` as tags | Metric labels/data points |
| Resource attributes | `process.command_line` containing credentials | Resource attached to broad telemetry |
| Exception | Message or stack metadata containing sensitive data | Logs/traces |
| OTLP exporter headers | `api-key`, `Authorization: Bearer ...` | HTTP/gRPC metadata to Collector/backend |

Secrets are not just passwords. Consider access/refresh tokens, API keys, private keys, session cookies, database passwords, signed URLs, payment credentials, client secrets, webhook secrets, and personal information that can identify or grant access to an account.

### 2.1 Examples of Data That Must Not Be Recorded

~~~http
Authorization: Bearer eyJhbGciOi...
Cookie: SESSION=abc123
X-Api-Key: sk_live_example
~~~

Never copy these values into baggage, span attributes, log statements, MDC, metric tags, or exception context. If you need to confirm authentication succeeded, record a normalized outcome (e.g., `authentication.outcome=success`) instead of the credential.

### 2.2 Secrets in URLs Are Still Secrets

Never record raw URLs when query parameters contain `access_token`, `id_token`, signed download URLs, password reset tokens, emails, phone numbers, or private search data. Prefer a route template such as `/orders/{orderId}`, not the resolved URL with real values. If you must observe query parameters, record only parameter names or values categorized/anonymized per policy.

## 3. Distinguishing Exporter Credentials From Telemetry Payloads

An OTLP exporter sends requests to the Collector over HTTP or gRPC. To authenticate, the exporter may attach headers, tokens, client certificates, or use TLS/mTLS. This information protects the transport channel; it is not business metadata of a trace.

~~~mermaid
flowchart LR
    A["Spring Boot application"] --> B["OTLP exporter"]
    B -->|"TLS/mTLS + auth header"| C["Collector receiver"]
    B -->|"Telemetry payload"| C
    C --> D["Processors: filter/redact"]
    D --> E["Backend exporter"]
    E --> F["Observability backend"]
~~~

| Data | Example | How to Protect |
|---|---|---|
| Exporter credential | `Authorization` header, API key, client certificate | Secret manager, runtime injection, TLS/mTLS, least privilege |
| Telemetry content | Span attributes, log bodies, metric labels, Resource attributes | Data minimization, allowlists, redaction/filtering |
| Collector backend credential | Token sent to vendor backend | Secret management at the Collector |
| Trace context | Trace ID, Span ID, sampled flag | Propagated per protocol; not an authentication secret |

Do not put exporter tokens into baggage or span attributes to debug the exporter. Authentication headers should also not be printed in HTTP client wire logs or debug logs. The Collector must avoid logging sensitive headers via receiver/exporter config and operational policies.

## 4. Data Minimization: If You Do Not Collect It, You Do Not Have to Scrub It

OpenTelemetry cannot automatically determine which fields are business-sensitive. Instrumentation implementers must decide what data needs to be observed and take responsibility for protecting telemetry. The safest approach is usually not collecting sensitive data in the first place.

Checklist before adding an attribute:
1. **Purpose:** which operational question does this field answer?
2. **Necessity:** can a summarized status, enum, or route template replace raw data?
3. **Scope:** which signal truly needs this field?
4. **Sensitivity:** could this field contain credentials, PII, financial data, or regulated data?
5. **Cardinality:** is the value nearly unique per request?
6. **Retention/access:** who reads the backend, how long is data kept, and in which region?
7. **Testing:** is there a test proving secrets do not appear in payloads?

| Instead of Recording | Consider |
|---|---|
| `Authorization` header | `authentication.outcome=success/denied` |
| Cookie/session token | `session.present=true` |
| Raw SQL with parameters | `db.system.name`, operation name, query template stripped of literals |
| Full URL/query string | `http.route=/orders/{orderId}` |
| Payment card number | `payment.method=card`, `result=approved` |
| Customer email | `customer.type=registered` or allowed region |
| Raw exception message with token | Normalized `exception.type` and `error.category` |

Do not hash sensitive data and automatically assume it is harmless. Hashing emails/phone numbers or IDs with a small value domain can be reversed via dictionary attacks; hashing also produces stable values enabling correlation of user activity.

## 5. Avoiding Recording Secrets in Spring Boot Instrumentation

### 5.1 Never Log All HTTP Headers

Avoid:

~~~java
// DO NOT DO THIS: may log Authorization, Cookie, API key...
log.debug("Request headers: {}", request.getHeaders());
~~~

Replace with allowlisted metadata:

~~~java
log.debug("Incoming request method={} route={} contentType={}",
        request.getMethod(),
        routeTemplate,
        safeContentType);
~~~

If you need to observe authentication, log normalized outcomes without credentials:

~~~java
log.info("Authentication completed outcome={} mechanism={}",
        "success",
        "oauth2");
~~~

Do not log raw header maps just to verify a request was sent properly. Some HTTP instrumentations capture headers automatically per config; inspect your instrumentation library's allowlist and disable sensitive captures.

### 5.2 Never Put Raw Request/Response Bodies Into Logs or Spans

~~~java
// DO NOT DO THIS
log.info("Payment request body={}", requestBody);
span.tag("payment.request", requestBody);
~~~

Payment payloads can contain card numbers, addresses, tokens, or customer data. Replace with safe fields:

~~~java
log.info("Payment request received method={} currency={} amountBand={}",
        paymentMethod,
        currency,
        amountBand);
~~~

Choose `amountBand` only if business rules allow it and the range buckets do not expose sensitive data.

### 5.3 Sanitize Exception Messages

Exceptions can include URLs with query tokens, connection strings, or SQL containing parameters. Never assume every exception message is safe to log or attach to a span.

~~~java
try {
    paymentGateway.authorize(command);
} catch (PaymentGatewayException ex) {
    observation.error(ex);
    log.warn("Payment authorization failed type={} category={}",
            ex.getClass().getSimpleName(),
            "provider_error");
    throw ex;
}
~~~

This snippet logs exception class and category. Inspect default handlers because tracing/logging instrumentation may automatically append exception events or messages; sanitize where data is created and configure handlers appropriately if exceptions might contain secrets.

## 6. Never Put Secrets Into Baggage, MDC, Resource, or Metric Tags

**Baggage** propagates broadly across multiple services via the W3C `baggage` header. Never put tokens, cookies, emails, or raw user input into baggage. Allow only necessary keys, such as normalized channel or deployment cohort.

**MDC** appears in log events when encoders/patterns read keys. If a credential is placed in MDC, many log statements in the same scope may log it inadvertently. MDC must also be cleaned up/restored across async boundaries to avoid leaking context between worker tasks.

**Resource attributes** attach to a service/instance's telemetry and are typically repeated/grouped across many spans, metrics, and logs. Never put database URLs with passwords, process command lines containing `--password`, cloud credentials, or secret mount contents into Resource.

**Metric tags** can replicate sensitive data and drive rapid cardinality growth. Never attach user tokens, emails, account IDs, or payment references to tags. Use small, aggregated metric dimensions.

## 7. Managing OTLP Exporter Credentials

Spring Boot supports configuring endpoints, headers, and compression for OTLP exporters. They can be configured commonly across traces/logs/metrics or per signal depending on version/property group. Headers may carry an `Authorization` bearer token or `api-key`.

Illustrative common configuration example:

~~~yaml
management:
  opentelemetry:
    otlp:
      endpoint: https://otel-collector.example.internal:4318
      compression: gzip
      headers:
        Authorization: <injected-secret>
~~~

The placeholder above represents a value injected from secret management or the runtime environment; never write real tokens into source control, Dockerfiles, image layers, public ConfigMaps, or shared sample files. Binding/injection syntax must follow your Spring Boot version and platform.

Some integrations/versions have separate settings per exporter, such as traces, logs, or Micrometer metrics. Read the property reference for your exact Spring Boot version; do not assume `management.opentelemetry.otlp.headers` configures every metrics registry outside Micrometer.

### 7.1 Use a Secret Manager or Platform Secret Injection

Credentials should originate from a secret management system (Vault, cloud secret manager, protected Kubernetes Secret, workload identity, or equivalent).

- Inject at runtime or mount files/SSL bundles with appropriate permissions.
- Only services/instances that need to send telemetry should be able to read the credential.
- Use narrow-scoped tokens allowing ingest only to the required tenant/project.
- Rotate periodically and whenever exposure is suspected.
- Do not echo the environment, print application config, or dump beans containing headers.
- Do not leave secrets in build logs, process command lines, or diagnostics.
- Prefer workload identity/mTLS when supported by infrastructure instead of static long-lived API keys.

Not every environment uses the same secret manager; pick the mechanism suited to your platform and verify it does not leak credentials into secondary logs/metadata.

### 7.2 TLS and mTLS

TLS protects connections and prevents eavesdropping/tampering in transit. mTLS adds client authentication via certificates. TLS does not prevent secrets already embedded inside telemetry payloads from being stored by the Collector; payloads must be scrubbed separately.

When using private CAs/client certificates, configure SSL bundles or truststores/keystores per your Spring Boot/OTLP exporter integration. Never disable certificate validation to fix connection errors; resolve CA chains and hostname verification properly.

### 7.3 Header Secrets Do Not Belong in Resource or Baggage

Do not create attributes like these:

~~~text
Resource:
  otlp.authorization = Bearer ...
  collector.api_key = ...

Baggage:
  exporter-token = ...

Span attributes:
  http.request.header.authorization = ...
~~~

The exporter uses headers at the transport layer; never copy them into attributes for debugging. If you need to verify authentication, record connection status or normalized error codes without logging credentials.

## 8. Collector Processors as an Additional Defense Layer

The OpenTelemetry Collector has processors that delete, update, filter, or transform telemetry before sending to backends.

| Processor | Effect | When to Use |
|---|---|---|
| `attributes` | Insert/update/delete/hash attributes of spans/logs/metrics | Remove specific keys or transform metadata |
| `filter` | Drop spans, logs, or metric records/data points by condition | Discard disallowed records |
| `redaction` | Keep an allowlist of attributes, remove non-listed fields, and mask blocked values | Centralized data minimization |
| `transform` | Modify/replace/delete data via OTTL statements/regex | Normalize or scrub complex patterns |

**Declaring a processor does not activate it automatically.** It must be added to the corresponding `service.pipelines`. Configure each pipeline for traces, metrics, and logs; a processor added only to the `traces` pipeline does not automatically protect the `logs` pipeline.

### 8.1 Deleting Attributes With the `attributes` Processor

Collector Contrib example:

~~~yaml
processors:
  attributes/drop-sensitive:
    actions:
      - key: user.password
        action: delete
      - key: http.request.header.authorization
        action: delete
      - key: session.id
        action: delete

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [attributes/drop-sensitive, batch]
      exporters: [otlp/backend]
    metrics:
      receivers: [otlp]
      processors: [attributes/drop-sensitive, batch]
      exporters: [otlp/backend]
    logs:
      receivers: [otlp]
      processors: [attributes/drop-sensitive, batch]
      exporters: [otlp/backend]
~~~

This example illustrates Contrib processor configuration and pipeline names; receiver/exporter identifiers must be declared correspondingly in the deployment config. The `attributes` processor acts only on attributes in supported contexts; **it does not automatically remove secrets embedded inside log bodies or message strings**. Inspect the actual structure of each signal.

### 8.2 Allowlist-Based `redaction` Processor

The `redaction` processor can strip attributes outside an allowed list and mask values matching blocked values. This is the allowlist approach: retain only keys genuinely needed for observability.

~~~yaml
processors:
  redaction/safe-fields:
    allow_all_keys: false
    allowed_keys:
      - http.request.method
      - http.route
      - http.response.status_code
      - service.name
      - deployment.environment.name
      - error.type
    blocked_values:
      - "Bearer .*"
      - ".*@.*"
~~~

Field names and syntax depend on the Collector Contrib version/distribution and processor stability. The example illustrates the concept; verify the schema of your deployed binary before applying. Overly strict allowlists can strip fields needed for investigation; test on representative data.

### 8.3 `transform` Processor and Log Bodies

The `transform` processor uses OpenTelemetry Transformation Language (OTTL) to set, modify, or delete attributes or log bodies in supported contexts. Example deleting keys from spans:

~~~yaml
processors:
  transform/remove-secret:
    error_mode: ignore
    trace_statements:
      - context: span
        statements:
          - delete_key(attributes, "user.password")
          - delete_key(attributes, "http.request.header.authorization")
~~~

Log bodies can be strings or structured maps; use the matching OTTL contexts/statements. Do not rely on generic regexes to catch every token: formats, encodings, and nested objects vary. Best practice is never putting secrets into bodies in the first place.

### 8.4 `filter` Processor

The `filter` processor fits when you need to drop entire records/spans/metrics by condition. However, dropping an entire span can lose non-sensitive investigative data alongside the secret. Prefer deleting the specific attribute whenever possible; drop the entire record only when it cannot be safely sanitized or policy requires it.

## 9. Pipeline Order and Protected Zones

Collector processors run sequentially inside a pipeline. A redaction processor placed after a debug sink runs too late for the branch before it. Every output path must pass through the required scrubber layer before crossing a trust boundary.

~~~mermaid
flowchart TD
    A["OTLP receiver"] --> B["Early validation / allowlist"]
    B --> C["Attributes / redaction / transform"]
    C --> D["Batch"]
    D --> E["Authorized backend exporter"]
    C --> F["Optional secondary exporter"]
    F --> G["Other approved destination"]
~~~

Check:
- Does any debug exporter or logging exporter receive payloads before redaction?
- Do multiple pipelines share a receiver while only one pipeline has a scrubber?
- Does any connector/exporter bypass the Collector and send straight to a vendor?
- Do Collector internal logs accidentally print auth headers or payload values?
- Do retry queues or file storage hold unscrubbed payloads?

A Collector only protects paths passing through that Collector. If an application sends telemetry straight to a vendor, protect it at the application and along that exporter path.

## 10. Limitations of Redaction

Collector-side redaction is defense-in-depth, not a license to record sensitive data in telemetry.

- Secrets can appear in `span.name`, event names, log bodies, stack traces, or nested attributes, not just flat attributes.
- A processor may support traces while lacking the same maturity for logs/metrics; check stability status for your deployed version.
- Regexes will not detect every token encoding, base64, URL encoding, multiline value, or custom format.
- Hashed values can still be linked back to individuals if the input domain is small or guessable.
- A misconfigured or omitted processor in a pipeline can send telemetry straight to the exporter.
- The Collector cannot scrub data already stored previously by a backend.
- When fanning out to multiple exporters, ensure all branches comply with policy.

**Do not treat "we have a Collector" as proof there are no secrets.** Test the final payload at each destination.

## 11. Controlling Span/Log/Metric Instrumentation

### 11.1 HTTP Header Capture

Capture only allowlisted headers, such as standardized non-sensitive correlation headers. Exclude at minimum `Authorization`, `Cookie`, `Set-Cookie`, proxy authorization, API keys, custom secret headers, and headers carrying PII. Capture properties and semantics vary across instrumentation libraries; check each instrumenter.

### 11.2 Database Statements

Never record connection strings containing passwords or SQL containing sensitive literal parameters. Use `db.system`, `db.operation.name`, allowed database names, and safe statement templates. If query text is collected, verify whether parameters are inlined.

### 11.3 Exceptions and Stack Traces

Exceptions can contain request URLs, query tokens, usernames, connection strings, or remote response bodies. Inspect application-created log messages, exception events added by tracing handlers, stack traces/suppressed exceptions, and error response bodies captured by HTTP client instrumentation. Configure exception recording intentionally and sanitize messages before they enter signal pipelines if needed.

### 11.4 Metrics Must Never Carry Secrets

Metric tags typically persist long-term in time-series backends and carry index/cardinality costs. Never attach secrets or user identifiers to labels, even if hashed. Record only outcome, route template, protocol, status code, or finite dimensions.

### 11.5 Resource and Process Metadata

Inspect Resource attributes generated by auto-detection, especially `process.command_line`, host identifiers, container labels, and custom service metadata. Never inject secrets via command-line arguments because they can surface in process metadata or diagnostics.

## 12. Testing That Secrets Are Not Exported

A good security test does more than inspect configuration; it verifies a fake secret never appears in the final serialized telemetry.

### 12.1 Fake Canary Secret

Create a test string with zero real access value:

~~~text
FAKE_CANARY_SECRET_DO_NOT_EXPORT_9f23a7
~~~

Place the canary into a fake `Authorization` header, fake cookie, fake query parameter, test exception message, and test log body. After sending the request, capture telemetry output with a test exporter or mock OTLP Collector and assert the canary string appears in zero signals.

### 12.2 Inspecting Serialized OTLP Payloads

Tests should inspect:
1. Span attributes and events.
2. Resource attributes.
3. Metric attributes/labels.
4. Log bodies and log attributes.
5. Baggage propagation headers.
6. OTLP exporter headers in test transport (use fake credentials only; never print to output).

Do not check logger messages alone; secrets can be added automatically by instrumentation or exception handlers.

### 12.3 Testing Redaction Processors

Send OTLP test records containing secret fields into the Collector pipeline; confirm secret attributes are deleted/masked, non-sensitive attributes remain intact, the processor is wired into every signal pipeline, and secondary exporters receive only scrubbed data. Test nested fields inside log bodies separately; do not confuse deleted attributes with scrubbed log bodies.

Use synthetic payloads; never put real user data into test logs.

### 12.4 Post-Rollout Verification

After deployment, search for the canary pattern in backend logs/traces/metrics if sent by tests; inspect Collector self-telemetry and exporter errors; review representative traces/log records; confirm exporter credentials never appear in debug logging. Repeat when adding instrumentation libraries or upgrading Spring Boot/Micrometer/OTel agent versions.

## 13. Debugging: A Secret Appeared in the Backend

**Scenario:** A backend trace has attribute `http.request.header.authorization` containing a bearer token.

1. **Stop further leaks:** disable the leaking instrumentation/capture path or block exporting the field/record at the ingress Collector.
2. **Determine scope:** traces, logs, metrics, baggage, Resource; service/version/instance; start/end timestamps.
3. **Origin:** code manually adding attributes, HTTP agent capture, exception handler, log body, or Collector transform.
4. **Spread path:** which services received/forwarded baggage; which backends and exporter destinations received it.
5. **Credential response:** if a real secret leaked, revoke/rotate the credential via its owning system; do not merely delete the field in a dashboard.
6. **Data retention:** follow incident/security policy to purge or restrict records/backups where possible and permitted.
7. **Verify:** send a new canary test, inspect every destination, and monitor for non-recurrence.
8. **Prevent recurrence:** add allowlists, instrumentation tests, Collector redaction, and reviews on dependency changes.

Never paste real secrets into tickets, Slack, chat, or incident reports to prove a leak. Use field names, locations, timestamps, and policy-compliant canary/fingerprints.

## 14. Symptom and Cause Matrix

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `Authorization` appears in span | HTTP header capture or custom tag | Disable capture, allowlist headers, remove at source |
| Cookie appears in logs | Request logging/filter logs all headers | Redact in app logger, check MDC/encoder |
| Token inside exception | Exception message contains URL/body/remote response | Sanitize message/exception event and fix source |
| Secret inside span name | URL/raw input used as name | Use route templates and stable operation names |
| Secret in downstream baggage | Caller/service writes credential into baggage | Remove field, allowlist baggage, check propagation |
| Secret in metric labels | Dynamic tag pulled from input | Remove tag, switch to finite dimension, check cardinality |
| Secret in Resource | Environment/process metadata holds credentials | Fix injection pattern, build safe Resource |
| Collector redaction not working | Processor not wired into pipeline | Check `service.pipelines` for traces/logs/metrics |
| Attribute deleted yet log body retains secret | Processor modifies attributes only | Sanitize body at source or transform in proper context |
| Backend B still receives secret | Fan-out pipeline bypasses scrubber | Ensure all exporters receive scrubbed data |
| OTLP export gets 401 | Invalid or expired credentials/headers | Check secret injection, scope, rotation; do not log token |
| TLS handshake error | CA/certificate/hostname mismatch | Fix trust chain/SSL bundle; never disable verification |
| Canary absent at Collector yet present in backend | Direct exporter or another pipeline exists | Check all export paths and destinations |
| Secret returns after upgrade | Newer instrumentation adds fields/headers | Regression canary tests and review semantic attributes |

## 15. Secure Design Workflow for OTLP Export

Before enabling OTLP export for production:

1. **Inventory signals:** list traces, metrics, logs, and where they are produced.
2. **Data classification:** flag secrets, PII, financial data, and internal infrastructure details.
3. **Source allowlist:** record only purposeful fields, using route templates and standardized enums.
4. **Exporter auth:** issue least-privilege credentials via secret management; configure TLS/mTLS.
5. **Collector pipeline:** wire `filter`/`redaction`/`attributes`/`transform` processors into every pipeline.
6. **Access control:** restrict backend read access, tenant/project scope, and retention.
7. **Canary test:** prove fake secrets are absent from serialized payloads and backends.
8. **Review upgrades:** check capture defaults when upgrading instrumentation, agents, Boot, or OTel SDKs.
9. **Incident playbook:** know how to halt export, rotate credentials, and handle stored telemetry.

Do not enable debug HTTP logging in production if it can print exporter headers or request/response payloads. When diagnostics are needed, use synthetic credentials/traffic and turn logging off after testing.

## 16. Self-Check Exercises

**Exercise 1 — Classifying secrets.** A span has attributes `Authorization`, `http.route`, and response status. Which fields may be kept, and which must be removed? Explain.

**Exercise 2 — Exporter headers.** An application uses an OTLP bearer token in the HTTP `Authorization` header to authenticate with the Collector. Why must this credential never be added to a span attribute or Resource?

**Exercise 3 — Data minimization.** An exception message contains a signed URL. Propose a way to record the error so it remains investigable without recording the URL/token.

**Exercise 4 — Collector processors.** You declare an `attributes` processor to delete `user.password`, yet the backend still receives secrets inside log bodies. Why? Where should you inspect and fix it?

**Exercise 5 — Pipeline coverage.** The Collector has a `traces` pipeline using redaction, while `logs` and `metrics` pipelines omit the processor. What can happen? How do you ensure all destinations receive scrubbed data?

**Exercise 6 — Hashing.** A developer hashes emails and writes them into baggage. Why does hashing not automatically make emails anonymous? When should the field be omitted entirely?

**Exercise 7 — TLS.** An OTLP exporter fails certificate verification. Why is disabling hostname verification not the right fix? List the steps to check the CA and certificate.

**Exercise 8 — Leak response.** A real access token appeared in the traces backend. Outline the sequence of actions: halting export, rotating/revoking, handling stored data, and regression testing.

### Answer Hints

1. Keep the route template and status code if needed; remove `Authorization`. Never retain raw headers.
2. The header is transport authentication data; spans/Resource can be stored, searched, and forwarded broadly. Never copy credentials into telemetry.
3. Log exception type, error category, dependency, and correlation ID; sanitize URLs/messages and never log raw signed URLs.
4. The `attributes` processor modifies attributes only; the log body is a separate region. Sanitize in the app or transform the log body with matching OTTL; test the final payload.
5. Logs/metrics can still carry secrets. Wire the processor into every signal pipeline and every exporter branch.
6. Email domains are easy to dictionary-attack, and a stable hash still allows correlation; usually omit it or use non-identifying categorical data.
7. Check SAN/hostname, CA chain, truststore/SSL bundle, certificate expiry, and endpoint; keep verification enabled.
8. Block the emission path, revoke/rotate the secret, determine scope, handle retention/copies per incident policy, add canary tests, and confirm non-recurrence.

## 17. Official References

- [OpenTelemetry — Handling Sensitive Data](https://opentelemetry.io/docs/security/handling-sensitive-data/): data minimization, sensitive attributes, and Collector processors.
- [OpenTelemetry — Security Best Practices](https://opentelemetry.io/docs/security/config-best-practices/): protecting Collector/export pipelines and secure configuration.
- [OpenTelemetry — Transforming Telemetry](https://opentelemetry.io/docs/collector/transforming-telemetry/): `attributes`, `filter`, `redaction`, and `transform` processors.
- [OpenTelemetry Collector — Configuration](https://opentelemetry.io/docs/collector/configuration/): receivers, processors, exporters, and service pipelines.
- [Collector Contrib — Attributes Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/attributesprocessor): insert/update/delete/hash attribute values.
- [Collector Contrib — Redaction Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/redactionprocessor): allowlists and blocked values for telemetry attributes.
- [Collector Contrib — Transform Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/transformprocessor): OTTL transformation for spans, logs, and metrics.
- [OpenTelemetry — OTLP Exporter Configuration](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/): endpoints, headers, and transport configuration.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): OTLP endpoints, headers, compression, and exporter properties.
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): current OTLP configuration properties.

**Key takeaway:** Never export secrets into telemetry hoping the Collector will always scrub them properly. Do not collect credentials in instrumentation in the first place; use allowlists for spans/logs/metrics/baggage/Resource; manage exporter auth via secret management and TLS; and continue applying redaction/filtering across every Collector pipeline as a second defense layer. Test with fake canaries against serialized payloads and backends. If a real secret was exported, revoke/rotate the credential and handle stored data per incident procedures, because deleting an attribute on future exports does not recall historical records.
