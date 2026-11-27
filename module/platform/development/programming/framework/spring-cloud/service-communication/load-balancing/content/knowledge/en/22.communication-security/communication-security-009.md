# Redacting Tokens, Cookies, and Sensitive Data in Logs

In microservice systems using **Spring Cloud LoadBalancer**, logs help pinpoint failures when `RestClient`, `WebClient`, or OpenFeign selects a `ServiceInstance`, executes HTTP calls, retries, or times out. Yet those same logs can become a **leakage channel for credentials and personal data** if the application prints raw `Authorization`, `Cookie`, URLs containing tokens, response bodies, or exceptions carrying sensitive details.

For example, to diagnose a failing call to `catalog-service`, you usually only need **service ID, logical operation, HTTP method, status, duration, error category, and a valid trace ID**. You **do not need** the JWT, session cookie, password, or payment payload sent in the request.

This lesson in the **Communication Security** chapter guides designing logs around **logging only approved fields (an allowlist)**, handling multi-layer client DEBUG/wiretap settings, verifying logs contain no secrets, and responding when sensitive data has already been logged.

> Foundational rule: **never put secrets into log events in the first place**. Masking strings after a secret has already reached a file, log collector, or trace is too late to consider the data protected.

## 1. Why Is This a Security Risk, Not Just Verbose Logging?

A typical request can carry several kinds of data that need protection:

~~~http
GET /orders/42?access_token=LAB_ONLY_TOKEN HTTP/1.1
Host: order-service
Authorization: Bearer LAB_ONLY_JWT
Cookie: SESSION=LAB_ONLY_SESSION
X-Request-Id: lab-request-001
~~~

In the example, all values are **illustrative dummy data**. On real traffic, if tokens/cookies land in logs:

- Anyone or any system with log read access can replay unexpired credentials to impersonate a user or service.
- Logs are routinely replicated to central aggregators, search indexes, tracing backends, dashboards, customer support tools, and backups.
- Data can persist far longer than needed for debugging.
- A URL carrying a token in its query string can spread into access logs, APMs, analytics, proxies, and exception messages.
- An uncontrolled log record can violate internal policies, contractual obligations, or applicable data-protection regulations.

**HTTPS only encrypts data in transit.** It does not stop applications, HTTP clients, reverse proxies, or observability agents from logging those exact headers/bodies once decrypted.

### Three Data Categories to Distinguish

| Category | Examples | Default Action |
|---|---|---|
| **Granting secrets** | Bearer tokens, API keys, refresh tokens, session cookies, passwords, signing secrets, private keys | **Never log values** |
| **Sensitive personal/business data** | Emails, phone numbers, addresses, customer identifiers, payment info, health records, order contents | Never log raw; emit only policy-approved aggregates/fields |
| **Operational metadata requiring bounds** | Service ID, route template, duration, status, error category, trace ID, instance ID | May log via allowlist; check for embedded identifiers or user-supplied data |

Even `instanceId`, hostnames, or internal IPs can expose infrastructure topology. Never assume every piece of `ServiceInstance` metadata is safe for broad logging.

## 2. Places Where Data Can Be Accidentally Logged

It is not only a `logger.debug(...)` call in business code that causes leaks:

| Log Source | Data That Can Appear | Common Risk |
|---|---|---|
| Inbound controller/filter | URL, headers, form data, JSON request | Logging `Authorization`, `Cookie`, passwords |
| `RestClient` / `RestTemplate` interceptor | URI, request headers/body, response | Dumping `request.getHeaders()` or bodies |
| `WebClient` exchange filter | `ClientRequest`, `ClientResponse`, URI | `toString()`, header dumps, body buffering for debug |
| OpenFeign logger | Method, URL, status, headers, body per log level | `HEADERS` or `FULL` exposes tokens/cookies |
| Apache HttpClient wire/header log | HTTP headers or transmitted payloads per config | Transport-level debug prints real requests |
| Reactor Netty `wiretap` | Network events, hex/text payloads | `HEX_DUMP` or `TEXTUAL` can record sensitive data |
| Gateway/proxy/service mesh | Request target, headers, error pages | Access logs recording query strings or auth headers |
| Exception handler | `exception.getMessage()`, request/response bodies | URLs with secrets, error payloads holding user data |
| Tracing/Micrometer/MDC | Span attributes, baggage, metric labels | Putting tokens, user IDs, or raw URLs into telemetry |
| Logging/observability agents | Captured requests/responses, stack traces, custom attributes | Data shipped to third-party backends |
| Actuator/admin endpoints | Env, configprops, HTTP exchanges, dumps | Exposure misaligned with access policy |

