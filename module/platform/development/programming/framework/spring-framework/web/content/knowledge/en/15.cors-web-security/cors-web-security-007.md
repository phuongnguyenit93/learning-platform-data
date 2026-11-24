# ForwardedHeaderFilter, proxy-supplied headers, and trust boundaries in Spring MVC

> **Scope:** Spring Web MVC (Servlet stack), Java 17+, Spring Boot 3.x / Spring Framework 6.x, deployed behind Nginx/ingress/load balancer/reverse proxy. This lesson explains `Forwarded` and `X-Forwarded-*`, how Spring reconstructs the scheme/host/port/prefix of public URLs, configuring `ForwardedHeaderFilter` and `server.forward-headers-strategy`, as well as **the trust boundary between client, proxy, and application**. Forwarded headers sent directly by an HTTP client are **untrusted data**; they may only be used after a controlled proxy has **stripped and regenerated** them. The lesson includes a runnable Spring Boot example, local verification, illustrative proxy configuration, a strip-only strategy, and a security testing checklist.

## 1. Real-world problem: public HTTPS yet the backend sees HTTP

Suppose a user opens:

```text
https://app.example.test/api/orders
```

A reverse proxy receives HTTPS, terminates TLS, and then calls the Java application over a private network:

```text
Browser
  https://app.example.test:443
       |
       | TLS
       v
Trusted reverse proxy / ingress
       |
       | internal HTTP
       v
Spring Boot / Tomcat
  http://10.10.0.15:8080/api/orders
```

If the application reads only metadata from the internal connection, it may see:

| Servlet property | Direct backend | External user |
| --- | --- | --- |
| `request.getScheme()` | `http` | `https` |
| `request.getServerName()` | `10.10.0.15` or internal hostname | `app.example.test` |
| `request.getServerPort()` | `8080` | `443` |
| `request.isSecure()` | `false` | Browser → proxy connection uses TLS |
| Context/prefix | May be absent | May be `/portal` |

This affects server-generated links, such as:
- Redirect `Location` headers.
- Resource URIs returned in JSON or HTML.
- URLs in emails, canonical URLs, OpenAPI server URLs, or callback URLs if code relies on the request.
- Logic handling secure redirects/cookies or decisions depending on scheme/host if implemented carelessly.

A misconfigured application may generate links like `http://10.10.0.15:8080/api/orders/42` instead of `https://app.example.test/api/orders/42`. Forwarded headers are the mechanism for passing **information about the original public request** through proxies, not proof of user identity.

## 2. The standard Forwarded header and X-Forwarded-* headers

### 2.1. RFC 7239 standard: one composite header

```http
Forwarded: for=192.0.2.10;proto=https;host=app.example.test
```

Meaning of common parameters:

- `for`: the client or previous hop from the perspective of the proxy writing the header. Can be an IP address, obfuscated per spec, or a non-IP identifier; **does not automatically authenticate the client**.
- `proto`: original scheme such as `https`.
- `host`: original hostname (possibly with port).
- `by`: proxy interface/address declared by the proxy.

Multiple proxies can produce a `Forwarded` chain with multiple elements, e.g. comma-separated. The header is only reliable for determining the "original client" if you know exactly which proxies are trusted, how each hop appends/modifies fields, and whether client-supplied values were stripped at the edge.

### 2.2. Non-standard yet common X-Forwarded headers

```http
X-Forwarded-For: 192.0.2.10
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
X-Forwarded-Prefix: /portal
```

| Header | Purpose | Risk when trusted blindly |
| --- | --- | --- |
| `Forwarded` | RFC 7239 standard, with `for/proto/host/by` | Spoofing client, scheme, host |
| `X-Forwarded-For` | One or more addresses across hops | Wrong IP in audit/rate-limit/access rules if client injects it |
| `X-Forwarded-Proto` | Public scheme `http/https` | Wrong HTTP/HTTPS links, breaking security assumptions |
| `X-Forwarded-Host` | Public host | Host-header poisoning, email/reset links/redirects to fake domains |
| `X-Forwarded-Port` | Public port | Wrong host/port URIs, wrong redirects |
| `X-Forwarded-Prefix` | Public path prefix when proxy rewrites routes | Wrong path links, exploitable if prefix is client-controlled |
| `X-Forwarded-Ssl` | TLS indicator in some systems | Not an independent source of TLS verification |

**Never treat `X-Forwarded-For` as identity or authentication.** It does not prove who the user is; users may share IPs, sit behind NAT/VPN, or intentionally send a string resembling a trusted address.

### 2.3. Multi-hop example

```text
Client (192.0.2.10)
    |
Edge proxy (10.0.0.2)
    |
Internal ingress (10.0.0.3)
    |
Backend (10.0.0.15)
```

