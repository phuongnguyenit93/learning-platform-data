# Redacting Authorization, Cookies, Personal Data, and Sensitive Content in Spring Boot HTTP Observability

## 1. Objectives and Real-World Scenario

HTTP observability helps answer "which service is slow?", "where are requests failing?", "how many 401/500 errors occurred?", and "did this deployment increase error rates?". Yet logs, traces, metrics, access logs, and Actuator can also become **a data-leak channel**. A seemingly harmless line can contain bearer tokens, session cookies, verification codes, emails, phone numbers, shipping addresses, payment data, personal profiles, or paths pointing to private documents.

Example request (synthetic dummy data only):

```http
GET /api/orders/customer-42?access_token=TEST_TOKEN_DO_NOT_USE HTTP/1.1
Host: api.example.test
Authorization: Bearer TEST_ACCESS_TOKEN
Cookie: SESSION=TEST_SESSION_ID; preference=dark
Referer: https://app.example.test/reset?code=TEST_RESET_CODE
X-Request-Id: TEST_USER_CONTROLLED_ID
```

**Wrong** when logging the full request:

```text
GET /api/orders/customer-42?access_token=TEST_TOKEN_DO_NOT_USE
Authorization: Bearer TEST_ACCESS_TOKEN
Cookie: SESSION=TEST_SESSION_ID; preference=dark
```

**Better**, when operations only need the processing path and latency:

```text
http_exchange method=GET route=/api/orders/{id} status=200 durationMs=18
```

The second line suffices to analyze throughput and latency per route without storing values from `Authorization`, `Cookie`, path variables, or query strings. When you need to correlate records belonging to one request, use a trace or correlation ID generated/verified per policy; **never use tokens or session IDs as correlation keys**.

This lesson applies to **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+**, covering Spring MVC, WebFlux, and HTTP clients. The runnable example uses Java 21, Gradle, and Spring Boot 3.3.13. The core focus is **preventing sensitive data from entering observability systems**; regex substitution after events are emitted is strictly a secondary defense, never the primary security design.

## 2. Four Principles: Minimize, Allowlist, Redact Before Writing, and Test

A safe HTTP observability policy starts with four questions:

1. **Do we actually need this data?** If you only need error counts by HTTP status, you never need request bodies, query strings, cookies, or `Authorization`.
2. **Which fields are permitted?** Use an explicit allowlist of log/trace/metric fields rather than relying solely on a denylist of sensitive names that will inevitably miss new fields.
3. **Where should redaction happen?** Strip or redact **before writing to appenders/exporters/collectors**, rather than waiting for dashboard UIs to hide values.
4. **How do we prove it works?** Send requests with clearly recognizable synthetic canaries and verify those canaries never appear in logs, tracing backends, metric labels, access logs, Actuator, or responses.

Handling levels:

| Approach | Description | Example |
| --- | --- | --- |
| **Do not collect** | Never read or emit the field into telemetry | Skip `Authorization`, `Cookie`, bodies |
| **Substitute value** | Keep field name for structural auditing, replace data | `authorization=[REDACTED]` |
| **Categorize** | Map into a bounded enum/category | `auth_scheme=bearer`, `payload_type=json` |
| **Partial mask** | Expose only minimal approved portion per policy | Unsuitable for access tokens/passwords; consider only for approved low-sensitivity data |
| **Pseudonymization** | Controlled substitute identifier | HMAC of business ID when correlation is genuinely required |
| **Restricted-access encryption** | Recoverable by authorized keyholders | Only for specialized audit systems with legal basis and strict controls |

**Important:** "Masking" does not mean leaving the last four characters visible. For bearer tokens, refresh tokens, passwords, session cookies, private keys, and one-time codes, the safest rule is **log none of it**. Partial fragments can still widen attack surfaces or enable unauthorized correlation.

## 3. Classify HTTP Data Before Enabling Logging

| Data source | Example | Risk | Recommended policy |
| --- | --- | --- | --- |
| Auth headers | `Authorization`, `Proxy-Authorization` | API/session takeover | Never log values |
| Cookie headers | `Cookie`, `Set-Cookie` | Session, CSRF, remember-me token leaks | Never log values |
| Custom API keys | `X-API-Key`, `X-Auth-Token` | Unauthorized system access | Never log values |
| Query parameters | `token`, `code`, `password`, `email`, `phone` | Secrets/PII leaked via URL | Never log raw query; prefer routes |
| Path variables | `/users/{email}`, `/orders/{id}` | Can identify people or actions | Log **route pattern**, not path instance |
| Request body | Passwords, personal info, nested JSON | Domain-specific sensitive data | Do not log bodies by default |
| Response body | Profiles, orders, health records | Exposes data protected by API | Do not log bodies by default |
| `Referer` | Previous URL carrying tokens or queries | Cross-screen data leak | Never log raw value |
| `User-Agent` | Contributes to fingerprinting | Tracking/identification, high cardinality | Store only approved category if needed |
| IP and geo | `remoteAddr`, `X-Forwarded-For` | Personal data in many jurisdictions; spoofing | Restrict purpose, trusted sources, and retention |
| Session/principal | Session ID, username, subject ID | Links personal activity | Never log session ID; pseudonymize only if needed |
| HTTP method/status | `GET`, `POST`, `200`, `403` | Usually low risk | Appropriate for telemetry |
| Route template | `/api/orders/{id}` | Reveals less than raw path | Good for logging, metrics |
| Duration / outcome | `durationMs=18`, `outcome=SUCCESS` | Usually low risk | Appropriate for telemetry |

A field does not have to be named "password" to carry a secret. Fields named `payload`, `metadata`, `debug`, `data`, `description`, `comment`, `state`, `assertion`, or URLs in `Location`/`Referer` can carry tokens too. **Sensitive-name lists are a secondary layer, never a guarantee.**

Update your classification whenever adding endpoints, switching identity providers, changing gateways, or adopting GraphQL/SSE/WebSockets.

## 4. Why `Authorization` Must Never Enter Routine Logs

`Authorization` can carry:

```http
Authorization: Bearer eyJ... (dummy token)
Authorization: Basic dGVzdDp0ZXN0 (dummy credentials)
Authorization: Digest ...
```

A bearer token is typically a **directly usable credential**: anyone holding it can call APIs within its scope and lifetime without knowing the user's password. Basic Authentication uses Base64 encoding, not secret encryption. **Never log the full token, Base64 string, JWT payload, signature, or a long prefix.**

Even though a JWT looks like "just three text segments", its payload can carry personal claims and the full token can be replayed. `log.debug("token={}", token)` is a severe flaw even at `DEBUG`, since log levels can be raised during production incidents.

Instead of:

```java
// Do not do this:
log.info("request Authorization={}",
        request.getHeader("Authorization"));
```

If you **truly** need to know the authentication mechanism, log a bounded value determined by trusted application logic:

```text
auth_mechanism=oauth2
auth_result=authenticated
auth_failure_reason=expired
```

