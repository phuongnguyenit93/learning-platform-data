# Distinguishing forwarded-header processing at the server vs. at Spring Framework

## 1. The real-world problem: the original request is HTTPS, but the app sees HTTP

Suppose a user accesses `https://app.example.test/portal/orders`. A load balancer or reverse proxy terminates TLS and forwards the request to a Spring Boot application running HTTP at `10.0.0.15:8080`. On the direct connection between the proxy and the application, the web server may see:

```text
scheme       = http
serverName   = 10.0.0.15 or backend host
serverPort   = 8080
remoteAddr   = proxy IP address
requestURI   = /orders
```

Yet the URL the user actually sees is:

```text
https://app.example.test/portal/orders
```

If the application builds absolute paths, redirects to login, creates email links, emits a `Location` header, or evaluates whether the request is secure, misunderstanding **scheme, host, port, client IP, and external path prefix** can cause failures:

- `Location: http://10.0.0.15:8080/login` or redirecting to HTTP even though the browser uses HTTPS.
- Links in JSON, HTML, and email notifications using the internal host.
- Redirecting to `/orders` instead of `/portal/orders` when the proxy has stripped the prefix.
- `HttpServletRequest.isSecure()` returning `false` after TLS termination, breaking HTTPS-required logic or URL building.
- Logs and rate limits mistakenly attributing all requests to the same proxy IP.
- If client-supplied headers are trusted, an attacker can spoof the public host/IP and corrupt links or control redirects.

Spring Boot provides the **`server.forward-headers-strategy`** property with three options: `NONE`, `NATIVE`, and `FRAMEWORK`. This lesson explains why **`NATIVE` processes headers at the web server/container layer** while **`FRAMEWORK` processes them using Spring Framework components**, how to choose and verify between them, and how this differs from **CORS**.

Scope: Spring Boot **3.3.x**, Spring Framework 6.1.x, Java 17+; the hands-on example uses Spring Boot 3.3.13, Java 21, and Spring MVC with embedded Tomcat, with a comparison to Spring WebFlux. External HTTP headers are always treated as **untrusted** until they cross a controlled proxy boundary.

## 2. What are forwarded headers and who is responsible for setting them?

A reverse proxy can convey information about the original request through the RFC 7239 standard header or common headers prefixed with `X-Forwarded-`:

| Header | Typical meaning | Example |
| --- | --- | --- |
| `Forwarded` | RFC 7239 standard header with `for`, `proto`, `host` parameters; may span multiple hops | `for=192.0.2.10;proto=https;host=app.example.test` |
| `X-Forwarded-For` | List of addresses across proxies, related to client IP | `192.0.2.10, 10.0.0.5` |
| `X-Forwarded-Proto` | Scheme the client used at a trusted proxy | `https` |
| `X-Forwarded-Host` | Public host forwarded by the proxy | `app.example.test` |
| `X-Forwarded-Port` | Public-facing port | `443` |
| `X-Forwarded-Prefix` | External path prefix added or stripped by the proxy during forwarding | `/portal` |
| `X-Forwarded-Ssl` | Non-standard header some infrastructure uses as a TLS signal | `on` |

The `Forwarded` header and `X-Forwarded-*` family are **metadata sent in HTTP**. Browsers or HTTP clients can forge them when not blocked by an intermediary; Spring cannot tell from a header's value alone whether it came from a proxy or an attacker.

Example request flow:

```text
Browser: https://app.example.test/portal/orders
      |
      | TLS to edge
      v
Trusted edge proxy
      | Strips /portal prefix, forwards HTTP to :8080
      | X-Forwarded-Proto: https
      | X-Forwarded-Host: app.example.test
      | X-Forwarded-Port: 443
      | X-Forwarded-Prefix: /portal
      | X-Forwarded-For: 192.0.2.10
      v
Embedded web server: HTTP /orders
      |
      v
Spring MVC / WebFlux request handling
```

At the edge, the proxy must **strip any `Forwarded` and `X-Forwarded-*` values sent by untrusted clients**, and only set new values derived from a trusted connection and configuration. If there are multiple proxies, all parties must agree on the **trusted chain** and how the hop list is represented. This requires both **network policy** (accepting backend traffic only from trusted proxies) and **header normalization** at the edge.

## 3. The three values of `server.forward-headers-strategy`

Spring Boot 3.3 provides the enum values `NONE`, `NATIVE`, and `FRAMEWORK`:

```properties
# Choose one of the three values:
server.forward-headers-strategy=NONE
# server.forward-headers-strategy=NATIVE
# server.forward-headers-strategy=FRAMEWORK
```

| Strategy | Where it is processed | Primary mechanism | When suitable |
| --- | --- | --- | --- |
| `NONE` | Boot does not enable forwarded-header processing | Server/app sees the backend connection details by default | No proxy used, or do not want to trust forwarded headers |
| `NATIVE` | Embedded server/container | Built-in features of Tomcat, Jetty, Undertow, or Reactor Netty | Proxy sends headers natively supported by the server; usually `X-Forwarded-For` and `X-Forwarded-Proto` |
| `FRAMEWORK` | Spring Framework | Servlet `ForwardedHeaderFilter`; WebFlux `ForwardedHeaderTransformer` | Need Spring-level header handling, especially host/scheme/prefix and URL/redirects when native is insufficient |

