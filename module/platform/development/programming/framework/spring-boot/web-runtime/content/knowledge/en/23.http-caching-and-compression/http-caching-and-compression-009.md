# Never Publicly Cache Responses Containing Personal Information in Spring Boot

## 1. Why Can Caching Become a Data-Leakage Vulnerability?

A Spring Boot application has an endpoint `GET /api/me`. When Alice logs in, it returns Alice's name, email, permissions, or order data. When Bob logs in, the **same URL** returns a different body. If a CDN, reverse proxy, or gateway caches Alice's copy by URL and serves it back to Bob, Spring Boot's authentication becomes ineffective: Bob's request never even reaches the origin.

~~~text
Alice -- GET /api/me, Cookie A --> CDN -- MISS --> Spring Boot
                                 |               |
                                 |<-- Alice -----|
                                 |  wrong URL cache
                                 |
Bob -- GET /api/me, Cookie B ----> CDN -- HIT --> Alice's data
                                           (DATA LEAK)
~~~

This is not merely a stale-cache bug—it is a **cross-user data isolation breach**. The same consequences apply to payment info, addresses, financial reports, session-bearing HTML, or JSON containing credentials.

**Principle:** a response depending on user/tenant/authorization **must never be stored in a shared HTTP cache**. For sensitive content, the safe default is `Cache-Control: no-store`: instructing **neither shared caches nor private caches to store it**. For personal content allowed to remain on the user's browser, `private` forbids shared caches while still permitting browser storage.

“GET is idempotent”, “the URL is unique”, “the request has a cookie”, and “Spring Security is installed” **do not prove** a response is safe for public caching. You must examine the **entire body and headers**, response origin, every cache layer along the path, and account switching/logout.

## 2. Distinguish Cache Types Before Fixing

| Type | Example | Shared across multiple users? | Controlled by response `Cache-Control`? |
| --- | --- | --- | --- |
| Private HTTP cache | Browser memory/disk, single-user HTTP client | Normally only within that client/profile | Yes |
| Shared HTTP cache | CDN edge, proxy cache, API gateway response cache | Yes, by cache key and rules | Yes if compliant and not overridden |
| Application data cache | Spring `@Cacheable`, Redis object cache, in-memory map | Depends on code/keys | **No** |
| Service worker/browser app storage | Cache Storage, IndexedDB, localStorage | Within client app, separate lifecycle | **Not guaranteed** |
| Session store | Redis session/`HttpSession` | App nodes sharing server state | **No**; not an HTTP response cache |
| Logs/archives/analytics | Access logs, APM traces, downloaded files | Depends on infrastructure/permissions | **No** |

**Do not confuse HTTP caching with Spring Cache.** A response tagged `no-store` can still come from a backend `@Cacheable` with the wrong key. Conversely, a backend without Redis cache can still have HTTP responses mistakenly cached by a CDN.

HTTPS protects transport, yet a CDN terminating TLS and enforcing cache rules can still store responses; there is no private-caching guarantee just because a URL starts with `https://`.

## 3. Comparing Key Cache-Control Directives

| Directive in **response** | Effect on shared cache | Effect on private cache | Use for personal info? |
| --- | --- | --- | --- |
| `public, max-age=300` | Allowed to store and serve fresh for 300s | Allowed | **No** for personal responses |
| `private` | **Forbids shared cache from storing entire response** | May store | Only if browser copy is allowed |
| `private, max-age=60` | Forbids shared storage | May store up to 60s | Only for data safe to keep on client |
| `no-cache` | May store; must revalidate before reuse | May store and revalidate | **Insufficient** if storage is forbidden |
| `no-store` | **Must not intentionally store request/response** | **Must not intentionally store** | **Preferred for sensitive content** |
| `private, no-store` | Does not store | Does not store | Valid; `no-store` is already stricter |
| `max-age=0` | May store, immediately stale | May store | Cannot replace `no-store` |
| `must-revalidate` | Once stale, must revalidate before use | Same | Not a storage prohibition |
| `s-maxage=600` | Shared cache gets 600s TTL, overriding `max-age` | Not private cache TTL | **No** for personalized responses |
| `no-transform` | Forbids intermediaries from altering representation | Does not forbid caching | Does not replace `private/no-store` |

### 3.1. `no-cache` Does Not Mean “Do Not Store”

~~~http
HTTP/1.1 200 OK
Cache-Control: no-cache
Content-Type: application/json

