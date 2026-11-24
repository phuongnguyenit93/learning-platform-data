# Designing Consistent URLs with Context Path and Public Paths

When a Spring Boot application runs directly on a developer machine, a URL might simply be `http://localhost:8080/api/products/42`. When deployed behind a reverse proxy, API gateway, load balancer, or under a shared organizational prefix, however, that same endpoint may be accessed publicly at `https://api.example.test/catalog/v1/products/42` while the backend listens at `http://catalog-service:8080/catalog/v1/products/42`.

Without distinguishing **the application's path inside the Servlet container** from **the public path exposed by the gateway**, common bugs appear: 404s, duplicated or missing prefixes, redirects to `localhost:8080`, wrong HTTP/HTTPS schemes in JSON URLs, unusable cookies, inaccurate OpenAPI server URLs, or frontend paths mismatched with the backend.

This lesson belongs to the **Web Routing** group and focuses on organizing consistent URLs across **`server.servlet.context-path`**, **`@RequestMapping` paths**, **reverse proxy/API gateway prefixes**, **public paths**, and **application-generated URLs**. Examples run on **Spring Boot 3.3.x, Spring MVC/Servlet, Java 21, and Gradle**. Spring WebFlux has a different base path configuration and runtime; do not apply every Servlet property verbatim to the reactive stack.

## 1. A URL has multiple structural layers

Examine a public address:

~~~text
https://api.example.test/catalog/v1/products/42?lang=vi#details
|---|  |--------------| |---------------------| |-------| |------|
scheme       host                  path              query    fragment
~~~

Breakdown:

- **Scheme**: `https` or `http`; external clients may use HTTPS even while the backend receives HTTP from a reverse proxy.
- **Host**: `api.example.test`; the external hostname differs from an internal container name like `catalog-service`.
- **Port**: default 443 for HTTPS or internal 8080; proxies can hide backend ports.
- **Path**: `/catalog/v1/products/42`, combining the deployment prefix and resource route.
- **Query**: `lang=vi`, commonly used for filtering, pagination, or options; not synonymous with the URL path.
- **Fragment**: `#details` belongs to client-side navigation and is normally **not sent in the HTTP request-target** to the server.

Public paths require an explicit contract. For instance, an API uses host `api.example.test` and prefix `/catalog`. API versions can follow as `/v1` or `/v2`. A browser request can pass through multiple URL-transforming layers before reaching the controller.

A useful mental model:

~~~text
Browser/mobile client
    |
    | PUBLIC URL
    | https://api.example.test/catalog/v1/products/42
    v
CDN / API gateway / reverse proxy
    |
    | UPSTREAM URL (may preserve or rewrite path)
    | http://catalog-service:8080/catalog/v1/products/42
    v
Embedded Tomcat + Servlet application context
    |
    | Spring MVC lookup path
    | /v1/products/42
    v
@RequestMapping("/v1/products") + @GetMapping("/{id}")
~~~

**Public URL does not necessarily equal upstream URL.** Determine specifically whether the proxy **preserves, prepends, strips, or replaces** prefixes; this is a prerequisite before configuring context paths.

## 2. Three path layers to distinguish

In Spring Boot 3.3 + Spring MVC/Servlet, there are typically three layers:

| Layer | Example | Where configured | Responsibility |
| --- | --- | --- | --- |
| **Servlet context path** | `/catalog` | `server.servlet.context-path` | Prefix of the entire Servlet web application |
| **DispatcherServlet servlet path** | Normally `/` | `spring.mvc.servlet.path` when customization is needed | URL mapping handled by DispatcherServlet |
| **Controller mapping** | `/v1/products/{id}` | `@RequestMapping`, `@GetMapping` | Business route selected by Spring MVC |

With a simple configuration:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /catalog
~~~

and controller:

~~~java
@RestController
@RequestMapping("/v1/products")
class ProductController {
    @GetMapping("/{id}")
    public ProductView get(@PathVariable long id) {
        // ...
    }
}
~~~

the path served by Tomcat from this application is:

~~~text
http://localhost:8080/catalog/v1/products/42
                       |------| |-------------|
                       context   controller mappings
~~~

This is **illustrative controller code**, assuming `ProductView` and method body are defined. A full runnable project follows later.

**Do not repeat the context path inside `@RequestMapping`.** If the example above wrote `@RequestMapping("/catalog/v1/products")`, the application URL would become `/catalog/catalog/v1/products/42`. Likewise, do not manually prepend `/catalog` to links when using helpers that already understand the context path.

### 2.1. server.servlet.context-path affects the entire Servlet application

`server.servlet.context-path` is configured at the Servlet web application layer, not as a route annotation. Changing this value shifts the URLs of Servlet endpoints in the same application context, including REST endpoints and, depending on setup, static resources or other web components in the same context.

Do not change the context path per controller to simulate "group routing": when you need business namespaces like `/v1/orders`, `/admin`, or `/internal`, use class-level `@RequestMapping` and matching policies.

The default value is an empty (root) context path. At root, `@GetMapping("/health")` is normally reached at `/health`; with context `/catalog`, the URL becomes `/catalog/health`, aside from endpoints belonging to a separate web server/management context.

### 2.2. spring.mvc.servlet.path is not an arbitrary second context path

