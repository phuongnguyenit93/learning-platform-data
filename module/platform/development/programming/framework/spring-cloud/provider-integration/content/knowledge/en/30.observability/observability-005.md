# Structured logs, correlation IDs, and provider request IDs

## 1. Context and objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, we practice integrating Spring Boot with managed services from **AWS, Azure, and Google Cloud** using the corresponding Spring Cloud libraries and SDKs. When a request traverses an API, object storage, database, message broker, and asynchronous workers, logs must hold enough context for operations teams to link events together and look up the exact request on the cloud provider side.

Consider an API downloading a document from Azure Blob Storage. The API returns 503. A log containing only “Storage request failed” is not enough to investigate. Operations needs to know which service handled the request, which correlation ID, which trace/span, which Blob operation, which HTTP status, and which `x-ms-request-id` Azure returned. When contacting Microsoft Support, the service request ID lets them look up the request inside Azure's systems.

This lesson focuses on three layers of identifiers and how to include them in logs:

- **Structured logging:** recording events as stable JSON fields so log systems can filter, group, and query them.
- **Correlation ID:** an application-managed identifier linking requests, logs, and jobs belonging to the same business flow.
- **Provider request ID:** an identifier returned by a cloud service for a specific request, used for provider-side investigation.

After this lesson, you will be able to:

- Enable structured JSON logging in Spring Boot 3.5.
- Design a unified log schema across services and cloud providers.
- Generate, validate, and propagate correlation IDs across HTTP, messages, and background processing.
- Include trace ID/span ID from Micrometer Tracing in logs.
- Capture AWS request IDs, Azure service request IDs, and request details provided by Google APIs.
- Distinguish request ID, trace ID, correlation ID, message ID, and idempotency key.
- Redact secrets/PII, prevent log injection, and control log storage costs.
- Write tests verifying that critical fields appear in logs.

## 2. Distinguishing identifier types

Different IDs often appear together in a single log event yet have different origins and purposes.

| Identifier | Who creates it? | Scope | Used for |
|---|---|---|---|
| **trace_id** | Tracing SDK/propagator | One distributed trace | Finding the full technical journey |
| **span_id** | Tracing SDK | One operation within a trace | Finding a specific HTTP call, SDK call, or handler |
| **correlation_id** | Application or trusted gateway | One request/job/business flow | Connecting logs and events across multiple services |
| **internal request_id** | Application/API | One HTTP request or processing run | Returning to callers and finding logs for that request |
| **provider_request_id** | AWS/Azure/Google API | One request to a cloud service | Looking up a request with the provider/support |
| **client_request_id** | Application/client SDK | One request sent to a provider | Finding a request from the client side if echoed/logged by the service |
| **message_id** | Broker or producer | One message | Finding a specific message send/receive |
| **idempotency_key** | Application/caller | One retryable business action | Preventing duplicate side effects |

For example, a job may keep one `correlation_id` end-to-end, while each call to S3, Blob Storage, or Pub/Sub receives a different `provider_request_id`. When an SDK retries, each attempt can have its own request ID. Never use a provider request ID as a correlation ID because the application does not control its lifecycle.

**A trace ID is not a business correlation ID either.** Traces can be sampled out, recreated at trust boundaries, or split into multiple traces on long-running jobs. A correlation ID/job ID can persist across retries and multiple traces.

## 3. Structured logging in Spring Boot 3.5

Structured logging writes logs as fields with stable names and types, typically JSON. Spring Boot natively supports three JSON formats:

- **ECS (Elastic Common Schema):** suited for Elastic-based stacks.
- **GELF:** Graylog's JSON format.
- **Logstash:** a common JSON format in ELK pipelines.

Structured logging has been built in since Spring Boot 3.4. In Spring Boot 3.5, you can enable ECS for console output:

~~~yaml
spring:
  application:
    name: document-api

logging:
  structured:
    format:
      console: ecs
    ecs:
      service:
        name: document-api
        version: 1.0.0
        environment: production
~~~

Or use Logstash:

~~~yaml
logging:
  structured:
    format:
      console: logstash
~~~

Spring Boot automatically includes MDC key/value pairs in structured JSON logs. You can also add per-event fields via SLF4J's fluent logging API with `addKeyValue`. Once structured formatting is enabled, avoid manually concatenating JSON strings or logging a string containing nested JSON inside the message.

