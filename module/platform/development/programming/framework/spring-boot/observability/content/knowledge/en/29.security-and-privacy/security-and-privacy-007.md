# PII in Tags

A Spring Boot application records metrics for a customer search endpoint. To debug, a developer adds email, customer ID, and phone number to metric tags. Initially, the dashboard seems convenient because requests for a specific person can be filtered. However, each value creates additional time series, and personal data spreads to the metrics backend, dashboards, alerts, backups, and export systems. When telemetry is retained for a long time or shared across teams, the data access scope goes far beyond the original debugging purpose.

The lesson **PII in Tags** belongs to the **Security and Privacy** chapter of the **SPRING_BOOT_OBSERVABILITY** module. This module teaches how to set up observability for Spring Boot with Micrometer Observation, metrics, logs, and distributed tracing; understand context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

> **Principle:** Never put PII directly into metric tags or telemetry attributes that may be widely exported. Metrics require finite, stable, non-personally-identifiable dimensions. If you need to investigate a specific user or request, use a controlled random correlation ID in logs/traces with appropriate access policies, retention, and redaction. Hashing does not automatically turn personal data into anonymous data.

## 1. Learning Objectives

After this lesson, you will be able to:
1. Explain PII and why telemetry can expose personal data.
2. Identify direct identifiers and quasi-identifiers in tags, logs, traces, and baggage.
3. Understand cardinality, cost, and risks of placing user-specific values in metric labels.
4. Design low-cardinality dimensions instead of email, phone, customer ID, and IP.
5. Distinguish between anonymization, pseudonymization, masking, hashing, and redaction.
6. Minimize data at the instrumentation/source before export.
7. Use allowlists and normalization for metric tags.
8. Configure redaction/filtering for logs, traces, and Collector pipelines.
9. Manage access, retention, sampling, and data governance for telemetry.
10. Test to ensure PII does not appear in exported signals.

## 2. What Is PII in Observability?

PII (personally identifiable information) is information that can identify an individual directly or when combined with other data. The legal scope varies by jurisdiction and processing context; when building policies, follow applicable laws and your organization's privacy/legal team.

Examples of data that may be PII or sensitive data:
- Full name, email, phone number.
- Home address, date of birth.
- Identity document numbers, bank accounts.
- Customer/user ID if linkable to a person.
- IP address, device identifier, or location data in many contexts.
- Session ID, access token, cookie, or credential that could grant account access.
- Request/response contents containing personal information.

A value that is not a name or email can still identify a person when combined with other data. Precise timestamps, IPs, small regions, and product choices can form a quasi-identifier. Classify data based on data inventory, purpose, linkability, and organizational policy.

## 3. Where Can PII Appear in Telemetry?

Telemetry consists of metrics, traces, logs, and resource/context attributes. PII can slip into many places:

| Signal/Location | Risk Example | Impact |
|---|---|---|
| Metric tags | `user.id`, `email`, `phone` | Cardinality explodes, data proliferates widely |
| Span attributes | `customer.email`, `request.body` | Trace backend stores personal content |
| Span name | `GET /users/alice@example.com` | PII appears in indexes/names |
| Events/exceptions | Exception message containing SQL/input | Sensitive content gets exported |
| Logs/MDC | Request payload, authorization header | Log search easily queries personal data |
| Baggage | `customer.email` propagated across services | PII replicated across network boundaries |
| Resource attributes | Tenant/user-specific values | Attaches PII to the process's telemetry |
| Exemplars/correlation | Identity-linking context | Can link metrics with identifying data |

Check automatic instrumentation as well. HTTP instrumentation may record safer route templates than raw URLs, but high-cardinality URL/query attributes or header capture can still contain sensitive data if misconfigured.

## 4. Why Is PII in Metric Tags Especially Dangerous?

Metric tags identify individual meter time series. If you add a user ID or email, each user can generate one or more series.

Unsafe example:

~~~java
Counter.builder("app.login.attempts")
        .tag("email", userEmail)
        .tag("customer.id", customerId)
        .register(meterRegistry)
        .increment();
~~~

Suppose there are 100,000 users and each user has several tag combinations. The number of series scales with user count instead of a few business categories. Consequences:
- Registry/backend consumes excessive RAM, storage, and index resources.
- Scraping/ingestion/querying becomes slow and expensive.
- Dashboards/alerts become difficult to aggregate.
- Personal data is copied to multiple telemetry systems.
- Retention, deletion, access, and auditing requirements become hard to satisfy.

Metric tags should describe groups with a finite number of values, such as operation, outcome, channel, coarse region, and `error.type`.

## 5. Designing Safe Dimensions

Replace personal values with operationally meaningful yet bounded dimensions:

