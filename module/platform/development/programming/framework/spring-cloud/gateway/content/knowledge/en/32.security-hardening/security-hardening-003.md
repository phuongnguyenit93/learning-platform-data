# Handling Encoded Paths, Path Traversal, and Inconsistent Normalization in Spring Cloud Gateway

In a microservices architecture, a request may traverse **CDN/WAF → ingress → Spring Security → Spring Cloud Gateway route predicate/filter chain → HTTP client → backend**. These layers can parse, decode, and normalize URLs under different rules. One layer treats `%2F` as data within a path segment, while another turns it into a `/` separator; `%2e%2e` can become `..`; semicolons, double slashes, backslashes, or Unicode can also change meaning along the way.

This lesson belongs to the **Security Hardening** chapter of the **SPRING_CLOUD_GATEWAY** module, focusing on **handling encoded paths, path traversal, and inconsistent normalization**. This topic relates directly to route predicates, the filter chain, path/header transformations, authentication, rate limiting, circuit breakers, retries, TLS, service discovery, and observability: if components use **different representations of the same URL**, a request deemed public at the Gateway might point to a privileged resource on the backend.

**Objectives:**

1. Distinguish **request-target, raw path, decoded path, normalized path, URI template variables**, and effective downstream path.
2. Recognize encoded slashes, encoded dot segments, double encoding, backslashes, semicolons, duplicate slashes, Unicode normalization, and parser limits.
3. Understand why a **Path predicate match is not equivalent to authorization**.
4. Design **strict grammars and reject ambiguous inputs**, avoiding repeated decoding or normalization.
5. Test across **ingress, Gateway, and backend**, not just a single filter test.
6. Apply WebFlux filters/Java URI builders, distinguish Servlet Web MVC/ProxyExchange, and build a deployment checklist.

> **Scope:** Code examples focus on **Gateway Server WebFlux**. Server Web MVC uses Servlet/WebMvc.fn, and ProxyExchange uses controller-style proxying. Handling of encoded slashes/semicolons/invalid UTF-8 depends on the HTTP server, framework, ingress, and version. Never assume one fixed default across all runtimes. Unusual URLs shown are **defensive test cases in authorized environments**.

## 1. Core Risk: Checking Path A While Executing Path B

Suppose Gateway has `/api/public/**` and `/api/admin/**`. The public route allows anonymous traffic; the admin route requires `SCOPE_admin`. The backend also hosts unexposed internal endpoints.

~~~mermaid
flowchart LR
    C["Client request-target"] --> W["CDN / WAF"]
    W --> I["Ingress / proxy"]
    I --> S["Spring Security"]
    S --> R["Gateway predicates"]
    R --> F["StripPrefix / RewritePath"]
    F --> B["Backend router + authorization"]
    B --> D["Protected resource"]
~~~

A mismatch to guard against:

1. Ingress permits the request based on **raw path prefix**.
2. A subsequent hop decodes `%2e%2e` into `..` and resolves dot-segments.
3. Security matchers or Gateway filters select a route using a different representation.
4. The final backend sees a path inside a privileged namespace.
5. If the backend skips object-level authorization assuming Gateway already checked, data can be exposed.

**This is a threat model, not a claim that every product transforms paths identically.** You must test your exact stack and version.

**Security invariant:** Normalization, decoding, rewriting, or proxying must never grant a caller access to a **final resource** they are not authorized to access.

## 2. URI Structure: Path Differs from Query and Fragment

~~~text
https://api.example.test/api/items/A%2FB?lang=vi&sort=asc#section
|_____scheme______| |__authority__| |_____path_____| |____query____| fragment
~~~

| Component | Example | What matters |
|---|---|---|
| Scheme | `https` | TLS/forwarded scheme |
| Authority/Host | `api.example.test` | Virtual host, SNI, proxy trust |
| **Raw path** | `/api/items/A%2FB` | Percent-encoded representation |
| Segments | `api`, `items`, `A%2FB` before structural change | Slash acts as delimiter |
| Decoded segment | `A/B` if `%2F` is decoded | May contain reserved characters |
| Normalized path | Form after applying `.`/`..` and separator rules | May point to a different resource |
| Query | `lang=vi&sort=asc` | Not part of path; may contain PII |
| Fragment | `#section` | Usually client-side only, not sent in HTTP request-target |

In standard HTTP, fragments are not sent by clients to origin servers; **never use fragments as authorization rules**.

### Raw Path in Spring Is Not Raw Bytes from the Client

In WebFlux, `exchange.getRequest().getURI().getRawPath()` returns the raw path of the **URI object received by Java**. It **does not prove** the client's request line carried the exact same bytes: CDN, ingress, or Netty parsers may have rejected, decoded, or normalized it beforehand.

When comparing hops, use edge/Gateway/backend telemetry with restricted access and masked sensitive data.

## 3. Percent-Encoding and Reserved Characters

Percent-encoding represents an octet via `%HH`. Key cases:

| Input | Corresponding decoded value | Risk |
|---|---|---|
| `%2F` or `%2f` | `/` | Adds a path separator |
| `%5C` | Backslash | Treated as a separator by some backends/filesystems |
| `%2E` | `.` | Forms dot segments |
| `%3B` | `;` | Matrix/path parameters |
| `%3F` | `?` | Confuses path/query boundary if decoded prematurely |
| `%23` | `#` | Confuses fragment delimiter |
| `%25` | `%` | Double encoding |
| `%00` | NUL | Parser/logging/native handling mismatch |
| `%20` | Space | Divergent URI encoding/normalization |
| `%2B` | `+` | Easily confused with form encoding |

Under RFC 3986, **unreserved** characters include alphanumerics, `-`, `.`, `_`, `~`; many characters like `/`, `?`, `#`, `;`, `:`, `@` are **reserved** and can alter URL structure when decoded early.

`%2f` and `%2F` represent the same byte; never write a filter blocking only one hex case. Invalid sequences like `%ZZ` and incomplete `%2` must have a rejection policy at the appropriate ingress point.

