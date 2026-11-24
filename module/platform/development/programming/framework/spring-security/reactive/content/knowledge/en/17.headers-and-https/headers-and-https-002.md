# Cache-Control and Restricting Caching of Responses Containing Sensitive Data

## 1. The Problem: Logged Out, Yet Data Can Still Exist in Cache

In a Spring Security Reactive application running on Spring WebFlux, a successful request may return private data such as a profile, balance, transaction history, HR records, orders, internal documents, account recovery codes, or session-related details. Even when Spring Security authenticates and authorizes properly at request time, the response may pass through **browser caches, proxies, CDNs, or application/client-managed caches**.

If a server inadvertently allows sensitive responses to be cached, the risks include:

- Another person using the same device/browser can view cached data after the user logs out.
- A misconfigured proxy/CDN can retain and serve one user's private content to other users.
- Old account data can appear when switching users in the same browser.
- UI information fails to update after logout, permission changes, or privacy policy changes.
- A response containing tokens, reset links, transaction codes, or personal data gets stored in unnecessary caches.
- HTTP tests only verify status 200 and ignore `Cache-Control`, leaving a hard-to-detect vulnerability.

In Spring Security WebFlux, **Cache-Control is a layer that reduces the risk of storing and reusing HTTP responses**. It does not replace authentication, authorization, TLS, logout, XSS prevention, or clearing data stored elsewhere by JavaScript.

This lesson belongs to the **Headers and HTTPS** group. The direct topic is **Cache-Control and restricting caching of responses containing sensitive data**; the focus is on HTTP header semantics, Spring Security Reactive defaults, proper WebFlux configuration, and testing.

### Learning Objectives

After this lesson, you can:

1. Explain the differences between browser cache, shared cache, CDN, service worker, and application-stored data.
2. Accurately distinguish `no-store`, `no-cache`, `private`, `public`, `max-age`, `must-revalidate`, and legacy headers.
3. Understand which headers Spring Security Reactive sends by default, when the application may override them, and how to avoid disabling protection globally.
4. Use `CacheControl.noStore()`, `ResponseEntity.cacheControl(...)`, and `ServerHttpSecurity.headers(...)` in WebFlux.
5. Protect private responses while still allowing caching of **public, versioned** resources such as CSS/JavaScript/images.
6. Run a Java 17+ / Spring Boot / WebFlux Security project and verify it with `curl` and `WebTestClient`.
7. Design cache policies for 200/401/403, errors, file downloads, post-logout browsers, and CDNs.
8. Identify the limitations of `no-store` and the mandatory accompanying controls.

## 2. Where Does HTTP Caching Live?

A request can pass through multiple layers:

~~~text
Browser / Mobile App
       |
       +--> Browser HTTP cache (memory/disk)
       +--> Back-forward page cache, page state, Service Worker Cache API
       +--> App state: localStorage, sessionStorage, IndexedDB, memory
       |
       v
Forward proxy / corporate gateway (if present)
       |
       v
CDN / reverse proxy cache
       |
       v
Spring WebFlux + Spring Security Reactive
       |
       v
Service / Database
~~~

Not all of the layers above use `Cache-Control` in the same way:

- **Browser HTTP cache:** typically interprets HTTP caching directives for responses eligible for storage.
- **Shared cache:** reverse proxies/CDNs may serve the same response to multiple clients. They must follow `private`/`no-store` semantics and rules regarding Authorization, unless misconfigured or non-compliant.
- **Browser back-forward cache (BFCache):** may retain a page and rendered state when a user navigates away and clicks Back; behavior with `no-store` also depends on browser version/policy, so you should not promise that the header alone always clears the UI.
- **Service Worker / Cache API:** JavaScript code can programmatically store responses by design. `Cache-Control` is not a command that automatically purges every copy actively stored by the app in the Cache API.
- **localStorage / sessionStorage / IndexedDB / SPA memory variables:** these are not HTTP caches; `Cache-Control: no-store` does not automatically erase data written there.
- **Server-side cache** such as Redis/Caffeine: controls backend performance and does not determine whether the browser stores the response.

Therefore, to protect sensitive data, you must first answer: **which layers can store the response**, and do those layers actually respect HTTP caching directives?

### 2.1. HTTP Cache Is Not Spring Cache

In Java, `@Cacheable` / `CacheManager` usually refers to caching computation or query results **inside the server system**. `Cache-Control` is a header on the **HTTP response** telling HTTP caches how to store/reuse data. The two mechanisms are independent.

A service can cache business data in Redis to optimize queries while returning `Cache-Control: no-store` to the browser; conversely, an API not using Redis can still accidentally allow a CDN to cache its response.

Do not confuse Spring Session caching, database caching, and browser caching.

## 3. Important HTTP Cache Directives per RFC 9111

Read the semantics carefully before writing configuration. This is the core distinction of this lesson.

| Response directive | Exact meaning | Suitable for highly sensitive data? |
| --- | --- | --- |
| `no-store` | Compliant caches **must not store** the response or use it to serve another request | **Yes**, usually the core directive |
| `no-cache` | Caches **may store**, but must revalidate with the origin before reuse | **Alone: insufficient** if you want to avoid storage |
| `private` | Shared caches **must not store**; private caches (e.g., browser) may still store | **Alone: insufficient** for secrets on shared devices |
| `public` | Allows the response to be stored in a shared cache if other conditions are met | **Do not** use for user-specific content |
| `max-age=0` | Response becomes stale almost immediately; caches may still store and revalidate | **Does not** replace `no-store` |
| `max-age=3600` | Maximum freshness lifetime of 3600 seconds per HTTP semantics | Intended for cacheable content |
| `s-maxage` | Freshness lifetime for **shared caches**, can override other limits there | Do not apply to sensitive resources unless specifically designed |
| `must-revalidate` | Once stale, caches must revalidate before reuse, never serve stale arbitrarily | Supplementary only; does not forbid storage |
| `immutable` | Hints that content will not change during its freshness lifetime | Only for truly versioned/fingerprinted assets |
| `no-transform` | Asks intermediaries not to transform the representation | Does not replace no-store/no-cache |

### 3.1. no-store — "Do Not Store"

Example for an account page or private data API:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"account":"DEMO-001","balance":100}
~~~

According to RFC 9111, a `no-store` response instructs compliant caches **not to store any part of the immediate request/response** and not to use that response to serve another request. It applies to both private and shared caches.

However, the RFC also notes that `no-store` **is not an absolute guarantee of confidentiality**: malicious or buggy caches may ignore the directive; transit still requires TLS; data may already reside in application memory or screenshots. It is an important safeguard, but cannot replace comprehensive privacy/security controls.

