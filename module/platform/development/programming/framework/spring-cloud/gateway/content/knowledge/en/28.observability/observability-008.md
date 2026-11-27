# HTTP Client/Server Wiretap and Protecting Sensitive Data

## Learning Objectives

In the **Observability** chapter of **Spring Cloud Gateway**, this lesson focuses on a powerful diagnostic technique that also carries serious risk: **Reactor Netty `HttpServer` and `HttpClient` wiretap logging**. When an API Gateway receives a request, evaluates **route predicates**, runs **filter chains**, authenticates, rewrites paths/headers, retries, circuit-breaks, load-balances, and dispatches HTTP upstream to microservices, wiretap lets you see events and data at those HTTP legs.

However, a single wiretap record can contain **bearer tokens, cookies, API keys, customer IDs, query strings, JSON request/response bodies, payment data, or other sensitive content**. Leaving DEBUG enabled on real traffic without safeguards creates a brand-new secret store inside your log pipeline.

After this lesson, you will be able to:

- Distinguish **HTTP server-side** wiretap (client ↔ Gateway) from **HTTP client-side** wiretap (Gateway ↔ upstream).
- Understand `READ`, `WRITE`, connection IDs, `HEX_DUMP`, `TEXTUAL`, and `SIMPLE`, and why a connection ID is not an HTTP request ID.
- Enable/disable `httpserver.wiretap` and `httpclient.wiretap` in the exact **Spring Cloud Gateway Server WebFlux namespace** and configure appropriate DEBUG loggers.
- Distinguish wiretap from **access logs**, **application logs**, **Micrometer metrics**, **distributed tracing**, and **audit logs**.
- Explain why HTTPS/TLS does not render wiretap logs harmless.
- Design a **minimal, time-boxed diagnostic workflow on synthetic traffic** without logging real bodies or credentials.
- Use allowlisted metadata logging, `routeId`, status, latency, and trace IDs instead of full HTTP payloads in production.
- Test sensitive-data filtering, manage retention and RBAC, and purge accidentally captured records.
- Diagnose Gateway 404/502/503s, retries, response header mismatches, and TLS errors without turning on full-request logging by default.

> **Scope:** Examples use **Spring Cloud Gateway Server WebFlux** backed by **Reactor Netty**. Do not treat Gateway Server Web MVC's `WebMvc.fn`, `ProxyExchange`, Servlet `Filter`, or external ingress logging as drop-in replacements for Netty wiretap. Spring Cloud Gateway spans multiple release trains; the main YAML examples illustrate the **current prefix** `spring.cloud.gateway.server.webflux.*`, whereas older releases used `spring.cloud.gateway.*`. Always cross-check against your running Spring Boot, Spring Cloud Gateway, and Reactor Netty versions.

## 1. What Is Wiretap and Why Use It Strictly for Diagnostics?

**Wiretap** is instrumentation/logging at Reactor Netty's **network I/O layer**. When enabled on `HttpServer` or `HttpClient` with its logger set appropriately, it records connection lifecycle events, read/write directions, and HTTP byte buffers.

Picture a request:

```text
Client
  │   HTTP request (public path, headers, body)
  ▼
Gateway HttpServer    ← HTTP server wiretap
  │
  │   Spring Security, route matching, GlobalFilter,
  │   GatewayFilter, RewritePath/SetRequestHeader...
  │
Gateway HttpClient    ← HTTP client wiretap
  │
  │   HTTP request (upstream path, headers, body)
  ▼
Order Service
  │
  │   HTTP response
  ▼
Gateway HttpClient    ← response wiretap upstream → Gateway
  │
  │   response filters, fallback, headers...
  ▼
Gateway HttpServer    ← response wiretap Gateway → Client
  │
  ▼
Client
```

This diagram shows **four logical observation points**:

1. Server `READ`: Gateway receives the client request.
2. Client `WRITE`: Gateway sends the request upstream.
3. Client `READ`: Gateway receives the upstream response.
4. Server `WRITE`: Gateway sends the final response to the client.

This helps when:

- Client calls `/api/orders/42` yet the backend receives `/42`, pointing to a `StripPrefix` misconfiguration.
- An `X-Request-Id` header exists at the client yet disappears before upstream.
- Gateway returns 502/503 and you need to confirm whether an upstream connection actually opened.
- Response headers from the backend differ from what Gateway sends to the browser.
- You need to separate bugs across **route selection**, **filter chain**, **outbound client**, and **upstream**.

With real data, however, **more visibility does not mean more safety**. Wiretap can replicate one sensitive request across stdout, log files, log agents, and centralized log stores.

### 1.1. Wiretap Is Not Raw Packet Capture

Reactor Netty wiretap observes **events and buffers inside the Netty pipeline**. It is not tcpdump/Wireshark on a network interface, nor does it guarantee TLS bytes on the wire appear encrypted in logs.

Handler placement in the pipeline and logger type determine what gets recorded. With HTTPS, **HTTP payloads after TLS decryption (or before TLS encryption) can appear as readable plaintext in application logs**. Never treat “WSS/HTTPS is enabled” as protection for wiretap logs.

### 1.2. Necessity Matrix

| Symptom | Tools to Try First | When to Consider Wiretap? |
| --- | --- | --- |
| Rising 5xx | Gateway metrics, backend health, tracing | When unclear whether Gateway sends/receives valid HTTP |
| Wrong route match | Actuator routes, `routeId` logs, predicate tests | When proving exact path/headers across an HTTP hop |
| Rising 429 | Rate limiter metrics, safe auth/`KeyResolver` logs | Rarely; never dump tokens just to explain quotas |
| Unusual retries | Retry counters, idempotency logs, traces | When testing HTTP attempts on synthetic traffic |
| TLS handshake error | TLS/Netty exception categories, cert diagnostics | No body logging needed—no valid HTTP payload exists |
| Missing/mutated header | Header-name allowlist diagnostics, backend echo | Only in a controlled test environment |
| Broken body rewrite | Synthetic JSON tests, content-length/encoding checks | Only with fake bodies and isolated loggers |
| KPI reporting | Micrometer + dashboards | **Never use wiretap** for ongoing dashboards |

**Rule:** wiretap is a **point-in-time investigation tool**, never a default observability strategy for all Gateway traffic.

## 2. `HttpServer` and `HttpClient`: Two Connections, Four Data Directions

Spring Cloud Gateway Server WebFlux typically uses a **Netty HTTP server** for incoming traffic and a **Netty HTTP client** for outbound backend calls.

```mermaid
sequenceDiagram
    participant C as Client
    participant HS as Gateway HttpServer
    participant F as Gateway filters
    participant HC as Gateway HttpClient
    participant B as Backend
    C->>HS: GET /api/orders/42
    Note over HS: Server READ
    HS->>F: Match route + rewrite
    F->>HC: GET /orders/42
    Note over HC: Client WRITE
    HC->>B: HTTP request
    B-->>HC: 200 + JSON
    Note over HC: Client READ
    HC-->>F: Response to filter chain
    F-->>HS: Processed headers/body
    HS-->>C: 200 + JSON
    Note over HS: Server WRITE
```

### 2.1. Reading Logs from the Gateway's Perspective

| Logger / Observation Point | Event Direction | Meaning |
| --- | --- | --- |
| `reactor.netty.http.server.HttpServer` | `READ` | Gateway reads bytes from client or ingress |
| `reactor.netty.http.server.HttpServer` | `WRITE` | Gateway writes bytes to client or ingress |
| `reactor.netty.http.client.HttpClient` | `WRITE` | Gateway writes bytes to upstream backend |
| `reactor.netty.http.client.HttpClient` | `READ` | Gateway reads bytes from upstream backend |

