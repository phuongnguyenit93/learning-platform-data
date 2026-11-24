# HTTP to HTTPS Redirection and Protocol Detection Behind a Reverse Proxy — Spring Security WebFlux

## Objectives

After this lesson, learners can:

1. Explain why TLS encryption, HTTP → HTTPS redirection, and protocol detection behind a reverse proxy are three related yet **distinct** concerns.
2. Enable `ServerHttpSecurity.redirectToHttps(Customizer.withDefaults())` in `SecurityWebFilterChain`, understanding the roles of `HttpsRedirectWebFilter` and `Location`.
3. Explain why browsers access HTTPS while Spring Boot still sees HTTP when TLS terminates at a proxy, leading to redirect loops or wrong absolute URLs.
4. Use `Forwarded` (RFC 7239), `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port`, and `server.forward-headers-strategy: framework` so WebFlux restores the public scheme/host/port.
5. Understand the differences between `none`, `native`, `framework`, and `ForwardedHeaderTransformer`; **never trust client-supplied headers**.
6. Combine proxy TLS termination, trusted network controls, HSTS, `Secure` cookies, callback URLs, and thorough HTTPS verification.
7. Run a Java 17+ / Spring Boot 3.5 / Spring Security 6.5 example verifying HTTP redirects, forwarded HTTPS, 401/403/200, HSTS, and request scheme with `WebTestClient`.

> This lesson covers **Spring Security reactive (WebFlux)**. The code uses `ServerHttpSecurity`, `SecurityWebFilterChain`, `ServerWebExchange`, and Spring WebFlux. Servlet APIs such as `HttpSecurity`, `ForwardedHeaderFilter`, `RemoteIpValve`, and `HttpServletRequest` are not direct solutions for Reactor Netty.

## 1. The Problem Diagram: HTTPS Browser, HTTP Backend

Common deployment:

```text
Browser                   Reverse proxy / Load balancer            Spring WebFlux
    |                                 |                                   |
    | HTTPS app.example.test          |                                   |
    |-------------------------------->|                                   |
    |       TLS termination           |                                   |
    |                                 | HTTP 127.0.0.1:8080               |
    |                                 |---------------------------------->|
    |                                 | X-Forwarded-Proto: https          |
    |                                 | X-Forwarded-Host: app.example.test |
    |                                 | X-Forwarded-Port: 443             |
    |                                 |                                   |
    |<--------------------------------|<----------------------------------|
    | HTTPS response                  | HTTP internal response            |
```

The browser has an encrypted connection with the reverse proxy. Yet on the socket between the proxy and Netty, the application may see `http://127.0.0.1:8080/...`. Without handling the original request's metadata, the application will:

- Observe `exchange.getRequest().getURI().getScheme() == "http"` even though the external client connected over HTTPS.
- Return `Location: https://...` for the **same request** after the proxy terminated TLS, causing a redirect loop.
- Generate absolute URLs, OAuth2 redirect URIs, password-reset links, or cookie attributes using the internal hostname/port/scheme.
- Fail to recognize secure requests for HSTS or other scheme-dependent behaviors.

When the proxy forwards **trusted metadata**, Spring can see the client-facing URI as `https://app.example.test/account` even though the final TCP hop is HTTP. However, rewriting the request URI **does not encrypt the internal hop**. The internal network still needs firewalls, segmentation, or TLS/mTLS where appropriate.

### Distinguishing Three Functions

| Function | Outcome | Does not solve by itself |
| --- | --- | --- |
| HTTPS/TLS | Encrypts and authenticates transit up to the TLS endpoint | Does not automatically inform an HTTP backend of the original scheme |
| HTTP → HTTPS redirect | Returns HTTP 3xx + `Location: https://...` | Does not encrypt the initial HTTP request |
| Forwarded headers | Tells Spring the original scheme/host/port | Does not protect headers from client spoofing if proxy/network is wrong |
| HSTS | Instructs browser to prefer HTTPS on subsequent visits | Does not replace TLS certificates or trusted proxies |
| `Secure` cookie | Restricts browser from sending cookies over non-HTTPS | Does not replace CSRF, authn, or authz |

The right mental model: **HTTPS is established at the edge**, **HTTP is redirected to HTTPS as early as possible**, and **Spring needs trusted knowledge of the external scheme** so it neither mis-redirects nor builds wrong URLs.

## 2. Configuring redirectToHttps in Spring Security Reactive

In Spring Security 6.5, the recommended DSL is:

