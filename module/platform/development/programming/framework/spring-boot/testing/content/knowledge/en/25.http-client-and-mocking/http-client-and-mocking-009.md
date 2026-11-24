# Testing Propagation of Tokens, Correlation IDs, and Required Headers

A Spring Boot application can both receive HTTP requests from clients and call downstream HTTP services. When forwarding calls, the application often must propagate an **Authorization token**, a **correlation ID**, and certain **required downstream contract headers**. However, **propagation does not mean copying every header**: credentials carry specific audiences and scopes; correlation IDs are metadata that callers can forge; and proxy, cookie, and hop-by-hop headers are usually unfit for forwarding downstream. A single line like `outboundHeaders.addAll(inboundHeaders)` can send a token to the wrong host, leak session cookies, or trust a caller-spoofed tenant ID.

This lesson belongs to the **HTTP Client and Mocking** section of the **Spring Boot – testing** module. It walks through deciding which headers to propagate, generate, validate, transform, or strip; testing propagation across **controller → application context → `RestClient` → downstream**; writing positive and negative tests; and knowing when real network integration is needed over mocks. Examples use **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, JUnit Jupiter 5, `MockMvc`, `@RestClientTest`, and `MockRestServiceServer`**.

**Security boundary disclaimer:** Tokens in the examples are synthetic test tokens; demo code only checks **Bearer syntax and propagation**—it **does not** verify JWT signatures, issuers, audiences, expiry, scopes, or authorization. Never deploy this gateway sample to production without proper **Spring Security resource server/OAuth2 client** protection. When production uses token exchange or service credentials, keep propagation tests while replacing the token source with an approved security mechanism.

## 1. Learning objectives

- Distinguish **token relay**, **client credentials**, **token exchange**, **correlation IDs**, **W3C trace context**, and **HTTP header contracts**.
- Identify the exact **trust boundary** between inbound callers, gateway/application, and downstream services.
- Build per-downstream header allowlists; never propagate session cookies, proxy credentials, or caller-forged identity headers.
- Verify `Authorization: Bearer ...` headers are formatted properly without doubling `Bearer` or retaining a previous request's token.
- Verify valid correlation IDs are preserved/canonicalized, missing ones generated, and malformed ones rejected per policy.
- Verify request-specific `X-Client-Channel` and `Accept: application/json` headers on the outbound client.
- Understand the difference between **inbound `MockMvc`** and **outbound `MockRestServiceServer`**, and why neither proves network/TLS/redirect safety.
- Build a runnable Java 17+, Spring Boot 3.5 sample with a controller, policy, `RestClient`, DTO, and three test classes.
- Design negative tests for missing tokens, invalid IDs, cookie leaks, untrusted hosts, 401/429/5xx, retries, and concurrency.
- Structure tracing/MDC/async context so one user never accidentally inherits another user's correlation ID or token.
- Pick the lowest-cost test level that still observes the target risk.

## 2. Header propagation diagram

```text
Client
  |
  | GET /api/proxy/BOOK
  | Authorization: Bearer demo-user-token.123
  | X-Correlation-ID: 15cf0e17-83eb-42bc-a85f-0c70d7be1293
  | X-Client-Channel: WEB
  | Cookie: browser_session=...         <-- DO NOT relay
  | X-Forwarded-For: attacker-input     <-- DO NOT trust blindly
  v
Spring MVC / security filter chain
  |
  +-- Authenticate/authorize (production requirement)
  +-- Header policy (validate/generate correlation)
  +-- RelayContext per invocation
  v
CatalogClient / RestClient
  |
  | GET /api/catalog/BOOK
  | Authorization: Bearer demo-user-token.123   <-- only if trust/aud OK
  | X-Correlation-ID: 15cf0e17-...
  | X-Client-Channel: WEB
  | Accept: application/json
  | No Cookie / no Proxy-Authorization
  v
Trusted catalog downstream
  |
  v
Gateway response:
  | X-Correlation-ID: 15cf0e17-...
  | JSON CatalogItem body
  | No token, no downstream Set-Cookie
```

Four independent decisions: **(1) what do we accept? (2) what do we trust/validate? (3) what exactly goes downstream? (4) what headers return to the caller?** The same header name may follow different policies on request vs. response.

## 3. Token relay, delegated access, and service identity

| Mechanism | Where does the credential come from? | When is it used? | What must tests observe? |
|---|---|---|---|
| **Token relay** | Validated inbound credential suitable for downstream | User delegation permitted | Right token, audience/scope, no leakage to other hosts |
| **OAuth2 client_credentials** | Authorized client manager calls token endpoint | Service calls API under its own app identity | Client registration selection, scope, refresh/reuse |
| **Token exchange / on-behalf-of** | Exchanges inbound token for a new-audience token | Inbound token is not valid directly for API B | New audience, identity delegation, expiry, exchange failure |
| **Anonymous downstream** | No `Authorization` needed | Public endpoints | Never accidentally forward caller tokens |
| **mTLS/proof-of-possession** | Certificate/key or sender-constrained token | High-security integrations | TLS handshake, identity, not just header text |

Never read `Authorization` as "already authenticated." An HTTP request carrying `Bearer abc` may be forged or expired. With Spring Security resource server, verify tokens at ingress and **ensure downstream is allowed to receive that token**. If a user token only has `aud=api-A`, never relay it blindly to `api-B`. To act on a user's behalf at API B, use an approved delegation or token-exchange flow—never rewrite JWT claims manually.

### 3.1. RFC 6750 and Bearer grammar

For header:

```http
Authorization: Bearer mF_9.B5f-4.1JqM
```

The `Bearer` scheme is case-insensitive; RFC 6750 Bearer tokens typically consist of letters, digits, `- . _ ~ + /`, and trailing `=` padding. Spring's `HttpHeaders.setBearerAuth(token)` expects **only the token value**, not the full `Bearer ...` prefix.

Wrong:

```java
// COUNTER-EXAMPLE: easily becomes "Bearer Bearer abc".
headers.setBearerAuth("Bearer abc");
```

Right:

```java
headers.setBearerAuth("abc");
```

Never place bearer credentials in URL queries, application logs, tracing baggage, MDC, or exception messages. **Bearer tokens must travel over HTTPS** across any network.

## 4. Correlation IDs are metadata, not credentials

A correlation ID is typically a UUID logged across multiple services to trace one request flow:

```http
X-Correlation-ID: 15cf0e17-83eb-42bc-a85f-0c70d7be1293
```

Example policy:

1. Caller sends a valid UUID → normalize to lowercase.
2. Caller omits it → generate a new UUID.
3. Caller sends a malformed ID → HTTP 400, never call downstream.
4. Outbound uses **the exact resolved value**.
5. Gateway response returns **the same correlation ID** to the caller.
6. When retrying the same logical request, keep a stable logical ID if policy defines it that way.
7. IDs must contain no PII, secrets, control characters, or unbounded lengths.

