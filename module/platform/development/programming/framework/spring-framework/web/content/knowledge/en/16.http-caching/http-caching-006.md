# Vary, Personalized Content, and Avoiding Accidental Private Data Caching in HTTP

## 1. The Problem: Same URL, Two Users, Two Results

A Spring MVC API has the endpoint `GET /api/me`. When Alice logs in, the server returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"user":"alice","displayName":"Alice"}
~~~

Bob calls the **same URL**, yet the result must be:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"user":"bob","displayName":"Bob"}
~~~

If a shared cache at a CDN, reverse proxy, or HTTP intermediary keys solely by URL and accidentally reuses Alice's response for Bob, that is a **cross-user data leak**. This bug does not necessarily live in the controller, because the controller may never have received Bob's request: an upstream cache answered on its behalf.

In HTTP, `Vary` and `Cache-Control` have distinct responsibilities:

- **`Vary`** declares which **request headers** cause the representation to change; caches must account for them when deciding whether a stored response may be reused.
- **`Cache-Control: private`** specifies that the response may only be stored in a client's private cache, **not** in a shared cache.
- **`Cache-Control: no-store`** instructs HTTP-compliant caches **not to store** the associated response/request.
- **Authentication/authorization** must verify who is calling and what data they may view; cache directives **do not replace** permission checks.

**Core takeaway:** do not fix private data leaks by adding `Vary: Cookie` and continuing to let CDNs cache personalized content unchecked. For sensitive data, establish a **no-store** or **private-only** policy first, and only optimize caching when safety is proven.

### Learning Outcomes

After this lesson, you will:
1. Distinguish a private cache (browser) from a shared cache (proxy/CDN).
2. Understand cache keys, `Vary`, `Cache-Control`, and their relationship with `Accept-Language`, `Accept-Encoding`, and `Origin`.
3. Know why `Cookie`, `Authorization`, and `Set-Cookie` do not automatically guarantee a response is only ever served to the right user.
4. Pick `no-store`, `private`, `no-cache`, `max-age`, `s-maxage`, and `public` appropriately.
5. Build Spring MVC controllers using `ResponseEntity` and `CacheControl` to emit explicit policies.
6. Test two users, languages, and headers with MockMvc, then verify against a real CDN/reverse proxy upon deployment.
7. Prevent ETags, 304 responses, service workers, browser history, or application caches from leaking data even when HTTP headers are right.

This lesson uses Java 17+, Spring Boot 3.x / Spring Framework 6.x. The concrete example uses Spring Boot 3.3.5, Spring MVC Servlet stack, and Spring Security HTTP Basic. HTTP rules follow **RFC 9111**, not a Spring-specific feature.

## 2. Four Commonly Seen Cache Layers

~~~text
Alice's Browser
   |
   +-- Browser HTTP cache / memory cache (private)
   |
   +-- Service worker / Cache Storage if deployed by the app
   |
   v
CDN / reverse proxy / API gateway (shared or managed cache)
   |
   v
Spring MVC application
   |
   +-- Application data cache (e.g. @Cacheable/Redis)
   |
   v
Database / other services
~~~

### 2.1. Browser HTTP Cache

This is typically a **private cache** tied to one client. Under HTTP caching semantics, it may retain `Cache-Control: private` responses. However, shared computers, shared browser profiles, or post-logout state still pose risks: `private` does not mean data **vanishes from the user's device**.

### 2.2. Shared Cache

A CDN, proxy, or reverse proxy shares resources across many clients. This is where response reuse saves significant cost, while simultaneously becoming dangerous if cache keys fail to reflect per-user differences.

Examples:
- A logo image identical for everyone: a shared cache is a sensible candidate.
- `/api/me` reflecting the current user: must never be accidentally shared-cached.
- Public news in Vietnamese/English: can be shared-cached by `Accept-Language` when designed properly.
- Internal reports varying by permissions: should use `private` or `no-store` depending on sensitivity and policy.

### 2.3. Spring/Service Cache Is Not an HTTP Cache

`@Cacheable` (Spring Cache abstraction) stores **method return values** by cache key in the JVM/Redis/...; it **does not emit `Cache-Control`, understand `Vary`, or isolate data by principal automatically**.

If a service uses:

~~~java
// WRONG when result varies by user yet key is just "summary":
@Cacheable(cacheNames = "reports", key = "'summary'")
public Report summaryForCurrentUser() { ... }
~~~

This is an illustrative broken fragment, not runnable code from the app below. When Alice calls first, the method cache can hand Alice's report to Bob **right inside the backend**, even if the HTTP response carries `Cache-Control: no-store`. You need cache keys scoped by user/tenant/permission, authorization before returning, or no caching at all. HTTP cache headers cannot fix internal backend caching bugs.

### 2.4. Service Workers, Frontend Stores, and Managed CDNs Have Their Own Logic

JavaScript `Cache API`, `localStorage`, state stores, service worker offline caches, client-side GraphQL caches, and custom CDN rules do not necessarily follow the same storage rules as the browser's HTTP cache. You must design **every** layer capable of storing data. Do not merely add `no-store` on the backend and assume existing copies in service workers or local storage disappear on their own.

## 3. Default Cache Keys and Why the URL Is Not Enough

A typical HTTP cache considers at least the request method and target URI, status/header storage eligibility, response freshness, and the headers named in `Vary`.

~~~text
Primary key (conceptual): target URI + relevant request method
Secondary selection: request headers listed by the stored response in Vary
+ cache policy/status/freshness/revalidation
~~~

This is a conceptual model, not a complete specification of every cache implementation. A CDN may customize keys by host, query, cookie, header, device, URL rewrites, and custom VCL/rules.

### 3.1. Different Query Strings Can Mean Different Resources

~~~text
GET /api/products?category=java
GET /api/products?category=spring
~~~

These are two distinct target URIs by HTTP convention. However, **a managed CDN can be configured to ignore query parameters** or allowlist only certain params in its cache key. If `category` affects the response yet the CDN strips it from the key, users will receive wrong data.

