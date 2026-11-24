# Reverse Proxies, Ingress, and Public URLs with Context Paths

**Module:** Spring Boot - web-runtime  
**Parent topic:** Application Deployment

## 1. Why Does an API Work Inside a Container Yet Break When Exposed to the Internet?

Suppose a Spring Boot application runs at an internal address:

~~~text
http://catalog-service:8080/api/items/42
~~~

Users must only access the public URL:

~~~text
https://api.example.test/shop/api/items/42
~~~

A reverse proxy, API gateway, or Kubernetes Ingress can terminate TLS, change the host/port, and alter the path. A GET request may reach the controller and return 200, yet a `201 Created` response returns a `Location` header like this:

~~~http
HTTP/1.1 201 Created
Location: http://catalog-service:8080/api/items/43
~~~

This URL leaks the internal hostname, lacks HTTPS, and omits **/shop**. External clients may fail to open it, and browsers may block HTTP resources inside HTTPS pages. Similar bugs occur in 302 redirects, self links, HATEOAS, OAuth2 callbacks, Swagger UI, or CSS/JavaScript paths.

Sometimes the prefix is doubled instead:

~~~text
https://api.example.test/shop/shop/api/items/42
~~~

Or requests return 404 even though the controller exists, because the proxy stripped **/shop** while Tomcat still ran with **`server.servlet.context-path=/shop`**.

**Two separate problems need to be solved:**

1. **Inbound routing:** which path does the proxy send to the backend? Do the Servlet context path and `@RequestMapping` match?
2. **Outbound URL generation:** when constructing `Location`, redirects, and links, which public scheme, host, port, and prefix does the backend use?

An application can get question 1 right while failing question 2. This lesson explains how to configure both consistently and verify both.

### Learning Objectives

After this lesson, you will be able to:

- Distinguish public URL, upstream URL, Servlet context path, Spring MVC mapping, and Ingress path.
- Compare proxy **preserve**, **strip**, and **replace** path prefix strategies.
- Use **`server.servlet.context-path`** properly and avoid doubling prefixes in controllers.
- Understand **`Forwarded`**, **`X-Forwarded-Host`**, **`X-Forwarded-Proto`**, **`X-Forwarded-Port`**, **`X-Forwarded-Prefix`**, and **`X-Forwarded-For`**.
- Choose **`server.forward-headers-strategy=none/native/framework`** based on topology.
- Understand the difference between **`proxy_pass`** with/without a trailing slash and `ingress-nginx` `rewrite-target`.
- Write a **Spring Boot 3.3 / Java 17+** application generating URIs with **`ServletUriComponentsBuilder`**.
- Verify GET links, POST **201 `Location`**, and **302 `Location`** redirects over real HTTP and through a proxy.
- Evaluate Host-header poisoning, OAuth2 redirects, cookies, static assets, CORS, Actuator, and probes.
- Build a deployment checklist usable when moving applications to Kubernetes.

## 2. URL Model at Each Hop

A request may travel through:

~~~text
Browser:
  https://api.example.test/shop/api/items/42
       |
       v
Ingress / Nginx / Load balancer
  TLS: HTTPS -> backend HTTP
  Host: api.example.test -> catalog-service
  Prefix: maybe preserve/strip/replace /shop
       |
       v
Spring Boot / embedded Tomcat :8080
  Servlet context path
       |
       v
DispatcherServlet + @RequestMapping("/api/items")
  GET /{id}
       |
       v
Response: body JSON, Location, redirect, links
       |
       v
Proxy -> Browser
~~~

Key concepts:

| Concept | Example | Who is responsible? |
| --- | --- | --- |
| Public origin | `https://api.example.test` | DNS, TLS, and public proxy. |
| Public path | `/shop/api/items/42` | Public routing contract. |
| Upstream origin | `http://catalog-service:8080` | Internal service/network. |
| Upstream request path | `/api/items/42` or `/shop/api/items/42` | Proxy rewrite configuration. |
| Servlet context path | empty, `/shop`, or `/internal` | Spring Boot `server.servlet.context-path`. |
| MVC handler mapping | `/api/items/{id}` | `@RequestMapping`/`@GetMapping`. |
| Forwarded prefix | `/shop` | Trusted proxy metadata for effective URLs. |
| Generated public URL | `https://api.example.test/shop/api/items/43` | Spring URI builder, redirect, HATEOAS, etc. |

**The Servlet context path is not a string automatically prepended to whatever URL the proxy sends.** It determines where the application is mounted inside the Servlet container. If the backend has context path **/shop**, direct requests must contain `/shop` before the MVC mapping. If the backend runs at the root context, `/shop` is a concern of the proxy or client-facing link building.

To debug issues, always write out the equation:

~~~text
Public path -> Proxy rewrite -> Upstream path
Upstream path - Servlet context path -> MVC mapping
Generated public origin/prefix -> Link, Location, redirect
~~~

If this equation breaks at any hop, the configuration can produce 404s, redirect loops, or wrong hosts/paths.

## 3. Three Common Deployment Patterns

Assume clients must reach **/shop/api/items/42** while the MVC handler mapping is **/api/items/{id}**.

| Pattern | Public path | Path received by backend | Backend context path | `X-Forwarded-Prefix` metadata |
| --- | --- | --- | --- | --- |
| **Preserve** | `/shop/api/items/42` | `/shop/api/items/42` | `/shop` | Not required; host/proto still needed if public differs from backend. |
| **Strip** | `/shop/api/items/42` | `/api/items/42` | empty | `/shop` when generated public URLs are needed. |
| **Replace** | `/shop/api/items/42` | `/internal/api/items/42` | `/internal` | `/shop` to reflect the public prefix instead of internal. |

### Preserve Path

Backend mounts directly at **/shop**:

~~~properties
server.servlet.context-path=/shop
~~~

The proxy forwards the path unchanged. Handler **`@GetMapping("/api/items/{id}")`** works under `/shop`. When the public host/proto differs from the backend, use trusted forwarded headers so generated URIs use the right scheme/host.

### Strip Path

Backend mounts at root (no context path configured). The proxy strips `/shop` and forwards `/api/items/42`. For the server to generate public links including `/shop`, the proxy adds **`X-Forwarded-Prefix: /shop`** and Boot handles it via the `framework` strategy.

### Replace Path

A legacy backend mounts at **/internal**; the proxy rewrites `/shop` to `/internal` while telling the server the public prefix `/shop`. With Spring Framework handling `X-Forwarded-Prefix` properly, generated links reflect `/shop` instead of `/internal`.

