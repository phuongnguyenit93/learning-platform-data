# RestTemplate in Existing Systems and Gradual Migration to RestClient — Deprecation from Spring Framework 7

> **Scope:** Spring Framework 6.2.x, Spring Boot 3.5.x, Java 17+ for runnable examples; cross-referencing deprecation announcements in Spring Framework **7.0** and the planned Java `@Deprecated` annotation in **7.1**. This lesson focuses on **systems currently using RestTemplate**: when to keep it, what can be reused, two-step migration to RestClient, method call equivalents, error/status differences, regression testing, timeouts, connection pools, auth, and rollout/rollback planning. Do not suggest switching to WebClient solely because RestTemplate is old: both RestTemplate and RestClient are **synchronous** HTTP clients.

## 1. Understanding the “Deprecated from Spring 7” Announcement Accurately

### 1.1. Version Milestones to Distinguish

| Version | RestTemplate Status | What to Do |
| --- | --- | --- |
| Spring Framework 6.0 | RestTemplate remains supported; RestClient does not exist yet | Maintain, ensure request factory/timeouts are configured |
| Spring Framework 6.1 | RestClient introduced, synchronous fluent API | Can begin incremental migration |
| Spring Framework 6.2 / Spring Boot 3.5 | RestTemplate still works; RestClient is the preferred API for new sync code | Migrate modules gradually with tests |
| Spring Framework 7.0 | **Deprecated in docs/reference and release notes**; RestClient recommended | Avoid writing new RestTemplate code; build a migration roadmap |
| Spring Framework 7.1 (targeted after Oct 2026) | **Planned** Java `@Deprecated` annotation on RestTemplate and related types | Verify Javadoc of the actual 7.1 release before relying on compiler warnings |
| Spring Framework 8.0 (unscheduled) | Spring announced **planned removal** of RestTemplate | Do not wait until upgrading major versions to start migrating |

The Spring Team announced this roadmap on September 30, 2025. Spring 7.0 release notes clarify: deprecation is in 7.0 documentation, while the Java `@Deprecated` annotation is planned for 7.1; removal is planned for 8.0. **Never write “RestTemplate was removed in Spring 7” or “Spring 7.0 enforces a compiler warning”**. Both statements are false.

Per Spring's public roadmap, exact dates for 7.1/8.0 may change. Do not infer from SNAPSHOT docs that an unreleased version is already a stable release.

Official sources:
- [Spring Framework 7.0 Release Notes — Deprecations](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes).
- [The state of HTTP clients in Spring — Spring Blog, 2025-09-30](https://spring.io/blog/2025/09/30/the-state-of-http-clients-in-spring/).
- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html).

### 1.2. Deprecated Does Not Mean Immediate Rewrite

For a running system, the right question is not “delete RestTemplate today?”, but:
- How many call sites exist and what is their test coverage?
- Which `ClientHttpRequestFactory`/Apache HttpClient/JDK client is in use?
- Are there custom `ResponseErrorHandler`, `ClientHttpRequestInterceptor`, `HttpMessageConverter`, `UriTemplateHandler`, or certificate/pool configs?
- Is there an upcoming Spring Framework 7/8 upgrade or JDK change?
- Do business endpoints have distinct retries, 404 semantics, timeouts, and auth?
- Can each service/client bean be migrated with compatibility tests without changing external behavior?

A well-configured and monitored RestTemplate **can continue running during step-by-step migration**. However, adding new RestTemplate code in a Spring 6.2+ codebase increases future call sites to migrate. For **new** synchronous HTTP calls, choose RestClient.

## 2. Why Does RestClient Replace RestTemplate?

RestTemplate is a template-method API from Spring 3.0:

```java
Item item = restTemplate.getForObject(
        "/items/{id}", Item.class, 7L);

ResponseEntity<Item> response = restTemplate.getForEntity(
        "/items/{id}", Item.class, 7L);
```

RestClient has a fluent API from Spring Framework 6.1:

```java
Item item = restClient.get()
        .uri("/items/{id}", 7L)
        .retrieve()
        .body(Item.class);

ResponseEntity<Item> response = restClient.get()
        .uri("/items/{id}", 7L)
        .retrieve()
        .toEntity(Item.class);
```

The above are **snippets**, requiring declared clients, `Item`, and a base URL. **Both remain synchronous/blocking at the caller** when performing the exchange. RestClient's main advantages are its fluent builder, per-request status handlers, and higher-level extensibility; **it does not turn requests into reactive I/O**.

### 2.1. Shared Infrastructure Keeps Migration Small

RestTemplate and RestClient share:
- `ClientHttpRequestFactory` (selects HTTP transport, timeouts/connection behavior);
- `HttpMessageConverter<?>` (JSON, String, byte[], form, Resource);
- `ClientHttpRequestInterceptor`;
- `ClientHttpRequestInitializer`;
- `UriBuilderFactory`/URI template handling;
- error mapping mechanisms, with adapter support to reuse `ResponseErrorHandler`.

Therefore Spring provides `RestClient.create(existingRestTemplate)` and `RestClient.builder(existingRestTemplate)` to create a client **from existing configuration**.

```java
RestClient newClient = RestClient.create(restTemplate);
// Or if you want further customization before building:
RestClient customized = RestClient.builder(restTemplate)
        .defaultHeader("Accept", "application/json")
        .build();
```

Since Spring Framework 6.1, this overload inherits legacy configuration such as request factory, converters, interceptors, initializers, URI builder factory, and error handler. This is the **biggest migration advantage**: you can switch **how call sites look** first, and refactor **how the client is constructed** later. You do not have to change pools/certificates/cookies/auth all at once.

### 2.2. What Is Not Guaranteed to Be Automatically Equivalent?

Reusing configuration does not make every behavior identical for free:
- Status/error handling with `RestClient.retrieve()` differs from `RestClient.exchange(...)`; see below.
- A request converter or custom interceptor might depend on header order or body buffering.
- URI templates vs URI builders, percent encoding, slashes, and query params can change if you alter base URLs/builders during migration.
- GET/HEAD/POST calls and body extraction must be replaced with the exact terminal operation.
- Multipart/form payloads, streaming downloads, ETags, content-length, and redirects need dedicated tests.
- Shared mutable config on `RestTemplate` must not be modified while serving requests; RestClient.create(template) does not make runtime mutation thread-safe.
- TLS/proxy pools/client libraries must be verified in real environments, not only mocks.
- Never assume every custom `ResponseErrorHandler` behaves identically to request-specific `onStatus` when altering config.

**Goal:** keep the wire contract with downstreams stable rather than “changing the API and opportunistically rewriting retries/errors/auth at the same time”.

## 3. Two-Phase Migration Plan

### Phase A — Keep Infrastructure, Migrate Call Sites

