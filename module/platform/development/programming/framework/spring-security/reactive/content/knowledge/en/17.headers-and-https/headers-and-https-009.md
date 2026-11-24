# Handling Forwarded, X-Forwarded-*, and Proxy Trust Boundaries

## 1. Why Can an External HTTPS Request Become HTTP in WebFlux?

In a Spring Security reactive system using Spring WebFlux, the application often does not terminate TLS connections directly from the browser. A CDN, WAF, load balancer, or reverse proxy may terminate HTTPS at the network edge and forward requests over internal HTTP to Reactor Netty:

~~~text
Browser
    │
    │ GET https://app.example.com/account
    │ TLS, HTTP/2 or HTTP/1.1
    ▼
┌──────────────────────────────┐
│ Edge / Reverse Proxy         │
│ - Verify TLS/Host            │
│ - Strip spoofed Forwarded    │
│ - Write verified headers     │
└──────────────┬───────────────┘
               │
               │ GET http://10.0.0.12:8080/account
               │ Host: app.example.com
               │ X-Forwarded-Proto: https
               │ X-Forwarded-Host: app.example.com
               │ X-Forwarded-For: 198.51.100.27
               ▼
┌──────────────────────────────┐
│ Spring Boot WebFlux          │
│ Reactor Netty                │
│ ForwardedHeaderTransformer   │
│ Spring Security WebFilters   │
│ Controller / handler         │
└──────────────────────────────┘
~~~

At the backend connection layer, the request arriving at `10.0.0.12:8080` is HTTP. From the client's perspective, however, the public URL is `https://app.example.com/account`. This difference affects:

- Scheme/host/port of absolute URLs in redirects, email links, and API docs.
- Determining whether a request is HTTPS-secure for HSTS and certain cookie policies.
- Path prefix handling when the app is published under `/gateway` or `/myapp`.
- Client IP in logs, auditing, rate limiting, and network-based policies.
- Origin/CSRF checks, CORS, and OAuth2/OIDC redirect URIs.
- Risks of **Host header poisoning**, open redirects, and IP spoofing if clients are allowed to control forwarded headers.

Spring Framework and Spring Boot support restoring original request details, **yet the application cannot tell on its own whether a `Forwarded` header was created by a trusted proxy or forged by a malicious client**. Therefore, **the trust boundary must be enforced at the infrastructure layer** before allowing the backend to consume these headers.

### Lesson Objectives

1. Read RFC 7239 `Forwarded` and common `X-Forwarded-*` headers accurately.
2. Understand both perspectives: the physical proxy → backend connection and the public browser → proxy URL.
3. Configure `server.forward-headers-strategy=none/native/framework` in Spring Boot WebFlux 3.3.
4. Use WebFlux's `ForwardedHeaderTransformer` and `removeOnly` mode when headers should not be trusted.
5. Configure reverse proxies to emit headers solely from verified data and **strip both client-sent `Forwarded` and `X-Forwarded-*`**.
6. Recognize spoofing attacks targeting `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-For`, and `X-Forwarded-Prefix`.
7. Distinguish forwarded metadata from authentication, authorization, CSRF, CORS, and real TLS.
8. Run a Java 17+ Spring Boot WebFlux example verifying the app **accepts metadata when FRAMEWORK mode is enabled**, while demonstrating why the backend must never be exposed directly.

## 2. Key Headers and Their Exact Meanings

### 2.1. RFC 7239 Standard: `Forwarded`

RFC 7239 defines a single header capable of carrying multiple attributes per hop:

~~~http
Forwarded: for=198.51.100.27;proto=https;host=app.example.com
~~~

Common parameters:
- `for=`: the client/prior-hop address recorded by the proxy; may be IPv4, properly quoted IPv6, or an obfuscated identifier.
- `by=`: address/identifier of the proxy interface that received the request, if populated by the proxy.
- `proto=`: scheme reported by the proxy, e.g., `https`.
- `host=`: external host (and optionally port) requested by the client.

Multiple comma-separated entries may exist across multiple proxies:

~~~http
Forwarded: for=198.51.100.27;proto=https;host=app.example.com, for=10.0.0.7;by=10.0.0.9
~~~

**Never treat the first entry or every value in this header as verified proof.** If a trusted proxy merely *appends* without stripping client-sent headers, an attacker can inject the first entry and mislead the application about the request's origin.

For IPv6, parsers must obey quoting/bracket rules rather than naively splitting on `:` or commas everywhere. **Never write custom regexes to parse `Forwarded` for access control**; rely on supported proxies/infrastructure and libraries with explicit trust bounds.

### 2.2. Common `X-Forwarded-*` Family

| Header | Intended meaning | Risk when trusting client data |
| --- | --- | --- |
| `X-Forwarded-For` | Chain of client and intermediate proxy IPs | Spoofing IP to bypass rate limits, corrupt audits, or evade IP allowlists |
| `X-Forwarded-Proto` | Client-facing scheme, e.g., `https` | Misleads HTTP/HTTPS detection; wrong redirects, cookies, HSTS |
| `X-Forwarded-Host` | Public host called by client | Poisons absolute URLs, password-reset links, redirects to attacker domains |
| `X-Forwarded-Port` | External port, e.g., 443 | Wrong URLs/redirects, callback URIs, origin/port mismatches |
| `X-Forwarded-Prefix` | Public route prefix when proxy rewrites paths | Broken links/base paths, attacker-controlled prefix redirects |
| `X-Forwarded-Ssl` | SSL indicator from some legacy proxies | Easy way to spoof TLS state if the edge does not filter it |

An internal request might carry:

~~~http
GET /account HTTP/1.1
Host: 10.0.0.12:8080
X-Forwarded-Host: app.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-For: 198.51.100.27
~~~

These headers are not client "certificates." They are merely HTTP text until a **trusted proxy** guarantees their provenance and accuracy.

Moreover, the `Host` header itself can be chosen by external clients. Never assume that stripping `X-Forwarded-Host` guarantees `Host` is valid; the ingress must validate hostnames or enforce a canonical host on traffic entering the app.

### 2.3. `Forwarded` and `X-Forwarded-*` Can Conflict

Example dangerous request:

~~~http
Forwarded: for=203.0.113.10;proto=http;host=evil.example
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.com
~~~

