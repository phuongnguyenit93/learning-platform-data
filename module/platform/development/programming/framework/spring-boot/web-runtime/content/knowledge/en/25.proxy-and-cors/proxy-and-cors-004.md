# Only trust forwarded metadata from controlled proxies

## 1. The problem: request metadata can be altered in transit

A Spring Boot application rarely receives HTTPS connections directly from users. Between the browser and the application there may be a CDN, API gateway, ingress controller, load balancer, or NGINX reverse proxy. The proxy accepts the public request, may terminate TLS, and then calls the internal application over HTTP. As a result, Spring Boot sees a connection **from the proxy**, not the original connection.

```text
Browser
  198.51.100.25
  https://api.example.test/orders
        │ TLS/HTTPS
        ▼
Edge reverse proxy / ingress
  10.0.0.10
  TLS termination + host verification + header normalization
        │ Internal HTTP
        │ X-Forwarded-For: 198.51.100.25
        │ X-Forwarded-Proto: https
        │ X-Forwarded-Host: api.example.test
        │ X-Forwarded-Port: 443
        ▼
Spring Boot (Tomcat or Reactor Netty)
  10.0.1.20:8080
  initial physical request.getRemoteAddr() = proxy address
  initial physical request.getScheme() = http
        │
        ▼
Business handler, redirects, logging, security decisions
```

So that the application can build links and redirects matching the public URL, the proxy can send **forwarded headers**. However, those headers are still fundamentally **HTTP data**: if a client can inject `X-Forwarded-Host: attacker.invalid` and the backend trusts it, the request can be tricked.

**Mandatory principle:** the application may use forwarded metadata only when it arrives through **a proxy inside a trust boundary**, the proxy has **stripped/overwritten client-declared data**, and **connections to the backend are restricted to authorized proxies**. Simply toggling a Spring Boot property does not make the network secure.

This lesson targets Spring Boot 3.3.x and Java 17+, covering both Spring MVC/Servlet and WebFlux. The goal is not to "always get the real IP" at all costs, but to **know which data is trustworthy, where to obtain it, what to use it for, and how to test for spoofing**.

## 2. Which headers can carry forwarded metadata?

### 2.1. RFC 7239: the standard `Forwarded` header

Example:

```http
Forwarded: for=198.51.100.25;proto=https;host=api.example.test
```

Common directives:

- `for=...`: the client/peer address at a hop; may be an IP, quoted/bracketed IPv6, or an obfuscated identifier per RFC.
- `by=...`: the sending proxy's interface/identifier.
- `proto=http|https`: the scheme of the connection before the proxy.
- `host=...`: the original authority/host described by the proxy.

When crossing multiple proxies, there may be **multiple elements** separated by commas. Do not parse the standard header yourself with `split(",")` or `split(";")` for security purposes: quoted-string, IPv6, and escaping syntax can be subtle. Use a supported parser/framework and clear hop policies.

RFC 7239 specifies that this information **cannot be assumed accurate by default**, because the client or any hop along the path can create or modify it. That is why a trust boundary must be established at the network/proxy layer.

### 2.2. The `X-Forwarded-*` header family

| Header | Common meaning | Risk if trusted from client |
|---|---|---|
| `X-Forwarded-For` | List of client/proxy IPs across hops | Bypass IP allowlists/rate limits with a forged IP |
| `X-Forwarded-Proto` | Public scheme (`https`/`http`) | Broken links/redirects; incorrect scheme-dependent HTTPS/cookie logic |
| `X-Forwarded-Host` | Public hostname | Host-header poisoning, password-reset links pointing to attacker domain |
| `X-Forwarded-Port` | Public port (443, 80, custom port) | Wrong port in redirects/OAuth callbacks, malicious links |
| `X-Forwarded-Prefix` | Prefix added/stripped at the proxy | Broken URL/path generation; can affect redirect paths |
| `X-Forwarded-Ssl` | Legacy convention to indicate SSL on some proxies | Conflicts with `X-Forwarded-Proto` |
| `X-Real-IP` | IP set by some proxies | If passed through from client, merely an attacker-claimed IP |

Some implementations use only a subset of headers. Spring Boot and embedded servers do not promise to handle every variant and order identically. **Do not allow both `Forwarded` and `X-Forwarded-*` from inconsistent sources simultaneously**, because library A may prefer one while library B prefers the other.

Example **malicious request**:

```http
GET /forgot-password HTTP/1.1
Host: api.example.test
Forwarded: for=192.0.2.99;proto=https;host=attacker.invalid
X-Forwarded-For: 192.0.2.99
X-Forwarded-Host: attacker.invalid
X-Forwarded-Proto: https
```

