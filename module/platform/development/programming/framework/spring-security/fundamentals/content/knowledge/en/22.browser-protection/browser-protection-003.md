# HSTS and requirements for proper HTTPS deployment

> **Topic:** Spring Security – fundamentals → **Browser Protection**. This lesson targets Java 17+, Spring Boot 3.x, and Spring Security 6.x, focusing on **HTTP Strict Transport Security (HSTS)**, how browsers learn and enforce HTTPS-only, how it differs from HTTP → HTTPS redirects, Spring MVC/WebFlux configuration, TLS deployment behind reverse proxies, `includeSubDomains`/`preload` risks, rollout procedures, and practical tests.

## 1. What problem does HSTS protect against?

**HSTS** is a mechanism for a host to tell browsers: *"For a given period of time, every connection to this host must use HTTPS; if a user opens an HTTP URL, upgrade it to HTTPS before sending the request over the network."*

The server sends an HTTP response header over a **trusted HTTPS connection**:

```http
HTTP/1.1 200 OK
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Type: text/html; charset=utf-8
```

After receiving and accepting the header, the browser remembers the policy for the host for **31536000 seconds** (365 days). When visiting `http://app.example.com` while covered by the policy, the browser automatically rewrites it to `https://app.example.com`. If `includeSubDomains` is set on a parent domain, the policy also applies to subdomains of that parent.

**Three key points to remember:**

1. HSTS is a **browser behavior policy**, not a server TLS configuration. HSTS does not issue certificates, encrypt requests, or open an HTTPS listener.
2. An HSTS header is trusted by browsers **only when received over HTTPS with a valid certificate**; sending the header over HTTP does not establish an accepted policy.
3. HSTS primarily protects **subsequent visits** after the browser has learned the policy. To enforce the policy on the very first visit before the browser has contacted the host, a mechanism like **HSTS preload** is required, though preload carries operational risks and must not be enabled casually.

Enabling HSTS does not mean an application has deployed HTTPS properly. The policy can turn a certificate error, DNS mistake, or HTTP-only subdomain into a state where browsers **cannot access the site at all** until HTTPS is fixed.

## 2. Why is an HTTP → HTTPS redirect alone insufficient?

Suppose a user types `bank.example`, clicks an `http://bank.example` link, or a browser/client tries HTTP first. If the server responds:

```http
HTTP/1.1 308 Permanent Redirect
Location: https://bank.example/
```

the redirect is helpful, yet the **initial HTTP request and response** can be read or tampered with by an attacker on the network path. An attacker on untrusted Wi-Fi could intercept the redirect, keep the user on HTTP, or steer them to a lookalike domain.

For a host already protected by HSTS, the browser **upgrades the URL before issuing the HTTP request**, reducing protocol downgrade / SSL stripping risk.

```text
HSTS NOT YET KNOWN:

Browser -> http://bank.example
          |   Initial request may travel over HTTP
          v
HTTP Server -> 308 Location: https://bank.example/
          |
          v
Browser -> HTTPS handshake + certificate check
          |
          v
HTTPS Server -> Strict-Transport-Security
          |
          v
Browser remembers policy for future requests

HSTS ALREADY KNOWN:

User opens http://bank.example
          |
          v
Browser auto-upgrades to https://bank.example
          |
          v
HTTPS handshake + certificate check
          |
          v
HTTPS request to host (no initial HTTP request sent)
```

**Do not confuse this:** HSTS does not retroactively protect the first request that already went over HTTP. Preload or browser HTTPS-First features can help on first visits, but those mechanisms have prerequisites and do not replace a properly configured HTTPS server.

## 3. `Strict-Transport-Security` syntax and interpretation

Several header patterns—use **one appropriate option**, not all at once:

```http
Strict-Transport-Security: max-age=300
```

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

```http
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
```

| Directive | Meaning | Notes |
|---|---|---|
| `max-age=300` | Browser remembers HTTPS-only for 300 **seconds** | Useful for pilot rollouts |
| `max-age=31536000` | One-year lifetime | Very hard to revert to HTTP while browsers still remember |
| `includeSubDomains` | Applies policy to all subdomains and nested subdomains | Can break services on subdomains lacking HTTPS |
| `preload` | Signals intent to join the HSTS preload list | Does not automatically add the domain to browser preload lists |
| `max-age=0` | Clears the host's learned policy when received over valid HTTPS | Has no effect if sent over HTTP; does not immediately clear parent/preload policies |

Browsers refresh the expiration timestamp whenever a new valid header is received. A host continuously returning `max-age=31536000` keeps extending expiration; the browser will not simply forget the policy one year after deployment if users visit over HTTPS daily.

**HSTS applies per hostname**, not per path like `/login`, `/admin`, or `/api`. Placing the header in one controller and assuming HSTS protects only that controller is the wrong mental model. `includeSubDomains` on `example.com` covers `app.example.com`, `api.example.com`, `legacy.example.com`, `printer.internal.example.com`, and nested subdomains, as long as the host falls under that domain suffix.