Derive `auth_mechanism` from configuration or security outcomes rather than echoing header values. For 401 errors, route template, outcome, error category, and correlation ID usually suffice. Error messages like `"Invalid token: <value>"` can also leak tokens into exceptions and logs.

## 5. `Cookie` and `Set-Cookie` Are Even Easier to Miss

Browsers send `Cookie` and servers return `Set-Cookie`:

```http
Cookie: SESSION=DEMO_SESSION; rememberMe=DEMO_REMEMBER; theme=dark
Set-Cookie: SESSION=NEW_DEMO_SESSION; HttpOnly; Secure; SameSite=Lax
```

`SESSION`, `JSESSIONID`, refresh/session cookies, and CSRF cookies enable session hijacking or tracking. Never log **the entire header** just because one cookie like `theme=dark` looks benign.

Do not rely on splitting cookies on `;` to mask only a few known cookie names: apps introduce new cookies, values get URL-encoded, or formats vary. The safe policy for general observability is **never log `Cookie` or `Set-Cookie` values**.

Do not enable:

```text
Cookie=SESSION=...
Set-Cookie=...
```

just to debug logout or SSO. Emit structured events instead:

```text
session_event=CREATED auth_method=oidc outcome=SUCCESS
session_event=REVOKED reason=LOGOUT outcome=SUCCESS
```

If you need to correlate a session lifecycle for security audits, generate a secondary non-credential identifier. Per OWASP, raw session IDs must not appear in logs. Even "hashing the session ID" requires evaluating linkability, key management, and retention.

## 6. Personal Data Lives in Paths, Queries, and `Referer`, Not Only Bodies

URLs often carry private data:

```text
/api/users/alice@example.test
/api/orders/customer-42
/reset?code=DEMO_ONE_TIME_CODE
/callback?code=DEMO_OAUTH_CODE&state=DEMO_STATE
/search?q=sensitive-medical-query
/download?signature=DEMO_SIGNED_URL
```

Many access logs record the **full request line** (method, path, query) or `Referer`. Skipping headers and bodies alone is **not enough**.

Prefer:

```text
method=GET route=/api/users/{email} status=200
method=GET route=/reset status=302
method=GET route=/download status=200
```

where `route` comes from **server-defined handler mappings**, not the client's raw request path.

Note carefully:

- `request.getRequestURI()` **omits the query string**, yet still retains emails, phone numbers, or account IDs in the **path**.
- `request.getQueryString()` holds arbitrary user-supplied values and is particularly hazardous.
- `request.getRequestURL()` returns the URL with the concrete path, not a route template.
- HTTP client `URI.toString()`, `HttpRequest.getURI()`, and client-library exceptions can contain signed URLs and query tokens.
- `Referer` can carry the previous page's URL along with sensitive parameters.
- Response `Location` headers on redirects can also carry authorization codes, nonces, or identifiers.

For routes unmatched by Spring MVC, log a fixed label like `UNMAPPED` or `OTHER`—**never fall back to the raw URI**. For file servers or wildcard routes, log a logical category (`STATIC_RESOURCE`) rather than raw file paths.

## 7. Request and Response Bodies: The Hardest Source to Mask

Bodies arrive as JSON, form-urlencoded, XML, multipart, protobuf, GraphQL variables, binary files, or SSE streams. Each format carries distinct hazards:

| Body type | Potentially exposed data |
| --- | --- |
| `application/json` | `password`, email, phone, `customerId`, profiles, nested objects |
| `application/x-www-form-urlencoded` | Passwords, OTPs, callback codes, form fields |
| `multipart/form-data` | Personal files, ID documents, photos, metadata |
| GraphQL | Variables, query literals, customer fields, nested errors |
| XML/SOAP | Credentials, identifiers, medical/payment data |
| Binary/protobuf | Unreadable raw payloads still carrying sensitive data |
| Response JSON | User profiles, auth tokens, refresh tokens, order lists |
| SSE/WebSocket | Chat messages, real-time payloads, per-session personal data |

In Spring MVC, wrappers like `ContentCachingRequestWrapper`/`ContentCachingResponseWrapper` can cache body bytes for logging. They serve controlled technical scenarios yet **do not sanitize anything automatically**. Body caching also increases memory footprint and retains sensitive data on the heap; misusing the response wrapper can even drop the response body before the client receives it.

Never turn on global body logging to debug a single failing endpoint. If inspecting real payloads is strictly necessary, use an **isolated diagnostic channel** with explicit authorization, narrow scope, encryption, sampling, short retention, and tested redaction—and always try **synthetic test data** first.

Never naively assume a regex like `"password":"..."` catches every secret: nested JSON, escaped quotes, encodings, key aliases, arrays, compressed bodies, multipart forms, and inconsistently named fields routinely bypass regexes.

## 8. HTTP Observability Architecture: Every Layer Can Leak Data

```text
Client
  |
  +-- Browser devtools / client SDK debug logs
  v
CDN / WAF / Load Balancer / API Gateway
  |       access logs, request mirroring, security event dumps
  v
Embedded Tomcat / Reactor Netty / HTTP wire logging
  |       request line, headers, bytes
  v
Servlet Filter / WebFlux WebFilter / Spring Security
  |       logs, exceptions, auth failure reports
  v
Controller / service / outbound HTTP client
  |       domain events, request/response debugging
  v
Micrometer Observation / Tracing / Actuator
  |       spans, tags, HTTP exchanges, env/configprops
  v
Agent / Collector / message queue / log platform
  |       transport and storage copies, indexes, retention
  v
Dashboards / alerts / exports / support tickets
```

**Redacting inside one Spring filter does not erase copies already recorded by gateways, web server access logs, wiretap agents, or collectors.** Maintain a full inventory of every logging point and who has permission to raise levels to `DEBUG`/`TRACE`.

Enforce policies **at the telemetry source**. Collector-side redaction is defense-in-depth, not an excuse to let secrets reach unauthorized sinks or network hops.

## 9. Choosing Metadata That Is Useful Without Exceeding Purpose

A recommended HTTP log entry for standard SRE needs:

```json
{
  "event": "http_exchange",
  "method": "GET",
  "route": "/api/orders/{id}",
  "status": 200,
  "duration_ms": 18,
  "service": "orders-api",
  "trace_id": "synthetic_trace_id"
}
```

Note: this JSON **illustrates a schema**, not Spring Boot's automatic default output. `trace_id` should come from a trusted tracing pipeline, never from raw bearer tokens or session cookies.

Fields worth considering:

- `event`: a finite category name.
- `method`: normalized HTTP method.
- `route`: application-defined template.
- `status` and `duration_ms`: measure behavior and performance.
- `service`/`environment`: controlled deployment metadata.
- `trace_id`: links logs and traces per policy.
- `error_code`: bounded system-controlled error code, **never** a raw exception message.
- `downstream_service`: logical name without embedded full URIs or credentials.

Data to exclude from default telemetry: `Authorization`, cookies, raw paths, raw queries, raw bodies, raw headers, signed URLs, GraphQL variables, SQL literals, user profiles, card numbers, user filenames, config secrets, and raw error dumps.