The `198.51.100.0/24` and `192.0.2.0/24` ranges used in examples are documentation ranges, not real user Internet addresses. If the app generates reset links from a spoofed host, it could send `https://attacker.invalid/...` to the user. Using forwarded hosts in sensitive flows **must not replace public URL/canonical host controls**.

## 3. Trust boundary: three defense layers must coexist

| Layer | Purpose | Examples |
|---|---|---|
| **Network/transport** | Only authorized proxies connect to the backend | Internal `server.address`, firewall/security group, Kubernetes NetworkPolicy, mTLS if needed |
| **Edge proxy** | Strip/overwrite all untrusted forwarded headers at the public boundary | NGINX `proxy_set_header X-Forwarded-For $remote_addr`, `Forwarded ""`, host allowlist |
| **Framework/container** | Interpret headers only according to config and appropriate proxies/hops | Spring Boot `server.forward-headers-strategy`, Tomcat `RemoteIpValve`, trusted proxies |

Missing any one of the three layers still leaves a risk. For example:
- Backend is **publicly reachable** with `FRAMEWORK` enabled: direct clients can inject fake headers themselves.
- NGINX passes `X-Forwarded-For` through from the client and the backend takes the first element: IP spoofing still happens even though traffic flows through NGINX.
- Edge sanitizes well, but another sidecar/instance on the internal network can connect straight to the backend: you cannot assume every private IP source is a trusted proxy.
- Backend is network-restricted yet trusts `X-Forwarded-Host` preserved from the user by a CDN: absolute URLs can still be poisoned.

**The basis of trust is connecting from an authenticated/permitted peer and the proxy's header-creation process, not the header name.** `Forwarded` data carries no signature by default. TLS between the client and the edge does not prove client-sent forwarded headers were filtered if the edge passes them through intact.

## 4. When should forwarded headers be ignored completely?

If the application receives direct connections, or a proxy boundary is not yet guaranteed, use:

```properties
server.forward-headers-strategy=none
```

`NONE` tells Boot not to apply Boot-configured forwarding mechanisms. Request metadata then normally reflects the **direct connection to the embedded server**; do not infer client scheme/host/IP from `X-Forwarded-*`.

Note: `NONE` **does not make raw headers safe or strip them from the request**. Custom code calling `request.getHeader("X-Forwarded-For")` will still read whatever string the client sent. If you truly want those headers gone at the application, block them at the proxy or use a removal filter/transformer where appropriate.

In Spring Framework Servlet, `ForwardedHeaderFilter` has `setRemoveOnly(true)` to **hide/strip Forwarded-style headers without interpreting them**. In WebFlux, there is `ForwardedHeaderTransformer.setRemoveOnly(true)`. This is an advanced option when the application layer must not see the headers, but **you should not arbitrarily stack a remove-only filter on top of a `NATIVE` pipeline that already uses the headers**. Stripping at the edge boundary remains best.

Property names here follow Spring Boot 3.3; verify your exact version before using options from other releases.

## 5. Three `server.forward-headers-strategy` modes in Spring Boot

| Value | Component used | When suitable | Security condition |
|---|---|---|---|
| `NONE` | Boot forwarded processing disabled | No trusted proxy, direct app access | Code does not trust raw headers |
| `NATIVE` | Native support from embedded server/container (Tomcat `RemoteIpValve`, server-dependent) | Proxy sends standard headers and you can restrict trusted proxies at the server | Verify peer/hop trust, edge sanitization, network ACL |
| `FRAMEWORK` | Spring MVC `ForwardedHeaderFilter` or WebFlux `ForwardedHeaderTransformer` | Need Spring Framework handling instead of native | **Framework cannot tell whether headers came from a trusted proxy or a spoofing client**; edge filtering is mandatory |

Spring Boot 3.3 may default to `NATIVE` in certain detected cloud environments; in other environments the default may be `NONE`. **Do not rely on implicit defaults:** declare it explicitly per deployment/profile and test through the real proxy.

For **Tomcat** using `NATIVE`, Spring Boot provides related properties:
- `server.tomcat.remoteip.internal-proxies`: regular expression of proxy addresses considered internal/trusted at connection time.
- `server.tomcat.remoteip.trusted-proxies`: trusted intermediate proxies appearing in the chain, per the `RemoteIpValve` contract.
- `server.tomcat.remoteip.remote-ip-header`: name of the header carrying the IP list (typically `x-forwarded-for`).
- `server.tomcat.remoteip.protocol-header`: header carrying the original protocol (typically `x-forwarded-proto`).
- `server.tomcat.remoteip.host-header` and `port-header`: host/port headers used to build metadata.

