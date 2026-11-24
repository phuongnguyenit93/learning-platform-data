# HTTPS, Reverse Proxies, and the Application's Public URL

## 1. The deployment problem: the browser sees HTTPS, the app sees HTTP

In development, Spring Boot typically runs at `http://localhost:8080`. In real deployments, users access a public address such as `https://app.example.com`. Between users and the application there may be a **reverse proxy**, load balancer, Kubernetes Ingress, or CDN responsible for accepting connections and performing **TLS termination**.

A common diagram:

```text
Browser / mobile client
        |
        | HTTPS:443, Host: app.example.com
        v
Internet-facing reverse proxy / load balancer
        |  (TLS validation, host and header policy)
        |
        | HTTP:8080 on loopback or protected internal network
        | X-Forwarded-Proto: https
        | X-Forwarded-Host: app.example.com
        | X-Forwarded-Port: 443
        v
Spring Boot + Spring Security
        |
        v
Controller / Service / data
```

If the application sees only the internal HTTP connection and **does not receive verified original address information**, many features can misbehave:

- Redirecting from `/private` to `http://localhost:8080/login` or `http://app.example.com/login` instead of `https://app.example.com/login`.
- OAuth2/OIDC generating a `redirect_uri` with a scheme, host, port, or path that mismatches the callback registered at the Identity Provider (IdP), causing `redirect_uri_mismatch`.
- Generating absolute links in password-reset emails, account verification messages, notifications, or JSON APIs pointing to an internal hostname.
- Session cookies missing the `Secure` attribute per policy, or browsers refusing to send cookies because domain, path, and SameSite do not match.
- HSTS not appearing as expected, or both proxy and application setting the header with conflicting policies.
- The application trusting client-spoofed `X-Forwarded-Host`, leading to **Host header poisoning**, password-reset links pointing to an attacker's domain, wrong redirects, or tenant confusion.

The core issue is not just "turning on HTTPS". You must clearly define the **canonical public URL, where TLS terminates, which network/infrastructure is trusted to write original headers, and how Spring Boot consumes that information**.

This guide uses **Spring Boot 3.x / Spring Security 6.x, Java 17+ on Servlet/MVC**, with a co-located Nginx example. Differences for WebFlux, Kubernetes, and multi-proxy setups are noted separately; do not mix Servlet mechanisms into reactive apps.

## 2. Four components of a public URL

The public URL (*public base URL*, sometimes called external URL/canonical origin) is the address **real users must use** to reach the application.

Example:

```text
https://app.example.com/portal
|____| |_____________| |_____|
scheme       host       path prefix

Standard HTTPS port 443 is usually omitted from the URL.
```

The components must stay consistent:

| Component | Public configuration | Value the backend might see if unhandled |
| --- | --- | --- |
| Scheme | `https` | `http` |
| Host | `app.example.com` | `127.0.0.1`, `backend`, or an internal host |
| Port | `443` (usually hidden) | `8080` |
| Path prefix | `/portal` or none | May have been stripped by the proxy before forwarding |
| Client IP | Verified IP at network edge | IP of the proxy/CDN |
| Request target | `/private`, `/portal/private` | Rewritten path |

Two URL forms must be clearly distinguished:

- **Internal URL**: `http://127.0.0.1:8080`, solely for a co-located proxy to reach the app; never put it in emails, HTML redirects, OIDC callbacks, or user-facing instructions.
- **Public URL**: `https://app.example.com`, configured in infrastructure and used consistently with certificates, DNS, allowed hosts, and authentication systems.

An application should not blindly read `Host` from every HTTP request to build password-reset links. For emails, security callbacks, and proactively emitted public links, use a **controlled public base URL configuration** or an allowlist-verified tenant origin. Forwarded headers help the framework interpret proxied requests; **they do not replace a trusted-origin policy**.

## 3. Where is HTTPS configured?

### 3.1. TLS termination at the reverse proxy

A common architecture:

```text
Client --TLS/HTTPS--> Nginx, Ingress, or Load Balancer
Proxy  --HTTP-------> Spring Boot private backend
```

This model is acceptable **when the backend channel lies inside a protected network boundary**: loopback on the same host, an isolated internal network, or security groups/network policies allowing only trusted proxies to reach the backend port. If the proxy–backend hop crosses untrusted infrastructure or networks, consider TLS/mTLS for that segment instead of assuming HTTP is always safe.

Some systems use **TLS pass-through** so the application directly receives HTTPS; then the URL Spring sees already has the right scheme. Others use **re-encryption**: TLS from client–proxy and TLS again from proxy–backend. Whichever architecture you choose, know **who verifies certificates, who updates TLS config, and who owns the external origin**.

### 3.2. Certificates, HTTPS redirects, and HSTS

At the public edge, ensure:

- Valid certificates for the hostname, proper CA chain, and monitored renewal/rotation; never use self-signed certificates for real customers without a dedicated trust model.
- TLS versions/ciphers matching current policy, restricting plain HTTP and redirecting to HTTPS.
- Redirecting to the **canonical hostname**, avoiding echoing an arbitrary client-supplied `Host` header.
- HSTS only after confirming the site and all dependent assets work over HTTPS; carefully evaluate `includeSubDomains` and `preload`.
- The backend internal port must not be directly public, even if Spring Boot has Basic auth.

**HSTS is not a replacement for HTTPS.** HSTS instructs browsers to prefer HTTPS for a previously recorded host; the initial connection must still be protected by TLS/certificates. Spring Security Servlet enables HSTS by default, but emits the header only when the request is considered secure in its context. If the proxy terminates TLS yet the app sees HTTP due to missing forwarded configuration, **do not assume Spring Security's HSTS header will appear as expected**. Choose either the edge or a properly trusted app to emit HSTS; avoid two layers emitting conflicting policies.

### 3.3. Secure cookies after TLS termination

Web logins using session cookies should verify:

| Attribute | Role | Notes |
| --- | --- | --- |
| `Secure` | Browser sends cookie only over HTTPS per browser rules | Set explicitly on production sessions; do not rely on the backend seeing HTTP |
| `HttpOnly` | JavaScript cannot read the cookie | Does not completely stop other risks like CSRF/XSS; only one layer |
| `SameSite=Lax/Strict/None` | Restricts cross-site cookie transmission | `None` requires `Secure` on modern browsers; consider OAuth2 callbacks/form flows |
| `Domain` | Hostname scope receiving the cookie | Avoid broadening to all subdomains unless needed; host-only cookies are usually better |
| `Path` | URL path scope of the cookie | Watch out when the external app has a `/portal` prefix or reverse proxy rewrites |
| Session ID rotation/expiry | Limits session fixation and overly long sessions | Define timeouts, logout, and session revocation |

A proxy **does not automatically turn an HTTP session cookie missing `Secure` into a secure cookie**. Conversely, setting `Secure=true` while using plain local HTTP where not designed for it may prevent browsers from sending the cookie back. Keep local/test and production configurations clearly separated.

## 4. What do Forwarded and X-Forwarded-* mean?

When a proxy receives `https://app.example.com/private` and forwards internally to `http://127.0.0.1:8080/private`, the backend needs external metadata to build accurate redirects.

Two common header families:

1. RFC 7239 standard header: `Forwarded`, e.g., `Forwarded: for=192.0.2.20;proto=https;host=app.example.com`.
2. `X-Forwarded-*` prefixed headers common across proxies and load balancers.

| Header | Example | Meaning |
| --- | --- | --- |
| `X-Forwarded-Proto` | `https` | External scheme |
| `X-Forwarded-Host` | `app.example.com` | Public host of the request |
| `X-Forwarded-Port` | `443` | Public port |
| `X-Forwarded-For` | `192.0.2.20` | Client IP chain across proxies |
| `X-Forwarded-Prefix` | `/portal` | External prefix when proxy rewrites paths |
| `Forwarded` | `for=192.0.2.20;proto=https;host=app.example.com` | Standard header combining multiple attributes |
| `Host` | `app.example.com` | HTTP Host on the request forwarded by the proxy; must also be controlled |

**A header does not become trustworthy because of its name.** A public client can send:

```http
GET /private HTTP/1.1
Host: app.example.com
X-Forwarded-Proto: https
X-Forwarded-Host: attacker.example
X-Forwarded-Port: 443
Forwarded: proto=https;host=attacker.example
```

If Spring Boot receives this request directly or the proxy forwards spoofed headers without sanitizing them, the application may derive an attacker-chosen origin. Consequences include open redirects to another domain, wrong URLs in emails, tenant confusion, or wrong `isSecure()` handling.

**Protection rule:** the proxy at the **first trust boundary** must strip or overwrite **both the standard `Forwarded` header and all `X-Forwarded-*` headers used by the system**, regardless of what the client sent. The backend must accept connections only from trusted proxies. With multiple proxy tiers, define clearly which tier is trusted to write and read the IP/host/scheme chain.

Configuring `server.forward-headers-strategy=framework` while leaving backend port 8080 exposed to the Internet is a **dangerous configuration**. Enabling forwarded header handling does not verify that the sender is a trusted proxy.

## 5. How does Spring Boot handle forwarded headers?

In Spring Boot 3.x, the main setting is:

```properties
server.forward-headers-strategy=framework
```

Modes:

| Value | Meaning | When to consider |
| --- | --- | --- |
| `none` | Do not use forwarded headers to reconstruct request origin | Backend receives HTTPS directly or infrastructure has no trusted forwarded headers |
| `native` | Uses built-in support of embedded web servers (Tomcat/Jetty/Undertow), depending on type and config | Infrastructure sends simple headers matching web server support; verify trusted proxy policy |
| `framework` | Uses Spring Framework support: Servlet `ForwardedHeaderFilter`, WebFlux `ForwardedHeaderTransformer` | When Spring needs fuller handling of scheme/host/port/prefix |

**Do not enable multiple forwarded-header mechanisms simultaneously assuming "more is safer".** Choose one strategy, inspect the actual web server configuration, and test redirects, links, and cookies thoroughly. In some cloud environments detected by Spring Boot, the default may be `native`; elsewhere it may be `none`. Do not rely on defaults when this is a deployment security requirement.

In Servlet apps, `ForwardedHeaderFilter` adjusts request methods like `getScheme()`, `getServerName()`, `getServerPort()`, and `isSecure()` based on forwarded headers; it also handles corresponding `X-Forwarded-Prefix` scenarios. However, **the filter does not verify the header's origin**. That is the responsibility of network architecture and trusted proxies.

For Tomcat behind a TLS-terminating proxy, Spring Boot documentation also notes:

```properties
server.tomcat.redirect-context-root=false
```

so that `X-Forwarded-Proto` is processed before certain context-root redirects. This property is not a substitute for configuring and verifying the proxy; it applies only to Tomcat in the corresponding scenario.

### 5.1. Avoid registering ForwardedHeaderFilter twice

When using `server.forward-headers-strategy=framework`, Spring Boot configures appropriate forwarded-header handling. Do not simultaneously register a manual `@Bean ForwardedHeaderFilter` without verifying ordering and invocation count, as that can cause unpredictable behavior. If configuring the filter manually, consult Spring Framework documentation on ordering before related filters, dispatch types, and the `removeOnly` variant when you want to strip forwarded headers rather than apply them.

### 5.2. Why compare getRequestURL with the public base URL?

A controller or framework building URLs may read scheme, host, and port from `HttpServletRequest`. When forwarded headers are handled properly, request-based URLs reflect the external origin. However, links **not originating from an HTTP request** (emails sent from a background job) or **security-sensitive links** should use a dedicated public base URL/validated tenant URL setting rather than deriving from an arbitrary HTTP `Host`.

## 6. Deployment configuration pattern: co-located Nginx, Spring Boot listening on loopback only

Assume:

- The fixed public URL is `https://app.example.com` (no path prefix).
- Nginx and Spring Boot run on the same host.
- Nginx listens on Internet ports 80/443; Spring Boot listens only on `127.0.0.1:8080`.
- TLS certificates are issued and stored at real deployment paths.
- In this example, Nginx is the **first trust boundary**, with no upstream CDN/proxy.

Illustrative Nginx configuration:

```nginx
server {
    listen 80;
    server_name app.example.com;

    # Redirect HTTP to the fixed HTTPS hostname.
    return 308 https://app.example.com$request_uri;
}

server {
    listen 443 ssl;
    server_name app.example.com;

    ssl_certificate     /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;

        # Controlled public origin; do not reflect
        # Host/X-Forwarded-Host from an arbitrary client.
        proxy_set_header Host             app.example.com;
        proxy_set_header X-Forwarded-Host app.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;

        # Strip standard header that a client could spoof.
        proxy_set_header Forwarded "";

        # No external path prefix is used in this example.
        proxy_set_header X-Forwarded-Prefix "";
        proxy_set_header X-Forwarded-Ssl "";

        # This is the edge proxy: take the IP connecting to Nginx,
        # do not trust the client's X-Forwarded-For chain.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Real-IP        $remote_addr;
    }
}
```

**This is a skeleton config for the described topology**, not a complete production file. Certificate paths are meaningful only when real files exist with proper permissions; you may also need a default 443 listener rejecting unwanted hosts, timeouts, header size limits, HTTPS monitoring, log redaction, and certificate rotation/reload.

**Note on header cleanup:** Nginx may forward other HTTP headers that are not explicitly overwritten. Real systems must review every header used by the framework/gateway (standard `Forwarded` and `X-Forwarded-*` variants), stripping or normalizing them at the trusted ingress. The snippet above illustrates the core fields for the chosen origin; it **does not claim every possible forwarded header is handled by wildcard**.

If a CDN/load balancer sits in front of Nginx, `$remote_addr` will be that tier's IP rather than the end user's. To use the real client IP for auditing or rate limiting, declare **exact trusted hops/IP ranges** rather than enabling "trust all forwarded for". A client IP derived from proxy chains is distinct from the user identity in `Authentication`.

### Why avoid blindly using proxy_set_header Host $http_host?