Because callers can supply correlation IDs themselves, treat them as **untrusted input** before validation. They never prove user identity, tenant, permissions, or token validity. If a system must **return the ID even on errors**, the correlation filter/exception handler must assign the ID **before** the controller and attach it to error responses too; the main demo focuses on the happy path, returning 400/401 on validation failures.

### 4.1. Do not compare one random UUID against another

Counter-example:

```java
assertEquals(
        UUID.randomUUID().toString(),
        actualCorrelationId);
```

Better:

```java
String returned = response.getHeader("X-Correlation-ID");
assertEquals(returned, UUID.fromString(returned).toString());
assertEquals(returned, capturedOutboundContext.correlationId());
```

This is a snippet; `response` and `capturedOutboundContext` come from test setup rather than a standalone runnable file.

## 5. W3C Trace Context is not the same as a Correlation ID

Trace context uses:

```http
traceparent: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01
tracestate: congo=t61rcWkgMzE
```

`traceparent` carries version, trace-id, parent-id, and flags. When a service creates a child span, **the parent/span ID legitimately changes** between inbound and outbound, while the distributed `trace-id` stays continuous. Therefore:

- Never copy `traceparent` verbatim in a custom `RestClient` interceptor when using Micrometer Tracing/OpenTelemetry.
- Let the tracing propagator manage `traceparent`, `tracestate`, and baggage.
- When testing trace continuity, assert parent/child relationships across spans rather than raw `traceparent` text equality.
- Never put tokens or sensitive user data into baggage.
- `X-Correlation-ID` is a business/operational header that may coexist, with a single clear owner.

If a team uses both tracing and separate correlation IDs, document how logs are searched with each ID. Never silently generate three conflicting IDs across gateway, filter, and controller.

## 6. Header matrix: propagate, generate, filter, or drop

| Header | Recommended behavior | Why / what to test |
|---|---|---|
| `Authorization` | Relay only if token is valid and audience/scope/trust match | Security boundary |
| `X-Correlation-ID` | Validate or generate, then use consistently | Cross-service log correlation |
| `traceparent`, `tracestate` | Managed by tracing instrumentation | Parent/span semantics |
| `Accept` | Set per downstream contract | JSON GET: `application/json` |
| `Content-Type` | Set per outbound body | GET should not copy inbound `Content-Type` |
| `X-Client-Channel` | Allowlist if downstream requires it | Never trust arbitrary caller values |
| `Idempotency-Key` | Propagate only per mutation/retry contract | Prevents duplicate side effects |
| `X-API-Version` | Adapter sets per target API version | Never blindly forward caller's version |
| `Cookie` | Never relay by default | Browser sessions do not belong downstream |
| `Proxy-Authorization` | Never relay | Sensitive proxy credentials |
| `Forwarded`/`X-Forwarded-*` | Handle only across trusted proxy chains | Callers can forge them |
| `Host`, `Content-Length` | Let the HTTP client/transport set them | Each hop has its own host/body |
| `Connection`, `Transfer-Encoding` | Hop-by-hop; never copy | HTTP framing/connection-specific |
| `Origin`, `Referer` | Never forward by default | Browser/CORS context |
| Response `Set-Cookie` | Never copy automatically to caller | Cookie scope/domain leak |
| Response `Location` | Map to public API contract | May expose internal hosts |

**Every downstream needs its own explicit allowlist.** "All headers except `Cookie`" is still far too permissive. Never call `headers.addAll(inboundHeaders)` and try to blocklist a handful of fields while missing new headers introduced later.

## 7. Identity headers are easy to spoof

Headers such as `X-User-ID`, `X-Tenant-ID`, `X-Role`, or `X-Forwarded-User` sound authoritative, yet external callers can inject them freely. Reading them directly to query data can cause **privilege escalation**.

Instead of:

```java
// COUNTER-EXAMPLE: trusting caller-asserted user identity.
String tenant = servletRequest.getHeader("X-Tenant-ID");
queryInvoicesFor(tenant);
```

extract identity/tenant from the **authenticated `SecurityContext`**, or from a signed/injected header produced by a trusted gateway over a protected network where external clients cannot forge it. Tests should send spoofed tenant/role headers and verify the policy rejects or ignores them.

In the demo, `X-Client-Channel` is merely **channel metadata** for downstream metrics/formatting, not user authorization. Even `PARTNER` in the allowlist **does not** prove the caller is an authenticated partner.

## 8. Inbound and outbound response headers need distinct allowlists

When the gateway receives a downstream response:

- JSON bodies can be deserialized to DTOs and re-serialized per the public API.
- Downstream `Set-Cookie` does not belong to the gateway's cookie domain.
- Downstream `WWW-Authenticate` may expose internal realms or client IDs.
- `Location` may reveal internal hosts that should stay private.
- `Content-Length` breaks if the body is transformed.
- `X-Correlation-ID` should use the gateway-resolved ID rather than letting downstream overwrite it.

Hence the demo returns only **JSON `CatalogItem`** and `X-Correlation-ID`. Never forward `Authorization` or `Set-Cookie` back to a browser. Add negative response-header tests if the gateway ever proxies a downstream `ResponseEntity` directly.

## 9. Choose tests by boundary, not annotation name

| Test | Tool | Real TCP? | What it can catch |
|---|---|---|---|
| Pure policy | JUnit Jupiter | No | Missing token, invalid UUID, channel allowlist |
| Inbound MVC | `@WebMvcTest` + `MockMvc` | No | Header-to-context mapping, response header, 400/401, zero client calls |
| Outbound client | `@RestClientTest` + `MockRestServiceServer` | No | Exact URL/method/headers, omitted headers, token bleed |
| Wire-level HTTP | WireMock/MockWebServer | Yes | Redirects, proxies, TLS, HTTP client framing/timeouts |
| Full app | `@SpringBootTest(RANDOM_PORT)` + trusted stub | Yes | Security filters, controller, service, client, real server |
| Partner sandbox | Controlled remote endpoint | Yes | Actual identity/TLS/gateway/rate-limit contract |

`MockMvc` opens no HTTP sockets; `MockRestServiceServer` replaces the client's request factory with a mock. Never label them real network integration tests. Still, they are usually the **cheapest layer** to catch forgotten or leaked headers; add real HTTP tests wherever transport risks exist.

## 10. `@RestClientTest` and `MockRestServiceServer`

Spring Boot 3.5 supports:

```java
@RestClientTest(CatalogClient.class)
class CatalogClientHeaderTest {

    @Autowired CatalogClient client;
    @Autowired MockRestServiceServer server;
}
```

The test slice auto-configures `RestClient.Builder` and the mock REST server. The real `CatalogClient` bean builds the outbound request; when it calls `RestClient`, the mock server intercepts the request and returns the stub response.