### 3.2. Cookie-Based Login and Identical URLs

~~~http
GET /api/me HTTP/1.1
Cookie: SESSION=alice-session-id
~~~

~~~http
GET /api/me HTTP/1.1
Cookie: SESSION=bob-session-id
~~~

If the cache key doesn't differentiate or **private content isn't barred from storage**, both requests share the exact same URL. Therefore you must define explicit storage policies. A `Cookie` header on a request **does not automatically tell a cache that the response is private**.

### 3.3. The `Authorization` Field Has RFC 9111 Protections, Yet Don't Over-Rely on Them

RFC 9111 places guardrails on shared caches when a **request contains `Authorization`**: a cached response must not be reused for another request unless the response carries a directive permitting shared-cache use (such as `public`, `s-maxage`, or `must-revalidate` under corresponding conditions).

Important points:
- The guardrail for `Authorization` **does not automatically apply identically to `Cookie`**.
- You can **accidentally bypass the guardrail** by returning `Cache-Control: public` or `s-maxage` on a Bearer/Basic endpoint whose body is personalized.
- Never assume every custom-configured cache/CDN strictly honors default semantics.
- An `Authorization: Bearer ...` header is a credential; never let tokens appear in logs, public cache keys, URLs, or metrics labels.

**Safety rule:** on endpoints returning per-principal personal data, intentionally emit `no-store` or `private` even when requests use `Authorization`. Do not rely solely on an RFC exception that a future policy refactor might inadvertently override.

## 4. What Does `Vary` Actually Do?

An HTTP response can declare:

~~~http
Vary: Accept-Language
~~~

This states that content varies according to the request's `Accept-Language`. A cache wishing to reuse a stored response must check whether the headers listed in `Vary` on the incoming request match those of the original request per HTTP rules.

Example:

~~~http
GET /api/public/greeting HTTP/1.1
Accept-Language: vi-VN
~~~

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=60
Vary: Accept-Language
Content-Type: application/json

{"language":"vi","message":"Xin chào"}
~~~

Same URL, different request:

~~~http
GET /api/public/greeting HTTP/1.1
Accept-Language: en-US
~~~

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=60
Vary: Accept-Language
Content-Type: application/json

{"language":"en","message":"Hello"}
~~~

These two representations are **public content**; thus shared caches may store them keyed by `Accept-Language`. `Vary` does not necessarily turn two header strings into two separate entries in every CDN, but an HTTP-compliant cache must ensure reuse happens only when matching rules hold.

### 4.1. `Vary` Does NOT Forbid Caches from Storing Data

~~~http
Vary: Cookie
Cache-Control: public, max-age=600
~~~

The pattern above **is unsafe as a default for `/api/me` content**. It asks caches to match cookies on reuse, while still allowing shared caches to store personalized responses. Cookies can contain session data, mutate over time, and have enormous cardinality. A CDN or custom cache-key configuration may ignore cookies or normalize them wrongly, causing leaks.

To forbid shared caches from storing **the entire response**, choose:

~~~http
Cache-Control: private, no-cache
~~~

If no cache should store it at all, choose:

~~~http
Cache-Control: no-store
~~~

`Vary` only distinguishes variants **when storage is permitted**; it is not a user security boundary.

### 4.2. Commonly Used Headers in `Vary`

| Listed header | When useful | Risks / considerations |
| --- | --- | --- |
| `Accept-Language` | Localized public pages/data | Many language-tag variants; normalization can reduce cache fragmentation |
| `Accept-Encoding` | `gzip`, `br`, `identity` differ in bytes | Servers/proxies often add this automatically; do not strip carelessly |
| `Accept` | APIs serving JSON/XML or multiple formats | Prevents serving cached JSON to a client accepting only XML |
| `Origin` | CORS returning different allow-origin per request | Prevents serving wrong CORS header; **does not isolate by user** |
| `User-Agent` | Content genuinely varies by device/UA | Far too many variants; poor cache hit ratio |
| `Cookie` | Public variants depending on harmless cookies genuinely meant to cache | Very high cardinality, private-data risk; usually bypass instead of `Vary` |
| `Authorization` | Content intentionally split by credential under special policy | Poor first choice for personalized responses |

A server can emit:

~~~http
Vary: Accept-Encoding, Accept-Language
~~~

Header names in the list are case-insensitive. Never add dozens of arbitrary request headers to `Vary`; cache efficiency drops and CDN management becomes complex.

### 4.3. `Vary: *`

`Vary: *` means a cache **cannot confirm** that a stored response is suitable for reuse on a subsequent request by comparing known headers; under HTTP caching rules, a response with `Vary: *` is not selected for ordinary reuse matching.

This is **not** a command to delete stored data and does not replace `Cache-Control: no-store`. If the goal is preventing storage of sensitive content, use `no-store` directly.

### 4.4. `Vary: Origin` in CORS

If a server returns `Access-Control-Allow-Origin` matching an allowed origin:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
~~~

then the response headers depend on `Origin`. `Vary: Origin` prevents a shared cache from reusing a CORS response for an inappropriate origin. For preflights, variants often also depend on `Access-Control-Request-Method` and `Access-Control-Request-Headers`.

However:
- CORS only controls whether browser JavaScript may **read** a cross-origin response.
- CORS does not prove the user is authorized to access the data.
- `Vary: Origin` does not separate users if Alice and Bob share **the same frontend origin**.
- CORS does not replace `Cache-Control: private/no-store`, authentication, authorization, or CSRF protection.

Therefore, never assume a CORS allowlist + `Vary: Origin` is enough to protect `GET /api/me` from shared caching.

## 5. `Cache-Control`: What Does Each Directive Mean?