{"email":"alice@example.test"}
~~~

A compliant cache **can still retain the body** and revalidate with the origin before reusing it. If the requirement is truly to leave no copy of PII in browsers/CDNs, the better directive is:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json

{"email":"alice@example.test"}
~~~

Under RFC 9111, `no-store` instructs caches not to **intentionally** store the request/response, yet does not guarantee wiping data already written to logs, extensions, screenshots, or non-compliant caches. TLS, authorization, and retention controls remain mandatory.

### 3.2. `private` Forbids **Shared** Caching, Not Browser Caching

~~~http
Cache-Control: private, max-age=120
~~~

Browsers may keep a private copy for up to two minutes if other cache rules allow. That is the difference from `no-store`. `private` does not encrypt data and does not protect when another user uses the same machine profile after logout.

RFC 9111 includes `private="Set-Cookie"` syntax restricting **only the named header field**; it does not forbid shared caches from storing the **body**. Therefore use parameterless `private` or `no-store` when the body contains PII.

### 3.3. `max-age=0, must-revalidate` Also Does Not Forbid Storage

~~~http
Cache-Control: max-age=0, must-revalidate
~~~

Caches can keep a stale copy and check again before using it. It does not satisfy “do not store responses”. To prevent storage, `no-store` is required.

### 3.4. Request vs. Response Cache-Control Differ

A client sending `Cache-Control: no-cache` on a **request** requests how caches handle that request; it **does not replace** the response directive Spring Boot must emit. Never rely solely on frontend `fetch(..., {cache: "no-store"})` while omitting headers at the origin. Traffic passing through CDNs/reverse proxies still needs the proper response policy.

## 4. Authorization, Cookie, and Set-Cookie Do Not Guarantee Privacy by Themselves

### 4.1. Requests with `Authorization`

RFC 9111 section `3.5` restricts shared-cache reuse for responses to requests carrying `Authorization`, **yet exceptions exist** when the response includes permitting directives, notably `public`, `s-maxage`, and `must-revalidate`.

~~~http
GET /api/me HTTP/1.1
Authorization: Bearer <Alice-token>
~~~

If the response accidentally includes:

~~~http
Cache-Control: public, s-maxage=1800
~~~

you cannot rely on the presence of a bearer token to assume shared caches won't reuse it. `must-revalidate` also **does not** substitute for `private` or `no-store` on personalized responses.

**Recommendation:** responses containing private data must always declare an explicit policy—at minimum `private`, and `no-store` for sensitive data—alongside CDN/gateway bypass.

### 4.2. Requests with `Cookie`

~~~http
Cookie: SESSION=<session-id>
~~~

Cookies do not share the same special shared-cache restriction as `Authorization` above. A session-authenticated response can still be mis-cached if gateway rules and Cache-Control permit it. Server-rendered HTML pages displaying “Hello, Alice” are especially easy to miss when a site-wide “cache HTML” rule is turned on.

### 4.3. Responses with `Set-Cookie`

The `Set-Cookie` header **does not automatically make a response non-cacheable** under HTTP caching standards. If a cacheable response carries a session cookie or user-specific body, proxies can introduce risk by storing/forwarding improperly.

Never let a response marked `public` contain per-user session IDs. Separate shared static pages/assets from session-setting APIs and personal data APIs, or design and verify edge behavior explicitly.

## 5. Why Doesn't `Vary: Cookie` Replace `private/no-store`?

`Vary` tells caches to inspect the named request headers when selecting a stored copy. `Vary: Accept-Encoding` is useful for gzip and uncompressed representations.

~~~http
Vary: Cookie
~~~

can make the variant key depend on Cookie, yet **is insufficient as a security control**:

1. It **does not forbid storing** responses in shared infrastructure.
2. CDNs may strip, normalize, or exclude Cookies from cache keys depending on config.
3. Multi-part cookies (session, analytics, experiments) produce infinite variants, inflating memory, cache misses, and log exposure risks.
4. Logout, session rotation, and permission changes do not automatically purge old entries.
5. A single matching bug, bypass, or override rule can serve Alice's copy to Bob.
6. For sensitive content, retaining a copy at the CDN already violates non-public-caching requirements.

Never use `Vary: Authorization` or a `userId` query parameter as an excuse to emit `Cache-Control: public` on profiles. Any data that is not genuinely public must be protected at both origin and edge.

## 6. Policy by Endpoint Category