### 3.2. no-cache — "May Store, Must Revalidate"

The name `no-cache` is misleading. Example:

~~~http
Cache-Control: no-cache
ETag: "version-7"
~~~

A cache may store the response. Before reusing it, it must send a conditional request and receive server confirmation that it is still valid (e.g., HTTP 304). If you do not want a copy of sensitive data residing on disk/cache, `no-cache` **is not enough**.

A common mistake:

~~~http
Cache-Control: private, no-cache
~~~

This header **does not forbid the browser from storing the response**. It restricts shared caches and forces revalidation, yet a private cache can still retain a copy. When the requirement is "do not cache responses containing sensitive data", `no-store` is usually needed.

### 3.3. private — Blocks Shared Caches, Not Browser Caches

Example:

~~~http
Cache-Control: private, max-age=60
~~~

It may suit **low-sensitivity personal data** when the product team accepts 60 seconds of browser caching while forbidding proxies/CDNs from sharing the cache. However, it should not be applied to bank statements, OTP codes, confidential documents, or profiles containing highly sensitive data when storage must be prevented.

**The word "private" here does not mean encrypted.** It only states which caches are allowed to retain the response.

### 3.4. max-age=0 Does Not Delete Data from Cache

~~~http
Cache-Control: max-age=0, must-revalidate
~~~

A cache can store the response and then ask the server before reusing it. When switching users on the same device, the cache may continue to hold a representation stored on disk. This is not an equivalent policy to `no-store`.

Similarly, `Expires: 0` is a legacy freshness directive; it does not carry the storage-prohibition semantics of `no-store`.

### 3.5. public and Static Resources

For genuinely public assets with versioned/fingerprinted URLs like `/assets/app.84bd2.js`, you can allow:

~~~http
Cache-Control: public, max-age=31536000, immutable
~~~

When the asset changes, the build pipeline emits a **new URL**; never mutate content at the same immutable URL. This reduces load and latency without risking user-data responses being cached.

Do not use `public` for user-specific HTML dashboards, profile JSON, bearer-token responses, password resets, or personal report exports.

## 4. Default Header Set of Spring Security Reactive

According to the Spring Security documentation, when security headers are enabled by default, the cache-related response headers are typically:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

**Meaning of each part:**
- `no-store`: the most important part for preventing storage of sensitive responses.
- `no-cache`: requires revalidation if a cache happens to hold the response under other circumstances.
- `max-age=0` and `must-revalidate`: clarify freshness and revalidation behavior.
- `Pragma: no-cache`: legacy HTTP/1.0 compatibility; does not replace standard response `Cache-Control`.
- `Expires: 0`: legacy date/freshness indicator; not a strong enough anti-caching control on its own.

In Spring Security WebFlux, **you do not need to manually add these headers in every controller** if the default security chain already applies them and the application does not override them.

However, two important details apply:

1. **When the application sets its own Cache-Control**, Spring Security may yield to the application's configuration. This is intentional so that CSS/JS/image assets can be cached. Therefore, if a controller returns `public, max-age=...` on a sensitive endpoint, do not expect the security defaults to fix that mistake automatically.
2. **If a security chain does not apply to a request**, you cannot assume those headers were added. With multiple `SecurityWebFilterChain` beans, routes outside a security matcher or chains with security headers disabled can produce different responses.

**Always test the actual headers** on sensitive routes rather than only reading a single chain configuration.

### 4.1. Defaults Can Be Overridden When the Application Explicitly Sets Headers

Example:

~~~java
// A controller's ResponseEntity is allowed to set its own Cache-Control.
return ResponseEntity.ok()
        .cacheControl(CacheControl.maxAge(Duration.ofDays(30)).cachePublic())
        .body("public-asset");
~~~

In WebFlux, Spring Security does not impose a blanket "forbid caching everything unconditionally" policy. The Reactive documentation allows **selectively setting Cache-Control on ServerHttpResponse** to override the default, especially for static assets. This balances security and performance.

Consequence: **code reviews must inspect every place calling setCacheControl/cacheControl/header("Cache-Control",...)**, not just SecurityConfig.

### 4.2. Do Not Disable All Security Headers Just to Cache One Asset

Anti-pattern:

~~~java
// WRONG for most applications: removes the entire set of default security headers.
.headers(headers -> headers.disable())
~~~

This can strip other protective layers such as content-type options, frame options, and HSTS depending on request/config. If you only want to allow caching of a public asset, set a dedicated Cache-Control on that asset.

Likewise, do not disable the cache-header writer globally and forget to reapply it to every endpoint:

~~~java
// Syntactically valid API, but risky if applied unconditionally.
.headers(headers -> headers
        .cache(cache -> cache.disable()))
~~~

This snippet disables **Spring Security's cache-related default headers**; it neither prevents all caching by itself nor adds a replacement policy. In browser applications handling sensitive data, keep the defaults or ensure an appropriate WebFilter/controller policy across all protected routes.

**This is the WebFlux DSL:** `ServerHttpSecurity.headers(headers -> headers.cache(...))`. Do not use Servlet's `HttpSecurity` or `headers.cacheControl(...)` when running Spring WebFlux.

## 5. Classify Responses by Sensitivity Before Deciding Cache Policy

No single rule fits all resources. A starting matrix:

| Response type | Example | Suggested policy | Reason |
| --- | --- | --- | --- |
| Logged-in user profile | `GET /api/me` | `no-store` | Contains identity and personal data |
| Balance, statements, banking data | `GET /api/statements` | `no-store` | Prevent copies in browser/proxy |
| Password reset code, OTP, token exchange | `POST /api/auth/recover` | `no-store` | Access-control-sensitive data |
| User-scoped internal search results | `GET /api/search/private` | `no-store` or evaluated private policy | May leak history or document names |
| User-specific HTML dashboard | `GET /app/dashboard` | `no-store` | Avoid displaying stale content after switching accounts |
| User-specific exported PDF file | `GET /api/export/report.pdf` | `no-store` | Prevent storing/re-serving private files from HTTP cache |
| Error response with personal info | `4xx/5xx` | `no-store` | Error bodies can also contain sensitive data |
| Login/logout HTML pages | `GET/POST auth routes` | `no-store` | Avoid caching stale info, CSRF tokens, or form state |
| Public product catalog | `GET /public/catalog` | `public` + moderate `max-age` if truly public | Improves performance |
| Versioned/fingerprinted JS/CSS | `/assets/app.a1b2c3.js` | `public, max-age=31536000, immutable` when immutable | Public assets cached long-term |
| Frequently changing public config | `/public/config.json` | `no-cache` + validators or short TTL | Can be stored, but must verify version |
| Internal API accepting only Bearer | Depends on data | **Not automatically safe to cache** | Authorization header does not solve everything |