```java
@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http
            .redirectToHttps(Customizer.withDefaults())
            .authorizeExchange(exchanges -> exchanges
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

This is a **fragment** inside a configuration class requiring imports for `Bean`, `ServerHttpSecurity`, `SecurityWebFilterChain`, and `Customizer`. A complete runnable example appears in the hands-on section.

When `redirectToHttps` is enabled:

- Spring Security adds `HttpsRedirectWebFilter`, which checks the URI/scheme observed by WebFlux.
- If the request is not HTTPS, the filter builds a redirect to the equivalent HTTPS URL (port and path per configured mapping).
- If the request is recognized as HTTPS, the filter passes it along to authentication/authorization/controllers.
- Redirecting does not mean the user is authenticated; the redirected request still undergoes authentication and authorization.
- The exact default redirect status code depends on implementation/version; tests should assert **3xx and a `Location` with scheme `https`** unless stricter requirements apply, rather than hardcoding a single 301/302 number.

The no-argument `http.redirectToHttps()` overload was deprecated in Spring Security 6.5. Use `redirectToHttps(Customizer.withDefaults())` to match the current API in this baseline.

### Position in the Filter Chain

`HttpsRedirectWebFilter` redirects before allowing HTTP requests deeper into the protection pipeline. However, configurations with multiple `SecurityWebFilterChain` beans, security matchers, or custom filters can alter execution order. Always test **each actual route** rather than assuming one security bean redirects every URL.

### An HTTPS Redirect Cannot Rescue the Initial HTTP Request

If a user submits a login form over HTTP, the credentials **have already traveled over HTTP** before the server returns the redirect. If an attacker can intercept or downgrade the initial HTTP request, redirecting to HTTPS afterward does not eliminate that exposure. Therefore:

- All links, form actions, and API URLs should target HTTPS from the start.
- Edge proxies should redirect HTTP GETs to HTTPS early and never serve sensitive operations on port 80.
- Enable HSTS on HTTPS domains after auditing all relevant subdomains.
- Never send passwords, JWTs, or session cookies over public HTTP hoping a redirect will secure the request.

## 3. Why Do Redirect Loops Happen Behind a Proxy?

A classic loop:

```text
Browser GET https://app.example.test/settings
          |
          v
Proxy receives HTTPS; calls backend over HTTP
          |
          v
Spring has not processed X-Forwarded-Proto
-> perceived scheme=http
          |
          v
HttpsRedirectWebFilter -> 3xx Location=https://app.example.test/settings
          |
          v
Browser requests the exact same HTTPS URL again
          |
          +--> Proxy forwards HTTP again ... loop
```

Browsers usually show `ERR_TOO_MANY_REDIRECTS`. You may also see redirects from `https://public` to `https://internal-host:8080`, or OAuth2 providers reporting callback URI mismatches.

When the proxy sets and sanitizes `X-Forwarded-Proto: https` and Spring uses `ForwardedHeaderTransformer`:

```text
Browser HTTPS
  -> trusted proxy (TLS termination)
  -> backend HTTP + forwarded HTTPS metadata
  -> WebFlux restores external URI with scheme=https
  -> HttpsRedirectWebFilter sees HTTPS: NO redirect
  -> authentication + authorization + controller run normally
```

The key is **restoring the perceived scheme before the security redirect**, not disabling security or trusting arbitrary headers.

## 4. Forwarded (RFC 7239) and X-Forwarded-*

### 4.1. Standard Header

```http
Forwarded: for=192.0.2.123;proto=https;host=app.example.test
```

Parameters:

- `for`: client/prior-hop address per convention and topology.
- `proto`: original scheme when the proxy received the request.
- `host`: public external host.

Multiple comma-separated entries may exist across multiple proxies; never blindly trust the first entry. The proxy chain must have clear policies for trusted hops and header normalization.

### 4.2. Common Practical Headers

```http
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
X-Forwarded-For: 192.0.2.123
```

| Header | Intended info | Risk if spoofed |
| --- | --- | --- |
| `X-Forwarded-Proto` | Public scheme | Bypasses HTTPS redirect or distorts Secure/HSTS handling |
| `X-Forwarded-Host` | Public host requested | Poisons absolute URLs, password-reset links, or redirects to attacker hosts |
| `X-Forwarded-Port` | External port | Wrong ports in URLs/redirects/callbacks, or leaks internal ports |
| `X-Forwarded-For` | Client IP across proxy hops | Spoofs IP allowlists, rate limiting, and audit logs if source is untrusted |
| `X-Forwarded-Prefix` | Public context path/prefix | Wrong callback paths or links, or attacker-controlled redirect prefixes |
| `Forwarded` | Standardized multi-parameter metadata | Conflicts with `X-Forwarded-*` or spoofing |

For an external `https://app.example.test/path` hitting backend `http://127.0.0.1:8080/path`, expected post-transform URI:

```text
Before header processing:
  scheme=http, host=127.0.0.1, port=8080

After processing trusted proxy metadata:
  scheme=https, host=app.example.test, port=443
```

Standard HTTPS port 443 is typically omitted when re-serializing the URI. Controllers, redirect URL builders, HSTS, and secure-request checks all benefit from the normalized URI.

### Why Not Parse Raw Headers Manually in Controllers?

Do not write:

```java
// Anti-pattern if header is not sanitized by a trusted proxy:
String scheme = exchange.getRequest().getHeaders()
        .getFirst("X-Forwarded-Proto");
boolean secure = "https".equalsIgnoreCase(scheme);
```

