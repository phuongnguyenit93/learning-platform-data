# Preserving Query Strings, Slashes, and Encoded Characters When Rewriting Paths

## 1. Why Can Path Rewriting Easily Break Requests?

In microservices systems, clients typically hit a public path like `/api/v1/catalog/products/42`, whereas the backend service only handles `/products/42`. **Spring Cloud Gateway** provides `RewritePath`, `StripPrefix`, `SetPath`, and `PrefixPath` to transform paths before proxying requests. They keep the public API stable even when internal service structures evolve.

However, URLs also contain query strings and percent-encoded characters. Consider the request:

~~~http
GET /api/v1/items/blue%20shirt?tag=a%2Fb&tag=c&sort=desc HTTP/1.1
Host: api.example.test
~~~

If the goal is solely to strip the `/api/v1` prefix, the backend should receive the **raw path** `/items/blue%20shirt` and **raw query** `tag=a%2Fb&tag=c&sort=desc`. A flawed URL rewrite could:

- Drop `?tag=...` entirely when replacing the path.
- Turn `a%2Fb` into `a/b`, changing how the value is parsed.
- Turn `blue%20shirt` into `blue%2520shirt` by encoding `%` a second time.
- Strip a trailing `/` from the path, or accidentally produce `//items`.
- Collapse repeated query parameters into a single value when parsing and rebuilding the URL.

This lesson in the **Path Rewriting and Redirects** chapter of **Spring Cloud Gateway** focuses on **modifying only the path while preserving the rest per the API contract**. Examples use **Gateway Server WebFlux**; for Server Web MVC or other version lines, consult the matching API and configuration namespaces.

After this lesson, you will be able to:

1. Distinguish raw paths, decoded paths, query strings, and percent-encoding.
2. Configure `RewritePath`, `StripPrefix`, and `SetPath` without inadvertently dropping queries.
3. Explain the difference between literal slashes `/` and encoded slashes `%2F`.
4. Explicitly handle root paths, trailing slashes, duplicate slashes, and repeated query parameters.
5. Distinguish internal path rewriting from 3xx redirects.
6. Verify the request actually received by the backend and prevent decoding discrepancies across the Gateway, proxies, and services.

## 2. Path, Query, and Fragment Are Distinct Components

An HTTP URI can be broken down as follows:

~~~text
https://api.example.test:8443/api/v1/items/blue%20shirt?tag=a%2Fb&tag=c#section
|scheme|------ authority -------|-------- raw path ------|--- raw query ---|
~~~

| Component | Illustrative value | Purpose |
| --- | --- | --- |
| Scheme | `https` | Protocol |
| Authority | `api.example.test:8443` | Host and port |
| Raw path | `/api/v1/items/blue%20shirt` | Path that may retain percent-escapes |
| Raw query | `tag=a%2Fb&tag=c` | Portion after `?` |
| Fragment | `section` | Portion after `#`, handled client-side; omitted from standard HTTP request-targets |

The **path** is normally used to route to a resource or handler. The **query** is an independent component, typically expressing filters, search terms, pagination, or response options. Path-rewriting rules do not need to interpret query semantics unless query rewriting is explicitly required.

~~~text
/api/v1/items/42
/api/v1/items/42?lang=vi
/api/v1/items/42?lang=en&tag=hot&tag=new
~~~

All three requests can rewrite their path to `/items/42` while keeping each request's query intact. Crucially, do not reconstruct the full URL from a single-value parameter map, since a plain map can drop the second `tag` value.

### Raw path vs. decoded path

| Raw path | After one appropriate decode | Note |
| --- | --- | --- |
| `/items/blue%20shirt` | `/items/blue shirt` | Spaces must be encoded in URIs |
| `/items/a%2Fb` | `/items/a/b` | Encoded slashes can alter segment boundaries |
| `/items/a%252Fb` | `/items/a%2Fb` | Decoding again can produce a literal slash |
| `/items/price%2Btax` | `/items/price+tax` | Plus signs in paths are not automatically spaces |
| `/items/%C3%A1o` | `/items/áo` in UTF-8 | Non-ASCII characters are encoded across multiple bytes |

