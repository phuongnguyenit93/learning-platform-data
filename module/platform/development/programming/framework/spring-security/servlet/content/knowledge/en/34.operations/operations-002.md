# TLS Termination, Forwarded Headers, and Trusting Only Designated Proxies

## 1. Goal: Distinguishing the Real Connection from Proxy-Forwarded Metadata

In a **Spring Security Servlet** application, HTTPS may terminate directly at Tomcat/Jetty/Undertow or terminate at a reverse proxy, ingress, load balancer, or API gateway. When **TLS termination** occurs in front of the backend, the browser uses HTTPS, whereas the request sent by the proxy to Spring Boot may be internal HTTP.

Example:

```text
                    Internet / public trust zone
Browser ── HTTPS:443 ──> Reverse proxy / TLS terminator
                                 |
                                 | HTTP:8080 on private network
                                 | X-Forwarded-Proto: https
                                 | X-Forwarded-Host: app.example.test
                                 | X-Forwarded-Port: 443
                                 v
                        Spring Boot Servlet
                        request.getScheme() == ?
                        request.isSecure() == ?
                        redirects / OAuth2 / cookies
```

If the backend only inspects the internal HTTP socket, it may think the request is insecure (`http`, port `8080`) even though the browser connected to the proxy over HTTPS. If the backend trusts any `X-Forwarded-*` from Internet clients, an attacker can forge the scheme/host/port and corrupt redirects, channel checks, or generate malicious links.

**The right goal has two inseparable parts:**

1. A **trusted** proxy accurately describes the public scheme, host, port (and prefix if needed) so Spring MVC/Security constructs URLs and channel logic correctly.
2. **Only** the designated proxy can supply this data; all forwarded headers coming from the Internet must be stripped or normalized before reaching the backend.

`ForwardedHeaderFilter` or `server.forward-headers-strategy=framework` only **interprets headers**; it does not verify by itself which IP address or system created those headers. The trust boundary must be enforced at the network, gateway, and upstream configuration layers.

## 2. TLS Termination Flow and Three Different Perspectives

A request can have three perspectives:

| Layer | What it sees | What it is used for |
| --- | --- | --- |
| Browser | `https://app.example.test/profile` over TLS 443 | Secure Context, HSTS, `Secure` cookies, and integrity with the edge |
| Reverse proxy | TLS handshake with browser; may forward over HTTP or HTTPS | Domain/certificate checks, policy, authentication, routing, and headers |
| Spring Boot Servlet | Socket from proxy, often `http://backend:8080` | `HttpServletRequest`, redirect URLs, OAuth2 callbacks, and channel security |

Suppose the edge has verified TLS successfully but **does not forward headers**; the application may see:

```text
request.getScheme()      = "http"
request.isSecure()       = false
request.getServerPort()  = 8080
```

After the proxy sends accurate public metadata and Spring Boot processes the headers with an appropriate mechanism, the application typically sees:

```text
request.getScheme()      = "https"
request.isSecure()       = true
request.getServerName()  = "app.example.test"
request.getServerPort()  = 443
```

These values reflect the **user-to-proxy connection path**, not that the proxy-to-JVM socket uses TLS. Do not use `request.isSecure()` alone to prove that the backend peer is authenticated or that the proxy → backend link cannot be eavesdropped.

There are three main models:

- **TLS passthrough:** the proxy forwards TLS directly to the backend; the backend decrypts it itself and directly sees HTTPS. Forwarded headers may not be needed to determine the public scheme.
- **TLS termination + HTTP backend:** the edge decrypts, and the backend receives HTTP inside a protected network zone; policy and forwarded headers are needed to reconstruct public URLs.
- **TLS termination + re-encryption:** the edge decrypts and establishes another TLS connection to the backend. You still need to distinguish public host/port from internal host/port; mTLS can confirm the proxy is the backend's peer.

TLS from browser to edge does not protect the HTTP proxy → backend hop when the two components reside in different trust zones. For cross-host networks, multi-tenant setups, or compliance requirements, consider re-encryption/mTLS rather than assuming "the internal network is always safe".

## 3. Important Headers and Scope of Meaning

There are two header families:

**De facto family:**

```http
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
X-Forwarded-For: 198.51.100.25
X-Forwarded-Prefix: /portal
```

**Standardized `Forwarded` header (RFC 7239):**

```http
Forwarded: for=198.51.100.25;proto=https;host=app.example.test
```

| Field | Role | Warning |
| --- | --- | --- |
| `X-Forwarded-Proto` / `proto` | Scheme used by the user at the trusted proxy | `https` can be self-asserted by a client if not sanitized |
| `X-Forwarded-Host` / `host` | Public host/authority used to build URLs | An untrusted host can cause host-header poisoning |
| `X-Forwarded-Port` | Public port, usually `443` | Wrong port leaks `:8080`/`:8443` in URLs |
| `X-Forwarded-Prefix` | Public path prefix when ingress rewrites paths | Not all proxies/frameworks handle this identically |
| `X-Forwarded-For` / `for` | Chain of client/hop IPs | Not proof of an authenticated user; multiple hops require policy |
| `Host` | HTTP authority of the request forwarded by proxy to backend | Must also be validated or fixed by the route |
| `X-Forwarded-Ssl` and aliases | Used by some legacy systems to indicate HTTPS | Avoid accepting conflicting, unnormalized formats |