This input can be fabricated by external clients. Furthermore, after `ForwardedHeaderTransformer` runs, the header may already be stripped from the downstream request. The right approach is letting the framework normalize `ServerHttpRequest` at the configured boundary while firewalls/proxies guarantee metadata trustworthiness.

## 5. server.forward-headers-strategy in Spring Boot 3.5

Boot provides the property:

```yaml
server:
  forward-headers-strategy: framework
```

| Value | Mechanism | When to choose |
| --- | --- | --- |
| `none` | Boot does not consume forwarded headers to adjust URIs | App serves TLS directly or uses a custom solution |
| `native` | Embedded HTTP server handles forwarded headers natively (Netty/Tomcat/Jetty, etc.) | Once native handling is verified for your headers/topology |
| `framework` | Spring Framework handles them; in WebFlux this is `ForwardedHeaderTransformer` | When WebFlux must restore external scheme/host/port behind a sanitizing edge |

Spring Boot 3.5 docs note that the default can be `native` in certain supported cloud platforms, and `none` elsewhere. Never rely on defaults when configuring TLS termination; declare it explicitly and verify at runtime.

### Where Does ForwardedHeaderTransformer Run?

In WebFlux, `org.springframework.web.server.adapter.ForwardedHeaderTransformer` processes requests **before security WebFilters**:

1. Reads forwarded headers from the request.
2. Restores request URI/host/port from the forwarded metadata.
3. Strips forwarded headers from the request passed downstream to prevent duplicate or accidental reuse.
4. Lets `HttpsRedirectWebFilter` and downstream components observe the accurate client-facing scheme.

This differs from Servlet's `ForwardedHeaderFilter`. In Boot WebFlux, `server.forward-headers-strategy=framework` wires up the appropriate integration; you do not need to register duplicate manual filters/transformers alongside it.

### When There Is No Trusted Proxy: removeOnly

Spring Framework supports `ForwardedHeaderTransformer#setRemoveOnly(true)` to **strip** forwarded headers without trusting them:

```java
// Alternative fragment inside Spring @Configuration.
// Do not register alongside another active transformer.
@Bean(name = "forwardedHeaderTransformer")
ForwardedHeaderTransformer forwardedHeaderTransformer() {
    ForwardedHeaderTransformer transformer =
            new ForwardedHeaderTransformer();
    transformer.setRemoveOnly(true);
    return transformer;
}
```

Requires importing `org.springframework.web.server.adapter.ForwardedHeaderTransformer` and `org.springframework.context.annotation.Bean`. Use this when **no** proper trust boundary exists, not alongside Boot's trusting `framework` strategy. With `removeOnly`, Spring **cannot infer external HTTPS** from stripped headers.

## 6. A Trusted Proxy Is a Mandatory Security Boundary

Enabling `framework` on an app with a publicly exposed backend port and **no** restriction on who can send headers creates a vulnerability. A direct HTTP request carrying `X-Forwarded-Proto: https` can trick the app into treating HTTP as HTTPS. `X-Forwarded-Host: malicious.invalid` can make code build absolute URLs or redirects to the wrong host.

**Three non-negotiable requirements:**

1. **Network isolation:** the backend accepts connections only from approved reverse proxies/load balancers/workloads. Single-host setups can use `server.address=127.0.0.1`; container environments need security groups, private listeners, network policies, or mTLS.
2. **Edge header normalization:** strip any client-sent `Forwarded` and `X-Forwarded-*` headers, then emit fresh headers from the connection the proxy actually observed. Never pass raw client-supplied `$http_x_forwarded_proto`.
3. **Host/protocol allowlist:** the proxy serves only approved virtual hosts rather than reflecting arbitrary `Host` or `Forwarded-Host` values; applications should also configure a trusted public base URL for sensitive links.

Across chained reverse proxies (CDN → LB → Gateway → Spring), define which hops are trusted and where headers are stripped vs. appended. Never trust "the first X-Forwarded-For entry" if external clients can supply that header.

### Illustrative Dangerous Behavior (Analysis Only)

```http
GET /api/public HTTP/1.1
Host: backend.example.test:8080
X-Forwarded-Proto: https
X-Forwarded-Host: malicious.invalid
X-Forwarded-Port: 443
```

If a public backend trusts these headers, the perceived request looks like HTTPS on the wrong host even though TCP is plain HTTP. Therefore, **never** treat a unit test simulating `XFP=https` as proof that production is secure. Simulated tests prove the framework parses headers; firewalls and proxy sanitization must be tested separately.

### Consequences of Misconfiguration

| Infrastructure flaw | Consequence |
| --- | --- |
| Proxy omits `X-Forwarded-Proto` | Redirect loop even while browser uses HTTPS |
| Public backend trusts client `XFP=https` | Real HTTP requests can bypass redirect |
| Proxy preserves client `X-Forwarded-Host` | Open redirect, link poisoning, or wrong callback URLs |
| Proxy keeps RFC `Forwarded` while rewriting XFP | Two conflicting metadata sources |
| Proxy sends internal `Host` to backend | Absolute `Location`/links point internally |
| Proxy trusts any `X-Forwarded-For` source | Spoofed client IP logs and rate-limit bypass |
| `framework` enabled with no network isolation | Trust boundary exposed directly to the Internet |