If the edge removes all untrusted values, it can set `X-Forwarded-For: 192.0.2.10`. A downstream ingress can append the edge address if both belong to an explicit trust chain. However, if the edge uses `$proxy_add_x_forwarded_for` on a client-supplied header without scrubbing, the first element can be a forged IP.

Do not naively write:

```java
// ANTI-PATTERN: client can inject the leading address.
String claimedIp = request.getHeader("X-Forwarded-For")
        .split(",")[0]
        .trim();
```

If IP must be used for security/rate limiting, you need a **trusted proxy list/CIDR** and a standardized hop-chain parsing algorithm/infrastructure; usually rely on native proxy handling or controlled, thoroughly tested edge policies. Never infer trust merely because a header exists.

## 3. The trust boundary is the single most important issue

A `ForwardedHeaderFilter` **cannot tell** which header was created by a trusted proxy versus forged by a malicious client. This security warning is explicitly documented by Spring Framework.

```text
UNTRUSTED                       TRUSTED
Internet client                   Private deployment zone
    |                                      |
    | GET /api/inspect                    |
    | X-Forwarded-Host: attacker.test      |
    v                                      |
[ Edge proxy: TRUST BOUNDARY ]            |
    |                                      |
    | 1) DELETE client-supplied            |
    |    Forwarded and X-Forwarded-*       |
    | 2) SET authoritative proto/host/port |
    |    and optional prefix/for           |
    | 3) RESTRICT backend network access   |
    v                                      |
[ Spring Boot app: parse sanitized headers ]
    |
[ Generate links using trusted public URI ]
```

**Minimum requirements to trust forwarded headers:**

1. The application is reachable only from trusted proxies/ingress via firewalls, network policies, or security groups; do not expose the backend port to the Internet.
2. The proxy **strips incoming `Forwarded` and `X-Forwarded-*` headers from untrusted sources** before adding new values, including header families the backend currently **does not** use.
3. The proxy **authoritatively sets** scheme, host, port, and prefix from verified configuration/routes or trusted metadata; never preserve an arbitrary client-supplied host not on an allowlist.
4. Internal proxies behind the edge accept forwarded chains only from known hops, never trusting every source inside the same VPC by default.
5. The application consistently configures a single interpretation of forwarded headers; avoid one layer trusting `Forwarded` while another prefers a client-sent `X-Forwarded-Host`.
6. Have tests intentionally sending spoofed headers from outside to prove the proxy strips them.

### 3.1. Why must both header families be stripped?

Suppose a proxy only overwrites `X-Forwarded-Proto` yet leaves intact:

```http
Forwarded: proto=https;host=attacker.test
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
```

If another framework, plugin, or filter prioritizes the standard `Forwarded` header, the request can be treated as coming from `attacker.test`. Therefore **scrub both the RFC standard and all related X-Forwarded fields**, then emit only one trusted format per the proxy-backend contract.

**The trust boundary lives at the proxy/network**, not in code like:

```java
if (request.getHeader("X-Forwarded-Proto") != null) {
    // Cannot self-verify that this came from a proxy.
}
```

### 3.2. What if the backend is directly reachable?

If the application enables `server.forward-headers-strategy=framework` while port `8080` remains open to external clients, a direct caller can send:

```http
X-Forwarded-Proto: https
X-Forwarded-Host: attacker.test
```

The filter may use them to build a request wrapper "as if the request arrived via a proxy." It **does not verify source IPs or header signatures**. This is a **misconfiguration** that can lead to URL poisoning or broken assumptions. The primary fix is **blocking direct access**, not merely adding regex checks in controllers.

## 4. How does ForwardedHeaderFilter work?

`org.springframework.web.filter.ForwardedHeaderFilter` is a Spring Servlet Filter. When forwarded headers are present and processing is enabled, it creates an `HttpServletRequestWrapper` to re-expose certain request attributes according to the forwarded metadata.

Examples of downstream methods that observe the interpreted values:
- `getScheme()`.
- `getServerName()`.
- `getServerPort()`.
- `isSecure()`.
- `getRequestURL()` and URL-building via Spring infrastructure.
- Prefix/context path depending on configuration/version and supported headers.

The filter also processes/hides forwarded headers so downstream components do not re-read them differently. However, **hiding them downstream does not make the already-used values trustworthy**. Security depends on the edge proxy controlling those headers.

### 4.1. How does the filter affect URL generation?

In MVC:

```java
String publicLink = ServletUriComponentsBuilder
        .fromCurrentContextPath()
        .path("/api/orders/42")
        .toUriString();
```

This is a **snippet** inside an HTTP request flowing through the pipeline, requiring `import org.springframework.web.servlet.support.ServletUriComponentsBuilder`. When Spring uses valid forwarded info from the proxy, the generated URI can be:

```text
https://app.example.test/api/orders/42
```