Do not expect every middleware to resolve conflicts in the same precedence order, especially across versions or HTTP stacks. **Infrastructure design must strip both header families from clients** and emit only the header family the backend is configured to consume, with verified values.

A proxy that strips `Forwarded` while letting `X-Forwarded-Host` slip through—or vice versa—still leaves a spoofing hole.

## 3. Where Does the Trust Boundary Live?

### 3.1. Unsafe Scenario: Clients Send Headers Directly to the Backend

~~~text
Attacker
   │
   │ GET http://public-app:8080/internal/request-view
   │ X-Forwarded-Proto: https
   │ X-Forwarded-Host: evil.example
   ▼
Spring Boot configured with FRAMEWORK
   │
   └─ App may perceive the request as https://evil.example/
      if the backend accepts unsanitized headers.
~~~

If an application enables `ForwardedHeaderTransformer` while its backend port remains publicly reachable, a client can bypass the proxy and forge "trusted" metadata directly. The framework **has no independent way** to verify whether a header came from a proxy or an attacker.

**Thus, backend forwarded-header configuration is safe only when the network boundary is also sound.** Key protections:
1. Allow traffic to the backend solely from approved proxies/ingresses (firewall, security group, NetworkPolicy, private service).
2. Public proxies **strip or overwrite** all client-supplied `Forwarded` and `X-Forwarded-*` headers.
3. Proxies emit fresh metadata solely from the scheme/host/client address they actually observed.
4. Protect proxy → backend connections from untrusted sources; consider internal TLS/mTLS for high-risk workloads.
5. Configure the backend to process only the headers designed and proven to come from the trusted proxy.

### 3.2. Correct Scenario: Edge Normalizes Metadata

~~~text
Internet
   │
   │ Client may send:
   │   Forwarded: proto=http;host=evil.example
   │   X-Forwarded-Host: evil.example
   │   X-Forwarded-For: 127.0.0.1
   ▼
TRUST BOUNDARY: public proxy
   ├─ Reject hostnames not in allowlist
   ├─ Strip client-sent Forwarded
   ├─ Strip all client-sent X-Forwarded-*
   ├─ Set X-Forwarded-Proto = verified scheme
   ├─ Set X-Forwarded-Host = verified canonical host
   ├─ Set X-Forwarded-For = verified connection IP
   └─ Forward request to private backend
                    │
                    ▼
         WebFlux ForwardedHeaderTransformer
         ├─ Restore URI scheme/host/port
         └─ Strip forwarded headers before handler
                    │
                    ▼
          Spring Security + business handler
~~~

**Core rule:** only the component capable of verifying the external connection may decide forwarded values. Application-layer frameworks never replace edge validation.

### 3.3. Multiple Proxies in Sequence

Example:

~~~text
Browser → CDN → WAF → ingress → Spring WebFlux
~~~

Clearly identify which proxy is the **first point where Internet traffic is no longer trusted**, which proxies are trusted to emit `X-Forwarded-For`, and how many hops are permitted. If an ingress simply appends `$proxy_add_x_forwarded_for` while a CDN failed to sanitize client headers, the left side of the chain may contain forged data.

The rule "the real IP is always the first value in X-Forwarded-For" **holds only in properly configured topologies**, not as a universal security truth. With multiple hops, extracting the client IP must rely on the trusted proxy set, right-to-left chain traversal, and validated entry points; never use `split(",")[0]` for sensitive authorization decisions.

Nor is `X-Real-IP` automatically trustworthy if clients can pass it through the edge. Ingress/network policy matters more than header names.

## 4. Spring Boot 3.3 Configuration: none, native, framework

Spring Boot 3.3 provides the property:

~~~properties
server.forward-headers-strategy=framework
~~~

Three strategies:

| Value | Meaning | When to consider |
| --- | --- | --- |
| `none` | Disables Boot's auto-configured forwarded-metadata handling | Backend needs no proxy metadata, or trust boundary is not yet established |
| `native` | Delegates forwarded-header handling to the HTTP server/container | Server/proxy natively supports it; check implementation-specific trust rules |
| `framework` | Uses Spring Framework infrastructure; in WebFlux this is `ForwardedHeaderTransformer` | Need to restore request scheme/host/port in WebFlux once edge sanitizes headers |

Trusted-proxy profile example:

~~~properties
# Enable ONLY when backend is blocked from direct Internet access
# and the reverse proxy strips all untrusted forwarded headers.
server.forward-headers-strategy=framework
~~~

Untrusted/direct profile example:

~~~properties
# Do not accept forwarded values from public requests.
server.forward-headers-strategy=none
~~~

**Do not assume defaults are identical across every environment.** Spring Boot may pick a different default strategy when detecting certain cloud platforms. In production, **set it explicitly** and inspect the effective configuration at runtime.

The `native` option must be tested per server: Reactor Netty, reactive Tomcat, and reactive Jetty have different mechanisms and limitations. When running Reactor Netty in WebFlux, never copy Servlet-Tomcat-only properties like `server.tomcat.remoteip.internal-proxies` assuming they govern Netty.

**Crucial point:** `framework`, `native`, and `none` describe **how the backend consumes metadata**; they do not create a firewall, enforce that requests come from a trusted proxy, validate HMACs/JWTs, or strip client headers at the Internet edge.

### 4.1. Do Boot `framework` and a Custom Bean Differ?

In Spring Framework WebFlux, `ForwardedHeaderTransformer` can be registered manually under the exact bean name `forwardedHeaderTransformer`. Configuring `server.forward-headers-strategy=framework` in Spring Boot wires up the corresponding mechanism.

There is no reason to enable Boot's strategy and simultaneously copy-paste a custom transformer bean without cause. Doing so can alter which bean wins or make configuration confusing. Pick one clear mechanism and test it.

**Alternative snippet**, not part of the runnable project below:

~~~java
@Bean(name = "forwardedHeaderTransformer")
ForwardedHeaderTransformer forwardedHeaderTransformer() {
    return new ForwardedHeaderTransformer();
}
~~~

This is a **code excerpt** for Spring Framework 6.1.x requiring imports for `org.springframework.web.server.adapter.ForwardedHeaderTransformer` and `org.springframework.context.annotation.Bean`. In newer Spring Framework lines, constructors or header-selection methods may evolve; verify against your exact version.

### 4.2. `removeOnly`: Stripping Headers Without Trusting Metadata