`MockRestServiceServer` can assert:

- URL, HTTP method, query params.
- `Authorization`, `X-Correlation-ID`, channel, `Accept`.
- Absent headers via custom `RequestMatcher`.
- Request count/order and response status/body.
- If no request occurs, `server.verify()` fails.

Spring Framework notes: when verifying **real transport**, a mock web server is superior because `MockRestServiceServer` does not simulate network libraries, proxies, or redirects. Keeping those two goals separate prevents false confidence.

## 11. `RestClient` must set headers per request

A `RestClient` can be a Spring-injected singleton:

```java
@Bean
RestClient downstream(RestClient.Builder builder) {
    return builder.baseUrl("https://trusted-api.internal")
            .build();
}
```

Do not do this:

```java
// COUNTER-EXAMPLE: user A's token baked into shared singleton client.
return builder.defaultHeader(
        HttpHeaders.AUTHORIZATION, "Bearer token-user-A")
        .build();
```

If user B reuses that client, A's credential leaks onto B's request. Use the per-request spec:

```java
client.get()
        .uri("/api/items/{id}", id)
        .headers(h -> {
            h.setBearerAuth(context.accessToken());
            h.set("X-Correlation-ID", context.correlationId());
        })
        .retrieve()
        .body(Item.class);
```

This is a snippet with hypothetical `Item`/`context`. Passing context via method parameters avoids mutable singleton fields and `ThreadLocal` leaks. If tracing or OAuth2 interceptors are registered, clarify whether they overwrite these headers and test the final request.

## 12. Spring Security / OAuth2 production integration

Spring Security 6.5 provides `OAuth2ClientHttpRequestInterceptor` backed by `OAuth2AuthorizedClientManager` for `RestClient`. Example:

```java
// Snippet; requires spring-security-oauth2-client,
// OAuth2AuthorizedClientManager, and client registration.
OAuth2ClientHttpRequestInterceptor interceptor =
        new OAuth2ClientHttpRequestInterceptor(manager);

RestClient protectedClient = RestClient.builder()
        .requestInterceptor(interceptor)
        .baseUrl("https://trusted-api.internal")
        .build();
```

It can fetch tokens, reuse authorized clients, and refresh when needed; configure an appropriate principal/`clientRegistrationId` resolver, especially for `client_credentials` (app-level scope rather than per-user). Never set `Bearer` manually **and** attach an OAuth2 interceptor without a clear precedence policy and tests verifying the outgoing request.

If API A is a resource server accepting JWTs, validate **issuer, signature, expiration, audience, and scopes** via Spring Security before deciding to relay. A token issued for API A is not automatically valid for API B; token exchange or service credentials address that depending on architecture.

## 13. Runnable example: demo app requirements

- Inbound endpoint: `GET /api/proxy/{sku}`.
- Fixed downstream: `{demo.catalog.base-url}/api/catalog/{sku}`.
- Required headers: `Authorization: Bearer ...` and `X-Client-Channel` in `WEB`, `MOBILE`, `PARTNER`.
- Correlation ID: `8-4-4-4-12` UUID; preserved if valid, generated if missing.
- Outbound: Bearer, correlation ID, client channel, `Accept: application/json`.
- Outbound **must not** contain browser `Cookie`/`Proxy-Authorization`/`X-Forwarded-For`.
- Response: JSON `CatalogItem(sku, title)` and `X-Correlation-ID`, never echoing the token.
- SKU path: uppercase/digits/hyphens to prevent malformed URLs.
- Synthetic test token, host `catalog.example.test`; zero outbound network calls.

### 13.1. Source tree

```text
header-propagation-demo/
  settings.gradle
  build.gradle
  src/main/java/com/example/headerprop/
    HeaderPropagationApplication.java
    RelayContext.java
    HeaderRelayPolicy.java
    CatalogItem.java
    CatalogClient.java
    ProxyController.java
  src/test/java/com/example/headerprop/
    HeaderRelayPolicyTest.java
    ProxyControllerTest.java
    CatalogClientHeaderTest.java
```

Three test groups:

1. `HeaderRelayPolicyTest`: pure JUnit policy tests.
2. `ProxyControllerTest`: `@WebMvcTest` + Mockito mock of `CatalogClient`.
3. `CatalogClientHeaderTest`: `@RestClientTest` + `MockRestServiceServer` with real `CatalogClient`.

Files in sections 14–21 are complete; code blocks labeled "snippet" in earlier sections are not standalone runnable files.

## 14. Gradle files

**`settings.gradle`**

```groovy
rootProject.name = 'header-propagation-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` provides MVC/`RestClient`/Jackson, and `starter-test` provides JUnit/Mockito/Spring Test. No Docker, real API tokens, Redis, or OAuth server is needed to run these mocks. **This is a testing lesson on propagation**, not a reference security deployment: production must add proper security dependencies and policies.

## 15. Application and request-scoped context

**`src/main/java/com/example/headerprop/HeaderPropagationApplication.java`**

```java
package com.example.headerprop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HeaderPropagationApplication {

    public static void main(String[] args) {
        SpringApplication.run(HeaderPropagationApplication.class, args);
    }
}
```

**`src/main/java/com/example/headerprop/RelayContext.java`**

```java
package com.example.headerprop;

public record RelayContext(
        String accessToken,
        String correlationId,
        String clientChannel) {
}
```

This context is **created fresh per request**, never held in a singleton. Never log the record since its default `toString()` exposes the token. In production, wrap tokens in a redacted security-specific type or rely on an authorized-client mechanism.

## 16. Header policy: parsing and input validation

**`src/main/java/com/example/headerprop/HeaderRelayPolicy.java`**

```java
package com.example.headerprop;

import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

public final class HeaderRelayPolicy {

    private static final Pattern BEARER_TOKEN =
            Pattern.compile("^[A-Za-z0-9._~+/-]+=*$");

    private static final Pattern STRICT_UUID = Pattern.compile(
            "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-" +
            "[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" +
            "[0-9a-fA-F]{12}$");

    private static final Set<String> CHANNELS =
            Set.of("WEB", "MOBILE", "PARTNER");

    private HeaderRelayPolicy() {
    }

    public static RelayContext fromInbound(
            String authorization,
            String correlationId,
            String clientChannel) {

        String token = parseBearer(authorization);
        String correlation = normalizeCorrelation(correlationId);
        String channel = requireChannel(clientChannel);

        return new RelayContext(token, correlation, channel);
    }

    static String parseBearer(String authorization) {
        if (authorization == null
                || authorization.length() > 8192
                || !authorization.regionMatches(
                        true, 0, "Bearer ", 0, 7)) {
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED,
                    "Bearer credentials required");
        }

        String token = authorization.substring(7);
        if (token.isEmpty()
                || !BEARER_TOKEN.matcher(token).matches()) {
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED,
                    "Invalid Bearer credential format");
        }

        return token;
    }

    static String normalizeCorrelation(String incoming) {
        if (incoming == null || incoming.isBlank()) {
            return UUID.randomUUID().toString();
        }

        if (incoming.length() != 36
                || !STRICT_UUID.matcher(incoming).matches()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Invalid X-Correlation-ID");
        }

        return UUID.fromString(incoming).toString();
    }

    static String requireChannel(String incoming) {
        if (incoming == null || !CHANNELS.contains(incoming)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Invalid X-Client-Channel");
        }
        return incoming;
    }
}
```

