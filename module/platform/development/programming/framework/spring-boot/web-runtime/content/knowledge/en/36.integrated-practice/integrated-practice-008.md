# Placing a Spring Boot Application Behind a Reverse Proxy with Properly Scoped Forwarded Headers and CORS

A Spring Boot application may run smoothly on `http://127.0.0.1:8080`, yet when placed behind NGINX, a load balancer, or an API gateway it suddenly generates `Location` headers with the wrong hostname, redirects to HTTP even though users visit over HTTPS, drops session cookies, or triggers **CORS policy blocked** errors in the frontend. These issues do not share a single cause: they stem from **public vs upstream addresses**, **Forwarded/X-Forwarded-* headers**, **path prefixes**, **proxy trust boundaries**, **browser same-origin/CORS rules**, and **cookie/CSRF security**.

This lesson belongs to **Integrated Practice** in the Spring Boot web-runtime module. The main example uses **Java 17+, Spring Boot 3.3.x, Spring MVC/embedded Tomcat, NGINX, and a cross-origin frontend**. We build a small order create/read API exposed under public prefix `/shop`, scope CORS **strictly to the orders API and allowed origin**, and test `Location`/redirects, `OPTIONS` preflight, rejected origins, and HTTPS termination effects.

## 1. Concrete Problem and Desired Output

Suppose the system has this topology:

```text
Browser / frontend
  Origin: https://app.example.test
          |
          | fetch() over HTTPS
          v
Public reverse proxy NGINX
  https://api.example.test:443
  Public prefix: /shop
          |
          | internal HTTP, prefix stripped
          v
Spring Boot (same host in this lab)
  http://127.0.0.1:8080
  Internal root: /
  Internal route: /api/v1/orders
```

The frontend sends:

```http
POST https://api.example.test/shop/api/v1/orders
Origin: https://app.example.test
Content-Type: application/json

{"sku":"BOOK-001","quantity":2}
```

NGINX accepts public HTTPS and forwards upstream:

```http
POST http://127.0.0.1:8080/api/v1/orders
Host: api.example.test
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.test
X-Forwarded-Port: 443
X-Forwarded-Prefix: /shop
X-Forwarded-For: <client-address>
Origin: https://app.example.test
Content-Type: application/json
```

`<client-address>` is established by the trusted proxy—**never take an arbitrary client-supplied string as a verified identity**.

Upon creating the resource, the client needs to see:

```http
HTTP/1.1 201 Created
Location: https://api.example.test/shop/api/v1/orders/1
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Expose-Headers: Location, X-Request-ID
Vary: Origin
Content-Type: application/json
```

Headers may vary in order or casing, and the ID varies at runtime; `Location` above is illustrative. When a browser sends a cross-origin JSON request, an **`OPTIONS` preflight** normally runs before `POST`. Frontends from `https://evil.example.test` or `http://app.example.test` **must not** be allowed to read responses via CORS merely because of a similar domain suffix or matching API path.

**Important:** `example.test` is a reserved test domain, not a public website. To run end-to-end HTTPS locally, configure `/etc/hosts`/internal DNS and a certificate trusted by your test machine, or use an internal domain and certificate you manage.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Distinguish public URL, internal URL, client origin, target origin, and proxy hop.
2. Explain why Spring Boot sees `http://127.0.0.1:8080` while the browser sees `https://api.example.test/shop`.
3. Explain HTTP `Host`, RFC 7239 `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port`, `X-Forwarded-Prefix`, and `X-Forwarded-For`.
4. Choose `server.forward-headers-strategy=none/native/framework` accurately in Spring Boot 3.3.
5. Explain why an edge reverse proxy must strip/overwrite forwarded headers before the app trusts them.
6. Design NGINX `location /shop/` + `proxy_pass .../` with explicit prefix stripping.
7. Build `Location` and redirects from proxy-normalized request metadata rather than hardcoding internal URLs.
8. Distinguish **same-origin** vs **same-site**, simple requests, preflight, and actual CORS requests.
9. Configure Spring MVC CORS **per route and specific origin** instead of `allowedOrigins("*")` across the whole app.
10. Understand `Access-Control-Allow-Origin`, `Allow-Methods`, `Allow-Headers`, `Expose-Headers`, `Allow-Credentials`, `Max-Age`, and `Vary`.
11. Test allowed/rejected preflights, out-of-scope paths, public redirects, and real HTTP with `MockMvc` and `RANDOM_PORT`.
12. Integrate Spring Security with CORS when authentication is present.
13. Avoid confusing CORS with CSRF, authentication, authorization, firewalls, or Host spoofing protection.
14. Verify `Secure`, `HttpOnly`, `SameSite`, `Path`, and cross-site credentialed cookie flows.
15. Diagnose issues involving TLS at the proxy, HTTPS redirects, OAuth2 callbacks, ingress prefixes, CDN caching, and multi-proxy chains.

## 3. Address Types: Public Origin, Internal Origin, and Frontend Origin

In the browser security model, an **origin** is the triple `(scheme, host, port)`. The path **does not** participate in origin comparison.

| URL | Origin | Notes |
| --- | --- | --- |
| `https://api.example.test/shop/api/v1/orders` | `https://api.example.test:443` | Public API |
| `https://api.example.test/other` | `https://api.example.test:443` | Same origin despite different path |
| `https://app.example.test` | `https://app.example.test:443` | **Different origin** from API |
| `http://app.example.test` | `http://app.example.test:80` | **Different origin** due to scheme |
| `https://app.example.test:8443` | `https://app.example.test:8443` | **Different origin** due to port |
| `http://127.0.0.1:8080` | `http://127.0.0.1:8080` | Internal backend |

CORS governs which **origins** a browser allows JavaScript to read responses from across origins. It is not network access control. Non-browser clients like `curl` can still call the HTTP API directly whenever network and auth allow, even with zero `Access-Control-Allow-Origin` headers.

### 3.1. Same-Site Is Not Same-Origin

`https://app.example.test` and `https://api.example.test` are **different origins** (different hostnames), so frontend `fetch()` needs CORS. Yet under modern browsers' schemeful site definition, two hosts sharing the same registrable domain and HTTPS scheme can be **same-site**. Cookie `SameSite=Lax` and CORS are **separate** mechanisms.

Conversely, `https://shop.other-example.test` calling `https://api.example.test` is genuinely **cross-site**; sending cookies on cross-site `fetch()` typically requires `SameSite=None; Secure` alongside `credentials:"include"` and a compatible CORS credentials policy. Browsers may also restrict third-party cookies, so verify with browser E2E tests in addition to checking headers.

### 3.2. Prefix /shop Does Not Belong in the CORS Origin

Never configure `allowedOrigins("https://app.example.test/shop")`: that is not a valid origin because origins **contain no path**. API path scope is set via `CorsRegistry.addMapping(...)` or `CorsConfigurationSource`. These are two orthogonal dimensions:

- **Origin scope:** who may read responses via browser JavaScript?
- **Path scope:** which HTTP endpoints emit CORS headers?

In this lesson, the single allowed origin is `https://app.example.test`; the Java MVC paths configured for CORS are `/api/v1/orders` and `/api/v1/orders/**`. NGINX strips the public `/shop` prefix before forwarding to Spring MVC.

## 4. What Changes as a Request Traverses a Reverse Proxy?

```text
Browser request:
GET https://api.example.test/shop/api/v1/orders/7

(1) NGINX TLS listener :443
    scheme = https
    host = api.example.test
    public context prefix = /shop

(2) NGINX forwards upstream:
    GET http://127.0.0.1:8080/api/v1/orders/7
    socket scheme = http
    socket host/port = 127.0.0.1:8080

(3) Headers set by proxy:
    X-Forwarded-Proto: https
    X-Forwarded-Host: api.example.test
    X-Forwarded-Port: 443
    X-Forwarded-Prefix: /shop

(4) Spring Boot FRAMEWORK:
    ForwardedHeaderFilter normalizes request-facing
    scheme / host / port / context-path

(5) Controller:
    builds Location/redirects using the public request
```

Without forwarded header handling, a controller using `ServletUriComponentsBuilder` or `HttpServletRequest.getScheme()` sees `http`, the internal host, and no prefix—leaking internal links, redirecting to HTTP, or breaking OAuth2 callbacks.

### 4.1. Host and X-Forwarded-Host

`Host` is the HTTP/1.1 target authority; a reverse proxy may preserve the public `Host` or replace it with the upstream host. `X-Forwarded-Host` conveys the public host through proxies. Both `Host` and `X-Forwarded-Host` **are attacker-controllable inputs if the edge fails to validate or overwrite them**.

For example, an attacker sends:

```http
Host: attacker.example.test
X-Forwarded-Host: attacker.example.test
X-Forwarded-Proto: https
```

If the app reflects this host into `Location` or password-reset links, the attacker achieves **Host header injection**, phishing, or malicious redirects. Turning on `framework` alone is not enough: you must enforce a **proxy trust boundary**.

### 4.2. X-Forwarded-For Is Not Identity Proof

