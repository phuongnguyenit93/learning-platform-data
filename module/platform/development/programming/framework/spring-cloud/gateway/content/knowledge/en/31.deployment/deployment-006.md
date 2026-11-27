# Trusted Proxies and Public Paths Behind Multiple Proxy Layers

## 1. Why Does the Gateway Need to Know the Public URL?

In a microservices architecture, **Spring Cloud Gateway** serves as the entrypoint responsible for route predicates, filter chains, path/header transformations, service discovery, authentication, rate limiting, circuit breakers, retries, TLS, and request observability. In real deployments, the Gateway rarely terminates raw TCP/TLS connections directly from the Internet: CDNs, WAFs, load balancers, ingresses, or reverse proxies sit in front of it.

For example, a user requests:

~~~http
GET https://api.example.test/platform/api/orders/42?lang=vi
~~~

Yet each hop sees a different path and scheme:

~~~text
Browser
  https://api.example.test/platform/api/orders/42
       |
       v
CDN / WAF
  public host = api.example.test; TLS from client
       |
       v
Ingress / Nginx
  strip /platform
       |
       v
Spring Cloud Gateway WebFlux
  http://edge-gateway:8080/api/orders/42
  Path=/api/orders/**; StripPrefix=1
       |
       v
order-service
  http://order-service:8081/orders/42
~~~

If the Gateway and backends only see internal addresses, the system may emit `Location: http://order-service:8081/orders/42` instead of the public URL, redirect from HTTPS down to HTTP, generate broken OAuth2/OIDC callbacks, or set cookie Paths that do not match the public prefix. If the Gateway trusts client-supplied `Forwarded`/`X-Forwarded-*` headers, the bug can escalate into **IP allowlist/rate-limit bypasses, host-header poisoning, or open redirects**.

This lesson, **"Trusted Proxies and Public Paths Behind Multiple Proxy Layers"**, from the **Deployment** chapter of the **SPRING_CLOUD_GATEWAY** module, explains how to govern these concerns as a **per-hop contract** rather than a disconnected list of settings.

**Learning objectives:**

1. Map proxy hops and distinguish client-facing URLs from URLs seen by the Gateway and backends.
2. Understand `Host`, `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port`, and `X-Forwarded-Prefix`.
3. Place the trust boundary at the right proxy, stripping client-spoofed headers.
4. Configure Gateway WebFlux `trusted-proxies` in the right version-specific namespace, distinguishing it from Spring Boot `server.forward-headers-strategy`.
5. Solve prefix stripping, public redirects, `Location`, cookies, OAuth callbacks, and forwarded client IPs.
6. Test the full chain and prevent regressions across security patch upgrades.

> **Scope:** Primary examples use **Spring Cloud Gateway Server WebFlux**. Gateway Server Web MVC runs on Servlet/WebMvc.fn with conceptually similar filters/properties under different namespaces and Java APIs. When switching runtimes, never just swap the starter name and copy reactive config verbatim.

## 2. Different Views of the Same Request

| Perspective | Scheme / Host | Path | Role |
| --- | --- | --- | --- |
| Client | `https://api.example.test` | `/platform/api/orders/42` | **Public URL**, must be used in links |
| CDN/WAF | Validated public origin | `/platform/api/orders/42` | Internet boundary |
| Ingress receives | Depends on routing/TLS topology | `/platform/api/orders/42` | Strips `/platform` |
| Gateway receives | `http://edge-gateway:8080` | `/api/orders/42` | Route predicate |
| Backend receives | `http://order-service:8081` | `/orders/42` | Business handler |
| Client receives redirect | `https://api.example.test` | `/platform/api/orders/42` | Never leaks internal host/path |

**Separate three concerns:** the public address, the actual request path at each hop, and the response URL returned to the client. Simply receiving `X-Forwarded-Prefix` does not mean the Gateway automatically rewrites all response links per the table above.

### 2.1. TLS Per Hop

~~~text
Client --TLS A--> CDN --TLS B or HTTP--> Ingress
       --HTTP/TLS C--> Gateway --HTTP/TLS D--> Backend
~~~

`X-Forwarded-Proto: https` typically describes the outer scheme; it **does not prove** Gateway → backend traffic is encrypted. If internal TLS/mTLS is required, configure SSL trust, certificate verification, SNI, and service identities separately. Inbound HTTPS does not automatically secure outbound HTTPS.

### 2.2. User-Facing URL vs Transport URL

The client sees `https://api.example.test`, while Gateway's Reactor Netty receives a socket from ingress and sees `http://10.42.0.10:8080`. Both views can be right for their respective purposes. Mistakes begin when the app builds public URLs from transport scheme/host, or conversely uses an unvalidated public host to pick a backend target.

## 3. Two Header Families Describing the Proxy Chain

### 3.1. RFC 7239 Forwarded

Example:

~~~http
Forwarded: for=203.0.113.44;proto=https;host=api.example.test
~~~

| Parameter | Common meaning |
| --- | --- |
| `for` | Address identity of the client or proxy prior to the current hop |
| `proto` | External scheme observed by the proxy |
| `host` | Host of the forwarded request |
| `by` | Proxy address/interface handling the hop, if enabled |

Across multiple hops, `Forwarded` can contain comma-separated elements:

~~~http
Forwarded: for=203.0.113.44;proto=https;host=api.example.test, for=198.51.100.10;proto=https;host=api.example.test
~~~

The RFC allows quoted strings, bracketed IPv6, `unknown`, and obfuscated identifiers. Do not write a naive `split(",")` parser and assume it handles every format.

### 3.2. X-Forwarded-* Is More Common Across Infrastructure

~~~http
Host: edge-gateway.internal
X-Forwarded-For: 203.0.113.44, 198.51.100.10
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.test
X-Forwarded-Port: 443
X-Forwarded-Prefix: /platform
~~~

| Header | Purpose | Risk if blindly trusted |
| --- | --- | --- |
| `X-Forwarded-For` | Client/proxy IP chain | Spoofed IP to bypass quotas/allowlists |
| `X-Forwarded-Proto` | Public scheme | HTTP downgrade redirects, broken Secure cookies |
| `X-Forwarded-Host` | Public host | Host poisoning, open redirects |
| `X-Forwarded-Port` | Public port | Links leaking `:8080`, scheme/port mismatch |
| `X-Forwarded-Prefix` | Prefix stripped at a prior hop | 404s, double prefixes, or path injection |
| `Forwarded` | Standardized combined metadata | Parsing/precedence conflicts with X-Forwarded |

Headers are **data provided by an HTTP sender**, not credentials. Internet clients can inject any of the values above directly.

### 3.3. Current Host and X-Forwarded-Host Are Not Identical

- `Host` can be the current HTTP hop's authority or the preserved host per proxy configuration.
- `X-Forwarded-Host` intends to represent the original/public authority.
- Gateway's HTTP client may set `Host` from the backend target URI unless a preserve/set host filter runs.
- Even if a client-supplied `Host=evil.example` matches a Host predicate, **that is not user authentication**.

## 4. Trust Boundary: Sanitize Before Trusting

### 4.1. Core Rule

The **first proxy inside the trusted domain** must be designed to:

1. Accept requests from the Internet or a lower-trust source.
2. **Strip or overwrite both `Forwarded` and the `X-Forwarded-*` family that clients might supply.**
3. Recompute scheme/host/port/prefix from its TLS listener, validated hostname, route mapping, and actual remote peer.
4. Forward normalized metadata only to authorized downstream hops.
5. Enforce header size limits, hop limits, and malformed chain handling.
6. Enforce host allowlists, network ACLs, and TLS policies independently.

Stripping only `Forwarded` while leaving `X-Forwarded-Host: evil.example`, or vice versa, leaves the same attack surface open. Both Spring Framework and Spring Security emphasize sanitizing **both header families** at the trusted boundary.

### 4.2. Spoofing Client Example

~~~http
GET /login HTTP/1.1
Host: api.example.test
Forwarded: for=10.0.0.1;proto=http;host=evil.example
X-Forwarded-Host: evil.example
X-Forwarded-Proto: http
X-Forwarded-Prefix: /admin
~~~

If the app builds callbacks/redirects from unverified values, it can emit:

~~~http
HTTP/1.1 302 Found
Location: http://evil.example/admin/oauth2/callback
~~~

This is a **dangerous anti-pattern**. Valid output must use an allowlisted public origin/prefix or reject the request. Never validate solely by checking HTTP 200; assert `Location`, backend-received headers, derived client IP, and security decisions.

### 4.3. Three Complementary Layers of Defense

| Layer | Purpose | Cannot replace |
| --- | --- | --- |
| Network ACL / Kubernetes NetworkPolicy / SecurityGroup | Permit only ingress to connect to Gateway | Does not sanitize headers |
| Ingress/CDN header sanitization | Strip spoofed headers, generate trusted metadata | Does not replace backend auth |
| Gateway/Spring trusted forwarded processing | Consume/forward trusted data cleanly | Does not block direct NodePort bypasses |

**No property inside Gateway turns port 8080 into a private network.** An exposed NodePort or secondary public LoadBalancer alongside ingress gives attackers a bypass path to send `X-Forwarded-Host` straight to Gateway.

### 4.4. Source-Based Trust Definition

A trusted chain might look like:

~~~text
Client -> CDN/WAF -> Ingress (sanitize) -> Gateway (private) -> Service
~~~

Yet if the CDN is trusted while ingress allows traffic bypassing the CDN, consuming client IP headers from the CDN **without verifying the peer is actually the CDN** opens a vulnerability. Trust requires both network/source identity and a header contract.

## 5. Spring Cloud Gateway WebFlux `trusted-proxies`

### 5.1. 4.3/5.x Line Using the New Namespace

Gateway Server WebFlux 5.x docs list the property:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          trusted-proxies: '^10[.]42[.]0[.](?:10|11)$'
~~~

This is a **Java regular expression** matching two proxy identities `10.42.0.10` and `10.42.0.11`—not a CIDR. It **does not whitelist socket remote IPs on its own** and does not replace private networking/ACLs. If forwarded metadata includes ports, IPv6, quotes, or other formatting, verify how your Gateway version's matcher evaluates the regex and adjust accordingly.

The `HttpHeadersFilters` docs describe `trusted-proxies` as required to enable `Forwarded` and `X-Forwarded-*` processing in outbound HTTP header filters. Related options include:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          x-forwarded:
            for-enabled: true
            host-enabled: true
            proto-enabled: true
            port-enabled: true
            prefix-enabled: true
            for-append: true
            host-append: true
            proto-append: true
            port-append: true
            prefix-append: true
~~~

The snippet above is an **illustrative table of knobs**, not a copy-paste production baseline. In some versions these flags default to true, yet patches/security advisories can alter defaults and filter activation rules. **Appending is unsafe if prior entries in the chain include unsanitized client-supplied values.**

Overall toggle flags listed in configprops:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          forwarded:
            enabled: true
          x-forwarded:
            enabled: true
~~~

These are feature flags, **not instructions to trust every request header**. Use only with a trusted proxy chain and verify patch levels.

### 5.2. 4.1/4.2 or Pre-Migration 4.3 Namespace

In many earlier releases:

~~~yaml
spring:
  cloud:
    gateway:
      trusted-proxies: '^10[.]42[.]0[.](?:10|11)$'
      x-forwarded:
        for-enabled: true
        host-enabled: true
        proto-enabled: true
        prefix-enabled: true
~~~

| Config line | Trusted proxies property |
| --- | --- |
| Gateway Server WebFlux 4.1/4.2 | `spring.cloud.gateway.trusted-proxies` |
| Gateway 4.3 migration phase | Whichever namespace the running artifact/version supports |
| Gateway Server WebFlux 5.x | `spring.cloud.gateway.server.webflux.trusted-proxies` |
| Gateway Server Web MVC 5.x | `spring.cloud.gateway.server.webmvc.trusted-proxies` |

Do not define both property/route namespaces side by side "just to be safe." That can produce active config different from what operators think is enabled.

### 5.3. Regex Is Not CIDR

~~~yaml
# ANTI-PATTERN: do not write CIDR strings assuming Java regex understands subnets.
trusted-proxies: '10.42.0.0/24'

# ANTI-PATTERN: overly broad, defeats the trust boundary.
trusted-proxies: '.*'
~~~

Use a regex tightly scoping the exact proxy identities appearing in forwarded headers, lock down direct network access with separate ACLs, and write integration tests matching real header formats.

## 6. Published Spring Security Advisories

### 6.1. CVE-2025-41235, Published 2025-05-27

Spring disclosed **Gateway Server forwards headers from untrusted proxies**. Listed affected ranges included:

- 4.2.0–4.2.2; OSS fix 4.2.3.
- 4.1.0–4.1.7; OSS fix 4.1.8.
- Certain 4.0.x and 3.1.x branches per advisory.

The fix changed default forwarded-header behavior; enabling it requires configuring appropriate trusted proxies. Never treat setting a regex as equivalent to applying the security patch.

Source: [Spring Security Advisory CVE-2025-41235](https://spring.io/security/cve-2025-41235/).

### 6.2. CVE-2026-47825, Published 2026-06-11

Spring disclosed **forwarding `X-Forwarded-For`/`Forwarded` from untrusted proxies in certain configurations**, affecting both Server WebFlux **and** WebMVC.

| Affected range per advisory | Fix listed by Spring |
| --- | --- |
| 5.0.0–5.0.1 | 5.0.2 (OSS) |
| 4.3.0–4.3.4 | 4.3.5 (OSS) |
| 4.2.0–4.2.8 | 4.2.9 (Enterprise Support) |
| 4.1.0–4.1.12 | 4.1.13 (Enterprise Support) |
| Older branches | Consult advisory and upgrade plan |

Per the advisory, the fix **disabled Gateway Server WebFlux's `NettyServerCustomizer` by default**. If an application must re-enable the customizer on 5.0.x or namespace-migrated 4.3.x, the property is:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpserver:
            customizer-enabled: true
~~~

**Do not enable this option by default.** It is only for restoring functionality after understanding the impact, threat modeling, and testing. For legacy namespaces, the advisory lists `spring.cloud.gateway.httpserver.customizer-enabled`; check your installed version first.

Source: [Spring Security Advisory CVE-2026-47825](https://spring.io/security/cve-2026-47825/).

**Operational lesson:** upgrade to supported patched releases, re-verify forwarding behavior, and run regression tests after upgrading. Security patches and advisories are an integral part of deployment, not optional footnotes.

## 7. Spring Boot `forward-headers-strategy` at the Inbound Layer

Gateway `HttpHeadersFilters` process headers **before outbound HTTP calls to backends**. Spring Boot/Spring Framework also has a mechanism to **read forwarded metadata as requests enter the Gateway itself**.

### 7.1. Options in Boot 3.x

| `server.forward-headers-strategy` value | Purpose |
| --- | --- |
| `NONE` | Do not apply forwarded metadata via Boot auto-configuration |
| `NATIVE` | Delegate to the HTTP server's native mechanism |
| `FRAMEWORK` | Use Spring Framework—for WebFlux, `ForwardedHeaderTransformer` |

Example strictly inside an environment where **trusted ingress already sanitizes headers**:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

`ForwardedHeaderTransformer` adjusts scheme, host, port, and prefix visible to Spring WebFlux, and processes/strips consumed headers. In Servlet MVC, the counterpart is `ForwardedHeaderFilter` or Tomcat/Jetty native configuration.

**If the Gateway's public port is reachable directly by Internet clients sending arbitrary forwarded headers, never enable `FRAMEWORK` and assume it is safe.** Enforce a network boundary.

### 7.2. Inbound Transformer Differs from Outbound Filters

~~~text
Ingress HTTP request
  -> Boot/Framework forwarded handling:
       interprets effective scheme/host/port/prefix
  -> Gateway route predicate/filter chain:
       selects route, strips/rewrites path
  -> Gateway HttpHeadersFilters:
       generates/adjusts outbound forwarded headers
  -> HTTP client to backend
~~~

Once Spring Framework applies and strips incoming headers, Gateway may generate outbound headers from the transformed request. If both ingress and Gateway prepend prefixes or append conflicting chains, you easily get double prefixes, wrong proto, or inconsistent headers.

Design:

1. Identify which proxy generates and sanitizes headers.
2. Decide whether Boot should alter the effective request URI.
3. Decide whether Gateway should forward metadata downstream to backends.
4. Test `request.getURI()`, route matching, and backend-recorded headers on your exact patch level.
5. Do not register a custom transformer and assume default auto-configuration still behaves unchanged.

### 7.3. `removeOnly` When Headers Should Never Be Applied

Spring WebFlux provides `ForwardedHeaderTransformer.setRemoveOnly(true)`, which **strips headers without applying them**:

~~~java
package example.gateway.deployment;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.adapter.ForwardedHeaderTransformer;

@Configuration
class DiscardForwardedHeaders {

    @Bean
    ForwardedHeaderTransformer forwardedHeaderTransformer() {
        ForwardedHeaderTransformer transformer =
                new ForwardedHeaderTransformer();
        transformer.setRemoveOnly(true);
        return transformer;
    }
}
~~~

This is an **alternative policy**, not something to stack alongside `FRAMEWORK` for "extra security." If your app needs to reconstruct the public origin from trusted headers, `removeOnly` intentionally **discards** that information. Pick one clear policy instead of layering conflicting mechanisms.

### 7.4. Additional Points to Check in Spring Boot 4.x

Spring Boot 4.x documentation adds `server.request.header.forwarded.*` properties and prefix-related options. Do not assume all Boot 3.x properties/behaviors carry over unchanged across major versions. Consult the docs for **Running Behind a Front-end Proxy Server** and inspect effective configuration at startup.

## 8. Example: Nginx at the TLS Edge with No Front CDN

### 8.1. Contract

In this example, **Nginx is the first public proxy**:

- Public: `https://api.example.test/platform/api/orders/42`.
- Nginx strips `/platform` and sends `http://edge-gateway:8080/api/orders/42`.
- Gateway strips `/api` and calls `http://order-service:8081/orders/42`.
- Nginx is the authoritative source of forwarded headers trusted by the app.

### 8.2. Illustrative Nginx Config

~~~nginx
# SIMPLIFIED FOR LAB; omits TLS hardening, rate limits,
# security headers, host validation, logging/monitoring, and timeouts.
server {
    listen 443 ssl;
    server_name api.example.test;

    ssl_certificate     /etc/nginx/certs/server.crt;
    ssl_certificate_key /etc/nginx/certs/server.key;

    location /platform/ {
        # Trailing / on proxy_pass tells Nginx to replace /platform/ with /.
        proxy_pass http://edge-gateway:8080/;
        proxy_http_version 1.1;

        # Prevent clients from supplying Forwarded.
        proxy_set_header Forwarded "";

        # Overwrite metadata using facts known at the public edge.
        proxy_set_header Host api.example.test;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host api.example.test;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-Prefix /platform;
    }
}
~~~

**Important caveats:**

- Do not treat this snippet as a **complete production Nginx config**. Add TLS policies, default-host rejection, trusted networking, comprehensive header allowlisting/sanitization, timeouts, and limits.
- Nginx forwards unlisted headers by default. Audit any custom forwarded-style headers if backends consume them.
- `$remote_addr` is the TCP peer seen by Nginx. If a CDN sits in front, `$remote_addr` may be the **CDN address**—never blindly treat it as the original client IP.
- `X-Forwarded-Prefix` is trustworthy here because Nginx **sets a fixed value** from its own mapping rather than echoing client input.
- `proxy_pass http://edge-gateway:8080/;` with a trailing slash inside `location /platform/` alters the prefix per Nginx location rules. Whenever you adjust slashes, re-run path tests.

## 9. Gateway Route Matching the Same Public Mapping

### 9.1. Gateway Server WebFlux 5.x

~~~yaml
server:
  port: 8080
  forward-headers-strategy: framework

spring:
  application:
    name: edge-gateway
  cloud:
    gateway:
      server:
        webflux:
          trusted-proxies: '^10[.]42[.]0[.](?:10|11)$'
          routes:
            - id: orders-api
              uri: http://order-service:8081
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
~~~

Expected flow:

~~~text
Client:  GET /platform/api/orders/42  [public HTTPS]
Nginx:   GET /api/orders/42           [internal HTTP]
Gateway: route orders-api
Backend: GET /orders/42               [internal HTTP]
~~~

The IP regex here is strictly a **placeholder** for real proxy identities; it does not configure Nginx IPs or routing. Because Boot's forwarded-header handling can alter request URI/prefix before route predicates run, test the **actual received route path** on your running version. Never treat YAML + Nginx snippets on paper as a passing test before executing them.

### 9.2. Gateway WebFlux 4.x Using the Legacy Namespace

~~~yaml
server:
  port: 8080
  forward-headers-strategy: framework

spring:
  cloud:
    gateway:
      trusted-proxies: '^10[.]42[.]0[.](?:10|11)$'
      routes:
        - id: orders-api
          uri: http://order-service:8081
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
~~~

These two configs are **mutually exclusive alternatives**. In 4.3 there was a namespace migration depending on minor version; verify runtime property binding before choosing.

### 9.3. Backend URI Does Not Prove Service Discovery or TLS

`uri: http://order-service:8081` targets a concrete HTTP endpoint. If using `lb://ORDER-SERVICE`, LoadBalancer needs real service instances plus matching scheme/security policies. Forwarded headers **do not** replace mTLS or downstream authorization.

## 10. `X-Forwarded-Prefix` and Three Distinct Transformations

### 10.1. Ingress Rewrite, Gateway Rewrite, and URL Reconstruction

| Mechanism | Effect |
| --- | --- |
| Nginx `proxy_pass` / ingress rewrite | Changes the path Gateway **actually receives** |
| Gateway `StripPrefix` / `RewritePath` | Changes the path the backend **actually receives** |
| `X-Forwarded-Prefix` | Metadata stating which public prefix was stripped upstream |
| Response `Location` rewrite / public base URL | Determines links/redirects the client sees |

`X-Forwarded-Prefix` **does not automatically prepend the prefix to every outbound request or redirect**.

### 10.2. Double Stripping

~~~text
Public:               /platform/api/orders/42
Ingress accidentally: /platform/api  -> /orders/42
Gateway still has:    Path=/api/orders/**  -> no match
~~~

Or if Gateway has a broader route while keeping `StripPrefix=1`, `/orders/42` turns into `/42`, causing a backend 404.

Fix: in the sample topology, ingress **only strips `/platform`**, and Gateway **only strips `/api`**.

### 10.3. Double Prefixing

~~~text
Backend already emitted: /platform/api/orders/42
Gateway mistakenly adds: /platform/platform/api/orders/42
~~~

Never blindly prepend `X-Forwarded-Prefix` to every link. Account for relative vs absolute redirects, encoded paths, empty prefixes, double slashes, multiple routes, and earlier hop rewrites.

### 10.4. Maintain a Path Table Across Every Hop Boundary

| Client | Nginx → Gateway | Gateway → backend |
| --- | --- | --- |
| `/platform/api/orders/42` | `/api/orders/42` | `/orders/42` |
| `/platform/api/orders/42?x=1` | `/api/orders/42?x=1` | `/orders/42?x=1` |
| `/platform/api/orders/42/items` | `/api/orders/42/items` | `/orders/42/items` |
| `/platform/api/orders-old/42` | `/api/orders-old/42` | Does not match orders route |
| `/platform/platform/api/orders/42` | Violates contract | Do not "auto-fix" via double-strip |

These values are **test expectations**, not observed execution logs. For encoded slashes, dot segments, and Unicode, proxies and frameworks may normalize at different stages; verify on the real topology.

## 11. When a CDN Sits in Front of Ingress

~~~mermaid
flowchart LR
    C["Client<br/>203.0.113.44"] --> CDN["CDN/WAF<br/>198.51.100.10"]
    CDN --> ING["Ingress<br/>192.0.2.20"]
    ING --> G["Spring Cloud Gateway"]
    G --> O["order-service"]
~~~

These addresses belong to **documentation example IP ranges**, not live IPs.

### 11.1. Why Might `$remote_addr` Not Be the Client IP?

When a CDN connects to Nginx, `$remote_addr` seen by Nginx is `198.51.100.10`, not `203.0.113.44`. Using Section 8's config behind a CDN **loses the original client IP**, though it still prevents trusting spoofed client XFF headers.

If the original client IP is needed:

1. Restrict ingress connections strictly to verified CDN IP ranges.
2. Identify the exact header where the CDN provider writes the client IP.
3. Accept that header only when the **transport peer** belongs to the allowed CDN IP set.
4. Configure Nginx's real-IP/trusted-proxy module per version and keep IP ranges updated.
5. After resolving, emit a clean `X-Forwarded-For` from one authoritative owner.
6. Test both CDN-routed traffic and direct CDN-bypass attempts.

**Never configure `set_real_ip_from 0.0.0.0/0` or trust XFF from arbitrary peers.**

### 11.2. Appending Does Not Sanitize Spoofed Input

Anti-pattern:

~~~http
# Attacker sends:
X-Forwarded-For: 10.0.0.1

# A proxy merely appends:
X-Forwarded-For: 10.0.0.1, 203.0.113.44
~~~

An app reading the first element mistakes `10.0.0.1` for the client. **Appending is safe only after untrusted prior elements are verified or stripped.**

### 11.3. `Forwarded` and `X-Forwarded-*` Can Conflict

~~~http
Forwarded: for=203.0.113.44;proto=https;host=api.example.test
X-Forwarded-For: 10.0.0.1
X-Forwarded-Proto: http
X-Forwarded-Host: evil.example
~~~

There is no universal "RFC header always wins" rule across all implementations. One service may prefer `Forwarded` while another reads `X-Forwarded-*`. Normalize **both families at the edge**; if one family is unused, strip it per contract.

## 12. Public Redirects and `Location` Responses

### 12.1. Wrong Scheme, Host, Port, or Path Are All Bugs

Backend returns:

~~~http
HTTP/1.1 302 Found
Location: http://order-service:8081/orders/42
~~~

Yet the client must receive:

~~~http
HTTP/1.1 302 Found
Location: https://api.example.test/platform/api/orders/42
~~~

Swapping the host alone misses `/platform/api`. Prepending the prefix alone leaves `http` instead of `https`. Reconstruct the complete **scheme + host + port + public path**.

### 12.2. `RewriteLocationResponseHeader`

Gateway Server WebFlux provides `RewriteLocationResponseHeader` to adjust `Location`, typically fixing the host and handling API versions.

Example syntax on Gateway 5.x:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-api
              uri: http://order-service:8081
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
                - RewriteLocationResponseHeader=AS_IN_REQUEST, Location, api.example.test, https?
~~~

`AS_IN_REQUEST` is the mode governing API version stripping; the host parameter replaces the Location host per filter semantics. **Do not treat this filter as a silver bullet for all schemes/prefixes**: it does not promise to reconstruct `/platform/api` in every response or force HTTP to HTTPS across every topology. Test actual outputs; if needed, configure canonical public URLs at the backend or add a verified response rewrite.

### 12.3. Relative `Location` Can Still Miss the Prefix

~~~http
Location: /orders/42
~~~

Browsers resolve this to `https://api.example.test/orders/42` **without adding `/platform/api`**. If the contract expects a relative Location, include the public path:

~~~http
Location: /platform/api/orders/42
~~~

### 12.4. Redirect Loops and HTTP Methods

- An internal Gateway receiving HTTP while the client speaks HTTPS can enter a redirect loop if the app ignores `proto=https` from a trusted proxy.
- Historically, `301/302` caused clients to downgrade POST to GET depending on user agent/semantics.
- `307/308` preserve the HTTP method.
- Tests should **disable auto-follow redirects** when checking status codes and raw `Location` headers.
- Never use an arbitrary forwarded host to construct logout, password-reset, or OAuth callback links.

## 13. What Roles Do `PreserveHostHeader` and `SetRequestHostHeader` Play?

### 13.1. Backend Host Differs from Public Host

An HTTP request traversing Gateway involves multiple authority values:

~~~text
Client Host:                 api.example.test
Ingress -> Gateway Host:     api.example.test or edge-gateway.internal
Gateway target URI host:     order-service:8081
Backend outbound Host:       per target or active Gateway filter
~~~

`PreserveHostHeader` is a Gateway WebFlux filter instructing Gateway to retain the incoming request Host per Gateway behavior. `SetRequestHostHeader` explicitly overrides the Host on outbound HTTP calls.

~~~yaml
# Mutually exclusive choices requiring review; do not enable both casually.
filters:
  - PreserveHostHeader
~~~

or:

~~~yaml
filters:
  - SetRequestHostHeader=orders.internal.example.test
~~~

**Do not equate HTTP `Host` with TLS SNI or certificate identity:** the HTTP client connects to the target URI, while truststores/SNI/hostname validation follow separate rules. Test thoroughly when backends use virtual hosts or TLS/mTLS.

### 13.2. `PreserveHostHeader` Can Increase Risk

If ingress fails to restrict `Host`, preserving `Host: evil.example` downstream can:

- Cause the backend to select the wrong virtual host.
- Cause the backend to emit absolute `Location` headers pointing to a spoofed domain.
- Break cookie `Domain` attributes.
- Corrupt OAuth2 callbacks.
- Cause cache poisoning if cache keys depend on `Host`.

Only preserve the public Host **once it has passed a host allowlist and network trust boundary**. If a backend only expects its internal target host, do not preserve.

### 13.3. A `Host` Route Predicate Is Routing, Not Identity

Example:

~~~yaml
predicates:
  - Host=api.example.test
  - Path=/api/orders/**
~~~

A client connecting directly to the Gateway can set any HTTP `Host` header. A `Host` predicate does not replace OAuth2/JWT authentication, ownership checks, or mTLS service identity.

## 14. Cookies, Sessions, and OAuth2/OIDC Redirect URIs

### 14.1. Cookie `Path` Must Align with the Public Path

Backend returns:

~~~http
Set-Cookie: SID=demo; Path=/orders; HttpOnly; SameSite=Lax
~~~

The browser accesses `https://api.example.test/platform/api/orders/42`. With `Path=/orders`, the browser **will not send the cookie** on public requests. Either a response rewrite or a public-base-path-aware backend must emit the contracted `Path`.

| Cookie attribute | Verification |
| --- | --- |
| `Domain` | Matches public domain? No accidental leak to sibling domains? |
| `Path` | Matches public path so the browser resends it? |
| `Secure` | Enabled on sensitive cookies over HTTPS? |
| `HttpOnly` | Prevents JavaScript from reading session cookies? |
| `SameSite` | Compatible with cross-site SSO/frontend flows? |
| `Max-Age`/`Expires` | Matches session/token lifecycle? |

`X-Forwarded-Proto=https` does not keep cookies safe if the server trusts untrusted headers or inbound HTTPS is not enforced.

### 14.2. OAuth2/OIDC `redirect_uri`

A redirect URI registered at the IdP might be:

~~~text
https://api.example.test/platform/login/oauth2/code/company
~~~

If Gateway/backend constructs callbacks from the internal request URI, it generates `http://edge-gateway:8080/login/oauth2/code/company`, which the IdP rejects. Conversely, reading an attacker-spoofed `X-Forwarded-Host` redirects callbacks to an unapproved domain.

Design:

1. Construct URLs strictly from a trusted configured public base URL or headers normalized by a trusted proxy.
2. Register exact redirect URIs with the IdP per environment.
3. Require HTTPS and validate host/scheme.
4. Test the complete login flow, `state`, session cookies, CSRF, and callback Path.
5. For multi-tenant domains, map domains from an allowlist keyed by authenticated tenant—never from arbitrary `Host` headers.
6. Never log authorization codes or access tokens in query strings/`Location` during debugging.

### 14.3. CORS and Frontends

CORS `Origin` governs cross-origin browser JavaScript, not authentication. Swagger/OpenAPI `servers` entries must also publish the public URL including its prefix. If an OpenAPI spec advertises `http://order-service:8081`, frontends try calling an unreachable internal host or hit mixed-content errors.

Before publishing docs or client SDKs, test:

- Public OpenAPI server URL.
- Redirects from `/docs`.
- CORS preflight `OPTIONS` and credentials policy.
- Browser cookie behavior.
- Public `wss://` WebSocket upgrades if used.
- Absence of internal IPs/hosts in response bodies and headers.

## 15. `X-Forwarded-For` and Client IP: Two Different Resolvers

### 15.1. Default `RemoteAddr` Sees the TCP Peer

In Gateway WebFlux, the `RemoteAddr` route predicate inspects the request's remote address. Behind an ingress, that address is usually the **ingress IP**, not the browser IP.

Spring Cloud Gateway also provides `XForwardedRemoteAddressResolver` to extract client IPs from `X-Forwarded-For`.

### 15.2. `trustAll` Is Unsafe

~~~java
import org.springframework.cloud.gateway.support.ipresolver.XForwardedRemoteAddressResolver;

// ANTI-PATTERN: can pick the leftmost element supplied by an attacker.
XForwardedRemoteAddressResolver unsafe =
        XForwardedRemoteAddressResolver.trustAll();

// Example selecting trusted hop count; must be verified against real topology.
XForwardedRemoteAddressResolver controlled =
        XForwardedRemoteAddressResolver.maxTrustedIndex(2);
~~~

`trustAll()` picks the first element and is trivially spoofed unless XFF is sanitized. `maxTrustedIndex(n)` counts from **right to left** by index, assuming a known trusted proxy chain.

Example header:

~~~http
X-Forwarded-For: 203.0.113.44, 198.51.100.10, 192.0.2.20
~~~

| `maxTrustedIndex` | Result for example |
| --- | --- |
| `1` | `192.0.2.20` |
| `2` | `198.51.100.10` |
| `3` | `203.0.113.44` |

**Do not blindly pick 3 just because a diagram shows three proxy boxes.** Headers may be formatted differently, omit hops, or carry spoofed client entries. Inspect the exact chain produced by your real infrastructure, count actual trusted hops, and never trust the leftmost item outside policy.

### 15.3. `maxTrustedIndex` Differs from `trusted-proxies`

| Mechanism | Purpose | Input type |
| --- | --- | --- |
| `trusted-proxies` | Gates processing/forwarding trusted metadata in Gateway `HttpHeadersFilters` | Java regular expression |
| `XForwardedRemoteAddressResolver.maxTrustedIndex(n)` | Selects an IP from the XFF chain | Hop count/index |
| `RemoteAddr` | Matches remote address against a list | CIDR ranges |
| NetworkPolicy/firewall | Blocks TCP connections into Gateway | IP/network/service identity |

**Never use a resolver as a substitute for edge sanitization**, and never treat the `trusted-proxies` regex as an ACL governing allowed TCP connections.

### 15.4. IP Is Not Authentication

Even with the true client IP:

- Many users share one IP behind NAT.
- Mobile IPs shift mid-session.
- Proxy chain changes cause logs and rate-limit keys to drift.
- An IP never proves tenant membership or resource ownership.

For authenticated APIs, key rate limits on the verified principal or tenant; treat client IP purely as an auxiliary abuse-prevention signal.

## 16. Impact on Rate Limiting, Auditing, and Tracing

### 16.1. IP-Based Rate Limiting Can Be Bypassed If Spoofed

If a KeyResolver reads the leftmost header value directly:

~~~http
X-Forwarded-For: 203.0.113.1
~~~

an attacker can swap it to `203.0.113.2` on the next request to evade quotas unless the edge sanitizes it. Conversely, keying on the ingress IP forces all users into one bucket and causes mass 429 outages.

Correct approach:

1. Key on authenticated principal/tenant whenever available.
2. For unauthenticated traffic, use a client IP verified along the trusted chain.
3. Never trust raw client-sent `X-Client-IP` or `X-Forwarded-For`.
4. Test Redis buckets and rate-limit behavior across multiple principals/IPs.
5. Whenever CDN/ingress topology changes, re-test to verify selected client IPs didn't shift.

### 16.2. Distinguishing `transportRemoteIp` from `derivedClientIp`

An **illustrative** redacted log schema:

~~~text
routeId=orders-api
transportPeer=ingress
derivedClientIpCategory=external
publicHost=api.example.test
publicProto=https
publicPrefix=/platform
status=200
~~~

Never dump raw cookies, Authorization headers, token-bearing queries, or full XFF chains into application logs unnecessarily. IP addresses may constitute personal data under applicable regulations; enforce retention, access control, and redaction.

### 16.3. Trace Context Is Independent of Forwarding Headers

W3C `traceparent` links Gateway → microservice traces, yet does not verify client IP, Host, public Proto, or authorization. Any attacker can fabricate a valid `traceparent`.

Therefore:

- Tracing does not replace security.
- Forwarded headers do not replace trace propagation.
- Rate limiting must never key on baggage or client trace IDs.
- Proxy chain changes must be tested for both tracing header injection and public URL reconstruction.

## 17. Network Security, TLS, and Application Layers

### 17.1. Do Not Leave Ingress as the "Only Path on the Diagram"

In Kubernetes, verify:

- Gateway Service uses the right type with no unintended public LoadBalancer/NodePort.
- NetworkPolicies allow ingress controller → Gateway while blocking other sources.
- Cloud firewalls/SecurityGroups restrict public ports.
- Direct pod IP access and service-mesh bypass routes are blocked.
- DNS/service discovery and mTLS identities are enforced where used.
- Management/Actuator endpoints are unreachable via unguarded public routes.

Even when a NetworkPolicy exists, confirm the CNI actually enforces it alongside appropriate default-deny rules.

### 17.2. Public HTTPS and Outbound HTTPS Are Independent

A request carrying `X-Forwarded-Proto: https` can still travel Gateway → backend over `http://`. If policy requires outbound TLS:

- Configure `https://` route targets or secure service instance metadata.
- Configure trust stores/certificate bundles.
- Enforce hostname validation/SNI.
- Configure client certificates/mTLS if service identity requires it.
- Never use an insecure trust manager in production.

Emit HSTS at the public HTTPS boundary per domain policy rather than having backends guess schemes from headers.

### 17.3. WebSockets, HTTP/2, and gRPC

For WebSockets, public `wss://` may translate to `ws://` or dedicated backend TLS. Upgrade headers carry special HTTP semantics; every proxy in the chain must forward Upgrade/Connection matching your websocket routing config.

HTTP/2 and gRPC use pseudo-headers/authority differently from HTTP/1.1; forwarded headers are not a general substitute for SNI or gRPC authority. Test routing and headers using the real protocol rather than assuming a single HTTP/1.1 `curl` proves WebSocket or gRPC works.

## 18. Full Proxy Chain Testing: Three Observation Boundaries

A strong integration test captures:

1. **Client response:** status, `Location`, `Set-Cookie`, HTML/JSON absolute links.
2. **Gateway view:** route ID, effective scheme/host/prefix, post-ingress path.
3. **Mock backend recorded request:** method/path/query, Host, `Forwarded`, and `X-Forwarded-*`.

~~~mermaid
flowchart LR
    T["Test Client"] --> P["Nginx/Envoy test ingress"]
    P --> G["Gateway WebFlux"]
    G --> B["MockWebServer / WireMock"]
    B --> A["RecordedRequest assertions"]
    G --> T
    T --> R["Response assertions"]
~~~

Unit tests mocking a `ServerWebExchange` **do not prove** public ingress strips paths cleanly, terminates TLS, or blocks direct NodePort bypasses.

### 18.1. Path Test Matrix

| Test | Client public path | Gateway should receive | Backend should receive |
| --- | --- | --- | --- |
| P1 | `/platform/api/orders/42` | `/api/orders/42` | `/orders/42` |
| P2 | `/platform/api/orders/42?x=1` | `/api/orders/42?x=1` | `/orders/42?x=1` |
| P3 | `/platform/api/orders/42/items` | `/api/orders/42/items` | `/orders/42/items` |
| P4 | `/platform/api/orders/` | `/api/orders/` | `/orders/` if matched |
| P5 | `/platform/api/orders-old/42` | `/api/orders-old/42` | Does not match orders route |
| P6 | `/platform/api/orders/a%2Fb` | Per URI encoding policy | Cannot bypass path/authorization |
| P7 | `/platform/platform/api/orders/42` | Violates public contract | Never "auto-fixes" double prefix |
| P8 | Direct `/api/orders/42` to Gateway | Denied by network policy outside ingress | Cannot bypass |

Table entries are **test expectations**, not observed run logs. For encoded slashes, dot segments, and Unicode, proxies and frameworks may normalize at different times; verify on the real topology.

### 18.2. Spoofing Test with curl

Run in an **authorized test environment** through the public entrypoint:

~~~bash
curl -i \
  -H 'Forwarded: for=10.0.0.1;proto=http;host=evil.example' \
  -H 'X-Forwarded-For: 10.0.0.1' \
  -H 'X-Forwarded-Proto: http' \
  -H 'X-Forwarded-Host: evil.example' \
  -H 'X-Forwarded-Prefix: /admin' \
  'https://api.example.test/platform/api/orders/42'
~~~

Required assertions:

- Public `Location`/absolute links **never** adopt `evil.example`.
- Gateway/backend **never** treat client-sent `10.0.0.1` as a trusted client IP.
- Backend receives normalized forwarded metadata per ingress/Gateway policy.
- Never jumps to `/admin` routes or bypasses auth.
- Never logs raw forwarded headers containing sensitive data.

### 18.3. Redirect Test with an Internal Upstream

Have the mock backend return:

~~~http
HTTP/1.1 302 Found
Location: http://order-service:8081/orders/42
~~~

If the contract requires rewriting, configure the test client not to follow redirects automatically and assert:

~~~text
status = 302
Location = https://api.example.test/platform/api/orders/42
~~~

This test passes only when **response rewriting or canonical public URL reconstruction truly works**. Merely setting `trusted-proxies` does not automatically fix scheme, host, and public prefix inside `Location`.

### 18.4. Session and OAuth Checks

- Cookie `Path` includes the right public prefix; `Domain` is allowlisted; `Secure`/`HttpOnly`/`SameSite` are valid.
- Callback URL matches IdP registration exactly.
- Redirect statuses and `Location` omit internal hosts/ports.
- Untrusted host/proto/prefix injection cannot alter callbacks.
- Direct requests to internal API routes cannot bypass authorization.

### 18.5. Testing Behind the Real CDN and Bypass Paths

A local mock ingress cannot fully validate provider-specific CDN headers. Run staging tests through the real CDN, compare the IP seen by ingress, and attempt bypassing the CDN from an untrusted source to confirm blocking.

With multiple Gateway replicas, run tests across every replica/canary to catch config drift.

## 19. What Assertions Does an Automated Test Suite Need?

### 19.1. Upstream Request Assertions

Use `@SpringBootTest(webEnvironment = RANDOM_PORT)` + `WebTestClient.bindToServer()` with a real Gateway and MockWebServer/WireMock upstream. When testing Nginx behavior, include a real reverse proxy in the test harness.

Expectations:

~~~text
Given public route /platform/api/orders/**
When client GET /platform/api/orders/42?lang=vi
Then backend recorded request:
  method = GET
  path = /orders/42
  query = lang=vi
  Host = per configured policy
  Forwarded/X-Forwarded = metadata from trusted hops only
~~~

Do not assert byte-for-byte header equality between client and backend: Gateway applies header filters, strips hop-by-hop headers, and follows HTTP client transport rules.

### 19.2. Client Response Assertions

~~~text
Given backend returns:
  302 Location: http://order-service:8081/orders/42

Then client must see:
  302 Location: https://api.example.test/platform/api/orders/42
  no internal hostname in response
~~~

Even if the architecture delegates canonical URL construction to the backend instead of Gateway rewriting, the client-side assertion remains identical. Implementation can vary, but the **public URL contract stays fixed**.

### 19.3. Complementary Test Layers

| Layer | Verifies | Limitation |
| --- | --- | --- |
| Unit logic | Public host/prefix validation/normalization | Misses network bypasses |
| Gateway HTTP integration | Routes, paths, headers, `Location` | May lack TLS/CDN |
| Ingress integration | Prefix stripping and header sanitization | Cannot fully emulate provider CDNs |
| Staging full chain | CDN/Ingress/Gateway/Service/TLS | Slower; requires test data/secret isolation |
| Security tests | Spoofed Host/Forwarded, direct bypasses, IP limits | Must run on accurate topology |
| Upgrade regression | Pre/post-patch behavior | Does not replace security review |

**Never mark PASS from a bare HTTP 200**; the mock backend must verify the rewritten upstream request and the test client must verify the public response.

## 20. Layered Verification Guide with `curl`

### 20.1. Public HTTPS

~~~bash
curl -i \
  'https://api.example.test/platform/api/orders/42'
~~~

To inspect raw 3xx redirects, **omit `-L`**. For lab self-signed certificates, supply the test CA via `--cacert`; never use `-k` in production to ignore certificate errors.

### 20.2. Redirect Inspection

~~~bash
curl -i \
  'https://api.example.test/platform/api/orders/42/redirect'
~~~

Verify:

~~~text
Location scheme = https
Location host   = api.example.test
Location path   = /platform/api/orders/...
Location        = contains no internal DNS/port
Location        = does not duplicate /platform
~~~

### 20.3. Direct Gateway Calls Strictly Inside an Internal Sandbox

~~~bash
# Execute only within an authorized test network.
curl -i \
  -H 'Forwarded: for=203.0.113.99;proto=https;host=evil.example' \
  -H 'X-Forwarded-Host: evil.example' \
  'http://edge-gateway:8080/api/orders/42'
~~~

In production, direct connections from untrusted networks must be **blocked by ACLs/NetworkPolicies**. Never rely on Spring appearing to ignore a header as your sole line of defense.

### 20.4. Conditional Log Observation

Redacted example log:

~~~text
routeId=orders-api
publicHost=api.example.test
publicProto=https
publicPrefix=/platform
gatewayPath=/api/orders/42
backendPath=/orders/42
transportPeer=ingress
forwardedPolicy=trusted
status=200
~~~

This is a **recommended schema**, not default output. Avoid logging raw tokens, cookies, PII, or full forwarded chains.

## 21. Symptoms, Causes, and Fixes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Redirects from HTTPS to HTTP | Internal scheme used as public scheme | Trusted proxy proto, Boot strategy, canonical URLs |
| `Location` contains `:8080` | Inherited internal Gateway port | Public port/rewrite |
| `Location` contains `order-service` | Internal host not rewritten | Public Location contract |
| HTTP–HTTPS redirect loop | Proto lost/corrupted across hops | Inspect every hop, trusted metadata |
| Client gets 404 after 302 | Missing `/platform` or `/api` prefix | Assert public path in `Location` |
| URL has `/platform/platform` | Prefix applied twice | Assign a single owner |
| Backend receives `/42` | Double strip across ingress + Gateway | Maintain per-hop path table |
| Gateway 404, backend gets zero requests | Prefix/route mismatch, wrong namespace | Check ingress paths and route predicates |
| Wrong outbound Host | `PreserveHostHeader`/`SetRequestHostHeader` missing or wrong | Backend Host test + TLS SNI |
| Cookies not sent | Wrong cookie `Path`/`Domain`/`Secure` | Browser test/`Set-Cookie` |
| OAuth2 `redirect_uri` rejected | Wrong public callback scheme/host/prefix | Canonical URL and IdP registration |
| All users share one rate-limit bucket | Keyed on ingress IP instead of client IP | Trusted resolver or principal |
| Rate limit bypassed via XFF | Trusting client-supplied element | Edge sanitization; never use `trustAll` |
| `RemoteAddr` CIDR mismatch | Transport peer differs from client IP | XForwarded resolver + network review |
| `trusted-proxies` never matches | CIDR written instead of Java regex, or header format mismatch | Effective regex + recorded headers |
| `Forwarded` vs XFF conflict | Both families not normalized together | Sanitize both at the edge |
| Swagger servers list internal host | Missing public base URL | Configure OpenAPI public servers |
| Client IP lost behind CDN | Ingress `$remote_addr` is CDN IP | Verify CDN IP ranges and Real-IP policy |
| Header behavior changed after upgrade | Security patch altered defaults/customizer | Review advisories and regression tests |
| Gateway WebMVC uses WebFlux property | Wrong namespace/runtime | Use `server.webmvc.*` for that release |
| Gateway test passes yet NodePort stays open | Tested headers only, not network isolation | Firewall/NetworkPolicy tests |
| Only one replica emits bad redirects | Config or patch drift | Canary, config diff/rollout |
| Backend HTTPS fails despite `XFP=https` | Outbound TLS unconfigured | Truststore, certificates, and SNI |
| Audit logs flooded with IPs/PII | Dumping raw forwarding headers | Redact, enforce retention policies |

## 22. Trusted Proxies Rollout Runbook

### 22.1. Before Changing Configuration

1. Diagram the **actually running** CDN/WAF/LB/Ingress/Gateway/Backend topology—not an assumed diagram.
2. Document public hosts, HTTPS ports, path prefixes, and OAuth callbacks.
3. Inventory network identities/IP ranges for every proxy hop.
4. Assign **which hop sanitizes, which appends, and which consumes** every header.
5. Check Spring Boot, Spring Cloud Gateway, Spring Framework, and ingress versions.
6. Check CVE-2025-41235/CVE-2026-47825 and upgrade to supported fixed releases.
7. Pick one Gateway namespace and one Boot forwarded strategy per design.
8. Build a test matrix covering spoofing, `Location`, `Set-Cookie`, method/path/query, and direct bypasses.
9. Monitor 3xx redirects, 404, 401/403, 429, p95/p99, and TLS errors.
10. Prepare a rollback plan that **preserves network isolation and header sanitization**.

### 22.2. Canary Rollout

- Confirm networking blocks direct public access to Gateway.
- Enable edge sanitization and host validation.
- Update Gateway configuration on one observable canary replica.
- Verify effective inbound scheme/host/path/prefix.
- Verify the mock backend gets the expected path and only trusted forwarded metadata.
- Test client spoofing and IP-based quotas.
- Test redirects/cookies/OAuth flows over public HTTPS URLs.
- Watch for 404s and redirect loops after the change.
- Compare against baseline and expand rollout if passing.
- Keep all Gateway replicas aligned on identical configuration.

### 22.3. Post-Rollout

- Audit patch status and `NettyServerCustomizer` behavior across version updates.
- Monitor changes to CDN IP ranges, ingress controllers, and security groups.
- Alert on forwarding header size/drop/malformed events.
- Review redacted logs/traces without dumping raw tokens/cookies.
- On failure, roll back to a **verified safe configuration**—never use `trusted-proxies: '.*'` or `trustAll()` as a quick fix.
- Record owner, change date, test results, and rollback criteria.

## 23. Capstone Hands-On Exercise

**Scenario:** A system has public URL `https://api.example.test/platform/api/orders/42`, an Nginx ingress, Gateway WebFlux, and a mock `order-service`. A CDN may be added in phase two.

### Requirements

1. Map scheme/host/port/path at every hop.
2. Have Nginx terminate TLS and rewrite `/platform` per contract.
3. Strip/overwrite incoming `Forwarded` and `X-Forwarded-*` from the Internet.
4. Block direct public access to Gateway outside ingress.
5. Choose a Gateway release and matching `trusted-proxies` namespace.
6. Write a tightly scoped Java regex matching proxy metadata—never `.*`.
7. Choose a Boot forwarded strategy and verify its effect on request URIs.
8. Create route `Path=/api/orders/**`, `StripPrefix=1`, targeting the mock backend.
9. Send a public GET and verify the backend receives `/orders/42`.
10. Test queries, trailing slashes, encoded slashes, and unmatched routes.
11. Send spoofed `X-Forwarded-Host/Proto/For/Prefix` and confirm zero impact on public URLs or permissions.
12. Have the mock backend return `302 Location: http://order-service:8081/orders/42`; implement rewrite/canonical URL per contract.
13. Verify public `Location` scheme/host/prefix; test relative `Location`.
14. Verify `Secure`/`Path`/`Domain`/`SameSite` cookies in a browser flow.
15. Verify exact OAuth2/OIDC `redirect_uri` and login callback.
16. Test `maxTrustedIndex(1/2/3)` against a mock XFF chain, explaining results and threat model.
17. Verify rate limiters key on principal/trusted IP rather than client-supplied XFF.
18. Add a mock/real CDN in staging and verify changes to remote peer, Host, and XFF.
19. Test one replica with stale config to verify config drift detection.
20. Apply an advisory patch upgrade, re-run contract/security tests, and write a runbook.

### Acceptance Matrix

| Code | Test | Expectation |
| --- | --- | --- |
| A1 | HTTPS public request | Hits right route/backend |
| A2 | Ingress prefix strip | Gateway receives `/api/orders/42` |
| A3 | Gateway StripPrefix | Backend receives `/orders/42` |
| A4 | Query `lang=vi` | Query preserved across hops |
| A5 | Client-spoofed XFF | Never becomes trusted client IP |
| A6 | Spoofed Forwarded/XFH | Never generates `evil.example` Location |
| A7 | Spoofed XFP | Cannot swap public prefix to `/admin` |
| A8 | Internal backend 302 | Client Location uses public HTTPS origin/path |
| A9 | Relative redirect | Neither missing nor duplicated prefix |
| A10 | Session cookie | Attributes match browser contract |
| A11 | OAuth callback | Exact `redirect_uri` from trusted origin |
| A12 | No-route | Does not accidentally invoke another backend |
| A13 | Rate limiter | Cannot be bypassed with spoofed IP |
| A14 | Direct Gateway bypass | Network-denied |
| A15 | Multi-replica | Version and header policies uniform |
| A16 | Patch upgrade | Regression/security tests still PASS |

**These are testing targets**, not claims of commands executed in a live project.

## 24. Production Checklist

- [ ] Public origin and path prefix documented as an explicit contract.
- [ ] CDN/WAF/LB/ingress/Gateway/backend topology has clear owners and network identities.
- [ ] Trusted edge sanitizes **both** `Forwarded` and `X-Forwarded-*` from clients.
- [ ] Host allowlist, header size limits, and malformed-value handling enforced.
- [ ] Gateway accepts traffic only from trusted ingress; no public NodePort/bypass.
- [ ] Vendor-supported Gateway patches installed for forwarded-header advisories.
- [ ] `trusted-proxies` uses a tight Java regex tested against real proxy metadata.
- [ ] Neither `trusted-proxies: '.*'` nor CIDR syntax used in place of regex.
- [ ] Gateway/WebFlux vs Server WebMVC properties match the release train.
- [ ] Boot forwarded strategy and Gateway outbound filters do not double-process.
- [ ] Append/overwrite rules defined for every proxy hop.
- [ ] Nginx/CDN client IP verified before trusting XFF.
- [ ] `XForwardedRemoteAddressResolver.trustAll()` never used for security.
- [ ] Ingress and Gateway strip exact matching path segments.
- [ ] `X-Forwarded-Prefix` causes neither missing nor duplicated public paths.
- [ ] Public redirects/absolute links never leak HTTP or internal DNS/ports.
- [ ] Relative `Location` tested under the public prefix.
- [ ] Cookies have proper `Domain`/`Path`/`Secure`/`HttpOnly`/`SameSite`.
- [ ] OAuth2/OIDC callbacks match exactly and never read untrusted hosts.
- [ ] HSTS/CORS/OpenAPI/WebSocket public schemes aligned.
- [ ] Outbound TLS/mTLS/certificates governed independently of XFP.
- [ ] Rate-limit and IP audit keys use trusted client IPs or principals.
- [ ] Tested spoofing, network bypasses, 3xx loops, 404s, and multi-hop chains.
- [ ] Gateway replicas run consistent patches/configs with safe rollbacks.
- [ ] Logs/traces redact raw tokens, cookies, and client PII.

## 25. Summary and References

Behind multiple proxies in Spring Cloud Gateway, public URLs and internal URLs **naturally differ**: clients call `https://api.example.test/platform/api/orders/42`, ingress forwards `/api/orders/42`, and Gateway routes to backend `/orders/42`. What matters is every hop fulfilling its exact responsibility.

**Three rules to remember:**

1. **Trust by source, not by header name.** The trusted edge must sanitize `Forwarded` and `X-Forwarded-*`, bypass paths must be blocked, and the Gateway must run patched versions with version-accurate trusted-proxy policies.
2. **Request paths and public response URLs are separate problems.** Ingress rewrites, Gateway `StripPrefix`, `X-Forwarded-Prefix`, and `Location`/cookie/OAuth callbacks do not automatically substitute for one another.
3. **Test the full chain.** Assert the actual request reaching the backend, the final client response, and deliberate spoofing of `Host`/`Proto`/`For`/`Prefix`. A bare HTTP 200 proves nothing about forwarded-header safety.

When CDN, ingress, Boot forwarded handling, Gateway header filters, and backends share an explicit contract, the microservices platform cleanly combines routing, auth, rate limiting, retries, TLS, and tracing without turning forwarding metadata into a security bypass.

### Official References

- [Spring Cloud Gateway Server WebFlux — HttpHeadersFilters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/httpheadersfilters.html).
- [Spring Cloud Gateway — Configuration Properties 5.x](https://docs.spring.io/spring-cloud-gateway/reference/5.0/configprops.html).
- [Spring Cloud Gateway Server WebFlux — RemoteAddr and XForwardedRemoteAddressResolver](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/request-predicates-factories.html).
- [Spring Cloud Gateway Server WebFlux — RewriteLocationResponseHeader](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/gatewayfilter-factories/rewritelocationresponseheader-factory.html).
- [Spring Cloud Gateway Server WebMVC — HttpHeadersFilters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/httpheadersfilters.html).
- [Spring Boot 3.5 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html).
- [Spring Boot 4.0 — Embedded Web Servers and Forwarded Headers](https://docs.spring.io/spring-boot/4.0/how-to/webserver.html).
- [Spring Framework WebFlux — ForwardedHeaderTransformer](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html).
- [Spring Security — HTTP Forwarded Headers Security](https://docs.spring.io/spring-security/reference/7.0/features/exploits/http.html).
- [IETF RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239.html).
- [Spring Security Advisory CVE-2025-41235](https://spring.io/security/cve-2025-41235/).
- [Spring Security Advisory CVE-2026-47825](https://spring.io/security/cve-2026-47825/).