### 3.1. Why shouldn't you log just a plain sentence?

Plain-text log:

~~~text
ERROR Blob download failed for document 42 with status 503
~~~

Structured log:

~~~json
{
  "@timestamp": "2026-11-24T10:15:30.123Z",
  "log.level": "ERROR",
  "service.name": "document-api",
  "message": "Cloud dependency call failed",
  "provider": "azure",
  "provider_service": "blob",
  "operation": "download",
  "correlation_id": "req-7f3a",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "provider_request_id": "8f0a-example",
  "http_status": 503,
  "error_type": "service_unavailable"
}
~~~

The log platform can filter `provider=azure`, group by `operation=download`, search by `correlation_id`, or cross-reference `provider_request_id` with provider diagnostics.

## 4. Designing a shared log schema

Not every log event needs every field. However, standardize the names and meanings of commonly used fields.

| Field | Type | Meaning |
|---|---|---|
| `@timestamp` | timestamp | UTC timestamp of the log event |
| `log.level` | string | INFO, WARN, ERROR, DEBUG |
| `service.name` | string | Service name |
| `service.version` | string | Application version |
| `deployment.environment` | string | local, staging, production |
| `message` | string | Concise, stable description |
| `trace_id` | string | Trace ID if present |
| `span_id` | string | Span ID if present |
| `correlation_id` | string | Business/request correlation ID |
| `request_id` | string | Internal request ID if needed |
| `provider` | string | aws, azure, gcp |
| `provider_service` | string | s3, blob, servicebus, pubsub, rds |
| `operation` | string | get_object, upload, send_message, query |
| `outcome` | string | success, error, timeout, rejected |
| `http_status` | integer | HTTP status if applicable |
| `error_type` | string | Standardized error category |
| `provider_request_id` | string | ID returned by the provider |
| `client_request_id` | string | Client-sent ID if supported by the service |
| `retry_attempt` | integer | Attempt number if instrumented |
| `duration_ms` | number | Operation duration |

Each log event should answer a specific question. For example, a log starting message processing does not need a provider request ID; an S3 call failure log should include provider, service, operation, error type, and request ID if the response provided one.

Keep field names consistent across services. Do not let service A use `correlationId`, service B use `correlation_id`, and service C use `requestCorrelation`.

## 5. Including trace ID and span ID in logs

When Micrometer Tracing is configured in Spring Boot, trace ID and span ID can be placed into MDC. With ECS/Logstash structured logging, MDC fields are included in the JSON output.

Example correlation pattern configuration for text-mode console logs:

~~~yaml
logging:
  pattern:
    correlation: "[%X{traceId:-},%X{spanId:-}] "
~~~

To also include a business correlation ID, the application puts `correlation_id` into MDC for the duration of the request. With structured logging active, that field appears in the JSON output.

Trace ID/span ID help investigate a specific span. Correlation ID helps find the same business flow across HTTP, queues, and workers. Some logs may only have correlation ID when a trace is sampled out; startup logs may have neither.

Spring Boot/Micrometer typically populate trace ID and span ID in MDC under the keys `traceId` and `spanId`. If your centralized log schema expects `trace_id`/`span_id` or `trace.id`/`span.id`, normalize field names in a logging customizer or log ingestion pipeline; do not assume MDC keys and schema field names already match.

## 6. Generating and validating correlation IDs for HTTP requests

An application may receive `X-Correlation-ID` from an API gateway or client. Never trust arbitrary incoming header values: enforce length and character restrictions to prevent log injection or malformed fields. If missing or invalid, generate a new ID.

Example Servlet filter:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class CorrelationIdFilter extends OncePerRequestFilter {
    public static final String HEADER = "X-Correlation-ID";
    public static final String MDC_KEY = "correlation_id";

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String candidate = request.getHeader(HEADER);
        String correlationId =
                candidate != null && SAFE_ID.matcher(candidate).matches()
                        ? candidate
                        : UUID.randomUUID().toString();

        String previous = MDC.get(MDC_KEY);
        MDC.put(MDC_KEY, correlationId);
        response.setHeader(HEADER, correlationId);

        try {
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove(MDC_KEY);
            } else {
                MDC.put(MDC_KEY, previous);
            }
        }
    }
}
~~~