**Exact scope:**

- The token parser validates **format only**; it **does not authenticate** real credentials.
- `Bearer` scheme is accepted case-insensitively.
- The parser intentionally requires **one ASCII space** after the scheme; RFC 6750 permits `1*SP`, so the demo is stricter than the RFC. Update parser and tests if full protocol whitespace syntax is needed.
- 8192 is an **illustrative cap** against oversized headers, not an RFC-mandated limit.
- UUIDs normalize to lowercase; invalid IDs return 400; null/blank generates a new UUID.
- `X-Client-Channel` is allowlisted metadata, **not** partner authentication.
- Raw tokens and malicious input are never echoed in error messages.

## 17. DTO and HTTP client

**`src/main/java/com/example/headerprop/CatalogItem.java`**

```java
package com.example.headerprop;

public record CatalogItem(String sku, String title) {
}
```

**`src/main/java/com/example/headerprop/CatalogClient.java`**

```java
package com.example.headerprop;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class CatalogClient {

    private final RestClient client;

    public CatalogClient(
            RestClient.Builder builder,
            @Value("${demo.catalog.base-url}") String baseUrl) {
        this.client = builder.baseUrl(baseUrl).build();
    }

    public CatalogItem fetch(String sku, RelayContext context) {
        CatalogItem item = client.get()
                .uri("/api/catalog/{sku}", sku)
                .accept(MediaType.APPLICATION_JSON)
                .headers(headers -> {
                    headers.setBearerAuth(context.accessToken());
                    headers.set(
                            "X-Correlation-ID",
                            context.correlationId());
                    headers.set(
                            "X-Client-Channel",
                            context.clientChannel());
                })
                .retrieve()
                .body(CatalogItem.class);

        if (item == null) {
            throw new IllegalStateException(
                    "Catalog returned empty JSON body");
        }
        return item;
    }
}
```

`RestClient` receives `baseUrl` from service config, **never from user input**. In tests using `http://catalog.example.test`, `MockRestServiceServer` intercepts calls inside the JVM so no TLS/network runs. In production, downstream base URLs must be trusted HTTPS origins—never arbitrary callback URLs—paired with redirect policies blocking cross-origin token leakage. `fetch` reads headers solely from `RelayContext`, having zero access to raw inbound `HttpHeaders`.

## 18. Controller inbound → outbound context

**`src/main/java/com/example/headerprop/ProxyController.java`**

```java
package com.example.headerprop;

import java.util.regex.Pattern;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/proxy")
public class ProxyController {

    private static final Pattern SKU =
            Pattern.compile("^[A-Z0-9-]{1,40}$");

    private final CatalogClient catalog;

    public ProxyController(CatalogClient catalog) {
        this.catalog = catalog;
    }

    @GetMapping(
            path = "/{sku}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<CatalogItem> get(
            @PathVariable String sku,
            @RequestHeader(
                    name = HttpHeaders.AUTHORIZATION,
                    required = false) String authorization,
            @RequestHeader(
                    name = "X-Correlation-ID",
                    required = false) String correlationId,
            @RequestHeader(
                    name = "X-Client-Channel",
                    required = false) String clientChannel) {

        if (!SKU.matcher(sku).matches()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid sku");
        }

        RelayContext context = HeaderRelayPolicy.fromInbound(
                authorization, correlationId, clientChannel);

        CatalogItem item = catalog.fetch(sku, context);

        return ResponseEntity.ok()
                .header(
                        "X-Correlation-ID",
                        context.correlationId())
                .body(item);
    }
}
```

Only three inbound header values enter the request context. `Cookie` and `X-Forwarded-For` are never read or passed, preventing accidental forwarding across trust boundaries. `Authorization` is never returned in the body or response headers. Note that the demo validates SKU before policy; a production security filter should authenticate before reaching the controller so unauthenticated callers receive no unnecessary details.

## 19. Pure JUnit: testing parsing and policy

**`src/test/java/com/example/headerprop/HeaderRelayPolicyTest.java`**

```java
package com.example.headerprop;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class HeaderRelayPolicyTest {

    private static final String ID =
            "15cf0e17-83eb-42bc-a85f-0c70d7be1293";

    @Test
    void retainsValidHeaders() {
        RelayContext c = HeaderRelayPolicy.fromInbound(
                "Bearer demo-user-token.123", ID, "WEB");

        assertEquals("demo-user-token.123", c.accessToken());
        assertEquals(ID, c.correlationId());
        assertEquals("WEB", c.clientChannel());
    }

    @Test
    void bearerSchemeIsCaseInsensitive() {
        RelayContext c = HeaderRelayPolicy.fromInbound(
                "bearer token-for-test", ID, "MOBILE");

        assertEquals("token-for-test", c.accessToken());
    }

    @Test
    void createsIdWhenMissing() {
        RelayContext c = HeaderRelayPolicy.fromInbound(
                "Bearer token-for-test", null, "PARTNER");

        assertNotNull(c.correlationId());
        assertEquals(
                c.correlationId(),
                UUID.fromString(c.correlationId()).toString());
    }

    @Test
    void canonicalizesUppercaseUuid() {
        RelayContext c = HeaderRelayPolicy.fromInbound(
                "Bearer token-for-test",
                ID.toUpperCase(), "WEB");

        assertEquals(ID, c.correlationId());
    }

    @Test
    void rejectsMissingBearer() {
        ResponseStatusException ex = assertThrows(
                ResponseStatusException.class,
                () -> HeaderRelayPolicy.fromInbound(
                        null, ID, "WEB"));

        assertEquals(
                HttpStatus.UNAUTHORIZED, ex.getStatusCode());
    }

    @Test
    void rejectsInvalidCorrelationAndChannel() {
        ResponseStatusException badId = assertThrows(
                ResponseStatusException.class,
                () -> HeaderRelayPolicy.fromInbound(
                        "Bearer token-for-test",
                        "not-a-uuid", "WEB"));

        assertEquals(
                HttpStatus.BAD_REQUEST, badId.getStatusCode());

        ResponseStatusException badChannel = assertThrows(
                ResponseStatusException.class,
                () -> HeaderRelayPolicy.fromInbound(
                        "Bearer token-for-test",
                        ID, "UNTRUSTED"));

        assertEquals(
                HttpStatus.BAD_REQUEST,
                badChannel.getStatusCode());
    }

    @Test
    void rejectsInjectedCredentialText() {
        ResponseStatusException ex = assertThrows(
                ResponseStatusException.class,
                () -> HeaderRelayPolicy.fromInbound(
                        "Bearer abc\r\nX-Injected: yes",
                        ID, "WEB"));

        assertEquals(
                HttpStatus.UNAUTHORIZED, ex.getStatusCode());
    }
}
```