`READ` does **not** mean “the client read the response,” and `WRITE` does **not** mean “the backend processed the request successfully.” They describe I/O **from that logger's perspective**.

### 2.2. What Does Server-Only Wiretap Show?

Enabling only:

```yaml
httpserver:
  wiretap: true
httpclient:
  wiretap: false
```

shows client/Gateway traffic on the server side, yet **does not** show the exact HTTP request after `RewritePath`, `SetRequestHeader`, and outbound load balancing.

For example:

```text
Server READ:   GET /api/orders/42
```

The backend may receive:

```text
GET /orders/42
```

but confirming what went upstream requires HTTP client wiretap or a controlled backend stub. When comparing both sides, prefer a **test environment with fake data** instead of enabling both in production.

### 2.3. What Does Client-Only Wiretap Show?

Enabling only:

```yaml
httpserver:
  wiretap: false
httpclient:
  wiretap: true
```

focuses logs on Gateway–upstream I/O. Here you see payloads after:

- Path rewrites.
- Header additions, removals, or overrides.
- Routing to a specific `lb://` instance.
- Multiple HTTP retry attempts.
- HTTP client proxy and TLS settings.

However, client wiretap **will not show** why an inbound request was rejected by Spring Security before entering the Gateway route chain; 401/403 requests never trigger an outbound HTTP call.

### 2.4. Request IDs and Connection IDs Are Not the Same

A Netty connection ID like:

```text
[a1b2c3d4, L:/10.0.0.5:8080 - R:/10.0.0.9:53000]
```

identifies a **connection/channel** at a point in time, not a unique UUID per **HTTP request**. HTTP keep-alive reuses a connection across many requests; HTTP/2 multiplexes concurrent streams over one connection.

Never equate `server connection ID == client connection ID`: the Gateway normally maintains **two distinct connections**, and the client connection pool reuses upstream connections across unrelated requests.

For safe request correlation, use **`traceId`/`spanId`** generated and propagated by tracing infrastructure; you may also attach a policy-governed request ID, but never substitute connection IDs or user tokens for trace context.

## 3. Enabling Wiretap with Accurate Spring Cloud Gateway Configuration

In newer **Spring Cloud Gateway Server WebFlux** releases, configuration properties are:

```text
spring.cloud.gateway.server.webflux.httpserver.wiretap
spring.cloud.gateway.server.webflux.httpclient.wiretap
```

Both default to **`false`** in current configuration tables.

### 3.1. YAML Example Strictly for an Isolated Diagnostic Environment

```yaml
# application-wiretap-lab.yml
# Enable only with fake traffic and isolated log sinks.
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpserver:
            wiretap: true
          httpclient:
            wiretap: true

logging:
  level:
    reactor.netty.http.server.HttpServer: DEBUG
    reactor.netty.http.client.HttpClient: DEBUG
```

**This is a lab config, not a production recommendation.** With both flags and DEBUG loggers active, log volume surges and includes HTTP headers and bodies. Saving this under a `wiretap-lab` profile does not prevent someone from accidentally activating it in production; enforce separate deployment/RBAC policies.

Keep two separate conditions straight:

1. `httpserver.wiretap` / `httpclient.wiretap` **attaches the wiretap handler to the Netty HTTP pipeline**.
2. Setting `logging.level` appropriately **allows DEBUG events to be emitted**.

If wiretap stays `false` while you raise the logger to DEBUG, raw I/O will not turn into wiretap dumps. If wiretap is `true` while the logger remains at INFO/WARN, expected DEBUG lines will not appear.

### 3.2. Investigating Upstream Only

If the backend returns errors while Gateway ingress looks healthy:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpserver:
            wiretap: false
          httpclient:
            wiretap: true
logging:
  level:
    reactor.netty.http.client.HttpClient: DEBUG
```

This remains a **high-risk mode** because upstream requests can carry tokens and JSON bodies. Use **synthetic requests**, an isolated pod/namespace, and separate log outputs. Unless you guarantee only fake data flows through that pod, **do not enable it** just because fewer lines are logged.

### 3.3. Legacy Version Namespace

Earlier Spring Cloud Gateway versions before the namespace change used:

```yaml
spring:
  cloud:
    gateway:
      httpserver:
        wiretap: true
      httpclient:
        wiretap: true
```

The properties:

```text
spring.cloud.gateway.httpserver.wiretap
spring.cloud.gateway.httpclient.wiretap
```

appear in older Gateway Server WebFlux documentation. Never copy old properties into Gateway 5.x assuming `true` takes effect. Conversely, do not apply `server.webflux` to Gateway 3.x or Gateway Server Web MVC if unsupported.

**How to confirm:** check **version-accurate** configuration properties/Javadoc, the project's dependency tree, startup logs, and a test with fake HTTP payloads. Never assume Spring Boot always warns when an unrecognized property is ignored.

### 3.4. Do Not Treat “DEBUG Logger” as a Safe Toggle

If an app initializes Netty HTTP client/server **with wiretap enabled**, dynamically raising the logger to DEBUG starts emitting dumps. If the flag started as `false`, changing the logger level **does not retroactively attach wiretap handlers** to already-created connections.

Thus, a successful `/actuator/loggers` call does not guarantee wiretap is “cleanly toggled” across every instance. Similarly, mutating runtime properties may not reconfigure existing Netty client/server instances until contexts or connections rebuild per version semantics.

**Manage activation/deactivation via controlled deployment configs and live verification**—never let an unguarded loggers API toggle wiretap across a live cluster.

## 4. Reactor Netty Has Three Wire Logging Formats

Reactor Netty supports `AdvancedByteBufFormat`:

| Format | What It Records | Data Sensitivity | Use Case |
| --- | --- | --- | --- |
| `SIMPLE` | Events, byte counts, connection/channel metadata; no content buffer dumps | Lower, **yet not completely harmless** | Diagnosing connect/read/write lifecycles |
| `HEX_DUMP` | Events **plus content** as hex/ASCII dumps | **Very high** | Analyzing HTTP bytes/framing in a lab |
| `TEXTUAL` | Events **plus content** as readable text | **Very high** | Reading headers/bodies in a lab with fake data |

Per Reactor Netty docs, **`HEX_DUMP` is the default formatter** when default wire logging is used. Hex encoding does not protect data: hex can be decoded straight back to original bytes, and dumps even include an ASCII column showing HTTP headers and bodies directly.

### 4.1. Example `SIMPLE` Events

```text
[conn-id-1, L:/127.0.0.1:8080 - R:/127.0.0.1:53000] REGISTERED
[conn-id-1, L:/127.0.0.1:8080 - R:/127.0.0.1:53000] ACTIVE
[conn-id-1, L:/127.0.0.1:8080 - R:/127.0.0.1:53000] READ: 142B
[conn-id-1, L:/127.0.0.1:8080 - R:/127.0.0.1:53000] WRITE: 205B
```

These lines are **illustrative**, not an exact format or byte-count promise across all versions. While body bytes are omitted, they still expose:

- Endpoint addresses/ports and network topology.
- Traffic volumes and communication cadence.
- Activity timing.
- Other loggers/handlers that may still log URIs or headers outside this formatter.

`SIMPLE` reduces **content-dump** risk inside the formatter itself, yet does not replace RBAC, retention limits, or log-infrastructure security.

### 4.2. `HEX_DUMP` Still Leaks Secrets Despite Looking Like Machine Code

A fake payload:

```http
POST /api/orders HTTP/1.1
Authorization: Bearer TEST_TOKEN_ONLY
Cookie: SESSION=TEST_COOKIE_ONLY
Content-Type: application/json