**Not every HTTP stack accepts encoded slashes `%2F`.** Proxies, servlet containers, or applications may reject, preserve, or decode them according to their own policies. When designing routes and authorization, standardize handling system-wide; never rely solely on how one layer inspects the raw path.

## 3. Where Does Path Rewriting Sit in the Gateway Pipeline?

Spring Cloud Gateway resolves routes using **route predicates** such as `Path`, `Method`, `Host`, or `Header`. After a matching route is chosen, `FilteringWebHandler` runs the relevant gateway filters, including path-transforming filters and upstream routing filters.

~~~mermaid
flowchart TD
    A[Client: /api/v1/items/42?lang=vi] --> B[RoutePredicateHandlerMapping]
    B -->|Matching route| C[FilteringWebHandler]
    C --> D[RewritePath or StripPrefix]
    D --> E[New raw path: /items/42]
    E --> F[HTTP routing to upstream]
    F --> G[Backend: /items/42?lang=vi]
    G --> H[Response to client]
~~~

A dedicated filter like `RewritePath` modifies the path portion of the request and updates routing metadata. Downstream routing filters consume the information in `ServerWebExchange`, including the target URL prepared via exchange attributes such as `GATEWAY_REQUEST_URL_ATTR`.

Three principles:

1. **Predicates select the route before that route's filters run.** If `Path` fails to match the incoming request, that route's `RewritePath` never executes.
2. **Modify only the component that needs changing.** When the goal is simply removing a path prefix, replace the path instead of rebuilding the entire scheme, authority, and query.
3. **Verify at the backend.** Even if the Gateway transforms the path properly, proxies in front/behind or the backend framework may normalize paths differently.

## 4. RewritePath with Query Strings Preserved