## 7. Nginx TLS Termination Example

Assume:

- Browsers access `https://app.example.test`.
- Nginx runs on the same host as Spring Boot with a trusted TLS certificate for the real domain.
- Spring Boot listens on HTTP `127.0.0.1:8080`, unexposed to the Internet.
- Nginx is the sole edge, not behind another proxy. Other topologies require adjusting IP/trusted-hop settings.

Illustrative Nginx config:

```nginx
server {
    listen 80;
    server_name app.example.test;

    return 308 https://app.example.test$request_uri;
}

server {
    listen 443 ssl;
    server_name app.example.test;

    ssl_certificate     /etc/ssl/certs/app.example.test.crt;
    ssl_certificate_key /etc/ssl/private/app.example.test.key;

    location / {
        proxy_pass http://127.0.0.1:8080;

        # Allowlisted public Host; do not reflect arbitrary Host headers.
        proxy_set_header Host app.example.test;

        # Strip client-supplied RFC Forwarded headers.
        proxy_set_header Forwarded "";

        # Overwrite X-Forwarded metadata with edge-verified facts.
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host app.example.test;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $remote_addr;

        # Clear unused metadata variants outside demo scope.
        proxy_set_header X-Forwarded-Prefix "";
        proxy_set_header X-Forwarded-Ssl "";
    }
}
```

Certificate paths are illustrative; supply real certs/keys and TLS policies in deployments. In Nginx, an empty string in `proxy_set_header` suppresses forwarding that header. You should also configure a default server rejecting unknown hostnames outside approved `server_name` entries. This model fixes one hostname because it serves a single domain; multi-tenant/vhost setups require dedicated design.

**Nginx 80 → HTTPS** protects HTTP clients at the edge; **Spring redirectToHttps** serves as an extra guard if any request still looks like HTTP. When browsers arrive via Nginx HTTPS, `forwarded scheme=https` prevents Spring from redirecting again.

**Do not blindly use `$proxy_add_x_forwarded_for` on an edge proxy receiving untrusted `X-Forwarded-For`**, because appending preserves attacker-supplied values. With multiple trusted hops, configure `realip`/trusted proxies and explicit append/replace policies.

## 8. Runnable Spring Boot 3.5 WebFlux Project

The example includes:

- Spring Boot + WebFlux/Spring Security, Java 17.
- Default HTTPS redirect.
- Forwarded strategy `framework`.
- A public API showing the URI Spring perceives after transformation.
- A private API requiring HTTP Basic and an admin API requiring role `ADMIN`.
- `WebTestClient` running against real embedded Netty on loopback, testing direct HTTP and forwarded HTTPS.

**File layout:**

```text
https-proxy-demo/
  settings.gradle
  build.gradle
  src/main/java/example/httpsproxy/
    HttpsProxyApplication.java
    SecurityConfiguration.java
    ApiController.java
  src/main/resources/
    application.yml
  src/test/java/example/httpsproxy/
    HttpsProxyIntegrationTest.java
```

### 8.1. Gradle

**`settings.gradle`**:

```groovy
rootProject.name = 'https-proxy-demo'
```

**`build.gradle`**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Boot 3.5.7 provides a stable baseline for this example, not a recommendation to stay on an unpatched release when production requires security upgrades. The project requires JDK 17+ and compatible Gradle. Never add `spring-boot-starter-web` to a pure WebFlux demo, as Boot may select Servlet when both starters exist on the classpath.

### 8.2. application.yml

**`src/main/resources/application.yml`**:

```yaml
server:
  address: 127.0.0.1
  port: 8080
  forward-headers-strategy: framework

spring:
  application:
    name: https-proxy-demo
```

- Netty binds only to loopback on the demo machine, avoiding public backend exposure.
- The backend does not enable TLS on 8080; public TLS sits at the proxy.
- `framework` activates `ForwardedHeaderTransformer` in WebFlux.
- `RANDOM_PORT` tests override the port while still running on loopback.
- In containers on separate hosts, never copy loopback binding blindly without understanding networking; configure private listeners and network policies.

### 8.3. Main Class

**`src/main/java/example/httpsproxy/HttpsProxyApplication.java`**:

```java
package example.httpsproxy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpsProxyApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpsProxyApplication.class, args);
    }
}
```

### 8.4. Spring Security WebFlux Configuration

**`src/main/java/example/httpsproxy/SecurityConfiguration.java`**:

```java
package example.httpsproxy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService demoUsers(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("local-demo-password"))
                .roles("READER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("local-demo-password"))
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .redirectToHttps(Customizer.withDefaults())
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/public")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .pathMatchers(HttpMethod.GET, "/api/private")
                            .authenticated()
                        .anyExchange().denyAll()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

Explanation:

1. `redirectToHttps` triggers when **Spring perceives the scheme as HTTP**. If `ForwardedHeaderTransformer` already normalized `scheme=https`, the request continues without looping.
2. Roles are never elevated merely because HTTPS is active. `/api/admin` still checks `ROLE_ADMIN`.
3. HTTP Basic makes testing 401 (unauthenticated) and 403 (logged in, lacking role) clear. Never send real Basic credentials over public HTTP; production needs HTTPS and appropriate authentication.
4. HTML login is disabled so a 302 login-page redirect is not confused with a 3xx HTTPS redirect.
5. Default CSRF remains enabled; the demo uses GET only. If adding unsafe methods for browser cookies, design CSRF explicitly.
6. The demo hashes passwords with `DelegatingPasswordEncoder`, using hardcoded values solely for localhost/testing. Never copy demo accounts into production.
7. One `SecurityWebFilterChain` covers all URLs; in real multi-chain apps, configure and test HTTPS policies per matcher.

### 8.5. Controller Observing the Public Scheme

**`src/main/java/example/httpsproxy/ApiController.java`**:

```java
package example.httpsproxy;

import java.net.URI;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<String> perceivedUri(ServerWebExchange exchange) {
        URI uri = exchange.getRequest().getURI();
        return Mono.just(uri.getScheme() + "://" +
                uri.getRawAuthority() + uri.getRawPath());
    }

    @GetMapping("/api/private")
    public Mono<String> privateInfo() {
        return Mono.just("private-ok");
    }

    @GetMapping("/api/admin")
    public Mono<String> adminInfo() {
        return Mono.just("admin-ok");
    }
}
```

Once the framework trusts headers **from a sanitizing proxy**, `/api/public` reflects the external URL `https://app.example.test/api/public` despite the backend HTTP socket. In production, do not use a public debug endpoint like this to generate password-reset URLs or make trust decisions; for sensitive links, use a fixed, validated public base URL configuration.

No `block()` or manual `subscribe()` appears in the controller; WebFlux subscribes to `Mono<String>`.

## 9. Integration Tests with WebTestClient and Real Netty

This test launches embedded Netty via `@SpringBootTest(webEnvironment=RANDOM_PORT)`. Each test client sends HTTP to the loopback backend:

- `direct`: no forwarded headers, representing a direct HTTP backend call.
- `proxied`: sets `X-Forwarded-Proto: https`, host, and port to simulate headers inserted by a **trusted proxy**.

**Note:** test connections are still HTTP; these tests verify scheme parsing and security filter logic, **not** TLS/certificates or spoof prevention in production. Those must be tested after deploying a real reverse proxy.

**`src/test/java/example/httpsproxy/HttpsProxyIntegrationTest.java`**:

```java
package example.httpsproxy;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpsProxyIntegrationTest {

    @LocalServerPort
    int port;

    private WebTestClient direct;
    private WebTestClient proxied;

    @BeforeEach
    void prepareClients() {
        String url = "http://127.0.0.1:" + port;

        direct = WebTestClient.bindToServer()
                .baseUrl(url)
                .build();

        // Headers set by mock proxy in test, NOT production.
        proxied = WebTestClient.bindToServer()
                .baseUrl(url)
                .defaultHeader("X-Forwarded-Proto", "https")
                .defaultHeader("X-Forwarded-Host", "app.example.test")
                .defaultHeader("X-Forwarded-Port", "443")
                .build();
    }

    @Test
    void httpDirectRequestRedirectsToHttps() {
        direct.get().uri("/api/public")
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectHeader().value("Location", location ->
                        assertTrue(location.startsWith("https://")));
    }

    @Test
    void insecureResponseDoesNotSetHsts() {
        direct.get().uri("/api/public")
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectHeader().doesNotExist("Strict-Transport-Security");
    }

    @Test
    void forwardedHttpsIsRecognizedWithoutLoop() {
        proxied.get().uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(body -> {
                    assertTrue(body.startsWith(
                            "https://app.example.test"));
                    assertTrue(body.endsWith("/api/public"));
                });
    }

    @Test
    void forwardedHttpsAnonymousStillNeedsLogin() {
        proxied.get().uri("/api/private")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedReaderGetsPrivateData() {
        proxied.get().uri("/api/private")
                .headers(headers -> headers.setBasicAuth(
                        "reader", "local-demo-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("private-ok");
    }

    @Test
    void authenticatedReaderCannotUseAdminEndpoint() {
        proxied.get().uri("/api/admin")
                .headers(headers -> headers.setBasicAuth(
                        "reader", "local-demo-password"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void authorizedAdminCanUseAdminEndpoint() {
        proxied.get().uri("/api/admin")
                .headers(headers -> headers.setBasicAuth(
                        "admin", "local-demo-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void recognizedSecureRequestGetsHsts() {
        proxied.get().uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().exists("Strict-Transport-Security");
    }

    @Test
    void forwardedHttpStillRequiresRedirect() {
        direct.get().uri("/api/public")
                .header("X-Forwarded-Proto", "http")
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectHeader().value("Location", location ->
                        assertTrue(location.startsWith("https://")));
    }

    @Test
    void securePublicApiNeedsNoIdentity() {
        proxied.get().uri("/api/public")
                .exchange()
                .expectStatus().isOk();
    }
}
```