| Directive | Which caches may store? | Key detail |
| --- | --- | --- |
| `no-store` | Compliant caches must not store the request/response | Use for sensitive data, tokens, transactions |
| `private` | Private caches may store; shared caches must not store full copy | Suitable for user-specific data safe to keep in the browser |
| `no-cache` | May store, but must revalidate successfully before reuse | **Not** a synonym for `no-store` |
| `max-age=60` | Permits 60s freshness when all caching conditions are met | Does not imply `public` or shared-cache safety |
| `s-maxage=120` | Sets shared-cache freshness, overriding `max-age` in shared caches | Can make responses with `Authorization` **shareable** if permitted |
| `public` | Allows shared caches to store when other conditions allow | Dangerous if accidentally enabled on personalized content |
| `must-revalidate` | Once stale, must not reuse without validating as specified | Interacts notably with `Authorization` and shared caching |
| `immutable` | Hints content will not change while fresh | Use for fingerprinted assets, not user profiles |
| `stale-while-revalidate` | Allows serving stale for a window if cache supports it | Evaluate freshness/privacy carefully for user data |
| `no-transform` | Asks intermediaries not to alter the representation | Does not make a response `private` |

**Note:** cache lifetime is an HTTP decision made by compliant caches. CDNs have dashboard rules, edge functions, custom keys, and surrogate directives; test your real deployment policy. Never assume one header always beats every cache product rule without testing.

### 5.1. `no-cache` vs. `no-store`

Two responses:

~~~http
Cache-Control: no-cache
~~~

~~~http
Cache-Control: no-store
~~~

are not equivalent. With `no-cache`, a cache **may still store bytes** and reuse them after the server confirms validity via a conditional request like `If-None-Match`/`If-Modified-Since`. With `no-store`, compliant caches must not store the response/request. For medical records, OTP codes, payment details, or sensitive data that should not linger in caches, `no-store` is usually the clear choice.

### 5.2. `private` vs. `no-store`

~~~http
Cache-Control: private, max-age=30
~~~

lets the **browser HTTP cache** hold data for 30 seconds while forbidding shared caches from storing it. Suitable when UX benefits from short-term caching and data sensitivity permits.

~~~http
Cache-Control: no-store
~~~

requests no storage in either private or shared caches, better suited for truly sensitive data. `private` does not protect if an attacker uses **the same browser profile** or accesses storage on a compromised device.

### 5.3. `no-store` Cannot Erase the Past

If a CDN or browser **already cached** an older version of a response before the app added `no-store`, the new header does not automatically purge all old entries immediately. You must purge CDN keys, version URLs if needed, disable faulty cache rules, verify headers, and assess whether data was exposed.

A managed cache may be custom-configured to ignore standard headers. Adding `no-store` at the origin without fixing a "cache everything" rule at the CDN is an incomplete fix.

### 5.4. Do Not Rely on `Pragma: no-cache` for Modern Fixes

`Pragma: no-cache` is a historical HTTP/1.0 request-compatibility mechanism. For modern responses, `Cache-Control` is the clearer interface and must be the primary control. Avoid contradictory header combinations like "public, one-year max-age" alongside "no-store" without knowing how caches interpret them.

## 6. Cookies, `Set-Cookie`, and Sessions: Dangerous Assumptions

### 6.1. `Cookie` in a Request Does Not Make the Response Private Automatically

A request:

~~~http
GET /api/me HTTP/1.1
Cookie: SESSION=opaque-session-id
~~~

merely indicates the browser is sending a cookie. Shared caches often have product-specific rules for cookies, yet **HTTP caching RFCs do not magically mark every request carrying a Cookie as "private."** If a response returns private content, emit `Cache-Control: private` or `no-store` as required and verify CDN policy.

### 6.2. `Set-Cookie` Is Not a Caching Ban

A response carrying:

~~~http
HTTP/1.1 200 OK
Set-Cookie: session=opaque-id; HttpOnly; Secure; SameSite=Lax
~~~

is not guaranteed by that alone to stop shared caches from storing everything else. Custom proxy policies handle `Set-Cookie` in various ways, so you must **proactively** classify data and declare `Cache-Control`. If a CDN caches a response containing user A's `Set-Cookie` and serves it to user B, that can cause a severe session hijacking incident.

**Never treat "has Set-Cookie so CDN definitely bypasses" as a security guarantee.** Audit cache product config, response headers, multi-session tests, and controlled production logs.

### 6.3. Session Cookies vs. Bearer Tokens

- Session cookie: browsers attach it automatically by domain/path/`SameSite`/`Secure`; HTTP caching has no inherent awareness of which attributes encode permissions.
- Bearer token: typically sent in `Authorization`, which carries shared-cache restrictions under RFC 9111; yet directives can still inadvertently reopen shared caching.
- JWTs do not automatically make responses cache-safe: the returned payload may still be personalized or restricted to a single principal.

### 6.4. Logout Does Not Automatically Clear All Caches

Upon logout:
- The server may invalidate the session/refresh token and clear cookies.
- The browser HTTP cache may still retain `private` entries if not cleared or expired.
- Service workers or application state may still hold data.
- A misconfigured shared CDN may continue serving cached data unless purged.
- Browser back/forward cache and history snapshots have separate semantics from HTTP caching.

Systems that must leave no trace after logout on shared machines can use `no-store` for sensitive pages/responses, clear frontend state, and align service worker/cache mechanisms. `Cache-Control: no-store` is not an absolute guarantee that every copy disappears; test real browsers against your threat model.

## 7. Policy Selection Table by Content Type

