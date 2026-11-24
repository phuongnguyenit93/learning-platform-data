# Forwarded, X-Forwarded-*, and server.forward-headers-strategy in Spring Boot

**Context:** Spring Boot → web-runtime → Proxy and CORS. This lesson presents RFC 7239 `Forwarded`, the `X-Forwarded-*` headers, and the `server.forward-headers-strategy` property for reconstructing original requests behind a reverse proxy; it also distinguishes MVC from WebFlux, analyzes scheme/host/port/prefix mismatches, redirects, CORS, cookies, client IP, and security risks.

**Example environment:** Java 17+, Maven, Spring Boot **3.5.16**, Spring MVC/embedded Tomcat. Spring Boot 3.5.16 is the final OSS release of the 3.5 line (June 2026). Use this example to understand the mechanism; for production, upgrade to a maintained branch/patch such as Spring Boot 4.x suited to your platform or use commercial support. Do not leave a framework version whose OSS support has ended outside your security update policy.

## 1. The problem: HTTPS at the proxy, HTTP at the backend

A browser requests:

~~~http
GET /shop/orders HTTP/1.1
Host: app.example.test
~~~

The visible URL is `https://app.example.test/shop/orders`. The reverse proxy (Nginx, load balancer, ingress) terminates TLS on port 443 and then calls the Spring Boot backend at `http://10.0.0.20:8080/orders`. The proxy has changed three things: **scheme**, **host/port**, and possibly the **path prefix**.

~~~text
Client Browser                  Trusted Reverse Proxy                 Spring Boot
https://app.example.test:443    203.0.113.10:443                      10.0.0.20:8080
GET /shop/orders                        │                              GET /orders
       │                                │                                    │
       ├────── TLS/HTTPS ──────────────►│                                    │
       │                                │ strip external fake headers         │
       │                                │ set verified metadata              │
       │                                ├──── HTTP internal ─────────────────►│
       │                                │                                    │
       │                                │                 Servlet connection: │
       │                                │                 scheme=http        │
       │                                │                 host=10.0.0.20     │
       │                                │                 port=8080          │
       │                                │                                    │
       │                                │  with forwarded processing:        │
       │                                │  scheme=https, host=app...,        │
       │                                │  port=443, prefix=/shop            │
       ◄───────── HTTP response ────────┴────────────────────────────────────┘
~~~

Without trustworthy forwarded information, the server may produce:
- `Location: http://10.0.0.20:8080/login` or absolute links pointing to an internal host;
- broken CSS/JS URLs when the proxy strips `/shop`, causing 404s;
- OAuth/OIDC callbacks with the wrong hostname, scheme, or prefix;
- Swagger/OpenAPI `servers`, HATEOAS links, or password-reset emails pointing to the wrong host;
- `request.isSecure()==false` even though the browser connected to the proxy over HTTPS;
- proxy IPs instead of client IPs in logs and rate limiting.

**A critical requirement:** forwarded metadata **does not prove** that a request genuinely came from a browser with the claimed scheme/host. These are just **HTTP headers that a client can send on its own**. The application may only use them when a **trusted edge proxy** has stripped untrusted values, re-established the original request metadata, and locked down direct network access to the backend.

## 2. RFC 7239 `Forwarded`: syntax and meaning

