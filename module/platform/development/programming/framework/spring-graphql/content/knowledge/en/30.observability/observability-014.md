# Do Not Include Sensitive Queries in Traces

## 1. Why Can GraphQL Queries Expose Data?

Traces help identify the cause of slow or failing requests by storing spans, attributes, and events for each execution. However, telemetry is typically sent to centralized systems, accessed by multiple teams, and retained longer than ordinary application logs. If traces contain GraphQL documents, input variables, or error messages with real data, sensitive information can escape the service's security boundary.

A GraphQL operation can contain:

- Personal information such as emails, phone numbers, addresses, or dates of birth.
- Financial information such as account numbers, card numbers, amounts, or transaction data.
- Health information or protected category data.
- Credentials such as access tokens, API keys, passwords, or verification codes.
- Internal data such as tenant IDs, customer codes, contract details, or internal business structures.

GraphQL documents can embed literal values directly in arguments. Variables are typically sent in the request body. If instrumentation, logs, or an APM record the document or payload, those values can end up in traces or logs.

The goal is to retain enough metadata to investigate performance and errors while stripping data that trace viewers do not need to see.

## 2. Places That Can Contain Sensitive Data

`graphql.document` is not the only risk. Audit the entire path of the request and telemetry:

| Location | Example | Risk |
| --- | --- | --- |
| GraphQL document | `customerByEmail(email: "alice@example.com")` | Literal sits directly in the query text |
| GraphQL variables | `{ "email": "alice@example.com" }` | Value sent in the request payload |
| Operation name | `customer_0981234567` | Clients can embed data in the operation name |
| Span name | `query customer_0981234567` | Data appears directly in the span name and affects cardinality |
| GraphQL error message | `Invalid value for email alice@example.com` | Error events can preserve the full message |
| Exception message/stack trace | `Payment failed for card 4111...` | Logs or exception events may contain input values |
| HTTP headers | `Authorization`, `Cookie`, custom API keys | Credentials may be recorded in transport logs or span attributes |
| HTTP request body | JSON containing `query` and `variables` | Body capture or debug logging may store the entire payload |
| Custom Observation/Span attributes | `user.email`, `tenant.id`, `query` | Custom code may inject data into telemetry |

Even field names or query structure can reveal internal details. For example, a field named `internalRiskScore` can expose business logic the API does not want publicized. Therefore, replacing literals with `?` reduces value leakage but is not always enough to make a document completely safe.

## 3. Distinguishing Document, Variables, and Operation Name

A GraphQL request typically has three parts that must be managed separately:

```graphql
query CustomerByEmail($email: String!) {
    customerByEmail(email: $email) {
        id
        displayName
    }
}
```

Variables:

```json
{
  "email": "alice@example.com"
}
```

- **Document** describes the operation structure and selected fields.
- **Variables** hold dynamic values passed into arguments.
- **Operation name** is the client-chosen name for the operation, such as `CustomerByEmail`.

Using variables instead of literals keeps the document reusable and reduces the risk of real values appearing in query text. However, variables can still be recorded if the HTTP body, WebSocket payload, or request object is logged/captured.

Operation name is also supplied by the client. Do not append emails, user IDs, tenant IDs, or transaction codes to the operation name. Operation names should be fixed, follow a convention, and contain no per-request values.

## 4. What Does Spring GraphQL Put in Observations by Default?

Spring for GraphQL integrates Micrometer through `GraphQlObservationInstrumentation`. Under the default convention, the `graphql.request` Observation has the following KeyValues:

| Group | Key | Meaning |
| --- | --- | --- |
| Low cardinality | `graphql.operation.type` | `query`, `mutation`, `subscription`, or `operation` |
| Low cardinality | `graphql.outcome` | `SUCCESS`, `REQUEST_ERROR`, or `INTERNAL_ERROR` |
| High cardinality | `graphql.execution.id` | Execution ID of the request |
| High cardinality | `graphql.operation.name` | Operation name provided by the client |

