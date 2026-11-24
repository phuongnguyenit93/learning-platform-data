# Cache-Control for content containing sensitive data

## 1. Problem to solve

Suppose a user logs into a banking application to view their balance, profile, or transaction history. After they log out, the server invalidates the session. However, **the browser, a proxy, a CDN, or another cache layer may have retained a copy of the response containing sensitive data**. If that copy is reused, the next person on the same machine or another user passing through a shared cache could see the old data.

A misconfigured private response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=3600

{"account":"demo","balance":"100000000"}
~~~

`public` can allow shared HTTP caches to store the response, and `max-age=3600` indicates freshness for up to one hour under HTTP rules. This is an inappropriate policy for a private account balance.

For highly sensitive content, the typical choice is:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
~~~

Spring Security provides a broader protective default when security headers remain enabled:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

**Lesson goals:** accurately explain `Cache-Control` directives; understand why `no-cache`, `private`, and `max-age=0` differ from `no-store`; identify which cache layers are risky; configure Spring Security so private responses are not stored while static assets can still be cached; test via MockMvc, browser, and CDN; and understand the limits of HTTP headers after logout.

Primary example scope: **Spring Security 6.5 / Servlet, Spring Boot 3.5.16, and Java 17**, with an extension for WebFlux. Examples use mock data and do not require a real login environment.

## 2. Which layers store HTTP cache data?

~~~text
Browser
  | Browser HTTP cache
  v
CDN / reverse proxy / gateway
  | Shared HTTP cache
  v
Spring Security filter chain
  v
Spring MVC / WebFlux
  v
Business service / database
~~~

### 2.1. Private cache in the browser

Browsers can store HTML, CSS, JavaScript, images, and API responses to reduce network requests. Storage behavior depends on HTTP response headers, request method, status code, browser, browser configuration, and the URL's cache history. On shared machines, account data or secret information should not be retained as a replayable copy in the HTTP cache.

### 2.2. Shared caches at proxies, gateways, and CDNs

A shared cache serves multiple clients. If a CDN keys its cache solely on the URL `/api/profile` without accounting for user-specific data, user A's response may be served to user B. Sending a cookie or `Authorization` header **does not replace cache policy verification**. CDN "cache all" rules, cache keys missing account context, or origin `Cache-Control` overrides are real risks that must be evaluated.

`private` instructs **compliant shared HTTP caches not to store** the response; `no-store` is stronger, instructing both private and shared HTTP caches not to store it. For secrets or financial data, `no-store` is usually the clearest choice.

### 2.3. Things not fully managed by HTTP Cache-Control

- **Back/forward cache (bfcache):** browsers may keep a snapshot of the page or DOM to restore when clicking Back. This mechanism differs from the HTTP cache; `no-store` may affect eligibility depending on the browser/version, but does not guarantee wiping every snapshot.
- **Service Worker Cache API:** application-written `CacheStorage` logic can store responses outside the standard HTTP cache. You must control custom cache logic, avoid writing sensitive content to offline caches, and clean up data on logout.
- **SPA state and web storage:** Redux, React state, DOM, IndexedDB, `localStorage`, and JavaScript variables are not cleared just because the server returns `no-store`.
- **Downloaded files, screenshots, and logs:** Cache-Control does not delete already downloaded data, proxy logs, or screenshots.
- **Backend caches:** Redis, application caches, and database/query caches require their own authorization and data retention policies; HTTP headers do not control those stores.

**Distinction to keep in mind:** HTTP caching policy is only one layer; the application must still enforce authentication, authorization, session revocation, logout, and cleanup of client-side data.

## 3. Practical meaning of Cache-Control directives

| Directive (response) | Meaning | Best suited for |
| --- | --- | --- |
| `no-store` | Compliant HTTP caches must not intentionally store the response | Tokens, balances, sensitive account data, secret keys |
| `no-cache` | May **store**, but must **revalidate with origin before reuse** | Data that may be kept locally but must be verified before every reuse |
| `private` | Private caches may store; shared caches must not store | Per-user content where browser retention is acceptable |
| `public` | Allows shared caches to store if other conditions are met | Static/public content identical for everyone |
| `max-age=N` | Response may be considered fresh for N seconds | Public assets or cacheable content |
| `s-maxage=N` | Freshness for shared caches, taking precedence over max-age in shared caches | CDN policies for public content |
| `must-revalidate` | Once stale, must not be reused without revalidation | Cacheable content that must never be served stale |
| `immutable` | Indicates the resource is unlikely to change during its freshness lifetime | Assets with content hashes in filenames or versioned URLs |

