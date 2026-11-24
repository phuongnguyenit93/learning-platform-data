# Default Security Headers in Spring Security Reactive

> **Context:** Spring Security 6.x on Spring WebFlux, Java 17+, Spring Boot 3.3.x. This lesson focuses on the **HTTP response security headers automatically added by Spring Security WebFlux**, their meaning, conditions under which they appear, how to keep/customize each header, and how to test them in a reactive application. The example syntax uses Spring Boot 3.3.13 to illustrate the API; in real deployments, upgrade to a supported and security-patched version of Spring Security/Spring Framework.

## 1. What Are Security Headers?

Every HTTP response includes a set of headers that tell browsers and clients how to handle the content. Some headers establish **protective constraints on the browser side**:

- Do not store sensitive copies in cache.
- Do not guess a content type that differs from `Content-Type`.
- Restrict the page from being embedded in an `iframe`.
- Encourage the browser to use HTTPS only for hosts that have established HSTS.
- Restrict or specify allowed sources for scripts, styles, images, frames, camera, geolocation, etc., **when the application explicitly configures** the corresponding policies.

In Spring Security WebFlux, these headers are configured via `ServerHttpSecurity.headers(...)` and written by `ServerHttpHeadersWriter` implementations within the `SecurityWebFilterChain` system.

```text
HTTP request
    |
    v
WebFlux / WebFilterChainProxy
    |
    +--> SecurityWebFilterChain (selected by securityMatcher)
             |
             +--> Spring Security header writers
             |       +-- Cache-Control / Pragma / Expires
             |       +-- X-Content-Type-Options
             |       +-- X-Frame-Options
             |       +-- X-XSS-Protection
             |       +-- HSTS (only when request is considered secure)
             |
             +--> Authentication / Authorization / CSRF ...
             |
             v
         Controller or 401/403 error
             |
             v
         HTTP response + headers if allowed by chain/response
```

Crucial point: **security headers are not authentication or authorization mechanisms**. `X-Frame-Options: DENY` does not by itself block `GET /admin` for a user lacking permissions. Nor does `Strict-Transport-Security` enable TLS on Netty or force Spring Security to redirect all HTTP requests to HTTPS. Those layers must be configured separately.

### Easily Confused Terms

| Term | Role | Example |
|---|---|---|
| **Response header** | Returned by server, read by client | `X-Content-Type-Options: nosniff` |
| **Request header** | Sent by client to server | `Accept: application/json`, `Authorization: Bearer ...` |
| **SecurityWebFilterChain** | Filter set applied to WebFlux requests | Bean returning `SecurityWebFilterChain` |
| **Header writer** | Component that creates/adds response headers | `XFrameOptionsServerHttpHeadersWriter` |
| **HTTP security policy** | Rules granting route, user, method access | `authorizeExchange(...).hasRole("ADMIN")` |
| **HTTPS redirect** | Redirect response from HTTP to HTTPS | `redirectToHttps(Customizer.withDefaults())` |
| **HSTS** | Browser remembers to use HTTPS for the host going forward | `Strict-Transport-Security` |

The presence of a header in a response does not prove that an application is completely secure. Headers are just one layer of defense in a model that includes HTTPS, authorization, CSRF, XSS prevention, cookie management, input validation, and patching.

## 2. Default Header List in Spring Security WebFlux

According to the default list in the Spring Security 6.x Javadoc for `ServerHttpSecurity.headers(...)`, responses passing through the Security chain typically receive:

```http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 0
Strict-Transport-Security: max-age=31536000 ; includeSubDomains
```

**Critical note:** the `Strict-Transport-Security` header **is only added when the request is recognized as HTTPS/secure**. Therefore, responses on `http://localhost:8080` typically contain the other six headers, **without** HSTS. This is not a default configuration bug.

Detailed table:

| Header | Default value per Spring Security 6.x list | Purpose | Conditions/notes |
|---|---|---|---|
| `Cache-Control` | `no-cache, no-store, max-age=0, must-revalidate` | Prevent caches from accidentally storing sensitive responses | Application may set its own value for public resources |
| `Pragma` | `no-cache` | Legacy client/cache compatibility | Accompanies default cache policy |
| `Expires` | `0` | Indicates response is already expired for caching | Not a token/session expiration time |
| `X-Content-Type-Options` | `nosniff` | Restricts MIME/content sniffing | Must still send accurate `Content-Type` for resources |
| `X-Frame-Options` | `DENY` | Mitigates clickjacking via iframe | Change to `SAMEORIGIN` when same-origin embedding is evaluated and required |
| `X-XSS-Protection` | `0` | Disables the unreliable legacy XSS Auditor | Does **not** mean XSS protection is already handled |
| `Strict-Transport-Security` | `max-age=31536000 ; includeSubDomains` | HSTS: browser uses HTTPS after receiving policy | **Only on secure requests**; `preload` is not default |

**Do not conclude that every HTTP response in the real world always has the exact table above.** `SecurityWebFilterChain` configuration, proxies/CDNs, Spring Security version, specific resources, additional filters, or application-set headers can alter the result. Verify against the **running dependency** with integration tests and actual HTTP responses.

### Special Case: Referrer-Policy by Version and Documentation

There is an easy point to misunderstand when looking only at documentation:

- The default headers list in the Spring Security 6.x `ServerHttpSecurity.headers(...)` Javadoc includes the headers above, and **does not list `Referrer-Policy`**.
- The **Spring Security 6.5 WebFlux** reference guide describes `Referrer-Policy: no-referrer` as a default behavior of the reactive branch.
- The **Servlet** documentation in similar versions states that `Referrer-Policy` is not added automatically.

Therefore, **do not assume** from a general table alone whether `Referrer-Policy` is present or absent across all versions. To guarantee a policy in a deployment, **configure `referrerPolicy(...)` explicitly** and test the actual HTTP responses. Do not use documentation differences as an excuse to disable other protective headers.

### Not Every Security-Related Header Is Added by Default

Spring Security provides APIs for additional configuration, but **does not emit all of the following policies by default**:

- `Content-Security-Policy` (CSP), `Content-Security-Policy-Report-Only`.
- `Permissions-Policy`.
- `Cross-Origin-Opener-Policy` (COOP).
- `Cross-Origin-Embedder-Policy` (COEP).
- `Cross-Origin-Resource-Policy` (CORP).
- `Feature-Policy` (legacy, replaced by Permissions-Policy in many contexts).
- `Access-Control-Allow-Origin`/`Access-Control-Allow-Methods`: these are CORS response headers **dependent on the request and CORS policy**, not part of the security defaults list above.
- `Set-Cookie: ...; Secure; HttpOnly; SameSite=...`: managed by session/cookie/authentication/related frameworks, not automatically present just by calling `headers(...)`.

In your exact setup, an additional header may be added by another framework or a reverse proxy; distinguish **who owns the policy** to avoid one layer overwriting another.

## 3. Cache-Control, Pragma, Expires: Preventing Caching of Private Data

### 3.1 Why Is Caching Disabled by Default?

Suppose a user logs in, loads a bank statement page, and then logs out. If a browser or proxy stores a copy of that page as a public cache, another person reusing the machine or another client could view data that should have been protected.

Spring Security uses by default:

```http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
```

- `no-store`: instructs caches not to store any copy of the response.
- `no-cache`: allows some caches to store the response, but requires revalidation before reuse (per HTTP semantics). **Not strictly synonymous with "do not store"**; `no-store` is the critical directive in this policy.
- `max-age=0`: the response is immediately considered stale.
- `must-revalidate`: once stale, caches must revalidate via a valid mechanism.
- `Pragma` and `Expires` provide fallback support for older clients/proxies.

These directives apply to the **response**; they do not automatically delete cookies, terminate sessions, revoke JWTs, or prevent all forms of client-side storage. After logout, the backend must still invalidate sessions/tokens according to policy.

### 3.2 Public Resources That Can Be Cached

A versioned JavaScript file, public image, or genuinely cacheable page can use:

```http
Cache-Control: public, max-age=300
```

Spring Security allows the application to **write its own Cache-Control** for that response instead of the default. For example, in WebFlux:

```java
@GetMapping("/api/public-cache")
public Mono<ResponseEntity<String>> cacheablePublic() {
    return Mono.just(
        ResponseEntity.ok()
            .header(HttpHeaders.CACHE_CONTROL, "public, max-age=120")
            .body("public-cache"));
}
```

This is an **illustrative method**, requiring imports for `GetMapping`, `Mono`, `ResponseEntity`, and `HttpHeaders`. The full demo in section 8 contains a corresponding method.

**Do not** return `public` cache headers for resources containing user-specific data, cookies/sessions, permission results, or tokens. For non-public content, prefer keeping `no-store`. If a reverse proxy caches by route, add appropriate `Vary` policies and cache keys; do not rely on Spring Security headers alone to fix a misconfigured CDN cache.

### 3.3 When Can the Cache Header Writer Be Disabled?

Spring Security allows:

```java
.headers(headers -> headers
    .cache(cache -> cache.disable()))
```

This is a **DSL snippet** and should not be copied into production just to cache a static file. Disabling the `cache` writer can affect **every response belonging to that chain**. Usually, it is preferable to set a dedicated `Cache-Control` on only the public endpoints/resources or configure a specialized resource chain.

## 4. X-Content-Type-Options: nosniff

`X-Content-Type-Options: nosniff` instructs the browser not to "guess" the content type in supported contexts. Historically, a server might serve a user-uploaded file with an incorrect MIME type, and the browser would infer it as JavaScript/HTML, causing untrusted code to execute.

```http
Content-Type: application/json
X-Content-Type-Options: nosniff
```

These two headers serve two different purposes:

1. `Content-Type`: the server declares that the data is JSON.
2. `X-Content-Type-Options`: restricts the browser from sniffing it into another content type.

**Do not assume `nosniff` automatically assigns a correct Content-Type.** Always send the standard MIME type for JavaScript/CSS, do not serve untrusted uploads on the same origin where a browser might treat them as script/HTML; consider a separate domain for user-uploaded files and `Content-Disposition: attachment` where appropriate.

If disabling it is required:

```java
.headers(headers -> headers
    .contentTypeOptions(options -> options.disable()))
```

Use this only when a genuine compatibility constraint has been identified and the risks are understood. This lesson **does not recommend** turning off `nosniff` to work around MIME errors: fixing the MIME type is safer.

## 5. X-Frame-Options: DENY

### 5.1 Clickjacking

An attacker can embed your sensitive page inside an `iframe` and overlay a UI layer so the user thinks they are clicking a harmless button while actually interacting with the sensitive page.

Default:

```http
X-Frame-Options: DENY
```

This means browsers supporting this header will not render the response inside a frame. This policy is useful for login pages, account management pages, admin consoles, transactions, etc.

When an application **needs** to embed certain pages in a **same-origin** iframe, you can choose:

```java
.headers(headers -> headers
    .frameOptions(frame -> frame
        .mode(XFrameOptionsServerHttpHeadersWriter.Mode.SAMEORIGIN)))
```

Import:

```java
import org.springframework.security.web.server.header.XFrameOptionsServerHttpHeadersWriter;
```

**SAMEORIGIN does not mean "allow any iframe within the organization".** It is constrained by the same-origin rule (scheme + host + port). Another website on a different subdomain or different scheme may not be considered same-origin.

### 5.2 CSP frame-ancestors Is More Flexible

When you need to allow another domain to embed a page, `X-Frame-Options` lacks modern syntax for allowlisting multiple origins. Use **Content-Security-Policy: frame-ancestors ...** to declare a policy for trusted origins:

```http
Content-Security-Policy: frame-ancestors 'self' https://portal.example.com
```

Notes:

- CSP is not automatically generated just because `X-Frame-Options` is present.
- Older and newer browsers have varying levels of support; verify the combination of CSP/`X-Frame-Options` when cross-origin embedding is needed.
- Do not drop `DENY` globally just to fix a single embed case; consider a route-specific policy/chain and threat model.
- `frame-ancestors` controls **who can embed your page**, whereas `frame-src` or `child-src` specifies where your page can embed content from.

## 6. Strict-Transport-Security: HSTS Only Over HTTPS

### 6.1 What Does HSTS Do?

The header:

```http
Strict-Transport-Security: max-age=31536000 ; includeSubDomains
```

instructs HSTS-capable browsers to remember that this host should only be connected to via HTTPS for the specified duration. `31536000` seconds is approximately **one year**; `includeSubDomains` extends the policy to subdomains.

**Important conditions:**

- By default, Spring Security only adds HSTS **when the request is evaluated as secure/HTTPS**.
- Browsers only learn HSTS from a **trusted HTTPS response**; they do not honor the header from plain-text HTTP.
- HSTS does not open an HTTPS listener. The application or reverse proxy must actually serve TLS with a valid certificate.
- HSTS cannot protect a very first HTTP request if the browser does not yet know the host; preload can address some cases, but carries separate requirements and operational commitments.

```text
First time before HSTS is known:
  browser -> https://shop.example.com
       -> TLS OK -> HSTS response -> browser remembers host

Subsequent visits:
  user types http://shop.example.com
       -> browser remembers HSTS -> upgrades to HTTPS before sending data
```

### 6.2 HSTS Does Not Replace redirectToHttps

`ServerHttpSecurity.redirectToHttps(...)` can configure redirecting HTTP requests to HTTPS. **This is not the HSTS header**. A configuration with a redirect but without proper HTTPS/TLS will still fail; HSTS is only meaningful when responses are delivered over secure HTTPS.

Configuration snippet:

```java
// Enable only when TLS/proxy infrastructure is truly ready.
http.redirectToHttps(Customizer.withDefaults());
```

Do not enable this redirect in a localhost HTTP example if an HTTPS endpoint is not prepared: it easily causes redirects to a port with no service listening.

### 6.3 Customizing max-age, Subdomains, and Preload

Spring Security WebFlux DSL:

```java
.headers(headers -> headers
    .hsts(hsts -> hsts
        .maxAge(Duration.ofDays(180))
        .includeSubdomains(false)
        .preload(false)))
```

Requires importing `java.time.Duration` and placing inside the `ServerHttpSecurity` chain.

- `maxAge(Duration.ofDays(180))`: a testing/operational policy with the chosen duration; **not** the default value.
- `includeSubdomains(false)`: does not force subdomains to apply the HSTS policy; this differs from the illustrative default.
- `preload(false)`: does not include the preload directive in the header.

**Defaults in the HstsSpec Javadoc:** one year, includes subdomains, `preload=false`. Therefore, **do not claim that Spring Security sends `preload` by default**, even though some general documentation snippets illustrate `; preload`.

### 6.4 Caution with includeSubDomains and Preload

HSTS can persist after you deploy or decommission a service. If a subdomain depends on HTTP (legacy, internal, older service), enabling `includeSubDomains` on the parent domain can prevent users from accessing it over HTTP.

Registering for **HSTS preload** also involves separate browser vendor policies/processes, and removing a domain from the preload list is difficult or time-consuming. Do not enable `preload(true)` just to "boost a security scanner score". Before doing so, ensure valid HTTPS certificates for all related subdomains and a long-term operational commitment.

### 6.5 Reverse Proxy and TLS Termination

Common topology:

```text
Browser --HTTPS--> Reverse Proxy/Load Balancer --HTTP--> Spring WebFlux
                       |
                  TLS terminates here
```

If Spring WebFlux only sees the request from the proxy as `http://...`, the HSTS header writer may **fail to recognize the external request as HTTPS** and omit HSTS. Conversely, blindly trusting `X-Forwarded-Proto: https` sent by an Internet user can introduce spoofing/redirect/scheme issues.

One Spring Boot strategy when **behind a trusted proxy**:

```yaml
server:
  forward-headers-strategy: framework
```