| URL or response type | User-dependent? | Suggested headers |
| --- | --- | --- |
| `/assets/app.abcd1234.js`, fingerprinted CSS | No | `public, max-age=31536000, immutable` if URL changes when bytes change |
| `/assets/logo.svg` | No | `public, max-age=86400` depending on update frequency |
| Purely public `/api/catalog` | No | `public, max-age=300` |
| `/api/catalog` with member-specific pricing | Yes | Separate user pricing or `private/no-store` |
| `/api/me`, `/account` | Yes, PII | `no-store` |
| `/api/orders`, `/checkout` | Yes, sensitive | `no-store` |
| `/payment-methods` | Yes | `no-store` |
| `/login` with CSRF token or session state | Potentially | `no-store` |
| 401/403/404 with user-specific content | Potentially | `no-store` |
| 3xx redirect containing private state/tokens in URL | Potentially | `no-store`, avoid secrets in URLs |
| Owner-only file downloads | Yes | `no-store` and per-request auth |
| Truly public avatars | No | Cacheable via versioned URLs |

**Public HTML shell + private API** is a useful pattern: shared CSS, JS, and shell HTML can be cached; profile and transaction data are fetched separately with `no-store`. If you inject `"Welcome back, Alice"` directly into the cached HTML, the entire response becomes personalized.

## 7. Configuring Cache-Control on Spring MVC ResponseEntity

Spring Framework provides `org.springframework.http.CacheControl` and `ResponseEntity.cacheControl(...)`.

For private data:

~~~java
// Snippet inside a @RestController:
return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(personalProfile);
~~~

You can write `CacheControl.noStore().cachePrivate()` if you also want to express disallowing shared storage, though `no-store` alone is already stricter.

For **genuinely public** content:

~~~java
return ResponseEntity.ok()
        .cacheControl(
                CacheControl.maxAge(Duration.ofMinutes(5))
                        .cachePublic())
        .body(commonCatalog);
~~~

This emits `max-age=300` and `public`. Do not use global annotations or filters that attach `public` to every GET.

Alongside `Cache-Control`, you can add:

~~~http
Pragma: no-cache
Expires: 0
~~~

to support legacy clients. These are **supplementary headers**, not replacements for `no-store`. Especially avoid multiple middlewares writing conflicting Cache-Control values without testing the final header.

## 8. Runnable Project: Java 17 + Spring Boot MVC + Security

The example has two lab users Alice/Bob and two endpoints:

- `GET /api/catalog` is public, identical for all users, and cacheable.
- `GET /api/me` requires HTTP Basic, returns username from `Principal`, **no-store**.

**HTTP Basic on localhost is strictly for lab use.** Production must use HTTPS and securely managed identity/password/secret systems; never ship demo passwords into real systems.

### 8.1. Structure and Gradle

~~~text
cache-privacy-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/cache/CachePrivacyApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/cache/CachePrivacyTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'cache-privacy-lab'
~~~

`build.gradle` (Spring Boot 3.3.13 is an example 3.x version; real projects should use a supported version):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8080
~~~

### 8.2. Java Source

`src/main/java/demo/cache/CachePrivacyApplication.java`:

~~~java
package demo.cache;

import java.security.Principal;
import java.time.Duration;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CachePrivacyApplication {
    public static void main(String[] args) {
        SpringApplication.run(CachePrivacyApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
                .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-password"))
                .roles("USER")
                .build();
        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("bob-password"))
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/catalog").permitAll()
                .anyRequest().authenticated());
        http.httpBasic(Customizer.withDefaults());
        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }
}

@RestController
class CachePrivacyController {
    @GetMapping("/api/catalog")
    ResponseEntity<Map<String, Object>> catalog() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl
                        .maxAge(Duration.ofMinutes(5))
                        .cachePublic())
                .body(Map.of(
                        "product", "Java Handbook",
                        "price", 100));
    }

    @GetMapping("/api/me")
    ResponseEntity<Map<String, String>> profile(Principal principal) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .header(HttpHeaders.PRAGMA, "no-cache")
                .header(HttpHeaders.EXPIRES, "0")
                .body(Map.of(
                        "viewer", principal.getName(),
                        "kind", "personal"));
    }
}
~~~

Explanation:

1. `Principal` is authenticated by Spring Security rather than trusting an arbitrary user ID header from the client.
2. `SessionCreationPolicy.STATELESS` only affects how demo auth stores sessions; it does **not** exempt personal data from needing `no-store`.
3. `/api/me` returns `no-store`; `Pragma` and `Expires` are added for compatibility.
4. `/api/catalog` is public and independent of username, so controlled caching is permitted.
5. If catalog later includes per-user pricing, experiment cookies, or "Hello Alice", the `public` policy must be removed/changed.
6. `Map.of` does not guarantee JSON field order; tests assert by key.
7. In-memory users/passwords are strictly for the lab. Never log credentials, and never put real sessions/PII into examples.

### 8.3. Run and Observe

Once the Gradle wrapper is set up for the project:

~~~bash
./gradlew bootRun
~~~

PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Test public endpoint:

~~~bash
curl -i http://localhost:8080/api/catalog
~~~

Expected key lines (header/JSON key ordering may vary):

~~~http
HTTP/1.1 200 OK
Cache-Control: max-age=300, public
Content-Type: application/json

{"product":"Java Handbook","price":100}
~~~

Test Alice:

~~~bash
curl -i -u alice:alice-password http://localhost:8080/api/me
~~~

Expected:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Pragma: no-cache
Expires: 0
Content-Type: application/json

{"viewer":"alice","kind":"personal"}
~~~

Test Bob on the **same URL**:

~~~bash
curl -i -u bob:bob-password http://localhost:8080/api/me
~~~

Expect body `"viewer":"bob"`, still `Cache-Control: no-store`. Call unauthenticated:

~~~bash
curl -i http://localhost:8080/api/me
~~~

Spring Security normally returns **401 Unauthorized**, never any user's profile. Check cache policies on 401/error paths in real environments too.

## 9. Automated Spring MVC Testing with MockMvc

To prevent regressions from developers accidentally altering headers, add tests. File `src/test/java/demo/cache/CachePrivacyTest.java`:

~~~java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CachePrivacyTest {
    @Autowired
    MockMvc mvc;

    @Test
    void aliceHasNoStore() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "alice-password")))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, containsString("no-store")))
            .andExpect(jsonPath("$.viewer").value("alice"));
    }

    @Test
    void bobHasNoStoreAndHisOwnBody() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("bob", "bob-password")))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, containsString("no-store")))
            .andExpect(jsonPath("$.viewer").value("bob"));
    }

    @Test
    void unauthenticatedCannotReadProfile() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void catalogIsExplicitlyPublic() throws Exception {
        mvc.perform(get("/api/catalog"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, containsString("public")))
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, containsString("max-age=300")));
    }
}
~~~

Run command:

~~~bash
./gradlew test --tests demo.cache.CachePrivacyTest
~~~

Tests verify both **per-user bodies** and **`no-store` policies**. Checking only status 200 lets caching bugs slip through. Note that `MockMvc` runs at the origin and **does not simulate CDNs/proxies**, so staging integration tests across real network paths are still required.

## 10. Spring Security Default Headers Do Not Replace Response Classification

Spring Security normally adds protective anti-cache headers:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

This is a helpful default. However, if the application explicitly sets `Cache-Control`, security header writers usually **respect the application's policy** so public assets can be cached. Consequently:

- A developer can accidentally attach `Cache-Control: public` to a profile page.
- A `SecurityFilterChain` might not cover the endpoint you think it covers.
- Disabling cache-control headers **globally** just to cache CSS/JS strips away protective defaults.
- API error pages, redirects, static handlers, and template engines can emit headers different from success controllers.
- A CDN may rewrite headers after Spring Boot already emitted no-store.

**Verify the final response**, rather than assuming having `spring-boot-starter-security` makes every route safe.

## 11. Preserving `no-store` on Error Responses, Redirects, and Private HTML

Not only `200 OK` can contain PII. For example:

- `401/403` bodies containing emails or user info.
- `404` displaying unauthorized record/order IDs.
- `500` returning stack traces or SQL/debug data.
- `302` redirects carrying state/session/one-time tokens in the URL.
- Server-rendered HTML pages displaying the logged-in user's name/account.
- File downloads with private names or sensitive content.
- `304` responses or cache metadata computed wrongly per identity.

A **route/boundary policy** should prevent public caching across all responses on private branches. Controllers use `ResponseEntity.cacheControl(CacheControl.noStore())` for success responses, and a defensive filter can apply headers before they commit.

Snippet for **Spring MVC Servlet**, inside a class extending `OncePerRequestFilter` and properly registered:

~~~java
@Override
protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain)
        throws ServletException, IOException {

    String path = request.getServletPath();
    if (path.equals("/api/me")
            || path.startsWith("/api/account/")
            || path.startsWith("/api/orders/")) {
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("Pragma", "no-cache");
        response.setHeader("Expires", "0");
    }

    chain.doFilter(request, response);
}
~~~

**Not a standalone runnable class:** the snippet needs Jakarta Servlet imports, Spring Web, and class/filter registration. Test with the Spring Security chain, error dispatches, and context paths.

If a controller or proxy later **overwrites** Cache-Control to `public`, setting it early in a filter is not enough. You need final-response tests and clear boundary policy enforcement. Never let exception handlers leak PII merely because `no-store` is present.

## 12. WebFlux: Same Cache-Control, Different Processing API

WebFlux uses `Mono`/`Flux` and `ServerWebExchange`; HTTP headers retain identical semantics. Illustrative snippet inside an authenticated WebFlux `@RestController`:

~~~java
@GetMapping("/api/reactive-me")
Mono<ResponseEntity<Map<String, String>>> me(
        Mono<Principal> principal) {

    return principal.map(p ->
            ResponseEntity.ok()
                    .cacheControl(CacheControl.noStore())
                    .body(Map.of("viewer", p.getName())));
}
~~~

This is a method snippet, not a standalone Java class. `Principal` must come from real security config; if unauthenticated, handle 401/403 per policy.

`WebFilter` snippet to attach no-store **before response commit**:

~~~java
// Add to real WebFlux configuration:
return (exchange, chain) -> {
    String path = exchange.getRequest()
            .getPath().pathWithinApplication().value();

    if (path.equals("/api/reactive-me")
            || path.startsWith("/api/private/")) {
        exchange.getResponse().getHeaders()
                .setCacheControl("no-store");
    }
    return chain.filter(exchange);
};
~~~

Do not use `HttpServletResponse`/`OncePerRequestFilter` to control pure Netty WebFlux. Verify reactive Spring Security headers and final responses under the same principles as Servlet.

**Reactor `Mono.cache()` and Spring `@Cacheable` are application-layer caches.** They can return user A's data to B if a shared Publisher or cache key is wrong, regardless of response no-store. Never cache a single global `Mono<UserProfile>` across all users.

## 13. CDN and Reverse Proxy: Whitelist Only Public Resources

Typical path:

~~~text
Browser
   |
   v
CDN edge cache
   |
   v
API gateway / reverse proxy / ingress
   |
   v
Spring Boot origin
   |
   v
Database / Session store
~~~

Origin `Cache-Control: no-store` is a contract with compliant caches, yet some CDNs have “cache everything” modes, forced TTLs, cache keys omitting Cookie/Authorization, edge workers rewriting headers, or rules ignoring origin headers. **Audit the exact product configuration in use**.

Recommended deployment rules:

1. **Bypass both lookup and storage** on `/api/me`, `/api/account/**`, `/api/orders/**`, checkout, payment, auth, private downloads, and admin.
2. Permit caching on fingerprinted `/assets/**`, public images/logos, and APIs whose bodies are verified **identical for every user**.
3. For requests carrying Authorization/session cookies, bypass by default except on endpoints reviewed and proven public.
4. Avoid caching responses containing Set-Cookie or user-specific details, even though Set-Cookie does not itself forbid HTTP caching.
5. Never rely on `Vary: Cookie` alone and never log raw session cookies in CDN cache-key logs.
6. Inspect response headers **after the CDN** to catch overridden origin headers; check `Age`, `Cache-Status`, `Via`, or vendor `X-Cache` if available.
7. Know that some CDNs omit hit headers, so “absence of Age” does not prove caching was bypassed.

### NGINX Snippet: Skip Reading Old Cache and Skip Writing New Cache

This example assumes an `upstream spring_backend` and `proxy_cache` are defined elsewhere, **not a standalone NGINX config**:

~~~nginx
location /api/me {
    proxy_pass http://spring_backend;
    proxy_cache_bypass 1;
    proxy_no_cache 1;
}

location /api/orders/ {
    proxy_pass http://spring_backend;
    proxy_cache_bypass 1;
    proxy_no_cache 1;
}
~~~

- `proxy_cache_bypass 1` skips looking up existing cache entries.
- `proxy_no_cache 1` prevents storing new responses.
- Verify exact path matching (including trailing slashes, queries, routing) and confirm any CDN **in front of** NGINX has matching rules.
- Do not copy this snippet verbatim onto cloud/CDN platforms using different rule models.