| Resource type | Suggested policy | Explanation |
| --- | --- | --- |
| Fingerprinted JS/CSS, static public content | `public, max-age=31536000, immutable` | URL changes whenever content changes |
| Public product catalog, identical for everyone | `public, max-age=60` | Shared caching is beneficial |
| Public translations by `Accept-Language` | `public, max-age=60` + `Vary: Accept-Language` | Caches pick the right variant |
| User dashboard, low sensitivity, allowed on private device | `private, max-age=20` | Kept out of shared caches; evaluate post-logout behavior |
| Personal profile, account info | `no-store` or `private, no-cache` per security policy | Weigh risks of copies remaining in browser |
| OTP codes, tokens, payment/sensitive info | `no-store` | Prevent storage in compliant HTTP caches |
| Role/tenant-dependent report API | `no-store` unless permission-aware caching is proven | Never assume "same URL" is a safe cache key |
| 401/403 error responses tied to a principal | Usually `no-store` | Avoid reusing error bodies carrying personal details |
| Private file downloads | Usually `private` or `no-store` by sensitivity | CDN and `Content-Disposition` must be controlled |

These are **design recommendations**, not RFC-mandated headers for every resource. Applications with specific business needs may pick another policy after proving data isolation and cache compliance.

## 8. Relationship Between `Vary`, `ETag`, and `304 Not Modified`

A public response can use `ETag` to save bandwidth:

~~~http
HTTP/1.1 200 OK
ETag: "greeting-vi-v1"
Vary: Accept-Language
Cache-Control: public, max-age=60
Content-Type: application/json

{"language":"vi","message":"Xin chào"}
~~~

When the response goes stale, a client/cache can send:

~~~http
GET /api/public/greeting HTTP/1.1
Accept-Language: vi-VN
If-None-Match: "greeting-vi-v1"
~~~

The server responds:

~~~http
HTTP/1.1 304 Not Modified
ETag: "greeting-vi-v1"
Vary: Accept-Language
Cache-Control: public, max-age=60
~~~

Caches can reuse the stored body for the matching variant per HTTP rules. `304` carries no resource body, yet still updates metadata; combining `304` with stored responses must follow RFC 9111 update/selection rules.

### 8.1. Validators Must Also Match the Right Representation

If an endpoint varies by user or language, **never use a single global ETag** across all representations if doing so causes wrong `304` evaluations. For example, hashing only record count without accounting for user permissions can produce wrong responses or leak state the client shouldn't learn.

For private/sensitive endpoints needing `no-store`, ETags are usually unnecessary for cache reuse. An `ETag` **does not make data safe by itself**: it only identifies versions and assists revalidation when access is authorized.

### 8.2. `ShallowEtagHeaderFilter` Does Not Govern Cache Privacy

Spring MVC provides `ShallowEtagHeaderFilter` to compute an ETag from rendered response bytes, supporting certain conditional request flows. This filter does not decide whether a response is public or private, and it buffers responses at resource cost. It does not replace `Cache-Control` and does not fix CDNs wrongly caching personalized data.

For private content, you still need proper authorization and `no-store`/`private`. For large or dynamic data, an ETag derived from resource version metadata without pre-rendering the body can be more efficient, provided the validator accurately reflects the representation and permissions.

## 9. Spring MVC: `ResponseEntity` and `CacheControl`

Spring Framework provides `org.springframework.http.CacheControl` to construct `Cache-Control` without manual string concatenation:

~~~java
CacheControl.noStore();
CacheControl.noCache();
CacheControl.maxAge(Duration.ofSeconds(60)).cachePublic();
CacheControl.maxAge(Duration.ofSeconds(20)).cachePrivate();
~~~

These are illustrative Java expressions requiring `java.time.Duration` and `org.springframework.http.CacheControl` imports in real code. They produce headers:
- `no-store`
- `no-cache`
- `max-age=60, public`
- `max-age=20, private`

A controller can return:

~~~java
return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(new Profile("alice"));
~~~

This fragment assumes a `Profile` record and does not compile standalone. `ResponseEntity.BodyBuilder.cacheControl(...)` writes the `Cache-Control` response header; status, body, content type, and other headers are handled by MVC. Returning a Java DTO does not make it safe for shared caching by default.

### 9.1. Do Not Confuse `@Cacheable` with `CacheControl`

| API | Layer | Role |
| --- | --- | --- |
| `@Cacheable` | Spring Cache abstraction (service/method) | Caches method results in application store |
| `CacheControl` | Spring Web HTTP response | Builds `Cache-Control` header |
| `ResponseEntity` | Spring MVC | Status, headers, and response body |
| `ShallowEtagHeaderFilter` | Spring Web filter | Computes/checks HTTP validator from rendered body |
| `WebContentInterceptor` | Spring MVC | Configures cache policy by URL patterns |
| CDN cache rules | Infrastructure | Stores/serves HTTP responses at edge/proxy |

They share the word "cache" yet have **different scopes and keys**. You can cache a method on the backend while keeping the HTTP response `no-store`, or skip method caching while browsers still cache HTTP responses. Identify which layer holds data when debugging.

## 10. Complete Example: Spring Boot 3.3.5 + Security + Caching Headers

The demo application exposes three endpoints:
1. `GET /api/public/greeting` — **public**, Vietnamese/English by locale, permits shared caching for 60 seconds, and includes `Vary: Accept-Language`.
2. `GET /api/me/profile` — **authentication required**, distinct body per user, returns `Cache-Control: no-store`.
3. `GET /api/me/preview` — **authentication required**, less sensitive demo data, allows **private browser caching** up to 20 seconds while forbidding shared caches.

No database and no CDN. HTTP Basic is used here only to distinguish Alice and Bob easily in tests, **not as the mandated auth mechanism for all production APIs**. The backend determines identity from the authenticated `Principal`; clients must never pass a `?user=` query param to switch permissions.

~~~text
http-cache-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/httpcache/
    │   ├── HttpCacheApplication.java
    │   ├── security/SecurityConfig.java
    │   └── web/CacheDemoController.java
    └── test/java/com/example/httpcache/
        └── CacheDemoIntegrationTest.java
~~~

### 10.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'http-cache-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
~~~

`spring-boot-starter-web` includes Servlet MVC and Jackson. `spring-boot-starter-security` adds the security filter chain and authentication. `spring-security-test` provides `httpBasic(...)` for testing requests through `SecurityFilterChain`. Java 17 and a compatible Gradle wrapper are used.

