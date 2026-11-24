# Configuring CORS, Static Resources, and HTTP Caching in Spring WebFlux

## 1. Objectives and Three HTTP Concerns That Often Go Together

A Spring WebFlux application can simultaneously serve a **JSON API**, a **website/static resources**, and a **browser frontend on a different origin**. These three mechanisms are often confused because all three involve response headers:

1. **CORS (Cross-Origin Resource Sharing):** is the browser allowed to let JavaScript at origin A read a response from origin B?
2. **Static resources:** which URLs map to CSS/JS/image/HTML files, in what order are files located, and how are resources served over HTTP?
3. **HTTP caching:** may browser/CDN caches store or reuse a response, for how long, and when should `ETag`/`Last-Modified` be used to revalidate?

An API can have **valid CORS yet broken caching**, or **valid caching yet the browser still refuses to read it due to CORS**. For example:

~~~http
GET /api/public/catalog HTTP/1.1
Origin: https://app.example.test
Accept: application/json
~~~

The server may respond:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
Cache-Control: public, max-age=60
ETag: "catalog-2026-a"
Content-Type: application/json

{"edition":"2026-A","subjects":["WebFlux","HTTP"]}
~~~

`Access-Control-Allow-Origin` controls read permission via **CORS in the browser**. `Vary: Origin` informs caches that representation/response headers can vary by origin. `Cache-Control` governs how caches store and reuse the response. `ETag` allows clients to send conditional requests and receive 304 when the response has not changed.

This lesson focuses on the **Spring WebFlux reactive stack**, not Servlet Spring MVC. The complete example uses **Java 17**, **Spring Boot 3.3.5**, and `spring-boot-starter-webflux`; do not add `spring-boot-starter-web`. Some “current” Spring documentation pages target Framework 7, whereas Boot 3.3.5 manages Spring Framework 6.1.x; the code samples use APIs compatible with Spring 6.1.

### After This Lesson You Will Be Able To

- Explain origin, the same-origin policy, and CORS preflight.
- Distinguish simple CORS requests, non-simple requests, credentials, preflight, and actual responses.
- Configure `@CrossOrigin`, `WebFluxConfigurer.addCorsMappings`, and `CorsWebFilter` where appropriate without opening CORS recklessly.
- Recognize that CORS must be coordinated with **Spring Security WebFlux**, and does not replace authentication, authorization, or CSRF.
- Serve files from `classpath:/static/` and customize `ResourceHandlerRegistry`.
- Configure `Cache-Control` for static resources, avoiding overly long caching on HTML entrypoints while caching hashed JS/CSS aggressively.
- Use `ResponseEntity.cacheControl(...)`, `eTag(...)`, `lastModified(...)`, and conditional GET returning 304.
- Distinguish `Cache-Control: no-cache`, `no-store`, `private`, `public`, `max-age`, `s-maxage`, and `immutable`.
- Recognize the difference between `Access-Control-Max-Age` and `Cache-Control: max-age`.
- Write `WebTestClient` tests for preflight, rejected origins, 200/304, static files, and private caching.
- Diagnose common issues using browser Network tools, curl, CDNs, proxies, and headers.

## 2. Foundations: Origin and the Same-Origin Policy

An **origin** is defined by **scheme + host + port**. For example:

| URL | Origin | Compared to `https://app.example.test` |
| --- | --- | --- |
| `https://app.example.test/dashboard` | `https://app.example.test` | Same origin |
| `https://app.example.test:443/page` | Default HTTPS 443 | Same origin |
| `http://app.example.test/page` | HTTP instead of HTTPS | Cross-origin |
| `https://api.example.test/v1` | Different subdomain | Cross-origin |
| `https://app.example.test:8443` | Different port | Cross-origin |
| `https://cdn.example.test/app.js` | Different host | Cross-origin |

Browsers enforce the **same-origin policy** to restrict JavaScript from reading responses across origins. **CORS is the protocol servers use to tell browsers that a specific origin is permitted to read a response**, not a user authentication mechanism.

Frontend example:

~~~javascript
const result = await fetch(
  "https://api.example.test/api/public/catalog"
);
const data = await result.json();
~~~

If the page runs at `https://app.example.test`, this is a cross-origin fetch. The browser sends `Origin: https://app.example.test`. The server must return appropriate CORS response headers before JavaScript can read the JSON.

**CORS does not stop all HTTP requests from reaching the server.** curl, Postman, and server-to-server HTTP clients do not enforce browser CORS checks. If a DELETE endpoint lacks authorization, CORS blocking a malicious frontend **does not make the endpoint safe** against a direct HTTP client.

### 2.1. Origin Is Not Site, and Excludes URL Path

SameSite cookies use the **site** (schemeful site) concept, which does not fully match origin. Two subdomains can be same-site yet cross-origin. CORS governs whether browser JS can read cross-origin responses; SameSite partially governs how cookies are sent; CSRF protects against abuse of authenticated browser requests. **Never substitute one of these three mechanisms for another.**

### 2.2. Do Not Confuse CORS with CSP

- CORS is a **resource server → browser** contract for cross-origin read access.
- Content Security Policy (CSP) directives like `connect-src` and `script-src` are **document/frontend app** policies governing which sources can be loaded or connected to.
- Browsers may require both to allow the request. A valid `Access-Control-Allow-Origin` does not cause `connect-src 'self'` to allow calling external-origin APIs.
- Headers like `Cross-Origin-Resource-Policy` (CORP) and `Cross-Origin-Embedder-Policy` (COEP) serve different embedding/cross-origin isolation use cases; they are not aliases for CORS.

## 3. How Does a Typical CORS Request Work?

A GET without special request headers may be sent directly by the browser:

~~~http
GET /api/public/catalog HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Accept: application/json
~~~

Server:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
Content-Type: application/json

{"edition":"2026-A"}
~~~

The browser inspects `Access-Control-Allow-Origin`. If the origin matches and the credentials policy aligns, JavaScript can read the body. Otherwise, the browser reports a CORS error to the script even though the server may have processed the request and sent an HTTP status/body.

**Do not try to "fix CORS" by setting `mode: "no-cors"`** in `fetch`. That normally yields an opaque response whose body and headers JavaScript cannot read like a normal JSON API. Browser extensions disabling security are not production deployment solutions.

### 3.1. Request Header Origin Differs from Referer

`Origin` carries the request origin per browser semantics; `Referer` can be truncated or hidden by Referrer-Policy and is not an accurate substitute for Origin. Server CORS must use standard CORS configuration rather than manually matching strings with `request.getHeaders().getFirst("Referer")`.

### 3.2. Accessing Public Resources with curl

~~~bash
curl -i 'http://localhost:8080/api/public/catalog' \
  -H 'Origin: https://app.example.test'
~~~

You can observe the server's CORS headers. However, curl does not enforce the same-origin policy: **being able to read JSON with curl does not prove a browser can read it**. Use browser DevTools and test both preflight and actual responses when verifying CORS.

## 4. Preflight: When the Browser Asks First via OPTIONS

If a frontend sends a request outside the CORS-safelisted set, for example:

~~~javascript
await fetch("https://api.example.test/api/public/echo", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Client-Trace": "ui-demo"
  },
  body: JSON.stringify({name: "An"})
});
~~~

the browser typically sends an **OPTIONS preflight** before the actual POST:

~~~http
OPTIONS /api/public/echo HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-client-trace
~~~

Example server approval:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: Content-Type,X-Client-Trace
Access-Control-Max-Age: 600
~~~

Only after a valid preflight does the browser send the actual POST and check CORS **on the actual response**. Never treat a successful preflight as user authentication or a guarantee that the POST will succeed.

### 4.1. When Does Preflight Trigger?

Conditions that commonly trigger preflight:
- An HTTP method other than GET/HEAD/POST under Fetch constraints.
- Custom headers such as `X-Client-Trace` or `Authorization`.
- POST with `Content-Type: application/json` (not one of the safelisted Content-Types in standard cases).
- Certain other header values/types and request modes defined by Fetch.

Avoid oversimplified myths like “every POST preflights” or “GET never preflights.” For example, a cross-origin GET with `Authorization` normally requires preflight.

### 4.2. Preflight Cache vs Response Cache

| Header | Consumer | Meaning |
| --- | --- | --- |
| `Access-Control-Max-Age: 600` | Browser CORS-preflight cache | Allows reusing preflight permission checks for a duration (browsers may cap the max) |
| `Cache-Control: max-age=600` | Browser HTTP cache / shared caches per rules | Freshness of the HTTP representation, not preflight permission |
| `Expires` | HTTP caching | Expiration timestamp per HTTP semantics |
| `ETag`, `If-None-Match` | Conditional HTTP requests | Can avoid transferring the body via 304 |
| `Vary: Origin` | HTTP caches | Reuse cached response only when request headers match the variant key |

A server can send `Access-Control-Max-Age: 3600` while the JSON API itself carries `Cache-Control: no-store`. Never infer one header's behavior from the other.

### 4.3. Never Write a Custom OPTIONS Handler Returning Wildcard for Every Origin

Setting:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

is an **invalid combination for credentialed CORS requests**. With credentials, `Access-Control-Allow-Origin` must specify an explicit allowed origin, not wildcard `*`. Spring CORS validates configurations appropriately, though security reviews remain essential.

## 5. Four Key CORS Response Headers

### 5.1. `Access-Control-Allow-Origin`

Permits a specific origin or `*` when genuinely appropriate for uncredentialed public resources. With `allowCredentials(true)`, `allowedOrigins("*")` is forbidden by both spec and Spring validation. `allowedOriginPatterns` can match controlled patterns if a use case truly requires it, yet allowlisting a finite set of explicit origins is safer.

### 5.2. `Access-Control-Allow-Methods`

Used in preflight to declare which methods are permitted for cross-origin browser requests. It **does not create route mappings** on the server: allowing POST in CORS does not turn a GET-only controller into a POST endpoint, nor does it grant user permissions.

### 5.3. `Access-Control-Allow-Headers`

Permits the **request headers** the browser intends to send in the actual request, such as `Content-Type`, `Authorization`, or `X-Client-Trace`. Do not confuse it with `Access-Control-Expose-Headers`.

### 5.4. `Access-Control-Expose-Headers`

Specifies **non-CORS-safelisted response headers** that frontend JavaScript is allowed to read.

~~~javascript
const response = await fetch("https://api.example.test/api/public/catalog");
console.log(response.headers.get("ETag"));
~~~

To let browser JavaScript read `ETag`, configure `Access-Control-Expose-Headers: ETag`. A header being present on the wire does not mean fetch JS can read it unless properly exposed.

**Note:** `Set-Cookie` is a forbidden response header name and cannot be made readable to JS via `exposedHeaders("Set-Cookie")`. Cookies remain governed by their own policies.

## 6. Three Ways to Configure CORS in Spring WebFlux

### 6.1. `@CrossOrigin` on Annotated Controllers

Use when only one or a few specific endpoints need exceptions:

~~~java
@CrossOrigin(
        origins = "https://app.example.test",
        methods = {RequestMethod.GET},
        maxAge = 600)
@GetMapping("/api/public/catalog")
public Mono<Catalog> catalog() {
    return Mono.just(catalogService.current());
}
~~~

This is a **fragment**, not standalone: it requires a controller class, `Catalog`, and a service. `@CrossOrigin` at class level applies to allowed methods and can combine with global configuration; verify how class/method/global rules merge when layering policies.

Pro: policy sits close to the endpoint, easy to follow for a few exceptions. Con: hard to audit across hundreds of controllers with different origins per environment.

### 6.2. `WebFluxConfigurer.addCorsMappings`: Shared Configuration by URL Pattern

This is the standard choice for managing CORS across groups of annotated APIs:

~~~java
@Configuration
public class CorsWebConfig implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/public/**")
                .allowedOrigins("https://app.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "X-Client-Trace")
                .exposedHeaders("ETag", "X-Request-Id")
                .allowCredentials(false)
                .maxAge(600);
    }
}
~~~

**For Spring Boot**, simply add `@Configuration implements WebFluxConfigurer` **without `@EnableWebFlux`** if you want to preserve Boot's WebFlux auto-configurations. Use `@EnableWebFlux` only when intentionally taking over framework configuration and re-configuring any needed Boot integrations.

Explanation:
- `addMapping("/api/public/**")` is the path pattern covered.
- `allowedOrigins` permits only the declared frontend origin.
- `allowedMethods` covers GET and POST.
- `allowedHeaders` allows JSON plus the client's custom header.
- `exposedHeaders` lets JavaScript read ETag and server correlation headers.
- `allowCredentials(false)` disables credentialed CORS.
- `maxAge(600)` sets the **preflight cache** duration in seconds.

Never use `"*"` with `allowCredentials(true)` in production. If an API uses auth cookies, consider explicit origins, secure cookies, CSRF, and Spring Security integration.

### 6.3. `CorsWebFilter` for Functional Routes / Early Full-Stack Handling

For WebFlux.fn or when handling CORS inside the WebFilter chain, Spring provides `CorsWebFilter`:

~~~java
@Bean
CorsWebFilter corsWebFilter() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://app.example.test"));
    cors.setAllowedMethods(List.of("GET", "POST"));
    cors.setAllowedHeaders(
            List.of("Content-Type", "X-Client-Trace"));
    cors.setAllowCredentials(false);
    cors.setMaxAge(600L);

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/public/**", cors);
    return new CorsWebFilter(source);
}
~~~

This is a **fragment**: the config class and imports are omitted. Servlet `CorsFilter` is not a WebFlux reactive stack bean; use `org.springframework.web.cors.reactive.CorsWebFilter` and `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`.

**Choose one clear source of CORS policy.** Avoid accidentally enabling a global registry, `@CrossOrigin`, a `CorsWebFilter`, and gateway CORS headers simultaneously without defining precedence/overlap. That can produce duplicate/contradictory headers or inconsistent checks between preflight and actual responses.

### 6.4. Spring Security WebFlux Must Handle Preflight Before Auth

Preflight requests usually **do not carry the same authentication cookies** as actual requests. If an authentication filter blocks OPTIONS before CORS runs, the browser reports a CORS failure even when the subsequent POST would be valid.

When adding `spring-boot-starter-security` and `SecurityWebFilterChain`:
- Ensure CORS integration executes **before security authentication/authorization**, per the reactive Spring Security docs.
- Configure `CorsWebFilter` or a `CorsConfigurationSource` so Spring Security integrates with it.
- Configure `http.cors(...)` in reactive security per your Security 6.x version.
- Never disable all CSRF protection simply because a frontend is cross-origin.
- Actual GET/POST requests must still pass authentication, authorization, and object ownership checks.
- Test 200/401/403/OPTIONS with `WebTestClient` through the real filter chain.

Never copy Servlet `HttpSecurity`/`SecurityFilterChain` snippets into reactive `ServerHttpSecurity`/`SecurityWebFilterChain`.

## 7. CORS Is Not Authorization and Does Not Prevent CSRF

An endpoint with a broad `Access-Control-Allow-Origin` must still verify:
- Who is the caller, and is the token/session valid?
- Is the user permitted to read that resource ID?
- Which tenant is active?
- Do browser credentialed requests include a CSRF token for state-changing operations?
- Are rate limits and other protections enforced?

CORS primarily prevents JavaScript on disallowed origins from **reading** cross-origin responses; it does not guarantee side-effecting requests never reach the server. Form submissions, cross-site requests, and direct HTTP clients are separate threat models.

### 7.1. `credentials: "include"` Has Strict Prerequisites

Browser request:

~~~javascript
fetch("https://api.example.test/api/account/me", {
  credentials: "include"
});
~~~

To support credentialed CORS on the server:
- Allow only **explicit origins**.
- Return `Access-Control-Allow-Credentials: true` on matching responses.
- Set cookie attributes to permit cross-site sending when needed (`SameSite=None; Secure` where appropriate), noting browsers may enforce third-party cookie restrictions.
- Maintain proper CSRF and session security.
- Never return `Access-Control-Allow-Origin: *` on credentialed responses.

Even with `allowCredentials(true)` in Spring CORS, it neither creates an auth session, grants roles, nor guarantees the browser will send cookies; other configurations determine those.

### 7.2. CORS with CDNs

If the server varies `Access-Control-Allow-Origin` by incoming `Origin`, ensure the CDN never serves origin A's ACAO response to origin B. The framework can emit `Vary: Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers` where appropriate; the CDN must honor `Vary` or use a safe custom cache key.

**Never substitute `Vary: Origin` for `Cache-Control: no-store/private` on user-specific data.** Two clients on the same Origin are not the same user. CORS and cache keys are not authentication mechanisms.

## 8. Default Static Resource Serving in Spring Boot WebFlux

Spring Boot serves static resources from familiar classpath directories:
- `classpath:/static/`
- `classpath:/public/`
- `classpath:/resources/`
- `classpath:/META-INF/resources/`

Example files:

~~~text
src/main/resources/static/index.html
src/main/resources/static/css/app.css
src/main/resources/static/js/app.js
~~~

These can be served at:
- `GET /` for the welcome page `index.html` when no higher-priority route matches.
- `GET /css/app.css`.
- `GET /js/app.js`.

Spring Boot WebFlux uses `ResourceWebHandler` to serve these files. The default mapping is typically `/**`; it can be changed via `spring.webflux.static-path-pattern` and `spring.web.resources.static-locations` per the Boot version.

**Do not treat Servlet WAR's `src/main/webapp` as the standard resource location for a Boot WebFlux executable JAR.** WebFlux does not rely on Servlet WAR packaging; place files under `src/main/resources` for proper packaging.

### 8.1. Static Files Are Not View Templates

- `src/main/resources/static/index.html` is normally **raw static HTML**, not evaluated for Thymeleaf variables like a template.
- Template engines use their own `templates/` folder and view resolvers.
- JS/CSS bundlers may output files into `static/assets/`; manage cache busting and versioned filenames.
- Client-side SPA routes like `/app/settings` do not automatically fall back to `index.html` in every WebFlux setup. If an SPA fallback is needed, configure it carefully so it does not swallow `/api/**`, asset files, or real 404s.

### 8.2. Customizing Static Paths in Properties

~~~properties
spring.webflux.static-path-pattern=/assets/**
~~~

This example changes the default static resource mapping and is **not used in the runnable project below**. If enabled, update HTML asset paths and verify welcome-page behavior; do not add this property to the demo when intentionally registering a `/docs/**` resource handler.

### 8.3. Can Static Resources Require CORS?

Yes. A browser fetching a static file from JavaScript across origins can require CORS, whereas HTML tags like `<img src>` or `<script src>` follow different loading/rendering rules. If a frontend fetches fonts or assets via a CDN, configure CORS for those asset URLs or at the CDN. Never assume a `/api/**` CORS mapping covers `/assets/**`.

## 9. `ResourceHandlerRegistry`: Custom Routes for Static Resources

WebFlux provides `WebFluxConfigurer.addResourceHandlers`:

~~~java
@Override
public void addResourceHandlers(ResourceHandlerRegistry registry) {
    registry.addResourceHandler("/docs/**")
            .addResourceLocations("classpath:/docs/")
            .setCacheControl(
                    CacheControl.maxAge(Duration.ofMinutes(5))
                            .cachePublic());
}
~~~

When the application packages `src/main/resources/docs/guide.txt`, `GET /docs/guide.txt` reads the matching resource. `max-age=300` bounds HTTP cache freshness in this example; `public` allows shared caches to store the response unless otherwise constrained.

### 9.1. Key Parts

- `addResourceHandler("/docs/**")`: URL pattern accepted by the server.
- `addResourceLocations("classpath:/docs/")`: source directory root, not the client URL.
- `setCacheControl(...)`: HTTP cache policy for resources served by that handler.
- Resource resolvers and transformers can participate in cache-busting/versioned URLs, compressed resources, and path resolution.

Never pass a filesystem path from a query parameter straight to a resource loader without path validation. Keep Spring's path-traversal protections intact; never disable normalization checks to "work around" an awkward path.

### 9.2. Metadata, 304, and `Last-Modified`

Resource handlers can use metadata like last-modified to support conditional requests: clients send `If-Modified-Since`, and the server can return **304 Not Modified** if the file has not changed and preconditions match. Do not assume all resource types (files inside JARs, cloud objects, dynamically generated files) carry equally accurate last-modified timestamps.

`Cache-Control` expresses the caching policy; `Last-Modified` and `ETag` provide validators. Browsers can reuse a fresh cached asset **without sending any request**; once stale, they can send a conditional request rather than re-downloading the full bytes.

### 9.3. Never Long-Cache Resources with Unversioned URLs

If `/js/app.js` keeps the same URL across deployments while you set `Cache-Control: public, max-age=31536000, immutable`, clients may run stale JS for a long time. For frequently changing files, use short `max-age` values with validators, or deploy content-hashed filenames.

## 10. Versioned Assets and Long-Term Cache Policies

Frontend build tools commonly emit:

~~~text
/assets/app.f2a21c6a.js
/assets/app.83e4d9cd.css
/assets/logo.9da430ef.svg
~~~

When filenames reflect content hashes and builds/deployments keep older assets available during rollout windows, a long cache policy works well:

~~~http
Cache-Control: public, max-age=31536000, immutable
~~~

Meanwhile, `index.html` should typically use:

~~~http
Cache-Control: no-cache
ETag: "index-build-20261021"
~~~

so each time the browser revalidates the entrypoint, it picks up updated references to hashed assets.

**`no-cache` does not mean "forbid storing."** It allows storing while requiring revalidation before reuse. `no-store` is the directive forbidding compliant HTTP caches from storing the response, suited for sensitive data.

### 10.1. `VersionResourceResolver` in WebFlux

Spring WebFlux includes a resource chain where `VersionResourceResolver` can serve content-hashed or fixed-version resource URLs:

~~~java
registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/static/assets/")
        .resourceChain(true)
        .addResolver(new VersionResourceResolver()
                .addContentVersionStrategy("/**"));
~~~

This is a **fragment** for a different use case—do not combine it with the `/docs/**` demo below. If the frontend requests `/assets/app.js` while the server expects `/assets/app-<hash>.js`, you need a matching build/URL-rewriting step or `ResourceUrlProvider`. **Do not assume enabling the resolver automatically rewrites HTML/JS links in every WebFlux view.**

When combining compressed resolvers (`EncodedResourceResolver`) with versioning, Spring docs emphasize ordering so hashes are computed from **uncompressed** bytes. Use a resource chain thoroughly tested with gzip/Brotli and CDNs; never assign identical strong ETags to different representations carelessly.

### 10.2. Long CDN Caches Need an Old-Asset Retention Strategy

Old HTML may still reference `app.oldhash.js` right after a deployment. If the server/CDN deletes old assets immediately, users with open tabs break. A hashed-asset deployment strategy should ensure:
- Old files remain available during the compatibility window.
- CDN purges do not accidentally delete content-addressed files still referenced by active clients.
- HTML entrypoints use validators or short freshness.
- Atomic builds and rollbacks never produce “new HTML + missing old assets.”
- Critical security patches have an explicit invalidation plan.

## 11. HTTP Caching: Fundamental Concepts

A cache may be:
- A browser private cache.
- A shared proxy/CDN cache.
- An application reverse proxy.
- A Service Worker cache (separate mechanism managed by script).
- An application-level cache like Spring Cache/Redis (does not automatically follow HTTP headers).

These layers **do not automatically share cache keys or eviction policies**. `@Cacheable` in a service does not emit HTTP `Cache-Control`/ETag headers. Conversely, `Cache-Control: no-store` on an HTTP response does not automatically evict entries in Redis or a database.

### 11.1. `Cache-Control` Directives

| Directive | Core meaning | Use when |
| --- | --- | --- |
| `no-store` | Compliant HTTP caches must not store request/response | Sensitive data or when HTTP caching is forbidden |
| `no-cache` | May be stored, yet must revalidate before reuse | HTML entrypoints, content needing freshness checks |
| `private` | Shared caches must not store; private caches may | Personal data where browser caching is permitted |
| `public` | Allows shared caches to store if other rules permit | Public assets/data |
| `max-age=N` | Freshness lifetime in seconds | Rarely changing public resources |
| `s-maxage=N` | Shared-cache freshness, overriding max-age for shared caches | Dedicated CDN/proxy policy |
| `must-revalidate` | Restricts serving stale without revalidation | Content with strict staleness rules |
| `immutable` | Hints not to revalidate while fresh because representation is immutable | Content-hashed assets |
| `no-transform` | Instructs intermediaries not to alter the representation | Content that must remain intact |

Never assume `Cache-Control: public` guarantees CDN caching: Authorization headers, cookies, status codes, cache keys, CDN rules, `Vary`, and other headers still apply. Never put user-specific data into a public cache through misunderstanding `public`.

### 11.2. Fresh vs Stale

Suppose:

~~~http
Cache-Control: public, max-age=60
~~~

During the fresh window, a cache can serve the stored response without contacting the origin (provided it cached it and conditions still hold). Afterward the response becomes stale, and the client/cache may need conditional revalidation.

A response with `no-cache` can still be **stored**, yet must be revalidated before reuse; do not treat it as an absolute "disable browser cache."

### 11.3. HTTP Cache Keys and Query Strings

`/api/public/catalog?lang=vi` and `?lang=en` are two distinct target URIs in the standard cache model, though a CDN might be configured to ignore query params. For responses varying by `Accept-Language` or `Origin`, emit the proper `Vary` header. Never rely on theoretical cache keys when a gateway/CDN overrides them.

## 12. Conditional GET: `ETag`, `Last-Modified`, and 304

### 12.1. The 200 → If-None-Match → 304 Sequence

First request:

~~~http
GET /api/public/catalog HTTP/1.1
~~~

Response:

~~~http
HTTP/1.1 200 OK
ETag: "catalog-2026-a"
Cache-Control: public, max-age=60
Content-Type: application/json

{"edition":"2026-A","subjects":["WebFlux","HTTP"]}
~~~

When the cache needs to revalidate:

~~~http
GET /api/public/catalog HTTP/1.1
If-None-Match: "catalog-2026-a"
~~~

If the server determines the representation is unchanged:

~~~http
HTTP/1.1 304 Not Modified
ETag: "catalog-2026-a"
Cache-Control: public, max-age=60
~~~

304 carries no new JSON response body; the cache/browser reuses its stored body with updated metadata if eligible. **304 is not a 200 with an empty body.** A hand-written HTTP client lacking a cache can still receive 304 with no JSON bytes to parse—it needs a prior cached representation or different handling.

### 12.2. Strong vs Weak ETags

- A strong ETag looks like `"abc123"`, acting as a strong validator per byte-for-byte representation rules.
- A weak ETag looks like `W/"abc123"`, useful for semantic equivalence when bytes may vary.
- An ETag is an **opaque token**, not a hash the browser interprets. Never leak private state or internal database secrets inside it.
- Using the same ETag for two distinct JSON representations (e.g., different languages or media types) violates semantics; derive ETags per representation alongside `Vary`.

In Spring WebFlux, `ResponseEntity.BodyBuilder.eTag("catalog-2026-a")` normalizes quotes to form a valid ETag. Do not manually add extra layers of quotes unchecked.

### 12.3. Last-Modified

~~~http
Last-Modified: Thu, 01 Oct 2026 00:00:00 GMT
~~~

Clients can send `If-Modified-Since`. HTTP dates have one-second resolution, making multiple updates within the same second hard to distinguish; version-based ETags are typically more reliable for granular updates.

When a client sends both `If-None-Match` and `If-Modified-Since`, HTTP semantics specify an evaluation precedence order; **do not arbitrarily combine both into an AND condition yourself**.

### 12.4. 304 Does Not Bypass Authorization

If a resource depends on user/tenant, the server must still verify authentication and authorization on revalidation requests. An unauthorized attacker must never receive 304 and exploit stale cached content belonging to someone else. 304 and ETags save bandwidth, not permission checks.

### 12.5. Preconditions for Writes

`If-Match`/ETag also enables optimistic concurrency on PUT/PATCH/DELETE; the server can return **412 Precondition Failed** if the resource changed. This differs from GET `If-None-Match` → 304. Updates must compare versions atomically within a transaction rather than checking an ETag and updating the database asynchronously later.

## 13. Using `CacheControl` and `ResponseEntity` in Spring WebFlux

Spring's `CacheControl` builds response headers for common cases:

~~~java
CacheControl cache = CacheControl.maxAge(Duration.ofSeconds(60))
        .cachePublic();
~~~

Controller returns:

~~~java
@GetMapping("/api/public/catalog")
public ResponseEntity<Catalog> catalog() {
    return ResponseEntity.ok()
            .cacheControl(cache)
            .eTag("catalog-2026-a")
            .body(new Catalog("2026-A", List.of("WebFlux", "HTTP")));
}
~~~

This is a fragment (`Catalog` class and `cache` variable are omitted); the runnable demo in section 17 declares everything in full. In WebFlux you can also use `Mono<ResponseEntity<T>>` when metadata/status/body are known only after async work. Never call `.block()` just to prepare a cache policy inside a controller.

### 13.1. Spring Handles Conditional Requests When ResponseEntity Includes Validators

Spring WebFlux can evaluate conditional GET/HEAD requests against the ETag/lastModified returned by a controller and return 304 when preconditions match. Configuration must match contract, method, and version. Use `WebTestClient` with `If-None-Match` to verify behavior rather than guessing.

### 13.2. Personalized APIs: `no-store`

~~~java
@GetMapping("/api/example-sensitive")
public ResponseEntity<Map<String,String>> sample() {
    return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of("sample", "not real user data"));
}
~~~

This is a fragment. `no-store` suits highly sensitive HTTP responses, yet it does not stop server logs or users copying information manually. If a response contains real personal data, authentication plus object/tenant authorization remain prerequisites.

### 13.3. Shared Caches with `Authorization`

RFC 9111 defines restrictions and exceptions for shared caches on responses to requests carrying `Authorization`. Never set `Cache-Control: public` or `s-maxage` on credentialed resources with personalized bodies without a carefully reviewed cache-key and security architecture.

Multiple users can call the same `/api/me` URI; if a CDN caches by URI alone, both risk receiving the same body. `Vary: Origin`, `Vary: Accept`, or `Vary: Authorization` are not complete substitutes for tenant/user isolation and safe caching policies. Use `private` or `no-store` according to sensitivity.

## 14. CORS and Caching Have Subtle Interactions

### 14.1. Public APIs Varying by Origin

A server can echo an allowlisted request `Origin` and send `Vary: Origin`. If a shared cache ignores `Vary` or a CDN custom cache key omits Origin, it may serve origin A's response to origin B, triggering browser CORS errors or policy violations.

CORS states only which origins may read via JS. An ACAO header for `app.example.test` **does not** mean the data is safe to store in a shared cache. If data is user-dependent, evaluate `Cache-Control` independently.

### 14.2. Vary: Accept-Encoding and Versioned Assets

Compressed resources have gzip/Brotli variants; when representations depend on `Accept-Encoding`, `Vary: Accept-Encoding` governs cache selection. Never serve the same strong ETag for compressed and uncompressed bytes if doing so violates strong-validator semantics.

### 14.3. Browser Preflight Cache Does Not Replace ETag Validation

CORS preflight permissions may be cached for 600 seconds, yet the same client can send conditional GETs whenever HTTP revalidation is needed. The browser may skip OPTIONS while still sending GET and receiving 304. The two caches are independent; never share invalidation assumptions between them.

### 14.4. CORS Headers in 304 Responses

A conditional request from a cross-origin frontend is still subject to CORS. If a 304 response loses `Access-Control-Allow-Origin`/`Vary` through a gateway or cache, the browser may reject the response. Test **both** 200 and 304 with an `Origin` header in integration and CDN tests.

## 15. Which Settings Apply to Static Files vs APIs?

| URL scope | Response kind | CORS | Suggested HTTP cache |
| --- | --- | --- | --- |
| `/api/public/**` | Public JSON, no secrets | Allowlist needed frontend origins | Short freshness + ETag |
| `/api/account/**` | Authenticated data | Explicit origin + credentials if needed | `no-store` or `private` per policy |
| `/docs/**` | Public doc files | CORS needed only if browser JS fetches cross-origin | Short `max-age`, validators |
| `/assets/**` hashed | Public JS/CSS/images | Per CDN/font/fetch needs | `public, max-age=31536000, immutable` when filenames are truly content-addressed |
| `/index.html` | Frequently updated entrypoint | Usually same-origin | `no-cache` or short freshness + validators |
| `/api/admin/**` | Administration | Restrict origins; never open to all sites | `no-store`; auth and authorization mandatory |

**Never apply a global `Cache-Control: public` to every URL**, as it can accidentally cover 401/403/PII/error responses. Likewise, never put `@CrossOrigin(origins="*")` on all controllers just to silence frontend dev errors.

## 16. Runnable Demo: Java 17 + Spring Boot 3.3.5 WebFlux

The small app implements:
- `GET /api/public/catalog`: stable JSON response, `Cache-Control: public, max-age=60`, `ETag: "catalog-2026-a"`, fixed `Last-Modified`.
- `POST /api/public/echo`: reads small JSON via `@RequestBody Mono<HelloRequest>` and returns JSON; used to test CORS preflight.
- `GET /api/example-sensitive`: fixture containing no PII, demonstrating `Cache-Control: no-store`.
- `GET /docs/guide.txt`: public file from classpath, cached 5 minutes via `ResourceHandlerRegistry`.
- `GET /`: `static/index.html` served by Spring Boot auto-config.
- `WebFluxConfigurer`: strict CORS allowlist for `/api/public/**`, custom static handler for `/docs/**`.
- `WebTestClient`: verifies valid/invalid origins, POST preflight, ETag/304, static content, and `no-store`.

The app has no auth or database because the focus is CORS/static/caching. Never treat `example-sensitive` as an example of protecting real user data; in production add Spring Security and resource-level authorization.

~~~text
webflux-cors-static-cache/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/cacheweb/
    │   │   ├── CacheWebApplication.java
    │   │   ├── config/WebFluxHttpConfig.java
    │   │   └── web/CatalogController.java
    │   └── resources/
    │       ├── static/index.html
    │       └── docs/guide.txt
    └── test/java/com/example/cacheweb/
        └── CorsStaticCacheIntegrationTest.java
~~~

### 16.1. Gradle and Java

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-cors-static-cache'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Do not add** `spring-boot-starter-web`: when both MVC and WebFlux starters are present, Spring Boot typically picks the MVC application type; this example requires WebFlux with Reactor Netty. Generate the Gradle wrapper with a Gradle version compatible with Java 17/Boot 3.3.5 if `gradlew` is not already present.

### 16.2. Main Application

`src/main/java/com/example/cacheweb/CacheWebApplication.java`:

~~~java
package com.example.cacheweb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CacheWebApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheWebApplication.class, args);
    }
}
~~~

### 16.3. WebFlux HTTP Config: CORS and Static Files

`src/main/java/com/example/cacheweb/config/WebFluxHttpConfig.java`:

~~~java
package com.example.cacheweb.config;

import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class WebFluxHttpConfig implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/public/**")
                .allowedOrigins("https://app.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "X-Client-Trace")
                .exposedHeaders("ETag", "X-Request-Id")
                .allowCredentials(false)
                .maxAge(600);
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/docs/**")
                .addResourceLocations("classpath:/docs/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofMinutes(5))
                                .cachePublic());
    }
}
~~~

Omit `@EnableWebFlux` to keep Boot auto-config. The CORS mapping applies only to `/api/public/**`, without opening origins for `/api/example-sensitive` or `/docs/**`. If browser JavaScript needs to fetch `/docs/**` cross-origin, add a separate reviewed CORS policy rather than assuming public cache implies CORS.

### 16.4. Controller: ResponseEntity, ETag, Last-Modified, no-store

`src/main/java/com/example/cacheweb/web/CatalogController.java`:

~~~java
package com.example.cacheweb.web;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class CatalogController {

    public record Catalog(String edition, List<String> subjects) {}
    public record HelloRequest(String name) {}
    public record HelloResponse(String greeting) {}

    private static final String CATALOG_VERSION = "catalog-2026-a";
    private static final Instant UPDATED =
            Instant.parse("2026-10-01T00:00:00Z");

    @GetMapping(
            path = "/public/catalog",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Catalog> catalog() {
        Catalog data = new Catalog(
                "2026-A", List.of("WebFlux", "HTTP"));

        return ResponseEntity.ok()
                .cacheControl(
                        CacheControl.maxAge(Duration.ofSeconds(60))
                                .cachePublic())
                .eTag(CATALOG_VERSION)
                .lastModified(UPDATED)
                .body(data);
    }

    @PostMapping(
            path = "/public/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<HelloResponse>> echo(
            @RequestBody Mono<HelloRequest> body) {

        return body.map(request -> {
            String name = request.name();

            if (name == null || name.isBlank()
                    || name.length() > 50) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Invalid name");
            }

            return ResponseEntity.ok()
                    .cacheControl(CacheControl.noStore())
                    .body(new HelloResponse(
                            "Hello, " + name.trim()));
        });
    }

    @GetMapping(
            path = "/example-sensitive",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, String>> noStoreExample() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                        "note", "Fixture only; no personal data"));
    }
}
~~~

**Points to verify in the code:**
- `CATALOG_VERSION` and `UPDATED` are hypothetical metadata **kept stable because the catalog fixture is fixed**. When a real catalog changes, ETag/version and lastModified must change with the content.
- `.eTag(CATALOG_VERSION)` is normalized by Spring into `"catalog-2026-a"`.
- `.cacheControl(...)` sets the Cache-Control response header; it does **not** add `Vary: Origin` on its own—that comes from CORS processing.
- `.lastModified(UPDATED)` adds Last-Modified, enabling `If-Modified-Since` where appropriate.
- `ResponseEntity<Catalog>` decides status/headers/body synchronously, fitting here because the fixture has no async call. With a reactive service, use `Mono<ResponseEntity<Catalog>>` when metadata comes from a reactive publisher.
- POST `echo` returns `no-store` because it is an input-driven response; in practice an echo could contain PII and must not be cached.
- `@RequestBody Mono<HelloRequest>` lets Spring's codec decode JSON without reading the request `Flux<DataBuffer>` twice.
- No `block()`, `Thread.sleep`, or blocking JDBC on the event loop.
- The error body from `ResponseStatusException` depends on Spring Boot error handling; sample tests assert only status 400 rather than a fixed JSON schema.
- Without a security dependency, `example-sensitive` has **no auth**; it teaches only the HTTP cache directive.

### 16.5. Default HTML Page

`src/main/resources/static/index.html`:

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>WebFlux HTTP demo</title>
</head>
<body>
  <h1>WebFlux CORS / Static / Cache</h1>
  <p>This page is served from classpath:/static/index.html.</p>
</body>
</html>
~~~

Spring Boot includes welcome-page detection; when no higher-priority `GET "/"` handler exists, `/` serves `index.html`. This is a **static HTML file**, not evaluated for Thymeleaf expressions.

### 16.6. Docs File Served by the Custom Handler

`src/main/resources/docs/guide.txt`:

~~~text
WebFlux resource guide
~~~

`GET /docs/guide.txt` reads the file via the path registered in `WebFluxHttpConfig`. `Cache-Control` is set on the ResourceWebHandler for this route; if docs must be fetched cross-origin from browser JS, configure CORS separately.

## 17. Integration Tests with WebTestClient

Uses embedded Reactor Netty on a random port to verify HTTP routing, CORS, and response headers. These are not Servlet MockMvc tests.

`src/test/java/com/example/cacheweb/CorsStaticCacheIntegrationTest.java`:

~~~java
package com.example.cacheweb;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CorsStaticCacheIntegrationTest {

    private static final String FRONTEND =
            "https://app.example.test";

    @Autowired
    WebTestClient client;

    @Test
    void publicCatalogHasExplicitCorsAndCacheHeaders() {
        client.get().uri("/api/public/catalog")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND)
                .expectHeader().valueEquals(
                        HttpHeaders.ETAG, "\"catalog-2026-a\"")
                .expectHeader().valueContains(
                        HttpHeaders.CACHE_CONTROL, "max-age=60")
                .expectBody()
                .jsonPath("$.edition").isEqualTo("2026-A")
                .jsonPath("$.subjects[0]").isEqualTo("WebFlux");
    }

    @Test
    void conditionalGetReturns304WithoutNewBody() {
        client.get().uri("/api/public/catalog")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .header(HttpHeaders.IF_NONE_MATCH, "\"catalog-2026-a\"")
                .exchange()
                .expectStatus().isNotModified()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND)
                .expectHeader().valueEquals(
                        HttpHeaders.ETAG, "\"catalog-2026-a\"")
                .expectBody().isEmpty();
    }

    @Test
    void allowedPreflightPermitsJsonPostAndCustomHeader() {
        client.options().uri("/api/public/echo")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type,x-client-trace")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND)
                .expectHeader().valueContains(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS, "POST");
    }

    @Test
    void forbiddenOriginIsRejectedByCorsProcessor() {
        client.get().uri("/api/public/catalog")
                .header(HttpHeaders.ORIGIN, "https://evil.example.test")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void actualJsonPostIsHandledAndNotCached() {
        client.post().uri("/api/public/echo")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("name", "An"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND)
                .expectHeader().valueContains(
                        HttpHeaders.CACHE_CONTROL, "no-store")
                .expectBody()
                .jsonPath("$.greeting").isEqualTo("Hello, An");
    }

    @Test
    void personalizedPolicyExampleSaysNoStore() {
        client.get().uri("/api/example-sensitive")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueContains(
                        HttpHeaders.CACHE_CONTROL, "no-store")
                .expectBody()
                .jsonPath("$.note").exists();
    }

    @Test
    void customDocsResourceIsServedWithShortPublicCache() {
        client.get().uri("/docs/guide.txt")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueContains(
                        HttpHeaders.CACHE_CONTROL, "max-age=300")
                .expectBody(String.class)
                .isEqualTo("WebFlux resource guide\n");
    }

    @Test
    void defaultBootWelcomePageServesHtml() {
        client.get().uri("/")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_HTML)
                .expectBody(String.class)
                .value(html -> {
                    if (!html.contains("WebFlux CORS / Static / Cache")) {
                        throw new AssertionError("Missing welcome content");
                    }
                });
    }
}
~~~

### 17.1. Why Is Testing 304 Important?

Testing only normal GETs does not verify whether Spring handles `If-None-Match` properly. The test above sends the previous ETag and expects:
- HTTP 304.
- Empty body.
- Consistent ETag.
- Present CORS headers for the valid frontend origin.

**In networks with a CDN**, also test through the CDN because shared caches can alter headers/cache keys or serve 304 without reaching the origin. Embedded server tests prove only application behavior.

### 17.2. Testing Preflight vs Testing the Actual POST

The preflight test sends `OPTIONS`, `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`. The actual POST test sends the JSON body and checks the echo response. The browser must be permitted at **both steps**, and security logic still runs on the actual request per architecture.

### 17.3. Why Not Assert Exact Byte-for-Byte Other Headers?

Servers/containers may add Date, Content-Length, transfer-encoding, or reorder fields. Tests should focus on HTTP semantics:
- Correct ACAO origin.
- Quoted ETag format.
- `Cache-Control` containing expected `max-age`/`no-store`.
- Empty body on 304.
- Successful GET for static files.
- Disallowed origins rejected.
- HTML content and content type.

Some headers like `Vary` can contain multiple values; when checking for `Origin`, use `contains` matching rather than assuming a single line and fixed order.

### 17.4. Running the Project

In the project folder with a valid Gradle wrapper:

~~~bash
./gradlew test
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test
.\gradlew.bat bootRun
~~~

If the project lacks a Gradle wrapper, generate it with an installed Gradle version; do not expect `settings.gradle` and `build.gradle` alone to generate `gradlew`. The demo presents complete source/build files without wrapper binaries/scripts.

## 18. Trying with curl and a Browser

### 18.1. Successful CORS Request

~~~bash
curl -i 'http://localhost:8080/api/public/catalog' \
  -H 'Origin: https://app.example.test'
~~~

Expected HTTP 200 with `Access-Control-Allow-Origin: https://app.example.test`, `Cache-Control` `max-age=60`, and ETag `"catalog-2026-a"`.

### 18.2. Revalidating the Catalog

~~~bash
curl -i 'http://localhost:8080/api/public/catalog' \
  -H 'Origin: https://app.example.test' \
  -H 'If-None-Match: "catalog-2026-a"'
~~~

Expected HTTP 304 and an empty body. `curl` does not maintain a browser-style HTTP cache, so when calling 304 directly, do not expect it to reprint the previously received JSON body.

### 18.3. CORS Preflight

~~~bash
curl -i -X OPTIONS \
  'http://localhost:8080/api/public/echo' \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-client-trace'
~~~

Expected 200 with CORS preflight approval headers. Testing a disallowed origin:

~~~bash
curl -i -X OPTIONS \
  'http://localhost:8080/api/public/echo' \
  -H 'Origin: https://evil.example.test' \
  -H 'Access-Control-Request-Method: POST'
~~~

The WebFlux CORS processor is expected to reject with 403. If Spring Security or a gateway is added, error ordering/layers may differ, so test the real deployment.

### 18.4. Actual POST

~~~bash
curl -i -X POST \
  'http://localhost:8080/api/public/echo' \
  -H 'Origin: https://app.example.test' \
  -H 'Content-Type: application/json' \
  -H 'X-Client-Trace: sample' \
  -d '{"name":"An"}'
~~~

Expected HTTP 200:

~~~json
{"greeting":"Hello, An"}
~~~

and `Cache-Control: no-store`. Note that a browser will preflight this request cross-origin; curl does not send OPTIONS automatically beforehand.

### 18.5. Static Files

~~~bash
curl -i 'http://localhost:8080/docs/guide.txt'
curl -i 'http://localhost:8080/'
~~~

`/docs/guide.txt` returns the text file with max-age 300. `/` returns HTML from static `index.html`. No manual controller is needed to serve these two files.

## 19. Debugging CORS with Chrome/Firefox DevTools

When a browser reports “blocked by CORS policy,” check in order:
1. Identify the frontend's **actual Origin** (scheme/host/port), not the backend URL.
2. Check Network: did the browser send an OPTIONS preflight?
3. If OPTIONS ran, inspect its HTTP status and `Access-Control-Allow-Origin/Methods/Headers/Max-Age`.
4. Check CORS headers on the **actual response**, including 304/401/403/500/error paths where relevant.
5. Check whether cookies are sent, `credentials` mode, `SameSite`, `Secure`, and third-party cookie policies.
6. With Spring Security, verify CORS is processed before authentication/authorization.
7. Check whether a gateway/CDN strips `Origin` or response ACAO headers.
8. If responses are cacheable, check `Vary: Origin`/cache keys.
9. Check frontend CSP `connect-src` and TLS/mixed-content rules: they can block requests independently of CORS.
10. Compare browser traffic against curl OPTIONS/actual requests with matching headers.

**CORS errors sometimes mask real underlying errors** like 401, 502, or a reverse proxy returning an HTML error lacking ACAO. Do not slap `Access-Control-Allow-Origin: *` globally; fix the upstream error path or auth/CORS integration.

## 20. HTTP Caching Troubleshooting

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Browser keeps re-downloading unchanged JS | No freshness or validators | `Cache-Control` + ETag/Last-Modified |
| New JS deployed yet browser runs old version | Unversioned URL, overly long max-age | Content-hashed filenames or short freshness |
| Old HTML points to deleted JS | Purged old assets too early | Retain old assets across compatibility window |
| 304 lacks JSON body causing parse error | HTTP client without a cache sent If-None-Match | Do not parse 304 like 200; use a proper cache store |
| Content changed yet ETag unchanged | Validator tied to wrong version/representation | Compute/update ETag with data |
| Same URL in two languages cached interchangeably | Missing `Vary: Accept-Language` or wrong CDN key | Proper Vary/custom cache key |
| Origin A's CORS response served to origin B on HIT | CDN ignored `Vary: Origin` | Configure Vary/cache key properly |
| Private profile serves another user's data | `Cache-Control: public` or non-user-keyed cache | `no-store`/`private` + security review |
| Public GET not cached despite max-age | Request/response cache constraints, auth/cookie/CDN policy | Check cache logs/headers and gateway rules |
| `no-cache` still appears in browser storage | Misunderstanding `no-cache` | Use `no-store` if storing must be forbidden |
| 304 via CDN loses ACAO | CDN/proxy rewrote headers | Test 200/304 CORS and preserve headers |
| Inaccurate Last-Modified timestamps | JAR/file metadata or clock skew | Use ETags; check resource source |
| Cached POST behaves unexpectedly | Unsafe method caching differs from GET | Follow HTTP semantics and explicit policy |
| Multiple Content-Encoding variants share wrong ETag | Representation/validator mismatch | ETag/Vary aligned with bytes/semantics |
| Static resource handler misses file | Wrong classpath location or missing packaged resource | Inspect JAR and `addResourceLocations` |
| `@EnableWebFlux` breaks Boot behavior | Took over framework config manually | Remove annotation when only `WebFluxConfigurer` is needed |
| Spring Boot runs MVC instead of WebFlux | Both `starter-web` and `starter-webflux` present | Use the right starter/application type |

### 20.1. `Vary` Alone Does Not Solve Privacy

`Vary: Origin` separates variants by origin. Users Alice and Bob on the same frontend origin can still receive each other's cached bodies if the cache key uses only URI and Origin. Sensitive data requires security plus `private`/`no-store` policies and CDN verification.

### 20.2. `Access-Control-Max-Age` Does Not Guarantee Full-Duration Browser Caching

Browsers may cap, evict, or partition preflight caches by network partition/security context. Never design a system that requires “OPTIONS only once per hour.” When optimizing preflight traffic at a proxy/edge, measure real traffic rather than treating the config value as an SLA.

## 21. Production Checklist

- [ ] Know the exact frontend origins for every environment: dev/stage/prod, scheme/host/port.
- [ ] Allow only necessary origins; never pair `credentials=true` with a wildcard origin.
- [ ] Keep allowed methods/headers/exposed headers as intentional allowlists rather than opening everything by default.
- [ ] Handle preflight before Security auth when using credentials or Authorization headers.
- [ ] Never use CORS in place of authentication, authorization, CSRF, or object ownership.
- [ ] Avoid overlapping/conflicting `@CrossOrigin`, `WebFluxConfigurer`, `CorsWebFilter`, and gateway rules.
- [ ] Test both actual and OPTIONS responses, plus 304/401/403/error paths.
- [ ] Ensure CDNs/caches honor `Origin`/`Vary` and never serve private data across users.
- [ ] Define separate HTTP cache policies for public APIs, private APIs, HTML entrypoints, and hashed assets.
- [ ] Apply long `max-age`/`immutable` caching only to content-hashed JS/CSS; retain old assets across deploys.
- [ ] Place static resources in the right classpath locations and ensure resource handlers never expose private files.
- [ ] Avoid `@EnableWebFlux` when only extending Boot defaults.
- [ ] Keep `ResponseEntity.eTag`/`lastModified` consistent with actual representations.
- [ ] Test `If-None-Match`/`If-Modified-Since` and empty-body 304 behavior.
- [ ] Ensure 304 and cached responses still enforce CORS and authorization.
- [ ] Never confuse `no-cache` with `no-store`; choose based on sensitivity.
- [ ] Never leak raw private headers/cookies/tokens into CDN logs or cache metadata.
- [ ] Write `WebTestClient` integration tests for config and header contracts.
- [ ] Verify staging with the real gateway/CDN/browser, since embedded tests do not reflect edge configs.
- [ ] Monitor CORS preflight failures, 304 ratios, cache HIT/MISS rates, stale responses, and deployment cache busting.

### Self-Check Questions

**1.** Which parts make up an Origin in CORS?

**Answer:** Scheme, host, and port (including default ports per URL semantics). Path is not part of an origin.

**2.** Is a CORS preflight an actual POST request?

**Answer:** No. The browser sends OPTIONS to ask the server whether the intended method/headers are permitted cross-origin, and sends the actual request only if approved.

**3.** Why can't `Access-Control-Allow-Origin: *` be used with credentialed CORS?

**Answer:** Browser CORS rules forbid wildcard ACAO on credentialed responses; an explicit allowed origin and `Access-Control-Allow-Credentials: true` must be used when appropriate.

**4.** Is `Access-Control-Max-Age` the same as `Cache-Control: max-age`?

**Answer:** No. The first governs the browser's preflight permission cache; the second governs HTTP representation freshness.

**5.** Does `Cache-Control: no-cache` forbid storing the body?

**Answer:** No. It permits storing while requiring revalidation before reuse. `no-store` is what instructs compliant HTTP caches not to store it.

**6.** What does `ETag` enable when paired with `If-None-Match`?

**Answer:** Client/cache revalidation; if the representation is unchanged, the server can return 304 without a body, avoiding re-transmitting the payload.

**7.** Why can hashed assets be cached longer than `index.html`?

**Answer:** URLs containing content hashes change whenever bytes change, so browsers can treat an asset URL as immutable. The `index.html` entrypoint must stay fresh enough to point to new asset versions.

**8.** Should `@EnableWebFlux` be used in every Boot WebFlux app?

**Answer:** No. When only adding configuration, use `@Configuration implements WebFluxConfigurer` without `@EnableWebFlux` to preserve Boot auto-config.

**9.** Does CORS configured for `/api/public/**` automatically apply to `/docs/**`?

**Answer:** No. Path mappings must be defined separately for docs/assets if cross-origin browser JS must access them.

**10.** Is an authenticated GET with `Vary: Origin` already safe for CDN shared caching?

**Answer:** No. Origin does not represent a user/tenant; authorization and `private`/`no-store` caching policies must be enforced independently.

**11.** When a body is already fresh in the browser cache, must it send `If-None-Match`?

**Answer:** Not necessarily. A fresh cached entry can be used directly. When revalidation is needed, the client can send a conditional request.

## 22. Official Documentation and HTTP Standards

- [Spring Framework — WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): `@CrossOrigin`, `CorsRegistry`, CorsWebFilter, credentials, origins.
- [Spring Framework — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): `WebFluxConfigurer`, static resources, `ResourceHandlerRegistry`, resource chains.
- [Spring Framework — WebFlux HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webflux/caching.html): `CacheControl`, `ResponseEntity.eTag`, `Last-Modified`, 304.
- [Spring Framework — WebFlux ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html): sync and reactive status/headers/body combinations.
- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): auto-configuration, static paths, web application type.
- [Spring Security — Reactive CORS Integration](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): preflight before security, CorsWebFilter, and security integration.
- [Spring Framework — ResourceHandlerRegistration Javadoc 6.1](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/config/ResourceHandlerRegistration.html): adding locations, cache control, and resource chains.
- [Spring Framework — CacheControl Javadoc 6.1](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/CacheControl.html): maxAge/noStore/noCache/cachePublic/cachePrivate.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): conditional requests, validators, 304, 412, ETag.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): Cache-Control, shared/private caches, Vary, freshness, revalidation.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): preflight, ACAO, credentials, and browser behavior.
- [MDN — HTTP Caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching): fresh/stale, validators, cache busting.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): reactive HTTP integration tests.

**Key takeaway:** CORS governs **cross-origin read permissions in browsers**, static resource handlers govern **file-to-URL mapping**, and HTTP caching governs **storing, reusing, and revalidating representations**. They appear together in Spring WebFlux yet solve three independent problems. Use controlled origin configurations, manage static resources via `WebFluxConfigurer`, use versioned assets for long-term caching, and use `ResponseEntity`/`CacheControl`/`ETag` for APIs; verify with `WebTestClient` alongside browser and CDN tests before real deployment.