1. Group RestTemplate beans by downstream: catalog, pricing, identity, payments; document base URLs, interceptors, timeouts, and error handlers.
2. Pick a small group with solid unit/integration tests.
3. Build a RestClient from the **existing RestTemplate bean** via `RestClient.create(template)` or `builder(template)`.
4. Replace `getForObject/getForEntity/exchange/postForEntity/...` with equivalent RestClient chains **without** changing request factory/pool/auth at the same time.
5. Compare URI, method, headers, request body, JSON mapping, statuses/exceptions, and latency with tests.
6. Deploy to staging, canary, and monitor 4xx/5xx, pool waits, timeouts, and correlation IDs.
7. Roll back via routing or selecting the implementation if regressions appear.

```text
Legacy endpoints                  New endpoints
       |                                 |
 RestTemplate ----------------> RestClient.create(template)
       |                         (config inherited from template)
       +------------+--------------------+
                    |
       same request factory / interceptors /
       URI builder / message converters / error handler
                    |
                HTTP transport
                    |
               Downstream API
```

During this phase, RestTemplate and the derived RestClient can run side by side. Never delete the legacy bean before confirming no consumers remain. Resource-wise, verify they share the intended request factory/pool rather than spawning multiple independent HTTP clients that increase connection counts.

### Phase B — Replace Client Construction Once Call Sites Stabilize

Once all service methods use RestClient:
1. Build a standalone `RestClient.Builder` with `baseUrl`, `requestFactory`, `messageConverters`, `requestInterceptors`, and `defaultStatusHandler` as needed.
2. Use Spring Boot's `RestClient.Builder` configuration where appropriate to preserve customizations and observability.
3. Migrate custom error handlers to tested fluent status-handler APIs.
4. Remove the RestTemplate bean once zero consumers remain; remove migration-only adapters.
5. Audit dependencies and Java/Spring versions before upgrading to Spring Framework 7.x/8.x.
6. Keep the created tests as a **regression contract**, not merely compile checks.

```java
RestClient client = RestClient.builder()
        .baseUrl("https://catalog.example.test")
        .requestFactory(configuredRequestFactory)
        .requestInterceptor(configuredTracingInterceptor)
        .defaultStatusHandler(
                HttpStatusCode::is5xxServerError,
                (request, response) -> {
                    throw new IllegalStateException("Remote service failure");
                })
        .build();
```

**Snippet** illustrating builder APIs; requires declaring request factory and interceptor. Production should use typed exceptions and avoid swallowing upstream statuses/bodies needed for monitoring. When Spring Boot supplies a customized builder, avoid calling `RestClient.builder()` arbitrarily and accidentally losing Boot's SSL/observability setup.

## 4. Method Equivalents: RestTemplate → RestClient

| Legacy RestTemplate | New RestClient (in Spring 6.2) | Notes |
| --- | --- | --- |
| `getForObject(url, Dto.class, id)` | `get().uri(url,id).retrieve().body(Dto.class)` | DTO may be null if no body |
| `getForEntity(url, Dto.class, id)` | `get().uri(url,id).retrieve().toEntity(Dto.class)` | Captures status/headers |
| `postForObject(url, request, Dto.class)` | `post().uri(url).body(request).retrieve().body(Dto.class)` | Check Content-Type/JSON |
| `postForEntity(url, request, Dto.class)` | `post().uri(url).body(request).retrieve().toEntity(Dto.class)` | Read Location/201 status |
| `put(url, request, id)` | `put().uri(url,id).body(request).retrieve().toBodilessEntity()` | Returns ResponseEntity<Void>, caller may ignore result |
| `delete(url, id)` | `delete().uri(url,id).retrieve().toBodilessEntity()` | Does not require body on 204 |
| `exchange(url,GET,...,ParameterizedTypeReference)` | `get().uri(url).retrieve().toEntity(ParameterizedTypeReference)` | Preserves generic type |
| `exchange(url,PUT/POST,HttpEntity,...)` | `method(HttpMethod.X).uri(...).headers(...).body(...).retrieve()...` | Headers/body must be separated properly |
| `headForHeaders(url,id)` | `head().uri(url,id).retrieve().toBodilessEntity().getHeaders()` | HEAD has headers, no body |
| `execute(url, method, callback, extractor)` | `exchange((request,response)->...)` | **Manually** handle status/body/cleanup |
| `setErrorHandler(handler)` | `RestClient.builder(template)` keeps handler; later `defaultStatusHandler(...)` | Test status overrides/order |

Expressions in the table are **mapping patterns**, not mechanical text replacements for every overload. Some methods return different types (e.g., legacy delete/put returned `void`, while the RestClient chain returns ResponseEntity<Void>); update call sites without breaking service API contracts.

### 4.1. GET with URI Template

**Before:**

```java
ItemView item = restTemplate.getForObject(
        "/items/{id}", ItemView.class, itemId);
```

**After:**

```java
ItemView item = restClient.get()
        .uri("/items/{id}", itemId)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(ItemView.class);
```

`.uri("/items/{id}", ...)` uses URI templates instead of concatenating strings from inputs that might contain slashes/spaces. If a path variable has numeric constraints, validate in the domain layer. URI encoding across both APIs/URI factory configs needs regression tests; never let clients supply arbitrary absolute target URIs due to SSRF.

### 4.2. Reading Status and Headers

**Before:**

```java
ResponseEntity<ItemView> response =
        restTemplate.getForEntity("/items/{id}", ItemView.class, id);
```

**After:**

```java
ResponseEntity<ItemView> response = restClient.get()
        .uri("/items/{id}", id)
        .retrieve()
        .toEntity(ItemView.class);
```

Use `ResponseEntity` when `ETag`, `Last-Modified`, `Location`, 204/206 status, or business headers are needed. With `retrieve()`, 4xx/5xx throw `RestClientResponseException` by default unless custom status handlers apply.

### 4.3. POST and Location

```java
record CreateItem(String name) {}

ResponseEntity<ItemView> created = restClient.post()
        .uri("/items")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .body(new CreateItem("Spring"))
        .retrieve()
        .toEntity(ItemView.class);

URI location = created.getHeaders().getLocation();
```

This is a snippet needing a RestClient bean, DTO, and imports. If the server returns 201 without a body, `created.getBody()` can be null; avoid NPEs. When Location is relative, never trust raw remote headers to redirect browsers outside the trust boundary.

### 4.4. PUT, PATCH, and DELETE

```java
ResponseEntity<Void> updated = restClient.put()
        .uri("/items/{id}", id)
        .contentType(MediaType.APPLICATION_JSON)
        .body(new UpdateItem("Renamed"))
        .retrieve()
        .toBodilessEntity();

ResponseEntity<Void> deleted = restClient.delete()
        .uri("/items/{id}", id)
        .retrieve()
        .toBodilessEntity();
```