A system can keep application logs clean and still leak tokens in **proxy access logs**. You must audit **the entire observability pipeline**, from caller to backend and log sinks.

## 3. Core Principle: An Allowlist Beats Redacting Raw Records

Two approaches are commonly suggested:

**Risky approach:** log raw headers, URLs, and bodies, then run a regex replacing `Authorization` or `password` with `***`.

**Preferred approach:** construct log events solely from pre-approved fields from the start, never reading secret data unnecessarily.

Example:

~~~text
AVOID:
  outbound request=<full URL with query>
  headers=<all request headers>
  body=<full JSON payload>

PREFER:
  event=downstream_http
  service=catalog-service
  operation=catalog.getProduct
  method=GET
  route=/products/{id}
  status=200
  headerLatencyMs=43
  errorCategory=NONE
  traceId=<validated trace identifier>
~~~

`operation` and `route` in the example are **code-defined literals**, not taken from `request.getURI().toString()`. Even if the real URI contains `?token=...`, it never enters the log event.

### Field Classification Table

| Field to Log | Allowed by Default? | Notes |
|---|---|---|
| App-defined fixed service ID | Yes | Do not place arbitrary registry metadata into tags |
| HTTP method | Yes | Enum-style values like GET/POST only |
| Route template `/products/{id}` | Yes, if approved | Never replace with expanded path containing IDs |
| HTTP status | Yes | Never auto-log response bodies alongside status |
| Duration / timeout category | Yes | Use aggregated values; avoid per-user high cardinality |
| `Content-Type` | Policy-dependent | Allowlist media types only; avoid arbitrary long headers |
| Raw URL / query string | **No** | May contain tokens, emails, signed URLs |
| `Authorization` / `Proxy-Authorization` | **No** | Direct credentials |
| `Cookie` / `Set-Cookie` | **No** | Sessions, CSRF, tracking identifiers |
| `X-API-Key` and custom auth headers | **No** | Header names vary per project |
| Request/response body | **No** by default | JSON, multipart, files, upstream stack traces |
| `exception.getMessage()` | Not by default | May contain URLs, headers, or bodies |
| Exception class/category | Yes after review | Do not print stack traces with messages unchecked |
| Generated/validated Trace ID | Yes per policy | Never treat arbitrary client-sent headers as safe |
| Instance ID/host/IP | Restricted | Can reveal topology; requires matching roles and retention |

Regex redaction can still serve as a **secondary defense layer**, such as in a logging pipeline, yet never replaces an allowlist at log-creation time. Regexes routinely miss custom header names, URL-encoded values, nested JSON, multipart payloads, and binary/hex formats.

## 4. Authorization, Cookies, and Easily Overlooked Data

### 4.1. Sensitive Headers

At a minimum, avoid logging values of:

- `Authorization`: Bearer, Basic, or other schemes.
- `Proxy-Authorization`.
- `Cookie` and `Set-Cookie`.
- `X-API-Key`, `Api-Key`, `X-Auth-Token`, and organization-specific header names.
- Headers carrying client assertions, signed requests, session IDs, or anti-forgery tokens.
- Any header carrying personal information or secrets under the API contract.

**Never block only names containing the word "token".** Many systems use custom header names like `X-Credential` or transmit signing keys under other names.

### 4.2. Data Inside URLs

Places commonly missed:

~~~text
GET /reset-password?code=LAB_ONLY_RESET_CODE
GET /callback?state=LAB_ONLY_STATE
GET /files?signature=LAB_ONLY_SIGNED_QUERY
GET /orders/customer@example.test
GET /download/ONE_TIME_TOKEN/path
~~~

- Query strings can carry verification codes, signed URLs, or access keys.
- Paths can contain emails, customer IDs, password-reset tokens, or user identifiers.
- URIs can be injected automatically into exceptions, tracing spans, or HTTP access logs.
- URL fragments are normally not sent to the HTTP server, yet can still appear in client/browser logs if the app logs the raw original URL string.

