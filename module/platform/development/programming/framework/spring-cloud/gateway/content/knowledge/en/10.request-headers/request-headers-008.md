# Forwarded, X-Forwarded-*, and Trusted Proxy Information

## 1. Why Do Forwarded Headers Matter in an API Gateway?

In a microservices architecture, clients rarely connect directly to the Spring Cloud Gateway application. Requests often travel through CDNs, WAFs, load balancers, ingresses, and one or more reverse proxies before reaching the gateway. These intermediate hops can alter the peer address, HTTPS/HTTP scheme, `Host`, and path. Without information about upstream hops, the target service cannot easily determine the external URL the client originally requested.

**`Forwarded`** and the **`X-Forwarded-*`** header family pass this context between proxies. They commonly participate in building absolute URLs, redirects, trace/log investigations, determining client IP addresses, and policy selection. However, **HTTP headers can be sent directly by clients**. A gateway should only rely on proxy metadata after controlling its origin and trust boundaries.

This lesson belongs to the **Request Headers** chapter of **SPRING_CLOUD_GATEWAY**. This knowledge complements route predicates, the filter chain, path/header transformations, and service discovery; it also directly impacts authentication, IP-based rate limiting, circuit breakers, retries, TLS, and request observability when operating a secure microservices entry point.

After this lesson, you will be able to:

1. Distinguish the structure of `Forwarded` from `X-Forwarded-For/Host/Proto/Port/Prefix` headers.
2. Understand the difference between a direct connection peer and a client IP **inferred** through proxies.
3. Design trust boundaries: strip untrusted inbound headers, regenerate them at the edge, and accept connections only from permitted proxies.
4. Configure **`trusted-proxies`** and `x-forwarded.*` options properly for your Spring Cloud Gateway release line.
5. Distinguish Spring WebFlux's `ForwardedHeaderTransformer` from the Gateway's `HttpHeadersFilters`.
6. Verify behavior on a backend and detect header-spoofing attempts in a test environment.

> **Scope:** Examples focus on **Spring Cloud Gateway Server WebFlux**. Versions 4.2.x, 4.3.x, and 5.x have property naming differences. Gateway Server MVC uses its own namespace and filters; refer to the documentation for that exact variant.

## 2. Inspecting the Full Proxy Chain Before Reading Headers

Suppose the architecture is:

~~~mermaid
flowchart LR
    C["Client<br/>198.51.100.24"] -->|"HTTPS"| E["WAF / Edge<br/>10.0.1.10"]
    E -->|"Internal HTTP or HTTPS"| I["Ingress<br/>10.0.1.20"]
    I --> G["Spring Cloud Gateway<br/>10.0.2.30"]
    G -->|"Route + filter + proxy"| B["orders-service"]
~~~

In this example, the WAF is the **first trust boundary**: it accepts requests from the Internet, strips any client-supplied `Forwarded` and `X-Forwarded-*` values, and creates fresh metadata from the real connection. The ingress accepts traffic only from the WAF and appends metadata following agreed rules. The gateway accepts traffic only from the ingress.

At that point, the request arriving at the gateway **might** carry:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
X-Forwarded-For: 198.51.100.24, 10.0.1.10
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.test
X-Forwarded-Port: 443
~~~

The addresses above are illustrative. A real system may choose to pass only `Forwarded`, only `X-Forwarded-*`, or both if configured consistently.

| Concept | Illustrative value | Source of truth |
| --- | --- | --- |
| Real client IP | `198.51.100.24` | Connection observed by the WAF; trusted **after the WAF sanitizes input** |
| First proxy | `10.0.1.10` | WAF, observed by the ingress |
| Proxy connecting directly to gateway | `10.0.1.20` | Peer of the connection to the gateway |
| Scheme used by client | `https` | Client → WAF connection, if confirmed by the WAF |
| Scheme between ingress and gateway | May be `http` | Depends on internal TLS termination/re-encryption |
| Public Host | `api.example.test` | Validated by edge and forwarded per rules |

`198.51.100.0/24`, `192.0.2.0/24`, and `203.0.113.0/24` are IPv4 ranges reserved for documentation examples; `2001:db8::/32` is an illustrative IPv6 range. Never use them as production allowlists.