**Never add `/shop` manually to every `@RequestMapping`** when `/shop` is already mounted by the Servlet container. Do not add a context path just because clients see `/shop` if the proxy already strips it. **`X-Forwarded-Prefix` does not make the Servlet container create a context path**; it communicates the external view so URI builders reflect the public path.

## 4. server.servlet.context-path and Other Base Path Types

Example:

~~~properties
server.port=8080
server.servlet.context-path=/shop
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/items")
class ItemController {
    @GetMapping("/{id}")
    public String get(@PathVariable long id) {
        return "item:" + id;
    }
}
~~~

This is an illustrative snippet, not the class in the main demo below. The right direct request is:

~~~text
GET http://localhost:8080/shop/api/items/42
~~~

**`GET http://localhost:8080/api/items/42`** does not enter the same context. Do not confuse it with:

- **`spring.mvc.servlet.path`**: mapping prefix of `DispatcherServlet`, a different layer from the Servlet context path.
- **`management.endpoints.web.base-path`**: Actuator path (default `/actuator`).
- **`management.server.base-path`**: base path when the management server runs on a separate port.
- **`spring.webflux.base-path`**: base path for the WebFlux reactive stack, not equivalent to a Servlet context path.
- **Ingress path**: routing rule on the ingress controller, which may or may not rewrite.
- **Frontend base URL/HTML base href**: affects browser routes/assets; not fixed automatically by the servlet context path.

If you put `/shop` in Servlet context, `DispatcherServlet` path, and `@RequestMapping`, the prefix can be duplicated multiple times in URLs.

**Actuator on the same port:** when management endpoints share the main servlet listener, default `/actuator` is relative to the servlet context path. For example, backend context `/shop` → direct path is typically **`/shop/actuator/health`** when health is exposed.

**Actuator on a separate port:** when a dedicated **`management.server.port`** is configured, `management.endpoints.web.base-path` is relative to `management.server.base-path`, not the main servlet context path. Health probes must check the real backend port/path, distinct from public ingress URLs.

## 5. Forwarded Headers Help the Backend See the Client's Perspective

Proxies can pass standard RFC 7239 metadata:

~~~http
Forwarded: proto=https;host=api.example.test
~~~

Or de facto headers:

~~~http
X-Forwarded-Host: api.example.test
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-Prefix: /shop
X-Forwarded-For: 203.0.113.8
~~~

| Header | Meaning | Failure when missing or wrong |
| --- | --- | --- |
| **`Forwarded`** | Original host/proto/for/by per RFC 7239. | Server unaware of public origin when proxy changes it. |
| **`X-Forwarded-Host`** | Public hostname, optionally with port. | Links use `catalog-service` or `127.0.0.1`. |
| **`X-Forwarded-Proto`** | Public `http`/`https` scheme. | Redirects downgrade to `http` even when browser uses HTTPS. |
| **`X-Forwarded-Port`** | Public port, e.g. 443. | Links leak `:8080` or wrong public port. |
| **`X-Forwarded-Prefix`** | Public path prefix, e.g. `/shop`. | Links omit `/shop` after proxy strips it. |
| **`X-Forwarded-For`** | Client and proxy IP chain. | Server sees proxy IP instead of client; easily spoofed if unsanitized. |

**`X-Forwarded-Prefix` must contain a path prefix, not a full URL.** Correct is `/shop`, not `https://api.example.test/shop`. Nor does it alter the path the reverse proxy already sent to the container; request routing and URI generation are two separate jobs.

Some proxies emit the standard **`Forwarded`** header while others emit `X-Forwarded-*`. Do not allow both forms to carry conflicting host/proto values. Decide which layer may overwrite them and which form Spring/the container consumes.

### Security Concerns

An Internet client can also send forged `X-Forwarded-Host` and `X-Forwarded-Prefix` headers. Spring cannot tell whether a header came from a trusted proxy or an attacker. Only enable interpretation when:

1. The edge proxy **strips all `Forwarded`/`X-Forwarded-*` headers** sent by public clients.
2. The edge or trusted hop **rewrites the correct values** from controlled virtual host/TLS/route config.
3. The backend accepts traffic only from trusted proxies/networks; the raw application port is never exposed to the Internet.
4. A public host allowlist or fixed public origin is enforced when the service serves a single domain.
5. Spoofed headers are tested through the public edge to verify `Location`/`self` cannot be altered.

Otherwise, attackers can trigger **host-header poisoning**, open redirects, or malicious links in logins, emails, password resets, and JSON responses. **`ForwardedHeaderFilter` does not replace stripping forged headers at the edge.**

## 6. Three Modes of server.forward-headers-strategy

Spring Boot 3.3 supports:

~~~properties
server.forward-headers-strategy=framework
~~~

Values:

| Strategy | Mechanism | When to use |
| --- | --- | --- |
| **`none`** | Boot applies no forwarded-headers strategy. | No trusted proxy, or public URLs handled by explicit config. |
| **`native`** | Delegated to the web server/container such as Tomcat `RemoteIpValve`. | When using native scheme/host/client-IP handling and supported headers are verified. |
| **`framework`** | Servlet MVC uses **`ForwardedHeaderFilter`**; reactive WebFlux uses **`ForwardedHeaderTransformer`**. | Usually appropriate when `X-Forwarded-Prefix` and proxy-aware URL/redirect generation are needed. |

**Boot 3.3 docs** note `native` suffices for common headers like `X-Forwarded-For`/`Proto` with compatible proxies. When more handling is required—especially prefixes—`framework` is usually the practical option. Do not assume `native` handles `X-Forwarded-Prefix` identically across Tomcat, Jetty, Undertow, and Reactor Netty; test on the real container.

**The default strategy varies depending on the cloud platform Boot detects.** In some cloud environments it may pick `native`; elsewhere `none`. Do not rely on an invisible default when public prefixes matter: set it explicitly and verify actual behavior.

### How ForwardedHeaderFilter Works

In the Servlet stack, the filter wraps the request/response so **`getScheme()`**, **`getServerName()`**, **`getServerPort()`**, effective context path/request URI, and redirect URLs reflect forwarded metadata. URI builders such as **`ServletUriComponentsBuilder`** or **`WebMvcLinkBuilder`** can then construct links using the public origin/prefix.

**Do not declare an extra `ForwardedHeaderFilter` bean manually** just because you enabled the `framework` strategy. Boot auto-configures it. Double registration or wrong filter ordering can produce unpredictable behavior. If manually registering the filter or using `removeOnly` mode, understand ordering, `REQUEST`/`ASYNC`/`ERROR` dispatchers, and trust policy.