`X-Forwarded-For` lists client and proxy IP hops. However, leading entries can be spoofed by clients if the edge appends without stripping untrusted values. Never treat `X-Forwarded-For` as authentication, authorization, MFA bypass, or unconditional IP banning without a verified trusted-proxy chain. Use network ACLs, real authentication, and explicit trusted-proxy parsing libraries.

### 4.3. RFC 7239 Forwarded

RFC 7239 standardizes the header syntax:

```http
Forwarded: for=198.51.100.42;proto=https;host=api.example.test
```

`X-Forwarded-*` headers are non-standard yet widespread conventions. If an edge sets `X-Forwarded-*` while passing through arbitrary client-supplied `Forwarded`, a framework may prioritize the header you did not expect. **Strip/normalize both families**, not just one.

## 5. Spring Boot 3.3: NONE, NATIVE, and FRAMEWORK

Key property:

```properties
server.forward-headers-strategy=framework
```

| Value | Behavior | When to Use |
| --- | --- | --- |
| `NONE` | Ignores forwarded headers for request metadata | App directly exposed or no trusted proxy |
| `NATIVE` | Uses embedded server's native mechanism, e.g., Tomcat `RemoteIpValve` | Simple proxy headers fully supported by native server |
| `FRAMEWORK` | Spring Framework `ForwardedHeaderFilter` (Servlet) / `ForwardedHeaderTransformer` (reactive) | Need public scheme/host/prefix, especially `X-Forwarded-Prefix` |

**Spring Boot 3.3** should not be configured using assumptions from other versions. Boot docs state that on certain cloud platforms the default may be `NATIVE`, and otherwise typically `NONE`. Whenever an app relies on forwarded metadata, **set the property explicitly**, inspect effective config, and test it.

### 5.1. Why Choose FRAMEWORK Here?

This lab uses a **public prefix `/shop` stripped by the reverse proxy upstream**. `X-Forwarded-Prefix` is used by Spring Framework's `ForwardedHeaderFilter` to restore the public context path/URI. `NATIVE` can cover `X-Forwarded-For` and `X-Forwarded-Proto`, but prefix/host/port support varies by embedded server. **Never assume `NATIVE` handles every `X-Forwarded-*` header.**

### 5.2. Do You Need to Define a ForwardedHeaderFilter Bean Manually?

In Boot 3.3:

```properties
server.forward-headers-strategy=framework
```

Boot auto-configures the filter for you. **Do not manually register an extra `ForwardedHeaderFilter`** without a strong reason, or headers may be processed twice with confusing filter ordering/dispatch behavior. If customizing filters, inspect Boot's auto-registration first.

### 5.3. What Does ForwardedHeaderFilter Do?

In the Servlet stack, the filter wraps the request so downstream calls like `getScheme()`, `getServerName()`, `getServerPort()`, `isSecure()`, and public context paths reflect trusted forwarded headers. It also removes processed forwarded headers from the wrapper so downstream components do not re-read them inconsistently. Spring Framework docs require it to run early before filters relying on request metadata.

**The filter cannot verify the network origin of headers.** If the backend is exposed directly so any client can inject `X-Forwarded-Host`, `FRAMEWORK` turns forged input into request metadata. Enable it only behind an enforced trust boundary.

### 5.4. ForwardedHeaderFilter removeOnly

Spring Framework supports a `removeOnly` mode that **strips** forwarded headers without applying them—useful when proxy metadata is untrusted and downstream layers must not see raw forwarded headers. In simple Spring Boot properties, use `NONE` to ignore them; if `removeOnly` is needed, configure a properly ordered filter without registering a second forwarding filter alongside it. Never use `removeOnly` when you actually need to reconstruct public scheme/host/prefix with no alternative source.

### 5.5. Tomcat redirect-context-root

Spring Boot 3.3 docs note that with Tomcat behind a TLS-terminating reverse proxy, consider:

```properties
server.tomcat.redirect-context-root=false
```

so `X-Forwarded-Proto` is evaluated before Tomcat issues context-root redirects. This is a targeted guard for container redirects, not a substitute for proper trusted forwarded headers and NGINX config.

## 6. Trust Rules for Reverse Proxies

An Internet client must never be able to claim "I arrived over HTTPS on the official host" simply by injecting `X-Forwarded-Proto: https`. Forwarded metadata is trustworthy only when set by a **trusted proxy**.

**Trust boundary in this lesson:** NGINX is the **first edge facing the Internet**. NGINX owns the fixed hostname/certificate, accepts public traffic, strips or overwrites `Forwarded`/`X-Forwarded-*`, and proxies to Spring Boot bound exclusively to `127.0.0.1` on the same host. External clients **cannot open sockets directly to the upstream port**.

### 6.1. Edge Checklist

- Validate `Host` via `server_name` and a default-server policy; reject unknown hosts.
- Terminate TLS with valid certificates and issue HTTPS redirects toward the canonical public authority.
- Strip inbound `Forwarded` and meaningful `X-Forwarded-*` headers (at minimum Proto/Host/Port/Prefix/For/Ssl/Server) and set authoritative values.
- Block direct access to upstream via loopback, private subnets, security groups, or network policies.
- Never copy arbitrary client `Host` into `X-Forwarded-Host`.
- Across multiple proxy hops, specify exactly which hop may append/overwrite and which sources are trusted.
- Never trust `X-Forwarded-For` for authorization; audits and rate limits must use verified client attribution through trusted hops.
- Log HTTPS scheme, Host, and prefix **without logging secrets or raw cookies**.
- Test both forged `Forwarded` headers and multi-value `X-Forwarded-For` headers.
- With a service mesh or ingress controller, ensure two layers do not rewrite prefixes or overwrite schemes inconsistently.

### 6.2. When NGINX Is Not the Outermost Edge

Example:

```text
Internet -> CDN -> Cloud Load Balancer -> NGINX -> Spring
```

Here `$remote_addr` seen by NGINX is the Load Balancer's IP, not the end user's IP. Configure trusted LB/CDN CIDR ranges in NGINX's real-IP module (or ingress equivalent), identify which hop holds the true client IP, and strip Internet-supplied headers **at the outermost edge**. Never blindly use `$proxy_add_x_forwarded_for` at the edge and assume the first element is genuine.

## 7. NGINX HTTPS and Public Prefix Rewriting

Illustrative **NGINX configuration co-located with Spring Boot**. Domain and certificate paths are placeholders; provision valid trusted certificates for your test domain before running.

Suggested file `/etc/nginx/conf.d/api-proxy.conf`:

```nginx
# Also configure a separate default server to reject invalid Host values
# at the edge instead of proxying unknown names to the backend.

server {
    listen 80;
    server_name api.example.test;

    return 308 https://api.example.test$request_uri;
}

server {
    listen 443 ssl;
    server_name api.example.test;

    ssl_certificate     /etc/nginx/tls/api.crt;
    ssl_certificate_key /etc/nginx/tls/api.key;

    # Client requests /shop without a trailing slash.
    location = /shop {
        return 308 https://api.example.test/shop/;
    }

    location /shop/ {
        proxy_http_version 1.1;

        # Trailing slash: /shop/api/v1/orders
        # becomes upstream /api/v1/orders.
        proxy_pass http://127.0.0.1:8080/;

        # Fixed public Host for this single virtual host example.
        proxy_set_header Host api.example.test;

        # Drop any client-supplied RFC 7239 Forwarded header.
        proxy_set_header Forwarded "";

        # Edge sets authoritative scheme/host/port/prefix.
        proxy_set_header X-Forwarded-Proto  https;
        proxy_set_header X-Forwarded-Host   api.example.test;
        proxy_set_header X-Forwarded-Port   443;
        proxy_set_header X-Forwarded-Prefix /shop;

        # Since this is the edge, discard any client-sent X-Forwarded-For.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Real-IP       $remote_addr;

        # Clear legacy/unused forwarding headers.
        proxy_set_header X-Forwarded-Ssl "";
        proxy_set_header X-Forwarded-Server "";

        proxy_connect_timeout 3s;
        proxy_read_timeout    30s;
        proxy_send_timeout    30s;
    }
}
```

### 7.1. Why Must proxy_pass Have a Trailing Slash?

Compare inside a prefix location:

```nginx
location /shop/ {
    proxy_pass http://127.0.0.1:8080/;
}
```

When the upstream URI ends with `/`, NGINX replaces the matched `/shop/` prefix with `/`: external `/shop/api/v1/orders` → upstream `/api/v1/orders`.

Conversely:

```nginx
location /shop/ {
    proxy_pass http://127.0.0.1:8080;
}
```

When `proxy_pass` has **no URI part**, URI handling differs: NGINX typically passes the original request URI (subject to rewrites/normalization), so upstream still receives `/shop/api/v1/orders`. Because the controller maps `/api/v1/orders`, the request returns 404. **Never alter the trailing slash without testing.**

### 7.2. Why Send X-Forwarded-Prefix=/shop?