**Never set `server.tomcat.remoteip.internal-proxies` to empty to "trust all" in production.** Private ranges `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` may contain untrusted workloads in a VPC/Kubernetes cluster. Narrow it to the IP/CIDR of the actual proxy hop and block all other connections at the network layer.

Tomcat processes the proxy chain using `RemoteIpValve`'s algorithm and trust settings. Never write `X-Forwarded-For.split(",")[0]` to make IP allowlist decisions; the leftmost value can be client-supplied. With multiple proxies, hop ordering and client IP selection depend on the trust policy, starting from the network peer closest to the application.

## 6. Runnable example: Spring Boot MVC observing metadata behind a proxy

Standalone example using **Java 17+, Spring Boot 3.3.13, Gradle**, running Tomcat MVC. The `/inspect` endpoint displays metadata **already processed by the embedded server** and a URL generated from the request. Use this endpoint only for learning and testing; in production, do not expose debug endpoints that reveal topology.

### 6.1. Project structure

```text
proxy-trust-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/proxytrust/ProxyTrustApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/proxytrust/ForwardedHeadersIgnoredTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8080
# Demo allows only NGINX on the same machine to call Tomcat.
# Container environments need different bind and firewall/NetworkPolicy settings.
server.address=127.0.0.1

# Interpret forwarded headers only via Tomcat RemoteIpValve.
server.forward-headers-strategy=native

# Example for a single proxy hop running on localhost.
# In .properties, two backslashes -> one regex backslash after parsing.
server.tomcat.remoteip.internal-proxies=127\\.0\\.0\\.1
server.tomcat.remoteip.remote-ip-header=x-forwarded-for
server.tomcat.remoteip.protocol-header=x-forwarded-proto
server.tomcat.remoteip.host-header=x-forwarded-host
server.tomcat.remoteip.port-header=x-forwarded-port

# When TLS terminates at the proxy, avoid premature context-root redirects.
server.tomcat.redirect-context-root=false
```

**Important note:** `internal-proxies` is chosen for **the demo's single loopback hop**, not as a universal regex. In real deployments, replace it with the appropriate proxy peer/network rather than trusting the entire private network by default. Binding `server.address=127.0.0.1` only works when NGINX and the backend share the same host/net namespace; in Kubernetes/Docker across networks, use internal binds, firewalls, and matching policies.

**`src/main/java/com/example/proxytrust/ProxyTrustApplication.java`:**

```java
package com.example.proxytrust;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@SpringBootApplication
public class ProxyTrustApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProxyTrustApplication.class, args);
    }
}

@RestController
class ProxyDiagnosticController {

    @GetMapping("/inspect")
    RequestView inspect(HttpServletRequest request) {
        String exampleLink = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/done")
                .toUriString();

        return new RequestView(
                request.getScheme(),
                request.isSecure(),
                request.getServerName(),
                request.getServerPort(),
                request.getRemoteAddr(),
                exampleLink);
    }

    @GetMapping("/done")
    ResponseEntity<String> done() {
        return ResponseEntity.status(HttpStatus.OK).body("done");
    }
}

record RequestView(
        String scheme,
        boolean secure,
        String host,
        int port,
        String remoteAddress,
        String exampleLink) {}
```

There is only one top-level `public class` in the Java file; package-private `ProxyDiagnosticController` and `RequestView` are valid. `ServletUriComponentsBuilder` is used on the **diagnostic** endpoint to reveal differences between the internal URL and the public URL. Never use an unallowlisted request-host-derived URL for OAuth callbacks, password resets, or sensitive actions.

**Run the app:**

```bash
gradle bootRun
```

If you have the Gradle Wrapper, you can use `./gradlew bootRun` (Linux/macOS) or `.\gradlew.bat bootRun` (Windows PowerShell). Requires JDK 17+ and a Gradle version compatible with Boot 3.3.x.

Sending a direct local request to the backend:

```bash
curl -s http://127.0.0.1:8080/inspect
```

Without forwarded headers, the JSON response reflects the local HTTP connection. Key fields typically look like:

```json
{
  "scheme": "http",
  "secure": false,
  "host": "127.0.0.1",
  "port": 8080,
  "remoteAddress": "127.0.0.1",
  "exampleLink": "http://127.0.0.1:8080/done"
}
```

This is **illustrative output**, depending on the hostname `curl` sends, IPv4/IPv6 loopback address, and server implementation. Do not assert unrelated environment-specific strings such as a loopback IP across different environments.

**Warning about direct tests:** because the demo is configured to **trust the loopback peer**, any local process can call port 8080 directly and **spoof forwarded headers itself**. This does not mean the backend is safe against an attacker with local access; it only simulates NGINX running on the same host. In production, restrict **who can connect to the backend** and define a threat model for all processes in the same network namespace.