Even on `GET`, **never log raw URLs**. Substitute a safe `route template` or operation name.

### 4.3. Bodies and Multipart Payloads

Request bodies can contain:

- `password`, `refreshToken`, `clientSecret`.
- User profiles, street addresses, phone numbers, emails.
- Payment details or account numbers.
- Uploaded files, document images, chat transcripts.
- Sensitive data submitted in multipart form fields.

Never judge safety by HTTP method—assuming `GET` is safe while `POST` is risky: `GET` query strings and `POST` bodies can both leak sensitive data.

## 5. What Does Spring Cloud LoadBalancer Need Logged for Debugging?

Spring Cloud LoadBalancer picks a `ServiceInstance` from a service ID using discovery, caches, health checks, and selection/filtering policies. When troubleshooting failures, the usual questions are:

1. Which **service ID** did the caller invoke?
2. How many candidate instances were returned?
3. Was an instance selected?
4. Did the connection succeed and receive an HTTP status?
5. Were there retries, and which attempt number?
6. Did waiting happen in discovery, pooling, connect, response, or business logic?
7. Was the error `NO_INSTANCE`, `NETWORK`, `HTTP_STATUS`, `DECODE`, or `CONTRACT`?

You do not need to log tokens or cookies to answer any of these questions.

~~~mermaid
flowchart TD
    A["App calls catalog-service"]
    B["LoadBalancer selects ServiceInstance"]
    C["HTTP transport executes request"]
    D["Response or exception"]
    E["Controlled log event"]
    X["Token / Cookie / Body / Raw URL"]
    A --> B --> C --> D --> E
    B -->|"service ID, selection outcome"| E
    C -->|"method, duration, category"| E
    X -.->|"Excluded from logs"| E
~~~

In multi-zone environments, you may add **approved zone labels**, fallback status, or selection algorithm details. However, registry-provided `metadata` can hold arbitrary values: pick fields by allowlist rather than printing `ServiceInstance.getMetadata()` wholesale.

### Watch Out for High Cardinality

If metric tags or log indexes include `userId`, raw URLs, tokens, or unbounded instance IDs, observability storage balloons rapidly and private data becomes a searchable key. Metrics should use stable labels such as `serviceId`, `operation`, `statusGroup`, and `errorCategory`.

## 6. RestClient: An Interceptor Logging Only Approved Metadata

A LoadBalancer-integrated `RestClient` can be declared with `@LoadBalanced RestClient.Builder`. The following example **neither reads nor logs** headers, real URIs, request bodies, response bodies, or exception messages.

~~~java
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class SafeCatalogClientConfiguration {

    private static final Logger LOG =
            LoggerFactory.getLogger(SafeCatalogClientConfiguration.class);

    @Bean("safeCatalogBuilder")
    @LoadBalanced
    RestClient.Builder safeCatalogBuilder() {
        return RestClient.builder().requestInterceptor(
                (request, body, execution) -> {
                    long start = System.nanoTime();

                    try {
                        ClientHttpResponse response =
                                execution.execute(request, body);

                        LOG.info(
                                "event=downstream_http service={} "
                                + "operation={} method={} status={} "
                                + "headersElapsedMs={}",
                                "catalog-service",
                                "catalog.api",
                                request.getMethod().name(),
                                response.getStatusCode().value(),
                                elapsedMillis(start));
                        return response;
                    } catch (IOException | RuntimeException ex) {
                        LOG.warn(
                                "event=downstream_http_failed "
                                + "service={} operation={} "
                                + "errorType={} headersElapsedMs={}",
                                "catalog-service",
                                "catalog.api",
                                ex.getClass().getSimpleName(),
                                elapsedMillis(start));
                        throw ex;
                    }
                });
    }

    @Bean("safeCatalogClient")
    RestClient safeCatalogClient(
            @Qualifier("safeCatalogBuilder") RestClient.Builder builder) {
        return builder.baseUrl("http://catalog-service").build();
    }

    private static long elapsedMillis(long start) {
        return TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - start);
    }
}
~~~

In the example above, `catalog.api` is a **fixed label** for the client; if per-operation granularity is needed, assign operation names at the service adapter using approved constants or safe observation conventions. Never try inferring the operation by logging raw `request.getURI()`.

