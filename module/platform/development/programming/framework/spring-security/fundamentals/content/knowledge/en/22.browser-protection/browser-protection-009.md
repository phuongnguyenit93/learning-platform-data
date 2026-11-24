# Path normalization, HttpFirewall, and input limits

> Scope: Spring Security for **Servlet/Spring MVC applications** (Spring Boot 3.x, Java 17+). Part of the **Browser Protection** topic, focusing on how HTTP paths are interpreted, rejecting suspicious requests prior to authorization, and enforcing input limits at the proper layers.

## 1. Why care about request shape?

When a developer secures `/admin/**` yet a client sends a variant such as `/admin/../public`, `/admin//users`, `/admin;v=1/users`, or `/admin%2Fusers`, components along the request path may *interpret the path differently*:

- Browsers or clients may normalize URIs before sending them.
- Reverse proxies, WAFs, load balancers, and servlet containers may decode or reject different characters.
- Route matchers, security rule matchers, and controllers may observe differing path representations.
- Attackers intentionally exploit those discrepancies to reach unintended routes, bypass URL checks, or trigger processing errors.

The goal is to **inspect requests before authorization**, allow only consistently supported path forms, and **limit input size and structure** to reduce resource-abuse risks. `HttpFirewall` helps reject certain suspicious requests; it does not replace authorization checks, authentication, business input validation, or HTTP server size limits.

### Processing pipeline to visualize

```text
Client
  -> CDN / reverse proxy / gateway
  -> HTTP connector + servlet container (parse request, enforce HTTP limits)
  -> Spring Security Servlet FilterChainProxy
       -> HttpFirewall inspects / wraps request
       -> SecurityFilterChain: authentication, CSRF, authorization, ...
  -> DispatcherServlet -> Controller -> Service
  -> Response
```

A request rejected by a proxy/container may **never reach Spring Security**. A request rejected by `StrictHttpFirewall` may **never reach a controller**. Therefore, when observing error status codes, identify which layer actually rejected the request.

## 2. Understanding "path normalization" properly

A URL has distinct parts. In `https://example.test/app/api/products/42?sort=asc`, `/app` can be the `contextPath`, `/api/products/42` is the application path used for routing, and `sort=asc` is the query. `servletPath` and `pathInfo` are split by the servlet container; `queryString` is **not** part of the path matched by route security rules.

"Normalization" turns accepted representations into a consistent interpretation; "canonical form checking" **rejects** ambiguous representations instead of silently rewriting them. Across security boundaries, trying to fix paths after authorization can produce an interpretation different from what was authorized.

| Path variant attempted by client | Risk / point to understand |
| --- | --- |
| `/api/../admin` or `/api/./users` | `..` and `.` segments can alter the path after normalization. |
| `/api//users` | Repeated slashes can be handled differently across layers. |
| `/api/%2e%2e/admin` | Percent-encoded dots; behavior depends on decoding layers and config. |
| `/api%2Fadmin` | `%2F` is an encoded slash, potentially creating segment-splitting mismatches. |
| `/api%5Cadmin` | Backslashes may be treated as path separators at some layers. |
| `/api;v=1/admin` | Semicolons / path parameters can affect matchers and matrix variables. |
| `/api/%252e%252e/admin` | Repeated sequential decoding can change the string's meaning. |

This table describes **risks**, not a guarantee of one fixed HTTP code for every string. Characters may be rejected at the gateway, container, or firewall, and clients may normalize URIs before sending. **Never percent-decode twice by default**; every layer must agree on path and encoding policy.

**Crucial distinction:** `%2F` inside a *path* differs from `%2F` inside a *query parameter value or JSON body*. Do not jump from path-rejection policies to banning legitimate percent characters in body/query data.

## 3. Where does `HttpFirewall` sit and what does it do?

In Servlet applications, Spring Security uses `FilterChainProxy` to dispatch to `SecurityFilterChain` instances. `FilterChainProxy`'s `HttpFirewall` validates the request and can supply a request wrapper so security matchers see a consistently processed path. The default strategy is `StrictHttpFirewall`.