Spring GraphQL's default convention does not add raw GraphQL documents or variables to these KeyValues. This is a safer starting point than recording the entire request, yet you still need to check other instrumentations and custom conventions in your application.

`graphql.operation.name` is client-controlled data. It is classified as high cardinality, intended only for traces, and can contain data if clients choose unconventional names. Do not treat high cardinality as synonymous with safe or non-sensitive.

## 5. An Easily Overlooked Risk: GraphQL Error Events

Spring for GraphQL records errors in GraphQL responses as Observation Events. By default convention, the event name reflects the error type and the contextual name contains the full GraphQL error message.

For example, a parser error can indicate the offending token. A resolver error can also include argument values or information from an underlying exception. If the message contains an email, token, account number, or personal data, trace events can store that exact content even though the raw query was never added as a span attribute.

Therefore, control all of the following:

- Messages returned from `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver`.
- Parse/validation error messages generated by the GraphQL engine.
- Exception messages written to logs or span events.
- Custom Observation events created by the application.

Do not pass `exception.getMessage()` directly into a GraphQL error or event if the message could contain input data. Return normalized messages and keep technical details in controlled internal logging systems.

## 6. Distinguishing Spring GraphQL Micrometer from the OpenTelemetry Java Agent

An application may simultaneously run:

1. Spring for GraphQL's `GraphQlObservationInstrumentation`.
2. The OpenTelemetry Java Agent automatically instrumenting GraphQL Java.
3. HTTP instrumentation from Spring Framework or the Java Agent.
4. Custom organizational tracing, logging, or APM agents.

These components do not necessarily share the same data collection policy. The fact that Spring GraphQL omits documents in its default convention does not prove that a Java Agent or another APM does not capture documents either.

Under current OpenTelemetry semantic conventions, the `graphql.document` attribute is opt-in. If instrumentation records the document, it should strip sensitive data where it can reliably identify and redact it. OpenTelemetry also warns that client-provided operation names can have high cardinality and recommends against using them in default span names.

Check the actual configuration of every instrumentation running in the same JVM. Do not read only Spring Boot configuration and conclude traces are safe.

## 7. Use Variables Instead of Literals in Queries

Avoid writing personal values or secrets directly inside GraphQL documents.

Avoid:

```graphql
query {
    customerByEmail(email: "alice@example.com") {
        id
        displayName
    }
}
```

Prefer:

```graphql
query CustomerByEmail($email: String!) {
    customerByEmail(email: $email) {
        id
        displayName
    }
}
```

Send values in variables:

```json
{
  "email": "alice@example.com"
}
```

This keeps documents stable, cacheable, and easier to sanitize for literals. Still, variables remain sensitive data. Never record them in logs, span attributes, exception messages, or HTTP body captures. When diagnostics are needed, record operation type, item counts, outcome, and safely designed correlation IDs.

## 8. Normalize Operation Names and Use Persisted Queries

Operation names should reflect functionality, not individual user data:

| Unsafe | Fixed name to use |
| --- | --- |
| `FindCustomer_alice@example.com` | `FindCustomer` |
| `GetInvoice_123456789` | `GetInvoice` |
| `SearchTenant_tenant-93` | `SearchTenant` |
| `VerifyToken_eyJhbGci...` | `VerifySession` |

For public APIs or untrusted clients, consider persisted queries/trusted documents. The server accepts only pre-registered documents identified by a controlled ID or hash. This constrains operation structure, prevents clients from sending arbitrary documents, and creates a stable identifier for observability.

If using a document hash as a trace attribute, normalize the query before hashing and do not put high-cardinality hashes into metric tags. Hashing is not data encryption: for small query sets or predictable values, someone with trace access could still test guesses with a dictionary attack.

## 9. Keep Only Necessary Metadata in Observation Conventions

Spring GraphQL allows replacing the default convention with an `ExecutionRequestObservationConvention` bean. If you do not want client-sent operation names appearing in traces, override high-cardinality KeyValues to retain only the execution ID.

Example for Spring Boot:

```java
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;
import org.springframework.graphql.observation.ExecutionRequestObservationConvention;

@Configuration(proxyBeanMethods = false)
public class GraphQlTracePrivacyConfig {

    @Bean
    ExecutionRequestObservationConvention executionRequestObservationConvention() {
        return new DefaultExecutionRequestObservationConvention() {

            @Override
            public KeyValues getHighCardinalityKeyValues(
                    ExecutionRequestObservationContext context) {

                // Keep execution ID for correlation, omit client-provided operation name.
                return KeyValues.of(executionId(context));
            }
        };
    }
}
```

`executionId(context)` is a protected method on `DefaultExecutionRequestObservationConvention`. This override retains the default execution ID while stripping `graphql.operation.name` from the GraphQL request's high-cardinality KeyValues.

If the application needs operation names for investigation, enforce a server-side allowlist of operation names and validate values before permitting them in traces. Do not add raw queries or variables to conventions merely to make debugging more convenient.

## 10. Add Only Safe Low-Cardinality Metadata

When you need to distinguish API versions or functional groups, prefer fixed, finite values:

```java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;
import org.springframework.graphql.observation.ExecutionRequestObservationConvention;

@Configuration(proxyBeanMethods = false)
public class SafeExecutionConventionConfig {

    @Bean
    ExecutionRequestObservationConvention executionRequestObservationConvention() {
        return new SafeExecutionConvention();
    }
}

final class SafeExecutionConvention
        extends DefaultExecutionRequestObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ExecutionRequestObservationContext context) {

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("graphql.api.version", "v1"));
    }
}
```

The value `v1` does not vary per user or request, so its cardinality is low. Other useful tags might be `client.tier=internal|partner|public` or `deployment.region=ap-southeast-1`, provided the value set is controlled.

Do not add the following values to low-cardinality KeyValues:

- Email, phone number, user ID, or tenant ID.
- Execution ID, request ID, or session ID.
- GraphQL documents, variables, or raw URLs.
- Search terms, free-text inputs, or transaction IDs.

Unbounded values both inflate time series counts and risk carrying sensitive data.

## 11. Configuring the OpenTelemetry Java Agent for GraphQL

If the application uses the OpenTelemetry Java Agent with GraphQL Java instrumentation, the agent has dedicated settings for capturing query documents and sanitizing queries.

To avoid recording documents into spans, configure:

```bash
OTEL_INSTRUMENTATION_GRAPHQL_CAPTURE_QUERY=false
OTEL_INSTRUMENTATION_GRAPHQL_QUERY_SANITIZATION_ENABLED=true
OTEL_INSTRUMENTATION_GRAPHQL_OPERATION_NAME_IN_SPAN_NAME_ENABLED=false
```

Meaning:

| Configuration | Effect |
| --- | --- |
| `OTEL_INSTRUMENTATION_GRAPHQL_CAPTURE_QUERY=false` | Disables capturing queries into the `graphql.document` span attribute |
| `OTEL_INSTRUMENTATION_GRAPHQL_QUERY_SANITIZATION_ENABLED=true` | Enables sanitizing sensitive literals if queries are still captured |
| `OTEL_INSTRUMENTATION_GRAPHQL_OPERATION_NAME_IN_SPAN_NAME_ENABLED=false` | Prevents client-supplied operation names from entering span names |

In current OpenTelemetry Java Agent releases, GraphQL query capture is enabled by default and query sanitization is also enabled by default. Disabling capture is the stricter option when you do not need document structure in traces. If you need query shapes for investigation, only enable capture after verifying the sanitizer handles the literal types your application uses.

These environment variables belong to the OpenTelemetry Java Agent, not Spring Boot or Spring GraphQL properties. Check your deployed agent version and property names before applying; older names like `query-sanitizer.enabled` were replaced by `query-sanitization.enabled`.

## 12. What Are the Limitations of Document Sanitization?

Sanitization usually replaces literals with placeholders to preserve query structure:

Original query:

```graphql
query FindCustomer {
    customerByEmail(email: "alice@example.com") {
        id
    }
}
```

Sanitized document may look like:

```graphql
query FindCustomer {
    customerByEmail(email: ?) {
        id
    }
}
```