## 7. NGINX example: overwrite headers, do not pass client values through

In a single-hop setup:
- External HTTP clients connect to **edge NGINX**.
- NGINX validates the permitted host and builds a **standardized header set**.
- Spring Boot accepts connections only from NGINX.
- The application uses `server.forward-headers-strategy=native` as configured in section 6.

The following **local lab** NGINX example belongs inside NGINX's `http { ... }` block, not as a standalone `nginx.conf` file:

```nginx
# Unmatched hosts will not reach the app.
server {
    listen 127.0.0.1:8088 default_server;
    server_name _;
    return 421;
}

server {
    listen 127.0.0.1:8088;
    server_name localhost;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;

        # Fixed host for the valid virtual host.
        proxy_set_header Host localhost;

        # Use only the X-Forwarded family regenerated by NGINX.
        # Do not pass client-sent RFC Forwarded headers through.
        proxy_set_header Forwarded "";

        # Single edge hop: replace, DO NOT append to client-sent headers.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host localhost;
        proxy_set_header X-Forwarded-Port $server_port;

        # Strip metadata outside the demo's policy.
        proxy_set_header X-Forwarded-Prefix "";
        proxy_set_header X-Forwarded-Ssl "";
        proxy_set_header X-Forwarded-Server "";
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**Key points:**
- `proxy_set_header X-Forwarded-For $remote_addr` **replaces** the value with the socket address NGINX actually observes. Unlike `$proxy_add_x_forwarded_for`, client-supplied values **are not appended into the chain**. This is the clean choice when NGINX is the **first edge**, with no legitimate proxy ahead of it.
- `proxy_set_header Forwarded ""` and empty-valued headers are **not forwarded upstream** by NGINX. This prevents conflicts between RFC `Forwarded` and NGINX-normalized `X-Forwarded-*`.
- `X-Forwarded-Proto=$scheme` uses the scheme NGINX actually received, not a client-provided `X-Forwarded-Proto`. In the HTTP 8088 lab, that value must be `http`; on TLS-terminating NGINX, it will be `https`.
- `Host localhost` and `X-Forwarded-Host localhost` use a fixed value rather than raw `$http_host` sent by the client. When serving multiple hostnames, maintain an explicit **allowlist/virtual host routing** and set the validated host.
- `X-Forwarded-Port=$server_port` takes the port NGINX is listening on—8088 in the lab. If your deployment has port mapping or an external CDN, this may not be the external port; derive it from **trusted infrastructure**, not client-sent headers.
- A `default_server` configuration rejects unknown hosts; with TLS you must also check matching SNI/certificates and the HTTP authority contract, not just `server_name`.

This is an **internal HTTP lab** to isolate forwarded-header behavior, **not a public production config**. Real deployments need TLS termination, public ports, ingress protections, timeouts, size limits, security headers, and proper network permissions.

### 7.1. Verifying that NGINX does not preserve fake headers

With NGINX loaded and Spring Boot running:

```bash
curl -s \
  -H 'Forwarded: for=192.0.2.99;proto=https;host=attacker.invalid' \
  -H 'X-Forwarded-For: 192.0.2.99' \
  -H 'X-Forwarded-Host: attacker.invalid' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Port: 443' \
  -H 'Host: localhost' \
  http://127.0.0.1:8088/inspect
```

Expected server-processed metadata:

```json
{
  "scheme": "http",
  "secure": false,
  "host": "localhost",
  "port": 8088,
  "remoteAddress": "127.0.0.1",
  "exampleLink": "http://localhost:8088/done"
}
```

This is **illustrative output in an IPv4 loopback lab**; it can differ when NGINX/Java bind IPv6 or when the nginx config differs. What must be asserted is **no `attacker.invalid`**, the scheme did not flip to `https` from the spoofed request, and the port was not forced to 443. The client's `Forwarded` header was dropped; the client's `X-Forwarded-*` headers were overwritten.

Test a host not in the allowlist:

```bash
curl -i -H 'Host: attacker.invalid' \
  http://127.0.0.1:8088/inspect
```

Expect NGINX's `default_server` to return HTTP **421** without proxying to Spring Boot. In the lab, `421` is chosen by the NGINX config, not generated by Spring Boot.

### 7.2. Why can `$proxy_add_x_forwarded_for` be risky?

A very common directive:

```nginx
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

This variable builds the list by **keeping the existing `X-Forwarded-For` value and appending `$remote_addr`**. It fits specific positions/contracts in a multi-proxy chain, yet it is **insufficient** to strip client-declared data at the first edge. If a client sends `X-Forwarded-For: 192.0.2.99`, upstream can see `192.0.2.99, 198.51.100.25`. An application taking the leftmost token gets the forged IP.