The standard [RFC 7239](https://www.rfc-editor.org/rfc/rfc7239.html) header uses `name=value` pairs separated by `;` within a single hop; multiple hops/proxies are separated by `,`.

~~~http
Forwarded: for=198.51.100.21;proto=https;host=app.example.test
~~~

| Parameter | Meaning | Example |
| --- | --- | --- |
| `for` | Node connecting to the proxy at a hop, usually representing client IP | `for=198.51.100.21` |
| `proto` | Scheme observed by the proxy, e.g., HTTP/HTTPS | `proto=https` |
| `host` | Request host received by the proxy | `host=app.example.test` |
| `by` | Interface or node of the proxy itself, optional | `by=203.0.113.10` |

For a proxy chain:

~~~http
Forwarded: for=198.51.100.21;proto=https;host=app.example.test, for=10.0.0.7;proto=http;by=10.0.0.8
~~~

The first element is usually written by the first proxy, and subsequent ones are appended by downstream proxies. However, that **does not mean** the first element is the truth: if a client injected a fake `Forwarded` header before reaching the edge and the edge only appends without stripping, the chain can start with untrusted data.

IPv6 and values containing `:` or brackets require quoted-strings per RFC syntax:

~~~http
Forwarded: for="[2001:db8::21]:51000";proto=https;host="app.example.test:443"
~~~

You may also encounter `for=unknown` or obfuscated IDs (e.g., `for=_hidden`). Do not parse all cases yourself with `String.split(",")` followed by `split(";")`: quoted strings, escaping, IPv6, multiple headers with the same name, and malformed data easily break naive parsers.

**Warning from the RFC:** Any node along the path, including the client, can modify this information; you must manage trusted proxies and pass data securely between them before trusting the header.

## 3. The `X-Forwarded-*` family: common conventions

Even though RFC 7239 standardized `Forwarded`, many CDNs and ingresses still use legacy headers such as:

~~~http
X-Forwarded-For: 198.51.100.21, 10.0.0.7
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
X-Forwarded-Prefix: /shop
~~~

| Header | Information | Limitations |
| --- | --- | --- |
| **`X-Forwarded-For`** | IPs/nodes at each hop, usually comma-separated | First element can be forged if edge does not reset; requires a trusted proxy policy |
| **`X-Forwarded-Proto`** | Client-facing scheme: `https` or `http` | Does not tell whether the backend hop uses TLS |
| **`X-Forwarded-Host`** | Public host when the proxy received the request | Can be forged to generate malicious URLs |
| **`X-Forwarded-Port`** | Public port, e.g., 443/8443 | Not the servlet socket port |
| **`X-Forwarded-Prefix`** | Public URL prefix such as `/shop` | Rewrite/replace behavior depends on proxy, web stack, and framework |
| `X-Forwarded-Ssl` | Legacy convention, usually `on` or `off` | Prefer explicit `X-Forwarded-Proto` |
| `X-Real-IP` | Custom header from some proxies | Not treated as XFF by default in every framework |

`X-Forwarded-*` is a de-facto group; **there is no single standard** forcing Nginx, AWS ALB, Envoy, Traefik, and other ingresses to behave identically. Check your infrastructure documentation before choosing Spring properties.

### 3.1. Multiple proxies and `X-Forwarded-For`

~~~text
Client 198.51.100.21
         │
         ▼
Proxy A 10.0.0.7
         │
         ▼
Proxy B 10.0.0.8
         │
         ▼
Spring Boot 10.0.0.20

A chain produced by trusted proxies may look like:
X-Forwarded-For: 198.51.100.21, 10.0.0.7
Nearest socket peer at the backend: 10.0.0.8
~~~

If the client sent `X-Forwarded-For: 1.2.3.4` before Proxy A, unchecked appending can produce `1.2.3.4, 198.51.100.21, 10.0.0.7`. **Do not take `split(",")[0]` as a trusted IP for authorization or rate limiting.** The IP must be interpreted along the chain and CIDRs of genuinely trusted proxies, starting from the known network peer.

### 3.2. Both header families conflicting

~~~http
Forwarded: proto=http;host=evil.example.test
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
~~~

If a system carries both families with different values, Spring may prioritize one family depending on version/configuration and derive the wrong origin. **The proxy at the Internet boundary must strip both `Forwarded` and `X-Forwarded-*` supplied by the client**, and then emit a single consistent contract to the backend. With newer Spring Framework versions that offer APIs to choose a specific header family, configure it to match the proxy contract exactly; never skip input sanitization at the edge.

## 4. `server.forward-headers-strategy`: NONE, NATIVE, FRAMEWORK

Spring Boot uses the property:

~~~properties
server.forward-headers-strategy=framework
~~~

The three values of the `ServerProperties.ForwardHeadersStrategy` enum:

| Value | Handled by | Best suited for | Important limitation |
| --- | --- | --- | --- |
| **`NONE`** | Boot does **not** process forwarded metadata via built-in support | No proxy, or custom request normalization | App may see backend scheme/host; does **not** strip headers at the edge |
| **`NATIVE`** | Embedded server, e.g., Tomcat `RemoteIpValve` | Proxy mainly sends `X-Forwarded-For`/`X-Forwarded-Proto`, container has proper trusted proxies | `Forwarded`/Prefix/Host/Port behavior depends on server and config |
| **`FRAMEWORK`** | Spring MVC `ForwardedHeaderFilter` or WebFlux `ForwardedHeaderTransformer` | Need to reconstruct external scheme/host/port and prefix via Spring APIs | Does **not authenticate** whether headers came from a proxy or an attacker |

In `application.properties`, you can write `none`, `native`, `framework` (Boot relaxed binding); the Java enum uses uppercase.

**The default is not always the same:** Spring Boot 3.5 defaults to **`NATIVE` on supported Cloud Platforms** detected by Boot, whereas other environments typically default to **`NONE`**. Do not assume the environment just because the app runs in a container or Kubernetes. To make auditing easy, set the value **explicitly in deployment profiles** and verify with real requests.

Do not use the legacy `server.use-forward-headers=true` property from pre-Boot 2.2 tutorials instead of the current property. Do not confuse `server.forward-headers-strategy` with `server.servlet.context-path`, `spring.webflux.base-path`, or CORS policy.

### 4.1. NONE

~~~properties
server.forward-headers-strategy=none
~~~

With a lab app listening on `http://localhost:8080` and no custom filter, `request.getScheme()` is normally `http`, `getServerName()` is `localhost`, and `getServerPort()` is 8080.

`NONE` only means that **Boot does not enable its built-in mechanism** via this property. Other libraries or custom-registered filters can still read the headers. Do not interpret using `NONE` as permission for a public proxy to pass self-declared client headers through harmlessly.

### 4.2. NATIVE with Tomcat

~~~properties
server.forward-headers-strategy=native
server.tomcat.remoteip.remote-ip-header=x-forwarded-for
server.tomcat.remoteip.protocol-header=x-forwarded-proto

# Useful when Tomcat is behind a TLS-terminating proxy and redirects the context root:
server.tomcat.redirect-context-root=false
~~~

Embedded Tomcat supports `RemoteIpValve` to adjust certain request attributes from headers and **trusted proxy ranges**. `server.tomcat.remoteip.internal-proxies` is a regex for proxy addresses trusted by Tomcat's logic. Set it to match your real network; never leave it empty to "trust all" in production. A backend reachable directly from the Internet that trusts every proxy risks IP/host spoofing.

Spring Boot advises `server.tomcat.redirect-context-root=false` so `X-Forwarded-Proto` is processed before context-root redirects, avoiding HTTP redirects with the wrong scheme.

**Do not equate `NATIVE` with `FRAMEWORK`:** support for `X-Forwarded-Prefix` or RFC `Forwarded`, as well as normalization order and client-IP behavior, varies across Tomcat/Jetty/Netty/Undertow. Native does not mean "every X-Forwarded header is supported."

### 4.3. FRAMEWORK with MVC and WebFlux

~~~properties
server.forward-headers-strategy=framework
~~~

- **Spring MVC/Servlet:** Spring Boot integrates `org.springframework.web.filter.ForwardedHeaderFilter`, wrapping the request/response so `getScheme()`, `getServerName()`, `getServerPort()`, `isSecure()`, URL builders, and `sendRedirect()` reflect the original metadata. The filter also strips forwarded headers from the request before downstream layers see it.
- **Spring WebFlux/Reactive:** uses `org.springframework.web.server.adapter.ForwardedHeaderTransformer` to transform `ServerHttpRequest` prior to handler resolution, then removes forwarded headers from the transformed request.

**Do not manually add a `@Bean ForwardedHeaderFilter` if `FRAMEWORK` already enables it**, unless you intentionally manage registration/filter ordering yourself and know how to avoid double processing. Mixing a container native valve with a framework filter without control can lead to inconsistent host/scheme/prefix values.

### 4.4. Visible comparison

Suppose the backend socket receives:

~~~http
GET /inspect HTTP/1.1
Host: localhost:8080
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
~~~

Without header processing, the perceived URL can be `http://localhost:8080/inspect`. When metadata **from a trusted proxy** is processed properly, the external request values are typically:

| Attribute | Without processing | Properly processed |
| --- | --- | --- |
| Scheme | `http` | `https` |
| Server name | `localhost` | `app.example.test` |
| Server port | `8080` | `443` |
| `isSecure()` | `false` | `true` |
| Absolute URL | `http://localhost:8080/inspect` | `https://app.example.test/inspect` |

This is the expected result of **a system with a trusted proxy contract**, not proof that forged headers sent from any machine are valid.

## 5. Runnable example: verifying scheme/host/port and redirects with Spring MVC

Create a Maven project in the `forwarded-demo` directory using **two Java classes**, with no database needed. Run it on localhost **for learning purposes only**; do not expose the app port to the Internet when `FRAMEWORK` trusts incoming headers.

~~~text
forwarded-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/forwarded/
    │   ├── ForwardedDemoApplication.java
    │   └── InspectController.java
    └── resources/application.properties
~~~

### 5.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>forwarded-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
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

### 5.2. `src/main/resources/application.properties`

~~~properties
server.port=8080

# For localhost lab only. Do not allow Internet clients to reach the app directly.
server.forward-headers-strategy=framework
~~~

### 5.3. `src/main/java/com/example/forwarded/ForwardedDemoApplication.java`

~~~java
package com.example.forwarded;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ForwardedDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ForwardedDemoApplication.class, args);
    }
}
~~~