This still lets you recognize fields and selection set structure without keeping literal values. However, a sanitizer cannot always understand the business semantics of every value. It can miss:

- Data encoded or concatenated into strings using custom formats.
- Sensitive values embedded in operation names or aliases.
- Content inside comments or custom directives.
- Values already placed into custom span attributes before the sanitizer runs.
- Variables logged by an HTTP body logger or another APM.
- Error messages or exceptions containing real data.

Thus, a sanitizer is a supplementary defense layer. Never send secrets inside query documents when secure transport authentication mechanisms exist, and do not treat enabling a sanitizer as a license to log entire requests.

## 13. Do Not Capture Variables, Headers, and HTTP Bodies

Variables usually live in the JSON body of an HTTP request or the payload of a WebSocket message. Even though default Spring GraphQL Observations do not attach variables as KeyValues, another component might log request bodies.

Audit and disable or restrict:

- Request/response body logging in reverse proxies, API gateways, servlet filters, and WebClient/WebTestClient filters.
- Debug logging of HTTP message converters or codecs.
- APM agents with payload-capture features.
- Logging entire `WebGraphQlRequest`, `ExecutionInput`, variables, or WebSocket payloads.
- Capturing `Authorization`, `Cookie`, `Set-Cookie`, API keys, and custom authentication headers.

Do not put credentials inside GraphQL variables. Access tokens should be transmitted via transport authentication mechanisms and handled in the security context. Even so, authentication headers should never appear in span attributes or logs either.

When request logging is needed for diagnostics, emit a filtered record containing operation type, allowlisted operation name, correlation ID, payload size, and outcome. Never log raw bodies.

## 14. Sanitize GraphQL Error Messages Before Creating Responses

Because Spring GraphQL can record full error messages in Observation events, generate safe messages right at the source.

Example using `@GraphQlExceptionHandler` to return a generic message:

```java
import java.util.Map;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class SafeGraphQlErrorAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handlePaymentFailure(
            PaymentGatewayException exception,
            DataFetchingEnvironment environment) {

        // Do not put exception.getMessage() into the response or trace event.
        return GraphqlErrorBuilder.newError(environment)
            .message("Unable to process payment request")
            .extensions(Map.of("code", "PAYMENT_UNAVAILABLE"))
            .build();
    }
}
```

`PaymentGatewayException` is an example business exception of the application. When logging the error, record the correlation ID, exception type, and an internal error code; only write stack traces or original messages in access-controlled logging systems with explicit redaction policies.

For parse/validation errors generated by the GraphQL engine, not every error passes through controller exception handlers. Check whether malformed requests create events containing offending tokens or literals. If they do, handle them in the appropriate instrumentation/collector or restrict exporting those events according to telemetry policy.

## 15. Redaction in the OpenTelemetry Collector

The Collector can act as an extra layer of protection before telemetry is forwarded to a backend. The `opentelemetry-collector-contrib` redaction processor supports attribute allowlists, stripping disallowed keys, and masking pattern-matched values.

Conceptual configuration example:

```yaml
processors:
  redaction/graphql:
    allow_all_keys: false
    allowed_keys:
      - graphql.operation.type
      - graphql.outcome
      - graphql.field.name
      - http.request.method
      - http.response.status_code
    blocked_key_patterns:
      - '(?i).*authorization.*'
      - '(?i).*token.*'
      - '(?i).*password.*'
      - '(?i).*email.*'
    blocked_values:
      - 'Bearer\s+[A-Za-z0-9._-]+'
    masking_string: "[REDACTED]"
    summary: silent
```

In the trace pipeline, place this processor before the exporter:

```yaml
service:
  pipelines:
    traces:
      processors: [redaction/graphql, batch]
```

This is an illustrative example; a complete configuration also requires receivers and exporters for your environment. Adjust the allowlist to match the actual attributes used by dashboards and tracing backends. If `allowed_keys` is too strict, useful metadata may be stripped.