`spring.mvc.servlet.path` configures the path of `DispatcherServlet`, distinct from `server.servlet.context-path`. In **Spring Boot 3.3**, the common default `PathPatternParser` path-matching strategy **is incompatible with configuring DispatcherServlet with a path prefix via `spring.mvc.servlet.path`**. If a servlet path prefix is strictly required, you must evaluate a compatible matching strategy, such as `spring.mvc.pathmatch.matching-strategy=ant-path-matcher` per the documentation for your version.

Therefore, **do not create a demo configuration combining `spring.mvc.servlet.path=/api` with default matching and assume it will run reliably**. For most REST applications, `server.servlet.context-path` plus `@RequestMapping` is sufficient, easier to understand, and less infrastructure-sensitive.

### 2.3. Controller prefix is the route contract

A common pattern:

~~~java
@RestController
@RequestMapping("/v1/products")
class ProductController {
    @GetMapping("/{id}")
    public ProductView getById(@PathVariable long id) {
        // ...
    }

    @GetMapping("/search")
    public List<ProductView> search(@RequestParam String q) {
        // ...
    }
}
~~~

In this example, `/v1/products` belongs to the API route. If multiple controller groups exist, each group can use its own class-level prefix while the application's context path remains `/catalog`.

Note: URL path matching, trailing slashes, and encoded path variables follow Spring Framework 6 rules; do not expect `/v1/products/42/` to automatically match `/v1/products/42` without intentional configuration.

## 3. Internal URL formula and non-proxied example

With the default `/` Servlet mapping and no reverse proxy rewrites:

~~~text
Application URL path =
    servlet context path
    + class-level @RequestMapping path
    + method-level mapping path
~~~

Example:

| Setting | Value |
| --- | --- |
| `server.port` | `8080` |
| `server.servlet.context-path` | `/catalog` |
| Controller class-level mapping | `/v1/products` |
| Method mapping | `/{id}` |
| Method input | `id=42` |
| Backend request URL | `http://localhost:8080/catalog/v1/products/42` |

This formula is a mental model for simple cases. If custom DispatcherServlet mappings, extra Servlets, gateway rewrites, or special forwarding rules exist, analyze the corresponding layers too.

### 3.1. Three paths that are easy to misread

On an `HttpServletRequest` in a Servlet application:

- `getContextPath()`: application context path, e.g., `/catalog`.
- `getRequestURI()`: request URI path presented by the request wrapper, e.g., `/catalog/v1/products/42`; excludes the query string.
- `getServletPath()`: path portion used to identify the Servlet in the active mapping; inspect the actual Servlet mapping rather than assuming it always equals the full controller route.
- `getPathInfo()`: extra path info in certain Servlet mappings; may be `null`.
- `getQueryString()`: raw query string, e.g., `lang=vi`, excluding `?`.

When forwarded header processing is enabled, values returned by these getters can be adjusted by a **wrapper** to reflect the public request. Therefore, logs should state clearly whether a path was captured at the proxy or inside the app, and whether forwarded headers were trusted/applied.

## 4. Three deployment patterns for public prefixes behind a gateway

Suppose the API already has controller route `/v1/products/42`.

### 4.1. Pattern A: Preserve the prefix from public to backend

~~~text
Client:
  GET https://api.example.test/catalog/v1/products/42

Proxy forwards:
  GET http://catalog-service:8080/catalog/v1/products/42

Application:
  server.servlet.context-path=/catalog
  @RequestMapping("/v1/products")
  @GetMapping("/{id}")
~~~

Advantage: paths between client and backend match, making observation and testing straightforward and requiring minimal URL translation. For many systems, **this is the simplest configuration** when you control both the gateway and the application.

The proxy still needs to forward external scheme/host/port when the application generates absolute links, redirects, or `Location` headers. Otherwise, the app could emit `http://catalog-service:8080/catalog/...` even when the client connected over HTTPS.

### 4.2. Pattern B: Proxy strips the public prefix; backend runs at root

~~~text
Client:
  GET https://api.example.test/catalog/v1/products/42

Proxy strips /catalog and forwards:
  GET http://catalog-service:8080/v1/products/42

Application:
  server.servlet.context-path= (root)
  @RequestMapping("/v1/products")
  @GetMapping("/{id}")
~~~

In this pattern, the controller does not see `/catalog` from the backend URL unless the proxy passes extra metadata. **Inbound routing still works**, yet application-generated URLs, redirects, or response links risk missing `/catalog`.

If the application needs to know the public prefix, the gateway can pass `X-Forwarded-Prefix: /catalog` and the application must configure appropriate forwarded-header processing. This is not strictly required if all absolute public URLs are built from a dedicated canonical base URL without introspecting the prefix, yet the policy must be consistent.

### 4.3. Pattern C: Proxy replaces with a different prefix on the backend

~~~text
Client:
  GET https://api.example.test/shop/v1/products/42

Proxy replaces /shop with /internal:
  GET http://catalog-service:8080/internal/v1/products/42

Application:
  server.servlet.context-path=/internal
  @RequestMapping("/v1/products")
  @GetMapping("/{id}")
~~~

In this case, the client needs to see `/shop/v1/products/42`, not `/internal/v1/products/42`. Under Spring Framework mechanisms, the proxy can send `X-Forwarded-Prefix: /shop` to indicate the public prefix, and Spring processes forwarded headers to generate accurate external links.