Smaller, focused logs are often **more useful** because they aggregate cleanly, index quickly, and can be shared safely within operational teams.

## 10. Spring Boot 3.3 Demo: Logging Safe Access Metadata with Route Templates

The example uses Java 21, Spring Boot 3.3.13, and Gradle. The app exposes `/api/orders/{id}`, while the filter logs only the **route pattern** without reading path variables, query parameters, headers, or bodies.

Project structure:

```text
build.gradle
src/main/java/com/example/safelog/
    SafeLogApplication.java
    OrderController.java
    SafeHttpAccessLogFilter.java
src/main/resources/application.properties
src/test/java/com/example/safelog/SafeHttpAccessLogFilterTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/java/com/example/safelog/SafeLogApplication.java`:**

```java
package com.example.safelog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeLogApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeLogApplication.class, args);
    }
}
```

**`src/main/java/com/example/safelog/OrderController.java`:**

```java
package com.example.safelog;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @GetMapping("/api/orders/{id}")
    public String readOrder(@PathVariable("id") String ignoredId) {
        // Observability lesson only; ID is unused for data processing.
        return "order-ok";
    }
}
```

The controller returns a fixed body for testing. In production, protect this route with Spring Security and ownership/user/tenant authorization checks. Never interpret an unauthenticated demo controller as a secure production template.

## 11. `SafeHttpAccessLogFilter`: Extracting Only Method, Template, Status, and Duration

**`src/main/java/com/example/safelog/SafeHttpAccessLogFilter.java`:**

```java
package com.example.safelog;

import java.io.IOException;
import java.util.Set;
import java.util.concurrent.TimeUnit;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

@Component
public class SafeHttpAccessLogFilter extends OncePerRequestFilter {

    private static final Logger LOG =
            LoggerFactory.getLogger(SafeHttpAccessLogFilter.class);

    private static final Set<String> KNOWN_METHODS = Set.of(
            "GET", "HEAD", "POST", "PUT",
            "PATCH", "DELETE", "OPTIONS");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        long startNanos = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            Object mapped = request.getAttribute(
                    HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);

            String route = mapped instanceof String template
                    ? template
                    : "UNMAPPED";

            String method = request.getMethod();
            if (!KNOWN_METHODS.contains(method)) {
                method = "OTHER";
            }

            long durationMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - startNanos);

            LOG.info(
                    "http_exchange method={} route={} status={} durationMs={}",
                    method, route, response.getStatus(), durationMs);
        }
    }
}
```

**Why is this filter safer than logging the entire request?**

- `request.getHeader("Authorization")`, `getCookies()`, `getQueryString()`, `getRequestURI()`, and `getInputStream()` are **never called**.
- `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` comes from Spring MVC route matching. `/api/orders/customer-42` appears as `/api/orders/{id}`.
- Unmatched requests fall back to `UNMAPPED`—leaking no raw path.
- HTTP methods are logged only from an allowlisted standard set; unusual client-supplied method strings are normalized to `OTHER`.
- Status is an integer and duration is a non-sensitive numeric measurement for demo purposes.
- The log format string is a fixed literal containing no user-controlled text, reducing log-forging/CRLF injection risk.

**Example scope boundary:** `OncePerRequestFilter` here demonstrates **synchronous requests**. With async Servlets, SSE/streaming, or container-handled exceptions after the filter chain returns, `finally` can execute before the response finishes; status and duration at that point do not reflect the complete request lifecycle. In production, use properly configured Spring HTTP Observations or lifecycle-aware Servlet async listeners/instrumentation. **Never advertise this filter as an accurate total-duration tool for arbitrary streams.**

A developer-defined route pattern is not automatically harmless if sensitive data is hardcoded into a literal path or a custom handler mapping returns user-supplied data. Always review router conventions before production.

## 12. Sample Config: Minimal Actuator Exposure

**`src/main/resources/application.properties`:**

```properties
server.address=127.0.0.1
server.port=8080

# Keep raw Tomcat access logs disabled for the demo.
server.tomcat.accesslog.enabled=false

# Keep request/header/body debug logging disabled.
logging.level.org.springframework.web=INFO
logging.level.org.springframework.security=INFO

# Actuator: expose only health in the demo environment.
management.endpoints.web.exposure.include=health

# Keep config/env values masked even if those endpoints are ever enabled.
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never

# Do not leak application error details in error responses.
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-stacktrace=never
```

`server.address=127.0.0.1` binds the demo to loopback only. Real deployments still need network boundaries, authn/authz, and TLS. Do not treat this snippet as "complete security" for an API.

`management.endpoint.env.show-values=never` and `configprops.show-values=never` are **Spring Boot 3.3 Actuator options**; other endpoints, custom endpoints, logs, and traces are not automatically protected by these two properties.

**Never use:**

```properties
management.endpoints.web.exposure.include=*
management.endpoint.env.show-values=always
```

on an Internet-reachable service. Exposing only `health` is defense-in-depth; Spring Security/access controls remain essential whenever exposing additional internal endpoints.

Run via Gradle Wrapper:

```bash
./gradlew bootRun
```

Test with curl:

```bash
curl -i \
  -H 'Authorization: Bearer DEMO_ACCESS_CANARY' \
  -H 'Cookie: SESSION=DEMO_COOKIE_CANARY' \
  'http://127.0.0.1:8080/api/orders/DEMO_PRIVATE_ID?code=DEMO_CODE_CANARY'
```

Expected **exact** response body:

```text
order-ok
```

The log emitted by **SafeHttpAccessLogFilter** looks like:

```text
http_exchange method=GET route=/api/orders/{id} status=200 durationMs=...
```

`durationMs` varies at runtime and stdout is not byte-exact. None of `DEMO_ACCESS_CANARY`, `DEMO_COOKIE_CANARY`, `DEMO_PRIVATE_ID`, or `DEMO_CODE_CANARY` may appear in the **filter's log line**.

## 13. Canary Testing with MockMvc and `OutputCaptureExtension`

Even when developers intend never to log headers, a seemingly minor change later—such as `log.debug("request={}", request)`—can introduce secret leaks. Maintain regression tests using **synthetic sentinels**.

**`src/test/java/com/example/safelog/SafeHttpAccessLogFilterTest.java`:**

```java
package com.example.safelog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ExtendWith(OutputCaptureExtension.class)
class SafeHttpAccessLogFilterTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void doesNotLogSensitivePathQueryOrHeaders(
            CapturedOutput output) throws Exception {

        mvc.perform(get("/api/orders/PRIVATE_ORDER_CANARY")
                        .header("Authorization", "Bearer AUTH_CANARY")
                        .header("Cookie", "SESSION=COOKIE_CANARY")
                        .param("access_token", "QUERY_CANARY")
                        .param("email", "PII_CANARY"))
                .andExpect(status().isOk())
                .andExpect(content().string("order-ok"));

        String recorded = output.getOut() + output.getErr();

        assertThat(recorded)
                .contains("route=/api/orders/{id}")
                .doesNotContain("PRIVATE_ORDER_CANARY")
                .doesNotContain("AUTH_CANARY")
                .doesNotContain("COOKIE_CANARY")
                .doesNotContain("QUERY_CANARY")
                .doesNotContain("PII_CANARY");
    }
}
```