`$http_host` can reflect the client's `Host` header. If Nginx accepts a request with an unexpected `Host` and passes it to the backend or forwarded headers, the app may generate client-controlled absolute URLs. In a single-hostname setup, explicitly sending `app.example.com` is simpler and safer. For dynamic multi-tenant hosts, maintain a **verified host/tenant registry** and route to the right tenant instead of accepting arbitrary `Host` headers.

### Internal connectivity and firewall

In `application-prod.properties`:

```properties
server.address=127.0.0.1
server.port=8080
```

This example applies only when Nginx and Spring Boot are **on the same host**. In containers/Kubernetes, `127.0.0.1` inside one pod/container may not be reachable from a reverse proxy running elsewhere. There, the backend may listen in the pod/container network namespace while firewalls, security groups, or `NetworkPolicy` ensure **only trusted proxies/ingress can connect**.

The goal is not that the backend must always use `127.0.0.1`, but that **the backend has no direct Internet path capable of sending spoofed forwarded headers**.

## 7. Java 17+ example verifying how the app perceives its URL

For a repeatable test, we create a Spring Boot Servlet application with:

- `GET /public`: public endpoint to test TLS and routing.
- `GET /private`: endpoint requiring form login, used to observe redirects.
- `GET /admin/diagnostics`: restricted to `ROLE_ADMIN`, returning the request info **interpreted by Spring** (scheme, host, port, secure) and the configured public base URL.
- In-memory demo accounts `viewer` and `admin`; never use in production.

Create a Spring Boot 3.x / Spring Security 6.x / Java 17+ project with `Spring Web` and `Spring Security` dependencies. File:

```text
src/main/java/demo/publicurl/PublicUrlApplication.java
```

```java
package demo.publicurl;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PublicUrlApplication {

    public static void main(String[] args) {
        SpringApplication.run(PublicUrlApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login", "/error")
                    .permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("viewer")
                .password(encoder.encode("viewer123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @RestController
    public static class Routes {
        private final String configuredPublicBaseUrl;

        Routes(
                @Value("${app.public-base-url}") String publicUrl) {
            this.configuredPublicBaseUrl = publicUrl;
        }

        @GetMapping("/public")
        public Map<String, String> publicEndpoint() {
            return Map.of("status", "ready");
        }

        @GetMapping("/private")
        public Map<String, String> privateEndpoint(
                Authentication authentication) {
            return Map.of(
                "message", "authenticated",
                "actor", authentication.getName()
            );
        }

        @GetMapping("/admin/diagnostics")
        public Map<String, Object> diagnostics(
                HttpServletRequest request) {
            return Map.of(
                "scheme", request.getScheme(),
                "host", request.getServerName(),
                "port", request.getServerPort(),
                "secure", request.isSecure(),
                "configuredPublicBaseUrl",
                    configuredPublicBaseUrl
            );
        }
    }
}
```

This is a program **runnable within a Spring Boot project on the Spring classpath**; it cannot be compiled with `javac PublicUrlApplication.java` alone. `@Value` reads application configuration, not browser-supplied data.

**Important:** `/admin/diagnostics` is for learning and controlled investigation; in real products remove it after verification or restrict it to authorized operators with minimal output. Never return raw headers, Cookies, Authorization tokens, or internal network config to clients.

### 7.1. Local run configuration

`src/main/resources/application.properties`:

```properties
spring.application.name=public-url-lab
server.port=8080
app.public-base-url=http://localhost:8080

# Do not trust forwarded headers when the app receives requests directly locally.
server.forward-headers-strategy=none
```

Run:

```bash
./gradlew bootRun

# Windows PowerShell:
# .\gradlew.bat bootRun
```

With local config, `http://localhost:8080/public` returns **200** with JSON `{"status":"ready"}`. Unauthenticated `http://localhost:8080/private` typically returns **302** to the login page. After logging in as `viewer` or `admin`, `/private` returns the authenticated account name.

### 7.2. Production configuration behind proxy

`src/main/resources/application-prod.properties`:

```properties
# For the same-host Nginx example only.
server.address=127.0.0.1
server.port=8080

# Enable only after the trusted proxy strips/overwrites
# forwarded headers from Internet requests.
server.forward-headers-strategy=framework

# Useful when Tomcat runs behind TLS termination.
server.tomcat.redirect-context-root=false

# Cookie policy for public HTTPS.
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax

# Trusted source for generating proactive public links.
app.public-base-url=https://app.example.com
```

Run the production profile in an environment **that actually has the reverse proxy**:

```bash
./gradlew bootRun --args='--spring.profiles.active=prod'
```

Without Nginx/TLS, do not use this profile for local HTTP browser tests: the backend binds only to loopback, and `Secure` cookies may not behave as expected over HTTP. Configure certificates/DNS/proxy before evaluating results.