Snippet needs DTOs. If the server returns 204, there is no body by design; do not call `body(ItemView.class)` expecting an object on 204. PATCH requires the request factory/underlying HTTP transport to actually support PATCH, not merely compile; retest if legacy RestTemplate used a custom Apache HttpClient factory.

### 4.5. Generic Lists

```java
List<ItemView> items = restClient.get()
        .uri("/items")
        .retrieve()
        .body(new ParameterizedTypeReference<List<ItemView>>() {});
```

Do not use `List.class` and cast list elements to ItemView—the JSON decoder can return Maps due to lost generic type info. Directly equivalent to `RestTemplate.exchange(..., new ParameterizedTypeReference<List<ItemView>>() {})`.

### 4.6. Query Params, Headers, and Authentication

```java
ItemView item = restClient.get()
        .uri(builder -> builder
                .path("/items/{id}")
                .queryParam("lang", "vi")
                .build(id))
        .headers(headers -> {
            headers.setBearerAuth(validAccessToken);
            headers.setAccept(List.of(MediaType.APPLICATION_JSON));
        })
        .retrieve()
        .body(ItemView.class);
```

Snippet requires `validAccessToken`. Client credentials/service identities must come from OAuth2/trusted providers; never forward a user's bearer token indiscriminately to arbitrary upstreams. Keep tokens out of URLs/queries and exception logs. When migrating interceptors, verify you do not accidentally attach duplicate Authorization headers or duplicate tracing headers.

## 5. Common Trap: retrieve() Differs from exchange()

### 5.1. RestClient retrieve()

```java
ItemView item = restClient.get()
        .uri("/items/{id}", 7)
        .retrieve()
        .body(ItemView.class);
```

`retrieve()` selects the high-level API; actual exchange execution occurs at terminal `body(...)`, `toEntity(...)`, or `toBodilessEntity()`. For 4xx/5xx statuses, RestClient throws an exception by default. Customize per request:

```java
ItemView item = restClient.get()
        .uri("/items/{id}", 7)
        .retrieve()
        .onStatus(status -> status.value() == 404,
                (request, response) -> {
                    throw new ItemMissingException("not found");
                })
        .body(ItemView.class);
```

This is a snippet; `ItemMissingException` must be defined. The status predicate matches only 404; 500 still raises a server exception by default unless default handlers are replaced. Do not throw arbitrary `RuntimeException`s that strip status semantics when APIs must distinguish auth, 404, and transient errors.

### 5.2. RestClient exchange() Does Not Use retrieve Status Handlers

```java
ResponseEntity<String> raw = restClient.get()
        .uri("/items/{id}", 7)
        .exchange((request, response) -> {
            HttpStatusCode status = response.getStatusCode();
            if (status.isError()) {
                throw new IllegalStateException("Upstream HTTP error");
            }
            String body = new String(
                    response.getBody().readAllBytes(),
                    StandardCharsets.UTF_8);
            return ResponseEntity.status(status).body(body);
        });
```

Snippet needs `StandardCharsets`, `HttpStatusCode`, and `ResponseEntity` imports; the example reads only small bodies—never use `readAllBytes()` on large/infinite response streams. **Important:** `exchange(...)` **does not apply** `onStatus` or `defaultStatusHandler` configured for `retrieve()`, because the caller controls the response. If legacy RestTemplate code used `execute(...,ResponseExtractor)` to stream files, migrating to `RestClient.exchange(...)` requires testing input stream and resource cleanup before returning from the callback.

### 5.3. RestTemplate Error Handlers Are Carried Over

```java
RestTemplate template = new RestTemplate();
// Already configured template.setErrorHandler(customHandler) if needed.
RestClient restClient = RestClient.create(template);
```

Per Spring Javadoc, this overload **builds on** the legacy template including its error handler. When creating a new RestClient from a template with a `ResponseErrorHandler`, test against 400, 404, 429, and 500:
- Does the error handler throw the expected exception subtype?
- Does it consume the response body and deprive the decoder of data?
- Does behavior differ between `retrieve` and `exchange`?
- Does the handler leak PII or tokens?

Do not register both old and new default status handlers simultaneously without checking order: policies can override or execute twice unexpectedly.

### 5.4. Data Loss on Empty Bodies

`RestTemplate.getForObject(...)` and `RestClient.retrieve().body(...)` can return null on 2xx with no body. `toEntity(Dto.class)` captures status/headers even with a null body. If the service contract requires an item to exist, check for null explicitly before dereferencing and raise the proper business exception.

## 6. HTTP Status Handling Strategy During Migration

| HTTP / Scenario | Behavior to Verify |
| --- | --- |
| 200 JSON object | Body decodes into exact DTO |
| 201 Created | Status, Location, body per downstream |
| 202 Accepted | May be an async server task; do not treat 202 as completed |
| 204 No Content | Do not dereference null body |
| 206 Partial Content | Range/content headers and body streaming semantics |
| 301/302/307/308 | How HTTP transport handles redirects; are method/tokens preserved? |
| 304 Not Modified | ETag/cache logic, expect no body |
| 400 Validation | Return proper domain error without swallowing |
| 401/403 | Auth/permission; never blind-retry |
| 404 | Missing resource vs upstream misconfiguration per business |
| 409/412 | Conflict/precondition failure, optimistic locking |
| 429 | Rate-limit/Retry-After, bounded retries |
| 500/502/503/504 | Server/downstream failure; logging, timeouts, circuit breakers |
| Timeout/DNS/TLS failure | I/O exception, not necessarily an HTTP status |
| Malformed JSON | Message conversion exception, distinct from HTTP status |
| Oversized response body | Bound reads/buffering, test memory/OOM |

**Never “catch every RestClientException and return 404”.** Transport exceptions differ from status errors, and an upstream 404 does not automatically equal a 404 on your API facade.

### 6.1. RestClientException Is the Umbrella Type

Common categories:
- `RestClientResponseException` and subclasses: server returned an HTTP error response; exception holds status/headers/body when captured.
- `ResourceAccessException`: I/O errors, connect/read timeouts, DNS/socket issues.
- `UnknownContentTypeException`/message conversion failures: unable to decode the representation.
- Custom exceptions from `onStatus`/domain layer.

Specific subtypes vary by version/library. Never assert only exact exception classes for every network error in integration tests; assert status, cause category, and required behavior. When logging, never print raw upstream bodies containing personal data.

### 6.2. Conditional Retries

For synchronous HTTP clients, manage retries via service-layer policies or a resilience library (Spring Retry, Resilience4j, etc.) once dependencies/configs are added and request idempotency is established. Never write `while(true)` loops or retry every IOException regardless of POST side effects.

Conceptual business logic sketch (not a complete program):

```text
attempt request
  -> success: return
  -> 400/401/403: no retry
  -> 404: per domain contract, usually no retry
  -> 429: check Retry-After + budget + jitter
  -> 503/timeouts: retry only if operation is idempotent and within deadline
  -> exhausted: sanitized error + metrics + tracing
```

