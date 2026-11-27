# Validating Target URIs and Avoiding Open Proxies in Controllers

An API Gateway must forward requests to downstream microservices while preserving security boundaries. With **Spring Cloud Gateway Proxy Exchange**, you can inject a `ProxyExchange<byte[]>` parameter directly into a Spring Web MVC or WebFlux controller and call `proxy.uri(...).get()`, `post()`, or other HTTP methods. This convenience brings a particularly severe risk: if the destination URL is taken directly from user input, the controller can become an **open proxy**, enabling **Server-Side Request Forgery (SSRF)**.

For instance, an endpoint like `GET /api/proxy?url=...` might seem handy for testing backends. However, if the controller does not restrict destinations, outsiders can make the Gateway send requests to addresses they cannot reach directly: internal admin services, cloud metadata APIs, loopback, or another system. If the controller also accidentally forwards cookies, access tokens, or identity headers, the incident escalates from a routing bug to **credential leakage and authorization boundary bypass**.

This lesson belongs to the **Proxy Exchange** chapter of the **SPRING_CLOUD_GATEWAY** module. Within the context of building an API Gateway with route predicates, filter chains, path/header transformations, service discovery, authentication, rate limiting, circuit breakers, retries, TLS, and request observability, **controlling target URIs** is a mandatory boundary whenever proxying from a controller.

**Learning objectives:**

1. Distinguish **Gateway Server** from **Proxy Exchange**, along with their respective Web MVC/WebFlux APIs.
2. Recognize **open proxies**, SSRF, confused deputy attacks, and common URI validation bypasses.
3. Enforce the principle: **the client selects business data only; the server decides scheme, host, and port**.
4. Build safe URIs from a **fixed base URL**, valid path segments, and allowlisted query parameters.
5. Verify destination policies against tricky dynamic URL cases: redirects, DNS rebinding, actual peer IPs, TLS/SNI, and egress.
6. Protect `Authorization`, `Cookie`, `Host`, `Forwarded`, and hop-by-hop headers.
7. Write illustrative MVC/WebFlux controllers and test rejected cases so **zero outbound requests** are sent.
8. Combine authentication, authorization, timeouts, retries, circuit breakers, and observability for safe operations.

> **Version scope:** This lesson uses **Spring Cloud Gateway Proxy Exchange**, with artifacts `spring-cloud-gateway-proxyexchange-webmvc` and `spring-cloud-gateway-proxyexchange-webflux` per Gateway 4.3/5.x documentation. This is *an alternative gateway style* using annotated controllers, **not** Gateway Server Web MVC or Server WebFlux with automatic route predicates/filter chains. Gateway Server filters/configs do not automatically protect `ProxyExchange` controllers; corresponding policies must be implemented in the controller, Spring Security, HTTP client, and network layers.

## 1. What Does Proxy Exchange Do?

Spring Cloud Gateway docs describe `ProxyExchange` as a utility object used inside a **regular Spring web handler**:

```java
// Conceptual pattern per official docs (MVC).
@GetMapping("/test")
public ResponseEntity<?> proxy(ProxyExchange<byte[]> proxy) {
    return proxy.uri("https://backend.example/api/image/png").get();
}
```

With **WebFlux**, the controller method typically returns:

```java
// Conceptual pattern (WebFlux), not a servlet controller.
@GetMapping("/test")
public Mono<ResponseEntity<?>> proxy(ProxyExchange<byte[]> proxy) {
    return proxy.uri("https://backend.example/api/image/png").get();
}
```

`uri(...)` **selects the outbound destination** and `get()` **executes an HTTP GET** to that destination. `ProxyExchange` itself has no way to know whether that URL belongs to a backend approved by the system owner.

### Two Matching Artifacts

```xml
<!-- For Spring Web MVC / Servlet -->
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-gateway-proxyexchange-webmvc</artifactId>
</dependency>

<!-- Or (do not combine both merely because both say Gateway):
     For Spring WebFlux / Reactive -->
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-gateway-proxyexchange-webflux</artifactId>
</dependency>
```

Pick the dependency matching your Spring Boot stack and a **compatible Spring Cloud BOM**. In older releases you may see `spring-cloud-gateway-mvc`/`spring-cloud-gateway-webflux`; current docs use `proxyexchange-*`.

### Distinguishing From Gateway Server

| Question | Gateway **Proxy Exchange** | Gateway **Server Web MVC/WebFlux** |
| --- | --- | --- |
| Where is routing decided? | Annotations/controllers and application logic | Route definitions + predicates/handler mappings |
| Who sets upstream URLs? | Code calling `proxy.uri(...)` | Route URI, filter chains, load balancing |
| HTTP programming model | `@GetMapping`, `@PostMapping` controllers | Filters/RouterFunctions depending on product |
| Primary API | `ProxyExchange<T>` | `GatewayFilter`/`GlobalFilter` or `HandlerFilterFunction` |
| Destination control | Controller must enforce strict policy | Route sources/control plane must also be protected |
| Local `forward()` support | **MVC** variant supports it | Server-specific forwarding mechanism |
| Automatically gets Gateway Server Retry/RateLimiter? | **Not by default** | Configurable per route with built-in filters |
| When to use? | A few custom BFF/proxy endpoints, specific business mappings | Shared entry gateway with many routes/policies |

**Key takeaway:** A controller using `ProxyExchange` does not become a safe gateway just because “gateway” appears in a dependency name. It remains an HTTP client running with the server's network privileges.

## 2. Open Proxy and SSRF: Related, Not Identical

An **open proxy** is an endpoint that lets users make the server forward requests to **arbitrary destinations**, often without requiring authorization or sensible limits.

**SSRF** is causing a server to send requests to unauthorized addresses by manipulating parameters such as URL, host, path, redirects, or DNS. SSRF can occur even when an endpoint is not a full open proxy.

```mermaid
flowchart LR
    A["Untrusted client"] -->|"client-chosen url"| G["Controller + ProxyExchange"]
    G -->|"Gateway HTTP client"| P["Arbitrary destination"]
    P --> I["Internal API"]
    P --> M["Cloud metadata / token service"]
    P --> E["External system"]
    I --> G
    M --> G
    E --> G
    G -->|"Proxied response returned"| A
```

Consequences can include:

- Accessing resources on **loopback** (`127.0.0.1`/`::1`) or internal networks closed to the Internet.
- Hitting administrative endpoints or metadata services issuing credentials.
- Port scanning and service fingerprinting via status/latency even without reading full bodies.
- Abusing the Gateway's IP address to bypass network allowlists on other services.
- Accidentally forwarding user or Gateway `Authorization` headers or cookies to an attacker-controlled host.
- Returning HTTP responses containing config info or PII to unauthorized callers.

A controller with a **flawed domain allowlist** can still suffer SSRF via redirects or DNS rebinding. Multiple layers of defense are required, not just a `String.startsWith(...)` check.

## 3. Most Obvious Anti-Pattern: Accepting a URL and Calling proxy.uri()

Never write a public endpoint like this:

```java
// UNSAFE — shown only to recognize the vulnerability.
@GetMapping("/api/proxy")
public ResponseEntity<?> unsafe(
        @RequestParam String url,
        ProxyExchange<byte[]> proxy) {

    return proxy.uri(url).get();
}
```

In this example, the client chooses **scheme, host, port, path, and query**. The server itself sends the outbound request to the chosen URL.

```text
GET /api/proxy?url=https://catalog.example/items/42

Without controls, the same API can be aimed at:
  localhost / loopback
  an admin service inside a private network
  a cloud metadata endpoint
  an external host controlled by an attacker
```

**You do not need** to implement an HTTP CONNECT proxy to create an open proxy. A single `GET` controller returning responses from arbitrary addresses suffices to turn the Gateway into an untrusted relay.

### Variants That Are Just as Dangerous