### Tomcat Context Root Redirect Case

Spring Boot 3.3 documentation notes that when TLS terminates at a front-end proxy, check:

~~~properties
server.tomcat.redirect-context-root=false
~~~

This setting ensures **`X-Forwarded-Proto`** is processed before Tomcat redirects the context root to append a trailing **`/`**. Otherwise, an HTTPS request to **/shop** could be redirected to **`http://.../shop/`** with the wrong public scheme.

**This is a Tomcat-specific property**; it does not change `server.servlet.context-path`, fix rewrites, or replace edge TLS requirements.

## 7. Nginx Preserve Prefix: Watch proxy_pass Without a Trailing Slash

Suppose the backend runs with:

~~~properties
server.servlet.context-path=/shop
server.forward-headers-strategy=framework
server.tomcat.redirect-context-root=false
~~~

An Nginx server block **for local lab use only**:

~~~nginx
server {
    listen 8088;
    server_name localhost;

    location = /shop {
        return 308 /shop/;
    }

    location /shop/ {
        # Only upstream host:port, no URI trailing slash.
        proxy_pass http://127.0.0.1:8080;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
~~~

In this layout, **`http://localhost:8088/shop/api/items/42`** reaches the backend as **`/shop/api/items/42`**. The controller mapping **`/api/items/{id}`** still matches because the Servlet context path is `/shop`.

There is no need to manually add `X-Forwarded-Prefix` in preserve mode when the backend already receives the same prefix; if a real ingress emits that header automatically, test the interaction instead of appending it again.

**This is not a production TLS configuration.** Public environments require HTTPS certificates, allowlisted `Host` headers, and edge header sanitization. Nginx's `$host` variable in the lab reflects the inbound `Host`; production must never treat arbitrary `Host` headers from the Internet as the canonical public hostname.

## 8. Nginx Strip Prefix: proxy_pass With a Trailing Slash

Root-context backend application:

~~~properties
# Do not set server.servlet.context-path=/shop.
server.forward-headers-strategy=framework
~~~

Local Nginx server block:

~~~nginx
server {
    listen 8088;
    server_name localhost;

    location = /shop {
        return 308 /shop/;
    }

    location /shop/ {
        # URI "/" replaces matching prefix /shop/.
        proxy_pass http://127.0.0.1:8080/;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-Prefix /shop;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
~~~

Here, **`/shop/api/items/42`** becomes **`/api/items/42`** going to the backend. In these two fixed snippets, the trailing **`/`** on **`proxy_pass`** is the key difference: with a URI **`/`**, Nginx replaces the matched location prefix with **`/`**; without a URI, it generally forwards the original path.

**This rule depends on configuration.** If Nginx uses regex locations, variables, `rewrite` directives, or other `proxy_pass` URI forms, semantics can change. Always test the real upstream request path rather than applying the trailing-slash rule from these two snippets universally.

Generated links via the effective request context become:

~~~text
http://localhost:8088/shop/api/items/42
~~~

against the local Nginx lab on HTTP port 8088. On a properly configured public HTTPS ingress, public scheme/host/port match accordingly:

~~~text
https://api.example.test/shop/api/items/42
~~~

### Trap: Setting context-path=/shop While the Proxy Already Strips It

If Nginx sends **`/api/items/42`** while the Servlet application is mounted at **`/shop`**, the server returns 404 before any controller matches. Adding `X-Forwarded-Prefix=/shop` only affects URL generation; **it does not change the backend servlet context path**. You must choose either preserve path, or root context in strip mode.

## 9. When the Public Prefix Differs from the Internal Context Path

A legacy application deploys with:

~~~properties
server.servlet.context-path=/internal
server.forward-headers-strategy=framework
~~~

Yet the public URL must use `/shop`:

~~~text
Public:   https://api.example.test/shop/api/items/42
Upstream: http://catalog-service:8080/internal/api/items/42
Header:   X-Forwarded-Prefix: /shop
~~~

The proxy must **rewrite `/shop` to `/internal`** when forwarding requests to the backend so Servlet routing matches. `X-Forwarded-Prefix` tells the app the public prefix for link generation. When Spring Framework processes the forwarded prefix properly, generated URLs reflect `/shop` rather than `/internal`.

Do not build URLs by manually concatenating **`/shop + /internal + /api/items`**. Use URI builders backed by the effective request context and test through the public ingress. This pattern suits legacy apps, though it is more complex than preserve or strip, requiring contract tests for `Location`, redirects, and assets.

## 10. Kubernetes Ingress: Path Matching Is Not Rewriting

The **standard Ingress API** defines host/path routing and backend Services. It does not standardize how rewrites or `X-Forwarded-Prefix` generation work. Many annotations only apply to **a specific controller**.

### 10.1. Ingress Preserve Path

Ingress snippet:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: catalog-preserve
spec:
  ingressClassName: nginx
  rules:
    - host: api.example.test
      http:
        paths:
          - path: /shop
            pathType: Prefix
            backend:
              service:
                name: catalog-svc
                port:
                  number: 8080
~~~

If the controller forwards the path unchanged, the backend must serve **`/shop/api/items/42`**, typically via **`server.servlet.context-path=/shop`**.

**`pathType: Prefix`** defines URL segment matching semantics, not automatic `/shop` stripping. The manifest above illustrates path routing; it **does not include TLS, Service, Deployment, or security hardening**, and is not a complete production configuration.

### 10.2. Ingress-nginx Rewrite Path

Controller-specific example for `ingress-nginx`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: catalog-strip
  annotations:
    nginx.ingress.kubernetes.io/use-regex: "true"
    nginx.ingress.kubernetes.io/rewrite-target: /$2
spec:
  ingressClassName: nginx
  rules:
    - host: api.example.test
      http:
        paths:
          - path: /shop(/|$)(.*)
            pathType: ImplementationSpecific
            backend:
              service:
                name: catalog-svc
                port:
                  number: 8080
~~~

On an `ingress-nginx` supporting this rule, **`/shop/api/items/42`** can be rewritten to **`/api/items/42`** via the second capture group **`$2`**. A **root-context backend** will match the controller.

**YAML alone does not prove `X-Forwarded-Prefix` is added automatically.** Verify whether the controller/gateway actually emits **`X-Forwarded-Prefix: /shop`**. If not, configure it per controller and trust boundary; avoid casually enabling `configuration-snippet` as many clusters block it for security risk.

**`IngressClass`/controller-specific:** `nginx.ingress.kubernetes.io` annotations do not automatically apply to Traefik, Envoy Gateway, NGINX Inc, managed cloud ingresses, or Gateway API implementations. Whenever changing controllers or Kubernetes versions, re-audit rewrite behavior and HTTPS/forwarding headers from scratch.

## 11. Preventing Host-Header Poisoning and Open Redirects

An attacker can send to the public edge:

~~~http
GET /shop/api/items/42 HTTP/1.1
Host: api.example.test
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
X-Forwarded-Prefix: /evil
~~~

If the edge forwards forged headers straight to the backend and Boot trusts them, the API can emit:

~~~http
Location: https://attacker.example/evil/api/items/42
~~~

This can poison redirects, resource links, OAuth2 callbacks, or email/password-reset links. **`ForwardedHeaderFilter` does not verify header trustworthiness by itself.**

Defenses:

1. Edge **strips or overwrites all `Forwarded`/`X-Forwarded-*`** sent by Internet clients.
2. Trusted edge constructs headers from controlled virtual host, TLS listener, and allowlisted public routes.
3. Backend accepts traffic only from authorized edge/networks; close public backend listeners.
4. Across multiple proxy hops, define which hop owns/overwrites the `Forwarded` chain.
5. Never let raw `Host` or `X-Forwarded-Host` choose the domain for email/reset links.
6. Test spoofed headers through the **public ingress** to confirm `self`/`Location` retain the canonical hostname.
7. Never treat `X-Forwarded-For` as authenticated user identity.
8. If there is no trusted proxy, keep strategy `none` or use an admin-configured fixed public base URL.

For Java Servlet apps configuring **`ForwardedHeaderFilter`** directly, there is a **`removeOnly`** mode to strip headers without honoring them. That is an option when the app should ignore forwarded headers, but it must be intentionally designed rather than enabling `framework` strategy while exposing the app to arbitrary public requests.

## 12. Runnable Demo: Spring Boot 3.3, Java 17+

This example includes GET, POST 201, and 302 redirect. URLs are built from the Servlet request context without hardcoding localhost or a public hostname.

**Environment:** Spring Boot **3.3.13**, Java 17+, Maven, Spring MVC, embedded Tomcat. This example targets the 3.3 line; new production systems should pick a Boot line still under active maintenance.

Structure:

~~~text
public-path-demo/
  pom.xml
  src/main/java/com/example/publicpath/
    PublicPathApplication.java
    ItemView.java
    CreateItemRequest.java
    ItemController.java
  src/main/resources/
    application.properties
  src/test/java/com/example/publicpath/
    StrippedPrefixHttpTests.java
    PreservedPrefixHttpTests.java
    ItemControllerMvcTests.java
~~~

### 12.1. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>public-path-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`spring-boot-starter-web`** brings Servlet Spring MVC and BOM-aligned Tomcat/Jackson; `starter-test` brings JUnit Jupiter, MockMvc, and `SpringBootTest`.

### 12.2. application.properties

~~~properties
spring.application.name=public-path-demo
server.port=8080

# Default root context for the strip-path demo.
# When preserve is needed: start with --server.servlet.context-path=/shop

# Only use framework strategy when the reverse proxy is genuinely trusted.
server.forward-headers-strategy=framework

# Needed when Tomcat sits behind a TLS termination proxy.
server.tomcat.redirect-context-root=false

server.error.include-message=never
server.error.include-stacktrace=never
~~~

**Never expose the demo backend port publicly with config trusting forwarded headers.** The headers in the tests below are synthetic to test URI generation assuming a sanitizing proxy; production must enforce network policies and edge verification.

### 12.3. Main Class

**`src/main/java/com/example/publicpath/PublicPathApplication.java`**:

~~~java
package com.example.publicpath;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PublicPathApplication {
    public static void main(String[] args) {
        SpringApplication.run(PublicPathApplication.class, args);
    }
}
~~~

### 12.4. DTOs

**`src/main/java/com/example/publicpath/ItemView.java`**:

~~~java
package com.example.publicpath;

public record ItemView(
        long id,
        String name,
        String self,
        String collection) {
}
~~~

**`src/main/java/com/example/publicpath/CreateItemRequest.java`**:

~~~java
package com.example.publicpath;

public record CreateItemRequest(String name) {
}
~~~

`ItemView` has two absolute URL fields for inspection. These are **not automatic HAL**; with Spring HATEOAS, `linkTo`/`WebMvcLinkBuilder` also require the right effective request context, though this demo API keeps dependencies minimal.

### 12.5. Complete Controller

**`src/main/java/com/example/publicpath/ItemController.java`**:

~~~java
package com.example.publicpath;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

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
@RequestMapping("/api/items")
public class ItemController {

    private record Item(long id, String name) {
    }

    private final Map<Long, Item> items =
            new ConcurrentHashMap<>(Map.of(
                    42L, new Item(42L, "Example item")
            ));

    private final AtomicLong nextId = new AtomicLong(100L);

    private URI itemUri(long id) {
        return ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/api/items/{id}")
                .buildAndExpand(id)
                .toUri();
    }

    private URI collectionUri() {
        return ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/api/items")
                .build()
                .toUri();
    }

    private ItemView view(Item item) {
        return new ItemView(
                item.id(),
                item.name(),
                itemUri(item.id()).toString(),
                collectionUri().toString());
    }

    @GetMapping(value = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ItemView> one(
            @PathVariable("id") long id) {

        Item item = items.get(id);
        if (item == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(view(item));
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ItemView> create(
            @RequestBody CreateItemRequest input) {

        if (input == null || input.name() == null
                || input.name().isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        long id = nextId.getAndIncrement();
        Item created = new Item(id, input.name().trim());
        items.put(id, created);

        return ResponseEntity.created(itemUri(id))
                .body(view(created));
    }

    @GetMapping("/{id}/redirect")
    public ResponseEntity<Void> redirect(
            @PathVariable("id") long id) {

        if (!items.containsKey(id)) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.status(HttpStatus.FOUND)
                .location(itemUri(id))
                .build();
    }
}
~~~

**Analysis:**

- The controller maps only **`/api/items`** and **`/{id}`**, without adding `/shop` to each route.
- **`ServletUriComponentsBuilder.fromCurrentContextPath()`** retrieves the effective servlet context of the current request, including origin and context path processed from trusted forwarding.
- **`ResponseEntity.created(itemUri(id))`** returns `201 Created` with `Location` as an absolute URI.
- **`ResponseEntity.status(HttpStatus.FOUND).location(...).build()`** returns `302 Found` and `Location`; the controller does not follow redirects server-side.
- The JSON body includes **`self`** and **`collection`** to test links inside representations.
- Data is stored in `ConcurrentHashMap` and `AtomicLong` to run standalone without a DB; insufficient authorization/validation for production.
- The URI builder only solves URL semantics; it does not prevent host-header poisoning if the proxy does not enforce trust.

## 13. Run the Demo and Test with curl

From the directory containing `pom.xml`, with Java 17+ and Maven:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Once the server is up, direct request (bypassing proxy):

~~~bash
curl -si \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/api/items/42
~~~

Typical body:

~~~json
{
  "id": 42,
  "name": "Example item",
  "self": "http://127.0.0.1:8080/api/items/42",
  "collection": "http://127.0.0.1:8080/api/items"
}
~~~

This is the **direct-backend origin** since no forwarded metadata was sent. Now simulate a proxy that strips `/shop` and sends matching headers:

~~~bash
curl -si \
  -H 'Accept: application/json' \
  -H 'X-Forwarded-Host: api.example.test' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Port: 443' \
  -H 'X-Forwarded-Prefix: /shop' \
  http://127.0.0.1:8080/api/items/42
~~~

Valid output must have **`self`** with scheme **`https`**, host **`api.example.test`**, path **`/shop/api/items/42`**, and **`collection`** with path **`/shop/api/items`**. Typical representation:

~~~json
{
  "id": 42,
  "name": "Example item",
  "self": "https://api.example.test/shop/api/items/42",
  "collection": "https://api.example.test/shop/api/items"
}
~~~

**The standard port 443 may be rendered explicitly by some URI builders/configurations.** In portable tests, compare scheme/host/path and accept port `-1` or `443` unless canonical formatting is strictly required.

### POST 201 Created

~~~bash
curl -si \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -H 'X-Forwarded-Host: api.example.test' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Prefix: /shop' \
  --data-binary '{"name":"Created via API"}' \
  http://127.0.0.1:8080/api/items
~~~

Expected **201**, with `Location` carrying the public path **`/shop/api/items/{id}`**. The ID comes from `AtomicLong` and usually starts at `100` for the first create on a fresh JVM; do not hardcode `100` in tests when state can change.

### Redirect 302 Found

~~~bash
curl -si \
  -H 'X-Forwarded-Host: api.example.test' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Prefix: /shop' \
  http://127.0.0.1:8080/api/items/42/redirect
~~~

Expected **302**, with `Location` set to the public URI of item 42. **Do not use `curl -L`** when inspecting the raw 302 response, because `-L` follows redirects automatically and can hide errors in the initial redirect.

### Launching in Preserve Mode

Stop the server, then:

~~~bash
mvn spring-boot:run \
  -Dspring-boot.run.arguments="--server.servlet.context-path=/shop"
~~~

The right backend path is now **`http://127.0.0.1:8080/shop/api/items/42`**. In preserve mode, do not send `X-Forwarded-Prefix` when the public prefix is already in the Servlet context; only forwarded host/proto are needed if the public origin differs from the backend.

**Caution:** `curl` calls sending synthetic `X-Forwarded-*` in this section are for localhost lab only and do not substitute for security testing through a trusted edge. If a backend is exposed publicly, any client can spoof identical headers.

## 14. HTTP Integration Test for the Strip Case

This is **`SpringBootTest(RANDOM_PORT)`** against a real embedded HTTP server without Nginx. We simulate trusted forwarding headers to verify the URL builder.

Create **`src/test/java/com/example/publicpath/StrippedPrefixHttpTests.java`**:

~~~java
package com.example.publicpath;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {"server.forward-headers-strategy=framework"})
class StrippedPrefixHttpTests {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newBuilder()
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    private final ObjectMapper json = new ObjectMapper();

    private HttpRequest.Builder forwarded(String path) {
        return HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(5))
                .header("X-Forwarded-Host", "api.example.test")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Port", "443")
                .header("X-Forwarded-Prefix", "/shop");
    }

    private void assertPublicUrl(String link, String path) {
        URI uri = URI.create(link);
        assertEquals("https", uri.getScheme());
        assertEquals("api.example.test", uri.getHost());
        assertEquals(path, uri.getPath());
        assertTrue(uri.getPort() == -1 || uri.getPort() == 443);
    }

    @Test
    void getGeneratesPublicLinks() throws Exception {
        HttpResponse<String> response = client.send(
                forwarded("/api/items/42").GET().build(),
                HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        JsonNode body = json.readTree(response.body());

        assertEquals(42, body.path("id").asInt());
        assertPublicUrl(body.path("self").asText(),
                "/shop/api/items/42");
        assertPublicUrl(body.path("collection").asText(),
                "/shop/api/items");
    }

    @Test
    void postGeneratesPublicLocation() throws Exception {
        HttpResponse<String> response = client.send(
                forwarded("/api/items")
                    .header("Content-Type", "application/json")
                    .header("Accept", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            "{\"name\":\"New item\"}"))
                    .build(),
                HttpResponse.BodyHandlers.ofString());

        assertEquals(201, response.statusCode());
        JsonNode body = json.readTree(response.body());
        long id = body.path("id").asLong();

        assertPublicUrl(response.headers()
                .firstValue("Location").orElseThrow(),
                "/shop/api/items/" + id);

        assertPublicUrl(body.path("self").asText(),
                "/shop/api/items/" + id);
    }

    @Test
    void redirectGeneratesPublicLocation() throws Exception {
        HttpResponse<String> response = client.send(
                forwarded("/api/items/42/redirect")
                    .GET().build(),
                HttpResponse.BodyHandlers.ofString());

        assertEquals(302, response.statusCode());
        assertPublicUrl(response.headers()
                .firstValue("Location").orElseThrow(),
                "/shop/api/items/42");
    }
}
~~~

**What is proven:** With a root Servlet context and Boot's `framework` strategy, forwarded scheme/host/prefix are applied to links and `Location` over a real HTTP request.

**What is not yet proven:** that the real ingress strips `/shop`, that the edge sanitizes headers, that public TLS works, or that DNS resolves. Because this test injects synthetic headers directly, it does not test the proxy trust boundary.

## 15. HTTP Integration Test for the Preserve Case

Create **`src/test/java/com/example/publicpath/PreservedPrefixHttpTests.java`**:

~~~java
package com.example.publicpath;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.servlet.context-path=/shop",
        "server.forward-headers-strategy=framework"
    })
class PreservedPrefixHttpTests {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newHttpClient();
    private final ObjectMapper json = new ObjectMapper();

    @Test
    void correctServletContextIsReflectedInSelf()
            throws Exception {

        HttpRequest req = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port
                        + "/shop/api/items/42"))
                .timeout(Duration.ofSeconds(5))
                .header("X-Forwarded-Host", "api.example.test")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Port", "443")
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                req, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());

        JsonNode body = json.readTree(response.body());
        URI self = URI.create(body.path("self").asText());

        assertEquals("https", self.getScheme());
        assertEquals("api.example.test", self.getHost());
        assertEquals("/shop/api/items/42", self.getPath());
        assertTrue(self.getPort() == -1 || self.getPort() == 443);
    }

    @Test
    void backendRootWithoutServletPrefixIsNotSameRoute()
            throws Exception {

        HttpRequest req = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port
                        + "/api/items/42"))
                .timeout(Duration.ofSeconds(5))
                .GET().build();

        HttpResponse<String> response = client.send(
                req, HttpResponse.BodyHandlers.ofString());

        assertEquals(404, response.statusCode());
    }
}
~~~