**Measurement caveat:** this interceptor measures time until `execution.execute(...)` returns the response and may **not yet include reading the entire response body**. Never label this metric as "total business duration". With retries, each attempt can emit its own event depending on where the interceptor sits in the chain.

**Do not log `ex.getMessage()` or pass raw `ex` to the logger in data-protection examples**, since messages/stack traces can hold URLs/headers/bodies or downstream-supplied text. When deep debugging is needed, define standardized error codes and controlled incident capture rather than dumping raw exceptions in production logs.

### 6.1. Mistakes to Avoid

~~~java
// AVOID: the values below can contain secrets.
log.debug("uri={}", request.getURI());
log.debug("headers={}", request.getHeaders());
log.debug("body={}", new String(body, StandardCharsets.UTF_8));
log.error("HTTP call failed", exception);
~~~

These are **anti-patterns**, not code to put into real applications. In particular, `new String(body)` also assumes the body is text; on binary uploads it can log huge payloads, corrupt encodings, and cause memory pressure.

If you want to measure request size, consider `body.length` only when interception already holds a byte array, understanding that some interceptors/request factories affect buffering and streaming. Never enable body buffering solely to log upload size.

### 6.2. Spring Boot Observability

Manually calling `RestClient.builder()` focuses on illustrating the logging principle. In a Spring Boot app, when you want to retain framework auto-customizers (observation/tracing, JSON converters, authentication interceptors), use `RestClientBuilderConfigurer` or a Boot-managed builder. Never sacrifice controlled observability just to add an interceptor that logs raw requests.

## 7. WebClient: Exchange Filter Without Reading Headers or Body

With `WebClient`, you can attach an `ExchangeFilterFunction` to log status and timing **without touching sensitive data**:

~~~java
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class SafeCatalogWebClientConfiguration {

    private static final Logger LOG =
            LoggerFactory.getLogger(
                    SafeCatalogWebClientConfiguration.class);

    @Bean
    @LoadBalanced
    WebClient.Builder safeCatalogWebClientBuilder() {
        ExchangeFilterFunction safeLogging = (request, next) -> {
            long started = System.nanoTime();

            return next.exchange(request)
                    .doOnNext(response -> LOG.info(
                            "event=downstream_http service={} "
                            + "operation={} status={} headersElapsedMs={}",
                            "catalog-service",
                            "catalog.api",
                            response.statusCode().value(),
                            millis(started)))
                    .doOnError(error -> LOG.warn(
                            "event=downstream_http_failed "
                            + "service={} operation={} errorType={} "
                            + "headersElapsedMs={}",
                            "catalog-service",
                            "catalog.api",
                            error.getClass().getSimpleName(),
                            millis(started)));
        };

        return WebClient.builder().filter(safeLogging);
    }

    private static long millis(long start) {
        return TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - start);
    }
}
~~~

This snippet never calls `ClientRequest.url()`, never prints `ClientRequest.headers()`, and never uses `ClientResponse.bodyToMono(String.class)` for logging. Nor does it add a second subscription to the response body—a frequent bug when writing reactive debug filters.

**Note:** elapsed time is measured until response headers arrive and may not include full body consumption; with retries/resubscriptions, event counts depend on the filter's position in the reactive chain. A logging filter cannot by itself guarantee lower layers have not enabled wiretap.

### With Streaming, Never Buffer the Body Just to Debug

A `Flux<DataBuffer>` or response stream can carry files, video, SSE, or large datasets. Trying to `collectList()` the whole stream for logging:

- Can hold huge amounts of data in RAM.
- Risks breaking backpressure, failing to release buffers properly, or slowing down consumers.
- Can inject sensitive data into logs/traces.
- For infinite streams, collecting the entire stream never finishes.

For streaming, prefer total byte count, duration, chunk count, completion/cancellation status, and normalized error codes—never log payloads.

## 8. OpenFeign: NONE, BASIC, HEADERS, and FULL Levels

Per Spring Cloud OpenFeign documentation, `Logger.Level` has four levels:

| Feign Level | What Can Be Logged? | Risk Assessment |
|---|---|---|
| `NONE` | No request/response logging from Feign logger | Safest choice when wire-level Feign logs are unneeded |
| `BASIC` | Method, **URL**, status, elapsed | URLs with query/path tokens or personal data can still leak |
| `HEADERS` | BASIC + request/response headers | Can expose `Authorization`, `Cookie`, `Set-Cookie` |
| `FULL` | Headers and bodies of request/response | Highest risk: exposes both secrets and business data |