| Unsafe | Better Alternative |
|---|---|
| `email=user@example.com` | `auth.method=password` |
| `customer.id=83921` | `customer.segment=standard` |
| `phone=+84...` | `verification.channel=sms` |
| Raw IP address | `network.class=public/private` or coarse region |
| `order.id=...` | `operation=order.create` |
| Raw URL with user ID | `route=/users/{userId}` |
| `exception.message` | `error.type=validation/timeout/constraint` |
| Raw tenant ID | `tenant.tier=free/business/enterprise` if policy permits |

Alternatives are safe only if values are genuinely bounded and cannot re-identify individuals in that specific context. Overly small regions, overly granular segments, or tenant tiers with very few members can still create privacy risks.

### 5.1 Allowlist and Normalization

Do not pass raw input directly into tags. Normalize to an allowed set:

~~~java
enum LoginMethod {
    PASSWORD,
    OIDC,
    SAML,
    UNKNOWN
}

LoginMethod normalizeMethod(String raw) {
    if (raw == null) {
        return LoginMethod.UNKNOWN;
    }
    return switch (raw.toLowerCase(Locale.ROOT)) {
        case "password" -> LoginMethod.PASSWORD;
        case "oidc" -> LoginMethod.OIDC;
        case "saml" -> LoginMethod.SAML;
        default -> LoginMethod.UNKNOWN;
    };
}
~~~

Use the normalized enum value:

~~~java
Counter.builder("app.login.attempts")
        .tag("method", normalizeMethod(method).name().toLowerCase(Locale.ROOT))
        .register(meterRegistry)
        .increment();
~~~

An allowlist keeps cardinality bounded and prevents arbitrary input from flowing directly into telemetry. It does not replace data classification; an allowlisted value can still be sensitive if it reveals personal attributes.

## 6. Metrics, Traces, and Logs Have Different Purposes

Do not try to solve every need by putting the same field into every signal:

| Signal | Used For | Data Principle |
|---|---|---|
| Metrics | Aggregate trends, SLOs, alerts | Bounded dimensions, no PII |
| Traces | Request/dependency flow and latency | Minimal attributes, avoid payloads/identities |
| Logs | Event details and diagnostics | Structured fields, redaction, access/retention |
| Baggage | Propagating context across services | Only required keys/values, no secrets/PII |
| Resource attributes | Service/process/deployment metadata | Stable metadata, no user/request data |

If you need to find a specific request, use a trace ID or random correlation ID. This ID may still count as pseudonymous personal data if it can be linked back to a user, so apply appropriate access controls and retention. Never turn it into a metric tag.

## 7. Hashing Does Not Mean Anonymization

Hashing an email or customer ID does not automatically make data anonymous.

Risks:
- Emails/phones have predictable value spaces; attackers can dictionary-attack hashes.
- Unsalted hashes or shared salts allow linking the same person across systems.
- Stable hashes allow tracking an individual's behavior over time.
- Hashed values still have cardinality proportional to the number of users.
- If the organization retains a mapping or can re-link, the data typically remains pseudonymous.

Example of what not to do:

~~~java
String tag = sha256(userEmail);
counter.tag("user", tag);
~~~

This still creates per-user series and enables long-term linkability. If the business needs cohort analysis, prefer aggregating into sufficiently large segments or privacy-preserving analytics approved by the privacy team. Never invent a hashing scheme for metric tags to circumvent data policy.

## 8. Redaction, Masking, Pseudonymization, and Anonymization

| Technique | Meaning | Caveats |
|---|---|---|
| Redaction | Removing fields/data from telemetry | Preferred when the data is not needed |
| Masking | Replacing part of a value with masking characters | The remaining part may still be identifying |
| Pseudonymization | Replacing an identifier with another token/code, linkable via mapping/key | Still requires protection when re-linkable |
| Anonymization | Transforming so individuals are no longer reasonably identifiable | Hard to achieve; must evaluate re-identification risk |
| Aggregation | Grouping data into buckets/totals | Small groups can still disclose individuals |

Email masking like `a***@example.com` can still be identifying if the domain or prefix is distinctive. Recording only the last four digits of an account may also suffice to link with other data. Remove the field entirely if there is no clear operational purpose.

## 9. Minimizing PII at the Source

The best redaction happens before data enters the telemetry pipeline:
- Never create metric tags from raw request parameters.
- Never record request/response bodies in spans by default.
- Never capture `Authorization`, `Cookie`, `Set-Cookie`, or token headers.
- Use route templates instead of raw paths.
- Normalize `error.type` instead of exception messages.
- Add only required baggage fields.
- Keep Resource attributes at the service/deployment level; do not attach user context.
- Use structured logging with a field allowlist.

Safer structured log example:

~~~java
log.info("Login attempt method={} outcome={}",
        normalizedMethod,
        "rejected");