### 3.1. `no-cache` still allows storage

For example:

~~~http
Cache-Control: private, no-cache
ETag: "profile-v6"
~~~

The browser may store the response body in its private cache. When reusing it, it must verify with the origin (for example by sending `If-None-Match`). If the server legitimately returns `304 Not Modified` after checking authorization, the browser may reuse the cached body. **If the requirement is not to retain a copy at all**, `no-cache` is insufficient: use `no-store`.

### 3.2. `no-store` is not a command to wipe old data

~~~http
Cache-Control: no-store
~~~

This directive prevents storage in compliant HTTP caches. It **does not delete copies stored earlier**, nor does it guarantee clearing browser history, custom Service Worker caches, `localStorage`, or downloaded files. If an older response is still fresh and a cache does not contact the origin, the server's updated headers may not even be consulted yet.

For **responses containing access tokens, refresh tokens, or credentials** in OAuth 2.0, RFC 6749 Section 5.1 specifies:

~~~http
Cache-Control: no-store
Pragma: no-cache
~~~

### 3.3. `private` differs from `no-store`

~~~http
Cache-Control: private, max-age=300
~~~

This example allows the browser to keep a personal profile for up to 5 minutes while fresh, while shared caches must not store it. That may be a reasonable trade-off for low-sensitivity content after weighing device and UX risks. For recovery codes, financial statements, medical records, or API keys, prefer `no-store`.

### 3.4. `max-age=0` does not mean "do not store"

`max-age=0` typically makes a response immediately stale, and `must-revalidate` requires revalidation once stale. Those two directives **do not forbid creating a cache copy**. Spring Security pairs them with `no-store` for defense-in-depth and compatibility with older HTTP implementations.

### 3.5. `Pragma` and `Expires` are for compatibility

`Pragma: no-cache` is a historical HTTP/1.0 mechanism; `Expires: 0` marks an already-expired timestamp in many legacy systems. For modern responses carrying highly sensitive data, never replace `Cache-Control: no-store` with `Pragma`/`Expires` alone.

### 3.6. Request headers and response headers are not the same

A client may send:

~~~http
GET /account HTTP/1.1
Host: app.example.org
Cache-Control: no-cache
~~~

A request header mainly asks caches to revalidate when serving data. **It does not force the server to mark the response as non-storable.** To protect private responses, the policy must be on the **response** and enforced at any proxy layers responsible for caching.

## 4. Choosing a cache policy by data category

| Response category | Recommendation | Explanation |
| --- | --- | --- |
| OAuth token endpoint, access/refresh tokens, recovery codes, newly generated passwords | `no-store`; for OAuth responses add `Pragma: no-cache` per RFC | Keep credentials out of HTTP caches |
| Balance APIs, internal documents, sensitive identifiers, admin pages | `no-store` | Minimize copies in HTTP caches |
| Private data PDF/CSV downloads | `no-store` | Do not store in HTTP caches; still protect the file after download |
| Low-sensitivity per-user dashboard | Consider `private, no-cache` if browser storage is acceptable | Allows browser caching but requires revalidation |
| Public app shell HTML, frequently updated | `no-cache` or short freshness | Browser can reuse after verification |
| Public CSS/JS with content-hashed filenames | `public, max-age=31536000, immutable` if URL is immutable | Improves performance without storing user data |
| Public logos, fonts, and images | Appropriate `public, max-age` | Makes effective use of shared/browser caches |
| Error responses accidentally containing sensitive details | `no-store` | Do not protect only status 200 |

These are risk-based patterns, not rigid Spring Security rules for every app. Public content does not strictly have to be cached, and authenticated content is not all secret. Assess the **actual sensitivity of the body**.

## 5. How does Spring Security protect caching?

According to Spring Security 6.5 documentation, when default security response headers are active, the framework emits:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

In the Servlet stack, components such as `HeaderWriterFilter` and `CacheControlHeadersWriter` generate or manage this header group. **Never assume every final response is automatically safe**: if the application sets `Cache-Control` itself, Spring Security may yield to that configuration. Bypassed security filter chains or proxy header overrides can also alter the outcome.