### Do Not Use URLDecoder as a Path Sanitizer

`java.net.URLDecoder` is meant for `application/x-www-form-urlencoded`, which converts `+` to space. Never use it to decode an entire raw URI path and consider it clean:

~~~java
// COUNTEREXAMPLE: decoding raw path manually and treating it as safe.
String decoded = java.net.URLDecoder.decode(
    clientSuppliedPath,
    java.nio.charset.StandardCharsets.UTF_8);
~~~

Use validation based on **domain identifiers**, an appropriate URI/path segment builder, and authorization on the final resource.

## 4. Double Encoding and the Risk of Repeated Decoding

~~~text
Raw:           /api/items/A%252FB
Decode pass 1: /api/items/A%2FB
Decode pass 2: /api/items/A/B

Raw:           /api/public/%252e%252e/admin
Decode pass 1: /api/public/%2e%2e/admin
Decode pass 2: /api/public/../admin
~~~

Risks typically emerge in three situations:

- A WAF decodes once; the backend receives the path and decodes again.
- The framework already decoded `@PathVariable`, yet code invokes `URLDecoder` a second time.
- A filter constructs an outbound URI from raw/decoded strings, and an HTTP client or proxy subsequently re-encodes/normalizes.

**Never decode in a loop until no `%` remains.** Doing so can change path semantics with every iteration. For APIs that do not need percent-encoded paths, rejecting `%` outright is much easier to verify; for APIs needing encoding, define **single-pass decoding and a canonical representation** explicitly.

## 5. Dot-Segments, Traversal, and URI.normalize()

Variants to test at the perimeter and backend:

~~~text
/api/public/../admin/config
/api/public/%2e%2e/admin/config
/api/public/.%2e/admin/config
/api/public/%2e./admin/config
/api/public/%252e%252e/admin/config
/api/public/..%2fadmin/config
/api/public/%2e%2e%2fadmin/config
~~~

One server may reject before a Gateway route matches; another layer may pass it through unchanged; the backend may decode further. **Do not assume exact behavior without testing your specific version.**

`java.net.URI.normalize()` is not an all-purpose security control: it does not authorize resources, check symlinks/filesystem containment, decode every parser's encoded dot forms, or know what Gateway `RewritePath` turned the path into.

**Normalizing is not sanitizing.** With a path grammar that disallows dot segments, **reject** them instead of trying to rewrite every string into another URL.

## 6. Encoded Slash and Backslash: One ID or Two Segments?

`/api/items/A%2FB` can be interpreted as an ID `A/B` inside a single segment, or as two segments `A` and `B`. `%5C` can carry separator semantics on some backends/filesystems, especially when applications interact with Windows paths.

| ID type | Recommended contract |
|---|---|
| Integer | `[0-9]+` with length cap |
| UUID | Parse/validate canonical UUID |
| ASCII slug | `[A-Za-z0-9_-]+` |
| Object key containing slash | Opaque ID or body/query per contract; test encoding |
| Client-supplied file path | Avoid; map server-side ID → file |
| Unicode slug | Valid UTF-8 and explicit normalization |

**Never replace backslashes with slashes to "fix" input**, as that can shift a path to a completely different resource.

## 7. Double Slash, Trailing Slash, and Case Sensitivity

~~~text
/api/admin/config
/api//admin/config
//api/admin/config
/api/admin/config/
/API/admin/config
/api/admin//config
/api/admin/.//config
~~~

These paths are **not automatically equivalent**. An ingress may collapse double slashes; Security/route matchers may treat trailing slashes differently from the backend; resource IDs may be case-sensitive.

- If duplicate slashes are unneeded → reject them at an appropriate trusted boundary.
- If trailing slashes are valid, test the **same authorization policy** on both forms.
- Never blindly lowercase the entire path.
- Never add arbitrary 301/308 redirects for requests with bodies/side effects.
- Verify both the **pre-rewrite path** and the **effective backend path**.

## 8. Semicolons, Matrix Parameters, and Encoded Semicolons

~~~text
/api/items/42;color=red
/api/items/42;role=admin
/api/items/42%3Brole%3Dadmin
/api/items/42;v=1/details
~~~

Semicolons can represent **matrix/path parameters**. One framework may strip `;...` when matching paths, while another retains it inside a resource ID variable.

If matrix variables are unsupported, an easily verifiable policy is rejecting **literal `;` and encoded `%3B`**. If supported, you must test across the full chain: **ingress parser → Gateway route/security matcher → backend router → authorization**. Do not write a rule banning only `";role=admin"` and assume all bypasses are stopped.

## 9. Unicode Normalization, UTF-8, and Lookalike Characters

- NFC/NFD: accented characters can have multiple code point sequences.
- Compatibility forms such as fullwidth characters.
- Homoglyphs across different scripts.
- Unicode case folding differs from ASCII lowercasing.
- Invalid/overlong UTF-8 may be rejected or substituted differently across parsers.

If the business **only needs UUIDs/numbers**, enforce an ASCII grammar and disallow encoded Unicode paths. If Unicode slugs are truly needed:

1. Enforce strictly valid UTF-8.
2. Pick a domain-appropriate normalization form (typically consider NFC).
3. Normalize at **one deterministic point**.
4. Use the exact same canonical ID for storage lookup and authorization.
5. Test NFC/NFD, Unicode percent-encoding, and malformed byte sequences.
6. Do not apply NFKC without evaluating collisions and business semantics.

Unicode normalization **never replaces resource-level authorization**.

## 10. Forwarded Headers, Host, and Protocol Translation

Other sources besides the path can change effective routing:

| Value | Risk |
|---|---|
| `Host` / HTTP/2 `:authority` | Virtual host selection/SNI |
| `Forwarded`, `X-Forwarded-Proto` | Spoofed scheme/host |
| `X-Forwarded-Prefix` | Public base path vs internal path mismatch |
| `X-Original-URL`, `X-Rewrite-URL` | Extension headers affecting paths in certain proxies |
| `Location` redirect | Client resolves new URI |
| HTTP/2 → HTTP/1.1 | `:path`/request-target translation |