**Choose one strategy deliberately.** Avoid enabling native rewriting while also manually registering a `ForwardedHeaderFilter` that re-processes the same headers without understanding their order; this easily produces mismatched results or makes it unclear which layer consumed the headers.

Per Spring Boot 3.3 documentation, on **supported cloud platforms** the default strategy may be `NATIVE`; in other environments, the default is `NONE`. Thus two environments running the same code without declaring the property can behave differently. When configuring production behind a proxy, **set the property explicitly** and verify the effective configuration in the real environment.

A subtle point: `NONE` means **Boot does not automatically process** forwarded headers; it does not mean the raw headers are removed from `HttpServletRequest.getHeader(...)`. If your application or another library reads those headers directly, or an operator configured a manual Valve/filter, check those separately. Never use `getHeader("X-Forwarded-For")` as a trusted IP merely because `NONE` is set.

## 4. `NATIVE` processing: the container understands the request before filters/controllers

When using `NATIVE`, Spring Boot lets the **HTTP server/container** map information from forwarded headers onto the corresponding request APIs. For default Spring MVC using embedded Tomcat, the key component is **Tomcat `RemoteIpValve`**.

Responsibility diagram:

```text
TCP connection from proxy
       |
       v
Tomcat Connector
       |
       v
Tomcat RemoteIpValve (when NATIVE and appropriately configured)
       |  Reads headers per configuration/trust rules
       |  Adjusts perceived remote IP/scheme/secure/host/port
       v
Servlet filter chain (Spring Security, etc.)
       |
       v
DispatcherServlet -> Controller
```

Because it operates in the **container pipeline**, many parts of the application see the adjusted request properties before Spring MVC runs. The exact mechanism depends on Tomcat, Jetty, Undertow, or Reactor Netty; do not call every implementation "RemoteIpValve," as that is specific to **Tomcat**.

Example declaration when the proxy sends `X-Forwarded-For` and `X-Forwarded-Proto`:

```properties
server.forward-headers-strategy=NATIVE
server.tomcat.redirect-context-root=false
```

`server.tomcat.redirect-context-root=false` is especially noteworthy when **Tomcat sits behind a TLS-terminating proxy**: per Spring Boot 3.3 guidance, it allows `X-Forwarded-Proto` to be evaluated before certain context-root redirects occur.

Related Tomcat properties:

```properties
server.tomcat.remoteip.remote-ip-header=x-forwarded-for
server.tomcat.remoteip.protocol-header=x-forwarded-proto

# Must explicitly specify trusted proxies matching your actual topology.
# server.tomcat.remoteip.internal-proxies=...
```

`remote-ip-header`/`protocol-header` are used when customizing the **header names** sent by the proxy. `internal-proxies` controls which internal proxies Tomcat trusts; it uses its own syntax (regex in `RemoteIpValve`) and must not be filled arbitrarily or made into a pattern matching every address. Verify default trust rules and the socket address of the **proxy closest to the application**, including IPv4/IPv6.

Depending on the server implementation, `NATIVE` may not support all headers or handle external prefixes like Spring Framework. **Spring Boot 3.3 explicitly states**: for common `X-Forwarded-For` and `X-Forwarded-Proto`, `NATIVE` is usually sufficient; if not, consider `FRAMEWORK`.

## 5. `FRAMEWORK` processing: Spring wraps or transforms the request

For Spring MVC/Servlet:

```properties
server.forward-headers-strategy=FRAMEWORK
```

Spring Boot uses **Spring Framework `ForwardedHeaderFilter`**. This filter inspects forwarded headers on the request and creates **request/response wrappers** so downstream code sees the scheme/host/port and related attributes from the public client's perspective. It also **strips the relevant forwarded headers from the wrapped request** so downstream layers are not accidentally influenced by ad-hoc raw header reads.

```text
Tomcat HTTP Connector -> Original Servlet request
       |
       v
ForwardedHeaderFilter (Spring Framework)
       |  Reads Forwarded / X-Forwarded-*
       |  Wraps HttpServletRequest / HttpServletResponse
       v
Filters/controllers see wrapped request
       |
       v
Spring MVC HandlerMapping, URL builders, redirects
```

The key point is the **different processing layer**: `FRAMEWORK` does not turn Tomcat into a proxy or add TLS to the HTTP connection; it makes Spring view the request according to metadata confirmed by the proxy. The actual backend socket remains plain HTTP. Therefore, verifying real transport security must rely on TLS configuration at the proxy/backend, not just `request.isSecure()` after rewriting.

`ForwardedHeaderFilter` also participates in redirect handling via the response wrapper, helping some `sendRedirect(...)` calls or request-based URL generation reflect the public host/scheme. With `X-Forwarded-Prefix`, the Framework can support applications hosted under an external path prefix stripped by the proxy. **Do not assume every prefix/rewrite variant behaves identically**: it still depends on how the proxy formats the prefix, the framework version, servlet context path, and redirect type.

In Spring WebFlux, the counterpart is **`ForwardedHeaderTransformer`**, which transforms `ServerHttpRequest` before reactive request handling. Do not register the Servlet `ForwardedHeaderFilter` and expect it to apply to Reactor Netty/WebFlux.

## 6. Detailed comparison between NATIVE and FRAMEWORK