This filter:

- Accepts only alphanumeric characters, dots, underscores, and hyphens, up to 64 characters.
- Generates a UUID if the header is missing or invalid.
- Places the correlation ID in MDC during request handling.
- Returns the `X-Correlation-ID` header so callers can reference it when contacting support.
- Restores the previous MDC value so servlet threads do not leak IDs into subsequent requests.

In systems spanning multiple trust boundaries, a gateway may mint a fresh internal correlation ID and record the external request ID separately. Never use a correlation ID for authentication, authorization, or proving caller identity.

## 7. Propagating correlation IDs via HTTP clients

Micrometer Tracing automatically propagates W3C trace context when using Spring Boot auto-configured HTTP client builders. `X-Correlation-ID` is a separate business field, so the application must propagate it if downstream services should log the same ID.

Example with `RestClient.Builder`:

~~~java
import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class DownstreamClientConfiguration {
    @Bean
    RestClient catalogClient(RestClient.Builder builder) {
        return builder
                .baseUrl("https://catalog.internal")
                .requestInterceptor((request, body, execution) -> {
                    String correlationId =
                            MDC.get(CorrelationIdFilter.MDC_KEY);
                    if (correlationId != null) {
                        request.getHeaders().set(
                                CorrelationIdFilter.HEADER, correlationId);
                    }
                    return execution.execute(request, body);
                })
                .build();
    }
}
~~~

Obtain the builder from the Spring context to retain auto-configuration and tracing instrumentation. If requests run on a background thread, ensure the MDC correlation ID has been propagated before the interceptor executes.

Never overwrite `traceparent` with a correlation ID. These two headers serve distinct purposes and must propagate independently.

## 8. Preserving MDC when switching to background threads

MDC is normally thread-bound. When execution switches from a servlet thread to an executor, `correlation_id` may disappear. When using thread pools, capture and restore MDC to avoid losing IDs or leaking IDs across tasks.

Example `TaskDecorator` for MDC:

~~~java
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public class MdcTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
~~~

Attach the decorator to `ThreadPoolTaskExecutor`:

~~~java
executor.setTaskDecorator(new MdcTaskDecorator());
~~~

This decorator propagates MDC, including `correlation_id`. If the application also needs to propagate Micrometer Observation/trace context, use `ContextPropagatingTaskDecorator` or compose both mechanisms properly; do not replace a trace-propagating decorator with one that only copies MDC. With Reactor, enable Spring Boot's context propagation and store correlation metadata in Reactor Context when appropriate.

## 9. Logging with the SLF4J fluent API

Spring Boot structured logging supports key/value pairs added via the SLF4J fluent API. Example logging a dependency failure:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class CloudCallLogger {
    private static final Logger log =
            LoggerFactory.getLogger(CloudCallLogger.class);

    public void logFailure(
            String provider,
            String providerService,
            String operation,
            String providerRequestId,
            int status,
            String errorType) {

        log.atError()
                .addKeyValue("provider", provider)
                .addKeyValue("provider_service", providerService)
                .addKeyValue("operation", operation)
                .addKeyValue("provider_request_id", providerRequestId)
                .addKeyValue("http_status", status)
                .addKeyValue("error_type", errorType)
                .log("Cloud dependency call failed");
    }
}
~~~

Avoid concatenating every field into the message string. Keep messages short and stable; fields used for filtering belong in structured attributes. If no provider request ID is available, omit the field or write null per your log platform's schema; never fabricate a placeholder ID and label it as a provider request ID.

## 10. Extracting request IDs from AWS SDK for Java 2.x

AWS SDK for Java 2.x exposes the request ID in response metadata when a service responds successfully. On service exceptions, `AwsServiceException`/`SdkServiceException` also exposes the request ID for error lookup.

Example with S3 `HeadObject`:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import software.amazon.awssdk.awscore.exception.AwsServiceException;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadObjectResponse;

public class S3DocumentReader {
    private static final Logger log =
            LoggerFactory.getLogger(S3DocumentReader.class);

    private final S3Client s3;