Run from a project with Gradle Wrapper:

```bash
./gradlew test --tests example.httpsproxy.HttpsProxyIntegrationTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.httpsproxy.HttpsProxyIntegrationTest
```

**Expected:** 10 tests PASS with JDK, Gradle, dependencies, and project set up per the example. This is expected from the source, **not an actual workspace execution result**. When upgrading Spring Boot/Security or switching servers, re-test status codes, Host forwarding, TLS handling, and cookies.

### Meaning of Each Test Group

| Test group | Proves |
| --- | --- |
| Direct HTTP → 3xx + HTTPS Location | Redirect filter works |
| Direct HTTP omits HSTS | HSTS is not emitted as if secure |
| Forwarded HTTPS → 200, public URI | Framework restored scheme/host/port from metadata |
| Forwarded HTTPS anonymous private → 401 | HTTPS does not bypass authentication |
| Reader private → 200; reader admin → 403 | Authorization still enforces roles |
| Admin → 200 | Authorized role succeeds |
| Forwarded HTTPS includes HSTS | Spring sees secure request and emits security header |
| Forwarded HTTP still 3xx | `XFP=http` cannot bypass HTTPS requirement |

These tests **do not guarantee** a production backend cannot be called directly with forged headers. Test firewalls/ingresses at the infrastructure layer, real TLS certificates, and browser HSTS/cookies on the real domain.

## 10. Manual Testing and Inspecting Results

### 10.1. Run the Demo Backend

In the project with Gradle Wrapper:

```bash
./gradlew bootRun
```

PowerShell:

```powershell
.\gradlew.bat bootRun
```

### 10.2. Direct Backend HTTP

```bash
curl -i "http://127.0.0.1:8080/api/public"
```

Expected: 3xx response and `Location` with `https` scheme. Never pass `curl -L` to follow onto HTTP port 8080, because the example does not serve TLS on that port. The redirect port is determined by `HttpsRedirectWebFilter`/port mapping; do not assume it equals the backend port.

### 10.3. Simulating an HTTPS Proxy Request Locally

```bash
curl -i "http://127.0.0.1:8080/api/public" \
    -H "X-Forwarded-Proto: https" \
    -H "X-Forwarded-Host: app.example.test" \
    -H "X-Forwarded-Port: 443"
```

Expected: 200 with URI showing `https://app.example.test/api/public`. The very fact that `curl` can supply these headers demonstrates **why backends must not be publicly exposed** when trusting forwarded metadata.

### 10.4. Through Real Nginx

Once a valid certificate is installed for a domain you control:

```bash
curl -i "https://app.example.test/api/public"
curl -I "http://app.example.test/api/public"
```

- Public HTTPS requests traverse real TLS to the proxy, forward as HTTPS to the backend, and return 200.
- Public HTTP requests on port 80 receive 308 from Nginx without hitting Spring in this setup.
- Verify the TLS certificate chain, exact hostname, and HSTS on HTTPS.
- Never use `curl -k` in production TLS testing, as it skips certificate verification.

If a browser loops 301/302 on the same URL, check proxy headers and the forwarded strategy rather than merely clearing browser cookies.

## 11. HSTS: Protecting Subsequent Visits

HSTS (HTTP Strict Transport Security) tells the browser that a host should only be accessed via HTTPS for the server-announced duration:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

- `max-age`: duration the browser remembers the policy.
- `includeSubDomains`: extends to subdomains; never enable before auditing hosts that might still use HTTP.
- `preload`: directive for preload inclusion subject to separate rules and submission; simply adding the word `preload` does not preload the domain immediately.
- HSTS headers **are meaningful only when received over valid HTTPS**; an HTTP response cannot establish HSTS trust.

Spring Security supports HSTS on secure responses by default. Behind a TLS-terminating proxy, if the app misperceives the scheme as HTTP, HSTS may not be written properly. Thus forwarded-scheme detection impacts both redirects **and** security headers.

Do not overuse HSTS preload on systems with legacy subdomains; browser caches/preload lists can persist long after a rollback.

## 12. Secure Cookies, Auth Callbacks, and Absolute URLs

### Cookies/Sessions

Applications using `WebSession` and login cookies should evaluate `Secure`, `HttpOnly`, `SameSite`, and appropriate domain/path settings. Cookie issuance may inspect request security state, so verify `Set-Cookie` on **HTTPS responses through the real proxy**, not only via fake forwarded headers in tests. HSTS and `Secure` cookies do not replace CSRF protection.

### OAuth2/OIDC

Redirect URIs can be misconstructed as:

```text
http://127.0.0.1:8080/login/oauth2/code/provider
```

instead of:

```text
https://app.example.test/login/oauth2/code/provider
```

Identity providers validate registered redirect URIs, so wrong scheme/host/port causes `redirect_uri mismatch`. When running OAuth2 login, test callbacks through the real TLS proxy and inspect client registrations, server base URLs, forwarded metadata, and security allowlists. Never expose a public HTTP callback to work around errors.