When a payment/order-creation POST times out, the server may already have committed; unconditional retries produce duplicates. Use idempotency keys, lookup reconciliation, or saga/outbox per business requirements.

## 7. Request Factory, Timeout, and Pool Configuration

### 7.1. Configuring Existing RestTemplate via Boot

Spring Boot 3.5 provides RestTemplateBuilder:

```java
@Bean
RestTemplate catalogTemplate(RestTemplateBuilder builder) {
    return builder
            .rootUri("https://catalog.example.test")
            .connectTimeout(Duration.ofSeconds(2))
            .readTimeout(Duration.ofSeconds(3))
            .build();
}
```

Snippet requires `Duration` and `RestTemplateBuilder` imports. Boot 3.5's `connectTimeout/readTimeout` methods accept Duration. Older Spring Boot versions may use `setConnectTimeout/setReadTimeout`. In Boot 4, check new packages and auto-configuration; do not mix Boot 3.5 and 4 imports.

Creating Phase A RestClient:

```java
@Bean
RestClient catalogRestClient(RestTemplate catalogTemplate) {
    return RestClient.create(catalogTemplate);
}
```

This preserves the template's configuration. However, **timeouts must be measured on the actual HTTP transport**: connect timeout, socket/read, connection pool lease, and overall deadline differ. Read timeout does not automatically cover DNS/TLS/queue/retries. All timeout cases must be tested against a slow mock HTTP server.

### 7.2. Configuring RestClient Directly in Phase B

```java
@Bean
RestClient catalogClient(RestClient.Builder builder,
                         ClientHttpRequestFactory factory) {
    return builder
            .baseUrl("https://catalog.example.test")
            .requestFactory(factory)
            .build();
}
```

Snippet requires a `factory` bean chosen/configured for the app's transport. If Apache HttpClient is needed, verify dependencies/classpath and confirm `HttpComponentsClientHttpRequestFactory` is actually active; never assume every factory offers strong connection pooling. Configure timeouts/certificates/proxies/compression on the appropriate **factory/underlying HTTP client**.

### 7.3. Commonly Confused Timeouts

- DNS: resolves hostnames; may follow OS/network/library-specific policies.
- Connect: opens the TCP connection.
- TLS handshake: verifies certificates and completes TLS.
- Connection pool acquire: waits to obtain a free connection.
- Response/read: waits for server data and reads bytes.
- Overall deadline: total duration, including redirects/retries/backoff.
- Idle timeout: connection keepalive/pool eviction, not a request deadline.

**Never set a single “3-second” option and conclude every request finishes under 3 seconds.** Test against slow downstreams, connection exhaustion, DNS/TLS failures, large responses, and retries.

### 7.4. Pools and Thread Concurrency

RestTemplate/RestClient still block the caller during a synchronous exchange. If an MVC application has 200 worker threads calling a slow downstream simultaneously, all 200 threads can be occupied even when the HTTP pool is smaller. A pool of 20 connections with 200 callers causes 180 callers to wait on acquire or fail with timeouts. Plan capacity based on:
- inbound RPS/concurrency;
- downstream p95/p99 latency;
- max connections, per-route limits, and pending queues;
- max servlet threads and scheduled workers;
- rate limiters/bulkheads;
- retries that amplify load.

A fluent REST API does not automatically provide rate limiting or non-blocking resource control.

## 8. Message Converters, JSON, and Generic Types

RestTemplate and RestClient both use `HttpMessageConverter`. Yet migration can expose differences if legacy converter configuration is dropped.

### 8.1. Custom Converters

```java
RestClient client = RestClient.builder()
        .messageConverters(converters -> {
            // Register custom converter if business requires.
            // Avoid accidentally removing default converters.
        })
        .build();
```

This is a snippet, not production JSON configuration. In Spring 7, some converter configuration APIs change/deprecate; code targeting Spring 6.2 must consult its matching Javadoc.

### 8.2. Generic Types

**Before:**

```java
ResponseEntity<List<ItemView>> response =
        restTemplate.exchange(
                "/items", HttpMethod.GET, HttpEntity.EMPTY,
                new ParameterizedTypeReference<List<ItemView>>() {});
```

**After:**

```java
List<ItemView> items = restClient.get()
        .uri("/items")
        .retrieve()
        .body(new ParameterizedTypeReference<List<ItemView>>() {});
```

These are snippets requiring `ItemView` DTO and imports. `List.class` retains only the raw type; JSON objects become maps and trigger ClassCastException when accessed as DTOs. For generic wrappers like `PageEnvelope<ItemView>`, use ParameterizedTypeReference identically.

### 8.3. Multipart, Forms, and Downloads

Do not blindly replace a `RestTemplate.execute(..., ResponseExtractor)` reading large files with `RestClient.retrieve().body(byte[].class)`: the new approach buffers the entire response on the heap. For downloads, evaluate `RestClient.exchange(...)` streaming inside the callback with proper cleanup; test large payloads and client disconnects separately.

If the legacy client sends multipart forms (files, strings, repeated keys), compare request wire formats:
- multipart boundary, Content-Disposition, filename escaping;
- per-part Content-Type;
- Content-Length vs chunked transfer;
- encoded form parameters;
- request buffering/streaming and memory;
- HTTP PATCH/PUT method support in the request factory.

A passing 200 JSON test does not substitute for multipart tests.

## 9. Security, Headers, and URI Encoding

### 9.1. Interceptors Can Be Reused, but Access Controls Still Apply

```java
RestTemplate template = new RestTemplate();
template.getInterceptors().add((request, body, execution) -> {
    request.getHeaders().set("X-Service-Name", "catalog-reader");
    return execution.execute(request, body);
});

RestClient client = RestClient.create(template);
```

Snippet illustrates a shared interceptor; header `X-Service-Name` is not an authentication credential and clients can spoof headers if inbound proxies do not strip them. Never treat it as proof of authorization. For real auth, use OAuth2/token providers/signed requests and ensure bearer tokens are never sent to untrusted hosts.

### 9.2. Never Concatenate Input into URLs

```java
// Risk of bad encoding and SSRF if userInput is an arbitrary URL:
String unsafe = baseUrl + "/items/" + userInput;
```

URI template expansion:

```java
client.get()
        .uri("/items/{id}", id)
        .retrieve()
        .body(ItemView.class);
```

However, URI encoding **does not stop SSRF** if users can supply absolute `http://internal.host/...` values. For dynamic URLs, enforce host/scheme/port allowlists, network egress controls, redirect restrictions, and DNS rebinding defenses per your threat model.

### 9.3. Do Not Lose Security/Observability When Switching to a New Builder

If legacy `RestTemplate` had a `ClientHttpRequestInterceptor` adding:
- Authorization from a service credential provider;
- traceparent/request ID;
- tenant context/locale;
- metrics/timing;
- mTLS client certificates via request factory;

