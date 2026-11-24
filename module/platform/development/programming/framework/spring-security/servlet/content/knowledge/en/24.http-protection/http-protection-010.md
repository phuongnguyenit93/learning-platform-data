# Requiring HTTPS, Redirect Configuration, and Proxy Redirect Loop Risks

## 1. Problem to solve

When a **Spring Security Servlet** API accepts only secure access, visits over `http://` typically need to be upgraded to `https://`. That sounds simple on a server handling TLS directly, but easily breaks when a Spring Boot application runs behind a **reverse proxy, ingress, or load balancer**.

A common deployment topology:

```text
Browser --HTTPS:443--> Reverse proxy / Load balancer
                               |
                               | HTTP:8080 (internal network)
                               v
                         Spring Boot Servlet
                         Spring Security
```

The browser used HTTPS to reach the proxy, yet the **proxy → Spring Boot** connection remains HTTP. If Spring Security inspects the internal request and concludes the client used HTTP, it returns a redirect to HTTPS. The browser requests the exact same HTTPS URL again, the proxy forwards it to the backend over HTTP again, and the process can loop indefinitely.

To configure this properly, distinguish three tasks:

1. **Enforcing HTTPS for clients:** deciding which requests must be redirected or rejected when clients use HTTP.
2. **Recognizing the original scheme behind a proxy:** letting the app know the client actually connected to the proxy via HTTPS, using metadata normalized by a trusted proxy.
3. **Securing each connection hop:** client → proxy HTTPS does not automatically encrypt proxy → backend; the internal hop must be protected according to your network and threat model.

**Key point:** `requiresSecure()` handles Spring Security's channel policy; `server.ssl.*` and TLS listeners handle actual transport; `Forwarded`/`X-Forwarded-*` interpret the original protocol behind a proxy. They are related, not interchangeable.

## 2. What does HTTPS mean in a multi-layered system?

HTTPS is HTTP protected by TLS. The browser verifies the TLS server's certificate, establishes encryption keys, and exchanges data over the secure channel. With a reverse proxy performing *TLS termination*, the proxy decrypts requests before forwarding them to the backend.

There are two primary deployment patterns.

### A. Direct TLS at the application

```text
Client --HTTPS--> Spring Boot (TLS listener)
```

The application opens an HTTPS port and manages its own certificate/keystore. Servlet requests typically show:

```text
request.isSecure() = true
request.getScheme() = "https"
```

An HTTP request to a separate port can be redirected, rejected, or left unexposed depending on the architecture.

### B. TLS terminated at a proxy

```text
Client --HTTPS--> Proxy --HTTP--> Spring Boot
```

**Without forwarded-header processing**, backend Servlet requests reflect the actual connection the backend sees:

```text
request.isSecure() = false
request.getScheme() = "http"
request.getServerPort() = 8080
```

Even though the browser displays the HTTPS padlock, Spring Security may believe the request is insecure. To interpret the original protocol accurately, the proxy must pass trusted metadata and Spring Boot must be configured to read it.

`X-Forwarded-Proto: https` typically describes the external scheme. The standardized RFC 7239 header looks like `Forwarded: proto=https;host=api.example.com`. Fields such as host and port also need to be accurate when constructing absolute redirects.

## 3. How does Spring Security decide to redirect?

In Servlet-based Spring Security, you can require requests to use HTTPS via the `requiresChannel(...)` DSL. Channel security inspects the incoming request; when security is required yet the request is not recognized as secure, Spring Security can return a **redirect** to an HTTPS URL.

```java
http.requiresChannel(channel ->
        channel.anyRequest().requiresSecure());
```

This has three consequences:

- A redirect is a **response sent back to the client**, not the backend opening an HTTPS connection on its own.
- `requiresSecure()` **does not install certificates, open an HTTPS port, or turn HTTP between proxy and backend into TLS**.
- If the backend misreads the scheme because the proxy did not forward it or isn't trusted, valid HTTPS visits can still get redirected again.

Spring Security must also determine the redirect URL: scheme, hostname, and port. In some configurations, HTTP → HTTPS port mappings may use defaults (such as 8080 → 8443). This must be checked when the app sits behind a proxy serving public port 443.