If an application **has no trusted proxy** yet still wants forwarded headers stripped before downstream components see them, Spring Framework provides:

~~~java
@Bean(name = "forwardedHeaderTransformer")
ForwardedHeaderTransformer forwardedHeaderTransformer() {
    ForwardedHeaderTransformer transformer =
        new ForwardedHeaderTransformer();

    transformer.setRemoveOnly(true);
    return transformer;
}
~~~

This is an **alternative configuration**; do not blindly enable it alongside Boot's `framework` mode. When `removeOnly=true`:
- `Forwarded` and recognized `X-Forwarded-*` headers are stripped from the request.
- The original connection URI is not rewritten from those headers.
- Downstream application code cannot accidentally read forged metadata from headers already stripped by the transformer.

Note that `removeOnly` does not identify clients or proxies. If your app sits behind a real proxy and needs accurate absolute URLs, you cannot simultaneously **discard all forwarded metadata** and expect the framework to deduce external HTTPS from an internal HTTP socket.

For systems needing upstream anti-spoofing, still protect at the proxy **even if** `removeOnly` is active in the app; never mistake an application sanitizer for an ingress trust policy.

## 5. Behavior of WebFlux `ForwardedHeaderTransformer`

The WebFlux component resides at:

~~~java
org.springframework.web.server.adapter.ForwardedHeaderTransformer
~~~

It processes requests **before** building/passing the exchange through most WebFilters and controllers, so request APIs observe the restored metadata (when trusted). Afterward, forwarded headers are removed from the transformed request to avoid downstream interference.

Effects may include:
- `request.getURI().getScheme()`: from internal HTTP to public HTTPS.
- `request.getURI().getHost()`: from backend address to public host.
- `request.getURI().getPort()`: public port, or `-1` when using the default/omitted port.
- `request.getRemoteAddress()`: may reflect forwarded source depending on implementation and headers; never treat it as an authenticated IP just because the API returns it.
- `X-Forwarded-Prefix`: in supporting versions/configs, can affect context/base paths used to construct links/routes.

**Never use** `request.getSslInfo()` as proof of direct TLS with the browser when TLS terminates at a proxy: the app socket sees HTTP even though the public URL uses HTTPS. Distinguish physical socket TLS from edge-verified metadata.

**Never use** Servlet's `ForwardedHeaderFilter` as the primary filter for WebFlux; Spring Framework WebFlux uses `ForwardedHeaderTransformer`. This is a stack difference, not just a class name.

### 5.1. Before-and-After Example

Suppose the browser requests:

~~~text
https://app.example.com/account
~~~

The proxy sends to the app:

~~~http
GET /account HTTP/1.1
Host: backend.internal:8080
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.com
X-Forwarded-Port: 443
~~~

Inside the backend before processing, the logical URI is typically:

~~~text
http://backend.internal:8080/account
~~~

Once the transformer is enabled and headers are genuinely trusted:

~~~text
https://app.example.com/account
~~~

This makes links and redirects reflect the public address, yet **does not encrypt the backend connection itself**. Network isolation/appropriate TLS is still needed between proxy and backend.

### 5.2. Easily Overlooked: `X-Forwarded-Prefix`

Suppose a proxy publishes:

~~~text
https://app.example.com/gateway/orders/123
~~~

While the backend receives:

~~~text
http://orders-service:8080/orders/123
~~~

A proxy can emit `X-Forwarded-Prefix: /gateway` so WebFlux constructs matching URLs. However:
- The prefix must be assigned by the proxy from verified routing config, never chosen arbitrarily by clients.
- Proxy and backend must agree on stripping/preserving prefixes.
- Prefix support can vary by Spring Framework version, how the transformer is created, and `setUseForwardedPrefix` in newer API lines; check your exact version.
- Never make access-control decisions by matching unnormalized prefix strings.
- Test redirects and links thoroughly when deploying under a subpath to prevent double prefixes or missing prefixes.

If not publishing under a prefix, **do not let clients control `X-Forwarded-Prefix`**.

## 6. Impact on Spring Security: More Than Pretty URLs

### 6.1. Redirects and Absolute URLs

An application might generate a `Location` header or link like:

~~~http
HTTP/1.1 302 Found
Location: http://backend.internal:8080/login
~~~

If the backend does not know the public scheme/host, redirects can expose internal hosts/ports, breaking UX or leaking infrastructure topology. Conversely, trusting an untrusted `X-Forwarded-Host` allows an attacker to turn links into:

~~~http
HTTP/1.1 302 Found
Location: https://evil.example/login
~~~

This can lead to open redirects, phishing, password-reset link poisoning, or broken OAuth2/OIDC callbacks. The framework does not turn a forged `Host` into a trusted `Host`; the problem lies at the trust boundary.

**Recommendation:** for password-reset emails, OAuth2/OIDC callbacks, tokenized URLs, and sensitive absolute links, prefer an **explicitly configured and validated public base URL** (e.g., `https://app.example.com`) rather than concatenating directly from `request.getURI().getHost()`. For multi-tenant/multi-host setups, validate hosts against a trusted allowlist/mapping before generating links.

### 6.2. HTTPS, Redirect Loops, and HSTS

Proxies often terminate HTTPS and speak internal HTTP. If Spring Security or the app deems requests "insecure" solely from internal HTTP while the public edge is HTTPS, channel-redirect rules can cause a **redirect loop**:

~~~text
Browser HTTPS → proxy → backend HTTP
Backend thinks request is HTTP → redirects to HTTPS
Browser HTTPS → proxy → backend HTTP
... repeats
~~~

Once HTTPS metadata is restored accurately, the app recognizes the public URL. Yet never rely on forwarded headers to replace **the proxy enforcing HTTPS from the Internet**. Edge HTTP → HTTPS redirects should use validated hostnames and proper TLS.

HSTS (`Strict-Transport-Security`) instructs browsers to use HTTPS for known hosts. Spring Security supports security response headers; HSTS behavior depends on whether the request is recognized as secure and your security config. If the backend sees HTTP or responses traverse an edge proxy, verify end-to-end that browsers **actually receive HSTS over public HTTPS**; you can configure/enforce HSTS at the edge if that layer terminates TLS.

Never emit HSTS casually on hostnames not yet ready for HTTPS. Evaluate `includeSubDomains`/`preload` across the entire domain/subdomain tree due to long-lasting impact.