### 3.1. Parent hosts, child hosts, and HSTS scope

| Host with learned HSTS | Header | Request to | Covered by parent policy? |
|---|---|---|---|
| `example.com` | `max-age=300` | `example.com` | Yes |
| `example.com` | `max-age=300` | `app.example.com` | No (unless app has its own policy) |
| `example.com` | `max-age=300; includeSubDomains` | `app.example.com` | Yes |
| `example.com` | `max-age=300; includeSubDomains` | `a.b.example.com` | Yes |
| `app.example.com` | `max-age=300; includeSubDomains` | `example.com` | No |
| `app.example.com` | `max-age=300; includeSubDomains` | `api.example.com` | No |
| `example.com` | `max-age=300; includeSubDomains` | `example.com.attacker.net` | No |

Only set `includeSubDomains=true` on a **parent domain where your organization controls all associated services**. It does not care whether a subdomain is used for UI, APIs, email gateways, or internal devices; browsers will attempt HTTPS for every covered host.

### 3.2. Ports and URLs

HSTS is not scoped by path or by an arbitrary application port. When upgrading an HTTP URL using default port 80, HTTPS typically uses default port 443. For URLs with a non-default port, upgrading may retain the specified port and switch to HTTPS; if that port only speaks HTTP, clients will fail. Test web services/consoles running on non-standard ports.

### 3.3. IP literals and local development

HSTS is designed for DNS hostnames and browsers, so tests against `http://127.0.0.1` or IP literals should not be used to draw conclusions about production. In test environments, use proper domain names and trusted CA certificates when evaluating real HSTS. Some browsers treat `localhost` specially, but never rely on that exception when designing public HTTPS.

## 4. When does a browser accept HSTS?

A browser should only learn the policy when:

1. The response arrives over `https://`.
2. The TLS handshake succeeds with a trusted certificate chain, valid hostname/SAN, and non-expired certificate.
3. The `Strict-Transport-Security` header is valid and includes `max-age`.
4. The browser supports HSTS and records the policy for the hostname.
5. Future requests to covered hosts are upgraded before sending HTTP.

Headers on HTTP responses are ignored by browsers:

```http
HTTP/1.1 308 Permanent Redirect
Location: https://app.example.com/
Strict-Transport-Security: max-age=31536000
```

In this example, **the redirect is still useful**, but the HSTS header placed on **HTTP** does not cause the browser to learn HSTS. To establish the policy, the `https://app.example.com/` response must return the header after TLS succeeds.

### 4.1. What if the certificate has errors?

If HSTS is active and the HTTPS certificate expires, has the wrong SAN, or is untrusted, browsers typically refuse to let users click through the TLS warning as they normally might. This is an essential part of anti-downgrade protection, yet it can also cause a **severe outage** if certificate renewal is missed.

HSTS **does not fix** a certificate chain, add a TLS listener, or bypass certificate errors. Therefore, maintain certificate issuance, monitoring, renewal, key rotation, and HTTPS recovery capabilities **before setting a long max-age**.

### 4.2. HSTS does not prevent all types of attacks

HSTS does not replace:

- HTTPS/TLS validation and browser-managed certificate trust.
- `Secure`, `HttpOnly`, and `SameSite` cookies and session management.
- XSS prevention, CSP, output encoding, and third-party script controls.
- CSRF protection for browser auto-attached credentials.
- Authentication, authorization, roles/scopes, and tenant/ownership checks.
- Phishing protection against **different lookalike domains**, even when those domains have valid HTTPS certificates.
- Token/secret hygiene: keeping bearer tokens out of logs, URLs, and crash reports.

## 5. Deploy real HTTPS before enabling HSTS

Two common deployment topologies exist:

**Model A – TLS termination at a reverse proxy/CDN/ingress:**

```text
Browser --HTTPS:443--> Nginx / Ingress / Load Balancer
                             |
                             | Internal HTTP or mTLS
                             v
                         Spring Boot :8080
```

**Model B – Spring Boot terminates HTTPS directly:**

```text
Browser --HTTPS:443/8443--> Embedded Tomcat/Jetty/Netty
                             |
                             v
                         Spring application
```

Both models can use HSTS. What matters is that **public-facing HTTPS works properly**, proxy headers/trust are right, and HSTS is emitted from a single place with clear policy ownership.

### 5.1. Minimum requirements for TLS/HTTPS