Feign logging also normally emits output only when the Feign client's logger is at **DEBUG** level. Thus enabling DEBUG for the Feign package/interface and raising `loggerLevel` can dramatically increase what gets logged.

### 8.1. Restrictive Logging Configuration

Example for `@FeignClient(name = "catalog-service")`:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          catalog-service:
            loggerLevel: NONE

logging:
  level:
    com.example.orders.client.CatalogFeignClient: INFO
~~~

`NONE` configures the Feign logger not to log requests/responses; `INFO` also prevents enabling DEBUG logging for that client. **Neither disables** other loggers configured by application interceptors, HTTP transports, gateways, or APMs.

### 8.2. Why Is BASIC Not Automatically Safe?

A URL such as:

~~~text
GET /files/download?signature=LAB_ONLY_SIGNED_URL
~~~

can be logged at `BASIC` level because the URL is part of the basic record. Therefore, if the app ever transmits credentials in query strings or paths, **never treat BASIC as a redacted level**.

If an organization genuinely must run deep Feign debugging, do so in an environment with synthetic data, using a custom logger whose masking policy has been tested and with strict time/scope limits. Never enable `FULL` against real tokens just because you hit a timeout bug.

### 8.3. Feign Is Not the Only Layer

With Spring Cloud LoadBalancer, `FeignBlockingLoadBalancerClient` helps select instances. The underlying HTTP delegate beneath Feign (Apache HttpClient 5 or another transport) has its own logging. Setting `loggerLevel: NONE` for Feign does not guarantee the HTTP delegate has disabled wire/header logging.

## 9. Apache HttpClient and Reactor Netty Wiretap

HTTP transports can log data below Spring's client APIs.

### Apache HttpClient 5

When DEBUG/TRACE or wire logs are enabled on the corresponding categories, request/response headers or HTTP payloads can appear. Exact logger names vary by version and transport; inspect the logging config of your actual dependencies.

An illustrative defensive config:

~~~yaml
logging:
  level:
    org.apache.hc.client5.http.wire: OFF
    org.apache.hc.client5.http.headers: OFF
    org.apache.hc.core5.http.wire: OFF
~~~

This is **not a universal guarantee** that every Apache logger or third-party library logger has stopped logging payloads. Verify which loggers are actually active through integration tests and by inspecting both client and proxy logs.

### Reactor Netty

Reactor Netty includes a `wiretap` feature, disabled by default. Its formatters have distinct traits:

- `SIMPLE`: primarily logs events and byte sizes, without intentionally printing payload contents.
- `HEX_DUMP`: can print HTTP contents in hexadecimal; **hex is still decodable data**, not anonymization.
- `TEXTUAL`: can print text contents, including headers/bodies where applicable.

In production, **prefer disabling wiretap and using safe WebClient filters/observations**. Even `SIMPLE` can reveal connection addresses or infrastructure metadata; enable it only if organizational policy allows.

~~~text
PREFER in production:
  Reactor Netty wiretap: disabled
  HTTP event logging: allowlisted fields

ONLY in labs with synthetic data:
  Wiretap or transport-level logger to analyze protocol behavior
  Never use real Bearer tokens, cookies, or PII
~~~

If you enable HTTP debugging in a staging environment populated with production-cloned data, that environment still carries real-data exposure risk.

## 10. Never Let Sensitive Data Leak Through Exceptions and Error Handlers

A common failure chain:

~~~text
RestClient/WebClient/Feign request fails
  -> HTTP/transport exception
  -> exception message may contain URL, response, or upstream details
  -> global exception handler calls logger.error("...", exception)
  -> centralized logs receive unintended sensitive data
~~~

Operations to scrutinize closely:

- `error.getMessage()` / `error.toString()`.
- `logger.error("failed", exception)`: stack trace including message/cause.
- `RestClientResponseException.getResponseBodyAsString()`.
- `WebClientResponseException.getResponseBodyAsString()`.
- `FeignException.contentUTF8()` or reading raw response bodies.
- `request.getURI().toString()` / `response.getHeaders().toString()`.