`StrictHttpFirewall` typically rejects:

1. Non-canonical paths or variants prone to matching discrepancies.
2. Dangerous characters/encodings such as semicolons, backslashes, URL-encoded slashes, encoded percent signs, or NUL bytes under default rules.
3. HTTP methods outside the allowlist; by default `DELETE`, `GET`, `HEAD`, `OPTIONS`, `PATCH`, `POST`, and `PUT` are permitted.
4. Header names, header values, and parameter names containing control characters or characters disallowed by default rules.
5. Hosts or parameter values failing predicates **if the application configured custom predicates**. By default, it does not perform full validation of all parameter values or host allowlists.

When a check fails, `StrictHttpFirewall` throws `RequestRejectedException`. In standard setups, the request receives **400 Bad Request** via the corresponding handler, though proxies/containers may block earlier with a different status. This is not `AccessDeniedException` from lacking user permissions; **400 and 403 carry different meanings**.

Spring Security recommends rejecting non-canonical paths rather than writing your own "normalizer" to rewrite arbitrary URLs. If a special structure must be supported, verify protocol requirements, container parsing, and security impact before relaxing a rule.

### Three defense layers with distinct responsibilities

| Layer | Question to answer | Typical tools |
| --- | --- | --- |
| HTTP / gateway / container | Is the request well-formed, within size limits, and safely parsed? | HTTP parser, proxy limits, Tomcat/Jetty settings |
| Firewall / security | Are path/method/headers trustworthy and is the caller authorized for the resource? | `StrictHttpFirewall`, `SecurityFilterChain`, `@PreAuthorize` |
| Input / business | Is the data valid in type, length, format, and business permission? | Jakarta Bean Validation, business checks, parameterized queries |

Do not use a single regex in a controller as a substitute for all three layers.

## 4. Safe Spring Security configuration

With Spring Boot 3.x / Spring Security 6.x, start from the default `StrictHttpFirewall`. Customize only when there is a clear requirement. The example below illustrates an app permitting only `GET`, `HEAD`, `POST`, and `OPTIONS` at the firewall layer while requiring authentication by default for paths outside `/public/**`.

```java
package com.example.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.firewall.StrictHttpFirewall;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    StrictHttpFirewall httpFirewall() {
        StrictHttpFirewall firewall = new StrictHttpFirewall();
        firewall.setAllowedHttpMethods(
            List.of("GET", "HEAD", "POST", "OPTIONS")
        );
        return firewall;
    }
}
```

This is **configuration code inside a Spring Boot project with Spring Security dependencies**, not a standalone Java file to run with `java SecurityConfig`. The `httpFirewall` bean is picked up by Spring Security for the filter chain; `SecurityFilterChain` still defines **who** has access. In this example, `PUT`, `PATCH`, and `DELETE` requests are rejected by the firewall even if a controller maps them; that is an **illustrative policy**, unsuitable for every REST API. When using `OPTIONS` for CORS, proper CORS config is still necessary; the firewall only permits the HTTP method rather than authorizing cross-origin callers. CSRF remains enabled per `HttpSecurity` defaults in this example.

To keep default HTTP methods and path rules, **omit the `httpFirewall` bean altogether**. That is usually safer and lower-maintenance. If restricting methods, inventory all live routes, logout, uploads, APIs, and health checks.

### Why think carefully before `setAllowSemicolon(true)`?

Spring MVC can use *matrix variables* like `/products;color=red`. `StrictHttpFirewall` blocks semicolons by default because containers and matchers can interpret path parameters differently. Allowing semicolons changes your **attack surface**:

```java
@Bean
StrictHttpFirewall httpFirewall() {
    StrictHttpFirewall firewall = new StrictHttpFirewall();
    firewall.setAllowSemicolon(true); // Only after evaluating matrix variable requirements
    return firewall;
}
```