**Do not haphazardly mix strategies:** if a proxy already preserves `/shop` and the app also sets context path `/shop`, do not add a rewrite rule causing the backend to receive `/shop/shop/...`. Assign clear ownership for every prefix: does the gateway or the application add/strip/replace it?

## 5. Public URLs and upstream URLs have different roles

Document clearly in deployment specs:

| Item | Example | Owner |
| --- | --- | --- |
| Public scheme | `https` | Ingress/TLS termination |
| Public host | `api.example.test` | DNS, gateway, public API contract |
| Public path prefix | `/catalog` | API gateway/ingress or shared convention |
| Internal service address | `catalog-service:8080` | Service discovery/Kubernetes/internal network |
| Internal context path | `/catalog` or root | Spring Boot application/server config |
| Controller route | `/v1/products/{id}` | Application API code |
| Version segment | `/v1` | API contract/versioning policy |
| Public base URL for generated links | `https://api.example.test/catalog` | Gateway trust policy or canonical config |

A common mistake is building URLs using the internal host/port instead of the external host/scheme. Specifically, `localhost` inside a container refers to that container itself, not the user's machine. Public clients cannot reach `http://catalog-service:8080/...` unless they have direct internal network access.

**Public API contracts must not depend on internal service names.** A backend can change service names, ports, or pods while keeping public URLs stable through gateway mappings.

## 6. Forwarded headers restore public request information

When a proxy terminates TLS or rewrites paths, the details Tomcat sees can differ from the client's perspective.

Common headers:

| Header | Meaning |
| --- | --- |
| `Forwarded` | Standard RFC 7239 header conveying `for`, `host`, `proto` across proxies |
| `X-Forwarded-Host` | Original host accessed by the client |
| `X-Forwarded-Proto` | Original scheme, e.g. `https` |
| `X-Forwarded-Port` | External port, e.g. `443` |
| `X-Forwarded-Prefix` | Public path prefix applied by the proxy |
| `X-Forwarded-For` | Chain of client/proxy addresses across hops |

Example:

~~~text
Public:
  https://api.example.test/catalog/v1/products/42

Backend:
  http://catalog-service:8080/catalog/v1/products/42

Headers from trusted proxy:
  X-Forwarded-Host: api.example.test
  X-Forwarded-Proto: https
  X-Forwarded-Port: 443
~~~

When Spring applies trusted forwarded headers, a request-aware URI builder can emit `https://api.example.test/catalog/...` instead of `http://catalog-service:8080/catalog/...`.

### 6.1. server.forward-headers-strategy

Spring Boot 3.3 supports these handling modes:

| Value | Practical meaning |
| --- | --- |
| `none` | Disables Boot's automatic forwarded-header handling |
| `native` | Uses the web server's native mechanism, e.g. Tomcat RemoteIpValve; supported headers and scope depend on runtime |
| `framework` | Uses Spring Framework's mechanism: `ForwardedHeaderFilter` for Servlet or `ForwardedHeaderTransformer` for WebFlux |

When only host/proto/port are needed on a runtime with full native support, `native` may suffice. For scenarios needing `X-Forwarded-Prefix` and complex URI reconstruction, `framework` is usually better suited; always test behavior against your exact Boot/Framework version and proxy.

Example **application-prod.yml** for use only behind a trusted edge proxy:

~~~yaml
server:
  forward-headers-strategy: framework
  tomcat:
    redirect-context-root: false
~~~

Setting `redirect-context-root: false` is recommended by Spring Boot when **Tomcat receives HTTPS terminated at a proxy**, so the forwarded scheme can be evaluated before Tomcat redirects to the context root. This property does not replace configuring prefixes and controller-generated URLs.

**Never enable trusting forwarded headers on a public endpoint receiving arbitrary direct traffic** without enforcing a trust boundary. Production configuration must derive from topology and operator security policies.

### 6.2. Security warning: forwarded headers can be spoofed

An arbitrary client can send:

~~~http
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
X-Forwarded-Prefix: /fake
~~~

If the server trusts them blindly, absolute URLs, redirects, cookie settings, or links in emails can be compromised. Therefore, **the edge reverse proxy at the trust boundary must strip or overwrite any `Forwarded` and `X-Forwarded-*` headers from untrusted sources**, adding only proxy-verified values.

Also restrict clients from connecting directly to the backend bypassing the gateway. Header rewriting must remain consistent across hops; never treat an unchecked client header as authoritative for the public origin.

Forwarded headers are for **URL reconstruction and network metadata**, not proof of user identity. Authentication and authorization are separate responsibilities.

## 7. X-Forwarded-Prefix: prepending, stripping, or overriding path prefixes

Spring Framework describes different scenarios:

~~~text
Override case:
  public /api/{path}        -> internal /app1/{path}
  X-Forwarded-Prefix: /api

Remove case:
  public /{path}            -> internal /app1/{path}
  X-Forwarded-Prefix: (empty value)

Insert case:
  public /api/app1/{path}   -> internal /app1/{path}
  X-Forwarded-Prefix: /api/app1
~~~

`X-Forwarded-Prefix` is not merely a static string "prepended to URLs". It expresses the **external prefix** that Spring can use to adapt wrapped request information. Once `ForwardedHeaderFilter`/framework strategy is active, the context path retrieved by a URL builder can differ from the raw internal request prior to filtering.