| Component | Check | If misconfigured |
|---|---|---|
| DNS/hostname | Public URL resolves to the right edge/server | Clients hit the wrong host or get misdirected |
| Certificate SAN | Certificate includes the exact hostname | Browser warns on domain mismatch |
| Trust chain | CA/intermediate chain is valid | Browser rejects certificate |
| Validity | Certificate is unexpired with automated renewal | HSTS hosts may become inaccessible |
| TLS versions | TLS 1.2/1.3 per current policy, no weak protocols | Downgrades, incompatibility, higher risk |
| Private key | Stored in a restricted secret store/volume | Key leakage, server impersonation |
| SNI | Edge serves the right cert per hostname | Wrong cert with multiple virtual hosts |
| Redirect | HTTP → HTTPS to proper host/path, no loops | Browser cannot reach HTTPS |
| Mixed content | JS/API/assets/WebSockets use HTTPS/WSS | Browser blocks requests or degrades security |
| Proxy headers | Public scheme/host/port accurately conveyed | App misreads `isSecure`, breaks redirects/cookies/HSTS |
| Monitoring | Alerts for expiry/handshakes/errors/redirect loops | Prolonged outage while HSTS remains cached |

TLS must serve every important route, including login, APIs, OAuth callbacks, static assets, and HTTPS redirects. HSTS must never be used to mask URLs that are still HTTP-only.

### 5.2. HTTP redirect: choose 301 or 308?

An HTTP listener on port 80 should redirect to HTTPS instead of processing sensitive data. 301 or 308 redirects are commonly used; `307`/`308` preserve the HTTP method and body under modern semantics, whereas 301/302 historically allowed converting POST to GET.

Never let users submit passwords or `Authorization` headers over HTTP before redirecting. For browsers with HSTS, HTTP requests upgrade before hitting the wire; for clients without HSTS, configure clients to use HTTPS URLs from the start rather than relying on redirects to protect credentials in transit.

## 6. Example of Nginx in front of a Spring Boot application

Illustrative configuration, not a complete production Nginx setup:

```nginx
server {
    listen 80;
    server_name app.example.com;

    return 308 https://app.example.com$request_uri;
}

server {
    listen 443 ssl;
    server_name app.example.com;

    ssl_certificate     /etc/tls/fullchain.pem;
    ssl_certificate_key /etc/tls/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;

        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;
        proxy_set_header X-Forwarded-Port  $server_port;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    }
}
```

Real operations also require: TLS ciphers/versions, HTTP/2/HTTP/3 as needed, internal mTLS where appropriate, rate limits, timeouts, error pages, log redaction, certificate automation, and access controls. Private key files **must never be committed to Git**.

HSTS should have **one owner**:

- **Spring Security** emits HSTS on HTTPS responses and Nginx forwards it; or
- **Nginx/CDN/ingress** emits HSTS on HTTPS responses and Spring is configured not to emit a conflicting policy.

If the edge owns HSTS, it can be placed inside the HTTPS `server` block:

```nginx
# Place only inside the HTTPS server block after verifying TLS.
add_header Strict-Transport-Security "max-age=300" always;
```

`always` ensures the header appears across many status codes including errors, though you must check actual inheritance/location/proxy behavior. **Do not emit HSTS on HTTP port 80 expecting browsers to accept it.** Never let Nginx and Spring emit different `max-age` values, which makes behavior unpredictable and rollback hard.

## 7. Reverse proxies and `X-Forwarded-Proto`: a common pitfall

Browsers speak HTTPS to the proxy, while the proxy may speak HTTP to the Spring Boot backend. In Servlet, if the framework only inspects the backend socket, `request.isSecure()` can return `false`. Because Spring Security's **HstsHeaderWriter** defaults to checking `ServletRequest.isSecure()` to decide whether to write the header, responses that were HTTPS from the browser's perspective can **lack HSTS**.

Beyond HSTS, an incorrect scheme can also cause:

- Generated links and `Location` redirects to use `http://`.
- Form login / OIDC callbacks to build the wrong redirect URI, causing HTTP/HTTPS loops.
- `Secure` cookie logic or other scheme-dependent features to misbehave.
- The app to misidentify its public hostname/port.

Spring Boot has forwarded header settings:

```yaml
# application.yml when behind a TRUSTED reverse proxy
server:
  forward-headers-strategy: framework
```

Another option is `server.forward-headers-strategy: native` so the servlet container handles supported forwarded headers. Choose based on your topology, web server, cloud environment, and current Spring Boot docs.

**Critical security rule:** Never trust `Forwarded`/`X-Forwarded-*` headers sent by internet clients. Nginx/ingress must **strip or overwrite** these headers at the trust boundary, restrict direct network access to the backend, and accept them only from trusted proxies. If an attacker can spoof `X-Forwarded-Proto: https` or `X-Forwarded-Host`, link generation, redirects, and security behaviors can be manipulated.

When using Tomcat with SSL termination at a proxy, Spring Boot documentation also notes that `server.tomcat.redirect-context-root=false` may be needed so the forwarded protocol is applied before redirecting the context root.

**Do not "fix" missing HSTS by forcing the header onto every plain HTTP request Spring sees.** Instead, verify the public HTTPS path and fix scheme handling or edge ownership properly so HTTP and HTTPS are never conflated in the security layer.

## 8. HSTS in Spring Security Servlet: default behavior

Per Spring Security 6.x docs, the default security response headers include:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

Added **only when the request is considered secure/HTTPS**. The default Servlet writer sets:

- `max-age`: one year.
- `includeSubDomains`: `true`.
- `preload`: `false`.

This is a safe default in many environments **with complete HTTPS deployments**, but may be unsuitable if the app sits on a parent domain with legacy HTTP subdomains. When rolling out HSTS initially, choose a deliberate policy rather than blindly accepting the long-lived default.

### 8.1. Servlet configuration for a pilot phase

Place `HstsSecurityConfig.java` in a Spring Boot MVC application with `spring-boot-starter-web` and `spring-boot-starter-security`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HstsSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .headers(headers -> headers
                .httpStrictTransportSecurity(hsts -> hsts
                    .maxAgeInSeconds(300)
                    .includeSubDomains(false)
                    .preload(false)
                )
            );

        return http.build();
    }
}
```

**Explanation:**

- `.httpStrictTransportSecurity(...)` is the HSTS DSL on Servlet `HttpSecurity`.
- `maxAgeInSeconds(300)` = 5 minutes, suited for a small pilot. Do not treat this as a permanent production policy.
- `includeSubDomains(false)` covers only the host itself, avoiding unintended impact on untested subdomains.
- `preload(false)` does not signal inclusion in preload lists.
- `httpBasic` is only an illustrative authentication mechanism and is **not required** for HSTS to work. With browsers, Basic auth can still be exposed to CSRF and requires HTTPS.
- HSTS is independent of `authenticated()`, `hasRole`, and service-level authorization rules; having HSTS does not mean data access is authorized.

Once ready to protect the parent and all subdomains for a year, the policy can be updated to:

```java
// Snippet inside HttpSecurity config:
.headers(headers -> headers
    .httpStrictTransportSecurity(hsts -> hsts
        .maxAgeInSeconds(31536000)
        .includeSubDomains(true)
        .preload(false)
    )
)
```

**Do not add `preload(true)` out of habit.** Enabling preload requires approval from the DNS/TLS owners because its effects are domain-wide and rollback can take a long time.

### 8.2. Multiple security filter chains

If an application has multiple `SecurityFilterChain` beans using `securityMatcher` by path, ensure responses requiring HSTS actually traverse a chain applying the header. HSTS is a **hostname-wide** policy and should not accidentally appear on `/login` while missing `/error`, static paths, or a separate chain.

When Nginx/CDN owns the header, verify HTTPS errors/redirects also receive a consistent policy without duplicate layers writing conflicting values. When Spring owns the header, verify the filter chain and scheme at runtime.

## 9. Spring Boot MVC demo: complete code and tests

The following example uses **Java 17+, Maven, and Spring Boot 3.5.7**. It verifies `HstsHeaderWriter` at the Spring Security layer using `MockMvc`, which **does not replace TLS testing**. To run, create files at these paths:

```text
hsts-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/hsts/
    │   ├── HstsDemoApplication.java
    │   ├── HstsSecurityConfig.java
    │   └── PingController.java
    └── test/java/com/example/hsts/
        └── HstsSecurityTests.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>hsts-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
```

`HstsDemoApplication.java`:

```java
package com.example.hsts;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HstsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(HstsDemoApplication.class, args);
    }
}
```

`HstsSecurityConfig.java`:

```java
package com.example.hsts;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HstsSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .headers(headers -> headers
                .httpStrictTransportSecurity(hsts -> hsts
                    .maxAgeInSeconds(300)
                    .includeSubDomains(false)
                    .preload(false)
                )
            );
        return http.build();
    }
}
```

`PingController.java`:

```java
package com.example.hsts;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }
}
```

`HstsSecurityTests.java`:

```java
package com.example.hsts;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HstsSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void secureRequestGetsHstsHeader() throws Exception {
        mvc.perform(get("/public/ping").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string("Strict-Transport-Security",
                containsString("max-age=300")));
    }

    @Test
    void insecureRequestDoesNotTeachHsts() throws Exception {
        mvc.perform(get("/public/ping").secure(false))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                "Strict-Transport-Security"));
    }
}
```

Run tests:

```bash
mvn test
```

Run the application:

```bash
mvn spring-boot:run
```

**Limitations of the demo:** Local Boot defaults to HTTP on `localhost:8080` if TLS is not configured; thus seeing no HSTS in `curl -i http://localhost:8080/public/ping` is normal. `MockMvc`'s `.secure(true)` only simulates the Servlet request's secure attribute—it **does not test certificates, redirects, cipher suites, proxies, or browser enforcement**.

What the demo omits: issuing certificates, configuring proxies, creating production users, implementing a full login workflow, or designing fine-grained authorization. Basic auth here illustrates a protected route; with browsers, Basic auth may need CSRF defenses given automatic credential sending.

## 10. Spring Boot serving HTTPS directly with SSL bundles

If the Spring Boot embedded web server acts directly as the TLS endpoint, Spring Boot 3.x supports SSL bundles with PEM/JKS/PKCS12. Example `application.yml`:

```yaml
spring:
  ssl:
    bundle:
      pem:
        webserver:
          keystore:
            certificate: "file:/etc/tls/fullchain.pem"
            private-key: "file:/etc/tls/privkey.pem"

server:
  port: 8443
  ssl:
    bundle: "webserver"
```

- `spring.ssl.bundle.pem.webserver` declares the PEM certificate and private key pair.
- `server.ssl.bundle: "webserver"` applies the SSL bundle to the embedded web server.
- `server.port: 8443` picks the HTTPS port in this example. In production, ingress/proxies may expose 443 and forward/route to the appropriate port.
- Certificate/key files must exist, have valid SANs and trust chains, and be mounted from a secure secret store; never hardcode private keys in YAML or commit them to a repository.
- Spring Boot does not automatically obtain or renew Let's Encrypt certificates via SSL bundle config alone. Separate ACME/cert-manager/ingress automation and lifecycle monitoring are required.
- SSL bundle configuration **does not automatically open an HTTP listener for redirects**. If both HTTP port 80 and HTTPS are needed, use a reverse proxy or add a separate connector appropriate for the web server.

Do not mix `server.ssl.bundle` with incompatible discrete SSL properties such as keystore options under `server.ssl.*`; per Spring Boot documentation, certain properties must be configured in the SSL bundle rather than combined.

### 10.1. Mixed content and absolute URLs

If the main page uses HTTPS while loading scripts, stylesheets, or APIs over `http://`, the browser may block mixed content or create security issues. Do not rely on HSTS for arbitrary third-party domains. Use `https://` or `wss://` for relevant resources and verify:

- API base URLs and WebSocket URLs.
- OAuth2/OIDC `redirect_uri`, logout URLs, and callback URLs.
- CSS/fonts/images/scripts loaded from external hosts.
- Absolute redirects/`Location` headers generated by the backend behind a proxy.
- Managed CDN endpoints and static asset domains.
- CSP `upgrade-insecure-requests` can assist in upgrading certain URLs, but will not fix certificates or whether the target actually supports HTTPS.

## 11. HSTS in Spring Security WebFlux

For reactive WebFlux, use `ServerHttpSecurity` and `SecurityWebFilterChain`; the HSTS configuration API differs from Servlet in method names and parameter types:

```java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveHstsSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .headers(headers -> headers
                .hsts(hsts -> hsts
                    .maxAge(Duration.ofMinutes(5))
                    .includeSubdomains(false)
                    .preload(false)
                )
            )
            .build();
    }
}
```

This is Spring configuration for a **separate WebFlux application** using `spring-boot-starter-webflux` and `spring-boot-starter-security`. Do not confuse `HttpSecurity`/`SecurityFilterChain` or `includeSubDomains` (Servlet spelling) with `includeSubdomains` (Reactive spelling). Both remain subject to the rule that HSTS only takes effect over **trusted HTTPS responses**.

To test WebFlux, use `WebTestClient` and an appropriate reactive test environment; to verify real HTTPS, test against an actual TLS/proxy endpoint rather than simulating only the security filter. Never force the reactive pipeline with manual `block()`/`subscribe()` calls just to handle headers.

## 12. HSTS preload: benefits and consequences

The **HSTS preload list** is a built-in list of domains hardcoded into browsers as HTTPS-only. Once a domain has been shipped to browsers, the browser knows the policy **before the very first visit**.

Example header used when preparing for preload:

```http
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
```

**Adding the `preload` directive does not automatically preload the domain in browsers.** The organization must satisfy technical requirements and submit via `https://hstspreload.org/`; once accepted, the domain must roll out into relevant browser releases. This takes time and has consequences that are hard to undo.

Key requirements per `hstspreload.org`:

1. A valid TLS certificate.
2. If an HTTP listener exists on port 80, redirect HTTP → HTTPS **on the same hostname**.
3. **All subdomains and nested subdomains**, including internal hosts, must support valid HTTPS.
4. The HTTPS base domain sends a header with `max-age` of at least **31536000 seconds**.
5. The header includes `includeSubDomains` and `preload`.
6. If the HTTPS base domain redirects further, that HTTPS redirect response must also include HSTS.
7. Commitment to continue meeting the requirements going forward.

A subdomain like `legacy.example.com` or `printer.corp.example.com` lacking HTTPS can become unreachable via browsers if parent `example.com` enters HSTS preload with `includeSubDomains`. Audit non-public subdomains too; do not scan only the main homepage.

**Preload service guidance emphasizes that HSTS is recommended, whereas preloading is not recommended as the default choice for all websites.** HSTS preload is appropriate when an organization truly controls the entire domain, sees clear security value, and is ready for sustained HTTPS operations.

### 12.1. Preload vs the `preload` header directive

| Scenario | Guaranteed browser upgrade on first visit to `http://example.com`? |
|---|---|
| Server only sends `max-age=31536000` on HTTPS, browser hasn't learned yet | Not guaranteed since no policy is stored yet |
| Server includes `preload` directive, not yet in browser list | Not guaranteed |
| Domain is already in the current browser's preload list | Browser can enforce HTTPS from the list before the first request |
| Browser uses its own HTTPS-First mode, domain has no HSTS | May try HTTPS first, though this is browser-specific behavior |