### 6.3. Secure Cookies, SameSite, and CSRF

Session cookies carry `Secure`, `HttpOnly`, `SameSite`, `Path`, and `Domain` attributes. When TLS terminates at a proxy, application configuration must align with **public HTTPS**, not internal HTTP.

Production WebFlux example:

~~~properties
# When browsers always connect over public HTTPS.
server.reactive.session.cookie.secure=true
server.reactive.session.cookie.http-only=true
server.reactive.session.cookie.same-site=lax
~~~

This is a threat-model-dependent recommendation, **not the local HTTP demo configuration**. `Secure` cookies are sent by browsers only over HTTPS; localhost/HTTP labs behave differently depending on the browser. `SameSite` is a cookie policy and does not replace CSRF tokens in all scenarios.

Important:
- Forwarded headers do not supply CSRF tokens or replace `CsrfWebFilter`.
- POST requests using sessions/HTTP Basic must still satisfy default CSRF when browser CSRF risk applies.
- Frontend CSRF tokens must use the proper repository and request handler.
- Edge HTTPS protects browser ↔ proxy, not necessarily proxy ↔ backend encryption or safety.
- Never log session cookies or CSRF tokens "to debug the proxy."

### 6.4. CORS and Origin Are Not Forwarded Headers

`Origin` is a distinct header used for CORS and CSRF origin checks, not a verified user or proxy identifier. CORS allowlists must enumerate **permitted public origins**; never construct allowlists from client-sent `X-Forwarded-Host`.

If origin checks rely on untrusted forwarded hosts:
- Attackers can spoof hosts and skew backend same-origin/cross-origin decisions.
- Redirects and CSRF Origin checks can break behind reverse proxies.
- Frontends suffer CORS errors because the backend perceives a different scheme/port than the browser.

A successful CORS response never grants authentication/authorization, and disabling CORS does not stop CSRF.

### 6.5. IP Addresses, Auditing, Rate Limiting, and `127.0.0.1` Spoofing

This is an extremely dangerous pattern:

~~~java
// ANTI-PATTERN: client headers can be forged.
String ip = request.getHeaders().getFirst("X-Forwarded-For");
if ("127.0.0.1".equals(ip)) {
    // GRANT ADMIN ACCESS -- NEVER DO THIS!
}
~~~

A direct request sending:

~~~http
X-Forwarded-For: 127.0.0.1
~~~

does not make the client a trusted loopback caller. IPs used for rate limiting, auditing, or alerting are useful only when derived according to a **trusted proxy topology**. If network allowlisting is needed at the ingress, enforce it at the network/proxy layer that observes the real socket peer and trusts only configured proxy chains. **Never use IP/client addresses alone in place of authentication and authorization** for sensitive data.

Even `request.getRemoteAddress()` after enabling `ForwardedHeaderTransformer` can reflect forwarded info rather than solely the directly observed socket peer. When logging "client IP," document its source/trust level and handle personal data per privacy policy.

## 7. Configuring the Reverse Proxy at the Right Trust Boundary

Below is an **illustrative Nginx snippet** where Nginx is the sole public edge serving a single HTTPS hostname `app.example.com` in front of local backend `127.0.0.1:8080`.

~~~nginx
server {
    listen 443 ssl;
    server_name app.example.com;

    # Replace with real certificate paths on deployment.
    ssl_certificate     /etc/nginx/tls/app.crt;
    ssl_certificate_key /etc/nginx/tls/app.key;

    # HSTS at HTTPS edge (choose max-age per policy).
    add_header Strict-Transport-Security "max-age=31536000" always;

    location / {
        proxy_pass http://127.0.0.1:8080;

        # Pin public Host; never trust attacker-supplied Host.
        proxy_set_header Host app.example.com;

        # Do not forward client-supplied RFC 7239 header.
        proxy_set_header Forwarded "";

        # Explicitly SET metadata verified at the edge.
        proxy_set_header X-Forwarded-Host app.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;

        # Use socket peer observed by this proxy.
        # Do not use $proxy_add_x_forwarded_for unless prior-hop
        # XFF headers have been verified/stripped.
        proxy_set_header X-Forwarded-For $remote_addr;

        # Clear unused variants.
        proxy_set_header X-Forwarded-Ssl "";
        proxy_set_header X-Forwarded-Prefix "";
    }
}
~~~

Explanation and limits:
- This is an **infrastructure snippet** and cannot simply be pasted without TLS certificates, routing policies, and firewalls.
- `proxy_set_header Forwarded "";` prevents passing client `Forwarded` headers upstream (in Nginx, an empty value omits the header).
- `X-Forwarded-*` values are **overwritten** with edge-verified values rather than forwarding client headers verbatim.
- `X-Forwarded-For $remote_addr` is **Nginx's socket peer**. If Nginx sits behind a CDN, that is the CDN's IP; you must extract the real client IP using the **trusted CDN IP list** and realip module rather than blindly picking the leftmost entry.
- The backend must accept traffic solely from Nginx (loopback in the demo; private network in production). If the backend remains Internet-reachable, attackers bypass all edge sanitization by calling it directly.
- Nginx may encounter other forwarding header variants; configure a **header allowlist**, strip client-supplied variants/duplicates, and never rely on an unchecked header.
- Public HTTP port 80 should redirect to HTTPS using a verified `server_name`; never reflect untrusted `$http_host` into absolute redirects.
- This config assumes **a single domain**. Multi-domain/multi-tenant deployments must validate hosts and select headers from a trusted mapping.

### 7.1. A Very Common Trap with `$proxy_add_x_forwarded_for`

Nginx configurations often use:

~~~nginx
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
~~~

This **appends** the peer IP to any existing `XFF` header. If an Internet request sends:

~~~http
X-Forwarded-For: 127.0.0.1
~~~

the forwarded value becomes `127.0.0.1, 198.51.100.27`. A backend picking the first element gets fooled. **Never declare appending syntax universally dangerous or universally safe**; it depends on whether upstream edges sanitized headers and on your trusted-hop list. When Nginx is the first edge, the example above intentionally **overwrites** instead of appending.

### 7.2. The Edge Might Not Be a CDN—or Might Include One