### 5.4. `src/main/java/com/example/forwarded/InspectController.java`

~~~java
package com.example.forwarded;

import jakarta.servlet.http.HttpServletRequest;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@Controller
public class InspectController {

    @GetMapping("/inspect")
    @ResponseBody
    public Map<String, Object> inspect(HttpServletRequest request) {
        Map<String, Object> values = new LinkedHashMap<>();
        values.put("scheme", request.getScheme());
        values.put("secure", request.isSecure());
        values.put("serverName", request.getServerName());
        values.put("serverPort", request.getServerPort());
        values.put("contextPath", request.getContextPath());
        values.put("url", ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/inspect")
                .toUriString());
        return values;
    }

    @GetMapping("/go")
    public String go() {
        return "redirect:/inspect";
    }
}
~~~

`@Controller` with `@ResponseBody` only on `/inspect` produces JSON. `/go` returns a **logical redirect view**, not JSON. If you replace `@Controller` with `@RestController`, the string `"redirect:/inspect"` is usually written literally as the response body, **not as a redirect**. The `mvn` commands below resolve dependencies and compile; you cannot run `javac InspectController.java` alone without the Spring/Servlet classpath.

### 5.5. Run and observe the response

From the project root:

~~~bash
java -version
mvn spring-boot:run
~~~