`RewritePath` takes a regex and a replacement. Example route on **Spring Cloud Gateway Server WebFlux**:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-v1
              uri: http://localhost:9001
              predicates:
                - Path=/api/v1/**
              filters:
                - RewritePath=^/api/v1(?<suffix>/.*)$, $\{suffix}
~~~

Meaning:

- `Path=/api/v1/**` matches requests under the public prefix.
- Regex `^/api/v1(?<suffix>/.*)$` captures the suffix starting with the **first slash** after `/api/v1`.
- Replacement `$\{suffix}` uses the capture group as the new path. In Gateway YAML, the backslash before the curly brace handles Spring's placeholder syntax; verify against your running version.
- `uri` is the test backend address. You must have a backend running on `localhost:9001` to observe responses.

Assuming a request passes through the Gateway with no other component actively rewriting the URL, the expected results are:

| Request to Gateway | Backend raw path | Expected raw query |
| --- | --- | --- |
| `/api/v1/items/42` | `/items/42` | None |
| `/api/v1/items/42?lang=vi` | `/items/42` | `lang=vi` |
| `/api/v1/items/42?tag=a&tag=b` | `/items/42` | `tag=a&tag=b` |
| `/api/v1/items/blue%20shirt?q=a%2Bb` | `/items/blue%20shirt` | `q=a%2Bb` |
| `/api/v1/?page=2` | `/` | `page=2` |
| `/api/v1/items/a%2Fb?x=1` | Depends on how HTTP stack handles encoded slashes | `x=1` if request is accepted |

**Why does the query normally remain unchanged?** When a filter mutates only the path, the URI's query component does not need to be parsed or re-serialized. The query travels along with the request to the upstream. Still, this is **behavior to verify across the full stack** when ingress controllers, proxies, custom filters, or query-adding filters are present.

### Analyzing the named capture group

~~~text
Regex:       ^/api/v1(?<suffix>/.*)$
Raw path:    /api/v1/items/42
suffix:      /items/42
Result:      /items/42
~~~

This regex **does not match `/api/v1` without a trailing slash**. If the API must support both `/api/v1` and `/api/v1/`, explicitly handle the root case rather than assuming the framework appends a slash automatically.

**Version note:** The `spring.cloud.gateway.server.webflux.routes` structure is used in several newer Spring Cloud Gateway Server WebFlux lines; other versions use `spring.cloud.gateway.routes`. Use the namespace and starter compatible with your application, and distinguish Gateway Server WebFlux from Server Web MVC.

## 5. How Do StripPrefix, SetPath, and PrefixPath Differ?

Not every path change needs regex. Pick the simplest filter that expresses the API contract:

| Filter | Goal | Example |
| --- | --- | --- |
| `StripPrefix=2` | Drop first two segments | `/api/v1/items/42` → `/items/42` |
| `PrefixPath=/internal` | Prepend path prefix | `/items/42` → `/internal/items/42` |
| `SetPath=/products/{id}` | Build path from matched template | `/api/v1/items/42` → `/products/42` |
| `RewritePath` | Apply regex and replacement | `/api/v1/items/42` → `/items/42` |

### Use StripPrefix for fixed prefixes

~~~yaml
predicates:
  - Path=/api/v1/**
filters:
  - StripPrefix=2
~~~

`StripPrefix=2` removes `api` and `v1` before forwarding. This is concise and readable, yet you still must verify segment counts on root paths, extra slashes, and encoded paths, because passing through URI parsers can affect segment splitting.

### Use SetPath when predicates supply URI variables

~~~yaml
predicates:
  - Path=/api/v1/items/{id}
filters:
  - SetPath=/products/{id}
~~~

`Path` captures the `id` variable and `SetPath` inserts it into the target path. This fits explicit templates well. If `id` contains percent-encoding or encoded slashes, test how route pattern matching and template expansion handle the value; do not assume every byte stays identical to raw-path operations.

### Use PrefixPath when the backend has a different context path

~~~yaml
predicates:
  - Path=/assets/**
filters:
  - PrefixPath=/internal
~~~

`/assets/logo.svg` becomes `/internal/assets/logo.svg`. When combining multiple filters, execution order determines the final path. Avoid stacking multiple `StripPrefix` or `RewritePath` filters unless it is clear which path each step receives.

## 6. Preserving Repeated Query Parameters and Raw Query Representation

When changing only the path, avoid accidentally altering the query:

~~~text
Input : /api/v1/items/42?tag=a&tag=b&search=a%2Bb&empty=&flag
Output: /items/42?tag=a&tag=b&search=a%2Bb&empty=&flag
~~~

Details that can matter:

- **Repeated keys:** `tag=a&tag=b` is not equivalent to a map retaining only `tag=b`.
- **Empty values:** `empty=` and `flag` represent distinct forms; do not normalize them unprompted.
- **Order:** many APIs ignore query parameter order, while URL-signing systems or caches may depend on a canonical form.
- **Encoding:** `search=a%2Bb` and `search=a+b` may not mean the same thing to every parser. `+` is often decoded as a space in `application/x-www-form-urlencoded` contexts, whereas `%2B` represents a literal plus sign.
- **Empty question mark:** a URI ending in `?` and a URI with no query can differ in representation; avoid altering it unnecessarily.

### Inspecting the raw query in WebFlux

Where you have a `ServerHttpRequest request`:

~~~java
import java.net.URI;
import org.springframework.http.server.reactive.ServerHttpRequest;

URI uri = request.getURI();
String rawPath = uri.getRawPath();
String rawQuery = uri.getRawQuery();
// rawQuery can be null if the URI has no query.
~~~

`getRawQuery()` returns the undecoded representation **as received by the application**. It does not prove every byte arrived untouched from the browser through CDN/ingress. When you need logical values, `request.getQueryParams()` is available; however, if the goal is simply preserving the raw query, avoid parsing and re-serializing it.

Filters such as `AddRequestParameter`, custom URI-mutating filters, or reverse-proxy query-rewrite rules can intentionally modify parameters. Distinguish **RewritePath's path-only behavior** from the **behavior of the full processing chain**.

## 7. Leading Slashes, Trailing Slashes, Root Paths, and Duplicate Slashes

The `/` character separates path segments; its presence or absence can affect routing, resource resolution, and access control.

| Input path | Question to decide | Risk |
| --- | --- | --- |
| `/api/v1` | Map to `/` or use a separate route? | A regex requiring a trailing slash will not match |
| `/api/v1/` | Does backend expect root `/` or another path? | Hits wrong controller after rewrite |
| `/api/v1/items` | Map to `/items`? | Standard case |
| `/api/v1/items/` | Preserve trailing slash? | Backend framework may treat differently from `/items` |
| `/api/v1//items` | Are duplicate slashes valid? | Proxy may collapse or reject |
| `/api/v1/items/a%2Fb` | How are encoded slashes treated? | Layers may split path segments differently |

### Explicit route for the base path

If `/api/v1` must map to the backend root, you can add a dedicated route:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-root
              order: -10
              uri: http://localhost:9001
              predicates:
                - Path=/api/v1
              filters:
                - SetPath=/

            - id: catalog-child
              order: 0
              uri: http://localhost:9001
              predicates:
                - Path=/api/v1/**
              filters:
                - RewritePath=^/api/v1(?<suffix>/.*)$, $\{suffix}
~~~

This gives `/api/v1` an explicit contract rather than relying on a child regex. For `/api/v1/`, the outcome also depends on the route matcher and the version's trailing-slash configuration; verify with tests. Never assume `//` equals `/` across all layers.

If enforcing canonical URLs, decide whether to **preserve, reject, or redirect** non-canonical slash forms. Never strip `//` across an **entire URL** with naive string replacement, or you will corrupt `https://`.

## 8. Percent-Encoding and Double Decode/Encode Bugs

Percent-encoding uses `%` followed by two hex digits to represent a byte. Many characters require encoding because they carry syntactic meaning in URIs.

| Character | Representation | Key reminder |
| --- | --- | --- |
| Space | `%20` | Never place raw spaces in a request-target |
| Slash inside segment data | `%2F` | May be interpreted as a path separator if decoded |
| Question mark in path | `%3F` | Improper decoding/concatenation can start a query |
| Hash sign | `%23` | Avoid creating fragments at the wrong layer |
| Percent sign | `%25` | Multiple decodes can synthesize new escape sequences |
| Plus sign | `%2B` | Do not confuse with spaces in form-urlencoded queries |
| Letter "á" | `%C3%A1` (UTF-8) | Unicode characters can span multiple bytes |

**Bug 1 — Decoding paths before routing:** If `/items/a%2Fb` turns into `/items/a/b`, one segment can be parsed as two. Checking security one way while the backend interprets it another creates risk.

**Bug 2 — Double encoding:** If `%20` is encoded a second time, `%` becomes `%25`, turning `/blue%20shirt` into `/blue%2520shirt`.

**Bug 3 — Double decoding:** `/a%252Fb` becomes `/a%2Fb` after one decode, and `/a/b` after a second. Policies at the Gateway and service can fall out of sync.

When simply removing a prefix, use built-in filters instead of calling `URLDecoder.decode(rawPath, ...)` or `URLEncoder.encode(entireUrl, ...)`. Those two APIs implement form-encoding semantics and are unsuitable for arbitrary whole-URI transformations.

### Path variants to test for security

Test `%2F`, `%5C`, `%2E`, `%252F`, `..`, and duplicate slashes across ingress, Gateway, Spring Security, and the backend. If one layer normalizes or rejects differently from another, attackers may bypass route predicates or access controls. **The safe policy is consistent interpretation or rejecting ambiguous forms**, rather than trying to force encoded slashes through in every scenario.

## 9. Regex and Escaping Replacements in YAML

`RewritePath` uses Java regex. Named capture group `(?<suffix>...)` is referenced via `${suffix}` at the regex replacement layer. In Gateway YAML configs, the escaped form `$\{suffix}` is commonly used to keep Spring from treating the replacement as a property placeholder.

~~~yaml
filters:
  - RewritePath=^/api/v1(?<suffix>/.*)$, $\{suffix}
~~~

Full form making each argument easy to distinguish:

~~~yaml
filters:
  - name: RewritePath
    args:
      regexp: '^/api/v1(?<suffix>/.*)$'
      replacement: '$\{suffix}'
~~~

**Successful YAML parsing alone is not enough**: verify that the binder loaded the route and check the path actually received. Because `$` has meaning in both regex replacements and Spring property placeholders, missing escapes easily break configuration.

Anchor regexes tightly—for instance `^/api/v1(?<suffix>/.*)$` with start/end anchors—instead of matching `/api/v1` anywhere in the string. Unanchored patterns can mistakenly rewrite `/legacy/api/v1/items` or `/api/v12/items`.

When paths include client-controlled data, avoid overly complex regexes with nested quantifiers that risk CPU-heavy backtracking. `SetPath` consumes URI template variables from route predicates; `RewritePath` runs regex on the path. Pick the right tool for your contract and test percent-encoded values specifically.

## 10. Internal Rewrite vs. HTTP Redirect

**Rewriting** happens inside the Gateway when forwarding to an upstream: the client keeps calling the original URL. **Redirecting** returns HTTP 3xx and a `Location` header; the client can issue a new request to a different URL.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Spring Cloud Gateway
    participant S as Backend
    Note over C,S: Internal rewrite
    C->>G: GET /api/v1/items/42?lang=vi
    G->>S: GET /items/42?lang=vi
    S-->>G: 200 OK
    G-->>C: 200 OK
    Note over C,S: HTTP redirect
    C->>G: GET /old-page?lang=vi
    G-->>C: 302 Location: /new-page
    C->>G: GET /new-page (if following redirect)
~~~

Static redirect example:

~~~yaml
predicates:
  - Path=/old-docs
filters:
  - RedirectTo=302, https://docs.example.test/guide
~~~

`Location` is the configured URL. **Do not assume the original query is automatically carried over to the redirect URL.** If the contract requires preserving queries, define explicit `Location` construction using a version-appropriate feature or controlled handler. Never use a client-supplied host to construct `Location`, to prevent **open redirects**.

| Status | Method semantics |
| --- | --- |
| 301 | Permanent redirect; some legacy clients convert POST to GET |
| 302 | Temporary redirect; some clients convert POST to GET |
| 307 | Temporary redirect; following clients must preserve method and body |
| 308 | Permanent redirect; following clients must preserve method and body |

307/308 specify method preservation, yet **do not guarantee the client will follow the redirect or can replay a streaming request body**. Be cautious before requiring redirects on write APIs.

## 11. Proxies, TLS, and Forwarded Headers Can Affect URLs

In production, clients may traverse a CDN, WAF, ingress, or load balancer before reaching the Gateway:

~~~mermaid
flowchart LR
    A[Client] --> B[CDN / WAF]
    B --> C[Ingress / reverse proxy]
    C --> D[Spring Cloud Gateway]
    D --> E[Microservice]
~~~

Separate four perspectives:

- **Public URL seen by client:** may carry a different prefix from the path entering the Gateway if an ingress already rewrote it.
- **Raw path received by Gateway:** after upstream proxy hops.
- **Path after GatewayFilter:** after `RewritePath`, `StripPrefix`, or related filters.
- **Request-target received by backend:** may pass through an internal sidecar/proxy and remain subject to its HTTP stack policies.

`Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, or `X-Forwarded-Prefix` can convey original URL details **when set by a trusted proxy**. If clients are permitted to inject them and the app uses them to build redirects, wrong URLs, redirects to attacker hosts, or data leaks can result. Strip/overwrite untrusted headers at the edge, configure trusted proxies properly, and test.

**TLS termination** also matters: external requests arrive over HTTPS while internal hops to the Gateway may use HTTP. When building an absolute `Location`, determine the public scheme/host/port from trusted sources—never trust user-submitted headers.

## 12. Measuring Path and Raw Query at a WebFlux Backend

To inspect the final output, create a test backend on port `9001`:

~~~java
import java.net.URI;

import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class RequestTargetDebugController {
    record RequestTarget(String rawPath, String rawQuery) {}

    @GetMapping("/items/**")
    Mono<RequestTarget> show(ServerHttpRequest request) {
        URI uri = request.getURI();
        return Mono.just(new RequestTarget(
                uri.getRawPath(),
                uri.getRawQuery()
        ));
    }
}
~~~

This is an illustrative controller that must live inside an actual WebFlux application with an HTTP server running. It reveals the URI **received by the backend**, without proving the raw client-side URL on its own. Never expose this debug endpoint to the public Internet if queries can carry tokens or sensitive data.

Using route `catalog-v1` from Section 4:

~~~bash
# Query with repeated parameters:
curl -i --path-as-is --globoff \
  'http://localhost:8080/api/v1/items/42?tag=a&tag=b&sort=desc'

# Encoded space and plus sign:
curl -i --path-as-is --globoff \
  'http://localhost:8080/api/v1/items/blue%20shirt?search=a%2Bb'

# Trailing slash:
curl -i --path-as-is --globoff \
  'http://localhost:8080/api/v1/items/?page=2'

# Encoded slash: may be rejected by one of the layers:
curl -i --path-as-is --globoff \
  'http://localhost:8080/api/v1/items/a%2Fb?source=test'
~~~

`--path-as-is` prevents curl from normalizing dots and segments before sending; `--globoff` disables URL globbing. Neither flag **disables normalization or security policies in proxies, the Gateway, or the backend**.

| Input at Gateway | Expected raw path at backend if accepted | Expected raw query |
| --- | --- | --- |
| `/api/v1/items/42?tag=a&tag=b&sort=desc` | `/items/42` | `tag=a&tag=b&sort=desc` |
| `/api/v1/items/blue%20shirt?search=a%2Bb` | `/items/blue%20shirt` | `search=a%2Bb` |
| `/api/v1/items/?page=2` | `/items/` | `page=2` |
| `/api/v1/items/a%2Fb?source=test` | Do not assume: may be blocked or interpreted differently | `source=test` if accepted |

The values above are **test expectations**, not recorded output from running this lesson. If actual output differs, call the backend directly, then via Gateway, then via ingress to pinpoint which layer altered the path or query.

## 13. Common Errors and Diagnostics

| Symptom | Common cause | Remedy |
| --- | --- | --- |
| Query lost after rewrite | Custom filter builds new URI with path only; proxy edits query | Use path-only filters; inspect `getRawQuery()` at each hop |
| `%20` becomes `%2520` | Percent-escapes encoded a second time | Remove duplicate encoding step; choose proper URI component API |
| Encoded slash rejected | HTTP stack security policy | Clarify contract, reject consistently, or choose a different identifier |
| `/api/v1` fails regex match | Regex requires suffix starting with a slash | Add a dedicated root route or adjust regex intentionally |
| Backend returns 404 on trailing slash | Controller distinguishes `/items/` from `/items` | Align contract and test both |
| Path with `//` hits wrong route | Proxy or framework collapses or rejects duplicate slashes | Define canonical path and verify across every layer |
| `tag=a&tag=b` collapses to one parameter | Parsed into single-value map | Preserve raw query or use multi-value structure |
| `+` turns into space | Form decoding applied in the wrong place | Separate path/query semantics; test `%2B` |
| YAML replacement has `$` and fails | Wrong placeholder escape or regex | Check `$\{suffix}` syntax and verify loaded config |
| Redirect drops query | `Location` omits requested query | Define target URL construction explicitly |
| Redirect points to fake host | Trusted client-supplied forwarded headers | Validate proxy source and allowed hosts |
| Authorization differs between Gateway and backend | Inconsistent URL decoding/normalization | Test encoded paths; reject ambiguous inputs |

Never rely on HTTP `200` alone to declare a rewrite correct. The backend might return `200` even while receiving a stripped query; conversely, a `404` can originate from the backend after the Gateway chose the right route.

## 14. Comprehensive Practice Lab

**Context:** An e-commerce system's public API uses `/api/v2/products/**`. The Product service only accepts `/products/**` and supports filtering by multiple `tag` query values. The Gateway also enforces authentication, rate limiting, tracing, and TLS by design.

### Part A — Route design

1. Declare route `product-v2` with `Path=/api/v2/**` targeting Product service.
2. Choose `StripPrefix=2` or `RewritePath` to remove the prefix; explain why you picked that filter.
3. Define the contract for `/api/v2`, `/api/v2/`, and `/api/v2/products/`; do not rely on uncontrolled trailing-slash normalization.

### Part B — Testing

| Request | Verification |
| --- | --- |
| `GET /api/v2/products/42?lang=vi` | Backend receives `/products/42` with query `lang=vi` |
| `GET /api/v2/products?tag=a&tag=b` | Second `tag` parameter is not lost |
| `GET /api/v2/products/blue%20shirt?search=a%2Bb` | No double-encoded path or unintended query mutation |
| `GET /api/v2/products/` | Trailing slash handled per contract |
| `GET /api/v2/products/a%2Fb` | Accepted or rejected under an explicit policy |
| `GET /api/v2/products?empty=&flag` | Special query forms are neither dropped nor merged |

### Part C — Verifying correctness and safety

1. In a test environment, simulate a custom filter that constructs a new URI while dropping the query; observe the bug, then switch back to path-only rewriting.
2. Compare direct Gateway calls against calls through ingress to spot where slashes or encodings change.
3. Verify routing and authorization cannot be bypassed using `%2F`, `%252F`, or ambiguous paths.
4. For redirects from legacy URLs, test both GET and POST with 302/307 to observe `Location` and client method handling.
5. Record route ID, latency, status, and traces without logging tokens or sensitive raw queries.

**Success criteria:** Prefix is rewritten accurately, repeated queries are preserved, encodings are not re-processed unexpectedly, root/trailing slashes follow an explicit policy, encoded slashes behave consistently, and results are verified at the receiving backend.

## 15. Key Takeaways

- **Changing a path means changing one URI component.** Use `StripPrefix`, `RewritePath`, `SetPath`, or `PrefixPath` instead of rebuilding the full URL manually.
- **Query strings** can have repeated keys, empty values, ordering sensitivities, and percent-encoding. Avoid parsing and re-serializing when you simply want to preserve them.
- **Literal slashes and encoded slashes are not equivalent.** Root paths, trailing slashes, duplicate slashes, and `%2F` need explicit contracts and testing across every layer.
- **Raw path differs from decoded path.** Extra decoding/encoding can turn `%2F` into `/` or `%20` into `%2520`.
- **`RewritePath`** uses regex and replacement; in YAML, mind group escaping like `$\{suffix}` and the Gateway version's property namespace.
- **Internal rewrites differ from redirects.** Redirects return `Location`, may trigger a new request, and do not automatically preserve queries or methods.
- When operating a Gateway, verify the **actual URL received by the backend**, accept forwarded headers only from trusted sources, and guard consistently against encoded path variants.