{"customerEmail":"fake@example.test"}
```

when hex-dumped still preserves every byte of `Authorization`, `TEST_TOKEN_ONLY`, session, and email. Any hex decoder restores the content. **Never call `HEX_DUMP` redaction or encryption.**

### 4.3. `TEXTUAL` Makes the Risk Obvious, Not Smaller

In a lab, the textual formatter makes output readable:

```text
READ: 123B POST /api/orders HTTP/1.1
Authorization: Bearer TEST_TOKEN_ONLY
Cookie: SESSION=TEST_COOKIE_ONLY
...
```

These are **fake values**, not live tokens or sessions. A centralized log store receiving equivalent lines in production becomes an unmanaged secret repository outside credential governance.

### 4.4. Customizing the Formatter via the Reactor Netty API

Reactor Netty exposes APIs such as:

```java
import io.netty.handler.logging.LogLevel;
import reactor.netty.http.client.HttpClient;
import reactor.netty.transport.logging.AdvancedByteBufFormat;

HttpClient diagnosticClient = HttpClient.create()
    .wiretap(
        "safe-diagnostic-wire",
        LogLevel.DEBUG,
        AdvancedByteBufFormat.SIMPLE
    );
```

This creates an **independent Reactor Netty `HttpClient` to illustrate the API**; it does not reconfigure the `HttpClient` Spring Cloud Gateway uses for routing. To customize Gateway's Netty client or server, use the **official extension/customizer for your exact version**, test TLS, pooling, proxies, and LoadBalancer behavior, and avoid accidentally wiping out default settings.

Never assume you can pick `AdvancedByteBufFormat.SIMPLE` via an invented YAML key like `httpclient.wiretap-format` unless that Gateway version's configuration-properties table **explicitly defines** it.

### 4.5. `SIMPLE` Still Incurs Overhead

Even without body dumps, logging every I/O event under heavy traffic can:

- Flood the logging framework with messages.
- Increase CPU, allocations, and lock contention.
- Overload log collectors/agents.
- Inflate storage and search costs.

Therefore, when you only need request counts, connections, p95 latency, or error rates, use **Micrometer metrics and tracing** instead of continuous wiretap.

## 5. What Does Wiretap See in HTTP Headers and Bodies?

An HTTP request can carry sensitive data in multiple places:

```text
Request line / URI:
  /api/accounts/123?access_token=...&email=...

Headers:
  Authorization, Cookie, X-API-Key, X-Auth-Token, X-Tenant-Id

Body:
  username/password, OTP, payment details, personal data, free text

Response:
  Set-Cookie, Location, account profile, error details, tokens
```

**Masking a single header is not enough** when the same data appears in query strings, JSON payloads, responses, or loggers at other layers.

### 5.1. Categories of Data to Avoid Logging

| Category | Examples | Risk |
| --- | --- | --- |
| Bearer/API credentials | `Authorization`, `X-API-Key` | API hijacking while token remains valid |
| Session credentials | `Cookie`, `Set-Cookie` | Session hijacking |
| Personal data | Email, phone, address, national ID | Privacy and compliance violations |
| Payment data | Card numbers, payment tokens, billing details | Expands sensitive-data scope in logs |
| Authentication factors | Passwords, reset tokens, OTPs | Account takeover |
| Healthcare/financial payloads | Medical records, bank accounts | Strictly regulated high-sensitivity data |
| User-generated text/files | Chat messages, uploaded documents | May contain unexpected secrets |
| Internal topology | `Host`, `Forwarded`, backend URIs, private IPs | Reconnaissance of internal architecture |
| Business secrets | Partner contract fields, pricing, access policies | Organizational data leakage |

These header names are illustrative only. Services can also use custom headers like `X-Partner-Token`, `X-Company-Secret`, or unpredictable body field names.

### 5.2. Post-Wiretap Masking Is Not Fully Reliable

Suppose a logging appender applies a regex:

```text
Authorization: .*  →  Authorization: [REDACTED]
```

That can still fail because:

- Wiretap may default to **`HEX_DUMP`** rather than plaintext.
- JSON bodies may use Unicode escapes, line breaks, or split across chunks.
- HTTP/2 headers may not render as single-line HTTP/1.1 strings.
- Secrets also live in `Cookie`, query strings, `Set-Cookie`, and multipart/binary payloads.
- Another appender, stderr, container log driver, or APM agent may capture the **raw record** before regex masking runs.
- Log formats or logger names can change during library upgrades.

**The best defense is not capturing secret payloads at all.** On live traffic, keep content wiretap off and rely on metadata-level allowlisted telemetry. Redaction is defense in depth, never permission to log raw payloads.

### 5.3. TLS Does Not Protect Content Already Written to Logs

TLS encrypts data **in transit between two TLS endpoints**. A Gateway often terminates inbound TLS and opens a separate outbound TLS leg:

```text
Browser ── TLS 1 ──▶ Gateway ── TLS 2 ──▶ Backend
```

The application still operates on the **plaintext HTTP representation** to match routes, authenticate, rewrite headers/bodies, and proxy. Depending on pipeline placement, Reactor Netty wiretap sees HTTP plaintext before outbound encryption or after inbound decryption.

**Never reason:** “HTTPS is encrypted, so wiretap only logs ciphertext with no PII.” Nor does using `wss://` or HTTP/2 make secret headers vanish from observability layers.

### 5.4. Bodies Can Be Logged Multiple Times Across Two Hops

A single `POST /api/payments` can produce:

```text
Server READ:  original request
Client WRITE: outbound request
Client READ:  backend response
Server WRITE: final response
```

If `Retry` performs additional attempts, client WRITE/READ events appear **multiple times** for one inbound request—multiplying secret storage and exposure risk with every attempt.

Gateway body transforms can also create **two distinct PII-bearing representations**. Even if an application filter strips a field before sending upstream, server-side wiretap **still recorded it on the original inbound read**.

## 6. Priority Rule: Metrics and Tracing First, Wiretap Last

A Gateway needs three primary observability pillars:

1. **Metrics** to spot error rates, latency, traffic shifts, and saturation.
2. **Traces** to follow a single request across the Gateway and microservices.
3. **Structured logs / allowlisted metadata** to explain events with non-secret context.

Wiretap is the **fourth tool**, reserved for comparing byte-level behavior on connections inside a controlled environment.

### 6.1. Spring Cloud Gateway Metrics

In Server WebFlux, Gateway integrates with **Spring Boot Actuator/Micrometer** when enabled on matching release trains. Current config-table properties:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          metrics:
            enabled: true
            path-tags:
              enabled: false
```

The goal is observing requests across **low-cardinality dimensions** such as:

```text
routeId
httpMethod
status/outcome
```

Gateway documentation describes the `spring.cloud.gateway.requests` timer metric with version-dependent tags like `routeId`, `routeUri`, `outcome`, `status`, `httpStatusCode`, and `httpMethod`. Inspect `/actuator/metrics` on your live app when running newer Spring Boot/Micrometer versions, because metric names, properties, and labels can differ.

**Never turn on raw path tags casually.** If `path` includes IDs, emails, or caller-controlled URLs, time-series counts explode and leak sensitive data into metrics. Keeping `path-tags.enabled: false` by default in newer configs is a prudent safeguard.

### 6.2. Access Logs Differ from Wiretap

Reactor Netty's `HttpServer` has its own **access logging**. Spring Cloud Gateway docs specify the JVM system property:

```text
-Dreactor.netty.http.server.accessLogEnabled=true
```

This is a **Java system property**, not a regular `spring.*` property. You can route the Logback logger:

```text
reactor.netty.http.server.AccessLog
```

to a dedicated appender with appropriate retention and access controls. Access logs record concise request summaries, **not raw header/body dumps like wiretap**.

Still, default access logs can include **full request URIs, query strings, IPs, path IDs, or Referers**; never assume “access logs are always safe” without checking actual formats and URL sanitization policies.

### 6.3. Tracing: Following Requests Across Microservices

When Micrometer Tracing/OpenTelemetry is wired across the system:

```text
Client
  → Gateway span
  → Order Service span
  → Payment Service span