The redaction processor only processes attributes of spans/logs/metric datapoints according to its configuration; do not assume it automatically sanitizes contents in span event names, log bodies, resource attributes, or custom payloads. Verify the exact data types and processor version. Redaction in the Collector also runs after data has already left the application for the Collector, so it does not replace preventing capture at the source.

Per current component documentation, the Collector Contrib redaction processor is at beta stability for traces and alpha for logs/metrics. Evaluate stability and test configurations against your exact deployed Collector version.

## 16. Protecting Telemetry at Storage and Access Layers

Even after stripping queries and variables, traces still contain metadata that must be protected. Control:

- Who has permission to view traces, logs, and metrics.
- Which environments are allowed to export telemetry externally.
- TLS and authentication between applications, Collectors, and backends.
- Retention duration, deletion policies, and data storage locations.
- Access permissions scoped by team/service/tenant.
- Sharing trace IDs in tickets, chat, or support tools.
- Backups and replicas of telemetry data.

Sampling reduces telemetry volume and storage cost, but it is not a redaction measure. A sampled span can still contain sensitive data. Sanitize before sampling/exporting and verify actual stored data in the backend.

## 17. Testing to Detect Leaked Queries or Data

Do not inspect only convention code. Test the final telemetry after it passes through instrumentation, processors, and exporters.

A privacy test should:

1. Create a GraphQL operation containing a synthetic sensitive literal such as `private-test@example.invalid`.
2. Send the same value via variables.
3. Trigger a resolver error whose exception message contains a synthetic marker.
4. Send the request with an `Authorization` header containing a fake token.
5. Collect spans, events, and logs via a test exporter or test Collector.
6. Assert that the markers do not appear in span names, span attributes, event names, event attributes, log bodies, or log attributes.
7. Assert that safe metadata such as operation type, outcome, and correlation ID remain present.

Conceptual assertion example:

```java
import static org.assertj.core.api.Assertions.assertThat;

assertThat(exportedSpan.getName()).doesNotContain("private-test@example.invalid");
assertThat(exportedSpan.getAttributes().toString())
    .doesNotContain("private-test@example.invalid")
    .doesNotContain("test-token-value");
```

The snippet above illustrates asserting against a `SpanData` collected by a test exporter; `exportedSpan` is test data, not a built-in Spring variable. In real tests, inspect span events and each event's attributes as well, not just `getAttributes()` on the span. Also check logs because exception messages may be logged independently of traces.

Include regression tests for these cases:

- Literals in documents.
- Variables in request bodies.
- Client-supplied operation names.
- GraphQL parser errors with offending tokens.
- Resolver exceptions with sensitive messages.
- Headers/cookies and WebSocket `connection_init` payloads.
- Custom Observation conventions or custom span attributes.
- Query sanitizer and Collector redaction.

## 18. Investigation Workflow When Sensitive Data Is Found in Traces

When you discover queries or sensitive values in traces, identify the source before fixing:

| Signal in trace | Where to check |
| --- | --- |
| `graphql.document` attribute | OpenTelemetry GraphQL instrumentation, custom span processors, or APM agents |
| Span name contains operation name | GraphQL Java instrumentation and custom span naming conventions |
| Attribute contains email/ID/token | Custom Observation conventions, baggage, HTTP header capture, or application instrumentation |
| Event name contains parser error | Spring GraphQL Observation error events and GraphQL parser messages |
| Event contains exception message | DataFetcher exception resolvers, `@GraphQlExceptionHandler`, or exception recording handlers |
| Log body contains query/variables | HTTP filters, access logs, request/response body logging, or WebSocket loggers |
| Data appears in backend despite app redaction | Collector pipelines, exporters, backend enrichment, or duplicate instrumentation |

After identifying the source:

1. Disable unnecessary capture in the instrumentation producing the data.
2. Normalize operation names and error messages.
3. Remove custom attributes without a clear operational purpose.
4. Add redaction/allowlists in the Collector as a second line of defense.
5. Re-test with synthetic markers across the entire export pipeline.
6. Handle already stored traces/logs according to your organization's incident and retention policies.