### 5.1. When the controller does not set Cache-Control itself

~~~java
@GetMapping("/account/profile")
Map<String, String> profile(Authentication auth) {
    return Map.of("user", auth.getName());
}
~~~

This is a **Spring MVC method**, not a standalone Java program. If the request passes through a filter chain with default security headers and no other header overrides it, the response typically receives Spring Security's `no-store` header set above.

### 5.2. When the controller sets Cache-Control itself

~~~java
@GetMapping("/public/news")
ResponseEntity<String> news() {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.maxAge(Duration.ofMinutes(10)).cachePublic())
        .body("Public announcement");
}
~~~

This is a snippet placed in a controller; required imports include Spring HTTP's `ResponseEntity`, `CacheControl`, and `java.time.Duration`. The `Cache-Control: max-age=600, public` header is intentionally set by the application for public content. Applying that same policy to a customer data API creates a data exposure risk.

### 5.3. Do not disable default headers without a replacement layer

The Servlet configuration snippet below **disables only default cache-control**:

~~~java
.headers(headers -> headers
    .cacheControl(cache -> cache.disable()))
~~~

And this **disables all security response headers** added by Spring Security configuration:

~~~java
.headers(headers -> headers.disable())
~~~

Do not enable either just to make CSS/JS cacheable. Define a dedicated policy for public assets instead. Disabling all headers also removes other security headers like `X-Content-Type-Options` and `X-Frame-Options`.

### 5.4. `permitAll` and `web.ignoring`

A route configured with `permitAll()` still passes through the Spring Security filter chain, so security headers continue to apply. A route bypassed via `web.ignoring()` skips the filter chain and may not receive headers from Spring Security. Never ignore filters for APIs carrying sensitive data.

### 5.5. Update versions to avoid header-writing bugs

Spring published advisory **CVE-2026-22732** concerning certain scenarios where Servlet security response headers were not written. For Spring Security 6.5 branches, patch **6.5.9** or later is required; applications should run maintained, verified versions. Even after upgrading, keep tests checking headers because risks remain from controller/proxy behavior or misconfigured security matchers.

## 6. Java 17 + Spring Boot + Spring Security (Servlet) example

The application below distinguishes two endpoints:

- `GET /account/me`: requires authentication, contains simulated private data, explicitly sets `Cache-Control: no-store`.
- `GET /public/news`: public, identical for all users, allows caching for up to 10 minutes.

Uses **Java 17**, Maven, **Spring Boot 3.5.16**, and Boot-managed Spring Security. These are released illustrative versions; in production, choose a Spring Boot line receiving security updates, upgrade dependencies, and enable HTTPS. The sample uses HTTP Basic and `{noop}` passwords **for learning only**.

Structure:

~~~text
sensitive-cache-demo/
├── pom.xml
└── src/
    ├── main/java/example/cache/SensitiveCacheApplication.java
    └── test/java/example/cache/SensitiveCacheApplicationTests.java
~~~