Run:

```bash
./gradlew test
```

The test verifies **console logs captured in the Spring Boot test**, not CDN, NGINX, reverse proxy, or external tracing safety. Depending on Logback appenders, also add tests targeting a **logger `ListAppender` directly** or end-to-end integration tests covering every real sink.

Never use **real tokens or personal data** as test fixtures. Pick distinct canaries named after the **risk category**, and avoid echoing canary strings inside `log.info` or test reports when passing.

If another controller/logger prints raw requests, this test catches it when written to captured stdout/stderr. External out-of-process exporters do not appear in captured stdout, so test every sink separately.

## 14. Standalone Java 17 Exercise on Header Policies

A self-contained example needing no Spring, demonstrating **never reflecting any header value**. When classifying whether a header is sensitive, operate solely on its name:

**`HeaderPolicyDemo.java`:**

```java
import java.util.Locale;
import java.util.Set;

public class HeaderPolicyDemo {
    private static final Set<String> SENSITIVE = Set.of(
            "authorization",
            "proxy-authorization",
            "cookie",
            "set-cookie",
            "x-api-key",
            "x-auth-token");

    public static String display(String name, String value) {
        String normalized = name.toLowerCase(Locale.ROOT);
        if (SENSITIVE.contains(normalized)) {
            return "[REDACTED]";
        }
        return "[OMITTED]";
    }

    public static void main(String[] args) {
        System.out.println(display(
                "AUTHORIZATION", "Bearer DEMO_SECRET"));
        System.out.println(display(
                "Set-Cookie", "SESSION=DEMO_ID"));
        System.out.println(display(
                "Referer", "https://example.test/?code=DEMO_CODE"));
    }
}
```

Compile and run:

```bash
javac HeaderPolicyDemo.java
java HeaderPolicyDemo
```

**Exact stdout:**

```text
[REDACTED]
[REDACTED]
[OMITTED]
```

This design intentionally **refuses to log even "supposedly ordinary headers"**. `Referer` is omitted despite not being in `SENSITIVE`, because URLs can carry sensitive parameters. The `value` parameter exists only to illustrate the API signature and is never touched: in real applications, **avoid reading the header value altogether** when only status and route matter.

Never turn this into a small denylist of a few header names while logging every remaining header verbatim. Custom headers, tracing baggage, and new cookie aliases carry unpredictable secrets.

## 15. `CommonsRequestLoggingFilter`: Even a "Safe-Looking" Config Can Leak Paths

Spring Framework includes `CommonsRequestLoggingFilter`, often enabled to inspect requests. Options include query string, headers, payload, and max payload length. Many online snippets show:

```java
// Do NOT apply in production without evaluating real data:
CommonsRequestLoggingFilter filter =
        new CommonsRequestLoggingFilter();
filter.setIncludeQueryString(true);
filter.setIncludeHeaders(true);
filter.setIncludePayload(true);
```

This configuration can dump query secrets, cookies, and bodies into logs. Setting `setMaxPayloadLength(1024)` **does not redact secrets**; tokens in the first 200 bytes still leak.

Even with all three `include...` flags set to `false`, the filter can still log the **request URI containing PII in the path**. Endpoints with sensitive path variables should prefer **route-template logging** as shown earlier rather than merely disabling headers/bodies in this filter.

Even if a library supports filtering specific headers, you must verify version behavior, trust policies, encodings, and custom headers; for HTTP access summaries, the safest stance is **no header values at all**.

Do not inspect only `application.properties`: an internal library might register a `CommonsRequestLoggingFilter` bean or `FilterRegistrationBean` that logs sensitive data as soon as a logger level is lowered.

## 16. Tomcat Access Logs: Request Lines and Queries Can Leak Secrets

Spring Boot MVC normally embeds Tomcat, which has its own access log config:

```properties
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.pattern=common
```

In many Servlet containers, the `common` format logs the full request line, potentially exposing URLs/paths/queries containing sensitive data. **Never enable a pattern with `%r`, `%q`, or `%U` without auditing contents and PII protection rules.** Even `%U` (URI path) exposes emails or account IDs inside dynamic path segments.

If operations only require HTTP method and status, a minimal pattern can serve as a **defensive baseline**:

```properties
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.pattern=%m %s
```

This pattern logs only HTTP method and response status; it **cannot print route templates** because Tomcat's access logger runs at the container layer outside MVC's normalized routing metadata. It does not replace HTTP metrics and logs normalized from `HandlerMapping`.

When legal or operational rules mandate forensic access logs (IP, URL), isolate them in dedicated partitions with strict access policies instead of collecting everything into general logs readable by every engineer. Verify the active pattern, access log output directory, and file/volume permissions at startup.

**Note:** `server.tomcat.accesslog.enabled=false` only turns off Boot-configured Tomcat access logging; external NGINX, CDN, and load balancer tiers keep their own access logs.

## 17. Reactor Netty, WebFlux, and HTTP Wiretap: Never Enable Carelessly in Production

Spring WebFlux typically runs on Reactor Netty. `wiretap`/HTTP client debug logging inspects network channels and—depending on mode—prints **headers and body bytes**. Never turn it on against uncontrolled live production traffic just to chase a TLS/HTTP glitch.

Potential logging sources:

- Reactor Netty `HttpServer` or `HttpClient` wiretap.
- Netty logging handlers.
- Spring WebFlux `WebFilter` code explicitly reading headers and bodies.
- Codec/encoder/decoder debug logs when request-details logging is enabled.
- Spring Security `DEBUG`/`TRACE`.
- Outbound wire logs from Apache HttpClient, JDK HttpClient, or other libraries.

**Never assume only controller `log.info` calls emit logs.** Agents and tracing libraries can capture HTTP attributes even when your app logs nothing for the request.

Safe conceptual pattern in WebFlux:

```java
// Design sketch; requires a WebFlux project context:
return chain.filter(exchange)
        .doFinally(signal -> {
            // Log normalized status/outcome and route template.
            // Never log exchange.getRequest().getURI().toString().
            // Never log request headers or body.
        });
```

This is not a standalone source file; WebFlux uses `WebFilter`, `ServerWebExchange`, `WebFilterChain`, and Reactor. **Cancellation/streaming** lifecycles differ from synchronous MVC: `doFinally` fires on cancel, error, or completion, so verify status and timing semantics. When an error happens before handler mapping resolves a route, log `UNMAPPED` rather than echoing the raw request URI.

To debug Netty for real, enable wiretap only with synthetic requests in an isolated environment for a brief window with restricted access, verifying the pipeline **emits no secrets** before real traffic ever touches it.

## 18. Outbound HTTP Clients Are Also a Leak Source