Enable and configure forwarded headers only when the reverse proxy **strips/overwrites client-supplied forwarding headers** and trusted hops are defined. Refer to the WebFlux `ForwardedHeaderTransformer` and Spring Boot documentation. Alternatively, HSTS can be configured at the **proxy** instead of the app; if so, agree on ownership and test the actual HTTPS response from the public Internet.

**Critical test:** verify production HTTPS and localhost/staging HTTP separately; `X-Forwarded-Proto` is not an authorization mechanism and does not replace TLS.

## 7. X-XSS-Protection: 0 Does Not Mean Disabling XSS Safety

Listed default:

```http
X-XSS-Protection: 0
```

This header relates to legacy browser XSS Auditors/filters. Those mechanisms have a history of causing bugs or unreliable behavior; modern browsers have removed or restricted support. A value of `0` tells older browsers to **disable** the filter; it does not mean Spring Security is turning off a "high-level" XSS defense layer.

**What you actually need to prevent XSS:**

- Context-aware output escaping for HTML/attributes/URLs/JavaScript.
- Use safe template engines and avoid building HTML from unencoded user input.
- Avoid `innerHTML` or uncontrolled HTML injection.
- Set an appropriate CSP for the application and minimize `unsafe-inline`.
- Manage script dependencies, integrity, trusted code, and upload boundaries.
- Ensure JSON/HTML routes have accurate `Content-Type` and `nosniff`.

You can adjust the header writer (rarely needed):

```java
.headers(headers -> headers
    .xssProtection(xss -> xss.disable()))
```

Do not change it to `X-XSS-Protection: 1; mode=block` just because "1 sounds enabled and safer"; check current browser support and recommendations. In most modern projects, CSP and output encoding policies are far more valuable than the legacy XSS Auditor.

## 8. Runnable Java 17+ Project: Inspecting Exact Default Headers

A small project using Spring WebFlux and Spring Security with three endpoints: public, intentionally cached public, and private/admin. **Do not customize `headers(...)`** so we can test the exact **defaults** of Spring Security 6.3.x.

### 8.1 Structure

```text
webflux-security-headers/
  settings.gradle
  build.gradle
  src/main/java/demo/headers/HeadersApplication.java
  src/main/java/demo/headers/SecurityConfiguration.java
  src/main/java/demo/headers/ApiController.java
  src/test/java/demo/headers/DefaultHeadersTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-security-headers'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.headers'
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
```

- `spring-boot-starter-webflux` creates a reactive HTTP server; do not declare Servlet's `spring-boot-starter-web`.
- `spring-boot-starter-security` applies WebFlux Security, default header writers, and Basic authentication.
- Tests use Spring Boot Test and WebTestClient.
- Gradle/JDK must be compatible with Spring Boot 3.3.13. Version 3.3.x is used only for learning the API; do not choose an unpatched release for production in 2026.

### 8.2 Spring Boot Application

**src/main/java/demo/headers/HeadersApplication.java**

```java
package demo.headers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HeadersApplication {

    public static void main(String[] args) {
        SpringApplication.run(HeadersApplication.class, args);
    }
}
```

### 8.3 SecurityConfiguration: Keeping Default Headers Intact

**src/main/java/demo/headers/SecurityConfiguration.java**

```java
package demo.headers;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("dev-only-password"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("dev-admin-password"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/public-cache")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/private")
                    .authenticated()
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            // Explicitly state keeping the default header configuration:
            .headers(Customizer.withDefaults())
            .build();
    }
}
```

Key takeaways:

1. `@EnableWebFluxSecurity` applies the Security WebFilter for WebFlux; do not use Servlet's `@EnableWebSecurity`.
2. `headers(Customizer.withDefaults())` preserves the default header policy and **does not automatically enable a custom CSP**. This line can be omitted in a minimal configuration if explicit expression isn't needed.
3. `/api/public` and `/api/public-cache` do not require login. **`permitAll()` does not disable header writers**; public responses still receive the appropriate security headers.
4. `/api/private` requires authentication, `/api/admin` requires `ROLE_ADMIN`.
5. HTTP Basic is used to test 401/200/403 responses. Passwords are demo credentials only and are hashed with BCrypt.
6. `formLogin(disable)` avoids HTML login redirects in the API demo; it is unrelated to default headers.
7. Spring Security WebFlux defaults also include **CSRF protection**. The demo only uses GET; when adding POST/PUT/PATCH/DELETE in a browser/cookie-based app, evaluate CSRF properly instead of disabling it to "fix 403 errors".

### 8.4 Controller

**src/main/java/demo/headers/ApiController.java**

```java
package demo.headers;

import java.security.Principal;

import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<String> publicInfo() {
        return Mono.just("public");
    }

    @GetMapping("/api/public-cache")
    public Mono<ResponseEntity<String>> publicCache() {
        return Mono.just(ResponseEntity.ok()
            .header(HttpHeaders.CACHE_CONTROL, "public, max-age=120")
            .body("public-cache"));
    }

    @GetMapping("/api/private")
    public Mono<String> privateInfo(Principal principal) {
        return Mono.just("hello " + principal.getName());
    }

    @GetMapping("/api/admin")
    public Mono<String> adminInfo() {
        return Mono.just("admin");
    }
}
```

The demo intentionally writes Cache-Control for a route that is **public and contains no user data**. Because Spring Security avoids overwriting responses that already have an application-set Cache-Control, this demonstrates how to allow selective caching without disabling all header writers.