| Criterion | `NATIVE` | `FRAMEWORK` |
| --- | --- | --- |
| Who reads headers? | Actual server/container | Spring Framework |
| With Servlet Tomcat | Usually `RemoteIpValve` | `ForwardedHeaderFilter` |
| With WebFlux | Server adapter / matching native support | `ForwardedHeaderTransformer` |
| When applied | In the web server pipeline, before the servlet filter chain | In Spring's filter/request-adapter |
| Adjusting scheme/secure/host/port | Per server support + configuration | Per Spring's `Forwarded`/`X-Forwarded` handling |
| Handling `X-Forwarded-For` | Tomcat Valve has remote IP and trusted proxy chain logic | Has framework-specific logic; not automatically identical to every native remote IP value |
| `X-Forwarded-Prefix` | Full support not guaranteed across all containers | Usually better suited for prefixes used by Spring URL builders |
| Early container-generated redirects | May need container-specific configuration | Filter cannot fix redirects sent **before the filter runs** |
| `HttpServletRequest` | May already be adjusted at the container level | Wrapper provides the request view to downstream |
| Trusted proxy control | Container-dependent (e.g., Tomcat internal/trusted proxy rules) | Framework **cannot tell on its own** whether forwarded headers came from a trusted proxy |
| CORS | Does not grant cross-origin access | Does not grant cross-origin access |
| Recommendation | Use when native suffices for your topology and trust config is right | Use when Spring wrapper/prefix features are needed and the edge sanitizes headers |

**Neither option automatically makes an untrusted proxy network safe.** If an attacker can call the backend directly with `X-Forwarded-Host: evil.example`, accepting that header can lead to malicious URLs or host-header injection.

`FRAMEWORK` also offers **`removeOnly` mode** on the `ForwardedHeaderFilter` API for manual configuration: it only removes headers **without using them**. This is a specific option when you want to discard untrusted metadata; it is not the same as `server.forward-headers-strategy=NONE`, because `NONE` does not strip raw headers. If Boot already auto-registers the filter under `FRAMEWORK`, do not arbitrarily add a second filter.

## 7. Proxy configuration: the most important part is the trust boundary

A secure setup requires a **trust boundary at the edge**:

1. Only authorized proxies/load balancers can reach the backend; use firewalls, security groups, Kubernetes NetworkPolicy, or internal mTLS per infrastructure.
2. The edge **strips** `Forwarded` and `X-Forwarded-*` headers from untrusted clients, including the RFC 7239 standard form.
3. The edge emits **one consistent header convention** from the verified connection: host, proto, port, IP, and prefix if needed.
4. If there are multiple proxy hops, clearly define which proxies append/overwrite the `for` list and which IPs count as trusted clients.
5. Spring Boot is configured with `NATIVE` or `FRAMEWORK` matching actual edge output, and the application does not manually parse raw headers elsewhere.

**Illustrative NGINX example** where NGINX itself is the **sole edge**, with public virtual host `app.example.test`, HTTPS termination at NGINX, and Spring Boot listening on localhost port 8080. This is only a `location` block, **not a complete TLS configuration** (it requires `server`, `listen 443 ssl`, certificates, and separate proxy/firewall controls):

```nginx
location /portal/ {
    # Trailing / on proxy_pass: strip the /portal/ prefix for the backend.
    proxy_pass http://127.0.0.1:8080/;

    # Do not pass client-supplied RFC Forwarded headers through to the backend.
    proxy_set_header Forwarded "";

    # Canonical public host, do not arbitrarily reflect the client's Host.
    proxy_set_header Host app.example.test;
    proxy_set_header X-Forwarded-Host app.example.test;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Port 443;
    proxy_set_header X-Forwarded-Prefix /portal;

    # Use this form only when NGINX is actually the client-facing edge.
    proxy_set_header X-Forwarded-For $remote_addr;
}
```

`proxy_set_header Forwarded ""` tells NGINX not to forward the RFC 7239 header to the backend; NGINX also overwrites the listed `X-Forwarded-*` headers with values from its config/connection. If there are other forwarded headers that the backend processes, sanitize **all** of them per policy, not just the ones shown here. Audit your real infrastructure proxy config before treating it as secure.

If there is a **CDN in front of NGINX**, `$remote_addr` is the CDN's connecting IP, not necessarily the browser's IP. In that case, configure real-IP/trusted proxies on NGINX and process the client IP chain according to your topology; do not blindly switch `X-Forwarded-For` to `$proxy_add_x_forwarded_for`, as that can preserve client-fabricated values.

## 8. The `/portal` prefix scenario: a critical difference

Suppose the client calls:

```text
GET https://app.example.test/portal/orders
```

The proxy strips `/portal` before forwarding to the backend:

```text
GET http://127.0.0.1:8080/orders
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Prefix: /portal
```

The internal controller still maps `@GetMapping("/orders")`. Yet when it builds an **external absolute link** or redirect, the ideal result is:

```text
https://app.example.test/portal/orders
```

not:

```text
http://127.0.0.1:8080/orders
https://app.example.test/orders
```

`NATIVE` suffices for `X-Forwarded-For`/`X-Forwarded-Proto` in many Tomcat setups, yet **there is no portable guarantee that native containers understand `X-Forwarded-Prefix`**. `FRAMEWORK` is the Spring Boot-recommended solution when native support is insufficient. With MVC, `ForwardedHeaderFilter`/Spring's request wrapper can help `ServletUriComponentsBuilder` and Spring link builders recognize the forwarded prefix.