~~~

Avoid:

~~~java
log.info("Login failed email={} password={} body={}",
        email, password, requestBody);
~~~

Do not rely solely on downstream redaction to fix unsafe instrumentation. Source minimization reduces the risk of sensitive data entering buffers, local files, networks, and other exporters.

## 10. Redaction for Traces and OpenTelemetry Collector

The OpenTelemetry Collector provides processors to filter or transform telemetry before exporting to a backend. For instance, you can delete sensitive attributes or filter span/log records per policy. Exact configuration depends on the Collector distribution and processor version.

Illustrative example using the `attributes` processor:

~~~yaml
processors:
  attributes/remove-sensitive:
    actions:
      - key: user.email
        action: delete
      - key: user.phone
        action: delete
      - key: http.request.header.authorization
        action: delete

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [attributes/remove-sensitive, batch]
      exporters: [otlp]
~~~

This is an illustrative configuration; verify the processor type, attribute names, and pipeline schema for your deployed Collector version. A traces-only processor does not automatically delete data in metrics/logs pipelines. Policies must be applied to every signal and every pipeline.

If an attribute has already been sent to the Collector, it has crossed a network boundary and may appear in Collector memory/diagnostics. Collector redaction is defense-in-depth; removal at the source remains essential.

## 11. Protecting Baggage and Context Propagation

Baggage is propagated across service boundaries. A key added to baggage can spread to many downstream services and telemetry systems. Never put emails, phones, customer IDs, account numbers, tokens, or raw session identifiers into baggage just for search convenience.

Prefer tracing-system-generated trace ID/span ID, random correlation IDs that do not encode identity, bounded business categories like operation type, and coarse tenant tier only if genuinely needed and privacy-reviewed.

Limit propagation fields and header sizes. Ensure proxies/gateways do not forward unnecessary baggage to external services. Do not assume baggage is secure just because it is tracing metadata.

## 12. Retention, Access, and Data Governance

Telemetry backends can store data longer than application logs, replicate across regions, and grant access to many teams. Policies must define:
- Collection purpose for each signal.
- Field allowlists and data classification.
- Who has permission to query raw traces/logs.
- Retention per signal/environment.
- How exports, backups, archives, and deletion requests are handled.
- Audit trails for accessing sensitive data.
- Incident procedures when PII has been exported.
- Vendor/region/data residency requirements under applicable laws.

Sampling reduces stored trace volume but is not a privacy control: a trace containing PII can still be sampled and exported. Redaction must run before sampling/export according to the appropriate pipeline policy.

## 13. Testing That PII Does Not Leak Into Telemetry

Build tests using synthetic canary values, never real customer data. Example:

~~~text
PII_CANARY_EMAIL=privacy-canary-482@example.invalid
PII_CANARY_TOKEN=CANARY_SECRET_DO_NOT_EXPORT_7b31
PII_CANARY_PHONE=+840000000000
~~~

Send requests containing canaries through critical code paths and collect test telemetry from:
- Micrometer `MeterRegistry`.
- Observation handlers.
- Tracing exporter/test span reporter.
- Logging appender or test log sink.
- Collector output if the test pipeline includes one.

Assert that canaries do not appear in metric names/tags, span names/attributes/events, baggage, log fields, or exported payloads. Also test exception, invalid input, timeout, and retry paths.

### 13.1 Testing Cardinality

Send many requests with different emails/customer IDs but the same channel/operation category. Confirm the meter ID count does not grow with user count, tag values stay within the allowlist, no raw URL/query/body exists in span attributes, and logs contain only approved fields.

Do not just grep a single log line; PII can hide in exception causes, nested attributes, or resource metadata.

## 14. Incident Response When PII Has Been Exported

If PII is discovered in metrics/traces/logs:
1. Identify the field, signal, service, timeframe, and receiving backend.
2. Stop new data from entering via a source fix or pipeline filter.
3. Determine retention scope, replicas, exports, backups, and who had access.
4. Notify privacy/security owners per the organization's incident process.
5. Assess notification obligations under applicable laws/policies.
6. Delete or restrict data per backend capabilities and approved retention policy.
7. Rotate/revoke credentials if secrets/tokens were also exposed.
8. Inspect dashboards, alerts, exemplars, and downstream copies.
9. Add regression tests with canary values.
10. Document root cause and instrumentation/policy changes to prevent recurrence.

Do not assume deleting a series from a dashboard means the data has been removed from storage, replicas, or backups.