    public S3DocumentReader(S3Client s3) {
        this.s3 = s3;
    }

    public void inspect(String bucket, String key) {
        try {
            HeadObjectResponse response = s3.headObject(
                    HeadObjectRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .build());

            String requestId = response.responseMetadata().requestId();
            log.atInfo()
                    .addKeyValue("provider", "aws")
                    .addKeyValue("provider_service", "s3")
                    .addKeyValue("operation", "head_object")
                    .addKeyValue("provider_request_id", requestId)
                    .log("S3 object metadata retrieved");
        } catch (AwsServiceException ex) {
            log.atError()
                    .addKeyValue("provider", "aws")
                    .addKeyValue("provider_service", "s3")
                    .addKeyValue("operation", "head_object")
                    .addKeyValue("provider_request_id", ex.requestId())
                    .addKeyValue("http_status", ex.statusCode())
                    .addKeyValue("aws_error_code",
                            ex.awsErrorDetails() == null
                                    ? null
                                    : ex.awsErrorDetails().errorCode())
                    .setCause(ex)
                    .log("S3 request failed");
            throw ex;
        }
    }
}
~~~

Key points to remember:

- On success: read `response.responseMetadata().requestId()`.
- On service error: read `ex.requestId()` and `ex.statusCode()`.
- The AWS error code is more informative than HTTP status alone because multiple service errors share the same HTTP status.
- Do not assume every network/credential error carries an AWS request ID. If the request never reached the service, the provider may not have assigned one.

The AWS SDK may retry internally. The request ID in the final response typically represents the attempt that produced the final result; if you need to inspect individual attempts, use appropriate SDK telemetry/logging and retain per-attempt request IDs. Do not enable full HTTP DEBUG wire logging in production without assessing the risk of logging sensitive headers or bodies.

## 11. Extracting request IDs from Azure SDK for Java

Azure Storage returns the service request ID in the `x-ms-request-id` response header. Clients can send `x-ms-client-request-id` for client-side correlation; these two IDs are not the same.

With Azure Core, successful responses can read headers via `Response.getHeaders()`. Example:

~~~java
import com.azure.core.http.HttpHeaderName;
import com.azure.core.http.rest.Response;
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobProperties;
import java.time.Duration;

public void logBlobProperties(BlobClient blobClient) {
    Response<BlobProperties> response =
            blobClient.getPropertiesWithResponse(
                    null, Duration.ofSeconds(10), Context.NONE);

    String serviceRequestId = response.getHeaders().getValue(
            HttpHeaderName.fromString("x-ms-request-id"));

    log.atInfo()
            .addKeyValue("provider", "azure")
            .addKeyValue("provider_service", "blob")
            .addKeyValue("operation", "get_properties")
            .addKeyValue("provider_request_id", serviceRequestId)
            .log("Blob properties retrieved");
}
~~~

On errors, `BlobStorageException` extends `HttpResponseException`. You can inspect the response and headers:

~~~java
import com.azure.core.http.HttpHeaderName;
import com.azure.storage.blob.models.BlobStorageException;

try {
    // Execute a Blob operation.
} catch (BlobStorageException ex) {
    String serviceRequestId = ex.getResponse() == null
            ? null
            : ex.getResponse().getHeaderValue(
                    HttpHeaderName.fromString("x-ms-request-id"));

    log.atError()
            .addKeyValue("provider", "azure")
            .addKeyValue("provider_service", "blob")
            .addKeyValue("provider_request_id", serviceRequestId)
            .addKeyValue("http_status", ex.getResponse() == null
                    ? null
                    : ex.getResponse().getStatusCode())
            .addKeyValue("azure_error_code", ex.getErrorCode())
            .setCause(ex)
            .log("Azure Blob request failed");
    throw ex;
}
~~~

`x-ms-request-id` is generated by the Azure service. `x-ms-client-request-id` is sent by the client; Azure can echo it in the response when the request is configured to send it. Keep both fields separate in logs, e.g. `provider_request_id` and `client_request_id`.

With the Azure SDK retry policy, one logical call can issue multiple physical HTTP requests. Reading headers only from the final response gives only that response's ID. If you need visibility into every attempt, instrument the HTTP pipeline/retry policy or use tracing; never infer attempt count from a single request ID.