**Do not treat redirects as the sole security barrier.** An initial HTTP request may already leak the URL, non-`Secure` cookies, or sensitive data before the server even returns a redirect. At the Internet edge, prioritize serving HTTPS properly, redirecting HTTP early, and protecting cookies.

## 4. Spring Boot 3.3.x and Java 17+ application example

The example below is a minimal Spring MVC + Spring Security Servlet application to observe **HTTPS requirements and redirect behavior**. A public endpoint is used solely for testing so auth errors do not obscure results. Real APIs must add proper business authentication/authorization rules.

### 4.1. Dependencies

Gradle Groovy example in `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 4.2. Application startup class

Create `src/main/java/demo/https/HttpsDemoApplication.java`:

```java
package demo.https;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpsDemoApplication.class, args);
    }
}
```

### 4.3. SecurityFilterChain: requiring HTTPS

Create `src/main/java/demo/https/HttpSecurityConfig.java`:

```java
package demo.https;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HttpSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .requiresChannel(channel ->
                        channel.anyRequest().requiresSecure())
                .authorizeHttpRequests(auth ->
                        auth.anyRequest().permitAll())
                .build();
    }
}
```

`anyRequest().requiresSecure()` expresses the policy across all paths. `permitAll()` here **only keeps the example focused on HTTPS**, and is not a production policy. Real applications normally configure authentication and per-endpoint access controls. Channel security does not replace authorization.

Create `src/main/java/demo/https/PingController.java`:

```java
package demo.https;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("message", "pong");
    }
}
```

For requests **recognized by the system as secure**, the controller returns JSON equivalent to:

```json
{"message":"pong"}
```

JSON property ordering is insignificant. For requests detected as plain HTTP, channel policy runs before MVC, so the controller is not invoked.

### 4.4. Running and observing redirects locally

Using the project's Gradle wrapper:

```bash
./gradlew bootRun
curl -i --max-redirs 0 http://localhost:8080/public/ping
```

On Windows PowerShell, you can run `.\gradlew.bat bootRun` and then invoke `curl.exe` (avoiding legacy PowerShell's `curl` alias).

When the app only listens on HTTP 8080, the output typically shows HTTP **3xx** with a `Location` header pointing to an HTTPS URL, such as:

```http
HTTP/1.1 302
Location: https://localhost:8443/public/ping
```

**This is an illustrative example, not a guarantee of exact status or port in every environment.** The URL depends on port mappings, server/proxy setup, and redirect configuration. Without an HTTPS listener at the target, using `curl -L` to follow the redirect will fail to connect even though the redirect rule is working. Do not confuse "no server listening on 8443" with a proxy HTTPS redirect loop.

## 5. TLS termination at a reverse proxy: application-side configuration

In production, suppose the public URL is `https://api.example.com`, with the proxy serving TLS on 443 and forwarding traffic to Spring Boot over HTTP 8080.

The app must know **the client connected via HTTPS**. Spring Boot Servlet supports forwarded header processing via:

```yaml
# src/main/resources/application-prod.yml
server:
  forward-headers-strategy: framework
```

With the `framework` strategy, Spring Boot registers Spring Framework's mechanism such as `ForwardedHeaderFilter` for Servlet, adjusting scheme, host, and port from forwarded headers during request processing. Another option is `native`, leveraging Servlet container support (e.g., Tomcat `RemoteIpValve`); proxy trust details and supported headers vary by container. `none` disables this translation.

When configured properly and the proxy sends `X-Forwarded-Proto: https`, Spring Security sees the request as **recognized** secure even though the socket between proxy and backend is HTTP.

```text
Browser:  HTTPS https://api.example.com/public/ping
Proxy:    TLS handled at the edge
Proxy -> Spring Boot:
          GET /public/ping HTTP/1.1
          Host: api.example.com
          X-Forwarded-Proto: https
          X-Forwarded-Host: api.example.com
          X-Forwarded-Port: 443
Spring Boot (after applying trusted forwarded metadata):
          isSecure() = true
          scheme = https
          serverPort = 443
Spring Security:
          HTTPS requirement satisfied -> no redirect
Controller:
          returns {"message":"pong"}
```