**Key point:** In the preserve test, GET to backend **`/shop/api/items/42`** succeeds because the Servlet app is mounted under `/shop`. A request omitting `/shop` does not reach the same Servlet context. Because the test deploys only one context, `404` is expected; on a server hosting multiple contexts, the status could differ.

**Do not send `X-Forwarded-Prefix` in the preserve test** since the public prefix is already present in the backend path; that is the main difference from the strip test.

## 16. MockMvc Tests the Controller, Not Proxy Integration

A fast MVC slice test can use **`@WebMvcTest`** and **`MockMvc`**. Create **`src/test/java/com/example/publicpath/ItemControllerMvcTests.java`**:

~~~java
package com.example.publicpath;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ItemController.class)
class ItemControllerMvcTests {

    @Autowired
    MockMvc mvc;

    @Test
    void itemMappingAndJsonAreCorrect() throws Exception {
        mvc.perform(get("/api/items/42")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.self",
                    endsWith("/api/items/42")));
    }

    @Test
    void unknownItemIs404() throws Exception {
        mvc.perform(get("/api/items/999")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isNotFound());
    }
}
~~~

`MockMvc` does not pass through sockets, TLS, Nginx, or Kubernetes. It verifies Spring MVC mappings and serialization, **not** real proxy rewrites or `X-Forwarded-Prefix`. Therefore your release pipeline needs both **`RANDOM_PORT` HTTP integration tests** and **public ingress tests**.