Not every exception is guaranteed to contain secrets; the problem is **there is no guarantee it does not**. Therefore, application logging should classify exceptions into stable categories:

| Safe Error Group to Log | Classification Basis |
|---|---|
| `NO_INSTANCE` | LoadBalancer could not pick a candidate |
| `CONNECT_FAILURE` | Connection establishment error matching checked exception types |
| `TIMEOUT` | Recognized connect/read/pool timeout |
| `HTTP_4XX` / `HTTP_5XX` | HTTP status family |
| `DECODE_FAILURE` | JSON/codec decoding mismatch |
| `CIRCUIT_OPEN` | Circuit breaker blocked execution |
| `UNKNOWN` | Unclassified without printing raw message |

An unclassified error should log `UNKNOWN` with a safe trace/correlation ID so operators can investigate via access-controlled telemetry. Never use `error.getMessage()` as a metric tag or end-user error message.

### Downstream Errors Returned to Clients

Never reflect downstream exception contents in HTTP responses sent to end users. Use an error contract with stable codes (such as `DOWNSTREAM_UNAVAILABLE`) and a correlation ID; internal details belong strictly in properly access-controlled diagnostic tools.

## 11. MDC, Trace IDs, and Baggage Must Also Be Checked

Distributed tracing links calls across `order-service`, `catalog-service`, and replicas chosen by LoadBalancer. Yet leaks happen if sensitive data enters these fields:

- MDC: `MDC.put("authorization", token)` is wrong.
- Baggage: never propagate emails, tokens, or account numbers across every span.
- Span attributes: never attach raw URLs, query strings, or response bodies.
- Metric tags: never use user IDs, access tokens, emails, or exception messages as labels.
- Trace ID/correlation ID: if read from user-supplied headers, validate syntax and cap length.

### Safe Correlation IDs

If an application accepts `X-Request-Id` from external requests:

1. Accept only a validated format, such as ASCII letters/digits, hyphens/underscores, and max 64 characters.
2. If invalid, generate a fresh ID at the trust boundary.
3. Never log the original header value when validation fails.
4. Never use a correlation ID as a security key or authentication proof.

Illustrative logic:

~~~java
import java.util.UUID;
import java.util.regex.Pattern;

final class CorrelationIds {

    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    static String acceptedOrGenerated(String inbound) {
        if (inbound != null &&
                SAFE.matcher(inbound).matches()) {
            return inbound;
        }
        return UUID.randomUUID().toString();
    }
}
~~~

This illustrates syntax checking to prevent oversized values or newlines in logs. **It does not prove a client-supplied ID is trustworthy**; systems needing strict tracing boundaries may always mint a fresh ID or use validated trace contexts.

If the logging backend combines MDC with a JSON encoder, restrict which MDC keys/values are allowed to be emitted. Using `%X` or dumping the full MDC map can accidentally emit keys injected by other libraries.

## 12. Actuator and Protecting Observability Configuration Data

Spring Boot Actuator exposes endpoints such as `/actuator/env` and `/actuator/configprops` with built-in sanitization of sensitive config values. However:

- Actuator sanitization **does not scrub application logs** already emitted by `logger.info(...)` or Feign/wiretap.
- Management endpoints still require authentication, authorization, and restricted exposure.
- Never turn on full value display just for debugging when configurations hold secrets.
- If `httpexchanges` is enabled with a backing repository, audit which HTTP details it stores and who can access it; do not assume it is a safe place for private data.

Example conservative policy for config values:

~~~yaml
management:
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
  endpoints:
    web:
      exposure:
        include: health,info
~~~

This configuration only illustrates restricting Actuator exposure. It does not automatically protect ingress logs, access logs, proxy logs, application logs, or transport logs. Verify management security per your Spring Boot version and organizational policy.

## 13. Pipeline-Layer Masking: Only a Secondary Defense

When a system must handle legacy logs or third-party library output that cannot be changed immediately, log collectors can apply redaction rules before indexing/storage. Understand the limits:

| Method | Benefit | Weakness |
|---|---|---|
| Never log raw; allowlist fixed fields | Prevents secrets from appearing at all | Requires explicit log event design |
| Mask a set of sensitive headers | Lowers risk on some structured logs | Can miss custom headers |
| Regex replacing `Bearer ...` | Catches some literal patterns | Misses tokens in URLs, JSON, alternate encodings, line wraps |
| DLP scanner at ingest | Catches additional secret/PII patterns | False positives/negatives; data already reached the scanner |
| Restricting access and retention | Shrinks exposure window/audience | Does not render already-leaked secrets harmless |
| Encrypting log storage | Reduces unauthorized storage access risk | Authorized log readers can still view raw secrets |

**Avoid logging first and redacting later inside the same process whenever possible**: another appender, APM agent, async queue, or debug console may receive the raw record before the filter runs.

### When Fingerprinting a Token Is Needed

Occasionally operators need to know whether two requests used the same credential. **Never log `SHA-256(token)` by default**: deterministic hashes still act as linkable cross-request identifiers and carry privacy or brute-force risks if secret entropy is low.

Prefer an **independent operation ID or correlation ID**. If credential fingerprinting is truly required, use an approved design (such as a keyed HMAC with securely managed keys and explicit scope/retention) and never turn that value into a public metric tag.

## 14. Practice: Verifying No Tokens Leak Through LoadBalancer Calls

Run two `catalog-service` instances in a local/test environment, each returning a value from `/whoami` to observe LoadBalancer. Never use real credentials.

### 14.1. Prepare Mock Inputs

Example input:

~~~http
GET http://catalog-service/orders/42?access_token=LAB_CANARY_QUERY_001
Authorization: Bearer LAB_CANARY_BEARER_001
Cookie: SESSION=LAB_CANARY_COOKIE_001
X-API-Key: LAB_CANARY_APIKEY_001
X-Request-Id: safe-lab-123
~~~

These are **synthetic canary strings**. Use a test JSON response:

~~~json
{
  "customerEmail": "canary@example.test",
  "password": "LAB_CANARY_PASSWORD_001",
  "result": "ok"
}
~~~

Never place canary values into "safe" logs; they exist solely as markers for **tests to search for and fail if any logging layer leaks them**.

### 14.2. Test Scenario

1. Configure `@LoadBalanced RestClient.Builder` with the safe interceptor from section 6.
2. Call a test endpoint accepting the mock headers and query while the backend returns the canary-filled body.
3. Confirm the request genuinely executed (server returned a status, or handler test assertions passed) without printing the input.
4. Collect application logs, HTTP client logs, lab gateway/proxy logs, and records from any observability tools running in the test environment.
5. Search all captured outputs for the canary strings.
6. Test Feign at `NONE` first, then—if investigating `FULL` risk—use synthetic data only in an isolated environment; confirm why `FULL` violates policy whenever secrets are present.
7. With WebClient, test with wiretap disabled, then (strictly in the lab) enable wiretap to see what kind of data gets recorded.
8. Also test HTTP 401/403/503 errors, timeouts, and network exceptions; failure paths must contain zero secrets as well.

### 14.3. Assertions for Captured Logs

Test pseudocode, depending on your logging/integration-test framework:

~~~java
String allCapturedLogs = captureLogsFromTheTestRun();

assertFalse(allCapturedLogs.contains("LAB_CANARY_BEARER_001"));
assertFalse(allCapturedLogs.contains("LAB_CANARY_COOKIE_001"));
assertFalse(allCapturedLogs.contains("LAB_CANARY_QUERY_001"));
assertFalse(allCapturedLogs.contains("LAB_CANARY_APIKEY_001"));
assertFalse(allCapturedLogs.contains("LAB_CANARY_PASSWORD_001"));
assertFalse(allCapturedLogs.contains("canary@example.test"));

assertTrue(allCapturedLogs.contains("service=catalog-service"));
assertTrue(allCapturedLogs.contains("status=200"));
~~~

`captureLogsFromTheTestRun()` is a **test harness placeholder**, not a built-in Spring API. With Logback, you can attach an in-memory appender in tests; with JSON logs or async appenders, inspect the final emitted output. If no canary appears simply because the request never ran or logs were not captured, that is a **false pass**.

Ensure tests include a **positive control**: a non-sensitive log event confirming the pipeline captured logs and the HTTP request reached the backend.

### 14.4. Verification Matrix