```

trace/span IDs pinpoint which request suffered errors or latency **without logging bodies or tokens**.

**Traces are not automatically harmless either.** Never attach JWTs, cookies, raw queries, account IDs, or full request/response bodies as span attributes or baggage. Handle trace context like `traceparent` per protocol and trust policy; a caller-supplied trace ID is never a credential or authorization proof.

### 6.4. When Are Metrics and Tracing Not Enough?

You might see:

```text
routeId=orders-v1
status=502
latency=150ms
upstream=order-service
```

and still not know whether the rewritten URI path is right. At that point:

1. Inspect loaded route definitions and filters.
2. Check a backend echo stub or structured metadata logs using path templates.
3. Add targeted, non-sensitive diagnostic logs around the suspect route/filter.
4. **Only as a last resort**, enable wiretap on **synthetic traffic in a lab/repro pod** to inspect raw HTTP bytes.

## 7. A Safer Logging Pattern: Record Selected Metadata Only

A `GlobalFilter` can log **`routeId`, HTTP method, status, and elapsed time** without reading request/response bodies or logging credentials. Example using the Gateway **Server WebFlux** API:

```java
package com.example.gateway.observability;

import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import static org.springframework.cloud.gateway.support.ServerWebExchangeUtils
    .GATEWAY_ROUTE_ATTR;

@Component
public class SafeGatewaySummaryFilter implements GlobalFilter, Ordered {

    private static final Logger log =
        LoggerFactory.getLogger(SafeGatewaySummaryFilter.class);

    @Override
    public int getOrder() {
        return -1;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            GatewayFilterChain chain) {

        long started = System.nanoTime();
        Route route = exchange.getAttribute(GATEWAY_ROUTE_ATTR);
        String routeId = route == null ? "unknown" : route.getId();
        String method = exchange.getRequest().getMethod().name();

        return chain.filter(exchange)
            .doFinally(signal -> {
                HttpStatusCode status =
                    exchange.getResponse().getStatusCode();
                String statusText =
                    status == null ? "uncommitted"
                                   : Integer.toString(status.value());

                long millis = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started
                );

                log.info(
                    "gateway routeId={} method={} status={} " +
                    "elapsedMs={} signal={}",
                    routeId,
                    method,
                    statusText,
                    millis,
                    signal
                );
            });
    }
}
```

**Safety highlights of this example:**

- Never calls `getBody()` or buffers JSON/`DataBuffer`s.
- Never logs `Authorization`, `Cookie`, `X-API-Key`, query strings, or form fields.
- Never logs raw paths that might contain `/customers/{customerId}`.
- `routeId` is controlled by route config; if external tenants can create routes, still enforce length, cardinality, and ID policies.
- `doFinally` observes cancellation and error signals, though it **does not classify exact network causes automatically**.
- On uncommitted response branches, status may be null; the example logs `"uncommitted"` instead of guessing `200`.

**Limitation:** a Gateway `GlobalFilter` runs for requests entering the **Gateway filtering chain**; it does not cover requests rejected by Spring Security/`WebFilter`s before route matching, or Actuator endpoints. Security `401/403`s and route-miss `404`s need metrics/observability at the proper web layer.

### 7.1. Prevent Log Injection from Untrusted Values

Even structured logs can hit:

```text
X-Request-Id: attacker-controlled
```

if an unchecked header is logged verbatim. Headers can be oversized, carry control characters, or break log explorers/indexes. For request correlation:

- Prefer trace IDs generated by instrumentation.
- If accepting a client correlation header, validate grammar and length.
- Never make raw message contents or exception bodies mandatory fields.
- Bound cardinality if any value enters metrics.

Never push **user IDs** or **tenant IDs** into unbounded global metric labels just to make request lookup easier; access-controlled traces and logs are built for that.

### 7.2. If You Only Need to Debug Filter Ordering

Instead of full-payload wiretap, log:

```text
routeId=orders-v1
filter=RewritePath
phase=pre
outcome=applied
```

or a normalized event naming the chosen upstream service. Avoid printing raw authorization headers, full URLs with queries, or complete request headers. If you must verify which header names were added or removed, log **allowlisted names**, never values.

## 8. Controlled Procedure for Temporarily Enabling Wiretap

Never treat wiretap as “enable and forget.” A safe workflow follows:

```mermaid
flowchart TD
    A["Incident / diagnostic question"]
    B{"Are metrics, traces, and safe logs enough?"}
    C["Keep wiretap off<br/>resolve from metadata"]
    D["Approve goal & scope"]
    E["Spin up test pod/namespace<br/>synthetic traffic only"]
    F["Enable targeted httpserver or httpclient<br/>with controlled DEBUG logger"]
    G["Send synthetic requests and capture evidence"]
    H["Disable wiretap and confirm logs stop"]
    I["Purge unnecessary records<br/>close incident/audit"]
    A --> B
    B -->|"Yes"| C
    B -->|"No"| D --> E --> F --> G --> H --> I
```

### 8.1. Before Enabling

Define:

1. **Testable hypothesis:** did `/api/orders/42` get rewritten to `/42`? Or was `X-Gateway-Source` overwritten?
2. **Exact HTTP hop:** do you need server-side or client-side? Never enable both if one suffices.
3. **Traffic isolation:** the test pod must **not receive production requests carrying real user data**.
4. **Synthetic data:** fake JWTs/cookies, fake user data, fake backends, and fixed test requests.
5. **Log destination:** do not ship raw wiretap output into central production observability stores.
6. **Authorized access:** restricted strictly to approved incident responders, with auditing.
7. **Expiration:** assign an owner, shutoff schedule, and shutoff verification steps.
8. **Rollback:** know how to redeploy the standard profile and recycle pods/instances.

Never expose a caller-supplied `?debug=true` query parameter to trigger raw body logging; that creates an easily abused data-exfiltration hole.

### 8.2. Running Against Fake Traffic

A safe local test:

```bash
curl --http1.1 -i \
  "http://localhost:8080/api/orders/42?debugCase=lab-001" \
  -H "Authorization: Bearer FAKE_TEST_TOKEN" \
  -H "Cookie: SESSION=FAKE_TEST_COOKIE" \
  -H "X-Test-Run: lab-001"
```

Values prefixed with `FAKE_` are **inert test strings**. Point to a backend stub that processes no real transactions—never hit real user accounts or live payment endpoints just to debug.

If verifying a request body:

```bash
curl --http1.1 -i -X POST \
  "http://localhost:8080/api/demo-echo" \
  -H "Content-Type: application/json" \
  --data '{"customer":"synthetic-user","cardToken":"FAKE_TEST_ONLY"}'