Verify both the **inbound path** (is the controller invoked?) and the **outbound path** (are JSON self links, `Location`, and redirects accurate public URLs?). A 200 response alone does not prove generated URIs are right.

### 7.1. Duplicated prefix error

Example:

~~~text
Expected: https://api.example.test/catalog/v1/products/42
Actual:   https://api.example.test/catalog/catalog/v1/products/42
~~~

Error sources:

- App sets `server.servlet.context-path=/catalog` while the controller also maps `/catalog/v1/...`.
- Gateway prepends `/catalog` even though the upstream app already has that prefix.
- Code takes a URI builder already containing the context prefix and manually appends `/catalog`.
- Forwarded prefix configuration mismatches proxy rewrite rules.

The fix is to **establish prefix ownership**, rather than randomly tweaking controller mappings. Write out a table of public → upstream → controller route and verify every segment.

### 7.2. Missing prefix error

~~~text
Expected: https://api.example.test/catalog/v1/products/42
Actual:   https://api.example.test/v1/products/42
~~~

Likely the proxy stripped `/catalog`, the backend runs at root, and the URI builder did not receive `X-Forwarded-Prefix`. If the app issues a redirect, the browser follows the wrong path and gets 404. Fix via forwarded-header processing with a clear trust boundary or a centrally managed canonical public base URL.

## 8. Generating URLs in code: never hardcode localhost or prefixes

Do not do this:

~~~java
// Anti-pattern: do not use in a multi-environment backend.
String self = "http://localhost:8080/catalog/v1/products/" + id;
~~~

On a developer machine the string looks fine, yet production uses a different domain and HTTPS. Likewise, manually concatenating `request.getContextPath()` into a URI builder that already accounts for the context path can produce a doubled prefix.

### 8.1. ServletUriComponentsBuilder

In **Spring MVC Servlet**, there is the `ServletUriComponentsBuilder` utility:

~~~java
URI self = ServletUriComponentsBuilder
    .fromCurrentContextPath()
    .path("/v1/products/{id}")
    .buildAndExpand(id)
    .toUri();
~~~

This is an illustrative fragment running **inside a Servlet request**; imports for `java.net.URI` and `org.springframework.web.servlet.support.ServletUriComponentsBuilder` are required. `fromCurrentContextPath()` pulls scheme, host, port, and context path from the active request (accounting for forwarded headers if properly handled), then appends the application route.

Example:

~~~text
Locally:
  http://localhost:8080/catalog/v1/products/42

Via trusted HTTPS gateway with same path:
  https://api.example.test/catalog/v1/products/42
~~~

**Why use fromCurrentContextPath?** Because the context path is retrieved by the framework rather than hardcoded as a string. Pick the builder method matching your scope: `fromCurrentRequestUri()` is useful when preserving the current request's URI path; `fromCurrentContextPath()` is useful when building a URI for another route in the same application context.

### 8.2. Path segments and encoding

If a path contains user-supplied text, never concatenate raw strings like:

~~~java
String unsafe = "/products/" + userInput;
~~~

A `/`, `?`, or `#` character in input can alter URL structure; furthermore, percent-encoding follows specific rules. Pass values into a URI builder and apply proper encoding:

~~~java
URI uri = UriComponentsBuilder
    .fromPath("/products")
    .pathSegment("{sku}")
    .encode()
    .buildAndExpand(sku)
    .toUri();
~~~

This is an illustrative fragment (assuming `sku` is provided, importing `UriComponentsBuilder` and `URI`). For already-encoded data or wildcard routes, check carefully to avoid **double encoding** and ensure consistent normalization across gateway and controller. Never treat URL encoding as an authorization mechanism.

### 8.3. Absolute and relative links

An API can return:

~~~json
{"self":"/catalog/v1/products/42"}
~~~

or:

~~~json
{"self":"https://api.example.test/catalog/v1/products/42"}
~~~

**Relative links** have less coupling to host/scheme and work well when clients resolve them against the right public origin. **Absolute links** are useful for HATEOAS, Location, or external integrations, yet require a trustworthy public origin.

When generating email links, webhook callbacks, or background jobs **with no HTTP request**, `ServletUriComponentsBuilder.fromCurrentContextPath()` is not a general solution because there is no active request. In those cases, use a **canonical public base URL** from environment-controlled configuration.

## 9. Redirects and Location must use public URLs

HTTP redirects and the Location header are where routing bugs surface fastest. Suppose a user visits:

~~~text
https://api.example.test/catalog/v1/products/go
~~~

If the server returns:

~~~http
HTTP/1.1 302 Found
Location: http://catalog-service:8080/catalog/v1/products/42
~~~

then the backend has leaked an internal address the browser may not be able to reach. With proper public origin and prefix, Location must be:

~~~http
HTTP/1.1 302 Found
Location: https://api.example.test/catalog/v1/products/42
~~~

You can use `ResponseEntity.status(HttpStatus.FOUND).location(uri).build()` to control the URL explicitly. For a POST that genuinely creates a resource, `201 Created` with `Location` pointing to the new resource is standard practice, provided the resource was actually created; the demo below uses a **GET 302 redirect** so it does not pretend to persist data.

### 9.1. Common redirect status codes