This matrix is a starting point for threat modeling, not a rulebook to apply blindly without examining the data. Specifically, **"HTTP GET" does not mean "public/cacheable"**; many GET requests return the most sensitive data.

### 5.1. Not Just HTTP 200

A 401 response may contain challenge details. A 403 response may expose resource names or missing permissions if error handling is unsafe; 404/409/422 can also describe user data. Hence, cache policies for HTTP error responses must also be considered.

Do not only add `no-store` to controllers returning 200 and forget:
- error handlers;
- authentication entry points;
- access denied handlers;
- logout and token refresh endpoints;
- file downloads;
- gateway/CDN-generated error pages.

Spring Security default headers help at the security layer, but every actual response should be tested.

## 6. Important HTTP Rules Beyond Cache-Control

### 6.1. Set-Cookie Does Not Automatically Forbid Caching

A common misconception is: "If a response has `Set-Cookie`, the CDN naturally won't cache it." RFC 9111 notes that **the presence of Set-Cookie does not automatically prohibit caching**; a response may still be cached and reused if other conditions permit.

Therefore, responses carrying session cookies and private data need an explicit policy, typically `Cache-Control: no-store`. Do not treat Set-Cookie as a substitute.

### 6.2. The Authorization Header Has Specific Rules for Shared Caches

Per RFC 9111, a shared cache observing a request with `Authorization` is normally restricted from storing/reusing the response unless the response includes specific directives permitting shared caching. Yet do not use this rule as a reason to omit `no-store` on sensitive endpoints:
- HTTP clients may use cookies/sessions instead of the Authorization header.
- CDN/gateway configurations may override or fail to comply.
- The response can still be cached in a **private browser cache**.
- A developer might accidentally add `public` or a shared-cache policy to an authenticated route.
- API tokens/cookies can be passed in different ways through reverse proxies.

**Set cache policies based on data classification**, not inferred from whether a request carries a particular auth header.

### 6.3. Vary Does Not Replace no-store

~~~http
Vary: Authorization
Cache-Control: private, max-age=60
~~~

`Vary` tells caches to consider the listed request header values when selecting a cached response per HTTP semantics; it does not make a response safe to store. Nor does `Vary: Cookie` guarantee a misconfigured CDN won't share data.

For data that must never be stored, use `no-store`. For public content that varies by language/encoding, `Vary` is useful, but inspect the cache key and test thoroughly.

### 6.4. HTTPS Does Not Automatically Disable Caching

HTTPS protects confidentiality and integrity in transit when properly configured. Browsers can still cache HTTPS responses according to HTTP caching rules; a CDN can terminate TLS and cache at the edge. Therefore:

- `HTTPS` is required for sensitive data.
- `Cache-Control: no-store` is required when HTTP caches must not store the response.
- `Authentication/Authorization` is required so only authorized users read the resource.
- Logout/session invalidation is required to revoke access on future requests.

Never use one mechanism as a replacement for another.

## 7. WebFlux APIs for Setting Cache-Control on Responses

Spring Framework provides:

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
~~~

Main approaches:

~~~java
// 1. Do not store response (protects sensitive content).
ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(data);

// 2. Browser/private cache only; NOT suitable for secrets needing no-store.
ResponseEntity.ok()
        .cacheControl(CacheControl.maxAge(Duration.ofSeconds(60))
                .cachePrivate())
        .body(nonSensitivePersonalData);

// 3. Public, versioned asset.
ResponseEntity.ok()
        .cacheControl(CacheControl.maxAge(Duration.ofDays(30))
                .cachePublic())
        .body(publicAsset);
~~~

These are **snippets** inside a method, not standalone Java files; they require importing `java.time.Duration` and having the corresponding variables `data`, `nonSensitivePersonalData`, and `publicAsset`. In production, do not choose private 60 seconds just because of the word "private" if the actual policy is to forbid storing sensitive data.

### 7.1. CacheControl.noStore()

~~~java
CacheControl.noStore()
~~~

When passed to `ResponseEntity.cacheControl`, it produces the equivalent cache directive value:

~~~http
Cache-Control: no-store
~~~

Spring Security may defer its default cache policy when the application explicitly sets a header; this is normal. If you explicitly choose `noStore()`, it still satisfies the goal of preventing standard HTTP caches from storing the response.

### 7.2. ResponseEntity in a Reactive Handler

Spring WebFlux allows handlers to return:

~~~java
Mono<ResponseEntity<MyDto>>
~~~

This means the HTTP status, headers, and body are determined asynchronously together. When data comes from a reactive repository:

~~~java
// Controller/service snippet; omits repository and model classes.
return repository.findById(id)
        .map(dto -> ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(dto))
        .switchIfEmpty(Mono.just(ResponseEntity.notFound().build()));
~~~

This only illustrates how to compose a `Mono`. The generic types of both branches must unify cleanly in a real class; a complete implementation also defines DTOs, repositories, 404 handling, and a dedicated error-response policy.

**Do not call `block()`** in a WebFlux controller just to add headers. Compose publishers and let Spring subscribe according to the request lifecycle.

### 7.3. Setting Headers via ServerHttpResponse

For `ServerWebExchange` or functional handlers:

~~~java
// Illustrative snippet inside a handler/filter.
exchange.getResponse().getHeaders()
        .setCacheControl(CacheControl.noStore());
~~~

If another component overwrites `Cache-Control` afterward, the final header on the actual response may differ. That is why testing from the HTTP boundary matters more than just verifying that a method was called.

Do not emit two conflicting `Cache-Control` headers (e.g., `public, max-age=3600` plus `no-store` added elsewhere). The policy must clearly establish ownership and final precedence.

## 8. Runnable Java 17+ Project: Safe Defaults, Public Asset Override

The demo uses **Java 17, Spring Boot 3.5.7, Spring WebFlux, and Spring Security Reactive 6.x**. To keep the focus on Cache-Control, we use in-memory HTTP Basic users; usernames/passwords are dummy data **for localhost only**. Do not use `{noop}` or Basic over plain HTTP in production.

The project demonstrates five response scenarios:

1. `GET /public/ping`: public, controller **sets no Cache-Control** → Spring Security default headers still protect it.
2. `GET /api/profile/default`: authenticated, controller **sets no Cache-Control** → Spring Security defaults to `no-store`.
3. `GET /api/profile/explicit`: authenticated, controller explicitly sets `CacheControl.noStore()`.
4. `GET /assets/app.v1.js`: public demo asset content, controller sets `public, max-age=30 days`, overriding the default for that specific route.
5. `GET /api/admin/statement`: ADMIN only, sensitive response set to `no-store`; unauthorized reader is denied.

