# Endpoint-Specific Header Customization and Real-World Verification in Spring Security Reactive

## 1. Problem Statement and Objectives

A **Spring WebFlux + Spring Security Reactive** application can serve multiple resource types:

- **GET /public/ping**: public JSON.
- **GET /ui/help**: simple HTML page, possibly containing same-origin stylesheets and images.
- **GET /api/me**: JSON containing the authenticated user's identity.
- **GET /api/admin/report**: JSON restricted to `ROLE_ADMIN`.

Every response should retain **baseline security headers**, yet some headers need **per-endpoint policies**. For example, CSP for an HTML page differs from CSP for JSON; private APIs must prevent caching; HTTPS hosts need HSTS even on error responses. Reading configuration code alone does not reveal whether a gateway or error handler alters headers on responses reaching the browser.

After this lesson, you can:

1. Distinguish request headers, response headers, URL access control, and browser rules.
2. Understand Spring Security WebFlux's default headers and why you should not disable all defaults just to add one header.
3. Configure **`ServerHttpSecurity.headers(...)`** and **`ServerHttpHeadersWriter`** to select headers by path/response type.
4. Identify the roles of **`Cache-Control`, `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, `Referrer-Policy`, `Permissions-Policy`, and `HSTS`**.
5. Ensure headers appear on 200, **401 Unauthorized**, and **403 Forbidden** responses.
6. Distinguish HSTS over HTTPS from plain HTTP requests or TLS termination at a reverse proxy.
7. Run a **Java 17+** Spring Boot WebFlux demo and test it with `curl`, `WebTestClient`, and mock HTTPS exchanges.
8. Inspect final responses behind CDN/NGINX/Ingress/API gateways instead of treating Java code as final proof.
9. Avoid weak CSPs, caching personal data, unsafe HSTS preloading, duplicate headers, and confusing CORS/CSRF.

**Key rule:** the goal is not to pile on as many headers as possible, but to **put the right headers on the right responses without breaking useful defaults, and verify actual values on the HTTP wire**.

## 2. Request Headers Differ from Response Headers

Example request:

~~~http
GET /api/me HTTP/1.1
Host: api.example.org
Authorization: Basic <encoded-credentials>
Accept: application/json
Origin: https://app.example.org
~~~

`Authorization` and `Origin` come from the client; **`Origin` does not authenticate identity**, and client-sent headers are not the server's security policy.

Example response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Content-Security-Policy: default-src 'none'; frame-ancestors 'none'

{"username":"reader"}
~~~

Response headers instruct browsers/proxies how to handle content; whether `reader` may view the profile comes from **Authentication, SecurityContext, `authorizeExchange`, and business permissions**, not from CSP or `no-store`.

| Response header | Purpose | Does not replace |
| --- | --- | --- |
| `Cache-Control: no-store` | Prevents caches from storing sensitive data | Authentication, logout, clearing already-fetched data |
| `X-Content-Type-Options: nosniff` | Restricts browser MIME-type sniffing | Accurate `Content-Type`, malicious file handling |
| `Content-Security-Policy` | Restricts script/style/img sources and framing via directives | Input validation, output encoding, auth |
| `X-Frame-Options: DENY` | Blocks framing the page in supporting browsers | Data access control, full CSP |
| `Referrer-Policy` | Limits URL data leaked via `Referer` | CSRF tokens, XSS prevention |
| `Permissions-Policy` | Restricts camera/geolocation/microphone and browser features | `ROLE_ADMIN`, API scopes |
| `Strict-Transport-Security` | Tells browsers to prefer HTTPS for the host on future visits | TLS certificates, initial HTTPS redirect |
| `Access-Control-Allow-Origin` | Permits certain cross-origin reads in browsers | Authentication, authorization, CSRF |

**Do not confuse an "endpoint" with a Java class name.** An endpoint is defined by the actual HTTP method/path traversed by requests. Both `@RestController` and `RouterFunction` are protected by the same `SecurityWebFilterChain` when registered in the same WebFlux application.

### 2.1. Origin, Site, and Host Are Not Authentication Principals

The `Origin` header relates to CORS, not proof that a user is an employee. `X-Forwarded-*` headers can be useful behind a **trusted** proxy, yet must never be blindly trusted from the Internet. Selecting per-path header profiles must rely on server-side policy, never interpolating client-supplied header values into CSP/HSTS.

## 3. Headers Provided by Spring Security Reactive by Default

In Spring Security 6.x, default header configuration typically includes:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 0
~~~

On a **secure HTTPS request**, Spring Security also includes an HSTS writer defaulting to one year and `includeSubDomains`. HSTS **is not written on HTTP** under standard writer behavior.

Notes:

- **CSP is not auto-configured with a one-size-fits-all policy**. Each HTML/SPA app must choose its script, style, image, font, and frame sources.
- **`X-XSS-Protection: 0`** disables legacy browser XSS filters, not the application's XSS defenses.
- **`Referrer-Policy`** should be checked against your exact version and effective policy; the demo sets `no-referrer` explicitly for stable test assertions.
- When a response already sets its own `Cache-Control`, default writers may respect that value; do not assume every response from every layer is identical.
- **Keep header support enabled**: adding a custom header is never a reason to turn off the whole baseline.

Wrong snippet:

~~~java
// Do not use just to add a new CSP.
.headers(headers -> headers.disable())
~~~

Disabling all defaults forces you to manage every critical header manually and increases misconfiguration risk. Use `HeaderSpec.writer` or specific `hsts`/`frameOptions`/`referrerPolicy`/`permissionsPolicy` DSL methods instead.

### 3.1. HTTP Status Codes Matter Too

When `GET /api/me` lacks credentials, the authentication entry point can return 401 **before any controller runs**. When `reader` hits `/api/admin/report` without `ROLE_ADMIN`, the access denied handler returns 403. Setting headers only inside controllers leaves these error responses without the policy.

**Lesson requirement:** test CSP, caching, nosniff, and required headers across **200/401/403**; also test at the public edge if a proxy is present.

## 4. Per-Endpoint Header Policy Matrix

The sample project chooses:

| Endpoint | Who can call? | Endpoint-specific response headers | Shared baseline |
| --- | --- | --- | --- |
| `GET /public/ping` | Guest and user | Strict JSON CSP | Cache no-store, nosniff, frame DENY, referrer no-referrer |
| `GET /ui/help` | Guest and user | CSP for script-free HTML | Same |
| `GET /api/me` | Authenticated | JSON CSP, `Permissions-Policy`, `X-Robots-Tag` | Same |
| `GET /api/admin/report` | `ROLE_ADMIN` | API policy even on 403 | Same |
| Unknown URL | `denyAll` | Strict JSON CSP as fallback | Same |

JSON CSP value:

~~~http
Content-Security-Policy: default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'
~~~

HTML help page CSP value:

~~~http
Content-Security-Policy: default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'
~~~

Why do they differ? JSON is not a page executing scripts or styles; a tight CSP acts as defense-in-depth if a browser ever misinterprets content. HTML may need same-origin CSS and images; the demo still forbids scripts and iframes. If HTML genuinely needs JavaScript, design **`script-src`/`connect-src`/nonces/hashes** properly. Never add `'unsafe-inline'` or `*` just to silence CSP warnings.

**`X-Frame-Options: DENY`** stays consistent with **`frame-ancestors 'none'`**. If a product needs approved iframe embedding, update both consistently and test clickjacking protection.

For APIs:

~~~http
Permissions-Policy: camera=(), microphone=(), geolocation=()
X-Robots-Tag: noindex, nofollow
~~~

These are supplementary browser/crawler policies and **neither grant nor revoke API permissions**. Never use `X-Robots-Tag` as data security, since bots are not forced to obey it.

### 4.1. Caching Personal Data

For `/api/me` and `/api/admin/report`, ensure **`Cache-Control` includes `no-store`**. A misconfigured CDN caching responses with `Authorization` or cookies can cause a severe leak even when CSP is perfect.

For `/assets/app.abc123.js`—a public file with a content hash—**`public`, long `max-age`, `immutable`** can be beneficial. That is a separate policy, best configured on the static resource handler/proxy and verified across `Cache-Control`, `Pragma`, `Expires`, and `Vary`; **never** open default caching across all `/api/**` routes.

## 5. Reactive APIs for Adding Headers

Correct WebFlux packages:

~~~java
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.header.ServerHttpHeadersWriter;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;
~~~

**`ServerHttpHeadersWriter`** contract:

~~~java
Mono<Void> writeHttpHeaders(ServerWebExchange exchange);
~~~

This is an illustrative signature, not a standalone Java file. In Spring Security 6.5, **`ServerHttpSecurity.HeaderSpec.writer(ServerHttpHeadersWriter)`** registers a custom writer in header support.

Partial `SecurityWebFilterChain` configuration:

~~~java
return http
        .headers(headers -> headers
                .writer(endpointHeadersWriter))
        .build();
~~~

**Never call `subscribe()` manually** on `Mono<Void>`. Spring Security wires the writer into the response commit lifecycle. If writing a standalone `WebFilter`, understand `response.beforeCommit` and filter ordering; avoid writing headers too late after the response has committed.

### 5.1. Selecting Paths Properly

~~~java
String path = exchange.getRequest()
        .getPath().pathWithinApplication().value();
~~~

With stable application paths, you can use an exact match for `/ui/help` and a prefix check for `/api/`. When gateways rewrite URLs, context paths exist, or multiple `SecurityWebFilterChain` beans are used, match against **the actual path seen by WebFlux**; browser paths may differ due to proxies.

### 5.2. Per-URL Headers Do Not Mean Per-URL Role Policies

A custom writer governs only response headers. Authentication and authorization are declared separately:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers("/public/ping", "/ui/help").permitAll()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated()
        .anyExchange().denyAll())
~~~

**Put the admin rule before `/api/**`**. Reversing the order lets an authenticated user lacking `ROLE_ADMIN` pass the broader `authenticated` rule. Even with perfect CSP, that would be an authorization flaw.

## 6. HSTS Only Works Properly Over HTTPS

**HTTP Strict Transport Security** instructs browsers to use HTTPS for the host for `max-age` seconds. It does not issue TLS certificates, prevent attacks before the browser learns the policy, or replace HTTPS redirects.

Example:

~~~http
Strict-Transport-Security: max-age=2592000
~~~

`2592000` seconds = **30 days**. The demo chooses 30 days, **`includeSubDomains=false`**, and **`preload=false`** to illustrate a cautious rollout step. This is **not** a universal production default: tighten protection after auditing HTTPS across your infrastructure.

- **On HTTP localhost:** do not expect HSTS. Browsers must ignore HSTS received over insecure HTTP.
- **On public HTTPS URLs:** expect HSTS per policy after proxy/edge processing.
- **`includeSubDomains`** should be enabled only once all subdomains serve trusted HTTPS.
- **`preload`** has long-term criteria and consequences; never turn it on merely because an admin endpoint needs strong security.
- HSTS is a **host-wide policy**, not a per-endpoint policy for `/api/admin` or a specific role.

### 6.1. With TLS Termination

Common architecture:

~~~text
Browser -- HTTPS --> Reverse proxy -- internal HTTP --> WebFlux
~~~

If the backend sees only HTTP, the HSTS writer may skip the header. Ensure:

1. The trusted-boundary proxy terminates TLS and strips/overwrites Internet-sent `Forwarded`/`X-Forwarded-*` headers.
2. Spring processes forwarded headers only when topology and trusted proxies are well-defined.
3. HTTP→HTTPS redirects and `Secure` `Set-Cookie` attributes work properly through the edge.
4. Decide who owns the final HSTS policy (proxy or app) to avoid duplicates or conflicts.
5. **`curl` the public HTTPS URL** to verify the final value rather than checking localhost alone.

Config example solely for deployments behind a trusted proxy:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Never enable it blindly when the backend is directly exposed to the Internet and clients can spoof `X-Forwarded-Proto`. Evaluate the trust boundary first.

## 7. Java 17+ Spring Boot WebFlux Sample Project

Uses **Java 17+**, **Spring Boot 3.5.16**, compatible Gradle 8.x, and Spring Boot BOM-managed Spring Security reactive. Do not add `spring-boot-starter-web` if you want to observe the exact WebFlux pipeline. For production, track active patches and supported release branches.

Demo accounts:

| Username | Local demo password | Role |
| --- | --- | --- |
| `reader` | `reader-pass` | `ROLE_USER` |
| `admin` | `admin-pass` | `ROLE_USER`, `ROLE_ADMIN` |

**Never hardcode real credentials in source or frontends**. HTTP Basic Base64 is not encryption; use HTTP localhost only for learning—production requires HTTPS/TLS and a proper identity store.

Layout:

~~~text
webflux-endpoint-headers/
├── settings.gradle
├── build.gradle
├── src/main/java/example/headers/HeadersApplication.java
├── src/main/java/example/headers/SecurityConfig.java
├── src/main/java/example/headers/EndpointHeadersWriter.java
├── src/main/java/example/headers/Endpoints.java
├── src/test/java/example/headers/HeaderPolicyTest.java
└── src/test/java/example/headers/HstsWriterTest.java
~~~

### 7.1. settings.gradle

~~~groovy
rootProject.name = 'webflux-endpoint-headers'
~~~

### 7.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 7.3. HeadersApplication.java

~~~java
package example.headers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HeadersApplication {
    public static void main(String[] args) {
        SpringApplication.run(HeadersApplication.class, args);
    }
}
~~~

### 7.4. EndpointHeadersWriter.java

~~~java
package example.headers;

import org.springframework.http.HttpHeaders;
import org.springframework.security.web.server.header.ServerHttpHeadersWriter;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class EndpointHeadersWriter
        implements ServerHttpHeadersWriter {

    public static final String API_CSP =
            "default-src 'none'; base-uri 'none'; "
            + "object-src 'none'; frame-ancestors 'none'";

    public static final String HELP_CSP =
            "default-src 'none'; style-src 'self'; "
            + "img-src 'self'; base-uri 'none'; "
            + "object-src 'none'; frame-ancestors 'none'";

    public static final String API_PERMISSIONS =
            "camera=(), microphone=(), geolocation=()";

    @Override
    public Mono<Void> writeHttpHeaders(ServerWebExchange exchange) {
        return Mono.fromRunnable(() -> {
            String path = exchange.getRequest()
                    .getPath().pathWithinApplication().value();

            HttpHeaders h = exchange.getResponse().getHeaders();

            // Apply strict fallback CSP across all paths and error responses.
            h.set("Content-Security-Policy",
                    "/ui/help".equals(path) ? HELP_CSP : API_CSP);

            if (path.startsWith("/api/")) {
                h.set("Permissions-Policy", API_PERMISSIONS);
                h.set("X-Robots-Tag", "noindex, nofollow");
            }
        });
    }
}
~~~

Explanation:

- Writer uses **`ServerWebExchange`**, not Servlet `HttpServletResponse`.
- **`Mono.fromRunnable`** mutates headers when the reactive publisher is subscribed during the commit lifecycle; never call `subscribe()`/`block()`.
- CSP is selected by **path**, while **values come strictly from server-controlled constants**, never reflecting query params, `Host`, `Origin`, or usernames.
- Every path except `/ui/help` receives the strict CSP, including 401/403/`denyAll` responses.
- `/api/**` adds `Permissions-Policy` and `X-Robots-Tag`. Those headers do not grant permissions.
- Default `Cache-Control` is left untouched since this lesson has no public-cached static assets.
- If adding custom error handlers, verify headers inside `SecurityWebFilterChain` as well.

### 7.5. SecurityConfig.java

~~~java
package example.headers;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.header.ReferrerPolicyServerHttpHeadersWriter.ReferrerPolicy;
import org.springframework.security.web.server.header.XFrameOptionsServerHttpHeadersWriter;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER").build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN").build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    EndpointHeadersWriter endpointHeadersWriter() {
        return new EndpointHeadersWriter();
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            EndpointHeadersWriter endpointWriter) {

        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/public/ping", "/ui/help")
                                .permitAll()
                        .pathMatchers("/api/admin/**")
                                .hasRole("ADMIN")
                        .pathMatchers("/api/**")
                                .authenticated()
                        .anyExchange().denyAll())
                .headers(headers -> headers
                        .hsts(hsts -> hsts
                                .maxAge(Duration.ofDays(30))
                                .includeSubdomains(false)
                                .preload(false))
                        .frameOptions(frame -> frame
                                .mode(
                                    XFrameOptionsServerHttpHeadersWriter
                                            .Mode.DENY))
                        .referrerPolicy(referrer -> referrer
                                .policy(ReferrerPolicy.NO_REFERRER))
                        .writer(endpointWriter))
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }
}
~~~

**Reading the configuration accurately:**

1. `authorizeExchange` enforces URL permissions; the admin rule precedes `/api/**`.
2. `HeaderSpec` adds settings **without calling `disable()`**, so nosniff and cache baselines continue to apply.
3. HSTS has a 30-day `maxAge` without `includeSubDomains`/`preload`, emitted only when the request is perceived as secure.
4. `X-Frame-Options: DENY` and CSP `frame-ancestors 'none'` align consistently.
5. `Referrer-Policy: no-referrer` is explicitly configured to minimize URL leakage.
6. `EndpointHeadersWriter` applies endpoint-specific CSP/`Permissions-Policy` values.
7. HTTP Basic returns 401 on missing/wrong credentials; missing roles return 403, and both must be header-tested.
8. The demo uses GET only and leaves CSRF enabled; when adding POSTs, evaluate CSRF per credential model.

### 7.6. Endpoints.java

~~~java
package example.headers;

import java.security.Principal;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class Endpoints {

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping(value = "/ui/help",
            produces = MediaType.TEXT_HTML_VALUE)
    public Mono<String> help() {
        return Mono.just(
                "<!doctype html><html lang=\"en\">"
                + "<head><title>Help</title></head>"
                + "<body><h1>Help</h1></body></html>");
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> profile(Mono<Principal> principal) {
        return principal.map(p -> Map.of("username", p.getName()));
    }

    @GetMapping("/api/admin/report")
    public Mono<Map<String, String>> report() {
        return Mono.just(Map.of("report", "ok"));
    }
}
~~~

The help HTML contains no inline scripts or CSS, so `HELP_CSP` does not break functionality. When adding scripts, design `script-src`, `connect-src`, and nonces/hashes instead of loosening wildcards indiscriminately.

### 7.7. Running

~~~bash
gradle bootRun
~~~

Requires JDK 17+, compatible Gradle, and Maven Central access. Default server runs at **http://localhost:8080**. Because this is local HTTP, do not expect HSTS there. To verify HSTS in production, inspect responses at the public HTTPS edge.

## 8. Verifying Headers with curl Instead of Trusting Config Alone

### 8.1. Call GET and Print Response Headers

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Or print headers while discarding the **GET** body:

~~~bash
curl -sS -D - -o /dev/null \
  http://localhost:8080/public/ping
~~~

Do not treat **`curl -I`** output as complete proof for GET, because `-I` sends HEAD. GET and HEAD can traverse different authorization/mapping paths.

Expected key headers on local HTTP:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Content-Security-Policy: default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'
~~~

`Date`, `Content-Length`, `Transfer-Encoding`, and header order may vary; this illustrates the values to check, not output copied from a live server.

### 8.2. GET the HTML Page

~~~bash
curl -sS -D - -o /dev/null \
  http://localhost:8080/ui/help
~~~

Expected:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html
X-Frame-Options: DENY
Content-Security-Policy: default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'
~~~

`Content-Type` may include `charset=UTF-8`; match the media type rather than exact byte strings. The HTML page receives a **different CSP** than JSON—the key behavior to verify.

### 8.3. Unauthenticated API: 401 Must Still Carry Headers

~~~bash
curl -sS -D - -o /dev/null \
  http://localhost:8080/api/me
~~~

Expected **401**, `WWW-Authenticate: Basic` with the framework's realm, and headers:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Content-Security-Policy: default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'
Permissions-Policy: camera=(), microphone=(), geolocation=()
X-Robots-Tag: noindex, nofollow
~~~

**Do not hardcode the default Basic challenge realm** as a long-term contract unless configured explicitly. Assert the right `WWW-Authenticate` scheme, status code, and that the API CSP still appears on 401.

### 8.4. Authenticated API: 200

~~~bash
curl -sS -D - -o /dev/null \
  -u reader:reader-pass \
  http://localhost:8080/api/me
~~~

Expected 200, API CSP, `no-store`, `nosniff`, `Permissions-Policy`. Body of a valid authenticated GET:

~~~json
{"username":"reader"}
~~~

### 8.5. Insufficient Role: 403

~~~bash
curl -sS -D - -o /dev/null \
  -u reader:reader-pass \
  http://localhost:8080/api/admin/report
~~~

Expected **403 Forbidden** along with API CSP, `no-store`, `nosniff`, and `Permissions-Policy`. If CSP had been set only in a controller, this 403 path would miss the header; placing the writer in the security chain and testing catches this.

### 8.6. Authorized Admin: 200

~~~bash
curl -sS -D - -o /dev/null \
  -u admin:admin-pass \
  http://localhost:8080/api/admin/report
~~~

Expected 200 with body:

~~~json
{"report":"ok"}
~~~

### 8.7. Never Log Secrets During Verification

Examples use demo passwords, never real accounts. Running `curl -v` or tracing requests can expose `Authorization`, `Cookie`, `Set-Cookie`, and tokens. Never paste output containing those values into chats, tickets, or public logs. Record only **status, header names, profiles, and match/mismatch outcomes**, omitting raw credentials from reports.

In PowerShell, use **`curl.exe`**; backslash line continuations above are for Bash.

## 9. Testing Actual HTTP Behavior with WebTestClient

**Verify both status and headers**, because unauthenticated requests may be rejected by `SecurityWebFilterChain` before any controller executes.

File **src/test/java/example/headers/HeaderPolicyTest.java**:

~~~java
package example.headers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class HeaderPolicyTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointHasBaselineAndApiCsp() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "Content-Security-Policy",
                        EndpointHeadersWriter.API_CSP)
                .expectHeader().valueEquals(
                        "X-Content-Type-Options", "nosniff")
                .expectHeader().valueEquals(
                        "X-Frame-Options", "DENY")
                .expectHeader().valueEquals(
                        "Referrer-Policy", "no-referrer")
                .expectHeader().value(HttpHeaders.CACHE_CONTROL,
                        v -> assertTrue(v.contains("no-store")))
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void htmlEndpointHasDifferentCsp() {
        client.get().uri("/ui/help")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_HTML)
                .expectHeader().valueEquals(
                        "Content-Security-Policy",
                        EndpointHeadersWriter.HELP_CSP);
    }

    @Test
    void unauthorizedResponseStillHasHeaders() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().exists(
                        HttpHeaders.WWW_AUTHENTICATE)
                .expectHeader().valueEquals(
                        "Content-Security-Policy",
                        EndpointHeadersWriter.API_CSP)
                .expectHeader().valueEquals(
                        "Permissions-Policy",
                        EndpointHeadersWriter.API_PERMISSIONS)
                .expectHeader().value(
                        HttpHeaders.CACHE_CONTROL,
                        v -> assertTrue(v.contains("no-store")));
    }

    @Test
    void authenticatedResponseHasApiHeaders() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth(
                        "reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "Content-Security-Policy",
                        EndpointHeadersWriter.API_CSP)
                .expectHeader().valueEquals(
                        "X-Robots-Tag", "noindex, nofollow")
                .expectBody()
                .jsonPath("$.username").isEqualTo("reader");
    }

    @Test
    void forbiddenResponseStillHasHeaders() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth(
                        "reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(
                        "Content-Security-Policy",
                        EndpointHeadersWriter.API_CSP)
                .expectHeader().valueEquals(
                        "Permissions-Policy",
                        EndpointHeadersWriter.API_PERMISSIONS);
    }

    @Test
    void adminGets200WithSamePolicy() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth(
                        "admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "Content-Security-Policy",
                        EndpointHeadersWriter.API_CSP)
                .expectBody()
                .jsonPath("$.report").isEqualTo("ok");
    }

    @Test
    void unlistedUrlIsDeniedWithFallbackCsp() {
        client.get().uri("/unlisted")
                .headers(h -> h.setBasicAuth(
                        "reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(
                        "Content-Security-Policy",
                        EndpointHeadersWriter.API_CSP);
    }

    @Test
    void localHttpHasNoHstsHeader() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().doesNotExist(
                        HttpHeaders.STRICT_TRANSPORT_SECURITY);
    }

    @Test
    void responseDoesNotAccidentallyDuplicateCsp() {
        EntityExchangeResult<byte[]> result =
                client.get().uri("/public/ping")
                        .exchange()
                        .expectStatus().isOk()
                        .expectBody()
                        .returnResult();

        assertEquals(1, result.getResponseHeaders()
                .getOrEmpty("Content-Security-Policy").size());
    }
}
~~~

Run:

~~~bash
gradle test
~~~

**Expected result:** all 9 tests in `HeaderPolicyTest` PASS when code, JDK, and dependencies are properly prepared. This is an expectation from the configuration, **not an executed log**.

### 9.1. Why Test 401 and 403?

401 requests may never reach controllers; 403s may come from authorization or CSRF filters. If headers are set only inside success handlers, error responses easily omit policies. `WebTestClient` traverses the `WebFilter`s and inspects the exact headers emitted by the test server, catching regressions in the error pipeline.

### 9.2. Why Count CSP Headers?

If both a gateway and the app emit CSP, browsers enforce multiple policies and can break the UI. Counting headers in app integration tests catches in-app duplicates, **while you must still inspect responses at the public edge** since proxies/CDNs can inject headers afterward.

### 9.3. Why Check `no-store` Instead of the Entire Cache-Control String?

`Cache-Control` carries multiple directives whose order may be normalized. The crucial business requirement is that **`no-store` is present on private data**. For stricter compliance checks, parse individual directives rather than doing context-free substring matches.

## 10. Testing HSTS with MockServerWebExchange

The demo runs on local HTTP, so **the HSTS secure branch cannot be confirmed solely by curling local HTTP**. Testing the standard writer with `MockServerWebExchange` across both schemes provides valuable unit verification.

File **src/test/java/example/headers/HstsWriterTest.java**:

~~~java
package example.headers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.header.StrictTransportSecurityServerHttpHeadersWriter;
import reactor.test.StepVerifier;

class HstsWriterTest {

    private StrictTransportSecurityServerHttpHeadersWriter writer() {
        StrictTransportSecurityServerHttpHeadersWriter hsts =
                new StrictTransportSecurityServerHttpHeadersWriter();
        hsts.setMaxAge(Duration.ofDays(30));
        hsts.setIncludeSubDomains(false);
        hsts.setPreload(false);
        return hsts;
    }

    @Test
    void writesHstsOnHttpsOnly() {
        MockServerWebExchange exchange =
                MockServerWebExchange.from(
                        MockServerHttpRequest.get(
                                "https://api.example.org/api/me"));

        StepVerifier.create(writer().writeHttpHeaders(exchange))
                .verifyComplete();

        assertEquals("max-age=2592000",
                exchange.getResponse().getHeaders()
                        .getFirst(
                                HttpHeaders.STRICT_TRANSPORT_SECURITY));
    }

    @Test
    void doesNotWriteHstsOnHttp() {
        MockServerWebExchange exchange =
                MockServerWebExchange.from(
                        MockServerHttpRequest.get(
                                "http://api.example.org/api/me"));

        StepVerifier.create(writer().writeHttpHeaders(exchange))
                .verifyComplete();

        assertNull(exchange.getResponse().getHeaders()
                .getFirst(HttpHeaders.STRICT_TRANSPORT_SECURITY));
    }
}
~~~

Running `gradle test` across the whole project is expected to yield **11 passing tests** (9 HTTP tests and 2 HSTS writer tests). The `MockExchange` tests verify **standard writer logic**, not that the production proxy emits HSTS. End-to-end verification must go through a **public TLS URL**.

### 10.1. Testing Real HTTPS Through a Proxy

Assuming your organization deployed a real domain with a valid TLS certificate:

~~~bash
curl -sS -D - -o /dev/null \
  https://api.example.org/api/me
~~~

Replace `api.example.org` with your real service hostname. Expect `Strict-Transport-Security` with your deployment's `max-age` alongside the other security headers. Never use **`curl -k`** to skip certificate verification in production tests.

If 401 is returned due to missing credentials, still verify HSTS, `no-store`, `nosniff`, and CSP; testing only 200 leaves security entry points unverified. Test 403 with a valid account lacking the role and 200 with an authorized test account too.

## 11. Verifying Final Values Behind Gateways, CDNs, and Browsers

**Response path:**

~~~text
WebFlux SecurityWebFilterChain
        |
        v
Controller/RouterFunction
        |
        v
Spring HTTP response
        |
        v
Ingress / NGINX / API gateway / WAF / CDN
        |
        v
Browser receives security response headers
~~~

Intermediate layers can:

- Add HSTS at the edge and strip backend values.
- Overwrite or delete `Cache-Control`.
- Inject their own CSP or `X-Frame-Options`, creating conflicting policies.
- Add/edit headers on 200s while missing 4xx/5xx responses.
- Rewrite `Location` to `http` instead of `https`.
- Alter `Content-Type`, `Vary`, CORS, or `Set-Cookie`.

To observe **actual values**:

1. Inspect headers on the internal app port if permitted.
2. Inspect headers through the public HTTPS URL and proxy.
3. Compare 200/401/403 across both HTML and JSON paths.
4. Confirm **no duplicate values**, especially for CSP, HSTS, and `Access-Control-Allow-Origin`.
5. For personal data, check `Cache-Control`, `Pragma`, and `Expires` on real responses.
6. Check redirect `Location` headers and `Secure`/`HttpOnly`/`SameSite` cookie flags when sessions exist.
7. Use DevTools Network/Console to inspect CSP violations and real browser behavior.
8. If using caches/CDNs, verify `Vary`/TTL and bypass caching while debugging.

**Never treat screenshots of source config as sufficient evidence.** Good verification evidence includes URL, HTTP method, status, sanitized header names/values, environment, and the tested proxy route.

### 11.1. HTML with Real Scripts and CSP

If an app uses an SPA with scripts from `self` or an approved CDN:

- Audit network traffic and define accurate `script-src`, `connect-src`, `img-src`, `font-src`, and `style-src`.
- Run CSP Report-Only in staging to analyze violations before enforcing.
- Prefer nonces/hashes for legitimate inline scripts rather than opening `unsafe-inline`.
- Never assume CSP eliminates all XSS: escaping, sanitization, and input validation remain essential.
- Never reflect attacker-chosen hostnames/origins into CSP or `frame-ancestors`.

### 11.2. Static Assets and Downloads Differ from JSON APIs

Content-hashed static files can be public-cached long-term, provided they hold no sensitive data; avoid overriding caching app-wide. File download endpoints need accurate `Content-Type`, sanitized/encoded `Content-Disposition` filenames, `nosniff`, and access-appropriate cache policies. User-uploaded files may need scanning/attachment disposition rather than inline rendering. Never interpolate unsanitized filenames into response headers.

### 11.3. Login, Logout, and 401/403

- HTTP Basic 401 requires the proper **`WWW-Authenticate`** scheme; custom header writers must never remove that challenge.
- Logged-in users lacking roles typically receive 403; preserve protective headers on error responses.
- Unauthenticated form logins may return a 302 redirect rather than 401; verify headers and `Location` too.
- Logout may use `Clear-Site-Data` on dedicated endpoints when aligned with your threat model; never attach `Clear-Site-Data` to every response.
- Proxy 5xx responses may bypass `SecurityWebFilterChain`; test those at the gateway too.
- CSP `frame-ancestors` is not CORS; `Referrer-Policy` is not CSRF.

## 12. Common Mistakes and How to Handle Them

| Mistake | Consequence | Proper approach |
| --- | --- | --- |
| `headers.disable()` just to add CSP | Loses security defaults | Use `headers.writer`, preserve baseline |
| Setting headers only in Controllers | 401/403 missing CSP/cache headers | Use `ServerHttpHeadersWriter` in `SecurityWebFilterChain` |
| Seeing no HSTS on local HTTP and calling it a bug | Confusing secure vs. insecure requests | Unit-test HTTPS writer and test public HTTPS |
| Trusting `X-Forwarded-Proto` from Internet clients | Spoofed scheme/trust | Edge strip/overwrite + trusted proxy |
| Enabling `preload`/`includeSubDomains` before TLS audit | Can break subdomain access | Phased, controlled rollout |
| CSP `default-src *` and `unsafe-inline` | Weakens XSS protection | Minimal CSP + nonces/hashes |
| CSP `frame-ancestors` differs from `X-Frame-Options` | Conflicting framing policies | Test clickjacking on both modern and legacy browsers |
| Public cache on `/api/me` | Cache data leak | `no-store` and audit CDN |
| Checking `Content-Type` without `nosniff` | Higher MIME confusion risk | Verify both `Content-Type` and `nosniff` |
| Treating `Permissions-Policy` as a role | Bypasses authorization | Use `hasRole`/`hasAuthority` and ownership checks |
| Treating `X-Robots-Tag` as blocking attackers | Data remains accessible | Enforce real authentication/authorization |
| Duplicate headers injected at gateway | Unintended browser policy intersection | Single policy owner, test at the edge |
| Using `curl -I` to verify GET | HEAD may differ from GET | Use `curl -D - -o /dev/null` with GET |
| Interpolating request `Origin`/`Host` into CSP | Policy injection or bypass | Use server-controlled constants/allowlists |
| Disabling CSRF because POST got 403 | Exposes browser credentials | Test CSRF separately for unsafe methods |
| Checking CSP on 200 and stopping | Misses error pipeline | Test 200, 401, 403, and 5xx as needed |
| Logging `Authorization`/cookies while debugging | Credential leak | Redact logs, use test fixtures |
| Changing paths without updating writer matchers | Wrong header profile applied | Test final paths after nesting/rewrites |

### 12.1. With Multiple SecurityWebFilterChain Beans

When splitting API and browser chains, check `securityMatcher` and `@Order`: a request traverses only the matching chain and does not inherit header writers from other chains. Even a public chain needs its own baseline headers if it does not share a common configuration.

### 12.2. ServerWebExchangeDelegatingServerHttpHeadersWriter

Spring Security also provides **`ServerWebExchangeDelegatingServerHttpHeadersWriter`**, running a writer whenever a **`ServerWebExchangeMatcher`** matches:

~~~java
new ServerWebExchangeDelegatingServerHttpHeadersWriter(
        matcher, delegateWriter);
~~~

This is an API illustration snippet—**`matcher` and `delegateWriter` must be constructed** in your app and are not pre-existing variables from the sample project. With many path-specific policies, matcher-based delegation can be cleaner than a long if/else writer. Either way, test exact paths/methods and preserve baseline headers.

## 13. Review, Staging, and Production Checklist

1. Inventory exact **methods/paths**, content types (HTML/JSON/download), and effective security chains.
2. Confirm `HeaderSpec` does not disable useful defaults.
3. Tailor CSP per endpoint without unjustified wildcards.
4. Keep `X-Frame-Options` and CSP `frame-ancestors` consistent.
5. Set `Referrer-Policy` to an approved value.
6. Ensure personal data and error responses include `Cache-Control: no-store`.
7. Verify `nosniff` and accurate `Content-Type`.
8. Remember API `Permissions-Policy` is a browser policy, not access control.
9. Never construct header values from untrusted input.
10. Verify HSTS over real HTTPS with proper `max-age` and subdomain scope.
11. Trust reverse proxy headers only after the proxy strips/overwrites client headers.
12. Verify HTTP→HTTPS redirects and `Location` headers in deployment.
13. Test **actual GET**, never confusing HEAD.
14. Test 200, 401, 403, and gateway 404/5xx as applicable.
15. Check for duplicate CSP, HSTS, and ACAO at the edge.
16. Verify CORS/CSRF if frontends send cross-origin cookies/credentials.
17. Separate static asset caching from private data without losing `Vary`.
18. Verify session cookie flags when form login is used.
19. Keep secrets, session IDs, and `Authorization` headers out of tickets/logs.
20. Maintain rollback plans for CSP/HSTS and monitor CSP violations post-deploy.

## 14. Self-Assessment Exercises

1. Why doesn't having CSP in source config prove the browser receives CSP?
2. Which headers are typically provided out of the box by Spring Security WebFlux? Which require explicit enabling?
3. Why shouldn't you use `headers.disable()` when merely adding one policy?
4. What type does `ServerHttpHeadersWriter` return, and why shouldn't you call `subscribe()` yourself?
5. If `/ui/help` serves HTML while `/api/me` returns JSON, should both endpoints share the exact same CSP?
6. Why must `X-Frame-Options: DENY` align with `frame-ancestors 'none'`?
7. When a user omits Basic credentials, should the header writer be verified on the 401 response?
8. When `reader` lacks `ROLE_ADMIN` and gets 403, how do you verify CSP is actually present?
9. Why shouldn't HSTS be emitted over HTTP?
10. Behind an HTTPS reverse proxy, how must `X-Forwarded-Proto` be checked along the trust boundary?
11. How do `includeSubDomains`/`preload` impact hosts not yet supporting HTTPS?
12. Why doesn't `curl -I` replace a GET test?
13. Does `Cache-Control: no-store` mean users no longer need to log in?
14. Why don't `X-Robots-Tag` and `Permissions-Policy` replace authorization?
15. If a CDN injects a second CSP, how might browsers handle it?
16. Why verify headers at the public edge rather than only on localhost?
17. When 200 responses have proper CSP yet 401s lack it, where should the policy be fixed?
18. Can a public, content-hashed file use long-lived caching? Under what conditions?

**Suggested answers:** (1) proxies/filters/error handlers may alter responses; (2) cache/nosniff/frame/secure-only HSTS are defaults, CSP is app-defined; (3) loses the baseline; (4) `Mono<Void>` subscribed by the framework; (5) no, tailor to required resources; (6) consistent clickjacking defense without conflict; (7) yes; (8) `WebTestClient` or `curl` checking status + response headers; (9) browsers only trust HSTS over HTTPS; (10) trust only controlled proxies; (11) can render HTTP-only subdomains inaccessible; (12) HEAD has different semantics than GET; (13) no; (14) browser/crawler policies differ from user permissions; (15) multiple policies may apply simultaneously/conflict; (16) the edge emits the final response; (17) configure inside the security header writer or proper edge policy; (18) yes, if non-sensitive and URL is immutable/properly hashed.

## 15. Official References

- Spring Security 6.5 — WebFlux Security HTTP Response Headers: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html
- Spring Security 6.5 — `ServerHttpSecurity.HeaderSpec` Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HeaderSpec.html
- Spring Security 6.5 — `ServerHttpHeadersWriter` Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/header/ServerHttpHeadersWriter.html
- Spring Security 6.5 — `StrictTransportSecurityServerHttpHeadersWriter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/header/StrictTransportSecurityServerHttpHeadersWriter.html
- Spring Security 6.5 — `ServerWebExchangeDelegatingServerHttpHeadersWriter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/header/ServerWebExchangeDelegatingServerHttpHeadersWriter.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- MDN — HTTP Strict Transport Security: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security
- MDN — Content Security Policy: https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP
- MDN — Cache-Control: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control
- OWASP — HTTP Headers Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html

**Conclusion:** To customize headers per endpoint in Spring Security Reactive, keep **`ServerHttpSecurity`'s baseline headers**, attach a **`ServerHttpHeadersWriter`** conditioned on path/response type, define clear CSP/cache/clickjacking policies, and test real HTTP responses across **200/401/403**. **HSTS is a host-level HTTPS policy** that must be verified at the public TLS edge behind proxies, not solely on local HTTP. Combining `WebTestClient`, mock HTTPS writers, `curl`, and DevTools proves headers arrive with the intended values.