Spring Boot apps call downstream services via `RestClient`, `RestTemplate`, `WebClient`, Feign, or Apache HttpClient. Outbound headers carry bearer tokens, `Cookie`, API keys, or signed URLs; responses carry customer data.

Anti-pattern:

```java
// Do not do this: full URI and headers can contain secrets.
log.debug("calling {} headers={}",
        request.getURI(), request.getHeaders());
```

Replace with logical metadata:

```text
outbound_call peer=inventory-api operation=get-stock status=200 durationMs=43
```

`peer` and `operation` are **finite service/operation names defined in code**, never arbitrary hostnames from user input. If using OpenTelemetry/Micrometer tracing, audit which attributes HTTP client instrumentation records—especially `url.full`, queries, and header capture.

When outbound calls fail, HTTP client exception messages can embed the **full URL**, including signed queries. Never log arbitrary exception messages/stack traces unconditionally for public errors without auditing `getMessage()` and inner causes.

A 400 validation failure from a REST call can carry **`rejectedValue`** fields; never dump full binding results into logs or error responses. Emit safe error categories and correlation IDs, keeping sensitive details restricted to authorized flows.

## 19. Error Handling: Avoid Leaking via Exception Messages, Stack Traces, or HTML Error Pages

Exceptions can originate from:

- Invalid credentials.
- SQL constraints/bindings.
- JWT parsing failures.
- HTTP client requests to signed URLs.
- File uploads with sensitive filenames.
- Validation failures containing rejected values.
- XML/JSON parsers quoting snippets of payload inside messages.
- Template rendering errors printing paths/context.

If you log:

```java
// Risky: Throwable message/cause may hold request details.
log.error("Request failed: {}", exception.getMessage(), exception);
```

both the message and stack trace can expose secrets. Classify errors using **controlled error codes**, trace IDs, and minimal operational metadata. Detailed exception diagnostics belong only in strictly protected stores **after** evaluation—never assume `Throwable.toString()` is harmless.

Sample error handler:

```java
package com.example.safelog;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class PublicErrorHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    public ProblemDetail badRequest(IllegalArgumentException ignored) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Invalid request");
    }
}
```

This is an **integration sample** that can be added as `PublicErrorHandler.java` to the demo. It logs no exception details and echoes no submitted values. In production, classify specific exception types rather than broad `IllegalArgumentException` used here for illustration. Never return `200 OK` on errors or bypass actual authorization checks.

`server.error.include-stacktrace=never` and `server.error.include-message=never` help suppress error details in default Spring Boot error responses, yet they **do not automatically secure custom exceptions, custom handlers, or GraphQL errors**. Test JSON and HTML error responses across failure paths.

## 20. Metrics: Route Templates Instead of Raw Paths and User IDs

Spring Boot Actuator + Micrometer Observation emits HTTP metrics, usually `http.server.requests`; instrumentation sets the `uri` tag to the **unsubstituted URI template** whenever resolved.

Good:

```text
http.server.requests{method="GET",uri="/api/orders/{id}",status="200"}
```

Bad:

```text
http.server.requests{uri="/api/orders/PRIVATE_ORDER_123"}
http.server.requests{email="alice@example.test"}
http.server.requests{authorization="Bearer ..."}
```

Raw paths, emails, `userId`, `sessionId`, access tokens, and `traceId` create **high cardinality** or expose PII; attaching them per request can generate millions of time series, inflate costs, and leak data on dashboards.

Watch out for a subtle trap: high-cardinality key-values in Micrometer Observation are excluded from metric labels, yet can still **be exported as trace attributes**. **Never put PII into high-cardinality attributes assuming it is safe** just because Prometheus metrics omit it.

When user-level dimensions are needed, pick bounded labels like `auth_result=SUCCESS|FAILURE`, `plan_tier=FREE|PAID` (if approved and non-sensitive), `route`, `method`, `status`, and `outcome`. Never use free-text exception messages or query text as dimensions.

## 21. Traces: Baggage, Span Attributes, and Sampling Do Not Replace Redaction

A trace follows a request across services. Sensitive data can show up in:

- Span names.
- Span attributes (HTTP URL, query, user ID, status, error message).
- Span events and exception events.
- Context propagation headers.
- **Baggage** propagated between services.
- Custom annotations or business tags.
- Database and HTTP client instrumentation.

W3C `traceparent` carries trace/span IDs and flags—it is **not a credential**. Even so, validate inputs and apply trust boundaries when crossing untrusted networks. `baggage` can carry **arbitrary text**, so never put emails, tokens, session IDs, or medical data into baggage "for debugging convenience".

**Sampling reduces record count, not the sensitivity of an individual record.** 1% sampling still stores 1% of tokens if instrumentation captures tokens. Tracing must never capture a full `Authorization` header just because "the odds of saving it are small".

When creating custom spans/observations, use only allowlisted attributes. Avoid:

```java
// Wrong: sensitive attribute can flow to the tracing exporter.
observation.highCardinalityKeyValue(
        "access_token", request.getHeader("Authorization"));
```

If business/audit correlation by user is required, adopt an explicit policy using pseudonymization or a protected business audit store with defined retention. **Never use trace tags as a personal-data repository.**

## 22. Actuator `httpexchanges`: Not an Automatic Data-Masking Mechanism

Spring Boot 3.3 offers `/actuator/httpexchanges` to inspect recent request-response exchanges when an **`HttpExchangeRepository` bean** is configured. Recorded fields can include URI, method, headers, status, principal, session info, and elapsed time depending on recording configuration. This data is potentially sensitive.

Key facts to understand:

1. Adding `spring-boot-starter-actuator` alone **does not** populate HTTP exchanges; a repository bean is required.
2. This endpoint is **not exposed over HTTP by default**, and should only be enabled/accessible with clear operational justification.
3. Raw exchange URIs can hold private queries/paths, and headers can hold credentials depending on recording rules. Never assume it is "safe logging" just because it comes from Actuator.
4. Principal/session metadata can also constitute personal data or sensitive identifiers.
5. `management.endpoint.env.show-values=never` **does not redact `httpexchanges`**; that property applies to a different endpoint.
6. An in-memory `HttpExchangeRepository` suits demos, not durable, secure production logging/metrics/tracing.

If your organization needs an HTTP exchange audit, write filtered/normalized metadata into a custom policy-compliant repository or rely on properly hardened telemetry pipelines rather than turning on full capture behind a network firewall alone.

`/actuator/logfile`, `/actuator/env`, `/actuator/configprops`, `/actuator/heapdump`, `/actuator/threaddump`, and `loggers` each carry exposure risks. Heap dumps can hold in-memory secrets; logger management can be abused to toggle `DEBUG`/`TRACE`. **Restrict permissions and isolate the management port/network** whenever used.

## 23. `env` and `configprops` Are Masked by Default, Not All of Actuator

In Spring Boot 3.3, `/env`, `/configprops`, and `/quartz` mask values to `******` by default. `show-values` options include:

```properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
```

`never` hides values even from authenticated users, fitting a conservative production HTTP API policy.