With layered CDNs/WAFs/ingresses, proxy configuration differs:
- A CDN may inject `Forwarded` or `XFF` per its own protocol.
- The ingress should trust headers solely from verified CDN/WAF CIDRs.
- Traffic bypassing the CDN must be blocked.
- If standardizing on RFC `Forwarded`, backend and proxy must align on one format so the two families do not conflict.
- Every provider or routing change requires re-running tests for spoofed IPs, hosts, schemes, path prefixes, and redirects.

**Infrastructure determines whether metadata is trustworthy; Spring simply decodes and applies it.**

## 8. Runnable Java 17+ Project: WebFlux Observing Forwarded Metadata

The project uses **Spring Boot 3.3.13**, Gradle 8.x, and JDK 17+. Versions are pinned to illustrate consistent Spring Framework 6.1.x APIs; production should stay on a supported line and re-verify tests.

**Demo goals:**
- `server.forward-headers-strategy=framework` to observe forwarded headers changing scheme/host.
- `GET /internal/request-view` requires `diagnostics:read` authority via HTTP Basic so debug info is not public.
- `GET /public-link` returns a canonical URL from trusted config rather than concatenating request `Host`.
- `GET /health` is public without exposing internal details.
- Sending forwarded headers directly to the local port in tests **intentionally demonstrates that spoofing can happen if a backend is directly reachable**. This is not an Internet-safe topology.
- A unit test for `ForwardedHeaderTransformer.removeOnly(true)` demonstrates opting out of trusting forwarded headers.

### 8.1. Structure

~~~text
webflux-forwarded-boundary/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── ForwardedBoundaryApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── RequestController.java
    │   └── resources/application.properties
    └── test/java/demo/
        └── ForwardedHeadersTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-forwarded-boundary'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Do not add Servlet `spring-boot-starter-web`. The reactive Boot starter uses Reactor Netty by default in this example.

`src/main/resources/application.properties`:

~~~properties
# DEMO FOR LOCAL/BEHIND TRUSTED PROXY USE ONLY.
# FRAMEWORK does not independently verify whether peers are trusted proxies.
server.forward-headers-strategy=framework

# Canonical URL from backend config, never taken from request Host.
app.public-base-url=https://app.example.com
~~~

Never expose the backend port directly in production. If no trusted edge exists, set `server.forward-headers-strategy=none` or use an appropriate remove-only configuration.

### 8.2. Bootstrap Class

`src/main/java/demo/ForwardedBoundaryApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ForwardedBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(ForwardedBoundaryApplication.class, args);
    }
}
~~~

### 8.3. Spring Security Reactive: Diagnostics Endpoint Must Require Auth

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails observer = User.withUsername("observer")
            .password(encoder.encode("observer-demo-pass"))
            .authorities("diagnostics:read")
            .build();

        return new MapReactiveUserDetailsService(observer);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health", "/public-link").permitAll()
                .pathMatchers("/internal/request-view")
                    .hasAuthority("diagnostics:read")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
~~~

- HTTP Basic is only for illustrating local tests. Production needs HTTPS and proper authentication.
- `/internal/request-view` is not public: host/scheme and request metadata can aid reconnaissance.
- Never use forwarded host or forwarded IP to grant roles/admin privileges.
- Do not disable CSRF: the demo defines only GETs with no side-effecting endpoints. When adding business POSTs, apply CSRF according to credential/browser usage.
- Demo passwords are BCrypt-hashed; never hardcode credentials in real deployments.
- No Servlet `HttpSecurity` appears in a WebFlux project.

### 8.4. Controller Observing the Transformed URI

`src/main/java/demo/RequestController.java`:

~~~java
package demo;

import java.net.URI;
import java.util.Locale;
import java.util.Map;

import org.springframework.core.env.Environment;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class RequestController {

    public record RequestView(
        String scheme,
        String host,
        int port,
        boolean forwardedHeaderStillVisible
    ) {}

    private final String publicBaseUrl;

    RequestController(Environment environment) {
        publicBaseUrl = environment
            .getRequiredProperty("app.public-base-url");
    }

    @GetMapping("/health")
    Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/public-link")
    Mono<Map<String, String>> publicLink() {
        // Never build tokenized/redirect URLs from request Host.
        return Mono.just(Map.of(
            "url", publicBaseUrl + "/help"));
    }

    @GetMapping("/internal/request-view")
    Mono<RequestView> requestView(ServerHttpRequest request) {
        return Mono.fromSupplier(() -> {
            URI uri = request.getURI();

            boolean stillVisible =
                request.getHeaders().keySet().stream()
                    .map(name -> name.toLowerCase(Locale.ROOT))
                    .anyMatch(name -> name.equals("forwarded")
                        || name.startsWith("x-forwarded-"));

            return new RequestView(
                uri.getScheme(),
                uri.getHost(),
                uri.getPort(),
                stillVisible
            );
        });
    }
}
~~~

Notable points:
- `request.getURI()` reflects metadata applied by `ForwardedHeaderTransformer` before the controller runs.
- `getHost()` is the post-transform observed host; **it does not mean the host was edge-verified** if the backend is directly reachable.
- After the transformer runs, forwarded headers are stripped from the downstream request per contract; `forwardedHeaderStillVisible` demonstrates this.
- `getPort()` may be `-1` when the URI omits an explicit port, even for HTTPS; **do not conclude `port=-1` is an error**.
- `/public-link` reads its base URL from config, so `X-Forwarded-Host: evil.example` is never injected into app-generated links. Canonical config must be validated and edit-controlled in production.
- The controller never returns remote IPs, Authorization headers, cookies, or sensitive network details.

## 9. Testing with WebTestClient Against a Real Server

When testing Spring Boot's `server.forward-headers-strategy`, bind to a **real HTTP server on a random port** rather than a mock WebFilterChain. This exercises Reactor Netty + forwarded transformer auto-configuration for real.

`src/test/java/demo/ForwardedHeadersTests.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.server.adapter.ForwardedHeaderTransformer;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
class ForwardedHeadersTests {