This is a **separate replacement example** for the identically named bean above—do not declare both beans in one config. Before enabling: verify consistent handling across proxy, container, MVC routing, and security matchers; verify permissions on all path variants. Similarly, avoid enabling `setAllowUrlEncodedSlash(true)`, `setAllowBackSlash(true)`, `setAllowUrlEncodedPercent(true)`, or `setUnsafeAllowAnyHttpMethod(true)` globally just to "silence" 400 errors. If a client sends malformed URIs, fix the client first.

### Host, header, and parameter restrictions

`StrictHttpFirewall` provides `setAllowedHostnames(Predicate<String>)`, `setAllowedHeaderNames(Predicate<String>)`, `setAllowedHeaderValues(Predicate<String>)`, `setAllowedParameterNames(Predicate<String>)`, and `setAllowedParameterValues(Predicate<String>)`. These predicates fit small, stable, well-tested policies. For example, when traffic hits a single known hostname directly, you might *consider* an explicit host allowlist. However, proxies, multiple domains, local tests, and health checks complicate that condition; verify the exact values the app actually receives before applying it.

**Never set `value -> true` predicates on headers/parameters just to avoid rejections:** doing so disables default safety checks. `Host` and `Forwarded`/`X-Forwarded-*` headers also require a *trusted proxy* policy at the gateway; never trust arbitrary client-sent headers. Nor should value predicates be confused with **byte-size** limits on headers or bodies.

## 5. Input limits: enforce at the right layer

The firewall primarily handles request shape and matching safety, not byte ceilings for bodies, JSON, file uploads, or field counts. Size limits must span **gateway → container → parser → controller/service**.

| Input type | Where to limit | Example / note |
| --- | --- | --- |
| Request line, URI, headers | Proxy and HTTP connector | `server.max-http-request-header-size` caps headers; exact accounting varies by server, and includes the request line on Tomcat. |
| `application/x-www-form-urlencoded` forms | Servlet container | `server.tomcat.max-http-form-post-size` applies to form POSTs in Tomcat, not as a byte cap for JSON requests. |
| `multipart/form-data` uploads | Multipart resolver / container / gateway | `spring.servlet.multipart.max-file-size` and `max-request-size` cap individual files and total multipart size. |
| JSON/text/XML bodies | Gateway or size-limiting body middleware, plus validation | Do not assume `max-http-form-post-size` or multipart settings cap JSON. Reject oversized bodies *before* parsing/buffering completely. |
| Field counts, JSON depth, multipart part counts | Parser / container / specialized settings | Prevents parameter pollution and parser/resource exhaustion; available settings vary by server and version. |
| Field values, IDs, page sizes, filenames | Controller / service | Bean Validation, format checks, allowed-value lists, query caps. |
| Request rate / bursts | API gateway / rate limiter | Rate limiting is separate from the firewall and size caps. |

Example `application.yml` for a Spring Boot app using **embedded Tomcat** with small uploads:

```yaml
server:
  max-http-request-header-size: 16KB
  tomcat:
    max-http-form-post-size: 256KB

spring:
  servlet:
    multipart:
      max-file-size: 2MB
      max-request-size: 3MB
```

These numbers are **policy examples**, not universal recommendations. Pick limits based on real requirements, legitimate session/cookie overhead, file types, field counts, and upstream gateway limits. When swapping Tomcat for Jetty/Undertow or using WebFlux, property names and semantics may differ. For `max-http-request-header-size`, Spring Boot docs note **Tomcat counts the request line, header names, and header values together**, whereas Netty applies the limit per header; do not treat them as identical.

If serving JSON APIs, configure **max request body** at the ingress/proxy or use a streaming body reader with early cutoff, then validate structure post-parse. Relying on `Content-Length` alone fails for streaming/chunked transfers, missing headers, and intermediaries. Any body-reading filter must remain compatible with Servlet processing, multipart handling, and controller body streams; avoid writing custom byte-counting wrappers if the gateway/container already provides suitable limits.

### Controller-level validation example

Required Boot project dependencies: `spring-boot-starter-web`, `spring-boot-starter-validation`, and `spring-boot-starter-security` (or existing security setup). The DTO uses `jakarta.validation`; the max lengths below constrain **post-parse values**, not HTTP byte sizes.