Verify in practice because the path can also depend on `server.servlet.context-path`, a trailing `/` in `proxy_pass`, servlet mappings, and prefix handling in your framework version. **Do not look only at `request.getRequestURI()` to conclude external URLs are right.** Call the API that actually generates `Location`/HATEOAS links and verify from the public URL.

`X-Forwarded-Prefix` is not a setting that "moves" all API endpoints to `/portal/**` inside the application; it represents the public prefix for forwarded-header-aware components. Backend routing still depends on the path the proxy actually sends.

## 9. Runnable Spring Boot MVC example to observe the differences

Build a small application returning request metadata seen by the Servlet API and an endpoint generating an absolute redirect. Use **Spring Boot 3.3.13, Java 21** in a project with the Gradle Wrapper.

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
```

**`src/main/java/com/example/forward/ForwardApplication.java`:**

```java
package com.example.forward;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ForwardApplication {
    public static void main(String[] args) {
        SpringApplication.run(ForwardApplication.class, args);
    }
}
```

**`src/main/java/com/example/forward/RequestInfoController.java`:**

```java
package com.example.forward;

import java.net.URI;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
public class RequestInfoController {

    public record RequestView(
            String scheme,
            String host,
            int port,
            boolean secure,
            String remoteAddress,
            String requestUri,
            String contextPath,
            String visibleUrl) {
    }

    @GetMapping("/inspect")
    public RequestView inspect(HttpServletRequest request) {
        return new RequestView(
                request.getScheme(),
                request.getServerName(),
                request.getServerPort(),
                request.isSecure(),
                request.getRemoteAddr(),
                request.getRequestURI(),
                request.getContextPath(),
                ServletUriComponentsBuilder.fromCurrentRequestUri()
                        .toUriString());
    }

    @GetMapping("/jump")
    public ResponseEntity<Void> jump() {
        URI location = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/inspect")
                .build()
                .toUri();

        return ResponseEntity.status(HttpStatus.FOUND)
                .location(location)
                .build();
    }
}
```

`RequestView` is a Java record, suitable for Java 17+. `visibleUrl` is computed with Spring `ServletUriComponentsBuilder` from the current request; if the proxy rewrites, this field helps detect differences from the public URL seen by the client. `jump()` builds `Location` from the current context path, serving as a check on **absolute URL generation** rather than just changing JSON display fields.

**`src/main/resources/application.properties`:**

```properties
server.port=8080
server.forward-headers-strategy=NONE

# When testing with Tomcat + a TLS-terminating proxy:
# server.tomcat.redirect-context-root=false
```

Run:

```bash
./gradlew bootRun
```

Test from loopback:

```bash
curl -s http://127.0.0.1:8080/inspect
curl -i http://127.0.0.1:8080/jump
```

With `NONE`, `inspect` scheme/host/port will reflect the backend HTTP connection. `Location` from `jump` may look like `http://127.0.0.1:8080/inspect`. `remoteAddress` is the IP of the socket client/proxy connecting to the server. Actual host, address, and status headers depend on how it is called and network config; compare only the **fields of interest**, rather than asserting an entire fixed JSON string.

## 10. Experimenting with all three modes on the same request

In an **isolated development environment**, you can simulate a trusted proxy by sending headers manually from localhost. This is only for studying rewrite behavior; **never allow public clients to send arbitrary headers to a production backend**.

First run the example in `NONE` mode:

```bash
curl -s -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: app.example.test' \
  -H 'X-Forwarded-Port: 443' \
  -H 'X-Forwarded-Prefix: /portal' \
  http://127.0.0.1:8080/inspect
```

With `NONE`, scheme/host/port usually remain at the backend view because Boot does not enable header processing. Change to:

```properties
server.forward-headers-strategy=NATIVE
```

restart, and send the same request. With Tomcat configured/trusting properly, you may see scheme `https`, `secure=true`, and container-processed info. The public prefix does not necessarily appear as with `FRAMEWORK`; if Tomcat does not trust the socket peer or `RemoteIpValve` config does not apply, check the native conditions.

Then switch to:

```properties
server.forward-headers-strategy=FRAMEWORK
```

restart, resend the request, and compare. Also try:

```bash
curl -i -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: app.example.test' \
  -H 'X-Forwarded-Port: 443' \
  -H 'X-Forwarded-Prefix: /portal' \
  http://127.0.0.1:8080/jump
```

Observe **`Location`** and the fields `scheme`, `host`, `port`, `contextPath`, `visibleUrl`. With `FRAMEWORK`, given valid headers, links/redirects built through Spring are better able to reflect the external origin and prefix than a native container that lacks prefix support.

**Note on stdout:** `remoteAddress`, `requestUri`, `contextPath`, `visibleUrl` JSON, and headers can vary by container/OS/version; this lesson does not state a single "exact" JSON shared across all three modes. The expected takeaway is a **property-by-property comparison**, not claiming one specific IP or `Location` across every environment.

For a real deployment, repeat the test **through the public proxy URL**, not only by sending spoofed headers directly. Only a public request proves rewriting, TLS termination, and header normalization work together.

## 11. RFC 7239 `Forwarded` and `X-Forwarded-*` are not the same thing

RFC 7239 uses a single header with parameters, for example:

```http
Forwarded: for=192.0.2.10;proto=https;host=app.example.test
```

The de facto equivalents in intent:

```http
X-Forwarded-For: 192.0.2.10
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
```

They are **not syntactically identical**. `Forwarded` can have multiple elements, quoted strings, IPv6, and delimiters requiring compliant parsing. `X-Forwarded-*` has no single standard covering every proxy/chain behavior. Native containers and Spring Framework may support different subsets or have different precedence rules.

**Principle:** the edge proxy should pick a single convention and strip the other or normalize per policy, avoiding sending `Forwarded: proto=http` alongside `X-Forwarded-Proto: https` and depending by chance on which library wins.

In Spring Framework 6.1, `ForwardedHeaderFilter` and `ForwardedHeaderTransformer` contain logic supporting both standard `Forwarded` and common `X-Forwarded` variants; verify how they interact if your environment sends non-standard headers. Never write your own parser using `split(",")[0]` and treat that as a trusted client IP.

## 12. `X-Forwarded-For` and client address: do not blindly take the first element

A request may pass through multiple proxies:

```text
client 192.0.2.10
   -> CDN 198.51.100.20
   -> ingress 10.2.0.8
   -> Spring Boot
```

The `X-Forwarded-For` header can become:

```text
192.0.2.10, 198.51.100.20
```

However, an attacker can inject the first value before traffic reaches the CDN if the CDN/ingress only appends without sanitizing. Thus:

```java
// Do not use as a trusted basis for authz/rate-limit/audit:
String claimedIp = request.getHeader("X-Forwarded-For")
        .split(",")[0].trim();
```

is not a valid algorithm for determining client IP. Identify the **trust starting point**: which proxies are truly infrastructure-controlled, whether they overwrite or append the header, which socket peers are permitted, and how far the server/container knows the trust chain.

Tomcat `RemoteIpValve` has `internal-proxies`/`trusted-proxies` settings suitable for these cases. In Spring Framework's filter, wrapping the request from headers **does not verify a proxy IP list on its own**. If rate limiting, geolocation, IP-based policy, or forensic logging is critical, use a client-address mechanism normalized by a trust boundary and test across multi-hop chains.

`X-Forwarded-For` is an **address asserted by the network path**, not a user identity. It does not replace authentication, authorization, or session validation.

## 13. HTTP → HTTPS redirects: avoid loops caused by the wrong scheme

Consider an application behind TLS termination:

```text
Client HTTPS -> Edge HTTPS -> Backend HTTP :8080
```

If the app checks `request.isSecure()` without processing `X-Forwarded-Proto`, it sees `false` and may redirect to HTTPS even though the client already used HTTPS. The result can be a **redirect loop** as the browser follows the redirect and re-sends the request through the proxy.

Choosing an appropriate forwarded strategy makes downstream code see the public scheme `https` and prevents self-redirects based on the backend scheme. Even so, enforcing HTTPS is usually simpler and more consistent at the **edge**, redirecting public HTTP port 80 to public HTTPS port 443 alongside an appropriate HSTS policy.

With Tomcat native mode, Spring Boot 3.3 specifically recommends:

```properties
server.forward-headers-strategy=NATIVE
server.tomcat.redirect-context-root=false
```

when TLS terminates at the proxy and `X-Forwarded-Proto` needs to be respected before context-root redirects. If a redirect is sent by Tomcat **before Servlet filters run**, `FRAMEWORK` cannot turn back time to rewrite an already-sent redirect; checking where a redirect originates is a key diagnostic step.

A redirect to the wrong URL may be caused by the app hardcoding a hostname, a separately configured OAuth callback URL, Spring Security, proxy rewriting, or a `Location` header emitted by the edge; **do not automatically blame `server.forward-headers-strategy` for every wrong redirect**.

## 14. CORS is a different mechanism from forwarded headers

**Forwarded headers** restore **external proxy request metadata**: scheme, host, port, client IP, and prefix.

**CORS (Cross-Origin Resource Sharing)** is a **browser JavaScript access policy** between origins. An origin consists of `scheme + host + port`. When a page at `https://spa.example.test` calls an API at `https://api.example.test`, it is cross-origin regardless of whether the API backend runs HTTP behind a proxy.

| Aspect | Forwarded headers | CORS |
| --- | --- | --- |
| Purpose | Reconstruct accurate request URL/public origin behind a proxy | Browser decides whether JS can read a cross-origin response |
| Primary request headers | `Forwarded`, `X-Forwarded-*` | `Origin`, plus `Access-Control-Request-Method/Headers` on preflight |
| Related response headers | Can affect `Location` and generated URLs/links | `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, ... |
| Where handled | Native server or Spring forwarded filter/transformer | Spring MVC/WebFlux CORS handlers, Spring Security, or edge proxy |
| Is it authn/authz? | No | No |
| Turns `HTTP` into real `HTTPS`? | No | No |
| Lets any frontend call the API? | No | Only when a suitable CORS policy is configured |

**Setting `server.forward-headers-strategy=FRAMEWORK` does not enable CORS**, and adding `@CrossOrigin` does not turn `request.getScheme()` from `http` into `https`. The two mechanisms may need to work together, but they have independent responsibilities.

Making the framework see the right public scheme/host can occasionally affect same-origin checks or generated URLs. Still, it does not replace configuring a CORS allowlist, credentials policy, and preflight handling. Conversely, passing CORS does not prove proxy forwarding is secure.

## 15. Configuring CORS with the right scope, not as a proxy workaround

Spring MVC example allowing only the `https://spa.example.test` frontend to call `/api/**`. Below is an **integration snippet** in a Spring Boot MVC application that can live in the same package as `@SpringBootApplication`:

**`src/main/java/com/example/forward/CorsConfiguration.java`**

```java
package com.example.forward;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class CorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://spa.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization")
                .maxAge(1800);
    }
}
```

The class name `CorsConfiguration` in the example package is not the framework's `org.springframework.web.cors.CorsConfiguration`; to avoid confusion in a larger project, you can rename it to `WebCorsPolicy`. This snippet does not enable `allowCredentials(true)` by default. If cookie-based cross-origin auth is needed, configure an appropriate credentials policy and address CSRF, `SameSite`, sessions, and OAuth/cookie rules independently.

Test preflight:

```bash
curl -i -X OPTIONS 'http://127.0.0.1:8080/api/data' \
  -H 'Origin: https://spa.example.test' \
  -H 'Access-Control-Request-Method: GET'
```

This result is only meaningful if a **`/api/data` mapping** exists and the CORS configuration applies to that route. The earlier `RequestInfoController` sample does not have `/api/data`; for an end-to-end test, add a `/api/data` controller route or test an existing API. Otherwise, a routing error can be mistaken for a CORS error.

If Spring Security is used, integrate CORS in the right place in the security filter chain (typically via `.cors(...)`) so preflight is not blocked by authentication filters before MVC CORS handles it. Do not have NGINX return `Access-Control-Allow-Origin: *` while Spring returns a specific origin and expect both policies to merge cleanly.

**Warning:** with credentialed CORS, never combine wildcard `"*"` in `allowedOrigins` with `allowCredentials=true`; configure explicit origins or appropriate `allowOriginPatterns` and restrict the allowed list.

## 16. WebFlux: `ForwardedHeaderTransformer` is not a Servlet filter

In a reactive Spring WebFlux application, requests are represented by `ServerHttpRequest` and do not necessarily pass through a Servlet filter like MVC. When setting:

```properties
server.forward-headers-strategy=FRAMEWORK
```

Spring Boot selects Spring WebFlux's **`ForwardedHeaderTransformer`** to transform request headers and URI according to forwarded metadata before reactive layers process the request. With `NATIVE`, forwarding details are handled by the reactive server/container (such as Reactor Netty) per its native capabilities.

WebFlux controller snippet returning the URI, **not to be used alongside the Servlet demo controller in the same application**:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveInspectController {

    @GetMapping("/reactive/inspect")
    public Mono<String> inspect(ServerWebExchange exchange) {
        var uri = exchange.getRequest().getURI();
        return Mono.just(uri.toString());
    }
}
```

This is an **integration snippet**, requiring `spring-boot-starter-webflux` and running in a reactive application. When both MVC and WebFlux starters are present, Spring Boot typically defaults to the Servlet web application type; do not assume adding `spring-boot-starter-webflux` guarantees `ForwardedHeaderTransformer` is active.

In WebFlux, forwarded processing does not create proxy trust either: the edge must sanitize, backend access must be restricted, and headers must be consistent. When WebFlux transforms the request differs from the Servlet pipeline; to debug, inspect `ServerHttpRequest.getURI()` and reactive link builders, and do not use Tomcat `RemoteIpValve` when running Reactor Netty.

## 17. Do not enable both Native Valve and Framework Filter uncontrollably

An error-prone configuration:

```text
Tomcat RemoteIpValve         reads X-Forwarded-Proto -> request scheme=https
ForwardedHeaderFilter        re-processes forwarded headers -> wrapper transforms again
Custom URL builder           manually parses X-Forwarded-Host a third time
```

Each layer handles `Forwarded` and `X-Forwarded-*` differently, sometimes with different precedence or after stripping headers from the wrapper. If a manually registered `ForwardedHeaderFilter` exists alongside `server.forward-headers-strategy=NATIVE`, the property no longer accurately describes reality; conversely, a manually added native Valve can interfere with `FRAMEWORK`.

**Pick one primary owner.** For `NATIVE`, configure the container's proxy rules and remove duplicate custom Spring filters; for `FRAMEWORK`, avoid double native rewriting unless there is a carefully tested reason.

In particular, the framework filter must run early enough so downstream filters/controllers see the wrapped request. If registering manually via `FilterRegistrationBean`, configure ordering and dispatcher types (`REQUEST`, `ASYNC`, `ERROR` where appropriate). Boot auto-configuration handles much of this for `FRAMEWORK`; do not write manual filter registration just to duplicate Boot's behavior.

## 18. The `removeOnly` case and disabling header trust

Spring Framework provides a **remove-only** mode for forwarded headers:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.filter.ForwardedHeaderFilter;

@Configuration(proxyBeanMethods = false)
public class RemoveUntrustedForwardedHeaders {

    @Bean
    ForwardedHeaderFilter forwardedHeaderFilter() {
        ForwardedHeaderFilter filter = new ForwardedHeaderFilter();
        filter.setRemoveOnly(true);
        return filter;
    }
}
```

This is a **manual configuration option on the Servlet stack** and should not be added to an app already configured with `server.forward-headers-strategy=FRAMEWORK` if it causes Boot and custom config to conflict. It is more appropriate when you want Spring to treat requests **using the backend connection**, prevent downstream MVC code from using forwarded headers, and explicitly control filter order.