**Why set a separate public URL even with forwarded headers enabled?** Forwarded headers help Spring interpret **incoming proxied requests**. When the application sends emails from a scheduled job or builds security redirects/links outside a request context, it still needs a configured and controlled origin. Relying solely on `X-Forwarded-Host` for all absolute links risks Host poisoning if any hop is misconfigured.

### 7.3. Across multiple environments

Separate public base URLs:

```text
Local:    http://localhost:8080
Staging:  https://staging.example.com
Prod:     https://app.example.com
```

Each environment needs its own hostname, certificate, OAuth2 callbacks, cookie scope, and secret registrations; never reuse production callbacks/credentials in development. When using a secret manager or config server, restrict write access to `app.public-base-url` because it affects security URLs sent to users.

## 8. Real-world testing from outside the reverse proxy

Once DNS, TLS, and Nginx are running, test from a machine **without direct access to the backend**:

```bash
# 1. Valid certificate, public endpoint returns 200.
curl -i https://app.example.com/public

# 2. HTTP at the public edge must redirect to HTTPS.
curl -i http://app.example.com/public

# 3. Private endpoint without a session -> redirect to login.
curl -i https://app.example.com/private

# 4. Inspect response headers only.
curl -I https://app.example.com/public
```

Expected results:

| Test | What to observe | If different |
| --- | --- | --- |
| Public HTTPS | 200, JSON, no certificate errors | Check DNS/cert/SNI/proxy route/app health |
| Public HTTP | 301/308 to `https://app.example.com/...` | Check port 80 listener and redirect host |
| Anonymous private HTTPS | 302 to login (due to form login) | Check SecurityFilterChain, session, entry point |
| Redirect Location | No `localhost:8080`, `http://`, or private host | Check forwarded strategy and proxy headers |
| Post-login cookie | `Secure`, `HttpOnly`, SameSite/path as designed | Check cookie properties, HTTPS, prefix |
| HSTS | Policy-compliant header over HTTPS | Check header owner and `isSecure()` |
| Backend port | Unreachable from the Internet | Check binding/firewall/ingress restrictions |

**Never use `curl -k` to declare HTTPS working.** `-k` skips certificate verification and can hide hostname or trust-chain errors. Use `-k` only in well-understood test contexts, never as security proof.

`curl -I` sends HEAD, which may be handled differently from GET by endpoints or custom filters. If a header is missing in HEAD, test with `curl -i` using GET before drawing conclusions—especially for login redirects and cookies.

### 8.1. Directly testing header spoofing

The security goal of this topology is: **an Internet request cannot choose its own external scheme/host by sending spoofed headers**.

For example, a client might try:

```bash
curl -i https://app.example.com/private \
  -H 'X-Forwarded-Host: attacker.example' \
  -H 'X-Forwarded-Proto: http' \
  -H 'Forwarded: host=attacker.example;proto=http'
```

When edge Nginx normalizes properly and the app accepts requests only via Nginx, the login redirect/response **must not use `attacker.example`**, nor revert to `http`. Note that this command tests only one header subset; security acceptance tests must verify every forwarded header your infrastructure accepts, including `X-Forwarded-Prefix` if applicable.

**This test does not replace network ACLs.** Even if the proxy cleans headers properly, an attacker can spoof headers whenever backend port 8080 is directly reachable. Verify from outside that the backend cannot be reached outside approved paths.

### 8.2. Inspecting the diagnostics output

Log in as `admin` in a browser at `https://app.example.com/login`, then open `https://app.example.com/admin/diagnostics`. With proper proxy/Boot setup, the JSON looks like:

```json
{
  "scheme": "https",
  "host": "app.example.com",
  "port": 443,
  "secure": true,
  "configuredPublicBaseUrl": "https://app.example.com"
}
```

Key order is not fixed, and ports/hosts depend on the real environment. These values represent **expected output for this guide's topology**, not measured stdout. After verification, remove or disable the diagnostics endpoint in production to avoid exposing unnecessary operational details.

If you see `scheme=http`, `secure=false`, host `127.0.0.1`, or port `8080`, inspect the Boot profile, `server.forward-headers-strategy`, Nginx `proxy_set_header`, server routes, and proxy trust order. Never work around it by hardcoding `request.isSecure()=true` in a controller: the root problem lies in origin metadata and infrastructure trust.

## 9. Integration testing Spring Security with forwarded headers