Spring Boot's upstream root is `/`, because NGINX stripped `/shop` from the request URI. Yet when generating absolute URLs, the app must know the public prefix is `/shop`. `X-Forwarded-Prefix` passes that context to the `FRAMEWORK` strategy so URI builders include the prefix in links and redirects.

Do not simultaneously set:

```properties
server.servlet.context-path=/shop
```

in the same topology that strips the prefix and sends `X-Forwarded-Prefix` without careful design. Combining both can double the prefix to `/shop/shop` or break route matching. Pick **one clear model**: proxy rewrite + forwarded prefix as shown here, or pass the prefix through and set the app's context path, then test every route.

### 7.3. NGINX Does Not Emit CORS Headers in This Sample

The example deliberately omits:

```nginx
add_header Access-Control-Allow-Origin *;
```

We keep **Spring MVC** as the single authority defining CORS scope. If both NGINX and the app inject ACAO, duplicate or conflicting headers appear, causing browser rejections or broken gateway caches. Pick one policy owner; here MVC owns CORS and NGINX simply forwards.

### 7.4. Do Not Forget the OPTIONS Method

CORS preflight uses HTTP `OPTIONS` with `Origin` and `Access-Control-Request-Method`. The sample NGINX config allows `OPTIONS` through so Spring MVC evaluates it. If a gateway blocks `OPTIONS` with 405/401 or replies with its own wildcard, the frontend breaks before sending the actual `POST`.

### 7.5. Configuration Works Only Once Certificates Exist

Running:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

succeeds only when NGINX is installed, certificate paths exist, and you hold reload privileges. For `.test` domains, use an internal CA or local trusted cert generator; **never fall back to `-k` unconditionally and claim TLS was verified**.

### 7.6. Real Servers Also Need a Default-Server Policy

`server_name api.example.test` matches that virtual host, yet if it is the only `server` block on the listener, NGINX can still route mismatched `Host` headers to it as the default vhost. Production needs an **explicit `default_server` rejecting unknown Hosts** alongside proper SNI/cert config. The sample focuses on forwarding and assumes edge vhost hardening is configured separately.

## 8. Spring Boot Application: Project Structure

We use Gradle and Java 17. The order creation API returns `201 Location` to verify public URLs, supports GET by ID, and provides a redirect to the canonical URL.

```text
proxy-cors-lab/
  settings.gradle
  build.gradle
  gradlew
  gradlew.bat
  gradle/wrapper/...
  src/
    main/
      java/demo/
        ProxyCorsLabApplication.java
        OrderInput.java
        OrderView.java
        OrderStore.java
        OrdersController.java
        CorsPolicy.java
        CorrelationFilter.java
      resources/
        application.properties
    test/
      java/demo/
        ProxyCorsMvcTest.java
        ProxyCorsHttpTest.java
```

**No database or authentication is included in this demo.** Data stays in memory and resets on restart; keep endpoints restricted to the private lab rather than exposing them on the Internet. Production requires Spring Security, actor/tenant authorization, persistence, and auditing.

### 8.1. settings.gradle

```groovy
rootProject.name = 'proxy-cors-lab'
```

### 8.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use [Spring Initializr](https://start.spring.io/) to generate the Gradle Wrapper and skeleton, then populate these files. If creating `build.gradle` manually without `gradlew`, generate the wrapper with a compatible Gradle install. Spring Boot 3.3 pairs with Spring Framework 6.1; do not mix Boot 4.x imports or `javax.validation.*` into this Java 17 codebase.

### 8.3. application.properties

```properties
spring.application.name=proxy-cors-lab

# Assumes NGINX runs on the SAME HOST as the app.
server.address=127.0.0.1
server.port=8080

# Read public metadata established by trusted NGINX.
server.forward-headers-strategy=framework
server.tomcat.redirect-context-root=false

# Strictly one specific frontend origin.
app.cors.allowed-origin=https://app.example.test

# Boot 3.3 graceful shutdown must be opted in explicitly.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s

# Limit default error details.
server.error.include-message=never
server.error.include-stacktrace=never
server.error.include-binding-errors=never

# Actuator on backend loopback only, not exposed through sample proxy.
management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never
```

**Deployment warning:** `server.forward-headers-strategy=framework` is safe **only when NGINX is trusted and upstream is unreachable from the Internet**. If the app runs in a separate Kubernetes Pod, `127.0.0.1` no longer means "same machine as NGINX"; bind `0.0.0.0` instead while restricting ingress via network policies/service mesh. Never copy lab configs into a cluster without adapting network boundaries.

## 9. Java 17+ Code: Entry Point and Models

### 9.1. ProxyCorsLabApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProxyCorsLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProxyCorsLabApplication.class, args);
    }
}
```

`@SpringBootApplication` component-scans `demo`, registering the controller, service, config, and filter in the same package.

### 9.2. OrderInput.java

```java
package demo;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public record OrderInput(

        @NotBlank
        @Pattern(regexp = "[A-Z0-9-]{3,40}")
        String sku,

        @NotNull
        @Min(1)
        @Max(100)
        Integer quantity
) {
}
```

The DTO validates incoming payloads; clients cannot supply an `id`. `@NotNull` on `Integer` quantity distinguishes missing fields from 0; `@Min(1)` rejects zero or negative quantities. `@Pattern` restricts SKU syntax in the demo, though it **never replaces authorization**.

### 9.3. OrderView.java

```java
package demo;

public record OrderView(
        long id,
        String sku,
        int quantity
) {
}
```

Keeping the response model separate from the input DTO prevents accidentally echoing private fields—a good habit once entities and databases are added.

### 9.4. OrderStore.java

```java
package demo;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrderStore {

    private final AtomicLong nextId = new AtomicLong();

    private final ConcurrentMap<Long, OrderView> orders =
            new ConcurrentHashMap<>();

    public OrderView create(OrderInput input) {
        long id = nextId.incrementAndGet();

        OrderView view = new OrderView(
                id,
                input.sku(),
                input.quantity()
        );

        orders.put(id, view);
        return view;
    }

    public OrderView find(long id) {
        OrderView found = orders.get(id);

        if (found == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Order not found");
        }

        return found;
    }
}
```

`AtomicLong` and `ConcurrentHashMap` handle basic multi-threading in a single JVM, without persistence, cross-Pod uniqueness, or idempotency. Production requires a transactional database/repository and authorization—never treat hard-to-guess IDs or CORS as access control.

## 10. OrdersController.java: Generating Public Links and Redirects

File `src/main/java/demo/OrdersController.java`:

```java
package demo;

import java.net.URI;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/api/v1/orders")
public class OrdersController {

    private final OrderStore store;