### 8.5 Running Tests with curl

In the project directory (with JDK 17+ and compatible Gradle):

```bash
gradle bootRun
```

If an appropriate Gradle Wrapper is present, use `./gradlew bootRun`; on Windows use `gradlew.bat bootRun`.

Open another terminal:

```bash
# Public, 200 response with default headers:
curl -i http://localhost:8080/api/public

# Public resource with custom Cache-Control:
curl -i http://localhost:8080/api/public-cache

# Unauthenticated: 401 response + HTTP Basic challenge:
curl -i http://localhost:8080/api/private

# Curl prompts for password when -u only provides username;
# enter dev-only-password at the prompt:
curl -i -u alice http://localhost:8080/api/private

# Alice lacks ROLE_ADMIN: 403:
curl -i -u alice http://localhost:8080/api/admin

# Valid admin: enter dev-admin-password at the prompt:
curl -i -u admin http://localhost:8080/api/admin
```

Windows PowerShell may require `curl.exe` when `curl` is an alias. Do not embed passwords in URLs or save real credentials in shell history.

**Observation on `http://localhost`:** `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 0`, and the no-cache group are expected; **do not expect to see `Strict-Transport-Security` because the request is not HTTPS**. Some responses may include other headers from Netty, Spring WebFlux, or other libraries.

### 8.6 Automated Testing with WebTestClient

**src/test/java/demo/headers/DefaultHeadersTest.java**

```java
package demo.headers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class DefaultHeadersTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicResponseHasDefaultHeaders() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.CACHE_CONTROL,
                "no-cache, no-store, max-age=0, must-revalidate")
            .expectHeader().valueEquals("Pragma", "no-cache")
            .expectHeader().valueEquals("Expires", "0")
            .expectHeader().valueEquals(
                "X-Content-Type-Options", "nosniff")
            .expectHeader().valueEquals(
                "X-Frame-Options", "DENY")
            .expectHeader().valueEquals(
                "X-XSS-Protection", "0");
    }

    @Test
    void hstsIsNotAddedOnPlainHttp() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist(
                "Strict-Transport-Security");
    }

    @Test
    void cspIsNotAutomicallyAdded() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist(
                "Content-Security-Policy")
            .expectHeader().doesNotExist(
                "Permissions-Policy");
    }

    @Test
    void applicationCanOverrideCacheForPublicResource() {
        client.get().uri("/api/public-cache")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.CACHE_CONTROL, "public, max-age=120")
            .expectHeader().valueEquals(
                "X-Content-Type-Options", "nosniff");
    }

    @Test
    void missingCredentialIsUnauthorized() {
        client.get().uri("/api/private")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueMatches(
                HttpHeaders.WWW_AUTHENTICATE, "Basic .*");
    }

    @Test
    void privateDataHasCacheProtection() {
        client.get().uri("/api/private")
            .headers(h ->
                h.setBasicAuth("alice", "dev-only-password"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.CACHE_CONTROL,
                "no-cache, no-store, max-age=0, must-revalidate")
            .expectBody(String.class).isEqualTo("hello alice");
    }

    @Test
    void unauthorizedRoleStillCannotSeeAdmin() {
        client.get().uri("/api/admin")
            .headers(h ->
                h.setBasicAuth("alice", "dev-only-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessProtectedRoute() {
        client.get().uri("/api/admin")
            .headers(h ->
                h.setBasicAuth("admin", "dev-admin-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin");
    }
}
```

These **8 test methods** demonstrate that:

- Default no-cache/nosniff/frame/XSS headers are generated for public resources.
- HSTS **does not appear** over plain HTTP on the test server.
- CSP/Permissions-Policy **are not automatically added** to responses by the default configuration.
- A public resource's custom `Cache-Control` can be preserved while `nosniff` remains intact.
- Authentication/authorization works **independently** of headers, covering 401, 403, and 200.
- Private data still receives the default anti-cache policy.

Run:

```bash
gradle test
```

**Note:** these are expected outcomes based on code and Javadoc review, **not an executed build/test log**. If using a different Spring Security/Netty version, verify each header's value. `Referrer-Policy` is not asserted as default due to the documentation discrepancy noted in section 2; if your application needs that policy, configure it explicitly and add a test.

### 8.7 Testing HSTS Over Real HTTPS

The tests in section 8.6 only run over HTTP. To verify HSTS:

1. Configure TLS on Netty or a reverse proxy with a valid certificate in a staging environment.
2. Access the endpoint **over real HTTPS** from a client/browser.
3. Observe the headers and confirm no proxy is stripping or mis-overwriting them.
4. If using HTTPS termination at a proxy, confirm forwarded headers/scheme are recognized properly or that the proxy owns HSTS.

Example:

```bash
curl -i https://staging.example.com/api/public
```

Expect the HTTPS response to include `Strict-Transport-Security` if the default or configured policy is active. **Do not use `curl -k` as proof that production TLS is secure**: skipping certificate verification hides TLS failures even if you can still read the headers.

## 9. Customizing Headers in the WebFlux DSL

When you do not want to replace all defaults, adjust **only the headers you need**:

```java
// Configuration snippet: use instead of .headers(withDefaults())
// inside SecurityWebFilterChain; do not chain both side by side.
.headers(headers -> headers
    .frameOptions(frame -> frame
        .mode(XFrameOptionsServerHttpHeadersWriter.Mode.SAMEORIGIN))
    .hsts(hsts -> hsts
        .maxAge(Duration.ofDays(180))
        .includeSubdomains(false)
        .preload(false))
    .referrerPolicy(referrer -> referrer
        .policy(ReferrerPolicyServerHttpHeadersWriter
            .ReferrerPolicy.NO_REFERRER))
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; object-src 'none'; "
                + "base-uri 'self'; frame-ancestors 'self'")))
```

Requires appropriate imports:

```java
import java.time.Duration;
import org.springframework.security.web.server.header.XFrameOptionsServerHttpHeadersWriter;
import org.springframework.security.web.server.header.ReferrerPolicyServerHttpHeadersWriter;
```

This is an **optional configuration snippet**, not a complete class. When applying it:

- `X-Frame-Options` becomes `SAMEORIGIN`; does same-origin embedding actually need to be allowed?
- HSTS becomes 180 days without subdomain inclusion; consider your domain policy.
- `Referrer-Policy: no-referrer` is added explicitly regardless of default differences.
- CSP is an **illustrative policy**, unlikely to fit a SPA using CDNs/inline scripts/WebSockets. Applied without testing, CSP can break legitimate functionality.
- Other default headers remain intact because we **did not disable `headers` as a whole**.

### CSP Must Be Designed Around Actual Resources

`Content-Security-Policy` is an optional header **with no universal default policy**. Example:

```http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'
```

It restricts resource origins and how pages can be embedded. However, an application with CDNs, fonts, images, or cross-origin API calls may need specific directives such as `script-src`, `style-src`, `img-src`, `connect-src`, and `font-src`. Do not drop `default-src` and open `*` everywhere just to "stop errors". For large deployments, test with `Content-Security-Policy-Report-Only` first and then tighten the policy.

`frame-ancestors` may interact with `X-Frame-Options` across different browsers; test against target browser versions.

### Permissions-Policy, COOP, COEP, CORP

These headers are added when an application wants to control browser feature permissions and cross-origin boundaries. Example custom policy:

```http
Permissions-Policy: geolocation=(), camera=(), microphone=()
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Resource-Policy: same-site
```

The lines above **merely illustrate** a policy and are **not defaults** in the demo. An application embedding SSO/payment iframes or requiring third-party integrations must carefully evaluate COOP/COEP/CORP to avoid breaking legitimate flows. They do not replace CORS or authentication.

### Changing the Frame Policy While Keeping Other Defaults

If you only need to use the H2 console or a same-origin embedded page in a learning environment, you can configure just that piece:

```java
.headers(headers -> headers
    .frameOptions(frame -> frame
        .mode(XFrameOptionsServerHttpHeadersWriter.Mode.SAMEORIGIN)))
```

Do not use `headers(headers -> headers.disable())` just because one page needs an iframe. That removes **the entire** group of protective headers on the chain.

### When Disabling All Header Writers

```java
// ANTI-PATTERN: loses all security headers for the chain.
.headers(headers -> headers.disable())
```

This configuration disables Spring Security header writers on the chain; consider it only when another layer has clear ownership, has been tested end-to-end, and you know the exact impact. For typical apps, this is an overly broad and dangerous fix.

## 10. Differences Between WebFlux and Servlet/MVC

| Topic | Reactive/WebFlux | Servlet/MVC |
|---|---|---|
| Security builder | `ServerHttpSecurity` | `HttpSecurity` |
| Filter chain | `SecurityWebFilterChain` | `SecurityFilterChain` |
| Enable configuration | `@EnableWebFluxSecurity` | `@EnableWebSecurity` |
| Header DSL | `.headers(headers -> ...)` | Similar DSL name but different classes/overloads |
| Header writer API | `ServerHttpHeadersWriter`, reactive response | `HeaderWriter`, Servlet response |
| Request/response | `ServerWebExchange`/`ServerHttpResponse` | `HttpServletRequest`/`HttpServletResponse` |
| HSTS | Based on whether the WebFlux request is considered secure | Based on Servlet secure request |
| Proxy forwarding | `ForwardedHeaderTransformer` or Boot integration | `ForwardedHeaderFilter` or native container |
| Default headers | Similar core list, may differ in details/version | Similar core; do not copy class imports |

**Do not** copy:

```java
// Servlet only; do not use in WebFlux:
HttpSecurity http;
SecurityFilterChain chain;
```

and expect those classes to work in a reactive configuration. Even with the same `headers` DSL method name, writer classes and enum imports differ. For instance, `XFrameOptionsServerHttpHeadersWriter.Mode.SAMEORIGIN` in WebFlux is not the Servlet header writer enum.

## 11. Real-World Issues and Diagnostic Methods

### 11.1 No Security Headers Visible at All

Check:

1. Does the request actually pass through a `SecurityWebFilterChain`?
2. Are there multiple chains with `securityMatcher`/`@Order`? Does the URL match another chain, or fall outside all chains?
3. Did someone call `headers(headers -> headers.disable())`?
4. Did Spring Boot select **WebFlux** properly, or is Spring MVC on the classpath?
5. Is a reverse proxy/CDN/WebFilter stripping or overwriting headers?
6. Does a response in a special error/redirect flow go through the filter writer?
7. Re-check the Spring Security version and configuration changes after an upgrade.

**Missing headers do not mean the route is unprotected**; however, it is a signal to investigate because browser protections and cache policies may be lost. Add tests to catch regressions.