Call directly (without forwarded headers):

~~~bash
curl -sS http://localhost:8080/inspect
~~~

Key fields of the typical JSON:

~~~json
{
  "scheme": "http",
  "secure": false,
  "serverName": "localhost",
  "serverPort": 8080,
  "contextPath": "",
  "url": "http://localhost:8080/inspect"
}
~~~

Simulate a reverse proxy sending **RFC 7239 `Forwarded`**:

~~~bash
curl -sS \
  -H 'Forwarded: for=198.51.100.21;proto=https;host=app.example.test' \
  http://localhost:8080/inspect
~~~

With the default `FRAMEWORK` filter in the sample stack, the result should show:

~~~json
{
  "scheme": "https",
  "secure": true,
  "serverName": "app.example.test",
  "serverPort": 443,
  "contextPath": "",
  "url": "https://app.example.test/inspect"
}
~~~

Simulate a proxy using **`X-Forwarded-*`**:

~~~bash
curl -sS \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: app.example.test' \
  -H 'X-Forwarded-Port: 443' \
  http://localhost:8080/inspect
~~~

Check the redirect:

~~~bash
curl -i \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: app.example.test' \
  -H 'X-Forwarded-Port: 443' \
  http://localhost:8080/go
~~~

`/go` should return **302 Found**; observe `Location` pointing to the external URL `https://app.example.test/inspect` or an equivalent valid redirect generated by the actual stack/container. The domain `app.example.test` is only a **sample name with no public DNS**; do not run `curl -L` against it and mistake a DNS error for a Spring bug.

**Security note:** Here `curl` itself sends the raw headers so you can see the filter work. In production, if clients can also do that directly to the app, that is a trust-boundary vulnerability; accept metadata only from a **sanitized proxy**.

### 5.6. Try the three strategies

In `application.properties`, change just one value, restart the app, and send the commands above:

~~~properties
server.forward-headers-strategy=none
~~~

Expect the app to still see the backend origin; Boot does not reconstruct scheme/host on its own.

~~~properties
server.forward-headers-strategy=native
~~~

On Tomcat, a subset of X-Forwarded headers may be supported via `RemoteIpValve` and trusted-peer rules. **Do not use localhost results to conclude a public environment is safe**, because loopback is often treated as an internal/trusted proxy.

~~~properties
server.forward-headers-strategy=framework
~~~

The Spring filter processes forwarded metadata. If complex prefixes/redirects are needed, verify empirically. Do not let both native and framework mechanisms run on the same request without clearly knowing the order, to avoid double rewriting.

## 6. `X-Forwarded-Prefix` and URL rewriting

Suppose the public route is `https://app.example.test/shop/inspect`, yet the proxy **strips** `/shop` before forwarding to `http://localhost:8080/inspect`. When generating external links, the backend needs to know the public prefix; the proxy can set:

~~~http
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
X-Forwarded-Prefix: /shop
~~~

Spring Framework has support for `X-Forwarded-Prefix` so URL builders and some redirects reflect the external prefix, depending on the framework version/stack. With the `FRAMEWORK` example, try:

~~~bash
curl -sS \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: app.example.test' \
  -H 'X-Forwarded-Port: 443' \
  -H 'X-Forwarded-Prefix: /shop' \
  http://localhost:8080/inspect
~~~

Expect the external URL to be reconstructed as `https://app.example.test/shop/inspect` when the filter behavior and prefix contract align. If `/shop` is missing or doubled, check the **actual backend request path**, servlet context path, reverse proxy rewrite, `ForwardedHeaderFilter`/`ForwardedHeaderTransformer`, and version. Do not fix it by hardcoding `"/shop"` string concatenation in every controller.

### 6.1. Three prefix variants

According to Spring Framework documentation, a prefix can:
1. **Override:** the client calls `/api/{path}`, the backend runs at `/app1/{path}`, and `X-Forwarded-Prefix: /api` replaces `/app1` when building public URLs.
2. **Remove:** the client calls `/{path}`, the backend internally sits at `/app1/{path}`; the proxy sends an empty prefix so the client does not see `/app1`.
3. **Prepend:** the client calls `/api/app1/{path}`, the backend sits at `/app1/{path}`; the public prefix becomes `/api/app1`.

This is **not simple string concatenation**. The contract depends on proxy rewrites and server context paths. For example, `server.servlet.context-path=/shop` creates a real internal Servlet context path; `X-Forwarded-Prefix: /shop` describes the public URL and **does not mean** both should be enabled. WebFlux has its own `spring.webflux.base-path`.

## 7. Nginx at the edge: strip forged headers, emit fresh metadata

This is an example of Nginx **facing the Internet directly**, terminating TLS, and proxying to Spring Boot **bound only to loopback**. The cert/key paths are examples with no secrets. When Nginx sits behind another CDN/load balancer, a different trusted-hop design is needed as in section 7.2.