```java
package com.example.web;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record CreatePostRequest(
    @NotBlank @Size(max = 100) String title,
    @NotBlank @Size(max = 2000) String content
) {}

@RestController
@RequestMapping("/api/posts")
class PostController {

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    String create(@Valid @RequestBody CreatePostRequest request) {
        // Demo accepts valid input; persistence service omitted.
        return "accepted";
    }
}
```

When input violates `@NotBlank`/`@Size`, Spring MVC normally responds **400** with `@RequestBody` validation errors. Still, an oversized JSON request can consume memory/CPU **before** Bean Validation runs if no HTTP/parser-level cap exists. For file uploads, additionally validate actual content type, user permissions, filename, and storage location—not just extension or client-sent `Content-Type`.

## 6. URL authorization must match the real resource

Suppose you define:

- `/public/**` is public.
- `/admin/**` requires `ROLE_ADMIN`.
- All other paths require authentication.

If one layer treats `/admin;anything/users` as matching `/admin/**` while another layer treats it as a different path, matching diverges. The firewall reduces these dangerous discrepancies; the **catch-all `anyRequest().authenticated()` rule is still necessary**, and sensitive resources should also enforce service-level authorization via method security.

Distinguish clearly:

- `permitAll()`: requests still pass through the Spring Security filter chain and firewall; only authentication is waived for that specific rule.
- `web.ignoring()` or requests bypassing the filter chain: can bypass multiple Spring Security defense layers; use only when fully understood, never as a quick fix for firewall 400s.
- Multiple `SecurityFilterChain` beans: check `securityMatcher` and chain order; ensure no path slips outside protection due to unmatched rules.

If handling **server filesystem paths** (e.g., downloading `/download/{name}`), that is an additional concern beyond URL authorization. Never use `Path.normalize()` alone to "sanitize" URLs. After checking resource authorization, resolve the filesystem path against the allowed base directory, guard against traversal and symlinks per your storage model, and never pass client-supplied filenames straight into unchecked I/O calls.

## 7. Real-world testing from client to controller

Test at least at two levels: **unit/integration tests for app rules** and **end-to-end through the same proxy/container used in production**. Spring MVC `MockMvc` is valuable for rule testing, yet does not fully simulate connector URI parsing or proxy transformations.

Start the properly configured Boot app and probe with `curl`, using `--path-as-is` so `curl` does not strip dot-segments before sending:

```bash
# Normal request (baseline for authentication/authorization)
curl -i http://localhost:8080/public/info

# Semicolon in path: default StrictHttpFirewall usually blocks if reached
curl -i --path-as-is 'http://localhost:8080/public;v=1/info'

# Path with dot-segment: may be rejected by container or firewall
curl -i --path-as-is 'http://localhost:8080/admin/../public/info'

# Encoded slash: outcome depends on both connector and firewall
curl -i --path-as-is 'http://localhost:8080/admin%2Fusers'

# TRACE method rejected by default StrictHttpFirewall if reached
curl -i -X TRACE http://localhost:8080/public/info

# JSON violating value constraints: handled by Bean Validation layer
curl -i -H 'Content-Type: application/json' \
  -d '{"title":"","content":"test"}' \
  http://localhost:8080/api/posts
```

**Interpreting results:** do not hardcode every probe to expect 400. A container may return 400 before the firewall, and a valid route may return 302 to login, 401, 403, or 404 depending on authentication/authorization/routing config. When automating, assert **no unauthorized access** and record *which layer handled it*, then add exact expectations for your verified stack. Never send "attack" probes to services outside your authorized testing scope.

### Minimum test matrix

| Check | Security expectation |
| --- | --- |
| Valid path to public route | Not blocked by firewall due to path; outcome depends on route. |
| Valid path to admin route, under-privileged user | No admin data returned; authentication/authorization handles it. |
| `..`, `//`, semicolon, encoded slash in path | Never becomes unauthorized access; rejecting layer depends on stack. |
| Method outside allowlist (e.g., `TRACE`) | Controller does not execute; blocked at HTTP/firewall layer. |
| Oversized header | Rejected early before app processing; exact HTTP code depends on server. |
| Multipart exceeding `max-file-size` or `max-request-size` | Upload rejected; oversized data not persisted. |
| Byte-valid JSON with oversized field | Rejected by validation / business handler. |
| JSON exceeding gateway body cap | Cut off early without unbounded deserialization. |
| Paths through proxy/ingress vs direct access | Identical access policy; no bypass via rewrite/decoding. |