The safe pattern at a single edge is **complete overwrite**. In multi-proxy setups, walk trusted hops **from the peer closest to the application outward**, accepting only authenticated/allowlisted hops. Never use "take the first token" as a global rule.

## 8. When TLS terminates at the proxy: preserve the right scheme and prevent broken redirects

Production typically looks like:

```text
Browser --HTTPS:443--> NGINX --HTTP:8080--> Spring Boot
                         │
                   X-Forwarded-Proto: https
                   X-Forwarded-Host: api.example.test
                   X-Forwarded-Port: 443
```

If Boot sees only the HTTP 8080 connection, it may:
- Generate `http://...` in `Location` redirects even though the user accessed HTTPS.
- Generate absolute URLs with the wrong scheme/port (affecting OAuth callbacks, email links, redirects).
- Evaluate `request.isSecure()` as false in Servlet-API-based logic.
- Leak internal hostnames/ports in links.
- Cause redirect loops when the proxy enforces HTTP→HTTPS while the backend redirects back.

On NGINX **actually terminating TLS**, emit headers from trusted metadata:

```nginx
# Configuration snippet for a controlled TLS server:
proxy_set_header X-Forwarded-Proto $scheme;      # https
proxy_set_header X-Forwarded-Host api.example.test;
proxy_set_header X-Forwarded-Port 443;
proxy_set_header Host api.example.test;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header Forwarded "";
```

This is only a **configuration snippet**; it needs `listen 443 ssl`, valid certificates/keys, `proxy_pass`, virtual host validation, and network ACLs. Do not paste it directly into NGINX as a standalone runnable file.

With **Spring Boot 3.3 + Tomcat**, `server.tomcat.redirect-context-root=false` is noted in Boot docs when SSL terminates at the proxy, so the protocol header is processed before context-root redirects. Use it alongside **proxy sanitization and trusted-peer constraints**; this property does not replace any security layer.

Never accept `X-Forwarded-Proto: https` as proof of an HTTPS connection from a direct non-proxied client, because an attacker can write it themselves. Likewise, never assume from an unvalidated `X-Forwarded-Host` that a redirect URI belongs in an allowlist.

## 9. Multi-hop proxies: IP selection principles and trust policies

Example:

```text
Client 198.51.100.25
      │
      ▼
CDN proxy 203.0.113.10
      │
      ▼
Ingress proxy 10.0.0.10
      │
      ▼
App 10.0.1.20
```

From the app's perspective, the physical socket peer is usually `10.0.0.10`, while `X-Forwarded-For` may carry a list. If the CDN and ingress **both belong to the trust policy** and sanitization happens at the edge, the valid hop chain can be preserved. If the CDN is outside the policy or clients can bypass the CDN, the list must be re-evaluated.

**Safe reasoning algorithm:**
1. Identify the **nearest socket peer**: is it a proxy the app permits?
2. If you do not trust the peer, **do not use forwarded headers** for security decisions.
3. If you trust the peer, examine values that the peer is guaranteed to have sanitized/overwritten; for multi-hop chains, define clear rules for intermediate IPs.
4. When parsing `X-Forwarded-For`, inspect hops from nearest the app outward, **stopping at the first untrusted hop** per your library/ingress contract. Never treat the leftmost IP as verified.
5. Verify `Host`/`Proto`/`Port` at authoritative sources, not just IPs. A trusted IP chain does not automatically make any forwarded host domain permissible.

Tomcat `RemoteIpValve` supports `internalProxies`/`trustedProxies` for multi-hop networks; each version has its own syntax and behavior. With NGINX behind a CDN, if using `real_ip_header`/`set_real_ip_from`, configure **exact, up-to-date CDN IP ranges** and avoid `set_real_ip_from 0.0.0.0/0`. Note that `$remote_addr` may then already be rewritten by the realip module along the proxy chain, so test specifically rather than assuming it is always the raw socket peer.

Never use untrusted sources such as raw `X-Forwarded-For`, `X-Real-IP`, or `Forwarded` as **proof of administrative privilege**. If IP allowlisting is a genuine requirement, enforce it at the edge/firewall before reaching the app or use a compliant trusted-proxy module, with spoofing tests and audits.

## 10. FRAMEWORK on MVC and WebFlux: URL handling is not proxy authentication

When `NATIVE` is insufficient (for example, the proxy sends `X-Forwarded-Prefix` or native server support is limited), Boot offers:

```properties
server.forward-headers-strategy=framework
```