```java
// UNSAFE: replacing full URL with client-chosen host.
proxy.uri("https://" + request.getParameter("host")
    + "/v1/items/42").get();

// UNSAFE: trusting a client-supplied header.
proxy.uri(request.getHeader("X-Target-Url")).get();

// UNSAFE: "base URL" where path can be resolved into another URI.
proxy.uri(baseUri.resolve(untrustedSuffix).toString()).get();
```

With `URI.resolve(...)`, a suffix starting with `//` is a **network-path reference** that can replace the authority; a suffix with `../` can escape the base path. That is why “joined onto a base URI” **cannot** be treated as locking down host and path.

**Best fix:** **Never let clients pass URLs or hosts.** Let clients pass a **resource ID**, a **service alias**, or a small set of validated query parameters, and let the server build a fixed destination.

## 4. Designing Trust Boundaries Before Writing Code

Clearly classify where each piece of data originates:

| Input | Trust Level | What to Use It For? |
| --- | --- | --- |
| `@PathVariable sku` | Untrusted | Only a **product code** after validation |
| `@RequestParam locale` | Untrusted | Only `vi`/`en` per allowlist |
| `@RequestHeader Host` | Untrusted | Never use to pick backend |
| `X-Forwarded-Host` / `Forwarded` | Untrusted unless from trusted proxy chain | Never use to construct `proxy.uri` |
| `@RequestParam url` | Untrusted | **Reject** as a destination |
| Tenant/user ID from verified JWT | Authenticated context, still needs policy | Permission checks; never freely form hostnames |
| Fixed URI in controlled config | Trusted per deployment pipeline | Select backend, still apply network/TLS guards |
| Internal service registry | Conditionally trusted | Must restrict allowed service IDs/instances |
| Backend-returned `Location` redirect | Not automatically trusted | Never auto-follow outside allowlist |
| DNS response | Conditionally trusted | Must verify actual peer IP and connection timing |

**Priority principles:**

1. **Clients express business intent**, not network routing details.
2. **The server maps** that intent to a known destination.
3. **A URI builder** encodes each path segment and query value individually.
4. **The HTTP client** is configured not to follow out-of-policy redirects.
5. **Network egress** allows only approved destinations.
6. **The backend** still enforces resource authorization rather than trusting the Gateway unconditionally.

## 5. Fixed-Destination Model: Clients Pass Only the SKU

A dedicated endpoint may accept:

```http
GET /api/catalog/items/sku-42?locale=vi HTTP/1.1
Host: api.example.com
```

While the outbound request built by the **server** is:

```http
GET /v1/items/sku-42?locale=vi HTTP/1.1
Host: catalog.internal.example:8443
```

There is no `url`, `scheme`, `host`, `port`, or `redirect` parameter in the public contract.

```mermaid
flowchart TD
    R["GET /api/catalog/items/{sku}?locale=vi"] --> V["Validate SKU + locale"]
    V --> T{"Valid input?"}
    T -- "No" --> X["400 Bad Request<br/>no outbound call"]
    T -- "Yes" --> B["Use base URI from trusted config"]
    B --> U["Append pathSegment + queryParam<br/>encode"]
    U --> N["ProxyExchange.uri(target).get()"]
    N --> P["Approved catalog-service"]
```

The **Spring Web MVC** example below uses `ProxyExchange` in controller style without accepting destinations from clients.

## 6. Java MVC Controller: Server-Decided URIs

Assumptions for this example:

- `CATALOG_BASE` is operator-controlled configuration; hardcoded here to highlight the trust boundary.
- The backend serves `GET /v1/items/{sku}`.
- SKUs contain only letters, digits, and hyphens, 1–40 characters long.
- Locale accepts only `vi` or `en`; no other query keys pass downstream.
- The controller supports GET only, never proxying arbitrary methods.

```java
package example.gateway.proxy;

import java.net.URI;
import java.util.Set;
import java.util.regex.Pattern;

import org.springframework.cloud.gateway.mvc.ProxyExchange;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

@RestController
public class CatalogProxyController {

    // In production: load from deployed/reviewed typed configuration,
    // never from client-supplied queries or headers.
    private static final URI CATALOG_BASE =
        URI.create("https://catalog.internal.example:8443");

    private static final Pattern SAFE_SKU =
        Pattern.compile("[A-Za-z0-9-]{1,40}");

    private static final Set<String> LOCALES =
        Set.of("vi", "en");

    @GetMapping("/api/catalog/items/{sku}")
    public ResponseEntity<?> findItem(
            @PathVariable String sku,
            @RequestParam(defaultValue = "vi") String locale,
            ProxyExchange<byte[]> proxy) {

        if (!SAFE_SKU.matcher(sku).matches()
                || !LOCALES.contains(locale)) {
            return ResponseEntity.badRequest().build();
        }

        URI target = UriComponentsBuilder
            .fromUri(CATALOG_BASE)
            .pathSegment("v1", "items", sku)
            .queryParam("locale", locale)
            .build()
            .encode()
            .toUri();

        // URL does not depend on client Host/X-Forwarded-Host or "url".
        return proxy.uri(target.toASCIIString()).get();
    }
}
```

### Intentional Controls

- `@PathVariable sku` is a **business identifier**, not an arbitrary path.
- `SAFE_SKU` excludes `/`, `\`, `:`, `?`, `#`, `%`, whitespace, and control characters from the SKU after Spring binding.
- `UriComponentsBuilder.pathSegment(...)` explicitly models the path segments and encodes per URI semantics.
- `CATALOG_BASE` never comes from requests, keeping destination changes inside the deployment process.
- `locale` is allowlisted; the controller **does not** copy raw query strings to the backend.
- The API is GET-only without a catch-all `@RequestMapping("/**")` across all HTTP verbs.

**Snippet limitations:** This is a **destination-selection example**, not a complete production configuration: you still need `SecurityFilterChain`, network egress rules, TLS verification, timeouts, response header policies, and HTTP redirect policies. The SKU regex fits simple product IDs; for resources with Unicode or complex segments, build a dedicated parser/URI builder and test double encoding.

### Reading the Base URI From Configuration

In production, never hardcode dev/prod targets in source code. You can use:

```yaml
app:
  upstreams:
    catalog:
      base-uri: https://catalog.internal.example:8443
```

Then bind via typed `URI` `@ConfigurationProperties`, validating **at startup**: scheme, host, port, and path prefix must match the environment's allowlist. Crucially: **an operator changing `base-uri` is a security change**, requiring code-level review and auditing—never let a public admin endpoint edit it arbitrarily.

Never use `@Value("${app.upstreams.catalog.base-uri}")` to read a value that clients could update through business data.

## 7. WebFlux Controller: Same Policy, Different Return Type

Proxy Exchange has a WebFlux variant for a standard `@RestController`. Here too, Gateway Server's `GlobalFilter`/`ServerWebExchange` are **not** used; the controller still selects the URI explicitly.

```java
// WebFlux pattern: import ProxyExchange from the proxyexchange-webflux
// artifact matching your Spring Cloud Gateway release train.
@RestController
class CatalogProxyWebFluxController {

    private static final URI CATALOG =
        URI.create("https://catalog.internal.example:8443");

    private static final Pattern SKU =
        Pattern.compile("[A-Za-z0-9-]{1,40}");

    @GetMapping("/api/catalog/items/{sku}")
    Mono<ResponseEntity<?>> find(
            @PathVariable String sku,
            ProxyExchange<byte[]> proxy) {

        if (!SKU.matcher(sku).matches()) {
            return Mono.just(ResponseEntity.badRequest().build());
        }

        URI target = UriComponentsBuilder.fromUri(CATALOG)
            .pathSegment("v1", "items", sku)
            .build()
            .encode()
            .toUri();

        return proxy.uri(target.toASCIIString()).get();
    }
}
```

**MVC vs. WebFlux differences:**