**Never conflate three distinct things:** the TCP connection's peer IP, an address written in the XFF header, and a client address *verified by a proxy*. Only the last one is suitable for sensitive decisions, and it depends on the entire trust chain.

## 3. Forwarded: Standard Format per RFC 7239

RFC 7239 defines the standard `Forwarded` header to describe proxy information using parameters:

| Parameter | Meaning | Example |
| --- | --- | --- |
| `for` | Party that sent the request to the proxy at that hop | `for=198.51.100.24` |
| `by` | Receiving interface of the proxy | `by=10.0.1.10` |
| `host` | Host observed by the proxy on the incoming request | `host=api.example.test` |
| `proto` | Scheme/protocol received by the proxy | `proto=https` |

Single-hop example:

~~~http
Forwarded: for=198.51.100.24;proto=https;host=api.example.test
~~~

With multiple proxies, **forwarded elements** are separated by **commas**. Inside each element, key-value pairs are separated by **semicolons**:

~~~http
Forwarded: for=198.51.100.24;proto=https;host=api.example.test, for=10.0.1.10;proto=https;host=api.example.test
~~~

The header may appear across multiple header lines with the same name depending on proxies and the HTTP layer. When parsing, follow RFC quoting and escaping rules—never blindly call `split(",")` and `split(";")` and treat the output as trusted security data.

IPv6 addresses typically require a quoted string and brackets:

~~~http
Forwarded: for="[2001:db8::1234]";proto=https;host=api.example.test
~~~

Per the RFC, `for` or `by` can also hold obfuscated identifiers or `unknown`; hence not every value is an IP suitable for CIDR matching. The `Forwarded` header describes proxy metadata, **not a digital signature or proof of authentication**.

### When Is Forwarded Useful?

Suppose a client visits `https://api.example.test/account`, yet the gateway receives the internal request from ingress as `http://gateway:8080/account`. If the backend builds absolute links or returns an HTTP `Location` derived from the internal URL, it may emit the wrong scheme/host and redirect to a private hostname. Verified proxy headers enable the application to reconstruct the external URL, e.g., `https://api.example.test/account`.

Conversely, blindly trusting a client-sent `host=attacker.example` value can cause the backend to emit redirects/links to malicious domains or apply incorrect cookie policies. Therefore, **validate allowed Hosts and sanitize headers at the edge** before using metadata to construct URLs.

## 4. X-Forwarded-*: The Widely Used Header Family in Practice

Unlike the standard `Forwarded` header, many reverse proxies emit `X-Forwarded-*` headers by historical convention. They do not necessarily share identical contents or syntax with RFC 7239.

| Header | Common meaning | Example | Notes |
| --- | --- | --- | --- |
| `X-Forwarded-For` | Chain of client IP and prior proxies | `198.51.100.24, 10.0.1.10` | The leftmost element is **not automatically** trustworthy |
| `X-Forwarded-Proto` | Scheme used by client entering the proxy | `https` | May differ from the internal scheme to the gateway |
| `X-Forwarded-Host` | Public Host requested by the client | `api.example.test` | Must guard against host header injection |
| `X-Forwarded-Port` | Client/proxy-side port | `443` | Does not always equal the gateway's listening port |
| `X-Forwarded-Prefix` | Public prefix altered by proxy before forwarding | `/api` | Must stay consistent with path rewrites; stacks vary in support |
| `X-Forwarded-Ssl` | Legacy convention indicating front-end SSL/TLS | `on` | Use only when infrastructure and frameworks explicitly support it |

### 4.1. X-Forwarded-For Across Multiple Hops

The chain is typically appended left-to-right:

~~~text
X-Forwarded-For: client, earlier-proxy, next-proxy
                 leftmost               rightmost
~~~

Normally, the last proxy immediately before the gateway **is not inside the XFF chain it receives/sends** until its own address is appended by a subsequent hop. The gateway can still observe that immediate peer from the network connection.

Suppose a malicious client intentionally sends:

~~~http
X-Forwarded-For: 203.0.113.99
~~~