## 19. Common Mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Spring GraphQL does not record documents yet traces still show queries | OpenTelemetry Java Agent or another APM is capturing `graphql.document` | Audit all instrumentations; disable capture or enable sanitizer |
| Variables appear in logs | HTTP body logging or WebSocket payload logging | Disable body logging or log filtered summaries |
| Operation name contains email/user ID | Client assigns dynamic operation names | Enforce fixed names and allowlists/persisted queries |
| Trace has parser error containing literals | Error events retain full GraphQL error messages | Control error messages or process events at instrumentation/Collector |
| Convention does not remove operation name | Custom convention bean not auto-configured or overridden by another bean | Inspect active beans and exported high-cardinality KeyValues |
| Sanitizer enabled yet data still appears | Sanitizer does not cover variables, operation names, error events, or custom attributes | Pinpoint the exact data source and apply targeted redaction |
| Collector redaction still leaks events | Processor does not process the event/name field carrying data | Sanitize at the source and verify processor capabilities/version |
| Metrics cardinality grows after adding tags | User ID, query hash, or operation name placed in low-cardinality tags | Use only finite value sets for metrics |
| Using sampling yet traces still hold sensitive data | Sampling does not scrub contents of retained spans | Redact before exporting; sampling only reduces volume |
| Logs are safe yet traces still leak | Traces and logs use different instrumentations/processors | Test each signal and exporter independently |

## 20. Checklist for Keeping Sensitive Queries Out of Traces

- [ ] Classify sensitive data in documents, variables, headers, error messages, and custom attributes.
- [ ] Never place emails, user IDs, tokens, or transaction codes in operation names.
- [ ] Use GraphQL variables instead of literals, and do not log variables.
- [ ] Understand the default KeyValues of `GraphQlObservationInstrumentation`.
- [ ] Audit operation names because they are client-supplied and high cardinality.
- [ ] Audit error events because contextual names can hold full GraphQL error messages.
- [ ] Audit the OpenTelemetry Java Agent and APM instrumentations independently of Spring GraphQL.
- [ ] Disable query capture if `graphql.document` is not needed.
- [ ] Enable query sanitization if you still need to retain query shapes.
- [ ] Do not capture HTTP bodies, WebSocket payloads, Authorization, or Cookies.
- [ ] Add only safe metadata with controlled cardinality.
- [ ] Normalize error messages before creating GraphQL responses/events.
- [ ] Use Collector redaction/allowlists as an additional defense layer.
- [ ] Control access permissions, exports, retention, and trace sharing.
- [ ] Test span names, span attributes, event attributes, and logs with synthetic markers.

## Conclusion

Keeping sensitive queries out of traces requires controlling the entire path of GraphQL data. By default, Spring for GraphQL only places operation type, outcome, execution ID, and operation name into `graphql.request`; it does not automatically add raw documents or variables in its default convention. However, client-supplied operation names and GraphQL error events can still carry unsafe content. The OpenTelemetry Java Agent, HTTP body logging, WebSocket logging, or custom instrumentation can also collect extra data.

Use variables instead of literals, normalize operation names, keep only necessary metadata, sanitize error messages, check OTel agent query capture settings, and use Collector redaction as an extra defense layer. Finally, test the actually exported telemetry rather than inspecting only configuration in source code. Good traces should help investigate slow requests and fields without storing emails, tokens, payloads, or users' private content.

## References

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — `DefaultExecutionRequestObservationConvention` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/DefaultExecutionRequestObservationConvention.html)
- [Spring for GraphQL — `ExecutionRequestObservationContext` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/ExecutionRequestObservationContext.html)
- [OpenTelemetry — Semantic Conventions for GraphQL Server Spans](https://opentelemetry.io/docs/specs/semconv/graphql/graphql-spans/)
- [OpenTelemetry — Handling Sensitive Data](https://opentelemetry.io/docs/security/handling-sensitive-data/)
- [OpenTelemetry Collector Contrib — Redaction Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/redactionprocessor)
- [OpenTelemetry Java Agent — Configuration](https://opentelemetry.io/docs/zero-code/java/agent/configuration/)