Run the suite:

~~~bash
mvn clean test
~~~

If Maven exits with code 0 after executing the test classes, the demo code/config passed its assertions. Never claim an environment passed tests merely because commands appear in the lesson; learners must create the project and run them locally or in CI.

## 17. Testing Through Public Ingress: Only After Deployment

Once DNS/TLS and the ingress are live, hit the public URL:

~~~bash
curl -si \
  -H 'Accept: application/json' \
  https://api.example.test/shop/api/items/42
~~~

Verify:

- HTTP 200, JSON contains item 42.
- `self` has **`https`**, host **`api.example.test`**, path **`/shop/api/items/42`**.
- `collection` has **`/shop/api/items`**.
- No **`/shop/shop`**, **`/internal`**, **`catalog-service:8080`**, `localhost`, or mixed-content `http` links.
- No redirect loop from `/shop` → `/shop/shop`.
- Query parameters/encoding preserved when real routes use query strings.

POST through public ingress:

~~~bash
curl -si \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary '{"name":"Public create"}' \
  https://api.example.test/shop/api/items
~~~

Require status **`201`** and **`Location`** as a public HTTPS link. Follow the exact `Location` returned by the server to GET the newly created item; do not hardcode the ID.

Check redirect:

~~~bash
curl -si \
  https://api.example.test/shop/api/items/42/redirect