If the WAF merely appends, the chain reaching the gateway becomes:

~~~http
X-Forwarded-For: 203.0.113.99, 198.51.100.24, 10.0.1.10
~~~

The value `203.0.113.99` was **self-declared by the client**. Any component that reads the leftmost IP and trusts it will be tricked. The edge WAF must strip Internet-supplied values and initialize XFF from the observed peer address, or apply an equivalent verified normalization mechanism.

### 4.2. Prefixes and External URLs

For example, suppose the ingress serves `https://api.example.test/edge/orders/42` but strips `/edge` before forwarding to the gateway, so the gateway sees `/orders/42`. If the trusted proxy sets `X-Forwarded-Prefix: /edge`, supporting components can use that prefix when reconstructing URLs/links.

This is **not the same** as the Gateway's `StripPrefix`/`SetPath` filters: those filters change the **request path sent to the backend**, whereas `X-Forwarded-Prefix` expresses the **public path context**. Configuring both out of order or duplicating prefixes can yield broken links or doubled path segments.

## 5. Two Directions of Header Processing in Spring Cloud Gateway

In **Gateway Server WebFlux**, two easily confused processing layers exist:

1. **Headers arriving at the gateway:** headers sent by clients/proxies are received by the WebFlux HTTP server. When configured, WebFlux or the server layer can read forwarded metadata to adjust the current request's URI/remote address.
2. **Headers sent from the gateway to the backend:** **`HttpHeadersFilters`** such as `Forwarded Headers Filter` and `XForwarded Headers Filter` are applied when preparing the outbound HTTP request, e.g., inside `NettyRoutingFilter`.

~~~mermaid
flowchart TD
    C["Client / proxy"] --> I["HTTP request to Gateway<br/>Forwarded, X-Forwarded-*"]
    I --> T["WebFlux / server processes<br/>forwarded input if configured"]
    T --> M["Route predicates and<br/>gateway filter chain"]
    M --> H["HttpHeadersFilters:<br/>Forwarded, XForwarded,<br/>RemoveHopByHop"]
    H --> R["Gateway HTTP client<br/>sends to service"]
    R --> B["Backend"]
~~~

**Do not think of `trusted-proxies` as a firewall that automatically blocks connections from other IPs.** This property governs the Gateway's version-specific forwarded-header trust/generation logic. Controlling **who can connect to the gateway** still requires firewalls, ingress policies, network ACLs, or equivalent; untrusted inbound headers must be sanitized at the edge proxy.

### 5.1. Forwarded Headers Filter

Per the WebFlux Gateway documentation, this filter generates the `Forwarded` header sent downstream using the current request's `Host`, scheme, and port, and can append to existing headers per trust policy. In current versions, enabling this behavior requires configuring `trusted-proxies` with a **Java regular expression**.

In the 4.3+/5.x line, the property `spring.cloud.gateway.server.webflux.forwarded.by.enabled=true` enables adding the `by` parameter; the documented default is `false`.

### 5.2. XForwarded Headers Filter

This filter sets `X-Forwarded-*` fields on the request sent downstream based on the current host, scheme, port, and path. Options use suffixes:

- `for-enabled`, `host-enabled`, `port-enabled`, `proto-enabled`, `prefix-enabled` to toggle generation of each field.
- `for-append`, `host-append`, `port-append`, `proto-append`, `prefix-append` to control whether prior values are appended to.

According to Spring Gateway 4.2/4.3/5.1 docs, these flags **default to true** once the corresponding filter is active. In multi-proxy systems, appending requires careful verification: appending onto an Internet-spoofed list is unsafe even if syntactically valid HTTP.

### 5.3. RemoveHopByHop Headers Filter

Headers valid only for a **single HTTP connection** (hop-by-hop) must not be forwarded across proxies as end-to-end headers. The Gateway includes a filter that strips the documented default list: `Connection`, `Keep-Alive`, `Proxy-Authenticate`, `Proxy-Authorization`, `TE`, `Trailer`, `Transfer-Encoding`, and `Upgrade`.