Never set `always` just to debug, as it can expose connection strings, secrets, feature flags, and internal details. `when-authorized` shows values to authorized callers, yet still warrants review: secrets might appear unmasked if sanitizer rules miss custom keys.

`SanitizingFunction` customizes masking on certain Actuator endpoints; it is not a global filter for application logs, Tomcat access logs, or OpenTelemetry span attributes.

**Minimizing exposure** is just as vital as masking. Never expose all of Actuator publicly assuming a single masking flag protects every endpoint.

## 24. Reverse Proxies, Ingress, WAF, and CDNs Must Share the Same Policy

An HTTP request can be logged by NGINX before the Java process ever sees it:

```text
Browser -> CDN access log -> WAF log -> Gateway log
                                 -> Tomcat access log
                                 -> App log / tracer
```

Even when your Spring filter avoids raw URIs, NGINX can still log `$request` (full request line with path/query), `$request_uri` (including query), `$http_authorization`, `$http_cookie`, or response `Set-Cookie` via a custom `log_format`.

Recommendation: configure an **allowlisted `log_format`** recording method/status, upstream response time, and gateway-normalized route keys if supported—never raw URI/query strings or header values. A proxy unaware of Spring MVC route templates should record **service route categories** or statuses rather than guessing `/orders/{id}` via fragile regexes.

Check all of these layers:

- NGINX `access_log`/`log_format` and error logs.
- Ingress annotations or gateway plugins capturing HTTP headers.
- API Gateway policies and external access logs.
- CDN/WAF request samples and blocked-request diagnostic payloads.
- Load balancer access logs and correlation IDs.
- Service mesh sidecars and eBPF agents.
- Platform-installed APM auto-instrumentation/HTTP capture.
- Request mirroring/shadow traffic sent to other environments.

Never let a "less secure" staging environment store mirrored production traffic containing real PII. Use synthetic traffic for debugging without copying live customer data.

## 25. Distinguishing Auditable Security Events from Secrets Never to Log

Refusing to log raw credentials **does not mean disabling security auditing**. Useful events include:

| Event | Metadata to consider | Data never to store |
| --- | --- | --- |
| Login succeeded | Timestamp, outcome, auth method, pseudonym if justified | Password, token, cookie |
| Login failed | Bounded failure category, route, rate-limit bucket | Entered password, raw username/email by default |
| Permission denied | Operation/role category, resource type, status | Full resource payload, bearer token |
| Token expired | `auth_failure=EXPIRED` | Raw JWT, refresh token |
| Session logout | Event type, status, appropriate correlation | Raw session ID |
| Sensitive data access | Resource category, action, policy-compliant audit principal | Copies of records/medical data |
| API key rotation | Approved internal key identifier, action/outcome | API key value or private key |

When mandatory auditing requires real identities, send events to a **strictly access-controlled audit store** with retention, encryption, viewer auditing, and legal rationale—never dump them into generic application logs or metrics. Enforce role-based access for audit viewers.

Audit events must ensure integrity and resist log forging. Validate/normalize client data, enforce length bounds, block CR/LF log-format control characters, and use validated structured fields.

## 26. Regex Masking: Useful as a "Safety Net", Not a Guarantee

You may hear requirements like "mask every occurrence of `Bearer ...` in Logback". Regexes in appenders/layouts have serious limitations:

- Secrets may not follow the expected pattern (Basic, custom API keys, signed URLs).
- JWTs/tokens can span lines or undergo multi-layer encoding.
- JSON introduces escaped characters and arbitrary nesting.
- Compressed, binary, and multipart payloads bypass simple text regexes.
- Secrets may already have reached another appender/agent before the regex runs.
- Field-name-based masking misses PII placed under generic names like `data`.
- Complex regexes over high-volume logs burn CPU or risk ReDoS latency spikes.

If you add regex masking as defense-in-depth, test it against multi-format canaries, cap log event sizes, and monitor masking-engine failures. Still, the primary defense must remain **allowlisting safe fields before the log call happens**.

**Wrong mindset:** "We log the full body and mask a few sensitive keys."

**Right mindset:** "We do not collect bodies. If a business use case requires auditing specific fields, build a **dedicated audit DTO containing only approved fields**."

## 27. Audit DTOs Instead of Logging Raw Request Objects

Suppose a profile update API receives:

```java
public record UpdateProfileRequest(
        String fullName,
        String email,
        String phone,
        String address) {
}
```

Never do:

```java
// Wrong: record.toString() prints every field.
log.info("Updating profile {}", request);
```

Define a **minimal event model** excluding sensitive values:

```java
public record ProfileAuditEvent(
        String action,
        String outcome,
        String source,
        long durationMillis) {
}
```

When logging:

```java
// Integration pattern: use controlled metadata only.
ProfileAuditEvent event = new ProfileAuditEvent(
        "PROFILE_UPDATED", "SUCCESS", "SELF_SERVICE", 35L);
log.info("profile_audit action={} outcome={} source={} durationMs={}",
        event.action(), event.outcome(),
        event.source(), event.durationMillis());
```

This is an integration snippet requiring a real logger and business logic. `durationMillis=35L` is purely illustrative, not a live runtime measurement.

Personal data is still processed by the service to save/update records; the principle is **keep it out of observability sinks**, not erase it from business functionality. If an audit event must reference a user, use an audit-policy-approved identifier and keep arbitrary IDs out of metrics tags.

## 28. Pseudonymization: HMAC Can Fit, Yet Never Makes Data Harmless

When you must correlate logs for a single customer without exposing raw customer IDs, one option is computing an **HMAC** using a dedicated observability key:

```text
user_ref = HMAC-SHA256(observability_key, canonical_customer_id)
```

HMAC reduces dictionary-attack risk compared to plain SHA-256 over emails or phone numbers. However, the output still **links events belonging to the same individual**, so it typically still counts as pseudonymous personal data subject to privacy policy.

Constraints:

- Store the HMAC key in a secret manager, separate from JWT signing keys or business encryption keys.
- Never write the HMAC key into logs, traces, metrics, or config endpoints.
- Plan key rotation; rotating keys breaks correlation across rotation boundaries.
- Restrict who holds lookup tables or keys, and enforce retention and purpose limits.
- Never HMAC full bearer tokens to log a "token fingerprint" by default: tracking tokens remains sensitive and enables session correlation analysis.

When per-user correlation isn't genuinely needed, **skip pseudonymization and drop the identifier altogether**—that is the lowest-risk option.

## 29. Preventing Log Forging and Injection from Client Data

If a client sends a header containing newlines or control characters and a logger prints it directly:

```text
X-Client-Tag: ok\nWARN Security bypassed
```

plain-text logs can look like a forged security event. Modern containers block many illegal HTTP control characters, yet **never rely solely on container checks** across every path (JSON bodies, queries, DB text, and other inputs still carry control characters).

Mitigations:

1. Never log raw client-controlled strings.
2. When a category must be logged, validate against a character/length allowlist.
3. Use structured logging with sink-appropriate encoding.
4. Strip CR/LF/control characters per policy before logging.
5. Separate error categories from exception messages and user-submitted values.
6. Cap per-event log size to prevent attacker-driven log amplification.

**Never confuse** JSON-escaping a string with masking sensitive data: encoding prevents structural injection and makes logs parseable, yet **does nothing to hide secrets**.

## 30. With Spring Security, Never Log Raw `Authentication` or Principals

Spring Security objects contain principals, credentials, authorities, authentication details, and provider-specific attributes. Calling `log.info("auth={}", authentication)` can print personal data or sensitive fields via a custom principal's `toString()`.

Never do:

```java
log.debug("securityContext={}",
        SecurityContextHolder.getContext());
```

Log only controlled outcome categories:

```text
auth_result=SUCCESS auth_method=OIDC
auth_result=DENIED reason=INSUFFICIENT_SCOPE
auth_result=FAILURE reason=BAD_CREDENTIALS
```

Each `reason` must come from an internal enum/allowlist, never directly from an exception message. With custom JWTs, claims like email, phone, address, or custom scopes can be sensitive; never copy claims indiscriminately into trace baggage or metrics.

Enabling Spring Security `DEBUG`/`TRACE` for investigation requires an approved procedure, time limit, isolated traffic, restricted log access, and verification of what your exact library versions emit. Never paste logs into tickets or chats accessible to unauthorized parties.

## 31. GraphQL and Streaming: Queries, Variables, and Events Can Also Be Sensitive

A GraphQL request sent to `/graphql` can contain:

```json
{
  "query": "query($email: String!){ customer(email:$email){ id address } }",
  "variables": {"email":"private@example.test"}
}
```

Logging a validated `operationName` and bounded error codes can be helpful; logging the **full `query` and `variables`** easily leaks PII. Never assume a single static endpoint URL `/graphql` means requests carry no personal data.

With SSE/WebSockets, every event payload can carry order updates, chat messages, locations, or other private data. Network wiretaps or stream loggers can expose streams over long sessions. Track metrics such as active stream count, event count, close-reason category, duration, and bytes instead of logging message payloads.

When streaming fails, never dump the last payload to "reproduce". Use synthetic event IDs, trace IDs, and normalized service metrics.

## 32. Multipart Uploads, Filenames, and Binary Payloads

File uploads deserve special attention: `Content-Disposition` carries `filename`, which frequently contains people's names, case IDs, or internal details. `Content-Type` does not tell you whether the payload is sensitive.

Never log:

```text
uploaded file="passport_alice_2026.jpg" body=<binary bytes>
```

Instead log:

```text
upload_attempt route=/api/uploads status=201 size_bucket=1MiB-5MiB type=image
```

Generate/normalize `size_bucket` and `type` per policy; never log raw file paths, original filenames, or file contents. Upload size limits, malware scanning, and path traversal defenses are separate controls not solved by masking.

Storage SDK errors can embed bucket/key/path names or presigned URLs; never log `exception.getMessage()` assuming HTTP Authorization redaction covered everything.

## 33. Response Redaction and `Set-Cookie` on Error Paths

A request can fail after the server has already added response headers, including `Set-Cookie`. If a proxy or custom filter captures full responses for debugging, session credentials can still leak even when request headers are masked.

Response checklist:

- Never log `Set-Cookie`, sensitive `WWW-Authenticate` details, or custom auth headers.
- Never log response bodies containing customer records, banking data, or session tokens.
- Never log raw `Location` headers containing OAuth codes or signed URLs.
- Never return or log rejected validation values in 400 responses.
- Never expose stack traces or raw exception details in 500 responses.
- Never store error responses carrying PII in public support systems.
- To audit error classes, log an `error_code` enum and HTTP status.

Gateway/WAF error handling can generate responses before the app receives the request; inspect every layer. Sanitized app logs cannot undo a proxy logging sensitive headers on error responses.

## 34. Log Lifecycle: Collect, Ship, Store, Display, Delete

Sensitive data governance does not end in source code:

```text
Application / proxy
  -> stdout/file/journald
  -> container log collector
  -> broker/queue
  -> central logging/APM vendor
  -> index/search/dashboard
  -> exported CSV/support ticket
  -> backup/retention/deletion
```

A secret written to stdout can replicate across half a dozen systems with different retention schedules. Hiding fields in a dashboard UI **does not delete raw bytes** in storage, queues, or backups.

Required operational controls:

- TLS for telemetry transport and encryption at rest per policy.
- Least-privilege roles for viewing logs/traces.
- Separate sensitive audit stores from general application logs.
- Retention limits aligned with purpose and applicable regulations.
- Auditing of who accessed or exported sensitive logs.
- Secret scanning across log samples with alerts.
- Immediate revocation/rotation if a real token leaks.
- An incident response playbook tracking all downstream destinations that received copies.
- Never ship raw production logs to third parties without reviewing contracts and data-processing rights.

Per the OWASP Logging Cheat Sheet, access tokens, session IDs, passwords, encryption keys, sensitive personal data, and payment data must generally never be written directly to logs.

## 35. Verifying Across Every Telemetry Sink

Proper verification goes beyond `grep`ing console output. Inject synthetic canaries across every input surface:

| Surface | Synthetic canary | Where to inspect |
| --- | --- | --- |
| `Authorization` | `AUTH_CANARY_A` | App logs, traces, gateway, outbound logs |
| `Cookie` | `COOKIE_CANARY_B` | App/access logs, HTTP exchange repository |
| `Set-Cookie` | `COOKIE_CANARY_C` | Reverse proxy, response captures |
| Raw path | `PRIVATE_ORDER_CANARY_D` | Tomcat/NGINX access logs, route tags |
| Query | `QUERY_CANARY_E` | Access logs, span attributes, exception URLs |
| `Referer` | `REFERER_CANARY_F` | Gateway, custom filters, APM |
| JSON body | `BODY_CANARY_G` | Request logging, cache wrappers, traces |
| Response body | `RESPONSE_CANARY_H` | Debug/HTTP client logs, gateway |
| Multipart filename | `FILE_CANARY_I` | Upload audits, exception logs |
| GraphQL variables | `GQL_CANARY_J` | GraphQL execution errors, trace attributes |

Use **synthetic data only**, avoiding triggering real auth/payment flows with live credentials. Test 2xx, 4xx, 5xx, timeouts, redirects, retries, async/streaming, cache hits, and gateway responses when backends are down.

Verify canaries are **absent** from prohibited sinks while approved fields (`route`, `method`, `status`, `duration`, valid `traceId`) remain intact for operations.

Tests prove only the code paths executed under known conditions. Whenever adding instrumentation libraries or changing profiles/proxy configs, re-run the regression suite.

## 36. Most Dangerous Anti-Patterns

**"We only log at DEBUG."** Flawed thinking. `DEBUG` can be toggled automatically or by operators, and data still persists in log sinks.

**"Masking `password` is enough."** Wrong. Authorization, cookies, OAuth codes, signed URLs, PII, and response payloads are sensitive too.