`Forwarded` can contain **multiple elements** for multiple proxy hops. Values like `for=`, `proto=`, and `host=` may have quoting/IPv6 and standard parsing rules. Do not write your own parser using `split(",")`/`split(";")` and trust the first or last element without a trust-hop contract.

When conflicting `Forwarded` and `X-Forwarded-*` headers coexist, different frameworks/versions may prioritize them differently. **The safe policy is to normalize at a trusted gateway**, forwarding only a governed, consistent set of headers; the backend should not guess which set is the truth.

## 4. Threat Model: Who Is Allowed to Assert HTTPS?

For example, an attacker calls HTTP directly on the backend and self-declares:

```http
GET /api/data HTTP/1.1
Host: internal.example
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
```

If the backend enables forwarded header processing without blocking direct access, `request.isSecure()` can return `true` **even though the attacker only used HTTP**. That is why headers must never be used as a TLS verification mechanism.

Another variant is **host-header poisoning**:

```http
GET /login HTTP/1.1
Host: app.example.test
X-Forwarded-Proto: https
X-Forwarded-Host: attacker.example
```

If the backend constructs absolute links from an attacker-controlled host, email/password reset redirects, OAuth2 redirect URIs, or `Location` headers can be corrupted or point to a foreign domain. OAuth2 providers that validate redirect URIs will usually reject mismatched URIs, but that does not replace input control at the proxy.

Minimum safety conditions:

1. Only designated proxies/gateways have a network path to the backend.
2. The proxy blocks, strips, or overwrites client-supplied forwarded headers **before** forwarding.
3. The proxy computes scheme, host, and port from its **verified** TLS listener and route, rather than copying untrusted headers from the client.
4. The backend enables exactly one forwarded-header processing strategy.
5. Authorization, user authentication, CSRF, and session security still operate independently; `X-Forwarded-Proto` does not authenticate a principal.
6. External network tests confirm clients cannot bypass the proxy or alter the public host/scheme.

## 5. Choosing the Spring Boot Strategy for Servlet

Spring Boot 3.x provides the property:

```yaml
server:
  forward-headers-strategy: framework
```

Common values:

| Value | Meaning | When to choose |
| --- | --- | --- |
| `none` | Do not interpret forwarded headers via Boot integration | Backend serves TLS directly or does not trust upstream headers |
| `framework` | Uses Spring Framework's mechanism, typically based on `ForwardedHeaderFilter` on Servlet | When the proxy has normalized forwarded headers and you want Spring to process request URLs |
| `native` | Uses the web server/container's native handling when supported | When container-specific behavior is needed, e.g., Tomcat `RemoteIpValve` |

**Do not enable both mechanisms and add extra custom filters** without defining ordering and contracts. Two layers interpreting forwarded headers together can produce unpredictable results, especially across multi-hop proxy chains.

In some environments, Boot may choose a default strategy based on the deployment platform; for trust-boundary problems, **configure it explicitly and test on your exact Boot/container version** rather than guessing defaults.

### `framework` and `ForwardedHeaderFilter`

`ForwardedHeaderFilter` is a Spring Framework Servlet filter that can wrap the request/response to reflect forwarded scheme/host/port/prefix when building URLs and redirects. When Boot already auto-registers the filter via the `framework` strategy, **do not arbitrarily register another equivalent filter**.

The filter has a `removeOnly` mode: strips forwarded headers **without using them** to alter the request. This mode is useful when the backend receives untrusted headers and wants to erase their trace before downstream use; it **does not replace** proxy sanitization and cannot distinguish "real headers" from "forged headers" by content alone.

### `native` and Tomcat Configuration

In a Servlet application running on Tomcat, the `native` strategy can use `RemoteIpValve` to interpret proxy headers. Related Tomcat options include lists of internal/trusted proxies and proto/remote IP headers. Exact configuration must be checked against your current Boot/Tomcat version, multi-proxy topology, and `server.forward-headers-strategy` setting.

**Do not assume `native` fixes trust-boundary flaws with a single flag.** When reverse proxy IPs change, proxy chains have multiple tiers, or CIDRs are configured too broadly, the native mechanism itself can mistakenly trust untrusted values. Regardless of strategy, the network layer must block direct access and the edge must normalize headers.

## 6. Practical Example: Spring Boot Servlet Behind Nginx HTTPS

Assumptions:

- Public URL: `https://app.example.test`
- Nginx runs on the same host as Spring Boot.
- Nginx is the TLS terminator on port 443.
- Spring Boot listens only on `127.0.0.1:8080`; this port is **not** public.
- Nginx sets fixed public host/scheme/port values from a defined route.
- HTTP Basic with a demo account is used only to illustrate an authenticated endpoint; using Basic over the Internet is not recommended.

### 6.1. Spring Boot 3.3.5 / Java 17+ Project

Structure:

```text
forwarded-headers-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/forwarded/
    │   │   ├── ForwardedDemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── TransportController.java
    │   └── resources/application.yml
    └── test/java/demo/forwarded/TransportSecurityTest.java
```

Create `build.gradle`:

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
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` uses Spring MVC on a Servlet container, and `spring-boot-starter-security` protects endpoints with a filter chain. The project needs a Gradle wrapper compatible with Java 17; if there is no wrapper yet, install Gradle and generate the wrapper per your team's build process.

Create `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080
  forward-headers-strategy: framework
```

This configuration binds only to loopback in the demo. If the backend runs in a different container from Nginx, `127.0.0.1` is no longer shared; you must use a private service/network, a policy allowing only the proxy to call in, and potentially TLS/mTLS on the internal hop.

Create `src/main/java/demo/forwarded/ForwardedDemoApplication.java`:

```java
package demo.forwarded;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ForwardedDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ForwardedDemoApplication.class, args);
    }
}
```

### 6.2. SecurityFilterChain and HTTPS Requirement

Create `src/main/java/demo/forwarded/SecurityConfig.java`:

```java
package demo.forwarded;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    UserDetailsService localUsers() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo-only")
                        .roles("READER")
                        .build());
    }

    @Bean
    SecurityFilterChain appSecurity(HttpSecurity http) throws Exception {
        return http
                .requiresChannel(channel -> channel
                        .anyRequest().requiresSecure())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/diag/transport").permitAll()
                        .requestMatchers("/api/self").hasRole("READER")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

**Technical meaning:**

1. `.requiresChannel(...requiresSecure())` requires the request to be viewed as HTTPS by Spring Security. With forwarded headers **properly trusted**, it inspects the public scheme. If the scheme is still `http`, Spring Security may return a redirect to HTTPS, even if the edge already terminated TLS.
2. `.requiresSecure()` **does not verify the origin of `X-Forwarded-Proto`**. If an attacker calls the backend directly and asserts `https`, this condition can be fooled.
3. `httpBasic()` is only for authentication demonstration. `{noop}` does not hash passwords and must not be used in production; test credentials are only suitable on loopback.
4. Do not arbitrarily disable CSRF. The demo API only uses GET. If the application uses session cookies and state-changing methods, a dedicated CSRF design is required.
5. In production, configuring HTTPS redirects primarily at the **edge** is usually clearer, though requiring HTTPS at the app can serve as defense-in-depth when the trust boundary is enforced.

**Do not use this HTTPS requirement configuration as a substitute for network policy.** On the proxy → backend link, traffic may still travel over HTTP; the HTTPS check only inspects the request metadata visible to the app.

### 6.3. Transport Diagnostics Endpoint

Create `src/main/java/demo/forwarded/TransportController.java`:

```java
package demo.forwarded;

import java.security.Principal;
import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TransportController {

    @GetMapping("/diag/transport")
    public Map<String, Object> transport(HttpServletRequest request) {
        return Map.of(
                "scheme", request.getScheme(),
                "secure", request.isSecure(),
                "host", request.getServerName(),
                "port", request.getServerPort());
    }

    @GetMapping("/api/self")
    public Map<String, Object> self(
            HttpServletRequest request,
            Principal principal) {
        return Map.of(
                "name", principal.getName(),
                "secure", request.isSecure());
    }
}
```

`HttpServletRequest` is passed to the controller by Spring MVC after the required filters have run. The `/diag/transport` endpoint here is only for **loopback/testing**, because exposing host/port configuration details may be inappropriate for a public application. In production, replace it with a minimal health check that does not expose sensitive operational data.

`request.isSecure()` is a property **from the Servlet view after processing forwarded metadata**, not the result of verifying the client's original certificate in the controller.

## 7. Configuring Nginx as a Trusted TLS Terminator

The following snippet is an example for an Nginx instance at the edge, receiving TLS **directly from the browser** and forwarding to Spring Boot on the same host over loopback. Domain/certificate paths are architectural placeholders and must be replaced with real resources; configure TLS protocols/ciphers/certificate lifecycles according to your infrastructure policy.

```nginx
server {
    listen 80;
    server_name app.example.test;
    return 308 https://app.example.test$request_uri;
}

server {
    listen 443 ssl;
    server_name app.example.test;

    ssl_certificate     /etc/nginx/certs/app.example.test.crt;
    ssl_certificate_key /etc/nginx/certs/app.example.test.key;

    location / {
        proxy_http_version 1.1;

        # Public identity comes from the governed route/certificate.
        proxy_set_header Host app.example.test;

        # Overwrite forwarded fields rather than copying from the client.
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host app.example.test;
        proxy_set_header X-Forwarded-Port 443;

        # With a single edge proxy, peer IP can come from $remote_addr.
        proxy_set_header X-Forwarded-For $remote_addr;

        # Clear standard header and unused aliases/prefixes to prevent conflicts.
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Prefix "";
        proxy_set_header X-Forwarded-Ssl "";

        proxy_pass http://127.0.0.1:8080;
    }
}
```

This configuration emphasizes three invariants:

- `X-Forwarded-Proto` is **`https` because the proxy's own port 443 SSL listener** verified TLS. If Nginx sits behind another load balancer, do not blindly set `https` if Nginx still accepts direct HTTP requests from untrusted sources.
- `X-Forwarded-Host` is set from the **designated** route hostname, not copied from the browser-sent `X-Forwarded-Host` value. Using a fixed host suits single-domain examples and helps prevent host-header poisoning.
- Backend port 8080 is loopback-only. An equivalent setup on Kubernetes must use an internal service and `NetworkPolicy`/ingress routing rather than treating every Pod in the cluster as trusted by default.

Some deployments need dynamic public hosts or path prefixes. In those cases, the valid hostname list and route mapping must be controlled by the proxy/ingress, never taken directly from client headers. If there are multiple proxy hops, the `X-Forwarded-For` policy must be designed explicitly; **never use IP forwarding as proof of identity**.

**Important:** many reverse proxies pass through headers that are not reset by default. Therefore, proactively clearing/overwriting `Forwarded` and all related identity/transport aliases is a security configuration requirement, not an aesthetic detail.

## 8. Observing with curl: Valid Flow vs. Spoofed Flow

Start the Java application:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

### 8.1. Direct HTTP Call Without Forwarded Headers

```bash
curl -i http://127.0.0.1:8080/diag/transport
```

With `.requiresSecure()` in the demo, expect **an HTTPS redirect** (HTTP 3xx) instead of JSON. The exact `Location` depends on Spring Security's `PortMapper`, host, Servlet port, and container configuration; do not predict the exact URI from a simplified example.

### 8.2. Simulating a Proxied Request

```bash
curl -i http://127.0.0.1:8080/diag/transport \
  -H "X-Forwarded-Proto: https" \
  -H "X-Forwarded-Host: app.example.test" \
  -H "X-Forwarded-Port: 443"
```

When the filter is active and no other rule rejects it, the returned JSON looks like:

```json
{
  "scheme": "https",
  "secure": true,
  "host": "app.example.test",
  "port": 443
}
```

**This tests header-processing functionality, not security.** We sent `X-Forwarded-Proto` ourselves over HTTP and the application still treated the request as `secure`. That is precisely why production must block direct calls and ensure the proxy writes the headers.

### 8.3. Calling Through a Real HTTPS Proxy

After installing a valid certificate and pointing the public host to Nginx:

```bash
curl -i https://app.example.test/diag/transport
```

Even though the backend socket is still HTTP/8080, the JSON seen by Spring Boot must match `scheme=https`, `secure=true`, `host=app.example.test`, `port=443`. Do not use `curl -k` to "prove TLS is secure": disabling certificate verification is only acceptable in controlled debugging scenarios.

### 8.4. Testing Standardized `Forwarded`

Another local test:

```bash
curl -i http://127.0.0.1:8080/diag/transport \
  -H "Forwarded: proto=https;host=app.example.test"
```

If the `framework` strategy and filter support it, the request can be treated as HTTPS with the correct public host. This test also demonstrates that anyone with direct access to the backend **can inject forwarded metadata** if the network boundary is not locked down.

## 9. Why Do Redirect Loops Happen Behind a Proxy?

Common scenario:

1. Browser requests `https://app.example.test/account`.
2. Proxy terminates TLS and calls `http://backend:8080/account`.
3. Spring Security misses or misreads forwarded metadata and sees `http`.
4. `.requiresSecure()` returns a redirect to `https://app.example.test/account` (or another URI/port).
5. Browser calls the proxy again over HTTPS.
6. Proxy sends internal HTTP again; the loop continues.

Diagram:

```text
Browser HTTPS
   |
   v
Proxy TLS termination --HTTP--> Spring Boot
                              sees scheme=http
                                   |
                                   v
                         302/redirect HTTPS
                                   |
                                   v
Browser HTTPS -> Proxy -> Spring Boot -> redirect ...
```

Symptoms may include `ERR_TOO_MANY_REDIRECTS`, `curl -L` repeating, consecutive 302s in ingress logs, or users unable to complete OAuth2 login.

Distinct causes:

| Symptom | Likely cause | Verification path |
| --- | --- | --- |
| Public HTTPS always receives 302 to the same URL | Backend always thinks `isSecure=false` | Check `X-Forwarded-Proto` at trusted proxy and filter/strategy |
| Redirect leaks `:8080`, `:8443`, or internal host | Public host/port reconstructed incorrectly | Check `X-Forwarded-Host`, `X-Forwarded-Port`, `Host`, and port mapping |
| OAuth2 callback is `http` instead of `https` | Public base URL derived from request is wrong | Check forwarded metadata and registered redirect URI |
| Redirect alternates between two hosts | Proxy rewrites host inconsistently or `Host` is unvalidated | Set canonical host and inspect route |
| Only one replica loops | Different environment config, proxy chain, or strategy | Compare configs/headers across replicas |
| Secure cookie is not sent back | Cookie `Secure`, domain, SameSite, or scheme inferred wrong | Inspect `Set-Cookie`, TLS, public origin, browser rules |
| HSTS makes browser upgrade HTTP to HTTPS | HSTS works, but proxy/backend handles scheme wrongly | Distinguish browser upgrade from server-generated 302 |

Do not fix this by **disabling the HTTPS requirement entirely** when the real issue is the proxy not forwarding metadata properly. Nor should you trust all forwarded headers on a public backend to "fix the loop"—that turns an availability bug into a security vulnerability.

## 10. OAuth2 Login, Absolute URLs, and Cookies Behind a TLS Proxy

### OAuth2 Redirect URI

A Spring Security OAuth2 Client application often uses a redirect URI with a base URL variable:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          login-provider:
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
```

This is an **illustrative snippet**; it lacks `provider` metadata/issuer URI or endpoints and is **not a standalone runnable OIDC configuration**. At runtime, `{baseUrl}` usually depends on the public URL derived from the request. If forwarded host/proto/port are wrong, the redirect URI can become `http://internal:8080/...`, causing the provider to reject it with `redirect_uri_mismatch`.

The solution involves accurate provider/registration configuration, a forwarded strategy behind a trusted proxy, and verifying that the **public** redirect URI matches the URI registered at the identity provider. Never register broad wildcard redirect URIs to bypass mismatches.

### Secure Cookies

Spring Security session or other cookies may require these attributes:

- **`Secure`**: sent only over HTTPS per browser rules.
- **`HttpOnly`**: blocks JavaScript access to the cookie.
- **`SameSite`**: mitigates certain cross-site cookie risks; must fit OAuth2 login callbacks/redirects.
- **Domain/Path**: must match the valid public host/prefix.

Behind TLS termination, the backend may need to know the public request is HTTPS to issue redirects/cookies properly. Still, **do not treat `isSecure=true` from a client header as proof of security**, and do not use forwarded headers to bypass CSRF or domain policy checks.

You can set an intentional session cookie policy in Boot depending on your product:

```yaml
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
```

In production, deploy `Secure` only when users actually access over HTTPS, and configure SameSite specifically based on flows; do not add attributes blindly and skip browser testing.

## 11. Preventing Host-Header Poisoning When Generating URLs

Code might build an absolute URL from the request:

```java
String scheme = request.getScheme();
String host = request.getServerName();
int port = request.getServerPort();
```

After the framework processes forwarded headers, all three values may come from proxy-forwarded headers. If clients are allowed to forge `X-Forwarded-Host`, the application could generate links like:

```text
https://attacker.example/reset?token=...
```

when the actual application site is `https://app.example.test`.

Countermeasures:

1. **At ingress:** pin/allowlist valid hosts per route and certificate; strip client-sent forwarded hosts.
2. **At the application:** when generating sensitive links sent by email, consider using a **configured canonical public base URL** instead of trusting request metadata completely.
3. **At OAuth2:** register exact redirect URIs; do not use dangerous wildcards.
4. **In tests:** intentionally send invalid `Host` and `X-Forwarded-Host` through the public endpoint; ensure redirects/links never point to an attacker domain.
5. **In logging:** record normalized domain/correlation IDs; do not log raw credentials or links containing tokens.

You do not need to forbid all dynamic hosts if the product is genuinely multi-domain; maintain a server-managed **tenant ↔ allowed host mapping** and avoid relying on client-asserted data.

## 12. Multiple Proxy Tiers and Trusted Hops

A realistic topology:

```text
Browser -> CDN -> Cloud Load Balancer -> Ingress -> Spring Boot
           TLS      TLS/HTTP?          HTTP?
```

At each hop, document clearly:

- Which hop is the **first entry point** allowed to accept Internet requests?
- Which hop actually sees the user's HTTPS connection?
- Which hop may create or sanitize `Forwarded`/`X-Forwarded-*`?
- Which hop could be called directly, bypassing authentication/routing?
- Which hop receives the original client IP and under what contract?
- Which exact hop does the backend trust, or which designated proxy network?

If the CDN already sent `X-Forwarded-Proto=https`, and an internal ingress uses the `$scheme` variable of the **CDN → ingress HTTP hop** and overwrites it to `http`, the backend sees the wrong scheme and may enter a redirect loop. Conversely, if ingress copies `$http_x_forwarded_proto` verbatim from any client, an attacker can spoof it.

**Rule:** only accept public metadata from an upstream **authenticated by network/identity**, then normalize it into a governed header set before passing it to the backend. If the upstream is untrusted, compute the public scheme from the listener/route controlled by that hop itself. Never patch around issues by trusting whatever values happen to be present.

In container/orchestrator systems, you can use firewalls, security groups, Kubernetes NetworkPolicy, service mesh policies, workload identity, and mTLS. A security group left open to an entire VPC/cluster broader than needed can allow an internal workload to impersonate a proxy and inject identity/transport metadata.

## 13. `X-Forwarded-For`, Client IP, and Proxy Verification

`X-Forwarded-For` is often a multi-hop IP list:

```http
X-Forwarded-For: 198.51.100.25, 10.0.1.8, 10.0.2.12
```

This list **has no trustworthiness if the client can prepend entries** and the proxy lacks a policy to separate trusted hops. Do not write authorization rules like:

```java
// UNSAFE: trusts an IP from a client-controllable header.
String clientIp = request.getHeader("X-Forwarded-For");
```

`clientIp` is unverified data unless normalized by a trusted chain. Verified IPs can be used for rate limiting/auditing and supplementary policies, but **never use IP or forwarded headers as a substitute for user authentication**.

If the application must verify allowed proxies:

- Prefer network rules blocking direct backend access over checking a header in code.
- For Tomcat native processing, inspect options for internal/trusted proxies and test on your real topology.
- In mTLS environments, authenticate the certificate/workload identity of the **immediate peer** and do not trust a header assertion from a regular client.
- Do not treat an IP address in `X-Forwarded-For` as the **peer socket** address connected to the JVM.
- If the framework alters `getRemoteAddr()` based on forwarded metadata, `getRemoteAddr()` in a controller is not necessarily the original TCP peer address either.

In most applications, the backend does not need to classify every hop in Java code; **designating a single trusted ingress proxy** and having infrastructure guarantee it is the sole source of forwarded metadata is a much easier model to audit.

## 14. MockMvc Testing with Spring Security and Forwarded Headers

We test **two different contracts**:

1. The application **processes** incoming headers and reconstructs the public request.
2. Infrastructure **prevents Internet clients from forging** fake headers and blocks direct access.

MockMvc suits contract (1), but does not prove (2). A MockMvc test without real networking **cannot** confirm firewalls, TLS certificates, mTLS, or Nginx sanitization.

Create `src/test/java/demo/forwarded/TransportSecurityTest.java`:

```java
package demo.forwarded;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TransportSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void httpRequestWithoutForwardedMetadataIsRedirected()
            throws Exception {
        mvc.perform(get("/diag/transport"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void trustedForwardedMetadataChangesServletView() throws Exception {
        mvc.perform(get("/diag/transport")
                        .header("X-Forwarded-Proto", "https")
                        .header("X-Forwarded-Host", "app.example.test")
                        .header("X-Forwarded-Port", "443"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.scheme").value("https"))
                .andExpect(jsonPath("$.secure").value(true))
                .andExpect(jsonPath("$.host")
                        .value("app.example.test"))
                .andExpect(jsonPath("$.port").value(443));
    }

    @Test
    void basicCredentialsAndHttpsMetadataAreSeparateChecks()
            throws Exception {
        mvc.perform(get("/api/self")
                        .header("X-Forwarded-Proto", "https")
                        .header("X-Forwarded-Host", "app.example.test")
                        .header("X-Forwarded-Port", "443")
                        .with(httpBasic("alice", "demo-only")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"))
                .andExpect(jsonPath("$.secure").value(true));
    }

    @Test
    void forwardedHttpsDoesNotAuthenticateAUser() throws Exception {
        mvc.perform(get("/api/self")
                        .header("X-Forwarded-Proto", "https")
                        .header("X-Forwarded-Host", "app.example.test"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidPasswordIsNotMadeValidByForwardedHttps()
            throws Exception {
        mvc.perform(get("/api/self")
                        .header("X-Forwarded-Proto", "https")
                        .with(httpBasic("alice", "wrong")))
                .andExpect(status().isUnauthorized());
    }
}
```

Run:

```bash
./gradlew test
```

On Windows:

```powershell
.\gradlew.bat test
```

This test suite uses Spring Boot context and MockMvc with filter integration. With other stacks or custom configs, ensure `ForwardedHeaderFilter` actually participates in the MockMvc filter chain; if the `framework` strategy is only applied in the real server, verify test wiring and add the filter to MockMvc matching real configuration rather than weakening security expectations to "pass".

**Point to remember:** the second test intentionally sends forwarded headers on a mock request to prove Spring processes them. That is **not a security pass** if the backend is exposed; the network tests in the next section verify headers cannot be spoofed through the public entry point.

## 15. End-to-End Verification at the Trust Boundary

After deploying Nginx/ingress and the backend, at minimum run these independent checks:

### 15.1. Backend Cannot Be Called Directly from Outside

From a host outside the proxy network (not localhost):

```bash
curl -i --connect-timeout 3 http://backend-internal.example:8080/diag/transport
```

Expect **inability to connect via disallowed external paths**, not a fake "secure" response from the application. The hostname is an example; in a real network, use the internal backend address your test environment is authorized to test. Check security groups, load balancer backend targets, and Kubernetes service type/NetworkPolicy.

### 15.2. Clients Cannot Forge `X-Forwarded-Proto`

```bash
curl -i https://app.example.test/diag/transport \
  -H "X-Forwarded-Proto: http" \
  -H "X-Forwarded-Host: attacker.example" \
  -H "Forwarded: proto=http;host=attacker.example"
```

Going through the **official TLS listener** of the demo Nginx, the backend must still see the proxy-set public values: `scheme=https`, `host=app.example.test`, `port=443`. If the backend sees the attacker host, re-check header-stripping policy and proxy/filter ordering.

### 15.3. Public HTTP Only Redirects to Canonical HTTPS

```bash
curl -I http://app.example.test/diag/transport
```

With the demo Nginx, expect status `308 Permanent Redirect` and `Location` starting with `https://app.example.test/`. Never construct `Location` from an un-allowlisted `Host`. `curl -I` sends HEAD; if a route behaves differently on HEAD, test the corresponding GET with `curl -i`.

### 15.4. No Infinite Redirects

```bash
curl -IL --max-redirs 5 https://app.example.test/diag/transport
```

Verify the response chain does not redirect infinitely or bounce between http/https; `curl` reports an error when `--max-redirs` is exceeded. Inspect the hops and `Location` values emitted by proxy/backend; do not treat a single 301/302 redirect by itself as a bug.

### 15.5. Checking OAuth2 Callbacks and Cookies

If the application has OAuth2 login, verify that the callback URL and `redirect_uri` at the authorization server use the exact **public HTTPS host**, without backend ports or internal DNS. Check `Secure`, `HttpOnly`, `SameSite`, domain/path attributes in the browser.

### 15.6. Simulating a Single Proxy-Hop Fault

Temporarily omit a forwarded header in a controlled staging environment: does the app redirect wrongly? Does a proxy hop overwrite `https` with `http`? Are metrics detecting redirect loops, spikes in 302s, and login failures?

These tests must be executed on a **real or staging-equivalent** topology. MockMvc does not test network-level trust.

## 16. Observing the System Without Exposing Secrets

When troubleshooting operational errors behind a TLS proxy, distinguish **original** data from data **after forwarding processing**. In a safe environment, you can temporarily log:

- correlation/request ID issued by the edge and received by the app;
- validated public route/domain;
- proxy/ingress name or workload identity;
- `scheme`, `serverName`, `serverPort`, `isSecure` **after the filter**;
- HTTP status and sanitized `Location`;
- latency at proxy, latency at application, and redirect count.

Do not log raw bearer tokens, cookies, Authorization headers, full JWTs, or user sessions. Do not expose a full diagnostics endpoint to the Internet if it could be abused to map internal topology.

An observation table:

| Data | Where to measure | Bad sign |
| --- | --- | --- |
| TLS negotiated protocol/cert | Edge | Wrong host/expired certificate, TLS handshake failure |
| Original public scheme | Edge after verification | Public HTTP mixed with HTTPS on the wrong route |
| Sanitized forwarded scheme | Proxy → backend | `http` even though public is HTTPS |
| Reconstructed Servlet request | Spring Boot | `isSecure=false`, internal host/port |
| `Location` | HTTP response | Redirect to same URI, internal host, or attacker host |
| Browser cookie | Client DevTools | Cookie missing Secure/Domain/Path or blocked |
| Login/auth flow | App/IdP | `redirect_uri_mismatch`, state mismatch, auth loop |

When debugging across tiers, use a correlation ID to join a public request with the upstream proxy request. Separate `401/403` errors from authentication/authorization from `3xx` errors from scheme/redirects. These issues can occur together yet have different root causes.

## 17. Common Configuration Mistakes and Right Fixes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Enabling `framework` while backend is still public | Client self-asserts `X-Forwarded-Proto=https` | Block direct access; force traffic through trusted proxy |
| Edge fails to strip client `Forwarded` | Conflicts/host poisoning | Strip Internet-originating headers and normalize at one source |
| Edge copies client's `X-Forwarded-Proto` | HTTPS spoofing | Compute scheme from TLS listener/authenticated upstream |
| Ingress uses `$scheme=http` despite CDN receiving HTTPS | 302 loop | Design multi-hop contract and verify CDN-to-ingress |
| Wrong public port | `Location` contains `:8080`/`:8443` | Send right public port; check port mapper |
| Using `request.isSecure()` as proof of backend TLS | May skip internal hop security | Verify peer via network policy/mTLS and real transport |
| Building absolute URLs from un-allowlisted host | Redirects/links to attacker domain | Canonical host or managed tenant-domain mapping |
| Using `X-Forwarded-For` as identity | Client IP spoofing and wrong authorization | Separate authentication and trusted proxy chain policy |
| Enabling both framework and native filters | Unclear wrap/unwrap order | Choose one strategy and test on target container |
| Testing only MockMvc and skipping network tests | Unknown if backend is exposed | Test direct access and header spoofing from Internet |
| Registering OAuth2 redirect-uri with internal host | Login failure | Configure valid public HTTPS callback |
| Disabling CSRF thinking the edge protects it | Cross-site risk with session cookies | Keep CSRF when credentials are auto-sent by browser |
| Missing Secure cookie behind termination | Cookie may be sent over HTTP if browser allows | Check TLS policy and secure cookies |
| Trusting an overly broad proxy CIDR list | Any internal workload can inject headers | Restrict source to real workloads/proxies; separate trust zones |
| Inconsistent HTTP redirects at both edge and backend | Redirect loop | Enforce canonical HTTPS at edge; align forwarding for backend |

Do not treat all these errors with a single setting. The problem must be solved across **network topology**, **header normalization**, **Servlet forwarding**, and **Spring Security configuration**.

## 18. Deployment Rules for Kubernetes / Ingress / Service Mesh

In Kubernetes, a Spring Boot Service may only be `ClusterIP` yet still be reachable from other Pods. `ClusterIP` **does not mean only ingress is allowed to call it**. If the application trusts `X-Forwarded-*`, control access sources with NetworkPolicy or appropriate mesh policies.

Items to evaluate:

1. Which ingress controller actually terminates TLS? If there is an external CDN/LB, who holds the original client TLS info?
2. Does ingress sanitize `Forwarded` and `X-Forwarded-*` from untrusted sources?
3. Are ingress/service mesh permitted to overwrite proto/host/port, and do they route canonical hosts?
4. Can backend Pods be called from Pods outside ingress?
5. When ingress → backend uses HTTP, is the link inside a protected trust zone? If not, use TLS/mTLS.
6. Is `server.forward-headers-strategy` identical across all replicas and environments?
7. If ingress rewrites `/portal` to `/`, is `X-Forwarded-Prefix`/context-path consistent?
8. Do OAuth2 callbacks and absolute redirects resolve to the right public host/port after rewrites?
9. Do Secure cookies, CORS, and CSRF match the real public origin?
10. During failover/node migration, does any new hop drop or alter forwarded headers?

With service mesh/Envoy, prioritize trust-hop and header-sanitization settings in the ingress/gateway itself rather than fabricating client-controlled headers in the application. Route and policy audits must accompany network topology changes.

## 19. Pre-Production Security and Operations Checklist

- Public traffic passes only through designated edges/ingresses using TLS with valid certificates/hostnames.
- Backend cannot be reached directly from the Internet or unauthorized workloads.
- Edge **strips/overwrites** all client-sent forwarded headers, including `Forwarded` and aliases affecting public URLs.
- Public hosts are allowlisted or fixed per route, never taken from attacker-controllable values.
- Public scheme, host, port, and prefix are accurately reflected in Spring Servlet requests.
- Choose **one** Boot strategy—`framework`, `native`, or `none`—based on topology; avoid duplicate filters.
- Spring Security `.requiresSecure()`/redirect policies do not loop behind TLS termination.
- Authentication and Authorization do not rely on forwarded headers to prove user identity.
- Proxy → backend HTTP hops have appropriate network policies or re-encryption/mTLS if required by risk.
- `X-Forwarded-For` is used properly for auditing/rate limiting if needed, never as identity.
- OAuth2 login/OIDC redirect URIs, reset links, absolute URLs, and callbacks all use the canonical HTTPS origin.
- `Secure`, `HttpOnly`, `SameSite` cookies, CSRF, and sessions are configured based on public browser behavior.
- Tests cover 3xx redirects, invalid hosts, spoofed proto, double headers, direct backend access, and multi-hop proxies.
- Monitoring detects redirect loops, leaked internal hosts/ports, and certificate/ingress failures.
- Logs never record session cookies, access tokens, or sensitive data from raw headers.

## Key Takeaways

**TLS termination** offloads HTTPS decryption to a proxy; the backend may see internal HTTP. **`Forwarded`/`X-Forwarded-*` help Spring Boot/Spring Security Servlet infer the public scheme, host, and port**, but those headers are **not trustworthy by themselves**. To use them safely, lock down direct backend access, identify the exact trusted proxies, strip/rewrite client headers at the edge, and choose a single forwarded-header processing strategy. Only when both layers—**trust boundary + forwarding interpretation**—align will HTTPS redirects, OAuth2 callbacks, absolute URLs, and cookies work consistently without introducing header-spoofing vulnerabilities.