- MVC `get()` returns `ResponseEntity<?>`.
- WebFlux `get()` returns `Mono<ResponseEntity<?>>`.
- WebFlux must not call `block()` to validate DNS or HTTP on the event loop.
- The same URL policy must apply on **both stacks**; switching to reactive does not eliminate SSRF.
- Verify exact `ProxyExchange` imports/APIs against your chosen artifact; never import MVC's `org.springframework.cloud.gateway.mvc.ProxyExchange` into a WebFlux controller.

Do not convert a controller to WebFlux merely to add Spring Cloud Gateway Server WebFlux filters. They are two distinct execution styles requiring separate dependency and auto-configuration evaluation.

## 8. Multiple Upstreams: Use Aliases, Never Accept Hosts

A BFF application may call several backends, such as `catalog` and `inventory`. Instead of:

```http
GET /api/fetch?host=inventory.internal.example&path=...
```

let the client pick from a restricted alias set while the server maps the alias to a configured URI **that requests cannot alter**:

```java
private static final Map<String, URI> TARGETS = Map.of(
    "catalog", URI.create("https://catalog.internal.example:8443"),
    "inventory", URI.create("https://inventory.internal.example:8443")
);

// Select only from the server-managed map.
URI base = TARGETS.get(alias);
if (base == null) {
    return ResponseEntity.badRequest().build();
}

// Then apply an alias-specific path template, NEVER a raw URL.
```

This is an **implementation fragment** for an MVC controller; add `Map`, `URI`, and response-handling imports when placing it in a full class.

**Why are aliases effective?**

1. Clients never see or supply internal hostnames.
2. Each alias can have its own **path/method allowlist**.
3. Each backend has its own HTTP client/TLS/timeout/credential policy.
4. Easy to enforce **RBAC**: users allowed to view catalog are not automatically allowed to call inventory admin.
5. Easy to emit bounded-cardinality metrics per alias.
6. When hostnames change across deployments/discovery, the public contract stays intact.

However, an alias **is not authorization by itself**. A client sending `alias=inventory` must still be authorized per business use case and resource; never use a shared map to expose all inventory admin endpoints.

## 9. Full URI Validation: Only a Secondary Layer, Not the Preferred Option

Sometimes a system genuinely must accept a URL from a **trusted administrator** (such as registering a webhook destination). Strict validation is required there, and that functionality should be isolated from public BFF proxies.

### URI-Level Checklist

| Component | Required Verification |
| --- | --- |
| Scheme | Only `https` or policy-approved schemes; reject `file`, `ftp`, `gopher`, `jar`, custom schemes |
| Host | **Exact allowlist** domain name or fixed alias; never flawed `contains`/`endsWith` |
| Port | One of explicit ports, e.g. `443` or `8443` |
| Userinfo | Reject URIs containing `user:pass@host` |
| Fragment | Reject; fragments are not sent in HTTP requests to servers |
| Opaque URI | Reject anything not a hierarchical HTTP(S) URI |
| Path | Permitted patterns/segments, never arbitrary full paths |
| Query | Only defined keys/values, with size/length limits |
| Redirect | Disable auto-follow or **revalidate every hop** |
| DNS/IP | Actual resolved IP allowed; prevent rebinding and TOCTOU |
| TLS | Verify hostname, certificate, and SNI; never disable verification |
| Egress | NetworkPolicy/firewall blocks unapproved destinations |
| Headers | Never send secrets or identity headers to untrusted destinations |

**Order of preference:** Whenever possible, rather than validating a user-entered URL, accept only an **allowlisted host/service alias** and construct the URL from fixed scheme, port, and path. OWASP emphasizes **avoiding accepting full URLs from users** because parser/canonicalization bugs are notoriously subtle.

### Example Application-Level URI Validator Class

```java
import java.net.URI;
import java.util.Locale;
import java.util.Set;

final class TrustedDestinationPolicy {

    private static final Set<String> ALLOWED_HOSTS =
        Set.of("catalog.internal.example",
               "inventory.internal.example");

    static URI validateAdministrativeUri(URI uri) {
        if (uri == null || !uri.isAbsolute() || uri.isOpaque()) {
            throw new IllegalArgumentException("Invalid URI");
        }

        String scheme = uri.getScheme();
        String host = uri.getHost();

        if (!"https".equalsIgnoreCase(scheme)
                || host == null
                || !ALLOWED_HOSTS.contains(
                    host.toLowerCase(Locale.ROOT))
                || uri.getPort() != 8443
                || uri.getRawUserInfo() != null
                || uri.getRawFragment() != null) {
            throw new IllegalArgumentException("Destination denied");
        }

        return uri;
    }
}
```

**Inline warning on the code:** This function checks only **scheme/host/port/userinfo/fragment**; it does **not** validate paths/queries, redirects, DNS peer IPs, or HTTP client behavior. It is **not a complete SSRF firewall**. In real applications, add path/query policies and egress enforcement—or better yet, never let users supply URIs at all.

Never echo the invalid URI back in public error messages—it could contain credentials or internal details.

## 10. String Checks That Are Easy to Bypass

These are **not** trustworthy destination allowlists:

```java
// ANTI-PATTERN: attacker string may just start with an allowed host
if (url.startsWith("https://catalog.internal.example")) {
    proxy.uri(url).get();
}

// ANTI-PATTERN: keyword can appear anywhere in the URL
if (url.contains("catalog.internal.example")) {
    proxy.uri(url).get();
}

// ANTI-PATTERN: blocking only literal "localhost"
if (!url.contains("localhost")) {
    proxy.uri(url).get();
}
```

Risky input classes to test at the parser/policy layer:

- URLs with **userinfo**: what precedes `@` is not the final host.
- Prefix-matching hosts: `catalog.internal.example.attacker.invalid`.
- Trailing dots, mixed casing, and non-canonical IDN/Punycode.
- IPv4 variants, IPv6 literals, IPv4-mapped IPv6, or NAT64 addresses.
- `%` characters and double encoding causing two parser layers to disagree.
- Strings with `\` or control characters interpreted differently across URL parsers.
- Redirects from an allowed host to a disallowed host.
- DNS returning an allowed IP at check time and a different IP at connect time.

**Do not try to solve this with one giant URL regex.** Parse with `URI`/URI builders, validate every component against an allowlist, and **enforce the actual destination at network connection time**.

## 11. URI Parsing and Canonicalization: Inspect the Authority Properly

A structured URL typically looks like:

```text
scheme://userinfo@host:port/path?query#fragment
        └──────── authority ────────┘