## 12. Extracting request IDs from Google Cloud Java clients

There is no uniform `requestId()` accessor across every Google Cloud Java client and error type. How you obtain a request ID depends on the API, transport, and error details returned by the service.

Some Google APIs return error details using `google.rpc.RequestInfo`. With clients built on Google API GAX, when the API populates that detail on `ApiException`, you can read it:

~~~java
import com.google.api.gax.rpc.ApiException;
import com.google.api.gax.rpc.ErrorDetails;
import com.google.rpc.RequestInfo;

try {
    // Call a Google API.
} catch (ApiException ex) {
    ErrorDetails details = ex.getErrorDetails();
    RequestInfo requestInfo =
            details == null ? null : details.getRequestInfo();
    String providerRequestId =
            requestInfo == null ? null : requestInfo.getRequestId();

    log.atError()
            .addKeyValue("provider", "gcp")
            .addKeyValue("provider_service", "google-api")
            .addKeyValue("provider_request_id", providerRequestId)
            .addKeyValue("status_code", ex.getStatusCode().getCode().name())
            .addKeyValue("error_reason", ex.getReason())
            .setCause(ex)
            .log("Google API request failed");
    throw ex;
}
~~~

This example only applies when the API/service returns `RequestInfo` and the client version provides `getErrorDetails()`. If the detail is absent, leave `provider_request_id` unset; do not substitute a trace ID or message ID.

In Google Cloud Storage Java, `StorageException` provides status code, reason, debug info, and other error fields, though you should not assume it always exposes a generic provider request ID accessor. Check response headers or error details per specific API. With gRPC, metadata/request IDs likewise vary by service and client stub.

Some Google APIs accept a client-supplied `request_id` field for idempotent create/update operations. That field is a **client-supplied request ID**, not a provider-generated request ID. Never log it under `provider_request_id`.

## 13. Request IDs across messages and background processing

When an API sends a message to a queue, propagate the correlation ID with the message so workers log under the same business flow. The provider request ID of the send-message call identifies that broker API call, not the message itself, and should not replace the message ID.

| Component | IDs to log |
|---|---|
| HTTP API | `request_id`, `correlation_id`, `trace_id`, `span_id` |
| Producer calling broker | `correlation_id`, `trace_id`/`span_id`, `provider_request_id` if available |
| Message envelope | `event_id`/`job_id`/`correlation_id`; trace context if needed |
| Consumer | `correlation_id`, `message_id`, `delivery_attempt`, `trace_id`/`span_id` |
| Worker calling storage/database | `correlation_id`, `provider`, `operation`, `provider_request_id` |
| DLQ/replay | original `message_id`, `event_id`, `correlation_id`, `replay_id`, `reason` |

A job can outlive its initial trace. Keep `job_id` or `correlation_id` in business metadata to link logs from later runs. Trace context links technical spans when messages are published/consumed; correlation ID remains useful when traces are sampled out or jobs are replayed.

Do not dump full payloads into logs just to trace messages. Log message ID, event ID, schema version, destination, and error category; store payloads only in access-controlled locations when genuinely required.

## 14. Logging retries and distinguishing logical calls from attempts

An SDK operation can retry internally. Distinguish:

- **Logical operation:** the action the application wants to complete, such as uploading a document.
- **Attempt:** a single physical request sent to the provider.
- **Provider request ID:** the ID of an attempt that reached the provider and returned a response.
- **Retry count:** extra attempts after the initial attempt.

Example of an upload with three attempts:

~~~text
correlation_id = job-42
operation      = upload_blob
attempt 1      = 429, provider_request_id = azure-req-a
attempt 2      = 503, provider_request_id = azure-req-b
attempt 3      = 201, provider_request_id = azure-req-c
final outcome  = success
~~~

If you only log one final line, you know the upload succeeded, but not that the first two attempts were throttled or failed transiently. If you log every attempt, retain the shared correlation ID and a logical operation ID to group them.

A practical convention:

- INFO: log the final outcome of a logical operation when needed for business auditing.
- WARN: log an attempt that hit a retryable failure if it affects latency or carries operational meaning.
- ERROR: log the final failure of a logical operation.
- DEBUG: log transport/SDK details in test environments or during time-boxed investigations.