| Scenario | What Must Never Appear in Logs | What Should Still Be Observable |
|---|---|---|
| Successful HTTP 200 request | Tokens, cookies, raw bodies | Service, operation, status, latency |
| HTTP 401/403 | Auth headers, sensitive error bodies | Status, auth error category |
| HTTP 503/timeout | Full URI, raw exception message with URL | Error category, attempt, timing |
| Retry to another instance | Credentials in headers on each attempt | Attempt number, service ID, outcome |
| OpenFeign `BASIC`/`HEADERS`/`FULL` in lab | Report which levels risk leaks | Justification for enforcing `NONE` in production |
| Reactor Netty wiretap | Real payloads never reach production output | Non-sensitive events/metrics |
| URI with canary in query/path | Raw URL or code embedded in path | Route template and HTTP method |
| Response JSON containing PII | Raw JSON, email/password | Status, approved content type |
| Tracing/MDC with client input | Unvalidated headers, tokens/baggage | Safe Trace ID |
| Actuator/admin endpoints | Secret config values when unauthorized | Restricted health/info exposure |

## 15. Responding When Secrets Are Found in Logs

If a real token or session cookie leaks into logs, fixing the code and waiting for old logs to expire is **not enough**. Follow an incident response process per organizational policy:

1. **Stop further leakage:** disable the offending logger/feature, deploy the fix, and audit related environments and libraries.
2. **Assess scope:** identify affected services, time windows, secret types, log sinks, indexes, dashboards, backups, and downstream systems that ingested the records.
3. **Revoke/rotate credentials:** revoke tokens, invalidate sessions, and rotate API keys/secrets commensurate with risk.
4. **Restrict access:** tighten log viewing permissions, enable access auditing, and clean up unnecessary shares or exports.
5. **Handle stored data:** execute deletion/redaction per retention, backup, and legal policies while preserving necessary incident-response evidence.
6. **Verify repeatedly:** add canary regression tests; confirm zero leaks across new logs, traces, metrics, gateways, and APMs.
7. **Learn and harden:** adopt shared allowlists, standardized loggers, and an approval process before enabling DEBUG in production.

Never upload logs suspected of holding real tokens to public tools, unprotected tickets, or broad group chats just to ask for help analyzing them. Use controlled incident channels.

## 16. Checklist for Implementing Safe Logging

- Have you explicitly defined which tokens, cookies, PII, and business fields **must never be logged**?
- Do you use an allowlist of stable fields rather than dumping full headers/URLs/bodies?
- Do you log route templates and operation names instead of sensitive raw URIs/queries/path variables?
- Do `RestClient` interceptors and `WebClient` filters avoid reading/logging bodies, headers, and exception messages?
- Is OpenFeign `Logger.Level` kept at `NONE` or an audited setting, with safeguards preventing `FULL` in production?
- Have Apache HttpClient/Netty wiretap, gateways, proxies, and APMs been audited individually?
- Do logs, MDC, baggage, and metric tags exclude tokens, user IDs, emails, and high-cardinality values?
- Are external correlation IDs syntax-validated and length-bounded or regenerated?
- Are HTTP 4xx/5xx, timeout, retry, decoder, and circuit breaker errors logged using safe categories?
- Are `/actuator/env`, `/actuator/configprops`, `/actuator/httpexchanges`, and management endpoints suitably restricted?
- Are log read permissions, retention windows, storage encryption, log exports, and access audits controlled?
- Have you run canary integration tests through the **real logging pipeline**, covering both happy paths and error paths?
- Is there a leak-response runbook covering token revocation, log-sink verification, and policy regression checks?

**Conclusion:** Safe logging for Spring Cloud LoadBalancer does not mean logging so little that you cannot debug—it means **recording the exact metadata needed at each layer**. Service ID, operation, instance-selection outcome, HTTP status, latency, error category, and controlled trace IDs are usually sufficient for diagnosis. `Authorization`, `Cookie`, signed URLs, request/response bodies, and raw exception messages must stay out of default logs. Prioritize **source-level allowlists**, disable wire-level payload logging in production, test with canaries, and protect the entire observability pipeline.

**Official References:**

- [Spring Cloud OpenFeign – Feign Logging](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html)
- [Spring Framework – REST Clients and Client Interceptors](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Reactor Netty – HTTP Client Wire Logger](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Spring Boot – Actuator Endpoints and Sanitize Sensitive Values](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