- **Spring MVC/Servlet:** `ForwardedHeaderFilter` creates request/response wrappers so APIs such as `getScheme()`, `getServerName()`, `getServerPort()`, `isSecure()`, and `sendRedirect(...)` reflect forwarded metadata.
- **Spring WebFlux:** `ForwardedHeaderTransformer` adjusts reactive `ServerHttpRequest` from forwarded metadata before the processing pipeline runs.

**Security takeaway:** the filter/transformer **cannot determine on its own** whether a header came from a controlled proxy or directly from a client. Spring Framework recommends that proxies at the **trust boundary** strip external `Forwarded` and `X-Forwarded-*` headers.

`removeOnly=true` only **removes** headers (without applying them). It can be useful when the app distrusts them. However, if you simply want to ignore forwarded headers with no proxy, prefer `NONE`, and if an edge proxy exists, sanitize right at the edge. Avoid enabling `NATIVE` + an uncontrolled custom `ForwardedHeaderFilter` simultaneously, which can double-rewrite requests or give inconsistent security views.

`FRAMEWORK` can make URLs look right inside the application, yet it does not validate client IP/hop chains on behalf of ingress. **Security depends on topology and proxy controls**, not the word `FRAMEWORK`.

## 11. Building URLs and redirects: how to prevent Host-header poisoning

Libraries building absolute URLs from request metadata may read `Host`, `scheme`, and `port` after forwarded processing. If those values are attacker-controlled, the system can:
- Send password-reset links pointing to a fake domain.
- Generate an OAuth `redirect_uri` outside the whitelist, causing errors or unintended flows.
- Emit a `Location` redirect response to a fake host.
- Generate wrong canonical URLs and cache keys, causing cache poisoning.
- Reference APIs/images from a rogue hostname in HTML/emails.

Risk mitigations:

1. **Allowlist hosts at the edge** (HTTP `Host` and HTTP/2 `:authority`, plus TLS SNI validation where applicable).
2. **Overwrite `X-Forwarded-Host`** with a verified hostname rather than forwarding raw `$http_host` unvalidated.
3. For sensitive URLs, **configure an explicit public base URL**, for example:

```properties
app.public-base-url=https://api.example.test
```

Instead of concatenating `request.getServerName()` or `request.getHeader("X-Forwarded-Host")` into verification links, read from operator-controlled config; avoid putting sensitive tokens in URLs when safer alternatives exist, and never log full URLs containing tokens.

4. When navigating within the same origin, prefer **relative-path redirects** per client/framework contract when an absolute URL is unnecessary. This reduces hostname dependence, though redirect/filter behavior should still be checked per version.
5. For callbacks/OAuth, register and match **fixed/allowlisted redirect URIs**. Never treat a forwarded host that "looks like an internal domain" as sufficient.
6. If `X-Forwarded-Prefix` is used for path rewriting, the proxy must generate the prefix from valid routes and strip client-supplied values. Never let clients shift the app to an arbitrary base path.

**No single "host filtering" middleware fits every system.** The proxy/gateway should be the authoritative public-host enforcer; the application still needs to validate public URLs used in sensitive workflows.

## 12. Proxy and CORS: two different trust models

The parent topic includes **Proxy and CORS**, so keep them distinct:

- **Forwarded headers:** describe connection metadata through a proxy; requires a **trusted proxy boundary**.
- **CORS `Origin`:** browser reports which origin initiated fetch/XHR and enforces policy in the browser. The `Origin` header itself can be forged by non-browser clients; it is **not an authentication mechanism**.
- **CSRF:** attacker abuses a browser holding credential cookies to send requests; a CORS allowlist must not be treated as a full replacement for CSRF protection.
- **Authorization:** relies on trustworthy identity/roles/scopes, not a client-declared `X-Forwarded-For`.

A dangerous mistake is automatically granting `Access-Control-Allow-Origin`/`Access-Control-Allow-Credentials` based on `X-Forwarded-Host` or any incoming `Origin`. Allowed origins should be configured for real public origins, never blindly "reflecting" whatever host was sent. Proper proxy trust is necessary, yet it **does not fix a broken CORS policy**.

For instance, service public origins must be explicitly allowlisted such as `https://app.example.test`, distinct from the backend host `api.example.test`. If cross-site cookies are used, also consider `SameSite`, `Secure`, CSRF, credentials, and TLS.

## 13. Testing against header spoofing

The best testing combines two layers: **Boot unit/integration tests** without a proxy, and **end-to-end tests through a real proxy** as in section 7.

### 13.1. JUnit + MockMvc: with NONE, forged headers do not alter metadata

Create `src/test/java/com/example/proxytrust/ForwardedHeadersIgnoredTest.java`:

```java
package com.example.proxytrust;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "server.forward-headers-strategy=none"
})
@AutoConfigureMockMvc
class ForwardedHeadersIgnoredTest {

    @Autowired
    MockMvc mvc;

    @Test
    void spoofedHeadersDoNotOverrideSchemeOrHost() throws Exception {
        mvc.perform(get("/inspect")
                        .header("Forwarded",
                                "for=192.0.2.99;proto=https;host=attacker.invalid")
                        .header("X-Forwarded-Host", "attacker.invalid")
                        .header("X-Forwarded-Proto", "https")
                        .header("X-Forwarded-For", "192.0.2.99")
                        .header("X-Forwarded-Port", "443"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.scheme").value("http"))
                .andExpect(jsonPath("$.secure").value(false))
                .andExpect(jsonPath("$.host").value("localhost"));
    }
}
```

Run:

```bash
gradle test
```

With `server.forward-headers-strategy=none` and no custom filter processing forwarded headers, Spring MVC sees `MockMvc`'s default metadata: `scheme=http`, `secure=false`, and `host=localhost` even when the request carries fake headers. The test is expected to pass.

**Test limitation:** `MockMvc` does not run through a real proxy and does not simulate Tomcat `RemoteIpValve` at the socket level. It only verifies the app does not accept forwarded headers on its own in `NONE` mode. **The most important test for a `NATIVE` deployment is through the real proxy**, covering both client-sent `Forwarded`/`X-Forwarded-*` and attempts to reach the backend directly from untrusted sources.

### 13.2. Test matrix recommended for CI/staging

| Case | What should happen |
|---|---|
| Client sends `Forwarded: host=attacker.invalid` to public edge | Proxy strips it; backend never sees the rogue hostname |
| Client sends `X-Forwarded-Proto: https` to HTTP edge | Proxy overwrites with the scheme it observes; app does not treat request as TLS |
| Client sends `X-Forwarded-For: 192.0.2.99` | App does not use the fake IP to bypass allowlists/rate limits |
| Client sends Host outside public allowlist | Edge rejects, does not route to app |
| Client attempts direct backend connection from Internet | Firewall/NetworkPolicy blocks it, not merely returning a different status |
| Valid proxy sends accurate HTTPS host/port | App generates links/redirects with the right public URL |
| Conflicting `Forwarded` and `X-Forwarded-*` headers | Edge retains only the policy-approved family; no inconsistent rewriting |
| Two proxy hops, one outside trust allowlist | Algorithm stops at the trust boundary; does not accept far-side self-declared IPs |
| Rollout changes ingress, proxy CIDRs, or hostnames | Trust-boundary tests re-run; `internal-proxies` is not broadened unconditionally |
| HTTP/2 client sends invalid `:authority` | Edge validates host/authority before forwarding to backend |

Do not bake an assumption like "IP is always the first element of `X-Forwarded-For`" into tests. Verify values derived from **verified connection peers and proxy chains**.

## 14. Observability, operations, and misconfiguration response

Logs and metrics should distinguish:
- **Socket peer IP**: who connected directly to the backend; from network accept/access logs prior to rewriting where available.
- **Derived client IP**: IP after forwarded-header processing and trusted-proxy policy, usable for analytics/rate limits at the appropriate layer.
- **External host/scheme/port**: edge-verified values; never dump raw attacker-controlled headers unescaped into logs.
- **Forwarded-header anomalies**: client-sent headers rejected by proxy, conflicting header families, non-allowlisted hosts, overly long IP chains.
- **Deployment topology/version**: ingress controller release, proxy IP allowlist, Spring Boot config, Tomcat vs. Netty, and network policies.

With managed CDNs or load balancers, IP ranges can change per provider; update them through a controlled process rather than hastily opening trust to the entire private network or the whole Internet during an incident.

When spoofing is suspected:
1. Check whether direct paths to the backend exist; audit network ACLs and public service exposure.
2. Check whether the edge **strips both `Forwarded` and all untrusted `X-Forwarded-*`** or is appending to client strings.
3. Check which `NONE/NATIVE/FRAMEWORK` mode Boot actually runs, which embedded server is used, and which trusted-proxy pattern applies.
4. Compare socket peer IP with derived client IP at a secure inspection point; do not expose this via a public debug endpoint.
5. Test Host/Proto/For/Port/Prefix spoofing through the public ingress, along with redirects and related auth flows.
6. If reset links/callback URLs were poisoned, review logs/emails/caches and respond per your organization's security incident process—not just by changing one property.

In logging, user-supplied values may contain control characters or forged data; log structured/escaped fields and bound length to prevent log injection or unbounded metric cardinality.

## 15. Common errors table