The suite contains **7 methods**. The CRLF-injection test runs at the Java policy layer; in a real servlet container, the server/proxy may also reject CRLF or malformed headers before reaching the controller. Do not force real HTTP tests to push malicious headers past container framing just to test the policy; test lower layers separately.

## 20. `@WebMvcTest`: testing controller header intake and transformation

**`src/test/java/com/example/headerprop/ProxyControllerTest.java`**

```java
package com.example.headerprop;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProxyController.class)
class ProxyControllerTest {

    private static final String ID =
            "15cf0e17-83eb-42bc-a85f-0c70d7be1293";

    @Autowired
    MockMvc mvc;

    @MockitoBean
    CatalogClient catalog;

    @Test
    void forwardsValidatedContextAndReturnsSameId()
            throws Exception {

        RelayContext expected = new RelayContext(
                "demo-user-token.123", ID, "WEB");

        when(catalog.fetch("BOOK", expected))
                .thenReturn(new CatalogItem(
                        "BOOK", "Spring Boot"));

        mvc.perform(get("/api/proxy/BOOK")
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer demo-user-token.123")
                        .header("X-Correlation-ID", ID)
                        .header("X-Client-Channel", "WEB"))
                .andExpectAll(
                        status().isOk(),
                        header().string("X-Correlation-ID", ID),
                        jsonPath("$.sku").value("BOOK"),
                        jsonPath("$.title").value("Spring Boot"));

        verify(catalog).fetch("BOOK", expected);
    }

    @Test
    void generatesIdThenReturnsExactlyThePassedId()
            throws Exception {

        when(catalog.fetch(eq("BOOK"), any(RelayContext.class)))
                .thenReturn(new CatalogItem(
                        "BOOK", "Spring Boot"));

        MvcResult result = mvc.perform(get("/api/proxy/BOOK")
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer token-for-test")
                        .header("X-Client-Channel", "WEB"))
                .andExpectAll(
                        status().isOk(),
                        header().exists("X-Correlation-ID"))
                .andReturn();

        ArgumentCaptor<RelayContext> captor =
                ArgumentCaptor.forClass(RelayContext.class);
        verify(catalog).fetch(eq("BOOK"), captor.capture());

        String actual = result.getResponse()
                .getHeader("X-Correlation-ID");
        assertEquals(actual, captor.getValue().correlationId());
        assertEquals(actual, UUID.fromString(actual).toString());
    }

    @Test
    void missingTokenNeverCallsCatalog() throws Exception {
        mvc.perform(get("/api/proxy/BOOK")
                        .header("X-Correlation-ID", ID)
                        .header("X-Client-Channel", "WEB"))
                .andExpect(status().isUnauthorized());

        verifyNoInteractions(catalog);
    }

    @Test
    void missingChannelNeverCallsCatalog() throws Exception {
        mvc.perform(get("/api/proxy/BOOK")
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer token-for-test")
                        .header("X-Correlation-ID", ID))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(catalog);
    }

    @Test
    void invalidCorrelationNeverCallsCatalog() throws Exception {
        mvc.perform(get("/api/proxy/BOOK")
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer token-for-test")
                        .header("X-Correlation-ID", "bad-id")
                        .header("X-Client-Channel", "WEB"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(catalog);
    }

    @Test
    void invalidSkuNeverCallsCatalog() throws Exception {
        mvc.perform(get("/api/proxy/book")
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer token-for-test")
                        .header("X-Client-Channel", "WEB"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(catalog);
    }
}
```

The suite has **6 methods**. It runs the real controller and policy while mocking `CatalogClient` with Mockito. Thus it proves **inbound headers → `RelayContext` → adapter method call** plus response statuses/headers—**not** that `RestClient` puts `Authorization` onto the outbound HTTP request. The `@RestClientTest` below tests that next boundary.

## 21. `@RestClientTest`: verifying the client's final outgoing request

**`src/test/java/com/example/headerprop/CatalogClientHeaderTest.java`**

```java
package com.example.headerprop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.client.MockRestServiceServer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@RestClientTest(CatalogClient.class)
@TestPropertySource(properties =
        "demo.catalog.base-url=http://catalog.example.test")
class CatalogClientHeaderTest {

    private static final String BASE =
            "http://catalog.example.test";

    private static final String ID =
            "15cf0e17-83eb-42bc-a85f-0c70d7be1293";

    @Autowired
    CatalogClient catalog;

    @Autowired
    MockRestServiceServer server;

    @Test
    void setsRequiredHeadersAndBlocksUnnecessaryOnes() {
        server.expect(requestTo(BASE + "/api/catalog/BOOK"))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header(
                        HttpHeaders.AUTHORIZATION,
                        "Bearer demo-user-token.123"))
                .andExpect(header("X-Correlation-ID", ID))
                .andExpect(header("X-Client-Channel", "WEB"))
                .andExpect(header(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE))
                .andExpect(request -> {
                    HttpHeaders actual = request.getHeaders();
                    assertFalse(actual.containsKey(HttpHeaders.COOKIE));
                    assertFalse(actual.containsKey(
                            "Proxy-Authorization"));
                    assertFalse(actual.containsKey(
                            "X-Forwarded-For"));
                })
                .andRespond(withSuccess(
                        "{\"sku\":\"BOOK\",\"title\":\"Java 17\"}",
                        MediaType.APPLICATION_JSON));

        CatalogItem item = catalog.fetch("BOOK",
                new RelayContext(
                        "demo-user-token.123", ID, "WEB"));

        assertEquals("BOOK", item.sku());
        assertEquals("Java 17", item.title());
        server.verify();
    }

    @Test
    void secondInvocationDoesNotInheritFirstUsersToken() {
        server.expect(requestTo(BASE + "/api/catalog/BOOK"))
                .andExpect(header(
                        HttpHeaders.AUTHORIZATION,
                        "Bearer token-user-A"))
                .andExpect(header(
                        "X-Correlation-ID",
                        "11111111-1111-4111-8111-111111111111"))
                .andRespond(withSuccess(
                        "{\"sku\":\"BOOK\",\"title\":\"A\"}",
                        MediaType.APPLICATION_JSON));

        server.expect(requestTo(BASE + "/api/catalog/PEN"))
                .andExpect(header(
                        HttpHeaders.AUTHORIZATION,
                        "Bearer token-user-B"))
                .andExpect(header(
                        "X-Correlation-ID",
                        "22222222-2222-4222-8222-222222222222"))
                .andRespond(withSuccess(
                        "{\"sku\":\"PEN\",\"title\":\"B\"}",
                        MediaType.APPLICATION_JSON));

        CatalogItem first = catalog.fetch("BOOK",
                new RelayContext(
                        "token-user-A",
                        "11111111-1111-4111-8111-111111111111",
                        "WEB"));

        CatalogItem second = catalog.fetch("PEN",
                new RelayContext(
                        "token-user-B",
                        "22222222-2222-4222-8222-222222222222",
                        "MOBILE"));

        assertEquals("A", first.title());
        assertEquals("B", second.title());
        server.verify();
    }

    @Test
    void usesOnlyConfiguredDownstreamBaseUrl() {
        server.expect(requestTo(BASE + "/api/catalog/BOOK"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"sku\":\"BOOK\",\"title\":\"Safe\"}",
                        MediaType.APPLICATION_JSON));

        CatalogItem item = catalog.fetch("BOOK",
                new RelayContext("token-for-test", ID, "WEB"));

        assertEquals("Safe", item.title());
        server.verify();
    }
}
```