Note that those values are **derived from forwarded metadata**; they do not prove the backend communicates directly with the proxy over TLS. Encrypting the internal hop must be addressed via backend TLS, mTLS, VPN/overlay, or a trusted private network per requirements.

### The proxy must normalize forwarded headers

Example **Nginx `location` snippet inside an HTTPS virtual host**, not a complete Nginx configuration:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host api.example.com;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host api.example.com;
    proxy_set_header X-Forwarded-Port 443;
}
```

The example uses a fixed public hostname. In practice, proxies may also need to pass prefix/path, original client IP, and per-tenant hosts; configure them from **values verified by the proxy**. If TLS terminates at a load balancer **in front of** Nginx, Nginx must also recognize the external protocol and trust metadata only from trusted upstream layers; never blindly hardcode `https` for non-upgraded HTTP requests.

On the edge HTTP virtual host, redirects can be handled like this (illustrative Nginx snippet; combine with real TLS configuration and `server_name`):

```nginx
server {
    listen 80;
    server_name api.example.com;
    return 308 https://api.example.com$request_uri;
}
```

HTTP 308 preserves the HTTP method and request body per redirect semantics, unlike 301/302 cases where clients might switch to GET. Even so, never design sensitive APIs expecting clients to POST credentials over HTTP first and upgrade afterward: clients must call HTTPS from the start.

## 6. How do redirect loops happen?

Suppose the browser sends `GET https://api.example.com/public/ping`. The proxy terminates TLS and forwards to the backend over HTTP, yet **omits `X-Forwarded-Proto`** or Spring Boot is not configured to use forwarded headers.

```text
(1) Browser -> https://api.example.com/public/ping
               |
(2) TLS proxy: HTTPS -> internal HTTP:8080
               |
(3) Spring Boot: isSecure() = false
               |
(4) Spring Security: requiresSecure()
                     -> returns 302 Location: https://api.example.com/public/ping
               |
(5) Browser follows HTTPS Location (the exact URL it just requested)
               |
(6) Back to (2), looping 302 -> 302 -> 302 ...
```

Symptoms include browser `ERR_TOO_MANY_REDIRECTS` errors or `curl` stopping after exceeding max redirects. When host/port are also wrong, `Location` might point to `https://localhost:8443`, `https://api.example.com:8443`, or an internal hostname: a sibling configuration bug from the same root cause, though not always an infinite loop.

**Common causes:**

1. The proxy does not forward `Forwarded` / `X-Forwarded-Proto`.
2. The proxy forwards them properly, yet Boot has `server.forward-headers-strategy=none` or the profile config is inactive.
3. Multiple proxy tiers exist; the final proxy **overwrites `X-Forwarded-Proto: http`** based on the internal hop instead of preserving the client scheme from a trusted upstream.
4. The app runs `ForwardedHeaderFilter` in strip-only mode (`removeOnly`), or another filter/proxy alters metadata incompatibly.
5. Port mappings or host/port headers do not match the public address, producing redirects to the wrong destination.
6. Two layers generate redirects with conflicting conditions (gateway modifies host/path, Spring redirects to another scheme/port, rewrite flips it back).
7. The proxy upgrades HTTP to HTTPS at the outer edge while backend Spring still views every request as HTTP: edge redirects alone **do not fix** Spring's scheme perception.

Never fix loops by disabling HTTPS requirements system-wide when the root cause is misinterpreted metadata. Verify the exact **client scheme**, **forwarded scheme**, **Servlet `isSecure()`**, and **`Location`** at each hop.

## 7. Step-by-step live troubleshooting

### 7.1. Testing from the client

From a machine able to reach the public URL:

```bash
curl -i --max-redirs 0 http://api.example.com/public/ping
curl -i --max-redirs 0 https://api.example.com/public/ping
curl -v -L --max-redirs 5 https://api.example.com/public/ping
```

Expected on a properly configured system: HTTP reaches HTTPS in at most one edge redirect step (if the HTTP port is open); HTTPS to a valid endpoint returns the app response rather than redirecting back to the same HTTPS URL.

In the `curl -v` trace, record `HTTP status`, `Location`, host, and port on **every** redirect hop. Never look only at the final response.