Without forwarded metadata when the request hits Tomcat directly:

```text
http://localhost:8080/api/orders/42
```

These URIs assume an **empty context path**; if `server.servlet.context-path`, reverse proxy rewrites, or `X-Forwarded-Prefix` are present, verify the actual output against your topology. Do not append the prefix twice manually.

### 4.2. Response redirects

The filter can also wrap `HttpServletResponse` to adjust `sendRedirect(...)` to the public scheme/host/port from the normalized request. `setRelativeRedirects(true)` changes behavior to emit relative redirects like `RelativeRedirectFilter`.

**Do not assume every redirect always returns an absolute URL:** the result depends on how the app generates `Location`, redirect type, filter configuration, container, and response wrappers. In tests, inspect the actual HTTP status and `Location` header; pay special attention to redirects from Spring Security/OAuth2 or container redirects occurring before the filter runs.

### 4.3. Filter order

Because later filters or handlers may call `getScheme()/getServerName()` to build links, `ForwardedHeaderFilter` must run **before** components needing normalized metadata. Spring Framework notes, for example, that it should run ahead of `RequestContextFilter`.

If Spring Boot auto-configuration creates the filter via `server.forward-headers-strategy=framework`, **do not manually declare a second `ForwardedHeaderFilter`** unless you thoroughly understand registration/filter ordering. Double processing between container/native and Framework can cause unpredictable behavior.

## 5. Spring Boot: NONE, NATIVE, FRAMEWORK

Spring Boot provides the property:

```properties
server.forward-headers-strategy=none
```

Three values:

| Strategy | Who interprets the headers? | When to consider |
| --- | --- | --- |
| `NONE` | Boot does not enable forwarded header handling | No trusted proxy or headers intentionally unused |
| `NATIVE` | Servlet container handles them, e.g. Tomcat RemoteIpValve | Container supports needed headers and trusted proxies can be properly controlled |
| `FRAMEWORK` | Spring Web uses ForwardedHeaderFilter on the Servlet stack | Need Spring integration like URL/prefix/redirect handling and proxy scrubs headers |

According to Spring Boot 3.5 documentation, on some supported cloud platforms the default may be `NATIVE`; in other environments the default may be `NONE`. **Never guess which strategy is active**: inspect effective configuration, deployment profiles, container, and exact version.

### 5.1. Choosing FRAMEWORK

```properties
# Safe only behind a trusted proxy that sanitizes forwarded headers.
server.forward-headers-strategy=framework
```

Spring Boot enables Spring Framework forwarded header support in the Servlet app. Use when the proxy fully enforces the trust boundary and the backend cannot be reached directly from the Internet.

The benefit is that builders/Servlet wrappers see the public scheme/host/port across many MVC response types. The security risk is that if ingress lets client-supplied forwarded headers slip through, **the app may trust forged values**.

### 5.2. Choosing NATIVE

```properties
server.forward-headers-strategy=native
```

With embedded Tomcat, infrastructure like `RemoteIpValve` can understand common headers such as `X-Forwarded-For` and `X-Forwarded-Proto` per configuration. Containers expose settings for header names and trusted/internal proxies depending on version. Example custom header names:

```properties
server.tomcat.remoteip.remote-ip-header=x-forwarded-for
server.tomcat.remoteip.protocol-header=x-forwarded-proto
```

**Note:** these properties only name the headers; **they do not create a trusted-proxy allowlist by themselves**. Configure `internal-proxies`/`trusted-proxies` accordingly and enforce network isolation per container docs. Never assume `NATIVE` supports `X-Forwarded-Prefix` identically to FRAMEWORK: prefix/path handling varies by container and how ingress rewrites paths.

### 5.3. Choosing NONE

```properties
server.forward-headers-strategy=none
```

Use when there is no trusted proxy or when the application intentionally **ignores** forwarded metadata. Setting NONE does not necessarily "physically strip incoming headers": code calling `request.getHeader("X-Forwarded-Host")` directly can still read a client-sent header unless stripped. If you need to strip all such headers from downstream Servlet requests, use `ForwardedHeaderFilter` in `removeOnly` mode as shown in section 6.

### 5.4. Tomcat and TLS termination considerations

Spring Boot recommends when using Tomcat behind a TLS-terminating proxy:

```properties
server.tomcat.redirect-context-root=false
```

This property helps prevent context-root redirects from occurring before forwarded proto metadata is applied in applicable topologies. Do not treat it as a "universal redirect fix." Test real redirects and container/filter ordering.

## 6. removeOnly mode: strip WITHOUT trusting forwarded headers

If the application does not need to interpret forwarded headers or wants to ensure downstream code cannot accidentally read them, you can use:

```java
ForwardedHeaderFilter filter = new ForwardedHeaderFilter();
filter.setRemoveOnly(true);
```