~~~

Require status **`302`** and a valid `Location`. To verify the full redirect chain you can use **`curl -L`**, but while debugging inspect the `Location` of the initial response so you do not mask errors.

### Testing Spoofed Forwarded Headers at the Edge

~~~bash
curl -si \
  -H 'X-Forwarded-Host: attacker.example' \
  -H 'X-Forwarded-Proto: http' \
  -H 'X-Forwarded-Prefix: /evil' \
  https://api.example.test/shop/api/items/42
~~~

If the edge is properly protected, the response **must not switch the host to `attacker.example` or the prefix to `/evil`**. This is a critical security test distinct from synthetic tests hitting the backend directly. Run tests only in authorized environments; never scan third-party hosts.

## 18. Other Links Prone to Prefix Bugs

| Component | Common bug | How to check |
| --- | --- | --- |
| **POST 201 `Location`** | `http://internal:8080/api/items/100` | Inspect `Location`, follow GET via public origin. |
| **302/303 login/logout redirect** | Downgrades HTTPS to HTTP, drops `/shop` | Inspect redirect chain and `Location` status. |
| **Spring HATEOAS** | `_links.self`/`next`/`collection` miss prefix | Inspect HAL links and `WebMvcLinkBuilder` `linkTo`/`methodOn`. |
| **OAuth2/OIDC** | `redirect_uri` mismatches registered URI | Inspect scheme/host/prefix in callback. |
| **Session cookie** | `Path=/internal` while browser only accesses `/shop` | Inspect `Set-Cookie` `Path`, `Domain`, `Secure`, `SameSite`. |
| **Frontend SPA** | `fetch("/api/items")` hits origin root | Configure public API base or relative routing properly. |
| **Static assets** | `/assets/app.js` 404s due to missing `/shop` | Inspect HTML `base href` and build asset public path. |
| **OpenAPI/Swagger UI** | UI calls internal URL or `swagger-config` wrong path | Inspect spec `servers` and browser Network tab. |
| **Actuator** | Probes `/actuator/health` when backend context=`/shop` | Use real backend context and management port. |
| **CORS preflight** | `OPTIONS` 404/403 due to proxy rewrite or security | Test `Origin`/`OPTIONS` via public URL. |
| **WebSocket/SSE** | Handshake/stream URI misses prefix | Inspect Upgrade, timeouts, and proxy route. |
| **CDN cache** | Cache key ignores host/path/representation | Inspect response `Cache-Control`/`Vary` and proxy cache policy. |

**SPAs are especially error-prone:** a page served at **`https://example.test/shop/`** whose JavaScript runs **`fetch("/api/items/42")`** sends the request to **`https://example.test/api/items/42`**, not `/shop/api/items/42`. The Servlet context path cannot fix a root-relative literal URL constructed in frontend code. Fix the frontend's public base path, reverse proxy routing, or use public URLs supplied by the backend.