### 11.2 All Headers Present Except HSTS on Localhost

This is usually **expected default behavior**: localhost uses HTTP, so HSTS is not added. Use real HTTPS or properly simulate a secure request in an appropriately designed test. Do not fix this by forcing HSTS over HTTP; browsers will not trust an HSTS policy from an HTTP response.

### 11.3 HSTS Missing After Deploying Behind a Reverse Proxy

The application may only see internal HTTP because TLS terminates at the proxy. Solutions:

- Configure forwarding headers properly on both the proxy and Boot.
- Or configure HSTS on the responsible proxy.
- Test from a browser via the **public HTTPS endpoint**, not just internally inside the pod.
- Do not trust `X-Forwarded-Proto` from the Internet if it has not been sanitized by the proxy.

### 11.4 Disabling X-Frame-Options to Render an Iframe

Consider `SAMEORIGIN` if that fits the requirement. If cross-origin embedding is needed, evaluate `Content-Security-Policy: frame-ancestors ...`, session/cookie SameSite settings, and the clickjacking threat model. Do not disable all headers.

### 11.5 Static CSS/JS Marked as "no-cache"

Default Cache-Control prioritizes safety. Choose a dedicated policy for public, versioned resources, or configure static resource caching; do not disable the cache writer globally if APIs serve user-specific data.

### 11.6 `nosniff` Is Present, but Script/Style Fails to Load

Fix the server to return the proper `Content-Type` (JavaScript/CSS). `nosniff` is helping the browser avoid executing content with the wrong MIME type; turning it off can mask a bug and open up XSS.

### 11.7 New Header Added, but Browser Behavior Does Not Change

- The browser does not support that policy.
- The policy is not on the **exact response** the browser loaded.
- The browser has stale cache/HSTS state, or a proxy is serving a different response.
- The CSP header has invalid syntax/duplicates; the console shows which directive blocked or failed.
- `Permissions-Policy`/cross-origin policy targets the wrong feature or browsing context.
- HSTS only takes effect on HTTPS hosts trusted by the browser.

### 11.8 Headers Emitted Twice

If CDN, reverse proxy, and application all add CSP/HSTS/X-Frame-Options, duplicate headers or unintended overlapping policies may appear. Establish **single ownership** or a clear unified contract: e.g., app owns route-level CSP; edge owns HSTS on public TLS; both are integration tested. Do not guess browser precedence when duplicated.

### 11.9 401/403 Errors Missing Proper Headers

Spring Security filters can normally add security headers to responses passing through the chain, including error responses, though filter/commit paths and proxies may behave differently. Directly test 200, 401, 403, redirects, and server errors. A `@RestControllerAdvice` is not the only place that can produce 401/403 since many Security errors originate from WebFilters before reaching controllers.

### 11.10 Headers Alone Do Not Solve CSRF, CORS, XSS, or Uploads

- `X-Content-Type-Options` does not replace XSS output encoding.
- `X-Frame-Options` does not by itself prevent CSRF.
- HSTS does not fix an invalid certificate or missing HTTPS listener.
- Cache-Control does not automatically clear sessions/tokens.
- CSP is not auto-generated and does not replace server-side permission checks.
- CORS only governs browser response sharing, not authorization.
- `X-XSS-Protection=0` is not an XSS filter.

## 12. Test Matrix Recommended for Real Projects

| Response type | Headers to verify | Condition |
|---|---|---|
| Public GET 200 | Default no-cache/nosniff/frame/XSS headers | When no cache override is set |
| Private GET 200 | Cache-Control protecting user data | With valid credentials |
| 401 Basic/Bearer | Security headers + proper `WWW-Authenticate` scheme | Missing/invalid credentials |
| 403 role/CSRF | Security headers and actual 403 status | Insufficient permissions or invalid CSRF |
| 302 login redirect | Cache/security headers when handled by chain | Form login/browser |
| Public static asset | Public Cache-Control matching resource | Contains no user data |
| HTTPS 200 | HSTS matching domain policy | Real TLS or request recognized as secure |
| HTTP 200 | Do not assert HSTS must be present | Running plain HTTP |
| Page using iframe | X-Frame-Options/CSP frame-ancestors | Allowed origins verified |
| CSP-enabled page | CSP policy and console violations | Source allowlist defined |
| Multi-chain routes | Headers written by the intended chain | `securityMatcher` and `@Order` precedence |
| Multiple proxies/CDNs | Headers reaching browser not overwritten improperly | End-to-end test |

**Testing advice:** test against your **application's security contract**, rather than hardcoding every incidental header the server sends. Core defaults can be asserted as in the demo; custom headers should have dedicated assertions. For browser behavior, test on target browsers and TLS environments.

## 13. Implementation and Maintenance Checklist