```

Enable body wiretap only when the **entire path** sits inside a test environment. Having a synthetic demo body does not make things safe if the same Gateway pod serves real user requests while DEBUG is active.

### 8.3. After Collecting Evidence

- Disable wiretap flags and DEBUG loggers via approved configuration/deployment.
- Verify new HTTP connections no longer emit content wiretap logs.
- Revoke temporary access and tear down the test pod or restore standard config.
- Record the incident/probe ID and diagnostic findings.
- Triage captured logs and **purge per retention policy**, covering local files, container stdout, sidecar/agent buffers, central indexes, and backups as feasible.
- If **real credentials** were accidentally captured, treat it as a **credential exposure**: notify the security team and revoke/rotate impacted secrets rather than merely deleting a local file.

**Turning off the logger does not delete records already shipped to a log aggregator.** That is a common reason a “2-minute debug session” leaves secrets lingering for weeks.

## 9. Why Never Enable Wiretap Across All Production Traffic?

### 9.1. Data Exposure

When a Gateway receives:

```http
POST /api/login
Content-Type: application/json

{"username":"user@example.test","password":"FAKE_ONLY"}
```

wiretap records the inbound body on **server `READ`** even if Gateway filters strip that field **before HTTP client `WRITE`**. With real production tokens or passwords, anyone or anything with log-read access can read them.

### 9.2. Massive Log Volume

An illustrative calculation:

```text
1,000 HTTP requests/second
× 2 hops (server + client)
× 2 directions (request + response)
= roughly 4,000 I/O directions observed/second
```

In practice, chunked `READ`/`WRITE` buffers, connection events, retries, HTTP/2 frames, and multi-line hex/ASCII dumps multiply output further—log lines and byte counts are **far larger** than 4× request count.

For a 10 KiB request body, a hex dump adds hex digits, offsets, and an ASCII column, inflating text log volume well beyond the original HTTP bytes.

### 9.3. Performance and Backpressure

Heavy logging drives up CPU, allocations, string formatting, disk/network I/O, and collector load. Synchronous/blocking appenders can stall the Reactor Netty event loop; async appenders can fill queues, drop logs, or pressure memory.

**Never use logging as a primary data plane** for thousands of requests per second. Sampled metrics and tracing with low-cardinality tags are built for 24/7 monitoring.

### 9.4. Operational Cost

With wiretap enabled:

- Log indexing, search, and storage costs spike.
- Noise obscures real 5xx signals across services.
- Compliance scope (PCI/HIPAA/GDPR) may expand to cover the entire log store.
- Retention policies get complicated because backups continue holding secrets.
- Users with log-read permissions gain access to **data meant strictly for application/backend boundaries**.

Security and governance costs quickly outweigh a single debugging convenience.

## 10. Log Masking: The Right Strategy Is Reducing Collection

Safe observability uses defense in depth:

```text
Layer 1 — Never capture bodies or credentials by default
Layer 2 — Allowlist only essential metadata
Layer 3 — Redact secrets at the log emission source
Layer 4 — Redact/suppress at collectors where appropriate
Layer 5 — RBAC, encryption, retention, auditing, deletion
Layer 6 — Automated tests using synthetic secrets
```

**Layer 1 is the most important.** Never rely solely on a regex at the end of the pipeline.

### 10.1. Allowlisting Instead of Blacklisting

Safe summary log:

```json
{
  "routeId": "orders-api",
  "httpMethod": "GET",
  "httpStatus": 502,
  "durationMs": 184,
  "upstreamService": "order-service",
  "outcome": "connect-error",
  "traceId": "synthetic-trace-id"
}
```

Unnecessary and risky:

```json
{
  "authorization": "Bearer ...",
  "cookie": "...",
  "requestBody": "...",
  "responseBody": "...",
  "requestUri": "/api/orders/42?access_token=..."
}
```

**Note:** `upstreamService` is a controlled logical service ID, never a URL carrying credentials or query parameters. `traceId` should come from tracing instrumentation rather than copying arbitrary strings from clients.

### 10.2. Do Not Log Raw Exception Messages at Every Layer

An exception message might read:

```text
Failed call https://service.example/path?token=...
```

Sending raw `exception.getMessage()` straight to alerts or dashboards leaks secret URLs even with wiretap off. Classify instead:

```text
errorCategory=connect-timeout
upstreamService=order-service
status=502
```

and keep redacted stack traces restricted to a protected log channel for deeper triage.

### 10.3. Do Not Store the Whole Body Just to “Mask One Field”

For example:

```json
{
  "user": {
    "email": "person@example.test",
    "credentials": {
      "password": "FAKE",
      "otp": "FAKE"
    }
  },
  "notes": "free text that can contain arbitrary data"
}
```

Stripping only a top-level `password` misses nested credentials, emails, OTPs, and free-text fields. Systems handling sensitive data should **never log full JSON bodies**. When business auditing is mandatory, use an **allowlisted schema**, size caps, and a separate audit store with dedicated permissions and retention.

## 11. Diagnosing Path Rewrite and Header Differences with Fake Data

Suppose the Gateway route is:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders
              uri: http://localhost:9001
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
                - SetRequestHeader=X-Gateway-Source, orders-edge
```

Client sends:

```http
GET /api/orders/42 HTTP/1.1
X-Gateway-Source: forged-client-value
```

Expected upstream request:

```http
GET /orders/42 HTTP/1.1
X-Gateway-Source: orders-edge
```

### 11.1. Observation Point A — Before Gateway Filters

Server wiretap (lab) shows:

```text
Server READ:
  GET /api/orders/42
  X-Gateway-Source: forged-client-value
```

This shows the inbound request path and header, **not yet proving** the route matched or filters ran.

### 11.2. Observation Point B — After Gateway Filters

Client wiretap (lab) shows:

```text
Client WRITE:
  GET /orders/42
  X-Gateway-Source: orders-edge
```

This proves the outbound request carries the rewritten path and header, though **does not prove the backend processed the business request cleanly**—the backend may still return 404 or 500 afterward.

### 11.3. Diagnosing Without Wiretap

In most cases, a backend echo stub is better:

```text
method = GET
path = /orders/42
X-Gateway-Source = orders-edge
```

The stub uses **fake data only** and lets you assert the exact request sent by the Gateway—carrying far lower risk than logging live traffic in production.

### 11.4. Unmatched Routes or Security Blocks

If `Path` fails to match, Gateway issues no outbound HTTP request. If Spring Security rejects before routing, you will also see **server `READ`/`WRITE`** with **no client `WRITE`**.

Absence of client wiretap does not always mean the HTTP client failed; the route may not have matched, or a filter short-circuited, served a cache hit, or returned an internal fallback. Use response statuses, route matching logs, and metrics to determine which path ran.

## 12. How `Retry`, `CircuitBreaker`, and `LoadBalancer` Change Log Interpretation

One incoming request does not always equal one outbound request.

```mermaid
flowchart TD
    IN["Single client request"]
    ROUTE["Gateway route"]
    RETRY["Retry filter"]
    A["Upstream attempt #1"]
    B["Upstream attempt #2"]
    C["Upstream attempt #3"]
    OUT["Gateway final response"]
    IN --> ROUTE --> RETRY
    RETRY --> A
    A -->|"retryable failure"| B
    B -->|"retryable failure"| C
    C --> OUT
```

### 12.1. Log Counts Across Attempts

Example:

```text
HttpServer READ      : 1 inbound request
HttpClient WRITE     : attempt 1
HttpClient READ/ERROR: attempt 1 fails
HttpClient WRITE     : attempt 2
HttpClient READ      : attempt 2 gets 503
HttpClient WRITE     : attempt 3
HttpClient READ      : attempt 3 gets 200
HttpServer WRITE     : 1 final client response
```