`Forwarded` and `X-Forwarded-*` are **not** hop-by-hop headers; verifying them requires dedicated trust mechanisms. When using HTTP Upgrade/WebSocket or specialized protocols, inspect the Gateway's corresponding filter/protocol handler rather than arbitrarily disabling header protections.

## 6. Configuring `trusted-proxies` by Version

Official documentation introduced an important namespace change:

| Spring Cloud Gateway Server WebFlux | Trusted proxy property | XFF generation option |
| --- | --- | --- |
| **4.2.x** | `spring.cloud.gateway.trusted-proxies` | `spring.cloud.gateway.x-forwarded.for-enabled` |
| **4.3.x** | `spring.cloud.gateway.server.webflux.trusted-proxies` | `spring.cloud.gateway.server.webflux.x-forwarded.for-enabled` |
| **5.0.x / 5.1.x** | `spring.cloud.gateway.server.webflux.trusted-proxies` | `spring.cloud.gateway.server.webflux.x-forwarded.for-enabled` |

Specifically, 4.3.x often still declares **routes** under `spring.cloud.gateway.routes`, whereas `trusted-proxies` and `x-forwarded.*` already use the **`server.webflux`** prefix. The 5.x line uses `spring.cloud.gateway.server.webflux.routes`. Never infer every property's namespace solely from where routes are placed.

### 6.1. Example for 4.3.x and 5.x

Suppose only the WAF `10.0.1.10` and ingress `10.0.1.20` are managed proxies properly recorded in the forwarded chain. WebFlux configuration to set trust policy and control forwarded headers:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          trusted-proxies: '^(?:10\.0\.1\.10|10\.0\.1\.20)$'
          x-forwarded:
            for-enabled: true
            for-append: true
            host-enabled: true
            host-append: true
            proto-enabled: true
            proto-append: true
            port-enabled: true
            prefix-enabled: true
~~~

**The `trusted-proxies` value is a Java regex, not a CIDR.** Dots in IPs must be escaped, like `10\.0\.1\.10`. YAML single quotes preserve backslashes literally. The regex above only **illustrates syntax**; production configs must be verified against your exact version's matching behavior, the header format emitted by your proxies, and your actual proxy IP list. Never use `.*` to "trust everything" on an Internet-facing system.

Note that `for-append: true` makes sense for preserving proxy history **only when inbound headers have already been sanitized**. Enabling the property does not mean the gateway automatically identifies the true client IP; inspect downstream requests to confirm the XFF chain contains no spoofed entries.

### 6.2. Example for 4.2.x

In Gateway WebFlux 4.2.x, the documented namespace is:

~~~yaml
spring:
  cloud:
    gateway:
      trusted-proxies: '^(?:10\.0\.1\.10|10\.0\.1\.20)$'
      x-forwarded:
        for-enabled: true
        for-append: true
        proto-enabled: true
        host-enabled: true
~~~

Filter options beyond the namespace difference should be checked in the reference docs for your exact **patch version**. If after an upgrade the backend suddenly stops receiving `Forwarded` or `X-Forwarded-*`, inspect Gateway security changes and `trusted-proxies` settings before widening your regex.

### 6.3. Security Advisory Published by Spring

Spring published **CVE-2025-41235** regarding Gateway Server forwarding `Forwarded`/`X-Forwarded-For` from untrusted proxy sources. Per the advisory, affected versions include **4.2.0–4.2.2** and **4.1.0–4.1.7**; fixed versions are **4.2.3** and **4.1.8**, respectively, alongside other older branches listed in the advisory.

Starting in the patched releases, forwarded-header behavior became stricter: forwarding of these headers is disabled by default until appropriate trusted proxies are configured. **Never downgrade or disable checks just to make XFF reappear.** Upgrade to a patched release and review your reverse proxy config alongside the matching properties.