Do not infer actual preload status from the header alone. You can check status on `hstspreload.org` and in appropriate browser/test environments, but never submit an active production domain just to "try it out".

## 13. Cautious phased HSTS rollout

HSTS has a persistent lifetime and prevents browsers from falling back to HTTP, so it should be **rolled out incrementally** rather than turning on one-year HSTS or preload on an unprepared domain.

### 13.1. Phase 0 – Prepare infrastructure

- Identify the hostname sending the header and every subdomain/nested domain impacted if using `includeSubDomains`.
- Check TLS certificates, chains, SANs, trust, expiry, SNI, ciphers/versions, and renewal.
- Check HTTP port 80 redirects, HTTPS port 443, and any other active ports.
- Review login, OAuth callbacks, cookies, CSP, API assets, and mixed content.
- Assign HSTS header ownership: Spring app or CDN/ingress; prevent conflicting dual emission.
- Prepare monitoring and runbooks: fixing certificates, restoring DNS, rolling back headers, avoiding prolonged downtime.

### 13.2. Phase 1 – `max-age=300`

```http
Strict-Transport-Security: max-age=300
```

Test with pilot users and major browsers: login, redirects, static assets, APIs, OAuth callbacks, HTTPS certificate renewal. **Do not enable `includeSubDomains` yet** if any services remain unchecked.

### 13.3. Phase 2 – 1 week, then 1 month

```http
Strict-Transport-Security: max-age=604800
```

Then:

```http
Strict-Transport-Security: max-age=2592000
```

Increase only after observing long enough to catch related issues and preparing mitigation plans. Keep in mind that `max-age` refreshes whenever browsers receive a new header; lowering `max-age` on the server does not mean browsers immediately pick up the change.

### 13.4. Phase 3 – Long-term HSTS

```http
Strict-Transport-Security: max-age=31536000
```

Only once all subdomains are standardized on HTTPS should you consider the parent policy:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

If considering preload, review requirements and operational costs; never add `preload` to a production policy merely because a code sample had it.

## 14. Rolling back HSTS and limitations of `max-age=0`

To clear a learned HSTS policy for a host, the server can send over **valid HTTPS**:

```http
Strict-Transport-Security: max-age=0
```

However:

- Browsers **do not** learn a removal policy from an HTTP response.
- If the HTTPS certificate is currently broken, browsers may not be able to receive the rollback header; **fix TLS first**.
- If parent `example.com` still sets `includeSubDomains`, subdomain `app.example.com` sending `max-age=0` **cannot opt out** of the parent policy.
- If the domain is already preloaded, removal follows its own process and can take **many months** across browser updates.
- If a CDN/ingress keeps emitting a long `max-age` while the app sends `max-age=0`, policies conflict and rollback may fail.
- A browser that never revisits the HTTPS host to receive the new header retains the old policy until expiration.

HSTS is a "sticky" commitment: **never rely on fast rollback** to compensate for skipping subdomain audits or certificate lifecycle checks.

## 15. Standalone Java 17: modeling HSTS hostnames and expiration

To understand scope without Spring/Maven, the following program checks exact host vs subdomain matching and expiration. This is **only a mental model**, not a browser: it omits TLS, certificates, preload, redirects, URI ports, cookies, and policy storage.

`HstsPolicyDemo.java`:

```java
import java.util.Locale;

public class HstsPolicyDemo {

    record Policy(String host, long expiresAtSeconds,
                  boolean includeSubdomains) {}

    static boolean applies(Policy policy, String requestHost, long now) {
        if (now >= policy.expiresAtSeconds()) {
            return false;
        }

        String root = policy.host().toLowerCase(Locale.ROOT);
        String requested = requestHost.toLowerCase(Locale.ROOT);

        return requested.equals(root)
            || (policy.includeSubdomains()
                && requested.endsWith("." + root));
    }

    static void check(String label, Policy policy, String host, long now) {
        System.out.println(label + ": " + applies(policy, host, now));
    }

    public static void main(String[] args) {
        long createdAt = 1_000_000L;
        long lifetime = 300L;

        Policy withSubdomains =
            new Policy("example.com", createdAt + lifetime, true);

        check("Exact host", withSubdomains,
            "example.com", createdAt + 120);
        check("Subdomain", withSubdomains,
            "app.example.com", createdAt + 120);
        check("Nested subdomain", withSubdomains,
            "api.dev.example.com", createdAt + 120);
        check("Lookalike", withSubdomains,
            "example.com.attacker.net", createdAt + 120);
        check("Expired", withSubdomains,
            "example.com", createdAt + 300);

        Policy hostOnly =
            new Policy("example.com", createdAt + lifetime, false);

        check("No includeSubDomains", hostOnly,
            "app.example.com", createdAt + 120);
    }
}
```