```

With Java `URI`:

| API | Meaning |
| --- | --- |
| `getScheme()` | `https` or another scheme |
| `getHost()` | Host identified by parser; may be null if URI is malformed or ambiguous |
| `getPort()` | Explicit port, or `-1` if omitted |
| `getRawUserInfo()` | Userinfo segment before host |
| `getRawPath()` | Undecoded path |
| `getRawQuery()` | Undecoded query |
| `getRawFragment()` | Fragment |
| `isOpaque()` | Distinguishes opaque URIs from hierarchical HTTP URIs |
| `normalize()` | Resolves some `.`/`..` path segments; **does not** replace security validation |

**Distinguishing port `-1`:** If policy permits default HTTPS, `getPort() == -1` may imply 443 in some HTTP clients. Be consistent: either require an explicit port or normalize port from scheme **before comparing**. Section 9's example **intentionally requires `8443`**.

### Why Are IDN and DNS Separate Problems?

Unicode domain names can map to Punycode. If a system permits multilingual domains, enforce `IDN.toASCII()` normalization and hostname validation, comparing against a normalized allowlist. Never accept a domain just because it “looks like” a valid host.

Even when `URI.getHost()` matches the allowlist, the IP returned by DNS lookup can be attacker-controlled if the DNS/domain is external to trusted infrastructure. Thus checking host strings alone is **insufficient** for external domains.

## 12. Path Traversal and Using ProxyExchange.path()

Proxy Exchange docs include `proxy.path("/proxy/path/")` to extract the remaining request path and append it to a backend URI. It is convenient, yet introduces risk if you treat the trailing path as **already trusted**.

Example from the docs:

```java
@GetMapping("/proxy/path/**")
public ResponseEntity<?> proxyPath(ProxyExchange<byte[]> proxy) {
    String path = proxy.path("/proxy/path/");
    return proxy.uri(home.toString() + "/foos/" + path).get();
}
```

This illustrates **API usage**, not a complete anti-SSRF/path-traversal policy. Whenever `/**` is permitted, attackers can submit dot-segments, encoded slashes, or special parameters.

### Distinct Risks

1. **Host escape:** the URI can switch hosts if code misuses `URI.resolve(...)` on user-controlled segments.
2. **Path escape:** even with a fixed host, the path can reach an admin endpoint on **the same backend**, escaping `/foos/**`.
3. **Double decoding:** Gateway/backend/proxies may decode `%2F` or `%2E` multiple times, resolving different paths.
4. **Parameter pollution:** original queries may be concatenated/forwarded outside the allowlist.

**Preferred solution:** explicit resource mapping:

```java
@GetMapping("/api/catalog/items/{sku}")
public ResponseEntity<?> item(
        @PathVariable String sku,
        ProxyExchange<byte[]> proxy) {

    if (!sku.matches("[A-Za-z0-9-]{1,40}")) {
        return ResponseEntity.badRequest().build();
    }

    URI dest = UriComponentsBuilder
        .fromUri(URI.create("https://catalog.internal.example:8443"))
        .pathSegment("v1", "items", sku)
        .build().encode().toUri();

    return proxy.uri(dest.toASCIIString()).get();
}
```

If multi-segment paths are truly necessary, split into **individually validated and encoded segments**; never pass a raw suffix to `resolve`/string concatenation, and enforce deny-by-default on backend admin endpoints. Test paths after decoding and normalization across the **Servlet container, Spring MVC, proxies, and backend**.

## 13. Query Parameters: Copy Only What the API Needs

Avoid:

```java
// ANTI-PATTERN: concatenating raw query strings without an allowlist.
String target = BASE + "/search?" + request.getQueryString();
return proxy.uri(target).get();
```

Raw queries can contain:

- `redirect`, `callback`, `url`, or `next` parameters causing the backend to redirect or make outbound calls.
- `admin=true` or `includeSecrets=true` with special backend meaning not meant for public APIs.
- Duplicate keys like `role=user&role=admin` where parsers pick first vs. last differently.
- Oversized queries bloating logs/upstreams or carrying credentials.
- Encoded `&`/`=` altering parsing upon concatenation or double decoding.

### Controlled Query Construction

```java
@GetMapping("/api/catalog/search")
public ResponseEntity<?> search(
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "20") int size,
        ProxyExchange<byte[]> proxy) {

    if (page < 1 || page > 1000 || size < 1 || size > 100) {
        return ResponseEntity.badRequest().build();
    }

    URI dest = UriComponentsBuilder
        .fromUri(URI.create(
            "https://catalog.internal.example:8443"))
        .pathSegment("v1", "search")
        .queryParam("page", page)
        .queryParam("size", size)
        .build()
        .encode()
        .toUri();

    return proxy.uri(dest.toASCIIString()).get();
}
```

If a client adds `?url=...`, this code **never uses it as a destination**. Still, define an explicit policy for unknown query parameters (ignore vs. reject) and test with real requests.

**Never copy headers like `X-Original-URL` or `X-Rewrite-URL` into URI construction**, unless supplied by a trusted component under an explicitly designed security contract.

## 14. Redirects: A Safe Initial Host Can Still Lead to a Bad Host

Suppose the initial target is allowlisted:

```text
https://catalog.internal.example:8443/v1/items/sku-42
```

The backend returns:

```http
HTTP/1.1 302 Found
Location: https://unapproved.example.invalid/collect
```

If the HTTP client inside `ProxyExchange` **auto-follows redirects**, the next outbound call can hit another host **without the controller ever checking it**.

Per OWASP, **disable automatic redirect following** on HTTP clients performing SSRF-sensitive operations, or **revalidate the entire policy** on **every hop** before connecting.

### Mandatory Controls

1. Identify which HTTP client/transport ProxyExchange MVC/WebFlux actually uses in your version.
2. Disable **automatic redirects** when designing fixed-destination endpoints; never enable global redirect following casually.
3. If business logic genuinely requires following, cap hop count and enforce **scheme, hostname, port, path, DNS/IP, and TLS** on each hop.
4. Never send host A's `Authorization`/`Cookie` to host B just because a `Location` header appeared.
5. Validate response `Location` before returning to clients if it could send browsers to unapproved domains.
6. Test `301`/`302`/`303`/`307`/`308`; note 307/308 preserve HTTP method and body, which is dangerous for POST.
7. Prevent redirect loops from causing DoS via unbounded hop counts.

**Important:** ProxyExchange docs give no universal guarantee that every HTTP client across every version **automatically disables redirect following**. Verify your transport configuration rather than assuming behavior from another client.

## 15. DNS Rebinding, TOCTOU, and Actual Destination IPs

Application-level Java validation typically flows like this:

```text
T1: validate host "approved.example" -> allow
T2: HTTP client resolves DNS on its own
T3: HTTP client connects to the new IP
```

If DNS responses at T1 and T2 differ, an attacker can pass validation with a benign IP and then redirect the connection to **loopback/private/link-local**. This is **DNS rebinding** and **time-of-check to time-of-use** (TOCTOU).

```mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway controller
    participant D as DNS
    participant H as HTTP client
    participant I as Disallowed destination

    C->>G: Request to alias/URL
    G->>D: Preliminary DNS check
    D-->>G: Valid IP at time T1
    G->>H: Pass target hostname
    H->>D: Re-resolve at T2
    D-->>H: Different IP
    H->>I: Connects if no network guard exists
    Note over G,I: Allowlisting at T1 alone is insufficient
```

**Defense-in-depth:**

- Prefer **organization-controlled hosts/services**; avoid passing arbitrary domains to the HTTP client.
- If accepting dynamic domains from trusted admins, enforce domain/IP policies across both **A and AAAA** records.
- Never rely on a denylist containing only `127.0.0.1`; account for **IPv4, IPv6, IPv4-mapped IPv6**, link-local, metadata endpoints, and environment-sensitive ranges.
- **Pin connections to the validated IP** at the HTTP client/network layer when external URLs are truly required, while keeping the original hostname for TLS certificate verification, SNI, and `Host`.
- Never allow an **unchecked DNS re-lookup** after validation.
- Enforce policies on **every retry, redirect, and failover attempt**, not just the first attempt.
- Use **egress firewalls, Kubernetes NetworkPolicies, service mesh policies, or egress proxies** on an allowlist basis so a code bug cannot open the entire internal network.

### Do Not Block Every Private IP Mechanically

A legitimate internal microservice may live at `10.x.x.x` or `172.16–31.x.x`; a blanket “block all private IPs” rule will break the app. The right policy is **allowing only the specific network/service identities this workload is permitted to call**, rather than letting clients reach the whole private network.

**Never disable hostname verification to connect directly by IP.** If the client must pin a resolved IP, configure the HTTP client so certificate verification and SNI still use the original hostname, and test with your exact client version.

## 16. Service Discovery and Dynamic Routes Do Not Replace URI Validation

Some Proxy Exchange apps call services by alias/discovery. Remember:

- `serviceId` must still belong to a **server-managed allowlist**.
- Presence in a registry/`ServiceInstanceListSupplier` does not mean every instance may receive tokens or tenant data.
- Never take an arbitrary `serviceId` from a query to call any service in the cluster.
- Restrict namespaces, zones, ports, and instance metadata per trust boundary.
- If a discovery source is tampered with, the proxy might connect to a rogue instance; network/identity policies limit the blast radius.

```text
Allowed:
  "catalog"   -> service identity catalog-service
  "inventory" -> service identity inventory-service

Disallowed:
  client passing any registry service ID,
  client passing Pod IP:port,
  client altering scheme/authority via headers.
```

In Gateway Server, an operator-declared `lb://catalog-service` URI is resolved inside the filter chain. With **ProxyExchange**, do not assume `proxy.uri("lb://...")` carries all Gateway Server behaviors; it is a controller utility backed by your artifact/version's transport. When service discovery is needed, design/test a dedicated URI-resolution mechanism or consider standard Gateway Server routes.

## 17. ProxyExchange Default Headers Are Not a Complete Security Policy

Official docs state `ProxyExchange` handles:

- **Sensitive headers:** defaults **`cookie`** and **`authorization`**, omitted from downstream calls by default.
- **Skipped headers:** defaults **`content-length`** and **`host`**, not copied verbatim outbound.
- **Proxy/forwarded headers:** `x-forwarded-*` headers handled via its own mechanism.
- Methods to add headers or map responses.

This **reduces default risk**, yet does not mean every request header is safe to forward or that every app retains default settings.

### Header Policy Table

| Header | Recommended Policy |
| --- | --- |
| `Authorization` | Do not forward by default; if TokenRelay/manual tokens are needed, send only to approved backends with matching audience/scope |
| `Cookie` | Never forward browser cookies to unauthorized upstreams; prevent session leaks |
| `Host` | Let HTTP client set the right authority; never use client's raw `Host` as target |
| `Content-Length` | Let HTTP client recalculate when body changes; prevent framing bugs |
| `Connection`, `Transfer-Encoding`, `TE`, `Upgrade` | Hop-by-hop; never forward blindly |
| `Proxy-Authorization` | Never copy proxy credentials |
| `Forwarded`, `X-Forwarded-*` | Trust only verified proxies; sanitize/rewrite per topology |
| `X-User-Id`, `X-Tenant-Id`, `X-Roles` | Never trust client-supplied values; regenerate after auth if backend contract needs them |
| `X-Request-Id` / trace context | Normalize, cap length, never use for auth |
| `Origin` | Used for CORS/browser policies; not a trusted identity source |
| `Accept` / `Content-Type` | Forward under API control; enforce valid types and limits |

**Never widen `sensitive headers` to let `Authorization` flow to every upstream.** An access token is valid only within a specific trust boundary and audience. If passing a token is mandatory, put that decision in a dedicated policy and test redirect scenarios too.

### Header Spoofing at Trust Boundaries

A client can supply:

```http
X-Forwarded-Host: admin.internal.example
X-Forwarded-Proto: https
X-User-Id: superuser
```

Nothing guarantees those values came from a trusted ingress. Therefore, **never use them to build outbound URIs or grant permissions**. At the trusted edge, strip client-supplied values and regenerate only from verified facts; across multiple proxies, define the chain and parser explicitly.

## 18. Responses Can Also Become a Leak Channel

Restricting outbound destinations solves only **half** the problem. If a trusted backend returns sensitive data and the controller hands the raw response to an under-privileged caller, the Gateway still leaks data.

Check:

- **Status/body:** proxy only resources the caller is authorized to read.
- **`Location`:** redirecting to an out-of-policy host can send browsers to phishing pages or leak URL tokens.
- **`Set-Cookie`:** backend cookies may have Domain/Path/SameSite/Secure values unsuited to the Gateway domain.
- **`WWW-Authenticate`:** can reveal issuer/realm/service topology; design an error contract.
- **CORS headers:** never let upstreams return `Access-Control-Allow-Origin: *` on credentialed APIs.
- **Cache headers:** `Cache-Control: no-store` when responses hold PII/tokens, preventing cross-tenant caching.
- **Content-Type:** never serve untrusted HTML/JavaScript on the same origin when the API contract expects JSON.
- **Server/trace/internal headers:** never return stack traces, hostnames, internal paths, or credentials.
- **Content length/encoding:** recalculate framing when transforming bodies; never copy stale `Content-Length`.

ProxyExchange docs support passing a **response mapper** to `get()` and other verbs to transform `ResponseEntity` before replying to the client. This is where **response header allowlisting/sanitization** can be applied alongside backend security.

**Never** just add a response header `X-Proxy-Safe: true` and assume SSRF is blocked. Safety depends on outbound destinations, HTTP client rules, and data authorization—not a self-assigned marker.

## 19. Authentication, Authorization, and Tenant Isolation

A proxy controller typically runs with broader network privileges than clients. This is the **confused deputy** pattern: the server has permission to call the backend, so it must verify whether the client is permitted to **ask the server to make that call**.

```mermaid
flowchart TD
    U["User / client"] --> A["Spring Security<br/>verify token/session"]
    A --> B{"Allowed to access endpoint + resource?"}
    B -- "No" --> X["401 / 403, do not proxy"]
    B -- "Yes" --> C["Validate alias/SKU/query"]
    C --> D["Build allowlisted URI"]
    D --> E["Outbound credential policy"]
    E --> F["Backend validates resource authorization"]
```

### Separating Three Permissions

1. **Permission to call the public endpoint:** may the user access `/api/catalog/items/**`?
2. **Permission to read the resource:** may the user/tenant view that specific SKU/data?
3. **Gateway permission to call upstream:** may the controller use that backend's service identity/credentials?

A user with `ROLE_VIEWER` must never be able to switch the target host to `billing-admin.internal`, even if `billing-admin` lives on the organization's private network.

### Access Tokens and ProxyExchange

By default, ProxyExchange does not forward `Authorization`/`Cookie` per its documented sensitive-header policy. When a backend needs identity:

- Use an **OAuth2 TokenRelay/token exchange** pattern at the Security layer rather than stripping all header restrictions.
- Send tokens only to approved backend trust domains and audiences.
- When using service-to-service tokens, the backend still needs verified user/tenant context and must enforce permissions.
- Never mix Gateway cookie sessions with backend access tokens.
- Never trust a client-supplied `X-Tenant` unless bound to the authenticated principal.

**Gateway Server's `TokenRelay` filter does not run automatically on ProxyExchange controllers.** If both products coexist in one app, track which flow traverses which filter chain.

## 20. HTTP Methods, Request Bodies, Streaming, and Resource Limits

An open proxy can be abused beyond GET. If a controller allows arbitrary verbs and bodies:

- `POST` can trigger state-changing actions on internal admin systems.
- `PUT`/`PATCH` can modify resources without authorization.
- `DELETE` can wipe data.
- Multipart uploads/large bodies can exhaust memory.
- Infinite streaming can tie up connections, threads, and buffers.
- Retrying write requests can multiply side effects.

**Choose narrow mappings:**

```java
// Prefer explicit read-only endpoints:
@GetMapping("/api/catalog/items/{sku}")

// Avoid this unless backed by dedicated network/business policies:
@RequestMapping(value = "/proxy/**", method = {
    RequestMethod.GET, RequestMethod.POST,
    RequestMethod.PUT, RequestMethod.DELETE
})
```

### Limits to Enforce

| Resource | Limit |
| --- | --- |
| Request body | Max size per endpoint, content-type allowlist |
| Response body | Max size / streaming policy; no unbounded buffering |
| HTTP client | Connect/read/response timeouts, connection pool, max connections |
| Redirects | Disable follow or cap hops + revalidate each hop |
| Retries | Transient errors only, idempotent methods only, small attempt cap |
| Concurrency | Appropriate thread pools, connection pools, and backpressure |
| Rate limits | Per user/tenant/alias; prevent abusing gateway network access |
| URI | Path/query lengths, segment counts, valid characters |
| Logging | Body size caps, header filtering, token redaction |
| Egress | Destination network/service allowlist |

With MVC, blocking HTTP calls tie up Servlet worker threads; with WebFlux, avoid blocking operations on the event loop. ProxyExchange is an HTTP utility; it does not automatically stream huge responses with zero memory overhead. Measure and test actual transport behavior.

## 21. Timeouts, Retries, and CircuitBreakers Do Not Replace URI Policy

Some teams try to “protect” an open proxy with a 1-second timeout. That does not stop SSRF—metadata and local endpoints often respond in a few milliseconds.

**Distinguish capabilities:**

| Mechanism | What It Helps With | What It Does Not Prevent |
| --- | --- | --- |
| URI allowlist | Restricts allowed destinations | Does not automatically stop DNS rebinding/redirects |
| Egress NetworkPolicy | Blocks connections to forbidden networks | Does not check whether the user may view data |
| Connect/response timeouts | Caps wait time on slow upstreams | Does not stop sending requests to the wrong destination |
| Retry | Recovers transient faults | Can multiply SSRF attempts if policy is flawed |
| CircuitBreaker | Sheds load during sustained failures | Does not decide whether a host is permitted |
| RateLimiter | Throttles client request volume | Does not make an arbitrary URL safe |
| TLS verification | Authenticates the specified hostname | Does not confirm that hostname fits business policy |
| Authentication | Identifies the caller | Logged-in callers can still abuse user-chosen URLs |
| Observability | Detects anomalous traffic | Does not block the initial request |

When enabling retries:

- **Validate the destination before every attempt** if targets can change.
- If redirects, failover, or DNS re-resolution occur, enforce policy at **connection time**.
- Never retry `POST`/`DELETE` casually.
- Set end-to-end deadlines and budgets so SSRF cannot exhaust Gateway threads/connections.
- Gateway Server's `CircuitBreaker`/`Retry` do not wrap `ProxyExchange` automatically; use actual HTTP client controls and resilience integrations inside the controller.

## 22. Local Lab: Proxying a Fixed Backend Instead of Arbitrary URLs

Sample topology:

- `ProxyExchange` controller running on `http://localhost:8080`.
- Valid test backend on `http://127.0.0.1:18081`.
- Backend exposes `GET /v1/items/{sku}`, returning a JSON marker.
- Controller allows only `GET /api/catalog/items/{sku}`.

**In the lab**, the base URI may be fixed to loopback:

```java
private static final URI TEST_BACKEND =
    URI.create("http://127.0.0.1:18081");
```

**Why doesn't this contradict SSRF guidance?** Loopback here is a **fixed, operator-configured destination** for local workstation testing; clients cannot pick the port or host. In production, remove loopback targets and use approved service identities/URIs.

Stub backend:

```java
package example.backend;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogStubController {

    @GetMapping("/v1/items/{sku}")
    public Map<String, String> item(@PathVariable String sku) {
        return Map.of(
            "sku", sku,
            "servedBy", "catalog-test-backend");
    }
}
```

Run the **stub backend on port 18081** in a separate application; the ProxyExchange controller runs on port 8080. These are illustrative snippets, not two Spring Boot processes booted from one file.

### Valid Request

```bash
curl -i \
  "http://localhost:8080/api/catalog/items/sku-42"
```

Expected: response from catalog stub containing `"servedBy":"catalog-test-backend"`. If you get 404, verify context path, request mapping, base URI, network, and ProxyExchange classpath before relaxing route permissions.

### Invalid SKU Input

```bash
# Space will be URL-encoded by curl, then handled by binding/validation.
curl -i \
  "http://localhost:8080/api/catalog/items/bad%20sku"
```

Expected: controller returns **400** (or Servlet/router may reject invalid URLs before the controller depending on settings). **Zero outbound requests** to the stub backend.

### Adding a Decoy Query URL That Is Ignored as a Target

```bash
curl -i \
  "http://localhost:8080/api/catalog/items/sku-42?url=http%3A%2F%2F127.0.0.1%3A18082%2Fadmin"
```

The sample controller does not bind the `url` query, so the destination remains backend 18081 and path `/v1/items/sku-42`. For stricter APIs, proactively return 400 on undeclared queries; the crucial invariant is **zero outbound traffic to 18082**.

**Use only controlled lab environments**; never probe real metadata or internal endpoints of a production system to test security.

## 23. Automated Tests: Proving Zero Outbound Calls on Rejected Input

Unit-testing a boolean “isValidUrl” helper is insufficient. Test the **controller**, **argument resolver**, and **real HTTP client** together to verify bad requests create zero outbound traffic.

### Test Matrix

| Input | Required Outcome | Expected Outbound Calls |
| --- | --- | --- |
| SKU `sku-42` | Success | 1 request to allowed catalog |
| SKU with whitespace | 400 | **0** |
| SKU with `/` or dot-segments | 400/404 at HTTP mapping per config | **0** |
| SKU longer than 40 chars | 400 | **0** |
| Query `url=http://...` | Ignored or 400 | Never calls URI in query |
| Header `X-Target-Url` | Ignored | Does not affect destination |
| Header `Host: arbitrary.invalid` | Host never used as target | Does not change outbound URI |
| Spoofed `X-Forwarded-Host` | Ignored/normalized | Does not affect destination |
| Unknown alias | 400/404 | **0** |
| Double-encoded path | Blocked by path policy | **0** if invalid |
| Backend returns 302 | Never auto-calls host outside allowlist | Calls only valid backend |
| DNS swaps peer IP | Connection blocked by client/egress policy | No connection to forbidden IP |
| Backend timeout | Controlled error status | No infinite retries |
| Under-privileged user | 401/403 | **0** |
| Unusual `Set-Cookie`/`Location` in response | Sanitized per contract | Never leaked to clients unexpectedly |

### Example URI Policy Unit Test

```java
import java.net.URI;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class TrustedDestinationPolicyTest {

    @Test
    void rejectsDifferentHost() {
        URI uri = URI.create(
            "https://unapproved.example.invalid:8443/v1/items/sku-42");

        assertThrows(IllegalArgumentException.class,
            () -> TrustedDestinationPolicy
                .validateAdministrativeUri(uri));
    }

    @Test
    void rejectsUserInfo() {
        URI uri = URI.create(
            "https://user:secret@catalog.internal.example:8443/items");

        assertThrows(IllegalArgumentException.class,
            () -> TrustedDestinationPolicy
                .validateAdministrativeUri(uri));
    }

    @Test
    void rejectsWrongPort() {
        URI uri = URI.create(
            "https://catalog.internal.example:9443/items");

        assertThrows(IllegalArgumentException.class,
            () -> TrustedDestinationPolicy
                .validateAdministrativeUri(uri));
    }

    @Test
    void rejectsNonHttpScheme() {
        URI uri = URI.create(
            "file:///etc/hosts");

        assertThrows(IllegalArgumentException.class,
            () -> TrustedDestinationPolicy
                .validateAdministrativeUri(uri));
    }
}
```

**This policy test does not verify outbound transport.** Pair it with integration tests against a mock HTTP server or controlled stub backend to verify:

- The actual host/port connected to.
- No unsafe redirect following.
- No sensitive headers forwarded.
- No second request on rejection.
- No destination switch after DNS/retries.
- No unauthorized response bodies returned.

You do not need to send real requests to cloud metadata endpoints; use local-network stubs and deny rules.

## 24. Integration Testing With MVC and WebFlux

### Spring Web MVC

With `@SpringBootTest(webEnvironment = RANDOM_PORT)` and an HTTP test client or `MockMvc`:

1. Start a stub backend recording request counts and headers.
2. Call the controller with a valid SKU and verify backend JSON is returned.
3. Call with an invalid SKU; verify `400` and that the backend counter did not increment.
4. Send forged `Host` and `X-Forwarded-Host`; verify the backend address does not change.
5. Send `Authorization: Bearer test-only`; verify outbound **does not forward automatically** per default sensitive policy.
6. Have the backend return `302 Location` pointing to a test-only blocked server; verify the blocked server's counter stays zero.
7. Enable Spring Security in the integration context and confirm unauthorized callers trigger zero outbound requests.
8. Verify response headers/`Set-Cookie` per contract before returning to the client.

`MockMvc` tests controller mapping/validation, yet proxy requests may still issue real HTTP calls depending on `ProxyExchangeArgumentResolver` config. Never expect a pure `MockMvc` test to block outbound calls automatically; use a mock HTTP client or controlled stub.

### Spring WebFlux

Use `WebTestClient` and an HTTP stub backend:

- Test missing and valid authentication.
- Test SKU formatting and query encoding.
- Test concurrent requests and backpressure when proxying large bodies.
- Never use `block()` in the controller; use blocking helpers only in **test code** if supported.
- If using asynchronous DNS/IP validation, test thread starvation, cancellation, and timeouts.

Both stacks must provide **network-layer evidence** that target URIs cannot be steered by queries, headers, or paths.

## 25. Egress Security: Blocking at Infrastructure Level When Code Fails

A gateway with broad network access is a high-value target. Even when controllers use fixed URIs, network controls should block connections outside approved backends.

```mermaid
flowchart LR
    G["ProxyExchange workload"] --> E["Egress policy / proxy"]
    E -->|"Allow service identity + port"| C["catalog-service"]
    E -->|"Allow service identity + port"| I["inventory-service"]
    E -.->|"Deny"| M["Cloud metadata endpoints"]
    E -.->|"Deny"| A["Arbitrary private admin APIs"]
    E -.->|"Deny"| X["Unapproved Internet hosts"]
```

### Defense Layers

| Layer | Controls |
| --- | --- |
| Application | Fixed destinations, path/query validation, per-user authorization |
| HTTP client | Redirect policy, TLS verification, timeouts, HTTP method controls |
| DNS / service discovery | Trusted resolvers, namespace restrictions, peer IP checks when dynamic |
| Kubernetes/VM network | Egress allowlists to service subnets/ports, block metadata |
| Service mesh | Service identities, mTLS, external service registration |
| Cloud environment | Metadata service hardening, egress security groups/firewalls |
| Monitoring | Alerts on DNS/egress denies, unusual hosts/ports, 4xx/5xx |

**Kubernetes NetworkPolicies typically operate on IPs/labels and depend on the CNI**; never assume an FQDN allowlist works in every cluster. For FQDN-based policies, use a supporting egress gateway/CNI and test DNS changes. For internal services, consider identity-based routing/service mesh.

Never grant unrestricted outbound Internet access to a ProxyExchange workload that only needs to call two internal microservices.

## 26. Safe Observability and Investigation

The goal is detecting **anomalous routes/destinations** without leaking sensitive data into logs.

| Signal | Should Log | Should Not Log |
| --- | --- | --- |
| Public endpoint | Template `/api/catalog/items/{sku}` | URLs with queries holding tokens |
| Route/alias | `catalog`, `inventory` | Unvalidated client-supplied hosts as metric labels |
| Destination | Approved service ID/host at permitted granularity | Raw URIs with credentials/queries |
| HTTP method | GET/POST per contract | Request bodies containing PII |
| Upstream status | 2xx/4xx/5xx and failure category | Raw backend errors containing secrets |
| Duration | p50/p95/p99, connect timeouts | Raw tokens/cookies |
| Rejection reason | `invalid_sku`, `blocked_target`, `unauthorized` | Verbatim malicious payload URLs |
| DNS/egress denied | Counts and resource types | Full internal network maps in public responses |
| Redirect denied | Hop count, destination category | `Location` containing credentials |
| Correlation ID | Normalized, bounded length | Unbounded client-injected IDs / log injection |

**Metric labels** should remain low-cardinality: endpoint templates, finite aliases, statuses, and error classes. Never use arbitrary hostnames, raw user IDs, or full URLs as labels, which cause memory pressure and leak PII.

### Suggested Alerts

- Unusual spikes in `blocked_target`/`invalid_path` from a single client.
- Repeated egress-denied connections to disallowed networks.
- Sudden increases in HTTP redirects compared to baseline.
- Connections to upstreams outside the approved service ID list.
- Rising 401/403s at backends caused by wrong-audience token relays.
- Spikes in timeouts/5xx alongside scan-like traffic.
- Proxy controller QPS exceeding normal business API baselines.

Never automatically block all users over a single input validation error; combine rate limits, authentication, and evidence-based investigation.

## 27. Troubleshooting: Common URI and Security Bugs

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Client only needs SKU, yet controller takes a URL | Overly generic API design | Narrow contract to resource ID/alias |
| `startsWith` lets foreign hosts through | String prefix check instead of URI components | Parse and exact-allowlist; better yet, server-fixed URI |
| Forged `Host` changes destination | Built URI from raw `Host`/`X-Forwarded-Host` | Remove those inputs from target selection |
| Valid initial URL redirects to another host | HTTP client auto-follows redirects | Disable auto-follow or revalidate every hop |
| DNS hostname valid, peer IP wrong | DNS rebinding / TOCTOU | Enforce connection-time policy + egress |
| `../` path reaches admin endpoint on same backend | Arbitrary suffix concatenation/`resolve` | Allowlist path segments; normalize consistently |
| Double-encoded path bypasses validator | Validated after one decode; backend decodes again | Test end-to-end parser pipeline; reject ambiguity |
| `URI.getHost()` returns null | Malformed URI, Unicode, or ambiguous authority | Fail closed; never fall back to raw string |
| IPv6 or IPv4-mapped IP slips past denylist | Checked IPv4 text only | Use canonical IP/network policy covering both IPv4 and IPv6 |
| Sensitive body returned to unauthorized caller | Missing resource authorization | Enforce tenant/resource checks at Gateway and backend |
| Proxy sends cookies/tokens to another host | Relaxed sensitive header policy or redirects | Keep default blocking; check audience + destination |
| Backend does not receive expected `Host` | ProxyExchange skips `Host` by default | Let HTTP client generate proper `Host`/SNI; do not copy client `Host` |
| Body errors on POST/multipart | Improper body/framing conversion | Configure HTTP client codecs/body limits; avoid open proxying |
| MVC controller returns strange `Mono` | Mixed MVC and WebFlux artifacts | Align stack, artifact, and API |
| Gateway Server filters do not run | ProxyExchange controllers bypass Gateway Server chain | Use Servlet/WebFlux security and separate controller policies |
| `lb://` fails with no route resolution | Assumed ProxyExchange acts like Gateway Server | Integrate/test discovery client or switch to Server flavor |
| TLS handshake failure | Wrong certificate/SNI/truststore | Fix trust config; never disable hostname verification |
| Proxy slow despite short timeout | DNS, pool, redirects, and retries have separate clocks | Set end-to-end deadline + connect/read/pool timeouts |
| Gateway runs out of threads | Blocking MVC calls or streaming under load | Enforce rate/concurrency limits and tune pools |
| 404 on valid SKU | Wrong path builder or backend mapping | Compare outbound path in stub/redacted logs |
| `X-Forwarded-*` headers wrong | Non-standard trusted proxy chain | Normalize at edge; never trust clients |
| Metric cardinality explodes | Raw URI/hostname/SKU used as label | Use bounded route templates/aliases |
| Wrong port in URI config | Default port mismatches backend | Inspect explicit/effective config ports |

### Root-Cause Investigation Workflow

1. **Inspect the public contract:** what can clients select? Are there URL/host fields?
2. **Verify the stack:** ProxyExchange MVC or WebFlux, and which packages/dependencies?
3. **Trace target construction:** do scheme/host/port come from **trusted config** or requests?
4. **Check path/query validation:** any raw suffix/query concatenation, normalization, or double decoding?
5. **Inspect outbound calls:** actual destination, redirect hops, DNS-resolved peer IP, and SNI/TLS?
6. **Inspect headers:** are `Authorization`/`Cookie`/`Host`/`Forwarded` relayed unintentionally?
7. **Check Security:** is the caller authorized for the target resource/tenant?
8. **Check egress:** is traffic to admin/metadata networks blocked?
9. **Test denials:** do invalid inputs produce **0 outbound requests**?
10. **Choose the fix:** prefer narrowing the API contract rather than patching payloads in a denylist.

## 28. Reinforcement Exercises

### Exercise 1 — Identify the Vulnerability

```java
@GetMapping("/fetch")
ResponseEntity<?> fetch(@RequestParam String url,
                        ProxyExchange<byte[]> proxy) {
    return proxy.uri(url).get();
}
```

**Question:** Which trust boundary is violated?

**Answer:** The user picks the outbound URI while the HTTP request originates from a server with internal network privileges. This is an open proxy and an SSRF entry point.

### Exercise 2 — Checking `startsWith`

A controller allows only URLs matching `startsWith("https://catalog.internal.example")`.

**Question:** Is that sufficient?

**Answer:** No. String prefix matching does not identify the actual host. Avoid user-supplied URLs altogether, or parse URI components, match an exact allowlist, and enforce the actual destination.

### Exercise 3 — `URI.resolve`

```java
URI base = URI.create("https://catalog.internal.example/v1/");
URI dest = base.resolve(userSuppliedSuffix);
```

**Question:** Why doesn't this guarantee host and path safety?

**Answer:** The suffix can be an absolute URI or network-path reference, and the path can contain dot-segments. Construct URIs from **fixed or validated path segments** instead.

### Exercise 4 — `Authorization` Header

The Gateway receives a Bearer token from a browser and needs to call an inventory backend.

**Question:** Should you disable the sensitive-headers mechanism to forward the token on every request?

**Answer:** No. Only forward or exchange tokens according to approved identity, audience, scopes, destinations, and backend authorization. ProxyExchange intentionally suppresses sensitive headers by default.

### Exercise 5 — Redirects

`catalog.internal.example` is allowlisted, yet the backend returns a 302 to an unapproved host.

**Question:** Is checking the initial host enough?

**Answer:** Not yet. Disable auto-follow or revalidate every hop, and enforce egress policies.

### Exercise 6 — DNS Rebinding

A DNS validator returns an allowed IP; the HTTP client re-resolves DNS and gets a private IP.

**Question:** What must you do?

**Answer:** Pin connections to the validated IP, disallow unchecked re-resolution, keep TLS/SNI aligned with the original hostname, and enforce a network egress allowlist.

### Exercise 7 — Multiple Upstreams

Clients need to select catalog or inventory. Should you accept `?host=...` or `?service=catalog`?

**Answer:** Use `catalog`/`inventory` aliases with server-side mappings and route-specific authorization; never let callers choose hostnames or ports.

### Exercise 8 — Query Passthrough

A controller copies `request.getQueryString()` verbatim to the backend.

**Question:** What is the risk?

**Answer:** The backend might interpret admin/redirect parameters outside the public contract, duplicate parameters, or encoded separators. Construct only allowlisted query parameters.

### Exercise 9 — Test Verification

Unit tests for `TargetPolicy` pass, yet there are no HTTP client tests.

**Question:** Have you proven SSRF is impossible?

**Answer:** No. You need integration tests with backend and blocked-server stubs confirming no outbound calls hit wrong hosts, including redirects and DNS/IP enforcement.

### Exercise 10 — ProxyExchange or Gateway Server?

An application must route hundreds of routes and manage per-route rate limits, circuit breakers, and retries.

**Question:** Should you build a `@RequestMapping("/**")` combined with `ProxyExchange`?

**Answer:** Usually no. The Gateway Server flavor provides route predicates and filter factories far better suited to that scale; use ProxyExchange for a few controller endpoints with explicit business logic.

## 29. Secure ProxyExchange Deployment Checklist

- [ ] Confirmed exact **Gateway Proxy Exchange** and MVC/WebFlux artifact for your release train.
- [ ] Do not assume ProxyExchange is automatically protected by Gateway Server route filters.
- [ ] Never take `url`/`uri`/`host`/`port` from clients straight into `proxy.uri(...)`.
- [ ] Use **fixed destinations or server-managed alias allowlists**.
- [ ] Accept only resource IDs/path variables with strict format/length; avoid raw `/**` suffixes without policies.
- [ ] Build URLs with a URI builder, separating path segments and queryParams; encode once.
- [ ] Never use `String.startsWith`, `contains`, or naive localhost denylists to validate hosts.
- [ ] If accepting URLs from trusted admins, validate scheme/host/port/userinfo/path/query/fragment and audit changes.
- [ ] Check IPv4, IPv6, mapped addresses, and DNS rebinding whenever targets can vary.
- [ ] Enforce **egress allowlists** at network/HTTP client layers, not solely in one validation function.
- [ ] Never follow out-of-policy redirects; test all relevant 3xx codes.
- [ ] Enforce TLS certificate/hostname/SNI verification; use mTLS when required by backends.
- [ ] Keep default suppression of sensitive `Authorization` and `Cookie` headers unless an explicit policy applies.
- [ ] Never use client `Host`/`Forwarded`/`X-Forwarded-*` as URI sources or trusted identities.
- [ ] Restrict HTTP methods: expose GET/POST/PUT/DELETE individually per business contract.
- [ ] Configure request/response size caps, timeouts, connection pools, concurrency, and rate limits.
- [ ] Never retry POST/DELETE arbitrarily; enforce idempotency when backends have side effects.
- [ ] Verify authentication and principal/tenant/resource authorization before proxying.
- [ ] Never relay tokens with wrong audience/scope or to unapproved hosts.
- [ ] Control response headers `Location`, `Set-Cookie`, CORS, caching, and error details.
- [ ] Test encoded paths, dot-segments, query pollution, URI userinfo, and host spoofing.
- [ ] Test redirect + DNS peer policies at transport level, not just URI parser unit tests.
- [ ] Every rejected request must produce **0 outbound requests**.
- [ ] Observe destination aliases/route templates rather than raw URLs, tokens, or user IDs.
- [ ] Verify behavior across multiple Gateway replicas and across DNS/cache/network changes.
- [ ] Protect destination configuration/control planes with RBAC, code review, and auditing.
- [ ] Maintain runbooks for egress denies, SSRF alerts, config rollbacks, and credential-exposure remediation.
- [ ] If proxy logic becomes overly general-purpose, consider **Gateway Server** with explicit route definitions and filter policies.

## Conclusion

**`ProxyExchange`** is a concise utility enabling Spring Web MVC or WebFlux controllers to send HTTP requests downstream. Precisely because the controller calls `proxy.uri(...)` directly, **choosing safe destinations is the application code's responsibility**. Allowing clients to supply arbitrary URLs, hosts, or ports quickly turns the Gateway into an open proxy and SSRF entry point—even when authentication, timeouts, and rate limiting are enabled.

The safest design lets **the server decide scheme, host, and port**, while clients supply only bounded business data. Use fixed URIs or aliases, `pathSegment`/`queryParam`, exact allowlists, header protections, and authorization, while enforcing policies at the **HTTP client, DNS/TLS, and network egress** layers. When accepting URLs from trusted sources is unavoidable, account for redirects, DNS rebinding/TOCTOU, canonicalization, and every retry attempt.

Consider a proxy endpoint safe only when **integration tests prove invalid inputs make zero outbound requests**, responses leak no credentials, and policies hold even when backends redirect, DNS records change, or service discovery updates. That foundation enables building a microservices API Gateway whose routing, authentication, TLS, and observability remain both flexible and controlled.

## References

- [Spring Cloud Gateway — Proxy Exchange Gateway with Spring Web MVC or WebFlux](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-proxy-exchange.html)
- [Spring Cloud Gateway 4.3 — Proxy Exchange MVC/WebFlux](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-proxy-exchange.html)
- [Spring Cloud Gateway — Server vs Proxy Exchange Overview](https://docs.spring.io/spring-cloud-gateway/reference/intro.html)
- [Spring Cloud 2025.0 — Module artifact and prefix migration](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes)
- [OWASP Cheat Sheet — Server Side Request Forgery Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP Cheat Sheet — Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP Cheat Sheet — REST Security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [Spring Framework — UriComponentsBuilder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html)
- [Spring Security — Servlet OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [Spring Security — Reactive OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html)
- [Spring Framework — Spring MVC Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html)
- [Spring Framework — Spring WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html)