    @LocalServerPort
    int port;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .build();
    }

    @Test
    void healthIsPublicButDiagnosticsRequireAuthentication() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");

        client.get().uri("/internal/request-view")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void noForwardedHeadersMeansLocalHttpScheme() {
        client.get().uri("/internal/request-view")
            .headers(h -> h.setBasicAuth(
                "observer", "observer-demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.scheme").isEqualTo("http")
            .jsonPath("$.host").isEqualTo("localhost")
            .jsonPath("$.forwardedHeaderStillVisible")
                .isEqualTo(false);
    }

    @Test
    void frameworkUsesTrustedRfc7239HeaderWhenPresent() {
        client.get().uri("/internal/request-view")
            .headers(h -> h.setBasicAuth(
                "observer", "observer-demo-pass"))
            .header("Forwarded",
                "for=198.51.100.27;proto=https;host=app.example.com")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.scheme").isEqualTo("https")
            .jsonPath("$.host").isEqualTo("app.example.com")
            .jsonPath("$.forwardedHeaderStillVisible")
                .isEqualTo(false);
    }

    @Test
    void frameworkUsesXForwardedSchemeAndHost() {
        client.get().uri("/internal/request-view")
            .headers(h -> h.setBasicAuth(
                "observer", "observer-demo-pass"))
            .header("X-Forwarded-Proto", "https")
            .header("X-Forwarded-Host", "app.example.com")
            .header("X-Forwarded-Port", "443")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.scheme").isEqualTo("https")
            .jsonPath("$.host").isEqualTo("app.example.com")
            .jsonPath("$.forwardedHeaderStillVisible")
                .isEqualTo(false);
    }

    @Test
    void directClientCouldSpoofHostIfBackendWerePublic() {
        // Test INTENTIONALLY demonstrates the risk.
        // No trusted proxy sanitizer exists in the test environment.
        client.get().uri("/internal/request-view")
            .headers(h -> h.setBasicAuth(
                "observer", "observer-demo-pass"))
            .header("X-Forwarded-Host", "evil.example")
            .header("X-Forwarded-Proto", "https")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.host").isEqualTo("evil.example");
    }

    @Test
    void canonicalLinkCannotBePoisonedByForwardedHost() {
        client.get().uri("/public-link")
            .header("X-Forwarded-Host", "evil.example")
            .header("X-Forwarded-Proto", "https")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.url")
                .isEqualTo("https://app.example.com/help");
    }

    @Test
    void removeOnlyDiscardsBothHeaderFamiliesWithoutUsingThem() {
        ForwardedHeaderTransformer transformer =
            new ForwardedHeaderTransformer();
        transformer.setRemoveOnly(true);

        ServerHttpRequest raw = MockServerHttpRequest
            .get("http://internal.local:8080/check")
            .header("Forwarded",
                "for=198.51.100.9;proto=https;host=evil.example")
            .header("X-Forwarded-Proto", "https")
            .header("X-Forwarded-Host", "evil.example")
            .build();

        ServerHttpRequest transformed = transformer.apply(raw);

        assertThat(transformed.getURI())
            .isEqualTo(raw.getURI());
        assertThat(transformed.getHeaders().containsKey("Forwarded"))
            .isFalse();
        assertThat(transformed.getHeaders().containsKey(
            "X-Forwarded-Host")).isFalse();
        assertThat(transformed.getHeaders().containsKey(
            "X-Forwarded-Proto")).isFalse();
    }
}
~~~

### 9.1. What Is Tested and What Is Not Proven?

1. `healthIsPublicButDiagnosticsRequireAuthentication`: restricts debug URLs to authorized users rather than leaking metadata anonymously.
2. `noForwardedHeadersMeansLocalHttpScheme`: on local HTTP without Forwarded headers, the app observes HTTP.
3. `frameworkUsesTrustedRfc7239HeaderWhenPresent`: in FRAMEWORK mode, the app restores scheme/host from RFC 7239 and forwarded headers disappear downstream.
4. `frameworkUsesXForwardedSchemeAndHost`: illustrates the common proxy `X-Forwarded-*` pattern.
5. `directClientCouldSpoofHostIfBackendWerePublic`: **intentionally demonstrates the danger**: if the backend can be called directly, a client-spoofed Host header is honored! A passing test does not mean security is achieved; it proves **why edge sanitization and network isolation are mandatory**.
6. `canonicalLinkCannotBePoisonedByForwardedHost`: critical links use the configured base URL instead of reflecting an untrusted host.
7. `removeOnlyDiscardsBothHeaderFamiliesWithoutUsingThem`: tests the transformer API standalone without spinning up another server.

**This test suite intentionally does not simulate Nginx itself**: to prove Internet header spoofing is blocked, you must run integration/E2E tests **through the real proxy** verifying the backend receives only sanitized values. App-level tests alone cannot prove the network boundary is locked down.

### 9.2. Where to Test Headers?

Once the proxy sanitizes requests:
- Send external requests carrying `Forwarded: proto=http;host=evil.example` and `X-Forwarded-Host: evil.example`.
- Verify public redirects/links still resolve to `https://app.example.com`.
- Confirm the backend is not directly reachable from the Internet.
- Verify proxy logs/observability capture request IDs without logging credentials or sensitive data.
- Verify `X-Forwarded-For` contains the verified peer IP, not client-injected lists.
- Test multi-hop scenarios and invalid `Origin`/`Host` cases.
- Verify HSTS and `Secure` cookies actually appear on public HTTPS responses.
- Confirm redirects neither loop nor point to internal backend addresses.
- With OIDC, confirm `redirect_uri` matches the registered URI without Host poisoning.

## 10. Running and Observing with curl

From the project directory:

~~~bash
gradle bootRun
~~~

If using a Gradle Wrapper, run `./gradlew bootRun` (Unix/macOS) or `gradlew.bat bootRun` (Windows). Run tests separately:

~~~bash
gradle test
~~~

This is a local HTTP example; **never send real credentials in plaintext over the Internet**.

### 10.1. Request Without Forwarded Headers

~~~bash
curl -s -u observer:observer-demo-pass \
  http://localhost:8080/internal/request-view
~~~

Typical response:

~~~json
{
  "scheme": "http",
  "host": "localhost",
  "port": 8080,
  "forwardedHeaderStillVisible": false
}
~~~

The `port` field varies with the actual port and URI representation. When using a default URI without an explicit port, `port=-1` is valid.

### 10.2. Simulating a Trusted Proxy via Forwarded Headers

~~~bash
curl -s -u observer:observer-demo-pass \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: app.example.com' \
  -H 'X-Forwarded-Port: 443' \
  http://localhost:8080/internal/request-view