| Status | Brief meaning |
| --- | --- |
| 301 Moved Permanently | Resource moved permanently; clients may cache per policy |
| 302 Found | Temporary redirect; real clients may change POST to GET depending on behavior |
| 303 See Other | After an action, directs the client to GET another URI |
| 307 Temporary Redirect | Temporary redirect preserving the HTTP method per standard |
| 308 Permanent Redirect | Permanent redirect preserving the HTTP method per standard |

Do not assume redirects always preserve methods or always switch to GET. Pick the status matching the intended API/client behavior and test with real clients.

### 9.2. Prevent open redirects

Never accept `?next=https://attacker.example` and echo it straight into `Location` without validation. If a redirect accepts target URLs from clients, restrict destinations to the same application or an explicit allowlist, validating scheme/host/path properly. Unchecked forwarded hosts can also become an input vector for **host-header poisoning** in absolute redirects.

## 10. Designing consistent routes around API resources

Separate what **deployment owns** from what the **API contract owns**:

~~~text
Public prefix:         /catalog
API version:           /v1
Resource collection:   /products
Resource identifier:   /{id}
--------------------------------
Public route:          /catalog/v1/products/{id}
~~~

A clear strategy:

- `/catalog` is owned by gateway/context path.
- `/v1` is owned by API versioning policy.
- `/products` is owned by controller/resource design.
- `/{id}` is the resource identifier, validated and encoded.
- Queries like `?page=1&size=20` handle filtering/pagination without changing the base route.

Use nouns for collections and item resources in REST designs, and avoid embedding environment names (dev/staging) into public routes when hostnames already separate environments. Some systems version via hostname or media type; choose one consistent convention and document it.

### 10.1. Never put internal hostnames into business routes

Controllers should not contain `http://catalog-service:8080` or `api.example.test` inside `@RequestMapping`. That annotation takes a **path pattern**, not public origin config. Host/domain routing belongs to gateways, reverse proxies, or dedicated routing layers.

### 10.2. Avoid arbitrary per-environment paths

If local runs `/api/products`, staging runs `/staging/api/products`, and production runs `/catalog/api/products`, tests risk missing prefix bugs. Maintain an environment matrix documenting public URL, upstream path, context path, and forwarded header policy instead of letting teams guess.

## 11. Configuring Spring Boot by environment

### 11.1. Default configuration for local

**src/main/resources/application.yml**

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /catalog
~~~

Locally without a proxy, the endpoint is:

~~~text
http://localhost:8080/catalog/v1/products/42
~~~

No forwarded header configuration is needed just to run on `localhost`.

### 11.2. Configuration for production behind a trusted proxy

**src/main/resources/application-prod.yml**

~~~yaml
server:
  forward-headers-strategy: framework
  tomcat:
    redirect-context-root: false
~~~

This supplements configuration under the `prod` profile without altering the context path in `application.yml`. The proxy must forward requests to the exact upstream path and sanitize forwarding headers; the backend should accept traffic only from trusted infrastructure.

Activate the profile using environment variable `SPRING_PROFILES_ACTIVE=prod` or equivalent configuration arguments; do not enable the prod profile across all dev environments and blindly trust client-sent headers.

### 11.3. Configuring canonical base URL when there is no request

For email/async/batch jobs, you can define a custom application property:

~~~yaml
app:
  public-base-url: "https://api.example.test/catalog"
~~~

This is a **custom property** `app.public-base-url`; Spring Boot does not automatically use it to alter routing, responses, or redirects. Your application can inject it via `@ConfigurationProperties` and use it as the source for URLs generated in background jobs.

Avoid hardcoding a production public URL in Java code. Configuration sources should be managed, tested, and access-controlled.

## 12. Complete Spring Boot MVC example: public self link and redirect

The following project implements a demo product reader featuring:

1. Servlet context path `/catalog`.
2. Controller `/v1/products` and item route `/{id}`.
3. Returning JSON with a **self URL** built from the current request context.
4. An endpoint redirecting to product 42 with **Location** constructed by a URI builder.
5. MockMvc tests for internal URLs and public URLs via trusted forwarded headers.

The example does not pretend to create/modify real data: only product `id=42` exists so the focus stays on paths.

Structure:

~~~text
public-url-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/publicurl/
    │   │   ├── PublicUrlApplication.java
    │   │   └── ProductController.java
    │   └── resources/
    │       ├── application.yml
    │       └── application-prod.yml
    └── test/java/com/example/publicurl/
        └── ProductControllerTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'public-url-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/main/java/com/example/publicurl/PublicUrlApplication.java**

~~~java
package com.example.publicurl;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PublicUrlApplication {
    public static void main(String[] args) {
        SpringApplication.run(PublicUrlApplication.class, args);
    }
}
~~~

**src/main/java/com/example/publicurl/ProductController.java**

~~~java
package com.example.publicurl;

import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/v1/products")
public class ProductController {

    public record ProductView(long id, String name, URI self) {
    }