### Absolute Links

Password-reset links, invitation emails, `Location` headers, login-success URLs, and JSON/HATEOAS links can all depend on request host. For account- or token-related URLs, prefer a **fixed, validated public base URL** rather than trusting raw `Host`/`Forwarded-Host`.

## 13. Environment Differences and Multi-Layer Reverse Proxies

### Dev Without TLS

If `redirectToHttps` is enabled while only HTTP exists on `localhost:8080`, the browser may be redirected to a **non-existent** HTTPS endpoint. That is HTTPS policy working as configured, not a password or CORS bug.

Choose one of two approaches:

- Stand up a local HTTPS reverse proxy with trusted dev certs mirroring production topology.
- Only in a dev profile, disable HTTPS redirect conditionally via an **operations-managed, trusted configuration property**; keep authentication/authorization active, and ensure that profile cannot be deployed to the Internet.

Do not assume private networks never need TLS; shared internal networks can still face sniffing or require mTLS.

### With CDN → LB → Gateway → Spring

- Identify where external TLS terminates and where trusted `X-Forwarded-Proto` is set.
- At the edge, strip untrusted client forwarded headers; on internal hops, define overwrite vs. append rules.
- Verify allowed proxy IPs/CIDRs/identities permitted to reach the backend.
- If public routes have a prefix differing from the backend, inspect `X-Forwarded-Prefix` and URL generation.
- Reject undeclared `Host` values to prevent redirects or email links pointing to attacker hosts.
- With multiple security chains, ensure `redirectToHttps` is configured on every necessary chain or enforced by the edge in front of all chains.
- Prevent proxy and Spring from generating conflicting redirects (HTTP⇄HTTPS or trailing-slash/path rewrite loops).

## 14. Common Troubleshooting Table

| Symptom | Likely cause | Remediation |
| --- | --- | --- |
| Browser reports `ERR_TOO_MANY_REDIRECTS` | Spring sees backend HTTP despite browser HTTPS | Trusted forwarded scheme + `framework` strategy |
| Public HTTPS redirects back to itself | Proxy omits `XFP=https` or Spring ignores it | Inspect actual requests at each hop |
| `Location` points to internal `host:8080` | Forwarded Host/Port unnormalized | Have proxy set fixed external host/port |
| Public HTTP backend returns 200 when client sends `XFP=https` | Header spoofing; broken trust boundary | Firewall, private binding, strip headers at edge |
| Random HTTPS hostname yields weird redirect URL | Host/`Forwarded-Host` poisoning | Host allowlist, default vhost rejection |
| HSTS missing behind TLS proxy | Spring perceives HTTP or gateway strips header | Check transformed scheme and edge response |
| Direct HTTP lacks HSTS | HSTS is invalid over HTTP | Expected behavior |
| Browser connects HTTPS to backend HTTP port | TLS handshake fails | Connect to proxy port 443, not 8080 |
| OAuth2 `redirect_uri` mismatch | Callback scheme/host/port inferred wrongly | Forwarded headers + public registered redirect URL |
| Password-reset link uses `http`/internal host | URL builder trusts wrong request info | Configure trusted public base URL |
| Cookie missing `Secure` flag | Session/proxy config or wrong scheme perceived | Inspect `Set-Cookie` at HTTPS edge |
| Gateway omits forwarded metadata | Backend cannot learn original TLS state | Emit standard headers from trusted gateway |
| `strategy=native` behaves differently from `framework` | Native server implementations differ in header support | Pick a strategy tested on your exact stack |
| `@Configuration` registers two transformers | Duplicate processing or conflicting policies | Use a single forwarding mechanism |
| Conflicting RFC `Forwarded` and `XFP` mixed | Proxy failed to sanitize all variants | Strip both and emit one consistent format |
| HSTS `includeSubDomains` breaks subdomains | Not all subdomains migrated to HTTPS | Audit/roll out before enabling |
| 401 behind HTTPS proxy | Authentication not satisfied | Fix credentials/token, never weaken redirect |
| 403 behind HTTPS proxy | Missing role, CSRF, or rule | Troubleshoot authorization/CSRF separately |
| POST changes method after redirect | 301/302/307/308 have different semantics | Use HTTPS URLs from the start; test clients |
| App has two `SecurityWebFilterChain`s, one skips redirect | HTTPS rule missing on one matcher | Test every chain/route |
| `WebTestClient` passes yet public site still exposes HTTP | Tests bypass ingress/network | Add TLS/network integration tests |

### Step-by-Step 302 Loop Debugging

1. Identify the URL used by the browser and where edge TLS terminates.
2. In the Network tab, record status and `Location` at each hop without sharing session cookies/tokens.
3. Verify the proxy actually forwards HTTPS requests to the backend and sets `X-Forwarded-Proto=https`.
4. Verify the proxy **strips** client-supplied `Forwarded`/`X-Forwarded-*` before setting its own metadata.
5. Check whether Boot's strategy is `none`/`native`/`framework` and confirm the stack is WebFlux rather than Servlet.
6. Inspect perceived scheme/host/port in safe staging to see which redirect filter emits the response.
7. Confirm the route matches the expected `SecurityWebFilterChain`.
8. Test direct HTTP → 3xx, forwarded HTTPS → 200/401/403, then real browser over TLS.
9. Verify HSTS, `Secure` cookies, and absolute callback URLs.
10. Fix only the proven faulty component; never turn off security indiscriminately.