~~~

Expected highlights:

~~~json
{
  "scheme": "https",
  "host": "app.example.com",
  "port": -1,
  "forwardedHeaderStillVisible": false
}
~~~

`port=-1` is a common representation when the URI has no explicit port. What must be verified are **scheme, host, optional port, and header removal**, rather than hardcoding a single port integer across all runtimes.

### 10.3. Intentionally Spoofing Host to Observe Risk

~~~bash
curl -s -u observer:observer-demo-pass \
  -H 'X-Forwarded-Host: evil.example' \
  -H 'X-Forwarded-Proto: https' \
  http://localhost:8080/internal/request-view
~~~

In a test environment where the backend accepts direct calls with `framework` enabled, you may see:

~~~json
{
  "scheme": "https",
  "host": "evil.example",
  "port": -1,
  "forwardedHeaderStillVisible": false
}
~~~

**This is a warning, not a security feature.** The framework behaved properly per API, yet has no way to know who sent the spoofed header. Never allow direct backend access like this in production deployments.

### 10.4. Canonical Link Remains Unchanged

~~~bash
curl -s \
  -H 'X-Forwarded-Host: evil.example' \
  http://localhost:8080/public-link
~~~

Response:

~~~json
{
  "url": "https://app.example.com/help"
}
~~~

Because the handler reads the public URL from trusted configuration rather than `Host`/`X-Forwarded-Host`. For multi-tenant apps, use a managed, validated hostname/tenant mapping table instead of concatenating raw headers.

## 11. Common Operational Issues and Fixes

| Symptom | Likely cause | Diagnosis and fix |
| --- | --- | --- |
| Redirect points to `http://10.0.0.x:8080` | App sees internal URI without public metadata | Check proxy scheme/host setting and Boot strategy |
| Browser uses HTTPS yet endlessly redirects to HTTPS | App/security context still thinks request is HTTP | Check forwarded proto, chain, proxy HTTPS enforcement, and rewrites |
| Password-reset link contains attacker domain | Trusts client-sent `Host`/`X-Forwarded-Host` | Canonical public URL + host validation + edge strip/overwrite |
| Cookie lacks `Secure` on HTTPS browser | Cookie policy or perceived scheme wrong | Set proper cookie secure policy; test over public HTTPS |
| HSTS absent in browser | App sees HTTP or edge omits header | Inspect HSTS at edge and Spring Security header policy |
| Audit IP is always the proxy | `XFF` unhandled or no trust-aware client IP source | Define topology, trusted hops, logging policy |
| Audit IP is `127.0.0.1` from Internet request | Client spoofed `XFF` and proxy appended unsanitized | Edge overwrite; never use raw `XFF` for authorization |
| CORS reports wrong origin/port | Public host/port differs from backend, or wrong allowlist | Define public origins explicitly; never derive allowlist from untrusted headers |
| OAuth2 login callback reports mismatch | Redirect URI has wrong public scheme/host/prefix | Configure canonical base URL/registered redirect URI; test proxy |
| URL under `/gateway` loses prefix | Proxy strips prefix but transformer/links unconfigured | Align `X-Forwarded-Prefix` and routing; test end-to-end |
| URL has double prefix | Both proxy and app prepend prefix | Align strip/preserve semantics |
| `server.forward-headers-strategy=native` misbehaves | Server implementations differ | Check native server docs; use `framework` if needed and secure proxy |
| `ForwardedHeaderTransformer` not applied | Wrong bean name or Boot config disabled | Verify Boot strategy or bean named `forwardedHeaderTransformer` |
| Local spoof test shows `evil.example` | Backend trusts headers on direct requests | Expected demonstration; lock backend behind trusted proxy |
| Direct HTTP to app still returns 200 | Backend port exposed, bypassing edge HTTPS enforcement | Firewall/network isolation; never rely on forwarded-header config |
| Client sends conflicting `Forwarded`/`X-Forwarded` | Proxy failed to normalize both families | Edge strips both and emits one approved format |
| Auth rejected despite valid forwarded metadata | Forwarded headers are not credentials | Check session/token/Basic and authorization independently |

## 12. Trust Boundary Design Checklist

### 12.1. Network and Edge

- [ ] Backend port is reachable only from approved proxies/ingresses; zero direct Internet bypass paths.
- [ ] Ingress validates `Host` against an allowlist/canonical mapping instead of reflecting raw `Host` unconditionally.
- [ ] Ingress strips **both** untrusted `Forwarded` and `X-Forwarded-*` (Proto, Host, For, Port, Prefix, and any variants used).
- [ ] Proxy re-creates headers solely from verified scheme/host/client connection state.
- [ ] Across multiple hops, maintain a trusted proxy/CIDR list and explicit client-IP selection rules rather than blindly picking the first element.
- [ ] Public HTTP redirects to HTTPS on the right hostname; TLS and HSTS policies are browser-verified.
- [ ] Proxy → backend traffic is protected via isolation and TLS/mTLS where appropriate.

### 12.2. Spring Boot/WebFlux

- [ ] Explicitly set `server.forward-headers-strategy` matching the architecture.
- [ ] When using `framework`, recognize `ForwardedHeaderTransformer` trusts incoming metadata; the framework does not authenticate the proxy.
- [ ] Do not confuse Servlet `ForwardedHeaderFilter` with WebFlux `ForwardedHeaderTransformer`.
- [ ] Avoid duplicating Boot's auto transformer with unreviewed custom beans.
- [ ] Without a trusted proxy, consider `none` and/or a `removeOnly` transformer.
- [ ] When using prefixes, verify `X-Forwarded-Prefix` version behavior and downstream paths.
- [ ] Never treat `request.getRemoteAddress()` post-forwarding as authorization proof.
- [ ] Never `block()` or manually `subscribe()` inside reactive security handlers.

### 12.3. Spring Security and Application