**Cookie path:** when the proxy strips `/shop` while the container runs at root, the session cookie `Path` may not match policy. If you need to scope the cookie strictly to `/shop`, set **`server.servlet.session.cookie.path=/shop`** after business/security review; do not set it blindly when multiple public prefixes share a cookie.

## 19. Spring Security, OAuth2, CORS, and Forwarded Origins

Spring Security generates login redirects, saved-request redirects, and OAuth2 `redirect_uri` values from the effective scheme/host/path. If trusted forwarding is misconfigured, the IdP can reject with **`redirect_uri_mismatch`** because the app generates an internal callback:

~~~text
http://catalog-service:8080/login/oauth2/code/provider
~~~

whereas the IdP has registered:

~~~text
https://api.example.test/shop/login/oauth2/code/provider
~~~

Fix the public origin/prefix and registered redirect URI properly; **never add dangerous wildcard redirect URIs** just to silence callback errors.

**CORS is not forwarded path handling.** CORS relies on `Origin`, `Access-Control-Allow-*`, and browser policy. `X-Forwarded-Prefix` does not enable CORS; `OPTIONS` preflight paths must be routed and handled properly by the ingress and `SecurityFilterChain`. With cookie-based sessions, CSRF protection remains required for unsafe methods.

**Never use unverified `Host`/`X-Forwarded-Host` headers to generate password-reset email links.** When the public origin is fixed, an admin-configured canonical public base URL is far safer than trusting client headers. If multi-tenant domains are supported, enforce a domain allowlist and canonicalization.

## 20. Actuator, Health Probes, and Management Paths

On the same server port:

~~~properties
server.servlet.context-path=/shop
management.endpoints.web.base-path=/actuator
management.endpoints.web.exposure.include=health
~~~

Same-port backends usually expose **`/shop/actuator/health`**. However, if:

~~~properties
management.server.port=8081
management.server.base-path=/manage
management.endpoints.web.base-path=/actuator
~~~

Management endpoints use the separate management server base path and port, **not automatically mounted under the main servlet context path**.

Kubelet probes normally hit the PodIP/container port or internal Service directly, **not necessarily going through the public Ingress**. Thus probe paths must match the **upstream/backend route**, rather than blindly copying the public `/shop` path. Distinguish readiness/liveness and separate vs main management ports.

Never expose all **`/actuator/`** endpoints on the public ingress just because a health probe returned 404. `loggers`, `env`, `heapdump`, `httpexchanges`, and `logfile` require a separate secured management plane.

## 21. Quick Symptom-Based Diagnostics

| Symptom | Common cause | Action |
| --- | --- | --- |
| Public GET `/shop/...` 404s, backend `/api/...` 200s | Proxy did not strip or backend context mismatches | Write out public → rewrite → upstream → servlet mapping. |
| Backend GET `/api/...` 404s when context=`/shop` | Backend path missing Servlet prefix | Preserve `/shop` when proxy forwards, or switch backend to root. |
| Links return `/shop/shop` | Prefix manually added in multiple layers | Remove duplicate concatenation, use URI builder, and test. |
| POST `Location` returns internal hostname | Forwarded host/scheme not processed | Verify edge headers, strategy, and builder. |
| Link has right host but drops `/shop` | Missing XFP or `native` does not support prefix | Trusted XFP + `framework`, or configured public base URI. |
| Redirect HTTPS → HTTP | Wrong XFP/Proto or premature Tomcat root redirect | Check `X-Forwarded-Proto` and `server.tomcat.redirect-context-root=false`. |
| `Location` points to `attacker.example` | Forged headers crossed trust boundary | Strip/overwrite at edge, host allowlist, private backend. |
| Cookie not sent after login | Wrong `Path`/`Domain`/`Secure`/`SameSite` | Inspect `Set-Cookie` on public response. |
| OAuth2 `redirect_uri_mismatch` | Wrong generated public origin/prefix | Check callback URL and IdP-registered URI. |
| CSS/JS 404s while API 200s | Frontend asset base missing `/shop` | Fix SPA public path and proxy static location. |
| Kubernetes probe 404s | Used public path instead of backend path | Determine exact context path/management port. |
| Ingress rewrite does not run | Different annotation/controller or wrong regex | Check `IngressClass` and real rules. |
| CORS `OPTIONS` 403s | Security or rewritten route issue | Test `Origin`/`OPTIONS` via ingress. |
| `MockMvc` green while public fails | `MockMvc` bypasses proxy | Test `RANDOM_PORT` and public topology. |
| Forwarded headers present yet URI still wrong | `none`/`native`/filter/order or hardcoded URLs | Check strategy, effective request, and code. |

## 22. Low-Risk Troubleshooting Runbook

1. Write down the **full public URL** users open, including scheme, host, port, and prefix.
2. Record the **actual upstream request URI** the ingress/proxy sends to the backend; do not guess from the Ingress manifest.
3. Check **`server.servlet.context-path`**, **`spring.mvc.servlet.path`**, and `@RequestMapping`.
4. Choose explicitly between preserve, strip, or replace. Never enable all prefix layers simultaneously.
5. Verify actual **`Forwarded`/`X-Forwarded-*`** emitted by the trusted proxy. Never trust unsanitized inbound headers.
6. Choose **`server.forward-headers-strategy`** matching your prefix behavior.
7. Use `ServletUriComponentsBuilder` or framework link builders instead of hardcoded origins.
8. Test GET body links, 201 `Location`, and 302 redirects, and follow the actual generated URLs.
9. Test session cookie `Path`, OAuth2 callbacks, SPA assets, and health endpoints.
10. Test spoofed forwarded headers through the public edge.
11. Add tests to CI and canary rollouts; maintain a rollback plan for Ingress rules and context configs.

**Measure at the right layer with metrics/traces:** a backend 404 may come from a controller or the Servlet context, while a 502/503 may come from the ingress failing to connect to the Service. Do not inspect only one backend log and assume the proxy is fine. Never log `Authorization`/`Cookie`/bodies while debugging.

## 23. Production Deployment Checklist