## 15. Production Checklist

1. Public HTTPS at the edge with valid certificates and expiry/chain monitoring.
2. Early edge HTTP → HTTPS redirect; never accept sensitive credentials over HTTP.
3. Backend non-public; only trusted reverse proxies/ingresses may connect.
4. Proxy sanitizes all client `Forwarded` and `X-Forwarded-*` headers and sets accurate original proto/host/port.
5. Clear host allowlist; never build sensitive URLs from arbitrary headers.
6. Spring Boot uses a compatible, tested forwarding strategy (e.g., `framework` in WebFlux).
7. `redirectToHttps(Customizer.withDefaults())` or edge enforcement applies consistently across all chains/routes.
8. Browser HTTPS via proxy experiences no loops or internal `Location` headers.
9. HSTS uses appropriate `max-age`/`includeSubDomains`; do not enable `preload` prematurely.
10. Cookie `Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path` match topology and are browser-tested.
11. OAuth2 callbacks and absolute links emit exact public HTTPS URLs.
12. Authentication, authorization, and CSRF remain active; HTTPS does not replace permissions.
13. Test HTTP/HTTPS, 3xx/401/403/200, wrong hosts, spoofed forwarded metadata, gateway chains, and TLS certificates.
14. Logs/traces exclude passwords, bearer tokens, cookies/session IDs, and untrusted raw forwarded headers.
15. Re-review the strategy whenever changing proxies, adding CDNs, changing domains, or upgrading Spring.

## 16. Exercises

1. Remove `server.forward-headers-strategy=framework` in the demo behind an HTTP proxy, predict the redirect failure, and verify it.
2. Enable `framework`, simulate `X-Forwarded-Proto=https`, and confirm no redirect occurs. Why doesn't this test prove real TLS?
3. Send an unexpected `X-Forwarded-Host` in a test environment to observe URL poisoning risk. Enforce a host allowlist at the edge and keep the backend private.
4. Compare `none`/`native`/`framework` on Reactor Netty and observe scheme/host/port in the controller under each mode.
5. Add `GET /api/admin` restricted to `ADMIN` and test 403 for `READER` over forwarded HTTPS to prove transport differs from authorization.
6. Disable redirect only in a `dev` profile and add a test/provisioning check preventing `dev` from running in production.
7. Set up a real TLS proxy for a domain you own and inspect HSTS and `Set-Cookie` in Chrome DevTools.
8. Place an OAuth2 client behind a proxy and compare `redirect_uri` with and without trusted forwarded metadata.
9. Add a security chain for `/admin/**` and verify HTTPS rules apply across both chains.
10. Extend the pipeline to CDN → gateway → app; document trusted hops, where headers are stripped, and where IPs are appended.
11. Locate an endpoint building password-reset URLs from request `Host` and replace it with a validated public base URL.
12. Check 301/302/307/308 semantics with a test form POST; design flows so credentials are never sent over initial HTTP.

## Summary

In Spring Security **WebFlux**, `redirectToHttps(Customizer.withDefaults())` redirects requests perceived as HTTP by the framework to HTTPS. When TLS terminates at a reverse proxy, the app may receive internal HTTP even though browsers use HTTPS; `server.forward-headers-strategy: framework` and `ForwardedHeaderTransformer` restore scheme/host/port **when metadata originates from a trusted proxy**.

Missing proper forwarding easily causes **redirect loops** and wrong URLs, cookies, HSTS, or callbacks. Conversely, trusting `X-Forwarded-Proto`/`X-Forwarded-Host` from external clients invites bypasses or host poisoning. Protection requires **edge TLS + network isolation + proxy header sanitization + Spring redirect/forwarding configuration + real-world testing**. HSTS, `Secure` cookies, CSRF, and authorization are complementary layers that never replace one another.

## Official Documentation

- [Spring Security 6.5 — Reactive HTTP, Redirect to HTTPS, and Proxy Server Configuration](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/http.html)
- [Spring Security 6.5 — ServerHttpSecurity Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security 6.5 — HttpsRedirectWebFilter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/transport/HttpsRedirectWebFilter.html)
- [Spring Security 6.5 — HTTP Strict Transport Security](https://docs.spring.io/spring-security/reference/6.5/features/exploits/headers.html)
- [Spring Boot 3.5 — Running Behind a Front-end Proxy](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Framework 6.2 — WebFlux Forwarded Header Transformer](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)
- [RFC 6797 — HTTP Strict Transport Security](https://www.rfc-editor.org/rfc/rfc6797)
- [OWASP — HTTP Strict Transport Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Strict_Transport_Security_Cheat_Sheet.html)