Compile and run with JDK 17+:

```bash
javac HstsPolicyDemo.java
java HstsPolicyDemo
```

Exact program stdout:

```text
Exact host: true
Subdomain: true
Nested subdomain: true
Lookalike: false
Expired: false
No includeSubDomains: false
```

Explanation: an unexpired policy covers the primary host, plus subdomains if the flag is enabled; lookalike domain `example.com.attacker.net` does not match the `.example.com` suffix; at expiration, the policy stops applying. `hostOnly` does not automatically protect subdomains. In real browsers, each subdomain may carry its own HSTS policy or be covered by a preloaded parent; this program does not simulate those layers.

## 16. Testing real HSTS/HTTPS behavior

### 16.1. Checking headers over HTTPS

```bash
curl -I https://app.example.com/
```

Example response:

```http
HTTP/2 200
strict-transport-security: max-age=300
content-type: text/html
```

HTTP status, version, and header casing can vary; do not assume every request returns 200. Verify HSTS appears on **HTTPS responses the browser actually receives**, including important login redirects and error responses. `curl -I` sends HEAD; if the server behaves differently for HEAD, test GET per actual contract.

### 16.2. Checking HTTP redirects

```bash
curl -I http://app.example.com/
```

Illustrative response:

```http
HTTP/1.1 308 Permanent Redirect
Location: https://app.example.com/
```

Never use an HTTP response containing HSTS to conclude browsers learn the policy. The HTTPS response is where `Strict-Transport-Security` must be verified.

### 16.3. Testing in a browser

1. Open DevTools → Network and visit the HTTPS URL; observe `Strict-Transport-Security` in the response.
2. Use an isolated test profile so the browser learns the policy, then enter an `http://` URL for the same host.
3. The browser may display **307 Internal Redirect** or only issue an HTTPS request, depending on the browser; an internal 307 is not necessarily an HTTP server redirect.
4. Confirm no HTTP network request is sent to the HSTS host after the policy is learned.
5. Test subdomains when `includeSubDomains` is enabled, especially rarely accessed hosts, internal hosts, and hosts with separate certs.
6. Check mixed content, OAuth callbacks, HTTPS assets, `Secure` cookies, and `wss://` WebSockets.
7. Check certificate expiry, trust chain, SNI, SSL/TLS protocols, preload status, and alerting.
8. Never break production certificates to test browser warning blocks; use a dedicated test environment.

**MockMvc** verifies the header writer, **curl** inspects actual server responses, and a **browser** verifies HSTS enforcement. These three testing approaches complement—not replace—one another.

### 16.4. Test matrix

| Test case | Result to observe |
|---|---|
| HTTPS secure request | HSTS appears per policy |
| HTTP insecure request | Browser does not learn HSTS from HTTP |
| Browser without learned policy | Initial first-visit gap may exist |
| Browser with learned `max-age>0` | Upgrades HTTP URL to HTTPS before network I/O |
| Host with `includeSubDomains=false` | Parent does not automatically protect child |
| Parent with `includeSubDomains=true` | Child/nested child forced to HTTPS |
| Expired certificate on HSTS host | Browser shows strict unbypassable error |
| Server sends `max-age=0` over HTTPS | Can clear the learned host policy |
| Server sends `max-age=0` over HTTP | Does not clear the host policy |
| Preload not yet distributed by browser | Cannot claim first-visit protection |
| Reverse proxy HTTPS while app sees HTTP | App HSTS writer may omit header |
| Both Nginx and Spring emit HSTS | Must detect and standardize on one source |
| Non-browser API client | Do not rely on HSTS to enforce TLS |
| Mixed content over HTTP | Detect and fix HTTPS URLs/resources |
| Certificate renewal/rotation | Causes no HTTPS or HSTS disruption |
| CSRF/XSS/authorization | Still tested independently |

## 17. Common mistakes

1. **Enabling redirects without HSTS**, leaving the initial HTTP request vulnerable to interception.
2. **Setting HSTS on HTTP port 80** and thinking the browser saved the policy.
3. **Enabling `includeSubDomains` on a parent while HTTP-only subdomains exist**, rendering legacy services unreachable.
4. **Enabling `preload` without understanding browser lists**, assuming adding the directive is enough.
5. **Confusing HSTS with TLS**, raising `max-age` without configuring certificates or a port 443 listener.
6. **Letting certificates expire** or misconfiguring SANs on an HSTS host, causing hard-to-bypass outages.
7. **Using `max-age=31536000` right away** without phased rollout or certificate monitoring.
8. **Thinking `max-age=0` over HTTP clears the policy** or opts out of parent/preload rules.
9. **Letting the backend behind a TLS proxy see requests as HTTP**, breaking HSTS/cookies/redirects.
10. **Trusting `X-Forwarded-Proto` from the internet** instead of only from a trusted reverse proxy.
11. **Both Nginx and Spring emitting different HSTS headers**, complicating review and rollback.
12. **Configuring HSTS for only one route** even though the policy applies hostname-wide.
13. **Failing to test HTTPS redirect/error responses**, leaving headers missing on real paths.
14. **Mixed content** from HTTP JS/API/font/script requests on an HTTPS page.
15. **Private keys stored in repositories/images**, neglecting secret stores and file permissions.
16. **Relying on MockMvc `secure(true)` to claim TLS safety**, even though the test touches no certificates.
17. **Relying on curl without browser testing**, missing browser HSTS store/upgrade behavior.
18. **Thinking HSTS blocks XSS/CSRF/phishing**, omitting application security layers.
19. **Overlooking internal subdomains and nested domains**, even though preload covers them.
20. **Lacking a rollback/runbook**, causing certificate/HTTPS failures to drag on for weeks or longer.