The suite contains **3 methods**, each calling `server.verify()`. If the client fails to send the expected request, verify fails. With the slice's `RestClient.Builder` wired properly, the mock server swaps the request factory and opens no sockets. `@RestClientTest` resets mock server expectations between test methods; if a project binds mock servers manually or uses a static client, reset explicitly.

### 21.1. Verifying absent headers is just as critical as present headers

`header("Authorization", "...")` detects missing or wrong tokens. Yet a request might simultaneously leak `Cookie` or `Proxy-Authorization` via another interceptor. Thus a custom matcher:

```java
.andExpect(request ->
        assertFalse(request.getHeaders()
                .containsKey(HttpHeaders.COOKIE)))
```

is essential whenever policy forbids forwarding cookies. If the app uses an OAuth2 interceptor, verify the request **after the interceptor runs**. Never assert a successful DTO response and assume headers are secure.

## 22. Run commands and expected results

From a Gradle project with wrapper:

```bash
./gradlew test --tests com.example.headerprop.HeaderRelayPolicyTest --tests com.example.headerprop.ProxyControllerTest --tests com.example.headerprop.CatalogClientHeaderTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.headerprop.HeaderRelayPolicyTest --tests com.example.headerprop.ProxyControllerTest --tests com.example.headerprop.CatalogClientHeaderTest
```

| Class | Method count | Boundary |
|---|---:|---|
| `HeaderRelayPolicyTest` | 7 | Pure Java parsing/validation |
| `ProxyControllerTest` | 6 | Inbound/controller/HTTP errors, `CatalogClient` mocked |
| `CatalogClientHeaderTest` | 3 | Real outbound `RestClient`, mock response factory |
| **Total** | **16** | Header propagation per boundary |

**Expected outcome:** With Java 17, Spring Boot 3.5.x, and proper build dependencies, tests are expected to pass. No Gradle wrapper is embedded in the code blocks; for a new project, generate the wrapper via Gradle/IDE per convention. No fixed business stdout exists. JUnit reports typically appear at `build/reports/tests/test/index.html`. **Examples were reviewed at the source level and have not been executed via Gradle in a live repository**.

## 23. What do MockMvc and MockRestServiceServer still leave untested?

Even when both suites pass:

- No HTTP/TLS handshakes, socket timeouts, or proxies tested.
- No cross-origin redirect leaking `Bearer` tested.
- No JWT signature, issuer, expiry, `aud`, or scopes tested.
- No gateway rejection of duplicate `Authorization` or header smuggling tested.
- No Spring Security filter chain tested (demo omits it).
- No Micrometer Tracing span creation tested.
- No Reactor Context/`@Async` propagation tested.
- No downstream failure mapping inside the controller tested.
- No multi-user concurrency where security context must propagate.

**These are deliberate scope limits**, not "incomplete tests": each test level serves its own purpose. Add real mock-server and security integration tests whenever your risk register highlights those boundaries.

## 24. Why not use `headers.addAll(inboundHeaders)`?

```java
// COUNTER-EXAMPLE: forwarding everything the browser sent.
client.get().uri("/resource")
        .headers(out -> out.addAll(inboundHeaders))
        .retrieve().body(String.class);
```

It can leak:

- Unvalidated or wrong-audience `Authorization`.
- `Cookie` carrying session/browser state.
- Proxy `Proxy-Authorization`.
- `Host` or `X-Forwarded-Host` causing confused routing.
- Caller-forged `X-User-ID`.
- `Content-Length` invalid for the new body.
- `Connection`/`Transfer-Encoding` meaningful only per hop.
- Arbitrary custom headers absent from today's allowlist that appear tomorrow.

Instead:

```java
// Snippet: context comes from a verified security/policy boundary.
client.get().uri("/resource")
        .headers(h -> {
            h.setBearerAuth(context.accessToken());
            h.set("X-Correlation-ID", context.correlationId());
            h.set("X-Client-Channel", context.clientChannel());
            h.setAccept(List.of(MediaType.APPLICATION_JSON));
        })
        .retrieve().body(String.class);
```

This is a snippet; runnable `CatalogClient` already enforces a clean allowlist without `inboundHeaders`. In production, replace manual Bearer setting with an OAuth2 interceptor where appropriate.

## 25. Multi-valued headers and normalization

HTTP permits repeated header fields; different servers and proxies merge them using differing rules. `Authorization`, forwarded identity, and host headers are especially sensitive. If a client sends two `Authorization` values, never pick one arbitrarily while a proxy picks the other.

In an ingress/security filter, check:

```java
// Servlet filter snippet:
List<String> values =
        Collections.list(
                request.getHeaders(HttpHeaders.AUTHORIZATION));

if (values.size() != 1) {
    throw new BadCredentialsException(
            "Expected one Authorization value");
}
```

Production requires imports and framework error handling. Testing duplicate headers may require running behind a real proxy/server because `MockMvc` parses headers differently. Never rely on case-sensitivity of HTTP header names: `authorization` and `Authorization` are the exact same semantic header field.

### 25.1. Header injection and length limits

Overly long correlation IDs or values containing `\r`/`\n`, Unicode control chars, whitespace, or non-contract characters can break logs and headers. Validate at the boundary and configure max header sizes on gateways and servers. Test both policy and wire-level handling when request smuggling is a risk; servlet containers may reject malformed headers before reaching the controller.

## 26. Context propagation in async and reactive code