The safe pattern is **allowlist-based public caching**, not “cache all GETs” and patching PII endpoints after incidents happen.

## 14. ETag, If-None-Match, and 304: Revalidation Does Not Guarantee User Isolation

A cache can hold a representation and send a conditional request:

~~~http
GET /api/report HTTP/1.1
If-None-Match: "v5"
~~~

If the origin returns:

~~~http
HTTP/1.1 304 Not Modified
ETag: "v5"
Cache-Control: private, max-age=0, must-revalidate
~~~

the client/cache can reuse the stored copy per rules. For private data:

- If the requirement is **do not store**, use `no-store` and avoid reuse paths on shared caches.
- If **private browser caching is permitted**, ETags must reflect the representation for **that specific user and permissions**, never sharing a global `"v5"` across differing bodies.
- When switching accounts in the same browser, a validator/cache key not scoped to identity can cause wrong 304s showing old data.
- `Vary: Accept-Encoding` distinguishes encodings; `Vary: Cookie` does not replace `private/no-store`.
- If data was ever publicly cached by mistake, fixing headers **does not erase** old cache entries. You must purge the CDN.

Spring MVC supports ETag/Last-Modified and resource caching, yet never turn on a global ETag mechanism for all personalized responses without reviewing representation keys and security policy.

## 15. HTTP Compression Differs from Caching; Carries Its Own Side-Channel Risks

**Compression** (`Content-Encoding: gzip`, `br`, etc.) reduces transferred bytes. **Caching** decides whether responses may be stored. An HTTP response can be compressed yet unstored:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Encoding: gzip
Vary: Accept-Encoding
Content-Type: application/json
~~~

`Vary: Accept-Encoding` only separates compressed/uncompressed variants; it **does not** isolate users. `no-transform` forbids intermediaries from altering representations; it **does not** forbid caching.

Spring Boot has compression settings:

~~~properties
server.compression.enabled=true
server.compression.min-response-size=2KB
~~~

This is not caching configuration. When secrets and attacker-influenced data share a compressed response, compressed size changes can create **BREACH**-style side channels. `no-store` does not prevent this side channel. Evaluate disabling compression on sensitive endpoints, separating secrets from reflected content, and applying CSRF/security controls.

Do not conclude “gzipped response ⇒ CDN cached” or “no-store ⇒ gzip disabled”.

## 16. Logout, Browser History, Service Workers, and Stored Data

`no-store` helps prevent compliant private/shared HTTP caches from storing responses, yet **does not guarantee erasing all displayed content**:

1. Logout must invalidate sessions/tokens on the server per policy; deleting browser cookies alone is insufficient if old tokens remain valid.
2. `localStorage`, IndexedDB, service worker Cache Storage, or SPA state managers can retain PII; apply dedicated lifecycles and clear on logout/account switch.
3. Browser history, back-forward cache (bfcache), UI snapshots/extensions have browser-dependent lifecycles; never promise no-store wipes all traces. Recheck authentication/identity when restoring UI state.
4. `Clear-Site-Data: "cache"` can help on logout in supporting browsers, yet has scope limits and **does not purge CDNs**.
5. For shared machines, enforce conservative cache policies, HTTPS, `Secure`/`HttpOnly`/`SameSite` cookies, session revocation, and proper CSRF/authorization.

No-store does not change API access rights or bearer token validity; both caching policies and security controls are required.

## 17. Spring `@Cacheable` Can Leak Data Right at the Origin

A **broken** example:

~~~java
// Anti-pattern: zero-argument method can share one cache key.
@Cacheable("profiles")
public Profile currentProfile() {
    return repository.findById(currentUserId());
}
~~~

If Alice calls first, Alice's profile gets stored under a shared key; when Bob calls next, he receives Alice's object. Even with HTTP `Cache-Control: no-store`, the data is already mixed up **before reaching the CDN**.

Conceptual fix with explicit key (snippet, not a complete class):

~~~java
@Cacheable(cacheNames = "profiles", key = "#userId")
public Profile loadProfile(String userId) {
    return repository.findById(userId).orElseThrow();
}
~~~

Even `userId` alone may be insufficient if data partitions by tenant/role/permission. Authorization must be checked **before serving cache hits**, keys must include every dimension affecting the response, and invalidation must trigger when roles/profiles change. For highly sensitive data, avoid application-layer caching altogether.