Trust forwarded headers only when generated and overwritten by a **trusted ingress/proxy**; never let clients select backend hosts or tenants via these headers.

HTTP request smuggling involves HTTP framing (`Content-Length`/`Transfer-Encoding`) and is a separate bug class. It can compound path confusion, but cannot be solved with path regexes alone.

## 11. Path Representations in Gateway Server WebFlux

Spring Cloud Gateway Server WebFlux exposes path representations at multiple points:

- `exchange.getRequest().getURI().getRawPath()`: raw path of the current URI object.
- `exchange.getRequest().getPath()`: `RequestPath` provided by Spring WebFlux, with parsed segments.
- `Path` route predicate results and URI template variables: data from route matching.
- `StripPrefix`, `RewritePath`, `SetPath`, `PrefixPath`: path transformations before downstream routing.
- Target URI/exchange attributes in Gateway routing: values that can change during the filter lifecycle.

**Do not treat all of these as the same string.** Security checks paths at one stage; Gateway rewrites at another; the backend parses the final URI sent to it again.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant I as Ingress
    participant S as Security WebFilter
    participant R as Gateway Path predicate
    participant F as Path filters
    participant B as Backend authorization
    C->>I: Raw request-target
    I->>S: Parsed / perhaps normalized path
    S->>S: Authentication & authorization
    S->>R: Route match
    R->>F: StripPrefix / RewritePath / SetPath
    F->>B: Effective downstream path
    B->>B: Final resource authorization
    Note over S,B: Permissions must hold across every path transformation
~~~

### PathPattern and Segment Boundaries

Spring Framework provides path parsing/matching abstractions that model segments structurally. However, **never assume Netty, ingress, Servlet, and backend routers always interpret encoded slashes identically**. To be sure, test end-to-end with your real versions and configurations.

## 12. StripPrefix and RewritePath Can Shift Security Namespaces

Gateway Server WebFlux example in the new configuration namespace:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-public
              uri: http://catalog.internal:8080
              predicates:
                - Path=/public/catalog/**
              filters:
                - StripPrefix=1
~~~

For `GET /public/catalog/items/42`, `StripPrefix=1` yields outbound path `/catalog/items/42` per the normal contract.

**Problem:** If the backend also hosts `/catalog/admin/**` without object-level authorization, a broad public route can accidentally expose it. Combined with inconsistent normalization, the risk escalates.

| Setting | Risk |
|---|---|
| `Path=/**` | Catch-all may expose unintended backend endpoints |
| `StripPrefix` on broad routes | Resulting path drops the prefix Security inspected |
| Broad `RewritePath` regex capture | Capture may contain encoded delimiters/dots |
| `SetPath` with template vars | User input can shape the outbound path |
| `PrefixPath` alongside ingress rewrites | Double-prefixing, security matcher mismatch |
| Unvetted dynamic routes | Creates URIs/paths into internal backends |

Maintain a **table of expected incoming path → matched route → outgoing path → backend operation** for sensitive routes, including encoded variants.

## 13. Building Outbound URIs Safely Using Path Segments

Counterexample:

~~~java
// Avoid: raw slug can contain "/", "..", "%2F", or "?..."
String target = "https://catalog.internal/items/" + clientSuppliedSlug;
~~~

For a slug API permitting only ASCII letters/digits, underscores, and hyphens:

~~~java
import java.net.URI;
import org.springframework.web.util.UriComponentsBuilder;

static URI itemUri(String slug) {
    if (slug == null || !slug.matches("[A-Za-z0-9_-]{1,64}")) {
        throw new IllegalArgumentException("invalid slug");
    }

    return UriComponentsBuilder
        .fromUriString("https://catalog.internal")
        .pathSegment("items", slug)
        .build()
        .encode()
        .toUri();
}
~~~

A URI builder separates **path segments** instead of concatenating raw strings, while validation enforces domain rules on the slug. **Do not treat a URI builder as authorization**; the backend must still verify resource owner/tenant, and origin allowlisting must stay intact.

For UUIDs, numbers, or Unicode IDs, define matching grammars. For raw URLs from clients, never call `proxy.uri(rawUrl)` or populate scheme/host from free-form input: beyond path bypasses, that introduces SSRF.

## 14. "Reject Ambiguous" Policy at the Trust Boundary

For simple API paths, **accepting a small, explicit path language** is usually far easier to verify than trying to "repair" paths into canonical form.

Under the contract, you can reject:

- `%` in raw paths if the API does not use encoded paths;
- `.`/`..` or encoded variants;
- `//`, raw backslashes, `%2F`, and `%5C`;
- `;` and `%3B` if matrix variables are unsupported;
- Invalid percent escapes, invalid UTF-8/NUL;
- Excessively long paths or too many segments;
- Unicode IDs if the domain accepts ASCII only.

**Do not blindly enforce this globally on an API that legitimately supports percent-encoded Unicode or filenames with dots** without a migration plan. If business needs require those characters, establish single-pass parse/decode rules and compare canonical values at every boundary.

**Rejecting differs from normalizing:** For ambiguous representations, returning 400 Bad Request is typically easier to prove secure than silently rewriting to another path.

## 15. Illustrative WebFlux WebFilter for Strict Raw-Path Grammar

Suppose a lab Gateway accepts only paths like `/`, `/api/orders/42`, `/api/items/item_01`, `/actuator/health`. Every segment contains only ASCII letters/digits/underscores/hyphens, with no encoded characters or dots.

~~~java
package example.gateway.security;

import java.util.regex.Pattern;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public final class StrictRawPathWebFilter implements WebFilter {

    // "/" or a sequence of ASCII path segments separated by single "/".
    private static final Pattern SAFE_RAW_PATH =
        Pattern.compile("^(?:/|/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*/?)$");

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        String rawPath = exchange.getRequest().getURI().getRawPath();

        if (rawPath == null
                || rawPath.length() > 2048
                || !SAFE_RAW_PATH.matcher(rawPath).matches()) {

            exchange.getResponse().setStatusCode(HttpStatus.BAD_REQUEST);
            return exchange.getResponse().setComplete();
        }

        return chain.filter(exchange);
    }
}
~~~