This is a conceptual sequence, not a claim that every attempt emits exactly one `READ`/`WRITE` log event. Chunked bodies, connection reuse, timeouts, handshakes, and client aborts can produce more or fewer events.

### 12.2. Do Not Conclude “Gateway Sent the Request Three Times” from Three `WRITE` Lines

A single HTTP request body can span multiple buffer writes, and connections get reused. Conversely, a request failing before send may have no completed write. To measure **attempt count**, rely on:

- Per-route retry metrics/counters.
- Tracing spans for outbound attempts where supported by instrumentation.
- Backend stub request counters.
- Application idempotency audits.

Never simply count `WRITE` log lines.

### 12.3. `CircuitBreaker` Can Short-Circuit

When a circuit is OPEN, requests **do not go upstream**, and the client receives a fallback/status straight from the Gateway. Thus:

```text
Server READ: present
Client WRITE: likely absent
Server WRITE: present
```

Missing client wiretap is not necessarily a bug. Check circuit breaker state, fallback metrics, and the route filter chain.

### 12.4. `LoadBalancer` Can Pick Different Instances

`lb://order-service` is a logical URI. The Netty client connects to the resolved physical instance (e.g., a pod IP). Wiretap can expose **private network topology**, so protect log destinations accordingly.

Never place backend `IP:port` values into broad metric labels or general dashboards unnecessarily; use logical route/service IDs for overview charts.

## 13. TLS and Failure Modes You Can Diagnose Without Body Dumps

TLS failures occur before a complete HTTP exchange at a hop or during connection setup.

### 13.1. Inbound TLS

```text
Client ── TLS handshake ──▶ Gateway HttpServer
```

Failures:

- Expired server cert or mismatched SAN.
- TLS version or cipher mismatch.
- SNI not matching the selected certificate.
- Untrusted or missing client mTLS certificate when required.

Diagnose via certificate inspection, handshake error categories, and network/TLS metrics. **You do not need HTTP body wiretap** to explain a `certificate_unknown` error.

### 13.2. Outbound TLS

```text
Gateway HttpClient ── TLS handshake ──▶ Upstream
```

Failures:

- Gateway does not trust the backend's CA.
- Backend hostname fails SAN verification.
- Proxy/SNI/ALPN incompatibility.
- Backend port unreachable.

Never “fix” errors in production with:

```yaml
use-insecure-trust-manager: true
```

Depending on Gateway version, the full property is `spring.cloud.gateway.server.webflux.httpclient.ssl.use-insecure-trust-manager` with default `false`; **turning on an insecure trust manager is not an observability technique**.

### 13.3. HTTPS Does Not Make Logs Safe

Even when both TLS legs are valid, each Netty HTTP stack still handles plaintext at the application boundary. Wiretap is never a ciphertext-only log stream. **Transport security and stored-log security are two separate layers.**

## 14. Comparing Wiretap, HTTP Access Logs, Metrics, Traces, and Audits

| Mechanism | Purpose | Typical Contents | Main Risks | Long-Term Use? |
| --- | --- | --- | --- | --- |
| **Wiretap** | Debug HTTP I/O at buffer/channel level | I/O events, headers, bodies (format-dependent) | Secret/PII leaks, huge log volume | **No** on live traffic |
| **Access log** | Who called what endpoint, status/bytes/latency | Method, URI, peer address, status | PII in URIs/queries, client IPs | Yes, with safe format and retention |
| **Structured app log** | Business/technical events | `routeId`, outcome, error category | Over-logging user input/exceptions | Yes, with allowlisting |
| **Metrics** | Rates, errors, latency, saturation | Numeric series + labels | High cardinality, label data leaks | Yes |
| **Distributed tracing** | Latency breakdown and call graphs | Trace/span IDs, attributes | Secrets in baggage/span tags | Yes, with privacy policy and sampling |
| **Audit log** | Non-repudiable action records | Actor/action/resource/outcome | Sensitive identities/decisions | Yes, in access-controlled storage |

### 14.1. Access Logs Are Not Audit Logs

A line reading:

```text
GET /api/admin/routes 200
```

does not prove who was authorized to change routes, who approved the revision, or what the before/after state was. For Gateway admin auditing, use a dedicated audit schema with trusted authorization context—never substitute full HTTP body wiretap for business audit trails.

### 14.2. Metrics Do Not Replace Request Replay

Metrics reveal rising p99 and 503 counts without storing raw payloads for transaction replay. That is a **data-protection feature**, not a gap you should “fix” by logging raw bodies. To reproduce bugs, build **synthetic test cases** in staging.

### 14.3. Traces Also Require Retention and RBAC

Trace IDs cross service boundaries. While not secrets on their own, traces can reveal internal service topology, endpoint names, and timing. Attach only essential attributes—never put passwords, tokens, or raw requests/responses into spans as a substitute for wiretap.

## 15. Test Environment and Practical Verification Workflow

Set up a Gateway **lab pod** and a backend echo service on `localhost:9001` or in an isolated namespace.