- [ ] Authentication/authorization never depends on `X-Forwarded-For: 127.0.0.1` or untrusted `Host`.
- [ ] Redirects, OAuth2 callbacks, and reset links use validated public base URLs/mappings.
- [ ] Cookie `Secure`/`HttpOnly`/`SameSite` match public HTTPS and session/CSRF mechanisms.
- [ ] HSTS on public HTTPS responses is verified end-to-end, not merely assumed from app config.
- [ ] CORS allowlists and CSRF `Origin` checks cannot be manipulated via host spoofing.
- [ ] Rate limiting and IP auditing rely on verified identity/network sources.
- [ ] Never log `Authorization`, cookies, reset tokens, CSRF tokens, or excessively sensitive client IPs.
- [ ] Test positive flows through the real proxy plus negative spoofed-header/multi-hop/bypass-route cases.
- [ ] Monitoring alerts on redirects to foreign hosts, 3xx loop spikes, IP spoofing, and direct backend access.

## 13. Practice Questions and Answers

**Q1.** The browser uses HTTPS, yet the Reactor Netty backend receives HTTP. Is that abnormal?

**Answer:** No, when TLS terminates at a reverse proxy. You need trusted public metadata and separate protection for the proxy → backend channel.

**Q2.** Does `X-Forwarded-Proto: https` prove the backend socket uses TLS?

**Answer:** No. The header only reports the scheme observed by the proxy; it is not proof of encryption on the current hop.

**Q3.** When is `server.forward-headers-strategy=framework` safe?

**Answer:** When the app accepts requests solely from trusted proxies and the proxy strips/overwrites untrusted headers at the trust boundary, with verified topology and hostnames.

**Q4.** Why can't Spring tell `Forwarded` sent by Nginx apart from `Forwarded` sent by an attacker?

**Answer:** Both arrive as HTTP headers. The app has no independent proof of each field's origin unless the network/proxy protects the boundary.

**Q5.** The proxy strips `Forwarded` but leaves client `X-Forwarded-Host` intact—is that enough?

**Answer:** No. Spring supports both families; untrusted headers from **both** must be stripped.

**Q6.** Why isn't the first entry in `X-Forwarded-For` always a trustworthy IP?

**Answer:** Appending proxies can preserve client-forged entries, and multi-hop chains require a trusted-hops policy.

**Q7.** How do `none`, `native`, and `framework` differ?

**Answer:** They are Boot options for **how to process** forwarded metadata: disabled, native HTTP server, or Spring Framework. None of them creates a firewall.

**Q8.** What does `removeOnly(true)` do?

**Answer:** Strips forwarded headers from downstream requests without using their values to rewrite URIs.

**Q9.** How do you prevent password-reset links from pointing to `evil.example`?

**Answer:** Use a validated canonical public base URL/mapping and ensure the ingress strips/overwrites untrusted `Host`/`Forwarded` headers.

**Q10.** Should setting `X-Forwarded-Prefix: /admin` automatically grant admin privileges?

**Answer:** No. Prefix is routing metadata, not an authorization claim. Host and path must be authorized independently.

**Q11.** Why can redirect loops happen with TLS termination?

**Answer:** The browser speaks HTTPS while the backend sees HTTP and keeps redirecting to HTTPS; restore trusted public scheme and align app/proxy redirect rules.

**Q12.** Should HSTS be checked only on internal HTTP responses?

**Answer:** No. Verify **public browser-facing HTTPS** responses carry the expected header without breaking the domain or subdomains.

**Q13.** Can `127.0.0.1` extracted from `XFF` bypass authentication?

**Answer:** Absolutely not. Headers can be spoofed; authorization must rely on trusted identity and policies.

**Q14.** Are transformer unit tests sufficient to verify production proxy boundaries?

**Answer:** No. You need E2E requests through the ingress and network tests proving the backend is unreachable directly.

**Q15.** Should CORS accept any `Origin` if `X-Forwarded-Host` looks like your domain?

**Answer:** No. CORS allowlists must be static/validated against trusted config; forwarded headers are not proof of Origin.

**Q16.** With multiple reverse proxies, should you always use `$proxy_add_x_forwarded_for`?

**Answer:** Never as a blanket rule. Check whether upstream proxies sanitized headers, network trust, real-IP modules, and IP extraction logic.

**Q17.** Why isn't `RequestView.port=-1` necessarily a bug?

**Answer:** Java `URI` returns `-1` when no explicit port is present; default HTTPS port 443 may be omitted from the URI.

**Q18.** A test intentionally sends `X-Forwarded-Host: evil.example` and observes the backend receive `evil.example` — did the test FAIL or PASS?

**Answer:** It is a **test illustrating spoofing exposure** in FRAMEWORK mode when a backend is called directly. It passes as an educational proof, yet production is safe only when the proxy boundary blocks such direct input.

**Q19.** Does a WebFlux API need a manual transformer bean when `server.forward-headers-strategy=framework` is already set?

**Answer:** Not necessarily; Boot configures the appropriate mechanism. Avoid duplicate config unless there is a specific reason.

**Q20.** What is the single most important safeguard against blindly trusting forwarded headers?

**Answer:** **Block direct backend access + strip/recreate both `Forwarded` and `X-Forwarded-*` at a trusted proxy**, before enabling header interpretation in the app.

## 14. Official References

- Spring Framework 6.1 — WebFlux Forwarded Headers: https://docs.spring.io/spring-framework/reference/6.1/web/webflux/reactive-spring.html#webflux-forwarded-headers
- Spring Framework — `ForwardedHeaderTransformer` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/adapter/ForwardedHeaderTransformer.html
- Spring Boot 3.3 — Running Behind a Front-end Proxy Server: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server
- Spring Boot 3.3 — `ServerProperties.ForwardHeadersStrategy`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/ServerProperties.ForwardHeadersStrategy.html
- Spring Security — Forwarded Headers and HTTP Security: https://docs.spring.io/spring-security/reference/features/exploits/http.html
- Spring Security — HSTS and Security Response Headers: https://docs.spring.io/spring-security/reference/features/exploits/headers.html
- RFC 7239 — Forwarded HTTP Extension: https://www.rfc-editor.org/rfc/rfc7239
- OWASP — HTTP Headers Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html
- OWASP — Unvalidated Redirects and Forwards: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html

**Remember:** `Forwarded` and `X-Forwarded-*` are **useful metadata, not self-authenticating facts**. In WebFlux, `ForwardedHeaderTransformer` restores scheme/host/port when permitted by the application, without verifying who sent the headers. To handle them accurately and safely, combine **edge sanitization + proxy-only backend access + proper Boot config + positive/negative testing**, then build redirects, HTTPS/HSTS/cookies/CSRF, and IP-based observability on top of a proven trust boundary.