**`spring.cache.*` is not HTTP Cache-Control configuration.** Treat Spring Cache/Redis/CDN/browsers as distinct layers with separate security models.

## 18. End-to-End Testing with Two Users and Proxy/CDN

Origin `MockMvc` tests are in place; next test the staging route **through the real CDN and load balancer** using two dummy accounts with distinct PII markers.

| Scenario | Expected |
| --- | --- |
| Alice calls `/api/me` at origin | no-store and Alice's body |
| Bob calls the same URL at origin | no-store and Bob's body |
| Alice/Bob call through CDN | No cross-user body reuse; private responses never shared-cache HIT |
| 401/403 on private routes | No PII leaked and no public caching |
| 500 error on private routes | No public caching or debug data leaked |
| Profile role/session changes | Old copy never shared-cache reused |
| With compression enabled | Cache-Control stays no-store |
| Conditional 304 | Never reuses another user's representation |
| Public catalog | Cacheable if body is truly identical for all |
| Catalog with member discount | Must change policy / split endpoints |
| Logout, switch accounts in same browser | Previous user's data not displayed |
| CDN force-cache enabled on staging test | Test must catch wrong policy |

Inspect headers across staging (placeholder token; never paste real credentials into docs/tickets):

~~~bash
curl -sD - -o /dev/null \
  -H "Authorization: Bearer <staging-token-A>" \
  https://staging.example.test/api/me
~~~

Inspect response bodies of both accounts safely and verify `Cache-Control` on the **final response delivered to clients**. `Age`, `Cache-Status`, `Via`, and `X-Cache` aid diagnosis, though not every CDN emits the same headers; absence of `Age` does not prove bypass. Cross-check edge caching rules and cache-hit metrics.

Never test with real customer data and never save raw Authorization/session IDs into public cURL logs.

## 19. Warning Signs and Remediation

| Warning sign | Cause | Remediation |
| --- | --- | --- |
| Bob sees Alice's profile | CDN/shared cache key omitted auth/cookies or public policy | Bypass, purge, incident investigation |
| Response has only `no-cache`, yet browser stores it | `no-cache` allows storage | Use `no-store` when storage must be forbidden |
| `max-age=0` present, yet proxy holds cache entry | `max-age=0` does not forbid storage | Use appropriate `private`/`no-store` |
| `Vary: Cookie` present, yet CDN retains PII | Vary does not forbid storage | Bypass shared cache and set `no-store` |
| Response with bearer Authorization gets publicly cached | Permitting directive present or CDN override | Audit response Cache-Control and edge config |
| Set-Cookie present, yet stored at proxy | Set-Cookie alone does not forbid caching | Separate responses, apply no-store/bypass |
| Spring Security defaults protect, yet controller writes `public` | App overrode Cache-Control | Test final headers at origin/edge |
| 401/500 lacks `no-store` | Headers set only in success controllers | Enforce route-level policy and test error paths |
| After logout, screen still shows old data | bfcache, service worker, client state/storage | Reset UI, invalidate session, set no-store |
| Spring `@Cacheable` returns wrong user's data | Key missing user/tenant/authorization | Fix application caching, auth, and invalidation |
| `304` reuses another user's copy | ETag/cache key not scoped to identity | Fix validators or skip caching PII |
| `Content-Encoding: gzip` appears | Compression is enabled | Evaluate compression and side-channels separately |
| CDN reports HIT on PII endpoint | Force-cache rule or broken bypass | Investigate/purge and block caching |

## 20. When Personal Information Was Accidentally Public-Cached

Do not just patch the origin header to `no-store` and stop: **stale entries can survive until TTL expires**, some edges have stale-serving rules, and copies already sent to other users cannot be recalled.

1. **Stop bleeding:** disable caching/enable bypass on the private route immediately, fix origin `no-store`, and inspect final responses.
2. **Purge/invalidate** cached entries on CDN/proxies by URL/key/tag or appropriate scope; never assume new headers erase existing cache entries.
3. **Assess blast radius:** endpoints, time window, edges, cache-hit logs, affected accounts; minimize copying PII into incident tracking systems.
4. **Assess credential exposure:** if session tokens/OTPs/bearer tokens could have leaked, revoke/rotate per security incident plan.
5. **Escalate** to security/privacy/operations and follow applicable policies/regulations based on verified impact.
6. **Add regression tests** for 200/304/401/403/500, two users on the same URL, CDN hit/miss, logout, rolling deploys, and proxy rules.
7. **Check other caches** (`@Cacheable`, service workers, app state), because fixing HTTP headers does not protect them.