| Symptom | Cause | Remediation |
|---|---|---|
| App generates `http://internal:8080` links instead of public HTTPS | Trusted `X-Forwarded-Proto/Host` not received/applied | Configure edge sanitization, Boot strategy, and valid host |
| Enabled `FRAMEWORK` and hit Host poisoning | Public backend or proxy passes client headers through | Block direct access, strip/overwrite at edge, restrict hosts |
| `request.getRemoteAddr()` can be a forged IP | Overly broad trusted-proxy pattern or wrong XFF token | Inspect socket peer, `RemoteIpValve`/ingress trusted hops |
| HTTP↔HTTPS redirect loop | Backend unaware of external scheme while proxy enforces HTTPS | Ensure accurate `X-Forwarded-Proto` from proxy and review redirect config |
| `server.tomcat.remoteip.internal-proxies` has no effect | Running `FRAMEWORK`/Netty instead of Tomcat `NATIVE` | Check runtime stack and pick matching config |
| WebFlux sees wrong host even though proxy sends headers | Framework transformer/native support disabled or headers stripped | Check Boot strategy and ingress routing |
| CORS preflight fails | Wrong Origin/CORS policy, not forwarded headers | Configure CORS allowlist and credentials properly |
| OAuth callback hostname changes | Reading host from unverified header | Pin/allowlist public redirect URI; avoid raw forwarded host |
| Cookie `Secure` behaves unexpectedly | App thinks request is HTTP after TLS termination | Verify trusted proto, HTTPS termination, and cookie policy |
| IP-based rate limit ineffective | Trusting client-supplied leftmost XFF | Rate-limit at edge or use a trusted-hop parser |
| Requests via CDN lose client IP | Edge/ingress overwrites without recognizing trusted CDN | Configure CDN real-IP from real IP ranges and chain contract |
| Invalid Host still reaches backend | NGINX default server does not reject, fallback route | Add virtual-host allowlist and check `Host/:authority` |

## 16. Secure deployment checklist

- [ ] Documented trust-boundary diagram: browser/CDN/edge/ingress/service/backend.
- [ ] Backend not directly reachable from sources outside trusted proxies.
- [ ] Edge strips client-declared forwarded data: **`Forwarded` and `X-Forwarded-*`**.
- [ ] Edge **generates** `For`, `Proto`, `Host`, `Port`, `Prefix` from verified routes/connections.
- [ ] Do not use `$proxy_add_x_forwarded_for` at a public edge as a default sanitizer.
- [ ] Explicitly choose `server.forward-headers-strategy=NONE/NATIVE/FRAMEWORK`.
- [ ] With Tomcat `NATIVE`, restrict `internal-proxies`/`trusted-proxies` rather than trusting the whole private network unnecessarily.
- [ ] No code reads raw `X-Forwarded-For` directly for authorization or security decisions.
- [ ] Public hosts and sensitive redirect URIs are configured/allowlisted, not taken from arbitrary `Host` headers.
- [ ] CORS, authentication, and CSRF are configured independently; never treat CORS as proof of proxy trust.
- [ ] Test Host/For/Proto/Port/Forwarded/Prefix spoofing and direct-backend bypass.
- [ ] Monitor redirects, HTTPS detection, proxy IP range changes, logs, and anomaly alerts.

## 17. Official documentation

1. Spring Boot 3.3 — **Running Behind a Front-end Proxy Server**, `NATIVE`/`FRAMEWORK`, Tomcat `RemoteIpValve`, and `redirect-context-root`: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
2. Spring Boot 3.3 — **Common Application Properties**, `server.forward-headers-strategy`, `server.tomcat.remoteip.*`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
3. Spring Framework 6.1 — **ForwardedHeaderFilter** and `removeOnly`: https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html
4. Spring Framework 6.1 — **ForwardedHeaderTransformer** for WebFlux: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/server/adapter/ForwardedHeaderTransformer.html
5. RFC 7239 — **Forwarded HTTP Extension**, Security Considerations `8.1`: https://www.rfc-editor.org/rfc/rfc7239.html
6. NGINX — `proxy_set_header`, empty-value behavior, and host headers: https://nginx.org/en/docs/http/ngx_http_proxy_module.html
7. Apache Tomcat — `RemoteIpValve`, proxy chain, and `internalProxies/trustedProxies`: https://tomcat.apache.org/tomcat-10.1-doc/config/valve.html

**Conclusion:** forwarded headers are merely **claims on the request** until they cross a **controlled proxy boundary**. The proxy itself must strip malicious headers and generate metadata from verified connections, and the backend must accept traffic only from that proxy. Spring Boot processes forwarded headers behind that boundary to build accurate URLs and redirects; it is not a replacement for network access control, host allowlists, CORS policy, or authorization.