This **simulates an asset in a controller**, rather than using a production resource handler. A later section shows practical configuration for fingerprinted static resources.

### 8.1. Directory Structure

~~~text
webflux-cache-control/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── DemoApplication.java
    │   ├── SecurityConfig.java
    │   └── CacheDemoController.java
    └── test/java/demo/
        └── CacheControlSecurityTest.java
~~~

### 8.2. settings.gradle

~~~groovy
rootProject.name = 'webflux-cache-control'
~~~

### 8.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

You need JDK 17+ and a compatible Gradle or project Gradle Wrapper. Spring Boot dependency management provides compatible Spring Framework/Security versions for the chosen Boot version. In real products, use a supported branch with the latest security patches per organizational policy.

### 8.4. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 8.5. SecurityConfig.java

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET, "/assets/app.v1.js")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/api/admin/statement")
                                .hasRole("ADMIN")
                        .pathMatchers(HttpMethod.GET,
                                "/api/profile/default",
                                "/api/profile/explicit")
                                .authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}readerpass")
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}adminpass")
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
~~~

**Intentional decisions:**

- Spring Security continues to manage **default security headers**. We **do not** call `headers.disable()` or `headers.cache(cache -> cache.disable())`.
- Public routes still receive default no-store when the controller does not set its own header. `permitAll` is purely an authorization policy; it does not make a route cacheable.
- The asset route has `permitAll`, yet still requires the controller to specify a public cache policy before browsers/CDNs have grounds to cache it.
- `/api/profile/...` requires authentication; `/api/admin/statement` requires ADMIN.
- `anyExchange().denyAll()` avoids accidentally exposing endpoints added later.
- There is no session login/form login in the demo; Basic is used to make testing 401/403 simpler.
- `{noop}` means unhashed passwords and must never be used in production. HTTP Basic must run over HTTPS; Base64 is only encoding.

**Do not set Cache-Control in SecurityConfig by disabling all defaults as a shortcut.** The goal of the demo is to let individual public routes override the policy while preserving all other default headers.

### 8.6. CacheDemoController.java

`src/main/java/demo/CacheDemoController.java`:

~~~java
package demo;