Reference: [Spring Security Advisory — CVE-2025-41235](https://spring.io/security/cve-2025-41235/).

## 7. How WebFlux `ForwardedHeaderTransformer` Differs from `HttpHeadersFilters`

Spring Framework WebFlux provides `ForwardedHeaderTransformer` to **read forwarded headers on incoming requests**, use them to reconstruct certain URL/remote-address fields on the request, and remove the processed headers; it can be enabled via a bean named `forwardedHeaderTransformer` or via appropriate Spring Boot configuration.

In Spring Boot 3.x lines, one configuration documented by Boot is:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

This mode makes WebFlux process forwarded input at the framework layer. `native` delegates processing to the underlying web server; `none` does not enable this mechanism automatically. **Property names and detailed behavior may change in newer Spring Boot releases**, so read the documentation for your exact version. Never enable both native and framework modes blindly.

Key differences:

| Component | Position | Primary purpose |
| --- | --- | --- |
| Spring WebFlux `ForwardedHeaderTransformer` | **Inbound side** of request, before app handles exchange | Reconstructs URI/remote from forwarded input if allowed; strips headers after processing |
| Gateway `Forwarded Headers Filter` | **Outbound side** sending request downstream | Creates/appends standard `Forwarded` header |
| Gateway `XForwarded Headers Filter` | **Outbound side** sending request downstream | Creates/appends `X-Forwarded-*` set |
| Edge reverse proxy/ingress at trust boundary | **Before Gateway** | Strips client-supplied metadata and writes verified metadata |

### 7.1. The `removeOnly` Mode

When an application wants to ignore all caller-supplied forwarded metadata, WebFlux can register the transformer in **`removeOnly`** mode:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.adapter.ForwardedHeaderTransformer;

@Configuration
class ForwardedHeaderPolicy {

    @Bean(name = "forwardedHeaderTransformer")
    ForwardedHeaderTransformer forwardedHeaderTransformer() {
        ForwardedHeaderTransformer transformer =
                new ForwardedHeaderTransformer();
        transformer.setRemoveOnly(true);
        return transformer;
    }
}
~~~

This example targets the **WebFlux request-intake layer**: it removes forwarded headers without using them to alter request metadata. Pick one consistent configuration approach; do not mix this bean with `server.forward-headers-strategy=framework` without checking auto-configuration in your running version.

If the gateway needs to accept metadata from a trusted ingress and also regenerate forwarded headers downstream, choosing `removeOnly` can wipe out the metadata you intended to propagate. Whether to enable the transformer must be a **trust-boundary and architectural decision**, not a toggle trick to fix HTTP status codes.

### 7.2. What Happens to the Remote Address?

Before forwarded input is processed, `exchange.getRequest().getRemoteAddress()` typically reflects the **direct connecting peer** (the ingress). After a component processes forwarded headers at the WebFlux or web-server layer, the request's remote address may be rewritten to the IP derived from the header.

Consequently, when using the `RemoteAddr` predicate, `XForwardedRemoteAddr` predicate, or IP-based rate limiters, verify **which value you are matching against**, whether it has been reliably sanitized, and how prior layers processed headers. `trusted-proxies` in `HttpHeadersFilters` and resolvers used by route predicates are not automatically interchangeable.

## 8. Designing Trust Boundaries at Edge Proxies

A secure architecture must combine **network rules** with **header rules**:

~~~mermaid
flowchart TD
    C["Internet: request may contain<br/>spoofed Forwarded"] --> E["Edge WAF / ingress"]
    E --> X["Strip client-supplied<br/>Forwarded and X-Forwarded-*"]
    X --> V["Create metadata from TLS, peer IP,<br/>and validated Host"]
    V --> N{"Only permitted proxies<br/>can reach Gateway?"}
    N -->|"No"| D["Block at network boundary"]
    N -->|"Yes"| G["Gateway processes per<br/>version + trusted-proxies"]
    G --> B["Backend authenticates / authorizes<br/>and observes request"]
~~~

Implementation principles:

1. **Leave no bypass port open:** the gateway must only accept traffic from managed proxies. If clients can reach the gateway directly and supply forged forwarded headers, the trust model is broken.
2. **Strip both header families at the edge:** even if you only use `X-Forwarded-*`, strip untrusted `Forwarded` headers; a downstream service might prioritize the standard header.
3. **Record metadata from real connections:** derive client IP from the peer observed by the edge; write `proto=https` only when the edge truly terminated HTTPS. Validate `Host` against an allowlist to prevent attacker-controlled redirects/links.
4. **Standardize append rules across internal proxies:** subsequent hops must accept traffic only from the prior hop and append the observed peer IP in a tested format. Avoid dynamic topologies while still assuming client IP sits at a fixed index.
5. **Protect every hop:** TLS to the edge does not automatically encrypt edge → ingress → gateway → service links. Consider internal HTTPS/mTLS, network policies, and secret/token protection.
6. **Authenticate independently of IP:** forwarding headers mainly support routing, URL reconstruction, and observability. Business authorization and token validation must still be enforced at the appropriate layers.

### 8.1. Illustrating How an Edge Nginx Regenerates Headers

This example **only illustrates the `location` block** where Nginx acts as the first public proxy, has terminated TLS, and validates `server_name`/Host. It omits certificates, upstreams, and network settings:

~~~nginx
location / {
    proxy_pass http://gateway_upstream;

    # Do not forward client-supplied Forwarded headers.
    proxy_set_header Forwarded "";

    # Regenerate metadata from the edge-verified connection/host.
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header Host $host;
}
~~~

At the **first edge**, `$remote_addr` is the actual peer observed by Nginx, so this example intentionally avoids `$proxy_add_x_forwarded_for` to prevent keeping spoofed Internet XFF values. For an **internal proxy sitting behind an already-sanitized edge**, appending the peer address can be appropriate, provided inbound connections are restricted to the edge and the entire chain is tested.

Behind CDNs or managed load balancers, `$remote_addr` may be the CDN IP rather than the real client. In that scenario, use the provider's *verified* upstream-identification mechanism and an IP allowlist; never blindly replace `$remote_addr` with `$http_x_forwarded_for`.

## 9. Hands-On: Observing Headers at the Backend

Test in a **local/lab** environment before deploying production policies. The goal is to observe the headers **actually sent to the backend**, not just what the client sent to the gateway.

### 9.1. WebFlux Echo Backend

Create a Spring Boot application with `spring-boot-starter-webflux`, listening on `localhost:9091`:

~~~yaml
# Backend src/main/resources/application.yml
server:
  port: 9091
~~~

Place the main class and controller in package `demo.echo`:

~~~java
package demo.echo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EchoApplication {
    public static void main(String[] args) {
        SpringApplication.run(EchoApplication.class, args);
    }
}
~~~

~~~java
package demo.echo;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EchoController {

    @GetMapping("/echo/{id}")
    public Map<String, Object> inspect(@PathVariable String id,
                                       ServerHttpRequest request) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", id);
        result.put("uri", request.getURI().toString());
        result.put("path", request.getPath().value());
        result.put("remoteAddress",
                String.valueOf(request.getRemoteAddress()));
        result.put("forwarded",
                request.getHeaders().getFirst("Forwarded"));
        result.put("xff",
                request.getHeaders().getFirst("X-Forwarded-For"));
        result.put("xfProto",
                request.getHeaders().getFirst("X-Forwarded-Proto"));
        result.put("xfHost",
                request.getHeaders().getFirst("X-Forwarded-Host"));
        result.put("xfPrefix",
                request.getHeaders().getFirst("X-Forwarded-Prefix"));
        return result;
    }
}
~~~