the new RestClient setup **must** preserve the equivalent. With Spring Security/OAuth2, token context propagation may rely on threads/schedulers; never read JWTs from a ThreadLocal belonging to an unrelated thread. Test that headers are set once, not duplicated or leaked across cross-origin redirects.

### 9.4. ResponseEntity and Cache Headers

Some endpoints return 304 with ETag/If-None-Match. When migrating clients, preserve:
- conditional request headers;
- 304 status with no body;
- ETag, Last-Modified, Cache-Control response headers;
- cache handling in the business layer.

Never hardcode logic like “null body = 404” when 204/304 are valid HTTP responses.

## 10. Runnable Example: Two Clients, One Configuration

Spring Boot 3.5/Java 17 demo running a **Spring MVC server** with an in-app mock supplier:
- `GET /remote/items/7` is the demo upstream;
- `GET /bridge/old/7` calls it via RestTemplate;
- `GET /bridge/new/7` calls it via a RestClient built from the configured RestTemplate;
- `GET /bridge/new-meta/7` demonstrates status/headers via ResponseEntity;
- `GET /bridge/new-list` uses a generic type;
- `POST /bridge/old` and `POST /bridge/new` create items via both clients.

**Demo note:** synchronous HTTP calls from an MVC handler back to the same server on localhost:8080 are strictly for easy observation, not a production architecture; under heavy load this self-call pattern can exhaust servlet worker threads. In real systems, clients call independent upstream services via trusted URLs with dedicated pools and deadlines.

### 10.1. Maven Project and Dependencies