### 10.2. Main Application

`src/main/java/com/example/httpcache/HttpCacheApplication.java`:

~~~java
package com.example.httpcache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpCacheApplication.class, args);
    }
}
~~~

### 10.3. Spring Security: HTTP Basic Authentication

`src/main/java/com/example/httpcache/security/SecurityConfig.java`:

~~~java
package com.example.httpcache.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public/**").permitAll()
                        .requestMatchers("/api/me/**").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .sessionManagement(session ->
                        session.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-local-demo"))
                        .roles("USER")
                        .build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-local-demo"))
                        .roles("USER")
                        .build());
    }
}
~~~

Notes:
- `/api/public/**` requires no authentication; `/api/me/**` requires an authenticated principal.
- `SessionCreationPolicy.STATELESS` avoids storing `SecurityContext` in an HTTP session in this Basic demo, keeping user separation clean in tests. It **does not stop other code from creating an HttpSession** depending on the app.
- Configuration omits `csrf().disable()`; GET is not an unsafe method requiring CSRF tokens, so the demo needs no CSRF policy change.
- In-memory usernames/passwords are strictly for local learning; production uses an identity provider, secret management, and HTTPS.
- `Authorization` in HTTP Basic must be protected like a password; base64 is not encryption. When using `curl -u` over real networks, always use TLS.
- Spring Security emits default cache-related response headers to protect resources. Here, the controller sets `Cache-Control` explicitly per endpoint; inspect the final response after the full filter chain rather than guessing whether Spring Security or MVC "wins."

### 10.4. Controller: Public `Vary`, Private `no-store`

`src/main/java/com/example/httpcache/web/CacheDemoController.java`:

~~~java
package com.example.httpcache.web;

import java.security.Principal;
import java.time.Duration;
import java.util.Locale;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class CacheDemoController {

    public record Greeting(String language, String message) {}
    public record Profile(String username, String displayName) {}
    public record Preview(String username, String label) {}

    @GetMapping("/public/greeting")
    public ResponseEntity<Greeting> greeting(Locale locale) {
        String language = "vi".equals(locale.getLanguage()) ? "vi" : "en";
        String message = "vi".equals(language) ? "Xin chào" : "Hello";

        return ResponseEntity.ok()
                .cacheControl(
                        CacheControl.maxAge(Duration.ofSeconds(60))
                                .cachePublic())
                .header(HttpHeaders.VARY, HttpHeaders.ACCEPT_LANGUAGE)
                .body(new Greeting(language, message));
    }

    @GetMapping("/me/profile")
    public ResponseEntity<Profile> profile(Principal principal) {
        String username = principal.getName();
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(new Profile(username, "Profile for " + username));
    }

    @GetMapping("/me/preview")
    public ResponseEntity<Preview> preview(Principal principal) {
        String username = principal.getName();
        return ResponseEntity.ok()
                .cacheControl(
                        CacheControl.maxAge(Duration.ofSeconds(20))
                                .cachePrivate())
                .body(new Preview(username, "Private preview"));
    }
}
~~~

**Why does this code protect those specific cases?**
1. Public greeting contains no user-specific data and returns the matching locale variant. `Vary: Accept-Language` clarifies what changes the content.
2. Profile reads `username` from the Security-authenticated `Principal`; it never trusts a client-supplied `?user=alice` or cookie as business identity.
3. The profile response sets `no-store`, instructing compliant HTTP caches not to store personal bodies.
4. Preview sets `private`, barring shared caches from storing it while letting browsers cache briefly per policy. **Never use the preview pattern for data that must not be stored on the device.**
5. Does not put `Vary: Cookie` on `/me` endpoints as a substitute for `no-store`/`private`.
6. Never puts raw passwords, tokens, or session IDs in JSON. `Cache-Control` cannot protect secrets already exposed in response bodies or logs.
7. A misconfigured proxy/CDN can still ignore headers; verify in a real deployment.

### 10.5. Expected HTTP Outputs

Public Vietnamese:

~~~http
GET /api/public/greeting HTTP/1.1
Accept-Language: vi-VN,vi;q=0.9
~~~

~~~http
HTTP/1.1 200 OK
Cache-Control: max-age=60, public
Vary: Accept-Language
Content-Type: application/json

{"language":"vi","message":"Xin chào"}
~~~

Public English:

~~~http
GET /api/public/greeting HTTP/1.1
Accept-Language: en-US,en;q=0.9
~~~

~~~http
HTTP/1.1 200 OK
Cache-Control: max-age=60, public
Vary: Accept-Language
Content-Type: application/json

{"language":"en","message":"Hello"}
~~~

Alice profile:

~~~http
GET /api/me/profile HTTP/1.1
Authorization: Basic <alice-credential>
~~~

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json

{"username":"alice","displayName":"Profile for alice"}
~~~

Bob profile:

~~~http
GET /api/me/profile HTTP/1.1
Authorization: Basic <bob-credential>
~~~

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json

{"username":"bob","displayName":"Profile for bob"}
~~~

`<alice-credential>` and `<bob-credential>` are illustrative wire placeholders, not literal strings for commands; `curl` below builds the Basic header from the demo credentials.

## 11. MockMvc: Proving Correct Headers and No User Mix-Ups

`src/test/java/com/example/httpcache/CacheDemoIntegrationTest.java`:

~~~java
package com.example.httpcache;

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
class CacheDemoIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicVietnameseVariantDeclaresVary() throws Exception {
        mvc.perform(get("/api/public/greeting")
                        .header(HttpHeaders.ACCEPT_LANGUAGE, "vi-VN,vi;q=0.9"))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.CACHE_CONTROL,
                        "max-age=60, public"))
                .andExpect(header().string(HttpHeaders.VARY,
                        containsString(HttpHeaders.ACCEPT_LANGUAGE)))
                .andExpect(jsonPath("$.language").value("vi"))
                .andExpect(jsonPath("$.message").value("Xin chào"));
    }

    @Test
    void publicEnglishVariantHasDifferentBody() throws Exception {
        mvc.perform(get("/api/public/greeting")
                        .header(HttpHeaders.ACCEPT_LANGUAGE, "en-US"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.language").value("en"))
                .andExpect(jsonPath("$.message").value("Hello"));
    }

    @Test
    void protectedProfileNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/me/profile"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceProfileIsNeverHttpCached() throws Exception {
        mvc.perform(get("/api/me/profile")
                        .with(httpBasic("alice", "alice-local-demo")))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.displayName")
                        .value("Profile for alice"));
    }

    @Test
    void bobNeverReceivesAlicesBody() throws Exception {
        mvc.perform(get("/api/me/profile")
                        .with(httpBasic("alice", "alice-local-demo")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));

        mvc.perform(get("/api/me/profile")
                        .with(httpBasic("bob", "bob-local-demo")))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
                .andExpect(jsonPath("$.username").value("bob"))
                .andExpect(jsonPath("$.displayName")
                        .value("Profile for bob"));
    }

    @Test
    void privatePreviewIsNotMarkedPublic() throws Exception {
        mvc.perform(get("/api/me/preview")
                        .with(httpBasic("alice", "alice-local-demo")))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.CACHE_CONTROL,
                        "max-age=20, private"))
                .andExpect(jsonPath("$.username").value("alice"));
    }
}
~~~

Run with the project's Gradle wrapper:

~~~bash
./gradlew test
~~~

The tests verify:
- The public endpoint emits `Vary: Accept-Language` and public `Cache-Control`.
- Both locales receive their corresponding JSON bodies.
- Private routes require authentication.
- Alice and Bob receive **distinct responses when hitting the origin Spring app**.
- Both profile responses carry `no-store`.
- Preview receives `private` rather than `public`.

**Important limitation:** MockMvc **does not act as an HTTP CDN cache**. The `bobNeverReceivesAlicesBody` test only proves the controller/Security doesn't mix up principals inside the app; it **does not prove the CDN is configured with bypass/no-store properly**. Test through a real reverse proxy/CDN or a caching-proxy integration test with controlled cache hit/miss/age headers.

Tests should also avoid depending on exact ordering of all response headers; assert meaningful directives and values. Whenever application security config changes, verify the final `Cache-Control` after all filters.

## 12. Running HTTP and Observing with curl

In a project with Java 17 and the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

### 12.1. Public Resource in Two Languages

~~~bash
curl -i 'http://localhost:8080/api/public/greeting' \
  -H 'Accept-Language: vi-VN,vi;q=0.9'

curl -i 'http://localhost:8080/api/public/greeting' \
  -H 'Accept-Language: en-US'
~~~

Observe:
- Both responses include `Cache-Control: max-age=60, public`.
- Both include `Vary: Accept-Language`.
- The body returns `vi` or `en` matching the request.

**`curl` is not an HTTP cache by default**: calling the URL twice in a row does not prove a shared cache separates variants. It only verifies that the origin builds distinct responses with the right headers.

### 12.2. Personal Profile Without HTTP Storage

~~~bash
curl -i -u alice:alice-local-demo \
  'http://localhost:8080/api/me/profile'

curl -i -u bob:bob-local-demo \
  'http://localhost:8080/api/me/profile'
~~~

Alice receives `"username":"alice"` and Bob receives `"username":"bob"`. Both include `Cache-Control: no-store`. Neither `public` nor `s-maxage` should ever appear on this endpoint's policy.

Without credentials:

~~~bash
curl -i 'http://localhost:8080/api/me/profile'
~~~

Expect `401 Unauthorized` from Spring Security. That status is not proof of CDN safety; verify error and auth paths are never mistakenly cached either.

### 12.3. Preview Stored Only in Private Cache

~~~bash
curl -i -u alice:alice-local-demo \
  'http://localhost:8080/api/me/preview'
~~~

Expected:

~~~http
Cache-Control: max-age=20, private
~~~

Although private caches may keep it briefly, **this is not an option for data that must vanish completely after logout**. When storage must be prohibited, switch the policy to `no-store` and add tests.

### 12.4. How to Prove Whether a CDN Leaks Data

Deploy the app behind a **staging** CDN/proxy matching production config, create two test accounts containing no real user info, and check:
1. Alice sends GET profile through the CDN hostname; confirm Alice's body and `no-store`.
2. Bob sends GET to the same URL; the body must be Bob's, not Alice's.
3. Reverse the order (Bob first, then Alice), repeating after cache warm-up.
4. Inspect observable cache headers such as `Age`, `Via`, `X-Cache`, `CF-Cache-Status`, or provider-specific headers **if actually present**. Never guess Hit/Miss if the provider emits no indicator.
5. Test `401`/`403`/`404`/`500` error responses on private endpoints; ensure they neither leak info nor get shared-cached.
6. Test with cookie-based sessions if the real app uses cookies instead of HTTP Basic.
7. Test "cache everything" deployment rules, Edge/Worker functions, and query normalization.
8. If a leak is discovered, disable the faulty cache rule, purge data, and treat it as a security incident—do not just tweak one header and declare the risk gone.

Never put raw session cookies, tokens, or real accounts into test logs or public tickets.

## 13. CDN Configuration: Edge Bypasses Must Align with Origin

A safe strategy for a mixed API:

~~~text
/api/public/**   -> shared cache candidate; allowlist TTL/method/query/header
/api/me/**       -> bypass shared cache; origin also returns no-store/private
/admin/**        -> bypass unless an explicit per-tenant/permission cache architecture exists
/static/**       -> public immutable when URLs are fingerprinted
~~~

This is a **policy diagram**, not configuration syntax for any specific CDN. Every vendor has its own naming and rules.

### 13.1. Path-Based Bypass Does Not Replace Authorization

Even when the CDN bypasses `/api/me/**`, the backend must still authenticate the user and authorize resource access. An attacker might hit the origin directly if network paths allow; CDN rules never replace application/service security.

### 13.2. Do Not Bypass Only When `Cookie` Is Present

A private API may authenticate via `Authorization` instead of cookies. If CDN rules bypass only on `Cookie`, Bearer endpoints could be cached. Conversely, a public page might still carry analytics cookies; having a `Cookie` doesn't always require disabling shared caching if content is genuinely public, though it must be designed and tested.

### 13.3. Custom Cache Keys and Query Params

If the backend responds differently to `GET /reports?id=1` vs. `GET /reports?id=2`, the CDN must not strip `id` from the cache key. If a resource also depends on locale/device headers, apply `Vary` or explicit cache-key policies. If a resource depends on role/tenant, **never build a key from a client-supplied header** without trusted authentication/authorization first.

### 13.4. Cache Purge After Discovering a Mistake

If user data was stored in a shared cache:
- Temporarily bypass the sensitive endpoint and block new entries.
- Purge by cache keys/tags/paths per provider, including variants and affected edge regions.
- Re-verify response headers and actual cache rules.
- Audit logs per security incident procedures and assess scope/impact.
- Rotate/revoke sessions or credentials if they were also exposed.
- Check service workers, frontend stores, and affected clients as needed.

`no-store` only stops compliant caches from storing future responses per policy; **it does not erase old copies or data already seen by other users**.

## 14. Handling `Vary` with Locale, Compression, and API Formats

### 14.1. Accept-Language

If a page returns content based on `Accept-Language`, include `Vary: Accept-Language`. However, header values have many combinations like `vi-VN,vi;q=0.9,en;q=0.5`, which can create too many variants in a shared cache.

Deliberate optimizations:
- Support a small set of locales with clear fallback rules.
- Consider turning public translated resources into explicit URLs like `/vi/articles/123` and `/en/articles/123` when appropriate.
- Add `Vary` only when the response genuinely differs by that header.
- If a response is personalized by a server-stored user preference, `Vary: Accept-Language` **does not reflect the user preference**; use `private`/`no-store` first.

### 14.2. Accept-Encoding

Different compression formats under `Accept-Encoding: gzip` or `br` typically need `Vary: Accept-Encoding` so caches do not serve mismatched encodings. Spring Boot, Tomcat, or reverse proxies may add compression headers separately; do not drop server/proxy-generated `Vary: Accept-Encoding` just because a controller adds another `Vary` header.

### 14.3. Accept

An API may return JSON or XML depending on `Accept` and message converters. When bytes or content types differ, `Vary: Accept` is generally needed on cacheable responses. If an API only ever returns JSON with no alternate representations, adding `Vary: Accept` yields no clear benefit while increasing variant fragmentation.

### 14.4. Origin

With CORS policies across multiple origins, `Vary: Origin` lets caches select responses with the right `Access-Control-Allow-Origin`. **Never assume a response is public just because CORS allows an Origin**. If the body depends on users sharing the same frontend origin, `Vary: Origin` will not separate them.

## 15. Security Defaults, Error Responses, and Real-World Conditions

### 15.1. Default Spring Security Cache Headers

Spring Security Servlet emits security response headers by default, including cache-related headers to reduce the risk of caching sensitive data. A typical default response looks like:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

This is a **common default example**, not mandatory headers across every Spring Boot/Security project. The security header writer may refrain from overwriting a `Cache-Control` already set by the application. In the demo, the public endpoint sets `max-age=60, public` while the private endpoint sets `no-store`; always **verify the final response via MockMvc and HTTP**.

Never disable all security headers just to cache one public page. Set deliberate cache policies on genuinely safe endpoints while keeping the remaining routes protected.

### 15.2. Error Responses Can Also Contain Private Data

A JSON error can echo an email, tenant, user ID, rejected values, resource names, or internal diagnostics. Therefore `400`/`401`/`403`/`404`/`500` responses on private routes need explicit policies keeping sensitive data out of shared caches. Never assume `4xx`/`5xx` statuses are always uncacheable in every situation: per-status caching behavior varies across headers and managed CDNs.

CORS `403` responses and `401` authentication challenges are often produced before reaching controllers; `@RestControllerAdvice` does not necessarily handle them. Inspect filters, exception handler layers, and edge policies instead of looking only at controller returns.

### 15.3. Conditional Requests and Authorization

If a private endpoint uses `ETag`:
- Authentication/authorization must still run on revalidation requests.
- The ETag must belong strictly to a representation the user is permitted to see.
- Never return `304` to another user just because `If-None-Match` matched a global ID.
- For highly sensitive content, `no-store` is usually simpler and safer than caching with revalidation.

A stale entry left in a CDN due to misconfiguration can bypass origin auth checks altogether; that is why cache rules must be reviewed as **part of security architecture**, not merely performance.

## 16. Common Dangerous Misconceptions

| Misconception or mistake | Consequence | Fix |
| --- | --- | --- |
| Adding `Vary: Cookie` and marking `/api/me` `public` | Shared caches can store per-session data, risking leaks | Use `no-store` or `private` and bypass CDN |
| Assuming requests with `Cookie` are auto `no-cache` | Proxies cache personal responses if policy permits | Set explicit `Cache-Control` and test the edge |
| Assuming `Set-Cookie` guarantees CDN bypass | Caches may store responses/cookies per rules | Classify data, bypass, and audit CDN config |
| Thinking `no-cache` means "do not store" | Personal bytes can remain in browser cache | Use `no-store` when storage must be disallowed |
| Setting `public` on an endpoint using `Authorization` | Can enable shared caching per RFC | Only use `public` when body is independent of principal |
| Trusting `Vary: Origin` as user authorization | Two users on the same origin share the variant | Use authz + `no-store`/`private` for personalized data |
| Omitting `Vary: Accept-Language` | Caches serve the wrong language | Add `Vary: Accept-Language` |
| Omitting `Vary: Accept-Encoding` | Caches serve incompatible content encodings | Let compression layers emit `Vary` properly |
| CDN strips query params affecting content | Responses for different queries get mixed | Check cache keys and URL rules |
| `@Cacheable` key lacks user/tenant | Backend returns prior user's data to next user | Scope method cache keys by permissions or avoid caching |
| Accidentally overriding Security's default `no-store` | Private responses gain shared-cache TTLs | Test headers after the full filter chain |
| Dashboard remains in browser after logout | `private` still allows local caching | Consider `no-store` and clear app state |
| Adding `no-store` and assuming old caches vanish | Stale CDN entries persist | Purge, verify cache status, assess incident |
| Sharing the same ETag across users despite different bodies | `304` evaluates wrongly and leaks metadata | Scope validators per representation; auth before conditional |
| Passing MockMvc 2-user tests means CDN is safe | MockMvc does not simulate shared caches | Test staging through the CDN with 2 sessions |
| CDN caches `401`/`403` containing private details | Leaks error context | Use non-shared error policies and safe details |
| Skipping auth because CORS allows the origin | Other sites/callers can read data if authz is missing | Keep authentication and authorization |
| Seeing `Age` increase on a route meant to be `no-store` | Misconfigured edge rule or stale response | Check CDN rules, purge, and triage incident |

## 17. Testing Workflow to Prevent Cross-User Data Leaks

1. Inventory every endpoint returning personalized content (user, role, tenant, session, A/B variant) and every cache layer handling it.
2. Document the HTTP policy per route: `public`/`private`/`no-store`, meaningful `Vary` headers, TTLs, and auth requirements.
3. In unit/MockMvc tests, assert `Cache-Control`/`Vary` and exact bodies for Alice/Bob; never assert only `200`.
4. In CDN integration tests, call the same URL with two different credentials/cookies, reverse order, warm the cache, and repeat.
5. Inspect provider headers like `Age`/`Via`/cache-status if available; test how the CDN handles `Authorization`, `Cookie`, `Set-Cookie`, and query params.
6. Test `200`, `304`, redirects, `401`, `403`, `404`, `500`, and file downloads if applicable.
7. Test locale, encoding, and CORS `Origin` variants, ensuring no wrong representation reuse.
8. Audit Spring Cache/Redis keys and services: HTTP `no-store` can still mask a backend cache bug.
9. Test browser behavior after logout, Back/Forward navigation, service workers, and app state against product privacy requirements.
10. In production, monitor unexpected cache hits on private paths, unintended `public`/`s-maxage`, new CDN rules, and security regressions.
11. Re-run tests before and after changes to CDN config, `SecurityFilterChain`, Spring MVC caching/interceptors, gateways, and user/session models.
12. If a leak occurs, handle it as a security incident: containment, purging, credential rotation if needed, audit, and recovery verification.

### Self-Check Questions

**1.** Does `Vary: Accept-Language` stop a CDN from storing a response?

**Answer:** No. It tells caches to consider `Accept-Language` when selecting a stored response for reuse; it can be paired with policies that permit storage.

**2.** Is `Vary: Cookie` safe as a default for `/api/me`?

**Answer:** No. Cookies have high cardinality and `Vary` does not prohibit shared caches from storing responses; use `private` or `no-store`.

**3.** What should you choose when personal data may be stored in the browser but never on a CDN?

**Answer:** `Cache-Control: private`, optionally combined with a TTL or revalidation depending on policy.

**4.** What should you use to instruct all HTTP-compliant caches not to store a sensitive profile?

**Answer:** `Cache-Control: no-store`. You still need to address custom CDN rules, stale entries, service workers, and internal caches.

**5.** Does `Cache-Control: no-cache` mean caches keep no copy?

**Answer:** No. Caches may store it, but must revalidate before reuse.

**6.** Why be careful with `public`/`s-maxage` when requests carry `Authorization`?

**Answer:** Those directives can allow shared caching of responses to `Authorization` requests under RFC 9111. If the body is personalized, data leakage risks arise.

**7.** Why do MockMvc tests with two users not prove a CDN won't leak data?

**Answer:** MockMvc runs against the Spring application, not CDN keys, rules, hits, or misses. You must test through a staging proxy or equivalent cache integration.

**8.** Does CORS `Vary: Origin` replace principal-based authorization?

**Answer:** No. Frontend origins can be identical for all users; authorization must rely on verified identity, permissions, and server-side policies.

**9.** Does `@Cacheable` automatically honor `Cache-Control: no-store`?

**Answer:** No. It uses application-level method caching and requires proper user/tenant cache keys or no caching at all.

## 18. Official References

- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): storage, shared caches, `Vary` matching, revalidation, `Cache-Control`, `Authorization`.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): request/response fields, content negotiation, conditional requests, and status codes.
- [MDN — HTTP Caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching): private/shared caches, `Vary`, `no-store`/`no-cache`, and personalization scenarios.
- [MDN — Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control): `private`/`public`/`max-age`/`s-maxage`/`must-revalidate`.
- [MDN — Vary](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Vary): cache selection by request headers.
- [Spring Framework — HTTP Caching in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): `CacheControl`, controller `ETag`/`Last-Modified`, static resources, ETag filters.
- [Spring Framework — CacheControl Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/http/CacheControl.html): `noStore`, `noCache`, `maxAge`, `cachePrivate`, `cachePublic` builders.
- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): protective defaults, cache control, configuring security headers.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): CORS policies and response headers with `Vary: Origin`.
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): service-layer `@Cacheable`, distinct from HTTP caching.

**Remember:** `Vary` helps caches pick the right **variant** of a cacheable resource; `Cache-Control` governs whether a response may be **stored and reused** in private/shared caches; security determines **who is allowed to see** the content. Whenever data depends on user/tenant/session, prefer `no-store` or `private`, verify both Spring and the CDN, and never treat `Vary: Cookie` or `Vary: Origin` as a substitute for authorization and private data protection.