On a synchronous servlet path, Spring `SecurityContext` and MDC live on the request thread. With `@Async`, `CompletableFuture`, scheduled jobs, or reactive `WebClient`:

- `ThreadLocal` does not automatically follow thread switches.
- Thread pools reuse threads across users.
- Never copy a credential-bearing `SecurityContext` into background jobs without policy and TTL.
- Use Reactor Context and `ReactiveSecurityContextHolder` properly in reactive flows.
- Propagate and clean up correlation/tracing context across task boundaries.
- Never store user tokens in `static String currentToken` or singleton fields.

**Valuable test:** run two users A/B nearly concurrently, capture outgoing headers in the downstream mock for each call, and assert neither request carries the other user's token or correlation ID. Sequential A-then-B tests (as in the sample) catch basic stale state; concurrency tests protect against real races.

## 27. MDC and logging

Filter example:

```java
// Filter snippet; not a standalone class file.
MDC.put("correlationId", correlationId);
try {
    filterChain.doFilter(request, response);
} finally {
    MDC.remove("correlationId");
}
```

`finally` is vital because servlet worker threads are pooled and reused. Forgetting to clear lets request B log request A's ID. Never place access tokens in MDC, error response payloads, or tracing baggage.

If a filter generates correlation IDs, controllers should not regenerate them; maintain **a single owner** for the ID. The demo generates it in the controller for simplicity; production may generate it earlier in a filter and attach it to request attributes/tracing context across all paths (including errors).

### 27.1. Testing log redaction

Execute a request carrying a distinctive synthetic token, capture structured logs in the test, and assert the token never appears. Never use real tokens in test cases. When tracing is active, verify span attributes and baggage exclude `Authorization`. This requires a dedicated test because `RestClient` tests do not inspect logs automatically.

## 28. Retries, timeouts, and `Idempotency-Key`

When a client retries a request:

- GET is normally idempotent by semantics, yet still requires capped attempts, timeouts, and backoff.
- Payment/order POSTs may have committed despite a client timeout; retrying without an idempotency policy creates duplicate side effects.
- `Idempotency-Key` must keep the **same value across retries of one logical operation**, never generating a fresh key per attempt.
- Correlation IDs can stay stable per request while tracing creates distinct attempt spans.
- Access tokens may legitimately refresh via `OAuth2AuthorizedClientManager`; never pull another user's token.
- Interceptors may run on each attempt; using `headers.set` avoids duplicating header values when requests are reused.

Retry tests should stub 503 then 200 or network timeouts and assert attempt counts and exact headers—not merely final 200 success. For POSTs, mock repositories/side effects or run sandbox integration tests verifying **at-most-once/idempotent semantics**.

**Never forward `Idempotency-Key` to every downstream merely because the caller sent one:** keys can collide or be reused across trust boundaries. Contracts must scope keys explicitly (endpoint, account, operation).

## 29. Cross-origin redirects and SSRF

Suppose a trusted API replies:

```http
HTTP/1.1 302 Found
Location: https://untrusted.example/collect
```

If the HTTP client follows redirects automatically and sends `Authorization` to the new host, the token leaks. Redirect behavior varies across HTTP client factories, versions, and proxies; **never guess** from the `RestClient` name alone.

Defenses:

1. Fixed/trusted outbound base URLs; never read them from caller query/body input.
2. HTTPS, hostname validation, and network egress rules.
3. Policy-driven redirect settings (disabled or same-origin only).
4. Real HTTP mock servers: server A returns 302 to server B, assert server B **receives zero `Authorization`**.
5. Cap redirect hops, validate schemes/hosts/IPs, and block `file://` or localhost metadata services.
6. Never mistake `MockRestServiceServer` for an SSRF test, because the mock swaps the request factory and follows no real redirects.

`@RestClientTest` proves the code targets the expected base URL; it **does not prove** redirect, TLS, or proxy transport safety.

## 30. Downstream 401/403/429/5xx and error mapping

A syntactically valid `Authorization` header can still be rejected downstream for expired tokens, wrong audience/scopes, or missing permissions. Error paths to test:

| Downstream | Distinguish | Suggested public behavior |
|---|---|---|
| 401 | Invalid user token vs. bad service credential | Map error per contract; never expose token |
| 403 | Insufficient user/service permissions | Never "retry around permissions" |
| 429 | Rate limit | Policy-driven retry/backoff, no storms |
| 5xx | Service outage | 502/503 or explicit error code |
| Timeout | Network ambiguity; commit may have happened | 504/reconciliation/idempotency |
| Invalid JSON | Broken downstream contract | Never echo raw upstream body |
| Missing response header | Downstream header contract failed | Report correlation, never leak internals |

`RestClient.retrieve()` provides default 4xx/5xx error handling raising `RestClientResponseException`. The demo omits extra error mapping beyond the happy path. Production can pair `onStatus(...)` with `@RestControllerAdvice` and public error DTOs. Test status codes, allowed response headers, zero leaked secrets, zero body stack traces, and correlation ID consistency.

## 31. Mock vs. wire-level: never confuse the two guarantees

`MockRestServiceServer` replaces the HTTP request factory inside the client under test. It efficiently answers: **"Did we build the request with the required headers and values?"**

WireMock/OkHttp `MockWebServer` actually opens an HTTP port to answer: **"How do our HTTP library, redirects, proxies, cookies, timeouts, and TLS behave?"**

To construct a fuller integration test:

```text
MockMvc or real inbound HTTP
    |
    v
Real Spring Security filter chain
    |
    v
Controller + Service + production RestClient request factory
    |
    v
WireMock/MockWebServer on randomized port
    |
    +-- verify Authorization/correlation
    +-- return 401/503/302 as needed
    +-- capture retries and redirect traffic
```

With `@SpringBootTest(RANDOM_PORT)`, use a **real inbound HTTP client** when testing servlet transport too; `MockMvc` in a full context still mocks the servlet pipeline. Never label the demo's tests end-to-end; they intentionally test two cheap, clean boundaries.

## 32. Duplicate headers, precedence, and interceptor ownership

Multiple components can touch `Authorization` or correlation headers:

```text
API gateway
 -> Security filter
 -> Correlation filter
 -> Controller
 -> RestClient request-spec headers
 -> OAuth2 interceptor
 -> Tracing interceptor
 -> ClientHttpRequestFactory
 -> Network proxy
```

If both controller and interceptor set a token, precedence can silently shift after refactoring. If a filter generates ID A while a controller generates ID B, logs disconnect. If a retry interceptor calls `add` instead of `set`, header values duplicate.

**Solution:** Give every header **one owner**, define a precedence contract, and test at the final outbound boundary. Whenever adding an OAuth2 interceptor, update tests to run with that interceptor—do not merely assert internal context and assume the final outgoing header matches.

## 33. Common troubleshooting table