## 15. Troubleshooting

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Metric series grow with user count | User ID/email used as a tag | Remove personal tag, use a bounded segment |
| Trace backend can search for emails | HTTP/body/header capture or custom attribute | Redact at source and Collector |
| PII appears in logs despite app logger | Exception message, access log, or agent instrumentation | Check appenders/agents and exception chains |
| Hashed user ID still has high cardinality | Hash is still unique per user | Remove identifier from metric dimensions |
| PII spreads to downstream services | Baggage/header propagation | Remove key and allowlist propagation |
| Collector redaction has no effect | Processor missing from signal pipeline or wrong key | Check traces/metrics/logs pipelines |
| PII appears only on errors | Exception message/cause contains request data | Normalize `error.type` and scrub exception output |
| Resource attribute contains tenant | Resource built from request context | Use only stable service/process metadata |
| Cannot delete data from backend | Retention/replication/backup behavior | Follow incident process and backend deletion capabilities |
| Canary tests pass but production leaks | Tests miss real code paths/agents/exporters | Test end-to-end against a production-like pipeline |

## 16. Playbook: Removing PII From Metric Tags

**Scenario:** A login attempts metric has an `email` tag and series counts are growing with the user population.

1. Identify the meter name, tag keys, and where the meter is created.
2. Stop creating tags from email/phone/customer ID at the source.
3. Replace them with bounded dimensions such as `auth.method`, `outcome`, and allowlisted `channel`.
4. Check whether auto-instrumentation captures HTTP headers, query parameters, or user context.
5. Identify which metric backends stored historical series and their retention/deletion policies.
6. Deploy the source fix and appropriate Collector filters for traces/logs if needed.
7. Send synthetic canary values through login success/failure paths.
8. Confirm canaries do not appear in metrics, traces, logs, or baggage.
9. Monitor series count/cardinality and error rate after deployment.
10. Conduct an incident/privacy review if real data was exported.

Do not just edit the dashboard query to hide the tag. You must stop new data from being recorded and evaluate already-stored copies.

## 17. Self-Check Exercises

**Exercise 1 — Cardinality.** Why does a `customer.id` tag increase series counts and backend costs even if the ID is hashed?

**Exercise 2 — Pseudonymization.** Does hashing an email make data completely anonymous? Give at least two reasons.

**Exercise 3 — Dimension Design.** What useful yet bounded dimensions can replace `email` in a login metric?

**Exercise 4 — Signal Choice.** When needing to locate a specific request, why is a trace ID/correlation ID in logs/traces better suited than a metric tag?

**Exercise 5 — Baggage.** Why is a customer email in baggage more dangerous than a local custom log field?

**Exercise 6 — Collector.** Why does deleting an attribute in the traces pipeline not guarantee metrics and logs are also redacted?

**Exercise 7 — Sampling.** Does sampling replace redaction? Explain.

**Exercise 8 — Incident.** PII has appeared in the telemetry backend and has been replicated. List the containment, assessment, and remediation steps.

### Answer Hints

1. Each ID creates a tag combination/series; hashing does not reduce the number of unique values.
2. Emails are vulnerable to dictionary attacks; stable hashes enable linking the same person; mappings/keys allow re-identification.
3. `auth.method`, `outcome`, `channel`, or `user.segment` with allowlisted values and groups large enough to prevent re-identification.
4. Trace/correlation IDs support investigating a single event without creating separate time series per request/user.
5. Baggage can propagate across multiple processes and boundaries, replicating data into downstream systems.
6. The Collector has separate pipelines for traces, metrics, and logs; processors must be applied to each signal.
7. No. Sampling only reduces record counts; sampled records can still contain PII.
8. Block new ingestion, determine scope/backends/replicas/backups/access, notify owners, assess obligations, delete/restrict per policy, add regression tests, and document root cause.

## 18. Official References

- [OpenTelemetry — Sensitive Data](https://opentelemetry.io/docs/security/handling-sensitive-data/): identifying and handling sensitive data in telemetry.
- [OpenTelemetry Collector — Transform Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/transformprocessor): filtering/transforming attributes and telemetry data.
- [OpenTelemetry Collector — Attributes Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/attributesprocessor): inserting, updating, hashing, or deleting attributes per policy.
- [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/): standardizing attribute names and signal conventions.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation context, handlers, and conventions.
- [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html): bounding/normalizing meter IDs and tags.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): tracing propagation, baggage, and span configuration.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): logging configuration and structured logging.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data to exclude, protect, and govern in logs.
- [NIST Privacy Framework](https://www.nist.gov/privacy-framework): managing privacy risk and the data processing lifecycle.

**Takeaway:** Telemetry can replicate personal data across metric backends, trace storage, log indexes, Collectors, and backups. Keep metric tags bounded and non-identifying; minimize data at the source; allowlist fields; redact per signal; and govern baggage, access, and retention. Hashing neither automatically anonymizes data nor solves cardinality. Use synthetic canary tests across the whole pipeline, and handle exported PII as an incident with concrete storage and replication scope.