Meaning: the filter **hides/strips** `Forwarded` / `X-Forwarded-*` headers from downstream views, yet **does not use them** to override host/scheme/port. Per Spring Javadoc, this is an officially supported mode.

Full Java config example of bean registration (used as **a separate approach**, not alongside Boot FRAMEWORK):

```java
package com.example.demo;

import java.util.EnumSet;
import jakarta.servlet.DispatcherType;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.web.filter.ForwardedHeaderFilter;

@Configuration
class ForwardedHeaderRemoveOnlyConfig {

    @Bean
    FilterRegistrationBean<ForwardedHeaderFilter>
    stripForwardedHeaders() {

        ForwardedHeaderFilter filter = new ForwardedHeaderFilter();
        filter.setRemoveOnly(true);

        FilterRegistrationBean<ForwardedHeaderFilter> bean =
                new FilterRegistrationBean<>(filter);
        bean.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        bean.setDispatcherTypes(EnumSet.of(
                DispatcherType.REQUEST,
                DispatcherType.ASYNC,
                DispatcherType.ERROR));
        bean.setAsyncSupported(true);
        return bean;
    }
}
```

When using this config, set:

```properties
server.forward-headers-strategy=none
```

**Do not** enable both `server.forward-headers-strategy=framework` and `stripForwardedHeaders()`, as two components with conflicting responsibilities would collide. If container-level `NATIVE` already consumed the headers before the Servlet Filter ran, `removeOnly` may be too late to undo container metadata; strip them at the proxy or disable/adjust native handling.

Nor should `removeOnly` be marketed as the sole defense against HTTP request smuggling or host validation. It only addresses a set of headers at the Servlet request layer, not every way Host/TLS metadata can be altered.

## 7. Runnable Spring Boot 3.x example: observing public URLs

This example intentionally uses **Spring Web** without database/security so headers are easy to observe. In lab mode, it allows sending fake forwarded headers **solely to demonstrate the effect** of FRAMEWORK. **Never configure a public-facing production backend like this.**

### 7.1. Create the project