    @GetMapping(path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ProductView> show(@PathVariable long id) {
        if (id != 42L) {
            return ResponseEntity.notFound().build();
        }

        URI self = productUri(42L);
        return ResponseEntity.ok(
            new ProductView(42L, "Notebook", self));
    }

    @GetMapping("/go")
    public ResponseEntity<Void> redirectToProduct() {
        return ResponseEntity.status(HttpStatus.FOUND)
            .location(productUri(42L))
            .build();
    }

    private URI productUri(long id) {
        return ServletUriComponentsBuilder
            .fromCurrentContextPath()
            .path("/v1/products/{id}")
            .buildAndExpand(id)
            .toUri();
    }
}
~~~

Explanation:

- `@RequestMapping("/v1/products")` does not repeat `/catalog`.
- `ProductView.self` is a `URI`; Jackson normally serializes it as a URL string in JSON.
- `productUri(...)` captures the context path + public scheme/host when requests are processed under the right forwarded-header strategy.
- `GET /v1/products/go` is more specific than `/{id}`, so MVC accurately selects `/go` instead of trying to parse `go` as a `long`.
- `show(42)` returns 200 with a self link; other ids return 404 per demo data.
- `redirectToProduct()` returns 302 and `Location`, creating no resources and changing no state.

**application.yml**:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /catalog
~~~

**application-prod.yml**:

~~~yaml
server:
  forward-headers-strategy: framework
  tomcat:
    redirect-context-root: false
~~~

For real infrastructure, before enabling the prod profile, confirm the proxy strips incoming `Forwarded` and `X-Forwarded-*` headers and forwards only trusted values.

### 12.1. Running locally

With JDK 21 and a compatible Gradle version (e.g., Gradle 8.5), if the wrapper exists:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell use `.\gradlew.bat bootRun`. If the project lacks a wrapper yet Gradle is installed:

~~~bash
gradle wrapper --gradle-version 8.5
./gradlew bootRun
~~~

Test product 42:

~~~bash
curl -i http://localhost:8080/catalog/v1/products/42
~~~

Expected HTTP **200 OK** and significant JSON:

~~~json
{
  "id": 42,
  "name": "Notebook",
  "self": "http://localhost:8080/catalog/v1/products/42"
}
~~~

JSON field order, headers, and logs may differ by runtime; the value of `self` is what to verify. For a missing ID:

~~~bash
curl -i http://localhost:8080/catalog/v1/products/99
~~~

Expected HTTP **404 Not Found** because the controller rejects ID 99.

Test redirect:

~~~bash
curl -i http://localhost:8080/catalog/v1/products/go
~~~

Expected status **302 Found** and header:

~~~http
Location: http://localhost:8080/catalog/v1/products/42
~~~

Locally without forwarded-header processing, this is the right application URL. Do not expose a local server to the Internet to test trusting arbitrary forwarded headers.

### 12.2. Running behind a trusted HTTPS gateway

Suppose the proxy preserves the path:

~~~text
Client URL:
  https://api.example.test/catalog/v1/products/42

Backend URL:
  http://catalog-service:8080/catalog/v1/products/42

Trusted proxy forwards:
  X-Forwarded-Host: api.example.test
  X-Forwarded-Proto: https
  X-Forwarded-Port: 443
~~~

With `server.forward-headers-strategy=framework`, the expected `self` constructed is:

~~~text
https://api.example.test/catalog/v1/products/42
~~~

Do not add `X-Forwarded-Prefix` when public and internal prefixes are already identical unless topology and proxy policy explicitly require it. If the proxy replaces prefixes, apply `X-Forwarded-Prefix` per scenario and test the emitted self links and `Location`.

## 13. Testing URLs and Location with MockMvc

Do not test only that controllers accept the right URLs; test that responses emit the right public origins. In Spring Boot, you can run MockMvc under a Servlet app and enable the framework forwarded-header strategy **specifically inside the test context** to simulate requests from a trusted proxy.

**src/test/java/com/example/publicurl/ProductControllerTest.java**

~~~java
package com.example.publicurl;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "server.forward-headers-strategy=framework")
@AutoConfigureMockMvc
class ProductControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void localContextPathIsIncludedOnce() throws Exception {
        mvc.perform(get("/catalog/v1/products/42")
                .contextPath("/catalog"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.self")
                .value("http://localhost/catalog/v1/products/42"));
    }