**`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>sensitive-cache-demo</artifactId>
  <version>1.0.0</version>
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
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
~~~

**`src/main/java/example/cache/SensitiveCacheApplication.java`**:

~~~java
package example.cache;

import java.time.Duration;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SensitiveCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(SensitiveCacheApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            // Keep default security headers; do not call headers.disable().
            .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo")
                .password("{noop}demo123") // demo only
                .roles("USER")
                .build());
    }

    @RestController
    static class Endpoints {
        @GetMapping("/account/me")
        ResponseEntity<Map<String, String>> account(Authentication auth) {
            return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                    "user", auth.getName(),
                    "balance", "SENSITIVE_DEMO_DATA"));
        }

        @GetMapping("/public/news")
        ResponseEntity<Map<String, String>> news() {
            return ResponseEntity.ok()
                .cacheControl(CacheControl.maxAge(Duration.ofMinutes(10))
                    .cachePublic())
                .body(Map.of("news", "PUBLIC_ANNOUNCEMENT"));
        }
    }
}
~~~

**Why is the code written this way?**

1. `authorizeHttpRequests` blocks `/account/me` when unauthenticated; `/public/**` is accessible without login.
2. `httpBasic` makes testing with `curl` easy. In production you need TLS, properly hashed password storage, and CSRF evaluation if browsers automatically send credentials on state-changing methods.
3. `CacheControl.noStore()` sets an explicit cache policy for sensitive content; this stays protective even if default security headers are altered in another configuration.
4. `CacheControl.maxAge(Duration.ofMinutes(10)).cachePublic()` is used **only** for public announcements.
5. The sample accesses no real data, issues no access tokens, and configures no CDN. Responses contain demo strings.

Run:

~~~bash
mvn spring-boot:run

# Public endpoint: expect HTTP 200 and max-age=600, public
curl -i http://localhost:8080/public/news

# Private endpoint without credentials: expect 401
curl -i http://localhost:8080/account/me

# Private endpoint with demo credentials: expect HTTP 200 + no-store
curl -i -u demo:demo123 http://localhost:8080/account/me
~~~

The private response body may look like `{"balance":"SENSITIVE_DEMO_DATA","user":"demo"}`; **JSON object key ordering is not guaranteed**, so do not test by comparing the raw body string verbatim. Assert values, status codes, and cache headers instead.

### 6.1. MockMvc testing

**`src/test/java/example/cache/SensitiveCacheApplicationTests.java`**:

~~~java
package example.cache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SensitiveCacheApplicationTests {
    @Autowired
    MockMvc mvc;

    @Test
    void sensitiveResponseIsNoStore() throws Exception {
        mvc.perform(get("/account/me").with(httpBasic("demo", "demo123")))
            .andExpect(status().isOk())
            .andExpect(header().string("Cache-Control",
                containsString("no-store")));
    }

    @Test
    void publicResponseHasPublicFreshness() throws Exception {
        mvc.perform(get("/public/news"))
            .andExpect(status().isOk())
            .andExpect(header().string("Cache-Control",
                containsString("public")))
            .andExpect(header().string("Cache-Control",
                containsString("max-age=600")));
    }

    @Test
    void privateResponseRequiresAuthentication() throws Exception {
        mvc.perform(get("/account/me"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Run tests:

~~~bash
mvn test
~~~

Expected result: three passing tests given compatible dependencies and environment. The first test verifies `no-store` is present on the private endpoint, the second verifies the public resource policy, and the final test confirms the private route rejects anonymous access. **MockMvc tests only the application layer**, bypassing CDNs and browser HTTP caches; verify the production edge separately.

## 7. Allowing caching of public static assets

You can optimize static files that **contain no user data** while keeping `no-store` for sensitive documents.

Example header for a JS file with a content hash in its filename:

~~~http
GET /assets/main.a94c1d3.js HTTP/1.1
Host: app.example.org

HTTP/1.1 200 OK
Content-Type: text/javascript
Cache-Control: public, max-age=31536000, immutable
~~~

Only use `immutable` for URLs whose content never changes during the cache lifetime; when a new build creates an updated asset, the URL must change. Never apply this policy to account HTML pages, token endpoints, user data, or private files.

Spring MVC allows configuring public static resources via `WebMvcConfigurer`; the snippet below is an **additional configuration class for a Servlet app**, not a standalone main class:

~~~java
@Configuration
class PublicAssetsConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
            .addResourceLocations("classpath:/static/assets/")
            .setCacheControl(CacheControl.maxAge(Duration.ofDays(365))
                .cachePublic());
    }
}
~~~

Imports: `org.springframework.context.annotation.Configuration`, `org.springframework.web.servlet.config.annotation.WebMvcConfigurer`, `org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry`, `org.springframework.http.CacheControl`, and `java.time.Duration`. Do not enable long freshness for files without versioned URLs; if a file can be replaced at the same path, use a shorter cache duration or versioning.

Some apps configure static files via Spring Boot properties or a CDN; choose **one primary owner** and inspect the final response, especially when both the security filter chain and a caching proxy modify headers.

## 8. Vary, ETag, 304, and the risk of wrong cache keys

### 8.1. `Vary` does not replace protecting private data

~~~http
Cache-Control: private, no-cache
Vary: Accept-Language
~~~

`Vary` indicates which request headers alter the response so caches can distinguish variants. However, `Vary: Cookie` or `Vary: Authorization` **must not be treated as sufficient protection** for confidential data. A CDN may ignore the header, normalize cookies, construct incorrect cache keys, or override them intentionally. Combine with `private` or `no-store` and enforce authorization at the origin.

### 8.2. `ETag` and `If-None-Match` are not security mechanisms

When a response is cacheable, the server may emit an `ETag`. The browser sends `If-None-Match` to validate its stored copy; the server may return `304 Not Modified` if appropriate. For private endpoints, **still verify the user/session/permissions before returning 304**. Never return 304 solely because the ETag string matches and allow the browser to reuse another account's body.

### 8.3. Shared caching with Authorization

HTTP has rules restricting shared caches from storing responses to requests carrying `Authorization`, but exceptions exist when the response contains directives like `public`, `s-maxage`, or `must-revalidate`. Never conclude "because `Authorization` is present, the CDN definitely won't cache it." Response policies and CDN configuration determine real behavior; test cases where user A and user B request the same URL with different credentials.

### 8.4. Cross-user data leakage example

~~~text
A -> GET /api/account/42 -> CDN stores body under cache key = URL
B -> GET /api/account/42 -> CDN serves A's body from cache
~~~

This is a severe vulnerability even if Spring Security properly authenticated requests reaching the origin: B's request may **never reach the origin** if the edge returns a cache hit. Disable caching on private routes or design product-specific cache keys/rules carefully, and test with multiple identities.

## 9. Logout, Back button, and practical limitations

Typical flow:

1. User A logs in and receives a private response with `Cache-Control: no-store`.
2. User A logs out; the server revokes the session/token appropriately.
3. Another person on the same browser clicks Back to return to the account page.
4. Depending on the environment, the browser may issue a network request, restore a snapshot from bfcache, or display SPA state.

The `no-store` header reduces the chance of the HTTP cache storing the new response, **but it does not automatically wipe other data sources**.

- **bfcache:** can restore a DOM snapshot. Behavior varies by browser/version; test Back/Forward explicitly.
- **SPA store:** if the app does not clear state on logout, A's data can remain in JavaScript memory.
- **Service Worker:** may retain responses in the Cache API.
- **Other tabs:** may still show pre-logout UI, even if new requests are rejected.
- **Downloaded files:** downloaded CSV/PDF files remain on the device.
- **Browser extensions/screenshots/logs:** are not erased by response headers.

To minimize UI exposure, SPAs must clear state on logout, handle multiple tabs, mask data when session re-verification is needed, and never treat UI-only protection as real authorization. The server must always reject new requests once a session has expired.

### 9.1. Restoring a page from bfcache

Browsers can fire the `pageshow` event with `event.persisted` when a document is restored from bfcache. An SPA can use this signal to **immediately hide stale information and recheck the session** before displaying sensitive data on screen. The example below is only a frontend integration snippet:

~~~javascript
window.addEventListener("pageshow", async (event) => {
  if (!event.persisted) return;

  document.body.classList.add("session-recheck");
  const response = await fetch("/api/session-status", {
    credentials: "same-origin",
    cache: "no-store"
  });

  if (response.ok) {
    window.location.reload();
  } else {
    window.location.replace("/login");
  }
});
~~~

The `/api/session-status` endpoint and `session-recheck` CSS class must be provided by your application; the snippet above is not a built-in Spring Security API. A real application must mask data properly during loading/restoring phases, handle network errors safely, and avoid flashing data for even a single frame prior to verification.

### 9.2. Clear-Site-Data on logout

Supporting browsers can react to the header:

~~~http
Clear-Site-Data: "cache", "storage"
~~~

It can help clear certain types of browser-side data within the specified scope, though effectiveness depends on the user agent and it neither clears CDN caches nor every local copy on disk. Use the `"cookies"` directive carefully because of its broad impact. Do not rely on `Clear-Site-Data` as an instant remediation for already-leaked data.

## 10. WebFlux: same goal, different API

Spring Security WebFlux uses `ServerHttpSecurity`, `SecurityWebFilterChain`, and reactive WebFilters instead of `HttpSecurity`/Servlet filters. By default, the framework also provides cache security headers when the corresponding chain applies.

Illustrative configuration **in a separate Spring WebFlux application**—do not copy verbatim into a Servlet application:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(a -> a
            .pathMatchers("/public/**").permitAll()
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Imports: `org.springframework.context.annotation.Bean`, `org.springframework.security.config.Customizer`, `org.springframework.security.config.web.server.ServerHttpSecurity`, and `org.springframework.security.web.server.SecurityWebFilterChain`. Place the method inside a `@Configuration` class.

A reactive controller can also set a per-response policy:

~~~java
@GetMapping("/account/reactive")
Mono<ResponseEntity<String>> sensitive() {
    return Mono.just(ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body("DEMO_PRIVATE_DATA"));
}
~~~

Corresponding imports: `GetMapping`, `Mono`, `ResponseEntity`, and `CacheControl`. This is only a method snippet, not standalone; the route must be secured by Spring Security in a real application.

If you need to disable only the cache-control writer in WebFlux, the syntax is:

~~~java
.headers(headers -> headers.cache(cache -> cache.disable()))
~~~

This **demonstrates configuration capability**, not a default recommendation. Use it only when all responses already have a tested alternative cache protection layer. Never mix `ServerHttpSecurity` into Servlet `HttpSecurity`.

## 11. Testing from browser to CDN

### 11.1. Checking at the application

~~~bash
curl -i http://localhost:8080/public/news
curl -i http://localhost:8080/account/me
curl -i -u demo:demo123 http://localhost:8080/account/me
~~~

Compare status, `Cache-Control`, `Pragma`, `Expires`, `Vary`, `Age`, `ETag`, `Set-Cookie`, and `Content-Type`. When inspecting real responses in a browser, do not enable DevTools "Disable cache" and conclude the server's policy is right: that option changes how the browser itself uses caching during the debug session.

### 11.2. HEAD does not replace GET in testing

You can use `curl -I` for HEAD, but some applications/proxies handle HEAD differently from GET. For responses carrying data, always test GET with authentication and check the policy on the actual body-bearing response.

### 11.3. Verification matrix

| Scenario | Expected result |
| --- | --- |
| GET sensitive info, authenticated | Final response has `Cache-Control: no-store` |
| GET versioned public resource | Has freshness/public per policy |
| Anonymous call to sensitive endpoint | 401 or login redirect per chain; no private body |
| Logout then re-request private content | Server rejects or requires fresh login |
| Back/Forward after logout | Neither HTTP cache, bfcache, nor SPA state exposes old content |
| User A and user B call identical URL through CDN | Never receive the other user's body |
| 302/401/403 responses or private downloads | Not inadvertently cached by overly broad rules |
| ETag and 304 revalidation | Server does not bypass authorization checks on revalidation |
| Gateway forces "cache all" | Sensitive endpoints must be exempted and measured at the edge |
| Service Worker/Offline | Private content is not cached in `CacheStorage` |
| Security matcher changed, Spring Security upgraded | CI and integration tests confirm headers are not lost |
| Multi-node and multi-tenant | Cache keys and policies remain consistent |

### 11.4. Observing at the proxy/CDN

Beyond `Cache-Control`, some CDNs emit cache status headers like `Age` or provider-specific headers. Repeatedly measure the same URL with **two test accounts** to verify there is no cross-caching; never use real user data. Check bypass rules, cookie/header-based cache keys, `Set-Cookie`, `Authorization`, status codes, `Vary`, cache TTLs, and stale-serving policies.

Do not test GET results only on localhost. A CDN configuration can ignore or rewrite origin headers; actual behavior is determined across the entire request path.

## 12. Common implementation mistakes

**Mistake 1 – Confusing `no-cache` with "do not store".** It still allows caching; use `no-store` if the body must not be retained.

**Mistake 2 – Using only `private` for tokens.** Browser private caches can still store it; tokens require `no-store` per relevant standards.

**Mistake 3 – Using `max-age=0` instead of `no-store`.** Data can still remain in the cache and be revalidated.

**Mistake 4 – Assuming Spring Security always enforces `no-store`.** Controller/gateway headers can override it, or the security chain may be bypassed.

**Mistake 5 – Disabling all security headers to speed up assets.** This drops other defenses; use a selective cache policy for public assets instead.

**Mistake 6 – Configuring `public` on an account data API.** Shared caches can store the private response, leaking user A's data to user B.

**Mistake 7 – Using `Vary: Cookie` instead of authorization.** `Vary` does not grant permissions and CDNs can misconfigure cache keys.

**Mistake 8 – Returning 304 without checking the session.** The server must verify authentication/authorization before letting a client reuse a stored body.

**Mistake 9 – Treating logout as a cache-wiping command.** Logout does not automatically clear browser data, Service Workers, downloads, or logs.

**Mistake 10 – Assuming `no-store` prevents all bfcache.** Browsers can restore DOM snapshots independently; test Back/Forward.

**Mistake 11 – Testing only with MockMvc.** MockMvc does not pass through edge/CDN layers where response headers may be modified.

**Mistake 12 – Checking only HTTP 200 responses.** Sensitive errors/redirects/downloads also need clear policies; test all flows.

**Mistake 13 – Using only `Pragma: no-cache` on OAuth responses.** RFC 6749 `5.1` requires `Cache-Control: no-store` and `Pragma: no-cache`.

**Mistake 14 – Updating headers and assuming old cached responses are gone.** Existing caches may retain copies until revalidation; plan cache purges and assess leakage risk.

## 13. Implementation checklist

1. **Classify routes:** tokens, sensitive data, dashboards, downloads, HTML shells, static resources; choose justified policies.
2. **Configure per response:** `no-store` for secrets; `private`/`no-cache` where browser retention is acceptable; long public caching only for versioned public assets.
3. **Preserve security headers properly:** avoid blanket disabling; audit security chains, matchers, and bypass paths.
4. **Protect the origin:** authenticate and authorize both regular requests and conditional `ETag/304` requests, handling logout and session expiry.
5. **Inspect every cache layer:** browser HTTP cache, bfcache, Service Worker, proxy, CDN, app cache.
6. **Prevent data leaks:** avoid logging tokens, keep credentials out of URLs, avoid caching user-specific responses at the CDN.
7. **Test with multiple identities:** same URL across two accounts, after logout, Back/Forward, private browsing, file downloads, errors/redirects.
8. **Test in CI and at the production edge:** ensure headers remain intact after dependency upgrades, router/security filter changes, or CDN rule updates.

## 14. Self-check questions

**Q1.** Does `Cache-Control: no-cache` guarantee the browser will not store a copy of a profile?  
**Answer:** No. It allows storage while requiring revalidation before reuse.

**Q2.** How does `Cache-Control: private` differ from `no-store`?  
**Answer:** `private` stops shared caches from storing the response while still allowing browser caching; `no-store` instructs HTTP caches not to keep a copy at all.

**Q3.** Which cache headers does Spring Security send by default?  
**Answer:** `Cache-Control: no-cache, no-store, max-age=0, must-revalidate`, `Pragma: no-cache`, and `Expires: 0` when default security headers are active.

**Q4.** An application controller explicitly sets `Cache-Control: public, max-age=3600` on a profile. Will Spring Security definitely overwrite it with `no-store`?  
**Answer:** No. Spring Security allows per-response customization; you must fix the policy at the layer emitting the header and verify the final result.

**Q5.** Why must the Back button still be tested after logout?  
**Answer:** Beyond the HTTP cache, there are bfcache, SPA state, Service Workers, and already-open tabs.

**Q6.** Why shouldn't `public, max-age=31536000` be used for profile HTML just because its JS file has a content hash?  
**Answer:** HTML contains user-specific data unlike public static assets. Only immutable content safe for everyone is suited to long-term caching.

**Q7.** What does RFC 6749 require for responses returning OAuth access/refresh tokens?  
**Answer:** `Cache-Control: no-store` and `Pragma: no-cache`.

**Q8.** Does MockMvc testing prove safety at the CDN?  
**Answer:** No. MockMvc tests only the application; you must inspect responses at the edge and verify cache hit/miss behavior across multiple identities.

## 15. References

- [Spring Security 6.5 – Servlet HTTP Security Response Headers](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html): default headers, cache-control customization, and disabling.
- [Spring Security 6.5 – WebFlux HTTP Security Response Headers](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html): reactive configuration.
- [Spring Framework – HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): Spring MVC `CacheControl`, ETag, and 304.
- [RFC 9111 – HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): definitions of `no-store`, `no-cache`, `private`, `public`, and revalidation.
- [RFC 6749 – OAuth 2.0, Section 5.1 Access Token Response](https://www.rfc-editor.org/rfc/rfc6749.html#section-5.1): token response protection requirements.
- [MDN – Cache-Control header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control): directive descriptions and limitations.
- [MDN – HTTP Caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching): browser/shared caches, static assets, old stored responses.
- [Spring Security Advisory – CVE-2026-22732](https://spring.io/security/cve-2026-22732/): why patched versions and actual header testing are necessary.