## 18. Production deployment checklist

- [ ] Hostnames, certificate SANs, CA chains, and expiration dates are valid.
- [ ] TLS 1.2/1.3 and cipher suites meet current standards; certificates are auto-renewed and monitored.
- [ ] HTTP redirects to HTTPS on the right host without loops and without sending credentials over HTTP.
- [ ] All login, API, OAuth redirect, static asset, and WebSocket traffic uses HTTPS/WSS with no mixed content.
- [ ] HSTS header is emitted on HTTPS responses, not expected on HTTP responses.
- [ ] If behind a proxy, forwarded scheme/host/port are properly configured and trusted proxies only are accepted.
- [ ] One owner is chosen for the HSTS policy (edge or Spring); no duplicate or conflicting headers.
- [ ] `max-age` is rolled out gradually with monitoring and observation windows.
- [ ] `includeSubDomains` is enabled only after auditing all subdomains and nested services.
- [ ] `preload` is considered only when accepting domain-wide HTTPS commitment and slow rollback.
- [ ] Certificate renewal alerts, TLS recovery runbooks, and HSTS rollback procedures exist.
- [ ] `Secure`/`HttpOnly`/`SameSite` cookies and CSRF/XSS/authorization are independently protected.
- [ ] MockMvc/WebTestClient header tests, TLS integration tests, and browser behavior tests are in place.
- [ ] Non-browser HTTP clients are not assumed to enforce HSTS.
- [ ] Domain and preload status are re-verified after DNS, proxy, certificate, or sub-product changes.

## 19. Self-check

**Question 1.** An HTTP `308` response includes `Strict-Transport-Security`. Has the browser learned HSTS yet?

**Answer:** Not from the HTTP response. The header must be received over HTTPS with valid TLS and certificates.

**Question 2.** HTTPS terminates at Nginx, and Spring Boot connects to Nginx over HTTP. Why might Spring Security omit HSTS?

**Answer:** In Servlet, the default HSTS writer checks `request.isSecure()`. If the framework is not configured to read the original scheme from a trusted proxy, it sees the request as insecure. Fix forwarded headers/trust boundaries or let the edge own the header.

**Question 3.** `example.com` sends `includeSubDomains` while `legacy.example.com` only supports HTTP. What is the risk?

**Answer:** Browsers that learn the parent policy will attempt HTTPS connections to the legacy host and may fail to reach it. Upgrade the legacy host first or restrict the policy to specific hosts.

**Question 4.** Is sending `max-age=0` from HTTP port 80 a complete rollback?

**Answer:** No. Browsers ignore HSTS on HTTP. Valid HTTPS is required, and parent or preload policies can continue forcing HTTPS.

**Question 5.** Does calling `preload(true)` in Spring Security mean the domain is in Chrome's preload list?

**Answer:** No. It only adds the `preload` directive to the header. You must meet `hstspreload.org` criteria, submit the domain, and wait for browser distribution.

**Question 6.** Does HSTS stop JavaScript from reading cookies or automatically validate CSRF tokens?

**Answer:** No. `HttpOnly` restricts JavaScript cookie access; CSRF tokens/Origin checks protect requests; HSTS only helps enforce HTTPS for the host.

## 20. References

- [RFC 6797 — HTTP Strict Transport Security](https://www.rfc-editor.org/rfc/rfc6797).
- [MDN — Strict-Transport-Security header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security).
- [Spring Security 6.5 — Servlet Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html).
- [Spring Security 6.5 — Reactive Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html).
- [Spring Boot — SSL bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html).
- [Spring Boot — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/how-to/webserver.html).
- [HSTS Preload List Submission — Requirements and Deployment](https://hstspreload.org/).
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html).

**Remember:** HSTS is a **hostname-scoped HTTPS-only commitment in the browser**, protecting requests after the browser learns the policy or the domain is preloaded. It **does not create HTTPS and does not fix certificate errors**. Deploy TLS/HTTPS properly, redirect HTTP, protect private keys, configure trusted proxies, test real paths, and roll out `max-age` gradually. `includeSubDomains` and `preload` should only be enabled after thorough auditing, approval, and commitment to maintain HTTPS across the entire affected scope.