    @Test
    void forwardedPublicOriginProducesPublicSelfLink() throws Exception {
        mvc.perform(get("/catalog/v1/products/42")
                .contextPath("/catalog")
                .header("X-Forwarded-Host", "api.example.test")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Port", "443"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.self")
                .value("https://api.example.test/catalog/v1/products/42"));
    }

    @Test
    void redirectLocationIncludesContextPath() throws Exception {
        mvc.perform(get("/catalog/v1/products/go")
                .contextPath("/catalog"))
            .andExpect(status().isFound())
            .andExpect(header().string(
                "Location",
                "http://localhost/catalog/v1/products/42"));
    }

    @Test
    void missingProductReturns404() throws Exception {
        mvc.perform(get("/catalog/v1/products/99")
                .contextPath("/catalog"))
            .andExpect(status().isNotFound());
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

**Why is the URL in MockMvc `http://localhost` without `:8080`?** MockHttpServletRequest defaults to simulating a request on host localhost at the default HTTP port 80; it is not a real TCP request to embedded Tomcat on port 8080. When running `bootRun` and hitting port 8080 with `curl`, the URI builder sees the real request's port.

These tests verify controller routing, context paths, and forwarded origins under Spring's test setup. They **do not replace** testing against a real gateway: an ingress can strip prefixes incorrectly, duplicate headers, or rewrite hosts differently than mocked.

### 13.1. Testing the gateway from outside

In a staging environment you control, create a minimal matrix:

| Public request | Expected behavior |
| --- | --- |
| GET existing product | 200, JSON self link has accurate public scheme/host/prefix |
| GET non-existent product | 404 per API contract |
| GET redirect | 302, `Location` points to a valid public URL |
| GET over HTTP if redirecting to HTTPS | No redirect loop; Location points to HTTPS per policy |
| GET with query | Query is forwarded intact when used by the route |
| URL with wrong trailing slash | Consistent, intentional 404 or redirect |
| Request with encoded path | Not double-decoded; does not bypass authorization boundaries |
| Client attempts to spoof forwarded headers | Proxy strips/overwrites; response URLs are not poisoned |
| Public request via secondary subdomain | CORS/cookies/callbacks work if policy allows |

Never attempt spoofing tests against environments belonging to others or unauthorized public endpoints; test only in infrastructure you own.

## 14. 404 errors caused by context path, prefix, and route

Do not modify `@GetMapping` before knowing what path the request actually reaches the backend with.

An investigation workflow:

1. Confirm the exact **public request URL** (scheme, host, path, query).
2. Confirm the proxy/ingress matched the route and forwarded to the right service.
3. Inspect the **upstream request path** after rewrites.
4. Confirm the active `server.servlet.context-path` for the running profile.
5. Confirm class-level and method-level `@RequestMapping` combine accurately.
6. If using `spring.mvc.servlet.path`, verify the actual mapping and path-matching strategy.
7. Verify `DispatcherServlet` and `RequestMappingHandlerMapping` actually registered the route.
8. Verify the controller bean lies within `@SpringBootApplication` component-scan scope.
9. Distinguish 404 from **missing handler** vs. 404 from **business resource lookup**.
10. Compare direct local requests against staging requests through the gateway.

When Spring Boot cannot find an endpoint for a route, the error may surface from Spring MVC or the static resource handler depending on config. Never assume 404 is always nginx/gateway's fault or always a missing controller.

### 14.1. Common failure patterns

| Symptom | Common cause |
| --- | --- |
| `/catalog/catalog/...` | Prefix prepended twice |
| Public `/v1/products/...` missing `/catalog` | Proxy stripped prefix; app did not restore public prefix when building links |
| App only serves `/catalog/...` yet client calls `/api/...` | Public contract and proxy rewrite out of sync |
| Links point to `http://catalog-service:8080` | Missing forwarded host/proto or code hardcoded internal URL |
| Redirect from HTTPS to HTTP | Proxy terminates TLS yet app misses forwarded proto or redirects context root too early |
| Gateway returns 502/503 | Not necessarily controller mapping; could be upstream unavailable/connection error |
| Redirect loop | Gateway and app force conflicting scheme/prefix rules |
| Local 200, staging 404 | Differing context path, proxy rewrite, component scanning, route, or ingress host |

## 15. How do URLs relate to CORS, cookies, and security?

Changing public hosts/paths affects more than controller routes. Browsers and security frameworks enforce their own rules too.

### 15.1. Same-origin and CORS

Origin is determined by **scheme + host + port**, not path prefix. Two URLs sharing domain/scheme/port with `/catalog` vs. `/admin` are still same-origin; `https://app.example.test` calling `https://api.example.test` is cross-origin even if they share a prefix.

CORS policies must list trusted origins per contract rather than inferring them from `server.servlet.context-path`. CORS preflight `OPTIONS` requests can be rejected before handlers run if the gateway/Spring Security is misconfigured.

### 15.2. Cookies and session paths

A cookie's `Path` attribute decides which browser requests include that cookie. An app running under `/catalog` may need a matching cookie path; whenever a gateway changes public prefixes or moves root, inspect `Set-Cookie` and browser behavior.

Cookies are also governed by `Domain`, `Secure`, `HttpOnly`, `SameSite`, and HTTPS; changing context paths alone will not make all cookies/sessions work. Never use cookie paths as an authorization mechanism.

### 15.3. CSRF and authorization matchers

When Spring Security rules match paths, understand that matchers evaluate the **request path inside the application**, not necessarily the unrewritten public URL. When a gateway changes prefixes, security rules must protect the exact controller routes the backend receives.

A critical vulnerability occurs when a gateway allows `/catalog/admin` while an authorization rule only checks `/admin` under a mistaken assumption about context path. Test security boundaries and actual routes directly rather than guessing from URL strings.

### 15.4. Host header and forwarded header spoofing

If an application builds absolute URLs from client-controlled `Host` or `X-Forwarded-Host`, links in password resets/emails, redirects, or JSON responses can be hijacked to an attacker host. Public base URLs for security-sensitive links should come from trusted/canonical configuration rather than unverified headers.

## 16. Frontend, static assets, SPAs, and API docs

### 16.1. Frontend hosted on the same or different origin

An SPA served at `https://web.example.test/app/` may call an API at `https://api.example.test/catalog/v1/...`. Here, do not use relative paths like `/v1/products` if that sends browser requests to the wrong frontend domain. Configure the frontend's API base URL per environment, or route both behind a shared gateway origin.

If a frontend is served under `/catalog`, root-relative paths starting with `/` can drop the prefix. Align the frontend's build-time base path, router base path, and server public prefix.

### 16.2. Static assets and redirects

HTML containing `<script src="/main.js">` requests the file at the domain root without prepending `/catalog`. If an app is served under a prefix, use appropriate asset paths or configure the frontend bundler/base path; do not expect Spring MVC to rewrite links inside HTML automatically.

### 16.3. OpenAPI/Swagger servers and Try it out

If API docs generate `servers: [http://localhost:8080]` in staging/production, "Try it out" clients will hit the wrong domain/protocol. Configure the public server URL or forwarded headers properly for your OpenAPI tool. Swagger UI paths must also account for proxy/context paths; this is docs library configuration, not controller `@RequestMapping`.

### 16.4. Actuator can have a separate base path/port

`/actuator/health` does not necessarily share URL patterns with all business endpoints. When Actuator runs on the same port/context, the management base path relates to the application context path; when `management.server.port` is set separately, it can use a dedicated management context/base path.

Clearly separate **public API endpoints** from **internal monitoring endpoints**. Never expose all Actuator endpoints to the public Internet just to make a dashboard or liveness probe work.

## 17. Spring MVC/Servlet vs. Spring WebFlux: do not mix up properties

| Topic | Spring MVC/Servlet | Spring WebFlux |
| --- | --- | --- |
| Web dispatcher | `DispatcherServlet` | `DispatcherHandler` |
| Common application prefix | `server.servlet.context-path` | `spring.webflux.base-path` per Boot configuration |
| Servlet mapping | `spring.mvc.servlet.path` (has matching strategy caveats) | Not MVC's Servlet path mechanism |
| Request/response API | `HttpServletRequest`/`HttpServletResponse` | `ServerWebExchange`/reactive HTTP APIs |
| Forwarded-header support | `ForwardedHeaderFilter` with framework strategy | `ForwardedHeaderTransformer` with framework strategy |
| Default server | Tomcat with `spring-boot-starter-web` | Reactor Netty with `spring-boot-starter-webflux` |

Do not set `server.servlet.context-path=/catalog` in a reactive app and assume WebFlux routes have that prefix. Conversely, `spring.webflux.base-path` does not configure a Servlet context path for Spring MVC.

When both starters sit on the classpath, Boot normally chooses Servlet/MVC by default; confirm the active runtime before debugging prefixes.

## 18. Checklist for designing consistent URLs

Before releasing an API behind a proxy/gateway:

1. **Public:** What are the official public scheme/host/port and URL prefix?
2. **Internal:** Which port, context path, and controller routes does the backend listen on?
3. **Proxy:** Does the proxy pass-through, strip, prepend, or replace the path prefix?
4. **Forwarding:** Which `Forwarded`/`X-Forwarded-*` headers does the proxy send, and across which hops?
5. **Trust:** Does the edge proxy strip/overwrite arbitrary client-sent headers?
6. **Spring Boot:** Is `server.forward-headers-strategy` set to `none`, `native`, or `framework`, and why?
7. **Tomcat TLS:** Is `server.tomcat.redirect-context-root=false` needed in this TLS-termination topology?
8. **Mapping:** Is `server.servlet.context-path` accidentally duplicated in `@RequestMapping`?
9. **Dispatcher:** Is `spring.mvc.servlet.path` configured, and was path-matcher compatibility verified?
10. **Generated URLs:** Do JSON self links, `Location`, and redirects emit the right public origin/prefix?
11. **Requestless contexts:** Do emails, webhooks, and async jobs have a canonical public base URL?
12. **Encoding:** Are path variables/queries encoded properly without double-decoding or unsafe rewrites?
13. **Security:** Do authorization matchers, CORS, CSRF, and cookie Path/Secure align with public routes?
14. **Frontend:** Do SPA router bases, asset URLs, and API base URLs use the right prefix?
15. **Docs:** Do OpenAPI servers, Swagger UI, and API examples point to the public domain/path?
16. **Monitoring:** Are health probes and Actuator on the right port/base path with public exposure restricted?
17. **Tests:** Have direct local URLs, staging gateway URLs, 404s, redirects, and Location been tested?
18. **Observability:** Can logs distinguish public path, upstream path, and controller mapping for troubleshooting?
19. **Deployment:** Is there a reviewed matrix mapping environment → public URL → upstream URL → context path?
20. **Rollback:** Can proxy/context-path changes roll back quickly without breaking long-lived bookmarks/callbacks?

**Conclusion:** Consistent URL design requires clearly separating **the public prefix exposed by the gateway**, **the Servlet context path deployed by the application**, and **the controller mappings defined by the API**. When the proxy preserves paths, setup is straightforward; when the proxy strips or replaces prefixes, you need a strategy to reconstruct public URLs via trusted forwarded headers or a canonical base URL. Never duplicate prefixes in `@RequestMapping`, never hardcode `localhost` into links/redirects, and never trust unchecked forwarded headers. Testing both **inbound requests** and **outbound URLs** confirms the configuration works accurately across every environment.

## References

- [Spring Boot 3.3 — Embedded Web Servers / Running Behind a Front-end Proxy](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): `server.forward-headers-strategy`, TLS termination, and Tomcat redirect context root.
- [Spring Framework — Servlet Filters / Forwarded Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): `ForwardedHeaderFilter`, `X-Forwarded-Prefix`, and security/trust considerations.
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): MVC mapping, servlet path, and `PathPatternParser` compatibility.
- [Spring Framework — Spring MVC Annotated Request Mapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): class/method mappings.
- [Spring Framework — UriComponentsBuilder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html): building URIs and encoding.