However, `removeOnly` is not a substitute for edge sanitization. Before a request reaches the application, web server/Valve layers, gateway filters, or logging middleware may have already read the headers. To distrust headers system-wide, block/sanitize at the edge and do not register a native Valve that accepts them.

Some use cases require retaining raw forwarded headers for accurate auditing. In such cases, logging at the **trusted ingress** can be better than logging from an app using a request wrapper. Never put a raw user-controlled `X-Forwarded-For` into audit identity fields as though it were a verified IP.

## 19. Controlled testing: verify exactly which layer applied

Use three observation points:

**A. Servlet metadata:** `request.getScheme()`, `request.getServerName()`, `request.getServerPort()`, `request.isSecure()`, `request.getRemoteAddr()`.

**B. Generated URLs:** `ServletUriComponentsBuilder.fromCurrentRequestUri()` and the `Location` response header from `/jump`.

**C. Real network/proxy behavior:** send requests to the **public HTTPS endpoint** and inspect headers emitted by the edge, the real backend connection, and the redirect chain.

Sample test matrix (without hardcoding one IP across every runtime):

| Scenario | Input | Expectation to verify |
| --- | --- | --- |
| Local direct, `NONE` | `http://127.0.0.1:8080/inspect` | Request sees backend scheme/host/port |
| `NONE` + spoofed forwarded headers on localhost | Send `X-Forwarded-Proto: https` | Boot does not automatically alter servlet metadata |
| `NATIVE` + trusted local proxy | Send headers matching Tomcat conventions | Native can apply scheme/secure/client IP per rules |
| `FRAMEWORK` + canonical host/proto | Send headers through a trusted proxy | Spring wrapper reflects public scheme/host/port |
| `FRAMEWORK` + `/portal` prefix | Proxy strips prefix | Generated links and redirects include external prefix per design |
| Conflicting `Forwarded` and `X-Forwarded` | Test in staging | Disallowed in production; fix edge normalization |
| Public backend receives spoofed host | Security test check | Backend unreachable directly or ignores spoofed headers |
| Disallowed CORS origin | `Origin: https://evil.example` | No CORS permission outside allowlist |
| OAuth/login redirect through proxy | Exercise real auth flow | Callback and redirect scheme/host/port match, no backend host leaked |
| Multiple trusted proxy hops | CDN + ingress + app | Client address and audit fields follow trust policy, not client choice |

A simple regression test can assert the `Location` value from `/jump` at the **public URL**, yet you should not treat all forwarded fields as trusted identities simply because that test passes.

## 20. Common errors and how to diagnose them

| Symptom | Possible cause | Where to investigate |
| --- | --- | --- |
| Returned link is `http://localhost:8080/...` | Forwarded headers unused or URL builder hardcodes backend | `server.forward-headers-strategy`, controller link code |
| External HTTPS yet `request.isSecure=false` | Proxy terminates TLS, backend is HTTP, strategy/trust rules not applied | `X-Forwarded-Proto`, server mode, socket trust |
| 302 HTTP/HTTPS redirect loop | App sees wrong scheme or redirects occur at multiple layers | Browser redirect chain, edge redirect, `request.isSecure` |
| `Location` missing `/portal` | Proxy strips prefix, `NATIVE` does not process prefix | `X-Forwarded-Prefix`, `FRAMEWORK`, route rewrites |
| `Location` repeats `/portal/portal` | Proxy and app both add prefix | Compare inbound request path, servlet context path, header prefix |
| Remote IP is always the proxy | XFF not processed or no trusted chain yet | Native Valve config, ingress headers |
| Remote IP becomes arbitrary caller-supplied IP | Trusting untrusted leftmost XFF element | Edge sanitization, proxy trust, no manual split |
| Response redirects to `evil.example` | Host forwarding injection | Lock down backend, sanitize `X-Forwarded-Host`, canonical host allowlist |
| `FRAMEWORK` enabled yet Tomcat redirect still wrong | Container sends redirect before Servlet filter | Tomcat `redirect-context-root`, container configuration |
| Works in cloud, differs locally | Default strategy differs between supported cloud and other envs | Set property explicitly |
| Switching `NATIVE` to `FRAMEWORK` changes client IP | Different layer and address handling | Check `RemoteIpValve`/`ForwardedHeaderFilter` behavior |
| CORS preflight 401/403 | Spring Security blocks preflight or CORS unconfigured | Security `.cors(...)`, CORS mappings |
| CORS passes yet JSON URLs are wrong | CORS does not rewrite forwarded URLs | Separate link-builder checks from CORS |
| Public HTTPS shows wrong certificate | Edge TLS termination/SSL config | Check proxy certificate, do not tweak forwarded headers |
| Only some APIs show wrong origin | Endpoint manually builds URLs with hardcoded host/raw header | Audit URL builders and related libraries |

Diagnose in order: **real HTTP request to edge → edge sanitization → backend connection → native/framework strategy → handler/link builder → response headers**. Do not keep tweaking `server.forward-headers-strategy` when the bug comes from missing proxy headers or a controller concatenating `"http://" + host`.

## 21. Security: host spoofing, secure cookies, redirects, and OAuth callbacks

Forwarded headers affect **how the framework perceives the public origin**, so a faulty trust policy causes consequences beyond ugly URLs:

- **Host-header injection:** If the app uses an unverified `X-Forwarded-Host` to build password-reset links or absolute redirects, an attacker can steer users to a host they control.
- **Open redirect:** Redirect logic built from request scheme/host can be hijacked when headers are not sanitized.
- **Secure channel detection:** If the app relies on `request.isSecure()` from forwarded proto, a forged HTTPS header can mislead the app about transport protection. Enforce real TLS and HSTS at the edge.
- **Cookies:** `Secure`, `SameSite`, `Domain`, `Path`, or OAuth/logout links can depend on host/scheme/prefix configuration. Verify behind a real proxy, not only in controller tests.
- **Rate limit/IP ban:** If IPs come from an untrusted XFF, an attacker can evade limits or cause others to be blocked mistakenly.
- **Audit:** Logs should clearly separate socket peer, trusted-chain IP, and trace/correlation metadata; never replace a trusted source with raw client-supplied fields.

Enabling `NATIVE` does not solve all of these on its own, because the container must also know **which proxies are trusted**. Enabling `FRAMEWORK` does not create a trusted-proxy list automatically. The primary control layer is the **proxy edge and backend network**; the application should use canonical host configuration when generating sensitive links.

One effective mitigation is never building password-reset or OAuth callbacks from arbitrary request host headers; use a **fixed configured public base URL** when high assurance is required.

## 22. When to choose NONE, NATIVE, or FRAMEWORK?

| Architecture / requirement | Initial choice | Additional conditions |
| --- | --- | --- |
| App receives HTTPS/HTTP directly, no proxy | `NONE` | Do not trust client-supplied forwarded headers |
| Simple proxy, Tomcat needs XFF/XFP, no external prefix | `NATIVE` | Configure/trust `RemoteIpValve`, edge sanitization |
| Proxy strips `/portal`, needs Spring-generated absolute links | `FRAMEWORK` | Edge sends `X-Forwarded-Prefix`, test redirects/links |
| WebFlux app behind reverse proxy needing public origin restored | `FRAMEWORK` or `NATIVE` per server | With `FRAMEWORK` use `ForwardedHeaderTransformer` |
| Kubernetes Ingress / Cloud LB | Set explicit value after understanding topology | Do not rely on cloud auto-detection defaults |
| Proxy forwards RFC 7239 `Forwarded` rather than XFF/XFP | Check actual server/framework support | Do not send two conflicting conventions |
| Want to strip untrusted headers without applying them | Edge sanitization + optional `removeOnly` filter | Do not enable double processing |
| SPA CORS is blocked | **Not solved by picking a forward strategy** | Configure origin allowlist / Security CORS separately |
| Untrusted header IPs for rate limiting | Proxy/network trust rules first | Never manually parse first XFF element |

**Pragmatic rule:** start from the **headers your trusted proxy actually provides**. If `NATIVE` satisfies all URL/redirect/IP needs on your stack, keep it simple. If prefix handling or fuller Spring-aware behavior is needed, pick `FRAMEWORK` and verify against the public URL. Never enable both without a tested reason.

## 23. Review questions

1. Why might a public HTTPS request reach Spring Boot over HTTP while the app still needs to emit `https://...` links?
2. At which **processing layer** do `server.forward-headers-strategy=NATIVE` and `FRAMEWORK` differ in Spring MVC?
3. How does Tomcat `RemoteIpValve` differ from `ForwardedHeaderFilter`? Why doesn't `NATIVE` always handle external prefixes like `FRAMEWORK`?
4. How can a client spoof `X-Forwarded-For`? Why must you never take the first element via `split(",")[0]` for access checks?
5. When is `server.tomcat.redirect-context-root=false` needed?
6. How should a proxy handle `Forwarded: for=...;proto=...;host=...` and `X-Forwarded-*` to avoid conflicts?
7. If an app enters an HTTPS↔HTTP redirect loop, which layers should you inspect before editing `@Controller`?
8. Why does `@CrossOrigin` or passing CORS not prove URL generation behind a proxy is correct?
9. In WebFlux, why is `ForwardedHeaderTransformer` used instead of Servlet `ForwardedHeaderFilter`?
10. For an endpoint generating password-reset links, why is a preconfigured canonical base URL safer than trusting a raw forwarded host?
11. If both a custom Tomcat Valve and Boot `FRAMEWORK` are active, how can double-processing bugs occur?
12. What tests are needed to prove the `/portal` prefix works correctly through the proxy without being added twice?

**Remember:** Forwarded headers restore the **public request view** behind one or more proxies. `NATIVE` delegates to the **web server/container**, `FRAMEWORK` delegates to **Spring Framework**, and `NONE` prevents Boot from proactively interpreting them. Choose the right strategy after establishing a **trusted proxy boundary**. CORS is a separate browser cross-origin policy, not a proxy header-forwarding mechanism.

### Official references

- Spring Boot 3.3 — Embedded Web Servers, Running Behind a Front-end Proxy Server: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 — `ForwardHeadersStrategy` enum API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/ServerProperties.ForwardHeadersStrategy.html
- Spring Boot 3.3 — Common Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Framework — Servlet Filters / Forwarded Headers: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Framework 6.1 — `ForwardedHeaderFilter` API: https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html
- Spring Framework — WebFlux Forwarded Headers: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework — CORS for MVC: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- RFC 7239 — Forwarded HTTP Extension: https://www.rfc-editor.org/rfc/rfc7239