**Important limitations of this example:**

- The filter **neither decodes nor rewrites**; it strictly rejects or forwards to the chain.
- The regex forbids `%`, dots, semicolons, raw backslashes, double slashes, and Unicode **if they still appear in the representation the filter sees**.
- Ingress or the HTTP server decoder may process the URL **before the WebFilter**; a Java filter is not the sole defense layer.
- `@Order(Ordered.HIGHEST_PRECEDENCE)` expresses intent to run early; verify actual ordering relative to Spring Security.
- It does not validate queries, Host, authentication/authorization, bodies, or backend resources.
- It will reject legitimate paths like `/favicon.ico`, `/.well-known/**`, or Unicode slugs; use only for an API grammar matching these assumptions.
- If Actuator runs on a separate management port/server, a WebFilter on the application port **does not automatically protect Actuator**.

This is an **illustrative policy**, not a universal canonicalizer for every Spring Cloud Gateway app.

## 16. Unit Testing StrictRawPathWebFilter

Use Spring MockWebExchange and Reactor Test to prove the downstream chain is not called:

~~~java
package example.gateway.security;

import java.net.URI;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class StrictRawPathWebFilterTest {
    private final StrictRawPathWebFilter filter =
        new StrictRawPathWebFilter();

    @Test
    void acceptsSimplePathAndInvokesNext() {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/api/orders/42"));
        AtomicBoolean nextCalled = new AtomicBoolean();
        WebFilterChain next = ex -> {
            nextCalled.set(true);
            return Mono.empty();
        };

        StepVerifier.create(filter.filter(exchange, next))
            .verifyComplete();

        assertTrue(nextCalled.get());
    }

    @Test
    void rejectsEncodedTraversalBeforeNext() {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get(
                URI.create("/api/%2e%2e/admin")));
        AtomicBoolean nextCalled = new AtomicBoolean();
        WebFilterChain next = ex -> {
            nextCalled.set(true);
            return Mono.empty();
        };

        StepVerifier.create(filter.filter(exchange, next))
            .verifyComplete();

        assertFalse(nextCalled.get());
        assertEquals(HttpStatus.BAD_REQUEST,
            exchange.getResponse().getStatusCode());
    }
}
~~~

**Unit tests do not prove Netty/ingress parsers preserve encoded paths verbatim.** You need integration tests through the real HTTP server and ingress.

### Inputs Corresponding to the Example Regex

| Raw path | Expected when the WebFilter actually sees this string |
|---|---|
| `/api/orders/42` | Allow |
| `/api/orders/42/` | Allow trailing slash |
| `/api//orders/42` | Reject |
| `//` | Reject (root must not have double slash) |
| `/api/../admin` | Reject |
| `/api/%2e%2e/admin` | Reject |
| `/api/%252e%252e/admin` | Reject |
| `/api/%2Fadmin` | Reject |
| `/api/%5cadmin` | Reject |
| `/api/orders;v=1` | Reject |
| `/api/café` | Reject under ASCII policy |
| `/favicon.ico` | Reject; requires another grammar if needed |

Do not test only HTTP 400: prove **the backend sees zero side effects and protected resources are never invoked**.

## 17. Spring Security WebFlux Authorizing by Path and Identity

Gateway Server WebFlux commonly uses `SecurityWebFilterChain`. Illustrative **stateless Bearer JWT** API configuration:

~~~java
package example.gateway.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class GatewaySecurityConfiguration {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {

        return http
            // Illustrative for stateless bearer APIs; CSRF differs if using cookies.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/actuator/health").permitAll()
                .pathMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_admin")
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Running this requires Spring Security OAuth2 Resource Server/JWT dependencies, issuer/JWK decoders, audience/scope checks, and real testing; copying the class **does not mean production security is fully configured**.

### Four Limitations to Remember

1. `pathMatchers` inspects paths **at the time Security executes**, not necessarily the path after Gateway rewrites.
2. Spring Security does not know which **resource/tenant** the backend will map the path to.
3. Configuring `permitAll` on a public route must never be used to skip **backend object-level authorization**.
4. CSRF should only be disabled when the API genuinely uses an appropriate stateless bearer model; browser cookie sessions require CSRF protection.

Even if both users A and B have valid JWTs, the backend must still verify whether they have permission for the **specific object**.

## 18. Differences in Gateway Server Web MVC and ProxyExchange

| Aspect | Server WebFlux | Server Web MVC | ProxyExchange MVC/WebFlux |
|---|---|---|---|
| Request API | `ServerWebExchange` / `ServerHttpRequest` | Servlet request / WebMvc.fn `ServerRequest` | Controller/request API per stack |
| Security | `SecurityWebFilterChain` | `SecurityFilterChain` | Per MVC or WebFlux |
| Path predicates | Gateway WebFlux factories | `GatewayRequestPredicates` MVC | Controller mappings, no built-in route engine |
| Filters | Reactive `GatewayFilter` / `GlobalFilter` / `WebFilter` | Servlet/MVC handler filters | Controller logic and stack-specific filters |
| Observable raw path | URI object `getRawPath()` | Servlet `getRequestURI()` per container | Depends on web stack |
| URL decoder | Reactor Netty/WebFlux behavior | Servlet container/framework behavior | Application client+server |
| Rewrite | Gateway WebFlux filters | Gateway MVC before/handler filters | App URI builder/ProxyExchange |

**Do not transplant WebFlux `WebFilter` and `Mono` directly into Server MVC**, nor treat `HttpServletRequest.getRequestURI()` as the raw TCP request line. Servlet containers may reject/normalize before reaching the app.

With ProxyExchange, never build outbound URIs via `proxy.uri(rawUrlFromClient)`: that also introduces open proxy/SSRF risks. Use origin allowlists and URI-safe path segment builders.

## 19. Backend Filesystem: Path Traversal Does Not Stop at HTTP Routing

Counterexample:

~~~java
// COUNTEREXAMPLE: never concatenate raw clientPath into a file read path.
Path file = Path.of("/srv/documents", clientPath);
byte[] content = Files.readAllBytes(file);
~~~

A value containing `..` or separators can escape the intended directory; symlinks can also lead outside even when the string looks valid.

### Safer Strategy

1. Prefer **opaque IDs/UUIDs** → backend looks up metadata to find the storage key.
2. Check resource owner/tenant/scope on the **final ID**.
3. If filesystem paths are unavoidable, validate grammar first, then resolve/normalize with `java.nio.file.Path`.
4. Check containment with `Path.startsWith(Path)`, **never string prefix comparison**: `/srv/doc` does not contain `/srv/doc-secret`.
5. Check `toRealPath()` and symlink escapes for existing files, per policy.
6. When creating/writing files, account for races/TOCTOU and safe file access APIs (e.g., `SecureDirectoryStream` where supported).
7. Archive extraction also requires per-entry checks against `zip-slip`/symlink traversal.
8. Avoid leaking full internal filesystem paths/credentials into responses or logs.

**`Path.normalize()` alone does not solve symlinks, races, resource ownership, or paths mis-decoded at the HTTP layer.**

## 20. Ingress/CDN/WAF: Pin Down Where Paths Are Parsed

A real deployment may look like:

~~~text
Client
  → CDN/WAF
  → NGINX/Envoy/Ingress
  → Gateway Server WebFlux / Web MVC
  → HTTP client / service discovery
  → Backend ingress/router
  → Backend controller/storage
~~~

Every hop can **reject, preserve, or canonicalize** the raw URI. In NGINX, `$request_uri` and `$uri` have different semantics; `proxy_pass`, rewrites, trailing slashes, and versions/configs also affect the path sent downstream. **Never copy a random NGINX snippet without knowing the exact request URI the backend actually receives.**

| Question | Policy needed |
|---|---|
| Allow encoded slashes? | Reject if ID grammar does not require them |
| Allow encoded dots/double encoding? | Typically reject under strict contracts |
| Are duplicate slashes collapsed? | Standardize on rejection or explicit canonicalization contract |
| Are semicolon paths used? | Reject if unsupported |
| Are Unicode paths needed? | Valid UTF-8 + explicit normalization form |
| What is authorization evaluated on? | Final effective resource + trusted identity |
| How to reject? | 400 for malformed/ambiguous, 403/404 per auth policy |
| Which layer may log raw URIs? | Security diagnostics with restricted access/redaction/retention |
| Who owns the path grammar? | API contract review plus ingress/Gateway/backend owners |
| When upgrading proxy versions? | Re-run regression suite against production-like chain |

**Do not choose "normalize at every hop."** If parsers cannot be unified, reject ambiguous inputs early and enforce authorization at the backend.

## 21. Distinguishing 400, 401, 403, 404, and 414

When a request path is rejected, the status reflects **which layer** acted and **why**.

| Case | Typically appropriate status | Notes |
|---|---|---|
| Invalid percent escape, ambiguous path grammar | **400 Bad Request** | Parser/ingress may reject before Gateway |
| Path contains encoded separator/dot forbidden by policy | **400 Bad Request** | Do not try normalizing into another path |
| Unauthenticated | **401 Unauthorized** | Per authentication scheme |
| Authenticated but lacking permission | **403 Forbidden** or 404 concealment per policy | Requires backend resource authorization |
| No route/handler matched | **404 Not Found** | Distinct from lacking permission |
| Request-target too long | **414 URI Too Long** if enforced by layer | Do not confuse 414 with 413 body size |
| Headers too large | **431 Request Header Fields Too Large** if enforced | Not a path error |

**Do not assume every `%2e%2e` request returns 400 at every layer**: one parser may block before the app, a security rule may return 403, and a route miss may return 404. The invariant to prove is **unauthorized resources are never accessed**.

## 22. Testing Must Observe Both Sides of the Proxy

A sound test must record:

1. The URL/raw path the load generator **attempted to send**;
2. What ingress received/forwarded;
3. Whether Gateway Security/Path predicates matched;
4. Whether `StripPrefix`/`RewritePath`/`SetPath` filters ran;
5. **What method, request-target, URI, and query the backend actually received**;
6. What **authorization and side effects** the backend performed;
7. What status/body/headers the client received.

**Asserting client status 400/404 alone is insufficient.** A request might have reached the backend and triggered side effects before an error response was ultimately returned. Tests must verify the **backend privileged request counter equals 0** for disallowed inputs.

### Lab-Only Echo Backend

Example Servlet MVC backend emitting non-sensitive metadata:

~~~java
package example.backend.lab;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PathEchoController {

    @GetMapping("/lab/path")
    public Map<String, String> echo(HttpServletRequest request) {
        return Map.of(
            "method", request.getMethod(),
            "requestUri", request.getRequestURI(),
            "servletPath", request.getServletPath());
    }
}
~~~

`getRequestURI()` and `getServletPath()` reflect **how the Servlet container processed the request**, not necessarily the original raw TCP bytes. Never expose this debug endpoint in production as it can leak topology or sensitive URIs.

In a Gateway lab, maintain a mock backend **request journal** (e.g., WireMock/MockWebServer) to verify paths and outbound calls rather than checking response text alone.

## 23. cURL: Paths to Test with `--path-as-is`

Some clients normalize literal `/../` before sending. With cURL, `--path-as-is` prevents the client from stripping dot-segments out of the request path it emits.

### Baseline

~~~bash
curl -i --path-as-is \
  'http://localhost:8080/api/orders/42'
~~~

### Negative Test Suite in the Lab

~~~bash
# Dot segment
curl -i --path-as-is \
  'http://localhost:8080/api/public/../admin/config'

# Percent-encoded dot segment
curl -i --path-as-is \
  'http://localhost:8080/api/public/%2e%2e/admin/config'

# Double-encoded dot segment
curl -i --path-as-is \
  'http://localhost:8080/api/public/%252e%252e/admin/config'

# Encoded slash
curl -i --path-as-is \
  'http://localhost:8080/api/items/A%2FB'

# Encoded backslash
curl -i --path-as-is \
  'http://localhost:8080/api/items/A%5CB'

# Duplicate slash
curl -i --path-as-is \
  'http://localhost:8080/api//admin/config'

# Semicolon path param
curl -i --path-as-is \
  'http://localhost:8080/api/items/42;v=1'

# Mixed-case escaped dots
curl -i --path-as-is \
  'http://localhost:8080/api/%2e%2E/admin/config'
~~~

Run **only in authorized environments**. `--path-as-is` does not guarantee all HTTP request-line bytes stay identical to the input string, because HTTP libraries, proxies, TLS, or protocol translation can still modify them. To prove octet-level behavior, use proper lab HTTP tracing/captures.

**Important:** Never put private tokens or real user IDs in request samples, logs, or test dashboards.

## 24. Test Matrix: Safe Outcome Matters More Than Exact Status

| Input (raw path at start of pipeline) | Expected strict grammar | Protected backend calls | Explanation |
|---|---|---|---|
| `/api/orders/42` | Allow if authenticated | Per authorization | Baseline |
| `/api/orders/42/` | Per contract | No privilege escalation | Trailing slash |
| `/api/orders/../admin` | Reject | **0** | Raw traversal |
| `/api/%2e%2e/admin` | Reject | **0** | Encoded dots |
| `/api/%252e%252e/admin` | Reject | **0** | Double encoding |
| `/api/%2Fadmin` | Reject | **0** | Encoded slash |
| `/api/%5Cadmin` | Reject | **0** | Encoded backslash |
| `/api//admin` | Reject | **0** | Duplicate slash |
| `/api/items;role=admin/42` | Reject if unsupported | **0** | Matrix param |
| `/api/%00/admin` | Reject/parser reject | **0** | NUL |
| `/api/%ZZ/admin` | Reject/parser reject | **0** | Invalid escape |
| `/api/café` | Reject under ASCII-only | **0** | Unicode input |
| `/API/admin` | Deny/no route per grammar | **0 if unauthorized** | Case sensitivity |
| `/api/admin/config` missing scope | 403/404 per policy | **0** or backend deny | Authorization |
| `/api/admin/config` with admin scope | Allow | Valid resource only | Positive security |

The table reflects the **illustrative strict grammar API** from section 15. For APIs with valid Unicode/encoded slugs, expected statuses differ, but **privilege escalation must remain impossible**.

### Test Beyond the Gateway

- Security denials must occur before protected business operations.
- Backends must never skip authorization just because an HTTP path "came through the Gateway."
- Unit tests verify custom WebFilters do not invoke the chain when rejecting.
- HTTP integration tests verify ingress/HTTP server parsers, Gateway, and backend are all safe.
- Test both HTTP/1.1 and HTTP/2 if production supports both protocols.
- Test requests with/without tokens, tokens missing scopes, cross-tenant resources, and header spoofing.

## 25. Integration Test: Gateway → Mock Backend → Privileged Journal

An end-to-end setup should include:

~~~text
Gateway:
  - SpringBootTest RANDOM_PORT
  - Strict path policy enabled per test config
  - Spring Security auth rules
  - Public route and protected route

Mock backend:
  - /catalog/items/42 returns 200 + public marker
  - /admin/config returns 200 + synthetic marker "PRIVATE_TEST_ONLY"
  - Journal counts requests and records backend paths

Test cases:
  1. Send path variants using an HTTP client capable of preserving request-target.
  2. Assert response never leaks "PRIVATE_TEST_ONLY".
  3. Assert mock backend received zero requests to /admin/config.
  4. Assert policy status per chosen parser/ingress.
  5. Assert negative cases trigger zero resource side effects.
  6. Assert valid requests reach the right backend path with contract status.
~~~

**StepVerifier + MockServerWebExchange does not replace tests against real Netty/ingress.** A unit test can inject URIs with encoded bytes straight into a mock, whereas Netty or ingress might reject/decode/normalize before the request ever reaches the filter.

### When Upgrading Spring Boot/Gateway/Netty/Ingress Versions

Re-run the **exact same regression matrix** and compare:

- Percentages of 400/403/404;
- Final backend requests;
- Raw/canonical paths at each hop;
- Authorization decisions;
- False positives on legitimate Unicode/encoded identifiers;
- Dynamic route/rewrite config revisions.

Never approve a rollout merely because "more requests are being blocked"; it might be causing an outage for legitimate clients without fixing the root cause.

## 26. File Downloads, Object IDs, and Access Permissions

Suppose an endpoint is:

~~~text
GET /api/files/{documentId}
~~~

A defensive design:

1. `documentId` is an opaque UUID or integer with a strict grammar.
2. Gateway/Spring Security authenticates the request.
3. The backend resolves ID → storage key via **server-side** metadata.
4. The backend checks **object owner, tenant, scope, and permission state**.
5. The storage API returns the authorized object without concatenating raw URI paths into filesystem paths.
6. Download headers such as `Content-Disposition`/`Content-Type` are escaped/validated per contract.
7. Real filesystem paths or user secrets are never logged in telemetry.

If file paths must be used, `Path.normalize()` and `Path.startsWith(Path)` are only part of the defense; **symlinks and race/TOCTOU** still require filesystem-level controls. For archive extraction, inspect every entry to prevent zip-slip and symlink escapes.

**The Gateway cannot verify every document ownership relationship.** Backends must deny cross-tenant access even when paths arrive through an approved public route.

## 27. Dynamic Routes, Rate Limiting, Retries, and Fallbacks Do Not Replace Path Security

### Dynamic Routes

When Gateway reads routes from Config Server/DB/registry or exposes route mutation APIs:

- Allow only trusted principals to create/edit `Path`, `RewritePath`, `SetPath`, `StripPrefix`, and target URIs.
- Review `Path=/**` routes and overlapping patterns.
- Never allow tenants to point routes to admin/metadata/internal targets.
- Gate changes with GitOps/review and route revision audits.
- Reconcile route configs across all Gateway instances.
- After upgrading filter factories, test effective downstream paths.

### RequestRateLimiter

A RateLimiter is not a URL validator. `KeyResolver` should not use raw user paths as identity keys because encoded variants can produce distinct keys. Choose a verified identity + stable policy ID and keep metric labels bounded.

### Retry

Retries do not make requests safer; they can replay **the same transformed outbound path**. A POST with side effects also risks duplicate business execution. Manage idempotency/deadlines/attempt caps separately.

### Circuit Breaker/Fallback

Fallbacks may serve cached data when backends fail, but **must never bypass authorization or leak user A's data to user B**. Never use a 200 fallback to mask a route pointing at the wrong resource. Fallback headers carrying exception details must also be filtered for allowed forwarding data.

## 28. Observability: Spotting Mismatches Without Logging Credentials

During an incident, you need to know **which hop saw which path**, yet raw URIs or queries may contain document/user IDs, bearer tokens, or PII.

| Field | How to log/record metrics |
|---|---|
| Gateway route ID | Allowed if finite and reviewed |
| HTTP method/status | Allowed |
| Correlation/trace ID | Logs/traces, never as a Prometheus label |
| Reject reason | Bounded enum: `invalid_escape`, `ambiguous_path`, etc. |
| Canonical route template | `/api/items/{id}` instead of raw URL |
| Raw path | Security diagnostics only with RBAC/redaction/retention |
| Query / Authorization / Cookie | Never log verbatim |
| Internal downstream host/path | Restricted to admin logs |
| User/tenant ID | Never attach to metric labels |
| Raw exception messages | Never forward to clients or put in metric labels |

Example **suggested** custom counter (not built into Gateway):

~~~text
gateway_path_rejections_total{
  reason="ambiguous_separator",
  route_class="public_api"
}
~~~

`reason` and `route_class` must belong to a **fixed set of values**. Per-request raw paths cause extreme cardinality and can leak sensitive data into Prometheus.

If the edge blocks requests before the Gateway, Gateway metrics **cannot count** them; combine ingress/WAF metrics with Gateway HTTP/route metrics.

## 29. Incident Runbook for Path Normalization Mismatches

When a suspected path bypass report arrives:

1. **Contain impact:** identify affected routes, backends, methods, auth policies, and timeframe.
2. **Inspect route revisions:** did `Path`/`RewritePath`/`StripPrefix`/`SetPath` change?
3. **Inspect the proxy chain:** did ingress/HTTP/2 translation/forwarded prefixes change?
4. **Compare representations:** compare raw paths in controlled logs against effective downstream paths.
5. **Check backend logs/journals:** was the protected resource actually accessed?
6. **Assess credentials/tenants:** were there unauthorized object reads or writes?
7. **Block ambiguous sources:** reject at edge/Gateway per grammar; verify backend auth immediately.
8. **Build regression tests:** raw/double-encoded slashes/dots, semicolons, Unicode, invalid UTF-8, route rewrites.
9. **Canary/rollback:** watch 400/403/404 rates, false positives, legitimate client traffic, and privileged backend access.
10. **Postmortem:** document which hop owns canonicalization and add the contract to architecture reviews.

**Never block a single specific payload with a regex** and declare the system safe. Fix the invariant: a caller cannot switch resources using encoding variants.

## 30. Symptom-Based Troubleshooting

| Symptom | Hypothesis | What to check |
|---|---|---|
| Raw `..` blocked, but `%2e%2e` reaches backend | Decoded at a later hop | Compare raw vs decoded at each hop |
| `%252F` bypasses filter | Double decoding | Reject ambiguous/repeated decoding |
| `%2F` returns 400, yet `%2f` matches | Faulty case-sensitive check | Hex case tests |
| Security permits public, backend sees admin | Rewrite/prefix mapping | Final outbound path + backend auth |
| Gateway returns 404, yet backend was called | Proxy/error/redirect behavior | Backend request journal |
| `/api//items` still routes | Proxy collapses separators | Ingress config and matchers |
| Semicolon disappears between Gateway/backend | Matrix param stripping | Parser behavior/version |
| Unicode slug points to wrong object | NFC/NFD/case folding | Canonical ID and DB lookup |
| Windows file backend reads outside base | Backslash/symlink | Real path containment |
| `getRawPath` shows no percent escapes | Ingress already normalized | Edge policy/tracing |
| WebFlux filter does not run in MVC | Wrong web stack | Servlet filter/HandlerFilter |
| RewritePath regex alters encoding | YAML escaping/URI processing | Test outbound bytes/path |
| 400 spike after deploying hardening | Legitimate encoded slugs | API grammar migration |
| Gateway route returns 200 on private backend | Backend lacks object-level auth | Deny-by-default on resources |
| One Gateway node behaves differently from peers | Config/version/ingress drift | Route revisions, release metadata |
| Metrics cardinality explodes | Raw paths used as tags | Stable route templates |
| Raw tokens leak in logs | Raw request-target logging | Redact/rotate/restrict |
| Ingress returns 403, Gateway logs nothing | Edge rejected before app | Ingress WAF/access logs |
| Actuator exposed via catch-all rewrite | Management/routing policy flaw | Separate port, restrict endpoints |

### Six Triage Questions

1. At **which hop** did the request stop?
2. Which **path representation** did each hop see?
3. Which layer decoded, normalized, re-encoded, rewrote, or redirected?
4. What did Spring Security **authorize**, and what did the final backend **execute**?
5. Is the backend privileged request counter/side-effect count truly zero?
6. Do regressions cover all variants without breaking legitimate APIs?

Never "quick-fix" by enabling `permitAll`, disabling TLS, opening Actuator, enabling encoded slashes across all servers, or adding a single rule blocking `../`.

## 31. Production Hardening Checklist

### Path Grammar and Parsers

- [ ] Defined path grammar per API group: charset, encoding, separators, max length.
- [ ] Raw path/decoded path/normalized path clearly distinguished in design.
- [ ] Explicit policy for `%2F`, `%5C`, `%2e`, `%25`, `..`, and `//`.
- [ ] No repeated decoding or calling `URLDecoder` on whole raw paths.
- [ ] Invalid UTF-8, malformed escapes, and NUL/control chars rejected per policy.
- [ ] Semicolon/matrix params either intentionally supported or rejected.
- [ ] Consistent Unicode normalization when needed; canonical object IDs.
- [ ] Trailing slashes/case sensitivity cannot bypass authorization.
- [ ] Ambiguous requests never silently normalized into privileged paths.

### Gateway and Backend Authorization

- [ ] Correct Gateway variant selected: WebFlux/MVC/ProxyExchange.
- [ ] Stack-appropriate Security chain configured **deny by default**.
- [ ] `Path` predicate only selects routes; backend still authorizes the final resource.
- [ ] Every `StripPrefix`/`RewritePath`/`SetPath` has expected outbound path tests.
- [ ] Catch-all/dynamic routes never expose admin/actuator/internal endpoints.
- [ ] Forwarded headers trusted only from controlled proxies.
- [ ] Outbound URIs use allowlists/builders, never raw client host/path concatenation.
- [ ] File/object APIs use opaque IDs/authorization and filesystem containment if applicable.
- [ ] Rate limiters/retries/fallbacks are never treated as path or permission checks.

### End-to-End Regression and Operations

- [ ] Ingress/CDN/WAF and backend proxies have verified normalization contracts.
- [ ] Tests cover encoded slash/dot/double encoding/semicolon/double slash/Unicode/invalid escapes.
- [ ] Both HTTP/1.1 and HTTP/2 tested if production supports both.
- [ ] Negative tests prove **0 protected backend calls** when rejected.
- [ ] Verified no cross-tenant data leaks and no unauthorized side effects.
- [ ] Tested over a production-like network path, not just MockServerWebExchange.
- [ ] Matrix re-run after every Gateway/Netty/Servlet/ingress upgrade.
- [ ] Logging uses redaction/RBAC/retention for raw path diagnostics.
- [ ] Metrics use reject reason codes and route templates, never raw URL labels.
- [ ] Runbook, route revision auditing, and rollback plan in place.

## 32. Hands-On Exercises

**Exercise 1 — Raw and decoded:** Trace the data flow for `/api/items/A%2FB` through client, ingress, Spring Security, Gateway route, and backend. Identify which representation each hop uses to make authorization decisions.

**Exercise 2 — Double encoding:** For `/api/public/%252e%252e/admin`, write the representation after 0/1/2 decode passes. Explain why "decode until no `%` remains" is an anti-pattern.

**Exercise 3 — Route rewrite:** Gateway `Path=/public/catalog/**` paired with `StripPrefix=1`. Create a table of public URLs → backend URLs, identify admin namespaces at risk of exposure, and add backend policies.

**Exercise 4 — WebFilter:** Add unit tests for `StrictRawPathWebFilter`: `%2F`/`%2f`, `%5c`, `;`, `//`, `%ZZ`, and Unicode. Why might an HTTP server reject certain malformed URLs before the test ever reaches the Java filter?

**Exercise 5 — Authorization:** Use a JWT lacking admin scope to call path variants; assert Gateway/ingress denial and backend privileged counter = 0. Add a test where a valid token from tenant A attempts to access tenant B's document.

**Exercise 6 — MVC migration:** Analyze migrating Gateway WebFlux to Server Web MVC: how do Servlet parsers, filter APIs, `SecurityFilterChain`, and route predicates differ? Propose a regression matrix.

**Exercise 7 — File service:** Design opaque document IDs and storage lookups avoiding raw file paths, defending against symlink escapes, zip-slip, and check-then-open races.

**Exercise 8 — Rollout:** After upgrading an ingress version, some legitimate Unicode slugs start returning 400. Design a way to measure false positives without reopening encoded traversal bypasses.

## References

- [RFC 3986 — Uniform Resource Identifier: Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986) — percent-encoding, reserved/unreserved, dot-segments, and normalization.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — HTTP resource semantics and response statuses.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112) — request-target and HTTP message parsing.
- [RFC 3987 — Internationalized Resource Identifiers](https://www.rfc-editor.org/rfc/rfc3987) — Unicode/IRI considerations.
- [OWASP — Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal) — directory traversal, encoded variants, and defensive approaches.
- [OWASP — Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html) — allowlist grammar and validation.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — deny by default, object-level authorization.
- [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) — trusted outbound URIs and egress controls.
- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — Gateway Server WebFlux/MVC, Path predicates, StripPrefix, RewritePath, SetPath, and versions.
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html) — request path abstractions and WebFilter.
- [Spring Security — Reactive](https://docs.spring.io/spring-security/reference/reactive/index.html) — `SecurityWebFilterChain`, path-based authorization, and resource server.
- [Spring Security — Servlet](https://docs.spring.io/spring-security/reference/servlet/index.html) — Servlet `SecurityFilterChain`.
- [NGINX — Core Variables](https://nginx.org/en/docs/http/ngx_http_core_module.html#variables) — `$request_uri` and `$uri`, must coordinate with `proxy_pass`/rewrite configs.
- [Unicode Standard Annex #15](https://unicode.org/reports/tr15/) — Unicode normalization forms.

**Remember:** **Path traversal is not just literal `../`.** Risks emerge whenever ingress, Gateway, Security, path filters, and backends **decode `%HH`, resolve `..`/`//`, or handle encoded slashes/backslashes, semicolons, Unicode, and rewrites under inconsistent rules**. Design **explicit path grammars, reject ambiguous inputs, never decode repeatedly**, and require **the backend to authorize the final resource** after every transformation. Unit tests for Java filters are necessary but insufficient: test the full pipeline, confirm **zero unauthorized requests touch privileged resources**, and log/emit metrics safely without exposing sensitive data.