import java.time.Duration;
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class CacheDemoController {

    public record Profile(String accountId, String displayName) {
    }

    @GetMapping(path = "/public/ping",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicPing() {
        return Mono.just("pong");
    }

    @GetMapping("/api/profile/default")
    public Mono<Profile> defaultProfile() {
        return Mono.just(new Profile("DEMO-001", "Example Reader"));
    }

    @GetMapping("/api/profile/explicit")
    public Mono<ResponseEntity<Profile>> explicitProfile() {
        Profile payload = new Profile("DEMO-001", "Example Reader");
        return Mono.just(ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(payload));
    }

    @GetMapping(path = "/api/admin/statement",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<ResponseEntity<String>> statement() {
        return Mono.just(ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body("DEMO-SENSITIVE-STATEMENT"));
    }

    @GetMapping(path = "/assets/app.v1.js",
            produces = "application/javascript")
    public Mono<ResponseEntity<String>> publicAsset() {
        return Mono.just(ResponseEntity.ok()
                .cacheControl(CacheControl
                        .maxAge(Duration.ofDays(30))
                        .cachePublic())
                .body("console.log('static-demo-v1');"));
    }
}
~~~

Notable characteristics:
- `Mono<Profile>` on the default route adds no headers manually; the Spring Security WebFilter sets default cache headers when committing the response.
- `Mono<ResponseEntity<Profile>>` on the explicit route lets WebFlux resolve body and headers in the reactive flow. `CacheControl.noStore()` makes the policy explicit in the controller.
- `statement` preserves `no-store` for sensitive content even as the API evolves into real report exports.
- `publicAsset` sets `public, max-age=2592000` (30 days). The JS string is a **public constant** containing no personal data, and the URL is versioned as v1. When changing its content in the demo, bump the URL version to avoid stale cache.
- No `block()` or manual `subscribe()` calls.
- This uses dummy data only and is not an example of object/tenant ownership authorization. Production requires resource-level authorization in services.

**Important:** the 30-day public configuration is safe **only because this asset contains no private information**. An HTML template rendered with a user's name/email, or a JS file dynamically generated with tokens/secrets, **is no longer a public asset** even if its path starts with `/assets/`.

## 9. Running Examples with curl

In the directory containing `build.gradle`:

~~~bash
gradle bootRun
~~~

If the project includes a Wrapper, run `./gradlew bootRun` on macOS/Linux or `gradlew.bat bootRun` on Windows. By default the server listens on `http://localhost:8080`. This HTTP demo is for local personal use only; do not expose the demo API to the Internet.

### 9.1. Public Route Still Has Secure Cache Defaults

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Expected result:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
Content-Type: text/plain;charset=UTF-8

pong
~~~

Header order/casing and charset details may vary by Netty/Spring version. What matters is checking that `Cache-Control` includes `no-store`, not matching the entire response character-for-character.

**Why does a public route get no-store?** Because `permitAll` does not imply cacheable. Spring Security adds safe defaults whenever the application specifies no explicit policy.

### 9.2. Protected Route, No Credentials

~~~bash
curl -i http://localhost:8080/api/profile/default
~~~

Expected **401 Unauthorized**, typically with `WWW-Authenticate: Basic ...`. This error response should also carry a safe cache policy. Do not use `curl -I` as a direct substitute: it sends HEAD, whereas the demo security rules only list GET, so HEAD may be denied by a separate rule.

### 9.3. Protected Route with Valid Basic Auth, Using Defaults

~~~bash
curl -i -u reader:readerpass \
  http://localhost:8080/api/profile/default
~~~

Expected **200 OK**, body:

~~~json
{"accountId":"DEMO-001","displayName":"Example Reader"}
~~~

and `Cache-Control` containing `no-store` even though the controller did not add it. This is Spring Security's default response headers at work.

### 9.4. Protected Route with Explicit no-store

~~~bash
curl -i -u reader:readerpass \
  http://localhost:8080/api/profile/explicit
~~~

Expected `200 OK`, profile body as above, and:

~~~http
Cache-Control: no-store
~~~

**Do not require `Pragma: no-cache` and `Expires: 0` to always appear on this route**, since the controller set its own Cache-Control and Spring Security may omit the default set in that case.

### 9.5. Public Asset Selectively Cached

~~~bash
curl -i http://localhost:8080/assets/app.v1.js
~~~

Expected `200 OK`, body:

~~~javascript
console.log('static-demo-v1');
~~~

and a header with `max-age=2592000` and `public`, for example:

~~~http
Cache-Control: max-age=2592000, public
~~~

This is intentional: when a public asset is properly versioned, caching reduces load. Do not disable headers across the entire application.

### 9.6. ADMIN-Only Endpoint

~~~bash
# Authenticated reader lacking ROLE_ADMIN:
curl -i -u reader:readerpass \
  http://localhost:8080/api/admin/statement

# Authorized admin:
curl -i -u admin:adminpass \
  http://localhost:8080/api/admin/statement
~~~

Expected:
- Reader: **403 Forbidden**.
- Admin: **200 OK**, body `DEMO-SENSITIVE-STATEMENT`, `Cache-Control: no-store`.

Authorization remains mandatory even when the response already has a good Cache-Control header. `no-store` does not stop unauthorized users from calling the API; it only instructs caches not to store the response.

### 9.7. Observing Response Headers Through a Proxy/CDN

If the application runs behind a reverse proxy/CDN, run curl **against the public hostname** to observe the exact headers after all intermediaries. Headers observed on localhost/Netty do not prove the CDN is not adding or modifying `Cache-Control`.

When verifying, record:
- URL/method/status;
- `Cache-Control`;
- `Age` if present;
- `Vary`;
- CDN-specific headers like `X-Cache`/`CF-Cache-Status` if used;
- two calls from two different accounts;
- an unauthenticated request.

Note that a CDN may cache based on its own rules outside HTTP headers; that requires infrastructure configuration and cache-bypass policies.

## 10. Testing with WebTestClient

Spring Security Test provides `springSecurity()` configuration for `WebTestClient` when binding to an ApplicationContext. Verify both **status** and **cache headers**; this is a proper regression test aligned with the security goal.

`src/test/java/demo/CacheControlSecurityTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class CacheControlSecurityTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicEndpointStillHasSecureCacheDefault() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueMatches(
                        HttpHeaders.CACHE_CONTROL, ".*no-store.*")
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void protectedEndpointWithoutCredentialsIs401() {
        client.get().uri("/api/profile/default")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueMatches(
                        HttpHeaders.WWW_AUTHENTICATE, "Basic.*");
    }

    @Test
    void protectedProfileHasNoStoreByDefault() {
        client.get().uri("/api/profile/default")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueMatches(
                        HttpHeaders.CACHE_CONTROL, ".*no-store.*")
                .expectBody()
                .jsonPath("$.accountId").isEqualTo("DEMO-001");
    }

    @Test
    void explicitNoStoreOverridesDefaultSafely() {
        client.get().uri("/api/profile/explicit")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueMatches(
                        HttpHeaders.CACHE_CONTROL, ".*no-store.*")
                .expectBody()
                .jsonPath("$.displayName").isEqualTo("Example Reader");
    }

    @Test
    void versionedPublicAssetCanBeCached() {
        client.get().uri("/assets/app.v1.js")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueMatches(
                        HttpHeaders.CACHE_CONTROL, ".*max-age=2592000.*")
                .expectHeader().valueMatches(
                        HttpHeaders.CACHE_CONTROL, ".*public.*")
                .expectBody(String.class)
                .isEqualTo("console.log('static-demo-v1');");
    }

    @Test
    void readerCannotReadAdminStatement() {
        client.get().uri("/api/admin/statement")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminStatementMustNotBeStored() {
        client.get().uri("/api/admin/statement")
                .headers(h -> h.setBasicAuth("admin", "adminpass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueMatches(
                        HttpHeaders.CACHE_CONTROL, ".*no-store.*")
                .expectBody(String.class)
                .isEqualTo("DEMO-SENSITIVE-STATEMENT");
    }

    @Test
    void invalidPasswordIsRejected() {
        client.get().uri("/api/profile/default")
                .headers(h -> h.setBasicAuth("reader", "wrong"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

Expect **8 tests** to PASS when files/dependencies are created as described. This is an expectation based on code and API docs, **not a claim that the project was actually built/tested**.

A few notes:
- Default tests use `.valueMatches(..., ".*no-store.*")` rather than an exact full-string match, because directive ordering can vary.
- The asset test checks the exact Max-Age value for 30 days (**2,592,000 seconds**).
- The protected profile test verifies both the cache policy **and** that authentication works.
- The test where reader gets 403 does not prove all 403 error bodies have no-store; if error handlers/proxies are customized, add corresponding tests.
- `WebTestClient` tests do not fully simulate browser disk caches, BFCache, service workers, or CDNs; integration/E2E tests against the public endpoint are needed.

### 10.1. Why Only Test GET?

GET is the method most commonly evaluated by HTTP caches. However, **POST responses containing sensitive data still need appropriate headers**, even though cacheability differs from GET and depends on HTTP semantics. The demo is kept minimal to contrast policies; production should also test auth/reset-token endpoints, file downloads, and unsafe-method responses.

### 10.2. When an API Returns 401 or 403

Verify where the response is generated:
- 401 may come from Spring Security's authentication entry point.
- 403 may come from authorization or CSRF.
- 404/409/422 may come from WebFlux/controller advice.
- 5xx may come from the server or gateway.

For those responses, preserve appropriate policies whenever the body or context includes sensitive data. Controller annotations may not run when a SecurityWebFilter rejects a request before the controller, so test from the HTTP boundary.

## 11. Configuring Production Static Resources Instead of a Demo Controller

In real applications, JS/CSS/images are usually resources in `classpath:/static/assets/`, served by the WebFlux resource handler. This example **replaces** the demo's asset controller—do not add both for the same path:

~~~java
package demo;

import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class StaticAssetsConfig implements WebFluxConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/assets/")
                .setCacheControl(CacheControl
                        .maxAge(Duration.ofDays(365))
                        .cachePublic());
    }
}
~~~

This is a valid class when real resources and the WebFlux dependency exist; it is not a file to add to the current demo while `/assets/app.v1.js` is served by the demo controller.

**Notes:**
- In Spring Boot WebFlux, implementing `WebFluxConfigurer` typically does not require `@EnableWebFlux`; manually adding `@EnableWebFlux` can alter or disable parts of Spring Boot's default auto-configuration.
- Restrict the `/assets/**` path strictly to public content; never place user-data templates, private uploads, or token-bearing JSON in that directory.
- With 365-day caching, use content-hashed filenames and a build pipeline that renames files when assets change. Using a stable URL whose content changes causes clients to keep stale assets for a long time.
- You can use `ETag`/`Last-Modified` for static resources via WebFlux caching support, provided reusing the response is permitted.
- Spring Security still needs to permit the asset route in authorization rules. If `anyExchange().denyAll()` is active without a rule for `GET /assets/**`, requests will be denied before reaching the resource handler.

### 11.1. An Asset "Named .js" Is Not Automatically Public

Never public-cache a dynamically generated script like:

~~~javascript
window.currentUser = {
  email: "alice@example.test",
  token: "secret-value"
};
~~~

This is an **UNSAFE** example illustrating a leak; never embed user data or tokens inside static assets that CDNs might cache. Separate user data into a protected API returning `no-store`.

### 11.2. Where Do ETag and Last-Modified Fit?

For cacheable public resources, `ETag` or `Last-Modified` supports conditional requests returning `304 Not Modified` when the representation has not changed. This saves bandwidth while preserving freshness policies.

For sensitive content requiring `no-store`, do not design a default flow that "caches in the browser and sends If-None-Match to reuse"; that defeats the goal of avoiding stored copies. If a business case legitimately warrants private caching for certain data, perform a security review covering cache keys, user binding, revalidation, logout, and multi-account usage.

## 12. CDN/Reverse Proxy: Don't Just Check Controller Headers

Applications sit behind infrastructure:

~~~text
Browser
   |
   v HTTPS
CDN / Edge Cache
   |
   v HTTPS (or trusted internal hop)
API Gateway / Reverse Proxy
   |
   v
Spring WebFlux + Spring Security
~~~

Some CDNs have rules that **bypass origin Cache-Control**, "cache everything", override TTLs, or cache by path without distinguishing cookies/Authorization. In those cases, a response marked `no-store` on the backend **can still be mishandled** at the edge.

### 12.1. Operational Policies to Verify

- Routes such as `/api/me`, `/api/account/**`, `/api/admin/**`, and `/api/auth/**` must have CDN cache-bypass rules when serving sensitive data.
- If the CDN/cache key uses Host, path, query, or Authorization/cookies, audit that user A's data can never be served to user B.
- Do not rely solely on `Vary: Cookie`; inspect the CDN's own rules as well.
- Check cookie/session and token endpoints separately; `Set-Cookie` does not automatically disable caching.
- Verify whether the reverse proxy adds `Cache-Control: public` or overwrites `no-store`.
- For proxies with dedicated control headers like `Surrogate-Control`, follow vendor documentation and reviewed policies; that header does not replace standard `Cache-Control` in browsers.
- Gateway-generated responses (401/403/5xx) may bypass Spring Security; protect them if they contain sensitive details.
- Once sensitive data has been accidentally cached, **fixing headers afterward does not delete previously cached copies**; purge/invalidate the CDN and handle the incident appropriately.

### 12.2. Cross-User Repeat Verification

A strong security QA test case:

1. User A logs in and calls `GET /api/me` through the public hostname.
2. Verify A's response has `no-store` and no CDN HIT indicator.
3. User B, using a different session/credentials, calls the **exact same URL**.
4. Confirm B sees only B's data and never A's cached response.
5. An unauthenticated user calls the URL — receives 401/redirect per policy, never A's or B's body.
6. Log A out, retry the URLs, and verify no representation of A is reused.
7. Repeat across mobile browsers, shared-device browsers, and relevant edge regions.

Do not perform this test with real user data: use test accounts and synthetic data under safe procedures.

### 12.3. CDN Lifetime Differs from Browser max-age

You may have `s-maxage` for shared caches and `max-age` for general caches. A `public, s-maxage=600` policy suited for a public catalog is **unsuitable** for a private profile. Never "optimize CDN caching" on an authorized endpoint simply by increasing TTL.

## 13. Logout, the Back Button, and the Limits of no-store

Common scenario: a user opens their profile page, logs out, and clicks Back. Some UIs may show stale data from memory or browser state if the application does not clean up.

`Cache-Control: no-store` on responses containing sensitive data is an important safeguard, yet it has limits:

- Browsers may still retain **rendered state or SPA component state** in memory in certain scenarios.
- Modern browsers may evolve their BFCache policy for `no-store` pages; test on supported browser versions.
- Data written by the frontend to localStorage, IndexedDB, or the Cache API is not cleared when the server returns `no-store`.
- An already-open tab may still hold data fetched before logout, since the header does not "control" the app's live memory.
- Screenshots, clipboard copies, downloaded files, and logs cannot be revoked by Cache-Control.

A safer logout workflow:
1. Perform proper server-side logout/session invalidation/token revocation.
2. Set `no-store` on private responses (including HTML containing personal data).
3. Clear sensitive data from client state on logout, account switch, or token expiration.
4. Avoid storing raw tokens in localStorage if your threat model forbids it; follow an evaluated auth strategy.
5. On navigation/back, when needed, **revalidate authentication** and never reconstruct private views from persisted state.
6. Test thoroughly with Back/Forward, open tabs, reloads, offline mode, and multi-account scenarios.
7. Never treat pressing Back without seeing data in one browser as a guarantee across all browsers.

### 13.1. What Role Does Clear-Site-Data Play?

Some browsers support the `Clear-Site-Data` response header, e.g.:

~~~http
Clear-Site-Data: "cache"
~~~

Spring Security Reactive supports configuring this header in certain logout flows via `ClearSiteDataServerHttpHeadersWriter`. It is a **supplementary tool** to instruct the browser to clear supported data types within scope/policy, however:

- Browser support and behavior vary.
- The scope of cleared cookies/cache/storage must be chosen carefully to avoid breaking legitimate data of other apps on the same origin.
- This header does not guarantee clearing CDN caches, malicious clients, or prior copies.
- It does not replace `Cache-Control: no-store` on sensitive responses when data is being served.

Do not add `Clear-Site-Data` unconditionally to every response; it is typically reserved for explicitly designed flows such as logout.

### 13.2. Browser Fetch Cache Mode Differs from HTTP Response Cache Policy

Frontends can write:

~~~javascript
const response = await fetch("/api/me", {
  cache: "no-store",
  credentials: "same-origin"
});
~~~

This is a browser **request-side fetch cache mode**, not a mandatory response policy for all clients/proxies. Always **still** return `Cache-Control: no-store` from the server. Another script or HTTP client that omits that fetch option must still receive the proper policy when calling the API.

## 14. When Are private or no-cache Actually Reasonable?

Not every personal response requires an absolute ban on storage; sometimes an organization accepts short browser caching to improve UX.

For example, a low-sensitivity UI preferences page:

~~~http
Cache-Control: private, max-age=60
Vary: Accept-Language
~~~

This allows private caches to store up to 60 seconds while blocking shared caches, provided the policy has evaluated shared-device exposure. If the user switches accounts within 60 seconds, the UI must avoid reusing stale data; the app should clear related caches and bind data to the session/user.

For a public resource that updates frequently:

~~~http
Cache-Control: no-cache
ETag: "catalog-v12"
~~~

Browsers may store the representation, but must revalidate before using it. This is a good optimization for public content, **never to be copied for password resets/tokens/statements**.

### 14.1. Questions to Review Before Allowing "Private Cache"

Security/product teams should answer:
- Does the content contain PII or information sufficient to infer user activity?
- Might the device/browser be shared or a kiosk?
- Are there legal/internal compliance rules prohibiting local storage?
- Do clients switch between multiple logged-in accounts?
- Could a cached representation be served to the wrong user after login/logout?
- Does the response carry `Set-Cookie`, tokens, signed URLs, or sensitive metadata?
- Has the CDN/edge been proven not to store it under that policy?
- Could ETag/304 cause unintended reuse of a private response?

If you cannot answer confidently, **prefer `no-store` for sensitive data** instead of trying private caching merely for performance.

## 15. Common Mistakes When Configuring Cache-Control in WebFlux

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Thinking `no-cache` forbids storing the response | Browser can still store a copy and revalidate | Use `no-store` when storage must be prevented |
| Thinking `private` means "completely secured" | Browser/private caches can still store it | Use `no-store` for secrets |
| Treating `max-age=0` as equivalent to no-store | Caches can retain a stale representation | Distinguish freshness from storage |
| Using `public, max-age` on `/api/me` | Risk of sharing personal data via cache | Only public-cache truly public content |
| Thinking `Set-Cookie` automatically blocks CDN caching | RFC does not guarantee that | Send an explicit Cache-Control policy |
| Thinking `Authorization` alone protects all caches | Cookie auth, browser cache, and CDN rules differ | Classify policy by data sensitivity |
| Calling `headers.disable()` to cache CSS | Loses other security headers | Override only on the specific asset |
| Calling `headers.cache(cache -> cache.disable())` app-wide | Sensitive data loses default no-store | Keep defaults or replace with a complete policy |
| Confusing `HttpSecurity` with `ServerHttpSecurity` | Applies Servlet config wrongly to WebFlux | Use the Reactive API |
| Relying only on backend `@Cacheable` | Browsers/CDNs can still cache HTTP responses | Return explicit HTTP Cache-Control |
| Checking only `curl 200`, ignoring headers | Unknown whether response is cacheable | Assert `Cache-Control` in tests |
| Running `curl -I` and comparing status with GET | HEAD may be denied by a separate matcher | Test with the exact HTTP method |
| Caching a JS file containing tokens/user data | Exposes secrets via CDN/browser | Separate static assets from sensitive data |
| Setting 365-day TTL on unversioned asset URLs | Browsers serve stale files after deploys | Use fingerprinted filenames |
| Using `Vary: Cookie` as the sole security layer | Shared caches may be misconfigured | Use `no-store` + edge bypass policy |
| Expecting `Cache-Control` to clear localStorage | Has no effect on JS-managed storage | Clear client state per auth lifecycle |
| Ignoring BFCache/back button | UI may show stale data after logout | Test in browsers and clear state |
| Forgetting error responses/file downloads | Sensitive data in 4xx/5xx/PDF gets cached | Apply policies at every data-returning layer |
| Assuming HTTPS implies no-cache | HTTPS responses can still be cached | TLS and Cache-Control are separate layers |
| Testing only localhost, never via CDN | Edge may add or strip headers | Test public hostnames and cache rules |

## 16. Troubleshooting: Why Does Data Still Appear After Logout?

When users report "I logged out, hit Back, and still see the old page," check in order:

1. **What is the actual response `Cache-Control`?** Does HTML or JSON with sensitive data have `no-store`?
2. **Does the Spring Security chain cover the route?** Are there multiple chain matchers, or is the resource handled outside the security chain?
3. **Did another controller/handler set `Cache-Control: private/public`?** Spring Security may yield if the app already wrote the header.
4. **Is the HTML page a public shell or does it embed user data?** A static shell can be cached, but personalized responses should not.
5. **Is the data coming from HTTP cache or SPA memory/localStorage/IndexedDB?** Check DevTools Application/Network tabs.
6. **How does the browser handle BFCache?** Test Back/Forward across supported browsers and versions.
7. **Did logout actually invalidate/revoke the server session/token?** Cache headers do not alter access rights.
8. **Did the CDN record a cache HIT?** Test requests via the public URL and a different test account.
9. **Is a service worker serving a cached response?** Audit the Cache API and fetch handlers.
10. **Are `ETag`/`Last-Modified`/304 present on private data?** If the policy is no-store, review the conditional caching design.
11. **Is a proxy/WAF/gateway overwriting Cache-Control?** Observe both origin and edge.
12. **Does the app emit 401/403 responses before reaching controllers?** Test default security headers at entry points/denied handlers.
13. **Does frontend code persist responses in state?** Clear it on logout/account switch.
14. **Is there a response with Set-Cookie and personal data missing no-store?** Fix per RFC 9111.
15. **Did a stale cache entry exist prior to your fix?** You may need to purge the CDN and handle affected clients per incident policy.
16. **Does the response include `Age`/`Via`/vendor cache headers?** Use them to pinpoint which layer stored it.

### 16.1. Safe Logging When Debugging Caching

You may log method, route template, status, cache directives, and correlation IDs. Never log full response bodies containing PII, Authorization headers, Cookie/Set-Cookie values, session IDs, access tokens, or OTPs. When using logs to diagnose caching issues, the goal is to identify **policy and cache hit/miss**, not create yet another sensitive copy in logs.

### 16.2. Do Not "Fix" It by Disabling Caching System-Wide

If CSS/JS loads slowly because of default no-store, the proper fix is:
1. Identify the exact public resource namespace.
2. Version/fingerprint filenames.
3. Configure `Cache-Control: public, max-age=...` **only** for that namespace.
4. Keep `no-store` for APIs and user-specific HTML.
5. Run regression tests for both groups.

There is no need to disable all security headers to achieve a performance goal.

## 17. Cache Policy Design Checklist

### 17.1. APIs Containing Sensitive Data
- [ ] Private routes have `Cache-Control: no-store` at the public HTTP boundary.
- [ ] 401/403 responses and domain errors containing sensitive data are not improperly cached.
- [ ] Private PDF/CSV/attachment documents carry `no-store` when appropriate.
- [ ] No unintended `public` or shared-cache `s-maxage` on private routes.
- [ ] Responses with `Set-Cookie` do not rely on the cookie header to prevent caching.
- [ ] GET, HEAD, POST, logout, login, refresh, and token-reset flows have been evaluated.
- [ ] Security chains cover the proper routes; header writers are not unintentionally disabled.
- [ ] No application code overrides default no-store with a broader policy.
- [ ] Object/tenant authorization is enforced independently; no-store does not replace access control.

### 17.2. Static/Public Assets
- [ ] Assets are genuinely public and contain no profile/token/secret data.
- [ ] Filenames are versioned/hashed if using long TTLs.
- [ ] `Cache-Control` allows public caching only for approved asset groups.
- [ ] ETag/Last-Modified/304 are used appropriately for the resource.
- [ ] No stable URL with frequently changing content is marked `immutable`.
- [ ] WebFlux resource handlers and Spring Security authorization rules align.

### 17.3. Browser, CDN, and Operations
- [ ] Public hostname and origin backend return consistent response headers.
- [ ] CDN bypasses caching on account/auth/private routes, rather than relying solely on cache keys.
- [ ] Cross-account A/B tests confirm no response bleed.
- [ ] Logout, Back, Forward, reload, offline mode, and open tabs have been tested.
- [ ] SPA clears persisted private data on logout/user switch.
- [ ] Service Worker Cache API and IndexedDB are controlled.
- [ ] No logs/analytics capture sensitive responses.
- [ ] CDN purge/incident procedures exist in case of mis-caching.
- [ ] Supported browsers are tested alongside `WebTestClient` and curl.
- [ ] A 200 status alone is never taken as proof that cache policy is correct.

## 18. Self-Check Questions

**Q1.** Does `Cache-Control: no-cache` forbid browsers from storing profile JSON?

> No. `no-cache` permits caches to store the response, requiring revalidation before reuse. If the policy is do-not-store, use `no-store`.

**Q2.** Is `private, max-age=60` suitable for confidential documents on a shared computer?

> Not if storage must be forbidden. `private` only blocks shared caches; the browser may still retain a copy.

**Q3.** Why is `Set-Cookie` insufficient cache protection?

> Per RFC 9111, Set-Cookie does not automatically prevent HTTP caches from storing a response when other conditions permit it. Proper Cache-Control is required.

**Q4.** Which cache headers does Spring Security Reactive typically send by default?

> `Cache-Control: no-cache, no-store, max-age=0, must-revalidate`, along with `Pragma: no-cache` and `Expires: 0` when applied.

**Q5.** A controller sets `public, max-age=3600` on `/api/me`. Will Spring Security defaults definitely override it back to no-store?

> Do not rely on that. Spring Security may defer to a response that already has Cache-Control, so code review and tests are mandatory to catch unsafe policies.

**Q6.** In WebFlux, which class is used to set no-store on ResponseEntity?

> `org.springframework.http.CacheControl.noStore()` with `ResponseEntity.ok().cacheControl(...)`.

**Q7.** Why shouldn't you use `headers.disable()` just to cache CSS?

> It can turn off other security response headers. Override Cache-Control specifically on static assets instead.

**Q8.** Do default security headers guarantee that every public page is definitely blocked from caching?

> If the default security chain applies and no custom Cache-Control is present, `no-store` may be added; however, do not infer this solely from `permitAll` or the path name. Test the actual response.

**Q9.** Why doesn't service-layer `@Cacheable` replace HTTP Cache-Control?

> `@Cacheable` manages intermediate data on the server side, whereas HTTP Cache-Control instructs browsers/proxies/CDNs on caching HTTP responses.

**Q10.** Server logout already invalidated the session—is no-store still needed?

> Yes for private responses, to reduce the risk of HTTP caches retaining old content. Conversely, no-store does not replace session invalidation.

**Q11.** Does `no-store` erase an SPA's IndexedDB/localStorage?

> No. Those are client-managed storage mechanisms requiring separate cleanup along the auth lifecycle.

**Q12.** When can `public, max-age=31536000, immutable` be used?

> For genuinely public, immutable assets served at fingerprinted/versioned URLs; whenever content changes, emit a new URL.

**Q13.** A localhost curl GET shows the right headers—is that enough to conclude the CDN is safe?

> Not yet. You must call via the public hostname, inspect edge cache rules, and test across different accounts.

**Q14.** Is a response to a request carrying an Authorization header always safe regarding caching?

> No. While shared caches have specific rules, private caches can still store it; cookie-based auth, CDN overrides, and `public` responses require an independent data-driven policy.

**Q15.** Can `Pragma: no-cache` and `Expires: 0` replace `Cache-Control: no-store`?

> No. These are legacy compatibility/freshness mechanisms and do not express the full standard storage prohibition of `no-store`.

## 19. Summary and Implementation Principles

**Cache-Control is a security feature of HTTP responses, not merely a performance tool.** For sensitive content, the primary goal is reducing the ability of browsers/proxies/CDNs to store and reuse representations. In HTTP caching standards, the most critical directive is **`no-store`**; `no-cache` and `private` mean different things and are not equivalent.

In Spring Security Reactive, the default cache headers already include `no-store`. Never disable defaults just to cache CSS/JS; instead set a dedicated `Cache-Control` for public versioned resources using `CacheControl.maxAge(...).cachePublic()`. For account, statement, profile, token, or private file APIs, you can also explicitly set `CacheControl.noStore()` so the policy is clear directly in the controller.

Whenever modifying a cache policy, be sure to:
1. Determine response sensitivity, not just HTTP method or path.
2. Ensure Spring Security headers and application overrides do not conflict.
3. Verify both status **and Cache-Control** with WebTestClient/curl.
4. Test through the real CDN/reverse proxy if applicable.
5. Test logout, the Back button, and data stored by SPAs/Service Workers.
6. Maintain authentication, authorization, HTTPS, and client state cleanup as distinct layers.

### Official References

- Spring Security Reference — Security HTTP Response Headers (Reactive): https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html
- Spring Security Reference — Default Security Headers: https://docs.spring.io/spring-security/reference/features/exploits/headers.html
- Spring Framework Reference — HTTP Caching in WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux/caching.html
- Spring Framework Reference — WebFlux ResponseEntity: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html
- Spring Framework Javadoc — CacheControl: https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/http/CacheControl.html
- Spring Framework Reference — WebFlux Configuration: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Boot Reference — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
- RFC 9111 — HTTP Caching: https://www.rfc-editor.org/rfc/rfc9111
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110
- MDN — Cache-Control: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control
- MDN — Clear-Site-Data: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Clear-Site-Data