This is a **diagnostic** endpoint: never expose real users' forwarded headers and remote addresses to the public Internet. Use it only in isolated test environments and remove or secure it before production deployment.

### 9.2. Gateway Route to Backend

Example route using the **Gateway Server WebFlux 5.x** namespace:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: echo-headers
              uri: http://localhost:9091
              predicates:
                - Path=/api/echo/**
              filters:
                - StripPrefix=1
                - AddResponseHeader=X-Lab-Route, echo-headers
~~~

In WebFlux 4.2/4.3, place the `routes` list under `spring.cloud.gateway.routes`. Pair it with **a matching `trusted-proxies` configuration** if your real setup has a trusted reverse proxy in front, as shown in section 6.

When a client calls `/api/echo/42`, the backend receives `/echo/42`. `X-Lab-Route` merely tags the response as having passed through the lab route; it does not prove forwarded headers were trusted.

Start the backend and gateway in two terminals from their respective project directories (e.g., via Maven Wrapper):

~~~bash
./mvnw spring-boot:run
~~~

In Windows PowerShell, use `mvnw.cmd spring-boot:run`. These are hands-on instructions; this article does not claim to have executed the applications.

### 9.3. Comparing Direct Requests vs. Requests Through a Trusted Edge

Call the backend directly:

~~~bash
curl -i "http://localhost:9091/echo/42"
~~~

Call through the lab gateway:

~~~bash
curl -i "http://localhost:8080/api/echo/42"
~~~

If a separate ingress/WAF is deployed, test via **that proxy's public address** (deployed with valid TLS):

~~~bash
curl -i "https://api.example.test/api/echo/42"
~~~

When routed through a properly configured edge, the backend **may** see `X-Forwarded-For` containing the verified IP chain and `X-Forwarded-Proto: https`; exact output depends on proxy rules, gateway version, trust regex, and whether the backend itself consumes forwarded headers. Never assume specific values solely because `curl` returned `200`.

### 9.4. Testing Spoofed Client Headers

Run only against your own test gateway:

~~~bash
curl -i "http://localhost:8080/api/echo/42" \
  -H "Forwarded: for=203.0.113.99;proto=https;host=attacker.example" \
  -H "X-Forwarded-For: 203.0.113.99" \
  -H "X-Forwarded-Proto: https" \
  -H "X-Forwarded-Host: attacker.example"
~~~

**Security expectation:** self-declared values must never become trusted IPs, schemes, or hosts for access policies or backend-generated URLs. Header behavior can differ by version/configuration; inspect both echo output and proxy/gateway logs. If the backend sees spoofed values as trusted metadata, fix edge sanitization, bypass paths, forwarded-input settings, or trusted proxies.

**Do not "fix" missing headers by setting `trusted-proxies: '.*'`.** Overly broad regexes reopen the very risks that security patches were designed to close.

### 9.5. Two-Way Verification Table

| Scenario | What to observe | Common mistake |
| --- | --- | --- |
| Client → edge over HTTPS | Edge knows real client scheme and allowlisted Host | Backend builds `http://...` links by trusting internal scheme |
| Client attempts spoofed `Forwarded`/XFF | Edge strips self-declared values | Client controls IP or Host seen by backend |
| Edge → gateway | Gateway accepts connections only from permitted proxies | Public port exists bypassing the ingress |
| Gateway → backend | Headers seen by backend match `HttpHeadersFilters` policy | Headers vanish after patch upgrade or append incorrectly |
| Path rewrite at ingress/gateway | `X-Forwarded-Prefix` and final path do not conflict | Redirect doubles prefix segments |
| Generating `301`/`302` or absolute URLs | `Location` uses valid public scheme/host | Open redirect / host header injection |
| Using IP for rate limiting or routing | Normalized IP from clear origin | Multiple clients collapsed into proxy IP or attacker rotates key |
| Backend returns `4xx`/`5xx` | Separate Gateway rejections from backend errors | Confusing auth/rate-limiter error with XFF issue |

## 10. Common Design Mistakes

### 10.1. Trusting the Leftmost IP in X-Forwarded-For

Proxy docs often refer to the leftmost entry as "client IP," yet an attacker can prepend entries to the front of the header. Only extract an address after controlling every participating proxy and enforcing a proper trust model. With `XForwardedRemoteAddr` predicates or `XForwardedRemoteAddressResolver.maxTrustedIndex(n)`, understand exactly which address they pick—and remember they **do not** prove that address was authenticated.

### 10.2. Confusing Route Predicates with Header Trust Mechanisms

`Path`, `Host`, `RemoteAddr`, and `XForwardedRemoteAddr` decide whether a route matches. `trusted-proxies` governs Gateway forwarded-header handling. Neither replaces authorization, NetworkPolicies, or WAF rules. A broad fallback route might still catch requests that fail an IP-allowlisted route; audit all routes and security policies together.

### 10.3. Enabling Multiple Forwarded-Header Processing Layers at Once

For example, the edge already builds `Forwarded`, the Gateway enables `ForwardedHeaderTransformer`, and `HttpHeadersFilters` also appends headers downstream. Without tracing the full header lifecycle, metadata can be duplicated, dropped, or diverge between RFC `Forwarded` and XFF. Clearly assign **which component writes the source value**, which reads it, which forwards it, and which strips it.

### 10.4. Treating X-Forwarded-Proto as Proof of TLS

A client-sent `X-Forwarded-Proto: https` header **does not prove** the client connected over HTTPS. TLS must be verified at the TLS termination point; the Gateway → backend hop needs its own HTTPS/mTLS if transport protection is required. When building redirect URLs or secure cookies, rely only on metadata validated across the trust boundary.

### 10.5. Logging Every Header for Diagnostics

Access tokens, cookies, and sensitive identifiers can leak into logs. Record only essential fields such as route ID, trace ID, status, latency, verified IP (per data-protection policies), proxy hop count, and origin-check results. Never expose internal echo endpoints in production.

## 11. Production Readiness Checklist

- [ ] Confirmed exact **Spring Cloud Gateway Server WebFlux** variant and version, especially `trusted-proxies` and `x-forwarded.*` namespaces.
- [ ] Running a Spring Cloud Gateway branch patched for forwarded-header security advisories.
- [ ] Mapped the full path: client → CDN/WAF → load balancer → ingress → gateway → microservice.
- [ ] Verified no direct path exists from the Internet to the gateway bypassing the trust boundary.
- [ ] First public proxy strips **both** client-sent `Forwarded` and `X-Forwarded-*`.
- [ ] Edge builds headers from real peer IP and TLS/Host; `Host` is checked against an allowlist.
- [ ] Internal proxies accept traffic only from prior trusted hops and append consistently.
- [ ] `trusted-proxies` uses a properly namespaced Java regex, never trusts all addresses, and is tested with real requests.
- [ ] Determined explicitly whether Spring Boot/WebFlux `ForwardedHeaderTransformer` is needed; tested if using `framework`, `native`, or `removeOnly`.
- [ ] Tested both `Forwarded` and XFF headers, including spoofed, missing, repeated, multi-hop, and IPv6 cases.
- [ ] Verified route predicates, rate limiters, redirects, absolute links, and logs rely only on **verified data**, not arbitrary headers.
- [ ] Enforced authentication/authorization at Gateway and backend by responsibility; IP serves only as an auxiliary signal.
- [ ] Observed requests at both gateway **and** backend without logging tokens, cookies, or sensitive data.

## 12. Version-Specific References

Official resources to check syntax and limits:

1. [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239.html): `for`, `by`, `host`, `proto`, multi-hop syntax, and escaping.
2. [Spring Cloud Gateway Server WebFlux 5.x — HttpHeadersFilters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/httpheadersfilters.html): `Forwarded`, `XForwarded`, `RemoveHopByHop`, and new namespaces.
3. [Spring Cloud Gateway Server WebFlux 4.3.x — HttpHeadersFilters](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/httpheadersfilters.html): `server.webflux.trusted-proxies` and X-Forwarded options.
4. [Spring Cloud Gateway 4.2.x — HttpHeadersFilters](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/httpheadersfilters.html): `spring.cloud.gateway.trusted-proxies` and legacy prefix.
5. [Spring Framework WebFlux — ForwardedHeaderTransformer](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): forwarded input, remove-only mode, and security boundaries.
6. [Spring Boot — Running Behind a Front-end Proxy](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): forwarding strategy in Boot 3.x.
7. [Spring Security Advisory CVE-2025-41235](https://spring.io/security/cve-2025-41235/): affected versions and trusted-proxy requirements in patched releases.

**Key takeaway:** `Forwarded` and `X-Forwarded-*` help services understand pre-proxy request context, but **they are trustworthy only when created or sanitized at a proxy inside a controlled trust boundary**. In Spring Cloud Gateway, separate WebFlux's **inbound** header processing from `HttpHeadersFilters` **outbound to the backend**, use the right properties for your version, test for spoofing across the entire chain, and never use these headers as substitutes for authentication or authorization.