~~~nginx
server {
    listen 443 ssl;
    server_name app.example.test;

    ssl_certificate     /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;

        # Serve only the chosen public host, do not reflect arbitrary Host headers.
        proxy_set_header Host app.example.test;

        # Strip client-supplied forwarded metadata.
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Ssl "";
        proxy_set_header X-Forwarded-Prefix "";

        # Overwrite with metadata observed by the edge.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host app.example.test;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
~~~

Conditions:
- Backend port 8080 **must not be public**. Bind to loopback or restrict via firewall/security group/NetworkPolicy so only trusted proxies connect.
- Nginx must have a vhost/default-server handling invalid `Host` values (never forward unknown names to the app). A single `server_name` does not replace a full default-vhost policy.
- The `proxy_set_header` directives above **overwrite** client-supplied X-Forwarded headers. `proxy_set_header Forwarded "";` clears the standard family so it cannot conflict with the trusted `X-*` family.
- When the proxy terminates TLS, the HTTP backend does not automatically have TLS; if the internal hop crosses an untrusted network, use internal TLS/mTLS per policy.
- If a public prefix is needed, configure `location`/`proxy_pass` path rewriting consistently and set `X-Forwarded-Prefix` appropriately. A trailing `/` in `proxy_pass` changes how Nginx builds the upstream URI, so test actual paths, assets, and redirects.
- The domain `app.example.test` is for documentation only. Replace it with your actual deployment hostname, certificate, and DNS.

### 7.1. `$remote_addr` vs `$proxy_add_x_forwarded_for`

Nginx's `$proxy_add_x_forwarded_for` takes the **incoming `X-Forwarded-For` header** and **appends `$remote_addr`**. If a malicious client sent `X-Forwarded-For: 1.2.3.4`, the proxy could pass along:

~~~http
X-Forwarded-For: 1.2.3.4, 198.51.100.21
~~~

If the backend uses the first item as a trusted IP, an attacker can pick any IP. At an edge **with no trusted proxy in front of it**, use `X-Forwarded-For $remote_addr` to overwrite explicitly. Only in a chain standardized from the edge may internal proxies append according to the design.

### 7.2. Nginx behind a CDN/load balancer

When a CDN/LB sits in front of Nginx, `$remote_addr` can be the **CDN's IP**, not the browser's IP. Nginx's realip module supports `set_real_ip_from` and `real_ip_header` for specific trusted CIDRs. Configure only the official CDN/LB CIDRs and verify the exact hop; never use `set_real_ip_from 0.0.0.0/0` to trust the entire Internet.

Infrastructure may use PROXY protocol, mTLS connections between hops, or a dedicated CDN-provided header. Never pick a header without verification. Once the real IP is resolved, the backend may receive a normalized client IP, but **an IP is not a user identity** and does not replace authentication/authorization.

## 8. WebFlux: `ForwardedHeaderTransformer`

In Spring WebFlux, requests flow through `DispatcherHandler` and reactive APIs rather than the Servlet `DispatcherServlet`. With `FRAMEWORK`, the main component is `ForwardedHeaderTransformer`.

| Aspect | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Web starter | `spring-boot-starter-web` | `spring-boot-starter-webflux` |
| Dispatcher | `DispatcherServlet` | `DispatcherHandler` |
| FRAMEWORK handling | `ForwardedHeaderFilter` | `ForwardedHeaderTransformer` |
| Request | `HttpServletRequest` | `ServerHttpRequest` |
| URL origin | Servlet API/`ServletUriComponentsBuilder` | `ServerHttpRequest.getURI()` and reactive URI builders |
| Common property | `server.forward-headers-strategy=framework` | `server.forward-headers-strategy=framework` |

The code below is **illustrative only**, not standalone (requires a Spring WebFlux project with imports and application context):

~~~java
@GetMapping("/reactive/inspect")
Mono<Map<String, String>> inspect(ServerHttpRequest request) {
    URI uri = request.getURI();
    return Mono.just(Map.of(
        "scheme", uri.getScheme(),
        "host", uri.getHost(),
        "path", uri.getPath()
    ));
}
~~~

When both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Boot normally prefers the MVC/Servlet application type; do not assume an app is WebFlux merely because it uses `WebClient`, `Mono`, or reactive dependencies.

### 8.1. `removeOnly` and choosing a header family

`ForwardedHeaderFilter`/`ForwardedHeaderTransformer` supports **removeOnly**, to **strip headers** without using them to adjust scheme/host/port. This is a filter/transformer-specific behavior, **different from** Boot's `server.forward-headers-strategy=none`. If you only need to sanitize headers inside the app, register the appropriate bean/filter with `removeOnly=true` and control registration/ordering; do not add it to an app already using Boot's auto-configured filter without assessing double processing.

In Framework versions offering constructors that select standard `Forwarded` or `X-Forwarded-*` specifically, configure the family matching your trusted proxy contract. Several security improvements were introduced in patch versions of Spring Framework 6.2.x and 7.1; always verify the exact API and apply the latest patches.

### 8.2. Processing order

The MVC filter wraps the request/response, so it must be registered **before** other filters that need to know the scheme/host, including when redirects happen early. When registering a filter manually, pay attention to `REQUEST`, `ASYNC`, and `ERROR` dispatch types; rely on Boot auto-configuration before writing manual registrations. The WebFlux transformer runs during reactive request transformation, not as a Servlet filter.

## 9. Redirects, canonical URLs, and security consequences

**Redirect `Location`**, URLs in emails/reset tokens, OAuth callbacks, HATEOAS links, and OpenAPI docs can be built from the current request. When Spring trusts a host from a forged forwarded header, an attacker can redirect links to a domain they control—a form of **host header poisoning** that can lead to open redirects or token leaks.

For sensitive URLs:
- prefer configuring a **canonical public base URL** in application config and a hostname allowlist instead of blindly reading request `Host`;
- have the proxy accept only valid public hostnames and strip/override client-supplied forwarded headers;
- verify OAuth/OIDC redirect URIs match the registered callback list;
- never generate password-reset URLs containing secrets/tokens from an unverified request host;
- inspect `Location` on actual responses passing through the proxy, not just internal app responses.

`server.forward-headers-strategy=framework` can make redirects point to **the right external address**, but **it does not create a trust boundary on its own**. A browser sending HTTPS to a proxy whose backend receives HTTP may still need `Secure` cookies, HSTS, and a correct forwarded scheme. However, `X-Forwarded-Proto=https` **does not encrypt the proxy→backend hop**.

Example Servlet session cookie policy (depends on design):

~~~properties
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
~~~

`SameSite`, HSTS, reverse proxy policy, and other application cookies must be reviewed separately. Do not fix mixed content with CORS: if HTTPS HTML references an `http://...` resource, fix URL/scheme generation rather than loosening Cross-Origin policy.

## 10. How do CORS and forwarded headers relate?

A browser **origin** consists of `scheme://host:port`; differing in any part can make a request **cross-origin**.

~~~text
https://app.example.test      is origin A
http://app.example.test       differs from A by scheme
https://api.example.test      differs from A by hostname
https://app.example.test:8443 differs from A by port
~~~

`Origin` sent by the browser (in a CORS flow) is **not** `Forwarded`, `X-Forwarded-Host`, or `X-Forwarded-Proto`. Enabling a forwarded-headers strategy in Spring Boot **does not enable CORS**, nor does it automatically return `Access-Control-Allow-Origin`.

- If the frontend and API share the same public origin via a proxy, the browser may not need CORS even though the backend uses an HTTP socket.
- If truly cross-origin, you must configure allowed origins, methods, headers, credentials, and handle `OPTIONS` preflight in Web MVC/WebFlux/Spring Security/ingress.
- When using credentialed CORS, never reflect an arbitrary `Origin` and never use wildcard `*` as a quick fix.
- CORS errors can be masked by HTTP→HTTPS redirects, 401/403 on `OPTIONS`, cookie/SameSite failures, caching, or proxies; inspect the browser Network tab.

An illustrative MVC snippet (not part of the lab project in section 5):

~~~java
@Configuration
class PublicWebCorsConfig implements WebMvcConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization");
    }
}
~~~