From [Spring Initializr](https://start.spring.io/), create a Maven project:
- Spring Boot **3.5.x**;
- Java **17**;
- **Spring Web** dependency.

POM fragment (parent, plugins, and dependency management generated by Initializr):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

No spring-boot-starter-webflux is needed for this **synchronous** migration.

### 10.2. Complete Java Source

Save the entire contents to `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.net.URI;
import java.time.Duration;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.RestTemplate;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    RestTemplate legacyTemplate(RestTemplateBuilder builder) {
        return builder
                .rootUri("http://localhost:8080")
                .connectTimeout(Duration.ofSeconds(2))
                .readTimeout(Duration.ofSeconds(3))
                .build();
    }

    @Bean
    RestClient migratedClient(RestTemplate legacyTemplate) {
        // Phase A: inherit existing HTTP configuration.
        return RestClient.create(legacyTemplate);
    }
}

record Item(long id, String name) {
}

record CreateItem(String name) {
}

record ApiError(String code, int upstreamStatus) {
}

// Mock server simulating an independent upstream (demo only).
@RestController
@RequestMapping("/remote/items")
class RemoteItemController {

    private final AtomicLong nextId = new AtomicLong(7);
    private final ConcurrentMap<Long, Item> items =
            new ConcurrentHashMap<>();

    RemoteItemController() {
        items.put(7L, new Item(7L, "Spring Framework"));
    }

    @GetMapping("/{id}")
    ResponseEntity<Item> get(@PathVariable("id") long id) {
        Item item = items.get(id);
        return item == null
                ? ResponseEntity.notFound().build()
                : ResponseEntity.ok(item);
    }

    @GetMapping
    List<Item> list() {
        return items.values().stream()
                .sorted(Comparator.comparingLong(Item::id))
                .toList();
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Item> create(@RequestBody CreateItem command) {
        if (command.name() == null || command.name().isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        long id = nextId.incrementAndGet();
        Item item = new Item(id, command.name().trim());
        items.put(id, item);

        return ResponseEntity
                .created(URI.create("/remote/items/" + id))
                .body(item);
    }
}

// Transition from legacy call sites to fluent RestClient.
@RestController
@RequestMapping("/bridge")
class BridgeController {

    private final RestTemplate oldClient;
    private final RestClient newClient;

    BridgeController(RestTemplate legacyTemplate,
                     RestClient migratedClient) {
        this.oldClient = legacyTemplate;
        this.newClient = migratedClient;
    }

    @GetMapping("/old/{id}")
    Item oldGet(@PathVariable("id") long id) {
        return oldClient.getForObject(
                "/remote/items/{id}", Item.class, id);
    }

    @GetMapping("/new/{id}")
    Item newGet(@PathVariable("id") long id) {
        return newClient.get()
                .uri("/remote/items/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(Item.class);
    }

    @GetMapping("/new-meta/{id}")
    ResponseEntity<Item> newGetWithHeaders(
            @PathVariable("id") long id) {
        return newClient.get()
                .uri("/remote/items/{id}", id)
                .retrieve()
                .toEntity(Item.class);
    }

    @GetMapping("/new-list")
    List<Item> newList() {
        return newClient.get()
                .uri("/remote/items")
                .retrieve()
                .body(new ParameterizedTypeReference<List<Item>>() {});
    }

    @PostMapping(path = "/old",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Item> oldCreate(
            @RequestBody CreateItem input) {
        return oldClient.postForEntity(
                "/remote/items", input, Item.class);
    }

    @PostMapping(path = "/new",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Item> newCreate(
            @RequestBody CreateItem input) {
        return newClient.post()
                .uri("/remote/items")
                .contentType(MediaType.APPLICATION_JSON)
                .body(input)
                .retrieve()
                .toEntity(Item.class);
    }
}

@RestControllerAdvice
class ClientErrorAdvice {

    @ExceptionHandler(RestClientResponseException.class)
    ResponseEntity<ApiError> handle(
            RestClientResponseException ex) {
        return ResponseEntity.status(ex.getStatusCode())
                .body(new ApiError(
                        "UPSTREAM_HTTP_ERROR",
                        ex.getStatusCode().value()));
    }
}
```

### 10.3. Code Explanation

- Java 17 allows `record`; a file contains one public top-level class `DemoApplication`.
- `@SpringBootApplication` scans @RestControllers in the same package and starts the default embedded Tomcat from Spring MVC starter.
- `legacyTemplate(RestTemplateBuilder)` is a bean configured **once** with root URL and Duration timeouts. Never mutate config while multiple threads use it.
- `migratedClient(RestTemplate)` uses `RestClient.create(template)` to inherit the template's request factory, converters, interceptors, initializers, URI builder, and error handler.
- `RemoteItemController` is an in-process simulated upstream. GET/POST endpoints use an in-memory map and AtomicLong, with no database or auth.
- `BridgeController` shows both HTTP clients returning the same domain type `Item`, differing only in call style.
- `newGetWithHeaders` returns ResponseEntity to keep status/headers; `newList` uses ParameterizedTypeReference to avoid raw Lists.
- `ClientErrorAdvice` is a **demo policy**: forwarding upstream 404 or 500 statuses for easy comparison. In production, an upstream 500 should typically map to facade 502/503 or an appropriate business error; do not blindly forward all upstream statuses.
- Both `RestClient` and `RestTemplate` are synchronous; the MVC worker thread waits for the remote call to finish. Never claim fluent syntax makes it faster.
- Beans are created at startup without allocating new HTTP clients per request.
- If changing `server.port` away from 8080, update `rootUri("http://localhost:8080")` accordingly; this is hardcoded demo config.
- No auth/CSRF/CORS/rate limiting/mTLS/retries/observability/persistence; not for public deployment.

### 10.4. Running

In the Maven project directory generated by Initializr:

```bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell or CMD
mvnw.cmd spring-boot:run
```

### 10.5. GET via Both Clients

```bash
curl -i 'http://localhost:8080/bridge/old/7'
curl -i 'http://localhost:8080/bridge/new/7'
curl -i 'http://localhost:8080/bridge/new-meta/7'
```

All three responses under normal operation:
- Status 200;
- Matching JSON Content-Type;
- equivalent body:

```json
{"id":7,"name":"Spring Framework"}
```

JSON whitespace and header ordering are not part of the business contract. `/bridge/new-meta/7` demonstrates using `ResponseEntity` to preserve status and response headers. Legacy RestTemplate vs RestClient differs only in the client-side programming API.

### 10.6. Generic List

```bash
curl -i 'http://localhost:8080/bridge/new-list'
```

On startup, the JSON body contains one item:

```json
[{"id":7,"name":"Spring Framework"}]
```

After POST calls, the list includes additional items sorted by Item.id ascending because the controller sorts by Item.id.

### 10.7. POST via Both Clients

```bash
curl -i -X POST 'http://localhost:8080/bridge/old' \
  -H 'Content-Type: application/json' \
  --data-binary '{"name":"Legacy-created"}'

curl -i -X POST 'http://localhost:8080/bridge/new' \
  -H 'Content-Type: application/json' \
  --data-binary '{"name":"RestClient-created"}'
```

On startup with no concurrent requests, the first POST creates ID 8 and the second creates ID 9; each response is HTTP 201 Created, header `Location: /remote/items/{id}`, and JSON body `{"id":8,"name":"Legacy-created"}` or the matching ID. Note: Location points to **the demo remote endpoint resource**, not necessarily the bridge endpoint.

### 10.8. 404 via Legacy and Modern

```bash
curl -i 'http://localhost:8080/bridge/old/999'
curl -i 'http://localhost:8080/bridge/new/999'
```

The demo upstream returns HTTP 404. Legacy RestTemplate and migrated RestClient receive the default HTTP status error; `ClientErrorAdvice` turns both into the same demo policy response:

```json
{"code":"UPSTREAM_HTTP_ERROR","upstreamStatus":404}
```

Do not rely on this alone to claim every custom error handler in a real app copies and runs identically. Regression tests are needed for real handlers, especially with `RestClient.exchange` and request-specific `onStatus`.

### 10.9. Windows PowerShell

```powershell
curl.exe -i "http://localhost:8080/bridge/old/7"
curl.exe -i "http://localhost:8080/bridge/new/7"
curl.exe -i "http://localhost:8080/bridge/new-list"
curl.exe -i "http://localhost:8080/bridge/new/999"
```

If escaping JSON quotes is awkward in Windows shells, create a UTF-8 `request.json`:

```json
{"name":"RestClient-created"}
```

Send via:

```powershell
curl.exe -i -X POST "http://localhost:8080/bridge/new" -H "Content-Type: application/json" --data-binary "@request.json"
```

## 11. Testing Migration: Do Not Only Assert HTTP 200

A successful migration means **both clients behave equivalently at the HTTP boundary**, not merely returning the same DTO. Test methods, path/query encoding, headers, body bytes/JSON, 200/201/204, 404/429/5xx, TLS/proxies, connection reuse, and deadlines.

### 11.1. Unit Tests with MockRestServiceServer

Spring Test supports `MockRestServiceServer.createServer(RestTemplate)` and `MockRestServiceServer.bindTo(RestClient.Builder)`. This mocks the HTTP boundary and compares URIs/methods/JSON deterministically.

With Boot 3.5, add the POM fragment:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Save `src/test/java/com/example/demo/MigrationClientTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.DefaultUriBuilderFactory;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class MigrationClientTest {

    private static RestTemplate templateWithBaseUri() {
        RestTemplate template = new RestTemplate();
        template.setUriTemplateHandler(
                new DefaultUriBuilderFactory("https://catalog.example.test"));
        return template;
    }

    @Test
    void oldTemplateSendsExpectedGet() {
        RestTemplate template = templateWithBaseUri();

        MockRestServiceServer server =
                MockRestServiceServer.createServer(template);

        server.expect(requestTo(
                        "https://catalog.example.test/items/7"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"id\":7,\"name\":\"Spring Framework\"}",
                        MediaType.APPLICATION_JSON));

        Item item = template.getForObject(
                "/items/{id}", Item.class, 7);

        assertNotNull(item);
        assertEquals(7, item.id());
        assertEquals("Spring Framework", item.name());
        server.verify();
    }

    @Test
    void newClientCopiesLegacyUriConfiguration() {
        RestTemplate template = templateWithBaseUri();

        RestClient.Builder builder = RestClient.builder(template);

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        RestClient client = builder.build();

        server.expect(requestTo(
                        "https://catalog.example.test/items/7"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"id\":7,\"name\":\"Spring Framework\"}",
                        MediaType.APPLICATION_JSON));

        Item item = client.get()
                .uri("/items/{id}", 7)
                .retrieve()
                .body(Item.class);

        assertNotNull(item);
        assertEquals(7, item.id());
        assertEquals("Spring Framework", item.name());
        server.verify();
    }

    @Test
    void newClientRetrieveStillThrowsOn404() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://catalog.example.test");

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        RestClient client = builder.build();

        server.expect(requestTo(
                        "https://catalog.example.test/items/99"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        RestClientResponseException exception = assertThrows(
                RestClientResponseException.class,
                () -> client.get()
                        .uri("/items/{id}", 99)
                        .retrieve()
                        .body(Item.class));

        assertEquals(404, exception.getStatusCode().value());
        server.verify();
    }
}
```

Test explanation:
- Test 1 keeps the legacy RestTemplate API and base URI.
- Test 2 creates `RestClient.Builder` **from the already-configured template**, then `bindTo(builder)` attaches a mock request factory before `build()`. The test focuses strictly on URI/method/JSON without DNS/TLS.
- Test 3 protects the 404 contract from `retrieve()`; `RestClientResponseException` is the right base type by default.
- Mocking the builder replaces the request factory and therefore **does not prove** connection pooling, SSL, or timeouts of the legacy factory; separate integration tests are needed for those behaviors.

### 11.2. Additional Test Matrix

| Behavior | Concrete Checks |
| --- | --- |
| JSON GET 200 | DTO fields, UTF-8, Content-Type |
| Generic list | ParameterizedTypeReference preserves type |
| POST 201 | Location, request Content-Type, response status/body |
| Empty 204 | No NPE, code handles null body |
| 304/ETag | Headers, conditional GET if used |
| 400/401/403 | No retries and no raw upstream body leakage |
| 404 | Policy: missing resource vs dependency misconfiguration |
| 409/412 | Conflict/ETag behavior |
| 429/Retry-After | Rate limit/backoff, no retry storms |
| 500/503/504 | Typed service errors, metrics, deadlines |
| Connect/read timeouts | Test against slow HTTP server, verify workers do not hang |
| TLS/proxies | Certificate/host validation, ALPN, proxies matching prod |
| Multipart/PATCH | Request factory supports method, binary bodies accurate |
| Authorization/tracing | Interceptor headers neither lost nor duplicated |
| Query/path encoding | Spaces, Unicode, slashes, `%`, repeated queries |
| Concurrency | Thread pools, connection reuse, saturation |
| Redirects | Is Authorization ever forwarded outside the trust boundary? |

### 11.3. Running Tests

```bash
# Linux / macOS
./mvnw test

# Windows
mvnw.cmd test
```

**Do not treat the presence of source/test code in documentation as execution results.** To confirm runnable status in a real project, run `./mvnw test` and the curl steps in a matching Spring Boot 3.5/JDK 17 environment. Adjust tests for any custom beans, security, or auto-configuration policies.

## 12. Phased Rollout, Monitoring, and Rollback

### 12.1. Inventory All RestTemplate Consumers

Document per service/call site (no new spreadsheet needed if tracking within one project):

| Inventory Item | What to Record |
| --- | --- |
| Bean name and consumer | Which service uses which RestTemplate? |
| Downstream logical name | Catalog, payments, identity, shipping |
| Method/path | GET, POST, PATCH, multipart/stream |
| Timeout/request factory | Connect/read/pool acquisition limits |
| Interceptors | Auth, tracing, tenancy, metrics, signatures |
| Converters | JSON/XML/custom, multipart |
| Error handler | Class, status mapping, body handling |
| Resilience | Retries, circuit breaker, fallbacks, idempotency |
| Security | Credentials, redirect/SSRF restrictions |
| Test coverage | 200/4xx/5xx, timeouts, encoding |
| Migration status | Legacy, dual-client, converted, validated |

### 12.2. Canary by Client Bean or Service

You can keep two implementations behind one interface:

```java
interface CatalogGateway {
    ItemView load(long id);
}

class LegacyCatalogGateway implements CatalogGateway {
    // RestTemplate getForObject...
}

class MigratedCatalogGateway implements CatalogGateway {
    // RestClient get().retrieve().body()...
}
```

This is a design snippet, not full source. Select the implementation via Spring Profiles/server-side feature flags and monitor the canary. Be careful **never to send two live POSTs in parallel** just to shadow-compare, because side effects will be duplicated. If shadowing read-only GETs, still verify quotas, auth/PII, and cost.

### 12.3. Before-and-After Metrics

Compare before/after migration:
- 4xx/5xx error rates and I/O timeouts;
- p50/p95/p99 latency per downstream;
- connection pool active/idle/pending counts;
- JVM thread states, servlet pool usage, heap/GC;
- request volume and retry attempts;
- URI template/HTTP method distributions;
- response payload bytes/codec errors;
- authorization/correlation header propagation.

Never use raw user IDs, order IDs, emails, or request IDs as high-cardinality Micrometer tags. Use URI templates and logical service names.

### 12.4. Rollback Criteria

Roll back if:
- 404/500 mappings diverge from contract;
- 429/throttling or connection pool timeouts spike;
- auth signatures go missing/mismatch or redirects jump to unexpected hosts;
- duplicate POSTs occur from retries;
- multipart/streaming payloads break;
- JSON decode failure rates rise;
- request timeouts stop bounding slow downstreams;
- any data leak, SSRF, or security regression appears.

Because Phase A preserves the old RestTemplate alongside its request factory/config, rolling back can be as simple as switching the call site/service implementation back to RestTemplate, provided no unintended business data changes occurred.

## 13. When Should Architecture Be Reconsidered Instead of Just Changing the API?

### 13.1. If Using the WebFlux Event Loop

Never swap RestTemplate for RestClient and call it directly inside a WebFlux handler: **RestClient is still blocking**. In a native WebFlux app, prefer WebClient to compose network I/O, or temporarily bridge blocking calls onto bounded `Schedulers.boundedElastic()`:

```java
Mono<ItemView> bridged = Mono.fromCallable(
                () -> restClient.get()
                        .uri("/items/{id}", id)
                        .retrieve()
                        .body(ItemView.class))
        .subscribeOn(Schedulers.boundedElastic());
```

This is a reactive bridge snippet; it does not make RestClient a non-blocking HTTP transport. Bound boundedElastic queue/concurrency and downstream pools. If the app mainly uses JDBC/JPA and sync HTTP, Spring MVC may be a better fit than WebFlux.

### 13.2. Interface-First HTTP Service Clients

Spring 6+ supports declaring HTTP interfaces:

```java
@HttpExchange("/items")
interface CatalogApi {
    @GetExchange("/{id}")
    ItemView get(@PathVariable("id") long id);
}
```

And creating a proxy over RestClient:

```java
CatalogApi catalog = HttpServiceProxyFactory
        .builderFor(RestClientAdapter.create(restClient))
        .build()
        .createClient(CatalogApi.class);
```

These are snippets needing imports and a RestClient bean. HTTP Service Client is an **interface/proxy over RestClient**, not a new transport, and methods remain synchronous when using RestClientAdapter. Useful when multiple endpoints share a remote contract, cutting boilerplate and easing interface mocking. There is no requirement to rewrite RestTemplate into an HTTP interface if the problem only needs one GET.

### 13.3. For Very Large Streaming Workloads

RestClient supports low-level exchange to process InputStreams inside callbacks, while still holding a caller thread. WebClient is better suited for event streams/NDJSON/high concurrency and reactive processing. Never force streaming tasks onto `body(byte[].class)` because that can buffer the entire payload in RAM.

## 14. Common Migration Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| RestClient missing in Spring 6.0 | API debuted in 6.1 | Upgrade per compatibility plan |
| Claiming RestTemplate was removed in Spring 7 | Misread deprecation notice | 7.0 docs deprecation; 7.1 planned @Deprecated; 8.0 planned removal |
| Keeping RestTemplate forever because no warning shows | Spring 7.0 may not have the annotation yet | Plan migration based on the roadmap |
| Switching to RestClient drops auth headers | Dropped old interceptor/customizer | `RestClient.create(template)` + integration test |
| URI routes differ from before | Changed URI builder/baseUrl/encoding | Compare HTTP requests byte-level |
| 404/500 handled differently | Dropped error handler/status policy | Test retrieve/onStatus/defaultStatusHandler |
| Using `exchange` and expecting throws on 4xx | exchange skips retrieve status handlers | Check status and body manually |
| Request never gets sent | Called `retrieve()` without terminal method | `body/toEntity/toBodilessEntity` |
| 204 causes NullPointerException | Empty body is valid | Null check / ResponseEntity |
| JSON List becomes List<Map> | Type erasure | ParameterizedTypeReference |
| POST duplicated on retry | Missing idempotency | Key + reconciliation |
| Download causes OOM | Replaced stream extractor with byte[] | Bounded streaming exchange |
| PATCH works on one client, fails on another | Different request factory | Transport-specific PATCH tests |
| HTTP pool saturated | Connection limits misaligned with load | Pool metrics/bulkhead/timeouts |
| Netty WebFlux still stalls | RestClient is still blocking | WebClient/native reactive |
| SSL/certificate errors after migration | New request factory dropped mTLS config | Reuse/test TLS config |
| Redirect leaks tokens | Unrestricted cross-origin auto-follow | Redirect/auth/allowlist policies |
| Testing happy path only | Missing 4xx/5xx/timeout/encoding tests | Contract test matrix |
| Creating RestClient per request | Wasted pools/client lifecycle | Reuse bean |
| Mutating RestTemplate config during concurrent calls | Unsafe mutation | Startup-only configuration |
| Relying on deprecated annotation in wrong version | 7.0 docs differ from 7.1 API | Check Javadoc/release notes for exact version |

## 15. Implementation Checklist

- [ ] Pin Spring/JDK versions; distinguish **7.0 docs** deprecation from **planned 7.1 Java annotation**.
- [ ] Inventory all RestTemplate beans and consumers with explicit contracts and owners.
- [ ] Phase A uses `RestClient.create(existingRestTemplate)`, without changing factory/pool/auth simultaneously.
- [ ] Map legacy methods to fluent APIs with the right terminal operations.
- [ ] Test 201/204/404/429/5xx statuses, ResponseEntity headers, and empty bodies.
- [ ] Test generic `List<T>`, URI templates, Unicode/encoding, and query params.
- [ ] Test migrated custom ResponseErrorHandlers and interceptors.
- [ ] Distinguish RestClient.retrieve vs exchange without dropping status policies.
- [ ] Configure and measure connect/read/pool/TLS/deadlines against a real HTTP server.
- [ ] Preserve business semantics for retries/idempotency/circuit breakers/rate limits.
- [ ] Security credentials, mTLS, and tracing/tenant propagation are neither lost nor leaked.
- [ ] Transport-specific contract tests exist for multipart/downloads/PATCH.
- [ ] Reuse client beans; never mutate shared templates during concurrent requests.
- [ ] Canary/rollback and before/after metrics use URI template tags.
- [ ] Never assume RestClient is async/reactive; choose WebClient when non-blocking is needed.
- [ ] Phase B removes RestTemplate beans only after all consumers migrate and pass tests.
- [ ] When upgrading to Spring 7/Boot 4, review imports/versions and that release's deprecation policy.

## 16. Self-Check Questions

**Question 1.** Does Spring Framework 7.0 remove RestTemplate?

**Answer:** No. Spring 7.0 deprecates RestTemplate in documentation; the Java `@Deprecated` annotation is planned for 7.1 and removal is planned for unscheduled 8.0.

**Question 2.** Can you migrate the API without immediately changing the connection pool?

**Answer:** Yes. Use `RestClient.create(restTemplate)` or `builder(restTemplate)` to reuse the request factory and related configuration.

**Question 3.** Does RestClient prevent MVC threads from blocking when the network is slow?

**Answer:** No. It is a synchronous client just like RestTemplate. WebClient provides the non-blocking HTTP model.

**Question 4.** Why should you avoid replacing `RestTemplate.execute(...,ResponseExtractor)` with `body(byte[].class)` for large files?

**Answer:** The latter buffers the entire body in RAM, risking memory pressure or OOM; design proper streaming and cleanup instead.

**Question 5.** Has `RestClient.get().retrieve()` already returned an Item?

**Answer:** Not yet. A terminal `body(Item.class)`, `toEntity`, or equivalent operation is required.

**Question 6.** Does `RestClient.exchange` apply retrieve's default status handlers?

**Answer:** No. The callback is responsible for handling status and body itself.

**Question 7.** When a 204 returns a null body, is the upstream broken?

**Answer:** No. 204 No Content having no body is valid.

**Question 8.** When copying a RestTemplate error handler, can you skip the 404 regression test?

**Answer:** No. Status handler order, per-request overrides, and retrieve/exchange behavior can differ, so testing is required.

**Question 9.** Is shadow-comparing two concurrent payment POSTs safe?

**Answer:** No. It can trigger side effects twice; use contract tests/mocks, idempotency, and controlled canaries.

**Question 10.** If you want a reactive HTTP client in WebFlux, choose RestClient or WebClient?

**Answer:** WebClient, because RestClient remains blocking even with its modern fluent syntax.

## 17. Official Reference Documentation

- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html): RestTemplate/RestClient/WebClient, converters, error handling.
- [Spring Framework — Migrating to RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html#migrating-to-restclient): two-phase guide and equivalence table.
- [Spring Framework 7.0 — Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes): documentation deprecation in 7.0 and planned @Deprecated in 7.1.
- [Spring Blog — The state of HTTP clients in Spring (2025-09-30)](https://spring.io/blog/2025/09/30/the-state-of-http-clients-in-spring/): migration and removal roadmap.
- [Spring Framework 6.2 — RestClient Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/client/RestClient.html): `create(RestTemplate)`, `builder(RestTemplate)`, retrieve/exchange.
- [Spring Framework 6.2 — RestTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/client/RestTemplate.html): template methods, thread configuration.
- [Spring Framework 6.2 — RestClient.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/client/RestClient.Builder.html): requestFactory/converters/interceptors/defaultStatusHandler.
- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html): RestTemplateBuilder/RestClient.Builder.
- [Spring Framework — MockRestServiceServer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html): testing RestTemplate and RestClient.Builder.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): credentials, authorized HTTP calls.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): non-blocking option when architecture changes.

**Conclusion:** `RestTemplate` is a legacy synchronous client that remains functional in Spring 6.2 and is not removed in Spring 7.0. Spring 7.0 announces deprecation in docs, 7.1 plans `@Deprecated`, and 8.0 plans removal. Choose **RestClient** for new synchronous HTTP code and **migrate service by service** using `RestClient.create(restTemplate)` to preserve infrastructure first, before refactoring builders and removing legacy beans. A solid migration preserves HTTP statuses, headers/bodies, error policies, timeouts/pools, auth, and side effects—not just syntax.