At [Spring Initializr](https://start.spring.io/), create a Maven project with Java 17+, Spring Boot 3.x, and the **Spring Web** dependency. POM dependency:

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

This is a fragment; Initializr generates the complete POM/versions/plugins.

### 7.2. Complete Java demo

Create `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

record RequestInfo(
        String scheme,
        String host,
        int port,
        boolean secure,
        String contextPath,
        String requestUrl,
        String generatedLink) {
}

@RestController
class InspectController {

    @GetMapping("/api/inspect")
    public RequestInfo inspect(HttpServletRequest request) {

        String generatedLink = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/api/resource/42")
                .toUriString();

        return new RequestInfo(
                request.getScheme(),
                request.getServerName(),
                request.getServerPort(),
                request.isSecure(),
                request.getContextPath(),
                request.getRequestURL().toString(),
                generatedLink);
    }
}
```

Every field in the record is what the controller **sees after Servlet filter chain processing**. Endpoint `/api/resource/42` here is only a **sample generated link**, not a registered real resource. The app does not use the forwarded host to perform network calls.

### 7.3. application.properties for the lab

Create `src/main/resources/application.properties`:

```properties
server.forward-headers-strategy=framework
# Bind to loopback only when testing on a personal machine:
server.address=127.0.0.1
server.port=8080
```

In this setup, only processes on the local machine can call the loopback port. Production typically requires different network/private-interface policies; do not copy lab settings verbatim.

Run with:

```bash
# Linux/macOS
./mvnw spring-boot:run

# Windows
mvnw.cmd spring-boot:run
```

### 7.4. Request without forwarded headers

```bash
curl -sS 'http://127.0.0.1:8080/api/inspect'
```

Key fields in the JSON typically match:

```json
{
  "scheme": "http",
  "host": "127.0.0.1",
  "port": 8080,
  "secure": false,
  "contextPath": "",
  "requestUrl": "http://127.0.0.1:8080/api/inspect",
  "generatedLink": "http://127.0.0.1:8080/api/resource/42"
}
```

These depend on the request's actual Host and server configuration; this is expected output for a loopback curl command, not representative of a production proxy.

### 7.5. Simulating a proxy with forwarded headers

```bash
curl -sS 'http://127.0.0.1:8080/api/inspect' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: app.example.test' \
  -H 'X-Forwarded-Port: 443'
```

With Spring Framework forwarded header handling enabled, key fields can become:

```json
{
  "scheme": "https",
  "host": "app.example.test",
  "port": 443,
  "secure": true,
  "contextPath": "",
  "requestUrl": "https://app.example.test/api/inspect",
  "generatedLink": "https://app.example.test/api/resource/42"
}
```

**This simultaneously demonstrates the attack** if outsiders are allowed to call the backend directly. When a client sets `X-Forwarded-Host` and the server accepts it, generated links are controlled by the client. This mechanism is **safe only** when headers on real requests reaching the backend were produced by a trusted proxy after stripping untrusted input.

### 7.6. Simulating host spoofing

```bash
curl -sS 'http://127.0.0.1:8080/api/inspect' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: attacker.example.test' \
  -H 'X-Forwarded-Port: 443'
```

In the lab with FRAMEWORK enabled, `host` and `generatedLink` can contain `attacker.example.test`. This is behavior that must be **blocked at the proxy boundary in production**, not a valid way to obtain the public host.

**After finishing this lab, switch the strategy to NONE if running a service reachable from untrusted networks without a trusted reverse proxy in front.**

### 7.7. Testing NONE mode for comparison

Change the config:

```properties
server.forward-headers-strategy=none
server.address=127.0.0.1
server.port=8080
```

Restart and run the command with `X-Forwarded-Host: attacker.example.test` as above. Because Boot disables the forwarded strategy, Servlet fields/links in the demo continue reflecting the direct connection URL `127.0.0.1:8080`. However, if you manually call `request.getHeader("X-Forwarded-Host")`, the raw header string may still be present: NONE is **not** a request header firewall.

## 8. Illustrative reverse proxy config: scrub then set

The example below is an **Nginx fragment for a fixed topology**, not a complete production TLS configuration. It assumes `app.example.test` is controlled, the proxy is the HTTPS entry point, the app listens only on loopback `127.0.0.1:8080`, and there is no routing prefix.

```nginx
# Place inside an HTTPS server/location block with TLS configured.
location / {
    proxy_pass http://127.0.0.1:8080;

    # Backend Host consistent with the valid public host.
    proxy_set_header Host app.example.test;

    # Strip client-supplied standard Forwarded header.
    proxy_set_header Forwarded "";

    # Overwrite with authoritative edge proxy metadata.
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host app.example.test;
    proxy_set_header X-Forwarded-Port 443;
    proxy_set_header X-Forwarded-For $remote_addr;

    # Prevent clients from injecting other variants.
    proxy_set_header X-Forwarded-Ssl "";
    proxy_set_header X-Forwarded-Prefix "";
}
```

**Correctness condition:** this snippet must be applied at the edge trust boundary, not overridden against policy by an inherited Nginx config or an upstream/downstream proxy. Verify Nginx does not pass unlisted forwarded headers in conflicting ways. In complex systems, scrub all header names read by the application and every middleware component, including `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Port`, `X-Forwarded-Prefix`, and any stack-specific variants.

`X-Forwarded-For $remote_addr` uses the IP of the **connection to Nginx**. If Nginx is truly the edge, that is the external IP seen by the edge. If a trusted CDN/proxy sits ahead of Nginx, `$remote_addr` is usually the CDN's IP rather than the client's; getting the real client IP requires a trusted-real-IP policy at the edge and ensuring the CDN scrubs headers first.

### 8.1. Why not use $proxy_add_x_forwarded_for by default?

Nginx provides `$proxy_add_x_forwarded_for` to append the current IP to an existing `X-Forwarded-For` header. If the existing part was client-supplied and unscrubbed, the result keeps the client's forged IP:

```text
Client: X-Forwarded-For: 1.2.3.4 (forged)
Proxy append: 1.2.3.4, 192.0.2.10
```

An application taking the first element gets the forged IP. Appending should only be used when **prior segments were built exclusively by trusted hops**, and the reader parses the chain using an explicit trusted-proxies policy.

### 8.2. What if there are multiple public hostnames?

Do not hardcode one host if the product legitimately uses multiple tenant domains. Still, **never** accept any Host value and blindly copy it into `X-Forwarded-Host`. The proxy should:
- Match `server_name`/routing rules against an allowlist of valid hostnames/tenant domains.
- Reject default/unknown Hosts or redirect to a canonical host.
- Set `X-Forwarded-Host` only to a validated/routed host.
- When the app builds password-reset/email links, prefer a public base URL from verified configuration/tenant records instead of relying on raw request headers.

### 8.3. X-Forwarded-Prefix when a gateway rewrites paths

Suppose the public URL is:

```text
https://app.example.test/portal/api/inspect
```

The proxy strips `/portal` and forwards to the backend:

```text
http://127.0.0.1:8080/api/inspect
```

The proxy can set `X-Forwarded-Prefix: /portal` so Spring builds public links with the right context when supported by the mechanism/framework/version. **Do not** add `/portal` to both backend routes and builder code if the framework already applies the prefix; doing so can produce `/portal/portal/...`.

Prefix handling varies between `FRAMEWORK` and native containers. Some Spring Framework versions provide dedicated settings to enable `X-Forwarded-Prefix`; check the Javadoc for your exact `ForwardedHeaderFilter` version. With modern Spring APIs offering constructors for header families and prefix options, **do not copy methods from 7.x Javadoc into an older 6.x release**.

## 9. Web security risks when trusting forged headers

### 9.1. Host header injection / password reset poisoning

If code builds a password reset email like:

```java
String link = ServletUriComponentsBuilder
        .fromCurrentContextPath()
        .path("/reset")
        .queryParam("token", token)
        .toUriString();
```

This snippet depends on `token`. When the forwarded host is attacker-controlled, the email URL can become:

```text
https://attacker.example.test/reset?token=...
```

A user receives an apparently legitimate email yet visits another domain, potentially leaking the token. **Stronger defense:** construct sensitive URLs from a **configured and allowlisted canonical public base URL**; proxies must also scrub forwarded headers and validate Host.

### 9.2. Open redirects and Location poisoning

Rewriting the request's host to the public host does not by itself cause an open redirect, yet many redirect helpers use the request's host/scheme. If that host is untrusted, an attacker can influence `Location`. For redirects to optional targets like `next=...`, still validate relative paths or an independent destination allowlist; `ForwardedHeaderFilter` **does not** protect redirect parameters.

### 9.3. CORS: forwarded headers do not define valid Origins

`Origin: https://frontend.example.test` is a request header used by browsers in CORS. `X-Forwarded-Host: app.example.test` describes the proxy's public URL; the two concepts are not synonymous.

Never write a CORS policy like:

```java
// ANTI-PATTERN: using untrusted host/proxy metadata as an allowlist.
String origin = request.getHeader("Origin");
response.setHeader("Access-Control-Allow-Origin", origin);
response.setHeader("Access-Control-Allow-Credentials", "true");
```

Arbitrarily reflecting `Origin` (especially with credentials) is dangerous. Maintain a trusted origins list and separate credential policy; forwarded headers do not replace CORS checks. Nor is CORS **authentication or CSRF protection**.

### 9.4. Secure cookies and HTTPS

When TLS terminates at the proxy, the backend may see `http`/`isSecure=false` without corresponding handling. This can affect custom code or frameworks relying on the secure-request signal when setting cookies/redirects. However, never treat a client-sent `X-Forwarded-Proto=https` as "proof TLS was used"; the proxy must ensure the real public connection is encrypted.

For session cookies: configure `Secure`, `HttpOnly`, `SameSite`, TLS, and security settings matching your app's threat model. Do not rely solely on `isSecure()` if proxy architecture/configuration is uncontrolled.

### 9.5. OAuth2/OIDC callbacks and redirect_uri

OAuth2 client applications may build `redirect_uri` from the request and registered client settings. Wrong forwarded host/scheme can cause redirect URI mismatches or generation on the wrong domain. Use exact-matched registered redirect URIs, canonical public URLs, trusted proxy configurations, and integration tests on the real topology. Never let an arbitrary forwarded host decide where authorization codes/tokens are sent.

### 9.6. IP-based rate limiting and auditing

If code takes the first element of `X-Forwarded-For` as the "real IP," callers can spoof IPs to bypass quotas or frame other addresses. Trust only addresses from an edge-verified trusted chain. For security-critical identity, rely on authenticated principals/sessions/tokens and risk policies; IP is a supplementary signal, not an identity credential.

## 10. Deployment checklist with Spring Security

| Area | Practice |
| --- | --- |
| HTTP ingress | Validate TLS/certificates, restrict public hosts |
| Backend port | Accessible only from proxy/ingress; do not expose NodePort/backend to Internet |
| Forwarded headers | Scrub and regenerate both RFC `Forwarded` and `X-Forwarded-*` at the edge |
| App strategy | Choose `NONE/NATIVE/FRAMEWORK` deliberately, avoid double processing |
| Client IP | Trusted proxy CIDRs/chain; never parse raw first XFF |
| CORS | Separate origin allowlist; never trust arbitrary Origin or forwarded host |
| CSRF | Protect state-changing requests with cookie/session authentication |
| Session cookies | Secure/HttpOnly/SameSite and matching security config |
| Authentication | Spring Security identity; never use forwarded headers as user ID |
| URL generation | Canonical public base URL for sensitive links |
| Logs/metrics | Never log raw Authorization/cookies/reset tokens; distinguish remote proxy from verified client IP |
| Host validation | Allowlist public domains at ingress/app; reject unknown Hosts |
| Redirect/callback | Test Location, OAuth redirect_uri, and absolute links after TLS termination |
| Security tests | Test spoofed headers from Internet, direct backend, and inside the network |

**Filter order matters, yet is not enough:** if another middleware reads forwarded headers **before** `ForwardedHeaderFilter`, or the container alters request metadata natively, a later filter cannot undo every prior decision. Therefore enforce the trust boundary right at the network/ingress edge.

## 11. Required tests before allowing real traffic

### 11.1. Test through the real proxy, not just direct curl to backend

| Test | Public-side request | Expected |
| --- | --- | --- |
| A | HTTPS + valid public Host | Returned URIs/links use `https://app.example.test` |
| B | Client adds `X-Forwarded-Host: attacker.test` | Edge strips fake header; links still use valid public host |
| C | Client adds `Forwarded: host=attacker.test;proto=http` | Edge strips fake RFC header; no host/scheme poisoning |
| D | Client adds `X-Forwarded-For: 1.2.3.4` | System derives IP from trusted chain, ignoring forged item |
| E | Client changes `Host` to an unapproved hostname | Edge rejects or redirects canonically per policy |
| F | Client tries direct access to backend:8080 | Blocked by network policy/firewall |
| G | Request via route with `X-Forwarded-Prefix` | Links neither omit nor duplicate prefix |
| H | 302/303 redirects and OAuth callbacks | `Location`/redirect_uri match canonical host, scheme, and path |
| I | App switches NONE/NATIVE/FRAMEWORK | Behavior matches config with no double normalization |

**Important:** tests B/C/D must send spoofed headers **from outside the trust boundary**, not just directly to the local lab app. Testing only the backend proves filter behavior, **not** that the proxy strips headers.

### 11.2. MockMvc test for the filter (in-app unit/integration)

Add `spring-boot-starter-test` and create the test:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "server.forward-headers-strategy=framework")
@AutoConfigureMockMvc
class ForwardedMetadataTest {