When diagnosing, log **status code, rejecting component, correlation ID, logical route, and violation category**. Avoid logging full URIs, headers, or bodies containing tokens, cookies, emails, or personal data. For `RequestRejectedException`, configure sensible log levels and monitoring to spot unusual spikes without treating every 400 as an active attack.

## 8. Common implementation mistakes

1. **Assuming the firewall safely "fixes URLs":** `StrictHttpFirewall` prefers to *reject* anomalous paths. If an integration unexpectedly emits `//` or `%2F`, investigate the source and decoding layers.
2. **Turning on all `allow*` options to eliminate errors:** removes guards against path ambiguity. Relax a rule only with clear justification, tests, and impact review.
3. **Confusing route matchers with business permission checks:** `/orders/{id}` is only an entry route; the caller must still be authorized for that specific `id`.
4. **Assuming `@Size` stops huge payloads:** Bean Validation typically runs after parsing; enforce byte-size caps at earlier layers.
5. **Using form/multipart limits to assume JSON caps:** these are distinct payload types requiring separate limits.
6. **Relying solely on `Content-Length`:** streaming/chunked requests may have no upfront fixed length.
7. **Blindly trusting `X-Forwarded-*`, `Host`, or client-side validation:** only trusted proxy setups and server-side validation provide security.
8. **Testing with `curl` without preserving raw paths and assuming the firewall worked:** clients may normalize URIs first; use `--path-as-is` and inspect real wire requests.
9. **Arbitrarily bypassing the Spring Security filter chain for "static/public routes":** reduces security filter coverage; prefer `permitAll()` inside the chain.
10. **Conflating 400, 401, 403, 404, and 413/414/431:** they can originate from different layers; trace the request path and access logs before changing config.

## 9. Pre-production checklist

- [ ] Public, authenticated, and admin routes are identified, with a catch-all default policy for unmatched requests.
- [ ] Default `StrictHttpFirewall` is retained unless a verified requirement demands changes; any exceptions and regression tests are documented.
- [ ] Handling of encoded slashes, backslashes, semicolons, and duplicate slashes is aligned between gateway and servlet container.
- [ ] Request line/header limits are configured at the HTTP server/proxy and tested against valid cookies/sessions.
- [ ] Appropriate caps are configured for forms, multipart uploads, and JSON bodies, plus field count/depth limits where needed.
- [ ] Bean Validation is applied to DTOs, resource-level authorization is enforced in services, and uploaded files are handled safely.
- [ ] Tests cover happy paths, malformed inputs, ambiguous URIs, unsupported methods, and oversized payloads.
- [ ] Rejecting layers are observable, logs are scrubbed of sensitive data, and errors never leak stack traces to clients.

### Self-check questions

1. Why can it be dangerous if a proxy, container, and Spring Security decode `%2F` differently?
2. Does default `StrictHttpFirewall` **reject** anomalous paths or rewrite all paths and let them through?
3. Which use case does `setAllowSemicolon(true)` enable, and what risks must be tested?
4. Why is `spring.servlet.multipart.max-request-size` not a JSON size limit?
5. Why does `/orders/{id}` still require checking ownership/permissions on the order object after passing the firewall?

**Answer hints:** (1) one layer may authorize one path while another routes to a different path; (2) prefers rejecting; (3) matrix variables, risking route/matcher mismatches; (4) multipart differs from JSON and is parsed differently; (5) URL access rules do not prove permission for a specific resource ID.

## Official references for version verification

- Spring Security — HttpFirewall: https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html
- Spring Security — StrictHttpFirewall API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/firewall/StrictHttpFirewall.html
- Spring Boot 3.3 — Common Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring MVC — @RequestBody and Bean Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