    public OrdersController(OrderStore store) {
        this.store = store;
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<OrderView> create(
            @Valid @RequestBody OrderInput input) {

        OrderView created = store.create(input);

        URI resourceUri = ServletUriComponentsBuilder
                .fromCurrentRequestUri()
                .path("/{id}")
                .buildAndExpand(created.id())
                .toUri();

        return ResponseEntity.created(resourceUri)
                .body(created);
    }

    @GetMapping("/{id}")
    public OrderView find(@PathVariable long id) {
        return store.find(id);
    }

    @GetMapping("/{id}/canonical")
    public ResponseEntity<Void> canonical(
            @PathVariable long id) {

        store.find(id);

        URI resourceUri = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/api/v1/orders/{id}")
                .buildAndExpand(id)
                .toUri();

        return ResponseEntity
                .status(HttpStatus.FOUND)
                .location(resourceUri)
                .build();
    }
}
```

**Why build URIs via the builder instead of hardcoding?**

- `fromCurrentRequestUri()` takes the collection POST URI and appends the resource ID.
- `fromCurrentContextPath()` captures the resolved scheme, host, port, and public context path, then appends the canonical path.
- When NGINX strips `/shop` and sends `X-Forwarded-Prefix=/shop`, Spring Framework's forwarding filter restores the public prefix.
- When the proxy terminates HTTPS and sends `X-Forwarded-Proto=https`, absolute URLs do not fall back to `http`.
- Never manually concatenate raw `Host` or `X-Forwarded-Host` strings into URLs or redirect to arbitrary user query parameters.

**The lab never accepts client-supplied `returnUrl`/`redirect` parameters**, preventing open redirects. In OAuth2/login flows, validate every redirect target against an allowlist/path policy and test under attacker-controlled `Host` headers.

### 10.1. Why Use 302 for the Redirect?

`GET /api/v1/orders/{id}/canonical` is a demo route returning `302 Found` with a `Location` header pointing to the main resource. Other APIs may use 308 (permanent redirect preserving method), 303 (after POST/Redirect/Get), or 307 (temporary redirect preserving method). Never pick 301/302/303/307/308 arbitrarily on state-changing requests, as clients handle method preservation and redirect caching differently.

### 10.2. Valid URI Building Is Not Enough for Proxy Security

If the app accepts spoofed forwarded headers directly from the Internet, the URI builder can still output an attacker's host despite using the "right" framework API. **The framework merely consumes metadata**; the proxy establishes the trust boundary. Integration tests injecting headers verify URL-building behavior; security tests must verify external clients **cannot spoof** forwarded values past NGINX.

## 11. CorsPolicy.java: Allow Only the Exact Origin, Methods, Headers, and Paths

File `src/main/java/demo/CorsPolicy.java`:

```java
package demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class CorsPolicy implements WebMvcConfigurer {

    private final String allowedOrigin;

    public CorsPolicy(
            @Value("${app.cors.allowed-origin}")
            String allowedOrigin) {

        this.allowedOrigin = allowedOrigin;
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {

        // Collection route.
        configure(registry.addMapping("/api/v1/orders"));

        // Child routes, e.g. /api/v1/orders/7.
        configure(registry.addMapping("/api/v1/orders/**"));
    }

    private void configure(CorsRegistration mapping) {
        mapping.allowedOrigins(allowedOrigin)
                .allowedMethods("GET", "POST")
                .allowedHeaders(
                        "Content-Type", "X-Request-ID")
                .exposedHeaders(
                        "Location", "X-Request-ID")
                .allowCredentials(false)
                .maxAge(600);
    }
}
```

**Rationale behind each setting:**

- `allowedOrigins("https://app.example.test")`: one exact HTTPS origin, no path, no wildcard. Configurable via property per environment **after reviewing the origin allowlist**.
- Two `addMapping` entries: scoped to **internal MVC paths**, since NGINX already stripped `/shop`. Never map `/shop/api/**` in Spring when the app receives `/api/**`.
- `allowedMethods("GET","POST")`: GET to read, POST to create. **`OPTIONS` need not be listed in allowedMethods** for browser preflights requesting POST/GET; Spring's CORS processor handles `OPTIONS` preflights against `Access-Control-Request-Method`.
- `allowedHeaders("Content-Type","X-Request-ID")`: permits only these requested headers in preflight. Browsers may include CORS-safelisted headers without listing them; if the frontend sends `Authorization`, explicitly review and add it rather than blindly using `*`.
- `exposedHeaders("Location","X-Request-ID")`: allows browser JavaScript to read those two response headers via `fetch().headers.get(...)`. It **does not** control which request headers clients may send.
- `allowCredentials(false)`: this anonymous lab API does not send cross-origin cookies—a safer default whenever cookie auth is unnecessary.
- `maxAge(600)`: lets browsers cache **preflight** results for up to 600 seconds per `Access-Control-Max-Age` and browser caps—not caching the API JSON response itself.
- No extra `@CrossOrigin` annotations on controllers, avoiding mixed policies that inadvertently widen scope.

### 11.1. Why Not Use /**?

Anti-pattern:

```java
registry.addMapping("/**")
        .allowedOrigins("*")
        .allowedMethods("*");
```

This exposes CORS on health/admin endpoints and unreviewed APIs. While CORS **is not authorization**, a malicious frontend could read responses from endpoints where the browser attaches credentials under looser credential/CORS rules; overly broad scopes are hard to audit and invite chained vulnerabilities.

This practice restricts CORS exclusively to the orders API collection/child routes. Actuator `/actuator/health` stays outside the mapping and never returns `Access-Control-Allow-Origin`.

### 11.2. Global CORS and @CrossOrigin Combine

Spring MVC combines global `CorsRegistry` rules with controller/method `@CrossOrigin` annotations. Allowed origins, methods, and headers can merge additively; a single controller adding `@CrossOrigin(origins="*")` can widen the effective policy beyond what you expected. **Establish one single policy owner** or review combination behavior carefully—never scatter annotations across controllers and assume the global allowlist still holds as an upper bound.

### 11.3. When Spring Security Is Present

With `spring-boot-starter-security`, CORS must execute **before Spring Security authentication**, because preflight `OPTIONS` requests do not carry `JSESSIONID` cookies. Spring Security supports `http.cors(withDefaults())`, reusing MVC CORS configuration when Spring MVC is on the classpath and no separate `CorsConfigurationSource` bean overrides it.

Integration snippet **for projects that have Spring Security and full authentication configured**:

```java
@Bean
SecurityFilterChain security(HttpSecurity http)
        throws Exception {

    http.cors(Customizer.withDefaults())
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(
                "/actuator/health/**").permitAll()
            .anyRequest().authenticated());

    return http.build();
}
```

This is a **snippet** needing `@Bean`, `SecurityFilterChain`, `HttpSecurity`, `Customizer`, and real auth config; it is **not part of the unauthenticated runnable baseline**. Never blindly call `csrf.disable()` with session/cookie auth. With multiple security chains or multiple `CorsConfigurationSource` beans, wire the right policy per chain explicitly.

### 11.4. CORS Does Not Replace CSRF

CORS restricts **reading responses** from another origin in the browser. CSRF tricks a browser into sending credentialed state-changing requests. Cross-origin HTML forms can submit certain requests without reading responses; servers using cookie authentication must enforce CSRF protection for state-changing operations. Spring Security's `CookieCsrfTokenRepository`/CSRF tokens, `SameSite`, and Origin/Referer checks work together per threat model.

### 11.5. Authorization Header Differs from Cookies

If the frontend sends a Bearer access token in `Authorization`, a browser POST with that header triggers a preflight. To support token clients, configure CORS:

```java
mapping.allowedHeaders(
        "Content-Type", "Authorization", "X-Request-ID");
```

Apply this **deliberately** only on endpoints using `Authorization`, not globally. `Access-Control-Allow-Headers: Authorization` does not replace server-side JWT/token validation. Browser JS holding bearer tokens also requires strong XSS defenses and careful token handling.

## 12. CorrelationFilter.java: Response Header to Test CORS Expose

File `src/main/java/demo/CorrelationFilter.java`:

```java
package demo;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class CorrelationFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        response.setHeader(
                "X-Request-ID",
                UUID.randomUUID().toString());

        chain.doFilter(request, response);
    }
}
```

The filter only sets one header; it never reads the request body, never logs `Authorization`/`Cookie`, and never guesses client IP from raw `X-Forwarded-For`. Because the frontend needs to read `X-Request-ID` in JS, `CorsPolicy`'s `exposedHeaders` includes it.

**Note:** errors generated by NGINX or the container before reaching the app bypass this filter, so not every response on the Internet will carry this ID. In multi-hop architectures, generate/normalize correlation IDs at the gateway and propagate them across trusted channels.

## 13. Running the Application Directly

From the directory containing the Gradle Wrapper:

```bash
./gradlew clean test bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat clean test bootRun
```

Package an executable JAR and run it directly:

```bash
./gradlew bootJar
java -jar build/libs/proxy-cors-lab-0.0.1-SNAPSHOT.jar
```

**Note:** `java -jar` runs on local loopback without NGINX in front. Direct calls to `127.0.0.1:8080` with no forwarded headers only see the internal address; public URIs appear only when proxy metadata is supplied. The local curl commands below are **functional tests**, not proof that NGINX's trust boundary is secure.

### 13.1. Direct POST Without Forwarded Headers

```bash
curl -i -X POST \
  http://127.0.0.1:8080/api/v1/orders \
  -H 'Content-Type: application/json' \
  -d '{"sku":"BOOK-001","quantity":2}'
```

First response on a fresh JVM:

```http
HTTP/1.1 201
Location: http://127.0.0.1:8080/api/v1/orders/1
Content-Type: application/json

{"id":1,"sku":"BOOK-001","quantity":2}
```

Additional headers may be present and ID increments with state. This is the **internal URL**—normal without proxy metadata, though not the public `Location` browsers should receive.

### 13.2. Simulating Proxy Metadata Locally with curl

```bash
curl -i -X POST \
  http://127.0.0.1:8080/api/v1/orders \
  -H 'Content-Type: application/json' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: api.example.test' \
  -H 'X-Forwarded-Port: 443' \
  -H 'X-Forwarded-Prefix: /shop' \
  -d '{"sku":"BOOK-002","quantity":3}'
```

With `server.forward-headers-strategy=framework`, expected `Location`:

```text
https://api.example.test/shop/api/v1/orders/2
```

ID varies at runtime. If `Location` lacks `/shop`, check the filter strategy, upstream rewrite, `X-Forwarded-Prefix`, and whether two layers modified the prefix. If `Location` starts with `http://127.0.0.1`, the app is not reading forwarded metadata or the proxy omitted headers.

**Security warning:** the fact that a direct curl can control `X-Forwarded-Host` demonstrates why **the backend must never be directly exposed** when `FRAMEWORK` is enabled. This test is a functional simulation, not anti-spoofing certification.

### 13.3. GET and 302 Redirect

After POST, using the returned ID:

```bash
curl -i \
  http://127.0.0.1:8080/api/v1/orders/2

curl -i \
  http://127.0.0.1:8080/api/v1/orders/2/canonical \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: api.example.test' \
  -H 'X-Forwarded-Port: 443' \
  -H 'X-Forwarded-Prefix: /shop'
```

Expect 302 `Location: https://api.example.test/shop/api/v1/orders/2`. Do not pass `curl -L` when inspecting the redirect header itself; `-L` tries to follow the public host (which may lack local DNS/certs).

## 14. CORS Preflight: Browser Checks Before Posting JSON

Because frontend `https://app.example.test` and API `https://api.example.test` have different origins, a JSON POST triggers a **preflight** under Fetch/CORS rules (`Content-Type: application/json` is not a safelisted simple-request content type).

Before the POST, the browser sends to the public URL:

```http
OPTIONS /shop/api/v1/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
```

NGINX forwards upstream:

```http
OPTIONS /api/v1/orders HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
X-Forwarded-Prefix: /shop
```

Spring MVC evaluates the preflight against `CorsPolicy`. A valid response looks like:

```http
HTTP/1.1 200
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: content-type
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

**Do not hardcode exact header casing or ordering across every implementation.** What matters is a 2xx preflight status with matching `Access-Control-Allow-*` headers and no duplicates or redirects.

### 14.1. Actual Request Must Also Include CORS Headers

After preflight passes, the browser sends the `POST`. The `201` response still needs `Access-Control-Allow-Origin` so JavaScript can read the body and exposed headers. A passing preflight **does not** make the actual response readable if the proxy or app drops CORS headers on error or redirect paths.

### 14.2. Browsers Handle Preflight Automatically

Frontend JavaScript should never issue a fake manual `OPTIONS` request assuming that grants permission. The browser/Fetch engine decides when preflights run and caches them per policy. Actual `fetch()` call:

```javascript
const api = "https://api.example.test/shop/api/v1/orders";

const response = await fetch(api, {
  method: "POST",
  mode: "cors",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    sku: "BOOK-001",
    quantity: 2
  })
});

if (!response.ok) {
  throw new Error("HTTP " + response.status);
}

const order = await response.json();
const resourceLocation = response.headers.get("Location");
const requestId = response.headers.get("X-Request-ID");

console.log(order, resourceLocation, requestId);
```

This is a **frontend snippet** executed from a page on `https://app.example.test`, without session cookies or tokens in the lab. `mode:"cors"` does not grant permission; the server still controls allowed origins. Because `CorsPolicy` exposes `Location` and `X-Request-ID`, JS can read both headers on a valid CORS response.

### 14.3. Why Calling Directly from Node.js or curl Does Not Enforce CORS

Node HTTP clients and `curl` do not enforce the browser same-origin policy. A response missing `Access-Control-Allow-Origin` is still readable in Node. **CORS is strictly a browser enforcement mechanism** and never substitutes for firewalls, authentication, or authorization.

## 15. CORS Response Headers and Their Exact Roles

| Header | Phase | Meaning |
| --- | --- | --- |
| `Origin` | Request | Origin of the calling document/script |
| `Access-Control-Request-Method` | Preflight request | Browser asks if actual method is allowed |
| `Access-Control-Request-Headers` | Preflight request | Browser asks if non-safelisted request headers are allowed |
| `Access-Control-Allow-Origin` | Preflight/actual response | Server declares which origin may read the response in browser JS |
| `Access-Control-Allow-Methods` | Preflight response | Permitted actual HTTP methods |
| `Access-Control-Allow-Headers` | Preflight response | Permitted request headers |
| `Access-Control-Allow-Credentials` | Response | Allows credentialed cross-origin reads if true; requires exact origin |
| `Access-Control-Expose-Headers` | Actual response | Response headers readable by JS |
| `Access-Control-Max-Age` | Preflight response | Seconds browsers may cache the preflight result |
| `Vary` | Response/cache | Separates cached responses by `Origin` and CORS request headers/method |

### 15.1. AllowedHeaders vs ExposedHeaders

When the frontend sends request header `Content-Type`, preflight checks `Access-Control-Allow-Headers`. When the backend returns response header `Location`, JS reads it via `Access-Control-Expose-Headers`. Never put `Location` in `allowedHeaders` hoping JS can read it—those two headers govern opposite directions.

### 15.2. Vary and CDNs

When responses vary by `Origin`, shared caches must separate variants, typically via `Vary: Origin`. Preflights can also vary by `Access-Control-Request-Method` and `Access-Control-Request-Headers`. If a CDN caches one origin's response and serves it to another without proper `Vary`, browsers reject it or policies leak. Never strip `Vary` to "optimize cache hit rate" without designing cache keys properly.

### 15.3. Max-Age Is Not Order Data TTL

`maxAge(600)` caches preflight results, not order payloads. Response caching depends on `Cache-Control`, `ETag`, `Last-Modified`, and proxy/CDN rules. Private API data must never be public-cached merely because CORS succeeded.

### 15.4. Origin null

Contexts like `file://`, sandboxed iframes, or privacy modes can send `Origin: null`. Never add `"null"` to a general allowlist to "fix CORS" without an explicit threat model; many untrusted contexts produce `null` origins.

## 16. Rejected Origin Cases

Preflight request:

```bash
curl -i -X OPTIONS \
  http://127.0.0.1:8080/api/v1/orders \
  -H 'Origin: https://evil.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
```

With `CorsPolicy` and Spring MVC `DefaultCorsProcessor`, non-allowlisted cross-origin requests typically receive **HTTP 403 Invalid CORS request** (or omit ACAO depending on pipeline); the browser aborts before sending the actual POST.

None of the following equal `https://app.example.test`:

- `https://app.example.test.evil.test` — subdomain lookalike.
- `http://app.example.test` — different scheme.
- `https://app.example.test:8443` — different port.
- `https://other.example.test` — different host.
- `null` — opaque origin, not allowlisted.
- `https://APP.example.test` — DNS hostnames are case-insensitive in principle, yet never roll your own ad-hoc string normalization for authorization; rely on framework origin matching and tests.

Browsers do not send preflight on every request. For a **simple GET**, the browser sends the actual GET directly and blocks JS from reading the response if ACAO is missing. Thus, **no `OPTIONS` in access logs does not mean the frontend is same-origin or CORS is off**.

### 16.1. CORS Does Not Prevent Side Effects in All Cases

Some requests (like HTML form submissions) can fire without preflight even when JS cannot read the response. Cookie-authenticated state-changing endpoints always need CSRF defenses. Never set `allowedOrigins("*")` thinking the server "blocks hackers": CORS only controls browser response reads, not arbitrary HTTP clients.

## 17. MockMvc Tests for Forwarding and CORS

This practice loads the full Spring Boot context to wire Spring MVC mappings, `ForwardedHeaderFilter` auto-configuration, and CORS config. `MockMvc` opens no real TCP port, yet cleanly tests controllers, `HandlerMapping`, CORS processing, and response headers.

Create `src/test/java/demo/ProxyCorsMvcTest.java`:

```java
package demo;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProxyCorsMvcTest {

    private static final String FRONTEND =
            "https://app.example.test";

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper json;

    private String requestBody() {
        return """
            {"sku":"BOOK-001","quantity":2}
            """;
    }

    @Test
    void preflightAllowedForExactOriginAndPost()
            throws Exception {

        mvc.perform(options("/api/v1/orders")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "POST")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "content-type"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    FRONTEND))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                    containsString("POST")))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_MAX_AGE,
                    "600"));
    }

    @Test
    void preflightRejectsUnknownOrigin() throws Exception {
        mvc.perform(options("/api/v1/orders")
                .header(
                    HttpHeaders.ORIGIN,
                    "https://evil.example.test")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "POST"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void schemeAndPortArePartOfOrigin() throws Exception {
        mvc.perform(options("/api/v1/orders")
                .header(
                    HttpHeaders.ORIGIN,
                    "http://app.example.test")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "POST"))
            .andExpect(status().isForbidden());

        mvc.perform(options("/api/v1/orders")
                .header(
                    HttpHeaders.ORIGIN,
                    "https://app.example.test:8443")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "POST"))
            .andExpect(status().isForbidden());
    }

    @Test
    void actualPostExposesLocationOnlyToAllowedOrigin()
            throws Exception {

        mvc.perform(post("/api/v1/orders")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .contentType(MediaType.APPLICATION_JSON)
                .content(requestBody()))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    FRONTEND))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS,
                    containsString("Location")))
            .andExpect(header().exists(
                    "X-Request-ID"));
    }

    @Test
    void forwardedPublicLocationContainsHttpsAndPrefix()
            throws Exception {

        MvcResult created = mvc.perform(
                post("/api/v1/orders")
                    .header(
                        "X-Forwarded-Proto", "https")
                    .header(
                        "X-Forwarded-Host",
                        "api.example.test")
                    .header(
                        "X-Forwarded-Port", "443")
                    .header(
                        "X-Forwarded-Prefix", "/shop")
                    .contentType(
                        MediaType.APPLICATION_JSON)
                    .content(requestBody()))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                    HttpHeaders.LOCATION,
                    startsWith(
                        "https://api.example.test/shop/api/v1/orders/")))
            .andReturn();

        JsonNode response = json.readTree(
                created.getResponse()
                       .getContentAsString());

        long id = response.get("id").asLong();

        mvc.perform(get(
                    "/api/v1/orders/{id}/canonical", id)
                .header("X-Forwarded-Proto", "https")
                .header(
                    "X-Forwarded-Host",
                    "api.example.test")
                .header("X-Forwarded-Port", "443")
                .header(
                    "X-Forwarded-Prefix", "/shop"))
            .andExpect(status().isFound())
            .andExpect(header().string(
                    HttpHeaders.LOCATION,
                    "https://api.example.test/shop/api/v1/orders/"
                        + id));
    }

    @Test
    void invalidInputFailsBeanValidation()
            throws Exception {

        mvc.perform(post("/api/v1/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"sku":" ","quantity":0}
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void healthIsNotGivenOrdersCorsPolicy()
            throws Exception {

        mvc.perform(options("/actuator/health")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "GET"))
            .andExpect(header().doesNotExist(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }
}
```

**Technical notes:** tests avoid hardcoded IDs because `OrderStore` preserves in-memory state across test methods. To test the forwarded redirect, the test parses the ID from the POST response. `JsonNode`/`ObjectMapper` come from `spring-boot-starter-web`; Hamcrest, MockMvc, JUnit, and AssertJ come from `starter-test`.

### 17.1. What MockMvc Does and Does Not Verify

**Verifies:** handler mappings, CORS allow/deny rules, preflight headers, DTO validation, Spring Boot forwarding filter (when registered in the test context), and `Location`/redirects constructed from forwarded metadata.

**Does not verify:** whether NGINX strips malicious forwarded headers, whether `proxy_pass` rewrites paths cleanly, HTTPS/TLS 443 certificates, DNS, keep-alive, browser cookie policies, CSP, CDN/ingress behavior, or network ACLs.

A passing MockMvc test sending `X-Forwarded-Host: api.example.test` only proves the framework **trusts** and formats that header as expected—not that attackers are blocked from reaching the backend directly.

### 17.2. Avoid Rigid Assertions on Dynamic Values

When asserting `Location`, check the prefix and actual returned ID rather than hardcoding ID 1 across shared/parallel tests. For `Vary` and `Access-Control-Allow-Headers`, check element presence without relying on strict header value ordering or casing.

### 17.3. If Tests Fail Because the Forwarded Filter Is Missing

Verify `server.forward-headers-strategy=framework`, Boot 3.3 version, that `@AutoConfigureMockMvc` registers servlet filters, and that no custom test filter disables forwarding. Never manually add a duplicate `ForwardedHeaderFilter` in production just to make tests pass—diagnose auto-config and test setup first.

## 18. RANDOM_PORT: Testing the Real HTTP Container

File `src/test/java/demo/ProxyCorsHttpTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ProxyCorsHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate client;

    private String url() {
        return "http://127.0.0.1:"
                + port + "/api/v1/orders";
    }

    @Test
    void realHttpResponseUsesForwardedPublicUri() {

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.add(
                "X-Forwarded-Proto", "https");
        headers.add(
                "X-Forwarded-Host", "api.example.test");
        headers.add(
                "X-Forwarded-Port", "443");
        headers.add(
                "X-Forwarded-Prefix", "/shop");

        HttpEntity<String> request = new HttpEntity<>(
                """
                {"sku":"BOOK-123","quantity":1}
                """,
                headers
        );

        ResponseEntity<String> result = client.exchange(
                url(),
                HttpMethod.POST,
                request,
                String.class
        );

        assertThat(result.getStatusCode())
                .isEqualTo(HttpStatus.CREATED);

        assertThat(result.getHeaders().getLocation())
                .isNotNull()
                .satisfies(location ->
                    assertThat(location.toString())
                        .startsWith(
                          "https://api.example.test/shop/api/v1/orders/"));
    }

    @Test
    void preflightWorksOverTcp() {

        HttpHeaders headers = new HttpHeaders();
        headers.add(
                HttpHeaders.ORIGIN,
                "https://app.example.test");
        headers.add(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "POST");
        headers.add(
                HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "content-type");

        ResponseEntity<String> result = client.exchange(
                url(),
                HttpMethod.OPTIONS,
                new HttpEntity<>(headers),
                String.class
        );

        assertThat(result.getStatusCode())
                .isEqualTo(HttpStatus.OK);

        assertThat(result.getHeaders().getFirst(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN))
                .isEqualTo("https://app.example.test");
    }
}
```

`RANDOM_PORT` launches a real embedded Tomcat with `application.properties`, and `TestRestTemplate` hits it over TCP loopback. This confirms Boot's forwarding stack and MVC CORS run inside the real HTTP server, though it still bypasses NGINX, edge header sanitization, and browser credential enforcement.

### 18.1. Why Injecting Simulated Headers in Tests Still Adds Value

This is a **functional integration assertion** verifying the app builds public URLs accurately *when receiving trusted proxy metadata*. At the same time, it highlights the risk: if exposed directly, an attacker could supply the host. Add **E2E tests through NGINX** to prove external headers are ignored.

### 18.2. Real Path Testing Through NGINX Differs from RANDOM_PORT

The `RANDOM_PORT` test calls `/api/v1/orders` with explicit `X-Forwarded-Prefix=/shop`. Through real NGINX, clients call `/shop/api/v1/orders` **without** sending forwarded headers; NGINX strips the prefix and sets the metadata itself. Both tests cover distinct layers and are both needed in production.

## 19. End-to-End NGINX Verification

To test the external route, map `api.example.test` via DNS/hosts to NGINX and install a client-trusted certificate (e.g., local CA/mkcert or internal PKI).

`curl --resolve` maps a hostname for **a single curl invocation** while preserving normal TLS hostname/certificate verification:

```bash
curl -i \
  --resolve api.example.test:443:127.0.0.1 \
  https://api.example.test/shop/api/v1/orders
```

If the certificate is invalid, curl fails TLS verification. Never make `--insecure`/`-k` your default for security testing; use a proper CA/cert or `--cacert` for internal CAs.

### 19.1. Create Order Through the HTTPS Proxy

```bash
curl -i \
  --resolve api.example.test:443:127.0.0.1 \
  -X POST \
  'https://api.example.test/shop/api/v1/orders' \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://app.example.test' \
  -d '{"sku":"BOOK-234","quantity":4}'
```

Verify:

- HTTP **201**.
- Body contains `id` and submitted fields.
- `Location` starts with `https://api.example.test/shop/api/v1/orders/`.
- `Access-Control-Allow-Origin: https://app.example.test`.
- `Access-Control-Expose-Headers` allows reading `Location` and `X-Request-ID`.
- No internal `127.0.0.1:8080` leaks into absolute headers.
- TLS verification passes.

### 19.2. Preflight Through the HTTPS Proxy

```bash
curl -i \
  --resolve api.example.test:443:127.0.0.1 \
  -X OPTIONS \
  'https://api.example.test/shop/api/v1/orders' \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
```

Expect a 2xx status and exact `Access-Control-Allow-Origin`. If the public URL returns a 301/308/302 redirect due to a missing trailing slash or HTTP→HTTPS, preflight behavior varies across browsers—frontends should call the **canonical HTTPS URL** directly. Inspect URL, path, and origin in DevTools.

### 19.3. Negative Test: Disallowed Origin

```bash
curl -i \
  --resolve api.example.test:443:127.0.0.1 \
  -X OPTIONS \
  'https://api.example.test/shop/api/v1/orders' \
  -H 'Origin: https://evil.example.test' \
  -H 'Access-Control-Request-Method: POST'
```

Spring MVC preflight typically rejects with 403—and at minimum must omit ACAO for the disallowed origin. Non-browser `curl` still being able to send requests does not mean CORS failed; CORS prevents unauthorized browser JS from reading responses.

### 19.4. Negative Test: Spoofed X-Forwarded-Host from the Internet

Safe test **only inside staging/lab environments you control**:

```bash
curl -i \
  --resolve api.example.test:443:127.0.0.1 \
  -X POST \
  'https://api.example.test/shop/api/v1/orders' \
  -H 'Content-Type: application/json' \
  -H 'X-Forwarded-Host: attacker.example.test' \
  -H 'X-Forwarded-Proto: http' \
  -H 'Forwarded: for=192.0.2.1;proto=http;host=attacker.example.test' \
  -d '{"sku":"BOOK-345","quantity":1}'
```

**Expected safe behavior:** the NGINX edge strips/overwrites client-supplied values. `Location` must still point to `https://api.example.test/shop/...` with zero attacker host or `http` scheme. If it ever points to the attacker's host, the **trust boundary failed** regardless of passing Spring Boot controller tests.

Never run this probe against third-party services; test only your own systems within authorized scope.

### 19.5. Negative Test: Unlisted Host Header

Production edges should reject unknown hosts or route them to a non-proxying default server. Verify HTTP Host/SNI/certificate behavior within authorized test plans; do not put a single `server_name` in NGINX and assume it rejects every unlisted Host. The sample NGINX snippet needs an explicit default-server policy before production.

## 20. CORS with Cookies and Sessions: When to Enable Credentials

The baseline sets:

```java
.allowCredentials(false)
```

because the lab API is cookie-free. If using **session cookie authentication**, a cross-origin browser frontend generally uses:

```javascript
const response = await fetch(
  "https://api.example.test/shop/api/v1/orders",
  {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-TOKEN": "<server-issued token>"
    },
    body: JSON.stringify({
      sku: "BOOK-001",
      quantity: 2
    })
  }
);
```

This **snippet assumes a system with CSRF token issuance and authentication**, not the unauthenticated baseline. Browser JS cannot manually set a `Cookie` header on fetch; it relies on the browser cookie jar and `credentials:"include"`.

The backend must allow credentials strictly for exact origins:

```java
mapping.allowedOrigins("https://app.example.test")
        .allowCredentials(true)
        .allowedHeaders(
            "Content-Type", "X-CSRF-TOKEN");
```

This is a **dedicated replacement** for deployments needing credentials—replace the baseline config rather than stacking conflicting rules. When `allowCredentials` is true:

- **Never** use `allowedOrigins("*")`. Spring Framework validation rejects combining wildcard `*` with `allowCredentials(true)`.
- `Access-Control-Allow-Origin` must echo an exact valid origin, never `*`.
- `Access-Control-Allow-Credentials: true` must be returned for credentialed cross-origin reads.
- Cookies remain subject to `Secure`, `SameSite`, `Path`, `Domain`, and browser privacy restrictions.
- The server must still validate session/tokens and CSRF for state-changing requests; **CORS never replaces them**.
- With Bearer `Authorization` instead of session cookies, configure `allowedHeaders` accordingly rather than conflating Bearer tokens with cookies.

### 20.1. Same-Origin vs Same-Site Still Matters

Frontend `https://app.example.test` calling `https://api.example.test` is **cross-origin yet potentially same-site**. Browsers can send a `SameSite=Lax` cookie within the same schemeful site when `credentials:"include"` and cookie scope permit, yet CORS is still required for JS to read cross-origin responses.

If the frontend sits on a different registrable site, cross-site fetch cookies usually require `SameSite=None; Secure`, and modern browsers may restrict third-party cookies. Never "fix" this by disabling CORS, dropping `Secure`, or setting wildcard origins—test in real browsers across the real domain topology.

### 20.2. Cookie Path and Public Prefix

Here the proxy exposes prefix `/shop` while the backend runs at `/`. When issuing cookies for the public API, scope the path appropriately:

```http
Set-Cookie: session_hint=opaque; Path=/shop; Secure; HttpOnly; SameSite=Lax
```

Browsers match cookies against the public URL path. `Path=/shop` sends the cookie under `/shop/...` rather than unrelated root paths. With Servlet `JSESSIONID`, inspect `server.servlet.session.cookie.path` / Spring Session serialization and test through the proxy—**never assume `X-Forwarded-Prefix` automatically rewrites every cookie `Path` or `Domain`**.

### 20.3. Domain: Prefer Host-Only When Possible

Avoid `Domain=.example.test` just so "both frontend and API share cookies" when only the API needs the session. Host-only cookies bound to `api.example.test` minimize exposure. Setting `Domain` widens scope across subdomains, increasing risk if any subdomain is compromised. Cookie `Path`/`Domain` never replace server-side session authorization.

### 20.4. Secure Flag and HTTPS Termination

When the app listens on HTTP upstream, it can observe `isSecure=false` without forwarded-header handling, producing non-`Secure` cookies or HTTP redirects. With a trusted forwarding strategy, downstream request metadata reflects external HTTPS. Even so, production session cookies should **explicitly force `Secure`** via config rather than relying solely on headers.

### 20.5. CSRF with Cookies

An attacker site can trigger certain cross-site credentialed requests from a victim's browser without needing to read the response. CORS does not stop CSRF. For cookie-based Spring Security logins, keep CSRF protection active, transport tokens cleanly, and test that missing/invalid CSRF tokens return 403. Stateless Bearer-token threat models differ, yet still require strict authentication and authorization.

## 21. When Multiple Layers Handle CORS: Who Owns the Policy?

A common stack:

```text
Browser -> CDN -> NGINX -> Spring Security -> Spring MVC
```

CDN, NGINX, Security, and MVC can all emit CORS headers if configured. Without a single owner, typical bugs include:

- Two `Access-Control-Allow-Origin` headers or one header with two origins.
- NGINX returning `*` while Spring returns an exact origin.
- Preflight blocked 401/403 by a Security filter before reaching MVC.
- Gateway returning CORS 200 for an invalid route while actual POST gets 404 without ACAO.
- CDN caching a preflight for origin A and serving it to origin B.
- Spring MVC emitting ACAO on controller successes while proxy-generated 502s lack CORS headers.
- `@CrossOrigin` on one controller expanding scope past the global allowlist.

**This lesson designates MVC as the CORS owner.** NGINX forwards `OPTIONS` without adding ACAO. When Spring Security is added, wire `http.cors(...)` so preflights run cleanly in the filter chain from one source of truth. If you choose edge-owned CORS instead, transfer ownership intentionally and test every success and error path—never emit headers in both places.

### 21.1. Vary and CDN Caching

When responses vary by `Origin`, ensure `Vary` or cache keys distinguish `Origin`/`Request-Method`/`Request-Headers` as needed. User-specific data requires stricter caching rules than CORS alone: never cache personalized GETs in a shared CDN relying on ACAO. For credentialed/cookie responses, set `Cache-Control: private, no-store` per data sensitivity.

### 21.2. Browser "CORS Blocked" Is Not Always a CORS Root Cause

Browsers may report "CORS blocked" when an upstream 502/504, TLS failure, redirect loop, or proxy-generated HTML error omits ACAO. In DevTools Network, inspect **status, URL, redirect chain, and response headers** alongside server/NGINX logs. Never rush to set `Access-Control-Allow-Origin: *` just to make the browser console message disappear.

## 22. Practical Troubleshooting Matrix

| Symptom | Possible Cause | Diagnosis / Fix |
| --- | --- | --- |
| `Location` starts with `http://127.0.0.1:8080` | Spring is ignoring or missing forwarded scheme/host | Check `server.forward-headers-strategy` and `proxy_set_header` |
| `Location` has HTTPS yet lacks `/shop` | Missing `X-Forwarded-Prefix` or wrong slash rewrite | Inspect `proxy_pass` and prefix header |
| `Location` doubles to `/shop/shop` | Both proxy and context path add the prefix | Pick one clear rewrite/context strategy |
| Public URL 404, internal API 200 | NGINX not stripping prefix properly | Compare `proxy_pass` with vs without trailing slash |
| Redirects to HTTP despite HTTPS browser | Wrong `X-Forwarded-Proto` or Tomcat root redirect | Check edge TLS, `redirect-context-root`, and forwarding strategy |
| Attacker controls hostname in `Location` | Forwarded headers not sanitized | Strip/overwrite at edge, block direct upstream access |
| Unknown `Host` proxied to app | Missing default vhost/SNI/Host validation | Reject unknown hosts at edge |
| `X-Forwarded-For` shows forged IP | Edge appends client header unchecked | Overwrite at trust boundary, configure trusted chain |
| Browser blocks cross-origin JSON POST | `OPTIONS` gets 404/401/405/redirect or lacks ACAO | Test preflight directly on public HTTPS URL |
| Preflight 200 yet POST blocked by browser | Actual response lacks ACAO, proxy error, or redirect | Test both `OPTIONS` and actual `POST` |
| CORS `allowCredentials=true` with `*` | Wildcard origin forbidden with credentials | Use exact `allowedOrigins` |
| `Origin=https://evil...` permitted | Overly broad wildcard/pattern or merged `@CrossOrigin` | Narrow to exact origin and path |
| CORS granted on `/actuator/**` unintentionally | Mapping `/**` or broad Security/NGINX rule | Scope strictly to intended APIs |
| Preflight requesting `Authorization` rejected | `Authorization` missing from `allowedHeaders` | Explicitly allow it for bearer-token APIs |
| Browser JS cannot read `Location` on 201 | Missing `Access-Control-Expose-Headers` | Expose `Location` intentionally |
| Browser does not send cookie | `Secure`/`SameSite`/`Domain`/`Path`/credentials mismatch | Test in DevTools over real HTTPS |
| Session cookie Path is `/`, needs `/shop` | Servlet/Spring Session cookie path unset | Set cookie path explicitly and verify |
| Credentialed POST returns 403 | CSRF or auth failure, not necessarily CORS | Separate preflight from actual request diagnostics |
| User B reads User A's order | Missing authorization; CORS does not stop it | Add owner/tenant authorization checks |
| NGINX returns 502 | Backend down, wrong upstream, or timeout | Check error logs, port, firewall |
| NGINX returns 413 on upload | Proxy `client_max_body_size` | Tune proxy limits to match file policy |
| Wrong CORS cached across origins | Missing `Vary`/cache key at proxy/CDN | Fix caching contract |
| Backend bound to loopback in K8s | Proxy in another Pod cannot reach `127.0.0.1` | Bind Pod interface and enforce NetworkPolicy |
| MockMvc passes yet public URL fails | MockMvc skips NGINX and TLS | Add end-to-end proxy tests |
| API redirects to foreign domain | Misconfigured trusted headers / open redirect | Decouple client redirect targets from `Host` |
| Health endpoint leaks internals | Broad CORS or Actuator exposure | Keep management private and secured |
| NGINX passes `OPTIONS` yet Security returns 401 | CORS not ordered before authentication | Enable Spring Security CORS integration |

## 23. Security Checklist for Forwarded Headers and CORS

1. **TLS:** valid certificates, SNI, HSTS, and HTTP→HTTPS redirects toward the canonical authority. Enable HSTS only once HTTPS and subdomains are cleanly managed.
2. **Host allowlist:** edge accepts only expected hostnames. Never generate absolute links from arbitrary `Host` headers.
3. **Trusted hops:** know every CDN/LB/ingress allowed to forward; strip untrusted inbound `Forwarded`/`X-Forwarded-*`.
4. **Backend isolation:** allow only trusted proxies to reach upstream (loopback on same host; NetworkPolicy/private Service in Kubernetes).
5. **Scheme normalization:** app recognizes external HTTPS without redirecting to HTTP or causing mixed content.
6. **Prefix ownership:** prevent double rewrites, duplicate context paths, and broken OAuth2 redirect URIs.
7. **CORS origin allowlist:** exact scheme/host/port, no path, no wildcard for credentialed flows.
8. **CORS route scope:** enable only on endpoints needed by the frontend—never blindly on `/**`.
9. **CORS methods/headers:** minimal methods (`GET`/`POST`) and headers; add `Authorization`/`PUT`/`DELETE` only per API contract.
10. **CORS response exposure:** expose only needed headers like `Location`/`X-Request-ID`, never secrets.
11. **CORS preflight:** pass `OPTIONS` through the proxy; with Security, process CORS before authentication.
12. **Credentials:** `allowCredentials(true)` only when needed, with exact origin and `Secure`/`HttpOnly`/`SameSite`/`Path` cookies.
13. **CSRF:** always evaluate when cookie/session auth backs state-changing operations.
14. **Authentication/authorization:** CORS never stops `curl`/Postman; verify identity and resource ownership server-side.
15. **Cookie scope:** avoid overly broad `Domain` or wrong `Path`; never log session IDs.
16. **Cache/Vary:** prevent CDNs/proxies from caching ACAO or private responses across origins/users.
17. **Logging:** never log raw `Cookie`, `Authorization`, request bodies, or untrusted client-supplied forwarded headers as verified facts.
18. **Negative tests:** test attacker `Host`/`Forwarded`, disallowed origins, wrong schemes/ports, prefix duplication, and proxy 502s.
19. **Error behavior:** proxy/Security/container errors can bypass MVC CORS; test error paths E2E and monitor them.
20. **Deployment:** measure p95/p99 latency, graceful drain, keep-alive, redirects, retries, and idempotency during rolling updates.

## 24. Self-Check Questions

**1.** Why does Spring Boot emit `Location: http://127.0.0.1:8080` even when users visit via HTTPS?  
**Answer:** The backend receives plain internal HTTP; without trusted forwarded metadata, request metadata does not reflect the public scheme or host.

**2.** Does `server.forward-headers-strategy=framework` protect against spoofed `X-Forwarded-Host` by itself?  
**Answer:** No. The filter trusts incoming headers. The edge must strip/overwrite them and the backend must not be directly reachable.

**3.** Are `NATIVE` and `FRAMEWORK` identical?  
**Answer:** No. `NATIVE` delegates to the embedded server; `FRAMEWORK` uses `ForwardedHeaderFilter`/`Transformer`, often needed for `X-Forwarded-Prefix`.

**4.** How does NGINX `proxy_pass http://127.0.0.1:8080/;` inside `location /shop/` differ from omitting the trailing slash?  
**Answer:** With the `/` URI, NGINX replaces the matched prefix with `/`; without a URI, path forwarding rules differ. Always test against your topology.

**5.** Can CORS `allowedOrigins` take `https://app.example.test/shop`?  
**Answer:** No; an origin is scheme + host + port, while path scoping is defined separately in `CorsRegistry`.

**6.** If the app and API are same-site yet on different hosts, is CORS still required?  
**Answer:** Yes. Same-site does not mean same-origin.

**7.** Does CORS protect the server against `curl` or non-browser clients?  
**Answer:** No. It restricts browser JavaScript from reading cross-origin responses.

**8.** Once preflight `OPTIONS` succeeds, is the actual `POST` guaranteed to succeed?  
**Answer:** No. The browser still sends `POST`, the server still runs validation/auth/business logic, and the actual response must carry matching ACAO.

**9.** Why can a `GET` fail CORS even when no `OPTIONS` request appears?  
**Answer:** Simple GETs skip preflight; the browser blocks JavaScript from reading the actual response if ACAO is missing or mismatched.

**10.** Is `allowedOrigins("*")` with `allowCredentials(true)` valid?  
**Answer:** No. Spring Framework rejects wildcard `allowedOrigins` alongside `allowCredentials(true)`; use exact origins or carefully constrained patterns if truly needed.

**11.** Does `Access-Control-Allow-Headers` allow JS to read `Location` from the response?  
**Answer:** No. JS reads response `Location` thanks to `Access-Control-Expose-Headers`.

**12.** Can adding `@CrossOrigin` on a controller widen scope beyond global config?  
**Answer:** Yes, because Spring MVC combines local and global policies. Review and test carefully.

**13.** Is `X-Forwarded-For` guaranteed proof of the user's IP?  
**Answer:** Not without a verified trusted-proxy chain; clients can spoof leading values if the edge fails to sanitize.

**14.** When the frontend uses session cookies, does CORS replace CSRF protection?  
**Answer:** No. Appropriate CSRF and authorization controls remain mandatory, alongside browser cookie policies.

**15.** Does a `SameSite=Lax` cookie mean CORS is no longer needed?  
**Answer:** No. `SameSite` governs cookie transmission by site context; CORS governs cross-origin response access from JavaScript.

**16.** An app sets `server.servlet.context-path=/shop` while NGINX strips `/shop` and sends `X-Forwarded-Prefix`. What can break?  
**Answer:** Duplicate prefixes, route mismatches, or broken `Location` URLs. Pick one consistent strategy and test E2E.

**17.** If `curl` sends a malicious `Origin` and still receives HTTP 201, has CORS failed?  
**Answer:** Not necessarily: CORS does not block non-browser HTTP requests. For cross-origin browser requests, JS cannot read the response without ACAO, and auth/CSRF must protect side effects.

**18.** Why must proxy chains handle both RFC `Forwarded` and `X-Forwarded-*` together?  
**Answer:** Frameworks and gateways may inspect both; overwriting only one family allows attackers to spoof the other.

**19.** Why do CDNs need `Vary: Origin`?  
**Answer:** CORS responses vary by `Origin`; caches must key variants separately so one origin's policy isn't served to another.

**20.** Does a passing MockMvc test with `X-Forwarded-Prefix` prove NGINX strips attacker headers?  
**Answer:** No. MockMvc tests Spring's handling; only E2E tests through the edge verify the real trust boundary.

## 25. Official References

1. [Spring Boot 3.3 — Embedded Web Servers, Running Behind a Front-end Proxy](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html)
2. [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
3. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
4. [Spring Framework 6.1 — ForwardedHeaderFilter API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html)
5. [Spring Framework — Forwarded Header Filter and Security Considerations](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
6. [Spring Framework 6.1 — CORS](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc-cors.html)
7. [Spring Framework 6.1 — CorsConfiguration API](https://docs.spring.io/spring-framework/docs/6.1.1/javadoc-api/org/springframework/web/cors/CorsConfiguration.html)
8. [Spring Security — CORS Servlet Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
9. [NGINX — ngx_http_proxy_module / proxy_pass / proxy_set_header](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
10. [NGINX — Reverse Proxy Admin Guide](https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/)
11. [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)
12. [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
13. [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS)
14. [MDN — Same-Origin Policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy)
15. [MDN — HTTP Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies)
16. [OWASP — HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html)
17. [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)

**Conclusion:** Deploying Spring Boot behind a reverse proxy involves two distinct yet connected concerns. **Forwarded headers** tell the application its public scheme, host, port, and prefix—provided it **trusts only headers normalized by a trusted proxy**. **CORS** governs which browser origins may read cross-origin responses on **explicitly scoped API paths**, without replacing authentication, authorization, or CSRF. A sound configuration aligns NGINX rewrites, `server.forward-headers-strategy=framework`, Spring MVC `CorsRegistry`, cookie/redirect policies, and **tests across MockMvc, real HTTP, and E2E through the HTTPS proxy**, including malicious `Origin` and spoofed `Forwarded` cases.