This snippet needs imports and an appropriate `SecurityFilterChain` if the app uses Spring Security. **CORS is not authorization** and does not prevent non-browser clients from calling the API.

## 11. Client IP, rate limiting, and access logs

Distinguish between the **socket peer IP**, the **IP reported by the proxy as client**, and the **IP verified by the system under a trusted proxy policy**. Some native implementations such as Tomcat `RemoteIpValve` can adjust `getRemoteAddr()`. However, do not assume every `FRAMEWORK` implementation modifies the servlet remote address identically: `ForwardedHeaderFilter` primarily affects scheme/host/port and redirects.

**Do not use** this snippet for IP allowlisting:

~~~java
// ANTI-PATTERN: NOT safe at an edge that does not sanitize XFF.
String ip = request.getHeader("X-Forwarded-For").split(",")[0];
if (ip.equals("10.0.0.99")) {
    // grant privilege...
}
~~~

It can trust an IP supplied by the client itself. Instead, configure trusted proxy/IP ranges in the ingress/gateway/container, use the observed peer where appropriate, and apply identity-based authorization (session/JWT/mTLS) for critical access decisions.

For logging:
- log `observedPeerIp` and `verifiedClientIp` separately rather than lumping both into an ambiguous `clientIP` field;
- escape/sanitize values from HTTP headers; bound their length and retention;
- consider privacy, internal addresses leaking topology, and the fact that an IP is not always a single user;
- detect when many requests share one peer IP due to misconfigured proxy trust.

## 12. Threat model: attacks from misconfigured forwarding trust