Do not log the same exception as separate ERROR events at every layer (SDK wrapper, service, controller, and global handler). Choose one layer to own the final error log; other layers can add context or propagate the exception.

## 15. Exceptions, stack traces, and diagnostic details

When logging exceptions:

- Include `error.type` or `error.class` for grouping.
- Include provider status/error code, request ID, and operation when available.
- Attach the throwable so stack traces are available when needed.
- Avoid repeating full stack traces at every layer.
- Never put raw exception messages into metric labels or low-cardinality grouping fields.

Exception messages sometimes contain URLs, resource paths, account names, queries, or fragments of payloads. Inspect them before logging verbatim. Spring Boot structured logging supports bounding stack trace length and depth via `logging.structured.json.stacktrace.*`.

Example:

~~~yaml
logging:
  structured:
    json:
      stacktrace:
        max-length: 8192
        max-throwable-depth: 20
        include-common-frames: false
~~~

Tune limits to ingestion capacity and diagnostic needs. Do not truncate essential root causes, and do not emit hundreds of kilobytes of stack traces on every repeated failure.

## 16. Security: redaction, PII, and log injection

Logs are operational data that can contain sensitive information. Once shipped to a centralized system, multiple people and services may read them.

**Never log the following:**

- Passwords, access tokens, refresh tokens, API keys, account keys, or private keys.
- Azure SAS tokens/query strings or signed URLs.
- HTTP `Authorization`, `Cookie`, `Set-Cookie`, and credential headers.
- Full request/response bodies containing personal data or user documents.
- Database connection strings and secret manager responses.
- Message payloads containing customer data without clear necessity and authorization.

**Preventing log injection:**

- Cap the length of caller-supplied headers.
- Whitelist allowed characters for correlation IDs.
- Use structured fields instead of concatenating user-controlled strings.
- Do not allow newlines in free-form fields to forge new log events.
- Escape/redact untrusted values using your logging framework's encoder.

Provider request IDs are normally diagnostic metadata rather than credentials. Still, restrict access to logs and avoid placing request IDs in public URLs or metric labels.

## 17. Cardinality, indexing, and storage cost

Logs and metrics have different requirements. Provider request ID, correlation ID, and message ID are near-unique values; they make good searchable fields in access-controlled logs, but poor metric labels.

| Value | Structured log | Metric label |
|---|---|---|
| `provider` = aws/azure/gcp | Yes | Yes |
| `operation` = upload/get_object | Yes | Yes |
| `error_type` = timeout/throttled | Yes | Yes |
| `provider_request_id` | Yes, prefer controlled indexing | No |
| `correlation_id` | Yes, indexed per policy | No |
| `trace_id`/`span_id` | Yes or linked by tracing backend | No |
| `customer_id`/`object_name` | Only when permitted and controlled | No |

Some log platforms charge per indexed field. You do not need to index every high-uniqueness field; keep provider request IDs in raw structured logs and index selectively when needed for investigation. Apply retention per environment and criticality, and limit DEBUG/HTTP wire logging.

## 18. Querying logs and investigation runbook

When a request fails, investigate in order:

1. Find `correlation_id` or `request_id` from the API response.
2. Check `trace_id` to open the distributed trace if sampled.
3. Filter logs by `provider`, `provider_service`, `operation`, and `error_type`.
4. Extract `provider_request_id` from the final failed call or target attempt.
5. Cross-reference the AWS request ID, Azure `x-ms-request-id`, or Google API request details when engaging support.
6. Inspect retry logs, status codes, client request IDs, and timestamps to determine which attempt failed.

Example SQL-style query in a JSON-capable log store:

~~~sql
SELECT
  "@timestamp",
  service.name,
  provider,
  provider_service,
  operation,
  http_status,
  provider_request_id,
  error_type,
  message
FROM application_logs
WHERE correlation_id = 'req-7f3a'
ORDER BY "@timestamp";
~~~

Example query by provider request ID:

~~~sql
SELECT
  "@timestamp",
  service.name,
  correlation_id,
  trace_id,
  operation,
  provider_request_id,
  message
FROM application_logs
WHERE provider_request_id = '8f0a-example';
~~~