1. Confirm the app uses WebFlux and which `SecurityWebFilterChain` bean actually applies.
2. Know the exact default header group for your running version; do not confuse it with "current" docs for another version.
3. Keep `Cache-Control: no-store` on private resources; allow caching only for public resources.
4. Keep `X-Content-Type-Options: nosniff`, and fix MIME types/`Content-Disposition` for uploads/resources.
5. Keep `X-Frame-Options: DENY` unless embedding is required; if needed, design CSP `frame-ancestors` around trusted origins.
6. Remember `X-XSS-Protection: 0` disables the legacy XSS Auditor; implement output encoding and CSP separately.
7. Ensure HTTPS/TLS at the public edge and verify HSTS appears only over HTTPS. Evaluate `includeSubDomains`/`preload` carefully.
8. Establish a trust boundary for forwarding headers to prevent scheme/host spoofing from the Internet.
9. Never casually call `headers(...disable())` or disable cache/security writers globally.
10. If the app needs CSP, Referrer-Policy, Permissions-Policy, or COOP/COEP/CORP, configure them explicitly and test.
11. Clarify who owns security headers when combining app + Nginx/Ingress/CDN.
12. Test 200/401/403/302, static assets, HTTPS, fallback chains, and after dependency upgrades.
13. Treat browser DevTools/CSP reports, HTTP integration tests, and security scanners as complementary signals — do not treat an "A grade" as sufficient proof.
14. Never leak passwords, session cookies, Authorization headers, or tokens in logs/debug output while inspecting headers.
15. Stay on a supported Spring Security version; also check header-related advisories. For example, **CVE-2026-22732** (published 2026-03-19) describes a case where headers were not written on the **Servlet branch** in certain versions; **do not automatically assume the same CVE applies to WebFlux**. This is a reminder to verify scope and patches from official advisories.

## 14. Practice Exercises

1. Run the demo and inspect all response headers of `GET /api/public`. Compare with the default list; why might `Strict-Transport-Security` be absent?
2. Call `GET /api/private` without logging in. Confirm the 401 Basic challenge and protective headers, distinguishing them from authentication/authorization.
3. Log in as Alice and inspect `Cache-Control` on `GET /api/private`. Why can't `no-store` be replaced with `public,max-age=3600`?
4. Compare `GET /api/public` and `GET /api/public-cache`. Why is a cache override appropriate only for public resources?
5. Change `frameOptions` from `DENY` to `SAMEORIGIN`, write a header test, and test embedding the page same-origin. For a third-party portal, what additional mechanism is needed?
6. Deploy staging HTTPS and check HSTS on responses through a proxy. If HSTS is missing, inspect scheme, forwarding headers, policy ownership, and TLS termination.
7. Try configuring HSTS `maxAge` to 180 days without `includeSubdomains`. Analyze why enabling `preload` is not just a minor change.
8. Add a CSP allowing only same-origin scripts and test a page using a CDN script. Propose a safe violation-reporting and rollout approach.
9. Explicitly enable `Referrer-Policy: no-referrer`. Verify on the actual Spring Security version rather than guessing from general documentation.
10. Add `Permissions-Policy: geolocation=()` and test that the browser blocks geolocation calls in disallowed contexts.
11. Create two `SecurityWebFilterChain` beans with a `/api/**` matcher and a fallback; check default headers on each group. What happens if a URL matches no chain?
12. Explain why `X-XSS-Protection: 0` does not make an application "XSS-proof" and why `nosniff` does not auto-fix content types.
13. Describe a post-deploy header testing workflow using WebTestClient, curl, and browser DevTools, covering 200/401/403/HTTPS.
14. Audit the proxy/CDN so it neither strips app-emitted headers nor unexpectedly duplicates HSTS/CSP.

## Summary

**Spring Security WebFlux provides a default set of HTTP response security headers** to protect caching, MIME handling, iframe embedding, legacy XSS browser behavior, and HTTPS. The defaults listed in the Spring Security 6.x Javadoc include **`Cache-Control`, `Pragma`, `Expires`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 0`, and `Strict-Transport-Security` on secure requests only**. HSTS does not mean Spring Boot automatically opens HTTPS; CSP/Permissions-Policy and cross-origin isolation policies require application-specific configuration. If you only need to change one header, use `ServerHttpSecurity.headers(...)` to customize **that specific header**, without disabling all protections. Always verify caching, HTTPS/proxy, security chains, role/CSRF rules, and browser behavior together.

## Official References

1. Spring Security 6.5 — WebFlux Security HTTP Response Headers: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html
2. Spring Security 6.5 — `ServerHttpSecurity.headers(Customizer)` and default header list: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/ServerHttpSecurity.html
3. Spring Security — General HTTP Response Headers list: https://docs.spring.io/spring-security/reference/features/exploits/headers.html
4. Spring Security 6.3.10 — `ServerHttpSecurity.HeaderSpec` (lambda API): https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/config/web/server/ServerHttpSecurity.HeaderSpec.html
5. Spring Security 6.3.x — `XFrameOptionsServerHttpHeadersWriter.Mode`: https://docs.spring.io/spring-security/site/docs/6.3.0-M3/api/org/springframework/security/web/server/header/XFrameOptionsServerHttpHeadersWriter.Mode.html
6. Spring Security 6.5 — `ReferrerPolicyServerHttpHeadersWriter.ReferrerPolicy`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/header/ReferrerPolicyServerHttpHeadersWriter.ReferrerPolicy.html
7. Spring Security — HTTP, HTTPS redirect, TLS, and proxy forwarding: https://docs.spring.io/spring-security/reference/6.5/features/exploits/http.html
8. Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
9. Spring Framework — ForwardedHeaderTransformer (WebFlux): https://docs.spring.io/spring-framework/reference/web/webflux/filters.html
10. OWASP Cheat Sheet — HTTP Security Response Headers: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html
11. MDN — Strict-Transport-Security: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security
12. Spring Security advisory CVE-2026-22732, Servlet-specific scope: https://spring.io/security/cve-2026-22732/