    @Autowired
    MockMvc mvc;

    @Test
    void canReadForwardedMetadataInControlledTest() throws Exception {
        mvc.perform(get("/api/inspect")
                        .header("X-Forwarded-Proto", "https")
                        .header("X-Forwarded-Host", "app.example.test")
                        .header("X-Forwarded-Port", "443"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.scheme").value("https"))
                .andExpect(jsonPath("$.host").value("app.example.test"))
                .andExpect(jsonPath("$.secure").value(true));
    }
}
```

This tests **the app**, not the reverse proxy; it verifies request wrapper/framework behavior when headers are present. Depending on Boot version, filter registration in a MockMvc test context can depend on how filters are auto-configured. If a test does not show the behavior, verify filter registration rather than immediately switching to parsing raw headers.

### 11.3. Testing host poisoning from ingress

A valuable security regression test sends requests to the **real public URL** with both kinds of forged forwarded headers:

```bash
curl -i 'https://app.example.test/api/inspect' \
  -H 'Forwarded: proto=http;host=attacker.example.test' \
  -H 'X-Forwarded-Host: attacker.example.test' \
  -H 'X-Forwarded-Proto: http'
```

Expect the system **not** to generate absolute links pointing to `attacker.example.test`, not to treat the public request as HTTP because of the fake header, and not to bypass permissions. Exact status/body may depend on the proxy's header-blocking policy; what matters is **not trusting forged values**.

**Do not run the command above against any system you do not own or are not authorized to test.** In an authorized lab or staging environment, this is a standard configuration test.

## 12. Troubleshooting: wrong HTTPS/Host/prefix/redirects

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| App generates `http://...:8080` links | App not using proxy metadata | Strategy; proxy setting `X-Forwarded-Proto/Host/Port` |
| `https` right yet host still internal | Proxy didn't set it or app prefers another header | Both `Forwarded` and `X-Forwarded-Host` |
| Links contain `/portal/portal/...` | Prefix added twice | Proxy path rewrite, context path, and prefix |
| 302 redirect reverts to HTTP | TLS termination/redirect before forwarded handling | Tomcat redirect context root, filter order, and `Location` |
| OAuth redirect_uri mismatch | App builds URI differing from registered value | Canonical public URL / forwarded policy |
| `isSecure()` false behind HTTPS proxy | Strategy none/native wrong or proto header missing | Container config, trusted proxies, X-Forwarded-Proto |
| Filter does not run | Framework strategy off, servlet filter order/dispatcher types | Filter registration, REQUEST/ASYNC/ERROR |
| Filter runs twice | Both Boot FRAMEWORK and manual filter registration | Pick one mechanism |
| Audit IP is spoofed | App reads first XFF element sent by client | Edge scrub + trusted chain algorithm |
| Internal health URL changes host unexpectedly | Forwarded headers sent on internal requests | Use NONE/removeOnly for traffic not via trusted proxy |
| Direct backend request spoofs scheme/host | Backend port exposed + FRAMEWORK | Network isolation and edge scrub |
| Strange CORS origin reflected | CORS policy built from request input | Explicit allowed origins |
| Password reset email points to wrong domain | Host poisoning | Configured base URL, host allowlist, proxy header scrub |
| `X-Forwarded-Prefix` has no effect | Native unsupported or framework/version config | Check strategy and API version |
| Blocked via removeOnly yet app still "https" | Container already ran NATIVE before the filter | Disable native, scrub at edge, and test request metadata |
| Cannot see forwarded headers in controller | ForwardedHeaderFilter intentionally hides them | Use normalized request fields; debug safely at proxy |

### 12.1. Systematic debugging steps

1. Map the real topology: client → CDN? → WAF? → ingress? → backend. Where is the **edge of trust**?
2. Inspect effective edge config: are **both families** of forwarded headers scrubbed and re-set?
3. Verify the backend cannot receive direct requests from the Internet or untrusted VPCs.
4. Check the effective `server.forward-headers-strategy` for the target environment/profile and Servlet container.
5. In the app, compare `request.getScheme()`, `getServerName()`, `getServerPort()`, and link builder output against the expected public URL.
6. If native/container, inspect trusted/internal proxies and header names.
7. If Framework, inspect filter registration, ordering, and prefix support.
8. Test from the public side **with spoofed headers**, not only header-free requests.
9. Test redirects, secure cookies, OAuth callbacks, CORS, and sensitive links.
10. Limit debug logs: never emit tokens, cookies, or customer details into diagnostic output.

## 13. Common misconceptions

**Q1.** With `ForwardedHeaderFilter`, can the app automatically tell proxy headers apart from client headers?

**Answer:** No. The filter does not know trusted origins; the edge proxy must scrub then set headers, and the backend must restrict direct access.

**Q2.** Does `X-Forwarded-For` prove a user's real IP address?

**Answer:** No. It is just HTTP data; you must know the trusted proxy chain and strip forged client headers before using it.

**Q3.** How does `server.forward-headers-strategy=framework` differ from `native`?

**Answer:** FRAMEWORK uses Spring's `ForwardedHeaderFilter`, while NATIVE uses container support for forwarded headers. Prefix reading and trusted-proxy algorithms may differ; never enable both arbitrarily.

**Q4.** When should `removeOnly=true` be used?

**Answer:** When you need to strip forwarded headers from downstream **without using their information**. It does not reconstruct public URLs and does not replace the edge/proxy trust boundary.

**Q5.** The server behind a proxy sees HTTP while the user uses HTTPS. Can it trust a client-sent `X-Forwarded-Proto=https` to detect HTTPS?

**Answer:** Only after that value is generated by a trusted proxy that stripped client input. If the backend is directly open to clients, the answer is no.

**Q6.** Do forwarded headers replace CORS allowlists, CSRF protection, or authentication?

**Answer:** No. They describe metadata of a proxied request; Origin policies, CSRF tokens, identity, and authorization are independent mechanisms.

**Q7.** If the proxy strips `X-Forwarded-Host` yet leaves `Forwarded` untouched, is that safe enough?

**Answer:** Not yet. A component may prioritize the RFC `Forwarded` header still carrying a forged host.

**Q8.** If the public URL has `/portal` yet the backend has no prefix, what should be done?

**Answer:** Configure path rewrite/prefix at the gateway and matching Spring strategy/version; verify URL builders neither omit nor duplicate `/portal`.

## 14. Official documentation

- [Spring Framework — Servlet Filters and Forwarded Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): RFC 7239, X-Forwarded headers, ForwardedHeaderFilter, trust boundaries, and dispatcher types.
- [Spring Framework 6.2 — ForwardedHeaderFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html): wrapper semantics, `setRemoveOnly`, `setRelativeRedirects`.
- [Spring Boot 3.5 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server): NATIVE/FRAMEWORK strategies, redirects/Tomcat.
- [Spring Boot 3.5 — ForwardHeadersStrategy Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/ServerProperties.ForwardHeadersStrategy.html): `NONE`, `NATIVE`, `FRAMEWORK`.
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239): syntax and proxy hop chains.
- [Spring Framework — ServletUriComponentsBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/servlet/support/ServletUriComponentsBuilder.html): building URIs from the Servlet request.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter chain, security context, and trust architecture.
- [OWASP — Host Header Injection](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/07-Input_Validation_Testing/17-Testing_for_Host_Header_Injection): risks and testing for Host header poisoning.
- [Nginx — proxy_set_header](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_set_header): policies for forwarding headers upstream.

**Final takeaway:** `ForwardedHeaderFilter` solves **scheme/host/port/prefix accuracy when an application sits behind a proxy**; it **does not authenticate** forwarded header values. A secure architecture requires an edge proxy that **strips untrusted headers**, sets metadata from the real route/TLS, restricts direct backend access, applies the right `NONE/NATIVE/FRAMEWORK` strategy, and tests host/proto/IP spoofing. For sensitive absolute paths like password resets or OAuth callbacks, prefer a **canonical configured public URL** over trusting request metadata.