**"Actuator sanitizes everything by default."** False. Sanitization on select endpoints does not protect `httpexchanges`, `logfile`, `heapdump`, custom endpoints, or custom tracing.

**"Reading only `getRequestURI()` avoids tokens."** Not guaranteed. Paths can hold emails, order IDs, or personal identifiers.

**"Enabling `CommonsRequestLoggingFilter` with payload off is safe."** Not guaranteed. Queries, headers, or concrete paths can still be logged depending on config.

**"Our Logback regex strips every secret."** No. Regexes miss alternate encodings, nested payloads, and other sinks.

**"Hashing emails with SHA-256 fully anonymizes them."** False. Emails are vulnerable to dictionary guessing; pseudonyms still require privacy controls.

**"0.1% sampling removes the risk."** False. Any sampled record can contain a complete secret.

**"Setting `traceId` to the session cookie makes debugging easy."** Dangerous. Trace/correlation IDs must remain separate from credentials.

**"Enabling `server.tomcat.accesslog.enabled=true` with `common` is harmless."** Audit the request line first—it carries raw URLs and queries.

**"On HTTP 500, logging the entire exception is always needed."** Not every `Throwable.getMessage()` is safe; log controlled error categories first and use protected diagnostics when necessary.

**"The frontend sends `Access-Control-Allow-Origin` to hide data."** Wrong layer. CORS is not a masking or logging control.

## 37. Codebase and Deployment Config Audit Checklist

When auditing a Spring Boot service, search by category:

**Application code:**

```text
getHeader("Authorization")
getHeaders()
getCookies()
getQueryString()
getRequestURI()
getRequestURL()
request.toString()
response.toString()
log.*(request)
log.*(response)
log.*(exception)
ContentCachingRequestWrapper
ContentCachingResponseWrapper
@ExceptionHandler
```

**Framework/HTTP clients:**

```text
CommonsRequestLoggingFilter
OncePerRequestFilter
WebFilter
WebClient ExchangeFilterFunction
RestTemplate ClientHttpRequestInterceptor
RestClient request interceptor
Reactor Netty wiretap
Apache HttpClient wire logging
Spring Security DEBUG/TRACE
```

**Observability/platform:**

```text
http.server.requests
http.client.requests
ObservationConvention
ObservationFilter
OpenTelemetry attributes
W3C baggage
Actuator httpexchanges/env/configprops/logfile
Tomcat accesslog.pattern
NGINX log_format
Ingress/Gateway/CDN log rules
Logback appenders, encoders and masking patterns
```

Do not treat every text hit as a vulnerability; inspect active code paths, logger levels, profiles, byte contents, destinations, and access controls. Also check custom internal libraries and out-of-band auto-instrumentation agents beyond Java source code.

**Prioritize fixes in order:** raw data emitters → telemetry allowlists → canary tests → collector filters (secondary defense) → permissions/retention → continuous monitoring.

## 38. Comprehension Exercises

1. Why is `Authorization: Bearer ...` a credential rather than harmless debug metadata?
2. Why must `Cookie` and `Set-Cookie` be excluded from both request and response captures?
3. How does `request.getRequestURI()` differ from `request.getQueryString()`, and why can both hold PII?
4. Why is route template `/api/orders/{id}` better than `/api/orders/customer-42` in logs and metric labels?
5. Does `CommonsRequestLoggingFilter.setIncludePayload(false)` eliminate risks from dynamic paths?
6. Does `ContentCachingRequestWrapper` sanitize bodies or eliminate memory risks automatically?
7. Why doesn't `server.tomcat.accesslog.enabled=false` prevent NGINX/CDNs from logging raw URLs?
8. When a high-cardinality Micrometer field contains an email, where can it still leak despite not being a metric label?
9. Lowering sampling reduces record counts—does it redact credentials?
10. Does `management.endpoint.env.show-values=never` apply to `httpexchanges`?
11. Why can `Throwable.getMessage()` or a stack trace leak a signed URL?
12. Which scenarios require policy-governed pseudonymization, and why is HMAC not true anonymity?
13. How do you design a canary test to catch leaks in both app logs **and** gateway logs?
14. Why must even expired tokens stay out of logs?
15. Upon discovering a production access token in logs, what steps must be taken for log destinations/copies and the credential?
16. What is the boundary between identity-bearing business audits and aggregated HTTP metrics?
17. With asynchronous SSE, why can a Servlet filter's `finally` block run before the response ends?
18. When adding a new endpoint whose path includes an email, which test should be updated to confirm route normalization?

**Lab A:** Run the Spring Boot demo and send a request with 4 canaries across headers, path, and query. Inspect stdout, filter logs, and Actuator exposure; confirm only route template, status, and duration are recorded.

**Lab B:** In an isolated test environment, temporarily enable an access log pattern recording the request line; observe the raw path/query leak, then fix the pattern or disable logging. Never use real data, and restore safe configuration immediately afterward.

**Lab C:** Send two GET requests with distinct path variables to the same route, verify Micrometer's `uri` tag is normalized, and ensure no raw path becomes a custom tag.

**Lab D:** Write an audit DTO allowing only `action`, `outcome`, `errorCode`, and `durationMs`, then write a unit test asserting no password/email/token fields exist. Verify error paths as well.

## 39. Conclusion: Not Collecting Is the Strongest Defense

**A reliable implementation blueprint:**

```text
1. Classify data requiring protection
2. Allow only minimal HTTP metadata
3. Log route template, method, status, latency, outcome
4. Exclude auth headers, cookies, queries, bodies, raw paths
5. Restrict and audit Actuator, wiretap, gateways, access logs
6. Keep traces/metrics strictly to approved fields/labels
7. Test synthetic canaries against every telemetry sink
8. Govern pipelines, retention, access controls, and incident response
```

In Spring Boot, **no single magic property** hides sensitive data across all HTTP logs, metrics, traces, Actuator endpoints, proxies, and HTTP clients. Enforce protection at **every telemetry emitter**. Allowlist metadata, exclude `Authorization`, `Cookie`/`Set-Cookie`, personal data, and raw paths/queries/bodies; when sensitive auditing is required, isolate it in a dedicated store under explicit policies. Strong observability security is proven by canary tests, never by a promise that "masking is turned on".

### Official Reference Documentation

- Spring Boot 3.3 — Actuator Endpoints, Security, and Sanitizing Sensitive Values: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — Observability: https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html
- Spring Boot 3.3 — HTTP Metrics / URI Template: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
- Spring Boot 3.3 — Common Application Properties (`server.tomcat.accesslog.*`, `management.endpoint.*`): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Framework 6.1 — `OncePerRequestFilter`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Framework 6.1 — `AbstractRequestLoggingFilter`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/filter/AbstractRequestLoggingFilter.html
- Spring Framework — HTTP Observations: https://docs.spring.io/spring-framework/reference/integration/observability.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OpenTelemetry Semantic Conventions — HTTP: https://opentelemetry.io/docs/specs/semconv/http/