- [ ] Documented mapping table: public URL → proxy rewrite → upstream URI → Servlet context → MVC mapping.
- [ ] **`server.servlet.context-path`** configured properly for chosen preserve/strip/replace pattern.
- [ ] Same prefix is not duplicated across `@RequestMapping`, `DispatcherServlet` path, frontend, and proxy.
- [ ] Verified **`server.forward-headers-strategy`** against embedded server/version.
- [ ] With path rewrites, **`X-Forwarded-Prefix`** is injected by a trusted proxy and processed accurately by Spring.
- [ ] With TLS termination before Tomcat, checked **`server.tomcat.redirect-context-root=false`**.
- [ ] Edge strips untrusted `Forwarded`/`X-Forwarded-*` and sets canonical values.
- [ ] Backend isolated from direct public traffic, with `Host` allowlisting where needed.
- [ ] GET links/`self`, POST 201 `Location`, and 302/303 redirects use public scheme/host/path.
- [ ] No `/shop/shop`, `/internal`, `http://internal`, or `service:8080` in generated public links.
- [ ] Nginx `proxy_pass` slash behavior and ingress `rewrite-target`/capture groups tested.
- [ ] `IngressClass`/controller-specific annotations match the deployed ingress controller.
- [ ] Actuator management port/base-path accounted for separately, with admin data unexposed.
- [ ] Frontend SPA, static assets, Swagger UI/OpenAPI servers, and public API base use the right prefix.
- [ ] OAuth2 callbacks, session cookies, CSRF/CORS, and proxy routing verified.
- [ ] Includes `MockMvc` mapping tests, `RANDOM_PORT` forwarded tests, and public ingress end-to-end tests.
- [ ] Security test spoofing `X-Forwarded-Host`/`Proto`/`Prefix` through public edge passes.
- [ ] Re-run URL contract tests after upgrading Boot/Framework/ingress controller.

## 24. Self-Check Questions

**1. What does `server.servlet.context-path=/shop` do?**  
Mounts the Servlet application under `/shop` on the backend; MVC mappings are evaluated relative to that context.

**2. If the proxy strips `/shop` and the backend receives `/api/items/42`, which context path fits?**  
Root context (empty).

**3. If the proxy preserves `/shop` and the backend context path is `/shop`, is `X-Forwarded-Prefix` required for routing?**  
No; forwarded metadata is only used when public origin/prefix must be reflected in URL generation.

**4. Which header normally passes the public prefix when stripped?**  
`X-Forwarded-Prefix: /shop`.

**5. Which header indicates HTTPS on the public side after TLS termination?**  
`X-Forwarded-Proto: https` or `Forwarded` `proto=https`.

**6. Why might `Location` show `http://service:8080`?**  
The app built the URL from the upstream origin instead of trusted public forwarded metadata.

**7. What does `server.forward-headers-strategy=framework` use for Servlet Spring MVC?**  
Spring Framework's `ForwardedHeaderFilter`.

**8. Does `native` automatically support `X-Forwarded-Prefix` across every server/version?**  
Do not assume so; test specifically—`framework` is usually appropriate for prefix rewrites.

**9. Can `X-Forwarded-Host` be trusted directly from the Internet?**  
No. The edge must strip forged headers and write controlled canonical values.

**10. Why does Ingress `pathType: Prefix` not automatically strip the prefix?**  
It specifies match/routing conditions; rewriting is an extra controller feature.

**11. Why does the trailing slash on `proxy_pass` matter in the Nginx examples?**  
In the location prefix examples above, the `/` URI causes Nginx to replace the location prefix; omitting the URI preserves the original upstream path.

**12. Why is a GET 200 not enough to verify reverse proxy configuration?**  
`Location`/redirects/`self`/cookies/OAuth callbacks may still emit the wrong public host, scheme, or path.

**13. Can `MockMvc` verify real ingress rewrites?**  
No. You need HTTP integration and public topology tests.

**14. When Actuator runs on a separate `management.port`, are endpoint paths automatically under the main Servlet context path?**  
No; they follow the management server base path.

**15. Why can session Cookie `Path` break logins when the public prefix differs from the internal context?**  
Browsers only send cookies on matching paths; `Path=/internal` does not match `/shop`.

**16. Which context base path does WebFlux use?**  
`spring.webflux.base-path` and reactive-stack forwarded handling; it does not use a Servlet context path like MVC.

**17. What scenario does `server.tomcat.redirect-context-root=false` solve?**  
Allows `X-Forwarded-Proto` to be evaluated before Tomcat redirects the context root when TLS terminates at a proxy.

**18. How do you test for host-header poisoning risk?**  
Send a forged `X-Forwarded-Host` through the public edge and confirm responses still emit the canonical host.

**19. Does `X-Forwarded-Prefix` fix an upstream URI that was rewritten incorrectly?**  
No. Proxy routing and Servlet mappings must match independently of URL generation metadata.

**20. What must you verify after switching Ingress controllers?**  
Path rewrites, forwarded headers, TLS scheme, public `Location`/redirects/links, and security trust boundaries.

## 25. Official References

- **Spring Boot 3.3 – Embedded Web Servers / Running Behind a Front-end Proxy Server:** https://docs.spring.io/spring-boot/3.3/how-to/webserver.html — `forward-headers-strategy`, `native`/`framework`, Tomcat `redirect-context-root`.
- **Spring Boot 3.3 – Common Application Properties:** https://docs.spring.io/spring-boot/3.3/appendix/application-properties/ — `context-path`, forwarded headers, session cookie path, management base-path.
- **Spring Framework – MVC Forwarded Headers:** https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html — `X-Forwarded-Prefix` scenarios, `ForwardedHeaderFilter`, and trust boundary.
- **Spring Framework – ServletUriComponentsBuilder Javadoc:** https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/support/ServletUriComponentsBuilder.html — `fromCurrentContextPath` and URI building.
- **Spring Boot 3.3 – Test Spring Boot Applications:** https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html — MockMvc, `@WebMvcTest`, `@SpringBootTest(RANDOM_PORT)`, `@LocalServerPort`.
- **Spring Boot 3.3 – Actuator Endpoints:** https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html — web base path/health/readiness, exposure.
- **Kubernetes Ingress:** https://kubernetes.io/docs/concepts/services-networking/ingress/ — `pathType`/host/service routing.
- **ingress-nginx rewrite example:** https://github.com/kubernetes/ingress-nginx/blob/main/docs/examples/rewrite/README.md — `use-regex`/`rewrite-target`/capture groups, controller-specific.
- **NGINX ngx_http_proxy_module:** https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass — trailing URI/replacement behavior.
- **RFC 7239 Forwarded HTTP Extension:** https://www.rfc-editor.org/rfc/rfc7239 — standard `Forwarded` header.
- **RFC 9110 HTTP Semantics:** https://www.rfc-editor.org/rfc/rfc9110.html — `Location`, redirects, host/authority.