| Risk | Condition | Consequence | Mitigation |
| --- | --- | --- | --- |
| Host-header poisoning | Server trusts client-supplied `X-Forwarded-Host` | Password-reset links/redirects to attacker domain | Edge override, canonical base URL, host allowlist |
| Fake IP / rate-limit bypass | Code trusts first XFF element | Bypass limits/IP ACLs, falsified logs | Trusted proxy chain, edge reset, verified client IP |
| Scheme spoofing | Trusts `X-Forwarded-Proto=https` from untrusted client | Wrong `isSecure`, redirect/cookie logic | Keep backend private, enforce trust boundary |
| Prefix spoofing | Accepts unsanitized `X-Forwarded-Prefix` | Abnormal URLs/redirects, poisoned cache keys | Fixed prefix from proxy, integration tests |
| Header precedence confusion | `Forwarded` and `X-*` conflict | Wrong origin, version-dependent behavior | Reset both and emit a single family |
| Direct backend bypass | Port 8080 open to Internet | Bypass proxy rate-limits/auth and inject headers | NetworkPolicy/firewall, private listeners |
| Trust-all proxies | Native container trusts every IP | Any client becomes a "trusted proxy" | Minimal internal proxy CIDRs/regex |
| OAuth callback mismatch | Proxy URL and app URL differ | Login loops, token/redirect errors | Verify scheme/host/port/prefix and registered URI |
| Overly broad CORS | Reflect arbitrary `Origin` | Cross-origin browsers read data under wrong policy | Explicit `allowedOrigins` and credentials rules |

Keep Boot, Framework, Tomcat/Netty, Nginx/ingress, Spring Security, and related components patched. Forwarded-header normalization is **one layer** in security design; it does not replace TLS, authN/authZ, CSRF, CORS, or network segmentation.

## 13. Debugging in proxy environments

### 13.1. Symptom table

| Symptom | Common cause | Action |
| --- | --- | --- |
| `Location: http://localhost:8080/...` | Scheme/host metadata not conveyed to app | Check headers at final hop and forward strategy |
| `request.isSecure()==false` despite browser HTTPS | TLS terminated at proxy, Boot not restoring scheme | Set/verify trusted `Proto`, right `FRAMEWORK`/`NATIVE` for stack |
| CSS/JS 404 when app is under `/shop` | Wrong prefix rewrite or generated URLs | Check `X-Forwarded-Prefix`, context path, static URLs |
| HTTP↔HTTPS redirect loop | Proxy and app redirect based on differing schemes | Trace `Location` across every hop |
| `/shop/shop/login` | Prefix added twice | Check `proxy_pass` rewrite, `contextPath`, forwarded prefix |
| OAuth `redirect_uri_mismatch` | Callback built from internal scheme/host/port | Check external absolute URL and allowed redirect URIs |
| `getRemoteAddr()` = proxy IP | Native client-IP policy not applied or only scheme fixed | Verify peer, `RemoteIpValve`, trusted CIDRs |
| User can change IP in logs via XFF | Incoming header not stripped | Edge overwrite + block direct backend access |
| No CORS despite `FRAMEWORK` enabled | CORS is an independent policy | Check `Origin`, `OPTIONS`, Spring Security CORS |
| `NATIVE` handles Proto but not Prefix | Native containers differ in scope | Use/test `FRAMEWORK` for prefix |
| App receives conflicting `Forwarded` and `X-*` | Multiple proxies set inconsistent headers | Standardize on one header family, strip others |
| OpenAPI server URL points to localhost | Origin derived from internal backend | Proper forwarded metadata or canonical server URL |
| HTTPS works but cookies sent incorrectly | Wrong `Secure`/`SameSite`/`Domain`/`Path` | Inspect `Set-Cookie` and browser behavior |
| Redirect points to unknown host | Host/forwarded injection or wrong vhost | Allowlist hosts, sanitize at edge, audit |

### 13.2. Quick debugging sequence

1. Draw the hop chain: browser → CDN → LB → ingress → app; mark protocol, host/port, and prefix at each hop.
2. Observe the **public** browser request and response status/`Location`, using the browser Network tab to catch mixed content, CORS, or redirect loops.
3. Find where forwarded headers are **first created**, and check if client-sent values are being appended.
4. Check whether the backend has a public path; lock down the network before trusting forwarded metadata.
5. Confirm whether the Boot app runs **MVC or WebFlux**, which embedded container it uses, and that the forward strategy is set explicitly.
6. For Tomcat `NATIVE`, check `RemoteIpValve`/`internal-proxies`/`protocol-header`/`remote-ip-header`.
7. For `FRAMEWORK`, inspect filter/transformer registration, ordering, header family, and prefix handling on your exact Framework patch.
8. Send a test `curl` directly to the app in staging to understand behavior, then send **the same forged headers** through the proxy to prove the edge strips/overrides them.
9. Check CORS preflight and cookie flags separately if browser-only issues appear.
10. Disable or protect the `/inspect` endpoint before going to production so infrastructure metadata is not exposed.

## 14. Production deployment checklist