| Symptom | Likely root cause | Check |
|---|---|---|
| Downstream 401 despite inbound token | Dropped header, wrong audience/scope, expired | `RestClientTest` + security token validation |
| `Bearer Bearer abc` | Passed scheme into `setBearerAuth` | Pass token value only |
| User B sends A's token | Singleton `defaultHeader` / mutable field | Request-local headers, concurrency tests |
| `Cookie` appears downstream | `headers.addAll(...)` | Allowlist + absence matcher |
| Response missing correlation ID | Split ownership or missing filter | Capture both outbound and response |
| Correlation ID changes on each hop | Multiple generators | Generate once; validate and reuse |
| `traceparent` loses child span | Manual copying overrides tracer | Let W3C tracing instrumentation handle it |
| Headers double-added | Interceptors using `add` | Use `set` + final outgoing matchers |
| Mock test passes, prod redirects leak tokens | Mock skips network transport | Real HTTP redirect test |
| Missing channel | Missing contract/policy check | 400 before outbound |
| Invalid token format still hits API | No header validation | Pure policy + MVC zero interaction |
| Oversized header triggers 431 | Gateway/server header length cap | Boundary size policy |
| Tokens in logs | Printing full `HttpHeaders`/`RelayContext` | Redaction/log tests |
| Flaky async tests | `ThreadLocal` context lost or leaked | Context propagation tests |
| `MockMvc` passes while downstream headers break | `CatalogClient` is mocked | `@RestClientTest` |
| Client test passes while HTTP proxy fails | Different request factory/TLS/proxy | Wire-level integration |
| Downstream 429 triggers retry storm | Missing backoff/budget | Retry contract test |

## 34. Practical exercises

### A — Duplicate Bearer

How does `headers.setBearerAuth("Bearer abc")` break? Write a test asserting the exact outgoing `Authorization` header with `MockRestRequestMatchers.header` and fix it to pass `"abc"`.

### B — Missing correlation ID

Inbound omits `X-Correlation-ID`. Instead of comparing against another random UUID, capture the ID from the response and `RelayContext`, asserting both match and form a valid UUID.

### C — Injected correlation ID

A client sends an ID with newlines/control characters or missing UUID segments. How does the demo policy respond? Is the HTTP client called? Verify with `verifyNoInteractions`.

### D — Forged identity header

A caller sends `X-Tenant-ID=admin`. Where should the gateway obtain the tenant instead? Describe a test proving user A cannot access tenant B even with forged headers.

### E — Wrong token audience

Inbound JWT has audience A, while downstream requires audience B. May we copy `Authorization` directly? Describe OAuth2 token exchange vs. client credentials depending on the scenario.

### F — Fooled by mocks

`@WebMvcTest` passes because the mocked `CatalogClient` returns success, yet real `RestClient` code forgot `X-Correlation-ID`. Which test catches it? Why is `@RestClientTest` needed?

### G — Cookie leak

A refactor introduces `headers.addAll(inboundHeaders)` and starts forwarding `Cookie`. Which absence matcher should you add? Why is checking HTTP 200 insufficient?

### H — Redirect

An HTTP client follows a 302 from a trusted host to an untrusted host. `MockRestServiceServer` verified the initial request was fine. Does that prove no token leaked? Design a test with two real mock HTTP servers to check.

### I — Retrying POST

Downstream committed, the client timed out, and retries with a new key. What is the risk, and what `Idempotency-Key` policy is required?

### J — WebClient and Reactor Context

A `WebClient` call runs on another scheduler where servlet `ThreadLocal` tokens disappear. Propose a context design and a concurrent A/B test to detect token bleed.

### K — Correlation vs. traceparent

`trace-id` stays constant while outbound `parent-id` differs from inbound. Is that necessarily a bug? How do you test span relationships better than raw header equality?

### L — Evolving header contract

Downstream newly requires `X-API-Version=v2`. Should you update the adapter's allowlist and tests, or proxy all inbound headers? Explain why.

## 35. Code review checklist

- [ ] Only propagate headers on a per-downstream allowlist.
- [ ] Never relay Bearer tokens across wrong trust boundaries or with wrong audience/scope.
- [ ] Authenticate inbound tokens in production; never mistake the demo header parser for authn.
- [ ] Never log tokens in URLs, logs, MDC, tracing baggage, or error responses.
- [ ] Never configure user A's Authorization as a default header on a singleton `RestClient`.
- [ ] Pass only the token value—never the scheme—to `setBearerAuth`.
- [ ] Validate/generate correlation IDs once, returning them consistently downstream and to the caller.
- [ ] Let tracing propagators manage `traceparent`/`tracestate`.
- [ ] Enforce `X-Client-Channel`/version/idempotency per contract.
- [ ] Never relay cookies, proxy credentials, or forged forwarded headers.
- [ ] Let transport manage `Host`/`Content-Length`/hop-by-hop headers.
- [ ] Response headers follow a different allowlist than request headers.
- [ ] `@WebMvcTest` covers 400/401 and zero downstream invocations.
- [ ] `@RestClientTest` verifies method/URL, required headers, and forbidden headers.
- [ ] Client tests invoke `server.verify()`.
- [ ] Tokens and correlation IDs never bleed across sequential requests.
- [ ] Async/reactive context propagates and clears cleanly.
- [ ] Idempotent retries keep a stable key and bounded attempts.
- [ ] Real mock-server tests exist when redirects/TLS/proxies pose risks.
- [ ] Security integration tests verify issuer/audience/scope/expiry/authorization.
- [ ] Downstream 401/429/5xx/timeouts map cleanly without leaking secrets.
- [ ] Fixed/trusted base URLs—never taken arbitrarily from client inputs.
- [ ] Zero real tokens or PII in test fixtures.
- [ ] Test scopes stay honest: controller mocks ≠ outbound mocks ≠ real HTTP.

**Conclusion:** Safe header propagation demands **explicit policies, trust boundaries, and right-sized testing**. Tokens are credentials scoped by audience and permissions, correlation IDs are metadata needing unified formatting/ownership, and W3C trace context belongs to tracing instrumentation. Verify both **required** and **must-be-absent** headers; pass request-local contexts instead of mutable singletons; pair `@WebMvcTest` and `@RestClientTest` to guard both ends; and add wire-level/security tests wherever mocks cannot see.

### Official references

- Spring Boot 3.5 — `@RestClientTest` + `MockRestServiceServer`: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — REST Clients `RestClient`/`WebClient`: https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html
- Spring Framework 6.2 — Testing HTTP Client Code, mock vs. wire: https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-client.html
- Spring Security 6.5 — `OAuth2AuthorizedClientManager` and `RestClient` interceptor: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/authorized-clients.html
- RFC 6750 — Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- W3C Trace Context — `traceparent`/`tracestate`: https://www.w3.org/TR/trace-context/
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110
- OWASP — SSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