Field names and query syntax depend on your log platform (Elastic, CloudWatch Logs Insights, Azure Monitor Logs, or Google Cloud Logging). What matters is maintaining a consistent schema and storing request IDs in dedicated fields.

## 19. Testing and hands-on scenarios

Logging tests should verify both expected content and the absence of sensitive data.

| Scenario | Expected result |
|---|---|
| HTTP request without correlation ID | Filter generates a new ID and returns the header |
| HTTP request with valid correlation ID | Preserves ID per policy and includes it in logs |
| Header contains newline/invalid chars/too long | Discards input value and generates a new ID |
| Request completes | MDC is restored/cleared; next request does not inherit old ID |
| Task moves to executor | Correlation ID is propagated and restored |
| Downstream HTTP call | `X-Correlation-ID` is forwarded; `traceparent` is managed by tracing instrumentation |
| AWS request succeeds | Log extracts request ID from response metadata |
| AWS service exception | Log captures request ID/status/error code when service responded |
| Azure Blob response | Log captures `x-ms-request-id` |
| Azure Blob exception | Log captures `x-ms-request-id` if response carries the header |
| Google API returns RequestInfo | Log captures request ID from ErrorDetails |
| Google API omits RequestInfo | Does not fabricate a provider request ID |
| SDK retries multiple times | Does not confuse the final request ID with all attempts |
| Log includes exception | Stack trace is bounded per configuration |
| Request carries secret/PII | Neither secrets nor sensitive bodies are logged |

### 19.1. Unit testing correlation ID rules

Validation logic can be extracted into a small helper:

~~~java
import java.util.UUID;
import java.util.regex.Pattern;

public final class CorrelationIds {
    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    private CorrelationIds() {
    }

    public static String normalize(String candidate) {
        if (candidate != null && SAFE.matcher(candidate).matches()) {
            return candidate;
        }
        return UUID.randomUUID().toString();
    }
}
~~~

Unit test:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CorrelationIdsTest {
    @Test
    void preservesSafeValue() {
        assertEquals("req-42_a", CorrelationIds.normalize("req-42_a"));
    }

    @Test
    void replacesNewlineAndLongValues() {
        String newline = CorrelationIds.normalize("req-42\nforged");
        String longValue = CorrelationIds.normalize("x".repeat(100));

        assertNotEquals("req-42\nforged", newline);
        assertNotEquals("x".repeat(100), longValue);
        assertTrue(newline.length() <= 36);
        assertTrue(longValue.length() <= 36);
    }
}
~~~

### 19.2. Validating JSON logs

In integration tests, enable structured formatting and capture output. Parse each line with a JSON parser, then assert:

- `service.name`, `log.level`, and `message` exist.
- `correlation_id` matches the response header.
- `trace_id`/`span_id` appear when tracing context is active.
- `provider_request_id` appears only when the adapter received an ID from the response/error.
- No fields such as `authorization`, `access_token`, `sas`, or unapproved raw payloads are present.

Do not merely assert that a JSON string contains a substring; parsing JSON catches renamed fields, broken escaping, or fields accidentally embedded inside `message`.

### 19.3. Hands-on scenarios

**Scenario A — AWS S3:** A `HeadObject` call returns 403. Log correlation ID, trace ID, AWS request ID, HTTP status, and AWS error code; explain why no request ID may exist if the failure happened before reaching S3.

**Scenario B — Azure Blob:** An upload retries twice before succeeding. Distinguish `x-ms-request-id` from each response versus `x-ms-client-request-id` sent by the app, and identify which layer must be instrumented to capture all attempts.

**Scenario C — Google Cloud:** An API returns `google.rpc.RequestInfo`. Extract the request ID from `ErrorDetails`; then test an API without this detail and verify logs do not record a fake trace ID as `provider_request_id`.

**Scenario D — Asynchronous worker:** The API creates a job with correlation ID `job-42`, and a worker runs on an executor. Ensure MDC is propagated, logs share the same correlation ID, and each cloud call records its own provider request ID.

**Scenario E — Log injection:** A caller sends `X-Correlation-ID` containing a newline and a forged `ERROR` line. Verify the filter replaces it with a UUID and the JSON encoder still emits exactly one log event.