If production permits HTTPS only and port 80 is completely closed, HTTP requests may fail at the network layer; that can also be a valid policy rather than requiring a redirect.

### 7.2. Inspecting at the proxy

Confirm:

- Where **TLS actually terminates** and public port 443.
- That the scheme header is computed from the request **before TLS termination**, not from a downstream HTTP hop.
- The values of `Forwarded`/`X-Forwarded-Proto`, `X-Forwarded-Host`, and `X-Forwarded-Port` sent by the final proxy to the backend.
- Whether the proxy performs its own redirects and whether they alter host, path, or port.
- Whether scheme/path rewriting occurs between ingress, API gateway, and reverse proxy.
- Whether the backend is directly reachable from the Internet; if so, forwarded headers can be spoofed.

An example of **internal, temporary** diagnostic logging after forwarded processing runs:

```text
request.getScheme() = https
request.isSecure() = true
request.getServerName() = api.example.com
request.getServerPort() = 443
```

Never expose such detailed infrastructure info on public endpoints just for debugging. If the app still logs `http/false/8080` for public HTTPS traffic, investigate metadata and filter ordering before modifying Security rules.

### 7.3. Isolating security policies

Locate all redirect sources:

- `.requiresChannel(...requiresSecure())` or equivalent HTTPS policy in `SecurityFilterChain`.
- HTTP → HTTPS redirects at the load balancer or ingress.
- Spring MVC redirects or controllers manually returning `Location`.
- Context path, virtual host, port mapping, and `X-Forwarded-Prefix` configuration.
- Authentication redirects (login page / OAuth2 callback): these are login redirects distinct from HTTPS upgrade redirects.

HTTP `301`, `302`, `307`, and `308` are all redirects, requiring inspection of `Location` and context to identify their origin. With login/OAuth2, a wrong callback hostname or scheme can cause a separate loop even when requests are already secure.

## 8. Trust boundaries: forwarded headers can be spoofed

`X-Forwarded-Proto` is an HTTP header and carries **no cryptographic signature**. A client can send:

```http
GET /public/ping HTTP/1.1
Host: api.example.com
X-Forwarded-Proto: https
```

If an HTTP backend is exposed directly to the Internet and trusts this header, Spring Security can treat the request as secure even though the client never used TLS. Thus `server.forward-headers-strategy=framework` is **only valid when deployed with a trusted proxy boundary**.

Measures to combine:

1. Allow only trusted proxies, ingresses, or load balancers to reach the backend; lock down internal ports via firewalls/security groups/network policies.
2. At the edge proxy, **strip or overwrite** client-supplied `Forwarded` and `X-Forwarded-*` headers from the Internet; emit fresh headers from verified connections and routing.
3. With multiple hops, explicitly define which proxies are trusted and how original scheme/host are determined; never append or overwrite values arbitrarily.
4. If using container **native** support, configure the trusted proxy/IP allowlist and verify `isSecure()` after processing.
5. When forwarded headers are unnecessary, disable trusting them; when needed, do not turn them on merely because "it stops the loop".
6. Validate `Host`, forwarded host, and port before using them to construct absolute redirects, preventing `Location` headers pointing to attacker-controlled domains.

In Spring Framework, `ForwardedHeaderFilter` consumes both standard `Forwarded` and certain `X-Forwarded-*` headers; the filter itself does not distinguish headers added by a trusted proxy from headers injected by a client. **The proxy must perform sanitization.** If infrastructure requires strict IP-based trust, use appropriate container/native or gateway controls.

## 9. Redirect at the edge, in the application, or both?

| Location | Benefits | Caveats |
| --- | --- | --- |
| **Edge/proxy** | Redirects HTTP early, knows public host/port, avoids sending needless HTTP requests to the app | Must configure TLS/certs and routing properly; avoid looping across proxies |
| **Spring Security `requiresSecure()`** | Enforces policy as requests enter the app; acts as a safeguard if an unblocked HTTP path is reached | Must recognize scheme accurately behind proxies and build proper `Location` |
| **Both** | Edge upgrades early, app adds channel verification | Forwarded headers must align and both paths must be tested |