For Spring Boot 3.x Servlet, `MockMvc` and `spring-security-test` can verify how the app interprets forwarded headers in an **explicitly configured test context**. Add test dependencies to the Initializr project's `build.gradle`:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
tasks.named('test') {
    useJUnitPlatform()
}
```

Create file:

```text
src/test/java/demo/publicurl/PublicUrlApplicationTests.java
```

```java
package demo.publicurl;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
    .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "server.forward-headers-strategy=framework",
    "app.public-base-url=https://app.example.com"
})
@AutoConfigureMockMvc
class PublicUrlApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicIsAccessible() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk());
    }

    @Test
    void privateRequiresAuthentication() throws Exception {
        mvc.perform(get("/private"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void forwardedOriginIsObservedForAdmin() throws Exception {
        mvc.perform(
            get("/admin/diagnostics")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "app.example.com")
                .header("X-Forwarded-Port", "443")
                .with(user("admin").roles("ADMIN"))
        )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.scheme").value("https"))
            .andExpect(jsonPath("$.host").value("app.example.com"))
            .andExpect(jsonPath("$.port").value(443))
            .andExpect(jsonPath("$.secure").value(true))
            .andExpect(jsonPath("$.configuredPublicBaseUrl")
                .value("https://app.example.com"));
    }

    @Test
    void nonAdminCannotSeeDiagnostics() throws Exception {
        mvc.perform(get("/admin/diagnostics")
                .with(user("viewer").roles("USER")))
            .andExpect(status().isForbidden());
    }
}
```

**To create the actual Java file**, write the wrapped imports in the snippet as single-line statements (and omit the wrapped version):

```java
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

The Java parser allows line breaks between tokens, though single-line imports make copy/paste cleaner. Run:

```bash
./gradlew test
```

**Expectation:** the four tests pass with the stated dependencies and auto-configuration when Boot's forwarding filter is registered in MockMvc. This is a code expectation, **not an actual compiled/executed result in this document**. If tests do not observe the forwarded origin, check whether `ForwardedHeaderFilter` is registered and active in the test context/MockMvc.

These tests **do not prove the proxy strips spoofed headers**: they explicitly supply `X-Forwarded-*` to Spring and check how the framework interprets them. To prove **anti-spoofing infrastructure**, run real HTTP tests through Nginx/Ingress and verify external users cannot reach the backend directly.

## 10. OAuth2/OIDC redirect URI behind a proxy

The most common scenario is **OIDC login** or the OAuth2 Authorization Code flow. By default, Spring Security OAuth2 Login uses a redirect URI template of the form:

```text
{baseUrl}/login/oauth2/code/{registrationId}
```

With public app `https://app.example.com` and client registration `corp`, the callback registered at the IdP must be exactly:

```text
https://app.example.com/login/oauth2/code/corp
```

If Spring derives the wrong scheme/host from the backend, it can generate:

```text
http://127.0.0.1:8080/login/oauth2/code/corp
http://app.example.com/login/oauth2/code/corp
https://app.example.com:8080/login/oauth2/code/corp
```

These values do not match the registered redirect URI, causing the IdP to reject the request or send the browser to an unreachable address. **Do not "fix" this by loosening wildcard callbacks**; fix the external origin root cause.

Example client registration configuration in a Spring Boot project with the **OAuth2 Client** dependency and a real OIDC IdP:

```properties
spring.security.oauth2.client.registration.corp.client-id=${OIDC_CLIENT_ID}
spring.security.oauth2.client.registration.corp.client-secret=${OIDC_CLIENT_SECRET}
spring.security.oauth2.client.registration.corp.scope=openid,profile
spring.security.oauth2.client.registration.corp.redirect-uri={baseUrl}/login/oauth2/code/{registrationId}
spring.security.oauth2.client.provider.corp.issuer-uri=${OIDC_ISSUER_URI}
```

In this properties snippet, strings like `${OIDC_CLIENT_ID}` are **environment placeholders** resolved by Spring syntax after copying; never place real secrets into the repository. This is a **conditional illustrative config**—it will not turn the form-login program in section 7 into an OIDC client without adding the OAuth2 Client starter, a valid provider, and `oauth2Login(...)`.

**A conservative option** when the product has a single public origin is a fixed redirect URI `https://app.example.com/login/oauth2/code/corp`, while still ensuring Spring Security matchers/callbacks and proxy paths align; never use an unverified dynamic host from requests.

### 10.1. The OAuth callback is a security endpoint

OIDC needs more than the right hostname: the callback also relies on `state`, authorization code exchange, ID token validation, OIDC nonce (as configured), browser session/cookies, and authorization request lifetime. Thus, when a proxy alters scheme/host/path, callbacks can fail across **multiple layers**. Never disable `state`/nonce or CSRF just because login fails to complete.

If the IdP sets cookies or uses cross-site redirects/form-posts, check `SameSite` on the **application session cookie**. Do not switch all cookies to `SameSite=None` without understanding the flow and CSRF implications. A standard GET callback may behave differently from a form-post callback, so test with a real browser.

### 10.2. SAML and email links share the same issue

SAML 2.0 ACS URLs, metadata entity descriptors, and account-verification/password-reset email links also require accurate public host/scheme/path. Never use internal URLs constructed from an unprotected `request.getServerName()` for outbound messages. In multi-tenant systems, external URLs may vary by tenant, but must be selected only from registered and verified hostnames.

## 11. Apps with a /portal path prefix: subtle bugs

A proxy may publish:

```text
Public:  https://app.example.com/portal/private
Backend: http://127.0.0.1:8080/private
```

Here `/portal` is an **external prefix** stripped by the proxy before reaching the backend. Without knowing the prefix, Spring may redirect to `https://app.example.com/login` instead of `https://app.example.com/portal/login`.

`X-Forwarded-Prefix: /portal` helps Spring Framework reconstruct the request's context path in supported topologies. However, **prefix forwarding is not a universal path-rewriting trick that works identically across every proxy, Servlet container, OAuth callback, and security matcher**.

Choose one consistent strategy:

1. Keep the app's context path equal to the public prefix when appropriate, and have the proxy preserve the prefix; or
2. Have the proxy strip the prefix before forwarding while setting a controlled `X-Forwarded-Prefix`; or
3. Generate routes/callbacks/links from a fixed external base URL configuration tested end-to-end.

Do not blindly combine `server.servlet.context-path=/portal`, prefix-stripping rewrites, and `X-Forwarded-Prefix=/portal` expecting every URL to work; that easily produces doubled `/portal/portal` redirects or dropped prefixes. In all cases, test `/login`, static resources, logout, OAuth2 callbacks, and post-login return URLs.

An important test:

```text
GET https://app.example.com/portal/private
-> 302 Location: https://app.example.com/portal/login
-> login page / form action / CSS / callback all preserve /portal
```

This is an **architectural expectation**, not guaranteed output simply because a forwarded-header property was enabled.

## 12. Multiple proxies/CDN/Kubernetes Ingress: shifting trust boundaries

Multi-tier diagram:

```text
Client
  -> CDN / WAF
  -> cloud load balancer
  -> Kubernetes Ingress / reverse proxy
  -> Spring Boot pod
```

Each hop can alter Host, scheme, port, path, and source IP. Explicitly define:

- **Which hop is the first trust boundary?** It must strip spoofed headers sent from the Internet and establish trustworthy origin data.
- **Which hop normalizes forwarded headers before the backend?** Pass only verified sources of truth; do not append arbitrary client-supplied strings.
- **Where does the backend accept connections from?** Use private networks, security groups, `NetworkPolicy`, or service mesh identity/mTLS per model.
- **Where is TLS terminated?** If TLS terminates at the CDN and again at ingress, never pass `X-Forwarded-Proto=http` merely because the final hop speaks HTTP to the pod.
- **Who emits HSTS?** Edge or app, maintaining one consistent policy.
- **Which hosts are accepted?** Avoid using arbitrary hosts as the origin for security links or tenant identity.
- **How is source IP recovered?** `X-Forwarded-For` can hold multiple hops and must be parsed according to trusted proxies rather than trusting the client-supplied prefix.

For Spring Boot WebFlux, `server.forward-headers-strategy=framework` is handled by reactive Spring Framework support such as `ForwardedHeaderTransformer`. **Never add Servlet `ForwardedHeaderFilter` to a WebFlux app**; inspect the `WebFilter` pipeline and reactive request accordingly.

### Multiple domains and tenants

If each tenant has its own hostname, e.g., `https://tenant-a.example.com` and `https://tenant-b.example.com`, do not treat the raw `Host` header alone as proof of tenant identity. Maintain a verified hostname-to-tenant registry, matching certificates, and tenant resolution after ingress validates/normalizes the host. Authorization must still verify the user belongs to that tenant; a request with a valid host does not grant the caller access to tenant data.

## 13. Common issues and how to debug them

### 13.1. Redirect loop between HTTP and HTTPS

Symptom: the browser bounces endlessly between an HTTP and HTTPS URL or shows `ERR_TOO_MANY_REDIRECTS`. The proxy may redirect HTTP to HTTPS while the app still sees HTTP and redirects again, or forwarded-header precedence may be wrong. Check `X-Forwarded-Proto` from the proxy, the Boot strategy, and custom HTTPS redirect logic. Never disable HTTPS enforcement to hide a loop; fix the scheme mismatch.

### 13.2. Location contains localhost or :8080

Check whether the application receives forwarded headers, the effective `server.forward-headers-strategy`, whether the proxy sends a fixed host, and whether app code constructs URLs with `localhost`. For emails from background jobs, use a trusted `app.public-base-url` instead of relying on a non-existent request context.

### 13.3. OIDC reports redirect_uri_mismatch

Compare **character by character** the scheme, host, port, prefix, callback path, and registration ID against the URI registered at the IdP. Never open wildcard callbacks; fix routing and the forwarded strategy. Also check cookies/sessions if the callback fails on `state`.

### 13.4. Cookies are not stored or login loses session

Inspect `Set-Cookie` in DevTools: `Secure`, `HttpOnly`, `SameSite`, `Domain`, `Path`. Compare the external hostname with the internal host, HTTP/HTTPS, and path prefix. Never log session IDs for debugging; use non-sensitive request/correlation IDs.

### 13.5. HSTS is missing

Verify the external request is truly HTTPS and check which layer is supposed to emit HSTS (edge or Spring). If Spring Security is responsible, the request must be seen as secure. Never enable HSTS `preload` or `includeSubDomains` until every subdomain is confirmed HTTPS-ready; that policy can cause long-lasting outages.

### 13.6. Client spoofing X-Forwarded-Host causes redirect to attacker.example

This is a **trust-boundary vulnerability**, not a mere formatting bug. Check direct-to-backend access, ingress normalization, standard `Forwarded` and `X-Forwarded-*` headers, and host allowlists. Fix it at the proxy boundary and in security-link generation, not by filtering `attacker.example` in one controller.

### 13.7. HTTPS works but API still returns 403/401

HTTPS does not grant authorization. Check authentication/session/cookies, CSRF, token audience/scopes, `AuthorizationManager`, and role/owner/tenant rules as usual. If a proxy strips the `Authorization` header or cookies, 401 can occur; if a POST lacks a CSRF token, 403 can occur. Distinguish transport, authentication, and authorization failures.

### 13.8. Proxy redirects differ from Spring redirects

The proxy may issue 301/308 while Spring Security issues 302 to login. `curl -i` without following redirects shows each hop clearly. Across multiple redirects, use proxy and app logs with safe request IDs to tell which layer emitted `Location`.

### 13.9. Browser reports Mixed Content

An HTTPS page references `http://app.example.com/assets/...` or calls an HTTP API. Check base URLs in templates, frontend build/runtime config, static asset URLs, and proxy settings. Never use `http://127.0.0.1:8080` as an API URL for browsers; on a user's machine, that address points to **their own loopback**, not the server.

### 13.10. Spring Security HSTS conflicts with edge HSTS

Two layers emitting different `Strict-Transport-Security` values make auditing difficult. Decide which layer owns it, inspect actual response headers from the public Internet, and verify policy across all domains. Do not assume the app's header reaches clients intact if the edge adds, modifies, or removes it.

## 14. Deployment acceptance checklist

- [ ] DNS and certificates are valid for the exact public hostname.
- [ ] Public HTTP redirects cleanly to canonical HTTPS; never reflects arbitrary hosts.
- [ ] Public scheme/host/port/path prefix and canonical config location are clearly defined.
- [ ] Trusted proxy strips/overwrites Internet-supplied `Forwarded` and `X-Forwarded-*` headers.
- [ ] Backend is unreachable directly from the Internet; internal hops are protected.
- [ ] Spring Boot uses **one** appropriate forwarded-header strategy and it has been tested.
- [ ] Request-built URLs, 302 `Location` headers, and email links never leak internal hosts/ports.
- [ ] Session cookies have environment-appropriate `Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path`.
- [ ] HSTS has a clear policy and actually appears properly at the public HTTPS edge.
- [ ] CSRF continues protecting state-changing browser actions; never disabled just to silence 403s.
- [ ] OIDC/OAuth2 redirect URI matches exactly; callbacks and state/sessions work.
- [ ] Path prefix `/portal` is neither lost nor duplicated across login/logout/static assets.
- [ ] Multi-tenant host mapping and authorization are checked independently without trusting raw `Host`.
- [ ] Spoofed `X-Forwarded-Host/Proto/Forwarded` requests tested against the public edge.
- [ ] `curl -k` is never used as proof of a valid certificate.
- [ ] 401/403/302/200, status, `Location`, and `Set-Cookie` verified from outside the proxy, not just in controller tests.
- [ ] DEBUG/TRACE reduced after investigation; avoid logging credentials, tokens, cookies, and personal data.

**Key takeaway:** in a deployment behind a reverse proxy, Spring Security can enforce identities and roles accurately yet still emit **wrong redirects, cookies, callbacks, or links** if the application does not know its external origin. Manage the public URL as part of security configuration, trust forwarded headers only from controlled proxies, and test the **full path: browser → proxy → Spring Boot → browser**.

### Official references

- [Spring Boot 3.5 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Framework — Forwarded Headers and ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [Spring Security — Security HTTP Response Headers and HSTS](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
- [Spring Security — OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security — Advanced OAuth2 Login / Redirection Endpoint](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