Use synthetic data with distinct markers to reproduce; there is no need to broadcast real customer PII across the team to prove the bug.

## 21. Pre-Release Review Checklist

- Does the response contain PII, tokens, transaction numbers, emails, names, addresses, sensitive content, or private redirects?
- Does content depend on identity, cookies, bearer tokens, tenant, tier, experiment, permissions, or session?
- Is Cache-Control on private routes strictly `no-store`/`private` as needed, with no conflicting `public`/`s-maxage`?
- Do CDNs and reverse proxies bypass both **cache lookup** and **storage** on private paths?
- Is anyone falsely relying on `Vary: Cookie`, Set-Cookie, or Authorization to assume public caching is safe?
- Are ETags, 304s, and cache keys scoped to per-user representations?
- Do middleware/controllers accidentally override Spring Security defaults; are error/login/logout responses protected?
- Have compression and caching been reviewed separately; is there any side-channel risk on secret-bearing responses?
- Do Service Workers, localStorage, IndexedDB, and client app state retain data after logout?
- Do `@Cacheable`/Redis internal caches include proper user/tenant keys and authorization checks?
- Are both origin unit/MockMvc tests **and** two-user staging tests via the CDN in place?
- Are purge/incident plans and deploy-time rule audits ready?

## 22. Self-Check Questions

**1.** `GET /api/me` returns two bodies for Alice/Bob; can it be publicly cached if `Vary: Cookie` is added?

**Answer:** No. Vary does not forbid storage, CDNs can mishandle it, and shared caches still hold PII. Use `no-store` (or `private` if browser caching is acceptable) and bypass shared caches.

**2.** Does `no-cache` forbid writing data to disk cache?

**Answer:** No. It allows storage and only requires revalidation before reuse. `no-store` is the directive that forbids intentional storage.

**3.** With Spring Security enabled, why must `Cache-Control` on `/api/me` still be tested?

**Answer:** Security defaults may not override headers set by the app, or CDNs may apply their own rules. Verify the final response, not just dependencies.

**4.** Does a response containing `Set-Cookie` get blocked from caching automatically by the RFC?

**Answer:** No. Explicit `Cache-Control` policies and CDN bypass are required; Set-Cookie is not a `no-store` directive by itself.

**5.** A profile has `no-store` and `Content-Encoding: gzip`; is there a contradiction?

**Answer:** No: compression and caching are independent. Still, evaluate side-channel risks from compressing secrets.

**6.** Origin was fixed to `no-store`, yet the CDN previously mis-cached it; is a purge required?

**Answer:** Yes, because new headers do not retroactively delete old entries. Perform incident handling, scope assessment, and regression tests.

**7.** Controller returns `no-store`, yet `@Cacheable` has a shared key; is it safe?

**Answer:** No. Data can leak across users right at the origin; HTTP `no-store` does not fix backend cache keys.

**8.** Does `must-revalidate` replace `private` for personalized responses?

**Answer:** No. It does not forbid storage, and RFC 9111 permits certain shared caching of authenticated responses with that directive under specific conditions.

## 23. Official References

- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): `3.5` authenticated requests, `5.2` Cache-Control directives, `4.1` Vary, `4.3` revalidation.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): request methods, statuses, representations, and validators.
- [Spring Framework 6.1 — CacheControl API](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/http/CacheControl.html): `noStore()`, `cachePrivate()`, `cachePublic()`, `maxAge()`.
- [Spring Security — Default HTTP Response Headers](https://docs.spring.io/spring-security/reference/features/exploits/headers.html): default response headers and when app overrides apply.
- [Spring Security — Servlet HTTP Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): cache control in Servlet.
- [Spring Security — Reactive HTTP Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html): cache control in WebFlux.
- [Spring Framework — Web MVC HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): ETag, Last-Modified, and conditional requests.
- [Spring Boot — Web Servlet](https://docs.spring.io/spring-boot/reference/web/servlet.html): web runtime config, static resources, and compression.

**Remember:** `private` forbids shared caches while still permitting private caches, `no-cache` allows storage with revalidation, and **`no-store` forbids storage in both compliant shared and private HTTP caches**. For responses containing personal data, never use `public`/`s-maxage`; verify Spring Boot, CDNs/proxies, and application caches alike.