In many production architectures, the cleanest operational split is **the proxy owning ports 80/443 and public redirects**, while Spring Security requires HTTPS as a secondary check on properly interpreted requests. If the app only serves traffic via proxy, firewall off direct non-proxy access to the backend HTTP port.

If the proxy → backend network is not considered trusted, enable TLS on that hop (re-encryption or mTLS) instead of treating forwarded headers as encryption. Forwarded headers merely describe *metadata about* the original client connection.

## 10. What does HSTS help with and what does it not?

HSTS (`Strict-Transport-Security`) is a response header instructing browsers to prefer HTTPS for the host for a set duration after **receiving the header over a valid HTTPS connection**. Example:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

In Spring Security Servlet, security response headers typically support sending HSTS for requests seen as secure. However:

- HSTS **does not replace** TLS certificates, HTTPS listeners, or fixing forwarded headers.
- HSTS on a plain HTTP response cannot establish a trusted HSTS policy.
- If Spring Boot behind a proxy fails to recognize requests as secure, verify whether HSTS is emitted at the **HTTPS edge** or the application.
- `includeSubDomains` is appropriate only if all affected subdomains are HTTPS-ready; never enable `preload` domain-wide without auditing the whole domain and preload list criteria.
- HSTS helps browsers use HTTPS on subsequent visits, but does not eliminate first-visit exposure before the policy is learned.

HSTS is not a server-side mechanism handling HTTP requests from every kind of client. Non-browser API consumers must still enforce HTTPS via endpoints, SDKs, proxies, and dedicated security controls.

## 11. Redirects do not replace business security

Once the HTTPS channel is working, HTTP statuses also come from other mechanisms:

- `401 Unauthorized` when valid authentication is missing;
- `403 Forbidden` when permissions are missing or CSRF tokens are invalid;
- `404` for non-existent routes;
- `3xx` related to login/session/OAuth2;
- browser errors for TLS certificates, HSTS, or mixed content.

**HTTPS protects transport; authentication verifies identity; authorization enforces permissions; CSRF protects state-changing requests with auto-attached credentials.** Do not use the example's `.permitAll()` for real data. Never disable CSRF, CORS, or the Security filter chain just to "fix" a loop without diagnosing the redirect trigger.

Session cookies should use `Secure` over HTTPS, combined with `HttpOnly` and `SameSite` per application flows. If requests carry tokens/passwords or sensitive bodies, clients must call HTTPS from the outset; receiving a redirect from HTTP cannot undo exposure of payloads already transmitted in plaintext.

## 12. Runnable Java tests

With the project from section 4, create `src/test/java/demo/https/HttpsChannelTest.java`:

```java
package demo.https;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpsChannelTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void insecureRequestIsRedirected() throws Exception {
        mvc.perform(get("/public/ping").secure(false))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        HttpHeaders.LOCATION, startsWith("https://")));
    }

    @Test
    void secureRequestReachesController() throws Exception {
        mvc.perform(get("/public/ping").secure(true))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"message\":\"pong\"}"));
    }
}
```

Run with the wrapper:

```bash
./gradlew test
```

On Windows use `.\gradlew.bat test`.

This test proves `requiresSecure()` distinguishes secure vs. insecure requests in Spring Security and that the endpoint returns the right body. `MockMvc` simulates Servlet requests; **it does not prove** real ingress environments add/sanitize forwarded headers properly, TLS termination and port 443 work, or public Internet redirects do not loop. Run additional verification in staging through real public hosts and reverse proxies.

A minimal deployment integration test suite should check:

1. Public HTTP (if open) redirects to the public HTTPS host with expected path/query and status.
2. Public HTTPS returns the final app response without a `Location` pointing to the same URL.
3. The application sees the right scheme/host/port behind the trusted proxy.
4. Direct Internet access to the backend port is blocked by the network.
5. Spoofed client `X-Forwarded-Proto` headers do not alter outcomes at the proxy.
6. HSTS, `Secure` cookies, authentication, authorization, and callback URLs remain intact.
7. At least one POST/login case and one credentialed API case are tested to catch unintended redirects.

## 13. Deployment variants to watch