- Only trusted proxies can connect to the backend. Internal ports are never exposed to the Internet.
- Edge strips/overrides both untrusted `Forwarded` and `X-Forwarded-*`; only one header policy is explicitly published.
- `server.forward-headers-strategy` has an explicit value per environment; native and framework processing are not accidentally mixed.
- If using `NATIVE`, set exact trusted proxy regex/CIDRs—never trust-all.
- If using a public path prefix, test entry routes, redirects, static assets, links, OpenAPI, and context path.
- Verify generated URLs carry the right scheme/host/port even when TLS terminates ahead of the app.
- For auth callbacks and password resets, use a canonical allowed origin; never trust arbitrary request hosts.
- Verify HTTP cookie `Secure`/`HttpOnly`/`SameSite`, HSTS, mixed content, and TLS across hops.
- Set CORS to real public origins, handling preflight and credentials policy separately.
- Trusted IPs used for security or rate limiting must be the output of a trusted-proxy policy, not a raw XFF string.
- Include regression tests for header spoofing, `Forwarded` vs `X-*` conflicts, multiple hops, redirects/prefixes, direct backend access, and non-allowlisted hosts.
- Keep all proxy and Spring components updated; pay attention to `ForwardedHeaderFilter`/`ForwardedHeaderTransformer` patches on the version in use.

## 15. Self-check questions

1. Why might the server see `http://localhost:8080` when the browser visits `https://app.example.test`?
2. In `Forwarded`, what do `for`, `proto`, `host`, and `by` describe? What do `;` and `,` separate?
3. Does `X-Forwarded-For: 1.2.3.4, 198.51.100.21` prove `1.2.3.4` is the real client?
4. At which processing layer do `NONE`, `NATIVE`, and `FRAMEWORK` differ?
5. MVC uses `ForwardedHeaderFilter`; which class does WebFlux use?
6. Does enabling `server.forward-headers-strategy=framework` automatically make proxy IPs trustworthy?
7. Must `X-Forwarded-Prefix: /shop` and `server.servlet.context-path=/shop` always be configured together?
8. Why does returning `"redirect:/login"` from `@RestController` not produce a 302 like `@Controller`?
9. Does `request.isSecure()==true` from a forwarded header prove the proxy→backend connection uses TLS?
10. Do `X-Forwarded-Host` and `Origin` in CORS share the same semantics?
11. Why shouldn't `$proxy_add_x_forwarded_for` be used indiscriminately at an unsanitized edge?
12. What happens if both `Forwarded` and `X-*` reach the backend with different hosts?
13. Why must password-reset URLs and OAuth callback URLs use controlled hosts?
14. If you add the WebFlux starter to an MVC app, does the server definitely switch to WebFlux by default?
15. If Nginx sits behind a CDN, is `$remote_addr` guaranteed to be the browser IP?
16. Why does `server.forward-headers-strategy=none` not guarantee every library ignores raw headers?
17. How do you verify an edge proxy prevents client-header spoofing?
18. Can forwarded headers be used to automatically enable CORS and allow cross-origin credentials?
19. Why is `server.tomcat.redirect-context-root=false` helpful for Tomcat behind a TLS-terminating proxy?
20. When a browser loads CSS at the wrong path `/shop/shop/css`, which components would you inspect?

**Suggested answers:** (1) TLS termination and proxy rewriting; (2) node/protocol/host/proxy metadata, `;` separates pairs, `,` separates hops; (3) no, the leftmost value can be forged; (4) `NONE` does no processing, `NATIVE` uses the server container, `FRAMEWORK` uses Spring Filter/Transformer; (5) `ForwardedHeaderTransformer`; (6) no, headers must be stripped at the edge and network access restricted; (7) no, it depends on the rewrite model; (8) `@RestController` writes a literal response body; (9) no; (10) no; (11) it can preserve a forged XFF and append to it; (12) ambiguous policy / wrong origin; (13) to prevent host-header poisoning; (14) normally no, Boot selects MVC; (15) it may be the CDN's IP; (16) raw headers remain on the request and other code can read them; (17) send malicious headers in staging through the edge and compare backend metadata; (18) no, CORS is independent; (19) processes forwarded proto before redirects; (20) `proxy_pass`, context path, `X-Forwarded-Prefix`, filter, and links.

## 16. Official documentation

- RFC 7239, **Forwarded HTTP Extension**: https://www.rfc-editor.org/rfc/rfc7239.html
- Spring Boot 3.5, **Running Behind a Front-end Proxy Server**: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 3.5, **ServerProperties.ForwardHeadersStrategy**: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/ServerProperties.ForwardHeadersStrategy.html
- Spring Framework 6.2, **MVC Forwarded Headers and ForwardedHeaderFilter**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html
- Spring Framework 6.2, **WebFlux ForwardedHeaderTransformer**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Nginx, **proxy_set_header and $proxy_add_x_forwarded_for**: https://nginx.org/en/docs/http/ngx_http_proxy_module.html
- Nginx, **ngx_http_realip_module**: https://nginx.org/en/docs/http/ngx_http_realip_module.html
- Spring Boot, **3.5.16 last OSS release announcement**: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/