**Scenario F — Secret leakage:** An SDK exception message contains a URL with a SAS query string. Design logging to emit only provider, operation, status, request ID, and error type; never log the URL or verbatim exception message unredacted.

### Self-check questions

1. **What problem does structured logging solve?** Creates stable fields for filtering and querying in log systems rather than parsing free-form text sentences.
2. **Who manages the correlation ID?** The application or a trusted gateway; it links a business flow across multiple services.
3. **Who generates the provider request ID?** The cloud service returns it for a specific request.
4. **Does a trace ID replace a correlation ID?** No; traces can be sampled or split, whereas a correlation ID can span an entire job.
5. **Where does AWS SDK v2 expose a successful request ID?** From `response.responseMetadata().requestId()`.
6. **Where does an AWS service exception expose a request ID?** From `AwsServiceException.requestId()`.
7. **Which header holds Azure Blob's service request ID?** `x-ms-request-id`.
8. **How does an Azure client request ID differ from a service request ID?** The client request ID is sent by the application; the service request ID is returned by Azure.
9. **Does Google Cloud have one shared request ID accessor across all SDKs?** No; it depends on the API, error details, and transport.
10. **Should provider request IDs be put in metric labels?** No; near-unique values cause cardinality to explode.
11. **Does MDC propagate automatically across thread pools?** No; it requires context propagation or an appropriate `TaskDecorator`.
12. **Is it okay to log access tokens/SAS URLs for debugging?** No; investigate using request IDs, correlation IDs, error codes, and traces.

## 20. Summary

Useful logging in Spring Cloud systems requires **a stable schema, cross-service correlation IDs, and authentic provider request IDs**. Spring Boot 3.5 supports structured JSON logging (ECS, GELF, Logstash), automatically outputting MDC entries and SLF4J key/value fields. Micrometer Tracing adds trace ID/span ID; the application adds correlation IDs to link business flows across HTTP, messages, and workers.

AWS SDK for Java 2.x exposes request IDs in response metadata and service exceptions. Azure Storage returns service request IDs via `x-ms-request-id`, separate from client request IDs. Google Cloud has no single request ID accessor across all clients; record request IDs only when the API genuinely returns `google.rpc.RequestInfo` or an equivalent mechanism.

Keep provider request IDs in structured logs rather than metric labels; propagate MDC safely across threads; redact secrets/PII; and cap stack traces and HTTP debug logging. During incidents, use correlation ID to locate the flow, trace ID to inspect the journey, and provider request ID when collaborating with cloud support.

### Official references

- [Spring Boot 3.5 — Logging and Structured Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html)
- [Spring Boot 3.5 — Tracing and Log Correlation](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html)
- [SLF4J — Fluent Logging API](https://www.slf4j.org/manual.html#fluent)
- [AWS SDK for Java 2.x — Logging with the SDK](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/logging-slf4j.html)
- [AWS SDK for Java 2.x — AwsResponseMetadata](https://docs.aws.amazon.com/java/api/latest/software/amazon/awssdk/awscore/AwsResponseMetadata.html)
- [AWS SDK for Java 2.x — AwsServiceException](https://docs.aws.amazon.com/java/api/latest/software/amazon/awssdk/awscore/exception/AwsServiceException.html)
- [Microsoft Learn — Azure SDK for Java exceptions](https://learn.microsoft.com/java/api/com.azure.core.exception?view=azure-java-stable)
- [Azure SDK for Java — HttpResponse](https://azuresdkdocs.z19.web.core.windows.net/java/azure-core/1.56.1/com/azure/core/http/HttpResponse.html)
- [Azure SDK for Java — HttpHeaders](https://azuresdkdocs.z19.web.core.windows.net/java/azure-core/1.56.1/com/azure/core/http/HttpHeaders.html)
- [Google Cloud — RequestInfo](https://docs.cloud.google.com/java/docs/reference/proto-google-common-protos/latest/com.google.rpc.RequestInfo)
- [Google Cloud — GAX ApiException and ErrorDetails](https://docs.cloud.google.com/java/docs/reference/gax/latest/com.google.api.gax.rpc.ErrorDetails)
- [Google Cloud — Data Manager API error details and RequestInfo (Java)](https://developers.google.com/data-manager/api/devguides/concepts/understand-errors)