**Kubernetes ingress or cloud load balancers:** multiple TLS termination layers and multiple forwarded header types may exist. Identify the final layer holding trustworthy scheme metadata. Switching ingress controllers or adding a CDN can invalidate older `X-Forwarded-Proto` settings.

**Running HTTPS directly in Spring Boot:** real certificates and TLS server settings (`server.ssl.*`) must be configured; `requiresSecure()` only enforces channel policy and can redirect to an unopened port if no HTTPS listener exists.

**Multiple `SecurityFilterChain` beans:** ensure HTTPS policies apply to the right request matchers/chains. A narrow `SecurityFilterChain` for admin and another for APIs can diverge in channel policy if not configured consistently.

**`http://localhost` in development:** you may want plain HTTP locally for simplicity. Scope policies appropriately to profiles and environments; never rely on temporary local exceptions to relax public host policies. In an example with global `requiresSecure()`, local HTTP actively redirects, so `curl -L` cannot complete cleanly without TLS.

**WebSockets and third-party callbacks:** secure WebSocket handshakes use `wss://`. OAuth2/OIDC callbacks need exact schemes and public hosts; wrong proxy settings can send bad redirect URIs to identity providers and trigger failures distinct from channel-security loops.

## 14. Troubleshooting table

| Symptom | Likely diagnosis | Remediation |
| --- | --- | --- |
| Browser reports too many redirects on public HTTPS | Backend sees HTTPS client as HTTP behind proxy | Check `X-Forwarded-Proto`/`Forwarded`, `server.forward-headers-strategy`, trusted proxy chain |
| `Location: https://localhost:8443/...` | Backend uses internal host/port or default port mapping | Check forwarded host/port and edge redirects |
| Local HTTP 8080 redirects to 8443, then connection fails | Policy requires HTTPS with no local TLS listener | Use an HTTPS listener or separate dev profile; not a proxy loop bug |
| HTTPS returns `401`/`403` | Business security or CSRF | Check authentication/authorization/CSRF; do not remove HTTPS requirement |
| HTTPS lacks HSTS | App header writer does not see secure request or edge omits header | Inspect HSTS on HTTPS response and scheme recognition |
| HTTPS works via proxy, yet direct HTTP to backend is treated as HTTPS | Spoofed forwarded headers are trusted | Block direct access and sanitize headers at the proxy |
| Redirects bounce between two hostnames or paths | Inconsistent rewrites/proxy routes/callbacks | Trace every `Location`, host, scheme, port, and prefix across hops |
| Only some routes fail to redirect or stay unprotected | Multiple filter chains, matchers, or gateway rules | Audit rules by URL/method and active filter chain |
| HTTP POST loses body or switches to GET after redirect | Client handling of 301/302 or redirect conditions | Send HTTPS directly; consider 307/308 at edge per client contract |

## 15. Safe deployment checklist

Before signing off on an HTTPS-enforced Servlet API:

- Clearly define the canonical public URL: `https` scheme, hostname, port, context path.
- Identify **exactly** where TLS terminates; protect the internal hop per infrastructure policy.
- Configure HTTP → HTTPS redirects at the edge if the HTTP port is open.
- If Spring Security uses `requiresSecure()`, verify it sees accurate `isSecure()` behind proxies.
- Configure `server.forward-headers-strategy` appropriately **and** trust forwarded headers only from verified proxies.
- Block backend ports from the Internet; have the proxy strip/overwrite untrusted forwarded headers.
- Test public HTTPS responses for absence of redirect loops; inspect every `Location` header.
- Test real hostnames/ports/context paths, POSTs with bodies, logins, cookies, CSRF, and callbacks.
- Configure HSTS and `Secure` cookies appropriately; monitor for spikes in 3xx responses and alert on redirect loops.

## Takeaways

`requiresSecure()` requires requests to be recognized as HTTPS by Spring Security and can redirect when unmet. In the **HTTPS client → proxy → HTTP backend** model, avoiding redirect loops requires forwarding accurate scheme/host/port metadata through a **trusted proxy** and configuring Spring Boot to interpret it. Enable forwarded headers only once the proxy controls their origin; handle HTTP redirects at the edge, manage real TLS properly, and test the public URL end to end.