### 15.1. Sample Route

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: echo-lab
              uri: http://localhost:9001
              predicates:
                - Path=/lab/echo/**
              filters:
                - StripPrefix=2
                - SetRequestHeader=X-Gateway-Environment, lab
```

Client:

```bash
curl --http1.1 -i \
  "http://localhost:8080/lab/echo/orders/42" \
  -H "X-Gateway-Environment: forged" \
  -H "Authorization: Bearer FAKE_TEST_TOKEN"
```

The echo backend should receive:

```text
path = /orders/42
X-Gateway-Environment = lab
```

**Note:** this test verifies path/header transformation, not bearer token collection. When enabling wiretap to learn, tokens must be **invalid dummy strings rejected by real apps**, and the test pod must never share production traffic.

### 15.2. Reading the Four Log Groups

| Observation | Expected in Test |
| --- | --- |
| Server `READ` | `GET /lab/echo/orders/42`, client's `forged` header |
| Client `WRITE` | `GET /orders/42`, header rewritten to `lab` |
| Client `READ` | Upstream echo response |
| Server `WRITE` | Final response returned to test client |

If the client receives 200 yet client wiretap is empty, check active profile/loggers/prefixes, whether the route actually used the HTTP client, exact logger name/version, and log appender filters—do not assume the Gateway never sent the request.

### 15.3. Testing Without Real Secrets

Send a test request carrying synthetic markers:

```http
Authorization: Bearer SECRET_MARKER_FAKE_001
Cookie: SESSION=SECRET_MARKER_FAKE_002
X-API-Key: SECRET_MARKER_FAKE_003
```

In **controlled lab wiretap mode**, the marker appears in the server-side dump—proving why content wiretap is **unfit for live credentials**.

After turning wiretap off, replay the synthetic request and assert:

- No raw markers appear in logs generated after shutoff.
- Safe summary metrics/logs continue emitting (`routeId`/status/latency).
- No forgotten debug mode remains active on a second pod.
- Old markers are purged from log sinks per retention policy.

**Never test by probing real secrets or running credential scanners over unauthorized customer data.** Use traceable, approved synthetic markers strictly in test environments.

## 16. Automated Testing for Logging Policies

Unit and integration tests should verify both sides: **essential telemetry works** and **logs never store sensitive data**.

### 16.1. Testing That Safe Loggers Omit Bodies and Headers

For `SafeGatewaySummaryFilter`:

```text
Given:
  request contains Authorization=FAKE_TEST_TOKEN
  request contains Cookie=FAKE_TEST_COOKIE
  request body contains "FAKE_PASSWORD"

When:
  GET/POST goes through Gateway route

Then:
  a summary event contains routeId, method, status, elapsedMs
  no log event from SafeGatewaySummaryFilter contains:
    FAKE_TEST_TOKEN
    FAKE_TEST_COOKIE
    FAKE_PASSWORD
```

Use a **test log appender** attached specifically to `SafeGatewaySummaryFilter`. Do not claim the entire platform never logs secrets just because one logger passed: Netty wiretap, `WebClient` logs, ingress, exception loggers, and APM agents can still log independently.

### 16.2. Testing Profile-Specific Configuration

Normal environment test:

```text
spring.cloud.gateway.server.webflux.httpserver.wiretap = false
spring.cloud.gateway.server.webflux.httpclient.wiretap = false
```

Diagnostic profile test:

```text
wiretap may be enabled only in isolated test context
```

Beyond property unit tests, test deployment policies blocking diagnostic profiles from running in production namespaces. Having `wiretap: false` in repo YAML does not prove env vars, ConfigMaps, or Helm overrides won't flip it on at runtime.

### 16.3. Testing for Secret Leaks Across the Log Pipeline

A staging integration test can:

1. Send synthetic markers in headers, query params, and JSON bodies.
2. Collect logs from **every sink** within test scope.
3. Verify the safe logging pipeline stores zero markers.
4. When diagnostic wiretap lab mode is enabled, confirm markers **do appear**, then isolate and purge those logs.
5. Verify collector RBAC, retention, and access audits.

Never check only application stdout if sidecars, Fluent Bit, Vector, or OpenTelemetry Collectors copy or forward raw logs elsewhere.

### 16.4. Testing That Gateway Functionality Stays Intact

After toggling diagnostic mode on and off, verify:

- Route predicates and filter chains behave identically.
- JWT validation, `RateLimiter`, `CircuitBreaker`, and `Retry` work as before.
- HTTP/1.1 and HTTP/2 clients receive valid responses.
- Inbound/outbound TLS certificate verification is unchanged.
- Logging does not add significant latency or CPU/memory saturation.
- Access logs and metrics keep expected sampling and labels.

## 17. Common Pitfalls When Enabling Wiretap

### 17.1. `wiretap: true` Set, Yet No Logs Appear

Possible causes:

- Corresponding Reactor Netty logger is not set to DEBUG/TRACE.
- Wrong property prefix (`spring.cloud.gateway.*` vs. newer `server.webflux.*`).
- Running Gateway Server Web MVC, which does not use Netty `HttpServer` like WebFlux.
- Request rejected by security or route matching so **no outbound client exchange occurred**.
- Logging appender, filter, or sampling dropped the lines.
- Flag changed at runtime after Netty client/server instances were already constructed.

**Resolution:** verify version/configprops, logger names, route behavior, and send a synthetic request to a lab pod. Never crank `logging.level.reactor.netty=TRACE` up in production just to “see what shows up.”

### 17.2. Seeing Inbound Requests Only, No Upstream Logs

**Likely cause:** `httpserver.wiretap` is enabled without `httpclient.wiretap`; or no outbound HTTP call ran due to 401/403/404, an OPEN circuit, cache hit, or fallback.

**Resolution:** check both configuration and the route/filter chain. Backend stubs and traces quickly tell them apart.

### 17.3. Seeing Server `READ`/`WRITE` Without `routeId`

Netty connection logging is not route-level tracing. HTTP server wiretap operates in the network pipeline before or outside route selection; it does not know `routeId`.

**Resolution:** use Gateway metrics, traces, or structured route summaries. Never treat a connection ID as a `routeId`.

### 17.4. One Request Appears Multiple Times in Client Logs

**Likely causes:** `Retry` attempts, chunked HTTP bodies, client-followed redirects per policy, multiple proxy hops, or connection reuse.

**Resolution:** count attempts via retry metrics or backend stubs—never count `WRITE` log lines as transaction counts.

### 17.5. Logs Show Hex Strings with Unreadable Payloads

That is likely the default **`HEX_DUMP`** formatter. Hex encodes raw bytes verbatim and is never masking. Analyze bytes in a lab with fake data; never switch production to `TEXTUAL` just to “make it easier to read.”

### 17.6. Wiretap Still Leaks `Authorization` Despite `RemoveRequestHeader`

**Likely cause:** server-side wiretap sees the **original client header** before Gateway filters remove it, or another logger records headers at a different layer.

**Resolution:** never run content wiretap on real traffic. `RemoveRequestHeader` controls **forwarding**, not redaction of bytes already read by the Gateway.

### 17.7. Gateway or Log Collector CPU/Disk Spikes

**Likely causes:** dumping too many buffers, `HEX_DUMP` inflation, blocking I/O appenders, async queue backlogs, or retry loops.

**Resolution:** turn off diagnostic wiretap, clean up logs, monitor disk/memory/CPU, and rely on metrics/traces for continuous monitoring.

### 17.8. DEBUG Turned Off, Yet Secrets Still Turn Up in Log Searches

Logs emitted prior to shutoff may already reside in:

```text
container stdout
node log files
sidecar buffers
collector queues
central index
long-term archive / backups
```

**Resolution:** scope the exposure, trigger incident response, purge per policy, and rotate/revoke any captured credentials; disabling logging **never recalls already-written secrets**.

### 17.9. Wiretap Over HTTPS Still Logs Readable JSON

This matches the rule that **TLS protects transit, not endpoint logs**. If exposure occurred, halt diagnostics and respond as a security incident immediately—never try to “fix” it by tweaking TLS ciphers or assuming HTTPS makes logs safe.

### 17.10. `/actuator/loggers` Left Publicly Exposed

If an unauthorized actor can change log levels while wiretap is enabled in the app, they can trigger massive leaks of sensitive data. Lock down Actuator management APIs, restrict `loggers`, control write access, require TLS, isolate networks, and audit access.

## 18. Pre-Deployment and Pre-Investigation Checklist

| Item | Question |
| --- | --- |
| **Runtime** | Running the exact right Gateway Server WebFlux / Reactor Netty version? |
| **Namespace** | Using `server.webflux.httpserver/httpclient.wiretap` vs. legacy `gateway.httpserver/httpclient.wiretap`? |
| **Defaults** | Are both wiretap flags `false` in production? |
| **Loggers** | Are `reactor.netty.http.server.HttpServer` and `.http.client.HttpClient` at INFO/WARN outside debugging? |
| **Scope** | Do you genuinely need server-side, client-side, or both? |
| **Goal** | Have you written down a specific hypothesis to test? |
| **Traffic** | Strictly synthetic traffic, with zero production credentials/payloads hitting the diagnostic pod? |
| **Formatter** | Aware that `HEX_DUMP`/`TEXTUAL` log content and `SIMPLE` still logs metadata? |
| **TLS** | Not assuming HTTPS hides data from wiretap loggers? |
| **Auth headers** | Never logging `Authorization`, `Cookie`, API keys, or `Set-Cookie`? |
| **Body/query** | Never logging PII-bearing JSON, multipart forms, or tokens in URLs? |
| **Filter chain** | Not substituting wiretap for route-level metrics/tracing? |
| **Resilience** | Aware retries multiply outbound attempts and log copies? |
| **Log pipeline** | Accounted for files, stdout, agents, collectors, indexes, and archives? |
| **RBAC** | Only approved responders can read diagnostic logs and access management controls? |
| **Retention** | Defined TTL, cleanup, auditing, and accidental-exposure runbook? |
| **Overhead** | Monitoring CPU, GC, memory, disk, and log queues? |
| **Clean shutoff** | Verified flags/logger levels and all instances reverted to normal mode? |
| **Alternatives** | Could metrics, tracing, access logs, or metadata filters solve the question instead? |
| **Tests** | Tested path/header rewrites, leak markers, security rejections, retries, and TLS? |

## 19. Practice Scenarios with Answers

### Scenario A: 404 After Rewrite

Gateway route:

```yaml
filters:
  - StripPrefix=2
```

Client calls:

```text
GET /api/orders/42
```

Backend only exposes:

```text
GET /orders/42
```

**Question:** should you enable full production wiretap to find the bug?

**Answer:** no. Calculate ahead of time that `StripPrefix=2` strips down to `/42`, verify route config and backend echo in staging, and if needed, use client-side wiretap **only on fake test requests in a lab** to confirm the outbound path.

### Scenario B: Missing `Authorization`

Client sends:

```http
Authorization: Bearer FAKE_TEST_TOKEN
```

Yet the backend returns 401.

**Question:** is server/client wiretap the first step to see where the token went?

**Answer:** no. Check Spring Security/`TokenRelay` policy first, log only auth outcome/scope categories, and test with a backend stub **without real tokens**. If checking header presence, log `authorizationPresent=true/false` in a controlled scope—**never log the token value**.

### Scenario C: HTTPS and Hex Dumps

The Gateway speaks `wss://` or `https://` to upstream. An operator claims “wiretap logs hex, so the token is encrypted.”

**Answer:** false. Hex is simply a **byte representation** that decodes back trivially; Netty logging in the application pipeline sees HTTP plaintext before encryption or after decryption. TLS never prevents data from being written to Gateway logs.

### Scenario D: One GET, Three Client `WRITE`s

There is one inbound GET yet three groups of HTTP client writes.

**Answer:** you cannot conclude three upstream attempts from log line counts alone; bodies may be chunked, retried, or interleaved with connection events. Use retry metrics, traces, and backend stubs to count actual requests.

### Scenario E: No Logs After `logging.level...=DEBUG`

**Answer:** `httpserver.wiretap`/`httpclient.wiretap` may still be `false`, the namespace may be wrong, or requests never reached an outbound call. The debug logger and the wiretap handler are two separate prerequisites.

### Scenario F: Wanting to Log Every JSON Response to Debug 503s

**Answer:** avoid doing so. Check error rates/statuses/route IDs, classify Netty connection errors, and inspect circuit states and service health first. If response bodies must be inspected, return **fake JSON from a backend stub** rather than dumping live customer data.

### Scenario G: Real Token Accidentally Stored in Log Collector

**Answer:** this is a **data security incident**, not just a logging bug. Stop collection, identify sinks/scope, notify security, rotate/revoke affected credentials, purge retention/indexes/backups per policy, and audit access.

### Scenario H: Needing Only Total 502/503 Counts by Route

**Answer:** use **Gateway/Micrometer metrics** with `routeId`, status/outcome, and latency—no wiretap needed.

## 20. Self-Check Questions

1. **Which direction does server `READ` describe?**  
   Gateway receiving bytes from the client/ingress at Netty `HttpServer`.

2. **Which direction does client `WRITE` describe?**  
   Gateway sending bytes upstream through Netty `HttpClient`.

3. **Do client `READ` and server `WRITE` always carry identical data?**  
   No; they can observe different representations of the response because Gateway response filters can alter headers, bodies, or status codes.

4. **Is setting the logger to DEBUG with the wiretap flag `false` enough?**  
   No. Both the Netty wiretap handler and the appropriate log level are needed.

5. **What are the defaults in newer Gateway config tables?**  
   `server.webflux.httpserver.wiretap=false` and `server.webflux.httpclient.wiretap=false`.

6. **Is a `HEX_DUMP` field encrypted and safe to share?**  
   No. It contains raw HTTP bytes that can be decoded right back.

7. **Is `SIMPLE` guaranteed to contain zero sensitive operational data?**  
   No. It can still expose remote IPs/ports, byte counts, timing, or coexist with other loggers.

8. **Does TLS guarantee wiretap never sees HTTP payloads?**  
   No. Depending on Netty handler placement and runtime, plaintext before/after TLS processing can be logged.

9. **Can you count HTTP requests by counting `WRITE` log lines?**  
   No. Chunking, connection reuse, multiplexing, and retries distort line counts.

10. **Why is masking only `Authorization` insufficient?**  
    Secrets also appear in `Cookie`, `Set-Cookie`, query strings, request/response bodies, custom API-key headers, and hex dumps.

11. **Why can retries multiply log output?**  
    One inbound request can trigger multiple outbound HTTP attempts.

12. **What should you use when you only need route latency?**  
    Micrometer metrics/tracing with low-cardinality tags.

13. **Are access logs completely safe?**  
    No; URIs, query strings, and client IPs can carry PII and require format/retention policies.

14. **When wiretap is turned off, do old logs disappear automatically?**  
    No. Log aggregators, files, and backups can still hold copies.

15. **Why secure `/actuator/loggers`?**  
    To prevent unauthorized log-level changes that expose data when diagnostics are enabled or overload log sinks.

16. **When is content wiretap acceptable?**  
    Only when genuinely needed, approved, restricted to fake test traffic in an isolated environment, with TTL, rollback, and controlled log sinks.

## 21. Official Reference Documentation

- [Spring Cloud Gateway Server WebFlux — Troubleshooting / Wiretap](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/troubleshooting.html): logger levels and `HttpClient`/`HttpServer` wiretap description.
- [Spring Cloud Gateway — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html): `spring.cloud.gateway.server.webflux.httpclient.wiretap`, `httpserver.wiretap`, and metrics properties.
- [Spring Cloud Gateway Server WebFlux — Global Filters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html): Gateway metrics, route-level observability, and filter lifecycle.
- [Spring Cloud Gateway Server WebFlux — Reactor Netty Access Logs](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/reactor-netty-access-logs.html): enabling access logs via JVM system property and isolating logger/appender.
- [Reactor Netty — HTTP Client Reference](https://projectreactor.io/docs/netty/release/reference/http-client.html) and [HTTP Server Reference](https://projectreactor.io/docs/netty/release/reference/http-server.html): wire loggers, Netty client/server, and formatters.
- [Reactor Netty — `AdvancedByteBufFormat` API](https://projectreactor.io/docs/netty/release/api/reactor/netty/transport/logging/AdvancedByteBufFormat.html): `SIMPLE`, `HEX_DUMP`, and `TEXTUAL` semantics.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): Micrometer Observation, metrics/traces, and low/high-cardinality metadata.

## Summary

**Reactor Netty `HttpServer` and `HttpClient` wiretap** is a sharp tool for observing HTTP I/O on **both sides of Spring Cloud Gateway Server WebFlux**. `HttpServer` sees **client ↔ Gateway** traffic while `HttpClient` sees **Gateway ↔ upstream** traffic; `READ` and `WRITE` must always be interpreted from the logging component's perspective. In modern Gateway releases, `spring.cloud.gateway.server.webflux.httpserver.wiretap` and `.httpclient.wiretap` default to off, and DEBUG logging is a separate condition to emit output.

Even more critical is **data protection**: `HEX_DUMP` and `TEXTUAL` can log full headers and bodies, while `SIMPLE` reduces content dumps yet still requires metadata governance. **TLS never protects records already emitted inside the application.** Never enable content wiretap on real traffic as a permanent monitoring solution. Lead with **metrics, distributed tracing, access logs, and allowlisted structured metadata**, and reserve wiretap for **isolated labs with fake traffic—under explicit approval, tight scope, TTL, RBAC, log-sink isolation, rollback, and purge procedures** when deep byte-level diagnosis is truly required.
